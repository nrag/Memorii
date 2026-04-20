"""In-memory typed indexes for memory directory relationships."""

from collections import defaultdict

from memorii.domain.directory import (
    AgentMemoryPartitionLink,
    ExecutionNodeSolverLink,
    TaskExecutionGraphLink,
    TranscriptTaskLink,
    WritebackSourceLink,
)


class DirectoryIndexes:
    def __init__(self) -> None:
        self.task_to_execution_graph: dict[str, TaskExecutionGraphLink] = {}
        self.execution_to_solver_runs: dict[str, list[ExecutionNodeSolverLink]] = defaultdict(list)
        self.thread_to_task: dict[str, TranscriptTaskLink] = {}
        self.session_to_task: dict[str, TranscriptTaskLink] = {}
        self.agent_to_partitions: dict[str, list[AgentMemoryPartitionLink]] = defaultdict(list)
        self.writeback_sources: dict[str, WritebackSourceLink] = {}
