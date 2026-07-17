"""Runtime-backed memory evolution benchmark suite runner."""

from __future__ import annotations

import argparse
from pathlib import Path

from memorii.core.benchmark.artifact_validation import validate_memory_evolution_run
from memorii.core.benchmark.memory_evolution_runtime import (
    run_runtime_scenarios,
    runtime_summary_metrics,
    runtime_warning_policy,
    write_runtime_artifacts,
)
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES, require_memorii_only
from memorii.tools.benchmark_suites.memory_evolution_sim import (
    load_memory_evolution_scenarios,
    print_memory_evolution_summary,
    write_memory_evolution_artifacts,
)
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies

SUITE_NAME = "memory_evolution_runtime_v1"


def _run_memory_evolution_runtime_suite(
    args: argparse.Namespace,
    *,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> int:
    scenarios, fixture_source = load_memory_evolution_scenarios(args)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    exit_code = 0
    for mode in modes:
        runtime_rows = run_runtime_scenarios(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
            llm_client_factory=dependencies.llm_client_factory,
        )
        summary = runtime_summary_metrics(runtime_rows)
        provider_health = summary["runtime_provider_health"]
        runtime_metric_scalars = {
            key: value for key, value in summary.items() if not isinstance(value, dict)
        }
        report_overrides = {
            "dry_run": runtime_rows.dry_run,
            "execution_source": provider_health.get("execution_source", "mixed")
            if isinstance(provider_health, dict)
            else "mixed",
            "provider_successes": summary.get("provider_successes", 0),
            "provider_failures": summary.get("provider_failures", 0),
            "fallbacks": summary.get("fallbacks", 0),
            "fake_calls": len(runtime_rows.llm_rows) if runtime_rows.dry_run else 0,
            "runtime": summary,
            "metrics": runtime_metric_scalars,
            "runtime_graph_summary": summary["runtime_graph_summary"],
            "runtime_graph_alignments_summary": summary["runtime_graph_alignments_summary"],
            "runtime_failure_bucket_counts": summary["runtime_failure_bucket_counts"],
            "runtime_provider_health": summary["runtime_provider_health"],
            "warning_policy": runtime_warning_policy(),
        }
        run_dir = write_memory_evolution_artifacts(
            scenarios=scenarios,
            scenario_rows=runtime_rows.scenario_rows,
            checkpoint_rows=runtime_rows.checkpoint_rows,
            judge_rows=runtime_rows.judge_rows,
            llm_rows=runtime_rows.llm_rows,
            suite=SUITE_NAME,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
            args=args,
            report_overrides=report_overrides,
        )
        write_runtime_artifacts(run_dir=run_dir, rows=runtime_rows)
        validate_memory_evolution_run(run_dir, suite=SUITE_NAME)
        print_memory_evolution_summary(
            suite=SUITE_NAME,
            mode=mode,
            profile=args.sim_profile,
            run_dir=run_dir,
            scenarios=scenarios,
            scenario_rows=runtime_rows.scenario_rows,
            checkpoint_rows=runtime_rows.checkpoint_rows,
            llm_rows=runtime_rows.llm_rows,
        )
        provider_health = summary.get("runtime_provider_health", {})
        if isinstance(provider_health, dict) and provider_health.get("clean_runtime_gate") is False:
            exit_code = 1
        if getattr(args, "fail_on_benchmark_failure", False) and any(
            not row.success for row in runtime_rows.checkpoint_rows
        ):
            exit_code = 1
    return exit_code



def run(args: argparse.Namespace, prompt_root: Path, *, dependencies: BenchmarkRuntimeDependencies) -> int:
    require_memorii_only(args, SUITE_NAME)
    return _run_memory_evolution_runtime_suite(args, prompt_root=prompt_root, dependencies=dependencies)


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FunctionBenchmarkSuiteRunner(
        SUITE_NAME,
        lambda args, prompt_root: run(args, prompt_root, dependencies=dependencies),
        ALL_DECISION_MODES,
    )
