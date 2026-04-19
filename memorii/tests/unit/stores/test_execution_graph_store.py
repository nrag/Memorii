from datetime import UTC, datetime

from memorii.domain.enums import ExecutionEdgeType, ExecutionNodeStatus, ExecutionNodeType
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.stores.execution_graph import InMemoryExecutionGraphStore


def _node(node_id: str, status: ExecutionNodeStatus = ExecutionNodeStatus.READY) -> ExecutionNode:
    return ExecutionNode(
        id=node_id,
        type=ExecutionNodeType.WORK_ITEM,
        title=f"node-{node_id}",
        description="desc",
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_execution_graph_persistence_and_reload() -> None:
    store = InMemoryExecutionGraphStore()
    task_id = "task-1"

    n1 = _node("n1", ExecutionNodeStatus.READY)
    n2 = _node("n2", ExecutionNodeStatus.BLOCKED)
    e1 = ExecutionEdge(
        id="e1",
        src="n1",
        dst="n2",
        type=ExecutionEdgeType.DEPENDS_ON,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    store.upsert_node(task_id, n1)
    store.upsert_node(task_id, n2)
    store.upsert_edge(task_id, e1)

    assert len(store.list_nodes(task_id)) == 2
    assert len(store.list_edges(task_id)) == 1
    assert [node.id for node in store.get_dependencies(task_id, "n1")] == ["n2"]
    assert store.get_status_snapshot(task_id) == {"n1": "READY", "n2": "BLOCKED"}
