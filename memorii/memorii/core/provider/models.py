"""Provider-facing normalized operation models and result contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from memorii.domain.enums import (
    ExtractionFailureCode,
    ExtractionRunStatus,
    FallbackOutcome,
    FinalExtractionSource,
    MemoryDomain,
    ProviderAttemptStatus,
    SourceModality,
)

PrefetchDecisionT = TypeVar("PrefetchDecisionT", bound=BaseModel)
DeliveryId = Annotated[str, StringConstraints(min_length=1)]


class ProviderOperation(StrEnum):
    CHAT_USER_TURN = "chat_user_turn"
    CHAT_ASSISTANT_TURN = "chat_assistant_turn"
    MEMORY_WRITE_LONGTERM = "memory_write_longterm"
    MEMORY_WRITE_USER = "memory_write_user"
    MEMORY_WRITE_DAILYLOG = "memory_write_dailylog"
    SESSION_END = "session_end"
    PRE_COMPRESS = "pre_compress"
    DELEGATION_RESULT = "delegation_result"
    PREFETCH_QUERY = "prefetch_query"
    UNKNOWN = "unknown"


class ProviderWriteKind(StrEnum):
    RAW_APPEND = "raw_append"
    CANDIDATE_STAGE = "candidate_stage"
    COMMIT = "commit"


class ProviderEvolutionOutcome(BaseModel):
    operation_id: str
    status: Literal[
        "evolution_pending",
        "evolution_running",
        "evolution_committed",
        "evolution_failed",
    ]
    attempt_count: int = Field(ge=0)
    failure_code: str | None = None
    retryable: bool = False
    extraction_status: ExtractionRunStatus | None = None
    provider_attempt_status: ProviderAttemptStatus | None = None
    fallback_outcome: FallbackOutcome = FallbackOutcome.NOT_USED
    final_extraction_source: FinalExtractionSource | None = None
    extraction_failure_code: ExtractionFailureCode | None = None
    primary_failure_code: ExtractionFailureCode | None = None
    fallback_provider: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_outcome(self) -> ProviderEvolutionOutcome:
        committed = self.status == "evolution_committed"
        complete_extraction = self.extraction_status in {
            ExtractionRunStatus.SUCCEEDED,
            ExtractionRunStatus.ABSTAINED,
        }
        deterministic_abstention = (
            self.extraction_status == ExtractionRunStatus.ABSTAINED
            and self.provider_attempt_status == ProviderAttemptStatus.NOT_ATTEMPTED
            and self.fallback_outcome == FallbackOutcome.NOT_USED
            and self.final_extraction_source == FinalExtractionSource.NONE
            and self.extraction_failure_code is None
            and self.primary_failure_code is None
        )
        if committed and (
            not complete_extraction
            or self.final_extraction_source is None
            or (self.final_extraction_source == FinalExtractionSource.NONE and not deterministic_abstention)
        ):
            raise ValueError("committed outcome requires a usable extraction result")
        if self.fallback_outcome == FallbackOutcome.SUCCEEDED:
            if not self.fallback_provider or self.final_extraction_source != FinalExtractionSource.FALLBACK:
                raise ValueError("successful fallback requires fallback provenance")
        elif self.fallback_outcome == FallbackOutcome.FAILED:
            if not self.fallback_provider or self.final_extraction_source != FinalExtractionSource.NONE:
                raise ValueError("failed fallback requires terminal fallback provenance")
        elif self.fallback_provider is not None:
            raise ValueError("unused fallback cannot identify a fallback provider")
        if committed and self.failure_code is not None:
            raise ValueError("committed outcome cannot contain an operation failure")
        if self.status == "evolution_failed" and self.failure_code is None:
            raise ValueError("failed outcome requires a failure code")
        return self


class ProviderEvent(BaseModel):
    event_id: DeliveryId
    operation: ProviderOperation
    content: str | None = None
    role: str | None = None
    target: str | None = None
    action: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    language: str = "en"
    speaker_id: str | None = None
    timestamp: datetime | None = None
    source_modality: SourceModality | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        return normalize_delivery_id(value)


def normalize_delivery_id(value: str) -> str:
    """Forward to the owning ingestion contract without an import-time cycle."""

    from memorii.core.memory_evolution.ingestion_contracts import (
        is_reserved_composite_delivery_id,
    )
    from memorii.core.memory_evolution.ingestion_contracts import (
        normalize_delivery_id as normalize,
    )

    normalized = normalize(value)
    if is_reserved_composite_delivery_id(normalized):
        raise ValueError("public delivery ID cannot use a reserved composite coordinate")
    return normalized


class ProviderDomainPermission(BaseModel):
    operation: ProviderOperation
    allowed_raw_append_domains: list[MemoryDomain] = Field(default_factory=list)
    allowed_candidate_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_commit_domains: list[MemoryDomain] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ProviderPolicyDecision(BaseModel):
    operation: ProviderOperation
    allowed_raw_append_domains: list[MemoryDomain] = Field(default_factory=list)
    allowed_candidate_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_commit_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_reasons: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ProviderWriteDecision(BaseModel):
    blocked_domains: list[MemoryDomain] = Field(default_factory=list)
    allowed_candidate_domains: list[MemoryDomain] = Field(default_factory=list)
    committed_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_reasons: dict[str, str] = Field(default_factory=dict)
    candidate_ids: list[str] = Field(default_factory=list)
    raw_append_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_commit_domains: list[MemoryDomain] = Field(default_factory=list)
    evolution_outcomes: list[ProviderEvolutionOutcome] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ProviderSyncResult(BaseModel):
    transcript_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    blocked_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_reasons: dict[str, str] = Field(default_factory=dict)
    allowed_candidate_domains: list[MemoryDomain] = Field(default_factory=list)
    raw_append_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_commit_domains: list[MemoryDomain] = Field(default_factory=list)
    evolution_outcomes: list[ProviderEvolutionOutcome] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ProviderQueryClass(StrEnum):
    PREFERENCE_PROFILE = "preference_profile"
    FACT_CONFIG = "fact_config"
    EVENT_HISTORY = "event_history"
    GENERAL_CONTINUITY = "general_continuity"


class ProviderStoredRecord(BaseModel):
    memory_id: str
    domain: MemoryDomain
    text: str
    status: str
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    language: str = "en"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class ProviderRerankTraceItem(BaseModel):
    memory_id: str
    domain: MemoryDomain
    final_score: float
    domain_prior_score: float
    lexical_score: float
    recency_score: float
    scope_score: float
    rank: int

    model_config = ConfigDict(extra="forbid")


class ProviderPrefetchTrace(BaseModel):
    query: str
    query_class: ProviderQueryClass
    lexical_method: str = "bm25"
    candidate_count: int
    ranked_items: list[ProviderRerankTraceItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RetrievalChannelStatus(StrEnum):
    ANSWER = "answer"
    NO_MATCH = "no_match"
    ABSTAIN = "abstain"
    ERROR = "error"


class RetrievalChannelAuthority(StrEnum):
    AUTHORITATIVE = "authoritative"
    SUPPLEMENTAL = "supplemental"
    NONE = "none"


class RetrievalChannelResult(BaseModel):
    channel: Literal["canonical", "evolution"]
    status: RetrievalChannelStatus
    authority: RetrievalChannelAuthority
    context: str
    selected_record_ids: list[str] = Field(default_factory=list)
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class ProviderPrefetchResult(BaseModel, Generic[PrefetchDecisionT]):
    """Typed result of production retrieval composition and arbitration."""

    context: str
    selected_channel: Literal["canonical", "evolution", "none"]
    canonical: RetrievalChannelResult
    evolution: RetrievalChannelResult
    evolution_decision: PrefetchDecisionT | None = None

    model_config = ConfigDict(extra="forbid")
