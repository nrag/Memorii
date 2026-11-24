"""Durable state and transition rules for managed local outbox delivery.

These rules consume the current context and resolved authority supplied by
the installation owner. Publication, revalidation and target effects belong
to the owning transaction. A claim or receipt alone is never authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from memorii.core.consolidation.runtime_outputs import SourceReferences
from memorii.core.persistence.runtime_contracts import canonical_runtime_digest

_MAX_CLAIMS = 3
_LEASE_LENGTH = timedelta(seconds=30)

Identity = Annotated[str, Field(min_length=1, max_length=512)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Positive = Annotated[int, Field(ge=1, strict=True)]


class _DeliveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class _TaskTarget(_DeliveryRecord):
    partition_id: Identity
    task_id: Identity


class WorkStateProjectionScope(_TaskTarget):
    kind: Literal["work_state_projection"] = "work_state_projection"


class MemoryPlaneCandidateScope(_TaskTarget):
    kind: Literal["memory_plane_candidate"] = "memory_plane_candidate"
    domain: Literal["episodic", "semantic", "user"]


class ProtectedSkillCandidateScope(_TaskTarget):
    kind: Literal["protected_skill_candidate"] = "protected_skill_candidate"


DeliveryTargetScope = Annotated[
    WorkStateProjectionScope | MemoryPlaneCandidateScope | ProtectedSkillCandidateScope,
    Field(discriminator="kind"),
]


class DeliveryAuthorityBinding(_DeliveryRecord):
    installation_id: Identity
    principal: Identity
    client_namespace: Identity
    project_id: Identity | None = None
    host_binding_id: Identity
    credential_id: Identity
    grant_id: Identity
    grant_epoch: Positive
    scope: DeliveryTargetScope
    source_refs: SourceReferences = ()


class DeliveryRequest(_DeliveryRecord):
    delivery_id: Digest
    operation_generation: Identity
    origin_operation_id: Identity
    payload_ref: Identity
    payload_digest: Digest
    authority: DeliveryAuthorityBinding

    def request_digest(self) -> str:
        """Bind the target request independently of claim and retry metadata."""
        return canonical_runtime_digest(self.model_dump(mode="json"))


class DeliveryContext(_DeliveryRecord):
    installation_id: Identity
    partition_id: Identity
    generation_id: Identity
    eligibility_epoch: Positive
    control_revision: Positive | None = None
    mode: Literal["active", "read_only", "bypass"]


class PendingDelivery(_DeliveryRecord):
    status: Literal["pending"] = "pending"
    next_retry_at: AwareDatetime | None = None


class DeliveryClaim(_DeliveryRecord):
    status: Literal["delivering"] = "delivering"
    delivery_id: Digest
    worker_id: Identity
    fence_token: Positive
    eligibility_epoch: Positive
    control_revision: Positive | None = None
    expires_at: AwareDatetime


class DeliveredEffect(_DeliveryRecord):
    """Verified identity supplied by the registered target's own transaction."""

    record_id: Identity
    record_digest: Digest
    revision: Positive


class RuntimeTargetReceipt(_DeliveryRecord):
    delivery_id: Digest
    target_kind: Literal["work_projection", "writeback_candidate"]
    scope: DeliveryTargetScope
    request_digest: Digest
    effect: DeliveredEffect
    generation_id: Identity

    def matches_request(self, request: DeliveryRequest, *, generation_id: str) -> bool:
        expected_kind = (
            "work_projection"
            if isinstance(request.authority.scope, WorkStateProjectionScope)
            else "writeback_candidate"
        )
        return (
            self.delivery_id == request.delivery_id
            and self.target_kind == expected_kind
            and self.scope == request.authority.scope
            and self.request_digest == request.request_digest()
            and self.generation_id == generation_id
        )


class DeliveredDelivery(_DeliveryRecord):
    status: Literal["delivered"] = "delivered"
    receipt: RuntimeTargetReceipt
    completed_claim: DeliveryClaim | None = None


class RejectedDelivery(_DeliveryRecord):
    status: Literal["rejected"] = "rejected"
    reason: Literal["denied", "forgotten", "invalid_payload"]


class UnresolvedDelivery(_DeliveryRecord):
    status: Literal["needs_reconciliation"] = "needs_reconciliation"
    reason: Literal["retry_exhausted", "ambiguous_effect", "unverified_receipt"]


DeliveryProgress = Annotated[
    PendingDelivery | DeliveryClaim | DeliveredDelivery | RejectedDelivery | UnresolvedDelivery,
    Field(discriminator="status"),
]


class ManagedDelivery(_DeliveryRecord):
    """One typed delivery and its durable bounded progress."""

    request: DeliveryRequest
    generation_id: Identity
    version: Positive = 1
    attempt_count: int = Field(default=0, ge=0, le=_MAX_CLAIMS, strict=True)
    fence_token: int = Field(default=0, ge=0, strict=True)
    progress: DeliveryProgress = Field(default_factory=PendingDelivery)

    @model_validator(mode="after")
    def _check_progress_binding(self) -> Self:
        if self.fence_token < self.attempt_count:
            raise ValueError("delivery fence must cover all attempted claims")
        if isinstance(self.progress, DeliveryClaim) and (
            self.progress.delivery_id != self.request.delivery_id
            or self.progress.fence_token != self.fence_token
            or self.attempt_count == 0
        ):
            raise ValueError("claim does not match delivery progress")
        if isinstance(self.progress, DeliveredDelivery) and (
            not self.progress.receipt.matches_request(self.request, generation_id=self.generation_id)
            or self.attempt_count == 0
        ):
            raise ValueError("receipt does not match delivery request")
        return self


class DeliveryTransitionError(RuntimeError):
    """A requested change could not be applied to the current delivery."""


def _advance(
    delivery: ManagedDelivery,
    progress: DeliveryProgress,
    *,
    count_claim: bool = False,
) -> ManagedDelivery:
    return ManagedDelivery(
        request=delivery.request,
        generation_id=delivery.generation_id,
        version=delivery.version + 1,
        attempt_count=delivery.attempt_count + int(count_claim),
        fence_token=delivery.fence_token + int(count_claim),
        progress=progress,
    )


def _require_active(delivery: ManagedDelivery, context: DeliveryContext) -> None:
    request = delivery.request
    if context.mode != "active":
        raise DeliveryTransitionError("unavailable: delivery requires active mode")
    if (
        context.installation_id != request.authority.installation_id
        or context.partition_id != request.authority.scope.partition_id
        or context.generation_id != delivery.generation_id
    ):
        raise DeliveryTransitionError("needs_reconciliation: delivery belongs to another generation or partition")


def _require_claim(
    delivery: ManagedDelivery,
    claim: DeliveryClaim,
    context: DeliveryContext,
    *,
    now: datetime,
) -> None:
    _require_active(delivery, context)
    _require_timestamp(now)
    if (
        delivery.progress != claim
        or claim.eligibility_epoch != context.eligibility_epoch
        or claim.control_revision != context.control_revision
        or now >= claim.expires_at
    ):
        raise DeliveryTransitionError("conflict: delivery claim is stale")


def _require_authority(delivery: ManagedDelivery, authority: DeliveryAuthorityBinding) -> None:
    if delivery.request.authority != authority:
        raise DeliveryTransitionError("denied: live authority does not match delivery binding")


def _require_timestamp(now: datetime) -> None:
    if now.utcoffset() is None:
        raise DeliveryTransitionError("invalid_request: delivery time must be timezone-aware")


def claim_delivery(
    delivery: ManagedDelivery,
    *,
    context: DeliveryContext,
    current_authority: DeliveryAuthorityBinding,
    worker_id: str,
    now: datetime,
) -> ManagedDelivery:
    _require_active(delivery, context)
    _require_authority(delivery, current_authority)
    _require_timestamp(now)
    pending = delivery.progress
    if not isinstance(pending, PendingDelivery):
        raise DeliveryTransitionError("conflict: only a pending delivery can be claimed")
    if pending.next_retry_at is not None and now < pending.next_retry_at:
        raise DeliveryTransitionError("conflict: delivery retry is not due")
    if delivery.attempt_count >= _MAX_CLAIMS:
        return _advance(delivery, UnresolvedDelivery(reason="retry_exhausted"))
    claim = DeliveryClaim(
        delivery_id=delivery.request.delivery_id,
        worker_id=worker_id,
        fence_token=delivery.fence_token + 1,
        eligibility_epoch=context.eligibility_epoch,
        control_revision=context.control_revision,
        expires_at=now + _LEASE_LENGTH,
    )
    return _advance(delivery, claim, count_claim=True)


def _schedule_retry(delivery: ManagedDelivery, *, since: datetime) -> ManagedDelivery:
    if delivery.attempt_count >= _MAX_CLAIMS:
        return _advance(delivery, UnresolvedDelivery(reason="retry_exhausted"))
    return _advance(
        delivery,
        PendingDelivery(next_retry_at=since + timedelta(seconds=delivery.attempt_count)),
    )


def recover_delivery_claim(
    delivery: ManagedDelivery, *, context: DeliveryContext, now: datetime
) -> ManagedDelivery:
    """Recover an elapsed or invalidated claim without admitting a target effect."""
    _require_active(delivery, context)
    _require_timestamp(now)
    claim = delivery.progress
    if not isinstance(claim, DeliveryClaim):
        raise DeliveryTransitionError("conflict: delivery has no recoverable claim")
    if (
        claim.eligibility_epoch == context.eligibility_epoch
        and claim.control_revision == context.control_revision
        and now < claim.expires_at
    ):
        raise DeliveryTransitionError("conflict: delivery claim is still current")
    return _schedule_retry(delivery, since=min(now, claim.expires_at))


def reject_pending_delivery(
    delivery: ManagedDelivery,
    *,
    context: DeliveryContext,
    reason: Literal["denied", "forgotten", "invalid_payload"],
) -> ManagedDelivery:
    """Record a permanent authoritative refusal before any target claim."""
    _require_active(delivery, context)
    if not isinstance(delivery.progress, PendingDelivery):
        raise DeliveryTransitionError("conflict: only a pending delivery can be rejected before claim")
    return _advance(delivery, RejectedDelivery(reason=reason))


def record_delivery_failure(
    delivery: ManagedDelivery,
    *,
    claim: DeliveryClaim,
    context: DeliveryContext,
    now: datetime,
    outcome: Literal["transient", "denied", "forgotten", "invalid_payload", "ambiguous_effect", "unverified_receipt"],
) -> ManagedDelivery:
    _require_claim(delivery, claim, context, now=now)
    if outcome == "transient":
        return _schedule_retry(delivery, since=now)
    if outcome in ("ambiguous_effect", "unverified_receipt"):
        return _advance(delivery, UnresolvedDelivery(reason=outcome))
    return _advance(delivery, RejectedDelivery(reason=outcome))


def complete_delivery(
    delivery: ManagedDelivery,
    *,
    claim: DeliveryClaim,
    context: DeliveryContext,
    current_authority: DeliveryAuthorityBinding,
    now: datetime,
    receipt: RuntimeTargetReceipt,
    effect: DeliveredEffect,
) -> ManagedDelivery:
    """Validate the effect and receipt before publishing them with terminal queue state."""
    _require_claim(delivery, claim, context, now=now)
    _require_authority(delivery, current_authority)
    if (
        not receipt.matches_request(delivery.request, generation_id=delivery.generation_id)
        or receipt.effect != effect
    ):
        raise DeliveryTransitionError("integrity_error: target receipt does not match request and verified effect")
    return _advance(delivery, DeliveredDelivery(receipt=receipt, completed_claim=claim))
