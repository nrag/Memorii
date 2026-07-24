"""Deterministic compilation of valid simulator semantic decisions."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.channel_contract import (
    require_valid_channel_algebra,
    selected_entity_ids_for_claims,
)
from memorii.core.benchmark.memory_evolution_sim.claim_policy import (
    NONCURRENT_CLAIM_STATES,
    is_noncurrent_claim,
)
from memorii.core.benchmark.memory_evolution_sim.decision_contract import (
    validate_sim_decision_contract,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    SimSemanticDecision,
    SimSystemOutput,
    VisibleClaimCandidate,
    VisibleRelationCandidate,
)
from memorii.core.benchmark.memory_evolution_sim.utils import ordered_unique
from memorii.core.benchmark.memory_evolution_sim.visible_graph_closure import (
    derive_visible_graph_closure,
)

_CONFLICT_RELATION_TYPES = {"contradicts", "corrects", "supersedes"}


def compile_sim_semantic_decision(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    semantic: SimSemanticDecision,
) -> SimSystemOutput:
    """Compile a contract-valid semantic decision into canonical graph channels."""

    validation = validate_sim_decision_contract(context=context, semantic=semantic)
    if not validation.valid:
        codes = ",".join(issue.code.value for issue in validation.issues)
        raise ValueError(f"invalid simulator semantic decision: {codes}")

    claims = {claim.claim_id: claim for claim in context.visible_claims}
    relations = {
        relation.relation_id: relation for relation in context.visible_relations
    }
    closure = derive_visible_graph_closure(
        context=context,
        assessments=semantic.claim_assessments,
    )
    selected = list(closure.primary_claim_ids)
    selected_subjects = {
        claims[item].subject_entity_id
        for item in selected
        if claims[item].predicate_id != "entity_type"
    }
    if (
        context.checkpoint.task_contract.definition_claim_placement
        == "selected_and_supporting_required"
    ):
        selected.extend(
            claim_id
            for claim_id in closure.relevant_claim_ids
            if claims[claim_id].predicate_id == "entity_type"
            and claims[claim_id].subject_entity_id in selected_subjects
        )
    selected = ordered_unique(selected)
    selected_set = set(selected)

    context_claims: list[str] = []
    rejected_claims: list[str] = []
    for claim_id in closure.relevant_claim_ids:
        if claim_id in selected_set:
            continue
        claim = claims[claim_id]
        if is_noncurrent_claim(claim):
            rejected_claims.append(claim_id)
            continue
        if claim.predicate_id == "entity_type":
            context_claims.append(claim_id)
            continue
        if claim.subject_entity_id not in selected_subjects:
            placement = (
                context.checkpoint.task_contract.wrong_entity_claim_placement
            )
            if placement == "rejected":
                rejected_claims.append(claim_id)
            elif placement == "context":
                context_claims.append(claim_id)
            continue
        context_claims.append(claim_id)

    (
        selected_relations,
        supporting_relations,
        context_relations,
        rejected_relations,
    ) = _relation_channels(
        semantic=semantic,
        relation_ids=closure.relation_ids,
        relations=relations,
        conflict_placement=context.checkpoint.task_contract.conflict_relation_placement,
    )

    selected_entities = selected_entity_ids_for_claims(
        selected_claims=[claims[item] for item in selected],
        role_policy=context.checkpoint.task_contract.selected_entity_role_policy,
    )
    context_entities = _claim_subject_ids(claims, context_claims)
    context_entities.extend(_relation_entity_ids(relations, context_relations))
    context_entities = [
        item
        for item in ordered_unique(context_entities)
        if item not in set(selected_entities)
    ]
    rejected_entities = _claim_subject_ids(claims, rejected_claims)
    rejected_entities.extend(_relation_entity_ids(relations, rejected_relations))
    occupied_entities = set(selected_entities) | set(context_entities)
    rejected_entities = [
        item
        for item in ordered_unique(rejected_entities)
        if item not in occupied_entities
    ]

    supporting_citations = _claim_evidence_ids(claims, selected)
    context_citations = [
        item
        for item in _claim_evidence_ids(claims, context_claims)
        if item not in set(supporting_citations)
    ]
    occupied_citations = set(supporting_citations) | set(context_citations)
    rejection_citations = [
        item
        for item in _claim_evidence_ids(claims, rejected_claims)
        if item not in occupied_citations
    ]
    ranked_assessments = sorted(
        (
            assessment
            for assessment in semantic.claim_assessments
            if assessment.belief_rank is not None
        ),
        key=lambda assessment: assessment.belief_rank or 0,
    )
    output = SimSystemOutput(
        operation=semantic.operation,
        belief_ranking_ids=[
            assessment.claim_id for assessment in ranked_assessments
        ],
        selected_entity_ids=selected_entities,
        selected_claim_ids=selected,
        selected_relation_ids=selected_relations,
        supporting_claim_ids=list(selected),
        supporting_relation_ids=supporting_relations,
        supporting_citation_event_ids=supporting_citations,
        rejected_entity_ids=rejected_entities,
        rejected_claim_ids=ordered_unique(rejected_claims),
        rejected_relation_ids=rejected_relations,
        rejection_citation_event_ids=rejection_citations,
        context_entity_ids=context_entities,
        context_claim_ids=ordered_unique(context_claims),
        context_relation_ids=context_relations,
        context_citation_event_ids=context_citations,
        answer=semantic.answer,
        next_action=semantic.next_action,
        uncertain_ids=ordered_unique(semantic.uncertain_ids),
        confidence=semantic.confidence,
        rationale=semantic.rationale,
    )
    require_valid_channel_algebra(output)
    return output


def render_sim_answer(
    *,
    output: SimSystemOutput,
    semantic: SimSemanticDecision,
) -> SimSystemOutput:
    """Render scalar response text without changing compiled graph channels."""

    return output.model_copy(
        update={"answer": semantic.answer, "next_action": semantic.next_action}
    )


def _relation_channels(
    *,
    semantic: SimSemanticDecision,
    relation_ids: tuple[str, ...],
    relations: dict[str, VisibleRelationCandidate],
    conflict_placement: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    selected: list[str] = []
    supporting: list[str] = []
    context: list[str] = []
    rejected: list[str] = []
    for relation_id in relation_ids:
        relation = relations[relation_id]
        if relation.lifecycle_state in NONCURRENT_CLAIM_STATES:
            rejected.append(relation_id)
            continue
        placement = (
            conflict_placement
            if relation.relation_type in _CONFLICT_RELATION_TYPES
            else (
                "selected_and_supporting"
                if semantic.operation == "graph_reconstruction"
                else "context"
            )
        )
        if placement == "selected_and_supporting":
            selected.append(relation_id)
            supporting.append(relation_id)
        elif placement == "supporting":
            supporting.append(relation_id)
        elif placement == "context":
            context.append(relation_id)
        elif placement == "rejected":
            rejected.append(relation_id)
        else:
            raise ValueError(f"unsupported relation placement: {placement}")
    return selected, supporting, context, rejected


def _claim_subject_ids(
    claims: dict[str, VisibleClaimCandidate],
    claim_ids: list[str],
) -> list[str]:
    return ordered_unique([claims[item].subject_entity_id for item in claim_ids])


def _relation_entity_ids(
    relations: dict[str, VisibleRelationCandidate],
    relation_ids: list[str],
) -> list[str]:
    result: list[str] = []
    for relation_id in relation_ids:
        relation = relations[relation_id]
        if relation.source_type == "entity":
            result.append(relation.source_id)
        if relation.target_type == "entity":
            result.append(relation.target_id)
    return ordered_unique(result)


def _claim_evidence_ids(
    claims: dict[str, VisibleClaimCandidate],
    claim_ids: list[str],
) -> list[str]:
    return ordered_unique(
        [
            event_id
            for claim_id in claim_ids
            for event_id in claims[claim_id].evidence_event_ids
        ]
    )
