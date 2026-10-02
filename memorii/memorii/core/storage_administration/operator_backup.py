"""Backup/restore operator controls over one installation.

Owner-authorized, plan-governed operations matching the design contract:
backup create runs under the acknowledged exclusive barrier (read_only),
snapshots the control and partition databases through SQLite's online
backup API (never live file copies), records the revision vector and
control epoch, and writes an InstallationBackupManifest with per-participant
digests. Backup verify recomputes every digest and refuses torn or
foreign archives. Restore plans from a verified archive and applies into
a staging directory, validating installation identity and control state
compatibility before the owner switches roots; it never deletes the
source archive or the prior installation.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.storage_administration.operator import (
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    _require_owner_capability,
)

_BACKUP_MARKER = "backup-complete.json"
_CHUNK = 1 << 20


class BackupParticipant(BaseModel):
    """One participant snapshot inside a backup."""

    participant_id: str = Field(min_length=1)
    kind: Literal["sqlite"]
    filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)

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
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

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
    ) -> InstallationBackupManifest:
        service = self._operator._administration
        _require_owner_capability(service, capability)
        if not reason.strip():
            raise OperatorError("invalid_request: backup reason is required")
        archive_root.mkdir(parents=True, exist_ok=True)
        os.chmod(archive_root, 0o700)

        status = self._operator.status()
        if status.mode != "read_only":
            raise OperatorError(
                "conflict: backups require the acknowledged exclusive barrier"
                " (change mode to read_only first)"
            )

        participants: list[BackupParticipant] = []
        for participant_id, database_path in (
            ("control", service.control_path()),
            ("partition", service.partition_path()),
        ):
            snapshot_path = archive_root / f"{participant_id}.sqlite3"
            _sqlite_backup(Path(database_path), snapshot_path)
            participants.append(
                BackupParticipant(
                    participant_id=participant_id,
                    kind="sqlite",
                    filename=snapshot_path.name,
                    sha256=_sha256_file(snapshot_path),
                    size_bytes=snapshot_path.stat().st_size,
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
            manifest_digest="0" * 64,
        )
        digest = hashlib.sha256(
            json.dumps(
                manifest.model_dump(exclude={"manifest_digest"}), sort_keys=True
            ).encode()
        ).hexdigest()
        manifest = manifest.model_copy(update={"manifest_digest": digest})
        marker_path = archive_root / _BACKUP_MARKER
        temporary = archive_root / f".{_BACKUP_MARKER}.tmp"
        temporary.write_text(manifest.model_dump_json() + "\n")
        os.replace(temporary, marker_path)
        os.chmod(marker_path, 0o600)
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
        digest = hashlib.sha256(
            json.dumps(
                manifest.model_dump(exclude={"manifest_digest"}), sort_keys=True
            ).encode()
        ).hexdigest()
        if digest != manifest.manifest_digest:
            raise OperatorError("integrity_error: backup manifest digest mismatch")
        for participant in manifest.participants:
            snapshot = archive_root / participant.filename
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
        _require_owner_capability(service, capability)
        manifest = self.verify_backup(archive_root=archive_root)
        current = service._control_state()
        if manifest.installation_id != current.installation_id:
            raise OperatorError(
                "denied: backup belongs to a different installation"
            )
        if not data_loss_acknowledged and manifest.control_revision < current.control_revision:
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
    ) -> Path:
        service = self._operator._administration
        _require_owner_capability(service, capability)
        manifest = self.verify_backup(archive_root=Path(plan.archive_path))
        if manifest.installation_id != plan.installation_id:
            raise OperatorError("conflict: plan and archive disagree")
        if not plan.data_loss_acknowledged and manifest.control_revision < service._control_state().control_revision:
            raise OperatorError(
                "conflict: data-loss acknowledgement missing for older backup"
            )
        staging_root.mkdir(parents=True, exist_ok=True)
        os.chmod(staging_root, 0o700)
        restored: list[Path] = []
        for participant in manifest.participants:
            source = Path(plan.archive_path) / participant.filename
            destination = staging_root / f"{participant.participant_id}.sqlite3"
            shutil_copy(source, destination)
            if _sha256_file(destination) != participant.sha256:
                for path in restored:
                    path.unlink(missing_ok=True)
                raise OperatorError(
                    "integrity_error: restored participant digest mismatch"
                )
            restored.append(destination)
        return staging_root


def shutil_copy(source: Path, destination: Path) -> None:
    import shutil

    shutil.copyfile(source, destination)
    os.chmod(destination, 0o600)


__all__ = [
    "BackupParticipant",
    "BackupRestoreOperator",
    "InstallationBackupManifest",
    "RestorePlan",
]
