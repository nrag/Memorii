"""Promotion decision provider models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PromotionCandidateType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    USER_MEMORY = "user_memory"
    PROJECT_FACT = "project_fact"


class PromotionDecision(BaseModel):
    promote: bool
    target_plane: str | None = None
    confidence: float
    rationale: str
    merge_with_memory_id: str | None = None
    supersede_memory_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    trace_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class PromotionContext(BaseModel):
    candidate_id: str
    candidate_type: PromotionCandidateType
    content: str
    source_ids: list[str] = Field(default_factory=list)
    related_memory_ids: list[str] = Field(default_factory=list)
    repeated_across_episodes: int = 0
    explicit_user_memory_request: bool = False
    created_from: str
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
