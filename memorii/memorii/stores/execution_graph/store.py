"""In-memory execution graph store."""

from collections import defaultdict

from memorii.domain.enums import ExecutionEdgeType
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.stores.base.interfaces import ExecutionGraphStore


class InMemoryExecutionGraphStore(ExecutionGraphStore):
    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, ExecutionNode]] = defaultdict(dict)
        self._edges: dict[str, dict[str, ExecutionEdge]] = defaultdict(dict)

    def upsert_node(self, task_id: str, node: ExecutionNode) -> None:
        self._nodes[task_id][node.id] = node

    def upsert_edge(self, task_id: str, edge: ExecutionEdge) -> None:
        self._edges[task_id][edge.id] = edge

    def get_node(self, task_id: str, node_id: str) -> ExecutionNode | None:
        return self._nodes.get(task_id, {}).get(node_id)

    def get_edge(self, task_id: str, edge_id: str) -> ExecutionEdge | None:
        return self._edges.get(task_id, {}).get(edge_id)

    def list_nodes(self, task_id: str) -> list[ExecutionNode]:
        return list(self._nodes.get(task_id, {}).values())

    def list_edges(self, task_id: str) -> list[ExecutionEdge]:
        return list(self._edges.get(task_id, {}).values())

    def get_children(self, task_id: str, node_id: str) -> list[ExecutionNode]:
        child_ids: list[str] = [
            edge.dst
            for edge in self._edges.get(task_id, {}).values()
            if edge.src == node_id
        ]
        return [node for child_id in child_ids if (node := self.get_node(task_id, child_id)) is not None]

    def get_parents(self, task_id: str, node_id: str) -> list[ExecutionNode]:
        parent_ids: list[str] = [
            edge.src
            for edge in self._edges.get(task_id, {}).values()
            if edge.dst == node_id
        ]
        return [node for parent_id in parent_ids if (node := self.get_node(task_id, parent_id)) is not None]

    def get_dependencies(self, task_id: str, node_id: str) -> list[ExecutionNode]:
        dependency_ids: list[str] = [
            edge.dst
            for edge in self._edges.get(task_id, {}).values()
            if edge.src == node_id and edge.type == ExecutionEdgeType.DEPENDS_ON
        ]
        return [node for dep_id in dependency_ids if (node := self.get_node(task_id, dep_id)) is not None]

    def get_status_snapshot(self, task_id: str) -> dict[str, str]:
        return {node.id: node.status.value for node in self._nodes.get(task_id, {}).values()}
