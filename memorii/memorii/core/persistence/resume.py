"""Task and solver resume service."""

from memorii.domain.enums import SolverNodeStatus, SolverNodeType
from memorii.domain.solver_graph.state import ExecutionResumeState, SolverResumeState
from memorii.stores.base.interfaces import ExecutionGraphStore, OverlayStore, SolverGraphStore


class ResumeService:
    def __init__(
        self,
        execution_store: ExecutionGraphStore,
        solver_store: SolverGraphStore,
        overlay_store: OverlayStore,
    ) -> None:
        self._execution_store = execution_store
        self._solver_store = solver_store
        self._overlay_store = overlay_store

    def load_execution_graph(self, task_id: str) -> ExecutionResumeState:
        nodes = self._execution_store.list_nodes(task_id)
        edges = self._execution_store.list_edges(task_id)
        return ExecutionResumeState(
            task_id=task_id,
            nodes=nodes,
            edges=edges,
            status_by_node=self._execution_store.get_status_snapshot(task_id),
        )

    def load_solver_graph(self, solver_run_id: str) -> SolverResumeState:
        nodes = self._solver_store.list_nodes(solver_run_id)
        edges = self._solver_store.list_edges(solver_run_id)
        execution_node_id = self._solver_store.get_execution_node_id(solver_run_id)
        latest_overlay = self._overlay_store.get_latest_version(solver_run_id)

        active_frontier: list[str] = []
        unresolved_questions: list[str] = []
        unexplained_observations: list[str] = []
        reopenable_branches: list[str] = []

        if latest_overlay is not None:
            for node_overlay in latest_overlay.node_overlays:
                if node_overlay.is_frontier:
                    active_frontier.append(node_overlay.node_id)
                if node_overlay.unexplained:
                    unexplained_observations.append(node_overlay.node_id)
                if node_overlay.reopenable:
                    reopenable_branches.append(node_overlay.node_id)

        node_by_id = {node.id: node for node in nodes}
        for node in nodes:
            overlay = None
            if latest_overlay is not None:
                overlay = next((item for item in latest_overlay.node_overlays if item.node_id == node.id), None)
            if node.type == SolverNodeType.QUESTION:
                if overlay is None or overlay.status != SolverNodeStatus.RESOLVED:
                    unresolved_questions.append(node.id)

        return SolverResumeState(
            solver_run_id=solver_run_id,
            execution_node_id=execution_node_id,
            nodes=nodes,
            edges=edges,
            active_frontier=sorted(set(active_frontier)),
            unresolved_questions=sorted(set(unresolved_questions)),
            unexplained_observations=sorted({node_id for node_id in unexplained_observations if node_id in node_by_id}),
            reopenable_branches=sorted({node_id for node_id in reopenable_branches if node_id in node_by_id}),
            latest_overlay=latest_overlay,
        )
