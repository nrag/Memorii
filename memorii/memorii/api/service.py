"""Framework-neutral runtime API service for external harnesses."""

from datetime import UTC, datetime

from memorii.api.models import ResumeTaskResult, RuntimeTaskState, StartTaskResult, StepResult, TaskInput
from memorii.core.execution import RuntimeObservationInput, RuntimeStepService
from memorii.core.persistence.resume import ResumeService
from memorii.domain.enums import EventType, ExecutionNodeStatus, ExecutionNodeType
from memorii.domain.routing import InboundEventClass
from memorii.domain.events import EventRecord
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.state import ExecutionResumeState, SolverResumeState
from memorii.stores.base.interfaces import EventLogStore, ExecutionGraphStore, OverlayStore, SolverGraphStore


class MemoriiRuntimeAPI:
    """Clean runtime API surface for harness-driven execution."""

    def __init__(
        self,
        *,
        runtime_step_service: RuntimeStepService,
        execution_store: ExecutionGraphStore,
        solver_store: SolverGraphStore,
        overlay_store: OverlayStore,
        event_log_store: EventLogStore,
    ) -> None:
        self._runtime = runtime_step_service
        self._execution_store = execution_store
        self._solver_store = solver_store
        self._overlay_store = overlay_store
        self._event_log_store = event_log_store
        self._resume = ResumeService(execution_store, solver_store, overlay_store)

    def start_task(self, task_id: str, input: TaskInput) -> StartTaskResult:
        created_execution_node_id = self._ensure_root_execution_node(task_id)
        self._event_log_store.append(
            EventRecord(
                event_id=f"task-started:{input.event_id}",
                event_type=EventType.TASK_STARTED,
                timestamp=datetime.now(UTC),
                task_id=task_id,
                execution_node_id=created_execution_node_id,
                source="runtime_api",
                payload={
                    "graph_type": "system",
                    "entity_type": "task",
                    "operation": "create",
                    "entity_id": task_id,
                    "entity": {"input": input.payload},
                    "metadata": {"version": 1, "is_candidate": False, "is_committed": True},
                },
                dedupe_key=f"task-started:{input.event_id}",
            )
        )

        initial_step = self._runtime.step(
            task_id=task_id,
            execution_node_id=created_execution_node_id,
            observation=RuntimeObservationInput(
                event_id=input.event_id,
                event_class=InboundEventClass.USER_MESSAGE,
                payload=input.payload,
                source="runtime_api_start_task",
            ),
        )
        return StartTaskResult(
            task_id=task_id,
            created_execution_node_id=created_execution_node_id,
            initial_step=initial_step,
        )

    def step(self, task_id: str, observation: RuntimeObservationInput) -> StepResult:
        return StepResult(result=self._runtime.step(task_id=task_id, observation=observation))

    def resume_task(self, task_id: str) -> ResumeTaskResult:
        execution = self._resume.load_execution_graph(task_id)
        solver_states = [
            self._resume.load_solver_graph(solver_run_id)
            for node in execution.nodes
            for solver_run_id in self._solver_store.list_by_execution_node(node.id)
        ]
        self._event_log_store.append(
            EventRecord(
                event_id=f"task-resumed:{task_id}:{datetime.now(UTC).timestamp()}",
                event_type=EventType.TASK_RESUMED,
                timestamp=datetime.now(UTC),
                task_id=task_id,
                source="runtime_api",
                payload={
                    "graph_type": "system",
                    "entity_type": "task",
                    "operation": "update",
                    "entity_id": task_id,
                    "entity": {"solver_runs": [state.solver_run_id for state in solver_states]},
                    "metadata": {"version": 1, "is_candidate": False, "is_committed": True},
                },
                dedupe_key=f"task-resume:{task_id}",
            )
        )
        return ResumeTaskResult(task_id=task_id, state=RuntimeTaskState(task_id=task_id, execution=execution, solver_runs=solver_states))

    def get_state(self, task_id: str) -> RuntimeTaskState:
        execution = self._resume.load_execution_graph(task_id)
        solver_states = [
            self._resume.load_solver_graph(solver_run_id)
            for node in execution.nodes
            for solver_run_id in self._solver_store.list_by_execution_node(node.id)
        ]
        return RuntimeTaskState(task_id=task_id, execution=execution, solver_runs=solver_states)

    def get_solver_state(self, solver_run_id: str) -> SolverResumeState:
        return self._resume.load_solver_graph(solver_run_id)

    def get_execution_state(self, task_id: str) -> ExecutionResumeState:
        return self._resume.load_execution_graph(task_id)

    def _ensure_root_execution_node(self, task_id: str) -> str:
        existing_nodes = self._execution_store.list_nodes(task_id)
        if existing_nodes:
            return sorted(node.id for node in existing_nodes)[0]

        node_id = f"exec:{task_id}:root"
        now = datetime.now(UTC)
        root = ExecutionNode(
            id=node_id,
            type=ExecutionNodeType.WORK_ITEM,
            title=f"Task {task_id}",
            description=f"Root execution node for task {task_id}",
            status=ExecutionNodeStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )
        self._execution_store.upsert_node(task_id, root)
        return node_id
