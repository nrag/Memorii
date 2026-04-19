"""In-memory solver graph store."""

from collections import defaultdict, deque

from memorii.domain.enums import CommitStatus
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.stores.base.interfaces import SolverGraphStore


class InMemorySolverGraphStore(SolverGraphStore):
    def __init__(self) -> None:
        self._solver_to_execution: dict[str, str] = {}
        self._execution_to_solvers: dict[str, set[str]] = defaultdict(set)
        self._nodes: dict[str, dict[str, SolverNode]] = defaultdict(dict)
        self._edges: dict[str, dict[str, SolverEdge]] = defaultdict(dict)

    def create_solver_run(self, solver_run_id: str, execution_node_id: str) -> None:
        self._solver_to_execution[solver_run_id] = execution_node_id
        self._execution_to_solvers[execution_node_id].add(solver_run_id)

    def upsert_node(self, solver_run_id: str, node: SolverNode) -> None:
        self._nodes[solver_run_id][node.id] = node

    def upsert_edge(self, solver_run_id: str, edge: SolverEdge) -> None:
        self._edges[solver_run_id][edge.id] = edge

    def get_node(self, solver_run_id: str, node_id: str) -> SolverNode | None:
        return self._nodes.get(solver_run_id, {}).get(node_id)

    def get_edge(self, solver_run_id: str, edge_id: str) -> SolverEdge | None:
        return self._edges.get(solver_run_id, {}).get(edge_id)

    def list_nodes(self, solver_run_id: str) -> list[SolverNode]:
        return list(self._nodes.get(solver_run_id, {}).values())

    def list_edges(self, solver_run_id: str) -> list[SolverEdge]:
        return list(self._edges.get(solver_run_id, {}).values())

    def list_by_execution_node(self, execution_node_id: str) -> list[str]:
        return sorted(self._execution_to_solvers.get(execution_node_id, set()))

    def get_execution_node_id(self, solver_run_id: str) -> str:
        if solver_run_id not in self._solver_to_execution:
            raise KeyError(f"Unknown solver run id: {solver_run_id}")
        return self._solver_to_execution[solver_run_id]

    def list_candidate_nodes(self, solver_run_id: str) -> list[SolverNode]:
        return [node for node in self.list_nodes(solver_run_id) if node.metadata.candidate_state == CommitStatus.CANDIDATE]

    def list_committed_nodes(self, solver_run_id: str) -> list[SolverNode]:
        return [node for node in self.list_nodes(solver_run_id) if node.metadata.candidate_state == CommitStatus.COMMITTED]

    def list_candidate_edges(self, solver_run_id: str) -> list[SolverEdge]:
        return [edge for edge in self.list_edges(solver_run_id) if edge.metadata.candidate_state == CommitStatus.CANDIDATE]

    def list_committed_edges(self, solver_run_id: str) -> list[SolverEdge]:
        return [edge for edge in self.list_edges(solver_run_id) if edge.metadata.candidate_state == CommitStatus.COMMITTED]

    def get_local_neighborhood(
        self,
        solver_run_id: str,
        node_ids: list[str],
        depth: int,
    ) -> tuple[list[SolverNode], list[SolverEdge]]:
        if depth < 0:
            raise ValueError("depth must be >= 0")

        adjacency: dict[str, set[str]] = defaultdict(set)
        edges: list[SolverEdge] = self.list_edges(solver_run_id)
        for edge in edges:
            adjacency[edge.src].add(edge.dst)
            adjacency[edge.dst].add(edge.src)

        seen: set[str] = set(node_ids)
        queue: deque[tuple[str, int]] = deque((node_id, 0) for node_id in node_ids)

        while queue:
            node_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for next_node in adjacency.get(node_id, set()):
                if next_node not in seen:
                    seen.add(next_node)
                    queue.append((next_node, current_depth + 1))

        neighborhood_nodes: list[SolverNode] = [
            node for node_id in seen if (node := self.get_node(solver_run_id, node_id)) is not None
        ]

        neighborhood_edges: list[SolverEdge] = [
            edge for edge in edges if edge.src in seen and edge.dst in seen
        ]

        return neighborhood_nodes, neighborhood_edges
