"""Production retrieval contracts for evolved memory.

The benchmark may compare a decision with an oracle, but it must not decide
which claims answer a query. This module is the production-owned boundary
between a query/temporal frame and lifecycle-aware claim selection.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.execution import ContinuationDecision, WorkStateSnapshot
from memorii.core.memory_evolution.models import ClaimLifecycleState, ClaimState, MemoryScope
from memorii.core.memory_evolution.query_graph import GraphPatternResolution, GraphPatternResolutionStatus
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryTemporalFrame,
    QueryTemporalKind,
    RetrievalDecision,
    TemporalResolution,
    evaluate_temporal_eligibility,
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
    """Natural-language request whose semantics are owned by the configured analyzer."""

    query: str


class ResolvedMemoryQuery(QueryRequestOptions):
    """Internal analyzer result consumed by deterministic retrieval policy."""

    query: str
    query_analysis: QueryAnalysis
    temporal_frame: QueryTemporalFrame
    subject_entity_id: str | None = None
    predicate_id: str | None = None
    graph_pattern_resolution: GraphPatternResolution | None = None
    scope_mode: Literal["scoped", "full"] = "scoped"


MemoryQueryInput = MemoryQueryRequest


class GraphAuditRequest(MemoryQueryRequest):
    """Explicit diagnostic request for graph-neighborhood reconstruction."""

    scope_mode: Literal["scoped", "full"] = "scoped"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_purpose(self) -> GraphAuditRequest:
        if self.purpose != RetrievalPurpose.GRAPH_AUDIT:
            raise ValueError("GraphAuditRequest requires graph_audit purpose")
        return self


class RetrievalCandidate(BaseModel):
    """A claim candidate with an inspectable ranking trace."""

    claim_id: str
    score: float = Field(ge=0.0)
    score_semantics: Literal["ordinal"] = "ordinal"
    lexical_overlap: int = Field(ge=0)
    lifecycle_state: ClaimLifecycleState
    rationale: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ScopedExecutionView(BaseModel):
    """Execution state derived exclusively from records readable by the request."""

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


class ProductionRetrievalDecision(RetrievalDecision):
    """Query-conditioned retrieval result exposed to provider and agents."""

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
            event_id.removeprefix("action:") for event_id in self.execution_state.readable_action_event_ids
        }
        disclosed_record_ids = {
            *self.selected_record_ids,
            *self.supporting_record_ids,
            *self.context_record_ids,
            *self.rejected_record_ids,
        }
        hidden_record_ids = disclosed_record_ids - readable_record_ids
        if hidden_record_ids:
            raise ValueError("execution decision discloses records outside its scoped view")
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


ProductionRetrievalDecision.model_rebuild()


def reconcile_memory_query(request: ResolvedMemoryQuery) -> TemporalResolution:
    """Reconcile validated semantic analysis with caller-owned request context."""

    analysis = request.query_analysis
    frame, status, rationale = _reconcile_request_frame(request, request.temporal_frame)
    return TemporalResolution(
        frame=frame,
        status=("ambiguous" if status != "resolved" or frame.ambiguity_reasons else "resolved"),
        rationale=rationale,
        language=analysis.language,
        analysis_source=analysis.analysis_source,
    )


def _reconcile_request_frame(
    request: ResolvedMemoryQuery,
    frame: QueryTemporalFrame,
) -> tuple[QueryTemporalFrame, Literal["resolved", "ambiguous"], str]:
    """Prevent caller context from silently broadening a supplied frame."""

    if request.scope_key is not None:
        if frame.scope_key is not None and frame.scope_key != request.scope_key:
            return (
                frame.model_copy(
                    update={
                        "temporal_kind": QueryTemporalKind.AMBIGUOUS,
                        "resolution_confidence": 0.0,
                        "ambiguity_reasons": ["request_frame_scope_mismatch"],
                    }
                ),
                "ambiguous",
                "request scope does not match the supplied temporal frame",
            )
        if frame.scope_key is None:
            frame = frame.with_scope(request.scope_key)
    if request.subject_entity_id is not None:
        if frame.resolved_entity_ids and request.subject_entity_id not in frame.resolved_entity_ids:
            return (
                frame.model_copy(
                    update={
                        "temporal_kind": QueryTemporalKind.AMBIGUOUS,
                        "resolution_confidence": 0.0,
                        "ambiguity_reasons": ["request_frame_entity_mismatch"],
                    }
                ),
                "ambiguous",
                "request entity does not match the supplied temporal frame",
            )
        if request.subject_entity_id not in frame.resolved_entity_ids:
            frame = frame.model_copy(
                update={"resolved_entity_ids": [*frame.resolved_entity_ids, request.subject_entity_id]}
            )
    if frame.temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        if frame.evaluation_time is not None and frame.evaluation_time != request.reference_time:
            return (
                frame.model_copy(
                    update={
                        "temporal_kind": QueryTemporalKind.AMBIGUOUS,
                        "resolution_confidence": 0.0,
                        "ambiguity_reasons": ["request_frame_evaluation_time_mismatch"],
                    }
                ),
                "ambiguous",
                "request reference time does not match the supplied temporal frame",
            )
        if frame.evaluation_time is None and request.reference_time is not None:
            frame = frame.model_copy(update={"evaluation_time": request.reference_time})
    if (
        frame.temporal_kind == QueryTemporalKind.AMBIGUOUS
        or frame.ambiguity_reasons
        or frame.resolution_confidence <= 0.0
    ):
        return frame, "ambiguous", "temporal frame is ambiguous or unresolved"
    return frame, "resolved", "request context and temporal frame are consistent"


def rank_claims(
    *,
    request: ResolvedMemoryQuery,
    frame: QueryTemporalFrame,
    resolution_status: str = "resolved",
    states: list[ClaimState],
    entity_names_by_id: dict[str, set[str]] | None = None,
    subject_entity_by_claim: dict[str, str] | None = None,
    object_entity_by_claim: dict[str, str] | None = None,
) -> ProductionRetrievalDecision:
    """Rank lifecycle-filtered claims without benchmark/oracle knowledge."""

    if (
        frame.temporal_kind == QueryTemporalKind.AMBIGUOUS
        or resolution_status != "resolved"
        or frame.ambiguity_reasons
        or frame.resolution_confidence <= 0.0
    ):
        graph_status = request.graph_pattern_resolution.status if request.graph_pattern_resolution is not None else None
        semantic_frame_status = (
            SemanticFrameStatus.MATCHED
            if graph_status == GraphPatternResolutionStatus.NO_MATCH and request.predicate_id is not None
            else SemanticFrameStatus.UNSUPPORTED
            if request.query_analysis.failure_code is not None
            or request.query_analysis.analysis_source in {"language_guard", "provider"}
            else SemanticFrameStatus.AMBIGUOUS
        )
        entity_ambiguity = any("entity" in reason for reason in frame.ambiguity_reasons)
        return ProductionRetrievalDecision(
            query=request.query,
            semantic_frame_status=semantic_frame_status,
            temporal_frame=frame,
            query_analysis=request.query_analysis,
            graph_pattern_resolution=request.graph_pattern_resolution,
            resolution_status=resolution_status,
            abstained=True,
            abstention_reason=(
                "graph_constraint_no_match"
                if graph_status is not None and graph_status.value == "no_match"
                else "graph_constraint_unsupported"
                if graph_status is not None and graph_status.value == "unsupported"
                else "entity_resolution_ambiguous"
                if entity_ambiguity
                else "temporal_frame_ambiguous"
                if frame.temporal_kind == QueryTemporalKind.AMBIGUOUS or frame.ambiguity_reasons
                else "entity_resolution_unresolved"
            ),
            confidence_status="abstained",
        )
    query_tokens = _tokens(request.query)
    selected: list[RetrievalCandidate] = []
    rejected: list[str] = []
    context: list[str] = []
    entity_names_by_id = entity_names_by_id or {}
    subject_entity_by_claim = subject_entity_by_claim or {}
    object_entity_by_claim = object_entity_by_claim or {}
    excluded_terms = _excluded_terms(request.query)
    graph_matched_claim_ids = (
        set(request.graph_pattern_resolution.matched_claim_ids)
        if request.graph_pattern_resolution is not None
        and request.graph_pattern_resolution.status.value == "resolved"
        and request.graph_pattern_resolution.matched_claim_ids
        else set()
    )
    # A graph audit asks for the resolved entity neighborhood. Inference of a
    # predicate from the wording would silently turn that audit into an
    # answer query and drop definition/rekey evidence. An explicit predicate
    # remains authoritative for callers that intentionally narrow the audit.
    effective_predicate_id = request.predicate_id if request.predicate_id is not None else None
    if request.predicate_id is None and request.purpose != RetrievalPurpose.GRAPH_AUDIT:
        eligible_predicates = {
            state.claim_key.predicate_id
            for state in states
            if (
                not request.subject_entity_id
                or subject_entity_by_claim.get(state.claim_id, state.claim_key.subject_entity_id)
                == request.subject_entity_id
            )
            and (
                not frame.resolved_entity_ids
                or subject_entity_by_claim.get(state.claim_id, state.claim_key.subject_entity_id)
                in frame.resolved_entity_ids
            )
            and request.scope.can_read(state.claim_key.scope)
            and _frame_matches(
                state,
                frame,
                resolved_subject=subject_entity_by_claim.get(state.claim_id),
                resolved_object=object_entity_by_claim.get(state.claim_id),
                request_scope=request.scope,
            )
        }
        if len(eligible_predicates) > 1 and effective_predicate_id not in eligible_predicates:
            return ProductionRetrievalDecision(
                query=request.query,
                semantic_frame_status=SemanticFrameStatus.AMBIGUOUS,
                temporal_frame=frame,
                query_analysis=request.query_analysis,
                graph_pattern_resolution=request.graph_pattern_resolution,
                resolution_status="ambiguous",
                abstained=True,
                abstention_reason="predicate_ambiguous",
                confidence_status="abstained",
            )
    selected_scope_specificity_by_claim: dict[tuple[str, str, str], int] = {}
    for state in states:
        if graph_matched_claim_ids and state.claim_id not in graph_matched_claim_ids:
            continue
        if (
            not request.scope.can_read(state.claim_key.scope)
            or (effective_predicate_id and state.claim_key.predicate_id != effective_predicate_id)
            or not _frame_matches(
                state,
                frame,
                resolved_subject=subject_entity_by_claim.get(state.claim_id),
                resolved_object=object_entity_by_claim.get(state.claim_id),
                request_scope=request.scope,
            )
        ):
            continue
        identity = _claim_scope_identity(state)
        selected_scope_specificity_by_claim[identity] = max(
            _scope_specificity(state.claim_key.scope, request),
            selected_scope_specificity_by_claim.get(identity, 0),
        )
    for state in states:
        if graph_matched_claim_ids and state.claim_id not in graph_matched_claim_ids:
            resolved_subject = subject_entity_by_claim.get(state.claim_id, state.claim_key.subject_entity_id)
            entity_terms = _tokens(" ".join(entity_names_by_id.get(resolved_subject, set())))
            if excluded_terms & entity_terms:
                rejected.append(state.claim_id)
            elif request.include_context:
                context.append(state.claim_id)
            continue
        if effective_predicate_id and state.claim_key.predicate_id != effective_predicate_id:
            continue
        if not request.scope.can_read(state.claim_key.scope):
            continue
        if _scope_specificity(state.claim_key.scope, request) < selected_scope_specificity_by_claim.get(
            _claim_scope_identity(state),
            0,
        ):
            if request.include_context:
                context.append(state.claim_id)
            continue
        # A full graph audit enumerates the lifecycle-valid graph slice instead
        # of treating one heuristic name match as an answer-time constraint.
        # This broadening is available only through the explicit audit purpose.
        frame_for_match = (
            frame.model_copy(update={"resolved_entity_ids": []})
            if request.purpose == RetrievalPurpose.GRAPH_AUDIT and request.scope_mode == "full"
            else frame
        )
        resolved_object = object_entity_by_claim.get(state.claim_id)
        resolved_subject = subject_entity_by_claim.get(state.claim_id, state.claim_key.subject_entity_id)
        if not _frame_matches(
            state,
            frame_for_match,
            resolved_subject=resolved_subject,
            resolved_object=resolved_object,
            request_scope=request.scope,
        ):
            entity_terms = _tokens(" ".join(entity_names_by_id.get(resolved_subject, set())))
            if entity_terms & query_tokens and state.lifecycle_state == ClaimLifecycleState.ACTIVE:
                if frame.resolved_entity_ids and resolved_subject not in frame.resolved_entity_ids:
                    if excluded_terms & entity_terms:
                        rejected.append(state.claim_id)
                    elif request.include_context:
                        context.append(state.claim_id)
                elif request.include_context and frame.temporal_kind in {
                    QueryTemporalKind.HISTORICAL,
                    QueryTemporalKind.INTERVAL,
                }:
                    context.append(state.claim_id)
            elif request.include_context and state.lifecycle_state in {
                ClaimLifecycleState.SUPERSEDED,
                ClaimLifecycleState.INVALIDATED,
                ClaimLifecycleState.EXPIRED,
            }:
                context.append(state.claim_id)
            continue
        searchable = _tokens(
            f"{state.claim_key.subject_entity_id} {state.claim_key.predicate_id} {state.object_value} {state.claim_key.scope_key}"
        ) | _tokens(" ".join(entity_names_by_id.get(resolved_subject, set())))
        overlap = len(query_tokens & searchable)
        rationale: list[str] = []
        score = float(overlap)
        if resolved_subject in frame.resolved_entity_ids or resolved_object in frame.resolved_entity_ids:
            score += 10.0
            rationale.append("resolved_entity_match")
        if effective_predicate_id == state.claim_key.predicate_id:
            score += 6.0
            rationale.append("predicate_match")
        if frame.scope_key is not None and state.claim_key.scope_key == frame.scope_key:
            score += 5.0
            rationale.append("scope_match")
        elif request.scope_key is not None and state.claim_key.scope_key == "global":
            rationale.append("global_scope_fallback")
        if state.lifecycle_state == ClaimLifecycleState.ACTIVE:
            score += 2.0
            rationale.append("active_lifecycle")
        if request.purpose == RetrievalPurpose.EXECUTION and state.claim_key.predicate_id == "action_state":
            score += 8.0
            rationale.append("active_execution_state")
            normalized_status = state.object_value.casefold().replace(" ", "_")
            if normalized_status in {"in_progress", "resumed", "progressed"}:
                score += 6.0
                rationale.append("continuation_eligible_status")
            elif normalized_status in {"blocked", "abandoned", "completed", "failed", "succeeded"}:
                score -= 6.0
                rationale.append("terminal_execution_status")
        if overlap or rationale:
            selected.append(
                RetrievalCandidate(
                    claim_id=state.claim_id,
                    score=max(0.0, score),
                    lexical_overlap=overlap,
                    lifecycle_state=state.lifecycle_state,
                    rationale=rationale,
                )
            )
        elif request.include_context:
            context.append(state.claim_id)
    selected.sort(key=lambda candidate: (-candidate.score, candidate.claim_id))
    limit = 1 if request.purpose == RetrievalPurpose.EXECUTION else request.top_k
    discarded = selected[limit:]
    if request.include_context:
        context.extend(candidate.claim_id for candidate in discarded)
    selected = selected[:limit]
    selected_ids = [candidate.claim_id for candidate in selected]
    if request.include_conflicts:
        rejected.extend(
            state.claim_id
            for state in states
            if state.lifecycle_state
            in {ClaimLifecycleState.SUPERSEDED, ClaimLifecycleState.INVALIDATED, ClaimLifecycleState.EXPIRED}
            and state.claim_id not in selected_ids
        )
    result = ProductionRetrievalDecision(
        query=request.query,
        semantic_frame_status=SemanticFrameStatus.MATCHED,
        temporal_frame=frame,
        query_analysis=request.query_analysis,
        graph_pattern_resolution=request.graph_pattern_resolution,
        resolution_status="resolved",
        selected_record_ids=list(dict.fromkeys(selected_ids)),
        supporting_record_ids=selected_ids,
        rejected_record_ids=sorted(set(rejected)),
        context_record_ids=sorted(set(context) - set(selected_ids)),
        abstained=not selected_ids,
        abstention_reason="no_lifecycle_valid_match" if not selected_ids else None,
        candidates=selected,
        confidence_status="uncalibrated" if selected_ids else "abstained",
    )
    channels: dict[str, Literal["selected", "supporting", "context", "rejected"]] = {}
    for claim_id in selected_ids:
        channels[claim_id] = "selected"
    for claim_id in result.supporting_record_ids:
        channels.setdefault(claim_id, "supporting")
    for claim_id in result.context_record_ids:
        channels.setdefault(claim_id, "context")
    for claim_id in result.rejected_record_ids:
        channels.setdefault(claim_id, "rejected")
    state_by_id = {state.claim_id: state for state in states}
    context_items = [
        RetrievalContextItem(
            claim_id=claim_id,
            channel=channel,
            lifecycle_state=state_by_id[claim_id].lifecycle_state,
            subject_entity_id=subject_entity_by_claim.get(
                claim_id,
                state_by_id[claim_id].claim_key.subject_entity_id,
            ),
            predicate_id=state_by_id[claim_id].claim_key.predicate_id,
            scope_key=state_by_id[claim_id].claim_key.scope_key,
        )
        for claim_id, channel in channels.items()
        if claim_id in state_by_id
    ]
    evidence = [
        RetrievalEvidence(claim_id=claim_id, source_id=span.source_id, quote=span.quote)
        for claim_id, state in state_by_id.items()
        if claim_id in channels
        for span in state.evidence_spans
    ]
    return result.model_copy(update={"context_items": context_items, "evidence": evidence})


def _frame_matches(
    state: ClaimState,
    frame: QueryTemporalFrame,
    *,
    resolved_subject: str | None = None,
    resolved_object: str | None = None,
    request_scope: MemoryScope | None = None,
) -> bool:
    effective_subject = resolved_subject or state.claim_key.subject_entity_id
    if (
        frame.resolved_entity_ids
        and effective_subject not in frame.resolved_entity_ids
        and resolved_object not in frame.resolved_entity_ids
    ):
        return False
    if request_scope is not None and not request_scope.can_read(state.claim_key.scope):
        return False
    if (
        request_scope is None
        and frame.scope_key is not None
        and state.claim_key.scope_key not in {frame.scope_key, "global"}
    ):
        return False
    if frame.temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        return evaluate_temporal_eligibility(
            lifecycle_state=state.lifecycle_state,
            valid_from=state.valid_from,
            valid_to=state.valid_to,
            temporal_kind=frame.temporal_kind,
            evaluation_time=frame.evaluation_time,
        ).eligible
    if frame.temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
        return evaluate_temporal_eligibility(
            lifecycle_state=state.lifecycle_state,
            valid_from=state.valid_from,
            valid_to=state.valid_to,
            temporal_kind=frame.temporal_kind,
            requested_from=frame.valid_from,
            requested_to=frame.valid_to,
        ).eligible
    return False


def _scope_specificity(scope: MemoryScope, request: ResolvedMemoryQuery) -> int:
    return scope.specificity if request.scope.can_read(scope) else -1


def _claim_scope_identity(state: ClaimState) -> tuple[str, str, str]:
    return (
        state.claim_key.subject_entity_id,
        state.claim_key.predicate_id,
        state.claim_key.qualifier_key,
    )


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\w]+", value.casefold()) if len(token) >= 2}


def _excluded_terms(value: str) -> set[str]:
    tokens = list(re.findall(r"[\w]+", value.casefold()))
    excluded: set[str] = set()
    for marker in ("not", "without", "except", "excluding"):
        for index, token in enumerate(tokens):
            if token == marker:
                excluded.update(tokens[index + 1 : index + 4])
    return {token for token in excluded if len(token) >= 2}
