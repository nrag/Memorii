"""Output helpers for benchmark reports."""

from __future__ import annotations

import json

from memorii.core.benchmark.models import BenchmarkRunReport


def to_json(report: BenchmarkRunReport) -> str:
    return report.model_dump_json(indent=2)


def to_markdown(report: BenchmarkRunReport) -> str:
    lines = ["# Memorii Benchmark Report", "", f"Run ID: `{report.run_id}`", "", "## Aggregate Metrics (By System)"]
    for system, metrics in sorted(report.aggregate_by_system.items(), key=lambda item: item[0].value):
        lines.append(f"### {system.value}")
        metric_map = metrics.model_dump(exclude_none=True)
        if not metric_map:
            lines.append("- (no metrics)")
            continue
        for name, value in sorted(metric_map.items()):
            lines.append(f"- {name}: {value:.4f}")
        lines.append("")
    lines.extend(["## Aggregate Metrics (By Category)", ""])
    for category, system_metrics in sorted(report.aggregate_by_category.items(), key=lambda item: item[0].value):
        lines.append(f"### {category.value}")
        for system, metrics in sorted(system_metrics.items(), key=lambda item: item[0].value):
            lines.append(f"- {system.value}")
            metric_map = metrics.model_dump(exclude_none=True)
            if not metric_map:
                lines.append("  - (no metrics)")
                continue
            for name, value in sorted(metric_map.items()):
                lines.append(f"  - {name}: {value:.4f}")
        lines.append("")
    lines.extend(["## Per-Scenario Results", ""])
    for result in sorted(report.scenario_results, key=lambda item: (item.scenario_id, item.system.value)):
        lines.append(f"- `{result.scenario_id}` ({result.category.value}, {result.system.value})")
        metric_map = result.metrics.model_dump(exclude_none=True)
        if not metric_map:
            lines.append("  - metrics: none")
            continue
        lines.append(f"  - metrics: {metric_map}")
    return "\n".join(lines)


def write_json(report: BenchmarkRunReport, path: str) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write(to_json(report))


def write_markdown(report: BenchmarkRunReport, path: str) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write(to_markdown(report))


def baseline_summary(report: BenchmarkRunReport) -> str:
    return json.dumps(
        {
            scenario_id: [
                {
                    "baseline": delta.baseline.value,
                    "metric_deltas": delta.metric_deltas,
                    "skipped": delta.skipped,
                    "skip_reason": delta.skip_reason,
                }
                for delta in deltas
            ]
            for scenario_id, deltas in report.baseline_comparison.items()
        },
        indent=2,
        sort_keys=True,
    )
