"""Runtime orchestration service for harness-driven task execution."""

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.consolidation.consolidator import Consolidator
from memorii.core.directory.directory import MemoryDirectory
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.classifier import build_event_id, make_event
from memorii.core.provider.models import ProviderOperation, ProviderWriteDecision
from memorii.core.persistence.resume import ResumeService
from memorii.core.retrieval.planner import RetrievalPlanner
from memorii.core.router.router import MemoryRouter
from memorii.core.solver import (
    SolverContextItem,
    SolverDecision,
    SolverModelInput,
    NextTestAction,
    SolverModelProvider,
    SolverUpdateEngine,
    SolverUpdateInput,
)
from memorii.domain.enums import EventType, ExecutionNodeStatus, MemoryDomain
from memorii.domain.events import EventRecord
from memorii.domain.memory_object import MemoryObject
from memorii.domain.retrieval import RetrievalIntent, RetrievalPlan, RetrievalScope
from memorii.domain.routing import InboundEvent, InboundEventClass, RoutingDecision
from memorii.domain.writebacks import WritebackCandidate
from memorii.stores.base.interfaces import EventLogStore, ExecutionGraphStore, OverlayStore, SolverGraphStore

logger = logging.getLogger(__name__)


class RuntimeObservationInput(BaseModel):
    event_id: str
    event_class: InboundEventClass
    payload: dict[str, object] = Field(default_factory=dict)
    source: str = "runtime"

    model_config = ConfigDict(extra="forbid")


class RuntimeStepResult(BaseModel):
    task_id: str
    execution_node_id: str
    solver_run_id: str
    retrieval_plan: RetrievalPlan
    retrieval_plan_queries: list[str] = Field(default_factory=list)
    retrieved_ids_by_domain_raw: dict[str, list[str]] = Field(default_factory=dict)
    retrieved_ids_by_domain_deduped: dict[str, list[str]] = Field(default_factory=dict)
    retrieved_ids_deduped: list[str] = Field(default_factory=list)
    retrieved_by_domain: dict[str, list[str]] = Field(default_factory=dict)
    routed_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_reasons: dict[str, str] = Field(default_factory=dict)
    solver_decision: SolverDecision
    follow_up_required: bool
    downgraded: bool
    next_action: str | None = None
    next_test_action: NextTestAction | None = None
    solver_state_summary: str = ""
    unresolved_questions: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    candidate_decisions: list[str] = Field(default_factory=list)
    writeback_candidates: list[WritebackCandidate] = Field(default_factory=list)
    writeback_trace: list[dict[str, object]] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class InMemoryMemoryPlane:
    """Compatibility wrapper around the canonical MemoryPlaneService."""

    def __init__(self, service: MemoryPlaneService | None = None) -> None:
        self._service = service or MemoryPlaneService()

    @property
    def service(self) -> MemoryPlaneService:
        return self._service

    def put(self, memory_object: MemoryObject) -> None:
        self._service.seed_runtime_memory_object(memory_object)

    def query(self, query):
        return self._service.query_runtime_memory(query)

class RuntimeStepService:
    def __init__(
        self,
        *,
        execution_store: ExecutionGraphStore,
        solver_store: SolverGraphStore,
        overlay_store: OverlayStore,
        event_log_store: EventLogStore,
        router: MemoryRouter | None = None,
        retrieval_planner: RetrievalPlanner | None = None,
        consolidator: Consolidator | None = None,
        directory: MemoryDirectory | None = None,
        solver_update_engine: SolverUpdateEngine | None = None,
        memory_plane: InMemoryMemoryPlane | None = None,
        model_provider: SolverModelProvider | None = None,
    ) -> None:
        self._execution_store = execution_store
        self._solver_store = solver_store
        self._overlay_store = overlay_store
        self._event_log_store = event_log_store
        self._router = router or MemoryRouter()
        self._retrieval_planner = retrieval_planner or RetrievalPlanner()
        self._consolidator = consolidator or Consolidator()
        self._directory = directory or MemoryDirectory()
        self._solver_update_engine = solver_update_engine or SolverUpdateEngine()
        self._memory_plane = memory_plane or InMemoryMemoryPlane()
        self._memory_plane_service = self._memory_plane.service
        self._resume_service = ResumeService(execution_store, solver_store, overlay_store)
        self._model_provider = model_provider

    def seed_memory_object(self, memory_object: MemoryObject) -> None:
        self._memory_plane_service.seed_runtime_memory_object(memory_object)


    def apply_provider_compat_write(
        self,
        *,
        operation: ProviderOperation,
        content: str,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        action: str = "upsert",
        target: str = "memory",
    ) -> ProviderWriteDecision:
        """Compatibility shim: runtime path delegates provider-style writes to the canonical memory plane."""
        event = make_event(
            event_id=build_event_id("runtime-compat-write", session_id=session_id, task_id=task_id, sequence=1),
            operation=operation,
            content=content,
            action=action,
            target=target,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
        )
        return self._memory_plane_service.apply_provider_memory_write(event=event)

    def step(
        self,
        *,
        task_id: str,
        observation: RuntimeObservationInput,
        execution_node_id: str | None = None,
        model_output: dict[str, object] | None = None,
    ) -> RuntimeStepResult:
        logger.info("runtime_step_start task_id=%s event_id=%s", task_id, observation.event_id)

        execution_state = self._resume_service.load_execution_graph(task_id)
        target_node_id = execution_node_id or self._pick_execution_node(task_id, execution_state.status_by_node)

        solver_run_id = self._resolve_solver_run(task_id, target_node_id)
        routing_decision = self._route_observation(
            task_id=task_id,
            execution_node_id=target_node_id,
            solver_run_id=solver_run_id,
            observation=observation,
        )
        logger.info(
            "routing_decision task_id=%s event_id=%s domains=%s",
            task_id,
            observation.event_id,
            [item.domain.value for item in routing_decision.routed_objects],
        )

        intent = self._resolve_intent(observation)
        scope = RetrievalScope(task_id=task_id, execution_node_id=target_node_id, solver_run_id=solver_run_id)
        retrieval_plan = self._retrieval_planner.build_plan(
            intent=intent,
            scope=scope,
            active_validity_only=True,
            include_raw_transcript=True,
        )

        retrieval_result = self._execute_retrieval(retrieval_plan)
        retrieved = retrieval_result.retrieved_items
        logger.info(
            "retrieval_plan task_id=%s event_id=%s queries=%s retrieved=%d",
            task_id,
            observation.event_id,
            [query.domain.value for query in retrieval_plan.queries],
            len(retrieved),
        )
        available_evidence_ids = sorted({item.memory_id for item in retrieved})

        effective_model_output = model_output or self._call_model_provider(
            task_id=task_id,
            execution_node_id=target_node_id,
            solver_run_id=solver_run_id,
            observation=observation,
            retrieved=retrieved,
            available_evidence_ids=available_evidence_ids,
        )

        update_input = SolverUpdateInput(
            task_id=task_id,
            solver_run_id=solver_run_id,
            execution_node_id=target_node_id,
            observation_text=str(observation.payload),
            observation_source_ref=observation.event_id,
            available_evidence_ids=available_evidence_ids,
            model_output=effective_model_output,
        )

        decision_node_id = f"node:{observation.event_id}:decision"
        prior_overlay = self._overlay_store.get_latest_node_overlay(solver_run_id, decision_node_id)

        update_result = self._solver_update_engine.apply_update(
            update_input=update_input,
            next_overlay_version_id=f"ov:{solver_run_id}:{observation.event_id}",
            next_event_id=f"solver-update:{observation.event_id}",
            next_node_id=f"node:{observation.event_id}",
            next_edge_id=f"edge:{observation.event_id}",
            prior_belief=prior_overlay.belief if prior_overlay is not None else None,
        )
        logger.info(
            "solver_decision task_id=%s event_id=%s decision=%s downgraded=%s",
            task_id,
            observation.event_id,
            update_result.final_decision.value,
            update_result.downgraded,
        )

        for node in update_result.created_nodes:
            self._solver_store.upsert_node(solver_run_id, node)
        for edge in update_result.created_edges:
            self._solver_store.upsert_edge(solver_run_id, edge)
        if update_result.overlay_version is not None:
            self._overlay_store.append_overlay_version(update_result.overlay_version)

        for event in update_result.generated_events:
            self._event_log_store.append(event)

        writebacks: list[WritebackCandidate] = []
        if update_result.final_decision in {SolverDecision.SUPPORTED, SolverDecision.REFUTED}:
            writebacks.append(
                self._consolidator.from_solver_resolution(
                    candidate_id=f"wb:{solver_run_id}:{observation.event_id}",
                    task_id=task_id,
                    solver_run_id=solver_run_id,
                    execution_node_id=target_node_id,
                    summary=update_result.parsed_output.rationale_short,
                    source_refs=[observation.event_id, *update_result.parsed_output.evidence_ids],
                )
            )

        result = RuntimeStepResult(
            task_id=task_id,
            execution_node_id=target_node_id,
            solver_run_id=solver_run_id,
            retrieval_plan=retrieval_plan,
            retrieval_plan_queries=[query.domain.value for query in retrieval_plan.queries],
            retrieved_ids_by_domain_raw=retrieval_result.retrieved_ids_by_domain_raw,
            retrieved_ids_by_domain_deduped=retrieval_result.retrieved_ids_by_domain_deduped,
            retrieved_ids_deduped=retrieval_result.retrieved_ids_deduped,
            retrieved_by_domain=retrieval_result.retrieved_ids_by_domain_deduped,
            routed_domains=[item.domain for item in routing_decision.routed_objects],
            blocked_domains=sorted(set(routing_decision.blocked_domains), key=lambda domain: domain.value),
            blocked_reasons=self._blocked_reasons(routing_decision),
            solver_decision=update_result.final_decision,
            follow_up_required=update_result.follow_up_required,
            downgraded=update_result.downgraded,
            next_action=update_result.parsed_output.next_best_test,
            solver_state_summary=update_result.parsed_output.rationale_short,
            next_test_action=update_result.parsed_output.next_test_action,
            unresolved_questions=update_result.parsed_output.missing_evidence,
            required_tests=[update_result.parsed_output.next_best_test]
            if update_result.parsed_output.next_best_test
            else [update_result.parsed_output.next_test_action.description]
            if update_result.parsed_output.next_test_action
            else [],
            candidate_decisions=[update_result.parsed_output.decision.value],
            writeback_candidates=writebacks,
            writeback_trace=self._writeback_trace(writebacks),
            event_ids=[item.event_id for item in update_result.generated_events],
        )

        self._event_log_store.append(
            EventRecord(
                event_id=f"runtime-step:{observation.event_id}",
                event_type=EventType.ACTION_COMPLETED,
                timestamp=datetime.now(UTC),
                task_id=task_id,
                execution_node_id=target_node_id,
                solver_run_id=solver_run_id,
                source="runtime_step_service",
                payload={
                    "graph_type": "system",
                    "entity_type": "runtime_step",
                    "operation": "create",
                    "entity_id": f"step:{observation.event_id}",
                    "entity": result.model_dump(mode="json"),
                    "metadata": {"version": 1, "is_candidate": False, "is_committed": True},
                },
                dedupe_key=f"runtime-step:{observation.event_id}",
            )
        )

        logger.info(
            "verification_result task_id=%s event_id=%s follow_up=%s writebacks=%d",
            task_id,
            observation.event_id,
            update_result.follow_up_required,
            len(writebacks),
        )
        return result

    def _call_model_provider(
        self,
        *,
        task_id: str,
        execution_node_id: str,
        solver_run_id: str,
        observation: RuntimeObservationInput,
        retrieved: list[MemoryObject],
        available_evidence_ids: list[str],
    ) -> dict[str, object] | None:
        if self._model_provider is None:
            return None

        model_input = SolverModelInput(
            task_id=task_id,
            execution_node_id=execution_node_id,
            solver_run_id=solver_run_id,
            observation_event_id=observation.event_id,
            observation_text=str(observation.payload),
            context_items=[
                SolverContextItem(
                    memory_id=item.memory_id,
                    memory_domain=item.memory_type.value,
                    content=item.content,
                )
                for item in retrieved
            ],
            available_evidence_ids=available_evidence_ids,
        )
        decision = self._model_provider.generate_decision(model_input)
        return decision.model_dump(mode="python")

    def _route_observation(
        self,
        *,
        task_id: str,
        execution_node_id: str,
        solver_run_id: str,
        observation: RuntimeObservationInput,
    ) -> RoutingDecision:
        inbound = InboundEvent(
            event_id=observation.event_id,
            event_class=observation.event_class,
            task_id=task_id,
            execution_node_id=execution_node_id,
            solver_run_id=solver_run_id,
            payload=observation.payload,
            timestamp=datetime.now(UTC),
        )
        return self._memory_plane_service.ingest_runtime_observation(router=self._router, inbound=inbound)

    def _resolve_intent(self, observation: RuntimeObservationInput) -> RetrievalIntent:
        failed = observation.payload.get("status") == "failed" or observation.payload.get("outcome") == "failed"
        if failed or observation.event_class in {
            InboundEventClass.TOOL_RESULT,
            InboundEventClass.TOOL_STATE_UPDATE,
            InboundEventClass.SOLVER_OBSERVATION,
        }:
            return RetrievalIntent.DEBUG_OR_INVESTIGATE
        return RetrievalIntent.CONTINUE_EXECUTION

    def _resolve_solver_run(self, task_id: str, execution_node_id: str) -> str:
        solver_runs = self._directory.list_solver_runs_for_execution_node(execution_node_id)
        if solver_runs:
            return solver_runs[-1]

        solver_runs = self._solver_store.list_by_execution_node(execution_node_id)
        if solver_runs:
            solver_run_id = solver_runs[-1]
            self._directory.map_execution_node_to_solver_run(task_id, execution_node_id, solver_run_id)
            return solver_run_id

        solver_run_id = f"solver:{task_id}:{execution_node_id}"
        self._solver_store.create_solver_run(solver_run_id, execution_node_id)
        self._directory.map_execution_node_to_solver_run(task_id, execution_node_id, solver_run_id)
        return solver_run_id

    def _pick_execution_node(self, task_id: str, status_by_node: dict[str, str]) -> str:
        nodes = self._execution_store.list_nodes(task_id)
        if not nodes:
            raise ValueError(f"No execution nodes available for task {task_id}")

        running = sorted(node.id for node in nodes if node.status == ExecutionNodeStatus.RUNNING)
        if running:
            return running[0]
        ready = sorted(node.id for node in nodes if node.status == ExecutionNodeStatus.READY)
        if ready:
            return ready[0]
        return sorted(node.id for node in nodes if node.id in status_by_node)[0]

    def _execute_retrieval(self, plan: RetrievalPlan) -> "_RuntimeRetrievalTrace":
        trace = self._memory_plane_service.retrieve_runtime_context(plan=plan)
        return _RuntimeRetrievalTrace(
            retrieved_items=trace.retrieved_items,
            retrieved_ids_by_domain_raw=trace.retrieved_ids_by_domain_raw,
            retrieved_ids_by_domain_deduped=trace.retrieved_ids_by_domain_deduped,
            retrieved_ids_deduped=trace.retrieved_ids_deduped,
        )

    def _blocked_reasons(self, decision: RoutingDecision) -> dict[str, str]:
        reasons: dict[str, str] = {}
        for trace_item in decision.policy_trace:
            if not trace_item.startswith("blocked:"):
                continue
            _, domain, reason = trace_item.split(":", maxsplit=2)
            reasons[domain] = reason
        return reasons

    def _writeback_trace(self, writebacks: list[WritebackCandidate]) -> list[dict[str, object]]:
        return [
            {
                "candidate_id": candidate.candidate_id,
                "target_domain": candidate.target_domain.value,
                "status": candidate.status.value,
                "validation_state": candidate.validation_state.value,
                "source_refs": list(candidate.provenance.source_refs),
                "source_type": candidate.provenance.source_type.value,
            }
            for candidate in writebacks
        ]


class _RuntimeRetrievalTrace(BaseModel):
    retrieved_items: list[MemoryObject] = Field(default_factory=list)
    retrieved_ids_by_domain_raw: dict[str, list[str]] = Field(default_factory=dict)
    retrieved_ids_by_domain_deduped: dict[str, list[str]] = Field(default_factory=dict)
    retrieved_ids_deduped: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
