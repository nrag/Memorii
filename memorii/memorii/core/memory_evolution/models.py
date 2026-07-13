"""Typed runtime primitives for evolving memory from source observations."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.domain.enums import MemoryDomain, SourceType


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


class SourceModality(StrEnum):
    ASSERTION = "assertion"
    CORRECTION = "correction"
    QUOTED_OR_PASTED = "quoted_or_pasted"
    HYPOTHETICAL = "hypothetical"
    QUESTION = "question"
    INSTRUCTION = "instruction"
    TOOL_RESULT = "tool_result"
    ASSISTANT_CLAIM = "assistant_claim"
    THIRD_PARTY_CLAIM = "third_party_claim"
    NOISE = "noise"


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
    modality: SourceModality = SourceModality.ASSERTION
    trigger_mode: ExtractionTriggerMode = ExtractionTriggerMode.IMMEDIATE

    model_config = ConfigDict(extra="forbid")


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
    entity_type: EntityType = EntityType.UNKNOWN
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

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
    lifecycle_state: EntityLinkLifecycleState = EntityLinkLifecycleState.ACTIVE
    superseded_by_entity_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class ClaimKey(BaseModel):
    subject_entity_id: str
    predicate_id: str
    scope_key: str = "global"
    qualifier_key: str = "default"

    model_config = ConfigDict(extra="forbid")

    def stable_id(self) -> str:
        return "|".join(
            [
                self.subject_entity_id,
                self.predicate_id,
                self.scope_key,
                self.qualifier_key,
            ]
        )


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


class ExtractedAction(BaseModel):
    action_id: str
    actor_entity_id: str | None = None
    action_type: str
    target_entity_ids: list[str] = Field(default_factory=list)
    status: str
    dependency_ids: list[str] = Field(default_factory=list)
    blocking_ids: list[str] = Field(default_factory=list)
    timestamp: datetime
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    extraction_run_id: str

    model_config = ConfigDict(extra="forbid")


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


class MemoryGraphNode(BaseModel):
    node_id: str
    node_type: MemoryGraphNodeType
    label: str
    canonical_id: str | None = None
    lifecycle_state: str
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
    lifecycle_state: str
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
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionResult(BaseModel):
    extraction_run: ExtractionRun
    entities: list[EntityMention] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    actions: list[ExtractedAction] = Field(default_factory=list)
    observations: list[SourceObservation] = Field(default_factory=list)
    entity_links: list[EntityLinkState] = Field(default_factory=list)
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
