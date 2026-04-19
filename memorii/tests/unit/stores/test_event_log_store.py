from datetime import UTC, datetime

import pytest

from memorii.domain.enums import EventType
from memorii.domain.events import EventRecord
from memorii.stores.event_log import InMemoryEventLogStore


def _event(event_id: str, task_id: str, solver_id: str | None = None) -> EventRecord:
    return EventRecord(
        event_id=event_id,
        event_type=EventType.NODE_ADDED,
        timestamp=datetime.now(UTC),
        task_id=task_id,
        solver_graph_id=solver_id,
        actor_id="system",
        payload={"graph_type": "execution", "entity": {"id": event_id}},
        dedupe_key=event_id,
    )


def test_event_append_and_query() -> None:
    store = InMemoryEventLogStore()
    e1 = _event("e1", "t1")
    e2 = _event("e2", "t1", solver_id="s1")

    assert store.append(e1) is True
    assert store.append(e2) is True

    assert [e.event_id for e in store.list_by_task("t1")] == ["e1", "e2"]
    assert [e.event_id for e in store.list_by_solver_run("s1")] == ["e2"]


def test_event_idempotency_and_collision() -> None:
    store = InMemoryEventLogStore()
    e1 = _event("e1", "t1")
    assert store.append(e1) is True
    assert store.append(e1) is False

    mutated = e1.model_copy(update={"payload": {"graph_type": "execution", "entity": {"id": "different"}}})
    with pytest.raises(ValueError):
        store.append(mutated)


def test_event_query_is_deterministically_ordered() -> None:
    store = InMemoryEventLogStore()
    early = EventRecord(
        event_id="a",
        event_type=EventType.NODE_ADDED,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        task_id="t-order",
        actor_id="system",
        payload={},
        dedupe_key="a",
    )
    late = EventRecord(
        event_id="b",
        event_type=EventType.NODE_ADDED,
        timestamp=datetime(2026, 1, 2, tzinfo=UTC),
        task_id="t-order",
        actor_id="system",
        payload={},
        dedupe_key="b",
    )

    store.append(late)
    store.append(early)

    assert [event.event_id for event in store.list_by_task("t-order")] == ["a", "b"]
