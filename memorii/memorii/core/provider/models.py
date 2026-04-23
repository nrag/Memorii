"""Provider-facing normalized operation models and result contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.enums import MemoryDomain


class ProviderOperation(str, Enum):
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


class ProviderWriteKind(str, Enum):
    RAW_APPEND = "raw_append"
    CANDIDATE_STAGE = "candidate_stage"
    COMMIT = "commit"


class ProviderEvent(BaseModel):
    event_id: str
    operation: ProviderOperation
    content: str | None = None
    role: str | None = None
    target: str | None = None
    action: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    timestamp: datetime | None = None

    model_config = ConfigDict(extra="forbid")


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

    model_config = ConfigDict(extra="forbid")


class ProviderSyncResult(BaseModel):
    transcript_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    blocked_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_reasons: dict[str, str] = Field(default_factory=dict)
    allowed_candidate_domains: list[MemoryDomain] = Field(default_factory=list)
    raw_append_domains: list[MemoryDomain] = Field(default_factory=list)
    blocked_commit_domains: list[MemoryDomain] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ProviderQueryClass(str, Enum):
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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")
