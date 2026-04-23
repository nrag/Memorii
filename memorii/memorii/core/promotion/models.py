"""Promotion lifecycle models shared across deciders and executors."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import MemoryDomain


class PromotionAction(str, Enum):
    COMMIT = "commit"
    REJECT = "reject"
    KEEP_STAGED = "keep_staged"


class PromotionDecision(BaseModel):
    action: PromotionAction
    target_domain: MemoryDomain
    reasons: list[str] = Field(default_factory=list)
    duplicate_of_memory_id: str | None = None
    supersedes_memory_ids: list[str] = Field(default_factory=list)
    conflict_with_memory_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None
    decided_by: str

    model_config = ConfigDict(extra="forbid")


class PromotionContext(BaseModel):
    candidate: CanonicalMemoryRecord
    committed_in_scope: list[CanonicalMemoryRecord] = Field(default_factory=list)
    candidates_in_scope: list[CanonicalMemoryRecord] = Field(default_factory=list)
    same_domain_committed: list[CanonicalMemoryRecord] = Field(default_factory=list)
    same_domain_candidates: list[CanonicalMemoryRecord] = Field(default_factory=list)
    duplicates: list[CanonicalMemoryRecord] = Field(default_factory=list)
    possible_conflicts: list[CanonicalMemoryRecord] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class PromotionResult(BaseModel):
    candidate_id: str
    action: PromotionAction
    target_domain: MemoryDomain
    reasons: list[str] = Field(default_factory=list)
    duplicate_of_memory_id: str | None = None
    supersedes_memory_ids: list[str] = Field(default_factory=list)
    conflict_with_memory_ids: list[str] = Field(default_factory=list)
    decided_by: str
    committed_memory_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class BatchPromotionResult(BaseModel):
    results: list[PromotionResult] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
