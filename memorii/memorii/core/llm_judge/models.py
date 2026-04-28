"""Models for single-dimension LLM judges, jury aggregation, and calibration."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class JudgeDimension(str, Enum):
    PROMOTION_PRECISION = "promotion_precision"
    TEMPORAL_VALIDITY = "temporal_validity"
    ATTRIBUTION = "attribution"
    BELIEF_DIRECTION = "belief_direction"
    MEMORY_PLANE = "memory_plane"
    BELIEF_CALIBRATION = "belief_calibration"
    EVIDENCE_RELEVANCE = "evidence_relevance"
    MISSING_EVIDENCE = "missing_evidence"
    ABSTRACTION_LEVEL = "abstraction_level"
    RECENCY_SUPERSESSION = "recency_supersession"
    DUPLICATE_MERGE = "duplicate_merge"
    CONFLICT_HANDLING = "conflict_handling"
    NEGATIVE_MEMORY = "negative_memory"
    RATIONALE_GROUNDING = "rationale_grounding"
    VERIFIER_OVERRIDE = "verifier_override"


class JudgeVerdict(BaseModel):
    verdict_id: str
    judge_id: str
    dimension: JudgeDimension
    snapshot_id: str | None = None
    trace_id: str | None = None
    passed: bool
    score: float
    rationale: str
    failure_mode: str | None = None
    needs_human_review: bool = False
    created_at: datetime

    model_config = ConfigDict(extra="forbid")

    @field_validator("score")
    @classmethod
    def _validate_score(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
        return value


class JuryVerdict(BaseModel):
    jury_id: str
    snapshot_id: str | None = None
    trace_id: str | None = None
    verdicts: list[JudgeVerdict]
    passed: bool
    aggregate_score: float
    disagreement: bool = False
    needs_human_review: bool = False
    created_at: datetime

    model_config = ConfigDict(extra="forbid")

    @field_validator("aggregate_score")
    @classmethod
    def _validate_aggregate_score(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("aggregate_score must be between 0.0 and 1.0")
        return value


class JudgeRubric(BaseModel):
    judge_id: str
    dimension: JudgeDimension
    name: str
    description: str
    score_1_anchor: str
    score_0_5_anchor: str
    score_0_anchor: str
    pass_threshold: float = 0.7
    failure_modes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("pass_threshold")
    @classmethod
    def _validate_pass_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("pass_threshold must be between 0.0 and 1.0")
        return value


class CalibrationExample(BaseModel):
    example_id: str
    dimension: JudgeDimension
    input_payload: dict[str, object]
    expected_passed: bool
    expected_score_min: float
    expected_score_max: float
    expected_failure_mode: str | None = None
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("expected_score_min", "expected_score_max")
    @classmethod
    def _validate_expected_scores(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("expected score bounds must be between 0.0 and 1.0")
        return value

    @field_validator("expected_score_max")
    @classmethod
    def _validate_score_range(cls, value: float, info: ValidationInfo) -> float:
        min_score = info.data.get("expected_score_min")
        if min_score is not None and value < min_score:
            raise ValueError("expected_score_max must be >= expected_score_min")
        return value


class JudgeCalibrationReport(BaseModel):
    judge_id: str
    dimension: JudgeDimension
    total_examples: int
    passed_examples: int
    failed_examples: int
    agreement_rate: float
    false_positive_count: int
    false_negative_count: int
    ambiguous_count: int
    failure_mode_counts: dict[str, int]

    model_config = ConfigDict(extra="forbid")

    @field_validator("agreement_rate")
    @classmethod
    def _validate_agreement_rate(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("agreement_rate must be between 0.0 and 1.0")
        return value
