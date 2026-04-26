from memorii.core.work_state.models import WorkStateBindingStatus
from memorii.core.work_state.service import WorkStateService


def test_bind_and_resolve_by_task() -> None:
    service = WorkStateService()
    service.bind_state(task_id="task:bind:1", solver_run_id="solver:task:1")

    assert service.resolve_solver_run_id(task_id="task:bind:1") == "solver:task:1"


def test_bind_and_resolve_by_session() -> None:
    service = WorkStateService()
    service.bind_state(session_id="session:bind:1", solver_run_id="solver:session:1")

    assert service.resolve_solver_run_id(session_id="session:bind:1") == "solver:session:1"


def test_task_resolution_wins_over_session_resolution() -> None:
    service = WorkStateService()
    service.bind_state(session_id="session:bind:2", solver_run_id="solver:session:2")
    service.bind_state(task_id="task:bind:2", solver_run_id="solver:task:2")

    assert (
        service.resolve_solver_run_id(task_id="task:bind:2", session_id="session:bind:2")
        == "solver:task:2"
    )


def test_latest_active_binding_wins() -> None:
    service = WorkStateService()
    service.bind_state(task_id="task:bind:3", solver_run_id="solver:task:3:old")
    service.bind_state(task_id="task:bind:3", solver_run_id="solver:task:3:new")

    assert service.resolve_solver_run_id(task_id="task:bind:3") == "solver:task:3:new"


def test_inactive_bindings_ignored() -> None:
    service = WorkStateService()
    for status in (
        WorkStateBindingStatus.PAUSED,
        WorkStateBindingStatus.RESOLVED,
        WorkStateBindingStatus.ABANDONED,
    ):
        service.bind_state(task_id=f"task:bind:{status.value}", solver_run_id=f"solver:{status.value}", status=status)

    assert service.resolve_solver_run_id(task_id="task:bind:paused") is None
    assert service.resolve_solver_run_id(task_id="task:bind:resolved") is None
    assert service.resolve_solver_run_id(task_id="task:bind:abandoned") is None
