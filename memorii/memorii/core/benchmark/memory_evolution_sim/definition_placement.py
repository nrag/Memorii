"""Visible-context policy for placing entity-definition claims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
)

DefinitionChannel = Literal["selected_and_supporting", "context"]


@dataclass(frozen=True)
class DefinitionPlacement:
    claim_ids: tuple[str, ...]
    channel: DefinitionChannel


def definition_placement_for_selected_claims(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    selected_claim_ids: list[str] | tuple[str, ...],
) -> DefinitionPlacement:
    """Return the required channel for active definitions of selected facts."""

    claims = {claim.claim_id: claim for claim in context.visible_claims}
    selected_subjects = {
        claim.subject_entity_id
        for claim_id in selected_claim_ids
        if (claim := claims.get(claim_id)) is not None
    }
    definition_ids = tuple(
        claim.claim_id
        for claim in context.visible_claims
        if claim.predicate_id == "entity_type"
        and claim.lifecycle_state == "active"
        and claim.subject_entity_id in selected_subjects
    )
    channel: DefinitionChannel = (
        "selected_and_supporting"
        if context.checkpoint.task_contract.definition_claim_placement
        == "selected_and_supporting_required"
        else "context"
    )
    return DefinitionPlacement(claim_ids=definition_ids, channel=channel)
