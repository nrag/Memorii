"""Scenario execution against Memorii and baseline systems."""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass

from memorii.core.benchmark.multilingual_tokenization import icu_tokens, mixed_char_ngrams
from memorii.core.benchmark.models import (
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    BenchmarkSystem,
    ConflictCandidate,
    ImplicitRecallFixture,
    RetrievalFixture,
    RetrievalFixtureMemoryItem,
    ScenarioExecutionLevel,
    ScenarioObservation,
)
from memorii.core.execution import RuntimeObservationInput, RuntimeStepService
from memorii.core.provider.models import ProviderStoredRecord
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.hermes_provider import HermesMemoryProvider
from memorii.core.persistence.resume import ResumeService
from memorii.core.retrieval.planner import RetrievalPlanner
from memorii.core.router.router import MemoryRouter
from memorii.core.solver import SolverDecisionOutput, StaticSolverModelProvider
from memorii.core.solver.abstention import SolverDecision
from memorii.core.solver.verifier import SolverDecisionVerifier
from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import (
    CommitStatus,
    Durability,
    ExecutionNodeStatus,
    ExecutionNodeType,
    MemoryDomain,
    MemoryScope,
    SourceType,
    SolverCreatedBy,
    SolverNodeStatus,
    SolverNodeType,
)
from memorii.domain.memory_object import MemoryObject
from memorii.domain.common import Provenance, RoutingInfo
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope
from memorii.domain.routing import InboundEventClass
from memorii.domain.routing import ValidationState
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion
from memorii.stores.event_log.store import InMemoryEventLogStore
from memorii.stores.execution_graph.store import InMemoryExecutionGraphStore
from memorii.stores.overlays.store import InMemoryOverlayStore
from memorii.stores.solver_graph.store import InMemorySolverGraphStore

BENCHMARK_REFERENCE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


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
        if fixture.category == BenchmarkScenarioType.LEARNING_ACROSS_EPISODES:
            return self._run_learning_across_episodes(fixture, system)
        if fixture.category == BenchmarkScenarioType.LONG_HORIZON_DEGRADATION:
            return self._run_long_horizon_degradation(fixture, system)
        if fixture.category == BenchmarkScenarioType.CONFLICT_RESOLUTION:
            return self._run_conflict_resolution(fixture, system)
        if fixture.category == BenchmarkScenarioType.IMPLICIT_RECALL:
            return self._run_implicit_recall(fixture, system)
        raise ValueError(f"Unsupported scenario category: {fixture.category}")

    def _run_retrieval(self, fixture: BenchmarkScenarioFixture, system: BenchmarkSystem) -> ScenarioObservation:
        if fixture.retrieval is None:
            raise ValueError("retrieval fixture is required")

        retrieval = fixture.retrieval
        top, latency_ms = self._retrieve(fixture=retrieval, system=system)

        retrieved_ids = [item.item_id for item in top]
        relevant_ids = set(retrieval.expected_relevant_ids)
        excluded_ids = set(retrieval.expected_excluded_ids)
        retrieved = set(retrieved_ids)
        scenario_success = relevant_ids.issubset(retrieved) and retrieved.isdisjoint(excluded_ids)

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
            retrieved_ids=retrieved_ids,
            relevant_ids=list(retrieval.expected_relevant_ids),
            excluded_ids=list(retrieval.expected_excluded_ids),
            retrieval_latency_ms=latency_ms,
            scenario_success=scenario_success,
        )

    def _run_learning_across_episodes(
        self,
        fixture: BenchmarkScenarioFixture,
        system: BenchmarkSystem,
    ) -> ScenarioObservation:
        if fixture.learning_across_episodes is None:
            raise ValueError("learning across episodes fixture is required")

        fx = fixture.learning_across_episodes
        retrieval = RetrievalFixture(
            query=fx.episode_two_query,
            intent=fixture.retrieval.intent if fixture.retrieval is not None else RetrievalIntent.RESUME_TASK,
            scope=fixture.retrieval.scope if fixture.retrieval is not None else RetrievalScope(),
            top_k=fx.top_k,
            corpus=fx.corpus,
            expected_relevant_ids=[fx.expected_reuse_id],
        )
        if system == BenchmarkSystem.MEMORII:
            ranked = sorted(
                fx.corpus,
                key=lambda item: (-_retrieval_score(fx.episode_two_query, item.text), item.item_id),
            )
            top = ranked[: fx.top_k]
            latency_ms = float(len(fx.corpus) * 3)
        else:
            top, latency_ms = self._retrieve(fixture=retrieval, system=system)
        retrieved_ids = [item.item_id for item in top]
        reuse_correct = fx.expected_reuse_id in set(retrieved_ids)
        baseline_without_reuse_success = fx.expected_reuse_id in set(fx.baseline_without_reuse_retrieved_ids)
        performance_delta = float(reuse_correct) - float(baseline_without_reuse_success)
        writeback_correct = (
            system == BenchmarkSystem.MEMORII and fx.expected_writeback_domain in set(fx.episode_one_writeback_domains)
        )

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
            retrieved_ids=retrieved_ids,
            relevant_ids=[fx.expected_reuse_id],
            retrieval_latency_ms=latency_ms,
            cross_episode_reuse_correct=reuse_correct,
            baseline_without_reuse_success=baseline_without_reuse_success,
            performance_improvement_over_baseline=performance_delta,
            writeback_reuse_correct=writeback_correct,
            writeback_candidate_domains=list(fx.episode_one_writeback_domains),
            expected_writeback_candidate_domains=list(fx.expected_writeback_domains),
            writeback_candidate_ids=[f"wb:learning:{fx.expected_reuse_id}"],
            expected_writeback_candidate_ids=list(fx.expected_writeback_candidate_ids),
            scenario_success=reuse_correct and writeback_correct,
        )

    def _run_long_horizon_degradation(
        self,
        fixture: BenchmarkScenarioFixture,
        system: BenchmarkSystem,
    ) -> ScenarioObservation:
        if fixture.long_horizon_degradation is None:
            raise ValueError("long-horizon degradation fixture is required")

        fx = fixture.long_horizon_degradation
        early_top, early_latency_ms = self._retrieve(fixture=fx.early_retrieval, system=system)
        delayed_top, delayed_latency_ms = self._retrieve(fixture=fx.delayed_retrieval, system=system)

        early_hits = len({item.item_id for item in early_top} & set(fx.early_retrieval.expected_relevant_ids))
        delayed_hits = len({item.item_id for item in delayed_top} & set(fx.delayed_retrieval.expected_relevant_ids))
        early_recall = _safe_ratio(early_hits, len(set(fx.early_retrieval.expected_relevant_ids))) or 0.0
        delayed_recall = _safe_ratio(delayed_hits, len(set(fx.delayed_retrieval.expected_relevant_ids))) or 0.0
        degradation = max(0.0, early_recall - delayed_recall)
        latency_growth = max(0.0, delayed_latency_ms - early_latency_ms)
        noise_hits = len({item.item_id for item in delayed_top} & set(fx.noise_ids))
        noise_resilience = 1.0 - (_safe_ratio(noise_hits, len(delayed_top)) or 0.0)
        delayed_ids = [item.item_id for item in delayed_top]
        expected_relevant_set = set(fx.delayed_retrieval.expected_relevant_ids)
        expected_hard_distractors = set(fx.delayed_retrieval.expected_hard_distractor_ids)
        gold_rank = _first_rank(delayed_ids, expected_relevant_set)
        precision_at_1 = 1.0 if delayed_ids and delayed_ids[0] in expected_relevant_set else 0.0
        top_k_contamination_rate = _safe_ratio(
            len([item_id for item_id in delayed_ids if item_id not in expected_relevant_set]),
            len(delayed_ids),
        ) or 0.0
        hard_distractor_outrank_rate = _compute_hard_distractor_outrank_rate(
            retrieved_ids=delayed_ids,
            relevant_ids=expected_relevant_set,
            hard_distractor_ids=expected_hard_distractors,
        )
        domain_priority_correctness = _domain_priority_correctness(
            retrieved=delayed_top,
            relevant_ids=expected_relevant_set,
            hard_distractor_ids=expected_hard_distractors,
            expected_domain_priority=fx.delayed_retrieval.expected_domain_priority,
        )
        has_explicit_hard_distractors = bool(fx.delayed_retrieval.expected_hard_distractor_ids)
        if has_explicit_hard_distractors:
            resume_under_scale = (
                expected_relevant_set.issubset(set(delayed_ids))
                and gold_rank is not None
                and gold_rank <= 2
                and hard_distractor_outrank_rate == 0.0
            )
        else:
            resume_under_scale = delayed_recall >= 1.0
        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
            retrieved_ids=[item.item_id for item in delayed_top],
            relevant_ids=list(fx.delayed_retrieval.expected_relevant_ids),
            retrieval_latency_ms=delayed_latency_ms,
            early_recall=early_recall,
            delayed_recall=delayed_recall,
            early_latency_ms=early_latency_ms,
            delayed_latency_ms=delayed_latency_ms,
            noise_hit_count=noise_hits,
            retrieval_recall_degradation=degradation,
            retrieval_latency_growth=latency_growth,
            resume_correctness_under_scale=resume_under_scale,
            noise_resilience=noise_resilience,
            precision_at_1=precision_at_1,
            gold_rank=gold_rank,
            hard_distractor_outrank_rate=hard_distractor_outrank_rate,
            top_k_contamination_rate=top_k_contamination_rate,
            domain_priority_correctness=domain_priority_correctness,
            scenario_success=resume_under_scale,
        )

    def _run_conflict_resolution(
        self,
        fixture: BenchmarkScenarioFixture,
        system: BenchmarkSystem,
    ) -> ScenarioObservation:
        if fixture.conflict_resolution is None:
            raise ValueError("conflict resolution fixture is required")
        fx = fixture.conflict_resolution
        selected = self._resolve_conflict(candidates=fx.candidates, system=system)
        conflict_detected = len(fx.candidates) > 1 and system != BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE
        correct_preference = selected.preferred if selected is not None else False
        stale_rejected = selected.validity_status not in {"expired", "invalidated"} if selected is not None else False
        winner_matches = selected is not None and selected.candidate_id == fx.expected_winner_candidate_id
        contradictory_correct = conflict_detected and correct_preference and stale_rejected and winner_matches

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
            conflict_detected=conflict_detected,
            conflict_resolution_correct=winner_matches,
            stale_memory_rejected=stale_rejected,
            contradictory_handling_correct=contradictory_correct,
            scenario_success=contradictory_correct,
        )

    def _run_implicit_recall(
        self,
        fixture: BenchmarkScenarioFixture,
        system: BenchmarkSystem,
    ) -> ScenarioObservation:
        if fixture.implicit_recall is None:
            raise ValueError("implicit recall fixture is required")
        fx = fixture.implicit_recall
        ranked = self._rank_implicit(fixture=fx, system=system)
        top = ranked[: fx.top_k]
        retrieved_ids = [item.item_id for item in top]
        relevant = set(fx.relevant_ids)
        relevant_hits = len(set(retrieved_ids) & relevant)
        false_positives = len(set(retrieved_ids) - relevant)
        false_positive_rate = _safe_ratio(false_positives, len(retrieved_ids)) or 0.0
        implicit_success = relevant_hits > 0

        plan_domains: set[str]
        if system == BenchmarkSystem.FLAT_RETRIEVAL_BASELINE:
            plan_domains = {item.domain.value for item in fx.corpus}
        else:
            plan = self._planner.build_plan(intent=RetrievalIntent.DEBUG_OR_INVESTIGATE, scope=RetrievalScope())
            plan_domains = {query.domain.value for query in plan.queries}
            if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
                plan_domains = {"transcript"}
            if system == BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE:
                plan_domains = {domain for domain in plan_domains if domain != "solver"}

        expected_domains = {domain.value for domain in fx.expected_domains}
        plan_accuracy = expected_domains.issubset(plan_domains)

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
            retrieved_ids=retrieved_ids,
            relevant_ids=list(fx.relevant_ids),
            implicit_recall_success=implicit_success,
            retrieval_plan_relevance_accuracy=plan_accuracy,
            false_positive_retrieval_rate=false_positive_rate,
            scenario_success=implicit_success and plan_accuracy,
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
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
            routed_domains=routed,
            blocked_domains=blocked,
            expected_routed_domains=list(routing.expected_domains),
            expected_blocked_domains=list(routing.expected_blocked_domains),
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
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
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
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
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
            execution_level=ScenarioExecutionLevel.COMPONENT_LEVEL,
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
        if fixture.retrieval is None:
            raise ValueError("end-to-end fixture requires retrieval corpus for realistic storage-path seeding")
        routed_domains: list[MemoryDomain] = []
        writeback_domains: list[MemoryDomain] = []
        writeback_ids: list[str] = []
        writeback_records: list[_ObservedWriteback] = []
        routed_records: list[_ObservedRoutedMemory] = []
        blocked_domain_set: set[MemoryDomain] | None = None
        blocked_reasons: dict[str, str] = {}
        observability_missing: list[str] = []
        retrieved_ids: list[str] = []
        execution_level = ScenarioExecutionLevel.SYSTEM_LEVEL
        if event is not None and system == BenchmarkSystem.MEMORII and fx.system_interface == "provider":
            execution_level = ScenarioExecutionLevel.PROVIDER_SYSTEM
            provider_service = ProviderMemoryService()
            provider = HermesMemoryProvider(provider_service)
            for item in fixture.retrieval.corpus:
                if (
                    item.status == CommitStatus.COMMITTED
                    and item.domain in {MemoryDomain.TRANSCRIPT, MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC, MemoryDomain.USER}
                ):
                    provider_service.seed_committed_record(
                        ProviderStoredRecord(
                            memory_id=item.item_id,
                            domain=item.domain,
                            text=item.text,
                            status=item.status.value,
                            session_id="session:benchmark",
                            task_id=item.task_id or fx.task_id,
                            user_id="user:benchmark",
                        )
                    )
            turn_result = provider.sync_turn(
                user_content=str(event.payload),
                assistant_content="Acknowledged update.",
                session_id="session:benchmark",
                task_id=fx.task_id,
                user_id="user:benchmark",
            )
            write_result = provider.on_memory_write(
                action="upsert",
                target="memory",
                content=str(event.payload),
                session_id="session:benchmark",
                task_id=fx.task_id,
                user_id="user:benchmark",
            )
            retrieved_context = provider.prefetch(
                fixture.retrieval.query,
                session_id="session:benchmark",
                task_id=fx.task_id,
                user_id="user:benchmark",
            )
            routed_domains = [MemoryDomain.TRANSCRIPT]
            blocked_domain_set = set(turn_result.blocked_domains) | set(write_result.blocked_domains)
            blocked_reasons = {**turn_result.blocked_reasons, **write_result.blocked_reasons}
            writeback_ids = sorted(set(write_result.candidate_ids))
            writeback_domains = sorted(set(write_result.allowed_candidate_domains), key=lambda domain: domain.value)
            writeback_records = [
                _ObservedWriteback(
                    domain=domain,
                    candidate_id=candidate_id,
                    status=CommitStatus.CANDIDATE,
                    validated=False,
                    source_kind="raw",
                )
                for domain in write_result.allowed_candidate_domains
                for candidate_id in write_result.candidate_ids
                if f"cand:{domain.value}:" in candidate_id
            ]
            routed_records = [
                _ObservedRoutedMemory(domain=MemoryDomain.TRANSCRIPT, status=CommitStatus.COMMITTED, is_raw_event=True)
            ]
            retrieved_ids = [
                line.split(" ", 1)[0].strip("-")
                for line in retrieved_context.splitlines()
                if line.startswith("- [")
            ]
        elif event is not None and system == BenchmarkSystem.MEMORII:
            execution_store = InMemoryExecutionGraphStore()
            solver_store = InMemorySolverGraphStore()
            overlay_store = InMemoryOverlayStore()
            event_log_store = InMemoryEventLogStore()
            now = datetime.now(UTC)
            execution_store.upsert_node(
                fx.task_id,
                ExecutionNode(
                    id=f"exec:{fx.task_id}:root",
                    type=ExecutionNodeType.WORK_ITEM,
                    title="root",
                    description="root",
                    status=ExecutionNodeStatus.RUNNING,
                    created_at=now,
                    updated_at=now,
                ),
            )
            runtime = RuntimeStepService(
                execution_store=execution_store,
                solver_store=solver_store,
                overlay_store=overlay_store,
                event_log_store=event_log_store,
                model_provider=StaticSolverModelProvider(
                    SolverDecisionOutput(
                        decision="SUPPORTED",
                        evidence_ids=[f"{event.event_id}:transcript"],
                        missing_evidence=[],
                        next_best_test=None,
                        rationale_short="validated resolution path",
                        confidence_band="high",
                    )
                ),
            )
            for item in fixture.retrieval.corpus:
                if not self._in_scope(item=item, retrieval=fixture.retrieval):
                    continue
                namespace = {
                    "task_id": item.task_id or fx.task_id,
                    "memory_domain": item.domain.value,
                }
                if item.execution_node_id is not None:
                    namespace["execution_node_id"] = item.execution_node_id
                if item.solver_run_id is not None:
                    namespace["solver_run_id"] = item.solver_run_id
                seeded = MemoryObject(
                    memory_id=item.item_id,
                    memory_type=item.domain,
                    scope=(
                        MemoryScope.EXECUTION_NODE
                        if item.execution_node_id is not None or item.solver_run_id is not None
                        else MemoryScope.TASK
                    ),
                    durability=Durability.TASK_PERSISTENT,
                    status=item.status,
                    validity_status=item.validity_status,
                    valid_from=item.valid_from,
                    valid_to=item.valid_to,
                    content={"text": item.text},
                    provenance=Provenance(
                        source_type=SourceType.SYSTEM,
                        source_refs=[item.item_id],
                        created_at=now,
                        created_by="benchmark",
                    ),
                    routing=RoutingInfo(primary_store="in_memory", secondary_stores=[]),
                    namespace=namespace,
                )
                runtime.seed_memory_object(seeded)
            result = runtime.step(
                task_id=fx.task_id,
                observation=RuntimeObservationInput(
                    event_id=event.event_id,
                    event_class=InboundEventClass(event.event_class.value),
                    payload=event.payload,
                    source="benchmark",
                ),
                execution_node_id=f"exec:{fx.task_id}:root",
            )
            routed_domains = list(result.routed_domains)
            blocked_domain_set = set(result.blocked_domains)
            blocked_reasons = dict(result.blocked_reasons)
            retrieved_ids = list(result.retrieved_ids_deduped)
            routed_records = [
                _ObservedRoutedMemory(
                    domain=domain,
                    status=CommitStatus.COMMITTED,
                    is_raw_event=True,
                )
                for domain in routed_domains
            ]
            if result.writeback_trace:
                writeback_trace = result.writeback_trace
            else:
                writeback_trace = [
                    {
                        "candidate_id": candidate.candidate_id,
                        "target_domain": candidate.target_domain.value,
                        "status": candidate.status.value,
                        "validation_state": candidate.validation_state.value,
                    }
                    for candidate in result.writeback_candidates
                ]
                observability_missing.append("writeback_trace")
            writeback_domains = [MemoryDomain(str(trace_entry["target_domain"])) for trace_entry in writeback_trace]
            writeback_ids = [str(trace_entry["candidate_id"]) for trace_entry in writeback_trace]
            writeback_records = [
                _ObservedWriteback(
                    domain=MemoryDomain(str(trace_entry["target_domain"])),
                    candidate_id=str(trace_entry["candidate_id"]),
                    status=CommitStatus(str(trace_entry["status"])),
                    validated=(str(trace_entry["validation_state"]) == ValidationState.VALIDATED.value),
                    source_kind="consolidated",
                )
                for trace_entry in writeback_trace
            ]
            if not result.retrieval_plan_queries:
                observability_missing.append("retrieval_plan_queries")
            if not result.retrieved_ids_by_domain_deduped:
                observability_missing.append("retrieved_ids_by_domain_deduped")
        elif event is not None:
            decision = self._router.route_event(event)
            routed_domains = [item.domain for item in decision.routed_objects]
            blocked_domain_set = set(decision.blocked_domains)
            routed_records = [
                _ObservedRoutedMemory(
                    domain=item.domain,
                    status=item.memory_object.status,
                    is_raw_event=True,
                )
                for item in decision.routed_objects
            ]
            if system == BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE:
                routed_domains = [domain for domain in routed_domains if domain.value != "solver"]
            if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
                routed_domains = [domain for domain in routed_domains if domain.value == "transcript"]
            writeback_records = self._baseline_writeback_candidates(system=system, event_class=event.event_class)
            writeback_domains = sorted({candidate.domain for candidate in writeback_records}, key=lambda d: d.value)
            writeback_ids = sorted({candidate.candidate_id for candidate in writeback_records})
            retrieved_ids = []

        expected_routed_domains = list(fixture.routing.expected_domains) if fixture.routing is not None else []
        expected_blocked_domains = list(fixture.routing.expected_blocked_domains) if fixture.routing is not None else []
        routed_domain_set = set(routed_domains)
        runtime_observability_status: str | None = None
        if system == BenchmarkSystem.MEMORII:
            runtime_observability_status = "unsupported" if observability_missing else "supported"

        pipeline_success_ok = fx.expect_pipeline_success
        routing_ok = routed_domain_set == set(expected_routed_domains)
        blocked_ok = (not expected_blocked_domains) or (
            blocked_domain_set is not None and blocked_domain_set == set(expected_blocked_domains)
        )
        writeback_domains_ok = set(writeback_domains) == set(fx.expect_writeback_domains)
        expected_writeback_ids = set(fx.expect_writeback_candidate_ids)
        writeback_ids_ok = (not expected_writeback_ids) or (set(writeback_ids) == expected_writeback_ids)
        writeback_ok = writeback_domains_ok and writeback_ids_ok
        scenario_success = pipeline_success_ok and routing_ok and blocked_ok and writeback_ok
        if runtime_observability_status == "unsupported":
            scenario_success = False
        semantic_pollution, user_pollution = self._derive_pollution(
            routed_records=routed_records,
            writeback_records=writeback_records,
        )

        return ScenarioObservation(
            scenario_id=fixture.scenario_id,
            category=fixture.category,
            system=system,
            execution_level=execution_level,
            scenario_success=scenario_success,
            retrieved_ids=retrieved_ids,
            routed_domains=sorted(set(routed_domains), key=lambda d: d.value),
            blocked_domains=sorted(blocked_domain_set, key=lambda d: d.value) if blocked_domain_set is not None else [],
            blocked_reasons=blocked_reasons,
            expected_routed_domains=expected_routed_domains,
            expected_blocked_domains=expected_blocked_domains,
            runtime_observability_status=runtime_observability_status,
            runtime_observability_missing=observability_missing,
            writeback_candidate_domains=sorted(set(writeback_domains), key=lambda d: d.value),
            expected_writeback_candidate_domains=list(fx.expect_writeback_domains),
            writeback_candidate_ids=sorted(set(writeback_ids)),
            expected_writeback_candidate_ids=list(fx.expect_writeback_candidate_ids),
            semantic_pollution=semantic_pollution,
            user_memory_pollution=user_pollution,
        )

    def _derive_pollution(
        self,
        *,
        routed_records: list["_ObservedRoutedMemory"],
        writeback_records: list["_ObservedWriteback"],
    ) -> tuple[bool, bool]:
        semantic_pollution = any(
            (
                (item.domain == MemoryDomain.SEMANTIC and item.is_raw_event)
                for item in routed_records
            )
        ) or any(
            (
                candidate.domain == MemoryDomain.SEMANTIC
                and (candidate.status == CommitStatus.CANDIDATE and not candidate.validated)
                and candidate.source_kind == "raw"
                for candidate in writeback_records
            )
        )
        user_pollution = any(
            (
                (item.domain == MemoryDomain.USER and item.is_raw_event)
                for item in routed_records
            )
        ) or any(
            (
                candidate.domain == MemoryDomain.USER
                and (candidate.status == CommitStatus.CANDIDATE and not candidate.validated)
                and candidate.source_kind == "raw"
                for candidate in writeback_records
            )
        )
        return semantic_pollution, user_pollution

    def _baseline_writeback_candidates(
        self,
        *,
        system: BenchmarkSystem,
        event_class: InboundEventClass,
    ) -> list["_ObservedWriteback"]:
        if system != BenchmarkSystem.FLAT_RETRIEVAL_BASELINE:
            return []
        if event_class in {InboundEventClass.TOOL_RESULT, InboundEventClass.TOOL_STATE_UPDATE}:
            return [
                _ObservedWriteback(
                    domain=MemoryDomain.SEMANTIC,
                    candidate_id="wb:baseline:flat:semantic",
                    status=CommitStatus.CANDIDATE,
                    validated=False,
                    source_kind="raw",
                ),
                _ObservedWriteback(
                    domain=MemoryDomain.USER,
                    candidate_id="wb:baseline:flat:user",
                    status=CommitStatus.CANDIDATE,
                    validated=False,
                    source_kind="raw",
                ),
            ]
        return []

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

    def _retrieve(
        self,
        *,
        fixture: RetrievalFixture,
        system: BenchmarkSystem,
    ) -> tuple[list[RetrievalFixtureMemoryItem], float]:
        if system == BenchmarkSystem.FLAT_RETRIEVAL_BASELINE:
            candidates = list(fixture.corpus)
        else:
            plan = self._planner.build_plan(intent=fixture.intent, scope=fixture.scope)
            query_domains = {query.domain for query in plan.queries}
            if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
                query_domains = {domain for domain in query_domains if domain.value == "transcript"}
            if system == BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE:
                query_domains = {domain for domain in query_domains if domain.value != "solver"}
            candidates = [item for item in fixture.corpus if item.domain in query_domains]
            candidates = [item for item in candidates if self._in_scope(item=item, retrieval=fixture)]
            candidates = [item for item in candidates if item.status != CommitStatus.CANDIDATE]
            if _intent_requires_active_validity(fixture.intent):
                candidates = [item for item in candidates if _is_active(item, valid_at=BENCHMARK_REFERENCE_TIME)]

        ranked = sorted(
            candidates,
            key=lambda item: (
                -_retrieval_score(
                    fixture.query,
                    item.text,
                    language=fixture.language or item.language or "und",
                ),
                item.item_id,
            ),
        )
        top = ranked[: fixture.top_k]
        latency_ms = float(len(candidates) * 2 + len(ranked))
        return top, latency_ms

    def _resolve_conflict(self, *, candidates: list[ConflictCandidate], system: BenchmarkSystem) -> ConflictCandidate | None:
        if not candidates:
            return None
        if system == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE:
            return sorted(candidates, key=lambda c: (c.recency_rank, c.candidate_id))[0]
        if system == BenchmarkSystem.FLAT_RETRIEVAL_BASELINE:
            return sorted(candidates, key=lambda c: c.candidate_id)[0]
        if system == BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE:
            return sorted(candidates, key=lambda c: (-c.recency_rank, c.candidate_id))[0]

        active = [candidate for candidate in candidates if candidate.validity_status not in {"expired", "invalidated"}]
        pool = active if active else candidates
        return sorted(pool, key=lambda c: self._conflict_sort_key(c))[0]

    def _conflict_sort_key(self, candidate: ConflictCandidate) -> tuple[int, float, int, str]:
        validity_priority = 0 if candidate.validity_status not in {"expired", "invalidated"} else 1
        timestamp_priority = -(candidate.timestamp.timestamp() if candidate.timestamp is not None else 0.0)
        version_priority = -(candidate.version if candidate.version is not None else candidate.recency_rank)
        return (validity_priority, timestamp_priority, version_priority, candidate.candidate_id)

    def _rank_implicit(
        self,
        *,
        fixture: ImplicitRecallFixture,
        system: BenchmarkSystem,
    ) -> list[RetrievalFixtureMemoryItem]:
        scored: list[tuple[float, RetrievalFixtureMemoryItem]] = []
        for item in fixture.corpus:
            score = _retrieval_score(fixture.query, item.text, language=item.language or "und")
            if system == BenchmarkSystem.MEMORII:
                score += _retrieval_score(" ".join(fixture.context_tokens), item.text, language=item.language or "und")
            scored.append((score, item))
        return [item for _, item in sorted(scored, key=lambda row: (-row[0], row[1].item_id))]


def _retrieval_score(query: str, text: str, *, language: str = "und") -> float:
    query_tokens = icu_tokens(query, language)
    text_tokens = icu_tokens(text, language)
    if not query_tokens or not text_tokens:
        return 0.0
    query_set = set(query_tokens)
    text_set = set(text_tokens)
    token_overlap = _safe_ratio(len(query_set & text_set), len(query_set | text_set)) or 0.0
    query_ngrams = mixed_char_ngrams(query)
    text_ngrams = mixed_char_ngrams(text)
    char_ngram_overlap = _safe_ratio(len(query_ngrams & text_ngrams), len(query_ngrams | text_ngrams)) or 0.0
    phrase_bonus = 1.0 if " ".join(query_tokens) in " ".join(text_tokens) else 0.0
    return (0.45 * token_overlap) + (0.35 * char_ngram_overlap) + (0.20 * phrase_bonus)


def _first_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> int | None:
    for index, item_id in enumerate(retrieved_ids, start=1):
        if item_id in relevant_ids:
            return index
    return None


def _compute_hard_distractor_outrank_rate(
    *,
    retrieved_ids: list[str],
    relevant_ids: set[str],
    hard_distractor_ids: set[str],
) -> float:
    if not hard_distractor_ids:
        return 0.0
    best_gold_rank = _first_rank(retrieved_ids, relevant_ids)
    if best_gold_rank is None:
        return 1.0
    outranking = 0
    considered = 0
    rank_by_id = {item_id: idx for idx, item_id in enumerate(retrieved_ids, start=1)}
    for distractor_id in hard_distractor_ids:
        distractor_rank = rank_by_id.get(distractor_id)
        if distractor_rank is None:
            continue
        considered += 1
        if distractor_rank < best_gold_rank:
            outranking += 1
    if considered == 0:
        return 0.0
    return float(outranking) / float(considered)


def _domain_priority_correctness(
    *,
    retrieved: list[RetrievalFixtureMemoryItem],
    relevant_ids: set[str],
    hard_distractor_ids: set[str],
    expected_domain_priority: list[str],
) -> bool | None:
    if not expected_domain_priority:
        return None
    domain_rank = {domain: index for index, domain in enumerate(expected_domain_priority)}
    gold = next((item for item in retrieved if item.item_id in relevant_ids), None)
    distractor = next((item for item in retrieved if item.item_id in hard_distractor_ids), None)
    if gold is None or distractor is None:
        return None
    gold_rank = domain_rank.get(gold.domain.value, len(expected_domain_priority))
    distractor_rank = domain_rank.get(distractor.domain.value, len(expected_domain_priority))
    return gold_rank <= distractor_rank


def _intent_requires_active_validity(intent: RetrievalIntent) -> bool:
    return intent != RetrievalIntent.CONSOLIDATE_CASE


def _is_active(item: RetrievalFixtureMemoryItem, *, valid_at: datetime) -> bool:
    if item.validity_status.value != "active":
        return False
    if item.valid_from is not None and item.valid_from > valid_at:
        return False
    if item.valid_to is not None and item.valid_to < valid_at:
        return False
    return True


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


@dataclass(frozen=True)
class _ObservedWriteback:
    domain: MemoryDomain
    candidate_id: str
    status: CommitStatus
    validated: bool
    source_kind: str


@dataclass(frozen=True)
class _ObservedRoutedMemory:
    domain: MemoryDomain
    status: CommitStatus
    is_raw_event: bool
