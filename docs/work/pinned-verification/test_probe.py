"""Check pinned-snapshot acquisition on small signed synthetic fixtures."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from memorii.core.persistence.contracts import RuntimePublicationState
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import (
    InstallationIntegrityError,
    StorageAdministrationError,
)
from memorii.stores.sqlite.partition import PartitionDataRepository, VerificationCookie
from probe import ObservedService, pinned_acquisition
from tests.support.reference_capacity import TaskAllocation
from tests.support.reference_capacity_fixture import _prepare


@pytest.fixture
def installation(tmp_path: Path) -> Path:
    root = tmp_path / "installation"
    _prepare(root, "balanced", (TaskAllocation("balanced", 0, 3, 9, 0, 0, 2),), raw_payloads=True)
    return root


def test_pinned_snapshot_matches_production(installation: Path) -> None:
    with ObservedService(installation) as reader:
        pinned = pinned_acquisition(reader)
        assert reader.stale == 0
        assert pinned == reader.acquire_verified_snapshot()


def test_cached_signer_must_match_current_owner(installation: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with ObservedService(installation) as reader:
        monkeypatch.setattr(reader._signing, "public_key_fingerprint", lambda _key_id: "stale-fingerprint")
        with pytest.raises(InstallationIntegrityError, match="cached signer differs"):
            pinned_acquisition(reader)
        assert not reader.scans


def test_preserved_head_sql_commit_invalidates_verified_pin(
    installation: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with ObservedService(installation) as reader:
        verify = reader._matches_materialization
        path = reader.partition_path()

        def tamper_after_verify(
            connection: sqlite3.Connection, finalized: RuntimePublicationState, *,
            partition: PartitionDataRepository | None = None, cookie: VerificationCookie | None = None,
        ) -> bool:
            exact = verify(connection, finalized, partition=partition, cookie=cookie)
            if not reader.stale:
                assert exact
                with closing(sqlite3.connect(path)) as writer, writer:
                    writer.execute("UPDATE memory_payloads SET body=zeroblob(length(body)) WHERE rowid=1")
            return exact

        monkeypatch.setattr(reader, "_matches_materialization", tamper_after_verify)
        with pytest.raises(InstallationIntegrityError, match="current pinned snapshot failed exact verification"):
            pinned_acquisition(reader)
        assert reader.stale == 1


def test_repeated_external_publication_exhausts_retries(
    installation: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with ObservedService(installation) as reader, ObservedService(installation) as writer:
        verify = reader._matches_materialization
        task_id = TaskAllocation("balanced", 0, 3, 9, 0, 0, 2).task_id

        def write_after_verify(
            connection: sqlite3.Connection, finalized: RuntimePublicationState, *,
            partition: PartitionDataRepository | None = None, cookie: VerificationCookie | None = None,
        ) -> bool:
            exact = verify(connection, finalized, partition=partition, cookie=cookie)
            assert exact

            def advance(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
                task = repository.get_task_in(connection, task_id)
                assert task is not None
                repository.apply_task(connection, task.model_copy(update={"version": task.version + 1}))

            publish_runtime_change(writer, advance)
            return exact

        monkeypatch.setattr(reader, "_matches_materialization", write_after_verify)
        with pytest.raises(StorageAdministrationError, match="changed during all pinned verification attempts"):
            pinned_acquisition(reader)
        assert reader.stale == 3
        assert len(reader.scans) == 3
