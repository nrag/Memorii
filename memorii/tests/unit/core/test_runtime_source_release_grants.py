"""Legacy signed runtime history remains readable across the grant catalog change."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.persistence.runtime_api import RuntimeCommandService
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.provider.runtime_source_release import list_runtime_released_sources
from memorii.core.storage_administration.revoked_identity_view import RevokedIdentities, RevokedIdentityView
from memorii.core.storage_administration.service import StorageAdministrationService


def test_reopen_prior_runtime_history_without_source_release_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "installation"
    with monkeypatch.context() as previous:
        previous.setattr("memorii.stores.sqlite.partition.PARTITION_SCHEMA_VERSION", 4)
        with StorageAdministrationService(root) as administration:
            administration.initialize()
            RuntimeCommandService(administration).dispatch(RuntimeCommandRequest(
                kind="start_task", operation_id="prior-start", goal="Retain prior signed history",
            ))
            signed = administration.acquire_verified_snapshot()

    with StorageAdministrationService(root) as administration:
        assert administration.acquire_verified_snapshot() == signed
        repository = RuntimeStateRepository(administration.partition())
        task, = repository.list_tasks()
        with repository.partition.transaction(write=False) as connection:
            assert not repository.partition.supports_runtime_source_release(connection)
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'runtime_source_release_grants'"
            ).fetchone() is None
            assert list_runtime_released_sources(
                connection, repository, task_id=task.task_id, principal=task.principal,
                now=datetime.now(UTC), revoked=RevokedIdentityView(RevokedIdentities()),
            ) == ()
