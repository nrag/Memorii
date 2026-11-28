"""Exercise sealed readiness with real SQLite files and macOS custody flags."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import sys
from contextlib import closing
from pathlib import Path

import pytest
from checkpoint_capacity import append_root_update
from measure_sealed_startup import persist_fixture_seal, prepare_fixture
from memorii.core.persistence.contracts import TrustRegistryEntry
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.service import StorageAdministrationService
from sealed_startup import (
    SealedStartupError,
    acquire,
    frozen_fixture,
    image_view,
    issue_seal,
)
from tests.support.reference_capacity import TaskAllocation
from tests.support.reference_capacity_fixture import _prepare

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="uses native macOS file flags")
_VERIFIER = "1" * 64


@pytest.fixture
def staged(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "installation"
    _prepare(root, "balanced", (TaskAllocation("balanced", 0, 3, 9, 0, 0, 2),), raw_payloads=True)
    with StorageAdministrationService(root) as owner:
        task, = RuntimeStateRepository(owner.partition()).list_tasks()
        append_root_update(owner, task, checkpoint=True)
        _, original = owner._active_partition_selection()
        assert original is not None
    path, expected = prepare_fixture(root, original.payload_digest())
    return root, path, expected


def _seal(root: Path, path: Path) -> None:
    with frozen_fixture(root, path):
        witness = issue_seal(root, _VERIFIER)
    persist_fixture_seal(root, witness)


def test_frozen_sqlite_and_hash_read_the_selected_image(
    staged: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, path, expected = staged
    _seal(root, path)
    assert hasattr(stat, "UF_IMMUTABLE")

    def forbid_full_verification(*_args: object, **_kwargs: object) -> None:
        pytest.fail("fast acquisition invoked logical verification")

    def attempt_changes() -> None:
        with pytest.raises(PermissionError):
            path.write_bytes(b"foreign")
        with pytest.raises(PermissionError):
            path.rename(path.with_suffix(".replaced"))
        with pytest.raises(PermissionError):
            path.parent.rename(path.parent.with_name("detached"))

    monkeypatch.setattr(StorageAdministrationService, "_matches_materialization", forbid_full_verification)
    monkeypatch.setattr("sealed_startup._exact_verification", forbid_full_verification)
    with frozen_fixture(root, path), StorageAdministrationService(root) as owner:
        assert acquire(owner, _VERIFIER, before_sqlite=attempt_changes) == (expected, path.stat().st_size)
        with image_view(root, path) as view, view.sqlite_view() as connection:
            assert connection.execute("SELECT tuple_digest FROM partition_publication").fetchone()[0] == expected
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                connection.execute("DELETE FROM partition_publication")


def test_copied_bytes_at_the_same_path_cannot_replace_the_pinned_image(staged: tuple[Path, Path, str]) -> None:
    root, path, _ = staged
    _seal(root, path)
    replacement = root / "replacement.sqlite3"
    shutil.copyfile(path, replacement)

    def replace_after_hash() -> None:
        os.chflags(path.parent, 0)
        os.chflags(path, 0)
        replacement.replace(path)
        os.chflags(path, stat.UF_IMMUTABLE)
        os.chflags(path.parent, stat.UF_IMMUTABLE)

    with (
        frozen_fixture(root, path), StorageAdministrationService(root) as owner,
        pytest.raises(SealedStartupError, match="image identity or custody changed"),
    ):
        acquire(owner, _VERIFIER, before_sqlite=replace_after_hash)


@pytest.mark.parametrize("catalog", [
    "memory_payloads", "runtime_event_batches", "runtime_replay_checkpoints", "runtime_event_id_bindings",
])
def test_preserved_head_tampering_blocks_readiness(staged: tuple[Path, Path, str], catalog: str) -> None:
    root, path, expected = staged
    _seal(root, path)
    with closing(sqlite3.connect(path)) as external:
        with external:
            if catalog == "memory_payloads":
                rowid, = external.execute("SELECT min(rowid) FROM memory_payloads").fetchone()
                with external.blobopen(catalog, "body", rowid) as blob:
                    blob[-1] ^= 1
            elif catalog == "runtime_event_id_bindings":
                external.execute(
                    "UPDATE runtime_event_id_bindings SET binding_json = replace(binding_json, 'event_id', 'event_xx')",
                )
                assert external.total_changes > 0
            else:
                external.execute(f"UPDATE {catalog} SET record_json = ?", ("{}",))
        assert external.execute("SELECT tuple_digest FROM partition_publication").fetchone()[0] == expected
    with (
        frozen_fixture(root, path), StorageAdministrationService(root) as owner,
        pytest.raises(SealedStartupError, match="sealed byte image differs"),
    ):
        acquire(owner, _VERIFIER)


def test_ineligible_seal_and_hidden_wal_deny_readiness(staged: tuple[Path, Path, str]) -> None:
    root, path, _ = staged
    _seal(root, path)
    with (
        frozen_fixture(root, path), StorageAdministrationService(root) as owner,
        pytest.raises(SealedStartupError, match="current authority"),
    ):
        acquire(owner, "2" * 64)
    path.with_name(path.name + "-wal").write_bytes(b"unreviewed WAL")
    with pytest.raises(SealedStartupError, match="side files"), frozen_fixture(root, path):
        pytest.fail("fixture admitted a WAL side file")


def test_corruption_prevents_seal_issuance(staged: tuple[Path, Path, str]) -> None:
    root, path, _ = staged
    with closing(sqlite3.connect(path)) as external, external:
        external.execute("UPDATE memory_payloads SET body = zeroblob(raw_size)")
    with frozen_fixture(root, path), pytest.raises(sqlite3.DatabaseError, match="payload digest differs"):
        issue_seal(root, _VERIFIER)
    assert not (root / "control" / "verified_image.json").exists()


def test_seal_version_must_be_explicit(staged: tuple[Path, Path, str]) -> None:
    root, path, _ = staged
    _seal(root, path)
    seal = root / "control" / "verified_image.json"
    record = json.loads(seal.read_text())
    del record["version"]
    seal.write_text(json.dumps(record))
    with (
        frozen_fixture(root, path), StorageAdministrationService(root) as owner,
        pytest.raises(ValueError, match="version"),
    ):
        acquire(owner, _VERIFIER)


@pytest.mark.parametrize("after_hash", [False, True])
def test_trust_change_denies_sealed_readiness(staged: tuple[Path, Path, str], after_hash: bool) -> None:
    root, path, _ = staged
    _seal(root, path)

    def retire_signer() -> None:
        with StorageAdministrationService(root) as other:
            other._control.install_trust_entry(TrustRegistryEntry(
                key_id=other._signer_key_id,
                public_key_fingerprint=other._signing.public_key_fingerprint(other._signer_key_id),
                purpose="memorii.verified-image.v1",
                sequence_interval_start=1,
                lifecycle="retired",
            ))

    if not after_hash:
        retire_signer()
    with (
        frozen_fixture(root, path), StorageAdministrationService(root) as owner,
        pytest.raises(SealedStartupError, match="trust registry"),
    ):
        acquire(owner, _VERIFIER, before_sqlite=retire_signer if after_hash else None)
