"""Real reader/list persistence coverage; resolution transitions belong to the next slice."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.memory_evolution.conflict_attention import (
    ConflictAttention,
    ConflictAudience,
    ConflictKind,
    ConflictResolutionOption,
    ConflictStatus,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    ConflictCursorKey,
    FileConflictAttentionRepository,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.hermes_provider import HermesMemoryProvider

NOW = datetime(2026, 8, 2, tzinfo=UTC)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _attention(index: int) -> ConflictAttention:
    return ConflictAttention(
        conflict_id=f"conflict-{index}",
        conflict_revision=_digest(f"revision:{index}"),
        kind=ConflictKind.SEMANTIC_DISAGREEMENT,
        audience=ConflictAudience.USER,
        status=ConflictStatus.OPEN,
        question="Which value should memory retain?",
        options=(
            ConflictResolutionOption(
                candidate_id=f"candidate-{index}-a",
                label="A",
                statement="A",
                candidate_digest=_digest(f"candidate:{index}:a"),
            ),
            ConflictResolutionOption(
                candidate_id=f"candidate-{index}-b",
                label="B",
                statement="B",
                candidate_digest=_digest(f"candidate:{index}:b"),
            ),
        ),
        created_at=NOW,
        creation_coordinate=index,
        scope_digest=_digest(f"scope:{index}"),
    )


def _key(
    key_id: str,
    *,
    epoch: int,
    secret: bytes,
    signing: bool,
    revoked: bool = False,
) -> ConflictCursorKey:
    return ConflictCursorKey(
        key_id=key_id,
        key_epoch=epoch,
        secret=secret,
        valid_from=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=1),
        signing=signing,
        revoked=revoked,
    )


class _MutableResolver:
    def __init__(self, scopes: tuple[str, ...] = ("a", "b", "c")) -> None:
        self.scopes = scopes
        self.principal_id = "principal"

    def resolve(
        self,
        host_ingress: AuthenticatedHostIngress,
        server_time: datetime,
    ) -> AuthenticatedIngressContext:
        del host_ingress, server_time
        binding = DeliveryPrincipalBinding.create(
            principal_subject_id=self.principal_id,
            tenant_partition_id="tenant",
            provider_identity="hermes",
        )
        scopes = RequiredOutcomeScopeSet.create(tenant_partition_id="tenant", scopes=self.scopes)
        return AuthenticatedIngressContext(
            delivery_principal_binding=binding,
            required_outcome_scopes=scopes,
            current_authorized_scopes=scopes,
        )


def _host() -> AuthenticatedHostIngress:
    return AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=NOW,
    )


def _repository(
    path: Path,
    *,
    keys: tuple[ConflictCursorKey, ...] | None = None,
) -> FileConflictAttentionRepository:
    return FileConflictAttentionRepository(
        path,
        keys=keys or (_key("old", epoch=1, secret=b"o" * 32, signing=True),),
        now_provider=lambda: NOW,
    )


def _hermes(
    repository: FileConflictAttentionRepository,
    resolver: _MutableResolver,
    *,
    enabled: bool = True,
) -> HermesMemoryProvider:
    return HermesMemoryProvider(
        ProviderMemoryService(
            conflict_attention_repository=repository,
            conflict_attention_enabled=enabled,
            authenticated_ingress_resolver=resolver,
            now_provider=lambda: NOW,
        )
    )


def _list(
    hermes: HermesMemoryProvider,
    arguments: dict[str, object],
) -> tuple[bool, dict[str, object], str | None]:
    envelope = hermes.handle_tool_call_with_attention(
        "memorii_list_conflicts",
        arguments,
        authenticated_host_ingress=_host(),
    )
    return envelope.legacy_result.ok, envelope.legacy_result.result, envelope.legacy_result.error


def _ids(result: dict[str, object]) -> list[str]:
    items = result["items"]
    assert isinstance(items, list)
    return [str(item["conflict_id"]) for item in items if isinstance(item, dict)]


def test_negotiated_hermes_listing_retains_snapshot_across_restart_and_concurrent_append(tmp_path: Path) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path)
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.append_open(_attention(1), scope_ids=("b",))
    repository.append_open(_attention(2), scope_ids=("c",))
    repository.append_open(_attention(3), scope_ids=("a", "b"))
    resolver = _MutableResolver()
    hermes = _hermes(repository, resolver)
    assert hermes.get_tool_schemas_with_attention()[-1]["name"] == "memorii_list_conflicts"

    ok, first, error = _list(hermes, {"scope_ids": ["a", "b"], "page_size": 1})
    assert ok is True and error is None
    assert _ids(first) == ["conflict-0"]
    assert first["total_pending"] == 3
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)

    def append(index: int) -> None:
        _repository(path).append_open(_attention(index), scope_ids=("a",))

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(append, (4, 5)))
    restarted = _hermes(_repository(path), resolver)
    ok, second, error = _list(restarted, {"cursor": cursor, "page_size": 2})
    assert ok is True and error is None
    assert _ids(second) == ["conflict-1", "conflict-3"]
    assert second["total_pending"] == 3


def test_disable_and_reenable_preserve_ledger_bytes_and_restore_listing(tmp_path: Path) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path)
    repository.append_open(_attention(0), scope_ids=("a",))
    resolver = _MutableResolver()
    before = path.read_bytes()

    disabled = _hermes(repository, resolver, enabled=False)
    legacy = disabled.prefetch("anything")
    assert disabled.prefetch_with_attention(
        "anything",
        authenticated_host_ingress=_host(),
        context_budget_utf8_bytes=10_000,
    ) == legacy
    ok, result, error = _list(disabled, {})
    assert ok is False and result == {} and error == "conflict_attention_unavailable"
    assert path.read_bytes() == before

    enabled = _hermes(_repository(path), resolver)
    ok, result, error = _list(enabled, {"page_size": 100})
    assert ok is True and error is None
    assert _ids(result) == ["conflict-0"]


def test_authorization_change_and_empty_authorization_fail_closed_without_append(tmp_path: Path) -> None:
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path)
    repository.append_open(_attention(0), scope_ids=("a",))
    repository.append_open(_attention(1), scope_ids=("a",))
    resolver = _MutableResolver()
    hermes = _hermes(repository, resolver)
    ok, first, error = _list(hermes, {"scope_ids": ["a"], "page_size": 1})
    assert ok is True and error is None
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)
    before = path.read_bytes()

    resolver.scopes = ("a", "b", "c", "d")
    ok, result, error = _list(hermes, {"cursor": cursor})
    assert ok is False and result == {} and error == "invalid_conflict_cursor"
    assert path.read_bytes() == before

    resolver.scopes = ()
    legacy = hermes.prefetch("anything")
    assert hermes.prefetch_with_attention(
        "anything",
        authenticated_host_ingress=_host(),
        context_budget_utf8_bytes=10_000,
    ) == legacy
    ok, result, error = _list(hermes, {})
    assert ok is False and result == {} and error == "conflict_attention_authorization_required"
    assert path.read_bytes() == before


def test_rotation_accepts_old_cursor_then_unavailable_snapshot_rejects_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "conflicts.jsonl"
    old = _key("old", epoch=1, secret=b"o" * 32, signing=True)
    repository = _repository(path, keys=(old,))
    for index in range(4):
        repository.append_open(_attention(index), scope_ids=("a",))
    resolver = _MutableResolver()
    ok, first, error = _list(_hermes(repository, resolver), {"page_size": 1})
    assert ok is True and error is None
    old_cursor = first["next_cursor"]
    assert isinstance(old_cursor, str)

    retained_old = old.model_copy(update={"signing": False})
    new = _key("new", epoch=2, secret=b"n" * 32, signing=True)
    rotated = _hermes(_repository(path, keys=(retained_old, new)), resolver)
    ok, second, error = _list(rotated, {"cursor": old_cursor, "page_size": 1})
    assert ok is True and error is None
    assert _ids(second) == ["conflict-1"]
    new_cursor = second["next_cursor"]
    assert isinstance(new_cursor, str)

    final_repository = _repository(path, keys=(new,))
    new_only = _hermes(final_repository, resolver)
    ok, third, error = _list(new_only, {"cursor": new_cursor, "page_size": 1})
    assert ok is True and error is None
    assert _ids(third) == ["conflict-2"]
    unavailable_cursor = third["next_cursor"]
    assert isinstance(unavailable_cursor, str)

    retained = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["record_type"] != "snapshot"
    ]
    path.write_text("\n".join(retained) + "\n", encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(
        final_repository,
        "_read_all",
        lambda: pytest.fail("conflict payload read must not occur"),
    )
    monkeypatch.setattr(
        final_repository,
        "_append",
        lambda _value: pytest.fail("fallback snapshot must not be appended"),
    )
    ok, result, error = _list(new_only, {"cursor": unavailable_cursor})
    assert ok is False and result == {} and error == "invalid_conflict_cursor"
    assert path.read_bytes() == before
