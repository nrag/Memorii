"""Proof of incremental signed publication and independent rebuild parity."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.runtime_contracts import TaskRecord
from memorii.core.persistence.runtime_repository import publish_runtime_change
from memorii.core.storage_administration.service import InstallationIntegrityError, StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain


def _record(identity: str, payload: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=identity, domain=MemoryDomain.TRANSCRIPT, text=payload, status=CommitStatus.COMMITTED,
    )


def _task(identity: str) -> TaskRecord:
    return TaskRecord(
        task_id=identity, root_execution_node_id=f"root:{identity}", goal="Verify signed publication",
        principal="owner", created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_runtime_and_memory_publication_fold_precise_changes_without_full_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with StorageAdministrationService(tmp_path) as service:
        service.initialize()
        service.acquire_verified_snapshot()
        partition = service.partition()

        def reject_scan(_connection: sqlite3.Connection) -> None:
            pytest.fail("warm writer rebuilt the catalog")

        with monkeypatch.context() as guarded:
            guarded.setattr(partition, "rebuild_manifest_accumulator", reject_scan)
            for index in range(3):
                service.publish_memory_plane_batch((_record(f"source:{index}", "retained" * 1000),))
                publish_runtime_change(
                    service, lambda connection, repository, index=index: repository.apply_task(
                        connection, _task(f"task:{index}"),
                    ),
                )
            expected = service.acquire_verified_snapshot()
        with partition.transaction(write=False) as connection:
            from memorii.core.persistence.contracts import RuntimeMaterializationManifest

            assert RuntimeMaterializationManifest(
                catalogs=partition.compute_materialization_manifest(connection),
            ).digest() == expected.manifest_digest
    with StorageAdministrationService(tmp_path) as reopened:
        assert reopened.acquire_verified_snapshot() == expected


@pytest.mark.parametrize("owner", ["runtime", "memory"])
def test_write_begin_rechecks_cache_after_an_unfenced_external_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner: str,
) -> None:
    with StorageAdministrationService(tmp_path) as service:
        service.initialize()
        service.publish_memory_plane_batch((_record("source:seed", "original"),))
        partition = service.partition()
        original = partition.manual_write_transaction
        original_state = service._control.read_publication_state(service._repository_id())

        @contextmanager
        def change_between_acquire_and_write():
            with closing(sqlite3.connect(partition.database_path)) as external:
                external.execute("UPDATE memory_current_records SET source_kind = 'foreign' WHERE memory_id = 'source:seed'")
                external.commit()
            with original() as transaction:
                yield transaction

        monkeypatch.setattr(partition, "manual_write_transaction", change_between_acquire_and_write)
        with pytest.raises(InstallationIntegrityError, match="base changed before publication"):
            if owner == "runtime":
                publish_runtime_change(
                    service, lambda connection, repository: repository.apply_task(connection, _task("task:rejected")),
                )
            else:
                service.publish_memory_plane_batch((_record("source:rejected", "new"),))
        assert service._control.read_publication_state(service._repository_id()) == original_state
        assert service._control.read_pending_intent(service._repository_id()) is None


def test_tracker_honors_savepoint_rollback_and_replace_secondary_unique_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.stores.sqlite.materialization_sql import capture_manifest_changes
    from memorii.stores.sqlite.partition import LEGACY_RUNTIME_UPGRADE_SCHEMA_VERSION, PartitionDataRepository

    # This SQL fixture exercises the retained inline-record projection.
    monkeypatch.setattr("memorii.stores.sqlite.partition.PARTITION_SCHEMA_VERSION", LEGACY_RUNTIME_UPGRADE_SCHEMA_VERSION)
    with PartitionDataRepository(tmp_path / "data.sqlite3") as partition, partition.transaction(write=True) as connection:
        connection.execute(
            "INSERT INTO memory_current_records VALUES ('first', '{}', 'committed', 'transcript', 'raw', 1)",
        )
        base = partition.rebuild_manifest_accumulator(connection)
        assert base is not None
        with capture_manifest_changes(connection, base) as capture:
            connection.execute("SAVEPOINT transient")
            connection.execute("DELETE FROM memory_current_records WHERE memory_id = 'first'")
            connection.execute("ROLLBACK TO transient")
            connection.execute("RELEASE transient")
            connection.execute(
                "INSERT OR REPLACE INTO memory_current_records VALUES ('next', '{}', 'committed', 'transcript', 'raw', 1)",
            )
        assert capture.result is not None
        assert capture.result.manifest == partition.rebuild_manifest_accumulator(connection).manifest
        assert [row[0] for row in connection.execute("SELECT memory_id FROM memory_current_records")] == ["next"]
