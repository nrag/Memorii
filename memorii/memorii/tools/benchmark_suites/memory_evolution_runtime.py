"""Runtime-backed memory evolution benchmark suite runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memorii.core.benchmark.artifact_rows import BenchmarkReportSummary
from memorii.core.benchmark.memory_evolution_runtime import (
    run_runtime_scenarios,
    runtime_summary_metrics,
    runtime_warning_policy,
    write_runtime_artifacts,
)
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES, require_memorii_only
from memorii.tools.benchmark_suites.memory_evolution_sim import (
    _load_memory_evolution_sim_suite,
    _print_memory_evolution_sim_summary,
    _write_memory_evolution_sim_artifacts,
)
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies

SUITE_NAME = "memory_evolution_runtime_v1"


def _run_memory_evolution_runtime_suite(
    args: argparse.Namespace,
    *,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> int:
    scenarios, fixture_source = _load_memory_evolution_sim_suite(args)
    modes = ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
    for mode in modes:
        runtime_rows = run_runtime_scenarios(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
            llm_client_factory=dependencies.llm_client_factory,
        )
        run_dir = _write_memory_evolution_sim_artifacts(
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
        )
        write_runtime_artifacts(run_dir=run_dir, rows=runtime_rows)
        summary = runtime_summary_metrics(runtime_rows)
        report_path = run_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report.setdefault("runtime", {}).update(summary)
        if isinstance(summary.get("runtime_graph_summary"), dict):
            report["runtime_graph_summary"] = summary["runtime_graph_summary"]
        if isinstance(summary.get("runtime_graph_alignments_summary"), dict):
            report["runtime_graph_alignments_summary"] = summary["runtime_graph_alignments_summary"]
        if isinstance(summary.get("runtime_failure_bucket_counts"), dict):
            report["runtime_failure_bucket_counts"] = summary["runtime_failure_bucket_counts"]
        report["warning_policy"] = runtime_warning_policy()
        metrics = report.get("metrics", {}) if isinstance(report.get("metrics"), dict) else {}
        for key in ("hidden_item_count", "hidden_hallucination_rate", "hidden_answer_leak_rate"):
            if key in metrics:
                report[key] = metrics[key]
        scalar_summary = {key: value for key, value in summary.items() if not isinstance(value, dict)}
        report["metrics"] = {**report.get("metrics", {}), **scalar_summary}
        report = BenchmarkReportSummary.from_flat_row(report).to_json_row()
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        _print_memory_evolution_sim_summary(
            suite=SUITE_NAME,
            mode=mode,
            profile=args.sim_profile,
            run_dir=run_dir,
            scenarios=scenarios,
            scenario_rows=runtime_rows.scenario_rows,
            checkpoint_rows=runtime_rows.checkpoint_rows,
            llm_rows=runtime_rows.llm_rows,
        )
    return 0



def run(args: argparse.Namespace, prompt_root: Path, *, dependencies: BenchmarkRuntimeDependencies) -> int:
    require_memorii_only(args, SUITE_NAME)
    return _run_memory_evolution_runtime_suite(args, prompt_root=prompt_root, dependencies=dependencies)


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FunctionBenchmarkSuiteRunner(
        SUITE_NAME,
        lambda args, prompt_root: run(args, prompt_root, dependencies=dependencies),
        ALL_DECISION_MODES,
    )
