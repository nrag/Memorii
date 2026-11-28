"""Installed operator wiring and failure cuts through managed native owners."""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state import native_sources
from memorii.core.harness_state.managed_enrollment import HostEnrollmentRequest, ManagedHostEnrollment
from memorii.core.harness_state.sidecar import RuntimeSidecar
from memorii.core.harness_state.write_authority import NativeSourceScope
from memorii.core.persistence.runtime_api import ManagedRuntimeCommandService
from memorii.core.persistence.runtime_contracts import OperationOrigin, RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.managed_spool_selection import open_managed_spool, register_managed_spool
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.stores.sqlite.private_storage import finish_private_handoff, read_private_file, write_private_file
from memorii.tools.runtime_operator import main


def _managed_sidecar(administration: StorageAdministrationService) -> RuntimeSidecar:
    enrollment = ManagedHostEnrollment(administration)
    return RuntimeSidecar.for_managed_installation(
        administration, credentials=enrollment.credentials, enrollment=enrollment,
        spool=open_managed_spool(administration),
    )


def _state(sidecar: RuntimeSidecar, credential: str, task_id: str) -> int:
    status, _ = sidecar.handle_state_request(
        bearer_token=credential, origin=None, body=json.dumps({"task_id": task_id}).encode(),
    )
    return status


def _source(
    sidecar: RuntimeSidecar, credential: str, task_id: str, source: NativeSourceScope,
    *, capture: bool = False,
) -> tuple[int, bytes]:
    payload: dict[str, object] = {"task_id": task_id, "source": source.model_dump(mode="json")}
    if capture:
        payload.update(delivery_id="turn:one", text="test native captured text")
    return sidecar.handle_native_source_request(
        bearer_token=credential, origin=None, host=None, body=json.dumps(payload).encode(), capture=capture,
    )


def test_running_operator_prevents_cutover_of_legacy_managed_spool(tmp_path: Path) -> None:
    installation = tmp_path / "installation"
    capability_file = tmp_path / "owner-capability"
    with StorageAdministrationService(installation) as administration:
        administration.initialize()
        capability = mint_owner_capability(administration, "owner")
        write_private_file(capability_file, capability.capability_digest.encode("ascii"), exclusive=True)
        operator = StorageAdministrationOperator(administration)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only", expected_control_revision=operator.status().control_revision,
                reason="stage a managed spool",
            ),
            capability=capability,
        )
    owner = [
        sys.executable, "-m", "memorii.tools.runtime_operator", "--installation-root", str(installation),
        "--owner-principal", "owner", "--capability-file", str(capability_file),
    ]
    register = [*owner, "runtime-spool", "register"]
    with subprocess.Popen([*owner, "serve", "--port", "0"], stdout=subprocess.PIPE, text=True) as serving:
        try:
            assert serving.stdout is not None
            with selectors.DefaultSelector() as readiness:
                readiness.register(serving.stdout, selectors.EVENT_READ)
                assert readiness.select(timeout=15), "foreground operator did not report ready"
            assert json.loads(serving.stdout.readline())["status"] == "ready"
            refused = subprocess.run(register, capture_output=True, text=True, timeout=15, check=False)
            assert refused.returncode == 3
            assert "conflict" in refused.stderr
        finally:
            serving.terminate()
            serving.wait(timeout=15)
    subprocess.run(register, capture_output=True, text=True, timeout=15, check=True)


def test_operator_enrolls_distinct_credentials_for_the_same_principal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    installation = tmp_path / "installation"
    capability_file = tmp_path / "owner-capability"
    owner = ["--installation-root", str(installation), "--owner-principal", "owner:test"]
    assert main([*owner, "init", "--capability-output", str(capability_file)]) == 0
    assert capability_file.stat().st_mode & 0o777 == 0o600
    assert capability_file.read_text() not in capsys.readouterr().out
    owner.extend(("--capability-file", str(capability_file)))
    expires_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    def enroll(
        operation: str, source: NativeSourceScope, destination: Path, *task_arguments: str,
    ) -> tuple[dict[str, str], list[str]]:
        args = [
            *owner, "runtime-grant", "enroll-native", "--operation-id", operation,
            "--principal", "operator-shared-principal", "--native-source", source.model_dump_json(),
            "--expires-at", expires_at, "--credential-output", str(destination), *task_arguments,
        ]
        assert main(args) == 0
        output = capsys.readouterr().out
        assert destination.read_text() not in output
        assert destination.stat().st_mode & 0o777 == 0o600
        return json.loads(output), args

    pi_source = NativeSourceScope(kind="pi", session_id="pi-session")
    openclaw_source = NativeSourceScope(kind="openclaw", session_id="gateway-session")
    pi_file = tmp_path / "pi-credential"
    openclaw_file = tmp_path / "openclaw-credential"
    pi, pi_args = enroll("provision-pi", pi_source, pi_file, "--goal", "Pi task")
    openclaw, _ = enroll("provision-openclaw", openclaw_source, openclaw_file, "--goal", "OpenClaw task")
    pi_secret, openclaw_secret = pi_file.read_text(), openclaw_file.read_text()
    assert main(pi_args) == 0
    assert json.loads(capsys.readouterr().out) == pi
    assert pi_file.read_text() == pi_secret
    assert main([*pi_args[:-1], "Different goal"]) == 3
    assert not capsys.readouterr().out

    with StorageAdministrationService(installation) as administration:
        sidecar = _managed_sidecar(administration)
        assert _state(sidecar, pi_secret, pi["task_id"]) == 200
        assert _state(sidecar, openclaw_secret, openclaw["task_id"]) == 200
        assert _state(sidecar, pi_secret, openclaw["task_id"]) == 403
        assert _state(sidecar, openclaw_secret, pi["task_id"]) == 403
        prepare = json.dumps({
            "kind": "resume_task", "operation_id": "crossed-resume",
            "task_id": openclaw["task_id"], "expected_revision": 1,
        }).encode()
        assert sidecar.handle_prepare_request(bearer_token=pi_secret, origin=None, body=prepare)[0] == 403
        status, proof = sidecar.handle_prepare_request(bearer_token=openclaw_secret, origin=None, body=prepare)
        assert status == 200
        intake = json.dumps({"command": json.loads(prepare)}).encode()
        assert sidecar.handle_intake_request(
            bearer_token=pi_secret, origin=None, body=intake, operation_origin=proof.decode(),
        )[0] == 403
        assert sidecar.handle_consolidation_read_request(
            bearer_token=pi_secret, origin=None,
            body=json.dumps({"task_id": openclaw["task_id"], "origin_operation_id": "close"}).encode(),
        )[0] == 403
        assert _source(sidecar, pi_secret, openclaw["task_id"], openclaw_source)[0] == 403
        assert _source(sidecar, pi_secret, pi["task_id"], openclaw_source)[0] == 403
        assert _source(sidecar, pi_secret, pi["task_id"], pi_source, capture=True)[0] == 200

    with StorageAdministrationService(installation) as administration:
        sidecar = _managed_sidecar(administration)
        status, payload = _source(sidecar, pi_secret, pi["task_id"], pi_source)
        assert status == 200
        assert json.loads(payload)["messages"][0]["text"] == "test native captured text"

    replacement = tmp_path / "rotated-pi"
    rotated, _ = enroll(
        "rotate-pi", pi_source, replacement, "--task-id", pi["task_id"],
        "--replaces-grant-id", pi["command_grant_id"],
    )
    assert rotated["task_id"] == pi["task_id"]
    assert rotated["credential_id"] != pi["credential_id"]
    with StorageAdministrationService(installation) as administration:
        sidecar = _managed_sidecar(administration)
        assert _state(sidecar, pi_secret, pi["task_id"]) == 401
        assert _state(sidecar, replacement.read_text(), pi["task_id"]) == 200
        assert main([*owner, "runtime-grant", "revoke", "--grant-id", rotated["command_grant_id"]]) == 0
        assert _state(sidecar, replacement.read_text(), pi["task_id"]) == 403
        assert _state(sidecar, openclaw_secret, openclaw["task_id"]) == 200


def test_enrollment_crash_cuts_preserve_one_task_and_withhold_unhanded_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    installation = tmp_path / "installation"
    request = HostEnrollmentRequest(
        operation_id="provision-retry", principal="native", source=NativeSourceScope(kind="pi", session_id="native"),
        goal="One task despite retries", expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    credential_file = tmp_path / "credential"
    issued: list[str] = []
    with StorageAdministrationService(installation) as administration:
        administration.initialize()
        capability = mint_owner_capability(administration, "owner")
        enrollment = ManagedHostEnrollment(administration)
        dispatch = ManagedRuntimeCommandService.dispatch

        def fail_after_task(
            service: ManagedRuntimeCommandService, command: RuntimeCommandRequest, *, operation_origin: OperationOrigin,
        ) -> None:
            dispatch(service, command, operation_origin=operation_origin)
            raise OSError("simulated process exit after signed task")

        with monkeypatch.context() as interruption:
            interruption.setattr(ManagedRuntimeCommandService, "dispatch", fail_after_task)
            with pytest.raises(OSError, match="simulated process exit"):
                enrollment.enroll(request, capability=capability, credential_file=credential_file)
        assert not credential_file.exists()
        issue = enrollment.credentials.issue

        def fail_after_issue(principal: str, *, credential_id: str | None = None) -> None:
            _, secret = issue(principal, credential_id=credential_id)
            issued.append(secret)
            raise OSError("simulated process exit after issuing the digest")

        with monkeypatch.context() as interruption:
            interruption.setattr(enrollment.credentials, "issue", fail_after_issue)
            with pytest.raises(OSError, match="simulated process exit"):
                enrollment.enroll(request, capability=capability, credential_file=credential_file)
        assert not credential_file.exists()
        repository = RuntimeStateRepository(administration.partition())
        task_id, = tuple(task.task_id for task in repository.list_tasks())
        assert _state(_managed_sidecar(administration), issued[0], task_id) == 403

    def fail_before_activation(*args: object, **kwargs: object) -> None:
        raise OSError("simulated process exit after private handoff")

    with StorageAdministrationService(installation) as administration:
        enrollment = ManagedHostEnrollment(administration)
        with monkeypatch.context() as interruption:
            interruption.setattr(native_sources, "enroll_native_source", fail_before_activation)
            with pytest.raises(OSError, match="simulated process exit"):
                enrollment.enroll(request, capability=capability, credential_file=credential_file)
        handed_off = credential_file.read_text()
        sidecar = _managed_sidecar(administration)
        assert _state(sidecar, issued[0], task_id) == 401
        assert _state(sidecar, handed_off, task_id) == 403
        assert _source(sidecar, handed_off, task_id, request.source, capture=True)[0] == 403

    with StorageAdministrationService(installation) as administration:
        result = ManagedHostEnrollment(administration).enroll(
            request, capability=capability, credential_file=credential_file,
        )
        assert result.task_id == task_id
        assert credential_file.read_text() == handed_off
        assert _state(_managed_sidecar(administration), handed_off, task_id) == 200
        assert len(RuntimeStateRepository(administration.partition()).list_tasks()) == 1


def test_backup_pins_signed_pending_managed_intake_and_verifies_restore_stage(tmp_path: Path) -> None:
    credential_file = tmp_path / "credential"
    archive = tmp_path / "archive"
    staging = tmp_path / "stage"
    key = b"k" * 32
    with StorageAdministrationService(tmp_path / "installation") as administration:
        administration.initialize()
        capability = mint_owner_capability(administration, "owner")
        operator = StorageAdministrationOperator(administration)

        def set_mode(mode: str) -> None:
            operator.change_mode(ModeChangeRequest.model_validate({
                "target_mode": mode, "expected_control_revision": operator.status().control_revision,
                "reason": "backup pending native intake",
            }), capability=capability)

        set_mode("read_only")
        binding = register_managed_spool(administration, capability=capability, store_id="1" * 32)
        set_mode("active")
        enrollment = ManagedHostEnrollment(administration).enroll(
            HostEnrollmentRequest(
                operation_id="enroll", principal="principal", goal="Task created by owner",
                source=NativeSourceScope(kind="pi", session_id="scope"),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            ),
            capability=capability, credential_file=credential_file,
        )
        secret = credential_file.read_text()
        sidecar = _managed_sidecar(administration)
        command = {
            "kind": "resume_task", "operation_id": "pending-resume",
            "task_id": enrollment.task_id, "expected_revision": 1,
        }
        status, proof = sidecar.handle_prepare_request(
            bearer_token=secret, origin=None, body=json.dumps(command).encode(),
        )
        assert status == 200
        intake = sidecar.handle_intake_request(
            bearer_token=secret, origin=None, body=json.dumps({"command": command}).encode(),
            operation_origin=proof.decode(),
        )
        assert intake[0] == 200
        spool = open_managed_spool(administration)
        assert len(spool.pending()) == 1

        set_mode("read_only")
        backups = BackupRestoreOperator(operator)
        manifest = backups.create_backup(
            capability=capability, archive_root=archive, reason="pending intake cut", recovery_key=key,
        )
        assert manifest.manifest_version == 3
        assert manifest.managed_spool is not None
        assert manifest.managed_spool.store_id == binding.store_id
        assert manifest.managed_spool.high_water_mark == 1
        plan = backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=False)
        backups.apply_restore(capability=capability, plan=plan, staging_root=staging, recovery_key=key)
        attestation = backups.verify_staged_restore(capability=capability, plan=plan, staging_root=staging)
        assert attestation.spool_snapshot_digest is not None
        assert (staging / "managed-spool.sqlite3").is_file()
        assert len(open_managed_spool(administration).pending()) == 1


def test_exclusive_credential_publication_recovers_after_process_exit(tmp_path: Path) -> None:
    target = tmp_path / "handoff"
    program = """
import os
import sys
from pathlib import Path
from memorii.stores.sqlite.private_storage import write_private_file

link = os.link
def stop_after_link(source, destination):
    link(source, destination)
    os._exit(23)
os.link = stop_after_link
write_private_file(Path(sys.argv[1]), b'private bytes', exclusive=True)
"""
    child = subprocess.run([sys.executable, "-c", program, str(target)], check=False, timeout=20)
    assert child.returncode == 23
    assert target.stat().st_nlink == 2
    with pytest.raises(OSError):
        read_private_file(target, limit=64)
    finish_private_handoff(target)
    assert target.stat().st_nlink == 1
    assert read_private_file(target, limit=64) == b"private bytes"
