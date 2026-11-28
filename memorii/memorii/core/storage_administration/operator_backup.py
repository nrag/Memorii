"""Backup/restore operator controls over one installation.

Owner-authorized, plan-governed operations matching the design contract:
Backup create pins control and partition SQLite snapshots under the
acknowledged read_only barrier and copies them through the online backup API. It verifies the
pair against the captured signed tuple and control journal tip, encrypts
participants with a wrapped content key, and atomically publishes the archive.
Restore plans bind the verified archive and the current live watermark.
Staging verifies the decrypted pair before copying current suppression evidence
and publishing an inert, signed staging directory.
"""
from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
    model_validator,
)

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import (
    RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
    BatchPosition,
    InstallationControlJournalEntry,
    InstallationControlState,
    InstallationGenerationChangeIntent,
    RuntimeHistoryInterval,
    RuntimeMaterializationManifest,
    RuntimePublicationState,
    canonical_json_digest,
    empty_pointer_set_digest,
)
from memorii.core.persistence.key_owner import (
    PARTITION_GENERATION_SIGNATURE_PURPOSE,
    RESTORE_STAGING_SIGNATURE_PURPOSE,
    LocalSigningKeyOwner,
)
from memorii.core.persistence.managed_delivery import DeliveryRestoreHold
from memorii.core.persistence.runtime_api import convert_legacy_outbox_record
from memorii.core.persistence.runtime_journal import RuntimeJournalError, append_runtime_changes, verify_runtime_history
from memorii.core.storage_administration.backup_cipher import decrypt_backup_participant, encrypt_backup_participant
from memorii.core.storage_administration.generation_selection import (
    PARTITION_GENERATION_SELECTOR,
    PartitionGenerationSelector,
    read_partition_generation_selector,
    selected_partition_path,
)
from memorii.core.storage_administration.operator import (
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    require_owner_capability,
)
from memorii.core.storage_administration.service import StorageAdministrationError, StorageAdministrationService
from memorii.stores.sqlite.control import ControlDatabase, ControlJournalChainError, ControlStateError
from memorii.stores.sqlite.partition import (
    LEGACY_RUNTIME_UPGRADE_SCHEMA_VERSION,
    RAW_MEMORY_PAYLOAD_SCHEMA_VERSION,
    PartitionDataRepository,
)
from memorii.stores.sqlite.private_storage import (
    ensure_private_directory,
    open_private_file,
    prepare_installation_root,
    prepare_private_sqlite,
    require_private_directory,
    require_private_sqlite,
)
from memorii.stores.sqlite.raw_memory_payloads import RawPayloadFramingError, validate_upgrade_framing

_BACKUP_MARKER = "backup-complete.json"
_RECOVERY_BUNDLE = "control-recovery-bundle.json"
_RECOVERY_ANCHOR = "recovery-anchor.json"
_RESTORE_ATTESTATION = "restore-staging-attestation.json"
_SIGNING_PURPOSE = "memorii.installation-backup-manifest.v1"
_CHUNK = 1 << 20
_SQLITE_BACKUP_TIMEOUT_SECONDS = 300
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


class RestoreInventoryDelta(BaseModel):
    identical: int = Field(ge=0)
    live_only: int = Field(ge=0)
    staged_only: int = Field(ge=0)
    changed: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RawPayloadUpgradePreview(BaseModel):
    """Reviewed physical format and workspace inputs for an opt-in upgrade."""

    source_schema_version: int = Field(ge=4, le=LEGACY_RUNTIME_UPGRADE_SCHEMA_VERSION)
    target_schema_version: Literal[8] = RAW_MEMORY_PAYLOAD_SCHEMA_VERSION
    source_partition_bytes: int = Field(gt=0)
    estimated_workspace_bytes: int = Field(gt=0)
    available_workspace_bytes: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RestoreStagePreview(BaseModel):
    """Evidence about verified catalog differences for the owner's review."""

    plan_digest: _Digest
    attestation_digest: _Digest
    live_publication_digest: _Digest
    staged_publication_digest: _Digest
    command_receipts: RestoreInventoryDelta
    target_receipts: RestoreInventoryDelta
    outbox_deliveries: RestoreInventoryDelta
    writeback_decisions: RestoreInventoryDelta
    raw_payload_upgrade: RawPayloadUpgradePreview | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_serializer(mode="wrap")
    def serialize_review(self, serialize: SerializerFunctionWrapHandler) -> dict[str, object]:
        payload = serialize(self)
        if self.raw_payload_upgrade is None:
            payload.pop("raw_payload_upgrade", None)
        return payload

    def digest(self) -> str:
        # Free space is a point-in-time diagnostic, not a reviewed input.
        return _canonical_digest(
            self.model_dump(mode="json", exclude={"raw_payload_upgrade": {"available_workspace_bytes"}})
        )


def _restore_inventory_delta(
    live: Iterator[tuple[tuple[str, ...], str]], staged: Iterator[tuple[tuple[str, ...], str]],
) -> RestoreInventoryDelta:
    identical = live_only = staged_only = changed = 0
    current, restored = next(live, None), next(staged, None)
    while current is not None or restored is not None:
        if current is not None and (restored is None or current[0] < restored[0]):
            live_only += 1
            current = next(live, None)
        elif restored is not None and (current is None or restored[0] < current[0]):
            staged_only += 1
            restored = next(staged, None)
        else:
            assert current is not None and restored is not None
            if current[1] == restored[1]:
                identical += 1
            else:
                changed += 1
            current, restored = next(live, None), next(staged, None)
    return RestoreInventoryDelta(identical=identical, live_only=live_only, staged_only=staged_only, changed=changed)


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
    _require_snapshot_without_sidecars(path)
    if path.is_symlink() or not path.is_file():
        raise OperatorError("integrity_error: staged SQLite snapshot must be a regular file")
    require_private_sqlite(path)
    return _sha256_file(path)


def _require_snapshot_without_sidecars(path: Path) -> None:
    for extension in ("-wal", "-shm", "-journal"):
        sidecar = path.with_name(path.name + extension)
        if sidecar.is_symlink() or sidecar.exists():
            raise OperatorError("integrity_error: staged SQLite snapshot contains a live sidecar")


def _copy_private_restore_media(source: Path, destination: Path) -> None:
    with open_private_file(source) as original:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            shutil.copyfileobj(original, output, length=_CHUNK)
            output.flush()
            os.fsync(output.fileno())


def _copy_attested_partition(source: Path, target: Path, expected_digest: str) -> None:
    """Copy only the immutable SQLite bytes named by the attestation."""
    _copy_private_restore_media(source, target)
    if _snapshot_digest(target) != expected_digest:
        raise OperatorError("integrity_error: restore partition changed during copy")


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


def backup_lifetime_guard(service: StorageAdministrationService, *, exclusive: bool):
    # Erasure takes this before the publication fence, so it cannot finish
    # while a backup still retains readers or plaintext outside that fence.
    return locked_file(
        service.installation_root / "control" / ".backup-lifetime.lock",
        exclusive=exclusive, private=True,
    )


@contextmanager
def _open_backup_snapshot(path: Path) -> Iterator[sqlite3.Connection]:
    require_private_directory(path.parent)
    require_private_sqlite(path)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise OperatorError("unavailable: online backup requires WAL snapshots for both participants")
        connection.execute("BEGIN")
        yield connection


def _sqlite_backup(source: sqlite3.Connection, destination: Path) -> None:
    """Copy a transaction already pinned by a verified read on this handle."""
    deadline = time.monotonic() + _SQLITE_BACKUP_TIMEOUT_SECONDS

    def check_deadline(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() >= deadline:
            raise OperatorError("unavailable: pinned SQLite backup copy deadline exceeded")

    if not source.in_transaction:
        raise OperatorError("integrity_error: backup source is missing its pinned read transaction")
    prepare_private_sqlite(destination)
    with closing(sqlite3.connect(str(destination))) as copy:
        source.backup(copy, pages=512, progress=check_deadline, sleep=0.01)


@dataclass(frozen=True)
class _BackupAuthority:
    state: InstallationControlState
    publication: RuntimePublicationState
    journal_tip: str
    runtime_revision: int
    control_path: Path
    partition_path: Path
    control_identity: tuple[int, int]
    partition_identity: tuple[int, int]
    suppression_watermark: tuple[str, str]
    signer_fingerprint: str


def _backup_suppression_watermark(service: StorageAdministrationService) -> tuple[str, str]:
    control = service.installation_root / "control"
    return (
        _suppression_snapshot_digest(control / "suppressions"),
        _suppression_snapshot_digest(control / "suppressions-archive"),
    )


def _pin_backup_sources(
    service: StorageAdministrationService,
    state: InstallationControlState,
    finalized: RuntimePublicationState,
    stack: ExitStack,
) -> tuple[_BackupAuthority, sqlite3.Connection, sqlite3.Connection]:
    position, tip = service._control.next_journal_position()
    control_path = service.control_path()
    partition = service.partition()
    partition_path = service.partition_path()
    control_identity = service._partition_file_identity(control_path)
    partition_identity = service._partition_file_identity(partition_path)
    control = stack.enter_context(_open_backup_snapshot(control_path))
    data = stack.enter_context(_open_backup_snapshot(partition_path))

    # BEGIN alone does not establish a SQLite read snapshot. Read the exact
    # rows that bind each transaction while holding the publication fence.
    selected = control.execute(
        "SELECT state_json FROM publication_states WHERE repository_id = ?", (finalized.repository_id,),
    ).fetchone()
    control_row = control.execute("SELECT state_json FROM installation_control WHERE id = 1").fetchone()
    journal = control.execute("SELECT entry_json FROM control_journal ORDER BY revision DESC LIMIT 1").fetchone()
    if journal is None:
        raise OperatorError("integrity_error: pinned control snapshot is missing its journal tip")
    entry = InstallationControlJournalEntry.model_validate_json(journal[0])
    row = partition.read_publication_row(data)
    if (
        selected is None or RuntimePublicationState.model_validate_json(selected[0]) != finalized
        or control_row is None or InstallationControlState.model_validate_json(control_row[0]) != state
        or (entry.revision + 1, entry.entry_digest) != (position, tip)
        or row is None or row["tuple_digest"] != finalized.payload_digest()
        or not service._matches_signed_publication(row, finalized)
        or partition.read_revision_state(data) != (
            finalized.vector.memory_write_revision, finalized.vector.memory_data_revision,
        )
        or service._partition_file_identity(control_path) != control_identity
        or service._partition_file_identity(partition_path) != partition_identity
    ):
        raise OperatorError("integrity_error: pinned backup snapshots differ from the selected watermark")
    authority = _BackupAuthority(
        state=state, publication=finalized, journal_tip=tip,
        runtime_revision=partition.read_runtime_revision(data),
        control_path=control_path, partition_path=partition_path,
        control_identity=control_identity, partition_identity=partition_identity,
        suppression_watermark=_backup_suppression_watermark(service),
        signer_fingerprint=service._signing.public_key_fingerprint(service._signer_key_id),
    )
    return authority, control, data


def _require_backup_authority(
    service: StorageAdministrationService, capability: OwnerCapability, authority: _BackupAuthority,
) -> None:
    state = service._require_operational()
    current = service._control.read_publication_state(authority.publication.repository_id)
    if (
        state.installation_id != authority.state.installation_id
        or state.mode not in ("active", "read_only")
        or state.control_revision < authority.state.control_revision
        or state.eligibility_epoch != authority.state.eligibility_epoch
        or state.pending_epoch_increments != authority.state.pending_epoch_increments
        or current is None
        or current.installation_id != state.installation_id
        or current.repository_id != authority.publication.repository_id
        or current.data_generation_id != authority.publication.data_generation_id
        or current.vector.partition_ordinal < authority.publication.vector.partition_ordinal
        or (
            current.vector.partition_ordinal == authority.publication.vector.partition_ordinal
            and current != authority.publication
        )
        or current.eligibility_epoch != state.eligibility_epoch
        or current.trust_registry_digest != authority.publication.trust_registry_digest
        or service._control.read_pending_intent(authority.publication.repository_id) is not None
        or not service._signing.has_key(service._signer_key_id)
        or not service._signing.verify(
            service._signer_key_id, RUNTIME_PUBLICATION_SIGNATURE_PURPOSE, current.payload_digest(), current.signature,
        )
        or service.control_path() != authority.control_path
        # Resolve the live selector, including refusal of a prepared
        # generation change whose selector still points to the old file.
        or service.partition_path() != authority.partition_path
        or service._partition_file_identity(authority.control_path) != authority.control_identity
        or service._partition_file_identity(authority.partition_path) != authority.partition_identity
        or _backup_suppression_watermark(service) != authority.suppression_watermark
    ):
        raise OperatorError("conflict: backup authority changed before archive publication")
    # The service's signer caches the private key. Refresh from the current
    # key owner before publishing an archive signed with that cached handle.
    signer = LocalSigningKeyOwner(service.installation_root / "control" / "keys")
    if signer.public_key_fingerprint(service._signer_key_id) != authority.signer_fingerprint:
        raise OperatorError("conflict: backup authority changed before archive publication")
    require_owner_capability(service, capability)


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
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
        with (
            backup_lifetime_guard(service, exclusive=False),
            tempfile.TemporaryDirectory(prefix=".backup-", dir=archive_root.parent) as scratch,
            tempfile.TemporaryDirectory(
                prefix=".backup-plaintext-", dir=service.installation_root / "partition",
            ) as plaintext,
        ):
            # An abrupt process exit may leave SQLite plaintext behind. Keep
            # it in the tree the installation's erasure operation owns.
            copies = Path(plaintext)
            require_private_directory(copies)
            encrypted = Path(scratch) / "encrypted"
            ensure_private_directory(encrypted)
            try:
                with ExitStack() as snapshots:
                    with service.verified_operation_context() as (state, finalized):
                        require_owner_capability(service, capability)
                        if state.mode != "read_only":
                            raise OperatorError(
                                "conflict: backups require the acknowledged exclusive barrier"
                                " (change mode to read_only first)"
                            )
                        authority, control, partition = _pin_backup_sources(service, state, finalized, snapshots)
                    _sqlite_backup(control, copies / "control.sqlite3")
                    _sqlite_backup(partition, copies / "partition.sqlite3")
            except (
                ControlJournalChainError, ControlStateError, OSError, sqlite3.Error,
                StorageAdministrationError, ValidationError,
            ) as exc:
                raise OperatorError("unavailable: could not capture pinned backup snapshots") from exc
            participants: list[BackupParticipant] = []
            content_key = os.urandom(32)
            key_wrap_nonce = os.urandom(12)
            wrapped_key = AESGCM(recovery_key).encrypt(
                key_wrap_nonce, content_key, None
            )
            for participant_id in _ALLOWED_PARTICIPANTS:
                nonce = os.urandom(12)
                snapshot_path = encrypted / f"{participant_id}.sqlite3.enc"
                digest, size = encrypt_backup_participant(
                    copies / f"{participant_id}.sqlite3", snapshot_path, key=content_key, nonce=nonce,
                )
                participants.append(
                    BackupParticipant(
                        participant_id=participant_id,
                        kind="sqlite",
                        filename=snapshot_path.name,
                        sha256=digest,
                        size_bytes=size,
                        nonce=base64.b64encode(nonce).decode("ascii"),
                    )
                )

            manifest = InstallationBackupManifest(
                manifest_version=2,
                installation_id=state.installation_id,
                created_at_unix=int(time.time()),
                control_revision=state.control_revision,
                eligibility_epoch=state.eligibility_epoch,
                runtime_revision=authority.runtime_revision,
                memory_write_revision=finalized.vector.memory_write_revision,
                memory_data_revision=finalized.vector.memory_data_revision,
                publication_digest=finalized.payload_digest(),
                control_tip_digest=authority.journal_tip,
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
            try:
                with service._publication_fence():
                    _require_backup_authority(service, capability, authority)
                    os.replace(encrypted, archive_root)
                    _sync_directory(archive_root.parent)
            except (
                ControlJournalChainError, ControlStateError, PermissionError,
                StorageAdministrationError, ValidationError,
            ) as exc:
                raise OperatorError("conflict: backup authority changed before archive publication") from exc
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
            require_private_directory(staging)
            for participant in manifest.participants:
                source = archive_root / _validate_participant(participant)
                decrypt_backup_participant(
                    source, staging / f"{participant.participant_id}.sqlite3",
                    key=content_key, nonce=base64.b64decode(participant.nonce),
                    expected_digest=participant.sha256, expected_size=participant.size_bytes,
                )
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
            require_private_directory(staging_root)
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
                self._require_staging_suppression(service, attestation)
        except StorageAdministrationError as exc:
            raise OperatorError("unavailable: live restore watermark could not be verified") from exc
        except (OSError, ValidationError) as exc:
            raise OperatorError("integrity_error: restore staging evidence could not be verified") from exc
        return attestation

    def preview_staged_restore(
        self, *, capability: OwnerCapability, plan: RestorePlan, staging_root: Path, raw_payloads: bool = False,
    ) -> RestoreStagePreview:
        """Compare attested staging and current catalogs without changing either."""
        service = self._operator._administration
        attestation = self.verify_staged_restore(capability=capability, plan=plan, staging_root=staging_root)
        raw_upgrade = None
        try:
            with tempfile.TemporaryDirectory(prefix="memorii-restore-preview-") as scratch:
                snapshot = Path(scratch) / "partition.sqlite3"
                _copy_attested_partition(
                    staging_root / "partition.sqlite3", snapshot, attestation.partition_snapshot_digest,
                )
                uri = snapshot.as_uri() + "?mode=ro&immutable=1"
                if raw_payloads:
                    if attestation.source_publication.payload_digest() != plan.expected_publication_digest:
                        raise OperatorError("conflict: raw payload upgrade requires an exact-current staged backup")
                    with closing(sqlite3.connect(uri, uri=True)) as staged:
                        staged.row_factory = sqlite3.Row
                        version = PartitionDataRepository.read_schema_version(staged)
                        if not 4 <= version <= LEGACY_RUNTIME_UPGRADE_SCHEMA_VERSION:
                            raise OperatorError(
                                "unsupported_configuration: raw payload upgrade requires storage format 4 through 7"
                            )
                        validate_upgrade_framing(staged)
                    source_size = snapshot.stat().st_size
                    # Working copy plus transient conversion and compaction pages.
                    raw_upgrade = RawPayloadUpgradePreview(
                        source_schema_version=version,
                        source_partition_bytes=source_size,
                        estimated_workspace_bytes=3 * source_size,
                        available_workspace_bytes=shutil.disk_usage(service.installation_root / "partition").free,
                    )
                with service.verified_operation_context() as (state, finalized):
                    require_owner_capability(service, capability)
                    self._require_restore_watermark(service, plan, state, finalized)
                    self._require_staging_suppression(service, attestation)
                    deltas = self._preview_inventory(service, uri)
        except StorageAdministrationError as exc:
            raise OperatorError("unavailable: live restore watermark could not be verified") from exc
        except RawPayloadFramingError as exc:
            raise OperatorError(f"unsupported_configuration: {exc}") from exc
        except (OSError, sqlite3.DatabaseError) as exc:
            raise OperatorError("integrity_error: restore preview inventory could not be read") from exc
        return RestoreStagePreview(
            plan_digest=plan.plan_digest,
            attestation_digest=attestation.unsigned_digest(),
            live_publication_digest=finalized.payload_digest(),
            staged_publication_digest=attestation.source_publication.payload_digest(),
            command_receipts=deltas["runtime_command_receipts"],
            target_receipts=deltas["runtime_target_receipts"],
            outbox_deliveries=deltas["runtime_outbox_deliveries"],
            writeback_decisions=deltas["writeback_decisions"],
            raw_payload_upgrade=raw_upgrade,
        )

    @staticmethod
    def _preview_inventory(service: StorageAdministrationService, uri: str) -> dict[str, RestoreInventoryDelta]:
        with closing(sqlite3.connect(uri, uri=True)) as staged, service.partition().transaction(write=False) as live:
            rows = PartitionDataRepository.restore_inventory_rows
            return {
                name: _restore_inventory_delta(rows(live, name), rows(staged, name))
                for name in (
                    "runtime_command_receipts", "runtime_target_receipts",
                    "runtime_outbox_deliveries", "writeback_decisions",
                )
            }

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
        ensure_private_directory(generations)
        with tempfile.TemporaryDirectory(prefix=".exact-current-restore-", dir=generations) as scratch:
            staged_copy = Path(scratch) / "partition.sqlite3"
            _copy_attested_partition(
                staging_root / "partition.sqlite3", staged_copy, attestation.partition_snapshot_digest,
            )

            with service.verified_operation_context() as (state, finalized):
                require_owner_capability(service, capability)
                self._require_restore_watermark(service, plan, state, finalized)
                if source != finalized:
                    raise OperatorError("conflict: restore selection no longer matches the live watermark")
                self._require_staging_suppression(service, attestation)
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

    def activate_older_restore(
        self,
        *,
        capability: OwnerCapability,
        plan: RestorePlan,
        staging_root: Path,
        preview_digest: str,
    ) -> InstallationGenerationChangeIntent:
        """Select a separately verified generation with the old delivery authority held."""
        if not plan.data_loss_acknowledged:
            raise OperatorError("conflict: older restore requires the reviewed data-loss acknowledgement")
        return self._activate_staged_generation(
            capability=capability, plan=plan, staging_root=staging_root, preview_digest=preview_digest,
            operation="restore",
        )

    def upgrade_current_runtime(
        self,
        *,
        capability: OwnerCapability,
        plan: RestorePlan,
        staging_root: Path,
        preview_digest: str,
        raw_payloads: bool = False,
    ) -> InstallationGenerationChangeIntent:
        """Upgrade an exact-current signed runtime copy under a reviewed generation cutover."""
        return self._activate_staged_generation(
            capability=capability, plan=plan, staging_root=staging_root, preview_digest=preview_digest,
            operation="migrate", raw_payloads=raw_payloads,
        )

    def _activate_staged_generation(
        self,
        *,
        capability: OwnerCapability,
        plan: RestorePlan,
        staging_root: Path,
        preview_digest: str,
        operation: Literal["restore", "migrate"],
        raw_payloads: bool = False,
    ) -> InstallationGenerationChangeIntent:
        service = self._operator._administration
        require_owner_capability(service, capability)
        if plan.unsigned_digest() != plan.plan_digest:
            raise OperatorError("conflict: generation change requires the reviewed plan digest")
        with service.verified_operation_context() as (_state, finalized):
            prior = service._control.read_generation_change(finalized.repository_id)
            if (
                prior is not None and prior.operation == operation and prior.phase == "finalized"
                and prior.preview_digest == preview_digest
                and prior.old_publication.payload_digest() == plan.expected_publication_digest
                and prior.expected_control_revision == plan.expected_control_revision
                and prior.candidate_publication.data_generation_id == finalized.data_generation_id
            ):
                if operation == "migrate":
                    with service.partition().transaction(write=False) as connection:
                        current_raw = (
                            service.partition().read_schema_version(connection) == RAW_MEMORY_PAYLOAD_SCHEMA_VERSION
                        )
                    if raw_payloads != current_raw:
                        raise OperatorError("conflict: generation change requires the exact reviewed storage format")
                return prior
        preview = self.preview_staged_restore(
            capability=capability, plan=plan, staging_root=staging_root, raw_payloads=raw_payloads,
        )
        is_current = preview.live_publication_digest == preview.staged_publication_digest
        if preview.digest() != preview_digest or is_current != (operation == "migrate"):
            raise OperatorError("conflict: generation change requires the exact reviewed preview for this operation")
        attestation = self.verify_staged_restore(capability=capability, plan=plan, staging_root=staging_root)
        if preview.attestation_digest != attestation.unsigned_digest():
            raise OperatorError("conflict: restore staging changed after preview")
        partition_root = service.installation_root / "partition"
        generations = partition_root / "generations"
        if partition_root.is_symlink() or generations.is_symlink():
            raise OperatorError("integrity_error: generation storage must not use symlinks")
        ensure_private_directory(generations)
        try:
            if preview.raw_payload_upgrade is not None:
                size = preview.raw_payload_upgrade.source_partition_bytes
                available = shutil.disk_usage(generations).free
                if available < size:
                    raise OperatorError(
                        f"resource_exhausted: staged partition copy requires {size} bytes, available {available}"
                    )
            with tempfile.TemporaryDirectory(prefix=".older-restore-", dir=generations) as scratch:
                working = Path(scratch) / "partition.sqlite3"
                _copy_attested_partition(staging_root / "partition.sqlite3", working, attestation.partition_snapshot_digest)
                with service.verified_operation_context() as (state, finalized):
                    require_owner_capability(service, capability)
                    self._require_restore_watermark(service, plan, state, finalized)
                    self._require_staging_suppression(service, attestation)
                    target = self._prepare_restored_generation(
                        working, source=attestation.source_publication, live=finalized, preview_digest=preview_digest,
                        require_upgrade=operation == "migrate", raw_payloads=raw_payloads,
                    )
                    old_selector = read_partition_generation_selector(service.installation_root / "control")
                    intent = InstallationGenerationChangeIntent(
                        intent_id=preview_digest, operation=operation,
                        old_publication=finalized, candidate_publication=target,
                        old_named_selector=old_selector is not None,
                        expected_control_revision=state.control_revision, preview_digest=preview_digest,
                        data_loss_acknowledged=plan.data_loss_acknowledged,
                    )
                    return self._select_replacement(generations, working.parent, intent)
        except RawPayloadFramingError as exc:
            raise OperatorError(f"unsupported_configuration: {exc}") from exc
        except (OSError, sqlite3.DatabaseError) as exc:
            if raw_payloads and (
                (isinstance(exc, OSError) and exc.errno == errno.ENOSPC)
                or getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL
            ):
                raise OperatorError("resource_exhausted: raw payload upgrade ran out of staging space") from exc
            raise OperatorError("integrity_error: older restore candidate could not be prepared or published") from exc
        except (ValidationError, RuntimeJournalError) as exc:
            raise OperatorError("integrity_error: older restore candidate could not be prepared or published") from exc

    def _prepare_restored_generation(
        self,
        working: Path,
        *,
        source: RuntimePublicationState,
        live: RuntimePublicationState,
        preview_digest: str,
        require_upgrade: bool,
        raw_payloads: bool,
    ) -> RuntimePublicationState:
        service = self._operator._administration
        generation_id = uuid.uuid4().hex
        ancestry = source.runtime_history_ancestry
        source_head = source.vector.runtime_position
        if isinstance(source_head, BatchPosition) and (not ancestry or ancestry[-1].through_position != source_head):
            ancestry = (*ancestry, RuntimeHistoryInterval(
                generation_id=source.data_generation_id, through_position=source_head,
            ))
        hold = DeliveryRestoreHold(
            hold_id=preview_digest, installation_id=live.installation_id, partition_id=live.repository_id,
            restored_generation_id=generation_id, source_generation_id=source.data_generation_id,
            source_publication_digest=source.payload_digest(), live_publication_digest=live.payload_digest(),
            preview_digest=preview_digest,
        )
        with (
            PartitionDataRepository(working, require_existing=True, protected_storage_root=working.parent) as staged,
            staged.transaction(write=True) as connection,
        ):
            upgrade_needed = staged.read_schema_version(connection) < LEGACY_RUNTIME_UPGRADE_SCHEMA_VERSION
            staged.stage_runtime_recovery_upgrade(connection, source_digest=source.payload_digest())
            if raw_payloads:
                staged.stage_raw_memory_payload_upgrade(connection)
                upgrade_needed = True
            previous = source.model_copy(update={"data_generation_id": generation_id})
            revision = staged.bump_runtime_revision(connection)
            with staged.capture_runtime_rows(connection) as changes:
                staged.insert_delivery_restore_hold(connection, hold_id=hold.hold_id, record_json=hold.model_dump_json())
                for key, raw in tuple(staged.restore_inventory_rows(connection, "runtime_outbox_deliveries")):
                    legacy = convert_legacy_outbox_record(key[0], raw)
                    if legacy is not None and legacy.model_dump_json() != raw:
                        upgrade_needed = True
                        staged.upsert_runtime_row(
                            connection, table="runtime_outbox_deliveries", keys=("delivery_id",),
                            values=key, record_json=legacy.model_dump_json(),
                        )
            if require_upgrade and not upgrade_needed:
                raise OperatorError("conflict: current generation already has the recovery format and typed outbox")
            head = append_runtime_changes(
                connection, changes=changes, previous=previous, runtime_revision=revision,
                sign=lambda purpose, digest: service._signing.sign(service._signer_key_id, purpose, digest),
            )
            manifest = RuntimeMaterializationManifest(catalogs=staged.compute_materialization_manifest(connection))
            ordinal = live.vector.partition_ordinal + 1
            publication = service._sign_state(RuntimePublicationState(
                installation_id=live.installation_id, repository_id=live.repository_id,
                data_generation_id=generation_id, position=BatchPosition(sequence=ordinal, digest=manifest.digest()),
                manifest_digest=manifest.digest(), trust_registry_digest=live.trust_registry_digest,
                eligibility_epoch=live.eligibility_epoch,
                vector=source.vector.model_copy(update={"partition_ordinal": ordinal, "runtime_position": head}),
                runtime_history_ancestry=ancestry, signature="0" * 128,
            ))
            staged.write_publication_row(
                connection, ordinal=ordinal, position_kind="batch", position_sequence=ordinal,
                position_digest=manifest.digest(), tuple_digest=publication.payload_digest(),
                generation_id=generation_id, vector_json=publication.vector.model_dump_json(),
                manifest_digest=manifest.digest(),
            )
            if not service._matches_materialization(connection, publication, partition=staged):
                raise OperatorError("integrity_error: restored generation does not replay to its signed tuple")
        if raw_payloads:
            with closing(sqlite3.connect(working)) as connection:
                connection.execute("VACUUM")
            with (
                PartitionDataRepository(working, require_existing=True, protected_storage_root=working.parent) as compacted,
                compacted.transaction(write=False) as connection,
            ):
                if not service._matches_materialization(connection, publication, partition=compacted):
                    raise OperatorError("integrity_error: compacted generation does not replay to its signed tuple")
        _snapshot_digest(working)
        with working.open("rb") as database:
            os.fsync(database.fileno())
        return publication

    def _select_replacement(
        self, generations: Path, working: Path, intent: InstallationGenerationChangeIntent,
    ) -> InstallationGenerationChangeIntent:
        service = self._operator._administration
        publication = intent.candidate_publication
        unsigned = PartitionGenerationSelector(
            installation_id=publication.installation_id, repository_id=publication.repository_id,
            generation_id=publication.data_generation_id, signature="0" * 128,
        )
        selector = unsigned.model_copy(update={"signature": service._signing.sign(
            service._signer_key_id, PARTITION_GENERATION_SIGNATURE_PURPOSE, unsigned.unsigned_digest(),
        )})
        with service.partition().manual_write_transaction():
            _sync_directory(working)
            os.rename(working, generations / publication.data_generation_id)
            _sync_directory(generations)
            service._control.write_generation_change(
                intent,
                service._journal_entry(
                    operation="generation_change_prepared",
                    before_digest=intent.old_publication.payload_digest(), after_digest=intent.binding_digest(),
                ),
            )
            _atomic_write(
                service.installation_root / "control" / PARTITION_GENERATION_SELECTOR,
                (selector.model_dump_json() + "\n").encode(),
            )
            _sync_directory(service.installation_root / "control")
        outcome = service._recover_generation_change(intent)
        if outcome.disposition != "finalized":
            raise OperatorError("integrity_error: restored generation did not finalize")
        return intent.model_copy(update={"phase": "finalized"})

    @staticmethod
    def _require_staging_suppression(
        service: StorageAdministrationService, attestation: RestoreStagingAttestation,
    ) -> None:
        live_suppressions = service.installation_root / "control" / "suppressions"
        if _suppression_snapshot_digest(live_suppressions) != attestation.suppression_snapshot_digest:
            raise OperatorError("conflict: live suppression watermark changed after staging")

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
            PartitionDataRepository(staging / "partition.sqlite3", protected_storage_root=staging) as partition,
        ):
            control.validate_journal()
            state = control.read_control_state()
            repository = f"{manifest.installation_id}:default-partition"
            finalized = control.read_publication_state(repository)
            control_tip_digest = control.next_journal_position()[1]
            trust_entries = control.list_trust_entries()
            generation_change = control.read_generation_change(repository)
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
                or (generation_change is not None and generation_change.phase == "prepared")
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
                    checkpoint_signer_key_id=service._signer_key_id,
                    checkpoint_signer_fingerprint=(
                        service._signing.public_key_fingerprint(service._signer_key_id)
                        if finalized.checkpoint_digest is not None else None
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
    if installation_root.is_symlink() or (installation_root.exists() and any(installation_root.iterdir())):
        raise OperatorError(
            "invalid_request: fresh-host boot requires an empty installation root"
        )
    identity = str(anchor.get("installation_id", ""))
    if not identity:
        raise OperatorError("invalid_request: anchor is missing the installation identity")
    try:
        require_private_directory(staging_root)
        require_private_directory(signing_keys_directory)
        installation_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".restore-boot-", dir=installation_root.parent) as scratch:
            working = Path(scratch)
            require_private_directory(working)
            control_root, partition_root = working / "control", working / "partition"
            ensure_private_directory(control_root)
            ensure_private_directory(partition_root)
            partition = partition_root / "partition.sqlite3"
            for name, target in (("control.sqlite3", control_root / "control.sqlite3"), ("partition.sqlite3", partition)):
                source = staging_root / name
                _require_snapshot_without_sidecars(source)
                _copy_private_restore_media(source, target)
            with closing(sqlite3.connect(partition.absolute().as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
                if PartitionDataRepository.requires_managed_restore(connection):
                    raise OperatorError("needs_reconciliation: managed runtime state requires a staged generation restore")
            keys_target = control_root / "keys"
            ensure_private_directory(keys_target)
            for key in sorted(signing_keys_directory.glob("*.key")):
                _copy_private_restore_media(key, keys_target / key.name)
            staged_suppressions = staging_root / "suppressions"
            if staged_suppressions.exists() or staged_suppressions.is_symlink():
                require_private_directory(staged_suppressions)
                target = control_root / "suppressions"
                ensure_private_directory(target)
                for journal in staged_suppressions.glob("forget-*.json"):
                    _copy_private_restore_media(journal, target / journal.name)
            with StorageAdministrationService(working) as service:
                if service._control_state().installation_id != identity:
                    raise OperatorError("integrity_error: staged control identity does not match the anchor")
            prepare_installation_root(installation_root)
            os.replace(working, installation_root)
            _sync_directory(installation_root.parent)
    except OSError as exc:
        raise OperatorError("denied: restore media and destination must be private to the storage owner") from exc
    except sqlite3.DatabaseError as exc:
        raise OperatorError("integrity_error: staged partition runtime inventory cannot be read") from exc
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
