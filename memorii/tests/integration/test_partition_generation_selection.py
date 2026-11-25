"""Signed generation selection fences repository handles retained across cutover."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.contracts import InstallationControlJournalEntry, RuntimePublicationIntent
from memorii.core.persistence.key_owner import PARTITION_GENERATION_SIGNATURE_PURPOSE
from memorii.core.storage_administration.generation_selection import (
    PARTITION_GENERATION_SELECTOR,
    PartitionGenerationSelector,
)
from memorii.core.storage_administration.service import (
    InstallationIntegrityError,
    StorageAdministrationError,
    StorageAdministrationService,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.stores.sqlite.partition import PartitionDataRepository


def _write_selector(
    service: StorageAdministrationService, generation: str, *, valid_signature: bool = True,
) -> Path:
    state = service._control_state()
    selector = PartitionGenerationSelector(
        installation_id=state.installation_id,
        repository_id=service._repository_id(),
        generation_id=generation,
        signature="0" * 128,
    )
    if valid_signature:
        selector = selector.model_copy(update={"signature": service._signing.sign(
            service._signer_key_id, PARTITION_GENERATION_SIGNATURE_PURPOSE, selector.unsigned_digest(),
        )})
    pointer = service.installation_root / "control" / PARTITION_GENERATION_SELECTOR
    pending = pointer.with_suffix(".tmp")
    pending.write_text(selector.model_dump_json())
    pending.chmod(0o600)
    os.replace(pending, pointer)
    return pointer


def _select_generation(service: StorageAdministrationService, *, generation_id: str = "selected") -> Path:
    """Exercise the reader boundary with an owner-signed finalized generation."""
    previous = service._control.read_publication_state(service._repository_id())
    assert previous is not None
    destination = service.installation_root / "partition" / "generations" / generation_id / "partition.sqlite3"
    destination.parent.mkdir(parents=True)
    legacy = service.partition_path()
    candidate = service._sign_state(previous.model_copy(update={"data_generation_id": generation_id}))
    # Selection and control publication are the test scope's owner-only
    # setup. Live restore requires the separately reviewed intent protocol.
    with service._publication_fence(), locked_file(legacy.with_name(f"{legacy.name}.lock"), exclusive=True):
        with closing(sqlite3.connect(legacy)) as source, closing(sqlite3.connect(destination)) as staged:
            source.backup(staged)
        with PartitionDataRepository(destination, require_existing=True) as stage, stage.transaction(write=True) as connection:
            connection.execute(
                "UPDATE partition_publication SET generation_id = ?, tuple_digest = ? WHERE id = 1",
                (candidate.data_generation_id, candidate.payload_digest()),
            )
        service._control.write_publication_state(
            candidate.repository_id, candidate,
            service._journal_entry(
                operation="publication_finalized", before_digest=previous.payload_digest(),
                after_digest=candidate.payload_digest(),
            ),
        )
        _write_selector(service, candidate.data_generation_id)
    return destination


def test_selected_generation_fences_retained_readers_and_writers(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path) as service:
        service.initialize()
        old = service.partition()
        old_store = service.memory_plane_store()
        secret = old_store.load_or_create_protected_secret(purpose="fixture", length=32)
        destination = _select_generation(service)
        for write in (False, True):
            with pytest.raises(StorageAdministrationError, match="selection changed"), old.transaction(write=write):
                pytest.fail("a retired partition handle opened a transaction")
        with pytest.raises(StorageAdministrationError, match="selection changed"), old.manual_write_transaction():
            pytest.fail("a retired partition handle opened a manual write transaction")
        with StorageAdministrationService(tmp_path) as reopened:
            assert reopened.partition_path() == destination
            assert reopened.acquire_verified_snapshot().ordinal == 0
            assert reopened.memory_plane_store().load_or_create_protected_secret(purpose="fixture", length=32) == secret
            # Once current authority advances, loss of the selector must
            # never make the legacy path an implicit rollback.
            (tmp_path / "control" / PARTITION_GENERATION_SELECTOR).unlink()
            with pytest.raises(StorageAdministrationError, match="selection changed"):
                reopened.acquire_verified_snapshot()
        with (
            StorageAdministrationService(tmp_path) as fallback,
            pytest.raises(InstallationIntegrityError, match="generation"),
        ):
            fallback.acquire_verified_snapshot()


def test_named_acquisition_reuses_manifest_for_write_until_external_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = CanonicalMemoryRecord(
        memory_id="source", domain=MemoryDomain.TRANSCRIPT, text="initial",
        source_kind="fixture", status=CommitStatus.COMMITTED,
    )
    with StorageAdministrationService(tmp_path) as owner:
        owner.initialize()
        owner.publish_memory_plane_batch((source,))
        _select_generation(owner)
    with StorageAdministrationService(tmp_path) as selected:
        acquired = selected.acquire_verified_snapshot()
        partition = selected.partition()

        def reject_scan(_connection: sqlite3.Connection) -> None:
            pytest.fail("publication rebuilt an already verified manifest")

        with monkeypatch.context() as guarded:
            guarded.setattr(partition, "rebuild_manifest_accumulator", reject_scan)
            selected.publish_memory_plane_batch((source.model_copy(update={"text": "updated"}),))
        published = selected.acquire_verified_snapshot()
        assert published.ordinal == acquired.ordinal + 1
        with closing(sqlite3.connect(partition.database_path)) as external, external:
            external.execute("UPDATE memory_current_records SET source_kind = 'foreign' WHERE memory_id = 'source'")
        with pytest.raises(InstallationIntegrityError, match="materializations are not verified"):
            selected.publish_memory_plane_batch((source.model_copy(update={"text": "rejected"}),))
        finalized = selected._control.read_publication_state(selected._repository_id())
        assert finalized is not None
        assert finalized.payload_digest() == published.tuple_digest
        assert selected._control.read_pending_intent(selected._repository_id()) is None


def test_selector_loss_cannot_release_an_older_copy_of_the_same_generation(tmp_path: Path) -> None:
    old_source = CanonicalMemoryRecord(
        memory_id="same-generation-source", domain=MemoryDomain.TRANSCRIPT, text="old fixture",
        source_kind="fixture", status=CommitStatus.COMMITTED,
    )
    with StorageAdministrationService(tmp_path) as service:
        initialized = service.initialize()
        service.publish_memory_plane_batch((old_source,))
        _select_generation(service, generation_id=initialized.data_generation_id)
    with StorageAdministrationService(tmp_path) as selected:
        selected.publish_memory_plane_batch((old_source.model_copy(update={"text": "new fixture"}),))
    (tmp_path / "control" / PARTITION_GENERATION_SELECTOR).unlink()
    with (
        StorageAdministrationService(tmp_path) as fallback,
        pytest.raises(InstallationIntegrityError, match="finalized publication"),
    ):
        fallback.memory_plane_store().get_record(old_source.memory_id)


@pytest.mark.parametrize("failure", ["signature", "wrong_generation", "missing_database", "symlink"])
def test_invalid_generation_selection_fails_closed(tmp_path: Path, failure: str) -> None:
    with StorageAdministrationService(tmp_path) as service:
        initialized = service.initialize()
        generation = initialized.data_generation_id if failure != "wrong_generation" else "foreign"
        pointer = _write_selector(service, generation, valid_signature=failure != "signature")
        if failure == "symlink":
            real_pointer = pointer.with_name("pointed.json")
            pointer.rename(real_pointer)
            pointer.symlink_to(real_pointer)
        with (
            StorageAdministrationService(tmp_path) as reopened,
            pytest.raises(InstallationIntegrityError, match="selector|selection"),
        ):
            reopened.partition()
        assert not (tmp_path / "partition" / "generations").exists()


@pytest.mark.parametrize("publication_cut", ["prepared", "data_committed", "control_committed"])
def test_named_generation_does_not_release_data_before_pending_intent_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, publication_cut: str,
) -> None:
    with StorageAdministrationService(tmp_path) as service:
        service.initialize()
        _select_generation(service)
    with StorageAdministrationService(tmp_path) as owner:
        def lose_response(*_args: object) -> None:
            raise RuntimeError("publication interrupted")

        original_intent_write = owner._control.write_intent

        def interrupt_intent_write(intent: RuntimePublicationIntent, entry: InstallationControlJournalEntry) -> None:
            if publication_cut == "control_committed" and intent.phase == "finalized":
                lose_response()
            original_intent_write(intent, entry)
            if publication_cut == "prepared" and intent.phase == "prepared":
                lose_response()

        with monkeypatch.context() as scoped:
            if publication_cut == "data_committed":
                scoped.setattr(owner, "_finalize_publication", lose_response)
            else:
                scoped.setattr(owner._control, "write_intent", interrupt_intent_write)
            with pytest.raises(RuntimeError, match="publication interrupted"):
                owner.publish_memory_plane_batch((CanonicalMemoryRecord(
                    memory_id="pending-source", domain=MemoryDomain.TRANSCRIPT, text="pending",
                    source_kind="fixture", status=CommitStatus.COMMITTED,
                ),))
    commit_data = publication_cut != "prepared"
    with StorageAdministrationService(tmp_path) as recovered:
        with pytest.raises(InstallationIntegrityError, match="pending publication recovery"):
            recovered.memory_plane_store().get_record("pending-source")
        assert recovered.acquire_verified_snapshot().ordinal == int(commit_data)
        record = recovered.memory_plane_store().get_record("pending-source")
        if commit_data:
            assert record is not None and record.text == "pending"
        else:
            assert record is None
