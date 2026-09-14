"""One-snapshot, authority-filtered scoped context assembly."""

from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError

from memorii.core.memory_evolution.claim_queries import ClaimStateQueryService
from memorii.core.memory_evolution.models import ClaimState, EntityLinkState, MemoryScope, RetrievalView
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.query_analysis import EnglishLexicalQueryAnalyzer
from memorii.core.memory_evolution.query_graph import GraphPatternResolutionStatus
from memorii.core.memory_evolution.retrieval_contracts import RetrievalPurpose
from memorii.core.memory_evolution.retrieval_runtime import MemoryEvolutionRetrievalRuntime
from memorii.core.memory_evolution.state_repository import EvolutionStateRepository
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryTemporalKind,
    TemporalAnchorCatalog,
    TemporalEntityCandidate,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.bm25 import BM25Scorer
from memorii.core.scoped_context.authority import ResolvedScopedReadGrant
from memorii.core.scoped_context.contracts import (
    ScopedContextActivation,
    ScopedContextChannel,
    ScopedContextItem,
    ScopedContextOmission,
    ScopedContextRequest,
    ScopedContextStatus,
    ScopedOmissionReason,
    ScopedStructuredOutcome,
)
from memorii.core.scoped_context.index import ScopedContextIndex
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility, TemporalValidityStatus


class ScopedSnapshotBackendError(RuntimeError):
    pass


class ScopedSnapshotDecodeError(RuntimeError):
    pass


class ScopedOptionalScorerError(RuntimeError):
    pass


class ScopedStructuredDependencyError(RuntimeError):
    pass


class ScopedUnsupportedQueryError(RuntimeError):
    pass


class ScopedClaimQueryAnalyzer:
    """Keep v1 structured reads on the local answer-only branch."""

    def __init__(self) -> None:
        self._delegate = EnglishLexicalQueryAnalyzer()

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
        analysis = self._delegate.analyze(
            query=query,
            language=language,
            reference_time=reference_time,
            entity_candidates=entity_candidates,
            anchor_catalog=anchor_catalog,
            request_scope=request_scope,
        )
        frame = analysis.temporal_frame
        if frame is not None and frame.temporal_kind in {
            QueryTemporalKind.EXECUTION,
            QueryTemporalKind.BELIEF,
        }:
            raise ScopedUnsupportedQueryError("scoped context does not support execution or belief queries")
        return analysis


class ScopedContextAssembler:
    def assemble(
        self,
        *,
        request: ScopedContextRequest,
        revision: int,
        records: tuple[CanonicalMemoryRecord, ...],
        grant: ResolvedScopedReadGrant,
    ) -> ScopedContextActivation:
        authorized, source_provenance_missing = _provenance_closed_records(records, grant)
        for record in authorized:
            if record.content.get("memory_evolution_kind") in {
                "claim_state", "entity_link", "temporal_anchor", "action",
            }:
                _decode_owned(record)
        eligible, lifecycle_missing = _current_provenance_closed_records(authorized, request.reference_time)
        lexical_provenance_missing = tuple(sorted(set(source_provenance_missing) | set(lifecycle_missing)))
        by_id = {record.memory_id: record for record in eligible}
        mandatory_records = [by_id.get(ref.record_id) for ref in request.mandatory_record_references]
        if any(record is None for record in mandatory_records):
            return _empty(ScopedContextStatus.MANDATORY_UNRESOLVED)
        mandatory = tuple(
            _item(record, ScopedContextChannel.MANDATORY) for record in mandatory_records if record is not None
        )
        if (
            len(mandatory) > request.budget.max_mandatory_items
            or _bytes(mandatory) > request.budget.max_rendered_utf8_bytes
        ):
            return _empty(ScopedContextStatus.MANDATORY_OVERFLOW)
        optional: list[ScopedContextItem] = []
        omissions: list[ScopedContextOmission] = []
        remaining = request.budget.max_rendered_utf8_bytes - _bytes(mandatory)
        self._assemble_lexical(
            request, eligible, {item.record_id for item in mandatory}, remaining, optional, omissions
        )
        missing_optional = tuple(
            record_id for record_id in lexical_provenance_missing
            if any(record.memory_id == record_id and record.domain in request.optional_domains for record in records)
        )
        if missing_optional:
            omissions.append(_omission(
                ScopedContextChannel.SEMANTIC_BM25,
                ScopedOmissionReason.PROVENANCE_UNAVAILABLE,
                missing_optional,
                request.budget.max_optional_omission_ids,
            ))
        structured_outcome = None
        if request.structured_query is not None:
            structured_excluded = tuple(
                record_id
                for record_id in source_provenance_missing
                if any(
                    record.memory_id == record_id
                    and record.content.get("memory_evolution_kind") in {"claim_state", "entity_link", "temporal_anchor", "action"}
                    for record in records
                )
            )
            structured_outcome = self._assemble_structured(
                request, authorized, structured_excluded, remaining - _bytes(tuple(optional)), optional, omissions
            )
        return ScopedContextActivation.model_construct(
            status=ScopedContextStatus.PARTIAL_OPTIONAL if omissions else ScopedContextStatus.COMPLETE,
            request_task_id=request.host_task_id,
            request_state_id=request.host_state_id,
            authority_binding_receipt=None,
            memory_snapshot_revision=revision,
            mandatory_items=mandatory,
            optional_items=tuple(optional),
            omissions=tuple(omissions),
            structured_outcome=structured_outcome,
        )

    def _assemble_lexical(
        self,
        request: ScopedContextRequest,
        eligible: tuple[CanonicalMemoryRecord, ...],
        selected_ids: set[str],
        remaining: int,
        optional: list[ScopedContextItem],
        omissions: list[ScopedContextOmission],
    ) -> None:
        if request.optional_query is None or not request.optional_query.strip():
            omissions.append(
                _omission(
                    ScopedContextChannel.SEMANTIC_BM25,
                    ScopedOmissionReason.EMPTY_QUERY,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return
        candidates = tuple(record for record in eligible if record.domain in request.optional_domains)
        try:
            ranked = ScopedContextIndex(candidates, BM25Scorer()).rank(request.optional_query)
        except ScopedOptionalScorerError:
            omissions.append(
                _omission(
                    ScopedContextChannel.SEMANTIC_BM25,
                    ScopedOmissionReason.SCORER_UNAVAILABLE,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return
        rejected: list[str] = []
        byte_limited = False
        for record in ranked:
            if record.memory_id in selected_ids:
                continue
            item = _item(record, _channel(record))
            if len(optional) >= request.budget.max_optional_items:
                rejected.append(record.memory_id)
            elif _bytes(tuple(optional) + (item,)) > remaining:
                byte_limited = True
                rejected.append(record.memory_id)
            else:
                optional.append(item)
                selected_ids.add(record.memory_id)
        if rejected:
            reason = ScopedOmissionReason.RENDERED_BYTE_LIMIT if byte_limited else ScopedOmissionReason.OPTIONAL_LIMIT
            omissions.append(
                _omission(
                    ScopedContextChannel.SEMANTIC_BM25,
                    reason,
                    tuple(rejected),
                    request.budget.max_optional_omission_ids,
                )
            )
        elif not ranked:
            omissions.append(
                _omission(
                    ScopedContextChannel.SEMANTIC_BM25,
                    ScopedOmissionReason.NO_MATCH,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )

    def _assemble_structured(
        self,
        request: ScopedContextRequest,
        eligible: tuple[CanonicalMemoryRecord, ...],
        provenance_excluded: tuple[str, ...],
        remaining: int,
        optional: list[ScopedContextItem],
        omissions: list[ScopedContextOmission],
    ) -> ScopedStructuredOutcome | None:
        query = request.structured_query
        assert query is not None
        if query.purpose != RetrievalPurpose.ANSWER:
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.STRUCTURED_UNSUPPORTED_QUERY,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return None
        eligible, lifecycle_excluded = _structured_eligible_records(eligible, request.reference_time)
        excluded = tuple(sorted(set(provenance_excluded) | set(lifecycle_excluded)))
        if excluded:
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.PROVENANCE_UNAVAILABLE,
                    excluded,
                    request.budget.max_optional_omission_ids,
                )
            )
        try:
            _validate_unique_claim_ids(eligible)
            repository = EvolutionStateRepository.from_snapshot(eligible)
            claims = ClaimStateQueryService(repository=repository, now_provider=lambda: request.reference_time)
            anchors = TemporalAnchorCatalog()
            repository.hydrate_temporal_anchors(anchors)
            runtime = MemoryEvolutionRetrievalRuntime(
                claim_reader=claims.retrieve,
                entity_link_reader=repository.list_entity_links,
                action_reader=repository.list_actions,
                query_analyzer=ScopedClaimQueryAnalyzer(),
                temporal_anchor_catalog=anchors,
                now_provider=lambda: request.reference_time,
                predicate_registry=PredicateRegistry(),
            )
            decision = runtime.retrieve(query.model_copy(update={"reference_time": request.reference_time}))
        except ScopedUnsupportedQueryError:
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.STRUCTURED_UNSUPPORTED_QUERY,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return None
        except (ValidationError, KeyError) as exc:
            raise ScopedSnapshotDecodeError() from exc
        except ScopedStructuredDependencyError:
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.STRUCTURED_UNAVAILABLE,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return None
        if decision.abstained and (
            decision.abstention_reason == "no_lifecycle_valid_match"
            or (
                decision.graph_pattern_resolution is not None
                and decision.graph_pattern_resolution.status == GraphPatternResolutionStatus.NO_MATCH
            )
        ):
            outcome = ScopedStructuredOutcome(status="no_match", claim_items=(), evidence_items=())
            omissions.append(_omission(ScopedContextChannel.STRUCTURED_GRAPH, ScopedOmissionReason.STRUCTURED_NO_MATCH, (), request.budget.max_optional_omission_ids))
            return outcome
        if decision.abstained:
            outcome = ScopedStructuredOutcome(
                status="abstained",
                claim_items=(),
                evidence_items=(),
                abstention_reason=decision.abstention_reason or "structured abstention",
            )
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.STRUCTURED_ABSTAINED,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return outcome
        if not decision.selected_record_ids:
            outcome = ScopedStructuredOutcome(status="no_match", claim_items=(), evidence_items=())
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.STRUCTURED_NO_MATCH,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return outcome
        claim_records_in_snapshot = [
            record for record in eligible if record.content.get("memory_evolution_kind") == "claim_state"
        ]
        by_claim = {
            _claim_id(record): record
            for record in claim_records_in_snapshot
        }
        by_id = {record.memory_id: record for record in eligible}
        claim_records = [by_claim.get(claim_id) for claim_id in decision.selected_record_ids]
        evidence_ids = sorted({item.source_id for item in decision.evidence})
        # Claim state evidence is authoritative even when the ranking decision
        # carries a reduced citation view.
        for record in claim_records:
            if record is not None:
                evidence_ids.extend(_source_closure_ids(record, by_id))
        selected_record_ids = {record.memory_id for record in claim_records if record is not None}
        evidence_records = [by_id.get(record_id) for record_id in sorted(set(evidence_ids) - selected_record_ids)]
        if any(item is None for item in claim_records + evidence_records):
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.PROVENANCE_UNAVAILABLE,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return None
        claim_items = tuple(
            _item(record, ScopedContextChannel.STRUCTURED_GRAPH)
            for record in sorted((item for item in claim_records if item), key=lambda item: item.memory_id)
        )
        evidence_items = tuple(
            _item(record, ScopedContextChannel.STRUCTURED_GRAPH)
            for record in sorted((item for item in evidence_records if item), key=lambda item: item.memory_id)
        )
        unit = claim_items + evidence_items
        if len(optional) + len(unit) > request.budget.max_optional_items:
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.OPTIONAL_LIMIT,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return None
        if _bytes(unit) > remaining:
            omissions.append(
                _omission(
                    ScopedContextChannel.STRUCTURED_GRAPH,
                    ScopedOmissionReason.RENDERED_BYTE_LIMIT,
                    (),
                    request.budget.max_optional_omission_ids,
                )
            )
            return None
        return ScopedStructuredOutcome(status="answered", claim_items=claim_items, evidence_items=evidence_items)


def _decode_owned(record: CanonicalMemoryRecord) -> None:
    try:
        repository = EvolutionStateRepository.from_snapshot((record,))
        kind = record.content["memory_evolution_kind"]
        if kind == "claim_state":
            ClaimState.model_validate(record.content["claim_state"])
            repository.list_claim_states()
        elif kind == "entity_link":
            EntityLinkState.model_validate(record.content["entity_link"])
            repository.list_entity_links()
        elif kind == "temporal_anchor":
            repository.hydrate_temporal_anchors(TemporalAnchorCatalog())
        elif kind == "action":
            repository.list_actions()
    except (ValidationError, KeyError, TypeError) as exc:
        raise ScopedSnapshotDecodeError() from exc


def _claim_id(record: CanonicalMemoryRecord) -> str | None:
    state = record.content.get("claim_state")
    return state.get("claim_id") if isinstance(state, dict) and isinstance(state.get("claim_id"), str) else None


def _authorized(record: CanonicalMemoryRecord, grant: ResolvedScopedReadGrant) -> bool:
    return (
        _matches_grant(record, grant)
        and record.status == CommitStatus.COMMITTED
        and record.visibility == MemoryRecordVisibility.RUNTIME_CONTEXT
    )


def _provenance_closed_records(
    records: tuple[CanonicalMemoryRecord, ...], grant: ResolvedScopedReadGrant
) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[str, ...]]:
    """Retain only records whose complete declared source closure is readable."""
    candidates = {record.memory_id: record for record in records if _authorized(record, grant)}
    if len(candidates) != len([record for record in records if _authorized(record, grant)]):
        raise ScopedSnapshotDecodeError("duplicate canonical record ID")
    allowed = set(candidates)
    changed = True
    while changed:
        changed = False
        for record_id in tuple(allowed):
            record = candidates[record_id]
            if not _inner_scope_agrees(record) or not _source_ids(record).issubset(allowed):
                allowed.remove(record_id)
                changed = True
    return (
        tuple(record for record in records if record.memory_id in allowed),
        tuple(sorted(set(candidates) - allowed)),
    )


def _source_closure_ids(record: CanonicalMemoryRecord, by_id: dict[str, CanonicalMemoryRecord]) -> set[str]:
    """Return every authorized transitive source required to reconstruct a record."""
    closed: set[str] = set()
    pending = list(_source_ids(record))
    while pending:
        record_id = pending.pop()
        if record_id in closed:
            continue
        closed.add(record_id)
        source = by_id.get(record_id)
        if source is not None:
            pending.extend(_source_ids(source) - closed)
    return closed


def _current_provenance_closed_records(
    records: tuple[CanonicalMemoryRecord, ...], reference_time: datetime
) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[str, ...]]:
    """Apply lifecycle eligibility to every mandatory or lexical source closure."""
    by_id = {record.memory_id: record for record in records}
    allowed = {record.memory_id for record in records if _current_eligible(record, reference_time)}
    changed = True
    while changed:
        changed = False
        for record_id in tuple(allowed):
            sources = _source_ids(by_id[record_id])
            if (by_id[record_id].content.get("memory_evolution_kind") in {"claim_state", "entity_link"} and not sources) or not sources.issubset(allowed):
                allowed.remove(record_id)
                changed = True
    return tuple(record for record in records if record.memory_id in allowed), tuple(sorted(set(by_id) - allowed))


def _structured_eligible_records(
    records: tuple[CanonicalMemoryRecord, ...], reference_time: datetime
) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[str, ...]]:
    """Keep historical claim candidates while requiring current readable dependencies."""
    by_id = {record.memory_id: record for record in records}
    typed_candidates = {"claim_state", "entity_link", "temporal_anchor", "action"}
    current_records, _ = _current_provenance_closed_records(records, reference_time)
    current = {record.memory_id for record in current_records}
    allowed = set(current)
    for record in records:
        kind = record.content.get("memory_evolution_kind")
        if kind in typed_candidates:
            sources = _source_ids(record)
            if (
                (kind not in {"claim_state", "entity_link"} or bool(sources))
                and sources.issubset(current)
            ):
                allowed.add(record.memory_id)
    return (
        tuple(record for record in records if record.memory_id in allowed),
        tuple(sorted(set(by_id) - allowed)),
    )


def _validate_unique_claim_ids(records: tuple[CanonicalMemoryRecord, ...]) -> None:
    claim_ids = [
        _claim_id(record)
        for record in records
        if record.content.get("memory_evolution_kind") == "claim_state"
    ]
    if any(claim_id is None for claim_id in claim_ids) or len(claim_ids) != len(set(claim_ids)):
        raise ScopedSnapshotDecodeError("invalid or duplicate logical claim ID")


def _source_ids(record: CanonicalMemoryRecord) -> set[str]:
    ids = set(record.source_record_ids)
    kind = record.content.get("memory_evolution_kind")
    key = kind if kind in {"claim_state", "entity_link", "temporal_anchor"} else ""
    payload = record.content.get(key)
    if isinstance(payload, dict):
        evidence_values = payload.get("evidence_spans", payload.get("evidence", []))
        if isinstance(evidence_values, (list, tuple)):
            for evidence in evidence_values:
                if isinstance(evidence, dict) and isinstance(evidence.get("source_id"), str):
                    ids.add(evidence["source_id"])
        if kind == "temporal_anchor":
            source_values = payload.get("source_ids", [])
            if isinstance(source_values, (list, tuple)):
                ids.update(value for value in source_values if isinstance(value, str))
    return ids


def _inner_scope_agrees(record: CanonicalMemoryRecord) -> bool:
    kind = record.content.get("memory_evolution_kind")
    key = kind if kind in {"claim_state", "entity_link", "temporal_anchor"} else ""
    payload = record.content.get(key)
    if not isinstance(payload, dict):
        return True
    if kind == "claim_state":
        if "claim_key" not in payload or not isinstance(payload["claim_key"], dict):
            return True
        scope = payload["claim_key"].get("scope", {})
    else:
        scope = payload.get("scope", {})
    if not isinstance(scope, dict):
        return True
    return all(scope.get(field) == getattr(record, field) for field in ("task_id", "session_id", "user_id"))


def _current_eligible(record: CanonicalMemoryRecord, reference_time: datetime) -> bool:
    if record.validity_status in {TemporalValidityStatus.EXPIRED, TemporalValidityStatus.INVALIDATED}:
        return False
    if (
        record.valid_from is not None
        and record.valid_from > reference_time
        or record.valid_to is not None
        and record.valid_to <= reference_time
    ):
        return False
    if record.content.get("memory_evolution_kind") == "claim_state":
        repository = EvolutionStateRepository.from_snapshot((record,))
        return bool(
            ClaimStateQueryService(repository=repository, now_provider=lambda: reference_time).retrieve(
                view=RetrievalView.CURRENT
            )
        )
    if record.content.get("memory_evolution_kind") == "entity_link":
        repository = EvolutionStateRepository.from_snapshot((record,))
        links = repository.list_entity_links()
        if not links or links[0].lifecycle_state.value in {"invalidated", "expired"}:
            return False
        link = links[0]
        return not (
            (link.valid_from is not None and link.valid_from > reference_time)
            or (link.valid_to is not None and link.valid_to <= reference_time)
        )
    # Unbounded generic projections are not current evidence.  Raw transcript
    # and committed plain context are the two canonical exceptions.
    return not (
        record.valid_from is None
        and record.domain is not MemoryDomain.TRANSCRIPT
        and (
            record.status is not CommitStatus.COMMITTED
            or record.content.get("memory_evolution_kind") is not None
        )
    )


def _matches_grant(record: CanonicalMemoryRecord, grant: ResolvedScopedReadGrant) -> bool:
    fields = ("task_id", "session_id", "user_id", "agent_id", "execution_node_id", "solver_run_id")
    return any(
        row.domain == record.domain
        and (row.allowed_record_ids is None or record.memory_id in row.allowed_record_ids)
        and all(getattr(row, field) == getattr(record, field) for field in fields)
        for row in grant.rows
    )


def _channel(record: CanonicalMemoryRecord) -> ScopedContextChannel:
    return (
        ScopedContextChannel.SEMANTIC_BM25
        if record.domain == MemoryDomain.SEMANTIC
        else ScopedContextChannel.EPISODIC_BM25
    )


def _item(record: CanonicalMemoryRecord, channel: ScopedContextChannel) -> ScopedContextItem:
    provenance = record.content.get("provenance_ref")
    return ScopedContextItem(
        channel=channel,
        record_id=record.memory_id,
        domain=record.domain,
        source_kind=record.source_kind,
        rendered_text=record.text,
        source_record_ids=tuple(sorted(_source_ids(record))),
        provenance_ref=provenance if isinstance(provenance, str) else None,
    )


def _bytes(items: tuple[ScopedContextItem, ...]) -> int:
    return sum(
        sum(
            len(value.encode("utf-8"))
            for value in (
                item.rendered_text,
                item.record_id,
                item.domain.value,
                item.source_kind,
                *item.source_record_ids,
                *((item.provenance_ref,) if item.provenance_ref else ()),
            )
        )
        for item in items
    )


def _omission(
    channel: ScopedContextChannel, reason: ScopedOmissionReason, ids: tuple[str, ...], cap: int
) -> ScopedContextOmission:
    return ScopedContextOmission(
        channel=channel,
        reason=reason,
        omitted_count=len(ids),
        omitted_record_ids=ids[:cap],
        identifiers_truncated=len(ids) > cap,
    )


def _empty(status: ScopedContextStatus) -> ScopedContextActivation:
    return ScopedContextActivation(
        status=status,
        request_task_id=None,
        request_state_id=None,
        authority_binding_receipt=None,
        memory_snapshot_revision=None,
        mandatory_items=(),
        optional_items=(),
        omissions=(),
        structured_outcome=None,
    )
