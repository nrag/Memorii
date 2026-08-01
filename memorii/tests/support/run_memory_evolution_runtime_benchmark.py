"""Test-only CLI for deterministic M2 runtime benchmark evidence."""

from __future__ import annotations

import sys

from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_benchmark import BenchmarkApplication

from tests.support.memory_evolution_provider_harness import MemoryEvolutionProviderHarness


def main(argv: list[str] | None = None) -> int:
    dependencies = BenchmarkRuntimeDependencies(
        memory_evolution_provider_factory=MemoryEvolutionProviderHarness,
    )
    return BenchmarkApplication(dependencies=dependencies).run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
