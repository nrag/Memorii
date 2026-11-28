"""Installed v8 sidecar and owner drain for the native host journeys."""

from __future__ import annotations

import http.client
import json
import select
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from memorii.core.harness_state.envelope import HarnessStateEnvelope
from memorii.core.harness_state.native_sources import NativeSourceCaptureRequest
from memorii.core.harness_state.write_authority import NativeSourceScope
from memorii.core.persistence.runtime_contracts import RuntimeCommandReceipt
from memorii.core.storage_administration.managed_spool_selection import open_managed_spool
from memorii.core.storage_administration.service import StorageAdministrationService


def _observation_handler(
    port: int, observations: list[tuple[NativeSourceCaptureRequest, RuntimeCommandReceipt]],
) -> type[BaseHTTPRequestHandler]:
    """Relay loopback host requests unchanged to the installed sidecar."""

    class ObserveCapture(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            body = self.rfile.read(int(self.headers["Content-Length"]))
            headers = {
                name: self.headers[name]
                for name in ("Host", "Origin", "Authorization", "Content-Type", "Memorii-Operation-Origin")
                if name in self.headers
            }
            upstream = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                upstream.request("POST", self.path, body=body, headers=headers)
                response = upstream.getresponse()
                status, payload = response.status, response.read()
            finally:
                upstream.close()
            if self.path == "/v1/runtime/source/capture" and status == 200:
                observations.append((
                    NativeSourceCaptureRequest.model_validate_json(body),
                    RuntimeCommandReceipt.model_validate_json(payload),
                ))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ObserveCapture


def _stop_process(process: subprocess.Popen[str]) -> None:
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    finally:
        if process.stdout is not None:
            process.stdout.close()


class ManagedHostJourney:
    def __init__(self, root: Path, host, session_id: str) -> None:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.installation = root / "installation"
        self.goal = f"Resume the persisted {host} task"
        self.principal = "principal:a"
        self.source = NativeSourceScope(kind=host, session_id=session_id)
        self.model_requests: list[dict] = []
        self.observations: list[tuple[NativeSourceCaptureRequest, RuntimeCommandReceipt]] = []
        self._process: subprocess.Popen[str] | None = None
        self._operator = [
            str(Path(sys.executable).with_name("memorii-operator")),
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
            "MEMORII_SIDECAR_URL": "http://127.0.0.1:8762",
            "MEMORII_TASK_ID": self.task_id,
            "MEMORII_CREDENTIAL_PATH": str(credential_path),
        }

    def start(self) -> None:
        assert self._process is None
        self.observations.clear()
        process = subprocess.Popen(
            [*self._operator, "serve", "--port", "0"], stdout=subprocess.PIPE, text=True,
        )
        try:
            assert process.stdout is not None
            assert select.select([process.stdout], [], [], 30)[0], "installed operator did not report readiness"
            line = process.stdout.readline()
            assert line, f"installed operator exited before readiness: {process.poll()}"
            readiness = json.loads(line)
            assert readiness["status"] == "ready" and readiness["publication_digest"]
            backend = urlsplit(readiness["url"])
            assert backend.scheme == "http" and backend.hostname == "127.0.0.1" and backend.port
            self._server = ThreadingHTTPServer(("127.0.0.1", 8762), _observation_handler(backend.port, self.observations))
            self._worker = Thread(target=self._server.serve_forever, daemon=True)
            self._worker.start()
        except BaseException:
            _stop_process(process)
            raise
        self.url = readiness["url"]
        self._process = process

    def stop(self) -> None:
        if self._process is None:
            return
        try:
            self._server.shutdown()
            self._worker.join()
            self._server.server_close()
        finally:
            _stop_process(self._process)
            self._process = None

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
        [(captured, receipt)] = self.observations
        assert captured.text == prompt and captured.source == self.source
        assert receipt.status == "committed" and receipt.operation_origin and receipt.source_admission
        assert receipt.source_admission.task_id == self.task_id
        with StorageAdministrationService(self.installation) as administration:
            spool = open_managed_spool(administration)
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
            [str(Path(sys.executable).with_name("memorii-consume")),
             "--installation-root", str(self.installation), "--managed", "--drain"],
            capture_output=True, text=True, timeout=90, check=False,
        )
