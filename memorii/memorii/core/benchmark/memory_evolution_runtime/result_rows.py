"""Typed checkpoint and extractor-trace projection for runtime benchmarks."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from memorii.core.benchmark.artifact_rows import (
    CheckpointDecisionTraceSection,
    CheckpointDiagnosticsPayload,
    CheckpointDiagnosticsSection,
    CheckpointHorizonSection,
    CheckpointVerdictSection,
    DecisionMode,
    FinalOutputSource,
    RuntimeCheckpointResultRow,
    RuntimeDiagnosticsSection,
    RuntimeExtractorOutput,
    RuntimeExtractorTracePayload,
    RuntimeExtractorTraceRow,
    checkpoint_warning_buckets,
)
from memorii.core.benchmark.memory_evolution_runtime.artifacts import (
    horizon_distance_bucket,
    interference_count_bucket,
    source_event_age_days_bucket,
)
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection import runtime_relation_support_rows
from memorii.core.benchmark.memory_evolution_runtime.execution_state_projection import (
    action_alignment_failure_reason,
    runtime_action_support_rows,
)
from memorii.core.benchmark.memory_evolution_runtime.extractors import (
    RecordedExtractionRun,
    RecordingMemoryExtractor,
    recorded_extraction_runs,
)
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeProjection
from memorii.core.benchmark.memory_evolution_runtime.utils import ordered_unique
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    LatentGraphScenario,
    OracleCheckpoint,
    SimSystemOutput,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.memory_evolution import MemoryGraphSnapshot


def build_runtime_checkpoint_result_row(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    mode: DecisionMode,
    effective_mode: DecisionMode,
    final_output_source: FinalOutputSource,
    success: bool,
    aggregate: JudgeAggregate,
    diagnostics: CheckpointDiagnosticsSection,
    runtime_buckets: list[str],
    graph_snapshot: MemoryGraphSnapshot,
    projection: RuntimeProjection,
    raw_output: SimSystemOutput,
    output: SimSystemOutput,
    provider_successes: int,
    provider_failures: int,
    fallbacks: int,
    fallback_used: bool,
) -> RuntimeCheckpointResultRow:
    failure_classification = runtime_failure_classification(runtime_buckets, diagnostics)
    horizon = CheckpointHorizonSection(
        family=scenario.family,
        profile=scenario.profile,
        horizon_distance=checkpoint.horizon_distance,
        horizon_distance_bucket=horizon_distance_bucket(checkpoint.horizon_distance),
        interference_count=checkpoint.interference_count,
        interference_count_bucket=interference_count_bucket(checkpoint.interference_count),
        source_event_age_days=checkpoint.source_event_age_days,
        source_event_age_days_bucket=source_event_age_days_bucket(checkpoint.source_event_age_days),
        required_retrieval_view=checkpoint.required_retrieval_view,
        expected_stage_path=list(checkpoint.expected_stage_path),
        query_or_task=checkpoint.query_or_task,
    )
    decision_trace = CheckpointDecisionTraceSection(
        decision_mode=mode,
        effective_decision_mode=effective_mode,
        llm_call_made=effective_mode in {"llm", "hybrid"},
        fallback_used=fallback_used,
        fallback_reason="runtime_extractor_fallback" if fallback_used else None,
        final_output_source=final_output_source,
        request_id=f"memory_evolution_runtime:{mode}:{scenario.scenario_id}:{checkpoint.checkpoint_id}",
    )
    candidate_cards = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    warning_buckets = checkpoint_warning_buckets(
        answer_match_type=diagnostics.answer_match_type,
        output=output,
    )
    verdict = CheckpointVerdictSection(
        success=success,
        passed=aggregate.verdict.value == "pass" and not runtime_buckets,
        verdict="fail" if runtime_buckets else aggregate.verdict.value,
        score=aggregate.score,
        confidence=aggregate.confidence,
        review_required=aggregate.review_required or bool(runtime_buckets),
        failure_buckets=sorted({*aggregate.critical_failure_buckets, *runtime_buckets}),
        warning_buckets=warning_buckets,
    )
    runtime_section = RuntimeDiagnosticsSection(
        runtime_graph_validation_errors=list(graph_snapshot.validation_errors),
        runtime_relation_support=runtime_relation_support_rows(projection),
        runtime_action_support=runtime_action_support_rows(projection),
        runtime_action_alignments=projection.action_alignment_rows,
        runtime_execution_state=projection.execution_state,
        runtime_retrieval_decision=projection.retrieval_decision,
        active_continuation_branch=projection.execution_state.active_continuation_branch,
        suppressed_branch_ids=list(projection.execution_state.suppressed_branch_ids),
        action_alignment_failure_reason=action_alignment_failure_reason(projection.action_alignment_rows),
    )
    return RuntimeCheckpointResultRow(
        scenario_id=scenario.scenario_id,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_type=checkpoint.checkpoint_type,
        success=verdict.success,
        passed=verdict.passed,
        verdict=verdict.verdict,
        score=verdict.score,
        confidence=verdict.confidence,
        review_required=verdict.review_required,
        failure_buckets=verdict.failure_buckets,
        warning_buckets=verdict.warning_buckets,
        diagnostics=CheckpointDiagnosticsPayload.from_sections(diagnostics, runtime_section),
        output=output,
        profile=horizon.profile,
        family=horizon.family,
        decision_mode=decision_trace.decision_mode,
        effective_decision_mode=decision_trace.effective_decision_mode,
        final_output_source=decision_trace.final_output_source,
        phase=horizon.phase,
        horizon_distance=horizon.horizon_distance,
        horizon_distance_bucket=horizon.horizon_distance_bucket,
        interference_count=horizon.interference_count,
        interference_count_bucket=horizon.interference_count_bucket,
        source_event_age_days=horizon.source_event_age_days,
        source_event_age_days_bucket=horizon.source_event_age_days_bucket,
        required_retrieval_view=horizon.required_retrieval_view,
        expected_stage_path=horizon.expected_stage_path,
        query_or_task=horizon.query_or_task,
        llm_call_made=decision_trace.llm_call_made,
        fallback_used=decision_trace.fallback_used,
        fallback_reason=decision_trace.fallback_reason,
        request_id=decision_trace.request_id,
        expected=checkpoint,
        candidate_cards=candidate_cards,
        raw_output=raw_output,
        judge_aggregate=aggregate,
        runtime_failure_buckets=runtime_buckets,
        runtime_failure_classification=failure_classification,
        scenario_provider_successes=provider_successes,
        scenario_provider_failures=provider_failures,
        scenario_fallbacks=fallbacks,
        provider_successes=provider_successes,
        provider_failures=provider_failures,
        fallbacks=fallbacks,
        provider_count_scope="scenario_extractor_calls",
    )


def extractor_trace_rows(
    *,
    scenario: LatentGraphScenario,
    extractor: RecordingMemoryExtractor,
    effective_mode: DecisionMode,
    dry_run: bool,
) -> list[RuntimeExtractorTraceRow]:
    if effective_mode not in {"llm", "hybrid"}:
        return []
    rows: list[RuntimeExtractorTraceRow] = []
    for index, run in enumerate(recorded_extraction_runs(extractor)):
        rows.append(
            RuntimeExtractorTraceRow(
                scenario_id=scenario.scenario_id,
                checkpoint_id=None,
                transition_type="runtime_memory_extraction",
                decision_mode=effective_mode,
                effective_decision_mode=effective_mode,
                final_output_source=run_output_source(
                    effective_mode=effective_mode,
                    dry_run=dry_run,
                    run=run,
                ),
                trace=RuntimeExtractorTracePayload(
                    provider=run.provider,
                    model=run.model,
                    prompt_hash=run.prompt_hash,
                    scenario_id=scenario.scenario_id,
                    call_index=index,
                    input_source_ids=run.input_source_ids,
                    failure_classification=run.failure_classification,
                    errors=run.errors,
                    entity_count=run.entity_count,
                    claim_count=run.claim_count,
                    action_count=run.action_count,
                    validation_summary=run.validation_summary,
                ),
                success=run.success,
                fallback_used=run.fallback_used,
                failure_mode=None if run.success else "runtime_extractor_failure",
                output=RuntimeExtractorOutput(
                    entity_ids=run.entity_ids,
                    claim_ids=run.claim_ids,
                    action_ids=run.action_ids,
                ),
            )
        )
    return rows


def runtime_final_output_source(
    *,
    effective_mode: str,
    dry_run: bool,
    extractor: RecordingMemoryExtractor,
    recorded_runs: Sequence[RecordedExtractionRun] | None = None,
) -> FinalOutputSource:
    if effective_mode == "rule":
        return "rule"
    if dry_run:
        return "fake_oracle"
    runs = list(recorded_runs) if recorded_runs is not None else recorded_extraction_runs(extractor)
    if runs:
        sources = {run_output_source(effective_mode=effective_mode, dry_run=dry_run, run=run) for run in runs}
        if len(sources) == 1:
            return cast(FinalOutputSource, next(iter(sources)))
        return "mixed"
    return "reused_runtime_state"


def run_output_source(*, effective_mode: str, dry_run: bool, run: RecordedExtractionRun) -> FinalOutputSource:
    if effective_mode == "rule":
        return "rule"
    if dry_run:
        return "fake_oracle"
    return "rule" if run.fallback_used else "live_llm"


def runtime_failure_classification(runtime_buckets: list[str], diagnostics: CheckpointDiagnosticsSection) -> list[str]:
    classifications = list(diagnostics.failure_classification)
    known_buckets = {
        "runtime_missing_expected_entity",
        "runtime_missing_expected_claim",
        "runtime_missing_expected_relation",
        "runtime_missing_expected_action",
        "runtime_missing_expected_rejection",
        "runtime_action_target_mismatch",
        "runtime_action_status_mismatch",
        "runtime_action_evidence_missing",
        "runtime_execution_state_missing",
        "runtime_execution_state_ambiguous",
        "runtime_extra_hidden_fact",
        "runtime_modality_false_positive",
        "runtime_scope_leak",
        "runtime_provenance_missing",
        "runtime_alignment_ambiguous",
        "runtime_graph_validation_error",
        "long_horizon_retrieval_miss",
        "stale_fact_resurfaced",
        "historical_fact_lost",
        "scope_decay",
        "source_trust_decay",
        "entity_rekey_lost",
        "branch_state_decay",
        "branch_state_not_projected",
        "blocked_branch_selected",
        "provenance_chain_broken",
        "hidden_fact_leak",
        "calibration_drift",
    }
    concrete_runtime_classifications = [bucket for bucket in runtime_buckets if bucket in known_buckets]
    if concrete_runtime_classifications:
        classifications = [item for item in classifications if item != "unclassified_failure"]
    classifications.extend(concrete_runtime_classifications)
    return ordered_unique(classifications)
