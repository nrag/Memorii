"""Conservative English lexical query analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from memorii.core.memory_evolution.language import supports_english_rules
from memorii.core.memory_evolution.models import EntityType, MemoryScope, RecordLifecycleState
from memorii.core.memory_evolution.query_text import contains_query_phrase, normalize_query_text
from memorii.core.memory_evolution.temporal_contracts import (
    QueryResolutionConfidenceSource,
    QueryTemporalFrame,
    QueryTemporalKind,
    TemporalAnchorCatalog,
    TemporalCandidate,
    TemporalEntityCandidate,
    TemporalResolution,
    evaluate_temporal_eligibility,
)


class EnglishLexicalQueryResolver:
    """High-precision English fallback; unsupported locales fail closed."""

    def supports(self, language: str) -> bool:
        return is_english(language)

    def infer_predicate_id(self, query: str) -> str | None:
        return infer_query_predicate_id(query)

    def resolve_temporal_frame(
        self,
        query: str,
        *,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        language: str,
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope | None,
    ) -> TemporalResolution:
        return resolve_query_temporal_frame(
            query,
            reference_time=reference_time,
            entity_candidates=entity_candidates,
            language=language,
            anchor_catalog=anchor_catalog,
            request_scope=request_scope,
        )


@dataclass(frozen=True)
class _EntityQueryMatch:
    entity_id: str
    entity_type: str | None
    score: float
    explicit_names: frozenset[str]


def infer_query_predicate_id(query: str) -> str | None:
    """Infer only a unique high-precision predicate cue from a query.

    This deterministic vocabulary is an analyzer fallback, not a ranking
    policy. If the query contains multiple predicate cues or none, the
    analyzer returns ``None`` and the retrieval layer must abstain when the
    eligible claims span multiple predicates.
    """

    normalized = normalize_query_text(re.sub(r"[^\w\s]", " ", query))
    if contains_query_phrase(normalized, "api owner") or contains_query_phrase(normalized, "apiowner"):
        return "api_owner"
    cues = {
        "owner": {"owner", "owners", "ownership", "owns", "owned", "responsible", "proprietor"},
        "approver": {"approver", "approve", "approved", "reviewer", "review"},
        "status": {"status", "state", "progress"},
        "dependency": {"depends", "dependency", "blocked by", "requires"},
        "preference": {"prefer", "preference", "prefers"},
        "action_state": {"continue", "resume", "blocked", "in progress", "next action"},
    }
    matches = {
        predicate_id
        for predicate_id, terms in cues.items()
        if any(contains_query_phrase(normalized, term) for term in terms)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def resolve_query_temporal_frame(
    query: str,
    *,
    reference_time: datetime | None = None,
    entity_candidates: list[TemporalEntityCandidate] | None = None,
    language: str = "en",
    anchor_catalog: TemporalAnchorCatalog | None = None,
    request_scope: MemoryScope | None = None,
) -> TemporalResolution:
    """Resolve explicit temporal language and entity anchors conservatively."""

    normalized = " ".join(query.casefold().split())
    if reference_time is not None and reference_time.tzinfo is None:
        raise ValueError("reference_time must be timezone-aware")
    effective_scope = request_scope or MemoryScope()
    registered_anchor = (
        anchor_catalog.resolve(
            normalized,
            scope=effective_scope,
        )
        if anchor_catalog is not None
        else None
    )
    if registered_anchor is not None and registered_anchor.status == "ambiguous":
        frame = QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.AMBIGUOUS,
            resolution_confidence=0.0,
            resolution_confidence_source=QueryResolutionConfidenceSource.HEURISTIC_UNCALIBRATED,
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
    if (
        registered_anchor is not None
        and registered_anchor.status == "resolved"
        and registered_anchor.anchor is not None
    ):
        anchor = (
            QueryTemporalKind.HISTORICAL,
            registered_anchor.anchor.valid_from,
            registered_anchor.anchor.valid_to,
            registered_anchor.rationale,
        )
        anchor_id = registered_anchor.anchor.anchor_id
    if anchor is None and not is_english(language):
        frame = QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.AMBIGUOUS,
            resolution_confidence=0.0,
            resolution_confidence_source=QueryResolutionConfidenceSource.LANGUAGE_GUARD,
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
    elif any(contains_query_phrase(normalized, token) for token in ("might", "maybe", "unclear", "which one")):
        kind, valid_from, valid_to, rationale = (
            QueryTemporalKind.AMBIGUOUS,
            None,
            None,
            "query temporal anchor is ambiguous",
        )
    elif any(contains_query_phrase(normalized, token) for token in ("continue", "resume", "previous fix")):
        kind, valid_from, valid_to, rationale = (
            QueryTemporalKind.EXECUTION,
            None,
            None,
            "query asks for execution continuation",
        )
    elif any(contains_query_phrase(normalized, token) for token in ("belief", "hypothesis", "should rank")):
        kind, valid_from, valid_to, rationale = QueryTemporalKind.BELIEF, None, None, "query asks for belief ranking"
    else:
        kind, valid_from, valid_to, rationale = (
            QueryTemporalKind.CURRENT,
            None,
            None,
            "no historical or interval anchor was stated",
        )

    resolved_entity_ids, entity_status, entity_rationale = _resolve_entities(
        normalized,
        entity_candidates or [],
        temporal_kind=kind,
        evaluation_time=reference_time
        if kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}
        else None,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    status = (
        "ambiguous"
        if kind == QueryTemporalKind.AMBIGUOUS or entity_status == "ambiguous"
        else "resolved"
        if entity_status == "resolved"
        else "unresolved"
    )
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
            QueryResolutionConfidenceSource.LANGUAGE_GUARD
            if not is_english(language)
            else QueryResolutionConfidenceSource.HEURISTIC_UNCALIBRATED
        ),
        resolution_confidence_is_calibrated=False,
        ambiguity_reasons=[rationale] if status != "resolved" else [],
    )
    return TemporalResolution(
        frame=frame, status=status, rationale=rationale, language=language, analysis_source="heuristic"
    )


def is_english(language: str) -> bool:
    return supports_english_rules(language)


def _temporal_anchor(
    query: str,
    *,
    reference_time: datetime | None,
) -> tuple[QueryTemporalKind, datetime | None, datetime | None, str] | None:
    year_match = re.search(r"\b(20\d{2})\b", query)
    month_names = {
        name: index
        for index, name in enumerate(
            (
                "january",
                "february",
                "march",
                "april",
                "may",
                "june",
                "july",
                "august",
                "september",
                "october",
                "november",
                "december",
            ),
            start=1,
        )
    }
    month_match = next(((name, month) for name, month in month_names.items() if re.search(rf"\b{name}\b", query)), None)
    if month_match is None and year_match is None:
        if contains_query_phrase(query, "between") or (
            contains_query_phrase(query, "from") and contains_query_phrase(query, "to")
        ):
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
    return (
        QueryTemporalKind.HISTORICAL,
        datetime(year, 1, 1, tzinfo=UTC),
        datetime(year + 1, 1, 1, tzinfo=UTC),
        f"resolved year anchor {year}",
    )


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
    preferred_types, excluded_types = _query_entity_type_constraints(query)
    matches_by_id: dict[str, _EntityQueryMatch] = {}
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
        explicit_names: set[str] = set()
        for name in candidate.names:
            normalized_name = normalize_query_text(name)
            name_tokens = set(re.findall(r"[\w]{2,}", normalized_name))
            overlap = len(query_tokens & name_tokens)
            if contains_query_phrase(query, normalized_name):
                candidate_scores.append(100.0 + len(name_tokens) + min(len(normalized_name), 50) / 100.0)
                explicit_names.add(normalized_name)
            elif overlap:
                candidate_scores.append(float(overlap))
        if candidate_scores:
            type_score = 0.0
            if candidate.entity_type in preferred_types:
                type_score = 50.0
            elif candidate.entity_type in excluded_types:
                type_score = -100.0
            score = max(candidate_scores) + type_score
            if not score:
                continue
            previous = matches_by_id.get(candidate.entity_id)
            matches_by_id[candidate.entity_id] = _EntityQueryMatch(
                entity_id=candidate.entity_id,
                entity_type=candidate.entity_type,
                score=max(score, previous.score) if previous is not None else score,
                explicit_names=frozenset(
                    explicit_names | (set(previous.explicit_names) if previous is not None else set())
                ),
            )
    matches = list(matches_by_id.values())
    if not matches:
        return [], "unresolved", "no entity candidate matched the query"
    explicit_set_ids = _explicit_entity_set_ids(
        matches,
        preferred_types=preferred_types,
        excluded_types=excluded_types,
    )
    if len(explicit_set_ids) > 1:
        return explicit_set_ids, "resolved", f"resolved explicit entity set {','.join(explicit_set_ids)}"
    best_score = max(match.score for match in matches)
    best_ids = sorted(match.entity_id for match in matches if match.score == best_score)
    if len(best_ids) > 1:
        return best_ids, "ambiguous", f"entity candidates tied at score {best_score}"
    return best_ids, "resolved", f"resolved entity {best_ids[0]}"


def _explicit_entity_set_ids(
    matches: list[_EntityQueryMatch],
    *,
    preferred_types: set[str],
    excluded_types: set[str],
) -> list[str]:
    eligible = [match for match in matches if match.entity_type not in excluded_types]
    name_owners: dict[str, set[str]] = {}
    type_owners: dict[str, set[str]] = {}
    for match in eligible:
        for name in match.explicit_names:
            name_owners.setdefault(name, set()).add(match.entity_id)
        if match.entity_type is not None:
            type_owners.setdefault(match.entity_type, set()).add(match.entity_id)
    explicit_ids = {
        match.entity_id
        for match in eligible
        if any(name_owners[name] == {match.entity_id} for name in match.explicit_names)
        or (
            match.entity_type in preferred_types
            and type_owners.get(match.entity_type) == {match.entity_id}
        )
    }
    return sorted(explicit_ids) if len(explicit_ids) > 1 else []


def _query_entity_type_constraints(query: str) -> tuple[set[str], set[str]]:
    """Resolve explicit English type contrasts for the fallback analyzer.

    This is deliberately limited to ontology labels already present in the
    production entity catalog. Non-English queries remain on the structured
    analyzer/caller contract instead of being transliterated heuristically.
    """

    entity_types = {item.value for item in EntityType if item != EntityType.UNKNOWN}
    preferred = {entity_type for entity_type in entity_types if contains_query_phrase(query, entity_type)}
    excluded: set[str] = set()
    for entity_type in preferred:
        escaped = re.escape(entity_type)
        if re.search(rf"\bnot\s+(?:the\s+)?{escaped}\b", query) or re.search(
            rf"\brather\s+than\s+(?:the\s+)?(?:\w+\s+)?{escaped}\b",
            query,
        ):
            excluded.add(entity_type)
    return preferred - excluded, excluded


def _entity_candidate_matches_query(
    candidate: TemporalEntityCandidate,
    *,
    temporal_kind: QueryTemporalKind,
    evaluation_time: datetime | None,
    valid_from: datetime | None,
    valid_to: datetime | None,
) -> bool:
    if temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        if candidate.lifecycle_state != RecordLifecycleState.ACTIVE:
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
