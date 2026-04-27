from datetime import UTC, datetime

from memorii.core.decision_state.models import DecisionState, DecisionStatus
from memorii.core.decision_state.store import JsonlDecisionStateStore
from memorii.core.work_state.models import (
    WorkStateBinding,
    WorkStateBindingStatus,
    WorkStateEvent,
    WorkStateEventType,
    WorkStateKind,
    WorkStateRecord,
    WorkStateStatus,
)
from memorii.core.work_state.store import JsonlWorkStateStore


def _now() -> datetime:
    return datetime.now(UTC)


def _state(
    work_state_id: str,
    *,
    session_id: str = "s:1",
    task_id: str = "t:1",
    user_id: str = "u:1",
    kind: WorkStateKind = WorkStateKind.TASK_EXECUTION,
    status: WorkStateStatus = WorkStateStatus.ACTIVE,
    title: str = "Work",
) -> WorkStateRecord:
    timestamp = _now()
    return WorkStateRecord(
        work_state_id=work_state_id,
        kind=kind,
        status=status,
        session_id=session_id,
        task_id=task_id,
        user_id=user_id,
        title=title,
        summary="summary",
        confidence=0.8,
        source_event_ids=["e:1"],
        created_at=timestamp,
        updated_at=timestamp,
    )


def _binding(
    binding_id: str,
    *,
    session_id: str = "s:1",
    task_id: str = "t:1",
    work_state_id: str = "ws:1",
    status: WorkStateBindingStatus = WorkStateBindingStatus.ACTIVE,
) -> WorkStateBinding:
    timestamp = _now()
    return WorkStateBinding(
        binding_id=binding_id,
        session_id=session_id,
        task_id=task_id,
        work_state_id=work_state_id,
        execution_node_id="exec:1",
        solver_run_id="solver:1",
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _event(event_id: str, *, work_state_id: str, content: str) -> WorkStateEvent:
    return WorkStateEvent(
        event_id=event_id,
        work_state_id=work_state_id,
        event_type=WorkStateEventType.PROGRESS,
        content=content,
        evidence_ids=["ev:1"],
        created_at=_now(),
    )


def _decision(
    decision_id: str,
    *,
    session_id: str = "s:1",
    task_id: str = "t:1",
    work_state_id: str = "ws:1",
    status: DecisionStatus = DecisionStatus.OPEN,
    question: str = "Choose",
) -> DecisionState:
    timestamp = _now()
    return DecisionState(
        decision_id=decision_id,
        work_state_id=work_state_id,
        session_id=session_id,
        task_id=task_id,
        user_id="u:1",
        question=question,
        status=status,
        options=[],
        criteria=[],
        constraints=[],
        evidence=[],
        unresolved_questions=[],
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_jsonl_work_state_store_upsert_get_state(tmp_path) -> None:
    store = JsonlWorkStateStore(tmp_path)
    state = _state("ws:1")

    store.upsert_state(state)

    loaded = store.get_state("ws:1")
    assert loaded is not None
    assert loaded.work_state_id == "ws:1"


def test_jsonl_work_state_store_latest_state_wins_by_id(tmp_path) -> None:
    store = JsonlWorkStateStore(tmp_path)
    original = _state("ws:1", title="old")
    updated = original.model_copy(update={"title": "new", "updated_at": _now()})

    store.upsert_state(original)
    store.upsert_state(updated)

    states = store.list_states()
    assert len(states) == 1
    assert states[0].title == "new"


def test_jsonl_work_state_store_list_states_filters(tmp_path) -> None:
    store = JsonlWorkStateStore(tmp_path)
    a = _state("ws:a", session_id="s:a", task_id="t:a", user_id="u:a")
    b = _state(
        "ws:b",
        session_id="s:b",
        task_id="t:b",
        user_id="u:b",
        kind=WorkStateKind.INVESTIGATION,
        status=WorkStateStatus.PAUSED,
    )
    store.upsert_state(a)
    store.upsert_state(b)

    assert [s.work_state_id for s in store.list_states(session_id="s:a")] == ["ws:a"]
    assert [s.work_state_id for s in store.list_states(task_id="t:b")] == ["ws:b"]
    assert [s.work_state_id for s in store.list_states(user_id="u:a")] == ["ws:a"]
    assert [s.work_state_id for s in store.list_states(kinds=[WorkStateKind.INVESTIGATION])] == ["ws:b"]
    assert [s.work_state_id for s in store.list_states(statuses=[WorkStateStatus.PAUSED])] == ["ws:b"]


def test_jsonl_work_state_store_binding_upsert_list_filters(tmp_path) -> None:
    store = JsonlWorkStateStore(tmp_path)
    original = _binding("b:1", task_id="t:1")
    updated = original.model_copy(update={"status": WorkStateBindingStatus.PAUSED, "updated_at": _now()})
    other = _binding("b:2", session_id="s:2", task_id="t:2", work_state_id="ws:2")

    store.upsert_binding(original)
    store.upsert_binding(updated)
    store.upsert_binding(other)

    all_bindings = store.list_bindings()
    assert len(all_bindings) == 2
    assert [b.binding_id for b in store.list_bindings(session_id="s:2")] == ["b:2"]
    assert [b.binding_id for b in store.list_bindings(task_id="t:1")] == ["b:1"]
    assert [b.binding_id for b in store.list_bindings(work_state_id="ws:1")] == ["b:1"]
    assert [b.binding_id for b in store.list_bindings(statuses=[WorkStateBindingStatus.PAUSED])] == ["b:1"]


def test_jsonl_work_state_store_events_append_list_in_order(tmp_path) -> None:
    store = JsonlWorkStateStore(tmp_path)
    event_one = _event("e:1", work_state_id="ws:1", content="first")
    event_two = _event("e:2", work_state_id="ws:1", content="second")
    other = _event("e:3", work_state_id="ws:2", content="other")

    store.append_event(event_one)
    store.append_event(event_two)
    store.append_event(other)

    events = store.list_events("ws:1")
    assert [event.event_id for event in events] == ["e:1", "e:2"]
    assert [event.content for event in events] == ["first", "second"]


def test_jsonl_work_state_store_returns_empty_lists_when_files_absent(tmp_path) -> None:
    store = JsonlWorkStateStore(tmp_path / "missing")

    assert store.list_states() == []
    assert store.list_bindings() == []
    assert store.list_events("ws:none") == []


def test_jsonl_decision_state_store_upsert_get_decision(tmp_path) -> None:
    store = JsonlDecisionStateStore(tmp_path)
    decision = _decision("d:1")

    store.upsert_decision(decision)

    loaded = store.get_decision("d:1")
    assert loaded is not None
    assert loaded.decision_id == "d:1"


def test_jsonl_decision_state_store_latest_decision_wins_by_id(tmp_path) -> None:
    store = JsonlDecisionStateStore(tmp_path)
    original = _decision("d:1", question="old")
    updated = original.model_copy(update={"question": "new", "updated_at": _now()})

    store.upsert_decision(original)
    store.upsert_decision(updated)

    decisions = store.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].question == "new"


def test_jsonl_decision_state_store_filters(tmp_path) -> None:
    store = JsonlDecisionStateStore(tmp_path)
    a = _decision("d:1", session_id="s:1", task_id="t:1", work_state_id="ws:1", status=DecisionStatus.OPEN)
    b = _decision("d:2", session_id="s:2", task_id="t:2", work_state_id="ws:2", status=DecisionStatus.DECIDED)
    store.upsert_decision(a)
    store.upsert_decision(b)

    assert [d.decision_id for d in store.list_decisions(session_id="s:1")] == ["d:1"]
    assert [d.decision_id for d in store.list_decisions(task_id="t:2")] == ["d:2"]
    assert [d.decision_id for d in store.list_decisions(work_state_id="ws:1")] == ["d:1"]
    assert [d.decision_id for d in store.list_decisions(statuses=[DecisionStatus.DECIDED])] == ["d:2"]


def test_jsonl_stores_survive_fresh_instance_with_same_path(tmp_path) -> None:
    work_path = tmp_path / "work"
    decision_path = tmp_path / "decision"
    work_store = JsonlWorkStateStore(work_path)
    decision_store = JsonlDecisionStateStore(decision_path)

    work_store.upsert_state(_state("ws:1", title="persisted"))
    decision_store.upsert_decision(_decision("d:1", question="persisted"))

    reloaded_work = JsonlWorkStateStore(work_path)
    reloaded_decision = JsonlDecisionStateStore(decision_path)

    loaded_state = reloaded_work.get_state("ws:1")
    loaded_decision = reloaded_decision.get_decision("d:1")
    assert loaded_state is not None
    assert loaded_state.title == "persisted"
    assert loaded_decision is not None
    assert loaded_decision.question == "persisted"
