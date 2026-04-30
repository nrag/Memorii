"""Shared schemas for LLM decision points, traces, and eval metadata."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class LLMDecisionPoint(str, Enum):
    PROMOTION = "promotion"
    BELIEF_UPDATE = "belief_update"
    MEMORY_EXTRACTION = "memory_extraction"
    CONFLICT_DETECTION = "conflict_detection"
    DECISION_SUMMARY = "decision_summary"


class LLMDecisionMode(str, Enum):
    RULE = "rule"
    RULE_BASED = "rule"
    LLM = "llm"
    HYBRID = "hybrid"


class LLMDecisionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FALLBACK_USED = "fallback_used"
    VALIDATION_FAILED = "validation_failed"
    PROVIDER_ERROR = "provider_error"


class LLMDecisionTrace(BaseModel):
    trace_id: str
    decision_point: LLMDecisionPoint
    mode: LLMDecisionMode
    prompt_version: str | None = None
    model_name: str | None = None
    input_payload: dict[str, object]
    raw_output: str | None = None
    parsed_output: dict[str, object] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    final_output: dict[str, object]
    status: LLMDecisionStatus
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class EvalSnapshot(BaseModel):
    snapshot_id: str
    decision_point: LLMDecisionPoint
    input_payload: dict[str, object]
    expected_output: dict[str, object] | None = None
    source: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class JudgeVerdict(BaseModel):
    judge_id: str
    passed: bool
    score: float | None = None
    rationale: str | None = None

    model_config = ConfigDict(extra="forbid")


class JuryVerdict(BaseModel):
    snapshot_id: str
    decision_point: LLMDecisionPoint
    judge_verdicts: list[JudgeVerdict]
    passed: bool
    aggregate_score: float | None = None
    disagreement: bool = False
    needs_human_review: bool = False

    model_config = ConfigDict(extra="forbid")


class GoldenCandidate(BaseModel):
    candidate_id: str
    snapshot_id: str
    decision_point: LLMDecisionPoint
    reason: str
    priority: float = 0.5
    created_at: datetime

    model_config = ConfigDict(extra="forbid")
