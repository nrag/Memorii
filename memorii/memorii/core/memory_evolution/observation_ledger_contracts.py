"""Strict, revision-free shapes for the profile-3 observation ledger.

These contracts deliberately stop at deterministic in-memory shape validation.
The protected registry/store owns record identifiers, content commitments,
genesis, and all persistence joins.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalIngestionObservationDelta,
    CanonicalSourceTerminalOutcomeRecord,
    IngestionObservationDelta,
    IngestionObservationRecordMutation,
    SourceFinalizationObservationDelta,
    rebuild_graph_effect_contracts,
)
from memorii.core.semantic_ingestion.contracts import (
    GovernanceCarrierArtifact,
    MessageAdmissionCarrierSet,
    MessageAdmissionIdentity,
    RequiredOutcomeScopeSet,
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
)

_DIGEST = r"^[0-9a-f]{64}$"
_IDENTIFIER = Annotated[str, Field(min_length=1)]

# Native graph-effect models carry deferred semantic-ingestion annotations.
# Resolve them through their canonical owner before exposing ledger unions.
rebuild_graph_effect_contracts()


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


class ObservationLedgerHead(_ClosedModel):
    schema_version: Literal[1]
    repository_id: str = Field(min_length=1)
    activation_digest: str = Field(pattern=_DIGEST)
    sequence: int = Field(ge=0)
    observation_revision: str = Field(min_length=1)
    last_delta_id: str | None = Field(..., min_length=1)
    last_delta_digest: str | None = Field(..., pattern=_DIGEST)
    last_entry_digest: str | None = Field(..., pattern=_DIGEST)
    head_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def validate_sequence_shape(self) -> ObservationLedgerHead:
        prior_values = (self.last_delta_id, self.last_delta_digest, self.last_entry_digest)
        if (self.sequence == 0 and any(value is not None for value in prior_values)) or (
            self.sequence > 0 and any(value is None for value in prior_values)
        ):
            raise ValueError("observation ledger head predecessor shape is invalid")
        if (self.sequence == 0) != (self.observation_revision == "genesis"):
            raise ValueError("observation ledger genesis revision is invalid")
        return self


class ObservationGroupResultLocator(_ClosedModel):
    schema_version: Literal[1]
    kind: Literal["group_primary"]
    immutable_record_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    source_operation_id: str = Field(min_length=1)
    operation_fence_id: str = Field(min_length=1)
    transaction_group_id: str = Field(min_length=1)
    operation_ids: tuple[_IDENTIFIER, ...]
    request_ctv_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def validate_operation_ids(self) -> ObservationGroupResultLocator:
        if not self.operation_ids or self.operation_ids != tuple(sorted(set(self.operation_ids))):
            raise ValueError("group result locator operation IDs must be sorted, unique, and nonempty")
        return self


class ObservationSourceResultLocator(_ClosedModel):
    schema_version: Literal[1]
    kind: Literal["source_terminal"]
    immutable_record_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    source_operation_id: str = Field(min_length=1)
    operation_fence_id: str = Field(min_length=1)
    namespace_id: str = Field(min_length=1)
    artifact_generation: int = Field(ge=1)
    member_id: str = Field(min_length=1)
    publication_request_digest: str = Field(pattern=_DIGEST)


ObservationResultLocator: TypeAlias = Annotated[
    ObservationGroupResultLocator | ObservationSourceResultLocator,
    Field(discriminator="kind"),
]


class ObservationGroupSemanticPayload(_ClosedModel):
    """Exact terminal-group delta fields other than revision and delta digest."""

    kind: Literal["terminal_group"]
    observation_delta_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    segment_governance_bindings: tuple[SegmentGovernanceBinding, ...]
    message_admission_identities: tuple[MessageAdmissionIdentity, ...]
    governance_carrier_artifact: GovernanceCarrierArtifact
    operation_fence_id: str = Field(min_length=1)
    transaction_group_id: str = Field(min_length=1)
    operation_ids: tuple[_IDENTIFIER, ...]
    terminal_status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"]
    graph_revision_delta_digest: str | None = Field(default=None, pattern=_DIGEST)
    observation_schema_fingerprint: str = Field(pattern=_DIGEST)
    record_mutations: tuple[IngestionObservationRecordMutation, ...]

    @model_validator(mode="after")
    def validate_payload_shape(self) -> ObservationGroupSemanticPayload:
        if (
            not self.operation_ids
            or not self.record_mutations
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            or len({mutation.record_id for mutation in self.record_mutations}) != len(self.record_mutations)
            or self.segment_governance_bindings
            != tuple(sorted(self.segment_governance_bindings, key=lambda item: item.binding_digest))
            or self.message_admission_identities
            != tuple(sorted(self.message_admission_identities, key=lambda item: item.message_admission_key_digest))
            or (self.terminal_status == "committed") != (self.graph_revision_delta_digest is not None)
        ):
            raise ValueError("terminal-group semantic payload shape is invalid")
        return self

    @classmethod
    def from_delta(cls, delta: IngestionObservationDelta) -> Self:
        """Project a validated native delta without its ledger-assigned fields."""
        return cls(
            kind=delta.kind,
            observation_delta_id=delta.observation_delta_id,
            source_id=delta.source_id,
            source_digest=delta.source_digest,
            segment_governance_bindings=delta.segment_governance_bindings,
            message_admission_identities=delta.message_admission_identities,
            governance_carrier_artifact=delta.governance_carrier_artifact,
            operation_fence_id=delta.operation_fence_id,
            transaction_group_id=delta.transaction_group_id,
            operation_ids=delta.operation_ids,
            terminal_status=delta.terminal_status,
            graph_revision_delta_digest=delta.graph_revision_delta_digest,
            observation_schema_fingerprint=delta.observation_schema_fingerprint,
            record_mutations=delta.record_mutations,
        )


class ObservationSourceSemanticPayload(_ClosedModel):
    """Exact source-finalization delta fields other than revision and delta digest."""

    kind: Literal["source_finalization"]
    observation_delta_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    delivery_principal_binding_digest: str = Field(pattern=_DIGEST)
    delivery_key_digest: str = Field(pattern=_DIGEST)
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    required_outcome_scopes: RequiredOutcomeScopeSet
    operation_fence_id: str = Field(min_length=1)
    operation_ids: tuple[_IDENTIFIER, ...]
    source_outcome: CanonicalSourceTerminalOutcomeRecord
    observation_schema_fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def validate_payload_shape(self) -> ObservationSourceSemanticPayload:
        outcome = self.source_outcome
        if (
            self.source_id != outcome.source_id
            or self.source_digest != outcome.source_digest
            or self.delivery_principal_binding_digest != outcome.delivery_principal_binding_digest
            or self.delivery_key_digest != outcome.delivery_key_digest
            or self.segment_governance_carriers != outcome.segment_governance_carriers
            or self.message_admission_carriers != outcome.message_admission_carriers
            or self.governance_carrier_artifact != outcome.governance_carrier_artifact
            or self.required_outcome_scopes != outcome.required_outcome_scopes
            or self.operation_fence_id != outcome.operation_fence_id
            or self.operation_ids != outcome.operation_ids
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
        ):
            raise ValueError("source-finalization semantic payload shape is invalid")
        return self

    @classmethod
    def from_delta(cls, delta: SourceFinalizationObservationDelta) -> Self:
        """Project a validated native delta without its ledger-assigned fields."""
        return cls(
            kind=delta.kind,
            observation_delta_id=delta.observation_delta_id,
            source_id=delta.source_id,
            source_digest=delta.source_digest,
            delivery_principal_binding_digest=delta.delivery_principal_binding_digest,
            delivery_key_digest=delta.delivery_key_digest,
            segment_governance_carriers=delta.segment_governance_carriers,
            message_admission_carriers=delta.message_admission_carriers,
            governance_carrier_artifact=delta.governance_carrier_artifact,
            required_outcome_scopes=delta.required_outcome_scopes,
            operation_fence_id=delta.operation_fence_id,
            operation_ids=delta.operation_ids,
            source_outcome=delta.source_outcome,
            observation_schema_fingerprint=delta.observation_schema_fingerprint,
        )


ObservationLedgerSemanticPayload: TypeAlias = Annotated[
    ObservationGroupSemanticPayload | ObservationSourceSemanticPayload,
    Field(discriminator="kind"),
]


class ObservationLedgerEntry(_ClosedModel):
    schema_version: Literal[1]
    repository_id: str = Field(min_length=1)
    activation_digest: str = Field(pattern=_DIGEST)
    sequence: int = Field(ge=1)
    previous_entry_digest: str | None = Field(..., pattern=_DIGEST)
    semantic_payload_digest: str = Field(pattern=_DIGEST)
    delta: CanonicalIngestionObservationDelta
    result_locator: ObservationResultLocator
    result_digest: str = Field(pattern=_DIGEST)
    entry_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def validate_entry_shape(self) -> ObservationLedgerEntry:
        if (self.sequence == 1) != (self.previous_entry_digest is None):
            raise ValueError("observation ledger entry predecessor shape is invalid")
        if isinstance(self.delta, IngestionObservationDelta):
            if not isinstance(self.result_locator, ObservationGroupResultLocator):
                raise ValueError("terminal-group delta requires a group result locator")
            if (
                self.delta.source_id != self.result_locator.source_id
                or self.delta.source_digest != self.result_locator.source_digest
                or self.delta.operation_fence_id != self.result_locator.operation_fence_id
                or self.delta.transaction_group_id != self.result_locator.transaction_group_id
                or self.delta.operation_ids != self.result_locator.operation_ids
            ):
                raise ValueError("terminal-group result locator coordinates are substituted")
        elif isinstance(self.delta, SourceFinalizationObservationDelta):
            if not isinstance(self.result_locator, ObservationSourceResultLocator):
                raise ValueError("source-finalization delta requires a source result locator")
            if (
                self.delta.source_id != self.result_locator.source_id
                or self.delta.source_digest != self.result_locator.source_digest
                or self.delta.operation_fence_id != self.result_locator.operation_fence_id
            ):
                raise ValueError("source-finalization result locator coordinates are substituted")
        else:  # pragma: no cover - the discriminated native union is exhaustive
            raise ValueError("unknown observation ledger delta")
        return self


class SourceObservationIntent(_ClosedModel):
    kind: Literal["source_finalization"]
    source_outcome: CanonicalSourceTerminalOutcomeRecord
    observation_schema_fingerprint: str = Field(pattern=_DIGEST)
    intent_digest: str = Field(pattern=_DIGEST)


class ObservationLedgerActivation(_ClosedModel):
    schema_version: Literal[1]
    repository_id: str = Field(min_length=1)
    previous_writer_admission_digest: str = Field(pattern=_DIGEST)
    target_writer_epoch: int = Field(ge=1)
    writer_implementation_fingerprint: str = Field(pattern=_DIGEST)
    observation_schema_fingerprint: str = Field(pattern=_DIGEST)
    ledger_codec_fingerprint: str = Field(pattern=_DIGEST)
    legacy_terminal_inventory_digest: str = Field(pattern=_DIGEST)
    activation_digest: str = Field(pattern=_DIGEST)


__all__ = [
    "ObservationGroupResultLocator",
    "ObservationGroupSemanticPayload",
    "ObservationLedgerActivation",
    "ObservationLedgerEntry",
    "ObservationLedgerHead",
    "ObservationLedgerSemanticPayload",
    "ObservationResultLocator",
    "ObservationSourceResultLocator",
    "ObservationSourceSemanticPayload",
    "SourceObservationIntent",
]
