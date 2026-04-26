from datetime import UTC, datetime
from unittest.mock import MagicMock

from memorii.core.execution import RuntimeObservationInput, RuntimeStepService
from memorii.core.retrieval import RetrievalPlanner
from memorii.core.router import MemoryRouter
from memorii.core.router.routing_policy import RoutingPolicy
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
    TemporalValidityStatus,
)
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.memory_object import MemoryObject
from memorii.domain.retrieval import DomainRetrievalQuery, FreshnessPolicy, RetrievalNamespace, RetrievalScope, ValidityStatus
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


def _decision_belief(runtime: RuntimeStepService, solver_run_id: str) -> float:
    latest = runtime._overlay_store.get_latest_version(solver_run_id)  # noqa: SLF001 - test-only introspection
    assert latest is not None
    decision_overlay = next(overlay for overlay in latest.node_overlays if overlay.node_id.endswith(":decision"))
    return decision_overlay.belief


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


def test_runtime_retrieval_dedupes_memory_ids_across_queries() -> None:
    task_id = "task-dedupe"
    execution_node_id = "exec-dedupe"
    solver_run_id = f"solver:{task_id}:{execution_node_id}"
    runtime = _build_runtime(task_id=task_id, execution_node_id=execution_node_id)

    runtime.seed_memory_object(_make_memory("dup-id", MemoryDomain.EXECUTION, task_id, execution_node_id, solver_run_id))
    runtime.seed_memory_object(_make_memory("dup-id", MemoryDomain.TRANSCRIPT, task_id, execution_node_id, solver_run_id))
    runtime.seed_memory_object(_make_memory("uniq-id", MemoryDomain.SOLVER, task_id, execution_node_id, solver_run_id))

    result = runtime.step(
        task_id=task_id,
        observation=RuntimeObservationInput(
            event_id="evt-dedupe",
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

    flattened = [memory_id for ids in result.retrieved_by_domain.values() for memory_id in ids]
    assert flattened.count("dup-id") == 1


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


def test_in_memory_query_excludes_candidates_by_default() -> None:
    plane = _build_runtime()._memory_plane
    task_id = "task-filter"
    execution_node_id = "exec-filter"
    solver_run_id = f"solver:{task_id}:{execution_node_id}"
    plane.put(_make_memory("committed:1", MemoryDomain.SEMANTIC, task_id, execution_node_id, solver_run_id))
    candidate = _make_memory("candidate:1", MemoryDomain.SEMANTIC, task_id, execution_node_id, solver_run_id)
    candidate.status = CommitStatus.CANDIDATE
    plane.put(candidate)
    query = DomainRetrievalQuery(
        domain=MemoryDomain.SEMANTIC,
        scope=RetrievalScope(task_id=task_id, execution_node_id=execution_node_id, solver_run_id=solver_run_id),
        namespace=RetrievalNamespace(
            memory_domain=MemoryDomain.SEMANTIC,
            task_id=task_id,
            execution_node_id=execution_node_id,
            solver_run_id=solver_run_id,
        ),
    )
    assert [item.memory_id for item in plane.query(query)] == ["committed:1"]


def test_in_memory_query_can_include_candidates_when_requested() -> None:
    plane = _build_runtime()._memory_plane
    task_id = "task-filter-candidates"
    execution_node_id = "exec-filter-candidates"
    solver_run_id = f"solver:{task_id}:{execution_node_id}"
    plane.put(_make_memory("committed:2", MemoryDomain.SEMANTIC, task_id, execution_node_id, solver_run_id))
    candidate = _make_memory("candidate:2", MemoryDomain.SEMANTIC, task_id, execution_node_id, solver_run_id)
    candidate.status = CommitStatus.CANDIDATE
    plane.put(candidate)
    query = DomainRetrievalQuery(
        domain=MemoryDomain.SEMANTIC,
        scope=RetrievalScope(task_id=task_id, execution_node_id=execution_node_id, solver_run_id=solver_run_id),
        namespace=RetrievalNamespace(
            memory_domain=MemoryDomain.SEMANTIC,
            task_id=task_id,
            execution_node_id=execution_node_id,
            solver_run_id=solver_run_id,
        ),
        include_candidates=True,
    )
    assert set(item.memory_id for item in plane.query(query)) == {"committed:2", "candidate:2"}


def test_in_memory_query_respects_active_validity_filtering() -> None:
    plane = _build_runtime()._memory_plane
    task_id = "task-validity"
    execution_node_id = "exec-validity"
    solver_run_id = f"solver:{task_id}:{execution_node_id}"
    active = _make_memory("active:1", MemoryDomain.SEMANTIC, task_id, execution_node_id, solver_run_id)
    expired = _make_memory("expired:1", MemoryDomain.SEMANTIC, task_id, execution_node_id, solver_run_id)
    expired.validity_status = TemporalValidityStatus.EXPIRED
    plane.put(active)
    plane.put(expired)
    query = DomainRetrievalQuery(
        domain=MemoryDomain.SEMANTIC,
        scope=RetrievalScope(task_id=task_id, execution_node_id=execution_node_id, solver_run_id=solver_run_id),
        namespace=RetrievalNamespace(
            memory_domain=MemoryDomain.SEMANTIC,
            task_id=task_id,
            execution_node_id=execution_node_id,
            solver_run_id=solver_run_id,
        ),
        freshness=FreshnessPolicy(required_validity=ValidityStatus.ACTIVE),
    )
    assert [item.memory_id for item in plane.query(query)] == ["active:1"]


def test_runtime_step_exposes_blocked_domains_and_reasons() -> None:
    class BlockingPolicy(RoutingPolicy):
        def route_domains(self, event_class, payload=None):  # type: ignore[override]
            return [MemoryDomain.TRANSCRIPT, MemoryDomain.SEMANTIC, MemoryDomain.USER]

    runtime = _build_runtime(task_id="task-blocked", execution_node_id="exec-blocked")
    runtime._router = MemoryRouter(policy=BlockingPolicy())  # noqa: SLF001 - test-only controlled wiring

    result = runtime.step(
        task_id="task-blocked",
        observation=RuntimeObservationInput(
            event_id="evt-blocked",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed"},
        ),
        model_output={
            "decision": "INSUFFICIENT_EVIDENCE",
            "evidence_ids": [],
            "missing_evidence": ["log"],
            "next_best_test": "collect_log",
            "rationale_short": "insufficient",
            "confidence_band": "low",
        },
    )

    assert set(result.blocked_domains) == {MemoryDomain.SEMANTIC, MemoryDomain.USER}
    assert result.blocked_reasons == {"semantic": "raw_event", "user": "raw_event"}


def test_runtime_step_exposes_retrieval_and_writeback_traces() -> None:
    task_id = "task-trace"
    execution_node_id = "exec-trace"
    solver_run_id = f"solver:{task_id}:{execution_node_id}"
    runtime = _build_runtime(task_id=task_id, execution_node_id=execution_node_id)
    runtime.seed_memory_object(_make_memory("dup-id", MemoryDomain.TRANSCRIPT, task_id, execution_node_id, solver_run_id))
    runtime.seed_memory_object(_make_memory("dup-id", MemoryDomain.EXECUTION, task_id, execution_node_id, solver_run_id))
    runtime.seed_memory_object(_make_memory("uniq-id", MemoryDomain.SOLVER, task_id, execution_node_id, solver_run_id))

    result = runtime.step(
        task_id=task_id,
        observation=RuntimeObservationInput(
            event_id="evt-trace",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "passed"},
        ),
        model_output={
            "decision": "SUPPORTED",
            "evidence_ids": ["evt-trace:transcript"],
            "missing_evidence": [],
            "next_best_test": None,
            "rationale_short": "resolved",
            "confidence_band": "high",
        },
    )

    assert result.retrieval_plan_queries
    assert "transcript" in result.retrieved_ids_by_domain_raw
    assert "execution" in result.retrieved_ids_by_domain_raw
    assert result.retrieved_ids_deduped.count("dup-id") == 1
    assert result.retrieved_by_domain == result.retrieved_ids_by_domain_deduped
    assert len(result.writeback_trace) == 1
    assert result.writeback_trace[0]["candidate_id"] == result.writeback_candidates[0].candidate_id


def test_needs_test_with_structured_next_test_action_is_supported_in_runtime() -> None:
    runtime = _build_runtime(task_id="task-structured", execution_node_id="exec-structured")

    result = runtime.step(
        task_id="task-structured",
        observation=RuntimeObservationInput(
            event_id="evt-structured",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed", "error": "assertion mismatch"},
        ),
        model_output={
            "decision": "NEEDS_TEST",
            "evidence_ids": [],
            "missing_evidence": ["stacktrace"],
            "next_test_action": {
                "action_type": "run_command",
                "description": "Run pytest tests/unit/core/test_phase5_runtime.py -k structured",
                "required_tool": "pytest",
            },
            "rationale_short": "Need direct reproduction evidence",
            "confidence_band": "low",
        },
    )

    assert result.solver_decision == SolverDecision.NEEDS_TEST
    assert result.next_action is None
    assert result.next_test_action is not None
    assert result.next_test_action.description.startswith("Run pytest")
    assert result.required_tests == [result.next_test_action.description]

    decision_node = next(node for node in runtime._solver_store.list_nodes(result.solver_run_id) if node.id.endswith(":decision"))  # noqa: SLF001 - test-only introspection
    assert decision_node.content["next_test_action"] is not None
    assert decision_node.content["next_test_action"]["action_type"] == "run_command"


def test_invalid_structured_next_test_action_triggers_parse_fallback() -> None:
    runtime = _build_runtime(task_id="task-invalid-action", execution_node_id="exec-invalid-action")

    result = runtime.step(
        task_id="task-invalid-action",
        observation=RuntimeObservationInput(
            event_id="evt-invalid-action",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "failed", "detail": "bad schema"},
        ),
        model_output={
            "decision": "NEEDS_TEST",
            "evidence_ids": [],
            "missing_evidence": ["stacktrace"],
            "next_test_action": {
                "action_type": "unknown_action",
                "description": "invalid",
            },
            "rationale_short": "bad action type",
            "confidence_band": "low",
        },
    )

    assert result.solver_decision == SolverDecision.INSUFFICIENT_EVIDENCE
    assert result.event_ids == []


def test_supported_with_evidence_overlay_belief_is_above_default() -> None:
    runtime = _build_runtime(task_id="task-belief-supported", execution_node_id="exec-belief-supported")
    result = runtime.step(
        task_id="task-belief-supported",
        observation=RuntimeObservationInput(
            event_id="evt-belief-supported",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "passed"},
        ),
        model_output={
            "decision": "SUPPORTED",
            "evidence_ids": ["evt-belief-supported:transcript"],
            "missing_evidence": [],
            "next_best_test": None,
            "rationale_short": "supported",
            "confidence_band": "high",
        },
    )
    assert _decision_belief(runtime, result.solver_run_id) > 0.5


def test_needs_test_with_missing_evidence_overlay_belief_is_below_default() -> None:
    runtime = _build_runtime(task_id="task-belief-needs-test", execution_node_id="exec-belief-needs-test")
    result = runtime.step(
        task_id="task-belief-needs-test",
        observation=RuntimeObservationInput(
            event_id="evt-belief-needs-test",
            event_class=InboundEventClass.TOOL_RESULT,
            payload={"status": "failed"},
        ),
        model_output={
            "decision": "NEEDS_TEST",
            "evidence_ids": [],
            "missing_evidence": ["traceback", "repro"],
            "next_best_test": "collect_logs",
            "rationale_short": "need test",
            "confidence_band": "low",
        },
    )
    assert _decision_belief(runtime, result.solver_run_id) < 0.5


def test_verifier_downgrade_reduces_belief_vs_non_downgraded_supported() -> None:
    supported_runtime = _build_runtime(task_id="task-belief-normal", execution_node_id="exec-belief-normal")
    supported = supported_runtime.step(
        task_id="task-belief-normal",
        observation=RuntimeObservationInput(
            event_id="evt-belief-normal",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "passed"},
        ),
        model_output={
            "decision": "SUPPORTED",
            "evidence_ids": ["evt-belief-normal:transcript"],
            "missing_evidence": [],
            "next_best_test": None,
            "rationale_short": "supported",
            "confidence_band": "high",
        },
    )
    normal_belief = _decision_belief(supported_runtime, supported.solver_run_id)

    downgraded_runtime = _build_runtime(task_id="task-belief-downgraded", execution_node_id="exec-belief-downgraded")
    downgraded = downgraded_runtime.step(
        task_id="task-belief-downgraded",
        observation=RuntimeObservationInput(
            event_id="evt-belief-downgraded",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "ambiguous"},
        ),
        model_output={
            "decision": "SUPPORTED",
            "evidence_ids": ["missing-evidence-id"],
            "missing_evidence": ["real_proof"],
            "next_best_test": "collect_real_proof",
            "rationale_short": "unsupported commitment",
            "confidence_band": "medium",
        },
    )
    downgraded_belief = _decision_belief(downgraded_runtime, downgraded.solver_run_id)

    assert downgraded.downgraded is True
    assert downgraded_belief < normal_belief


def test_observation_overlay_belief_remains_one() -> None:
    runtime = _build_runtime(task_id="task-observation-belief", execution_node_id="exec-observation-belief")
    result = runtime.step(
        task_id="task-observation-belief",
        observation=RuntimeObservationInput(
            event_id="evt-observation-belief",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            payload={"status": "seen"},
        ),
        model_output={
            "decision": "INSUFFICIENT_EVIDENCE",
            "evidence_ids": [],
            "missing_evidence": ["details"],
            "next_best_test": "collect_details",
            "rationale_short": "unknown",
            "confidence_band": "low",
        },
    )
    latest = runtime._overlay_store.get_latest_version(result.solver_run_id)  # noqa: SLF001 - test-only introspection
    assert latest is not None
    observation_overlay = next(overlay for overlay in latest.node_overlays if overlay.node_id.endswith(":obs"))
    assert observation_overlay.belief == 1.0
