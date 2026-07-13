"""General schemas for grounded answer generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.llm_decision.models import LLMDecisionTrace


class EvidenceCandidate(BaseModel):
    candidate_id: str
    text: str
    source_id: str | None = None
    title: str | None = None
    position: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class EvidenceSelectionContext(BaseModel):
    query: str
    candidates: list[EvidenceCandidate] = Field(default_factory=list)
    answer_format: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


ProofCitationRole = Literal[
    "direct_answer",
    "bridge",
    "entity_link",
    "comparison_operand",
    "temporal_scope",
    "constraint_support",
    "disambiguation",
    "background_context",
]

AnswerRequirementType = Literal[
    "bridge_entity",
    "relation",
    "comparison",
    "temporal_scope",
    "answer_type",
    "direct_answer",
    "disambiguation",
    "constraint_support",
]


class ProofStepCitation(BaseModel):
    candidate_id: str
    role: ProofCitationRole
    required_for_final_support: bool = False
    claim_supported: str
    rationale: str

    model_config = ConfigDict(extra="forbid")


class ProofStep(BaseModel):
    step_id: str
    description: str
    candidate_ids: list[str] = Field(default_factory=list)
    required_candidate_ids: list[str] = Field(default_factory=list)
    citations: list[ProofStepCitation] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def required_candidates_must_be_cited(self) -> ProofStep:
        missing = [candidate_id for candidate_id in self.required_candidate_ids if candidate_id not in self.candidate_ids]
        if missing:
            raise ValueError(f"required_candidate_ids must be a subset of candidate_ids: {missing}")
        citation_ids = [citation.candidate_id for citation in self.citations]
        missing_citations = [candidate_id for candidate_id in citation_ids if candidate_id not in self.candidate_ids]
        if missing_citations:
            raise ValueError(f"citations candidate_id must be a subset of candidate_ids: {missing_citations}")
        if not self.citations and self.candidate_ids:
            required = set(self.required_candidate_ids)
            self.citations = [
                ProofStepCitation(
                    candidate_id=candidate_id,
                    role="constraint_support" if candidate_id in required else "background_context",
                    required_for_final_support=candidate_id in required,
                    claim_supported=self.description,
                    rationale="Backfilled citation role for compatibility with legacy proof-step output.",
                )
                for candidate_id in self.candidate_ids
            ]
        required_without_citation = [
            candidate_id
            for candidate_id in self.required_candidate_ids
            if not any(citation.candidate_id == candidate_id for citation in self.citations)
        ]
        if required_without_citation:
            raise ValueError(f"required_candidate_ids must have matching citations: {required_without_citation}")
        return self


class EvidenceSelectionDecision(BaseModel):
    selected_candidate_ids: list[str] = Field(default_factory=list)
    excluded_candidate_ids: list[str] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list)
    proof_steps: list[ProofStep] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")


class GroundedAnswerContext(BaseModel):
    query: str
    evidence: list[EvidenceCandidate] = Field(default_factory=list)
    answer_format: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class AnswerRequirement(BaseModel):
    requirement_id: str
    description: str
    requirement_type: AnswerRequirementType
    candidate_ids: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class CandidateRequirementCoverage(BaseModel):
    requirement_id: str
    satisfied: bool
    candidate_ids: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class CandidateAnswerConsidered(BaseModel):
    answer: str
    candidate_ids: list[str] = Field(default_factory=list)
    selected: bool = False
    answer_type: str = "short_span"
    requirement_coverage: list[CandidateRequirementCoverage] = Field(default_factory=list)
    satisfied_requirement_ids: list[str] = Field(default_factory=list)
    missing_requirement_ids: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class GroundedAnswerDecision(BaseModel):
    answer: str
    citation_candidate_ids: list[str] = Field(default_factory=list)
    answer_requirements: list[AnswerRequirement] = Field(default_factory=list)
    candidate_answers_considered: list[CandidateAnswerConsidered] = Field(default_factory=list)
    answer_type: str = "short_span"
    answer_span_candidate_id: str | None = None
    answer_span_text: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def selected_candidate_must_match_answer(self) -> GroundedAnswerDecision:
        if self.answer != "noanswer" and not self.answer_requirements and self.citation_candidate_ids:
            self.answer_requirements = [
                AnswerRequirement(
                    requirement_id="requirement:direct_answer",
                    description="The answer must be directly supported by cited evidence.",
                    requirement_type="direct_answer",
                    candidate_ids=list(self.citation_candidate_ids),
                    rationale="Backfilled requirement for compatibility with legacy grounded-answer output.",
                )
            ]
        if self.answer != "noanswer" and not self.candidate_answers_considered:
            requirement_ids = [requirement.requirement_id for requirement in self.answer_requirements]
            self.candidate_answers_considered = [
                CandidateAnswerConsidered(
                    answer=self.answer,
                    candidate_ids=list(self.citation_candidate_ids),
                    selected=True,
                    answer_type=self.answer_type,
                    requirement_coverage=[
                        CandidateRequirementCoverage(
                            requirement_id=requirement.requirement_id,
                            satisfied=True,
                            candidate_ids=list(requirement.candidate_ids or self.citation_candidate_ids),
                            rationale="Backfilled coverage for compatibility with legacy grounded-answer output.",
                        )
                        for requirement in self.answer_requirements
                    ],
                    satisfied_requirement_ids=requirement_ids,
                    missing_requirement_ids=[],
                    rationale="Backfilled selected candidate for compatibility with legacy grounded-answer output.",
                )
            ]
        selected = [candidate for candidate in self.candidate_answers_considered if candidate.selected]
        if self.answer != "noanswer" and len(selected) != 1:
            raise ValueError("candidate_answers_considered must include exactly one selected candidate for non-noanswer answers")
        if selected and selected[0].answer != self.answer:
            raise ValueError("selected candidate answer must match answer")
        requirement_ids = {requirement.requirement_id for requirement in self.answer_requirements}
        for candidate in self.candidate_answers_considered:
            unknown_satisfied = [item for item in candidate.satisfied_requirement_ids if item not in requirement_ids]
            unknown_missing = [item for item in candidate.missing_requirement_ids if item not in requirement_ids]
            unknown_coverage = [item.requirement_id for item in candidate.requirement_coverage if item.requirement_id not in requirement_ids]
            if unknown_satisfied or unknown_missing or unknown_coverage:
                raise ValueError(
                    "candidate answer requirement coverage must reference answer_requirements: "
                    f"{unknown_satisfied + unknown_missing + unknown_coverage}"
                )
        return self


class AnswerVerificationContext(BaseModel):
    query: str
    answer: str
    evidence: list[EvidenceCandidate] = Field(default_factory=list)
    citation_candidate_ids: list[str] = Field(default_factory=list)
    answer_requirements: list[AnswerRequirement] = Field(default_factory=list)
    candidate_answers_considered: list[CandidateAnswerConsidered] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class QuestionConstraintCoverage(BaseModel):
    constraint_id: str
    description: str
    satisfied: bool
    candidate_ids: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class AlternativeAnswerCheck(BaseModel):
    answer: str
    candidate_ids: list[str] = Field(default_factory=list)
    satisfies_question_constraints: bool
    better_than_proposed_answer: bool
    satisfied_requirement_ids: list[str] = Field(default_factory=list)
    missing_requirement_ids: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class AnswerVerificationDecision(BaseModel):
    entailed: bool
    corrected_answer: str | None = None
    required_candidate_ids: list[str] = Field(default_factory=list)
    missing_candidate_ids: list[str] = Field(default_factory=list)
    question_constraints: list[QuestionConstraintCoverage] = Field(default_factory=list)
    alternative_answers: list[AlternativeAnswerCheck] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")


class ProvenanceReconciliationDecision(BaseModel):
    final_citation_candidate_ids: list[str] = Field(default_factory=list)
    dropped_citation_candidate_ids: list[str] = Field(default_factory=list)
    added_citation_candidate_ids: list[str] = Field(default_factory=list)
    covered_proof_step_ids: list[str] = Field(default_factory=list)
    uncovered_proof_step_ids: list[str] = Field(default_factory=list)
    strategy: str
    rationale: str

    model_config = ConfigDict(extra="forbid")


class AnswerFinalizationDecision(BaseModel):
    raw_answer: str
    final_answer: str
    corrected_answer: str | None = None
    answer_changed: bool = False
    accepted: bool = False
    rejected_reason: str | None = None
    supporting_candidate_ids: list[str] = Field(default_factory=list)
    strategy: str
    rationale: str

    model_config = ConfigDict(extra="forbid")


class GroundedAnswerPipelineResult(BaseModel):
    answer: str
    selected_candidate_ids: list[str] = Field(default_factory=list)
    proof_citation_candidate_ids: list[str] = Field(default_factory=list)
    required_proof_citation_candidate_ids: list[str] = Field(default_factory=list)
    answer_citation_candidate_ids: list[str] = Field(default_factory=list)
    verified_citation_candidate_ids: list[str] = Field(default_factory=list)
    citation_candidate_ids: list[str] = Field(default_factory=list)
    verified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    fallback_used: bool = False
    success: bool = True
    failure_mode: str | None = None
    rationale: str
    evidence_selection: EvidenceSelectionDecision
    grounded_answer: GroundedAnswerDecision
    answer_verification: AnswerVerificationDecision
    provenance_reconciliation: ProvenanceReconciliationDecision
    answer_finalization: AnswerFinalizationDecision
    traces: list[LLMDecisionTrace] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
