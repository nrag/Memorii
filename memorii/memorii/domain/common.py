"""Shared schema components for Memorii domain models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.enums import CommitStatus, ConfidenceClass, SolverCreatedBy, SourceType

JSONValue = Any


class Provenance(BaseModel):
    source_type: SourceType
    source_refs: list[str] = Field(default_factory=list)
    created_at: datetime
    created_by: str

    model_config = ConfigDict(extra="forbid")


class RoutingInfo(BaseModel):
    primary_store: str
    secondary_stores: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SolverNodeMetadata(BaseModel):
    created_at: datetime
    created_by: SolverCreatedBy
    origin_perspective: str | None = None
    candidate_state: CommitStatus
    source_refs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SolverEdgeMetadata(BaseModel):
    created_at: datetime
    created_by: SolverCreatedBy
    origin_perspective: str | None = None
    candidate_state: CommitStatus
    confidence_class: ConfidenceClass
    source_refs: list[str] = Field(default_factory=list)
    assumption_refs: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
