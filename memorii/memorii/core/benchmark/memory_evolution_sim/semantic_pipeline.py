"""Visible-only semantic validation and graph-channel compilation for the simulator."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    SimSemanticDecision,
    SimSystemOutput,
    VisibleClaimCandidate,
)
from memorii.core.benchmark.memory_evolution_sim.utils import ordered_unique

_NONCURRENT_STATES = {"superseded", "invalidated", "expired", "archived", "evidence_only"}


class SimSemanticViolationCode(StrEnum):
    INVALID_CLAIM_ID = "invalid_claim_id"
    INVALID_RELATION_ID = "invalid_relation_id"
    INVALID_UNCERTAIN_ID = "invalid_uncertain_id"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    SELECTED_NOT_CONSIDERED = "selected_not_considered"
    EMPTY_SELECTION = "empty_selection"
    STALE_SELECTED_CLAIM = "stale_selected_claim"
    NON_ACTION_SELECTED_FOR_EXECUTION = "non_action_selected_for_execution"
    INACTIVE_ACTION_SELECTED_FOR_EXECUTION = "inactive_action_selected_for_execution"
    BELIEF_RANKING_REQUIRED = "belief_ranking_required"
    BELIEF_RANKING_REFERENCES_UNCONSIDERED = "belief_ranking_references_unconsidered"


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
    """Return machine-readable semantic violations without rewriting the decision."""

    claims = {claim.claim_id: claim for claim in context.visible_claims}
    claim_ids = set(claims)
    relation_ids = set(context.visible_relation_ids)
    event_ids = {event.event_id for event in context.visible_events}
    entity_ids = set(context.visible_entity_ids)
    all_ids = claim_ids | relation_ids | event_ids | entity_ids
    violations: list[SimSemanticViolationCode] = []
    referenced_claims = {
        *semantic.selected_claim_ids,
        *semantic.considered_claim_ids,
        *semantic.belief_ranking_ids,
    }
    if referenced_claims - claim_ids:
        violations.append(SimSemanticViolationCode.INVALID_CLAIM_ID)
    if set(semantic.relevant_relation_ids) - relation_ids:
        violations.append(SimSemanticViolationCode.INVALID_RELATION_ID)
    if set(semantic.uncertain_ids) - all_ids:
        violations.append(SimSemanticViolationCode.INVALID_UNCERTAIN_ID)
    if semantic.operation not in set(context.checkpoint.task_contract.allowed_operations) | {"abstain"}:
        violations.append(SimSemanticViolationCode.OPERATION_NOT_ALLOWED)
    if set(semantic.selected_claim_ids) - set(semantic.considered_claim_ids):
        violations.append(SimSemanticViolationCode.SELECTED_NOT_CONSIDERED)
    if semantic.operation != "abstain" and not semantic.selected_claim_ids:
        violations.append(SimSemanticViolationCode.EMPTY_SELECTION)
    if not context.checkpoint.task_contract.allow_stale_selected_claims and any(
        claims[item].lifecycle_state in _NONCURRENT_STATES for item in semantic.selected_claim_ids if item in claims
    ):
        violations.append(SimSemanticViolationCode.STALE_SELECTED_CLAIM)
    if semantic.operation == "next_action" and any(
        claims[item].predicate_id not in {"action_state", "status", "progress"}
        and "action" not in claims[item].predicate_id
        for item in semantic.selected_claim_ids
        if item in claims
    ):
        violations.append(SimSemanticViolationCode.NON_ACTION_SELECTED_FOR_EXECUTION)
    if semantic.operation == "next_action" and any(
        claims[item].lifecycle_state != "active"
        or claims[item].object_value.casefold() in {"blocked", "abandoned", "archived", "cancelled", "completed"}
        for item in semantic.selected_claim_ids
        if item in claims
    ):
        violations.append(SimSemanticViolationCode.INACTIVE_ACTION_SELECTED_FOR_EXECUTION)
    if context.checkpoint.task_contract.belief_ranking_policy == "required" and not semantic.belief_ranking_ids:
        violations.append(SimSemanticViolationCode.BELIEF_RANKING_REQUIRED)
    if set(semantic.belief_ranking_ids) - set(semantic.considered_claim_ids):
        violations.append(SimSemanticViolationCode.BELIEF_RANKING_REFERENCES_UNCONSIDERED)
    return SimSemanticValidation(violation_codes=list(dict.fromkeys(violations)))


def compile_sim_semantic_decision(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    semantic: SimSemanticDecision,
) -> SimSystemOutput:
    """Compile semantic choices using visible cards and the public task contract only."""

    validation = validate_sim_semantic_decision(context=context, semantic=semantic)
    if not validation.valid:
        codes = ",".join(code.value for code in validation.violation_codes)
        raise ValueError(f"invalid simulator semantic decision: {codes}")

    claims = {claim.claim_id: claim for claim in context.visible_claims}
    relations = {relation.relation_id: relation for relation in context.visible_relations}
    selected = ordered_unique(semantic.selected_claim_ids)
    if context.checkpoint.task_contract.definition_claim_placement == "selected_and_supporting_required":
        selected = ordered_unique([*selected, *_required_definition_claim_ids(claims, selected)])
    selected_set = set(selected)
    considered = ordered_unique([*semantic.considered_claim_ids, *selected])
    rejected = [
        claim_id
        for claim_id in considered
        if claim_id not in selected_set
        and claim_id in claims
        and claims[claim_id].lifecycle_state in _NONCURRENT_STATES
    ]
    context_claims = [
        claim_id for claim_id in considered if claim_id not in selected_set and claim_id not in set(rejected)
    ]
    if context.checkpoint.task_contract.wrong_entity_claims_belong_in:
        rejected = ordered_unique([*rejected, *context_claims])

    selected_entities = _selected_entity_ids(
        claims=claims,
        selected_claim_ids=selected,
        policy=context.checkpoint.task_contract.selected_entity_role_policy,
    )
    rejected_entities = _claim_subject_ids(claims, rejected, excluded=set(selected_entities))
    context_entities = _claim_subject_ids(
        claims,
        context_claims,
        excluded=set(selected_entities),
    )
    if context.checkpoint.task_contract.wrong_entity_claims_belong_in:
        context_entities = ordered_unique([*context_entities, *rejected_entities])

    relevant_relations = ordered_unique(semantic.relevant_relation_ids)
    selected_relations: list[str] = []
    supporting_relations: list[str] = []
    context_relations: list[str] = []
    rejected_relations: list[str] = []
    relation_channels = set(context.checkpoint.task_contract.conflict_relation_ids_belong_in)
    for relation_id in relevant_relations:
        relation = relations[relation_id]
        if relation.lifecycle_state in _NONCURRENT_STATES:
            rejected_relations.append(relation_id)
            continue
        if "supporting_relation_ids" in relation_channels:
            supporting_relations.append(relation_id)
        if "context_relation_ids" in relation_channels:
            context_relations.append(relation_id)
        if semantic.operation == "graph_reconstruction" and not {
            "supporting_relation_ids",
            "context_relation_ids",
        }.issubset(relation_channels):
            selected_relations.append(relation_id)
            supporting_relations.append(relation_id)

    supporting_citations = _claim_evidence_ids(claims, selected)
    rejection_citations = _claim_evidence_ids(claims, rejected)
    context_citations = _claim_evidence_ids(claims, context_claims)
    output = SimSystemOutput(
        operation=semantic.operation,
        belief_ranking_ids=ordered_unique(semantic.belief_ranking_ids),
        selected_entity_ids=selected_entities,
        selected_claim_ids=selected,
        selected_relation_ids=ordered_unique(selected_relations),
        supporting_claim_ids=list(selected),
        supporting_relation_ids=ordered_unique(supporting_relations),
        supporting_citation_event_ids=supporting_citations,
        rejected_entity_ids=rejected_entities,
        rejected_claim_ids=ordered_unique(rejected),
        rejected_relation_ids=ordered_unique(rejected_relations),
        rejection_citation_event_ids=rejection_citations,
        context_entity_ids=context_entities,
        context_claim_ids=ordered_unique(context_claims),
        context_relation_ids=ordered_unique(context_relations),
        context_citation_event_ids=context_citations,
        answer=semantic.answer,
        next_action=semantic.next_action,
        uncertain_ids=ordered_unique(semantic.uncertain_ids),
        confidence=semantic.confidence,
        rationale=semantic.rationale,
    )
    _validate_compiled_channel_algebra(output)
    return output


def render_sim_answer(
    *,
    output: SimSystemOutput,
    semantic: SimSemanticDecision,
) -> SimSystemOutput:
    """Render scalar response text without changing compiled graph channels."""

    return output.model_copy(update={"answer": semantic.answer, "next_action": semantic.next_action})


def project_rejected_sim_semantic_decision(
    semantic: SimSemanticDecision,
) -> SimSystemOutput:
    """Preserve rejected model choices without deriving trusted graph channels."""

    selected_claim_ids = ordered_unique(semantic.selected_claim_ids)
    selected_claim_set = set(selected_claim_ids)
    return SimSystemOutput(
        operation=semantic.operation,
        belief_ranking_ids=ordered_unique(semantic.belief_ranking_ids),
        selected_claim_ids=selected_claim_ids,
        selected_relation_ids=ordered_unique(semantic.relevant_relation_ids),
        context_claim_ids=[
            claim_id
            for claim_id in ordered_unique(semantic.considered_claim_ids)
            if claim_id not in selected_claim_set
        ],
        answer=semantic.answer,
        next_action=semantic.next_action,
        uncertain_ids=ordered_unique(semantic.uncertain_ids),
        confidence=semantic.confidence,
        rationale=semantic.rationale,
    )


def _required_definition_claim_ids(
    claims: dict[str, VisibleClaimCandidate],
    selected_claim_ids: list[str],
) -> list[str]:
    selected_subjects = {
        claims[item].subject_entity_id
        for item in selected_claim_ids
        if item in claims and claims[item].predicate_id != "entity_type"
    }
    return [
        claim.claim_id
        for claim in claims.values()
        if claim.predicate_id == "entity_type" and claim.subject_entity_id in selected_subjects
    ]


def _selected_entity_ids(
    *,
    claims: dict[str, VisibleClaimCandidate],
    selected_claim_ids: list[str],
    policy: str,
) -> list[str]:
    if policy == "audit_graph_entities":
        return []
    entity_ids: list[str] = []
    for claim_id in selected_claim_ids:
        claim = claims[claim_id]
        if policy in {"subject", "subject_and_object", "active_graph_subjects"}:
            entity_ids.append(claim.subject_entity_id)
        if policy in {"object", "subject_and_object"} and claim.object_entity_id:
            entity_ids.append(claim.object_entity_id)
    return ordered_unique(entity_ids)


def _claim_subject_ids(
    claims: dict[str, VisibleClaimCandidate],
    claim_ids: list[str],
    *,
    excluded: set[str],
) -> list[str]:
    return ordered_unique(
        [
            claims[item].subject_entity_id
            for item in claim_ids
            if item in claims and claims[item].subject_entity_id not in excluded
        ]
    )


def _claim_evidence_ids(
    claims: dict[str, VisibleClaimCandidate],
    claim_ids: list[str],
) -> list[str]:
    return ordered_unique(
        [event_id for claim_id in claim_ids if claim_id in claims for event_id in claims[claim_id].evidence_event_ids]
    )


def _validate_compiled_channel_algebra(output: SimSystemOutput) -> None:
    selected_claims = set(output.selected_claim_ids)
    supporting_claims = set(output.supporting_claim_ids)
    rejected_claims = set(output.rejected_claim_ids)
    if selected_claims != supporting_claims:
        raise ValueError("compiled selected and supporting claim channels must agree")
    if (selected_claims | supporting_claims) & rejected_claims:
        raise ValueError("compiled direct-support claims cannot also be rejected")
    if set(output.selected_entity_ids) & set(output.rejected_entity_ids):
        raise ValueError("compiled selected entities cannot also be rejected")
    if set(output.selected_relation_ids) & set(output.rejected_relation_ids):
        raise ValueError("compiled selected relations cannot also be rejected")
