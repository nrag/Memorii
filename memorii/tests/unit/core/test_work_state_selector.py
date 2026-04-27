from memorii.core.work_state.models import WorkStateKind
from memorii.core.work_state.selector import WorkStateSelector
from memorii.core.work_state.service import WorkStateService


def test_select_recall_work_states_prefers_task_scope() -> None:
    service = WorkStateService()
    task_state = service.open_or_resume_work(title="Task", task_id="task:1", kind=WorkStateKind.TASK_EXECUTION)
    service.open_or_resume_work(title="Session", session_id="session:1", kind=WorkStateKind.RESEARCH)

    selected = WorkStateSelector(service).select_recall_work_states(
        task_id="task:1",
        session_id="session:1",
        user_id=None,
    )

    assert [state.work_state_id for state in selected] == [task_state.work_state_id]


def test_select_recall_work_states_returns_empty_without_service() -> None:
    selected = WorkStateSelector(None).select_recall_work_states(
        task_id="task:missing",
        session_id=None,
        user_id=None,
    )
    assert selected == []
