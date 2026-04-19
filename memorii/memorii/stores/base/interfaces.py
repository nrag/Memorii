"""Framework-neutral store interfaces for Memorii v1."""

from abc import ABC, abstractmethod
from typing import Protocol

from memorii.domain.events import EventRecord
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.memory_object import MemoryObject
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode


class BaseStore(Protocol):
    """Marker protocol for store contracts."""


class MemoryObjectStore(ABC):
    @abstractmethod
    def put(self, memory_object: MemoryObject) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str) -> MemoryObject | None:
        raise NotImplementedError


class ExecutionGraphStore(ABC):
    @abstractmethod
    def add_node(self, node: ExecutionNode) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_edge(self, edge: ExecutionEdge) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_node(self, node_id: str) -> ExecutionNode | None:
        raise NotImplementedError


class SolverGraphStore(ABC):
    @abstractmethod
    def add_node(self, node: SolverNode) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_edge(self, edge: SolverEdge) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_node(self, node_id: str) -> SolverNode | None:
        raise NotImplementedError


class EventLogStore(ABC):
    @abstractmethod
    def append(self, event: EventRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_by_task(self, task_id: str) -> list[EventRecord]:
        raise NotImplementedError


class DirectoryStore(ABC):
    @abstractmethod
    def map_task_to_execution_graph(self, task_id: str, graph_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_execution_graph_id(self, task_id: str) -> str | None:
        raise NotImplementedError
