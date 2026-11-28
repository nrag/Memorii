"""Installed v8 sidecar and owner drain for the native host journeys."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from memorii.core.harness_state.envelope import HarnessStateEnvelope
from memorii.core.harness_state.managed_enrollment import ManagedHostEnrollment
from memorii.core.harness_state.native_sources import NativeSourceCaptureRequest
from memorii.core.harness_state.sidecar import RuntimeSidecar, serve_loopback
from memorii.core.harness_state.write_authority import NativeSourceScope
from memorii.core.persistence.runtime_contracts import RuntimeCommandReceipt
from memorii.core.storage_administration.managed_spool_selection import open_managed_spool
from memorii.core.storage_administration.service import StorageAdministrationService


class ObservedSidecar(RuntimeSidecar):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.observations: list[tuple[NativeSourceCaptureRequest, RuntimeCommandReceipt]] = []

    def handle_native_source_request(self, **kwargs) -> tuple[int, bytes]:
        status, body = super().handle_native_source_request(**kwargs)
        if kwargs["capture"] and status == 200:
            self.observations.append((
                NativeSourceCaptureRequest.model_validate_json(kwargs["body"]),
                RuntimeCommandReceipt.model_validate_json(body),
            ))
        return status, body


class ManagedHostJourney:
    def __init__(self, root: Path, host, session_id: str) -> None:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.installation = root / "installation"
        self.goal = f"Resume the persisted {host} task"
        self.principal = "principal:a"
        self.source = NativeSourceScope(kind=host, session_id=session_id)
        self.model_requests: list[dict] = []
        self._operator = [
            sys.executable, "-m", "memorii.tools.runtime_operator",
            "--installation-root", str(self.installation), "--owner-principal", "owner",
        ]
        capability_path = root / "owner.cap"
        credential_path = root / "host.credential"
        subprocess.run(
            [*self._operator, "init", "--capability-output", str(capability_path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        self._operator.extend(("--capability-file", str(capability_path)))
        enrolled = subprocess.run(
            [*self._operator, "runtime-grant", "enroll-native", "--operation-id", f"enroll:{host}",
             "--principal", self.principal, "--native-source", self.source.model_dump_json(),
             "--expires-at", (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
             "--credential-output", str(credential_path), "--goal", self.goal],
            capture_output=True, text=True, timeout=30, check=True,
        )
        receipt = json.loads(enrolled.stdout)
        self.task_id = receipt["task_id"]
        self.grant_id = receipt["command_grant_id"]
        self.secret = credential_path.read_text(encoding="ascii")
        assert self.secret not in enrolled.stdout and self.secret not in enrolled.stderr
        self.start()
        self.environment = {
            "MEMORII_SIDECAR_URL": self.url,
            "MEMORII_TASK_ID": self.task_id,
            "MEMORII_CREDENTIAL_PATH": str(credential_path),
        }

    def start(self) -> None:
        self.administration = StorageAdministrationService(self.installation)
        enrollment = ManagedHostEnrollment(self.administration)
        self.sidecar = ObservedSidecar.for_managed_installation(
            self.administration, credentials=enrollment.credentials, enrollment=enrollment,
            spool=open_managed_spool(self.administration),
        )
        self.url, self.server = serve_loopback(self.sidecar, port=8762)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.administration.close()

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

    def source_request(self, endpoint: str, **fields: object) -> tuple[int, dict]:
        body = {"task_id": self.task_id, "source": self.source.model_dump(), **fields}
        request = urllib.request.Request(
            f"{self.url}/v1/runtime/source/{endpoint}", data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.secret}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def prove_turn(self, prompt: str) -> RuntimeCommandReceipt:
        [(captured, receipt)] = self.sidecar.observations
        assert captured.text == prompt and captured.source == self.source
        assert receipt.status == "committed" and receipt.operation_origin and receipt.source_admission
        assert receipt.source_admission.task_id == self.task_id
        spool = open_managed_spool(self.administration)
        entry = spool.find(receipt.operation_origin)
        assert entry is not None and entry.state == "committed"
        assert entry.operation_origin.coordinate == receipt.operation_origin
        assert prompt not in entry.model_dump_json()
        assert spool.pending() == ()
        retry = self.drain()
        assert retry.returncode == 0 and retry.stdout == ""
        status, payload = self.source_request("capture", delivery_id=captured.delivery_id, text=prompt)
        assert status == 200 and RuntimeCommandReceipt.model_validate(payload) == receipt
        status, payload = self.source_request("capture", delivery_id=captured.delivery_id, text=prompt + " altered")
        assert status == 409 and payload["code"] == "conflict"
        assert self.source_request("recall", task_id="task:other")[0] == 403
        assert self.source_request("recall", source={"kind": self.source.kind, "session_id": "unbound"})[0] == 403
        print("Exact user text committed with a signed observation; duplicate reused the same receipt", flush=True)
        return receipt

    def prove_recall(self, first_prompt: str) -> None:
        status, recall = self.source_request("recall")
        assert status == 200 and recall["messages"][-1]["text"] == first_prompt

    def prove_model_recall(self, first_prompt: str) -> None:
        assert any(
            "Memorii historical user data" in message and first_prompt in message
            for message in self.last_model_messages()
        ), "recalled data did not appear in the model request"
        print("Restarted native host delivered the remembered text to the model", flush=True)

    def last_model_messages(self) -> list[str]:
        return [json.dumps(message.get("content")) for message in self.model_requests[-1]["messages"]]

    def revoke(self) -> None:
        subprocess.run(
            [*self._operator, "runtime-grant", "revoke", "--grant-id", self.grant_id],
            capture_output=True, text=True, timeout=30, check=True,
        )
        status, payload = self.source_request("recall")
        assert status == 403 and payload["code"] == "denied" and "messages" not in payload
        status, payload = self.source_request("capture", delivery_id="revoked-delivery", text="revoked input")
        assert status == 403 and payload["code"] == "denied"
        print("Revoked enrollment denied recall", flush=True)

    def prove_model_without_recall(self) -> None:
        assert all("Memorii historical user data" not in message for message in self.last_model_messages())

    def drain(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "memorii.tools.runtime_consume",
             "--installation-root", str(self.installation), "--managed", "--drain"],
            capture_output=True, text=True, timeout=90, check=False,
        )
