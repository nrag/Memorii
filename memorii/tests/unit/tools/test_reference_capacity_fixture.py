"""Check untimed setup through the real signed SQLite owners at small scale."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from memorii.core.persistence.runtime_repository import RuntimeStateError, publish_runtime_change
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.stores.sqlite.partition import PARTITION_SCHEMA_VERSION, RAW_MEMORY_PAYLOAD_SCHEMA_VERSION
from tests.support.reference_capacity import FIXTURE_START, SOURCE_BODY_BYTES, EventFillInput, TaskAllocation
from tests.support.reference_capacity_fixture import ReferenceFixtureError, _audit, _prepare, main

_TASK = TaskAllocation(
    distribution="balanced", index=0, execution_nodes=3, solver_nodes=9, first_solver_node=0,
    first_source=0, sources=2,
)


def test_signed_fixture_retains_sources_and_exact_graph_counts(tmp_path: Path) -> None:
    first = _prepare(tmp_path / "first", "balanced", (_TASK,), require_fresh_v8=True)
    second = _prepare(tmp_path / "second", "balanced", (_TASK,))
    assert first.partition_schema_version == 8
    assert first.fixture_origin == "fresh-default"
    assert first.partition_tuple_digest != second.partition_tuple_digest
    assert first.graph_digest == second.graph_digest
    assert first.sources_digest == second.sources_digest
    assert first.source_receipts_digest == second.source_receipts_digest
    assert first.event_inventory_digest != second.event_inventory_digest
    assert (first.source_count, first.source_body_bytes) == (2, 2 * SOURCE_BODY_BYTES)
    assert first.source_receipt_count == 2
    assert first.graph_row_counts == {
        "runtime_tasks": 1, "runtime_execution_nodes": 3, "runtime_execution_edges": 2,
        "runtime_solver_runs": 1, "runtime_solver_nodes": 9, "runtime_solver_edges": 2,
        "runtime_overlay_versions": 1,
    }
    assert sum(first.graph_row_counts.values()) == 19
    assert first.runtime_event_count == 25
    assert first.checkpoint_digest is None
    assert first.checkpoint_tail_count == 0
    assert first.qualification_blockers


def test_fresh_default_qualification_refuses_legacy_installed_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tests.support.reference_capacity_fixture.PARTITION_SCHEMA_VERSION", 7)
    with pytest.raises(ReferenceFixtureError, match="fresh default-v8"):
        _prepare(tmp_path / "fixture", "balanced", (_TASK,), require_fresh_v8=True)
    assert not (tmp_path / "fixture").exists()


def test_solver_edge_owner_refuses_an_endpoint_outside_the_run(tmp_path: Path) -> None:
    root = tmp_path / "fixture"
    _prepare(root, "balanced", (_TASK,))
    with StorageAdministrationService(root) as service:
        before = service.acquire_verified_snapshot()
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            row = connection.execute("SELECT record_json FROM runtime_solver_edges ORDER BY edge_id").fetchone()
        edge = SolverEdge.model_validate_json(row["record_json"])
        cross_scope = edge.model_copy(update={"id": "cross-scope", "dst": "foreign:node"})
        with pytest.raises(RuntimeStateError, match="endpoints must belong"):
            publish_runtime_change(service, lambda connection, repo: repo.apply_solver_edge(
                connection, solver_id=_TASK.solver_id, edge=cross_scope,
            ))
        assert service.acquire_verified_snapshot() == before


@pytest.mark.parametrize("raw_payloads", [False, True], ids=["default-format", "staged-raw-format"])
def test_full_fixture_seals_boundary_and_replays_exact_single_event_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw_payloads: bool,
) -> None:
    monkeypatch.setattr("tests.support.reference_capacity_fixture.EVENT_COUNT", 29)
    monkeypatch.setattr("tests.support.reference_capacity_fixture.CHECKPOINT_TAIL_COUNT", 2)
    expected_mandatory = 26 if raw_payloads else 25
    if raw_payloads:
        monkeypatch.setattr("memorii.stores.sqlite.partition.PARTITION_SCHEMA_VERSION", 7)

    def planned_fill(mandatory_count: int) -> list[EventFillInput]:
        assert mandatory_count == expected_mandatory
        return [
            EventFillInput(
                ordinal=ordinal, task_id=_TASK.task_id, timestamp=FIXTURE_START + timedelta(seconds=ordinal),
                kind="status_update", checkpoint_tail=ordinal >= 27,
            ) for ordinal in range(mandatory_count, 29)
        ]

    root = tmp_path / "fixture"
    audit = _prepare(root, "balanced", (_TASK,), fill=planned_fill, raw_payloads=raw_payloads)
    assert audit.runtime_event_count == 29
    assert audit.runtime_event_batch_count == 8
    assert audit.runtime_operation_counts["runtime_execution_nodes/execution/node/update"] == 29 - expected_mandatory
    assert audit.checkpoint_digest
    assert audit.checkpoint_tail_count == 2
    assert "runtime_checkpoints" not in audit.graph_row_counts
    assert audit.source_receipt_count == 2
    assert audit.partition_schema_version == (RAW_MEMORY_PAYLOAD_SCHEMA_VERSION if raw_payloads else PARTITION_SCHEMA_VERSION)
    with StorageAdministrationService(root) as service, pytest.raises(ReferenceFixtureError, match="expected reference partition"):
        _audit(
            service, "balanced", (_TASK,), expected_events=29, expected_tail=2,
            expected_schema=7,
        )


def test_qualification_preflight_exposes_missing_owner_paths_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "never-created"
    assert main(["--distribution", "balanced", "--installation-root", str(root), "--require-qualified"]) == 2
    assert not root.exists()
    assert json.loads(capsys.readouterr().err) == {
        "status": "unavailable",
        "blockers": ["timed_reference_workload_not_measured"],
    }
