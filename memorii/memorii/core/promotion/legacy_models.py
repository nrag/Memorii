"""Legacy promotion lifecycle models shared across deciders and executors."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import MemoryDomain


class PromotionAction(str, Enum):
    COMMIT = "commit"
    REJECT = "reject"
    KEEP_STAGED = "keep_staged"


class PromotionReasonCode(str, Enum):
    DUPLICATE_COMMITTED_MEMORY_EXISTS = "duplicate_committed_memory_exists"
    POSSIBLE_CONFLICT_WITH_COMMITTED_MEMORY = "possible_conflict_with_committed_memory"
    EPISODIC_CANDIDATE_TRUSTED_SOURCE = "episodic_candidate_trusted_source"
    EPISODIC_SOURCE_NOT_TRUSTED = "episodic_source_not_trusted"
    SEMANTIC_REQUIRES_EXPLICIT_MEMORY_WRITE = "semantic_requires_explicit_memory_write"
    SEMANTIC_EXPLICIT_WRITE_SAFE = "semantic_explicit_write_safe"
    USER_MEMORY_REQUIRES_EXPLICIT_MEMORY_WRITE_USER = "user_memory_requires_explicit_memory_write_user"
    USER_EXPLICIT_WRITE_SAFE = "user_explicit_write_safe"
    DOMAIN_NOT_AUTO_PROMOTED = "domain_not_auto_promoted"
    FAKE_DECIDER = "fake_decider"
    UNKNOWN = "unknown"


class LegacyPromotionDecision(BaseModel):
    action: PromotionAction
    target_domain: MemoryDomain
    reason_codes: list[PromotionReasonCode] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    duplicate_of_memory_id: str | None = None
    supersedes_memory_ids: list[str] = Field(default_factory=list)
    conflict_with_memory_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None
    decided_by: str

    model_config = ConfigDict(extra="forbid")


class LegacyPromotionContext(BaseModel):
    candidate: CanonicalMemoryRecord
    committed_in_scope: list[CanonicalMemoryRecord] = Field(default_factory=list)
    candidates_in_scope: list[CanonicalMemoryRecord] = Field(default_factory=list)
    same_domain_committed: list[CanonicalMemoryRecord] = Field(default_factory=list)
    same_domain_candidates: list[CanonicalMemoryRecord] = Field(default_factory=list)
    duplicates: list[CanonicalMemoryRecord] = Field(default_factory=list)
    possible_conflicts: list[CanonicalMemoryRecord] = Field(default_factory=list)
    scope_summary: str | None = None
    candidate_count_in_scope: int = 0
    committed_count_in_scope: int = 0
    same_domain_committed_count: int = 0
    same_domain_candidate_count: int = 0

    model_config = ConfigDict(extra="forbid")


class PromotionResult(BaseModel):
    candidate_id: str
    action: PromotionAction
    target_domain: MemoryDomain
    reason_codes: list[PromotionReasonCode] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    duplicate_of_memory_id: str | None = None
    supersedes_memory_ids: list[str] = Field(default_factory=list)
    conflict_with_memory_ids: list[str] = Field(default_factory=list)
    decided_by: str
    committed_memory_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class BatchPromotionResult(BaseModel):
    results: list[PromotionResult] = Field(default_factory=list)
    count_by_action: dict[PromotionAction, int] = Field(default_factory=dict)
    count_by_target_domain: dict[MemoryDomain, int] = Field(default_factory=dict)
    count_by_reason_code: dict[PromotionReasonCode, int] = Field(default_factory=dict)
    count_by_decider: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

# Backward-compatible aliases
PromotionDecision = LegacyPromotionDecision
PromotionContext = LegacyPromotionContext

