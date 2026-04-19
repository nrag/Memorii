from datetime import UTC, datetime

from memorii.domain.common import SolverEdgeMetadata, SolverNodeMetadata
from memorii.domain.enums import CommitStatus, ConfidenceClass, SolverCreatedBy, SolverEdgeType, SolverNodeType
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.stores.solver_graph import InMemorySolverGraphStore


def _solver_node(node_id: str, node_type: SolverNodeType, state: CommitStatus) -> SolverNode:
    return SolverNode(
        id=node_id,
        type=node_type,
        content={"text": node_id},
        metadata=SolverNodeMetadata(
            created_at=datetime.now(UTC),
            created_by=SolverCreatedBy.MODEL,
            candidate_state=state,
        ),
    )


def _solver_edge(edge_id: str, src: str, dst: str, state: CommitStatus) -> SolverEdge:
    return SolverEdge(
        id=edge_id,
        src=src,
        dst=dst,
        type=SolverEdgeType.SUPPORTS,
        metadata=SolverEdgeMetadata(
            created_at=datetime.now(UTC),
            created_by=SolverCreatedBy.MODEL,
            candidate_state=state,
            confidence_class=ConfidenceClass.INFERRED,
        ),
    )


def test_solver_graph_persistence_and_candidate_committed_distinction() -> None:
    store = InMemorySolverGraphStore()
    store.create_solver_run("solver-1", "exec-1")

    n1 = _solver_node("s1", SolverNodeType.HYPOTHESIS, CommitStatus.CANDIDATE)
    n2 = _solver_node("s2", SolverNodeType.OBSERVATION, CommitStatus.COMMITTED)
    e1 = _solver_edge("se1", "s1", "s2", CommitStatus.CANDIDATE)
    e2 = _solver_edge("se2", "s2", "s1", CommitStatus.COMMITTED)

    store.upsert_node("solver-1", n1)
    store.upsert_node("solver-1", n2)
    store.upsert_edge("solver-1", e1)
    store.upsert_edge("solver-1", e2)

    assert store.get_execution_node_id("solver-1") == "exec-1"
    assert store.list_by_execution_node("exec-1") == ["solver-1"]
    assert [node.id for node in store.list_candidate_nodes("solver-1")] == ["s1"]
    assert [node.id for node in store.list_committed_nodes("solver-1")] == ["s2"]
    assert [edge.id for edge in store.list_candidate_edges("solver-1")] == ["se1"]
    assert [edge.id for edge in store.list_committed_edges("solver-1")] == ["se2"]


def test_solver_local_neighborhood_by_depth() -> None:
    store = InMemorySolverGraphStore()
    store.create_solver_run("solver-2", "exec-2")
    store.upsert_node("solver-2", _solver_node("a", SolverNodeType.HYPOTHESIS, CommitStatus.CANDIDATE))
    store.upsert_node("solver-2", _solver_node("b", SolverNodeType.OBSERVATION, CommitStatus.COMMITTED))
    store.upsert_node("solver-2", _solver_node("c", SolverNodeType.ACTION, CommitStatus.CANDIDATE))
    store.upsert_edge("solver-2", _solver_edge("ab", "a", "b", CommitStatus.COMMITTED))
    store.upsert_edge("solver-2", _solver_edge("bc", "b", "c", CommitStatus.COMMITTED))

    nodes_depth_1, _ = store.get_local_neighborhood("solver-2", ["a"], depth=1)
    nodes_depth_2, edges_depth_2 = store.get_local_neighborhood("solver-2", ["a"], depth=2)

    assert {n.id for n in nodes_depth_1} == {"a", "b"}
    assert {n.id for n in nodes_depth_2} == {"a", "b", "c"}
    assert {e.id for e in edges_depth_2} == {"ab", "bc"}
