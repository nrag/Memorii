"""Loopback sidecar journeys: transport posture, credentials, protocol."""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
