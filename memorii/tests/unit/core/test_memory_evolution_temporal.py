from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.query_analysis import (
    ConservativeQueryAnalyzer,
    StructuredQueryAnalyzer,
    StructuredQueryConstraintError,
    infer_query_predicate_id,
    resolve_query_temporal_frame,
    validate_temporal_frame_constraints,
)
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryScopeKind,
    QueryTemporalFrame,
    QueryTemporalKind,
    TemporalAnchor,
    TemporalAnchorCatalog,
    TemporalCandidate,
    TemporalEntityCandidate,
    TemporalResolution,
    candidate_matches_frame,
)


def test_current_and_historical_frames_are_separate() -> None:
    candidate = TemporalCandidate(
        record_id="claim-bob",
        lifecycle_state="superseded",
        valid_from=datetime(2026, 3, 1, tzinfo=UTC),
        valid_to=None,
    )
    current = QueryTemporalFrame()
    historical = QueryTemporalFrame(
        temporal_kind=QueryTemporalKind.HISTORICAL,
        valid_from=datetime(2026, 3, 1, tzinfo=UTC),
        valid_to=datetime(2026, 3, 31, tzinfo=UTC),
    )

    assert candidate_matches_frame(candidate, current) is False
    assert candidate_matches_frame(candidate, historical) is True


def test_point_in_time_current_allows_claim_until_supersession_but_now_does_not() -> None:
    candidate = TemporalCandidate(
        record_id="claim-alice",
        lifecycle_state="superseded",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert (
        candidate_matches_frame(
            candidate,
            QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.CURRENT,
                evaluation_time=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        )
        is True
    )
    assert (
        candidate_matches_frame(
            candidate,
            QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.CURRENT,
                evaluation_time=datetime(2026, 4, 1, tzinfo=UTC),
            ),
        )
        is False
    )


def test_scoped_frame_requires_scope_key() -> None:
    with pytest.raises(ValueError, match="scope_key is required"):
        QueryTemporalFrame(scope_kind=QueryScopeKind.TASK)


def test_unscoped_frame_rejects_scope_key() -> None:
    with pytest.raises(ValueError, match="scope_key must be omitted"):
        QueryTemporalFrame(scope_key="task:one")


def test_with_scope_updates_scope_kind_and_key_together() -> None:
    frame = QueryTemporalFrame().with_scope("task:one")
    assert frame.scope_kind == QueryScopeKind.TASK
    assert frame.scope_key == "task:one"


def test_global_request_rejects_scoped_structured_frame() -> None:
    with pytest.raises(StructuredQueryConstraintError, match="out-of-scope frame"):
        validate_temporal_frame_constraints(
            QueryTemporalFrame(
                scope_kind=QueryScopeKind.TASK,
                scope_key="task:secret",
            ),
            entity_candidates=[],
            anchor_catalog=TemporalAnchorCatalog(),
            request_scope=MemoryScope(),
        )


def test_global_request_normalizes_unscoped_frame_to_explicit_global_scope() -> None:
    frame = validate_temporal_frame_constraints(
        QueryTemporalFrame(),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
        request_scope=MemoryScope(),
    )

    assert frame.scope_key == "global"
    assert frame.scope_kind == QueryScopeKind.GLOBAL


@pytest.mark.parametrize(
    ("request_scope", "expected_kind"),
    [
        (
            MemoryScope(
                scope_key="task:incident",
                task_id="task:incident",
                session_id="session:incident",
                user_id="user:one",
            ),
            QueryScopeKind.TASK,
        ),
        (
            MemoryScope(
                scope_key="session:incident",
                session_id="session:incident",
                user_id="user:one",
            ),
            QueryScopeKind.SESSION,
        ),
        (MemoryScope(scope_key="user:one", user_id="user:one"), QueryScopeKind.USER),
    ],
)
def test_structured_frame_inherits_typed_request_scope(
    request_scope: MemoryScope,
    expected_kind: QueryScopeKind,
) -> None:
    frame = validate_temporal_frame_constraints(
        QueryTemporalFrame(),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
        request_scope=request_scope,
    )

    assert frame.scope_key == request_scope.scope_key
    assert frame.scope_kind == expected_kind


def test_task_request_can_select_entity_from_readable_parent_scope() -> None:
    request_scope = MemoryScope(
        scope_key="task:incident",
        task_id="task:incident",
        session_id="session:incident",
        user_id="user:one",
    )
    frame = validate_temporal_frame_constraints(
        QueryTemporalFrame(resolved_entity_ids=["atlas"]),
        entity_candidates=[
            TemporalEntityCandidate(
                entity_id="atlas",
                names=["Atlas"],
                scope=MemoryScope(
                    scope_key="session:incident",
                    session_id="session:incident",
                    user_id="user:one",
                ),
            )
        ],
        anchor_catalog=TemporalAnchorCatalog(),
        request_scope=request_scope,
    )

    assert frame.resolved_entity_ids == ["atlas"]


def test_task_request_can_use_temporal_anchor_from_readable_parent_scope() -> None:
    request_scope = MemoryScope(
        scope_key="task:incident",
        task_id="task:incident",
        session_id="session:incident",
        user_id="user:one",
    )
    anchor = TemporalAnchor(
        anchor_id="anchor:session-release",
        names=["release week"],
        valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        valid_to=datetime(2026, 6, 8, tzinfo=UTC),
        source_ids=["event:session-release"],
        scope=MemoryScope(
            scope_key="session:incident",
            session_id="session:incident",
            user_id="user:one",
        ),
    )

    frame = validate_temporal_frame_constraints(
        QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.HISTORICAL,
            anchor_id=anchor.anchor_id,
            valid_from=anchor.valid_from,
            valid_to=anchor.valid_to,
        ),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(anchors=[anchor]),
        request_scope=request_scope,
    )

    assert frame.scope_key == "task:incident"
    assert frame.scope_kind == QueryScopeKind.TASK


def test_task_request_rejects_entity_from_unreadable_sibling_scope() -> None:
    request_scope = MemoryScope(
        scope_key="task:incident",
        task_id="task:incident",
        session_id="session:incident",
        user_id="user:one",
    )
    with pytest.raises(StructuredQueryConstraintError, match="out-of-scope entity"):
        validate_temporal_frame_constraints(
            QueryTemporalFrame(resolved_entity_ids=["atlas"]),
            entity_candidates=[
                TemporalEntityCandidate(
                    entity_id="atlas",
                    names=["Atlas"],
                    scope=MemoryScope(
                        scope_key="session:other",
                        session_id="session:other",
                        user_id="user:one",
                    ),
                )
            ],
            anchor_catalog=TemporalAnchorCatalog(),
            request_scope=request_scope,
        )


def test_structured_query_analyzer_accepts_json_mapping_and_constrains_candidates() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "language": "es",
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "candidate_entity_ids": ["project"],
            "model_confidence": 0.9,
        },
        analyzer_name="test-provider",
        analyzer_version="2026-07-16",
    )
    result = analyzer.analyze(
        query="¿Quién es el propietario?",
        language="es",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[TemporalEntityCandidate(entity_id="project", names=["Atlas"])],
        anchor_catalog=TemporalAnchorCatalog(),
    )
    assert result.analysis_source == "structured_model"
    assert result.confidence_source == "structured_model"
    assert result.confidence_is_calibrated is False
    assert result.analyzer_name == "test-provider"
    assert result.temporal_frame is not None
    assert result.temporal_frame.resolved_entity_ids == ["project"]
    assert result.temporal_frame.resolution_confidence_source == "temporal_compiler"


def test_structured_query_analyzer_cannot_author_current_evaluation_time() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "evaluation_time": "1980-01-01T00:00:00Z",
        },
        analyzer_name="untrusted-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query="Who owns Atlas now?",
        language="en",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code == "schema_error"
    assert result.temporal_frame is not None
    assert result.temporal_frame.temporal_kind == QueryTemporalKind.AMBIGUOUS


def test_structured_query_analyzer_cannot_author_historical_interval() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "historical",
            "temporal_expression": {"expression_kind": "current"},
            "valid_from": "1980-01-01T00:00:00Z",
            "valid_to": "1981-01-01T00:00:00Z",
        },
        analyzer_name="untrusted-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query="Who owned Atlas?",
        language="en",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code == "schema_error"


def test_structured_absolute_date_is_compiled_from_exact_multilingual_source_span() -> None:
    query = "¿Quién era el propietario el 2026-01?"
    date_text = "2026-01"
    start = query.index(date_text)
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "language": "es",
            "temporal_intent": "historical",
            "temporal_expression": {
                "expression_kind": "absolute_date",
                "source_span": {"start": start, "end": start + len(date_text), "text": date_text},
            },
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query=query,
        language="es",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code is None
    assert result.temporal_frame is not None
    assert result.temporal_frame.valid_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert result.temporal_frame.valid_to == datetime(2026, 2, 1, tzinfo=UTC)


def test_structured_temporal_source_span_must_match_original_query() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "historical",
            "temporal_expression": {
                "expression_kind": "absolute_date",
                "source_span": {"start": 0, "end": 7, "text": "2026-01"},
            },
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query="History for 2026-01",
        language="en",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code == "constraint_error"


def test_structured_catalog_anchor_uses_catalog_interval_and_request_scope() -> None:
    query = "What changed during release week?"
    anchor_text = "release week"
    start = query.index(anchor_text)
    anchor = TemporalAnchor(
        anchor_id="anchor:release",
        names=[anchor_text],
        valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        valid_to=datetime(2026, 6, 8, tzinfo=UTC),
        scope=MemoryScope(scope_key="task:release", task_id="task:release"),
        source_ids=["event:release"],
    )
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "historical",
            "temporal_expression": {
                "expression_kind": "catalog_anchor",
                "anchor_id": anchor.anchor_id,
                "source_span": {
                    "start": start,
                    "end": start + len(anchor_text),
                    "text": anchor_text,
                },
            },
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query=query,
        language="en",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(anchors=[anchor]),
        request_scope=MemoryScope(scope_key="task:release", task_id="task:release"),
    )

    assert result.failure_code is None
    assert result.temporal_frame is not None
    assert result.temporal_frame.anchor_id == anchor.anchor_id
    assert result.temporal_frame.valid_from == anchor.valid_from
    assert result.temporal_frame.valid_to == anchor.valid_to
    assert result.temporal_frame.scope_key == "task:release"


def test_structured_catalog_anchor_rejects_id_that_does_not_match_cited_span() -> None:
    query = "What changed during release week?"
    anchor_text = "release week"
    start = query.index(anchor_text)
    anchors = [
        TemporalAnchor(
            anchor_id="anchor:release",
            names=[anchor_text],
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
            valid_to=datetime(2026, 6, 8, tzinfo=UTC),
            source_ids=["event:release"],
        ),
        TemporalAnchor(
            anchor_id="anchor:incident",
            names=["incident week"],
            valid_from=datetime(2026, 7, 1, tzinfo=UTC),
            valid_to=datetime(2026, 7, 8, tzinfo=UTC),
            source_ids=["event:incident"],
        ),
    ]
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "historical",
            "temporal_expression": {
                "expression_kind": "catalog_anchor",
                "anchor_id": "anchor:incident",
                "source_span": {
                    "start": start,
                    "end": start + len(anchor_text),
                    "text": anchor_text,
                },
            },
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query=query,
        language="en",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(anchors=anchors),
    )

    assert result.failure_code == "constraint_error"
    assert result.temporal_frame is not None
    assert result.temporal_frame.temporal_kind == QueryTemporalKind.AMBIGUOUS


def test_structured_catalog_anchor_rejects_ambiguous_cited_span() -> None:
    query = "What changed during release week?"
    anchor_text = "release week"
    start = query.index(anchor_text)
    anchors = [
        TemporalAnchor(
            anchor_id=f"anchor:release:{index}",
            names=[anchor_text],
            valid_from=datetime(2026, 6, index, tzinfo=UTC),
            valid_to=datetime(2026, 6, index + 1, tzinfo=UTC),
            source_ids=[f"event:release:{index}"],
        )
        for index in (1, 2)
    ]
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "historical",
            "temporal_expression": {
                "expression_kind": "catalog_anchor",
                "anchor_id": anchors[0].anchor_id,
                "source_span": {
                    "start": start,
                    "end": start + len(anchor_text),
                    "text": anchor_text,
                },
            },
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query=query,
        language="en",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(anchors=anchors),
    )

    assert result.failure_code == "constraint_error"
    assert result.temporal_frame is not None
    assert result.temporal_frame.temporal_kind == QueryTemporalKind.AMBIGUOUS


def test_structured_relative_expression_fails_closed_without_locale_resolver() -> None:
    query = "What changed last quarter?"
    relative_text = "last quarter"
    start = query.index(relative_text)
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "historical",
            "temporal_expression": {
                "expression_kind": "relative_date",
                "source_span": {
                    "start": start,
                    "end": start + len(relative_text),
                    "text": relative_text,
                },
            },
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query=query,
        language="en",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code == "constraint_error"
    assert result.temporal_frame is not None
    assert result.temporal_frame.temporal_kind == QueryTemporalKind.AMBIGUOUS


def test_structured_impossible_iso_date_fails_as_classified_constraint_error() -> None:
    query = "History for 2026-99"
    date_text = "2026-99"
    start = query.index(date_text)
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "historical",
            "temporal_expression": {
                "expression_kind": "absolute_date",
                "source_span": {
                    "start": start,
                    "end": start + len(date_text),
                    "text": date_text,
                },
            },
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query=query,
        language="en",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code == "constraint_error"
    assert result.provider_error == "TemporalCompilationError"


def test_fallback_entity_resolution_honors_explicit_type_contrast() -> None:
    resolution = resolve_query_temporal_frame(
        "Who owns the Atlas project rather than the Atlas service?",
        reference_time=datetime(2026, 7, 16, tzinfo=UTC),
        entity_candidates=[
            TemporalEntityCandidate(
                entity_id="project",
                names=["Atlas"],
                entity_type="project",
            ),
            TemporalEntityCandidate(
                entity_id="service",
                names=["Atlas"],
                entity_type="service",
            ),
        ],
    )

    assert resolution.status == "resolved"
    assert resolution.frame.resolved_entity_ids == ["project"]


def test_structured_query_analyzer_abstains_on_unknown_entity_candidate() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "candidate_entity_ids": ["hidden"],
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )
    result = analyzer.analyze(
        query="Who owns Atlas?",
        language="en",
        reference_time=None,
        entity_candidates=[TemporalEntityCandidate(entity_id="project", names=["Atlas"])],
        anchor_catalog=TemporalAnchorCatalog(),
    )
    assert result.temporal_intent == QueryTemporalKind.AMBIGUOUS
    assert result.provider_error == "StructuredQueryConstraintError"
    assert result.failure_code.value == "constraint_error"
    assert result.abstention_reason is not None


def test_structured_query_analyzer_abstains_on_unknown_predicate() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "predicate_id": "not-registered",
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query="What is the state?",
        language="en",
        reference_time=None,
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code.value == "constraint_error"
    assert result.confidence_source == "provider"
    assert result.temporal_frame is not None
    assert result.temporal_frame.resolution_confidence_source == "provider"


def test_structured_graph_object_does_not_expand_temporal_subject_frame() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "predicate_id": "owner",
            "subject_entity_id": "project",
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "candidate_entity_ids": ["project"],
            "graph_patterns": [
                {
                    "subject": {
                        "reference_kind": "resolved",
                        "entity_id": "project",
                        "expected_entity_types": ["project"],
                    },
                    "predicate_id": "owner",
                    "object": {
                        "entity": {
                            "reference_kind": "resolved",
                            "entity_id": "person:carol",
                            "expected_entity_types": ["person"],
                        },
                        "value_type": "entity",
                    },
                }
            ],
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query="Which project is owned by Carol?",
        language="en",
        reference_time=None,
        entity_candidates=[
            TemporalEntityCandidate(entity_id="project", names=["Atlas"], entity_type="project"),
            TemporalEntityCandidate(entity_id="person:carol", names=["Carol"], entity_type="person"),
        ],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.temporal_frame is not None
    assert result.temporal_frame.resolved_entity_ids == ["project"]
    assert result.graph_patterns[0].object is not None
    assert result.graph_patterns[0].object.entity is not None
    assert result.graph_patterns[0].object.entity.entity_id == "person:carol"


def test_structured_graph_pattern_rejects_entity_type_mismatch() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "graph_patterns": [
                {
                    "subject": {
                        "reference_kind": "resolved",
                        "entity_id": "service",
                        "expected_entity_types": ["project"],
                    },
                    "predicate_id": "owner",
                }
            ],
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )

    result = analyzer.analyze(
        query="Who owns the project?",
        language="en",
        reference_time=None,
        entity_candidates=[
            TemporalEntityCandidate(entity_id="service", names=["Atlas"], entity_type="service")
        ],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code == "constraint_error"
    assert result.temporal_intent == QueryTemporalKind.AMBIGUOUS


def test_structured_query_analyzer_does_not_swallow_unexpected_provider_errors() -> None:
    def provider(**_kwargs: object) -> dict[str, object]:
        raise TypeError("provider programming error")

    analyzer = StructuredQueryAnalyzer(provider, analyzer_name="test-provider", analyzer_version="1")

    with pytest.raises(TypeError, match="provider programming error"):
        analyzer.analyze(
            query="Who owns Atlas?",
            language="en",
            reference_time=None,
            entity_candidates=[],
            anchor_catalog=TemporalAnchorCatalog(),
        )


def test_structured_query_analyzer_classifies_timeout_as_provider_failure() -> None:
    def provider(**_kwargs: object) -> dict[str, object]:
        raise TimeoutError("query analyzer timed out")

    analyzer = StructuredQueryAnalyzer(provider, analyzer_name="test-provider", analyzer_version="1")

    result = analyzer.analyze(
        query="Who owns Atlas?",
        language="en",
        reference_time=None,
        entity_candidates=[],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert result.failure_code == "provider_error"
    assert result.provider_error == "TimeoutError"
    assert result.analysis_source == "provider"


def test_temporal_candidate_interval_uses_exclusive_end() -> None:
    candidate = TemporalCandidate(
        record_id="claim",
        lifecycle_state="active",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert (
        candidate_matches_frame(
            candidate,
            QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.INTERVAL,
                valid_from=datetime(2026, 1, 15, tzinfo=UTC),
                valid_to=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        )
        is True
    )
    assert (
        candidate_matches_frame(
            candidate,
            QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.INTERVAL,
                valid_from=datetime(2026, 2, 1, tzinfo=UTC),
                valid_to=datetime(2026, 3, 1, tzinfo=UTC),
            ),
        )
        is False
    )


def test_current_candidate_is_inactive_at_exclusive_end() -> None:
    candidate = TemporalCandidate(
        record_id="claim",
        lifecycle_state="active",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 2, 1, tzinfo=UTC),
    )

    assert (
        candidate_matches_frame(
            candidate,
            QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.CURRENT,
                evaluation_time=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        )
        is False
    )


def test_temporal_frame_rejects_zero_length_interval() -> None:
    with pytest.raises(ValueError, match="half-open interval"):
        QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.INTERVAL,
            valid_from=datetime(2026, 2, 1, tzinfo=UTC),
            valid_to=datetime(2026, 2, 1, tzinfo=UTC),
        )


def test_temporal_entity_candidate_rejects_naive_or_zero_length_interval() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TemporalEntityCandidate(
            entity_id="atlas",
            names=["Atlas"],
            valid_from=datetime(2026, 1, 1),
        )
    with pytest.raises(ValueError, match="half-open interval"):
        TemporalEntityCandidate(
            entity_id="atlas",
            names=["Atlas"],
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_to=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_temporal_resolver_separates_historical_anchor_from_entity_resolution() -> None:
    result = resolve_query_temporal_frame(
        "Who owned Atlas billing migration in January before the directory update?",
        reference_time=datetime(2026, 7, 15, tzinfo=UTC),
        entity_candidates=[
            TemporalEntityCandidate(entity_id="project", names=["Atlas Billing Migration"]),
            TemporalEntityCandidate(entity_id="service", names=["Atlas Platform Service"]),
        ],
    )
    assert result.status == "resolved"
    assert result.frame.temporal_kind == QueryTemporalKind.HISTORICAL
    assert result.frame.valid_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert result.frame.resolved_entity_ids == ["project"]
    assert result.frame.resolution_confidence_source == "heuristic_uncalibrated"


def test_temporal_resolver_abstains_on_tied_entity_anchor() -> None:
    result = resolve_query_temporal_frame(
        "Which Atlas owner might be current?",
        entity_candidates=[
            TemporalEntityCandidate(entity_id="project", names=["Atlas"]),
            TemporalEntityCandidate(entity_id="service", names=["Atlas"]),
        ],
    )
    assert result.status == "ambiguous"
    assert result.frame.temporal_kind == QueryTemporalKind.AMBIGUOUS
    assert result.frame.resolved_entity_ids == ["project", "service"]


def test_non_english_query_requires_structured_temporal_frame() -> None:
    result = resolve_query_temporal_frame(
        "¿Quién es el propietario actual de Atlas?",
        language="es",
        entity_candidates=[TemporalEntityCandidate(entity_id="project", names=["Atlas"])],
    )

    assert result.status == "ambiguous"
    assert result.analysis_source == "language_guard"
    assert result.frame.temporal_kind == QueryTemporalKind.AMBIGUOUS
    assert result.frame.resolution_confidence_source == "language_guard"


def test_conservative_analyzer_accepts_an_explicit_locale_resolver() -> None:
    class SpanishResolver:
        def supports(self, language: str) -> bool:
            return language == "es"

        def infer_predicate_id(self, query: str) -> str | None:
            return "owner"

        def resolve_temporal_frame(self, query: str, **_kwargs: object) -> TemporalResolution:
            return TemporalResolution(
                frame=QueryTemporalFrame(
                    temporal_kind=QueryTemporalKind.CURRENT,
                    resolved_entity_ids=["project:atlas"],
                    resolution_confidence=0.65,
                ),
                status="resolved",
                rationale="resolved by Spanish locale policy",
                language="es",
                analysis_source="locale_resolver",
            )

    analysis = ConservativeQueryAnalyzer(lexical_resolver=SpanishResolver()).analyze(
        query="¿Quién es el propietario actual de Atlas?",
        language="es",
        reference_time=None,
        entity_candidates=[TemporalEntityCandidate(entity_id="project:atlas", names=["Atlas"])],
        anchor_catalog=TemporalAnchorCatalog(),
    )

    assert analysis.predicate_id == "owner"
    assert analysis.temporal_frame is not None
    assert analysis.temporal_frame.resolved_entity_ids == ["project:atlas"]


@pytest.mark.parametrize("query", ["The homeowner is waiting.", "Preview the release notes."])
def test_predicate_inference_does_not_match_substrings(query: str) -> None:
    assert infer_query_predicate_id(query) is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Who has ownership of Atlas?", "owner"),
        ("Who owns Atlas?", "owner"),
        ("Ｗｈｏ ｏｗｎｓ Atlas?", "owner"),
    ],
)
def test_predicate_inference_uses_unicode_normalized_token_boundaries(
    query: str,
    expected: str,
) -> None:
    assert infer_query_predicate_id(query) == expected


def test_structured_query_analysis_is_authoritative_for_non_english_retrieval() -> None:
    analysis = QueryAnalysis(
        language="es",
        temporal_frame=QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.CURRENT,
            resolved_entity_ids=["project"],
        ),
        analysis_source="structured_model",
    )
    assert analysis.temporal_frame is not None
    assert analysis.temporal_frame.resolved_entity_ids == ["project"]


def test_registered_named_temporal_anchor_resolves_with_evidence_backed_interval() -> None:
    catalog = TemporalAnchorCatalog(
        anchors=[
            TemporalAnchor(
                anchor_id="anchor:release-week",
                names=["release week", "launch week"],
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 8, tzinfo=UTC),
                source_ids=["event:release"],
            )
        ]
    )

    result = resolve_query_temporal_frame(
        "Who owned Atlas during release week?",
        entity_candidates=[TemporalEntityCandidate(entity_id="atlas", names=["Atlas"])],
        anchor_catalog=catalog,
    )

    assert result.status == "resolved"
    assert result.frame.anchor_id == "anchor:release-week"
    assert result.frame.valid_from == datetime(2026, 6, 1, tzinfo=UTC)
    assert result.frame.valid_to == datetime(2026, 6, 8, tzinfo=UTC)


def test_registered_named_temporal_anchor_abstains_when_aliases_collide() -> None:
    catalog = TemporalAnchorCatalog(
        anchors=[
            TemporalAnchor(
                anchor_id="anchor:release-a",
                names=["release week"],
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 8, tzinfo=UTC),
                source_ids=["event:release-a"],
            ),
            TemporalAnchor(
                anchor_id="anchor:release-b",
                names=["release week"],
                valid_from=datetime(2026, 7, 1, tzinfo=UTC),
                valid_to=datetime(2026, 7, 8, tzinfo=UTC),
                source_ids=["event:release-b"],
            ),
        ]
    )

    result = resolve_query_temporal_frame("What happened during release week?", anchor_catalog=catalog)

    assert result.status == "ambiguous"
    assert result.frame.temporal_kind == QueryTemporalKind.AMBIGUOUS


def test_registered_temporal_anchor_is_filtered_by_query_scope() -> None:
    catalog = TemporalAnchorCatalog(
        anchors=[
            TemporalAnchor(
                anchor_id="anchor:incident-release",
                names=["release week"],
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 8, tzinfo=UTC),
                scope=MemoryScope(scope_key="task:incident", task_id="task:incident"),
                source_ids=["event:incident-release"],
            ),
            TemporalAnchor(
                anchor_id="anchor:platform-release",
                names=["release week"],
                valid_from=datetime(2026, 7, 1, tzinfo=UTC),
                valid_to=datetime(2026, 7, 8, tzinfo=UTC),
                scope=MemoryScope(scope_key="task:platform", task_id="task:platform"),
                source_ids=["event:platform-release"],
            ),
        ]
    )

    result = resolve_query_temporal_frame(
        "What happened to Atlas during release week?",
        anchor_catalog=catalog,
        entity_candidates=[TemporalEntityCandidate(entity_id="atlas", names=["Atlas"])],
        request_scope=MemoryScope(scope_key="task:incident", task_id="task:incident"),
    )

    assert result.status == "resolved"
    assert result.frame.anchor_id == "anchor:incident-release"


def test_scoped_temporal_anchor_does_not_leak_into_global_query() -> None:
    catalog = TemporalAnchorCatalog(
        anchors=[
            TemporalAnchor(
                anchor_id="anchor:incident-release",
                names=["release week"],
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 8, tzinfo=UTC),
                scope=MemoryScope(scope_key="task:incident", task_id="task:incident"),
                source_ids=["event:incident-release"],
            )
        ]
    )

    resolution = catalog.resolve("What happened during release week?")

    assert resolution.status == "unresolved"


def test_session_scoped_temporal_anchor_preserves_full_scope_identity() -> None:
    session_scope = MemoryScope(
        scope_key="session:incident",
        session_id="session:incident",
        user_id="user:one",
    )
    catalog = TemporalAnchorCatalog(
        anchors=[
            TemporalAnchor(
                anchor_id="anchor:session-release",
                names=["release week"],
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 8, tzinfo=UTC),
                scope=session_scope,
                source_ids=["event:session-release"],
            )
        ]
    )

    result = resolve_query_temporal_frame(
        "What happened to Atlas during release week?",
        request_scope=session_scope,
        anchor_catalog=catalog,
        entity_candidates=[TemporalEntityCandidate(entity_id="atlas", names=["Atlas"])],
    )

    assert result.status == "resolved"
    assert result.frame.anchor_id == "anchor:session-release"


def test_temporal_anchor_prefers_most_specific_readable_scope() -> None:
    request_scope = MemoryScope(
        scope_key="task:incident",
        task_id="task:incident",
        session_id="session:incident",
        user_id="user:one",
    )
    catalog = TemporalAnchorCatalog(
        anchors=[
            TemporalAnchor(
                anchor_id="anchor:user-release",
                names=["release week"],
                valid_from=datetime(2026, 5, 1, tzinfo=UTC),
                valid_to=datetime(2026, 5, 8, tzinfo=UTC),
                scope=MemoryScope(scope_key="user:one", user_id="user:one"),
                source_ids=["event:user-release"],
            ),
            TemporalAnchor(
                anchor_id="anchor:session-release",
                names=["release week"],
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 8, tzinfo=UTC),
                scope=MemoryScope(
                    scope_key="session:incident",
                    session_id="session:incident",
                    user_id="user:one",
                ),
                source_ids=["event:session-release"],
            ),
        ]
    )

    resolution = catalog.resolve("What happened during release week?", scope=request_scope)

    assert resolution.status == "resolved"
    assert resolution.anchor is not None
    assert resolution.anchor.anchor_id == "anchor:session-release"


def test_entity_resolution_is_lifecycle_aware_for_current_and_historical_queries() -> None:
    candidates = [
        TemporalEntityCandidate(
            entity_id="old-atlas",
            names=["Atlas"],
            lifecycle_state="split",
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_to=datetime(2026, 4, 1, tzinfo=UTC),
        ),
        TemporalEntityCandidate(
            entity_id="new-atlas",
            names=["Atlas"],
            lifecycle_state="active",
            valid_from=datetime(2026, 3, 1, tzinfo=UTC),
        ),
    ]

    current = resolve_query_temporal_frame("Who owns Atlas now?", entity_candidates=candidates)
    historical = resolve_query_temporal_frame(
        "Who owned Atlas in January 2026?",
        entity_candidates=candidates,
    )

    assert current.status == "resolved"
    assert current.frame.resolved_entity_ids == ["new-atlas"]
    assert historical.status == "resolved"
    assert historical.frame.resolved_entity_ids == ["old-atlas"]


def test_temporal_anchor_matching_uses_boundaries() -> None:
    catalog = TemporalAnchorCatalog(
        anchors=[
            TemporalAnchor(
                anchor_id="anchor:q1",
                names=["Q1"],
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_to=datetime(2026, 4, 1, tzinfo=UTC),
                source_ids=["event:q1"],
            )
        ]
    )

    assert catalog.resolve("What happened in Q10?").status == "unresolved"
    assert catalog.resolve("What happened in Q1?").status == "resolved"
