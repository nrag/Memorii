"""Resume-oriented solver runtime snapshots."""

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverOverlayVersion


class ExecutionResumeState(BaseModel):
    task_id: str
    nodes: list[ExecutionNode] = Field(default_factory=list)
    edges: list[ExecutionEdge] = Field(default_factory=list)
    status_by_node: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class SolverResumeState(BaseModel):
    solver_run_id: str
    execution_node_id: str
    nodes: list[SolverNode] = Field(default_factory=list)
    edges: list[SolverEdge] = Field(default_factory=list)
    active_frontier: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    unexplained_observations: list[str] = Field(default_factory=list)
    reopenable_branches: list[str] = Field(default_factory=list)
    latest_overlay: SolverOverlayVersion | None = None

    model_config = ConfigDict(extra="forbid")
