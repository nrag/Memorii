from datetime import UTC, datetime

from memorii.core.decision_state.models import DecisionEvidencePolarity, DecisionStatus
from memorii.core.decision_state.service import DecisionStateService
from memorii.core.next_step import NextStepEngine, NextStepRequest
from memorii.core.provider.service import ProviderMemoryService
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


def test_decision_work_without_decision_state_requests_open() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:missing",
        kind=WorkStateKind.DECISION,
    )

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=DecisionStateService(),
    ).get_next_step(NextStepRequest(task_id="task:decision:missing"))

    assert result.based_on_work_state_id == decision_work.work_state_id
    assert result.next_step["action_type"] == "open_decision_state"
    assert result.next_step["reason"] == "decision_state_missing"


def test_decision_without_options_requests_options() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:no-options",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    decision = decision_service.open_decision(
        question="Which provider?",
        work_state_id=decision_work.work_state_id,
        task_id="task:decision:no-options",
    )

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:no-options"))

    assert result.next_step["action_type"] == "add_decision_options"
    assert result.next_step["decision_state_id"] == decision.decision_id


def test_decision_without_criteria_requests_criteria() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:no-criteria",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    decision = decision_service.open_decision(
        question="Which provider?",
        work_state_id=decision_work.work_state_id,
        task_id="task:decision:no-criteria",
    )
    decision_service.add_option(decision_id=decision.decision_id, option_id="o1", label="A")

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:no-criteria"))

    assert result.next_step["action_type"] == "add_decision_criteria"


def test_decision_without_evidence_requests_evidence() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:no-evidence",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    decision = decision_service.open_decision(
        question="Which provider?",
        work_state_id=decision_work.work_state_id,
        task_id="task:decision:no-evidence",
    )
    decision_service.add_option(decision_id=decision.decision_id, option_id="o1", label="A")
    decision_service.add_criterion(decision_id=decision.decision_id, criterion_id="c1", label="Latency")

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:no-evidence"))

    assert result.next_step["action_type"] == "add_decision_evidence"


def test_decision_without_recommendation_requests_set_recommendation() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:no-rec",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    decision = decision_service.open_decision(
        question="Which provider?",
        work_state_id=decision_work.work_state_id,
        task_id="task:decision:no-rec",
    )
    decision_service.add_option(decision_id=decision.decision_id, option_id="o1", label="A")
    decision_service.add_criterion(decision_id=decision.decision_id, criterion_id="c1", label="Latency")
    decision_service.add_evidence(
        decision_id=decision.decision_id,
        evidence_id="e1",
        content="A has low latency",
        polarity=DecisionEvidencePolarity.FOR_OPTION,
        option_id="o1",
    )

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:no-rec"))

    assert result.next_step["action_type"] == "set_decision_recommendation"


def test_decision_with_recommendation_requests_finalize() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:finalize",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    decision = decision_service.open_decision(
        question="Which provider?",
        work_state_id=decision_work.work_state_id,
        task_id="task:decision:finalize",
    )
    decision_service.add_option(decision_id=decision.decision_id, option_id="o1", label="A")
    decision_service.add_criterion(decision_id=decision.decision_id, criterion_id="c1", label="Latency")
    decision_service.add_evidence(
        decision_id=decision.decision_id,
        evidence_id="e1",
        content="A has low latency",
        polarity=DecisionEvidencePolarity.FOR_OPTION,
        option_id="o1",
    )
    decision_service.update_recommendation(decision_id=decision.decision_id, recommendation="Pick A")

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:finalize"))

    assert result.next_step["action_type"] == "finalize_decision"


def test_decided_decision_requests_record_outcome() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:decided",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    decision = decision_service.open_decision(
        question="Which provider?",
        work_state_id=decision_work.work_state_id,
        task_id="task:decision:decided",
    )
    decision_service.add_option(decision_id=decision.decision_id, option_id="o1", label="A")
    decision_service.add_criterion(decision_id=decision.decision_id, criterion_id="c1", label="Latency")
    decision_service.add_evidence(
        decision_id=decision.decision_id,
        evidence_id="e1",
        content="A has low latency",
        polarity=DecisionEvidencePolarity.FOR_OPTION,
        option_id="o1",
    )
    decision_service.update_recommendation(decision_id=decision.decision_id, recommendation="Pick A")
    decision_service.record_final_decision(decision_id=decision.decision_id, final_decision="A")

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:decided"))

    assert result.next_step["action_type"] == "record_outcome"
    assert result.next_step["reason"] == "decision_already_decided"


def test_decision_without_service_falls_back_to_generic_clarify() -> None:
    work_state_service = WorkStateService()
    work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:no-service",
        kind=WorkStateKind.DECISION,
    )

    result = NextStepEngine(work_state_service=work_state_service).get_next_step(
        NextStepRequest(task_id="task:decision:no-service")
    )

    assert result.next_step["action_type"] == "clarify_decision_criteria"


def test_provider_memory_service_passes_decision_state_service_to_next_step_engine() -> None:
    decision_state_service = DecisionStateService()
    provider = ProviderMemoryService(decision_state_service=decision_state_service)

    assert provider._next_step_engine._decision_state_service is decision_state_service


def test_decision_lookup_prefers_open_over_decided() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:prefer-open",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    decided = decision_service.open_decision(question="Old", work_state_id=decision_work.work_state_id)
    decision_service.record_final_decision(decision_id=decided.decision_id, final_decision="Old choice")
    open_decision = decision_service.open_decision(question="Current", work_state_id=decision_work.work_state_id)

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:prefer-open"))

    assert result.next_step["action_type"] == "add_decision_options"
    assert result.next_step["decision_state_id"] == open_decision.decision_id


def test_decision_lookup_uses_decided_when_no_open_exists() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:prefer-decided",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    decided = decision_service.open_decision(question="Only", work_state_id=decision_work.work_state_id)
    decision_service.add_option(decision_id=decided.decision_id, option_id="o1", label="A")
    decision_service.add_criterion(decision_id=decided.decision_id, criterion_id="c1", label="Latency")
    decision_service.add_evidence(
        decision_id=decided.decision_id,
        evidence_id="e1",
        content="A has low latency",
        polarity=DecisionEvidencePolarity.FOR_OPTION,
        option_id="o1",
    )
    decision_service.update_recommendation(decision_id=decided.decision_id, recommendation="A")
    decision_service.record_final_decision(decision_id=decided.decision_id, final_decision="A")

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:prefer-decided"))

    assert result.next_step["action_type"] == "record_outcome"
    assert result.next_step["decision_state_id"] == decided.decision_id


def test_decision_lookup_ignores_non_open_non_decided_statuses() -> None:
    work_state_service = WorkStateService()
    decision_work = work_state_service.open_or_resume_work(
        title="Choose provider",
        task_id="task:decision:ignore-abandoned",
        kind=WorkStateKind.DECISION,
    )
    decision_service = DecisionStateService()
    abandoned = decision_service.open_decision(question="Old", work_state_id=decision_work.work_state_id)
    decision_service.abandon_decision(decision_id=abandoned.decision_id)

    decisions = decision_service.list_decisions(work_state_id=decision_work.work_state_id)
    assert decisions[0].status == DecisionStatus.ABANDONED

    result = NextStepEngine(
        work_state_service=work_state_service,
        decision_state_service=decision_service,
    ).get_next_step(NextStepRequest(task_id="task:decision:ignore-abandoned"))

    assert result.next_step["action_type"] == "open_decision_state"
