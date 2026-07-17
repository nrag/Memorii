"""Hand-authored memory evolution benchmark suite runner."""

from __future__ import annotations

import argparse
import json
from datetime import (
    UTC,
    datetime,
)
from pathlib import Path
from typing import cast

from memorii.core.benchmark.fixture_sets.memory_evolution_v1 import load_memory_evolution_v1_fixture_set
from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionScenario,
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
from memorii.core.llm_decision.adapters import LLMMemoryEvolutionDecisionAdapter
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.artifact_io import _write_jsonl
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES, require_memorii_only
from memorii.tools.benchmark_suites.fake_adapters import _ExpectedMemoryEvolutionFakeAdapter
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_live_llm_eval import _validate_live_safety

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
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=_decision_mode(mode))
        if mode != "auto"
        else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
    )
    effective_mode = decision_config.resolve(runtime_config)
    if effective_mode in {"llm", "hybrid"}:
        live_config = LLMLiveTestConfig.from_env(env_snapshot.env)
        _validate_live_safety(
            modes=[effective_mode],
            dry_run=dry_run,
            allow_live=allow_live,
            runtime_config=runtime_config,
            live_config=live_config,
        )

    registry = PromptRegistry(prompt_root=prompt_root)
    adapter = None
    if effective_mode in {"llm", "hybrid"}:
        client = dependencies.eval_fake_client_cls() if dry_run else dependencies.llm_client_factory.from_config(runtime_config)
        runner = PromptLLMRunner(client=client, config=runtime_config)
        adapter = (
            _ExpectedMemoryEvolutionFakeAdapter(scenarios=scenarios, registry=registry)
            if dry_run and dependencies.is_default_fake_client()
            else LLMMemoryEvolutionDecisionAdapter(runner=runner, registry=registry)
        )

    scenario_rows: list[dict[str, object]] = []
    checkpoint_rows: list[dict[str, object]] = []
    llm_rows: list[dict[str, object]] = []
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
                llm_result = adapter.decide(
                    context,
                    request_id=request_id,
                    metadata=metadata,
                )
                output, llm_trace, llm_success, fallback_reason = memory_evolution_engine_result_from_llm(
                    result=llm_result,
                    mode=LLMDecisionMode(effective_mode),
                    rule_output=rule_output,
                )
                final_output_source = "llm" if llm_success else "rule"
                llm_rows.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "transition_type": "memory_evolution_decision",
                        "decision_mode": mode,
                        "effective_decision_mode": effective_mode,
                        "trace": llm_trace.model_dump(mode="json"),
                        "success": llm_success,
                        "fallback_used": not llm_success,
                        "failure_mode": fallback_reason,
                        "output": output,
                    }
                )
            else:
                llm_trace = rule_trace

            diagnostics = memory_evolution_decision_diagnostics(
                scenario=scenario,
                checkpoint=checkpoint,
                decision=output,
            )
            assertion_passed = diagnostics.assertion_passed
            success = assertion_passed and (effective_mode != "llm" or llm_success or not llm_used)
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
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "discriminative": scenario.discriminative,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "checkpoint_count": len(scenario_checkpoint_rows),
                "success": scenario_success,
                "failure_mode": None if scenario_success else "one_or_more_checkpoints_failed",
                "checkpoints_passed": sum(1 for row in scenario_checkpoint_rows if row["success"] is True),
                "checkpoints_failed": sum(1 for row in scenario_checkpoint_rows if row["success"] is False),
            }
        )
    return scenario_rows, checkpoint_rows, llm_rows


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
    llm_rows: list[dict[str, object]],
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
        "artifact_version": "memory_evolution_v1_artifacts:2",
        "scenarios": len(scenario_rows),
        "checkpoints": len(checkpoint_rows),
        "passed": passed,
        "failed": failed,
        "llm_calls": len(llm_rows),
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
        f"passed={passed} failed={failed} llm_calls={len(llm_rows)}\n"
    )
    (run_dir / "report.json").write_text(report_json, encoding="utf-8")
    (run_dir / "memory_evolution_report.json").write_text(report_json, encoding="utf-8")
    (run_dir / "report.md").write_text(report_md, encoding="utf-8")
    (run_dir / "memory_evolution_report.md").write_text(report_md, encoding="utf-8")
    (run_dir / "fixtures.json").write_text(
        json.dumps([scenario.model_dump(mode="json") for scenario in scenarios], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(run_dir / "memory_evolution_traces.jsonl", scenario_rows)
    _write_jsonl(run_dir / "memory_evolution_checkpoint_traces.jsonl", checkpoint_rows)
    _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
    _write_jsonl(run_dir / "failures.jsonl", [row for row in checkpoint_rows if row["success"] is False])
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
    llm_rows: list[dict[str, object]],
) -> None:
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    print(
        f"suite={suite} mode={mode} systems=memorii "
        f"scenarios={len(scenario_rows)} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} "
        f"llm_calls={len(llm_rows)} artifacts={run_dir}"
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
