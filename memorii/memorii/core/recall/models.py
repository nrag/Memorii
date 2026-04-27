"""Structured recall-state models used by provider prefetch."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.decision_state.summary import DecisionStateSummary
from memorii.core.work_state.models import WorkStateKind, WorkStateStatus


class WorkStateEventSummary(BaseModel):
    event_id: str
    work_state_id: str
    event_type: str
    content: str
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class WorkStateSummary(BaseModel):
    work_state_id: str
    kind: WorkStateKind
    status: WorkStateStatus
    title: str
    summary: str
    confidence: float
    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    source_event_ids: list[str] = Field(default_factory=list)
    recent_events: list[WorkStateEventSummary] = Field(default_factory=list)
    latest_progress: str | None = None
    latest_outcome: str | None = None
    decision_state: DecisionStateSummary | None = None

    model_config = ConfigDict(extra="forbid")


class NextStepRecommendation(BaseModel):
    action_type: str
    description: str
    confidence: float | None = None
    reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RecallStateBundle(BaseModel):
    query: str
    memory_context: str
    work_states: list[WorkStateSummary] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    recent_progress: list[str] = Field(default_factory=list)
    recommended_next_steps: list[NextStepRecommendation] = Field(default_factory=list)
    trace: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
