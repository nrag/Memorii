"""Execution graph edge schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from memorii.domain.enums import ExecutionEdgeType


class ExecutionEdge(BaseModel):
    id: str
    src: str
    dst: str
    type: ExecutionEdgeType
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")
