"""Provider authorization for protected source references used by managed runtime."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from memorii.core.consolidation.runtime_outputs import ConsolidationSourceReference
from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService, source_admission_index_record_id
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext, OperationFenceBinding
from memorii.core.memory_evolution.source_governance import semantic_required_outcome_scopes_for_retained_source
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import ReadOnlyMemoryPlaneSnapshotStore, record_digest
from memorii.core.persistence.contracts import RuntimePublicationState
from memorii.core.persistence.runtime_contracts import OperationOriginCoordinate
from memorii.core.semantic_ingestion.contracts import SegmentGovernanceCarrierSet, SourceAuthorityEvidence
from memorii.core.storage_administration.revoked_identity_view import RevokedIdentityServingGate
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
    SourceModality,
    TemporalValidityStatus,
)
from memorii.stores.sqlite.partition import PartitionDataRepository

_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_Coordinate = Annotated[str, Field(min_length=1, max_length=512, pattern=r"^[^\x00]+$")]


class RuntimeSourceAuthorityError(RuntimeError):
    """A content-free refusal to expose a protected runtime source reference."""


class RuntimeSourceTaskBinding(BaseModel):
    """Installation-owned association between runtime and one provider delivery."""

    installation_id: _Coordinate
    repository_id: _Coordinate
    generation_id: _Coordinate
    runtime_task_id: _Coordinate
    runtime_principal: _Coordinate
    client_namespace: _Coordinate
    provider_task_id: _Coordinate
    provider_session_id: _Coordinate
    provider_principal_binding_digest: _Digest
    delivery_key_digest: _Digest

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeSourceEvidence(BaseModel):
    """Metadata derived from a live, exact provider admission; contains no source text."""

    source_ref: ConsolidationSourceReference
    source_digest: _Digest
    admission_index_digest: _Digest
    delivery_key_digest: _Digest
    source_write_revision: int = Field(ge=1)
    source_type: Literal["user"] = "user"
    modalities: tuple[SourceModality, ...] = Field(min_length=1)
    retained_at: AwareDatetime

    model_config = ConfigDict(extra="forbid", frozen=True)


def resolve_runtime_source(
    connection: sqlite3.Connection,
    partition: PartitionDataRepository,
    *,
    finalized: RuntimePublicationState,
    origin: OperationOriginCoordinate,
    runtime_task_id: str,
    source_digest: str,
    operation_fence: OperationFenceBinding,
    resolve_ingress: Callable[[], AuthenticatedIngressContext | None],
    binding: RuntimeSourceTaskBinding,
    revoked: RevokedIdentityServingGate,
    now: datetime,
) -> RuntimeSourceEvidence:
    """Recheck an owner-bound native user source inside the caller's signed snapshot.

    The runtime owner holds its verified context and passes the authorized
    operation. Provider composition supplies the binding, operation fence and
    fresh ingress resolver. The host command body can select only the digest.
    """
    if (
        now.utcoffset() is None
        or binding.installation_id != origin.installation_id
        or binding.installation_id != finalized.installation_id
        or binding.repository_id != origin.repository_id
        or binding.repository_id != finalized.repository_id
        or binding.generation_id != origin.generation_id
        or binding.generation_id != finalized.data_generation_id
        or binding.runtime_task_id != runtime_task_id
        or binding.runtime_principal != origin.principal
        or binding.client_namespace != origin.client_namespace
        or operation_fence.source_digest != source_digest
        or operation_fence.delivery_identity.delivery_key_digest != binding.delivery_key_digest
        or operation_fence.delivery_principal_binding_digest != binding.provider_principal_binding_digest
        or revoked.is_revoked_task(runtime_task_id)
        or revoked.is_revoked_task(binding.provider_task_id)
        or revoked.is_revoked_source(operation_fence.source_id)
    ):
        raise _denied()
    ingress = resolve_ingress()
    if (
        ingress is None
        or ingress.delivery_principal_binding.binding_digest != binding.provider_principal_binding_digest
        or ingress.semantic_source_authority is None
        or ingress.semantic_source_authority.authenticated_provenance_class != "authenticated_user"
    ):
        raise _denied()
    publication = partition.read_publication_row(connection)
    if publication is None or publication["tuple_digest"] != finalized.payload_digest():
        raise _denied()

    source_id = operation_fence.source_id
    index_id = source_admission_index_record_id(binding.delivery_key_digest)
    source_row = partition.read_current_record_row(connection, source_id)
    index_row = partition.read_current_record_row(connection, index_id)
    if source_row is None or index_row is None:
        raise _denied()
    source_bytes = str(source_row["record_json"])
    index_bytes = str(index_row["record_json"])
    # The immutable source and admission index are an atomic provider write.
    # Read their original revision by primary key without exposing source text.
    version = partition.first_memory_pair_revision(connection, (source_id, source_bytes), (index_id, index_bytes))
    if version is None or not 0 < int(version["batch_revision"]) <= finalized.vector.memory_write_revision:
        raise _denied()

    try:
        source = CanonicalMemoryRecord.model_validate_json(source_bytes)
        index = CanonicalMemoryRecord.model_validate_json(index_bytes)
        if (
            source.memory_id != source_id
            or index.memory_id != index_id
            or source.user_id != ingress.delivery_principal_binding.principal_subject_id
            or source.task_id != binding.provider_task_id
            or source.session_id != binding.provider_session_id
            or source.source_kind != "semantic_ingestion_source"
            or source.domain != MemoryDomain.TRANSCRIPT
            or source.status != CommitStatus.COMMITTED
            or source.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
            or not source.is_raw_event
            or source.validity_status in (TemporalValidityStatus.EXPIRED, TemporalValidityStatus.INVALIDATED)
            or (source.valid_from is not None and (source.valid_from.utcoffset() is None or now < source.valid_from))
            or (source.valid_to is not None and (source.valid_to.utcoffset() is None or now >= source.valid_to))
            or not revoked.keeps_record(source)
            or not revoked.keeps_record(index)
        ):
            raise _denied()
        admission = source.content.get("source_admission")
        if not isinstance(admission, dict) or admission.get("source_kind") != "conversation_turn":
            raise _denied()
        authority = SourceAuthorityEvidence.model_validate(admission.get("retained_source_authority_evidence"))
        current_authority = ingress.semantic_source_authority
        if (
            authority.source_id != source_id
            or authority.source_digest != source_digest
            or authority.authority.model_dump() != current_authority.model_dump(exclude={"provenance_digest"})
            or authority.provenance_digest != current_authority.provenance_digest
        ):
            raise _denied()
        snapshot = ReadOnlyMemoryPlaneSnapshotStore(
            write_revision=finalized.vector.memory_write_revision, records=(source, index),
        )
        accepted = GovernedSourceAdmissionService(MemoryPlaneService(record_store=snapshot)).recover_pending_admission(
            operation_fence=operation_fence, authenticated_ingress=ingress,
        )
        if (
            accepted is None
            or not accepted.observation.is_step_one_admitted
            or accepted.observation.required_outcome_scopes
            != semantic_required_outcome_scopes_for_retained_source(accepted.required_outcome_scopes)
        ):
            raise _denied()
        carriers = accepted.observation.segment_governance_carriers
        if not isinstance(carriers, SegmentGovernanceCarrierSet):
            raise _denied()
        modalities = tuple(sorted({carrier.modality for carrier in carriers.bindings}))
        if not modalities or SourceModality.ASSISTANT_CLAIM in modalities or SourceModality.TOOL_RESULT in modalities:
            raise _denied()
        return RuntimeSourceEvidence(
            source_ref=ConsolidationSourceReference(source_id=source_id, source_digest=record_digest(source)),
            source_digest=accepted.source_digest, admission_index_digest=accepted.admission_index_digest,
            delivery_key_digest=binding.delivery_key_digest, source_write_revision=int(version["batch_revision"]),
            modalities=modalities, retained_at=source.timestamp,
        )
    except (TypeError, ValueError):
        raise _denied() from None


def _denied() -> RuntimeSourceAuthorityError:
    return RuntimeSourceAuthorityError("denied: governed runtime source is unavailable")
