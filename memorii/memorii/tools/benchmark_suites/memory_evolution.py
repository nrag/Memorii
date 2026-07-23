"""Hand-authored memory evolution benchmark suite runner."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from datetime import (
    UTC,
    datetime,
)
from pathlib import Path
from typing import Literal, cast

from memorii.core.benchmark.artifact_rows import (
    CuratedMemoryEvolutionLLMTraceRow,
    DecisionMode,
    FinalOutputSource,
    SemanticDecisionAttemptRow,
    artifact_row_to_json,
)
from memorii.core.benchmark.bounded_semantic_repair import run_with_one_semantic_repair
from memorii.core.benchmark.decision_modes import resolve_benchmark_decision_mode
from memorii.core.benchmark.fixture_sets.memory_evolution_v1 import load_memory_evolution_v1_fixture_set
from memorii.core.benchmark.llm_adapters import LLMMemoryEvolutionDecisionAdapter
from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionDecision,
    MemoryEvolutionScenario,
    MemoryEvolutionSemanticDecision,
    MemoryEvolutionSemanticRepairRequest,
    memory_evolution_context_for_checkpoint,
    memory_evolution_decision_diagnostics,
    memory_evolution_engine_result_from_llm,
    memory_evolution_trace_for_rule,
    rule_memory_evolution_decision_for_checkpoint,
)
from memorii.core.benchmark.models import BenchmarkRunConfig
from memorii.core.benchmark.reproducibility import build_run_id
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import (
    DecisionModeName,
    LLMDecisionRuntimeConfig,
    LLMLiveTestConfig,
    LLMRuntimeConfig,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.models import LLMDecisionResult
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution import FallbackOutcome, ProviderAttemptStatus
from memorii.core.prompts.registry import PromptRegistry
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.artifact_io import write_jsonl
from memorii.tools.benchmark_suites.common import (
    ALL_DECISION_MODES,
    require_memorii_only,
)
from memorii.tools.benchmark_suites.fake_adapters import ExpectedMemoryEvolutionFakeAdapter
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_live_llm_eval import validate_live_safety

SUITE_NAME = "memory_evolution_v1"


def _decision_mode(mode: str) -> DecisionModeName:
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return cast(DecisionModeName, mode)
    raise ValueError(f"Unsupported memory evolution mode: {mode}")


def _load_memory_evolution_suite(suite: str) -> tuple[list[MemoryEvolutionScenario], str]:
    if suite == SUITE_NAME:
        return (
            load_memory_evolution_v1_fixture_set(),
            "memorii.core.benchmark.fixture_sets.memory_evolution_v1",
        )
    raise ValueError(f"Unsupported memory evolution benchmark suite: {suite}")

def _run_memory_evolution_transitions(
    *,
    scenarios: list[MemoryEvolutionScenario],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[CuratedMemoryEvolutionLLMTraceRow],
]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=_decision_mode(mode))
        if mode != "auto"
        else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
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
            ExpectedMemoryEvolutionFakeAdapter(scenarios=scenarios, registry=registry)
            if dependencies.use_oracle_adapters(dry_run=dry_run)
            else LLMMemoryEvolutionDecisionAdapter(runner=runner, registry=registry)
        )

    scenario_rows: list[dict[str, object]] = []
    checkpoint_rows: list[dict[str, object]] = []
    llm_rows: list[CuratedMemoryEvolutionLLMTraceRow] = []
    for scenario in scenarios:
        scenario_checkpoint_rows: list[dict[str, object]] = []
        for checkpoint in scenario.checkpoints:
            context = memory_evolution_context_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            rule_decision = rule_memory_evolution_decision_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            rule_output = rule_decision.model_dump(mode="json")
            rule_trace = memory_evolution_trace_for_rule(
                context=context,
                decision=rule_decision,
                mode="rule",
            )
            request_id = f"memory_evolution:{mode}:{scenario.scenario_id}:{checkpoint.checkpoint_id}"
            output = rule_output
            llm_success = False
            llm_used = False
            fallback_used = effective_mode in {"auto", "hybrid"} and effective_mode == "rule"
            fallback_reason = "llm_not_configured" if fallback_used else None
            final_output_source = "rule"

            if effective_mode in {"llm", "hybrid"} and adapter is not None:
                llm_used = True
                metadata: dict[str, object] = {
                    "suite": "memory_evolution_v1",
                    "scenario_id": scenario.scenario_id,
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "decision_mode": mode,
                    "transition_type": "memory_evolution_decision",
                }
                resolution = run_with_one_semantic_repair(
                    context=context,
                    request_id=request_id,
                    metadata=metadata,
                    decide=lambda candidate_context, candidate_request_id, candidate_metadata: adapter.decide(
                        candidate_context,
                        request_id=candidate_request_id,
                        metadata=candidate_metadata,
                    ),
                    evaluate=lambda result, candidate_context, rule_output=rule_output: (
                        memory_evolution_engine_result_from_llm(
                            result=result,
                            mode=LLMDecisionMode(effective_mode),
                            context=candidate_context,
                            rule_output=rule_output,
                        )
                    ),
                    build_repair_context=lambda original, output_payload, violation_codes: original.model_copy(
                        update={
                            "repair_request": MemoryEvolutionSemanticRepairRequest(
                                violation_codes=violation_codes,
                                previous_decision=MemoryEvolutionSemanticDecision.model_validate(
                                    output_payload
                                ),
                            )
                        }
                    ),
                )
                final_attempt = resolution.final_attempt
                output = final_attempt.output
                llm_trace = final_attempt.trace
                llm_success = final_attempt.success
                fallback_reason = final_attempt.failure_mode
                provider_attempts = [
                    _memory_evolution_provider_attempt(
                        attempt=index,
                        result=attempt.provider_result,
                        accepted=attempt.success,
                        failure_mode=attempt.failure_mode,
                        validation_issues=[
                            issue.code for issue in attempt.trace.validation_issues
                        ],
                    )
                    for index, attempt in enumerate(resolution.attempts)
                ]
                if llm_success:
                    if llm_binding is None:
                        raise RuntimeError("LLM result is missing execution provenance")
                    final_output_source = llm_binding.final_output_source
                else:
                    final_output_source = "rule"
                llm_rows.append(
                    CuratedMemoryEvolutionLLMTraceRow(
                        scenario_id=scenario.scenario_id,
                        checkpoint_id=checkpoint.checkpoint_id,
                        transition_type="memory_evolution_decision",
                        decision_mode=cast(DecisionMode, mode),
                        effective_decision_mode=effective_mode,
                        final_output_source=cast(FinalOutputSource, final_output_source),
                        trace=llm_trace,
                        provider_attempt_status=_provider_attempt_status(
                            final_attempt.provider_result
                        ),
                        semantic_validation_status=_semantic_validation_status(
                            final_attempt.provider_result
                        ),
                        fallback_outcome=(
                            FallbackOutcome.NOT_USED if llm_success else FallbackOutcome.SUCCEEDED
                        ),
                        final_output_accepted=llm_success,
                        failure_mode=fallback_reason,
                        provider_attempts=provider_attempts,
                        output=MemoryEvolutionDecision.model_validate(output),
                    )
                )
            else:
                llm_trace = rule_trace

            diagnostics = memory_evolution_decision_diagnostics(
                scenario=scenario,
                checkpoint=checkpoint,
                decision=output,
            )
            assertion_passed = diagnostics.assertion_passed
            functional_success = assertion_passed
            model_success = assertion_passed and (llm_success if llm_used else True)
            fallback_assisted_success = bool(
                llm_used
                and not llm_success
                and llm_trace.fallback_used
                and assertion_passed
            )
            success = model_success
            checkpoint_row = {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "checkpoint_id": checkpoint.checkpoint_id,
                "query_or_task": checkpoint.query_or_task,
                "discriminative": scenario.discriminative,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "llm_call_made": llm_used,
                "fallback_used": llm_trace.fallback_used if llm_used else fallback_used,
                "fallback_reason": fallback_reason,
                "final_output_source": final_output_source,
                "request_id": request_id if llm_used else llm_trace.trace_id,
                "success": success,
                "functional_success": functional_success,
                "model_success": model_success,
                "final_output_accepted": llm_success if llm_used else None,
                "fallback_assisted_success": fallback_assisted_success,
                "failure_mode": None if success else (fallback_reason or "memory_evolution_assertion_failed"),
                "transition_assertion_passed": assertion_passed,
                "memory_evolution_assertion_passed": assertion_passed,
                "expected": checkpoint.model_dump(mode="json"),
                "output": output,
                "diagnostics": diagnostics.model_dump(mode="json"),
                "failure_buckets": diagnostics.failure_buckets,
                "warning_buckets": diagnostics.warning_buckets,
            }
            checkpoint_rows.append(checkpoint_row)
            scenario_checkpoint_rows.append(checkpoint_row)

        scenario_success = all(row["success"] is True for row in scenario_checkpoint_rows)
        scenario_functional_success = all(
            row["functional_success"] is True for row in scenario_checkpoint_rows
        )
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "discriminative": scenario.discriminative,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "checkpoint_count": len(scenario_checkpoint_rows),
                "success": scenario_success,
                "functional_success": scenario_functional_success,
                "model_success": scenario_success,
                "failure_mode": None if scenario_success else "one_or_more_checkpoints_failed",
                "checkpoints_passed": sum(1 for row in scenario_checkpoint_rows if row["success"] is True),
                "checkpoints_failed": sum(1 for row in scenario_checkpoint_rows if row["success"] is False),
            }
        )
    return scenario_rows, checkpoint_rows, llm_rows


def _memory_evolution_provider_attempt(
    *,
    attempt: int,
    result: LLMDecisionResult,
    accepted: bool,
    failure_mode: str | None,
    validation_issues: list[str],
) -> SemanticDecisionAttemptRow:
    return SemanticDecisionAttemptRow(
        attempt=attempt,
        request_id=result.request.request_id,
        provider_attempt_status=_provider_attempt_status(result),
        semantic_validation_status=_semantic_validation_status(result),
        accepted=accepted,
        failure_mode=failure_mode,
        validation_issues=validation_issues,
    )


def _provider_attempt_status(result: LLMDecisionResult) -> ProviderAttemptStatus:
    if result.success or result.failure_mode == "semantic_validation":
        return ProviderAttemptStatus.SUCCEEDED
    return {
        "provider_error": ProviderAttemptStatus.PROVIDER_ERROR,
        "invalid_json": ProviderAttemptStatus.INVALID_JSON,
        "schema_validation": ProviderAttemptStatus.SCHEMA_ERROR,
    }.get(result.failure_mode or "", ProviderAttemptStatus.SCHEMA_ERROR)


def _semantic_validation_status(
    result: LLMDecisionResult,
) -> Literal["not_evaluated", "passed", "failed"]:
    if result.failure_mode == "semantic_validation":
        return "failed"
    return "passed" if result.success else "not_evaluated"


def memory_evolution_artifact_run_metadata(
    *,
    suite: str,
    mode: str,
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: list[dict[str, object]],
    dry_run: bool,
    allow_live: bool,
) -> dict[str, object]:
    benchmark_key = build_run_id(
        config=BenchmarkRunConfig(seed=7, run_label=f"{suite}_{mode}"),
        fixtures=[],
    )
    effective_modes = _effective_modes_for_rows(scenario_rows=scenario_rows, checkpoint_rows=checkpoint_rows)
    live_run = bool(allow_live and not dry_run and effective_modes & {"llm", "hybrid"})
    run_id = benchmark_key
    if live_run:
        run_id = f"{benchmark_key}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    return {
        "run_id": run_id,
        "benchmark_key": benchmark_key,
        "effective_decision_modes": sorted(effective_modes),
        "dry_run": dry_run,
        "allow_live": allow_live,
        "live_run": live_run,
    }


def _effective_modes_for_rows(
    *,
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: list[dict[str, object]],
) -> set[str]:
    modes: set[str] = set()
    for row in [*scenario_rows, *checkpoint_rows]:
        value = row.get("effective_decision_mode")
        if isinstance(value, str) and value:
            modes.add(value)
    return modes


def _write_memory_evolution_artifacts(
    *,
    scenarios: list[MemoryEvolutionScenario],
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: list[dict[str, object]],
    llm_rows: list[CuratedMemoryEvolutionLLMTraceRow],
    suite: str,
    mode: str,
    storage_root: str,
    fixture_source: str,
    dry_run: bool,
    allow_live: bool,
) -> Path:
    run_metadata = memory_evolution_artifact_run_metadata(
        suite=suite,
        mode=mode,
        scenario_rows=scenario_rows,
        checkpoint_rows=checkpoint_rows,
        dry_run=dry_run,
        allow_live=allow_live,
    )
    run_id = str(run_metadata["run_id"])
    run_dir = Path(storage_root) / "benchmark_runs" / suite / mode / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    functional_passed = sum(1 for row in scenario_rows if row["functional_success"] is True)
    functional_failed = len(scenario_rows) - functional_passed
    functional_checkpoints_passed = sum(
        1 for row in checkpoint_rows if row["functional_success"] is True
    )
    functional_checkpoints_failed = len(checkpoint_rows) - functional_checkpoints_passed
    provider_attempts = [
        attempt
        for row in llm_rows
        for attempt in row.provider_attempts
    ]
    provider_attempt_counts = Counter(
        attempt.provider_attempt_status.value for attempt in provider_attempts
    )
    semantic_validation_counts = Counter(
        attempt.semantic_validation_status for attempt in provider_attempts
    )
    fallback_outcome_counts = Counter(row.fallback_outcome.value for row in llm_rows)
    final_output_source_counts = Counter(row.final_output_source for row in llm_rows)
    final_outputs_accepted = sum(1 for row in llm_rows if row.final_output_accepted)
    fallback_assisted_passes = sum(
        1 for row in checkpoint_rows if row["fallback_assisted_success"] is True
    )
    local_certification_passed = (
        None
        if not llm_rows
        else bool(
            all(row["success"] is True for row in checkpoint_rows)
            and final_outputs_accepted == len(llm_rows)
            and fallback_assisted_passes == 0
        )
    )
    report_bucket_counts = _memory_evolution_report_bucket_counts(checkpoint_rows)
    discriminative_scenario_ids = {
        scenario.scenario_id for scenario in scenarios if scenario.discriminative
    }
    discriminative_scenario_rows = [
        row for row in scenario_rows if row["scenario_id"] in discriminative_scenario_ids
    ]
    non_discriminative_scenario_rows = [
        row for row in scenario_rows if row["scenario_id"] not in discriminative_scenario_ids
    ]
    discriminative_checkpoint_rows = [
        row for row in checkpoint_rows if row["scenario_id"] in discriminative_scenario_ids
    ]
    non_discriminative_checkpoint_rows = [
        row for row in checkpoint_rows if row["scenario_id"] not in discriminative_scenario_ids
    ]
    lifecycle_scope_counts = _lifecycle_expectation_scope_counts(checkpoint_rows)
    report = {
        "suite": suite,
        "mode": mode,
        **run_metadata,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_source": fixture_source,
        "storage_root": storage_root,
        "artifact_version": "memory_evolution_v1_artifacts:4",
        "scenarios": len(scenario_rows),
        "checkpoints": len(checkpoint_rows),
        "passed": passed,
        "failed": failed,
        "functional_passed": functional_passed,
        "functional_failed": functional_failed,
        "functional_checkpoints_passed": functional_checkpoints_passed,
        "functional_checkpoints_failed": functional_checkpoints_failed,
        "llm_calls": len(provider_attempts),
        "provider_attempt_counts": dict(sorted(provider_attempt_counts.items())),
        "semantic_validation_counts": dict(sorted(semantic_validation_counts.items())),
        "final_outputs_accepted": final_outputs_accepted,
        "final_outputs_rejected": len(llm_rows) - final_outputs_accepted,
        "fallback_outcome_counts": dict(sorted(fallback_outcome_counts.items())),
        "fallback_assisted_passes": fallback_assisted_passes,
        "final_output_source_counts": dict(sorted(final_output_source_counts.items())),
        "local_certification_passed": local_certification_passed,
        "discriminative_scenarios": len(discriminative_scenario_rows),
        "non_discriminative_scenarios": len(non_discriminative_scenario_rows),
        "discriminative_passed": sum(1 for row in discriminative_scenario_rows if row["success"] is True),
        "discriminative_failed": sum(1 for row in discriminative_scenario_rows if row["success"] is False),
        "non_discriminative_passed": sum(1 for row in non_discriminative_scenario_rows if row["success"] is True),
        "non_discriminative_failed": sum(1 for row in non_discriminative_scenario_rows if row["success"] is False),
        "discriminative_checkpoints": len(discriminative_checkpoint_rows),
        "non_discriminative_checkpoints": len(non_discriminative_checkpoint_rows),
        "discriminative_checkpoints_passed": sum(1 for row in discriminative_checkpoint_rows if row["success"] is True),
        "discriminative_checkpoints_failed": sum(1 for row in discriminative_checkpoint_rows if row["success"] is False),
        "non_discriminative_checkpoints_passed": sum(1 for row in non_discriminative_checkpoint_rows if row["success"] is True),
        "non_discriminative_checkpoints_failed": sum(1 for row in non_discriminative_checkpoint_rows if row["success"] is False),
        "lifecycle_expectation_scope_counts": lifecycle_scope_counts,
        **report_bucket_counts,
        "scenario_results": scenario_rows,
        "checkpoint_results": checkpoint_rows,
    }
    report_json = json.dumps(report, indent=2, sort_keys=True)
    report_md = (
        f"# {suite}\n\n"
        f"mode={mode} scenarios={len(scenario_rows)} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} functional_passed={functional_passed} "
        f"functional_failed={functional_failed} llm_calls={len(provider_attempts)} "
        f"final_outputs_accepted={final_outputs_accepted} "
        f"fallback_assisted_passes={fallback_assisted_passes} "
        f"local_certification_passed={local_certification_passed}\n"
    )
    (run_dir / "report.json").write_text(report_json, encoding="utf-8")
    (run_dir / "memory_evolution_report.json").write_text(report_json, encoding="utf-8")
    (run_dir / "report.md").write_text(report_md, encoding="utf-8")
    (run_dir / "memory_evolution_report.md").write_text(report_md, encoding="utf-8")
    (run_dir / "fixtures.json").write_text(
        json.dumps([scenario.model_dump(mode="json") for scenario in scenarios], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_jsonl(run_dir / "memory_evolution_traces.jsonl", scenario_rows)
    write_jsonl(run_dir / "memory_evolution_checkpoint_traces.jsonl", checkpoint_rows)
    write_jsonl(run_dir / "llm_traces.jsonl", [artifact_row_to_json(row) for row in llm_rows])
    write_jsonl(run_dir / "failures.jsonl", [row for row in checkpoint_rows if row["success"] is False])
    return run_dir


def _memory_evolution_report_bucket_counts(checkpoint_rows: list[dict[str, object]]) -> dict[str, dict[str, int]]:
    failure_buckets = _bucket_counts(checkpoint_rows, field="failure_buckets")
    warning_buckets = _bucket_counts(checkpoint_rows, field="warning_buckets")
    return {
        "failure_bucket_counts": failure_buckets,
        "warning_bucket_counts": warning_buckets,
        "answer_failure_counts": _filtered_bucket_counts(
            failure_buckets,
            {
                "answer_mismatch",
                "next_action_mismatch",
                "selected_memory_mismatch",
                "expected_retrieval_missing",
            },
        ),
        "temporal_frame_failure_counts": _filtered_bucket_counts(
            failure_buckets,
            {bucket for bucket in failure_buckets if bucket.startswith("temporal_")},
        ),
        "temporal_frame_warning_counts": _filtered_bucket_counts(
            warning_buckets,
            {bucket for bucket in warning_buckets if bucket.startswith("temporal_")},
        ),
        "scope_canonicalization_failure_counts": _filtered_bucket_counts(
            failure_buckets,
            {"temporal_scope_mismatch", "temporal_scope_key_mismatch"},
        ),
        "belief_lifecycle_failure_counts": _filtered_bucket_counts(
            failure_buckets,
            {bucket for bucket in failure_buckets if bucket.startswith("belief_")},
        ),
        "lifecycle_snapshot_failure_counts": _filtered_bucket_counts(
            failure_buckets,
            {
                bucket
                for bucket in failure_buckets
                if "checkpoint_" in bucket
                or "lifecycle" in bucket
                or bucket in {
                    "superseded_record_marked_checkpoint_active",
                    "historical_answer_record_marked_checkpoint_active",
                }
            },
        ),
        "channel_hygiene_failure_counts": _filtered_bucket_counts(
            failure_buckets,
            {
                "citation_channel_pollution",
                "belief_id_used_as_citation",
                "excluded_memory_selected",
                "selected_memory_rejected",
                "command_event_selected_as_active_state",
                "expected_excluded_memory_channel_missing",
            },
        ),
    }


def _lifecycle_expectation_scope_counts(checkpoint_rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in checkpoint_rows:
        diagnostics = row.get("diagnostics", {})
        if not isinstance(diagnostics, dict):
            continue
        scope = diagnostics.get("lifecycle_expectation_scope")
        if isinstance(scope, str):
            counts[scope] = counts.get(scope, 0) + 1
    return dict(sorted(counts.items()))


def _bucket_counts(checkpoint_rows: list[dict[str, object]], *, field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in checkpoint_rows:
        buckets = row.get(field, [])
        if not isinstance(buckets, list):
            continue
        for bucket in buckets:
            if isinstance(bucket, str):
                counts[bucket] = counts.get(bucket, 0) + 1
    return dict(sorted(counts.items()))


def _filtered_bucket_counts(bucket_counts: dict[str, int], allowed_buckets: set[str]) -> dict[str, int]:
    return {
        bucket: count
        for bucket, count in bucket_counts.items()
        if bucket in allowed_buckets
    }


def _print_memory_evolution_summary(
    *,
    suite: str,
    mode: str,
    run_dir: Path,
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: list[dict[str, object]],
    llm_rows: Sequence[CuratedMemoryEvolutionLLMTraceRow],
) -> None:
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    print(
        f"suite={suite} mode={mode} systems=memorii "
        f"scenarios={len(scenario_rows)} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} "
        f"llm_calls={sum(len(row.provider_attempts) for row in llm_rows)} artifacts={run_dir}"
    )

def _run_memory_evolution_suite(
    args: argparse.Namespace,
    *,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> int:
    scenarios, fixture_source = _load_memory_evolution_suite(SUITE_NAME)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        scenario_rows, checkpoint_rows, llm_rows = _run_memory_evolution_transitions(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
            dependencies=dependencies,
        )
        run_dir = _write_memory_evolution_artifacts(
            scenarios=scenarios,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            llm_rows=llm_rows,
            suite=SUITE_NAME,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
        )
        _print_memory_evolution_summary(
            suite=SUITE_NAME,
            mode=mode,
            run_dir=run_dir,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            llm_rows=llm_rows,
        )
    return 0



def run(args: argparse.Namespace, prompt_root: Path, *, dependencies: BenchmarkRuntimeDependencies) -> int:
    require_memorii_only(args, SUITE_NAME)
    return _run_memory_evolution_suite(args, prompt_root=prompt_root, dependencies=dependencies)


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FunctionBenchmarkSuiteRunner(
        SUITE_NAME,
        lambda args, prompt_root: run(args, prompt_root, dependencies=dependencies),
        ALL_DECISION_MODES,
    )
