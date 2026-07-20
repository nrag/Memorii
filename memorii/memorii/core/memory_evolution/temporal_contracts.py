"""Temporal-domain contracts and lifecycle eligibility policy."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.models import (
    ClaimLifecycleState,
    EntityLinkLifecycleState,
    MemoryGraphLifecycleState,
    MemoryScope,
)
from memorii.core.memory_evolution.query_graph import GraphPatternConstraint, GraphPatternConstraintOutput
from memorii.core.memory_evolution.query_text import contains_query_phrase, normalize_query_text


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
    UNSUPPORTED_LANGUAGE = "unsupported_language"


class QueryResolutionConfidenceSource(StrEnum):
    CALLER = "caller"
    STRUCTURED_MODEL = "structured_model"
    TEMPORAL_COMPILER = "temporal_compiler"
    GRAPH_CONSTRAINT = "graph_constraint"
    LEXICAL_PARTICIPANT_FALLBACK = "lexical_participant_fallback"
    SUBJECT_FRAME_FALLBACK = "subject_frame_fallback"
    HEURISTIC_UNCALIBRATED = "heuristic_uncalibrated"
    PROVIDER = "provider"
    LANGUAGE_GUARD = "language_guard"


class QueryScopeKind(StrEnum):
    NONE = "none"
    GLOBAL = "global"
    TASK = "task"
    SESSION = "session"
    USER = "user"
    ENTITY = "entity"
    CUSTOM = "custom"


class QueryTextSpan(BaseModel):
    """A provider-proposed span that must match the original query exactly."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_bounds(self) -> QueryTextSpan:
        if self.start >= self.end:
            raise ValueError("query span start must be before end")
        return self


class CurrentTemporalExpression(BaseModel):
    expression_kind: Literal["current"] = "current"

    model_config = ConfigDict(extra="forbid")


class CatalogAnchorTemporalExpression(BaseModel):
    expression_kind: Literal["catalog_anchor"] = "catalog_anchor"
    anchor_id: str = Field(min_length=1)
    source_span: QueryTextSpan

    model_config = ConfigDict(extra="forbid")


class AbsoluteDateTemporalExpression(BaseModel):
    expression_kind: Literal["absolute_date"] = "absolute_date"
    source_span: QueryTextSpan

    model_config = ConfigDict(extra="forbid")


class IntervalTemporalExpression(BaseModel):
    expression_kind: Literal["interval"] = "interval"
    start_span: QueryTextSpan
    end_span: QueryTextSpan

    model_config = ConfigDict(extra="forbid")


class RelativeDateTemporalExpression(BaseModel):
    expression_kind: Literal["relative_date"] = "relative_date"
    source_span: QueryTextSpan

    model_config = ConfigDict(extra="forbid")


TemporalExpression = Annotated[
    CurrentTemporalExpression
    | CatalogAnchorTemporalExpression
    | AbsoluteDateTemporalExpression
    | IntervalTemporalExpression
    | RelativeDateTemporalExpression,
    Field(discriminator="expression_kind"),
]


class CurrentTemporalExpressionOutput(BaseModel):
    expression_kind: Literal["current"] = Field()

    model_config = ConfigDict(extra="forbid")


class CatalogAnchorTemporalExpressionOutput(BaseModel):
    expression_kind: Literal["catalog_anchor"] = Field()
    anchor_id: str = Field(min_length=1)
    source_span: QueryTextSpan

    model_config = ConfigDict(extra="forbid")


class AbsoluteDateTemporalExpressionOutput(BaseModel):
    expression_kind: Literal["absolute_date"] = Field()
    source_span: QueryTextSpan

    model_config = ConfigDict(extra="forbid")


class IntervalTemporalExpressionOutput(BaseModel):
    expression_kind: Literal["interval"] = Field()
    start_span: QueryTextSpan
    end_span: QueryTextSpan

    model_config = ConfigDict(extra="forbid")


class RelativeDateTemporalExpressionOutput(BaseModel):
    expression_kind: Literal["relative_date"] = Field()
    source_span: QueryTextSpan

    model_config = ConfigDict(extra="forbid")


TemporalExpressionOutput = Annotated[
    CurrentTemporalExpressionOutput
    | CatalogAnchorTemporalExpressionOutput
    | AbsoluteDateTemporalExpressionOutput
    | IntervalTemporalExpressionOutput
    | RelativeDateTemporalExpressionOutput,
    Field(discriminator="expression_kind"),
]


class TemporalInterpretationProposal(BaseModel):
    """Untrusted semantic proposal emitted by a structured model.

    Authoritative timestamps, intervals, and scope are deliberately absent.
    They are introduced only by the trusted temporal compiler.
    """

    language: str = "en"
    temporal_intent: QueryTemporalKind
    temporal_expression: TemporalExpression | None = None
    candidate_entity_ids: list[str] = Field(default_factory=list)
    predicate_id: str | None = None
    subject_entity_id: str | None = None
    graph_patterns: list[GraphPatternConstraint] = Field(default_factory=list, max_length=3)
    entity_mentions: list[str] = Field(default_factory=list)
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    abstention_reason: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_resolution_claim(self) -> TemporalInterpretationProposal:
        if self.temporal_intent == QueryTemporalKind.AMBIGUOUS:
            if self.temporal_expression is not None:
                raise ValueError("ambiguous proposals cannot carry a resolved temporal expression")
            if self.abstention_reason is None:
                raise ValueError("ambiguous proposals require an abstention reason")
        elif self.temporal_expression is None:
            raise ValueError("resolved temporal proposals require an expression")
        return self


class TemporalInterpretationOutput(BaseModel):
    """Strict provider transport consumed by the trusted temporal compiler."""

    language: str = Field()
    temporal_intent: QueryTemporalKind
    temporal_expression: TemporalExpressionOutput | None = Field()
    candidate_entity_ids: list[str] = Field()
    predicate_id: str | None = Field()
    subject_entity_id: str | None = Field()
    graph_patterns: list[GraphPatternConstraintOutput] = Field(max_length=3)
    entity_mentions: list[str] = Field()
    model_confidence: float | None = Field(ge=0.0, le=1.0)
    abstention_reason: str | None = Field()

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_resolution_claim(self) -> TemporalInterpretationOutput:
        if self.temporal_intent == QueryTemporalKind.AMBIGUOUS:
            if self.temporal_expression is not None:
                raise ValueError("ambiguous proposals cannot carry a resolved temporal expression")
            if self.abstention_reason is None:
                raise ValueError("ambiguous proposals require an abstention reason")
        elif self.temporal_expression is None:
            raise ValueError("resolved temporal proposals require an expression")
        return self


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
    resolution_confidence_source: QueryResolutionConfidenceSource = (
        QueryResolutionConfidenceSource.CALLER
    )
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


QueryAnalysisSource: TypeAlias = Literal[
    "caller",
    "structured_model",
    "heuristic",
    "locale_resolver",
    "language_guard",
    "provider",
]


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
    graph_patterns: list[GraphPatternConstraint] = Field(default_factory=list, max_length=3)
    analysis_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    analysis_source: QueryAnalysisSource = "caller"
    confidence_source: QueryResolutionConfidenceSource = QueryResolutionConfidenceSource.CALLER
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
    lifecycle_state: MemoryGraphLifecycleState
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


_NEVER_ELIGIBLE_LIFECYCLE_STATES = frozenset(
    {
        MemoryGraphLifecycleState.CANDIDATE,
        MemoryGraphLifecycleState.INVALIDATED,
        MemoryGraphLifecycleState.ARCHIVED,
        MemoryGraphLifecycleState.UNKNOWN,
    }
)
_CLOSED_LIFECYCLE_STATES = frozenset(
    {
        MemoryGraphLifecycleState.SUPERSEDED,
        MemoryGraphLifecycleState.EXPIRED,
        MemoryGraphLifecycleState.MERGED,
        MemoryGraphLifecycleState.SPLIT,
        MemoryGraphLifecycleState.RELINKED,
    }
)


def evaluate_temporal_eligibility(
    *,
    lifecycle_state: MemoryGraphLifecycleState | ClaimLifecycleState | EntityLinkLifecycleState | str,
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

    lifecycle_value = lifecycle_state.value if isinstance(lifecycle_state, StrEnum) else lifecycle_state
    graph_lifecycle_state = MemoryGraphLifecycleState(lifecycle_value)
    if graph_lifecycle_state == MemoryGraphLifecycleState.INVALIDATED:
        return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.INVALIDATED)
    if graph_lifecycle_state == MemoryGraphLifecycleState.ARCHIVED:
        return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.ARCHIVED)
    if temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        # A checkpoint can ask for current truth *at a historical evaluation
        # time*. In that case a superseded/expired record remains eligible
        # only while its persisted half-open interval contains that time.
        # An unbounded superseded record is never safe to treat as current.
        if graph_lifecycle_state in _CLOSED_LIFECYCLE_STATES and (evaluation_time is None or valid_to is None):
            reason = (
                TemporalEligibilityReason.SUPERSEDED_FOR_CURRENT
                if graph_lifecycle_state != MemoryGraphLifecycleState.EXPIRED
                else TemporalEligibilityReason.EXPIRED_FOR_CURRENT
            )
            return TemporalEligibilityDecision(eligible=False, reason=reason)
        if (
            graph_lifecycle_state != MemoryGraphLifecycleState.ACTIVE
            and graph_lifecycle_state not in _CLOSED_LIFECYCLE_STATES
        ):
            return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.OUTSIDE_INTERVAL)
        if evaluation_time is not None:
            if valid_from is not None and valid_from > evaluation_time:
                return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.FUTURE_RECORD)
            if valid_to is not None and valid_to <= evaluation_time:
                return TemporalEligibilityDecision(eligible=False, reason=TemporalEligibilityReason.OUTSIDE_INTERVAL)
        return TemporalEligibilityDecision(eligible=True, reason=TemporalEligibilityReason.CURRENT_ACTIVE)
    if temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
        if graph_lifecycle_state in _NEVER_ELIGIBLE_LIFECYCLE_STATES:
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
    analysis_source: QueryAnalysisSource = "heuristic"

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
    scope: MemoryScope = Field(default_factory=MemoryScope)
    lifecycle_state: MemoryGraphLifecycleState = MemoryGraphLifecycleState.ACTIVE
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

    @property
    def scope_key(self) -> str:
        return self.scope.scope_key


class TemporalAnchor(BaseModel):
    """A named, evidence-backed interval that can anchor a query."""

    anchor_id: str
    names: list[str] = Field(min_length=1)
    valid_from: datetime
    valid_to: datetime
    source_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    scope: MemoryScope = Field(default_factory=MemoryScope)
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

    def resolve(self, query: str, *, scope: MemoryScope | None = None) -> TemporalAnchorResolution:
        normalized = normalize_query_text(query)
        request_scope = scope or MemoryScope()
        matches = [
            anchor
            for anchor in self.anchors
            if request_scope.can_read(anchor.scope)
            and any(contains_query_phrase(normalized, name) for name in anchor.names)
        ]
        if matches:
            maximum_specificity = max(anchor.scope.specificity for anchor in matches)
            matches = [anchor for anchor in matches if anchor.scope.specificity == maximum_specificity]
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
