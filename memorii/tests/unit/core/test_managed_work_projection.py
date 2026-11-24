from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state.credentials import IssuedCredential
from memorii.core.harness_state.write_authority import (
    HostCommandGrantRequest,
    ManagedHostCommandAuthority,
)
from memorii.core.persistence.managed_delivery import DeliveredDelivery, DeliveryClaim, RejectedDelivery
from memorii.core.persistence.runtime_api import (
    RuntimeCommandService,
    operation_origin_namespace,
    operation_origin_proof_digest,
)
from memorii.core.persistence.runtime_contracts import (
    OperationOriginCoordinate,
    RuntimeCommandReceipt,
    RuntimeCommandRequest,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.writer_enrollment import (
    WriterEnrollmentError,
    WriterEnrollmentRegistry,
)
from memorii.core.work_state.runtime_projection import (
    ManagedWorkProjectionDelivery,
    ManagedWorkProjectionWorker,
    stage_work_projection,
)


@pytest.fixture
def installation(tmp_path: Path) -> Iterator[StorageAdministrationService]:
    service = StorageAdministrationService(tmp_path / "installation")
    try:
        service.initialize()
        yield service
    finally:
        service.close()


def _seed(
    service: StorageAdministrationService, *, with_projection: bool = True,
) -> ManagedWorkProjectionDelivery | None:
    runtime = RuntimeCommandService(service, client_namespace="owner")
    runtime.dispatch(RuntimeCommandRequest(kind="start_task", operation_id="start", goal="Prepare handoff"))
    task, = runtime.repository.list_tasks()
    command = RuntimeCommandRequest(
        kind="pause_task", operation_id="pause", task_id=task.task_id,
        expected_revision=task.version, pause_reason="waiting",
    )
    authority = ManagedHostCommandAuthority(service)
    credential = IssuedCredential(principal=task.principal, credential_id="credential")
    capability = mint_owner_capability(service, "owner")
    grant = authority.issue(
        HostCommandGrantRequest(
            grant_id="grant", credential_id=credential.credential_id,
            principal=credential.principal, client_namespace="host",
            allowed_kinds=("pause_task",), allowed_task_ids=(task.task_id,),
            allowed_projection_task_ids=(task.task_id,) if with_projection else (),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
        capability=capability,
    )
    with service.verified_operation_context() as (state, finalized):
        coordinate = OperationOriginCoordinate(
            installation_id=state.installation_id, repository_id=finalized.repository_id,
            generation_id=finalized.data_generation_id, principal=task.principal,
            client_namespace=grant.client_namespace, operation_id=command.operation_id,
            request_digest=command.managed_intent_digest(),
        )
        origin = service.sign_operation_origin(coordinate)
        resolved = authority.resolve_in_verified_context(
            credential=credential, request=command, grant_id=grant.grant_id,
            grant_epoch=grant.epoch, state=state, finalized=finalized,
        )

    entries: list[ManagedWorkProjectionDelivery | None] = []

    def enqueue(connection, repository):
        # This invokes the target stage port from the signed command transaction.
        # The separately owned production command wiring is qualified elsewhere.
        revision = repository.read_runtime_revision_in(connection)
        repository.apply_task(connection, task.model_copy(update={"lifecycle": "paused"}))
        repository.apply_command_receipt(
            connection,
            RuntimeCommandReceipt(
                operation_id=command.operation_id, client_namespace=grant.client_namespace,
                request_digest=coordinate.request_digest, status="committed",
                base_revision=revision - 1, current_revision=revision,
                operation_origin=coordinate, origin_proof_digest=operation_origin_proof_digest(origin),
            ),
            lookup_namespace=operation_origin_namespace(coordinate),
        )
        entries.append(stage_work_projection(
            connection, repository, command=command, origin=origin, grant=resolved, runtime_revision=revision,
        ))

    publish_runtime_change(service, enqueue)
    return entries[0]


def _enroll(service: StorageAdministrationService) -> None:
    WriterEnrollmentRegistry(service.installation_root / "control" / "writers").enroll(
        "projection-worker", kind="managed_work_projection"
    )


def test_work_projection_requires_explicit_target_scope(installation: StorageAdministrationService) -> None:
    assert _seed(installation, with_projection=False) is None
    with installation.partition().transaction(write=False) as connection:
        rows = installation.partition().read_runtime_rows(connection, table="runtime_outbox_deliveries")
    assert not rows


def test_enrolled_work_projection_atomically_publishes_effect_receipt_and_terminal_state(
    installation: StorageAdministrationService, monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _seed(installation)
    assert entry is not None
    delivery_id = entry.delivery.request.delivery_id
    worker = ManagedWorkProjectionWorker(installation, worker_id="projection-worker")
    before = installation.acquire_verified_snapshot()
    with pytest.raises(WriterEnrollmentError, match="not enrolled"):
        worker.claim(delivery_id)
    assert installation.acquire_verified_snapshot() == before
    _enroll(installation)
    claim = worker.claim(delivery_id)
    assert isinstance(claim, DeliveryClaim)
    claimed = installation.acquire_verified_snapshot()
    original_insert = RuntimeStateRepository.insert_work_projection_effect

    def fail_after_target_write(self, connection, projection, receipt):
        original_insert(self, connection, projection, receipt)
        raise RuntimeError("fail between target and terminal queue state")

    with monkeypatch.context() as fault:
        fault.setattr(RuntimeStateRepository, "insert_work_projection_effect", fail_after_target_write)
        with pytest.raises(RuntimeError, match="fail between"):
            worker.publish(claim)
    assert installation.acquire_verified_snapshot() == claimed
    with installation.partition().transaction(write=False) as connection:
        for catalog in ("runtime_work_projections", "runtime_target_receipts"):
            assert installation.partition().read_delivery_record(
                connection, catalog=catalog, record_id=delivery_id
            ) is None

    receipt = worker.publish(claim)
    assert receipt is not None
    committed = installation.acquire_verified_snapshot()
    reopened = StorageAdministrationService(installation.installation_root)
    try:
        assert reopened.acquire_verified_snapshot() == committed
        restarted = ManagedWorkProjectionWorker(reopened, worker_id="projection-worker")
        assert restarted.publish(claim) == receipt
        assert reopened.acquire_verified_snapshot() == committed
        repository = RuntimeStateRepository(reopened.partition())
        with reopened.partition().transaction(write=False) as connection:
            loaded = repository.get_managed_work_projection_delivery(connection, delivery_id)
            assert loaded is not None
            assert loaded.delivery.progress == DeliveredDelivery(receipt=receipt, completed_claim=claim)
            repository.verify_work_projection_effect(connection, loaded, receipt)
    finally:
        reopened.close()


def test_revocation_after_claim_prevents_projection_effect(installation: StorageAdministrationService) -> None:
    entry = _seed(installation)
    assert entry is not None
    delivery_id = entry.delivery.request.delivery_id
    _enroll(installation)
    worker = ManagedWorkProjectionWorker(installation, worker_id="projection-worker")
    claim = worker.claim(delivery_id)
    assert isinstance(claim, DeliveryClaim)
    grants = ManagedHostCommandAuthority(installation)
    grants.revoke("grant", capability=mint_owner_capability(installation, "owner"))
    assert worker.publish(claim) is None
    repository = RuntimeStateRepository(installation.partition())
    with installation.partition().transaction(write=False) as connection:
        loaded = repository.get_managed_work_projection_delivery(connection, delivery_id)
        assert loaded is not None
        assert loaded.delivery.progress == RejectedDelivery(reason="denied")
        assert installation.partition().read_delivery_record(
            connection, catalog="runtime_work_projections", record_id=delivery_id
        ) is None
