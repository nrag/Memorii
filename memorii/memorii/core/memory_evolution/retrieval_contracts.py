"""Typed request, candidate, and decision contracts for memory retrieval."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.execution import ContinuationDecision, WorkStateSnapshot
from memorii.core.memory_evolution.models import ClaimLifecycleState, MemoryScope
from memorii.core.memory_evolution.query_graph import GraphPatternResolution
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryTemporalFrame,
    RetrievalDecision,
)


class RetrievalPurpose(StrEnum):
    ANSWER = "answer"
    GRAPH_AUDIT = "graph_audit"
    EXECUTION = "execution"


class SemanticFrameStatus(StrEnum):
    MATCHED = "matched"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class QueryRequestOptions(BaseModel):
    """Non-semantic retrieval options shared by public and resolved queries."""

    query_language: str = "en"
    reference_time: datetime | None = None
    scope: MemoryScope = Field(default_factory=MemoryScope)
    top_k: int = Field(default=8, ge=1, le=100)
    include_context: bool = True
    # Lifecycle arbitration always considers query-relevant versions.
    # This option controls disclosure of the broader conflict neighborhood,
    # not whether stale competitors can be classified as rejected.
    include_conflicts: bool = False
    purpose: RetrievalPurpose = RetrievalPurpose.ANSWER

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_reference_time(self) -> QueryRequestOptions:
        if self.reference_time is not None and self.reference_time.tzinfo is None:
            raise ValueError("reference_time must be timezone-aware")
        return self

    @property
    def scope_key(self) -> str:
        return self.scope.scope_key

    @property
    def task_id(self) -> str | None:
        return self.scope.task_id

    @property
    def session_id(self) -> str | None:
        return self.scope.session_id

    @property
    def user_id(self) -> str | None:
        return self.scope.user_id


class MemoryQueryRequest(QueryRequestOptions):
    query: str


class ResolvedMemoryQuery(QueryRequestOptions):
    query: str
    query_analysis: QueryAnalysis
    temporal_frame: QueryTemporalFrame
    subject_entity_id: str | None = None
    predicate_id: str | None = None
    graph_pattern_resolution: GraphPatternResolution | None = None
    scope_mode: Literal["scoped", "full"] = "scoped"


MemoryQueryInput = MemoryQueryRequest


class GraphAuditRequest(MemoryQueryRequest):
    scope_mode: Literal["scoped", "full"] = "scoped"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_purpose(self) -> GraphAuditRequest:
        if self.purpose != RetrievalPurpose.GRAPH_AUDIT:
            raise ValueError("GraphAuditRequest requires graph_audit purpose")
        return self


class RetrievalCandidate(BaseModel):
    claim_id: str
    score: float = Field(ge=0.0)
    score_semantics: Literal["ordinal"] = "ordinal"
    lexical_overlap: int = Field(ge=0)
    lifecycle_state: ClaimLifecycleState
    rationale: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ScopedExecutionView(BaseModel):
    work_state: WorkStateSnapshot
    continuation: ContinuationDecision
    readable_action_event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_continuation_visibility(self) -> ScopedExecutionView:
        selected_event_id = self.continuation.action_event_id
        if selected_event_id is not None and selected_event_id not in self.readable_action_event_ids:
            raise ValueError("continuation action event is outside the scoped execution view")
        visible_branch_ids = {state.branch_id for state in self.work_state.states}
        hidden_candidates = set(self.continuation.candidate_branch_ids) - visible_branch_ids
        if hidden_candidates:
            raise ValueError("continuation candidates are outside the scoped execution view")
        return self


class RetrievalEvidence(BaseModel):
    claim_id: str
    source_id: str
    quote: str

    model_config = ConfigDict(extra="forbid")


class RetrievalContextItem(BaseModel):
    claim_id: str
    channel: Literal["selected", "supporting", "context", "rejected"]
    lifecycle_state: ClaimLifecycleState
    subject_entity_id: str
    predicate_id: str
    scope_key: str

    model_config = ConfigDict(extra="forbid")


class ProductionRetrievalDecision(RetrievalDecision):
    query: str
    semantic_frame_status: SemanticFrameStatus
    query_analysis: QueryAnalysis | None = None
    graph_pattern_resolution: GraphPatternResolution | None = None
    resolution_status: str = "resolved"
    candidates: list[RetrievalCandidate] = Field(default_factory=list)
    decision_source: str = "production_memory_evolution_retriever"
    confidence_status: Literal["uncalibrated", "calibrated", "abstained"] = "uncalibrated"
    execution_state: ScopedExecutionView | None = None
    evidence: list[RetrievalEvidence] = Field(default_factory=list)
    context_items: list[RetrievalContextItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_execution_record_visibility(self) -> ProductionRetrievalDecision:
        if self.execution_state is None:
            return self
        readable_record_ids = {
            event_id.removeprefix("action:")
            for event_id in self.execution_state.readable_action_event_ids
        }
        disclosed_record_ids = {
            *self.selected_record_ids,
            *self.supporting_record_ids,
            *self.context_record_ids,
            *self.rejected_record_ids,
        }
        if disclosed_record_ids - readable_record_ids:
            raise ValueError("execution decision discloses records outside its scoped view")
        return self
