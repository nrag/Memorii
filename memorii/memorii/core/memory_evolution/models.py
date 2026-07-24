"""Typed runtime primitives for evolving memory from source observations."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.domain.enums import (
    ExtractionFailureCode,
    ExtractionRunStatus,
    FallbackOutcome,
    FinalExtractionSource,
    MemoryDomain,
    ProviderAttemptStatus,
    SourceModality,
    SourceType,
)


def _validate_optional_half_open_interval(
    valid_from: datetime | None,
    valid_to: datetime | None,
    label: str,
) -> None:
    for name, value in (("valid_from", valid_from), ("valid_to", valid_to)):
        if value is not None and value.tzinfo is None:
            raise ValueError(f"{label} {name} must be timezone-aware")
    if valid_from is not None and valid_to is not None and valid_from >= valid_to:
        raise ValueError(f"{label} valid_from must be before valid_to for a half-open interval")


class EntityType(StrEnum):
    PROJECT = "project"
    PERSON = "person"
    SERVICE = "service"
    TASK = "task"
    PREFERENCE = "preference"
    UNKNOWN = "unknown"


class ClaimValueType(StrEnum):
    TEXT = "text"
    ENTITY = "entity"
    BOOLEAN = "boolean"
    NUMBER = "number"
    DATE = "date"


class PredicateCardinality(StrEnum):
    SINGLE = "single"
    MULTI = "multi"


class PredicateConflictPolicy(StrEnum):
    SUPERSEDE_BY_TRUST_AND_TIME = "supersede_by_trust_and_time"
    ACCUMULATE = "accumulate"
    CONTRADICT = "contradict"


class PredicateMergePolicy(StrEnum):
    REINFORCE_SAME_VALUE = "reinforce_same_value"
    MERGE_UNIQUE_VALUES = "merge_unique_values"
    NO_MERGE = "no_merge"


class PredicateTemporalPolicy(StrEnum):
    CURRENT_VALUE = "current_value"
    HISTORICAL_EVENT = "historical_event"
    EXPIRING_VALUE = "expiring_value"


class ClaimLifecycleState(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class ClaimTransitionType(StrEnum):
    CREATE = "create"
    REINFORCE = "reinforce"
    MERGE = "merge"
    SUPERSEDE = "supersede"
    SPLIT = "split"
    INVALIDATE = "invalidate"
    EXPIRE = "expire"
    ARCHIVE = "archive"
    REOPEN = "reopen"
    ENTITY_MERGE = "entity_merge"
    ENTITY_SPLIT = "entity_split"
    ENTITY_RELINK = "entity_relink"
    CLAIM_REKEY = "claim_rekey"


class ExtractionTriggerMode(StrEnum):
    IMMEDIATE = "immediate"
    DEFERRED = "deferred"
    BATCH_ONLY = "batch_only"
    SKIP = "skip"


class EntityLinkLifecycleState(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    SPLIT = "split"
    RELINKED = "relinked"
    INVALIDATED = "invalidated"


class RecordLifecycleState(StrEnum):
    """Persistence lifecycle for graph records, independent of domain state."""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    MERGED = "merged"
    SPLIT = "split"
    RELINKED = "relinked"
    UNKNOWN = "unknown"


class EntityIdentityDecisionType(StrEnum):
    REUSE_EXISTING = "reuse_existing"
    CREATE_DISTINCT = "create_distinct"
    SPLIT_EXISTING = "split_existing"
    MERGE_EXISTING = "merge_existing"
    ABSTAIN = "abstain"


class ValidationVerdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class RetrievalView(StrEnum):
    CURRENT = "current"
    HISTORICAL_AT = "historical_at"
    ALL_VERSIONS = "all_versions"
    CONFLICTS = "conflicts"
    EVIDENCE_ONLY = "evidence_only"


class MemoryGraphNodeType(StrEnum):
    SOURCE_OBSERVATION = "source_observation"
    ENTITY = "entity"
    CLAIM = "claim"
    ACTION = "action"
    LITERAL = "literal"
    SCOPE = "scope"
    TASK = "task"
    CONTRADICTION_SET = "contradiction_set"
    REFERENCE_ENTITY = "reference_entity"
    REFERENCE_CLAIM = "reference_claim"


class MemoryGraphEdgeType(StrEnum):
    OBSERVED_IN = "observed_in"
    MENTIONS = "mentions"
    HAS_SUBJECT = "has_subject"
    HAS_OBJECT = "has_object"
    HAS_LITERAL_OBJECT = "has_literal_object"
    HAS_SCOPE = "has_scope"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    REINFORCES = "reinforces"
    CONFLICTS_WITH = "conflicts_with"
    ALIAS_OF = "alias_of"
    SAME_AS = "same_as"
    MERGED_INTO = "merged_into"
    SPLIT_FROM = "split_from"
    REKEYED_FROM = "rekeyed_from"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    MEMBER_OF_CONTRADICTION_SET = "member_of_contradiction_set"
    TYPED_AS = "typed_as"
    REFERENCE_SUPPORTS = "reference_supports"


class SourceObservation(BaseModel):
    source_id: str
    text: str
    source_type: SourceType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    domain: MemoryDomain = MemoryDomain.TRANSCRIPT
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    language: str = "en"
    modality: SourceModality = SourceModality.ASSERTION
    trigger_mode: ExtractionTriggerMode = ExtractionTriggerMode.IMMEDIATE

    model_config = ConfigDict(extra="forbid")


class MemoryScope(BaseModel):
    """Server-owned visibility boundary for memory records and query catalogs."""

    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @property
    def scope_key(self) -> str:
        """Return a display key; authorization must use the complete scope."""

        return self.task_id or self.session_id or self.user_id or "global"

    @property
    def identity(self) -> tuple[str | None, str | None, str | None]:
        return (self.user_id, self.session_id, self.task_id)

    def stable_id(self) -> str:
        return "|".join(value or "" for value in self.identity)

    @property
    def is_global(self) -> bool:
        return self.scope_key == "global"

    @property
    def specificity(self) -> int:
        """Return the visibility level, from global to task-local."""

        if self.task_id is not None:
            return 3
        if self.session_id is not None:
            return 2
        if self.user_id is not None:
            return 1
        return 0

    def can_read(self, candidate: MemoryScope) -> bool:
        if candidate.is_global:
            return True
        if self.is_global:
            return False
        if candidate.user_id is not None and self.user_id != candidate.user_id:
            return False
        if candidate.session_id is not None and self.session_id != candidate.session_id:
            return False
        return candidate.task_id is None or self.task_id == candidate.task_id


def memory_scope_from_observation(observation: SourceObservation) -> MemoryScope:
    return MemoryScope(
        task_id=observation.task_id,
        session_id=observation.session_id,
        user_id=observation.user_id,
    )


class EvidenceSpan(BaseModel):
    source_id: str
    quote: str
    char_start: int | None = None
    char_end: int | None = None
    source_type: SourceType
    timestamp: datetime

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_offsets(self) -> EvidenceSpan:
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be provided together")
        if self.char_start is not None and self.char_end is not None and self.char_start > self.char_end:
            raise ValueError("char_start must be <= char_end")
        return self


class ConfidenceComponents(BaseModel):
    extraction: float = Field(ge=0.0, le=1.0)
    evidence: float = Field(ge=0.0, le=1.0)
    source_trust: float = Field(ge=0.0, le=1.0)
    agreement: float = Field(default=0.0, ge=0.0, le=1.0)
    contradiction: float = Field(default=0.0, ge=0.0, le=1.0)
    calibrated: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class EntityMention(BaseModel):
    entity_id: str
    mention_text: str
    normalized_name: str
    aliases: list[str] = Field(default_factory=list)
    entity_type: EntityType = EntityType.UNKNOWN
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    scope: MemoryScope = Field(default_factory=MemoryScope)

    model_config = ConfigDict(extra="forbid")


class EntityLinkState(BaseModel):
    link_id: str
    mention_text: str
    canonical_entity_id: str
    normalized_name: str
    entity_type: EntityType = EntityType.UNKNOWN
    aliases: list[str] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    scope: MemoryScope = Field(default_factory=MemoryScope)
    lifecycle_state: EntityLinkLifecycleState = EntityLinkLifecycleState.ACTIVE
    superseded_by_entity_id: str | None = None
    lineage_parent_entity_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_interval(self) -> EntityLinkState:
        _validate_optional_half_open_interval(self.valid_from, self.valid_to, "entity link")
        return self


class ClaimKey(BaseModel):
    subject_entity_id: str
    predicate_id: str
    scope: MemoryScope = Field(default_factory=MemoryScope)
    qualifier_key: str = "default"

    model_config = ConfigDict(extra="forbid")

    def stable_id(self) -> str:
        return "|".join(
            [
                self.subject_entity_id,
                self.predicate_id,
                self.scope.stable_id(),
                self.qualifier_key,
            ]
        )

    @property
    def scope_key(self) -> str:
        return self.scope.scope_key


class ExtractedClaim(BaseModel):
    claim_id: str
    claim_key: ClaimKey
    object_value: str
    object_entity_id: str | None = None
    qualifiers: dict[str, str] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    confidence: ConfidenceComponents
    extraction_run_id: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_interval(self) -> ExtractedClaim:
        _validate_optional_half_open_interval(self.valid_from, self.valid_to, "claim")
        return self


class ExtractedAction(BaseModel):
    action_id: str
    actor_entity_id: str | None = None
    action_type: str
    target_entity_ids: list[str] = Field(default_factory=list)
    status: str
    dependency_entity_ids: list[str] = Field(default_factory=list)
    blocking_entity_ids: list[str] = Field(default_factory=list)
    timestamp: datetime
    scope: MemoryScope = Field(default_factory=MemoryScope)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    extraction_run_id: str

    model_config = ConfigDict(extra="forbid")

    @property
    def task_id(self) -> str | None:
        return self.scope.task_id

    @property
    def session_id(self) -> str | None:
        return self.scope.session_id

    @property
    def user_id(self) -> str | None:
        return self.scope.user_id

    @property
    def scope_key(self) -> str:
        return self.scope.scope_key


class ValidationResult(BaseModel):
    validator_name: str
    verdict: ValidationVerdict
    score: float = Field(ge=0.0, le=1.0)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    contradicted_claim_ids: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class ClaimState(BaseModel):
    claim_id: str
    claim_key: ClaimKey
    object_value: str
    lifecycle_state: ClaimLifecycleState
    source_claim_id: str
    confidence: ConfidenceComponents
    source_modality: SourceModality = SourceModality.ASSERTION
    validation_results: list[ValidationResult] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    supersedes_claim_ids: list[str] = Field(default_factory=list)
    superseded_by_claim_id: str | None = None
    conflict_with_claim_ids: list[str] = Field(default_factory=list)
    confidence_history: list[ConfidenceUpdate] = Field(default_factory=list)
    subject_link_id: str | None = None
    object_link_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_interval(self) -> ClaimState:
        _validate_optional_half_open_interval(self.valid_from, self.valid_to, "claim state")
        return self


class ConfidenceUpdate(BaseModel):
    update_id: str
    claim_id: str
    prior_confidence: float = Field(ge=0.0, le=1.0)
    new_confidence: float = Field(ge=0.0, le=1.0)
    evidence_delta: float = 0.0
    agreement_delta: float = 0.0
    contradiction_delta: float = 0.0
    source_trust_delta: float = 0.0
    modality: SourceModality
    rationale: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class ContradictionSet(BaseModel):
    contradiction_set_id: str
    predicate_id: str
    claim_key: ClaimKey
    active_claim_id: str | None = None
    conflicting_claim_ids: list[str] = Field(default_factory=list)
    rationale: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class ClaimLifecycleTransition(BaseModel):
    transition_id: str
    transition_type: ClaimTransitionType
    claim_id: str
    related_claim_ids: list[str] = Field(default_factory=list)
    rationale: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class EntityIdentityDecision(BaseModel):
    decision_id: str
    decision_type: EntityIdentityDecisionType
    mention_entity_id: str
    resolved_entity_id: str | None = None
    candidate_entity_ids: list[str] = Field(default_factory=list)
    parent_entity_id: str | None = None
    evidence_source_ids: list[str] = Field(default_factory=list)
    semantic_discriminators: list[str] = Field(default_factory=list)
    scope: MemoryScope = Field(default_factory=MemoryScope)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    failure_code: str | None = None

    model_config = ConfigDict(extra="forbid")


class EntityResolutionOutcome(BaseModel):
    decisions: list[EntityIdentityDecision] = Field(default_factory=list)
    links: list[EntityLinkState] = Field(default_factory=list)
    transitions: list[ClaimLifecycleTransition] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MemoryGraphNode(BaseModel):
    node_id: str
    node_type: MemoryGraphNodeType
    label: str
    canonical_id: str | None = None
    lifecycle_state: RecordLifecycleState
    confidence: float = Field(ge=0.0, le=1.0)
    source_record_ids: list[str] = Field(default_factory=list)
    payload_ref: str
    properties: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class MemoryGraphEdge(BaseModel):
    edge_id: str
    edge_type: MemoryGraphEdgeType
    source_node_id: str
    target_node_id: str
    directed: bool = True
    lifecycle_state: RecordLifecycleState
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_span_ids: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)
    properties: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class MemoryGraphSnapshot(BaseModel):
    snapshot_id: str
    nodes: list[MemoryGraphNode] = Field(default_factory=list)
    edges: list[MemoryGraphEdge] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_run_id: str | None = None
    validation_errors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ExtractionRun(BaseModel):
    extraction_run_id: str
    provider: str
    model: str | None = None
    prompt_hash: str | None = None
    input_source_ids: list[str]
    entity_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    validation_summary: dict[str, int] = Field(default_factory=dict)
    status: ExtractionRunStatus = ExtractionRunStatus.SUCCEEDED
    provider_attempt_status: ProviderAttemptStatus = ProviderAttemptStatus.NOT_ATTEMPTED
    fallback_outcome: FallbackOutcome = FallbackOutcome.NOT_USED
    final_output_source: FinalExtractionSource = FinalExtractionSource.PRIMARY
    failure_code: ExtractionFailureCode | None = None
    primary_failure_code: ExtractionFailureCode | None = None
    fallback_provider: str | None = None
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_outcome(self) -> ExtractionRun:
        if self.status == ExtractionRunStatus.SUCCEEDED:
            if self.failure_code is not None:
                raise ValueError("successful extraction cannot contain a terminal failure")
        elif self.status != ExtractionRunStatus.ABSTAINED and self.failure_code is None:
            raise ValueError("non-successful extraction requires a failure code")
        provider_failure_code = {
            ProviderAttemptStatus.PROVIDER_ERROR: ExtractionFailureCode.PROVIDER_ERROR,
            ProviderAttemptStatus.INVALID_JSON: ExtractionFailureCode.INVALID_JSON,
            ProviderAttemptStatus.SCHEMA_ERROR: ExtractionFailureCode.SCHEMA_VALIDATION,
        }.get(self.provider_attempt_status)
        if provider_failure_code is not None and self.primary_failure_code != provider_failure_code:
            raise ValueError("failed provider attempt requires its typed primary failure code")
        if self.provider_attempt_status in {
            ProviderAttemptStatus.NOT_ATTEMPTED,
            ProviderAttemptStatus.SUCCEEDED,
        } and self.primary_failure_code in {
            ExtractionFailureCode.PROVIDER_ERROR,
            ExtractionFailureCode.INVALID_JSON,
            ExtractionFailureCode.SCHEMA_VALIDATION,
        }:
            raise ValueError("successful or absent provider attempt cannot contain a provider failure")
        if self.fallback_outcome == FallbackOutcome.NOT_USED:
            if self.fallback_provider is not None or self.final_output_source == FinalExtractionSource.FALLBACK:
                raise ValueError("unused fallback cannot identify a fallback provider or output")
        else:
            if not self.fallback_provider:
                raise ValueError("fallback outcome requires a fallback provider")
            expected_source = (
                FinalExtractionSource.FALLBACK
                if self.fallback_outcome == FallbackOutcome.SUCCEEDED
                else FinalExtractionSource.NONE
            )
            if self.final_output_source != expected_source:
                raise ValueError("fallback outcome and final output source disagree")
        deterministic_abstention = (
            self.status == ExtractionRunStatus.ABSTAINED
            and self.provider_attempt_status == ProviderAttemptStatus.NOT_ATTEMPTED
            and self.fallback_outcome == FallbackOutcome.NOT_USED
            and self.failure_code is None
            and self.primary_failure_code is None
            and not self.entity_ids
            and not self.claim_ids
            and not self.action_ids
        )
        if self.final_output_source == FinalExtractionSource.NONE:
            if self.status != ExtractionRunStatus.FAILED and not deterministic_abstention:
                raise ValueError("missing extraction output requires failure or deterministic abstention")
        elif self.status == ExtractionRunStatus.FAILED:
            raise ValueError("failed extraction cannot identify a final output source")
        return self


class MemoryEvolutionResult(BaseModel):
    extraction_run: ExtractionRun
    entities: list[EntityMention] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    actions: list[ExtractedAction] = Field(default_factory=list)
    observations: list[SourceObservation] = Field(default_factory=list)
    entity_links: list[EntityLinkState] = Field(default_factory=list)
    entity_identity_decisions: list[EntityIdentityDecision] = Field(default_factory=list)
    contradiction_sets: list[ContradictionSet] = Field(default_factory=list)
    deferred_observation_ids: list[str] = Field(default_factory=list)
    skipped_observation_ids: list[str] = Field(default_factory=list)
    validation_results: dict[str, list[ValidationResult]] = Field(default_factory=dict)
    claim_states: list[ClaimState] = Field(default_factory=list)
    transitions: list[ClaimLifecycleTransition] = Field(default_factory=list)
    written_record_ids: list[str] = Field(default_factory=list)
    graph_nodes: list[MemoryGraphNode] = Field(default_factory=list)
    graph_edges: list[MemoryGraphEdge] = Field(default_factory=list)
    graph_snapshot_id: str | None = None
    graph_validation_errors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
