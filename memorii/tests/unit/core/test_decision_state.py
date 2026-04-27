from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from memorii.core.decision_state.models import (
    DecisionEvidencePolarity,
    DecisionState,
    DecisionStatus,
)
from memorii.core.decision_state.service import DecisionStateService
from memorii.core.decision_state.store import InMemoryDecisionStateStore


def _decision(
    decision_id: str,
    *,
    session_id: str = "s:1",
    task_id: str = "t:1",
    work_state_id: str = "ws:1",
) -> DecisionState:
    timestamp = datetime.now(UTC)
    return DecisionState(
        decision_id=decision_id,
        question="Which approach should we choose?",
        session_id=session_id,
        task_id=task_id,
        work_state_id=work_state_id,
        options=[],
        criteria=[],
        constraints=[],
        evidence=[],
        unresolved_questions=[],
        status=DecisionStatus.OPEN,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_open_decision_creates_open_decision() -> None:
    service = DecisionStateService()

    decision = service.open_decision(question="Should we ship feature X?", task_id="task:1")

    assert decision.status == DecisionStatus.OPEN
    assert decision.task_id == "task:1"
    assert service.get_decision(decision.decision_id) is not None


def test_add_option_appends_option() -> None:
    service = DecisionStateService()
    decision = service.open_decision(question="Should we ship feature X?")

    updated = service.add_option(
        decision_id=decision.decision_id,
        option_id="opt:a",
        label="Ship now",
    )

    assert updated is not None
    assert [option.option_id for option in updated.options] == ["opt:a"]


def test_add_criterion_appends_criterion() -> None:
    service = DecisionStateService()
    decision = service.open_decision(question="Choose architecture")

    updated = service.add_criterion(
        decision_id=decision.decision_id,
        criterion_id="crit:1",
        label="Reliability",
        weight=2.0,
    )

    assert updated is not None
    assert len(updated.criteria) == 1
    assert updated.criteria[0].criterion_id == "crit:1"
    assert updated.criteria[0].weight == 2.0


def test_add_evidence_appends_evidence_with_polarity() -> None:
    service = DecisionStateService()
    decision = service.open_decision(question="Choose database")

    updated = service.add_evidence(
        decision_id=decision.decision_id,
        evidence_id="ev:1",
        content="Operational cost is lower.",
        option_id="opt:a",
        polarity=DecisionEvidencePolarity.FOR_OPTION,
    )

    assert updated is not None
    assert len(updated.evidence) == 1
    assert updated.evidence[0].polarity.value == "for_option"


def test_update_recommendation_updates_recommendation() -> None:
    service = DecisionStateService()
    decision = service.open_decision(question="Choose test strategy")

    updated = service.update_recommendation(
        decision_id=decision.decision_id,
        recommendation="Prefer integration-first rollout.",
    )

    assert updated is not None
    assert updated.current_recommendation == "Prefer integration-first rollout."


def test_record_final_decision_marks_decided() -> None:
    service = DecisionStateService()
    decision = service.open_decision(question="Choose deployment region")

    updated = service.record_final_decision(
        decision_id=decision.decision_id,
        final_decision="Deploy to us-east-1",
    )

    assert updated is not None
    assert updated.status == DecisionStatus.DECIDED
    assert updated.final_decision == "Deploy to us-east-1"


def test_abandon_decision_marks_abandoned() -> None:
    service = DecisionStateService()
    decision = service.open_decision(question="Choose rollout window")

    updated = service.abandon_decision(decision_id=decision.decision_id)

    assert updated is not None
    assert updated.status == DecisionStatus.ABANDONED


def test_list_decisions_filters_by_task_session_work_state_and_status() -> None:
    service = DecisionStateService()
    a = service.open_decision(question="A", session_id="s:1", task_id="t:1", work_state_id="ws:1")
    b = service.open_decision(question="B", session_id="s:2", task_id="t:2", work_state_id="ws:2")
    service.record_final_decision(decision_id=b.decision_id, final_decision="done")

    assert [d.decision_id for d in service.list_decisions(session_id="s:1")] == [a.decision_id]
    assert [d.decision_id for d in service.list_decisions(task_id="t:2")] == [b.decision_id]
    assert [d.decision_id for d in service.list_decisions(work_state_id="ws:1")] == [a.decision_id]
    assert [d.decision_id for d in service.list_decisions(statuses=[DecisionStatus.DECIDED])] == [b.decision_id]


def test_store_upsert_replaces_same_decision_id() -> None:
    store = InMemoryDecisionStateStore()
    original = _decision("decision:1")
    updated = original.model_copy(update={"question": "Updated question"})

    store.upsert_decision(original)
    store.upsert_decision(updated)

    loaded = store.get_decision("decision:1")
    assert loaded is not None
    assert loaded.question == "Updated question"
    assert len(store.list_decisions()) == 1


def test_pydantic_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DecisionState(
            decision_id="decision:extra",
            question="q",
            options=[],
            criteria=[],
            constraints=[],
            evidence=[],
            unresolved_questions=[],
            status=DecisionStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            extra_field="not-allowed",
        )
