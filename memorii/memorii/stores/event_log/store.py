"""In-memory immutable event log with idempotent append."""

from collections import defaultdict

from memorii.domain.events import EventRecord
from memorii.stores.base.interfaces import EventLogStore


class InMemoryEventLogStore(EventLogStore):
    def __init__(self) -> None:
        self._events_in_order: list[EventRecord] = []
        self._by_id: dict[str, EventRecord] = {}
        self._by_task: dict[str, list[EventRecord]] = defaultdict(list)
        self._by_solver: dict[str, list[EventRecord]] = defaultdict(list)

    def append(self, event: EventRecord) -> bool:
        existing: EventRecord | None = self._by_id.get(event.event_id)
        if existing is not None:
            if existing.model_dump(mode="json") != event.model_dump(mode="json"):
                raise ValueError(f"Event id collision with mismatched payload: {event.event_id}")
            return False

        self._events_in_order.append(event)
        self._by_id[event.event_id] = event
        self._by_task[event.task_id].append(event)
        if event.solver_graph_id is not None:
            self._by_solver[event.solver_graph_id].append(event)
        return True

    def append_many(self, events: list[EventRecord]) -> list[bool]:
        return [self.append(event) for event in events]

    def get_by_event_id(self, event_id: str) -> EventRecord | None:
        return self._by_id.get(event_id)

    def list_by_task(self, task_id: str) -> list[EventRecord]:
        return list(self._by_task.get(task_id, []))

    def list_by_solver_run(self, solver_run_id: str) -> list[EventRecord]:
        return list(self._by_solver.get(solver_run_id, []))
