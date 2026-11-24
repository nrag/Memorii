"""Scoped, verified reads of sealed runtime consolidation results."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal, TypedDict

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from memorii.core.consolidation.runtime_outputs import (
    ArchivePackage,
    ConsolidationOmission,
    ConsolidationOutput,
    ConsolidationResult,
    ConsolidationSourceReference,
    EpisodicSummary,
    UnresolvedFollowUpSummary,
)
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.grant_registry import GrantEpochRegistry, GrantRegistryError
from memorii.core.harness_state.paging import (
    DEFAULT_CURSOR_LIFETIME,
    HarnessCursorError,
    cursor_codec_for,
)
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    ManagedHostCommandAuthority,
    ResolvedHostCommandAuthority,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.key_owner import LocalSigningKeyOwner
from memorii.core.persistence.runtime_api import managed_receipt_namespace
from memorii.core.persistence.runtime_checkpoint import RuntimeCheckpointError, TaskLifecycleArchive
from memorii.core.persistence.runtime_repository import RuntimeStateError, RuntimeStateRepository
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryRecordVisibility, TemporalValidityStatus

ConsolidationReadErrorCode = Literal[
    "unauthenticated", "denied", "not_found", "stale_cursor", "unavailable",
    "integrity_error", "unsupported_configuration",
]


class ConsolidationReadError(RuntimeError):
    """A public reason without identifiers or stored content."""

    code: ConsolidationReadErrorCode

    def __init__(self, code: ConsolidationReadErrorCode) -> None:
        super().__init__(code)
        self.code = code


def _coordinate(value: str) -> str:
    if not value.strip() or "\x00" in value:
        raise ValueError("coordinate must be nonblank and contain no NUL")
    return value


Coordinate = Annotated[str, Field(min_length=1, max_length=512), AfterValidator(_coordinate)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _ClosedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConsolidationReadBinding(_ClosedRecord):
    """Optional echo of the installed host's resolved coordinates."""

    installation_id: Coordinate
    client_namespace: Coordinate
    task_id: Coordinate


class ConsolidationReadRequest(_ClosedRecord):
    protocol_version: Literal[1] = 1
    task_id: Coordinate
    origin_operation_id: Coordinate
    host_binding: ConsolidationReadBinding | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=16_384)
    page_size: int = Field(default=10, ge=1, le=32, strict=True)


class ConsolidationOfferStatus(_ClosedRecord):
    output_id: Digest
    offer_version: int = Field(ge=1)
    payload_digest: Digest
    decision_status: Literal["offered", "accepted", "declined"]
    delivery_status: Literal["pending", "delivering", "delivered", "rejected", "needs_reconciliation"] | None = None


class ConsolidationReadEntry(_ClosedRecord):
    output: ConsolidationOutput
    offer: ConsolidationOfferStatus | None = None


class ConsolidationReadPage(_ClosedRecord):
    protocol_version: Literal[1] = 1
    result_id: Digest
    origin_revision: int = Field(ge=0)
    outputs: tuple[ConsolidationReadEntry, ...] = Field(max_length=32)
    omissions: tuple[ConsolidationOmission, ...] = Field(max_length=32)
    continuation_cursor: str | None = None


# The decision owner can attach a typed reader once its catalog is live. A
# recorded decision never silently collapses back to the initial offer state.
DecisionReader = Callable[[sqlite3.Connection, ConsolidationOutput], ConsolidationOfferStatus]


class _CursorContext(TypedDict):
    task_id: str
    principal: str
    grant_id: str
    grant_epoch: int
    runtime_revision: int
    view: str


class ConsolidationReadService:
    """Read through the managed authority and one acquired SQL snapshot."""

    def __init__(
        self,
        administration: StorageAdministrationService,
        *,
        credentials: SidecarCredentialStore,
        secret: str,
        grant_factory: Callable[[str], RuntimeReadGrant],
        decision_reader: DecisionReader | None = None,
    ) -> None:
        self._administration = administration
        self._credentials = credentials
        self._secret = secret
        self._grant_factory = grant_factory
        self._decision_reader = decision_reader

    def read(self, request: ConsolidationReadRequest) -> ConsolidationReadPage:
        with self._administration.verified_operation_context() as (state, finalized):
            if state.mode == "bypass":
                raise ConsolidationReadError("unavailable")
            moment = datetime.now(UTC)
            grant, authority = self._authorize(request, state, finalized, now=moment)
            revoked = RefreshingRevokedIdentityView(self._administration.installation_root / "control")
            if revoked.is_revoked_task(request.task_id):
                raise ConsolidationReadError("denied")
            partition = self._administration.partition()
            repository = RuntimeStateRepository(partition)
            with partition.transaction(write=False) as connection:
                task = repository.get_task_in(connection, request.task_id)
                if task is None or task.principal != authority.principal:
                    raise ConsolidationReadError("denied")
                result = self._load_result(connection, repository, request, finalized, authority)
                visible = self._visible_outputs(
                    connection, repository, result.outputs, revoked, task_id=task.task_id,
                    principal=authority.principal, moment=moment,
                )
                if self._authorize(request, state, finalized, now=datetime.now(UTC)) != (grant, authority):
                    raise ConsolidationReadError("denied")

            # The existing cursor codec signs its complete context. Hash the
            # result query and current serving view before passing it through
            # the codec's single view field. Changing any of these restarts paging.
            view = sha256(encode_typed_value((
                "consolidation", finalized.installation_id, finalized.repository_id,
                finalized.data_generation_id, finalized.payload_digest(), state.control_revision,
                state.eligibility_epoch, state.pending_epoch_increments,
                authority.grant_id, authority.grant_epoch, result.result_id, request.page_size,
                tuple(entry.output.output_id for entry in visible),
            ))).hexdigest()
            cursor_context: _CursorContext = {
                "task_id": request.task_id, "principal": grant.principal,
                "grant_id": grant.grant_id, "grant_epoch": grant.epoch,
                "runtime_revision": finalized.vector.partition_ordinal, "view": view,
            }
            offset = 0
            if request.cursor is not None:
                try:
                    offset = cursor_codec_for(partition).decode(request.cursor, now=moment, **cursor_context)
                except HarnessCursorError as exc:
                    raise ConsolidationReadError("stale_cursor") from exc
            next_offset = offset + request.page_size
            continuation = (
                cursor_codec_for(partition).encode(
                    offset=next_offset, expires_at=moment + DEFAULT_CURSOR_LIFETIME, **cursor_context,
                )
                if next_offset < len(visible)
                else None
            )
            # Reauthorize after loading the cursor secret and before exposing
            # bytes. The publication barrier also remains held through release.
            if self._authorize(request, state, finalized, now=datetime.now(UTC)) != (grant, authority):
                raise ConsolidationReadError("denied")
            return ConsolidationReadPage(
                result_id=result.result_id, origin_revision=result.origin_revision,
                outputs=visible[offset:next_offset], omissions=result.omissions,
                continuation_cursor=continuation,
            )

    def _authorize(
        self,
        request: ConsolidationReadRequest,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
        *,
        now: datetime,
    ) -> tuple[RuntimeReadGrant, ResolvedHostCommandAuthority]:
        credentials = self._credentials
        credentials.verify_permissions()
        credential = credentials.credential_for(self._secret)
        if credential is None:
            raise ConsolidationReadError("unauthenticated")
        grant = self._grant_factory(credential.principal)
        if (
            grant.principal != credential.principal
            or request.task_id not in grant.allowed_task_ids
            or grant.expires_at.tzinfo is None
            or not grant.authorizes(request.task_id, now=now)
            or "\x00" in grant.principal
            or "\x00" in grant.grant_id
        ):
            raise ConsolidationReadError("denied")
        try:
            read_grants = GrantEpochRegistry(self._administration.installation_root / "control" / "grants")
            read_grants.verify_permissions()
            read_grants.require_current(grant.grant_id, grant.epoch)
            authority = ManagedHostCommandAuthority(
                self._administration,
            ).resolve_consolidation_reader_in_verified_context(
                credential=credential, task_id=request.task_id,
                origin_operation_id=request.origin_operation_id, state=state, finalized=finalized, now=now,
            )
        except GrantRegistryError as exc:
            raise ConsolidationReadError("denied") from exc
        except HostCommandAuthorityError as exc:
            if str(exc).startswith("unsupported_configuration:"):
                raise ConsolidationReadError("unsupported_configuration") from exc
            raise ConsolidationReadError("denied") from exc
        if request.host_binding is not None and request.host_binding != ConsolidationReadBinding(
            installation_id=finalized.installation_id,
            client_namespace=authority.client_namespace, task_id=request.task_id,
        ):
            raise ConsolidationReadError("denied")
        return grant, authority

    @staticmethod
    def _load_result(
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        request: ConsolidationReadRequest,
        finalized: RuntimePublicationState,
        authority: ResolvedHostCommandAuthority,
    ) -> ConsolidationResult:
        lookup_namespace = managed_receipt_namespace(
            installation_id=finalized.installation_id, repository_id=finalized.repository_id,
            generation_id=finalized.data_generation_id, principal=authority.principal,
            client_namespace=authority.client_namespace,
        )
        try:
            receipt = repository.get_command_receipt_in(connection, lookup_namespace, request.origin_operation_id)
        except ValidationError as exc:
            raise ConsolidationReadError("integrity_error") from exc
        if receipt is None or receipt.consolidation_result_id is None:
            raise ConsolidationReadError("not_found")
        try:
            result = repository.get_consolidation_result_in(connection, receipt.consolidation_result_id)
        except (ValidationError, RuntimeStateError) as exc:
            raise ConsolidationReadError("integrity_error") from exc
        if result is None or receipt.operation_origin is None:
            raise ConsolidationReadError("integrity_error")
        if result.origin.task_id != request.task_id:
            raise ConsolidationReadError("denied")
        origin = receipt.operation_origin
        if (
            result.origin.installation_id != origin.installation_id
            or result.origin.partition_id != origin.repository_id
            or result.origin.operation_generation != origin.generation_id
            or result.origin.client_namespace != origin.client_namespace
            or result.origin.operation_id != origin.operation_id
            or result.origin.request_digest != origin.request_digest
            or origin.installation_id != finalized.installation_id
            or origin.repository_id != finalized.repository_id
            or origin.generation_id != finalized.data_generation_id
            or origin.principal != authority.principal
            or origin.client_namespace != authority.client_namespace
            or origin.operation_id != request.origin_operation_id
            or receipt.current_revision != result.origin_revision
            or sha256(result.canonical_bytes()).hexdigest() != receipt.result_digest
        ):
            raise ConsolidationReadError("integrity_error")
        return result

    def _visible_outputs(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        outputs: tuple[ConsolidationOutput, ...],
        revoked: RefreshingRevokedIdentityView,
        *,
        task_id: str,
        principal: str,
        moment: datetime,
    ) -> tuple[ConsolidationReadEntry, ...]:
        visible: list[ConsolidationReadEntry] = []
        partition = repository.partition
        for output in outputs:
            payload = output.payload
            if isinstance(payload, ArchivePackage):
                row = partition.read_runtime_row(
                    connection, table="runtime_checkpoints",
                    match=(("checkpoint_id", payload.reference.checkpoint_id),),
                )
                if row is None:
                    raise ConsolidationReadError("integrity_error")
                try:
                    archive = TaskLifecycleArchive.model_validate_json(row["record_json"])
                    if archive.reference() != payload.reference:
                        raise ConsolidationReadError("integrity_error")
                    key_owner = LocalSigningKeyOwner(self._administration.installation_root / "control" / "keys")
                    archive.verify_signature(key_owner.verify)
                except (ValidationError, RuntimeCheckpointError) as exc:
                    raise ConsolidationReadError("integrity_error") from exc
                if all(self._source_is_current(
                    connection, repository, ref, revoked, task_id, principal, moment, allow_protected=True,
                ) for ref in archive.checkpoint.source_closure):
                    visible.append(ConsolidationReadEntry(output=output))
                continue
            refs = (
                tuple(ref for item in payload.items for ref in item.source_refs)
                if isinstance(payload, UnresolvedFollowUpSummary)
                else payload.source_refs
            )
            if not all(
                self._source_is_current(
                    connection, repository, ref, revoked, task_id, principal, moment,
                    allow_protected=isinstance(payload, EpisodicSummary),
                )
                for ref in refs
            ):
                continue
            if isinstance(payload, UnresolvedFollowUpSummary):
                visible.append(ConsolidationReadEntry(output=output))
            elif refs:
                visible.append(ConsolidationReadEntry(
                    output=output, offer=self._offer_status(connection, repository, output),
                ))
        return tuple(visible)

    def _offer_status(
        self, connection: sqlite3.Connection, repository: RuntimeStateRepository, output: ConsolidationOutput,
    ) -> ConsolidationOfferStatus:
        if self._decision_reader is not None:
            status = self._decision_reader(connection, output)
            if status.output_id != output.output_id or status.payload_digest != output.payload_digest:
                raise ConsolidationReadError("integrity_error")
            return status
        from memorii.core.harness_state.writeback_decision import (
            WritebackDecisionError,
            load_recorded_decision,
            read_candidate_delivery,
        )

        try:
            decision = load_recorded_decision(connection, repository, output.output_id)
            if decision is not None:
                if (
                    decision.request.expected_payload_digest != output.payload_digest
                    or not self._administration.verify_operation_origin(decision.origin)
                ):
                    raise ConsolidationReadError("integrity_error")
                receipt = decision.receipt(read_candidate_delivery(connection, repository, decision))
                return ConsolidationOfferStatus(
                    output_id=output.output_id, payload_digest=output.payload_digest,
                    offer_version=receipt.offer_version, decision_status=receipt.outcome,
                    delivery_status=receipt.delivery_status,
                )
        except (WritebackDecisionError, ValueError) as exc:
            raise ConsolidationReadError("integrity_error") from exc
        return ConsolidationOfferStatus(
            output_id=output.output_id, offer_version=1, payload_digest=output.payload_digest,
            decision_status="offered",
        )

    @staticmethod
    def _source_is_current(
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        ref: ConsolidationSourceReference,
        revoked: RefreshingRevokedIdentityView,
        task_id: str,
        principal: str,
        moment: datetime,
        *,
        allow_protected: bool = False,
    ) -> bool:
        if revoked.is_revoked_source(ref.source_id) or revoked.is_revoked_record(ref.source_id):
            return False
        row = repository.partition.read_current_record_row(connection, ref.source_id)
        if row is None:
            return False
        try:
            record = CanonicalMemoryRecord.model_validate_json(row["record_json"])
        except ValidationError as exc:
            raise ConsolidationReadError("integrity_error") from exc
        if allow_protected and record.visibility == MemoryRecordVisibility.INTERNAL_CONTROL:
            from memorii.core.provider.runtime_source_release import get_current_source_release

            return get_current_source_release(
                connection, repository, task_id=task_id, principal=principal, source_ref=ref,
                now=moment, revoked=revoked,
            ) is not None
        return (
            record.memory_id == ref.source_id
            and record.user_id == principal
            and record.task_id == task_id
            and record.status == CommitStatus.COMMITTED
            and record.visibility == MemoryRecordVisibility.RUNTIME_CONTEXT
            and record.validity_status not in {TemporalValidityStatus.EXPIRED, TemporalValidityStatus.INVALIDATED}
            and (
                record.valid_from is None or (record.valid_from.tzinfo is not None and record.valid_from <= moment)
            )
            and (
                record.valid_to is None or (record.valid_to.tzinfo is not None and moment < record.valid_to)
            )
            and revoked.keeps_record(record)
            and record_digest(record) == ref.source_digest
        )


def authenticated_consolidation_reader(
    administration: StorageAdministrationService,
    credentials: SidecarCredentialStore,
    secret: str,
    grant_factory: Callable[[str], RuntimeReadGrant],
) -> ConsolidationReadService:
    """Compose a reader for this request's authenticated host credential."""
    return ConsolidationReadService(
        administration, credentials=credentials, secret=secret, grant_factory=grant_factory,
    )
