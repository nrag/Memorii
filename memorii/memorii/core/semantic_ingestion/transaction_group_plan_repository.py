"""Atomic-store read view for coordinator-owned transaction group plans.

Plans are published only as a member of the source's planned checkpoint.  This
module deliberately exposes no standalone write operation: a plan that is not
in the same atomic generation as the progress which first names it is not
planning authority.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Protocol

from memorii.core.memory_evolution.atomic_store import AtomicGenerationMember
from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
    decode_typed_value,
)
from memorii.core.semantic_ingestion.contracts import (
    TransactionSemanticGroupPlan,
    TransactionSemanticGroupPlanReference,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
)

TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_ID = "semantic_ingestion.transaction_group_plans"
TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_CONTRACT_FINGERPRINT = contract_digest(
    b"memorii.semantic-ingestion.transaction-group-plan-repository.v1",
    {
        "repository_id": TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_ID,
        "member_kind": "plan",
        "publication": "planned_checkpoint_only",
        "schema": "transaction_semantic_group_plan",
    },
)


class _AtomicPlanStore(Protocol):
    def get_operation(self, operation_fence: OperationFenceBinding): ...

    def generation_members(
        self, operation_fence: OperationFenceBinding, generation: int
    ) -> tuple[AtomicGenerationMember, ...]: ...


class TransactionSemanticGroupPlanRepository(Protocol):
    """Read one complete, atomically published plan by its typed reference."""

    def reference_for(
        self, plan: TransactionSemanticGroupPlan
    ) -> TransactionSemanticGroupPlanReference: ...

    def checkpoint_member(self, plan: TransactionSemanticGroupPlan) -> AtomicGenerationMember: ...

    def get(
        self, reference: TransactionSemanticGroupPlanReference
    ) -> TransactionSemanticGroupPlan: ...


class AtomicStoreTransactionSemanticGroupPlanRepository:
    """Fence-bound typed plan view over one source's atomic-store generations."""

    def __init__(self, *, atomic_store: _AtomicPlanStore, operation_fence: OperationFenceBinding) -> None:
        self._atomic_store = atomic_store
        self._operation_fence = operation_fence

    @staticmethod
    def reference_for(
        plan: TransactionSemanticGroupPlan,
    ) -> TransactionSemanticGroupPlanReference:
        validated = TransactionSemanticGroupPlan.model_validate(plan.model_dump(mode="python"))
        return TransactionSemanticGroupPlanReference(
            plan_id=validated.plan_id,
            plan_digest=validated.plan_digest,
            repository_id=TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_ID,
            repository_contract_fingerprint=(
                TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_CONTRACT_FINGERPRINT
            ),
        )

    @staticmethod
    def checkpoint_member(plan: TransactionSemanticGroupPlan) -> AtomicGenerationMember:
        """Encode the sole plan member to be included in a planned checkpoint.

        The caller still has to submit this member through the atomic checkpoint
        request.  Returning a member instead of writing here prevents a racing
        plan-only publication path.
        """
        validated = TransactionSemanticGroupPlan.model_validate(plan.model_dump(mode="python"))
        payload = encode_semantic_contract(validated)
        return AtomicGenerationMember(
            member_id="semantic-ingestion-plan",
            kind="plan",
            canonical_payload=payload,
            payload_digest=sha256(payload).hexdigest(),
        )

    def get(
        self, reference: TransactionSemanticGroupPlanReference
    ) -> TransactionSemanticGroupPlan:
        if (
            reference.repository_id != TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_ID
            or reference.repository_contract_fingerprint
            != TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_CONTRACT_FINGERPRINT
        ):
            raise ValueError("transaction group plan reference names another repository")
        control = self._atomic_store.get_operation(self._operation_fence)
        matches: list[TransactionSemanticGroupPlan] = []
        for generation in range(2, control.generation + 1):
            for member in self._atomic_store.generation_members(self._operation_fence, generation):
                if member.kind != "plan":
                    continue
                try:
                    envelope = decode_typed_value(member.canonical_payload)
                except (TypeError, ValueError) as exc:
                    raise ValueError("transaction group plan member is undecodable") from exc
                if not isinstance(envelope, dict) or envelope.get("kind") != "transaction_semantic_group_plan":
                    # The pre-lineage terminal marker is deliberately not
                    # planning authority for a typed reference.
                    continue
                try:
                    plan = decode_semantic_contract(
                        member.canonical_payload, TransactionSemanticGroupPlan
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError("transaction group plan member is invalid") from exc
                if encode_semantic_contract(plan) != member.canonical_payload:
                    raise ValueError("transaction group plan member is not canonical")
                if plan.plan_id == reference.plan_id:
                    matches.append(plan)
        if len(matches) != 1:
            raise ValueError("transaction group plan reference is absent or ambiguous")
        plan = matches[0]
        if plan.plan_digest != reference.plan_digest:
            raise ValueError("transaction group plan digest is inconsistent")
        return TransactionSemanticGroupPlan.model_validate(plan.model_dump(mode="python"))


__all__ = [
    "AtomicStoreTransactionSemanticGroupPlanRepository",
    "TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_CONTRACT_FINGERPRINT",
    "TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_ID",
    "TransactionSemanticGroupPlanRepository",
]
