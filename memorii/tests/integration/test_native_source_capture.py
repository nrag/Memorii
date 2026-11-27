"""Recovery of a signed native observation across a sidecar outage."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from memorii.core.harness_state import native_sources
from memorii.core.harness_state.consumer import ManagedRuntimeSpool
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry
from memorii.core.harness_state.managed_ingress import authenticated_host_commands
from memorii.core.harness_state.native_source_release import issue_native_source_release
from memorii.core.harness_state.native_sources import (
    NativeSourceCaptureRequest,
    NativeSourceRecallRequest,
    NativeSourceService,
    enroll_native_source,
)
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.write_authority import (
    HostCommandGrantRequest,
    ManagedHostCommandAuthority,
    NativeSourceScope,
)
from memorii.core.persistence.runtime_api import ManagedRuntimeCommandService, RuntimeCommandError
from memorii.core.persistence.runtime_contracts import RuntimeCommandReceipt, RuntimeCommandRequest, TaskRecord
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import ExecutionNodeStatus, ExecutionNodeType
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.tools.runtime_consume import main as drain


@pytest.mark.parametrize("revoked", [False, True])
def test_managed_owner_resolves_native_observation_after_sidecar_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], revoked: bool,
) -> None:
    scope = NativeSourceScope(kind="pi", session_id="local-session")
    root = tmp_path / "installation"
    credentials = SidecarCredentialStore(root / "control" / "runtime-credentials")
    credential, secret = credentials.issue("principal:a")
    now = datetime.now(UTC)
    capture = NativeSourceCaptureRequest(task_id="task:scope", source=scope, delivery_id="message-1", text="precise")
    recall = NativeSourceRecallRequest(task_id=capture.task_id, source=scope)

    def read_grant(principal: str) -> RuntimeReadGrant:
        return RuntimeReadGrant(
            grant_id="native-read", principal=principal, expires_at=now + timedelta(hours=1),
            allowed_task_ids=(capture.task_id,), epoch=1,
        )

    with StorageAdministrationService(root) as administration:
        administration.initialize()
        spool = ManagedRuntimeSpool(root / "spool" / "managed")
        task = TaskRecord(
            task_id=capture.task_id, principal=credential.principal, goal="continue",
            created_at=now, root_execution_node_id="exec:root",
        )
        node = ExecutionNode(
            id=task.root_execution_node_id, type=ExecutionNodeType.MISSION, title="Root", description="Graph root",
            status=ExecutionNodeStatus.READY, owner=task.principal, created_at=now, updated_at=now,
        )

        def seed(connection, repository) -> None:
            repository.apply_task(connection, task)
            repository.apply_execution_node(
                connection, task_id=task.task_id, node_id=node.id, node_json=node.model_dump_json(),
            )

        publish_runtime_change(administration, seed, operation_binding="native_source_test_task")
        capability = mint_owner_capability(administration, "owner")
        enrollment = enroll_native_source(
            administration, HostCommandGrantRequest(
                grant_id="capture", credential_id=credential.credential_id, principal=credential.principal,
                client_namespace="host:pi", allowed_kinds=("record_observation", "pause_task"),
                allowed_task_ids=(task.task_id,),
                native_source=scope, expires_at=now + timedelta(hours=1),
            ), capability=capability,
        )
        service = NativeSourceService(administration, credentials, spool, read_grant)
        grant_directory = root / "control" / "runtime-write-grants"
        with pytest.raises(RuntimeCommandError, match="unauthenticated"):
            service.capture("unknown", capture.model_copy(update={"task_id": "task:unbound"}))
        assert list(grant_directory.glob("capture-*.lock")) == []

        def unavailable(*args, **kwargs) -> None:
            raise RuntimeCommandError("unavailable: simulated loss after durable intake")

        with monkeypatch.context() as fault:
            fault.setattr(ManagedRuntimeCommandService, "dispatch", unavailable)
            with pytest.raises(RuntimeCommandError, match="simulated loss"):
                service.capture(secret, capture)
        [pending] = spool.pending()
        assert capture.text not in pending.model_dump_json()
        assert service.recall(secret, recall).messages == ()
        changed_task = task.model_copy(update={"goal": "updated independently", "version": task.version + 1})
        publish_runtime_change(
            administration, lambda connection, repository: repository.apply_task(connection, changed_task),
            operation_binding="native_source_test_task",
        )
        if revoked:
            ManagedHostCommandAuthority(administration).revoke(enrollment.grant_id, capability=capability)

    status = drain(["--installation-root", str(root), "--managed", "--drain"])
    output = capsys.readouterr()
    with StorageAdministrationService(root) as reopened:
        service = NativeSourceService(reopened, credentials, spool, read_grant)
        if revoked:
            assert status == 3 and "denied" in output.err and output.out == ""
            with pytest.raises(RuntimeCommandError, match="denied"):
                service.recall(secret, recall)
            with pytest.raises(RuntimeCommandError, match="denied"):
                service.capture(secret, capture)
            return
        assert status == 0 and spool.pending() == ()
        receipt = RuntimeCommandReceipt.model_validate_json(output.out)
        assert receipt.operation_origin == pending.operation_origin.coordinate
        task_after_drain = RuntimeStateRepository(reopened.partition()).get_task(capture.task_id)
        assert task_after_drain is not None and task_after_drain.goal == "updated independently"
        assert service.capture(secret, capture) == receipt
        [message] = service.recall(secret, recall).messages
        assert message.text == capture.text
        second = service.capture(secret, capture.model_copy(update={"delivery_id": "message-2"}))
        assert second != receipt
        assert [item.text for item in service.recall(secret, recall).messages] == ["precise", "precise"]
        owner = mint_owner_capability(reopened, "owner")
        for observation in (receipt, second):
            assert observation.operation_origin is not None
            entry = spool.find(observation.operation_origin)
            assert entry is not None
            release = issue_native_source_release(reopened, capability=owner, entry=entry)
            assert release.source == observation.source_admission
        current_task = RuntimeStateRepository(reopened.partition()).get_task(capture.task_id)
        assert current_task is not None
        pause = RuntimeCommandRequest(
            kind="pause_task", task_id=capture.task_id, operation_id="pause-after-native-capture",
            expected_revision=current_task.version, pause_reason="handoff",
        )
        commands = authenticated_host_commands(reopened, credentials, secret)
        assert commands.dispatch(pause, operation_origin=commands.prepare(pause)).status == "committed"
        original_resolver = native_sources.resolve_enrolled_runtime_source
        read_epochs = GrantEpochRegistry(root / "control" / "grants")

        def revoke_during_read(*args, **kwargs):
            result = original_resolver(*args, **kwargs)
            if read_epochs.current_epoch("native-read") == 1:
                read_epochs.revoke("native-read", reason="during native recall")
            return result

        monkeypatch.setattr(native_sources, "resolve_enrolled_runtime_source", revoke_during_read)
        with pytest.raises(RuntimeCommandError, match="denied"):
            service.recall(secret, recall)
