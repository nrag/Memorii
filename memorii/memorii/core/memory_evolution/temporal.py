"""Production query-temporal and lifecycle contracts.

Temporal relevance answers which time frame a query asks about.  Lifecycle
state answers whether a memory is active, superseded, or historical.  They
are intentionally separate so a historical query cannot accidentally turn a
superseded record into current truth.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.memory_evolution.predicates import PredicateRegistry


class QueryTemporalKind(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    INTERVAL = "interval"
    EXECUTION = "execution"
    BELIEF = "belief"
    AMBIGUOUS = "ambiguous"


class QueryAnalysisFailureCode(StrEnum):
    PROVIDER_ERROR = "provider_error"
    SCHEMA_ERROR = "schema_error"
    CONSTRAINT_ERROR = "constraint_error"


class QueryScopeKind(StrEnum):
    NONE = "none"
    GLOBAL = "global"
    TASK = "task"
    ENTITY = "entity"
    CUSTOM = "custom"


class QueryTemporalFrame(BaseModel):
    temporal_kind: QueryTemporalKind = QueryTemporalKind.CURRENT
    scope_kind: QueryScopeKind = QueryScopeKind.NONE
    scope_key: str | None = None
    anchor_id: str | None = None
    evaluation_time: datetime | None = None
    resolved_entity_ids: list[str] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    resolution_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    resolution_confidence_source: Literal[
        "caller", "structured_model", "heuristic_uncalibrated", "provider", "language_guard"
    ] = "caller"
    resolution_confidence_is_calibrated: bool = False
    ambiguity_reasons: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_interval(self) -> QueryTemporalFrame:
        if self.valid_from is not None and self.valid_from.tzinfo is None:
            raise ValueError("valid_from must be timezone-aware")
        if self.valid_to is not None and self.valid_to.tzinfo is None:
            raise ValueError("valid_to must be timezone-aware")
        if self.evaluation_time is not None and self.evaluation_time.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware")
        if self.valid_from is not None and self.valid_to is not None and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be before valid_to for a half-open interval")
        if self.scope_kind == QueryScopeKind.NONE and self.scope_key is not None:
            raise ValueError("scope_key must be omitted for an unscoped temporal frame")
        if self.temporal_kind == QueryTemporalKind.HISTORICAL and self.valid_from is None and self.valid_to is None:
            raise ValueError("historical frames require a temporal anchor")
        if self.scope_kind != QueryScopeKind.NONE and not self.scope_key:
            raise ValueError("scope_key is required for a scoped temporal frame")
        return self

    def with_scope(self, scope_key: str, *, scope_kind: QueryScopeKind = QueryScopeKind.TASK) -> QueryTemporalFrame:
        """Return a frame whose scope kind and key are updated together."""

        if not scope_key.strip():
            raise ValueError("scope_key must not be empty")
        return self.model_copy(update={"scope_key": scope_key, "scope_kind": scope_kind})


class QueryAnalysis(BaseModel):
    """Structured query interpretation supplied by an upstream analyzer.

    The memory retriever may use a deterministic English fallback for early
    development, but non-English or ambiguous requests must arrive with an
    explicit temporal frame rather than silently inheriting current truth.
    """

    language: str = "en"
    temporal_frame: QueryTemporalFrame | None = None
    predicate_id: str | None = None
    subject_entity_id: str | None = None
    analysis_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    analysis_source: Literal["caller", "structured_model", "heuristic", "provider"] = "caller"
    confidence_source: Literal[
        "caller", "structured_model", "heuristic_uncalibrated", "provider", "language_guard"
    ] = "caller"
    confidence_is_calibrated: bool = False
    temporal_intent: QueryTemporalKind | None = None
    entity_mentions: list[str] = Field(default_factory=list)
    abstention_reason: str | None = None
    analyzer_name: str | None = None
    analyzer_version: str | None = None
    provider_error: str | None = None
    failure_code: QueryAnalysisFailureCode | None = None

    model_config = ConfigDict(extra="forbid")


class LifecycleSnapshot(BaseModel):
    evaluation_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    active_record_ids: list[str] = Field(default_factory=list)
    superseded_record_ids: list[str] = Field(default_factory=list)
    historical_record_ids: list[str] = Field(default_factory=list)
    active_work_state_ids: list[str] = Field(default_factory=list)
    conflict_set_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class TemporalCandidate(BaseModel):
    record_id: str
    entity_id: str | None = None
    scope_key: str = "global"
    lifecycle_state: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class TemporalEligibilityReason(StrEnum):
    CURRENT_ACTIVE = "current_active"
    HISTORICAL_OVERLAP = "historical_overlap"
    OUTSIDE_INTERVAL = "outside_interval"
    SUPERSEDED_FOR_CURRENT = "superseded_for_current"
    EXPIRED_FOR_CURRENT = "expired_for_current"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"
    FUTURE_RECORD = "future_record"


class TemporalEligibilityDecision(BaseModel):
    """The single lifecycle/temporal decision used by retrieval callers."""

    eligible: bool
    reason: TemporalEligibilityReason

    model_config = ConfigDict(extra="forbid")


_CURRENT_EXCLUDED_LIFECYCLE_STATES = frozenset({"candidate", "invalidated", "archived"})
_HISTORICAL_EXCLUDED_LIFECYCLE_STATES = frozenset({"candidate", "invalidated", "archived"})


def evaluate_temporal_eligibility(
    *,
    lifecycle_state: str,
    valid_from: datetime | None,
    valid_to: datetime | None,
    temporal_kind: QueryTemporalKind,
    evaluation_time: datetime | None = None,
    requested_from: datetime | None = None,
    requested_to: datetime | None = None,
) -> TemporalEligibilityDecision:
    """Apply lifecycle and half-open interval semantics in one place.

    Current truth is intentionally stricter than historical recall: a record
    marked superseded or expired is never current even when its persisted
    validity interval was not closed by an upstream writer.
    """

    if lifecycle_state in {"invalidated"}:
        return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.INVALIDATED)
    if lifecycle_state in {"archived"}:
        return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.ARCHIVED)
    if temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        # A checkpoint can ask for current truth *at a historical evaluation
        # time*. In that case a superseded/expired record remains eligible
        # only while its persisted half-open interval contains that time.
        # An unbounded superseded record is never safe to treat as current.
        if lifecycle_state in {"superseded", "expired"} and (evaluation_time is None or valid_to is None):
            reason = (
                TemporalEligibilityReason.SUPERSEDED_FOR_CURRENT
                if lifecycle_state == "superseded"
                else TemporalEligibilityReason.EXPIRED_FOR_CURRENT
            )
            return TemporalEligibilityDecision(eligible=False, reason=reason)
        if lifecycle_state in _CURRENT_EXCLUDED_LIFECYCLE_STATES:
            return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.OUTSIDE_INTERVAL)
        if evaluation_time is not None:
            if valid_from is not None and valid_from > evaluation_time:
                return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.FUTURE_RECORD)
            if valid_to is not None and valid_to <= evaluation_time:
                return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.OUTSIDE_INTERVAL)
        return TemporalEligibilityDecision(eligible=True, reason=TemporalEligibilityReason.CURRENT_ACTIVE)
    if temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
        if lifecycle_state in _HISTORICAL_EXCLUDED_LIFECYCLE_STATES:
            return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.OUTSIDE_INTERVAL)
        candidate_from = valid_from or datetime.min.replace(tzinfo=UTC)
        candidate_to = valid_to or datetime.max.replace(tzinfo=UTC)
        query_from = requested_from or datetime.min.replace(tzinfo=UTC)
        query_to = requested_to or datetime.max.replace(tzinfo=UTC)
        if candidate_from < query_to and query_from < candidate_to:
            return TemporalEligibilityDecision(eligible=True, reason=TemporalEligibilityReason.HISTORICAL_OVERLAP)
        return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.OUTSIDE_INTERVAL)
    return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.OUTSIDE_INTERVAL)


def candidate_matches_frame(candidate: TemporalCandidate, frame: QueryTemporalFrame) -> bool:
    if frame.resolved_entity_ids and candidate.entity_id not in frame.resolved_entity_ids:
        return False
    if frame.scope_key is not None and candidate.scope_key not in {frame.scope_key, "global"}:
        return False
    return evaluate_temporal_eligibility(
        lifecycle_state=candidate.lifecycle_state,
        valid_from=candidate.valid_from,
        valid_to=candidate.valid_to,
        temporal_kind=frame.temporal_kind,
        evaluation_time=frame.evaluation_time,
        requested_from=frame.valid_from,
        requested_to=frame.valid_to,
    ).eligible


class TemporalResolution(BaseModel):
    frame: QueryTemporalFrame
    status: Literal["resolved", "ambiguous", "unresolved"]
    rationale: str
    language: str = "en"
    analysis_source: Literal["caller", "structured_model", "heuristic", "language_guard"] = "heuristic"

    model_config = ConfigDict(extra="forbid")


class RetrievalDecision(BaseModel):
    temporal_frame: QueryTemporalFrame
    selected_record_ids: list[str] = Field(default_factory=list)
    supporting_record_ids: list[str] = Field(default_factory=list)
    rejected_record_ids: list[str] = Field(default_factory=list)
    context_record_ids: list[str] = Field(default_factory=list)
    abstained: bool = False
    abstention_reason: str | None = None
    resolution_status: str = "resolved"
    decision_source: str = "production_memory_evolution_retriever"

    model_config = ConfigDict(extra="forbid")


class TemporalEntityCandidate(BaseModel):
    entity_id: str
    names: list[str] = Field(min_length=1)
    entity_type: str | None = None
    scope_key: str | None = None
    lifecycle_state: str = "active"
    lineage_parent_entity_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_interval(self) -> TemporalEntityCandidate:
        if self.valid_from is not None and self.valid_from.tzinfo is None:
            raise ValueError("valid_from must be timezone-aware")
        if self.valid_to is not None and self.valid_to.tzinfo is None:
            raise ValueError("valid_to must be timezone-aware")
        if self.valid_from is not None and self.valid_to is not None and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be before valid_to for a half-open interval")
        return self


class TemporalAnchor(BaseModel):
    """A named, evidence-backed interval that can anchor a query."""

    anchor_id: str
    names: list[str] = Field(min_length=1)
    valid_from: datetime
    valid_to: datetime
    source_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    scope_key: str | None = None
    evidence: list[TemporalAnchorEvidence] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_interval(self) -> TemporalAnchor:
        if self.valid_from.tzinfo is None or self.valid_to.tzinfo is None:
            raise ValueError("temporal anchor bounds must be timezone-aware")
        if self.valid_from >= self.valid_to:
            raise ValueError("temporal anchor valid_from must be before valid_to for a half-open interval")
        if not self.source_ids:
            raise ValueError("temporal anchor must reference at least one source")
        evidence_source_ids = {item.source_id for item in self.evidence}
        if evidence_source_ids and not evidence_source_ids.issubset(set(self.source_ids)):
            raise ValueError("temporal anchor evidence must reference source_ids")
        return self


class TemporalAnchorEvidence(BaseModel):
    """Evidence that a source observation supports a named time interval."""

    source_id: str
    span: str = Field(min_length=1)
    support_type: Literal["explicit_interval", "derived_interval", "named_event"]

    model_config = ConfigDict(extra="forbid")


TemporalAnchor.model_rebuild()


class TemporalAnchorResolution(BaseModel):
    status: Literal["resolved", "ambiguous", "unresolved"]
    anchor: TemporalAnchor | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class TemporalAnchorCatalog(BaseModel):
    """Production-owned catalog for named time references.

    The catalog is deliberately explicit. A phrase such as "release week" is
    not assigned dates from world knowledge; it resolves only when an
    evidence-backed anchor has been registered by the caller or runtime.
    """

    anchors: list[TemporalAnchor] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def register(self, anchor: TemporalAnchor) -> None:
        self.anchors = [existing for existing in self.anchors if existing.anchor_id != anchor.anchor_id]
        self.anchors.append(anchor)

    def resolve(self, query: str, *, scope_key: str | None = None) -> TemporalAnchorResolution:
        normalized = _normalize_text(query)
        matches = [
            anchor
            for anchor in self.anchors
            if (anchor.scope_key is None if scope_key is None else anchor.scope_key in {None, scope_key})
            and any(_contains_phrase(normalized, name) for name in anchor.names)
        ]
        if not matches:
            return TemporalAnchorResolution(
                status="unresolved",
                rationale="no registered temporal anchor matched the query",
            )
        if len(matches) > 1:
            return TemporalAnchorResolution(
                status="ambiguous",
                candidate_ids=sorted(anchor.anchor_id for anchor in matches),
                rationale="multiple registered temporal anchors matched the query",
            )
        anchor = matches[0]
        return TemporalAnchorResolution(
            status="resolved",
            anchor=anchor,
            candidate_ids=[anchor.anchor_id],
            rationale=f"resolved registered temporal anchor {anchor.anchor_id}",
        )


class QueryAnalyzer(Protocol):
    def analyze(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        scope_key: str | None = None,
    ) -> QueryAnalysis: ...


class StructuredQueryAnalysisProvider(Protocol):
    """Provider boundary for structured semantic query analysis.

    Providers may return a validated model or a JSON-like mapping. They must
    not manufacture entity IDs; the analyzer validates all IDs against the
    server-provided candidate catalog.
    """

    def __call__(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        scope_key: str | None = None,
    ) -> QueryAnalysis | Mapping[str, object]: ...


class StructuredQueryProviderError(Exception):
    """Expected transport/provider failure at the structured-query boundary."""


class StructuredQueryConstraintError(ValueError):
    """Expected semantic constraint violation in provider output."""


def validate_temporal_frame_constraints(
    frame: QueryTemporalFrame,
    *,
    entity_candidates: list[TemporalEntityCandidate],
    anchor_catalog: TemporalAnchorCatalog,
    scope_key: str | None = None,
) -> QueryTemporalFrame:
    """Validate a structured frame against server-owned retrieval catalogs.

    This is intentionally shared by provider output and caller-supplied
    structured requests.  A validated Pydantic object is not sufficient: its
    identifiers and anchor interval must also belong to the current runtime
    catalog.
    """

    candidate_by_id = {candidate.entity_id: candidate for candidate in entity_candidates}
    unknown_ids = set(frame.resolved_entity_ids) - set(candidate_by_id)
    if unknown_ids:
        raise StructuredQueryConstraintError("structured query selected unknown entity candidates")
    if scope_key is not None and frame.scope_key not in {None, scope_key, "global"}:
        raise StructuredQueryConstraintError("structured query selected an out-of-scope frame")
    for entity_id in frame.resolved_entity_ids:
        candidate_scope = candidate_by_id[entity_id].scope_key
        if candidate_scope is not None and scope_key is not None and candidate_scope not in {scope_key, "global"}:
            raise StructuredQueryConstraintError("structured query selected an out-of-scope entity")
    if frame.anchor_id is not None:
        anchor = next((item for item in anchor_catalog.anchors if item.anchor_id == frame.anchor_id), None)
        if anchor is None:
            raise StructuredQueryConstraintError("structured query selected an unknown temporal anchor")
        if frame.valid_from != anchor.valid_from or frame.valid_to != anchor.valid_to:
            raise StructuredQueryConstraintError("structured query changed the registered anchor interval")
        if anchor.scope_key is not None and frame.scope_key not in {None, anchor.scope_key}:
            raise StructuredQueryConstraintError("structured query selected an out-of-scope temporal anchor")
    return frame


def validate_query_analysis_constraints(
    analysis: QueryAnalysis,
    *,
    entity_candidates: list[TemporalEntityCandidate],
    anchor_catalog: TemporalAnchorCatalog,
    scope_key: str | None = None,
    predicate_registry: PredicateRegistry | None = None,
) -> QueryAnalysis:
    """Validate structured query identifiers at the retrieval trust boundary."""

    if analysis.temporal_frame is None:
        raise StructuredQueryConstraintError("structured query analysis must return a temporal frame")
    requested_ids = set(analysis.temporal_frame.resolved_entity_ids)
    if analysis.subject_entity_id is not None:
        requested_ids.add(analysis.subject_entity_id)
    frame = analysis.temporal_frame.model_copy(update={"resolved_entity_ids": sorted(requested_ids)})
    frame = validate_temporal_frame_constraints(
        frame,
        entity_candidates=entity_candidates,
        anchor_catalog=anchor_catalog,
        scope_key=scope_key,
    )
    if analysis.predicate_id is not None and predicate_registry is not None and predicate_registry.get(analysis.predicate_id) is None:
        raise StructuredQueryConstraintError(
            f"structured query selected unknown predicate: {analysis.predicate_id}"
        )
    return analysis.model_copy(update={"temporal_frame": frame})


def validate_query_analysis_matches_authoritative_result(
    *,
    requested_frame: QueryTemporalFrame | None,
    requested_analysis: QueryAnalysis | None,
    authoritative_analysis: QueryAnalysis,
    reference_time: datetime | None,
    scope_key: str | None,
) -> None:
    """Ensure caller context cannot replace analyzer-owned query semantics.

    ``requested_frame`` and ``requested_analysis`` are useful as explicit
    constraints for trusted integrations, but they are not an alternate
    source of truth. The configured analyzer must produce the same temporal
    and entity semantics before retrieval can proceed.
    """

    authoritative_frame = authoritative_analysis.temporal_frame
    if authoritative_frame is None:
        raise StructuredQueryConstraintError("authoritative query analysis omitted a temporal frame")

    def normalized_frame(frame: QueryTemporalFrame) -> tuple[object, ...]:
        evaluation_time = frame.evaluation_time
        if (
            evaluation_time is None
            and reference_time is not None
            and frame.temporal_kind in {
                QueryTemporalKind.CURRENT,
                QueryTemporalKind.EXECUTION,
                QueryTemporalKind.BELIEF,
            }
        ):
            evaluation_time = reference_time
        effective_scope = frame.scope_key or scope_key
        return (
            frame.temporal_kind,
            frame.scope_kind if effective_scope is None else effective_scope,
            effective_scope,
            frame.anchor_id,
            evaluation_time,
            frame.valid_from,
            frame.valid_to,
            tuple(sorted(frame.resolved_entity_ids)),
        )

    requested_temporal_frame = requested_frame
    if requested_analysis is not None:
        if requested_analysis.temporal_frame is None:
            raise StructuredQueryConstraintError("requested query analysis omitted a temporal frame")
        requested_temporal_frame = requested_analysis.temporal_frame
        if requested_analysis.subject_entity_id is not None:
            requested_temporal_frame = requested_temporal_frame.model_copy(
                update={
                    "resolved_entity_ids": sorted(
                        {
                            *requested_temporal_frame.resolved_entity_ids,
                            requested_analysis.subject_entity_id,
                        }
                    )
                }
            )

    if (
        requested_temporal_frame is not None
        and normalized_frame(requested_temporal_frame) != normalized_frame(authoritative_frame)
    ):
        raise StructuredQueryConstraintError(
            "caller temporal context disagrees with analyzer-owned query semantics"
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
    ) -> None:
        self._provider = provider
        self._analyzer_name = analyzer_name
        self._analyzer_version = analyzer_version
        self._predicates = predicate_registry or PredicateRegistry()

    def analyze(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        scope_key: str | None = None,
    ) -> QueryAnalysis:
        failure_code: QueryAnalysisFailureCode | None = None
        failure_type: str | None = None
        try:
            analysis = self._provider(
                query=query,
                language=language,
                scope_key=scope_key,
                reference_time=reference_time,
                entity_candidates=entity_candidates,
                anchor_catalog=anchor_catalog,
            )
            parsed = QueryAnalysis.model_validate(analysis)
            parsed = validate_query_analysis_constraints(
                parsed,
                entity_candidates=entity_candidates,
                anchor_catalog=anchor_catalog,
                scope_key=scope_key,
                predicate_registry=self._predicates,
            )
            frame = parsed.temporal_frame
            assert frame is not None
            frame = frame.model_copy(
                update={
                    "resolution_confidence_source": "structured_model",
                    "resolution_confidence_is_calibrated": False,
                }
            )
            return parsed.model_copy(
                update={
                    "temporal_frame": frame,
                    "analysis_source": "structured_model",
                    "confidence_source": "structured_model",
                    "confidence_is_calibrated": False,
                    "analyzer_name": self._analyzer_name,
                    "analyzer_version": self._analyzer_version,
                    "temporal_intent": parsed.temporal_intent or (
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
        except StructuredQueryConstraintError as exc:
            failure_code = QueryAnalysisFailureCode.CONSTRAINT_ERROR
            failure_type = type(exc).__name__
        return QueryAnalysis(
            language=language,
            temporal_frame=QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.AMBIGUOUS,
                resolution_confidence=0.0,
                resolution_confidence_source="provider",
                ambiguity_reasons=["structured_query_analysis_failed"],
            ),
            analysis_confidence=0.0,
            analysis_source="provider",
            confidence_source="provider",
            confidence_is_calibrated=False,
            temporal_intent=QueryTemporalKind.AMBIGUOUS,
            abstention_reason=f"structured_query_analysis_failed:{failure_type}",
            analyzer_name=self._analyzer_name,
            analyzer_version=self._analyzer_version,
            provider_error=failure_type,
            failure_code=failure_code,
        )


class ConservativeQueryAnalyzer:
    """Default production analyzer with explicit abstention semantics."""

    def analyze(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        scope_key: str | None = None,
    ) -> QueryAnalysis:
        resolution = resolve_query_temporal_frame(
            query,
            reference_time=reference_time,
            scope_key=scope_key,
            entity_candidates=entity_candidates,
            language=language,
            anchor_catalog=anchor_catalog,
        )
        return QueryAnalysis(
            language=language,
            temporal_frame=resolution.frame,
            predicate_id=infer_query_predicate_id(query) if _is_english(language) else None,
            analysis_confidence=resolution.frame.resolution_confidence,
            analysis_source="heuristic",
            confidence_source="heuristic_uncalibrated",
            confidence_is_calibrated=False,
            temporal_intent=resolution.frame.temporal_kind,
            abstention_reason=(resolution.rationale if resolution.status != "resolved" else None),
            analyzer_name="conservative_query_analyzer",
            analyzer_version="1",
        )


def infer_query_predicate_id(query: str) -> str | None:
    """Infer only a unique high-precision predicate cue from a query.

    This deterministic vocabulary is an analyzer fallback, not a ranking
    policy. If the query contains multiple predicate cues or none, the
    analyzer returns ``None`` and the retrieval layer must abstain when the
    eligible claims span multiple predicates.
    """

    normalized = re.sub(r"[^\w\s]", " ", query.casefold())
    if "api owner" in normalized or "apiowner" in normalized:
        return "api_owner"
    cues = {
        "owner": {"owner", "owns", "owned", "responsible", "proprietor", "propietario", "dueño"},
        "approver": {"approver", "approve", "approved", "reviewer", "review"},
        "status": {"status", "state", "progress", "estado"},
        "dependency": {"depends", "dependency", "blocked by", "requires"},
        "preference": {"prefer", "preference", "prefers"},
        "action_state": {"continue", "resume", "blocked", "in progress", "next action"},
    }
    matches = {
        predicate_id
        for predicate_id, terms in cues.items()
        if any(term in normalized for term in terms)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def resolve_query_temporal_frame(
    query: str,
    *,
    reference_time: datetime | None = None,
    scope_key: str | None = None,
    entity_candidates: list[TemporalEntityCandidate] | None = None,
    language: str = "en",
    anchor_catalog: TemporalAnchorCatalog | None = None,
) -> TemporalResolution:
    """Resolve explicit temporal language and entity anchors conservatively."""

    normalized = " ".join(query.casefold().split())
    if reference_time is not None and reference_time.tzinfo is None:
        raise ValueError("reference_time must be timezone-aware")
    registered_anchor = anchor_catalog.resolve(normalized, scope_key=scope_key) if anchor_catalog is not None else None
    if registered_anchor is not None and registered_anchor.status == "ambiguous":
        frame = QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.AMBIGUOUS,
            resolution_confidence=0.0,
            resolution_confidence_source="heuristic_uncalibrated",
            ambiguity_reasons=[registered_anchor.rationale],
        )
        return TemporalResolution(
            frame=frame,
            status="ambiguous",
            rationale=registered_anchor.rationale,
            language=language,
            analysis_source="heuristic",
        )
    anchor = _temporal_anchor(normalized, reference_time=reference_time)
    anchor_id: str | None = None
    if registered_anchor is not None and registered_anchor.status == "resolved" and registered_anchor.anchor is not None:
        anchor = (
            QueryTemporalKind.HISTORICAL,
            registered_anchor.anchor.valid_from,
            registered_anchor.anchor.valid_to,
            registered_anchor.rationale,
        )
        anchor_id = registered_anchor.anchor.anchor_id
    if anchor is None and not _is_english(language):
        frame = QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.AMBIGUOUS,
            resolution_confidence=0.0,
            resolution_confidence_source="language_guard",
            ambiguity_reasons=["non_english_query_requires_structured_temporal_frame"],
        )
        return TemporalResolution(
            frame=frame,
            status="ambiguous",
            rationale="non-English query requires an explicit structured temporal frame",
            language=language,
            analysis_source="language_guard",
        )
    if anchor is not None:
        kind, valid_from, valid_to, rationale = anchor
    elif any(token in normalized for token in ("might", "maybe", "unclear", "which one")):
        kind, valid_from, valid_to, rationale = QueryTemporalKind.AMBIGUOUS, None, None, "query temporal anchor is ambiguous"
    elif any(token in normalized for token in ("continue", "resume", "previous fix")):
        kind, valid_from, valid_to, rationale = QueryTemporalKind.EXECUTION, None, None, "query asks for execution continuation"
    elif any(token in normalized for token in ("belief", "hypothesis", "should rank")):
        kind, valid_from, valid_to, rationale = QueryTemporalKind.BELIEF, None, None, "query asks for belief ranking"
    else:
        kind, valid_from, valid_to, rationale = QueryTemporalKind.CURRENT, None, None, "no historical or interval anchor was stated"

    resolved_entity_ids, entity_status, entity_rationale = _resolve_entities(
        normalized,
        entity_candidates or [],
        temporal_kind=kind,
        evaluation_time=reference_time if kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF} else None,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    status = "ambiguous" if kind == QueryTemporalKind.AMBIGUOUS or entity_status == "ambiguous" else "resolved" if entity_status == "resolved" else "unresolved"
    if entity_rationale:
        rationale = f"{rationale}; {entity_rationale}"
    frame = QueryTemporalFrame(
        temporal_kind=kind,
        evaluation_time=reference_time if kind == QueryTemporalKind.CURRENT else None,
        resolved_entity_ids=resolved_entity_ids,
        valid_from=valid_from,
        valid_to=valid_to,
        anchor_id=anchor_id,
        # Lexical resolution is useful for candidate generation, not a
        # calibrated probability. Keep it below the acceptance boundary so
        # callers cannot mistake a heuristic match for model certainty.
        resolution_confidence=0.65 if status == "resolved" else 0.0,
        resolution_confidence_source=(
            "language_guard" if not _is_english(language) else "heuristic_uncalibrated"
        ),
        resolution_confidence_is_calibrated=False,
        ambiguity_reasons=[rationale] if status != "resolved" else [],
    )
    return TemporalResolution(frame=frame, status=status, rationale=rationale, language=language, analysis_source="heuristic")


def _is_english(language: str) -> bool:
    normalized = language.strip().casefold()
    return normalized in {"", "en", "eng", "auto"} or normalized.startswith("en-")


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _contains_phrase(normalized_query: str, phrase: str) -> bool:
    """Match a normalized phrase without substring collisions such as Q1/Q10."""

    normalized_phrase = _normalize_text(phrase)
    if not normalized_phrase:
        return False
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return re.search(pattern, normalized_query, flags=re.UNICODE) is not None


def _temporal_anchor(
    query: str,
    *,
    reference_time: datetime | None,
) -> tuple[QueryTemporalKind, datetime | None, datetime | None, str] | None:
    year_match = re.search(r"\b(20\d{2})\b", query)
    month_names = {name: index for index, name in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), start=1)}
    month_match = next(((name, month) for name, month in month_names.items() if re.search(rf"\b{name}\b", query)), None)
    if month_match is None and year_match is None:
        if "between" in query or ("from" in query and "to" in query):
            return QueryTemporalKind.AMBIGUOUS, None, None, "interval language requires explicit date bounds"
        return None
    if month_match is not None:
        year = int(year_match.group(1)) if year_match else reference_time.year if reference_time is not None else None
        if year is None:
            return QueryTemporalKind.AMBIGUOUS, None, None, "month anchor has no year or reference time"
        start = datetime(year, month_match[1], 1, tzinfo=UTC)
        end = datetime(year + (month_match[1] == 12), month_match[1] % 12 + 1, 1, tzinfo=UTC)
        return QueryTemporalKind.HISTORICAL, start, end, f"resolved month anchor {month_match[0]} {year}"
    if year_match is None:
        return QueryTemporalKind.AMBIGUOUS, None, None, "temporal anchor could not be resolved"
    year = int(year_match.group(1))
    return QueryTemporalKind.HISTORICAL, datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC), f"resolved year anchor {year}"


def _resolve_entities(
    query: str,
    candidates: list[TemporalEntityCandidate],
    *,
    temporal_kind: QueryTemporalKind = QueryTemporalKind.CURRENT,
    evaluation_time: datetime | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> tuple[list[str], str, str]:
    if not candidates:
        return [], "unresolved", "no entity catalog supplied"
    query_tokens = set(re.findall(r"[\w]{2,}", query))
    scored: list[tuple[float, str]] = []
    for candidate in candidates:
        if not _entity_candidate_matches_query(
            candidate,
            temporal_kind=temporal_kind,
            evaluation_time=evaluation_time,
            valid_from=valid_from,
            valid_to=valid_to,
        ):
            continue
        candidate_scores: list[float] = []
        for name in candidate.names:
            normalized_name = _normalize_text(name)
            name_tokens = set(re.findall(r"[\w]{2,}", normalized_name))
            overlap = len(query_tokens & name_tokens)
            if _contains_phrase(query, normalized_name):
                candidate_scores.append(100.0 + len(name_tokens) + min(len(normalized_name), 50) / 100.0)
            elif overlap:
                candidate_scores.append(float(overlap))
        if candidate_scores:
            scored.append((max(candidate_scores), candidate.entity_id))
    scored = [(score, entity_id) for score, entity_id in scored if score]
    if not scored:
        return [], "unresolved", "no entity candidate matched the query"
    best_score = max(score for score, _entity_id in scored)
    best_ids = sorted(entity_id for score, entity_id in scored if score == best_score)
    if len(best_ids) > 1:
        return best_ids, "ambiguous", f"entity candidates tied at score {best_score}"
    return best_ids, "resolved", f"resolved entity {best_ids[0]}"


def _entity_candidate_matches_query(
    candidate: TemporalEntityCandidate,
    *,
    temporal_kind: QueryTemporalKind,
    evaluation_time: datetime | None,
    valid_from: datetime | None,
    valid_to: datetime | None,
) -> bool:
    if temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        if candidate.lifecycle_state != "active":
            return False
        return evaluate_temporal_eligibility(
            lifecycle_state=candidate.lifecycle_state,
            valid_from=candidate.valid_from,
            valid_to=candidate.valid_to,
            temporal_kind=temporal_kind,
            evaluation_time=evaluation_time,
            requested_from=valid_from,
            requested_to=valid_to,
        ).eligible
    if temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
        return evaluate_temporal_eligibility(
            lifecycle_state=candidate.lifecycle_state,
            valid_from=candidate.valid_from,
            valid_to=candidate.valid_to,
            temporal_kind=temporal_kind,
            requested_from=valid_from,
            requested_to=valid_to,
        ).eligible
    return True


def _overlaps(
    candidate: TemporalCandidate | TemporalEntityCandidate,
    valid_from: datetime | None,
    valid_to: datetime | None,
) -> bool:
    if valid_from is None and valid_to is None:
        return True
    candidate_from = candidate.valid_from or datetime.min.replace(tzinfo=UTC)
    candidate_to = candidate.valid_to or datetime.max.replace(tzinfo=UTC)
    query_from = valid_from or datetime.min.replace(tzinfo=UTC)
    query_to = valid_to or datetime.max.replace(tzinfo=UTC)
    return candidate_from < query_to and query_from < candidate_to


def _candidate_valid_at(candidate: TemporalCandidate, evaluation_time: datetime) -> bool:
    return evaluate_temporal_eligibility(
        lifecycle_state=candidate.lifecycle_state,
        valid_from=candidate.valid_from,
        valid_to=candidate.valid_to,
        temporal_kind=QueryTemporalKind.CURRENT,
        evaluation_time=evaluation_time,
    ).eligible
