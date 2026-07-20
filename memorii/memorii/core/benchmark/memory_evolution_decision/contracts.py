"""Typed contracts for the hand-authored memory-evolution benchmark."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEGRADED_BELIEF_SCORE_MAX = 0.35


class MemoryEvolutionSourceType(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    VERIFIED_OBSERVATION = "verified_observation"
    TRANSCRIPT = "transcript"


class MemoryEvolutionEventRole(StrEnum):
    OBSERVATION = "observation"
    COMMAND_CONTEXT = "command_context"
    ACTION_STATE = "action_state"
    BLOCKED_STATE = "blocked_state"
    ARCHIVED_STATE = "archived_state"


class MemoryEvolutionEvent(BaseModel):
    event_id: str
    timestamp: datetime
    source_type: MemoryEvolutionSourceType
    content: str
    entity_ids: list[str] = Field(default_factory=list)
    task_id: str | None = None
    scope: str | None = None
    trust_level: int = Field(default=1, ge=0, le=5)
    event_role: MemoryEvolutionEventRole = MemoryEvolutionEventRole.OBSERVATION
    language: str = "en"
    script: str | None = None
    subject_entity_id: str | None = None
    predicate: str | None = None
    object_value: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    temporal_anchor_ids: list[str] = Field(default_factory=list)
    temporal_anchor_aliases: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

class MemoryEvolutionBeliefState(StrEnum):
    UNKNOWN = "unknown"
    CONFIDENT = "confident"
    DEGRADED = "degraded"
    FALSIFIED = "falsified"
    SUPERSEDED = "superseded"


class MemoryEvolutionBeliefScore(BaseModel):
    memory_id: str
    belief: float = Field(ge=0.0, le=1.0)
    # Belief content state is independent from the lifecycle of the memory
    # record that stores it. It is optional for non-belief checkpoints, but
    # required by the belief-state contract when expectations are authored.
    belief_state: MemoryEvolutionBeliefState | None = None

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionAnswerTemporalMode(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    EXECUTION = "execution"
    BELIEF = "belief"


class MemoryEvolutionTemporalKind(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    INTERVAL = "interval"
    EXECUTION = "execution"
    BELIEF = "belief"
    AMBIGUOUS = "ambiguous"


class MemoryEvolutionScopeKind(StrEnum):
    NONE = "none"
    GLOBAL = "global"
    TASK = "task"
    ENTITY = "entity"
    CUSTOM = "custom"


class MemoryEvolutionRecordLifecycleState(StrEnum):
    CHECKPOINT_ACTIVE = "checkpoint_active"
    CHECKPOINT_SUPERSEDED = "checkpoint_superseded"
    CHECKPOINT_RETAINED = "checkpoint_retained"


class MemoryEvolutionSelectedMemoryPolicy(StrEnum):
    ANSWER_SUPPORT = "answer_support"
    CURRENT_TRUTH = "current_truth"
    HISTORICAL_TRUTH = "historical_truth"
    ACTIVE_EXECUTION_STATE = "active_execution_state"
    BELIEF_ORDER = "belief_order"


class MemoryEvolutionAnswerProjectionPolicy(StrEnum):
    CLAIM_OBJECT = "claim_object"
    CLAIM_SUBJECT = "claim_subject"
    NONE = "none"
    NEXT_ACTION = "next_action"
    GRAPH_CHANNELS_ONLY = "graph_channels_only"


class MemoryEvolutionAnswerLanguagePolicy(StrEnum):
    MATCH_QUERY = "match_query"
    MATCH_EVIDENCE = "match_evidence"
    ENGLISH_OK = "english_ok"
    STRUCTURED_ONLY = "structured_only"


class MemoryEvolutionTransliterationPolicy(StrEnum):
    ALLOWED = "allowed"
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


class MemoryEvolutionDecisionOperation(StrEnum):
    ANSWER = "answer"
    NEXT_ACTION = "next_action"
    ABSTAIN = "abstain"


class MemoryEvolutionAnswerSelection(BaseModel):
    selected_memory_ids: list[str] = Field(default_factory=list)
    supporting_memory_ids: list[str] = Field(default_factory=list)
    citation_memory_ids: list[str] = Field(default_factory=list)
    temporal_mode: MemoryEvolutionAnswerTemporalMode
    rationale: str = ""

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionTemporalFrame(BaseModel):
    temporal_kind: MemoryEvolutionTemporalKind
    scope_kind: MemoryEvolutionScopeKind = MemoryEvolutionScopeKind.NONE
    scope_key: str | None = None
    anchor_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str = ""

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionLifecycleSnapshot(BaseModel):
    checkpoint_active_record_ids: list[str] = Field(default_factory=list)
    checkpoint_superseded_record_ids: list[str] = Field(default_factory=list)
    checkpoint_retained_record_ids: list[str] = Field(default_factory=list)
    evaluation_time: datetime
    rationale: str = ""

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionRetrievalContext(BaseModel):
    query_relevant_memory_ids: list[str] = Field(default_factory=list)
    query_historical_memory_ids: list[str] = Field(default_factory=list)
    query_context_memory_ids: list[str] = Field(default_factory=list)
    rejected_memory_ids: list[str] = Field(default_factory=list)
    rationale: str = ""

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionExecutionSelection(BaseModel):
    selected_action_memory_ids: list[str] = Field(default_factory=list)
    active_work_state_memory_ids: list[str] = Field(default_factory=list)
    command_context_memory_ids: list[str] = Field(default_factory=list)
    suppressed_branch_memory_ids: list[str] = Field(default_factory=list)
    rationale: str = ""

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionCheckpointKind(StrEnum):
    CURRENT_TRUTH = "current_truth"
    HISTORICAL_TRUTH = "historical_truth"
    BELIEF_RANKING = "belief_ranking"
    BELIEF_DEGRADATION = "belief_degradation"
    EXECUTION_CONTINUATION = "execution_continuation"


class MemoryEvolutionCitationPolicy(StrEnum):
    DIRECT_ONLY = "direct_only"
    DIRECT_WITH_CONTEXT_WARNING = "direct_with_context_warning"


class MemoryEvolutionLifecyclePolicy(StrEnum):
    EXACT = "exact"
    NON_CHECKPOINT_ACTIVE_EQUIVALENT = "non_checkpoint_active_equivalent"
    WARNING = "warning"


class MemoryEvolutionScopeMatchPolicy(StrEnum):
    EXACT = "exact"
    KIND_ONLY = "kind_only"
    NONE_OR_GLOBAL = "none_or_global"
    NONE_OR_ENTITY = "none_or_entity"
    NONE_OR_TASK = "none_or_task"
    NONE_GLOBAL_OR_ENTITY = "none_global_or_entity"


class MemoryEvolutionTemporalIntervalPolicy(StrEnum):
    NONE = "none"
    EXACT = "exact"
    REQUIRE_START_AND_END = "require_start_and_end"
    ALLOW_CHECKPOINT_BOUNDS = "allow_checkpoint_bounds"
    ALLOW_EXTRA_BOUNDS = "allow_extra_bounds"


class MemoryEvolutionScopeKeyPolicy(StrEnum):
    EXACT = "exact"
    CANONICAL_ALIAS = "canonical_alias"
    KIND_ONLY = "kind_only"
    NONE_ALLOWED = "none_allowed"


class MemoryEvolutionBeliefLifecyclePolicy(StrEnum):
    NONE = "none"
    DEGRADED_RETAINED_EVALUABLE = "degraded_retained_evaluable"
    RANKING_CANDIDATES_ALLOWED = "ranking_candidates_allowed"


class MemoryEvolutionBeliefScorePolicy(StrEnum):
    NONE = "none"
    RANKING_ONLY = "ranking_only"
    DEGRADED_THRESHOLD = "degraded_threshold"
    EXACT = "exact"


class MemoryEvolutionExcludedMemoryPolicy(StrEnum):
    NONE = "none"
    REJECTED_OR_CONTEXT = "rejected_or_context"


class MemoryEvolutionNextActionPolicy(StrEnum):
    NONE = "none"
    NONEMPTY_STRUCTURED = "nonempty_structured"


class MemoryEvolutionCheckpointContract(BaseModel):
    checkpoint_kind: MemoryEvolutionCheckpointKind
    answer_temporal_mode: MemoryEvolutionAnswerTemporalMode
    selected_memory_policy: MemoryEvolutionSelectedMemoryPolicy
    answer_projection_policy: MemoryEvolutionAnswerProjectionPolicy = MemoryEvolutionAnswerProjectionPolicy.CLAIM_OBJECT
    citation_policy: MemoryEvolutionCitationPolicy = MemoryEvolutionCitationPolicy.DIRECT_ONLY
    lifecycle_policy: MemoryEvolutionLifecyclePolicy = MemoryEvolutionLifecyclePolicy.EXACT
    scope_match_policy: MemoryEvolutionScopeMatchPolicy = MemoryEvolutionScopeMatchPolicy.EXACT
    temporal_interval_policy: MemoryEvolutionTemporalIntervalPolicy = MemoryEvolutionTemporalIntervalPolicy.EXACT
    scope_key_policy: MemoryEvolutionScopeKeyPolicy = MemoryEvolutionScopeKeyPolicy.EXACT
    allow_extra_temporal_anchor: bool = False
    allow_extra_temporal_bounds: bool = False
    belief_lifecycle_policy: MemoryEvolutionBeliefLifecyclePolicy = MemoryEvolutionBeliefLifecyclePolicy.NONE
    belief_score_policy: MemoryEvolutionBeliefScorePolicy = MemoryEvolutionBeliefScorePolicy.NONE
    next_action_policy: MemoryEvolutionNextActionPolicy = MemoryEvolutionNextActionPolicy.NONE
    requires_execution_selection: bool = False
    allow_historical_selected_memory: bool = False
    excluded_memory_policy: MemoryEvolutionExcludedMemoryPolicy = MemoryEvolutionExcludedMemoryPolicy.NONE

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionBeliefStateExpectation(BaseModel):
    memory_id: str
    expected_state: MemoryEvolutionBeliefState
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_score: float | None = Field(default=None, ge=0.0, le=1.0)
    score_required: bool = False

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionCheckpoint(BaseModel):
    checkpoint_id: str
    timestamp: datetime
    query_or_task: str
    contract: MemoryEvolutionCheckpointContract
    expected_answer: str | None = None
    expected_next_action: str | None = None
    expected_retrieval_ids: list[str] = Field(default_factory=list)
    expected_citation_ids: list[str] = Field(default_factory=list)
    expected_context_citation_ids: list[str] = Field(default_factory=list)
    expected_excluded_memory_ids: list[str] = Field(default_factory=list)
    expected_checkpoint_active_record_ids: list[str] = Field(default_factory=list)
    expected_checkpoint_superseded_record_ids: list[str] = Field(default_factory=list)
    expected_checkpoint_retained_record_ids: list[str] = Field(default_factory=list)
    expected_full_checkpoint_active_record_ids: list[str] = Field(default_factory=list)
    expected_full_checkpoint_superseded_record_ids: list[str] = Field(default_factory=list)
    expected_full_checkpoint_retained_record_ids: list[str] = Field(default_factory=list)
    expected_belief_ranking: list[str] = Field(default_factory=list)
    expected_belief_scores: dict[str, float] = Field(default_factory=dict)
    expected_belief_states: list[MemoryEvolutionBeliefStateExpectation] = Field(default_factory=list)
    expected_answer_aliases: list[str] = Field(default_factory=list)
    expected_temporal_frame: MemoryEvolutionTemporalFrame | None = None
    query_language: str = "en"
    evidence_languages: list[str] = Field(default_factory=lambda: ["en"])
    answer_language_policy: MemoryEvolutionAnswerLanguagePolicy = MemoryEvolutionAnswerLanguagePolicy.MATCH_QUERY
    cross_lingual: bool = False
    transliteration_policy: MemoryEvolutionTransliterationPolicy = MemoryEvolutionTransliterationPolicy.ALLOWED

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionVisibleCheckpoint(BaseModel):
    checkpoint_id: str
    timestamp: datetime
    query_or_task: str
    query_language: str = "en"
    evidence_languages: list[str] = Field(default_factory=lambda: ["en"])
    answer_language_policy: MemoryEvolutionAnswerLanguagePolicy = MemoryEvolutionAnswerLanguagePolicy.MATCH_QUERY
    cross_lingual: bool = False
    transliteration_policy: MemoryEvolutionTransliterationPolicy = MemoryEvolutionTransliterationPolicy.ALLOWED

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionMemoryKind(StrEnum):
    FACT = "fact"
    BELIEF = "belief"
    EVIDENCE = "evidence"
    ACTION = "action"
    UNKNOWN = "unknown"


class MemoryEvolutionEvidenceEffectBasis(StrEnum):
    SURFACE_TEXT_PATTERN = "surface_text_pattern"


class MemoryEvolutionVisibleMemoryCard(BaseModel):
    memory_id: str
    memory_kind: MemoryEvolutionMemoryKind
    statement: str
    timestamp: datetime
    source_type: MemoryEvolutionSourceType
    trust_level: int = Field(ge=0, le=5)
    entity_ids: list[str] = Field(default_factory=list)
    task_id: str | None = None
    scope: str | None = None
    event_role: MemoryEvolutionEventRole = MemoryEvolutionEventRole.OBSERVATION
    language: str = "en"
    script: str | None = None

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionEntityResolutionCard(BaseModel):
    entity_id: str
    entity_type: str = "unknown"
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    evidence_memory_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionTemporalAnchorCard(BaseModel):
    anchor_id: str
    aliases: list[str] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_memory_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionEntityStateClaimCard(BaseModel):
    memory_id: str
    entity_id: str
    predicate: str
    value: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    observed_at: datetime
    temporal_anchor_ids: list[str] = Field(default_factory=list)
    record_lifecycle: MemoryEvolutionRecordLifecycleState
    source_memory_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionEvidenceEffectCard(BaseModel):
    evidence_memory_id: str
    supports_memory_ids: list[str] = Field(default_factory=list)
    weakens_memory_ids: list[str] = Field(default_factory=list)
    falsifies_memory_ids: list[str] = Field(default_factory=list)
    dependency_memory_ids: list[str] = Field(default_factory=list)
    extraction_basis: MemoryEvolutionEvidenceEffectBasis = MemoryEvolutionEvidenceEffectBasis.SURFACE_TEXT_PATTERN

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionScenario(BaseModel):
    scenario_id: str
    family: str
    events: list[MemoryEvolutionEvent]
    checkpoints: list[MemoryEvolutionCheckpoint]
    discriminative: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_references(self) -> MemoryEvolutionScenario:
        event_ids = {event.event_id for event in self.events}
        if len(self.events) < 2:
            raise ValueError("memory evolution scenarios require at least two events")
        if not self.checkpoints:
            raise ValueError("memory evolution scenarios require at least one checkpoint")
        for checkpoint in self.checkpoints:
            referenced = [
                *checkpoint.expected_retrieval_ids,
                *checkpoint.expected_citation_ids,
                *checkpoint.expected_context_citation_ids,
                *checkpoint.expected_excluded_memory_ids,
                *checkpoint.expected_checkpoint_active_record_ids,
                *checkpoint.expected_checkpoint_superseded_record_ids,
                *checkpoint.expected_checkpoint_retained_record_ids,
                *checkpoint.expected_full_checkpoint_active_record_ids,
                *checkpoint.expected_full_checkpoint_superseded_record_ids,
                *checkpoint.expected_full_checkpoint_retained_record_ids,
                *checkpoint.expected_belief_ranking,
                *checkpoint.expected_belief_scores.keys(),
                *(expectation.memory_id for expectation in checkpoint.expected_belief_states),
            ]
            missing = sorted({item for item in referenced if item not in event_ids})
            if missing:
                raise ValueError(
                    f"checkpoint {checkpoint.checkpoint_id} references unknown event ids: {missing}"
                )
        return self


class MemoryEvolutionDecisionContext(BaseModel):
    scenario_id: str
    family: str
    events: list[MemoryEvolutionEvent]
    checkpoint: MemoryEvolutionVisibleCheckpoint
    visible_memory_cards: list[MemoryEvolutionVisibleMemoryCard] = Field(default_factory=list)
    entity_resolution_cards: list[MemoryEvolutionEntityResolutionCard] = Field(default_factory=list)
    temporal_anchor_cards: list[MemoryEvolutionTemporalAnchorCard] = Field(default_factory=list)
    entity_state_cards: list[MemoryEvolutionEntityStateClaimCard] = Field(default_factory=list)
    evidence_effect_cards: list[MemoryEvolutionEvidenceEffectCard] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionDecision(BaseModel):
    operation: MemoryEvolutionDecisionOperation
    answer: str | None = None
    next_action: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    query_temporal_frame: MemoryEvolutionTemporalFrame
    answer_selection: MemoryEvolutionAnswerSelection
    lifecycle_snapshot: MemoryEvolutionLifecycleSnapshot
    retrieval_context: MemoryEvolutionRetrievalContext
    execution_selection: MemoryEvolutionExecutionSelection | None = None
    evaluated_belief_ids: list[str] = Field(default_factory=list)
    belief_scores: list[MemoryEvolutionBeliefScore] = Field(default_factory=list)
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_operation_sections(self) -> MemoryEvolutionDecision:
        if self.operation == MemoryEvolutionDecisionOperation.NEXT_ACTION and self.execution_selection is None:
            raise ValueError("execution_selection is required when operation is next_action")
        if self.operation != MemoryEvolutionDecisionOperation.NEXT_ACTION and self.execution_selection is not None:
            raise ValueError("execution_selection is only allowed when operation is next_action")
        return self


class MemoryEvolutionBeliefScoreOutput(MemoryEvolutionBeliefScore):
    belief_state: MemoryEvolutionBeliefState


class MemoryEvolutionAnswerSelectionOutput(MemoryEvolutionAnswerSelection):
    selected_memory_ids: list[str]
    supporting_memory_ids: list[str]
    citation_memory_ids: list[str]
    rationale: str


class MemoryEvolutionTemporalFrameOutput(MemoryEvolutionTemporalFrame):
    scope_kind: MemoryEvolutionScopeKind
    scope_key: str | None
    anchor_id: str | None
    valid_from: datetime | None
    valid_to: datetime | None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class MemoryEvolutionLifecycleSnapshotOutput(MemoryEvolutionLifecycleSnapshot):
    checkpoint_active_record_ids: list[str]
    checkpoint_superseded_record_ids: list[str]
    checkpoint_retained_record_ids: list[str]
    rationale: str


class MemoryEvolutionRetrievalContextOutput(MemoryEvolutionRetrievalContext):
    query_relevant_memory_ids: list[str]
    query_historical_memory_ids: list[str]
    query_context_memory_ids: list[str]
    rejected_memory_ids: list[str]
    rationale: str


class MemoryEvolutionExecutionSelectionOutput(MemoryEvolutionExecutionSelection):
    selected_action_memory_ids: list[str]
    active_work_state_memory_ids: list[str]
    command_context_memory_ids: list[str]
    suppressed_branch_memory_ids: list[str]
    rationale: str


class MemoryEvolutionDecisionOutput(MemoryEvolutionDecision):
    """Strict provider response for benchmark memory-evolution decisions."""

    answer: str | None
    next_action: str | None
    query_temporal_frame: MemoryEvolutionTemporalFrameOutput
    answer_selection: MemoryEvolutionAnswerSelectionOutput
    lifecycle_snapshot: MemoryEvolutionLifecycleSnapshotOutput
    retrieval_context: MemoryEvolutionRetrievalContextOutput
    execution_selection: MemoryEvolutionExecutionSelectionOutput | None
    evaluated_belief_ids: list[str]
    belief_scores: list[MemoryEvolutionBeliefScoreOutput]
    failure_mode: str | None
    requires_judge_review: bool

class MemoryEvolutionFailureBucket(StrEnum):
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    ANSWER_MISMATCH = "answer_mismatch"
    NEXT_ACTION_MISMATCH = "next_action_mismatch"
    SELECTED_MEMORY_MISMATCH = "selected_memory_mismatch"
    EXPECTED_RETRIEVAL_MISSING = "expected_retrieval_missing"
    EXCLUDED_MEMORY_SELECTED = "excluded_memory_selected"
    EXPECTED_CITATION_MISSING = "expected_citation_missing"
    CITATION_CHANNEL_POLLUTION = "citation_channel_pollution"
    BELIEF_ID_USED_AS_CITATION = "belief_id_used_as_citation"
    EXPECTED_CHECKPOINT_ACTIVE_RECORD_MISSING = "expected_checkpoint_active_record_missing"
    EXPECTED_CHECKPOINT_SUPERSEDED_RECORD_MISSING = "expected_checkpoint_superseded_record_missing"
    SUPERSEDED_RECORD_MARKED_CHECKPOINT_ACTIVE = "superseded_record_marked_checkpoint_active"
    HISTORICAL_ANSWER_RECORD_MARKED_CHECKPOINT_ACTIVE = "historical_answer_record_marked_checkpoint_active"
    QUERY_LIFECYCLE_CONFLATION = "query_lifecycle_conflation"
    SELECTED_MEMORY_REJECTED = "selected_memory_rejected"
    WRONG_TEMPORAL_MODE = "wrong_temporal_mode"
    HISTORICAL_MEMORY_NOT_MARKED_QUERY_RELEVANT = "historical_memory_not_marked_query_relevant"
    CHECKPOINT_ACTIVE_RECORD_MISSING_FROM_LIFECYCLE_SNAPSHOT = "checkpoint_active_record_missing_from_lifecycle_snapshot"
    COMMAND_EVENT_SELECTED_AS_ACTIVE_STATE = "command_event_selected_as_active_state"
    ACTIVE_EXECUTION_STATE_MISSING = "active_execution_state_missing"
    EXPECTED_CHECKPOINT_RETAINED_RECORD_MISSING = "expected_checkpoint_retained_record_missing"
    BELIEF_RANKING_MISSING_SCORE = "belief_ranking_missing_score"
    BELIEF_RANKING_WRONG_ORDER = "belief_ranking_wrong_order"
    BELIEF_SCORE_ORDER_CONTRADICTS_SELECTED_ORDER = "belief_score_order_contradicts_selected_order"
    WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL = "weakened_belief_ranked_above_neutral"
    BELIEF_STATE_MISMATCH = "belief_state_mismatch"
    BELIEF_SCORE_MISMATCH = "belief_score_mismatch"
    BELIEF_CONFIDENCE_NOT_DEGRADED = "belief_confidence_not_degraded"
    TEMPORAL_FRAME_MISMATCH = "temporal_frame_mismatch"
    TEMPORAL_KIND_MISMATCH = "temporal_kind_mismatch"
    TEMPORAL_SCOPE_MISMATCH = "temporal_scope_mismatch"
    TEMPORAL_ANCHOR_MISMATCH = "temporal_anchor_mismatch"
    TEMPORAL_INTERVAL_MISMATCH = "temporal_interval_mismatch"
    TEMPORAL_FRAME_UNDER_SPECIFIED = "temporal_frame_under_specified"
    TEMPORAL_SCOPE_KEY_MISMATCH = "temporal_scope_key_mismatch"
    TEMPORAL_EXTRA_ANCHOR = "temporal_extra_anchor"
    TEMPORAL_EXTRA_INTERVAL = "temporal_extra_interval"
    RECORD_LIFECYCLE_CONTENT_STATE_CONFLATION = "record_lifecycle_content_state_conflation"
    SOURCE_TRUST_LOSER_MARKED_ACTIVE = "source_trust_loser_marked_active"
    EXPECTED_EXCLUDED_MEMORY_CHANNEL_MISSING = "expected_excluded_memory_channel_missing"


class MemoryEvolutionWarningBucket(StrEnum):
    ACTIVE_CHANNEL_POLLUTION = "active_channel_pollution"
    BELIEF_CANDIDATE_MARKED_ACTIVE = "belief_candidate_marked_active"
    BELIEF_SCORE_CALIBRATION_DRIFT = "belief_score_calibration_drift"
    LIFECYCLE_CHANNEL_DRIFT = "lifecycle_channel_drift"
    CONTEXT_CITATION_IN_DIRECT_CHANNEL = "context_citation_in_direct_channel"
    EXTRA_CHECKPOINT_ACTIVE_RECORD_IDS = "extra_checkpoint_active_record_ids"
    EXTRA_SELECTED_EVALUATED_BELIEF_IDS = "extra_selected_evaluated_belief_ids"
    BELIEF_SCORES_ON_NON_BELIEF_CHECKPOINT = "belief_scores_on_non_belief_checkpoint"
    TEMPORAL_FRAME_ENRICHMENT = "temporal_frame_enrichment"


class MemoryEvolutionDecisionDiagnostics(BaseModel):
    assertion_passed: bool
    failure_buckets: list[MemoryEvolutionFailureBucket] = Field(default_factory=list)
    warning_buckets: list[MemoryEvolutionWarningBucket] = Field(default_factory=list)
    missing_retrieval_ids: list[str] = Field(default_factory=list)
    extra_selected_ids: list[str] = Field(default_factory=list)
    missing_citation_ids: list[str] = Field(default_factory=list)
    extra_citation_ids: list[str] = Field(default_factory=list)
    belief_ids_used_as_citations: list[str] = Field(default_factory=list)
    belief_ids_marked_active: list[str] = Field(default_factory=list)
    evaluated_belief_ids: list[str] = Field(default_factory=list)
    extra_checkpoint_active_record_ids: list[str] = Field(default_factory=list)
    lifecycle_drift_ids: list[str] = Field(default_factory=list)
    query_lifecycle_conflation_ids: list[str] = Field(default_factory=list)
    selected_historical_record_ids: list[str] = Field(default_factory=list)
    historical_answer_record_marked_checkpoint_active_ids: list[str] = Field(default_factory=list)
    checkpoint_active_record_missing_expected_ids: list[str] = Field(default_factory=list)
    checkpoint_superseded_record_missing_expected_ids: list[str] = Field(default_factory=list)
    command_events_selected_as_active_state: list[str] = Field(default_factory=list)
    expected_belief_ranking: list[str] = Field(default_factory=list)
    actual_belief_ranking: list[str] = Field(default_factory=list)
    score_mismatch_ids: list[str] = Field(default_factory=list)
    belief_state_mismatch_ids: list[str] = Field(default_factory=list)
    missing_required_belief_score_ids: list[str] = Field(default_factory=list)
    belief_effect_order_errors: list[str] = Field(default_factory=list)
    temporal_frame_mismatch: bool = False
    temporal_kind_mismatch: bool = False
    temporal_scope_mismatch: bool = False
    temporal_anchor_mismatch: bool = False
    temporal_interval_mismatch: bool = False
    temporal_frame_under_specified: bool = False
    temporal_scope_key_mismatch: bool = False
    temporal_extra_anchor: bool = False
    temporal_extra_interval: bool = False
    temporal_frame_warning: bool = False
    expected_temporal_frame: MemoryEvolutionTemporalFrame | None = None
    actual_temporal_frame: MemoryEvolutionTemporalFrame | None = None
    record_lifecycle_content_state_conflation_ids: list[str] = Field(default_factory=list)
    excluded_memory_missing_channel_ids: list[str] = Field(default_factory=list)
    lifecycle_expectation_scope: str = "query_relevant"
    rationale: str

    model_config = ConfigDict(extra="forbid")
