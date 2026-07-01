"""Factory helpers for runtime memory evolution extractors."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import LLMDecisionRuntimeConfig, LLMRuntimeConfig
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution.extraction import HybridMemoryExtractor, LLMMemoryExtractor, MemoryExtractor, RuleMemoryExtractor


def build_memory_extractor_from_env(
    *,
    env: Mapping[str, str] | None = None,
    prompt_root: Path | None = None,
) -> MemoryExtractor:
    snapshot = load_memorii_environment(env=env)
    runtime_config = LLMRuntimeConfig.from_env(snapshot.env)
    decision_config = LLMDecisionRuntimeConfig.from_env(snapshot.env)
    mode = decision_config.resolve(runtime_config)
    if mode == "rule":
        return RuleMemoryExtractor()
    if not runtime_config.has_live_provider():
        return RuleMemoryExtractor()

    runner = PromptLLMRunner(
        client=LLMClientFactory.from_config(runtime_config),
        config=runtime_config,
    )
    llm_extractor = LLMMemoryExtractor(runner=runner, prompt_root=prompt_root)
    if mode == "llm":
        return llm_extractor
    if mode == "hybrid":
        return HybridMemoryExtractor(llm_extractor=llm_extractor)
    raise ValueError(f"Unsupported memory extraction mode: {mode}")

