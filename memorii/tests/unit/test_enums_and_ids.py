from memorii.domain.enums import (
    CommitStatus,
    EventType,
    ExecutionEdgeType,
    ExecutionNodeStatus,
    ExecutionNodeType,
    MemoryDomain,
    SolverEdgeType,
    SolverNodeType,
)
from memorii.domain.ids import (
    new_edge_id,
    new_event_id,
    new_memory_id,
    new_node_id,
    new_solver_graph_id,
    new_task_id,
)


def test_core_enums_include_required_values() -> None:
    assert MemoryDomain.TRANSCRIPT.value == "transcript"
    assert CommitStatus.CANDIDATE.value == "candidate"
    assert ExecutionNodeType.WORK_ITEM.value == "WORK_ITEM"
    assert ExecutionEdgeType.DEPENDS_ON.value == "DEPENDS_ON"
    assert ExecutionNodeStatus.DONE.value == "DONE"
    assert SolverNodeType.HYPOTHESIS.value == "HYPOTHESIS"
    assert SolverEdgeType.SUPPORTS.value == "SUPPORTS"
    assert EventType.ACTION_COMPLETED.value == "ACTION_COMPLETED"


def test_uuid_id_generators_return_unique_string_values() -> None:
    generated_ids = {
        str(new_memory_id()),
        str(new_node_id()),
        str(new_edge_id()),
        str(new_event_id()),
        str(new_task_id()),
        str(new_solver_graph_id()),
    }
    assert len(generated_ids) == 6
