from datetime import UTC, datetime, timedelta

from memorii.core.recall.builder import summarize_work_states
from memorii.core.work_state.models import WorkStateEvent, WorkStateEventType, WorkStateKind, WorkStateRecord, WorkStateStatus


def _state(work_state_id: str) -> WorkStateRecord:
    now = datetime.now(UTC)
    return WorkStateRecord(
        work_state_id=work_state_id,
        kind=WorkStateKind.TASK_EXECUTION,
        status=WorkStateStatus.ACTIVE,
        title="Test state",
        summary="Test summary",
        confidence=1.0,
        task_id="task:test",
        source_event_ids=[],
        created_at=now,
        updated_at=now,
    )


def test_summarize_work_states_backward_compatible_without_events() -> None:
    summaries = summarize_work_states([_state("ws:no-events")])

    assert len(summaries) == 1
    assert summaries[0].recent_events == []
    assert summaries[0].latest_progress is None
    assert summaries[0].latest_outcome is None


def test_summarize_work_states_respects_max_events_per_state() -> None:
    base_time = datetime.now(UTC)
    state = _state("ws:max-events")
    events = [
        WorkStateEvent(
            event_id=f"wse:{index}",
            work_state_id=state.work_state_id,
            event_type=WorkStateEventType.PROGRESS,
            content=f"progress {index}",
            evidence_ids=[],
            created_at=base_time + timedelta(seconds=index),
        )
        for index in range(5)
    ]

    summaries = summarize_work_states(
        [state],
        events_by_state_id={state.work_state_id: events},
        max_events_per_state=3,
    )

    assert len(summaries[0].recent_events) == 3
    assert [event.event_id for event in summaries[0].recent_events] == ["wse:4", "wse:3", "wse:2"]
