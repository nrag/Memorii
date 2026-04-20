from datetime import UTC, datetime
from unittest.mock import MagicMock

from memorii.core.execution import RuntimeObservationInput, RuntimeStepService
from memorii.core.retrieval import RetrievalPlanner
from memorii.core.router import MemoryRouter
from memorii.core.solver import SolverDecision
from memorii.domain.common import Provenance, RoutingInfo
from memorii.domain.enums import (
    CommitStatus,
    Durability,
    ExecutionNodeStatus,
    ExecutionNodeType,
    MemoryDomain,
    MemoryScope,
    SourceType,
)
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.memory_object import MemoryObject
from memorii.domain.routing import InboundEventClass
from memorii.stores.event_log import InMemoryEventLogStore
from memorii.stores.execution_graph import InMemoryExecutionGraphStore
from memorii.stores.overlays import InMemoryOverlayStore
from memorii.stores.solver_graph import InMemorySolverGraphStore


def _make_execution_node(node_id: str, status: ExecutionNodeStatus) -> ExecutionNode:
    return ExecutionNode(
        id=node_id,
        type=ExecutionNodeType.WORK_ITEM,
        title=node_id,
        description=node_id,
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_memory(
    memory_id: str,
    domain: MemoryDomain,
    task_id: str,
    execution_node_id: str,
    solver_run_id: str,
) -> MemoryObject:
    return MemoryObject(
        memory_id=memory_id,
        memory_type=domain,
        scope=MemoryScope.EXECUTION_NODE,
        durability=Durability.TASK_PERSISTENT,
        status=CommitStatus.COMMITTED,
        content={"summary": memory_id},
        provenance=Provenance(
            source_type=SourceType.SYSTEM,
            source_refs=[memory_id],
            created_at=datetime.now(UTC),
            created_by="test",
        ),
        routing=RoutingInfo(primary_store=domain.value),
        namespace={
            "memory_domain": domain.value,
            "task_id": task_id,
            "execution_node_id": execution_node_id,
            "solver_run_id": solver_run_id,
        },
    )


def _build_runtime(task_id: str = "task-1", execution_node_id: str = "exec-1") -> RuntimeStepService:
    execution_store = InMemoryExecutionGraphStore()
    execution_store.upsert_node(task_id, _make_execution_node(execution_node_id, ExecutionNodeStatus.RUNNING))
    return RuntimeStepService(
        execution_store=execution_store,
        solver_store=InMemorySolverGraphStore(),
        overlay_store=InMemoryOverlayStore(),
        event_log_store=InMemoryEventLogStore(),
    )


def test_failure_debug_flow_then_resolution() -> None:
    runtime = _build_runtime()

    first = runtime.step(
        task_id="task-1",
        observation=RuntimeObservationInput(
            event_id="evt-fail",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed", "error": "assertion mismatch"},
        ),
        model_output={
            "decision": "NEEDS_TEST",
            "evidence_ids": [],
            "missing_evidence": ["traceback"],
            "next_best_test": "run_targeted_test",
            "rationale_short": "Need more evidence",
            "confidence_band": "low",
        },
    )

    assert first.solver_decision == SolverDecision.NEEDS_TEST
    assert first.follow_up_required is True
    assert first.writeback_candidates == []

    second = runtime.step(
        task_id="task-1",
        observation=RuntimeObservationInput(
            event_id="evt-pass",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "passed", "detail": "repro fixed"},
        ),
        model_output={
            "decision": "SUPPORTED",
            "evidence_ids": ["evt-pass:transcript"],
            "missing_evidence": [],
            "next_best_test": None,
            "rationale_short": "Fix validated by follow-up observation",
            "confidence_band": "medium",
        },
    )

    assert second.solver_decision == SolverDecision.SUPPORTED
    assert second.follow_up_required is False
    assert len(second.writeback_candidates) == 1
    assert second.writeback_candidates[0].target_domain == MemoryDomain.EPISODIC


def test_resume_after_persisted_step_restores_frontier() -> None:
    task_id = "task-resume"
    execution_node_id = "exec-resume"

    execution_store = InMemoryExecutionGraphStore()
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    event_log = InMemoryEventLogStore()
    execution_store.upsert_node(task_id, _make_execution_node(execution_node_id, ExecutionNodeStatus.RUNNING))

    runtime = RuntimeStepService(
        execution_store=execution_store,
        solver_store=solver_store,
        overlay_store=overlay_store,
        event_log_store=event_log,
    )

    runtime.step(
        task_id=task_id,
        observation=RuntimeObservationInput(
            event_id="evt-resume",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed", "detail": "flake"},
        ),
        model_output={
            "decision": "NEEDS_TEST",
            "evidence_ids": [],
            "missing_evidence": ["stable_repro"],
            "next_best_test": "rerun_with_seed",
            "rationale_short": "Need stable reproducer",
            "confidence_band": "low",
        },
    )

    from memorii.core.persistence.resume import ResumeService

    resume = ResumeService(execution_store, solver_store, overlay_store)
    solver_state = resume.load_solver_graph(f"solver:{task_id}:{execution_node_id}")

    assert solver_state.active_frontier
    assert solver_state.unresolved_questions == []
    assert solver_state.reopenable_branches


def test_multi_memory_retrieval_combines_execution_solver_transcript_and_episodic() -> None:
    task_id = "task-multi"
    execution_node_id = "exec-multi"
    solver_run_id = f"solver:{task_id}:{execution_node_id}"

    runtime = _build_runtime(task_id=task_id, execution_node_id=execution_node_id)
    runtime.seed_memory_object(_make_memory("m-exec", MemoryDomain.EXECUTION, task_id, execution_node_id, solver_run_id))
    runtime.seed_memory_object(_make_memory("m-solv", MemoryDomain.SOLVER, task_id, execution_node_id, solver_run_id))
    runtime.seed_memory_object(_make_memory("m-epis", MemoryDomain.EPISODIC, task_id, execution_node_id, solver_run_id))

    result = runtime.step(
        task_id=task_id,
        observation=RuntimeObservationInput(
            event_id="evt-multi",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed", "detail": "debug me"},
        ),
        model_output={
            "decision": "INSUFFICIENT_EVIDENCE",
            "evidence_ids": [],
            "missing_evidence": ["more_logs"],
            "next_best_test": "collect_logs",
            "rationale_short": "Not enough evidence",
            "confidence_band": "low",
        },
    )

    assert "execution" in result.retrieved_by_domain
    assert "solver" in result.retrieved_by_domain
    assert "episodic" in result.retrieved_by_domain
    assert "transcript" in result.retrieved_by_domain


def test_consolidation_emits_candidate_and_semantic_remains_gated() -> None:
    runtime = _build_runtime(task_id="task-cons", execution_node_id="exec-cons")

    result = runtime.step(
        task_id="task-cons",
        observation=RuntimeObservationInput(
            event_id="evt-cons",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "passed", "detail": "all green"},
        ),
        model_output={
            "decision": "SUPPORTED",
            "evidence_ids": ["evt-cons:transcript"],
            "missing_evidence": [],
            "next_best_test": None,
            "rationale_short": "All evidence supports resolution",
            "confidence_band": "high",
        },
    )

    assert len(result.writeback_candidates) == 1
    candidate = result.writeback_candidates[0]
    assert candidate.status == CommitStatus.CANDIDATE
    assert candidate.target_domain == MemoryDomain.EPISODIC


def test_abstention_and_downgrade_do_not_commit_unsupported_claim() -> None:
    runtime = _build_runtime(task_id="task-abstain", execution_node_id="exec-abstain")

    result = runtime.step(
        task_id="task-abstain",
        observation=RuntimeObservationInput(
            event_id="evt-unsupported",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "partial", "detail": "ambiguous"},
        ),
        model_output={
            "decision": "SUPPORTED",
            "evidence_ids": ["does-not-exist"],
            "missing_evidence": ["real_logs"],
            "next_best_test": "collect_real_logs",
            "rationale_short": "Claimed support without real evidence",
            "confidence_band": "medium",
        },
    )

    assert result.solver_decision == SolverDecision.INSUFFICIENT_EVIDENCE
    assert result.downgraded is True
    assert result.writeback_candidates == []


def test_malformed_unresolved_output_is_invalid_and_does_not_mutate_solver_state() -> None:
    task_id = "task-invalid"
    execution_node_id = "exec-invalid"
    solver_run_id = f"solver:{task_id}:{execution_node_id}"

    execution_store = InMemoryExecutionGraphStore()
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    event_log = InMemoryEventLogStore()
    execution_store.upsert_node(task_id, _make_execution_node(execution_node_id, ExecutionNodeStatus.RUNNING))

    runtime = RuntimeStepService(
        execution_store=execution_store,
        solver_store=solver_store,
        overlay_store=overlay_store,
        event_log_store=event_log,
    )

    result = runtime.step(
        task_id=task_id,
        observation=RuntimeObservationInput(
            event_id="evt-invalid",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "failed", "detail": "incomplete output"},
        ),
        model_output={
            "decision": "NEEDS_TEST",
            "evidence_ids": [],
            "missing_evidence": ["traceback"],
            "next_best_test": None,
            "rationale_short": "Missing required next test",
            "confidence_band": "low",
        },
    )

    assert result.solver_decision == SolverDecision.INSUFFICIENT_EVIDENCE
    assert result.event_ids == []
    assert solver_store.list_nodes(solver_run_id) == []
    assert overlay_store.list_versions(solver_run_id) == []


def test_runtime_routes_observation_once_and_reuses_routing_decision() -> None:
    task_id = "task-route-once"
    execution_node_id = "exec-route-once"
    execution_store = InMemoryExecutionGraphStore()
    execution_store.upsert_node(task_id, _make_execution_node(execution_node_id, ExecutionNodeStatus.RUNNING))

    router = MemoryRouter()
    original = router.route_event
    router.route_event = MagicMock(wraps=original)

    runtime = RuntimeStepService(
        execution_store=execution_store,
        solver_store=InMemorySolverGraphStore(),
        overlay_store=InMemoryOverlayStore(),
        event_log_store=InMemoryEventLogStore(),
        router=router,
    )

    runtime.step(
        task_id=task_id,
        observation=RuntimeObservationInput(
            event_id="evt-route-once",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed", "detail": "assertion mismatch"},
        ),
        model_output={
            "decision": "INSUFFICIENT_EVIDENCE",
            "evidence_ids": [],
            "missing_evidence": ["debug logs"],
            "next_best_test": "collect_debug_logs",
            "rationale_short": "Need more grounding",
            "confidence_band": "low",
        },
    )

    assert router.route_event.call_count == 1


def test_runtime_does_not_append_manual_debug_queries_outside_planner() -> None:
    task_id = "task-planner-owned"
    execution_node_id = "exec-planner-owned"
    execution_store = InMemoryExecutionGraphStore()
    execution_store.upsert_node(task_id, _make_execution_node(execution_node_id, ExecutionNodeStatus.RUNNING))

    class MinimalPlanner(RetrievalPlanner):
        def build_plan(self, **kwargs):  # type: ignore[override]
            scope = kwargs["scope"]
            return super().build_plan(intent=kwargs["intent"], scope=scope, include_raw_transcript=False)

    runtime = RuntimeStepService(
        execution_store=execution_store,
        solver_store=InMemorySolverGraphStore(),
        overlay_store=InMemoryOverlayStore(),
        event_log_store=InMemoryEventLogStore(),
        retrieval_planner=MinimalPlanner(),
    )

    result = runtime.step(
        task_id=task_id,
        observation=RuntimeObservationInput(
            event_id="evt-planner-owned",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed", "detail": "debug me"},
        ),
        model_output={
            "decision": "INSUFFICIENT_EVIDENCE",
            "evidence_ids": [],
            "missing_evidence": ["more logs"],
            "next_best_test": "collect_logs",
            "rationale_short": "Need more evidence",
            "confidence_band": "low",
        },
    )

    domains = [query.domain.value for query in result.retrieval_plan.queries]
    assert domains == ["solver", "episodic", "semantic", "execution", "transcript"]
