from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    ReconstructionTaskContract,
    SimClaimAssessment,
    SimClaimSemanticRole,
    VisibleCheckpointCandidate,
    VisibleClaimCandidate,
)
from memorii.core.benchmark.memory_evolution_sim.visible_graph_closure import (
    derive_visible_graph_closure,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _claim(
    claim_id: str,
    *,
    subject_id: str,
    predicate: str = "owner",
    object_value: str,
    object_entity_id: str | None = None,
    lifecycle_state: str = "active",
    contradicts: tuple[str, ...] = (),
) -> VisibleClaimCandidate:
    return VisibleClaimCandidate(
        claim_id=claim_id,
        subject_entity_id=subject_id,
        subject_name=subject_id,
        subject_entity_type="task" if predicate == "action_state" else "project",
        predicate_id=predicate,
        object_value=object_value,
        object_entity_id=object_entity_id,
        object_entity_type="person" if object_entity_id else None,
        scope_key="global",
        lifecycle_state=lifecycle_state,
        valid_from=_NOW,
        valid_to=None,
        source_trust=3,
        source_modality="assertion",
        evidence_event_ids=[f"event:{claim_id}"],
        evidence_quote=claim_id,
        contradicts_claim_ids=list(contradicts),
    )


def _context(
    claims: list[VisibleClaimCandidate],
    *,
    next_action: bool = False,
) -> MemoryEvolutionSimReconstructionContext:
    contract = (
        ReconstructionTaskContract(
            allowed_operations=["next_action"],
            answer_required=False,
            answer_projection_policy="next_action",
            wrong_entity_claim_placement="rejected",
            requires_next_action=True,
        )
        if next_action
        else ReconstructionTaskContract(wrong_entity_claim_placement="rejected")
    )
    return MemoryEvolutionSimReconstructionContext(
        scenario_id="scenario",
        surface_observations=[],
        checkpoint=VisibleCheckpointCandidate(
            checkpoint_id="checkpoint",
            timestamp=_NOW,
            query_or_task="visible task",
            task_contract=contract,
        ),
        visible_claim_ids=[claim.claim_id for claim in claims],
        visible_claims=claims,
    )


def _assessments(
    claims: list[VisibleClaimCandidate],
    *,
    primary_id: str,
    relevant_ids: tuple[str, ...] = (),
) -> list[SimClaimAssessment]:
    return [
        SimClaimAssessment(
            claim_id=claim.claim_id,
            role=(
                SimClaimSemanticRole.PRIMARY
                if claim.claim_id == primary_id
                else (
                    SimClaimSemanticRole.RELEVANT
                    if claim.claim_id in relevant_ids
                    else SimClaimSemanticRole.IRRELEVANT
                )
            ),
            belief_rank=None,
        )
        for claim in claims
    ]


def test_closure_adds_lifecycle_and_one_hop_identity_confusion() -> None:
    claims = [
        _claim(
            "claim:primary",
            subject_id="entity:project",
            object_value="Nadia",
            object_entity_id="entity:nadia",
        ),
        _claim(
            "claim:stale",
            subject_id="entity:project",
            object_value="Sam",
            object_entity_id="entity:sam",
            lifecycle_state="superseded",
        ),
        _claim(
            "claim:wrong-subject",
            subject_id="entity:service",
            object_value="Sam",
            object_entity_id="entity:sam",
        ),
        _claim(
            "claim:unrelated",
            subject_id="entity:other",
            predicate="reviewer",
            object_value="Sam",
            object_entity_id="entity:sam",
        ),
    ]

    closure = derive_visible_graph_closure(
        context=_context(claims),
        assessments=_assessments(claims, primary_id="claim:primary"),
    )

    assert set(closure.primary_claim_ids) == {"claim:primary"}
    assert set(closure.relevant_claim_ids) == {
        "claim:primary",
        "claim:stale",
        "claim:wrong-subject",
    }


def test_closure_does_not_follow_a_second_identity_hop() -> None:
    claims = [
        _claim(
            "claim:primary",
            subject_id="entity:project",
            object_value="Nadia",
            object_entity_id="entity:nadia",
        ),
        _claim(
            "claim:stale-project",
            subject_id="entity:project",
            object_value="Sam",
            object_entity_id="entity:sam",
            lifecycle_state="superseded",
        ),
        _claim(
            "claim:service-current",
            subject_id="entity:service",
            object_value="Sam",
            object_entity_id="entity:sam",
        ),
        _claim(
            "claim:service-stale",
            subject_id="entity:service",
            object_value="Bob",
            object_entity_id="entity:bob",
            lifecycle_state="superseded",
        ),
        _claim(
            "claim:second-hop",
            subject_id="entity:other",
            object_value="Bob",
            object_entity_id="entity:bob",
        ),
    ]

    closure = derive_visible_graph_closure(
        context=_context(claims),
        assessments=_assessments(claims, primary_id="claim:primary"),
    )

    assert "claim:service-current" in closure.relevant_claim_ids
    assert "claim:service-stale" not in closure.relevant_claim_ids
    assert "claim:second-hop" not in closure.relevant_claim_ids


def test_active_claims_with_shared_object_do_not_bridge() -> None:
    claims = [
        _claim(
            "claim:primary",
            subject_id="entity:project",
            object_value="Sam",
            object_entity_id="entity:sam",
        ),
        _claim(
            "claim:other",
            subject_id="entity:service",
            object_value="Sam",
            object_entity_id="entity:sam",
        ),
    ]

    closure = derive_visible_graph_closure(
        context=_context(claims),
        assessments=_assessments(claims, primary_id="claim:primary"),
    )

    assert closure.relevant_claim_ids == ("claim:primary",)


def test_execution_closure_adds_all_action_competitors_but_not_owner_context() -> None:
    claims = [
        _claim(
            "claim:active-branch",
            subject_id="entity:branch-b",
            predicate="action_state",
            object_value="in_progress",
        ),
        _claim(
            "claim:blocked-branch",
            subject_id="entity:branch-a",
            predicate="action_state",
            object_value="blocked",
        ),
        _claim(
            "claim:superseded-action",
            subject_id="entity:branch-b",
            predicate="action_state",
            object_value="started",
            lifecycle_state="superseded",
        ),
        _claim(
            "claim:owner",
            subject_id="entity:project",
            object_value="Nadia",
            object_entity_id="entity:nadia",
        ),
    ]

    closure = derive_visible_graph_closure(
        context=_context(claims, next_action=True),
        assessments=_assessments(claims, primary_id="claim:active-branch"),
    )

    assert set(closure.relevant_claim_ids) == {
        "claim:active-branch",
        "claim:blocked-branch",
        "claim:superseded-action",
    }
    assert closure.primary_claim_ids == ("claim:active-branch",)


def test_closure_is_invariant_to_order_and_visible_labels() -> None:
    claims = [
        _claim(
            "claim:primary",
            subject_id="entity:project",
            object_value="Nadia",
            object_entity_id="entity:nadia",
        ),
        _claim(
            "claim:stale",
            subject_id="entity:project",
            object_value="Sam",
            object_entity_id="entity:sam",
            lifecycle_state="superseded",
        ),
        _claim(
            "claim:wrong",
            subject_id="entity:service",
            object_value="Sam",
            object_entity_id="entity:sam",
        ),
    ]
    expected = derive_visible_graph_closure(
        context=_context(claims),
        assessments=_assessments(claims, primary_id="claim:primary"),
    )
    changed_claims = [
        claim.model_copy(
            update={
                "subject_name": f"renamed:{claim.subject_name}",
                "evidence_quote": f"rewritten:{claim.evidence_quote}",
            }
        )
        for claim in reversed(claims)
    ]

    actual = derive_visible_graph_closure(
        context=_context(changed_claims),
        assessments=list(
            reversed(
                _assessments(changed_claims, primary_id="claim:primary")
            )
        ),
    )

    assert actual == expected
