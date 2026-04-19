"""Solver graph edge schemas."""

from pydantic import BaseModel, ConfigDict

from memorii.domain.common import SolverEdgeMetadata
from memorii.domain.enums import SolverEdgeType


class SolverEdge(BaseModel):
    id: str
    src: str
    dst: str
    type: SolverEdgeType
    weight: float | None = None
    metadata: SolverEdgeMetadata

    model_config = ConfigDict(extra="forbid")
