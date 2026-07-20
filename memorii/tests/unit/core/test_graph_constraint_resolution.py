from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.graph_constraint_resolution import (
    resolve_graph_constraints,
)
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ClaimLifecycleState,
    ClaimState,
    ConfidenceComponents,
    EntityLinkState,
)
from memorii.core.memory_evolution.query_graph import (
    AmbiguousEntityReference,
    ExecutableObjectConstraint,
    ExplicitEntitySet,
    GraphConstraintOperator,
    GraphPatternConstraint,
    GraphPatternFailureReason,
    GraphPatternResolutionStatus,
    GraphResolutionMethod,
    ObjectConstraint,
    ResolvedEntityReference,
)
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryTemporalFrame,
    QueryTemporalKind,
)
from pydantic import ValidationError

NOW = datetime(2026, 1, 3, tzinfo=UTC)
CONFIDENCE = ConfidenceComponents(
    extraction=1.0,
    evidence=1.0,
    source_trust=1.0,
    calibrated=1.0,
)


def _link(link_id: str, entity_id: str, name: str, entity_type: str) -> EntityLinkState:
    return EntityLinkState(
        link_id=link_id,
        mention_text=name,
        normalized_name=name.casefold(),
        canonical_entity_id=entity_id,
        entity_type=entity_type,
        confidence=1.0,
    )


def _claim(
    claim_id: str,
    *,
    subject: EntityLinkState,
    predicate: str,
    object_link: EntityLinkState,
) -> ClaimState:
    return ClaimState(
        claim_id=claim_id,
        claim_key=ClaimKey(subject_entity_id=subject.canonical_entity_id, predicate_id=predicate),
        object_value=object_link.mention_text,
        lifecycle_state=ClaimLifecycleState.ACTIVE,
        source_claim_id=f"source:{claim_id}",
        confidence=CONFIDENCE,
        subject_link_id=subject.link_id,
        object_link_id=object_link.link_id,
        valid_from=NOW,
    )


def _reference(entity: EntityLinkState) -> ResolvedEntityReference:
    return ResolvedEntityReference(
        entity_id=entity.canonical_entity_id,
        expected_entity_types=[entity.entity_type],
    )


def _pattern(
    predicate: str,
    *,
    object_link: EntityLinkState,
    operator: GraphConstraintOperator = GraphConstraintOperator.EQUALS,
) -> GraphPatternConstraint:
    return GraphPatternConstraint(
        predicate_id=predicate,
        object=ObjectConstraint(
            entity=_reference(object_link),
            value_type="entity",
            operator=operator,
        ),
    )


def _resolve(
    *,
    query: str,
    patterns: list[GraphPatternConstraint],
    states: list[ClaimState],
    links: list[EntityLinkState],
    language: str = "en",
):
    return resolve_graph_constraints(
        query=query,
        analysis=QueryAnalysis(
            language=language,
            predicate_id=patterns[0].predicate_id if len(patterns) == 1 else None,
            graph_patterns=patterns,
            temporal_frame=QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.CURRENT,
                evaluation_time=NOW,
            ),
        ),
        temporal_frame=QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.CURRENT,
            evaluation_time=NOW,
        ),
        states=states,
        entity_links=links,
    )


def test_explicit_object_no_match_never_falls_back_to_eligible_claims() -> None:
    atlas = _link("link:atlas", "entity:atlas", "Atlas", "service")
    carol = _link("link:carol", "person:carol", "Carol", "person")
    owen = _link("link:owen", "person:owen", "Owen", "person")

    result = _resolve(
        query="Who owns Atlas?",
        patterns=[_pattern("owner", object_link=carol)],
        states=[_claim("claim:owner", subject=atlas, predicate="owner", object_link=owen)],
        links=[atlas, carol, owen],
    )

    assert result.status == GraphPatternResolutionStatus.NO_MATCH
    assert result.matched_claim_ids == []
    assert result.failure_reasons == [GraphPatternFailureReason.OBJECT_CONSTRAINT_NO_MATCH]


def test_structured_constraints_are_invariant_to_query_language() -> None:
    atlas = _link("link:atlas", "entity:atlas", "Atlas", "service")
    carol = _link("link:carol", "person:carol", "Carol", "person")
    claim = _claim("claim:owner", subject=atlas, predicate="owner", object_link=carol)
    pattern = _pattern("owner", object_link=carol)

    english = _resolve(
        query="Which service is owned by Carol?",
        patterns=[pattern],
        states=[claim],
        links=[atlas, carol],
        language="en",
    )
    japanese = _resolve(
        query="キャロルが所有するサービスはどれですか？",
        patterns=[pattern],
        states=[claim],
        links=[atlas, carol],
        language="ja",
    )

    assert english.model_dump(mode="json") == japanese.model_dump(mode="json")
    assert japanese.status == GraphPatternResolutionStatus.RESOLVED
    assert japanese.resolution_method == GraphResolutionMethod.STRUCTURED_CONSTRAINT


def test_top_level_predicate_is_materialized_in_compiled_pattern() -> None:
    atlas = _link("link:atlas", "entity:atlas", "Atlas", "service")
    carol = _link("link:carol", "person:carol", "Carol", "person")
    frame = QueryTemporalFrame(
        temporal_kind=QueryTemporalKind.CURRENT,
        evaluation_time=NOW,
    )

    result = resolve_graph_constraints(
        query="Who owns Atlas?",
        analysis=QueryAnalysis(
            predicate_id="owner",
            graph_patterns=[GraphPatternConstraint(subject=_reference(atlas))],
            temporal_frame=frame,
        ),
        temporal_frame=frame,
        states=[_claim("claim:owner", subject=atlas, predicate="owner", object_link=carol)],
        entity_links=[atlas, carol],
    )

    assert result.status == GraphPatternResolutionStatus.RESOLVED
    assert result.pattern.predicate_id == "owner"
    assert result.matched_claim_ids == ["claim:owner"]


def test_conjunction_requires_one_common_evidence_backed_subject() -> None:
    atlas = _link("link:atlas", "entity:atlas", "Atlas", "service")
    other = _link("link:other", "entity:other", "Other", "service")
    carol = _link("link:carol", "person:carol", "Carol", "person")
    states = [
        _claim("claim:owner", subject=atlas, predicate="owner", object_link=carol),
        _claim("claim:api-owner", subject=atlas, predicate="api_owner", object_link=carol),
        _claim("claim:other-owner", subject=other, predicate="owner", object_link=carol),
    ]

    result = _resolve(
        query="Carol owns and is API owner",
        patterns=[_pattern("owner", object_link=carol), _pattern("api_owner", object_link=carol)],
        states=states,
        links=[atlas, other, carol],
    )

    assert result.status == GraphPatternResolutionStatus.RESOLVED
    assert result.subject_entity_id == atlas.canonical_entity_id
    assert result.matched_claim_ids == ["claim:api-owner", "claim:owner"]


def test_unimplemented_direction_is_not_part_of_the_public_schema() -> None:
    with pytest.raises(ValidationError, match="direction"):
        GraphPatternConstraint.model_validate({"predicate_id": "owner", "direction": "incoming"})


def test_negative_object_constraint_excludes_the_named_object() -> None:
    atlas = _link("link:atlas", "entity:atlas", "Atlas", "service")
    other = _link("link:other", "entity:other", "Other", "service")
    carol = _link("link:carol", "person:carol", "Carol", "person")
    owen = _link("link:owen", "person:owen", "Owen", "person")

    result = _resolve(
        query="Find an owner other than Carol",
        patterns=[
            _pattern(
                "owner",
                object_link=carol,
                operator=GraphConstraintOperator.NOT_EQUALS,
            )
        ],
        states=[
            _claim("claim:atlas-owner", subject=atlas, predicate="owner", object_link=carol),
            _claim("claim:other-owner", subject=other, predicate="owner", object_link=owen),
        ],
        links=[atlas, other, carol, owen],
    )

    assert result.status == GraphPatternResolutionStatus.RESOLVED
    assert result.subject_entity_id == other.canonical_entity_id
    assert result.matched_claim_ids == ["claim:other-owner"]


def test_ambiguous_reference_never_becomes_implicit_set_membership() -> None:
    atlas = _link("link:atlas", "entity:atlas", "Atlas", "service")
    carol = _link("link:carol", "person:carol", "Carol", "person")
    other_carol = _link("link:carol-2", "person:carol-2", "Carol", "person")
    pattern = GraphPatternConstraint(
        predicate_id="owner",
        object=ObjectConstraint(
            entity=AmbiguousEntityReference(
                mention="Carol",
                candidate_entity_ids=[carol.canonical_entity_id, other_carol.canonical_entity_id],
            ),
            value_type="entity",
        ),
    )

    result = _resolve(
        query="Which service is owned by Carol?",
        patterns=[pattern],
        states=[_claim("claim:owner", subject=atlas, predicate="owner", object_link=carol)],
        links=[atlas, carol, other_carol],
    )

    assert result.status == GraphPatternResolutionStatus.AMBIGUOUS
    assert result.matched_claim_ids == []
    assert result.failure_reasons == [GraphPatternFailureReason.AMBIGUOUS_ENTITY_REFERENCE]


def test_explicit_entity_set_is_distinct_from_ambiguous_reference() -> None:
    atlas = _link("link:atlas", "entity:atlas", "Atlas", "service")
    carol = _link("link:carol", "person:carol", "Carol", "person")
    other_carol = _link("link:carol-2", "person:carol-2", "Carol", "person")
    pattern = GraphPatternConstraint(
        predicate_id="owner",
        object=ObjectConstraint(
            entity=ExplicitEntitySet(
                entity_ids=[carol.canonical_entity_id, other_carol.canonical_entity_id]
            ),
            value_type="entity",
            operator=GraphConstraintOperator.IN,
        ),
    )

    result = _resolve(
        query="Which service is owned by either listed Carol?",
        patterns=[pattern],
        states=[_claim("claim:owner", subject=atlas, predicate="owner", object_link=carol)],
        links=[atlas, carol, other_carol],
    )

    assert result.status == GraphPatternResolutionStatus.RESOLVED
    assert result.subject_entity_id == atlas.canonical_entity_id


def test_object_constraint_without_predicate_is_structurally_invalid() -> None:
    carol = _link("link:carol", "person:carol", "Carol", "person")
    with pytest.raises(ValidationError, match="object constraints require a predicate_id"):
        GraphPatternConstraint(object=ObjectConstraint(entity=_reference(carol), value_type="entity"))


def test_entity_ids_and_executable_operands_reject_invalid_states() -> None:
    with pytest.raises(ValidationError, match="surrounding whitespace"):
        ResolvedEntityReference(entity_id=" entity:atlas ")
    with pytest.raises(ValidationError, match="exactly one"):
        ExecutableObjectConstraint(operator=GraphConstraintOperator.EQUALS)
    with pytest.raises(ValidationError, match="exactly one"):
        ExecutableObjectConstraint(
            operator=GraphConstraintOperator.EQUALS,
            entity_ids=["entity:atlas"],
            literal_value="Atlas",
        )


def test_negative_entity_constraint_does_not_treat_missing_link_as_inequality() -> None:
    atlas = _link("link:atlas", "entity:atlas", "Atlas", "service")
    carol = _link("link:carol", "person:carol", "Carol", "person")
    state = _claim("claim:owner", subject=atlas, predicate="owner", object_link=carol).model_copy(
        update={"object_link_id": None}
    )

    result = _resolve(
        query="Find an owner other than Carol",
        patterns=[
            _pattern(
                "owner",
                object_link=carol,
                operator=GraphConstraintOperator.NOT_EQUALS,
            )
        ],
        states=[state],
        links=[atlas, carol],
    )

    assert result.status == GraphPatternResolutionStatus.AMBIGUOUS
    assert result.failure_reasons == [GraphPatternFailureReason.OPEN_WORLD_COMPARISON_UNKNOWN]
