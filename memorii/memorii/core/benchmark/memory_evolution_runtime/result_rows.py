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
    RuntimeSemanticComparisonIssueRow,
    RuntimeStageTraceRow,
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
from memorii.core.memory_evolution import (
    FallbackOutcome,
    MemoryGraphSnapshot,
    ProviderAttemptStatus,
)
from memorii.core.memory_evolution import (
    FinalExtractionSource as MemoryFinalExtractionSource,
)


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
    recorded_runs: Sequence[RecordedExtractionRun],
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
        passed=success,
        verdict="pass" if success else "fail",
        score=(projection.semantic_comparison.score if projection.semantic_comparison is not None else 0.0),
        confidence=aggregate.confidence,
        review_required=not success,
        failure_buckets=sorted(set(runtime_buckets)),
        warning_buckets=warning_buckets,
    )
    runtime_section = RuntimeDiagnosticsSection(
        runtime_graph_validation_errors=list(graph_snapshot.validation_errors),
        runtime_relation_support=runtime_relation_support_rows(projection),
        runtime_action_support=runtime_action_support_rows(projection),
        runtime_action_alignments=projection.action_alignment_rows,
        runtime_channel_alignments=projection.channel_alignment_rows,
        runtime_stage_trace=runtime_stage_trace(
            checkpoint=checkpoint,
            recorded_runs=recorded_runs,
            graph_snapshot=graph_snapshot,
            projection=projection,
            runtime_buckets=runtime_buckets,
        ),
        runtime_semantic_comparison_issues=(
            []
            if projection.semantic_comparison is None
            else [
                RuntimeSemanticComparisonIssueRow(
                    code=issue.code,
                    channel=issue.channel,
                    expected=issue.expected,
                    actual=issue.actual,
                )
                for issue in projection.semantic_comparison.issues
            ]
        ),
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
                    requested_model=run.requested_model,
                    actual_model=run.actual_model,
                    prompt_hash=run.prompt_hash,
                    scenario_id=scenario.scenario_id,
                    call_index=index,
                    input_source_ids=run.input_source_ids,
                    errors=run.errors,
                    entity_count=run.entity_count,
                    claim_count=run.claim_count,
                    action_count=run.action_count,
                    validation_summary=run.validation_summary,
                ),
                extraction_status=run.extraction_status,
                provider_attempt_status=run.provider_attempt_status,
                fallback_outcome=run.fallback_outcome,
                final_extraction_source=run.final_output_source,
                failure_code=run.failure_code,
                primary_failure_code=run.primary_failure_code,
                fallback_provider=run.fallback_provider,
                operation_id=run.operation_id,
                operation_status=run.operation_status,
                operation_failure_code=run.operation_failure_code,
                operation_retryable=run.operation_retryable,
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
    if run.final_output_source == MemoryFinalExtractionSource.NONE:
        return "reused_runtime_state"
    return "rule" if run.final_output_source == MemoryFinalExtractionSource.FALLBACK else "live_llm"


def runtime_failure_classification(runtime_buckets: list[str], diagnostics: CheckpointDiagnosticsSection) -> list[str]:
    if not runtime_buckets:
        return []
    classifications = [f"{_runtime_failure_owner(bucket)}:{bucket}" for bucket in runtime_buckets]
    ingestion_blocked = any(bucket.startswith("production_ingestion_") for bucket in runtime_buckets)
    diagnostic_classifications = [
        classification
        for classification in diagnostics.failure_classification
        if not ingestion_blocked and (classification != "unclassified_failure" or not runtime_buckets)
    ]
    classifications.extend(f"benchmark_comparison:{classification}" for classification in diagnostic_classifications)
    return ordered_unique(classifications)


def _runtime_failure_owner(bucket: str) -> str:
    if bucket.startswith("production_ingestion_"):
        return "production_ingestion"
    if bucket.startswith("production_lifecycle_"):
        return "production_lifecycle"
    if bucket.startswith("production_semantic_graph_") or bucket.startswith("runtime_action_"):
        return "production_semantic_graph"
    if bucket.startswith("production_retrieval_") or bucket.startswith("runtime_evolution_"):
        return "production_retrieval"
    if bucket.startswith("runtime_provider_") or bucket.startswith("runtime_output_validation_"):
        return "production_ingestion"
    if bucket.startswith("runtime_partial_extraction") or bucket.startswith("runtime_evolution_operation_"):
        return "production_ingestion"
    if bucket.startswith("runtime_missing_evolution_") or bucket.startswith("runtime_nonterminal_evolution_"):
        return "production_ingestion"
    if bucket.startswith("benchmark_alignment_"):
        return "benchmark_alignment"
    return "benchmark_harness"


def runtime_stage_trace(
    *,
    checkpoint: OracleCheckpoint,
    recorded_runs: Sequence[RecordedExtractionRun],
    graph_snapshot: MemoryGraphSnapshot,
    projection: RuntimeProjection,
    runtime_buckets: Sequence[str],
) -> list[RuntimeStageTraceRow]:
    ingestion_failure_buckets = sorted(
        bucket for bucket in runtime_buckets if bucket.startswith("production_ingestion_")
    )
    prefix_semantic_failures = [
        bucket for bucket in ingestion_failure_buckets if bucket.startswith("production_ingestion_semantic_prefix_")
    ]
    extraction_failures = sorted(
        {run.extraction_status.value for run in recorded_runs if run.extraction_status.value in {"failed", "partial"}}
    )
    extraction_execution_failures = sorted(
        {
            run.provider_attempt_status.value
            for run in recorded_runs
            if run.provider_attempt_status == ProviderAttemptStatus.PROVIDER_ERROR
        }
    )
    extraction_schema_failures = sorted(
        {
            run.provider_attempt_status.value
            for run in recorded_runs
            if run.provider_attempt_status
            in {
                ProviderAttemptStatus.INVALID_JSON,
                ProviderAttemptStatus.SCHEMA_ERROR,
            }
        }
    )
    extraction_fallbacks = sorted(
        {run.fallback_outcome.value for run in recorded_runs if run.fallback_outcome != FallbackOutcome.NOT_USED}
    )
    extraction_semantic_failure = bool(
        extraction_failures or extraction_schema_failures or extraction_fallbacks or prefix_semantic_failures
    )
    extraction_execution_failure = bool(extraction_execution_failures)
    extraction_reason_codes = [
        *(f"provider_execution:{status}" for status in extraction_execution_failures),
        *(f"provider_schema:{status}" for status in extraction_schema_failures),
        *(f"extraction_status:{status}" for status in extraction_failures),
        *(f"fallback_outcome:{status}" for status in extraction_fallbacks),
        *prefix_semantic_failures,
    ]
    operation_failures = sorted(
        {run.operation_failure_code.value for run in recorded_runs if run.operation_failure_code is not None}
    )
    validation_failures = sum(
        run.validation_summary.get("fail", 0)
        + run.validation_summary.get("input_validation_errors", 0)
        + run.validation_summary.get("entity_binding_errors", 0)
        + run.validation_summary.get("claim_binding_errors", 0)
        + run.validation_summary.get("action_binding_errors", 0)
        for run in recorded_runs
    )
    lifecycle_counts: dict[str, int] = {}
    for item in projection.graph_items:
        lifecycle_counts[item.lifecycle_state.value] = lifecycle_counts.get(item.lifecycle_state.value, 0) + 1
    decision = projection.retrieval_decision
    query_semantic_failure = (
        decision is None
        or (checkpoint.expected_abstention and not decision.abstained)
        or (
            not checkpoint.expected_abstention
            and (
                decision.abstained
                or decision.semantic_frame_status.value != "matched"
                or decision.resolution_status != "resolved"
            )
        )
    )
    retrieval_count = (
        0
        if decision is None
        else len(decision.selected_record_ids) + len(decision.context_record_ids) + len(decision.rejected_record_ids)
    )
    retrieval_semantic_failure = (
        decision is None
        or (not checkpoint.expected_abstention and retrieval_count == 0)
        or any(bucket.startswith("production_retrieval_") for bucket in runtime_buckets)
    )
    lifecycle_semantic_failure = any(bucket.startswith("production_lifecycle_") for bucket in runtime_buckets)
    comparison_failure = projection.semantic_comparison is None or not projection.semantic_comparison.passed
    comparison_reasons = (
        ["benchmark_semantic_comparison_missing"]
        if projection.semantic_comparison is None
        else projection.semantic_comparison.failure_buckets
    )
    downstream_blocked = bool(ingestion_failure_buckets)
    blocked_stage = {
        "status": "not_run",
        "execution_status": "not_run",
        "semantic_status": "not_evaluated",
        "reason_codes": ["blocked_by_ingestion"],
        "input_count": 0,
        "output_count": 0,
    }
    rows = [
        RuntimeStageTraceRow(
            stage="extraction",
            status=("fail" if extraction_execution_failure or extraction_semantic_failure else "pass"),
            execution_status="fail" if extraction_execution_failure else "pass",
            semantic_status="fail" if extraction_semantic_failure else "pass",
            reason_codes=extraction_reason_codes or (["reused_persisted_state"] if not recorded_runs else []),
            input_count=len(recorded_runs),
            output_count=sum(run.entity_count + run.claim_count + run.action_count for run in recorded_runs),
        ),
        RuntimeStageTraceRow(
            stage="validation",
            status="fail" if extraction_failures or validation_failures else "pass",
            execution_status="pass",
            semantic_status="fail" if extraction_failures or validation_failures else "pass",
            reason_codes=([f"candidate_validation_failures:{validation_failures}"] if validation_failures else []),
            input_count=sum(run.claim_count for run in recorded_runs),
            output_count=sum(run.claim_count for run in recorded_runs),
        ),
        RuntimeStageTraceRow(
            stage="normalization",
            status="fail" if graph_snapshot.validation_errors else "pass",
            execution_status="pass",
            semantic_status="fail" if graph_snapshot.validation_errors else "pass",
            reason_codes=["runtime_graph_validation_error"] if graph_snapshot.validation_errors else [],
            input_count=len(graph_snapshot.nodes) + len(graph_snapshot.edges),
            output_count=len(projection.graph_items),
        ),
        RuntimeStageTraceRow(
            stage="lifecycle",
            status="fail" if lifecycle_semantic_failure else "pass",
            execution_status="pass",
            semantic_status="fail" if lifecycle_semantic_failure else "pass",
            reason_codes=[f"{name}:{count}" for name, count in sorted(lifecycle_counts.items())],
            input_count=sum(lifecycle_counts.values()),
            output_count=lifecycle_counts.get("active", 0),
        ),
        RuntimeStageTraceRow(
            stage="persistence",
            status="fail" if operation_failures else "pass",
            execution_status="fail" if operation_failures else "pass",
            semantic_status="not_evaluated" if operation_failures else "pass",
            reason_codes=operation_failures,
            input_count=len(recorded_runs),
            output_count=sum(run.operation_status is not None for run in recorded_runs),
        ),
        RuntimeStageTraceRow(
            stage="query",
            **(
                blocked_stage
                if downstream_blocked
                else {
                    "status": "fail" if query_semantic_failure else "pass",
                    "execution_status": "fail" if decision is None else "pass",
                    "semantic_status": "fail" if query_semantic_failure else "pass",
                    "reason_codes": (
                        ["retrieval_decision_missing"]
                        if decision is None
                        else [decision.semantic_frame_status.value, decision.resolution_status]
                    ),
                    "input_count": 1,
                    "output_count": int(decision is not None),
                }
            ),
        ),
        RuntimeStageTraceRow(
            stage="retrieval",
            **(
                blocked_stage
                if downstream_blocked
                else {
                    "status": "fail" if retrieval_semantic_failure else "pass",
                    "execution_status": "fail" if decision is None else "pass",
                    "semantic_status": "fail" if retrieval_semantic_failure else "pass",
                    "reason_codes": (
                        ["retrieval_decision_missing"] if decision is None else [decision.resolution_status]
                    ),
                    "input_count": int(decision is not None),
                    "output_count": retrieval_count,
                }
            ),
        ),
        RuntimeStageTraceRow(
            stage="comparison",
            **(
                blocked_stage
                if downstream_blocked
                else {
                    "status": "fail" if comparison_failure else "pass",
                    "execution_status": ("fail" if projection.semantic_comparison is None else "pass"),
                    "semantic_status": "fail" if comparison_failure else "pass",
                    "reason_codes": comparison_reasons,
                    "input_count": len(projection.alignments),
                    "output_count": (
                        0
                        if projection.semantic_comparison is None
                        else projection.semantic_comparison.requirement_count
                    ),
                }
            ),
        ),
    ]
    first_failure = next((index for index, row in enumerate(rows) if row.status == "fail"), None)
    if first_failure is not None:
        rows[first_failure] = rows[first_failure].model_copy(update={"is_first_divergence": True})
    return rows
