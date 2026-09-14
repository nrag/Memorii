"""Typed profile-3 observation replay and checkpoint body shapes.

Signature, self-digest, lifecycle-history, and persistence verification remain
with their protected registry, authority, and store owners.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalIngestionObservationRecord,
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    CanonicalSourceIntroductionRecord,
    CanonicalSourceTerminalOutcomeRecord,
)
from memorii.core.memory_evolution.observation_ledger_contracts import (
    ObservationLedgerEntry,
    ObservationLedgerHead,
)

_DIGEST = r"^[0-9a-f]{64}$"


def _record_identity(record: CanonicalIngestionObservationRecord) -> str:
    """Return the canonical identity named by each native record variant."""
    if isinstance(record, (CanonicalSourceIntroductionRecord, CanonicalOperationIntroductionRecord)):
        return record.introduction_id
    if isinstance(record, (CanonicalOperationTerminalOutcomeRecord, CanonicalSourceTerminalOutcomeRecord)):
        return record.outcome_id
    raise ValueError("unknown canonical ingestion observation record")  # pragma: no cover


def _utc_timestamp(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value.astimezone(UTC)


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def reject_boolean_schema_version(cls, value: object) -> object:
        if (
            "schema_version" in cls.model_fields
            and isinstance(value, Mapping)
            and isinstance(value.get("schema_version"), bool)
        ):
            raise ValueError("schema version must be an integer literal")
        return value


class ObservationReplayState(_ClosedModel):
    schema_version: Literal[1]
    repository_id: str = Field(min_length=1)
    activation_digest: str = Field(pattern=_DIGEST)
    head: ObservationLedgerHead
    entries: tuple[ObservationLedgerEntry, ...]
    records: tuple[CanonicalIngestionObservationRecord, ...]
    state_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def validate_state_coordinates(self) -> ObservationReplayState:
        record_keys = tuple(
            (
                record.ingestion_record_kind,
                _record_identity(record),
            )
            for record in self.records
        )
        if (
            self.head.repository_id != self.repository_id
            or self.head.activation_digest != self.activation_digest
            or tuple(entry.sequence for entry in self.entries) != tuple(range(1, len(self.entries) + 1))
            or len(self.entries) != self.head.sequence
            or any(
                entry.repository_id != self.repository_id or entry.activation_digest != self.activation_digest
                for entry in self.entries
            )
            or (
                bool(self.entries)
                and (
                    self.entries[-1].entry_digest != self.head.last_entry_digest
                    or self.entries[-1].delta.observation_revision_after != self.head.observation_revision
                    or self.entries[-1].delta.observation_delta_id != self.head.last_delta_id
                    or self.entries[-1].delta.delta_digest != self.head.last_delta_digest
                )
            )
            or any(
                entry.previous_entry_digest != prior.entry_digest
                for prior, entry in zip(self.entries, self.entries[1:], strict=False)
            )
            or record_keys != tuple(sorted(set(record_keys)))
        ):
            raise ValueError("observation replay state coordinates are invalid")
        return self


class IngestionObservationReplayCheckpoint(_ClosedModel):
    checkpoint_id: str = Field(min_length=1)
    observation_revision: str = Field(min_length=1)
    last_observation_delta_id: str = Field(min_length=1)
    last_observation_delta_digest: str = Field(pattern=_DIGEST)
    materialized_observation_ledger_digest: str = Field(pattern=_DIGEST)
    observation_schema_fingerprint: str = Field(pattern=_DIGEST)
    created_at: datetime
    signing_key_id: str = Field(min_length=1)
    trust_policy_digest: str = Field(pattern=_DIGEST)
    checkpoint_digest: str = Field(pattern=_DIGEST)
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc_timestamp(value, label="created_at")


class ObservationCheckpointLifecycle(_ClosedModel):
    repository_id: str = Field(min_length=1)
    authority_revision: int = Field(ge=1)
    registry_revision: int = Field(ge=1)
    registry_digest: str = Field(pattern=_DIGEST)
    registry_history_digest: str = Field(pattern=_DIGEST)
    trust_policy_revision: int = Field(ge=1)
    trust_policy_digest: str = Field(pattern=_DIGEST)
    minimum_checkpoint_sequence: int = Field(ge=1)
    predecessor_authority_digest: str | None = Field(..., pattern=_DIGEST)
    authority_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def validate_genesis_shape(self) -> ObservationCheckpointLifecycle:
        if (self.authority_revision == 1) != (self.predecessor_authority_digest is None):
            raise ValueError("observation checkpoint lifecycle predecessor shape is invalid")
        return self


class ObservationCheckpointSigningPreimage(_ClosedModel):
    purpose: Literal["observation_checkpoint"]
    repository_id: str = Field(min_length=1)
    activation_digest: str = Field(pattern=_DIGEST)
    sequence: int = Field(ge=1)
    head: ObservationLedgerHead
    lifecycle: ObservationCheckpointLifecycle
    checkpoint_id: str = Field(min_length=1)
    observation_revision: str = Field(min_length=1)
    last_observation_delta_id: str = Field(min_length=1)
    last_observation_delta_digest: str = Field(pattern=_DIGEST)
    materialized_observation_ledger_digest: str = Field(pattern=_DIGEST)
    observation_schema_fingerprint: str = Field(pattern=_DIGEST)
    created_at: datetime
    signing_key_id: str = Field(min_length=1)
    trust_policy_digest: str = Field(pattern=_DIGEST)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc_timestamp(value, label="created_at")

    @model_validator(mode="after")
    def validate_preimage_coordinates(self) -> ObservationCheckpointSigningPreimage:
        if (
            self.head.repository_id != self.repository_id
            or self.head.activation_digest != self.activation_digest
            or self.head.sequence != self.sequence
            or self.lifecycle.repository_id != self.repository_id
            or self.observation_revision != self.head.observation_revision
            or self.last_observation_delta_id != self.head.last_delta_id
            or self.last_observation_delta_digest != self.head.last_delta_digest
            or self.trust_policy_digest != self.lifecycle.trust_policy_digest
        ):
            raise ValueError("observation checkpoint signing preimage coordinates are invalid")
        return self


class ObservationCheckpointPublicationReceipt(_ClosedModel):
    repository_id: str = Field(min_length=1)
    activation_digest: str = Field(pattern=_DIGEST)
    checkpoint_id: str = Field(min_length=1)
    checkpoint_digest: str = Field(pattern=_DIGEST)
    lifecycle_authority_digest: str = Field(pattern=_DIGEST)
    state_digest: str = Field(pattern=_DIGEST)
    head_digest: str = Field(pattern=_DIGEST)
    receipt_digest: str = Field(pattern=_DIGEST)


class ObservationCheckpointBundle(_ClosedModel):
    schema_version: Literal[1]
    repository_id: str = Field(min_length=1)
    activation_digest: str = Field(pattern=_DIGEST)
    sequence: int = Field(ge=1)
    head: ObservationLedgerHead
    state: ObservationReplayState
    checkpoint: IngestionObservationReplayCheckpoint
    lifecycle: ObservationCheckpointLifecycle
    publication_receipt: ObservationCheckpointPublicationReceipt
    bundle_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def validate_bundle_coordinates(self) -> ObservationCheckpointBundle:
        if (
            self.head.repository_id != self.repository_id
            or self.head.activation_digest != self.activation_digest
            or self.head.sequence != self.sequence
            or self.state.repository_id != self.repository_id
            or self.state.activation_digest != self.activation_digest
            or self.state.head != self.head
            or self.lifecycle.repository_id != self.repository_id
            or self.checkpoint.observation_revision != self.head.observation_revision
            or self.checkpoint.last_observation_delta_id != self.head.last_delta_id
            or self.checkpoint.last_observation_delta_digest != self.head.last_delta_digest
            or self.checkpoint.materialized_observation_ledger_digest != self.state.state_digest
            or self.checkpoint.trust_policy_digest != self.lifecycle.trust_policy_digest
            or self.publication_receipt.repository_id != self.repository_id
            or self.publication_receipt.activation_digest != self.activation_digest
            or self.publication_receipt.checkpoint_id != self.checkpoint.checkpoint_id
            or self.publication_receipt.checkpoint_digest != self.checkpoint.checkpoint_digest
            or self.publication_receipt.lifecycle_authority_digest != self.lifecycle.authority_digest
            or self.publication_receipt.state_digest != self.state.state_digest
            or self.publication_receipt.head_digest != self.head.head_digest
        ):
            raise ValueError("observation checkpoint bundle coordinates are invalid")
        return self


__all__ = [
    "IngestionObservationReplayCheckpoint",
    "ObservationCheckpointBundle",
    "ObservationCheckpointLifecycle",
    "ObservationCheckpointPublicationReceipt",
    "ObservationCheckpointSigningPreimage",
    "ObservationReplayState",
]
