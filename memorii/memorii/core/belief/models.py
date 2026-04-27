"""Belief update provider models and strict schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.solver.abstention import SolverDecision


class BeliefUpdateContext(BaseModel):
    prior_belief: float | None = None
    decision: SolverDecision
    evidence_count: int = 0
    missing_evidence_count: int = 0
    verifier_downgraded: bool = False
    conflict_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    node_id: str | None = None
    solver_run_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class BeliefUpdateDecision(BaseModel):
    belief: float
    confidence: float
    rationale: str
    trace_id: str | None = None
    fallback_used: bool = False

    model_config = ConfigDict(extra="forbid")
