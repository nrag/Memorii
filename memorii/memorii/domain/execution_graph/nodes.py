"""Execution graph node schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.enums import ExecutionNodeStatus, ExecutionNodeType


class ExecutionNode(BaseModel):
    id: str
    type: ExecutionNodeType
    title: str
    description: str
    status: ExecutionNodeStatus
    acceptance_criteria: list[str] = Field(default_factory=list)
    linked_artifacts: list[str] = Field(default_factory=list)
    linked_constraints: list[str] = Field(default_factory=list)
    owner: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")
