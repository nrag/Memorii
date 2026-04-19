from datetime import UTC, datetime

from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import CommitStatus, ExecutionNodeStatus, ExecutionNodeType, SolverCreatedBy, SolverNodeType
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.stores.execution_graph import InMemoryExecutionGraphStore
from memorii.stores.solver_graph import InMemorySolverGraphStore


def test_execution_and_solver_graphs_remain_distinct() -> None:
    execution_store = InMemoryExecutionGraphStore()
    solver_store = InMemorySolverGraphStore()

    execution_store.upsert_node(
        "task-1",
        ExecutionNode(
            id="exec-node",
            type=ExecutionNodeType.WORK_ITEM,
            title="exec",
            description="exec",
            status=ExecutionNodeStatus.READY,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )

    solver_store.create_solver_run("solver-1", "exec-node")
    solver_store.upsert_node(
        "solver-1",
        SolverNode(
            id="solver-node",
            type=SolverNodeType.HYPOTHESIS,
            content={"text": "solver"},
            metadata=SolverNodeMetadata(
                created_at=datetime.now(UTC),
                created_by=SolverCreatedBy.SYSTEM,
                candidate_state=CommitStatus.CANDIDATE,
            ),
        ),
    )

    assert execution_store.get_node("task-1", "solver-node") is None
    assert solver_store.get_node("solver-1", "exec-node") is None
