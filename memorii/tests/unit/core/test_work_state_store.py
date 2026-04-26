from datetime import UTC, datetime

from memorii.core.work_state.models import (
    WorkStateBinding,
    WorkStateBindingStatus,
    WorkStateEvent,
    WorkStateEventType,
    WorkStateKind,
    WorkStateRecord,
    WorkStateStatus,
)
from memorii.core.work_state.service import WorkStateService
from memorii.core.work_state.store import InMemoryWorkStateStore


def _state(
    work_state_id: str,
    *,
    session_id: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
    kind: WorkStateKind = WorkStateKind.TASK_EXECUTION,
    status: WorkStateStatus = WorkStateStatus.ACTIVE,
    summary: str = "summary",
) -> WorkStateRecord:
    timestamp = datetime.now(UTC)
    return WorkStateRecord(
        work_state_id=work_state_id,
        kind=kind,
        status=status,
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        title="title",
        summary=summary,
        confidence=1.0,
        source_event_ids=[],
        created_at=timestamp,
        updated_at=timestamp,
    )


def _binding(
    binding_id: str,
    *,
    session_id: str | None = None,
    task_id: str | None = None,
    work_state_id: str | None = None,
    status: WorkStateBindingStatus = WorkStateBindingStatus.ACTIVE,
) -> WorkStateBinding:
    timestamp = datetime.now(UTC)
    return WorkStateBinding(
        binding_id=binding_id,
        session_id=session_id,
        task_id=task_id,
        work_state_id=work_state_id,
        solver_run_id="solver:1",
        execution_node_id="exec:1",
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_in_memory_store_upserts_state() -> None:
    store = InMemoryWorkStateStore()
    original = _state("ws:1", summary="summary")
    updated = original.model_copy(update={"summary": "updated"})

    store.upsert_state(original)
    store.upsert_state(updated)

    assert store.get_state("ws:1") is not None
    assert store.get_state("ws:1").summary == "updated"
    assert len(store.list_states()) == 1


def test_list_states_filters() -> None:
    store = InMemoryWorkStateStore()
    store.upsert_state(_state("ws:a", session_id="s:1", task_id="t:1", user_id="u:1"))
    store.upsert_state(
        _state(
            "ws:b",
            session_id="s:2",
            task_id="t:2",
            user_id="u:2",
            kind=WorkStateKind.INVESTIGATION,
            status=WorkStateStatus.CANDIDATE,
        )
    )

    assert [state.work_state_id for state in store.list_states(session_id="s:1")] == ["ws:a"]
    assert [state.work_state_id for state in store.list_states(task_id="t:2")] == ["ws:b"]
    assert [state.work_state_id for state in store.list_states(user_id="u:1")] == ["ws:a"]
    assert [
        state.work_state_id for state in store.list_states(kinds=[WorkStateKind.INVESTIGATION])
    ] == ["ws:b"]
    assert [
        state.work_state_id for state in store.list_states(statuses=[WorkStateStatus.CANDIDATE])
    ] == ["ws:b"]


def test_upsert_binding_replaces_by_binding_id() -> None:
    store = InMemoryWorkStateStore()
    first = _binding("b:1", task_id="t:1")
    second = first.model_copy(update={"task_id": "t:2"})

    store.upsert_binding(first)
    store.upsert_binding(second)

    bindings = store.list_bindings()
    assert len(bindings) == 1
    assert bindings[0].task_id == "t:2"


def test_list_bindings_filters() -> None:
    store = InMemoryWorkStateStore()
    store.upsert_binding(_binding("b:a", session_id="s:1", task_id="t:1", work_state_id="ws:1"))
    store.upsert_binding(
        _binding(
            "b:b",
            session_id="s:2",
            task_id="t:2",
            work_state_id="ws:2",
            status=WorkStateBindingStatus.PAUSED,
        )
    )

    assert [binding.binding_id for binding in store.list_bindings(session_id="s:1")] == ["b:a"]
    assert [binding.binding_id for binding in store.list_bindings(task_id="t:2")] == ["b:b"]
    assert [binding.binding_id for binding in store.list_bindings(work_state_id="ws:1")] == ["b:a"]
    assert [
        binding.binding_id for binding in store.list_bindings(statuses=[WorkStateBindingStatus.PAUSED])
    ] == ["b:b"]


def test_append_and_list_events() -> None:
    store = InMemoryWorkStateStore()
    first = WorkStateEvent(
        event_id="wse:1",
        work_state_id="ws:1",
        event_type=WorkStateEventType.PROGRESS,
        content="progress",
        evidence_ids=["e:1"],
        created_at=datetime.now(UTC),
    )
    second = WorkStateEvent(
        event_id="wse:2",
        work_state_id="ws:2",
        event_type=WorkStateEventType.OUTCOME,
        content="outcome",
        evidence_ids=["e:2"],
        created_at=datetime.now(UTC),
    )

    store.append_event(first)
    store.append_event(second)

    assert [event.event_id for event in store.list_events("ws:1")] == ["wse:1"]


def test_work_state_service_uses_injected_store() -> None:
    store = InMemoryWorkStateStore()
    service = WorkStateService(store=store)

    state = service.open_or_resume_work(title="Implement parser", task_id="task:store")

    assert store.get_state(state.work_state_id) is not None
