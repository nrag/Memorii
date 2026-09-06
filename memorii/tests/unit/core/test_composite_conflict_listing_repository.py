"""Composite conflict-listing repository integration proof.

Drives the real file ledger with both audience sides, pages through v2
composite cursors across an independent repository reopen, and proves the
provider composite wiring through the ordinary attention pull.
"""

import fcntl
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Event, Thread, current_thread

import pytest
from memorii.core.memory_evolution.composite_conflict_listing import (
    CompositeConflictListingRepository,
)
from memorii.core.memory_evolution.conflict_attention import (
    ConflictAccessContext,
    ConflictAttention,
    ConflictAttentionPage,
    ConflictAudience,
    ConflictKind,
    ConflictListRequest,
    ConflictResolutionOption,
    ConflictStatus,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    ConflictAttentionReadError,
    ConflictCursorKey,
    FileConflictAttentionRepository,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)
D = lambda text: sha256(text.encode()).hexdigest()  # noqa: E731


def _key() -> ConflictCursorKey:
    return ConflictCursorKey(
        key_id="key-1",
        key_epoch=1,
        secret=b"x" * 32,
        valid_from=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=1),
        signing=True,
    )


def _semantic_attention(index: int) -> ConflictAttention:
    return ConflictAttention(
        conflict_id=f"conflict-semantic-{index}",
        conflict_revision=D(f"semantic-revision:{index}"),
        kind=ConflictKind.SEMANTIC_DISAGREEMENT,
        audience=ConflictAudience.USER,
        status=ConflictStatus.OPEN,
        question="Choose",
        options=(
            ConflictResolutionOption(
                candidate_id=f"candidate-{index}-a",
                label="a",
                statement="a",
                candidate_digest=D(f"candidate:{index}:a"),
            ),
            ConflictResolutionOption(
                candidate_id=f"candidate-{index}-b",
                label="b",
                statement="b",
                candidate_digest=D(f"candidate:{index}:b"),
            ),
        ),
        created_at=NOW,
        creation_coordinate=index,
        scope_digest=D(f"semantic-scope:{index}"),
    )


def _access() -> ConflictAccessContext:
    return ConflictAccessContext(
        tenant_id="tenant:a",
        principal_id="principal:a",
        principal_binding_digest=D("binding"),
        authorized_scope_ids=("scope:a",),
        scope_digest=D("scopes"),
        authorization_snapshot_digest=D("authz"),
    )


class _ProviderAccessResolver:
    def resolve(
        self, host_ingress: AuthenticatedHostIngress, server_time: datetime
    ) -> AuthenticatedIngressContext:
        del host_ingress, server_time
        binding = DeliveryPrincipalBinding.create(
            principal_subject_id="principal:a",
            tenant_partition_id="tenant:a",
            provider_identity="hermes",
        )
        scopes = RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:a", scopes=("scope:a",)
        )
        return AuthenticatedIngressContext(
            delivery_principal_binding=binding,
            required_outcome_scopes=scopes,
            current_authorized_scopes=scopes,
        )


def _provider_ingress() -> AuthenticatedHostIngress:
    return AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=NOW,
    )


def _integrity_conflict_id() -> str:
    # Mirrors the ledger's domain-separated incident conflict id.
    from memorii.core.memory_evolution.conflict_attention_repository import (
        _INTEGRITY_CONFLICT_ID_DOMAIN,
        _digest,
    )

    return _digest(
        _INTEGRITY_CONFLICT_ID_DOMAIN,
        {
            "repository_id": "integrity-repository",
            "incident_evidence_digest": D("incident-evidence"),
        },
    )


def _seeded_repository(tmp_path, clock=None) -> FileConflictAttentionRepository:
    current = clock or [NOW]
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl",
        keys=(_key(),),
        now_provider=lambda: current[0],
    )
    for index in range(2):
        repository.append_open(
            _semantic_attention(index), scope_ids=("scope:a",)
        )
    repository.append_sanitized_storage_integrity_incident(
        repository_id="integrity-repository",
        incident_evidence_digest=D("incident-evidence"),
        frozen_scope_ids=("scope:a",),
        recorded_at=NOW,
    )
    return repository


def test_composite_pages_both_children_through_v2_cursors(tmp_path) -> None:
    repository = _seeded_repository(tmp_path)
    composite = CompositeConflictListingRepository(repository)

    first = composite.list_conflicts(
        _access(), ConflictListRequest(page_size=2)
    )
    assert first.total_pending == 3
    assert tuple(item.conflict_id for item in first.items) == (
        "conflict-semantic-0",
        "conflict-semantic-1",
    )
    assert first.next_cursor is not None and first.next_cursor.startswith("v2.")

    second = composite.list_conflicts(
        _access(),
        ConflictListRequest(page_size=2, cursor=first.next_cursor),
    )
    assert len(second.items) == 1
    assert second.items[0].kind is ConflictKind.STORAGE_INTEGRITY
    assert second.items[0].conflict_id == _integrity_conflict_id()
    assert second.next_cursor is None


def test_composite_continuation_survives_repository_reopen(tmp_path) -> None:
    repository = _seeded_repository(tmp_path)
    composite = CompositeConflictListingRepository(repository)
    first = composite.list_conflicts(
        _access(), ConflictListRequest(page_size=1)
    )
    assert first.next_cursor is not None

    reopened = CompositeConflictListingRepository(
        FileConflictAttentionRepository(
            repository._path, keys=(_key(),), now_provider=lambda: NOW
        )
    )
    second = reopened.list_conflicts(
        _access(),
        ConflictListRequest(page_size=5, cursor=first.next_cursor),
    )
    assert tuple(item.conflict_id for item in second.items) == (
        "conflict-semantic-1",
        _integrity_conflict_id(),
    )
    assert second.items[1].kind is ConflictKind.STORAGE_INTEGRITY
    assert second.total_pending == 3


def test_composite_rejects_tampered_and_cross_scope_cursors(tmp_path) -> None:
    repository = _seeded_repository(tmp_path)
    composite = CompositeConflictListingRepository(repository)
    first = composite.list_conflicts(
        _access(), ConflictListRequest(page_size=1)
    )
    assert first.next_cursor is not None
    with pytest.raises(ConflictAttentionReadError, match="invalid_conflict_cursor"):
        composite.list_conflicts(
            _access(),
            ConflictListRequest(
                page_size=1, cursor=first.next_cursor[:-4] + "AAAA"
            ),
        )
    other_access = _access().model_copy(
        update={"principal_id": "principal:other"}
    )
    with pytest.raises(ConflictAttentionReadError, match="invalid_conflict_cursor"):
        composite.list_conflicts(
            other_access,
            ConflictListRequest(page_size=1, cursor=first.next_cursor),
        )
    with pytest.raises(ConflictAttentionReadError, match="invalid_cursor_scope"):
        composite.list_conflicts(
            _access(),
            ConflictListRequest(
                page_size=1,
                cursor=first.next_cursor,
                scope_ids=("scope:other",),
            ),
        )


def test_public_provider_composite_inherits_ledger_clock_across_reopen(tmp_path) -> None:
    from memorii.core.provider.service import ProviderMemoryService

    repository = _seeded_repository(tmp_path)
    repository.append_open(_semantic_attention(3), scope_ids=("scope:a",))
    service = ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        conflict_attention_composite=True,
        authenticated_ingress_resolver=_ProviderAccessResolver(),
        now_provider=lambda: NOW + timedelta(days=90),
    )
    first = service.prefetch_with_attention(
        "query", authenticated_host_ingress=_provider_ingress()
    )
    page = first.attention_required
    assert page.total_pending == 4
    assert len(page.items) == 3
    assert page.next_cursor is not None and page.next_cursor.startswith("v2.")

    reopened = ProviderMemoryService(
        conflict_attention_repository=FileConflictAttentionRepository(
            repository._path, keys=(_key(),), now_provider=lambda: NOW
        ),
        conflict_attention_enabled=True,
        conflict_attention_composite=True,
        authenticated_ingress_resolver=_ProviderAccessResolver(),
        now_provider=lambda: NOW + timedelta(days=180),
    )
    continuation = reopened.handle_tool_call_with_attention(
        "memorii_list_conflicts",
        {"cursor": page.next_cursor, "page_size": 3},
        authenticated_host_ingress=_provider_ingress(),
    )
    assert continuation.legacy_result.ok is True
    assert continuation.legacy_result.result["total_pending"] == 4
    assert len(continuation.legacy_result.result["items"]) == 1


def _provider_service(repository, *, composite: bool):
    from memorii.core.provider.service import ProviderMemoryService

    return ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        conflict_attention_composite=composite,
        authenticated_ingress_resolver=_ProviderAccessResolver(),
        now_provider=lambda: NOW + timedelta(days=90),
    )


def test_public_composite_short_key_failure_never_appends(tmp_path) -> None:
    clock = [NOW]
    key = ConflictCursorKey(
        key_id="key-1", key_epoch=1, secret=b"x" * 32,
        valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(seconds=1000),
        signing=True,
    )
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl", keys=(key,), now_provider=lambda: clock[0]
    )
    for index in range(4):
        repository.append_open(_semantic_attention(index), scope_ids=("scope:a",))
    clock[0] = NOW + timedelta(seconds=200)
    service = _provider_service(repository, composite=True)
    before = repository._path.read_bytes()
    for _ in range(2):
        with pytest.raises(ConflictAttentionReadError, match="conflict_cursor_key_unavailable"):
            service.prefetch_with_attention("query", authenticated_host_ingress=_provider_ingress())
        assert repository._path.read_bytes() == before


@pytest.mark.parametrize("item_count", [0, 1])
def test_public_nonpaginated_short_key_prefetch_needs_no_cursor(tmp_path, item_count: int) -> None:
    clock = [NOW]
    key = ConflictCursorKey(
        key_id="key-1", key_epoch=1, secret=b"x" * 32,
        valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(seconds=1000),
        signing=True,
    )
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl", keys=(key,), now_provider=lambda: clock[0]
    )
    for index in range(item_count):
        repository.append_open(_semantic_attention(index), scope_ids=("scope:a",))
    clock[0] = NOW + timedelta(seconds=200)
    page = _provider_service(repository, composite=True).prefetch_with_attention(
        "query", authenticated_host_ingress=_provider_ingress()
    ).attention_required
    assert len(page.items) == item_count
    assert page.next_cursor is None


def test_public_cross_protocol_cursors_reject_without_ledger_fallback(tmp_path) -> None:
    repository = _seeded_repository(tmp_path)
    repository.append_open(_semantic_attention(3), scope_ids=("scope:a",))
    direct = _provider_service(repository, composite=False)
    access = direct._conflict_access(_provider_ingress())
    assert access is not None
    v1 = repository.list_conflicts(access, ConflictListRequest(page_size=1)).next_cursor
    assert v1 is not None and v1.startswith("v1.")
    before = repository._path.read_bytes()
    composite = _provider_service(repository, composite=True)
    result = composite.handle_tool_call_with_attention(
        "memorii_list_conflicts", {"cursor": v1}, authenticated_host_ingress=_provider_ingress()
    )
    assert result.legacy_result.error == "invalid_conflict_cursor"
    assert repository._path.read_bytes() == before
    v2 = composite.prefetch_with_attention("query", authenticated_host_ingress=_provider_ingress()).attention_required.next_cursor
    assert v2 is not None and v2.startswith("v2.")
    before = repository._path.read_bytes()
    result = direct.handle_tool_call_with_attention(
        "memorii_list_conflicts", {"cursor": v2}, authenticated_host_ingress=_provider_ingress()
    )
    assert result.legacy_result.error == "invalid_conflict_cursor"
    assert repository._path.read_bytes() == before


def test_atomic_prepare_linearizes_page_boundary_before_concurrent_append(tmp_path, monkeypatch) -> None:
    clock = [NOW]
    key = ConflictCursorKey(
        key_id="key-1", key_epoch=1, secret=b"x" * 32,
        valid_from=NOW - timedelta(days=1), expires_at=NOW + timedelta(seconds=1000),
        signing=True,
    )
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl", keys=(key,), now_provider=lambda: clock[0]
    )
    repository.append_open(_semantic_attention(0), scope_ids=("scope:a",))
    clock[0] = NOW + timedelta(seconds=200)
    entered, release = Event(), Event()
    decode = repository._decode_ledger_lines

    def paused(lines):
        entered.set()
        release.wait(timeout=2)
        return decode(lines)

    monkeypatch.setattr(repository, "_decode_ledger_lines", paused)
    result: list[ConflictAttentionPage] = []
    failure: list[BaseException] = []

    def list_page() -> None:
        try:
            result.append(_provider_service(repository, composite=True).prefetch_with_attention(
                "query", authenticated_host_ingress=_provider_ingress()
            ).attention_required)
        except BaseException as exc:  # pragma: no cover - asserted below
            failure.append(exc)

    reader = Thread(target=list_page)
    writer_attempted = Event()
    writer_done = Event()

    def append() -> None:
        repository.append_open(_semantic_attention(1), scope_ids=("scope:a",))
        writer_done.set()

    writer = Thread(target=append)
    flock = fcntl.flock

    def observed_flock(handle, operation):
        if current_thread() is writer and operation & fcntl.LOCK_EX:
            writer_attempted.set()
        return flock(handle, operation)

    monkeypatch.setattr(fcntl, "flock", observed_flock)
    reader.start()
    assert entered.wait(timeout=2)
    writer.start()
    assert writer_attempted.wait(timeout=2)
    assert not writer_done.is_set()
    release.set()
    reader.join(timeout=2)
    writer.join(timeout=2)
    assert not failure
    assert len(result) == 1
    page = result[0]
    assert page.total_pending == 1
    assert page.next_cursor is None
    assert writer_done.is_set()
    assert len(repository._read_all()) == 5


def test_fresh_cursor_uses_post_lock_issuance_time(tmp_path, monkeypatch) -> None:
    clock = [NOW]
    key = ConflictCursorKey(
        key_id="key-1",
        key_epoch=1,
        secret=b"x" * 32,
        valid_from=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=1),
        signing=True,
    )
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl",
        keys=(key,),
        now_provider=lambda: clock[0],
    )
    for index in range(4):
        repository.append_open(_semantic_attention(index), scope_ids=("scope:a",))

    entered, release = Event(), Event()
    decode = repository._decode_ledger_lines

    def paused(lines):
        entered.set()
        assert release.wait(timeout=2)
        return decode(lines)

    monkeypatch.setattr(repository, "_decode_ledger_lines", paused)
    service = _provider_service(repository, composite=True)
    result: list[ConflictAttentionPage] = []

    def list_page() -> None:
        result.append(
            service.prefetch_with_attention(
                "query", authenticated_host_ingress=_provider_ingress()
            ).attention_required
        )

    reader = Thread(target=list_page)
    reader.start()
    assert entered.wait(timeout=2)
    clock[0] = NOW + timedelta(seconds=901)
    release.set()
    reader.join(timeout=2)
    assert len(result) == 1
    first = result[0]
    assert first.next_cursor is not None

    continued = service.handle_tool_call_with_attention(
        "memorii_list_conflicts",
        {"cursor": first.next_cursor},
        authenticated_host_ingress=_provider_ingress(),
    )
    assert continued.legacy_result.ok is True
    assert continued.legacy_result.result["total_pending"] == 4
    assert len(continued.legacy_result.result["items"]) == 1


def test_continuation_revalidates_time_after_locked_read(tmp_path, monkeypatch) -> None:
    clock = [NOW]
    key = ConflictCursorKey(
        key_id="key-1",
        key_epoch=1,
        secret=b"x" * 32,
        valid_from=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=1),
        signing=True,
    )
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl",
        keys=(key,),
        now_provider=lambda: clock[0],
    )
    for index in range(4):
        repository.append_open(_semantic_attention(index), scope_ids=("scope:a",))
    service = _provider_service(repository, composite=True)
    first = service.prefetch_with_attention(
        "query", authenticated_host_ingress=_provider_ingress()
    ).attention_required
    assert first.next_cursor is not None

    entered, release = Event(), Event()
    decode = repository._decode_ledger_lines

    def paused(lines):
        entered.set()
        assert release.wait(timeout=2)
        return decode(lines)

    monkeypatch.setattr(repository, "_decode_ledger_lines", paused)
    result = []

    def continue_page() -> None:
        result.append(
            service.handle_tool_call_with_attention(
                "memorii_list_conflicts",
                {"cursor": first.next_cursor, "page_size": 1},
                authenticated_host_ingress=_provider_ingress(),
            )
        )

    reader = Thread(target=continue_page)
    reader.start()
    assert entered.wait(timeout=2)
    clock[0] = NOW + timedelta(seconds=901)
    release.set()
    reader.join(timeout=2)
    assert len(result) == 1
    assert result[0].legacy_result.error == "invalid_conflict_cursor"


def test_composite_malformed_ledger_is_non_disclosing_without_mutation(tmp_path) -> None:
    repository = _seeded_repository(tmp_path)
    repository._path.write_text("{broken\n", encoding="utf-8")
    before = repository._path.read_bytes()
    with pytest.raises(ConflictAttentionReadError, match="conflict_attention_corrupt"):
        CompositeConflictListingRepository(repository).list_conflicts(
            _access(), ConflictListRequest(page_size=1)
        )
    assert repository._path.read_bytes() == before
    result = _provider_service(repository, composite=True).handle_tool_call_with_attention(
        "memorii_list_conflicts", {}, authenticated_host_ingress=_provider_ingress()
    )
    assert result.legacy_result.error == "conflict_attention_corrupt"
    assert repository._path.read_bytes() == before



def test_provider_composite_requires_file_ledger_child() -> None:
    from memorii.core.provider.service import ProviderMemoryService

    class _ForeignRepository:
        def list_conflicts(self, access, request):  # pragma: no cover
            raise AssertionError("must not be called")

    service = ProviderMemoryService(
        conflict_attention_repository=_ForeignRepository(),
        conflict_attention_enabled=True,
        conflict_attention_composite=True,
        now_provider=lambda: NOW,
    )
    with pytest.raises(RuntimeError, match="file ledger child"):
        service._attention_page(_access(), ConflictListRequest(page_size=1))


def test_scoped_composite_listing_continues_past_first_page(tmp_path) -> None:
    wide = ConflictAccessContext(
        tenant_id="tenant:a",
        principal_id="principal:a",
        principal_binding_digest=D("binding"),
        authorized_scope_ids=("scope:a", "scope:b"),
        scope_digest=D("scopes"),
        authorization_snapshot_digest=D("authz"),
    )
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl",
        keys=(_key(),),
        now_provider=lambda: NOW,
    )
    for index in range(2):
        repository.append_open(_semantic_attention(index), scope_ids=("scope:a",))
    composite = CompositeConflictListingRepository(repository)

    first = composite.list_conflicts(
        wide,
        ConflictListRequest(page_size=1, scope_ids=("scope:a",)),
    )
    assert first.total_pending == 2
    assert first.next_cursor is not None
    second = composite.list_conflicts(
        wide,
        # The retained scope set is restated byte-for-byte: the exact
        # continuation shape the scoped-listing defect falsely rejected.
        ConflictListRequest(
            page_size=1, cursor=first.next_cursor, scope_ids=("scope:a",)
        ),
    )
    assert tuple(item.conflict_id for item in second.items) == (
        "conflict-semantic-1",
    )
    assert second.total_pending == 2


def test_composite_cursor_emission_maps_to_closed_error_boundary(tmp_path) -> None:
    clock = [NOW]
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl",
        keys=(
            ConflictCursorKey(
                key_id="key-1",
                key_epoch=1,
                secret=b"x" * 32,
                valid_from=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(seconds=1000),
                signing=True,
            ),
        ),
        now_provider=lambda: clock[0],
    )
    for index in range(2):
        repository.append_open(_semantic_attention(index), scope_ids=("scope:a",))
    composite = CompositeConflictListingRepository(repository)
    clock[0] = NOW + timedelta(seconds=200)
    rows_before = len(repository._read_all())
    for _ in range(2):
        with pytest.raises(
            ConflictAttentionReadError, match="conflict_cursor_key_unavailable"
        ):
            composite.list_conflicts(_access(), ConflictListRequest(page_size=1))
        assert len(repository._read_all()) == rows_before


@pytest.mark.parametrize("item_count", [0, 1])
def test_composite_nonpaginated_listing_does_not_require_signing_key(
    tmp_path, item_count: int
) -> None:
    clock = [NOW]
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl",
        keys=(
            ConflictCursorKey(
                key_id="key-1", key_epoch=1, secret=b"x" * 32,
                valid_from=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(seconds=1000), signing=True,
            ),
        ),
        now_provider=lambda: clock[0],
    )
    for index in range(item_count):
        repository.append_open(_semantic_attention(index), scope_ids=("scope:a",))
    clock[0] = NOW + timedelta(seconds=200)

    page = CompositeConflictListingRepository(repository).list_conflicts(
        _access(), ConflictListRequest(page_size=1)
    )
    assert len(page.items) == item_count
    assert page.next_cursor is None


def test_composite_explicit_clock_override_remains_authoritative(tmp_path) -> None:
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl",
        keys=(
            ConflictCursorKey(
                key_id="key-1",
                key_epoch=1,
                secret=b"x" * 32,
                valid_from=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(seconds=1000),
                signing=True,
            ),
        ),
        now_provider=lambda: NOW,
    )
    for index in range(2):
        repository.append_open(_semantic_attention(index), scope_ids=("scope:a",))
    composite = CompositeConflictListingRepository(
        repository, now_provider=lambda: NOW + timedelta(seconds=200)
    )

    with pytest.raises(
        ConflictAttentionReadError, match="conflict_cursor_key_unavailable"
    ):
        composite.list_conflicts(_access(), ConflictListRequest(page_size=1))


def test_retained_composite_snapshot_excludes_post_snapshot_conflicts(tmp_path) -> None:
    repository = _seeded_repository(tmp_path)
    composite = CompositeConflictListingRepository(repository)
    first = composite.list_conflicts(
        _access(), ConflictListRequest(page_size=1)
    )
    assert first.total_pending == 3
    repository.append_open(
        _semantic_attention(9), scope_ids=("scope:a",)
    )
    second = composite.list_conflicts(
        _access(),
        ConflictListRequest(page_size=10, cursor=first.next_cursor),
    )
    assert second.total_pending == 3
    assert "conflict-semantic-9" not in tuple(
        item.conflict_id for item in second.items
    )


def test_composite_listing_with_only_semantic_children(tmp_path) -> None:
    repository = FileConflictAttentionRepository(
        tmp_path / "conflict-attention.jsonl",
        keys=(_key(),),
        now_provider=lambda: NOW,
    )
    repository.append_open(_semantic_attention(0), scope_ids=("scope:a",))
    composite = CompositeConflictListingRepository(repository)
    page = composite.list_conflicts(_access(), ConflictListRequest(page_size=10))
    assert page.total_pending == 1
    assert page.items[0].conflict_id == "conflict-semantic-0"
    assert page.next_cursor is None
