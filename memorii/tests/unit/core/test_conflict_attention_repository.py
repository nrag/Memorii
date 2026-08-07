from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from memorii.core.memory_evolution.conflict_attention import (
    ConflictAccessContext,
    ConflictAttention,
    ConflictAudience,
    ConflictKind,
    ConflictListingCursorClaims,
    ConflictListingSnapshot,
    ConflictListRequest,
    ConflictResolutionOption,
    ConflictStatus,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    ConflictAttentionReadError,
    ConflictCursorKey,
    FileConflictAttentionRepository,
)
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value

NOW = datetime(2026, 8, 2, tzinfo=UTC)
_CURSOR_DOMAIN = b"memorii.conflict-listing-cursor.v1\0"


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _access(
    *,
    tenant_id: str = "tenant",
    principal_id: str = "principal",
    principal_binding_digest: str | None = None,
    authorized_scope_ids: tuple[str, ...] = ("a", "b", "c"),
    scope_digest: str | None = None,
    authorization_snapshot_digest: str | None = None,
) -> ConflictAccessContext:
    scope_label = ",".join(authorized_scope_ids)
    return ConflictAccessContext(
        tenant_id=tenant_id,
        principal_id=principal_id,
        principal_binding_digest=principal_binding_digest or _digest(f"binding:{tenant_id}:{principal_id}"),
        authorized_scope_ids=authorized_scope_ids,
        scope_digest=scope_digest or _digest(f"scope:{tenant_id}:{scope_label}"),
        authorization_snapshot_digest=authorization_snapshot_digest or _digest(f"auth:{tenant_id}:{scope_label}"),
    )


def _attention(index: int) -> ConflictAttention:
    def option(suffix: str) -> ConflictResolutionOption:
        return ConflictResolutionOption(
            candidate_id=f"candidate-{index}-{suffix}",
            label=suffix,
            statement=suffix,
            candidate_digest=_digest(f"candidate:{index}:{suffix}"),
        )

    return ConflictAttention(
        conflict_id=f"conflict-{index}",
        conflict_revision=_digest(f"revision:{index}"),
        kind=ConflictKind.SEMANTIC_DISAGREEMENT,
        audience=ConflictAudience.USER,
        status=ConflictStatus.OPEN,
        question="Choose",
        options=(option("a"), option("b")),
        created_at=NOW,
        creation_coordinate=index,
        scope_digest=_digest(f"attention-scope:{index}"),
    )


def _key(
    key_id: str = "key-1",
    *,
    epoch: int = 1,
    secret: bytes = b"x" * 32,
    signing: bool = True,
    revoked: bool = False,
    valid_from: datetime = NOW - timedelta(days=1),
    expires_at: datetime = NOW + timedelta(days=1),
) -> ConflictCursorKey:
    return ConflictCursorKey(
        key_id=key_id,
        key_epoch=epoch,
        secret=secret,
        valid_from=valid_from,
        expires_at=expires_at,
        signing=signing,
        revoked=revoked,
    )


def _repository(
    path: Path,
    *,
    keys: tuple[ConflictCursorKey, ...] | None = None,
    clock: list[datetime] | None = None,
) -> FileConflictAttentionRepository:
    current = clock or [NOW]
    return FileConflictAttentionRepository(
        path,
        keys=keys or (_key(),),
        now_provider=lambda: current[0],
    )


def _cursor_claims(cursor: str) -> ConflictListingCursorClaims:
    encoded = cursor.split(".")[1]
    raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    return ConflictListingCursorClaims.model_validate_json(json.dumps(decode_typed_value(raw)))


def _seed_scoped(repository: FileConflictAttentionRepository) -> None:
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.append_open(_attention(1), scope_ids=("b",))
    repository.append_open(_attention(2), scope_ids=("c",))
    repository.append_open(_attention(3), scope_ids=("a", "b"))


def test_listing_subset_retains_complete_authorization_across_restart_and_variable_pages(tmp_path: Path) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path)
    _seed_scoped(repository)
    access = _access()

    first = repository.list_conflicts(
        access,
        ConflictListRequest(scope_ids=("a", "b"), page_size=1),
    )
    assert [item.conflict_id for item in first.items] == ["conflict-0"]
    assert first.total_pending == 3
    assert first.next_cursor is not None
    claims = _cursor_claims(first.next_cursor)
    assert claims.authorized_scope_ids == ("a", "b", "c")
    assert claims.listing_scope_ids == ("a", "b")

    repository.append_open(_attention(4), scope_ids=("a",))
    restarted = _repository(path)
    omitted = restarted.list_conflicts(access, ConflictListRequest(page_size=2, cursor=first.next_cursor))
    equal = restarted.list_conflicts(
        access,
        ConflictListRequest(scope_ids=("a", "b"), page_size=1, cursor=first.next_cursor),
    )
    assert [item.conflict_id for item in omitted.items] == ["conflict-1", "conflict-3"]
    assert [item.conflict_id for item in equal.items] == ["conflict-1"]
    assert omitted.total_pending == equal.total_pending == 3
    assert "conflict-2" not in {item.conflict_id for item in omitted.items}
    assert "conflict-4" not in {item.conflict_id for item in omitted.items}


@pytest.mark.parametrize("changed_scopes", [("a",), ("a", "b", "c")])
def test_changed_continuation_scope_rejects_before_read_or_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_scopes: tuple[str, ...],
) -> None:
    repository = _repository(tmp_path / "conflicts.jsonl")
    _seed_scoped(repository)
    cursor = repository.list_conflicts(
        _access(),
        ConflictListRequest(scope_ids=("a", "b"), page_size=1),
    ).next_cursor
    assert cursor is not None

    monkeypatch.setattr(repository, "_read_all", lambda: pytest.fail("payload read must not occur"))
    monkeypatch.setattr(repository, "_append", lambda _value: pytest.fail("append must not occur"))
    with pytest.raises(ConflictAttentionReadError, match="^invalid_cursor_scope$"):
        repository.list_conflicts(
            _access(),
            ConflictListRequest(scope_ids=changed_scopes, page_size=1, cursor=cursor),
        )


@pytest.mark.parametrize(
    "variant",
    ["tenant", "principal", "binding", "authorization", "scope-expansion", "scope-reduction"],
)
def test_cursor_rejects_every_current_authorization_change_before_payload_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
) -> None:
    repository = _repository(tmp_path / "conflicts.jsonl")
    _seed_scoped(repository)
    cursor = repository.list_conflicts(_access(), ConflictListRequest(page_size=1)).next_cursor
    assert cursor is not None
    changed = {
        "tenant": _access(tenant_id="tenant-2"),
        "principal": _access(principal_id="principal-2"),
        "binding": _access(principal_binding_digest=_digest("different-binding")),
        "authorization": _access(authorization_snapshot_digest=_digest("different-authorization")),
        "scope-expansion": _access(authorized_scope_ids=("a", "b", "c", "d")),
        "scope-reduction": _access(authorized_scope_ids=("a", "b")),
    }[variant]
    monkeypatch.setattr(repository, "_read_all", lambda: pytest.fail("payload read must not occur"))
    monkeypatch.setattr(repository, "_append", lambda _value: pytest.fail("append must not occur"))
    with pytest.raises(ConflictAttentionReadError, match="^invalid_conflict_cursor$"):
        repository.list_conflicts(changed, ConflictListRequest(page_size=1, cursor=cursor))


def test_expiry_boundary_and_future_issued_cursor_reject_before_payload_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "conflicts.jsonl"
    clock = [NOW]
    repository = _repository(path, clock=clock)
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.append_open(_attention(1), scope_ids=("a",))
    cursor = repository.list_conflicts(_access(), ConflictListRequest(page_size=1)).next_cursor
    assert cursor is not None
    clock[0] = NOW + timedelta(seconds=900)
    monkeypatch.setattr(repository, "_read_all", lambda: pytest.fail("payload read must not occur"))
    with pytest.raises(ConflictAttentionReadError, match="^invalid_conflict_cursor$"):
        repository.list_conflicts(_access(), ConflictListRequest(page_size=1, cursor=cursor))

    future_clock = [NOW + timedelta(seconds=60)]
    future = _repository(tmp_path / "future.jsonl", clock=future_clock)
    future.append_open(_attention(0), scope_ids=("a",))
    future.append_open(_attention(1), scope_ids=("a",))
    future_cursor = future.list_conflicts(_access(), ConflictListRequest(page_size=1)).next_cursor
    assert future_cursor is not None
    verifier = _repository(tmp_path / "future.jsonl", clock=[NOW])
    monkeypatch.setattr(verifier, "_read_all", lambda: pytest.fail("payload read must not occur"))
    with pytest.raises(ConflictAttentionReadError, match="^invalid_conflict_cursor$"):
        verifier.list_conflicts(_access(), ConflictListRequest(page_size=1, cursor=future_cursor))


def test_rotation_accepts_retained_verifier_and_signs_next_cursor_with_active_key(tmp_path: Path) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path, keys=(_key("old", secret=b"o" * 32),))
    for index in range(4):
        repository.append_open(_attention(index), scope_ids=("a",))
    cursor = repository.list_conflicts(_access(), ConflictListRequest(page_size=1)).next_cursor
    assert cursor is not None

    rotated = _repository(
        path,
        keys=(
            _key("old", secret=b"o" * 32, signing=False),
            _key("new", epoch=2, secret=b"n" * 32, signing=True),
        ),
    )
    page = rotated.list_conflicts(_access(), ConflictListRequest(page_size=1, cursor=cursor))
    assert [item.conflict_id for item in page.items] == ["conflict-1"]
    assert page.next_cursor is not None
    assert _cursor_claims(page.next_cursor).key_id == "new"


@pytest.mark.parametrize("old_key_state", ["revoked", "expired"])
def test_revoked_or_expired_retained_key_rejects_without_payload_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old_key_state: str,
) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path, keys=(_key("old", secret=b"o" * 32),))
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.append_open(_attention(1), scope_ids=("a",))
    cursor = repository.list_conflicts(_access(), ConflictListRequest(page_size=1)).next_cursor
    assert cursor is not None
    old = (
        _key("old", secret=b"o" * 32, signing=False, revoked=True)
        if old_key_state == "revoked"
        else _key(
            "old",
            secret=b"o" * 32,
            signing=False,
            expires_at=NOW + timedelta(seconds=899),
        )
    )
    verifier = _repository(
        path,
        keys=(old, _key("new", epoch=2, secret=b"n" * 32)),
    )
    monkeypatch.setattr(verifier, "_read_all", lambda: pytest.fail("payload read must not occur"))
    with pytest.raises(ConflictAttentionReadError, match="^invalid_conflict_cursor$"):
        verifier.list_conflicts(_access(), ConflictListRequest(page_size=1, cursor=cursor))


def test_malformed_tampered_and_noncanonical_cursors_reject_before_payload_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path / "conflicts.jsonl")
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.append_open(_attention(1), scope_ids=("a",))
    cursor = repository.list_conflicts(_access(), ConflictListRequest(page_size=1)).next_cursor
    assert cursor is not None
    replacement = "A" if cursor[-1] != "A" else "B"
    tampered = cursor[:-1] + replacement
    assert tampered != cursor
    version, encoded, _signature = cursor.split(".")
    raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)) + b"\x00"
    mac = hmac.new(b"x" * 32, _CURSOR_DOMAIN + raw, hashlib.sha256).digest()
    noncanonical = (
        f"{version}."
        f"{base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')}."
        f"{base64.urlsafe_b64encode(mac).rstrip(b'=').decode('ascii')}"
    )
    monkeypatch.setattr(repository, "_read_all", lambda: pytest.fail("payload read must not occur"))
    monkeypatch.setattr(repository, "_append", lambda _value: pytest.fail("append must not occur"))
    for invalid in ("invalid", tampered, noncanonical):
        with pytest.raises(ConflictAttentionReadError, match="^invalid_conflict_cursor$"):
            repository.list_conflicts(_access(), ConflictListRequest(page_size=1, cursor=invalid))


def test_unavailable_snapshot_returns_invalid_cursor_without_payload_read_or_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path)
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.append_open(_attention(1), scope_ids=("a",))
    cursor = repository.list_conflicts(_access(), ConflictListRequest(page_size=1)).next_cursor
    assert cursor is not None
    retained = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["record_type"] != "snapshot"
    ]
    path.write_text("\n".join(retained) + "\n", encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(repository, "_read_all", lambda: pytest.fail("conflict payload read must not occur"))
    monkeypatch.setattr(repository, "_append", lambda _value: pytest.fail("fallback snapshot must not be appended"))
    with pytest.raises(ConflictAttentionReadError, match="^invalid_conflict_cursor$"):
        repository.list_conflicts(_access(), ConflictListRequest(page_size=1, cursor=cursor))
    assert path.read_bytes() == before


def test_snapshot_retention_race_is_linearized_before_payload_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path)
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.append_open(_attention(1), scope_ids=("a",))
    cursor = repository.list_conflicts(_access(), ConflictListRequest(page_size=1)).next_cursor
    assert cursor is not None
    retained = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["record_type"] != "snapshot"
    ]
    metadata_validated = Event()
    retention_attempted = Event()
    original_validate = repository._validate_snapshot

    def pause_after_metadata(
        snapshot: ConflictListingSnapshot,
        *,
        claims: ConflictListingCursorClaims,
        access: ConflictAccessContext,
    ) -> ConflictListingSnapshot:
        result = original_validate(snapshot, claims=claims, access=access)
        metadata_validated.set()
        assert retention_attempted.wait(timeout=5)
        return result

    def remove_snapshot() -> None:
        assert metadata_validated.wait(timeout=5)
        with path.open("r+", encoding="utf-8") as handle:
            retention_attempted.set()
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            handle.truncate()
            handle.write("\n".join(retained) + "\n")
            handle.flush()

    monkeypatch.setattr(repository, "_validate_snapshot", pause_after_metadata)
    with ThreadPoolExecutor(max_workers=2) as executor:
        continuation = executor.submit(
            repository.list_conflicts,
            _access(),
            ConflictListRequest(page_size=1, cursor=cursor),
        )
        retention = executor.submit(remove_snapshot)
        assert [item.conflict_id for item in continuation.result(timeout=5).items] == ["conflict-1"]
        retention.result(timeout=5)

    monkeypatch.setattr(repository, "_decode_ledger_lines", lambda _lines: pytest.fail("payload decode must not occur"))
    with pytest.raises(ConflictAttentionReadError, match="^invalid_conflict_cursor$"):
        repository.list_conflicts(_access(), ConflictListRequest(page_size=1, cursor=cursor))


def test_snapshot_digest_is_validated_on_every_ledger_read(tmp_path: Path) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path)
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.list_conflicts(_access(), ConflictListRequest(page_size=1))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    snapshot = next(row for row in rows if row["record_type"] == "snapshot")
    snapshot["snapshot"]["snapshot_digest"] = "0" * 64
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    with pytest.raises(ConflictAttentionReadError, match="^conflict_attention_corrupt$"):
        repository.list_conflicts(_access(), ConflictListRequest(page_size=1))
    assert path.read_bytes() == before


@pytest.mark.parametrize("scope_ids", [(), ("",), ("b", "a"), ("a", "a")])
def test_conflict_scope_ids_are_strict_and_reject_before_append(
    tmp_path: Path,
    scope_ids: tuple[str, ...],
) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        repository.append_open(_attention(0), scope_ids=scope_ids)
    assert path.read_bytes() == before


def test_independent_instances_serialize_concurrent_conflict_introductions(tmp_path: Path) -> None:
    path = tmp_path / "conflicts.jsonl"

    def append(index: int) -> None:
        _repository(path).append_open(_attention(index), scope_ids=("a",))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(append, range(8)))
    page = _repository(path).list_conflicts(_access(), ConflictListRequest(page_size=100))
    assert [item.conflict_id for item in page.items] == [f"conflict-{index}" for index in range(8)]
