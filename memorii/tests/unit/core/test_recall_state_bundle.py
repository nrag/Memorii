from datetime import UTC, datetime, timedelta

from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.work_state.models import WorkStateKind, WorkStateRecord, WorkStateStatus
from memorii.core.work_state.service import WorkStateService


def _state(
    *,
    work_state_id: str,
    status: WorkStateStatus,
    confidence: float,
    title: str,
    summary: str,
    task_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    updated_at: datetime | None = None,
) -> WorkStateRecord:
    now = updated_at or datetime.now(UTC)
    return WorkStateRecord(
        work_state_id=work_state_id,
        kind=WorkStateKind.TASK_EXECUTION,
        status=status,
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        title=title,
        summary=summary,
        confidence=confidence,
        source_event_ids=[f"event:{work_state_id}"],
        created_at=now,
        updated_at=now,
    )


def test_prefetch_without_work_state_service_remains_backward_compatible() -> None:
    provider = ProviderMemoryService()
    context = provider.prefetch("what changed", task_id="task:none")

    assert "Current work state" not in context
    bundle = provider.last_recall_bundle()
    assert bundle is not None
    assert bundle.work_states == []


def test_prefetch_with_work_state_service_and_no_matching_states_has_no_section() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser changes",
        session_id="session:other",
        task_id="task:other",
        user_id="user:other",
    )
    context = provider.prefetch("continue", session_id="session:1", task_id="task:1", user_id="user:1")

    assert "Current work state" not in context
    bundle = provider.last_recall_bundle()
    assert bundle is not None
    assert bundle.work_states == []


def test_prefetch_includes_matching_candidate_task_state() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser updates and write tests",
        session_id="session:2",
        task_id="task:2",
        user_id="user:2",
    )
    context = provider.prefetch("continue parser work", session_id="session:2", task_id="task:2", user_id="user:2")

    assert "Current work state" in context
    assert "Task execution in progress" in context
    assert "implement parser updates" in context
    bundle = provider.last_recall_bundle()
    assert bundle is not None
    assert len(bundle.work_states) == 1


def test_prefetch_excludes_resolved_and_abandoned_states() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    now = datetime.now(UTC)
    work_state_service._states.extend(  # noqa: SLF001
        [
            _state(
                work_state_id="ws:active",
                status=WorkStateStatus.ACTIVE,
                confidence=0.7,
                title="Active work",
                summary="still in progress",
                task_id="task:3",
                session_id="session:3",
                updated_at=now,
            ),
            _state(
                work_state_id="ws:resolved",
                status=WorkStateStatus.RESOLVED,
                confidence=0.95,
                title="Resolved work",
                summary="already done",
                task_id="task:3",
                session_id="session:3",
                updated_at=now - timedelta(minutes=1),
            ),
            _state(
                work_state_id="ws:abandoned",
                status=WorkStateStatus.ABANDONED,
                confidence=0.9,
                title="Abandoned work",
                summary="not relevant",
                task_id="task:3",
                session_id="session:3",
                updated_at=now - timedelta(minutes=2),
            ),
        ]
    )

    context = provider.prefetch("continue", task_id="task:3", session_id="session:3")
    assert "Current work state" in context
    assert "Active work" in context
    assert "Resolved work" not in context
    assert "Abandoned work" not in context

    bundle = provider.last_recall_bundle()
    assert bundle is not None
    assert [state.work_state_id for state in bundle.work_states] == ["ws:active"]


def test_work_states_are_sorted_deterministically() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    now = datetime.now(UTC)
    work_state_service._states.extend(  # noqa: SLF001
        [
            _state(
                work_state_id="ws:candidate-high",
                status=WorkStateStatus.CANDIDATE,
                confidence=0.9,
                title="Candidate high",
                summary="candidate",
                task_id="task:4",
                updated_at=now - timedelta(seconds=20),
            ),
            _state(
                work_state_id="ws:active-low",
                status=WorkStateStatus.ACTIVE,
                confidence=0.6,
                title="Active low",
                summary="active low",
                task_id="task:4",
                updated_at=now - timedelta(seconds=30),
            ),
            _state(
                work_state_id="ws:active-high",
                status=WorkStateStatus.ACTIVE,
                confidence=0.95,
                title="Active high",
                summary="active high",
                task_id="task:4",
                updated_at=now - timedelta(seconds=10),
            ),
            _state(
                work_state_id="ws:paused-high",
                status=WorkStateStatus.PAUSED,
                confidence=0.99,
                title="Paused high",
                summary="paused",
                task_id="task:4",
                updated_at=now,
            ),
        ]
    )

    provider.prefetch("continue", task_id="task:4")
    bundle = provider.last_recall_bundle()
    assert bundle is not None
    assert [state.work_state_id for state in bundle.work_states] == [
        "ws:active-high",
        "ws:active-low",
        "ws:candidate-high",
        "ws:paused-high",
    ]


def test_last_recall_bundle_trace_is_populated() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement and update parser",
        session_id="session:5",
        task_id="task:5",
        user_id="user:5",
    )

    provider.prefetch("continue", task_id="task:5")
    bundle = provider.last_recall_bundle()
    assert bundle is not None
    assert bundle.trace["work_state_count"] == 1
    assert bundle.trace["work_state_ids"]
    assert bundle.trace["included_statuses"] == ["candidate"]
