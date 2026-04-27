"""Decision-state storage contracts and in-memory implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from memorii.core.decision_state.models import DecisionState, DecisionStatus


class DecisionStateStore(Protocol):
    def get_decision(self, decision_id: str) -> DecisionState | None: ...

    def upsert_decision(self, decision: DecisionState) -> None: ...

    def list_decisions(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        work_state_id: str | None = None,
        statuses: list[DecisionStatus] | None = None,
    ) -> list[DecisionState]: ...


class InMemoryDecisionStateStore:
    def __init__(self) -> None:
        self._decisions: list[DecisionState] = []

    def get_decision(self, decision_id: str) -> DecisionState | None:
        for decision in self._decisions:
            if decision.decision_id == decision_id:
                return decision
        return None

    def upsert_decision(self, decision: DecisionState) -> None:
        for idx, existing in enumerate(self._decisions):
            if existing.decision_id == decision.decision_id:
                self._decisions[idx] = decision
                return
        self._decisions.append(decision)

    def list_decisions(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        work_state_id: str | None = None,
        statuses: list[DecisionStatus] | None = None,
    ) -> list[DecisionState]:
        status_set = set(statuses) if statuses else None
        return [
            decision
            for decision in self._decisions
            if (session_id is None or decision.session_id == session_id)
            and (task_id is None or decision.task_id == task_id)
            and (work_state_id is None or decision.work_state_id == work_state_id)
            and (status_set is None or decision.status in status_set)
        ]


class JsonlDecisionStateStore:
    def __init__(self, path: str | Path) -> None:
        self._base_path = Path(path)
        self._decisions_path = self._base_path / "decisions.jsonl"
        self._base_path.mkdir(parents=True, exist_ok=True)

    def get_decision(self, decision_id: str) -> DecisionState | None:
        latest: DecisionState | None = None
        for line in self._iter_jsonl_lines(self._decisions_path):
            decision = DecisionState.model_validate_json(line)
            if decision.decision_id == decision_id:
                latest = decision
        return latest

    def upsert_decision(self, decision: DecisionState) -> None:
        self._append_jsonl(self._decisions_path, decision.model_dump_json())

    def list_decisions(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        work_state_id: str | None = None,
        statuses: list[DecisionStatus] | None = None,
    ) -> list[DecisionState]:
        status_set = set(statuses) if statuses else None
        latest_by_id: dict[str, DecisionState] = {}
        for line in self._iter_jsonl_lines(self._decisions_path):
            decision = DecisionState.model_validate_json(line)
            latest_by_id[decision.decision_id] = decision
        return [
            decision
            for decision in latest_by_id.values()
            if (session_id is None or decision.session_id == session_id)
            and (task_id is None or decision.task_id == task_id)
            and (work_state_id is None or decision.work_state_id == work_state_id)
            and (status_set is None or decision.status in status_set)
        ]

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
