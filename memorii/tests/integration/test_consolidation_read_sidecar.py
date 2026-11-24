"""Installed-host consolidation pages release only current scoped outputs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.consolidation.runtime_outputs import (
    ConsolidationOrigin,
    ConsolidationSourceReference,
    SemanticCandidate,
    build_consolidation_result,
)
from memorii.core.harness_state.consolidation_read import ConsolidationReadPage, ConsolidationReadRequest
from memorii.core.harness_state.consumer import ManagedRuntimeSpool
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry
from memorii.core.harness_state.managed_ingress import authenticated_host_commands
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.sidecar import RuntimeSidecar
from memorii.core.harness_state.write_authority import HostCommandGrantRequest, ManagedHostCommandAuthority
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.persistence.runtime_api import operation_origin_namespace, operation_origin_proof_digest
from memorii.core.persistence.runtime_contracts import RuntimeCommandReceipt, RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.suppression_journal import (
    SuppressionCoordinate,
    SuppressionRecord,
    write_suppression_record,
)
from memorii.core.storage_administration.writer_enrollment import WriterEnrollmentRegistry
from memorii.core.work_state.runtime_projection import ManagedWorkProjectionDelivery, ManagedWorkProjectionWorker
from memorii.domain.enums import CommitStatus, MemoryDomain


@dataclass
class _Installation:
    administration: StorageAdministrationService
    credentials: SidecarCredentialStore
    secret: str
    task_id: str
    read_grant: RuntimeReadGrant

    def sidecar(self) -> RuntimeSidecar:
        return RuntimeSidecar.for_managed_installation(
            self.administration,
            credentials=self.credentials,
            grant_factory=lambda _principal: self.read_grant,
            spool=ManagedRuntimeSpool(self.administration.installation_root / "spool"),
        )

    def read(
        self, *, operation_id: str = "pause", page_size: int = 10, cursor: str | None = None,
    ) -> tuple[int, bytes]:
        return self.sidecar().handle_consolidation_read_request(
            bearer_token=self.secret,
            origin=None,
            body=ConsolidationReadRequest(
                task_id=self.task_id, origin_operation_id=operation_id, page_size=page_size, cursor=cursor,
            ).model_dump_json().encode(),
        )


@pytest.fixture
def installed(tmp_path: Path) -> Iterator[_Installation]:
    administration = StorageAdministrationService(tmp_path / "installation")
    try:
        administration.initialize()
        credentials = SidecarCredentialStore(administration.installation_root / "control" / "credentials")
        credential, secret = credentials.issue("principal:one")
        capability = mint_owner_capability(administration, "owner")
        command_grants = ManagedHostCommandAuthority(administration)
        expires = datetime.now(UTC) + timedelta(minutes=5)
        command_grants.issue(HostCommandGrantRequest(
            grant_id="start-grant", credential_id=credential.credential_id,
            principal=credential.principal, client_namespace="host:start",
            allowed_kinds=("start_task",), allowed_operation_ids=("start",), expires_at=expires,
        ), capability=capability)
        commands = authenticated_host_commands(administration, credentials, secret)
        start = RuntimeCommandRequest(kind="start_task", operation_id="start", goal="Test verified consolidation")
        commands.dispatch(start, operation_origin=commands.prepare(start))
        task, = RuntimeStateRepository(administration.partition()).list_tasks()
        command_grants.issue(HostCommandGrantRequest(
            grant_id="pause-grant", credential_id=credential.credential_id,
            principal=credential.principal, client_namespace="host:lifecycle",
            allowed_kinds=("pause_task",), allowed_task_ids=(task.task_id,),
            allowed_projection_task_ids=(task.task_id,),
            allowed_operation_ids=("pause", "sourced-outputs"), expires_at=expires,
        ), capability=capability)
        pause = RuntimeCommandRequest(
            kind="pause_task", operation_id="pause", task_id=task.task_id,
            pause_reason="waiting", expected_revision=task.version,
        )
        commands.dispatch(pause, operation_origin=commands.prepare(pause))
        yield _Installation(
            administration, credentials, secret, task.task_id,
            RuntimeReadGrant(
                grant_id="read-current", principal=credential.principal, allowed_task_ids=(task.task_id,),
                epoch=1, expires_at=expires,
            ),
        )
    finally:
        administration.close()


def test_managed_pause_queues_a_signed_projection_for_the_enrolled_worker(installed: _Installation) -> None:
    administration = installed.administration
    partition = administration.partition()
    with partition.transaction(write=False) as connection:
        [row] = partition.read_runtime_rows(connection, table="runtime_outbox_deliveries")
        entry = ManagedWorkProjectionDelivery.model_validate_json(str(row["record_json"]))
        assert entry.command.operation_id == "pause"
        assert entry.projection.summary.task_id == installed.task_id
    WriterEnrollmentRegistry(administration.installation_root / "control" / "writers").enroll(
        "projection", kind="managed_work_projection",
    )
    worker = ManagedWorkProjectionWorker(administration, worker_id="projection")
    claim = worker.claim(entry.delivery.request.delivery_id)
    assert claim is not None
    receipt = worker.publish(claim)
    assert receipt is not None
    after = administration.acquire_verified_snapshot()
    assert worker.publish(claim) == receipt
    assert administration.acquire_verified_snapshot() == after


def test_sidecar_pages_the_saved_result_and_rejects_stale_or_wrong_scope(installed: _Installation) -> None:
    status, raw = installed.read(page_size=1)
    assert status == 200
    first = ConsolidationReadPage.model_validate_json(raw)
    assert first.outputs[0].output.payload.kind == "unresolved_follow_up_summary"
    assert first.continuation_cursor
    status, raw = installed.read(page_size=1, cursor=first.continuation_cursor)
    assert status == 200
    second = ConsolidationReadPage.model_validate_json(raw)
    assert second.result_id == first.result_id
    assert second.outputs[0].output.payload.kind == "archive_package"
    assert second.continuation_cursor is None
    assert all(entry.offer is None for entry in (*first.outputs, *second.outputs))

    status, raw = installed.sidecar().handle_consolidation_read_request(
        bearer_token=installed.secret, origin=None,
        body=ConsolidationReadRequest(task_id="foreign-task", origin_operation_id="pause").model_dump_json().encode(),
    )
    assert status == 403
    assert b"foreign-task" not in raw
    status, raw = installed.read(page_size=2, cursor=first.continuation_cursor)
    assert status == 409
    assert json.loads(raw)["code"] == "stale_cursor"

    root = installed.administration.installation_root
    epochs = GrantEpochRegistry(root / "control" / "grants")
    epochs.revoke(installed.read_grant.grant_id, reason="test revoke")
    status, raw = installed.read()
    assert status == 403
    assert first.result_id.encode() not in raw


def test_suppressed_output_is_omitted_and_existing_offer_cursor_is_stale(installed: _Installation) -> None:
    administration = installed.administration
    commands = authenticated_host_commands(administration, installed.credentials, installed.secret)
    source = CanonicalMemoryRecord(
        memory_id="retained:source", domain=MemoryDomain.TRANSCRIPT, text="retained owner evidence",
        status=CommitStatus.COMMITTED, task_id=installed.task_id, user_id=installed.read_grant.principal,
    )
    administration.publish_memory_plane_batch((source,))
    source_ref = ConsolidationSourceReference(source_id=source.memory_id, source_digest=record_digest(source))
    prepare = RuntimeCommandRequest(
        kind="pause_task", operation_id="sourced-outputs", task_id=installed.task_id,
        expected_revision=2, pause_reason="fixture",
    )
    operation = commands.prepare(prepare).coordinate

    # Synthetic signed producer records keep this serving fixture independent
    # of the not-yet-installed semantic producer. The actual pause producer
    # is covered by the other test.
    def stage(connection, repository: RuntimeStateRepository) -> None:
        result = build_consolidation_result(
            ConsolidationOrigin(
                installation_id=operation.installation_id, partition_id=operation.repository_id,
                operation_generation=operation.generation_id, task_id=installed.task_id,
                client_namespace=operation.client_namespace, operation_id=operation.operation_id,
                request_digest=operation.request_digest,
            ),
            origin_revision=repository.read_runtime_revision_in(connection),
            outputs=tuple(
                SemanticCandidate(abstraction=f"Eligible abstraction {index}", source_refs=(source_ref,))
                for index in (1, 2)
            ),
        )
        repository.apply_consolidation_result(connection, result)
        receipt = RuntimeCommandReceipt(
            operation_id=operation.operation_id, client_namespace=operation.client_namespace,
            request_digest=operation.request_digest, status="committed", base_revision=result.origin_revision - 1,
            current_revision=result.origin_revision, consolidation_result_id=result.result_id,
            result_digest=sha256(result.canonical_bytes()).hexdigest(), operation_origin=operation,
            origin_proof_digest=operation_origin_proof_digest(administration.sign_operation_origin(operation)),
        )
        repository.apply_command_receipt(connection, receipt, lookup_namespace=operation_origin_namespace(operation))

    publish_runtime_change(administration, stage)
    status, raw = installed.read(operation_id=operation.operation_id, page_size=1)
    assert status == 200
    before = ConsolidationReadPage.model_validate_json(raw)
    entry, = before.outputs
    assert entry.offer is not None
    assert entry.offer.output_id == entry.output.output_id
    assert entry.offer.offer_version == 1
    assert entry.offer.payload_digest == entry.output.payload_digest
    assert before.continuation_cursor

    # Stand in for the already-committed, control-barrier source suppression.
    # The serving gate intentionally cannot depend on a new partition revision.
    write_suppression_record(administration.installation_root / "control", SuppressionRecord(
        suppression_id="1" * 64, plan_digest="2" * 64, closure_digest="3" * 64,
        scope_note="test fixture",
        suppressed=(SuppressionCoordinate(coordinate_kind="source", coordinate_id=source.memory_id),),
        applied_at_unix=1,
    ))
    status, raw = installed.read(operation_id=operation.operation_id, page_size=1)
    assert status == 200
    after = ConsolidationReadPage.model_validate_json(raw)
    assert after.outputs == () and after.continuation_cursor is None
    assert entry.output.output_id.encode() not in raw
    assert source.memory_id.encode() not in raw
    status, raw = installed.read(operation_id=operation.operation_id, page_size=1, cursor=before.continuation_cursor)
    assert status == 409
    assert json.loads(raw)["code"] == "stale_cursor"
