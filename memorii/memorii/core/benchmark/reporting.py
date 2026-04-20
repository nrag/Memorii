"""Output helpers for benchmark reports."""

from __future__ import annotations

import json

from memorii.core.benchmark.models import BenchmarkRunReport


def to_json(report: BenchmarkRunReport) -> str:
    return report.model_dump_json(indent=2)


def to_markdown(report: BenchmarkRunReport) -> str:
    lines = ["# Memorii Benchmark Report", "", f"Run ID: `{report.run_id}`", "", "## Aggregate Metrics"]
    for system, metrics in sorted(report.aggregate_by_system.items(), key=lambda item: item[0].value):
        lines.append(f"### {system.value}")
        metric_map = metrics.model_dump(exclude_none=True)
        if not metric_map:
            lines.append("- (no metrics)")
            continue
        for name, value in sorted(metric_map.items()):
            lines.append(f"- {name}: {value:.4f}")
        lines.append("")
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
                {"baseline": delta.baseline.value, "metric_deltas": delta.metric_deltas}
                for delta in deltas
            ]
            for scenario_id, deltas in report.baseline_comparison.items()
        },
        indent=2,
        sort_keys=True,
    )
