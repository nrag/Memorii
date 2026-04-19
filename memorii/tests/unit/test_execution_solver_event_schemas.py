from datetime import UTC, datetime

from memorii.domain.common import SolverEdgeMetadata, SolverNodeMetadata
from memorii.domain.enums import (
    CommitStatus,
    ConfidenceClass,
    EventType,
    ExecutionEdgeType,
    ExecutionNodeStatus,
    ExecutionNodeType,
    SolverCreatedBy,
    SolverEdgeType,
    SolverNodeType,
)
from memorii.domain.events import EventRecord
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode


def test_execution_models_serialize() -> None:
    node = ExecutionNode(
        id="n1",
        type=ExecutionNodeType.WORK_ITEM,
        title="Implement schema",
        description="Create execution node schema",
        status=ExecutionNodeStatus.READY,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    edge = ExecutionEdge(
        id="e1",
        src="n1",
        dst="n2",
        type=ExecutionEdgeType.DEPENDS_ON,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert node.model_dump(mode="json")["type"] == "WORK_ITEM"
    assert edge.model_dump(mode="json")["type"] == "DEPENDS_ON"


def test_solver_models_serialize() -> None:
    node = SolverNode(
        id="s1",
        type=SolverNodeType.HYPOTHESIS,
        content={"text": "possible root cause"},
        metadata=SolverNodeMetadata(
            created_at=datetime.now(UTC),
            created_by=SolverCreatedBy.MODEL,
            candidate_state=CommitStatus.CANDIDATE,
        ),
    )
    edge = SolverEdge(
        id="se1",
        src="s1",
        dst="s2",
        type=SolverEdgeType.SUPPORTS,
        metadata=SolverEdgeMetadata(
            created_at=datetime.now(UTC),
            created_by=SolverCreatedBy.MODEL,
            candidate_state=CommitStatus.CANDIDATE,
            confidence_class=ConfidenceClass.SPECULATIVE,
        ),
    )

    assert node.model_dump(mode="json")["type"] == "HYPOTHESIS"
    assert edge.model_dump(mode="json")["type"] == "SUPPORTS"


def test_event_record_requires_dedupe_key() -> None:
    event = EventRecord(
        event_id="ev1",
        event_type=EventType.TASK_STARTED,
        timestamp=datetime.now(UTC),
        task_id="t1",
        actor_id="system",
        payload={"goal": "bootstrap"},
        dedupe_key="dedupe-1",
    )

    serialized = event.model_dump(mode="json")
    assert serialized["event_type"] == "TASK_STARTED"
    assert serialized["dedupe_key"] == "dedupe-1"
