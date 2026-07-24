"""Deterministic bounded closure over model-visible simulator cards."""

from __future__ import annotations

from dataclasses import dataclass

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    SimClaimAssessment,
    SimClaimSemanticRole,
    VisibleClaimCandidate,
    VisibleRelationCandidate,
)


@dataclass(frozen=True)
class VisibleGraphClosure:
    primary_claim_ids: tuple[str, ...]
    relevant_claim_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]


def derive_visible_graph_closure(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    assessments: list[SimClaimAssessment],
) -> VisibleGraphClosure:
    """Close semantic claim judgments over visible lifecycle and graph edges."""

    claims = {claim.claim_id: claim for claim in context.visible_claims}
    primary = {
        assessment.claim_id
        for assessment in assessments
        if assessment.role == SimClaimSemanticRole.PRIMARY
    }
    relevant = {
        assessment.claim_id
        for assessment in assessments
        if assessment.role in {SimClaimSemanticRole.PRIMARY, SimClaimSemanticRole.RELEVANT}
    }

    for claim_id in tuple(primary):
        claim = claims[claim_id]
        relevant.update(
            candidate.claim_id
            for candidate in context.visible_claims
            if candidate.subject_entity_id == claim.subject_entity_id
            and candidate.predicate_id == claim.predicate_id
        )
        relevant.update(item for item in claim.contradicts_claim_ids if item in claims)
        relevant.update(
            candidate.claim_id
            for candidate in context.visible_claims
            if claim_id in candidate.contradicts_claim_ids
        )

    entity_ids = _claim_entity_ids(claims, relevant)
    relation_ids = {
        relation.relation_id
        for relation in context.visible_relations
        if _relation_incident_to(relation, claim_ids=relevant, entity_ids=entity_ids)
    }
    for relation in context.visible_relations:
        if relation.relation_id not in relation_ids:
            continue
        for endpoint_id, endpoint_type in (
            (relation.source_id, relation.source_type),
            (relation.target_id, relation.target_type),
        ):
            if endpoint_type in {"claim", "belief"} and endpoint_id in claims:
                relevant.add(endpoint_id)
            elif endpoint_type == "entity":
                entity_ids.add(endpoint_id)

    entity_ids.update(_claim_entity_ids(claims, relevant))
    relevant.update(
        claim.claim_id
        for claim in context.visible_claims
        if claim.predicate_id == "entity_type"
        and claim.lifecycle_state == "active"
        and claim.subject_entity_id in entity_ids
    )

    return VisibleGraphClosure(
        primary_claim_ids=tuple(_ordered_claim_ids(context.visible_claims, primary)),
        relevant_claim_ids=tuple(_ordered_claim_ids(context.visible_claims, relevant)),
        relation_ids=tuple(_ordered_relation_ids(context.visible_relations, relation_ids)),
    )


def _claim_entity_ids(
    claims: dict[str, VisibleClaimCandidate],
    claim_ids: set[str],
) -> set[str]:
    entity_ids = {claims[item].subject_entity_id for item in claim_ids}
    for claim_id in claim_ids:
        object_entity_id = claims[claim_id].object_entity_id
        if object_entity_id is not None:
            entity_ids.add(object_entity_id)
    return entity_ids


def _relation_incident_to(
    relation: VisibleRelationCandidate,
    *,
    claim_ids: set[str],
    entity_ids: set[str],
) -> bool:
    return (
        relation.source_id in claim_ids
        or relation.target_id in claim_ids
        or relation.source_id in entity_ids
        or relation.target_id in entity_ids
    )


def _ordered_claim_ids(
    claims: list[VisibleClaimCandidate],
    included: set[str],
) -> list[str]:
    return [
        claim.claim_id
        for claim in sorted(claims, key=_claim_sort_key)
        if claim.claim_id in included
    ]


def _ordered_relation_ids(
    relations: list[VisibleRelationCandidate],
    included: set[str],
) -> list[str]:
    return [
        relation.relation_id
        for relation in sorted(relations, key=_relation_sort_key)
        if relation.relation_id in included
    ]


def _claim_sort_key(claim: VisibleClaimCandidate) -> tuple[str, ...]:
    return (
        claim.subject_entity_type,
        claim.subject_name.casefold(),
        claim.predicate_id,
        claim.object_entity_type or "",
        claim.object_value.casefold(),
        claim.scope_key,
        claim.lifecycle_state,
        claim.valid_from.isoformat() if claim.valid_from else "",
        claim.valid_to.isoformat() if claim.valid_to else "",
        claim.claim_id,
    )


def _relation_sort_key(relation: VisibleRelationCandidate) -> tuple[str, ...]:
    return (
        relation.relation_type,
        relation.source_type,
        relation.source_label.casefold(),
        relation.target_type,
        relation.target_label.casefold(),
        relation.lifecycle_state,
        relation.relation_id,
    )
