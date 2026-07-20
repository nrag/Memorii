"""Provider-facing assessment contracts for promotion candidates."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.evidence_quality import EvidenceQualitySignals


class PromotionCandidateType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    USER_MEMORY = "user_memory"
    PROJECT_FACT = "project_fact"


class PromotionReason(StrEnum):
    EXPLICIT_USER_MEMORY_REQUEST = "explicit_user_memory_request"
    TASK_OUTCOME = "task_outcome"
    INVESTIGATION_CONCLUSION = "investigation_conclusion"
    DECISION_FINALIZED = "decision_finalized"
    REPEATED_ACROSS_EPISODES = "repeated_across_episodes"
    OBSERVATION_NOT_PROMOTED = "observation_not_promoted"
    DUPLICATE_OR_MERGE_NEEDED = "duplicate_or_merge_needed"
    AMBIGUOUS_SCOPE = "ambiguous_scope"
    WRONG_PLANE_RISK = "wrong_plane_risk"


class PromotionFailureMode(StrEnum):
    NOISE = "noise"
    ONE_OFF_PREFERENCE = "one_off_preference"
    UNSUPPORTED_INFERENCE = "unsupported_inference"
    SPECULATIVE_CLAIM = "speculative_claim"
    INSUFFICIENT_REPETITION = "insufficient_repetition"
    AMBIGUOUS_SCOPE = "ambiguous_scope"
    TEMPORAL_SCOPE = "temporal_scope"
    ATTRIBUTION_UNCLEAR = "attribution_unclear"
    WRONG_PLANE_RISK = "wrong_plane_risk"
    DUPLICATE_OR_MERGE_NEEDED = "duplicate_or_merge_needed"


class _PromotionAssessmentFields(BaseModel):
    promote: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: PromotionReason
    rationale: str

    model_config = ConfigDict(extra="forbid")


class PromotionAssessmentOutput(_PromotionAssessmentFields):
    """Strict provider transport returned by the promotion prompt."""

    target_plane: PromotionCandidateType | None
    failure_mode: PromotionFailureMode | None
    requires_judge_review: bool


class PromotionAssessment(_PromotionAssessmentFields):
    """Internal decision enriched with deterministic defaults and trace data."""

    target_plane: PromotionCandidateType | None = None
    failure_mode: PromotionFailureMode | None = None
    requires_judge_review: bool = False
    merge_with_memory_id: str | None = None
    supersede_memory_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    trace_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class PromotionAssessmentContext(BaseModel):
    candidate_id: str
    candidate_type: PromotionCandidateType
    content: str
    source_ids: list[str] = Field(default_factory=list)
    related_memory_ids: list[str] = Field(default_factory=list)
    repeated_across_episodes: int = 0
    explicit_user_memory_request: bool = False
    created_from: str
    evidence_quality: EvidenceQualitySignals = Field(default_factory=EvidenceQualitySignals)
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    def prompt_payload(self) -> dict[str, object]:
        """Return semantic promotion inputs without untyped control metadata."""

        return self.model_dump(mode="json", exclude={"metadata"})


__all__ = [
    "PromotionCandidateType",
    "PromotionAssessmentContext",
    "PromotionAssessment",
    "PromotionAssessmentOutput",
    "PromotionFailureMode",
    "PromotionReason",
]
