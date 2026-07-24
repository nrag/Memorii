"""Contradiction-set helpers for memory evolution."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.models import ClaimState, ContradictionSet, ExtractedClaim
from memorii.core.memory_evolution.predicates import PredicatePolicy


class ContradictionResolver:
    def contradiction_for(
        self,
        *,
        policy: PredicatePolicy,
        claim: ExtractedClaim,
        existing_active: list[ClaimState],
        active_claim_id: str | None,
    ) -> ContradictionSet | None:
        conflicting = [
            state.claim_id
            for state in existing_active
            if state.claim_key.stable_id() == claim.claim_key.stable_id()
            and _norm(state.object_value) != _norm(claim.object_value)
        ]
        if not conflicting:
            return None
        conflicting_claim_ids = {claim.claim_id, *conflicting}
        if active_claim_id is not None:
            conflicting_claim_ids.discard(active_claim_id)
        now = datetime.now(UTC)
        return ContradictionSet(
            contradiction_set_id=_stable_id(
                "contradiction",
                f"{claim.claim_key.stable_id()}:{claim.claim_id}:{','.join(sorted(conflicting))}",
            ),
            predicate_id=policy.predicate_id,
            claim_key=claim.claim_key,
            active_claim_id=active_claim_id,
            conflicting_claim_ids=sorted(conflicting_claim_ids),
            rationale=f"claims disagree under predicate policy {policy.conflict_policy.value}",
            created_at=now,
            updated_at=now,
        )


def _norm(value: str) -> str:
    return " ".join(value.lower().strip(" .").split())


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"
