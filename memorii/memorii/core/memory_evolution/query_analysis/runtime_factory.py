"""Explicit construction for prompt-backed production query analysis."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.query_analysis.analyzers import (
    EnglishLexicalQueryAnalyzer,
    ProductionQueryAnalyzer,
    StructuredQueryAnalyzer,
)
from memorii.core.memory_evolution.query_analysis.provider import PromptBackedStructuredQueryAnalysisProvider
from memorii.core.memory_evolution.temporal_compilation import RelativeTemporalExpressionResolver
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root


def build_production_query_analyzer(
    *,
    runtime_config: LLMRuntimeConfig,
    prompt_root: Path | None = None,
    predicate_registry: PredicateRegistry | None = None,
    relative_temporal_resolver: RelativeTemporalExpressionResolver | None = None,
    client_factory: Callable[[LLMRuntimeConfig], LLMStructuredClient] = LLMClientFactory.from_config,
) -> ProductionQueryAnalyzer:
    """Build the single production lexical-to-structured query composition."""

    lexical = EnglishLexicalQueryAnalyzer()
    if not runtime_config.has_live_provider():
        return ProductionQueryAnalyzer(lexical=lexical, structured=None)
    predicates = predicate_registry or PredicateRegistry()
    registry = PromptRegistry(prompt_root=prompt_root or default_prompt_root())
    runner = PromptLLMRunner(
        client=client_factory(runtime_config),
        config=runtime_config,
    )
    provider = PromptBackedStructuredQueryAnalysisProvider(
        runner=runner,
        registry=registry,
        predicate_registry=predicates,
    )
    structured = StructuredQueryAnalyzer(
        provider,
        analyzer_name="prompt_backed_structured_query_analyzer",
        analyzer_version=provider.prompt_ref,
        predicate_registry=predicates,
        relative_temporal_resolver=relative_temporal_resolver,
    )
    return ProductionQueryAnalyzer(lexical=lexical, structured=structured)
