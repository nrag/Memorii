"""Backup/restore operator controls over one installation.

Owner-authorized, plan-governed operations matching the design contract:
backup create runs under the acknowledged exclusive barrier (read_only)
AND holds the publication fence for the whole snapshot window, snapshots
the control and partition databases through SQLite's online backup API
(never live file copies), encrypts every participant snapshot with AEAD
under a fresh per-backup content key wrapped by the operator's recovery
key, signs the manifest with the installation's Ed25519 signing key,
records the revision vector and control epoch, and writes an atomically
renamed complete marker plus a signed control recovery bundle and an
independent recovery anchor the owner retains. Backup verify checks the
manifest signature and recomputes every digest, refusing torn, tampered,
foreign, and path-traversing archives. Restore plans from a verified
archive with installation-identity binding and explicit data-loss
acknowledgement for older control revisions, applies into a staging
directory whose participants are validated (plain basenames only), and
reapplies the CURRENT installation's suppression journals into staging so
restored data cannot resurrect revoked evidence. Neither the source
archive nor the live installation is ever modified.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field

from memorii.core.storage_administration.operator import (
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    require_owner_capability,
)

_BACKUP_MARKER = "backup-complete.json"
_RECOVERY_BUNDLE = "control-recovery-bundle.json"
_RECOVERY_ANCHOR = "recovery-anchor.json"
_SIGNING_PURPOSE = "memorii.installation-backup-manifest.v1"
_CHUNK = 1 << 20
_ALLOWED_PARTICIPANTS = ("control", "partition")


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

    manifest_version: Literal[1] = 1
    installation_id: str = Field(min_length=1)
    created_at_unix: int = Field(ge=0)
    control_revision: int = Field(ge=1)
    eligibility_epoch: int = Field(ge=1)
    runtime_revision: int = Field(ge=0)
    memory_write_revision: int = Field(ge=0)
    memory_data_revision: int = Field(ge=0)
    participants: tuple[BackupParticipant, ...] = Field(min_length=1)
    wrapped_content_key: str = Field(min_length=1)
    key_wrap_nonce: str = Field(min_length=16, max_length=32)
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class RestorePlan(BaseModel):
    """Owner-reviewed plan derived from a verified backup archive."""

    archive_path: str = Field(min_length=1)
    installation_id: str = Field(min_length=1)
    control_revision: int = Field(ge=1)
    participant_count: int = Field(ge=1)
    data_loss_acknowledged: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_backup(source: Path, destination: Path) -> None:
    """Snapshot one SQLite database through the online backup API."""
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
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
    directory = os.open(path.parent, os.O_RDONLY)
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
        archive_root.mkdir(parents=True, exist_ok=True)
        os.chmod(archive_root, 0o700)

        status = self._operator.status()
        if status.mode != "read_only":
            raise OperatorError(
                "conflict: backups require the acknowledged exclusive barrier"
                " (change mode to read_only first)"
            )

        # The fence spans status + snapshots + manifest assembly so the
        # recorded revision vector always agrees with the snapshot bytes.
        with service._publication_fence():
            participants: list[BackupParticipant] = []
            content_key = os.urandom(32)
            key_wrap_nonce = os.urandom(12)
            wrapped_key = AESGCM(recovery_key).encrypt(
                key_wrap_nonce, content_key, None
            )
            for participant_id in _ALLOWED_PARTICIPANTS:
                database_path = (
                    service.control_path()
                    if participant_id == "control"
                    else service.partition_path()
                )
                plain_path = archive_root / f".{participant_id}.plain"
                _sqlite_backup(Path(database_path), plain_path)
                nonce = os.urandom(12)
                ciphertext = AESGCM(content_key).encrypt(
                    nonce, plain_path.read_bytes(), None
                )
                plain_path.unlink()
                snapshot_path = archive_root / f"{participant_id}.sqlite3.enc"
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
                installation_id=service._control_state().installation_id,
                created_at_unix=int(time.time()),
                control_revision=status.control_revision,
                eligibility_epoch=status.eligibility_epoch,
                runtime_revision=status.runtime_revision,
                memory_write_revision=status.memory_write_revision,
                memory_data_revision=status.memory_data_revision,
                participants=tuple(participants),
                wrapped_content_key=base64.b64encode(wrapped_key).decode("ascii"),
                key_wrap_nonce=base64.b64encode(key_wrap_nonce).decode("ascii"),
                manifest_digest="0" * 64,
                manifest_signature="0" * 128,
            )
            digest = hashlib.sha256(
                json.dumps(
                    manifest.model_dump(
                        exclude={"manifest_digest", "manifest_signature"}
                    ),
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            key_id = service._signer_key_id
            service._ensure_signing_key()
            signature = service._signing.sign(key_id, _SIGNING_PURPOSE, digest)
            manifest = manifest.model_copy(
                update={"manifest_digest": digest, "manifest_signature": signature}
            )
            _atomic_write(
                archive_root / _BACKUP_MARKER,
                (manifest.model_dump_json() + "\n").encode(),
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
                archive_root / _RECOVERY_BUNDLE,
                json.dumps({**bundle, "signature": bundle_signature}, sort_keys=True).encode()
                + b"\n",
            )
            _atomic_write(
                archive_root / _RECOVERY_ANCHOR,
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
        digest = hashlib.sha256(
            json.dumps(
                manifest.model_dump(
                    exclude={"manifest_digest", "manifest_signature"}
                ),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if digest != manifest.manifest_digest:
            raise OperatorError("integrity_error: backup manifest digest mismatch")
        try:
            service._ensure_signing_key()
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
        current = service._control_state()
        if manifest.installation_id != current.installation_id:
            raise OperatorError(
                "denied: backup belongs to a different installation"
            )
        if (
            not data_loss_acknowledged
            and manifest.control_revision < current.control_revision
        ):
            raise OperatorError(
                "conflict: restoring an older backup requires explicit"
                " data-loss acknowledgement"
            )
        return RestorePlan(
            archive_path=str(archive_root),
            installation_id=manifest.installation_id,
            control_revision=manifest.control_revision,
            participant_count=len(manifest.participants),
            data_loss_acknowledged=data_loss_acknowledged,
        )

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
        manifest = self.verify_backup(archive_root=Path(plan.archive_path))
        if manifest.installation_id != plan.installation_id:
            raise OperatorError("conflict: plan and archive disagree")
        if (
            not plan.data_loss_acknowledged
            and manifest.control_revision
            < service._control_state().control_revision
        ):
            raise OperatorError(
                "conflict: data-loss acknowledgement missing for older backup"
            )
        staging_root.mkdir(parents=True, exist_ok=True)
        os.chmod(staging_root, 0o700)
        content_key = AESGCM(recovery_key).decrypt(
            base64.b64decode(manifest.key_wrap_nonce),
            base64.b64decode(manifest.wrapped_content_key),
            None,
        )
        restored: list[Path] = []
        for participant in manifest.participants:
            source = Path(plan.archive_path) / _validate_participant(participant)
            destination = staging_root / f"{participant.participant_id}.sqlite3"
            if destination.exists():
                for path in restored:
                    path.unlink(missing_ok=True)
                raise OperatorError(
                    "invalid_request: staging root is not empty;"
                    " use a fresh staging directory"
                )
            ciphertext = source.read_bytes()
            if hashlib.sha256(ciphertext).hexdigest() != participant.sha256:
                for path in restored:
                    path.unlink(missing_ok=True)
                raise OperatorError(
                    "integrity_error: archive mutated during restore"
                )
            plaintext = AESGCM(content_key).decrypt(
                base64.b64decode(participant.nonce), ciphertext, None
            )
            _atomic_write(destination, plaintext)
            restored.append(destination)
        # Reapply the CURRENT installation's suppression journals so restored
        # data can never resurrect revoked evidence (design: restore reapply).
        current_suppressions = (
            service.installation_root / "control" / "suppressions"
        )
        if current_suppressions.is_dir():
            staging_suppressions = staging_root / "suppressions"
            staging_suppressions.mkdir(exist_ok=True)
            for journal in sorted(current_suppressions.glob("forget-*.json")):
                shutil.copyfile(journal, staging_suppressions / journal.name)
        return staging_root


__all__ = [
    "BackupParticipant",
    "BackupRestoreOperator",
    "InstallationBackupManifest",
    "RestorePlan",
]
