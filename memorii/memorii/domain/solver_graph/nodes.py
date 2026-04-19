"""Solver graph node schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import SolverNodeType


class SolverNode(BaseModel):
    id: str
    type: SolverNodeType
    content: dict[str, Any]
    metadata: SolverNodeMetadata

    model_config = ConfigDict(extra="forbid")
