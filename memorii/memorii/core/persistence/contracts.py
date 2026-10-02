"""Closed persistence contracts for durable partition publication and control.

Every model here is a closed schema (``extra=forbid``) with finite enums and
explicit typed unions. Signature purposes are domain-separated strings; no
timestamp is ever used as a fencing token or ordering authority.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RUNTIME_PUBLICATION_SIGNATURE_PURPOSE = "memorii.runtime-publication.v1"
RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE = "memorii.runtime-event-batch.v1"
RUNTIME_CONTROL_JOURNAL_SIGNATURE_PURPOSE = "memorii.runtime-control-journal.v1"

_EMPTY_CHAIN_DOMAIN = b"memorii.runtime-publication.v1\x00empty-chain"
_EMPTY_POINTER_SET_DOMAIN = b"memorii.runtime-publication.v1\x00empty-pointer-set"
_HEX_64 = r"^[0-9a-f]{64}$"
_HEX_SIGNATURE = r"^[0-9a-f]{64,256}$"


def empty_chain_commitment() -> str:
    """Fixed domain-separated commitment for a genesis (empty) history."""
    return hashlib.sha256(_EMPTY_CHAIN_DOMAIN).hexdigest()


def empty_pointer_set_digest() -> str:
    """Fixed domain-separated digest for an empty ontology pointer set."""
    return hashlib.sha256(_EMPTY_POINTER_SET_DOMAIN).hexdigest()


def canonical_json_digest(payload: dict[str, object]) -> str:
    encoded = hashlib.sha256(
        "\x00".join(
            f"{key}={payload[key]}" for key in sorted(payload) if payload[key] is not None
        ).encode("utf-8")
    )
    return encoded.hexdigest()


class GenesisPosition(BaseModel):
    kind: Literal["genesis"] = "genesis"

    model_config = ConfigDict(extra="forbid", frozen=True)


class BatchPosition(BaseModel):
    kind: Literal["batch"] = "batch"
    sequence: int = Field(ge=1)
    digest: str = Field(pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)


PublicationPosition = Annotated[GenesisPosition | BatchPosition, Field(discriminator="kind")]


class MaterializationCatalogEntry(BaseModel):
    catalog: str = Field(min_length=1)
    row_count: int = Field(ge=0)
    digest: str = Field(pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeMaterializationManifest(BaseModel):
    """Every authoritative materialized catalog with its ordered row digest."""

    catalogs: tuple[MaterializationCatalogEntry, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def catalogs_are_unique_and_ordered(self) -> RuntimeMaterializationManifest:
        names = [entry.catalog for entry in self.catalogs]
        if len(set(names)) != len(names):
            raise ValueError("materialization manifest contains duplicate catalogs")
        if names != sorted(names):
            raise ValueError("materialization manifest catalogs must be ordered by id")
        return self

    def digest(self) -> str:
        return canonical_json_digest(
            {
                "catalogs": [
                    f"{entry.catalog}:{entry.row_count}:{entry.digest}"
                    for entry in self.catalogs
                ]
            }
        )


class PartitionRevisionVector(BaseModel):
    """Cross-domain revision heads bound by one partition publication."""

    partition_ordinal: int = Field(ge=0)
    runtime_position: PublicationPosition
    memory_write_revision: int = Field(ge=0)
    memory_data_revision: int = Field(ge=0)
    semantic_position: PublicationPosition
    ontology_pointer_digest: str = Field(pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def genesis(cls) -> PartitionRevisionVector:
        return cls(
            partition_ordinal=0,
            runtime_position=GenesisPosition(),
            memory_write_revision=0,
            memory_data_revision=0,
            semantic_position=GenesisPosition(),
            ontology_pointer_digest=empty_pointer_set_digest(),
        )


class RuntimePublicationState(BaseModel):
    """Finalized signed tuple binding one verified data generation."""

    installation_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    data_generation_id: str = Field(min_length=1)
    position: PublicationPosition
    manifest_digest: str = Field(pattern=_HEX_64)
    checkpoint_digest: str | None = Field(default=None, pattern=_HEX_64)
    trust_registry_digest: str = Field(pattern=_HEX_64)
    eligibility_epoch: int = Field(ge=1)
    vector: PartitionRevisionVector
    signature: str = Field(pattern=_HEX_SIGNATURE)

    model_config = ConfigDict(extra="forbid", frozen=True)

    def signed_payload(self) -> dict[str, object]:
        return {
            "installation_id": self.installation_id,
            "repository_id": self.repository_id,
            "data_generation_id": self.data_generation_id,
            "position": self.position.model_dump(mode="json"),
            "manifest_digest": self.manifest_digest,
            "checkpoint_digest": self.checkpoint_digest,
            "trust_registry_digest": self.trust_registry_digest,
            "eligibility_epoch": self.eligibility_epoch,
            "vector": self.vector.model_dump(mode="json"),
        }

    def payload_digest(self) -> str:
        return canonical_json_digest(self.signed_payload())


IntentPhase = Literal["prepared", "finalized", "aborted", "quarantined"]


class RuntimePublicationIntent(BaseModel):
    intent_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    expected_old_discriminator: Literal["uninitialized"] | str = Field(min_length=1)
    candidate_state: RuntimePublicationState
    operation_binding: str = Field(min_length=1)
    authority_epoch: int = Field(ge=1)
    fence_token: int = Field(ge=1)
    phase: IntentPhase = "prepared"

    model_config = ConfigDict(extra="forbid", frozen=True)


class TrustRegistryEntry(BaseModel):
    key_id: str = Field(min_length=1)
    public_key_fingerprint: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    sequence_interval_start: int = Field(ge=1)
    sequence_interval_end: int | None = None
    lifecycle: Literal["active", "retired"] = "active"

    model_config = ConfigDict(extra="forbid", frozen=True)


class InstallationControlState(BaseModel):
    installation_id: str = Field(min_length=1)
    format_version: int = Field(ge=1)
    control_revision: int = Field(ge=1)
    eligibility_epoch: int = Field(ge=1)
    mode: Literal["active", "read_only", "bypass"] = "active"
    initialization_receipt_digest: str | None = Field(default=None, pattern=_HEX_64)
    adopted_legacy_records_digest: str | None = Field(
        default=None,
        pattern=_HEX_64,
        description=(
            "Fingerprint of the legacy plane this installation was migrated"
            " from; binds the preserved legacy input to its adoption."
        ),
    )
    quarantined_reason: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class InstallationControlJournalEntry(BaseModel):
    revision: int = Field(ge=1)
    prior_digest: str = Field(pattern=_HEX_64)
    operation: Literal[
        "initialize",
        "publication_prepared",
        "publication_finalized",
        "publication_aborted",
        "publication_quarantined",
        "mode_changed",
        "trust_changed",
        "logical_forget_applied",
        "partition_erasure_applied",
    ]
    before_digest: str | None = Field(default=None, pattern=_HEX_64)
    after_digest: str | None = Field(default=None, pattern=_HEX_64)
    entry_digest: str = Field(pattern=_HEX_64)
    signer_key_id: str = Field(min_length=1)
    signature: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "prior_digest": self.prior_digest,
            "operation": self.operation,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "signer_key_id": self.signer_key_id,
        }


__all__ = [
    "BatchPosition",
    "GenesisPosition",
    "InstallationControlJournalEntry",
    "InstallationControlState",
    "MaterializationCatalogEntry",
    "PartitionRevisionVector",
    "PublicationPosition",
    "RUNTIME_CONTROL_JOURNAL_SIGNATURE_PURPOSE",
    "RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE",
    "RUNTIME_PUBLICATION_SIGNATURE_PURPOSE",
    "RuntimeMaterializationManifest",
    "RuntimePublicationIntent",
    "RuntimePublicationState",
    "TrustRegistryEntry",
    "canonical_json_digest",
    "empty_chain_commitment",
    "empty_pointer_set_digest",
]
