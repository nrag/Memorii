from datetime import UTC, datetime

from memorii.core.memory_evolution.execution import (
    ActionEvent,
    ActionEventType,
    ContinuationResolutionStatus,
    WorkStateStatus,
    normalize_work_state_status,
    reduce_work_states,
    resolve_continuation,
)
from memorii.core.memory_evolution.models import ExtractedAction, MemoryScope


def test_explicit_progress_status_beats_resume_event_type() -> None:
    snapshot = reduce_work_states(
        [
            ActionEvent(
                event_id="resume-1",
                event_type=ActionEventType.RESUME,
                target_entity_ids=["branch-b"],
                event_time=datetime(2026, 1, 2, tzinfo=UTC),
                explicit_status=WorkStateStatus.IN_PROGRESS,
                evidence_event_ids=["source-1"],
            )
        ]
    )

    state = snapshot.states[0]
    assert state.status == WorkStateStatus.IN_PROGRESS
    assert state.active is True
    assert snapshot.active_branch_ids == ["branch-b"]


def test_latest_terminal_event_suppresses_prior_progress() -> None:
    start = ActionEvent(
        event_id="start-1",
        event_type=ActionEventType.START,
        target_entity_ids=["branch-a"],
        event_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    blocked = ActionEvent(
        event_id="blocked-1",
        event_type=ActionEventType.BLOCK,
        target_entity_ids=["branch-a"],
        event_time=datetime(2026, 1, 2, tzinfo=UTC),
    )
    snapshot = reduce_work_states([blocked, start])

    assert snapshot.states[0].status == WorkStateStatus.BLOCKED
    assert snapshot.states[0].active is False
    assert snapshot.suppressed_branch_ids == ["branch-a"]


def test_status_normalization_has_one_work_state_vocabulary() -> None:
    assert normalize_work_state_status("in progress") == WorkStateStatus.IN_PROGRESS
    assert normalize_work_state_status("in_progress") == WorkStateStatus.IN_PROGRESS
    assert normalize_work_state_status("resumed") == WorkStateStatus.IN_PROGRESS
    assert normalize_work_state_status("succeeded") == WorkStateStatus.SUCCEEDED
    assert normalize_work_state_status("failed") == WorkStateStatus.FAILED
    assert normalize_work_state_status("unknown model status") == WorkStateStatus.UNKNOWN


def test_continuation_resolution_abstains_when_active_branches_are_equally_plausible() -> None:
    events = [
        ActionEvent(
            event_id="progress-a",
            event_type=ActionEventType.PROGRESS,
            target_entity_ids=["branch-a"],
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
            explicit_status=WorkStateStatus.IN_PROGRESS,
        ),
        ActionEvent(
            event_id="progress-b",
            event_type=ActionEventType.PROGRESS,
            target_entity_ids=["branch-b"],
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
            explicit_status=WorkStateStatus.IN_PROGRESS,
        ),
    ]
    snapshot = reduce_work_states(events)
    extracted = [
        ExtractedAction(
            action_id="progress-a",
            action_type="progress",
            target_entity_ids=["branch-a"],
            status="in_progress",
            timestamp=events[0].event_time,
            extraction_run_id="run",
        ),
        ExtractedAction(
            action_id="progress-b",
            action_type="progress",
            target_entity_ids=["branch-b"],
            status="in_progress",
            timestamp=events[1].event_time,
            extraction_run_id="run",
        ),
    ]

    decision = resolve_continuation(snapshot, extracted)

    assert decision.status == ContinuationResolutionStatus.AMBIGUOUS
    assert decision.branch_id is None
    assert decision.candidate_branch_ids == ["branch-a", "branch-b"]


def test_newer_active_progress_wins_over_older_active_progress() -> None:
    events = [
        ActionEvent(
            event_id="progress-a",
            event_type=ActionEventType.PROGRESS,
            target_entity_ids=["branch-a"],
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
            explicit_status=WorkStateStatus.IN_PROGRESS,
        ),
        ActionEvent(
            event_id="progress-b",
            event_type=ActionEventType.PROGRESS,
            target_entity_ids=["branch-b"],
            event_time=datetime(2026, 1, 3, tzinfo=UTC),
            explicit_status=WorkStateStatus.IN_PROGRESS,
        ),
    ]
    snapshot = reduce_work_states(events)
    extracted = [
        ExtractedAction(
            action_id=event.event_id,
            action_type="progress",
            target_entity_ids=event.target_entity_ids,
            status="in_progress",
            timestamp=event.event_time,
            extraction_run_id="run",
        )
        for event in events
    ]

    decision = resolve_continuation(snapshot, extracted)

    assert decision.status == ContinuationResolutionStatus.RESOLVED
    assert decision.branch_id == "branch-b"


def test_task_context_selects_matching_branch_when_target_is_shared() -> None:
    events = [
        ActionEvent(
            event_id="progress-incident",
            event_type=ActionEventType.PROGRESS,
            target_entity_ids=["shared-fix"],
            task_id="task:incident",
            session_id="session:incident",
            scope_key="task:incident",
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
            explicit_status=WorkStateStatus.IN_PROGRESS,
        ),
        ActionEvent(
            event_id="progress-platform",
            event_type=ActionEventType.PROGRESS,
            target_entity_ids=["shared-fix"],
            task_id="task:platform",
            session_id="session:platform",
            scope_key="task:platform",
            event_time=datetime(2026, 1, 3, tzinfo=UTC),
            explicit_status=WorkStateStatus.IN_PROGRESS,
        ),
    ]
    snapshot = reduce_work_states(events)
    actions = [
        ExtractedAction(
            action_id=event.event_id,
            action_type="progress",
            target_entity_ids=event.target_entity_ids,
            status="in_progress",
            timestamp=event.event_time,
            scope=MemoryScope(task_id=event.task_id, session_id=event.session_id),
            extraction_run_id="run",
        )
        for event in events
    ]

    decision = resolve_continuation(
        snapshot,
        actions,
        requested_task_id="task:incident",
        requested_session_id="session:incident",
        requested_scope_key="task:incident",
        target_entity_ids=["shared-fix"],
    )

    assert decision.status == ContinuationResolutionStatus.RESOLVED
    assert decision.action_event_id == "progress-incident"
