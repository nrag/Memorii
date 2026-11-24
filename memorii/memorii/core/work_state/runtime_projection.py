"""Managed local work projections derived from signed runtime command effects."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.consolidation.runtime_outputs import ConsolidationOrigin, runtime_delivery_id
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    ManagedHostCommandAuthority,
    ResolvedHostCommandAuthority,
)
from memorii.core.persistence.contracts import (
    InstallationControlState,
    RuntimePublicationState,
    canonical_json_digest,
)
from memorii.core.persistence.managed_delivery import (
    DeliveredDelivery,
    DeliveredEffect,
    DeliveryAuthorityBinding,
    DeliveryClaim,
    DeliveryContext,
    DeliveryRequest,
    DeliveryTransitionError,
    ManagedDelivery,
    PendingDelivery,
    RuntimeTargetReceipt,
    WorkStateProjectionScope,
    claim_delivery,
    complete_delivery,
    record_delivery_failure,
    recover_delivery_claim,
    reject_pending_delivery,
)
from memorii.core.persistence.runtime_contracts import OperationOrigin, RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.recall.models import WorkStateSummary
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.writer_enrollment import (
    WriterEnrollmentError,
    WriterEnrollmentRegistry,
)
from memorii.core.work_state.models import WorkStateKind, WorkStateStatus

_WORK_PROJECTION_COMMANDS = ("record_action_dispatch", "pause_task", "complete_task")
_T = TypeVar("_T")


class ManagedWorkProjection(BaseModel):
    """Immutable revision-bound effect in the local work-state owner."""

    origin_runtime_revision: int = Field(ge=1)
    scope: WorkStateProjectionScope
    summary: WorkStateSummary

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="after")
    def _scope_matches_summary(self) -> ManagedWorkProjection:
        if self.summary.task_id != self.scope.task_id:
            raise ValueError("projection summary differs from task scope")
        return self

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class ManagedWorkProjectionDelivery(BaseModel):
    """Signed outbox row with the immutable, reconstructible projection payload."""

    record_type: Literal["managed_work_projection"] = "managed_work_projection"
    origin: OperationOrigin
    command: RuntimeCommandRequest
    delivery: ManagedDelivery
    projection: ManagedWorkProjection

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="after")
    def _bound_payload(self) -> ManagedWorkProjectionDelivery:
        request = self.delivery.request
        coordinate = self.origin.coordinate
        authority = request.authority
        expected_delivery_id = runtime_delivery_id(
            coordinate.repository_id,
            "work_projection",
            ConsolidationOrigin(
                installation_id=coordinate.installation_id,
                partition_id=coordinate.repository_id,
                operation_generation=coordinate.generation_id,
                task_id=self.projection.scope.task_id,
                client_namespace=coordinate.client_namespace,
                operation_id=coordinate.operation_id,
                request_digest=coordinate.request_digest,
            ),
        )
        if (
            request.delivery_id != expected_delivery_id
            or request.payload_ref != expected_delivery_id
            or request.payload_digest != self.projection.digest()
            or request.operation_generation != coordinate.generation_id
            or request.origin_operation_id != coordinate.operation_id
            or self.command.operation_id != coordinate.operation_id
            or self.command.kind not in _WORK_PROJECTION_COMMANDS
            or self.command.task_id != self.projection.scope.task_id
            or self.command.managed_intent_digest() != coordinate.request_digest
            or authority.installation_id != coordinate.installation_id
            or authority.principal != coordinate.principal
            or authority.client_namespace != coordinate.client_namespace
            or authority.scope != self.projection.scope
            or authority.source_refs
        ):
            raise ValueError("projection delivery payload or origin binding does not match")
        return self

    def with_delivery(self, delivery: ManagedDelivery) -> ManagedWorkProjectionDelivery:
        return ManagedWorkProjectionDelivery(
            origin=self.origin, command=self.command, delivery=delivery, projection=self.projection,
        )


def stage_work_projection(
    connection: sqlite3.Connection,
    repository: RuntimeStateRepository,
    *,
    command: RuntimeCommandRequest,
    origin: OperationOrigin,
    grant: ResolvedHostCommandAuthority,
    runtime_revision: int,
) -> ManagedWorkProjectionDelivery | None:
    """Stage metadata from the same authorized origin transaction as its effect.

    Caller is the managed command owner. Projection is a distinct optional
    permission supplied by that owner's current fenced authorization.
    """
    task_id = command.task_id
    if command.kind not in _WORK_PROJECTION_COMMANDS or not task_id or not grant.permits_work_projection(task_id):
        return None
    from memorii.core.persistence.runtime_api import operation_origin_namespace, operation_origin_proof_digest

    coordinate = origin.coordinate
    if (
        grant.principal != coordinate.principal
        or grant.client_namespace != coordinate.client_namespace
        or grant.installation_id != coordinate.installation_id
        or grant.data_generation_id != coordinate.generation_id
    ):
        raise DeliveryTransitionError("denied: projection grant does not match command owner")
    receipt = repository.get_command_receipt_in(
        connection, operation_origin_namespace(coordinate), coordinate.operation_id
    )
    if (
        receipt is None
        or receipt.status != "committed"
        or receipt.operation_origin != coordinate
        or receipt.origin_proof_digest != operation_origin_proof_digest(origin)
        or receipt.current_revision != runtime_revision
        or repository.read_runtime_revision_in(connection) != runtime_revision
    ):
        raise DeliveryTransitionError("integrity_error: projection lacks its exact origin receipt")
    task = repository.get_task_in(connection, task_id)
    if task is None or task.principal != grant.principal:
        raise DeliveryTransitionError("denied: projection task does not belong to the resolved host principal")
    scope = WorkStateProjectionScope(partition_id=coordinate.repository_id, task_id=task_id)
    lifecycle_status = {
        "active": WorkStateStatus.ACTIVE,
        "paused": WorkStateStatus.PAUSED,
        "completed": WorkStateStatus.RESOLVED,
        "aborted": WorkStateStatus.ABANDONED,
    }[task.lifecycle]
    projection = ManagedWorkProjection(
        origin_runtime_revision=runtime_revision,
        scope=scope,
        summary=WorkStateSummary(
            work_state_id=f"runtime:{task_id}",
            kind=WorkStateKind.TASK_EXECUTION,
            status=lifecycle_status,
            title="Runtime task",
            summary=f"Runtime task status: {task.lifecycle}.",
            confidence=1,
            task_id=task_id,
            user_id=task.principal,
        ),
    )
    delivery_id = runtime_delivery_id(
        coordinate.repository_id,
        "work_projection",
        ConsolidationOrigin(
            installation_id=coordinate.installation_id,
            partition_id=coordinate.repository_id,
            operation_generation=coordinate.generation_id,
            task_id=task_id,
            client_namespace=coordinate.client_namespace,
            operation_id=coordinate.operation_id,
            request_digest=coordinate.request_digest,
        ),
    )
    entry = ManagedWorkProjectionDelivery(
        origin=origin,
        command=command,
        delivery=ManagedDelivery(
            request=DeliveryRequest(
                delivery_id=delivery_id,
                operation_generation=coordinate.generation_id,
                origin_operation_id=coordinate.operation_id,
                payload_ref=delivery_id,
                payload_digest=projection.digest(),
                authority=DeliveryAuthorityBinding(
                    installation_id=coordinate.installation_id,
                    principal=coordinate.principal,
                    client_namespace=coordinate.client_namespace,
                    project_id=task.project,
                    host_binding_id=grant.client_namespace,
                    credential_id=grant.credential_id,
                    grant_id=grant.grant_id,
                    grant_epoch=grant.grant_epoch,
                    scope=scope,
                ),
            ),
            generation_id=coordinate.generation_id,
        ),
        projection=projection,
    )
    repository.apply_managed_work_projection_delivery(connection, entry)
    return entry


def require_current_projection_authority(
    administration: StorageAdministrationService,
    grants: ManagedHostCommandAuthority,
    entry: ManagedWorkProjectionDelivery,
    state: InstallationControlState,
    finalized: RuntimePublicationState,
    now: datetime,
) -> None:
    """Verify the original proof and its current grant under the owner's fence."""
    if not administration.verify_operation_origin(entry.origin):
        raise DeliveryTransitionError("integrity_error: invalid signed projection origin")
    binding = entry.delivery.request.authority
    resolved = grants.resolve_persisted_binding_in_verified_context(
        credential_id=binding.credential_id,
        principal=binding.principal,
        grant_id=binding.grant_id,
        grant_epoch=binding.grant_epoch,
        request=entry.command,
        state=state,
        finalized=finalized,
        now=now,
    )
    if (
        resolved.client_namespace != binding.client_namespace
        or resolved.client_namespace != binding.host_binding_id
        or not resolved.permits_work_projection(entry.projection.scope.task_id)
    ):
        raise HostCommandAuthorityError("denied: current grant does not authorize projection")


class ManagedWorkProjectionWorker:
    """Enrolled local worker. An effect requires current grant and a live claim."""

    def __init__(
        self,
        administration: StorageAdministrationService,
        *,
        worker_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._administration = administration
        self._worker_id = worker_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._grants = ManagedHostCommandAuthority(administration)
        self._revoked = RefreshingRevokedIdentityView(administration.installation_root / "control")
        self._writers = WriterEnrollmentRegistry(administration.installation_root / "control" / "writers")

    def claim(self, delivery_id: str) -> DeliveryClaim | None:
        """Claim a due projection, recording a terminal refusal if its grant was revoked."""
        def apply(
            connection: sqlite3.Connection, repository: RuntimeStateRepository,
            entry: ManagedWorkProjectionDelivery, state: InstallationControlState,
            context: DeliveryContext, finalized: RuntimePublicationState,
        ) -> DeliveryClaim | None:
            delivery = entry.delivery
            now = self._clock()
            if isinstance(delivery.progress, DeliveryClaim):
                result = recover_delivery_claim(delivery, context=context, now=now)
                repository.apply_managed_work_projection_delivery(connection, entry.with_delivery(result))
                return None
            if self._revoked.is_revoked_task(entry.projection.scope.task_id):
                result = reject_pending_delivery(delivery, context=context, reason="forgotten")
                repository.apply_managed_work_projection_delivery(connection, entry.with_delivery(result))
                return None
            try:
                require_current_projection_authority(self._administration, self._grants, entry, state, finalized, now)
            except HostCommandAuthorityError as exc:
                if not str(exc).startswith(("denied:", "not_found:")):
                    raise
                result = reject_pending_delivery(delivery, context=context, reason="denied")
                repository.apply_managed_work_projection_delivery(connection, entry.with_delivery(result))
                return None
            if not isinstance(delivery.progress, PendingDelivery):
                raise DeliveryTransitionError("conflict: projection is terminal")
            result = claim_delivery(
                delivery, context=context, current_authority=delivery.request.authority,
                worker_id=self._worker_id, now=now,
            )
            repository.apply_managed_work_projection_delivery(connection, entry.with_delivery(result))
            return result.progress if isinstance(result.progress, DeliveryClaim) else None

        return self._publish(delivery_id, apply)

    def publish(self, claim: DeliveryClaim) -> RuntimeTargetReceipt | None:
        """Publish target effect, target receipt and terminal delivery together."""
        if claim.worker_id != self._worker_id:
            raise DeliveryTransitionError("denied: claim belongs to another worker")

        def apply(
            connection: sqlite3.Connection, repository: RuntimeStateRepository,
            entry: ManagedWorkProjectionDelivery, state: InstallationControlState,
            context: DeliveryContext, finalized: RuntimePublicationState,
        ) -> RuntimeTargetReceipt | None:
            delivery = entry.delivery
            now = self._clock()
            if self._revoked.is_revoked_task(entry.projection.scope.task_id):
                if not isinstance(delivery.progress, DeliveryClaim):
                    raise DeliveryTransitionError("denied: projection task is suppressed")
                rejected = record_delivery_failure(
                    delivery, claim=claim, context=context, now=now, outcome="forgotten",
                )
                repository.apply_managed_work_projection_delivery(connection, entry.with_delivery(rejected))
                return None
            try:
                require_current_projection_authority(self._administration, self._grants, entry, state, finalized, now)
            except HostCommandAuthorityError as exc:
                if (
                    not str(exc).startswith(("denied:", "not_found:"))
                    or not isinstance(delivery.progress, DeliveryClaim)
                ):
                    raise
                rejected = record_delivery_failure(
                    delivery, claim=claim, context=context, now=now, outcome="denied",
                )
                repository.apply_managed_work_projection_delivery(connection, entry.with_delivery(rejected))
                return None
            if isinstance(delivery.progress, DeliveredDelivery):
                if delivery.progress.completed_claim != claim:
                    raise DeliveryTransitionError("conflict: projection receipt requires the completed claim")
                receipt = delivery.progress.receipt
                repository.verify_work_projection_effect(connection, entry, receipt)
                raise _DeliveredProjection(receipt)
            effect = DeliveredEffect(
                record_id=claim.delivery_id,
                record_digest=entry.projection.digest(),
                revision=repository.read_runtime_revision_in(connection),
            )
            receipt = RuntimeTargetReceipt(
                delivery_id=claim.delivery_id,
                target_kind="work_projection",
                scope=entry.projection.scope,
                request_digest=delivery.request.request_digest(),
                effect=effect,
                generation_id=context.generation_id,
            )
            completed = complete_delivery(
                delivery, claim=claim, context=context, current_authority=delivery.request.authority,
                now=now, receipt=receipt, effect=effect,
            )
            repository.insert_work_projection_effect(connection, entry, receipt)
            repository.apply_managed_work_projection_delivery(connection, entry.with_delivery(completed))
            return receipt

        try:
            return self._publish(claim.delivery_id, apply)
        except _DeliveredProjection as recovered:
            return recovered.receipt

    def _publish(
        self,
        delivery_id: str,
        apply: Callable[[
            sqlite3.Connection, RuntimeStateRepository, ManagedWorkProjectionDelivery,
            InstallationControlState, DeliveryContext, RuntimePublicationState,
        ], _T],
    ) -> _T:
        result: list[_T] = []
        verified: list[tuple[InstallationControlState, DeliveryContext, RuntimePublicationState]] = []

        def validate(state: InstallationControlState, finalized: RuntimePublicationState) -> None:
            writer = self._writers.require_enrolled(self._worker_id)
            if writer.kind != "managed_work_projection":
                raise WriterEnrollmentError("unsupported_configuration: incorrect managed projection worker kind")
            if state.mode != "active":
                raise DeliveryTransitionError("unavailable: projection requires active mode")
            verified.append((state, DeliveryContext(
                installation_id=finalized.installation_id,
                partition_id=finalized.repository_id,
                generation_id=finalized.data_generation_id,
                eligibility_epoch=state.eligibility_epoch + state.pending_epoch_increments,
                control_revision=state.control_revision,
                mode=state.mode,
            ), finalized))

        def apply_verified(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            state, context, finalized = verified[0]
            entry = repository.get_managed_work_projection_delivery(connection, delivery_id)
            if entry is None:
                raise DeliveryTransitionError("not_found: no managed projection delivery")
            if entry.delivery.generation_id != context.generation_id:
                raise DeliveryTransitionError("needs_reconciliation: delivery belongs to another generation")
            binding = entry.delivery.request.authority
            task = repository.get_task_in(connection, binding.scope.task_id)
            if task is None or task.principal != binding.principal or task.project != binding.project_id:
                raise DeliveryTransitionError("denied: projection scope no longer matches the task")
            result.append(apply(connection, repository, entry, state, context, finalized))

        publish_runtime_change(self._administration, apply_verified, validate_authority=validate)
        return result[0]


class _DeliveredProjection(RuntimeError):
    def __init__(self, receipt: RuntimeTargetReceipt) -> None:
        self.receipt = receipt
