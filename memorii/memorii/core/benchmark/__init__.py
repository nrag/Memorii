"""Benchmarking and evaluation infrastructure for Memorii."""

from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.hotpotqa import (
    HotpotQABenchmarkSelection,
    build_hotpotqa_benchmark_fixtures,
    run_hotpotqa_benchmark,
)
from memorii.core.benchmark.hotpotqa_official import evaluate_hotpotqa_predictions
from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkRunReport, BenchmarkScenarioFixture
from memorii.core.benchmark.reporting import to_canonical_report, write_artifacts

__all__ = [
    "BenchmarkHarness",
    "BenchmarkRunConfig",
    "BenchmarkRunReport",
    "BenchmarkScenarioFixture",
    "HotpotQABenchmarkSelection",
    "build_hotpotqa_benchmark_fixtures",
    "evaluate_hotpotqa_predictions",
    "run_hotpotqa_benchmark",
    "to_canonical_report",
    "write_artifacts",
]
