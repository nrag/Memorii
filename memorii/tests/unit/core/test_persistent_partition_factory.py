"""Fail-closed managed partition factory and bundle composition."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.filesystem_storage.bundle import FilesystemStorageBundle
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import (
    ManagedPartitionError,
    detect_legacy_memory_plane_layouts,
    open_managed_partition,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain


def _record(memory_id: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text=f"factory:{memory_id}",
        status=CommitStatus.COMMITTED,
        source_kind="partition_factory",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _initialized_root(tmp_path: Path) -> Path:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
    return root


def test_open_managed_partition_serves_verified_partition(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    administration, _memory_plane = open_managed_partition(root)
    try:
        store = SqliteMemoryPlaneStore(administration.partition())
        store.stage_record(_record("mem:one"))
        assert store.revision() == 1
        administration.publish_memory_plane_batch(
            (_record("mem:published"),), store=store
        )
        snapshot = administration.acquire_verified_snapshot()
        assert snapshot.vector.memory_data_revision == 2
    finally:
        administration.close()


def test_uninitialized_root_refuses_without_creating_anything(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with pytest.raises(ManagedPartitionError, match="uninitialized") as excinfo:
        open_managed_partition(root)
    assert excinfo.value.reason == "uninitialized"
    assert not (root / "partition" / "partition.sqlite3").exists()
    assert not (root / "control" / "control.sqlite3").exists()


@pytest.mark.parametrize(
    ("directory", "layout"),
    [("memory-plane", "hermes-host-memory-plane"), ("memory_plane", "filesystem-bundle-memory-plane")],
)
def test_legacy_layout_reports_migration_required_and_never_creates_a_database(
    tmp_path: Path, directory: str, layout: str
) -> None:
    root = tmp_path / "installation"
    root.mkdir()
    (root / directory).mkdir()
    (root / directory / "memory_records.jsonl").write_text("{}", encoding="utf-8")
    assert detect_legacy_memory_plane_layouts(root) == (layout,)
    with pytest.raises(ManagedPartitionError, match="migration_required") as excinfo:
        open_managed_partition(root)
    assert excinfo.value.reason == "migration_required"
    assert not (root / "partition").exists()


def test_mixed_legacy_layouts_are_unsupported_configuration(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    root.mkdir()
    for directory in ("memory-plane", "memory_plane"):
        (root / directory).mkdir()
        (root / directory / "memory_records.jsonl").write_text("{}", encoding="utf-8")
    with pytest.raises(ManagedPartitionError, match="unsupported_configuration") as excinfo:
        open_managed_partition(root)
    assert excinfo.value.reason == "unsupported_configuration"


def test_partition_without_control_is_an_integrity_refusal(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    (root / "partition").mkdir(parents=True)
    (root / "partition" / "partition.sqlite3").write_bytes(b"orphan")
    with pytest.raises(ManagedPartitionError, match="integrity"):
        open_managed_partition(root)


def test_managed_bundle_shares_the_partition_and_writes_no_jsonl(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    administration, _memory_plane = open_managed_partition(root)
    try:
        bundle = FilesystemStorageBundle.from_managed_root(root, administration)
        assert bundle.memory_plane_store.durable
        bundle.memory_plane_store.stage_record(_record("mem:bundle"))
        store = SqliteMemoryPlaneStore(administration.partition())
        assert store.get_record("mem:bundle") is not None
        assert not (root / "memory-plane").exists()
        assert not (root / "memory_plane").exists()
        assert bundle.storage_status() is not None
    finally:
        administration.close()


def test_legacy_bundle_path_is_unchanged(tmp_path: Path) -> None:
    bundle = FilesystemStorageBundle.from_root(tmp_path / "legacy-root")
    assert bundle.memory_plane_store.durable
    assert (tmp_path / "legacy-root" / "memory_plane").exists()
