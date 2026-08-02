"""Runtime benchmark suite orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from memorii.core.benchmark.artifact_rows import (
    DecisionMode,
    RuntimeCheckpointResultRow,
    RuntimeExtractorTraceRow,
    RuntimeGraphAlignmentRow,
    SimScenarioResultRow,
)
from memorii.core.benchmark.decision_modes import resolve_benchmark_decision_mode
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_evaluation import (
    runtime_failure_buckets,
    runtime_ingestion_failure_buckets,
)
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection import project_runtime_checkpoint
from memorii.core.benchmark.memory_evolution_runtime.extractors import (
    build_runtime_extractor,
    recorded_extraction_runs,
)
from memorii.core.benchmark.memory_evolution_runtime.graph_items import (
    graph_items_from_snapshot,
)
from memorii.core.benchmark.memory_evolution_runtime.ingestion import IngestionContext, ingest_surface_observation
from memorii.core.benchmark.memory_evolution_runtime.ingestion_oracle import (
    IngestionPrefixAuditRow,
    audit_ingestion_prefix,
)
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeGraphItem,
    RuntimeGraphSnapshotRow,
    RuntimeIngestionTraceRow,
    RuntimeSuiteRows,
)
from memorii.core.benchmark.memory_evolution_runtime.provider_composition import (
    provider_composition_failure_buckets,
)
from memorii.core.benchmark.memory_evolution_runtime.result_rows import (
    build_runtime_checkpoint_result_row,
    extractor_trace_rows,
    runtime_final_output_source,
)
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    JudgeVerdict,
    LatentGraphScenario,
    OracleCheckpoint,
    judge_sim_checkpoint,
    sim_checkpoint_diagnostics,
)
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import DecisionModeName, LLMDecisionRuntimeConfig, LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.memory_evolution import FallbackOutcome, ProviderAttemptStatus, RetrievalPurpose
from memorii.core.memory_evolution.query_analysis.runtime_factory import build_production_query_analyzer
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.service import ProviderMemoryService
from memorii.tools.run_live_llm_eval import validate_live_safety


@dataclass(frozen=True)
class RuntimeRetrievalInvocation:
    """Benchmark translation into the public production retrieval contract."""

    purpose: RetrievalPurpose
    include_context: bool
    include_conflicts: bool


def runtime_retrieval_invocation(checkpoint: OracleCheckpoint) -> RuntimeRetrievalInvocation:
    view = checkpoint.required_retrieval_view
    supported_views = {
        "current",
        "historical_at",
        "all_versions",
        "conflicts",
        "evidence_only",
    }
    if view not in supported_views:
        raise ValueError(f"Unsupported runtime retrieval view: {view}")
    if checkpoint.checkpoint_type == "execution_continuation":
        return RuntimeRetrievalInvocation(
            purpose=RetrievalPurpose.EXECUTION,
            include_context=False,
            include_conflicts=False,
        )
    graph_reconstruction = (
        "graph_reconstruction" in checkpoint.task_contract.allowed_operations
        and checkpoint.task_contract.belief_ranking_policy != "required"
    )
    if graph_reconstruction:
        return RuntimeRetrievalInvocation(
            purpose=RetrievalPurpose.GRAPH_AUDIT,
            include_context=True,
            include_conflicts=view in {"all_versions", "conflicts"},
        )
    if view in {"all_versions", "conflicts", "historical_at", "evidence_only"}:
        return RuntimeRetrievalInvocation(
            purpose=RetrievalPurpose.ANSWER,
            include_context=True,
            include_conflicts=True,
        )
    if view == "current":
        return RuntimeRetrievalInvocation(
            purpose=RetrievalPurpose.ANSWER,
            include_context=False,
            include_conflicts=False,
        )
    raise AssertionError(f"unhandled runtime retrieval view: {view}")


def validate_runtime_live_safety(
    *, mode: str, dry_run: bool, allow_live: bool
) -> tuple[DecisionMode, LLMRuntimeConfig]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=decision_mode(mode))
        if mode != "auto"
        else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
    )
    effective_mode: DecisionMode = resolve_benchmark_decision_mode(
        decision_config=decision_config,
        runtime_config=runtime_config,
        dry_run=dry_run,
    )
    if effective_mode in {"llm", "hybrid"}:
        if not dry_run and not runtime_config.model:
            raise RuntimeError("live runtime benchmarks require an explicit MEMORII_LLM_MODEL")
        live_config = LLMLiveTestConfig.from_env(env_snapshot.env)
        validate_live_safety(
            modes=[effective_mode],
            dry_run=dry_run,
            allow_live=allow_live,
            runtime_config=runtime_config,
            live_config=live_config,
        )
        if not dry_run:
            runtime_config = runtime_config.model_copy(update={"max_retries": 0})
    return effective_mode, runtime_config


def decision_mode(mode: str) -> DecisionModeName:
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return cast(DecisionModeName, mode)
    raise ValueError(f"Unsupported memory evolution runtime mode: {mode}")


def run_runtime_scenarios(
    *,
    scenarios: list[LatentGraphScenario],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    live_client_factory: Callable[[LLMRuntimeConfig], LLMStructuredClient] = LLMClientFactory.from_config,
    provider_factory: Callable[..., ProviderMemoryService] | None = None,
) -> RuntimeSuiteRows:
    if provider_factory is None:
        raise RuntimeError(
            "memory-evolution runtime benchmarks require the writer-safe preplanning provider composition, "
            "which is unavailable in the governed-source admission source-only configuration"
        )
    requested_mode = decision_mode(mode)
    effective_mode, runtime_config = validate_runtime_live_safety(mode=mode, dry_run=dry_run, allow_live=allow_live)
    scenario_rows: list[SimScenarioResultRow] = []
    checkpoint_rows: list[RuntimeCheckpointResultRow] = []
    judge_rows: list[JudgeAggregate] = []
    llm_rows: list[RuntimeExtractorTraceRow] = []
    graph_snapshots: list[RuntimeGraphSnapshotRow] = []
    graph_items: list[RuntimeGraphItem] = []
    alignments: list[RuntimeGraphAlignmentRow] = []
    runtime_failures: list[RuntimeCheckpointResultRow] = []
    ingestion_traces: list[RuntimeIngestionTraceRow] = []
    ingestion_prefix_audits: list[IngestionPrefixAuditRow] = []

    for scenario in scenarios:
        extractor = build_runtime_extractor(
            scenario=scenario,
            effective_mode=effective_mode,
            dry_run=dry_run,
            runtime_config=runtime_config,
            prompt_root=prompt_root,
            live_client_factory=live_client_factory,
        )
        memory_plane = MemoryPlaneService()
        query_runtime_config = (
            runtime_config.model_copy(update={"provider": "none", "api_key": None}) if dry_run else runtime_config
        )
        query_analyzer = build_production_query_analyzer(
            runtime_config=query_runtime_config,
            prompt_root=prompt_root,
            client_factory=live_client_factory,
        )
        provider = provider_factory(
            memory_plane=memory_plane,
            memory_evolution_extractor=extractor,
            memory_evolution_query_analyzer=query_analyzer,
        )
        source_id_to_event_id: dict[str, str] = {}
        ordered_observations = sorted(scenario.observations, key=lambda item: (item.timestamp, item.event_id))
        observation_index = 0
        before_record_ids: set[str] = set()
        evolution_service = provider.memory_evolution_service
        scenario_checkpoint_rows: list[RuntimeCheckpointResultRow] = []
        scenario_prefix_audits: list[IngestionPrefixAuditRow] = []
        extractor_provider_successes = 0
        extractor_provider_failures = 0
        extractor_fallbacks = 0
        ingestion_context = IngestionContext()
        ordered_checkpoints = sorted(scenario.checkpoints, key=lambda item: (item.timestamp, item.checkpoint_id))
        for checkpoint_index, checkpoint in enumerate(ordered_checkpoints):
            checkpoint_run_start = len(recorded_extraction_runs(extractor))
            while (
                observation_index < len(ordered_observations)
                and ordered_observations[observation_index].timestamp <= checkpoint.timestamp
            ):
                observation = ordered_observations[observation_index]
                ingestion_result = ingest_surface_observation(
                    provider=provider,
                    memory_plane=memory_plane,
                    observation=observation,
                    context=ingestion_context,
                    before_ids=before_record_ids,
                )
                source_id_to_event_id.update(ingestion_result.source_id_to_event_id)
                extractor.record_operation_outcomes(ingestion_result.evolution_outcomes)
                extractor.record_evolution_results(ingestion_result.evolution_results)
                before_record_ids = {record.memory_id for record in memory_plane.list_records()}
                observation_index += 1
                prefix_audit = audit_ingestion_prefix(
                    scenario=scenario,
                    observations=ordered_observations[:observation_index],
                    snapshot=evolution_service.retrieve_graph_snapshot(),
                    source_id_to_event_id=source_id_to_event_id,
                )
                scenario_prefix_audits.append(prefix_audit)
                ingestion_prefix_audits.append(prefix_audit)
            prefix_runs = recorded_extraction_runs(extractor)
            ingestion_blocked = any(not audit.passed for audit in scenario_prefix_audits) or bool(
                runtime_ingestion_failure_buckets(prefix_runs)
            )
            work_state = evolution_service.derive_work_state()
            retrieval_decision = None
            composition_failures: list[str] = []
            if not ingestion_blocked:
                # Keep the benchmark on the provider-facing production retrieval
                # contract. The benchmark may judge the result, but it must not
                # bypass the provider's decision boundary.
                retrieval_invocation = runtime_retrieval_invocation(checkpoint)
                request_task_id = checkpoint.request_task_id or ingestion_context.task_id
                request_session_id = checkpoint.request_session_id or ingestion_context.session_id
                request_user_id = checkpoint.request_user_id or ingestion_context.user_id
                prefetch_result = provider.prefetch_result(
                    checkpoint.query_or_task,
                    reference_time=checkpoint.timestamp,
                    top_k=8,
                    include_context=retrieval_invocation.include_context,
                    include_conflicts=retrieval_invocation.include_conflicts,
                    purpose=retrieval_invocation.purpose,
                    query_language=checkpoint.query_language,
                    task_id=request_task_id,
                    session_id=request_session_id,
                    user_id=request_user_id,
                )
                retrieval_decision = prefetch_result.evolution_decision
                if retrieval_decision is None:
                    raise RuntimeError("production prefetch omitted its evolution decision")
                composition_failures = provider_composition_failure_buckets(prefetch_result)
            graph_snapshot = evolution_service.retrieve_graph_snapshot()
            normalization = graph_items_from_snapshot(
                scenario_id=scenario.scenario_id,
                snapshot=graph_snapshot,
                source_id_to_event_id=source_id_to_event_id,
            )
            runtime_graph_items = normalization.items
            graph_snapshots.append(
                RuntimeGraphSnapshotRow(
                    scenario_id=scenario.scenario_id,
                    checkpoint_id=checkpoint.checkpoint_id,
                    checkpoint_index=checkpoint_index,
                    is_terminal=checkpoint_index == len(ordered_checkpoints) - 1,
                    snapshot_id=graph_snapshot.snapshot_id,
                    nodes=list(graph_snapshot.nodes),
                    edges=list(graph_snapshot.edges),
                    validation_errors=[
                        *graph_snapshot.validation_errors,
                        *normalization.validation_errors,
                    ],
                    generated_at=graph_snapshot.generated_at.isoformat(),
                    source_run_id=graph_snapshot.source_run_id,
                )
            )
            graph_items.extend(runtime_graph_items)
            recorded_runs = recorded_extraction_runs(extractor)
            extractor_provider_successes = sum(
                run.provider_attempt_status == ProviderAttemptStatus.SUCCEEDED for run in recorded_runs
            )
            extractor_provider_failures = sum(
                run.provider_attempt_status
                in {
                    ProviderAttemptStatus.PROVIDER_ERROR,
                    ProviderAttemptStatus.INVALID_JSON,
                    ProviderAttemptStatus.SCHEMA_ERROR,
                }
                for run in recorded_runs
            )
            extractor_fallbacks = sum(run.fallback_outcome != FallbackOutcome.NOT_USED for run in recorded_runs)
            projection = project_runtime_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                graph_snapshot=graph_snapshot,
                graph_items=runtime_graph_items,
                source_id_to_event_id=source_id_to_event_id,
                work_state=work_state,
                retrieval_decision=retrieval_decision,
            )
            projection.stage_failure_buckets.extend(composition_failures)
            projection.stage_failure_buckets.extend(
                sorted(
                    {
                        f"production_ingestion_semantic_prefix_{issue.code}"
                        for audit in scenario_prefix_audits
                        if not audit.passed
                        for issue in audit.issues
                    }
                )
            )
            alignments.extend(
                RuntimeGraphAlignmentRow.from_alignment(
                    alignment,
                    scenario_id=scenario.scenario_id,
                    checkpoint_id=checkpoint.checkpoint_id,
                )
                for alignment in projection.alignments
            )
            raw_output = projection.output
            output = raw_output
            aggregate = (
                _ingestion_blocked_judge_aggregate(checkpoint)
                if ingestion_blocked
                else judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
            )
            diagnostics = sim_checkpoint_diagnostics(
                scenario=scenario, checkpoint=checkpoint, output=output, aggregate=aggregate
            )
            checkpoint_runs = recorded_extraction_runs(extractor)[checkpoint_run_start:]
            runtime_buckets = runtime_failure_buckets(
                checkpoint=checkpoint,
                output=output,
                projection=projection,
                graph_snapshot=graph_snapshot,
                recorded_runs=prefix_runs,
                ingestion_blocked=ingestion_blocked,
            )
            success = not runtime_buckets
            final_output_source = runtime_final_output_source(
                effective_mode=effective_mode,
                dry_run=dry_run,
                extractor=extractor,
                recorded_runs=checkpoint_runs,
            )
            row = build_runtime_checkpoint_result_row(
                scenario=scenario,
                checkpoint=checkpoint,
                mode=requested_mode,
                effective_mode=effective_mode,
                final_output_source=final_output_source,
                success=success,
                aggregate=aggregate,
                diagnostics=diagnostics,
                runtime_buckets=runtime_buckets,
                graph_snapshot=graph_snapshot,
                projection=projection,
                raw_output=raw_output,
                output=output,
                provider_successes=extractor_provider_successes,
                provider_failures=extractor_provider_failures,
                fallbacks=extractor_fallbacks,
                fallback_used=any(run.fallback_outcome != FallbackOutcome.NOT_USED for run in checkpoint_runs),
                recorded_runs=prefix_runs,
            )
            checkpoint_rows.append(row)
            scenario_checkpoint_rows.append(row)
            judge_rows.append(aggregate)
            if not success:
                runtime_failures.append(row)
        extractor_call_rows = extractor_trace_rows(
            scenario=scenario,
            extractor=extractor,
            effective_mode=effective_mode,
            dry_run=dry_run,
        )
        llm_rows.extend(extractor_call_rows)
        ingestion_traces.extend(recorded_extraction_runs(extractor))
        scenario_success = all(row.success is True for row in scenario_checkpoint_rows)
        scenario_rows.append(
            SimScenarioResultRow(
                scenario_id=scenario.scenario_id,
                semantic_world_fingerprint=scenario.semantic_world_fingerprint,
                family=scenario.family,
                profile=scenario.profile,
                decision_mode=requested_mode,
                effective_decision_mode=effective_mode,
                checkpoint_count=len(scenario_checkpoint_rows),
                success=scenario_success,
                failure_mode=None if scenario_success else "one_or_more_runtime_checkpoints_failed",
                checkpoints_passed=sum(row.success for row in scenario_checkpoint_rows),
                checkpoints_failed=sum(not row.success for row in scenario_checkpoint_rows),
            )
        )
    return RuntimeSuiteRows(
        scenario_rows=scenario_rows,
        checkpoint_rows=checkpoint_rows,
        judge_rows=judge_rows,
        llm_rows=llm_rows,
        graph_snapshots=graph_snapshots,
        graph_items=graph_items,
        alignments=alignments,
        runtime_failures=runtime_failures,
        ingestion_traces=ingestion_traces,
        ingestion_prefix_audits=ingestion_prefix_audits,
        effective_mode=effective_mode,
        dry_run=dry_run,
        provider_metadata=_provider_metadata(
            runtime_config=runtime_config,
            effective_mode=effective_mode,
            dry_run=dry_run,
        ),
    )


def _ingestion_blocked_judge_aggregate(checkpoint: OracleCheckpoint) -> JudgeAggregate:
    """Represent an intentionally unevaluated downstream judge boundary."""

    return JudgeAggregate(
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.ABSTAIN,
        score=0.0,
        confidence=0.0,
        votes=[],
        required_judge_ids=list(checkpoint.required_judge_ids),
        critical_failure_buckets=[],
        review_required=True,
        rationale="not evaluated because ingestion prefix validation failed",
    )


def _provider_metadata(
    *,
    runtime_config: LLMRuntimeConfig,
    effective_mode: DecisionMode,
    dry_run: bool,
) -> dict[str, str]:
    if dry_run and effective_mode in {"llm", "hybrid"}:
        return {"backend": "fake_oracle", "provider": "fake"}
    if effective_mode == "rule":
        return {"backend": "rule", "provider": "none"}
    return {
        "backend": "live_provider",
        "provider": runtime_config.provider,
        "model": runtime_config.model or "provider_default",
        "timeout_seconds": str(runtime_config.timeout_seconds),
        "max_retries": str(runtime_config.max_retries),
    }
