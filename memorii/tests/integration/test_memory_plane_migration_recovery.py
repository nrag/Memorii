"""Legacy migration journeys: adopt, import, cut over, restart, roll back."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.persistence.factory import select_persistent_memory_plane
from memorii.core.storage_administration.migration import (
    LegacyMigrationError,
    build_migration_plan,
    migrate_legacy_installation,
)
from memorii.domain.enums import CommitStatus, MemoryDomain


def _seed_legacy_installation(root: Path, batches: int = 3) -> Path:
    plane = root / "memory_plane"
    store = JsonlMemoryPlaneStore(plane)
    for index in range(batches):
        store.write_records(
            (
                CanonicalMemoryRecord(
                    memory_id=f"mem:legacy:{index}",
                    domain=MemoryDomain.SEMANTIC,
                    text=f"legacy:{index}",
                    content={"origin": "legacy"},
                    status=CommitStatus.COMMITTED,
                    source_kind="legacy_source",
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            )
        )
    return plane


def _legacy_snapshot(plane: Path) -> tuple[int, int, tuple[str, ...]]:
    store = JsonlMemoryPlaneStore(plane)
    write_revision = store.read_write_snapshot()[0]
    data_revision = store.revision()
    ids = tuple(record.memory_id for record in store.list_records())
    return write_revision, data_revision, ids


def test_migration_preserves_bytes_and_serves_managed_traffic(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    root.mkdir(parents=True)
    plane = _seed_legacy_installation(root)
    legacy_bytes = (plane / "memory_records.jsonl").read_bytes()
    expected = _legacy_snapshot(plane)

    plan = build_migration_plan(root, plane_directory=plane)
    service = migrate_legacy_installation(
        root, plane_directory=plane, approved_plan=plan
    )
    try:
        snapshot = service.acquire_verified_snapshot()
        assert snapshot.vector.memory_write_revision == expected[0]
        assert snapshot.vector.memory_data_revision == expected[1]
        store = SqliteMemoryPlaneStore(service.partition())
        ids = tuple(record.memory_id for record in store.list_records())
        assert ids == expected[2]
    finally:
        service.close()

    # Legacy input untouched; the root now selects managed.
    assert (plane / "memory_records.jsonl").read_bytes() == legacy_bytes
    selection = select_persistent_memory_plane(root)
    assert selection.managed
    try:
        writeback_ids = [
            record.memory_id
            for record in selection.memory_plane._records.list_records()
        ]
        assert writeback_ids == list(expected[2])
    finally:
        selection.administration.close()


def test_migration_refuses_changed_legacy_input(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    root.mkdir(parents=True)
    plane = _seed_legacy_installation(root)
    plan = build_migration_plan(root, plane_directory=plane)
    JsonlMemoryPlaneStore(plane).write_records(
        (
            CanonicalMemoryRecord(
                memory_id="mem:legacy:extra",
                domain=MemoryDomain.SEMANTIC,
                text="extra",
                status=CommitStatus.COMMITTED,
                source_kind="legacy_source",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )
    )
    with pytest.raises(LegacyMigrationError, match="changed since the approved plan"):
        migrate_legacy_installation(root, plane_directory=plane, approved_plan=plan)


_RESTART_PROGRAM = '''
import sys
from pathlib import Path

from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import select_persistent_memory_plane

root = Path(sys.argv[1])
selection = select_persistent_memory_plane(root)
assert selection.managed
try:
    store = SqliteMemoryPlaneStore(selection.administration.partition())
    write_revision = store.read_write_snapshot()[0]
    print(write_revision, len(store.list_records()))
finally:
    selection.administration.close()
'''


def test_migrated_installation_serves_a_fresh_process(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    root.mkdir(parents=True)
    plane = _seed_legacy_installation(root)
    plan = build_migration_plan(root, plane_directory=plane)
    service = migrate_legacy_installation(
        root, plane_directory=plane, approved_plan=plan
    )
    service.close()
    restarted = subprocess.run(
        [sys.executable, "-c", _RESTART_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert restarted.stdout.strip() == "3 3"


def test_repeat_migration_is_idempotent_and_serves(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    root.mkdir(parents=True)
    plane = _seed_legacy_installation(root)
    plan = build_migration_plan(root, plane_directory=plane)
    first = migrate_legacy_installation(root, plane_directory=plane, approved_plan=plan)
    first.close()
    second = migrate_legacy_installation(root, plane_directory=plane, approved_plan=plan)
    try:
        snapshot = second.acquire_verified_snapshot()
        assert snapshot.vector.memory_write_revision == 3
    finally:
        second.close()
