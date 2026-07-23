"""Runtime-backed memory evolution benchmark suite runner."""

from __future__ import annotations

import argparse
from pathlib import Path

from memorii.core.benchmark.artifact_validation import (
    finalize_memory_evolution_run,
    validate_memory_evolution_run,
)
from memorii.core.benchmark.memory_evolution_runtime import (
    run_runtime_scenarios,
    runtime_summary_metrics,
    runtime_warning_policy,
    write_runtime_artifacts,
)
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES, require_memorii_only
from memorii.tools.benchmark_suites.memory_evolution_artifacts import (
    print_memory_evolution_summary,
    write_memory_evolution_artifacts,
)
from memorii.tools.benchmark_suites.memory_evolution_scenarios import (
    load_memory_evolution_scenarios,
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
            live_client_factory=dependencies.create_live_client,
        )
        summary = runtime_summary_metrics(runtime_rows)
        provider_health = summary.runtime_provider_health
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
            runtime_report=summary,
            warning_policy=runtime_warning_policy(),
        )
        write_runtime_artifacts(run_dir=run_dir, rows=runtime_rows)
        finalize_memory_evolution_run(run_dir)
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
        if not args.defer_live_gate and not provider_health.clean_runtime_gate:
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
