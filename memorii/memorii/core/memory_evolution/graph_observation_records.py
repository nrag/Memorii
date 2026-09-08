"""Closed profile-3 structural payloads for graph observation.

The protected observation body decoder owns profile-bound record-digest
verification.  These models deliberately validate payload shape and preserve
the native validators of every embedded authority; they do not implement a
second digest algorithm or a retrieval route.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_records import GraphRecordKind
from memorii.core.memory_evolution.semantic_state import (
    ActiveTemporalProjectionPointer,
    ActiveTrustProjectionPointer,
    SemanticAssertionKey,
    SemanticClaimSlotKey,
    TemporalProjectionRecord,
    TrustProjectionRecord,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.semantic_ingestion.contracts import (
    AcceptedTemporalEvidence,
    AuthenticatedSourceIntervalEvidence,
    OperationTemporalDecisionBinding,
    SourceSpanReference,
    TemporalReferenceEvidence,
    TypedLiteral,
)


class _ClosedObservationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1)]


class ObservedEntityReference(_ClosedObservationPayload):
    entity_revision_id: Identifier
    logical_entity_id: Identifier
    reference_path: Identifier


class ObservedAssertionEntityReference(_ClosedObservationPayload):
    entity: ObservedEntityReference
    logical_entity_id_at_assertion: Identifier


class ObservedEntityRevision(_ClosedObservationPayload):
    entity_revision_id: Identifier
    logical_entity_id: Identifier
    canonical_type: str | None
    lifecycle_state: str
    valid_interval: TimeInterval | None
    system_interval: TimeInterval
    source_ids: tuple[Identifier, ...]
    operation_ids: tuple[Identifier, ...]
    boundary: bool
    record_digest: Digest


class ObservedAliasRevision(_ClosedObservationPayload):
    alias_revision_id: Identifier
    entity: ObservedEntityReference
    alias_namespace: str
    normalized_alias_key: str
    binding_evidence_ids: tuple[Identifier, ...]
    valid_interval: TimeInterval | None
    system_interval: TimeInterval
    source_ids: tuple[Identifier, ...]
    boundary: bool
    record_digest: Digest


class ObservedTypeEvidence(_ClosedObservationPayload):
    evidence_id: Identifier
    entity: ObservedEntityReference
    asserted_type: str
    origin: str
    source_evidence: tuple[SourceSpanReference, ...]
    proof_ancestry_ids: tuple[Identifier, ...]
    proof_policy_fingerprint: str
    valid_interval: TimeInterval | None
    system_interval: TimeInterval
    boundary: bool
    record_digest: Digest


class ObservedClaimAssertion(_ClosedObservationPayload):
    claim_assertion_id: Identifier
    subject_assertion_ref: ObservedAssertionEntityReference
    object_assertion_ref: ObservedAssertionEntityReference | None
    assertion_key_at_recording: SemanticAssertionKey
    predicate_id: Identifier
    literal_value: TypedLiteral | None
    polarity: str
    commitment: str
    scope_identity: Identifier
    valid_interval: TimeInterval | None
    temporal_reference_evidence: TemporalReferenceEvidence | None
    authenticated_source_interval_evidence: AuthenticatedSourceIntervalEvidence | None
    temporal_decision_binding: OperationTemporalDecisionBinding
    system_interval: TimeInterval
    source_authority_class: str
    source_ids: tuple[Identifier, ...]
    operation_ids: tuple[Identifier, ...]
    citation_ids: tuple[Identifier, ...]
    provenance_ids: tuple[Identifier, ...]
    policy_fingerprints: tuple[str, ...]
    boundary: bool
    record_digest: Digest


class ObservedTemporalClaimProjection(_ClosedObservationPayload):
    observation_id: Identifier
    projection: TemporalProjectionRecord
    generation_digest: Digest
    publication_pointer: ActiveTemporalProjectionPointer
    successor_publication_pointer: ActiveTemporalProjectionPointer | None
    boundary: bool
    record_digest: Digest

    @model_validator(mode="after")
    def _validate_native_pointer_binding(self) -> ObservedTemporalClaimProjection:
        successor = self.successor_publication_pointer
        if (
            self.generation_digest != self.publication_pointer.generation_digest
            or self.projection.repository_id != self.publication_pointer.repository_id
            or (
                successor is not None
                and (
                    successor.repository_id != self.publication_pointer.repository_id
                    or successor.pointer_revision != self.publication_pointer.pointer_revision + 1
                    or successor.publication_sequence
                    != self.publication_pointer.publication_sequence + 1
                    or successor.predecessor_pointer_digest
                    != self.publication_pointer.pointer_digest
                )
            )
        ):
            raise ValueError("temporal observation projection pointer binding mismatch")
        return self


class ObservedTrustClaimProjection(_ClosedObservationPayload):
    observation_id: Identifier
    projection: TrustProjectionRecord
    generation_digest: Digest
    publication_pointer: ActiveTrustProjectionPointer
    successor_publication_pointer: ActiveTrustProjectionPointer | None
    boundary: bool
    record_digest: Digest

    @model_validator(mode="after")
    def _validate_native_pointer_binding(self) -> ObservedTrustClaimProjection:
        successor = self.successor_publication_pointer
        if (
            self.generation_digest != self.publication_pointer.generation_digest
            or self.projection.repository_id != self.publication_pointer.repository_id
            or (
                successor is not None
                and (
                    successor.repository_id != self.publication_pointer.repository_id
                    or successor.pointer_revision != self.publication_pointer.pointer_revision + 1
                    or successor.publication_sequence
                    != self.publication_pointer.publication_sequence + 1
                    or successor.predecessor_pointer_digest
                    != self.publication_pointer.pointer_digest
                )
            )
        ):
            raise ValueError("trust observation projection pointer binding mismatch")
        return self


class ObservedRelation(_ClosedObservationPayload):
    relation_id: Identifier
    predicate_id: Identifier
    subject: ObservedEntityReference
    object_kind: Literal["entity", "literal"]
    object_entity: ObservedEntityReference | None
    literal_value: TypedLiteral | None
    supporting_claim_assertion_ids: tuple[Identifier, ...]
    lifecycle_state: str
    valid_interval: TimeInterval | None
    system_interval: TimeInterval
    source_ids: tuple[Identifier, ...]
    provenance_ids: tuple[Identifier, ...]
    boundary: bool
    record_digest: Digest

    @model_validator(mode="after")
    def _validate_object_shape(self) -> ObservedRelation:
        entity_shape = self.object_entity is not None and self.literal_value is None
        literal_shape = self.object_entity is None and self.literal_value is not None
        if (self.object_kind == "entity" and not entity_shape) or (
            self.object_kind == "literal" and not literal_shape
        ):
            raise ValueError("observed relation object does not match object kind")
        return self


class ObservedActionRoleBinding(_ClosedObservationPayload):
    role_id: Identifier
    endpoint_kind: Literal["actor", "object"]
    entities: tuple[ObservedEntityReference, ...]


class ObservedActionRevision(_ClosedObservationPayload):
    action_revision_id: Identifier
    logical_action_id: Identifier
    role_bindings: tuple[ObservedActionRoleBinding, ...]
    action_state: str
    execution_branch_id: str | None
    transition_rule_id: Identifier
    transition_applicability_key_digest: Digest
    supporting_claim_assertion_ids: tuple[Identifier, ...]
    valid_interval: TimeInterval | None
    authenticated_source_interval_evidence: AuthenticatedSourceIntervalEvidence | None
    temporal_decision_binding: OperationTemporalDecisionBinding
    system_interval: TimeInterval
    source_ids: tuple[Identifier, ...]
    provenance_ids: tuple[Identifier, ...]
    boundary: bool
    record_digest: Digest


class ObservedCitationRecord(_ClosedObservationPayload):
    citation_id: Identifier
    cited_record_kind: GraphRecordKind
    cited_record_id: Identifier
    source_id: Identifier
    source_span: SourceSpanReference
    source_digest: Digest
    boundary: bool
    record_digest: Digest


class ObservedProvenanceRecord(_ClosedObservationPayload):
    provenance_id: Identifier
    record_kind: GraphRecordKind
    record_id: Identifier
    source_ids: tuple[Identifier, ...]
    operation_ids: tuple[Identifier, ...]
    proof_ancestry_ids: tuple[Identifier, ...]
    policy_fingerprints: tuple[str, ...]
    system_interval: TimeInterval
    boundary: bool
    record_digest: Digest


class ObservedCertifiedTextEffectiveTime(_ClosedObservationPayload):
    kind: Literal["certified_text_time"]
    effective_at: datetime
    evidence_spans: tuple[SourceSpanReference, ...]
    temporal_policy_fingerprint: str


class ObservedAuthenticatedReferenceEffectiveTime(_ClosedObservationPayload):
    kind: Literal["authenticated_reference_time"]
    effective_at: datetime
    reference_evidence: TemporalReferenceEvidence
    temporal_policy_fingerprint: str


class ObservedSystemRecordedEffectiveTime(_ClosedObservationPayload):
    kind: Literal["system_recorded_only"]
    temporal_policy_fingerprint: str


ObservedEffectiveTimeCoordinate: TypeAlias = Annotated[
    ObservedCertifiedTextEffectiveTime
    | ObservedAuthenticatedReferenceEffectiveTime
    | ObservedSystemRecordedEffectiveTime,
    Field(discriminator="kind"),
]


class ObservedTemporalTransition(_ClosedObservationPayload):
    transition_id: Identifier
    operation_id: Identifier
    claim_slot_key: SemanticClaimSlotKey
    compared_claim_ids: tuple[Identifier, ...]
    previous_projection_claim_ids: tuple[Identifier, ...]
    next_projection_claim_ids: tuple[Identifier, ...]
    transition_kind: Literal["correction", "retraction"]
    effective_time: ObservedEffectiveTimeCoordinate
    transition_temporal_evidence: AcceptedTemporalEvidence
    transition_temporal_decision_binding: OperationTemporalDecisionBinding
    system_interval: TimeInterval
    source_ids: tuple[Identifier, ...]
    provenance_ids: tuple[Identifier, ...]
    boundary: bool
    record_digest: Digest


class ObservedIdentityTransition(_ClosedObservationPayload):
    transition_id: Identifier
    operation: Literal["alias", "rekey", "merge", "split"]
    predecessor_entities: tuple[ObservedEntityReference, ...]
    successor_entities: tuple[ObservedEntityReference, ...]
    effective_time: ObservedEffectiveTimeCoordinate
    transition_temporal_evidence: AcceptedTemporalEvidence
    transition_temporal_decision_binding: OperationTemporalDecisionBinding
    system_interval: TimeInterval
    source_evidence: tuple[SourceSpanReference, ...]
    operation_id: Identifier
    boundary: bool
    record_digest: Digest


class ObservedReferenceDisposition(_ClosedObservationPayload):
    disposition_id: Identifier
    transition_id: Identifier
    record_kind: GraphRecordKind
    record_id: Identifier
    reference_path: Identifier
    predecessor_entity: ObservedEntityReference
    successor_entities: tuple[ObservedEntityReference, ...]
    disposition: str
    evidence_ids: tuple[Identifier, ...]
    system_interval: TimeInterval
    boundary: bool
    record_digest: Digest


__all__ = [
    "Digest", "Identifier", "ObservedActionRevision", "ObservedActionRoleBinding",
    "ObservedAliasRevision", "ObservedAssertionEntityReference",
    "ObservedAuthenticatedReferenceEffectiveTime", "ObservedCertifiedTextEffectiveTime",
    "ObservedCitationRecord", "ObservedClaimAssertion", "ObservedEffectiveTimeCoordinate", "ObservedEntityReference",
    "ObservedEntityRevision", "ObservedIdentityTransition", "ObservedProvenanceRecord",
    "ObservedReferenceDisposition", "ObservedRelation", "ObservedSystemRecordedEffectiveTime",
    "ObservedTemporalClaimProjection", "ObservedTemporalTransition", "ObservedTrustClaimProjection",
    "ObservedTypeEvidence",
]
