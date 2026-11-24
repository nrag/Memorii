from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    HostCommandGrantRequest,
    ManagedHostCommandAuthority,
)
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.runtime_api import (
    CommandAuthorityPurpose,
    ManagedRuntimeCommandService,
    ResolvedRuntimeCommandAuthority,
    RuntimeCommandError,
    RuntimeCommandService,
)
from memorii.core.persistence.runtime_contracts import (
    OperationOrigin,
    OperationOriginCoordinate,
    RuntimeCommandRequest,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService

_AUTHORITY = ResolvedRuntimeCommandAuthority(principal="caller", client_namespace="client")


class _CurrentAuthority:
    def __init__(self) -> None:
        self.denied: set[CommandAuthorityPurpose] = {"historical_release"}

    def __call__(
        self,
        request: RuntimeCommandRequest,
        purpose: CommandAuthorityPurpose,
        coordinate: OperationOriginCoordinate | None,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> ResolvedRuntimeCommandAuthority | None:
        return None if purpose in self.denied else _AUTHORITY


@pytest.fixture
def administration(tmp_path: Path) -> Iterator[StorageAdministrationService]:
    service = StorageAdministrationService(tmp_path / "installation")
    try:
        service.initialize()
        yield service
    finally:
        service.close()


def _start_request() -> RuntimeCommandRequest:
    return RuntimeCommandRequest(kind="start_task", operation_id="operation", goal="diagnose latency")


def test_prepared_start_reopens_with_one_verified_receipt(
    administration: StorageAdministrationService,
) -> None:
    command = _start_request()
    authorizer = _CurrentAuthority()
    service = ManagedRuntimeCommandService(administration, authorize=authorizer)
    before = administration.acquire_verified_snapshot()
    origin = service.prepare(command)
    assert service.validate_intake(command, operation_origin=origin) is None
    assert administration.acquire_verified_snapshot() == before

    committed = service.dispatch(command, operation_origin=origin)
    assert committed.operation_origin == origin.coordinate
    assert committed.origin_proof_digest
    snapshot = administration.acquire_verified_snapshot()
    reopened = StorageAdministrationService(administration.installation_root)
    try:
        retried = ManagedRuntimeCommandService(reopened, authorize=authorizer)
        origin_from_carrier = OperationOrigin.model_validate_json(origin.model_dump_json())
        assert retried.dispatch(command, operation_origin=origin_from_carrier) == committed
        assert reopened.acquire_verified_snapshot() == snapshot
        tasks = RuntimeStateRepository(reopened.partition()).list_tasks()
        assert len(tasks) == 1
        assert tasks[0].principal == _AUTHORITY.principal
    finally:
        reopened.close()


def test_proof_is_not_scope_or_permission_and_divergent_intent_cannot_commit(
    administration: StorageAdministrationService,
) -> None:
    command = _start_request()
    authorizer = _CurrentAuthority()
    service = ManagedRuntimeCommandService(administration, authorize=authorizer)
    origin = service.prepare(command)
    before = administration.acquire_verified_snapshot()
    forged = origin.model_copy(update={
        "coordinate": origin.coordinate.model_copy(update={"generation_id": "wrong-generation"})
    })
    with pytest.raises(RuntimeCommandError, match="does not authenticate"):
        service.dispatch(command, operation_origin=forged)
    changed = command.model_copy(update={"goal": "different intent"})
    with pytest.raises(RuntimeCommandError, match="does not authenticate"):
        service.dispatch(changed, operation_origin=origin)
    authorizer.denied.add("dispatch")
    with pytest.raises(RuntimeCommandError, match="current command authority"):
        service.validate_intake(command, operation_origin=origin)
    with pytest.raises(RuntimeCommandError, match="current command authority"):
        service.dispatch(command, operation_origin=origin)
    assert administration.acquire_verified_snapshot() == before

    authorizer.denied.remove("dispatch")
    service.dispatch(command, operation_origin=origin)
    authorizer.denied.add("release")
    with pytest.raises(RuntimeCommandError, match="current command authority"):
        service.dispatch(command, operation_origin=origin)


def test_generation_change_cannot_reissue_or_dispatch_an_old_origin(
    administration: StorageAdministrationService, monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = _start_request()
    authorizer = _CurrentAuthority()
    service = ManagedRuntimeCommandService(administration, authorize=authorizer)
    origin = service.prepare(command)
    receipt = service.dispatch(command, operation_origin=origin)
    absent = command.model_copy(update={"operation_id": "uncommitted-before-restore"})
    absent_origin = service.prepare(absent)
    snapshot = administration.acquire_verified_snapshot()

    original_context = administration.verified_operation_context

    @contextmanager
    def restored_context() -> Iterator[tuple[InstallationControlState, RuntimePublicationState]]:
        # Simulate the finalized generation change at the verified context
        # boundary. Restore choreography is qualified by its separate owner.
        with original_context() as (state, finalized):
            yield state, finalized.model_copy(update={"data_generation_id": "restored-generation"})

    monkeypatch.setattr(administration, "verified_operation_context", restored_context)
    with pytest.raises(RuntimeCommandError, match="historical receipt is absent"):
        service.dispatch(absent, operation_origin=absent_origin)
    with pytest.raises(RuntimeCommandError, match="historical receipt is held"):
        service.dispatch(command, operation_origin=origin)
    authorizer.denied.remove("historical_release")
    assert service.dispatch(command, operation_origin=origin) == receipt
    assert administration.acquire_verified_snapshot() == snapshot


def test_reserved_managed_receipt_index_cannot_be_opened_as_a_legacy_namespace(
    administration: StorageAdministrationService,
) -> None:
    with pytest.raises(RuntimeCommandError, match="reserved for managed receipts"):
        RuntimeCommandService(administration, client_namespace="origin:forged")


def test_dispatch_and_duplicate_release_recheck_the_current_control_grant(
    administration: StorageAdministrationService,
) -> None:
    credentials = SidecarCredentialStore(administration.installation_root / "control" / "credentials")
    credential, bearer = credentials.issue("principal:one")
    grant_owner = ManagedHostCommandAuthority(administration)
    capability = mint_owner_capability(administration, "owner")
    command = _start_request()
    second_command = command.model_copy(update={"operation_id": "second-operation"})
    grant = grant_owner.issue(
        HostCommandGrantRequest(
            grant_id="command-grant",
            credential_id=credential.credential_id,
            principal=credential.principal,
            client_namespace="host:one",
            allowed_kinds=("start_task",),
            allowed_operation_ids=(command.operation_id, second_command.operation_id),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
        capability=capability,
    )

    def authorize(
        request: RuntimeCommandRequest,
        purpose: CommandAuthorityPurpose,
        coordinate: OperationOriginCoordinate | None,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> ResolvedRuntimeCommandAuthority | None:
        if purpose == "historical_release":
            return None
        current_credential = credentials.credential_for(bearer)
        if current_credential is None:
            return None
        try:
            resolution = grant_owner.resolve_in_verified_context(
                credential=current_credential,
                request=request,
                grant_id=grant.grant_id,
                grant_epoch=grant.epoch,
                state=state,
                finalized=finalized,
            )
        except HostCommandAuthorityError:
            return None
        return ResolvedRuntimeCommandAuthority(resolution.principal, resolution.client_namespace)

    service = ManagedRuntimeCommandService(administration, authorize=authorize)
    proof = service.prepare(command)
    pending = service.prepare(second_command)
    receipt = service.dispatch(command, operation_origin=proof)
    assert receipt.client_namespace == grant.client_namespace
    assert service.dispatch(command, operation_origin=proof) == receipt
    grant_owner.revoke(grant.grant_id, capability=capability)
    before = administration.acquire_verified_snapshot()
    with pytest.raises(RuntimeCommandError, match="current command authority"):
        service.dispatch(command, operation_origin=proof)
    with pytest.raises(RuntimeCommandError, match="current command authority"):
        service.dispatch(second_command, operation_origin=pending)
    assert administration.acquire_verified_snapshot() == before
