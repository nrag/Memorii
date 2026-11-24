"""Provider-owned durable release of exact runtime source references."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.consolidation.runtime_outputs import MAX_CONSOLIDATION_SOURCE_REFERENCES, ConsolidationSourceReference
from memorii.core.memory_evolution.admission import _index_digest, _index_id, source_admission_source_digest
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext, OperationFenceBinding
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.runtime_api import operation_origin_namespace, operation_origin_proof_digest
from memorii.core.persistence.runtime_contracts import (
    OperationOrigin,
    OperationOriginCoordinate,
    RuntimeSourceAdmissionReceipt,
    canonical_runtime_digest,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.provider.runtime_source_authority import (
    RuntimeSourceAuthorityError,
    RuntimeSourceTaskBinding,
    resolve_runtime_source,
)
from memorii.core.storage_administration.operator import OwnerCapability, require_owner_capability
from memorii.core.storage_administration.revoked_identity_view import (
    RefreshingRevokedIdentityView,
    RevokedIdentityServingGate,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility, TemporalValidityStatus

_GrantID = Annotated[str, Field(pattern=r"^runtime-source-release:[0-9a-f]{64}:[0-9a-f]{64}$")]
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_MAX_ACTIVE_PER_TASK = MAX_CONSOLIDATION_SOURCE_REFERENCES


class RuntimeSourceReleaseGrant(BaseModel):
    """Exact source, observation, task, and provider authority in one signed row."""

    grant_id: _GrantID
    task_id: str = Field(min_length=1, max_length=512)
    task_project: str | None
    binding: RuntimeSourceTaskBinding
    observation_origin: OperationOriginCoordinate
    observation_proof_digest: _Digest
    source: RuntimeSourceAdmissionReceipt
    source_index_record_digest: _Digest
    issued_at: AwareDatetime
    status: Literal["active", "revoked"] = "active"
    version: Literal[1, 2] = 1
    revoked_at: AwareDatetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def verify_scope(self) -> Self:
        binding = self.binding
        origin = self.observation_origin
        if (
            binding.installation_id != origin.installation_id
            or binding.repository_id != origin.repository_id
            or binding.generation_id != origin.generation_id
            or binding.runtime_principal != origin.principal
            or binding.client_namespace != origin.client_namespace
            or binding.runtime_task_id != self.task_id or self.source.task_id != self.task_id
            or self.source.delivery_key_digest != binding.delivery_key_digest
            or self.grant_id != _grant_id(origin.generation_id, self.task_id, origin.principal, self.source.source_id)
        ):
            raise ValueError("source release grant scope does not match its admission")
        if (self.status == "active" and (self.version != 1 or self.revoked_at is not None)) or (
            self.status == "revoked" and (self.version != 2 or self.revoked_at is None or self.revoked_at < self.issued_at)
        ):
            raise ValueError("source release grant revocation is invalid")
        return self

    def source_ref(self) -> ConsolidationSourceReference:
        return ConsolidationSourceReference(source_id=self.source.source_id, source_digest=self.source.source_record_digest)


def _task_prefix(generation_id: str, task_id: str, principal: str) -> str:
    return "runtime-source-release:" + canonical_runtime_digest((generation_id, task_id, principal)) + ":"


def _grant_id(generation_id: str, task_id: str, principal: str, source_id: str) -> str:
    return _task_prefix(generation_id, task_id, principal) + canonical_runtime_digest(source_id)


def validate_runtime_source_release_event(
    record_json: str, *, grant_id: str | int, previous_json: str | None,
) -> None:
    """Bind replayed grant state to the owner transition and physical key."""
    grant = RuntimeSourceReleaseGrant.model_validate_json(record_json)
    if grant.grant_id != grant_id:
        raise ValueError("source release grant key differs from its catalog identity")
    if previous_json is None:
        if grant.status != "active":
            raise ValueError("source release grant must begin active")
        return
    previous = RuntimeSourceReleaseGrant.model_validate_json(previous_json)
    if (
        previous.status != "active"
        or grant.status != "revoked"
        or grant.model_dump(exclude={"status", "version", "revoked_at"})
        != previous.model_dump(exclude={"status", "version", "revoked_at"})
    ):
        raise ValueError("source release grant can only be revoked without changing its scope")


def _observation_matches(
    connection: sqlite3.Connection, repository: RuntimeStateRepository, grant: RuntimeSourceReleaseGrant,
) -> bool:
    origin = grant.observation_origin
    row = repository.get_command_receipt_in(connection, operation_origin_namespace(origin), origin.operation_id)
    return row is not None and (
        row.status == "committed"
        and row.operation_origin == origin
        and row.origin_proof_digest == grant.observation_proof_digest
        and row.source_admission == grant.source
        and row.result_digest == grant.source.digest()
    )


def _record(
    connection: sqlite3.Connection, repository: RuntimeStateRepository, memory_id: str,
) -> CanonicalMemoryRecord | None:
    row = repository.partition.read_current_record_row(connection, memory_id)
    return None if row is None else CanonicalMemoryRecord.model_validate_json(row["record_json"])


def _release_is_current(
    connection: sqlite3.Connection,
    repository: RuntimeStateRepository,
    grant: RuntimeSourceReleaseGrant,
    *,
    generation_id: str,
    task_id: str,
    principal: str,
    revoked: RevokedIdentityServingGate,
    now: datetime,
) -> bool:
    binding = grant.binding
    admission = grant.source
    if (
        grant.status != "active"
        or binding.generation_id != generation_id or grant.task_id != task_id or binding.runtime_principal != principal
        or now.utcoffset() is None or now < grant.issued_at
        or revoked.is_revoked_task(task_id) or revoked.is_revoked_task(binding.provider_task_id)
        or revoked.is_revoked_source(admission.source_id) or revoked.is_revoked_record(admission.source_id)
    ):
        return False
    task = repository.get_task_in(connection, task_id)
    if task is None or task.principal != principal or task.project != grant.task_project:
        return False
    try:
        if not _observation_matches(connection, repository, grant):
            return False
        source = _record(connection, repository, admission.source_id)
        index = _record(connection, repository, _index_id(admission.delivery_key_digest))
        return (
            source is not None and index is not None
            and source.memory_id == admission.source_id
            and source.task_id == binding.provider_task_id and source.session_id == binding.provider_session_id
            and source.source_kind == "semantic_ingestion_source"
            and source.domain == MemoryDomain.TRANSCRIPT and source.is_raw_event
            and source.status == CommitStatus.COMMITTED and source.visibility == MemoryRecordVisibility.INTERNAL_CONTROL
            and source.validity_status not in (TemporalValidityStatus.EXPIRED, TemporalValidityStatus.INVALIDATED)
            and (source.valid_from is None or (source.valid_from.utcoffset() is not None and source.valid_from <= now))
            and (source.valid_to is None or (source.valid_to.utcoffset() is not None and now < source.valid_to))
            and record_digest(source) == admission.source_record_digest
            and source_admission_source_digest(source) == admission.provider_source_digest
            and index.source_kind == "semantic_ingestion_admission_index"
            and record_digest(index) == grant.source_index_record_digest
            and _index_digest(index) == admission.admission_index_digest
            and revoked.keeps_record(source) and revoked.keeps_record(index)
        )
    except (TypeError, ValueError):
        return False


def _generation(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> str | None:
    if not repository.partition.supports_runtime_source_release(connection):
        return None
    row = repository.partition.read_publication_row(connection)
    return None if row is None else str(row["generation_id"])


def get_current_source_release(
    connection: sqlite3.Connection,
    repository: RuntimeStateRepository,
    *,
    task_id: str,
    principal: str,
    source_ref: ConsolidationSourceReference,
    now: datetime,
    revoked: RevokedIdentityServingGate,
) -> RuntimeSourceAdmissionReceipt | None:
    """Return metadata only, from the caller's fenced and verified partition snapshot."""
    generation_id = _generation(connection, repository)
    if generation_id is None:
        return None
    grant_id = _grant_id(generation_id, task_id, principal, source_ref.source_id)
    raw = repository.partition.read_runtime_source_release_grant(connection, grant_id)
    if raw is None:
        return None
    try:
        grant = RuntimeSourceReleaseGrant.model_validate_json(raw)
    except ValidationError:
        return None
    if grant.grant_id != grant_id or grant.source_ref() != source_ref:
        return None
    return grant.source if _release_is_current(
        connection, repository, grant, generation_id=generation_id, task_id=task_id,
        principal=principal, revoked=revoked, now=now,
    ) else None


def list_runtime_released_sources(
    connection: sqlite3.Connection,
    repository: RuntimeStateRepository,
    *,
    task_id: str,
    principal: str,
    now: datetime,
    revoked: RevokedIdentityServingGate,
    limit: int = _MAX_ACTIVE_PER_TASK,
) -> tuple[ConsolidationSourceReference, ...]:
    """Resolve a bounded, stable set for the caller's exact task."""
    if not 1 <= limit <= _MAX_ACTIVE_PER_TASK:
        raise ValueError("runtime source release limit is outside the supported bound")
    generation_id = _generation(connection, repository)
    if generation_id is None:
        return ()
    values: list[ConsolidationSourceReference] = []
    for raw in repository.partition.read_active_runtime_source_release_grants(
        connection, task_prefix=_task_prefix(generation_id, task_id, principal), limit=_MAX_ACTIVE_PER_TASK,
    ):
        try:
            grant = RuntimeSourceReleaseGrant.model_validate_json(raw)
        except ValidationError:
            continue
        if _release_is_current(
            connection, repository, grant, generation_id=generation_id, task_id=task_id,
            principal=principal, revoked=revoked, now=now,
        ):
            values.append(grant.source_ref())
            if len(values) == limit:
                break
    return tuple(values)


class RuntimeSourceReleaseAuthority:
    """Mutate release grants only through the installation publication owner."""

    def __init__(self, administration: StorageAdministrationService) -> None:
        self._administration = administration

    def issue(
        self,
        *,
        capability: OwnerCapability,
        observation_origin: OperationOrigin,
        binding: RuntimeSourceTaskBinding,
        operation_fence: OperationFenceBinding,
        resolve_ingress: Callable[[], AuthenticatedIngressContext | None],
    ) -> RuntimeSourceReleaseGrant:
        committed: list[RuntimeSourceReleaseGrant] = []
        publication: list[RuntimePublicationState] = []
        origin = observation_origin.coordinate
        proof_digest = operation_origin_proof_digest(observation_origin)
        administration = self._administration
        revoked = RefreshingRevokedIdentityView(administration.installation_root / "control")
        require_owner_capability(administration, capability)

        def authorize(state: InstallationControlState, finalized: RuntimePublicationState) -> None:
            require_owner_capability(administration, capability)
            if (
                state.mode != "active" or origin.generation_id != finalized.data_generation_id
                or not administration.verify_operation_origin(observation_origin)
            ):
                raise _denied()
            publication.append(finalized)

        def apply(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            now = datetime.now(UTC)
            if not repository.partition.supports_runtime_source_release(connection):
                raise RuntimeSourceAuthorityError("unsupported_configuration: runtime source release catalog upgrade required")
            task = repository.get_task_in(connection, binding.runtime_task_id)
            observation = repository.get_command_receipt_in(connection, operation_origin_namespace(origin), origin.operation_id)
            if (
                task is None or task.principal != origin.principal or revoked.is_revoked_task(task.task_id)
                or observation is None or observation.status != "committed" or observation.operation_origin != origin
                or observation.origin_proof_digest != proof_digest
                or observation.source_admission is None
            ):
                raise _denied()
            source = observation.source_admission
            evidence = resolve_runtime_source(
                connection, repository.partition, finalized=publication[0], origin=origin, runtime_task_id=task.task_id,
                source_digest=source.provider_source_digest, operation_fence=operation_fence, resolve_ingress=resolve_ingress,
                binding=binding, revoked=revoked, now=now,
            )
            if (
                evidence.source_ref != ConsolidationSourceReference(
                    source_id=source.source_id, source_digest=source.source_record_digest,
                )
                or evidence.admission_index_digest != source.admission_index_digest
                or evidence.delivery_key_digest != source.delivery_key_digest
                or evidence.source_write_revision != source.source_write_revision
                or evidence.source_type != source.source_type or evidence.modalities != source.modalities
                or evidence.retained_at != source.retained_at
            ):
                raise _denied()
            index = _record(connection, repository, _index_id(source.delivery_key_digest))
            if index is None:
                raise _denied()
            grant_id = _grant_id(origin.generation_id, task.task_id, origin.principal, source.source_id)
            grant = RuntimeSourceReleaseGrant(
                grant_id=grant_id, task_id=task.task_id, task_project=task.project, binding=binding,
                observation_origin=origin, observation_proof_digest=proof_digest, source=source,
                source_index_record_digest=record_digest(index), issued_at=now,
            )
            raw = repository.partition.read_runtime_source_release_grant(connection, grant_id)
            if raw is not None:
                previous = RuntimeSourceReleaseGrant.model_validate_json(raw)
                if previous != grant.model_copy(update={"issued_at": previous.issued_at}):
                    raise _denied()
                committed.append(previous)
                return
            if len(repository.partition.read_active_runtime_source_release_grants(
                connection, task_prefix=_task_prefix(origin.generation_id, task.task_id, origin.principal),
                limit=_MAX_ACTIVE_PER_TASK,
            )) >= _MAX_ACTIVE_PER_TASK:
                raise RuntimeSourceAuthorityError("resource_exhausted: task runtime source release limit reached")
            repository.partition.write_runtime_source_release_grant(
                connection, grant_id=grant_id, record_json=grant.model_dump_json(), previous_json=None,
            )
            committed.append(grant)

        publish_runtime_change(administration, apply, validate_authority=authorize)
        return committed[0]

    def revoke(self, *, capability: OwnerCapability, grant_id: str) -> RuntimeSourceReleaseGrant:
        """Revoke terminally. The replay chain retains the active-to-revoked transition."""
        administration = self._administration
        committed: list[RuntimeSourceReleaseGrant] = []
        publication: list[RuntimePublicationState] = []
        require_owner_capability(administration, capability)

        def authorize(_state: InstallationControlState, finalized: RuntimePublicationState) -> None:
            require_owner_capability(administration, capability)
            publication.append(finalized)

        def apply(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            if not repository.partition.supports_runtime_source_release(connection):
                raise _denied()
            raw = repository.partition.read_runtime_source_release_grant(connection, grant_id)
            if raw is None:
                raise _denied()
            previous = RuntimeSourceReleaseGrant.model_validate_json(raw)
            if previous.grant_id != grant_id or previous.binding.generation_id != publication[0].data_generation_id:
                raise _denied()
            if previous.status == "revoked":
                committed.append(previous)
                return
            revoked = previous.model_copy(update={
                "version": 2, "status": "revoked", "revoked_at": max(previous.issued_at, datetime.now(UTC)),
            })
            repository.partition.write_runtime_source_release_grant(
                connection, grant_id=grant_id, record_json=revoked.model_dump_json(), previous_json=raw,
            )
            committed.append(revoked)

        publish_runtime_change(administration, apply, validate_authority=authorize)
        return committed[0]


def _denied() -> RuntimeSourceAuthorityError:
    return RuntimeSourceAuthorityError("denied: governed runtime source release is unavailable")
