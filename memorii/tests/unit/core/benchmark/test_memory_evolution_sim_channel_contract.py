from __future__ import annotations

import pytest
from memorii.core.benchmark.memory_evolution_sim.channel_contract import (
    ChannelAlgebraViolation,
    channel_algebra_violations,
    require_valid_channel_algebra,
    selected_entity_ids_for_claims,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    SimSystemOutput,
    VisibleClaimCandidate,
)


def _output(**updates: object) -> SimSystemOutput:
    return SimSystemOutput(
        selected_entity_ids=["entity:selected"],
        selected_claim_ids=["claim:selected"],
        selected_relation_ids=["relation:selected"],
        supporting_claim_ids=["claim:selected"],
        supporting_relation_ids=["relation:selected"],
        supporting_citation_event_ids=["event:supporting"],
        context_entity_ids=["entity:context"],
        context_claim_ids=["claim:context"],
        context_relation_ids=["relation:context"],
        context_citation_event_ids=["event:context"],
        rejected_entity_ids=["entity:rejected"],
        rejected_claim_ids=["claim:rejected"],
        rejected_relation_ids=["relation:rejected"],
        rejection_citation_event_ids=["event:rejected"],
        answer="answer",
        rationale="valid channel fixture",
    ).model_copy(update=updates)


def test_channel_algebra_accepts_valid_disjoint_channels() -> None:
    output = _output()

    assert channel_algebra_violations(output) == ()
    require_valid_channel_algebra(output)


@pytest.mark.parametrize(
    ("updates", "violation"),
    [
        (
            {"supporting_claim_ids": ["claim:different"]},
            ChannelAlgebraViolation.SELECTED_SUPPORTING_CLAIMS_DIFFER,
        ),
        (
            {"supporting_relation_ids": []},
            ChannelAlgebraViolation.SELECTED_RELATIONS_NOT_SUPPORTING,
        ),
        (
            {"context_claim_ids": ["claim:selected"]},
            ChannelAlgebraViolation.CLAIM_CHANNEL_OVERLAP,
        ),
        (
            {"rejected_claim_ids": ["claim:selected"]},
            ChannelAlgebraViolation.CLAIM_CHANNEL_OVERLAP,
        ),
        (
            {
                "context_claim_ids": ["claim:overlap"],
                "rejected_claim_ids": ["claim:overlap"],
            },
            ChannelAlgebraViolation.CLAIM_CHANNEL_OVERLAP,
        ),
        (
            {"context_entity_ids": ["entity:selected"]},
            ChannelAlgebraViolation.ENTITY_CHANNEL_OVERLAP,
        ),
        (
            {"rejected_entity_ids": ["entity:selected"]},
            ChannelAlgebraViolation.ENTITY_CHANNEL_OVERLAP,
        ),
        (
            {
                "context_entity_ids": ["entity:overlap"],
                "rejected_entity_ids": ["entity:overlap"],
            },
            ChannelAlgebraViolation.ENTITY_CHANNEL_OVERLAP,
        ),
        (
            {"context_relation_ids": ["relation:selected"]},
            ChannelAlgebraViolation.RELATION_CHANNEL_OVERLAP,
        ),
        (
            {"rejected_relation_ids": ["relation:selected"]},
            ChannelAlgebraViolation.RELATION_CHANNEL_OVERLAP,
        ),
        (
            {
                "context_relation_ids": ["relation:overlap"],
                "rejected_relation_ids": ["relation:overlap"],
            },
            ChannelAlgebraViolation.RELATION_CHANNEL_OVERLAP,
        ),
        (
            {"context_citation_event_ids": ["event:supporting"]},
            ChannelAlgebraViolation.CITATION_CHANNEL_OVERLAP,
        ),
        (
            {"rejection_citation_event_ids": ["event:supporting"]},
            ChannelAlgebraViolation.CITATION_CHANNEL_OVERLAP,
        ),
        (
            {
                "context_citation_event_ids": ["event:overlap"],
                "rejection_citation_event_ids": ["event:overlap"],
            },
            ChannelAlgebraViolation.CITATION_CHANNEL_OVERLAP,
        ),
        (
            {"selected_claim_ids": ["claim:selected", "claim:selected"]},
            ChannelAlgebraViolation.DUPLICATE_CHANNEL_ID,
        ),
    ],
)
def test_channel_algebra_rejects_each_forbidden_overlap(
    updates: dict[str, object],
    violation: ChannelAlgebraViolation,
) -> None:
    output = _output(**updates)

    assert violation in channel_algebra_violations(output)
    with pytest.raises(ValueError, match=violation.value):
        require_valid_channel_algebra(output)


def test_selected_entity_projection_has_one_policy_owner() -> None:
    claim = VisibleClaimCandidate(
        claim_id="claim:selected",
        subject_entity_id="entity:subject",
        subject_entity_type="project",
        subject_name="Atlas",
        predicate_id="owner",
        object_value="Rina",
        object_entity_id="entity:object",
        object_entity_type="person",
        lifecycle_state="active",
        scope_key="global",
        source_trust=5,
        source_modality="verified_observation",
        evidence_event_ids=["event:support"],
        evidence_quote="Rina owns Atlas.",
    )

    assert selected_entity_ids_for_claims(
        selected_claims=[claim],
        role_policy="subject",
    ) == ["entity:subject"]
    assert selected_entity_ids_for_claims(
        selected_claims=[claim],
        role_policy="subject_and_object",
    ) == ["entity:subject", "entity:object"]
    assert (
        selected_entity_ids_for_claims(
            selected_claims=[claim],
            role_policy="audit_graph_entities",
        )
        == []
    )
