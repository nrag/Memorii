"""Installed v8 sidecar and owner drain for the native host journeys."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from memorii.core.harness_state.consumer import ManagedRuntimeSpool
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.envelope import HarnessStateEnvelope
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.sidecar import RuntimeSidecar, SidecarError, serve_loopback
from memorii.core.harness_state.write_authority import HostCommandGrantRequest, ManagedHostCommandAuthority
from memorii.core.persistence.runtime_contracts import RuntimeCommandReceipt, RuntimeCommandRequest, TaskRecord
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService


class ObservedSidecar(RuntimeSidecar):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.observations: list[tuple[str | None, int, str | None]] = []

    def handle_prepare_request(self, **kwargs) -> tuple[int, bytes]:
        status, body = super().handle_prepare_request(**kwargs)
        command = RuntimeCommandRequest.model_validate_json(kwargs["body"])
        if command.kind == "record_observation":
            error_code = SidecarError.model_validate_json(body).code if status != 200 else None
            self.observations.append((command.source_digest, status, error_code))
        return status, body


class ManagedHostJourney:
    def __init__(self, root: Path, host: str) -> None:
        self.installation = root / "installation"
        self.task_id = f"task:{host}-session"
        self.goal = f"Resume the persisted {host} task"
        self.credentials = SidecarCredentialStore(self.installation / "control" / "runtime-credentials")
        self.spool_root = self.installation / "spool" / "managed"
        self.principal = "principal:a"
        self.credential, self.secret = self.credentials.issue(self.principal)
        with StorageAdministrationService(self.installation) as administration:
            administration.initialize()
            task = TaskRecord(
                task_id=self.task_id, principal=self.principal, goal=self.goal,
                created_at=datetime.now(UTC), root_execution_node_id="exec:root",
            )
            publish_runtime_change(
                administration, lambda connection, repo: repo.apply_task(connection, task),
                operation_binding="host_journey_task",
            )
            ManagedHostCommandAuthority(administration).issue(
                HostCommandGrantRequest(
                    grant_id=f"commands:{host}", principal=self.principal, credential_id=self.credential.credential_id,
                    client_namespace=f"host:{host}", allowed_task_ids=(self.task_id,),
                    allowed_kinds=("resume_task", "record_observation"),
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                ),
                capability=mint_owner_capability(administration, "owner"),
            )

        credential_path = root / "host.credential"
        descriptor = os.open(credential_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as writer:
            writer.write(self.secret)
        self.start()
        self.environment = {
            "MEMORII_SIDECAR_URL": self.url,
            "MEMORII_TASK_ID": self.task_id,
            "MEMORII_CREDENTIAL_PATH": str(credential_path),
        }

    def start(self) -> None:
        self.administration = StorageAdministrationService(self.installation)
        self.sidecar = ObservedSidecar.for_managed_installation(
            self.administration, credentials=self.credentials, grant_factory=self.read_grant,
            spool=ManagedRuntimeSpool(self.spool_root),
        )
        self.url, self.server = serve_loopback(self.sidecar, port=8762)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.administration.close()

    def read_grant(self, principal: str) -> RuntimeReadGrant:
        return RuntimeReadGrant(
            grant_id=f"read:{principal}", principal=principal, allowed_task_ids=(self.task_id,),
            epoch=1, expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    def read(self) -> HarnessStateEnvelope:
        request = urllib.request.Request(
            f"{self.url}/v1/runtime/state",
            data=json.dumps({
                "protocol_version": 1, "task_id": self.task_id, "view": "summary", "include_task_version": True,
            }).encode(),
            headers={"Authorization": f"Bearer {self.secret}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return HarnessStateEnvelope.model_validate_json(response.read())

    def prove_turn(self, prompt: str) -> RuntimeCommandReceipt:
        assert self.sidecar.observations == [
            (hashlib.sha256(prompt.encode()).hexdigest(), 503, "unsupported_configuration"),
        ]
        print("Native message text matched; governed source owner unavailable (503)", flush=True)
        spool = ManagedRuntimeSpool(self.spool_root)
        [entry] = spool.pending()
        assert entry.delivery.command.kind == "resume_task"
        result = self.drain()
        assert result.returncode == 0, result.stderr
        receipt = RuntimeCommandReceipt.model_validate_json(result.stdout)
        assert receipt.status == "committed" and receipt.operation_origin == entry.operation_origin.coordinate
        assert entry.delivery.command.task_id == self.task_id
        assert spool.pending() == ()
        retry = self.drain()
        assert retry.returncode == 0 and retry.stdout == ""
        repository = RuntimeStateRepository(self.administration.partition())
        assert repository.get_task(self.task_id) is not None
        print("Signed resume committed via managed drain; retry empty", flush=True)
        return receipt

    def drain(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "memorii.tools.runtime_consume",
             "--installation-root", str(self.installation), "--managed", "--drain"],
            capture_output=True, text=True, timeout=90, check=False,
        )
