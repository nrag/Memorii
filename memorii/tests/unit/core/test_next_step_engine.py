from datetime import UTC, datetime

from memorii.core.next_step import NextStepEngine, NextStepRequest
from memorii.core.solver import SolverFrontierPlanner
from memorii.core.work_state.models import WorkStateKind
from memorii.core.work_state.service import WorkStateService
from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import CommitStatus, SolverCreatedBy, SolverNodeStatus, SolverNodeType
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion
from memorii.stores.overlays import InMemoryOverlayStore
from memorii.stores.solver_graph import InMemorySolverGraphStore

NOW = datetime.now(UTC)


def _make_node(node_id: str, *, content: dict[str, object]) -> SolverNode:
    return SolverNode(
        id=node_id,
        type=SolverNodeType.ACTION,
        content=content,
        metadata=SolverNodeMetadata(
            created_at=NOW,
            created_by=SolverCreatedBy.SYSTEM,
            candidate_state=CommitStatus.COMMITTED,
        ),
    )


def _overlay(node_id: str, *, status: SolverNodeStatus = SolverNodeStatus.NEEDS_TEST) -> SolverNodeOverlay:
    return SolverNodeOverlay(
        node_id=node_id,
        belief=0.5,
        status=status,
        frontier_priority=1.0,
        is_frontier=True,
        updated_at=NOW,
    )


def _append_overlay(store: InMemoryOverlayStore, solver_run_id: str, overlays: list[SolverNodeOverlay]) -> None:
    store.append_overlay_version(
        SolverOverlayVersion(
            version_id=f"ov:{solver_run_id}:{len(store.list_versions(solver_run_id))}",
            solver_run_id=solver_run_id,
            created_at=NOW,
            committed=True,
            node_overlays=overlays,
        )
    )


def test_no_work_state_returns_ask_user() -> None:
    result = NextStepEngine().get_next_step(NextStepRequest(task_id="task:none"))
    assert result.next_step["action_type"] == "ask_user"
    assert result.planner_reason == "no_solver_run_resolved"


def test_task_work_state_returns_continue_task() -> None:
    work_state_service = WorkStateService()
    work_state = work_state_service.open_or_resume_work(title="Task", task_id="task:a", kind=WorkStateKind.TASK_EXECUTION)
    result = NextStepEngine(work_state_service=work_state_service).get_next_step(NextStepRequest(task_id="task:a"))
    assert result.next_step["action_type"] == "continue_task"
    assert result.based_on_work_state_id == work_state.work_state_id


def test_investigation_work_state_returns_inspect_failure() -> None:
    work_state_service = WorkStateService()
    work_state_service.open_or_resume_work(title="Investigate", task_id="task:b", kind=WorkStateKind.INVESTIGATION)
    result = NextStepEngine(work_state_service=work_state_service).get_next_step(NextStepRequest(task_id="task:b"))
    assert result.next_step["action_type"] == "inspect_failure"


def test_explicit_solver_run_id_uses_frontier_planner() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_store.create_solver_run("solver:explicit", "exec-1")
    solver_store.upsert_node("solver:explicit", _make_node("node-1", content={"next_best_test": "run it"}))
    _append_overlay(overlay_store, "solver:explicit", [_overlay("node-1")])
    result = NextStepEngine(
        solver_frontier_planner=SolverFrontierPlanner(),
        solver_store=solver_store,
        overlay_store=overlay_store,
    ).get_next_step(NextStepRequest(solver_run_id="solver:explicit"))
    assert result.planner_used is True
    assert result.solver_run_resolution_source == "explicit"


def test_task_binding_resolves_solver_run_id() -> None:
    work_state_service = WorkStateService()
    work_state_service.bind_state(task_id="task:t", solver_run_id="solver:task-bound")
    result = NextStepEngine(work_state_service=work_state_service).get_next_step(NextStepRequest(task_id="task:t"))
    assert result.resolved_solver_run_id == "solver:task-bound"
    assert result.solver_run_resolution_source == "task_binding"


def test_session_binding_resolves_solver_run_id() -> None:
    work_state_service = WorkStateService()
    work_state_service.bind_state(session_id="session:s", solver_run_id="solver:session-bound")
    result = NextStepEngine(work_state_service=work_state_service).get_next_step(NextStepRequest(session_id="session:s"))
    assert result.resolved_solver_run_id == "solver:session-bound"
    assert result.solver_run_resolution_source == "session_binding"


def test_missing_planner_dependencies_falls_back() -> None:
    result = NextStepEngine().get_next_step(NextStepRequest(solver_run_id="solver:missing"))
    assert result.planner_used is False
    assert result.planner_reason == "planner_not_configured"


def test_no_frontier_falls_back() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_store.create_solver_run("solver:nf", "exec-1")
    result = NextStepEngine(
        solver_frontier_planner=SolverFrontierPlanner(),
        solver_store=solver_store,
        overlay_store=overlay_store,
    ).get_next_step(NextStepRequest(solver_run_id="solver:nf"))
    assert result.planner_used is False
    assert result.planner_reason == "no_frontier_found"


def test_structured_frontier_action_maps_all_fields() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_store.create_solver_run("solver:structured", "exec-1")
    solver_store.upsert_node(
        "solver:structured",
        _make_node(
            "node:structured",
            content={
                "next_test_action": {
                    "action_type": "call_tool",
                    "description": "Run tool",
                    "expected_evidence": "tool output",
                    "success_condition": "status=ok",
                    "failure_condition": "status=error",
                    "required_tool": "memorii_get_state_summary",
                    "target_ref": "task:1",
                }
            },
        ),
    )
    _append_overlay(overlay_store, "solver:structured", [_overlay("node:structured")])
    result = NextStepEngine(
        solver_frontier_planner=SolverFrontierPlanner(),
        solver_store=solver_store,
        overlay_store=overlay_store,
    ).get_next_step(NextStepRequest(solver_run_id="solver:structured"))
    assert result.next_step["action_type"] == "call_tool"
    assert result.next_step["expected_evidence"] == "tool output"
    assert result.next_step["success_condition"] == "status=ok"
    assert result.next_step["failure_condition"] == "status=error"
    assert result.next_step["required_tool"] == "memorii_get_state_summary"
    assert result.next_step["target_ref"] == "task:1"


def test_legacy_frontier_action_maps_run_test() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_store.create_solver_run("solver:legacy", "exec-1")
    solver_store.upsert_node("solver:legacy", _make_node("node:legacy", content={"next_best_test": "rerun tests"}))
    _append_overlay(overlay_store, "solver:legacy", [_overlay("node:legacy")])
    result = NextStepEngine(
        solver_frontier_planner=SolverFrontierPlanner(),
        solver_store=solver_store,
        overlay_store=overlay_store,
    ).get_next_step(NextStepRequest(solver_run_id="solver:legacy"))
    assert result.next_step["action_type"] == "run_test"
    assert result.next_step["description"] == "rerun tests"


def test_frontier_without_action_maps_inspect_frontier() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_store.create_solver_run("solver:inspect", "exec-1")
    solver_store.upsert_node("solver:inspect", _make_node("node:inspect", content={}))
    _append_overlay(overlay_store, "solver:inspect", [_overlay("node:inspect")])
    result = NextStepEngine(
        solver_frontier_planner=SolverFrontierPlanner(),
        solver_store=solver_store,
        overlay_store=overlay_store,
    ).get_next_step(NextStepRequest(solver_run_id="solver:inspect"))
    assert result.next_step["action_type"] == "inspect_frontier"
