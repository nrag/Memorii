"""Closed profile-3 ingestion observation payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from memorii.core.memory_evolution.graph_observation_records import (
    Digest,
    Identifier,
    ObservedEntityReference,
)
from memorii.core.semantic_ingestion.contracts import (
    GovernanceCarrierArtifact,
    MessageAdmissionIdentity,
    OperationTemporalDecisionBinding,
    SegmentGovernanceBinding,
    SourceSpanReference,
)


class _ClosedIngestionObservationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ObservedSourceIntroduction(_ClosedIngestionObservationPayload):
    introduction_id: Identifier
    source_id: Identifier
    source_digest: Digest
    delivery_principal_binding_digest: Digest
    delivery_key_digest: Digest
    segment_governance: SegmentGovernanceBinding
    message_admission_identity: MessageAdmissionIdentity | None
    governance_carrier_artifact: GovernanceCarrierArtifact
    mention_span: SourceSpanReference
    entity: ObservedEntityReference
    independently_asserted_type_evidence_ids: tuple[Identifier, ...]
    operation_id: Identifier
    operation_fence_id: Identifier
    boundary: bool
    record_digest: Digest

    @model_validator(mode="after")
    def _validate_coordinates(self) -> ObservedSourceIntroduction:
        artifact = self.governance_carrier_artifact
        admission = self.message_admission_identity
        if (
            self.segment_governance.source_id != self.source_id
            or self.mention_span.source_id != self.source_id
            or artifact.segment_governance.source_id != self.source_id
            or artifact.message_admissions.source_id != self.source_id
            or self.segment_governance not in artifact.segment_governance.bindings
            or (
                admission is not None
                and (
                    admission not in artifact.message_admissions.identities
                    or admission.segment_governance_binding_digest
                    != self.segment_governance.binding_digest
                    or admission.delivery_principal_binding_digest
                    != self.delivery_principal_binding_digest
                )
            )
            or self.independently_asserted_type_evidence_ids
            != tuple(sorted(set(self.independently_asserted_type_evidence_ids)))
        ):
            raise ValueError("observed source introduction coordinates mismatch")
        return self


class _ObservedOperationCoordinates(_ClosedIngestionObservationPayload):
    operation_id: Identifier
    source_id: Identifier
    source_digest: Digest
    delivery_principal_binding_digest: Digest
    delivery_key_digest: Digest
    segment_governance_binding_digests: tuple[Digest, ...]
    message_admission_key_digests: tuple[Digest, ...]
    governance_carrier_artifact: GovernanceCarrierArtifact
    operation_fence_id: Identifier
    transaction_group_id: Identifier

    def _validate_governance_coordinates(self) -> None:
        artifact = self.governance_carrier_artifact
        binding_digests = tuple(item.binding_digest for item in artifact.segment_governance.bindings)
        admissions = {
            item.message_admission_key_digest: item for item in artifact.message_admissions.identities
        }
        if (
            artifact.segment_governance.source_id != self.source_id
            or artifact.message_admissions.source_id != self.source_id
            or self.segment_governance_binding_digests
            != tuple(sorted(set(self.segment_governance_binding_digests)))
            or self.message_admission_key_digests
            != tuple(sorted(set(self.message_admission_key_digests)))
            or not set(self.segment_governance_binding_digests).issubset(binding_digests)
            or not set(self.message_admission_key_digests).issubset(admissions)
            or any(
                admissions[key].segment_governance_binding_digest
                not in self.segment_governance_binding_digests
                for key in self.message_admission_key_digests
            )
        ):
            raise ValueError("observed operation governance coordinates mismatch")


class ObservedOperationIntroduction(_ObservedOperationCoordinates):
    introduction_id: Identifier
    operation_kind: str
    predicate_id: Identifier | None
    owned_source_spans: tuple[SourceSpanReference, ...]
    boundary: bool
    record_digest: Digest

    @model_validator(mode="after")
    def _validate_coordinates(self) -> ObservedOperationIntroduction:
        self._validate_governance_coordinates()
        if any(span.source_id != self.source_id for span in self.owned_source_spans):
            raise ValueError("observed operation introduction source span mismatch")
        return self


class ObservedOperationTerminalOutcome(_ObservedOperationCoordinates):
    outcome_id: Identifier
    final_status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"]
    graph_revision_delta_digest: Digest | None
    temporal_decision_bindings: tuple[OperationTemporalDecisionBinding, ...]
    reason_codes: tuple[str, ...]
    record_digest: Digest

    @model_validator(mode="after")
    def _validate_coordinates(self) -> ObservedOperationTerminalOutcome:
        self._validate_governance_coordinates()
        if (
            any(item.operation_id != self.operation_id for item in self.temporal_decision_bindings)
            or len({item.binding_digest for item in self.temporal_decision_bindings})
            != len(self.temporal_decision_bindings)
            or (self.final_status == "committed") != (self.graph_revision_delta_digest is not None)
        ):
            raise ValueError("observed operation terminal outcome coordinates mismatch")
        return self


class ObservedSourceTerminalOutcome(_ClosedIngestionObservationPayload):
    outcome_id: Identifier
    source_id: Identifier
    source_digest: Digest
    delivery_principal_binding_digest: Digest
    delivery_key_digest: Digest
    segment_governance_carrier_set_digest: Digest
    message_admission_carrier_set_digest: Digest
    required_outcome_scope_set_digest: Digest
    governance_carrier_artifact: GovernanceCarrierArtifact
    operation_fence_id: Identifier
    operation_ids: tuple[Identifier, ...]
    final_status: Literal[
        "fully_committed", "partially_committed", "evidence_only", "rejected", "unresolved", "failed"
    ]
    group_result_digests: tuple[Digest, ...]
    source_result_digest: Digest
    record_digest: Digest

    @model_validator(mode="after")
    def _validate_coordinates(self) -> ObservedSourceTerminalOutcome:
        artifact = self.governance_carrier_artifact
        if (
            artifact.segment_governance.source_id != self.source_id
            or artifact.message_admissions.source_id != self.source_id
            or self.segment_governance_carrier_set_digest
            != artifact.segment_governance.carrier_set_digest
            or self.message_admission_carrier_set_digest
            != artifact.message_admissions.carrier_set_digest
            or self.required_outcome_scope_set_digest
            != artifact.required_outcome_scopes.required_scope_set_digest
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            or (bool(self.group_result_digests) and len(set(self.group_result_digests)) != len(self.group_result_digests))
        ):
            raise ValueError("observed source terminal outcome coordinates mismatch")
        return self


class ObservedSourceOutcomeConsistencyAssessment(_ClosedIngestionObservationPayload):
    source_id: Identifier
    delivery_principal_binding_digest: Digest
    delivery_key_digest: Digest
    governance_carrier_artifact_digest: Digest
    required_outcome_scope_set_digest: Digest
    source_outcome_record_digest: Digest
    source_result_digest: Digest
    operation_set_digest: Digest
    group_result_set_digest: Digest
    operation_fence_partition_digest: Digest
    observation_delta_set_digest: Digest
    status: Literal["consistent", "inconsistent"]
    reason_codes: tuple[str, ...]
    assessment_digest: Digest


__all__ = [
    "ObservedOperationIntroduction", "ObservedOperationTerminalOutcome",
    "ObservedSourceIntroduction", "ObservedSourceOutcomeConsistencyAssessment",
    "ObservedSourceTerminalOutcome",
]
