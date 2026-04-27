"""Decision-state storage contracts and in-memory implementation."""

from __future__ import annotations

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
