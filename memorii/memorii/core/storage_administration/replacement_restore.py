"""Offline managed cutover against an independently retained recovery head."""

from __future__ import annotations

import base64
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from memorii.core.harness_state.grant_registry import GrantDenialSnapshot, GrantEpochRegistry
from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import (
    InstallationControlJournalEntry,
    InstallationControlState,
    InstalledManagedSpoolBinding,
    RuntimePublicationState,
    canonical_json_digest,
)
from memorii.core.persistence.key_owner import (
    INSTALLATION_RECOVERY_ACTIVATION_SIGNATURE_PURPOSE,
    verify_public_signature,
)
from memorii.core.storage_administration.backup_cipher import decrypt_backup_participant
from memorii.core.storage_administration.control_recovery_export import (
    MAX_RECOVERY_METADATA_BYTES,
    export_control_recovery,
    read_recovery_suppressions,
)
from memorii.core.storage_administration.operator import StorageAdministrationOperator
from memorii.core.storage_administration.operator_backup import (
    BackupRestoreOperator,
    InstallationBackupManifest,
    _copy_private_restore_media,
    _open_backup_snapshot,
    _snapshot_digest,
    _sqlite_backup,
    _suppression_snapshot_digest,
    _sync_directory,
    _validate_participant,
    _verify_staged_backup,
)
from memorii.core.storage_administration.recovery_authority import (
    IndependentRecoveryCustody,
    InstallationControlRecoveryBundle,
    InstallationRecoveryHead,
    PendingRecoveryHead,
    RecoveryAuthorityError,
    RecoveryParticipantExpectation,
    SealedRecoveryHead,
    decode_recovery_json,
    sign_recovery_head,
)
from memorii.core.storage_administration.recovery_bundle import open_recovery_bundle, seal_recovery_bundle
from memorii.core.storage_administration.service import (
    REPLACEMENT_RECOVERY_QUARANTINE,
    StorageAdministrationService,
)
from memorii.core.storage_administration.suppression_journal import SuppressionRecord
from memorii.stores.sqlite.control import ControlDatabase
from memorii.stores.sqlite.partition import PartitionDataRepository
from memorii.stores.sqlite.private_storage import (
    ensure_private_directory,
    read_private_file,
    require_private_directory,
    require_private_file,
    write_private_file,
)

_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_ACTIVATION_FILE = "replacement-activation.json"
_CAP_BYTES = 256 * 1024
_SUPPRESSION_RECORDS = TypeAdapter(tuple[SuppressionRecord, ...])


class ReplacementRestorePlan(BaseModel):
    """Owner review of exact inputs and acknowledged loss before cutover."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal[1] = 1
    archive_digest: _Digest
    predecessor: _Digest
    custody_id: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    signer_fingerprint: _Digest
    isolation_evidence_digest: _Digest
    data_loss_acknowledged: Literal[True]

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class InstallationRecoveryActivation(BaseModel):
    """Signed local link from an inert root to the planned independent seal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal[1] = 1
    plan: ReplacementRestorePlan
    pending_head: InstallationRecoveryHead
    publication: RuntimePublicationState
    suppression_snapshots: tuple[_Digest, _Digest]
    managed_spool_digest: _Digest | None = None
    read_grant_denials_digest: _Digest | None = None
    activation_state: InstallationControlState
    activation_journal: InstallationControlJournalEntry
    signer_key_id: str = Field(min_length=1)
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    def unsigned_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json", exclude={"signature"}))


def _bounded_record(path: Path, *, limit: int = MAX_RECOVERY_METADATA_BYTES) -> object:
    raw = read_private_file(path, limit=limit + 1)
    if len(raw) > limit:
        raise RecoveryAuthorityError("resource_exhausted: recovery record exceeds limit")
    return decode_recovery_json(raw)


def _materialize_suppressions(source: Path, directory: Path) -> None:
    records = _SUPPRESSION_RECORDS.validate_python(_bounded_record(source))
    identities = {record.suppression_id for record in records}
    if len(identities) != len(records):
        raise RecoveryAuthorityError("integrity_error: duplicate suppression record")
    if any(record.authority_capability_digest is not None for record in records):
        raise RecoveryAuthorityError("denied: recovery suppression contains reusable owner authority")
    ensure_private_directory(directory)
    for record in records:
        write_private_file(
            directory / f"forget-{record.suppression_id}.json",
            record.model_dump_json().encode("utf-8"), exclusive=True,
        )


def _stage_archive(
    owner: BackupRestoreOperator, archive: Path, temporary: Path, *, recovery_key: bytes,
) -> InstallationBackupManifest:
    require_private_directory(archive)
    require_private_file(archive / "backup-complete.json")
    manifest = owner.verify_backup(archive_root=archive)
    if manifest.control_tip_digest is None or manifest.publication_digest is None or len(recovery_key) != 32:
        raise RecoveryAuthorityError("invalid_request: managed replacement requires an exact signed archive")
    key = AESGCM(recovery_key).decrypt(
        base64.b64decode(manifest.key_wrap_nonce, validate=True),
        base64.b64decode(manifest.wrapped_content_key, validate=True),
        None,
    )
    for participant in manifest.participants:
        source = archive / _validate_participant(participant)
        require_private_file(source)
        decrypt_backup_participant(
            source, temporary / f"{participant.participant_id}.sqlite3", key=key,
            nonce=base64.b64decode(participant.nonce, validate=True),
            expected_digest=participant.sha256, expected_size=participant.size_bytes,
        )
    return manifest


def _restore_spool(
    binding: InstalledManagedSpoolBinding | None, manifest: InstallationBackupManifest, source: Path, destination: Path,
    publication: RuntimePublicationState,
) -> str | None:
    from memorii.core.harness_state.managed_spool_store import SqliteManagedSpool, _store_file

    watermark = manifest.managed_spool
    if (binding is None) != (watermark is None) or (
        binding is not None and watermark is not None and binding.store_id != watermark.store_id
    ):
        raise RecoveryAuthorityError("integrity_error: archived spool differs from independent registration")
    if watermark is None:
        return None
    spool = destination / "spool" / "managed"
    ensure_private_directory(spool.parent)
    ensure_private_directory(spool)
    path = _store_file(spool, watermark.store_id)
    _copy_private_restore_media(source / "managed-spool.sqlite3", path)
    selected = SqliteManagedSpool(spool, watermark.store_id)
    selected.hold_prior_generation(
        installation_id=publication.installation_id, repository_id=publication.repository_id,
        generation_id=publication.data_generation_id,
    )
    _sync_directory(spool)
    _sync_directory(spool.parent)
    return _snapshot_digest(path)


def _read_activation(root: Path, trust_key: bytes) -> InstallationRecoveryActivation:
    marker = InstallationRecoveryActivation.model_validate(_bounded_record(root / "control" / _ACTIVATION_FILE, limit=_CAP_BYTES))
    if hashlib.sha256(trust_key).hexdigest() != marker.plan.signer_fingerprint or not verify_public_signature(
        trust_key, INSTALLATION_RECOVERY_ACTIVATION_SIGNATURE_PURPOSE, marker.unsigned_digest(), marker.signature,
    ):
        raise RecoveryAuthorityError("integrity_error: replacement activation marker is invalid")
    return marker


def _require_inert_root(service: StorageAdministrationService, marker: InstallationRecoveryActivation) -> None:
    from memorii.core.harness_state.managed_spool_store import _store_file

    state = service._control_state()
    expected = marker.activation_state
    publication = marker.publication
    if (
        state.quarantined_reason != REPLACEMENT_RECOVERY_QUARANTINE
        or state.control_revision + 1 != expected.control_revision
        or state.model_copy(update={"quarantined_reason": None, "control_revision": expected.control_revision}) != expected
        or service._control.read_publication_state(publication.repository_id) != publication
        or service._control.next_journal_position() != (marker.activation_journal.revision, marker.activation_journal.prior_digest)
        or marker.activation_journal.before_digest != canonical_json_digest(state.model_dump(mode="json"))
        or marker.activation_journal.after_digest != canonical_json_digest(expected.model_dump(mode="json"))
    ):
        raise RecoveryAuthorityError("integrity_error: inert replacement control changed since staging")
    control = service.installation_root / "control"
    if marker.read_grant_denials_digest is not None:
        registry = GrantEpochRegistry(control / "grants")
        with registry.recovery_lease():
            registry.require_recovery_custody(marker.plan.custody_id)
            if registry.recovery_snapshot().digest() != marker.read_grant_denials_digest:
                raise RecoveryAuthorityError("integrity_error: replacement read denials changed since staging")
    if marker.suppression_snapshots != (
        _suppression_snapshot_digest(control / "suppressions"), _suppression_snapshot_digest(control / "suppressions-archive"),
    ):
        raise RecoveryAuthorityError("integrity_error: inert replacement suppression changed since staging")
    binding = service._control.read_managed_spool_binding()
    if (binding is None) != (marker.managed_spool_digest is None) or (
        binding is not None and marker.managed_spool_digest != _snapshot_digest(
            _store_file(service.installation_root / "spool" / "managed", binding.store_id),
        )
    ):
        raise RecoveryAuthorityError("integrity_error: inert replacement spool changed since staging")
    root = service.installation_root / "partition"
    with (
        PartitionDataRepository(root / "partition.sqlite3", require_existing=True, protected_storage_root=root) as partition,
        partition.transaction(write=False) as connection,
    ):
        row = partition.read_publication_row(connection)
        if (
            row is None or row["tuple_digest"] != publication.payload_digest()
            or not service._matches_signed_publication(row, publication)
            or not service._matches_materialization(connection, publication, partition=partition)
        ):
            raise RecoveryAuthorityError("integrity_error: inert replacement partition changed since staging")


def _publish_replacement(
    candidate: Path, destination: Path, marker: InstallationRecoveryActivation, custody: IndependentRecoveryCustody,
) -> None:
    if destination.exists() or destination.is_symlink():
        raise RecoveryAuthorityError("conflict: replacement destination appeared before publish")
    current = custody.current()
    if current.digest() == marker.plan.predecessor:
        custody.prepare(marker.pending_head)
    elif current != marker.pending_head:
        raise RecoveryAuthorityError("conflict: different independent recovery transition")
    os.rename(candidate, destination)
    _sync_directory(destination.parent)


def stage_replacement_restore(
    plan: ReplacementRestorePlan, *, custody: IndependentRecoveryCustody,
    archive: Path, bundle: Path, destination: Path, trust_key: bytes,
    retained_signing_keys: Path, data_recovery_key: bytes, control_recovery_key: bytes,
) -> InstallationRecoveryActivation:
    """Publish an inert root. A separate verified independent seal gates activation."""
    require_private_directory(destination.parent)
    require_private_directory(retained_signing_keys)
    if str(destination.absolute()) != plan.destination or destination.exists() or destination.is_symlink():
        raise RecoveryAuthorityError("conflict: replacement requires the reviewed absent destination")
    prepared = destination.parent / f".replacement-{plan.digest()}"
    if prepared.exists() or prepared.is_symlink():
        require_private_directory(prepared)
        with locked_file(destination.parent / ".replacement-publish.lock", exclusive=True, private=True):
            marker = _read_activation(prepared, trust_key)
            if marker.plan != plan:
                raise RecoveryAuthorityError("conflict: prepared replacement differs from review")
            with StorageAdministrationService(prepared, signer_key_id=marker.signer_key_id) as service:
                _require_inert_root(service, marker)
            _publish_replacement(prepared, destination, marker, custody)
        return marker
    predecessor = custody.current_sealed()
    assert isinstance(predecessor.payload, SealedRecoveryHead)
    anchor = predecessor.payload.anchor
    if (
        plan.predecessor != predecessor.digest()
        or plan.custody_id != anchor.custody_id
        or plan.signer_fingerprint != anchor.signer_fingerprint
        or hashlib.sha256(trust_key).hexdigest() != anchor.signer_fingerprint
        or bundle.absolute() != custody.bundle_path(anchor).absolute()
    ):
        raise RecoveryAuthorityError("conflict: independent authority changed since review")
    try:
        with tempfile.TemporaryDirectory(prefix=".managed-replacement-", dir=destination.parent) as scratch:
            workspace = Path(scratch)
            authority_root = workspace / "authority"
            authority = open_recovery_bundle(
                bundle, anchor=anchor, public_key=trust_key, recovery_key=control_recovery_key,
                destination=authority_root,
            )
            sources = {
                (record.owner_id, record.kind): authority_root / f"member-{position:03d}.snapshot"
                for position, record in enumerate(authority.members)
            }
            # This first reader supports the exact current-format local deny
            # participants. A future owner codec must be explicit. Never ignore
            # a signed authority member that this reader cannot apply.
            recognized = {
                ("storage-owner", "control_snapshot"), ("storage-owner", "control_journal"),
                ("storage-owner", "public_trust"), ("storage-owner", "finalized_publications"),
                ("storage-owner", "participant_inventory"), ("active", "suppression"),
                ("archived", "suppression"),
            }
            read_denial_key = ("read-grants", "deny_state")
            if set(sources) - {read_denial_key} != recognized or any(member.schema_version != 1 for member in authority.members):
                raise RecoveryAuthorityError("unsupported_configuration: replacement authority codecs are incomplete")
            working = workspace / "replacement"
            control = working / "control"
            keys = control / "keys"
            ensure_private_directory(working)
            ensure_private_directory(control)
            ensure_private_directory(keys)
            _copy_private_restore_media(sources["storage-owner", "control_snapshot"], control / "control.sqlite3")
            key_name = f"{authority.signer_key_id}.key"
            if Path(key_name).name != key_name or key_name.startswith("."):
                raise RecoveryAuthorityError("invalid_request: retained signer identity is invalid")
            _copy_private_restore_media(retained_signing_keys / key_name, keys / key_name)
            _materialize_suppressions(sources["active", "suppression"], control / "suppressions")
            _materialize_suppressions(sources["archived", "suppression"], control / "suppressions-archive")
            read_denials = None
            if read_denial_key in sources:
                read_denials = GrantDenialSnapshot.model_validate(_bounded_record(sources[read_denial_key]))
                member = next(item for item in authority.members if (item.owner_id, item.kind) == read_denial_key)
                if member.source_coordinate != read_denials.digest():
                    raise RecoveryAuthorityError("integrity_error: anchored read deny state does not match its coordinate")
                GrantEpochRegistry(control / "grants").restore_recovery_snapshot(read_denials, custody_id=anchor.custody_id)
            staged_archive = workspace / "archive"
            ensure_private_directory(staged_archive)
            with StorageAdministrationService(working, signer_key_id=authority.signer_key_id) as service:
                if service._signing.public_key_bytes(authority.signer_key_id) != trust_key:
                    raise RecoveryAuthorityError("denied: retained signer does not match independent authority")
                state = service._control_state()
                journal = service._control.read_journal()
                current = service._control.read_publication_state(anchor.repository_id)
                binding = service._control.read_managed_spool_binding()
                if (
                    current is None or state.quarantined_reason is not None
                    or state.installation_id != anchor.installation_id
                    or state.control_revision != anchor.control_revision
                    or state.eligibility_epoch != anchor.eligibility_epoch
                    or (len(journal), journal[-1].entry_digest if journal else "") != (anchor.journal_ordinal, anchor.journal_tip)
                    or current.payload_digest() != anchor.publication_digest
                    or current.data_generation_id != authority.generation_id
                    or service._trust_registry_digest() != authority.trust_registry_digest
                    or service._control.read_pending_intent(anchor.repository_id) is not None
                    or _bounded_record(sources["storage-owner", "control_journal"]) != [item.model_dump(mode="json") for item in journal]
                    or _bounded_record(sources["storage-owner", "public_trust"])
                    != [item.model_dump(mode="json") for item in service._control.list_trust_entries()]
                    or _bounded_record(sources["storage-owner", "finalized_publications"]) != [current.model_dump(mode="json")]
                    or _bounded_record(sources["storage-owner", "participant_inventory"])
                    != {"managed_spool": None if binding is None else binding.model_dump(mode="json")}
                ):
                    raise RecoveryAuthorityError("integrity_error: current control differs from its anchored inventory")
                generation_change = service._control.read_generation_change(anchor.repository_id)
                if generation_change is not None and generation_change.phase == "prepared":
                    raise RecoveryAuthorityError("needs_reconciliation: independent generation transition is unresolved")

                operator = BackupRestoreOperator(StorageAdministrationOperator(service))
                source_manifest = _stage_archive(operator, archive, staged_archive, recovery_key=data_recovery_key)
                if source_manifest.manifest_digest != plan.archive_digest:
                    raise RecoveryAuthorityError("conflict: archive differs from reviewed replacement")
                source = _verify_staged_backup(service, staged_archive, source_manifest)
                if (
                    source.publication.repository_id != anchor.repository_id
                    or source.publication.vector.partition_ordinal > current.vector.partition_ordinal
                    or source_manifest.control_revision > anchor.control_revision
                    or all(item.entry_digest != source.control_tip_digest for item in journal)
                ):
                    raise RecoveryAuthorityError("integrity_error: archive control is not an ancestor of the anchored root")
                partition_root = working / "partition"
                ensure_private_directory(partition_root)
                target = partition_root / "partition.sqlite3"
                _copy_private_restore_media(staged_archive / "partition.sqlite3", target)
                publication = operator._prepare_restored_generation(
                    target, source=source.publication, live=current, preview_digest=plan.digest(),
                    require_upgrade=False, raw_payloads=False,
                )
                spool_digest = _restore_spool(binding, source_manifest, staged_archive, working, publication)
                with (
                    PartitionDataRepository(target, require_existing=True, protected_storage_root=partition_root) as data,
                    data.transaction(write=False) as connection,
                ):
                    if not service._matches_materialization(connection, publication, partition=data):
                        raise RecoveryAuthorityError("integrity_error: replacement data closure is invalid")
                candidate = state.model_copy(update={
                    "mode": "read_only", "control_revision": state.control_revision + 1,
                    "quarantined_reason": REPLACEMENT_RECOVERY_QUARANTINE,
                })
                service._control.write_finalized_publication(
                    anchor.repository_id, publication, candidate,
                    service._journal_entry(
                        operation="publication_finalized", before_digest=current.payload_digest(),
                        after_digest=publication.payload_digest(),
                    ),
                )
                ready = candidate.model_copy(update={
                    "control_revision": candidate.control_revision + 1, "quarantined_reason": None,
                })
                entry = service._journal_entry(
                    operation="mode_changed", before_digest=canonical_json_digest(candidate.model_dump(mode="json")),
                    after_digest=canonical_json_digest(ready.model_dump(mode="json")),
                )
                pending = sign_recovery_head(
                    PendingRecoveryHead(
                        predecessor=plan.predecessor, prior_anchor=anchor, operation="generation",
                        operation_digest=plan.digest(), participants=(RecoveryParticipantExpectation(
                            participant_id="storage-owner", revision=state.control_revision, pre_state_digest=anchor.journal_tip,
                            effect_digest=entry.entry_digest,
                        ),),
                    ),
                    signer=service._signing, signer_key_id=authority.signer_key_id,
                )
                activation = InstallationRecoveryActivation(
                    plan=plan, pending_head=pending, publication=publication, activation_state=ready,
                    suppression_snapshots=(
                        _suppression_snapshot_digest(control / "suppressions"),
                        _suppression_snapshot_digest(control / "suppressions-archive"),
                    ), managed_spool_digest=spool_digest,
                    read_grant_denials_digest=None if read_denials is None else read_denials.digest(),
                    activation_journal=entry, signer_key_id=authority.signer_key_id, signature="0" * 128,
                )
                activation = activation.model_copy(update={"signature": service._signing.sign(
                    authority.signer_key_id, INSTALLATION_RECOVERY_ACTIVATION_SIGNATURE_PURPOSE, activation.unsigned_digest(),
                )})
                write_private_file(control / _ACTIVATION_FILE, activation.model_dump_json().encode("utf-8"), exclusive=True)

            _snapshot_digest(control / "control.sqlite3")
            _sync_directory(control)
            _sync_directory(partition_root)
            _sync_directory(working)
            with locked_file(destination.parent / ".replacement-publish.lock", exclusive=True, private=True):
                if prepared.exists() or prepared.is_symlink():
                    raise RecoveryAuthorityError("conflict: a prepared replacement already exists")
                os.rename(working, prepared)
                _sync_directory(destination.parent)
                _publish_replacement(prepared, destination, activation, custody)
            return activation
    except (InvalidTag, OSError, ValueError) as exc:
        raise RecoveryAuthorityError("integrity_error: replacement inputs could not be verified") from exc


def _require_activation_seal(
    sealed: InstallationRecoveryHead, marker: InstallationRecoveryActivation,
) -> SealedRecoveryHead:
    if not isinstance(sealed.payload, SealedRecoveryHead):
        raise RecoveryAuthorityError("needs_reconciliation: replacement authority is pending")
    successor = sealed.payload
    anchor = successor.anchor
    expected = marker.activation_state
    publication = marker.publication
    if (
        successor.outcome != "applied" or successor.pending_digest != marker.pending_head.digest()
        or successor.predecessor != marker.plan.predecessor or successor.operation_digest != marker.plan.digest()
        or anchor.custody_id != marker.plan.custody_id or anchor.signer_fingerprint != marker.plan.signer_fingerprint
        or anchor.installation_id != publication.installation_id or anchor.repository_id != publication.repository_id
        or anchor.publication_digest != publication.payload_digest() or anchor.control_revision != expected.control_revision
        or anchor.eligibility_epoch != expected.eligibility_epoch
        or (anchor.journal_ordinal, anchor.journal_tip)
        != (marker.activation_journal.revision, marker.activation_journal.entry_digest)
    ):
        raise RecoveryAuthorityError("conflict: independent seal differs from the prepared replacement")
    return successor


def _snapshot_successor(
    service: StorageAdministrationService, marker: InstallationRecoveryActivation, scratch: Path,
) -> tuple[InstallationControlRecoveryBundle, tuple[Path, ...]]:
    destination = scratch / "control.sqlite3"
    with _open_backup_snapshot(service.control_path()) as source:
        source.execute("SELECT id FROM installation_control").fetchone()
        _sqlite_backup(source, destination)
    with ControlDatabase(destination, journal_verifier=service._verify_journal_signature) as control:
        control.write_control_state(marker.activation_state, marker.activation_journal)
        control.validate_journal()
    _snapshot_digest(destination)
    root = service.installation_root / "control"
    denials = None
    if marker.read_grant_denials_digest is not None:
        registry = GrantEpochRegistry(root / "grants")
        with registry.recovery_lease():
            denials = registry.recovery_snapshot()
    return export_control_recovery(
        service, snapshot=destination, state=marker.activation_state, publication=marker.publication,
        custody_id=marker.plan.custody_id, output=scratch, grant_denials=denials,
        suppressions=(
            read_recovery_suppressions(root / "suppressions"),
            read_recovery_suppressions(root / "suppressions-archive"),
        ),
    )


def seal_staged_replacement(
    destination: Path, *, custody: IndependentRecoveryCustody, trust_key: bytes, control_recovery_key: bytes,
) -> InstallationRecoveryHead:
    """Retain the exact successor bundle before recording the independent seal."""
    require_private_directory(destination)
    marker = _read_activation(destination, trust_key)
    if marker.plan.destination != str(destination.absolute()):
        raise RecoveryAuthorityError("conflict: replacement root differs from reviewed destination")
    current = custody.current()
    if current != marker.pending_head:
        _require_activation_seal(current, marker)
        return current
    with (
        tempfile.TemporaryDirectory(prefix=".replacement-successor-", dir=destination.parent) as scratch,
        StorageAdministrationService(destination, signer_key_id=marker.signer_key_id) as service,
        service._publication_fence(),
    ):
        _require_inert_root(service, marker)
        manifest, sources = _snapshot_successor(service, marker, Path(scratch))
        anchor = manifest.anchor()
        path = custody.bundle_path(anchor)
        if path.exists() or path.is_symlink():
            open_recovery_bundle(
                path, anchor=anchor, public_key=trust_key, recovery_key=control_recovery_key,
                destination=Path(scratch) / "retained-successor",
            )
        else:
            seal_recovery_bundle(
                manifest, sources=sources, destination=path,
                recovery_key=control_recovery_key, public_key=trust_key,
            )
        successor = sign_recovery_head(
            SealedRecoveryHead(
                anchor=anchor, predecessor=marker.plan.predecessor, pending_digest=marker.pending_head.digest(),
                operation_digest=marker.plan.digest(), outcome="applied",
            ),
            signer=service._signing, signer_key_id=marker.signer_key_id,
        )
    custody.seal(successor, effects={"storage-owner": marker.activation_journal.entry_digest})
    return successor


def activate_sealed_replacement(
    destination: Path, *, custody: IndependentRecoveryCustody, trust_key: bytes, control_recovery_key: bytes,
) -> None:
    """Make the exact inert generation read-only once its sealed successor exists."""
    require_private_directory(destination)
    marker = _read_activation(destination, trust_key)
    if marker.plan.destination != str(destination.absolute()):
        raise RecoveryAuthorityError("conflict: replacement root differs from reviewed destination")
    sealed = custody.current_sealed()
    anchor = _require_activation_seal(sealed, marker).anchor
    with tempfile.TemporaryDirectory(prefix=".replacement-verify-", dir=destination.parent) as scratch:
        open_recovery_bundle(
            custody.bundle_path(anchor), anchor=anchor, public_key=trust_key,
            recovery_key=control_recovery_key, destination=Path(scratch) / "verified",
        )
    expected = marker.activation_state
    with (
        custody.guard_current_seal(sealed),
        StorageAdministrationService(destination, signer_key_id=marker.signer_key_id) as service,
        service._publication_fence(),
    ):
        if (
            service._control_state() == expected
            and service._control.next_journal_position() == (anchor.journal_ordinal + 1, anchor.journal_tip)
        ):
            return
        _require_inert_root(service, marker)
        service._control.write_control_state(expected, marker.activation_journal)
