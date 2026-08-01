from __future__ import annotations

from datetime import UTC, datetime

import pytest
from memorii.core.benchmark.memory_evolution_sim.claim_policy import (
    ACTION_PREDICATES,
    NONCURRENT_CLAIM_STATES,
    TERMINAL_ACTION_VALUES,
    is_action_claim,
    is_execution_eligible_claim,
    is_identity_confusion_bridge,
    is_noncurrent_claim,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import VisibleClaimCandidate


def _claim(
    claim_id: str,
    *,
    subject_id: str = "entity:project",
    predicate: str = "owner",
    object_value: str = "Sam",
    object_entity_id: str | None = "entity:sam",
    lifecycle_state: str = "active",
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
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=None,
        source_trust=3,
        source_modality="assertion",
        evidence_event_ids=[f"event:{claim_id}"],
        evidence_quote=claim_id,
    )


@pytest.mark.parametrize("state", sorted(NONCURRENT_CLAIM_STATES))
def test_noncurrent_policy_covers_every_owned_state(state: str) -> None:
    assert is_noncurrent_claim(_claim("claim", lifecycle_state=state))


def test_active_claim_is_current() -> None:
    assert not is_noncurrent_claim(_claim("claim"))


@pytest.mark.parametrize("predicate", sorted(ACTION_PREDICATES))
def test_action_policy_recognizes_owned_predicates(predicate: str) -> None:
    assert is_action_claim(_claim("claim", predicate=predicate))


@pytest.mark.parametrize("value", sorted(TERMINAL_ACTION_VALUES))
def test_terminal_action_is_not_execution_eligible(value: str) -> None:
    claim = _claim(
        "claim",
        predicate="action_state",
        object_value=value,
        object_entity_id=None,
    )

    assert is_action_claim(claim)
    assert not is_execution_eligible_claim(claim)


def test_active_nonterminal_action_is_execution_eligible() -> None:
    claim = _claim(
        "claim",
        predicate="action_state",
        object_value="in_progress",
        object_entity_id=None,
    )

    assert is_execution_eligible_claim(claim)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({}, True),
        ({"predicate_id": "reviewer"}, False),
        ({"object_entity_id": None}, False),
        ({"object_entity_id": "entity:other"}, False),
        ({"subject_entity_id": "entity:project"}, False),
    ],
)
def test_identity_bridge_requires_structural_identity_confusion(
    change: dict[str, str | None],
    expected: bool,
) -> None:
    stale = _claim("stale", lifecycle_state="superseded")
    candidate = _claim(
        "candidate",
        subject_id="entity:service",
    ).model_copy(
        update=change,
    )

    assert is_identity_confusion_bridge(stale, candidate) is expected


def test_active_claims_do_not_form_identity_bridge() -> None:
    left = _claim("left")
    right = _claim("right", subject_id="entity:service")

    assert not is_identity_confusion_bridge(left, right)
