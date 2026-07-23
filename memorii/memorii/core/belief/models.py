"""Belief update provider models and strict schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.evidence_quality import EvidenceQualitySignals
from memorii.core.solver.abstention import SolverDecision


class BeliefFailureMode(StrEnum):
    SHOULD_INCREASE = "should_increase"
    SHOULD_DECREASE = "should_decrease"
    SHOULD_NOT_INCREASE = "should_not_increase"
    SHOULD_REMAIN_UNCERTAIN = "should_remain_uncertain"
    AMBIGUOUS_DIRECTION = "ambiguous_direction"
    MISSING_EVIDENCE = "missing_evidence"
    VERIFIER_DOWNGRADE = "verifier_downgrade"
    CONFLICT_PRESENT = "conflict_present"
    EVIDENCE_IRRELEVANT = "evidence_irrelevant"


class BeliefUpdateContext(BaseModel):
    prior_belief: float | None = Field(default=None, ge=0.0, le=1.0)
    decision: SolverDecision
    evidence_count: int = 0
    missing_evidence_count: int = 0
    verifier_downgraded: bool = False
    conflict_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    evidence_quality: EvidenceQualitySignals = Field(default_factory=EvidenceQualitySignals)
    node_id: str | None = None
    solver_run_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    def prompt_payload(self) -> dict[str, object]:
        """Return the semantic decision contract without control-plane metadata."""

        return self.model_dump(
            mode="json",
            exclude={"node_id", "solver_run_id", "metadata"},
        )


class _BeliefUpdateFields(BaseModel):
    belief: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class BeliefUpdateOutput(_BeliefUpdateFields):
    """Strict provider transport returned by the belief-update prompt."""

    failure_mode: BeliefFailureMode | None
    requires_judge_review: bool


class BeliefUpdateDecision(_BeliefUpdateFields):
    """Internal belief decision enriched with fallback and trace metadata."""

    failure_mode: BeliefFailureMode | None = None
    requires_judge_review: bool = False
    trace_id: str | None = None
    fallback_used: bool = False

    model_config = ConfigDict(extra="forbid")
