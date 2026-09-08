"""Closed profile-3 ingestion-time attestation contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_observation_records import Digest, Identifier


def _utc(value: datetime, *, label: str) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value.astimezone(UTC)


class _ClosedIngestionTimeContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceRetentionTimeAttestation(_ClosedIngestionTimeContract):
    kind: Literal["source_retention"]
    attestation_id: Identifier
    source_id: Identifier
    operation_fence_id: Identifier
    retained_at: datetime
    graph_revision: Identifier
    clock_identity: Identifier
    source_record_digest: Digest
    attestation_digest: Digest

    @model_validator(mode="after")
    def _validate_time(self) -> SourceRetentionTimeAttestation:
        _utc(self.retained_at, label="source retention time")
        return self


class TransactionGroupCommitTimeAttestation(_ClosedIngestionTimeContract):
    kind: Literal["transaction_group_commit"]
    attestation_id: Identifier
    source_id: Identifier
    operation_fence_id: Identifier
    transaction_group_id: Identifier
    operation_ids: tuple[Identifier, ...]
    transaction_started_at: datetime
    transaction_committed_at: datetime
    graph_revision_before: Identifier
    graph_revision_after: Identifier
    applied_graph_delta_digest: Digest
    clock_identity: Identifier
    committed_batch_digest: Digest
    attestation_digest: Digest

    @model_validator(mode="after")
    def _validate_time(self) -> TransactionGroupCommitTimeAttestation:
        started_at = _utc(self.transaction_started_at, label="transaction start time")
        committed_at = _utc(self.transaction_committed_at, label="transaction commit time")
        if committed_at < started_at:
            raise ValueError("transaction commit time precedes transaction start time")
        return self


ProductionIngestionTimeAttestation: TypeAlias = Annotated[
    SourceRetentionTimeAttestation | TransactionGroupCommitTimeAttestation,
    Field(discriminator="kind"),
]


__all__ = [
    "ProductionIngestionTimeAttestation", "SourceRetentionTimeAttestation",
    "TransactionGroupCommitTimeAttestation",
]
