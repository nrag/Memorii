"""Framework-neutral store interfaces for Memorii v1."""

from abc import ABC, abstractmethod

from memorii.domain.events import EventRecord
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.memory_object import MemoryObject
from memorii.domain.directory import WritebackSourceLink
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion


class MemoryObjectStore(ABC):
    @abstractmethod
    def put(self, memory_object: MemoryObject) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str) -> MemoryObject | None:
        raise NotImplementedError


class ExecutionGraphStore(ABC):
    @abstractmethod
    def upsert_node(self, task_id: str, node: ExecutionNode) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_edge(self, task_id: str, edge: ExecutionEdge) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_node(self, task_id: str, node_id: str) -> ExecutionNode | None:
        raise NotImplementedError

    @abstractmethod
    def get_edge(self, task_id: str, edge_id: str) -> ExecutionEdge | None:
        raise NotImplementedError

    @abstractmethod
    def list_nodes(self, task_id: str) -> list[ExecutionNode]:
        raise NotImplementedError

    @abstractmethod
    def list_edges(self, task_id: str) -> list[ExecutionEdge]:
        raise NotImplementedError

    @abstractmethod
    def get_children(self, task_id: str, node_id: str) -> list[ExecutionNode]:
        raise NotImplementedError

    @abstractmethod
    def get_parents(self, task_id: str, node_id: str) -> list[ExecutionNode]:
        raise NotImplementedError

    @abstractmethod
    def get_dependencies(self, task_id: str, node_id: str) -> list[ExecutionNode]:
        raise NotImplementedError

    @abstractmethod
    def get_status_snapshot(self, task_id: str) -> dict[str, str]:
        raise NotImplementedError


class SolverGraphStore(ABC):
    @abstractmethod
    def create_solver_run(self, solver_run_id: str, execution_node_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_node(self, solver_run_id: str, node: SolverNode) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_edge(self, solver_run_id: str, edge: SolverEdge) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_node(self, solver_run_id: str, node_id: str) -> SolverNode | None:
        raise NotImplementedError

    @abstractmethod
    def get_edge(self, solver_run_id: str, edge_id: str) -> SolverEdge | None:
        raise NotImplementedError

    @abstractmethod
    def list_nodes(self, solver_run_id: str) -> list[SolverNode]:
        raise NotImplementedError

    @abstractmethod
    def list_edges(self, solver_run_id: str) -> list[SolverEdge]:
        raise NotImplementedError

    @abstractmethod
    def list_by_execution_node(self, execution_node_id: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def get_execution_node_id(self, solver_run_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def list_candidate_nodes(self, solver_run_id: str) -> list[SolverNode]:
        raise NotImplementedError

    @abstractmethod
    def list_committed_nodes(self, solver_run_id: str) -> list[SolverNode]:
        raise NotImplementedError

    @abstractmethod
    def list_candidate_edges(self, solver_run_id: str) -> list[SolverEdge]:
        raise NotImplementedError

    @abstractmethod
    def list_committed_edges(self, solver_run_id: str) -> list[SolverEdge]:
        raise NotImplementedError

    @abstractmethod
    def get_local_neighborhood(
        self,
        solver_run_id: str,
        node_ids: list[str],
        depth: int,
    ) -> tuple[list[SolverNode], list[SolverEdge]]:
        raise NotImplementedError


class EventLogStore(ABC):
    @abstractmethod
    def append(self, event: EventRecord) -> bool:
        raise NotImplementedError

    @abstractmethod
    def append_many(self, events: list[EventRecord]) -> list[bool]:
        raise NotImplementedError

    @abstractmethod
    def get_by_event_id(self, event_id: str) -> EventRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_by_task(self, task_id: str) -> list[EventRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_by_solver_run(self, solver_run_id: str) -> list[EventRecord]:
        raise NotImplementedError


class OverlayStore(ABC):
    @abstractmethod
    def append_overlay_version(self, overlay: SolverOverlayVersion) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_versions(self, solver_run_id: str) -> list[SolverOverlayVersion]:
        raise NotImplementedError

    @abstractmethod
    def get_latest_version(self, solver_run_id: str) -> SolverOverlayVersion | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_for_node(self, solver_run_id: str, node_id: str) -> SolverOverlayVersion | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_node_overlay(self, solver_run_id: str, node_id: str) -> SolverNodeOverlay | None:
        raise NotImplementedError


class DirectoryStore(ABC):
    @abstractmethod
    def map_task_to_execution_graph(self, task_id: str, graph_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_execution_graph_id(self, task_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def map_execution_node_to_solver_run(self, task_id: str, execution_node_id: str, solver_run_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_solver_runs_for_execution_node(self, execution_node_id: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def map_transcript_to_task(self, task_id: str, *, thread_id: str | None = None, session_id: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_task_for_thread(self, thread_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_task_for_session(self, session_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def map_agent_partition(self, agent_id: str, partition_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_partitions_for_agent(self, agent_id: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def map_writeback_source(
        self,
        candidate_id: str,
        task_id: str,
        *,
        solver_run_id: str | None = None,
        execution_node_id: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_writeback_source(self, candidate_id: str) -> WritebackSourceLink | None:
        raise NotImplementedError
