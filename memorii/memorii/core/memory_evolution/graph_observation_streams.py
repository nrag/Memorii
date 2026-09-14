"""Explicit closed profile-3 graph-observation stream variants."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_ingestion_observation_records import (
    ObservedOperationIntroduction,
    ObservedOperationTerminalOutcome,
    ObservedSourceIntroduction,
    ObservedSourceTerminalOutcome,
)
from memorii.core.memory_evolution.graph_observation_records import (
    Digest,
    Identifier,
    ObservedActionRevision,
    ObservedAliasRevision,
    ObservedCitationRecord,
    ObservedClaimAssertion,
    ObservedEntityRevision,
    ObservedIdentityTransition,
    ObservedProvenanceRecord,
    ObservedReferenceDisposition,
    ObservedRelation,
    ObservedTemporalClaimProjection,
    ObservedTemporalTransition,
    ObservedTrustClaimProjection,
    ObservedTypeEvidence,
)


class _ClosedStreamRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class EntityRevisionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["entity_revision"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedEntityRevision

    @model_validator(mode="after")
    def _validate_closure(self) -> EntityRevisionStreamRecord:
        if self.primary_key != self.payload.entity_revision_id or self.record_digest != self.payload.record_digest:
            raise ValueError("entity revision stream record closure mismatch")
        return self


class AliasRevisionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["alias_revision"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedAliasRevision

    @model_validator(mode="after")
    def _validate_closure(self) -> AliasRevisionStreamRecord:
        if self.primary_key != self.payload.alias_revision_id or self.record_digest != self.payload.record_digest:
            raise ValueError("alias revision stream record closure mismatch")
        return self


class TypeEvidenceStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["type_evidence"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedTypeEvidence

    @model_validator(mode="after")
    def _validate_closure(self) -> TypeEvidenceStreamRecord:
        if self.primary_key != self.payload.evidence_id or self.record_digest != self.payload.record_digest:
            raise ValueError("type evidence stream record closure mismatch")
        return self


class ClaimAssertionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["claim_assertion"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedClaimAssertion

    @model_validator(mode="after")
    def _validate_closure(self) -> ClaimAssertionStreamRecord:
        if self.primary_key != self.payload.claim_assertion_id or self.record_digest != self.payload.record_digest:
            raise ValueError("claim assertion stream record closure mismatch")
        return self


class TemporalClaimProjectionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["temporal_claim_projection"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedTemporalClaimProjection

    @model_validator(mode="after")
    def _validate_closure(self) -> TemporalClaimProjectionStreamRecord:
        if self.primary_key != self.payload.observation_id or self.record_digest != self.payload.record_digest:
            raise ValueError("temporal projection stream record closure mismatch")
        return self


class TrustClaimProjectionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["trust_claim_projection"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedTrustClaimProjection

    @model_validator(mode="after")
    def _validate_closure(self) -> TrustClaimProjectionStreamRecord:
        if self.primary_key != self.payload.observation_id or self.record_digest != self.payload.record_digest:
            raise ValueError("trust projection stream record closure mismatch")
        return self


class RelationStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["relation"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedRelation

    @model_validator(mode="after")
    def _validate_closure(self) -> RelationStreamRecord:
        if self.primary_key != self.payload.relation_id or self.record_digest != self.payload.record_digest:
            raise ValueError("relation stream record closure mismatch")
        return self


class ActionRevisionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["action_revision"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedActionRevision

    @model_validator(mode="after")
    def _validate_closure(self) -> ActionRevisionStreamRecord:
        if self.primary_key != self.payload.action_revision_id or self.record_digest != self.payload.record_digest:
            raise ValueError("action revision stream record closure mismatch")
        return self


class CitationStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["citation"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedCitationRecord

    @model_validator(mode="after")
    def _validate_closure(self) -> CitationStreamRecord:
        if self.primary_key != self.payload.citation_id or self.record_digest != self.payload.record_digest:
            raise ValueError("citation stream record closure mismatch")
        return self


class ProvenanceStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["provenance"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedProvenanceRecord

    @model_validator(mode="after")
    def _validate_closure(self) -> ProvenanceStreamRecord:
        if self.primary_key != self.payload.provenance_id or self.record_digest != self.payload.record_digest:
            raise ValueError("provenance stream record closure mismatch")
        return self


class TemporalTransitionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["temporal_transition"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedTemporalTransition

    @model_validator(mode="after")
    def _validate_closure(self) -> TemporalTransitionStreamRecord:
        if self.primary_key != self.payload.transition_id or self.record_digest != self.payload.record_digest:
            raise ValueError("temporal transition stream record closure mismatch")
        return self


class IdentityTransitionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["identity_transition"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedIdentityTransition

    @model_validator(mode="after")
    def _validate_closure(self) -> IdentityTransitionStreamRecord:
        if self.primary_key != self.payload.transition_id or self.record_digest != self.payload.record_digest:
            raise ValueError("identity transition stream record closure mismatch")
        return self


class ReferenceDispositionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["reference_disposition"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedReferenceDisposition

    @model_validator(mode="after")
    def _validate_closure(self) -> ReferenceDispositionStreamRecord:
        if self.primary_key != self.payload.disposition_id or self.record_digest != self.payload.record_digest:
            raise ValueError("reference disposition stream record closure mismatch")
        return self


class SourceIntroductionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["source_introduction"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedSourceIntroduction

    @model_validator(mode="after")
    def _validate_closure(self) -> SourceIntroductionStreamRecord:
        if self.primary_key != self.payload.introduction_id or self.record_digest != self.payload.record_digest:
            raise ValueError("source introduction stream record closure mismatch")
        return self


class OperationIntroductionStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["operation_introduction"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedOperationIntroduction

    @model_validator(mode="after")
    def _validate_closure(self) -> OperationIntroductionStreamRecord:
        if self.primary_key != self.payload.introduction_id or self.record_digest != self.payload.record_digest:
            raise ValueError("operation introduction stream record closure mismatch")
        return self


class OperationTerminalOutcomeStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["operation_terminal_outcome"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedOperationTerminalOutcome

    @model_validator(mode="after")
    def _validate_closure(self) -> OperationTerminalOutcomeStreamRecord:
        if self.primary_key != self.payload.outcome_id or self.record_digest != self.payload.record_digest:
            raise ValueError("operation terminal outcome stream record closure mismatch")
        return self


class SourceTerminalOutcomeStreamRecord(_ClosedStreamRecord):
    record_kind: Literal["source_terminal_outcome"]
    primary_key: Identifier
    record_digest: Digest
    payload: ObservedSourceTerminalOutcome

    @model_validator(mode="after")
    def _validate_closure(self) -> SourceTerminalOutcomeStreamRecord:
        if self.primary_key != self.payload.outcome_id or self.record_digest != self.payload.record_digest:
            raise ValueError("source terminal outcome stream record closure mismatch")
        return self


GraphObservationStreamRecord: TypeAlias = Annotated[
    EntityRevisionStreamRecord
    | AliasRevisionStreamRecord
    | TypeEvidenceStreamRecord
    | ClaimAssertionStreamRecord
    | TemporalClaimProjectionStreamRecord
    | TrustClaimProjectionStreamRecord
    | RelationStreamRecord
    | ActionRevisionStreamRecord
    | CitationStreamRecord
    | ProvenanceStreamRecord
    | TemporalTransitionStreamRecord
    | IdentityTransitionStreamRecord
    | ReferenceDispositionStreamRecord
    | SourceIntroductionStreamRecord
    | OperationIntroductionStreamRecord
    | OperationTerminalOutcomeStreamRecord
    | SourceTerminalOutcomeStreamRecord,
    Field(discriminator="record_kind"),
]


__all__ = [
    "ActionRevisionStreamRecord", "AliasRevisionStreamRecord", "CitationStreamRecord",
    "ClaimAssertionStreamRecord", "EntityRevisionStreamRecord", "GraphObservationStreamRecord",
    "IdentityTransitionStreamRecord", "OperationIntroductionStreamRecord",
    "OperationTerminalOutcomeStreamRecord", "ProvenanceStreamRecord",
    "ReferenceDispositionStreamRecord", "RelationStreamRecord", "SourceIntroductionStreamRecord",
    "SourceTerminalOutcomeStreamRecord", "TemporalClaimProjectionStreamRecord",
    "TemporalTransitionStreamRecord", "TrustClaimProjectionStreamRecord", "TypeEvidenceStreamRecord",
]
