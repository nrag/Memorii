"""Visible-only mechanical claim policy for simulator decisions."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.schemas import VisibleClaimCandidate

NONCURRENT_CLAIM_STATES = frozenset(
    {"superseded", "invalidated", "expired", "archived", "evidence_only"}
)
TERMINAL_ACTION_VALUES = frozenset(
    {"blocked", "abandoned", "archived", "cancelled", "completed"}
)
ACTION_PREDICATES = frozenset({"action_state", "status", "progress"})


def is_noncurrent_claim(claim: VisibleClaimCandidate) -> bool:
    return claim.lifecycle_state in NONCURRENT_CLAIM_STATES


def is_action_claim(claim: VisibleClaimCandidate) -> bool:
    return claim.predicate_id in ACTION_PREDICATES or "action" in claim.predicate_id


def is_execution_eligible_claim(claim: VisibleClaimCandidate) -> bool:
    return (
        is_action_claim(claim)
        and not is_noncurrent_claim(claim)
        and claim.lifecycle_state == "active"
        and claim.object_value.casefold() not in TERMINAL_ACTION_VALUES
    )


def is_identity_confusion_bridge(
    left: VisibleClaimCandidate,
    right: VisibleClaimCandidate,
) -> bool:
    return (
        left.subject_entity_id != right.subject_entity_id
        and left.predicate_id == right.predicate_id
        and left.object_entity_id is not None
        and left.object_entity_id == right.object_entity_id
        and (is_noncurrent_claim(left) or is_noncurrent_claim(right))
    )
