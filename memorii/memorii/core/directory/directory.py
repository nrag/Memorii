"""Memory directory service for cross-memory mappings."""

from memorii.core.directory.indexes import DirectoryIndexes
from memorii.domain.directory import (
    AgentMemoryPartitionLink,
    ExecutionNodeSolverLink,
    TaskExecutionGraphLink,
    TranscriptTaskLink,
    WritebackSourceLink,
)


class MemoryDirectory:
    def __init__(self, indexes: DirectoryIndexes | None = None) -> None:
        self._indexes = indexes or DirectoryIndexes()

    def map_task_to_execution_graph(self, task_id: str, execution_graph_id: str) -> None:
        self._indexes.task_to_execution_graph[task_id] = TaskExecutionGraphLink(
            task_id=task_id,
            execution_graph_id=execution_graph_id,
        )

    def get_execution_graph_id(self, task_id: str) -> str | None:
        link = self._indexes.task_to_execution_graph.get(task_id)
        return None if link is None else link.execution_graph_id

    def map_execution_node_to_solver_run(self, task_id: str, execution_node_id: str, solver_run_id: str) -> None:
        links = self._indexes.execution_to_solver_runs[execution_node_id]
        existing = {link.solver_run_id for link in links}
        if solver_run_id not in existing:
            links.append(
                ExecutionNodeSolverLink(
                    task_id=task_id,
                    execution_node_id=execution_node_id,
                    solver_run_id=solver_run_id,
                )
            )

    def list_solver_runs_for_execution_node(self, execution_node_id: str) -> list[str]:
        return sorted(link.solver_run_id for link in self._indexes.execution_to_solver_runs.get(execution_node_id, []))

    def map_transcript_to_task(self, task_id: str, *, thread_id: str | None = None, session_id: str | None = None) -> None:
        link = TranscriptTaskLink(task_id=task_id, thread_id=thread_id, session_id=session_id)
        if thread_id is not None:
            self._indexes.thread_to_task[thread_id] = link
        if session_id is not None:
            self._indexes.session_to_task[session_id] = link

    def get_task_for_thread(self, thread_id: str) -> str | None:
        link = self._indexes.thread_to_task.get(thread_id)
        return None if link is None else link.task_id

    def get_task_for_session(self, session_id: str) -> str | None:
        link = self._indexes.session_to_task.get(session_id)
        return None if link is None else link.task_id

    def map_agent_partition(self, agent_id: str, partition_key: str) -> None:
        links = self._indexes.agent_to_partitions[agent_id]
        if partition_key not in {item.partition_key for item in links}:
            links.append(AgentMemoryPartitionLink(agent_id=agent_id, partition_key=partition_key))

    def list_partitions_for_agent(self, agent_id: str) -> list[str]:
        return sorted(item.partition_key for item in self._indexes.agent_to_partitions.get(agent_id, []))

    def map_writeback_source(
        self,
        candidate_id: str,
        task_id: str,
        *,
        solver_run_id: str | None = None,
        execution_node_id: str | None = None,
    ) -> None:
        self._indexes.writeback_sources[candidate_id] = WritebackSourceLink(
            candidate_id=candidate_id,
            task_id=task_id,
            solver_run_id=solver_run_id,
            execution_node_id=execution_node_id,
        )

    def get_writeback_source(self, candidate_id: str) -> WritebackSourceLink | None:
        return self._indexes.writeback_sources.get(candidate_id)
