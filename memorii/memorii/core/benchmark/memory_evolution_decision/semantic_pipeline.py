"""Deterministic compilation of curated memory-evolution semantic decisions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from memorii.core.benchmark.memory_evolution_decision.contracts import (
    MemoryEvolutionAnswerSelection,
    MemoryEvolutionBeliefScorePolicy,
    MemoryEvolutionDecision,
    MemoryEvolutionDecisionContext,
    MemoryEvolutionDecisionDomain,
    MemoryEvolutionDecisionOperation,
    MemoryEvolutionEventRole,
    MemoryEvolutionExecutionSelection,
    MemoryEvolutionLifecycleSnapshot,
    MemoryEvolutionMemoryKind,
    MemoryEvolutionRecordLifecycleState,
    MemoryEvolutionRetrievalContext,
    MemoryEvolutionSemanticDecision,
    MemoryEvolutionTemporalReference,
)
from memorii.core.benchmark.memory_evolution_decision.utils import dedupe_string_ids


class MemoryEvolutionSemanticViolationCode(StrEnum):
    INVALID_MEMORY_ID = "invalid_memory_id"
    INVALID_BELIEF_ID = "invalid_belief_id"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    DECISION_DOMAIN_MISMATCH = "decision_domain_mismatch"
    TEMPORAL_REFERENCE_MISMATCH = "temporal_reference_mismatch"
    SELECTED_NOT_CONSIDERED = "selected_not_considered"
    EMPTY_SELECTION = "empty_selection"
    COMMAND_SELECTED_AS_ACTION = "command_selected_as_action"
    NON_ACTION_SELECTED_FOR_EXECUTION = "non_action_selected_for_execution"
    STALE_SELECTED_FOR_CURRENT_QUERY = "stale_selected_for_current_query"
    FALSIFIED_BELIEF_SELECTED = "falsified_belief_selected"


class MemoryEvolutionSemanticValidation(BaseModel):
    violation_codes: list[MemoryEvolutionSemanticViolationCode]

    model_config = ConfigDict(extra="forbid")

    @property
    def valid(self) -> bool:
        return not self.violation_codes


def validate_memory_evolution_semantic_decision(
    *,
    context: MemoryEvolutionDecisionContext,
    semantic: MemoryEvolutionSemanticDecision,
) -> MemoryEvolutionSemanticValidation:
    """Validate semantic choices without changing them."""

    visible_by_id = {card.memory_id: card for card in context.visible_memory_cards}
    visible_ids = set(visible_by_id)
    violations: list[MemoryEvolutionSemanticViolationCode] = []
    referenced = {
        *semantic.selected_memory_ids,
        *semantic.considered_memory_ids,
        *(score.memory_id for score in semantic.belief_scores),
    }
    if referenced - visible_ids:
        violations.append(MemoryEvolutionSemanticViolationCode.INVALID_MEMORY_ID)
    if any(
        visible_by_id.get(score.memory_id) is not None
        and visible_by_id[score.memory_id].memory_kind != MemoryEvolutionMemoryKind.BELIEF
        for score in semantic.belief_scores
    ):
        violations.append(MemoryEvolutionSemanticViolationCode.INVALID_BELIEF_ID)
    expected_operation = (
        MemoryEvolutionDecisionOperation.NEXT_ACTION
        if context.decision_contract.requires_execution_selection
        else MemoryEvolutionDecisionOperation.ANSWER
    )
    if semantic.operation not in {expected_operation, MemoryEvolutionDecisionOperation.ABSTAIN}:
        violations.append(MemoryEvolutionSemanticViolationCode.OPERATION_NOT_ALLOWED)
    if semantic.query_temporal_frame.decision_domain != context.decision_contract.decision_domain:
        violations.append(MemoryEvolutionSemanticViolationCode.DECISION_DOMAIN_MISMATCH)
    if semantic.query_temporal_frame.temporal_reference != context.decision_contract.temporal_reference:
        violations.append(MemoryEvolutionSemanticViolationCode.TEMPORAL_REFERENCE_MISMATCH)
    if set(semantic.selected_memory_ids) - set(semantic.considered_memory_ids):
        violations.append(MemoryEvolutionSemanticViolationCode.SELECTED_NOT_CONSIDERED)
    if semantic.operation != MemoryEvolutionDecisionOperation.ABSTAIN and not semantic.selected_memory_ids:
        violations.append(MemoryEvolutionSemanticViolationCode.EMPTY_SELECTION)
    selected_cards = [visible_by_id[item] for item in semantic.selected_memory_ids if item in visible_by_id]
    if semantic.query_temporal_frame.decision_domain == MemoryEvolutionDecisionDomain.EXECUTION:
        if any(card.event_role == MemoryEvolutionEventRole.COMMAND_CONTEXT for card in selected_cards):
            violations.append(MemoryEvolutionSemanticViolationCode.COMMAND_SELECTED_AS_ACTION)
        if any(card.event_role != MemoryEvolutionEventRole.ACTION_STATE for card in selected_cards):
            violations.append(MemoryEvolutionSemanticViolationCode.NON_ACTION_SELECTED_FOR_EXECUTION)
    state_by_id = {card.memory_id: card for card in context.entity_state_cards}
    if semantic.query_temporal_frame.temporal_reference == MemoryEvolutionTemporalReference.CURRENT and any(
        state_by_id[item].record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_SUPERSEDED
        for item in semantic.selected_memory_ids
        if item in state_by_id
    ):
        violations.append(MemoryEvolutionSemanticViolationCode.STALE_SELECTED_FOR_CURRENT_QUERY)
    falsified = {score.memory_id for score in semantic.belief_scores if score.belief_state.value == "falsified"}
    if falsified & set(semantic.selected_memory_ids):
        violations.append(MemoryEvolutionSemanticViolationCode.FALSIFIED_BELIEF_SELECTED)
    return MemoryEvolutionSemanticValidation(violation_codes=list(dict.fromkeys(violations)))


def compile_memory_evolution_decision(
    *,
    context: MemoryEvolutionDecisionContext,
    semantic: MemoryEvolutionSemanticDecision,
) -> MemoryEvolutionDecision:
    """Compile visible semantic choices into mutually consistent output channels."""

    validation = validate_memory_evolution_semantic_decision(context=context, semantic=semantic)
    if not validation.valid:
        codes = ",".join(code.value for code in validation.violation_codes)
        raise ValueError(f"invalid memory-evolution semantic decision: {codes}")

    visible_by_id = {card.memory_id: card for card in context.visible_memory_cards}
    selected = dedupe_string_ids(semantic.selected_memory_ids)
    considered = dedupe_string_ids([*semantic.considered_memory_ids, *selected])
    considered_set = set(considered)
    selected_set = set(selected)
    state_by_id = {card.memory_id: card for card in context.entity_state_cards}
    selected_state_keys = {
        (state_by_id[item].entity_id, state_by_id[item].predicate) for item in selected if item in state_by_id
    }
    relevant_states = [
        card
        for card in context.entity_state_cards
        if card.memory_id in considered_set and (card.entity_id, card.predicate) in selected_state_keys
    ]
    active = [
        card.memory_id
        for card in relevant_states
        if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_ACTIVE
    ]
    superseded = [
        card.memory_id
        for card in relevant_states
        if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_SUPERSEDED
    ]
    retained = [
        card.memory_id
        for card in relevant_states
        if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_RETAINED
    ]
    if not relevant_states and semantic.query_temporal_frame.decision_domain == MemoryEvolutionDecisionDomain.FACT:
        if semantic.query_temporal_frame.temporal_reference == MemoryEvolutionTemporalReference.HISTORICAL:
            current_candidates = [item for item in considered if item not in selected_set and item in visible_by_id]
            if current_candidates:
                active = [
                    max(
                        current_candidates,
                        key=lambda item: (
                            visible_by_id[item].timestamp,
                            visible_by_id[item].trust_level,
                            item,
                        ),
                    )
                ]
            superseded = list(selected)
        else:
            active = list(selected)
            superseded = [item for item in considered if item not in selected_set]

    falsified = {score.memory_id for score in semantic.belief_scores if score.belief_state.value == "falsified"}
    evaluated_beliefs = [score.memory_id for score in semantic.belief_scores]
    if semantic.query_temporal_frame.decision_domain == MemoryEvolutionDecisionDomain.BELIEF:
        if context.decision_contract.belief_score_policy != MemoryEvolutionBeliefScorePolicy.RANKING_ONLY:
            active = dedupe_string_ids([*active, *(item for item in evaluated_beliefs if item not in falsified)])
        superseded = dedupe_string_ids([*superseded, *falsified])
        selected_evidence = [
            item for item in selected if visible_by_id[item].memory_kind == MemoryEvolutionMemoryKind.EVIDENCE
        ]
        active = dedupe_string_ids([*active, *selected_evidence])

    command_context: list[str] = []
    suppressed: list[str] = []
    if semantic.query_temporal_frame.decision_domain == MemoryEvolutionDecisionDomain.EXECUTION:
        active = list(selected)
        command_context = [
            item for item in considered if visible_by_id[item].event_role == MemoryEvolutionEventRole.COMMAND_CONTEXT
        ]
        retained = [
            item
            for item in considered
            if visible_by_id[item].event_role
            in {MemoryEvolutionEventRole.BLOCKED_STATE, MemoryEvolutionEventRole.ARCHIVED_STATE}
        ]
        suppressed = [
            item
            for item in considered
            if item not in selected_set
            and visible_by_id[item].event_role
            in {
                MemoryEvolutionEventRole.ACTION_STATE,
                MemoryEvolutionEventRole.BLOCKED_STATE,
                MemoryEvolutionEventRole.ARCHIVED_STATE,
            }
        ]
        superseded = [
            item for item in suppressed if visible_by_id[item].event_role == MemoryEvolutionEventRole.ACTION_STATE
        ]

    citations = [item for item in selected if visible_by_id[item].memory_kind != MemoryEvolutionMemoryKind.BELIEF]
    if semantic.query_temporal_frame.decision_domain == MemoryEvolutionDecisionDomain.BELIEF:
        for effect in context.evidence_effect_cards:
            if set(effect.supports_memory_ids) & selected_set:
                citations.append(effect.evidence_memory_id)
    citations = dedupe_string_ids(citations)

    rejected_candidates = (
        []
        if semantic.query_temporal_frame.temporal_reference == MemoryEvolutionTemporalReference.HISTORICAL
        else [item for item in considered if item not in selected_set]
    )
    rejected = dedupe_string_ids(
        [
            *rejected_candidates,
            *falsified,
            *suppressed,
        ]
    )
    historical = (
        list(selected)
        if semantic.query_temporal_frame.temporal_reference == MemoryEvolutionTemporalReference.HISTORICAL
        else []
    )
    query_context = dedupe_string_ids(
        [
            *(
                item
                for item in active
                if semantic.query_temporal_frame.temporal_reference == MemoryEvolutionTemporalReference.HISTORICAL
                and item not in selected_set
            ),
            *retained,
            *command_context,
        ]
    )
    rejected = [item for item in rejected if item not in selected_set]

    temporal_frame = semantic.query_temporal_frame
    execution = None
    if semantic.query_temporal_frame.decision_domain == MemoryEvolutionDecisionDomain.EXECUTION:
        execution = MemoryEvolutionExecutionSelection(
            selected_action_memory_ids=selected,
            active_work_state_memory_ids=active,
            command_context_memory_ids=command_context,
            suppressed_branch_memory_ids=suppressed,
            rationale="Compiled from visible event roles and the semantic action selection.",
        )
    return MemoryEvolutionDecision(
        operation=semantic.operation,
        answer=semantic.answer,
        next_action=semantic.next_action,
        confidence=semantic.confidence,
        query_temporal_frame=temporal_frame,
        answer_selection=MemoryEvolutionAnswerSelection(
            selected_memory_ids=selected,
            supporting_memory_ids=selected,
            citation_memory_ids=citations,
            temporal_reference=semantic.query_temporal_frame.temporal_reference,
            rationale="Compiled from the semantic selection.",
        ),
        lifecycle_snapshot=MemoryEvolutionLifecycleSnapshot(
            checkpoint_active_record_ids=dedupe_string_ids(active),
            checkpoint_superseded_record_ids=dedupe_string_ids(superseded),
            checkpoint_retained_record_ids=dedupe_string_ids(retained),
            evaluation_time=context.checkpoint.timestamp,
            rationale="Compiled from visible state cards, belief state, and event roles.",
        ),
        retrieval_context=MemoryEvolutionRetrievalContext(
            query_relevant_memory_ids=dedupe_string_ids([*selected, *citations, *query_context]),
            query_historical_memory_ids=historical,
            query_context_memory_ids=query_context,
            rejected_memory_ids=rejected,
            rationale="Compiled from considered alternatives and visible lifecycle context.",
        ),
        execution_selection=execution,
        evaluated_belief_ids=evaluated_beliefs,
        belief_scores=list(semantic.belief_scores),
        rationale=semantic.rationale,
        failure_mode=None,
        requires_judge_review=semantic.requires_judge_review,
    )


def render_memory_evolution_answer(
    *,
    decision: MemoryEvolutionDecision,
    semantic: MemoryEvolutionSemanticDecision,
) -> MemoryEvolutionDecision:
    """Render scalar answer fields without changing semantic or graph state."""

    return decision.model_copy(update={"answer": semantic.answer, "next_action": semantic.next_action})
