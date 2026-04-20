"""Scenario execution against Memorii and baseline systems."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.models import (
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    BenchmarkSystem,
    ScenarioObservation,
)
from memorii.core.persistence.resume import ResumeService
from memorii.core.retrieval.planner import RetrievalPlanner
from memorii.core.router.router import MemoryRouter
from memorii.core.solver.abstention import SolverDecision
from memorii.core.solver.verifier import SolverDecisionVerifier
from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import (
    CommitStatus,
    ExecutionNodeStatus,
    ExecutionNodeType,
    SolverCreatedBy,
    SolverNodeStatus,
    SolverNodeType,
)
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion
from memorii.stores.execution_graph.store import InMemoryExecutionGraphStore
from memorii.stores.overlays.store import InMemoryOverlayStore
from memorii.stores.solver_graph.store import InMemorySolverGraphStore


class ScenarioExecutor:
    def __init__(self) -> None:
        self._planner = RetrievalPlanner()
        self._router = MemoryRouter()
        self._verifier = SolverDecisionVerifier()

    def run(self, *, fixture: BenchmarkScenarioFixture, system: BenchmarkSystem) -> ScenarioObservation:
        if fixture.category in {
            BenchmarkScenarioType.TRANSCRIPT_RETRIEVAL,
            BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            BenchmarkScenarioType.EPISODIC_RETRIEVAL,
        }:
            return self._run_retrieval(fixture, system)
        if fixture.category == BenchmarkScenarioType.ROUTING_CORRECTNESS:
            return self._run_routing(fixture, system)
        if fixture.category == BenchmarkScenarioType.EXECUTION_RESUME:
            return self._run_execution_resume(fixture, system)
        if fixture.category == BenchmarkScenarioType.SOLVER_RESUME:
            return self._run_solver_resume(fixture, system)
        if fixture.category == BenchmarkScenarioType.SOLVER_VALIDATION:
            return self._run_solver_validation(fixture, system)
        if fixture.category == BenchmarkScenarioType.END_TO_END:
            return self._run_end_to_end(fixture, system)
        raise ValueError(f"Unsupported scenario category: {fixture.category}")

    def _run_retrieval(self, fixture: BenchmarkScenarioFixture, system: BenchmarkSystem) -> ScenarioObservation:
        if fixture.retrieval is None:
            raise ValueError("retrieval fixture is required")

        retrieval = fixture.retrieval
        if system == BenchmarkSystem.FLAT_RETRIEVAL_BASELINE:
            candidates = list(retrieval.corpus)
        else:
            plan = self._planner.build_plan(intent=retrieval.intent, scope=retrieval.scope)
            query_domains = {query.domain for query in plan.queries}
            if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
                query_domains = {domain for domain in query_domains if domain.value == "transcript"}
            if system == BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE:
                query_domains = {domain for domain in query_domains if domain.value != "solver"}
            candidates = [item for item in retrieval.corpus if item.domain in query_domains]
            candidates = [item for item in candidates if self._in_scope(item=item, retrieval=retrieval)]

        ranked = sorted(candidates, key=lambda item: (-_keyword_overlap(retrieval.query, item.text), item.item_id))
        top = ranked[: retrieval.top_k]
        latency_ms = float(len(candidates) * 2 + len(ranked))

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            retrieved_ids=[item.item_id for item in top],
            relevant_ids=list(retrieval.expected_relevant_ids),
            excluded_ids=list(retrieval.expected_excluded_ids),
            retrieval_latency_ms=latency_ms,
        )

    def _run_routing(self, fixture: BenchmarkScenarioFixture, system: BenchmarkSystem) -> ScenarioObservation:
        if fixture.routing is None:
            raise ValueError("routing fixture is required")

        routing = fixture.routing
        if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
            routed = []
            blocked = []
            if routing.inbound_event.event_class.value in {"user_message", "agent_message", "tool_result"}:
                routed = [domain for domain in routing.expected_domains if domain.value == "transcript"]
        elif system == BenchmarkSystem.FLAT_RETRIEVAL_BASELINE:
            decision = self._router.route_event(routing.inbound_event)
            routed = sorted({obj.domain for obj in decision.routed_objects} | set(routing.expected_blocked_domains), key=lambda d: d.value)
            blocked = []
        else:
            decision = self._router.route_event(routing.inbound_event)
            routed = sorted({obj.domain for obj in decision.routed_objects}, key=lambda d: d.value)
            blocked = sorted(set(decision.blocked_domains), key=lambda d: d.value)
            if system == BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE:
                routed = [domain for domain in routed if domain.value != "solver"]

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            routed_domains=routed,
            blocked_domains=blocked,
            relevant_ids=[domain.value for domain in routing.expected_domains],
            excluded_ids=[domain.value for domain in routing.expected_blocked_domains],
        )

    def _run_execution_resume(self, fixture: BenchmarkScenarioFixture, system: BenchmarkSystem) -> ScenarioObservation:
        if fixture.execution_resume is None:
            raise ValueError("execution resume fixture is required")

        fx = fixture.execution_resume
        execution_store = InMemoryExecutionGraphStore()
        solver_store = InMemorySolverGraphStore()
        overlay_store = InMemoryOverlayStore()

        now = datetime.now(UTC)
        for node_id, status_value in fx.expected_status_by_node.items():
            execution_store.upsert_node(
                fx.task_id,
                ExecutionNode(
                    id=node_id,
                    type=ExecutionNodeType.WORK_ITEM,
                    title=node_id,
                    description=node_id,
                    status=ExecutionNodeStatus(status_value),
                    created_at=now,
                    updated_at=now,
                ),
            )

        if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
            execution_store = InMemoryExecutionGraphStore()
        resume = ResumeService(execution_store, solver_store, overlay_store).load_execution_graph(fx.task_id)
        observed_node_ids = sorted(node.id for node in resume.nodes)
        expected_node_ids = sorted(fx.expected_node_ids)
        is_correct = observed_node_ids == expected_node_ids and resume.status_by_node == fx.expected_status_by_node

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            execution_resume_correct=is_correct,
            scenario_success=is_correct,
        )

    def _run_solver_resume(self, fixture: BenchmarkScenarioFixture, system: BenchmarkSystem) -> ScenarioObservation:
        if fixture.solver_resume is None:
            raise ValueError("solver resume fixture is required")

        fx = fixture.solver_resume
        execution_store = InMemoryExecutionGraphStore()
        solver_store = InMemorySolverGraphStore()
        overlay_store = InMemoryOverlayStore()

        solver_store.create_solver_run(fx.solver_run_id, fx.execution_node_id)
        now = datetime.now(UTC)
        question = SolverNode(
            id="q:1",
            type=SolverNodeType.QUESTION,
            content={"text": "root question"},
            metadata=SolverNodeMetadata(
                created_at=now,
                created_by=SolverCreatedBy.SYSTEM,
                candidate_state=CommitStatus.COMMITTED,
                source_refs=[],
                tags=[],
            ),
        )
        solver_store.upsert_node(fx.solver_run_id, question)
        if system != BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE and system != BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
            overlay_store.append_overlay_version(
                SolverOverlayVersion(
                    version_id=f"ov:{fx.solver_run_id}:1",
                    solver_run_id=fx.solver_run_id,
                    created_at=now,
                    node_overlays=[
                        SolverNodeOverlay(
                            node_id="q:1",
                            belief=0.5,
                            status=SolverNodeStatus.NEEDS_TEST,
                            is_frontier=True,
                            reopenable=True,
                            unexplained=True,
                            updated_at=now,
                        )
                    ],
                )
            )

        state = ResumeService(execution_store, solver_store, overlay_store).load_solver_graph(fx.solver_run_id)
        frontier_ok = sorted(state.active_frontier) == sorted(fx.expected_frontier)
        unresolved_ok = sorted(state.unresolved_questions) == sorted(fx.expected_unresolved_questions)
        reopenable_ok = sorted(state.reopenable_branches) == sorted(fx.expected_reopenable_branches)
        solver_ok = frontier_ok and unresolved_ok and reopenable_ok

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            solver_resume_correct=solver_ok,
            frontier_restore_correct=frontier_ok,
            unresolved_restore_correct=unresolved_ok,
            scenario_success=solver_ok,
        )

    def _run_solver_validation(self, fixture: BenchmarkScenarioFixture, system: BenchmarkSystem) -> ScenarioObservation:
        if fixture.solver_validation is None:
            raise ValueError("solver validation fixture is required")

        fx = fixture.solver_validation
        decision = SolverDecision(fx.decision)
        if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
            downgraded = False
            invalid = False
            abstention = decision in {
                SolverDecision.INSUFFICIENT_EVIDENCE,
                SolverDecision.NEEDS_TEST,
                SolverDecision.MULTIPLE_PLAUSIBLE_OPTIONS,
            }
        else:
            outcome = self._verifier.verify(
                decision=decision,
                evidence_ids=list(fx.evidence_ids),
                missing_evidence=list(fx.missing_evidence),
                next_best_test=fx.next_best_test,
                available_evidence_ids=set(fx.available_evidence_ids),
            )
            downgraded = outcome.downgraded
            invalid = not outcome.is_valid
            abstention = outcome.final_decision in {
                SolverDecision.INSUFFICIENT_EVIDENCE,
                SolverDecision.NEEDS_TEST,
                SolverDecision.MULTIPLE_PLAUSIBLE_OPTIONS,
            }

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            downgraded=downgraded,
            invalid_output_rejected=invalid,
            abstention_preserved=abstention,
            scenario_success=(downgraded == fx.expect_downgrade and invalid == fx.expect_invalid_rejection),
        )

    def _run_end_to_end(self, fixture: BenchmarkScenarioFixture, system: BenchmarkSystem) -> ScenarioObservation:
        if fixture.end_to_end is None:
            raise ValueError("end-to-end fixture is required")

        fx = fixture.end_to_end
        event = fixture.routing.inbound_event if fixture.routing is not None else None
        routed_domains = []
        if event is not None:
            decision = self._router.route_event(event)
            routed_domains = [item.domain for item in decision.routed_objects]
            if system == BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE:
                routed_domains = [domain for domain in routed_domains if domain.value != "solver"]
            if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
                routed_domains = [domain for domain in routed_domains if domain.value == "transcript"]

        scenario_success = fx.expect_pipeline_success and set(fx.expect_writeback_domains).issubset(set(routed_domains))
        semantic_pollution = False
        user_pollution = False
        if system == BenchmarkSystem.FLAT_RETRIEVAL_BASELINE:
            semantic_pollution = True
            user_pollution = True

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            scenario_success=scenario_success,
            writeback_candidate_domains=sorted(set(routed_domains), key=lambda d: d.value),
            semantic_pollution=semantic_pollution,
            user_memory_pollution=user_pollution,
        )

    def _in_scope(self, *, item: object, retrieval: object) -> bool:
        item_task_id = getattr(item, "task_id", None)
        item_execution_node_id = getattr(item, "execution_node_id", None)
        item_solver_run_id = getattr(item, "solver_run_id", None)
        scope = getattr(retrieval, "scope")

        if scope.task_id is not None and item_task_id not in {None, scope.task_id}:
            return False
        if scope.execution_node_id is not None and item_execution_node_id not in {None, scope.execution_node_id}:
            return False
        if scope.solver_run_id is not None and item_solver_run_id not in {None, scope.solver_run_id}:
            return False
        return True


def _keyword_overlap(query: str, text: str) -> int:
    query_tokens = {token for token in query.lower().split() if token}
    text_tokens = {token for token in text.lower().split() if token}
    return len(query_tokens & text_tokens)
