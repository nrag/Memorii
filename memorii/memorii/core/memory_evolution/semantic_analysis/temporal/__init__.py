"""Local-only temporal-analysis adapters."""

from memorii.core.memory_evolution.semantic_analysis.temporal.duckling_adapter import (
    DucklingRuntimeCoordinates,
    DucklingTemporalResolver,
    DucklingTemporalResolverUnavailable,
)

__all__ = [
    "DucklingRuntimeCoordinates",
    "DucklingTemporalResolver",
    "DucklingTemporalResolverUnavailable",
]
