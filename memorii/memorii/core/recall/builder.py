"""Helpers to build structured recall-state bundles."""

from __future__ import annotations

from memorii.core.recall.models import WorkStateSummary
from memorii.core.work_state.models import WorkStateRecord, WorkStateStatus

_STATUS_ORDER = {
    WorkStateStatus.ACTIVE: 0,
    WorkStateStatus.CANDIDATE: 1,
    WorkStateStatus.PAUSED: 2,
    WorkStateStatus.RESOLVED: 3,
    WorkStateStatus.ABANDONED: 4,
}


def summarize_work_states(states: list[WorkStateRecord]) -> list[WorkStateSummary]:
    sorted_states = sorted(
        states,
        key=lambda state: (
            _STATUS_ORDER.get(state.status, 99),
            -state.confidence,
            -state.updated_at.timestamp(),
            state.work_state_id,
        ),
    )
    return [
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
        )
        for state in sorted_states
    ]
