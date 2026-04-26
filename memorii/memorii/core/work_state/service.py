"""In-memory work-state lifecycle service."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.work_state.detector import WorkStateDetector
from memorii.core.work_state.models import (
    AgentEventEnvelope,
    WorkStateBinding,
    WorkStateBindingStatus,
    WorkStateDetectionAction,
    WorkStateDetectionDecision,
    WorkStateKind,
    WorkStateRecord,
    WorkStateStatus,
)


class WorkStateService:
    def __init__(self, detector: WorkStateDetector | None = None) -> None:
        self._detector = detector or WorkStateDetector()
        self._states: list[WorkStateRecord] = []
        self._bindings: list[WorkStateBinding] = []

    def ingest_event(self, event: AgentEventEnvelope) -> WorkStateDetectionDecision:
        decision = self._detector.detect(event=event, active_states=self._states)
        work_state_id: str | None = None
        if decision.action == WorkStateDetectionAction.NO_STATE_UPDATE:
            self._upsert_event_binding(event=event, work_state_id=None)
            return decision

        should_commit = bool(event.metadata.get("memorii_commit_state"))
        if should_commit:
            decision = decision.model_copy(update={"action": WorkStateDetectionAction.COMMIT_STATE_UPDATE})

        if decision.action == WorkStateDetectionAction.CREATE_CANDIDATE_STATE:
            created = self._create_state(event=event, decision=decision, status=WorkStateStatus.CANDIDATE)
            work_state_id = created.work_state_id
            self._upsert_event_binding(event=event, work_state_id=work_state_id)
            return decision.model_copy(update={"work_state_id": work_state_id})

        if decision.action == WorkStateDetectionAction.UPDATE_EXISTING_STATE and decision.work_state_id:
            self._update_state(work_state_id=decision.work_state_id, event=event, decision=decision)
            self._upsert_event_binding(event=event, work_state_id=decision.work_state_id)
            return decision

        if decision.action == WorkStateDetectionAction.COMMIT_STATE_UPDATE:
            status = WorkStateStatus.ACTIVE
            if decision.work_state_id:
                self._update_state(work_state_id=decision.work_state_id, event=event, decision=decision, status=status)
                self._upsert_event_binding(event=event, work_state_id=decision.work_state_id)
                return decision
            created = self._create_state(event=event, decision=decision, status=status)
            work_state_id = created.work_state_id
            self._upsert_event_binding(event=event, work_state_id=work_state_id)
            return decision.model_copy(update={"work_state_id": work_state_id})

        self._upsert_event_binding(event=event, work_state_id=None)
        return decision

    def bind_state(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        work_state_id: str | None = None,
        execution_node_id: str | None = None,
        solver_run_id: str | None = None,
        status: WorkStateBindingStatus = WorkStateBindingStatus.ACTIVE,
    ) -> WorkStateBinding:
        timestamp = datetime.now(UTC)
        binding = WorkStateBinding(
            binding_id=f"wsb:{timestamp.timestamp()}:{len(self._bindings)}",
            session_id=session_id,
            task_id=task_id,
            work_state_id=work_state_id,
            execution_node_id=execution_node_id,
            solver_run_id=solver_run_id,
            status=status,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._bindings.append(binding)
        return binding

    def resolve_solver_run_id(
        self,
        *,
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> str | None:
        if task_id is not None:
            task_match = self._latest_active_binding(task_id=task_id)
            if task_match is not None:
                return task_match.solver_run_id
        if session_id is not None:
            session_match = self._latest_active_binding(session_id=session_id)
            if session_match is not None:
                return session_match.solver_run_id
        return None

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

    def _create_state(
        self,
        *,
        event: AgentEventEnvelope,
        decision: WorkStateDetectionDecision,
        status: WorkStateStatus,
    ) -> WorkStateRecord:
        timestamp = event.timestamp
        created = WorkStateRecord(
            work_state_id=f"ws:{decision.kind.value}:{_safe_id(event.event_id)}",
            kind=decision.kind,
            status=status,
            task_id=event.task_id,
            session_id=event.session_id,
            user_id=event.user_id,
            title=decision.title or self._default_title(decision.kind),
            summary=decision.summary or _summary_from_event(event),
            confidence=decision.confidence,
            source_event_ids=[event.event_id],
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._states.append(created)
        return created

    def _update_state(
        self,
        *,
        work_state_id: str,
        event: AgentEventEnvelope,
        decision: WorkStateDetectionDecision,
        status: WorkStateStatus | None = None,
    ) -> None:
        updated: list[WorkStateRecord] = []
        for state in self._states:
            if state.work_state_id != work_state_id:
                updated.append(state)
                continue
            event_ids = list(state.source_event_ids)
            if event.event_id not in event_ids:
                event_ids.append(event.event_id)
            updated.append(
                state.model_copy(
                    update={
                        "summary": decision.summary or _summary_from_event(event),
                        "updated_at": event.timestamp or datetime.now(UTC),
                        "confidence": max(state.confidence, decision.confidence),
                        "source_event_ids": event_ids,
                        "status": status or state.status,
                    }
                )
            )
        self._states = updated

    def _upsert_event_binding(self, *, event: AgentEventEnvelope, work_state_id: str | None) -> None:
        solver_run_id = _metadata_value(event=event, key="solver_run_id")
        execution_node_id = _metadata_value(event=event, key="execution_node_id")
        if solver_run_id is None and execution_node_id is None:
            return

        candidates = [
            binding
            for binding in self._bindings
            if binding.status == WorkStateBindingStatus.ACTIVE
            and (
                (event.task_id is not None and binding.task_id == event.task_id)
                or (event.session_id is not None and binding.session_id == event.session_id)
            )
        ]
        if candidates:
            latest = max(candidates, key=lambda item: item.updated_at)
            updated = latest.model_copy(
                update={
                    "session_id": event.session_id,
                    "task_id": event.task_id,
                    "work_state_id": work_state_id or latest.work_state_id,
                    "solver_run_id": solver_run_id,
                    "execution_node_id": execution_node_id,
                    "updated_at": event.timestamp,
                }
            )
            self._bindings = [updated if binding.binding_id == latest.binding_id else binding for binding in self._bindings]
            return

        self.bind_state(
            session_id=event.session_id,
            task_id=event.task_id,
            work_state_id=work_state_id,
            solver_run_id=solver_run_id,
            execution_node_id=execution_node_id,
        )

    def _latest_active_binding(
        self,
        *,
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> WorkStateBinding | None:
        if task_id is None and session_id is None:
            return None
        candidates = [
            binding
            for binding in self._bindings
            if binding.status == WorkStateBindingStatus.ACTIVE
            and binding.solver_run_id is not None
            and (task_id is None or binding.task_id == task_id)
            and (session_id is None or binding.session_id == session_id)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.updated_at)

    @staticmethod
    def _default_title(kind: WorkStateKind) -> str:
        return kind.value.replace("_", " ").title()


def _summary_from_event(event: AgentEventEnvelope) -> str:
    content = event.content.strip()
    return content[:240]


def _safe_id(event_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ":") else "-" for ch in event_id)


def _metadata_value(*, event: AgentEventEnvelope, key: str) -> str | None:
    value = event.metadata.get(key)
    if value is None:
        return None
    return str(value)
