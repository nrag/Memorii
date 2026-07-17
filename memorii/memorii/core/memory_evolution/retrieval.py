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
from memorii.core.memory_evolution.models import ClaimLifecycleState, ClaimState
from memorii.core.memory_evolution.temporal import (
    QueryAnalysis,
    QueryTemporalFrame,
    QueryTemporalKind,
    RetrievalDecision,
    TemporalEntityCandidate,
    TemporalResolution,
    evaluate_temporal_eligibility,
    resolve_query_temporal_frame,
)


class RetrievalPurpose(StrEnum):
    ANSWER = "answer"
    GRAPH_AUDIT = "graph_audit"
    EXECUTION = "execution"


class MemoryQueryRequest(BaseModel):
    """Structured request consumed by the production memory retriever."""

    query: str
    temporal_frame: QueryTemporalFrame | None = None
    query_analysis: QueryAnalysis | None = None
    query_language: str = "en"
    reference_time: datetime | None = None
    scope_key: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    subject_entity_id: str | None = None
    predicate_id: str | None = None
    top_k: int = Field(default=8, ge=1, le=100)
    include_context: bool = True
    include_conflicts: bool = False
    purpose: RetrievalPurpose = RetrievalPurpose.ANSWER

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_reference_time(self) -> MemoryQueryRequest:
        if self.reference_time is not None and self.reference_time.tzinfo is None:
            raise ValueError("reference_time must be timezone-aware")
        return self


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


class ExecutionRetrievalState(BaseModel):
    work_state: WorkStateSnapshot
    continuation: ContinuationDecision

    model_config = ConfigDict(extra="forbid")


class ProductionRetrievalDecision(RetrievalDecision):
    """Query-conditioned retrieval result exposed to provider and agents."""

    query: str
    query_analysis: QueryAnalysis | None = None
    resolution_status: str = "resolved"
    candidates: list[RetrievalCandidate] = Field(default_factory=list)
    decision_source: str = "production_memory_evolution_retriever"
    confidence_status: Literal["uncalibrated", "calibrated", "abstained"] = "uncalibrated"
    execution_state: ExecutionRetrievalState | None = None
    evidence: list[RetrievalEvidence] = Field(default_factory=list)
    context_items: list[RetrievalContextItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


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


def resolve_memory_query(
    request: MemoryQueryRequest,
    *,
    entity_catalog: list[TemporalEntityCandidate],
) -> TemporalResolution:
    """Resolve a query using the production entity catalog, conservatively."""

    if request.temporal_frame is not None:
        frame, status, rationale = _reconcile_request_frame(request, request.temporal_frame)
        return TemporalResolution(
            frame=frame,
            status=status,
            rationale=rationale,
            language=request.query_language,
            analysis_source="caller",
        )
    if request.query_analysis is not None:
        analysis = request.query_analysis
        frame = analysis.temporal_frame
        if frame is None:
            frame = QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.AMBIGUOUS,
                resolution_confidence=0.0,
                ambiguity_reasons=["structured_query_analysis_omitted_temporal_frame"],
            )
            return TemporalResolution(
                frame=frame,
                status="ambiguous",
                rationale="structured query analysis omitted a temporal frame",
                language=request.query_analysis.language,
                analysis_source="structured_model",
            )
        if analysis.subject_entity_id and analysis.subject_entity_id not in frame.resolved_entity_ids:
            frame = frame.model_copy(
                update={"resolved_entity_ids": [*frame.resolved_entity_ids, analysis.subject_entity_id]}
            )
        frame, status, rationale = _reconcile_request_frame(request, frame)
        return TemporalResolution(
            frame=frame,
            status=("ambiguous" if status != "resolved" or frame.ambiguity_reasons else "resolved"),
            rationale=rationale,
            language=request.query_analysis.language,
            analysis_source="structured_model",
        )
    return resolve_query_temporal_frame(
        request.query,
        reference_time=request.reference_time,
        scope_key=request.scope_key,
        entity_candidates=entity_catalog,
        language=request.query_language,
    )


def _reconcile_request_frame(
    request: MemoryQueryRequest,
    frame: QueryTemporalFrame,
) -> tuple[QueryTemporalFrame, Literal["resolved", "ambiguous"], str]:
    """Prevent caller context from silently broadening a supplied frame."""

    if request.scope_key is not None:
        if frame.scope_key is not None and frame.scope_key != request.scope_key:
            return (
                frame.model_copy(update={"temporal_kind": QueryTemporalKind.AMBIGUOUS, "resolution_confidence": 0.0, "ambiguity_reasons": ["request_frame_scope_mismatch"]}),
                "ambiguous",
                "request scope does not match the supplied temporal frame",
            )
        if frame.scope_key is None:
            frame = frame.with_scope(request.scope_key)
    if request.subject_entity_id is not None:
        if frame.resolved_entity_ids and request.subject_entity_id not in frame.resolved_entity_ids:
            return (
                frame.model_copy(update={"temporal_kind": QueryTemporalKind.AMBIGUOUS, "resolution_confidence": 0.0, "ambiguity_reasons": ["request_frame_entity_mismatch"]}),
                "ambiguous",
                "request entity does not match the supplied temporal frame",
            )
        if request.subject_entity_id not in frame.resolved_entity_ids:
            frame = frame.model_copy(update={"resolved_entity_ids": [*frame.resolved_entity_ids, request.subject_entity_id]})
    if (
        frame.temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}
        and frame.evaluation_time is None
        and request.reference_time is not None
    ):
        frame = frame.model_copy(update={"evaluation_time": request.reference_time})
    if frame.temporal_kind == QueryTemporalKind.AMBIGUOUS or frame.ambiguity_reasons or frame.resolution_confidence <= 0.0:
        return frame, "ambiguous", "temporal frame is ambiguous or unresolved"
    return frame, "resolved", "request context and temporal frame are consistent"


def rank_claims(
    *,
    request: MemoryQueryRequest,
    frame: QueryTemporalFrame,
    resolution_status: str = "resolved",
    states: list[ClaimState],
    entity_names_by_id: dict[str, set[str]] | None = None,
    object_entity_by_claim: dict[str, str] | None = None,
) -> ProductionRetrievalDecision:
    """Rank lifecycle-filtered claims without benchmark/oracle knowledge."""

    if (
        frame.temporal_kind == QueryTemporalKind.AMBIGUOUS
        or resolution_status != "resolved"
        or frame.ambiguity_reasons
        or frame.resolution_confidence <= 0.0
    ):
        entity_ambiguity = any("entity" in reason for reason in frame.ambiguity_reasons)
        return ProductionRetrievalDecision(
            query=request.query,
            temporal_frame=frame,
            query_analysis=request.query_analysis,
            resolution_status=resolution_status,
            abstained=True,
            abstention_reason=(
                "entity_resolution_ambiguous"
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
    object_entity_by_claim = object_entity_by_claim or {}
    excluded_terms = _excluded_terms(request.query)
    # A graph audit asks for the resolved entity neighborhood. Inference of a
    # predicate from the wording would silently turn that audit into an
    # answer query and drop definition/rekey evidence. An explicit predicate
    # remains authoritative for callers that intentionally narrow the audit.
    effective_predicate_id = (
        request.predicate_id
        if request.predicate_id is not None
        else None
    )
    if request.predicate_id is None and request.purpose != RetrievalPurpose.GRAPH_AUDIT:
        eligible_predicates = {
            state.claim_key.predicate_id
            for state in states
            if (not request.subject_entity_id or state.claim_key.subject_entity_id == request.subject_entity_id)
            and (not frame.resolved_entity_ids or state.claim_key.subject_entity_id in frame.resolved_entity_ids)
            and (not request.scope_key or state.claim_key.scope_key in {request.scope_key, "global"})
            and _frame_matches(state, frame, resolved_object=object_entity_by_claim.get(state.claim_id))
        }
        if len(eligible_predicates) > 1 and effective_predicate_id not in eligible_predicates:
            return ProductionRetrievalDecision(
                query=request.query,
                temporal_frame=frame,
                query_analysis=request.query_analysis,
                resolution_status="ambiguous",
                abstained=True,
                abstention_reason="predicate_ambiguous",
                confidence_status="abstained",
            )
    exact_scope_match = False
    if request.scope_key is not None:
        exact_scope_match = any(
            state.claim_key.scope_key == request.scope_key
            and (not effective_predicate_id or state.claim_key.predicate_id == effective_predicate_id)
            and (not request.subject_entity_id or state.claim_key.subject_entity_id == request.subject_entity_id)
            and _frame_matches(state, frame, resolved_object=object_entity_by_claim.get(state.claim_id))
            for state in states
        )
    for state in states:
        if effective_predicate_id and state.claim_key.predicate_id != effective_predicate_id:
            continue
        if request.subject_entity_id and state.claim_key.subject_entity_id != request.subject_entity_id:
            continue
        if request.scope_key and state.claim_key.scope_key not in {request.scope_key, "global"}:
            continue
        if exact_scope_match and state.claim_key.scope_key == "global":
            if request.include_context:
                context.append(state.claim_id)
            continue
        # Graph reconstruction is an explicit audit view: it must enumerate
        # the graph neighborhood instead of treating a heuristic name match
        # as an answer-time entity constraint. Scope and lifecycle constraints
        # remain enforced.
        # Graph auditing must be an explicit diagnostic operation; it may not
        # silently broaden answer retrieval by deleting resolved entities.
        frame_for_match = (
            frame.model_copy(update={"resolved_entity_ids": []})
            if isinstance(request, GraphAuditRequest) and request.scope_mode == "full"
            else frame
        )
        resolved_object = object_entity_by_claim.get(state.claim_id)
        if not _frame_matches(state, frame_for_match, resolved_object=resolved_object):
            entity_terms = _tokens(" ".join(entity_names_by_id.get(state.claim_key.subject_entity_id, set())))
            if entity_terms & query_tokens and state.lifecycle_state == ClaimLifecycleState.ACTIVE:
                if frame.resolved_entity_ids and state.claim_key.subject_entity_id not in frame.resolved_entity_ids:
                    if excluded_terms & entity_terms:
                        rejected.append(state.claim_id)
                    elif request.include_context:
                        context.append(state.claim_id)
                elif request.include_context and frame.temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
                    context.append(state.claim_id)
            elif request.include_context and state.lifecycle_state in {ClaimLifecycleState.SUPERSEDED, ClaimLifecycleState.INVALIDATED, ClaimLifecycleState.EXPIRED}:
                context.append(state.claim_id)
            continue
        searchable = _tokens(
            f"{state.claim_key.subject_entity_id} {state.claim_key.predicate_id} {state.object_value} {state.claim_key.scope_key}"
        ) | _tokens(" ".join(entity_names_by_id.get(state.claim_key.subject_entity_id, set())))
        overlap = len(query_tokens & searchable)
        rationale: list[str] = []
        score = float(overlap)
        if state.claim_key.subject_entity_id in frame.resolved_entity_ids or resolved_object in frame.resolved_entity_ids:
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
            if state.lifecycle_state in {ClaimLifecycleState.SUPERSEDED, ClaimLifecycleState.INVALIDATED, ClaimLifecycleState.EXPIRED}
            and state.claim_id not in selected_ids
        )
    result = ProductionRetrievalDecision(
        query=request.query,
        temporal_frame=frame,
        query_analysis=request.query_analysis,
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
            subject_entity_id=state_by_id[claim_id].claim_key.subject_entity_id,
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


def _frame_matches(state: ClaimState, frame: QueryTemporalFrame, *, resolved_object: str | None = None) -> bool:
    if frame.resolved_entity_ids and state.claim_key.subject_entity_id not in frame.resolved_entity_ids and resolved_object not in frame.resolved_entity_ids:
        return False
    if frame.scope_key is not None and state.claim_key.scope_key not in {frame.scope_key, "global"}:
        return False
    if frame.temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        return evaluate_temporal_eligibility(
            lifecycle_state=state.lifecycle_state.value,
            valid_from=state.valid_from,
            valid_to=state.valid_to,
            temporal_kind=frame.temporal_kind,
            evaluation_time=frame.evaluation_time,
        ).eligible
    if frame.temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
        return evaluate_temporal_eligibility(
            lifecycle_state=state.lifecycle_state.value,
            valid_from=state.valid_from,
            valid_to=state.valid_to,
            temporal_kind=frame.temporal_kind,
            requested_from=frame.valid_from,
            requested_to=frame.valid_to,
        ).eligible
    return False


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
