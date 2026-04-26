"""Schemas for next-step engine requests and responses."""

from pydantic import BaseModel, ConfigDict, Field


class NextStepRequest(BaseModel):
    query: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    solver_run_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class NextStepResult(BaseModel):
    next_step: dict[str, object]
    based_on_solver_run_id: str | None = None
    based_on_solver_node_id: str | None = None
    based_on_work_state_id: str | None = None
    planner_used: bool
    planner_reason: str
    candidate_frontier_node_ids: list[str] = Field(default_factory=list)
    requested_solver_run_id: str | None = None
    resolved_solver_run_id: str | None = None
    solver_run_resolution_source: str
    scope: dict[str, str | None] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
