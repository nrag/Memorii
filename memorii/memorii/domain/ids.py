"""ID utilities for Memorii entities."""

from typing import NewType
from uuid import uuid4

MemoryId = NewType("MemoryId", str)
NodeId = NewType("NodeId", str)
EdgeId = NewType("EdgeId", str)
EventId = NewType("EventId", str)
TaskId = NewType("TaskId", str)
ExecutionNodeId = NewType("ExecutionNodeId", str)
SolverGraphId = NewType("SolverGraphId", str)
DedupeKey = NewType("DedupeKey", str)


def _new_uuid() -> str:
    return str(uuid4())


def new_memory_id() -> MemoryId:
    return MemoryId(_new_uuid())


def new_node_id() -> NodeId:
    return NodeId(_new_uuid())


def new_edge_id() -> EdgeId:
    return EdgeId(_new_uuid())


def new_event_id() -> EventId:
    return EventId(_new_uuid())


def new_task_id() -> TaskId:
    return TaskId(_new_uuid())


def new_execution_node_id() -> ExecutionNodeId:
    return ExecutionNodeId(_new_uuid())


def new_solver_graph_id() -> SolverGraphId:
    return SolverGraphId(_new_uuid())


def new_dedupe_key() -> DedupeKey:
    return DedupeKey(_new_uuid())
