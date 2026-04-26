"""In-memory work-state lifecycle service."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.work_state.detector import WorkStateDetector
from memorii.core.work_state.models import (
    AgentEventEnvelope,
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

    def ingest_event(self, event: AgentEventEnvelope) -> WorkStateDetectionDecision:
        decision = self._detector.detect(event=event, active_states=self._states)
        if decision.action == WorkStateDetectionAction.NO_STATE_UPDATE:
            return decision

        should_commit = bool(event.metadata.get("memorii_commit_state"))
        if should_commit:
            decision = decision.model_copy(update={"action": WorkStateDetectionAction.COMMIT_STATE_UPDATE})

        if decision.action == WorkStateDetectionAction.CREATE_CANDIDATE_STATE:
            created = self._create_state(event=event, decision=decision, status=WorkStateStatus.CANDIDATE)
            return decision.model_copy(update={"work_state_id": created.work_state_id})

        if decision.action == WorkStateDetectionAction.UPDATE_EXISTING_STATE and decision.work_state_id:
            self._update_state(work_state_id=decision.work_state_id, event=event, decision=decision)
            return decision

        if decision.action == WorkStateDetectionAction.COMMIT_STATE_UPDATE:
            status = WorkStateStatus.ACTIVE
            if decision.work_state_id:
                self._update_state(work_state_id=decision.work_state_id, event=event, decision=decision, status=status)
                return decision
            created = self._create_state(event=event, decision=decision, status=status)
            return decision.model_copy(update={"work_state_id": created.work_state_id})

        return decision

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

    @staticmethod
    def _default_title(kind: WorkStateKind) -> str:
        return kind.value.replace("_", " ").title()


def _summary_from_event(event: AgentEventEnvelope) -> str:
    content = event.content.strip()
    return content[:240]


def _safe_id(event_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ":") else "-" for ch in event_id)
