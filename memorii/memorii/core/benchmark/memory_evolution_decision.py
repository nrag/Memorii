"""Benchmark-only memory evolution decision models and deterministic providers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_provider.models import (
    LLMDecisionResult,
    LLMStructuredRequest,
    LLMStructuredResponse,
)
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result

BucketT = TypeVar("BucketT", bound=str)

# Shared by the judge and the prompt contract. Keeping this rubric in one
# place prevents a model-facing calibration instruction from drifting from the
# score threshold that determines benchmark correctness.
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


def memory_evolution_context_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecisionContext:
    contract = memory_evolution_checkpoint_contract(scenario=scenario, checkpoint=checkpoint)
    visible_events = _visible_events_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    visible_memory_cards = _visible_memory_cards_for_events(visible_events)
    entity_resolution_cards = _entity_resolution_cards_for_events(visible_events)
    temporal_anchor_cards = _temporal_anchor_cards_for_events(visible_events)
    entity_state_cards = _entity_state_cards_for_events(events=visible_events, checkpoint=checkpoint)
    evidence_effect_cards = _evidence_effect_cards_for_events(visible_events)
    metadata: dict[str, object] = {
        "discriminative": scenario.discriminative,
        "checkpoint_contract": contract.model_dump(mode="json"),
        "output_channel_contract": _output_channel_contract(contract),
        "evidence_effect_policy": _evidence_effect_policy(contract),
        "temporal_grounding_policy": _temporal_grounding_policy(),
    }
    return MemoryEvolutionDecisionContext(
        scenario_id=scenario.scenario_id,
        family=scenario.family,
        events=visible_events,
        checkpoint=MemoryEvolutionVisibleCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            timestamp=checkpoint.timestamp,
            query_or_task=checkpoint.query_or_task,
            query_language=checkpoint.query_language,
            evidence_languages=list(checkpoint.evidence_languages),
            answer_language_policy=checkpoint.answer_language_policy,
            cross_lingual=checkpoint.cross_lingual,
            transliteration_policy=checkpoint.transliteration_policy,
        ),
        visible_memory_cards=visible_memory_cards,
        entity_resolution_cards=entity_resolution_cards,
        temporal_anchor_cards=temporal_anchor_cards,
        entity_state_cards=entity_state_cards,
        evidence_effect_cards=evidence_effect_cards,
        metadata=metadata,
    )


def expected_memory_evolution_decision_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecision:
    contract = memory_evolution_checkpoint_contract(scenario=scenario, checkpoint=checkpoint)
    execution_selection = None
    if contract.requires_execution_selection:
        execution_selection = MemoryEvolutionExecutionSelection(
            selected_action_memory_ids=list(checkpoint.expected_retrieval_ids),
            active_work_state_memory_ids=_lifecycle_expected_ids(
                checkpoint=checkpoint,
                lifecycle_kind="active",
            ),
            command_context_memory_ids=_command_context_ids(scenario=scenario, checkpoint=checkpoint),
            suppressed_branch_memory_ids=_dedupe_string_ids([
                *checkpoint.expected_excluded_memory_ids,
                *checkpoint.expected_checkpoint_superseded_record_ids,
                *checkpoint.expected_checkpoint_retained_record_ids,
            ]),
            rationale="Expected active execution state and suppressed branch history.",
        )
    return MemoryEvolutionDecision(
        operation=(
            MemoryEvolutionDecisionOperation.NEXT_ACTION
            if checkpoint.expected_next_action is not None
            else MemoryEvolutionDecisionOperation.ANSWER
        ),
        answer=checkpoint.expected_answer,
        next_action=checkpoint.expected_next_action,
        confidence=0.9,
        query_temporal_frame=_expected_temporal_frame(checkpoint=checkpoint, contract=contract),
        answer_selection=MemoryEvolutionAnswerSelection(
            selected_memory_ids=list(checkpoint.expected_retrieval_ids),
            supporting_memory_ids=list(checkpoint.expected_retrieval_ids),
            citation_memory_ids=list(checkpoint.expected_citation_ids),
            temporal_mode=contract.answer_temporal_mode,
            rationale="Expected direct answer or action-support memories.",
        ),
        lifecycle_snapshot=MemoryEvolutionLifecycleSnapshot(
            checkpoint_active_record_ids=_lifecycle_expected_ids(
                checkpoint=checkpoint,
                lifecycle_kind="active",
            ),
            checkpoint_superseded_record_ids=_lifecycle_expected_ids(
                checkpoint=checkpoint,
                lifecycle_kind="superseded",
            ),
            checkpoint_retained_record_ids=_lifecycle_expected_ids(
                checkpoint=checkpoint,
                lifecycle_kind="retained",
            ),
            evaluation_time=checkpoint.timestamp,
            rationale="Expected checkpoint-current lifecycle state.",
        ),
        retrieval_context=MemoryEvolutionRetrievalContext(
            query_relevant_memory_ids=_dedupe_string_ids([
                *checkpoint.expected_retrieval_ids,
                *checkpoint.expected_citation_ids,
            ]),
            query_historical_memory_ids=(
                list(checkpoint.expected_retrieval_ids)
                if contract.answer_temporal_mode == MemoryEvolutionAnswerTemporalMode.HISTORICAL
                else []
            ),
            query_context_memory_ids=_dedupe_string_ids([
                *([memory_id for memory_id in checkpoint.expected_checkpoint_active_record_ids if memory_id not in checkpoint.expected_retrieval_ids]
                  if contract.answer_temporal_mode == MemoryEvolutionAnswerTemporalMode.HISTORICAL else []),
                *checkpoint.expected_checkpoint_retained_record_ids,
            ]),
            rejected_memory_ids=_expected_rejected_memory_ids(
                checkpoint=checkpoint,
                contract=contract,
            ),
            rationale="Expected retrieval context, historical contrast, and rejected memories.",
        ),
        execution_selection=execution_selection,
        evaluated_belief_ids=_expected_belief_ids(checkpoint),
        belief_scores=[
            MemoryEvolutionBeliefScore(
                memory_id=memory_id,
                belief=belief,
                belief_state=next(
                    (
                        expectation.expected_state.value
                        for expectation in checkpoint.expected_belief_states
                        if expectation.memory_id == memory_id
                    ),
                    None,
                ),
            )
            for memory_id, belief in checkpoint.expected_belief_scores.items()
        ]
        or [
            MemoryEvolutionBeliefScore(memory_id=memory_id, belief=max(0.0, 1.0 - index * 0.2))
            for index, memory_id in enumerate(checkpoint.expected_belief_ranking)
        ],
        rationale="expected benchmark memory evolution decision",
        failure_mode=None,
        requires_judge_review=False,
    )

def rule_memory_evolution_decision_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecision:
    contract = memory_evolution_checkpoint_contract(scenario=scenario, checkpoint=checkpoint)
    ranked = _rank_events_by_shallow_overlap(scenario=scenario, checkpoint=checkpoint)
    selected = [ranked[0].event_id] if ranked else []
    selected_event = ranked[0] if ranked else None
    eligible_events = [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]
    latest_event = max(eligible_events, key=lambda event: event.timestamp, default=None)
    state_cards = _entity_state_cards_for_events(events=eligible_events, checkpoint=checkpoint)
    if state_cards:
        active_ids = [
            card.memory_id
            for card in state_cards
            if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_ACTIVE
        ]
        superseded_ids = [
            card.memory_id
            for card in state_cards
            if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_SUPERSEDED
        ]
        retained_ids = [
            card.memory_id
            for card in state_cards
            if card.record_lifecycle == MemoryEvolutionRecordLifecycleState.CHECKPOINT_RETAINED
        ]
    else:
        active_ids = [latest_event.event_id] if latest_event is not None else []
        superseded_ids = []
        retained_ids = []
    answer = _extract_shallow_answer(selected_event.content) if selected_event is not None else None
    next_action = f"continue {selected[0]}" if selected else None
    belief_scores = [
        MemoryEvolutionBeliefScore(memory_id=event.event_id, belief=0.5)
        for event in ranked[:3]
    ]
    execution_selection = None
    if contract.requires_execution_selection:
        execution_selection = MemoryEvolutionExecutionSelection(
            selected_action_memory_ids=selected,
            active_work_state_memory_ids=active_ids,
            command_context_memory_ids=[],
            suppressed_branch_memory_ids=[],
            rationale="rule provider uses shallow recency for execution state",
        )
    return MemoryEvolutionDecision(
        operation=(
            MemoryEvolutionDecisionOperation.NEXT_ACTION
            if checkpoint.expected_next_action is not None
            else MemoryEvolutionDecisionOperation.ANSWER
        ),
        answer=answer,
        next_action=next_action,
        confidence=0.45,
        query_temporal_frame=_expected_temporal_frame(checkpoint=checkpoint, contract=contract),
        answer_selection=MemoryEvolutionAnswerSelection(
            selected_memory_ids=selected,
            supporting_memory_ids=selected,
            citation_memory_ids=selected,
            temporal_mode=contract.answer_temporal_mode,
            rationale="rule provider uses shallow token overlap",
        ),
        lifecycle_snapshot=MemoryEvolutionLifecycleSnapshot(
            checkpoint_active_record_ids=active_ids,
            checkpoint_superseded_record_ids=superseded_ids,
            checkpoint_retained_record_ids=retained_ids,
            evaluation_time=checkpoint.timestamp,
            rationale="rule provider uses recency as current lifecycle",
        ),
        retrieval_context=MemoryEvolutionRetrievalContext(
            query_relevant_memory_ids=selected,
            query_historical_memory_ids=selected if contract.answer_temporal_mode == MemoryEvolutionAnswerTemporalMode.HISTORICAL else [],
            query_context_memory_ids=[],
            rejected_memory_ids=[],
            rationale="rule provider has no semantic rejection model",
        ),
        execution_selection=execution_selection,
        belief_scores=belief_scores,
        rationale=(
            "rule memory evolution provider uses shallow token overlap and recency; "
            "it does not reason over temporal addressability, trust hierarchy, semantic roles, "
            "belief dependency, scoped preferences, or abandoned work"
        ),
        failure_mode="rule_limit" if scenario.discriminative else None,
        requires_judge_review=scenario.discriminative,
    )

def memory_evolution_assertion_passed(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    decision: dict[str, object],
) -> bool:
    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=decision,
    )
    return diagnostics.assertion_passed


def memory_evolution_decision_diagnostics(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    decision: dict[str, object],
) -> MemoryEvolutionDecisionDiagnostics:
    failure_buckets: list[MemoryEvolutionFailureBucket] = []
    warning_buckets: list[MemoryEvolutionWarningBucket] = []
    try:
        parsed = MemoryEvolutionDecision.model_validate(decision)
    except ValidationError as exc:
        return MemoryEvolutionDecisionDiagnostics(
            assertion_passed=False,
            failure_buckets=[MemoryEvolutionFailureBucket.SCHEMA_VALIDATION_FAILED],
            rationale=f"MemoryEvolutionDecision schema validation failed: {exc.errors()}",
        )

    contract = memory_evolution_checkpoint_contract(scenario=scenario, checkpoint=checkpoint)
    answer_selection = parsed.answer_selection
    lifecycle = parsed.lifecycle_snapshot
    retrieval = parsed.retrieval_context
    execution = parsed.execution_selection
    expected_temporal_frame = _expected_temporal_frame(checkpoint=checkpoint, contract=contract)
    actual_temporal_frame = parsed.query_temporal_frame

    score_by_id = {score.memory_id: score.belief for score in parsed.belief_scores}
    belief_state_by_id = {
        score.memory_id: score.belief_state
        for score in parsed.belief_scores
        if score.belief_state is not None
    }
    selected_ids = list(answer_selection.selected_memory_ids)
    selected = set(selected_ids)
    supporting = set(answer_selection.supporting_memory_ids)
    citations = list(answer_selection.citation_memory_ids)
    citation_set = set(citations)
    checkpoint_active = set(lifecycle.checkpoint_active_record_ids)
    checkpoint_superseded = set(lifecycle.checkpoint_superseded_record_ids)
    checkpoint_retained = set(lifecycle.checkpoint_retained_record_ids)
    query_relevant = set(retrieval.query_relevant_memory_ids)
    query_historical = set(retrieval.query_historical_memory_ids)
    rejected = set(retrieval.rejected_memory_ids)
    evaluated_belief_ids = _dedupe_string_ids(
        [
            *parsed.evaluated_belief_ids,
            *[score.memory_id for score in parsed.belief_scores if _is_belief_memory_id(score.memory_id, checkpoint=checkpoint)],
        ]
    )

    lifecycle_expectation_scope = _lifecycle_expectation_scope(checkpoint)
    expected_active_ids = _lifecycle_expected_ids(checkpoint=checkpoint, lifecycle_kind="active")
    expected_superseded_ids = _lifecycle_expected_ids(checkpoint=checkpoint, lifecycle_kind="superseded")
    expected_retained_ids = _lifecycle_expected_ids(checkpoint=checkpoint, lifecycle_kind="retained")

    if answer_selection.temporal_mode != contract.answer_temporal_mode:
        failure_buckets.append(MemoryEvolutionFailureBucket.WRONG_TEMPORAL_MODE)
    temporal_frame_diagnostics = _temporal_frame_diagnostics(
        expected=expected_temporal_frame,
        actual=actual_temporal_frame,
        contract=contract,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    temporal_kind_mismatch = temporal_frame_diagnostics["temporal_kind_mismatch"]
    temporal_scope_mismatch = temporal_frame_diagnostics["temporal_scope_mismatch"]
    temporal_anchor_mismatch = temporal_frame_diagnostics["temporal_anchor_mismatch"]
    temporal_interval_mismatch = temporal_frame_diagnostics["temporal_interval_mismatch"]
    temporal_frame_under_specified = temporal_frame_diagnostics["temporal_frame_under_specified"]
    temporal_scope_key_mismatch = temporal_frame_diagnostics["temporal_scope_key_mismatch"]
    temporal_extra_anchor = temporal_frame_diagnostics["temporal_extra_anchor"]
    temporal_extra_interval = temporal_frame_diagnostics["temporal_extra_interval"]
    temporal_frame_warning = temporal_frame_diagnostics["temporal_frame_warning"]
    temporal_frame_mismatch = any(
        value
        for key, value in temporal_frame_diagnostics.items()
        if key != "temporal_frame_warning"
    )
    if temporal_frame_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_FRAME_MISMATCH)
    if temporal_frame_warning:
        warning_buckets.append(MemoryEvolutionWarningBucket.TEMPORAL_FRAME_ENRICHMENT)
    if temporal_kind_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_KIND_MISMATCH)
    if temporal_scope_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_SCOPE_MISMATCH)
    if temporal_anchor_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_ANCHOR_MISMATCH)
    if temporal_interval_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_INTERVAL_MISMATCH)
    if temporal_frame_under_specified:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_FRAME_UNDER_SPECIFIED)
    if temporal_scope_key_mismatch:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_SCOPE_KEY_MISMATCH)
    if temporal_extra_anchor:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_EXTRA_ANCHOR)
    if temporal_extra_interval:
        failure_buckets.append(MemoryEvolutionFailureBucket.TEMPORAL_EXTRA_INTERVAL)

    if _requires_answer_text(contract) and checkpoint.expected_answer is not None and not _answer_matches_expected(
        actual=parsed.answer,
        expected=checkpoint.expected_answer,
        aliases=checkpoint.expected_answer_aliases,
    ):
        failure_buckets.append(MemoryEvolutionFailureBucket.ANSWER_MISMATCH)

    if checkpoint.expected_next_action is not None and not _next_action_matches_expected(
        actual=parsed.next_action,
        expected=checkpoint.expected_next_action,
        checkpoint=checkpoint,
        scenario=scenario,
        parsed=parsed,
        contract=contract,
    ):
        failure_buckets.append(MemoryEvolutionFailureBucket.NEXT_ACTION_MISMATCH)

    expected_retrieval = list(checkpoint.expected_retrieval_ids)
    expected_retrieval_set = set(expected_retrieval)
    retrieval_surface = selected | supporting | query_relevant
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_RANKING:
        retrieval_surface |= set(evaluated_belief_ids)
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        retrieval_surface |= citation_set

    missing_retrieval_ids: list[str] = []
    extra_selected_ids: list[str] = []
    if scenario.discriminative and expected_retrieval and _requires_exact_selected_memory(contract):
        if selected_ids != expected_retrieval:
            missing_retrieval_ids = _ordered_missing(expected_retrieval, selected)
            extra_selected_ids = _ordered_extra(selected_ids, expected_retrieval_set)
            failure_buckets.append(MemoryEvolutionFailureBucket.SELECTED_MEMORY_MISMATCH)
    elif expected_retrieval and not expected_retrieval_set.issubset(retrieval_surface):
        missing_retrieval_ids = _ordered_missing(expected_retrieval, retrieval_surface)
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_RETRIEVAL_MISSING)

    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        extra_belief_selected = [
            memory_id
            for memory_id in _ordered_extra(selected_ids, expected_retrieval_set)
            if _is_belief_memory_id(memory_id, checkpoint=checkpoint)
        ]
        if extra_belief_selected:
            extra_selected_ids = _dedupe_string_ids([*extra_selected_ids, *extra_belief_selected])
            warning_buckets.append(MemoryEvolutionWarningBucket.EXTRA_SELECTED_EVALUATED_BELIEF_IDS)

    if selected & set(checkpoint.expected_excluded_memory_ids):
        failure_buckets.append(MemoryEvolutionFailureBucket.EXCLUDED_MEMORY_SELECTED)

    excluded_memory_missing_channel_ids: list[str] = []
    if contract.excluded_memory_policy == MemoryEvolutionExcludedMemoryPolicy.REJECTED_OR_CONTEXT:
        exclusion_surface = rejected | set(retrieval.query_context_memory_ids)
        if execution is not None:
            exclusion_surface |= set(execution.suppressed_branch_memory_ids)
        excluded_memory_missing_channel_ids = _ordered_missing(
            checkpoint.expected_excluded_memory_ids,
            exclusion_surface,
        )
        if excluded_memory_missing_channel_ids:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_EXCLUDED_MEMORY_CHANNEL_MISSING)

    selected_rejected_ids = sorted(selected & rejected)
    if selected_rejected_ids:
        failure_buckets.append(MemoryEvolutionFailureBucket.SELECTED_MEMORY_REJECTED)
        if set(selected_rejected_ids) & (set(checkpoint.expected_checkpoint_superseded_record_ids) | set(checkpoint.expected_checkpoint_retained_record_ids)):
            failure_buckets.append(MemoryEvolutionFailureBucket.QUERY_LIFECYCLE_CONFLATION)

    missing_citation_ids: list[str] = []
    extra_citation_ids: list[str] = []
    belief_ids_used_as_citations: list[str] = []
    if checkpoint.expected_citation_ids:
        expected_citations = set(checkpoint.expected_citation_ids)
        missing_citation_ids = _ordered_missing(checkpoint.expected_citation_ids, citation_set)
        extra_citation_ids = _ordered_extra(citations, expected_citations)
        if missing_citation_ids:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CITATION_MISSING)
        if extra_citation_ids:
            if _extra_direct_citations_are_warning_only(
                extra_citation_ids=extra_citation_ids,
                checkpoint=checkpoint,
                contract=contract,
            ):
                warning_buckets.append(MemoryEvolutionWarningBucket.CONTEXT_CITATION_IN_DIRECT_CHANNEL)
            else:
                failure_buckets.append(MemoryEvolutionFailureBucket.CITATION_CHANNEL_POLLUTION)
        belief_ids_used_as_citations = [
            memory_id
            for memory_id in citations
            if _is_belief_memory_id(memory_id, checkpoint=checkpoint)
        ]
        if belief_ids_used_as_citations:
            if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION and not missing_citation_ids:
                warning_buckets.append(MemoryEvolutionWarningBucket.CONTEXT_CITATION_IN_DIRECT_CHANNEL)
            else:
                failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_ID_USED_AS_CITATION)

    checkpoint_active_equivalent = set(checkpoint_active)
    if contract.belief_lifecycle_policy == MemoryEvolutionBeliefLifecyclePolicy.DEGRADED_RETAINED_EVALUABLE:
        checkpoint_active_equivalent |= {
            memory_id
            for memory_id in set(evaluated_belief_ids) | set(score_by_id)
            if _is_belief_memory_id(memory_id, checkpoint=checkpoint)
        }
    missing_checkpoint_active = _ordered_missing(
        expected_active_ids,
        checkpoint_active_equivalent,
    )
    if missing_checkpoint_active:
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_ACTIVE_RECORD_MISSING)
    lifecycle_content_conflation_ids = _record_lifecycle_content_state_conflation_ids(
        scenario=scenario,
        missing_checkpoint_active_ids=missing_checkpoint_active,
        checkpoint_superseded=checkpoint_superseded,
        checkpoint_retained=checkpoint_retained,
    )
    if lifecycle_content_conflation_ids:
        failure_buckets.append(MemoryEvolutionFailureBucket.RECORD_LIFECYCLE_CONTENT_STATE_CONFLATION)

    non_checkpoint_active = checkpoint_superseded | checkpoint_retained
    if contract.requires_execution_selection and execution is not None:
        non_checkpoint_active |= set(execution.suppressed_branch_memory_ids)
    missing_checkpoint_superseded = _ordered_missing(
        expected_superseded_ids,
        non_checkpoint_active if contract.lifecycle_policy == MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT else checkpoint_superseded,
    )
    if missing_checkpoint_superseded:
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_SUPERSEDED_RECORD_MISSING)

    superseded_marked_checkpoint_active = set(expected_superseded_ids) & checkpoint_active
    if superseded_marked_checkpoint_active:
        failure_buckets.append(MemoryEvolutionFailureBucket.SUPERSEDED_RECORD_MARKED_CHECKPOINT_ACTIVE)
    source_trust_losers_marked_active = _source_trust_losers_marked_active(
        scenario=scenario,
        checkpoint=checkpoint,
        checkpoint_active=checkpoint_active,
        selected=selected,
    )
    if source_trust_losers_marked_active:
        failure_buckets.append(MemoryEvolutionFailureBucket.SOURCE_TRUST_LOSER_MARKED_ACTIVE)

    selected_historical_record_ids = [
        memory_id
        for memory_id in selected_ids
        if memory_id in set(checkpoint.expected_checkpoint_superseded_record_ids) | set(checkpoint.expected_checkpoint_retained_record_ids)
    ]
    historical_answer_record_marked_checkpoint_active_ids = [memory_id for memory_id in selected_historical_record_ids if memory_id in checkpoint_active]
    if historical_answer_record_marked_checkpoint_active_ids:
        failure_buckets.append(MemoryEvolutionFailureBucket.HISTORICAL_ANSWER_RECORD_MARKED_CHECKPOINT_ACTIVE)
        failure_buckets.append(MemoryEvolutionFailureBucket.QUERY_LIFECYCLE_CONFLATION)

    if contract.answer_temporal_mode == MemoryEvolutionAnswerTemporalMode.HISTORICAL:
        historical_missing = _ordered_missing(checkpoint.expected_retrieval_ids, query_historical | selected)
        if historical_missing:
            failure_buckets.append(MemoryEvolutionFailureBucket.HISTORICAL_MEMORY_NOT_MARKED_QUERY_RELEVANT)

    _append_selected_memory_policy_failures(
        failure_buckets=failure_buckets,
        contract=contract,
        checkpoint=checkpoint,
        selected_ids=selected_ids,
        selected=selected,
        checkpoint_active=checkpoint_active,
        query_historical=query_historical,
        execution=execution,
    )

    if expected_active_ids and not set(expected_active_ids).issubset(checkpoint_active_equivalent):
        failure_buckets.append(MemoryEvolutionFailureBucket.CHECKPOINT_ACTIVE_RECORD_MISSING_FROM_LIFECYCLE_SNAPSHOT)

    missing_checkpoint_retained = _ordered_missing(
        expected_retained_ids,
        non_checkpoint_active if contract.lifecycle_policy == MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT else checkpoint_retained,
    )
    if missing_checkpoint_retained:
        if contract.lifecycle_policy in {
            MemoryEvolutionLifecyclePolicy.EXACT,
            MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT,
        }:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_RETAINED_RECORD_MISSING)
        else:
            warning_buckets.append(MemoryEvolutionWarningBucket.LIFECYCLE_CHANNEL_DRIFT)

    extra_checkpoint_active_record_ids = _ordered_extra(lifecycle.checkpoint_active_record_ids, set(expected_active_ids))
    if extra_checkpoint_active_record_ids:
        warning_buckets.append(MemoryEvolutionWarningBucket.EXTRA_CHECKPOINT_ACTIVE_RECORD_IDS)

    belief_ids_marked_active = [
        memory_id
        for memory_id in lifecycle.checkpoint_active_record_ids
        if _is_belief_memory_id(memory_id, checkpoint=checkpoint)
    ]
    if belief_ids_marked_active and not checkpoint.expected_checkpoint_active_record_ids:
        warning_buckets.extend(
            [
                MemoryEvolutionWarningBucket.ACTIVE_CHANNEL_POLLUTION,
                MemoryEvolutionWarningBucket.BELIEF_CANDIDATE_MARKED_ACTIVE,
            ]
        )

    command_events_selected_as_active_state: list[str] = []
    if contract.requires_execution_selection:
        if execution is None:
            failure_buckets.append(MemoryEvolutionFailureBucket.ACTIVE_EXECUTION_STATE_MISSING)
        else:
            active_execution = set(execution.active_work_state_memory_ids) | set(execution.selected_action_memory_ids)
            if not set(expected_active_ids).issubset(active_execution):
                failure_buckets.append(MemoryEvolutionFailureBucket.ACTIVE_EXECUTION_STATE_MISSING)
            command_ids = set(_command_context_ids(scenario=scenario, checkpoint=checkpoint))
            command_events_selected_as_active_state = sorted(command_ids & active_execution)
            if command_events_selected_as_active_state:
                failure_buckets.append(MemoryEvolutionFailureBucket.COMMAND_EVENT_SELECTED_AS_ACTIVE_STATE)

    if parsed.belief_scores and contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.NONE:
        warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORES_ON_NON_BELIEF_CHECKPOINT)

    expected_belief_ranking: list[str] = []
    actual_belief_ranking: list[str] = []
    score_mismatch_ids: list[str] = []
    belief_effect_order_errors: list[str] = []
    if checkpoint.expected_belief_ranking:
        if not set(checkpoint.expected_belief_ranking).issubset(score_by_id):
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_RANKING_MISSING_SCORE)
        expected_belief_ranking = list(checkpoint.expected_belief_ranking)
        selected_belief_ranking = [
            memory_id for memory_id in selected_ids if memory_id in set(checkpoint.expected_belief_ranking)
        ]
        score_ranked = sorted(score_by_id, key=lambda key: (-score_by_id[key], key))
        actual_belief_ranking = (
            selected_belief_ranking[: len(checkpoint.expected_belief_ranking)]
            if set(checkpoint.expected_belief_ranking).issubset(selected_belief_ranking)
            else score_ranked[: len(checkpoint.expected_belief_ranking)]
        )
        if actual_belief_ranking != expected_belief_ranking:
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_RANKING_WRONG_ORDER)
            belief_effect_order_errors = _belief_effect_order_errors(
                scenario=scenario,
                checkpoint=checkpoint,
                ranking=actual_belief_ranking,
            )
            if belief_effect_order_errors:
                failure_buckets.append(MemoryEvolutionFailureBucket.WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL)
        score_order_errors = _belief_score_order_errors(
            ranking=actual_belief_ranking,
            score_by_id=score_by_id,
        )
        if score_order_errors:
            score_mismatch_ids.extend(_belief_ids_from_order_errors(score_order_errors))
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_ORDER_CONTRADICTS_SELECTED_ORDER)
            belief_effect_score_errors = _belief_effect_order_errors(
                scenario=scenario,
                checkpoint=checkpoint,
                ranking=score_ranked,
            )
            if belief_effect_score_errors:
                belief_effect_order_errors = _dedupe_string_ids(
                    [*belief_effect_order_errors, *belief_effect_score_errors]
                )
                failure_buckets.append(MemoryEvolutionFailureBucket.WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL)

    if checkpoint.expected_belief_scores:
        for memory_id, expected in checkpoint.expected_belief_scores.items():
            actual = score_by_id.get(memory_id)
            if actual is None:
                if contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.EXACT:
                    score_mismatch_ids.append(memory_id)
                continue
            if contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.DEGRADED_THRESHOLD:
                if expected <= DEGRADED_BELIEF_SCORE_MAX and actual > DEGRADED_BELIEF_SCORE_MAX:
                    score_mismatch_ids.append(memory_id)
                    failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_CONFIDENCE_NOT_DEGRADED)
                elif abs(actual - expected) > 0.05:
                    score_mismatch_ids.append(memory_id)
                    warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT)
            elif contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.RANKING_ONLY:
                if abs(actual - expected) > 0.05:
                    score_mismatch_ids.append(memory_id)
                    warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT)
            elif contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.EXACT and abs(actual - expected) > 0.05:
                score_mismatch_ids.append(memory_id)
                failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH)
        if (
            contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.EXACT
            and any(memory_id not in score_by_id for memory_id in checkpoint.expected_belief_scores)
        ):
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH)

    belief_state_mismatch_ids, missing_required_belief_score_ids = _belief_state_mismatch_ids(
        checkpoint=checkpoint,
        score_by_id=score_by_id,
        belief_state_by_id=belief_state_by_id,
    )
    if belief_state_mismatch_ids:
        failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_STATE_MISMATCH)
    if missing_required_belief_score_ids:
        score_mismatch_ids.extend(missing_required_belief_score_ids)
        failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH)

    lifecycle_drift_ids = _dedupe_string_ids([*missing_checkpoint_active, *missing_checkpoint_superseded, *missing_checkpoint_retained])
    query_lifecycle_conflation_ids = _dedupe_string_ids([
        *historical_answer_record_marked_checkpoint_active_ids,
        *lifecycle_content_conflation_ids,
    ])
    failure_buckets = _dedupe_preserving_order(failure_buckets)
    warning_buckets = _dedupe_preserving_order(warning_buckets)
    return MemoryEvolutionDecisionDiagnostics(
        assertion_passed=not failure_buckets,
        failure_buckets=failure_buckets,
        warning_buckets=warning_buckets,
        missing_retrieval_ids=missing_retrieval_ids,
        extra_selected_ids=extra_selected_ids,
        missing_citation_ids=missing_citation_ids,
        extra_citation_ids=extra_citation_ids,
        belief_ids_used_as_citations=belief_ids_used_as_citations,
        belief_ids_marked_active=belief_ids_marked_active,
        evaluated_belief_ids=evaluated_belief_ids,
        extra_checkpoint_active_record_ids=extra_checkpoint_active_record_ids,
        lifecycle_drift_ids=lifecycle_drift_ids,
        query_lifecycle_conflation_ids=query_lifecycle_conflation_ids,
        selected_historical_record_ids=selected_historical_record_ids,
        historical_answer_record_marked_checkpoint_active_ids=historical_answer_record_marked_checkpoint_active_ids,
        checkpoint_active_record_missing_expected_ids=missing_checkpoint_active,
        checkpoint_superseded_record_missing_expected_ids=missing_checkpoint_superseded,
        command_events_selected_as_active_state=command_events_selected_as_active_state,
        expected_belief_ranking=expected_belief_ranking,
        actual_belief_ranking=actual_belief_ranking,
        score_mismatch_ids=_dedupe_string_ids(score_mismatch_ids),
        belief_state_mismatch_ids=belief_state_mismatch_ids,
        missing_required_belief_score_ids=missing_required_belief_score_ids,
        belief_effect_order_errors=belief_effect_order_errors,
        temporal_frame_mismatch=temporal_frame_mismatch,
        temporal_kind_mismatch=temporal_kind_mismatch,
        temporal_scope_mismatch=temporal_scope_mismatch,
        temporal_anchor_mismatch=temporal_anchor_mismatch,
        temporal_interval_mismatch=temporal_interval_mismatch,
        temporal_frame_under_specified=temporal_frame_under_specified,
        temporal_scope_key_mismatch=temporal_scope_key_mismatch,
        temporal_extra_anchor=temporal_extra_anchor,
        temporal_extra_interval=temporal_extra_interval,
        temporal_frame_warning=temporal_frame_warning,
        expected_temporal_frame=expected_temporal_frame,
        actual_temporal_frame=actual_temporal_frame,
        record_lifecycle_content_state_conflation_ids=lifecycle_content_conflation_ids,
        excluded_memory_missing_channel_ids=excluded_memory_missing_channel_ids,
        lifecycle_expectation_scope=lifecycle_expectation_scope,
        rationale="memory evolution assertion diagnostics",
    )

def memory_evolution_checkpoint_contract(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionCheckpointContract:
    del scenario
    return checkpoint.contract

def _evidence_effect_policy(contract: MemoryEvolutionCheckpointContract) -> dict[str, str]:
    if contract.checkpoint_kind != MemoryEvolutionCheckpointKind.BELIEF_RANKING:
        return {}
    return {
        "source": "surface-derived evidence_effect_cards",
        "ranking_order": "supported > neutral > weakened > falsified",
        "neutral_rule": "A visible hypothesis with no support or weakening outranks an explicitly weakened hypothesis.",
    }


def _temporal_grounding_policy() -> dict[str, str]:
    return {
        "query_temporal_frame": "Resolve the time/scope frame of the query before selecting memories.",
        "entity_state_cards": "Use valid_from/valid_to and record_lifecycle to distinguish query-applicable state from checkpoint-current memory record state.",
        "content_state_warning": "Words such as archived, closed, inactive, deprecated, or abandoned in a fact describe the subject state, not the memory record lifecycle.",
    }


def _output_channel_contract(contract: MemoryEvolutionCheckpointContract) -> dict[str, str]:
    base = {
        "answer_projection_policy": f"Project answer text using {contract.answer_projection_policy.value}; do not infer projection from English query phrasing.",
        "query_temporal_frame": "Resolve whether the query asks for current state, a historical interval, an event anchor, scope, execution state, or belief state before selecting memories.",
        "answer_selection.selected_memory_ids": "Final answer or decision memories only. Historical memories are allowed only for historical queries.",
        "answer_selection.supporting_memory_ids": "Memories that directly support the selected answer or next action.",
        "answer_selection.citation_memory_ids": "Direct evidence/source memory ids only.",
        "answer_selection.temporal_mode": "Query temporal mode: current, historical, execution, or belief. Scope belongs only in query_temporal_frame.",
        "lifecycle_snapshot.checkpoint_active_record_ids": "Memory records currently asserted by the graph at checkpoint time, independent of query-temporal relevance or words in the fact text.",
        "lifecycle_snapshot.checkpoint_superseded_record_ids": "Memory records superseded, invalidated, blocked, lower-trust, or no-longer-current at checkpoint time.",
        "lifecycle_snapshot.checkpoint_retained_record_ids": "Memory records retained only for audit/history, not records whose subject merely has an archived/closed/inactive state.",
        "retrieval_context.query_relevant_memory_ids": "Memories useful for interpreting the query, selected answer, or audit context.",
        "retrieval_context.query_historical_memory_ids": "Memories relevant because the query asks about past state or because they explain supersession.",
        "retrieval_context.query_context_memory_ids": "Useful audit context that is neither final truth nor direct support.",
        "retrieval_context.rejected_memory_ids": "Stale, blocked, falsified, lower-trust, wrong-scope, or wrong-entity memories considered and ruled out.",
        "excluded_memory_policy": (
            f"{contract.excluded_memory_policy.value}: every expected excluded memory must appear in "
            "rejected_memory_ids, query_context_memory_ids, or the "
            "structured suppressed execution branch channel; supporting/citation alone is not rejection evidence."
        ),
        "lifecycle_expectation_scope": (
            "Full-graph lifecycle expectations are supplied only when the checkpoint defines expected_full_* "
            "fields; otherwise lifecycle arrays are judged for the query-relevant contract scope."
        ),
    }
    if contract.belief_score_policy != MemoryEvolutionBeliefScorePolicy.NONE:
        base["belief_scores"] = "Rank/evaluate belief ids; score order must agree with selected_memory_ids and answer text, while magnitudes may be calibrated estimates unless an exact rubric is provided."
        base["evaluated_belief_ids"] = "Belief candidates being ranked or degraded; do not use this as answer support."
    if contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.DEGRADED_THRESHOLD:
        base["belief_score_calibration"] = (
            f"For degraded beliefs, emit a score in [0.0, {DEGRADED_BELIEF_SCORE_MAX:.2f}]. "
            "Do not use 0.4 as a degraded score; it is above the benchmark's degraded band. "
            "Use the explicit belief_state field for content state and keep falsified roots at or below their stated bound."
        )
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.CURRENT_TRUTH:
        base["source_trust_conflict"] = (
            "When higher-trust tool/user evidence contradicts lower-trust transcript/noise evidence, "
            "select the highest-authority winning current-truth memory; put corroborating same-answer "
            "evidence in support/context and lower-trust contradictory claims in rejected/context plus "
            "checkpoint_superseded_record_ids."
        )
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        base["answer_selection.selected_memory_ids"] = "Select the falsifying/current evidence when no belief remains confident; degraded beliefs belong in evaluated/rejected/lifecycle-inactive channels."
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.EXECUTION_CONTINUATION:
        base["execution_selection.selected_action_memory_ids"] = "Select the active continuation branch/action, not blocked, abandoned, or user-command context events."
        base["execution_selection.active_work_state_memory_ids"] = "Current active branch/work state that the next action continues."
        base["execution_selection.command_context_memory_ids"] = "User command events that triggered retrieval; they are context, not active state."
        base["execution_selection.suppressed_branch_memory_ids"] = "Blocked, abandoned, stale, or lower-priority branches."
        base["next_action"] = "Non-empty action phrase for the selected active branch; exact wording is less important than branch state."
    return base

def _requires_exact_selected_memory(contract: MemoryEvolutionCheckpointContract) -> bool:
    return contract.checkpoint_kind not in {
        MemoryEvolutionCheckpointKind.BELIEF_RANKING,
        MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION,
    }


def _append_selected_memory_policy_failures(
    *,
    failure_buckets: list[MemoryEvolutionFailureBucket],
    contract: MemoryEvolutionCheckpointContract,
    checkpoint: MemoryEvolutionCheckpoint,
    selected_ids: list[str],
    selected: set[str],
    checkpoint_active: set[str],
    query_historical: set[str],
    execution: MemoryEvolutionExecutionSelection | None,
) -> None:
    expected_retrieval = set(checkpoint.expected_retrieval_ids)
    if contract.selected_memory_policy == MemoryEvolutionSelectedMemoryPolicy.CURRENT_TRUTH:
        if selected and not selected.issubset(checkpoint_active):
            failure_buckets.append(MemoryEvolutionFailureBucket.QUERY_LIFECYCLE_CONFLATION)
        if expected_retrieval and not expected_retrieval.issubset(checkpoint_active):
            failure_buckets.append(MemoryEvolutionFailureBucket.CHECKPOINT_ACTIVE_RECORD_MISSING_FROM_LIFECYCLE_SNAPSHOT)
        return
    if contract.selected_memory_policy == MemoryEvolutionSelectedMemoryPolicy.HISTORICAL_TRUTH:
        if expected_retrieval and not expected_retrieval.issubset(selected | query_historical):
            failure_buckets.append(MemoryEvolutionFailureBucket.HISTORICAL_MEMORY_NOT_MARKED_QUERY_RELEVANT)
        expected_non_checkpoint_active = set(checkpoint.expected_checkpoint_superseded_record_ids) | set(checkpoint.expected_checkpoint_retained_record_ids)
        if expected_retrieval & expected_non_checkpoint_active & checkpoint_active:
            failure_buckets.append(MemoryEvolutionFailureBucket.QUERY_LIFECYCLE_CONFLATION)
        return
    if contract.selected_memory_policy == MemoryEvolutionSelectedMemoryPolicy.ACTIVE_EXECUTION_STATE:
        if execution is None:
            failure_buckets.append(MemoryEvolutionFailureBucket.ACTIVE_EXECUTION_STATE_MISSING)
            return
        active_execution = set(execution.selected_action_memory_ids) | set(execution.active_work_state_memory_ids)
        if not expected_retrieval & active_execution:
            failure_buckets.append(MemoryEvolutionFailureBucket.ACTIVE_EXECUTION_STATE_MISSING)
        return
    if (
        contract.selected_memory_policy == MemoryEvolutionSelectedMemoryPolicy.BELIEF_ORDER
        and checkpoint.expected_belief_ranking
        and not set(checkpoint.expected_belief_ranking).intersection(selected_ids)
    ):
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_RETRIEVAL_MISSING)


def _lifecycle_expectation_scope(checkpoint: MemoryEvolutionCheckpoint) -> str:
    if any(
        (
            checkpoint.expected_full_checkpoint_active_record_ids,
            checkpoint.expected_full_checkpoint_superseded_record_ids,
            checkpoint.expected_full_checkpoint_retained_record_ids,
        )
    ):
        return "full_graph"
    return "query_relevant"


def _lifecycle_expected_ids(
    *,
    checkpoint: MemoryEvolutionCheckpoint,
    lifecycle_kind: str,
) -> list[str]:
    full_ids = {
        "active": checkpoint.expected_full_checkpoint_active_record_ids,
        "superseded": checkpoint.expected_full_checkpoint_superseded_record_ids,
        "retained": checkpoint.expected_full_checkpoint_retained_record_ids,
    }[lifecycle_kind]
    if full_ids:
        return list(full_ids)
    return {
        "active": checkpoint.expected_checkpoint_active_record_ids,
        "superseded": checkpoint.expected_checkpoint_superseded_record_ids,
        "retained": checkpoint.expected_checkpoint_retained_record_ids,
    }[lifecycle_kind]


def _belief_state_mismatch_ids(
    *,
    checkpoint: MemoryEvolutionCheckpoint,
    score_by_id: dict[str, float],
    belief_state_by_id: dict[str, MemoryEvolutionBeliefState | None],
) -> tuple[list[str], list[str]]:
    mismatch_ids: list[str] = []
    missing_required_score_ids: list[str] = []
    for expectation in checkpoint.expected_belief_states:
        memory_id = expectation.memory_id
        actual_score = score_by_id.get(memory_id)
        if expectation.score_required and actual_score is None:
            missing_required_score_ids.append(memory_id)
            continue
        if actual_score is not None:
            if expectation.min_score is not None and actual_score < expectation.min_score:
                mismatch_ids.append(memory_id)
            if expectation.max_score is not None and actual_score > expectation.max_score:
                mismatch_ids.append(memory_id)
        actual_state = belief_state_by_id.get(memory_id)
        actual_state_value = actual_state.value if actual_state is not None else None
        if actual_state_value != expectation.expected_state.value:
            mismatch_ids.append(memory_id)
    return _dedupe_string_ids(mismatch_ids), _dedupe_string_ids(missing_required_score_ids)


def _expected_belief_ids(checkpoint: MemoryEvolutionCheckpoint) -> list[str]:
    return _dedupe_string_ids(
        [
            *checkpoint.expected_belief_ranking,
            *checkpoint.expected_belief_scores.keys(),
            *(expectation.memory_id for expectation in checkpoint.expected_belief_states),
        ]
    )


def _expected_rejected_memory_ids(
    *,
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> list[str]:
    rejected_candidates = [
        *checkpoint.expected_excluded_memory_ids,
        *checkpoint.expected_checkpoint_superseded_record_ids,
    ]
    if contract.answer_temporal_mode == MemoryEvolutionAnswerTemporalMode.HISTORICAL:
        historical_answer_ids = set(checkpoint.expected_retrieval_ids)
        rejected_candidates = [
            memory_id
            for memory_id in rejected_candidates
            if memory_id not in historical_answer_ids
        ]
    return _dedupe_string_ids(rejected_candidates)


def _extra_direct_citations_are_warning_only(
    *,
    extra_citation_ids: list[str],
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> bool:
    if contract.citation_policy != MemoryEvolutionCitationPolicy.DIRECT_WITH_CONTEXT_WARNING:
        return False
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.EXECUTION_CONTINUATION:
        return True
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        return all(_is_belief_memory_id(memory_id, checkpoint=checkpoint) for memory_id in extra_citation_ids)
    excluded = set(checkpoint.expected_excluded_memory_ids)
    allowed_context = set(checkpoint.expected_context_citation_ids)
    return bool(allowed_context) and all(
        memory_id in allowed_context and memory_id not in excluded for memory_id in extra_citation_ids
    )


def _requires_answer_text(contract: MemoryEvolutionCheckpointContract) -> bool:
    return contract.answer_projection_policy not in {
        MemoryEvolutionAnswerProjectionPolicy.GRAPH_CHANNELS_ONLY,
        MemoryEvolutionAnswerProjectionPolicy.NONE,
    }


def _next_action_matches_expected(
    *,
    actual: str | None,
    expected: str,
    checkpoint: MemoryEvolutionCheckpoint,
    scenario: MemoryEvolutionScenario,
    parsed: MemoryEvolutionDecision,
    contract: MemoryEvolutionCheckpointContract,
) -> bool:
    if contract.next_action_policy == MemoryEvolutionNextActionPolicy.NONEMPTY_STRUCTURED:
        if not _norm(actual):
            return False
        if parsed.execution_selection is None:
            return False
        expected_active = set(checkpoint.expected_checkpoint_active_record_ids) | set(checkpoint.expected_retrieval_ids)
        selected_state = (
            set(parsed.execution_selection.selected_action_memory_ids)
            | set(parsed.execution_selection.active_work_state_memory_ids)
            | set(parsed.answer_selection.selected_memory_ids)
            | set(parsed.answer_selection.supporting_memory_ids)
        )
        command_context = set(parsed.execution_selection.command_context_memory_ids)
        if command_context & selected_state & set(_command_context_ids(scenario=scenario, checkpoint=checkpoint)):
            return False
        return bool(expected_active & selected_state)
    action = _norm(actual)
    return all(token in action.split() for token in _norm(expected).split())

def _dedupe_string_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def memory_evolution_trace_for_rule(
    *,
    context: MemoryEvolutionDecisionContext,
    decision: MemoryEvolutionDecision,
    mode: str,
) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=f"trace:{uuid4().hex}",
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
        mode=LLMDecisionMode(mode),
        input_payload=context.model_dump(mode="json"),
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )


def memory_evolution_engine_result_from_llm(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    rule_output: dict[str, object],
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_output, trace, False, result.failure_mode or "llm_decision_failed"
    try:
        decision = MemoryEvolutionDecision.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    output = decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
        mode=mode,
        result=result,
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return output, trace, True, None


def fake_llm_result_for_memory_evolution(
    *,
    request: LLMStructuredRequest,
    decision: MemoryEvolutionDecision,
    provider_name: str = "fake",
) -> LLMDecisionResult:
    output = decision.model_dump(mode="json")
    response = LLMStructuredResponse(
        request_id=request.request_id,
        provider=provider_name,
        raw_text=json.dumps(output, sort_keys=True),
        parsed_json=output,
        valid_json=True,
        schema_valid=True,
    )
    return LLMDecisionResult(
        request=request,
        response=response,
        output=output,
        success=True,
        failure_mode=None,
    )


def _expected_temporal_frame(
    *,
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> MemoryEvolutionTemporalFrame:
    if checkpoint.expected_temporal_frame is not None:
        return checkpoint.expected_temporal_frame
    mode_by_answer_mode = {
        MemoryEvolutionAnswerTemporalMode.CURRENT: MemoryEvolutionTemporalKind.CURRENT,
        MemoryEvolutionAnswerTemporalMode.HISTORICAL: MemoryEvolutionTemporalKind.HISTORICAL,
        MemoryEvolutionAnswerTemporalMode.EXECUTION: MemoryEvolutionTemporalKind.EXECUTION,
        MemoryEvolutionAnswerTemporalMode.BELIEF: MemoryEvolutionTemporalKind.BELIEF,
    }
    return MemoryEvolutionTemporalFrame(
        temporal_kind=mode_by_answer_mode[contract.answer_temporal_mode],
        scope_kind=MemoryEvolutionScopeKind.NONE,
        scope_key=None,
        anchor_id=None,
        valid_from=None,
        valid_to=None,
        confidence=1.0,
        rationale="Derived from the authored checkpoint contract.",
    )


def _temporal_frame_diagnostics(
    *,
    expected: MemoryEvolutionTemporalFrame,
    actual: MemoryEvolutionTemporalFrame,
    contract: MemoryEvolutionCheckpointContract,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> dict[str, bool]:
    kind_mismatch = actual.temporal_kind != expected.temporal_kind
    scope_kind_mismatch, scope_key_mismatch = _temporal_scope_mismatches(
        expected=expected,
        actual=actual,
        contract=contract,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    anchor_mismatch = expected.anchor_id is not None and actual.anchor_id != expected.anchor_id
    extra_anchor = (
        expected.anchor_id is None
        and actual.anchor_id is not None
        and not contract.allow_extra_temporal_anchor
    )
    expected_has_interval = expected.valid_from is not None or expected.valid_to is not None
    actual_has_interval = actual.valid_from is not None or actual.valid_to is not None
    interval_mismatch = (
        (expected.valid_from is not None and actual.valid_from != expected.valid_from)
        or (expected.valid_to is not None and actual.valid_to != expected.valid_to)
    )
    extra_interval = (
        actual_has_interval
        and not expected_has_interval
        and not _extra_interval_is_allowed(contract=contract)
    )
    under_specified = expected_has_interval and not actual_has_interval
    if contract.temporal_interval_policy == MemoryEvolutionTemporalIntervalPolicy.REQUIRE_START_AND_END:
        under_specified = expected.valid_from is not None and actual.valid_from is None
        under_specified = under_specified or (expected.valid_to is not None and actual.valid_to is None)
    temporal_frame_warning = (
        (actual_has_interval and not expected_has_interval and _extra_interval_is_allowed(contract=contract))
        or (
            expected.anchor_id is None
            and actual.anchor_id is not None
            and contract.allow_extra_temporal_anchor
        )
    )
    return {
        "temporal_kind_mismatch": kind_mismatch,
        "temporal_scope_mismatch": scope_kind_mismatch,
        "temporal_anchor_mismatch": anchor_mismatch,
        "temporal_interval_mismatch": interval_mismatch,
        "temporal_frame_under_specified": under_specified,
        "temporal_scope_key_mismatch": scope_key_mismatch,
        "temporal_extra_anchor": extra_anchor,
        "temporal_extra_interval": extra_interval,
        "temporal_frame_warning": temporal_frame_warning,
    }


def _extra_interval_is_allowed(*, contract: MemoryEvolutionCheckpointContract) -> bool:
    return contract.allow_extra_temporal_bounds or contract.temporal_interval_policy in {
        MemoryEvolutionTemporalIntervalPolicy.ALLOW_CHECKPOINT_BOUNDS,
        MemoryEvolutionTemporalIntervalPolicy.ALLOW_EXTRA_BOUNDS,
    }


def _temporal_scope_mismatches(
    *,
    expected: MemoryEvolutionTemporalFrame,
    actual: MemoryEvolutionTemporalFrame,
    contract: MemoryEvolutionCheckpointContract,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> tuple[bool, bool]:
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.KIND_ONLY:
        return actual.scope_kind != expected.scope_kind, False
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.NONE_OR_GLOBAL:
        return actual.scope_kind not in {
            MemoryEvolutionScopeKind.NONE,
            MemoryEvolutionScopeKind.GLOBAL,
        }, False
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.NONE_OR_ENTITY:
        scope_kind_mismatch = actual.scope_kind not in {
            MemoryEvolutionScopeKind.NONE,
            MemoryEvolutionScopeKind.ENTITY,
        }
        scope_key_mismatch = (
            actual.scope_kind == MemoryEvolutionScopeKind.ENTITY
            and expected.scope_key is not None
            and not _scope_keys_equivalent(
                expected_key=expected.scope_key,
                actual_key=actual.scope_key,
                kind=MemoryEvolutionScopeKind.ENTITY,
                scenario=scenario,
                checkpoint=checkpoint,
                contract=contract,
            )
        )
        return scope_kind_mismatch, scope_key_mismatch
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.NONE_OR_TASK:
        scope_kind_mismatch = actual.scope_kind not in {
            MemoryEvolutionScopeKind.NONE,
            MemoryEvolutionScopeKind.TASK,
        }
        scope_key_mismatch = (
            actual.scope_kind == MemoryEvolutionScopeKind.TASK
            and expected.scope_key is not None
            and not _scope_keys_equivalent(
                expected_key=expected.scope_key,
                actual_key=actual.scope_key,
                kind=MemoryEvolutionScopeKind.TASK,
                scenario=scenario,
                checkpoint=checkpoint,
                contract=contract,
            )
        )
        return scope_kind_mismatch, scope_key_mismatch
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.NONE_GLOBAL_OR_ENTITY:
        scope_kind_mismatch = actual.scope_kind not in {
            MemoryEvolutionScopeKind.NONE,
            MemoryEvolutionScopeKind.GLOBAL,
            MemoryEvolutionScopeKind.ENTITY,
        }
        scope_key_mismatch = (
            actual.scope_kind == MemoryEvolutionScopeKind.ENTITY
            and expected.scope_key is not None
            and not _scope_keys_equivalent(
                expected_key=expected.scope_key,
                actual_key=actual.scope_key,
                kind=MemoryEvolutionScopeKind.ENTITY,
                scenario=scenario,
                checkpoint=checkpoint,
                contract=contract,
            )
        )
        return scope_kind_mismatch, scope_key_mismatch
    return (
        actual.scope_kind != expected.scope_kind,
        expected.scope_key is not None
        and not _scope_keys_equivalent(
            expected_key=expected.scope_key,
            actual_key=actual.scope_key,
            kind=actual.scope_kind,
            scenario=scenario,
            checkpoint=checkpoint,
            contract=contract,
        ),
    )


def _scope_keys_equivalent(
    *,
    expected_key: str | None,
    actual_key: str | None,
    kind: MemoryEvolutionScopeKind,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> bool:
    if contract.scope_key_policy == MemoryEvolutionScopeKeyPolicy.KIND_ONLY:
        return True
    if expected_key == actual_key:
        return True
    if actual_key is None:
        return contract.scope_key_policy == MemoryEvolutionScopeKeyPolicy.NONE_ALLOWED
    if contract.scope_key_policy != MemoryEvolutionScopeKeyPolicy.CANONICAL_ALIAS:
        return False
    expected_canonical = _canonical_scope_key(
        raw_key=expected_key,
        kind=kind,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    actual_canonical = _canonical_scope_key(
        raw_key=actual_key,
        kind=kind,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    return expected_canonical is not None and expected_canonical == actual_canonical


def _canonical_scope_key(
    *,
    raw_key: str | None,
    kind: MemoryEvolutionScopeKind,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> str | None:
    if raw_key is None:
        return None
    normalized = _normalize_scope_key(raw_key)
    aliases = _scope_aliases_by_canonical_key(
        kind=kind,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    for canonical, values in aliases.items():
        if normalized in values:
            return canonical
    return normalized


def _scope_aliases_by_canonical_key(
    *,
    kind: MemoryEvolutionScopeKind,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    relevant_ids = {
        *checkpoint.expected_retrieval_ids,
        *checkpoint.expected_citation_ids,
        *checkpoint.expected_context_citation_ids,
        *checkpoint.expected_excluded_memory_ids,
        *checkpoint.expected_checkpoint_active_record_ids,
        *checkpoint.expected_checkpoint_superseded_record_ids,
        *checkpoint.expected_checkpoint_retained_record_ids,
        *checkpoint.expected_belief_ranking,
        *checkpoint.expected_belief_scores.keys(),
    }
    for event in scenario.events:
        if relevant_ids and event.event_id not in relevant_ids:
            continue
        if kind == MemoryEvolutionScopeKind.TASK and event.task_id:
            canonical = _normalize_scope_key(event.task_id)
            aliases.setdefault(canonical, set()).update(
                _scope_key_aliases(event.task_id)
            )
        if kind == MemoryEvolutionScopeKind.ENTITY:
            for entity_id in event.entity_ids:
                canonical = _normalize_scope_key(entity_id)
                aliases.setdefault(canonical, set()).update(
                    _scope_key_aliases(entity_id)
                )
    return aliases


def _scope_key_aliases(value: str) -> set[str]:
    normalized = _normalize_scope_key(value)
    aliases = {normalized}
    if ":" in normalized:
        aliases.add(normalized.split(":", 1)[1])
    aliases.add(normalized.replace("-", " "))
    aliases.add(normalized.replace("_", " "))
    return aliases


def _normalize_scope_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).replace("_", "-")


def _record_lifecycle_content_state_conflation_ids(
    *,
    scenario: MemoryEvolutionScenario,
    missing_checkpoint_active_ids: list[str],
    checkpoint_superseded: set[str],
    checkpoint_retained: set[str],
) -> list[str]:
    misplaced = set(missing_checkpoint_active_ids) & (checkpoint_superseded | checkpoint_retained)
    if not misplaced:
        return []
    event_by_id = {event.event_id: event for event in scenario.events}
    return [
        memory_id
        for memory_id in missing_checkpoint_active_ids
        if memory_id in misplaced and _content_uses_domain_lifecycle_word(event_by_id.get(memory_id))
    ]


def _content_uses_domain_lifecycle_word(event: MemoryEvolutionEvent | None) -> bool:
    if event is None:
        return False
    lifecycle_like_terms = {
        "abandoned",
        "archived",
        "closed",
        "deprecated",
        "done",
        "expired",
        "inactive",
        "retired",
    }
    return bool(set(_norm(event.content).split()) & lifecycle_like_terms)



def _visible_events_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> list[MemoryEvolutionEvent]:
    return [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]


def _visible_memory_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionVisibleMemoryCard]:
    return [
        MemoryEvolutionVisibleMemoryCard(
            memory_id=event.event_id,
            memory_kind=_memory_kind_for_event(event),
            statement=event.content,
            timestamp=event.timestamp,
            source_type=event.source_type,
            trust_level=event.trust_level,
            entity_ids=list(event.entity_ids),
            task_id=event.task_id,
            scope=event.scope,
            event_role=event.event_role,
            language=event.language,
            script=event.script,
        )
        for event in events
    ]


def _entity_resolution_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionEntityResolutionCard]:
    evidence_by_entity: dict[str, list[str]] = {}
    for event in events:
        for entity_id in event.entity_ids:
            evidence_by_entity.setdefault(entity_id, []).append(event.event_id)
    return [
        MemoryEvolutionEntityResolutionCard(
            entity_id=entity_id,
            canonical_name=_canonical_name_from_id(entity_id),
            evidence_memory_ids=_dedupe_string_ids(evidence_ids),
        )
        for entity_id, evidence_ids in sorted(evidence_by_entity.items())
    ]


def _temporal_anchor_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionTemporalAnchorCard]:
    anchors: dict[str, dict[str, object]] = {}
    for event in events:
        for anchor_id in event.temporal_anchor_ids:
            anchor = anchors.setdefault(
                anchor_id,
                {
                    "aliases": [],
                    "valid_from": event.valid_from,
                    "valid_to": event.valid_to,
                    "source_memory_ids": [],
                },
            )
            aliases = anchor["aliases"]
            if isinstance(aliases, list):
                aliases.extend(event.temporal_anchor_aliases)
            sources = anchor["source_memory_ids"]
            if isinstance(sources, list):
                sources.append(event.event_id)
            if event.valid_from is not None:
                current = anchor["valid_from"]
                anchor["valid_from"] = event.valid_from if current is None else min(current, event.valid_from)  # type: ignore[arg-type]
            if event.valid_to is not None:
                current = anchor["valid_to"]
                anchor["valid_to"] = event.valid_to if current is None else max(current, event.valid_to)  # type: ignore[arg-type]
    return [
        MemoryEvolutionTemporalAnchorCard(
            anchor_id=anchor_id,
            aliases=_dedupe_string_ids([str(alias) for alias in values["aliases"]]),
            valid_from=values["valid_from"] if isinstance(values["valid_from"], datetime) else None,
            valid_to=values["valid_to"] if isinstance(values["valid_to"], datetime) else None,
            source_memory_ids=_dedupe_string_ids([str(memory_id) for memory_id in values["source_memory_ids"]]),
        )
        for anchor_id, values in sorted(anchors.items())
    ]


def _entity_state_cards_for_events(
    *,
    events: list[MemoryEvolutionEvent],
    checkpoint: MemoryEvolutionCheckpoint,
) -> list[MemoryEvolutionEntityStateClaimCard]:
    state_events = [
        event
        for event in events
        if event.subject_entity_id is not None and event.predicate is not None and event.object_value is not None
    ]
    return [
        MemoryEvolutionEntityStateClaimCard(
            memory_id=event.event_id,
            entity_id=event.subject_entity_id or "",
            predicate=event.predicate or "",
            value=event.object_value or "",
            valid_from=event.valid_from,
            valid_to=event.valid_to,
            observed_at=event.timestamp,
            temporal_anchor_ids=list(event.temporal_anchor_ids),
            record_lifecycle=_record_lifecycle_for_event(event=event, checkpoint=checkpoint, state_events=state_events),
            source_memory_ids=[event.event_id],
        )
        for event in state_events
    ]


def _record_lifecycle_for_event(
    *,
    event: MemoryEvolutionEvent,
    checkpoint: MemoryEvolutionCheckpoint,
    state_events: list[MemoryEvolutionEvent],
) -> MemoryEvolutionRecordLifecycleState:
    if event.event_role == MemoryEvolutionEventRole.ARCHIVED_STATE:
        return MemoryEvolutionRecordLifecycleState.CHECKPOINT_RETAINED
    if event.valid_to is not None and event.valid_to <= checkpoint.timestamp:
        return MemoryEvolutionRecordLifecycleState.CHECKPOINT_SUPERSEDED
    newer_same_slot = [
        candidate
        for candidate in state_events
        if candidate.event_id != event.event_id
        and candidate.subject_entity_id == event.subject_entity_id
        and candidate.predicate == event.predicate
        and candidate.timestamp <= checkpoint.timestamp
        and candidate.timestamp > event.timestamp
    ]
    if newer_same_slot:
        return MemoryEvolutionRecordLifecycleState.CHECKPOINT_SUPERSEDED
    return MemoryEvolutionRecordLifecycleState.CHECKPOINT_ACTIVE


def _canonical_name_from_id(entity_id: str) -> str:
    return entity_id.replace("-", " ").replace("_", " ").strip().title()


def _memory_kind_for_event(event: MemoryEvolutionEvent) -> MemoryEvolutionMemoryKind:
    if event.event_id.startswith("belief:"):
        return MemoryEvolutionMemoryKind.BELIEF
    if event.event_id.startswith("evidence:"):
        return MemoryEvolutionMemoryKind.EVIDENCE
    if event.event_id.startswith("exec:"):
        return MemoryEvolutionMemoryKind.ACTION
    if event.event_id.startswith("mem:"):
        return MemoryEvolutionMemoryKind.FACT
    return MemoryEvolutionMemoryKind.UNKNOWN


def _evidence_effect_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionEvidenceEffectCard]:
    label_to_memory_id = _belief_label_map(events)
    cards: list[MemoryEvolutionEvidenceEffectCard] = []
    for event in events:
        supports = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["supports", "support", "confirms", "backs", "strengthens"],
        )
        supports.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["supported", "confirmed", "backed", "strengthened"],
            )
        )
        weakens = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["weakens", "weaken", "downgrades", "degrades", "undermines", "leaves", "makes", "renders"],
        )
        weakens.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["weakened", "downgraded", "degraded", "less likely", "weaker", "unsupported"],
            )
        )
        falsifies = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["falsifies", "falsify", "refutes", "disproves", "invalidates"],
        )
        falsifies.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["falsified", "refuted", "disproved", "invalidated", "ruled out"],
            )
        )
        dependencies = _dependency_ids_for_text(event.content, label_to_memory_id)
        supports = _dedupe_string_ids(supports)
        weakens = _dedupe_string_ids(weakens)
        falsifies = _dedupe_string_ids(falsifies)
        if not (supports or weakens or falsifies or dependencies):
            continue
        cards.append(
            MemoryEvolutionEvidenceEffectCard(
                evidence_memory_id=event.event_id,
                supports_memory_ids=supports,
                weakens_memory_ids=weakens,
                falsifies_memory_ids=falsifies,
                dependency_memory_ids=dependencies,
            )
        )
    return cards


def _belief_label_map(events: list[MemoryEvolutionEvent]) -> dict[str, str]:
    label_to_memory_id: dict[str, str] = {}
    for event in events:
        if not event.event_id.startswith("belief:"):
            continue
        for match in re.finditer(r"\b(?:hypothesis|belief)\s+([a-z])\b", event.content, flags=re.IGNORECASE):
            label_to_memory_id.setdefault(match.group(1).upper(), event.event_id)
        event_id_match = re.match(r"belief:([a-z])-", event.event_id, flags=re.IGNORECASE)
        if event_id_match is not None:
            label_to_memory_id.setdefault(event_id_match.group(1).upper(), event.event_id)
    return label_to_memory_id


def _effect_ids_for_verbs(content: str, label_to_memory_id: dict[str, str], verbs: list[str]) -> list[str]:
    ids: list[str] = []
    for verb in verbs:
        for match in re.finditer(rf"\b{re.escape(verb)}\s+([a-z])\b", content, flags=re.IGNORECASE):
            memory_id = label_to_memory_id.get(match.group(1).upper())
            if memory_id is not None:
                ids.append(memory_id)
    return _dedupe_string_ids(ids)


def _effect_ids_for_label_predicates(
    content: str,
    label_to_memory_id: dict[str, str],
    predicates: list[str],
) -> list[str]:
    ids: list[str] = []
    predicate_pattern = "|".join(re.escape(predicate) for predicate in predicates)
    for match in re.finditer(
        rf"\b([a-z])\b\s+(?:is|was|looks|seems|becomes|became)?\s*(?:now\s+)?(?:more\s+)?(?:{predicate_pattern})\b",
        content,
        flags=re.IGNORECASE,
    ):
        memory_id = label_to_memory_id.get(match.group(1).upper())
        if memory_id is not None:
            ids.append(memory_id)
    return _dedupe_string_ids(ids)


def _dependency_ids_for_text(content: str, label_to_memory_id: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for match in re.finditer(r"\bdepends\s+on\s+([a-z])\b", content, flags=re.IGNORECASE):
        memory_id = label_to_memory_id.get(match.group(1).upper())
        if memory_id is not None:
            ids.append(memory_id)
    return _dedupe_string_ids(ids)


def _belief_effect_order_errors(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    ranking: list[str],
) -> list[str]:
    if not checkpoint.expected_belief_ranking:
        return []
    visible_events = _visible_events_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    effect_cards = _evidence_effect_cards_for_events(visible_events)
    supported: set[str] = set()
    weakened: set[str] = set()
    falsified: set[str] = set()
    for card in effect_cards:
        supported.update(card.supports_memory_ids)
        weakened.update(card.weakens_memory_ids)
        falsified.update(card.falsifies_memory_ids)
    candidates = list(checkpoint.expected_belief_ranking)
    ranked_candidates = [memory_id for memory_id in ranking if memory_id in set(candidates)]
    rank_by_id = {memory_id: index for index, memory_id in enumerate(ranked_candidates)}
    neutral = [memory_id for memory_id in candidates if memory_id not in supported | weakened | falsified]
    errors: list[str] = []
    for weakened_id in sorted(weakened & set(candidates)):
        if weakened_id not in rank_by_id:
            continue
        for neutral_id in neutral:
            if neutral_id not in rank_by_id:
                continue
            if rank_by_id[weakened_id] < rank_by_id[neutral_id]:
                errors.append(f"{weakened_id}>{neutral_id}")
    return errors


def _belief_score_order_errors(*, ranking: list[str], score_by_id: dict[str, float]) -> list[str]:
    errors: list[str] = []
    for earlier_index, earlier_id in enumerate(ranking):
        earlier_score = score_by_id.get(earlier_id)
        if earlier_score is None:
            continue
        for later_id in ranking[earlier_index + 1 :]:
            later_score = score_by_id.get(later_id)
            if later_score is None:
                continue
            if earlier_score < later_score:
                errors.append(f"{later_id}>{earlier_id}")
    return errors


def _belief_ids_from_order_errors(errors: list[str]) -> list[str]:
    ids: list[str] = []
    for error in errors:
        ids.extend(part for part in error.split(">") if part)
    return _dedupe_string_ids(ids)


def _source_trust_losers_marked_active(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    checkpoint_active: set[str],
    selected: set[str],
) -> list[str]:
    excluded_superseded = (
        set(checkpoint.expected_excluded_memory_ids)
        & set(checkpoint.expected_checkpoint_superseded_record_ids)
        & checkpoint_active
    )
    if not excluded_superseded:
        return []
    event_by_id = {event.event_id: event for event in scenario.events}
    selected_trust = [
        event_by_id[memory_id].trust_level
        for memory_id in selected
        if memory_id in event_by_id
    ]
    if not selected_trust:
        return []
    winning_trust = max(selected_trust)
    return [
        memory_id
        for memory_id in sorted(excluded_superseded)
        if (event := event_by_id.get(memory_id)) is not None
        and event.trust_level < winning_trust
    ]


def _command_context_ids(*, scenario: MemoryEvolutionScenario, checkpoint: MemoryEvolutionCheckpoint) -> list[str]:
    return [
        event.event_id
        for event in scenario.events
        if event.timestamp <= checkpoint.timestamp
        and event.source_type == MemoryEvolutionSourceType.USER
        and event.event_role == MemoryEvolutionEventRole.COMMAND_CONTEXT
    ]


def _rank_events_by_shallow_overlap(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> list[MemoryEvolutionEvent]:
    query_tokens = set(_norm(checkpoint.query_or_task).split())
    eligible = [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]
    return sorted(
        eligible,
        key=lambda event: (
            -len(query_tokens & set(_norm(event.content).split())),
            -event.timestamp.timestamp(),
            event.event_id,
        ),
    )


def _extract_shallow_answer(content: str) -> str:
    for separator in [" is ", " = ", ":"]:
        if separator in content:
            return content.split(separator, 1)[1].strip().rstrip(".")
    return content.strip().rstrip(".")


def _norm(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())


def _ordered_missing(expected_ids: list[str], actual_ids: set[str]) -> list[str]:
    return [memory_id for memory_id in expected_ids if memory_id not in actual_ids]


def _ordered_extra(actual_ids: list[str], expected_ids: set[str]) -> list[str]:
    return [memory_id for memory_id in actual_ids if memory_id not in expected_ids]


def _is_belief_memory_id(memory_id: str, *, checkpoint: MemoryEvolutionCheckpoint) -> bool:
    return (
        memory_id.startswith("belief:")
        or memory_id in checkpoint.expected_belief_ranking
        or memory_id in checkpoint.expected_belief_scores
    )


def _dedupe_preserving_order(values: list[BucketT]) -> list[BucketT]:
    seen: set[BucketT] = set()
    result: list[BucketT] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _answer_matches_expected(*, actual: str | None, expected: str, aliases: list[str] | None = None) -> bool:
    actual_norm = _norm(actual)
    candidates = [expected, *(aliases or [])]
    for candidate in candidates:
        expected_norm = _norm(candidate)
        if actual_norm == expected_norm:
            return True
        actual_tokens = set(actual_norm.split())
        expected_tokens = set(expected_norm.split())
        if not expected_tokens:
            return True
        expected_negated = bool({"not", "never"} & expected_tokens)
        if expected_negated and not _contains_negation(actual_norm):
            continue
        if not expected_negated and _contains_local_negation(
            actual_norm=actual_norm,
            expected_tokens=expected_tokens,
        ):
            continue
        if expected_tokens.issubset(actual_tokens):
            return True
        if _answer_token_stems(expected_tokens).issubset(_answer_token_stems(actual_tokens)):
            return True
        if "no" in expected_tokens and ({"no", "none", "neither", "zero"} & actual_tokens):
            return (expected_tokens - {"no"}).issubset(actual_tokens)
    return False


def _contains_negation(text: str) -> bool:
    return bool({"not", "never"} & set(text.split()))


def _contains_local_negation(*, actual_norm: str, expected_tokens: set[str]) -> bool:
    """Reject a match only when negation is near a required concept.

    Explanatory answers can contain a separate negative fact, such as
    "Nikhil is not included in the active Atlas facts", after stating the
    positive answer. Document-wide negation detection incorrectly rejects
    those answers. A short token window still catches direct contradictions
    such as "Alice is not the owner".
    """
    tokens = actual_norm.split()
    required_tokens = expected_tokens - {"not", "never", "no"}
    for index, token in enumerate(tokens):
        if token not in required_tokens:
            continue
        window = tokens[max(0, index - 3) : index + 1]
        if {"not", "never"} & set(window):
            return True
    return False


def _answer_token_stems(tokens: set[str]) -> set[str]:
    stems: set[str] = set()
    for token in tokens:
        if len(token) > 5 and token.endswith("ing"):
            stems.add(token[:-3])
        elif len(token) > 4 and (token.endswith("ed") or token.endswith("es")):
            stems.add(token[:-2])
        elif len(token) > 3 and token.endswith("s"):
            stems.add(token[:-1])
        else:
            stems.add(token)
    return stems
