"""Installed runtime history remains complete across publication and recovery."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.runtime_contracts import HypothesisContent, SolverRunRecord, TaskRecord
from memorii.core.persistence.runtime_journal import RuntimeJournalError
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.service import InstallationIntegrityError, StorageAdministrationService
from memorii.domain.enums import CommitStatus, ExecutionNodeStatus, ExecutionNodeType, MemoryDomain
from memorii.domain.execution_graph.nodes import ExecutionNode
from pydantic import ValidationError

_NOW = datetime(2026, 10, 10, tzinfo=UTC)
_TASK = TaskRecord(
    task_id="task:journal", principal="host", goal="Persist graph", created_at=_NOW,
    root_execution_node_id="node:root",
)
_ROOT = ExecutionNode(
    id="node:root", type=ExecutionNodeType.MISSION, title="Root", description="Test the graph",
    status=ExecutionNodeStatus.READY, created_at=_NOW, updated_at=_NOW,
)
_SOLVER = SolverRunRecord(
    solver_id="solver:journal", task_id=_TASK.task_id, parent_execution_node_id=_ROOT.id,
    category="diagnostic", created_by="host",
)
_HYPOTHESIS = HypothesisContent(statement="Captured evidence made retry safe", strength=0.8)


def _seed_graph(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
    repository.apply_task(connection, _TASK)
    repository.apply_execution_node(connection, task_id=_TASK.task_id, node_id=_ROOT.id, node_json=_ROOT.model_dump_json())
    repository.apply_solver_run(connection, _SOLVER)
    repository.apply_solver_node(
        connection, solver_id=_SOLVER.solver_id, node_id="node:hypothesis",
        content=_HYPOTHESIS, metadata_json="{}",
    )


def test_reopen_replays_execution_and_solver_after_memory_write(tmp_path: Path) -> None:
    installation_root = tmp_path / "installation"
    with StorageAdministrationService(installation_root) as service:
        service.initialize()
        publish_runtime_change(service, _seed_graph)
        first = service.acquire_verified_snapshot()
        service.publish_memory_plane_batch((CanonicalMemoryRecord(
            memory_id="memory:journal", domain=MemoryDomain.TRANSCRIPT, text="Other domain",
            status=CommitStatus.COMMITTED,
        ),))
        after_memory = service.acquire_verified_snapshot()
        assert after_memory.vector.runtime_position == first.vector.runtime_position
        assert after_memory.vector.memory_data_revision == 1
        updated_root = _ROOT.model_copy(update={"status": ExecutionNodeStatus.DONE})
        publish_runtime_change(
            service, lambda connection, repo: repo.apply_execution_node(
                connection, task_id=_TASK.task_id, node_id=_ROOT.id, node_json=updated_root.model_dump_json(),
            ),
        )
        final = service.acquire_verified_snapshot()
        assert final.vector.runtime_position.kind == "batch"
        assert final.vector.runtime_position.sequence == 2
        assert final.vector.memory_data_revision == after_memory.vector.memory_data_revision

    with StorageAdministrationService(installation_root) as service:
        assert service.acquire_verified_snapshot() == final
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            replay: dict[tuple[str, tuple[str, ...]], str] = {}
            for row in connection.execute("SELECT record_json FROM runtime_event_batches ORDER BY sequence"):
                batch = json.loads(row["record_json"])
                for event in batch["batch"]["events"]:
                    entity = event["entity"]
                    replay[entity["catalog"], tuple(entity["key"])] = entity["owner_record_json"]
            assert replay["runtime_execution_nodes", (_TASK.task_id, _ROOT.id)] == updated_root.model_dump_json()
            assert json.loads(replay["runtime_solver_nodes", (_SOLVER.solver_id, "node:hypothesis")])[
                "content"
            ] == _HYPOTHESIS.model_dump(mode="json")
            for table in ("runtime_event_id_bindings", "runtime_dedupe_bindings", "runtime_record_version_bindings"):
                assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 5


def test_divergent_historical_record_version_rolls_back_signed_publication(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        publish_runtime_change(service, _seed_graph)
        next_task = _TASK.model_copy(update={"version": 2, "goal": "Latest goal"})
        publish_runtime_change(service, lambda connection, repo: repo.apply_task(connection, next_task))
        before = service.acquire_verified_snapshot()
        invalid_task = _TASK.model_copy(update={"goal": "Changed historical value"})
        with pytest.raises(RuntimeJournalError, match="memory_integrity_conflict"):
            publish_runtime_change(service, lambda connection, repo: repo.apply_task(connection, invalid_task))
        assert service.acquire_verified_snapshot() == before
        assert RuntimeStateRepository(service.partition()).get_task(_TASK.task_id) == next_task


def test_runtime_journal_validates_the_owner_graph_schema_before_publication(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        before = service.acquire_verified_snapshot()
        with pytest.raises(ValidationError, match="identity differs"):
            publish_runtime_change(service, lambda connection, repository: repository.apply_execution_node(
                connection, task_id=_TASK.task_id, node_id="node:other", node_json=_ROOT.model_dump_json(),
            ))
        assert service.acquire_verified_snapshot() == before


def test_runtime_revision_is_covered_by_the_signed_history(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        publish_runtime_change(service, _seed_graph)
        before = service.acquire_verified_snapshot()
        assert publish_runtime_change(service, lambda _connection, _repository: None) == 1
        assert service.acquire_verified_snapshot() == before
        with service.partition().transaction(write=True) as connection:
            service.partition().bump_runtime_revision(connection)
        with pytest.raises(InstallationIntegrityError, match="signed tuple"):
            service.acquire_verified_snapshot()


def test_shared_partition_out_of_publication_write_invalidates_cached_snapshot(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        publish_runtime_change(service, _seed_graph)
        service.acquire_verified_snapshot()
        service.memory_plane_store().apply_batch((CanonicalMemoryRecord(
            memory_id="memory:unpublished", domain=MemoryDomain.TRANSCRIPT, text="Unpublished",
            status=CommitStatus.COMMITTED,
        ),), expected_revision=None)
        with pytest.raises(InstallationIntegrityError, match="signed tuple"):
            service.acquire_verified_snapshot()


@pytest.mark.parametrize("cut", ["after_prepare", "after_data_commit", "tampered_after_data_commit"])
def test_recovery_reconciles_signed_batches_before_control_finalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cut: str,
) -> None:
    installation_root = tmp_path / "installation"
    with StorageAdministrationService(installation_root) as service:
        service.initialize()
        publish_runtime_change(service, _seed_graph)
        before = service.acquire_verified_snapshot()
        db_path = service.partition().database_path
        updated = _TASK.model_copy(update={"version": 2, "goal": "Recovered revision"})

        def interrupt_before_finalize(*_args: object) -> None:
            raise RuntimeError("interrupt finalization")

        write_intent = service._control.write_intent

        def interrupt_after_prepare(*args) -> None:
            write_intent(*args)
            raise RuntimeError("interrupt finalization")

        if cut == "after_prepare":
            monkeypatch.setattr(service._control, "write_intent", interrupt_after_prepare)
        else:
            monkeypatch.setattr(service, "_finalize_publication", interrupt_before_finalize)
        with pytest.raises(RuntimeError, match="interrupt finalization"):
            publish_runtime_change(service, lambda connection, repo: repo.apply_task(connection, updated))

    if cut == "tampered_after_data_commit":
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE runtime_event_batches SET record_json=json_set(record_json, '$.runtime_revision', 999)"
                " WHERE sequence = 1"
            )
    with StorageAdministrationService(installation_root) as recovered:
        resolution = recovered.resolve_pending_publication()
        repository = RuntimeStateRepository(recovered.partition())
        if cut == "after_prepare":
            assert resolution.disposition == "aborted"
            assert recovered.acquire_verified_snapshot() == before
            assert repository.get_task(_TASK.task_id) == _TASK
        elif cut == "after_data_commit":
            assert resolution.disposition == "finalized"
            assert recovered.acquire_verified_snapshot().ordinal == before.ordinal + 1
            assert repository.get_task(_TASK.task_id) == updated
        else:
            assert resolution.disposition == "quarantined"
            finalized = recovered._control.read_publication_state(recovered._repository_id())
            assert finalized is not None
            assert finalized.payload_digest() == before.tuple_digest


@pytest.mark.parametrize("schema_version", [1, 2, 3])
def test_older_signed_partitions_reopen_without_synthetic_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema_version: int,
) -> None:
    installation_root = tmp_path / "installation"
    with monkeypatch.context() as format_fixture:
        format_fixture.setattr("memorii.stores.sqlite.partition.PARTITION_SCHEMA_VERSION", schema_version)
        with StorageAdministrationService(installation_root) as service:
            service.initialize()
            publish_runtime_change(service, _seed_graph)
            before = service.acquire_verified_snapshot()
    with StorageAdministrationService(installation_root) as service:
        assert service.acquire_verified_snapshot() == before
        assert RuntimeStateRepository(service.partition()).get_task(_TASK.task_id) == _TASK
        with service.partition().transaction(write=False) as connection:
            assert service.partition().read_schema_version(connection) == schema_version
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'runtime_event_batches'"
            ).fetchone() is None
