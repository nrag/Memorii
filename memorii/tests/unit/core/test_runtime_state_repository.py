"""Runtime state repository: typed views, closed content, published writes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.persistence.runtime_contracts import (
    ActionAttemptRecord,
    BeliefUpdateProposal,
    HypothesisContent,
    NodeMergeProposal,
    OverlayJustificationBinding,
    RuntimeCommandReceipt,
    RuntimeCommandRequest,
    RuntimeOverlayVersion,
    SolverJustificationRecord,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import (
    RuntimeStateError,
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _task(task_id: str = "task:one") -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        principal="principal:a",
        goal="Diagnose the latency regression",
        created_at=_NOW,
        root_execution_node_id="exec:root",
    )


def _run(solver_id: str = "solver:main") -> SolverRunRecord:
    return SolverRunRecord(
        solver_id=solver_id,
        task_id="task:one",
        parent_execution_node_id="exec:root",
        category="diagnostic",
        created_by="host",
    )


def _seeded_service(tmp_path: Path) -> StorageAdministrationService:
    service = StorageAdministrationService(tmp_path / "installation")
    service.initialize()
    return service


def test_runtime_writes_publish_and_advance_the_runtime_head(tmp_path: Path) -> None:
    service = _seeded_service(tmp_path)
    try:
        revision = publish_runtime_change(
            service,
            lambda connection, repository: (
                repository.apply_task(connection, _task()),
                repository.apply_solver_run(connection, _run()),
                repository.apply_solver_node(
                    connection,
                    solver_id="solver:main",
                    node_id="node:h1",
                    content=HypothesisContent(
                        statement="Cache stampede",
                        strength=0.7,
                        epistemic_status="candidate",
                    ),
                    metadata_json=json.dumps({"created_at": _NOW.isoformat()}),
                ),
            ),
        )
        assert revision >= 1
        repository = RuntimeStateRepository(service.partition())
        assert repository.runtime_revision() == revision
        task = repository.get_task("task:one")
        assert task is not None and task.lifecycle == "active"
        runs = repository.list_solver_runs("task:one")
        assert [run.solver_id for run in runs] == ["solver:main"]
        content = repository.read_solver_node_content("solver:main", "node:h1")
        assert isinstance(content, HypothesisContent)
        assert content.statement == "Cache stampede"
        # Memory-plane heads are untouched by a runtime-only publication.
        snapshot = service.acquire_verified_snapshot()
        assert snapshot.vector.memory_write_revision == 0
        assert snapshot.vector.runtime_position.sequence == revision  # type: ignore[attr-defined]
    finally:
        service.close()


def test_solver_node_content_rejects_unknown_and_generic_payloads(tmp_path: Path) -> None:
    from pydantic import ValidationError

    service = _seeded_service(tmp_path)
    try:
        with pytest.raises(ValidationError, match="validation error"):
            publish_runtime_change(
                service,
                lambda connection, repo: repo.apply_solver_node(
                    connection,
                    solver_id="solver:main",
                    node_id="node:bad",
                    content={"kind": "HYPOTHESIS", "statement": "generic dict"},
                    metadata_json="{}",
                ),
            )
        # The refused publication leaves no runtime revision change.
        assert RuntimeStateRepository(service.partition()).runtime_revision() == 0
    finally:
        service.close()


def test_justification_role_disjointness_enforced(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="disjoint"):
        SolverJustificationRecord(
            justification_id="j:1",
            solver_id="solver:main",
            conclusion="c",
            supporting_ids=("node:h1",),
            contradicting_ids=("node:h1",),
            strength=0.5,
        )


def test_command_union_gates_payloads_by_kind() -> None:
    RuntimeCommandRequest(
        kind="propose_state_change",
        operation_id="op:1",
        task_id="task:one",
        expected_revision=1,
        proposal=BeliefUpdateProposal(
            solver_id="solver:main",
            node_id="node:h1",
            justification_id="j:1",
            epistemic_status="committed",
            strength=0.8,
        ),
    )
    with pytest.raises(ValueError, match="completion evidence"):
        RuntimeCommandRequest(
            kind="complete_task",
            operation_id="op:2",
            task_id="task:one",
            expected_revision=1,
        )
    with pytest.raises(ValueError, match="differ"):
        NodeMergeProposal(
            solver_id="s",
            source_node_id="a",
            target_node_id="a",
            reason="same",
        )


def test_overlays_and_actions_round_trip_with_receipts(tmp_path: Path) -> None:
    service = _seeded_service(tmp_path)
    try:
        overlay = RuntimeOverlayVersion(
            version_id="overlay:v1",
            solver_id="solver:main",
            node_bindings=(
                OverlayJustificationBinding(
                    node_id="node:h1",
                    active_justification_ids=("j:1",),
                    frontier=True,
                    reopenable=True,
                ),
            ),
            created_at=_NOW,
            committed=True,
        )
        action = ActionAttemptRecord(
            action_id="action:measure",
            task_id="task:one",
            recommendation_id="rec:1",
            recommendation_revision=1,
            executor_binding="host",
            status="dispatched",
        )
        receipt = RuntimeCommandReceipt(
            operation_id="op:dispatch",
            client_namespace="client:a",
            request_digest="a" * 64,
            status="committed",
            base_revision=0,
            current_revision=1,
        )
        publish_runtime_change(
            service,
            lambda connection, repository: (
                repository.apply_overlay(connection, overlay),
                repository.apply_action_attempt(connection, action),
                repository.apply_command_receipt(connection, receipt),
            ),
        )
        repository = RuntimeStateRepository(service.partition())
        assert repository.get_overlay("overlay:v1") == overlay
        assert repository.get_action_attempt("action:measure") == action
        assert (
            repository.get_command_receipt("client:a", "op:dispatch") == receipt
        )
    finally:
        service.close()


def test_runtime_publication_refuses_uninitialized_installation(tmp_path: Path) -> None:
    service = StorageAdministrationService(tmp_path / "empty")
    try:
        with pytest.raises(RuntimeStateError):
            publish_runtime_change(
                service, lambda connection, repository: None
            )
    finally:
        service.close()
