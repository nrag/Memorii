"""Operator controls: modes, export, and capacity governance.

Owner-authorized operations over the registered installation: mode
transitions (active/read_only/bypass) with acknowledged fencing,
scoped export, and capacity admission. Destructive operations
(forget/erase/restore) remain governed by their own owner plans and
are not exposed here as one-call conveniences. Mode changes take
effect atomically in control state with a journal entry; the
publication gate enforces the new mode for every subsequent data
operation.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import RuntimePublicationState, canonical_json_digest
from memorii.core.storage_administration.operational_status import (
    InstalledArtifactStatus,
    QueueStatus,
    delivery_queue_status,
    installed_artifact_status,
)
from memorii.core.storage_administration.service import (
    MODE_RECOVERY_DIRECTORY,
    REPLACEMENT_RECOVERY_QUARANTINE,
    InstallationIntegrityError,
    InstallationQuarantinedError,
    StorageAdministrationService,
)
from memorii.stores.sqlite.private_storage import ensure_private_directory, read_private_file

InstallationMode = Literal["active", "read_only", "bypass"]


class OperatorError(RuntimeError):
    """Operator operation refused; the detail carries the reason."""


class OwnerCapability(BaseModel):
    """Owner-only admin capability; model tools can never mint one."""

    owner_principal: str = Field(min_length=1)
    capability_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class ModeChangeRequest(BaseModel):
    """Closed mode transition with the expected current epoch."""

    target_mode: InstallationMode
    expected_control_revision: int = Field(ge=1)
    reason: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class InstallationStatus(BaseModel):
    """Content-free operational status the owner can always read."""

    readiness: Literal["ready", "inert", "pending_recovery", "uninitialized", "quarantined", "unavailable"]
    mode: InstallationMode | None = None
    effective_mode: Literal["active", "read_only", "offline"] = "offline"
    control_revision: int | None = Field(default=None, ge=1)
    eligibility_epoch: int | None = Field(default=None, ge=1)
    pending_epoch_increments: int = Field(default=0, ge=0)
    quarantined: bool = False
    runtime_revision: int | None = Field(default=None, ge=0)
    memory_write_revision: int | None = Field(default=None, ge=0)
    memory_data_revision: int | None = Field(default=None, ge=0)
    verified_generation_id: str | None = None
    verified_publication_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    storage_schema_version: int | None = Field(default=None, ge=1)
    read_selectors_ready: bool | None = None
    custody_state: Literal["pending", "unknown"] = "unknown"
    backup_state: Literal["verified", "unavailable", "unknown"] = "unknown"
    verified_backup_age_seconds: int | None = Field(default=None, ge=0)
    delivery_queue: QueueStatus | None = None
    intake_queue: QueueStatus | None = None
    artifact: InstalledArtifactStatus

    model_config = ConfigDict(extra="forbid", frozen=True)


class StorageAdministrationOperator:
    """Owner-authorized operator surface over one installation."""

    def __init__(self, administration: StorageAdministrationService) -> None:
        self._administration = administration

    def status(self, *, backup_archive: Path | None = None) -> InstallationStatus:
        """Use only verified operational data and report inert roots without opening the partition."""
        result = self._status_current_root()
        if backup_archive is None or result.verified_generation_id is None:
            return result
        from memorii.core.storage_administration.operator_backup import BackupRestoreOperator

        service = self._administration
        try:
            manifest = BackupRestoreOperator(self).verify_backup(archive_root=backup_archive)
            if manifest.installation_id != service._control_state().installation_id:
                return result.model_copy(update={"backup_state": "unavailable"})
        except (OperatorError, OSError, ValueError):
            return result.model_copy(update={"backup_state": "unavailable"})
        return result.model_copy(update={
            "backup_state": "verified",
            "verified_backup_age_seconds": max(0, int(time.time()) - manifest.created_at_unix),
        })

    def _status_current_root(self) -> InstallationStatus:
        from memorii.core.storage_administration.operator_backup import backup_lifetime_guard

        with backup_lifetime_guard(self._administration, exclusive=False), ExitStack() as snapshots:
            return self._status_pinned_root(snapshots)

    def _status_pinned_root(self, snapshots: ExitStack) -> InstallationStatus:
        from memorii.core.harness_state.managed_spool_store import SqliteManagedSpool
        from memorii.core.storage_administration.operator_backup import open_backup_snapshot

        service = self._administration
        artifact = installed_artifact_status()
        with service._publication_fence():
            state = service._control.read_control_state()
            if state is None:
                return InstallationStatus(readiness="uninitialized", artifact=artifact)
            initial = InstallationStatus(
                readiness="unavailable", artifact=artifact, mode=state.mode,
                control_revision=state.control_revision, eligibility_epoch=state.eligibility_epoch,
                pending_epoch_increments=state.pending_epoch_increments,
                quarantined=state.quarantined_reason is not None,
            )
            if state.quarantined_reason == REPLACEMENT_RECOVERY_QUARANTINE or service.mode_recovery_pending(state):
                return initial.model_copy(update={"readiness": "pending_recovery", "custody_state": "pending"})
            if state.quarantined_reason is not None:
                return initial.model_copy(update={"readiness": "quarantined"})

            repository_id = service._repository_id()
            change = service._control.read_generation_change(repository_id)
            if (
                (change is not None and change.phase == "prepared")
                or service._control.read_pending_intent(repository_id) is not None
            ):
                return initial.model_copy(update={"readiness": "pending_recovery"})
            finalized = service._control.read_publication_state(repository_id)
            if finalized is None:
                return initial
            try:
                snapshot = service._verified_snapshot_locked()
                if snapshot.tuple_digest != finalized.payload_digest():
                    return initial
                partition = service.partition()
                path = service.partition_path()
                identity = service._partition_file_identity(path)
                connection = snapshots.enter_context(open_backup_snapshot(path))
                row = partition.read_publication_row(connection)
                if (
                    row is None or row["tuple_digest"] != finalized.payload_digest()
                    or not service._matches_signed_publication(row, finalized)
                    or service._partition_file_identity(path) != identity
                ):
                    return initial
                runtime_revision = partition.read_runtime_revision(connection)
                schema_version = partition.read_schema_version(connection)
                read_selectors_ready = not partition.needs_verified_read_selectors(connection)
            except InstallationQuarantinedError:
                return initial.model_copy(update={"readiness": "quarantined", "quarantined": True})
            except (InstallationIntegrityError, OperatorError, OSError, sqlite3.DatabaseError, ValueError):
                if service._control_state().quarantined_reason is not None:
                    return initial.model_copy(update={"readiness": "quarantined", "quarantined": True})
                return initial
            intake_connection, intake_available = self._pin_status_intake(finalized, snapshots)

        try:
            deliveries = delivery_queue_status(connection, finalized)
        except (sqlite3.DatabaseError, ValueError):
            return initial
        intake = None
        if intake_connection is not None:
            try:
                pending, held = SqliteManagedSpool.backlog_counts(
                    intake_connection, installation_id=finalized.installation_id,
                    repository_id=finalized.repository_id, generation_id=finalized.data_generation_id,
                )
                intake = QueueStatus(pending_count=pending, held_count=held)
            except sqlite3.DatabaseError:
                intake_available = False

        operational = intake_available and read_selectors_ready
        return initial.model_copy(update={
            "readiness": "inert" if state.mode == "bypass" else "ready" if operational else "unavailable",
            "effective_mode": state.mode if state.mode != "bypass" and operational else "offline",
            "runtime_revision": runtime_revision,
            "memory_write_revision": finalized.vector.memory_write_revision,
            "memory_data_revision": finalized.vector.memory_data_revision,
            "verified_generation_id": finalized.data_generation_id,
            "verified_publication_digest": snapshot.tuple_digest,
            "storage_schema_version": schema_version,
            "read_selectors_ready": read_selectors_ready,
            "delivery_queue": deliveries,
            "intake_queue": intake,
        })

    def _pin_status_intake(
        self, publication: RuntimePublicationState, snapshots: ExitStack,
    ) -> tuple[sqlite3.Connection | None, bool]:
        from memorii.core.harness_state.consumer import ConsumerDeliveryError
        from memorii.core.harness_state.managed_spool_store import SqliteManagedSpool
        from memorii.stores.sqlite.control import ControlJournalChainError, ControlStateError

        service = self._administration
        try:
            binding = service._control.read_managed_spool_binding()
            if binding is None:
                return None, True
            if binding.installation_id != publication.installation_id or binding.repository_id != publication.repository_id:
                return None, False
            connection = snapshots.enter_context(SqliteManagedSpool.pin_backlog(
                service.installation_root / "spool" / "managed", store_id=binding.store_id,
            ))
        except (ConsumerDeliveryError, ControlJournalChainError, ControlStateError):
            return None, False
        return connection, True

    def change_mode(
        self,
        request: ModeChangeRequest,
        *,
        capability: OwnerCapability,
    ) -> InstallationStatus:
        service = self._administration
        require_owner_capability(service, capability)
        # The transition takes the publication fence so an in-flight
        # publisher cannot commit across the mode change boundary.
        with service._publication_fence():
            recovery = service.installation_root / "control" / MODE_RECOVERY_DIRECTORY
            if recovery.exists() or recovery.is_symlink() or any(
                entry.operation in ("mode_recovery_registered", "mode_recovery_applied", "mode_recovery_activated")
                for entry in service._control.read_journal()
            ):
                raise OperatorError("unavailable: registered installation mode changes require independent custody")
            service.resolve_pending_publication()
            state = service._control_state()
            if state.quarantined_reason is not None:
                raise OperatorError(
                    "unsupported_configuration: quarantined installation;"
                    " owner recovery required before mode changes"
                )
            if state.control_revision != request.expected_control_revision:
                raise OperatorError(
                    "conflict: control revision changed;"
                    f" expected {request.expected_control_revision},"
                    f" current {state.control_revision}"
                )
            if state.mode != request.target_mode:
                if state.mode == "bypass" and request.target_mode != "active":
                    raise OperatorError("invalid_request: bypass returns to active only")
                service._control.write_control_state(
                    state.model_copy(
                        update={
                            "control_revision": state.control_revision + 1,
                            "mode": request.target_mode,
                        }
                    ),
                    service._journal_entry(
                        operation="mode_changed",
                        before_digest=canonical_json_digest(
                            {"mode": state.mode, "reason": request.reason}
                        ),
                        after_digest=canonical_json_digest(
                            {"mode": request.target_mode, "reason": request.reason}
                        ),
                    ),
                )
        if state.mode == "read_only" and request.target_mode != "read_only":
            # Leaving the barrier is the live-process trigger for forget
            # enforcement: pending reconciliations drain before the owner
            # sees the resumed status.
            service.drain_pending_forget_enforcement()
        return self.status()

    def read_export(self, *, capability: OwnerCapability) -> dict[str, object]:
        """Scoped deterministic export of current durable state."""
        service = self._administration
        require_owner_capability(service, capability)
        snapshot = service.acquire_verified_snapshot()
        repository = service.partition()
        suppressed = _suppressed_record_ids(service)
        with repository.transaction(write=False) as connection:
            tasks = [
                row["record_json"]
                for row in repository.read_runtime_rows(
                    connection, table="runtime_tasks"
                )
                if _record_id(row["record_json"]) not in suppressed
            ]
            runtime_revision = repository.read_runtime_revision(connection)
        import json as _json

        return {
            "publication_ordinal": snapshot.ordinal,
            "runtime_revision": runtime_revision,
            "memory_data_revision": snapshot.vector.memory_data_revision,
            "tasks": [_json.loads(task) for task in sorted(tasks)],
        }


def _suppressed_record_ids(service: StorageAdministrationService) -> frozenset[str]:
    """Task ids logically forgotten; exports and reads must never serve them.

    A tampered or unsupported journal entry raises: the export refuses
    rather than silently un-suppressing.
    """

    from memorii.core.storage_administration.suppression_journal import (
        read_suppression_records,
    )

    control_root = service.installation_root / "control"
    records = read_suppression_records(control_root)
    return frozenset(
        coordinate.coordinate_id
        for record in records
        for coordinate in record.suppressed
        if coordinate.coordinate_kind == "task"
    )


def _record_id(record_json: object) -> str:
    import json as _json

    try:
        return str(_json.loads(str(record_json)).get("task_id", ""))
    except ValueError:
        return ""


def _owner_capability_secret(administration: StorageAdministrationService) -> bytes:
    """The installation's owner-only capability secret.

    Created lazily under the owner-only key directory; never printed,
    logged, or included in any export. Holder of this secret can mint
    capabilities; the directory permissions are the trust boundary.
    """
    secret_path = administration.installation_root / "control" / "keys" / "owner-capability.secret"
    ensure_private_directory(secret_path.parent)
    with locked_file(secret_path.with_suffix(".lock"), exclusive=True, private=True):
        try:
            material = read_private_file(secret_path, limit=66).removesuffix(b"\n")
        except FileNotFoundError:
            material = secrets.token_hex(32).encode("ascii")
            descriptor, name = tempfile.mkstemp(prefix=".owner-capability.", dir=secret_path.parent)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(material + b"\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, secret_path)
            finally:
                temporary.unlink(missing_ok=True)
        if len(material) != 64:
            raise OperatorError("integrity_error: owner capability key is malformed")
        return material


def mint_owner_capability(
    administration: StorageAdministrationService,
    owner_principal: str,
) -> OwnerCapability:
    """Mint one capability for the installation's owner principal.

    Requires reading the owner-only secret: callers with filesystem
    access to the installation are the owners by construction; remote or
    model-origin callers can never reach this function.
    """
    import hmac as _hmac

    message = canonical_json_digest(
        {
            "installation_id": administration._control_state().installation_id,
            "owner_principal": owner_principal,
        }
    )
    secret = _owner_capability_secret(administration)
    digest = _hmac.new(secret, message.encode("utf-8"), "sha256").hexdigest()
    return OwnerCapability(owner_principal=owner_principal, capability_digest=digest)


def require_owner_capability(
    administration: StorageAdministrationService,
    capability: OwnerCapability,
) -> None:
    """The capability must be an HMAC over the installation's owner secret.

    The digest binds the installation id and principal under a secret
    held only in the owner-only key directory, so knowledge of public
    identifiers can never mint a capability; a foreign capability
    refuses before any state read beyond the installation identity.
    """
    expected = mint_owner_capability(
        administration, capability.owner_principal
    ).capability_digest
    import hmac as _hmac

    if not _hmac.compare_digest(expected, capability.capability_digest):
        raise OperatorError("denied: owner capability does not match this installation")


__all__ = [
    "InstallationMode",
    "InstallationStatus",
    "ModeChangeRequest",
    "OperatorError",
    "OwnerCapability",
    "StorageAdministrationOperator",
    "mint_owner_capability",
    "require_owner_capability",
]
