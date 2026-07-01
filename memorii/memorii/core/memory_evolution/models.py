"""Typed runtime primitives for evolving memory from source observations."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.domain.enums import MemoryDomain, SourceType


class EntityType(str, Enum):
    PROJECT = "project"
    PERSON = "person"
    SERVICE = "service"
    TASK = "task"
    PREFERENCE = "preference"
    UNKNOWN = "unknown"


class ClaimValueType(str, Enum):
    TEXT = "text"
    ENTITY = "entity"
    BOOLEAN = "boolean"
    NUMBER = "number"
    DATE = "date"


class PredicateCardinality(str, Enum):
    SINGLE = "single"
    MULTI = "multi"


class PredicateConflictPolicy(str, Enum):
    SUPERSEDE_BY_TRUST_AND_TIME = "supersede_by_trust_and_time"
    ACCUMULATE = "accumulate"
    CONTRADICT = "contradict"


class PredicateMergePolicy(str, Enum):
    REINFORCE_SAME_VALUE = "reinforce_same_value"
    MERGE_UNIQUE_VALUES = "merge_unique_values"
    NO_MERGE = "no_merge"


class PredicateTemporalPolicy(str, Enum):
    CURRENT_VALUE = "current_value"
    HISTORICAL_EVENT = "historical_event"
    EXPIRING_VALUE = "expiring_value"


class ClaimLifecycleState(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class ClaimTransitionType(str, Enum):
    CREATE = "create"
    REINFORCE = "reinforce"
    MERGE = "merge"
    SUPERSEDE = "supersede"
    SPLIT = "split"
    INVALIDATE = "invalidate"
    EXPIRE = "expire"
    ARCHIVE = "archive"
    REOPEN = "reopen"


class ValidationVerdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class RetrievalView(str, Enum):
    CURRENT = "current"
    HISTORICAL_AT = "historical_at"
    ALL_VERSIONS = "all_versions"
    CONFLICTS = "conflicts"
    EVIDENCE_ONLY = "evidence_only"


class SourceObservation(BaseModel):
    source_id: str
    text: str
    source_type: SourceType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    domain: MemoryDomain = MemoryDomain.TRANSCRIPT
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None

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
    def validate_offsets(self) -> "EvidenceSpan":
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
    valid_from: datetime | None = None
    valid_to: datetime | None = None
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
    validation_results: dict[str, list[ValidationResult]] = Field(default_factory=dict)
    claim_states: list[ClaimState] = Field(default_factory=list)
    transitions: list[ClaimLifecycleTransition] = Field(default_factory=list)
    written_record_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
