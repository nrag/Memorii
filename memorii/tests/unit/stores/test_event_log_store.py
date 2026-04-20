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
        solver_run_id=solver_id,
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


def test_event_record_accepts_legacy_solver_graph_id_alias() -> None:
    event = EventRecord.model_validate(
        {
            "event_id": "legacy-1",
            "event_type": "NODE_ADDED",
            "timestamp": datetime.now(UTC),
            "task_id": "t1",
            "solver_graph_id": "solver-legacy",
            "actor_id": "system",
            "payload": {"graph_type": "solver", "entity": {"id": "n1"}},
            "dedupe_key": "legacy-1",
        }
    )

    dumped = event.model_dump(mode="json")
    assert event.solver_run_id == "solver-legacy"
    assert dumped["solver_run_id"] == "solver-legacy"
    assert "solver_graph_id" not in dumped
