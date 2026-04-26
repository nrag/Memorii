"""Provider tool schemas and typed tool-call contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProviderToolCallResult(BaseModel):
    tool_name: str
    ok: bool
    result: dict[str, object] = Field(default_factory=dict)
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class GetStateSummaryInput(BaseModel):
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class GetNextStepInput(BaseModel):
    query: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None

    model_config = ConfigDict(extra="forbid")
