from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    JsonlMemoryPlaneStore,
    MemoryPlaneCorruptionError,
    _PersistedBatch,
)
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority, ScopedNamespaceGrantRow
from memorii.core.scoped_context.contracts import (
    ScopedContextActivation,
    ScopedContextBudget,
    ScopedContextChannel,
    ScopedContextOmission,
    ScopedContextRequest,
    ScopedContextStatus,
    ScopedOmissionReason,
    ScopedRecordReference,
)
from memorii.core.scoped_context.service import catalog_visibility_current_at_release
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    StructuredClaimCatalogBinding,
    StructuredFactReadAuthority,
    StructuredGrantState,
    ThreePredicateSeedCatalogAuthorityRepository,
    catalog_version_memory_id,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    CatalogCapturedTurnPin,
    SeedCatalogBundleLocator,
)
from memorii.core.semantic_ingestion.hermes_captured_turn import HermesCapturedTurnLedger
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


def _request() -> ScopedContextRequest:
    return ScopedContextRequest(
        host_task_id="task",
        host_state_id="state",
        declared_complete_mandatory_set=True,
        mandatory_record_references=(ScopedRecordReference(record_id="semantic:one", purpose="state"),),
        optional_query="context",
        optional_domains=(MemoryDomain.SEMANTIC,),
        budget=ScopedContextBudget(
            max_mandatory_items=2, max_optional_items=2, max_optional_omission_ids=2, max_rendered_utf8_bytes=1000
        ),
        reference_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_scoped_context_requires_authority_before_snapshot() -> None:
    service = ProviderMemoryService(memory_plane=MemoryPlaneService())
    result = service.retrieve_context(_request(), opaque_host_ingress=object())
    assert result.status.value == "denied"
    assert result.memory_snapshot_revision is None


def test_scoped_context_releases_authorized_snapshot_items() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    plane.write_records(
        (
            CanonicalMemoryRecord(
                memory_id="semantic:one",
                domain=MemoryDomain.SEMANTIC,
                text="context value",
                status=CommitStatus.COMMITTED,
                task_id="task",
                source_kind="test",
            ),
        )
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    assert result.status.value == "complete"
    assert [item.record_id for item in result.mandatory_items] == ["semantic:one"]
    assert result.authority_binding_receipt is not None


def test_revoked_handle_denies_without_record_disclosure() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    authority.revoke(handle)
    result = ProviderMemoryService(scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    assert result.status.value == "denied"
    assert result.mandatory_items == ()


def test_optional_byte_budget_omits_whole_ranked_records() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    plane.write_records(
        (
            CanonicalMemoryRecord(
                memory_id="semantic:one",
                domain=MemoryDomain.SEMANTIC,
                text="context value",
                status=CommitStatus.COMMITTED,
                task_id="task",
                source_kind="test",
            ),
            CanonicalMemoryRecord(
                memory_id="semantic:two",
                domain=MemoryDomain.SEMANTIC,
                text="context " + "x" * 300,
                status=CommitStatus.COMMITTED,
                task_id="task",
                source_kind="test",
            ),
        )
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    request = _request().model_copy(
        update={
            "budget": ScopedContextBudget(
                max_mandatory_items=2, max_optional_items=2, max_optional_omission_ids=1, max_rendered_utf8_bytes=80
            )
        }
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        request, opaque_host_ingress=handle
    )
    assert result.status.value == "partial_optional"
    assert result.optional_items == ()
    assert result.omissions[0].reason.value == "rendered_byte_limit"
    assert result.omissions[0].omitted_count == 1


def test_malformed_owned_snapshot_payload_is_unavailable() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    plane.write_records(
        (
            CanonicalMemoryRecord(
                memory_id="semantic:one",
                domain=MemoryDomain.SEMANTIC,
                text="context value",
                content={"memory_evolution_kind": "claim_state", "claim_state": {"bad": "payload"}},
                status=CommitStatus.COMMITTED,
                task_id="task",
                source_kind="test",
            ),
        )
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    assert result.status.value == "unavailable"
    assert result.memory_snapshot_revision is None


def test_request_and_failure_envelopes_reject_blank_identity_and_empty_echo() -> None:
    with pytest.raises(ValueError, match="nonblank"):
        ScopedContextRequest.model_validate(_request().model_dump() | {"host_task_id": "   "})
    with pytest.raises(ValueError, match="record_id"):
        ScopedRecordReference(record_id=" ", purpose="state")
    with pytest.raises(ValueError, match="must not disclose"):
        ScopedContextActivation(
            status=ScopedContextStatus.DENIED,
            request_task_id="",
            request_state_id=None,
            authority_binding_receipt=None,
            memory_snapshot_revision=None,
            mandatory_items=(), optional_items=(), omissions=(), structured_outcome=None,
        )


def test_snapshot_corruption_is_typed_unavailable(monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task", host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    plane = MemoryPlaneService()
    def corrupt_snapshot():
        raise MemoryPlaneCorruptionError("bad jsonl")
    monkeypatch.setattr(plane, "read_snapshot", corrupt_snapshot)
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    assert result.status is ScopedContextStatus.UNAVAILABLE
    assert result.memory_snapshot_revision is None


def _structured_projection_records(*, claim_digest: str = "a" * 64, binding_digest: str | None = None, active: bool = True):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    authenticated = AuthenticatedPrincipalAgent(principal_id="alice", agent_id="assistant")
    fact = FactScopeGrant(
        grant_id="fact:alice", grant_version=1, fact_scope="user:alice", authenticated=authenticated,
    )
    catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    visibility = CatalogOwnerVisibilityGrant(
        grant_id="catalog:base:alice", grant_version=1, catalog_scope=catalog.catalog_scope,
        authenticated=authenticated, purpose="visibility_status",
    )
    projection = CanonicalMemoryRecord(
        memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="Atlas owner Alice",
        content={
            "runtime_context_projection_kind": "bootstrap_v3_claim_assertion",
            "claim_assertion_id": "claim:atlas-owner",
            "claim_assertion_record_digest": claim_digest,
        },
        status=CommitStatus.COMMITTED, task_id="task", user_id="alice", agent_id="assistant",
        source_kind="memory_evolution",
    )
    binding = StructuredClaimCatalogBinding(
        schema_version=1, claim_assertion_id="claim:atlas-owner",
        claim_record_digest=binding_digest or claim_digest, catalog_scope=catalog.catalog_scope,
        catalog_digest=catalog.catalog_digest, fact_scope=fact.fact_scope, authenticated=authenticated,
    )
    binding_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:structured-claim-catalog:claim:atlas-owner",
        domain=MemoryDomain.SEMANTIC, text="", content={"binding": binding.model_dump(mode="json")},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_structured_claim_catalog_binding",
        timestamp=now, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    states = tuple(
        CanonicalMemoryRecord(
            memory_id="semantic_ingestion:structured-grant:" + sha256((kind + "\0" + grant.grant_id).encode()).hexdigest(),
            domain=MemoryDomain.EXECUTION, text="",
            content={"state": StructuredGrantState(schema_version=1, grant_kind=kind, grant=grant, active=active).model_dump(mode="json")},
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_structured_grant_state",
            timestamp=now, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        for kind, grant in (("fact", fact), ("catalog_visibility", visibility))
    )
    read_authority = StructuredFactReadAuthority(
        authenticated=authenticated, fact_grant=fact, catalog_visibility_grant=visibility,
    )
    return projection, binding_record, states, read_authority


def _structured_read_handle(authority, *, now, read_authority):
    return authority.provision(
        host_task_id="task", host_state_id="state",
        rows=(ScopedNamespaceGrantRow(
            domain=MemoryDomain.SEMANTIC, task_id="task", user_id="alice", agent_id="assistant",
        ),),
        expires_at=now + timedelta(minutes=1),
        structured_fact_read_authorities=(read_authority,),
    )


def _schema2_structured_projection_records():
    projection, _binding, states, read_authority = _structured_projection_records()
    bundle = SeedCatalogBundleLocator().locate()
    ledger = HermesCapturedTurnLedger(
        installation_id="install", session_id="session", principal_id="alice",
        agent_id="assistant", turn_ordinal=1, message_digest="b" * 64,
        source_id="source:atlas", source_digest="c" * 64,
        preparation_fingerprint="d" * 64, captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    pin = CatalogCapturedTurnPin.seed(
        ledger=ledger, bundle=bundle, selection_pointer_digest="e" * 64,
    )
    binding = StructuredClaimCatalogBinding(
        schema_version=2,
        claim_assertion_id=projection.content["claim_assertion_id"],
        claim_record_digest=projection.content["claim_assertion_record_digest"],
        catalog_scope=bundle.catalog.catalog_scope,
        catalog_digest=bundle.catalog.catalog_digest,
        fact_scope=read_authority.fact_grant.fact_scope,
        authenticated=read_authority.authenticated,
        capture_id=pin.capture_id,
        pin_memory_id=pin.memory_id,
        pin_digest=pin.pin_digest,
        selected_version_id=pin.selected_version_id,
        selected_version_digest=pin.selected_version_digest,
        runtime_bundle_digest=pin.runtime_bundle_digest,
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    binding_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:structured-claim-catalog:" + binding.claim_assertion_id,
        domain=MemoryDomain.SEMANTIC, text="", content={"binding": binding.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_structured_claim_catalog_binding",
        timestamp=now, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    pin_record = CanonicalMemoryRecord(
        memory_id=pin.memory_id, domain=MemoryDomain.EXECUTION, text="",
        content={"catalog_capture_pin": pin.model_dump(mode="json")},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_catalog_capture_pin",
        timestamp=now, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    version_record = CanonicalMemoryRecord(
        memory_id=catalog_version_memory_id(bundle.version), domain=MemoryDomain.EXECUTION,
        text="", content={"catalog_version": bundle.version.model_dump(mode="json")},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_catalog_version",
        timestamp=now, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    return projection, binding_record, states, pin_record, version_record, read_authority


def test_schema2_catalog_read_releases_verified_persisted_version_after_jsonl_reopen(tmp_path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, binding, states, pin, version, read_authority = _schema2_structured_projection_records()
    store = JsonlMemoryPlaneStore(tmp_path / "valid")
    with store._locked(exclusive=True):
        store._replace_batches([
            _PersistedBatch.create(
                revision=1, data_revision=1,
                records=(projection, binding, *states, pin, version),
            ),
        ])
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "valid"))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _structured_read_handle(authority, now=now, read_authority=read_authority)
    result = ProviderMemoryService(memory_plane=reopened, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle,
    )
    assert result.status is ScopedContextStatus.PARTIAL_OPTIONAL
    assert [item.record_id for item in result.mandatory_items] == [projection.memory_id]


@pytest.mark.parametrize("version_mode", ("missing", "substituted"))
def test_schema2_catalog_read_denies_missing_or_substituted_persisted_version_after_jsonl_reopen(
    tmp_path, version_mode: str,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, binding, states, pin, version, read_authority = _schema2_structured_projection_records()
    records = [projection, binding, *states, pin]
    if version_mode == "substituted":
        version = version.model_copy(update={"content": {"catalog_version": {
            **version.content["catalog_version"], "version_digest": "0" * 64,
        }}})
    elif version_mode != "missing":
        raise AssertionError("test version mode is invalid")
    if version_mode != "missing":
        records.append(version)
    store = JsonlMemoryPlaneStore(tmp_path / version_mode)
    with store._locked(exclusive=True):
        store._replace_batches([
            _PersistedBatch.create(revision=1, data_revision=1, records=tuple(records)),
        ])
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / version_mode))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _structured_read_handle(authority, now=now, read_authority=read_authority)
    result = ProviderMemoryService(memory_plane=reopened, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle,
    )
    assert result.status is ScopedContextStatus.DENIED
    assert result.mandatory_items == ()
    assert result.optional_items == ()
    assert result.omissions == ()
    assert result.structured_outcome is None


def _linearized_snapshot(monkeypatch, plane, revision, records) -> None:
    monkeypatch.setattr(plane, "read_snapshot", lambda: (revision, records))
    monkeypatch.setattr(
        plane,
        "read_snapshot_linearized",
        lambda callback: callback(revision, records),
    )


def test_new_structured_projection_requires_current_catalog_and_fact_visibility(monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, binding, states, read_authority = _structured_projection_records()
    plane = MemoryPlaneService()
    _linearized_snapshot(monkeypatch, plane, 1, (projection, binding, *states))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _structured_read_handle(authority, now=now, read_authority=read_authority)
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle,
    )
    assert result.status is ScopedContextStatus.PARTIAL_OPTIONAL
    assert [item.record_id for item in result.mandatory_items] == [projection.memory_id]


def test_new_catalog_release_recheck_ignores_unrelated_old_projection_and_detects_binding_loss(
    monkeypatch,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, binding, states, read_authority = _structured_projection_records()
    plane = MemoryPlaneService()
    original = (projection, binding, *states)
    _linearized_snapshot(monkeypatch, plane, 1, original)
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _structured_read_handle(authority, now=now, read_authority=read_authority)
    result = ProviderMemoryService(
        memory_plane=plane, scoped_read_authority=authority,
    ).retrieve_context(_request(), opaque_host_ingress=handle)
    assert [item.record_id for item in result.mandatory_items] == [projection.memory_id]
    grant = authority.resolve(handle, task_id="task", state_id="state")
    assert grant is not None
    old = projection.model_copy(update={
        "memory_id": "mem:bootstrap-v3:runtime-claim:old",
        "content": {
            "runtime_context_projection_kind": "bootstrap_v3_claim_assertion",
            "claim_assertion_id": "claim:old",
            "claim_assertion_record_digest": "b" * 64,
        },
    })
    assert catalog_visibility_current_at_release(
        records=(*original, old), original_records=original,
        grant=grant, activation=result,
    )
    assert not catalog_visibility_current_at_release(
        records=(projection, *states, old), original_records=original,
        grant=grant, activation=result,
    )


@pytest.mark.parametrize("binding_digest,active", (("b" * 64, True), (None, False)))
def test_new_structured_projection_fails_closed_for_mismatched_binding_or_revoked_visibility(
    binding_digest: str | None, active: bool, monkeypatch,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, binding, states, read_authority = _structured_projection_records(
        binding_digest=binding_digest, active=active,
    )
    plane = MemoryPlaneService()
    _linearized_snapshot(monkeypatch, plane, 1, (projection, binding, *states))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _structured_read_handle(authority, now=now, read_authority=read_authority)
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle,
    )
    assert result.status is ScopedContextStatus.DENIED
    assert result.mandatory_items == ()


def test_new_structured_projection_fails_closed_for_corrupt_catalog_binding(monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, binding, states, read_authority = _structured_projection_records()
    corrupt = binding.model_copy(update={"content": {"binding": {"claim_assertion_id": "claim:atlas-owner"}}})
    plane = MemoryPlaneService()
    _linearized_snapshot(monkeypatch, plane, 1, (projection, corrupt, *states))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _structured_read_handle(authority, now=now, read_authority=read_authority)
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle,
    )
    assert result.status is ScopedContextStatus.DENIED
    assert result.mandatory_items == ()


def test_bootstrap_v3_projection_without_its_marker_cannot_fall_through_to_legacy_read(monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, binding, states, read_authority = _structured_projection_records()
    unmarked = projection.model_copy(
        update={
            "memory_id": "mem:bootstrap-v3:runtime-claim:" + "f" * 64,
            "content": {
                "claim_assertion_id": projection.content["claim_assertion_id"],
                "claim_assertion_record_digest": projection.content["claim_assertion_record_digest"],
            },
        }
    )
    plane = MemoryPlaneService()
    _linearized_snapshot(monkeypatch, plane, 1, (unmarked,))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _structured_read_handle(authority, now=now, read_authority=read_authority)
    request = _request().model_copy(
        update={"mandatory_record_references": (ScopedRecordReference(record_id=unmarked.memory_id, purpose="state"),)}
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        request, opaque_host_ingress=handle,
    )
    assert result.status is ScopedContextStatus.DENIED
    assert result.mandatory_items == ()


@pytest.mark.parametrize(
    ("verification", "expected_status"),
    (
        ("verified", ScopedContextStatus.PARTIAL_OPTIONAL),
        ("not_legacy", ScopedContextStatus.DENIED),
        ("unavailable", ScopedContextStatus.UNAVAILABLE),
    ),
)
def test_bootstrap_v3_projection_uses_only_the_verified_legacy_reader(
    verification: str,
    expected_status: ScopedContextStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current scoped namespace is necessary but not enough for old V3 data."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, _binding, _states, _read_authority = _structured_projection_records()

    class LegacyVerifier:
        def verify_legacy_bootstrap_v3_runtime_projection(
            self, candidate, *, revision, records, grant,
        ):
            assert candidate == projection
            assert revision == 1
            assert records == (projection,)
            assert grant.rows
            return verification

    plane = MemoryPlaneService()
    _linearized_snapshot(monkeypatch, plane, 1, (projection,))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task",
        host_state_id="state",
        rows=(ScopedNamespaceGrantRow(
            domain=MemoryDomain.SEMANTIC,
            task_id="task",
            user_id="alice",
            agent_id="assistant",
        ),),
        expires_at=now + timedelta(minutes=1),
    )
    service = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority)
    service._semantic_atomic_store = LegacyVerifier()

    result = service.retrieve_context(_request(), opaque_host_ingress=handle)

    assert result.status is expected_status
    if verification == "verified":
        assert tuple(item.record_id for item in result.mandatory_items) == (projection.memory_id,)
    else:
        assert result.mandatory_items == ()
        assert result.optional_items == ()


def test_inaccessible_legacy_corruption_does_not_reach_the_legacy_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scope filtering precedes the legacy proof over an untrusted closure."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, _binding, _states, _read_authority = _structured_projection_records()
    inaccessible = projection.model_copy(update={
        "memory_id": "mem:bootstrap-v3:runtime-claim:" + "e" * 64,
        "task_id": "other-task",
        "content": {"runtime_context_projection_kind": "bootstrap_v3_claim_assertion"},
    })
    calls: list[CanonicalMemoryRecord] = []

    class LegacyVerifier:
        def verify_legacy_bootstrap_v3_runtime_projection(
            self, candidate, *, revision, records, grant,
        ):
            calls.append(candidate)
            return "unavailable"

    plane = MemoryPlaneService()
    _linearized_snapshot(monkeypatch, plane, 17, (projection, inaccessible))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task", host_state_id="state",
        rows=(ScopedNamespaceGrantRow(
            domain=MemoryDomain.SEMANTIC, task_id="task", user_id="alice", agent_id="assistant",
        ),),
        expires_at=now + timedelta(minutes=1),
    )
    service = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority)
    service._semantic_atomic_store = LegacyVerifier()

    result = service.retrieve_context(_request(), opaque_host_ingress=handle)

    assert result.status is ScopedContextStatus.UNAVAILABLE
    assert calls == [projection]


def test_new_structured_projection_uses_one_linearized_catalog_snapshot(monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    projection, binding, active_states, read_authority = _structured_projection_records(active=True)
    plane = MemoryPlaneService()
    _linearized_snapshot(monkeypatch, plane, 1, (projection, binding, *active_states))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = _structured_read_handle(authority, now=now, read_authority=read_authority)
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle,
    )
    assert result.status is ScopedContextStatus.PARTIAL_OPTIONAL
    assert [item.record_id for item in result.mandatory_items] == [projection.memory_id]


def test_pre_catalog_legacy_context_remains_on_existing_scoped_read_path() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    legacy = CanonicalMemoryRecord(
        memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="legacy context",
        status=CommitStatus.COMMITTED, task_id="task", source_kind="legacy",
    )
    plane.write_records((legacy,))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task", host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle,
    )
    assert result.status is ScopedContextStatus.COMPLETE
    assert [item.record_id for item in result.mandatory_items] == [legacy.memory_id]


def test_missing_optional_provenance_is_reported_with_capped_identifiers() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    plane.write_records((
        CanonicalMemoryRecord(memory_id="semantic:one", domain=MemoryDomain.SEMANTIC, text="context value", status=CommitStatus.COMMITTED, task_id="task", source_kind="test"),
        CanonicalMemoryRecord(memory_id="semantic:missing-source", domain=MemoryDomain.SEMANTIC, text="context missing", status=CommitStatus.COMMITTED, task_id="task", source_kind="test", source_record_ids=("raw:missing",)),
    ))
    authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = authority.provision(
        host_task_id="task", host_state_id="state",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task"),),
        expires_at=now + timedelta(minutes=1),
    )
    result = ProviderMemoryService(memory_plane=plane, scoped_read_authority=authority).retrieve_context(
        _request(), opaque_host_ingress=handle
    )
    omission = next(item for item in result.omissions if item.reason.value == "provenance_unavailable")
    assert omission.omitted_count == 1
    assert omission.omitted_record_ids == ("semantic:missing-source",)

    common = {
        "channel": ScopedContextChannel.SEMANTIC_BM25,
        "reason": ScopedOmissionReason.OPTIONAL_LIMIT,
    }
    assert ScopedContextOmission(
        **common, omitted_count=0, omitted_record_ids=(), identifiers_truncated=False
    ).omitted_count == 0
    assert ScopedContextOmission(
        **common, omitted_count=2, omitted_record_ids=("semantic:one",), identifiers_truncated=True
    ).omitted_record_ids == ("semantic:one",)
    with pytest.raises(ValueError, match="nonblank"):
        ScopedContextOmission(
            **common, omitted_count=1, omitted_record_ids=(" ",), identifiers_truncated=False
        )
    with pytest.raises(ValueError, match="unique"):
        ScopedContextOmission(
            **common, omitted_count=2, omitted_record_ids=("semantic:one", "semantic:one"), identifiers_truncated=False
        )
    with pytest.raises(ValueError, match="cannot be less"):
        ScopedContextOmission(
            **common, omitted_count=1, omitted_record_ids=("semantic:one", "semantic:two"), identifiers_truncated=False
        )
    with pytest.raises(ValueError, match="identifiers_truncated"):
        ScopedContextOmission(
            **common, omitted_count=2, omitted_record_ids=("semantic:one",), identifiers_truncated=False
        )
    with pytest.raises(ValueError, match="identifiers_truncated"):
        ScopedContextOmission(
            **common, omitted_count=1, omitted_record_ids=("semantic:one",), identifiers_truncated=True
        )
