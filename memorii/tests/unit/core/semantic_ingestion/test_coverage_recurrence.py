from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore
from memorii.core.semantic_ingestion.catalog_authority import CatalogAuthorityScope
from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageSemanticOutcome,
    CoverageSourceSpan,
    ObserverBindingIdentity,
    classify_coverage_observation,
    new_coverage_observation,
    start_coverage_observation,
)
from memorii.core.semantic_ingestion.coverage_recurrence import (
    CoverageRecurrenceRepository,
    RelationGapSignature,
    VerifiedCoverageGap,
    VerifiedCoverageGapRepository,
    build_coverage_recurrence_group,
)

_CATALOG_SCOPE = CatalogAuthorityScope(schema_version=1, kind="base")
_SIGNATURE = RelationGapSignature.create(
    normalized_relation_meaning="mentors",
    subject_type_id="Person",
    object_type_id="Person",
    domain_id="organization",
    evidence_rule_id="direct_assertion:v1",
)


def _gap(
    ordinal: int,
    *,
    lineage: str,
    session_id: str,
    source_scope_digest: str = "2" * 64,
    signature: RelationGapSignature = _SIGNATURE,
) -> VerifiedCoverageGap:
    binding = ObserverBindingIdentity(
        binding_version="observer:v1",
        provider="local",
        model="test-model",
        prompt_version="prompt:v1",
        transport="in_process",
        egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )
    queued = new_coverage_observation(
        source_id=f"semantic_ingestion:source:{ordinal}",
        source_digest=f"{ordinal:x}" * 64,
        source_span=None,
        source_scope_digest=source_scope_digest,
        origin_lineage_digest=lineage,
        session_id=session_id,
        principal_id="user:one",
        agent_id="agent:one",
        observed_at=datetime(2026, 9, 27, tzinfo=UTC)
        + timedelta(minutes=ordinal),
        catalog_scope=_CATALOG_SCOPE,
        catalog_digest="4" * 64,
        observer_binding=binding,
    )
    classified = classify_coverage_observation(
        start_coverage_observation(queued),
        semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
        source_span=CoverageSourceSpan(start=0, end=7),
    )
    return VerifiedCoverageGap.from_observation(
        classified,
        signature=signature,
    )


def test_recurrence_requires_three_lineages_across_two_sessions() -> None:
    first = build_coverage_recurrence_group(
        (
            _gap(1, lineage="a" * 64, session_id="session:one"),
            _gap(2, lineage="b" * 64, session_id="session:one"),
        )
    )
    eligible = build_coverage_recurrence_group(
        (
            _gap(1, lineage="a" * 64, session_id="session:one"),
            _gap(2, lineage="b" * 64, session_id="session:one"),
            _gap(3, lineage="c" * 64, session_id="session:two"),
        )
    )

    assert first.proposal_eligible is False
    assert first.independent_lineage_count == 2
    assert first.distinct_session_count == 1
    assert eligible.proposal_eligible is True
    assert eligible.independent_lineage_count == 3
    assert eligible.distinct_session_count == 2


def test_copied_lineage_cannot_satisfy_lineage_or_session_threshold() -> None:
    group = build_coverage_recurrence_group(
        (
            _gap(1, lineage="a" * 64, session_id="session:one"),
            _gap(2, lineage="a" * 64, session_id="session:two"),
            _gap(3, lineage="b" * 64, session_id="session:one"),
        )
    )

    assert group.independent_lineage_count == 2
    assert group.distinct_session_count == 1
    assert group.example_diversity_count == 2
    assert group.proposal_eligible is False


def test_recurrence_rejects_cross_scope_and_semantic_grouping() -> None:
    other_signature = RelationGapSignature.create(
        normalized_relation_meaning="sponsors",
        subject_type_id="Person",
        object_type_id="Project",
        domain_id="organization",
        evidence_rule_id="direct_assertion:v1",
    )

    with pytest.raises(ValueError, match="cross a recurrence boundary"):
        build_coverage_recurrence_group(
            (
                _gap(1, lineage="a" * 64, session_id="session:one"),
                _gap(
                    2,
                    lineage="b" * 64,
                    session_id="session:two",
                    source_scope_digest="9" * 64,
                ),
            )
        )
    with pytest.raises(ValueError, match="cross a recurrence boundary"):
        build_coverage_recurrence_group(
            (
                _gap(1, lineage="a" * 64, session_id="session:one"),
                _gap(
                    2,
                    lineage="b" * 64,
                    session_id="session:two",
                    signature=other_signature,
                ),
            )
        )


def test_recurrence_group_persists_inertly_and_updates_with_cas() -> None:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    repository = CoverageRecurrenceRepository(plane)
    evidence_repository = VerifiedCoverageGapRepository(plane)
    first_gap = _gap(1, lineage="a" * 64, session_id="session:one")
    second_gap = _gap(2, lineage="b" * 64, session_id="session:two")
    first = build_coverage_recurrence_group(
        (first_gap,)
    )
    second = build_coverage_recurrence_group(
        (first_gap, second_gap)
    )

    evidence_repository.create(first_gap)
    assert repository.write(first, previous=None) == first
    assert repository.write(first, previous=None) == first
    evidence_repository.create(second_gap)
    assert repository.write(second, previous=first) == second
    assert repository.load(first.group_id) == second
    records = plane.list_records()
    assert len(records) == 3
    assert all(record.domain.value == "execution" for record in records)
    assert all(record.visibility.value == "internal_control" for record in records)
    assert evidence_repository.for_group(
        catalog_scope=first.catalog_scope,
        catalog_digest=first.catalog_digest,
        source_scope_digest=first.source_scope_digest,
        signature=first.signature,
    ) == tuple(sorted((first_gap, second_gap), key=lambda gap: gap.evidence_id))


def test_only_classified_bound_exact_span_gaps_enter_recurrence() -> None:
    binding = ObserverBindingIdentity(
        binding_version="observer:v1",
        provider="local",
        model="test-model",
        prompt_version="prompt:v1",
        transport="in_process",
        egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )
    queued = new_coverage_observation(
        source_id="semantic_ingestion:source:pending",
        source_digest="1" * 64,
        source_span=None,
        source_scope_digest="2" * 64,
        origin_lineage_digest="3" * 64,
        session_id="session:one",
        principal_id="user:one",
        agent_id="agent:one",
        observed_at=datetime(2026, 9, 27, tzinfo=UTC),
        catalog_scope=_CATALOG_SCOPE,
        catalog_digest="4" * 64,
        observer_binding=binding,
    )

    with pytest.raises(ValueError, match="not a verified recurrent gap"):
        VerifiedCoverageGap.from_observation(queued, signature=_SIGNATURE)
    with pytest.raises(ValueError, match="exact source span"):
        classify_coverage_observation(
            start_coverage_observation(queued),
            semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
            source_span=None,
        )
