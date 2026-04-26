from datetime import UTC, datetime

from memorii.core.solver import SolverFrontierPlanner
from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import CommitStatus, SolverCreatedBy, SolverNodeStatus, SolverNodeType
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.work_state.models import WorkStateKind, WorkStateStatus
from memorii.core.work_state.service import WorkStateService
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


def _overlay(
    node_id: str,
    *,
    status: SolverNodeStatus = SolverNodeStatus.NEEDS_TEST,
    priority: float = 1.0,
    is_frontier: bool = True,
) -> SolverNodeOverlay:
    return SolverNodeOverlay(
        node_id=node_id,
        belief=0.5,
        status=status,
        frontier_priority=priority,
        is_frontier=is_frontier,
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


def test_get_tool_schemas_includes_state_summary_and_next_step() -> None:
    provider = ProviderMemoryService()

    schemas = provider.get_tool_schemas()
    tool_names = {schema["name"] for schema in schemas}

    assert "memorii_get_state_summary" in tool_names
    assert "memorii_get_next_step" in tool_names
    assert "memorii_open_or_resume_work" in tool_names

    next_step_schema = next(schema for schema in schemas if schema["name"] == "memorii_get_next_step")
    properties = next_step_schema["input_schema"]["properties"]
    assert "solver_run_id" in properties
    open_or_resume_schema = next(schema for schema in schemas if schema["name"] == "memorii_open_or_resume_work")
    assert open_or_resume_schema["input_schema"]["required"] == ["title"]
    assert "kind" in open_or_resume_schema["input_schema"]["properties"]


def test_handle_tool_call_unknown_tool_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("not_a_tool", {})

    assert result.ok is False
    assert "not_a_tool" in (result.error or "")


def test_handle_tool_call_validation_error_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": 123})

    assert result.ok is False
    assert "Validation error" in (result.error or "")


def test_get_state_summary_without_work_state_service_returns_empty() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:none"})

    assert result.ok is True
    assert result.result["state_count"] == 0
    assert result.result["work_states"] == []


def test_open_or_resume_without_work_state_service_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Resume parser task", "task_id": "task:none"},
    )

    assert result.ok is False
    assert result.error == "work_state_service_not_configured"


def test_open_or_resume_creates_active_state() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Implement parser updates", "kind": "task_execution", "task_id": "task:open:1"},
    )

    assert result.ok is True
    assert result.result["work_state"]["status"] == "active"
    states = work_state_service.list_states(task_id="task:open:1")
    assert len(states) == 1
    assert states[0].status == WorkStateStatus.ACTIVE


def test_open_or_resume_resumes_existing_task_state_without_duplicate() -> None:
    work_state_service = WorkStateService()
    existing = work_state_service.open_or_resume_work(
        title="Old title",
        summary="Old summary",
        kind=WorkStateKind.TASK_EXECUTION,
        task_id="task:resume:1",
    )
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {
            "title": "New title",
            "summary": "New summary",
            "kind": "task_execution",
            "task_id": "task:resume:1",
        },
    )

    assert result.ok is True
    assert result.result["work_state"]["work_state_id"] == existing.work_state_id
    assert result.result["work_state"]["title"] == "New title"
    assert result.result["work_state"]["summary"] == "New summary"
    states = work_state_service.list_states(task_id="task:resume:1")
    assert len(states) == 1


def test_open_or_resume_explicit_work_state_id_updates_exact_state() -> None:
    work_state_service = WorkStateService()
    target = work_state_service.open_or_resume_work(
        title="Target",
        kind=WorkStateKind.INVESTIGATION,
        task_id="task:exact:original",
    )
    work_state_service.open_or_resume_work(
        title="Other",
        kind=WorkStateKind.INVESTIGATION,
        task_id="task:exact:other",
    )
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {
            "title": "Updated target",
            "summary": "Updated target summary",
            "kind": "investigation",
            "task_id": "task:exact:new",
            "work_state_id": target.work_state_id,
        },
    )

    assert result.ok is True
    assert result.result["work_state"]["work_state_id"] == target.work_state_id
    assert result.result["work_state"]["task_id"] == "task:exact:new"


def test_open_or_resume_creates_binding_when_solver_run_supplied() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {
            "title": "Bound task",
            "task_id": "task:binding:tool",
            "solver_run_id": "solver:binding:tool",
        },
    )

    assert result.ok is True
    assert result.result["binding"] is not None
    assert work_state_service.resolve_solver_run_id(task_id="task:binding:tool") == "solver:binding:tool"


def test_open_or_resume_binding_used_by_next_step_planner() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:open-resume-next-step"
    task_id = "task:open-resume-next-step"
    node_id = "node:open-resume-next-step"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={"next_best_test": "run planner via binding"}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])

    open_result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Open + bind", "task_id": task_id, "solver_run_id": solver_run_id},
    )
    assert open_result.ok is True

    next_step_result = provider.handle_tool_call("memorii_get_next_step", {"task_id": task_id})
    assert next_step_result.ok is True
    assert next_step_result.result["planner_used"] is True


def test_get_state_summary_with_matching_state_returns_state() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser updates and write tests",
        session_id="session:tool:1",
        task_id="task:tool:1",
        user_id="user:tool:1",
    )

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:tool:1"})

    assert result.ok is True
    assert result.result["state_count"] == 1
    work_states = result.result["work_states"]
    assert isinstance(work_states, list)
    assert work_states[0]["task_id"] == "task:tool:1"


def test_get_next_step_without_state_returns_ask_user_stub() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:none"})

    assert result.ok is True
    next_step = result.result["next_step"]
    assert next_step["action_type"] == "ask_user"
    assert next_step["reason"] == "no_active_work_state"
    assert result.result["planner_used"] is False
    assert result.result["planner_reason"] == "no_solver_run_resolved"
    assert result.result["solver_run_resolution_source"] == "none"


def test_get_next_step_with_task_state_returns_continue_task_stub() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser updates and write tests",
        session_id="session:tool:2",
        task_id="task:tool:2",
        user_id="user:tool:2",
    )

    summary_result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:tool:2"})
    work_state_id = summary_result.result["work_states"][0]["work_state_id"]

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:tool:2"})

    assert result.ok is True
    assert result.result["next_step"]["action_type"] == "continue_task"
    assert result.result["based_on_work_state_id"] == work_state_id


def test_get_next_step_with_investigation_state_returns_inspect_failure_stub() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="build failed on CI while running tests",
        session_id="session:tool:3",
        task_id="task:tool:3",
        user_id="user:tool:3",
    )

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:tool:3"})

    assert result.ok is True
    assert result.result["next_step"]["action_type"] == "inspect_failure"


def test_get_next_step_with_solver_run_and_no_planner_dependencies_falls_back() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": "solver:missing", "task_id": "task:none"})

    assert result.ok is True
    assert result.result["planner_used"] is False
    assert result.result["planner_reason"] == "planner_not_configured"
    assert result.result["solver_run_resolution_source"] == "explicit"
    assert result.result["next_step"]["action_type"] == "ask_user"


def test_get_next_step_with_solver_run_and_no_frontier_falls_back() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    provider = ProviderMemoryService(
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_store.create_solver_run("solver:no-frontier", "exec-1")
    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": "solver:no-frontier", "task_id": "task:none"})

    assert result.ok is True
    assert result.result["planner_used"] is False
    assert result.result["planner_reason"] == "no_frontier_found"
    assert result.result["solver_run_resolution_source"] == "explicit"
    assert result.result["next_step"]["action_type"] == "ask_user"


def test_get_next_step_returns_structured_frontier_action() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    provider = ProviderMemoryService(
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:structured-next-step"
    node_id = "node:structured"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(
        solver_run_id,
        _make_node(
            node_id,
            content={
                "next_test_action": {
                    "action_type": "run_command",
                    "description": "Run targeted command with verbose mode",
                    "expected_evidence": "stderr includes timeout source",
                    "required_tool": "shell",
                }
            },
        ),
    )
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])

    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": solver_run_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["based_on_solver_node_id"] == node_id
    assert result.result["next_step"]["action_type"] == "run_command"
    assert result.result["next_step"]["description"] == "Run targeted command with verbose mode"
    assert result.result["next_step"]["expected_evidence"] == "stderr includes timeout source"
    assert result.result["next_step"]["required_tool"] == "shell"
    assert result.result["solver_run_resolution_source"] == "explicit"


def test_get_next_step_returns_legacy_frontier_action() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    provider = ProviderMemoryService(
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:legacy-next-step"
    node_id = "node:legacy"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={"next_best_test": "rerun flaky test with seed"}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])

    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": solver_run_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["next_step"]["action_type"] == "run_test"
    assert result.result["next_step"]["description"] == "rerun flaky test with seed"
    assert result.result["solver_run_resolution_source"] == "explicit"


def test_get_next_step_returns_inspect_frontier_when_node_has_no_action() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    provider = ProviderMemoryService(
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:inspect-frontier"
    node_id = "node:inspect"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])

    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": solver_run_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["next_step"]["action_type"] == "inspect_frontier"
    assert result.result["solver_run_resolution_source"] == "explicit"


def test_get_next_step_uses_task_binding() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:task-binding"
    node_id = "node:task-binding"
    task_id = "task:binding:1"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={"next_best_test": "run task-bound test"}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])
    work_state_service.bind_state(task_id=task_id, solver_run_id=solver_run_id)

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": task_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["resolved_solver_run_id"] == solver_run_id
    assert result.result["solver_run_resolution_source"] == "task_binding"


def test_get_next_step_uses_session_binding() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:session-binding"
    node_id = "node:session-binding"
    session_id = "session:binding:1"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={"next_best_test": "run session-bound test"}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])
    work_state_service.bind_state(session_id=session_id, solver_run_id=solver_run_id)

    result = provider.handle_tool_call("memorii_get_next_step", {"session_id": session_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["resolved_solver_run_id"] == solver_run_id
    assert result.result["solver_run_resolution_source"] == "session_binding"


def test_get_next_step_explicit_solver_run_id_overrides_bindings() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    explicit_solver_run_id = "solver:explicit-win"
    bound_solver_run_id = "solver:bound-lose"
    node_id = "node:explicit-win"
    task_id = "task:binding:override"
    solver_store.create_solver_run(explicit_solver_run_id, "exec-1")
    solver_store.upsert_node(explicit_solver_run_id, _make_node(node_id, content={"next_best_test": "run explicit test"}))
    _append_overlay(overlay_store, explicit_solver_run_id, [_overlay(node_id)])
    work_state_service.bind_state(task_id=task_id, solver_run_id=bound_solver_run_id)

    result = provider.handle_tool_call(
        "memorii_get_next_step",
        {"task_id": task_id, "solver_run_id": explicit_solver_run_id},
    )

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["resolved_solver_run_id"] == explicit_solver_run_id
    assert result.result["solver_run_resolution_source"] == "explicit"


def test_get_next_step_without_binding_falls_back_with_no_solver_run_resolved() -> None:
    provider = ProviderMemoryService(work_state_service=WorkStateService())

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:no-binding"})

    assert result.ok is True
    assert result.result["planner_used"] is False
    assert result.result["planner_reason"] == "no_solver_run_resolved"
