"""Provider tool schemas and typed tool-call contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.work_state.models import WorkStateKind


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
    solver_run_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class OpenOrResumeWorkInput(BaseModel):
    title: str
    summary: str | None = None
    kind: WorkStateKind = WorkStateKind.TASK_EXECUTION
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    work_state_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None

    model_config = ConfigDict(extra="forbid")
