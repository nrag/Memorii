"""Profile-3 shapes for immutable native projection-publication members.

The protected registry decoder owns the receipt and evidence self-digest checks.
These models establish only the typed body shape and deterministic member
coordinates needed by the future group-CAS owner.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import length_prefixed
from memorii.core.memory_evolution.projection_binding import ProjectionHistoryReplayBinding
from memorii.core.memory_evolution.projection_history import (
    TemporalProjectionPublication,
    TrustProjectionPublication,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.semantic_ingestion.contracts import SemanticGraphDelta
from memorii.core.semantic_ingestion.event_replay import (
    SemanticMemoryEventBatch,
    SemanticReplayAuthorityAggregate,
    SemanticReplayCheckpointBundle,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.observation_activation_runtime import RegisteredObservationArtifact
    from memorii.core.memory_evolution.projection_history import PreparedProjectionPublication
    from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
    from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
    from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory

_DIGEST = r"^[0-9a-f]{64}$"
_IDENTITY_DOMAIN = b"memorii.bootstrap-graph.native-projection-publication-identity.v3"
_MEMBER_PREFIX = "semantic_ingestion:bootstrap-graph-v3:native-projection-publication:"


class _ClosedProfileThreeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def reject_boolean_schema_version(cls, value: object) -> object:
        if isinstance(value, Mapping) and isinstance(value.get("schema_version"), bool):
            raise ValueError("schema version must be an integer literal")
        return value


def publication_identity_digest(
    *,
    source_operation_id: str,
    transaction_group_id: str,
    request_ctv_digest: str,
    canonical_graph_delta: SemanticGraphDelta,
    canonical_event_batch: SemanticMemoryEventBatch,
) -> str:
    """Derive the pre-receipt identity from the five approved LP components."""
    _require_identifier(source_operation_id, "source operation ID")
    _require_identifier(transaction_group_id, "transaction group ID")
    _require_digest(request_ctv_digest, "request CTV digest")
    if canonical_event_batch.graph_delta_digest != canonical_graph_delta.delta_digest:
        raise ValueError("native projection publication graph/event coordinates are substituted")
    return sha256(
        length_prefixed(
            _IDENTITY_DOMAIN,
            source_operation_id.encode("utf-8"),
            transaction_group_id.encode("utf-8"),
            request_ctv_digest.encode("ascii"),
            canonical_graph_delta.delta_digest.encode("ascii"),
            canonical_event_batch.source_event_batch_digest.encode("ascii"),
        )
    ).hexdigest()


def native_projection_publication_receipt_id(publication_identity: str) -> str:
    return _native_projection_publication_member_id(publication_identity, "receipt")


def native_projection_authority_evidence_id(publication_identity: str) -> str:
    return _native_projection_publication_member_id(publication_identity, "aggregate")


def native_projection_checkpoint_evidence_id(publication_identity: str) -> str:
    return _native_projection_publication_member_id(publication_identity, "checkpoint")


def _native_projection_publication_member_id(publication_identity: str, suffix: str) -> str:
    _require_digest(publication_identity, "native projection publication identity")
    return f"{_MEMBER_PREFIX}{publication_identity}:{suffix}"


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"native projection publication {label} is invalid")


def _require_digest(value: object, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"native projection publication {label} must be lowercase SHA-256")


class BootstrapGraphNativeProjectionPublicationReceiptV3(_ClosedProfileThreeModel):
    schema_version: Literal[1]
    source_operation_id: str = Field(min_length=1)
    transaction_group_id: str = Field(min_length=1)
    request_ctv_digest: str = Field(pattern=_DIGEST)
    graph_revision_before: str = Field(min_length=1)
    graph_revision_after: str = Field(min_length=1)
    canonical_graph_delta: SemanticGraphDelta
    canonical_event_batch: SemanticMemoryEventBatch
    temporal_publication: TemporalProjectionPublication
    trust_publication: TrustProjectionPublication
    projection_history_replay_bindings: tuple[ProjectionHistoryReplayBinding, ProjectionHistoryReplayBinding]
    replay_authority_evidence_id: str = Field(min_length=1)
    replay_authority_evidence_digest: str = Field(pattern=_DIGEST)
    replay_checkpoint_evidence_id: str = Field(min_length=1)
    replay_checkpoint_evidence_digest: str = Field(pattern=_DIGEST)
    publication_identity_digest: str = Field(pattern=_DIGEST)
    receipt_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def validate_coordinates(self) -> BootstrapGraphNativeProjectionPublicationReceiptV3:
        if (
            self.canonical_event_batch.transaction_group_id != self.transaction_group_id
            or self.canonical_event_batch.graph_delta_digest != self.canonical_graph_delta.delta_digest
            or tuple(binding.projection_kind for binding in self.projection_history_replay_bindings)
            != ("temporal", "trust")
            or self.publication_identity_digest
            != publication_identity_digest(
                source_operation_id=self.source_operation_id,
                transaction_group_id=self.transaction_group_id,
                request_ctv_digest=self.request_ctv_digest,
                canonical_graph_delta=self.canonical_graph_delta,
                canonical_event_batch=self.canonical_event_batch,
            )
        ):
            raise ValueError("native projection publication receipt coordinates are invalid")
        return self


class BootstrapGraphNativeReplayAuthorityEvidenceV3(_ClosedProfileThreeModel):
    schema_version: Literal[1]
    source_operation_id: str = Field(min_length=1)
    transaction_group_id: str = Field(min_length=1)
    request_ctv_digest: str = Field(pattern=_DIGEST)
    publication_identity_digest: str = Field(pattern=_DIGEST)
    receipt_id: str = Field(min_length=1)
    aggregate: SemanticReplayAuthorityAggregate
    evidence_digest: str = Field(pattern=_DIGEST)


class BootstrapGraphNativeReplayCheckpointEvidenceV3(_ClosedProfileThreeModel):
    schema_version: Literal[1]
    source_operation_id: str = Field(min_length=1)
    transaction_group_id: str = Field(min_length=1)
    request_ctv_digest: str = Field(pattern=_DIGEST)
    publication_identity_digest: str = Field(pattern=_DIGEST)
    receipt_id: str = Field(min_length=1)
    checkpoint_bundle: SemanticReplayCheckpointBundle
    evidence_digest: str = Field(pattern=_DIGEST)


def validate_native_projection_publication_evidence_coordinates(
    *,
    receipt: BootstrapGraphNativeProjectionPublicationReceiptV3,
    receipt_id: str,
    authority_evidence: BootstrapGraphNativeReplayAuthorityEvidenceV3,
    checkpoint_evidence: BootstrapGraphNativeReplayCheckpointEvidenceV3,
) -> None:
    """Check direct receipt/evidence joins without validating protected bodies."""
    receipt_coordinates = (
        receipt.source_operation_id,
        receipt.transaction_group_id,
        receipt.request_ctv_digest,
        receipt.publication_identity_digest,
    )
    if (
        receipt_id != native_projection_publication_receipt_id(receipt.publication_identity_digest)
        or
        receipt.replay_authority_evidence_id
        != native_projection_authority_evidence_id(receipt.publication_identity_digest)
        or receipt.replay_checkpoint_evidence_id
        != native_projection_checkpoint_evidence_id(receipt.publication_identity_digest)
        or receipt.replay_authority_evidence_digest != authority_evidence.evidence_digest
        or receipt.replay_checkpoint_evidence_digest != checkpoint_evidence.evidence_digest
        or authority_evidence.receipt_id != receipt_id
        or checkpoint_evidence.receipt_id != receipt_id
        or (
            authority_evidence.source_operation_id,
            authority_evidence.transaction_group_id,
            authority_evidence.request_ctv_digest,
            authority_evidence.publication_identity_digest,
        )
        != receipt_coordinates
        or (
            checkpoint_evidence.source_operation_id,
            checkpoint_evidence.transaction_group_id,
            checkpoint_evidence.request_ctv_digest,
            checkpoint_evidence.publication_identity_digest,
        )
        != receipt_coordinates
        or authority_evidence.aggregate.graph_state.graph_revision != receipt.graph_revision_after
        or authority_evidence.aggregate.projection_history_bindings != receipt.projection_history_replay_bindings
        or authority_evidence.aggregate.latest_checkpoint != checkpoint_evidence.checkpoint_bundle
    ):
        raise ValueError("native projection publication evidence coordinates are substituted")


def prepare_native_projection_evidence(
    *,
    source_operation_id: str,
    transaction_group_id: str,
    request_ctv_digest: str,
    graph_revision_before: str,
    graph_revision_after: str,
    canonical_graph_delta: SemanticGraphDelta,
    canonical_event_batch: SemanticMemoryEventBatch,
    prepared_projection: PreparedProjectionPublication,
    aggregate: SemanticReplayAuthorityAggregate,
    checkpoint: SemanticReplayCheckpointBundle,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> tuple[BootstrapGraphNativeProjectionPublicationReceiptV3, tuple[CanonicalMemoryRecord, CanonicalMemoryRecord, CanonicalMemoryRecord]]:
    """Seal native projection output as registered immutable CAS members."""
    from memorii.core.memory_evolution.observation_activation_runtime import (
        emit_registered_observation_artifact,
    )
    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

    identity = publication_identity_digest(
        source_operation_id=source_operation_id,
        transaction_group_id=transaction_group_id,
        request_ctv_digest=request_ctv_digest,
        canonical_graph_delta=canonical_graph_delta,
        canonical_event_batch=canonical_event_batch,
    )
    projection = prepared_projection.publication
    bindings = projection.replay_bindings
    if (
        tuple(binding.projection_kind for binding in bindings) != ("temporal", "trust")
        or aggregate.graph_state.graph_revision != graph_revision_after
        or aggregate.projection_history_bindings != bindings
        or aggregate.latest_checkpoint != checkpoint
        or checkpoint.watermark_batch != canonical_event_batch
        or canonical_event_batch.transaction_group_id != transaction_group_id
        or canonical_event_batch.graph_delta_digest != canonical_graph_delta.delta_digest
        or canonical_event_batch.events[0].payload.graph_revision_before != graph_revision_before
        or canonical_event_batch.events[0].payload.graph_revision_after != graph_revision_after
        or projection.temporal.generation.base_graph_revision != graph_revision_after
        or projection.trust.generation.base_graph_revision != graph_revision_after
        or projection.temporal.active_pointer.repository_id != projection.trust.active_pointer.repository_id
    ):
        raise ValueError("native projection publication closure is substituted")
    receipt_id = native_projection_publication_receipt_id(identity)
    authority_id = native_projection_authority_evidence_id(identity)
    checkpoint_id = native_projection_checkpoint_evidence_id(identity)
    authority = emit_registered_observation_artifact(
        BootstrapGraphNativeReplayAuthorityEvidenceV3(
            schema_version=1, source_operation_id=source_operation_id,
            transaction_group_id=transaction_group_id, request_ctv_digest=request_ctv_digest,
            publication_identity_digest=identity, receipt_id=receipt_id,
            aggregate=aggregate, evidence_digest="0" * 64,
        ), schema_id="BootstrapGraphNativeReplayAuthorityEvidenceV3",
        history=history, publication=publication, limits=limits,
    )
    checkpoint_evidence = emit_registered_observation_artifact(
        BootstrapGraphNativeReplayCheckpointEvidenceV3(
            schema_version=1, source_operation_id=source_operation_id,
            transaction_group_id=transaction_group_id, request_ctv_digest=request_ctv_digest,
            publication_identity_digest=identity, receipt_id=receipt_id,
            checkpoint_bundle=checkpoint, evidence_digest="0" * 64,
        ), schema_id="BootstrapGraphNativeReplayCheckpointEvidenceV3",
        history=history, publication=publication, limits=limits,
    )
    if (not isinstance(authority.value, BootstrapGraphNativeReplayAuthorityEvidenceV3)
            or not isinstance(checkpoint_evidence.value, BootstrapGraphNativeReplayCheckpointEvidenceV3)):
        raise ValueError("native projection evidence registration is invalid")
    receipt_artifact = emit_registered_observation_artifact(
        BootstrapGraphNativeProjectionPublicationReceiptV3(
            schema_version=1, source_operation_id=source_operation_id,
            transaction_group_id=transaction_group_id, request_ctv_digest=request_ctv_digest,
            graph_revision_before=graph_revision_before, graph_revision_after=graph_revision_after,
            canonical_graph_delta=canonical_graph_delta, canonical_event_batch=canonical_event_batch,
            temporal_publication=projection.temporal, trust_publication=projection.trust,
            projection_history_replay_bindings=(bindings[0], bindings[1]),
            replay_authority_evidence_id=authority_id,
            replay_authority_evidence_digest=authority.value.evidence_digest,
            replay_checkpoint_evidence_id=checkpoint_id,
            replay_checkpoint_evidence_digest=checkpoint_evidence.value.evidence_digest,
            publication_identity_digest=identity, receipt_digest="0" * 64,
        ), schema_id="BootstrapGraphNativeProjectionPublicationReceiptV3",
        history=history, publication=publication, limits=limits,
    )
    receipt = receipt_artifact.value
    if not isinstance(receipt, BootstrapGraphNativeProjectionPublicationReceiptV3):
        raise ValueError("native projection receipt registration is invalid")
    validate_native_projection_publication_evidence_coordinates(
        receipt=receipt, receipt_id=receipt_id,
        authority_evidence=authority.value,
        checkpoint_evidence=checkpoint_evidence.value,
    )
    timestamp = canonical_event_batch.events[0].timestamp
    def record(record_id: str, kind: str, artifact: RegisteredObservationArtifact) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(
            memory_id=record_id, domain=MemoryDomain.EXECUTION, text="",
            content={"semantic_ingestion_kind": kind, "artifact": artifact.raw.decode("utf-8")},
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_" + kind,
            timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
    return receipt, (
        record(receipt_id, "bootstrap_graph_v3_native_projection_receipt", receipt_artifact),
        record(authority_id, "bootstrap_graph_v3_native_replay_authority_evidence", authority),
        record(checkpoint_id, "bootstrap_graph_v3_native_replay_checkpoint_evidence", checkpoint_evidence),
    )


__all__ = [
    "BootstrapGraphNativeProjectionPublicationReceiptV3",
    "BootstrapGraphNativeReplayAuthorityEvidenceV3",
    "BootstrapGraphNativeReplayCheckpointEvidenceV3",
    "native_projection_authority_evidence_id",
    "native_projection_checkpoint_evidence_id",
    "native_projection_publication_receipt_id",
    "publication_identity_digest",
    "prepare_native_projection_evidence",
    "validate_native_projection_publication_evidence_coordinates",
]
