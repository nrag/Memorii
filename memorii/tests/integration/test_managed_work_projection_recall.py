"""Managed projection recall through the authenticated embedded host port."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.consolidation.runtime_outputs import ConsolidationOrigin, runtime_delivery_id
from memorii.core.harness_state.binding import HermesRuntimeStatePorts, RuntimeTaskBinding
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry
from memorii.core.harness_state.managed_ingress import authenticated_host_commands
from memorii.core.harness_state.service import HarnessStateError, HarnessStateService, RuntimeReadGrant
from memorii.core.harness_state.write_authority import HostCommandGrantRequest, ManagedHostCommandAuthority
from memorii.core.persistence.runtime_api import ManagedRuntimeCommandService
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest, TaskCompletionEvidence
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import (
    InstallationIntegrityError,
    StorageAdministrationError,
    StorageAdministrationService,
)
from memorii.core.storage_administration.writer_enrollment import WriterEnrollmentRegistry
from memorii.core.work_state.models import WorkStateStatus
from memorii.core.work_state.runtime_projection import ManagedWorkProjectionWorker
from memorii.core.work_state.runtime_projection_read import WorkProjectionRecallError


def _stage_projection(commands: ManagedRuntimeCommandService, command: RuntimeCommandRequest) -> str:
    proof = commands.prepare(command)
    commands.dispatch(command, operation_origin=proof)
    origin = proof.coordinate
    assert command.task_id is not None
    return runtime_delivery_id(
        origin.repository_id,
        "work_projection",
        ConsolidationOrigin(
            installation_id=origin.installation_id,
            partition_id=origin.repository_id,
            operation_generation=origin.generation_id,
            task_id=command.task_id,
            client_namespace=origin.client_namespace,
            operation_id=origin.operation_id,
            request_digest=origin.request_digest,
        ),
    )


def test_embedded_recall_selects_latest_eligible_origin_after_out_of_order_delivery(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        credentials = SidecarCredentialStore(root / "control" / "credentials")
        credential, secret = credentials.issue("principal:work")
        _, other_secret = credentials.issue("principal:other")
        owner = mint_owner_capability(service, "owner")
        grants = ManagedHostCommandAuthority(service)
        expires = datetime.now(UTC) + timedelta(minutes=5)
        grants.issue(HostCommandGrantRequest(
            grant_id="work-start", credential_id=credential.credential_id,
            principal=credential.principal, client_namespace="work:start", allowed_kinds=("start_task",),
            expires_at=expires,
        ), capability=owner)
        commands = authenticated_host_commands(service, credentials, secret)
        start = RuntimeCommandRequest(kind="start_task", operation_id="start", goal="A scoped work-state journey")
        commands.dispatch(start, operation_origin=commands.prepare(start))
        task, = RuntimeStateRepository(service.partition()).list_tasks()
        task_id = task.task_id
        grants.issue(HostCommandGrantRequest(
            grant_id="work-pause", credential_id=credential.credential_id,
            principal=credential.principal, client_namespace="work:pause", allowed_kinds=("pause_task", "resume_task"),
            allowed_task_ids=(task_id,), allowed_projection_task_ids=(task_id,), expires_at=expires,
        ), capability=owner)
        grants.issue(HostCommandGrantRequest(
            grant_id="work-complete", credential_id=credential.credential_id,
            principal=credential.principal, client_namespace="work:complete", allowed_kinds=("complete_task",),
            allowed_task_ids=(task_id,), allowed_projection_task_ids=(task_id,), expires_at=expires,
        ), capability=owner)
        read_grant = RuntimeReadGrant(
            grant_id="read:work", principal=credential.principal, allowed_task_ids=(task_id,),
            expires_at=expires, epoch=1,
        )
        ports = HermesRuntimeStatePorts(service)
        reader = ports.host_work_projection(credential=secret, grant=read_grant)
        assert reader.read(task_id=task_id) is None
        pause_delivery = _stage_projection(commands, RuntimeCommandRequest(
            kind="pause_task", operation_id="pause", task_id=task_id, expected_revision=task.version,
            pause_reason="waiting",
        ))
        assert reader.read(task_id=task_id) is None
        resume = RuntimeCommandRequest(
            kind="resume_task", operation_id="resume", task_id=task_id, expected_revision=task.version + 1,
        )
        commands.dispatch(resume, operation_origin=commands.prepare(resume))
        complete_delivery = _stage_projection(commands, RuntimeCommandRequest(
            kind="complete_task", operation_id="finish", task_id=task_id, expected_revision=task.version + 2,
            completion_evidence=TaskCompletionEvidence(),
        ))
        WriterEnrollmentRegistry(root / "control" / "writers").enroll("work-reader-test", kind="managed_work_projection")
        worker = ManagedWorkProjectionWorker(service, worker_id="work-reader-test")
        for delivery_id in (complete_delivery, pause_delivery):
            claim = worker.claim(delivery_id)
            assert claim is not None
            assert worker.publish(claim) is not None
        committed = service.acquire_verified_snapshot()

    with StorageAdministrationService(root) as reopened:
        assert reopened.acquire_verified_snapshot() == committed
        ports = HermesRuntimeStatePorts(reopened)
        reader = ports.host_work_projection(credential=secret, grant=read_grant)
        highest = reader.read(task_id=task_id)
        assert highest is not None and highest.summary.status == WorkStateStatus.RESOLVED
        assert highest.summary.work_state_id == f"runtime:{task_id}"

        with pytest.raises(WorkProjectionRecallError, match="denied:"):
            reader.read(task_id="task:other")
        with pytest.raises(WorkProjectionRecallError, match="denied:"):
            ports.host_work_projection(credential=other_secret, grant=read_grant).read(task_id=task_id)
        with pytest.raises(WorkProjectionRecallError, match="unauthenticated:"):
            ports.host_work_projection(credential="missing", grant=read_grant).read(task_id=task_id)
        empty_grant = read_grant.model_copy(update={"allowed_task_ids": ()})
        with pytest.raises(WorkProjectionRecallError, match="denied:"):
            ports.host_work_projection(credential=secret, grant=empty_grant).read(task_id=task_id)

        owner = mint_owner_capability(reopened, "owner")
        grants = ManagedHostCommandAuthority(reopened)
        grants.revoke("work-complete", capability=owner)
        previous = reader.read(task_id=task_id)
        assert previous is not None and previous.summary.status == WorkStateStatus.PAUSED
        assert previous.origin_runtime_revision < highest.origin_runtime_revision
        grants.revoke("work-pause", capability=owner)
        assert reader.read(task_id=task_id) is None

        GrantEpochRegistry(root / "control" / "grants").revoke(read_grant.grant_id, reason="withdraw scope")
        with pytest.raises(WorkProjectionRecallError, match="denied:"):
            reader.read(task_id=task_id)


@pytest.mark.parametrize("failure", [StorageAdministrationError("stale handle"), InstallationIntegrityError("bad tuple")])
def test_embedded_bound_read_maps_partition_transition_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: StorageAdministrationError,
) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        ports = HermesRuntimeStatePorts(service)
        ports.bind_task(RuntimeTaskBinding(installation_task_id="task:one", granted_to_principal="principal:one"))

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise failure

        monkeypatch.setattr(HarnessStateService, "read_state", refuse)
        with pytest.raises(HarnessStateError, match="^(unavailable|integrity_error):"):
            ports.read_bound_state(principal="principal:one")
