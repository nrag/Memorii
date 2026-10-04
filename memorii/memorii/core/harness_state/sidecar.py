"""Loopback runtime sidecar: typed HTTP over the persistent partition.

Transport posture is part of the contract: the sidecar binds loopback
only, rejects browser-origin requests before any task-derived data,
requires an installation-issued bearer credential mapped server-side to
a finite read grant, and refuses remote binding. Request strings never
choose principal authority. No task-derived data appears in
unauthenticated or denied responses.

The intake route extends the same posture to writes: a bearer
credential maps server-side to one producer binding over one durable
spool, the closed runtime-command union validates server-side, and
admission is durable before acknowledgement.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.harness_state.consumer import (
    ConsumerDeliveryError,
    HostEventDelivery,
    LocalDurableSpool,
)
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry
from memorii.core.harness_state.service import (
    HarnessStateError,
    HarnessStateService,
    RuntimeReadGrant,
)
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.revoked_identity_view import (
    RevokedIdentityServingGate,
)

_MAXIMUM_INTAKE_BYTES = 1 << 20


class SidecarRequest(BaseModel):
    """Closed v1 state request body."""

    protocol_version: Literal[1] = 1
    task_id: str = Field(min_length=1)
    view: Literal["execution", "solver", "summary", "history", "neighborhood"] = "summary"
    cursor: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class SidecarIntakeRequest(BaseModel):
    """Closed v1 intake body: one runtime command, authority stays server-side."""

    protocol_version: Literal[1] = 1
    command: RuntimeCommandRequest
    transport_message_id: str | None = Field(default=None, min_length=1, max_length=256)

    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class HostIntakeBinding:
    """Server-derived write authority for one authenticated principal."""

    spool: LocalDurableSpool
    producer_binding: str
    allowlisted_producers: tuple[str, ...]


class SidecarError(BaseModel):
    """Closed error envelope; no task-derived data."""

    code: Literal[
        "unauthenticated",
        "denied",
        "not_found",
        "unsupported_version",
        "unsupported_configuration",
        "invalid_request",
        "conflict",
        "stale_cursor",
        "resource_exhausted",
        "unavailable",
        "integrity_error",
        "needs_reconciliation",
    ]
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
        credentials: dict[str, str] | SidecarCredentialStore,
        grant_factory: Callable[[str], RuntimeReadGrant],
        intake_factory: Callable[[str], HostIntakeBinding] | None = None,
        grant_registry: GrantEpochRegistry | None = None,
        revoked_view: RevokedIdentityServingGate | None = None,
    ) -> None:
        self._repository = repository
        self._credentials = credentials
        self._grant_factory = grant_factory
        self._intake_factory = intake_factory
        # The revocation registry composes by default from the installation
        # control state so a revoked grant fails closed on every served path.
        if grant_registry is None:
            from pathlib import Path as _Path

            registry_root = (
                _Path(repository._partition.database_path).parent.parent
                / "control"
                / "grants"
            )
            try:
                grant_registry = GrantEpochRegistry(registry_root)
            except OSError:
                grant_registry = None
        # The revoked-identity view composes by default from the same
        # installation control state so revoked justifications never sponsor
        # a served hypothesis on any host surface.
        if revoked_view is None:
            from pathlib import Path as _Path

            from memorii.core.storage_administration.revoked_identity_view import (
                RefreshingRevokedIdentityView,
            )

            try:
                revoked_view = RefreshingRevokedIdentityView(
                    _Path(repository._partition.database_path).parent.parent
                    / "control"
                )
            except (OSError, ValueError):
                revoked_view = None
        self._service = HarnessStateService(
            repository, grant_registry=grant_registry, revoked_view=revoked_view
        )

    def _principal_for(self, secret: str) -> str | None:
        if isinstance(self._credentials, SidecarCredentialStore):
            return self._credentials.principal_for(secret)
        return self._credentials.get(secret)

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
        principal = self._principal_for(bearer_token or "")
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

    def handle_intake_request(
        self,
        *,
        bearer_token: str | None,
        origin: str | None,
        body: bytes,
        host: str | None = None,
        _content_length_header: str | None = None,
    ) -> tuple[int, bytes]:
        """Admit one runtime command durably; authority is server-derived.

        ``_content_length_header`` is a test hook replaying a raw header
        value through the pre-read validation the HTTP layer performs.
        """
        if (
            _content_length_header is not None
            and _safe_content_length(_content_length_header, _MAXIMUM_INTAKE_BYTES) is None
        ):
            return _error(
                400, "invalid_request", "content length is invalid or oversized"
            )
        if host is not None and host not in ("127.0.0.1", "localhost", "::1"):
            return _error(403, "denied", "remote binding is disabled")
        if origin is not None:
            return _error(403, "denied", "browser-origin requests are rejected")
        principal = self._principal_for(bearer_token or "")
        if principal is None:
            return _error(401, "unauthenticated", None)
        if self._intake_factory is None:
            return _error(503, "unavailable", None)
        binding = self._intake_factory(principal)
        if binding.producer_binding not in binding.allowlisted_producers:
            # Configuration inconsistency, never a client-supplied escape.
            return _error(503, "unavailable", None)
        if len(body) > _MAXIMUM_INTAKE_BYTES:
            return _error(400, "invalid_request", "intake body exceeds the closed limit")
        try:
            request = SidecarIntakeRequest.model_validate_json(body)
        except ValueError:
            return _error(400, "invalid_request", "body is not a closed v1 intake request")
        delivery = HostEventDelivery(
            transport_message_id=request.transport_message_id
            or f"sidecar:{request.command.operation_id}",
            producer_binding=binding.producer_binding,
            command=request.command,
        )
        try:
            record = binding.spool.admit(
                delivery, allowlisted_producers=binding.allowlisted_producers
            )
        except ConsumerDeliveryError as exc:
            message = str(exc)
            if message.startswith("conflict:"):
                return _error(409, "conflict", None)
            if message.startswith("denied:"):
                return _error(403, "denied", None)
            return _error(503, "unavailable", None)
        return 200, record.model_dump_json().encode("utf-8")


def _safe_content_length(raw: str | None, maximum: int) -> int | None:
    """Parse Content-Length before any read: non-integer, negative, and
    oversized values are refused pre-authentication so the handler never
    buffers unbounded input or blocks on a malformed request."""
    try:
        length = int(raw) if raw not in (None, "") else 0
    except ValueError:
        return None
    if length < 0 or length > maximum:
        return None
    return length


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
            if self.path == "/v1/runtime/intake":
                length = _safe_content_length(self.headers.get("Content-Length"), _MAXIMUM_INTAKE_BYTES)
                if length is None:
                    self._respond(*_error(400, "invalid_request", "content length is invalid or oversized"))
                    return
                body = self.rfile.read(length) if length else b""
                status, payload = sidecar.handle_intake_request(
                    bearer_token=self.headers.get("Authorization", "").removeprefix(
                        "Bearer "
                    )
                    or None,
                    origin=self.headers.get("Origin"),
                    body=body,
                    host=self.headers.get("Host", "").split(":")[0] or None,
                )
                self._respond(status, payload)
                return
            if self.path != "/v1/runtime/state":
                self._respond(*_error(404, "not_found", None))
                return
            length = _safe_content_length(self.headers.get("Content-Length"), _MAXIMUM_INTAKE_BYTES)
            if length is None:
                self._respond(*_error(400, "invalid_request", "content length is invalid or oversized"))
                return
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
    "HostIntakeBinding",
    "RuntimeSidecar",
    "SidecarError",
    "SidecarIntakeRequest",
    "SidecarRequest",
    "build_sidecar_handler",
    "serve_loopback",
]
