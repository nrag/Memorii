from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.query_analysis import (
    PromptBackedStructuredQueryAnalysisProvider,
    StructuredQueryAnalyzer,
    StructuredQueryProviderError,
)
from memorii.core.memory_evolution.query_analysis.runtime_factory import build_prompt_backed_query_analyzer
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysisFailureCode,
    QueryTemporalKind,
    TemporalAnchor,
    TemporalAnchorCatalog,
    TemporalEntityCandidate,
)
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root


def _scope(*, task: str, session: str, user: str = "user:one") -> MemoryScope:
    return MemoryScope(
        scope_key=task,
        task_id=task,
        session_id=session,
        user_id=user,
    )


def _response(*, entity_id: str = "entity:visible", language: str = "en") -> str:
    return json.dumps(
        {
            "language": language,
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "candidate_entity_ids": [entity_id],
            "predicate_id": "owner",
            "subject_entity_id": entity_id,
            "graph_patterns": [],
            "entity_mentions": ["Atlas"],
            "model_confidence": 0.9,
            "abstention_reason": None,
        },
        sort_keys=True,
    )


def _provider(client: FakeLLMStructuredClient) -> PromptBackedStructuredQueryAnalysisProvider:
    config = LLMRuntimeConfig(provider="fake", model="fake-structured", max_retries=0)
    return PromptBackedStructuredQueryAnalysisProvider(
        runner=PromptLLMRunner(client=client, config=config),
        registry=PromptRegistry(prompt_root=default_prompt_root()),
    )


def test_prompt_backed_query_provider_exposes_only_readable_catalog_metadata() -> None:
    client = FakeLLMStructuredClient(default_response=_response())
    provider = _provider(client)
    request_scope = _scope(task="task:visible", session="session:visible")
    hidden_scope = _scope(task="task:hidden", session="session:hidden")
    visible_anchor = TemporalAnchor(
        anchor_id="anchor:visible",
        names=["June release"],
        valid_from=datetime(2025, 6, 1, tzinfo=UTC),
        valid_to=datetime(2025, 7, 1, tzinfo=UTC),
        source_ids=["source:visible-sensitive"],
        scope=request_scope,
    )
    hidden_anchor = TemporalAnchor(
        anchor_id="anchor:hidden",
        names=["Secret release"],
        valid_from=datetime(2024, 1, 1, tzinfo=UTC),
        valid_to=datetime(2024, 2, 1, tzinfo=UTC),
        source_ids=["source:hidden"],
        scope=hidden_scope,
    )

    proposal = provider(
        query="Who owns Atlas now?",
        language="en",
        reference_time=datetime(2026, 7, 19, tzinfo=UTC),
        entity_candidates=[
            TemporalEntityCandidate(
                entity_id="entity:visible",
                names=["Atlas"],
                entity_type="project",
                scope=request_scope,
            ),
            TemporalEntityCandidate(
                entity_id="entity:hidden",
                names=["Hidden Atlas"],
                entity_type="project",
                scope=hidden_scope,
            ),
        ],
        anchor_catalog=TemporalAnchorCatalog(anchors=[visible_anchor, hidden_anchor]),
        request_scope=request_scope,
    )

    assert proposal.candidate_entity_ids == ["entity:visible"]
    assert client.last_request is not None
    rendered = client.last_request.user
    assert "entity:visible" in rendered
    assert "anchor:visible" in rendered
    for forbidden in (
        "entity:hidden",
        "Hidden Atlas",
        "anchor:hidden",
        "Secret release",
        "task:visible",
        "task:hidden",
        "source:visible-sensitive",
        "source:hidden",
        "2025-06-01",
        "2025-07-01",
        "2024-01-01",
    ):
        assert forbidden not in rendered


def test_prompt_backed_query_analyzer_rejects_model_invented_entity_id() -> None:
    analyzer = StructuredQueryAnalyzer(
        _provider(FakeLLMStructuredClient(default_response=_response(entity_id="entity:invented"))),
        analyzer_name="prompt-backed",
        analyzer_version="structured_query_analysis:v1",
    )

    result = analyzer.analyze(
        query="Who owns Atlas now?",
        language="en",
        reference_time=datetime(2026, 7, 19, tzinfo=UTC),
        entity_candidates=[TemporalEntityCandidate(entity_id="entity:visible", names=["Atlas"])],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.temporal_intent == QueryTemporalKind.AMBIGUOUS
    assert result.failure_code == QueryAnalysisFailureCode.CONSTRAINT_ERROR
    assert result.provider_error == "StructuredQueryConstraintError"


def test_prompt_backed_query_analyzer_classifies_expected_provider_failure() -> None:
    analyzer = StructuredQueryAnalyzer(
        _provider(FakeLLMStructuredClient(raise_on_request=True)),
        analyzer_name="prompt-backed",
        analyzer_version="structured_query_analysis:v1",
    )

    result = analyzer.analyze(
        query="Who owns Atlas now?",
        language="en",
        reference_time=None,
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code == QueryAnalysisFailureCode.PROVIDER_ERROR
    assert result.provider_error == StructuredQueryProviderError.__name__


def test_prompt_backed_query_analyzer_preserves_non_english_language() -> None:
    analyzer = StructuredQueryAnalyzer(
        _provider(FakeLLMStructuredClient(default_response=_response(language="es"))),
        analyzer_name="prompt-backed",
        analyzer_version="structured_query_analysis:v1",
    )

    result = analyzer.analyze(
        query="¿Quién es propietario de Atlas ahora?",
        language="es",
        reference_time=datetime(2026, 7, 19, tzinfo=UTC),
        entity_candidates=[TemporalEntityCandidate(entity_id="entity:visible", names=["Atlas"])],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.language == "es"
    assert result.temporal_intent == QueryTemporalKind.CURRENT
    assert result.temporal_frame is not None
    assert result.temporal_frame.resolved_entity_ids == ["entity:visible"]


def test_prompt_backed_query_analyzer_factory_is_explicit_live_opt_in() -> None:
    with pytest.raises(ValueError, match="requires a configured live provider"):
        build_prompt_backed_query_analyzer(runtime_config=LLMRuntimeConfig(provider="none"))
