"""Runtime-only prompt ownership and visibility registrations."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from memorii.core.prompts.sensitivity import ORACLE_INPUT_FIELDS, SECRET_KEYS


class PromptOwner(StrEnum):
    LLM_ANSWER_VERIFICATION_ADAPTER = "LLMAnswerVerificationAdapter"
    LLM_BELIEF_UPDATE_ADAPTER = "LLMBeliefUpdateAdapter"
    LLM_EVIDENCE_SELECTION_ADAPTER = "LLMEvidenceSelectionAdapter"
    LLM_EXECUTION_GRAPH_DECISION_ADAPTER = "LLMExecutionGraphDecisionAdapter"
    LLM_GROUNDED_ANSWER_ADAPTER = "LLMGroundedAnswerAdapter"
    LLM_HOTPOTQA_ANSWER_ADAPTER = "LLMHotpotQAAnswerAdapter"
    LLM_JUDGE_DECISION_ADAPTER = "LLMJudgeDecisionAdapter"
    LLM_LIFECYCLE_DECISION_ADAPTER = "LLMLifecycleDecisionAdapter"
    LLM_MEMORY_EVOLUTION_DECISION_ADAPTER = "LLMMemoryEvolutionDecisionAdapter"
    LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER = "LLMMemoryEvolutionSimReconstructionAdapter"
    LLM_MEMORY_EXTRACTOR = "LLMMemoryExtractor"
    LLM_PROMOTION_DECISION_ADAPTER = "LLMPromotionAssessmentAdapter"
    LLM_RETRIEVAL_RELEVANCE_DECISION_ADAPTER = "LLMRetrievalRelevanceDecisionAdapter"
    STRUCTURED_QUERY_ANALYSIS_PROVIDER = "PromptBackedStructuredQueryAnalysisProvider"


class PromptSemanticContract(StrEnum):
    NONE = "none"
    EVIDENCE_SELECTION = "memorii.core.grounding.models.EvidenceSelectionDecision"
    GROUNDED_ANSWER = "memorii.core.grounding.models.GroundedAnswerDecision"
    MEMORY_EVOLUTION_DECISION = (
        "memorii.core.benchmark.memory_evolution_decision.contracts.MemoryEvolutionSemanticDecision"
    )
    MEMORY_EVOLUTION_SIM_DECISION = (
        "memorii.core.benchmark.memory_evolution_sim.schemas.SimSemanticDecision"
    )
    STRUCTURED_QUERY_ANALYSIS = "memorii.core.memory_evolution.temporal_contracts.TemporalInterpretationProposal"


class PromptVisibilityPolicy(BaseModel):
    """Fields removed before model visibility and redacted from audit data."""

    forbidden_input_fields: list[str]
    audit_redacted_fields: list[str]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("forbidden_input_fields", "audit_redacted_fields")
    @classmethod
    def validate_canonical_fields(cls, values: list[str]) -> list[str]:
        if values != sorted(set(values)):
            raise ValueError("prompt visibility fields must be unique and sorted")
        return values


class PromptRuntimeRegistration(BaseModel):
    prompt_ref: str = Field(min_length=1)
    owning_adapter: PromptOwner
    semantic_contract: PromptSemanticContract
    visibility_policy: PromptVisibilityPolicy

    model_config = ConfigDict(extra="forbid", frozen=True)


_DEFAULT_VISIBILITY = PromptVisibilityPolicy(
    forbidden_input_fields=sorted(SECRET_KEYS | ORACLE_INPUT_FIELDS),
    audit_redacted_fields=sorted(SECRET_KEYS | ORACLE_INPUT_FIELDS),
)


def _registration(
    prompt_ref: str,
    owner: PromptOwner,
    *,
    semantic_contract: PromptSemanticContract,
    extra_forbidden: tuple[str, ...] = (),
) -> PromptRuntimeRegistration:
    visibility = _DEFAULT_VISIBILITY
    if extra_forbidden:
        visibility = PromptVisibilityPolicy(
            forbidden_input_fields=sorted(set(_DEFAULT_VISIBILITY.forbidden_input_fields) | set(extra_forbidden)),
            audit_redacted_fields=_DEFAULT_VISIBILITY.audit_redacted_fields,
        )
    return PromptRuntimeRegistration(
        prompt_ref=prompt_ref,
        owning_adapter=owner,
        semantic_contract=semantic_contract,
        visibility_policy=visibility,
    )


_JUDGE_REFS = (
    "judges/attribution:v1",
    "judges/belief_direction:v1",
    "judges/memory_plane:v1",
    "judges/promotion_precision:v1",
    "judges/temporal_validity:v1",
)


def prompt_runtime_registrations() -> dict[str, PromptRuntimeRegistration]:
    entries = [
        _registration(
            "answer_verification:v1",
            PromptOwner.LLM_ANSWER_VERIFICATION_ADAPTER,
            semantic_contract=PromptSemanticContract.NONE,
        ),
        _registration(
            "belief_update:v1", PromptOwner.LLM_BELIEF_UPDATE_ADAPTER, semantic_contract=PromptSemanticContract.NONE
        ),
        _registration(
            "evidence_selection:v1",
            PromptOwner.LLM_EVIDENCE_SELECTION_ADAPTER,
            semantic_contract=PromptSemanticContract.EVIDENCE_SELECTION,
        ),
        _registration(
            "execution_graph_decision:v1",
            PromptOwner.LLM_EXECUTION_GRAPH_DECISION_ADAPTER,
            semantic_contract=PromptSemanticContract.NONE,
        ),
        _registration(
            "grounded_answer:v1",
            PromptOwner.LLM_GROUNDED_ANSWER_ADAPTER,
            semantic_contract=PromptSemanticContract.GROUNDED_ANSWER,
        ),
        _registration(
            "hotpotqa_answer:v1", PromptOwner.LLM_HOTPOTQA_ANSWER_ADAPTER, semantic_contract=PromptSemanticContract.NONE
        ),
        *(
            _registration(ref, PromptOwner.LLM_JUDGE_DECISION_ADAPTER, semantic_contract=PromptSemanticContract.NONE)
            for ref in _JUDGE_REFS
        ),
        _registration(
            "lifecycle_decision:v1",
            PromptOwner.LLM_LIFECYCLE_DECISION_ADAPTER,
            semantic_contract=PromptSemanticContract.NONE,
        ),
        _registration(
            "memory_evolution_decision:v1",
            PromptOwner.LLM_MEMORY_EVOLUTION_DECISION_ADAPTER,
            semantic_contract=PromptSemanticContract.MEMORY_EVOLUTION_DECISION,
        ),
        _registration(
            "memory_evolution_sim_reconstruction:v1",
            PromptOwner.LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER,
            semantic_contract=PromptSemanticContract.MEMORY_EVOLUTION_SIM_DECISION,
            extra_forbidden=("excludedids",),
        ),
        _registration(
            "memory_extraction:v1", PromptOwner.LLM_MEMORY_EXTRACTOR, semantic_contract=PromptSemanticContract.NONE
        ),
        _registration(
            "promotion_decision:v1",
            PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
            semantic_contract=PromptSemanticContract.NONE,
        ),
        _registration(
            "retrieval_relevance:v1",
            PromptOwner.LLM_RETRIEVAL_RELEVANCE_DECISION_ADAPTER,
            semantic_contract=PromptSemanticContract.NONE,
        ),
        _registration(
            "structured_query_analysis:v1",
            PromptOwner.STRUCTURED_QUERY_ANALYSIS_PROVIDER,
            semantic_contract=PromptSemanticContract.STRUCTURED_QUERY_ANALYSIS,
        ),
    ]
    return {entry.prompt_ref: entry for entry in entries}
