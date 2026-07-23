"""Judge policy and diagnostics for hand-authored memory evolution."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from memorii.core.benchmark.memory_evolution_decision.contracts import (
    DEGRADED_BELIEF_SCORE_MAX,
    MemoryEvolutionAnswerProjectionPolicy,
    MemoryEvolutionAnswerTemporalMode,
    MemoryEvolutionBeliefLifecyclePolicy,
    MemoryEvolutionBeliefScorePolicy,
    MemoryEvolutionBeliefState,
    MemoryEvolutionCheckpoint,
    MemoryEvolutionCheckpointContract,
    MemoryEvolutionCheckpointKind,
    MemoryEvolutionCitationPolicy,
    MemoryEvolutionDecision,
    MemoryEvolutionDecisionDiagnostics,
    MemoryEvolutionExcludedMemoryPolicy,
    MemoryEvolutionExecutionSelection,
    MemoryEvolutionFailureBucket,
    MemoryEvolutionLifecyclePolicy,
    MemoryEvolutionNextActionPolicy,
    MemoryEvolutionScenario,
    MemoryEvolutionSelectedMemoryPolicy,
    MemoryEvolutionWarningBucket,
)
from memorii.core.benchmark.memory_evolution_decision.policies import checkpoint_contract, lifecycle_expected_ids
from memorii.core.benchmark.memory_evolution_decision.temporal_diagnostics import (
    expected_temporal_frame as build_expected_temporal_frame,
)
from memorii.core.benchmark.memory_evolution_decision.temporal_diagnostics import (
    record_lifecycle_content_state_conflation_ids,
)
from memorii.core.benchmark.memory_evolution_decision.temporal_diagnostics import (
    temporal_frame_diagnostics as compute_temporal_frame_diagnostics,
)
from memorii.core.benchmark.memory_evolution_decision.utils import (
    answer_matches_expected,
    dedupe_preserving_order,
    dedupe_string_ids,
    is_belief_memory_id,
    normalize_decision_text,
    ordered_extra,
    ordered_missing,
)
from memorii.core.benchmark.memory_evolution_decision.visible_context import (
    belief_effect_order_errors as compute_belief_effect_order_errors,
)
from memorii.core.benchmark.memory_evolution_decision.visible_context import (
    belief_ids_from_order_errors,
    belief_score_order_errors,
    command_context_ids,
)
from memorii.core.benchmark.memory_evolution_decision.visible_context import (
    source_trust_losers_marked_active as find_source_trust_losers_marked_active,
)


def memory_evolution_assertion_passed(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    decision: dict[str, object],
) -> bool:
    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=decision,
    )
    return diagnostics.assertion_passed


def memory_evolution_decision_diagnostics(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    decision: dict[str, object],
) -> MemoryEvolutionDecisionDiagnostics:
    failure_buckets: list[MemoryEvolutionFailureBucket] = []
    warning_buckets: list[MemoryEvolutionWarningBucket] = []
    try:
        parsed = MemoryEvolutionDecision.model_validate(decision)
    except ValidationError as exc:
        return MemoryEvolutionDecisionDiagnostics(
            assertion_passed=False,
            failure_buckets=[MemoryEvolutionFailureBucket.SCHEMA_VALIDATION_FAILED],
            rationale=f"MemoryEvolutionDecision schema validation failed: {exc.errors()}",
        )

    contract = checkpoint_contract(scenario=scenario, checkpoint=checkpoint)
    answer_selection = parsed.answer_selection
    lifecycle = parsed.lifecycle_snapshot
    retrieval = parsed.retrieval_context
    execution = parsed.execution_selection
    expected_temporal_frame = build_expected_temporal_frame(checkpoint=checkpoint, contract=contract)
    actual_temporal_frame = parsed.query_temporal_frame

    score_by_id = {score.memory_id: score.belief for score in parsed.belief_scores}
    belief_state_by_id = {
        score.memory_id: score.belief_state
        for score in parsed.belief_scores
        if score.belief_state is not None
    }
    selected_ids = list(answer_selection.selected_memory_ids)
    selected = set(selected_ids)
    supporting = set(answer_selection.supporting_memory_ids)
    citations = list(answer_selection.citation_memory_ids)
    citation_set = set(citations)
    checkpoint_active = set(lifecycle.checkpoint_active_record_ids)
    checkpoint_superseded = set(lifecycle.checkpoint_superseded_record_ids)
    checkpoint_retained = set(lifecycle.checkpoint_retained_record_ids)
    query_relevant = set(retrieval.query_relevant_memory_ids)
    query_historical = set(retrieval.query_historical_memory_ids)
    rejected = set(retrieval.rejected_memory_ids)
    evaluated_belief_ids = dedupe_string_ids(
        [
            *parsed.evaluated_belief_ids,
            *[score.memory_id for score in parsed.belief_scores if is_belief_memory_id(score.memory_id, checkpoint=checkpoint)],
        ]
    )

    lifecycle_expectation_scope = _lifecycle_expectation_scope(checkpoint)
    expected_active_ids = lifecycle_expected_ids(checkpoint=checkpoint, lifecycle_kind="active")
    expected_superseded_ids = lifecycle_expected_ids(checkpoint=checkpoint, lifecycle_kind="superseded")
    expected_retained_ids = lifecycle_expected_ids(checkpoint=checkpoint, lifecycle_kind="retained")

    if answer_selection.temporal_mode != contract.answer_temporal_mode:
        failure_buckets.append(MemoryEvolutionFailureBucket.WRONG_TEMPORAL_MODE)
    temporal_frame_diagnostics = compute_temporal_frame_diagnostics(
        expected=expected_temporal_frame,
        actual=actual_temporal_frame,
        contract=contract,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    temporal_kind_mismatch = temporal_frame_diagnostics["temporal_kind_mismatch"]
    temporal_scope_mismatch = temporal_frame_diagnostics["temporal_scope_mismatch"]
    temporal_anchor_mismatch = temporal_frame_diagnostics["temporal_anchor_mismatch"]
    temporal_interval_mismatch = temporal_frame_diagnostics["temporal_interval_mismatch"]
    temporal_frame_under_specified = temporal_frame_diagnostics["temporal_frame_under_specified"]
    temporal_scope_key_mismatch = temporal_frame_diagnostics["temporal_scope_key_mismatch"]
    temporal_extra_anchor = temporal_frame_diagnostics["temporal_extra_anchor"]
    temporal_extra_interval = temporal_frame_diagnostics["temporal_extra_interval"]
    temporal_frame_warning = temporal_frame_diagnostics["temporal_frame_warning"]
    temporal_frame_mismatch = any(
        value
        for key, value in temporal_frame_diagnostics.items()
        if key != "temporal_frame_warning"
    )
    if temporal_frame_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_FRAME_MISMATCH)
    if temporal_frame_warning:
        warning_buckets.append(MemoryEvolutionWarningBucket.TEMPORAL_FRAME_ENRICHMENT)
    if temporal_kind_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_KIND_MISMATCH)
    if temporal_scope_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_SCOPE_MISMATCH)
    if temporal_anchor_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_ANCHOR_MISMATCH)
    if temporal_interval_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_INTERVAL_MISMATCH)
    if temporal_frame_under_specified:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_FRAME_UNDER_SPECIFIED)
    if temporal_scope_key_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_SCOPE_KEY_MISMATCH)
    if temporal_extra_anchor:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_EXTRA_ANCHOR)
    if temporal_extra_interval:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_EXTRA_INTERVAL)

    if _requires_answer_text(contract) and checkpoint.expected_answer is not None and not answer_matches_expected(
        actual=parsed.answer,
        expected=checkpoint.expected_answer,
        aliases=checkpoint.expected_answer_aliases,
    ):
        failure_buckets.append(MemoryEvolutionFailureBucket.ANSWER_MISMATCH)

    if checkpoint.expected_next_action is not None and not _next_action_matches_expected(
        actual=parsed.next_action,
        expected=checkpoint.expected_next_action,
        checkpoint=checkpoint,
        scenario=scenario,
        parsed=parsed,
        contract=contract,
    ):
        failure_buckets.append(MemoryEvolutionFailureBucket.NEXT_ACTION_MISMATCH)

    expected_retrieval = list(checkpoint.expected_retrieval_ids)
    expected_retrieval_set = set(expected_retrieval)
    retrieval_surface = selected | supporting | query_relevant
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_RANKING:
        retrieval_surface |= set(evaluated_belief_ids)
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        retrieval_surface |= citation_set

    missing_retrieval_ids: list[str] = []
    extra_selected_ids: list[str] = []
    if scenario.discriminative and expected_retrieval and _requires_exact_selected_memory(contract):
        if selected_ids != expected_retrieval:
            missing_retrieval_ids = ordered_missing(expected_retrieval, selected)
            extra_selected_ids = ordered_extra(selected_ids, expected_retrieval_set)
            failure_buckets.append(MemoryEvolutionFailureBucket.SELECTED_MEMORY_MISMATCH)
    elif expected_retrieval and not expected_retrieval_set.issubset(retrieval_surface):
        missing_retrieval_ids = ordered_missing(expected_retrieval, retrieval_surface)
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_RETRIEVAL_MISSING)

    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        extra_belief_selected = [
            memory_id
            for memory_id in ordered_extra(selected_ids, expected_retrieval_set)
            if is_belief_memory_id(memory_id, checkpoint=checkpoint)
        ]
        if extra_belief_selected:
            extra_selected_ids = dedupe_string_ids([*extra_selected_ids, *extra_belief_selected])
            warning_buckets.append(MemoryEvolutionWarningBucket.EXTRA_SELECTED_EVALUATED_BELIEF_IDS)

    if selected & set(checkpoint.expected_excluded_memory_ids):
        failure_buckets.append(MemoryEvolutionFailureBucket.EXCLUDED_MEMORY_SELECTED)

    excluded_memory_missing_channel_ids: list[str] = []
    if contract.excluded_memory_policy == MemoryEvolutionExcludedMemoryPolicy.REJECTED_OR_CONTEXT:
        exclusion_surface = rejected | set(retrieval.query_context_memory_ids)
        if execution is not None:
            exclusion_surface |= set(execution.suppressed_branch_memory_ids)
        excluded_memory_missing_channel_ids = ordered_missing(
            checkpoint.expected_excluded_memory_ids,
            exclusion_surface,
        )
        if excluded_memory_missing_channel_ids:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_EXCLUDED_MEMORY_CHANNEL_MISSING)

    selected_rejected_ids = sorted(selected & rejected)
    if selected_rejected_ids:
        failure_buckets.append(MemoryEvolutionFailureBucket.SELECTED_MEMORY_REJECTED)
        if set(selected_rejected_ids) & (set(checkpoint.expected_checkpoint_superseded_record_ids) | set(checkpoint.expected_checkpoint_retained_record_ids)):
            failure_buckets.append(MemoryEvolutionFailureBucket.QUERY_LIFECYCLE_CONFLATION)

    missing_citation_ids: list[str] = []
    extra_citation_ids: list[str] = []
    belief_ids_used_as_citations: list[str] = []
    if checkpoint.expected_citation_ids:
        expected_citations = set(checkpoint.expected_citation_ids)
        missing_citation_ids = ordered_missing(checkpoint.expected_citation_ids, citation_set)
        extra_citation_ids = ordered_extra(citations, expected_citations)
        if missing_citation_ids:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CITATION_MISSING)
        if extra_citation_ids:
            if _extra_direct_citations_are_warning_only(
                extra_citation_ids=extra_citation_ids,
                checkpoint=checkpoint,
                contract=contract,
            ):
                warning_buckets.append(MemoryEvolutionWarningBucket.CONTEXT_CITATION_IN_DIRECT_CHANNEL)
            else:
                failure_buckets.append(MemoryEvolutionFailureBucket.CITATION_CHANNEL_POLLUTION)
        belief_ids_used_as_citations = [
            memory_id
            for memory_id in citations
            if is_belief_memory_id(memory_id, checkpoint=checkpoint)
        ]
        if belief_ids_used_as_citations:
            if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION and not missing_citation_ids:
                warning_buckets.append(MemoryEvolutionWarningBucket.CONTEXT_CITATION_IN_DIRECT_CHANNEL)
            else:
                failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_ID_USED_AS_CITATION)

    checkpoint_active_equivalent = set(checkpoint_active)
    if contract.belief_lifecycle_policy == MemoryEvolutionBeliefLifecyclePolicy.DEGRADED_RETAINED_EVALUABLE:
        checkpoint_active_equivalent |= {
            memory_id
            for memory_id in set(evaluated_belief_ids) | set(score_by_id)
            if is_belief_memory_id(memory_id, checkpoint=checkpoint)
        }
    missing_checkpoint_active = ordered_missing(
        expected_active_ids,
        checkpoint_active_equivalent,
    )
    if missing_checkpoint_active:
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_ACTIVE_RECORD_MISSING)
    lifecycle_content_conflation_ids = record_lifecycle_content_state_conflation_ids(
        scenario=scenario,
        missing_checkpoint_active_ids=missing_checkpoint_active,
        checkpoint_superseded=checkpoint_superseded,
        checkpoint_retained=checkpoint_retained,
    )
    if lifecycle_content_conflation_ids:
        failure_buckets.append(MemoryEvolutionFailureBucket.RECORD_LIFECYCLE_CONTENT_STATE_CONFLATION)

    non_checkpoint_active = checkpoint_superseded | checkpoint_retained
    if contract.requires_execution_selection and execution is not None:
        non_checkpoint_active |= set(execution.suppressed_branch_memory_ids)
    missing_checkpoint_superseded = ordered_missing(
        expected_superseded_ids,
        non_checkpoint_active if contract.lifecycle_policy == MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT else checkpoint_superseded,
    )
    if missing_checkpoint_superseded:
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_SUPERSEDED_RECORD_MISSING)

    superseded_marked_checkpoint_active = set(expected_superseded_ids) & checkpoint_active
    if superseded_marked_checkpoint_active:
        failure_buckets.append(MemoryEvolutionFailureBucket.SUPERSEDED_RECORD_MARKED_CHECKPOINT_ACTIVE)
    source_trust_losers_marked_active = find_source_trust_losers_marked_active(
        scenario=scenario,
        checkpoint=checkpoint,
        checkpoint_active=checkpoint_active,
        selected=selected,
    )
    if source_trust_losers_marked_active:
        failure_buckets.append(MemoryEvolutionFailureBucket.SOURCE_TRUST_LOSER_MARKED_ACTIVE)

    selected_historical_record_ids = [
        memory_id
        for memory_id in selected_ids
        if memory_id in set(checkpoint.expected_checkpoint_superseded_record_ids) | set(checkpoint.expected_checkpoint_retained_record_ids)
    ]
    historical_answer_record_marked_checkpoint_active_ids = [memory_id for memory_id in selected_historical_record_ids if memory_id in checkpoint_active]
    if historical_answer_record_marked_checkpoint_active_ids:
        failure_buckets.append(MemoryEvolutionFailureBucket.HISTORICAL_ANSWER_RECORD_MARKED_CHECKPOINT_ACTIVE)
        failure_buckets.append(MemoryEvolutionFailureBucket.QUERY_LIFECYCLE_CONFLATION)

    if contract.answer_temporal_mode == MemoryEvolutionAnswerTemporalMode.HISTORICAL:
        historical_missing = ordered_missing(checkpoint.expected_retrieval_ids, query_historical | selected)
        if historical_missing:
            failure_buckets.append(MemoryEvolutionFailureBucket.HISTORICAL_MEMORY_NOT_MARKED_QUERY_RELEVANT)

    _append_selected_memory_policy_failures(
        failure_buckets=failure_buckets,
        contract=contract,
        checkpoint=checkpoint,
        selected_ids=selected_ids,
        selected=selected,
        checkpoint_active=checkpoint_active,
        query_historical=query_historical,
        execution=execution,
    )

    if expected_active_ids and not set(expected_active_ids).issubset(checkpoint_active_equivalent):
        failure_buckets.append(MemoryEvolutionFailureBucket.CHECKPOINT_ACTIVE_RECORD_MISSING_FROM_LIFECYCLE_SNAPSHOT)

    missing_checkpoint_retained = ordered_missing(
        expected_retained_ids,
        non_checkpoint_active if contract.lifecycle_policy == MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT else checkpoint_retained,
    )
    if missing_checkpoint_retained:
        if contract.lifecycle_policy in {
            MemoryEvolutionLifecyclePolicy.EXACT,
            MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT,
        }:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_RETAINED_RECORD_MISSING)
        else:
            warning_buckets.append(MemoryEvolutionWarningBucket.LIFECYCLE_CHANNEL_DRIFT)

    extra_checkpoint_active_record_ids = ordered_extra(lifecycle.checkpoint_active_record_ids, set(expected_active_ids))
    if extra_checkpoint_active_record_ids:
        warning_buckets.append(MemoryEvolutionWarningBucket.EXTRA_CHECKPOINT_ACTIVE_RECORD_IDS)

    belief_ids_marked_active = [
        memory_id
        for memory_id in lifecycle.checkpoint_active_record_ids
        if is_belief_memory_id(memory_id, checkpoint=checkpoint)
    ]
    if belief_ids_marked_active and not checkpoint.expected_checkpoint_active_record_ids:
        warning_buckets.extend(
            [
                MemoryEvolutionWarningBucket.ACTIVE_CHANNEL_POLLUTION,
                MemoryEvolutionWarningBucket.BELIEF_CANDIDATE_MARKED_ACTIVE,
            ]
        )

    command_events_selected_as_active_state: list[str] = []
    if contract.requires_execution_selection:
        if execution is None:
            failure_buckets.append(MemoryEvolutionFailureBucket.ACTIVE_EXECUTION_STATE_MISSING)
        else:
            active_execution = set(execution.active_work_state_memory_ids) | set(execution.selected_action_memory_ids)
            if not set(expected_active_ids).issubset(active_execution):
                failure_buckets.append(MemoryEvolutionFailureBucket.ACTIVE_EXECUTION_STATE_MISSING)
            command_ids = set(command_context_ids(scenario=scenario, checkpoint=checkpoint))
            command_events_selected_as_active_state = sorted(command_ids & active_execution)
            if command_events_selected_as_active_state:
                failure_buckets.append(MemoryEvolutionFailureBucket.COMMAND_EVENT_SELECTED_AS_ACTIVE_STATE)

    if parsed.belief_scores and contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.NONE:
        warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORES_ON_NON_BELIEF_CHECKPOINT)

    expected_belief_ranking: list[str] = []
    actual_belief_ranking: list[str] = []
    score_mismatch_ids: list[str] = []
    belief_effect_order_errors: list[str] = []
    if checkpoint.expected_belief_ranking:
        if not set(checkpoint.expected_belief_ranking).issubset(score_by_id):
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_RANKING_MISSING_SCORE)
        expected_belief_ranking = list(checkpoint.expected_belief_ranking)
        selected_belief_ranking = [
            memory_id for memory_id in selected_ids if memory_id in set(checkpoint.expected_belief_ranking)
        ]
        score_ranked = sorted(score_by_id, key=lambda key: (-score_by_id[key], key))
        actual_belief_ranking = (
            selected_belief_ranking[: len(checkpoint.expected_belief_ranking)]
            if set(checkpoint.expected_belief_ranking).issubset(selected_belief_ranking)
            else score_ranked[: len(checkpoint.expected_belief_ranking)]
        )
        if actual_belief_ranking != expected_belief_ranking:
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_RANKING_WRONG_ORDER)
            belief_effect_order_errors = compute_belief_effect_order_errors(
                scenario=scenario,
                checkpoint=checkpoint,
                ranking=actual_belief_ranking,
            )
            if belief_effect_order_errors:
                failure_buckets.append(MemoryEvolutionFailureBucket.WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL)
        score_order_errors = belief_score_order_errors(
            ranking=actual_belief_ranking,
            score_by_id=score_by_id,
        )
        if score_order_errors:
            score_mismatch_ids.extend(belief_ids_from_order_errors(score_order_errors))
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_ORDER_CONTRADICTS_SELECTED_ORDER)
            belief_effect_score_errors = compute_belief_effect_order_errors(
                scenario=scenario,
                checkpoint=checkpoint,
                ranking=score_ranked,
            )
            if belief_effect_score_errors:
                belief_effect_order_errors = dedupe_string_ids(
                    [*belief_effect_order_errors, *belief_effect_score_errors]
                )
                failure_buckets.append(MemoryEvolutionFailureBucket.WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL)

    if checkpoint.expected_belief_scores:
        for memory_id, expected in checkpoint.expected_belief_scores.items():
            actual = score_by_id.get(memory_id)
            if actual is None:
                if contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.EXACT:
                    score_mismatch_ids.append(memory_id)
                continue
            if contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.DEGRADED_THRESHOLD:
                if expected <= DEGRADED_BELIEF_SCORE_MAX and actual > DEGRADED_BELIEF_SCORE_MAX:
                    score_mismatch_ids.append(memory_id)
                    failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_CONFIDENCE_NOT_DEGRADED)
                elif abs(actual - expected) > 0.05:
                    score_mismatch_ids.append(memory_id)
                    warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT)
            elif contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.RANKING_ONLY:
                if abs(actual - expected) > 0.05:
                    score_mismatch_ids.append(memory_id)
                    warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT)
            elif contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.EXACT and abs(actual - expected) > 0.05:
                score_mismatch_ids.append(memory_id)
                failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH)
        if (
            contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.EXACT
            and any(memory_id not in score_by_id for memory_id in checkpoint.expected_belief_scores)
        ):
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH)

    belief_state_mismatch_ids, missing_required_belief_score_ids = _belief_state_mismatch_ids(
        checkpoint=checkpoint,
        score_by_id=score_by_id,
        belief_state_by_id=belief_state_by_id,
    )
    if belief_state_mismatch_ids:
        failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_STATE_MISMATCH)
    if missing_required_belief_score_ids:
        score_mismatch_ids.extend(missing_required_belief_score_ids)
        failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH)

    lifecycle_drift_ids = dedupe_string_ids([*missing_checkpoint_active, *missing_checkpoint_superseded, *missing_checkpoint_retained])
    query_lifecycle_conflation_ids = dedupe_string_ids([
        *historical_answer_record_marked_checkpoint_active_ids,
        *lifecycle_content_conflation_ids,
    ])
    failure_buckets = dedupe_preserving_order(failure_buckets)
    warning_buckets = dedupe_preserving_order(warning_buckets)
    return MemoryEvolutionDecisionDiagnostics(
        assertion_passed=not failure_buckets,
        failure_buckets=failure_buckets,
        warning_buckets=warning_buckets,
        missing_retrieval_ids=missing_retrieval_ids,
        extra_selected_ids=extra_selected_ids,
        missing_citation_ids=missing_citation_ids,
        extra_citation_ids=extra_citation_ids,
        belief_ids_used_as_citations=belief_ids_used_as_citations,
        belief_ids_marked_active=belief_ids_marked_active,
        evaluated_belief_ids=evaluated_belief_ids,
        extra_checkpoint_active_record_ids=extra_checkpoint_active_record_ids,
        lifecycle_drift_ids=lifecycle_drift_ids,
        query_lifecycle_conflation_ids=query_lifecycle_conflation_ids,
        selected_historical_record_ids=selected_historical_record_ids,
        historical_answer_record_marked_checkpoint_active_ids=historical_answer_record_marked_checkpoint_active_ids,
        checkpoint_active_record_missing_expected_ids=missing_checkpoint_active,
        checkpoint_superseded_record_missing_expected_ids=missing_checkpoint_superseded,
        command_events_selected_as_active_state=command_events_selected_as_active_state,
        expected_belief_ranking=expected_belief_ranking,
        actual_belief_ranking=actual_belief_ranking,
        score_mismatch_ids=dedupe_string_ids(score_mismatch_ids),
        belief_state_mismatch_ids=belief_state_mismatch_ids,
        missing_required_belief_score_ids=missing_required_belief_score_ids,
        belief_effect_order_errors=belief_effect_order_errors,
        temporal_frame_mismatch=temporal_frame_mismatch,
        temporal_kind_mismatch=temporal_kind_mismatch,
        temporal_scope_mismatch=temporal_scope_mismatch,
        temporal_anchor_mismatch=temporal_anchor_mismatch,
        temporal_interval_mismatch=temporal_interval_mismatch,
        temporal_frame_under_specified=temporal_frame_under_specified,
        temporal_scope_key_mismatch=temporal_scope_key_mismatch,
        temporal_extra_anchor=temporal_extra_anchor,
        temporal_extra_interval=temporal_extra_interval,
        temporal_frame_warning=temporal_frame_warning,
        expected_temporal_frame=expected_temporal_frame,
        actual_temporal_frame=actual_temporal_frame,
        record_lifecycle_content_state_conflation_ids=lifecycle_content_conflation_ids,
        excluded_memory_missing_channel_ids=excluded_memory_missing_channel_ids,
        lifecycle_expectation_scope=lifecycle_expectation_scope,
        rationale="memory evolution assertion diagnostics",
    )

def _requires_exact_selected_memory(contract: MemoryEvolutionCheckpointContract) -> bool:
    return contract.checkpoint_kind not in {
        MemoryEvolutionCheckpointKind.BELIEF_RANKING,
        MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION,
    }


def _append_selected_memory_policy_failures(
    *,
    failure_buckets: list[MemoryEvolutionFailureBucket],
    contract: MemoryEvolutionCheckpointContract,
    checkpoint: MemoryEvolutionCheckpoint,
    selected_ids: list[str],
    selected: set[str],
    checkpoint_active: set[str],
    query_historical: set[str],
    execution: MemoryEvolutionExecutionSelection | None,
) -> None:
    expected_retrieval = set(checkpoint.expected_retrieval_ids)
    if contract.selected_memory_policy == MemoryEvolutionSelectedMemoryPolicy.CURRENT_TRUTH:
        if selected and not selected.issubset(checkpoint_active):
            failure_buckets.append(MemoryEvolutionFailureBucket.QUERY_LIFECYCLE_CONFLATION)
        if expected_retrieval and not expected_retrieval.issubset(checkpoint_active):
            failure_buckets.append(MemoryEvolutionFailureBucket.CHECKPOINT_ACTIVE_RECORD_MISSING_FROM_LIFECYCLE_SNAPSHOT)
        return
    if contract.selected_memory_policy == MemoryEvolutionSelectedMemoryPolicy.HISTORICAL_TRUTH:
        if expected_retrieval and not expected_retrieval.issubset(selected | query_historical):
            failure_buckets.append(MemoryEvolutionFailureBucket.HISTORICAL_MEMORY_NOT_MARKED_QUERY_RELEVANT)
        expected_non_checkpoint_active = set(checkpoint.expected_checkpoint_superseded_record_ids) | set(checkpoint.expected_checkpoint_retained_record_ids)
        if expected_retrieval & expected_non_checkpoint_active & checkpoint_active:
            failure_buckets.append(MemoryEvolutionFailureBucket.QUERY_LIFECYCLE_CONFLATION)
        return
    if contract.selected_memory_policy == MemoryEvolutionSelectedMemoryPolicy.ACTIVE_EXECUTION_STATE:
        if execution is None:
            failure_buckets.append(MemoryEvolutionFailureBucket.ACTIVE_EXECUTION_STATE_MISSING)
            return
        active_execution = set(execution.selected_action_memory_ids) | set(execution.active_work_state_memory_ids)
        if not expected_retrieval & active_execution:
            failure_buckets.append(MemoryEvolutionFailureBucket.ACTIVE_EXECUTION_STATE_MISSING)
        return
    if (
        contract.selected_memory_policy == MemoryEvolutionSelectedMemoryPolicy.BELIEF_ORDER
        and checkpoint.expected_belief_ranking
        and not set(checkpoint.expected_belief_ranking).intersection(selected_ids)
    ):
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_RETRIEVAL_MISSING)


def _lifecycle_expectation_scope(checkpoint: MemoryEvolutionCheckpoint) -> str:
    if any(
        (
            checkpoint.expected_full_checkpoint_active_record_ids,
            checkpoint.expected_full_checkpoint_superseded_record_ids,
            checkpoint.expected_full_checkpoint_retained_record_ids,
        )
    ):
        return "full_graph"
    return "query_relevant"


def _belief_state_mismatch_ids(
    *,
    checkpoint: MemoryEvolutionCheckpoint,
    score_by_id: dict[str, float],
    belief_state_by_id: Mapping[str, MemoryEvolutionBeliefState | None],
) -> tuple[list[str], list[str]]:
    mismatch_ids: list[str] = []
    missing_required_score_ids: list[str] = []
    for expectation in checkpoint.expected_belief_states:
        memory_id = expectation.memory_id
        actual_score = score_by_id.get(memory_id)
        if expectation.score_required and actual_score is None:
            missing_required_score_ids.append(memory_id)
            continue
        if actual_score is not None:
            if expectation.min_score is not None and actual_score < expectation.min_score:
                mismatch_ids.append(memory_id)
            if expectation.max_score is not None and actual_score > expectation.max_score:
                mismatch_ids.append(memory_id)
        actual_state = belief_state_by_id.get(memory_id)
        actual_state_value = actual_state.value if actual_state is not None else None
        if actual_state_value != expectation.expected_state.value:
            mismatch_ids.append(memory_id)
    return dedupe_string_ids(mismatch_ids), dedupe_string_ids(missing_required_score_ids)


def _extra_direct_citations_are_warning_only(
    *,
    extra_citation_ids: list[str],
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> bool:
    if contract.citation_policy != MemoryEvolutionCitationPolicy.DIRECT_WITH_CONTEXT_WARNING:
        return False
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.EXECUTION_CONTINUATION:
        return True
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        return all(is_belief_memory_id(memory_id, checkpoint=checkpoint) for memory_id in extra_citation_ids)
    excluded = set(checkpoint.expected_excluded_memory_ids)
    allowed_context = set(checkpoint.expected_context_citation_ids)
    return bool(allowed_context) and all(
        memory_id in allowed_context and memory_id not in excluded for memory_id in extra_citation_ids
    )


def _requires_answer_text(contract: MemoryEvolutionCheckpointContract) -> bool:
    return contract.answer_projection_policy not in {
        MemoryEvolutionAnswerProjectionPolicy.GRAPH_CHANNELS_ONLY,
        MemoryEvolutionAnswerProjectionPolicy.NONE,
    }


def _next_action_matches_expected(
    *,
    actual: str | None,
    expected: str,
    checkpoint: MemoryEvolutionCheckpoint,
    scenario: MemoryEvolutionScenario,
    parsed: MemoryEvolutionDecision,
    contract: MemoryEvolutionCheckpointContract,
) -> bool:
    if contract.next_action_policy == MemoryEvolutionNextActionPolicy.NONEMPTY_STRUCTURED:
        if not normalize_decision_text(actual):
            return False
        if parsed.execution_selection is None:
            return False
        expected_active = set(checkpoint.expected_checkpoint_active_record_ids) | set(checkpoint.expected_retrieval_ids)
        selected_state = (
            set(parsed.execution_selection.selected_action_memory_ids)
            | set(parsed.execution_selection.active_work_state_memory_ids)
            | set(parsed.answer_selection.selected_memory_ids)
            | set(parsed.answer_selection.supporting_memory_ids)
        )
        command_context = set(parsed.execution_selection.command_context_memory_ids)
        if command_context & selected_state & set(command_context_ids(scenario=scenario, checkpoint=checkpoint)):
            return False
        return bool(expected_active & selected_state)
    action = normalize_decision_text(actual)
    return all(token in action.split() for token in normalize_decision_text(expected).split())
