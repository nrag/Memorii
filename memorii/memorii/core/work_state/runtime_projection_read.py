"""Scoped recall of published managed work-state projections."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pydantic import ValidationError

from memorii.core.harness_state.credentials import CredentialError, IssuedCredential, SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry, GrantRegistryError
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.write_authority import HostCommandAuthorityError, ManagedHostCommandAuthority
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.managed_delivery import DeliveredDelivery, DeliveryTransitionError
from memorii.core.persistence.runtime_api import operation_origin_namespace, operation_origin_proof_digest
from memorii.core.persistence.runtime_contracts import TaskRecord
from memorii.core.persistence.runtime_repository import RuntimeStateError, RuntimeStateRepository
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import (
    InstallationIntegrityError,
    StorageAdministrationError,
    StorageAdministrationService,
)
from memorii.core.work_state.runtime_projection import (
    ManagedWorkProjection,
    ManagedWorkProjectionDelivery,
    require_current_projection_authority,
)


class WorkProjectionRecallError(RuntimeError):
    """Refuse a managed projection without releasing task content."""


class ManagedWorkProjectionReader:
    """Read one task's latest eligible managed summary through its owner."""

    def __init__(
        self,
        administration: StorageAdministrationService,
        *,
        credentials: SidecarCredentialStore,
        secret: str,
        grant: RuntimeReadGrant,
    ) -> None:
        self._administration = administration
        self._credentials = credentials
        self._secret = secret
        self._grant = grant
        control = administration.installation_root / "control"
        self._read_grants = GrantEpochRegistry(control / "grants")
        self._origin_grants = ManagedHostCommandAuthority(administration)
        self._revoked = RefreshingRevokedIdentityView(control)

    def read(self, *, task_id: str) -> ManagedWorkProjection | None:
        """Select and verify an immutable local effect without reading native event logs."""
        try:
            with self._administration.verified_operation_context() as (state, finalized):
                credential = self._authorize(task_id)
                if state.mode == "bypass":
                    raise WorkProjectionRecallError("unavailable: managed projection recall is unavailable")
                repository = RuntimeStateRepository(self._administration.partition())
                with repository.partition.transaction(write=False) as connection:
                    task = repository.get_task_in(connection, task_id)
                    if task is None or task.principal != credential.principal:
                        raise WorkProjectionRecallError("denied: managed projection scope is unavailable")
                    repository.partition.require_delivery_catalogs(connection)
                    projection = self._latest_eligible(connection, repository, task, state, finalized)
                    if self._authorize(task_id) != credential:
                        raise WorkProjectionRecallError("denied: managed projection scope is unavailable")
                    return projection
        except (
            ValidationError, sqlite3.DatabaseError, RuntimeStateError, DeliveryTransitionError, InstallationIntegrityError,
        ) as exc:
            raise WorkProjectionRecallError("integrity_error: managed projection could not be verified") from exc
        except StorageAdministrationError as exc:
            raise WorkProjectionRecallError("unavailable: reopen the managed projection port") from exc

    def _authorize(self, task_id: str) -> IssuedCredential:
        try:
            self._credentials.verify_permissions()
            credential = self._credentials.credential_for(self._secret)
        except (CredentialError, OSError, ValidationError) as exc:
            raise WorkProjectionRecallError("denied: managed projection scope is unavailable") from exc
        if credential is None:
            raise WorkProjectionRecallError("unauthenticated: installed credential is required")
        grant = self._grant
        if (
            not task_id or "\x00" in task_id
            or grant.principal != credential.principal
            or task_id not in grant.allowed_task_ids
            or grant.expires_at.utcoffset() is None
            or not grant.authorizes(task_id, now=datetime.now(UTC))
            or self._revoked.is_revoked_task(task_id)
        ):
            raise WorkProjectionRecallError("denied: managed projection scope is unavailable")
        try:
            self._read_grants.verify_permissions()
            self._read_grants.require_current(grant.grant_id, grant.epoch)
        except (GrantRegistryError, OSError, ValueError) as exc:
            raise WorkProjectionRecallError("denied: managed projection scope is unavailable") from exc
        return credential

    def _latest_eligible(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        task: TaskRecord,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> ManagedWorkProjection | None:
        # The local target owns one work-state identity per task. Keep task
        # and partition constraints in SQL and order by the origin revision,
        # independent of when the worker published an individual effect.
        rows = connection.execute(
            "SELECT delivery_id, record_json FROM runtime_work_projections"
            " WHERE json_extract(record_json, '$.scope.partition_id') = ?"
            " AND json_extract(record_json, '$.scope.task_id') = ?"
            " AND json_extract(record_json, '$.summary.work_state_id') = ?"
            " ORDER BY json_extract(record_json, '$.origin_runtime_revision') DESC, delivery_id",
            (finalized.repository_id, task.task_id, f"runtime:{task.task_id}"),
        )
        latest: ManagedWorkProjection | None = None
        for row in rows:
            projection = ManagedWorkProjection.model_validate_json(row["record_json"])
            if latest is not None and projection.origin_runtime_revision < latest.origin_runtime_revision:
                break
            entry = repository.get_managed_work_projection_delivery(connection, row["delivery_id"])
            if entry is None or entry.projection != projection:
                raise WorkProjectionRecallError("integrity_error: managed projection has no exact delivery")
            if not self._verify_published(connection, repository, entry, task, state, finalized):
                continue
            if latest is not None:
                raise WorkProjectionRecallError("integrity_error: ambiguous managed projection revision")
            latest = projection
        return latest

    def _verify_published(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        entry: ManagedWorkProjectionDelivery,
        task: TaskRecord,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> bool:
        origin = entry.origin.coordinate
        binding = entry.delivery.request.authority
        progress = entry.delivery.progress
        if origin.generation_id != finalized.data_generation_id:
            return False
        if (
            origin.installation_id != finalized.installation_id
            or origin.repository_id != finalized.repository_id
            or entry.delivery.generation_id != origin.generation_id
            or binding.scope.task_id != task.task_id
            or binding.principal != task.principal
            or entry.projection.summary.user_id != task.principal
            or not isinstance(progress, DeliveredDelivery)
            or progress.completed_claim is None
            or progress.completed_claim.delivery_id != entry.delivery.request.delivery_id
            or progress.completed_claim.fence_token != entry.delivery.fence_token
            or not progress.receipt.matches_request(entry.delivery.request, generation_id=origin.generation_id)
            or not entry.projection.origin_runtime_revision < progress.receipt.effect.revision
                <= repository.read_runtime_revision_in(connection)
        ):
            raise WorkProjectionRecallError("integrity_error: managed projection provenance differs")
        origin_receipt = repository.get_command_receipt_in(
            connection, operation_origin_namespace(origin), origin.operation_id,
        )
        if (
            origin_receipt is None
            or origin_receipt.status != "committed"
            or origin_receipt.operation_origin != origin
            or origin_receipt.origin_proof_digest != operation_origin_proof_digest(entry.origin)
            or origin_receipt.current_revision != entry.projection.origin_runtime_revision
        ):
            raise WorkProjectionRecallError("integrity_error: managed projection lacks an exact origin receipt")
        repository.verify_work_projection_effect(connection, entry, progress.receipt)
        if binding.project_id != task.project:
            return False
        try:
            require_current_projection_authority(
                self._administration, self._origin_grants, entry, state, finalized, datetime.now(UTC),
            )
        except HostCommandAuthorityError as exc:
            if str(exc).startswith(("denied:", "not_found:", "needs_reconciliation:")):
                return False
            raise WorkProjectionRecallError("integrity_error: managed projection grant could not be verified") from exc
        return True
