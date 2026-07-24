"""Visible-only semantic validation and deterministic simulator compilation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from memorii.core.benchmark.memory_evolution_sim.channel_contract import (
    require_valid_channel_algebra,
    selected_entity_ids_for_claims,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    SimClaimSemanticRole,
    SimSemanticDecision,
    SimSystemOutput,
    VisibleClaimCandidate,
    VisibleRelationCandidate,
)
from memorii.core.benchmark.memory_evolution_sim.utils import ordered_unique
from memorii.core.benchmark.memory_evolution_sim.visible_graph_closure import (
    derive_visible_graph_closure,
)
from memorii.core.benchmark.task_conditioned_fields import (
    TaskFieldPresencePolicy,
    TaskFieldPresenceViolation,
    task_field_presence_violation,
    task_operation_allowed,
)

_NONCURRENT_STATES = {"superseded", "invalidated", "expired", "archived", "evidence_only"}
_CONFLICT_RELATION_TYPES = {"contradicts", "corrects", "supersedes"}


class SimSemanticViolationCode(StrEnum):
    INVALID_CLAIM_ID = "invalid_claim_id"
    MISSING_CLAIM_ASSESSMENT = "missing_claim_assessment"
    DUPLICATE_CLAIM_ASSESSMENT = "duplicate_claim_assessment"
    INVALID_UNCERTAIN_ID = "invalid_uncertain_id"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    EMPTY_PRIMARY_SELECTION = "empty_primary_selection"
    STALE_SELECTED_CLAIM = "stale_selected_claim"
    NON_ACTION_SELECTED_FOR_EXECUTION = "non_action_selected_for_execution"
    INACTIVE_ACTION_SELECTED_FOR_EXECUTION = "inactive_action_selected_for_execution"
    BELIEF_RANKING_REQUIRED = "belief_ranking_required"
    BELIEF_RANKING_FORBIDDEN = "belief_ranking_forbidden"
    BELIEF_RANKING_INVALID = "belief_ranking_invalid"


class SimSemanticValidation(BaseModel):
    violation_codes: list[SimSemanticViolationCode]

    model_config = ConfigDict(extra="forbid")

    @property
    def valid(self) -> bool:
        return not self.violation_codes


def validate_sim_semantic_decision(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    semantic: SimSemanticDecision,
) -> SimSemanticValidation:
    """Validate exhaustive semantic judgments without rewriting them."""

    claims = {claim.claim_id: claim for claim in context.visible_claims}
    visible_claim_ids = set(claims)
    assessment_ids = [assessment.claim_id for assessment in semantic.claim_assessments]
    assessment_id_set = set(assessment_ids)
    primary_ids = [
        assessment.claim_id
        for assessment in semantic.claim_assessments
        if assessment.role == SimClaimSemanticRole.PRIMARY
    ]
    ranked = [assessment for assessment in semantic.claim_assessments if assessment.belief_rank is not None]
    all_visible_ids = (
        visible_claim_ids
        | set(context.visible_relation_ids)
        | set(context.visible_entity_ids)
        | {event.event_id for event in context.visible_events}
    )
    violations: list[SimSemanticViolationCode] = []

    if assessment_id_set - visible_claim_ids:
        violations.append(SimSemanticViolationCode.INVALID_CLAIM_ID)
    if visible_claim_ids - assessment_id_set:
        violations.append(SimSemanticViolationCode.MISSING_CLAIM_ASSESSMENT)
    if len(assessment_ids) != len(assessment_id_set):
        violations.append(SimSemanticViolationCode.DUPLICATE_CLAIM_ASSESSMENT)
    if set(semantic.uncertain_ids) - all_visible_ids:
        violations.append(SimSemanticViolationCode.INVALID_UNCERTAIN_ID)
    if not task_operation_allowed(
        allowed_operations=context.checkpoint.task_contract.allowed_operations,
        operation=semantic.operation,
    ):
        violations.append(SimSemanticViolationCode.OPERATION_NOT_ALLOWED)
    if semantic.operation != "abstain" and not primary_ids:
        violations.append(SimSemanticViolationCode.EMPTY_PRIMARY_SELECTION)
    if not context.checkpoint.task_contract.allow_stale_selected_claims and any(
        claims[item].lifecycle_state in _NONCURRENT_STATES for item in primary_ids if item in claims
    ):
        violations.append(SimSemanticViolationCode.STALE_SELECTED_CLAIM)
    if semantic.operation == "next_action" and any(
        claims[item].predicate_id not in {"action_state", "status", "progress"}
        and "action" not in claims[item].predicate_id
        for item in primary_ids
        if item in claims
    ):
        violations.append(SimSemanticViolationCode.NON_ACTION_SELECTED_FOR_EXECUTION)
    if semantic.operation == "next_action" and any(
        claims[item].lifecycle_state != "active"
        or claims[item].object_value.casefold() in {"blocked", "abandoned", "archived", "cancelled", "completed"}
        for item in primary_ids
        if item in claims
    ):
        violations.append(SimSemanticViolationCode.INACTIVE_ACTION_SELECTED_FOR_EXECUTION)

    ranking_presence = task_field_presence_violation(
        policy=TaskFieldPresencePolicy(context.checkpoint.task_contract.belief_ranking_policy),
        item_count=len(ranked),
    )
    if ranking_presence == TaskFieldPresenceViolation.REQUIRED_MISSING:
        violations.append(SimSemanticViolationCode.BELIEF_RANKING_REQUIRED)
    elif ranking_presence == TaskFieldPresenceViolation.FORBIDDEN_PRESENT:
        violations.append(SimSemanticViolationCode.BELIEF_RANKING_FORBIDDEN)
    ranks = [assessment.belief_rank for assessment in ranked]
    if ranked and (
        any(assessment.role == SimClaimSemanticRole.IRRELEVANT for assessment in ranked)
        or len(ranks) != len(set(ranks))
        or set(ranks) != set(range(1, len(ranks) + 1))
    ):
        violations.append(SimSemanticViolationCode.BELIEF_RANKING_INVALID)
    return SimSemanticValidation(violation_codes=list(dict.fromkeys(violations)))


def compile_sim_semantic_decision(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    semantic: SimSemanticDecision,
) -> SimSystemOutput:
    """Compile semantic assessments using visible cards and the task contract."""

    validation = validate_sim_semantic_decision(context=context, semantic=semantic)
    if not validation.valid:
        codes = ",".join(code.value for code in validation.violation_codes)
        raise ValueError(f"invalid simulator semantic decision: {codes}")

    claims = {claim.claim_id: claim for claim in context.visible_claims}
    relations = {relation.relation_id: relation for relation in context.visible_relations}
    closure = derive_visible_graph_closure(
        context=context,
        assessments=semantic.claim_assessments,
    )
    selected = list(closure.primary_claim_ids)
    selected_subjects = {
        claims[item].subject_entity_id for item in selected if claims[item].predicate_id != "entity_type"
    }
    if context.checkpoint.task_contract.definition_claim_placement == "selected_and_supporting_required":
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
        if claim.lifecycle_state in _NONCURRENT_STATES:
            rejected_claims.append(claim_id)
            continue
        if claim.predicate_id == "entity_type":
            context_claims.append(claim_id)
            continue
        if claim.subject_entity_id not in selected_subjects:
            placement = context.checkpoint.task_contract.wrong_entity_claim_placement
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
    context_entities = [item for item in ordered_unique(context_entities) if item not in set(selected_entities)]
    rejected_entities = _claim_subject_ids(claims, rejected_claims)
    rejected_entities.extend(_relation_entity_ids(relations, rejected_relations))
    occupied_entities = set(selected_entities) | set(context_entities)
    rejected_entities = [item for item in ordered_unique(rejected_entities) if item not in occupied_entities]

    supporting_citations = _claim_evidence_ids(claims, selected)
    context_citations = [
        item for item in _claim_evidence_ids(claims, context_claims) if item not in set(supporting_citations)
    ]
    occupied_citations = set(supporting_citations) | set(context_citations)
    rejection_citations = [
        item for item in _claim_evidence_ids(claims, rejected_claims) if item not in occupied_citations
    ]
    ranked_assessments = sorted(
        (assessment for assessment in semantic.claim_assessments if assessment.belief_rank is not None),
        key=lambda assessment: assessment.belief_rank or 0,
    )
    output = SimSystemOutput(
        operation=semantic.operation,
        belief_ranking_ids=[assessment.claim_id for assessment in ranked_assessments],
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

    return output.model_copy(update={"answer": semantic.answer, "next_action": semantic.next_action})


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
        if relation.lifecycle_state in _NONCURRENT_STATES:
            rejected.append(relation_id)
            continue
        placement = (
            conflict_placement
            if relation.relation_type in _CONFLICT_RELATION_TYPES
            else "selected_and_supporting"
            if semantic.operation == "graph_reconstruction"
            else "context"
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
    return ordered_unique([event_id for claim_id in claim_ids for event_id in claims[claim_id].evidence_event_ids])
