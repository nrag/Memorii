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

import sqlite3
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from select import select
from time import monotonic, sleep
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from memorii.core.harness_state.consolidation_read import (
    ConsolidationReadError,
    ConsolidationReadRequest,
    ConsolidationReadService,
    authenticated_consolidation_reader,
)
from memorii.core.harness_state.consumer import (
    ConsumerDeliveryError,
    HostEventDelivery,
    LocalDurableSpool,
    ManagedRuntimeSpool,
    SpoolRecord,
)
from memorii.core.harness_state.credentials import CredentialError, IssuedCredential, SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry, GrantRegistryError
from memorii.core.harness_state.managed_enrollment import HostEnrollmentError, ManagedHostEnrollment
from memorii.core.harness_state.native_sources import (
    NativeSourceCaptureRequest,
    NativeSourceRecallRequest,
    NativeSourceService,
)
from memorii.core.harness_state.paging import HarnessCursorError
from memorii.core.harness_state.service import (
    HarnessStateError,
    HarnessStateService,
    RuntimeReadGrant,
)
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    ManagedHostCommandAuthority,
    NativeSourceScope,
    ResolvedHostCommandAuthority,
)
from memorii.core.harness_state.writeback_decision import WritebackDecisionError, WritebackDecisionService
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.runtime_api import ManagedRuntimeCommandService, RuntimeCommandError
from memorii.core.persistence.runtime_contracts import OperationOrigin, RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.persistence.writeback_decisions import WritebackDecisionRequest
from memorii.core.storage_administration.revoked_identity_view import (
    RevokedIdentityServingGate,
)
from memorii.core.storage_administration.service import (
    InstallationIntegrityError,
    InstallationQuarantinedError,
    StorageAdministrationError,
    StorageAdministrationService,
)

_MAXIMUM_INTAKE_BYTES = 1 << 20
_MAXIMUM_OPERATION_ORIGIN_BYTES = 8192
_SOCKET_RELEASE_SECONDS = 2.0
_SOCKET_RELEASE_CHUNK_BYTES = 64 * 1024
_PREPARED_OPERATION = TypeAdapter(RuntimeCommandRequest | WritebackDecisionRequest)


class SidecarRequest(BaseModel):
    """Closed v1 state request body."""

    protocol_version: Literal[1] = 1
    task_id: str = Field(min_length=1)
    view: Literal["execution", "solver", "summary", "history", "neighborhood"] = "summary"
    cursor: str | None = None
    include_task_version: bool = False

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


@dataclass(frozen=True)
class ManagedHostIntakeBinding:
    """Server-resolved binding for one authenticated credential."""

    spool: ManagedRuntimeSpool
    commands: ManagedRuntimeCommandService


_ReleaseRequest = (
    SidecarRequest | NativeSourceCaptureRequest | NativeSourceRecallRequest | ConsolidationReadRequest
    | RuntimeCommandRequest | WritebackDecisionRequest
)


@dataclass(frozen=True)
class _ReleaseAuthority:
    credential: IssuedCredential
    task_id: str | None
    native_source: NativeSourceScope | None
    read_grant: RuntimeReadGrant | None
    command_grant: ResolvedHostCommandAuthority | None
    control: InstallationControlState
    publication: RuntimePublicationState
    suppression: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class _SocketReleasePermit:
    request: _ReleaseRequest
    authority: _ReleaseAuthority
    payload_digest: bytes
    deadline: float


def _suppression_coordinates(administration: StorageAdministrationService) -> tuple[tuple[int, ...], ...]:
    # Cooperating owners publish journal members by rename under the publication
    # fence. Include both directories to catch an interrupted control update.
    control = administration.installation_root / "control"
    coordinates: list[tuple[int, ...]] = []
    for name in ("suppressions", "suppressions-archive"):
        try:
            info = (control / name).stat(follow_symlinks=False)
        except FileNotFoundError:
            coordinates.append(())
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise StorageAdministrationError("suppression authority is unavailable")
        coordinates.append((info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns))
    return tuple(coordinates)


SidecarErrorCode = Literal[
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


class SidecarError(BaseModel):
    """Closed error envelope; no task-derived data."""

    code: SidecarErrorCode
    retryable: bool
    detail: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


_ERROR_STATUS: dict[SidecarErrorCode, int] = {
    "unauthenticated": 401,
    "denied": 403,
    "not_found": 404,
    "invalid_request": 400,
    "unsupported_version": 400,
    "unsupported_configuration": 503,
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
        grant_factory: Callable[[str], RuntimeReadGrant] | None,
        intake_factory: Callable[[str], HostIntakeBinding] | None = None,
        managed_intake_factory: Callable[[str], ManagedHostIntakeBinding | None] | None = None,
        consolidation_reader_factory: Callable[[str], ConsolidationReadService] | None = None,
        writeback_factory: Callable[[str], WritebackDecisionService] | None = None,
        grant_registry: GrantEpochRegistry | None = None,
        revoked_view: RevokedIdentityServingGate | None = None,
        administration: StorageAdministrationService | None = None,
        native_sources: NativeSourceService | None = None,
        enrollment: ManagedHostEnrollment | None = None,
    ) -> None:
        self._repository = repository
        self._administration = administration
        self._native_sources = native_sources
        self._credentials = credentials
        self._grant_factory = grant_factory
        self._enrollment = enrollment
        self._intake_factory = intake_factory
        if intake_factory is not None and managed_intake_factory is not None:
            raise ValueError("managed and legacy intake bindings are mutually exclusive")
        self._managed_intake_factory = managed_intake_factory
        self._consolidation_reader_factory = consolidation_reader_factory
        self._writeback_factory = writeback_factory
        # The revocation registry composes by default from the installation
        # control state so a revoked grant fails closed on every served path.
        if grant_registry is None:
            registry_root = (
                repository.partition.protected_storage_root.parent
                / "control"
                / "grants"
            )
            try:
                grant_registry = GrantEpochRegistry(registry_root)
            except OSError:
                if administration is not None:
                    raise
                grant_registry = None
        # The revoked-identity view composes by default from the same
        # installation control state so revoked justifications never sponsor
        # a served hypothesis on any host surface.
        if revoked_view is None:
            from memorii.core.storage_administration.revoked_identity_view import (
                RefreshingRevokedIdentityView,
            )

            try:
                revoked_view = RefreshingRevokedIdentityView(
                    repository.partition.protected_storage_root.parent / "control"
                )
            except (OSError, ValueError):
                if administration is not None:
                    raise
                revoked_view = None
        self._service = HarnessStateService(
            repository, grant_registry=grant_registry, revoked_view=revoked_view
        )
        self._grant_registry = grant_registry
        self._revoked_view = revoked_view
        self._socket_commands = None if administration is None else ManagedHostCommandAuthority(administration)

    @classmethod
    def for_managed_installation(
        cls,
        administration: StorageAdministrationService,
        *,
        credentials: SidecarCredentialStore,
        grant_factory: Callable[[str], RuntimeReadGrant] | None = None,
        spool: ManagedRuntimeSpool,
        enrollment: ManagedHostEnrollment | None = None,
    ) -> RuntimeSidecar:
        """Bind installed admission to control grants, separately from reads."""
        from memorii.core.harness_state.managed_ingress import authenticated_host_commands

        if (grant_factory is None) == (enrollment is None):
            raise ValueError("managed sidecar requires exactly one read authority binding")
        credentials.verify_permissions()

        def managed_binding(secret: str) -> ManagedHostIntakeBinding | None:
            if credentials.credential_for(secret) is None:
                return None
            return ManagedHostIntakeBinding(
                spool, authenticated_host_commands(administration, credentials, secret),
            )

        return cls(
            RuntimeStateRepository(administration.partition()),
            credentials=credentials,
            grant_factory=grant_factory,
            managed_intake_factory=managed_binding,
            consolidation_reader_factory=lambda secret: authenticated_consolidation_reader(
                administration, credentials, secret, grant_factory, enrollment=enrollment,
            ),
            writeback_factory=lambda secret: WritebackDecisionService(administration, credentials, secret),
            administration=administration,
            native_sources=NativeSourceService(
                administration, credentials, spool, grant_factory, enrollment=enrollment,
            ),
            enrollment=enrollment,
        )

    def handle_native_source_request(
        self, *, capture: bool, bearer_token: str | None, origin: str | None, body: bytes, host: str | None,
    ) -> tuple[int, bytes]:
        if origin is not None or host not in (None, "127.0.0.1", "localhost", "::1"):
            return _error(403, "denied", None)
        if not bearer_token:
            return _error(401, "unauthenticated", None)
        if self._native_sources is None:
            return _error(503, "unsupported_configuration", None)
        if len(body) > _MAXIMUM_INTAKE_BYTES:
            return _error(400, "invalid_request", None)
        try:
            if capture:
                result = self._native_sources.capture(bearer_token, NativeSourceCaptureRequest.model_validate_json(body))
                return 200, result.model_dump_json().encode()
            recall = self._native_sources.recall(bearer_token, NativeSourceRecallRequest.model_validate_json(body))
            return 200, recall.model_dump_json().encode()
        except (ValidationError, UnicodeError):
            return _error(400, "invalid_request", None)
        except (RuntimeCommandError, ConsumerDeliveryError) as exc:
            code = _harness_error_code(str(exc))
            return _error(_ERROR_STATUS[code], code, None)
        except CredentialError:
            return _error(401, "unauthenticated", None)
        except (InstallationIntegrityError, InstallationQuarantinedError, sqlite3.DatabaseError):
            return _error(500, "integrity_error", None)
        except (OSError, StorageAdministrationError):
            return _error(503, "unavailable", None)

    def _principal_for(self, secret: str) -> str | None:
        if isinstance(self._credentials, SidecarCredentialStore):
            try:
                return self._credentials.principal_for(secret)
            except CredentialError:
                return None
        return self._credentials.get(secret)

    def _state_grant(
        self, *, secret: str, principal: str, task_id: str,
        verified: tuple[InstallationControlState, RuntimePublicationState] | None,
        source: NativeSourceScope | None = None,
        credential: IssuedCredential | None = None,
    ) -> RuntimeReadGrant:
        if self._enrollment is not None:
            if verified is None or not isinstance(self._credentials, SidecarCredentialStore):
                raise HostEnrollmentError("denied: verified read authority is unavailable")
            credential = credential or self._credentials.credential_for(secret)
            if credential is None or credential.principal != principal:
                raise HostEnrollmentError("denied: enrolled credential is unavailable")
            state, finalized = verified
            return self._enrollment.resolve_read(
                credential=credential, task_id=task_id, state=state, finalized=finalized, source=source,
            )
        if self._grant_factory is None:
            raise HostEnrollmentError("denied: read authority is unavailable")
        grant = self._grant_factory(principal)
        if grant.principal != principal or not grant.authorizes(task_id):
            raise HostEnrollmentError("denied: read authority is unavailable")
        return grant

    @property
    def requires_socket_release(self) -> bool:
        return self._administration is not None

    @contextmanager
    def _socket_authority(self, request: _ReleaseRequest, secret: str) -> Iterator[_ReleaseAuthority]:
        administration = self._administration
        credentials = self._credentials
        if administration is None or not isinstance(credentials, SidecarCredentialStore):
            raise StorageAdministrationError("protected socket authority is unavailable")
        with administration.publication_release_context() as verified, credentials.current_credential(secret) as issued:
            state, finalized = verified
            task_id = request.task_id
            source = request.source if isinstance(request, NativeSourceCaptureRequest | NativeSourceRecallRequest) else None
            if state.mode == "bypass":
                raise StorageAdministrationError("protected socket authority is unavailable")
            if task_id is not None and self._revoked_view is not None and self._revoked_view.is_revoked_task(task_id):
                raise HostEnrollmentError("protected task authority is unavailable")
            grant = None
            if isinstance(request, SidecarRequest | NativeSourceRecallRequest | ConsolidationReadRequest):
                grant = self._state_grant(
                    secret=secret, principal=issued.principal, task_id=request.task_id, verified=verified, source=source,
                    credential=issued,
                )
            registry = self._grant_registry
            if grant is not None and registry is None:
                raise StorageAdministrationError("read grant registry is unavailable")
            with (
                registry.current_read(grant.grant_id, grant.epoch, blocking=False)
                if grant is not None and registry is not None else nullcontext()
            ):
                command = self._socket_command_authority(issued, request, state, finalized)
                if source is not None and (command is None or command.native_source != source):
                    raise HostEnrollmentError("protected source authority is unavailable")
                yield _ReleaseAuthority(
                    issued, task_id, source, grant, command, state, finalized,
                    _suppression_coordinates(administration),
                )

    def _socket_command_authority(
        self, credential: IssuedCredential, request: _ReleaseRequest,
        state: InstallationControlState, finalized: RuntimePublicationState,
    ) -> ResolvedHostCommandAuthority | None:
        if isinstance(request, SidecarRequest):
            return None
        grants = self._socket_commands
        if grants is None:
            raise StorageAdministrationError("command grant authority is unavailable")
        if isinstance(request, ConsolidationReadRequest):
            return grants.resolve_consolidation_reader_in_verified_context(
                credential=credential, task_id=request.task_id, origin_operation_id=request.origin_operation_id,
                state=state, finalized=finalized, now=datetime.now(UTC),
            )
        if isinstance(request, WritebackDecisionRequest):
            return grants.resolve_writeback_in_verified_context(
                credential=credential, request=request, state=state, finalized=finalized,
            )
        if isinstance(request, NativeSourceCaptureRequest | NativeSourceRecallRequest):
            request = RuntimeCommandRequest(
                kind="record_observation", task_id=request.task_id, operation_id="native-source-authorization",
                expected_revision=0, source_digest="0" * 64,
            )
        return grants.resolve_for_credential_in_verified_context(
            credential=credential, request=request, state=state, finalized=finalized,
        )

    def _sample_socket_authority(self, request: _ReleaseRequest, secret: str, deadline: float) -> _ReleaseAuthority:
        while monotonic() < deadline:
            try:
                with self._socket_authority(request, secret) as authority:
                    return authority
            except BlockingIOError:
                sleep(min(0.005, max(0.0, deadline - monotonic())))
        raise StorageAdministrationError("protected response release timed out")

    def prepare_socket_response(
        self, request: _ReleaseRequest, *, secret: str, assemble: Callable[[], tuple[int, bytes]], mutates: bool,
    ) -> tuple[int, bytes, _SocketReleasePermit | None]:
        """Bind a successful assembly to the authority under which it ran."""
        deadline = monotonic() + _SOCKET_RELEASE_SECONDS
        try:
            before = self._sample_socket_authority(request, secret, deadline)
            status, payload = assemble()
            if status != 200:
                return status, payload, None
            if len(payload) > _MAXIMUM_INTAKE_BYTES:
                return (*_error(429, "resource_exhausted", None), None)
            after = self._sample_socket_authority(request, secret, deadline)
            old, new = before.publication, after.publication
            if mutates and (
                (old.installation_id, old.repository_id, old.data_generation_id)
                == (new.installation_id, new.repository_id, new.data_generation_id)
            ):
                before = replace(before, publication=new)
            if before != after:
                return (*_error(403, "denied", None), None)
            return status, payload, _SocketReleasePermit(request, after, sha256(payload).digest(), deadline)
        except CredentialError:
            return (*_error(401, "unauthenticated", None), None)
        except (GrantRegistryError, HostCommandAuthorityError, HostEnrollmentError):
            return (*_error(403, "denied", None), None)
        except (OSError, StorageAdministrationError, ValidationError, ValueError, sqlite3.DatabaseError):
            return (*_error(503, "unavailable", None), None)

    @contextmanager
    def socket_release(self, permit: _SocketReleasePermit, secret: str) -> Iterator[None]:
        with self._socket_authority(permit.request, secret) as authority:
            if authority != permit.authority or monotonic() >= permit.deadline:
                raise HostEnrollmentError("protected response release is no longer authorized")
            yield

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
        secret = bearer_token or ""
        principal = self._principal_for(secret)
        if principal is None:
            return _error(
                401, "unauthenticated", None
            )  # no content, no task existence
        try:
            request = SidecarRequest.model_validate_json(body)
        except ValueError:
            return _error(400, "invalid_request", "body is not a closed v1 request")
        administration = self._administration
        try:
            with (
                nullcontext() if administration is None else administration.verified_operation_context()
            ) as verified:
                checkpoint_ref = None
                installation_binding = None
                if verified is not None:
                    state, finalized = verified
                    if state.mode == "bypass":
                        return _error(503, "unavailable", None)
                    checkpoint_ref = finalized.checkpoint_digest
                    installation_binding = (
                        finalized.data_generation_id, state.eligibility_epoch + state.pending_epoch_increments,
                    )
                grant = self._state_grant(secret=secret, principal=principal, task_id=request.task_id, verified=verified)
                envelope = self._service.read_state(
                    task_id=request.task_id,
                    grant=grant,
                    view=request.view,
                    cursor=request.cursor,
                    checkpoint_ref=checkpoint_ref,
                    installation_binding=installation_binding,
                    include_task_version=request.include_task_version,
                )
                if self._principal_for(secret) != principal:
                    return _error(401, "unauthenticated", None)
                grant_lock = (
                    nullcontext() if self._grant_registry is None
                    else self._grant_registry.current_read(grant.grant_id, grant.epoch)
                )
                with grant_lock:
                    if self._enrollment is not None and self._state_grant(
                        secret=secret, principal=principal, task_id=request.task_id, verified=verified,
                    ) != grant:
                        return _error(403, "denied", None)
                    excluded = {"task_version"} if envelope.task_version is None else None
                    return 200, envelope.model_dump_json(exclude=excluded).encode("utf-8")
        except (HostEnrollmentError, GrantRegistryError):
            return _error(403, "denied", None)
        except CredentialError:
            return _error(401, "unauthenticated", None)
        except (HarnessStateError, HarnessCursorError) as exc:
            code = _harness_error_code(str(exc))
            return _error(_ERROR_STATUS.get(code, 400), code, None)
        except (InstallationIntegrityError, InstallationQuarantinedError, sqlite3.DatabaseError):
            return _error(500, "integrity_error", None)
        except (OSError, StorageAdministrationError):
            return _error(503, "unavailable", None)

    def handle_intake_request(
        self,
        *,
        bearer_token: str | None,
        origin: str | None,
        body: bytes,
        host: str | None = None,
        operation_origin: str | None = None,
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
        if self._managed_intake_factory is not None:
            return self._handle_managed_intake(bearer_token or "", body, operation_origin)
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

    def handle_prepare_request(
        self, *, bearer_token: str | None, origin: str | None, body: bytes, host: str | None = None
    ) -> tuple[int, bytes]:
        """Prepare a new managed intent through the authenticated command owner."""
        if origin is not None or host not in (None, "127.0.0.1", "localhost", "::1"):
            return _error(403, "denied", None)
        secret = bearer_token or ""
        if self._principal_for(secret) is None:
            return _error(401, "unauthenticated", None)
        if self._managed_intake_factory is None:
            return _error(503, "unavailable", None)
        if len(body) > _MAXIMUM_INTAKE_BYTES:
            return _error(400, "invalid_request", None)
        try:
            request = _PREPARED_OPERATION.validate_json(body)
        except ValueError:
            return _error(400, "invalid_request", None)
        try:
            if isinstance(request, WritebackDecisionRequest):
                if self._writeback_factory is None:
                    return _error(503, "unavailable", None)
                proof = self._writeback_factory(secret).prepare(request)
            else:
                binding = self._managed_intake_factory(secret)
                if binding is None:
                    return _error(403, "denied", None)
                proof = binding.commands.prepare(request)
        except WritebackDecisionError as exc:
            return _error(_ERROR_STATUS[exc.code], exc.code, None)
        except (InstallationIntegrityError, InstallationQuarantinedError, sqlite3.DatabaseError, ValidationError):
            return _error(500, "integrity_error", None)
        except RuntimeCommandError as exc:
            code = _harness_error_code(str(exc))
            return _error(_ERROR_STATUS[code], code, None)
        except (OSError, StorageAdministrationError):
            return _error(503, "unavailable", None)
        return 200, proof.model_dump_json().encode()

    def handle_writeback_decision_request(
        self, *, bearer_token: str | None, origin: str | None, body: bytes,
        operation_origin: str | None, host: str | None = None,
    ) -> tuple[int, bytes]:
        """Decide a sealed offer using the originally authenticated host intent."""
        if origin is not None or host not in (None, "127.0.0.1", "localhost", "::1"):
            return _error(403, "denied", None)
        secret = bearer_token or ""
        if self._principal_for(secret) is None:
            return _error(401, "unauthenticated", None)
        if self._writeback_factory is None:
            return _error(503, "unavailable", None)
        if not operation_origin:
            return _error(403, "denied", None)
        if len(body) > _MAXIMUM_INTAKE_BYTES or len(operation_origin) > _MAXIMUM_OPERATION_ORIGIN_BYTES:
            return _error(400, "invalid_request", None)
        try:
            request = WritebackDecisionRequest.model_validate_json(body)
            proof = OperationOrigin.model_validate_json(operation_origin)
        except ValidationError:
            return _error(400, "invalid_request", None)
        try:
            receipt = self._writeback_factory(secret).decide(request, operation_origin=proof)
        except WritebackDecisionError as exc:
            return _error(_ERROR_STATUS[exc.code], exc.code, None)
        except (InstallationIntegrityError, InstallationQuarantinedError, sqlite3.DatabaseError, ValidationError):
            return _error(500, "integrity_error", None)
        except (OSError, StorageAdministrationError):
            return _error(503, "unavailable", None)
        return 200, receipt.model_dump_json().encode()

    def handle_consolidation_read_request(
        self, *, bearer_token: str | None, origin: str | None, body: bytes, host: str | None = None
    ) -> tuple[int, bytes]:
        """Read sealed outputs under the current authenticated host scope."""
        if origin is not None or host not in (None, "127.0.0.1", "localhost", "::1"):
            return _error(403, "denied", None)
        secret = bearer_token or ""
        if self._principal_for(secret) is None:
            return _error(401, "unauthenticated", None)
        reader_factory = self._consolidation_reader_factory
        if reader_factory is None:
            return _error(503, "unavailable", None)
        if len(body) > _MAXIMUM_INTAKE_BYTES:
            return _error(400, "invalid_request", None)
        try:
            request = ConsolidationReadRequest.model_validate_json(body)
        except ValueError:
            return _error(400, "invalid_request", None)
        try:
            result = reader_factory(secret).read(request)
        except ConsolidationReadError as exc:
            return _error(_ERROR_STATUS[exc.code], exc.code, None)
        except (InstallationIntegrityError, InstallationQuarantinedError, sqlite3.DatabaseError):
            return _error(_ERROR_STATUS["integrity_error"], "integrity_error", None)
        except (OSError, StorageAdministrationError):
            return _error(_ERROR_STATUS["unavailable"], "unavailable", None)
        return 200, result.model_dump_json().encode()

    def _handle_managed_intake(
        self, secret: str, body: bytes, operation_origin: str | None
    ) -> tuple[int, bytes]:
        if not operation_origin:
            return _error(403, "denied", None)
        if len(body) > _MAXIMUM_INTAKE_BYTES or len(operation_origin) > _MAXIMUM_OPERATION_ORIGIN_BYTES:
            return _error(400, "invalid_request", None)
        try:
            request = SidecarIntakeRequest.model_validate_json(body)
            proof = OperationOrigin.model_validate_json(operation_origin)
        except ValueError:
            return _error(400, "invalid_request", None)
        factory = self._managed_intake_factory
        assert factory is not None
        try:
            binding = factory(secret)
            if binding is None:
                return _error(403, "denied", None)
            entry = binding.spool.admit(
                HostEventDelivery(
                    transport_message_id=request.transport_message_id or f"sidecar:{request.command.operation_id}",
                    producer_binding=proof.coordinate.client_namespace,
                    command=request.command,
                ),
                operation_origin=proof,
                validate=lambda command, admitted: binding.commands.validate_intake(
                    command, operation_origin=admitted,
                ),
            )
        except (RuntimeCommandError, ConsumerDeliveryError) as exc:
            code = _harness_error_code(str(exc))
            return _error(_ERROR_STATUS[code], code, None)
        except (OSError, StorageAdministrationError):
            return _error(503, "unavailable", None)
        record = SpoolRecord(
            operation_id=entry.delivery.command.operation_id,
            producer_binding=entry.delivery.producer_binding,
            request_digest=entry.operation_origin.coordinate.request_digest,
            state=entry.state,
        )
        return 200, record.model_dump_json().encode()


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


def _error(status: int, code: SidecarErrorCode, detail: str | None) -> tuple[int, bytes]:
    payload = SidecarError(code=code, retryable=code in ("unavailable", "resource_exhausted"), detail=detail)
    return status, payload.model_dump_json().encode("utf-8")


def _harness_error_code(message: str) -> SidecarErrorCode:
    supplied_code = message.partition(":")[0]
    for code in _ERROR_STATUS:
        if supplied_code == code:
            return code
    return "invalid_request"


def _release_request(path: str, body: bytes) -> _ReleaseRequest:
    if path == "/v1/runtime/state":
        return SidecarRequest.model_validate_json(body)
    if path == "/v1/runtime/source/capture":
        return NativeSourceCaptureRequest.model_validate_json(body)
    if path == "/v1/runtime/source/recall":
        return NativeSourceRecallRequest.model_validate_json(body)
    if path == "/v1/operations/prepare":
        return _PREPARED_OPERATION.validate_json(body)
    if path == "/v1/consolidation/read":
        return ConsolidationReadRequest.model_validate_json(body)
    if path == "/v1/runtime/intake":
        return SidecarIntakeRequest.model_validate_json(body).command
    return WritebackDecisionRequest.model_validate_json(body)


def build_sidecar_handler(sidecar: RuntimeSidecar) -> type[BaseHTTPRequestHandler]:
    """HTTP handler bound to one sidecar instance."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            routes = {
                "/v1/runtime/state": sidecar.handle_state_request,
                "/v1/operations/prepare": sidecar.handle_prepare_request,
                "/v1/consolidation/read": sidecar.handle_consolidation_read_request,
                "/v1/runtime/intake": sidecar.handle_intake_request,
                "/v1/consolidation/decision": sidecar.handle_writeback_decision_request,
                "/v1/runtime/source/capture": partial(sidecar.handle_native_source_request, capture=True),
                "/v1/runtime/source/recall": partial(sidecar.handle_native_source_request, capture=False),
            }
            if self.path not in routes:
                self._respond(*_error(404, "not_found", None))
                return
            length = _safe_content_length(self.headers.get("Content-Length"), _MAXIMUM_INTAKE_BYTES)
            proofs = self.headers.get_all("Memorii-Operation-Origin", [])
            if length is None:
                self._respond(*_error(400, "invalid_request", "content length is invalid or oversized"))
                return
            body = self.rfile.read(length) if length else (b"{}" if self.path == "/v1/runtime/state" else b"")
            secret = self.headers.get("Authorization", "").removeprefix("Bearer ")
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "").split(":")[0] or None
            handle = routes[self.path]
            if self.path in ("/v1/runtime/intake", "/v1/consolidation/decision"):
                if len(proofs) > 1:
                    self._respond(*_error(400, "invalid_request", None))
                    return
                handle = partial(handle, operation_origin=proofs[0] if proofs else None)
            assemble = partial(handle, bearer_token=secret or None, origin=origin, body=body, host=host)
            if not sidecar.requires_socket_release:
                self._respond(*assemble())
                return
            if origin is not None or host not in (None, "127.0.0.1", "localhost", "::1"):
                self._respond(*_error(403, "denied", None))
                return
            if not secret:
                self._respond(*_error(401, "unauthenticated", None))
                return
            try:
                request = _release_request(self.path, body)
            except ValueError:
                status, payload = assemble()
                if status == 200:
                    self._respond(*_error(503, "unavailable", None))
                else:
                    self._respond(status, payload)
                return
            status, payload, permit = sidecar.prepare_socket_response(
                request, secret=secret, assemble=assemble,
                mutates=self.path in ("/v1/runtime/source/capture", "/v1/consolidation/decision"),
            )
            if permit is not None:
                self._respond_protected(status, payload, permit, secret)
            elif status == 200:
                self._respond(*_error(503, "unavailable", None))
            else:
                self._respond(status, payload)

        def log_message(self, format: str, *args: object) -> None:
            return  # content-free logging only

        def _respond(self, status: int, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _respond_protected(self, status: int, payload: bytes, permit: _SocketReleasePermit, secret: str) -> None:
            if sha256(payload).digest() != permit.payload_digest:
                self._respond(*_error(500, "integrity_error", None))
                return
            self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            frame = memoryview(b"".join(self._headers_buffer) + b"\r\n" + payload)
            self._headers_buffer = []
            timeout = self.connection.gettimeout()
            self.connection.setblocking(False)
            offset = 0
            try:
                while offset < len(frame) and monotonic() < permit.deadline:
                    try:
                        with sidecar.socket_release(permit, secret):
                            try:
                                written = self.connection.send(frame[offset:offset + _SOCKET_RELEASE_CHUNK_BYTES])
                            except BlockingIOError:
                                written = None
                    except BlockingIOError:
                        sleep(min(0.005, max(0.0, permit.deadline - monotonic())))
                        continue
                    if written is None:
                        select([], [self.connection], [], max(0.0, permit.deadline - monotonic()))
                    elif written == 0:
                        return
                    else:
                        offset += written
            except (CredentialError, GrantRegistryError, HostCommandAuthorityError, HostEnrollmentError):
                if offset == 0:
                    self._deny_unwritten_response(permit.deadline)
            except (OSError, StorageAdministrationError, ValueError, sqlite3.DatabaseError):
                # A partial response cannot be replaced by an error frame.
                return
            finally:
                self.connection.settimeout(timeout)

        def _deny_unwritten_response(self, deadline: float) -> None:
            remaining = deadline - monotonic()
            if remaining > 0:
                self.connection.settimeout(remaining)
                try:
                    self._respond(*_error(403, "denied", None))
                except OSError:
                    return

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
