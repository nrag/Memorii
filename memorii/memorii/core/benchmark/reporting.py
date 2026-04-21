"""Output helpers for benchmark reports."""

from __future__ import annotations

import json
import platform
import subprocess
from collections import defaultdict
from pathlib import Path

from memorii.core.benchmark.baselines import BASELINE_SYSTEMS, all_systems
from memorii.core.benchmark.models import (
    BenchmarkRunReport,
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    BenchmarkSystem,
    CanonicalBaselineEntry,
    CanonicalBenchmarkCategoryEntry,
    CanonicalBenchmarkConfig,
    CanonicalBenchmarkReport,
    CanonicalBenchmarkSummary,
    CanonicalScenarioEntry,
    CanonicalScenarioTrace,
    ScenarioMetrics,
)
from memorii.core.benchmark.validation import validate_canonical_report


def to_canonical_report(
    report: BenchmarkRunReport,
    *,
    fixtures: list[BenchmarkScenarioFixture] | None = None,
    dataset: str | None = None,
    fixture_source: str | None = None,
    subset_size: int | None = None,
) -> CanonicalBenchmarkReport:
    fixture_by_id = {fixture.scenario_id: fixture for fixture in fixtures or []}
    scenarios: list[CanonicalScenarioEntry] = []
    errors: list[str] = []
    for result in sorted(report.scenario_results, key=lambda item: (item.scenario_id, item.system.value)):
        fixture = fixture_by_id.get(result.scenario_id)
        expected = _build_expected_payload(result.scenario_id, fixture=fixture, observed=result.observation.model_dump(mode="python"))
        observed = _build_observed_payload(result.observation.model_dump(mode="python"))
        trace = _build_trace_payload(result.observation.model_dump(mode="python"))
        passed = bool(result.metrics.scenario_success_rate == 1.0)
        scenarios.append(
            CanonicalScenarioEntry(
                scenario_id=result.scenario_id,
                category=result.category,
                system=result.system,
                execution_type=result.observation.execution_level,
                passed=passed,
                metrics=result.metrics.model_dump(mode="python"),
                expected=expected,
                observed=observed,
                trace=trace,
                error=None,
                notes=[],
            )
        )

    aggregate_metrics = {
        system.value: metrics.model_dump(mode="python")
        for system, metrics in sorted(report.aggregate_by_system.items(), key=lambda item: item[0].value)
    }
    baseline_summary = _compute_baseline_summary(report)
    summary = CanonicalBenchmarkSummary(
        total_scenarios=len(scenarios),
        passed=sum(1 for scenario in scenarios if scenario.passed),
        failed=sum(1 for scenario in scenarios if not scenario.passed),
        aggregate_metrics=aggregate_metrics,
        baseline_comparison_summary=baseline_summary,
    )

    category_entries = _build_category_entries(report)
    baselines = _build_baseline_entries(report)
    metadata = _build_metadata(report)
    config = CanonicalBenchmarkConfig(
        dataset=dataset,
        fixture_source=fixture_source,
        subset_size=subset_size,
        seed=report.config.seed,
        benchmark_categories=sorted({item.category for item in report.scenario_results}, key=lambda item: item.value),
        systems=list(all_systems()),
    )
    canonical = CanonicalBenchmarkReport(
        metadata=metadata,
        config=config,
        summary=summary,
        categories=category_entries,
        scenarios=scenarios,
        baselines=baselines,
        errors=errors,
    )
    validate_canonical_report(canonical)
    return canonical


def to_json(report: BenchmarkRunReport, *, fixtures: list[BenchmarkScenarioFixture] | None = None) -> str:
    canonical = to_canonical_report(report, fixtures=fixtures)
    return canonical.model_dump_json(indent=2)


def to_markdown(report: BenchmarkRunReport, *, fixtures: list[BenchmarkScenarioFixture] | None = None) -> str:
    canonical = to_canonical_report(report, fixtures=fixtures)
    lines = ["# Memorii Benchmark Report", "", f"Run ID: `{canonical.metadata.run_id}`", ""]
    lines.append("## Summary")
    lines.append(f"- Total scenarios: {canonical.summary.total_scenarios}")
    lines.append(f"- Passed: {canonical.summary.passed}")
    lines.append(f"- Failed: {canonical.summary.failed}")
    lines.append("")
    lines.append("## Aggregate Metrics (By System)")
    for system_name, metric_map in sorted(canonical.summary.aggregate_metrics.items()):
        lines.append(f"### {system_name}")
        non_null = {name: value for name, value in metric_map.items() if value is not None}
        if not non_null:
            lines.append("- (no metrics)")
        else:
            for metric_name, value in sorted(non_null.items()):
                lines.append(f"- {metric_name}: {value:.4f}")
        lines.append("")

    lines.append("## Baseline Summary")
    for baseline_name, deltas in sorted(canonical.summary.baseline_comparison_summary.items()):
        lines.append(f"- {baseline_name}: {deltas}")
    lines.append("")

    lines.append("## Categories")
    for entry in canonical.categories:
        lines.append(f"### {entry.category.value} ({entry.scenario_count})")
        lines.append(f"- Metrics systems: {', '.join(sorted(entry.metrics.keys())) or 'none'}")
        lines.append(f"- Baseline delta systems: {', '.join(sorted(entry.baseline_delta.keys())) or 'none'}")
    lines.append("")

    lines.append("## Scenarios")
    for scenario in canonical.scenarios:
        lines.append(
            f"- `{scenario.scenario_id}` ({scenario.category.value}, {scenario.system.value}, {scenario.execution_type.value}) "
            f"passed={scenario.passed}"
        )
    return "\n".join(lines)


def write_json(report: BenchmarkRunReport, path: str, *, fixtures: list[BenchmarkScenarioFixture] | None = None) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write(to_json(report, fixtures=fixtures))


def write_markdown(report: BenchmarkRunReport, path: str, *, fixtures: list[BenchmarkScenarioFixture] | None = None) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write(to_markdown(report, fixtures=fixtures))


def baseline_summary(report: BenchmarkRunReport) -> str:
    canonical = to_canonical_report(report)
    return json.dumps(canonical.summary.baseline_comparison_summary, indent=2, sort_keys=True)


def write_artifacts(
    report: BenchmarkRunReport,
    *,
    fixtures: list[BenchmarkScenarioFixture] | None = None,
    dataset: str | None = None,
    fixture_source: str | None = None,
    subset_size: int | None = None,
    root_dir: str = "artifacts/benchmarks",
    include_markdown: bool = True,
    include_baseline: bool = True,
    include_fixtures: bool = True,
) -> Path:
    canonical = to_canonical_report(
        report,
        fixtures=fixtures,
        dataset=dataset,
        fixture_source=fixture_source,
        subset_size=subset_size,
    )
    run_dir = Path(root_dir) / canonical.metadata.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(canonical.model_dump_json(indent=2), encoding="utf-8")
    if include_markdown:
        markdown = to_markdown(report, fixtures=fixtures)
        (run_dir / "report.md").write_text(markdown, encoding="utf-8")
    if include_baseline:
        (run_dir / "baseline.json").write_text(
            json.dumps(canonical.summary.baseline_comparison_summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if include_fixtures and fixtures is not None:
        fixtures_payload = [fixture.model_dump(mode="json") for fixture in sorted(fixtures, key=lambda item: item.scenario_id)]
        (run_dir / "fixtures.json").write_text(json.dumps(fixtures_payload, indent=2), encoding="utf-8")
    return run_dir


def _build_expected_payload(
    scenario_id: str,
    *,
    fixture: BenchmarkScenarioFixture | None,
    observed: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {"scenario_id": scenario_id}
    if fixture is not None:
        payload["fixture"] = fixture.model_dump(mode="python", exclude_none=True)
    payload["relevant_ids"] = observed.get("relevant_ids", [])
    payload["excluded_ids"] = observed.get("excluded_ids", [])
    payload["expected_routed_domains"] = observed.get("expected_routed_domains", [])
    payload["expected_blocked_domains"] = observed.get("expected_blocked_domains", [])
    payload["expected_writeback_candidate_domains"] = observed.get("expected_writeback_candidate_domains", [])
    payload["expected_writeback_candidate_ids"] = observed.get("expected_writeback_candidate_ids", [])
    return payload


def _build_observed_payload(observed: dict[str, object]) -> dict[str, object]:
    return {
        "retrieved_ids": observed.get("retrieved_ids", []),
        "retrieval_latency_ms": observed.get("retrieval_latency_ms"),
        "routed_domains": observed.get("routed_domains", []),
        "blocked_domains": observed.get("blocked_domains", []),
        "writeback_candidate_domains": observed.get("writeback_candidate_domains", []),
        "writeback_candidate_ids": observed.get("writeback_candidate_ids", []),
        "scenario_success": observed.get("scenario_success"),
        "raw_observation": observed,
    }


def _build_trace_payload(observed: dict[str, object]) -> CanonicalScenarioTrace:
    return CanonicalScenarioTrace(
        routing_result={
            "routed_domains": observed.get("routed_domains", []),
            "blocked_domains": observed.get("blocked_domains", []),
        }
        if observed.get("routed_domains") or observed.get("blocked_domains")
        else None,
        retrieval_plan=None,
        retrieved_ids=list(observed.get("retrieved_ids", [])),
        solver_decision={
            "downgraded": observed.get("downgraded"),
            "abstention_preserved": observed.get("abstention_preserved"),
        }
        if observed.get("downgraded") is not None or observed.get("abstention_preserved") is not None
        else None,
        verifier_result={"invalid_output_rejected": observed.get("invalid_output_rejected")}
        if observed.get("invalid_output_rejected") is not None
        else None,
        writeback_candidates={
            "domains": observed.get("writeback_candidate_domains", []),
            "ids": observed.get("writeback_candidate_ids", []),
        }
        if observed.get("writeback_candidate_domains") or observed.get("writeback_candidate_ids")
        else None,
    )


def _build_category_entries(report: BenchmarkRunReport) -> list[CanonicalBenchmarkCategoryEntry]:
    category_counts: dict[BenchmarkScenarioType, int] = defaultdict(int)
    for result in report.scenario_results:
        category_counts[result.category] += 1

    category_deltas: dict[BenchmarkScenarioType, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for result in report.scenario_results:
        if result.system != BenchmarkSystem.MEMORII:
            continue
        for delta in report.baseline_comparison.get(result.scenario_id, []):
            for metric_name, delta_value in delta.metric_deltas.items():
                category_deltas[result.category][f"{delta.baseline.value}:{metric_name}"].append(delta_value)

    entries: list[CanonicalBenchmarkCategoryEntry] = []
    for category, per_system in sorted(report.aggregate_by_category.items(), key=lambda item: item[0].value):
        baseline_delta_map: dict[str, dict[str, float | None]] = {}
        for baseline_system in BASELINE_SYSTEMS:
            metric_map: dict[str, float | None] = {}
            for key, values in category_deltas[category].items():
                baseline_key, metric_name = key.split(":", maxsplit=1)
                if baseline_key != baseline_system.value:
                    continue
                metric_map[metric_name] = (sum(values) / len(values)) if values else None
            baseline_delta_map[baseline_system.value] = metric_map
        entries.append(
            CanonicalBenchmarkCategoryEntry(
                category=category,
                scenario_count=category_counts.get(category, 0),
                metrics={system.value: metrics.model_dump(mode="python") for system, metrics in per_system.items()},
                baseline_delta=baseline_delta_map,
            )
        )
    return entries


def _build_baseline_entries(report: BenchmarkRunReport) -> dict[BenchmarkSystem, CanonicalBaselineEntry]:
    output: dict[BenchmarkSystem, CanonicalBaselineEntry] = {}
    memorii_aggregate = report.aggregate_by_system.get(BenchmarkSystem.MEMORII, ScenarioMetrics())
    memorii_map = memorii_aggregate.model_dump(mode="python")
    for baseline in BASELINE_SYSTEMS:
        baseline_metrics = report.aggregate_by_system.get(baseline, ScenarioMetrics()).model_dump(mode="python")
        deltas: dict[str, float | None] = {}
        for metric_name, memorii_value in memorii_map.items():
            baseline_value = baseline_metrics.get(metric_name)
            if memorii_value is None or baseline_value is None:
                continue
            deltas[metric_name] = float(memorii_value - baseline_value)
        output[baseline] = CanonicalBaselineEntry(
            aggregate_metrics=baseline_metrics,
            deltas_vs_memorii=deltas,
        )
    return output


def _compute_baseline_summary(report: BenchmarkRunReport) -> dict[str, dict[str, float | None]]:
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for deltas in report.baseline_comparison.values():
        for delta in deltas:
            if delta.skipped:
                continue
            for metric_name, metric_value in delta.metric_deltas.items():
                buckets[delta.baseline.value][metric_name].append(metric_value)

    summary: dict[str, dict[str, float | None]] = {}
    for baseline, metric_buckets in buckets.items():
        summary[baseline] = {
            metric_name: (sum(values) / len(values) if values else None)
            for metric_name, values in metric_buckets.items()
        }
    for baseline in BASELINE_SYSTEMS:
        summary.setdefault(baseline.value, {})
    return summary


def _build_metadata(report: BenchmarkRunReport) -> dict[str, object]:
    return {
        "run_id": report.run_id,
        "timestamp": report.generated_at,
        "git_commit": _read_git_commit(),
        "memorii_version": _read_memorii_version(),
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "architecture": platform.machine() or None,
        },
    }


def _read_git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    commit = completed.stdout.strip()
    return commit or None


def _read_memorii_version() -> str | None:
    path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            parts = line.split("=", maxsplit=1)
            if len(parts) != 2:
                continue
            return parts[1].strip().strip('"').strip("'")
    return None
