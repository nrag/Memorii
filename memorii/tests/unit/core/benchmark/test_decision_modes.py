from __future__ import annotations

from memorii.core.benchmark.decision_modes import resolve_benchmark_decision_mode
from memorii.core.llm_config import LLMDecisionRuntimeConfig, LLMRuntimeConfig


def test_dry_run_hybrid_uses_benchmark_backend_without_live_credentials() -> None:
    mode = resolve_benchmark_decision_mode(
        decision_config=LLMDecisionRuntimeConfig(mode="hybrid"),
        runtime_config=LLMRuntimeConfig(provider="none"),
        dry_run=True,
    )

    assert mode == "hybrid"


def test_live_hybrid_without_provider_retains_runtime_fallback_policy() -> None:
    mode = resolve_benchmark_decision_mode(
        decision_config=LLMDecisionRuntimeConfig(mode="hybrid"),
        runtime_config=LLMRuntimeConfig(provider="none"),
        dry_run=False,
    )

    assert mode == "rule"


def test_explicit_llm_mode_is_unchanged_for_dry_runs() -> None:
    mode = resolve_benchmark_decision_mode(
        decision_config=LLMDecisionRuntimeConfig(mode="llm"),
        runtime_config=LLMRuntimeConfig(provider="none"),
        dry_run=True,
    )

    assert mode == "llm"
