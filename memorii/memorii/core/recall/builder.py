"""Helpers to build structured recall-state bundles."""

from __future__ import annotations

from memorii.core.decision_state.summary import DecisionStateSummary
from memorii.core.recall.models import WorkStateEventSummary, WorkStateSummary
from memorii.core.work_state.models import WorkStateEvent, WorkStateEventType, WorkStateRecord, WorkStateStatus

_STATUS_ORDER = {
    WorkStateStatus.ACTIVE: 0,
    WorkStateStatus.CANDIDATE: 1,
    WorkStateStatus.PAUSED: 2,
    WorkStateStatus.RESOLVED: 3,
    WorkStateStatus.ABANDONED: 4,
}


def summarize_work_states(
    states: list[WorkStateRecord],
    events_by_state_id: dict[str, list[WorkStateEvent]] | None = None,
    decision_summary_by_state_id: dict[str, DecisionStateSummary] | None = None,
    max_events_per_state: int = 3,
) -> list[WorkStateSummary]:
    sorted_states = sorted(
        states,
        key=lambda state: (
            _STATUS_ORDER.get(state.status, 99),
            -state.confidence,
            -state.updated_at.timestamp(),
            state.work_state_id,
        ),
    )
    summaries: list[WorkStateSummary] = []
    for state in sorted_states:
        state_events = list((events_by_state_id or {}).get(state.work_state_id, []))
        newest_first_events = sorted(
            state_events,
            key=lambda event: (-event.created_at.timestamp(), event.event_id),
        )
        recent_events = [
            WorkStateEventSummary(
                event_id=event.event_id,
                work_state_id=event.work_state_id,
                event_type=event.event_type.value,
                content=event.content,
                evidence_ids=list(event.evidence_ids),
                created_at=event.created_at,
            )
            for event in newest_first_events[:max_events_per_state]
        ]
        latest_progress = next(
            (event.content for event in newest_first_events if event.event_type == WorkStateEventType.PROGRESS),
            None,
        )
        latest_outcome = next(
            (event.content for event in newest_first_events if event.event_type == WorkStateEventType.OUTCOME),
            None,
        )

        summaries.append(
            WorkStateSummary(
                work_state_id=state.work_state_id,
                kind=state.kind,
                status=state.status,
                title=state.title,
                summary=state.summary,
                confidence=state.confidence,
                task_id=state.task_id,
                session_id=state.session_id,
                user_id=state.user_id,
                source_event_ids=list(state.source_event_ids),
                recent_events=recent_events,
                latest_progress=latest_progress,
                latest_outcome=latest_outcome,
                decision_state=(decision_summary_by_state_id or {}).get(state.work_state_id),
            )
        )
    return summaries
