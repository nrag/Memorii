"""Trusted compilation of untrusted temporal interpretation proposals."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Protocol

from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.temporal_contracts import (
    AbsoluteDateTemporalExpression,
    CatalogAnchorTemporalExpression,
    CurrentTemporalExpression,
    IntervalTemporalExpression,
    QueryAnalysis,
    QueryResolutionConfidenceSource,
    QueryScopeKind,
    QueryTemporalFrame,
    QueryTemporalKind,
    QueryTextSpan,
    RelativeDateTemporalExpression,
    TemporalAnchorCatalog,
    TemporalInterpretationProposal,
)


class TemporalCompilationError(ValueError):
    """The proposal could not be grounded in caller-owned temporal context."""


class RelativeTemporalExpressionResolver(Protocol):
    """Locale-aware resolver for deployments that support relative expressions."""

    def resolve(
        self,
        *,
        text: str,
        language: str,
        reference_time: datetime,
    ) -> tuple[datetime, datetime] | None: ...


def compile_temporal_proposal(
    proposal: TemporalInterpretationProposal,
    *,
    query: str,
    language: str,
    reference_time: datetime | None,
    request_scope: MemoryScope,
    anchor_catalog: TemporalAnchorCatalog,
    relative_resolver: RelativeTemporalExpressionResolver | None = None,
) -> QueryAnalysis:
    """Compile a model proposal into a server-owned temporal analysis.

    The provider chooses intent and references visible catalog objects. It can
    never author evaluation time, interval bounds, or request scope.
    """

    if proposal.language.casefold() != language.casefold():
        raise TemporalCompilationError("proposal language does not match the request")
    if proposal.temporal_intent == QueryTemporalKind.AMBIGUOUS:
        return _ambiguous_analysis(proposal, language=language)
    expression = proposal.temporal_expression
    if expression is None:
        raise TemporalCompilationError("resolved temporal proposal is missing an expression")

    anchor_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evaluation_time: datetime | None = None

    if isinstance(expression, CurrentTemporalExpression):
        if proposal.temporal_intent not in {
            QueryTemporalKind.CURRENT,
            QueryTemporalKind.EXECUTION,
            QueryTemporalKind.BELIEF,
        }:
            raise TemporalCompilationError("current expression conflicts with temporal intent")
        evaluation_time = reference_time
    elif isinstance(expression, CatalogAnchorTemporalExpression):
        anchor_text = _validate_query_span(query, expression.source_span)
        resolution = anchor_catalog.resolve(
            anchor_text,
            scope=request_scope,
        )
        if resolution.status != "resolved" or resolution.anchor is None:
            raise TemporalCompilationError(
                f"temporal anchor source span is {resolution.status}"
            )
        anchor = resolution.anchor
        if anchor.anchor_id != expression.anchor_id:
            raise TemporalCompilationError(
                "proposal anchor does not match the cited query span"
            )
        anchor_id = anchor.anchor_id
        valid_from = anchor.valid_from
        valid_to = anchor.valid_to
    elif isinstance(expression, AbsoluteDateTemporalExpression):
        text = _validate_query_span(query, expression.source_span)
        valid_from, valid_to = _parse_absolute_interval(text)
    elif isinstance(expression, IntervalTemporalExpression):
        start_text = _validate_query_span(query, expression.start_span)
        end_text = _validate_query_span(query, expression.end_span)
        valid_from, _ = _parse_absolute_interval(start_text)
        _, valid_to = _parse_absolute_interval(end_text)
        if valid_from >= valid_to:
            raise TemporalCompilationError("compiled temporal interval is empty or reversed")
    elif isinstance(expression, RelativeDateTemporalExpression):
        text = _validate_query_span(query, expression.source_span)
        if reference_time is None or relative_resolver is None:
            raise TemporalCompilationError("relative temporal expression is unsupported")
        resolved = relative_resolver.resolve(
            text=text,
            language=language,
            reference_time=reference_time,
        )
        if resolved is None:
            raise TemporalCompilationError("relative temporal expression is ambiguous")
        valid_from, valid_to = resolved
    else:  # pragma: no cover - discriminated Pydantic union is exhaustive
        raise TemporalCompilationError("unsupported temporal expression")

    if proposal.temporal_intent in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
        if valid_from is None or valid_to is None:
            raise TemporalCompilationError("historical intent requires a grounded interval")
    elif not isinstance(expression, CurrentTemporalExpression):
        raise TemporalCompilationError("bounded expression conflicts with current temporal intent")

    confidence = 1.0
    frame = QueryTemporalFrame(
        temporal_kind=proposal.temporal_intent,
        scope_kind=_scope_kind(request_scope),
        scope_key=request_scope.scope_key,
        anchor_id=anchor_id,
        evaluation_time=evaluation_time,
        resolved_entity_ids=list(proposal.candidate_entity_ids),
        valid_from=valid_from,
        valid_to=valid_to,
        resolution_confidence=confidence,
        resolution_confidence_source=QueryResolutionConfidenceSource.TEMPORAL_COMPILER,
        resolution_confidence_is_calibrated=False,
    )
    return QueryAnalysis(
        language=language,
        temporal_frame=frame,
        predicate_id=proposal.predicate_id,
        subject_entity_id=proposal.subject_entity_id,
        graph_patterns=proposal.graph_patterns,
        analysis_confidence=proposal.model_confidence or 0.0,
        analysis_source="structured_model",
        confidence_source=QueryResolutionConfidenceSource.STRUCTURED_MODEL,
        confidence_is_calibrated=False,
        temporal_intent=proposal.temporal_intent,
        entity_mentions=proposal.entity_mentions,
    )


def _ambiguous_analysis(
    proposal: TemporalInterpretationProposal,
    *,
    language: str,
) -> QueryAnalysis:
    reason = proposal.abstention_reason or "structured_temporal_proposal_ambiguous"
    return QueryAnalysis(
        language=language,
        temporal_frame=QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.AMBIGUOUS,
            resolution_confidence=0.0,
            resolution_confidence_source=QueryResolutionConfidenceSource.STRUCTURED_MODEL,
            ambiguity_reasons=[reason],
        ),
        predicate_id=proposal.predicate_id,
        subject_entity_id=proposal.subject_entity_id,
        graph_patterns=proposal.graph_patterns,
        analysis_confidence=0.0,
        analysis_source="structured_model",
        confidence_source=QueryResolutionConfidenceSource.STRUCTURED_MODEL,
        confidence_is_calibrated=False,
        temporal_intent=QueryTemporalKind.AMBIGUOUS,
        entity_mentions=proposal.entity_mentions,
        abstention_reason=reason,
    )


def _validate_query_span(query: str, span: QueryTextSpan) -> str:
    if span.end > len(query) or query[span.start : span.end] != span.text:
        raise TemporalCompilationError("temporal source span does not match the original query")
    return span.text.strip()


def _parse_absolute_interval(text: str) -> tuple[datetime, datetime]:
    """Parse language-neutral ISO date expressions and no other free text."""

    normalized = text.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}", normalized):
            year, month = (int(part) for part in normalized.split("-"))
            start = datetime(year, month, 1, tzinfo=UTC)
            end = (
                datetime(year + 1, 1, 1, tzinfo=UTC)
                if month == 12
                else datetime(year, month + 1, 1, tzinfo=UTC)
            )
            return start, end
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
            start = datetime.fromisoformat(normalized).replace(tzinfo=UTC)
            return start, start + timedelta(days=1)
        instant = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TemporalCompilationError("absolute temporal expression must use ISO 8601") from exc
    if instant.tzinfo is None:
        raise TemporalCompilationError("absolute temporal expression must include a timezone")
    instant = instant.astimezone(UTC)
    return instant, instant + timedelta(microseconds=1)


def _scope_kind(scope: MemoryScope) -> QueryScopeKind:
    if scope.task_id is not None:
        return QueryScopeKind.TASK
    if scope.session_id is not None:
        return QueryScopeKind.SESSION
    if scope.user_id is not None:
        return QueryScopeKind.USER
    return QueryScopeKind.GLOBAL
