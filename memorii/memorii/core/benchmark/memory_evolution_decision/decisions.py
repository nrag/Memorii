"""Decision-context construction and deterministic benchmark providers."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_decision.contracts import (
    MemoryEvolutionAnswerSelection,
    MemoryEvolutionBeliefScore,
    MemoryEvolutionBeliefState,
    MemoryEvolutionCheckpoint,
    MemoryEvolutionDecision,
    MemoryEvolutionDecisionContext,
    MemoryEvolutionDecisionOperation,
    MemoryEvolutionExecutionSelection,
    MemoryEvolutionLifecycleSnapshot,
    MemoryEvolutionRecordLifecycleState,
    MemoryEvolutionRetrievalContext,
    MemoryEvolutionScenario,
    MemoryEvolutionSemanticBeliefScore,
    MemoryEvolutionSemanticDecision,
    MemoryEvolutionTemporalReference,
    MemoryEvolutionVisibleCheckpoint,
)
from memorii.core.benchmark.memory_evolution_decision.policies import (
    evidence_effect_policy,
    expected_belief_ids,
    expected_rejected_memory_ids,
    lifecycle_expected_ids,
    output_channel_contract,
    temporal_grounding_policy,
    visible_decision_contract,
)
from memorii.core.benchmark.memory_evolution_decision.temporal_diagnostics import expected_temporal_frame
from memorii.core.benchmark.memory_evolution_decision.utils import dedupe_string_ids, extract_shallow_answer
from memorii.core.benchmark.memory_evolution_decision.visible_context import (
    command_context_ids,
    entity_resolution_cards_for_events,
    entity_state_cards_for_events,
    evidence_effect_cards_for_events,
    rank_events_by_shallow_overlap,
    temporal_anchor_cards_for_events,
    visible_events_for_checkpoint,
    visible_memory_cards_for_events,
)


def memory_evolution_context_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecisionContext:
    contract = visible_decision_contract(scenario=scenario, checkpoint=checkpoint)
    visible_events = visible_events_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    visible_memory_cards = visible_memory_cards_for_events(visible_events)
    entity_resolution_cards = entity_resolution_cards_for_events(visible_events)
    temporal_anchor_cards = temporal_anchor_cards_for_events(visible_events)
    entity_state_cards = entity_state_cards_for_events(events=visible_events, checkpoint=checkpoint)
    evidence_effect_cards = evidence_effect_cards_for_events(visible_events)
    metadata: dict[str, object] = {
        "discriminative": scenario.discriminative,
        "output_channel_contract": output_channel_contract(contract),
        "evidence_effect_policy": evidence_effect_policy(contract),
        "temporal_grounding_policy": temporal_grounding_policy(),
    }
    return MemoryEvolutionDecisionContext(
        scenario_id=scenario.scenario_id,
        family=scenario.family,
        events=visible_events,
        checkpoint=MemoryEvolutionVisibleCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            timestamp=checkpoint.timestamp,
            query_or_task=checkpoint.query_or_task,
            query_language=checkpoint.query_language,
            evidence_languages=list(checkpoint.evidence_languages),
            answer_language_policy=checkpoint.answer_language_policy,
            cross_lingual=checkpoint.cross_lingual,
            transliteration_policy=checkpoint.transliteration_policy,
        ),
        decision_contract=contract,
        visible_memory_cards=visible_memory_cards,
        entity_resolution_cards=entity_resolution_cards,
        temporal_anchor_cards=temporal_anchor_cards,
        entity_state_cards=entity_state_cards,
        evidence_effect_cards=evidence_effect_cards,
        metadata=metadata,
    )


def expected_memory_evolution_decision_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecision:
    contract = visible_decision_contract(scenario=scenario, checkpoint=checkpoint)
    execution_selection = None
    if contract.requires_execution_selection:
        execution_selection = MemoryEvolutionExecutionSelection(
            selected_action_memory_ids=list(checkpoint.expected_retrieval_ids),
            active_work_state_memory_ids=lifecycle_expected_ids(
                checkpoint=checkpoint,
                lifecycle_kind="active",
            ),
            command_context_memory_ids=command_context_ids(scenario=scenario, checkpoint=checkpoint),
            suppressed_branch_memory_ids=dedupe_string_ids(
                [
                    *checkpoint.expected_excluded_memory_ids,
                    *checkpoint.expected_checkpoint_superseded_record_ids,
                    *checkpoint.expected_checkpoint_retained_record_ids,
                ]
            ),
            rationale="Expected active execution state and suppressed branch history.",
        )
    return MemoryEvolutionDecision(
        operation=(
            MemoryEvolutionDecisionOperation.NEXT_ACTION
            if checkpoint.expected_next_action is not None
            else MemoryEvolutionDecisionOperation.ANSWER
        ),
        answer=checkpoint.expected_answer,
        next_action=checkpoint.expected_next_action,
        confidence=0.9,
        query_temporal_frame=expected_temporal_frame(checkpoint=checkpoint, contract=contract),
        answer_selection=MemoryEvolutionAnswerSelection(
            selected_memory_ids=list(checkpoint.expected_retrieval_ids),
            supporting_memory_ids=list(checkpoint.expected_retrieval_ids),
            citation_memory_ids=list(checkpoint.expected_citation_ids),
            temporal_reference=contract.temporal_reference,
            rationale="Expected direct answer or action-support memories.",
        ),
        lifecycle_snapshot=MemoryEvolutionLifecycleSnapshot(
            checkpoint_active_record_ids=lifecycle_expected_ids(
                checkpoint=checkpoint,
                lifecycle_kind="active",
            ),
            checkpoint_superseded_record_ids=lifecycle_expected_ids(
                checkpoint=checkpoint,
                lifecycle_kind="superseded",
            ),
            checkpoint_retained_record_ids=lifecycle_expected_ids(
                checkpoint=checkpoint,
                lifecycle_kind="retained",
            ),
            evaluation_time=checkpoint.timestamp,
            rationale="Expected checkpoint-current lifecycle state.",
        ),
        retrieval_context=MemoryEvolutionRetrievalContext(
            query_relevant_memory_ids=dedupe_string_ids(
                [
                    *checkpoint.expected_retrieval_ids,
                    *checkpoint.expected_citation_ids,
                ]
            ),
            query_historical_memory_ids=(
                list(checkpoint.expected_retrieval_ids)
                if contract.temporal_reference == MemoryEvolutionTemporalReference.HISTORICAL
                else []
            ),
            query_context_memory_ids=dedupe_string_ids(
                [
                    *(
                        [
                            memory_id
                            for memory_id in checkpoint.expected_checkpoint_active_record_ids
                            if memory_id not in checkpoint.expected_retrieval_ids
                        ]
                        if contract.temporal_reference == MemoryEvolutionTemporalReference.HISTORICAL
                        else []
                    ),
                    *checkpoint.expected_checkpoint_retained_record_ids,
                ]
            ),
            rejected_memory_ids=expected_rejected_memory_ids(
                checkpoint=checkpoint,
                contract=contract,
            ),
            rationale="Expected retrieval context, historical contrast, and rejected memories.",
        ),
        execution_selection=execution_selection,
        evaluated_belief_ids=expected_belief_ids(checkpoint),
        belief_scores=[
            MemoryEvolutionBeliefScore(
                memory_id=memory_id,
                belief=belief,
                belief_state=next(
                    (
                        expectation.expected_state
                        for expectation in checkpoint.expected_belief_states
                        if expectation.memory_id == memory_id
                    ),
                    None,
                ),
            )
            for memory_id, belief in checkpoint.expected_belief_scores.items()
        ]
        or [
            MemoryEvolutionBeliefScore(memory_id=memory_id, belief=max(0.0, 1.0 - index * 0.2))
            for index, memory_id in enumerate(checkpoint.expected_belief_ranking)
        ],
        rationale="expected benchmark memory evolution decision",
        failure_mode=None,
        requires_judge_review=False,
    )


def expected_memory_evolution_semantic_decision_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionSemanticDecision:
    """Oracle-backed fake-provider decision used only by deterministic dry runs."""

    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    considered = dedupe_string_ids(
        [
            *output.answer_selection.selected_memory_ids,
            *output.retrieval_context.query_historical_memory_ids,
            *output.retrieval_context.query_context_memory_ids,
            *output.retrieval_context.rejected_memory_ids,
        ]
    )
    return MemoryEvolutionSemanticDecision(
        operation=output.operation,
        answer=output.answer,
        next_action=output.next_action,
        confidence=output.confidence,
        query_temporal_frame=output.query_temporal_frame.model_dump(),
        selected_memory_ids=list(output.answer_selection.selected_memory_ids),
        considered_memory_ids=considered,
        belief_scores=[
            MemoryEvolutionSemanticBeliefScore(
                memory_id=score.memory_id,
                belief=score.belief,
                belief_state=score.belief_state or MemoryEvolutionBeliefState.UNKNOWN,
            )
            for score in output.belief_scores
        ],
        rationale=output.rationale,
        requires_judge_review=output.requires_judge_review,
    )


def rule_memory_evolution_decision_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecision:
    contract = visible_decision_contract(scenario=scenario, checkpoint=checkpoint)
    ranked = rank_events_by_shallow_overlap(scenario=scenario, checkpoint=checkpoint)
    selected = [ranked[0].event_id] if ranked else []
    selected_event = ranked[0] if ranked else None
    eligible_events = [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]
    latest_event = max(eligible_events, key=lambda event: event.timestamp, default=None)
    state_cards = entity_state_cards_for_events(events=eligible_events, checkpoint=checkpoint)
    if state_cards:
        active_ids = [
            card.memory_id
            for card in state_cards
            if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_ACTIVE
        ]
        superseded_ids = [
            card.memory_id
            for card in state_cards
            if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_SUPERSEDED
        ]
        retained_ids = [
            card.memory_id
            for card in state_cards
            if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_RETAINED
        ]
    else:
        active_ids = [latest_event.event_id] if latest_event is not None else []
        superseded_ids = []
        retained_ids = []
    answer = extract_shallow_answer(selected_event.content) if selected_event is not None else None
    next_action = f"continue {selected[0]}" if selected else None
    belief_scores = [MemoryEvolutionBeliefScore(memory_id=event.event_id, belief=0.5) for event in ranked[:3]]
    execution_selection = None
    if contract.requires_execution_selection:
        execution_selection = MemoryEvolutionExecutionSelection(
            selected_action_memory_ids=selected,
            active_work_state_memory_ids=active_ids,
            command_context_memory_ids=[],
            suppressed_branch_memory_ids=[],
            rationale="rule provider uses shallow recency for execution state",
        )
    return MemoryEvolutionDecision(
        operation=(
            MemoryEvolutionDecisionOperation.NEXT_ACTION
            if checkpoint.expected_next_action is not None
            else MemoryEvolutionDecisionOperation.ANSWER
        ),
        answer=answer,
        next_action=next_action,
        confidence=0.45,
        query_temporal_frame=expected_temporal_frame(checkpoint=checkpoint, contract=contract),
        answer_selection=MemoryEvolutionAnswerSelection(
            selected_memory_ids=selected,
            supporting_memory_ids=selected,
            citation_memory_ids=selected,
            temporal_reference=contract.temporal_reference,
            rationale="rule provider uses shallow token overlap",
        ),
        lifecycle_snapshot=MemoryEvolutionLifecycleSnapshot(
            checkpoint_active_record_ids=active_ids,
            checkpoint_superseded_record_ids=superseded_ids,
            checkpoint_retained_record_ids=retained_ids,
            evaluation_time=checkpoint.timestamp,
            rationale="rule provider uses recency as current lifecycle",
        ),
        retrieval_context=MemoryEvolutionRetrievalContext(
            query_relevant_memory_ids=selected,
            query_historical_memory_ids=selected
            if contract.temporal_reference == MemoryEvolutionTemporalReference.HISTORICAL
            else [],
            query_context_memory_ids=[],
            rejected_memory_ids=[],
            rationale="rule provider has no semantic rejection model",
        ),
        execution_selection=execution_selection,
        belief_scores=belief_scores,
        rationale=(
            "rule memory evolution provider uses shallow token overlap and recency; "
            "it does not reason over temporal addressability, trust hierarchy, semantic roles, "
            "belief dependency, scoped preferences, or abandoned work"
        ),
        failure_mode="rule_limit" if scenario.discriminative else None,
        requires_judge_review=scenario.discriminative,
    )
