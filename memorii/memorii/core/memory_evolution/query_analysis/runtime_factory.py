"""Explicit construction for prompt-backed production query analysis."""

from __future__ import annotations

from pathlib import Path

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.query_analysis.analyzers import StructuredQueryAnalyzer
from memorii.core.memory_evolution.query_analysis.provider import PromptBackedStructuredQueryAnalysisProvider
from memorii.core.memory_evolution.temporal_compilation import RelativeTemporalExpressionResolver
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root


def build_prompt_backed_query_analyzer(
    *,
    runtime_config: LLMRuntimeConfig,
    prompt_root: Path | None = None,
    predicate_registry: PredicateRegistry | None = None,
    relative_temporal_resolver: RelativeTemporalExpressionResolver | None = None,
) -> StructuredQueryAnalyzer:
    """Build the optional structured analyzer without changing service defaults."""

    if not runtime_config.has_live_provider():
        raise ValueError("prompt-backed query analysis requires a configured live provider")
    predicates = predicate_registry or PredicateRegistry()
    registry = PromptRegistry(prompt_root=prompt_root or default_prompt_root())
    runner = PromptLLMRunner(
        client=LLMClientFactory.from_config(runtime_config),
        config=runtime_config,
    )
    provider = PromptBackedStructuredQueryAnalysisProvider(
        runner=runner,
        registry=registry,
        predicate_registry=predicates,
    )
    return StructuredQueryAnalyzer(
        provider,
        analyzer_name="prompt_backed_structured_query_analyzer",
        analyzer_version=provider.prompt_ref,
        predicate_registry=predicates,
        relative_temporal_resolver=relative_temporal_resolver,
    )
