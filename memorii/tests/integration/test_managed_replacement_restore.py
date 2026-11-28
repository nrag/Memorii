"""Restore an older data archive with separately retained current authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry, GrantRegistryError
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.key_owner import INSTALLATION_CONTROL_RECOVERY_SIGNATURE_PURPOSE
from memorii.core.storage_administration import read_grant_recovery, replacement_restore
from memorii.core.storage_administration.operator import (
    InstallationMode,
    ModeChangeRequest,
    OperatorError,
    StorageAdministrationOperator,
    mint_owner_capability,
    require_owner_capability,
)
from memorii.core.storage_administration.operator_backup import (
    BackupRestoreOperator,
    _copy_private_restore_media,
    _open_backup_snapshot,
    _sqlite_backup,
)
from memorii.core.storage_administration.operator_governance import ForgetTargetSelector, GovernanceOperator
from memorii.core.storage_administration.read_grant_recovery import ReadGrantRecoveryOwner
from memorii.core.storage_administration.recovery_authority import (
    IndependentRecoveryCustody,
    InstallationControlRecoveryBundle,
    RecoveryAuthorityError,
    RecoveryBundleMember,
    SealedRecoveryHead,
    sign_recovery_head,
)
from memorii.core.storage_administration.recovery_bundle import open_recovery_bundle, seal_recovery_bundle
from memorii.core.storage_administration.replacement_restore import (
    ReplacementRestorePlan,
    activate_sealed_replacement,
    seal_staged_replacement,
    stage_replacement_restore,
)
from memorii.core.storage_administration.service import (
    REPLACEMENT_RECOVERY_QUARANTINE,
    StorageAdministrationService,
)
from memorii.core.storage_administration.suppression_journal import (
    SuppressionCoordinate,
    SuppressionRecord,
    read_suppression_records,
    write_suppression_record,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.stores.sqlite.private_storage import write_private_file

_DATA_KEY = b"d" * 32
_CONTROL_KEY = b"c" * 32
_OWNER = "owner:replacement-test"


def _set_mode(service: StorageAdministrationService, mode: InstallationMode) -> None:
    StorageAdministrationOperator(service).change_mode(
        ModeChangeRequest(
            target_mode=mode, expected_control_revision=service._control_state().control_revision,
            reason="replacement fixture",
        ),
        capability=mint_owner_capability(service, _OWNER),
    )


def _publish(service: StorageAdministrationService, identity: str) -> None:
    service.publish_memory_plane_batch((CanonicalMemoryRecord(
        memory_id=identity, domain=MemoryDomain.TRANSCRIPT, source_kind="replacement_fixture",
        text=identity, status=CommitStatus.COMMITTED,
    ),))


def _retain_current_authority(service: StorageAdministrationService, custody_root: Path, scratch: Path) -> tuple[
    IndependentRecoveryCustody, InstallationControlRecoveryBundle, bytes,
]:
    custody_root.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    signer_id = service._signer_key_id
    public_key = service._signing.public_key_bytes(signer_id)
    state = service._control_state()
    publication = service._control.read_publication_state(service._repository_id())
    assert publication is not None
    journal = service._control.read_journal()
    control_snapshot = scratch / "control.sqlite3"
    with _open_backup_snapshot(service.control_path()) as source:
        source.execute("SELECT id FROM installation_control").fetchone()
        _sqlite_backup(source, control_snapshot)
    payloads = {
        ("storage-owner", "control_journal"): [item.model_dump(mode="json") for item in journal],
        ("storage-owner", "public_trust"): [item.model_dump(mode="json") for item in service._control.list_trust_entries()],
        ("storage-owner", "finalized_publications"): [publication.model_dump(mode="json")],
        ("storage-owner", "participant_inventory"): {"managed_spool": None},
        ("active", "suppression"): [
            item.model_dump(mode="json") for item in read_suppression_records(service.installation_root / "control")
        ],
        ("archived", "suppression"): [],
    }
    inputs = {("storage-owner", "control_snapshot"): control_snapshot}
    for (owner, kind), payload in payloads.items():
        path = scratch / f"{owner}-{kind}.json"
        write_private_file(path, json.dumps(payload).encode(), exclusive=True)
        inputs[owner, kind] = path
    members = tuple(
        RecoveryBundleMember.model_validate({
            "owner_id": owner, "kind": kind, "schema_version": 1, "size_bytes": path.stat().st_size,
            "digest": hashlib.sha256(path.read_bytes()).hexdigest(), "source_coordinate": journal[-1].entry_digest,
        })
        for (owner, kind), path in sorted(inputs.items())
    )
    bundle = InstallationControlRecoveryBundle(
        installation_id=state.installation_id, repository_id=publication.repository_id,
        generation_id=publication.data_generation_id, custody_id="test-custody",
        control_revision=state.control_revision, journal_ordinal=len(journal), journal_tip=journal[-1].entry_digest,
        eligibility_epoch=state.eligibility_epoch, publication_digest=publication.payload_digest(),
        trust_registry_digest=service._trust_registry_digest(), signer_key_id=signer_id,
        signer_fingerprint=hashlib.sha256(public_key).hexdigest(), members=members, signature="0" * 128,
    )
    bundle = bundle.model_copy(update={"signature": service._signing.sign(
        signer_id, INSTALLATION_CONTROL_RECOVERY_SIGNATURE_PURPOSE, bundle.unsigned_digest(),
    )})
    custody = IndependentRecoveryCustody(
        custody_root, custody_id=bundle.custody_id, installation_id=bundle.installation_id,
        repository_id=bundle.repository_id, trusted_public_keys={signer_id: public_key},
    )
    seal_recovery_bundle(
        bundle, sources=tuple(path for _, path in sorted(inputs.items())),
        destination=custody.bundle_path(bundle.anchor()), recovery_key=_CONTROL_KEY, public_key=public_key,
    )
    custody.register(sign_recovery_head(
        SealedRecoveryHead(anchor=bundle.anchor(), outcome="registered"),
        signer=service._signing, signer_key_id=signer_id,
    ))
    return custody, bundle, public_key


def test_older_archive_restores_inert_and_retries_publish_before_sealed_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = tmp_path / "original"
    destination = tmp_path / "replacement"
    media = tmp_path / "retained-keys"
    media.mkdir(mode=0o700)
    archive = tmp_path / "old-archive"
    suppression = SuppressionRecord(
        suppression_id="a" * 64, plan_digest="b" * 64, closure_digest="c" * 64,
        scope_note="source revoked after archive", applied_at_unix=1,
        suppressed=(SuppressionCoordinate(coordinate_kind="source", coordinate_id="revoked-source"),),
    )
    with StorageAdministrationService(original) as source:
        source.initialize()
        _publish(source, "memory:before-archive")
        _set_mode(source, "read_only")
        manifest = BackupRestoreOperator(StorageAdministrationOperator(source)).create_backup(
            capability=mint_owner_capability(source, _OWNER),
            archive_root=archive, reason="replacement fixture", recovery_key=_DATA_KEY,
        )
        _set_mode(source, "active")
        _publish(source, "memory:after-archive")
        _set_mode(source, "read_only")
        write_suppression_record(original / "control", suppression)
        custody, bundle, public_key = _retain_current_authority(source, tmp_path / "custody", tmp_path / "snapshot")
        key_name = f"{source._signer_key_id}.key"
        _copy_private_restore_media(original / "control" / "keys" / key_name, media / key_name)
    original.rename(tmp_path / "unavailable-original")
    plan = ReplacementRestorePlan(
        archive_digest=manifest.manifest_digest, predecessor=custody.current_sealed().digest(),
        custody_id=bundle.custody_id, destination=str(destination), signer_fingerprint=bundle.signer_fingerprint,
        isolation_evidence_digest="f" * 64, data_loss_acknowledged=True,
    )

    def stage():
        return stage_replacement_restore(
            plan, custody=custody, archive=archive, bundle=custody.bundle_path(bundle.anchor()), destination=destination,
            trust_key=public_key, retained_signing_keys=media, data_recovery_key=_DATA_KEY,
            control_recovery_key=_CONTROL_KEY,
        )

    rename = replacement_restore.os.rename

    def cut_local_publish(source: Path, target: Path) -> None:
        if target == destination:
            raise OSError("interrupted after independent prepare")
        rename(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(replacement_restore.os, "rename", cut_local_publish)
        with pytest.raises(RecoveryAuthorityError, match="could not be verified"):
            stage()
    assert not destination.exists()
    with pytest.raises(RecoveryAuthorityError, match="pending"):
        custody.current_sealed()

    marker = stage()
    assert custody.current() == marker.pending_head
    with StorageAdministrationService(destination) as replacement:
        assert replacement._control_state().quarantined_reason == REPLACEMENT_RECOVERY_QUARANTINE
        with pytest.raises(RuntimeError, match="independent seal"):
            replacement.partition()
    with pytest.raises(RecoveryAuthorityError, match="pending"):
        activate_sealed_replacement(destination, custody=custody, trust_key=public_key, control_recovery_key=_CONTROL_KEY)

    successor = seal_staged_replacement(destination, custody=custody, trust_key=public_key, control_recovery_key=_CONTROL_KEY)
    assert custody.current_sealed() == successor
    assert seal_staged_replacement(
        destination, custody=custody, trust_key=public_key, control_recovery_key=_CONTROL_KEY,
    ) == successor
    for _ in range(2):
        activate_sealed_replacement(destination, custody=custody, trust_key=public_key, control_recovery_key=_CONTROL_KEY)
    with StorageAdministrationService(destination) as replacement:
        assert replacement._control_state() == marker.activation_state
        assert marker.activation_state.mode == "read_only"
        assert marker.publication.data_generation_id != bundle.generation_id
        assert read_suppression_records(destination / "control") == (suppression,)


def test_live_read_grant_partial_effect_seals_and_survives_older_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = tmp_path / "original"
    destination = tmp_path / "replacement"
    custody_path = tmp_path / "custody"
    custody_path.mkdir(mode=0o700)
    media = tmp_path / "retained-keys"
    media.mkdir(mode=0o700)
    archive = tmp_path / "older-archive"
    grant_id = "read-grant:revoked-after-archive"
    operation_id = "operator-revokes-old-grant"
    with StorageAdministrationService(original) as source:
        source.initialize()
        _publish(source, "memory:forgotten-after-archive")
        credentials = SidecarCredentialStore(original / "control" / "credentials")
        _, old_secret = credentials.issue("former-reader")
        _set_mode(source, "read_only")
        cap = mint_owner_capability(source, _OWNER)
        operator = StorageAdministrationOperator(source)
        manifest = BackupRestoreOperator(operator).create_backup(
            capability=cap, archive_root=archive, reason="archive before postarchive denials", recovery_key=_DATA_KEY,
        )
        governance = GovernanceOperator(operator)
        suppressed = governance.apply_forget(capability=cap, plan=governance.plan_forget(
            capability=cap, scope_note="do not return the forgotten record",
            selectors=(ForgetTargetSelector(selector_kind="record", selector_id="memory:forgotten-after-archive"),),
        ))
        signer_id = source._signer_key_id
        public_key = source._signing.public_key_bytes(signer_id)
        custody = IndependentRecoveryCustody(
            custody_path, custody_id="read-denial-custody", installation_id=source._control_state().installation_id,
            repository_id=source._repository_id(), trusted_public_keys={signer_id: public_key},
        )
        owner = ReadGrantRecoveryOwner(source, custody=custody, public_key=public_key, recovery_key=_CONTROL_KEY)
        registered = owner.register(capability=cap)
        assert owner.register(capability=cap) == registered
        registry = GrantEpochRegistry(original / "control" / "grants")
        assert registry.current_epoch(grant_id) == 1
        with pytest.raises(GrantRegistryError, match="requires independent custody"):
            registry.revoke(grant_id, reason="cannot bypass the custody owner")
        unavailable = (custody_path / "head.json").rename(custody_path / "temporarily-unavailable")
        try:
            with pytest.raises(RecoveryAuthorityError, match="could not be read"):
                owner.revoke(grant_id, operation_id=operation_id, capability=cap)
            assert registry.current_epoch(grant_id) == 1
        finally:
            unavailable.rename(custody_path / "head.json")

        write_epochs = GrantEpochRegistry._write_epochs

        def cut_after_local_epoch(registry: GrantEpochRegistry, epochs: dict[str, int]) -> None:
            write_epochs(registry, epochs)
            raise OSError("crash after the effective denial and before audit")

        with monkeypatch.context() as patch:
            patch.setattr(GrantEpochRegistry, "_write_epochs", cut_after_local_epoch)
            with pytest.raises(OSError, match="before audit"):
                owner.revoke(grant_id, operation_id=operation_id, capability=cap)
        with pytest.raises(RecoveryAuthorityError, match="pending"):
            custody.current_sealed()
        assert registry.revocations() == ()
        with pytest.raises(GrantRegistryError, match="stale_grant"):
            registry.require_current(grant_id, 1)
        key_name = f"{signer_id}.key"
        _copy_private_restore_media(original / "control" / "keys" / key_name, media / key_name)

    with StorageAdministrationService(original) as source:
        owner = ReadGrantRecoveryOwner(source, custody=custody, public_key=public_key, recovery_key=_CONTROL_KEY)
        with pytest.raises(RecoveryAuthorityError, match="operation is unavailable"):
            owner.revoke(grant_id, operation_id="unrelated-operation", capability=cap)
        journal = next((original / "control" / "suppressions").glob("forget-*.json"))
        interrupted = journal.rename(journal.with_name("temporarily-unavailable"))
        try:
            with pytest.raises(RecoveryAuthorityError, match="differs from retained control and suppressions"):
                owner.revoke(grant_id, operation_id=operation_id, capability=cap)
        finally:
            interrupted.rename(journal)

        def cut_before_seal(*_args: object, **_kwargs: object) -> None:
            raise OSError("interrupted after local audit")

        with monkeypatch.context() as patch:
            patch.setattr(read_grant_recovery, "seal_recovery_bundle", cut_before_seal)
            with pytest.raises(OSError, match="after local audit"):
                owner.revoke(grant_id, operation_id=operation_id, capability=cap)
        pending = custody.current()
        assert pending.payload.state == "pending"
        assert registry.revocations()[0].custody_operation_digest == pending.payload.operation_digest
        successor = owner.revoke(grant_id, operation_id=operation_id, capability=cap)
        assert owner.revoke(grant_id, operation_id=operation_id, capability=cap) == successor
        assert custody.current_sealed() == successor
        assert len(registry.revocations()) == 1
    original.rename(tmp_path / "isolated-original")

    assert isinstance(successor.payload, SealedRecoveryHead)
    anchor = successor.payload.anchor
    bundle_path = custody.bundle_path(anchor)
    verified = tmp_path / "inspected-authority"
    bundle = open_recovery_bundle(
        bundle_path, anchor=anchor, public_key=public_key, recovery_key=_CONTROL_KEY, destination=verified,
    )
    for index in range(len(bundle.members)):
        assert cap.capability_digest.encode() not in (verified / f"member-{index:03d}.snapshot").read_bytes()
        assert old_secret.encode() not in (verified / f"member-{index:03d}.snapshot").read_bytes()
    marker = stage_replacement_restore(
        ReplacementRestorePlan(
            archive_digest=manifest.manifest_digest, predecessor=successor.digest(), custody_id=anchor.custody_id,
            destination=str(destination), signer_fingerprint=anchor.signer_fingerprint,
            isolation_evidence_digest="b" * 64, data_loss_acknowledged=True,
        ),
        custody=custody, archive=archive, bundle=bundle_path, destination=destination,
        trust_key=public_key, retained_signing_keys=media, data_recovery_key=_DATA_KEY,
        control_recovery_key=_CONTROL_KEY,
    )
    assert marker.read_grant_denials_digest is not None
    seal_staged_replacement(destination, custody=custody, trust_key=public_key, control_recovery_key=_CONTROL_KEY)
    activate_sealed_replacement(destination, custody=custody, trust_key=public_key, control_recovery_key=_CONTROL_KEY)
    with StorageAdministrationService(destination) as replacement:
        with pytest.raises(OperatorError, match="owner capability does not match"):
            require_owner_capability(replacement, cap)
        assert SidecarCredentialStore(destination / "control" / "credentials").credential_for(old_secret) is None
        restored = GrantEpochRegistry(destination / "control" / "grants")
        with pytest.raises(GrantRegistryError, match="stale_grant"):
            restored.require_current(grant_id, 1)
        assert restored.current_epoch(grant_id) == 2
        records = read_suppression_records(destination / "control")
        assert [(record.suppression_id, record.authority_capability_digest) for record in records] == [
            (suppressed.suppression_id, None),
        ]
