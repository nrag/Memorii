"""Backup/restore operator controls over one installation.

Owner-authorized, plan-governed operations matching the design contract:
Backup create snapshots control and partition SQLite databases through the
online backup API under the acknowledged read_only barrier. It verifies the
pair against the captured signed tuple and control journal tip, encrypts
participants with a wrapped content key, and atomically publishes the archive.
Restore plans bind the verified archive and the current live watermark.
Staging verifies the decrypted pair before copying current suppression evidence
and publishing an inert, signed staging directory.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.persistence.contracts import (
    InstallationControlState,
    RuntimeMaterializationManifest,
    RuntimePublicationState,
    canonical_json_digest,
    empty_pointer_set_digest,
)
from memorii.core.persistence.key_owner import PARTITION_GENERATION_SIGNATURE_PURPOSE, RESTORE_STAGING_SIGNATURE_PURPOSE
from memorii.core.persistence.runtime_journal import RuntimeJournalError, verify_runtime_history
from memorii.core.storage_administration.generation_selection import (
    PARTITION_GENERATION_SELECTOR,
    PartitionGenerationSelector,
    selected_partition_path,
)
from memorii.core.storage_administration.operator import (
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    require_owner_capability,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.stores.sqlite.control import ControlDatabase, ControlJournalChainError
from memorii.stores.sqlite.partition import PartitionDataRepository

_BACKUP_MARKER = "backup-complete.json"
_RECOVERY_BUNDLE = "control-recovery-bundle.json"
_RECOVERY_ANCHOR = "recovery-anchor.json"
_RESTORE_ATTESTATION = "restore-staging-attestation.json"
_SIGNING_PURPOSE = "memorii.installation-backup-manifest.v1"
_CHUNK = 1 << 20
_ALLOWED_PARTICIPANTS = ("control", "partition")
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BackupParticipant(BaseModel):
    """One encrypted participant snapshot inside a backup."""

    participant_id: str = Field(min_length=1)
    kind: Literal["sqlite"] = "sqlite"
    filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    nonce: str = Field(min_length=16, max_length=32)

    model_config = ConfigDict(extra="forbid", frozen=True)


class InstallationBackupManifest(BaseModel):
    """Closed backup manifest; secrets and signing keys are never included."""

    manifest_version: Literal[1, 2] = 1
    installation_id: str = Field(min_length=1)
    created_at_unix: int = Field(ge=0)
    control_revision: int = Field(ge=1)
    eligibility_epoch: int = Field(ge=1)
    runtime_revision: int = Field(ge=0)
    memory_write_revision: int = Field(ge=0)
    memory_data_revision: int = Field(ge=0)
    publication_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    control_tip_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    participants: tuple[BackupParticipant, ...] = Field(min_length=1)
    wrapped_content_key: str = Field(min_length=1)
    key_wrap_nonce: str = Field(min_length=16, max_length=32)
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def exact_watermark(self) -> Self:
        if self.manifest_version == 2:
            if self.publication_digest is None or self.control_tip_digest is None:
                raise ValueError("backup manifest requires its signed publication and control tip")
        elif self.publication_digest is not None or self.control_tip_digest is not None:
            raise ValueError("legacy backup manifest cannot include an exact watermark")
        return self

    def unsigned_digest(self) -> str:
        excluded = {"manifest_digest", "manifest_signature"}
        if self.manifest_version == 1:
            excluded.update({"publication_digest", "control_tip_digest"})
        return hashlib.sha256(json.dumps(self.model_dump(exclude=excluded), sort_keys=True).encode()).hexdigest()


class RestorePlan(BaseModel):
    """Owner-reviewed plan derived from a verified backup archive."""

    archive_path: str = Field(min_length=1)
    installation_id: str = Field(min_length=1)
    control_revision: int = Field(ge=1)
    participant_count: int = Field(ge=1)
    archive_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_control_revision: int = Field(ge=1)
    expected_control_tip_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_loss_acknowledged: bool = False
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    def unsigned_digest(self) -> str:
        return canonical_json_digest(self.model_dump(exclude={"plan_digest"}))


class RestoreStagingAttestation(BaseModel):
    """Installation-signed evidence for an inert and review-bound restore."""

    attestation_version: Literal[1] = 1
    plan_digest: _Digest
    archive_manifest_digest: _Digest
    source_publication: RuntimePublicationState
    source_control_tip_digest: _Digest
    expected_publication_digest: _Digest
    expected_control_revision: int = Field(ge=1)
    expected_control_tip_digest: _Digest
    data_loss_acknowledged: bool
    control_snapshot_digest: _Digest
    partition_snapshot_digest: _Digest
    suppression_snapshot_digest: _Digest
    signer_key_id: str = Field(min_length=1)
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    def unsigned_digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"signature"})
        return _canonical_digest(payload)


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_digest(path: Path) -> str:
    for extension in ("-wal", "-shm", "-journal"):
        sidecar = path.with_name(path.name + extension)
        if sidecar.is_symlink() or sidecar.exists():
            raise OperatorError("integrity_error: staged SQLite snapshot contains a live sidecar")
    if path.is_symlink() or not path.is_file():
        raise OperatorError("integrity_error: staged SQLite snapshot must be a regular file")
    return _sha256_file(path)


def _suppression_snapshot_digest(directory: Path) -> str:
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise OperatorError("integrity_error: suppression snapshot must be a directory")
    entries: list[tuple[str, str]] = []
    for path in sorted(directory.glob("forget-*.json")):
        if path.is_symlink() or not path.is_file():
            raise OperatorError("integrity_error: suppression snapshot must contain regular journal files")
        entries.append((path.name, _sha256_file(path)))
    return _canonical_digest(entries)


@dataclass(frozen=True)
class _VerifiedBackup:
    publication: RuntimePublicationState
    control_tip_digest: str


def _sqlite_backup(source: Path, destination: Path) -> None:
    """Snapshot one SQLite database through the online backup API."""
    source_connection = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        destination_connection = sqlite3.connect(str(destination))
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()
    os.chmod(destination, 0o600)


def _atomic_write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    _sync_directory(path.parent)


def _sync_directory(path: Path) -> None:
    directory = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _validate_participant(participant: BackupParticipant) -> Path:
    """A participant filename must be a plain basename inside the archive."""
    filename = Path(participant.filename)
    if (
        filename.name != participant.filename
        or filename.is_absolute()
        or "/" in participant.filename
        or ".." in participant.filename
    ):
        raise OperatorError(
            f"invalid_request: participant {participant.participant_id}"
            " filename is not a plain basename"
        )
    return filename


class BackupRestoreOperator:
    """Backup create/verify and restore plan/apply over one installation."""

    def __init__(self, operator: StorageAdministrationOperator) -> None:
        self._operator = operator

    def create_backup(
        self,
        *,
        capability: OwnerCapability,
        archive_root: Path,
        reason: str,
        recovery_key: bytes,
    ) -> InstallationBackupManifest:
        service = self._operator._administration
        require_owner_capability(service, capability)
        if not reason.strip():
            raise OperatorError("invalid_request: backup reason is required")
        if len(recovery_key) != 32:
            raise OperatorError(
                "invalid_request: recovery key must be exactly 32 bytes"
            )
        if archive_root.is_symlink() or (
            archive_root.exists() and (not archive_root.is_dir() or any(archive_root.iterdir()))
        ):
            raise OperatorError("invalid_request: use a fresh backup directory")
        archive_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".backup-", dir=archive_root.parent) as scratch:
            copies = Path(scratch) / "copies"
            encrypted = Path(scratch) / "encrypted"
            copies.mkdir(mode=0o700)
            encrypted.mkdir(mode=0o700)
            # Only capture and the live watermark checks need the barrier.
            with service.verified_operation_context() as (state, finalized):
                if state.mode != "read_only":
                    raise OperatorError(
                        "conflict: backups require the acknowledged exclusive barrier"
                        " (change mode to read_only first)"
                    )
                _, tip = service._control.next_journal_position()
                with service.partition().transaction(write=False) as connection:
                    runtime_revision = service.partition().read_runtime_revision(connection)
                _sqlite_backup(service.control_path(), copies / "control.sqlite3")
                _sqlite_backup(service.partition_path(), copies / "partition.sqlite3")
                if (
                    service._control_state() != state
                    or service._control.read_publication_state(finalized.repository_id) != finalized
                    or service._control.next_journal_position()[1] != tip
                ):
                    raise OperatorError("conflict: live watermark changed during backup capture")
            participants: list[BackupParticipant] = []
            content_key = os.urandom(32)
            key_wrap_nonce = os.urandom(12)
            wrapped_key = AESGCM(recovery_key).encrypt(
                key_wrap_nonce, content_key, None
            )
            for participant_id in _ALLOWED_PARTICIPANTS:
                nonce = os.urandom(12)
                ciphertext = AESGCM(content_key).encrypt(
                    nonce, (copies / f"{participant_id}.sqlite3").read_bytes(), None,
                )
                snapshot_path = encrypted / f"{participant_id}.sqlite3.enc"
                _atomic_write(snapshot_path, ciphertext)
                participants.append(
                    BackupParticipant(
                        participant_id=participant_id,
                        kind="sqlite",
                        filename=snapshot_path.name,
                        sha256=hashlib.sha256(ciphertext).hexdigest(),
                        size_bytes=len(ciphertext),
                        nonce=base64.b64encode(nonce).decode("ascii"),
                    )
                )

            manifest = InstallationBackupManifest(
                manifest_version=2,
                installation_id=state.installation_id,
                created_at_unix=int(time.time()),
                control_revision=state.control_revision,
                eligibility_epoch=state.eligibility_epoch,
                runtime_revision=runtime_revision,
                memory_write_revision=finalized.vector.memory_write_revision,
                memory_data_revision=finalized.vector.memory_data_revision,
                publication_digest=finalized.payload_digest(),
                control_tip_digest=tip,
                participants=tuple(participants),
                wrapped_content_key=base64.b64encode(wrapped_key).decode("ascii"),
                key_wrap_nonce=base64.b64encode(key_wrap_nonce).decode("ascii"),
                manifest_digest="0" * 64,
                manifest_signature="0" * 128,
            )
            _verify_staged_backup(service, copies, manifest)
            digest = manifest.unsigned_digest()
            key_id = service._signer_key_id
            signature = service._signing.sign(key_id, _SIGNING_PURPOSE, digest)
            manifest = manifest.model_copy(
                update={"manifest_digest": digest, "manifest_signature": signature}
            )
            # Signed control recovery bundle + the independent anchor the
            # owner retains out of band (fresh-host restore material).
            bundle = {
                "installation_id": manifest.installation_id,
                "control_revision": manifest.control_revision,
                "manifest_digest": digest,
                "signer_fingerprint": service._signing.public_key_fingerprint(
                    key_id
                ),
                "participant_digests": {
                    p.participant_id: p.sha256 for p in participants
                },
                "created_at_unix": manifest.created_at_unix,
            }
            bundle_bytes = json.dumps(bundle, sort_keys=True).encode()
            bundle_signature = service._signing.sign(
                service._signer_key_id,
                _SIGNING_PURPOSE,
                hashlib.sha256(bundle_bytes).hexdigest(),
            )
            _atomic_write(
                encrypted / _RECOVERY_BUNDLE,
                json.dumps({**bundle, "signature": bundle_signature}, sort_keys=True).encode()
                + b"\n",
            )
            _atomic_write(
                encrypted / _RECOVERY_ANCHOR,
                json.dumps(
                    {
                        "installation_id": bundle["installation_id"],
                        "trusted_signer_fingerprint": bundle["signer_fingerprint"],
                        "control_revision": bundle["control_revision"],
                        "bundle_digest": hashlib.sha256(bundle_bytes).hexdigest(),
                    },
                    sort_keys=True,
                ).encode()
                + b"\n",
            )
            _atomic_write(
                encrypted / _BACKUP_MARKER,
                (manifest.model_dump_json() + "\n").encode(),
            )
            os.replace(encrypted, archive_root)
            _sync_directory(archive_root.parent)
        return manifest

    def verify_backup(
        self, *, archive_root: Path
    ) -> InstallationBackupManifest:
        marker_path = archive_root / _BACKUP_MARKER
        if not marker_path.is_file():
            raise OperatorError(
                "invalid_request: interrupted backup has no complete marker"
                " and is unusable"
            )
        manifest = InstallationBackupManifest.model_validate_json(
            marker_path.read_text()
        )
        service = self._operator._administration
        digest = manifest.unsigned_digest()
        if digest != manifest.manifest_digest:
            raise OperatorError("integrity_error: backup manifest digest mismatch")
        try:
            valid = service._signing.verify(
                service._signer_key_id,
                _SIGNING_PURPOSE,
                digest,
                manifest.manifest_signature,
            )
        except Exception as exc:  # noqa: BLE001 - any signer failure is a refusal
            raise OperatorError(
                "integrity_error: backup manifest signature unverifiable"
            ) from exc
        if not valid:
            raise OperatorError(
                "integrity_error: backup manifest signature mismatch"
                " (tampered or foreign archive)"
            )
        seen_ids: set[str] = set()
        for participant in manifest.participants:
            filename = _validate_participant(participant)
            if participant.participant_id in seen_ids:
                raise OperatorError(
                    f"invalid_request: duplicate participant id"
                    f" {participant.participant_id}"
                )
            if participant.participant_id not in _ALLOWED_PARTICIPANTS:
                raise OperatorError(
                    f"invalid_request: unknown participant"
                    f" {participant.participant_id}"
                )
            seen_ids.add(participant.participant_id)
            snapshot = archive_root / filename
            if not snapshot.is_file():
                raise OperatorError(
                    f"integrity_error: participant {participant.participant_id}"
                    " snapshot is missing"
                )
            if snapshot.stat().st_size != participant.size_bytes:
                raise OperatorError(
                    f"integrity_error: participant {participant.participant_id}"
                    " size mismatch"
                )
            if _sha256_file(snapshot) != participant.sha256:
                raise OperatorError(
                    f"integrity_error: participant {participant.participant_id}"
                    " digest mismatch"
                )
        if seen_ids != set(_ALLOWED_PARTICIPANTS):
            raise OperatorError("integrity_error: backup participant inventory is incomplete")
        return manifest

    def plan_restore(
        self,
        *,
        capability: OwnerCapability,
        archive_root: Path,
        data_loss_acknowledged: bool,
    ) -> RestorePlan:
        service = self._operator._administration
        require_owner_capability(service, capability)
        manifest = self.verify_backup(archive_root=archive_root)
        with service.verified_operation_context() as (current, finalized):
            if manifest.installation_id != current.installation_id:
                raise OperatorError("denied: backup belongs to a different installation")
            partition = service.partition()
            with partition.transaction(write=False) as connection:
                live_runtime_revision = partition.read_runtime_revision(connection)
            if not data_loss_acknowledged and (
                manifest.control_revision < current.control_revision
                or manifest.runtime_revision != live_runtime_revision
                or manifest.memory_write_revision != finalized.vector.memory_write_revision
                or manifest.memory_data_revision != finalized.vector.memory_data_revision
                or manifest.publication_digest not in (None, finalized.payload_digest())
            ):
                raise OperatorError(
                    "conflict: restoring a different backup watermark requires explicit data-loss acknowledgement"
                )
            plan = RestorePlan(
                archive_path=str(archive_root.resolve()),
                installation_id=manifest.installation_id,
                control_revision=manifest.control_revision,
                participant_count=len(manifest.participants),
                archive_manifest_digest=manifest.manifest_digest,
                expected_publication_digest=finalized.payload_digest(),
                expected_control_revision=current.control_revision,
                expected_control_tip_digest=service._control.next_journal_position()[1],
                data_loss_acknowledged=data_loss_acknowledged,
                plan_digest="0" * 64,
            )
            return plan.model_copy(update={"plan_digest": plan.unsigned_digest()})

    def apply_restore(
        self,
        *,
        capability: OwnerCapability,
        plan: RestorePlan,
        staging_root: Path,
        recovery_key: bytes,
    ) -> Path:
        service = self._operator._administration
        require_owner_capability(service, capability)
        if len(recovery_key) != 32:
            raise OperatorError(
                "invalid_request: recovery key must be exactly 32 bytes"
            )
        if plan.plan_digest != plan.unsigned_digest():
            raise OperatorError("conflict: restore plan digest does not match reviewed inputs")
        archive_root = Path(plan.archive_path)
        manifest = self.verify_backup(archive_root=archive_root)
        if (
            manifest.installation_id != plan.installation_id
            or manifest.manifest_digest != plan.archive_manifest_digest
            or manifest.control_revision != plan.control_revision
            or len(manifest.participants) != plan.participant_count
        ):
            raise OperatorError("conflict: plan and archive disagree")
        with service.verified_operation_context() as (state, finalized):
            self._require_restore_watermark(service, plan, state, finalized)
        if staging_root.is_symlink() or (
            staging_root.exists() and (not staging_root.is_dir() or any(staging_root.iterdir()))
        ):
            raise OperatorError("invalid_request: use a fresh staging directory")
        staging_root.parent.mkdir(parents=True, exist_ok=True)
        content_key = AESGCM(recovery_key).decrypt(
            base64.b64decode(manifest.key_wrap_nonce),
            base64.b64decode(manifest.wrapped_content_key),
            None,
        )
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=staging_root.parent) as scratch:
            staging = Path(scratch)
            for participant in manifest.participants:
                source = archive_root / _validate_participant(participant)
                ciphertext = source.read_bytes()
                if hashlib.sha256(ciphertext).hexdigest() != participant.sha256:
                    raise OperatorError("integrity_error: archive mutated during restore")
                plaintext = AESGCM(content_key).decrypt(
                    base64.b64decode(participant.nonce), ciphertext, None,
                )
                _atomic_write(staging / f"{participant.participant_id}.sqlite3", plaintext)
            source = _verify_staged_backup(service, staging, manifest)
            control_snapshot_digest = _snapshot_digest(staging / "control.sqlite3")
            partition_snapshot_digest = _snapshot_digest(staging / "partition.sqlite3")
            with service.verified_operation_context() as (state, finalized):
                self._require_restore_watermark(service, plan, state, finalized)
                if not plan.data_loss_acknowledged and source.publication.payload_digest() != finalized.payload_digest():
                    raise OperatorError("conflict: staged backup is older than the live publication")
                # Stage current suppression evidence rather than the older
                # control snapshot's view of eligible records.
                current_suppressions = service.installation_root / "control" / "suppressions"
                suppression_snapshot_digest = _suppression_snapshot_digest(current_suppressions)
                staging_suppressions = staging / "suppressions"
                if current_suppressions.is_dir():
                    staging_suppressions.mkdir(mode=0o700)
                    for journal in sorted(current_suppressions.glob("forget-*.json")):
                        _atomic_write(staging_suppressions / journal.name, journal.read_bytes())
                if _suppression_snapshot_digest(staging_suppressions) != suppression_snapshot_digest:
                    raise OperatorError("conflict: suppression evidence changed during restore staging")
                unsigned = RestoreStagingAttestation(
                    plan_digest=plan.plan_digest,
                    archive_manifest_digest=manifest.manifest_digest,
                    source_publication=source.publication,
                    source_control_tip_digest=source.control_tip_digest,
                    expected_publication_digest=plan.expected_publication_digest,
                    expected_control_revision=plan.expected_control_revision,
                    expected_control_tip_digest=plan.expected_control_tip_digest,
                    data_loss_acknowledged=plan.data_loss_acknowledged,
                    control_snapshot_digest=control_snapshot_digest,
                    partition_snapshot_digest=partition_snapshot_digest,
                    suppression_snapshot_digest=suppression_snapshot_digest,
                    signer_key_id=service._signer_key_id,
                    signature="0" * 128,
                )
                signature = service._signing.sign(
                    unsigned.signer_key_id, RESTORE_STAGING_SIGNATURE_PURPOSE, unsigned.unsigned_digest(),
                )
                attestation = unsigned.model_copy(update={"signature": signature})
                _atomic_write(staging / _RESTORE_ATTESTATION, (attestation.model_dump_json() + "\n").encode())
                os.replace(staging, staging_root)
                _sync_directory(staging_root.parent)
        return staging_root

    def verify_staged_restore(
        self, *, capability: OwnerCapability, plan: RestorePlan, staging_root: Path,
    ) -> RestoreStagingAttestation:
        """Revalidate inert staging against the reviewed plan and live watermark."""
        service = self._operator._administration
        require_owner_capability(service, capability)
        if plan.plan_digest != plan.unsigned_digest():
            raise OperatorError("conflict: restore plan digest does not match reviewed inputs")
        if staging_root.is_symlink() or not staging_root.is_dir():
            raise OperatorError("integrity_error: restore staging must be a directory")
        attestation_path = staging_root / _RESTORE_ATTESTATION
        if attestation_path.is_symlink() or not attestation_path.is_file():
            raise OperatorError("integrity_error: restore staging attestation is missing")
        try:
            attestation = RestoreStagingAttestation.model_validate_json(attestation_path.read_bytes())
            valid = attestation.signer_key_id == service._signer_key_id and service._signing.verify(
                attestation.signer_key_id,
                RESTORE_STAGING_SIGNATURE_PURPOSE,
                attestation.unsigned_digest(),
                attestation.signature,
            )
            if not valid:
                raise OperatorError("integrity_error: restore staging attestation signature is invalid")
            if (
                attestation.plan_digest != plan.plan_digest
                or attestation.archive_manifest_digest != plan.archive_manifest_digest
                or attestation.source_publication.installation_id != plan.installation_id
                or attestation.expected_publication_digest != plan.expected_publication_digest
                or attestation.expected_control_revision != plan.expected_control_revision
                or attestation.expected_control_tip_digest != plan.expected_control_tip_digest
                or attestation.data_loss_acknowledged != plan.data_loss_acknowledged
            ):
                raise OperatorError("conflict: staging does not match the reviewed restore plan")
            if (
                _snapshot_digest(staging_root / "control.sqlite3") != attestation.control_snapshot_digest
                or _snapshot_digest(staging_root / "partition.sqlite3") != attestation.partition_snapshot_digest
                or _suppression_snapshot_digest(staging_root / "suppressions") != attestation.suppression_snapshot_digest
            ):
                raise OperatorError("integrity_error: staged restore bytes differ from the attestation")
            with service.verified_operation_context() as (state, finalized):
                self._require_restore_watermark(service, plan, state, finalized)
                live_suppressions = service.installation_root / "control" / "suppressions"
                if _suppression_snapshot_digest(live_suppressions) != attestation.suppression_snapshot_digest:
                    raise OperatorError("conflict: live suppression watermark changed after staging")
        except (OSError, ValidationError) as exc:
            raise OperatorError("integrity_error: restore staging evidence could not be verified") from exc
        return attestation

    def activate_exact_current_restore(
        self, *, capability: OwnerCapability, plan: RestorePlan, staging_root: Path,
    ) -> PartitionGenerationSelector:
        """Relocate an attested exact-current snapshot under the owner barrier."""
        service = self._operator._administration
        attestation = self.verify_staged_restore(capability=capability, plan=plan, staging_root=staging_root)
        source = attestation.source_publication
        if source.payload_digest() != plan.expected_publication_digest:
            raise OperatorError("needs_reconciliation: older restore requires a new generation and delivery hold")
        partition_root = service.installation_root / "partition"
        generations = partition_root / "generations"
        if partition_root.is_symlink() or generations.is_symlink():
            raise OperatorError("integrity_error: generation storage must not use symlinks")
        generations.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".exact-current-restore-", dir=generations) as scratch:
            staged_copy = Path(scratch) / "partition.sqlite3"
            with (staging_root / "partition.sqlite3").open("rb") as original, staged_copy.open("xb") as clone:
                os.fchmod(clone.fileno(), 0o600)
                shutil.copyfileobj(original, clone, length=_CHUNK)
                clone.flush()
                os.fsync(clone.fileno())
            if _snapshot_digest(staged_copy) != attestation.partition_snapshot_digest:
                raise OperatorError("integrity_error: restore partition changed during selection preparation")

            with service.verified_operation_context() as (state, finalized):
                require_owner_capability(service, capability)
                self._require_restore_watermark(service, plan, state, finalized)
                if source != finalized or _suppression_snapshot_digest(
                    service.installation_root / "control" / "suppressions",
                ) != attestation.suppression_snapshot_digest:
                    raise OperatorError("conflict: restore selection no longer matches the live watermark")
                target = generations / finalized.data_generation_id
                unsigned = PartitionGenerationSelector(
                    installation_id=finalized.installation_id, repository_id=finalized.repository_id,
                    generation_id=finalized.data_generation_id, signature="0" * 128,
                )
                selector = unsigned.model_copy(update={"signature": service._signing.sign(
                    service._signer_key_id, PARTITION_GENERATION_SIGNATURE_PURPOSE, unsigned.unsigned_digest(),
                )})
                # A repeat request for an already selected exact snapshot has
                # no physical cutover to perform.
                active_path = service.partition_path()
                if active_path == target / "partition.sqlite3":
                    return selector
                with service.partition().manual_write_transaction():
                    if target.exists() or target.is_symlink():
                        existing = selected_partition_path(partition_root, finalized.data_generation_id)
                        if _snapshot_digest(existing) != attestation.partition_snapshot_digest:
                            raise OperatorError("conflict: occupied generation does not match reviewed staging")
                    else:
                        _sync_directory(Path(scratch))
                        os.rename(scratch, target)
                        _sync_directory(generations)
                    _atomic_write(
                        service.installation_root / "control" / PARTITION_GENERATION_SELECTOR,
                        (selector.model_dump_json() + "\n").encode(),
                    )
                    _sync_directory(service.installation_root / "control")
                    return selector

    @staticmethod
    def _require_restore_watermark(
        service: StorageAdministrationService,
        plan: RestorePlan,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> None:
        if state.installation_id != plan.installation_id:
            raise OperatorError("denied: restore plan belongs to another installation")
        if (
            finalized.payload_digest() != plan.expected_publication_digest
            or state.control_revision != plan.expected_control_revision
            or service._control.next_journal_position()[1] != plan.expected_control_tip_digest
        ):
            raise OperatorError("conflict: live restore watermark changed after planning")
        if state.mode != "read_only":
            raise OperatorError("conflict: restore staging requires read_only mode")


def _verify_staged_backup(
    service: StorageAdministrationService, staging: Path, manifest: InstallationBackupManifest,
) -> _VerifiedBackup:
    """Verify the decrypted pair against one signed backup watermark."""
    try:
        with (
            ControlDatabase(staging / "control.sqlite3", journal_verifier=service._verify_journal_signature) as control,
            PartitionDataRepository(staging / "partition.sqlite3") as partition,
        ):
            control.validate_journal()
            state = control.read_control_state()
            repository = f"{manifest.installation_id}:default-partition"
            finalized = control.read_publication_state(repository)
            control_tip_digest = control.next_journal_position()[1]
            trust_entries = control.list_trust_entries()
            trust_digest = (
                canonical_json_digest({"entries": [entry.model_dump_json() for entry in trust_entries]})
                if trust_entries else empty_pointer_set_digest()
            )
            if (
                state is None or finalized is None
                or state.installation_id != manifest.installation_id
                or finalized.installation_id != state.installation_id
                or finalized.repository_id != repository
                or state.mode != "read_only"
                or state.quarantined_reason is not None
                or state.control_revision != manifest.control_revision
                or state.eligibility_epoch != manifest.eligibility_epoch
                or finalized.eligibility_epoch != state.eligibility_epoch
                or finalized.trust_registry_digest != trust_digest
                or control.read_pending_intent(repository) is not None
                or manifest.control_tip_digest not in (None, control_tip_digest)
                or manifest.publication_digest not in (None, finalized.payload_digest())
            ):
                raise OperatorError("integrity_error: staged control does not match the backup watermark")
            with partition.transaction(write=False) as connection:
                row = partition.read_publication_row(connection)
                materialization = RuntimeMaterializationManifest(
                    catalogs=partition.compute_materialization_manifest(connection),
                )
                write_revision, data_revision = partition.read_revision_state(connection)
                if (
                    row is None or str(row["tuple_digest"]) != finalized.payload_digest()
                    or not service._matches_signed_publication(row, finalized)
                    or materialization.digest() != finalized.manifest_digest
                    or partition.read_runtime_revision(connection) != manifest.runtime_revision
                    or write_revision != manifest.memory_write_revision
                    or data_revision != manifest.memory_data_revision
                    or write_revision != finalized.vector.memory_write_revision
                    or data_revision != finalized.vector.memory_data_revision
                ):
                    raise OperatorError("integrity_error: staged partition does not match the backup watermark")
                verify_runtime_history(
                    connection, finalized=finalized,
                    verify=lambda purpose, digest, signature: service._verify_journal_signature(
                        service._signer_key_id, purpose, digest, signature,
                    ),
                )
            return _VerifiedBackup(publication=finalized, control_tip_digest=control_tip_digest)
    except (ControlJournalChainError, RuntimeJournalError, ValidationError, sqlite3.DatabaseError) as exc:
        raise OperatorError("integrity_error: staged backup verification failed") from exc


def boot_restored_installation(
    *,
    capability: OwnerCapability,
    staging_root: Path,
    anchor: dict[str, object],
    installation_root: Path,
    signing_keys_directory: Path,
) -> str:
    """Boot a fresh installation from a verified restore staging root.

    The design's fresh-host ceremony: the owner supplies the independently
    retained anchor (installation identity, trusted signer fingerprint,
    control revision, bundle digest) AND the out-of-band signing-key
    material — a data backup alone cannot recreate security authority, so
    the journal chain verifies against the owner-retained keys, never keys
    from the archive. The staged participants must carry the anchor's
    identity; current suppression state travels via the reapplied journals.
    """
    import shutil as _shutil

    from memorii.core.storage_administration.operator import OperatorError as _OpError
    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )

    if installation_root.exists() and any(installation_root.iterdir()):
        raise _OpError(
            "invalid_request: fresh-host boot requires an empty installation root"
        )
    staged_control = staging_root / "control.sqlite3"
    staged_partition = staging_root / "partition.sqlite3"
    for required in (staged_control, staged_partition):
        if not required.is_file():
            raise _OpError(
                f"integrity_error: staged participant missing: {required.name}"
            )
    try:
        with closing(sqlite3.connect(staged_partition.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            if PartitionDataRepository.requires_managed_restore(connection):
                raise _OpError("needs_reconciliation: managed runtime state requires a staged generation restore")
    except sqlite3.DatabaseError as exc:
        raise _OpError("integrity_error: staged partition runtime inventory cannot be read") from exc
    identity = str(anchor.get("installation_id", ""))
    if not identity:
        raise _OpError("invalid_request: anchor is missing the installation identity")
    control_root = installation_root / "control"
    partition_root = installation_root / "partition"
    control_root.mkdir(parents=True, exist_ok=True)
    partition_root.mkdir(parents=True, exist_ok=True)
    _shutil.copyfile(staged_control, control_root / "control.sqlite3")
    _shutil.copyfile(staged_partition, partition_root / "partition.sqlite3")
    os.chmod(control_root / "control.sqlite3", 0o600)
    os.chmod(partition_root / "partition.sqlite3", 0o600)
    # Owner-retained signing keys arrive out-of-band (never in the archive)
    # and become the fresh host's key material.
    keys_target = control_root / "keys"
    keys_target.mkdir(parents=True, exist_ok=True)
    os.chmod(keys_target, 0o700)
    for key_file in sorted(signing_keys_directory.glob("*.key")):
        _shutil.copyfile(key_file, keys_target / key_file.name)
        os.chmod(keys_target / key_file.name, 0o600)
    # Suppressions reapplied into staging travel with the boot so revoked
    # evidence stays revoked on the fresh host.
    staged_suppressions = staging_root / "suppressions"
    if staged_suppressions.is_dir():
        target = control_root / "suppressions"
        target.mkdir(parents=True, exist_ok=True)
        for journal in staged_suppressions.glob("forget-*.json"):
            _shutil.copyfile(journal, target / journal.name)
    # The booted control state must resolve as a coherent installation.
    service = StorageAdministrationService(installation_root)
    try:
        state = service._control_state()
        if state.installation_id != identity:
            raise _OpError(
                "integrity_error: staged control identity does not match the anchor"
            )
    finally:
        service.close()
    del capability
    return identity


__all__ = [
    "BackupParticipant",
    "BackupRestoreOperator",
    "InstallationBackupManifest",
    "RestorePlan",
    "RestoreStagingAttestation",
    "boot_restored_installation",
]
