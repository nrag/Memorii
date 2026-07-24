"""Structured and conservative query analyzers."""

from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError

from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.query_analysis.contracts import (
    LexicalQueryResolver,
    QueryAnalyzer,
    StructuredQueryAnalysisProvider,
    StructuredQueryConstraintError,
    StructuredQueryProviderError,
)
from memorii.core.memory_evolution.query_analysis.lexical import (
    EnglishLexicalQueryResolver,
)
from memorii.core.memory_evolution.query_analysis.validation import validate_query_analysis_constraints
from memorii.core.memory_evolution.temporal_compilation import (
    RelativeTemporalExpressionResolver,
    TemporalCompilationError,
    compile_temporal_proposal,
)
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryAnalysisFailureCode,
    QueryResolutionConfidenceSource,
    QueryTemporalFrame,
    QueryTemporalKind,
    TemporalAnchorCatalog,
    TemporalEntityCandidate,
    TemporalInterpretationProposal,
)


class StructuredQueryAnalyzer:
    """Adapter for a configured semantic analyzer with explicit provenance."""

    def __init__(
        self,
        provider: StructuredQueryAnalysisProvider,
        *,
        analyzer_name: str,
        analyzer_version: str,
        predicate_registry: PredicateRegistry | None = None,
        relative_temporal_resolver: RelativeTemporalExpressionResolver | None = None,
    ) -> None:
        self._provider = provider
        self._analyzer_name = analyzer_name
        self._analyzer_version = analyzer_version
        self._predicates = predicate_registry or PredicateRegistry()
        self._relative_temporal_resolver = relative_temporal_resolver

    def analyze(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope | None = None,
    ) -> QueryAnalysis:
        failure_code: QueryAnalysisFailureCode | None = None
        failure_type: str | None = None
        try:
            analysis = self._provider(
                query=query,
                language=language,
                request_scope=request_scope or MemoryScope(),
                reference_time=reference_time,
                entity_candidates=entity_candidates,
                anchor_catalog=anchor_catalog,
            )
            proposal = TemporalInterpretationProposal.model_validate(analysis)
            parsed = compile_temporal_proposal(
                proposal,
                query=query,
                language=language,
                reference_time=reference_time,
                request_scope=request_scope or MemoryScope(),
                anchor_catalog=anchor_catalog,
                relative_resolver=self._relative_temporal_resolver,
            )
            parsed = validate_query_analysis_constraints(
                parsed,
                entity_candidates=entity_candidates,
                anchor_catalog=anchor_catalog,
                request_scope=request_scope,
                predicate_registry=self._predicates,
            )
            return parsed.model_copy(
                update={
                    "analysis_source": "structured_model",
                    "confidence_source": parsed.confidence_source,
                    "confidence_is_calibrated": False,
                    "analyzer_name": self._analyzer_name,
                    "analyzer_version": self._analyzer_version,
                    "temporal_intent": parsed.temporal_intent
                    or (
                        parsed.temporal_frame.temporal_kind
                        if parsed.temporal_frame is not None
                        else QueryTemporalKind.AMBIGUOUS
                    ),
                }
            )
        except (StructuredQueryProviderError, TimeoutError, ConnectionError) as exc:
            failure_code = QueryAnalysisFailureCode.PROVIDER_ERROR
            failure_type = type(exc).__name__
        except ValidationError as exc:
            failure_code = QueryAnalysisFailureCode.SCHEMA_ERROR
            failure_type = type(exc).__name__
        except (StructuredQueryConstraintError, TemporalCompilationError) as exc:
            failure_code = QueryAnalysisFailureCode.CONSTRAINT_ERROR
            failure_type = type(exc).__name__
        return QueryAnalysis(
            language=language,
            temporal_frame=QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.AMBIGUOUS,
                resolution_confidence=0.0,
                resolution_confidence_source=QueryResolutionConfidenceSource.PROVIDER,
                ambiguity_reasons=["structured_query_analysis_failed"],
            ),
            analysis_confidence=0.0,
            analysis_source="provider",
            confidence_source=QueryResolutionConfidenceSource.PROVIDER,
            confidence_is_calibrated=False,
            temporal_intent=QueryTemporalKind.AMBIGUOUS,
            abstention_reason=f"structured_query_analysis_failed:{failure_type}",
            analyzer_name=self._analyzer_name,
            analyzer_version=self._analyzer_version,
            provider_error=failure_type,
            failure_code=failure_code,
        )


class LexicalQueryAnalyzer:
    """Locale-scoped deterministic analyzer with explicit abstention semantics."""

    def __init__(
        self,
        lexical_resolver: LexicalQueryResolver,
        *,
        analyzer_name: str,
        analyzer_version: str,
    ) -> None:
        self._lexical_resolver = lexical_resolver
        self._analyzer_name = analyzer_name
        self._analyzer_version = analyzer_version

    def analyze(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope | None = None,
    ) -> QueryAnalysis:
        if not self._lexical_resolver.supports(language):
            return QueryAnalysis(
                language=language,
                temporal_frame=QueryTemporalFrame(
                    temporal_kind=QueryTemporalKind.AMBIGUOUS,
                    resolution_confidence=0.0,
                    resolution_confidence_source=QueryResolutionConfidenceSource.LANGUAGE_GUARD,
                    ambiguity_reasons=["unsupported_language_requires_structured_query_analysis"],
                ),
                analysis_confidence=0.0,
                analysis_source="language_guard",
                confidence_source=QueryResolutionConfidenceSource.LANGUAGE_GUARD,
                confidence_is_calibrated=False,
                temporal_intent=QueryTemporalKind.AMBIGUOUS,
                abstention_reason="unsupported language requires structured query analysis",
                analyzer_name=self._analyzer_name,
                analyzer_version=self._analyzer_version,
                failure_code=QueryAnalysisFailureCode.UNSUPPORTED_LANGUAGE,
            )
        resolution = self._lexical_resolver.resolve_temporal_frame(
            query,
            reference_time=reference_time,
            entity_candidates=entity_candidates,
            language=language,
            anchor_catalog=anchor_catalog,
            request_scope=request_scope,
        )
        return QueryAnalysis(
            language=language,
            temporal_frame=resolution.frame,
            predicate_id=self._lexical_resolver.infer_predicate_id(query),
            analysis_confidence=resolution.frame.resolution_confidence,
            analysis_source=resolution.analysis_source,
            confidence_source=resolution.frame.resolution_confidence_source,
            confidence_is_calibrated=False,
            temporal_intent=resolution.frame.temporal_kind,
            abstention_reason=(resolution.rationale if resolution.status != "resolved" else None),
            analyzer_name=self._analyzer_name,
            analyzer_version=self._analyzer_version,
        )


class EnglishLexicalQueryAnalyzer(LexicalQueryAnalyzer):
    """High-precision English analyzer used when no semantic model is configured."""

    def __init__(self) -> None:
        super().__init__(
            EnglishLexicalQueryResolver(),
            analyzer_name="english_lexical_query_analyzer",
            analyzer_version="1",
        )


class ProductionQueryAnalyzer:
    """Escalate only unresolved lexical analyses and fail closed on model errors."""

    def __init__(
        self,
        *,
        lexical: QueryAnalyzer,
        structured: QueryAnalyzer | None,
    ) -> None:
        self._lexical = lexical
        self._structured = structured

    def analyze(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope | None = None,
    ) -> QueryAnalysis:
        arguments = {
            "query": query,
            "language": language,
            "reference_time": reference_time,
            "entity_candidates": entity_candidates,
            "anchor_catalog": anchor_catalog,
            "request_scope": request_scope,
        }
        lexical = self._lexical.analyze(**arguments)
        reason = _structured_escalation_reason(lexical)
        lexical_name = lexical.analyzer_name or type(self._lexical).__name__
        if reason is None:
            return lexical.model_copy(
                update={
                    "analyzer_path": [lexical_name],
                    "analyzer_outcome": "resolved",
                    "structured_query_call_count": 0,
                }
            )
        if self._structured is None:
            return lexical.model_copy(
                update={
                    "analyzer_path": [lexical_name],
                    "escalation_reason": reason,
                    "analyzer_outcome": "abstained",
                    "structured_query_call_count": 0,
                }
            )

        structured = self._structured.analyze(**arguments)
        structured_name = structured.analyzer_name or type(self._structured).__name__
        failed = structured.failure_code is not None or structured.provider_error is not None
        abstained = structured.abstention_reason is not None or (
            structured.temporal_frame is None
            or structured.temporal_frame.temporal_kind == QueryTemporalKind.AMBIGUOUS
        )
        outcome = "failed" if failed else "abstained" if abstained else "resolved"
        return structured.model_copy(
            update={
                "analyzer_path": [lexical_name, structured_name],
                "escalation_reason": reason,
                "analyzer_outcome": outcome,
                "structured_query_call_count": 1,
            }
        )


def _structured_escalation_reason(analysis: QueryAnalysis) -> str | None:
    if analysis.failure_code == QueryAnalysisFailureCode.UNSUPPORTED_LANGUAGE:
        return "unsupported_language"
    if analysis.temporal_frame is None:
        return "missing_temporal_frame"
    if analysis.temporal_frame.temporal_kind == QueryTemporalKind.AMBIGUOUS:
        return "ambiguous_lexical_analysis"
    if analysis.abstention_reason is not None:
        return "unresolved_lexical_analysis"
    return None
