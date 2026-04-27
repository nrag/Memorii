"""Work-state storage contracts and in-memory implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from memorii.core.work_state.models import (
    WorkStateBinding,
    WorkStateBindingStatus,
    WorkStateEvent,
    WorkStateKind,
    WorkStateRecord,
    WorkStateStatus,
)


class WorkStateStore(Protocol):
    def list_states(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        kinds: list[WorkStateKind] | None = None,
        statuses: list[WorkStateStatus] | None = None,
    ) -> list[WorkStateRecord]: ...

    def get_state(self, work_state_id: str) -> WorkStateRecord | None: ...

    def upsert_state(self, state: WorkStateRecord) -> None: ...

    def list_bindings(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        work_state_id: str | None = None,
        statuses: list[WorkStateBindingStatus] | None = None,
    ) -> list[WorkStateBinding]: ...

    def upsert_binding(self, binding: WorkStateBinding) -> None: ...

    def list_events(self, work_state_id: str) -> list[WorkStateEvent]: ...

    def append_event(self, event: WorkStateEvent) -> None: ...


class InMemoryWorkStateStore:
    def __init__(self) -> None:
        self._states: list[WorkStateRecord] = []
        self._bindings: list[WorkStateBinding] = []
        self._events: list[WorkStateEvent] = []

    def list_states(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        kinds: list[WorkStateKind] | None = None,
        statuses: list[WorkStateStatus] | None = None,
    ) -> list[WorkStateRecord]:
        kind_set = set(kinds) if kinds else None
        status_set = set(statuses) if statuses else None
        return [
            state
            for state in self._states
            if (session_id is None or state.session_id == session_id)
            and (task_id is None or state.task_id == task_id)
            and (user_id is None or state.user_id == user_id)
            and (kind_set is None or state.kind in kind_set)
            and (status_set is None or state.status in status_set)
        ]

    def get_state(self, work_state_id: str) -> WorkStateRecord | None:
        for state in self._states:
            if state.work_state_id == work_state_id:
                return state
        return None

    def upsert_state(self, state: WorkStateRecord) -> None:
        for idx, existing in enumerate(self._states):
            if existing.work_state_id == state.work_state_id:
                self._states[idx] = state
                return
        self._states.append(state)

    def list_bindings(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        work_state_id: str | None = None,
        statuses: list[WorkStateBindingStatus] | None = None,
    ) -> list[WorkStateBinding]:
        status_set = set(statuses) if statuses else None
        return [
            binding
            for binding in self._bindings
            if (session_id is None or binding.session_id == session_id)
            and (task_id is None or binding.task_id == task_id)
            and (work_state_id is None or binding.work_state_id == work_state_id)
            and (status_set is None or binding.status in status_set)
        ]

    def upsert_binding(self, binding: WorkStateBinding) -> None:
        for idx, existing in enumerate(self._bindings):
            if existing.binding_id == binding.binding_id:
                self._bindings[idx] = binding
                return
        self._bindings.append(binding)

    def list_events(self, work_state_id: str) -> list[WorkStateEvent]:
        return [event for event in self._events if event.work_state_id == work_state_id]

    def append_event(self, event: WorkStateEvent) -> None:
        self._events.append(event)


class JsonlWorkStateStore:
    def __init__(self, path: str | Path) -> None:
        self._base_path = Path(path)
        self._states_path = self._base_path / "work_states.jsonl"
        self._bindings_path = self._base_path / "work_state_bindings.jsonl"
        self._events_path = self._base_path / "work_state_events.jsonl"
        self._base_path.mkdir(parents=True, exist_ok=True)

    def list_states(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        kinds: list[WorkStateKind] | None = None,
        statuses: list[WorkStateStatus] | None = None,
    ) -> list[WorkStateRecord]:
        kind_set = set(kinds) if kinds else None
        status_set = set(statuses) if statuses else None
        latest_by_id: dict[str, WorkStateRecord] = {}
        for line in self._iter_jsonl_lines(self._states_path):
            state = WorkStateRecord.model_validate_json(line)
            latest_by_id[state.work_state_id] = state

        return [
            state
            for state in latest_by_id.values()
            if (session_id is None or state.session_id == session_id)
            and (task_id is None or state.task_id == task_id)
            and (user_id is None or state.user_id == user_id)
            and (kind_set is None or state.kind in kind_set)
            and (status_set is None or state.status in status_set)
        ]

    def get_state(self, work_state_id: str) -> WorkStateRecord | None:
        latest: WorkStateRecord | None = None
        for line in self._iter_jsonl_lines(self._states_path):
            state = WorkStateRecord.model_validate_json(line)
            if state.work_state_id == work_state_id:
                latest = state
        return latest

    def upsert_state(self, state: WorkStateRecord) -> None:
        self._append_jsonl(self._states_path, state.model_dump_json())

    def list_bindings(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        work_state_id: str | None = None,
        statuses: list[WorkStateBindingStatus] | None = None,
    ) -> list[WorkStateBinding]:
        status_set = set(statuses) if statuses else None
        latest_by_id: dict[str, WorkStateBinding] = {}
        for line in self._iter_jsonl_lines(self._bindings_path):
            binding = WorkStateBinding.model_validate_json(line)
            latest_by_id[binding.binding_id] = binding

        return [
            binding
            for binding in latest_by_id.values()
            if (session_id is None or binding.session_id == session_id)
            and (task_id is None or binding.task_id == task_id)
            and (work_state_id is None or binding.work_state_id == work_state_id)
            and (status_set is None or binding.status in status_set)
        ]

    def upsert_binding(self, binding: WorkStateBinding) -> None:
        self._append_jsonl(self._bindings_path, binding.model_dump_json())

    def list_events(self, work_state_id: str) -> list[WorkStateEvent]:
        return [
            event
            for line in self._iter_jsonl_lines(self._events_path)
            for event in [WorkStateEvent.model_validate_json(line)]
            if event.work_state_id == work_state_id
        ]

    def append_event(self, event: WorkStateEvent) -> None:
        self._append_jsonl(self._events_path, event.model_dump_json())

    @staticmethod
    def _iter_jsonl_lines(path: Path) -> list[str]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            return [line for line in f if line.strip()]

    @staticmethod
    def _append_jsonl(path: Path, payload: str) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(payload)
            f.write("\n")
