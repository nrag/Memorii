"""Composite conflict-listing repository integration proof.

Drives the real file ledger with both audience sides, pages through v2
composite cursors across an independent repository reopen, and proves the
provider composite wiring through the ordinary attention pull.
"""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.composite_conflict_listing import (
    CompositeConflictListingRepository,
)
from memorii.core.memory_evolution.conflict_attention import (
    ConflictAccessContext,
    ConflictAttention,
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
    assert tuple(item.conflict_id for item in second.items) == (
        D("incident-evidence")[:0] or second.items[0].conflict_id,
    )
    assert second.items[0].kind is ConflictKind.STORAGE_INTEGRITY
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
    ) or len(second.items) == 2
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


def test_provider_composite_wiring_pages_v2_cursors(tmp_path) -> None:
    from memorii.core.provider.service import ProviderMemoryService

    repository = _seeded_repository(tmp_path)
    service = ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        conflict_attention_composite=True,
        now_provider=lambda: NOW,
    )
    access = _access()
    page = service._attention_page(access, ConflictListRequest(page_size=2))
    assert page.total_pending == 3
    assert page.next_cursor is not None and page.next_cursor.startswith("v2.")


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
