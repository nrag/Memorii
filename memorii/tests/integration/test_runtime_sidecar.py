"""Loopback sidecar journeys: transport posture, credentials, protocol."""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.sidecar import (
    RuntimeSidecar,
    SidecarRequest,
    serve_loopback,
)
from memorii.core.persistence.runtime_contracts import TaskRecord
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _sidecar(tmp_path: Path) -> tuple[RuntimeSidecar, str]:
    administration = StorageAdministrationService(tmp_path / "installation")
    administration.initialize()
    repository = RuntimeStateRepository(administration.partition())
    task_id = "task:sidecar"

    def seed(connection, repo) -> None:
        repo.apply_task(
            connection,
            TaskRecord(
                task_id=task_id,
                principal="principal:a",
                goal="Sidecar journey",
                created_at=_NOW,
                root_execution_node_id="exec:root",
            ),
        )

    publish_runtime_change(administration, seed, operation_binding="sidecar_seed")

    def grant_for(principal: str) -> RuntimeReadGrant:
        return RuntimeReadGrant(
            grant_id=f"sidecar:{principal}",
            principal=principal,
            allowed_task_ids=(task_id,),
            epoch=1,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    sidecar = RuntimeSidecar(
        repository,
        credentials={"credential:one": "principal:a"},
        grant_factory=grant_for,
    )
    return sidecar, task_id


def _body(task_id: str) -> bytes:
    return SidecarRequest(task_id=task_id).model_dump_json().encode()


def test_authorized_request_serves_envelope(tmp_path: Path) -> None:
    sidecar, task_id = _sidecar(tmp_path)
    status, payload = sidecar.handle_state_request(
        bearer_token="credential:one",
        origin=None,
        body=_body(task_id),
        host="127.0.0.1",
    )
    assert status == 200
    envelope = json.loads(payload)
    assert envelope["task_id"] == task_id
    assert envelope["status"] in ("ready", "revalidate_required", "reconcile_required")


def test_browser_origin_rejected_before_any_task_data(tmp_path: Path) -> None:
    sidecar, task_id = _sidecar(tmp_path)
    status, payload = sidecar.handle_state_request(
        bearer_token="credential:one",
        origin="http://localhost:3000",
        body=_body(task_id),
        host="127.0.0.1",
    )
    assert status == 403
    assert json.loads(payload)["code"] == "denied"
    assert task_id not in payload.decode()


def test_missing_or_invalid_credential_is_unauthenticated_without_content(
    tmp_path: Path,
) -> None:
    sidecar, task_id = _sidecar(tmp_path)
    for token in (None, "credential:wrong"):
        status, payload = sidecar.handle_state_request(
            bearer_token=token,
            origin=None,
            body=_body(task_id),
            host="127.0.0.1",
        )
        assert status == 401
        assert json.loads(payload)["code"] == "unauthenticated"
        assert task_id not in payload.decode()


def test_remote_binding_refused(tmp_path: Path) -> None:
    sidecar, task_id = _sidecar(tmp_path)
    status, payload = sidecar.handle_state_request(
        bearer_token="credential:one",
        origin=None,
        body=_body(task_id),
        host="0.0.0.0",
    )
    assert status == 403
    assert json.loads(payload)["code"] == "denied"


def test_denied_and_not_found_map_to_closed_codes(tmp_path: Path) -> None:
    sidecar, task_id = _sidecar(tmp_path)
    # Authorized principal, other task: grant scope denies before lookup.
    status, payload = sidecar.handle_state_request(
        bearer_token="credential:one",
        origin=None,
        body=_body("task:other"),
        host="127.0.0.1",
    )
    assert status == 403
    # Unparsable body.
    status, payload = sidecar.handle_state_request(
        bearer_token="credential:one",
        origin=None,
        body=b"{not-json",
        host="127.0.0.1",
    )
    assert status == 400
    assert json.loads(payload)["code"] == "invalid_request"


def test_loopback_http_serves_the_same_protocol(tmp_path: Path) -> None:
    sidecar, task_id = _sidecar(tmp_path)
    url, server = serve_loopback(sidecar)
    try:
        request = urllib.request.Request(
            url + "/v1/runtime/state",
            data=_body(task_id),
            headers={"Authorization": "Bearer credential:one"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            envelope = json.loads(response.read())
            assert envelope["task_id"] == task_id
    finally:
        server.shutdown()
        server.server_close()


def test_python_client_speaks_the_same_protocol(tmp_path: Path) -> None:
    from memorii.core.harness_state.client import (
        RuntimeClientError,
        RuntimeStateClient,
    )

    sidecar, task_id = _sidecar(tmp_path)
    url, server = serve_loopback(sidecar)
    try:
        client = RuntimeStateClient(url, credential="credential:one")
        envelope = client.get_state(task_id)
        assert envelope.task_id == task_id
        denied_client = RuntimeStateClient(url, credential="credential:wrong")
        with pytest.raises(RuntimeClientError, match="401 unauthenticated"):
            denied_client.get_state(task_id)
        with pytest.raises(ValueError, match="loopback"):
            RuntimeStateClient("http://0.0.0.1:8080", credential="x")
    finally:
        server.shutdown()
        server.server_close()


def test_credential_store_backed_sidecar_serves_and_denies(tmp_path: Path) -> None:
    from memorii.core.harness_state.credentials import SidecarCredentialStore

    administration = StorageAdministrationService(tmp_path / "installation")
    administration.initialize()
    repository = RuntimeStateRepository(administration.partition())
    store = SidecarCredentialStore(tmp_path / "installation" / "control" / "credentials")
    record, secret = store.issue("principal:a")
    task_id = "task:cred"

    def seed(connection, repo) -> None:
        repo.apply_task(
            connection,
            TaskRecord(
                task_id=task_id,
                principal=record.principal,
                goal="Credential journey",
                created_at=_NOW,
                root_execution_node_id="exec:root",
            ),
        )

    publish_runtime_change(administration, seed, operation_binding="cred_seed")

    def grant_for(principal: str) -> RuntimeReadGrant:
        return RuntimeReadGrant(
            grant_id=f"sidecar:{principal}",
            principal=principal,
            allowed_task_ids=(task_id,),
            epoch=1,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    sidecar = RuntimeSidecar(
        repository, credentials=store, grant_factory=grant_for
    )
    status, payload = sidecar.handle_state_request(
        bearer_token=secret,
        origin=None,
        body=_body(task_id),
        host="127.0.0.1",
    )
    assert status == 200 and json.loads(payload)["task_id"] == task_id
    status, _payload = sidecar.handle_state_request(
        bearer_token="mri_forged",
        origin=None,
        body=_body(task_id),
        host="127.0.0.1",
    )
    assert status == 401
    store.verify_permissions()


def test_consume_cli_admits_dispatches_and_refuses_untrusted(tmp_path: Path) -> None:
    from memorii.tools.runtime_consume import main as consume_main

    root = tmp_path / "installation"
    administration = StorageAdministrationService(root)
    administration.initialize()
    administration.close()

    delivery = {
        "transport_message_id": "msg:one",
        "command": {
            "kind": "start_task",
            "operation_id": "op:consume-one",
            "goal": "Consumed durably",
        },
    }
    delivery_path = tmp_path / "delivery.json"
    delivery_path.write_text(json.dumps(delivery), encoding="utf-8")

    assert (
        consume_main(
            [
                "--installation-root",
                str(root),
                "--producer",
                "producer:trusted",
                "--delivery",
                str(delivery_path),
            ]
        )
        == 0
    )
    # Repeat delivery is idempotent: the same receipt, one task.
    assert (
        consume_main(
            [
                "--installation-root",
                str(root),
                "--producer",
                "producer:trusted",
                "--delivery",
                str(delivery_path),
            ]
        )
        == 0
    )
    administration = StorageAdministrationService(root)
    try:
        repository = RuntimeStateRepository(administration.partition())
        assert len(repository.list_tasks()) == 1
    finally:
        administration.close()

    forged = dict(delivery) | {
        "command": {
            "kind": "start_task",
            "operation_id": "op:consume-one",
            "goal": "Divergent intent",
        }
    }
    forged_path = tmp_path / "forged.json"
    forged_path.write_text(json.dumps(forged), encoding="utf-8")
    assert (
        consume_main(
            [
                "--installation-root",
                str(root),
                "--producer",
                "producer:untrusted",
                "--delivery",
                str(forged_path),
            ]
        )
        == 3
    )


def _intake_sidecar(tmp_path: Path) -> tuple[RuntimeSidecar, str, Path]:
    from memorii.core.harness_state.consumer import LocalDurableSpool
    from memorii.core.harness_state.sidecar import HostIntakeBinding

    sidecar, task_id = _sidecar(tmp_path)
    spool_directory = tmp_path / "spool"
    sidecar._intake_factory = lambda principal: HostIntakeBinding(
        spool=LocalDurableSpool(spool_directory),
        producer_binding=f"host:{principal}",
        allowlisted_producers=(f"host:{principal}",),
    )
    return sidecar, task_id, spool_directory


def _intake_body(
    operation_id: str,
    task_id: str,
    *,
    kind: str = "record_observation",
    revision: int = 0,
) -> bytes:
    from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest

    command = RuntimeCommandRequest(
        kind=kind,  # type: ignore[arg-type]
        operation_id=operation_id,
        task_id=task_id,
        expected_revision=revision,
        source_digest="a" * 64 if kind == "record_observation" else None,
    )
    import json

    return json.dumps(
        {"protocol_version": 1, "command": command.model_dump(mode="json")}
    ).encode()


def test_intake_admits_durably_and_idempotently(tmp_path: Path) -> None:
    sidecar, task_id, spool_directory = _intake_sidecar(tmp_path)
    first = sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=_intake_body("op:1", task_id)
    )
    assert first[0] == 200
    record = json.loads(first[1])
    assert record["operation_id"] == "op:1"
    assert record["state"] == "pending"
    assert (spool_directory / "intake.jsonl").exists()
    lines = (spool_directory / "intake.jsonl").read_text().splitlines()
    assert len(lines) == 1

    second = sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=_intake_body("op:1", task_id)
    )
    assert second[0] == 200
    assert json.loads(second[1])["operation_id"] == "op:1"
    assert len((spool_directory / "intake.jsonl").read_text().splitlines()) == 1


def test_intake_divergent_duplicate_dead_letters_as_conflict(tmp_path: Path) -> None:
    sidecar, task_id, _ = _intake_sidecar(tmp_path)
    assert sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=_intake_body("op:1", task_id)
    )[0] == 200
    divergent = _intake_body("op:1", task_id, kind="record_action_dispatch")
    status, payload = sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=divergent
    )
    assert status == 409
    assert json.loads(payload)["code"] == "conflict"


def test_intake_rejects_unknown_kind_and_mismatched_payload(tmp_path: Path) -> None:
    sidecar, task_id, _ = _intake_sidecar(tmp_path)
    unknown = _intake_body("op:2", task_id).replace(
        b'"record_observation"', b'"fabricate_truth"'
    )
    status, payload = sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=unknown
    )
    assert status == 400
    assert json.loads(payload)["code"] == "invalid_request"

    start_without_goal = b'{"protocol_version":1,"command":{"kind":"start_task","operation_id":"op:3"}}'
    status, payload = sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=start_without_goal
    )
    assert status == 400
    assert json.loads(payload)["code"] == "invalid_request"


def test_intake_posture_matches_the_read_route(tmp_path: Path) -> None:
    sidecar, task_id, _ = _intake_sidecar(tmp_path)
    body = _intake_body("op:4", task_id)
    assert sidecar.handle_intake_request(
        bearer_token=None, origin=None, body=body
    )[0] == 401
    status, payload = sidecar.handle_intake_request(
        bearer_token="credential:one", origin="http://127.0.0.1:4000", body=body
    )
    assert status == 403
    assert "task" not in payload.decode().lower()
    assert sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=body, host="10.0.0.9"
    )[0] == 403
    assert sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=b"x" * (2 << 20)
    )[0] == 400


def test_intake_without_configured_binding_is_unavailable(tmp_path: Path) -> None:
    sidecar, task_id = _sidecar(tmp_path)
    status, payload = sidecar.handle_intake_request(
        bearer_token="credential:one", origin=None, body=_intake_body("op:5", task_id)
    )
    assert status == 503
    assert json.loads(payload)["code"] == "unavailable"


def test_loopback_http_serves_intake(tmp_path: Path) -> None:
    sidecar, task_id, _ = _intake_sidecar(tmp_path)
    url, server = serve_loopback(sidecar)
    try:
        request = urllib.request.Request(
            f"{url}/v1/runtime/intake",
            data=_intake_body("op:http", task_id),
            headers={"Authorization": "Bearer credential:one"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 200
            assert json.loads(response.read())["operation_id"] == "op:http"
    finally:
        server.shutdown()
        server.server_close()


def test_intake_refuses_malformed_content_length_before_reading(tmp_path: Path) -> None:
    sidecar, task_id, _ = _intake_sidecar(tmp_path)
    body = _intake_body("op:cl", task_id)
    for header in ("not-a-number", "-5", str(2 << 20)):
        status, payload = sidecar.handle_intake_request(
            bearer_token="credential:one",
            origin=None,
            body=body,
            host="127.0.0.1",
            _content_length_header=header,
        )
        assert status == 400, header
        assert json.loads(payload)["code"] == "invalid_request"
    # A valid header still parses (route reaches auth/parse normally).
    status, _ = sidecar.handle_intake_request(
        bearer_token=None, origin=None, body=body, host="127.0.0.1",
        _content_length_header=str(len(body)),
    )
    assert status == 401
