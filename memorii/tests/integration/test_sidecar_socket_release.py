"""Observe protected response release through real loopback sockets."""

from __future__ import annotations

import http.client
import json
import socket
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

import pytest
from memorii.core.harness_state import sidecar as transport
from memorii.core.harness_state.consumer import ManagedRuntimeSpool
from memorii.core.harness_state.grant_registry import GrantEpochRegistry
from memorii.core.harness_state.managed_enrollment import HostEnrollmentRequest, ManagedHostEnrollment
from memorii.core.harness_state.sidecar import RuntimeSidecar, build_sidecar_handler
from memorii.core.harness_state.write_authority import NativeSourceScope
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService


class _SmallSendBufferServer(ThreadingHTTPServer):
    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        accepted, address = super().get_request()
        accepted.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        return accepted, address


@dataclass(frozen=True)
class _EnrolledSocket:
    administration: StorageAdministrationService
    sidecar: RuntimeSidecar
    grants: GrantEpochRegistry
    secret: str
    task_id: str
    read_grant_id: str
    command_grant_id: str
    source: NativeSourceScope


@contextmanager
def _server(sidecar: RuntimeSidecar) -> Iterator[int]:
    with _SmallSendBufferServer(("127.0.0.1", 0), build_sidecar_handler(sidecar)) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield int(server.server_address[1])
        finally:
            server.shutdown()
            worker.join()


@pytest.fixture
def enrolled(tmp_path: Path) -> Iterator[_EnrolledSocket]:
    with StorageAdministrationService(tmp_path / "installation") as administration:
        administration.initialize()
        enrollment = ManagedHostEnrollment(administration)
        credential_file = tmp_path / "credential"
        source = NativeSourceScope(kind="pi", session_id="authorized-session")
        receipt = enrollment.enroll(
            HostEnrollmentRequest(
                operation_id="enroll-for-socket",
                principal="local-owner",
                source=source,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                goal="Synthetic socket release witness",
            ),
            capability=mint_owner_capability(administration, "local-owner"),
            credential_file=credential_file,
        )
        sidecar = RuntimeSidecar.for_managed_installation(
            administration, credentials=enrollment.credentials, enrollment=enrollment,
            spool=ManagedRuntimeSpool(administration.installation_root / "spool" / "managed"),
        )
        yield _EnrolledSocket(
            administration, sidecar, GrantEpochRegistry(administration.installation_root / "control" / "grants"),
            credential_file.read_text(), receipt.task_id, receipt.read_grant_id, receipt.command_grant_id, source,
        )


def test_rotation_after_assembly_denies_before_first_response_byte(
    enrolled: _EnrolledSocket, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar, task_id = enrolled.sidecar, enrolled.task_id
    sampled = Event()
    proceed = Event()
    prepare = sidecar.prepare_socket_response

    def pause_after_assembly(*args, **kwargs):
        result = prepare(*args, **kwargs)
        assert result[0] == 200
        sampled.set()
        assert proceed.wait(timeout=1)
        return result

    monkeypatch.setattr(sidecar, "prepare_socket_response", pause_after_assembly)

    def request(port: int, secret: str) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request(
                "POST", "/v1/runtime/state", json.dumps({"task_id": task_id}),
                {"Authorization": f"Bearer {secret}"},
            )
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    with _server(sidecar) as port, ThreadPoolExecutor() as executor:
        result = executor.submit(request, port, enrolled.secret)
        try:
            assert sampled.wait(timeout=2)
            replacement = tmp_path / "replacement"
            administration = enrolled.administration
            ManagedHostEnrollment(administration).enroll(
                HostEnrollmentRequest(
                    operation_id="rotate-before-first-write", principal="local-owner", source=enrolled.source,
                    expires_at=datetime.now(UTC) + timedelta(hours=1), task_id=task_id,
                    replaces_grant_id=enrolled.command_grant_id,
                ),
                capability=mint_owner_capability(administration, "local-owner"),
                credential_file=replacement,
            )
        finally:
            proceed.set()
        status, body = result.result(timeout=3)
        assert request(port, replacement.read_text())[0] == 200
    assert status == 403
    assert json.loads(body)["code"] == "denied"
    assert task_id.encode() not in body


def test_revocation_while_socket_waits_aborts_partial_protected_response(
    enrolled: _EnrolledSocket, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = enrolled.sidecar
    waiting = Event()
    proceed = Event()
    handle_state = sidecar.handle_state_request
    real_select = transport.select
    real_send = socket.socket.send
    accepted = bytearray()
    payload = b'{"state":"' + b"x" * (768 * 1024) + b'never-release-after-revocation"}'

    def large_protected_response(**kwargs):
        status, body = handle_state(**kwargs)
        return (status, payload) if status == 200 else (status, body)

    def pause_if_socket_is_full(*args):
        waiting.set()
        assert proceed.wait(timeout=1)
        return real_select(*args)

    def record_accepted_bytes(connection: socket.socket, data: memoryview) -> int:
        count = real_send(connection, data)
        accepted.extend(data[:count])
        return count

    monkeypatch.setattr(sidecar, "handle_state_request", large_protected_response)
    monkeypatch.setattr(transport, "select", pause_if_socket_is_full)
    monkeypatch.setattr(socket.socket, "send", record_accepted_bytes)
    body = json.dumps({"task_id": enrolled.task_id}).encode()
    with _server(sidecar) as port, socket.socket() as connection:
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        connection.settimeout(3)
        connection.connect(("127.0.0.1", port))
        connection.sendall(
            f"POST /v1/runtime/state HTTP/1.0\r\nAuthorization: Bearer {enrolled.secret}\r\n"
            f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        )
        try:
            assert waiting.wait(timeout=2)
            before_revocation = bytes(accepted)
            enrolled.grants.revoke(enrolled.read_grant_id, reason="owner revoked during socket backpressure")
        finally:
            proceed.set()
        chunks = []
        while chunk := connection.recv(65536):
            chunks.append(chunk)
    received = b"".join(chunks)
    assert received == before_revocation
    header, _, sent = received.partition(b"\r\n\r\n")
    assert b" 200 " in header
    assert sent and len(sent) < len(payload)
    assert payload.startswith(sent)
    assert b"never-release-after-revocation" not in sent
