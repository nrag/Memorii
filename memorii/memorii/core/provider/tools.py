"""Provider tool schemas and typed tool-call contracts."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.decision_state.models import DecisionEvidencePolarity
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


class WorkOutcome(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ABANDONED = "abandoned"
    NEEDS_FOLLOWUP = "needs_followup"


class RecordProgressInput(BaseModel):
    work_state_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    title: str | None = None
    content: str
    evidence_ids: list[str] = Field(default_factory=list)
    solver_run_id: str | None = None
    execution_node_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class RecordOutcomeInput(BaseModel):
    work_state_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    outcome: WorkOutcome
    content: str
    evidence_ids: list[str] = Field(default_factory=list)
    solver_run_id: str | None = None
    execution_node_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class DecisionAddOptionInput(BaseModel):
    decision_state_id: str
    option_id: str
    label: str
    description: str | None = None

    model_config = ConfigDict(extra="forbid")


class DecisionAddCriterionInput(BaseModel):
    decision_state_id: str
    criterion_id: str
    label: str
    weight: float = 1.0

    model_config = ConfigDict(extra="forbid")


class DecisionAddEvidenceInput(BaseModel):
    decision_state_id: str
    evidence_id: str
    content: str
    polarity: DecisionEvidencePolarity
    option_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DecisionSetRecommendationInput(BaseModel):
    decision_state_id: str
    recommendation: str | None

    model_config = ConfigDict(extra="forbid")


class DecisionFinalizeInput(BaseModel):
    decision_state_id: str
    final_decision: str

    model_config = ConfigDict(extra="forbid")
