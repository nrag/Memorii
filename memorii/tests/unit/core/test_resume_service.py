from datetime import UTC, datetime

from memorii.core.persistence.resume import ResumeService
from memorii.domain.common import SolverEdgeMetadata, SolverNodeMetadata
from memorii.domain.enums import (
    CommitStatus,
    ConfidenceClass,
    ExecutionEdgeType,
    ExecutionNodeStatus,
    ExecutionNodeType,
    SolverCreatedBy,
    SolverEdgeType,
    SolverNodeStatus,
    SolverNodeType,
)
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion
from memorii.stores.execution_graph import InMemoryExecutionGraphStore
from memorii.stores.overlays import InMemoryOverlayStore
from memorii.stores.solver_graph import InMemorySolverGraphStore


def _exec_node(node_id: str, status: ExecutionNodeStatus) -> ExecutionNode:
    return ExecutionNode(
        id=node_id,
        type=ExecutionNodeType.WORK_ITEM,
        title=node_id,
        description=node_id,
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _solver_node(node_id: str, node_type: SolverNodeType) -> SolverNode:
    return SolverNode(
        id=node_id,
        type=node_type,
        content={"text": node_id},
        metadata=SolverNodeMetadata(
            created_at=datetime.now(UTC),
            created_by=SolverCreatedBy.SYSTEM,
            candidate_state=CommitStatus.CANDIDATE,
        ),
    )


def _solver_edge(edge_id: str, src: str, dst: str) -> SolverEdge:
    return SolverEdge(
        id=edge_id,
        src=src,
        dst=dst,
        type=SolverEdgeType.SUPPORTS,
        metadata=SolverEdgeMetadata(
            created_at=datetime.now(UTC),
            created_by=SolverCreatedBy.SYSTEM,
            candidate_state=CommitStatus.COMMITTED,
            confidence_class=ConfidenceClass.OBSERVED,
        ),
    )


def test_resume_reconstructs_required_solver_state() -> None:
    execution_store = InMemoryExecutionGraphStore()
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()

    execution_store.upsert_node("t1", _exec_node("ex1", ExecutionNodeStatus.RUNNING))
    execution_store.upsert_node("t1", _exec_node("ex2", ExecutionNodeStatus.WAITING))
    execution_store.upsert_edge(
        "t1",
        ExecutionEdge(
            id="ee1",
            src="ex1",
            dst="ex2",
            type=ExecutionEdgeType.DEPENDS_ON,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )

    solver_store.create_solver_run("solver-1", "ex1")
    solver_store.upsert_node("solver-1", _solver_node("q1", SolverNodeType.QUESTION))
    solver_store.upsert_node("solver-1", _solver_node("o1", SolverNodeType.OBSERVATION))
    solver_store.upsert_node("solver-1", _solver_node("h1", SolverNodeType.HYPOTHESIS))
    solver_store.upsert_edge("solver-1", _solver_edge("se1", "h1", "o1"))

    overlay_store.append_overlay_version(
        SolverOverlayVersion(
            version_id="v1",
            solver_run_id="solver-1",
            created_at=datetime.now(UTC),
            node_overlays=[
                SolverNodeOverlay(
                    node_id="h1",
                    belief=0.7,
                    status=SolverNodeStatus.REOPENABLE,
                    is_frontier=True,
                    reopenable=True,
                    updated_at=datetime.now(UTC),
                ),
                SolverNodeOverlay(
                    node_id="o1",
                    belief=0.3,
                    status=SolverNodeStatus.ACTIVE,
                    unexplained=True,
                    updated_at=datetime.now(UTC),
                ),
                SolverNodeOverlay(
                    node_id="q1",
                    belief=0.2,
                    status=SolverNodeStatus.NEEDS_TEST,
                    updated_at=datetime.now(UTC),
                ),
            ],
        )
    )

    service = ResumeService(execution_store, solver_store, overlay_store)

    execution_state = service.load_execution_graph("t1")
    assert execution_state.status_by_node["ex1"] == "RUNNING"
    assert len(execution_state.edges) == 1

    solver_state = service.load_solver_graph("solver-1")
    assert solver_state.execution_node_id == "ex1"
    assert solver_state.active_frontier == ["h1"]
    assert solver_state.unresolved_questions == ["q1"]
    assert solver_state.unexplained_observations == ["o1"]
    assert solver_state.reopenable_branches == ["h1"]
    assert solver_state.latest_overlay.version_id == "v1"


def test_resume_prefers_latest_committed_overlay() -> None:
    execution_store = InMemoryExecutionGraphStore()
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()

    solver_store.create_solver_run("solver-2", "ex1")
    solver_store.upsert_node("solver-2", _solver_node("q2", SolverNodeType.QUESTION))

    overlay_store.append_overlay_version(
        SolverOverlayVersion(
            version_id="v-committed",
            solver_run_id="solver-2",
            created_at=datetime.now(UTC),
            committed=True,
            node_overlays=[
                SolverNodeOverlay(
                    node_id="q2",
                    belief=0.6,
                    status=SolverNodeStatus.NEEDS_TEST,
                    updated_at=datetime.now(UTC),
                )
            ],
        )
    )
    overlay_store.append_overlay_version(
        SolverOverlayVersion(
            version_id="v-candidate",
            solver_run_id="solver-2",
            created_at=datetime.now(UTC),
            committed=False,
            node_overlays=[
                SolverNodeOverlay(
                    node_id="q2",
                    belief=0.2,
                    status=SolverNodeStatus.RESOLVED,
                    updated_at=datetime.now(UTC),
                )
            ],
        )
    )

    service = ResumeService(execution_store, solver_store, overlay_store)
    solver_state = service.load_solver_graph("solver-2")

    assert solver_state.latest_overlay.version_id == "v-committed"
    assert solver_state.unresolved_questions == ["q2"]
