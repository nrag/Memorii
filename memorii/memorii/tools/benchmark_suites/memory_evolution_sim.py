"""Latent graph memory evolution simulator benchmark suite runner."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from memorii.core.benchmark.artifact_rows import (
    CheckpointDecisionTraceSection,
    CheckpointDiagnosticsPayload,
    CheckpointDiagnosticsSection,
    CheckpointHorizonSection,
    CheckpointVerdictSection,
    DecisionMode,
    FinalOutputSource,
    SimCheckpointResultRow,
    SimLLMTraceRow,
    SimScenarioResultRow,
    checkpoint_warning_buckets,
)
from memorii.core.benchmark.artifact_validation import (
    finalize_memory_evolution_run,
    validate_memory_evolution_run,
)
from memorii.core.benchmark.decision_modes import resolve_benchmark_decision_mode
from memorii.core.benchmark.llm_adapters import LLMMemoryEvolutionSimReconstructionAdapter
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    OracleCheckpoint,
    SimSystemOutput,
    judge_sim_checkpoint,
    memory_evolution_sim_engine_result_from_llm,
    memory_evolution_sim_trace_for_rule,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import (
    DecisionModeName,
    LLMDecisionRuntimeConfig,
    LLMLiveTestConfig,
    LLMRuntimeConfig,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.common import (
    ALL_DECISION_MODES,
    require_memorii_only,
)
from memorii.tools.benchmark_suites.fake_adapters import ExpectedMemoryEvolutionSimFakeAdapter
from memorii.tools.benchmark_suites.memory_evolution_artifacts import (
    horizon_distance_bucket,
    interference_count_bucket,
    print_memory_evolution_summary,
    source_event_age_days_bucket,
    write_memory_evolution_artifacts,
)
from memorii.tools.benchmark_suites.memory_evolution_scenarios import (
    load_memory_evolution_scenarios,
)
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_live_llm_eval import validate_live_safety

SUITE_NAME = "memory_evolution_sim_v1"
_INVALID_REFERENCE_ID_BUCKET = "invalid_reference_id"


def _decision_modes_from_args(mode: str) -> list[DecisionModeName]:
    if mode == "all":
        return ["rule", "llm", "hybrid"]
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return [cast(DecisionModeName, mode)]
    raise ValueError(f"Unsupported memory evolution sim mode: {mode}")


def _ordered_unique(values: Sequence[object]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _run_memory_evolution_sim_transitions(
    *,
    scenarios: list[LatentGraphScenario],
    mode: DecisionModeName,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> tuple[
    list[SimScenarioResultRow],
    list[SimCheckpointResultRow],
    list[JudgeAggregate],
    list[SimLLMTraceRow],
]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=mode) if mode != "auto" else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
    )
    effective_mode = resolve_benchmark_decision_mode(
        decision_config=decision_config,
        runtime_config=runtime_config,
        dry_run=dry_run,
    )
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

    registry = PromptRegistry(prompt_root=prompt_root)
    adapter = None
    llm_binding = None
    if effective_mode in {"llm", "hybrid"}:
        llm_binding = dependencies.bind_llm_client(dry_run=dry_run, config=runtime_config)
        runner = PromptLLMRunner(client=llm_binding.client, config=runtime_config)
        adapter = (
            ExpectedMemoryEvolutionSimFakeAdapter(scenarios=scenarios, registry=registry)
            if dependencies.use_oracle_adapters(dry_run=dry_run)
            else LLMMemoryEvolutionSimReconstructionAdapter(runner=runner, registry=registry)
        )

    scenario_rows: list[SimScenarioResultRow] = []
    checkpoint_rows: list[SimCheckpointResultRow] = []
    judge_rows: list[JudgeAggregate] = []
    llm_rows: list[SimLLMTraceRow] = []

    for scenario in scenarios:
        scenario_checkpoint_rows: list[SimCheckpointResultRow] = []
        for checkpoint in scenario.checkpoints:
            context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
            rule_output = rule_sim_output_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
            rule_output_json = rule_output.model_dump(mode="json")
            rule_trace = memory_evolution_sim_trace_for_rule(context=context, decision=rule_output, mode="rule")
            request_id = f"memory_evolution_sim:{mode}:{scenario.scenario_id}:{checkpoint.checkpoint_id}"
            output_json = rule_output_json
            llm_call_made = False
            llm_success = False
            fallback_used = effective_mode in {"auto", "hybrid"} and effective_mode == "rule"
            fallback_reason = "llm_not_configured" if fallback_used else None
            final_output_source = "rule"
            llm_trace = rule_trace

            if effective_mode in {"llm", "hybrid"} and adapter is not None:
                llm_call_made = True
                result = adapter.decide(
                    context,
                    request_id=request_id,
                    metadata={
                        "suite": "memory_evolution_sim_v1",
                        "scenario_id": scenario.scenario_id,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "decision_mode": mode,
                        "effective_decision_mode": effective_mode,
                        "transition_type": "memory_evolution_sim_reconstruction",
                    },
                )
                output_json, llm_trace, llm_success, fallback_reason = memory_evolution_sim_engine_result_from_llm(
                    result=result,
                    mode=LLMDecisionMode(effective_mode),
                    scenario=scenario,
                    rule_output=rule_output_json,
                )
                invalid_reference_failure = fallback_reason == "llm_output_referenced_invalid_ids"
                if llm_success or invalid_reference_failure:
                    if llm_binding is None:
                        raise RuntimeError("LLM result is missing execution provenance")
                    final_output_source = llm_binding.final_output_source
                else:
                    final_output_source = "rule"
                fallback_used = not llm_success and not invalid_reference_failure
                llm_rows.append(
                    SimLLMTraceRow(
                        scenario_id=scenario.scenario_id,
                        checkpoint_id=checkpoint.checkpoint_id,
                        transition_type="memory_evolution_sim_reconstruction",
                        decision_mode=mode,
                        effective_decision_mode=effective_mode,
                        final_output_source=final_output_source,
                        trace=llm_trace,
                        success=llm_success,
                        fallback_used=fallback_used,
                        failure_mode=fallback_reason,
                        output=SimSystemOutput.model_validate(output_json),
                    )
                )

            raw_output = SimSystemOutput.model_validate(output_json)
            output = raw_output
            aggregate = judge_sim_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                output=output,
            )
            invalid_reference_failure = fallback_reason == "llm_output_referenced_invalid_ids"
            diagnostics = sim_checkpoint_diagnostics(
                scenario=scenario,
                checkpoint=checkpoint,
                output=output,
                aggregate=aggregate,
            )
            engine_failure_buckets = [_INVALID_REFERENCE_ID_BUCKET] if invalid_reference_failure else []
            if effective_mode == "llm" and llm_call_made and not llm_success:
                engine_failure_buckets.append(fallback_reason or "llm_provider_failure")
            success = (
                aggregate.verdict.value == "pass"
                and (effective_mode != "llm" or llm_success or not llm_call_made)
                and not invalid_reference_failure
            )
            warning_buckets = checkpoint_warning_buckets(
                answer_match_type=diagnostics.answer_match_type,
                output=output,
            )
            checkpoint_row = _build_sim_checkpoint_result_row(
                scenario=scenario,
                checkpoint=checkpoint,
                context=context,
                mode=mode,
                effective_mode=effective_mode,
                llm_call_made=llm_call_made,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                final_output_source=final_output_source,
                request_id=request_id if llm_call_made else llm_trace.trace_id,
                success=success,
                aggregate=aggregate,
                diagnostics=diagnostics,
                engine_failure_buckets=engine_failure_buckets,
                warning_buckets=warning_buckets,
                raw_output=raw_output,
                output=output,
            )
            checkpoint_rows.append(checkpoint_row)
            scenario_checkpoint_rows.append(checkpoint_row)
            judge_rows.append(aggregate)

        scenario_success = all(row.success is True for row in scenario_checkpoint_rows)
        scenario_rows.append(
            SimScenarioResultRow(
                scenario_id=scenario.scenario_id,
                semantic_world_fingerprint=scenario.semantic_world_fingerprint,
                family=scenario.family,
                profile=scenario.profile,
                decision_mode=mode,
                effective_decision_mode=effective_mode,
                checkpoint_count=len(scenario_checkpoint_rows),
                success=scenario_success,
                failure_mode=None if scenario_success else "one_or_more_checkpoints_failed",
                checkpoints_passed=sum(1 for row in scenario_checkpoint_rows if row.success),
                checkpoints_failed=sum(1 for row in scenario_checkpoint_rows if not row.success),
            )
        )
    return scenario_rows, checkpoint_rows, judge_rows, llm_rows


def _build_sim_checkpoint_result_row(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    context: MemoryEvolutionSimReconstructionContext,
    mode: DecisionMode,
    effective_mode: DecisionMode,
    llm_call_made: bool,
    fallback_used: bool,
    fallback_reason: str | None,
    final_output_source: FinalOutputSource,
    request_id: str,
    success: bool,
    aggregate: JudgeAggregate,
    diagnostics: CheckpointDiagnosticsSection,
    engine_failure_buckets: list[str],
    warning_buckets: list[str],
    raw_output: SimSystemOutput,
    output: SimSystemOutput,
) -> SimCheckpointResultRow:
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
        llm_call_made=llm_call_made,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        final_output_source=final_output_source,
        request_id=request_id,
    )
    verdict = CheckpointVerdictSection(
        success=success,
        passed=bool(success),
        verdict=(aggregate.verdict.value if aggregate.verdict.value != "pass" or success else "fail"),
        score=aggregate.score,
        confidence=aggregate.confidence,
        review_required=aggregate.review_required or bool(engine_failure_buckets),
        failure_buckets=_ordered_unique([*aggregate.critical_failure_buckets, *engine_failure_buckets]),
        warning_buckets=warning_buckets,
    )
    diagnostic_section = diagnostics
    if engine_failure_buckets:
        diagnostic_section = diagnostic_section.model_copy(
            update={
                "failure_classification": _ordered_unique(
                    [*diagnostic_section.failure_classification, *engine_failure_buckets]
                ),
                "precision_failure_classification": _ordered_unique(
                    [*diagnostic_section.precision_failure_classification, *engine_failure_buckets]
                ),
            }
        )
    diagnostics_payload = CheckpointDiagnosticsPayload.from_sections(diagnostic_section)
    return SimCheckpointResultRow(
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
        diagnostics=diagnostics_payload,
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
        candidate_cards=context,
        raw_output=raw_output,
        judge_aggregate=aggregate,
    )


def _run_memory_evolution_sim_suite(
    args: argparse.Namespace,
    *,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> int:
    scenarios, fixture_source = load_memory_evolution_scenarios(args)
    modes = _decision_modes_from_args(args.mode)
    benchmark_failed = False
    for mode in modes:
        scenario_rows, checkpoint_rows, judge_rows, llm_rows = _run_memory_evolution_sim_transitions(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
            dependencies=dependencies,
        )
        run_dir = write_memory_evolution_artifacts(
            scenarios=scenarios,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            judge_rows=judge_rows,
            llm_rows=llm_rows,
            suite=SUITE_NAME,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
            args=args,
        )
        finalize_memory_evolution_run(run_dir)
        validate_memory_evolution_run(run_dir, suite=SUITE_NAME)
        print_memory_evolution_summary(
            suite=SUITE_NAME,
            mode=mode,
            profile=args.sim_profile,
            run_dir=run_dir,
            scenarios=scenarios,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            llm_rows=llm_rows,
        )
        benchmark_failed = benchmark_failed or any(not row.success for row in checkpoint_rows)
    if getattr(args, "fail_on_benchmark_failure", False) and benchmark_failed:
        return 1
    return 0


def run(args: argparse.Namespace, prompt_root: Path, *, dependencies: BenchmarkRuntimeDependencies) -> int:
    require_memorii_only(args, SUITE_NAME)
    return _run_memory_evolution_sim_suite(args, prompt_root=prompt_root, dependencies=dependencies)


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FunctionBenchmarkSuiteRunner(
        SUITE_NAME,
        lambda args, prompt_root: run(args, prompt_root, dependencies=dependencies),
        ALL_DECISION_MODES,
    )
