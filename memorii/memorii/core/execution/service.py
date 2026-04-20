"""Minimal deterministic runtime service for Phase 5 orchestration."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.consolidation.consolidator import Consolidator
from memorii.core.directory.directory import MemoryDirectory
from memorii.core.persistence.resume import ResumeService
from memorii.core.retrieval.planner import RetrievalPlanner
from memorii.core.router.router import MemoryRouter
from memorii.core.solver import SolverDecision, SolverUpdateEngine, SolverUpdateInput
from memorii.domain.enums import EventType, ExecutionNodeStatus, MemoryDomain
from memorii.domain.events import EventRecord
from memorii.domain.memory_object import MemoryObject
from memorii.domain.retrieval import DomainRetrievalQuery, RetrievalIntent, RetrievalPlan, RetrievalScope
from memorii.domain.routing import InboundEvent, InboundEventClass
from memorii.domain.writebacks import WritebackCandidate
from memorii.stores.base.interfaces import EventLogStore, ExecutionGraphStore, OverlayStore, SolverGraphStore


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
    retrieved_by_domain: dict[str, list[str]] = Field(default_factory=dict)
    routed_domains: list[MemoryDomain] = Field(default_factory=list)
    solver_decision: SolverDecision
    follow_up_required: bool
    downgraded: bool
    writeback_candidates: list[WritebackCandidate] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class InMemoryMemoryPlane:
    """Simple in-memory memory object partition used by runtime retrieval."""

    def __init__(self) -> None:
        self._by_domain: dict[MemoryDomain, list[MemoryObject]] = {domain: [] for domain in MemoryDomain}

    def put(self, memory_object: MemoryObject) -> None:
        self._by_domain[memory_object.memory_type].append(memory_object)

    def query(self, query: DomainRetrievalQuery) -> list[MemoryObject]:
        items = self._by_domain[query.domain]
        return [item for item in items if self._matches_scope(item, query)]

    def _matches_scope(self, item: MemoryObject, query: DomainRetrievalQuery) -> bool:
        ns = item.namespace or {}
        if query.scope.task_id is not None and ns.get("task_id") != query.scope.task_id:
            return False
        if query.scope.execution_node_id is not None and ns.get("execution_node_id") != query.scope.execution_node_id:
            return False
        if query.scope.solver_run_id is not None and ns.get("solver_run_id") != query.scope.solver_run_id:
            return False
        if query.scope.agent_id is not None and ns.get("agent_id") != query.scope.agent_id:
            return False
        return True


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
        self._resume_service = ResumeService(execution_store, solver_store, overlay_store)

    def seed_memory_object(self, memory_object: MemoryObject) -> None:
        self._memory_plane.put(memory_object)

    def step(
        self,
        *,
        task_id: str,
        observation: RuntimeObservationInput,
        execution_node_id: str | None = None,
        model_output: dict[str, object] | None = None,
    ) -> RuntimeStepResult:
        execution_state = self._resume_service.load_execution_graph(task_id)
        target_node_id = execution_node_id or self._pick_execution_node(task_id, execution_state.status_by_node)

        solver_run_id = self._resolve_solver_run(task_id, target_node_id)
        self._route_observation(task_id=task_id, execution_node_id=target_node_id, solver_run_id=solver_run_id, observation=observation)

        intent = self._resolve_intent(observation)
        scope = RetrievalScope(task_id=task_id, execution_node_id=target_node_id, solver_run_id=solver_run_id)
        retrieval_plan = self._retrieval_planner.build_plan(
            intent=intent,
            scope=scope,
            include_raw_transcript=True,
        )
        if intent == RetrievalIntent.DEBUG_OR_INVESTIGATE:
            retrieval_plan.queries.append(
                DomainRetrievalQuery(
                    domain=MemoryDomain.EXECUTION,
                    scope=scope,
                    namespace={
                        "memory_domain": MemoryDomain.EXECUTION,
                        "task_id": task_id,
                        "execution_node_id": target_node_id,
                        "solver_run_id": solver_run_id,
                    },
                )
            )
            retrieval_plan.queries.append(
                DomainRetrievalQuery(
                    domain=MemoryDomain.TRANSCRIPT,
                    scope=scope,
                    namespace={
                        "memory_domain": MemoryDomain.TRANSCRIPT,
                        "task_id": task_id,
                        "execution_node_id": target_node_id,
                        "solver_run_id": solver_run_id,
                    },
                    require_raw_transcript=True,
                )
            )

        retrieved = self._execute_retrieval(retrieval_plan)
        available_evidence_ids = sorted({item.memory_id for item in retrieved})

        update_input = SolverUpdateInput(
            task_id=task_id,
            solver_run_id=solver_run_id,
            execution_node_id=target_node_id,
            observation_text=str(observation.payload),
            observation_source_ref=observation.event_id,
            available_evidence_ids=available_evidence_ids,
            model_output=model_output,
        )

        update_result = self._solver_update_engine.apply_update(
            update_input=update_input,
            next_overlay_version_id=f"ov:{solver_run_id}:{observation.event_id}",
            next_event_id=f"solver-update:{observation.event_id}",
            next_node_id=f"node:{observation.event_id}",
            next_edge_id=f"edge:{observation.event_id}",
        )

        for node in update_result.created_nodes:
            self._solver_store.upsert_node(solver_run_id, node)
        for edge in update_result.created_edges:
            self._solver_store.upsert_edge(solver_run_id, edge)
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
            retrieved_by_domain=self._retrieved_ids_by_domain(retrieval_plan),
            routed_domains=[item.domain for item in self._router.route_event(
                InboundEvent(
                    event_id=f"peek:{observation.event_id}",
                    event_class=observation.event_class,
                    task_id=task_id,
                    execution_node_id=target_node_id,
                    solver_run_id=solver_run_id,
                    payload=observation.payload,
                    timestamp=datetime.now(UTC),
                )
            ).routed_objects],
            solver_decision=update_result.final_decision,
            follow_up_required=update_result.follow_up_required,
            downgraded=update_result.downgraded,
            writeback_candidates=writebacks,
            event_ids=[item.event_id for item in update_result.generated_events],
        )

        self._event_log_store.append(
            EventRecord(
                event_id=f"runtime-step:{observation.event_id}",
                event_type=EventType.ACTION_COMPLETED,
                timestamp=datetime.now(UTC),
                task_id=task_id,
                execution_node_id=target_node_id,
                solver_graph_id=solver_run_id,
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

        return result

    def _route_observation(
        self,
        *,
        task_id: str,
        execution_node_id: str,
        solver_run_id: str,
        observation: RuntimeObservationInput,
    ) -> None:
        inbound = InboundEvent(
            event_id=observation.event_id,
            event_class=observation.event_class,
            task_id=task_id,
            execution_node_id=execution_node_id,
            solver_run_id=solver_run_id,
            payload=observation.payload,
            timestamp=datetime.now(UTC),
        )
        decision = self._router.route_event(inbound)
        for routed in decision.routed_objects:
            self._memory_plane.put(routed.memory_object)

    def _resolve_intent(self, observation: RuntimeObservationInput) -> RetrievalIntent:
        failed = observation.payload.get("status") == "failed" or observation.payload.get("outcome") == "failed"
        if failed or observation.event_class in {InboundEventClass.TOOL_RESULT, InboundEventClass.SOLVER_OBSERVATION}:
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

    def _execute_retrieval(self, plan: RetrievalPlan) -> list[MemoryObject]:
        results: list[MemoryObject] = []
        for query in plan.queries:
            results.extend(self._memory_plane.query(query))
        return results

    def _retrieved_ids_by_domain(self, plan: RetrievalPlan) -> dict[str, list[str]]:
        by_domain: dict[str, list[str]] = {}
        for query in plan.queries:
            ids = [item.memory_id for item in self._memory_plane.query(query)]
            by_domain.setdefault(query.domain.value, []).extend(ids)
        return by_domain
