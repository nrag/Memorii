"""Loopback runtime sidecar: typed HTTP over the persistent partition.

Transport posture is part of the contract: the sidecar binds loopback
only, rejects browser-origin requests before any task-derived data,
requires an installation-issued bearer credential mapped server-side to
a finite read grant, and refuses remote binding. Request strings never
choose principal authority. No task-derived data appears in
unauthenticated or denied responses.
"""

from __future__ import annotations

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.harness_state.service import (
    HarnessStateError,
    HarnessStateService,
    RuntimeReadGrant,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository


class SidecarRequest(BaseModel):
    """Closed v1 state request body."""

    protocol_version: Literal[1] = 1
    task_id: str = Field(min_length=1)
    view: Literal["execution", "solver", "summary", "history", "neighborhood"] = "summary"
    cursor: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class SidecarError(BaseModel):
    """Closed error envelope; no task-derived data."""

    code: str
    retryable: bool
    detail: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


_ERROR_STATUS = {
    "unauthenticated": 401,
    "denied": 403,
    "not_found": 404,
    "invalid_request": 400,
    "unsupported_version": 400,
    "conflict": 409,
    "stale_cursor": 409,
    "resource_exhausted": 429,
    "unavailable": 503,
    "integrity_error": 500,
    "needs_reconciliation": 409,
}


class RuntimeSidecar:
    """Composition root wiring credentials, grants and the read service."""

    def __init__(
        self,
        repository: RuntimeStateRepository,
        *,
        credentials: dict[str, str],
        grant_factory: Callable[[str], RuntimeReadGrant],
    ) -> None:
        self._repository = repository
        self._credentials = credentials
        self._grant_factory = grant_factory
        self._service = HarnessStateService(repository)

    def handle_state_request(
        self,
        *,
        bearer_token: str | None,
        origin: str | None,
        body: bytes,
        host: str | None = None,
    ) -> tuple[int, bytes]:
        """Serve one state request; returns (status, body)."""
        if host is not None and host not in ("127.0.0.1", "localhost", "::1"):
            return _error(403, "denied", "remote binding is disabled")
        if origin is not None:
            return _error(403, "denied", "browser-origin requests are rejected")
        principal = self._credentials.get(bearer_token or "")
        if principal is None:
            return _error(
                401, "unauthenticated", None
            )  # no content, no task existence
        try:
            request = SidecarRequest.model_validate_json(body)
        except ValueError:
            return _error(400, "invalid_request", "body is not a closed v1 request")
        grant = self._grant_factory(principal)
        try:
            envelope = self._service.read_state(
                task_id=request.task_id,
                grant=grant,
                view=request.view,
                cursor=request.cursor,
                # history/neighborhood page through the summary view until
                # their paged carriers exist; the request still fails closed
                # on unsupported forms through the service's view gate.
            )
        except HarnessStateError as exc:
            code = _harness_error_code(str(exc))
            return _error(_ERROR_STATUS.get(code, 400), code, None)
        return 200, envelope.model_dump_json().encode("utf-8")


def _error(status: int, code: str, detail: str | None) -> tuple[int, bytes]:
    payload = SidecarError(code=code, retryable=code in ("unavailable", "resource_exhausted"), detail=detail)
    return status, payload.model_dump_json().encode("utf-8")


def _harness_error_code(message: str) -> str:
    for code in _ERROR_STATUS:
        if message.startswith(code):
            return code
    return "invalid_request"


def build_sidecar_handler(sidecar: RuntimeSidecar) -> type[BaseHTTPRequestHandler]:
    """HTTP handler bound to one sidecar instance."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            if self.path != "/v1/runtime/state":
                self._respond(*_error(404, "not_found", None))
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b"{}"
            status, payload = sidecar.handle_state_request(
                bearer_token=self.headers.get("Authorization", "").removeprefix(
                    "Bearer "
                )
                or None,
                origin=self.headers.get("Origin"),
                body=body,
                host=self.headers.get("Host", "").split(":")[0] or None,
            )
            self._respond(status, payload)

        def log_message(self, *args: object) -> None:
            return  # content-free logging only

        def _respond(self, status: int, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def serve_loopback(
    sidecar: RuntimeSidecar, *, port: int = 0
) -> tuple[str, ThreadingHTTPServer]:
    """Bind loopback only; serve in a daemon thread; returns URL and server."""
    import threading

    server = ThreadingHTTPServer(("127.0.0.1", port), build_sidecar_handler(sidecar))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


__all__ = [
    "RuntimeSidecar",
    "SidecarError",
    "SidecarRequest",
    "build_sidecar_handler",
    "serve_loopback",
]
