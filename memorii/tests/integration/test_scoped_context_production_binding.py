import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

import pytest
from memorii.core.filesystem_storage.bundle import FilesystemStorageBundle
from memorii.core.memory_evolution import MemoryEvolutionService
from memorii.core.memory_evolution.claim_queries import ClaimStateQueryService
from memorii.core.memory_evolution.models import (
    ClaimAssertionMode,
    ClaimEpistemicStatus,
    ClaimKey,
    ClaimLifecycleState,
    ClaimModality,
    ClaimPolarity,
    ClaimSemanticContext,
    ClaimState,
    ConfidenceComponents,
    EntityLinkLifecycleState,
    EntityLinkState,
    EvidenceSpan,
    MemoryScope,
)
from memorii.core.memory_evolution.query_analysis import EnglishLexicalQueryAnalyzer
from memorii.core.memory_evolution.query_graph import GraphPatternConstraint, ResolvedEntityReference
from memorii.core.memory_evolution.record_projection import (
    record_from_claim_state,
    record_from_entity_link,
    record_from_temporal_anchor,
)
from memorii.core.memory_evolution.retrieval_contracts import MemoryQueryRequest, RetrievalPurpose
from memorii.core.memory_evolution.retrieval_runtime import MemoryEvolutionRetrievalRuntime
from memorii.core.memory_evolution.state_repository import EvolutionStateRepository
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryScopeKind,
    QueryTemporalFrame,
    QueryTemporalKind,
    TemporalAnchor,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority, ScopedNamespaceGrantRow
from memorii.core.scoped_context.contracts import ScopedContextBudget, ScopedContextRequest, ScopedRecordReference
from memorii.core.scoped_context.index import ScopedContextIndex
from memorii.core.scoped_context.service import (
    ScopedOptionalScorerError,
    ScopedSnapshotBackendError,
    ScopedSnapshotDecodeError,
    ScopedStructuredDependencyError,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, SourceType, TemporalValidityStatus
from memorii.integrations.hermes_provider import HermesMemoryProvider


def _request() -> ScopedContextRequest:
    return ScopedContextRequest(host_task_id="task", host_state_id="state", declared_complete_mandatory_set=True, mandatory_record_references=(ScopedRecordReference(record_id="semantic:one", purpose="state"),), optional_query=None, optional_domains=(), budget=ScopedContextBudget(max_mandatory_items=1, max_optional_items=1, max_optional_omission_ids=1, max_rendered_utf8_bytes=1000), reference_time=datetime(2026, 1, 1, tzinfo=UTC))


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_forward_scoped_authority(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    record = CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test")
    if root == "filesystem":
        bundle = FilesystemStorageBundle.from_root(tmp_path / "store")
        bundle.memory_plane_store.write_records((record,))
        provider = bundle.build_provider_memory_service(scoped_read_authority=authority)
    else:
        plane = MemoryPlaneService()
        plane.write_records((record,))
        provider = HermesMemoryProvider(memory_plane=plane, scoped_read_authority=authority)
    result = provider.retrieve_context(_request(), opaque_host_ingress=handle)
    assert result.status.value == "partial_optional"
    assert result.authority_binding_receipt is not None


def _analysis(kind: QueryTemporalKind, now: datetime) -> QueryAnalysis:
    frame_fields: dict[str, object] = {"temporal_kind": kind}
    if kind is QueryTemporalKind.HISTORICAL:
        frame_fields["valid_from"] = now - timedelta(days=2)
    elif kind is QueryTemporalKind.INTERVAL:
        frame_fields["valid_from"] = now - timedelta(days=2)
        frame_fields["valid_to"] = now - timedelta(days=1)
    elif kind is QueryTemporalKind.AMBIGUOUS:
        frame_fields["resolution_confidence"] = 0.0
        frame_fields["ambiguity_reasons"] = ["ambiguous"]
    return QueryAnalysis(temporal_frame=QueryTemporalFrame(**frame_fields), temporal_intent=kind)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("purpose", tuple(RetrievalPurpose))
@pytest.mark.parametrize("kind", tuple(QueryTemporalKind))
def test_real_roots_admit_only_answer_temporal_queries_without_execution_dispatch(
    root: str, purpose: RetrievalPurpose, kind: QueryTemporalKind, tmp_path, monkeypatch
) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task", host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    record = CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test")
    if root == "filesystem":
        bundle = FilesystemStorageBundle.from_root(tmp_path / "store")
        bundle.memory_plane_store.write_records((record,))
        provider = bundle.build_provider_memory_service(scoped_read_authority=authority)
    else:
        plane = MemoryPlaneService()
        plane.write_records((record,))
        provider = HermesMemoryProvider(memory_plane=plane, scoped_read_authority=authority)

    analysis_calls = 0
    execution_calls = 0
    def injected_analysis(self, **kwargs):
        nonlocal analysis_calls
        analysis_calls += 1
        return _analysis(kind, now)
    def fail_execution(self, **kwargs):
        nonlocal execution_calls
        execution_calls += 1
        raise AssertionError("scoped context must never dispatch execution retrieval")
    monkeypatch.setattr(EnglishLexicalQueryAnalyzer, "analyze", injected_analysis)
    monkeypatch.setattr(MemoryEvolutionRetrievalRuntime, "_retrieve_execution_decision", fail_execution)

    request = _request().model_copy(update={
        "reference_time": now,
        "structured_query": MemoryQueryRequest(query="value", purpose=purpose, reference_time=now),
    })
    result = provider.retrieve_context(request, opaque_host_ingress=handle)
    assert execution_calls == 0
    if purpose is not RetrievalPurpose.ANSWER:
        assert analysis_calls == 0
        assert any(item.reason.value == "structured_unsupported_query" for item in result.omissions)
    elif kind in {QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        assert analysis_calls == 1
        assert any(item.reason.value == "structured_unsupported_query" for item in result.omissions)
    elif kind is QueryTemporalKind.AMBIGUOUS:
        assert analysis_calls == 1
        assert result.structured_outcome is not None
        assert result.structured_outcome.status == "abstained"
    else:
        assert analysis_calls == 1
        assert result.structured_outcome is not None
        assert result.structured_outcome.status == "no_match"


def _root_with_record(root: str, tmp_path, authority):
    record = CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test")
    if root == "filesystem":
        bundle = FilesystemStorageBundle.from_root(tmp_path / "store")
        bundle.memory_plane_store.write_records((record,))
        return bundle.build_provider_memory_service(scoped_read_authority=authority), bundle.memory_plane_store
    plane = MemoryPlaneService()
    plane.write_records((record,))
    return HermesMemoryProvider(memory_plane=plane, scoped_read_authority=authority), plane


def _provider_with_records(root: str, tmp_path, authority, records: tuple[CanonicalMemoryRecord, ...]):
    if root == "filesystem":
        bundle = FilesystemStorageBundle.from_root(tmp_path / "store")
        bundle.memory_plane_store.write_records(records)
        return bundle.build_provider_memory_service(scoped_read_authority=authority)
    plane = MemoryPlaneService()
    plane.write_records(records)
    return HermesMemoryProvider(memory_plane=plane, scoped_read_authority=authority)


def _all_record_grant(authority, records: tuple[CanonicalMemoryRecord, ...], now: datetime):
    return authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=tuple(
            ScopedNamespaceGrantRow(
                domain=domain,
                task_id="task" if any(record.task_id == "task" and record.domain == domain for record in records) else None,
                allowed_record_ids=frozenset(record.memory_id for record in records if record.domain == domain),
            )
            for domain in {record.domain for record in records}
        ),
        expires_at=now + timedelta(minutes=1),
    )


def _raw_source(memory_id: str, now: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text="raw source",
        content={"text": "raw source"},
        status=CommitStatus.COMMITTED,
        task_id="task",
        source_kind="user",
        timestamp=now,
        is_raw_event=True,
    )


def _typed_link(*, now: datetime, lifecycle_state: EntityLinkLifecycleState, valid_to: datetime | None = None, evidence_ids: tuple[str, ...] = ()) -> EntityLinkState:
    return EntityLinkState(
        link_id="link:atlas",
        mention_text="Atlas",
        canonical_entity_id="entity:atlas",
        normalized_name="atlas",
        confidence=1.0,
        scope=MemoryScope(task_id="task"),
        lifecycle_state=lifecycle_state,
        valid_to=valid_to,
        evidence_spans=[
            EvidenceSpan(source_id=source_id, quote="raw", source_type=SourceType.USER, timestamp=now)
            for source_id in evidence_ids
        ],
    )


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize(
    ("lifecycle_state", "valid_to"),
    ((EntityLinkLifecycleState.INVALIDATED, None), (EntityLinkLifecycleState.ACTIVE, datetime(2026, 1, 2, tzinfo=UTC))),
)
def test_real_roots_exclude_invalidated_and_boundary_expired_typed_entity_links(
    root: str, lifecycle_state: EntityLinkLifecycleState, valid_to: datetime | None, tmp_path
) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    source = _raw_source("raw:source", now)
    link = _typed_link(now=now, lifecycle_state=lifecycle_state, valid_to=valid_to, evidence_ids=(source.memory_id,))
    link_record = CanonicalMemoryRecord(
        memory_id="semantic:one",
        domain=MemoryDomain.SEMANTIC,
        text="Atlas",
        content={"memory_evolution_kind": "entity_link", "entity_link": link.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        task_id="task",
        source_kind="memory_evolution",
    )
    records = (source, link_record)
    handle = _all_record_grant(authority, records, now)
    provider = _provider_with_records(root, tmp_path, authority, records)
    assert provider.retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle).status.value == "mandatory_unresolved"
    optional = provider.retrieve_context(
        _request().model_copy(update={"mandatory_record_references": (), "optional_query": "Atlas", "optional_domains": (MemoryDomain.SEMANTIC,), "reference_time": now}),
        opaque_host_ingress=handle,
    )
    assert any(omission.reason.value == "provenance_unavailable" for omission in optional.omissions)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_require_active_claim_provenance_for_mandatory_and_optional(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    claim = ClaimState(
        claim_id="claim:ungrounded",
        claim_key=ClaimKey(subject_entity_id="entity:atlas", predicate_id="owner", scope=MemoryScope(task_id="task")),
        object_value="Alice",
        lifecycle_state=ClaimLifecycleState.ACTIVE,
        source_claim_id="claim:ungrounded",
        confidence=ConfidenceComponents(extraction=1.0, evidence=1.0, source_trust=1.0, calibrated=1.0),
    )
    record = CanonicalMemoryRecord(
        memory_id="semantic:one",
        domain=MemoryDomain.SEMANTIC,
        text="Atlas owner Alice",
        content={"memory_evolution_kind": "claim_state", "claim_state": claim.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        task_id="task",
        source_kind="memory_evolution",
    )
    handle = _all_record_grant(authority, (record,), now)
    provider = _provider_with_records(root, tmp_path, authority, (record,))
    assert provider.retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle).status.value == "mandatory_unresolved"
    optional = provider.retrieve_context(
        _request().model_copy(update={"mandatory_record_references": (), "optional_query": "Atlas", "optional_domains": (MemoryDomain.SEMANTIC,), "reference_time": now}),
        opaque_host_ingress=handle,
    )
    omission = next(omission for omission in optional.omissions if omission.reason.value == "provenance_unavailable")
    assert omission.omitted_record_ids == ("semantic:one",)
    structured = provider.retrieve_context(
        _request().model_copy(update={"mandatory_record_references": (), "optional_query": "", "optional_domains": (), "reference_time": now, "structured_query": MemoryQueryRequest(query="Who owns the Atlas?", reference_time=now)}),
        opaque_host_ingress=handle,
    )
    assert structured.structured_outcome is not None and structured.structured_outcome.status != "answered"
    assert any(omission.reason.value == "provenance_unavailable" for omission in structured.omissions)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_emit_typed_and_canonical_evidence_ids_at_utf8_byte_boundary(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    canonical_source = _raw_source("raw:canonical", now)
    typed_source = _raw_source("raw:typed", now)
    link = _typed_link(now=now, lifecycle_state=EntityLinkLifecycleState.ACTIVE, evidence_ids=(typed_source.memory_id,))
    record = CanonicalMemoryRecord(
        memory_id="semantic:one",
        domain=MemoryDomain.SEMANTIC,
        text="caf\u00e9",
        content={"memory_evolution_kind": "entity_link", "entity_link": link.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        task_id="task",
        source_kind="memory_evolution",
        source_record_ids=(canonical_source.memory_id,),
    )
    records = (canonical_source, typed_source, record)
    handle = _all_record_grant(authority, records, now)
    provider = _provider_with_records(root, tmp_path, authority, records)
    source_ids = ("raw:canonical", "raw:typed")
    exact_bytes = sum(len(value.encode("utf-8")) for value in ("caf\u00e9", "semantic:one", "semantic", "memory_evolution", *source_ids))
    request = _request().model_copy(update={"reference_time": now, "budget": ScopedContextBudget(max_mandatory_items=1, max_optional_items=1, max_optional_omission_ids=1, max_rendered_utf8_bytes=exact_bytes)})
    result = provider.retrieve_context(request, opaque_host_ingress=handle)
    assert result.mandatory_items[0].source_record_ids == source_ids
    assert provider.retrieve_context(request.model_copy(update={"budget": request.budget.model_copy(update={"max_rendered_utf8_bytes": exact_bytes - 1})}), opaque_host_ingress=handle).status.value == "mandatory_overflow"


def _evolved_root(root: str, tmp_path):
    if root == "filesystem":
        bundle = FilesystemStorageBundle.from_root(tmp_path / "store")
        return bundle.build_memory_plane_service(), lambda authority: bundle.build_provider_memory_service(scoped_read_authority=authority)
    plane = MemoryPlaneService()
    return plane, lambda authority: HermesMemoryProvider(memory_plane=plane, scoped_read_authority=authority)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_answer_current_and_historical_structured_claims_from_evolution(root: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 3, 20, tzinfo=UTC)
    plane, build_provider = _evolved_root(root, tmp_path)
    evolution = MemoryEvolutionService(memory_plane=plane)
    for memory_id, text, timestamp in (
        ("tx:alice", "Atlas migration owner is Alice.", datetime(2026, 1, 10, tzinfo=UTC)),
        ("tx:bob", "Atlas migration owner is Bob.", datetime(2026, 3, 10, tzinfo=UTC)),
    ):
        record = CanonicalMemoryRecord(
            memory_id=memory_id,
            domain=MemoryDomain.TRANSCRIPT,
            text=text,
            content={"text": text},
            status=CommitStatus.COMMITTED,
            source_kind="user",
            timestamp=timestamp,
            is_raw_event=True,
        )
        plane.write_records((record,))
        evolution.evolve_records([record])
    _, records = plane.read_snapshot()
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    provider = build_provider(authority)
    budget = ScopedContextBudget(max_mandatory_items=2, max_optional_items=20, max_optional_omission_ids=2, max_rendered_utf8_bytes=10000)
    expected_by_query = {
        "Who owns the Atlas migration now?": next(
            record.memory_id for record in records
            if record.content.get("memory_evolution_kind") == "claim_state"
            and record.content["claim_state"].get("object_value") == "Bob"
        ),
        "Who owned the Atlas migration in January?": next(
            record.memory_id for record in records
            if record.content.get("memory_evolution_kind") == "claim_state"
            and record.content["claim_state"].get("object_value") == "Alice"
        ),
    }
    for query, expected_claim_id in expected_by_query.items():
        request = ScopedContextRequest(
            host_task_id="task",
            host_state_id="state",
            declared_complete_mandatory_set=True,
            mandatory_record_references=(),
            optional_query="",
            optional_domains=(),
            budget=budget,
            reference_time=now,
            structured_query=MemoryQueryRequest(query=query, reference_time=now),
        )
        result = provider.retrieve_context(request, opaque_host_ingress=handle)
        assert result.structured_outcome is not None
        assert result.structured_outcome.status == "answered"
        assert tuple(item.record_id for item in result.structured_outcome.claim_items) == (expected_claim_id,)
        structured_provenance_ids = {
            record_id
            for omission in result.omissions
            if omission.channel.value == "structured_graph" and omission.reason.value == "provenance_unavailable"
            for record_id in omission.omitted_record_ids
        }
        assert expected_claim_id not in structured_provenance_ids
    alice_claim_id = expected_by_query["Who owned the Atlas migration in January?"]
    alice_claim = next(record for record in records if record.memory_id == alice_claim_id)
    subject_entity_id = alice_claim.content["claim_state"]["claim_key"]["subject_entity_id"]
    interval_start = datetime(2026, 1, 1, tzinfo=UTC)
    interval_end = datetime(2026, 2, 1, tzinfo=UTC)
    monkeypatch.setattr(
        EnglishLexicalQueryAnalyzer,
        "analyze",
        lambda *_args, **_kwargs: QueryAnalysis(
            temporal_frame=QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.INTERVAL,
                valid_from=interval_start,
                valid_to=interval_end,
                resolved_entity_ids=[subject_entity_id],
            ),
            predicate_id="owner",
            subject_entity_id=subject_entity_id,
            graph_patterns=[
                GraphPatternConstraint(
                    subject=ResolvedEntityReference(entity_id=subject_entity_id),
                    predicate_id="owner",
                )
            ],
        ),
    )
    interval = provider.retrieve_context(
        ScopedContextRequest(
            host_task_id="task",
            host_state_id="state",
            declared_complete_mandatory_set=True,
            mandatory_record_references=(),
            optional_query="",
            optional_domains=(),
            budget=budget,
            reference_time=now,
            structured_query=MemoryQueryRequest(
                query="Who owned the Atlas migration in January?",
                reference_time=now,
            ),
        ),
        opaque_host_ingress=handle,
    )
    assert interval.structured_outcome is not None
    assert interval.structured_outcome.status == "answered"
    assert tuple(item.record_id for item in interval.structured_outcome.claim_items) == (alice_claim_id,)
    assert alice_claim_id not in {
        record_id
        for omission in interval.omissions
        if omission.channel.value == "structured_graph" and omission.reason.value == "provenance_unavailable"
        for record_id in omission.omitted_record_ids
    }


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_return_unique_sorted_transitive_structured_source_closure(root: str, tmp_path) -> None:
    now = datetime(2026, 3, 20, tzinfo=UTC)
    plane, build_provider = _evolved_root(root, tmp_path)
    raw = CanonicalMemoryRecord(
        memory_id="raw:atlas",
        domain=MemoryDomain.TRANSCRIPT,
        text="Atlas migration owner is Alice.",
        content={"text": "Atlas migration owner is Alice."},
        status=CommitStatus.COMMITTED,
        source_kind="user",
        timestamp=datetime(2026, 1, 10, tzinfo=UTC),
        is_raw_event=True,
    )
    plane.write_records((raw,))
    MemoryEvolutionService(memory_plane=plane).evolve_records([raw])
    _, evolved = plane.read_snapshot()
    claim = next(record for record in evolved if record.content.get("memory_evolution_kind") == "claim_state")
    source = CanonicalMemoryRecord(
        memory_id="semantic:source",
        domain=MemoryDomain.SEMANTIC,
        text="canonical evidence",
        status=CommitStatus.COMMITTED,
        source_kind="memory_evolution",
        source_record_ids=(raw.memory_id,),
    )
    plane.write_records((source,))
    plane.upsert_record(claim.model_copy(update={"source_record_ids": [source.memory_id]}))
    _, records = plane.read_snapshot()
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    request = ScopedContextRequest(
        host_task_id="task",
        host_state_id="state",
        declared_complete_mandatory_set=True,
        mandatory_record_references=(),
        optional_query="",
        optional_domains=(),
        budget=ScopedContextBudget(max_mandatory_items=1, max_optional_items=20, max_optional_omission_ids=2, max_rendered_utf8_bytes=10000),
        reference_time=now,
        structured_query=MemoryQueryRequest(query="Who owns the Atlas migration now?", reference_time=now),
    )
    result = build_provider(authority).retrieve_context(request, opaque_host_ingress=handle)
    assert result.structured_outcome is not None
    assert result.structured_outcome.status == "answered"
    evidence_ids = tuple(item.record_id for item in result.structured_outcome.evidence_items)
    assert evidence_ids == tuple(sorted(set(evidence_ids)))
    assert evidence_ids == (raw.memory_id, source.memory_id)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_structured_read_uses_one_captured_snapshot_after_live_mutation(root: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 3, 20, tzinfo=UTC)
    plane, build_provider = _evolved_root(root, tmp_path)
    old_raw = CanonicalMemoryRecord(memory_id="raw:old", domain=MemoryDomain.TRANSCRIPT, text="Atlas migration owner is Alice.", content={"text": "Atlas migration owner is Alice."}, status=CommitStatus.COMMITTED, source_kind="user", timestamp=datetime(2026, 1, 10, tzinfo=UTC), is_raw_event=True)
    plane.write_records((old_raw,))
    evolution = MemoryEvolutionService(memory_plane=plane)
    evolution.evolve_records([old_raw])
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    provider = build_provider(authority)
    snapshot_owner = provider._memory_plane if root == "filesystem" else provider._service._memory_plane
    captured_revision, captured_records = snapshot_owner.read_snapshot()
    old_claim_id = next(record.memory_id for record in captured_records if record.content.get("memory_evolution_kind") == "claim_state")
    handle = _all_record_grant(authority, captured_records, now)
    reads = 0
    def read_captured():
        nonlocal reads
        reads += 1
        new_raw = CanonicalMemoryRecord(memory_id="raw:new", domain=MemoryDomain.TRANSCRIPT, text="Atlas migration owner is Bob.", content={"text": "Atlas migration owner is Bob."}, status=CommitStatus.COMMITTED, source_kind="user", timestamp=datetime(2026, 3, 10, tzinfo=UTC), is_raw_event=True)
        snapshot_owner.write_records((new_raw,))
        evolution.evolve_records([new_raw])
        return captured_revision, captured_records
    monkeypatch.setattr(snapshot_owner, "read_snapshot", read_captured)
    request = ScopedContextRequest(host_task_id="task", host_state_id="state", declared_complete_mandatory_set=True, mandatory_record_references=(), optional_query="", optional_domains=(), budget=ScopedContextBudget(max_mandatory_items=1, max_optional_items=10, max_optional_omission_ids=2, max_rendered_utf8_bytes=10_000), reference_time=now, structured_query=MemoryQueryRequest(query="Who owns the Atlas migration now?", reference_time=now))
    result = provider.retrieve_context(request, opaque_host_ingress=handle)
    assert reads == 1 and result.memory_snapshot_revision == captured_revision
    assert result.structured_outcome is not None and tuple(item.record_id for item in result.structured_outcome.claim_items) == (old_claim_id,)
    assert tuple(item.record_id for item in result.structured_outcome.evidence_items) == (old_raw.memory_id,)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_charge_selected_claim_and_claim_evidence_once_at_exact_boundary(root: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 3, 20, tzinfo=UTC)
    plane, build_provider = _evolved_root(root, tmp_path)
    scope = MemoryScope(task_id="task")
    first_raw = _raw_source("raw:dependency:first", now)
    second_raw = _raw_source("raw:dependency:second", now)
    link = _typed_link(
        now=now,
        lifecycle_state=EntityLinkLifecycleState.ACTIVE,
        evidence_ids=(first_raw.memory_id,),
    )
    confidence = ConfidenceComponents(extraction=1.0, evidence=1.0, source_trust=1.0, calibrated=1.0)
    first_state = ClaimState(
        claim_id="claim:dependency:first",
        claim_key=ClaimKey(
            subject_entity_id="entity:atlas",
            predicate_id="dependency",
            scope=scope,
            assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
            epistemic_status=ClaimEpistemicStatus.ASSERTED,
            polarity=ClaimPolarity.POSITIVE,
            modality=ClaimModality.ASSERTION,
        ),
        object_value="database migration",
        lifecycle_state=ClaimLifecycleState.ACTIVE,
        source_claim_id="claim:dependency:first",
        confidence=confidence,
        semantic_context=ClaimSemanticContext(
            assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
            epistemic_status=ClaimEpistemicStatus.ASSERTED,
            polarity=ClaimPolarity.POSITIVE,
            modality=ClaimModality.ASSERTION,
            attribution_source_id=first_raw.memory_id,
        ),
        subject_link_id=link.link_id,
        valid_from=now - timedelta(days=1),
        evidence_spans=[EvidenceSpan(source_id=first_raw.memory_id, quote="raw source", source_type=SourceType.USER, timestamp=now)],
    )
    second_state = first_state.model_copy(
        update={
            "claim_id": "claim:dependency:second",
            "object_value": "service rollout",
            "source_claim_id": "claim:dependency:second",
            "semantic_context": ClaimSemanticContext(
                assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
                epistemic_status=ClaimEpistemicStatus.ASSERTED,
                polarity=ClaimPolarity.POSITIVE,
                modality=ClaimModality.ASSERTION,
                attribution_source_id=second_raw.memory_id,
            ),
            "evidence_spans": [EvidenceSpan(source_id=second_raw.memory_id, quote="raw source", source_type=SourceType.USER, timestamp=now)],
        }
    )
    first_claim = record_from_claim_state(state=first_state, source_candidate_id="candidate:dependency:first")
    second_claim = record_from_claim_state(state=second_state, source_candidate_id="candidate:dependency:second")
    # This selected-claim dependency must be charged once as the claim item, not again as evidence.
    first_claim = first_claim.model_copy(
        update={"source_record_ids": [first_raw.memory_id, second_claim.memory_id]}
    )
    plane.write_records((first_raw, second_raw, record_from_entity_link(link), first_claim, second_claim))
    revision, records = plane.read_snapshot()
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    request = ScopedContextRequest(host_task_id="task", host_state_id="state", declared_complete_mandatory_set=True, mandatory_record_references=(), optional_query="", optional_domains=(), budget=ScopedContextBudget(max_mandatory_items=1, max_optional_items=4, max_optional_omission_ids=3, max_rendered_utf8_bytes=10_000), reference_time=now, structured_query=MemoryQueryRequest(query="What dependencies does Atlas have now?", reference_time=now, scope=scope))
    provider = build_provider(authority)
    monkeypatch.setattr(
        EnglishLexicalQueryAnalyzer,
        "analyze",
        lambda *_args, **_kwargs: QueryAnalysis(
            temporal_frame=QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.CURRENT,
                scope_kind=QueryScopeKind.TASK,
                scope_key=scope.scope_key,
                resolved_entity_ids=["entity:atlas"],
            ),
            predicate_id="dependency",
            subject_entity_id="entity:atlas",
            graph_patterns=[
                GraphPatternConstraint(
                    subject=ResolvedEntityReference(entity_id="entity:atlas"),
                    predicate_id="dependency",
                )
            ],
        ),
    )
    full = provider.retrieve_context(request, opaque_host_ingress=handle)
    assert full.memory_snapshot_revision == revision and full.structured_outcome is not None
    assert tuple(item.record_id for item in full.structured_outcome.claim_items) == tuple(sorted((first_claim.memory_id, second_claim.memory_id)))
    assert tuple(item.record_id for item in full.structured_outcome.evidence_items) == tuple(sorted((first_raw.memory_id, second_raw.memory_id)))
    unit = full.structured_outcome.claim_items + full.structured_outcome.evidence_items
    assert len(unit) == 4 and len({item.record_id for item in unit}) == 4
    exact_bytes = sum(sum(len(value.encode("utf-8")) for value in (item.rendered_text, item.record_id, item.domain.value, item.source_kind, *item.source_record_ids, *((item.provenance_ref,) if item.provenance_ref else ()))) for item in unit)
    exact = provider.retrieve_context(request.model_copy(update={"budget": request.budget.model_copy(update={"max_rendered_utf8_bytes": exact_bytes})}), opaque_host_ingress=handle)
    assert exact.structured_outcome is not None and exact.structured_outcome.status == "answered"
    item_short = provider.retrieve_context(request.model_copy(update={"budget": request.budget.model_copy(update={"max_optional_items": 3})}), opaque_host_ingress=handle)
    assert item_short.structured_outcome is None and any(item.reason.value == "optional_limit" for item in item_short.omissions)
    short = provider.retrieve_context(request.model_copy(update={"budget": request.budget.model_copy(update={"max_rendered_utf8_bytes": exact_bytes - 1})}), opaque_host_ingress=handle)
    assert short.structured_outcome is None and any(item.reason.value == "rendered_byte_limit" for item in short.omissions)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_exclude_valid_empty_typed_scope_from_scoped_envelope(root: str, tmp_path) -> None:
    now = datetime(2026, 3, 20, tzinfo=UTC)
    source = _raw_source("raw:unscoped", now)
    state = ClaimState(
        claim_id="claim:unscoped",
        claim_key=ClaimKey(subject_entity_id="entity:atlas", predicate_id="dependency", scope=MemoryScope()),
        object_value="database migration",
        lifecycle_state=ClaimLifecycleState.ACTIVE,
        source_claim_id="claim:unscoped",
        confidence=ConfidenceComponents(extraction=1.0, evidence=1.0, source_trust=1.0, calibrated=1.0),
        evidence_spans=[EvidenceSpan(source_id=source.memory_id, quote="raw source", source_type=SourceType.USER, timestamp=now)],
    )
    scoped_envelope = record_from_claim_state(state=state, source_candidate_id="candidate:unscoped").model_copy(
        update={"task_id": "task"}
    )
    records = (source, scoped_envelope)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    provider = _provider_with_records(root, tmp_path, authority, records)
    request = _request().model_copy(
        update={
            "reference_time": now,
            "mandatory_record_references": (ScopedRecordReference(record_id=scoped_envelope.memory_id, purpose="state"),),
        }
    )
    assert provider.retrieve_context(request, opaque_host_ingress=handle).status.value == "mandatory_unresolved"


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_use_source_closed_temporal_anchor_catalog(root: str, tmp_path) -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    plane, build_provider = _evolved_root(root, tmp_path)
    raw = CanonicalMemoryRecord(memory_id="raw:release", domain=MemoryDomain.TRANSCRIPT, text="Atlas migration owner is Alice.", content={"text": "Atlas migration owner is Alice."}, status=CommitStatus.COMMITTED, task_id="task", source_kind="user", timestamp=datetime(2026, 6, 2, tzinfo=UTC), is_raw_event=True)
    plane.write_records((raw,))
    MemoryEvolutionService(memory_plane=plane).evolve_records([raw])
    anchor = record_from_temporal_anchor(TemporalAnchor(anchor_id="anchor:release", names=["release week"], valid_from=datetime(2026, 6, 1, tzinfo=UTC), valid_to=datetime(2026, 6, 8, tzinfo=UTC), source_ids=[raw.memory_id], scope=MemoryScope(task_id="task")))
    plane.write_records((anchor,))
    revision, records = plane.read_snapshot()
    claim_id = next(record.memory_id for record in records if record.content.get("memory_evolution_kind") == "claim_state")
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    request = ScopedContextRequest(host_task_id="task", host_state_id="state", declared_complete_mandatory_set=True, mandatory_record_references=(), optional_query="", optional_domains=(), budget=ScopedContextBudget(max_mandatory_items=1, max_optional_items=10, max_optional_omission_ids=2, max_rendered_utf8_bytes=10_000), reference_time=now, structured_query=MemoryQueryRequest(query="Who owned the Atlas migration during release week?", reference_time=now, scope=MemoryScope(task_id="task")))
    result = build_provider(authority).retrieve_context(request, opaque_host_ingress=handle)
    assert result.memory_snapshot_revision == revision and result.structured_outcome is not None
    assert result.structured_outcome.status == "answered"
    assert tuple(item.record_id for item in result.structured_outcome.claim_items) == (claim_id,)
    assert tuple(item.record_id for item in result.structured_outcome.evidence_items) == (raw.memory_id,)
    structured_provenance_ids = {
        record_id
        for omission in result.omissions
        if omission.channel.value == "structured_graph" and omission.reason.value == "provenance_unavailable"
        for record_id in omission.omitted_record_ids
    }
    assert {claim_id, anchor.memory_id}.isdisjoint(structured_provenance_ids)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_deny_at_expiry_before_snapshot(root: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now)
    provider, snapshot_owner = _root_with_record(root, tmp_path, authority)
    calls = 0
    original = snapshot_owner.read_snapshot
    def counted_snapshot():
        nonlocal calls
        calls += 1
        return original()
    monkeypatch.setattr(snapshot_owner, "read_snapshot", counted_snapshot)
    result = provider.retrieve_context(_request(), opaque_host_ingress=handle)
    assert result.status.value == "denied"
    assert result.memory_snapshot_revision is None
    assert calls == 0


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("request_update", ({"host_task_id": "wrong"}, {"host_state_id": "wrong"}))
def test_real_roots_deny_valid_handle_bound_to_another_request_before_snapshot(root: str, request_update: dict[str, str], tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    provider, plane = _root_with_record(root, tmp_path, authority)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    reads = 0
    original = plane.read_snapshot
    def counted_snapshot():
        nonlocal reads
        reads += 1
        return original()
    monkeypatch.setattr(plane, "read_snapshot", counted_snapshot)
    result = provider.retrieve_context(_request().model_copy(update=request_update), opaque_host_ingress=handle)
    assert reads == 0 and result.status.value == "denied" and result.mandatory_items == ()


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("invalid_kind", ("duplicate_refs", "duplicate_domains", "mismatched_structured_time"))
def test_real_roots_revalidate_model_construct_requests_before_snapshot(root: str, invalid_kind: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    provider, plane = _root_with_record(root, tmp_path, authority)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    base = _request().model_copy(update={"reference_time": now})
    values = base.__dict__.copy()
    if invalid_kind == "duplicate_refs":
        values["mandatory_record_references"] = base.mandatory_record_references * 2
    elif invalid_kind == "duplicate_domains":
        values["optional_domains"] = (MemoryDomain.SEMANTIC, MemoryDomain.SEMANTIC)
    else:
        values["structured_query"] = MemoryQueryRequest(query="value", reference_time=now - timedelta(seconds=1))
    invalid = ScopedContextRequest.model_construct(**values)
    reads = 0
    original = plane.read_snapshot
    def counted_snapshot():
        nonlocal reads
        reads += 1
        return original()
    monkeypatch.setattr(plane, "read_snapshot", counted_snapshot)
    result = provider.retrieve_context(invalid, opaque_host_ingress=handle)
    assert reads == 0 and result.status.value == "invalid_request" and result.mandatory_items == ()


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_scoped_authority_rejects_whitespace_namespace_and_mutable_record_ids(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    with pytest.raises(ValueError):
        authority.provision(host_task_id=" ", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    with pytest.raises(ValueError):
        ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id=" ")
    with pytest.raises(ValueError):
        ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, allowed_record_ids={"semantic:one"})


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_recheck_revocation_at_release(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    entered, proceed = Event(), Event()
    class BarrierAuthority(InProcessScopedReadAuthority):
        def authorize_release(self, grant):
            entered.set()
            assert proceed.wait(3)
            return super().authorize_release(grant)
    authority = BarrierAuthority(now_provider=lambda: now)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    provider, _ = _root_with_record(root, tmp_path, authority)
    outcome = []
    worker = Thread(target=lambda: outcome.append(provider.retrieve_context(_request(), opaque_host_ingress=handle)))
    worker.start()
    assert entered.wait(3)
    authority.revoke(handle)
    replacement = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    proceed.set()
    worker.join(3)
    assert not worker.is_alive()
    assert outcome[0].status.value == "denied"
    assert outcome[0].mandatory_items == ()
    assert provider.retrieve_context(_request(), opaque_host_ingress=replacement).authority_binding_receipt is not None


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_revoke_only_future_reads(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    provider, _ = _root_with_record(root, tmp_path, authority)
    assert provider.retrieve_context(_request(), opaque_host_ingress=handle).authority_binding_receipt is not None
    authority.revoke(handle)
    denied = provider.retrieve_context(_request(), opaque_host_ingress=handle)
    assert denied.status.value == "denied"
    assert denied.mandatory_items == ()


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_jsonl_reopen_requires_new_process_authority_and_preserves_bytes(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    storage_root = tmp_path / "jsonl"
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    bundle = FilesystemStorageBundle.from_root(storage_root)
    bundle.memory_plane_store.write_records((CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),))
    provider = bundle.build_provider_memory_service(scoped_read_authority=authority) if root == "filesystem" else HermesMemoryProvider(storage_root=str(storage_root), scoped_read_authority=authority)
    receipt = provider.retrieve_context(_request(), opaque_host_ingress=handle).authority_binding_receipt
    before = (storage_root / "memory_plane" / "memory_records.jsonl").read_bytes()
    script = """import json, sys\nfrom datetime import UTC, datetime, timedelta\nfrom memorii.core.filesystem_storage.bundle import FilesystemStorageBundle\nfrom memorii.core.scoped_context.authority import InProcessScopedReadAuthority, ScopedNamespaceGrantRow\nfrom memorii.core.scoped_context.contracts import ScopedContextBudget, ScopedContextRequest, ScopedRecordReference\nfrom memorii.domain.enums import MemoryDomain\nfrom memorii.integrations.hermes_provider import HermesMemoryProvider\nroot, kind, stale = sys.argv[1:]\nnow=datetime(2026,1,2,tzinfo=UTC)\na=InProcessScopedReadAuthority(now_provider=lambda:now)\nr=ScopedContextRequest(host_task_id='task',host_state_id='state',declared_complete_mandatory_set=True,mandatory_record_references=(ScopedRecordReference(record_id='semantic:one',purpose='state'),),optional_query=None,optional_domains=(),budget=ScopedContextBudget(max_mandatory_items=1,max_optional_items=1,max_optional_omission_ids=1,max_rendered_utf8_bytes=1000),reference_time=now)\np=FilesystemStorageBundle.from_root(root).build_provider_memory_service(scoped_read_authority=a) if kind=='filesystem' else HermesMemoryProvider(storage_root=root,scoped_read_authority=a)\nstale_status=p.retrieve_context(r,opaque_host_ingress=stale).status.value\nh=a.provision(host_task_id='task',host_state_id='state',rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC,task_id='task'),),expires_at=now+timedelta(minutes=1))\nprint(json.dumps([stale_status,p.retrieve_context(r,opaque_host_ingress=h).status.value]))\n"""
    completed = subprocess.run([sys.executable, "-c", script, str(storage_root), root, receipt.handle_id], check=True, capture_output=True, text=True)
    assert json.loads(completed.stdout) == ["denied", "partial_optional"]
    assert (storage_root / "memory_plane" / "memory_records.jsonl").read_bytes() == before


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("valid_to", (datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)))
def test_real_roots_exclude_parents_with_noncurrent_source_closure(root: str, valid_to: datetime, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    rows = (ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"), ScopedNamespaceGrantRow(domain=MemoryDomain.TRANSCRIPT, task_id="task"))
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=rows, expires_at=now + timedelta(minutes=1))
    source = CanonicalMemoryRecord(memory_id="raw:source", domain=MemoryDomain.TRANSCRIPT, text="source", status=CommitStatus.COMMITTED, task_id="task", source_kind="test", valid_to=valid_to)
    parent = CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test", source_record_ids=("raw:source",))
    if root == "filesystem":
        bundle = FilesystemStorageBundle.from_root(tmp_path / "store")
        bundle.memory_plane_store.write_records((source, parent))
        provider = bundle.build_provider_memory_service(scoped_read_authority=authority)
    else:
        plane = MemoryPlaneService()
        plane.write_records((source, parent))
        provider = HermesMemoryProvider(memory_plane=plane, scoped_read_authority=authority)
    assert provider.retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle).status.value == "mandatory_unresolved"
    optional = provider.retrieve_context(_request().model_copy(update={"mandatory_record_references": (), "optional_query": "value", "optional_domains": (MemoryDomain.SEMANTIC,), "reference_time": now}), opaque_host_ingress=handle)
    assert any(item.reason.value == "provenance_unavailable" for item in optional.omissions)


def _six_domain_records() -> tuple[CanonicalMemoryRecord, ...]:
    return tuple(
        CanonicalMemoryRecord(
            memory_id=f"{domain.value}:mandatory",
            domain=domain,
            text=f"{domain.value} mandatory",
            status=CommitStatus.COMMITTED,
            task_id="task",
            source_kind="test",
        )
        for domain in MemoryDomain
    )


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("optional_case", ("scorer_outage", "blank_query", "optional_overflow"))
def test_real_roots_keep_all_domain_mandatory_items_when_optional_work_fails(
    root: str, optional_case: str, tmp_path, monkeypatch
) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    records = _six_domain_records() + (
        CanonicalMemoryRecord(memory_id="semantic:optional", domain=MemoryDomain.SEMANTIC, text="optional context", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
        CanonicalMemoryRecord(memory_id="episodic:optional", domain=MemoryDomain.EPISODIC, text="optional episode", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    provider = _provider_with_records(root, tmp_path, authority, records)
    request = _request().model_copy(update={
        "reference_time": now,
        "mandatory_record_references": tuple(ScopedRecordReference(record_id=record.memory_id, purpose="state") for record in records[:6]),
        "optional_domains": (MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC),
        "optional_query": "optional" if optional_case != "blank_query" else " ",
        "budget": ScopedContextBudget(max_mandatory_items=6, max_optional_items=1 if optional_case == "optional_overflow" else 2, max_optional_omission_ids=1, max_rendered_utf8_bytes=10_000),
    })
    if optional_case == "scorer_outage":
        monkeypatch.setattr(ScopedContextIndex, "rank", lambda *_: (_ for _ in ()).throw(ScopedOptionalScorerError()))
    result = provider.retrieve_context(request, opaque_host_ingress=handle)
    assert tuple(item.record_id for item in result.mandatory_items) == tuple(record.memory_id for record in records[:6])
    expected = "scorer_unavailable" if optional_case == "scorer_outage" else "empty_query" if optional_case == "blank_query" else "optional_limit"
    assert any(omission.reason.value == expected for omission in result.omissions)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_stop_before_optional_work_on_mandatory_overflow(root: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    records = _six_domain_records()
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    provider = _provider_with_records(root, tmp_path, authority, records)
    monkeypatch.setattr(ScopedContextIndex, "rank", lambda *_: (_ for _ in ()).throw(AssertionError("optional work ran")))
    request = _request().model_copy(update={
        "reference_time": now,
        "mandatory_record_references": tuple(ScopedRecordReference(record_id=record.memory_id, purpose="state") for record in records),
        "optional_query": "context",
        "optional_domains": (MemoryDomain.SEMANTIC,),
        "budget": ScopedContextBudget(max_mandatory_items=5, max_optional_items=1, max_optional_omission_ids=1, max_rendered_utf8_bytes=10_000),
    })
    assert provider.retrieve_context(request, opaque_host_ingress=handle).status.value == "mandatory_overflow"


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_rank_authorized_optional_domains_from_one_immutable_snapshot(root: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    records = (
        CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="needle alpha", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
        CanonicalMemoryRecord(memory_id="semantic:two", domain=MemoryDomain.SEMANTIC, text="needle gamma", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
        CanonicalMemoryRecord(memory_id="episodic:two", domain=MemoryDomain.EPISODIC, text="needle delta", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
        CanonicalMemoryRecord(memory_id="episodic:one", domain=MemoryDomain.EPISODIC, text="needle beta", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
        CanonicalMemoryRecord(memory_id="semantic:excluded", domain=MemoryDomain.SEMANTIC, text="needle leaked", status=CommitStatus.COMMITTED, task_id="other", source_kind="test"),
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(
        ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),
        ScopedNamespaceGrantRow(domain=MemoryDomain.EPISODIC, task_id="task"),
    ), expires_at=now + timedelta(minutes=1))
    provider = _provider_with_records(root, tmp_path, authority, records)
    plane = provider._service._memory_plane if root == "hermes" else provider._memory_plane
    captured = plane.read_snapshot()
    reads = 0
    writes = 0
    original_write = plane.write_records

    def read_once():
        nonlocal reads
        reads += 1
        original_write((CanonicalMemoryRecord(memory_id="semantic:after", domain=MemoryDomain.SEMANTIC, text="needle after", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),))
        return captured

    def no_write(*_args, **_kwargs):
        nonlocal writes
        writes += 1
        raise AssertionError("scoped read must not write")

    monkeypatch.setattr(plane, "read_snapshot", read_once)
    monkeypatch.setattr(plane, "write_records", no_write)
    request = _request().model_copy(update={"reference_time": now, "optional_query": "needle", "optional_domains": (MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC), "budget": ScopedContextBudget(max_mandatory_items=1, max_optional_items=1, max_optional_omission_ids=1, max_rendered_utf8_bytes=10_000)})
    result = provider.retrieve_context(request, opaque_host_ingress=handle)
    assert reads == 1 and writes == 0 and result.memory_snapshot_revision == captured[0]
    assert tuple(item.record_id for item in result.optional_items) == ("semantic:two",)
    omission = next(item for item in result.omissions if item.reason.value == "optional_limit")
    assert omission.omitted_count == 2 and omission.identifiers_truncated


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_keep_positive_optional_matches_channel_first_and_omit_no_match(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    records = (
        CanonicalMemoryRecord(memory_id="semantic:match", domain=MemoryDomain.SEMANTIC, text="needle", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
        CanonicalMemoryRecord(memory_id="episodic:match", domain=MemoryDomain.EPISODIC, text="needle needle needle", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    provider = _provider_with_records(root, tmp_path, authority, records)
    request = _request().model_copy(update={
        "mandatory_record_references": (), "reference_time": now, "optional_query": "needle",
        "optional_domains": (MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC),
        "budget": ScopedContextBudget(max_mandatory_items=1, max_optional_items=2, max_optional_omission_ids=2, max_rendered_utf8_bytes=10_000),
    })
    matched = provider.retrieve_context(request, opaque_host_ingress=handle)
    assert tuple(item.record_id for item in matched.optional_items) == ("semantic:match", "episodic:match")
    no_match = provider.retrieve_context(request.model_copy(update={"optional_query": "absent-token"}), opaque_host_ingress=handle)
    assert no_match.status.value == "partial_optional" and no_match.optional_items == ()
    assert tuple((item.channel.value, item.reason.value) for item in no_match.omissions) == (("semantic_bm25", "no_match"),)
    punctuation = provider.retrieve_context(request.model_copy(update={"optional_query": "!!!"}), opaque_host_ingress=handle)
    assert punctuation.status.value == "partial_optional" and punctuation.optional_items == ()
    assert tuple((item.channel.value, item.reason.value) for item in punctuation.omissions) == (("semantic_bm25", "no_match"),)
    tokenless = provider.retrieve_context(request.model_copy(update={"optional_query": "   "}), opaque_host_ingress=handle)
    assert tokenless.optional_items == () and tuple(item.reason.value for item in tokenless.omissions) == ("empty_query",)
    capped = provider.retrieve_context(request.model_copy(update={"budget": request.budget.model_copy(update={"max_optional_items": 1})}), opaque_host_ingress=handle)
    assert tuple(item.record_id for item in capped.optional_items) == ("semantic:match",)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("fault", ("backend", "decode", "scorer", "structured"))
def test_real_roots_translate_typed_dependency_faults_without_losing_mandatory(root: str, fault: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    provider, plane = _root_with_record(root, tmp_path, authority)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    request = _request().model_copy(update={"reference_time": now, "optional_query": "value"})
    if fault in {"backend", "decode"}:
        calls = 0
        def failing_snapshot():
            nonlocal calls
            calls += 1
            raise ScopedSnapshotBackendError() if fault == "backend" else ScopedSnapshotDecodeError()
        monkeypatch.setattr(plane, "read_snapshot", failing_snapshot)
        result = provider.retrieve_context(request, opaque_host_ingress=handle)
        assert calls == 1 and result.status.value == "unavailable"
    elif fault == "scorer":
        monkeypatch.setattr(ScopedContextIndex, "rank", lambda *_: (_ for _ in ()).throw(ScopedOptionalScorerError()))
        result = provider.retrieve_context(request, opaque_host_ingress=handle)
        assert result.mandatory_items and any(item.reason.value == "scorer_unavailable" for item in result.omissions)
    else:
        monkeypatch.setattr("memorii.core.scoped_context.service.EvolutionStateRepository.from_snapshot", lambda *_: (_ for _ in ()).throw(ScopedStructuredDependencyError()))
        result = provider.retrieve_context(request.model_copy(update={"structured_query": MemoryQueryRequest(query="value", reference_time=now)}), opaque_host_ingress=handle)
        assert result.mandatory_items and any(item.reason.value == "structured_unavailable" for item in result.omissions)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_propagate_unexpected_snapshot_fault(root: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    provider, plane = _root_with_record(root, tmp_path, authority)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    monkeypatch.setattr(plane, "read_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("unexpected snapshot")))
    with pytest.raises(RuntimeError, match="unexpected snapshot"):
        provider.retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_propagate_unexpected_optional_faults(root: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    provider, _ = _root_with_record(root, tmp_path, authority)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    monkeypatch.setattr(ScopedContextIndex, "rank", lambda *_: (_ for _ in ()).throw(RuntimeError("unexpected")))
    with pytest.raises(RuntimeError, match="unexpected"):
        provider.retrieve_context(_request().model_copy(update={"reference_time": now, "optional_query": "value"}), opaque_host_ingress=handle)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("field", ("task_id", "session_id", "user_id", "agent_id", "execution_node_id", "solver_run_id"))
def test_real_roots_require_exact_namespace_fields_and_reject_forged_handles(root: str, field: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    fields = {name: None for name in ("task_id", "session_id", "user_id", "agent_id", "execution_node_id", "solver_run_id")}
    fields[field] = "expected"
    record = CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, source_kind="test", **fields)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, **fields),), expires_at=now + timedelta(minutes=1))
    provider = _provider_with_records(root, tmp_path, authority, (record,))
    assert provider.retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle).mandatory_items
    mismatched = record.model_copy(update={field: "other"})
    rejected = _provider_with_records(root, tmp_path, authority, (mismatched,)).retrieve_context(_request().model_copy(update={"reference_time": now, "optional_query": "value", "optional_domains": (MemoryDomain.SEMANTIC,)}), opaque_host_ingress=handle)
    assert rejected.status.value == "mandatory_unresolved" and rejected.mandatory_items == () and rejected.optional_items == ()
    denied = provider.retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=object())
    assert denied.status.value == "denied" and denied.model_dump(exclude={"status"}) == {key: None if key in {"request_task_id", "request_state_id", "authority_binding_receipt", "memory_snapshot_revision", "structured_outcome"} else () for key in denied.model_dump(exclude={"status"})}


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_allow_finite_all_null_grant_only_for_named_record(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    record = CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, source_kind="test")
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    with pytest.raises(ValueError):
        authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC),), expires_at=now + timedelta(minutes=1))
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, allowed_record_ids=frozenset({record.memory_id})),), expires_at=now + timedelta(minutes=1))
    result = _provider_with_records(root, tmp_path, authority, (record,)).retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle)
    assert result.mandatory_items and result.authority_binding_receipt is not None


@pytest.mark.integration
@pytest.mark.parametrize("root", ("factory", "filesystem", "hermes"))
def test_production_roots_fail_closed_without_authority_or_prefetch_fallback(root: str, tmp_path, monkeypatch) -> None:
    plane = MemoryPlaneService()
    plane.write_records((CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),))
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    if root == "factory":
        provider = build_provider_memory_service_from_env(memory_plane=plane)
    elif root == "filesystem":
        provider = FilesystemStorageBundle.from_root(tmp_path / "store").build_provider_memory_service(memory_plane=plane)
    else:
        provider = HermesMemoryProvider(memory_plane=plane)
    service = provider._service if root == "hermes" else provider
    reads = 0
    def no_snapshot():
        nonlocal reads
        reads += 1
        raise AssertionError("snapshot read")
    monkeypatch.setattr(plane, "read_snapshot", no_snapshot)
    monkeypatch.setattr(service, "prefetch", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("prefetch fallback")))
    denied = provider.retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle)
    assert reads == 0 and denied.status.value == "denied" and denied.memory_snapshot_revision is None and denied.mandatory_items == ()


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_exclude_malformed_nonruntime_candidates_before_decode(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    valid = CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test")
    malformed_candidate = CanonicalMemoryRecord(memory_id="semantic:candidate", domain=MemoryDomain.SEMANTIC, text="bad", content={"memory_evolution_kind": "entity_link", "entity_link": {"bad": True}}, status=CommitStatus.CANDIDATE, task_id="task", source_kind="test")
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, (valid, malformed_candidate), now)
    result = _provider_with_records(root, tmp_path, authority, (valid, malformed_candidate)).retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle)
    assert result.mandatory_items and result.status.value != "unavailable"


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_exclude_committed_malformed_owned_record_with_missing_source_before_decode(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    valid = CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test")
    malformed = CanonicalMemoryRecord(memory_id="semantic:bad", domain=MemoryDomain.SEMANTIC, text="bad", content={"memory_evolution_kind": "entity_link", "entity_link": {"bad": True}}, status=CommitStatus.COMMITTED, task_id="task", source_kind="test", source_record_ids=("raw:missing",))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, (valid, malformed), now)
    result = _provider_with_records(root, tmp_path, authority, (valid, malformed)).retrieve_context(_request().model_copy(update={"reference_time": now}), opaque_host_ingress=handle)
    assert result.mandatory_items and result.status.value != "unavailable"


@pytest.mark.integration
@pytest.mark.parametrize(
    "kind,payload",
    (
        ("claim_state", {"claim_key": "not-a-mapping", "evidence_spans": "not-a-list"}),
        ("temporal_anchor", {"scope": {"task_id": "task", "session_id": None, "user_id": None}, "source_ids": "not-a-list"}),
    ),
)
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_translate_malformed_eligible_owned_payload_to_unavailable(
    root: str, kind: str, payload: dict[str, object], tmp_path
) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    source = _raw_source("raw:source", now)
    malformed = CanonicalMemoryRecord(
        memory_id="semantic:one",
        domain=MemoryDomain.SEMANTIC,
        text="bad",
        content={"memory_evolution_kind": kind, kind: payload},
        status=CommitStatus.COMMITTED,
        task_id="task",
        source_kind="memory_evolution",
        source_record_ids=(source.memory_id,),
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    records = (source, malformed)
    handle = _all_record_grant(authority, records, now)
    result = _provider_with_records(root, tmp_path, authority, records).retrieve_context(
        _request().model_copy(update={"reference_time": now}),
        opaque_host_ingress=handle,
    )
    assert result.status.value == "unavailable" and result.memory_snapshot_revision is None


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("source_update", ({"valid_to": datetime(2026, 1, 2, tzinfo=UTC)}, {"validity_status": TemporalValidityStatus.INVALIDATED}, None))
def test_real_roots_structured_exclude_missing_or_noncurrent_claim_sources_with_provenance_omission(root: str, source_update: dict[str, object] | None, tmp_path) -> None:
    now = datetime(2026, 3, 20, tzinfo=UTC)
    plane, build_provider = _evolved_root(root, tmp_path)
    raw = CanonicalMemoryRecord(memory_id="raw:atlas", domain=MemoryDomain.TRANSCRIPT, text="Atlas migration owner is Alice.", content={"text": "Atlas migration owner is Alice."}, status=CommitStatus.COMMITTED, source_kind="user", timestamp=datetime(2026, 1, 10, tzinfo=UTC), is_raw_event=True)
    plane.write_records((raw,))
    MemoryEvolutionService(memory_plane=plane).evolve_records([raw])
    _, evolved = plane.read_snapshot()
    claim = next(record for record in evolved if record.content.get("memory_evolution_kind") == "claim_state")
    if source_update is None:
        plane.upsert_record(claim.model_copy(update={"source_record_ids": ["raw:missing"]}))
    else:
        plane.upsert_record(raw.model_copy(update=source_update))
    _, records = plane.read_snapshot()
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, records, now)
    request = ScopedContextRequest(host_task_id="task", host_state_id="state", declared_complete_mandatory_set=True, mandatory_record_references=(), optional_query="", optional_domains=(), budget=ScopedContextBudget(max_mandatory_items=1, max_optional_items=10, max_optional_omission_ids=2, max_rendered_utf8_bytes=10_000), reference_time=now, structured_query=MemoryQueryRequest(query="Who owns the Atlas migration now?", reference_time=now))
    result = build_provider(authority).retrieve_context(request, opaque_host_ingress=handle)
    assert result.structured_outcome is not None and result.structured_outcome.status != "answered"
    assert any(item.reason.value == "provenance_unavailable" for item in result.omissions)


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
def test_real_roots_require_valid_from_for_typed_nonclaim_current_records(root: str, tmp_path) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    source = _raw_source("raw:anchor", now)
    record = record_from_temporal_anchor(TemporalAnchor(anchor_id="anchor:one", names=["release"], valid_from=now - timedelta(days=2), valid_to=now + timedelta(days=2), source_ids=[source.memory_id], scope=MemoryScope(task_id="task")))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _all_record_grant(authority, (source, record), now)
    result = _provider_with_records(root, tmp_path, authority, (source, record)).retrieve_context(_request().model_copy(update={"reference_time": now, "mandatory_record_references": (ScopedRecordReference(record_id=record.memory_id, purpose="state"),)}), opaque_host_ingress=handle)
    assert result.status.value == "mandatory_unresolved"


@pytest.mark.integration
@pytest.mark.parametrize("root", ("filesystem", "hermes"))
@pytest.mark.parametrize("reader", ("claims", "links", "anchors"))
def test_real_roots_fail_closed_when_bound_snapshot_reader_is_unavailable(root: str, reader: str, tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    provider, _ = _root_with_record(root, tmp_path, authority)
    handle = authority.provision(host_task_id="task", host_state_id="state", rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),), expires_at=now + timedelta(minutes=1))
    service = provider._service if root == "hermes" else provider
    monkeypatch.setattr(service, "prefetch", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("prefetch fallback")))
    def fault(*_args, **_kwargs):
        raise ScopedStructuredDependencyError()
    if reader == "claims":
        monkeypatch.setattr(ClaimStateQueryService, "retrieve", fault)
    elif reader == "links":
        monkeypatch.setattr(EvolutionStateRepository, "list_entity_links", fault)
    else:
        monkeypatch.setattr(EvolutionStateRepository, "hydrate_temporal_anchors", fault)
    result = provider.retrieve_context(_request().model_copy(update={"reference_time": now, "structured_query": MemoryQueryRequest(query="value", reference_time=now)}), opaque_host_ingress=handle)
    assert result.mandatory_items and any(item.reason.value == "structured_unavailable" for item in result.omissions)
