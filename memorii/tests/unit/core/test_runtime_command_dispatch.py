"""Durable command dispatch: idempotency, lifecycle, dispatch reservation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.persistence.runtime_api import (
    RuntimeCommandError,
    RuntimeCommandService,
    RuntimeOperationAttempt,
    RuntimeOutboxDelivery,
    command_request_digest,
    fence_takeover,
    reserve_dispatch,
)
from memorii.core.persistence.runtime_contracts import (
    ActionAttemptRecord,
    RuntimeCommandRequest,
    TaskCompletionEvidence,
)
from memorii.core.persistence.runtime_repository import (
    publish_runtime_change,
)
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _service(tmp_path: Path) -> RuntimeCommandService:
    administration = StorageAdministrationService(tmp_path / "installation")
    administration.initialize()
    return RuntimeCommandService(administration)


def _start(service: RuntimeCommandService, goal: str = "Diagnose latency") -> object:
    return service.dispatch(
        RuntimeCommandRequest(kind="start_task", operation_id="op:start", goal=goal)
    )


def _seeded_task_id(service: RuntimeCommandService) -> str:
    _start(service)
    repository = service.repository
    tasks = repository.list_tasks()
    assert len(tasks) == 1
    return tasks[0].task_id


def test_start_allocates_task_and_repeat_returns_same_receipt(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        first = _start(service)
        repeat = _start(service)
        assert repeat == first
        assert first.status == "committed"
        assert len(service.repository.list_tasks()) == 1
    finally:
        service._administration.close()


def test_divergent_reuse_of_operation_id_fails(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        _start(service)
        with pytest.raises(RuntimeCommandError, match="divergent request"):
            service.dispatch(
                RuntimeCommandRequest(
                    kind="start_task", operation_id="op:start", goal="Different goal"
                )
            )
    finally:
        service._administration.close()


def test_task_lifecycle_commands_close_terminal_tasks(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        task_id = _seeded_task_id(service)
        service.dispatch(
            RuntimeCommandRequest(
                kind="pause_task",
                operation_id="op:pause",
                task_id=task_id,
                expected_revision=1,
                pause_reason="user lunch",
            )
        )
        task = service.repository.get_task(task_id)
        assert task is not None and task.lifecycle == "paused"
        service.dispatch(
            RuntimeCommandRequest(
                kind="complete_task",
                operation_id="op:complete",
                task_id=task_id,
                expected_revision=2,
                completion_evidence=TaskCompletionEvidence(
                    acceptance_results=("acceptance:latency-met",),
                    unresolved_blocker_acknowledged=True,
                ),
            )
        )
        completed = service.repository.get_task(task_id)
        assert completed is not None and completed.lifecycle == "completed"
        with pytest.raises(RuntimeCommandError, match="mutation commands are closed"):
            service.dispatch(
                RuntimeCommandRequest(
                    kind="pause_task",
                    operation_id="op:pause-again",
                    task_id=task_id,
                    expected_revision=3,
                    pause_reason="too late",
                )
            )
        # A lost acknowledgement replays the same completion idempotently.
        repeat = service.dispatch(
            RuntimeCommandRequest(
                kind="complete_task",
                operation_id="op:complete",
                task_id=task_id,
                expected_revision=2,
                completion_evidence=TaskCompletionEvidence(
                    acceptance_results=("acceptance:latency-met",),
                    unresolved_blocker_acknowledged=True,
                ),
            )
        )
        assert repeat.status == "committed"
    finally:
        service._administration.close()


def test_completion_blocked_by_unresolved_dispatched_action(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        task_id = _seeded_task_id(service)
        publish_runtime_change(
            service._administration,
            lambda connection, repository: repository.apply_action_attempt(
                connection,
                ActionAttemptRecord(
                    action_id="action:pending",
                    task_id=task_id,
                    recommendation_id="rec:1",
                    recommendation_revision=1,
                    executor_binding="host-a",
                    status="dispatched",
                ),
            ),
        )
        with pytest.raises(RuntimeCommandError, match="unresolved dispatched actions"):
            service.dispatch(
                RuntimeCommandRequest(
                    kind="complete_task",
                    operation_id="op:complete",
                    task_id=task_id,
                    expected_revision=1,
                    completion_evidence=TaskCompletionEvidence(
                        acceptance_results=("acceptance:x",),
                    ),
                )
            )
    finally:
        service._administration.close()


def test_stale_expected_revision_conflicts(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        task_id = _seeded_task_id(service)
        with pytest.raises(RuntimeCommandError, match="moved past"):
            service.dispatch(
                RuntimeCommandRequest(
                    kind="pause_task",
                    operation_id="op:stale",
                    task_id=task_id,
                    expected_revision=0,
                    pause_reason="stale",
                )
            )
    finally:
        service._administration.close()


def test_fenced_takeover_displaces_terminal_with_cause() -> None:
    attempt = RuntimeOperationAttempt(
        receipt_id="op:1",
        attempt_ordinal=1,
        request_digest="a" * 64,
        base_task_revision=0,
        model_binding="no-model",
        policy_digest="b" * 64,
        stage="awaiting_model",
        lease_owner="worker-a",
        fence_token=1,
    )
    displaced = fence_takeover(attempt, replacement_ordinal=2)
    assert displaced.terminal_cause == "superseded_by_fence"
    assert displaced.lease_owner is None
    with pytest.raises(RuntimeCommandError, match="strictly higher"):
        fence_takeover(attempt, replacement_ordinal=1)


def test_dispatch_reservation_prevents_double_execution(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        task_id = _seeded_task_id(service)
        first = reserve_dispatch(
            service.repository,
            service._administration,
            task_id=task_id,
            recommendation_id="rec:replay",
            recommendation_revision=1,
            executor_binding="host-a",
        )
        again = reserve_dispatch(
            service.repository,
            service._administration,
            task_id=task_id,
            recommendation_id="rec:replay",
            recommendation_revision=1,
            executor_binding="host-a",
        )
        assert again.action_id == first.action_id
        with pytest.raises(RuntimeCommandError, match="already reserved"):
            reserve_dispatch(
                service.repository,
                service._administration,
                task_id=task_id,
                recommendation_id="rec:replay",
                recommendation_revision=1,
                executor_binding="host-b",
            )
    finally:
        service._administration.close()


def test_outbox_delivery_requires_target_result_when_delivered() -> None:
    with pytest.raises(ValueError, match="target receipt"):
        RuntimeOutboxDelivery(
            delivery_id="d:1",
            origin_operation_id="op:1",
            kind="work_projection",
            target_protocol="memory-plane-admission",
            payload_digest="c" * 64,
            fence_token=1,
            status="delivered",
        )


def test_request_digest_excludes_expected_revision_only() -> None:
    base = RuntimeCommandRequest(
        kind="pause_task",
        operation_id="op:x",
        task_id="task:t",
        expected_revision=3,
        pause_reason="r",
    )
    same_different_revision = base.model_copy(update={"expected_revision": 4})
    different_reason = base.model_copy(update={"pause_reason": "other"})
    assert command_request_digest(base) == command_request_digest(same_different_revision)
    assert command_request_digest(base) != command_request_digest(different_reason)


def test_unimplemented_command_kinds_fail_closed(tmp_path: Path) -> None:
    """No kind commits a success receipt without a durable effect."""
    service = _service(tmp_path)
    try:
        task_id = _seeded_task_id(service)
        from memorii.core.persistence.runtime_contracts import (
            BeliefUpdateProposal,
        )
        cases = (
            ("record_observation", {}),
            (
                "propose_state_change",
                {
                    "proposal": BeliefUpdateProposal(
                        solver_id="solver:one",
                        node_id="node:h1",
                        justification_id="j:1",
                        epistemic_status="committed",
                        strength=0.7,
                    )
                },
            ),
            ("resume_task", {}),
            ("checkpoint_task", {}),
            ("replan_task", {}),
        )
        for kind, extra in cases:
            with pytest.raises(RuntimeCommandError, match="no implemented durable effect"):
                service.dispatch(
                    RuntimeCommandRequest(
                        kind=kind,
                        operation_id=f"op:{kind}",
                        task_id=task_id,
                        expected_revision=1,
                        **extra,
                    )
                )
        # Nothing was committed: no receipts, no revision change for these.
        assert service.repository.runtime_revision() == 1
    finally:
        service._administration.close()


def test_receipt_revisions_pin_the_runtime_head(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        first = _start(service)
        assert (first.base_revision, first.current_revision) == (0, 1)
        task_id = service.repository.list_tasks()[0].task_id
        second = service.dispatch(
            RuntimeCommandRequest(
                kind="pause_task",
                operation_id="op:pause",
                task_id=task_id,
                expected_revision=1,
                pause_reason="lunch",
            )
        )
        assert (second.base_revision, second.current_revision) == (1, 2)
    finally:
        service._administration.close()


def test_duplicate_dispatch_from_second_client_reapplies_nothing(tmp_path: Path) -> None:
    """Two command services over one root: the fence-level re-check holds."""
    task_id_holder: dict[str, str] = {}
    administration = StorageAdministrationService(tmp_path / "shared")
    administration.initialize()
    administration.close()
    service_a = RuntimeCommandService(
        StorageAdministrationService(tmp_path / "shared"), client_namespace="client-a"
    )
    try:
        first = service_a.dispatch(
            RuntimeCommandRequest(
                kind="start_task", operation_id="op:start", goal="Shared root"
            )
        )
        assert first.status == "committed"
        task_id_holder["task"] = service_a.repository.list_tasks()[0].task_id
    finally:
        service_a._administration.close()
    service_b = RuntimeCommandService(
        StorageAdministrationService(tmp_path / "shared"), client_namespace="client-a"
    )
    try:
        repeat = service_b.dispatch(
            RuntimeCommandRequest(
                kind="start_task", operation_id="op:start", goal="Shared root"
            )
        )
        assert repeat == first
        assert len(service_b.repository.list_tasks()) == 1
        assert service_b.repository.runtime_revision() == 1
    finally:
        service_b._administration.close()


def test_terminal_task_still_permits_checkpoint_and_resume(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        task_id = _seeded_task_id(service)
        service.dispatch(
            RuntimeCommandRequest(
                kind="complete_task",
                operation_id="op:complete",
                task_id=task_id,
                expected_revision=1,
                completion_evidence=TaskCompletionEvidence(
                    unresolved_blocker_acknowledged=True
                ),
            )
        )
        for kind in ("checkpoint_task", "resume_task"):
            with pytest.raises(RuntimeCommandError, match="no implemented durable effect"):
                service.dispatch(
                    RuntimeCommandRequest(
                        kind=kind,
                        operation_id=f"op:{kind}",
                        task_id=task_id,
                        expected_revision=2,
                    )
                )
    finally:
        service._administration.close()
