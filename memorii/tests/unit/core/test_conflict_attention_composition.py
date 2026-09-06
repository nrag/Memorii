"""Conflict-attention composition wiring across the built provider roots.

The provider service owns the bounded attention pull; these proofs pin the
composition contract: the factory and filesystem builders forward the
conflict-attention authority instead of silently disabling it, Hermes
self-built services inherit the same wiring, and the fail-closed default
(disabled without explicit authority) is preserved.
"""

from datetime import UTC, datetime

import pytest
from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_evolution.conflict_attention import (
    ConflictAttentionPage,
    ConflictListRequest,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    ConflictCursorKey,
)
from memorii.core.provider.factory import build_provider_memory_service_from_env

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)


class _PageRepository:
    """Minimal ConflictClarificationRepository returning one bounded page."""

    def __init__(self) -> None:
        self.calls: list[ConflictListRequest] = []

    def list_conflicts(
        self, context: object, request: ConflictListRequest
    ) -> ConflictAttentionPage:
        self.calls.append(request)
        return ConflictAttentionPage(total_pending=1)


def _builder_kwargs(repository: _PageRepository):
    return {
        "conflict_attention_repository": repository,
        "conflict_attention_enabled": True,
        "now_provider": lambda: NOW,
    }


@pytest.mark.parametrize(
    "build",
    (
        pytest.param(
            lambda tmp_path, repo: build_provider_memory_service_from_env(
                **_builder_kwargs(repo)
            ),
            id="factory",
        ),
        pytest.param(
            lambda tmp_path, repo: build_filesystem_provider(
                tmp_path / "root", **_builder_kwargs(repo)
            ),
            id="filesystem",
        ),
    ),
)
def test_built_roots_expose_bounded_attention_through_one_owner(
    tmp_path, build
) -> None:
    repository = _PageRepository()
    service = build(tmp_path, repository)
    assert service._conflict_attention_enabled is True
    assert service._conflict_attention_repository is repository


def test_factory_and_filesystem_defaults_remain_fail_closed(tmp_path) -> None:
    factory_service = build_provider_memory_service_from_env()
    assert factory_service._conflict_attention_enabled is False
    filesystem_service = build_filesystem_provider(tmp_path / "root")
    assert filesystem_service._conflict_attention_enabled is False


def test_enabled_attention_without_repository_fails_closed(tmp_path) -> None:
    with pytest.raises(ValueError, match="conflict attention"):
        build_provider_memory_service_from_env(conflict_attention_enabled=True)
    with pytest.raises(ValueError, match="conflict attention"):
        build_filesystem_provider(
            tmp_path / "root", conflict_attention_enabled=True
        )


def test_filesystem_bundle_builds_its_file_ledger_repository(tmp_path) -> None:
    from memorii.core.filesystem_storage.bundle import FilesystemStorageBundle

    bundle = FilesystemStorageBundle.from_root(tmp_path / "root")
    keys = (
        ConflictCursorKey(
            key_id="key-one",
            key_epoch=1,
            secret=b"a" * 32,
            valid_from=datetime(2020,1,1,tzinfo=UTC),
            expires_at=datetime(2050,1,1,tzinfo=UTC),
            signing=True,
        ),
    )
    repository = bundle.build_conflict_attention_repository(keys)
    assert repository is not None
    assert callable(repository.list_conflicts)
