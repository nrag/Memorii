"""Harness state envelope and service: budgets, denials, rendering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state import (
    HarnessOutputBlock,
    HarnessStateEnvelope,
    HarnessStateService,
    HarnessTextRenderer,
    RuntimeReadGrant,
    build_envelope,
    render_harness_state,
)
from memorii.core.persistence.runtime_contracts import (
    ActionAttemptRecord,
    OverlayJustificationBinding,
    RuntimeOverlayVersion,
    SolverJustificationRecord,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _grant(task_id: str, *, epoch: int = 1, expires_in_minutes: int = 5) -> RuntimeReadGrant:
    return RuntimeReadGrant(
        grant_id="grant:one",
        principal="principal:a",
        allowed_task_ids=(task_id,),
        epoch=epoch,
        expires_at=datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
    )


def _seeded_service(tmp_path: Path) -> tuple[HarnessStateService, str, RuntimeStateRepository]:
    administration = StorageAdministrationService(tmp_path / "installation")
    administration.initialize()
    repository = RuntimeStateRepository(administration.partition())
    task_id = "task:harness"

    def seed(connection, repo) -> None:
        repo.apply_task(
            connection,
            TaskRecord(
                task_id=task_id,
                principal="principal:a",
                goal="Diagnose latency",
                created_at=_NOW,
                root_execution_node_id="exec:root",
                acceptance_criteria=("acceptance:p95-restored",),
            ),
        )
        repo.apply_solver_run(
            connection,
            SolverRunRecord(
                solver_id="solver:harness",
                task_id=task_id,
                parent_execution_node_id="exec:root",
                category="diagnostic",
                created_by="test",
            ),
        )
        repo.apply_justification(
            connection,
            SolverJustificationRecord(
                justification_id="just:active",
                solver_id="solver:harness",
                conclusion="burst aligns with misses",
                supporting_ids=("node:obs",),
                strength=0.8,
                active=True,
            ),
        )
        repo.apply_justification(
            connection,
            SolverJustificationRecord(
                justification_id="just:retired",
                solver_id="solver:harness",
                conclusion="clock skew ruled out",
                contradicting_ids=("node:obs",),
                strength=0.2,
                active=False,
            ),
        )
        repo.apply_overlay(
            connection,
            RuntimeOverlayVersion(
                version_id="overlay:harness",
                solver_id="solver:harness",
                node_bindings=(
                    OverlayJustificationBinding(
                        node_id="node:h1",
                        active_justification_ids=("just:active",),
                        frontier=True,
                        reopenable=True,
                    ),
                    OverlayJustificationBinding(node_id="node:obs", unexplained=True),
                ),
                created_at=_NOW,
                committed=True,
            ),
        )
        repo.apply_action_attempt(
            connection,
            ActionAttemptRecord(
                action_id="action:pending",
                task_id=task_id,
                recommendation_id="rec:1",
                recommendation_revision=1,
                executor_binding="host",
                status="dispatched",
            ),
        )

    publish_runtime_change(administration, seed, operation_binding="harness_state_seed")
    return HarnessStateService(repository), task_id, repository


def test_envelope_binds_digest_and_budgets() -> None:
    envelope = build_envelope(
        protocol_version=1, task_id="task:x", revision=1, status="ready"
    )
    with pytest.raises(ValueError, match="digest is invalid"):
        HarnessStateEnvelope.model_validate(
            envelope.model_dump(mode="json") | {"revision": envelope.revision + 1}
        )
    with pytest.raises(ValueError, match="both candidate and committed"):
        HarnessOutputBlock(label="x", candidate=True, committed=True)


def test_service_denies_before_lookup_and_hides_existence(tmp_path: Path) -> None:
    service, task_id, _ = _seeded_service(tmp_path)
    other_grant = _grant("task:other")
    with pytest.raises(Exception, match="denied"):
        service.read_state(task_id=task_id, grant=other_grant)
    with pytest.raises(Exception, match="not_found"):
        service.read_state(task_id="task:missing", grant=_grant("task:missing"))
    expired = RuntimeReadGrant(
        grant_id="grant:one",
        principal="principal:a",
        allowed_task_ids=(task_id,),
        epoch=1,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    with pytest.raises(Exception, match="denied"):
        service.read_state(task_id=task_id, grant=expired)


def test_envelope_carries_pending_reconcile_and_distinct_commitment(tmp_path: Path) -> None:
    service, task_id, _ = _seeded_service(tmp_path)
    envelope = service.read_state(task_id=task_id, grant=_grant(task_id))
    assert envelope.status == "reconcile_required"
    assert envelope.pending_actions == ("action:pending",)
    assert envelope.recommendation_kind == "reconcile"
    candidate_labels = {block.label for block in envelope.candidate_hypotheses}
    committed_labels = {block.label for block in envelope.committed_hypotheses}
    assert candidate_labels == {"just:active"}
    assert committed_labels == {"just:retired"}
    assert candidate_labels.isdisjoint(committed_labels)
    assert envelope.selected_overlay_id == "overlay:harness"


def test_renderer_is_deterministic_and_labels_commitment(tmp_path: Path) -> None:
    service, task_id, _ = _seeded_service(tmp_path)
    envelope = service.read_state(task_id=task_id, grant=_grant(task_id))
    text = render_harness_state(envelope)
    again = HarnessTextRenderer().render(envelope)
    assert text == again
    assert "hypothesis (candidate): just:active" in text
    assert "hypothesis (committed): just:retired" in text
    assert "recommend: reconcile action:pending" in text
    assert "unexplained: node:obs" in text
    assert f"state-digest: {envelope.state_digest}" in text


def test_unsupported_view_fails_closed(tmp_path: Path) -> None:
    service, task_id, _ = _seeded_service(tmp_path)
    with pytest.raises(Exception, match="unsupported view"):
        service.read_state(task_id=task_id, grant=_grant(task_id), view="raw-sql")


def test_frontier_budget_truncation_records_omission(tmp_path: Path) -> None:
    administration = StorageAdministrationService(tmp_path / "installation")
    administration.initialize()
    repository = RuntimeStateRepository(administration.partition())
    task_id = "task:wide"

    def seed(connection, repo) -> None:
        repo.apply_task(
            connection,
            TaskRecord(
                task_id=task_id,
                principal="principal:a",
                goal="Wide frontier",
                created_at=_NOW,
                root_execution_node_id="exec:root",
            ),
        )
        repo.apply_solver_run(
            connection,
            SolverRunRecord(
                solver_id="solver:wide",
                task_id=task_id,
                parent_execution_node_id="exec:root",
                category="diagnostic",
                created_by="test",
            ),
        )
        repo.apply_overlay(
            connection,
            RuntimeOverlayVersion(
                version_id="overlay:wide",
                solver_id="solver:wide",
                node_bindings=tuple(
                    OverlayJustificationBinding(node_id=f"node:{index}", frontier=True)
                    for index in range(24)
                ),
                created_at=_NOW,
                committed=True,
            ),
        )

    publish_runtime_change(administration, seed, operation_binding="harness_state_seed")
    service = HarnessStateService(repository)
    envelope = service.read_state(task_id=task_id, grant=_grant(task_id))
    assert len(envelope.frontier) == 16
    assert any("frontier truncated" in omission for omission in envelope.omissions)


def _bound_ports(tmp_path: Path):
    from memorii.core.harness_state.binding import (
        HermesRuntimeStatePorts,
        RuntimeTaskBinding,
    )
    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )

    service, task_id, _repository = _seeded_service(tmp_path)
    ports = HermesRuntimeStatePorts(
        StorageAdministrationService(tmp_path / "installation")
    )
    ports.bind_task(
        RuntimeTaskBinding(
            installation_task_id=task_id,
            host_session_id="session:one",
            granted_to_principal="principal:a",
        )
    )
    return ports, task_id


def test_bound_prefetch_renders_envelope_and_unbound_denies(tmp_path: Path) -> None:
    ports, task_id = _bound_ports(tmp_path)
    text = ports.runtime_prefetch_text(principal="principal:a")
    assert text is not None
    assert f"task={task_id}" in text
    assert ports.runtime_prefetch_text(principal="principal:other") is None
    from memorii.core.harness_state.service import HarnessStateError

    with pytest.raises(HarnessStateError, match="no runtime task binding"):
        ports.read_bound_state(principal="principal:other")


def test_tool_summary_is_plain_about_nondurable_source(tmp_path: Path) -> None:
    ports, _task_id = _bound_ports(tmp_path)
    durable = ports.tool_state_summary(principal="principal:a")
    assert durable["durable_runtime_view"] is True
    assert durable["status"] == "reconcile_required"
    nondurable = ports.tool_state_summary(principal="principal:other")
    assert nondurable["durable_runtime_view"] is False
    assert nondurable["source"] == "provider-work-state-summary"
