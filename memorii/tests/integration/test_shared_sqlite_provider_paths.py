"""Shared-SQLite provider and inspection paths over the selected partition.

Composition roots select the managed published partition when the
installation is initialized, keep the legacy JSONL plane on pre-cutover
roots, and refuse ambiguous or empty roots instead of guessing.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import (
    ManagedPartitionError,
    select_persistent_memory_plane,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain


def _record(memory_id: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text=f"provider-path:{memory_id}",
        status=CommitStatus.COMMITTED,
        source_kind="shared_sqlite_provider_paths",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _initialized_root(tmp_path: Path) -> Path:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
    return root


def test_provider_on_a_managed_root_serves_the_published_partition(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    provider_service = build_filesystem_provider(root)
    selection = select_persistent_memory_plane(root)
    assert selection.managed
    assert selection.administration is not None
    try:
        selection.memory_plane.conditionally_write_records(
            (_record("mem:provider:one"),), preconditions=()
        )
        store = SqliteMemoryPlaneStore(selection.administration.partition())
        assert store.get_record("mem:provider:one") is not None
        snapshot = selection.administration.acquire_verified_snapshot()
        assert snapshot.vector.memory_write_revision == 1
        assert not (root / "memory-plane").exists()
        assert not (root / "memory_plane").exists()
    finally:
        selection.administration.close()
    del provider_service


def test_provider_on_a_legacy_root_keeps_the_jsonl_plane(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    (root / "memory_plane").mkdir(parents=True)
    (root / "memory_plane" / "memory_records.jsonl").write_text("", encoding="utf-8")
    build_filesystem_provider(root)
    assert (root / "memory_plane" / "memory_records.jsonl").exists()
    assert not (root / "control").exists()


def test_selection_refuses_empty_roots_without_bootstrap(tmp_path: Path) -> None:
    with pytest.raises(ManagedPartitionError, match="uninitialized"):
        select_persistent_memory_plane(tmp_path / "empty")
    assert not (tmp_path / "empty").exists()


def test_selection_refuses_managed_and_legacy_coexistence(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    (root / "memory-plane").mkdir()
    (root / "memory-plane" / "memory_records.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ManagedPartitionError, match="unsupported_configuration"):
        select_persistent_memory_plane(root)


_INSPECTION_PROGRAM = '''
import json
import sys
from pathlib import Path

from memorii.integrations.hermes_local_authority import inspect_local_memory

summary = inspect_local_memory(hermes_home=Path(sys.argv[1]))
print(json.dumps({"write_revision": summary["write_revision"]}))
'''


def test_hermes_inspection_reads_managed_partition_and_never_initializes(
    tmp_path: Path,
) -> None:
    hermes_home = tmp_path / "hermes-home"
    installation_root = hermes_home / "memorii"
    with StorageAdministrationService(installation_root) as service:
        service.initialize()
        service.publish_memory_plane_batch(
            (_record("mem:inspection:one"),), store=service.memory_plane_store()
        )
    inspected = subprocess.run(
        [sys.executable, "-c", _INSPECTION_PROGRAM, str(hermes_home)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert '"write_revision": 1' in inspected.stdout
    # No legacy plane was created by inspection.
    assert not (installation_root / "memory-plane").exists()

    from memorii.integrations.hermes_local_authority import (
        LocalLevel2AuthorityError,
        inspect_local_memory,
    )

    with pytest.raises(LocalLevel2AuthorityError):
        inspect_local_memory(hermes_home=tmp_path / "empty-home")
    assert not (tmp_path / "empty-home" / "memorii" / "memory-plane").exists()


_FRESH_PROCESS_PROVIDER_PROGRAM = '''
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.persistence.factory import select_persistent_memory_plane
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain

root = Path(sys.argv[1])
provider = build_filesystem_provider(root)
selection = select_persistent_memory_plane(root)
assert selection.managed
try:
    selection.memory_plane.conditionally_write_records(
        (
            CanonicalMemoryRecord(
                memory_id="mem:fresh:process",
                domain=MemoryDomain.SEMANTIC,
                text="fresh",
                status=CommitStatus.COMMITTED,
                source_kind="shared_sqlite_provider_paths",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
        preconditions=(),
    )
    print(selection.memory_plane._records.read_write_snapshot()[0])
finally:
    selection.administration.close()
'''


def test_provider_composition_survives_process_restart(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    writer = subprocess.run(
        [sys.executable, "-c", _FRESH_PROCESS_PROVIDER_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert writer.stdout.strip() == "1"
    reader = subprocess.run(
        [sys.executable, "-c", _FRESH_PROCESS_PROVIDER_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert reader.stdout.strip() == "2"
    with StorageAdministrationService(root) as verifier:
        snapshot = verifier.acquire_verified_snapshot()
        assert snapshot.vector.memory_write_revision == 2
        store = SqliteMemoryPlaneStore(verifier.partition())
        assert store.get_record("mem:fresh:process") is not None
