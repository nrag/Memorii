from datetime import UTC, datetime

from memorii.adapters import CLITestHarnessAdapter, GenericJSONHarnessAdapter, HarnessEvent
from memorii.api import MemoriiRuntimeAPI
from memorii.core.execution import RuntimeObservationInput, RuntimeStepService
from memorii.core.solver import SolverDecisionOutput, StaticSolverModelProvider
from memorii.domain.enums import ExecutionNodeStatus, ExecutionNodeType
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.routing import InboundEventClass
from memorii.stores.event_log import InMemoryEventLogStore
from memorii.stores.execution_graph import InMemoryExecutionGraphStore
from memorii.stores.overlays import InMemoryOverlayStore
from memorii.stores.solver_graph import InMemorySolverGraphStore


def _build_api(task_id: str = "task-phase6") -> tuple[MemoriiRuntimeAPI, CLITestHarnessAdapter]:
    execution_store = InMemoryExecutionGraphStore()
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    event_log_store = InMemoryEventLogStore()

    execution_store.upsert_node(
        task_id,
        ExecutionNode(
            id=f"exec:{task_id}:root",
            type=ExecutionNodeType.WORK_ITEM,
            title="root",
            description="root",
            status=ExecutionNodeStatus.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )

    provider = StaticSolverModelProvider(
        SolverDecisionOutput(
            decision="NEEDS_TEST",
            evidence_ids=[],
            missing_evidence=["traceback"],
            next_best_test="rerun_targeted_test",
            rationale_short="Need a targeted verification test",
            confidence_band="low",
        )
    )

    runtime = RuntimeStepService(
        execution_store=execution_store,
        solver_store=solver_store,
        overlay_store=overlay_store,
        event_log_store=event_log_store,
        model_provider=provider,
    )
    api = MemoriiRuntimeAPI(
        runtime_step_service=runtime,
        execution_store=execution_store,
        solver_store=solver_store,
        overlay_store=overlay_store,
        event_log_store=event_log_store,
    )
    adapter = CLITestHarnessAdapter(GenericJSONHarnessAdapter(api))
    return api, adapter


def test_harness_driven_execution_returns_structured_output() -> None:
    _, adapter = _build_api("task-harness")

    start = adapter.start_task("task-harness", "Debug flaky test")
    assert start.next_action == "rerun_targeted_test"
    assert "traceback" in start.unresolved_questions

    step = adapter.add_tool_result("task-harness", "evt-tool-1", "failed", "flake")
    assert step.required_tests == ["rerun_targeted_test"]
    assert step.candidate_decisions == ["NEEDS_TEST"]


def test_real_model_loop_uses_provider_when_model_output_not_passed() -> None:
    api, _ = _build_api("task-provider")

    result = api.step(
        "task-provider",
        observation=RuntimeObservationInput(
            event_id="evt-provider",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed", "detail": "timeout"},
            source="integration_test",
        ),
    ).result

    assert result.solver_decision.value == "NEEDS_TEST"
    assert result.next_action == "rerun_targeted_test"


def test_resume_via_adapter_restores_solver_state() -> None:
    _, adapter = _build_api("task-resume-adapter")

    adapter.start_task("task-resume-adapter", "Investigate regression")
    adapter.add_tool_result("task-resume-adapter", "evt-resume-tool", "failed", "assertion")

    resumed = adapter.resume_task("task-resume-adapter")
    solver_runs = resumed["state"]["solver_runs"]
    assert len(solver_runs) >= 1
    assert solver_runs[0]["active_frontier"]


def test_multi_step_debugging_scenario_tracks_follow_up() -> None:
    _, adapter = _build_api("task-debug")

    adapter.start_task("task-debug", "fix test")
    first = adapter.add_tool_result("task-debug", "evt-debug-1", "failed", "mismatch")
    second = adapter.add_user_message("task-debug", "evt-debug-2", "collect logs and rerun")

    assert first.next_action == "rerun_targeted_test"
    assert second.required_tests == ["rerun_targeted_test"]



def test_execution_update_event_ingestion_contract() -> None:
    _, adapter = _build_api("task-exec-update")

    adapter.start_task("task-exec-update", "Investigate failure")
    output = adapter.add_execution_update(
        "task-exec-update",
        "evt-exec-update",
        {"status": "running", "progress": "collecting artifacts"},
    )

    assert output.task_id == "task-exec-update"
    assert output.candidate_decisions == ["NEEDS_TEST"]

def test_failure_and_recovery_flow_downgrades_invalid_then_recovers() -> None:
    execution_store = InMemoryExecutionGraphStore()
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    event_log_store = InMemoryEventLogStore()
    task_id = "task-recovery"

    execution_store.upsert_node(
        task_id,
        ExecutionNode(
            id=f"exec:{task_id}:root",
            type=ExecutionNodeType.WORK_ITEM,
            title="root",
            description="root",
            status=ExecutionNodeStatus.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )

    runtime = RuntimeStepService(
        execution_store=execution_store,
        solver_store=solver_store,
        overlay_store=overlay_store,
        event_log_store=event_log_store,
    )
    api = MemoriiRuntimeAPI(
        runtime_step_service=runtime,
        execution_store=execution_store,
        solver_store=solver_store,
        overlay_store=overlay_store,
        event_log_store=event_log_store,
    )
    adapter = GenericJSONHarnessAdapter(api)

    first = adapter.step(
        HarnessEvent(
            event_id="evt-invalid",
            task_id=task_id,
            event_type=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed"},
        )
    )
    assert first.candidate_decisions == ["INSUFFICIENT_EVIDENCE"]

    second = api.step(
        task_id,
        observation=RuntimeObservationInput(
            event_id="evt-recover",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "passed", "detail": "verified"},
            source="integration_test",
        ),
    ).result
    assert second.solver_decision.value == "INSUFFICIENT_EVIDENCE"
    assert second.unresolved_questions
