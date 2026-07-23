"""Factory helpers for runtime memory evolution extractors."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import ResolvedLLMDecisionConfig
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution.extraction import (
    EnglishRuleMemoryExtractor,
    HybridMemoryExtractor,
    LLMMemoryExtractor,
)
from memorii.core.memory_evolution.extraction_contracts import MemoryExtractor


def build_memory_extractor_from_env(
    *,
    env: Mapping[str, str] | None = None,
    prompt_root: Path | None = None,
) -> MemoryExtractor:
    snapshot = load_memorii_environment(env=env)
    return build_memory_extractor(
        config=ResolvedLLMDecisionConfig.from_env(snapshot.env),
        prompt_root=prompt_root,
    )


def build_memory_extractor(
    *,
    config: ResolvedLLMDecisionConfig,
    prompt_root: Path | None = None,
) -> MemoryExtractor:
    """Build an extractor from an already resolved application configuration."""

    if config.mode == "rule":
        return EnglishRuleMemoryExtractor()
    if not config.runtime.has_live_provider():
        return EnglishRuleMemoryExtractor()

    runner = PromptLLMRunner(
        client=LLMClientFactory.from_config(config.runtime),
        config=config.runtime,
    )
    llm_extractor = LLMMemoryExtractor(runner=runner, prompt_root=prompt_root)
    if config.mode == "llm":
        return llm_extractor
    if config.mode == "hybrid":
        return HybridMemoryExtractor(llm_extractor=llm_extractor)
    raise ValueError(f"Unsupported memory extraction mode: {config.mode}")
