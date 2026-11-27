"""Operator-enrolled local transcript capture and bounded recall."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.harness_state.consumer import HostEventDelivery, ManagedRuntimeSpool
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry, GrantRegistryError
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    HostCommandGrant,
    HostCommandGrantRequest,
    ManagedHostCommandAuthority,
    NativeSourceScope,
    ResolvedHostCommandAuthority,
)
from memorii.core.memory_evolution.admission import source_admission_source_digest
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.runtime_api import RuntimeCommandError, managed_receipt_namespace
from memorii.core.persistence.runtime_contracts import (
    OperationOriginCoordinate,
    RuntimeCommandReceipt,
    RuntimeCommandRequest,
    RuntimeSourceAdmissionReceipt,
    canonical_runtime_digest,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.provider.models import ProviderEvent, ProviderOperation
from memorii.core.provider.runtime_source_authority import (
    RuntimeSourceAuthorityError,
    RuntimeSourceTaskBinding,
    resolve_runtime_source,
)
from memorii.core.storage_administration.operator import OwnerCapability, require_owner_capability
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import (
    InstallationControlState,
    RuntimePublicationState,
    StorageAdministrationService,
)

_OBSERVATION_PREFIX = "native-source:"
_OPERATION_ID = re.compile(r"native-source:[0-9a-f]{64}\Z")
_RECALL_LIMIT = 4


class NativeSourceRequest(BaseModel):
    protocol_version: Literal[1] = 1
    task_id: str = Field(min_length=1, max_length=512)
    source: NativeSourceScope

    model_config = ConfigDict(extra="forbid", frozen=True)


class NativeSourceCaptureRequest(NativeSourceRequest):
    delivery_id: str = Field(min_length=1, max_length=512, pattern=r"^[^\x00]+$")
    text: str = Field(min_length=1, max_length=16384)


class NativeSourceRecallRequest(NativeSourceRequest):
    exclude_delivery_id: str | None = Field(default=None, min_length=1, max_length=512, pattern=r"^[^\x00]+$")


class RecalledNativeMessage(BaseModel):
    source_id: str
    text: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class NativeSourceRecall(BaseModel):
    messages: tuple[RecalledNativeMessage, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


def _denied() -> RuntimeCommandError:
    return RuntimeCommandError("denied: native source enrollment is unavailable")


def _ingress(grant: ResolvedHostCommandAuthority, task_id: str) -> AuthenticatedIngressContext:
    source = grant.native_source
    if source is None:
        raise _denied()
    enrollment = canonical_runtime_digest((
        grant.installation_id, grant.data_generation_id, grant.grant_id,
        grant.grant_epoch, task_id, source.model_dump(mode="json"),
    ))
    binding = DeliveryPrincipalBinding.create(
        principal_subject_id=grant.principal, tenant_partition_id=grant.installation_id,
        provider_identity=f"memorii.native-source:{enrollment}",
    )
    scopes = RequiredOutcomeScopeSet.create(
        tenant_partition_id=grant.installation_id,
        scopes={f"user:{grant.principal}", f"session:{enrollment}"},
    )
    return AuthenticatedIngressContext(
        delivery_principal_binding=binding, required_outcome_scopes=scopes, current_authorized_scopes=scopes,
        semantic_egress_governance=AuthenticatedSemanticEgressGovernance(
            classification="private", provider="local", model="none", region="local",
            retention_mode="store_false", training_use=False,
        ),
        semantic_source_authority=AuthenticatedSemanticSourceAuthority(
            authority_class="official", authenticated_provenance_class="authenticated_user",
            policy_revision="memorii-native-source-v1", provenance_digest=enrollment,
        ),
    )


def native_operation_id(ingress: AuthenticatedIngressContext, delivery_id: str) -> str:
    return _OBSERVATION_PREFIX + canonical_runtime_digest((
        ingress.delivery_principal_binding.binding_digest, delivery_id,
    ))


def resolve_native_source_binding(
    administration: StorageAdministrationService,
    request: RuntimeCommandRequest,
    origin: OperationOriginCoordinate,
    finalized: RuntimePublicationState,
) -> tuple[AuthenticatedIngressContext, OperationFenceBinding, RuntimeSourceTaskBinding]:
    """Resolve one retained delivery against the current owner enrollment."""
    if not _OPERATION_ID.fullmatch(request.operation_id) or request.task_id is None or request.source_digest is None:
        raise _denied()
    state, _ = administration.current_publication_in_fence()
    try:
        grant = ManagedHostCommandAuthority(administration).resolve_persisted_namespace_in_verified_context(
            principal=origin.principal, client_namespace=origin.client_namespace, request=request,
            state=state, finalized=finalized,
        )
    except HostCommandAuthorityError as exc:
        raise _denied() from exc
    ingress = _ingress(grant, request.task_id)
    assert grant.native_source is not None
    identity = DeliveryIdentity.create(ingress.delivery_principal_binding, request.operation_id)
    source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
    fence = OperationFenceBinding.create(
        operation_id=request.operation_id, source_id=source_id,
        source_digest=request.source_digest, delivery_identity=identity,
    )
    binding = RuntimeSourceTaskBinding(
        installation_id=finalized.installation_id, repository_id=finalized.repository_id,
        generation_id=finalized.data_generation_id, runtime_task_id=request.task_id,
        runtime_principal=origin.principal, client_namespace=origin.client_namespace,
        provider_task_id=request.task_id, provider_session_id=grant.native_source.session_id,
        provider_principal_binding_digest=identity.delivery_principal_binding_digest,
        delivery_key_digest=identity.delivery_key_digest,
    )
    return ingress, fence, binding


def resolve_enrolled_runtime_source(
    administration: StorageAdministrationService,
    connection: sqlite3.Connection,
    repository: RuntimeStateRepository,
    request: RuntimeCommandRequest,
    origin: OperationOriginCoordinate,
    finalized: RuntimePublicationState,
) -> RuntimeSourceAdmissionReceipt:
    ingress, fence, binding = resolve_native_source_binding(administration, request, origin, finalized)
    try:
        evidence = resolve_runtime_source(
            connection, repository.partition, finalized=finalized, origin=origin, runtime_task_id=binding.runtime_task_id,
            source_digest=fence.source_digest, operation_fence=fence, resolve_ingress=lambda: ingress, binding=binding,
            revoked=RefreshingRevokedIdentityView(administration.installation_root / "control"), now=datetime.now(UTC),
        )
    except RuntimeSourceAuthorityError as exc:
        raise _denied() from exc
    return RuntimeSourceAdmissionReceipt(
        task_id=binding.runtime_task_id, source_id=evidence.source_ref.source_id,
        source_record_digest=evidence.source_ref.source_digest, provider_source_digest=evidence.source_digest,
        admission_index_digest=evidence.admission_index_digest, delivery_key_digest=evidence.delivery_key_digest,
        source_write_revision=evidence.source_write_revision, source_type=evidence.source_type,
        modalities=evidence.modalities, retained_at=evidence.retained_at,
    )


class NativeSourceService:
    def __init__(
        self, administration: StorageAdministrationService, credentials: SidecarCredentialStore,
        spool: ManagedRuntimeSpool, read_grant: Callable[[str], RuntimeReadGrant],
    ) -> None:
        self._administration = administration
        self._credentials = credentials
        self._grants = ManagedHostCommandAuthority(administration)
        self._spool = spool
        self._read_grant = read_grant
        self._control = administration.installation_root / "control"
        self._grant_epochs = GrantEpochRegistry(self._control / "grants")
        self._revoked = RefreshingRevokedIdentityView(self._control)

    def _authorize(
        self, secret: str, request: NativeSourceRequest,
        state: InstallationControlState, finalized: RuntimePublicationState,
    ) -> ResolvedHostCommandAuthority:
        self._credentials.verify_permissions()
        credential = self._credentials.credential_for(secret)
        if credential is None:
            raise RuntimeCommandError("unauthenticated: host credential is unavailable")
        probe = RuntimeCommandRequest(
            kind="record_observation", operation_id="native-source-authorization", task_id=request.task_id,
            expected_revision=0, source_digest="0" * 64,
        )
        try:
            grant = self._grants.resolve_for_credential_in_verified_context(
                credential=credential, request=probe, state=state, finalized=finalized,
            )
        except HostCommandAuthorityError as exc:
            raise _denied() from exc
        if grant.native_source != request.source or self._revoked.is_revoked_task(request.task_id):
            raise _denied()
        return grant

    def capture(self, secret: str, request: NativeSourceCaptureRequest) -> RuntimeCommandReceipt:
        from functools import partial

        from memorii.core.harness_state.managed_ingress import authenticated_host_commands, spooled_host_commands
        from memorii.core.memory_evolution.atomic_store import PreplanningStoreError
        from memorii.core.provider.native_source_admission import NativeSourceDeliveryConflict, retain_native_source

        if not request.text.strip():
            raise RuntimeCommandError("invalid_request: native message is empty")
        administration = self._administration
        with administration.verified_operation_context() as (state, finalized):
            authorized = self._authorize(secret, request, state, finalized)
        # Two source requests for one task must obtain their CAS versions in
        # order. The publication fence separately serializes other writers.
        lock = self._control / "runtime-write-grants" / f"capture-{canonical_runtime_digest(request.task_id)}.lock"
        with locked_file(lock, exclusive=True):
            with administration.verified_operation_context() as (state, finalized):
                grant = self._authorize(secret, request, state, finalized)
                if grant != authorized:
                    raise _denied()
                ingress = _ingress(grant, request.task_id)
                operation_id = native_operation_id(ingress, request.delivery_id)
            for pending in self._spool.pending():
                origin = pending.operation_origin
                command = pending.delivery.command
                if (
                    command.kind == "resume_task" and command.task_id == request.task_id
                    and origin.coordinate.principal == grant.principal
                    and origin.coordinate.client_namespace == grant.client_namespace
                    and origin.coordinate.generation_id == grant.data_generation_id
                ):
                    spooled_host_commands(administration, origin).dispatch(command, operation_origin=origin)
                    self._spool.mark_committed(pending)
            with administration.verified_operation_context() as (state, finalized):
                if self._authorize(secret, request, state, finalized) != grant:
                    raise _denied()
                self._require_active_task(request.task_id, grant, state)
            event = ProviderEvent(
                event_id=operation_id, operation=ProviderOperation.CHAT_USER_TURN, role="user", content=request.text,
                session_id=request.source.session_id, task_id=request.task_id, user_id=grant.principal,
                timestamp=datetime.now(UTC),
            )

            def current_task_version() -> int:
                state, current = administration.current_publication_in_fence()
                resolved = self._authorize(secret, request, state, current)
                if resolved != grant:
                    raise _denied()
                return self._require_active_task(request.task_id, grant, state)

            def check_current() -> None:
                current_task_version()

            try:
                record = retain_native_source(administration, event=event, ingress=ingress, check_current=check_current)
            except NativeSourceDeliveryConflict as exc:
                raise RuntimeCommandError("conflict: native delivery changed") from exc
            except PreplanningStoreError as exc:
                raise RuntimeCommandError("unavailable: governed writer is unavailable") from exc
            except ValueError as exc:
                raise _denied() from exc
            digest = source_admission_source_digest(record)
            with administration.verified_operation_context() as (_, current):
                task_version = current_task_version()
                command = RuntimeCommandRequest(
                    kind="record_observation", task_id=request.task_id, operation_id=operation_id,
                    source_digest=digest, expected_revision=task_version,
                )
                coordinate = OperationOriginCoordinate(
                    installation_id=current.installation_id, repository_id=current.repository_id,
                    generation_id=current.data_generation_id, principal=grant.principal,
                    client_namespace=grant.client_namespace, operation_id=operation_id,
                    request_digest=command.managed_intent_digest(),
                )
            commands = authenticated_host_commands(
                administration, self._credentials, secret,
                observation_source=partial(resolve_enrolled_runtime_source, administration),
                enrolled_source_append=True,
            )
            entry = self._spool.find(coordinate)
            if entry is None:
                proof = commands.prepare(command)
                entry = self._spool.admit(
                    HostEventDelivery(
                        transport_message_id=operation_id, producer_binding=grant.client_namespace, command=command,
                    ),
                    operation_origin=proof,
                    validate=lambda submitted, origin: commands.validate_intake(submitted, operation_origin=origin),
                )
            if entry.delivery.command.source_digest != digest:
                raise RuntimeCommandError("conflict: native delivery changed")
            receipt = commands.dispatch(entry.delivery.command, operation_origin=entry.operation_origin)
            self._spool.mark_committed(entry)
            return receipt

    def _require_active_task(
        self, task_id: str, grant: ResolvedHostCommandAuthority, state: InstallationControlState,
    ) -> int:
        task = RuntimeStateRepository(self._administration.partition()).get_task(task_id)
        if state.mode != "active" or task is None or task.principal != grant.principal or task.lifecycle != "active":
            raise _denied()
        return task.version

    def recall(self, secret: str, request: NativeSourceRecallRequest) -> NativeSourceRecall:
        administration = self._administration
        with administration.verified_operation_context() as (state, finalized):
            grant = self._authorize(secret, request, state, finalized)
            exclude = (
                None if request.exclude_delivery_id is None
                else native_operation_id(_ingress(grant, request.task_id), request.exclude_delivery_id)
            )
            read = self._read_grant(grant.principal)
            try:
                self._grant_epochs.require_current(read.grant_id, read.epoch)
            except GrantRegistryError as exc:
                raise _denied() from exc
            if state.mode == "bypass" or read.principal != grant.principal or not read.authorizes(request.task_id):
                raise _denied()
            repository = RuntimeStateRepository(administration.partition())
            namespace = managed_receipt_namespace(
                installation_id=finalized.installation_id, repository_id=finalized.repository_id,
                generation_id=finalized.data_generation_id, principal=grant.principal,
                client_namespace=grant.client_namespace,
            )
            with repository.partition.transaction(write=False) as connection:
                task = repository.get_task_in(connection, request.task_id)
                if task is None or task.principal != grant.principal:
                    raise _denied()
                rows = connection.execute(
                    "SELECT record_json FROM runtime_command_receipts"
                    " WHERE client_namespace = ? AND operation_id >= ? AND operation_id < ?"
                    " AND json_extract(record_json, '$.source_admission.task_id') = ?"
                    " ORDER BY json_extract(record_json, '$.source_admission.source_write_revision') DESC",
                    (namespace, _OBSERVATION_PREFIX, "native-source;", request.task_id),
                )
                messages: list[RecalledNativeMessage] = []
                for row in rows:
                    receipt = RuntimeCommandReceipt.model_validate_json(row["record_json"])
                    origin, admitted = receipt.operation_origin, receipt.source_admission
                    if origin is None or admitted is None or receipt.status != "committed":
                        raise RuntimeCommandError("integrity_error: invalid native source receipt")
                    if origin.operation_id == exclude:
                        continue
                    observation = RuntimeCommandRequest(
                        kind="record_observation", task_id=request.task_id, operation_id=origin.operation_id,
                        source_digest=admitted.provider_source_digest, expected_revision=0,
                    )
                    try:
                        current = resolve_enrolled_runtime_source(
                            administration, connection, repository, observation, origin, finalized,
                        )
                    except RuntimeCommandError as exc:
                        if str(exc).partition(":")[0] != "denied":
                            raise
                        continue
                    if current != admitted:
                        raise RuntimeCommandError("integrity_error: native source receipt changed")
                    raw = repository.partition.read_current_record_row(connection, admitted.source_id)
                    if raw is None:
                        raise RuntimeCommandError("integrity_error: native source is missing")
                    record = CanonicalMemoryRecord.model_validate_json(raw["record_json"])
                    messages.append(RecalledNativeMessage(source_id=record.memory_id, text=record.text))
                    if len(messages) == _RECALL_LIMIT:
                        break
            self._authorize(secret, request, state, finalized)
            try:
                with self._grant_epochs.current_read(read.grant_id, read.epoch):
                    current_read = self._read_grant(grant.principal)
                    if (
                        current_read.grant_id != read.grant_id or current_read.epoch != read.epoch
                        or current_read.principal != grant.principal or not current_read.authorizes(request.task_id)
                    ):
                        raise _denied()
                    return NativeSourceRecall(messages=tuple(reversed(messages)))
            except GrantRegistryError as exc:
                raise _denied() from exc


def enroll_native_source(
    administration: StorageAdministrationService, request: HostCommandGrantRequest, *, capability: OwnerCapability,
) -> HostCommandGrant:
    """Provision the existing provider writer as owner and issue a finite source enrollment."""
    from memorii.core.memory_evolution.writer_admission import (
        SemanticWriterAdmissionStore,
        bounded_preplanning_ownership_manifest,
        writer_admission_memory_id,
    )
    from memorii.core.memory_plane.service import MemoryPlaneService
    from memorii.core.persistence.factory import PublishedMemoryPlaneStore

    require_owner_capability(administration, capability)
    if request.native_source is None:
        raise ValueError("native source enrollment is required")
    plane = MemoryPlaneService(
        record_store=PublishedMemoryPlaneStore(administration, administration.memory_plane_store()),
    )
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    if plane.get_record(writer_admission_memory_id()) is None:
        writers.create_initial_evidence_only(
            admission_id="memorii-provider-semantic-writer-v1",
            writer_implementation_fingerprint="memorii-provider-semantic-evidence-only-v1",
            graph_schema_fingerprint="memorii-semantic-graph-preactivation-v1",
        )
    else:
        writers.current()
    return ManagedHostCommandAuthority(administration).issue(request, capability=capability)
