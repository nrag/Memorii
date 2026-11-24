"""Signed partition compatibility and immutable consolidation rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from memorii.core.consolidation.runtime_outputs import (
    ConsolidationOrigin,
    ConsolidationResult,
    EpisodicSummary,
    build_consolidation_result,
)
from memorii.core.persistence.runtime_repository import (
    RuntimeStateError,
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import InstallationIntegrityError, StorageAdministrationService
from memorii.stores.sqlite import partition as sqlite_partition
from memorii.stores.sqlite.partition import PartitionDataRepository


def _result(service: StorageAdministrationService, summary: str = "Sealed result") -> ConsolidationResult:
    with service.partition().transaction(write=False) as connection:
        publication = service.partition().read_publication_row(connection)
        assert publication is not None
    return build_consolidation_result(
        ConsolidationOrigin(
            installation_id=service._control_state().installation_id,
            partition_id=service._repository_id(),
            operation_generation=publication["generation_id"],
            task_id="task",
            client_namespace="client",
            operation_id="operation",
            request_digest="1" * 64,
        ),
        origin_revision=1,
        outputs=(EpisodicSummary(summary=summary),),
    )


def test_consolidation_catalog_reopens_signed_and_refuses_divergent_retry(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    service = StorageAdministrationService(root)
    try:
        service.initialize()
        result = _result(service)
        publish_runtime_change(service, lambda connection, repo: repo.apply_consolidation_result(connection, result))
    finally:
        service.close()

    service = StorageAdministrationService(root)
    try:
        signed = service.acquire_verified_snapshot()
        repository = RuntimeStateRepository(service.partition())
        assert repository.get_consolidation_result(result.result_id) == result
        with service.partition().transaction(write=False) as connection:
            entries = service.partition().compute_materialization_manifest(connection)
            assert next(entry.row_count for entry in entries if entry.catalog == "consolidation_results") == 1

        divergent = _result(service, "Different")
        assert divergent.result_id == result.result_id
        with pytest.raises(RuntimeStateError, match="divergent consolidation"):
            publish_runtime_change(
                service, lambda connection, repo: repo.apply_consolidation_result(connection, divergent)
            )
        assert service.acquire_verified_snapshot() == signed

        publish_runtime_change(service, lambda connection, repo: repo.apply_consolidation_result(connection, result))
        with service.partition().transaction(write=False) as connection:
            assert repository.list_consolidation_results_in(connection) == (result,)
        database_path = service.partition().database_path
    finally:
        service.close()

    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM consolidation_results")
    service = StorageAdministrationService(root)
    try:
        with pytest.raises(InstallationIntegrityError, match="materialization manifest"):
            service.acquire_verified_snapshot()
    finally:
        service.close()


def test_signed_initial_partition_retains_its_manifest_and_rejects_live_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "installation"
    with monkeypatch.context() as legacy:
        legacy.setattr(sqlite_partition, "PARTITION_SCHEMA_VERSION", 1)
        service = StorageAdministrationService(root)
        try:
            service.initialize()
            original = service.acquire_verified_snapshot()
        finally:
            service.close()

    service = StorageAdministrationService(root)
    try:
        assert service.acquire_verified_snapshot() == original
        result = _result(service)
        with pytest.raises(sqlite3.DatabaseError, match="upgrade required"):
            publish_runtime_change(service, lambda connection, repo: repo.apply_consolidation_result(connection, result))
        partition = service.partition()
        with (
            pytest.raises(sqlite3.DatabaseError, match="unpublished staging"),
            partition.transaction(write=True) as connection,
        ):
            partition.stage_consolidation_schema_upgrade(connection)
        assert service.acquire_verified_snapshot() == original
        with partition.transaction(write=False) as connection:
            initial_entries = partition.compute_materialization_manifest(connection)
    finally:
        service.close()

    with monkeypatch.context() as legacy:
        legacy.setattr(sqlite_partition, "PARTITION_SCHEMA_VERSION", 1)
        staged = PartitionDataRepository(tmp_path / "staged" / "partition.sqlite3")
    with staged:
        with staged.transaction(write=True) as connection:
            staged.stage_consolidation_schema_upgrade(connection)
            entries = staged.compute_materialization_manifest(connection)
            assert staged.read_schema_version(connection) == 2
        assert tuple(entry for entry in entries if entry.catalog != "consolidation_results") == initial_entries
        assert next(entry.row_count for entry in entries if entry.catalog == "consolidation_results") == 0


def test_schema_marker_cannot_hide_a_versioned_catalog(tmp_path: Path) -> None:
    with (
        PartitionDataRepository(tmp_path / "partition.sqlite3") as partition,
        pytest.raises(sqlite3.DatabaseError, match="outside the declared"),
        partition.transaction(write=True) as connection,
    ):
        connection.execute("UPDATE partition_schema SET value = '1' WHERE key = 'schema_version'")
        partition.compute_materialization_manifest(connection)
