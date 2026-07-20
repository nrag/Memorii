"""Typed checkpoint, judge, alignment, and diagnostic artifact rows."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.benchmark.artifact_rows.common import (
    ActionSupportMode,
    AlignmentItemType,
    AlignmentVerdict,
    CheckpointVerdict,
    DecisionMode,
    FinalOutputSource,
    FlatArtifactModel,
    ProviderCountScope,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    JudgeAggregate,
    JudgeVote,
    MemoryEvolutionSimReconstructionContext,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.calibration.alignment import RuntimeGraphAlignment
from memorii.core.memory_evolution.execution import (
    ContinuationDecision,
    WorkState,
    WorkStateSnapshot,
)
from memorii.core.memory_evolution.retrieval import ProductionRetrievalDecision


class ChannelOverlapSection(BaseModel):
    """Role-channel overlap diagnostics for selected/support/rejected/context views."""

    critical: list[str] = Field(default_factory=list)
    warning: list[str] = Field(default_factory=list)
    critical_ids: dict[str, list[str]] = Field(default_factory=dict)
    warning_ids: dict[str, list[str]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class SelectedClaimSupportClosureErrorSection(BaseModel):
    """Claim-local selected/supporting/citation closure diagnostics."""

    claim_id: str
    missing_supporting_claim: bool
    expected_event_ids: list[str] = Field(default_factory=list)
    present_event_ids: list[str] = Field(default_factory=list)
    missing_event_ids: list[str] = Field(default_factory=list)
    is_action_state: bool

    model_config = ConfigDict(extra="forbid")


class CheckpointResultRow(FlatArtifactModel):
    """Common checkpoint result contract for benchmark artifacts."""

    scenario_id: str
    checkpoint_id: str
    checkpoint_type: str
    success: bool
    passed: bool
    verdict: CheckpointVerdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    review_required: bool
    failure_buckets: list[str] = Field(default_factory=list)
    warning_buckets: list[str] = Field(default_factory=list)
    diagnostics: CheckpointDiagnosticsPayload = Field(default_factory=lambda: CheckpointDiagnosticsPayload())
    output: SimSystemOutput
    phase: str = "checkpoint"
    horizon_distance: int = Field(default=0, ge=0)
    horizon_distance_bucket: str = "short"
    interference_count: int = Field(default=0, ge=0)
    interference_count_bucket: str = "none"
    source_event_age_days: float = Field(default=0.0, ge=0.0)
    source_event_age_days_bucket: str = "fresh"
    required_retrieval_view: str = "current"
    expected_stage_path: list[str] = Field(default_factory=list)
    query_or_task: str = ""
    llm_call_made: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None
    request_id: str = ""
    expected: OracleCheckpoint
    candidate_cards: MemoryEvolutionSimReconstructionContext
    raw_output: SimSystemOutput
    judge_aggregate: JudgeAggregate
    # These high-value judge diagnostics remain top-level because artifact
    # consumers use them for filtering without joining or unpacking payloads.
    # The complete typed diagnostic section is also retained under diagnostics.
    selected_excluded_ids: dict[str, list[str]] = Field(default_factory=dict)
    supporting_excluded_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    extra_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_definition_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_context_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    answer_match_type: str = "unknown"
    failure_classification: list[str] = Field(default_factory=list)
    rejected_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_rejected_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_rejected_claim_subject_entity_ids: list[str] = Field(default_factory=list)
    supporting_wrong_entity_claim_ids: list[str] = Field(default_factory=list)
    selected_noncurrent_claim_ids: list[str] = Field(default_factory=list)
    supporting_noisy_citation_event_ids: list[str] = Field(default_factory=list)
    supporting_wrong_subject_claim_ids: list[str] = Field(default_factory=list)
    supporting_wrong_subject_entity_ids: list[str] = Field(default_factory=list)
    supporting_disambiguation_claim_ids: list[str] = Field(default_factory=list)
    missing_wrong_entity_rejection_claim_ids: list[str] = Field(default_factory=list)
    missing_wrong_entity_rejection_subject_ids: list[str] = Field(default_factory=list)
    context_only_noise_event_ids: list[str] = Field(default_factory=list)
    required_definition_claim_ids: list[str] = Field(default_factory=list)
    missing_definition_claim_ids: list[str] = Field(default_factory=list)
    missing_definition_support_claim_ids: list[str] = Field(default_factory=list)
    rejected_required_definition_claim_ids: list[str] = Field(default_factory=list)
    selected_entity_role_mismatches: list[str] = Field(default_factory=list)
    missing_selected_subject_entity_ids: list[str] = Field(default_factory=list)
    selected_object_entity_instead_of_subject_ids: list[str] = Field(default_factory=list)
    selected_graph_entity_overbreadth: list[str] = Field(default_factory=list)
    selected_nonrequired_graph_entity_ids: list[str] = Field(default_factory=list)
    selected_context_only_entity_ids: list[str] = Field(default_factory=list)
    selected_rejected_or_context_entity_ids: list[str] = Field(default_factory=list)
    selected_claim_support_closure_errors: list[SelectedClaimSupportClosureErrorSection] = Field(default_factory=list)
    selected_claim_ids_missing_support: list[str] = Field(default_factory=list)
    selected_claim_evidence_event_ids_missing_support: list[str] = Field(default_factory=list)
    selected_action_state_event_ids_missing_support: list[str] = Field(default_factory=list)
    supporting_role_violations: dict[str, list[str]] = Field(default_factory=dict)
    supporting_rejection_provenance_overlap: dict[str, list[str]] = Field(default_factory=dict)
    channel_overlap: ChannelOverlapSection = Field(default_factory=ChannelOverlapSection)
    required_judge_ids: list[str] = Field(default_factory=list)
    role_misclassification: bool = False
    precision_failure_classification: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_verdict_projection(self) -> CheckpointResultRow:
        expected_passed = self.verdict == "pass"
        if self.passed != expected_passed:
            raise ValueError("checkpoint passed must be true exactly when verdict is pass")
        return self


class CheckpointHorizonSection(BaseModel):
    """Typed checkpoint metadata flattened into checkpoint result artifacts."""

    family: str
    profile: str
    phase: str = "checkpoint"
    horizon_distance: int = Field(ge=0)
    horizon_distance_bucket: str
    interference_count: int = Field(ge=0)
    interference_count_bucket: str
    source_event_age_days: float = Field(ge=0.0)
    source_event_age_days_bucket: str
    required_retrieval_view: str
    expected_stage_path: list[str] = Field(default_factory=list)
    query_or_task: str

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class CheckpointDecisionTraceSection(BaseModel):
    """Typed decision/runtime trace metadata flattened into checkpoint rows."""

    decision_mode: DecisionMode
    effective_decision_mode: DecisionMode
    llm_call_made: bool
    fallback_used: bool
    fallback_reason: str | None = None
    final_output_source: FinalOutputSource
    request_id: str

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class CheckpointVerdictSection(BaseModel):
    """Typed verdict fields shared by simulator and runtime checkpoint rows."""

    success: bool
    passed: bool
    verdict: CheckpointVerdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    review_required: bool
    failure_buckets: list[str] = Field(default_factory=list)
    warning_buckets: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class CheckpointDiagnosticsSection(BaseModel):
    """Typed diagnostics emitted by sim/runtime judge diagnostics."""

    missing_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    extra_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_definition_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    allowed_context_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_selected_ids: dict[str, list[str]] = Field(default_factory=dict)
    answer_match_type: str = "unknown"
    failure_classification: list[str] = Field(default_factory=list)
    selected_excluded_ids: dict[str, list[str]] = Field(default_factory=dict)
    supporting_excluded_ids: dict[str, list[str]] = Field(default_factory=dict)
    rejected_expected_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_rejected_ids: dict[str, list[str]] = Field(default_factory=dict)
    missing_rejected_claim_subject_entity_ids: list[str] = Field(default_factory=list)
    supporting_wrong_entity_claim_ids: list[str] = Field(default_factory=list)
    supporting_wrong_subject_claim_ids: list[str] = Field(default_factory=list)
    supporting_wrong_subject_entity_ids: list[str] = Field(default_factory=list)
    supporting_disambiguation_claim_ids: list[str] = Field(default_factory=list)
    missing_wrong_entity_rejection_claim_ids: list[str] = Field(default_factory=list)
    missing_wrong_entity_rejection_subject_ids: list[str] = Field(default_factory=list)
    selected_noncurrent_claim_ids: list[str] = Field(default_factory=list)
    required_definition_claim_ids: list[str] = Field(default_factory=list)
    missing_definition_claim_ids: list[str] = Field(default_factory=list)
    missing_definition_support_claim_ids: list[str] = Field(default_factory=list)
    rejected_required_definition_claim_ids: list[str] = Field(default_factory=list)
    selected_entity_role_mismatches: list[str] = Field(default_factory=list)
    missing_selected_subject_entity_ids: list[str] = Field(default_factory=list)
    selected_object_entity_instead_of_subject_ids: list[str] = Field(default_factory=list)
    selected_graph_entity_overbreadth: list[str] = Field(default_factory=list)
    selected_nonrequired_graph_entity_ids: list[str] = Field(default_factory=list)
    selected_context_only_entity_ids: list[str] = Field(default_factory=list)
    selected_rejected_or_context_entity_ids: list[str] = Field(default_factory=list)
    supporting_noisy_citation_event_ids: list[str] = Field(default_factory=list)
    selected_claim_support_closure_errors: list[SelectedClaimSupportClosureErrorSection] = Field(default_factory=list)
    selected_claim_ids_missing_support: list[str] = Field(default_factory=list)
    selected_claim_evidence_event_ids_missing_support: list[str] = Field(default_factory=list)
    selected_action_state_event_ids_missing_support: list[str] = Field(default_factory=list)
    context_only_noise_event_ids: list[str] = Field(default_factory=list)
    supporting_role_violations: dict[str, list[str]] = Field(default_factory=dict)
    supporting_rejection_provenance_overlap: dict[str, list[str]] = Field(default_factory=dict)
    channel_overlap: ChannelOverlapSection = Field(default_factory=ChannelOverlapSection)
    role_misclassification: bool = False
    precision_failure_classification: list[str] = Field(default_factory=list)
    required_judge_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class SimCheckpointResultRow(CheckpointResultRow):
    """Checkpoint row emitted by ``memory_evolution_sim_v1``."""

    profile: str
    family: str
    decision_mode: DecisionMode
    effective_decision_mode: DecisionMode
    final_output_source: FinalOutputSource


class RuntimeCheckpointResultRow(SimCheckpointResultRow):
    """Checkpoint row emitted by ``memory_evolution_runtime_v1``."""

    runtime_failure_buckets: list[str] = Field(default_factory=list)
    runtime_failure_classification: list[str] = Field(default_factory=list)
    scenario_provider_successes: int = Field(default=0, ge=0)
    scenario_provider_failures: int = Field(default=0, ge=0)
    scenario_fallbacks: int = Field(default=0, ge=0)
    provider_successes: int = Field(default=0, ge=0)
    provider_failures: int = Field(default=0, ge=0)
    fallbacks: int = Field(default=0, ge=0)
    provider_count_scope: ProviderCountScope = "scenario_extractor_calls"


class JudgeVoteRow(FlatArtifactModel):
    """Stable row contract for flattened judge votes."""

    judge_id: str
    checkpoint_id: str
    verdict: CheckpointVerdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    covered_ids: list[str] = Field(default_factory=list)
    failed_ids: list[str] = Field(default_factory=list)
    abstained_ids: list[str] = Field(default_factory=list)
    failure_buckets: list[str] = Field(default_factory=list)
    rationale: str

    @classmethod
    def from_vote(cls, vote: JudgeVote) -> JudgeVoteRow:
        return cls(
            judge_id=vote.judge_id,
            checkpoint_id=vote.checkpoint_id,
            verdict=cast(CheckpointVerdict, vote.verdict.value),
            score=vote.score,
            confidence=vote.confidence,
            covered_ids=list(vote.covered_ids),
            failed_ids=list(vote.failed_ids),
            abstained_ids=list(vote.abstained_ids),
            failure_buckets=list(vote.failure_buckets),
            rationale=vote.rationale,
        )


class RuntimeGraphAlignmentRow(FlatArtifactModel):
    """Stable alignment row contract for runtime graph-to-oracle artifacts."""

    scenario_id: str
    checkpoint_id: str
    oracle_id: str
    runtime_id: str
    item_type: AlignmentItemType
    verdict: AlignmentVerdict
    score: float = Field(ge=0.0, le=1.0)
    matched_on: list[str] = Field(default_factory=list)
    failure_reason: str

    @classmethod
    def from_alignment(
        cls,
        alignment: RuntimeGraphAlignment,
        *,
        scenario_id: str,
        checkpoint_id: str,
    ) -> RuntimeGraphAlignmentRow:
        return cls(
            scenario_id=scenario_id,
            checkpoint_id=checkpoint_id,
            oracle_id=alignment.oracle_item_id or "",
            runtime_id=alignment.runtime_item_id or "",
            item_type=cast(AlignmentItemType, alignment.item_type),
            verdict=alignment.verdict.value,
            score=alignment.score,
            matched_on=list(alignment.matched_on),
            failure_reason="" if alignment.verdict.value == "aligned" else alignment.rationale,
        )

    @model_validator(mode="after")
    def validate_identity_by_verdict(self) -> RuntimeGraphAlignmentRow:
        verdict = self.verdict
        has_oracle = bool(self.oracle_id)
        has_runtime = bool(self.runtime_id)
        if verdict in {"aligned", "partial"} and not (has_oracle and has_runtime):
            raise ValueError(f"{verdict} graph alignment rows require oracle_id and runtime_id")
        if verdict == "missing_expected" and not has_oracle:
            raise ValueError("missing_expected graph alignment rows require oracle_id")
        if verdict == "unmatched_runtime" and not has_runtime:
            raise ValueError("unmatched_runtime graph alignment rows require runtime_id")
        if verdict == "ambiguous_alignment" and not (has_oracle or has_runtime):
            raise ValueError("ambiguous graph alignment rows require oracle_id or runtime_id")
        if verdict != "aligned" and not self.failure_reason:
            raise ValueError(f"{verdict} graph alignment rows require failure_reason")
        return self


class RuntimeActionAlignmentRow(FlatArtifactModel):
    """Stable row contract for runtime action-to-oracle alignment diagnostics."""

    expected_action_id: str
    runtime_action_id: str
    runtime_item_id: str
    verdict: AlignmentVerdict
    support_mode: ActionSupportMode
    matched_on: list[str] = Field(default_factory=list)
    failed_on: list[str] = Field(default_factory=list)
    failure_reason: str
    evidence_event_ids: list[str] = Field(default_factory=list)
    status: str = ""
    target_entity_ids: list[str] = Field(default_factory=list)
    continuation_rank: int = 0
    model_status_raw: str = ""
    action_type_raw: str = ""
    status_derived_from: str = ""
    bridged_target_entity_id: str | None = None

    @model_validator(mode="after")
    def validate_identity_by_verdict(self) -> RuntimeActionAlignmentRow:
        has_runtime = bool(self.runtime_action_id or self.runtime_item_id)
        if self.verdict == "aligned" and not has_runtime:
            raise ValueError("aligned action rows require runtime_action_id or runtime_item_id")
        if self.verdict == "partial" and not has_runtime:
            raise ValueError("partial action rows require runtime_action_id or runtime_item_id")
        if self.verdict == "missing_expected" and not self.failure_reason:
            raise ValueError("missing_expected action rows require failure_reason")
        if self.verdict == "ambiguous_alignment" and not has_runtime:
            raise ValueError("ambiguous action rows require runtime_action_id or runtime_item_id")
        if self.verdict != "aligned" and not self.failure_reason:
            raise ValueError(f"{self.verdict} action rows require failure_reason")
        return self


class RuntimeRelationSupportRow(BaseModel):
    """Typed relation-support diagnostics for runtime checkpoint artifacts."""

    relation_id: str
    support_mode: str

    model_config = ConfigDict(extra="forbid")


class RuntimeActionSupportRow(BaseModel):
    """Typed action-support diagnostics for runtime checkpoint artifacts."""

    action_id: str
    support_mode: str

    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionStateSection(FlatArtifactModel):
    """Typed production execution projection retained for auditability."""

    status: str | None = None
    reason: str | None = None
    active_continuation_branch: str | None = None
    active_runtime_continuation_branch: str | None = None
    active_evidence_event_ids: list[str] = Field(default_factory=list)
    suppressed_branch_ids: list[str] = Field(default_factory=list)
    ambiguous_action_count: int = Field(default=0, ge=0)
    aligned_action_count: int = Field(default=0, ge=0)
    decision_status: str | None = None
    decision_abstained: bool | None = None
    active_branch_ids: list[str] = Field(default_factory=list)
    states: list[WorkState] = Field(default_factory=list)
    ambiguous_branch_ids: list[str] = Field(default_factory=list)
    continuation_decision: ContinuationDecision | None = None
    production_work_state: WorkStateSnapshot | None = None

    model_config = ConfigDict(extra="forbid")


class RuntimeDiagnosticsSection(BaseModel):
    """Typed runtime diagnostics flattened into checkpoint rows."""

    runtime_graph_validation_errors: list[str] = Field(default_factory=list)
    runtime_relation_support: list[RuntimeRelationSupportRow] = Field(default_factory=list)
    runtime_action_support: list[RuntimeActionSupportRow] = Field(default_factory=list)
    runtime_action_alignments: list[RuntimeActionAlignmentRow] = Field(default_factory=list)
    runtime_execution_state: RuntimeExecutionStateSection
    runtime_retrieval_decision: ProductionRetrievalDecision | None = None
    active_continuation_branch: str | None = None
    suppressed_branch_ids: list[str] = Field(default_factory=list)
    action_alignment_failure_reason: str

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class CheckpointDiagnosticsPayload(CheckpointDiagnosticsSection):
    """Complete typed payload persisted under a checkpoint's diagnostics key."""

    runtime_graph_validation_errors: list[str] = Field(default_factory=list)
    runtime_relation_support: list[RuntimeRelationSupportRow] = Field(default_factory=list)
    runtime_action_support: list[RuntimeActionSupportRow] = Field(default_factory=list)
    runtime_action_alignments: list[RuntimeActionAlignmentRow] = Field(default_factory=list)
    runtime_execution_state: RuntimeExecutionStateSection | None = None
    runtime_retrieval_decision: ProductionRetrievalDecision | None = None
    active_continuation_branch: str | None = None
    suppressed_branch_ids: list[str] = Field(default_factory=list)
    action_alignment_failure_reason: str = ""

    @classmethod
    def from_sections(
        cls,
        checkpoint: CheckpointDiagnosticsSection,
        runtime: RuntimeDiagnosticsSection,
    ) -> CheckpointDiagnosticsPayload:
        return cls.model_validate(
            {
                **checkpoint.model_dump(mode="python"),
                **runtime.model_dump(mode="python"),
            }
        )


RuntimeDiagnosticsSection.model_rebuild()
CheckpointDiagnosticsSection.model_rebuild()
CheckpointDiagnosticsPayload.model_rebuild()
CheckpointResultRow.model_rebuild()
SimCheckpointResultRow.model_rebuild()
RuntimeCheckpointResultRow.model_rebuild()




def checkpoint_warning_buckets(
    *,
    answer_match_type: object,
    output: SimSystemOutput,
) -> list[str]:
    """Return warning-only artifact buckets shared by sim/runtime rows."""

    buckets: list[str] = []
    if answer_match_type == "optional_missing":
        buckets.append("graph_answer_optional_missing")
    if (
        output.context_claim_ids
        or output.context_entity_ids
        or output.context_relation_ids
        or output.context_citation_event_ids
    ):
        buckets.append("extra_context_provenance")
    return buckets
