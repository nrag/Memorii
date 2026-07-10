"""Minimal fixture-backed benchmark runner."""

from __future__ import annotations

from memorii.tools.benchmark_registry import BenchmarkSuiteRunner
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES
from memorii.tools.benchmark_suites.fixture_harness import FixtureBackedBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.fixture_loaders import load_minimal_fixture_set
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies

SUITE_NAME = "minimal"


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FixtureBackedBenchmarkSuiteRunner(
        suite_name=SUITE_NAME,
        loader=load_minimal_fixture_set,
        supported_modes=ALL_DECISION_MODES,
        dependencies=dependencies,
    )
