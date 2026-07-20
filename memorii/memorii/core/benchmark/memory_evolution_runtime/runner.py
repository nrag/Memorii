"""Runtime benchmark suite orchestration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from memorii.core.benchmark.artifact_rows import (
    DecisionMode,
    RuntimeCheckpointResultRow,
    RuntimeExtractorTraceRow,
    RuntimeGraphAlignmentRow,
    SimScenarioResultRow,
)
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_evaluation import runtime_failure_buckets
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection import project_runtime_checkpoint
from memorii.core.benchmark.memory_evolution_runtime.extractors import (
    build_runtime_extractor,
    recorded_extraction_runs,
)
from memorii.core.benchmark.memory_evolution_runtime.graph_items import (
    graph_items_from_snapshot,
)
from memorii.core.benchmark.memory_evolution_runtime.ingestion import IngestionContext, ingest_surface_observation
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeGraphItemRow,
    RuntimeGraphSnapshotRow,
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
    LatentGraphScenario,
    judge_sim_checkpoint,
    sim_checkpoint_diagnostics,
)
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import DecisionModeName, LLMDecisionRuntimeConfig, LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.memory_evolution import RetrievalPurpose
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.service import ProviderMemoryService
from memorii.tools.run_live_llm_eval import validate_live_safety


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
    effective_mode = decision_config.resolve(runtime_config)
    if effective_mode in {"llm", "hybrid"}:
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
) -> RuntimeSuiteRows:
    requested_mode = decision_mode(mode)
    effective_mode, runtime_config = validate_runtime_live_safety(mode=mode, dry_run=dry_run, allow_live=allow_live)
    scenario_rows: list[SimScenarioResultRow] = []
    checkpoint_rows: list[RuntimeCheckpointResultRow] = []
    judge_rows: list[JudgeAggregate] = []
    llm_rows: list[RuntimeExtractorTraceRow] = []
    graph_snapshots: list[RuntimeGraphSnapshotRow] = []
    graph_items: list[RuntimeGraphItemRow] = []
    alignments: list[RuntimeGraphAlignmentRow] = []
    runtime_failures: list[RuntimeCheckpointResultRow] = []

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
        provider = ProviderMemoryService(
            memory_plane=memory_plane,
            memory_evolution_extractor=extractor,
        )
        source_id_to_event_id: dict[str, str] = {}
        ordered_observations = sorted(scenario.observations, key=lambda item: (item.timestamp, item.event_id))
        observation_index = 0
        before_record_ids: set[str] = set()
        evolution_service = provider.memory_evolution_service
        scenario_checkpoint_rows: list[RuntimeCheckpointResultRow] = []
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
                source_id_to_event_id.update(
                    ingest_surface_observation(
                        provider=provider,
                        memory_plane=memory_plane,
                        observation=observation,
                        context=ingestion_context,
                        before_ids=before_record_ids,
                    )
                )
                before_record_ids = {record.memory_id for record in memory_plane.list_records()}
                observation_index += 1
            work_state = evolution_service.derive_work_state()
            # Keep the benchmark on the provider-facing production retrieval
            # contract. The benchmark may judge the result, but it must not
            # bypass the provider's decision boundary.
            is_graph_audit = checkpoint.checkpoint_type in {
                "entity_reconstruction",
                "conflict_audit",
                "claim_rekey",
            }
            request_task_id = checkpoint.request_task_id or ingestion_context.task_id
            request_session_id = checkpoint.request_session_id or ingestion_context.session_id
            request_user_id = checkpoint.request_user_id or ingestion_context.user_id
            retrieval_purpose = (
                RetrievalPurpose.GRAPH_AUDIT
                if is_graph_audit
                else RetrievalPurpose.EXECUTION
                if checkpoint.checkpoint_type == "execution_continuation"
                else RetrievalPurpose.ANSWER
            )
            prefetch_result = provider.prefetch_result(
                checkpoint.query_or_task,
                reference_time=checkpoint.timestamp,
                top_k=8,
                include_context=True,
                include_conflicts=True,
                purpose=retrieval_purpose,
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
            extractor_provider_successes = sum(run.success for run in recorded_runs)
            extractor_provider_failures = sum(not run.success for run in recorded_runs)
            extractor_fallbacks = sum(run.fallback_used for run in recorded_runs)
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
            aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
            diagnostics = sim_checkpoint_diagnostics(
                scenario=scenario, checkpoint=checkpoint, output=output, aggregate=aggregate
            )
            runtime_buckets = runtime_failure_buckets(
                checkpoint=checkpoint,
                output=output,
                aggregate=aggregate,
                projection=projection,
                graph_snapshot=graph_snapshot,
            )
            success = aggregate.verdict.value == "pass" and not runtime_buckets
            checkpoint_runs = recorded_extraction_runs(extractor)[checkpoint_run_start:]
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
                fallback_used=any(run.fallback_used for run in checkpoint_runs),
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
        effective_mode=effective_mode,
        dry_run=dry_run,
    )
