from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from memorii.core.persistence.managed_delivery import (
    DeliveredDelivery,
    DeliveredEffect,
    DeliveryAuthorityBinding,
    DeliveryClaim,
    DeliveryContext,
    DeliveryRequest,
    DeliveryTargetScope,
    DeliveryTransitionError,
    ManagedDelivery,
    MemoryPlaneCandidateScope,
    PendingDelivery,
    RejectedDelivery,
    RuntimeTargetReceipt,
    UnresolvedDelivery,
    WorkStateProjectionScope,
    claim_delivery,
    complete_delivery,
    record_delivery_failure,
    recover_delivery_claim,
    reject_pending_delivery,
)
from pydantic import TypeAdapter, ValidationError

_NOW = datetime(2026, 4, 25, tzinfo=UTC)
_CONTEXT = DeliveryContext(
    installation_id="installation",
    partition_id="partition",
    generation_id="generation",
    eligibility_epoch=1,
    mode="active",
)
_SCOPE = WorkStateProjectionScope(partition_id="partition", task_id="task")
_AUTHORITY = DeliveryAuthorityBinding(
    installation_id="installation",
    principal="principal",
    client_namespace="client",
    host_binding_id="host",
    credential_id="credential",
    grant_id="grant",
    grant_epoch=1,
    scope=_SCOPE,
)
_REQUEST = DeliveryRequest(
    delivery_id="a" * 64,
    operation_generation="generation",
    origin_operation_id="operation",
    payload_ref="result",
    payload_digest="b" * 64,
    authority=_AUTHORITY,
)
_EFFECT = DeliveredEffect(record_id="effect", record_digest="c" * 64, revision=1)
_RECEIPT = RuntimeTargetReceipt(
    delivery_id=_REQUEST.delivery_id,
    target_kind="work_projection",
    scope=_SCOPE,
    request_digest=_REQUEST.request_digest(),
    effect=_EFFECT,
    generation_id="generation",
)


def _pending() -> ManagedDelivery:
    return ManagedDelivery(request=_REQUEST, generation_id="generation")


def _claim(
    delivery: ManagedDelivery, *, context: DeliveryContext = _CONTEXT, now: datetime = _NOW
) -> tuple[ManagedDelivery, DeliveryClaim]:
    claimed = claim_delivery(
        delivery, context=context, current_authority=_AUTHORITY, worker_id="worker", now=now,
    )
    assert isinstance(claimed.progress, DeliveryClaim)
    return claimed, claimed.progress


def test_closed_task_bound_target_scopes() -> None:
    adapter = TypeAdapter(DeliveryTargetScope)
    fields = {"partition_id": "partition", "task_id": "task"}
    assert adapter.validate_python({"kind": "work_state_projection", **fields}) == _SCOPE
    for bad in (
        {"kind": "other"},
        {"kind": "memory_plane_candidate", "domain": "skill"},
        {"kind": "protected_skill_candidate", "domain": "semantic"},
        {"kind": "work_state_projection", "domain": "episodic"},
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python({**bad, **fields})


def test_claim_rolls_forward_with_fixed_delay_and_budget() -> None:
    first, initial_claim = _claim(_pending())
    pending = record_delivery_failure(
        first, claim=initial_claim, context=_CONTEXT, now=_NOW, outcome="transient"
    )
    assert pending.progress == PendingDelivery(next_retry_at=_NOW + timedelta(seconds=1))
    with pytest.raises(DeliveryTransitionError, match="not due"):
        _claim(pending)

    second_time = _NOW + timedelta(seconds=1)
    second, second_claim = _claim(pending, now=second_time)
    assert second_claim.fence_token > initial_claim.fence_token
    assert second_claim.expires_at == second_time + timedelta(seconds=30)
    with pytest.raises(DeliveryTransitionError, match="still current"):
        recover_delivery_claim(second, context=_CONTEXT, now=second_time)

    recovered = recover_delivery_claim(second, context=_CONTEXT, now=second_claim.expires_at)
    final_time = second_claim.expires_at + timedelta(seconds=2)
    assert recovered.progress == PendingDelivery(next_retry_at=final_time)
    third, final_claim = _claim(recovered, now=final_time)
    with pytest.raises(DeliveryTransitionError, match="claim is stale"):
        record_delivery_failure(
            third, claim=second_claim, context=_CONTEXT, now=final_time, outcome="denied"
        )
    exhausted = record_delivery_failure(
        third, claim=final_claim, context=_CONTEXT, now=final_time, outcome="transient"
    )
    assert exhausted.progress == UnresolvedDelivery(reason="retry_exhausted")
    assert exhausted.attempt_count == 3
    with pytest.raises(DeliveryTransitionError, match="only a pending"):
        _claim(exhausted, now=final_time)


def test_target_receipt_binds_exact_effect_and_scope() -> None:
    claimed, claim = _claim(_pending())
    other_scope = MemoryPlaneCandidateScope(
        partition_id="partition", task_id="task", domain="semantic"
    )
    for invalid in (
        _RECEIPT.model_copy(update={"scope": other_scope, "target_kind": "writeback_candidate"}),
        _RECEIPT.model_copy(update={"request_digest": "d" * 64}),
        _RECEIPT.model_copy(update={"effect": _EFFECT.model_copy(update={"revision": 2})}),
        _RECEIPT.model_copy(update={"generation_id": "restored"}),
    ):
        with pytest.raises(DeliveryTransitionError, match="integrity_error"):
            complete_delivery(
                claimed, claim=claim, context=_CONTEXT, current_authority=_AUTHORITY,
                now=_NOW, receipt=invalid, effect=_EFFECT,
            )
    delivered = complete_delivery(
        claimed, claim=claim, context=_CONTEXT, current_authority=_AUTHORITY,
        now=_NOW, receipt=_RECEIPT, effect=_EFFECT,
    )
    assert delivered.progress == DeliveredDelivery(receipt=_RECEIPT)
    assert ManagedDelivery.model_validate_json(delivered.model_dump_json()) == delivered
    with pytest.raises(DeliveryTransitionError, match="stale"):
        record_delivery_failure(
            delivered, claim=claim, context=_CONTEXT, now=_NOW, outcome="transient"
        )


def test_pause_revocation_and_generation_changes_block_effect() -> None:
    claimed, claim = _claim(_pending())
    for context, authority, why in (
        (_CONTEXT.model_copy(update={"mode": "read_only"}), _AUTHORITY, "active mode"),
        (_CONTEXT.model_copy(update={"mode": "bypass"}), _AUTHORITY, "active mode"),
        (_CONTEXT.model_copy(update={"eligibility_epoch": 2}), _AUTHORITY, "claim is stale"),
        (_CONTEXT.model_copy(update={"generation_id": "restored"}), _AUTHORITY, "another generation"),
        (_CONTEXT, _AUTHORITY.model_copy(update={"grant_epoch": 2}), "authority does not match"),
    ):
        with pytest.raises(DeliveryTransitionError, match=why):
            complete_delivery(
                claimed, claim=claim, context=context, current_authority=authority,
                now=_NOW, receipt=_RECEIPT, effect=_EFFECT,
            )
    rejected = reject_pending_delivery(_pending(), context=_CONTEXT, reason="forgotten")
    assert rejected.progress == RejectedDelivery(reason="forgotten")
    assert rejected.attempt_count == 0
