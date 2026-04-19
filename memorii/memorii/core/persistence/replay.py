"""Deterministic replay support for execution and solver graph rebuild."""

from memorii.domain.events import EventRecord
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.stores.base.interfaces import EventLogStore


class ReplayService:
    def __init__(self, event_log_store: EventLogStore) -> None:
        self._event_log_store = event_log_store

    def replay_task_events(self, task_id: str) -> tuple[dict[str, ExecutionNode], dict[str, ExecutionEdge]]:
        nodes: dict[str, ExecutionNode] = {}
        edges: dict[str, ExecutionEdge] = {}
        for event in self._event_log_store.list_by_task(task_id):
            self._apply_execution_event(event=event, nodes=nodes, edges=edges)
        return nodes, edges

    def replay_solver_events(self, solver_run_id: str) -> tuple[dict[str, SolverNode], dict[str, SolverEdge]]:
        nodes: dict[str, SolverNode] = {}
        edges: dict[str, SolverEdge] = {}
        for event in self._event_log_store.list_by_solver_run(solver_run_id):
            self._apply_solver_event(event=event, nodes=nodes, edges=edges)
        return nodes, edges

    def _apply_execution_event(
        self,
        event: EventRecord,
        nodes: dict[str, ExecutionNode],
        edges: dict[str, ExecutionEdge],
    ) -> None:
        graph_type = event.payload.get("graph_type")
        entity = event.payload.get("entity")
        if graph_type != "execution" or not isinstance(entity, dict):
            return

        if event.event_type.name in {"NODE_ADDED", "NODE_COMMITTED", "STATUS_UPDATED"}:
            node = ExecutionNode.model_validate(entity)
            nodes[node.id] = node
        elif event.event_type.name in {"EDGE_ADDED", "EDGE_COMMITTED"}:
            edge = ExecutionEdge.model_validate(entity)
            edges[edge.id] = edge

    def _apply_solver_event(
        self,
        event: EventRecord,
        nodes: dict[str, SolverNode],
        edges: dict[str, SolverEdge],
    ) -> None:
        graph_type = event.payload.get("graph_type")
        entity = event.payload.get("entity")
        if graph_type != "solver" or not isinstance(entity, dict):
            return

        if event.event_type.name in {"NODE_ADDED", "NODE_COMMITTED", "NODE_REOPENED", "STATUS_UPDATED"}:
            node = SolverNode.model_validate(entity)
            nodes[node.id] = node
        elif event.event_type.name in {"EDGE_ADDED", "EDGE_COMMITTED"}:
            edge = SolverEdge.model_validate(entity)
            edges[edge.id] = edge
