"""Baseline benchmark systems used for comparative evaluation."""

from memorii.core.benchmark.models import BenchmarkSystem


BASELINE_SYSTEMS: tuple[BenchmarkSystem, ...] = (
    BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE,
    BenchmarkSystem.FLAT_RETRIEVAL_BASELINE,
    BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE,
)


def all_systems() -> tuple[BenchmarkSystem, ...]:
    return (BenchmarkSystem.MEMORII, *BASELINE_SYSTEMS)
