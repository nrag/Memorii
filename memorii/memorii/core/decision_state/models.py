"""Decision-state schemas for explicit option/criteria/evidence tracking."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DecisionStatus(str, Enum):
    OPEN = "open"
    DECIDED = "decided"
    ABANDONED = "abandoned"


class DecisionEvidencePolarity(str, Enum):
    FOR_OPTION = "for_option"
    AGAINST_OPTION = "against_option"
    NEUTRAL = "neutral"


class DecisionOption(BaseModel):
    option_id: str
    label: str
    description: str | None = None

    model_config = ConfigDict(extra="forbid")


class DecisionCriterion(BaseModel):
    criterion_id: str
    label: str
    weight: float = 1.0

    model_config = ConfigDict(extra="forbid")


class DecisionEvidence(BaseModel):
    evidence_id: str
    content: str
    option_id: str | None = None
    polarity: DecisionEvidencePolarity
    source_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DecisionState(BaseModel):
    decision_id: str
    work_state_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    question: str
    options: list[DecisionOption] = Field(default_factory=list)
    criteria: list[DecisionCriterion] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    current_recommendation: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    final_decision: str | None = None
    status: DecisionStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")
