"""Evidence-backed semantic graph resolution for production retrieval."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from enum import StrEnum

from memorii.core.memory_evolution.graph_constraint_compilation import compile_graph_query
from memorii.core.memory_evolution.models import ClaimState, EntityLinkState
from memorii.core.memory_evolution.query_graph import (
    ExecutableGraphPattern,
    ExecutableObjectConstraint,
    GraphCompilationFailure,
    GraphCompilationFailureCode,
    GraphConstraintOperator,
    GraphPatternConstraint,
    GraphPatternFailureReason,
    GraphPatternResolution,
    GraphPatternResolutionStatus,
    GraphResolutionMethod,
    ResolvedEntityReference,
    UnresolvedEntityReference,
)
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryTemporalFrame,
    QueryTemporalKind,
    evaluate_temporal_eligibility,
)


class _ComparisonResult(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    UNKNOWN = "unknown"


def resolve_graph_constraints(
    *,
    query: str,
    analysis: QueryAnalysis,
    temporal_frame: QueryTemporalFrame,
    states: Iterable[ClaimState],
    entity_links: Iterable[EntityLinkState],
) -> GraphPatternResolution:
    """Compile and resolve a bounded conjunction against visible evidence."""

    state_list = list(states)
    link_list = list(entity_links)
    compiled = compile_graph_query(analysis)
    if isinstance(compiled, GraphCompilationFailure):
        return _compilation_failure_resolution(compiled)
    if compiled is None:
        return _resolve_unstructured_pattern(
            query=query,
            analysis=analysis,
            temporal_frame=temporal_frame,
            states=state_list,
            entity_links=link_list,
        )

    resolutions = [
        _execute_pattern(
            pattern=pattern,
            temporal_frame=temporal_frame,
            states=state_list,
            entity_links=link_list,
        )
        for pattern in compiled.patterns
    ]
    if len(resolutions) == 1:
        return resolutions[0]
    non_resolved = next(
        (
            item
            for item in resolutions
            if item.status != GraphPatternResolutionStatus.RESOLVED
            and item.failure_reasons != [GraphPatternFailureReason.MULTIPLE_SUBJECTS_MATCH]
        ),
        None,
    )
    if non_resolved is not None:
        return non_resolved.model_copy(
            update={"conjunctive_patterns": [item.source_pattern for item in compiled.patterns]}
        )
    common_subjects = set(resolutions[0].candidate_subject_entity_ids)
    for resolution in resolutions[1:]:
        common_subjects.intersection_update(resolution.candidate_subject_entity_ids)
    if len(common_subjects) != 1:
        reason = (
            GraphPatternFailureReason.CONJUNCTION_NO_COMMON_SUBJECT
            if not common_subjects
            else GraphPatternFailureReason.MULTIPLE_SUBJECTS_MATCH
        )
        return GraphPatternResolution(
            status=(
                GraphPatternResolutionStatus.NO_MATCH
                if not common_subjects
                else GraphPatternResolutionStatus.AMBIGUOUS
            ),
            resolution_method=GraphResolutionMethod.STRUCTURED_CONSTRAINT,
            pattern=compiled.patterns[0].source_pattern,
            conjunctive_patterns=[item.source_pattern for item in compiled.patterns],
            candidate_subject_entity_ids=sorted(common_subjects),
            ambiguity_reasons=[reason.value],
            failure_reasons=[reason],
        )

    subject_entity_id = next(iter(common_subjects))
    subject_by_claim_id = _subject_entity_by_claim(state_list, link_list)
    matched_claim_ids = sorted(
        {
            claim_id
            for item in resolutions
            for claim_id in item.matched_claim_ids
            if subject_by_claim_id.get(claim_id) == subject_entity_id
        }
    )
    matched_claim_id_set = set(matched_claim_ids)
    return GraphPatternResolution(
        status=GraphPatternResolutionStatus.RESOLVED,
        resolution_method=GraphResolutionMethod.STRUCTURED_CONSTRAINT,
        pattern=resolutions[0].pattern,
        conjunctive_patterns=[item.pattern for item in resolutions],
        subject_entity_id=subject_entity_id,
        matched_claim_ids=matched_claim_ids,
        supporting_source_ids=_source_ids(
            state for state in state_list if state.claim_id in matched_claim_id_set
        ),
        candidate_subject_entity_ids=[subject_entity_id],
    )


def resolve_graph_pattern(
    *,
    query: str,
    analysis: QueryAnalysis,
    temporal_frame: QueryTemporalFrame,
    states: Iterable[ClaimState],
    entity_links: Iterable[EntityLinkState],
) -> GraphPatternResolution:
    """Resolve one graph pattern through the same compile-before-execute path."""

    if len(analysis.graph_patterns) > 1:
        raise ValueError("resolve_graph_pattern accepts at most one structured pattern")
    return resolve_graph_constraints(
        query=query,
        analysis=analysis,
        temporal_frame=temporal_frame,
        states=states,
        entity_links=entity_links,
    )


def _execute_pattern(
    *,
    pattern: ExecutableGraphPattern,
    temporal_frame: QueryTemporalFrame,
    states: list[ClaimState],
    entity_links: list[EntityLinkState],
) -> GraphPatternResolution:
    if pattern.predicate_id is None:
        return _fall_back_to_subject_resolution(
            pattern=pattern.source_pattern,
            temporal_frame=temporal_frame,
            subject_entity_id=pattern.subject_entity_id,
            resolution_method=GraphResolutionMethod.STRUCTURED_CONSTRAINT,
        )

    entity_by_link_id = {link.link_id: link.canonical_entity_id for link in entity_links}
    subject_by_claim_id = _subject_entity_by_claim(states, entity_links)
    eligible = [
        state
        for state in states
        if state.claim_key.predicate_id == pattern.predicate_id
        and _state_matches_temporal_frame(state, temporal_frame)
        and (
            pattern.subject_entity_id is None
            or subject_by_claim_id[state.claim_id] == pattern.subject_entity_id
        )
    ]
    if pattern.subject_entity_id is not None and not eligible:
        return _failure_resolution(
            pattern.source_pattern,
            GraphPatternResolutionStatus.NO_MATCH,
            GraphPatternFailureReason.SUBJECT_CONSTRAINT_NO_MATCH,
        )

    matched: list[ClaimState] = []
    unknown: list[ClaimState] = []
    for state in eligible:
        comparison = _compare_object(
            state,
            constraint=pattern.object_constraint,
            entity_by_link_id=entity_by_link_id,
        )
        if comparison == _ComparisonResult.MATCH:
            matched.append(state)
        elif comparison == _ComparisonResult.UNKNOWN:
            unknown.append(state)
    if pattern.object_constraint is None:
        matched = eligible
    if unknown:
        return GraphPatternResolution(
            status=GraphPatternResolutionStatus.AMBIGUOUS,
            resolution_method=GraphResolutionMethod.STRUCTURED_CONSTRAINT,
            pattern=pattern.source_pattern,
            matched_claim_ids=sorted(state.claim_id for state in matched),
            supporting_source_ids=_source_ids(matched),
            candidate_subject_entity_ids=sorted(
                {subject_by_claim_id[state.claim_id] for state in [*matched, *unknown]}
            ),
            ambiguity_reasons=[GraphPatternFailureReason.OPEN_WORLD_COMPARISON_UNKNOWN.value],
            failure_reasons=[GraphPatternFailureReason.OPEN_WORLD_COMPARISON_UNKNOWN],
        )
    if pattern.object_constraint is not None and not matched:
        return _failure_resolution(
            pattern.source_pattern,
            GraphPatternResolutionStatus.NO_MATCH,
            GraphPatternFailureReason.OBJECT_CONSTRAINT_NO_MATCH,
        )

    candidate_subject_ids = sorted({subject_by_claim_id[state.claim_id] for state in matched})
    if len(candidate_subject_ids) != 1:
        reason = (
            GraphPatternFailureReason.MULTIPLE_SUBJECTS_MATCH
            if candidate_subject_ids
            else GraphPatternFailureReason.SUBJECT_CONSTRAINT_NO_MATCH
        )
        return GraphPatternResolution(
            status=(
                GraphPatternResolutionStatus.AMBIGUOUS
                if candidate_subject_ids
                else GraphPatternResolutionStatus.NO_MATCH
            ),
            resolution_method=GraphResolutionMethod.STRUCTURED_CONSTRAINT,
            pattern=pattern.source_pattern,
            matched_claim_ids=sorted(state.claim_id for state in matched),
            supporting_source_ids=_source_ids(matched),
            candidate_subject_entity_ids=candidate_subject_ids,
            ambiguity_reasons=[reason.value],
            failure_reasons=[reason],
        )

    subject_entity_id = candidate_subject_ids[0]
    resolved_pattern = pattern.source_pattern.model_copy(
        update={
            "subject": ResolvedEntityReference(
                entity_id=subject_entity_id,
                mention=pattern.source_pattern.subject.mention,
                expected_entity_types=pattern.source_pattern.subject.expected_entity_types,
            )
        }
    )
    return GraphPatternResolution(
        status=GraphPatternResolutionStatus.RESOLVED,
        resolution_method=GraphResolutionMethod.STRUCTURED_CONSTRAINT,
        pattern=resolved_pattern,
        subject_entity_id=subject_entity_id,
        matched_claim_ids=sorted(state.claim_id for state in matched),
        supporting_source_ids=_source_ids(matched),
        candidate_subject_entity_ids=[subject_entity_id],
    )


def _resolve_unstructured_pattern(
    *,
    query: str,
    analysis: QueryAnalysis,
    temporal_frame: QueryTemporalFrame,
    states: list[ClaimState],
    entity_links: list[EntityLinkState],
) -> GraphPatternResolution:
    """Conservative lexical fallback used only when no structured IR exists."""

    subject_entity_id = analysis.subject_entity_id
    pattern = GraphPatternConstraint(
        subject=(
            ResolvedEntityReference(entity_id=subject_entity_id)
            if subject_entity_id is not None
            else UnresolvedEntityReference()
        ),
        predicate_id=analysis.predicate_id,
    )
    if analysis.predicate_id is None:
        return _fall_back_to_subject_resolution(
            pattern=pattern,
            temporal_frame=temporal_frame,
            subject_entity_id=subject_entity_id,
            resolution_method=GraphResolutionMethod.SUBJECT_FRAME_FALLBACK,
        )

    entity_names = _entity_names(entity_links)
    entity_by_link_id = {link.link_id: link.canonical_entity_id for link in entity_links}
    subject_by_claim_id = _subject_entity_by_claim(states, entity_links)
    mentioned_entity_ids = {
        entity_id
        for entity_id, names in entity_names.items()
        if any(_contains_phrase(query, name) for name in names)
    }
    eligible = [
        state
        for state in states
        if state.claim_key.predicate_id == analysis.predicate_id
        and _state_matches_temporal_frame(state, temporal_frame)
    ]
    explicit_subjects = {subject_entity_id} if subject_entity_id is not None else set()
    if explicit_subjects:
        eligible = [
            state for state in eligible if subject_by_claim_id[state.claim_id] in explicit_subjects
        ]
    elif mentioned_entity_ids:
        evidence_counts = {
            state.claim_id: _participant_evidence_score(
                subject_entity_id=subject_by_claim_id[state.claim_id],
                object_entity_id=entity_by_link_id.get(state.object_link_id or ""),
                mentioned_entity_ids=mentioned_entity_ids,
                resolved_entity_ids=set(temporal_frame.resolved_entity_ids),
            )
            for state in eligible
        }
        maximum_evidence = max(evidence_counts.values(), default=0)
        eligible = [
            state
            for state in eligible
            if maximum_evidence > 0 and evidence_counts[state.claim_id] == maximum_evidence
        ]

    candidate_subject_ids = sorted({subject_by_claim_id[state.claim_id] for state in eligible})
    if len(candidate_subject_ids) != 1:
        reason = (
            GraphPatternFailureReason.MULTIPLE_SUBJECTS_MATCH
            if candidate_subject_ids
            else GraphPatternFailureReason.SUBJECT_CONSTRAINT_NO_MATCH
        )
        return GraphPatternResolution(
            status=(
                GraphPatternResolutionStatus.AMBIGUOUS
                if candidate_subject_ids
                else GraphPatternResolutionStatus.NO_MATCH
            ),
            resolution_method=GraphResolutionMethod.LEXICAL_PARTICIPANT_FALLBACK,
            pattern=pattern,
            candidate_subject_entity_ids=candidate_subject_ids,
            ambiguity_reasons=[reason.value],
            failure_reasons=[reason],
        )
    resolved_subject = candidate_subject_ids[0]
    return GraphPatternResolution(
        status=GraphPatternResolutionStatus.RESOLVED,
        resolution_method=GraphResolutionMethod.LEXICAL_PARTICIPANT_FALLBACK,
        pattern=pattern.model_copy(
            update={"subject": ResolvedEntityReference(entity_id=resolved_subject)}
        ),
        subject_entity_id=resolved_subject,
        matched_claim_ids=sorted(state.claim_id for state in eligible),
        supporting_source_ids=_source_ids(eligible),
        candidate_subject_entity_ids=[resolved_subject],
    )


def _participant_evidence_score(
    *,
    subject_entity_id: str,
    object_entity_id: str | None,
    mentioned_entity_ids: set[str],
    resolved_entity_ids: set[str],
) -> int:
    participants = {subject_entity_id}
    if object_entity_id is not None:
        participants.add(object_entity_id)
    lexical_evidence = len(participants & mentioned_entity_ids)
    analyzer_evidence = len(participants & resolved_entity_ids)
    return lexical_evidence + (2 * analyzer_evidence)


def _compare_object(
    state: ClaimState,
    *,
    constraint: ExecutableObjectConstraint | None,
    entity_by_link_id: dict[str, str],
) -> _ComparisonResult:
    if constraint is None:
        return _ComparisonResult.MATCH
    negative = constraint.operator in {
        GraphConstraintOperator.NOT_EQUALS,
        GraphConstraintOperator.NOT_IN,
    }
    if constraint.entity_ids:
        object_entity_id = entity_by_link_id.get(state.object_link_id or "")
        if object_entity_id is None:
            return _ComparisonResult.UNKNOWN
        equal = object_entity_id in set(constraint.entity_ids)
    else:
        if constraint.literal_value is None:
            return _ComparisonResult.UNKNOWN
        equal = _normalize(state.object_value) == _normalize(constraint.literal_value)
    matched = not equal if negative else equal
    return _ComparisonResult.MATCH if matched else _ComparisonResult.NO_MATCH


def _compilation_failure_resolution(failure: GraphCompilationFailure) -> GraphPatternResolution:
    reason = (
        GraphPatternFailureReason.UNRESOLVED_OBJECT_REFERENCE
        if failure.code == GraphCompilationFailureCode.UNRESOLVED_OBJECT
        else GraphPatternFailureReason.AMBIGUOUS_ENTITY_REFERENCE
    )
    return GraphPatternResolution(
        status=GraphPatternResolutionStatus.AMBIGUOUS,
        resolution_method=GraphResolutionMethod.STRUCTURED_CONSTRAINT,
        pattern=failure.pattern,
        ambiguity_reasons=[failure.rationale],
        failure_reasons=[reason],
    )


def _failure_resolution(
    pattern: GraphPatternConstraint,
    status: GraphPatternResolutionStatus,
    reason: GraphPatternFailureReason,
) -> GraphPatternResolution:
    return GraphPatternResolution(
        status=status,
        resolution_method=GraphResolutionMethod.STRUCTURED_CONSTRAINT,
        pattern=pattern,
        ambiguity_reasons=[reason.value],
        failure_reasons=[reason],
    )


def _fall_back_to_subject_resolution(
    *,
    pattern: GraphPatternConstraint,
    temporal_frame: QueryTemporalFrame,
    subject_entity_id: str | None,
    resolution_method: GraphResolutionMethod,
) -> GraphPatternResolution:
    subject_ids = ({subject_entity_id} if subject_entity_id is not None else set()) or set(
        temporal_frame.resolved_entity_ids
    )
    if len(subject_ids) == 1:
        resolved = next(iter(subject_ids))
        return GraphPatternResolution(
            status=GraphPatternResolutionStatus.RESOLVED,
            resolution_method=resolution_method,
            pattern=pattern.model_copy(
                update={"subject": ResolvedEntityReference(entity_id=resolved)}
            ),
            subject_entity_id=resolved,
            candidate_subject_entity_ids=[resolved],
        )
    return GraphPatternResolution(
        status=(
            GraphPatternResolutionStatus.AMBIGUOUS
            if len(subject_ids) > 1
            else GraphPatternResolutionStatus.NO_MATCH
        ),
        resolution_method=resolution_method,
        pattern=pattern,
        candidate_subject_entity_ids=sorted(subject_ids),
        ambiguity_reasons=[GraphPatternFailureReason.QUERY_SUBJECT_UNRESOLVED.value],
        failure_reasons=[GraphPatternFailureReason.QUERY_SUBJECT_UNRESOLVED],
    )


def _subject_entity_by_claim(
    states: Iterable[ClaimState],
    links: Iterable[EntityLinkState],
) -> dict[str, str]:
    entity_by_link_id = {link.link_id: link.canonical_entity_id for link in links}
    return {
        state.claim_id: entity_by_link_id.get(
            state.subject_link_id or "",
            state.claim_key.subject_entity_id,
        )
        for state in states
    }


def _source_ids(states: Iterable[ClaimState]) -> list[str]:
    return sorted({span.source_id for state in states for span in state.evidence_spans})


def _state_matches_temporal_frame(state: ClaimState, frame: QueryTemporalFrame) -> bool:
    if frame.temporal_kind in {
        QueryTemporalKind.CURRENT,
        QueryTemporalKind.EXECUTION,
        QueryTemporalKind.BELIEF,
    }:
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


def _entity_names(links: Iterable[EntityLinkState]) -> dict[str, set[str]]:
    names: dict[str, set[str]] = {}
    for link in links:
        names.setdefault(link.canonical_entity_id, set()).update(
            name for name in {link.mention_text, link.normalized_name, *link.aliases} if name.strip()
        )
    return names


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)", normalized_text) is not None


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())
