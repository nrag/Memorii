"""Decision-mode resolution for benchmark execution backends."""

from __future__ import annotations

from memorii.core.llm_config import (
    LLMDecisionRuntimeConfig,
    LLMRuntimeConfig,
    ResolvedDecisionModeName,
)


def resolve_benchmark_decision_mode(
    *,
    decision_config: LLMDecisionRuntimeConfig,
    runtime_config: LLMRuntimeConfig,
    dry_run: bool,
) -> ResolvedDecisionModeName:
    """Resolve a requested mode against the backend available to a benchmark run."""

    if dry_run and decision_config.mode == "hybrid":
        return "hybrid"
    return decision_config.resolve(runtime_config)
