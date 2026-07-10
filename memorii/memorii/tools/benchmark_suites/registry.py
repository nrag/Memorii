"""Build the benchmark suite registry."""

from __future__ import annotations

from memorii.tools.benchmark_registry import BenchmarkSuiteRegistry
from memorii.tools.benchmark_suites import (
    execution_graph,
    hotpotqa_v1,
    hotpotqa_official,
    memory_evolution,
    memory_evolution_runtime,
    memory_evolution_sim,
    memory_lifecycle_fixture,
    minimal,
    retrieval_corruption,
)
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies


def build_benchmark_suite_registry(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRegistry:
    return BenchmarkSuiteRegistry(
        [
            memory_lifecycle_fixture.build_runner(dependencies=dependencies),
            execution_graph.build_runner(dependencies=dependencies),
            memory_evolution.build_runner(dependencies=dependencies),
            memory_evolution_sim.build_runner(dependencies=dependencies),
            memory_evolution_runtime.build_runner(dependencies=dependencies),
            retrieval_corruption.build_runner(dependencies=dependencies),
            hotpotqa_v1.build_runner(dependencies=dependencies),
            hotpotqa_official.build_runner(dependencies=dependencies),
            minimal.build_runner(dependencies=dependencies),
        ]
    )
