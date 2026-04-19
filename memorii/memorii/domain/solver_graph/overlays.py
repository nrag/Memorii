"""Versioned belief and status overlays for solver graph runtime state."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.enums import SolverNodeStatus


class SolverNodeOverlay(BaseModel):
    node_id: str
    belief: float
    status: SolverNodeStatus
    frontier_priority: float | None = None
    is_frontier: bool = False
    unexplained: bool = False
    reopenable: bool = False
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class SolverOverlayVersion(BaseModel):
    version_id: str
    solver_run_id: str
    created_at: datetime
    committed: bool = True
    node_overlays: list[SolverNodeOverlay] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
