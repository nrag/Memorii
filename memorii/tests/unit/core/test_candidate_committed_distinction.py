from datetime import UTC, datetime

from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import CommitStatus, SolverCreatedBy, SolverNodeType
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.stores.solver_graph import InMemorySolverGraphStore


def test_candidate_and_committed_solver_entities_remain_distinct() -> None:
    store = InMemorySolverGraphStore()
    store.create_solver_run("solver-1", "exec-1")

    store.upsert_node(
        "solver-1",
        SolverNode(
            id="candidate",
            type=SolverNodeType.HYPOTHESIS,
            content={"label": "c"},
            metadata=SolverNodeMetadata(
                created_at=datetime.now(UTC),
                created_by=SolverCreatedBy.MODEL,
                candidate_state=CommitStatus.CANDIDATE,
            ),
        ),
    )
    store.upsert_node(
        "solver-1",
        SolverNode(
            id="committed",
            type=SolverNodeType.HYPOTHESIS,
            content={"label": "k"},
            metadata=SolverNodeMetadata(
                created_at=datetime.now(UTC),
                created_by=SolverCreatedBy.SYSTEM,
                candidate_state=CommitStatus.COMMITTED,
            ),
        ),
    )

    assert [node.id for node in store.list_candidate_nodes("solver-1")] == ["candidate"]
    assert [node.id for node in store.list_committed_nodes("solver-1")] == ["committed"]
