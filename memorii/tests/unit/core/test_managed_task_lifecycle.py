"""The managed source-free task path publishes a signed archive and sealed result."""

from __future__ import annotations

from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.consolidation.runtime_outputs import ArchivePackage, UnresolvedFollowUpSummary
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.key_owner import LocalSigningKeyOwner
from memorii.core.persistence.runtime_api import (
    CommandAuthorityPurpose,
    ManagedRuntimeCommandService,
    ResolvedRuntimeCommandAuthority,
    RuntimeCommandError,
)
from memorii.core.persistence.runtime_checkpoint import TaskLifecycleArchive
from memorii.core.persistence.runtime_contracts import (
    OperationOriginCoordinate,
    RuntimeCommandRequest,
    TaskCompletionEvidence,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.service import StorageAdministrationService


class _ScopedOwner:
    def __init__(self) -> None:
        self.task_id: str | None = None
        self.principal = "principal:one"
        self.revoked = False

    def __call__(
        self,
        request: RuntimeCommandRequest,
        purpose: CommandAuthorityPurpose,
        coordinate: OperationOriginCoordinate | None,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> ResolvedRuntimeCommandAuthority | None:
        if (
            self.revoked
            or purpose == "historical_release"
            or (request.kind != "start_task" and request.task_id != self.task_id)
        ):
            return None
        return ResolvedRuntimeCommandAuthority(self.principal, "host:one")


@pytest.fixture
def fresh_task(tmp_path: Path) -> Iterator[tuple[StorageAdministrationService, _ScopedOwner, TaskRecord]]:
    administration = StorageAdministrationService(tmp_path / "installation")
    try:
        administration.initialize()
        owner = _ScopedOwner()
        service = ManagedRuntimeCommandService(administration, authorize=owner)
        start = RuntimeCommandRequest(kind="start_task", operation_id="start", goal="Empty task")
        service.dispatch(start, operation_origin=service.prepare(start))
        task, = RuntimeStateRepository(administration.partition()).list_tasks()
        owner.task_id = task.task_id
        yield administration, owner, task
    finally:
        administration.close()


@pytest.mark.parametrize("complete", [False, True])
def test_managed_lifecycle_keeps_sealed_archive_and_result_across_reopen(
    fresh_task: tuple[StorageAdministrationService, _ScopedOwner, TaskRecord],
    complete: bool,
) -> None:
    administration, owner, task = fresh_task
    service = ManagedRuntimeCommandService(administration, authorize=owner)
    command = RuntimeCommandRequest(
        kind="complete_task" if complete else "pause_task",
        operation_id="lifecycle",
        task_id=task.task_id,
        expected_revision=task.version,
        completion_evidence=TaskCompletionEvidence() if complete else None,
        pause_reason=None if complete else "Waiting",
    )
    proof = service.prepare(command)
    receipt = service.dispatch(command, operation_origin=proof)
    assert receipt.consolidation_result_id is not None
    signed = administration.acquire_verified_snapshot()
    reopened = StorageAdministrationService(administration.installation_root)
    try:
        assert reopened.acquire_verified_snapshot() == signed
        read = ManagedRuntimeCommandService(reopened, authorize=owner)
        assert read.dispatch(command, operation_origin=proof) == receipt
        repo = RuntimeStateRepository(reopened.partition())
        result = repo.get_consolidation_result(receipt.consolidation_result_id)
        assert result is not None
        assert sha256(result.canonical_bytes()).hexdigest() == receipt.result_digest
        assert result.origin_revision == receipt.current_revision
        assert len(result.omissions) == 4
        follow_up, archived = (entry.payload for entry in result.outputs)
        assert isinstance(follow_up, UnresolvedFollowUpSummary)
        assert not follow_up.items
        assert isinstance(archived, ArchivePackage)
        with reopened.partition().transaction(write=False) as connection:
            row = reopened.partition().read_runtime_row(
                connection, table="runtime_checkpoints",
                match=(("checkpoint_id", archived.reference.checkpoint_id),),
            )
            assert row is not None
            archive = TaskLifecycleArchive.model_validate_json(row["record_json"])
            assert archive.reference() == archived.reference
            key_owner = LocalSigningKeyOwner(reopened.installation_root / "control" / "keys")
            archive.verify_signature(key_owner.verify)
            assert archive.checkpoint.task == task
            assert archive.checkpoint.root_node.id == task.root_execution_node_id
            assert not archive.manifest.source_closure
        updated = repo.get_task(task.task_id)
        assert updated is not None
        assert updated.lifecycle == ("completed" if complete else "paused")
        assert updated.version == task.version + 1
        assert reopened.acquire_verified_snapshot() == signed
        owner.revoked = True
        with pytest.raises(RuntimeCommandError, match="current command authority"):
            read.dispatch(command, operation_origin=proof)
    finally:
        reopened.close()


def test_unverified_completion_claims_and_missing_archive_roll_back(
    fresh_task: tuple[StorageAdministrationService, _ScopedOwner, TaskRecord],
) -> None:
    administration, owner, task = fresh_task
    service = ManagedRuntimeCommandService(administration, authorize=owner)
    claimed = RuntimeCommandRequest(
        kind="complete_task", operation_id="unsupported-completion",
        task_id=task.task_id, expected_revision=task.version,
        completion_evidence=TaskCompletionEvidence(acceptance_results=("unverified assertion",)),
    )
    before = administration.acquire_verified_snapshot()
    with pytest.raises(RuntimeCommandError, match="requires an evidence owner"):
        service.dispatch(claimed, operation_origin=service.prepare(claimed))
    assert administration.acquire_verified_snapshot() == before

    publish_runtime_change(
        administration,
        lambda connection, repo: connection.execute(
            "DELETE FROM runtime_execution_nodes WHERE task_id = ?", (task.task_id,),
        ),
    )
    pause = RuntimeCommandRequest(
        kind="pause_task", operation_id="no-root",
        task_id=task.task_id, expected_revision=task.version, pause_reason="Waiting",
    )
    before = administration.acquire_verified_snapshot()
    with pytest.raises(RuntimeCommandError, match="archive closure is unavailable"):
        service.dispatch(pause, operation_origin=service.prepare(pause))
    assert administration.acquire_verified_snapshot() == before
    repo = RuntimeStateRepository(administration.partition())
    assert repo.get_task(task.task_id) == task
    with administration.partition().transaction(write=False) as connection:
        assert repo.list_consolidation_results_in(connection) == ()
        assert not administration.partition().read_runtime_rows(connection, table="runtime_checkpoints")
