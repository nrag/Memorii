"""Installation administration contract: init, signed publication, recovery, verification."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence import contracts
from memorii.core.persistence.contracts import (
    BatchPosition,
    GenesisPosition,
    InstallationControlState,
    MaterializationCatalogEntry,
    PartitionRevisionVector,
    RuntimeMaterializationManifest,
    RuntimePublicationIntent,
)
from memorii.core.persistence.key_owner import LocalSigningKeyOwner
from memorii.core.storage_administration.service import (
    InitializationNotPossibleError,
    InstallationIntegrityError,
    InstallationQuarantinedError,
    StorageAdministrationError,
    StorageAdministrationService,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.stores.sqlite.control import (
    ControlDatabase,
    ControlJournalChainError,
    ControlStateError,
)


def _record(memory_id: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text=f"publication:{memory_id}",
        status=CommitStatus.COMMITTED,
        source_kind="administration_contract",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _state(revision: int = 1) -> InstallationControlState:
    return InstallationControlState(
        installation_id="installation",
        format_version=1,
        control_revision=revision,
        eligibility_epoch=1,
    )


# --- contracts ---------------------------------------------------------


def test_batch_position_rejects_zero_sequence_and_unknown_fields() -> None:
    with pytest.raises(ValueError):
        BatchPosition(sequence=0, digest="0" * 64)
    with pytest.raises(ValueError):
        BatchPosition.model_validate(
            {"kind": "batch", "sequence": 1, "digest": "0" * 64, "extra": True}
        )


def test_genesis_position_has_no_numeric_event_position() -> None:
    genesis = GenesisPosition()
    assert "sequence" not in genesis.model_dump()


def test_manifest_rejects_duplicate_and_unordered_catalogs() -> None:
    entry = MaterializationCatalogEntry(
        catalog="memory_batches", row_count=0, digest="1" * 64
    )
    with pytest.raises(ValueError):
        RuntimeMaterializationManifest(catalogs=(entry, entry))
    other = MaterializationCatalogEntry(catalog="alpha", row_count=0, digest="2" * 64)
    with pytest.raises(ValueError):
        RuntimeMaterializationManifest(catalogs=(entry, other))


def test_canonical_digest_is_deterministic_and_order_independent() -> None:
    first = contracts.canonical_json_digest({"a": "1", "b": "2"})
    second = contracts.canonical_json_digest({"b": "2", "a": "1"})
    assert first == second
    assert contracts.canonical_json_digest({"a": "1"}) != first


# --- key owner ---------------------------------------------------------


def test_key_owner_signs_and_verifies_with_domain_separation(tmp_path: Path) -> None:
    owner = LocalSigningKeyOwner(tmp_path / "keys")
    owner.create_key("installation-control")
    signature = owner.sign(
        "installation-control",
        contracts.RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
        "message",
    )
    assert owner.verify(
        "installation-control",
        contracts.RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
        "message",
        signature,
    )
    assert not owner.verify(
        "installation-control",
        contracts.RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
        "tampered",
        signature,
    )
    with pytest.raises(ValueError):
        owner.sign("installation-control", "memorii.unknown-purpose.v9", "message")


def test_key_owner_rejects_world_readable_keys(tmp_path: Path) -> None:
    owner = LocalSigningKeyOwner(tmp_path / "keys")
    owner.create_key("installation-control")
    (tmp_path / "keys" / "installation-control.key").chmod(0o644)
    fresh_handle = LocalSigningKeyOwner(tmp_path / "keys")
    with pytest.raises(PermissionError):
        fresh_handle.sign(
            "installation-control",
            contracts.RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
            "message",
        )


# --- control database --------------------------------------------------


def _journal(control: ControlDatabase, operation: str) -> object:
    from memorii.core.persistence.contracts import InstallationControlJournalEntry

    revision, prior = control.next_journal_position()
    unsigned = InstallationControlJournalEntry(
        revision=revision,
        prior_digest=prior,
        operation=operation,  # type: ignore[arg-type]
        entry_digest="0" * 64,
        signer_key_id="installation-control",
        signature="0",
    )
    digest = contracts.canonical_json_digest(unsigned.unsigned_payload())
    return unsigned.model_copy(
        update={"entry_digest": digest, "signature": "sig:" + digest}
    )


def test_control_journal_rejects_chain_breaks(tmp_path: Path) -> None:
    control = ControlDatabase(tmp_path / "control.sqlite3")
    try:
        valid = _journal(control, "initialize")
        control.write_control_state(_state(), valid)
        next_valid = _journal(control, "publication_prepared")
        forged = next_valid.model_copy(update={"prior_digest": "f" * 64})
        with pytest.raises(ControlJournalChainError):
            control.write_control_state(_state(2), forged)
        with pytest.raises(ControlJournalChainError):
            control.write_control_state(
                _state(2), next_valid.model_copy(update={"prior_digest": "0" * 64})
            )
        control.write_control_state(_state(2), next_valid)
    finally:
        control.close()


def test_control_state_rejects_revision_skips(tmp_path: Path) -> None:
    control = ControlDatabase(tmp_path / "control.sqlite3")
    try:
        control.write_control_state(_state(1), _journal(control, "initialize"))
        with pytest.raises(ControlStateError):
            control.write_control_state(_state(3), _journal(control, "mode_changed"))
    finally:
        control.close()


# --- installation service ----------------------------------------------


def test_initialize_publishes_genesis_and_returns_stable_receipt(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        receipt = service.initialize()
        assert receipt.data_generation_id
        snapshot = service.acquire_verified_snapshot()
        assert snapshot.ordinal == 0
        assert snapshot.vector == PartitionRevisionVector.genesis()
    with StorageAdministrationService(root) as reopened:
        duplicate = reopened.initialize()
        assert duplicate.receipt_digest == receipt.receipt_digest


def test_initialize_rejects_foreign_root_content(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    root.mkdir()
    (root / "stranger-file").write_text("foreign", encoding="utf-8")
    with StorageAdministrationService(root) as service, pytest.raises(
        InitializationNotPossibleError
    ):
        service.initialize()


def test_publish_batches_advance_signed_publication(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        store = service.memory_plane_store()
        outcome = service.publish_memory_plane_batch((_record("mem:one"),), store=store)
        assert (outcome.ordinal, outcome.data_revision, outcome.write_revision) == (1, 1, 1)
        second = service.publish_memory_plane_batch((_record("mem:two"),), store=store)
        assert second.ordinal == 2
        snapshot = service.acquire_verified_snapshot()
        assert snapshot.ordinal == 2
        assert snapshot.vector.memory_data_revision == 2
        assert [r.memory_id for r in store.list_records()] == ["mem:one", "mem:two"]


def test_recovery_after_intent_without_commit_aborts_to_old_state(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        store = service.memory_plane_store()
        service.publish_memory_plane_batch((_record("mem:one"),), store=store)
        finalized_digest = service.acquire_verified_snapshot().tuple_digest
        _stage_publication(service, store, (_record("mem:lost"),), commit=False)
        resolution = service.resolve_pending_publication()
        assert resolution.disposition == "aborted"
        assert resolution.tuple_digest == finalized_digest
        assert store.get_record("mem:lost") is None
        assert service.publish_memory_plane_batch(
            (_record("mem:two"),), store=store
        ).ordinal == 2


def test_recovery_after_commit_without_finalize_finalizes_new_state(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        store = service.memory_plane_store()
        service.publish_memory_plane_batch((_record("mem:one"),), store=store)
        staged_digest = _stage_publication(
            service, store, (_record("mem:kept"),), commit=True
        )
        resolution = service.resolve_pending_publication()
        assert resolution.disposition == "finalized"
        assert resolution.tuple_digest == staged_digest
        snapshot = service.acquire_verified_snapshot()
        assert snapshot.ordinal == 2
        assert store.get_record("mem:kept") is not None


def test_row_tampering_with_preserved_head_quarantines(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        service.publish_memory_plane_batch(
            (_record("mem:one"),), store=service.memory_plane_store()
        )
    connection = sqlite3.connect(root / "partition" / "partition.sqlite3")
    try:
        connection.execute(
            "UPDATE memory_current_records SET record_json = '{\"tampered\": true}'"
            " WHERE memory_id = 'mem:one'"
        )
        connection.commit()
    finally:
        connection.close()
    with StorageAdministrationService(root) as fresh_service:
        with pytest.raises(InstallationIntegrityError):
            fresh_service.acquire_verified_snapshot()
        with pytest.raises(InstallationQuarantinedError):
            fresh_service.publish_memory_plane_batch(
                (_record("mem:two"),), store=fresh_service.memory_plane_store()
            )


def test_tampered_control_journal_rejects_service_use(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
    connection = sqlite3.connect(root / "control" / "control.sqlite3")
    try:
        row = connection.execute(
            "SELECT entry_json FROM control_journal ORDER BY revision DESC LIMIT 1"
        ).fetchone()
        payload = json.loads(row[0])
        payload["after_digest"] = "f" * 64
        connection.execute(
            "UPDATE control_journal SET entry_json = ?"
            " WHERE revision = (SELECT MAX(revision) FROM control_journal)",
            (json.dumps(payload),),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(StorageAdministrationError), StorageAdministrationService(root):
        pass


def _stage_publication(
    service: StorageAdministrationService,
    store: SqliteMemoryPlaneStore,
    records: tuple[CanonicalMemoryRecord, ...],
    *,
    commit: bool,
) -> str:
    """Drive the protocol to a crash boundary: intent durable, commit optional."""
    from memorii.core.storage_administration.service import (
        _position_digest,
        _position_sequence,
    )

    state = service._require_operational()
    finalized = service._control.read_publication_state(service._repository_id())
    assert finalized is not None
    partition = service.partition()
    with partition.manual_write_transaction() as handle:
        connection = handle.connection
        store.apply_batch_in_transaction(connection, records, expected_revision=None)
        candidate = service._candidate_from_transaction(
            connection,
            generation_id=finalized.data_generation_id,
            epoch=state.eligibility_epoch,
        )
        partition.write_publication_row(
            connection,
            ordinal=candidate.vector.partition_ordinal,
            position_kind="batch",
            position_sequence=_position_sequence(candidate),
            position_digest=_position_digest(candidate),
            tuple_digest=candidate.payload_digest(),
            generation_id=finalized.data_generation_id,
            vector_json=candidate.vector.model_dump_json(),
            manifest_digest=candidate.manifest_digest,
        )
        intent = RuntimePublicationIntent(
            intent_id=uuid.uuid4().hex,
            repository_id=service._repository_id(),
            expected_old_discriminator=finalized.payload_digest(),
            candidate_state=candidate,
            operation_binding="memory_plane_batch",
            authority_epoch=state.eligibility_epoch,
            fence_token=finalized.vector.partition_ordinal + 1,
        )
        service._control.write_intent(
            intent,
            service._journal_entry(
                operation="publication_prepared",
                before_digest=finalized.payload_digest(),
                after_digest=candidate.payload_digest(),
            ),
        )
        if commit:
            handle.commit()
    return candidate.payload_digest()
