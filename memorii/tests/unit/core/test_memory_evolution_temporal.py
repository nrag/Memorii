from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.temporal import (
    QueryAnalysis,
    QueryScopeKind,
    QueryTemporalFrame,
    QueryTemporalKind,
    StructuredQueryAnalyzer,
    TemporalAnchor,
    TemporalAnchorCatalog,
    TemporalCandidate,
    TemporalEntityCandidate,
    candidate_matches_frame,
    resolve_query_temporal_frame,
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

    assert candidate_matches_frame(
        candidate,
        QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.CURRENT,
            evaluation_time=datetime(2026, 2, 1, tzinfo=UTC),
        ),
    ) is True
    assert candidate_matches_frame(
        candidate,
        QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.CURRENT,
            evaluation_time=datetime(2026, 4, 1, tzinfo=UTC),
        ),
    ) is False


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


def test_structured_query_analyzer_accepts_json_mapping_and_constrains_candidates() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "language": "es",
            "temporal_frame": {"temporal_kind": "current", "resolved_entity_ids": ["project"]},
            "analysis_confidence": 0.9,
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
    assert result.temporal_frame.resolution_confidence_source == "structured_model"


def test_structured_query_analyzer_abstains_on_unknown_entity_candidate() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_frame": {"temporal_kind": "current", "resolved_entity_ids": ["hidden"]},
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
            "temporal_frame": {"temporal_kind": "current"},
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
    assert candidate_matches_frame(
        candidate,
        QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.INTERVAL,
            valid_from=datetime(2026, 1, 15, tzinfo=UTC),
            valid_to=datetime(2026, 2, 1, tzinfo=UTC),
        ),
    ) is True
    assert candidate_matches_frame(
        candidate,
        QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.INTERVAL,
            valid_from=datetime(2026, 2, 1, tzinfo=UTC),
            valid_to=datetime(2026, 3, 1, tzinfo=UTC),
        ),
    ) is False


def test_current_candidate_is_inactive_at_exclusive_end() -> None:
    candidate = TemporalCandidate(
        record_id="claim",
        lifecycle_state="active",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 2, 1, tzinfo=UTC),
    )

    assert candidate_matches_frame(
        candidate,
        QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.CURRENT,
            evaluation_time=datetime(2026, 2, 1, tzinfo=UTC),
        ),
    ) is False


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
                scope_key="task:incident",
                source_ids=["event:incident-release"],
            ),
            TemporalAnchor(
                anchor_id="anchor:platform-release",
                names=["release week"],
                valid_from=datetime(2026, 7, 1, tzinfo=UTC),
                valid_to=datetime(2026, 7, 8, tzinfo=UTC),
                scope_key="task:platform",
                source_ids=["event:platform-release"],
            ),
        ]
    )

    result = resolve_query_temporal_frame(
        "What happened to Atlas during release week?",
        anchor_catalog=catalog,
        entity_candidates=[TemporalEntityCandidate(entity_id="atlas", names=["Atlas"])],
        scope_key="task:incident",
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
                scope_key="task:incident",
                source_ids=["event:incident-release"],
            )
        ]
    )

    resolution = catalog.resolve("What happened during release week?")

    assert resolution.status == "unresolved"


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
