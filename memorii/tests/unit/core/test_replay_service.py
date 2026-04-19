from datetime import UTC, datetime

from memorii.core.persistence.replay import ReplayService
from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import CommitStatus, EventType, ExecutionNodeStatus, ExecutionNodeType, SolverCreatedBy, SolverNodeType
from memorii.domain.events import EventRecord
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.stores.event_log import InMemoryEventLogStore


def test_event_append_and_deterministic_replay() -> None:
    event_store = InMemoryEventLogStore()

    exec_node = ExecutionNode(
        id="n1",
        type=ExecutionNodeType.WORK_ITEM,
        title="n1",
        description="n1",
        status=ExecutionNodeStatus.READY,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    solver_node = SolverNode(
        id="s1",
        type=SolverNodeType.HYPOTHESIS,
        content={"text": "hyp"},
        metadata=SolverNodeMetadata(
            created_at=datetime.now(UTC),
            created_by=SolverCreatedBy.MODEL,
            candidate_state=CommitStatus.CANDIDATE,
        ),
    )

    event_store.append(
        EventRecord(
            event_id="e1",
            event_type=EventType.NODE_ADDED,
            timestamp=datetime.now(UTC),
            task_id="t1",
            actor_id="system",
            payload={"graph_type": "execution", "entity": exec_node.model_dump(mode="json")},
            dedupe_key="e1",
        )
    )
    event_store.append(
        EventRecord(
            event_id="e2",
            event_type=EventType.NODE_ADDED,
            timestamp=datetime.now(UTC),
            task_id="t1",
            solver_graph_id="solver-1",
            actor_id="system",
            payload={"graph_type": "solver", "entity": solver_node.model_dump(mode="json")},
            dedupe_key="e2",
        )
    )

    replay = ReplayService(event_store)
    execution_nodes, execution_edges = replay.replay_task_events("t1")
    solver_nodes, solver_edges = replay.replay_solver_events("solver-1")

    assert list(execution_nodes) == ["n1"]
    assert execution_edges == {}
    assert list(solver_nodes) == ["s1"]
    assert solver_edges == {}
