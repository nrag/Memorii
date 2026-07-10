"""Legacy fixture-backed HotpotQA benchmark runner."""

from __future__ import annotations

from memorii.tools.benchmark_registry import BenchmarkSuiteRunner
from memorii.tools.benchmark_suites.common import DETERMINISTIC_BENCHMARK_MODES
from memorii.tools.benchmark_suites.fixture_harness import FixtureBackedBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.fixture_loaders import load_hotpotqa_v1_fixture_set
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies

SUITE_NAME = "hotpotqa_v1"


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FixtureBackedBenchmarkSuiteRunner(
        suite_name=SUITE_NAME,
        loader=load_hotpotqa_v1_fixture_set,
        supported_modes=DETERMINISTIC_BENCHMARK_MODES,
        dependencies=dependencies,
        all_mode_expands_to_rule_only=True,
        unsupported_mode_message_template="hotpotqa_v1 currently supports deterministic modes only: auto, rule, or all",
    )
