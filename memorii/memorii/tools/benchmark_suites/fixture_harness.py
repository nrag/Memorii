"""Shared harness for fixture-backed benchmark suites."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.metrics import aggregate_metrics, compute_metrics
from memorii.core.benchmark.models import (
    BenchmarkRunConfig,
    BenchmarkRunReport,
    BenchmarkScenarioFixture,
    BenchmarkSystem,
    ScenarioResult,
)
from memorii.core.benchmark.reporting import write_artifacts
from memorii.core.benchmark.reproducibility import apply_seed, build_run_id
from memorii.core.benchmark.scenarios import ScenarioExecutor
from memorii.core.benchmark.validation import validate_preflight, validate_report
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner
from memorii.tools.benchmark_suites.artifact_io import _write_jsonl
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies

FixtureLoader = Callable[[argparse.Namespace], tuple[list[BenchmarkScenarioFixture], str, dict[str, object] | None]]
TraceRunner = Callable[
    [list[BenchmarkScenarioFixture], str, bool, bool, Path, BenchmarkRuntimeDependencies],
    tuple[list[dict[str, object]], list[dict[str, object]]],
]
ReportMutator = Callable[[BenchmarkRunReport, list[dict[str, object]]], BenchmarkRunReport]


def aggregate_by_system(results: list[ScenarioResult]) -> dict[BenchmarkSystem, object]:
    grouped: dict[BenchmarkSystem, list[object]] = {}
    for result in results:
        grouped.setdefault(result.system, []).append(result.observation)
    return {system: aggregate_metrics(observations) for system, observations in grouped.items()}


def aggregate_by_category(results: list[ScenarioResult]) -> dict[object, dict[BenchmarkSystem, object]]:
    grouped: dict[object, dict[BenchmarkSystem, list[object]]] = {}
    for result in results:
        grouped.setdefault(result.category, {})
        grouped[result.category].setdefault(result.system, []).append(result.observation)
    return {
        category: {
            system: aggregate_metrics(observations)
            for system, observations in by_system.items()
        }
        for category, by_system in grouped.items()
    }


def run_memorii_only(
    *,
    fixtures: list[BenchmarkScenarioFixture],
    config: BenchmarkRunConfig,
) -> BenchmarkRunReport:
    apply_seed(config.seed)
    normalized = normalize_fixtures(fixtures)
    validate_preflight(fixtures=normalized, config=config)
    executor = ScenarioExecutor()

    results: list[ScenarioResult] = []
    for fixture in normalized:
        observation = executor.run(fixture=fixture, system=BenchmarkSystem.MEMORII)
        results.append(
            ScenarioResult(
                scenario_id=fixture.scenario_id,
                category=fixture.category,
                system=BenchmarkSystem.MEMORII,
                observation=observation,
                metrics=compute_metrics(observation),
            )
        )

    report = BenchmarkRunReport(
        run_id=build_run_id(config=config, fixtures=normalized),
        generated_at=datetime.now(UTC),
        config=config,
        scenario_results=results,
        aggregate_by_system=aggregate_by_system(results),
        aggregate_by_category=aggregate_by_category(results),
        baseline_comparison={},
    )
    validate_report(report)
    return report


def print_fixture_summary(
    *,
    suite: str,
    systems: str,
    mode: str,
    report: BenchmarkRunReport,
    run_dir: Path,
    llm_call_count: int,
) -> None:
    memorii_results = [result for result in report.scenario_results if result.system == BenchmarkSystem.MEMORII]
    scenario_count = len({result.scenario_id for result in report.scenario_results})
    passed = sum(1 for result in memorii_results if result.observation.scenario_success is True)
    failed = sum(1 for result in memorii_results if result.observation.scenario_success is False)
    baseline_results = [result for result in report.scenario_results if result.system != BenchmarkSystem.MEMORII]
    baseline_passed = sum(1 for result in baseline_results if result.observation.scenario_success is True)
    baseline_failed = sum(1 for result in baseline_results if result.observation.scenario_success is False)
    lifecycle_results = [
        result for result in memorii_results if result.observation.lifecycle_success is not None
    ]
    lifecycle_passed = sum(1 for result in lifecycle_results if result.observation.lifecycle_success is True)
    lifecycle_failed = sum(1 for result in lifecycle_results if result.observation.lifecycle_success is False)
    baseline_summary = (
        f"baseline_runs={len(baseline_results)} "
        f"baseline_runs_passed={baseline_passed} baseline_runs_failed={baseline_failed} "
        if baseline_results
        else ""
    )

    print(
        f"suite={suite} mode={mode} systems={systems} "
        f"scenarios={scenario_count} "
        f"memorii_runs={len(memorii_results)} "
        f"memorii_runs_passed={passed} memorii_runs_failed={failed} "
        f"{baseline_summary}"
        f"lifecycle_cases={len(lifecycle_results)} "
        f"lifecycle_passed={lifecycle_passed} lifecycle_failed={lifecycle_failed} "
        f"llm_calls={llm_call_count} "
        f"artifacts={run_dir}"
    )


@dataclass(frozen=True)
class FixtureBackedBenchmarkSuiteRunner:
    """Runner for fixture-backed suites with suite-owned trace hooks."""

    suite_name: str
    loader: FixtureLoader
    supported_modes: frozenset[str]
    dependencies: BenchmarkRuntimeDependencies
    trace_runner: TraceRunner | None = None
    report_mutator: ReportMutator | None = None
    trace_artifact_name: str | None = None
    supports_all_systems: bool = True
    all_mode_expands_to_rule_only: bool = False
    unsupported_mode_message_template: str | None = None

    def supports_mode(self, mode: str) -> bool:
        return mode in self.supported_modes

    def unsupported_mode_message(self, mode: str) -> str:
        if self.unsupported_mode_message_template is not None:
            return self.unsupported_mode_message_template.format(suite=self.suite_name, mode=mode)
        return f"{self.suite_name} does not support mode {mode}"

    def run(self, args: argparse.Namespace, *, prompt_root: Path) -> int:
        if args.systems == "all" and not self.supports_all_systems:
            raise SystemExit(f"{self.suite_name} currently supports --systems memorii only")

        fixtures, fixture_source, metadata = self.loader(args)
        modes = ["rule"] if self.all_mode_expands_to_rule_only and args.mode == "all" else (
            ["rule", "llm", "hybrid"] if args.mode == "all" else [args.mode]
        )
        for mode in modes:
            run_label = args.run_label or f"{self.suite_name}_{mode}"
            config = BenchmarkRunConfig(seed=args.seed, run_label=run_label)

            if args.systems == "all":
                report = BenchmarkHarness().run(fixtures=fixtures, config=config)
            else:
                report = run_memorii_only(fixtures=fixtures, config=config)

            trace_rows: list[dict[str, object]] = []
            llm_rows: list[dict[str, object]] = []
            if self.trace_runner is not None:
                trace_rows, llm_rows = self.trace_runner(
                    fixtures,
                    mode,
                    args.dry_run,
                    args.allow_live,
                    prompt_root,
                    self.dependencies,
                )
                if self.report_mutator is not None:
                    report = self.report_mutator(report, trace_rows)

            root_dir = Path(args.storage_root) / "benchmark_runs" / self.suite_name / mode
            run_dir = write_artifacts(
                report,
                fixtures=normalize_fixtures(fixtures),
                dataset=self.suite_name,
                fixture_source=fixture_source,
                subset_size=len(fixtures),
                root_dir=str(root_dir),
            )
            if trace_rows and self.trace_artifact_name is not None:
                _write_jsonl(run_dir / self.trace_artifact_name, trace_rows)
            if metadata is not None:
                (run_dir / "hotpotqa_metadata.json").write_text(
                    json.dumps(metadata, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
            _write_jsonl(run_dir / "failures.jsonl", [row for row in trace_rows if row.get("success") is False])
            print_fixture_summary(
                suite=self.suite_name,
                systems=args.systems,
                mode=mode,
                report=report,
                run_dir=run_dir,
                llm_call_count=len(llm_rows),
            )
        return 0
