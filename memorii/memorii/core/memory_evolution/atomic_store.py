"""Atomic, evidence-only writer-safe preplanning admission-to-preplanning persistence."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_hex
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.admission import (
    PreparedSourceAdmission,
    SourceAdmissionAccepted,
    source_admission_source_bytes,
    source_admission_source_digest,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapAdmissionPin,
    BootstrapAuthenticatedLanguageEvidence,
    BootstrapSegmentGrammarProof,
    CurrentBootstrapReleaseAssertion,
    CurrentBootstrapReleaseVerifier,
    HostVerifiedBootstrapReleaseEvidence,
)
from memorii.core.memory_evolution.conflict_attention import (
    ActiveSemanticConflict,
    ClarificationFailureClass,
    ClarificationSubmissionOutcome,
    ConflictAttention,
    ConflictAudience,
    ConflictClarificationAttempt,
    ConflictClarificationClaim,
    ConflictClarificationOperationReceipt,
    ConflictClarificationProcessingReceipt,
    ConflictClarificationSubmissionResult,
    ConflictClarificationWork,
    ConflictKind,
    ConflictResolutionRequest,
    ConflictStatus,
    SemanticConflictAuthorityCommitInput,
    SemanticConflictClarificationCasInput,
    SemanticConflictClarificationSubmissionGeneration,
    SemanticConflictClarificationTransition,
    SemanticConflictClarificationTransitionReason,
    SemanticConflictClarificationWorkGeneration,
    SemanticConflictReplayBinding,
    VerifiedUserConfirmation,
    conflict_clarification_processing_operation_id,
    decode_persisted_conflict_generation,
    verified_user_confirmation_digest,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    OperationFenceBinding,
    SemanticWriterCommitBinding,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.source_admission import DeliveryAuthorizationRequest
from memorii.core.memory_evolution.source_governance import require_complete_scope_authorization
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    SemanticWriterWriteAuthorization,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord, MemoryRecordFence
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    CheckpointSignatureAuthority,
    MemoryPlanePrecondition,
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    RecordFencePrecondition,
    record_digest,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility, TemporalValidityStatus

if TYPE_CHECKING:
    from memorii.core.memory_evolution.conflict_attention import (
        ActiveSemanticConflict,
        AgentClarificationProposal,
        ConflictClarificationAttemptResult,
        ConflictClarificationProcessingReceipt,
        RetainedConflictClarificationContext,
        SemanticConflictAuthorityResolver,
        SemanticConflictClarificationTransition,
    )
    from memorii.core.memory_evolution.policy_migration import (
        PolicyMigrationRepository,
        PreparedPolicyMigrationProgress,
        PreparedTemporalPolicyMigration,
        PreparedTrustPolicyMigration,
        TemporalMigrationCatchUpEntry,
        TemporalMigrationResult,
        TemporalPolicyMigrationPlan,
        TrustMigrationCatchUpEntry,
        TrustMigrationResult,
        TrustPolicyMigrationPlan,
    )
    from memorii.core.memory_evolution.projection_binding import (
        ProjectionHistoryReplayBinding,
    )
    from memorii.core.memory_evolution.projection_history import (
        ProjectionHistoryRepository,
    )
    from memorii.core.memory_evolution.projection_scheduler import (
        PreparedTrustDecayPublication,
        ProjectionScheduler,
    )
    from memorii.core.semantic_ingestion.canonical_evidence_arena import CanonicalEvidenceLease
    from memorii.core.semantic_ingestion.contracts import (
        SemanticArbitrationPolicyBundle,
        SemanticArtifactClosure,
        SemanticGraphDelta,
        SemanticObservationDelta,
        SemanticTerminalOutcome,
        TemporalPolicySnapshot,
        TrustPolicySnapshot,
    )
    from memorii.core.semantic_ingestion.event_replay import (
        ReplayCheckpointResumeAuthority,
        ReplayIntegrityLinearizer,
        SemanticEventSchemaRegistry,
        SemanticEventSchemaRegistryHistory,
        SemanticMemoryEventBatch,
        SemanticReplayAuthorityAggregate,
        SemanticReplayState,
    )

_SEMANTIC_EVENT_REPOSITORY_ID = "semantic_ingestion"
_SEMANTIC_CHECKPOINT_SIGNATURE_OWNER = object()
_SEMANTIC_INTEGRITY_GENERATION_DOMAIN = b"memorii.semantic-ingestion.atomic-integrity-generation.v1\0"
_SEMANTIC_CLEAN_GENERATION_DOMAIN = b"memorii.semantic-ingestion.atomic-clean-generation.v1\0"
_CLARIFICATION_RECOVERY_BINDING_DOMAIN = b"memorii.semantic-ingestion.clarification-recovery-binding.v1\0"


class PreplanningStoreError(ValueError):
    pass


class PreplanningOperationMismatchError(PreplanningStoreError):
    """The operation id is retained for a different exact request."""

    pass


class _BootstrapAuthorityUnavailableAtCommit(PreplanningStoreError):
    """The host rejected the final, transaction-linearized release check."""

    pass


class IdentityPlanningMigrationRequiredError(PreplanningStoreError):
    """An accepted-only identity artifact cannot be upgraded without authority."""

    pass


class IdentityPlanningStaleSnapshotError(PreplanningStoreError):
    """The exact graph authority changed before frozen-plan publication."""

    pass


@dataclass(frozen=True)
class _ValidatedTerminalGroupClosure:
    terminal: SemanticTerminalOutcome
    artifact_closure: SemanticArtifactClosure
    observation: SemanticObservationDelta
    graph_delta: SemanticGraphDelta | None
    event_batch: SemanticMemoryEventBatch | None


@dataclass(frozen=True)
class _RetainedPlannedTerminalClosure:
    terminal: SemanticTerminalOutcome
    artifact_closure: SemanticArtifactClosure
    terminal_bytes: bytes
    artifact_closure_bytes: bytes


class PreplanningLease(BaseModel):
    owner_id: str = Field(min_length=1)
    execution_token: str = Field(min_length=1)
    ownership_epoch: int = Field(ge=1)
    acquired_at: datetime
    expires_at: datetime
    renewal_interval: timedelta

    model_config = ConfigDict(extra="forbid", frozen=True)


class PreplanningOperationControl(BaseModel):
    operation_fence: OperationFenceBinding
    # New operations use the immutable fence namespace.  A missing value is a
    # pre-remediation raw-operation-ID family and is resolved on load.
    persistence_namespace_id: str | None = None
    writer_binding: SemanticWriterCommitBinding
    state: Literal["preplanning", "planned", "terminal", "lease_recovery_exhausted"] = "preplanning"
    lease: PreplanningLease | None = None
    lease_recovery_count: int = Field(default=0, ge=0)
    max_lease_recoveries: int = Field(default=1, ge=0)
    graph_record_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    terminal_group_ids: tuple[str, ...] = ()
    group_result_digests: tuple[str, ...] = ()
    graph_revision: str = "genesis"
    observation_revision: str = "genesis"
    effective_read_set_digest: str = "0" * 64
    generation: int = Field(default=1, ge=1)
    state_revision: int = Field(default=0, ge=0)
    attempt_count: int = Field(default=0, ge=0)
    last_request_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # Terminal finalization clears its renewable lease.  Retain only the
    # sealed lease-binding digest so a lost acknowledgement can be recovered
    # by that exact owner, never by a later/reclaimed owner.
    last_completed_lease_binding_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_persistence_namespace(self) -> PreplanningOperationControl:
        if (
            self.persistence_namespace_id is not None
            and self.persistence_namespace_id != self.operation_fence.operation_fence_id
        ):
            raise ValueError("preplanning persistence namespace must equal operation fence")
        return self


class PreplanningPublication(BaseModel):
    operation: PreplanningOperationControl
    introduction_bytes: bytes
    artifact_index_bytes: bytes
    artifact_closure_bytes: bytes

    model_config = ConfigDict(extra="forbid", frozen=True)


class AtomicGenerationMember(BaseModel):
    member_id: str = Field(min_length=1)
    kind: Literal[
        "progress",
        "retry_outcome",
        "group_result",
        "observation_delta",
        "graph_delta",
        "event_batch",
        "terminal_operation",
        "source_summary",
        "source_result",
        "lifecycle",
        "replay_artifact",
        "artifact_index",
        "artifact_closure",
        "plan",
        "planning_artifact",
        "independence_certificate",
        "planning_authorization",
        "authorization_read_set",
        "terminal_artifact",
        "execution_plan",
        "recovery_authority_binding",
        "stage_artifact",
        "source_normalization_request",
        "bootstrap_analysis_provenance",
        "bootstrap_v3_payload_limit_authority",
        "bootstrap_proposal_run_payload",
        "bootstrap_analysis_lane_result",
        "bootstrap_pre_alignment_operation_subject_set",
        "bootstrap_analyzer_scope_observation",
        "bootstrap_analyzer_temporal_attachment_observation",
        "bootstrap_source_local_identity_partition_evidence",
        "bootstrap_parser_consensus_assessment",
        "bootstrap_semantic_scope_consensus",
        "bootstrap_temporal_attachment_consensus",
        "bootstrap_operation_temporal_attachment_consensus_set",
        "bootstrap_source_local_identity_resolution",
        "bootstrap_proposal_coverage_audit",
        "bootstrap_operation_alignment",
        "bootstrap_source_dependency_group",
        "bootstrap_graph_free_interpretation_bundle",
        "bootstrap_source_proposal_alignment",
        "bootstrap_source_normalization_request",
        "bootstrap_source_normalization_evidence_manifest",
        "bootstrap_source_normalization_result",
        "bootstrap_normalization_request_core",
        "bootstrap_semantic_reduction_authority",
        "bootstrap_graph_normalization_authority",
        "graph_free_interpretation_bundle",
        "source_local_identity_partition_evidence",
        "parser_consensus",
        "semantic_scope_consensus",
        "temporal_attachment_consensus",
        "source_local_identity_resolution",
        "source_proposal_alignment",
        "source_dependency_groups",
        "source_normalization_result",
        "source_normalization_evidence_manifest",
        "graph_dependent_execution_policy",
        "consensus_policy_selection_bundle",
        "language_construction_policy_bundle",
    ]
    canonical_payload: bytes
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class ClarificationEventRecoveryAuthorityBinding(BaseModel):
    """Exact immutable provenance for one accepted clarification event batch."""

    processing_operation_id: str = Field(min_length=1)
    generation: int = Field(ge=2)
    event_batch_sequence: int = Field(ge=1)
    transaction_record_id: str = Field(min_length=1)
    transaction_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_record_id: str = Field(min_length=1)
    receipt_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_record_id: str = Field(min_length=1)
    event_batch_record_id: str = Field(min_length=1)
    event_payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_event_batch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_batch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    replay_aggregate_payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    replay_aggregate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_revision_before: str = Field(min_length=1)
    graph_revision_after: str = Field(min_length=1)
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(
        cls,
        *,
        processing_operation_id: str,
        generation: int,
        event_batch_sequence: int,
        transaction_record_id: str,
        transaction_record_digest: str,
        receipt_record_id: str,
        receipt_record_digest: str,
        authority_record_id: str,
        event_batch_record_id: str,
        event_payload_digest: str,
        source_event_batch_digest: str,
        event_batch_digest: str,
        replay_aggregate_payload_digest: str,
        replay_aggregate_digest: str,
        graph_revision_before: str,
        graph_revision_after: str,
    ) -> ClarificationEventRecoveryAuthorityBinding:
        body = {
            "processing_operation_id": processing_operation_id,
            "generation": generation,
            "event_batch_sequence": event_batch_sequence,
            "transaction_record_id": transaction_record_id,
            "transaction_record_digest": transaction_record_digest,
            "receipt_record_id": receipt_record_id,
            "receipt_record_digest": receipt_record_digest,
            "authority_record_id": authority_record_id,
            "event_batch_record_id": event_batch_record_id,
            "event_payload_digest": event_payload_digest,
            "source_event_batch_digest": source_event_batch_digest,
            "event_batch_digest": event_batch_digest,
            "replay_aggregate_payload_digest": replay_aggregate_payload_digest,
            "replay_aggregate_digest": replay_aggregate_digest,
            "graph_revision_before": graph_revision_before,
            "graph_revision_after": graph_revision_after,
        }
        return cls(
            **body,
            binding_digest=sha256(_CLARIFICATION_RECOVERY_BINDING_DOMAIN + encode_typed_value(body)).hexdigest(),
        )

    @model_validator(mode="after")
    def validate_binding(self) -> ClarificationEventRecoveryAuthorityBinding:
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if (
            self.generation != self.event_batch_sequence + 1
            or self.transaction_record_id != _conflict_clarification_transaction_id(self.processing_operation_id)
            or self.receipt_record_id != _conflict_clarification_receipt_id(self.processing_operation_id)
            or self.authority_record_id != _conflict_clarification_recovery_authority_id(self.processing_operation_id)
            or self.event_batch_record_id != _semantic_event_batch_id(self.event_batch_sequence)
            or self.binding_digest
            != sha256(_CLARIFICATION_RECOVERY_BINDING_DOMAIN + encode_typed_value(body)).hexdigest()
        ):
            raise ValueError("clarification recovery authority binding mismatch")
        return self


class OperationLeaseBinding(BaseModel):
    operation_id: str
    operation_fence_binding: OperationFenceBinding
    delivery_principal_binding_digest: str
    delivery_key_digest: str
    allocation_namespace_id: str
    writer_namespace: Literal["semantic_ingestion"]
    admitted_writer_epoch: int = Field(ge=0)
    writer_admission_digest: str
    writer_implementation_fingerprint: str
    state_revision: int = Field(ge=1)
    owner_id: str
    execution_token: str
    ownership_epoch: int = Field(ge=1)
    lease_expires_at: datetime
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> OperationLeaseBinding:
        values = self.model_dump(mode="python", exclude={"binding_digest"})
        values["operation_fence_binding"] = self.operation_fence_binding.model_dump(mode="python")
        if self.binding_digest != sha256(encode_typed_value(values)).hexdigest():
            raise ValueError("operation lease binding digest mismatch")
        return self


class AtomicGenerationRequest(BaseModel):
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    expected_operation_generation: int = Field(ge=1)
    expected_artifact_generation: int = Field(ge=1)
    members: tuple[AtomicGenerationMember, ...]
    required_artifact_digests: tuple[str, ...]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceCheckpointAtomicWriteRequest(AtomicGenerationRequest):
    kind: Literal["checkpoint"] = "checkpoint"
    progress_state: Literal["preplanning", "planned"]


class AuthorizationReadSetPrecondition(BaseModel):
    """Exact same-store authorization record expected by one terminal group."""

    authority_record_id: str = Field(min_length=1)
    expected_authority_revision: int = Field(ge=1)
    expected_coordinates_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticAuthorizationAuthorityRecord(BaseModel):
    """Authoritative mutable semantic ingestion authorization coordinates stored beside effects."""

    authority_record_id: str = Field(min_length=1)
    authority_scope_id: str = Field(min_length=1)
    authority_revision: int = Field(ge=1)
    state: Literal["active", "revoked"]
    policy_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_revision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_policy_revision: int | None = Field(default=None, ge=1)
    egress_decision_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    deployment_authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_active_epoch: int = Field(ge=1)
    deployment_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid_until: datetime
    read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    coordinates_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_coordinates(self) -> SemanticAuthorizationAuthorityRecord:
        if self.valid_until.utcoffset() is None:
            raise ValueError("semantic authorization authority expiry must be timezone-aware")
        body = self.model_dump(mode="python", exclude={"coordinates_digest"})
        if self.coordinates_digest != sha256(encode_typed_value(body)).hexdigest():
            raise ValueError("semantic authorization authority coordinates digest mismatch")
        return self


class CommittedGroupAtomicWriteRequest(AtomicGenerationRequest):
    kind: Literal["committed"] = "committed"
    expected_graph_revision: str = Field(min_length=1)
    expected_observation_revision: str = Field(min_length=1)
    expected_effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_revision_after: str = Field(min_length=1)
    observation_revision_after: str = Field(min_length=1)
    authorization_precondition: AuthorizationReadSetPrecondition | None = None
    # A terminal service may preflight this host-owned input before it acquires
    # a lease.  The final CAS still independently derives and validates it.
    semantic_conflict_authority: SemanticConflictAuthorityCommitInput | None = None


class NonCommittingGroupAtomicWriteRequest(AtomicGenerationRequest):
    kind: Literal["non_committing"] = "non_committing"
    expected_observation_revision: str = Field(min_length=1)
    observation_revision_after: str = Field(min_length=1)
    authorization_precondition: AuthorizationReadSetPrecondition | None = None


TerminalGroupAtomicWriteRequest = Annotated[
    CommittedGroupAtomicWriteRequest | NonCommittingGroupAtomicWriteRequest,
    Field(discriminator="kind"),
]


class SourceFinalizationAtomicWriteRequest(AtomicGenerationRequest):
    kind: Literal["finalization"] = "finalization"
    source_summary_kind: Literal["pre_graph", "graph_bound"]
    expected_group_result_digests: tuple[str, ...]


class BootstrapRetainedPendingAuthorityUnavailable(BaseModel):
    kind: Literal["retained_pending"] = "retained_pending"
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_pin_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_language_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_identity: DeliveryIdentity
    operation_fence_binding: OperationFenceBinding
    reason: Literal["authorization_unavailable", "release_unavailable", "pin_mismatch"]
    terminal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_terminal(self) -> BootstrapRetainedPendingAuthorityUnavailable:
        body = self.model_dump(mode="python", exclude={"terminal_digest"})
        if self.terminal_digest != sha256(
            b"memorii.semantic_ingestion.bootstrap_retained_pending_authority_unavailable.v1\0"
            + encode_typed_value(body)
        ).hexdigest():
            raise ValueError("bootstrap retained pending authority terminal digest mismatch")
        if (
            self.operation_fence_binding.source_id != self.source_id
            or self.operation_fence_binding.source_digest != self.source_digest
            or self.operation_fence_binding.delivery_identity != self.delivery_identity
        ):
            raise ValueError("bootstrap retained pending authority terminal fence is substituted")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapRetainedPendingAuthorityUnavailable:
        body = dict(values)
        body.pop("terminal_digest", None)
        digest_body = cls.model_construct(
            **body, terminal_digest="0" * 64
        ).model_dump(mode="python", exclude={"terminal_digest"})
        return cls(
            **body,
            terminal_digest=sha256(
                b"memorii.semantic_ingestion.bootstrap_retained_pending_authority_unavailable.v1\0"
                + encode_typed_value(digest_body)
            ).hexdigest(),
        )


class BootstrapPreparedPublishedAuthorityUnavailable(BaseModel):
    kind: Literal["prepared_published"] = "prepared_published"
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prepared_generation: int = Field(ge=1)
    prepared_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_pin_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_language_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_identity: DeliveryIdentity
    operation_fence_binding: OperationFenceBinding
    reason: Literal["authorization_unavailable", "release_unavailable"]
    terminal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_terminal(self) -> BootstrapPreparedPublishedAuthorityUnavailable:
        body = self.model_dump(mode="python", exclude={"terminal_digest"})
        if self.terminal_digest != sha256(
            b"memorii.semantic_ingestion.bootstrap_prepared_published_authority_unavailable.v1\0"
            + encode_typed_value(body)
        ).hexdigest():
            raise ValueError("bootstrap prepared authority terminal digest mismatch")
        if (
            self.operation_fence_binding.source_id != self.source_id
            or self.operation_fence_binding.source_digest != self.source_digest
            or self.operation_fence_binding.delivery_identity != self.delivery_identity
        ):
            raise ValueError("bootstrap prepared authority terminal fence is substituted")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapPreparedPublishedAuthorityUnavailable:
        body = dict(values)
        body.pop("terminal_digest", None)
        digest_body = cls.model_construct(
            **body, terminal_digest="0" * 64
        ).model_dump(mode="python", exclude={"terminal_digest"})
        return cls(
            **body,
            terminal_digest=sha256(
                b"memorii.semantic_ingestion.bootstrap_prepared_published_authority_unavailable.v1\0"
                + encode_typed_value(digest_body)
            ).hexdigest(),
        )


class BootstrapWriterHandoffRequest(BaseModel):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prepared_generation: int = Field(ge=1)
    prepared_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_pin: BootstrapAdmissionPin
    release_evidence: HostVerifiedBootstrapReleaseEvidence
    bootstrap_language_evidence: BootstrapAuthenticatedLanguageEvidence
    delivery_identity: DeliveryIdentity
    operation_fence_binding: OperationFenceBinding
    current_delivery_authorization: DeliveryAuthorizationRequest
    current_release_assertion: CurrentBootstrapReleaseAssertion
    expected_writer_admission_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_writer_epoch: int = Field(ge=0)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_request(self) -> BootstrapWriterHandoffRequest:
        body = self.model_dump(
            mode="python",
            exclude={"request_digest", "current_delivery_authorization", "current_release_assertion"},
        )
        expected = sha256(
            b"memorii.semantic_ingestion.bootstrap_writer_handoff_request.v1\0"
            + encode_typed_value(body)
        ).hexdigest()
        if self.request_digest != expected:
            raise ValueError("bootstrap writer handoff request digest mismatch")
        if (
            self.operation_fence_binding.source_id != self.source_id
            or self.operation_fence_binding.source_digest != self.source_digest
            or self.operation_fence_binding.delivery_identity != self.delivery_identity
            or self.authority_pin.source_id != self.source_id
            or self.authority_pin.source_digest != self.source_digest
            or self.authority_pin.operation_fence_binding_digest != self.operation_fence_binding.binding_digest
            or self.authority_pin.release_evidence_digest != self.release_evidence.evidence_digest
            or self.authority_pin.bootstrap_language_evidence_digest
            != self.bootstrap_language_evidence.evidence_digest
            or self.bootstrap_language_evidence.source_id != self.source_id
            or self.bootstrap_language_evidence.source_digest != self.source_digest
        ):
            raise ValueError("bootstrap writer handoff fence is substituted")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapWriterHandoffRequest:
        body = dict(values)
        body.pop("request_digest", None)
        digest_body = cls.model_construct(
            **body,
            request_digest="0" * 64,
        ).model_dump(
            mode="python",
            exclude={
                "request_digest",
                "current_delivery_authorization",
                "current_release_assertion",
            },
        )
        return cls(
            **body,
            request_digest=sha256(
                b"memorii.semantic_ingestion.bootstrap_writer_handoff_request.v1\0"
                + encode_typed_value(digest_body)
            ).hexdigest(),
        )


class BootstrapWriterHandoffMarker(BaseModel):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    handoff_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prepared_generation: int = Field(ge=1)
    prepared_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_pin_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_language_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_identity: DeliveryIdentity
    operation_fence_binding: OperationFenceBinding
    writer_commit_binding: SemanticWriterCommitBinding
    pending_operation_id: str
    pending_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    marker_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_marker(self) -> BootstrapWriterHandoffMarker:
        body = self.model_dump(mode="python", exclude={"marker_digest"})
        if self.marker_digest != sha256(
            b"memorii.semantic_ingestion.bootstrap_writer_handoff_marker.v1\0" + encode_typed_value(body)
        ).hexdigest():
            raise ValueError("bootstrap writer handoff marker digest mismatch")
        if (
            self.operation_fence_binding.source_id != self.source_id
            or self.operation_fence_binding.source_digest != self.source_digest
            or self.operation_fence_binding.delivery_identity != self.delivery_identity
            or self.pending_operation_id != self.operation_fence_binding.operation_fence_id
        ):
            raise ValueError("bootstrap writer handoff marker fence is substituted")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapWriterHandoffMarker:
        body = dict(values)
        body.pop("marker_digest", None)
        digest_body = cls.model_construct(
            **body, marker_digest="0" * 64
        ).model_dump(mode="python", exclude={"marker_digest"})
        return cls(
            **body,
            marker_digest=sha256(
                b"memorii.semantic_ingestion.bootstrap_writer_handoff_marker.v1\0" + encode_typed_value(digest_body)
            ).hexdigest(),
        )


class BootstrapWriterHandoffMarkerV3(BootstrapWriterHandoffMarker):
    """The V3 marker is the sole normal handoff marker.

    It retains the authenticated V1 handoff coordinates so existing consumers
    cannot accidentally lose fence or writer binding, and adds the immutable
    recovery identity in the same sealed wire.
    """

    schema_version: Literal[3]
    handoff_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_predecessor_operation_generation: int = Field(ge=1)
    expected_predecessor_artifact_generation: int = Field(ge=1)
    expected_predecessor_control_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    marker_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_marker(self) -> BootstrapWriterHandoffMarkerV3:
        if self.marker_digest != sha256(
            b"memorii.semantic-ingestion.bootstrap-handoff-marker.v3\0"
            + encode_typed_value(self.model_dump(mode="python", exclude={"marker_digest"}))
        ).hexdigest():
            raise ValueError("bootstrap V3 handoff marker digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapWriterHandoffMarkerV3:
        body = dict(values)
        body.pop("marker_digest", None)
        digest_body = cls.model_construct(
            **body,
            marker_digest="0" * 64,
        ).model_dump(
            mode="python",
            exclude={"marker_digest"},
        )
        return cls(
            **body,
            marker_digest=sha256(
                b"memorii.semantic-ingestion.bootstrap-handoff-marker.v3\0"
                + encode_typed_value(digest_body)
            ).hexdigest(),
        )


class BootstrapWriterHandoffResult(BaseModel):
    kind: Literal["started", "already_started", "authority_unavailable", "writer_unavailable", "conflict"]
    marker: BootstrapWriterHandoffMarker | BootstrapWriterHandoffMarkerV3 | None = None
    authority_unavailable: BootstrapPreparedPublishedAuthorityUnavailable | None = None
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(cls, *, kind: str, marker: BootstrapWriterHandoffMarker | BootstrapWriterHandoffMarkerV3 | None = None,
               authority_unavailable: BootstrapPreparedPublishedAuthorityUnavailable | None = None) -> BootstrapWriterHandoffResult:
        body = {"kind": kind, "marker": marker, "authority_unavailable": authority_unavailable}
        digest_body = cls.model_construct(
            **body, result_digest="0" * 64
        ).model_dump(mode="python", exclude={"result_digest"})
        return cls(**body, result_digest=sha256(
            b"memorii.semantic_ingestion.bootstrap_writer_handoff_result.v1\0" + encode_typed_value(digest_body)
        ).hexdigest())


class BootstrapHandoffAccessDenied(BaseModel):
    kind: Literal["access_denied"] = "access_denied"
    reason: Literal["unavailable"] = "unavailable"

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticIngestionAtomicStore:
    """The only writer-safe preplanning owner permitted to publish preplanning control evidence."""

    def __init__(
        self,
        memory_plane: MemoryPlaneService,
        writer_admission: SemanticWriterAdmissionStore,
        *,
        max_lease_recoveries: int = 1,
        now_provider=lambda: datetime.now(UTC),
        event_schema_registry: SemanticEventSchemaRegistry | None = None,
        event_schema_registry_history: SemanticEventSchemaRegistryHistory | None = None,
        semantic_freeze_guard: Callable[[SemanticGraphDelta], None] | None = None,
        semantic_integrity_incident_reporter: Callable[[tuple[str, ...]], None] | None = None,
        semantic_integrity_attention_publisher: Callable[[str, datetime], None] | None = None,
        semantic_integrity_linearization: ReplayIntegrityLinearizer | None = None,
        identity_decision_authority_verifier: object | None = None,
        semantic_conflict_authority_resolver: SemanticConflictAuthorityResolver
        | None = None,
        current_bootstrap_release_verifier: CurrentBootstrapReleaseVerifier | None = None,
    ) -> None:
        if max_lease_recoveries < 0:
            raise ValueError("max lease recoveries must be non-negative")
        self._memory_plane = memory_plane
        self._writers = writer_admission
        self._write_capability = self._writers._register_atomic_owner()
        self._max_lease_recoveries = max_lease_recoveries
        self._now = now_provider
        from memorii.core.semantic_ingestion.event_replay import (
            SemanticEventSchemaRegistry,
            SemanticEventSchemaRegistryHistory,
        )

        if event_schema_registry_history is None:
            event_schema_registry = event_schema_registry or SemanticEventSchemaRegistry.create()
            event_schema_registry_history = SemanticEventSchemaRegistryHistory.create((event_schema_registry,))
        elif event_schema_registry is not None and event_schema_registry != event_schema_registry_history.current:
            raise ValueError("active event registry does not match registry history")
        else:
            event_schema_registry = event_schema_registry_history.current
        self._event_schema_registry = event_schema_registry
        self._event_schema_registry_history = event_schema_registry_history
        self._uses_default_semantic_freeze_guard = semantic_freeze_guard is None
        self._semantic_freeze_guard = semantic_freeze_guard or self._default_semantic_freeze_guard
        self._semantic_integrity_incident_reporter = (
            semantic_integrity_incident_reporter or self._record_default_semantic_integrity_incident
        )
        reporter_linearization = getattr(semantic_integrity_incident_reporter, "linearization", None)
        self._semantic_integrity_linearization = semantic_integrity_linearization or (
            reporter_linearization
            if reporter_linearization is not None and hasattr(reporter_linearization, "exclusive")
            else None
        )
        self._semantic_integrity_attention_publisher = semantic_integrity_attention_publisher
        verify_identity = getattr(
            identity_decision_authority_verifier,
            "verify_identity_decision_authority",
            None,
        )
        if identity_decision_authority_verifier is not None and not callable(
            verify_identity
        ):
            raise TypeError("identity decision authority verifier is invalid")
        self._identity_decision_authority_verifier = (
            identity_decision_authority_verifier
        )
        assert_current = getattr(current_bootstrap_release_verifier, "assert_current", None)
        if current_bootstrap_release_verifier is not None and not callable(assert_current):
            raise TypeError("current bootstrap release verifier is invalid")
        self._current_bootstrap_release_verifier = current_bootstrap_release_verifier

        self._checkpoint_resume_authority = _store_checkpoint_authority(
            registry=event_schema_registry,
            registry_history=event_schema_registry_history,
            signature_authority=(
                self._memory_plane._claim_semantic_checkpoint_signature_authority(
                    owner=_SEMANTIC_CHECKPOINT_SIGNATURE_OWNER,
                )
            ),
            persistence_scope=("durable" if self._memory_plane.is_durable_store else "ephemeral"),
            current_time_provider=self._now,
        )
        from memorii.core.memory_evolution.projection_history import (
            ProjectionHistoryRepository,
        )

        self._projection_history = ProjectionHistoryRepository(
            self._memory_plane,
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            now_provider=self._now,
            publication_capability=self._write_capability,
            current_replay_authority_resolver=(self._current_projection_replay_authority),
            semantic_conflict_authority_resolver=semantic_conflict_authority_resolver,
        )
        from memorii.core.memory_evolution.projection_scheduler import (
            ProjectionScheduler,
        )

        self._projection_scheduler = ProjectionScheduler(
            self._memory_plane,
            self._projection_history,
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            now_provider=self._now,
            publication_capability=self._write_capability,
        )
        from memorii.core.memory_evolution.policy_migration import (
            PolicyMigrationRepository,
        )

        self._policy_migration = PolicyMigrationRepository(
            self._memory_plane,
            self._projection_history,
            self._projection_scheduler,
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            now_provider=self._now,
            publication_capability=self._write_capability,
        )

    def publish_prepared_source(
        self, prepared_source: object, *, writer_binding: SemanticWriterCommitBinding
    ) -> object:
        """Persist one validated Step-2 authority through the atomic owner."""
        from memorii.core.semantic_ingestion.contracts import (
            PreparedSource,
            encode_semantic_contract,
        )

        if not isinstance(prepared_source, PreparedSource):
            raise PreplanningStoreError("prepared source publication has an invalid type")
        prepared = PreparedSource.model_validate(prepared_source.model_dump(mode="python"))
        writer_record = self._writers.require_current(writer_binding)
        authorization = self._writers._authorize_atomic(writer_binding, capability=self._write_capability)
        record_id = "semantic_ingestion:prepared_source:" + sha256(prepared.source_id.encode("utf-8")).hexdigest()
        record = CanonicalMemoryRecord(
            memory_id=record_id, domain=MemoryDomain.TRANSCRIPT, text="",
            content={"source_id": prepared.source_id, "source_digest": prepared.source_digest,
                "preparation_fingerprint": prepared.preparation_fingerprint,
                "prepared_source_wire": base64.b64encode(
                    encode_semantic_contract(prepared)
                ).decode("ascii")},
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_prepared_source",
            timestamp=self._now(), visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        existing = self._memory_plane.get_record(record_id)
        if existing is not None:
            return self._load_prepared_source_record(existing, prepared.source_id, prepared.source_digest)
        try:
            self._memory_plane.conditionally_write_records(
                (record,),
                preconditions=(RecordAbsentPrecondition(memory_id=record_id), RecordDigestPrecondition(
                    memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record))),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError:
            existing = self._memory_plane.get_record(record_id)
            if existing is None:
                raise
            return self._load_prepared_source_record(existing, prepared.source_id, prepared.source_digest)
        return prepared

    def load_prepared_source(self, *, source_id: str, source_digest: str) -> object | None:
        record = self._memory_plane.get_record(
            "semantic_ingestion:prepared_source:" + sha256(source_id.encode("utf-8")).hexdigest()
        )
        return None if record is None else self._load_prepared_source_record(record, source_id, source_digest)

    def publish_bootstrap_prepared_source_if_absent(
        self,
        *,
        prepared_source: object,
        authority_pin: BootstrapAdmissionPin,
        release_evidence: HostVerifiedBootstrapReleaseEvidence,
        language_evidence: BootstrapAuthenticatedLanguageEvidence,
        grammar_proofs: tuple[BootstrapSegmentGrammarProof, ...],
        operation_fence_binding: OperationFenceBinding,
        authorization: DeliveryAuthorizationRequest,
        release_assertion: CurrentBootstrapReleaseAssertion,
    ) -> tuple[object, int]:
        """Source-owned Step-2 CAS.  It has no writer control side effect."""
        from memorii.core.semantic_ingestion.contracts import PreparedSource, encode_semantic_contract

        if not isinstance(prepared_source, PreparedSource):
            raise PreplanningStoreError("bootstrap prepared source has an invalid type")
        prepared = PreparedSource.model_validate(prepared_source.model_dump(mode="python"))
        if (
            prepared.source_id != authority_pin.source_id
            or prepared.source_digest != authority_pin.source_digest
            or language_evidence.source_id != prepared.source_id
            or language_evidence.source_digest != prepared.source_digest
            or authority_pin.release_evidence_digest != release_evidence.evidence_digest
            or authority_pin.bootstrap_language_evidence_digest != language_evidence.evidence_digest
            or authority_pin.operation_fence_binding_digest != operation_fence_binding.binding_digest
            or operation_fence_binding.source_id != prepared.source_id
            or operation_fence_binding.source_digest != prepared.source_digest
            or operation_fence_binding.delivery_identity != authorization.delivery_identity
        ):
            raise PreplanningStoreError("bootstrap prepared publication authority is substituted")
        existing_terminal = self._load_bootstrap_authority_terminal(
            source_id=prepared.source_id,
            source_digest=prepared.source_digest,
        )
        if existing_terminal is not None:
            return existing_terminal, 0
        if not self._bootstrap_assertion_is_valid(
            assertion=release_assertion,
            release_evidence=release_evidence,
            assertion_phase="prepared_publication",
        ) or not self._current_bootstrap_access_is_valid(
            authorization=authorization,
            release_evidence=release_evidence,
            assertion_phase="prepared_publication",
            expected_delivery_identity=operation_fence_binding.delivery_identity,
            language_evidence=language_evidence,
        ):
            terminal = BootstrapRetainedPendingAuthorityUnavailable.create(
                source_id=prepared.source_id,
                source_digest=prepared.source_digest,
                authority_pin_digest=authority_pin.pin_digest,
                release_evidence_digest=release_evidence.evidence_digest,
                bootstrap_language_evidence_digest=language_evidence.evidence_digest,
                delivery_identity=operation_fence_binding.delivery_identity,
                operation_fence_binding=operation_fence_binding,
                reason="release_unavailable",
            )
            self._persist_bootstrap_authority_terminal_if_absent(terminal)
            return terminal, 0
        expected_routes = prepared.segment_language_routes.routes
        if (
            tuple(proof.segment_id for proof in grammar_proofs)
            != tuple(route.segment_id for route in expected_routes)
            or any(
                proof.source_id != prepared.source_id
                or proof.normalized_segment_digest != route.normalized_segment_digest
                or proof.proof_digest != getattr(route, "grammar_proof_digest", None)
                for proof, route in zip(grammar_proofs, expected_routes, strict=True)
            )
        ):
            raise PreplanningStoreError("bootstrap grammar proofs do not exactly bind prepared routes")
        # The pin's fence digest is stable identity, not a delivery-key alias.
        # Its equality is enforced by the handoff tuple where the full fence is available.
        wire = encode_semantic_contract(prepared)
        record_id = "semantic_ingestion:prepared_source:" + sha256(prepared.source_id.encode("utf-8")).hexdigest()
        record = CanonicalMemoryRecord(
            memory_id=record_id, domain=MemoryDomain.TRANSCRIPT, text="",
            content={
                "source_id": prepared.source_id,
                "source_digest": prepared.source_digest,
                "preparation_fingerprint": prepared.preparation_fingerprint,
                "prepared_source_wire": base64.b64encode(wire).decode("ascii"),
                "bootstrap_authority_pin": authority_pin.model_dump(mode="json"),
                "bootstrap_release_evidence": release_evidence.model_dump(mode="json"),
                "bootstrap_language_evidence": language_evidence.model_dump(mode="json"),
                "bootstrap_grammar_proofs": [proof.model_dump(mode="json") for proof in grammar_proofs],
                "prepared_generation": 1,
            },
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_prepared_source",
            timestamp=self._now(), visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        current = self._writers.current()
        binding = self._writers.commit_binding(current)
        writer_record = self._writers.require_current(binding)
        writer_authorization = self._writers._authorize_atomic(binding, capability=self._write_capability)
        existing = self._memory_plane.get_record(record_id)
        if existing is not None:
            loaded = self._load_prepared_source_record(existing, prepared.source_id, prepared.source_digest)
            if existing.content != record.content:
                raise PreplanningStoreError("bootstrap prepared publication conflicts with existing source")
            return loaded, 1
        try:
            self._memory_plane.conditionally_write_records(
                (record,),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=record_id),
                    RecordAbsentPrecondition(
                        memory_id=self._bootstrap_authority_terminal_record_id(
                            prepared.source_id
                        )
                    ),
                    RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                ),
                authorization=writer_authorization,
                transaction_precondition=self._bootstrap_current_precondition(
                    authorization=authorization,
                    release_evidence=release_evidence,
                    assertion_phase="prepared_publication",
                    expected_delivery_identity=operation_fence_binding.delivery_identity,
                    language_evidence=language_evidence,
                ),
            )
        except _BootstrapAuthorityUnavailableAtCommit:
            existing_terminal = self._load_bootstrap_authority_terminal(
                source_id=prepared.source_id,
                source_digest=prepared.source_digest,
            )
            if existing_terminal is not None:
                return existing_terminal, 0
            terminal = BootstrapRetainedPendingAuthorityUnavailable.create(
                source_id=prepared.source_id,
                source_digest=prepared.source_digest,
                authority_pin_digest=authority_pin.pin_digest,
                release_evidence_digest=release_evidence.evidence_digest,
                bootstrap_language_evidence_digest=language_evidence.evidence_digest,
                delivery_identity=operation_fence_binding.delivery_identity,
                operation_fence_binding=operation_fence_binding,
                reason="release_unavailable",
            )
            return self._persist_bootstrap_authority_terminal_if_absent(terminal), 0
        except MemoryPlaneRevisionConflictError as exc:
            existing_terminal = self._load_bootstrap_authority_terminal(
                source_id=prepared.source_id,
                source_digest=prepared.source_digest,
            )
            if existing_terminal is not None:
                return existing_terminal, 0
            existing = self._memory_plane.get_record(record_id)
            if existing is None or existing.content != record.content:
                raise PreplanningStoreError("bootstrap prepared publication CAS conflicted") from exc
        return prepared, 1

    def bootstrap_writer_handoff(
        self, request: BootstrapWriterHandoffRequest, *, canonical_evidence_lease: CanonicalEvidenceLease | None = None
    ) -> BootstrapHandoffAccessDenied | BootstrapWriterHandoffResult:
        """Create writer state exactly once after source-owned publication.

        The current authorization and release assertion are checked before any
        marker lookup, preserving the non-disclosing recovery boundary.
        """
        terminal = self._load_bootstrap_authority_terminal(
            source_id=request.source_id, source_digest=request.source_digest
        )
        if isinstance(terminal, BootstrapRetainedPendingAuthorityUnavailable):
            if (
                terminal.authority_pin_digest == request.authority_pin.pin_digest
                and terminal.release_evidence_digest == request.release_evidence.evidence_digest
                and terminal.bootstrap_language_evidence_digest
                == request.bootstrap_language_evidence.evidence_digest
                and terminal.delivery_identity == request.delivery_identity
                and terminal.operation_fence_binding == request.operation_fence_binding
            ):
                return BootstrapWriterHandoffResult.create(
                    kind="authority_unavailable", authority_unavailable=terminal
                )
            return BootstrapWriterHandoffResult.create(kind="conflict")
        if isinstance(terminal, BootstrapPreparedPublishedAuthorityUnavailable):
            if (
                terminal.prepared_generation == request.prepared_generation
                and terminal.prepared_source_digest == request.prepared_source_digest
                and terminal.authority_pin_digest == request.authority_pin.pin_digest
                and terminal.release_evidence_digest == request.release_evidence.evidence_digest
                and terminal.bootstrap_language_evidence_digest
                == request.bootstrap_language_evidence.evidence_digest
                and terminal.delivery_identity == request.delivery_identity
                and terminal.operation_fence_binding == request.operation_fence_binding
            ):
                return BootstrapWriterHandoffResult.create(
                    kind="authority_unavailable", authority_unavailable=terminal
                )
            return BootstrapWriterHandoffResult.create(kind="conflict")
        if not self._bootstrap_assertion_is_valid(
            assertion=request.current_release_assertion,
            release_evidence=request.release_evidence,
            assertion_phase="pre_handoff_retry",
        ) or not self._current_bootstrap_access_is_valid(
            authorization=request.current_delivery_authorization,
            release_evidence=request.release_evidence,
            assertion_phase="pre_handoff_retry",
            expected_delivery_identity=request.delivery_identity,
            language_evidence=request.bootstrap_language_evidence,
        ):
            return BootstrapHandoffAccessDenied()
        marker_id = "semantic_ingestion:bootstrap-handoff:" + sha256(
            request.source_id.encode("utf-8") + request.request_digest.encode("ascii")
        ).hexdigest()
        prepared_record = self._memory_plane.get_record(
            "semantic_ingestion:prepared_source:" + sha256(request.source_id.encode("utf-8")).hexdigest()
        )
        if prepared_record is None:
            return BootstrapWriterHandoffResult.create(kind="conflict")
        content = prepared_record.content
        if (
            content.get("source_digest") != request.source_digest
            or content.get("prepared_generation") != request.prepared_generation
            or content.get("bootstrap_authority_pin") != request.authority_pin.model_dump(mode="json")
            or content.get("bootstrap_release_evidence") != request.release_evidence.model_dump(mode="json")
            or content.get("bootstrap_language_evidence") != request.bootstrap_language_evidence.model_dump(mode="json")
        ):
            return BootstrapWriterHandoffResult.create(kind="conflict")
        try:
            prepared = self._load_prepared_source_record(prepared_record, request.source_id, request.source_digest)
        except PreplanningStoreError:
            return BootstrapWriterHandoffResult.create(kind="conflict")
        current = self._writers.current()
        if (
            current.writer_epoch != request.expected_writer_epoch
            or current.admission_digest != request.expected_writer_admission_digest
        ):
            return BootstrapWriterHandoffResult.create(kind="writer_unavailable")
        if canonical_evidence_lease is None:
            from memorii.core.semantic_ingestion.contracts import encode_semantic_contract
            prepared_bytes = encode_semantic_contract(prepared)
        else:
            if canonical_evidence_lease._released:
                return BootstrapWriterHandoffResult.create(kind="conflict")
            evidence = canonical_evidence_lease.result
            scope = canonical_evidence_lease.scope
            if (
                type(evidence.contract) is not type(prepared)
                or evidence.contract != prepared
                or scope.operation != request.operation_fence_binding.operation_id
                or scope.generation != request.prepared_generation
                or scope.fence != request.operation_fence_binding.operation_fence_id
                or scope.tenant
                != request.current_delivery_authorization.ingress.delivery_principal_binding.tenant_partition_id
                or scope.writer != f"{current.admission_digest}:{current.writer_epoch}"
                or not evidence.member_evidence
            ):
                return BootstrapWriterHandoffResult.create(kind="conflict")
            prepared_bytes = evidence.canonical_contract_bytes
        if request.prepared_source_digest != sha256(prepared_bytes).hexdigest():
            return BootstrapWriterHandoffResult.create(kind="conflict")
        # An idempotent marker still consumes a fresh lease: exact loaded
        # bytes and current writer authority must be revalidated per delivery.
        existing = self._memory_plane.get_record(marker_id)
        if existing is not None:
            try:
                marker = BootstrapWriterHandoffMarkerV3.model_validate(existing.content["marker"])
            except (KeyError, TypeError, ValueError):
                return BootstrapWriterHandoffResult.create(kind="conflict")
            if marker.handoff_request_digest != request.request_digest:
                return BootstrapWriterHandoffResult.create(kind="conflict")
            return BootstrapWriterHandoffResult.create(kind="already_started", marker=marker)
        binding = self._writers.commit_binding(current)
        writer_record = self._writers.require_current(binding)
        writer_authorization = self._writers._authorize_atomic(binding, capability=self._write_capability)
        control = PreplanningOperationControl(
            operation_fence=request.operation_fence_binding,
            persistence_namespace_id=request.operation_fence_binding.operation_fence_id,
            writer_binding=binding,
            max_lease_recoveries=self._max_lease_recoveries,
            graph_revision=self.semantic_replay_state().graph_revision,
        )
        # Revalidate at the write linearization point.  A current failure here
        # becomes a retained terminal; pre-lookup denial remains ephemeral.
        if not self._current_bootstrap_access_is_valid(
            authorization=request.current_delivery_authorization,
            release_evidence=request.release_evidence,
            assertion_phase="writer_handoff",
            expected_delivery_identity=request.delivery_identity,
            language_evidence=request.bootstrap_language_evidence,
        ):
            terminal = BootstrapPreparedPublishedAuthorityUnavailable.create(
                source_id=request.source_id,
                source_digest=request.source_digest,
                prepared_generation=request.prepared_generation,
                prepared_source_digest=request.prepared_source_digest,
                authority_pin_digest=request.authority_pin.pin_digest,
                release_evidence_digest=request.release_evidence.evidence_digest,
                bootstrap_language_evidence_digest=request.bootstrap_language_evidence.evidence_digest,
                delivery_identity=request.delivery_identity,
                operation_fence_binding=request.operation_fence_binding,
                reason="release_unavailable",
            )
            persisted = self._persist_bootstrap_authority_terminal_if_absent(terminal)
            if not isinstance(persisted, BootstrapPreparedPublishedAuthorityUnavailable):
                return BootstrapWriterHandoffResult.create(kind="conflict")
            return BootstrapWriterHandoffResult.create(kind="authority_unavailable", authority_unavailable=persisted)
        publication = _publication(control)
        # The recovery key is minted before the marker so the marker can
        # authenticate it without introducing a digest cycle.
        from memorii.core.semantic_ingestion.contracts import BootstrapRecoveryKeyV3, contract_digest

        recovery_key_body = {
            "source_id": request.source_id,
            "source_digest": request.source_digest,
            "preparation_fingerprint": prepared.preparation_fingerprint,
            "operation_id": request.operation_fence_binding.operation_id,
            "operation_fence_digest": request.operation_fence_binding.binding_digest,
            "bootstrap_profile_manifest_digest": request.release_evidence.evidence_digest,
            "handoff_request_digest": request.request_digest,
        }
        recovery_key = BootstrapRecoveryKeyV3(
            **recovery_key_body,
            recovery_key_digest=contract_digest(
                b"memorii.semantic-ingestion.bootstrap-recovery-key.v3", recovery_key_body
            ),
        )
        marker = BootstrapWriterHandoffMarkerV3.create(
            schema_version=3,
            source_id=request.source_id, source_digest=request.source_digest,
            handoff_request_digest=request.request_digest,
            prepared_generation=request.prepared_generation,
            prepared_source_digest=request.prepared_source_digest,
            authority_pin_digest=request.authority_pin.pin_digest,
            release_evidence_digest=request.release_evidence.evidence_digest,
            bootstrap_language_evidence_digest=request.bootstrap_language_evidence.evidence_digest,
            delivery_identity=request.delivery_identity,
            operation_fence_binding=request.operation_fence_binding,
            writer_commit_binding=binding,
            pending_operation_id=request.operation_fence_binding.operation_fence_id,
            pending_operation_digest=sha256(encode_typed_value(control.model_dump(mode="python"))).hexdigest(),
            recovery_key_digest=recovery_key.recovery_key_digest,
            expected_predecessor_operation_generation=control.generation,
            expected_predecessor_artifact_generation=control.generation,
            expected_predecessor_control_digest=sha256(
                encode_typed_value(control.model_dump(mode="python"))
            ).hexdigest(),
        )
        marker_record = CanonicalMemoryRecord(
            memory_id=marker_id, domain=MemoryDomain.TRANSCRIPT, text="",
            content={"marker": marker.model_dump(mode="json")}, status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_bootstrap_handoff_marker", timestamp=self._now(),
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        recovery_record = _bootstrap_v3_unclaimed_recovery_record(
            recovery_key=recovery_key, operation_generation=control.generation,
            artifact_generation=control.generation, marker=marker, timestamp=self._now(),
        )
        records = (*_publication_records(publication, self._now()), marker_record, recovery_record)
        try:
            self._memory_plane.conditionally_write_records(
                records,
                preconditions=(
                    *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in records),
                    RecordAbsentPrecondition(
                        memory_id=self._bootstrap_authority_terminal_record_id(
                            request.source_id
                        )
                    ),
                    RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                ),
                authorization=writer_authorization,
                transaction_precondition=self._bootstrap_current_precondition(
                    authorization=request.current_delivery_authorization,
                    release_evidence=request.release_evidence,
                    assertion_phase="writer_handoff",
                    expected_delivery_identity=request.delivery_identity,
                    language_evidence=request.bootstrap_language_evidence,
                ),
            )
        except _BootstrapAuthorityUnavailableAtCommit:
            existing_terminal = self._load_bootstrap_authority_terminal(
                source_id=request.source_id,
                source_digest=request.source_digest,
            )
            if isinstance(existing_terminal, BootstrapPreparedPublishedAuthorityUnavailable):
                return BootstrapWriterHandoffResult.create(
                    kind="authority_unavailable", authority_unavailable=existing_terminal
                )
            if existing_terminal is not None:
                return BootstrapWriterHandoffResult.create(kind="conflict")
            terminal = BootstrapPreparedPublishedAuthorityUnavailable.create(
                source_id=request.source_id,
                source_digest=request.source_digest,
                prepared_generation=request.prepared_generation,
                prepared_source_digest=request.prepared_source_digest,
                authority_pin_digest=request.authority_pin.pin_digest,
                release_evidence_digest=request.release_evidence.evidence_digest,
                bootstrap_language_evidence_digest=request.bootstrap_language_evidence.evidence_digest,
                delivery_identity=request.delivery_identity,
                operation_fence_binding=request.operation_fence_binding,
                reason="release_unavailable",
            )
            persisted = self._persist_bootstrap_authority_terminal_if_absent(terminal)
            if not isinstance(persisted, BootstrapPreparedPublishedAuthorityUnavailable):
                return BootstrapWriterHandoffResult.create(kind="conflict")
            return BootstrapWriterHandoffResult.create(
                kind="authority_unavailable", authority_unavailable=persisted
            )
        except MemoryPlaneRevisionConflictError:
            terminal = self._load_bootstrap_authority_terminal(
                source_id=request.source_id,
                source_digest=request.source_digest,
            )
            if isinstance(terminal, BootstrapPreparedPublishedAuthorityUnavailable):
                return BootstrapWriterHandoffResult.create(
                    kind="authority_unavailable", authority_unavailable=terminal
                )
            if terminal is not None:
                return BootstrapWriterHandoffResult.create(kind="conflict")
            existing = self._memory_plane.get_record(marker_id)
            if existing is not None:
                try:
                    marker = BootstrapWriterHandoffMarkerV3.model_validate(existing.content["marker"])
                except (KeyError, TypeError, ValueError):
                    return BootstrapWriterHandoffResult.create(kind="conflict")
                if marker.handoff_request_digest == request.request_digest:
                    return BootstrapWriterHandoffResult.create(kind="already_started", marker=marker)
            return BootstrapWriterHandoffResult.create(kind="conflict")
        return BootstrapWriterHandoffResult.create(kind="started", marker=marker)

    def _current_bootstrap_access_is_valid(
        self,
        *,
        authorization: DeliveryAuthorizationRequest,
        release_evidence: HostVerifiedBootstrapReleaseEvidence,
        assertion_phase: Literal["prepared_publication", "pre_handoff_retry", "writer_handoff"],
        expected_delivery_identity: DeliveryIdentity,
        language_evidence: BootstrapAuthenticatedLanguageEvidence,
    ) -> bool:
        """Validate ephemeral host authority without letting it enter durable bytes."""
        if (
            authorization.delivery_identity != expected_delivery_identity
            or authorization.delivery_identity.delivery_principal_binding_digest
            != language_evidence.delivery_principal_binding_digest
        ):
            return False
        try:
            require_complete_scope_authorization(
                ingress=authorization.ingress,
                required_outcome_scopes=authorization.ingress.required_outcome_scopes,
            )
        except (AttributeError, TypeError, ValueError):
            return False
        verifier = self._current_bootstrap_release_verifier
        if verifier is None:
            return False
        try:
            raw_assertion = verifier.assert_current(
                authorization=authorization,
                release_evidence=release_evidence,
                assertion_phase=assertion_phase,
            )
            assertion = CurrentBootstrapReleaseAssertion.model_validate(
                raw_assertion.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError, OSError):
            return False
        return self._bootstrap_assertion_is_valid(
            assertion=assertion,
            release_evidence=release_evidence,
            assertion_phase=assertion_phase,
        )

    @staticmethod
    def _bootstrap_assertion_is_valid(
        *,
        assertion: CurrentBootstrapReleaseAssertion,
        release_evidence: HostVerifiedBootstrapReleaseEvidence,
        assertion_phase: Literal["prepared_publication", "pre_handoff_retry", "writer_handoff"],
    ) -> bool:
        try:
            value = CurrentBootstrapReleaseAssertion.model_validate(
                assertion.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            return False
        return (
            value.assertion_phase == assertion_phase
            and value.coordinate == release_evidence.coordinate
            and value.signed_release_digest == release_evidence.signed_release_digest
            and value.bootstrap_anchor_digest == release_evidence.bootstrap_anchor_digest
            and value.active_lifecycle_snapshot_digest
            == release_evidence.active_lifecycle_snapshot_digest
        )

    def _bootstrap_current_precondition(
        self,
        *,
        authorization: DeliveryAuthorizationRequest,
        release_evidence: HostVerifiedBootstrapReleaseEvidence,
        assertion_phase: Literal["prepared_publication", "pre_handoff_retry", "writer_handoff"],
        expected_delivery_identity: DeliveryIdentity,
        language_evidence: BootstrapAuthenticatedLanguageEvidence,
    ) -> Callable[[], None]:
        """Return the opaque, non-persisted host check for the write lock.

        ``MemoryPlaneStore.apply_batch`` invokes this after acquiring its
        transaction lock and immediately before applying records.  The host
        verifier owns revocation linearization, so a failed or malformed
        response prevents the entire batch from becoming visible.
        """
        def validate() -> None:
            if not self._current_bootstrap_access_is_valid(
                authorization=authorization,
                release_evidence=release_evidence,
                assertion_phase=assertion_phase,
                expected_delivery_identity=expected_delivery_identity,
                language_evidence=language_evidence,
            ):
                raise _BootstrapAuthorityUnavailableAtCommit(
                    "bootstrap release authority unavailable at write commit"
                )

        return validate

    @staticmethod
    def _bootstrap_authority_terminal_record_id(source_id: str) -> str:
        return "semantic_ingestion:bootstrap-authority-unavailable:" + sha256(
            source_id.encode("utf-8")
        ).hexdigest()

    def _load_bootstrap_authority_terminal(
        self, *, source_id: str, source_digest: str
    ) -> BootstrapRetainedPendingAuthorityUnavailable | BootstrapPreparedPublishedAuthorityUnavailable | None:
        record = self._memory_plane.get_record(self._bootstrap_authority_terminal_record_id(source_id))
        if record is None:
            return None
        if record.source_kind != "semantic_ingestion_bootstrap_authority_unavailable":
            raise PreplanningStoreError("bootstrap authority terminal record is substituted")
        try:
            payload = record.content["terminal"]
            kind = payload["kind"]
            terminal = (
                BootstrapRetainedPendingAuthorityUnavailable.model_validate(payload)
                if kind == "retained_pending"
                else BootstrapPreparedPublishedAuthorityUnavailable.model_validate(payload)
                if kind == "prepared_published"
                else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("bootstrap authority terminal record is invalid") from exc
        if terminal is None or terminal.source_id != source_id or terminal.source_digest != source_digest:
            raise PreplanningStoreError("bootstrap authority terminal identity is substituted")
        return terminal

    def _persist_bootstrap_authority_terminal_if_absent(
        self,
        terminal: BootstrapRetainedPendingAuthorityUnavailable | BootstrapPreparedPublishedAuthorityUnavailable,
    ) -> BootstrapRetainedPendingAuthorityUnavailable | BootstrapPreparedPublishedAuthorityUnavailable:
        record_id = self._bootstrap_authority_terminal_record_id(terminal.source_id)
        record = CanonicalMemoryRecord(
            memory_id=record_id,
            domain=MemoryDomain.TRANSCRIPT,
            text="",
            content={"terminal": terminal.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_bootstrap_authority_unavailable",
            timestamp=self._now(),
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        existing = self._load_bootstrap_authority_terminal(
            source_id=terminal.source_id, source_digest=terminal.source_digest
        )
        if existing is not None:
            if existing != terminal:
                raise PreplanningStoreError("bootstrap authority terminal conflicts with existing source")
            return existing
        current = self._writers.current()
        binding = self._writers.commit_binding(current)
        writer_record = self._writers.require_current(binding)
        authorization = self._writers._authorize_atomic(binding, capability=self._write_capability)
        try:
            self._memory_plane.conditionally_write_records(
                (record,),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=record_id),
                    RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._load_bootstrap_authority_terminal(
                source_id=terminal.source_id, source_digest=terminal.source_digest
            )
            if existing is None or existing != terminal:
                raise PreplanningStoreError("bootstrap authority terminal CAS conflicted") from exc
            return existing
        return terminal

    @staticmethod
    def _load_prepared_source_record(record: CanonicalMemoryRecord, source_id: str, source_digest: str) -> object:
        from memorii.core.semantic_ingestion.contracts import (
            PreparedSource,
            decode_semantic_contract,
        )

        content = record.content
        if (record.source_kind != "semantic_ingestion_prepared_source" or content.get("source_id") != source_id
                or content.get("source_digest") != source_digest or not isinstance(content.get("prepared_source_wire"), str)):
            raise PreplanningStoreError("prepared source record is substituted or invalid")
        try:
            prepared = decode_semantic_contract(
                base64.b64decode(content["prepared_source_wire"], validate=True),
                PreparedSource,
            )
        except (ValueError, TypeError) as exc:
            raise PreplanningStoreError("prepared source record payload is invalid") from exc
        if content.get("preparation_fingerprint") != prepared.preparation_fingerprint:
            raise PreplanningStoreError("prepared source record fingerprint is substituted")
        return prepared

    def publish_preplanning(
        self,
        *,
        admission: SourceAdmissionAccepted,
        writer_binding: SemanticWriterCommitBinding,
    ) -> PreplanningPublication:
        raise PreplanningStoreError("new preplanning publication requires atomic source admission")

    def publish_admitted_source(
        self,
        *,
        prepared: PreparedSourceAdmission,
        writer_binding: SemanticWriterCommitBinding,
    ) -> SourceAdmissionAccepted:
        """Publish only the immutable Step-1 admission evidence.

        Bootstrap preparation owns the next source-only CAS.  In particular,
        this boundary must not allocate a preplanning control, lease, or
        writer-bound generation; those begin at ``bootstrap_writer_handoff``.
        """
        linearization = self._semantic_integrity_linearization
        if linearization is None:
            return self._publish_admitted_source_linearized(
                prepared=prepared,
                writer_binding=writer_binding,
            )
        with linearization.exclusive():
            return self._publish_admitted_source_linearized(
                prepared=prepared,
                writer_binding=writer_binding,
            )

    def _publish_admitted_source_linearized(
        self,
        *,
        prepared: PreparedSourceAdmission,
        writer_binding: SemanticWriterCommitBinding,
    ) -> SourceAdmissionAccepted:
        admission = prepared.accepted
        existing_records = tuple(
            self._memory_plane.get_record(record.memory_id)
            for record in prepared.records
        )
        if any(record is not None for record in existing_records):
            if not all(
                _same_admission_record(existing, expected)
                for existing, expected in zip(existing_records, prepared.records, strict=True)
            ):
                raise PreplanningStoreError(
                    "atomic admission evidence is partial or mismatched"
                )
            return admission
        writer_record = self._writers.require_current(writer_binding)
        authorization = self._writers._authorize_atomic(
            writer_binding,
            capability=self._write_capability,
        )
        try:
            self._memory_plane.conditionally_write_records(
                prepared.records,
                preconditions=(
                    *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in prepared.records),
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id,
                        expected_digest=record_digest(writer_record),
                    ),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            if not all(
                _same_admission_record(
                    self._memory_plane.get_record(record.memory_id), record
                )
                for record in prepared.records
            ):
                raise PreplanningStoreError(
                    "atomic admission conflict is not an exact committed retry"
                ) from exc
        return admission

    def assert_current_bootstrap_release(
        self,
        *,
        authorization: DeliveryAuthorizationRequest,
        release_evidence: HostVerifiedBootstrapReleaseEvidence,
        assertion_phase: Literal[
            "prepared_publication", "pre_handoff_retry", "writer_handoff"
        ],
    ) -> CurrentBootstrapReleaseAssertion | None:
        """Obtain an ephemeral assertion solely from the host-installed verifier."""
        verifier = self._current_bootstrap_release_verifier
        if verifier is None:
            return None
        try:
            assertion = verifier.assert_current(
                authorization=authorization,
                release_evidence=release_evidence,
                assertion_phase=assertion_phase,
            )
            value = CurrentBootstrapReleaseAssertion.model_validate(
                assertion.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError, OSError):
            return None
        if (
            value.assertion_phase != assertion_phase
            or value.coordinate != release_evidence.coordinate
            or value.signed_release_digest != release_evidence.signed_release_digest
            or value.bootstrap_anchor_digest != release_evidence.bootstrap_anchor_digest
            or value.active_lifecycle_snapshot_digest
            != release_evidence.active_lifecycle_snapshot_digest
        ):
            return None
        return value

    def _publish_preplanning(
        self,
        *,
        admission: SourceAdmissionAccepted,
        writer_binding: SemanticWriterCommitBinding,
    ) -> PreplanningPublication:
        linearization = self._semantic_integrity_linearization
        if linearization is None:
            return self._publish_preplanning_linearized(
                admission=admission,
                writer_binding=writer_binding,
            )
        with linearization.exclusive():
            return self._publish_preplanning_linearized(
                admission=admission,
                writer_binding=writer_binding,
            )

    def _publish_preplanning_linearized(
        self,
        *,
        admission: SourceAdmissionAccepted,
        writer_binding: SemanticWriterCommitBinding,
    ) -> PreplanningPublication:
        operation_fence = admission.operation_fence_binding
        self._validate_handoff(admission, operation_fence)
        writer_record = self._writers.require_current(writer_binding)
        authorization = self._writers._authorize_atomic(
            writer_binding,
            capability=self._write_capability,
        )
        control_id = _control_id(operation_fence)
        existing = self._memory_plane.get_record(control_id)
        if existing is not None:
            return self._recover_publication(existing, admission, operation_fence, writer_binding)
        control = PreplanningOperationControl(
            operation_fence=operation_fence,
            persistence_namespace_id=operation_fence.operation_fence_id,
            writer_binding=writer_binding,
            max_lease_recoveries=self._max_lease_recoveries,
            graph_revision=self.semantic_replay_state().graph_revision,
        )
        publication = _publication(control)
        records = _publication_records(publication, self._now())
        try:
            self._memory_plane.conditionally_write_records(
                records,
                preconditions=tuple(RecordAbsentPrecondition(memory_id=record.memory_id) for record in records)
                + (
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)
                    ),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._memory_plane.get_record(control_id)
            if existing is None:
                raise exc
            return self._recover_publication(existing, admission, operation_fence, writer_binding)
        return publication

    def admit_source(
        self, *, prepared: PreparedSourceAdmission, writer_binding: SemanticWriterCommitBinding
    ) -> PreplanningPublication:
        """Atomically publish retained admission evidence and its pending operation."""

        linearization = self._semantic_integrity_linearization
        if linearization is None:
            return self._admit_source_linearized(
                prepared=prepared,
                writer_binding=writer_binding,
            )
        with linearization.exclusive():
            return self._admit_source_linearized(
                prepared=prepared,
                writer_binding=writer_binding,
            )

    def _admit_source_linearized(
        self,
        *,
        prepared: PreparedSourceAdmission,
        writer_binding: SemanticWriterCommitBinding,
    ) -> PreplanningPublication:
        admission = prepared.accepted
        fence = admission.operation_fence_binding
        if any(self._memory_plane.get_record(record.memory_id) is not None for record in prepared.records):
            if any(
                not _same_admission_record(self._memory_plane.get_record(record.memory_id), record)
                for record in prepared.records
            ):
                raise PreplanningStoreError("atomic admission evidence is partial or mismatched")
            return self._publish_preplanning(admission=admission, writer_binding=writer_binding)
        writer_record = self._writers.require_current(writer_binding)
        authorization = self._writers._authorize_atomic(writer_binding, capability=self._write_capability)
        control = PreplanningOperationControl(
            operation_fence=fence,
            persistence_namespace_id=fence.operation_fence_id,
            writer_binding=writer_binding,
            max_lease_recoveries=self._max_lease_recoveries,
            graph_revision=self.semantic_replay_state().graph_revision,
        )
        publication = _publication(control)
        generation_records = _publication_records(publication, self._now())
        all_records = (*prepared.records, *generation_records)
        try:
            self._memory_plane.conditionally_write_records(
                all_records,
                preconditions=(
                    *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in all_records),
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)
                    ),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            if any(
                not _same_admission_record(self._memory_plane.get_record(record.memory_id), record)
                for record in prepared.records
            ):
                raise PreplanningStoreError("atomic admission conflict is not an exact committed retry") from exc
            existing = self._memory_plane.get_record(_control_id(fence))
            if existing is None:
                raise PreplanningStoreError("atomic admission conflict has no complete operation generation") from exc
            return self._recover_publication(existing, admission, fence, writer_binding)
        return publication

    def acquire_lease(
        self,
        *,
        operation_fence: OperationFenceBinding | None = None,
        operation_id: str | None = None,
        writer_binding: SemanticWriterCommitBinding,
        execution_token: str,
        owner_id: str | None = None,
        duration: timedelta,
    ) -> PreplanningOperationControl:
        from memorii.core.memory_evolution.projection_history import ProjectionHistoryError

        if duration <= timedelta(0):
            raise PreplanningStoreError("lease duration must be positive")
        writer_record = self._writers.require_current(writer_binding)
        record = self._lease_control_record(operation_fence=operation_fence, operation_id=operation_id)
        control = _control_from_record(record)
        if control.writer_binding != writer_binding:
            raise PreplanningStoreError("writer binding does not own operation")
        if control.state == "lease_recovery_exhausted":
            return control
        if control.state not in {"preplanning", "planned"}:
            raise PreplanningStoreError("operation is terminal")
        now = self._now()
        lease = control.lease
        if lease is not None and lease.expires_at > now:
            if lease.execution_token == execution_token and (owner_id is None or lease.owner_id == owner_id):
                return control
            raise PreplanningStoreError("operation lease is held by another owner")
        recovery = control.lease_recovery_count + int(lease is not None and lease.expires_at <= now)
        if recovery > control.max_lease_recoveries:
            exhausted = control.model_copy(update={"state": "lease_recovery_exhausted", "lease": None})
            self._replace_control(
                record,
                exhausted,
                writer_record,
                writer_binding=writer_binding,
                expected_lease=lease,
            )
            return exhausted
        next_control = control.model_copy(
            update={
                "lease": PreplanningLease(
                    owner_id=owner_id or execution_token,
                    execution_token=execution_token,
                    ownership_epoch=(lease.ownership_epoch + 1 if lease is not None else 1),
                    acquired_at=now,
                    expires_at=now + duration,
                    renewal_interval=duration / 2,
                ),
                "lease_recovery_count": recovery,
                "state_revision": control.state_revision + 1,
                "attempt_count": control.attempt_count + 1,
            }
        )
        try:
            self._replace_control(
                record,
                next_control,
                writer_record,
                writer_binding=writer_binding,
                expected_lease=lease,
                require_active_lease=False,
            )
        except (MemoryPlaneRevisionConflictError, ProjectionHistoryError):
            raced = _control_from_record(
                self._lease_control_record(operation_fence=operation_fence, operation_id=operation_id)
            )
            if raced.state == "terminal":
                return raced
            if (
                raced.lease is not None
                and raced.lease.expires_at > self._now()
                and raced.lease.execution_token == execution_token
                and (owner_id is None or raced.lease.owner_id == owner_id)
            ):
                return raced
            raise
        return next_control

    def renew_lease(
        self,
        *,
        operation_fence: OperationFenceBinding | None = None,
        operation_id: str | None = None,
        writer_binding: SemanticWriterCommitBinding,
        lease: PreplanningLease,
        duration: timedelta,
    ) -> PreplanningOperationControl:
        if duration <= timedelta(0):
            raise PreplanningStoreError("lease duration must be positive")
        writer_record = self._writers.require_current(writer_binding)
        record = self._lease_control_record(operation_fence=operation_fence, operation_id=operation_id)
        control = _control_from_record(record)
        if control.writer_binding != writer_binding or control.lease != lease or lease.expires_at <= self._now():
            raise PreplanningStoreError("stale or mismatched operation lease")
        next_control = control.model_copy(
            update={
                "lease": lease.model_copy(
                    update={"expires_at": self._now() + duration, "renewal_interval": duration / 2}
                ),
                "state_revision": control.state_revision + 1,
            }
        )
        self._replace_control(
            record,
            next_control,
            writer_record,
            writer_binding=writer_binding,
            expected_lease=lease,
            require_active_lease=True,
        )
        return next_control

    def lease_binding(self, control: PreplanningOperationControl) -> OperationLeaseBinding:
        lease = control.lease
        if lease is None:
            raise PreplanningStoreError("operation has no active lease")
        fence = control.operation_fence
        values = {
            "operation_id": fence.operation_id,
            "operation_fence_binding": fence,
            "delivery_principal_binding_digest": fence.delivery_principal_binding_digest,
            "delivery_key_digest": fence.delivery_key_digest,
            "allocation_namespace_id": fence.allocation_namespace_id,
            "writer_namespace": "semantic_ingestion",
            "admitted_writer_epoch": control.writer_binding.expected_writer_epoch,
            "writer_admission_digest": control.writer_binding.admission_digest,
            "writer_implementation_fingerprint": control.writer_binding.writer_implementation_fingerprint,
            "state_revision": control.state_revision,
            "owner_id": lease.owner_id,
            "execution_token": lease.execution_token,
            "ownership_epoch": lease.ownership_epoch,
            "lease_expires_at": lease.expires_at,
        }
        digest_values = dict(values)
        digest_values["operation_fence_binding"] = fence.model_dump(mode="python")
        return OperationLeaseBinding(**values, binding_digest=sha256(encode_typed_value(digest_values)).hexdigest())

    def current_source_normalization_lease(
        self,
        *,
        operation_fence: OperationFenceBinding,
        expected_operation_generation: int,
        expected_artifact_generation: int,
        writer_commit_binding: SemanticWriterCommitBinding,
    ) -> OperationLeaseBinding:
        """Return only the live lease for one exact preplanning publication CAS.

        Host composition uses this narrow read to issue publication authority;
        callers cannot substitute another operation, generation, or writer.
        """
        control = self.get_operation(operation_fence)
        if (
            control.operation_fence != operation_fence
            or control.generation != expected_operation_generation
            or expected_artifact_generation != control.generation
            or control.writer_binding != writer_commit_binding
            or control.lease is None
        ):
            raise PreplanningStoreError("source normalization publication lease is unavailable")
        return self.lease_binding(control)

    def install_authorization_authority(
        self,
        *,
        writer_binding: SemanticWriterCommitBinding,
        authority: SemanticAuthorizationAuthorityRecord,
    ) -> AuthorizationReadSetPrecondition:
        expected_id = _authorization_authority_id(authority.authority_scope_id)
        if (
            authority.authority_record_id != expected_id
            or authority.authority_revision != 1
            or authority.state != "active"
        ):
            raise PreplanningStoreError("initial authorization authority record is invalid")
        self._writers.require_current(writer_binding)
        existing = self._memory_plane.get_record(expected_id)
        if existing is None:
            record = _authorization_authority_record(authority, self._now())
            self._memory_plane.conditionally_write_records(
                (record,),
                preconditions=(RecordAbsentPrecondition(memory_id=expected_id),),
                authorization=self._writers._authorize_atomic(
                    writer_binding,
                    capability=self._write_capability,
                ),
            )
            existing = self._memory_plane.get_record(expected_id)
        if existing is None:
            raise PreplanningStoreError("authorization authority publication was not durable")
        recovered = _authorization_authority_from_record(existing)
        if recovered != authority:
            raise PreplanningStoreError("authorization authority is already bound differently")
        return _authorization_precondition(existing, recovered)

    def replace_authorization_authority(
        self,
        *,
        writer_binding: SemanticWriterCommitBinding,
        expected: AuthorizationReadSetPrecondition,
        authority: SemanticAuthorizationAuthorityRecord,
    ) -> AuthorizationReadSetPrecondition:
        if (
            expected.authority_record_id != _authorization_authority_id(authority.authority_scope_id)
            or authority.authority_record_id != expected.authority_record_id
            or authority.authority_revision != expected.expected_authority_revision + 1
        ):
            raise PreplanningStoreError("authorization authority replacement is invalid")
        prior = self._memory_plane.get_record(expected.authority_record_id)
        if prior is None or record_digest(prior) != expected.expected_record_digest:
            raise PreplanningStoreError("authorization authority replacement CAS is stale")
        recovered = _authorization_authority_from_record(prior)
        if (
            recovered.authority_revision != expected.expected_authority_revision
            or recovered.coordinates_digest != expected.expected_coordinates_digest
        ):
            raise PreplanningStoreError("authorization authority replacement coordinates are stale")
        record = _authorization_authority_record(authority, prior.timestamp)
        self._memory_plane.conditionally_write_records(
            (record,),
            preconditions=(
                RecordDigestPrecondition(
                    memory_id=prior.memory_id,
                    expected_digest=expected.expected_record_digest,
                ),
            ),
            authorization=self._writers._authorize_atomic(
                writer_binding,
                capability=self._write_capability,
            ),
        )
        current = self._memory_plane.get_record(expected.authority_record_id)
        if current is None:
            raise PreplanningStoreError("authorization authority replacement was not durable")
        return _authorization_precondition(current, authority)

    def authorization_authority(
        self,
        authority_scope_id: str,
    ) -> tuple[SemanticAuthorizationAuthorityRecord, AuthorizationReadSetPrecondition] | None:
        record = self._memory_plane.get_record(_authorization_authority_id(authority_scope_id))
        if record is None:
            return None
        authority = _authorization_authority_from_record(record)
        return authority, _authorization_precondition(record, authority)

    def get_operation(self, operation_fence: OperationFenceBinding | str) -> PreplanningOperationControl:
        if isinstance(operation_fence, str):
            return _control_from_record(self._required_control_record_by_operation_id(operation_fence))
        return _control_from_record(self._required_control_record(operation_fence))

    def generation_members(
        self,
        operation_fence: OperationFenceBinding,
        generation: int,
    ) -> tuple[AtomicGenerationMember, ...]:
        """Read one exact internal generation through its authenticated fence.

        This is an internal recovery boundary, not public outcome lookup.  The
        complete fence must match the persisted operation before any member is
        returned, preventing raw operation IDs from becoming read authority.
        """
        control = _control_from_record(self._required_control_record(operation_fence))
        if generation < 2 or generation > control.generation:
            raise PreplanningStoreError("generation is outside the admitted operation")
        try:
            return self._read_generation_members(control, generation)
        except PreplanningStoreError:
            # The V3 recovery-ready generation carries only its sealed control
            # snapshot and claim; exposing it as an empty internal generation
            # prevents generic retry scans from treating it as corrupt output.
            for record in self._memory_plane.list_records(
                source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
            ):
                snapshot = record.content.get("control_snapshot")
                if (
                    (
                        record.content.get("state") == "claimed"
                        and isinstance(snapshot, dict)
                        and snapshot.get("control_record", {}).get("operation_generation") == generation
                        and snapshot.get("control_record", {}).get("operation_fence_digest")
                        == operation_fence.binding_digest
                    )
                    or (
                        record.content.get("state") == "found"
                        and record.content.get("publication_operation_generation") == generation + 1
                    )
                ):
                    return ()
            raise

    def recover_source_normalization(
        self, *, request_identity: str
    ) -> tuple[int, str, tuple[AtomicGenerationMember, ...]] | None:
        """Read exactly one source-normalization recovery-index target.

        The index is written with its generation CAS.  This method is a read
        boundary only: it never scans or reconstructs candidate artifacts.
        """
        records = self._memory_plane.list_records(
            source_kind="semantic_ingestion_source_normalization_recovery_index"
        )
        matches = [record for record in records if record.content.get("request_identity") == request_identity]
        if not matches:
            return None
        if len(matches) != 1:
            raise PreplanningStoreError("source normalization recovery index is ambiguous")
        record = matches[0]
        try:
            namespace = str(record.content["namespace_id"])
            generation = int(record.content["publication_generation"])
            atomic_request_digest = str(record.content["atomic_request_digest"])
            control = self._control_by_operation_fence_id(namespace)
            if _control_namespace(control) != namespace:
                raise ValueError
            return generation, atomic_request_digest, self._read_generation_members(control, generation)
        except (KeyError, TypeError, ValueError, PreplanningStoreError) as exc:
            raise PreplanningStoreError("source normalization recovery index is corrupt") from exc

    def recover_bootstrap_v3_source_normalization(
        self, *, recovery_key_digest: str
    ) -> tuple[int, str, str, tuple[AtomicGenerationMember, ...]] | None:
        """Reload the one V3 Found entry without re-running derivation work."""
        record = self._memory_plane.get_record(
            "semantic_ingestion:bootstrap-v3-recovery:" + recovery_key_digest
        )
        if record is None:
            return None
        try:
            content = record.content
            if (
                content["schema_version"] != 3
                or content["recovery_key_digest"] != recovery_key_digest
                or content["state"] != "found"
                or content["kind"] != "found"
            ):
                raise ValueError
            control = self._control_by_operation_fence_id(str(content["namespace_id"]))
            generation = int(content["publication_artifact_generation"])
            members = self._read_generation_members(control, generation)
            # A Found lookup has no caller-owned request to repair or fill in
            # missing analysis.  Decode the retained V3 closure directly from
            # this generation before exposing its result to recovery.
            from memorii.core.semantic_ingestion.source_normalization_repository import (
                AtomicStoreSourceNormalizationRepository,
            )
            AtomicStoreSourceNormalizationRepository.validate_bootstrap_v3_reloaded_members(members)
            return generation, str(content["atomic_request_digest"]), str(content["result_digest"]), members
        except (KeyError, TypeError, ValueError, PreplanningStoreError) as exc:
            raise PreplanningStoreError("bootstrap V3 recovery index is corrupt") from exc

    def bootstrap_v3_recovery_snapshot(self) -> tuple[tuple[str, str, str], ...]:
        """Return only the durable V3 recovery identities for testable reload proof."""
        rows: list[tuple[str, str, str]] = []
        for record in self._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
        ):
            content = record.content
            if content.get("schema_version") != 3 or content.get("state") not in {"claimed", "found"}:
                raise PreplanningStoreError("bootstrap V3 recovery index is corrupt")
            key = content.get("recovery_key_digest")
            if not isinstance(key, str):
                raise PreplanningStoreError("bootstrap V3 recovery index is corrupt")
            digest = (
                content.get("claim_digest")
                if content["state"] == "claimed"
                else content.get("consumed_claim_digest")
            )
            if not isinstance(digest, str):
                raise PreplanningStoreError("bootstrap V3 recovery index is corrupt")
            rows.append((key, content["state"], digest))
        return tuple(sorted(rows))

    def probe_bootstrap_v3_recovery(self, *, probe: object, server_time: datetime, monotonic_tick: int) -> object:
        """Atomically return Found, one live claim, or a closed unavailable arm."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapNormalizationReadyControlRecordV3,
            BootstrapRecoveryClaimedV3,
            BootstrapRecoveryClaimV3,
            BootstrapRecoveryControlSnapshotV3,
            BootstrapRecoveryFoundV3,
            BootstrapRecoveryProbeV3,
            contract_digest,
        )
        try:
            probe = BootstrapRecoveryProbeV3.model_validate(probe.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError):
            return _bootstrap_v3_unavailable("0" * 64, "invalid_probe")
        memory_id = _bootstrap_v3_recovery_id(probe.recovery_key.recovery_key_digest)
        record = self._memory_plane.get_record(memory_id)
        if record is None:
            return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "storage_unavailable")
        content = record.content
        try:
            if content["recovery_key_digest"] != probe.recovery_key.recovery_key_digest:
                raise ValueError
            if content["state"] == "found":
                body = {name: content[name] for name in (
                    "kind", "recovery_key_digest", "consumed_claim_digest",
                    "recovery_control_snapshot_digest", "predecessor_operation_generation",
                    "predecessor_artifact_generation", "publication_operation_generation",
                    "publication_artifact_generation", "result_digest", "provenance_manifest_digest",
                )}
                return BootstrapRecoveryFoundV3(**body, response_digest=contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-recovery-found.v3", body))
            if (content["operation_fence_digest"] != probe.recovery_key.operation_fence_digest
                    or content["handoff_marker_digest"] != probe.handoff_marker_digest
                    or content["predecessor_operation_generation"] != probe.expected_predecessor_operation_generation
                    or content["predecessor_artifact_generation"] != probe.expected_predecessor_artifact_generation
                    or content["predecessor_control_digest"] != probe.expected_predecessor_control_digest):
                return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "stale_predecessor")
            live = content["state"] == "claimed" and server_time < datetime.fromisoformat(content["expires_server_time"]) and monotonic_tick < content["expires_monotonic_tick"]
            if live:
                return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "foreign_live_claim")
            fence = OperationFenceBinding.model_validate(content["operation_fence"])
            writer_binding = SemanticWriterCommitBinding.model_validate(content["writer_commit_binding"])
            control_record = self._required_control_record(fence)
            control = _control_from_record(control_record)
            if content["state"] == "claimed":
                # The first claim owns the predecessor-to-ready transition.  A
                # later claimant must instead reuse that exact ready snapshot;
                # comparing it to the old predecessor would make every expiry
                # unrecoverable after the successful generation advance.
                prior_claim = BootstrapRecoveryClaimV3.model_validate_json(
                    json.dumps(
                        {name: content[name] for name in BootstrapRecoveryClaimV3.model_fields}
                    )
                )
                snapshot = prior_claim.control_snapshot.control_record
                if (
                    content.get("control_snapshot") != prior_claim.control_snapshot.model_dump(mode="json")
                    or control.generation != snapshot.operation_generation
                    or control.operation_fence != fence
                    or control.writer_binding != snapshot.writer_commit_binding
                    or control.lease is None
                    or self.lease_binding(control) != snapshot.operation_lease_binding
                ):
                    return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "stale_control_snapshot")
                if snapshot.operation_lease_binding.lease_expires_at <= server_time:
                    return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "lease_unavailable")
                current = self._writers.current()
                if self._writers.commit_binding(current) != snapshot.writer_commit_binding:
                    return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "writer_unavailable")
                claim_body = prior_claim.model_dump(
                    mode="python",
                    exclude={
                        "claim_digest", "claim_nonce", "issued_server_time",
                        "expires_server_time", "issued_monotonic_tick",
                        "expires_monotonic_tick", "renewal_count",
                    },
                )
                claim_body.update(
                    claim_nonce=token_hex(24),
                    issued_server_time=server_time,
                    expires_server_time=server_time + timedelta(seconds=10),
                    issued_monotonic_tick=monotonic_tick,
                    expires_monotonic_tick=monotonic_tick + 10,
                    renewal_count=0,
                )
                claim = BootstrapRecoveryClaimV3(
                    **claim_body,
                    claim_digest=contract_digest(
                        b"memorii.semantic-ingestion.bootstrap-recovery-claim.v3", claim_body
                    ),
                )
                next_record = record.model_copy(
                    update={"content": {**content, **claim.model_dump(mode="json")}}
                )
                self._memory_plane.conditionally_write_records(
                    (next_record,),
                    preconditions=(
                        RecordDigestPrecondition(memory_id=memory_id, expected_digest=record_digest(record)),
                    ),
                    authorization=self._writers._authorize_atomic(
                        snapshot.writer_commit_binding, capability=self._write_capability
                    ),
                )
                response = {"kind": "claimed", "claim": claim}
                return BootstrapRecoveryClaimedV3(**response, response_digest=contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-recovery-claimed.v1", response))
            if content["state"] != "unclaimed":
                return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "index_corrupt")
            predecessor_digest = sha256(encode_typed_value(control.model_dump(mode="python"))).hexdigest()
            if (control.generation != probe.expected_predecessor_operation_generation
                    or predecessor_digest != probe.expected_predecessor_control_digest):
                return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "stale_predecessor")
            current = self._writers.current()
            if self._writers.commit_binding(current) != writer_binding:
                return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "writer_unavailable")
            lease = PreplanningLease(owner_id="bootstrap-v3-recovery", execution_token=token_hex(24), ownership_epoch=1,
                acquired_at=server_time, expires_at=server_time + timedelta(seconds=60), renewal_interval=timedelta(seconds=30))
            next_control = control.model_copy(update={"generation": control.generation + 1, "lease": lease,
                "state_revision": control.state_revision + 1, "attempt_count": control.attempt_count + 1})
            lease_binding = self.lease_binding(next_control)
            ready_body = {"schema_version": 3, "recovery_key_digest": probe.recovery_key.recovery_key_digest,
                "handoff_marker_digest": probe.handoff_marker_digest, "source_id": probe.recovery_key.source_id,
                "source_digest": probe.recovery_key.source_digest, "preparation_fingerprint": probe.recovery_key.preparation_fingerprint,
                "operation_id": probe.recovery_key.operation_id, "operation_fence_digest": probe.recovery_key.operation_fence_digest,
                "predecessor_operation_generation": control.generation, "predecessor_artifact_generation": control.generation,
                "predecessor_control_digest": predecessor_digest, "operation_generation": next_control.generation,
                "artifact_generation": next_control.generation, "transition": "post_handoff_normalization_ready",
                "operation_lease_binding": lease_binding, "writer_commit_binding": writer_binding,
                "progress_digest": sha256(encode_typed_value(next_control.model_dump(mode="python"))).hexdigest()}
            ready = BootstrapNormalizationReadyControlRecordV3(**ready_body, control_record_digest=contract_digest(
                b"memorii.semantic-ingestion.bootstrap-normalization-ready-control-record.v3", ready_body))
            snapshot_body = {"control_record": ready}
            snapshot = BootstrapRecoveryControlSnapshotV3(**snapshot_body, snapshot_digest=contract_digest(
                b"memorii.semantic-ingestion.bootstrap-recovery-control-snapshot.v3", snapshot_body))
            body = {"recovery_key_digest": probe.recovery_key.recovery_key_digest,
                    "handoff_marker_digest": probe.handoff_marker_digest,
                    "operation_fence_digest": probe.recovery_key.operation_fence_digest, "control_snapshot": snapshot,
                    "claim_nonce": token_hex(24), "issued_server_time": server_time,
                    "expires_server_time": server_time + timedelta(seconds=10),
                    "issued_monotonic_tick": monotonic_tick, "expires_monotonic_tick": monotonic_tick + 10,
                    # The evidence producer renews once per lane per segment
                    # (4 per request) plus the proposal, interpreter, and
                    # publication rounds; a multi-segment source therefore
                    # needs 4N+4 renewals, which a budget of 10 cannot cover
                    # beyond one segment.
                    "renewal_count": 0, "max_claim_renewals": 64, "max_claim_total_duration_ticks": 10}
            claim = BootstrapRecoveryClaimV3(**body, claim_digest=contract_digest(
                b"memorii.semantic-ingestion.bootstrap-recovery-claim.v3", body))
            next_record = record.model_copy(update={"content": {**content, "state": "claimed", **claim.model_dump(mode="json")}})
            self._memory_plane.conditionally_write_records((_control_record(next_control, control_record.timestamp), next_record), preconditions=(
                RecordDigestPrecondition(memory_id=memory_id, expected_digest=record_digest(record)),
                RecordDigestPrecondition(memory_id=control_record.memory_id, expected_digest=record_digest(control_record)),
            ), authorization=self._writers._authorize_atomic(
                writer_binding, capability=self._write_capability
            ))
            response = {"kind": "claimed", "claim": claim}
            return BootstrapRecoveryClaimedV3(**response, response_digest=contract_digest(
                b"memorii.semantic-ingestion.bootstrap-recovery-claimed.v1", response))
        except MemoryPlaneRevisionConflictError:
            return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "foreign_live_claim")
        except (KeyError, TypeError, ValueError):
            return _bootstrap_v3_unavailable(probe.recovery_key.recovery_key_digest, "index_corrupt")

    def renew_or_abort_bootstrap_v3_recovery(self, *, claim: object, server_time: datetime, monotonic_tick: int) -> object:
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapRecoveryClaimV3,
            BootstrapRecoveryRenewedV3,
            contract_digest,
        )
        try:
            claim = BootstrapRecoveryClaimV3.model_validate(claim.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError):
            return _bootstrap_v3_aborted("0" * 64, "snapshot_substituted")
        record = self._memory_plane.get_record(_bootstrap_v3_recovery_id(claim.recovery_key_digest))
        if record is None:
            return _bootstrap_v3_aborted(claim.recovery_key_digest, "consumed")
        content = record.content
        if content.get("state") == "found":
            return _bootstrap_v3_aborted(claim.recovery_key_digest, "consumed")
        if content.get("state") != "claimed" or content.get("claim_digest") != claim.claim_digest or content.get("claim_nonce") != claim.claim_nonce:
            return _bootstrap_v3_aborted(claim.recovery_key_digest, "foreign")
        try:
            fence = claim.control_snapshot.control_record.operation_lease_binding.operation_fence_binding
            control = self.get_operation(fence)
            snapshot = claim.control_snapshot.control_record
            if (
                control.generation != snapshot.operation_generation
                or control.operation_fence != fence
                or control.writer_binding != snapshot.writer_commit_binding
                or control.lease is None
                or self.lease_binding(control) != snapshot.operation_lease_binding
            ):
                return _bootstrap_v3_aborted(claim.recovery_key_digest, "control_advanced")
            if snapshot.operation_lease_binding.lease_expires_at <= server_time:
                return _bootstrap_v3_aborted(claim.recovery_key_digest, "lease_expired")
            if self._writers.commit_binding(self._writers.current()) != snapshot.writer_commit_binding:
                return _bootstrap_v3_aborted(claim.recovery_key_digest, "writer_superseded")
        except (PreplanningStoreError, ValueError):
            return _bootstrap_v3_aborted(claim.recovery_key_digest, "snapshot_substituted")
        if server_time >= claim.expires_server_time or monotonic_tick >= claim.expires_monotonic_tick:
            return _bootstrap_v3_aborted(claim.recovery_key_digest, "expired")
        if claim.renewal_count >= claim.max_claim_renewals:
            return _bootstrap_v3_aborted(claim.recovery_key_digest, "renewal_bound")
        body = claim.model_dump(mode="python", exclude={"claim_digest", "issued_server_time", "expires_server_time", "issued_monotonic_tick", "expires_monotonic_tick", "renewal_count"})
        body.update(issued_server_time=server_time, expires_server_time=server_time + timedelta(seconds=10),
                    issued_monotonic_tick=monotonic_tick, expires_monotonic_tick=monotonic_tick + 10,
                    renewal_count=claim.renewal_count + 1)
        renewed = BootstrapRecoveryClaimV3(**body, claim_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-claim.v3", body))
        next_record = record.model_copy(update={"content": {**content, **renewed.model_dump(mode="json")}})
        try:
            current = self._writers.current()
            writer_binding = self._writers.commit_binding(current)
            self._memory_plane.conditionally_write_records((next_record,), preconditions=(
                RecordDigestPrecondition(memory_id=record.memory_id, expected_digest=record_digest(record)),
            ), authorization=self._writers._authorize_atomic(
                writer_binding, capability=self._write_capability
            ))
        except MemoryPlaneRevisionConflictError:
            return _bootstrap_v3_aborted(claim.recovery_key_digest, "foreign")
        body = {"kind": "renewed", "claim": renewed}
        return BootstrapRecoveryRenewedV3(**body, response_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-renewed.v3", body))

    def source_normalization_recovery_snapshot(
        self, *, request_identity: str
    ) -> tuple[int, int, str]:
        """Return a bounded snapshot proof for an indexed recovery absence."""
        matches = [
            record for record in self._memory_plane.list_records(
                source_kind="semantic_ingestion_source_normalization_recovery_index"
            )
            if record.content.get("request_identity") == request_identity
        ]
        if len(matches) > 1:
            raise PreplanningStoreError("source normalization recovery index is ambiguous")
        if matches:
            namespace = str(matches[0].content.get("namespace_id"))
            control = self._control_by_operation_fence_id(namespace)
            snapshot = sha256(encode_typed_value(matches[0].content)).hexdigest()
            return control.generation, control.generation, snapshot
        snapshot = sha256(encode_typed_value(("source_normalization_recovery", request_identity, ()))) .hexdigest()
        return 1, 1, snapshot

    @property
    def event_schema_registry(self) -> SemanticEventSchemaRegistry:
        return self._event_schema_registry

    @property
    def event_schema_registry_history(self) -> SemanticEventSchemaRegistryHistory:
        """Return public schema compatibility history without checkpoint secrets."""

        return self._event_schema_registry_history

    @property
    def identity_decision_authority_verifier(self) -> object | None:
        """Return the verifier capability sealed into this store instance."""

        return self._identity_decision_authority_verifier

    def authoritative_commit_timestamp(self) -> datetime:
        """Sample the one UTC timestamp used to materialize a commit attempt."""

        value = self._now()
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise PreplanningStoreError("semantic commit timestamp is not UTC")
        return value

    @property
    def projection_history(self) -> ProjectionHistoryRepository:
        """Return the sole typed temporal/trust projection authority owner."""

        return self._projection_history

    @property
    def projection_scheduler(self) -> ProjectionScheduler:
        """Expose the read-only scheduler owner; writes require atomic capability."""

        return self._projection_scheduler

    @property
    def policy_migration(self) -> PolicyMigrationRepository:
        """Expose deterministic planning; publication remains atomic-store owned."""

        return self._policy_migration

    def plan_temporal_policy_migration(
        self,
        active: TemporalPolicySnapshot,
        pending: TemporalPolicySnapshot,
        active_trust: TrustPolicySnapshot,
        *,
        writer_binding: SemanticWriterCommitBinding,
        migration_partition_revision: int = 0,
    ) -> TemporalPolicyMigrationPlan:
        """Derive complete temporal migration membership from active authority."""

        self._writers.require_current(writer_binding)
        plan = self._policy_migration.plan_temporal(
            active,
            pending,
            active_trust,
            writer_epoch=writer_binding.expected_writer_epoch,
            migration_partition_revision=migration_partition_revision,
        )
        self._commit_policy_migration_progress(
            self._policy_migration.prepare_progress(plan),
            writer_binding=writer_binding,
        )
        return plan

    def plan_trust_policy_migration(
        self,
        active: TrustPolicySnapshot,
        pending: TrustPolicySnapshot,
        *,
        arbitration_as_of: datetime,
        writer_binding: SemanticWriterCommitBinding,
        migration_partition_revision: int = 0,
    ) -> TrustPolicyMigrationPlan:
        """Derive complete trust migration and decay-command membership."""

        self._writers.require_current(writer_binding)
        plan = self._policy_migration.plan_trust(
            active,
            pending,
            arbitration_as_of=arbitration_as_of,
            writer_epoch=writer_binding.expected_writer_epoch,
            migration_partition_revision=migration_partition_revision,
        )
        self._commit_policy_migration_progress(
            self._policy_migration.prepare_progress(plan),
            writer_binding=writer_binding,
        )
        return plan

    def run_temporal_policy_migration(
        self,
        plan: TemporalPolicyMigrationPlan,
        pending: TemporalPolicySnapshot,
        active_trust: TrustPolicySnapshot,
        *,
        writer_binding: SemanticWriterCommitBinding,
    ) -> tuple[TemporalMigrationResult, ...]:
        """Recover and persist the durable temporal command queue in order."""

        self._writers.require_current(writer_binding)
        while True:
            result = self._policy_migration._execute_next_temporal(
                plan,
                pending,
                active_trust,
                capability=self._write_capability,
            )
            catch_up, persisted = self._policy_migration._load_temporal_progress(
                plan
            )
            if result is None:
                return persisted
            results = tuple(
                sorted((*persisted, result), key=lambda item: item.result_digest)
            )
            self._commit_policy_migration_progress(
                self._policy_migration.prepare_progress(
                    plan,
                    catch_up=catch_up,
                    results=results,
                ),
                writer_binding=writer_binding,
            )

    def cutover_temporal_policy(
        self,
        plan: TemporalPolicyMigrationPlan,
        pending: TemporalPolicySnapshot,
        results: tuple[TemporalMigrationResult, ...],
        *,
        writer_binding: SemanticWriterCommitBinding,
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...] = (),
        final_catch_up_watermark: str,
        expected_partition_revision: int,
        complete_read_set_digest: str,
    ) -> SemanticWriterCommitBinding:
        """Atomically activate one complete temporal policy generation."""

        completed = self._completed_policy_cutover_binding(
            plan,
            results,
            catch_up,
            final_catch_up_watermark=final_catch_up_watermark,
            expected_partition_revision=expected_partition_revision,
            complete_read_set_digest=complete_read_set_digest,
            writer_binding=writer_binding,
        )
        if completed is not None:
            return completed
        authorization = self._writers._authorize_atomic(
            writer_binding,
            capability=self._write_capability,
        )
        self._commit_policy_migration_progress(
            self._policy_migration.prepare_progress(
                plan,
                catch_up=catch_up,
                results=results,
            ),
            writer_binding=writer_binding,
        )
        prepared = self._policy_migration.prepare_temporal_cutover(
            plan,
            pending,
            results,
            catch_up=catch_up,
            final_catch_up_watermark=final_catch_up_watermark,
            expected_partition_revision=expected_partition_revision,
            complete_read_set_digest=complete_read_set_digest,
            authorization=authorization,
        )
        return self._commit_policy_migration(
            prepared,
            policy_snapshot_digest=pending.snapshot_digest,
            writer_binding=writer_binding,
        )

    def cutover_trust_policy(
        self,
        plan: TrustPolicyMigrationPlan,
        pending: TrustPolicySnapshot,
        results: tuple[TrustMigrationResult, ...],
        *,
        writer_binding: SemanticWriterCommitBinding,
        catch_up: tuple[TrustMigrationCatchUpEntry, ...] = (),
        final_catch_up_watermark: str,
        expected_partition_revision: int,
        complete_read_set_digest: str,
    ) -> SemanticWriterCommitBinding:
        """Atomically activate one complete trust policy generation."""

        completed = self._completed_policy_cutover_binding(
            plan,
            results,
            catch_up,
            final_catch_up_watermark=final_catch_up_watermark,
            expected_partition_revision=expected_partition_revision,
            complete_read_set_digest=complete_read_set_digest,
            writer_binding=writer_binding,
        )
        if completed is not None:
            return completed
        authorization = self._writers._authorize_atomic(
            writer_binding,
            capability=self._write_capability,
        )
        self._commit_policy_migration_progress(
            self._policy_migration.prepare_progress(
                plan,
                catch_up=catch_up,
                results=results,
            ),
            writer_binding=writer_binding,
        )
        prepared = self._policy_migration.prepare_trust_cutover(
            plan,
            pending,
            results,
            catch_up=catch_up,
            final_catch_up_watermark=final_catch_up_watermark,
            expected_partition_revision=expected_partition_revision,
            complete_read_set_digest=complete_read_set_digest,
            authorization=authorization,
        )
        return self._commit_policy_migration(
            prepared,
            policy_snapshot_digest=pending.snapshot_digest,
            writer_binding=writer_binding,
        )

    def _commit_policy_migration(
        self,
        prepared: PreparedTemporalPolicyMigration | PreparedTrustPolicyMigration,
        *,
        policy_snapshot_digest: str,
        writer_binding: SemanticWriterCommitBinding,
    ) -> SemanticWriterCommitBinding:
        from memorii.core.memory_evolution.policy_migration import (
            PreparedTemporalPolicyMigration as TemporalPreparedMigration,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            advance_semantic_replay_authority,
            create_replay_checkpoint,
        )

        if isinstance(prepared, TemporalPreparedMigration):
            kind: Literal["temporal", "trust"] = "temporal"
            bindings = self._projection_history.replay_bindings_with_temporal(
                prepared.publication
            )
        else:
            kind = "trust"
            bindings = self._projection_history.replay_bindings_with_trust(
                prepared.publication
            )
        projection = prepared.publication
        prior = self.semantic_replay_authority()
        conflict_binding = self._projection_history.semantic_conflict_replay_binding(
            pending_records=projection.records,
        )
        activated_epoch = prepared.cutover.activated_writer_epoch
        checkpoint = None
        if prior.latest_checkpoint is not None:
            checkpoint = create_replay_checkpoint(
                state=prior.graph_state,
                watermark_batch=prior.latest_checkpoint.watermark_batch,
                writer_epoch=activated_epoch,
                authority=self._checkpoint_resume_authority,
                created_at=self._now(),
                reconstructed_replay_authority_digest=(
                    prior.reconstructed_authority_digest
                ),
                projection_history_bindings=bindings,
                semantic_conflict_replay_binding=conflict_binding,
            )
        aggregate = advance_semantic_replay_authority(
            prior,
            graph_state=prior.graph_state,
            member_bindings=(),
            reconstructed_authority_digest=prior.reconstructed_authority_digest,
            latest_checkpoint=checkpoint,
            projection_history_bindings=bindings,
            semantic_conflict_replay_binding=conflict_binding,
        )
        now = self._now()
        replay_records = (
            _semantic_replay_authority_record(aggregate, now),
            _semantic_checkpoint_lifecycle_record(
                self._checkpoint_resume_authority, now
            ),
            _semantic_registry_history_record(self._event_schema_registry_history, now),
        )
        publication = projection.publication
        operation_id = f"policy-migration:{kind}:{prepared.plan.plan_digest}"
        envelope = _projection_publication_envelope_record(
            publication_kind=(
                "temporal_policy_migration"
                if kind == "temporal"
                else "trust_policy_migration"
            ),
            projection_kind=kind,
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            operation_id=operation_id,
            authority_coordinate_digest=prepared.cutover.cutover_digest,
            policy_snapshot_digest=policy_snapshot_digest,
            active_policy_fingerprint=prepared.plan.pending_policy_fingerprint,
            complete_read_set_digest=prepared.cutover.complete_read_set_digest,
            writer_epoch=activated_epoch,
            certificate_digest=publication.certificate.certificate_digest,
            generation_digest=publication.generation.generation_digest,
            pointer_digest=publication.active_pointer.pointer_digest,
            pointer_publication_kind="migration_cutover",
            timestamp=now,
        )
        records = (
            *replay_records,
            *projection.records,
            *prepared.authority_records,
            envelope,
        )
        preconditions = (
            *self._semantic_authority_record_preconditions(
                replay_records,
                require_unfrozen=True,
            ),
            *projection.preconditions,
            *prepared.authority_preconditions,
            RecordAbsentPrecondition(memory_id=envelope.memory_id),
        )
        successor = self._writers.advance_policy_epoch(
            expected=writer_binding,
            policy_activation_digest=prepared.cutover.cutover_digest,
            records=records,
            preconditions=preconditions,
        )
        return self._writers.commit_binding(successor)

    def _completed_policy_cutover_binding(
        self,
        plan: TemporalPolicyMigrationPlan | TrustPolicyMigrationPlan,
        results: tuple[TemporalMigrationResult, ...]
        | tuple[TrustMigrationResult, ...],
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...]
        | tuple[TrustMigrationCatchUpEntry, ...],
        *,
        final_catch_up_watermark: str,
        expected_partition_revision: int,
        complete_read_set_digest: str,
        writer_binding: SemanticWriterCommitBinding,
    ) -> SemanticWriterCommitBinding | None:
        current = self._writers.current()
        if current.writer_epoch == writer_binding.expected_writer_epoch:
            return None
        if (
            current.writer_epoch != writer_binding.expected_writer_epoch + 1
            or current.previous_admission_digest != writer_binding.admission_digest
        ):
            raise PreplanningStoreError("policy cutover retry is stale")
        if plan.migration_kind == "temporal":
            certificate = self._projection_history.completed_temporal_migration(
                plan.plan_digest
            )
            view = self._projection_history.active_temporal_authority()
        else:
            certificate = self._projection_history.completed_trust_migration(
                plan.plan_digest
            )
            view = self._projection_history.active_trust_authority()
        committed_result_digests = tuple(
            sorted(item.result_digest for item in results if item.status == "committed")
        )
        if (
            certificate is None
            or len(committed_result_digests) != len(results)
            or certificate.pending_policy_fingerprint
            != plan.pending_policy_fingerprint
            or certificate.writer_epoch_before
            != writer_binding.expected_writer_epoch
            or certificate.activated_writer_epoch != current.writer_epoch
            or certificate.final_catch_up_watermark
            != final_catch_up_watermark
            or expected_partition_revision
            != (
                max(item.partition_revision for item in catch_up)
                if catch_up
                else plan.migration_partition_revision
            )
            or certificate.complete_read_set_digest != complete_read_set_digest
            or certificate.server_derived_base_slot_plan_digests
            != tuple(item.slot_plan_digest for item in plan.slot_plans)
            or certificate.server_derived_catch_up_entry_digests
            != tuple(sorted(item.entry_digest for item in catch_up))
            or view.generation.canonical_slot_result_digests
            != committed_result_digests
        ):
            raise PreplanningStoreError("policy cutover retry diverged")
        return self._writers.commit_binding(current)

    def _commit_policy_migration_progress(
        self,
        prepared: PreparedPolicyMigrationProgress,
        *,
        writer_binding: SemanticWriterCommitBinding,
    ) -> None:
        operation_id = (
            f"policy-migration-progress:{prepared.migration_kind}:"
            f"{prepared.progress_digest}"
        )
        envelope = _projection_migration_progress_envelope_record(
            projection_kind=prepared.migration_kind,
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            operation_id=operation_id,
            migration_plan_digest=prepared.migration_plan_digest,
            catch_up_entry_digests=prepared.catch_up_entry_digests,
            result_digests=prepared.result_digests,
            writer_epoch=writer_binding.expected_writer_epoch,
            progress_digest=prepared.progress_digest,
            timestamp=self._now(),
        )
        existing = self._memory_plane.get_record(envelope.memory_id)
        if existing is not None:
            if (
                existing.source_kind == envelope.source_kind
                and existing.content == envelope.content
                and all(
                    self._memory_plane.get_record(record.memory_id) == record
                    for record in prepared.records
                )
            ):
                return
            raise PreplanningStoreError("policy migration progress diverged")
        authorization = self._writers._authorize_atomic(
            writer_binding,
            capability=self._write_capability,
        )
        self._memory_plane.conditionally_write_records(
            (*prepared.records, envelope),
            preconditions=(
                *prepared.preconditions,
                RecordAbsentPrecondition(memory_id=envelope.memory_id),
            ),
            authorization=authorization,
        )

    def reconcile_trust_decay(
        self,
        policy: TrustPolicySnapshot,
        *,
        writer_binding: SemanticWriterCommitBinding,
        complete_read_set_digest: str,
    ) -> bool:
        """Persist the exact same-policy threshold schedule through one atomic CAS."""

        authorization = self._writers._authorize_atomic(
            writer_binding,
            capability=self._write_capability,
        )
        prepared = self._projection_scheduler.prepare_schedule(
            policy,
            writer_epoch=writer_binding.expected_writer_epoch,
            complete_read_set_digest=complete_read_set_digest,
            authorization=authorization,
        )
        if prepared is None:
            return False
        self._commit_trust_decay_publication(
            prepared,
            writer_binding=writer_binding,
            authorization=authorization,
        )
        return True

    def run_due_trust_decay(
        self,
        policy: TrustPolicySnapshot,
        *,
        writer_binding: SemanticWriterCommitBinding,
        complete_read_set_digest: str,
    ) -> tuple[str, ...]:
        """Catch up every due threshold in canonical order without sleeping."""

        applied: list[str] = []
        self.reconcile_trust_decay(
            policy,
            writer_binding=writer_binding,
            complete_read_set_digest=complete_read_set_digest,
        )
        while True:
            authorization = self._writers._authorize_atomic(
                writer_binding,
                capability=self._write_capability,
            )
            prepared = self._projection_scheduler.prepare_next_due(
                policy,
                writer_epoch=writer_binding.expected_writer_epoch,
                complete_read_set_digest=complete_read_set_digest,
                authorization=authorization,
            )
            if prepared is None:
                return tuple(applied)
            self._commit_trust_decay_publication(
                prepared,
                writer_binding=writer_binding,
                authorization=authorization,
            )
            applied.extend(prepared.executed_command_digests)

    def _commit_trust_decay_publication(
        self,
        prepared: PreparedTrustDecayPublication,
        *,
        writer_binding: SemanticWriterCommitBinding,
        authorization: SemanticWriterWriteAuthorization,
    ) -> None:
        from memorii.core.semantic_ingestion.event_replay import (
            advance_semantic_replay_authority,
            create_replay_checkpoint,
        )

        if not prepared.projection.records:
            return
        prior = self.semantic_replay_authority()
        bindings = self._projection_history.replay_bindings_with_trust(
            prepared.projection
        )
        conflict_binding = self._projection_history.semantic_conflict_replay_binding(
            pending_records=prepared.projection.records,
        )
        checkpoint = None
        if prior.latest_checkpoint is not None:
            checkpoint = create_replay_checkpoint(
                state=prior.graph_state,
                watermark_batch=prior.latest_checkpoint.watermark_batch,
                writer_epoch=writer_binding.expected_writer_epoch,
                authority=self._checkpoint_resume_authority,
                created_at=self._now(),
                reconstructed_replay_authority_digest=(
                    prior.reconstructed_authority_digest
                ),
                projection_history_bindings=bindings,
                semantic_conflict_replay_binding=conflict_binding,
            )
        aggregate = advance_semantic_replay_authority(
            prior,
            graph_state=prior.graph_state,
            member_bindings=(),
            reconstructed_authority_digest=prior.reconstructed_authority_digest,
            latest_checkpoint=checkpoint,
            projection_history_bindings=bindings,
            semantic_conflict_replay_binding=conflict_binding,
        )
        now = self._now()
        replay_records = (
            _semantic_replay_authority_record(aggregate, now),
            _semantic_checkpoint_lifecycle_record(
                self._checkpoint_resume_authority,
                now,
            ),
            _semantic_registry_history_record(
                self._event_schema_registry_history,
                now,
            ),
        )
        publication = prepared.projection.publication
        envelope = _projection_publication_envelope_record(
            publication_kind=prepared.publication_kind,
            projection_kind="trust",
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            operation_id=prepared.operation_id,
            authority_coordinate_digest=prepared.command_digest,
            policy_snapshot_digest=prepared.policy_snapshot_digest,
            active_policy_fingerprint=(
                publication.active_pointer.policy_fingerprint
            ),
            complete_read_set_digest=(
                publication.certificate.complete_read_set_digest
            ),
            writer_epoch=writer_binding.expected_writer_epoch,
            certificate_digest=publication.certificate.certificate_digest,
            generation_digest=publication.generation.generation_digest,
            pointer_digest=publication.active_pointer.pointer_digest,
            pointer_publication_kind=(
                publication.active_pointer.publication_kind
            ),
            timestamp=now,
        )
        self._memory_plane.conditionally_write_records(
            (
                *replay_records,
                *prepared.projection.records,
                *prepared.command_records,
                envelope,
            ),
            preconditions=(
                *self._semantic_authority_record_preconditions(
                    replay_records,
                    require_unfrozen=True,
                ),
                *prepared.projection.preconditions,
                *prepared.command_preconditions,
                RecordAbsentPrecondition(memory_id=envelope.memory_id),
            ),
            authorization=authorization,
        )

    def _current_projection_replay_authority(
        self,
    ) -> tuple[str, tuple[ProjectionHistoryReplayBinding, ...]]:
        aggregate = self.semantic_replay_authority()
        return (
            aggregate.graph_state.graph_revision,
            aggregate.projection_history_bindings,
        )

    @property
    def has_replay_integrity_composition(self) -> bool:
        return self._semantic_freeze_guard is not None and self._semantic_integrity_incident_reporter is not None

    @property
    def semantic_integrity_linearization(self) -> ReplayIntegrityLinearizer | None:
        return self._semantic_integrity_linearization

    def semantic_integrity_generation_digest(self) -> str:
        """Digest the retained atomic generation/event/replay authority."""

        return _semantic_integrity_digest(
            _SEMANTIC_INTEGRITY_GENERATION_DOMAIN,
            tuple(record.model_dump(mode="python") for record in self._semantic_integrity_authority_records()),
        )

    def semantic_integrity_snapshot(self):
        """Return the production integrity snapshot for the atomic authority."""

        from memorii.core.memory_evolution.conflict_integrity import (
            ConflictRepositoryIntegritySnapshot,
            ConflictRepositoryPartitionSnapshot,
        )

        records = self._semantic_integrity_authority_records()
        retained: set[str] = set()
        for record in records:
            retained.add(record_digest(record))
            retained.add(sha256(encode_typed_value(record.content)).hexdigest())
            retained.update(_nested_semantic_integrity_digests(record.content))
            if record.source_kind == "semantic_ingestion_event_batch":
                try:
                    from memorii.core.semantic_ingestion.event_replay import (
                        decode_semantic_memory_event_batch,
                    )

                    canonical_hex = record.content["canonical_hex"]
                    if isinstance(canonical_hex, str):
                        retained.add(
                            decode_semantic_memory_event_batch(
                                bytes.fromhex(canonical_hex),
                                registry_history=self._event_schema_registry_history,
                            ).source_event_batch_digest
                        )
                except (KeyError, TypeError, ValueError):
                    pass
        generation_digest = self.semantic_integrity_generation_digest()
        partition = ConflictRepositoryPartitionSnapshot(
            partition_id="global",
            scope_digest=_semantic_integrity_digest(
                b"memorii.semantic-ingestion.atomic-integrity-scope.v1\0",
                generation_digest,
            ),
            retained_byte_digests=tuple(sorted(retained)),
        )
        event_sequences = sorted(
            int(record.memory_id.rsplit(":", 1)[1])
            for record in records
            if record.source_kind == "semantic_ingestion_event_batch" and record.memory_id.rsplit(":", 1)[-1].isdigit()
        )
        last_sequence = 0
        for sequence in event_sequences:
            if sequence != last_sequence + 1:
                break
            last_sequence = sequence
        return ConflictRepositoryIntegritySnapshot.create(
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            partitions=(partition,),
            conflict_ledger_start_coordinate=0,
            conflict_ledger_end_coordinate=len(records),
            last_verified_event_batch_sequence=last_sequence,
            store_topology_fingerprint=_semantic_integrity_digest(
                b"memorii.semantic-ingestion.atomic-integrity-topology.v1\0",
                tuple((record.memory_id, record.source_kind) for record in records),
            ),
        )

    def retain_semantic_clean_recovery_request(self, request) -> None:
        """Durably retain one typed privileged recovery request exactly once."""

        from memorii.core.memory_evolution.conflict_integrity import (
            SemanticEventCleanRecoveryRequest,
        )

        try:
            validated = SemanticEventCleanRecoveryRequest.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("clean recovery request is invalid") from exc
        if validated.repository_id != _SEMANTIC_EVENT_REPOSITORY_ID:
            raise PreplanningStoreError("clean recovery request is cross-repository")
        record = _semantic_clean_recovery_request_record(validated, self._now())
        existing = self._memory_plane.get_record(record.memory_id)
        if existing is not None:
            if existing.source_kind != record.source_kind or existing.content != record.content:
                raise PreplanningStoreError("clean recovery request is substituted")
            return
        writer_binding = self._writers.commit_binding(self._writers.current())
        writer_record = self._writers.require_current(writer_binding)
        try:
            self._memory_plane.conditionally_write_records(
                (record,),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=record.memory_id),
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id,
                        expected_digest=record_digest(writer_record),
                    ),
                ),
                authorization=self._writers._authorize_atomic(writer_binding, capability=self._write_capability),
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._memory_plane.get_record(record.memory_id)
            if existing is None or existing.source_kind != record.source_kind or existing.content != record.content:
                raise PreplanningStoreError("clean recovery request publication contended") from exc

    def _semantic_recovery_configuration_authority(
        self,
    ) -> tuple[CanonicalMemoryRecord, CanonicalMemoryRecord]:
        """Require the exact persisted replay configuration used for recovery."""

        from memorii.core.semantic_ingestion.event_replay import (
            decode_event_schema_registry_history,
            decode_replay_checkpoint_lifecycle,
        )

        lifecycle_record = self._memory_plane.get_record(_semantic_checkpoint_lifecycle_id())
        history_record = self._memory_plane.get_record(_semantic_registry_history_id())
        if lifecycle_record is None or history_record is None:
            raise PreplanningStoreError("semantic recovery configuration authority is partial")
        if (
            lifecycle_record.source_kind != "semantic_ingestion_checkpoint_lifecycle"
            or lifecycle_record.content.get("semantic_ingestion_kind") != "semantic_replay_checkpoint_lifecycle"
            or history_record.source_kind != "semantic_ingestion_event_schema_registry_history"
            or history_record.content.get("semantic_ingestion_kind") != "semantic_event_schema_registry_history"
        ):
            raise PreplanningStoreError("semantic recovery configuration authority is substituted")
        try:
            lifecycle_hex = lifecycle_record.content["canonical_hex"]
            history_hex = history_record.content["canonical_hex"]
            if not isinstance(lifecycle_hex, str) or not isinstance(history_hex, str):
                raise TypeError
            lifecycle = decode_replay_checkpoint_lifecycle(bytes.fromhex(lifecycle_hex))
            history = decode_event_schema_registry_history(bytes.fromhex(history_hex))
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("semantic recovery configuration authority is corrupt") from exc
        if (
            lifecycle != self._checkpoint_resume_authority.lifecycle
            or history != self._event_schema_registry_history
            or lifecycle.registry_history_digest != history.history_digest
            or lifecycle_record.content.get("authority_digest") != lifecycle.authority_digest
            or history_record.content.get("history_digest") != history.history_digest
        ):
            raise PreplanningStoreError("semantic recovery configuration authority is stale or substituted")
        return lifecycle_record, history_record

    def _accepted_clarification_recovery_authorities(
        self,
    ) -> tuple[CanonicalMemoryRecord, ...]:
        """Prove accepted clarification closures and authorities are bijective."""

        transactions = self._memory_plane.list_records(
            source_kind=("semantic_ingestion_conflict_clarification_transaction")
        )
        receipts = self._memory_plane.list_records(source_kind="semantic_ingestion_conflict_clarification_receipt")
        authorities = self._memory_plane.list_records(
            source_kind=("semantic_ingestion_conflict_clarification_recovery_authority")
        )
        receipt_by_id = {record.memory_id: record for record in receipts}
        authority_by_id = {record.memory_id: record for record in authorities}
        if (
            len(receipt_by_id) != len(receipts)
            or len(authority_by_id) != len(authorities)
        ):
            raise PreplanningStoreError("clarification recovery closure cardinality failure")
        used_receipt_ids: set[str] = set()
        used_authority_ids: set[str] = set()
        accepted_event_ids: dict[str, str] = {}
        accepted_operations: set[str] = set()
        retained: list[tuple[int, CanonicalMemoryRecord]] = []
        for transaction_record in transactions:
            try:
                body = transaction_record.content["transaction"]
                if not isinstance(body, dict):
                    raise TypeError
                processing_operation_id = body["processing_operation_id"]
                if not isinstance(processing_operation_id, str):
                    raise TypeError
            except (KeyError, TypeError, ValueError) as exc:
                raise PreplanningStoreError("clarification recovery transaction closure is corrupt") from exc
            if processing_operation_id in accepted_operations:
                raise PreplanningStoreError("clarification recovery transaction closure is duplicated")
            receipt_record_id = _conflict_clarification_receipt_id(processing_operation_id)
            receipt_record = receipt_by_id.get(receipt_record_id)
            receipt = self._decode_conflict_clarification_pair(
                processing_operation_id,
                transaction_record=transaction_record,
                receipt_record=receipt_record,
                verify_event_effect=False,
                verify_generation_authority=False,
                offline_recovery=True,
            )
            if receipt is None or receipt_record is None:
                raise PreplanningStoreError("clarification recovery transaction closure is orphaned")
            used_receipt_ids.add(receipt_record_id)
            if receipt.committed_outcome != "accepted":
                continue
            if processing_operation_id in accepted_operations:
                raise PreplanningStoreError("accepted clarification recovery closure is duplicated")
            accepted_operations.add(processing_operation_id)
            event_record_id = body.get("semantic_event_batch_id")
            authority_record_id = body.get("semantic_recovery_authority_id")
            if (
                not isinstance(event_record_id, str)
                or not isinstance(authority_record_id, str)
                or event_record_id in accepted_event_ids
                or authority_record_id in used_authority_ids
            ):
                raise PreplanningStoreError("accepted clarification recovery closure cardinality failure")
            authority_record = authority_by_id.get(authority_record_id)
            if authority_record is None:
                raise PreplanningStoreError("accepted clarification recovery closure is incomplete")
            authority_batch = self._validate_clarification_recovery_authority(
                authority_record=authority_record,
                expected_transaction_record=transaction_record,
                expected_receipt_record=receipt_record,
            )
            if authority_record_id != _conflict_clarification_recovery_authority_id(
                processing_operation_id
            ) or event_record_id != _semantic_event_batch_id(authority_batch.log_position.sequence):
                raise PreplanningStoreError("accepted clarification recovery closure is cross-bound")
            accepted_event_ids[event_record_id] = processing_operation_id
            used_authority_ids.add(authority_record_id)
            retained.append((authority_batch.log_position.sequence, authority_record))
        if used_receipt_ids != set(receipt_by_id):
            raise PreplanningStoreError("clarification recovery receipt closure is orphaned")
        if used_authority_ids != set(authority_by_id):
            raise PreplanningStoreError("clarification recovery authority closure is orphaned")
        retained.sort(key=lambda item: item[0])
        return tuple(record for _, record in retained)

    def _retained_semantic_clean_authority(self):
        """Derive the complete canonical event source sequence from generations."""

        from memorii.core.memory_evolution.conflict_integrity import (
            ConflictIntegrityError,
            SemanticEventCleanAuthorityBatch,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            SemanticReplayAuthorityMemberBinding,
            decode_semantic_memory_event_batch,
        )

        try:
            clarification_authorities = self._accepted_clarification_recovery_authorities()
        except PreplanningStoreError as exc:
            raise ConflictIntegrityError("clean_recovery_authority_invalid") from exc
        member_records = self._memory_plane.list_records(source_kind="semantic_ingestion_generation_member")
        members_by_id = {record.memory_id: record for record in member_records}
        if len(members_by_id) != len(member_records):
            raise ConflictIntegrityError("clean_recovery_authority_invalid")
        retained: list[tuple[int, SemanticEventCleanAuthorityBatch]] = []
        replay_bindings: list[SemanticReplayAuthorityMemberBinding] = []
        referenced_member_ids: set[str] = set()
        manifests = self._memory_plane.list_records(source_kind="semantic_ingestion_generation_manifest")
        for manifest in sorted(manifests, key=lambda record: record.memory_id):
            try:
                generation = manifest.content["generation"]
                manifest_members = tuple(
                    AtomicGenerationMember.model_validate(item) for item in manifest.content["members"]
                )
                if (
                    not isinstance(generation, int)
                    or generation < 2
                    or manifest.content.get("semantic_ingestion_kind") != "generation_manifest"
                    or set(manifest.content)
                    != {
                        "semantic_ingestion_kind",
                        "generation",
                        "request_digest",
                        "members",
                        "required_artifact_digests",
                    }
                    or not isinstance(manifest.content.get("request_digest"), str)
                    or len(manifest.content["request_digest"]) != 64
                    or not isinstance(
                        manifest.content.get("required_artifact_digests"),
                        (tuple, list),
                    )
                    or not manifest.memory_id.endswith(f":{generation}:manifest")
                    or tuple(member.member_id for member in manifest_members)
                    != tuple(sorted({member.member_id for member in manifest_members}))
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError) as exc:
                raise ConflictIntegrityError("clean_recovery_authority_invalid") from exc
            member_prefix = manifest.memory_id[: -len("manifest")]
            manifest_prefix = "semantic_ingestion:generation:"
            manifest_suffix = f":{generation}:manifest"
            operation_fence_id = manifest.memory_id[
                len(manifest_prefix) : -len(manifest_suffix)
            ]
            if not manifest.memory_id.startswith(manifest_prefix) or not operation_fence_id:
                raise ConflictIntegrityError("clean_recovery_authority_invalid")
            for member in manifest_members:
                member_record_id = f"{member_prefix}{member.member_id}"
                member_record = members_by_id.get(member_record_id)
                if (
                    member_record is None
                    or member_record.content.get("semantic_ingestion_kind") != "generation_member"
                    or member_record.content.get("member") != member.model_dump(mode="json")
                    or sha256(member.canonical_payload).hexdigest() != member.payload_digest
                ):
                    raise ConflictIntegrityError("clean_recovery_authority_invalid")
                referenced_member_ids.add(member_record_id)
                if member.kind in {
                    "observation_delta",
                    "progress",
                    "replay_artifact",
                    "artifact_index",
                    "artifact_closure",
                }:
                    replay_bindings.append(
                        SemanticReplayAuthorityMemberBinding.create(
                            operation_fence_id=operation_fence_id,
                            generation=generation,
                            member_id=member.member_id,
                            member_kind=member.kind,
                            payload_digest=member.payload_digest,
                        )
                    )
                if member.kind != "event_batch":
                    continue
                try:
                    batch = decode_semantic_memory_event_batch(
                        member.canonical_payload,
                        registry_history=self._event_schema_registry_history,
                    )
                except (TypeError, ValueError) as exc:
                    raise ConflictIntegrityError("clean_recovery_authority_invalid") from exc
                retained.append(
                    (
                        batch.log_position.sequence,
                        SemanticEventCleanAuthorityBatch(
                            source_id=_semantic_event_batch_id(batch.log_position.sequence),
                            canonical_batch_bytes=member.canonical_payload,
                            source_digest=member.payload_digest,
                        ),
                    )
                )
        for authority_record in clarification_authorities:
            try:
                batch = self._validate_clarification_recovery_authority(
                    authority_record=authority_record,
                )
            except PreplanningStoreError as exc:
                raise ConflictIntegrityError("clean_recovery_authority_invalid") from exc
            canonical_hex = authority_record.content.get("event_batch_canonical_hex")
            if not isinstance(canonical_hex, str):
                raise ConflictIntegrityError("clean_recovery_authority_invalid")
            canonical_bytes = bytes.fromhex(canonical_hex)
            retained.append(
                (
                    batch.log_position.sequence,
                    SemanticEventCleanAuthorityBatch(
                        source_id=_semantic_event_batch_id(batch.log_position.sequence),
                        canonical_batch_bytes=canonical_bytes,
                        source_digest=sha256(canonical_bytes).hexdigest(),
                    ),
                )
            )
        retained.sort(key=lambda item: item[0])
        sequences = tuple(sequence for sequence, _ in retained)
        sources = tuple(source for _, source in retained)
        binding_kind_order = {
            "observation_delta": 0,
            "progress": 1,
            "replay_artifact": 2,
            "artifact_index": 2,
            "artifact_closure": 2,
        }
        replay_bindings.sort(
            key=lambda item: (
                binding_kind_order[item.member_kind],
                item.operation_fence_id,
                item.generation,
                item.member_id,
            )
        )
        replay_binding_keys = tuple(
            (item.operation_fence_id, item.generation, item.member_id)
            for item in replay_bindings
        )
        if (
            not sources
            or referenced_member_ids != set(members_by_id)
            or sequences != tuple(range(1, len(sources) + 1))
            or len({source.source_id for source in sources}) != len(sources)
            or len({source.source_digest for source in sources}) != len(sources)
            or len(replay_binding_keys) != len(set(replay_binding_keys))
        ):
            raise ConflictIntegrityError("clean_recovery_authority_invalid")
        return sources, tuple(replay_bindings)

    def _validate_clarification_recovery_authority(
        self,
        *,
        authority_record: CanonicalMemoryRecord,
        expected_transaction_record: CanonicalMemoryRecord | None = None,
        expected_receipt_record: CanonicalMemoryRecord | None = None,
    ) -> SemanticMemoryEventBatch:
        """Verify clarification provenance without trusting active replay mirrors."""

        from memorii.core.semantic_ingestion.contracts import (
            SemanticGraphDelta,
            SemanticTerminalOutcome,
            decode_semantic_contract,
            encode_semantic_contract,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            decode_semantic_memory_event_batch,
            decode_semantic_replay_authority,
            validate_replay_checkpoint,
        )

        try:
            if (
                authority_record.source_kind != "semantic_ingestion_conflict_clarification_recovery_authority"
                or authority_record.content.get("semantic_ingestion_kind")
                != "conflict_clarification_recovery_authority"
                or set(authority_record.content)
                != {
                    "semantic_ingestion_kind",
                    "binding",
                    "event_batch_canonical_hex",
                    "replay_aggregate_canonical_hex",
                }
            ):
                raise ValueError("clarification recovery authority kind mismatch")
            binding = ClarificationEventRecoveryAuthorityBinding.model_validate(authority_record.content["binding"])
            event_hex = authority_record.content["event_batch_canonical_hex"]
            replay_hex = authority_record.content["replay_aggregate_canonical_hex"]
            if not isinstance(event_hex, str) or not isinstance(replay_hex, str):
                raise TypeError("clarification recovery payload is invalid")
            event_payload = bytes.fromhex(event_hex)
            replay_payload = bytes.fromhex(replay_hex)
            if (
                authority_record.memory_id != binding.authority_record_id
                or sha256(event_payload).hexdigest() != binding.event_payload_digest
                or sha256(replay_payload).hexdigest() != binding.replay_aggregate_payload_digest
            ):
                raise ValueError("clarification recovery payload mismatch")
            transaction_record = self._memory_plane.get_record(binding.transaction_record_id)
            receipt_record = self._memory_plane.get_record(binding.receipt_record_id)
            if (
                transaction_record is None
                or receipt_record is None
                or (expected_transaction_record is not None and transaction_record != expected_transaction_record)
                or (expected_receipt_record is not None and receipt_record != expected_receipt_record)
                or record_digest(transaction_record) != binding.transaction_record_digest
                or record_digest(receipt_record) != binding.receipt_record_digest
            ):
                raise ValueError("clarification transaction provenance mismatch")
            receipt = self._decode_conflict_clarification_pair(
                binding.processing_operation_id,
                transaction_record=transaction_record,
                receipt_record=receipt_record,
                verify_event_effect=False,
                verify_generation_authority=False,
                offline_recovery=True,
            )
            if receipt is None:
                raise ValueError("clarification receipt provenance is absent")
            body = transaction_record.content["transaction"]
            terminal_payload = bytes.fromhex(body["semantic_terminal_hex"])
            graph_delta_payload = bytes.fromhex(body["graph_delta_hex"])
            terminal = decode_semantic_contract(
                terminal_payload,
                SemanticTerminalOutcome,
            )
            graph_delta = decode_semantic_contract(
                graph_delta_payload,
                SemanticGraphDelta,
            )
            batch = decode_semantic_memory_event_batch(
                event_payload,
                registry_history=self._event_schema_registry_history,
            )
            aggregate = decode_semantic_replay_authority(replay_payload)
            aggregate_bindings = (
                *aggregate.observation_bindings,
                *aggregate.progress_bindings,
                *aggregate.artifact_bindings,
            )
            reconstructed = self._reconstruct_semantic_replay_authority(
                graph_state=aggregate.graph_state,
                bindings=aggregate_bindings,
            )
            checkpoint_state = (
                validate_replay_checkpoint(
                    aggregate.latest_checkpoint,
                    authority=self._checkpoint_resume_authority,
                    projection_history_verifier=self._projection_history,
                    semantic_conflict_verifier=self._projection_history,
                )
                if aggregate.latest_checkpoint is not None
                else None
            )
            if (
                body["processing_operation_id"] != binding.processing_operation_id
                or body["semantic_recovery_authority_generation"] != binding.generation
                or body["semantic_recovery_authority_id"] != authority_record.memory_id
                or body["semantic_event_batch_id"] != binding.event_batch_record_id
                or body["semantic_event_batch_digest"] != binding.source_event_batch_digest
                or body["graph_revision_before"] != binding.graph_revision_before
                or body["graph_revision_after"] != binding.graph_revision_after
                or terminal_payload != encode_semantic_contract(terminal)
                or graph_delta_payload != encode_semantic_contract(graph_delta)
                or terminal.terminal_digest != receipt.semantic_result_digest
                or graph_delta.delta_digest != body["graph_delta_digest"]
                or batch.log_position.sequence != binding.event_batch_sequence
                or batch.source_event_batch_digest != binding.source_event_batch_digest
                or batch.event_batch_digest != binding.event_batch_digest
                or batch.transaction_group_id != binding.processing_operation_id
                or batch.operation_fence_id != binding.processing_operation_id
                or batch.graph_delta_digest != graph_delta.delta_digest
                or batch.events[0].payload.graph_revision_before != binding.graph_revision_before
                or batch.events[-1].payload.graph_revision_after != binding.graph_revision_after
                or aggregate.aggregate_digest != binding.replay_aggregate_digest
                or aggregate.reconstructed_authority_digest
                != reconstructed.authority_digest
                or aggregate.graph_state.last_batch_position != batch.log_position
                or aggregate.graph_state.last_event_batch_digest != batch.source_event_batch_digest
                or aggregate.graph_state.graph_revision != binding.graph_revision_after
                or aggregate.latest_checkpoint is None
                or aggregate.latest_checkpoint.watermark_batch != batch
                or aggregate.latest_checkpoint.materialized_snapshot != aggregate.graph_state
                or checkpoint_state != aggregate.graph_state
            ):
                raise ValueError("clarification recovery authority mismatch")
            return batch
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("clarification recovery authority integrity failure") from exc

    def _validated_semantic_clean_recovery_plan(
        self,
        request,
        *,
        expected_status: Literal["prepared", "activated"] = "prepared",
        require_retained_corrupt_generation: bool = True,
    ):
        """Recompute every prepared clean-generation closure before release."""

        from memorii.core.memory_evolution.conflict_integrity import (
            ConflictCleanReplayVerification,
            ConflictIntegrityError,
            SemanticEventCleanRecoveryRequest,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            decode_semantic_memory_event_batch,
            decode_semantic_replay_authority,
            decode_semantic_replay_state,
            encode_semantic_replay_authority,
            encode_semantic_replay_state,
            replay_semantic_event_batches,
            validate_replay_checkpoint,
        )

        try:
            validated = SemanticEventCleanRecoveryRequest.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("clean_recovery_request_invalid") from exc
        plan_record = self._memory_plane.get_record(_semantic_clean_generation_id(validated.request_digest))
        status_record = self._memory_plane.get_record(_semantic_clean_generation_status_id(validated.request_digest))
        request_record = self._memory_plane.get_record(_semantic_clean_recovery_request_id(validated.request_digest))
        if plan_record is None or status_record is None or request_record is None:
            raise ConflictIntegrityError("clean_recovery_generation_absent")
        try:
            request_hex = request_record.content["canonical_hex"]
            plan_hex = plan_record.content["canonical_hex"]
            if not isinstance(request_hex, str) or not isinstance(plan_hex, str):
                raise TypeError
            retained_request = SemanticEventCleanRecoveryRequest.model_validate(
                decode_typed_value(bytes.fromhex(request_hex))
            )
            plan = decode_typed_value(bytes.fromhex(plan_hex))
            if not isinstance(plan, dict):
                raise TypeError
            batches = tuple(
                decode_semantic_memory_event_batch(
                    value,
                    registry_history=self._event_schema_registry_history,
                )
                for value in plan["canonical_batches"]
            )
            state = decode_semantic_replay_state(plan["replay_state"])
            aggregate = decode_semantic_replay_authority(plan["replay_aggregate"])
            verification = ConflictCleanReplayVerification.model_validate(plan["verification"])
            authority_record_digests = tuple(
                (str(memory_id), str(digest)) for memory_id, digest in plan["authority_record_digests"]
            )
            retained_authority_records = tuple(
                CanonicalMemoryRecord.model_validate(value) for value in plan["retained_authority_records"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("clean_recovery_generation_substituted") from exc

        try:
            self._semantic_recovery_configuration_authority()
            retained_sources, retained_bindings = self._retained_semantic_clean_authority()
        except PreplanningStoreError as exc:
            raise ConflictIntegrityError("clean_recovery_authority_invalid") from exc
        current_authority_records = self._semantic_clean_recovery_authority_records()
        current_authority_digests = tuple(
            (record.memory_id, record_digest(record)) for record in current_authority_records
        )
        try:
            replayed = replay_semantic_event_batches(
                repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                batches=batches,
                registry_history=self._event_schema_registry_history,
            )
            reconstructed = self._reconstruct_semantic_replay_authority(
                graph_state=replayed,
                bindings=retained_bindings,
            )
            projection_bindings = self._projection_history.replay_bindings()
            if aggregate.latest_checkpoint is not None:
                checkpoint_state = validate_replay_checkpoint(
                    aggregate.latest_checkpoint,
                    authority=self._checkpoint_resume_authority,
                    projection_history_verifier=self._projection_history,
                    semantic_conflict_verifier=self._projection_history,
                )
            else:
                checkpoint_state = None
        except (PreplanningStoreError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("clean_recovery_replay_failed") from exc
        clean_body = {
            "request_digest": validated.request_digest,
            "canonical_batches": plan["canonical_batches"],
            "replay_state": encode_semantic_replay_state(replayed),
            "replay_aggregate": encode_semantic_replay_authority(aggregate),
            "retained_corrupt_generation_digest": (validated.retained_corrupt_generation_digest),
        }
        clean_generation_digest = _semantic_integrity_digest(_SEMANTIC_CLEAN_GENERATION_DOMAIN, clean_body)
        expected_final_digest = replayed.last_event_batch_digest or _semantic_integrity_digest(
            b"memorii.semantic-event-empty-log.v1\0",
            _SEMANTIC_EVENT_REPOSITORY_ID,
        )
        if (
            retained_request != validated
            or validated.authority_batches != retained_sources
            or validated.authority_source_digests != tuple(sorted(source.source_digest for source in retained_sources))
            or tuple(plan["canonical_batches"]) != tuple(source.canonical_batch_bytes for source in retained_sources)
            or request_record.content.get("request_digest") != validated.request_digest
            or plan_record.content.get("request_digest") != validated.request_digest
            or status_record.content.get("request_digest") != validated.request_digest
            or status_record.content.get("status") != expected_status
            or plan.get("request_digest") != validated.request_digest
            or plan.get("retained_corrupt_generation_digest") != validated.retained_corrupt_generation_digest
            or (
                require_retained_corrupt_generation
                and self.semantic_integrity_generation_digest()
                != validated.retained_corrupt_generation_digest
            )
            or authority_record_digests != current_authority_digests
            # The retained plan decodes canonical content into tuples while
            # the reopened plane returns JSON-parsed lists, so record-object
            # equality is container-type noise: authority identity is the
            # durable (memory id, record digest) pair, already the basis of
            # the digest comparison above.
            or tuple(
                (record.memory_id, record_digest(record))
                for record in retained_authority_records
            ) != current_authority_digests
            or replayed != state
            or aggregate.graph_state != replayed
            or (
                *aggregate.observation_bindings,
                *aggregate.progress_bindings,
                *aggregate.artifact_bindings,
            )
            != retained_bindings
            or aggregate.reconstructed_authority_digest != reconstructed.authority_digest
            or aggregate.projection_history_bindings != projection_bindings
            or aggregate.aggregate_revision != 1
            or (bool(batches) and checkpoint_state != replayed)
            or (not batches and aggregate.latest_checkpoint is not None)
            or clean_generation_digest != plan.get("clean_generation_digest")
            or status_record.content.get("clean_generation_digest") != clean_generation_digest
            or verification.repository_id != _SEMANTIC_EVENT_REPOSITORY_ID
            or verification.clean_generation_id != validated.request_digest
            or verification.clean_generation_digest != clean_generation_digest
            or verification.retained_corrupt_generation_digest != validated.retained_corrupt_generation_digest
            or verification.repaired_partition_ids != validated.repaired_partition_ids
            or verification.retained_conflicting_byte_digests != validated.retained_conflicting_byte_digests
            or verification.authority_source_digests != validated.authority_source_digests
            or verification.replay_start_event_batch_sequence != 0
            or verification.replay_final_event_batch_sequence != len(batches)
            or verification.replay_final_batch_digest != expected_final_digest
            or verification.replay_repository_state_digest != replayed.state_digest
        ):
            raise ConflictIntegrityError("clean_recovery_generation_substituted")
        return (
            validated,
            plan,
            batches,
            state,
            aggregate,
            authority_record_digests,
            plan_record,
            status_record,
            request_record,
            verification,
        )

    def prepare_semantic_clean_recovery(
        self,
        repaired_partition_ids: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
    ):
        """Build and independently replay a clean generation without activating it."""

        from memorii.core.memory_evolution.conflict_integrity import (
            ConflictCleanReplayVerification,
            ConflictIntegrityError,
            SemanticEventCleanRecoveryRequest,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            SemanticReplayAuthorityAggregate,
            advance_semantic_replay_authority,
            create_replay_checkpoint,
            decode_semantic_memory_event_batch,
            encode_semantic_memory_event_batch,
            encode_semantic_replay_authority,
            encode_semantic_replay_state,
            replay_semantic_event_batches,
        )

        try:
            self._semantic_recovery_configuration_authority()
            retained_sources, retained_bindings = self._retained_semantic_clean_authority()
        except PreplanningStoreError as exc:
            raise ConflictIntegrityError("clean_recovery_authority_invalid") from exc
        expected_authority_source_digests = tuple(sorted(source.source_digest for source in retained_sources))
        if authority_source_digests != expected_authority_source_digests:
            raise ConflictIntegrityError("clean_recovery_authority_invalid")
        current_generation_digest = self.semantic_integrity_generation_digest()
        candidates = []
        for record in self._memory_plane.list_records(source_kind="semantic_ingestion_clean_recovery_request"):
            try:
                canonical_hex = record.content["canonical_hex"]
                if not isinstance(canonical_hex, str):
                    raise TypeError
                candidate = SemanticEventCleanRecoveryRequest.model_validate(
                    decode_typed_value(bytes.fromhex(canonical_hex))
                )
            except (KeyError, TypeError, ValueError):
                continue
            if (
                candidate.repaired_partition_ids == repaired_partition_ids
                and candidate.retained_conflicting_byte_digests == retained_conflicting_byte_digests
                and candidate.authority_source_digests == authority_source_digests
                and candidate.retained_corrupt_generation_digest == current_generation_digest
            ):
                candidates.append(candidate)
        if len(candidates) != 1:
            raise ConflictIntegrityError("clean_recovery_request_invalid")
        request = candidates[0]
        if (
            request.retained_corrupt_generation_digest != current_generation_digest
            or request.authority_batches != retained_sources
            or request.authority_source_digests != expected_authority_source_digests
            or not set(retained_conflicting_byte_digests)
            <= set(self.semantic_integrity_snapshot().partitions[0].retained_byte_digests)
        ):
            raise ConflictIntegrityError("clean_recovery_request_invalid")
        existing_plan = self._memory_plane.get_record(_semantic_clean_generation_id(request.request_digest))
        if existing_plan is not None:
            existing_status = self._memory_plane.get_record(
                _semantic_clean_generation_status_id(request.request_digest)
            )
            if existing_status is None:
                raise ConflictIntegrityError("clean_recovery_generation_substituted")
            *_, retained_verification = self._validated_semantic_clean_recovery_plan(request)
            if (
                retained_verification.repaired_partition_ids != repaired_partition_ids
                or retained_verification.retained_conflicting_byte_digests != retained_conflicting_byte_digests
                or retained_verification.authority_source_digests != authority_source_digests
            ):
                raise ConflictIntegrityError("clean_recovery_generation_substituted")
            return retained_verification

        try:
            batches = tuple(
                decode_semantic_memory_event_batch(
                    source.canonical_batch_bytes,
                    registry_history=self._event_schema_registry_history,
                )
                for source in request.authority_batches
            )
            state = replay_semantic_event_batches(
                repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                batches=batches,
                registry_history=self._event_schema_registry_history,
            )
            reconstructed = self._reconstruct_semantic_replay_authority(
                graph_state=state,
                bindings=retained_bindings,
            )
            projection_bindings = self._projection_history.replay_bindings()
            conflict_binding = self._projection_history.semantic_conflict_replay_binding()
            checkpoint = (
                create_replay_checkpoint(
                    state=state,
                    watermark_batch=batches[-1],
                    writer_epoch=batches[-1].writer_epoch,
                    authority=self._checkpoint_resume_authority,
                    created_at=self._now(),
                    reconstructed_replay_authority_digest=(reconstructed.authority_digest),
                    projection_history_bindings=projection_bindings,
                    semantic_conflict_replay_binding=conflict_binding,
                )
                if batches
                else None
            )
            aggregate = advance_semantic_replay_authority(
                SemanticReplayAuthorityAggregate.genesis(
                    _SEMANTIC_EVENT_REPOSITORY_ID
                ),
                graph_state=state,
                member_bindings=retained_bindings,
                reconstructed_authority_digest=reconstructed.authority_digest,
                latest_checkpoint=checkpoint,
                projection_history_bindings=projection_bindings,
                semantic_conflict_replay_binding=conflict_binding,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("clean_recovery_replay_failed") from exc
        canonical_batches = tuple(encode_semantic_memory_event_batch(batch) for batch in batches)
        clean_body = {
            "request_digest": request.request_digest,
            "canonical_batches": canonical_batches,
            "replay_state": encode_semantic_replay_state(state),
            "replay_aggregate": encode_semantic_replay_authority(aggregate),
            "retained_corrupt_generation_digest": (request.retained_corrupt_generation_digest),
        }
        clean_generation_digest = _semantic_integrity_digest(_SEMANTIC_CLEAN_GENERATION_DOMAIN, clean_body)
        if clean_generation_digest == request.retained_corrupt_generation_digest:
            raise ConflictIntegrityError("clean_recovery_generation_not_independent")
        verification = ConflictCleanReplayVerification.create(
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            repaired_partition_ids=repaired_partition_ids,
            retained_conflicting_byte_digests=retained_conflicting_byte_digests,
            authority_source_digests=authority_source_digests,
            clean_generation_id=request.request_digest,
            clean_generation_digest=clean_generation_digest,
            retained_corrupt_generation_digest=(request.retained_corrupt_generation_digest),
            replay_start_event_batch_sequence=0,
            replay_final_event_batch_sequence=len(batches),
            replay_final_batch_digest=(
                state.last_event_batch_digest
                or _semantic_integrity_digest(
                    b"memorii.semantic-event-empty-log.v1\0",
                    _SEMANTIC_EVENT_REPOSITORY_ID,
                )
            ),
            replay_repository_state_digest=state.state_digest,
            verified_at=self._now(),
        )
        authority_records = self._semantic_clean_recovery_authority_records()
        plan_body = {
            **clean_body,
            "clean_generation_digest": clean_generation_digest,
            "verification": verification.model_dump(mode="python"),
            "authority_record_digests": tuple(
                (record.memory_id, record_digest(record)) for record in authority_records
            ),
            "retained_authority_records": tuple(record.model_dump(mode="python") for record in authority_records),
        }
        plan = _semantic_clean_generation_record(request.request_digest, plan_body, self._now())
        status = _semantic_clean_generation_status_record(
            request.request_digest,
            clean_generation_digest=clean_generation_digest,
            status="prepared",
            timestamp=self._now(),
        )
        writer_binding = self._writers.commit_binding(self._writers.current())
        writer_record = self._writers.require_current(writer_binding)
        try:
            self._memory_plane.conditionally_write_records(
                (plan, status),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=plan.memory_id),
                    RecordAbsentPrecondition(memory_id=status.memory_id),
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id,
                        expected_digest=record_digest(writer_record),
                    ),
                ),
                authorization=self._writers._authorize_atomic(writer_binding, capability=self._write_capability),
            )
        except MemoryPlaneRevisionConflictError as exc:
            raise ConflictIntegrityError("clean_recovery_generation_contended") from exc
        return verification

    def activate_semantic_clean_recovery(self, request) -> None:
        """Atomically replace active event/replay mirrors from a prepared generation."""

        from memorii.core.memory_evolution.conflict_integrity import (
            ConflictIntegrityError,
            SemanticEventCleanRecoveryRequest,
        )

        validated = SemanticEventCleanRecoveryRequest.model_validate(request.model_dump(mode="python"))
        plan_record = self._memory_plane.get_record(_semantic_clean_generation_id(validated.request_digest))
        status_record = self._memory_plane.get_record(_semantic_clean_generation_status_id(validated.request_digest))
        if plan_record is None or status_record is None:
            raise ConflictIntegrityError("clean_recovery_generation_absent")
        if status_record.content.get("status") == "activated":
            self._validate_activated_semantic_clean_recovery(validated)
            return
        (
            validated,
            plan,
            batches,
            state,
            aggregate,
            authority_record_digests,
            plan_record,
            status_record,
            request_record,
            _,
        ) = self._validated_semantic_clean_recovery_plan(
            validated,
            # The plan's sealed verification already bound the request to the
            # corrupt generation at prepare time; the freeze step's quarantine
            # makes the live digest underivable afterwards, so activation
            # must not re-derive it (the reconcile boundary passes False for
            # the same reason).
            require_retained_corrupt_generation=False,
        )
        now = self._now()
        clean_records = [
            *(_semantic_event_batch_record(batch, now) for batch in batches),
            _semantic_replay_state_record(state, now),
            _semantic_replay_authority_record(aggregate, now),
        ]
        clean_ids = {record.memory_id for record in clean_records}
        for record in self._memory_plane.list_records(source_kind="semantic_ingestion_event_batch"):
            if record.memory_id not in clean_ids:
                clean_records.append(
                    _semantic_retained_event_slot_record(
                        record,
                        request_digest=validated.request_digest,
                        timestamp=now,
                    )
                )
        activated = _semantic_clean_generation_status_record(
            validated.request_digest,
            clean_generation_digest=plan["clean_generation_digest"],
            status="activated",
            timestamp=now,
        )
        preconditions: list[MemoryPlanePrecondition] = [
            RecordDigestPrecondition(memory_id=memory_id, expected_digest=digest)
            for memory_id, digest in authority_record_digests
        ]
        preconditions.append(
            RecordDigestPrecondition(
                memory_id=status_record.memory_id,
                expected_digest=record_digest(status_record),
            )
        )
        preconditions.extend(
            (
                RecordDigestPrecondition(
                    memory_id=plan_record.memory_id,
                    expected_digest=record_digest(plan_record),
                ),
                RecordDigestPrecondition(
                    memory_id=request_record.memory_id,
                    expected_digest=record_digest(request_record),
                ),
            )
        )
        existing_ids = {memory_id for memory_id, _ in authority_record_digests}
        for record in clean_records:
            if record.memory_id in existing_ids:
                continue
            current = self._memory_plane.get_record(record.memory_id)
            preconditions.append(
                RecordDigestPrecondition(
                    memory_id=record.memory_id,
                    expected_digest=record_digest(current),
                )
                if current is not None
                else RecordAbsentPrecondition(memory_id=record.memory_id)
            )
        writer_binding = self._writers.commit_binding(self._writers.current())
        writer_record = self._writers.require_current(writer_binding)
        preconditions.append(
            RecordDigestPrecondition(
                memory_id=writer_record.memory_id,
                expected_digest=record_digest(writer_record),
            )
        )
        try:
            self._memory_plane.conditionally_write_records(
                (*clean_records, activated),
                preconditions=tuple(preconditions),
                authorization=self._writers._authorize_atomic(writer_binding, capability=self._write_capability),
            )
        except MemoryPlaneRevisionConflictError as exc:
            raise ConflictIntegrityError("clean_recovery_activation_contended") from exc

    def _validate_activated_semantic_clean_recovery(self, request) -> None:
        """Prove an idempotent activation already installed the exact clean plan."""

        from memorii.core.memory_evolution.conflict_integrity import (
            ConflictIntegrityError,
        )

        (
            _,
            _,
            batches,
            state,
            aggregate,
            *_,
        ) = self._validated_semantic_clean_recovery_plan(
            request,
            expected_status="activated",
            require_retained_corrupt_generation=False,
        )
        active_event_records = self._memory_plane.list_records(
            source_kind="semantic_ingestion_event_batch"
        )
        expected_event_ids = {
            _semantic_event_batch_id(batch.log_position.sequence) for batch in batches
        }
        if {
            record.memory_id for record in active_event_records
        } != expected_event_ids:
            raise ConflictIntegrityError("clean_recovery_activation_substituted")
        for batch in batches:
            record = self._memory_plane.get_record(
                _semantic_event_batch_id(batch.log_position.sequence)
            )
            if record is None or record != _semantic_event_batch_record(
                batch,
                record.timestamp,
            ):
                raise ConflictIntegrityError("clean_recovery_activation_substituted")
        state_record = self._memory_plane.get_record(_semantic_replay_state_id())
        aggregate_record = self._memory_plane.get_record(
            _semantic_replay_authority_id()
        )
        if (
            state_record is None
            or aggregate_record is None
            or state_record
            != _semantic_replay_state_record(state, state_record.timestamp)
            or aggregate_record
            != _semantic_replay_authority_record(
                aggregate,
                aggregate_record.timestamp,
            )
        ):
            raise ConflictIntegrityError("clean_recovery_activation_substituted")

    def reconcile_semantic_clean_recovery(self, release_complete: bool) -> None:
        """Adopt a released-but-not-activated clean generation after restart."""

        if not release_complete:
            return
        from memorii.core.memory_evolution.conflict_integrity import (
            SemanticEventCleanRecoveryRequest,
        )

        recoveries = tuple(
            record
            for record in self._memory_plane.list_records(source_kind="semantic_ingestion_clean_generation_status")
            if record.content.get("status") in {"prepared", "activated"}
        )
        if len(recoveries) > 1:
            raise PreplanningStoreError("multiple clean recoveries await activation")
        if not recoveries:
            return
        request_digest = recoveries[0].content.get("request_digest")
        if not isinstance(request_digest, str):
            raise PreplanningStoreError("clean recovery status is corrupt")
        request_record = self._memory_plane.get_record(_semantic_clean_recovery_request_id(request_digest))
        if request_record is None:
            raise PreplanningStoreError("clean recovery request is absent")
        canonical_hex = request_record.content.get("canonical_hex")
        if not isinstance(canonical_hex, str):
            raise PreplanningStoreError("clean recovery request is corrupt")
        request = SemanticEventCleanRecoveryRequest.model_validate(decode_typed_value(bytes.fromhex(canonical_hex)))
        self.activate_semantic_clean_recovery(request)

    def _semantic_integrity_authority_records(
        self,
    ) -> tuple[CanonicalMemoryRecord, ...]:
        kinds = {
            "semantic_ingestion_generation_member",
            "semantic_ingestion_generation_manifest",
            "semantic_ingestion_event_batch",
            "semantic_ingestion_replay_state",
            "semantic_ingestion_replay_authority",
            "semantic_ingestion_checkpoint_lifecycle",
            "semantic_ingestion_event_schema_registry_history",
            "semantic_ingestion_conflict_clarification_transaction",
            "semantic_ingestion_conflict_clarification_receipt",
            "semantic_ingestion_conflict_clarification_recovery_authority",
        }
        return tuple(
            sorted(
                (record for record in self._memory_plane.list_records() if record.source_kind in kinds),
                key=lambda record: record.memory_id,
            )
        )

    def load_bootstrap_writer_handoff_marker_v3(
        self, *, operation_fence_binding: OperationFenceBinding
    ) -> BootstrapWriterHandoffMarkerV3 | None:
        """Load exactly one persisted V3 marker for an already-admitted fence."""
        matches: list[BootstrapWriterHandoffMarkerV3] = []
        for record in self._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_handoff_marker"
        ):
            try:
                marker = BootstrapWriterHandoffMarkerV3.model_validate(
                    record.content["marker"]
                )
            except (KeyError, TypeError, ValueError):
                continue
            if marker.operation_fence_binding == operation_fence_binding:
                matches.append(marker)
        return matches[0] if len(matches) == 1 else None

    def reload_bootstrap_recovery_replay_v3(
        self,
        *,
        recovery_key_digest: str,
        canonical_evidence_lease: CanonicalEvidenceLease | None = None,
        handoff_marker: BootstrapWriterHandoffMarkerV3 | None = None,
        tenant_partition_id: str | None = None,
    ) -> object | None:
        """Reload one exact found normalization closure; never scan generations."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapRecoveryFoundV3,
            BootstrapRecoveryReplayRecordV3,
            BootstrapSourceNormalizationRequestV3,
            BootstrapSourceNormalizationResultV3,
            contract_digest,
            decode_semantic_contract,
            encode_semantic_contract,
        )
        if canonical_evidence_lease is not None:
            if handoff_marker is None or tenant_partition_id is None:
                return None
            if not self._validate_recovery_prepared_lease(
                canonical_evidence_lease=canonical_evidence_lease,
                handoff_marker=handoff_marker,
                tenant_partition_id=tenant_partition_id,
            ):
                return None
        record = self._memory_plane.get_record(_bootstrap_v3_recovery_id(recovery_key_digest))
        if record is None or record.source_kind != "semantic_ingestion_bootstrap_v3_recovery_index":
            return None
        content = record.content
        try:
            if content["state"] != "found" or content["recovery_key_digest"] != recovery_key_digest:
                return None
            found_body = {name: content[name] for name in (
                "kind", "recovery_key_digest", "consumed_claim_digest",
                "recovery_control_snapshot_digest", "predecessor_operation_generation",
                "predecessor_artifact_generation", "publication_operation_generation",
                "publication_artifact_generation", "result_digest", "provenance_manifest_digest",
            )}
            found = BootstrapRecoveryFoundV3(
                **found_body,
                response_digest=contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-recovery-found.v3", found_body,
                ),
            )
            recovered = self.recover_bootstrap_v3_source_normalization(
                recovery_key_digest=recovery_key_digest
            )
            if recovered is None:
                return None
            _generation, _request_digest, result_digest, members = recovered
            request_member = next(item for item in members if item.kind == "bootstrap_source_normalization_request")
            result_member = next(item for item in members if item.kind == "bootstrap_source_normalization_result")
            request = decode_semantic_contract(
                request_member.canonical_payload,
                BootstrapSourceNormalizationRequestV3,
                max_nodes=20_000,
                max_depth=128,
            )
            result = decode_semantic_contract(
                result_member.canonical_payload,
                BootstrapSourceNormalizationResultV3,
                max_nodes=20_000,
                max_depth=128,
            )
            if (
                encode_semantic_contract(request) != request_member.canonical_payload
                or encode_semantic_contract(result) != result_member.canonical_payload
                or request_member.payload_digest != sha256(request_member.canonical_payload).hexdigest()
                or result_member.payload_digest != sha256(result_member.canonical_payload).hexdigest()
                or result.result_digest != result_digest
                or result.result_digest != found.result_digest
                or result.source_normalization_request_digest != request.request_digest
            ):
                return None
            return BootstrapRecoveryReplayRecordV3.create(
                recovery_key_digest=recovery_key_digest, found_response=found,
                source_normalization_request=request,
                source_normalization_result=result,
            )
        except (KeyError, StopIteration, TypeError, ValueError):
            return None

    def _validate_recovery_prepared_lease(
        self,
        *,
        canonical_evidence_lease: CanonicalEvidenceLease,
        handoff_marker: BootstrapWriterHandoffMarkerV3,
        tenant_partition_id: str,
    ) -> bool:
        """Validate a fresh recovery lease against retained prepared authority."""
        from memorii.core.semantic_ingestion.canonical_evidence_arena import (
            CANONICAL_CODEC_REVISION,
            CANONICAL_PROFILE_REVISION,
        )
        from memorii.core.semantic_ingestion.contracts import decode_semantic_contract

        if canonical_evidence_lease._released:
            return False
        try:
            tenant = tenant_partition_id
            current = self._writers.current()
            scope = canonical_evidence_lease.scope
            evidence = canonical_evidence_lease.result
            prepared_record = self._memory_plane.get_record(
                "semantic_ingestion:prepared_source:"
                + sha256(handoff_marker.source_id.encode("utf-8")).hexdigest()
            )
            if prepared_record is None:
                return False
            prepared = self._load_prepared_source_record(
                prepared_record, handoff_marker.source_id, handoff_marker.source_digest
            )
            leased_prepared = decode_semantic_contract(
                evidence.canonical_contract_bytes,
                type(prepared),
                max_nodes=20_000,
                max_depth=128,
            )
        except (AttributeError, PreplanningStoreError, TypeError, ValueError):
            return False
        return (
            type(evidence.contract) is type(prepared)
            and evidence.contract == prepared
            and leased_prepared == prepared
            and evidence.canonical_member_index.canonical_digest
            == sha256(evidence.canonical_contract_bytes).hexdigest()
            and bool(evidence.member_evidence)
            and all(
                member.profile_revision == CANONICAL_PROFILE_REVISION
                and member.codec_revision == CANONICAL_CODEC_REVISION
                for member in evidence.member_evidence
            )
            and evidence.domain
            and scope.tenant == tenant
            and scope.operation == handoff_marker.operation_fence_binding.operation_id
            and scope.generation == handoff_marker.prepared_generation
            and scope.fence == handoff_marker.operation_fence_binding.operation_fence_id
            and scope.writer == f"{current.admission_digest}:{current.writer_epoch}"
            and handoff_marker.writer_commit_binding.admission_digest
            == current.admission_digest
            and handoff_marker.writer_commit_binding.expected_writer_epoch
            == current.writer_epoch
            and handoff_marker.prepared_source_digest
            == sha256(evidence.canonical_contract_bytes).hexdigest()
        )

    def reload_bootstrap_graph_normalization_authority_v3(
        self, *, normalization_replay: object,
    ) -> object | None:
        """Reload the policy/capability member from the exact found generation."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphNormalizationAuthorityMemberV3,
            BootstrapGraphNormalizationAuthorityReloadV3,
            BootstrapRecoveryReplayRecordV3,
            canonical_contract_value,
            decode_semantic_contract,
            encode_semantic_contract,
        )

        if not isinstance(normalization_replay, BootstrapRecoveryReplayRecordV3):
            return None
        try:
            recovered = self.recover_bootstrap_v3_source_normalization(
                recovery_key_digest=normalization_replay.recovery_key_digest
            )
            if recovered is None:
                return None
            generation, atomic_write_digest, result_digest, members = recovered
            member = next(
                item for item in members
                if item.kind == "bootstrap_graph_normalization_authority"
            )
            authority = decode_semantic_contract(
                member.canonical_payload, BootstrapGraphNormalizationAuthorityMemberV3,
                max_nodes=20_000,
                max_depth=128,
            )
            authority_payload = encode_semantic_contract(authority)
            if (
                authority_payload != member.canonical_payload
                and encode_typed_value(canonical_contract_value(authority)) != member.canonical_payload
                or member.payload_digest != sha256(member.canonical_payload).hexdigest()
                or authority.recovery_key_digest != normalization_replay.recovery_key_digest
                or authority.normalization_request_digest
                != normalization_replay.source_normalization_request.request_digest
                or authority.normalization_result_digest != result_digest
            ):
                return None
            return BootstrapGraphNormalizationAuthorityReloadV3.create(
                normalization_replay=normalization_replay,
                normalization_atomic_write_digest=atomic_write_digest,
                normalization_operation_generation=generation,
                normalization_artifact_generation=generation,
                authority_member=authority,
            )
        except (PreplanningStoreError, StopIteration, TypeError, ValueError):
            return None

    def reload_bootstrap_semantic_reduction_authority_v3(
        self, *, normalization_replay: object,
    ) -> object | None:
        """Reload the exact native reduction member from the found generation.

        No caller may reconstruct a reduction from the replay wrapper or from
        live graph state: the retained core bytes are the authority boundary.
        """
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapNormalizationRequestCoreV3,
            BootstrapRecoveryReplayRecordV3,
            BootstrapSemanticReductionAuthorityMemberV3,
            BootstrapSemanticReductionAuthorityReloadV3,
            canonical_contract_value,
            decode_semantic_contract,
            encode_semantic_contract,
        )

        if not isinstance(normalization_replay, BootstrapRecoveryReplayRecordV3):
            return None
        try:
            recovered = self.recover_bootstrap_v3_source_normalization(
                recovery_key_digest=normalization_replay.recovery_key_digest
            )
            if recovered is None:
                return None
            generation, atomic_write_digest, _result_digest, members = recovered
            core_member = next(
                item for item in members
                if item.kind == "bootstrap_normalization_request_core"
            )
            authority_member = next(
                item for item in members
                if item.kind == "bootstrap_semantic_reduction_authority"
            )
            core = decode_semantic_contract(
                core_member.canonical_payload,
                BootstrapNormalizationRequestCoreV3,
                max_nodes=20_000,
                max_depth=128,
            )
            authority = decode_semantic_contract(
                authority_member.canonical_payload,
                BootstrapSemanticReductionAuthorityMemberV3,
                max_nodes=20_000,
                max_depth=128,
            )
            core_payload = encode_semantic_contract(core)
            if (
                core_payload != core_member.canonical_payload
                and encode_typed_value(canonical_contract_value(core)) != core_member.canonical_payload
            ):
                return None
            authority_payload = encode_semantic_contract(authority)
            if (
                authority_payload != authority_member.canonical_payload
                and encode_typed_value(canonical_contract_value(authority)) != authority_member.canonical_payload
            ):
                return None
            if (
                core_member.payload_digest != sha256(core_member.canonical_payload).hexdigest()
                or authority_member.payload_digest
                != sha256(authority_member.canonical_payload).hexdigest()
                or authority.normalization_request_core != core
                or core.recovery_key.recovery_key_digest
                != normalization_replay.recovery_key_digest
                or core.source_alignment
                != normalization_replay.source_normalization_request.source_alignment
            ):
                return None
            return BootstrapSemanticReductionAuthorityReloadV3.create(
                normalization_replay=normalization_replay,
                normalization_atomic_write_digest=atomic_write_digest,
                normalization_operation_generation=generation,
                normalization_artifact_generation=generation,
                authority_member=authority,
            )
        except (PreplanningStoreError, StopIteration, TypeError, ValueError):
            return None

    def publish_or_reload_bootstrap_graph_transaction_authority_v3(
        self, *, request: object,
    ) -> object:
        """CAS the complete pre-epoch graph authority and return reloaded bytes.

        This deliberately has a distinct record family from graph checkpoints:
        an authority projection exists before a control epoch or final request.
        """
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphAuthorityGenerationV3,
            BootstrapGraphAuthorityPublicationCoreV3,
            BootstrapGraphAuthorityPublicationReceiptV3,
            BootstrapGraphTransactionAuthorityReloadV3,
            BootstrapGraphTransactionAuthorityWriteRequestV3,
            encode_semantic_contract,
        )

        if not isinstance(request, BootstrapGraphTransactionAuthorityWriteRequestV3):
            raise PreplanningStoreError("bootstrap graph authority write has an invalid type")
        request = BootstrapGraphTransactionAuthorityWriteRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        projection = request.authority_projection
        existing = self._memory_plane.get_record(
            _bootstrap_graph_v3_authority_id(projection.authority_projection_digest)
        )
        if existing is not None:
            return _bootstrap_graph_v3_authority_from_record(existing)
        control_record = self._required_control_record(request.operation_fence_binding)
        control = _control_from_record(control_record)
        if (
            control.writer_binding != request.writer_commit_binding
            or control.lease is None
            or self.lease_binding(control) != request.operation_lease_binding
            or request.operation_lease_binding.lease_expires_at <= self._now()
        ):
            raise PreplanningStoreError("bootstrap graph authority is no longer current")
        writer_record = self._writers.require_current(request.writer_commit_binding)
        authorization = self._writers._authorize_atomic(
            request.writer_commit_binding,
            capability=self._write_capability,
            lease_expires_at=request.operation_lease_binding.lease_expires_at,
            server_now=self._now,
        )
        atomic_write_digest = sha256(
            b"memorii.semantic-ingestion.bootstrap-graph-authority-atomic-write.v3\0"
            + request.write_digest.encode("ascii")
        ).hexdigest()
        core = BootstrapGraphAuthorityPublicationCoreV3.create(
            write_request_digest=request.write_digest,
            authority_projection=projection,
            publication_operation_generation=control.generation,
            publication_artifact_generation=control.generation,
        )
        generation = BootstrapGraphAuthorityGenerationV3.create(
            store_identity_digest=sha256(_control_namespace(control).encode("utf-8")).hexdigest(),
            recovery_key_digest=projection.normalization_authority.normalization_replay.recovery_key_digest,
            normalization_atomic_write_digest=(
                projection.normalization_authority.normalization_atomic_write_digest
            ),
            authority_projection_digest=projection.authority_projection_digest,
            operation_id=control.operation_fence.operation_id,
            operation_fence_binding_digest=request.operation_fence_binding.binding_digest,
            operation_generation=control.generation,
            artifact_generation=control.generation,
        )
        receipt = BootstrapGraphAuthorityPublicationReceiptV3.create(
            recovery_key_digest=generation.recovery_key_digest,
            authority_projection_digest=projection.authority_projection_digest,
            write_request_digest=request.write_digest,
            atomic_write_digest=atomic_write_digest,
            publication_core_digest=core.core_digest,
            successor_generation=generation,
        )
        reload = BootstrapGraphTransactionAuthorityReloadV3.create(
            publication_core=core, publication_receipt=receipt,
        )
        timestamp = self._now()
        record = _bootstrap_graph_v3_authority_record(reload, timestamp)
        index = _bootstrap_graph_v3_authority_index_record(reload, timestamp)
        try:
            self._memory_plane.conditionally_write_records(
                (record, index),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=record.memory_id),
                    RecordAbsentPrecondition(memory_id=index.memory_id),
                    RecordDigestPrecondition(
                        memory_id=control_record.memory_id,
                        expected_digest=record_digest(control_record),
                    ),
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id,
                        expected_digest=record_digest(writer_record),
                    ),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._memory_plane.get_record(record.memory_id)
            if existing is None:
                raise PreplanningStoreError("bootstrap graph authority publication conflicted") from exc
        reloaded = self._memory_plane.get_record(record.memory_id)
        if reloaded is None:
            raise PreplanningStoreError("bootstrap graph authority publication was not durable")
        result = _bootstrap_graph_v3_authority_from_record(reloaded)
        if encode_semantic_contract(result) != encode_semantic_contract(reload):
            raise PreplanningStoreError("bootstrap graph authority reload is substituted")
        return result

    def publish_or_reload_bootstrap_canonical_identity_authority_v3(
        self, *, request: object,
    ) -> object:
        """Persist one pre-plan canonical identity authority or reload it exactly."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapCanonicalIdentityAuthorityWriteRequestV3,
            encode_semantic_contract,
        )
        if not isinstance(request, BootstrapCanonicalIdentityAuthorityWriteRequestV3):
            raise PreplanningStoreError("canonical identity authority write has an invalid type")
        request = BootstrapCanonicalIdentityAuthorityWriteRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        reload = request.authority_reload
        record_id = _bootstrap_canonical_identity_authority_id(reload.reload_digest)
        existing = self._memory_plane.get_record(record_id)
        if existing is not None:
            return _bootstrap_canonical_identity_authority_from_record(existing)
        control_record = self._required_control_record(request.operation_fence_binding)
        control = _control_from_record(control_record)
        if (
            control.writer_binding != request.writer_commit_binding
            or control.lease is None
            or self.lease_binding(control) != request.operation_lease_binding
            or request.operation_lease_binding.lease_expires_at <= self._now()
        ):
            raise PreplanningStoreError("canonical identity authority is no longer current")
        writer_record = self._writers.require_current(request.writer_commit_binding)
        authorization = self._writers._authorize_atomic(
            request.writer_commit_binding, capability=self._write_capability,
            lease_expires_at=request.operation_lease_binding.lease_expires_at,
            server_now=self._now,
        )
        record = CanonicalMemoryRecord(
            memory_id=record_id, domain=MemoryDomain.EXECUTION, text="",
            content={
                "semantic_ingestion_kind": "bootstrap_canonical_identity_authority_v3",
                "reload_digest": reload.reload_digest,
                "canonical_hex": encode_semantic_contract(reload).hex(),
            }, status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_bootstrap_canonical_identity_authority_v3",
            timestamp=self._now(), visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        try:
            self._memory_plane.conditionally_write_records(
                (record,), preconditions=(
                    RecordAbsentPrecondition(memory_id=record.memory_id),
                    RecordDigestPrecondition(memory_id=control_record.memory_id, expected_digest=record_digest(control_record)),
                    RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                ), authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._memory_plane.get_record(record_id)
            if existing is None:
                raise PreplanningStoreError("canonical identity authority publication conflicted") from exc
        reloaded = self._memory_plane.get_record(record_id)
        if reloaded is None:
            raise PreplanningStoreError("canonical identity authority was not durable")
        result = _bootstrap_canonical_identity_authority_from_record(reloaded)
        if encode_semantic_contract(result) != encode_semantic_contract(reload):
            raise PreplanningStoreError("canonical identity authority reload is substituted")
        return result

    def reload_bootstrap_graph_transaction_authority_for_recovery_v3(
        self,
        *,
        recovery_key_digest: str,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
        operation_fence_binding: object,
    ) -> object | None:
        """Authorized, non-disclosing recovery lookup for a pre-epoch projection."""
        from memorii.core.memory_evolution.ingestion_contracts import (
            OperationFenceBinding,
        )
        from memorii.core.semantic_ingestion.contracts import RequiredOutcomeScopeSet

        if (
            not isinstance(required_outcome_scopes, RequiredOutcomeScopeSet)
            or not isinstance(operation_fence_binding, OperationFenceBinding)
        ):
            return None
        try:
            control = _control_from_record(self._required_control_record(operation_fence_binding))
            if control.operation_fence != operation_fence_binding:
                return None
        except (PreplanningStoreError, ValueError):
            return None
        matches = []
        for record in self._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_authority_index"
        ):
            if record.content.get("recovery_key_digest") != recovery_key_digest:
                continue
            authority_id = record.content.get("authority_record_id")
            if not isinstance(authority_id, str):
                return None
            authority = self._memory_plane.get_record(authority_id)
            if authority is None:
                return None
            try:
                reloaded = _bootstrap_graph_v3_authority_from_record(authority)
            except (PreplanningStoreError, ValueError):
                return None
            projection = reloaded.publication_core.authority_projection
            graph = projection.graph_authority
            if (
                graph.operation_fence_binding != operation_fence_binding
                or graph.required_scope_set_digest
                != required_outcome_scopes.required_scope_set_digest
                or graph.delivery_principal_binding_digest
                != delivery_principal_binding_digest
            ):
                return None
            matches.append(reloaded)
        return matches[0] if len(matches) == 1 else None

    def _semantic_clean_recovery_authority_records(
        self,
    ) -> tuple[CanonicalMemoryRecord, ...]:
        """Snapshot only independently retained recovery authority."""

        retained_kinds = {
            "semantic_ingestion_generation_member",
            "semantic_ingestion_generation_manifest",
            "semantic_ingestion_checkpoint_lifecycle",
            "semantic_ingestion_event_schema_registry_history",
            "semantic_ingestion_conflict_clarification_transaction",
            "semantic_ingestion_conflict_clarification_receipt",
            "semantic_ingestion_conflict_clarification_recovery_authority",
        }
        return tuple(
            sorted(
                (
                    record
                    for kind in retained_kinds
                    for record in self._memory_plane.list_records(source_kind=kind)
                ),
                key=lambda record: record.memory_id,
            )
        )

    def _default_semantic_freeze_guard(self, graph_delta: SemanticGraphDelta) -> None:
        record = self._memory_plane.get_record(_semantic_integrity_control_id())
        if record is None:
            return
        partitions = record.content.get("frozen_partition_ids")
        if not isinstance(partitions, (tuple, list)) or not all(isinstance(item, str) for item in partitions):
            raise PreplanningStoreError("semantic integrity control is corrupt")
        if "global" in partitions:
            from memorii.core.semantic_ingestion.event_replay import SemanticEventReplayError

            raise SemanticEventReplayError("semantic_repository_scope_frozen")

    def _record_default_semantic_integrity_incident(self, conflicting_byte_digests: tuple[str, ...]) -> None:
        digests = tuple(sorted(set(conflicting_byte_digests)))
        if not digests or any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value) for value in digests
        ):
            raise PreplanningStoreError("semantic integrity incident evidence is invalid")
        for _ in range(8):
            current = self._memory_plane.get_record(_semantic_integrity_control_id())
            revision = 1
            prior_digest = None
            prior_evidence: tuple[str, ...] = ()
            if current is not None:
                revision_value = current.content.get("control_revision")
                evidence_value = current.content.get("conflicting_byte_digests")
                if (
                    not isinstance(revision_value, int)
                    or not isinstance(evidence_value, (tuple, list))
                    or not all(isinstance(item, str) for item in evidence_value)
                ):
                    raise PreplanningStoreError("semantic integrity control is corrupt")
                revision = revision_value + 1
                prior_digest = record_digest(current)
                prior_evidence = tuple(evidence_value)
            evidence = tuple(sorted(set((*prior_evidence, *digests))))
            now = self._now()
            control = CanonicalMemoryRecord(
                memory_id=_semantic_integrity_control_id(),
                domain=MemoryDomain.EXECUTION,
                text="",
                content={
                    "semantic_ingestion_kind": "semantic_replay_integrity_control",
                    "control_revision": revision,
                    "frozen_partition_ids": ("global",),
                    "conflicting_byte_digests": evidence,
                },
                status=CommitStatus.COMMITTED,
                source_kind="semantic_ingestion_replay_integrity_control",
                timestamp=now,
                visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
            )
            attention = CanonicalMemoryRecord(
                memory_id=_semantic_integrity_attention_id(revision),
                domain=MemoryDomain.EXECUTION,
                text="Memory integrity incident requires operator action.",
                content={
                    "semantic_ingestion_kind": "semantic_replay_integrity_attention",
                    "control_revision": revision,
                    "audience": "operator",
                },
                status=CommitStatus.COMMITTED,
                source_kind="semantic_ingestion_replay_integrity_attention",
                timestamp=now,
                visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
            )
            admission = self._writers.current()
            binding = self._writers.commit_binding(admission)
            writer_record = self._writers.require_current(binding)
            if current is None:
                precondition: MemoryPlanePrecondition = RecordAbsentPrecondition(memory_id=control.memory_id)
            else:
                if prior_digest is None:
                    raise PreplanningStoreError("semantic integrity control is corrupt")
                precondition = RecordDigestPrecondition(
                    memory_id=control.memory_id,
                    expected_digest=prior_digest,
                )
            try:
                self._memory_plane.conditionally_write_records(
                    (control, attention),
                    preconditions=(
                        precondition,
                        RecordAbsentPrecondition(memory_id=attention.memory_id),
                        RecordDigestPrecondition(
                            memory_id=writer_record.memory_id,
                            expected_digest=record_digest(writer_record),
                        ),
                    ),
                    authorization=self._writers._authorize_atomic(binding, capability=self._write_capability),
                )
                publisher = self._semantic_integrity_attention_publisher
                if publisher is not None:
                    publisher(
                        sha256(
                            encode_typed_value(
                                {
                                    "repository_id": _SEMANTIC_EVENT_REPOSITORY_ID,
                                    "frozen_partition_ids": ("global",),
                                    "conflicting_byte_digests": evidence,
                                }
                            )
                        ).hexdigest(),
                        now,
                    )
                return
            except MemoryPlaneRevisionConflictError:
                continue
        raise PreplanningStoreError("semantic integrity incident publication contention")

    def validate_semantic_replay_checkpoint(self, checkpoint) -> SemanticReplayState:
        """Validate a checkpoint without exposing signing or key material."""

        from memorii.core.semantic_ingestion.event_replay import (
            validate_replay_checkpoint,
        )

        return validate_replay_checkpoint(
            checkpoint,
            authority=self._checkpoint_resume_authority,
            projection_history_verifier=self._projection_history,
            semantic_conflict_verifier=self._projection_history,
        )

    def resume_semantic_replay_checkpoint_tail(
        self,
        checkpoint,
        tail_batches: tuple[SemanticMemoryEventBatch, ...],
    ) -> SemanticReplayState:
        """Resume a validated checkpoint through the store-owned authority."""

        from memorii.core.semantic_ingestion.event_replay import (
            replay_semantic_checkpoint_tail,
        )

        return replay_semantic_checkpoint_tail(
            checkpoint,
            tail_batches=tail_batches,
            authority=self._checkpoint_resume_authority,
            projection_history_verifier=self._projection_history,
            semantic_conflict_verifier=self._projection_history,
        )

    def semantic_replay_authority(self) -> SemanticReplayAuthorityAggregate:
        """Reconstruct and validate the complete production replay closure."""

        from memorii.core.memory_evolution.projection_history import (
            ProjectionHistoryError,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            SemanticReplayAuthorityAggregate,
            decode_event_schema_registry_history,
            decode_replay_checkpoint_lifecycle,
            decode_semantic_replay_authority,
            validate_replay_checkpoint,
        )

        lifecycle_record = self._memory_plane.get_record(_semantic_checkpoint_lifecycle_id())
        aggregate_record = self._memory_plane.get_record(_semantic_replay_authority_id())
        history_record = self._memory_plane.get_record(_semantic_registry_history_id())
        try:
            projection_bindings = self._projection_history.replay_bindings()
            # Replay authority is also the recovery boundary for the durable
            # clarification queue.  The pointer binding alone cannot prove
            # that a completed answer retained its work-generation and
            # attempt-result members, so reconstruct that independent chain
            # before exposing any aggregate as valid.
            self._projection_history.current_clarification_work()
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError("semantic replay projection authority is corrupt") from exc
        # A terminal clarification is part of replay authority even when it
        # has no graph event (for example, a rejected answer).  Reconstruct
        # its transaction/receipt closure before returning an aggregate so a
        # missing receipt cannot be mistaken for an intact replay boundary.
        # This routine also verifies the accepted-event recovery authorities.
        self._accepted_clarification_recovery_authorities()
        if lifecycle_record is None and aggregate_record is None and history_record is None:
            if projection_bindings:
                raise PreplanningStoreError("semantic replay projection authority is detached")
            return SemanticReplayAuthorityAggregate.genesis(_SEMANTIC_EVENT_REPOSITORY_ID)
        if lifecycle_record is None or aggregate_record is None or history_record is None:
            raise PreplanningStoreError("semantic replay authority closure is partial")
        try:
            lifecycle_hex = lifecycle_record.content["canonical_hex"]
            aggregate_hex = aggregate_record.content["canonical_hex"]
            history_hex = history_record.content["canonical_hex"]
            if not all(isinstance(value, str) for value in (lifecycle_hex, aggregate_hex, history_hex)):
                raise TypeError
            lifecycle = decode_replay_checkpoint_lifecycle(bytes.fromhex(lifecycle_hex))
            aggregate = decode_semantic_replay_authority(bytes.fromhex(aggregate_hex))
            history = decode_event_schema_registry_history(bytes.fromhex(history_hex))
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("semantic replay authority closure is corrupt") from exc
        current_lifecycle = self._checkpoint_resume_authority.lifecycle
        if (
            lifecycle != current_lifecycle
            or history != self._event_schema_registry_history
            or lifecycle_record.content.get("authority_digest") != lifecycle.authority_digest
            or aggregate_record.content.get("aggregate_digest") != aggregate.aggregate_digest
            or history_record.content.get("history_digest") != history.history_digest
        ):
            raise PreplanningStoreError("semantic replay lifecycle authority is stale or substituted")
        reconstructed = self.semantic_replay_state()
        if aggregate.graph_state != reconstructed:
            raise PreplanningStoreError("semantic replay aggregate graph state is inconsistent")
        authority = self._reconstruct_semantic_replay_authority(
            graph_state=reconstructed,
            bindings=(
                *aggregate.observation_bindings,
                *aggregate.progress_bindings,
                *aggregate.artifact_bindings,
            ),
        )
        if aggregate.reconstructed_authority_digest != authority.authority_digest:
            raise PreplanningStoreError("semantic replay aggregate member authority is inconsistent")
        try:
            self._projection_history.validate_active_graph_revision(reconstructed.graph_revision)
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError("semantic replay projection graph binding is inconsistent") from exc
        if aggregate.projection_history_bindings != projection_bindings:
            raise PreplanningStoreError("semantic replay projection authority binding is inconsistent")
        try:
            self._projection_history.validate_semantic_conflict_replay_binding(
                aggregate.semantic_conflict_replay_binding
                or SemanticConflictReplayBinding.genesis(_SEMANTIC_EVENT_REPOSITORY_ID)
            )
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError(
                "semantic replay conflict authority binding is inconsistent"
            ) from exc
        if aggregate.latest_checkpoint is not None:
            try:
                checkpoint_state = validate_replay_checkpoint(
                    aggregate.latest_checkpoint,
                    authority=self._checkpoint_resume_authority,
                    projection_history_verifier=self._projection_history,
                    semantic_conflict_verifier=self._projection_history,
                )
            except ValueError as exc:
                raise PreplanningStoreError("semantic replay aggregate checkpoint is invalid") from exc
            if checkpoint_state != reconstructed:
                raise PreplanningStoreError("semantic replay checkpoint is not current")
        return aggregate

    def reconstructed_semantic_replay_authority(self):
        """Return the typed, fully reconstructed replay authority."""

        aggregate = self.semantic_replay_authority()
        return self._reconstruct_semantic_replay_authority(
            graph_state=aggregate.graph_state,
            bindings=(
                *aggregate.observation_bindings,
                *aggregate.progress_bindings,
                *aggregate.artifact_bindings,
            ),
        )

    def _reconstruct_semantic_replay_authority(
        self,
        *,
        graph_state: SemanticReplayState,
        bindings: tuple,
        pending_request: AtomicGenerationRequest | None = None,
    ):
        """Load every bound member through its immutable fenced generation."""

        from memorii.core.semantic_ingestion.event_replay import (
            SemanticEventReplayError,
            project_semantic_replay_member,
            reconstruct_semantic_replay_authority,
            semantic_replay_dependency_digests,
        )

        pending_key = None
        pending_members: tuple[AtomicGenerationMember, ...] = ()
        if pending_request is not None:
            pending_key = (
                pending_request.operation_fence_binding.operation_fence_id,
                pending_request.expected_operation_generation + 1,
            )
            pending_members = pending_request.members
        grouped: dict[tuple[str, int], list] = {}
        for binding in bindings:
            grouped.setdefault((binding.operation_fence_id, binding.generation), []).append(binding)
        projections = []
        cumulative_dependencies: dict[str, set[str]] = {}
        last_complete_generation: dict[str, int] = {}
        try:
            for (operation_fence_id, generation), group_bindings in sorted(grouped.items()):
                control = self._control_by_operation_fence_id(operation_fence_id)
                if generation > control.generation + (1 if pending_key == (operation_fence_id, generation) else 0):
                    raise PreplanningStoreError("semantic replay member generation is not committed")
                dependencies = cumulative_dependencies.setdefault(operation_fence_id, set())
                for prior_generation in range(
                    last_complete_generation.get(operation_fence_id, 1) + 1,
                    generation,
                ):
                    for prior_member in self._read_generation_members(control, prior_generation):
                        dependencies.update(
                            semantic_replay_dependency_digests(prior_member.kind, prior_member.canonical_payload)
                        )
                if pending_key == (operation_fence_id, generation):
                    generation_members = pending_members
                else:
                    if generation > control.generation:
                        raise PreplanningStoreError("semantic replay member generation is not committed")
                    generation_members = self._read_generation_members(control, generation)
                member_by_id = {member.member_id: member for member in generation_members}
                if len(member_by_id) != len(generation_members):
                    raise PreplanningStoreError("semantic replay generation has ambiguous member identities")
                member_dependencies = {
                    member.member_id: semantic_replay_dependency_digests(member.kind, member.canonical_payload)
                    for member in generation_members
                }
                producers_by_digest: dict[str, set[str]] = {}
                for member_id, produced_digests in member_dependencies.items():
                    for produced_digest in produced_digests:
                        producers_by_digest.setdefault(produced_digest, set()).add(member_id)
                reference_edges: dict[str, set[str]] = {}
                for binding in sorted(group_bindings, key=lambda item: item.member_id):
                    member = member_by_id.get(binding.member_id)
                    if (
                        member is None
                        or member.kind != binding.member_kind
                        or member.payload_digest != binding.payload_digest
                    ):
                        raise PreplanningStoreError("semantic replay bound generation member is absent or substituted")
                    projection = project_semantic_replay_member(
                        binding,
                        canonical_payload=member.canonical_payload,
                        verified_dependency_digests=frozenset(
                            dependencies.union(
                                *(
                                    values
                                    for member_id, values in member_dependencies.items()
                                    if member_id != binding.member_id
                                )
                            )
                        ),
                    )
                    projections.append(projection)
                    for referenced_digest in projection.referenced_digests:
                        if referenced_digest in dependencies:
                            continue
                        producers = producers_by_digest.get(referenced_digest, set()) - {binding.member_id}
                        if not producers:
                            raise PreplanningStoreError("semantic replay reference has no canonical producer")
                        reference_edges.setdefault(binding.member_id, set()).update(producers)
                remaining = set(reference_edges)
                while remaining:
                    ready = {member_id for member_id in remaining if not (reference_edges[member_id] & remaining)}
                    if not ready:
                        raise PreplanningStoreError("semantic replay same-generation reference cycle")
                    remaining.difference_update(ready)
                for values in member_dependencies.values():
                    dependencies.update(values)
                last_complete_generation[operation_fence_id] = generation
        except SemanticEventReplayError as exc:
            raise PreplanningStoreError("semantic replay member authority is corrupt") from exc
        return reconstruct_semantic_replay_authority(
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            graph_state=graph_state,
            member_projections=tuple(projections),
        )

    def retain_conflict_clarification_context(
        self,
        *,
        proposal: AgentClarificationProposal,
        authorized_source,
        source_record: CanonicalMemoryRecord,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> bool:
        """Retain the exact authenticated user event needed by async clarification."""

        from memorii.core.memory_evolution.conflict_attention import (
            AgentClarificationProposal,
            AuthorizedUserEventProof,
            RetainedConflictClarificationContext,
        )
        from memorii.core.memory_evolution.ingestion_contracts import (
            AuthenticatedIngressContext,
        )

        try:
            validated_proposal = AgentClarificationProposal.model_validate(proposal.model_dump(mode="python"))
            validated_source = AuthorizedUserEventProof.model_validate(authorized_source.model_dump(mode="python"))
            validated_ingress = AuthenticatedIngressContext.model_validate(
                authenticated_ingress.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("clarification retained context is invalid") from exc
        identity = DeliveryIdentity.create(
            validated_ingress.delivery_principal_binding,
            validated_proposal.source_user_event_id,
        )
        # The proposal names the record the canonical commit supersedes: a
        # bare user-event id from the request vocabulary, that admitted
        # record's full id (the contest predecessor), or its delivery-key
        # digest form.
        expected_record_ids = {
            f"tx:{validated_proposal.source_user_event_id}",
            validated_proposal.source_user_event_id,
            f"semantic_ingestion:source:{identity.delivery_key_digest}",
        }
        current_source_record = self._memory_plane.get_record(source_record.memory_id)
        canonical_source_bytes = source_admission_source_bytes(source_record)
        if (
            current_source_record is None
            or record_digest(current_source_record) != record_digest(source_record)
            or source_record.memory_id not in expected_record_ids
            or source_record.domain != MemoryDomain.TRANSCRIPT
            or source_record.status != CommitStatus.COMMITTED
            or source_record.source_kind not in {"provider", "semantic_ingestion_source"}
            or not source_record.is_raw_event
            or (
                source_record.source_kind == "provider"
                and source_record.content.get("role") != "user"
                and source_record.content.get("operation") != "chat_user_turn"
                # A governed admission retains the raw transcript under its
                # step-one material; the user-turn shape was validated at
                # admission time by the delivery contract.
                and not isinstance(
                    source_record.content.get("source_admission"), dict
                )
            )
            # Decision (b): the proof authenticates the answering user event
            # while the proposal binds the contest predecessor, so they are
            # legitimately different records; the door validated the proof
            # against its own user-event record before retention.  Here the
            # retained record must bind the proposal exactly.
            or validated_proposal.source_user_event_digest
            != sha256(canonical_source_bytes).hexdigest()
            or validated_source.tenant_id != validated_ingress.delivery_principal_binding.tenant_partition_id
            or validated_source.principal_id != validated_ingress.delivery_principal_binding.principal_subject_id
        ):
            return False
        retained = RetainedConflictClarificationContext.create(
            proposal_digest=validated_proposal.proposal_digest,
            source_user_event_id=validated_proposal.source_user_event_id,
            source_user_event_digest=validated_proposal.source_user_event_digest,
            canonical_source_bytes=canonical_source_bytes,
            source_record_id=source_record.memory_id,
            source_record_digest=record_digest(source_record),
            source_text=source_record.text,
            authenticated_ingress=validated_ingress,
        )
        record_id = _conflict_clarification_context_id(validated_proposal.proposal_digest)
        existing = self._memory_plane.get_record(record_id)
        if existing is not None:
            recovered = self._decode_conflict_clarification_context(existing)
            if recovered != retained:
                raise PreplanningStoreError("clarification retained context is partial or conflicting")
            return True
        writer_binding = self._writers.commit_binding(self._writers.current())
        writer_record = self._writers.require_current(writer_binding)
        record = _conflict_clarification_context_record(retained, self._now())
        try:
            self._memory_plane.conditionally_write_records(
                (record,),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=record.memory_id),
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id,
                        expected_digest=record_digest(writer_record),
                    ),
                    RecordDigestPrecondition(
                        memory_id=source_record.memory_id,
                        expected_digest=record_digest(source_record),
                    ),
                ),
                authorization=self._writers._authorize_atomic(writer_binding, capability=self._write_capability),
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._memory_plane.get_record(record_id)
            if existing is None:
                raise
            recovered = self._decode_conflict_clarification_context(existing)
            if recovered != retained:
                raise PreplanningStoreError("clarification retained context is not an exact committed retry") from exc
        return True

    def resolve_conflict_clarification_context(
        self, proposal: AgentClarificationProposal
    ) -> RetainedConflictClarificationContext | None:
        """Resolve only a complete retained context bound to this exact proposal."""

        from memorii.core.memory_evolution.conflict_attention import (
            AgentClarificationProposal,
        )

        try:
            validated = AgentClarificationProposal.model_validate(proposal.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("clarification proposal is invalid") from exc
        record = self._memory_plane.get_record(_conflict_clarification_context_id(validated.proposal_digest))
        if record is None:
            return None
        retained = self._decode_conflict_clarification_context(record)
        source_record = self._memory_plane.get_record(retained.source_record_id)
        if (
            retained.proposal_digest != validated.proposal_digest
            or retained.source_user_event_id != validated.source_user_event_id
            or retained.source_user_event_digest != validated.source_user_event_digest
            or source_record is None
            or record_digest(source_record) != retained.source_record_digest
            or source_admission_source_bytes(source_record) != retained.canonical_source_bytes
            or source_admission_source_digest(source_record) != retained.source_user_event_digest
        ):
            raise PreplanningStoreError("clarification retained context does not bind its proposal")
        return retained

    @staticmethod
    def _decode_conflict_clarification_context(record: CanonicalMemoryRecord):
        from memorii.core.memory_evolution.conflict_attention import (
            RetainedConflictClarificationContext,
        )

        if (
            record.source_kind != "semantic_ingestion_conflict_clarification_context"
            or record.content.get("semantic_ingestion_kind") != "conflict_clarification_retained_context"
        ):
            raise PreplanningStoreError("clarification retained context integrity failure")
        try:
            context = record.content.get("context")
            if not isinstance(context, dict):
                raise TypeError
            normalized = dict(context)
            canonical_source = normalized.get("canonical_source_bytes")
            if isinstance(canonical_source, str):
                normalized["canonical_source_bytes"] = base64.urlsafe_b64decode(canonical_source.encode("ascii"))
            return RetainedConflictClarificationContext.model_validate(normalized)
        except (TypeError, ValueError) as exc:
            raise PreplanningStoreError("clarification retained context integrity failure") from exc

    def append_conflict_clarification_transition(
        self,
        transition: SemanticConflictClarificationTransition,
    ) -> ActiveSemanticConflict:
        """Persist a clarification edge through the registered semantic writer.

        Resolver-authority administration is intentionally not an alternative
        write route for lifecycle state.  The projection-history owner builds
        the pointer/history/head closure and this store supplies the sole
        registered atomic-writer authorization.
        """
        from memorii.core.memory_evolution.projection_history import (
            ProjectionHistoryError,
        )

        admission = self._writers.current()
        binding = self._writers.commit_binding(admission)
        authorization = self._writers._authorize_atomic(
            binding, capability=self._write_capability
        )
        try:
            return self._projection_history.append_clarification_transition(
                transition,
                authorization=authorization,
            )
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError("clarification lifecycle transition is stale") from exc

    def submit_conflict_clarification_generation(
        self,
        generation: SemanticConflictClarificationSubmissionGeneration,
    ) -> ActiveSemanticConflict:
        """Atomically publish the complete first-submission closure.

        This is intentionally separate from claim and completion: it owns only
        the unclaimed queue generation and delegates pointer/history/head CAS
        assembly to the semantic conflict authority repository.
        """
        from memorii.core.memory_evolution.conflict_attention import (
            SemanticConflictClarificationSubmissionGeneration,
        )
        from memorii.core.memory_evolution.projection_history import (
            ProjectionHistoryError,
        )

        try:
            validated = SemanticConflictClarificationSubmissionGeneration.model_validate(
                generation.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("clarification submission generation is invalid") from exc
        admission = self._writers.current()
        binding = self._writers.commit_binding(admission)
        authorization = self._writers._authorize_atomic(
            binding, capability=self._write_capability
        )
        try:
            # Submission changes the conflict pointer, so its replay binding
            # must advance in this *same* write.  Do not delegate to the
            # repository's detached append primitive and repair replay later.
            prepared = self._projection_history.prepare_clarification_transition_closure(
                validated.transition,
                submission_generation=validated,
            )
            replay_records, replay_preconditions, _ = (
                self._prepare_conflict_replay_binding_update(
                    pending_conflict_records=prepared.records,
                    writer_epoch=binding.expected_writer_epoch,
                    timestamp=self._now(),
                )
            )
            self._memory_plane.conditionally_write_records(
                (*prepared.records, *replay_records),
                preconditions=(*prepared.preconditions, *replay_preconditions),
                authorization=authorization,
            )
            return prepared.successor
        except (MemoryPlaneRevisionConflictError, ProjectionHistoryError):
            # The repository owns exact retained-edge recognition.  It is
            # safe only after the replay authority validates the same prefix.
            try:
                retained = self._projection_history.append_clarification_transition(
                    validated.transition,
                    authorization=authorization,
                    submission_generation=validated,
                )
                self.semantic_replay_authority()
                return retained
            except (ProjectionHistoryError, SemanticWriterAdmissionError) as exc:
                raise PreplanningStoreError("clarification submission is stale or corrupt") from exc

    def canonical_conflict_attention(self, conflict_id: str) -> ConflictAttention | None:
        """Return the replay-validated canonical attention item, never a file cache row."""

        from memorii.core.memory_evolution.conflict_attention import SemanticConflictIntroduction
        from memorii.core.memory_evolution.projection_history import ProjectionHistoryError

        try:
            current = self._projection_history._current_semantic_conflicts().get(conflict_id)
            if current is None:
                return None
            introduction, payload, pointer = current
            if isinstance(payload, SemanticConflictIntroduction):
                return ConflictAttention(
                    conflict_id=introduction.conflict_id,
                    conflict_revision=pointer.current_conflict_revision,
                    kind=ConflictKind.SEMANTIC_DISAGREEMENT,
                    audience=ConflictAudience.USER,
                    status=ConflictStatus.OPEN,
                    question=introduction.display.question,
                    options=introduction.display.options,
                    created_at=introduction.created_at,
                    creation_coordinate=introduction.creation_coordinate,
                    scope_digest=introduction.scope.scope_digest,
                )
            return payload.resulting_attention
        except (KeyError, TypeError, ValueError, ProjectionHistoryError) as exc:
            raise PreplanningStoreError("canonical conflict authority is corrupt") from exc

    def authorize_canonical_conflict_scopes(
        self, *, conflict_id: str, authorized_scope_ids: tuple[str, ...]
    ) -> None:
        """Require the caller's host-authorized scopes before provider use."""

        try:
            current = self._projection_history._current_semantic_conflicts().get(conflict_id)
            if current is None or not set(current[0].scope.scope_ids) <= set(authorized_scope_ids):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("canonical conflict authorization is invalid") from exc

    def canonical_conflict_predecessor(
        self, conflict_id: str
    ) -> tuple[str, str]:
        """Return the contest source record the accepted answer supersedes.

        The clarified conflict's introduction binds its contested assertions by
        claim identity and digest; the canonical commit's supersession
        discipline (record version 2 over the predecessor's version-1
        assertion) keys on the admitted source record behind the contested
        claim, so the resolution door binds the proposal to that record rather
        than to the answering user event.
        """

        from memorii.core.semantic_ingestion.contracts import ClaimAssertion

        try:
            current = self._projection_history._current_semantic_conflicts().get(conflict_id)
            if current is None:
                raise ValueError
            candidates = current[0].candidates
            if not candidates:
                raise ValueError
            candidate = candidates[-1]
            for materialized in (
                self.semantic_replay_authority().graph_state.materialized_records
            ):
                claim = materialized.record
                if (
                    materialized.record_id != candidate.candidate_id
                    or materialized.record_digest != candidate.assertion_record_digest
                    or not isinstance(claim, ClaimAssertion)
                    or claim.source_authority_evidence is None
                ):
                    continue
                source_id = claim.source_authority_evidence.source_id
                record = self._memory_plane.get_record(source_id)
                if record is None:
                    raise ValueError
                return source_id, source_admission_source_digest(record)
            raise ValueError
        except PreplanningStoreError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("canonical conflict predecessor is unavailable") from exc

    def canonical_clarification_operation_receipt(
        self, *, operation_id: str, request_digest: str
    ) -> ConflictClarificationOperationReceipt | None:
        """Resolve an exact retained submission before proof verification."""

        from memorii.core.memory_evolution.projection_history import (
            ProjectionHistoryError,
            decode_conflict_authority_record,
        )

        record = self._memory_plane.get_record(
            "semantic_ingestion:conflict-authority:clarification-submission-operation:"
            f"{operation_id}"
        )
        if record is None:
            return None
        try:
            record_type, payload, _ = decode_conflict_authority_record(record)
            from memorii.core.memory_evolution.conflict_attention import (
                SemanticConflictClarificationSubmissionOperation,
            )
            operation = decode_persisted_conflict_generation(
                payload, SemanticConflictClarificationSubmissionOperation
            )
            if record_type != "clarification_submission_operation":
                raise ValueError
            if operation.request_digest != request_digest:
                raise PreplanningOperationMismatchError(
                    "canonical clarification operation mismatch"
                )
            generation_record = self._memory_plane.get_record(
                "semantic_ingestion:conflict-authority:clarification-submission:"
                f"{operation.generation_digest}"
            )
            if generation_record is None:
                raise ValueError
            generation_type, generation_payload, _ = decode_conflict_authority_record(generation_record)
            generation = decode_persisted_conflict_generation(
                generation_payload, SemanticConflictClarificationSubmissionGeneration
            )
            if generation_type != "clarification_submission" or generation.operation_receipt.receipt_digest != operation.operation_receipt_digest:
                raise ValueError
            return generation.operation_receipt
        except PreplanningStoreError:
            raise
        except (KeyError, TypeError, ValueError, ProjectionHistoryError) as exc:
            raise PreplanningStoreError("canonical clarification operation is corrupt") from exc

    def submit_canonical_conflict_clarification(
        self,
        *,
        request: ConflictResolutionRequest,
        request_digest: str,
        proposal: AgentClarificationProposal,
        verified_confirmation: VerifiedUserConfirmation | None,
    ) -> ConflictClarificationSubmissionResult:
        """Build and append one canonical first-submission closure.

        The provider supplies only validated user inputs. This owner reloads
        the OPEN pointer, derives every lifecycle member, and delegates the
        single write to ``submit_conflict_clarification_generation``.
        """

        from memorii.core.memory_evolution.projection_history import ProjectionHistoryError

        try:
            # The operation index is checked before any receipt verifier can
            # consume a one-time proof on an acknowledgement retry.
            retained_receipt = self.canonical_clarification_operation_receipt(
                operation_id=request.operation_id,
                request_digest=request_digest,
            )
            if retained_receipt is not None:
                # The operation index alone is insufficient recovery proof:
                # retain the same replay-aggregate validation performed by
                # the lower exact-generation retry path.
                self.semantic_replay_authority()
                return ConflictClarificationSubmissionResult(
                    outcome=ClarificationSubmissionOutcome.IDEMPOTENT,
                    operation_receipt=retained_receipt,
                )
            target = self.canonical_conflict_attention(request.conflict_id)
            if target is None:
                raise ValueError
            if target.status != ConflictStatus.OPEN or target.conflict_revision != request.expected_conflict_revision:
                return ConflictClarificationSubmissionResult(
                    outcome=ClarificationSubmissionOutcome.STALE_REVISION, attention=target
                )
            if (
                proposal.conflict_id != request.conflict_id
                or proposal.conflict_revision != request.expected_conflict_revision
                or proposal.operation_id != request.operation_id
                or proposal.request_digest != request_digest
                or proposal.scope_digest != target.scope_digest
            ):
                raise ValueError
            current = self._projection_history._current_semantic_conflicts().get(request.conflict_id)
            binding = self._projection_history.semantic_conflict_replay_binding()
            if current is None:
                raise ValueError
            _, _, pointer = current
            successor_revision = sha256(
                b"memorii.semantic-conflict-clarification-revision.v1\0"
                + encode_typed_value({
                    "conflict_id": request.conflict_id,
                    "predecessor_conflict_revision": target.conflict_revision,
                    "proposal_digest": proposal.proposal_digest,
                    "pointer_revision": pointer.pointer_revision + 1,
                })
            ).hexdigest()
            attention = target.model_copy(update={
                "conflict_revision": successor_revision,
                "status": ConflictStatus.CLARIFICATION_SUBMITTED,
                "creation_coordinate": pointer.pointer_revision + 1,
                "created_at": self._now(),
            })
            policy_fingerprint = sha256(b"memorii.conflict-clarification-policy.v1\0").hexdigest()
            processing_operation_id = conflict_clarification_processing_operation_id(
                repository_id=self._projection_history.repository_id,
                conflict_revision=successor_revision,
                proposal_digest=proposal.proposal_digest,
                policy_fingerprint=policy_fingerprint,
            )
            transition_body = {
                "conflict_id": request.conflict_id,
                "predecessor_conflict_revision": target.conflict_revision,
                "predecessor_record_digest": pointer.current_record_digest,
                "predecessor_status": ConflictStatus.OPEN,
                "resulting_attention": attention,
                "reason": SemanticConflictClarificationTransitionReason.SUBMITTED,
                "proposal_digest": proposal.proposal_digest,
                "processing_operation_id": processing_operation_id,
                "successor_conflict_revision": None,
                "record_coordinate": binding.immutable_record_count + 1,
                "transition_coordinate": pointer.pointer_revision + 1,
                "transitioned_at": self._now(),
            }
            provisional_transition = SemanticConflictClarificationTransition.model_construct(
                **transition_body,
                transition_digest="0" * 64,
            )
            canonical_transition_body = provisional_transition.model_dump(
                mode="python",
                exclude={"transition_digest"},
            )
            transition = SemanticConflictClarificationTransition(
                **transition_body,
                transition_digest=sha256(
                    b"memorii.semantic-conflict-clarification-transition.v1\0"
                    + encode_typed_value(canonical_transition_body)
                ).hexdigest(),
            )
            receipt_body = {
                "operation_id": request.operation_id,
                "conflict_id": request.conflict_id,
                "conflict_revision": request.expected_conflict_revision,
                "request_digest": request_digest,
                "proposal_digest": proposal.proposal_digest,
                "verified_confirmation_digest": (
                    verified_user_confirmation_digest(verified_confirmation)
                    if verified_confirmation is not None else None
                ),
            }
            receipt = ConflictClarificationOperationReceipt(
                **receipt_body,
                receipt_digest=sha256(
                    b"memorii.conflict-clarification-operation-receipt.v1\0"
                    + encode_typed_value(receipt_body)
                ).hexdigest(),
            )
            work_values = {
                "conflict_id": request.conflict_id,
                "conflict_revision": successor_revision,
                "proposal_digest": proposal.proposal_digest,
                "attempt_count": 0, "max_attempts": 3, "owner_token": None,
                "ownership_epoch": 0, "lease_expires_at": None, "last_failure_class": None,
                "policy_fingerprint": policy_fingerprint,
                "processing_operation_id": processing_operation_id,
                "downstream_receipt_digest": None, "work_revision": 1,
                "predecessor_work_digest": None,
            }
            work = self._clarification_work_from_values(work_values)
            generation = SemanticConflictClarificationSubmissionGeneration.create(
                operation_receipt=receipt, proposal=proposal,
                verified_confirmation=verified_confirmation, work=work, transition=transition,
            )
            try:
                self.submit_conflict_clarification_generation(generation)
            except PreplanningStoreError:
                # A natural projection can win after the initial OPEN-pointer
                # read but before this first-submission closure reaches its
                # pointer CAS.  Re-read only after the lower owner has had a
                # chance to recognize an exact retained closure: that keeps
                # lost-ack retries and corrupt retained records fail closed.
                current_attention = self.canonical_conflict_attention(request.conflict_id)
                if (
                    current_attention is not None
                    and (
                        current_attention.status != ConflictStatus.OPEN
                        or current_attention.conflict_revision
                        != request.expected_conflict_revision
                    )
                ):
                    return ConflictClarificationSubmissionResult(
                        outcome=ClarificationSubmissionOutcome.STALE_REVISION,
                        attention=current_attention,
                    )
                raise
            return ConflictClarificationSubmissionResult(
                outcome=ClarificationSubmissionOutcome.SUBMITTED, operation_receipt=receipt
            )
        except PreplanningStoreError:
            # The retained index is checked here only after construction when
            # the first CAS loses. A later facade will expose exact retries.
            raise
        except (KeyError, TypeError, ValueError, ProjectionHistoryError) as exc:
            raise PreplanningStoreError("canonical clarification submission is invalid") from exc

    def _prepare_conflict_replay_binding_update(
        self,
        *,
        pending_conflict_records: tuple[CanonicalMemoryRecord, ...],
        writer_epoch: int,
        timestamp: datetime,
    ) -> tuple[
        tuple[CanonicalMemoryRecord, ...],
        tuple[MemoryPlanePrecondition, ...],
        SemanticReplayAuthorityAggregate,
    ]:
        """Prepare the replay aggregate for a same-plane conflict pointer CAS.

        Work-only records deliberately never call this helper: they do not
        alter the conflict replay prefix or active pointer set.
        """
        from memorii.core.memory_evolution.projection_history import ProjectionHistoryError
        from memorii.core.semantic_ingestion.event_replay import (
            advance_semantic_replay_authority,
            create_replay_checkpoint,
        )

        prior = self.semantic_replay_authority()
        aggregate_record = self._memory_plane.get_record(_semantic_replay_authority_id())
        lifecycle_record = self._memory_plane.get_record(_semantic_checkpoint_lifecycle_id())
        history_record = self._memory_plane.get_record(_semantic_registry_history_id())
        if aggregate_record is None or lifecycle_record is None or history_record is None:
            raise PreplanningStoreError("semantic replay authority closure is partial")
        try:
            current_binding = self._projection_history.semantic_conflict_replay_binding()
            if prior.semantic_conflict_replay_binding != current_binding:
                raise ValueError
            prospective_binding = self._projection_history.semantic_conflict_replay_binding(
                pending_records=pending_conflict_records
            )
        except (ProjectionHistoryError, ValueError) as exc:
            raise PreplanningStoreError("semantic replay conflict authority binding is inconsistent") from exc
        checkpoint = None
        if prior.latest_checkpoint is not None:
            checkpoint = create_replay_checkpoint(
                state=prior.graph_state,
                watermark_batch=prior.latest_checkpoint.watermark_batch,
                writer_epoch=writer_epoch,
                authority=self._checkpoint_resume_authority,
                created_at=timestamp,
                reconstructed_replay_authority_digest=prior.reconstructed_authority_digest,
                projection_history_bindings=prior.projection_history_bindings,
                semantic_conflict_replay_binding=prospective_binding,
            )
        aggregate = advance_semantic_replay_authority(
            prior,
            graph_state=prior.graph_state,
            member_bindings=(),
            reconstructed_authority_digest=prior.reconstructed_authority_digest,
            latest_checkpoint=checkpoint,
            projection_history_bindings=prior.projection_history_bindings,
            semantic_conflict_replay_binding=prospective_binding,
        )
        return (
            (_semantic_replay_authority_record(aggregate, timestamp),),
            (
                RecordDigestPrecondition(
                    memory_id=aggregate_record.memory_id,
                    expected_digest=record_digest(aggregate_record),
                ),
                RecordDigestPrecondition(
                    memory_id=lifecycle_record.memory_id,
                    expected_digest=record_digest(lifecycle_record),
                ),
                RecordDigestPrecondition(
                    memory_id=history_record.memory_id,
                    expected_digest=record_digest(history_record),
                ),
            ),
            aggregate,
        )

    def append_conflict_clarification_work_generation(
        self,
        generation: SemanticConflictClarificationWorkGeneration,
    ) -> SemanticConflictClarificationWorkGeneration:
        """Publish one already-constructed claim or renewal with writer authorization."""
        from memorii.core.memory_evolution.projection_history import ProjectionHistoryError

        try:
            validated = SemanticConflictClarificationWorkGeneration.model_validate(
                generation.model_dump(mode="python")
            )
            if (
                validated.attempt_result is not None
                and validated.attempt_result.outcome.value
                in {"accepted", "rejected", "insufficient", "superseded"}
            ):
                # Semantic completion and projection supersession own their
                # matching pointer/effect CAS closures.  The queue-only
                # facade cannot manufacture either terminal result.
                raise PreplanningStoreError(
                    "clarification terminal result requires its owning transaction"
                )
            admission = self._writers.current()
            binding = self._writers.commit_binding(admission)
            authorization = self._writers._authorize_atomic(
                binding, capability=self._write_capability
            )
            if validated.transition is None:
                return self._projection_history.append_clarification_work_generation(
                    validated, authorization=authorization
                )
            prepared_records, prepared_preconditions = (
                self._projection_history.append_clarification_work_generation(
                    validated, authorization=authorization, prepare_only=True
                )
            )
            replay_records, replay_preconditions, _ = (
                self._prepare_conflict_replay_binding_update(
                    pending_conflict_records=prepared_records,
                    writer_epoch=binding.expected_writer_epoch,
                    timestamp=self._now(),
                )
            )
            self._memory_plane.conditionally_write_records(
                (*prepared_records, *replay_records),
                preconditions=(*prepared_preconditions, *replay_preconditions),
                authorization=authorization,
            )
            return validated
        except (AttributeError, TypeError, ValueError, ProjectionHistoryError, MemoryPlaneRevisionConflictError) as exc:
            if "validated" in locals() and validated.transition is not None:
                try:
                    retained = self._projection_history.append_clarification_work_generation(
                        validated, authorization=authorization
                    )
                    self.semantic_replay_authority()
                    return retained
                except (ProjectionHistoryError, PreplanningStoreError):
                    pass
            raise PreplanningStoreError("clarification claim generation is stale or corrupt") from exc

    def claim_next_conflict_clarification(
        self,
        *,
        lease_duration: timedelta,
        owner_token: str | None = None,
    ) -> ConflictClarificationClaim | None:
        """Claim the first canonical submitted work item, if one is unowned.

        Supplying ``owner_token`` lets a caller repeat a lost acknowledgement
        exactly.  A generated token is suitable for the ordinary one-shot
        processor path.
        """
        from memorii.core.memory_evolution.conflict_attention import SemanticConflictClarificationWorkGeneration
        from memorii.core.memory_evolution.projection_history import ProjectionHistoryError

        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        token = owner_token or token_hex(32)
        now = self._now()
        try:
            states = self._projection_history.current_clarification_work()
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError("clarification claim generation is stale or corrupt") from exc
        # An already-persisted exact claimant is the lost-acknowledgement retry.
        retained = [
            state for state in states.values()
            if state.work.owner_token == token and state.attempt is not None
            and state.work.lease_expires_at is not None
            and state.work.lease_expires_at > now
        ]
        if len(retained) > 1:
            raise PreplanningStoreError("clarification claim generation is stale or corrupt")
        if retained:
            state = retained[0]
            return ConflictClarificationClaim(
                proposal=state.proposal, work=state.work, attempt=state.attempt
            )
        reclaimable = sorted(
            (
                state for state in states.values()
                if state.work.owner_token is not None
                and state.work.lease_expires_at is not None
                and state.work.lease_expires_at <= now
                and state.attempt is not None
            ),
            key=lambda state: (state.work.conflict_id.encode("utf-8"), state.work.work_digest),
        )
        if reclaimable:
            state = reclaimable[0]
            previous = state.work
            work = self._claimed_clarification_work(
                previous,
                owner_token=token,
                ownership_epoch=previous.ownership_epoch + 1,
                lease_expires_at=now + lease_duration,
            )
            attempt = self._clarification_attempt(
                previous=previous,
                work=work,
                owner_token=token,
                claimed_at=now,
                lease_expires_at=work.lease_expires_at,
                predecessor_attempt_digest=state.attempt.attempt_digest,
            )
            result = self._clarification_attempt_result(
                attempt=state.attempt,
                outcome="lease_expired",
                attempt_count_after=previous.attempt_count,
                completed_at=now,
            )
            generation = SemanticConflictClarificationWorkGeneration.create(
                predecessor_work_digest=previous.work_digest,
                work=work,
                attempt=attempt,
                attempt_result=result,
            )
            self.append_conflict_clarification_work_generation(generation)
            return ConflictClarificationClaim(proposal=state.proposal, work=work, attempt=attempt)
        eligible = sorted(
            (
                state for state in states.values()
                if (
                    state.work.owner_token is None
                    and state.work.attempt_count < state.work.max_attempts
                    and state.work.last_failure_class is not ClarificationFailureClass.TERMINAL
                )
            ),
            key=lambda state: (state.work.conflict_id.encode("utf-8"), state.work.work_digest),
        )
        if not eligible:
            return None
        state = eligible[0]
        previous = state.work
        lease_expires_at = now + lease_duration
        work = self._claimed_clarification_work(
            previous,
            owner_token=token,
            ownership_epoch=previous.ownership_epoch + 1,
            lease_expires_at=lease_expires_at,
        )
        attempt = self._clarification_attempt(
            previous=previous,
            work=work,
            owner_token=token,
            claimed_at=now,
            lease_expires_at=lease_expires_at,
            predecessor_attempt_digest=None,
        )
        generation = SemanticConflictClarificationWorkGeneration.create(
            predecessor_work_digest=previous.work_digest,
            work=work,
            attempt=attempt,
        )
        self.append_conflict_clarification_work_generation(generation)
        return ConflictClarificationClaim(proposal=state.proposal, work=work, attempt=attempt)

    def renew_conflict_clarification_claim(
        self,
        claim: ConflictClarificationClaim,
        *,
        lease_duration: timedelta,
    ) -> ConflictClarificationClaim:
        """Renew an exact owner/epoch claim without creating another attempt."""
        from memorii.core.memory_evolution.conflict_attention import SemanticConflictClarificationWorkGeneration
        from memorii.core.memory_evolution.projection_history import ProjectionHistoryError

        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        now = self._now()
        try:
            states = self._projection_history.current_clarification_work()
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError("clarification claim generation is stale or corrupt") from exc
        state = states.get(claim.work.conflict_id)
        if (
            state is None
            or state.proposal != claim.proposal
            or claim.work.owner_token is None
            or claim.work.lease_expires_at is None
            or claim.work.lease_expires_at <= now
            or state.attempt != claim.attempt
            or state.work.owner_token != claim.work.owner_token
            or state.work.ownership_epoch != claim.work.ownership_epoch
        ):
            raise PreplanningStoreError("clarification claim generation is stale or corrupt")
        # Build from the caller's fenced image.  If its exact successor was
        # already committed, append returns it; a different successor fails
        # closed without appending.
        work = self._claimed_clarification_work(
            claim.work,
            owner_token=claim.work.owner_token,
            ownership_epoch=claim.work.ownership_epoch,
            lease_expires_at=now + lease_duration,
        )
        generation = SemanticConflictClarificationWorkGeneration.create(
            predecessor_work_digest=claim.work.work_digest,
            work=work,
        )
        self.append_conflict_clarification_work_generation(generation)
        return ConflictClarificationClaim(proposal=claim.proposal, work=work, attempt=claim.attempt)

    def build_conflict_clarification_cas_input(
        self,
        claim: ConflictClarificationClaim,
    ) -> SemanticConflictClarificationCasInput:
        """Bind a live claimed image to its exact same-plane CAS members.

        The proposal binds the OPEN revision it answered.  The submitted
        pointer and claimed work both bind the successor lifecycle revision.
        This method is read-only: any stale, expired, missing, or divergent
        authority fails before a semantic transaction can be prepared.
        """
        from memorii.core.memory_evolution.conflict_attention import (
            ActiveSemanticConflict,
            ConflictClarificationAttempt,
            ConflictClarificationWork,
            SemanticConflictClarificationTransition,
        )
        from memorii.core.memory_evolution.projection_history import (
            ProjectionHistoryError,
            decode_conflict_authority_record,
        )

        now = self._now()
        try:
            if (
                claim.work.owner_token is None
                or claim.work.lease_expires_at is None
                or claim.work.lease_expires_at <= now
                or claim.attempt.ownership_epoch != claim.work.ownership_epoch
                or claim.attempt.owner_token_digest
                != sha256(claim.work.owner_token.encode("utf-8")).hexdigest()
            ):
                raise ValueError
            state = self._projection_history.current_clarification_work().get(
                claim.work.conflict_id
            )
            if state is None or state.proposal != claim.proposal or state.work != claim.work or state.attempt != claim.attempt:
                raise ValueError
            current = self._projection_history._current_semantic_conflicts().get(
                claim.work.conflict_id
            )
            if current is None or not isinstance(
                current[1], SemanticConflictClarificationTransition
            ):
                raise ValueError
            transition = current[1]
            pointer = current[2]
            if (
                transition.reason.value != "submitted"
                or transition.resulting_attention.status.value
                != "clarification_submitted"
                or transition.resulting_attention.conflict_revision != claim.work.conflict_revision
                or transition.proposal_digest != claim.proposal.proposal_digest
                or pointer.current_record_digest != transition.transition_digest
            ):
                raise ValueError
            pointer_record = self._memory_plane.get_record(
                f"semantic_ingestion:conflict-authority:pointer:{claim.work.conflict_id}"
            )
            work_record = self._memory_plane.get_record(
                "semantic_ingestion:conflict-authority:clarification-work-member:"
                f"{claim.work.work_digest}"
            )
            attempt_record = self._memory_plane.get_record(
                "semantic_ingestion:conflict-authority:clarification-attempt-member:"
                f"{claim.attempt.attempt_digest}"
            )
            if pointer_record is None or work_record is None or attempt_record is None:
                raise ValueError
            pointer_type, pointer_payload, _ = decode_conflict_authority_record(pointer_record)
            work_type, work_payload, _ = decode_conflict_authority_record(work_record)
            attempt_type, attempt_payload, _ = decode_conflict_authority_record(attempt_record)
            if (
                pointer_type != "active_pointer"
                or ActiveSemanticConflict.model_validate(pointer_payload) != pointer
                or work_type != "clarification_work_member"
                or decode_persisted_conflict_generation(work_payload, ConflictClarificationWork)
                != claim.work
                or attempt_type != "clarification_attempt_member"
                or decode_persisted_conflict_generation(
                    attempt_payload, ConflictClarificationAttempt
                )
                != claim.attempt
            ):
                raise ValueError
            return SemanticConflictClarificationCasInput.create(
                conflict_id=claim.work.conflict_id,
                expected_pointer_digest=pointer.pointer_digest,
                expected_pointer_revision=pointer.pointer_revision,
                expected_conflict_revision=pointer.current_conflict_revision,
                work_record_id=work_record.memory_id,
                work_record_digest=record_digest(work_record),
                attempt_record_id=attempt_record.memory_id,
                attempt_record_digest=record_digest(attempt_record),
                processing_operation_id=claim.work.processing_operation_id,
                ownership_epoch=claim.work.ownership_epoch,
                owner_token_digest=claim.attempt.owner_token_digest,
                proposal_digest=claim.proposal.proposal_digest,
            )
        except (KeyError, TypeError, ValueError, ProjectionHistoryError) as exc:
            raise PreplanningStoreError("clarification CAS image is stale or corrupt") from exc

    def fail_conflict_clarification_claim(
        self,
        claim: ConflictClarificationClaim,
        *,
        retryable: bool,
        completed_at: datetime | None = None,
    ) -> SemanticConflictClarificationWorkGeneration:
        """Close a claimed non-semantic attempt under its exact owner fence."""
        from memorii.core.memory_evolution.conflict_attention import (
            ClarificationAttemptOutcome,
            ClarificationFailureClass,
            ConflictAttention,
            ConflictStatus,
            SemanticConflictClarificationTransition,
            SemanticConflictClarificationTransitionReason,
            SemanticConflictClarificationWorkGeneration,
        )
        from memorii.core.memory_evolution.projection_history import ProjectionHistoryError

        now = completed_at or self._now()
        # An acknowledgement can be lost after the successor record commits.
        # Look up the one predecessor-keyed child before demanding that the
        # caller's claimed image is still current.
        from memorii.core.memory_evolution.projection_history import decode_conflict_authority_record
        retained_record = self._memory_plane.get_record(
            "semantic_ingestion:conflict-authority:clarification-work:"
            f"{claim.work.work_digest}"
        )
        if retained_record is not None:
            try:
                record_type, payload, _ = decode_conflict_authority_record(retained_record)
                retained = decode_persisted_conflict_generation(
                    payload, SemanticConflictClarificationWorkGeneration
                )
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise PreplanningStoreError("clarification failure generation is stale or corrupt") from exc
            expected_outcome = (
                ClarificationAttemptOutcome.RETRYABLE_FAILURE
                if retryable else ClarificationAttemptOutcome.TERMINAL_FAILURE
            )
            if (
                record_type == "clarification_work"
                and retained.attempt is None
                and retained.attempt_result is not None
                and retained.attempt_result.attempt_digest == claim.attempt.attempt_digest
                and retained.attempt_result.outcome == expected_outcome
            ):
                return retained
            raise PreplanningStoreError("clarification failure generation is stale or corrupt")
        try:
            states = self._projection_history.current_clarification_work()
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError("clarification failure generation is stale or corrupt") from exc
        state = states.get(claim.work.conflict_id)
        if (
            state is None
            or state.proposal != claim.proposal
            or state.work != claim.work
            or state.attempt != claim.attempt
            or claim.work.owner_token is None
            or claim.work.lease_expires_at is None
            or claim.work.lease_expires_at <= now
        ):
            raise PreplanningStoreError("clarification failure generation is stale or corrupt")
        outcome = (
            ClarificationAttemptOutcome.RETRYABLE_FAILURE
            if retryable
            else ClarificationAttemptOutcome.TERMINAL_FAILURE
        )
        attempt_count = claim.work.attempt_count + (1 if retryable else 0)
        values = claim.work.model_dump(mode="python", exclude={"work_digest"})
        values.update(
            owner_token=None,
            lease_expires_at=None,
            attempt_count=attempt_count,
            last_failure_class=(
                ClarificationFailureClass.RETRYABLE if retryable else ClarificationFailureClass.TERMINAL
            ),
            work_revision=claim.work.work_revision + 1,
            predecessor_work_digest=claim.work.work_digest,
        )
        released = self._clarification_work_from_values(values)
        result = self._clarification_attempt_result(
            attempt=claim.attempt,
            outcome=outcome.value,
            attempt_count_after=attempt_count,
            completed_at=now,
        )
        transition = None
        if retryable and attempt_count == released.max_attempts:
            current = self._projection_history._current_semantic_conflicts().get(claim.work.conflict_id)
            if current is None or not isinstance(current[1], SemanticConflictClarificationTransition):
                raise PreplanningStoreError("clarification failure generation is stale or corrupt")
            _, predecessor, pointer = current
            attention_values = predecessor.resulting_attention.model_dump(mode="python")
            attention_values.update(
                conflict_revision=sha256(
                    b"memorii.conflict-clarification-processing-exhausted.v1\0"
                    + encode_typed_value({"predecessor": predecessor.transition_digest, "result": result.result_digest})
                ).hexdigest(),
                status=ConflictStatus.OPEN,
            )
            attention = ConflictAttention(**attention_values)
            body = {
                "conflict_id": claim.work.conflict_id,
                "predecessor_conflict_revision": predecessor.resulting_attention.conflict_revision,
                "predecessor_record_digest": predecessor.transition_digest,
                "predecessor_status": ConflictStatus.CLARIFICATION_SUBMITTED,
                "resulting_attention": attention,
                "reason": SemanticConflictClarificationTransitionReason.PROCESSING_EXHAUSTED,
                "proposal_digest": claim.proposal.proposal_digest,
                "processing_operation_id": claim.work.processing_operation_id,
                "successor_conflict_revision": None,
                "record_coordinate": self._projection_history.semantic_conflict_replay_binding().immutable_record_count + 1,
                "transition_coordinate": pointer.pointer_revision + 1,
                "transitioned_at": now,
            }
            transition = SemanticConflictClarificationTransition(
                **body,
                transition_digest=sha256(
                    b"memorii.semantic-conflict-clarification-transition.v1\0"
                    + encode_typed_value(
                        body | {"resulting_attention": attention.model_dump(mode="python")}
                    )
                ).hexdigest(),
            )
        generation = SemanticConflictClarificationWorkGeneration.create(
            predecessor_work_digest=claim.work.work_digest,
            work=released,
            attempt_result=result,
            transition=transition,
        )
        return self.append_conflict_clarification_work_generation(generation)

    @staticmethod
    def _claimed_clarification_work(
        previous: ConflictClarificationWork,
        *,
        owner_token: str,
        ownership_epoch: int,
        lease_expires_at: datetime,
    ) -> ConflictClarificationWork:
        values = previous.model_dump(mode="python", exclude={"work_digest"})
        values.update(
            owner_token=owner_token,
            ownership_epoch=ownership_epoch,
            lease_expires_at=lease_expires_at,
            work_revision=previous.work_revision + 1,
            predecessor_work_digest=previous.work_digest,
        )
        return SemanticIngestionAtomicStore._clarification_work_from_values(values)

    @staticmethod
    def _clarification_work_from_values(values: dict[str, object]) -> ConflictClarificationWork:
        provisional = ConflictClarificationWork.model_construct(**values, work_digest="0" * 64)
        return ConflictClarificationWork(
            **values,
            work_digest=sha256(
                b"memorii.conflict-clarification-work.v1\0"
                + encode_typed_value(provisional.model_dump(mode="json", exclude={"work_digest"}))
            ).hexdigest(),
        )

    @staticmethod
    def _clarification_attempt(
        *,
        previous: ConflictClarificationWork,
        work: ConflictClarificationWork,
        owner_token: str,
        claimed_at: datetime,
        lease_expires_at: datetime,
        predecessor_attempt_digest: str | None,
    ) -> ConflictClarificationAttempt:
        attempt_id = sha256(
            b"memorii.conflict-clarification-attempt-id.v1\0"
            + encode_typed_value({
                "work_digest": previous.work_digest,
                "processing_operation_id": work.processing_operation_id,
                "ownership_epoch": work.ownership_epoch,
            })
        ).hexdigest()
        values = {
            "attempt_id": attempt_id,
            "processing_operation_id": work.processing_operation_id,
            "conflict_id": work.conflict_id,
            "conflict_revision": work.conflict_revision,
            "proposal_digest": work.proposal_digest,
            "attempt_ordinal": work.attempt_count + 1,
            "attempt_count_before": work.attempt_count,
            "ownership_epoch": work.ownership_epoch,
            "owner_token_digest": sha256(owner_token.encode("utf-8")).hexdigest(),
            "claimed_at": claimed_at,
            "lease_expires_at": lease_expires_at,
            "predecessor_attempt_digest": predecessor_attempt_digest,
        }
        provisional = ConflictClarificationAttempt.model_construct(**values, attempt_digest="0" * 64)
        return ConflictClarificationAttempt(
            **values,
            attempt_digest=sha256(
                b"memorii.conflict-clarification-attempt.v1\0"
                + encode_typed_value(provisional.model_dump(mode="json", exclude={"attempt_digest"}))
            ).hexdigest(),
        )

    @staticmethod
    def _clarification_attempt_result(
        *,
        attempt: ConflictClarificationAttempt,
        outcome: str,
        attempt_count_after: int,
        completed_at: datetime,
    ):
        from memorii.core.memory_evolution.conflict_attention import (
            ClarificationAttemptOutcome,
            ConflictClarificationAttemptResult,
        )

        values = {
            "attempt_id": attempt.attempt_id,
            "attempt_digest": attempt.attempt_digest,
            "processing_operation_id": attempt.processing_operation_id,
            "ownership_epoch": attempt.ownership_epoch,
            "owner_token_digest": attempt.owner_token_digest,
            "outcome": ClarificationAttemptOutcome(outcome),
            "attempt_count_after": attempt_count_after,
            "downstream_receipt_digest": None,
            "superseded_by_conflict_revision": None,
            "completed_at": completed_at,
        }
        provisional = ConflictClarificationAttemptResult.model_construct(**values, result_digest="0" * 64)
        return ConflictClarificationAttemptResult(
            **values,
            result_digest=sha256(
                b"memorii.conflict-clarification-attempt-result.v1\0"
                + encode_typed_value(provisional.model_dump(mode="json", exclude={"result_digest"}))
            ).hexdigest(),
        )

    def _retained_clarification_terminal_result(
        self,
        *,
        proposal: AgentClarificationProposal,
        clarification_cas: SemanticConflictClarificationCasInput,
        processing_operation_id: str,
    ) -> ConflictClarificationAttemptResult | None:
        """Return the exact terminal child of a stale claimed work image.

        A projection winner leaves the old claimed work member intact as the
        predecessor of its terminal generation.  This is the only safe place
        to recognize that a delayed completion lost the pointer race: the
        generation, attempt, and successor pointer must all bind the caller's
        exact CAS image.  No caller supplied semantic outcome is adopted.
        """
        from memorii.core.memory_evolution.conflict_attention import (
            ConflictClarificationAttempt,
            ConflictClarificationWork,
            SemanticConflictClarificationWorkGeneration,
        )
        from memorii.core.memory_evolution.projection_history import (
            ProjectionHistoryError,
            decode_conflict_authority_record,
        )

        record = self._memory_plane.get_record(
            "semantic_ingestion:conflict-authority:clarification-work:"
            f"{clarification_cas.work_record_id.rsplit(':', 1)[-1]}"
        )
        if record is None:
            # A receipt without its terminal work generation is a corrupt
            # retained completion, not a first attempt: no retained component
            # may be silently repaired by re-execution.
            receipt_probe = self._memory_plane.get_record(
                f"semantic_ingestion:clarification:receipt:{processing_operation_id}"
            )
            if receipt_probe is not None:
                raise PreplanningStoreError(
                    "clarification retained terminal result is corrupt"
                )
            return None
        try:
            record_type, payload, _ = decode_conflict_authority_record(record)
            generation = decode_persisted_conflict_generation(
                payload, SemanticConflictClarificationWorkGeneration
            )
            result = generation.attempt_result
            if (
                record_type != "clarification_work"
                or generation.predecessor_work_digest
                != clarification_cas.work_record_id.rsplit(":", 1)[-1]
                or result is None
                or result.attempt_digest
                != clarification_cas.attempt_record_id.rsplit(":", 1)[-1]
                or result.processing_operation_id != processing_operation_id
                or result.outcome.value
                not in {"accepted", "rejected", "insufficient", "superseded"}
            ):
                return None
            work_record = self._memory_plane.get_record(clarification_cas.work_record_id)
            attempt_record = self._memory_plane.get_record(clarification_cas.attempt_record_id)
            if work_record is None or attempt_record is None:
                raise ValueError
            work_type, work_payload, _ = decode_conflict_authority_record(work_record)
            attempt_type, attempt_payload, _ = decode_conflict_authority_record(attempt_record)
            work = decode_persisted_conflict_generation(work_payload, ConflictClarificationWork)
            attempt = decode_persisted_conflict_generation(
                attempt_payload, ConflictClarificationAttempt
            )
            if (
                work_type != "clarification_work_member"
                or attempt_type != "clarification_attempt_member"
                or record_digest(work_record) != clarification_cas.work_record_digest
                or record_digest(attempt_record) != clarification_cas.attempt_record_digest
                or work.work_digest != clarification_cas.work_record_id.rsplit(":", 1)[-1]
                or attempt.attempt_digest
                != clarification_cas.attempt_record_id.rsplit(":", 1)[-1]
                or work.conflict_id != clarification_cas.conflict_id
                or work.processing_operation_id != processing_operation_id
                or work.proposal_digest != proposal.proposal_digest
                or attempt.processing_operation_id != processing_operation_id
                or result.attempt_id != attempt.attempt_id
                or result.ownership_epoch != attempt.ownership_epoch
                or result.owner_token_digest != attempt.owner_token_digest
                or generation.work.owner_token is not None
            ):
                raise ValueError
            if result.outcome.value == "superseded":
                current = self._projection_history._current_semantic_conflicts().get(
                    clarification_cas.conflict_id
                )
                if (
                    current is None
                    or result.superseded_by_conflict_revision
                    != current[2].current_conflict_revision
                    or result.downstream_receipt_digest is not None
                ):
                    raise ValueError
            # Every retained completion component must still bind: the
            # receipt, the successor pointer (and the transition it names),
            # and the replay closure the accepted effect recorded.  A missing
            # or divergent member is corruption, never a silent repair.
            if result.downstream_receipt_digest is not None:
                # A committed completion retains its receipt; verify every
                # retained component still binds before replaying it.
                receipt_record = self._memory_plane.get_record(
                    f"semantic_ingestion:clarification:receipt:{processing_operation_id}"
                )
                if receipt_record is None:
                    raise ValueError
                receipt_value = ConflictClarificationProcessingReceipt.model_validate_json(
                    json.dumps(receipt_record.content["receipt"])
                )
                if (
                    receipt_value.receipt_digest != result.downstream_receipt_digest
                    or receipt_value.processing_operation_id != processing_operation_id
                    or receipt_value.committed_outcome != result.outcome.value
                    or receipt_value.conflict_id != clarification_cas.conflict_id
                ):
                    raise ValueError
                pointer_record = self._memory_plane.get_record(
                    f"semantic_ingestion:conflict-authority:pointer:"
                    f"{clarification_cas.conflict_id}"
                )
                if pointer_record is None:
                    raise ValueError
                _, pointer_value, _ = decode_conflict_authority_record(pointer_record)
                pointer = ActiveSemanticConflict.model_validate(pointer_value)
                transition_record = self._memory_plane.get_record(
                    pointer.current_record_id
                )
                if transition_record is None:
                    raise ValueError
                transition_type, transition_value, _ = decode_conflict_authority_record(
                    transition_record
                )
                if transition_type != "clarification_transition":
                    # A natural projection won the pointer after this
                    # completion: the successor is the projection's
                    # transition, internally consistent without naming this
                    # clarification's edge.
                    if (
                        transition_record.content.get("authority_digest")
                        != pointer.current_record_digest
                    ):
                        raise ValueError
                else:
                    transition = decode_persisted_conflict_generation(
                        transition_value, SemanticConflictClarificationTransition
                    )
                    if (
                        transition.processing_operation_id != processing_operation_id
                        or transition.reason.value != result.outcome.value
                        or transition.transition_digest != pointer.current_record_digest
                    ):
                        raise ValueError
                self.semantic_replay_authority()
            return result
        except (KeyError, TypeError, ValueError, ProjectionHistoryError) as exc:
            raise PreplanningStoreError(
                "clarification retained terminal result is corrupt"
            ) from exc

    def commit_conflict_clarification_transaction(
        self,
        *,
        proposal: AgentClarificationProposal,
        processing_operation_id: str,
        resulting_conflict_revision: str,
        policy_fingerprint: str,
        committed_outcome: Literal["accepted", "rejected", "insufficient"],
        semantic_result_digest: str,
        semantic_terminal: SemanticTerminalOutcome | None = None,
        clarification_cas: SemanticConflictClarificationCasInput | None = None,
    ) -> ConflictClarificationProcessingReceipt | ConflictClarificationAttemptResult:
        """Serialize one complete clarification transaction with integrity recovery."""

        linearization = self._semantic_integrity_linearization
        if linearization is None:
            return self._commit_conflict_clarification_transaction_linearized(
                proposal=proposal,
                processing_operation_id=processing_operation_id,
                resulting_conflict_revision=resulting_conflict_revision,
                policy_fingerprint=policy_fingerprint,
                committed_outcome=committed_outcome,
                semantic_result_digest=semantic_result_digest,
                semantic_terminal=semantic_terminal,
                clarification_cas=clarification_cas,
            )
        with linearization.exclusive():
            return self._commit_conflict_clarification_transaction_linearized(
                proposal=proposal,
                processing_operation_id=processing_operation_id,
                resulting_conflict_revision=resulting_conflict_revision,
                policy_fingerprint=policy_fingerprint,
                committed_outcome=committed_outcome,
                semantic_result_digest=semantic_result_digest,
                semantic_terminal=semantic_terminal,
                clarification_cas=clarification_cas,
            )

    def _commit_conflict_clarification_transaction_linearized(
        self,
        *,
        proposal: AgentClarificationProposal,
        processing_operation_id: str,
        resulting_conflict_revision: str,
        policy_fingerprint: str,
        committed_outcome: Literal["accepted", "rejected", "insufficient"],
        semantic_result_digest: str,
        semantic_terminal: SemanticTerminalOutcome | None = None,
        clarification_cas: SemanticConflictClarificationCasInput | None = None,
    ) -> ConflictClarificationProcessingReceipt | ConflictClarificationAttemptResult:
        """Atomically persist one idempotent semantic transaction and its receipt."""

        from memorii.core.memory_evolution.conflict_attention import (
            AgentClarificationProposal,
            ConflictClarificationAttemptResult,
            ConflictClarificationProcessingReceipt,
            ConflictClarificationWork,
            SemanticConflictClarificationCasInput,
            SemanticConflictClarificationTransition,
            SemanticConflictClarificationWorkGeneration,
        )
        from memorii.core.memory_evolution.projection_history import (
            decode_conflict_authority_record,
        )
        from memorii.core.semantic_ingestion.contracts import (
            SemanticGraphDelta,
            SemanticTerminalOutcome,
            encode_semantic_contract,
        )

        try:
            validated = AgentClarificationProposal.model_validate(proposal.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("clarification proposal is invalid") from exc
        # Clarification completion is never a detached semantic write.  The
        # submitted pointer is a successor of the OPEN revision in the user
        # proposal/work, so validate both bindings through that transition
        # below rather than incorrectly requiring the two revisions to match.
        if clarification_cas is None:
            raise PreplanningStoreError("clarification semantic transaction requires canonical CAS")
        try:
            # `model_copy()` deliberately skips validation.  Re-validate the
            # caller-supplied fence before consulting any retained member so a
            # forged digest cannot turn into a different completion request.
            clarification_cas = SemanticConflictClarificationCasInput.model_validate(
                clarification_cas.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("clarification CAS input is invalid") from exc
        if (
            clarification_cas.conflict_id != validated.conflict_id
            or clarification_cas.processing_operation_id != processing_operation_id
            or clarification_cas.proposal_digest != validated.proposal_digest
        ):
            raise PreplanningStoreError("clarification CAS input does not bind its proposal")
        retained_terminal = self._retained_clarification_terminal_result(
            proposal=validated,
            clarification_cas=clarification_cas,
            processing_operation_id=processing_operation_id,
        )
        if retained_terminal is not None:
            return retained_terminal
        terminal = None
        graph_delta = None
        if semantic_terminal is not None:
            try:
                terminal = SemanticTerminalOutcome.model_validate(semantic_terminal.model_dump(mode="python"))
            except (AttributeError, TypeError, ValueError) as exc:
                raise PreplanningStoreError("clarification semantic terminal is invalid") from exc
            expected_outcome = terminal.status if terminal.status in {"accepted", "rejected"} else "insufficient"
            if (
                terminal.operation_id != processing_operation_id
                or terminal.terminal_digest != semantic_result_digest
                or expected_outcome != committed_outcome
            ):
                raise PreplanningStoreError("clarification semantic terminal does not bind its transaction")
            if terminal.status == "accepted":
                graph_delta = self.enrich_identity_graph_delta(
                    SemanticGraphDelta.create(terminal), terminal,
                    operation_fence_id=processing_operation_id,
                )
                if any(
                    analysis.source_id != validated.source_user_event_id
                    or analysis.source_digest != validated.source_user_event_digest
                    for analysis in terminal.source_analyses
                ):
                    raise PreplanningStoreError("clarification semantic terminal does not bind its user event")
        elif committed_outcome != "insufficient":
            raise PreplanningStoreError("accepted or rejected clarification requires a governed semantic terminal")
        transaction_id = f"clarification-{processing_operation_id}"
        transaction_record_id = _conflict_clarification_transaction_id(processing_operation_id)
        receipt_record_id = _conflict_clarification_receipt_id(processing_operation_id)
        existing_transaction = self._memory_plane.get_record(transaction_record_id)
        existing_receipt = self._memory_plane.get_record(receipt_record_id)
        if existing_transaction is not None or existing_receipt is not None:
            persisted_receipt = self._decode_conflict_clarification_pair(
                processing_operation_id,
                transaction_record=existing_transaction,
                receipt_record=existing_receipt,
            )
            body = existing_transaction.content.get("transaction") if existing_transaction is not None else None
            terminal_hex = encode_semantic_contract(terminal).hex() if terminal is not None else None
            graph_delta_hex = encode_semantic_contract(graph_delta).hex() if graph_delta is not None else None
            if (
                persisted_receipt is None
                or not isinstance(body, dict)
                or body.get("processing_operation_id") != processing_operation_id
                or body.get("conflict_id") != validated.conflict_id
                or body.get("conflict_revision") != validated.conflict_revision
                or body.get("resulting_conflict_revision") != resulting_conflict_revision
                or body.get("proposal_digest") != validated.proposal_digest
                or body.get("source_user_event_id") != validated.source_user_event_id
                or body.get("source_user_event_digest") != validated.source_user_event_digest
                or body.get("policy_fingerprint") != policy_fingerprint
                or body.get("committed_outcome") != committed_outcome
                or body.get("semantic_result_digest") != semantic_result_digest
                or body.get("semantic_terminal_hex") != terminal_hex
                or body.get("graph_delta_hex") != graph_delta_hex
                or body.get("graph_delta_digest") != (graph_delta.delta_digest if graph_delta is not None else None)
                or body.get("clarification_cas_input_digest") != clarification_cas.input_digest
            ):
                raise PreplanningStoreError("clarification semantic transaction is partial or conflicting")
            # A receipt is not recoverable in isolation: its terminal attempt,
            # work successor, lifecycle transition, and active pointer must be
            # present as the exact retained closure before a lost-ack retry is
            # allowed to return it.
            try:
                # This verifies every immutable work generation/member before
                # selecting the terminal records below.  In particular, a
                # missing predecessor-keyed terminal generation must not turn
                # a lost-ack retry into a successful receipt replay.
                self._projection_history.current_clarification_work()
                current = self._projection_history._current_semantic_conflicts().get(
                    validated.conflict_id
                )
                if current is None or not isinstance(
                    current[1], SemanticConflictClarificationTransition
                ):
                    raise ValueError
                retained_transition = current[1]
                if (
                    retained_transition.reason.value != committed_outcome
                    or retained_transition.processing_operation_id != processing_operation_id
                    or retained_transition.proposal_digest != validated.proposal_digest
                    or retained_transition.resulting_attention.conflict_revision
                    != resulting_conflict_revision
                ):
                    raise ValueError
                work_members = tuple(
                    record for record in self._memory_plane.list_records(
                        source_kind="semantic_ingestion_conflict_authority"
                    )
                    if record.memory_id.startswith(
                        "semantic_ingestion:conflict-authority:clarification-work-member:"
                    )
                )
                result_members = tuple(
                    record for record in self._memory_plane.list_records(
                        source_kind="semantic_ingestion_conflict_authority"
                    )
                    if record.memory_id.startswith(
                        "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
                    )
                )
                terminal_work = next(
                    decode_persisted_conflict_generation(
                        decode_conflict_authority_record(record)[1], ConflictClarificationWork
                    )
                    for record in work_members
                    if decode_persisted_conflict_generation(
                        decode_conflict_authority_record(record)[1], ConflictClarificationWork
                    ).downstream_receipt_digest == persisted_receipt.receipt_digest
                )
                terminal_result = next(
                    decode_persisted_conflict_generation(
                        decode_conflict_authority_record(record)[1], ConflictClarificationAttemptResult
                    )
                    for record in result_members
                    if decode_persisted_conflict_generation(
                        decode_conflict_authority_record(record)[1], ConflictClarificationAttemptResult
                    ).downstream_receipt_digest == persisted_receipt.receipt_digest
                )
                if (
                    terminal_work.processing_operation_id != processing_operation_id
                    or terminal_work.owner_token is not None
                    or terminal_result.outcome.value != committed_outcome
                    or terminal_result.processing_operation_id != processing_operation_id
                ):
                    raise ValueError
            except (KeyError, StopIteration, TypeError, ValueError) as exc:
                raise PreplanningStoreError(
                    "clarification semantic transaction is partial or conflicting"
                ) from exc
            # The replay aggregate/checkpoint binds the same atomic closure
            # even for non-accepted outcomes.  Verify it before returning a
            # lost-ack retry so a stale or substituted aggregate cannot make
            # a completed receipt appear durable on its own.
            self.semantic_replay_authority()
            return persisted_receipt

        admission = self._writers.current()
        writer_binding = self._writers.commit_binding(admission)
        writer_record = self._writers.require_current(writer_binding)
        authorization = self._writers._authorize_atomic(
            writer_binding,
            capability=self._write_capability,
        )
        committed_at = self._now()
        event_records: tuple[CanonicalMemoryRecord, ...] = ()
        event_preconditions: tuple[MemoryPlanePrecondition, ...] = ()
        clarification_preconditions: tuple[MemoryPlanePrecondition, ...] = ()
        if clarification_cas is not None:
            from memorii.core.memory_evolution.conflict_attention import (
                ActiveSemanticConflict,
                SemanticConflictClarificationTransition,
            )
            from memorii.core.memory_evolution.projection_history import decode_conflict_authority_record

            pointer_id = (
                "semantic_ingestion:conflict-authority:pointer:"
                f"{clarification_cas.conflict_id}"
            )
            pointer_record = self._memory_plane.get_record(pointer_id)
            work_record = self._memory_plane.get_record(clarification_cas.work_record_id)
            attempt_record = self._memory_plane.get_record(clarification_cas.attempt_record_id)
            try:
                if pointer_record is None or work_record is None or attempt_record is None:
                    raise ValueError
                pointer = ActiveSemanticConflict.model_validate(
                    decode_conflict_authority_record(pointer_record)[1]
                )
                current = self._projection_history._current_semantic_conflicts().get(
                    clarification_cas.conflict_id
                )
                if current is None:
                    raise ValueError
                predecessor = current[1]
                if (
                    pointer.pointer_digest != clarification_cas.expected_pointer_digest
                    or pointer.pointer_revision != clarification_cas.expected_pointer_revision
                    or pointer.current_conflict_revision
                    != clarification_cas.expected_conflict_revision
                    or record_digest(work_record) != clarification_cas.work_record_digest
                    or record_digest(attempt_record) != clarification_cas.attempt_record_digest
                    or not isinstance(predecessor, SemanticConflictClarificationTransition)
                    or predecessor.reason.value != "submitted"
                    or predecessor.resulting_attention.status.value != "clarification_submitted"
                    or predecessor.predecessor_conflict_revision != validated.conflict_revision
                    or predecessor.proposal_digest != validated.proposal_digest
                    or pointer.current_record_digest != predecessor.transition_digest
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError) as exc:
                raise PreplanningStoreError("clarification semantic transaction race is conflicting") from exc
            clarification_preconditions = (
                RecordDigestPrecondition(
                    memory_id=pointer_record.memory_id,
                    expected_digest=record_digest(pointer_record),
                ),
                RecordDigestPrecondition(
                    memory_id=work_record.memory_id,
                    expected_digest=record_digest(work_record),
                ),
                RecordDigestPrecondition(
                    memory_id=attempt_record.memory_id,
                    expected_digest=record_digest(attempt_record),
                ),
            )
        semantic_event_batch = None
        semantic_event_batch_id = None
        semantic_event_batch_digest = None
        graph_revision_before = None
        graph_revision_after = None
        semantic_recovery_authority_generation = None
        semantic_recovery_authority_id = None
        semantic_replay_aggregate = None
        if graph_delta is not None:
            if terminal is None or terminal.authorization_read_set is None:
                raise PreplanningStoreError("accepted clarification has no authorization read set")
            (
                semantic_event_batch,
                semantic_replay_aggregate,
                event_records,
                event_preconditions,
            ) = self._clarification_semantic_event_authority_updates(
                graph_delta=graph_delta,
                terminal=terminal,
                policy_bundle=terminal.arbitration_policy_bundle,
                source_id=validated.source_user_event_id,
                processing_operation_id=processing_operation_id,
                writer_binding=writer_binding,
                committed_at=committed_at,
                complete_read_set_digest=(terminal.authorization_read_set.read_set_digest),
                authorization=authorization,
                terminal_clarification_conflict_ids=(clarification_cas.conflict_id,),
            )
            semantic_event_batch_id = _semantic_event_batch_id(semantic_event_batch.log_position.sequence)
            semantic_event_batch_digest = semantic_event_batch.source_event_batch_digest
            graph_revision_before = semantic_event_batch.events[0].payload.graph_revision_before
            graph_revision_after = semantic_event_batch.events[-1].payload.graph_revision_after
            semantic_recovery_authority_generation = semantic_event_batch.log_position.sequence + 1
            semantic_recovery_authority_id = _conflict_clarification_recovery_authority_id(processing_operation_id)
        transaction_body: dict[str, object] = {
            "processing_operation_id": processing_operation_id,
            "conflict_id": validated.conflict_id,
            "conflict_revision": validated.conflict_revision,
            "resulting_conflict_revision": resulting_conflict_revision,
            "proposal_digest": validated.proposal_digest,
            "source_user_event_id": validated.source_user_event_id,
            "source_user_event_digest": validated.source_user_event_digest,
            "policy_fingerprint": policy_fingerprint,
            "committed_outcome": committed_outcome,
            "semantic_result_digest": semantic_result_digest,
            "semantic_terminal_hex": (encode_semantic_contract(terminal).hex() if terminal is not None else None),
            "graph_delta_hex": (encode_semantic_contract(graph_delta).hex() if graph_delta is not None else None),
            "graph_delta_digest": (graph_delta.delta_digest if graph_delta is not None else None),
            "semantic_event_batch_id": semantic_event_batch_id,
            "semantic_event_batch_digest": semantic_event_batch_digest,
            "graph_revision_before": graph_revision_before,
            "graph_revision_after": graph_revision_after,
            "semantic_recovery_authority_generation": (semantic_recovery_authority_generation),
            "semantic_recovery_authority_id": semantic_recovery_authority_id,
            "clarification_cas_input_digest": (
                clarification_cas.input_digest if clarification_cas is not None else None
            ),
        }
        transaction_digest = sha256(encode_typed_value(transaction_body)).hexdigest()
        receipt = ConflictClarificationProcessingReceipt.create(
            processing_operation_id=processing_operation_id,
            conflict_id=validated.conflict_id,
            conflict_revision=resulting_conflict_revision,
            proposal_digest=validated.proposal_digest,
            policy_fingerprint=policy_fingerprint,
            semantic_transaction_id=transaction_id,
            semantic_transaction_digest=transaction_digest,
            semantic_result_digest=semantic_result_digest,
            committed_outcome=committed_outcome,
            committed_at=committed_at,
        )
        transaction_record = _conflict_clarification_transaction_record(
            transaction_id, transaction_body, transaction_digest, committed_at
        )
        receipt_record = _conflict_clarification_receipt_record(receipt, committed_at)
        # Complete the queue and its same-plane lifecycle edge in the exact
        # transaction that creates the receipt.  There is deliberately no
        # durable interval where semantic effects exist without conflict
        # closure (or vice versa).
        from memorii.core.memory_evolution.conflict_attention import (
            ClarificationAttemptOutcome,
            ConflictAttention,
            ConflictStatus,
            SemanticConflictClarificationTransition,
            SemanticConflictClarificationTransitionReason,
        )
        from memorii.core.memory_evolution.projection_history import (
            ProjectionHistoryError,
        )

        outcome_reason = {
            "accepted": SemanticConflictClarificationTransitionReason.ACCEPTED,
            "rejected": SemanticConflictClarificationTransitionReason.REJECTED,
            "insufficient": SemanticConflictClarificationTransitionReason.INSUFFICIENT,
        }[committed_outcome]
        try:
            work_type, work_payload, _ = decode_conflict_authority_record(work_record)
            attempt_type, attempt_payload, _ = decode_conflict_authority_record(attempt_record)
            current_work = decode_persisted_conflict_generation(
                work_payload, ConflictClarificationWork
            )
            current_attempt = decode_persisted_conflict_generation(
                attempt_payload, ConflictClarificationAttempt
            )
            member_mismatches = tuple(
                label
                for label, mismatched in (
                    ("work_type", work_type != "clarification_work_member"),
                    ("attempt_type", attempt_type != "clarification_attempt_member"),
                    (
                        "work_record_id",
                        current_work.work_digest
                        != clarification_cas.work_record_id.rsplit(":", 1)[-1],
                    ),
                    (
                        "attempt_record_id",
                        current_attempt.attempt_digest
                        != clarification_cas.attempt_record_id.rsplit(":", 1)[-1],
                    ),
                    (
                        "work_conflict_revision",
                        current_work.conflict_revision
                        != clarification_cas.expected_conflict_revision,
                    ),
                    (
                        "attempt_conflict_revision",
                        current_attempt.conflict_revision
                        != clarification_cas.expected_conflict_revision,
                    ),
                    ("owner_token", current_work.owner_token is None),
                    ("lease", current_work.lease_expires_at is None),
                    (
                        "work_lease_expired",
                        current_work.lease_expires_at is not None
                        and current_work.lease_expires_at <= committed_at,
                    ),
                    (
                        "work_operation",
                        current_work.processing_operation_id != processing_operation_id,
                    ),
                    ("work_proposal", current_work.proposal_digest != validated.proposal_digest),
                    (
                        "work_epoch",
                        current_work.ownership_epoch != clarification_cas.ownership_epoch,
                    ),
                    (
                        "work_owner",
                        current_work.owner_token is not None
                        and sha256(current_work.owner_token.encode("utf-8")).hexdigest()
                        != clarification_cas.owner_token_digest,
                    ),
                    (
                        "attempt_operation",
                        current_attempt.processing_operation_id != processing_operation_id,
                    ),
                    ("attempt_conflict", current_attempt.conflict_id != validated.conflict_id),
                    (
                        "attempt_proposal",
                        current_attempt.proposal_digest != validated.proposal_digest,
                    ),
                    (
                        "attempt_epoch",
                        current_attempt.ownership_epoch != clarification_cas.ownership_epoch,
                    ),
                    (
                        "attempt_owner",
                        current_attempt.owner_token_digest
                        != clarification_cas.owner_token_digest,
                    ),
                    (
                        "attempt_lease",
                        current_attempt.lease_expires_at != current_work.lease_expires_at,
                    ),
                    ("attempt_lease_expired", current_attempt.lease_expires_at <= committed_at),
                )
                if mismatched
            )
            if member_mismatches:
                raise ValueError(
                    "clarification CAS member mismatch: " + ",".join(member_mismatches)
                )
            terminal_values = current_work.model_dump(mode="python", exclude={"work_digest"})
            terminal_values.update(
                owner_token=None,
                lease_expires_at=None,
                downstream_receipt_digest=receipt.receipt_digest,
                work_revision=current_work.work_revision + 1,
                predecessor_work_digest=current_work.work_digest,
            )
            terminal_work = self._clarification_work_from_values(terminal_values)
            from memorii.core.memory_evolution.conflict_attention import (
                ConflictClarificationAttemptResult,
            )
            result_values = {
                "attempt_id": current_attempt.attempt_id,
                "attempt_digest": current_attempt.attempt_digest,
                "processing_operation_id": processing_operation_id,
                "ownership_epoch": current_attempt.ownership_epoch,
                "owner_token_digest": current_attempt.owner_token_digest,
                "outcome": ClarificationAttemptOutcome(committed_outcome),
                "attempt_count_after": current_work.attempt_count,
                "downstream_receipt_digest": receipt.receipt_digest,
                "superseded_by_conflict_revision": None,
                "completed_at": committed_at,
            }
            provisional_result = ConflictClarificationAttemptResult.model_construct(
                **result_values, result_digest="0" * 64
            )
            result = ConflictClarificationAttemptResult(
                **result_values,
                result_digest=sha256(
                    b"memorii.conflict-clarification-attempt-result.v1\0"
                    + encode_typed_value(
                        provisional_result.model_dump(
                            mode="json", exclude={"result_digest"}
                        )
                    )
                ).hexdigest(),
            )
            # Completion is a normal immutable work successor.  Keeping the
            # terminal work/result members without their predecessor-keyed
            # generation would make replay reject the queue as corrupted.
            terminal_generation = SemanticConflictClarificationWorkGeneration.create(
                predecessor_work_digest=current_work.work_digest,
                work=terminal_work,
                attempt_result=result,
            )
            attention_values = predecessor.resulting_attention.model_dump(mode="python")
            attention_values.update(
                conflict_revision=resulting_conflict_revision,
                # An accepted answer resolves the conflict.  Rejected and
                # insufficient answers deliberately reopen it for a future
                # user clarification; their queue/result closure is still
                # terminal for this processing operation.
                status=(
                    ConflictStatus.RESOLVED
                    if committed_outcome == "accepted"
                    else ConflictStatus.OPEN
                ),
            )
            attention = ConflictAttention(**attention_values)
            # The preliminary semantic-effect preparation is read-only and
            # already suppresses the claimed conflict.  If it materializes
            # other conflict edges, the terminal edge remains the immediate
            # successor of its submitted predecessor and the projection
            # allocator advances after this one-record prefix.
            projection_immutable_count = sum(
                1
                for record in event_records
                if (
                    record.source_kind == "semantic_ingestion_conflict_authority"
                    and record.content.get("immutable_record_coordinate") is not None
                )
            )
            transition_body = {
                "conflict_id": validated.conflict_id,
                "predecessor_conflict_revision": clarification_cas.expected_conflict_revision,
                "predecessor_record_digest": predecessor.transition_digest,
                "predecessor_status": ConflictStatus.CLARIFICATION_SUBMITTED,
                "resulting_attention": attention,
                "reason": outcome_reason,
                "proposal_digest": validated.proposal_digest,
                "processing_operation_id": processing_operation_id,
                "successor_conflict_revision": None,
                "record_coordinate": (
                    self._projection_history.semantic_conflict_replay_binding().immutable_record_count
                    + 1
                ),
                "transition_coordinate": clarification_cas.expected_pointer_revision + 1,
                "transitioned_at": committed_at,
            }
            transition = SemanticConflictClarificationTransition(
                **transition_body,
                transition_digest=sha256(
                    b"memorii.semantic-conflict-clarification-transition.v1\0"
                    + encode_typed_value(
                        transition_body
                        | {"resulting_attention": attention.model_dump(mode="python")}
                    )
                ).hexdigest(),
            )
            prepared_closure = self._projection_history.prepare_clarification_transition_closure(
                transition,
                include_ledger_head=(projection_immutable_count == 0),
            )
            terminal_work_record = self._projection_history._conflict_authority_record(
                "semantic_ingestion:conflict-authority:clarification-work-member:"
                f"{terminal_work.work_digest}", terminal_work, committed_at
            )
            result_record = self._projection_history._conflict_authority_record(
                "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
                f"{result.result_digest}", result, committed_at
            )
            terminal_generation_record = self._projection_history._conflict_authority_record(
                "semantic_ingestion:conflict-authority:clarification-work:"
                f"{terminal_generation.predecessor_work_digest}",
                terminal_generation,
                committed_at,
            )
        except (KeyError, TypeError, ValueError, ProjectionHistoryError) as exc:
            raise PreplanningStoreError(
                "clarification semantic transaction race is conflicting: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        # The lifecycle closure is part of the replay prefix.  Rebuild the
        # side-effect-free event authority only after its exact records exist,
        # so the aggregate/checkpoint and the pointer advance share one CAS.
        if graph_delta is not None:
            assert terminal is not None and terminal.authorization_read_set is not None
            (
                semantic_event_batch,
                semantic_replay_aggregate,
                event_records,
                event_preconditions,
            ) = self._clarification_semantic_event_authority_updates(
                graph_delta=graph_delta,
                terminal=terminal,
                policy_bundle=terminal.arbitration_policy_bundle,
                source_id=validated.source_user_event_id,
                processing_operation_id=processing_operation_id,
                writer_binding=writer_binding,
                committed_at=committed_at,
                complete_read_set_digest=terminal.authorization_read_set.read_set_digest,
                authorization=authorization,
                pending_conflict_records=prepared_closure.records,
                pending_conflict_immutable_prefix_count=(
                    1 if projection_immutable_count else 0
                ),
            )
        else:
            event_records, event_preconditions, semantic_replay_aggregate = (
                self._prepare_conflict_replay_binding_update(
                    pending_conflict_records=prepared_closure.records,
                    writer_epoch=writer_binding.expected_writer_epoch,
                    timestamp=committed_at,
                )
            )
        recovery_authority_records: tuple[CanonicalMemoryRecord, ...] = ()
        if graph_delta is not None:
            if semantic_event_batch is None or semantic_recovery_authority_generation is None:
                raise PreplanningStoreError("clarification recovery generation is incomplete")
            recovery_authority_records = (
                _conflict_clarification_recovery_authority_record(
                    processing_operation_id=processing_operation_id,
                    generation=semantic_recovery_authority_generation,
                    batch=semantic_event_batch,
                    replay_aggregate=semantic_replay_aggregate,
                    transaction_record=transaction_record,
                    receipt_record=receipt_record,
                    timestamp=committed_at,
                ),
            )
        try:
            self._memory_plane.conditionally_write_records(
                (
                    transaction_record,
                    receipt_record,
                    terminal_generation_record,
                    terminal_work_record,
                    result_record,
                    *prepared_closure.records,
                    *recovery_authority_records,
                    *event_records,
                ),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=transaction_record.memory_id),
                    RecordAbsentPrecondition(memory_id=receipt_record.memory_id),
                    RecordAbsentPrecondition(memory_id=terminal_generation_record.memory_id),
                    RecordAbsentPrecondition(memory_id=terminal_work_record.memory_id),
                    RecordAbsentPrecondition(memory_id=result_record.memory_id),
                    *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in recovery_authority_records),
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id,
                        expected_digest=record_digest(writer_record),
                    ),
                    *event_preconditions,
                    *clarification_preconditions,
                    *prepared_closure.preconditions,
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError:
            try:
                return self.commit_conflict_clarification_transaction(
                    proposal=validated,
                    processing_operation_id=processing_operation_id,
                    resulting_conflict_revision=resulting_conflict_revision,
                    policy_fingerprint=policy_fingerprint,
                    committed_outcome=committed_outcome,
                    semantic_result_digest=semantic_result_digest,
                    semantic_terminal=terminal,
                    clarification_cas=clarification_cas,
                )
            except PreplanningStoreError as recovery_exc:
                raise PreplanningStoreError("clarification semantic transaction race is conflicting") from recovery_exc
        return receipt

    def _clarification_semantic_event_authority_updates(
        self,
        *,
        graph_delta: SemanticGraphDelta,
        terminal: SemanticTerminalOutcome,
        policy_bundle: SemanticArbitrationPolicyBundle | None,
        source_id: str,
        processing_operation_id: str,
        writer_binding: SemanticWriterCommitBinding,
        committed_at: datetime,
        complete_read_set_digest: str,
        authorization: SemanticWriterWriteAuthorization,
        pending_conflict_records: tuple[CanonicalMemoryRecord, ...] = (),
        terminal_clarification_conflict_ids: tuple[str, ...] = (),
        pending_conflict_immutable_prefix_count: int = 0,
    ) -> tuple[
        SemanticMemoryEventBatch,
        SemanticReplayAuthorityAggregate,
        tuple[CanonicalMemoryRecord, ...],
        tuple[MemoryPlanePrecondition, ...],
    ]:
        """Build one canonical graph effect for the clarification transaction."""

        from memorii.core.memory_evolution.conflict_attention import (
            SemanticConflictClarificationTransition,
            decode_persisted_conflict_generation,
        )
        from memorii.core.memory_evolution.policy_migration import (
            PolicyMigrationError,
        )
        from memorii.core.memory_evolution.projection_history import (
            ProjectionCommitRequest,
            ProjectionHistoryError,
            decode_conflict_authority_record,
            projection_records_from_replay_state,
        )
        from memorii.core.memory_evolution.projection_scheduler import (
            ProjectionSchedulerError,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            SemanticEventReplayError,
            advance_semantic_replay_authority,
            build_semantic_memory_event_batch,
            create_replay_checkpoint,
            replay_semantic_event_batches,
        )

        try:
            if policy_bundle is None:
                raise PreplanningStoreError(
                    "clarification arbitration policy is unavailable"
                )
            if self._semantic_freeze_guard is not None:
                self._semantic_freeze_guard(graph_delta)
            prior = self.semantic_replay_authority()
            if prior.graph_state != self.semantic_replay_state():
                raise PreplanningStoreError("semantic replay authority graph state is stale")
            prior_state = prior.graph_state
            graph_revision_after = sha256(
                b"memorii.semantic-ingestion.graph-revision.v1"
                + b"\0"
                + prior_state.graph_revision.encode()
                + b"\0"
                + graph_delta.delta_digest.encode()
            ).hexdigest()
            batch = build_semantic_memory_event_batch(
                graph_delta=graph_delta,
                prior_state=prior_state,
                repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                source_id=source_id,
                transaction_group_id=processing_operation_id,
                operation_fence_id=processing_operation_id,
                writer_epoch=writer_binding.expected_writer_epoch,
                graph_revision_before=prior_state.graph_revision,
                graph_revision_after=graph_revision_after,
                timestamp=committed_at,
                registry=self._event_schema_registry,
            )
            next_state = replay_semantic_event_batches(
                repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                batches=(batch,),
                registry_history=self._event_schema_registry_history,
                initial_state=prior_state,
            )
            prior_bindings = (
                *prior.observation_bindings,
                *prior.progress_bindings,
                *prior.artifact_bindings,
            )
            reconstructed = self._reconstruct_semantic_replay_authority(
                graph_state=next_state,
                bindings=prior_bindings,
            )
            current_projection_bindings = self._projection_history.replay_bindings()
            (
                temporal_projections,
                trust_projections,
                temporal_policy_fingerprint,
                trust_policy_fingerprint,
                arbitration_as_of,
            ) = projection_records_from_replay_state(
                next_state,
                active_temporal=(
                    self._projection_history.active_temporal_authority()
                    if current_projection_bindings
                    else None
                ),
                active_trust=(
                    self._projection_history.active_trust_authority()
                    if current_projection_bindings
                    else None
                ),
                active_temporal_policy=(
                    policy_bundle.temporal_policy
                    if current_projection_bindings
                    else None
                ),
                active_trust_policy=(
                    policy_bundle.trust_policy
                    if current_projection_bindings
                    else None
                ),
            )
            record_terminal_clarification_conflict_ids = tuple(
                sorted(
                    {
                        decode_persisted_conflict_generation(
                            decode_conflict_authority_record(record)[1],
                            SemanticConflictClarificationTransition,
                        ).conflict_id
                        for record in pending_conflict_records
                        if record.content.get("authority_record_type")
                        == "clarification_transition"
                    }
                )
            )
            terminal_clarification_conflict_ids = tuple(
                sorted(
                    set(terminal_clarification_conflict_ids)
                    | set(record_terminal_clarification_conflict_ids)
                )
            )
            prepared_projection = self._projection_history.prepare(
                ProjectionCommitRequest(
                    repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                    operation_id=processing_operation_id,
                    graph_revision=next_state.graph_revision,
                    event_batch_sequence=batch.log_position.sequence,
                    event_batch_digest=batch.source_event_batch_digest,
                    complete_read_set_digest=complete_read_set_digest,
                    writer_epoch=writer_binding.expected_writer_epoch,
                    base_snapshot_token=prior_state.state_digest,
                    temporal_policy_fingerprint=temporal_policy_fingerprint,
                    trust_policy_fingerprint=trust_policy_fingerprint,
                    arbitration_as_of=arbitration_as_of,
                    temporal_projections=temporal_projections,
                    trust_projections=trust_projections,
                    semantic_conflict_authority=(
                        self._projection_history.resolve_semantic_conflict_authority(
                            temporal_projections=temporal_projections,
                            trust_projections=trust_projections,
                        )
                    ),
                    terminal_clarification_conflict_ids=(
                        terminal_clarification_conflict_ids
                    ),
                ),
                capability=self._write_capability,
                authorization=authorization,
                pending_conflict_immutable_prefix_count=(
                    pending_conflict_immutable_prefix_count
                ),
            )
            prepared_catch_up = self._policy_migration.prepare_write_catch_up(
                temporal_projections=temporal_projections,
                trust_projections=trust_projections,
                trust_decay_command_digests=(
                    prepared_projection.publication.trust.generation.canonical_decay_command_digests
                ),
                graph_revision=next_state.graph_revision,
                graph_delta_digest=graph_delta.delta_digest,
                ledger_position=batch.log_position.sequence,
                watermark=batch.source_event_batch_digest,
                complete_read_set_digest=complete_read_set_digest,
            )
            projection_records = prepared_projection.records
            projection_preconditions = prepared_projection.preconditions
            projection_bindings = prepared_projection.publication.replay_bindings
            conflict_binding = self._projection_history.semantic_conflict_replay_binding(
                pending_records=(*projection_records, *pending_conflict_records),
            )
            checkpoint = create_replay_checkpoint(
                state=next_state,
                watermark_batch=batch,
                writer_epoch=writer_binding.expected_writer_epoch,
                authority=self._checkpoint_resume_authority,
                created_at=committed_at,
                reconstructed_replay_authority_digest=(reconstructed.authority_digest),
                projection_history_bindings=projection_bindings,
                semantic_conflict_replay_binding=conflict_binding,
            )
            aggregate = advance_semantic_replay_authority(
                prior,
                graph_state=next_state,
                member_bindings=(),
                reconstructed_authority_digest=reconstructed.authority_digest,
                latest_checkpoint=checkpoint,
                projection_history_bindings=projection_bindings,
                semantic_conflict_replay_binding=conflict_binding,
            )
        except (
            PolicyMigrationError,
            ProjectionHistoryError,
            ProjectionSchedulerError,
            SemanticEventReplayError,
        ) as exc:
            raise PreplanningStoreError("clarification canonical semantic effect is invalid") from exc
        event_record_values = [
            _semantic_event_batch_record(batch, committed_at),
            _semantic_replay_state_record(next_state, committed_at),
        ]
        event_record_values.extend(
            self._identity_reservation_records(
                terminal,
                graph_delta=graph_delta,
                operation_fence_id=processing_operation_id,
                expected_graph_revision=prior_state.graph_revision,
                timestamp=committed_at,
            )
        )
        reference_record = self._memory_plane.get_record(_reference_integrity_ledger_id())
        if reference_record is not None:
            from memorii.core.memory_evolution.reference_integrity import (
                advance_reference_integrity,
            )

            try:
                prior_reference_snapshot = self.reference_integrity_snapshot()
                reference_snapshot = advance_reference_integrity(
                    prior_reference_snapshot,
                    prior_state=prior_state,
                    next_state=next_state,
                    operation_id=graph_delta.operation_id,
                    completed_at=committed_at,
                )
                self._validate_planned_identity_reference_mutations(
                    terminal,
                    graph_delta=graph_delta,
                    operation_fence_id=processing_operation_id,
                    graph_revision_before=prior_state.graph_revision,
                    graph_revision_after=graph_revision_after,
                    committed_at=batch.events[0].timestamp,
                    prior_reference_snapshot=prior_reference_snapshot,
                    next_reference_snapshot=reference_snapshot,
                )
            except ValueError as exc:
                raise PreplanningStoreError(
                    "clarification reference integrity ledger advance failed"
                ) from exc
            event_record_values.append(
                _reference_integrity_ledger_record(reference_snapshot, committed_at)
            )
        event_record_values.extend(
            (
                _semantic_replay_authority_record(aggregate, committed_at),
                _semantic_checkpoint_lifecycle_record(
                    self._checkpoint_resume_authority, committed_at
                ),
                _semantic_registry_history_record(
                    self._event_schema_registry_history, committed_at
                ),
            )
        )
        event_records = tuple(event_record_values)
        records = (*event_records, *projection_records, *prepared_catch_up.records)
        return (
            batch,
            aggregate,
            records,
            (
                *self._semantic_authority_record_preconditions(event_records, require_unfrozen=True),
                *projection_preconditions,
                *prepared_catch_up.preconditions,
            ),
        )

    def resolve_conflict_clarification_receipt(
        self, processing_operation_id: str
    ) -> ConflictClarificationProcessingReceipt | None:
        receipt_record = self._memory_plane.get_record(_conflict_clarification_receipt_id(processing_operation_id))
        transaction_record = self._memory_plane.get_record(
            _conflict_clarification_transaction_id(processing_operation_id)
        )
        receipt = self._decode_conflict_clarification_pair(
            processing_operation_id,
            transaction_record=transaction_record,
            receipt_record=receipt_record,
        )
        transaction = transaction_record.content.get("transaction") if transaction_record is not None else None
        if receipt is not None and isinstance(transaction, dict) and transaction.get("graph_delta_hex") is not None:
            self.semantic_replay_authority()
        return receipt

    def _decode_conflict_clarification_pair(
        self,
        processing_operation_id: str,
        *,
        transaction_record: CanonicalMemoryRecord | None,
        receipt_record: CanonicalMemoryRecord | None,
        verify_event_effect: bool = True,
        verify_generation_authority: bool = True,
        offline_recovery: bool = False,
    ) -> ConflictClarificationProcessingReceipt | None:
        from memorii.core.memory_evolution.conflict_attention import (
            ConflictClarificationProcessingReceipt,
        )
        from memorii.core.semantic_ingestion.contracts import (
            SemanticGraphDelta,
            SemanticTerminalOutcome,
            decode_semantic_contract,
            encode_semantic_contract,
        )

        if transaction_record is None and receipt_record is None:
            return None
        try:
            if transaction_record is None or receipt_record is None:
                raise ValueError("orphan clarification record")
            if (
                transaction_record.source_kind != "semantic_ingestion_conflict_clarification_transaction"
                or receipt_record.source_kind != "semantic_ingestion_conflict_clarification_receipt"
                or transaction_record.content.get("semantic_ingestion_kind") != "conflict_clarification_transaction"
                or receipt_record.content.get("semantic_ingestion_kind") != "conflict_clarification_processing_receipt"
                or transaction_record.memory_id != _conflict_clarification_transaction_id(processing_operation_id)
                or receipt_record.memory_id != _conflict_clarification_receipt_id(processing_operation_id)
                or set(transaction_record.content)
                != {
                    "semantic_ingestion_kind",
                    "semantic_transaction_id",
                    "semantic_transaction_digest",
                    "transaction",
                }
                or set(receipt_record.content) != {"semantic_ingestion_kind", "receipt"}
            ):
                raise ValueError("clarification record kind mismatch")
            receipt = ConflictClarificationProcessingReceipt.model_validate_json(
                json.dumps(receipt_record.content["receipt"])
            )
            body = transaction_record.content["transaction"]
            transaction_id = transaction_record.content["semantic_transaction_id"]
            transaction_digest = transaction_record.content["semantic_transaction_digest"]
            if (
                not isinstance(body, dict)
                or set(body)
                != {
                    "processing_operation_id",
                    "conflict_id",
                    "conflict_revision",
                    "resulting_conflict_revision",
                    "proposal_digest",
                    "source_user_event_id",
                    "source_user_event_digest",
                    "policy_fingerprint",
                    "committed_outcome",
                    "semantic_result_digest",
                    "semantic_terminal_hex",
                    "graph_delta_hex",
                    "graph_delta_digest",
                    "semantic_event_batch_id",
                    "semantic_event_batch_digest",
                    "graph_revision_before",
                    "graph_revision_after",
                    "semantic_recovery_authority_generation",
                    "semantic_recovery_authority_id",
                    "clarification_cas_input_digest",
                }
                or not isinstance(transaction_id, str)
                or not isinstance(transaction_digest, str)
                or transaction_digest != sha256(encode_typed_value(body)).hexdigest()
                or transaction_id != f"clarification-{processing_operation_id}"
                or receipt.processing_operation_id != processing_operation_id
                or receipt.semantic_transaction_id != transaction_id
                or receipt.semantic_transaction_digest != transaction_digest
                or receipt.conflict_id != body["conflict_id"]
                or receipt.conflict_revision != body["resulting_conflict_revision"]
                or receipt.proposal_digest != body["proposal_digest"]
                or receipt.policy_fingerprint != body["policy_fingerprint"]
                or receipt.committed_outcome != body["committed_outcome"]
                or receipt.semantic_result_digest != body["semantic_result_digest"]
            ):
                raise ValueError("clarification pair binding mismatch")
            terminal_hex = body.get("semantic_terminal_hex")
            graph_delta_hex = body.get("graph_delta_hex")
            graph_delta_digest = body.get("graph_delta_digest")
            event_batch_id = body.get("semantic_event_batch_id")
            event_batch_digest = body.get("semantic_event_batch_digest")
            graph_revision_before = body.get("graph_revision_before")
            graph_revision_after = body.get("graph_revision_after")
            semantic_recovery_authority_generation = body.get("semantic_recovery_authority_generation")
            semantic_recovery_authority_id = body.get("semantic_recovery_authority_id")
            clarification_cas_input_digest = body.get("clarification_cas_input_digest")
            if clarification_cas_input_digest is not None and (
                not isinstance(clarification_cas_input_digest, str)
                or len(clarification_cas_input_digest) != 64
            ):
                raise TypeError("clarification CAS binding is invalid")
            if terminal_hex is None:
                if (
                    receipt.committed_outcome != "insufficient"
                    or graph_delta_hex is not None
                    or graph_delta_digest is not None
                    or event_batch_id is not None
                    or event_batch_digest is not None
                    or graph_revision_before is not None
                    or graph_revision_after is not None
                    or semantic_recovery_authority_generation is not None
                    or semantic_recovery_authority_id is not None
                ):
                    raise ValueError("clarification semantic effect is absent")
            else:
                if not isinstance(terminal_hex, str):
                    raise TypeError("clarification terminal encoding is invalid")
                terminal = decode_semantic_contract(bytes.fromhex(terminal_hex), SemanticTerminalOutcome)
                expected_outcome = terminal.status if terminal.status in {"accepted", "rejected"} else "insufficient"
                if (
                    terminal.operation_id != processing_operation_id
                    or terminal.terminal_digest != receipt.semantic_result_digest
                    or expected_outcome != receipt.committed_outcome
                ):
                    raise ValueError("clarification terminal binding mismatch")
                if terminal.status == "accepted":
                    if not (
                        isinstance(graph_delta_hex, str)
                        and isinstance(event_batch_id, str)
                        and isinstance(event_batch_digest, str)
                        and isinstance(graph_revision_before, str)
                        and isinstance(graph_revision_after, str)
                        and isinstance(semantic_recovery_authority_generation, int)
                        and isinstance(semantic_recovery_authority_id, str)
                    ):
                        raise TypeError("accepted clarification graph effect is absent")
                    graph_delta = decode_semantic_contract(bytes.fromhex(graph_delta_hex), SemanticGraphDelta)
                    if (
                        bytes.fromhex(terminal_hex) != encode_semantic_contract(terminal)
                        or bytes.fromhex(graph_delta_hex) != encode_semantic_contract(graph_delta)
                        or (
                            not offline_recovery
                            and graph_delta
                            != self.enrich_identity_graph_delta(
                                SemanticGraphDelta.create(terminal),
                                terminal,
                                operation_fence_id=processing_operation_id,
                            )
                        )
                        or graph_delta.delta_digest != graph_delta_digest
                        or any(
                            analysis.source_id != body["source_user_event_id"]
                            or analysis.source_digest != body["source_user_event_digest"]
                            for analysis in terminal.source_analyses
                        )
                    ):
                        raise ValueError("clarification graph effect is substituted")
                    authority_batch = None
                    if verify_generation_authority:
                        recovery_authority_record = self._memory_plane.get_record(semantic_recovery_authority_id)
                        if recovery_authority_record is None:
                            raise ValueError("accepted clarification recovery authority is absent")
                        authority_batch = self._validate_clarification_recovery_authority(
                            authority_record=recovery_authority_record,
                            expected_transaction_record=transaction_record,
                            expected_receipt_record=receipt_record,
                        )
                        if authority_batch.log_position.sequence + 1 != semantic_recovery_authority_generation:
                            raise ValueError("accepted clarification generation is substituted")
                    if verify_event_effect:
                        matching_batches = tuple(
                            batch
                            for batch in self.semantic_event_batches()
                            if _semantic_event_batch_id(batch.log_position.sequence) == event_batch_id
                        )
                        if len(matching_batches) != 1:
                            raise ValueError("accepted clarification event effect is absent")
                        batch = matching_batches[0]
                        if (
                            batch.source_event_batch_digest != event_batch_digest
                            or batch.graph_delta_digest != graph_delta.delta_digest
                            or batch.source_id != body["source_user_event_id"]
                            or batch.transaction_group_id != processing_operation_id
                            or batch.operation_fence_id != processing_operation_id
                            or batch.events[0].payload.graph_revision_before != graph_revision_before
                            or batch.events[-1].payload.graph_revision_after != graph_revision_after
                            or (authority_batch is not None and batch != authority_batch)
                        ):
                            raise ValueError("accepted clarification event effect is substituted")
                        self.semantic_replay_authority()
                elif (
                    graph_delta_hex is not None
                    or graph_delta_digest is not None
                    or event_batch_id is not None
                    or event_batch_digest is not None
                    or graph_revision_before is not None
                    or graph_revision_after is not None
                    or semantic_recovery_authority_generation is not None
                    or semantic_recovery_authority_id is not None
                ):
                    raise ValueError("non-accepted clarification has a graph effect")
            return receipt
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("clarification semantic transaction integrity failure") from exc

    def semantic_event_batches(self) -> tuple[SemanticMemoryEventBatch, ...]:
        """Read and verify the repository-scoped canonical event authority."""

        from memorii.core.semantic_ingestion.event_replay import (
            SemanticEventReplayError,
            decode_semantic_memory_event_batch,
            replay_semantic_event_batches,
        )

        records = sorted(
            (
                record
                for record in self._memory_plane.list_records()
                if record.source_kind == "semantic_ingestion_event_batch"
            ),
            key=lambda record: record.memory_id,
        )
        batches: list[SemanticMemoryEventBatch] = []
        for record in records:
            try:
                canonical_hex = record.content["canonical_hex"]
                if not isinstance(canonical_hex, str):
                    raise TypeError
                batch = decode_semantic_memory_event_batch(
                    bytes.fromhex(canonical_hex),
                    registry_history=self._event_schema_registry_history,
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._semantic_integrity_incident_reporter((sha256(encode_typed_value(record.content)).hexdigest(),))
                raise PreplanningStoreError("semantic event batch authority is corrupt") from exc
            if (
                record.memory_id != _semantic_event_batch_id(batch.log_position.sequence)
                or record.content.get("event_batch_digest") != batch.source_event_batch_digest
            ):
                self._semantic_integrity_incident_reporter((sha256(encode_typed_value(record.content)).hexdigest(),))
                raise PreplanningStoreError("semantic event batch authority coordinate is invalid")
            batches.append(batch)
        try:
            replay_semantic_event_batches(
                repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                batches=batches,
                registry_history=self._event_schema_registry_history,
            )
        except SemanticEventReplayError as exc:
            self._semantic_integrity_incident_reporter(
                tuple(batch.source_event_batch_digest for batch in batches)
                or (sha256(b"semantic-event-authority-empty-corruption").hexdigest(),)
            )
            raise PreplanningStoreError("semantic event batch authority cannot be replayed") from exc
        return tuple(batches)

    def semantic_replay_state(self) -> SemanticReplayState:
        from memorii.core.semantic_ingestion.event_replay import (
            decode_semantic_replay_state,
            replay_semantic_event_batches,
        )

        batches = self.semantic_event_batches()
        reconstructed = replay_semantic_event_batches(
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            batches=batches,
            registry_history=self._event_schema_registry_history,
        )
        record = self._memory_plane.get_record(_semantic_replay_state_id())
        if record is None:
            if batches:
                raise PreplanningStoreError("semantic replay state authority is absent")
            return reconstructed
        try:
            canonical_hex = record.content["canonical_hex"]
            if not isinstance(canonical_hex, str):
                raise TypeError
            persisted = decode_semantic_replay_state(bytes.fromhex(canonical_hex))
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("semantic replay state authority is corrupt") from exc
        if persisted != reconstructed or record.content.get("state_digest") != persisted.state_digest:
            raise PreplanningStoreError("semantic replay state differs from genesis reconstruction")
        return persisted

    def graph_state_snapshot(self):
        """Project the complete typed graph snapshot from canonical event authority."""

        from memorii.core.memory_evolution.graph_records import (
            GraphPartitionVersion,
            GraphReadSet,
            GraphRecordKind,
            GraphStateSnapshot,
            SnapshotGraphRecord,
            canonical_graph_codec_manifest,
            graph_digest,
        )
        from memorii.core.memory_evolution.reference_integrity import (
            generated_reference_schema_manifest,
        )

        first = self.semantic_replay_state()
        ledger = self.reference_integrity_snapshot()
        second = self.semantic_replay_state()
        if first != second or ledger.audit_certificate is None:
            raise PreplanningStoreError("stale_graph_snapshot")
        codec_manifest = canonical_graph_codec_manifest()
        codec_by_kind = {item.record_kind: item for item in codec_manifest.entries}
        records = tuple(
            SnapshotGraphRecord(
                record_id=item.record_id,
                record_version=item.record_version,
                payload=item.record,
                codec_fingerprint=codec_by_kind[item.record_kind].codec_fingerprint,
                persistence_schema_fingerprint=(
                    codec_by_kind[item.record_kind].payload_schema_fingerprint
                ),
                record_digest=item.record_digest,
            )
            for item in first.materialized_records
        )
        manifest_fingerprints = tuple(sorted((
            codec_manifest.manifest_fingerprint,
            generated_reference_schema_manifest().manifest_fingerprint,
        )))
        read_set = GraphReadSet.create(
            record_keys=tuple(
                sorted(f"{item.payload_record_kind}:{item.record_id}" for item in records)
            ),
            partition_versions=(
                GraphPartitionVersion(partition_id="canonical_graph", version=first.state_digest),
                GraphPartitionVersion(partition_id="reference_ledger", version=ledger.ledger_digest),
            ),
            manifest_fingerprints=manifest_fingerprints,
        )
        snapshot_token = graph_digest(
            b"memorii.graph-snapshot-token.v1\0",
            (first.state_digest, ledger.ledger_digest),
        )
        values = {
            "snapshot_token": snapshot_token,
            "graph_revision": first.graph_revision,
            "system_as_of": self._now().astimezone(UTC),
            "records": records,
            "exact_record_counts_by_kind": tuple(
                (kind, sum(item.payload_record_kind == kind for item in records))
                for kind in sorted(GraphRecordKind.__args__)
            ),
            "codec_manifest_fingerprint": codec_manifest.manifest_fingerprint,
            "governance_policy_fingerprints": (),
            "read_set": read_set,
        }
        return GraphStateSnapshot.model_validate(
            values
            | {"snapshot_digest": graph_digest(b"memorii.graph-state-snapshot.v1\0", values)}
        )

    def lineage_audit_scope_event_ids(
        self,
        *,
        tenant_partition_id: str,
        authorized_scope_ids: tuple[str, ...],
    ) -> frozenset[str]:
        """Resolve event disclosure from retained admission-scope authority."""

        allowed = set(authorized_scope_ids)
        event_ids: set[str] = set()
        for batch in self.semantic_event_batches():
            control_record = self._memory_plane.get_record(
                f"semantic_ingestion:operation:{batch.operation_fence_id}"
            )
            if control_record is None:
                raise PreplanningStoreError("lineage audit operation authority is absent")
            control = _control_from_record(control_record)
            fence = control.operation_fence
            index = self._memory_plane.get_record(
                f"semantic_ingestion:admission:{fence.delivery_key_digest}"
            )
            if (
                index is None
                or index.source_kind != "semantic_ingestion_admission_index"
                or index.content.get("operation_fence_binding")
                != fence.model_dump(mode="json")
                or index.content.get("tenant_partition_id") != tenant_partition_id
            ):
                raise PreplanningStoreError("lineage audit admission authority is invalid")
            required = tuple(index.content.get("required_scopes", ()))
            if required and set(required).issubset(allowed):
                event_ids.update(item.event_id for item in batch.events)
        return frozenset(event_ids)

    def reference_integrity_snapshot(self):
        """Read the canonical generated-manifest edge-ledger authority."""

        from memorii.core.memory_evolution.reference_integrity import (
            ReferenceEdgeLedgerSnapshot,
            validate_reference_integrity_converse,
        )

        record = self._memory_plane.get_record(_reference_integrity_ledger_id())
        if record is None:
            raise PreplanningStoreError("unresolved_reference_integrity_not_bootstrapped")
        try:
            canonical_hex = record.content["canonical_hex"]
            if not isinstance(canonical_hex, str):
                raise TypeError
            snapshot = ReferenceEdgeLedgerSnapshot.model_validate(
                decode_typed_value(bytes.fromhex(canonical_hex))
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("reference integrity authority is corrupt") from exc
        if record.content.get("ledger_digest") != snapshot.ledger_digest:
            raise PreplanningStoreError("reference integrity authority digest differs")
        try:
            validate_reference_integrity_converse(snapshot, self.semantic_replay_state())
        except ValueError as exc:
            raise PreplanningStoreError("reference integrity authority is incomplete") from exc
        return snapshot

    def bootstrap_reference_integrity(
        self,
        *,
        writer_binding: SemanticWriterCommitBinding,
    ):
        """Activate reference completeness after one canonical replay-state audit."""

        from memorii.core.memory_evolution.reference_integrity import (
            bootstrap_reference_integrity,
        )

        self._writers.require_current(writer_binding)
        authorization = self._writers._authorize_atomic(
            writer_binding, capability=self._write_capability
        )
        for attempt in range(2):
            if self._memory_plane.get_record(_reference_integrity_ledger_id()) is not None:
                return self.reference_integrity_snapshot()
            replay_state_record = self._memory_plane.get_record(_semantic_replay_state_id())
            replay_state = self.semantic_replay_state()
            now = self._now()
            snapshot = bootstrap_reference_integrity(
                replay_state, completed_at=now
            )
            record = _reference_integrity_ledger_record(snapshot, now)
            replay_precondition: MemoryPlanePrecondition = (
                RecordAbsentPrecondition(memory_id=_semantic_replay_state_id())
                if replay_state_record is None
                else RecordDigestPrecondition(
                    memory_id=replay_state_record.memory_id,
                    expected_digest=record_digest(replay_state_record),
                )
            )
            try:
                self._memory_plane.conditionally_write_records(
                    (record,),
                    preconditions=(
                        RecordAbsentPrecondition(memory_id=record.memory_id),
                        replay_precondition,
                    ),
                    authorization=authorization,
                )
            except MemoryPlaneRevisionConflictError as exc:
                if attempt == 1:
                    raise PreplanningStoreError(
                        "reference integrity bootstrap contention"
                    ) from exc
                continue
            return snapshot
        raise AssertionError("unreachable reference integrity bootstrap retry")

    def _verify_frozen_identity_authority(self, value) -> None:
        from memorii.core.memory_evolution.graph_records import (
            TrustedAcceptedIdentityOperationDecision,
            VerifiedIdentityDecisionAuthority,
        )

        verify_authority = getattr(
            self._identity_decision_authority_verifier,
            "verify_identity_decision_authority",
            None,
        )
        if not callable(verify_authority):
            raise PreplanningStoreError(
                "identity planning decision authority is unverified"
            )
        try:
            decision = TrustedAcceptedIdentityOperationDecision.model_validate(
                value.trusted_decision
            )
            verification = VerifiedIdentityDecisionAuthority.model_validate(
                value.authority_verification
            )
            reverified = VerifiedIdentityDecisionAuthority.model_validate(
                verify_authority(decision)
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreplanningStoreError(
                "identity planning decision authority is unverified"
            ) from exc
        if (
            decision != value.trusted_decision
            or verification != value.authority_verification
            or reverified != verification
        ):
            raise PreplanningStoreError(
                "identity planning decision authority binding mismatch"
            )

    def publish_accepted_identity_operation(
        self,
        artifact,
        *,
        writer_binding: SemanticWriterCommitBinding,
    ):
        """Publish immutable accepted identity IR under the atomic-store owner."""

        from memorii.core.memory_evolution.graph_planning import (
            FrozenIdentityGraphPlanningArtifact,
        )
        raw = artifact.model_dump(mode="python")
        try:
            value = FrozenIdentityGraphPlanningArtifact.model_validate(raw)
        except ValueError as exc:
            from memorii.core.memory_evolution.graph_records import (
                AcceptedIdentityOperationArtifact,
            )

            AcceptedIdentityOperationArtifact.model_validate(raw)
            raise IdentityPlanningMigrationRequiredError(
                "accepted-only identity artifact requires explicit migration"
            ) from exc
        accepted = value.accepted_operation_artifact
        self._verify_frozen_identity_authority(value)
        self._writers.require_current(writer_binding)
        record = _accepted_identity_operation_record(value, self._now())
        existing = self._memory_plane.get_record(record.memory_id)
        if existing is not None:
            current = self.get_identity_graph_planning_artifact(
                operation_id=accepted.operation.operation_id,
                sealed_operation_digest=accepted.sealed_operation_digest,
                candidate_digest=accepted.candidate_digest,
                source_analysis_digest=accepted.source_analysis_digest,
            )
            if current != value:
                raise PreplanningStoreError("accepted identity operation artifact collision")
            return current
        self._semantic_freeze_guard(value.planning_delta)  # type: ignore[arg-type]
        authorization = self._writers._authorize_atomic(
            writer_binding, capability=self._write_capability
        )
        reservation_records = tuple(
            sorted(
                (
                    _graph_identity_reservation_record(
                        record_key=intent.record_key,
                        reservation_digest=reservation.reservation_digest,
                        operation_id=accepted.operation.operation_id,
                        operation_fence_id=accepted.operation_fence_id,
                        timestamp=record.timestamp,
                    )
                    for reservation in accepted.successor_reservations
                    for intent in reservation.expected_absent_write_intents
                ),
                key=lambda item: item.memory_id,
            )
        )
        if len({item.memory_id for item in reservation_records}) != len(
            reservation_records
        ):
            raise PreplanningStoreError(
                "identity planning reservation coordinates collide"
            )
        replay_record = self._memory_plane.get_record(_semantic_replay_state_id())
        ledger_record = self._memory_plane.get_record(_reference_integrity_ledger_id())
        replay_state = self.semantic_replay_state()
        reference_ledger = self.reference_integrity_snapshot()
        if (
            replay_state.state_digest != value.graph_replay_state_digest
            or reference_ledger.ledger_digest != value.reference_ledger_digest
            or ledger_record is None
        ):
            raise IdentityPlanningStaleSnapshotError(
                "identity planning graph snapshot changed before publication"
            )
        graph_preconditions = (
            RecordAbsentPrecondition(memory_id=_semantic_replay_state_id())
            if replay_record is None
            else RecordDigestPrecondition(
                memory_id=replay_record.memory_id,
                expected_digest=record_digest(replay_record),
            ),
            RecordDigestPrecondition(
                memory_id=ledger_record.memory_id,
                expected_digest=record_digest(ledger_record),
            ),
            *(
                (
                    RecordAbsentPrecondition(
                        memory_id=_semantic_integrity_control_id()
                    ),
                )
                if self._uses_default_semantic_freeze_guard
                else ()
            ),
        )

        def planning_publication_barrier() -> None:
            if not self._uses_default_semantic_freeze_guard:
                self._semantic_freeze_guard(
                    value.planning_delta  # type: ignore[arg-type]
                )

        try:
            self._memory_plane.conditionally_write_records(
                (record, *reservation_records),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=record.memory_id),
                    *(
                        RecordAbsentPrecondition(memory_id=item.memory_id)
                        for item in reservation_records
                    ),
                    *graph_preconditions,
                ),
                authorization=authorization,
                transaction_precondition=planning_publication_barrier,
            )
        except MemoryPlaneRevisionConflictError:
            if self._memory_plane.get_record(record.memory_id) is None:
                raise IdentityPlanningStaleSnapshotError(
                    "identity planning graph snapshot changed during publication"
                ) from None
            current = self.get_identity_graph_planning_artifact(
                operation_id=accepted.operation.operation_id,
                sealed_operation_digest=accepted.sealed_operation_digest,
                candidate_digest=accepted.candidate_digest,
                source_analysis_digest=accepted.source_analysis_digest,
            )
            if current != value:
                raise
        return value

    def get_accepted_identity_operation(
        self,
        *,
        operation_id: str,
        sealed_operation_digest: str | None,
        candidate_digest: str | None,
        source_analysis_digest: str | None,
    ):
        from memorii.core.memory_evolution.graph_planning import (
            FrozenIdentityGraphPlanningArtifact,
        )
        record = self._memory_plane.get_record(_accepted_identity_operation_id(operation_id))
        if record is None:
            return None
        try:
            raw = decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"])))
            try:
                planned = FrozenIdentityGraphPlanningArtifact.model_validate(raw)
            except ValueError as exc:
                from memorii.core.memory_evolution.graph_records import (
                    AcceptedIdentityOperationArtifact,
                )

                AcceptedIdentityOperationArtifact.model_validate(raw)
                raise IdentityPlanningMigrationRequiredError(
                    "accepted-only identity artifact requires explicit migration"
                ) from exc
            value = planned.accepted_operation_artifact
            persisted_digest = planned.artifact_digest
        except IdentityPlanningMigrationRequiredError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("accepted identity operation artifact is corrupt") from exc
        if (
            value.operation.operation_id != operation_id
            or value.sealed_operation_digest != sealed_operation_digest
            or value.candidate_digest != candidate_digest
            or value.source_analysis_digest != source_analysis_digest
            or record.content.get("operation_id") != operation_id
            or record.content.get("artifact_digest") != persisted_digest
        ):
            raise PreplanningStoreError("accepted identity operation artifact binding mismatch")
        self._verify_frozen_identity_authority(planned)
        return value

    def get_identity_graph_planning_artifact(
        self,
        *,
        operation_id: str,
        sealed_operation_digest: str | None,
        candidate_digest: str | None,
        source_analysis_digest: str | None,
    ):
        from memorii.core.memory_evolution.graph_planning import (
            FrozenIdentityGraphPlanningArtifact,
        )

        record = self._memory_plane.get_record(
            _accepted_identity_operation_id(operation_id)
        )
        if record is None:
            return None
        try:
            raw = decode_typed_value(
                bytes.fromhex(str(record.content["canonical_hex"]))
            )
            try:
                value = FrozenIdentityGraphPlanningArtifact.model_validate(raw)
            except ValueError as exc:
                from memorii.core.memory_evolution.graph_records import (
                    AcceptedIdentityOperationArtifact,
                )

                AcceptedIdentityOperationArtifact.model_validate(raw)
                raise IdentityPlanningMigrationRequiredError(
                    "accepted-only identity artifact requires explicit migration"
                ) from exc
        except IdentityPlanningMigrationRequiredError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError(
                "frozen identity graph planning artifact is absent or corrupt"
            ) from exc
        accepted = value.accepted_operation_artifact
        if (
            accepted.operation.operation_id != operation_id
            or accepted.sealed_operation_digest != sealed_operation_digest
            or accepted.candidate_digest != candidate_digest
            or accepted.source_analysis_digest != source_analysis_digest
            or record.content.get("operation_id") != operation_id
            or record.content.get("artifact_digest") != value.artifact_digest
        ):
            raise PreplanningStoreError(
                "frozen identity graph planning artifact binding mismatch"
            )
        self._verify_frozen_identity_authority(value)
        return value

    def enrich_identity_graph_delta(
        self,
        graph_delta,
        terminal,
        *,
        operation_fence_id: str,
        graph_revision_before: str | None = None,
        graph_revision_after: str | None = None,
        committed_at: datetime | None = None,
    ):
        """Bind commit-owned coordinates and attach frozen identity outputs."""

        from memorii.core.memory_evolution.graph_planning import (
            PlanningCommitValues,
            materialize_frozen_identity_graph_plan,
        )
        from memorii.core.memory_evolution.time_contracts import TimeInterval
        from memorii.core.semantic_ingestion.contracts import (
            IdentityLineageRecord,
            SemanticGraphDelta,
            TemporalTransitionRecord,
            contract_digest,
        )

        committed_at = committed_at or self.authoritative_commit_timestamp()
        graph_revision_before = (
            graph_revision_before or self.semantic_replay_state().graph_revision
        )
        graph_revision_after = graph_revision_after or graph_revision_before
        candidate_by_id = {item.candidate_id: item for item in terminal.candidates}
        analysis_by_id = {item.candidate_id: item for item in terminal.source_analyses}
        records = list(graph_delta.graph_records)
        materialized_identity: dict[str, tuple[object, ...]] = {}
        for sealed in terminal.sealed_operations:
            if sealed.kind != "identity":
                continue
            planned_artifact = self.get_identity_graph_planning_artifact(
                operation_id=sealed.operation_id,
                sealed_operation_digest=sealed.sealed_operation_digest,
                candidate_digest=candidate_by_id[sealed.candidate_id].candidate_digest,
                source_analysis_digest=analysis_by_id[sealed.candidate_id].analysis_digest,
            )
            if planned_artifact is None:
                raise PreplanningStoreError("frozen identity planning artifact is absent")
            artifact = planned_artifact.accepted_operation_artifact
            if artifact.operation_fence_id != operation_fence_id:
                raise PreplanningStoreError("accepted identity operation fence mismatch")
            output_records, _ = materialize_frozen_identity_graph_plan(
                planned_artifact,
                commit_values=PlanningCommitValues(
                    transaction_group_id=graph_delta.operation_id,
                    graph_revision_before=graph_revision_before,
                    graph_revision_after=graph_revision_after,
                    committed_at=committed_at,
                ),
            )
            materialized_identity[sealed.operation_id] = tuple(
                item.payload for item in output_records
            )
            records.extend(
                item.payload
                for item in output_records
                if item.payload_record_kind != "identity_lineage"
            )
        carriers = []
        for carrier in graph_delta.carriers:
            if isinstance(carrier, IdentityLineageRecord):
                outputs = materialized_identity.get(carrier.operation_id, ())
                materialized = next(
                    (
                        item
                        for item in outputs
                        if isinstance(item, IdentityLineageRecord)
                    ),
                    None,
                )
                if materialized is None:
                    raise PreplanningStoreError(
                        "identity planning materialization is incomplete"
                    )
                carriers.append(materialized)
            elif isinstance(carrier, TemporalTransitionRecord):
                values = carrier.model_dump(
                    mode="python", exclude={"record_digest"}
                )
                values["system_interval"] = TimeInterval(start=committed_at)
                carriers.append(
                    TemporalTransitionRecord.model_validate(
                        values
                        | {
                            "record_digest": contract_digest(
                                b"memorii.semantic-ingestion.temporal-carrier.v1",
                                values,
                            )
                        }
                    )
                )
            else:
                carriers.append(carrier)
        updated_delta = graph_delta.model_copy(update={"carriers": tuple(
            sorted(
                carriers,
                key=lambda item: (
                    item.operation_id,
                    item.record_kind,
                    item.record_digest,
                ),
            )
        )})
        if records:
            updated_delta = updated_delta.model_copy(
                update={"graph_records": tuple(sorted(records, key=lambda item: (item.record_kind, item.record_digest)))}
            )
        body = updated_delta.model_dump(mode="python", exclude={"delta_digest"})
        return SemanticGraphDelta.model_validate(
            body
            | {
                "delta_digest": contract_digest(
                    b"memorii.semantic-ingestion.graph-delta.v1", body
                )
            }
        )

    def prepare_semantic_event_batch(
        self,
        *,
        graph_delta: SemanticGraphDelta,
        operation_fence: OperationFenceBinding,
        writer_binding: SemanticWriterCommitBinding,
        graph_revision_before: str,
        graph_revision_after: str,
        committed_at: datetime | None = None,
    ) -> SemanticMemoryEventBatch:
        from memorii.core.semantic_ingestion.event_replay import build_semantic_memory_event_batch

        if self._semantic_freeze_guard is not None:
            self._semantic_freeze_guard(graph_delta)
        self._writers.require_current(writer_binding)
        return build_semantic_memory_event_batch(
            graph_delta=graph_delta,
            prior_state=self.semantic_replay_state(),
            repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
            source_id=operation_fence.source_id,
            transaction_group_id=graph_delta.operation_id,
            operation_fence_id=operation_fence.operation_fence_id,
            writer_epoch=writer_binding.expected_writer_epoch,
            graph_revision_before=graph_revision_before,
            graph_revision_after=graph_revision_after,
            timestamp=committed_at or self.authoritative_commit_timestamp(),
            registry=self._event_schema_registry,
        )

    def preflight_terminal_conflict_authority(
        self,
        *,
        operation_fence: OperationFenceBinding,
        terminal: SemanticTerminalOutcome,
        writer_binding: SemanticWriterCommitBinding,
    ) -> SemanticConflictAuthorityCommitInput:
        """Read and validate a terminal's conflict closure without mutating the plane.

        This deliberately mirrors the terminal event path far enough to derive
        the exact contender set.  The final generation write repeats this work
        under its record/pointer CAS preconditions; this preflight only keeps
        invalid host authority from creating a lease or checkpoint first.
        """
        from memorii.core.memory_evolution.projection_history import (
            ProjectionCommitRequest,
            ProjectionHistoryError,
            projection_records_from_replay_state,
        )
        from memorii.core.semantic_ingestion.contracts import SemanticGraphDelta
        from memorii.core.semantic_ingestion.event_replay import replay_semantic_event_batches

        control = self.get_operation(operation_fence)
        if control.state == "terminal" or terminal.status != "accepted":
            return SemanticConflictAuthorityCommitInput.empty()
        self._writers.require_current(writer_binding)
        committed_at = self.authoritative_commit_timestamp()
        unmaterialized = SemanticGraphDelta.create(terminal)
        provisional = self.enrich_identity_graph_delta(
            unmaterialized,
            terminal,
            operation_fence_id=operation_fence.operation_fence_id,
            graph_revision_before=control.graph_revision,
            graph_revision_after=control.graph_revision,
            committed_at=committed_at,
        )
        graph_revision_after = sha256(
            b"memorii.semantic-ingestion.graph-revision.v1\0"
            + control.graph_revision.encode()
            + b"\0"
            + provisional.delta_digest.encode()
        ).hexdigest()
        graph_delta = self.enrich_identity_graph_delta(
            unmaterialized,
            terminal,
            operation_fence_id=operation_fence.operation_fence_id,
            graph_revision_before=control.graph_revision,
            graph_revision_after=graph_revision_after,
            committed_at=committed_at,
        )
        batch = self.prepare_semantic_event_batch(
            graph_delta=graph_delta,
            operation_fence=operation_fence,
            writer_binding=writer_binding,
            graph_revision_before=control.graph_revision,
            graph_revision_after=graph_revision_after,
            committed_at=committed_at,
        )
        try:
            prior_state = self.semantic_replay_state()
            next_state = replay_semantic_event_batches(
                repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                batches=(batch,),
                registry_history=self._event_schema_registry_history,
                initial_state=prior_state,
            )
            bindings = self._projection_history.replay_bindings()
            (
                temporal_projections,
                trust_projections,
                temporal_policy_fingerprint,
                trust_policy_fingerprint,
                arbitration_as_of,
            ) = projection_records_from_replay_state(
                next_state,
                active_temporal=(self._projection_history.active_temporal_authority() if bindings else None),
                active_trust=(self._projection_history.active_trust_authority() if bindings else None),
                active_temporal_policy=(terminal.arbitration_policy_bundle.temporal_policy if bindings and terminal.arbitration_policy_bundle is not None else None),
                active_trust_policy=(terminal.arbitration_policy_bundle.trust_policy if bindings and terminal.arbitration_policy_bundle is not None else None),
            )
            authority = self._projection_history.resolve_semantic_conflict_authority(
                temporal_projections=temporal_projections,
                trust_projections=trust_projections,
            )
            authorization = self._writers._authorize_atomic(
                writer_binding, capability=self._write_capability
            )
            # `prepare` is read-only and validates record, pointer, resolver,
            # provenance, scope, and display closure as one prospective CAS.
            self._projection_history.prepare(
                ProjectionCommitRequest(
                    repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                    operation_id=batch.transaction_group_id,
                    graph_revision=next_state.graph_revision,
                    event_batch_sequence=batch.log_position.sequence,
                    event_batch_digest=batch.source_event_batch_digest,
                    complete_read_set_digest=control.effective_read_set_digest,
                    writer_epoch=writer_binding.expected_writer_epoch,
                    base_snapshot_token=prior_state.state_digest,
                    temporal_policy_fingerprint=temporal_policy_fingerprint,
                    trust_policy_fingerprint=trust_policy_fingerprint,
                    arbitration_as_of=arbitration_as_of,
                    temporal_projections=temporal_projections,
                    trust_projections=trust_projections,
                    semantic_conflict_authority=authority,
                ),
                capability=self._write_capability,
                authorization=authorization,
            )
            return authority
        except (ProjectionHistoryError, ValueError) as exc:
            raise PreplanningStoreError("terminal semantic conflict authority preflight failed") from exc

    def checkpoint_source_progress(
        self, request: SourceCheckpointAtomicWriteRequest | AtomicGenerationRequest
    ) -> tuple[AtomicGenerationMember, ...]:
        recovered = self._recover_exact_generation_if_current(request)
        if recovered is not None:
            return recovered
        control = self._require_current_generation_authority(request)
        # Bootstrap V3's generation-three closure has a sealed recovery
        # control/progress snapshot.  It must not grow a second generic
        # progress member merely to satisfy the older checkpoint grammar.
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapSourceNormalizationAtomicWriteRequestV3,
        )
        if isinstance(request, BootstrapSourceNormalizationAtomicWriteRequestV3):
            return self._publish_generation(
                request,
                next_state="preplanning",
                allowed_kinds={member.kind for member in request.members},
                clear_lease=True,
            )
        counts = _member_kind_counts(request.members)
        if request.progress_state == "planned" and control.state == "planned" and counts.get("plan") == 1:
            planned_generations_list: list[tuple[AtomicGenerationMember, ...]] = []
            for generation in range(2, control.generation + 1):
                members = self._read_generation_members(control, generation)
                if any(member.kind == "plan" for member in members):
                    planned_generations_list.append(members)
            planned_generations = tuple(planned_generations_list)
            if len(planned_generations) != 1:
                raise PreplanningStoreError("planned source has no unique planning generation")
            if planned_generations[0] != request.members:
                raise PreplanningStoreError("planned source closure differs from checkpoint retry")
            return planned_generations[0]
        if request.progress_state != "planned" and (
            counts.get("terminal_artifact", 0)
            or counts.get("artifact_closure", 0)
        ):
            raise PreplanningStoreError(
                "terminal artifacts are legal only in the canonical planned checkpoint"
            )
        if counts.get("terminal_artifact", 0) and control.state != "preplanning":
            raise PreplanningStoreError(
                "source already has its canonical planned terminal checkpoint"
            )
        if counts.get("progress") != 1:
            raise PreplanningStoreError("checkpoint requires exactly one progress record")
        if request.progress_state == "preplanning" and counts.get("retry_outcome", 0):
            raise PreplanningStoreError("preplanning checkpoint cannot contain retry outcomes")
        planned_closure = {
            "plan",
            "planning_artifact",
            "independence_certificate",
            "planning_authorization",
            "artifact_index",
            "artifact_closure",
        }
        if (
            request.progress_state == "planned"
            and control.state == "preplanning"
            and any(counts.get(kind) != 1 for kind in planned_closure)
        ):
            raise PreplanningStoreError("planned checkpoint closure is incomplete")
        allowed = {
            "progress",
            "retry_outcome",
            "replay_artifact",
            "artifact_index",
            "artifact_closure",
            "plan",
            "planning_artifact",
            "independence_certificate",
            "planning_authorization",
            "authorization_read_set",
            "terminal_artifact",
            "lifecycle",
            "execution_plan",
            "recovery_authority_binding",
            "stage_artifact",
            # Source normalization is a complete graph-free authority.  Its
            # specialized request validates the exact category closure before
            # this generic transaction owner sees the generation.
            "source_normalization_request",
            "graph_free_interpretation_bundle",
            "source_local_identity_partition_evidence",
            "parser_consensus",
            "semantic_scope_consensus",
            "temporal_attachment_consensus",
            "source_local_identity_resolution",
            "source_proposal_alignment",
            "source_dependency_groups",
            "source_normalization_result",
            "source_normalization_evidence_manifest",
            "graph_dependent_execution_policy",
            "consensus_policy_selection_bundle",
            "language_construction_policy_bundle",
            # Bootstrap V3 is a standalone wire schema.  These members are
            # intentionally not admitted through the generic V2 categories.
            "bootstrap_proposal_run_payload",
            "bootstrap_analysis_lane_result",
            "bootstrap_pre_alignment_operation_subject_set",
            "bootstrap_analyzer_scope_observation",
            "bootstrap_analyzer_temporal_attachment_observation",
            "bootstrap_parser_consensus_assessment",
            "bootstrap_semantic_scope_consensus",
            "bootstrap_temporal_attachment_consensus",
            "bootstrap_operation_temporal_attachment_consensus_set",
            "bootstrap_source_local_identity_partition_evidence",
            "bootstrap_source_local_identity_resolution",
            "bootstrap_proposal_coverage_audit",
            "bootstrap_operation_alignment",
            "bootstrap_source_dependency_group",
            "bootstrap_graph_free_interpretation_bundle",
            "bootstrap_source_proposal_alignment",
            "bootstrap_source_normalization_request",
            "bootstrap_source_normalization_evidence_manifest",
            "bootstrap_source_normalization_result",
            "bootstrap_normalization_request_core",
            "bootstrap_semantic_reduction_authority",
            "bootstrap_graph_normalization_authority",
        }
        progress_state = getattr(request, "progress_state", None)
        source_normalization_members = {
            "source_normalization_request",
            "source_normalization_result",
            "source_normalization_evidence_manifest",
            "bootstrap_proposal_run_payload",
            "bootstrap_analysis_lane_result",
            "bootstrap_graph_free_interpretation_bundle",
            "bootstrap_source_proposal_alignment",
        }
        # A source-normalization generation itself is graph-free preplanning.
        # Its later terminal checkpoint is a distinct generic transaction and
        # must be allowed to advance that same operation to planned.
        if counts.keys() & source_normalization_members and progress_state != "preplanning":
            raise PreplanningStoreError("source normalization checkpoint progress is invalid")
        return self._publish_generation(request, next_state=progress_state, allowed_kinds=allowed)

    def transition_or_find_bootstrap_graph_control_epoch_v3(self, *, request: object) -> object:
        """Append one immutable V3 control epoch or recover its exact prior write."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphControlEpochAdvancedV3,
            BootstrapGraphControlEpochFoundV3,
            BootstrapGraphControlEpochTransitionRequestV3,
        )

        if not isinstance(request, BootstrapGraphControlEpochTransitionRequestV3):
            raise PreplanningStoreError("bootstrap graph epoch transition has an invalid type")
        request = BootstrapGraphControlEpochTransitionRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        linearization = self._semantic_integrity_linearization
        if linearization is None:
            return self._transition_or_find_bootstrap_graph_control_epoch_v3_linearized(
                request=request,
                found_type=BootstrapGraphControlEpochFoundV3,
                advanced_type=BootstrapGraphControlEpochAdvancedV3,
            )
        with linearization.exclusive():
            return self._transition_or_find_bootstrap_graph_control_epoch_v3_linearized(
                request=request,
                found_type=BootstrapGraphControlEpochFoundV3,
                advanced_type=BootstrapGraphControlEpochAdvancedV3,
            )

    def load_bootstrap_graph_control_epoch_v3(
        self, *, request_core_digest: str
    ) -> object | None:
        """Return the current control epoch for a request core if one is present."""
        if not request_core_digest:
            return None

        head = self._memory_plane.get_record(
            _bootstrap_graph_v3_epoch_head_id(request_core_digest)
        )
        if head is None:
            return None
        if (
            head.source_kind != "semantic_ingestion_bootstrap_graph_v3_epoch_head"
            or head.content.get("semantic_ingestion_kind")
            != "bootstrap_graph_v3_epoch_head"
            or head.content.get("request_core_digest") != request_core_digest
        ):
            return None

        epoch_id = _bootstrap_graph_v3_epoch_id(
            request_core_digest,
            int(head.content.get("epoch", -1)),
        )
        epoch_record = self._memory_plane.get_record(epoch_id)
        if epoch_record is None:
            return None
        try:
            return _bootstrap_graph_v3_epoch_from_record(epoch_record)
        except (TypeError, ValueError, KeyError):
            return None

    def _transition_or_find_bootstrap_graph_control_epoch_v3_linearized(
        self, *, request: object, found_type: type, advanced_type: type
    ) -> object:
        from memorii.core.semantic_ingestion.contracts import BootstrapGraphControlEpochV3

        transition_record = self._memory_plane.get_record(
            _bootstrap_graph_v3_transition_id(request.transition_digest)
        )
        if transition_record is not None:
            epoch = _bootstrap_graph_v3_epoch_from_transition_record(transition_record)
            return found_type.create(kind="found", epoch=epoch)
        try:
            current_writer = self._writers.commit_binding(self._writers.current())
            if current_writer != request.writer_commit:
                return _bootstrap_graph_v3_epoch_unavailable(request, "writer_changed")
            self._writers.require_current(request.writer_commit)
            control_record = self._required_control_record(request.operation_fence)
            control = _control_from_record(control_record)
            if (
                control.operation_fence != request.operation_fence
                or control.writer_binding != request.writer_commit
                or control.lease is None
                or self.lease_binding(control) != request.operation_lease
                or request.operation_lease.lease_expires_at <= self._now()
            ):
                return _bootstrap_graph_v3_epoch_unavailable(request, "lease_unavailable")
            authority = request.graph_authority
            if (
                authority.operation_fence_binding != request.operation_fence
                or (
                    request.expected_epoch_digest is None
                    and authority.operation_lease_binding != request.operation_lease
                )
                or authority.writer_commit_binding != request.writer_commit
                or authority.required_scope_set_digest
                != request.required_outcome_scopes.required_scope_set_digest
                or authority.delivery_principal_binding_digest
                != request.delivery_principal_binding_digest
            ):
                return _bootstrap_graph_v3_epoch_unavailable(request, "ingress_unavailable")
            head_record = self._memory_plane.get_record(
                _bootstrap_graph_v3_epoch_head_id(request.request_core_digest)
            )
            if request.expected_epoch_digest is None:
                if request.transition != "initial" or head_record is not None:
                    return _bootstrap_graph_v3_epoch_unavailable(request, "stale_epoch")
                epoch_number = 0
                predecessor = None
            else:
                if head_record is None or head_record.content.get("epoch_digest") != request.expected_epoch_digest:
                    return _bootstrap_graph_v3_epoch_unavailable(request, "stale_epoch")
                prior = self._memory_plane.get_record(
                    _bootstrap_graph_v3_epoch_id(
                        request.request_core_digest, int(head_record.content.get("epoch", -1))
                    )
                )
                if prior is None:
                    return _bootstrap_graph_v3_epoch_unavailable(request, "stale_epoch")
                prior_epoch = _bootstrap_graph_v3_epoch_from_record(prior)
                prior_lease = prior_epoch.operation_lease_binding
                next_lease = request.operation_lease
                same_lease_owner = (
                    next_lease.owner_id == prior_lease.owner_id
                    and next_lease.execution_token == prior_lease.execution_token
                    and next_lease.ownership_epoch == prior_lease.ownership_epoch
                )
                if request.transition == "initial":
                    return _bootstrap_graph_v3_epoch_unavailable(
                        request, "invalid_transition"
                    )
                if request.transition == "lease_renewed" and (
                    not same_lease_owner
                    or next_lease.state_revision <= prior_lease.state_revision
                    or next_lease.lease_expires_at <= prior_lease.lease_expires_at
                ):
                    return _bootstrap_graph_v3_epoch_unavailable(
                        request, "invalid_transition"
                    )
                if request.transition == "lease_reclaimed" and (
                    same_lease_owner
                    or next_lease.ownership_epoch != prior_lease.ownership_epoch + 1
                    or prior_lease.lease_expires_at > self._now()
                ):
                    return _bootstrap_graph_v3_epoch_unavailable(
                        request, "invalid_transition"
                    )
                epoch_number = prior_epoch.epoch + 1
                predecessor = prior_epoch.epoch_digest
            epoch = BootstrapGraphControlEpochV3.create(
                request_core_digest=request.request_core_digest,
                normalization_replay_digest=request.normalization_replay.replay_digest,
                source_id=request.graph_authority.source_id,
                source_digest=request.graph_authority.source_digest,
                preparation_fingerprint=request.graph_authority.preparation_fingerprint,
                epoch=epoch_number,
                predecessor_epoch_digest=predecessor,
                transition=request.transition,
                delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                required_scope_set_digest=(
                    request.required_outcome_scopes.required_scope_set_digest
                ),
                operation_fence_binding=request.operation_fence,
                operation_lease_binding=request.operation_lease,
                writer_commit_binding=request.writer_commit,
                issued_server_time=self._now(),
                issued_monotonic_tick=epoch_number,
            )
            timestamp = self._now()
            epoch_record = _bootstrap_graph_v3_epoch_record(epoch=epoch, timestamp=timestamp)
            head = _bootstrap_graph_v3_epoch_head_record(epoch=epoch, timestamp=timestamp)
            index = _bootstrap_graph_v3_transition_record(
                transition=request, epoch=epoch, timestamp=timestamp
            )
            writer_record = self._writers.require_current(request.writer_commit)
            authorization = self._writers._authorize_atomic(
                request.writer_commit,
                capability=self._write_capability,
                lease_expires_at=request.operation_lease.lease_expires_at,
                server_now=self._now,
            )
            head_precondition = (
                RecordAbsentPrecondition(memory_id=head.memory_id)
                if head_record is None
                else RecordDigestPrecondition(memory_id=head_record.memory_id, expected_digest=record_digest(head_record))
            )
            self._memory_plane.conditionally_write_records(
                (epoch_record, head, index),
                preconditions=(
                    RecordDigestPrecondition(memory_id=control_record.memory_id, expected_digest=record_digest(control_record)),
                    RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                    RecordFencePrecondition(
                        memory_id=control_record.memory_id,
                        expected_fence=MemoryRecordFence(
                            execution_token=request.operation_lease.execution_token,
                            ownership_epoch=request.operation_lease.ownership_epoch,
                        ),
                    ),
                    head_precondition,
                    *(RecordAbsentPrecondition(memory_id=item.memory_id) for item in (epoch_record, index)),
                ),
                authorization=authorization,
            )
            return advanced_type.create(kind="advanced", epoch=epoch)
        except SemanticWriterAdmissionError:
            return _bootstrap_graph_v3_epoch_unavailable(request, "writer_unavailable")
        except MemoryPlaneRevisionConflictError:
            raced = self._memory_plane.get_record(
                _bootstrap_graph_v3_transition_id(request.transition_digest)
            )
            if raced is not None:
                return found_type.create(
                    kind="found", epoch=_bootstrap_graph_v3_epoch_from_transition_record(raced)
                )
            return _bootstrap_graph_v3_epoch_unavailable(request, "stale_epoch")

    def checkpoint_bootstrap_graph_transaction_v3(
        self,
        *,
        request: object,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
        control_epoch: object,
    ) -> object:
        """Publish and reload one sealed V3 graph checkpoint.

        Bootstrap graph artifacts intentionally have a separate persisted
        grammar.  They never enter the generic generation/member tables: the
        graph request's member digest, ordering, epoch, and recovery identity
        are all part of its own durable closure.
        """
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphCheckpointReceiptV3,
            BootstrapGraphCurrentGenerationV3,
            BootstrapGraphPlanAtomicReloadCoreV3,
            BootstrapGraphPlanAtomicReloadV3,
            BootstrapGraphPlanAtomicWriteRequestV3,
            validate_bootstrap_graph_plan_atomic_members_v3,
        )

        if not isinstance(request, BootstrapGraphPlanAtomicWriteRequestV3):
            raise PreplanningStoreError("bootstrap graph checkpoint has an invalid type")
        request = BootstrapGraphPlanAtomicWriteRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        try:
            validate_bootstrap_graph_plan_atomic_members_v3(request.members)
        except ValueError as exc:
            raise PreplanningStoreError("bootstrap graph checkpoint member is not native") from exc
        linearization = self._semantic_integrity_linearization
        if linearization is None:
            return self._checkpoint_bootstrap_graph_transaction_v3_linearized(
                request=request,
                delivery_principal_binding_digest=delivery_principal_binding_digest,
                required_outcome_scopes=required_outcome_scopes,
                control_epoch=control_epoch,
                current_generation_type=BootstrapGraphCurrentGenerationV3,
                reload_core_type=BootstrapGraphPlanAtomicReloadCoreV3,
                receipt_type=BootstrapGraphCheckpointReceiptV3,
                reload_type=BootstrapGraphPlanAtomicReloadV3,
            )
        with linearization.exclusive():
            return self._checkpoint_bootstrap_graph_transaction_v3_linearized(
                request=request,
                delivery_principal_binding_digest=delivery_principal_binding_digest,
                required_outcome_scopes=required_outcome_scopes,
                control_epoch=control_epoch,
                current_generation_type=BootstrapGraphCurrentGenerationV3,
                reload_core_type=BootstrapGraphPlanAtomicReloadCoreV3,
                receipt_type=BootstrapGraphCheckpointReceiptV3,
                reload_type=BootstrapGraphPlanAtomicReloadV3,
            )

    def load_bootstrap_graph_current_generation_v3(
        self, *, request: object, control_epoch: object, delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
    ) -> object:
        """Return the sealed predecessor snapshot; callers cannot supply scalars."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphControlEpochV3,
            BootstrapGraphCurrentGenerationV3,
        )
        if not isinstance(control_epoch, BootstrapGraphControlEpochV3):
            raise PreplanningStoreError("bootstrap graph control epoch is invalid")
        if (
            request.request_core_digest != control_epoch.request_core_digest
            or delivery_principal_binding_digest
            != control_epoch.delivery_principal_binding_digest
            or required_outcome_scopes.required_scope_set_digest
            != control_epoch.required_scope_set_digest
        ):
            raise PreplanningStoreError("bootstrap graph current generation authority is substituted")
        control = _control_from_record(self._required_control_record(control_epoch.operation_fence_binding))
        head = self._memory_plane.get_record(_bootstrap_graph_v3_epoch_head_id(control_epoch.request_core_digest))
        if head is None or head.content.get("epoch_digest") != control_epoch.epoch_digest:
            raise PreplanningStoreError("bootstrap graph control epoch is not current")
        return BootstrapGraphCurrentGenerationV3.create(
            store_identity_digest=sha256(_control_namespace(control).encode()).hexdigest(),
            operation_id=control.operation_fence.operation_id,
            request_digest=request.request_digest,
            operation_generation=control.generation, artifact_generation=control.generation,
            latest_atomic_write_digest=control.last_request_digest,
            control_epoch_digest=control_epoch.epoch_digest,
        )
    def _checkpoint_bootstrap_graph_transaction_v3_linearized(
        self,
        *,
        request: object,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
        control_epoch: object,
        current_generation_type: type,
        reload_core_type: type,
        receipt_type: type,
        reload_type: type,
    ) -> object:
        from memorii.core.semantic_ingestion.contracts import (
            validate_bootstrap_graph_plan_atomic_members_v3,
        )

        try:
            validate_bootstrap_graph_plan_atomic_members_v3(request.members)
        except ValueError as exc:
            raise PreplanningStoreError("bootstrap graph reload member is not native") from exc
        self._validate_bootstrap_graph_v3_current_authority(
            request=request,
            delivery_principal_binding_digest=delivery_principal_binding_digest,
            required_outcome_scopes=required_outcome_scopes,
            control_epoch=control_epoch,
        )
        control_record = self._required_control_record(request.operation_fence_binding)
        control = _control_from_record(control_record)
        existing = self._memory_plane.get_record(
            _bootstrap_graph_v3_idempotency_id(request.write_digest)
        )
        if existing is not None:
            return self._reload_bootstrap_graph_transaction_v3(
                request=request,
                delivery_principal_binding_digest=delivery_principal_binding_digest,
                required_outcome_scopes=required_outcome_scopes,
                control_epoch=control_epoch,
                current_generation_type=current_generation_type,
                reload_core_type=reload_core_type,
                receipt_type=receipt_type,
                reload_type=reload_type,
            )
        if (
            request.predecessor_generation.operation_generation != control.generation
            or request.predecessor_generation.artifact_generation != control.generation
            or request.predecessor_generation.operation_id != request.operation_fence_binding.operation_id
            or request.predecessor_generation.request_digest != request.request_digest
            or request.predecessor_generation.control_epoch_digest != control_epoch.epoch_digest
        ):
            raise PreplanningStoreError("bootstrap graph checkpoint generation is stale")
        if control.state in {"terminal", "lease_recovery_exhausted"}:
            raise PreplanningStoreError("bootstrap graph operation is terminal")
        next_terminal = request.kind == "bootstrap_graph_terminal_checkpoint"
        next_control = control.model_copy(
            update={
                "generation": control.generation + 1,
                "last_request_digest": request.write_digest,
                "state": "terminal" if next_terminal else control.state,
                "lease": None if next_terminal else control.lease,
                "last_completed_lease_binding_digest": (
                    request.operation_lease_binding.binding_digest
                    if next_terminal
                    else control.last_completed_lease_binding_digest
                ),
            }
        )
        timestamp = self._now()
        members = tuple(
            _bootstrap_graph_v3_member_record(
                namespace_id=_control_namespace(control), generation=control.generation + 1,
                member=member,
                timestamp=timestamp,
            )
            for member in request.members
        )
        manifest = _bootstrap_graph_v3_manifest_record(
            namespace_id=_control_namespace(control), request=request, timestamp=timestamp
        )
        index = _bootstrap_graph_v3_idempotency_record(
            namespace_id=_control_namespace(control), request=request, timestamp=timestamp
        )
        retry_index = (
            _bootstrap_graph_v3_retry_record(request=request, timestamp=timestamp)
            if request.kind == "bootstrap_graph_retry_checkpoint"
            else None
        )
        retry_recovery = (
            _bootstrap_graph_v3_retry_recovery_record(
                request=request,
                delivery_principal_binding_digest=delivery_principal_binding_digest,
                required_outcome_scopes=required_outcome_scopes,
                manifest_id=manifest.memory_id,
                timestamp=timestamp,
            )
            if request.kind == "bootstrap_graph_retry_checkpoint"
            else None
        )
        writer_record = self._writers.require_current(request.writer_commit_binding)
        authorization = self._writers._authorize_atomic(
            request.writer_commit_binding,
            capability=self._write_capability,
            lease_expires_at=request.operation_lease_binding.lease_expires_at,
            server_now=self._now,
        )
        try:
            written = (
                _control_record(next_control, control_record.timestamp),
                *members,
                manifest,
                index,
                *((retry_index,) if retry_index is not None else ()),
                *((retry_recovery,) if retry_recovery is not None else ()),
            )
            self._memory_plane.conditionally_write_records(
                written,
                preconditions=(
                    RecordDigestPrecondition(memory_id=control_record.memory_id, expected_digest=record_digest(control_record)),
                    RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                    RecordFencePrecondition(
                        memory_id=control_record.memory_id,
                        expected_fence=MemoryRecordFence(
                            execution_token=request.operation_lease_binding.execution_token,
                            ownership_epoch=request.operation_lease_binding.ownership_epoch,
                        ),
                    ),
                    *(RecordAbsentPrecondition(memory_id=item.memory_id) for item in (*members, manifest, index, *((retry_index,) if retry_index is not None else ()), *((retry_recovery,) if retry_recovery is not None else ()))),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            if self._memory_plane.get_record(_bootstrap_graph_v3_idempotency_id(request.write_digest)) is None:
                raise PreplanningStoreError("bootstrap graph checkpoint CAS conflicted") from exc
        return self._reload_bootstrap_graph_transaction_v3(
            request=request,
            delivery_principal_binding_digest=delivery_principal_binding_digest,
            required_outcome_scopes=required_outcome_scopes,
            control_epoch=control_epoch,
            current_generation_type=current_generation_type,
            reload_core_type=reload_core_type,
            receipt_type=receipt_type,
            reload_type=reload_type,
        )

    def reload_bootstrap_graph_transaction_v3(
        self,
        *,
        request: object,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
        control_epoch: object,
    ) -> object:
        """Re-read the exact persisted V3 checkpoint after current-authority checks."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphCheckpointReceiptV3,
            BootstrapGraphCurrentGenerationV3,
            BootstrapGraphPlanAtomicReloadCoreV3,
            BootstrapGraphPlanAtomicReloadV3,
            BootstrapGraphPlanAtomicWriteRequestV3,
        )

        if not isinstance(request, BootstrapGraphPlanAtomicWriteRequestV3):
            raise PreplanningStoreError("bootstrap graph reload has an invalid type")
        return self._reload_bootstrap_graph_transaction_v3(
            request=request,
            delivery_principal_binding_digest=delivery_principal_binding_digest,
            required_outcome_scopes=required_outcome_scopes,
            control_epoch=control_epoch,
            current_generation_type=BootstrapGraphCurrentGenerationV3,
            reload_core_type=BootstrapGraphPlanAtomicReloadCoreV3,
            receipt_type=BootstrapGraphCheckpointReceiptV3,
            reload_type=BootstrapGraphPlanAtomicReloadV3,
        )

    def reload_bootstrap_graph_retry_by_request_v3(
        self,
        *,
        request: object,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
        control_epoch: object,
    ) -> object | None:
        """Reload the exact durable retry checkpoint without scanning generations."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphPlanAtomicWriteRequestV3,
        )

        retry = self._memory_plane.get_record(
            _bootstrap_graph_v3_retry_id(request.request_digest)
        )
        if retry is None:
            return None
        if (
            retry.source_kind != "semantic_ingestion_bootstrap_graph_v3_retry_index"
            or retry.content.get("semantic_ingestion_kind")
            != "bootstrap_graph_v3_retry_index"
            or retry.content.get("request_digest") != request.request_digest
        ):
            raise PreplanningStoreError("bootstrap graph retry index is corrupt")
        write_digest = retry.content.get("write_digest")
        index = self._memory_plane.get_record(
            _bootstrap_graph_v3_idempotency_id(write_digest)
        )
        manifest_id = None if index is None else index.content.get("manifest_id")
        manifest = None if not isinstance(manifest_id, str) else self._memory_plane.get_record(manifest_id)
        if (
            index is None
            or index.source_kind != "semantic_ingestion_bootstrap_graph_v3_idempotency"
            or index.content.get("request_digest") != request.request_digest
            or index.content.get("request_write_digest") != write_digest
            or manifest is None
            or manifest.source_kind != "semantic_ingestion_bootstrap_graph_v3_manifest"
        ):
            raise PreplanningStoreError("bootstrap graph retry index is corrupt")
        try:
            retry_request = BootstrapGraphPlanAtomicWriteRequestV3.model_validate_json(
                json.dumps(manifest.content["request"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("bootstrap graph retry checkpoint is corrupt") from exc
        if retry_request.kind != "bootstrap_graph_retry_checkpoint":
            raise PreplanningStoreError("bootstrap graph retry checkpoint is substituted")
        return self.reload_bootstrap_graph_transaction_v3(
            request=retry_request,
            delivery_principal_binding_digest=delivery_principal_binding_digest,
            required_outcome_scopes=required_outcome_scopes,
            control_epoch=control_epoch,
        )

    def reload_bootstrap_graph_retry_by_recovery_v3(
        self, *, normalization_replay: object, delivery_principal_binding_digest: str,
        required_outcome_scopes: object, operation_fence_binding: object,
    ) -> object | None:
        """Recover sealed retry progress without requiring a live operation lease."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphRetryRecoveryLocatorV3,
        )

        record = self._memory_plane.get_record(
            _bootstrap_graph_v3_retry_recovery_id(
                operation_fence_binding.binding_digest
            )
        )
        if record is None:
            return None
        if (
            record.source_kind
            != "semantic_ingestion_bootstrap_graph_v3_retry_recovery_locator"
            or record.content.get("semantic_ingestion_kind")
            != "bootstrap_graph_v3_retry_recovery_locator"
        ):
            raise PreplanningStoreError("bootstrap graph retry recovery locator is corrupt")
        try:
            locator = BootstrapGraphRetryRecoveryLocatorV3.model_validate(
                record.content["locator"], strict=False
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError(
                "bootstrap graph retry recovery locator is corrupt"
            ) from exc
        if (
            locator.operation_fence_binding_digest
            != operation_fence_binding.binding_digest
            or locator.normalization_replay_digest != normalization_replay.replay_digest
            or locator.normalization_result_digest
            != normalization_replay.source_normalization_result.result_digest
            or locator.delivery_principal_binding_digest
            != delivery_principal_binding_digest
            or locator.required_scope_set_digest
            != required_outcome_scopes.required_scope_set_digest
        ):
            raise PreplanningStoreError("bootstrap graph retry recovery authority is substituted")
        manifest = self._memory_plane.get_record(locator.checkpoint_manifest_id)
        index = self._memory_plane.get_record(
            _bootstrap_graph_v3_idempotency_id(locator.checkpoint_write_digest)
        )
        retry_index = self._memory_plane.get_record(
            _bootstrap_graph_v3_retry_id(locator.request_digest)
        )
        if (
            manifest is None
            or manifest.source_kind != "semantic_ingestion_bootstrap_graph_v3_manifest"
            or index is None
            or index.source_kind != "semantic_ingestion_bootstrap_graph_v3_idempotency"
            or retry_index is None
            or retry_index.source_kind
            != "semantic_ingestion_bootstrap_graph_v3_retry_index"
            or retry_index.content.get("write_digest")
            != locator.checkpoint_write_digest
            or manifest.content.get("request")
            != locator.checkpoint_request.model_dump(mode="json")
        ):
            raise PreplanningStoreError("bootstrap graph retry recovery closure is corrupt")
        return locator.progress

    def reload_bootstrap_graph_terminal_v3(
        self,
        *,
        handoff: object,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
        control_epoch: object,
    ) -> object:
        """Found-only terminal recovery through the prepublication locator.

        This deliberately does not scan generations or infer a terminal write
        from ambient state.  An absent locator must be constructed by the V3
        coordinator from its retained typed carriers before this port can CAS.
        """
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphTerminalPersistenceHandoffV3,
            BootstrapGraphTerminalReloadV3,
        )

        if not isinstance(handoff, BootstrapGraphTerminalPersistenceHandoffV3):
            raise PreplanningStoreError("bootstrap graph terminal handoff has an invalid type")
        handoff = BootstrapGraphTerminalPersistenceHandoffV3.model_validate(
            handoff.model_dump(mode="python")
        )
        core = handoff.core
        intent = handoff.publication_intent
        if (
            core.operation_fence_binding.binding_digest
            != intent.operation_fence_binding_digest
            or core.operation_lease_binding.binding_digest
            != intent.operation_lease_binding_digest
            or core.writer_commit_binding.binding_digest
            != intent.writer_commit_binding_digest
            or core.control_epoch_digest != intent.control_epoch_digest
            or delivery_principal_binding_digest
            != intent.delivery_principal_binding_digest
            or required_outcome_scopes.required_scope_set_digest
            != intent.required_scope_set_digest
            or control_epoch.epoch_digest != intent.control_epoch_digest
            or control_epoch.operation_fence_binding != core.operation_fence_binding
        ):
            raise PreplanningStoreError("bootstrap graph terminal authority is substituted")
        index = self._memory_plane.get_record(
            _bootstrap_graph_v3_terminal_locator_id(intent.locator_digest)
        )
        if index is None:
            raise PreplanningStoreError("bootstrap graph terminal publication is absent")
        if (
            index.source_kind != "semantic_ingestion_bootstrap_graph_v3_terminal_locator"
            or index.content.get("locator_digest") != intent.locator_digest
            or index.content.get("handoff_digest") != handoff.handoff_digest
        ):
            raise PreplanningStoreError("bootstrap graph terminal locator is corrupt")
        try:
            reload = BootstrapGraphTerminalReloadV3.model_validate(index.content["reload"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("bootstrap graph terminal locator is corrupt") from exc
        control = reload.terminal_control
        identity = reload.final_write_identity
        if (
            reload.atomic_write_locator_digest != intent.locator_digest
            or reload.handoff_digest != handoff.handoff_digest
            or control.state != "terminal_published"
            or control.locator_digest != intent.locator_digest
            or control.completed_lease_binding_digest != core.operation_lease_binding.binding_digest
            or identity.locator_digest != intent.locator_digest
            or identity.terminal_control_digest != control.terminal_control_digest
            or identity.completed_lease_binding_digest != control.completed_lease_binding_digest
            or reload.delivery_principal_binding_digest != intent.delivery_principal_binding_digest
            or reload.required_scope_set_digest != intent.required_scope_set_digest
            or reload.operation_fence_binding_digest != intent.operation_fence_binding_digest
            or reload.operation_lease_binding_digest != control.completed_lease_binding_digest
            or reload.control_epoch_digest != intent.control_epoch_digest
        ):
            raise PreplanningStoreError("bootstrap graph terminal reload is substituted")
        return reload

    def persist_bootstrap_graph_terminal_v3(self, *, request: object) -> object:
        """Atomically publish the sealed terminal V3 closure or reload its locator.

        The locator is intentionally the only recovery coordinate.  In
        particular, this path never searches old generations for a plausible
        terminal result: an acknowledgement can be recovered only when it is
        bound to the same immutable publication intent.
        """
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphCanonicalSourceResultV3,
            BootstrapGraphCheckpointReceiptV3,
            BootstrapGraphCurrentGenerationV3,
            BootstrapGraphPlanAtomicMemberV3,
            BootstrapGraphPlanAtomicWriteIdentityV3,
            BootstrapGraphTerminalControlV3,
            BootstrapGraphTerminalPublicationRequestV3,
            BootstrapGraphTerminalReloadV3,
            BootstrapNativeGroupCommitTerminalConstructionV3,
            encode_semantic_contract,
        )

        if not isinstance(request, BootstrapGraphTerminalPublicationRequestV3):
            raise PreplanningStoreError("bootstrap graph terminal publication has an invalid type")
        request = BootstrapGraphTerminalPublicationRequestV3.model_validate(
            request.model_dump(mode="python")
        )
        linearization = self._semantic_integrity_linearization
        if linearization is None:
            return self._persist_bootstrap_graph_terminal_v3_linearized(
                request=request,
                member_type=BootstrapGraphPlanAtomicMemberV3,
                group_result_type=BootstrapNativeGroupCommitTerminalConstructionV3,
                canonical_result_type=BootstrapGraphCanonicalSourceResultV3,
                identity_type=BootstrapGraphPlanAtomicWriteIdentityV3,
                terminal_control_type=BootstrapGraphTerminalControlV3,
                current_generation_type=BootstrapGraphCurrentGenerationV3,
                receipt_type=BootstrapGraphCheckpointReceiptV3,
                reload_type=BootstrapGraphTerminalReloadV3,
                encoder=encode_semantic_contract,
            )
        with linearization.exclusive():
            return self._persist_bootstrap_graph_terminal_v3_linearized(
                request=request,
                member_type=BootstrapGraphPlanAtomicMemberV3,
                group_result_type=BootstrapNativeGroupCommitTerminalConstructionV3,
                canonical_result_type=BootstrapGraphCanonicalSourceResultV3,
                identity_type=BootstrapGraphPlanAtomicWriteIdentityV3,
                terminal_control_type=BootstrapGraphTerminalControlV3,
                current_generation_type=BootstrapGraphCurrentGenerationV3,
                receipt_type=BootstrapGraphCheckpointReceiptV3,
                reload_type=BootstrapGraphTerminalReloadV3,
                encoder=encode_semantic_contract,
            )

    def reload_bootstrap_graph_terminal_by_request_v3(self, *, request: object) -> object | None:
        """Reload an acknowledged terminal result by its authenticated request identity."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphTerminalReloadV3,
            rebuild_bootstrap_graph_effect_contracts,
        )

        rebuild_bootstrap_graph_effect_contracts()

        record = self._memory_plane.get_record(
            _bootstrap_graph_v3_terminal_request_id(request.request_digest)
        )
        if record is None:
            return None
        if record.source_kind != "semantic_ingestion_bootstrap_graph_v3_terminal_locator":
            raise PreplanningStoreError("bootstrap graph terminal request index is corrupt")
        try:
            reload = BootstrapGraphTerminalReloadV3.model_validate(
                record.content["reload"], strict=False
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("bootstrap graph terminal request index is corrupt") from exc
        if (
            record.content.get("coordinator_request_digest") != request.request_digest
            or record.content.get("locator_digest") != reload.atomic_write_locator_digest
            or reload.delivery_principal_binding_digest
            != request.delivery_principal_binding_digest
            or reload.required_scope_set_digest
            != request.required_outcome_scopes.required_scope_set_digest
            or reload.operation_fence_binding_digest
            != request.initial_control_epoch.operation_fence_binding.binding_digest
        ):
            raise PreplanningStoreError("bootstrap graph terminal request index is substituted")
        return self._reload_bootstrap_graph_terminal_exact_v3(
            locator_digest=reload.atomic_write_locator_digest,
            expected_reload=reload,
            expected_request_digest=request.request_digest,
            expected_normalization_replay_digest=request.normalization_replay.replay_digest,
            expected_delivery_principal_binding_digest=(
                request.delivery_principal_binding_digest
            ),
            expected_required_scope_set_digest=(
                request.required_outcome_scopes.required_scope_set_digest
            ),
            expected_operation_fence_binding=request.initial_control_epoch.operation_fence_binding,
        )

    def reload_bootstrap_graph_terminal_by_recovery_v3(
        self, *, normalization_replay: object, delivery_principal_binding_digest: str,
        required_outcome_scopes: object, operation_fence_binding: object,
    ) -> object | None:
        """Recover a terminal graph result from the exact normalization replay key."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphTerminalReloadV3,
            rebuild_bootstrap_graph_effect_contracts,
        )

        rebuild_bootstrap_graph_effect_contracts()

        record = self._memory_plane.get_record(
            _bootstrap_graph_v3_terminal_recovery_id(normalization_replay.recovery_key_digest)
        )
        if record is None:
            return None
        if record.source_kind != "semantic_ingestion_bootstrap_graph_v3_terminal_locator":
            raise PreplanningStoreError("bootstrap graph terminal recovery index is corrupt")
        try:
            reload = BootstrapGraphTerminalReloadV3.model_validate(
                record.content["reload"], strict=False
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("bootstrap graph terminal recovery index is corrupt") from exc
        canonical = reload.canonical_source_result
        if (
            record.content.get("normalization_recovery_key_digest")
            != normalization_replay.recovery_key_digest
            or record.content.get("normalization_replay_digest")
            != normalization_replay.replay_digest
            or record.content.get("normalization_result_digest")
            != normalization_replay.source_normalization_result.result_digest
            or record.content.get("locator_digest") != reload.atomic_write_locator_digest
            or canonical.normalization_replay_digest != normalization_replay.replay_digest
            or reload.delivery_principal_binding_digest
            != delivery_principal_binding_digest
            or reload.required_scope_set_digest
            != required_outcome_scopes.required_scope_set_digest
            or reload.operation_fence_binding_digest != operation_fence_binding.binding_digest
        ):
            raise PreplanningStoreError("bootstrap graph terminal recovery index is substituted")
        return self._reload_bootstrap_graph_terminal_exact_v3(
            locator_digest=reload.atomic_write_locator_digest,
            expected_reload=reload,
            expected_normalization_replay_digest=normalization_replay.replay_digest,
            expected_delivery_principal_binding_digest=(
                delivery_principal_binding_digest
            ),
            expected_required_scope_set_digest=(
                required_outcome_scopes.required_scope_set_digest
            ),
            expected_operation_fence_binding=operation_fence_binding,
        )

    def _persist_bootstrap_graph_terminal_v3_linearized(
        self, *, request: object, member_type: type, group_result_type: type,
        canonical_result_type: type, identity_type: type, terminal_control_type: type,
        current_generation_type: type, receipt_type: type,
        reload_type: type, encoder: Callable[[object], bytes],
    ) -> object:
        intent = request.publication_intent
        locator_id = _bootstrap_graph_v3_terminal_locator_id(intent.locator_digest)
        existing = self._memory_plane.get_record(locator_id)
        if existing is not None:
            return self._reload_bootstrap_graph_terminal_v3(request=request, reload_type=reload_type)

        # The absent branch is a live mutation: authenticate it before reading
        # the operation control or epoch head, while a found terminal locator
        # can subsequently prove its historical completed lease.
        if (
            request.delivery_principal_binding_digest
            != intent.delivery_principal_binding_digest
            or request.required_outcome_scopes.required_scope_set_digest
            != intent.required_scope_set_digest
            or request.operation_fence_binding.binding_digest != intent.operation_fence_binding_digest
            or request.operation_lease_binding.binding_digest != intent.operation_lease_binding_digest
            or request.writer_commit_binding.binding_digest != intent.writer_commit_binding_digest
            or request.control_epoch.epoch_digest != intent.control_epoch_digest
        ):
            raise PreplanningStoreError("bootstrap graph terminal authority is substituted")
        self._validate_bootstrap_graph_v3_current_authority(
            request=_TerminalAuthorityRequest(request),
            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            control_epoch=request.control_epoch,
        )
        control_record = self._required_control_record(request.operation_fence_binding)
        control = _control_from_record(control_record)
        if (
            request.predecessor_generation.operation_generation != control.generation
            or request.predecessor_generation.artifact_generation != control.generation
            or control.state in {"terminal", "lease_recovery_exhausted"}
        ):
            raise PreplanningStoreError("bootstrap graph terminal generation is stale")

        payloads = _bootstrap_graph_v3_terminal_payloads(
            request=request, group_result_type=group_result_type,
            canonical_result_type=canonical_result_type,
        )
        members = _bootstrap_graph_v3_terminal_members(
            request=request, payloads=payloads, member_type=member_type, encoder=encoder,
        )
        generation = control.generation + 1
        member_records = tuple(
            _bootstrap_graph_v3_member_record(
                namespace_id=_control_namespace(control), generation=generation,
                member=member, timestamp=self._now(),
            ) for member in members
        )
        manifest_digest = sha256(
            encode_typed_value(tuple(member.model_dump(mode="json") for member in members))
        ).hexdigest()
        atomic_write_digest = request.publication_request_digest
        terminal_control = terminal_control_type.create(
            state="terminal_published", operation_id=request.operation_fence_binding.operation_id,
            request_digest=request.coordinator_request.request_digest,
            locator_digest=intent.locator_digest, atomic_write_digest=atomic_write_digest,
            member_manifest_digest=manifest_digest,
            publication_operation_generation=generation, publication_artifact_generation=generation,
            delivery_principal_binding_digest=intent.delivery_principal_binding_digest,
            required_scope_set_digest=intent.required_scope_set_digest,
            operation_fence_binding_digest=intent.operation_fence_binding_digest,
            control_epoch_digest=intent.control_epoch_digest,
            completed_lease_binding_digest=request.operation_lease_binding.binding_digest,
            writer_commit_binding_digest=intent.writer_commit_binding_digest,
        )
        identity = identity_type.create(
            checkpoint_kind="bootstrap_graph_terminal_checkpoint", source_id=intent.source_id,
            source_digest=intent.source_digest, preparation_fingerprint=intent.preparation_fingerprint,
            operation_id=intent.operation_id, publication_intent_digest=intent.intent_digest,
            locator_digest=intent.locator_digest, request_digest=request.coordinator_request.request_digest,
            normalization_replay_digest=request.coordinator_request.normalization_replay.replay_digest,
            atomic_write_digest=atomic_write_digest, expected_operation_generation=control.generation,
            expected_artifact_generation=control.generation, publication_operation_generation=generation,
            publication_artifact_generation=generation,
            member_manifest_id=_bootstrap_graph_v3_manifest_id(_control_namespace(control), generation),
            member_manifest_digest=manifest_digest,
            required_member_digests=tuple(member.member_digest for member in members),
            operation_fence_binding_digest=intent.operation_fence_binding_digest,
            control_epoch_digest=intent.control_epoch_digest,
            terminal_control_digest=terminal_control.terminal_control_digest,
            completed_lease_binding_digest=request.operation_lease_binding.binding_digest,
        )
        canonical_result = payloads["bootstrap_graph_canonical_source_result"][0]
        successor = current_generation_type.create(
            store_identity_digest=sha256(_control_namespace(control).encode()).hexdigest(),
            operation_id=request.operation_fence_binding.operation_id,
            request_digest=request.coordinator_request.request_digest,
            operation_generation=generation, artifact_generation=generation,
            latest_atomic_write_digest=atomic_write_digest,
            control_epoch_digest=request.control_epoch.epoch_digest,
        )
        receipt = receipt_type.create(
            checkpoint_kind="bootstrap_graph_terminal_checkpoint",
            predecessor_generation=request.predecessor_generation,
            write_request_digest=request.publication_request_digest,
            atomic_write_digest=atomic_write_digest,
            reload_core_digest=terminal_control.terminal_control_digest,
            publication_operation_generation=generation,
            publication_artifact_generation=generation,
            successor_generation=successor,
        )
        reload = reload_type.create(
            handoff_digest=request.handoff.handoff_digest,
            atomic_write_locator_digest=intent.locator_digest, final_write_identity=identity,
            terminal_control=terminal_control, canonical_source_result=canonical_result,
            delivery_principal_binding_digest=intent.delivery_principal_binding_digest,
            required_scope_set_digest=intent.required_scope_set_digest,
            operation_fence_binding_digest=intent.operation_fence_binding_digest,
            operation_lease_binding_digest=request.operation_lease_binding.binding_digest,
            control_epoch_digest=intent.control_epoch_digest,
            checkpoint_receipt=receipt,
        )
        timestamp = self._now()
        manifest = _bootstrap_graph_v3_terminal_manifest_record(
            namespace_id=_control_namespace(control), generation=generation, members=members,
            manifest_digest=manifest_digest, request=request, timestamp=timestamp,
        )
        terminal_record = _bootstrap_graph_v3_terminal_control_record(terminal_control, timestamp)
        identity_record = _bootstrap_graph_v3_terminal_identity_record(identity, timestamp)
        locator_record = _bootstrap_graph_v3_terminal_locator_record(
            locator_digest=intent.locator_digest, handoff_digest=request.handoff.handoff_digest,
            reload=reload, timestamp=timestamp,
        )
        request_record = _bootstrap_graph_v3_terminal_request_record(
            request_digest=request.coordinator_request.request_digest,
            locator_digest=intent.locator_digest, reload=reload, timestamp=timestamp,
        )
        recovery_record = _bootstrap_graph_v3_terminal_recovery_record(
            normalization_replay=request.coordinator_request.normalization_replay,
            locator_digest=intent.locator_digest, reload=reload, timestamp=timestamp,
        )
        next_control = control.model_copy(update={
            "generation": generation, "last_request_digest": atomic_write_digest,
            "state": "terminal", "lease": None,
            "last_completed_lease_binding_digest": request.operation_lease_binding.binding_digest,
        })
        writer_record = self._writers.require_current(request.writer_commit_binding)
        authorization = self._writers._authorize_atomic(
            request.writer_commit_binding, capability=self._write_capability,
            lease_expires_at=request.operation_lease_binding.lease_expires_at, server_now=self._now,
        )
        records = (_control_record(next_control, control_record.timestamp), *member_records,
                   manifest, terminal_record, identity_record, locator_record, request_record,
                   recovery_record)
        try:
            self._memory_plane.conditionally_write_records(
                records,
                preconditions=(
                    RecordDigestPrecondition(memory_id=control_record.memory_id, expected_digest=record_digest(control_record)),
                    RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                    RecordFencePrecondition(memory_id=control_record.memory_id, expected_fence=MemoryRecordFence(execution_token=request.operation_lease_binding.execution_token, ownership_epoch=request.operation_lease_binding.ownership_epoch)),
                    *(RecordAbsentPrecondition(memory_id=item.memory_id) for item in records[1:]),
                ), authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            if self._memory_plane.get_record(locator_id) is None:
                raise PreplanningStoreError("bootstrap graph terminal CAS conflicted") from exc
        return self._reload_bootstrap_graph_terminal_v3(request=request, reload_type=reload_type)

    def _reload_bootstrap_graph_terminal_v3(self, *, request: object, reload_type: type) -> object:
        """Validate a terminal locator and every persisted immutable join."""
        intent = request.publication_intent
        if (
            request.delivery_principal_binding_digest != intent.delivery_principal_binding_digest
            or request.required_outcome_scopes.required_scope_set_digest
            != intent.required_scope_set_digest
            or request.operation_fence_binding.binding_digest != intent.operation_fence_binding_digest
            or request.control_epoch.epoch_digest != intent.control_epoch_digest
        ):
            raise PreplanningStoreError("bootstrap graph terminal authority is substituted")
        return self._reload_bootstrap_graph_terminal_exact_v3(
            locator_digest=intent.locator_digest,
            reload_type=reload_type,
            expected_handoff_digest=request.handoff.handoff_digest,
            expected_request_digest=request.coordinator_request.request_digest,
            expected_normalization_replay_digest=(
                request.coordinator_request.normalization_replay.replay_digest
            ),
            expected_delivery_principal_binding_digest=(
                request.delivery_principal_binding_digest
            ),
            expected_required_scope_set_digest=(
                request.required_outcome_scopes.required_scope_set_digest
            ),
            expected_operation_fence_binding=request.operation_fence_binding,
            expected_operation_lease_binding_digest=(
                request.operation_lease_binding.binding_digest
            ),
            expected_control_epoch_digest=request.control_epoch.epoch_digest,
        )

    def _reload_bootstrap_graph_terminal_exact_v3(
        self,
        *,
        locator_digest: str,
        expected_reload: object | None = None,
        reload_type: type | None = None,
        expected_handoff_digest: str | None = None,
        expected_request_digest: str | None = None,
        expected_normalization_replay_digest: str | None = None,
        expected_delivery_principal_binding_digest: str,
        expected_required_scope_set_digest: str,
        expected_operation_fence_binding: OperationFenceBinding,
        expected_operation_lease_binding_digest: str | None = None,
        expected_control_epoch_digest: str | None = None,
    ) -> object:
        """Reload one terminal only after proving its immutable persisted closure."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphPlanAtomicMemberV3,
            BootstrapGraphTerminalReloadV3,
        )

        index = self._memory_plane.get_record(
            _bootstrap_graph_v3_terminal_locator_id(locator_digest)
        )
        if index is None or index.source_kind != "semantic_ingestion_bootstrap_graph_v3_terminal_locator":
            raise PreplanningStoreError("bootstrap graph terminal publication is absent")
        try:
            reload = BootstrapGraphTerminalReloadV3.model_validate(
                index.content["reload"], strict=False
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PreplanningStoreError("bootstrap graph terminal locator is corrupt") from exc
        if reload_type is not None:
            try:
                reload = reload_type.model_validate(index.content["reload"], strict=False)
            except (KeyError, TypeError, ValueError) as exc:
                raise PreplanningStoreError("bootstrap graph terminal locator is corrupt") from exc
        if expected_reload is not None and reload != expected_reload:
            raise PreplanningStoreError("bootstrap graph terminal index is substituted")

        identity = reload.final_write_identity
        terminal = reload.terminal_control
        control = _control_from_record(
            self._required_control_record(expected_operation_fence_binding)
        )
        manifest = self._memory_plane.get_record(identity.member_manifest_id)
        terminal_record = self._memory_plane.get_record(
            _bootstrap_graph_v3_terminal_control_id(locator_digest)
        )
        identity_record = self._memory_plane.get_record(
            _bootstrap_graph_v3_terminal_identity_id(locator_digest)
        )
        members_value = () if manifest is None else manifest.content.get("members", ())
        try:
            members = tuple(
                BootstrapGraphPlanAtomicMemberV3.model_validate(item, strict=False)
                for item in members_value
            )
        except (TypeError, ValueError) as exc:
            raise PreplanningStoreError("bootstrap graph terminal member closure is corrupt") from exc
        member_values = tuple(member.model_dump(mode="json") for member in members)
        expected_kinds = (
            "bootstrap_graph_coordinator_request",
            "bootstrap_graph_control_epoch",
            "bootstrap_graph_dependent_attempt",
            "bootstrap_transaction_group_plan",
            "bootstrap_source_plan_lineage_entry",
            "ingestion_execution_manifest",
            "transaction_group_result",
            "bootstrap_graph_terminal_handoff",
            "bootstrap_graph_canonical_source_result",
        )
        kind_order = {kind: offset for offset, kind in enumerate(expected_kinds)}
        member_ids = tuple(member.member_id for member in members)
        member_digests = tuple(member.member_digest for member in members)
        kinds = tuple(member.kind for member in members)
        if (
            index.content.get("locator_digest") != locator_digest
            or index.content.get("handoff_digest") != reload.handoff_digest
            or reload.atomic_write_locator_digest != locator_digest
            or identity.locator_digest != locator_digest
            or terminal.locator_digest != locator_digest
            or identity.terminal_control_digest != terminal.terminal_control_digest
            or terminal.request_digest != identity.request_digest
            or terminal.atomic_write_digest != identity.atomic_write_digest
            or terminal.member_manifest_digest != identity.member_manifest_digest
            or terminal.publication_operation_generation != identity.publication_operation_generation
            or terminal.publication_artifact_generation != identity.publication_artifact_generation
            or terminal.operation_fence_binding_digest != identity.operation_fence_binding_digest
            or terminal.control_epoch_digest != identity.control_epoch_digest
            or terminal.completed_lease_binding_digest != identity.completed_lease_binding_digest
            or reload.operation_fence_binding_digest != terminal.operation_fence_binding_digest
            or reload.operation_lease_binding_digest != terminal.completed_lease_binding_digest
            or reload.control_epoch_digest != terminal.control_epoch_digest
            or reload.checkpoint_receipt.atomic_write_digest != identity.atomic_write_digest
            or reload.checkpoint_receipt.reload_core_digest != terminal.terminal_control_digest
            or control.state != "terminal"
            or control.last_completed_lease_binding_digest != reload.operation_lease_binding_digest
            or manifest is None
            or manifest.source_kind != "semantic_ingestion_bootstrap_graph_v3_manifest"
            or manifest.content.get("semantic_ingestion_kind") != "bootstrap_graph_v3_terminal_manifest"
            or manifest.content.get("locator_digest") != locator_digest
            or manifest.content.get("manifest_digest") != identity.member_manifest_digest
            or sha256(encode_typed_value(member_values)).hexdigest()
            != identity.member_manifest_digest
            or not members
            or len(member_ids) != len(set(member_ids))
            or identity.required_member_digests != member_digests
            or set(kinds) != set(expected_kinds)
            or tuple(sorted(kinds, key=kind_order.__getitem__)) != kinds
            or any(kinds.count(kind) != 1 for kind in (
                "bootstrap_graph_coordinator_request",
                "bootstrap_graph_control_epoch",
                "bootstrap_graph_dependent_attempt",
                "bootstrap_transaction_group_plan",
                "ingestion_execution_manifest",
                "bootstrap_graph_terminal_handoff",
                "bootstrap_graph_canonical_source_result",
            ))
            or terminal_record is None
            or terminal_record.source_kind != "semantic_ingestion_bootstrap_graph_v3_terminal_control"
            or terminal_record.content.get("terminal_control") != terminal.model_dump(mode="json")
            or identity_record is None
            or identity_record.source_kind != "semantic_ingestion_bootstrap_graph_v3_terminal_identity"
            or identity_record.content.get("identity") != identity.model_dump(mode="json")
            or reload.delivery_principal_binding_digest
            != expected_delivery_principal_binding_digest
            or reload.required_scope_set_digest != expected_required_scope_set_digest
            or reload.operation_fence_binding_digest
            != expected_operation_fence_binding.binding_digest
            or (expected_handoff_digest is not None and reload.handoff_digest != expected_handoff_digest)
            or (expected_request_digest is not None and identity.request_digest != expected_request_digest)
            or (
                expected_normalization_replay_digest is not None
                and identity.normalization_replay_digest
                != expected_normalization_replay_digest
            )
            or (
                expected_operation_lease_binding_digest is not None
                and reload.operation_lease_binding_digest
                != expected_operation_lease_binding_digest
            )
            or (
                expected_control_epoch_digest is not None
                and reload.control_epoch_digest != expected_control_epoch_digest
            )
        ):
            raise PreplanningStoreError("bootstrap graph terminal reload is corrupt or substituted")
        for member, member_value in zip(members, member_values, strict=True):
            record = self._memory_plane.get_record(
                _bootstrap_graph_v3_member_id(
                    _control_namespace(control),
                    identity.publication_operation_generation,
                    member.member_id,
                )
            )
            if (
                record is None
                or record.source_kind != "semantic_ingestion_bootstrap_graph_v3_member"
                or record.content.get("member") != member_value
            ):
                raise PreplanningStoreError("bootstrap graph terminal member closure is incomplete")
        return reload

    def _reload_bootstrap_graph_transaction_v3(
        self,
        *,
        request: object,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
        control_epoch: object,
        current_generation_type: type,
        reload_core_type: type,
        receipt_type: type,
        reload_type: type,
    ) -> object:
        from memorii.core.semantic_ingestion.contracts import (
            validate_bootstrap_graph_plan_atomic_members_v3,
        )

        try:
            validate_bootstrap_graph_plan_atomic_members_v3(request.members)
        except ValueError as exc:
            raise PreplanningStoreError("bootstrap graph reload member is not native") from exc
        self._validate_bootstrap_graph_v3_current_authority(
            request=request,
            delivery_principal_binding_digest=delivery_principal_binding_digest,
            required_outcome_scopes=required_outcome_scopes,
            control_epoch=control_epoch,
            allow_terminal_recovery=True,
        )
        control = _control_from_record(self._required_control_record(request.operation_fence_binding))
        index = self._memory_plane.get_record(_bootstrap_graph_v3_idempotency_id(request.write_digest))
        if (
            index is None
            or index.source_kind != "semantic_ingestion_bootstrap_graph_v3_idempotency"
            or index.content.get("request_write_digest") != request.write_digest
            or index.content.get("namespace_id") != _control_namespace(control)
            or index.content.get("publication_operation_generation")
            != request.publication_operation_generation
        ):
            raise PreplanningStoreError("bootstrap graph checkpoint is absent")
        manifest = self._memory_plane.get_record(
            _bootstrap_graph_v3_manifest_id(_control_namespace(control), request.publication_operation_generation)
        )
        if (
            manifest is None
            or manifest.source_kind != "semantic_ingestion_bootstrap_graph_v3_manifest"
            or manifest.content.get("request") != request.model_dump(mode="json")
        ):
            raise PreplanningStoreError("bootstrap graph checkpoint manifest is corrupt")
        for member in request.members:
            record = self._memory_plane.get_record(
                _bootstrap_graph_v3_member_id(
                    _control_namespace(control), request.publication_operation_generation, member.member_id
                )
            )
            if (
                record is None
                or record.source_kind != "semantic_ingestion_bootstrap_graph_v3_member"
                or record.content.get("member") != member.model_dump(mode="json")
            ):
                raise PreplanningStoreError("bootstrap graph checkpoint member closure is incomplete")
        core = reload_core_type.create(
            write_request_digest=request.write_digest,
            publication_operation_generation=request.publication_operation_generation,
            publication_artifact_generation=request.publication_artifact_generation,
            members=request.members,
            required_member_digests=request.required_member_digests,
            delivery_principal_binding_digest=(
                delivery_principal_binding_digest
            ),
            required_scope_set_digest=required_outcome_scopes.required_scope_set_digest,
            operation_fence_binding_digest=request.operation_fence_binding.binding_digest,
            operation_lease_binding_digest=request.operation_lease_binding.binding_digest,
            control_epoch_digest=control_epoch.epoch_digest,
        )
        successor = current_generation_type.create(
            store_identity_digest=sha256(_control_namespace(control).encode()).hexdigest(),
            operation_id=request.operation_fence_binding.operation_id,
            request_digest=request.request_digest,
            operation_generation=request.publication_operation_generation,
            artifact_generation=request.publication_artifact_generation,
            latest_atomic_write_digest=request.write_digest,
            control_epoch_digest=control_epoch.epoch_digest,
        )
        receipt = receipt_type.create(
            checkpoint_kind=request.kind, predecessor_generation=request.predecessor_generation,
            write_request_digest=request.write_digest, atomic_write_digest=request.write_digest,
            reload_core_digest=core.core_digest,
            publication_operation_generation=request.publication_operation_generation,
            publication_artifact_generation=request.publication_artifact_generation,
            successor_generation=successor,
        )
        return reload_type.create(core=core, checkpoint_receipt=receipt)

    def _validate_bootstrap_graph_v3_current_authority(
        self,
        *,
        request: object,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
        control_epoch: object,
        allow_terminal_recovery: bool = False,
    ) -> None:
        """Validate mutable authority before any V3 graph record lookup."""
        from memorii.core.semantic_ingestion.contracts import BootstrapGraphControlEpochV3

        if not isinstance(control_epoch, BootstrapGraphControlEpochV3):
            raise PreplanningStoreError("bootstrap graph control epoch is invalid")
        if (
            request.control_epoch_digest != control_epoch.epoch_digest
            or request.operation_fence_binding != control_epoch.operation_fence_binding
            or request.writer_commit_binding != control_epoch.writer_commit_binding
            or request.operation_lease_binding != control_epoch.operation_lease_binding
            or delivery_principal_binding_digest
            != control_epoch.delivery_principal_binding_digest
            or required_outcome_scopes.required_scope_set_digest
            != control_epoch.required_scope_set_digest
        ):
            raise PreplanningStoreError("bootstrap graph current authority is substituted")
        self._writers.require_current(request.writer_commit_binding)
        control_record = self._required_control_record(request.operation_fence_binding)
        control = _control_from_record(control_record)
        active = (
            control.lease is not None
            and self.lease_binding(control) == request.operation_lease_binding
            and request.operation_lease_binding.lease_expires_at > self._now()
        )
        terminal = (
            allow_terminal_recovery
            and control.state == "terminal"
            and control.last_request_digest == request.write_digest
            and control.last_completed_lease_binding_digest
            == request.operation_lease_binding.binding_digest
        )
        if not active and not terminal:
            raise PreplanningStoreError("bootstrap graph lease is stale or expired")
        head = self._memory_plane.get_record(
            _bootstrap_graph_v3_epoch_head_id(control_epoch.request_core_digest)
        )
        if (
            head is None
            or head.source_kind != "semantic_ingestion_bootstrap_graph_v3_epoch_head"
            or head.content.get("epoch_digest") != control_epoch.epoch_digest
        ):
            raise PreplanningStoreError("bootstrap graph control epoch is not current")

    def commit_or_reload_bootstrap_graph_group_v3(self, *, request: object) -> object:
        """Atomically materialize and persist one complete V3 group outcome.

        This deliberately has no per-operation write entry point: the primary
        record and every member fanout row are written in the same CAS as the
        control successor, so an acknowledgement loss can only reload the
        whole group closure.
        """
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphAtomicEffectReceiptV3,
            BootstrapGraphCurrentGenerationV3,
            BootstrapGraphGroupCommitReloadV3,
            BootstrapGraphGroupCommitRequestV3,
            BootstrapGraphGroupCommitResultCoreV3,
            BootstrapGraphGroupCommitResultV3,
            BootstrapGraphOperationCommitResultV3,
            contract_digest,
            encode_semantic_contract,
            validate_bootstrap_native_operation_reduction_v3,
        )

        if not isinstance(request, BootstrapGraphGroupCommitRequestV3):
            raise PreplanningStoreError("bootstrap graph group commit has an invalid type")
        request = BootstrapGraphGroupCommitRequestV3.model_validate(request.model_dump(mode="python"))
        for item in request.ordered_operation_inputs:
            validate_bootstrap_native_operation_reduction_v3(
                item.reduction,
                sealed_snapshot_digest=request.attempt.graph_snapshot_digest,
                effective_read_set_digest=request.attempt.sealed_read_set_digest,
            )
        self._validate_bootstrap_graph_v3_current_authority(
            request=request,
            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            control_epoch=request.control_epoch,
        )
        primary_id = _bootstrap_graph_v3_group_commit_primary_id(
            request.source_operation_id, request.transaction_group_id,
            request.operation_ids, request.request_ctv_digest,
        )
        existing = self._memory_plane.get_record(primary_id)
        if existing is not None:
            return _bootstrap_graph_v3_group_commit_reload_from_record(existing, request)

        def write() -> object:
            control_record = self._required_control_record(request.operation_fence_binding)
            control = _control_from_record(control_record)
            if (
                control.generation != request.expected_generation.operation_generation
                or request.expected_generation.artifact_generation != control.generation
                or request.expected_generation.control_epoch_digest != request.control_epoch.epoch_digest
            ):
                raise PreplanningStoreError("bootstrap graph group commit generation is stale")
            before_graph = control.graph_revision
            before_observation = control.observation_revision
            accepted = any(
                item.reduction.native_terminal.status == "accepted"
                for item in request.ordered_operation_inputs
            )
            after_graph = before_graph if not accepted else sha256(
                b"memorii.semantic-ingestion.bootstrap-graph-group-revision.v3\0"
                + before_graph.encode() + request.request_ctv_digest.encode()
            ).hexdigest()
            after_observation = sha256(
                b"memorii.semantic-ingestion.bootstrap-graph-group-observation-revision.v3\0"
                + before_observation.encode() + request.request_ctv_digest.encode()
            ).hexdigest()
            committed_at = self._now()
            operation_results = []
            effect_records: list[CanonicalMemoryRecord] = []
            all_materialized_records: list[object] = []
            for item in request.ordered_operation_inputs:
                reduction = item.reduction
                materialization = reduction.effect_materialization
                is_accepted = reduction.native_terminal.status == "accepted"
                materialized_records: tuple[object, ...] = ()
                if is_accepted:
                    from memorii.core.memory_evolution.graph_planning import (
                        PlanningCommitValues,
                        materialize_canonical_planning_payload,
                    )

                    commit_values = PlanningCommitValues(
                        transaction_group_id=request.transaction_group_id,
                        graph_revision_before=before_graph,
                        graph_revision_after=after_graph,
                        committed_at=committed_at,
                    )
                    materialized_records = tuple(
                        materialize_canonical_planning_payload(
                            intent.canonical_after_record,
                            commit_values=commit_values,
                            authorizing_transaction_group_id=request.transaction_group_id,
                        )
                        for intent in materialization.record_intents
                    )
                    all_materialized_records.extend(materialized_records)
                    if tuple(
                        (record.record_kind, record.record_digest)
                        for record in materialized_records
                    ) != tuple(sorted(
                        (
                            record.record_kind,
                            record.record_digest,
                        )
                        for record in materialized_records
                    )):
                        raise PreplanningStoreError(
                            "bootstrap graph materialized records are not canonical"
                        )
                graph_payload = encode_typed_value(tuple(
                    record.model_dump(mode="python") for record in materialized_records
                ))
                graph_digest = None if not is_accepted else contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-graph-native-delta.v3",
                    {
                        "operation_execution_id": item.operation_execution_id,
                        "graph_revision_before": before_graph,
                        "graph_revision_after": after_graph,
                        "records": tuple(
                            record.model_dump(mode="python")
                            for record in materialized_records
                        ),
                    },
                )
                event_payload = encode_typed_value({
                    "operation_execution_id": item.operation_execution_id,
                    "operation_id": item.operation_id,
                    "transaction_group_id": request.transaction_group_id,
                    "graph_delta_digest": graph_digest,
                    "record_digests": tuple(
                        record.record_digest
                        for record in materialized_records
                    ),
                    "committed_at": committed_at,
                })
                event_digest = None if not is_accepted else contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-graph-native-event-batch.v3",
                    decode_typed_value(event_payload),
                )
                observation_payload = encode_typed_value({
                    "operation_execution_id": item.operation_execution_id,
                    "operation_id": item.operation_id,
                    "disposition": materialization.observation_disposition,
                    "reason_codes": materialization.observation_reason_codes,
                    "graph_delta_digest": graph_digest,
                    "event_batch_digest": event_digest,
                    "observation_revision_before": before_observation,
                    "observation_revision_after": after_observation,
                })
                observation_digest = contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-graph-native-observation.v3",
                    decode_typed_value(observation_payload),
                )
                operation_results.append(BootstrapGraphOperationCommitResultV3.create(
                    transaction_group_id=request.transaction_group_id,
                    operation_id=item.operation_id,
                    operation_execution_id=item.operation_execution_id,
                    operation_input_digest=item.input_digest,
                    reduction=reduction,
                    final_status=reduction.native_terminal.status,
                    graph_delta_digest=graph_digest,
                    event_batch_digest=event_digest,
                    observation_delta_digest=observation_digest,
                ))
                effect_records.append(_bootstrap_graph_v3_group_commit_effect_record(
                    primary_id=primary_id, operation_id=item.operation_id,
                    kind="result", payload=encode_semantic_contract(operation_results[-1]),
                    timestamp=committed_at, carrier_digest=operation_results[-1].result_digest,
                ))
                if is_accepted:
                    effect_records.append(_bootstrap_graph_v3_group_commit_effect_record(
                        primary_id=primary_id, operation_id=item.operation_id,
                        kind="graph_delta", payload=graph_payload, timestamp=committed_at,
                        carrier_digest=graph_digest,
                    ))
                    effect_records.append(_bootstrap_graph_v3_group_commit_effect_record(
                        primary_id=primary_id, operation_id=item.operation_id,
                        kind="event_batch", payload=event_payload, timestamp=committed_at,
                        carrier_digest=event_digest,
                    ))
                effect_records.append(_bootstrap_graph_v3_group_commit_effect_record(
                    primary_id=primary_id, operation_id=item.operation_id,
                    kind="observation_delta", payload=observation_payload,
                    timestamp=committed_at, carrier_digest=observation_digest,
                ))
            canonical_event_records: tuple[CanonicalMemoryRecord, ...] = ()
            canonical_event_preconditions: tuple[MemoryPlanePrecondition, ...] = ()
            if accepted:
                from memorii.core.semantic_ingestion.contracts import SemanticGraphDelta
                from memorii.core.semantic_ingestion.event_replay import (
                    build_semantic_memory_event_batch,
                    replay_semantic_event_batches,
                )

                durable_kinds = {
                    "claim_assertion",
                    "action_revision",
                    "identity_lineage",
                    "temporal_transition",
                }
                durable_carriers = tuple(
                    record
                    for record in all_materialized_records
                    if record.record_kind in durable_kinds
                )
                graph_records = tuple(
                    record
                    for record in all_materialized_records
                    if record.record_kind not in durable_kinds
                )
                delta_body = {
                    "kind": "semantic_graph_delta",
                    "operation_id": request.transaction_group_id,
                    "carriers": durable_carriers,
                    "graph_records": graph_records,
                    "terminal_binding_sets": (),
                }
                canonical_graph_delta = SemanticGraphDelta(
                    **delta_body,
                    delta_digest=contract_digest(
                        b"memorii.semantic-ingestion.graph-delta.v1",
                        delta_body,
                    ),
                )
                prior_replay_state = self.semantic_replay_state()
                if prior_replay_state.graph_revision != before_graph:
                    raise PreplanningStoreError(
                        "bootstrap graph replay state is stale"
                    )
                canonical_event_batch = build_semantic_memory_event_batch(
                    graph_delta=canonical_graph_delta,
                    prior_state=prior_replay_state,
                    repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                    source_id=request.operation_fence_binding.source_id,
                    transaction_group_id=request.transaction_group_id,
                    operation_fence_id=(
                        request.operation_fence_binding.operation_fence_id
                    ),
                    writer_epoch=request.writer_commit_binding.expected_writer_epoch,
                    graph_revision_before=before_graph,
                    graph_revision_after=after_graph,
                    timestamp=committed_at,
                    registry=self._event_schema_registry_history.current,
                )
                next_replay_state = replay_semantic_event_batches(
                    repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                    batches=(canonical_event_batch,),
                    registry_history=self._event_schema_registry_history,
                    initial_state=prior_replay_state,
                )
                from memorii.core.memory_evolution.reference_integrity import (
                    advance_reference_integrity,
                )

                prior_reference_integrity = self.reference_integrity_snapshot()
                next_reference_integrity = advance_reference_integrity(
                    prior_reference_integrity,
                    prior_state=prior_replay_state,
                    next_state=next_replay_state,
                    operation_id=request.transaction_group_id,
                    completed_at=committed_at,
                )
                replay_state_record = self._memory_plane.get_record(
                    _semantic_replay_state_id()
                )
                reference_integrity_record = self._memory_plane.get_record(
                    _reference_integrity_ledger_id()
                )
                if reference_integrity_record is None:
                    raise PreplanningStoreError(
                        "bootstrap graph reference integrity authority is absent"
                    )
                canonical_event_records = (
                    _semantic_event_batch_record(canonical_event_batch, committed_at),
                    _semantic_replay_state_record(next_replay_state, committed_at),
                    _reference_integrity_ledger_record(
                        next_reference_integrity, committed_at
                    ),
                )
                canonical_event_preconditions = (
                    RecordAbsentPrecondition(
                        memory_id=canonical_event_records[0].memory_id
                    ),
                    (
                        RecordAbsentPrecondition(
                            memory_id=canonical_event_records[1].memory_id
                        )
                        if replay_state_record is None
                        else RecordDigestPrecondition(
                            memory_id=replay_state_record.memory_id,
                            expected_digest=record_digest(replay_state_record),
                        )
                    ),
                    RecordDigestPrecondition(
                        memory_id=reference_integrity_record.memory_id,
                        expected_digest=record_digest(reference_integrity_record),
                    ),
                )
            atomic_write = sha256(
                b"memorii.semantic-ingestion.bootstrap-graph-group-atomic-write.v3\0"
                + request.request_ctv_digest.encode() + str(control.generation + 1).encode()
            ).hexdigest()
            core = BootstrapGraphGroupCommitResultCoreV3.create(
                request_ctv_digest=request.request_ctv_digest,
                disposition="committed" if accepted else "noncommitting",
                ordered_operation_results=tuple(operation_results),
                graph_revision_before=before_graph, graph_revision_after=after_graph,
                event_revision_before=before_graph, event_revision_after=after_graph,
                observation_revision_before=before_observation, observation_revision_after=after_observation,
                publication_operation_generation=control.generation + 1,
                publication_artifact_generation=control.generation + 1,
                atomic_write_digest=atomic_write,
            )
            receipt = BootstrapGraphAtomicEffectReceiptV3.create(
                request_ctv_digest=request.request_ctv_digest, result_core_digest=core.core_digest,
                transaction_group_id=request.transaction_group_id,
                ordered_operation_result_digests=tuple(item.result_digest for item in operation_results),
                graph_revision_before=before_graph, graph_revision_after=after_graph,
                event_revision_before=before_graph, event_revision_after=after_graph,
                observation_revision_before=before_observation, observation_revision_after=after_observation,
                atomic_write_digest=atomic_write,
            )
            result = BootstrapGraphGroupCommitResultV3.create(core=core, receipt=receipt)
            successor = BootstrapGraphCurrentGenerationV3.create(
                store_identity_digest=sha256(_control_namespace(control).encode()).hexdigest(),
                operation_id=request.source_operation_id, request_digest=request.request_digest,
                operation_generation=control.generation + 1, artifact_generation=control.generation + 1,
                latest_atomic_write_digest=atomic_write, control_epoch_digest=request.control_epoch.epoch_digest,
            )
            reload = BootstrapGraphGroupCommitReloadV3.create(
                source_operation_id=request.source_operation_id, transaction_group_id=request.transaction_group_id,
                operation_ids=request.operation_ids, request_ctv_digest=request.request_ctv_digest,
                persisted_result=result, successor_generation=successor,
            )
            next_control = control.model_copy(update={
                "generation": control.generation + 1, "state": "planned",
                "last_request_digest": request.request_ctv_digest,
                "graph_revision": after_graph, "observation_revision": after_observation,
                "group_result_digests": (*control.group_result_digests, result.result_digest),
            })
            records = (
                _control_record(next_control, control_record.timestamp),
                _bootstrap_graph_v3_group_commit_primary_record(primary_id, request, reload, timestamp=self._now()),
                *(_bootstrap_graph_v3_group_commit_fanout_record(
                    source_operation_id=request.source_operation_id,
                    transaction_group_id=request.transaction_group_id,
                    operation_ids=request.operation_ids, member_operation_id=operation_id,
                    request_ctv_digest=request.request_ctv_digest, primary_id=primary_id,
                    reload_digest=reload.reload_digest, timestamp=self._now(),
                ) for operation_id in request.operation_ids),
                *effect_records,
                *canonical_event_records,
            )
            writer_record = self._writers.require_current(request.writer_commit_binding)
            authorization = self._writers._authorize_atomic(
                request.writer_commit_binding, capability=self._write_capability,
                lease_expires_at=request.operation_lease_binding.lease_expires_at, server_now=self._now,
            )
            try:
                self._memory_plane.conditionally_write_records(
                    records,
                    preconditions=(
                        RecordDigestPrecondition(memory_id=control_record.memory_id, expected_digest=record_digest(control_record)),
                        RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
                        *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in records[1:-len(canonical_event_records) or None]),
                        *canonical_event_preconditions,
                    ), authorization=authorization,
                )
            except MemoryPlaneRevisionConflictError as exc:
                found = self._memory_plane.get_record(primary_id)
                if found is None:
                    raise PreplanningStoreError("bootstrap graph group commit CAS conflicted") from exc
                return _bootstrap_graph_v3_group_commit_reload_from_record(found, request)
            return reload

        if self._semantic_integrity_linearization is None:
            return write()
        with self._semantic_integrity_linearization.exclusive():
            return write()

    def reload_exact_bootstrap_graph_group_v3(
        self, *, source_operation_id: str, transaction_group_id: str,
        operation_ids: tuple[str, ...], request_ctv_digest: str,
        delivery_principal_binding_digest: str, required_outcome_scopes: object,
        operation_fence_binding: object,
    ) -> object | None:
        """Reload one group primary only after caller authority is authenticated."""
        primary_id = _bootstrap_graph_v3_group_commit_primary_id(
            source_operation_id, transaction_group_id, operation_ids, request_ctv_digest,
        )
        record = self._memory_plane.get_record(primary_id)
        if record is None:
            return None
        request = _bootstrap_graph_v3_group_commit_request_from_record(record)
        if (
            request.delivery_principal_binding_digest != delivery_principal_binding_digest
            or request.required_outcome_scopes != required_outcome_scopes
            or request.operation_fence_binding != operation_fence_binding
        ):
            raise PreplanningStoreError("bootstrap graph group commit reload authority is substituted")
        self._validate_bootstrap_graph_v3_current_authority(
            request=request, delivery_principal_binding_digest=delivery_principal_binding_digest,
            required_outcome_scopes=required_outcome_scopes, control_epoch=request.control_epoch,
            allow_terminal_recovery=True,
        )
        return _bootstrap_graph_v3_group_commit_reload_from_record(record, request)

    def persist_terminal_group(
        self,
        request: TerminalGroupAtomicWriteRequest,
    ) -> tuple[AtomicGenerationMember, ...]:
        recovered = self._recover_exact_generation_if_current(request)
        if recovered is not None:
            if isinstance(request, CommittedGroupAtomicWriteRequest):
                self.semantic_replay_authority()
            return recovered
        control = _control_from_record(self._required_control_record(request.operation_fence_binding))
        if control.state != "planned":
            raise PreplanningStoreError("terminal group requires planned source progress")
        if request.kind == "committed" and request.writer_commit_binding.runtime_mode == "evidence_only":
            raise PreplanningStoreError("evidence-only writer cannot publish graph or event effects")
        if request.expected_observation_revision != control.observation_revision:
            raise PreplanningStoreError("observation revision precondition is stale")
        if request.kind == "committed":
            if (
                request.expected_graph_revision != control.graph_revision
                or request.expected_effective_read_set_digest != control.effective_read_set_digest
            ):
                raise PreplanningStoreError("graph/read-set precondition is stale")
            required = {
                "artifact_index",
                "group_result",
                "observation_delta",
                "graph_delta",
                "event_batch",
            }
            allowed = required | {"replay_artifact", "artifact_index", "artifact_closure"}
        else:
            required = {"artifact_index", "group_result", "observation_delta"}
            allowed = required | {"replay_artifact", "artifact_index", "artifact_closure"}
        counts = _member_kind_counts(request.members)
        if any(counts.get(kind) != 1 for kind in required):
            raise PreplanningStoreError("terminal group generation is incomplete")
        group_results = tuple(member for member in request.members if member.kind == "group_result")
        if len(group_results) != 1:
            raise PreplanningStoreError("terminal group requires exactly one group result")
        if request.kind == "committed" and request.authorization_precondition is None:
            raise PreplanningStoreError("committed group requires a same-store authorization precondition")

        return self._publish_generation(
            request,
            next_state="planned",
            allowed_kinds=allowed,
            terminal_group_result_digest=group_results[0].payload_digest,
            graph_revision_after=request.graph_revision_after if request.kind == "committed" else None,
            observation_revision_after=request.observation_revision_after,
        )

    def finalize_source(self, request: SourceFinalizationAtomicWriteRequest) -> tuple[AtomicGenerationMember, ...]:
        recovered = self._recover_exact_generation_if_current(request)
        if recovered is not None:
            return recovered
        control = _control_from_record(self._required_control_record(request.operation_fence_binding))
        required = {"terminal_operation", "source_summary", "source_result", "observation_delta", "lifecycle"}
        if any(_member_kind_counts(request.members).get(kind) != 1 for kind in required):
            raise PreplanningStoreError("source finalization generation is incomplete")
        if request.expected_group_result_digests != control.group_result_digests:
            raise PreplanningStoreError("source finalization group-result closure is mismatched")
        if request.source_summary_kind == "graph_bound" and not control.group_result_digests:
            raise PreplanningStoreError("graph-bound source has no terminal group results")
        if request.source_summary_kind == "pre_graph" and control.group_result_digests:
            raise PreplanningStoreError("pre-graph source cannot contain terminal group results")
        return self._publish_generation(
            request,
            next_state="terminal",
            allowed_kinds=required | {"replay_artifact", "artifact_index", "artifact_closure"},
            clear_lease=True,
        )

    def _publish_generation(
        self,
        request: AtomicGenerationRequest,
        *,
        next_state: Literal["preplanning", "planned", "terminal"],
        allowed_kinds: set[str],
        terminal_group_result_digest: str | None = None,
        graph_revision_after: str | None = None,
        observation_revision_after: str | None = None,
        clear_lease: bool = False,
    ) -> tuple[AtomicGenerationMember, ...]:
        linearization = self._semantic_integrity_linearization
        if linearization is None:
            return self._publish_generation_linearized(
                request,
                next_state=next_state,
                allowed_kinds=allowed_kinds,
                terminal_group_result_digest=terminal_group_result_digest,
                graph_revision_after=graph_revision_after,
                observation_revision_after=observation_revision_after,
                clear_lease=clear_lease,
            )
        with linearization.exclusive():
            return self._publish_generation_linearized(
                request,
                next_state=next_state,
                allowed_kinds=allowed_kinds,
                terminal_group_result_digest=terminal_group_result_digest,
                graph_revision_after=graph_revision_after,
                observation_revision_after=observation_revision_after,
                clear_lease=clear_lease,
            )

    def _publish_generation_linearized(
        self,
        request: AtomicGenerationRequest,
        *,
        next_state: Literal["preplanning", "planned", "terminal"],
        allowed_kinds: set[str],
        terminal_group_result_digest: str | None = None,
        graph_revision_after: str | None = None,
        observation_revision_after: str | None = None,
        clear_lease: bool = False,
    ) -> tuple[AtomicGenerationMember, ...]:
        # Import here to keep the memory-evolution owner independent of the
        # semantic contract module at import time.
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapSourceNormalizationAtomicWriteRequestV3,
        )

        writer_record = self._writers.require_current(request.writer_commit_binding)
        control_record = self._required_control_record(request.operation_fence_binding)
        control = _control_from_record(control_record)
        if (
            control.operation_fence != request.operation_fence_binding
            or control.writer_binding != request.writer_commit_binding
        ):
            raise PreplanningStoreError("generation does not bind the admitted operation")
        if request.request_digest != generation_request_digest(request):
            raise PreplanningStoreError("generation request digest is invalid")
        active_lease_matches = (
            control.lease is not None
            and self.lease_binding(control) == request.operation_lease_binding
            and request.operation_lease_binding.lease_expires_at > self._now()
        )
        terminal_recovery_matches = (
            control.state == "terminal"
            and control.last_request_digest == request.request_digest
            and control.last_completed_lease_binding_digest == request.operation_lease_binding.binding_digest
        )
        if not active_lease_matches and not terminal_recovery_matches:
            raise PreplanningStoreError("generation lease is stale or expired")
        if control.last_request_digest == request.request_digest:
            return self._read_generation_members(control, control.generation)
        if control.state in {"terminal", "lease_recovery_exhausted"}:
            raise PreplanningStoreError("operation is terminal")
        if (
            control.generation != request.expected_operation_generation
            or request.expected_artifact_generation != control.generation
        ):
            raise PreplanningStoreError("generation precondition is stale")
        if next_state == "preplanning" and control.state == "planned":
            raise PreplanningStoreError("planned progress cannot regress")
        ids = tuple(member.member_id for member in request.members)
        if len(ids) != len(set(ids)) or ids != tuple(sorted(ids)) or "manifest" in ids:
            raise PreplanningStoreError("generation members must have unique canonical order")
        if any(member.kind not in allowed_kinds for member in request.members):
            raise PreplanningStoreError("generation contains a forbidden member kind")
        if any(sha256(member.canonical_payload).hexdigest() != member.payload_digest for member in request.members):
            raise PreplanningStoreError("generation member digest is invalid")
        source_normalization_request = getattr(request, "kind", None) in {
            "source_normalization_checkpoint",
            "bootstrap_source_normalization_checkpoint",
        }
        available_artifacts = {
            member.payload_digest
            for member in request.members
            if member.kind == "replay_artifact" or source_normalization_request
        }
        for prior_generation in range(2, control.generation + 1):
            try:
                prior_members = self._read_generation_members(control, prior_generation)
            except PreplanningStoreError:
                # V3 recovery's generation two is a sealed control/claim
                # transition, not a candidate generation.  It intentionally
                # has no generic generation manifest or members.
                if self._is_bootstrap_v3_ready_generation(control, prior_generation):
                    continue
                raise
            for member in prior_members:
                if member.kind == "replay_artifact":
                    available_artifacts.add(member.payload_digest)
        if not set(request.required_artifact_digests).issubset(available_artifacts):
            raise PreplanningStoreError("required replay artifact closure is incomplete")
        if (
            isinstance(request, SourceCheckpointAtomicWriteRequest)
            and request.progress_state == "planned"
            and any(
            member.kind == "terminal_artifact" for member in request.members
            )
        ):
            self._validate_planned_terminal_checkpoint(request, control=control)
        terminal_group_closure = (
            self._validate_terminal_group_closure(request, control=control)
            if isinstance(
                request,
                (CommittedGroupAtomicWriteRequest, NonCommittingGroupAtomicWriteRequest),
            )
            else None
        )
        generation = control.generation + 1
        group_result_digests = control.group_result_digests
        if terminal_group_result_digest is not None:
            if terminal_group_result_digest in group_result_digests:
                raise PreplanningStoreError("terminal group result is already recorded")
            group_result_digests = (*group_result_digests, terminal_group_result_digest)
        next_control = control.model_copy(
            update={
                "state": next_state,
                "generation": generation,
                "last_request_digest": request.request_digest,
                "group_result_digests": group_result_digests,
                "graph_revision": graph_revision_after or control.graph_revision,
                "observation_revision": observation_revision_after or control.observation_revision,
                "lease": None if clear_lease else control.lease,
                "last_completed_lease_binding_digest": (
                    request.operation_lease_binding.binding_digest
                    if clear_lease
                    else control.last_completed_lease_binding_digest
                ),
            }
        )
        member_records = tuple(
            _generation_member_record(control, generation, member, self._now()) for member in request.members
        )
        manifest_record = _generation_manifest_record(control, generation, request, self._now())
        recovery_index_record: CanonicalMemoryRecord | None = None
        recovery_claim_record: CanonicalMemoryRecord | None = None
        if isinstance(request, BootstrapSourceNormalizationAtomicWriteRequestV3):
            claim = request.bootstrap_recovery_claim
            now = self._now()
            if now >= claim.expires_server_time:
                raise PreplanningStoreError("bootstrap recovery claim is expired")
            recovery_claim_record = self._memory_plane.get_record(
                _bootstrap_v3_recovery_id(claim.recovery_key_digest)
            )
            if recovery_claim_record is None or recovery_claim_record.content.get("state") != "claimed":
                raise PreplanningStoreError("bootstrap recovery claim is not live")
            if (
                recovery_claim_record.content.get("claim_digest") != claim.claim_digest
                or recovery_claim_record.content.get("claim_nonce") != claim.claim_nonce
                or recovery_claim_record.content.get("control_snapshot") != claim.control_snapshot.model_dump(mode="json")
                or control.generation != claim.expected_operation_generation
            ):
                raise PreplanningStoreError("bootstrap recovery claim is substituted")
            recovery_index_record = _bootstrap_v3_recovery_index_record(
                control=control,
                generation=generation,
                request=request,
                timestamp=now,
            )
        authorization = self._writers._authorize_atomic(
            request.writer_commit_binding,
            capability=self._write_capability,
            lease_expires_at=request.operation_lease_binding.lease_expires_at,
            server_now=self._now,
        )
        event_authority_records, event_authority_preconditions = self._semantic_event_authority_updates(
            request,
            authorization=authorization,
            terminal_group_closure=terminal_group_closure,
        )
        graph_delta_at_barrier = (
            terminal_group_closure.graph_delta
            if terminal_group_closure is not None
            else None
        )

        def semantic_commit_barrier() -> None:
            # The default freeze coordinate is covered by an in-lock absent
            # precondition. A custom external guard must be re-read after the
            # backend has acquired its transaction lock and before CAS/write.
            if (
                graph_delta_at_barrier is not None
                and self._semantic_freeze_guard is not None
                and not self._uses_default_semantic_freeze_guard
            ):
                self._semantic_freeze_guard(graph_delta_at_barrier)
        record_ids = [
            record.memory_id
            for record in (
                _control_record(next_control, control_record.timestamp),
                *member_records,
                manifest_record,
                *(() if recovery_index_record is None else (recovery_index_record,)),
                *event_authority_records,
            )
        ]
        if len(record_ids) != len(set(record_ids)):
            raise PreplanningStoreError("generation record identities collide")
        try:
            self._memory_plane.conditionally_write_records(
                (
                    _control_record(next_control, control_record.timestamp),
                    *member_records,
                    manifest_record,
                    *(() if recovery_index_record is None else (recovery_index_record,)),
                    *event_authority_records,
                ),
                preconditions=(
                    RecordDigestPrecondition(
                        memory_id=control_record.memory_id, expected_digest=record_digest(control_record)
                    ),
                    RecordDigestPrecondition(
                        memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)
                    ),
                    RecordFencePrecondition(
                        memory_id=control_record.memory_id,
                        expected_fence=MemoryRecordFence(
                            execution_token=request.operation_lease_binding.execution_token,
                            ownership_epoch=request.operation_lease_binding.ownership_epoch,
                        ),
                    ),
                    *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in (*member_records, manifest_record)),
                    *((
                        RecordDigestPrecondition(memory_id=recovery_claim_record.memory_id, expected_digest=record_digest(recovery_claim_record)),
                    ) if recovery_claim_record is not None else ()),
                    *event_authority_preconditions,
                    *(
                        (
                            RecordDigestPrecondition(
                                memory_id=request.authorization_precondition.authority_record_id,
                                expected_digest=request.authorization_precondition.expected_record_digest,
                            ),
                        )
                        if isinstance(request, (CommittedGroupAtomicWriteRequest, NonCommittingGroupAtomicWriteRequest))
                        and request.authorization_precondition is not None
                        else ()
                    ),
                ),
                authorization=authorization,
                transaction_precondition=semantic_commit_barrier,
            )
        except MemoryPlaneRevisionConflictError as exc:
            recovered = self._recover_published_generation(request)
            if recovered is None:
                if (
                    any(member.kind == "event_batch" for member in request.members)
                    and self._uses_default_semantic_freeze_guard
                    and self._memory_plane.get_record(_semantic_integrity_control_id()) is not None
                ):
                    raise PreplanningStoreError("semantic repository scope is frozen") from exc
                raise
            if isinstance(request, CommittedGroupAtomicWriteRequest):
                self.semantic_replay_authority()
            return recovered
        return request.members

    @staticmethod
    def _validate_terminal_fence_and_source(
        terminal: SemanticTerminalOutcome,
        *,
        operation_fence: OperationFenceBinding,
    ) -> None:
        from memorii.core.semantic_ingestion.contracts import ClaimAssertion

        source_authority_evidence = (
            *(
                analysis.source_authority_evidence
                for analysis in terminal.source_analyses
                if analysis.source_authority_evidence is not None
            ),
            *(
                operation.source_authority_evidence
                for operation in terminal.sealed_operations
                if operation.source_authority_evidence is not None
            ),
            *(
                carrier.source_authority_evidence
                for carrier in terminal.accepted_carriers
                if isinstance(carrier, ClaimAssertion)
                and carrier.source_authority_evidence is not None
            ),
        )
        if (
            terminal.operation_id != operation_fence.operation_id
            or any(
                analysis.source_id != operation_fence.source_id
                or analysis.source_digest != operation_fence.source_digest
                for analysis in terminal.source_analyses
            )
            or any(
                evidence.source_id != operation_fence.source_id
                or evidence.source_digest != operation_fence.source_digest
                for evidence in source_authority_evidence
            )
        ):
            raise PreplanningStoreError(
                "terminal does not bind its admitted operation source"
            )

    @staticmethod
    def _validate_terminal_artifact_closure(
        terminal: SemanticTerminalOutcome,
        artifact_closure: SemanticArtifactClosure,
    ) -> None:
        from memorii.core.semantic_ingestion.contracts import SemanticArtifactClosure

        if artifact_closure != SemanticArtifactClosure.create(terminal):
            raise PreplanningStoreError(
                "terminal artifact closure is not terminal-derived"
            )

    def _validate_planned_terminal_checkpoint(
        self,
        request: SourceCheckpointAtomicWriteRequest,
        *,
        control: PreplanningOperationControl,
    ) -> None:
        if (
            request.progress_state != "planned"
            or request.operation_fence_binding != control.operation_fence
            or request.writer_commit_binding != control.writer_binding
            or request.expected_operation_generation != control.generation
            or request.expected_artifact_generation != control.generation
        ):
            raise PreplanningStoreError(
                "planned terminal checkpoint does not bind its control"
            )
        self._validate_planned_terminal_members(
            request.members,
            operation_fence=request.operation_fence_binding,
            writer_binding=request.writer_commit_binding,
        )

    def _validate_planned_terminal_members(
        self,
        members: tuple[AtomicGenerationMember, ...],
        *,
        operation_fence: OperationFenceBinding,
        writer_binding: SemanticWriterCommitBinding,
    ) -> _RetainedPlannedTerminalClosure:
        from memorii.core.semantic_ingestion.contracts import (
            SemanticArtifactClosure,
            SemanticContractCodecError,
            SemanticLifecycleTransition,
            SemanticTerminalOutcome,
            TransactionSemanticGroupPlan,
            decode_semantic_contract,
            encode_semantic_contract,
        )

        def unique_member(kind: str) -> AtomicGenerationMember:
            matching = tuple(member for member in members if member.kind == kind)
            if len(matching) != 1:
                raise PreplanningStoreError(
                    f"planned terminal checkpoint requires exactly one {kind.replace('_', ' ')}"
                )
            return matching[0]

        terminal_member = unique_member("terminal_artifact")
        artifact_closure_member = unique_member("artifact_closure")
        try:
            terminal = decode_semantic_contract(
                terminal_member.canonical_payload,
                SemanticTerminalOutcome,
            )
            artifact_closure = decode_semantic_contract(
                artifact_closure_member.canonical_payload,
                SemanticArtifactClosure,
            )
        except (SemanticContractCodecError, ValueError) as exc:
            raise PreplanningStoreError(
                "planned terminal checkpoint closure is invalid"
            ) from exc
        if (
            terminal_member.canonical_payload != encode_semantic_contract(terminal)
            or artifact_closure_member.canonical_payload
            != encode_semantic_contract(artifact_closure)
        ):
            raise PreplanningStoreError(
                "planned terminal checkpoint does not bind its control"
            )
        self._validate_terminal_fence_and_source(
            terminal,
            operation_fence=operation_fence,
        )
        self._validate_terminal_artifact_closure(terminal, artifact_closure)

        expected_payloads = {
            "artifact_index": encode_typed_value(
                {
                    "terminal": terminal.terminal_digest,
                    "closure": artifact_closure.closure_digest,
                }
            ),
            "authorization_read_set": (
                encode_semantic_contract(terminal.authorization_read_set)
                if terminal.authorization_read_set is not None
                else encode_typed_value(None)
            ),
            "independence_certificate": encode_typed_value(
                {
                    "sealed_operations": tuple(
                        operation.sealed_operation_digest
                        for operation in terminal.sealed_operations
                    )
                }
            ),
            "planning_artifact": encode_typed_value(
                {
                    "operation_id": terminal.operation_id,
                    "terminal_digest": terminal.terminal_digest,
                    "execution_lineage": (
                        terminal.execution_lineage.model_dump(mode="python")
                        if terminal.execution_lineage is not None
                        else None
                    ),
                }
            ),
            "planning_authorization": encode_typed_value(
                {
                    "writer_admission_digest": writer_binding.admission_digest,
                    "policy_bundle_digest": (
                        terminal.arbitration_policy_bundle.bundle_digest
                        if terminal.arbitration_policy_bundle is not None
                        else None
                    ),
                    "execution_lineage_digest": (
                        terminal.execution_lineage.lineage_digest
                        if terminal.execution_lineage is not None
                        else None
                    ),
                }
            ),
            "progress": encode_typed_value(
                {
                    "state": "planned",
                    "terminal_digest": terminal.terminal_digest,
                }
            ),
        }
        if any(
            unique_member(kind).canonical_payload != expected_payload
            for kind, expected_payload in expected_payloads.items()
        ):
            raise PreplanningStoreError(
                "planned terminal checkpoint artifacts are substituted"
            )
        plan_member = unique_member("plan")
        legacy_plan_payload = encode_typed_value(
            {
                "kind": (
                    "semantic_terminal_committed"
                    if terminal.status == "accepted"
                    else "semantic_terminal_non_committing"
                )
            }
        )
        if plan_member.canonical_payload != legacy_plan_payload:
            try:
                plan = decode_semantic_contract(
                    plan_member.canonical_payload,
                    TransactionSemanticGroupPlan,
                )
            except (SemanticContractCodecError, ValueError) as exc:
                raise PreplanningStoreError(
                    "planned terminal checkpoint plan is invalid"
                ) from exc
            if (
                encode_semantic_contract(plan) != plan_member.canonical_payload
                or plan.source_id != operation_fence.source_id
            ):
                raise PreplanningStoreError(
                    "planned terminal checkpoint plan does not bind the admitted source"
                )

        lifecycle_members = tuple(
            member for member in members if member.kind == "lifecycle"
        )
        if terminal.status == "accepted":
            lifecycle = SemanticLifecycleTransition.accepted_candidate(
                operation_id=terminal.operation_id,
                candidate_digest=terminal.candidates[0].candidate_digest,
            )
            if (
                len(lifecycle_members) != 1
                or lifecycle_members[0].canonical_payload
                != encode_semantic_contract(lifecycle)
            ):
                raise PreplanningStoreError(
                    "planned terminal checkpoint lifecycle is substituted"
                )
        elif lifecycle_members:
            raise PreplanningStoreError(
                "nonaccepted planned terminal checkpoint carries a lifecycle"
            )
        return _RetainedPlannedTerminalClosure(
            terminal=terminal,
            artifact_closure=artifact_closure,
            terminal_bytes=terminal_member.canonical_payload,
            artifact_closure_bytes=artifact_closure_member.canonical_payload,
        )

    def _retained_planned_terminal_closure(
        self,
        *,
        control: PreplanningOperationControl,
    ) -> _RetainedPlannedTerminalClosure:
        planned_generations_list: list[tuple[AtomicGenerationMember, ...]] = []
        for generation in range(2, control.generation + 1):
            members = self._read_generation_members(control, generation)
            if any(member.kind == "plan" for member in members):
                planned_generations_list.append(members)
        planned_generations = tuple(planned_generations_list)
        if len(planned_generations) != 1:
            raise PreplanningStoreError(
                "terminal group has no unique retained planned generation"
            )
        try:
            return self._validate_planned_terminal_members(
                planned_generations[0],
                operation_fence=control.operation_fence,
                writer_binding=control.writer_binding,
            )
        except PreplanningStoreError as exc:
            raise PreplanningStoreError(
                "retained planned terminal closure is invalid"
            ) from exc

    def _validate_terminal_group_closure(
        self,
        request: TerminalGroupAtomicWriteRequest,
        *,
        control: PreplanningOperationControl,
    ) -> _ValidatedTerminalGroupClosure:
        """Validate the complete terminal group before any authority publication."""

        from memorii.core.semantic_ingestion.contracts import (
            SemanticArtifactClosure,
            SemanticContractCodecError,
            SemanticEffectGroupResult,
            SemanticGraphDelta,
            SemanticObservationDelta,
            decode_semantic_contract,
            encode_semantic_contract,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            SemanticEventReplayError,
            decode_semantic_memory_event_batch,
        )

        def unique_member(kind: str) -> AtomicGenerationMember:
            members = tuple(member for member in request.members if member.kind == kind)
            if len(members) != 1:
                raise PreplanningStoreError(
                    f"terminal group requires exactly one {kind.replace('_', ' ')}"
                )
            return members[0]

        group_result_member = unique_member("group_result")
        artifact_closure_member = unique_member("artifact_closure")
        artifact_index_member = unique_member("artifact_index")
        observation_member = unique_member("observation_delta")
        try:
            group_result = decode_semantic_contract(
                group_result_member.canonical_payload,
                SemanticEffectGroupResult,
            )
            artifact_closure = decode_semantic_contract(
                artifact_closure_member.canonical_payload,
                SemanticArtifactClosure,
            )
            observation = decode_semantic_contract(
                observation_member.canonical_payload,
                SemanticObservationDelta,
            )
        except (SemanticContractCodecError, ValueError) as exc:
            raise PreplanningStoreError("terminal group closure is invalid") from exc

        terminal = group_result.terminal
        self._validate_terminal_fence_and_source(
            terminal,
            operation_fence=request.operation_fence_binding,
        )
        self._validate_terminal_artifact_closure(terminal, artifact_closure)
        retained = self._retained_planned_terminal_closure(control=control)
        if (
            retained.terminal != terminal
            or retained.artifact_closure != artifact_closure
            or retained.terminal_bytes != encode_semantic_contract(terminal)
            or retained.artifact_closure_bytes
            != artifact_closure_member.canonical_payload
        ):
            raise PreplanningStoreError(
                "terminal group differs from its retained planned terminal closure"
            )
        expected_artifact_index = encode_typed_value(
            {
                "terminal": terminal.terminal_digest,
                "closure": artifact_closure.closure_digest,
            }
        )
        if artifact_index_member.canonical_payload != expected_artifact_index:
            raise PreplanningStoreError(
                "terminal group artifact index is not canonical"
            )
        expected_observation_revision = sha256(
            b"memorii.semantic-ingestion.observation-revision.v1\0"
            + control.observation_revision.encode()
            + b"\0"
            + terminal.terminal_digest.encode()
        ).hexdigest()
        if (
            request.operation_fence_binding != control.operation_fence
            or request.writer_commit_binding != control.writer_binding
            or request.expected_operation_generation != control.generation
            or request.expected_artifact_generation != control.generation
            or request.expected_observation_revision != control.observation_revision
            or request.observation_revision_after != expected_observation_revision
            or artifact_closure != group_result.artifact_closure
            or group_result
            != SemanticEffectGroupResult.create(
                terminal=terminal,
                artifact_closure=artifact_closure,
            )
        ):
            raise PreplanningStoreError(
                "terminal group does not bind its admitted operation closure"
            )

        graph_members = tuple(
            member for member in request.members if member.kind == "graph_delta"
        )
        event_members = tuple(
            member for member in request.members if member.kind == "event_batch"
        )
        if isinstance(request, NonCommittingGroupAtomicWriteRequest):
            if terminal.status == "accepted" or graph_members or event_members:
                raise PreplanningStoreError(
                    "non-committing terminal group contains graph or event authority"
                )
            if observation != SemanticObservationDelta.create(
                terminal=terminal,
                graph_delta=None,
            ):
                raise PreplanningStoreError(
                    "non-committing terminal observation is not terminal-derived"
                )
            return _ValidatedTerminalGroupClosure(
                terminal=terminal,
                artifact_closure=artifact_closure,
                observation=observation,
                graph_delta=None,
                event_batch=None,
            )

        if terminal.status != "accepted" or len(graph_members) != 1 or len(event_members) != 1:
            raise PreplanningStoreError(
                "committed terminal group lacks graph or event authority"
            )
        try:
            graph_delta = decode_semantic_contract(
                graph_members[0].canonical_payload,
                SemanticGraphDelta,
            )
            event_batch = decode_semantic_memory_event_batch(
                event_members[0].canonical_payload,
                registry_history=self._event_schema_registry_history,
            )
        except (SemanticContractCodecError, SemanticEventReplayError) as exc:
            raise PreplanningStoreError(
                "canonical semantic event batch is invalid"
            ) from exc
        expected_graph_revision = sha256(
            b"memorii.semantic-ingestion.graph-revision.v1\0"
            + control.graph_revision.encode()
            + b"\0"
            + graph_delta.delta_digest.encode()
        ).hexdigest()
        if (
            request.expected_graph_revision != control.graph_revision
            or request.expected_effective_read_set_digest
            != control.effective_read_set_digest
            or request.graph_revision_after != expected_graph_revision
            or graph_delta
            != self.enrich_identity_graph_delta(
                SemanticGraphDelta.create(terminal), terminal,
                operation_fence_id=request.operation_fence_binding.operation_fence_id,
                graph_revision_before=control.graph_revision,
                graph_revision_after=request.graph_revision_after,
                committed_at=event_batch.events[0].timestamp,
            )
            or observation
            != SemanticObservationDelta.create(
                terminal=terminal,
                graph_delta=graph_delta,
            )
            or event_batch.graph_delta_digest != graph_delta.delta_digest
            or event_batch.transaction_group_id != terminal.operation_id
            or event_batch.transaction_group_id
            != request.operation_fence_binding.operation_id
            or event_batch.operation_fence_id
            != request.operation_fence_binding.operation_fence_id
            or event_batch.source_id != request.operation_fence_binding.source_id
            or event_batch.writer_epoch
            != request.writer_commit_binding.expected_writer_epoch
            or event_batch.events[0].payload.graph_revision_before
            != request.expected_graph_revision
            or event_batch.events[-1].payload.graph_revision_after
            != request.graph_revision_after
        ):
            raise PreplanningStoreError(
                "canonical semantic event batch is invalid"
            )
        return _ValidatedTerminalGroupClosure(
            terminal=terminal,
            artifact_closure=artifact_closure,
            observation=observation,
            graph_delta=graph_delta,
            event_batch=event_batch,
        )

    def _semantic_event_authority_updates(
        self,
        request: AtomicGenerationRequest,
        *,
        authorization: SemanticWriterWriteAuthorization,
        terminal_group_closure: _ValidatedTerminalGroupClosure | None,
    ) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[MemoryPlanePrecondition, ...]]:
        from memorii.core.memory_evolution.policy_migration import (
            PolicyMigrationError,
        )
        from memorii.core.memory_evolution.projection_history import (
            ProjectionCommitRequest,
            ProjectionHistoryError,
            projection_records_from_replay_state,
        )
        from memorii.core.memory_evolution.projection_scheduler import (
            ProjectionSchedulerError,
        )
        from memorii.core.semantic_ingestion.event_replay import (
            SemanticEventReplayError,
            SemanticReplayAuthorityAggregate,
            SemanticReplayAuthorityMemberBinding,
            advance_semantic_replay_authority,
            create_replay_checkpoint,
            decode_semantic_replay_authority,
            replay_semantic_event_batches,
        )

        members = tuple(member for member in request.members if member.kind == "event_batch")
        if len(members) > 1:
            raise PreplanningStoreError("generation has ambiguous semantic event authority")
        batch = (
            terminal_group_closure.event_batch
            if terminal_group_closure is not None
            else None
        )
        graph_delta = (
            terminal_group_closure.graph_delta
            if terminal_group_closure is not None
            else None
        )
        if bool(members) != (batch is not None):
            raise PreplanningStoreError("generation event authority is not terminal-closed")
        prior_state = self.semantic_replay_state()
        next_state = prior_state
        try:
            if batch is not None:
                if not isinstance(request, CommittedGroupAtomicWriteRequest):
                    raise SemanticEventReplayError("non-committing generation contains an event batch")
                if graph_delta is None:
                    raise SemanticEventReplayError(
                        "committed event batch has no graph delta"
                    )
                if self._semantic_freeze_guard is not None:
                    self._semantic_freeze_guard(graph_delta)
                next_state = replay_semantic_event_batches(
                    repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                    batches=(batch,),
                    registry_history=self._event_schema_registry_history,
                    initial_state=next_state,
                )
        except SemanticEventReplayError as exc:
            raise PreplanningStoreError("canonical semantic event batch is invalid") from exc

        tracked_kinds = {
            "observation_delta",
            "progress",
            "replay_artifact",
            "artifact_index",
            "artifact_closure",
        }
        # Source normalization is a graph-free, pre-planning closure.  Its
        # retained progress record is not a semantic replay progress artifact;
        # replay authority begins only after graph-dependent work.
        tracked = (
            ()
            if getattr(request, "kind", None) == "source_normalization_checkpoint"
            else tuple(member for member in request.members if member.kind in tracked_kinds)
        )
        if batch is None and not tracked:
            return (), ()
        bindings = tuple(
            SemanticReplayAuthorityMemberBinding.create(
                operation_fence_id=request.operation_fence_binding.operation_fence_id,
                generation=request.expected_operation_generation + 1,
                member_id=member.member_id,
                member_kind=member.kind,
                payload_digest=member.payload_digest,
            )
            for member in tracked
        )
        aggregate_record = self._memory_plane.get_record(_semantic_replay_authority_id())
        if aggregate_record is None:
            prior = SemanticReplayAuthorityAggregate.genesis(_SEMANTIC_EVENT_REPOSITORY_ID)
        else:
            try:
                canonical_hex = aggregate_record.content["canonical_hex"]
                if not isinstance(canonical_hex, str):
                    raise TypeError
                prior = decode_semantic_replay_authority(bytes.fromhex(canonical_hex))
            except (KeyError, TypeError, ValueError) as exc:
                raise PreplanningStoreError("semantic replay authority is corrupt") from exc
        prior_bindings = (
            *prior.observation_bindings,
            *prior.progress_bindings,
            *prior.artifact_bindings,
        )
        try:
            current_projection_bindings = self._projection_history.replay_bindings()
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError("semantic projection authority is corrupt") from exc
        if prior.projection_history_bindings != current_projection_bindings:
            raise PreplanningStoreError("semantic replay projection authority binding is inconsistent")
        try:
            self._projection_history.validate_active_graph_revision(prior.graph_state.graph_revision)
        except ProjectionHistoryError as exc:
            raise PreplanningStoreError("semantic replay projection graph binding is inconsistent") from exc
        prior_by_coordinate = {
            (
                binding.operation_fence_id,
                binding.generation,
                binding.member_id,
            ): binding
            for binding in prior_bindings
        }
        binding_coordinates = tuple(
            (
                binding.operation_fence_id,
                binding.generation,
                binding.member_id,
            )
            for binding in bindings
        )
        overlapping = tuple(coordinate for coordinate in binding_coordinates if coordinate in prior_by_coordinate)
        if overlapping:
            if (
                len(overlapping) == len(binding_coordinates)
                and all(
                    prior_by_coordinate[coordinate] == binding
                    for coordinate, binding in zip(binding_coordinates, bindings, strict=True)
                )
                and prior.graph_state == next_state
            ):
                # Another exact-delivery writer won after this caller read the
                # operation control. Let the outer control CAS recover that
                # already-published generation instead of duplicating replay
                # bindings in a speculative aggregate.
                return (), ()
            raise PreplanningStoreError("semantic replay authority coordinate is substituted")
        if prior.graph_state != self.semantic_replay_state():
            raise PreplanningStoreError("semantic replay authority graph state is stale")
        prior_reconstructed = self._reconstruct_semantic_replay_authority(
            graph_state=prior.graph_state,
            bindings=prior_bindings,
        )
        if prior_reconstructed.authority_digest != prior.reconstructed_authority_digest:
            raise PreplanningStoreError("semantic replay authority member closure is corrupt")
        reconstructed = self._reconstruct_semantic_replay_authority(
            graph_state=next_state,
            bindings=(*prior_bindings, *bindings),
            pending_request=request,
        )
        projection_records: tuple[CanonicalMemoryRecord, ...] = ()
        projection_preconditions: tuple[MemoryPlanePrecondition, ...] = ()
        if batch is not None:
            if graph_delta is None or not isinstance(request, CommittedGroupAtomicWriteRequest):
                raise PreplanningStoreError("projection publication has no committed graph authority")
            try:
                (
                    temporal_projections,
                    trust_projections,
                    temporal_policy_fingerprint,
                    trust_policy_fingerprint,
                    arbitration_as_of,
                ) = projection_records_from_replay_state(
                    next_state,
                    active_temporal=(
                        self._projection_history.active_temporal_authority()
                        if current_projection_bindings
                        else None
                    ),
                    active_trust=(
                        self._projection_history.active_trust_authority()
                        if current_projection_bindings
                        else None
                    ),
                    active_temporal_policy=(
                        terminal_group_closure.terminal.arbitration_policy_bundle.temporal_policy
                        if current_projection_bindings
                        and terminal_group_closure is not None
                        and terminal_group_closure.terminal.arbitration_policy_bundle
                        is not None
                        else None
                    ),
                    active_trust_policy=(
                        terminal_group_closure.terminal.arbitration_policy_bundle.trust_policy
                        if current_projection_bindings
                        and terminal_group_closure is not None
                        and terminal_group_closure.terminal.arbitration_policy_bundle
                        is not None
                        else None
                    ),
                )
                # Terminal callers seal host callback output during the
                # side-effect-free preflight.  Do not invoke a host callback
                # after lease/checkpoint mutation.  `prepare` below still
                # independently derives contest/scope and binds every current
                # pointer/authority record as a CAS precondition.
                derived_conflict_authority = request.semantic_conflict_authority
                if derived_conflict_authority is None:
                    derived_conflict_authority = (
                        self._projection_history.resolve_semantic_conflict_authority(
                            temporal_projections=temporal_projections,
                            trust_projections=trust_projections,
                        )
                    )
                prepared_projection = self._projection_history.prepare(
                    ProjectionCommitRequest(
                        repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
                        operation_id=batch.transaction_group_id,
                        graph_revision=next_state.graph_revision,
                        event_batch_sequence=batch.log_position.sequence,
                        event_batch_digest=batch.source_event_batch_digest,
                        complete_read_set_digest=(request.expected_effective_read_set_digest),
                        writer_epoch=(request.writer_commit_binding.expected_writer_epoch),
                        base_snapshot_token=prior.graph_state.state_digest,
                        temporal_policy_fingerprint=temporal_policy_fingerprint,
                        trust_policy_fingerprint=trust_policy_fingerprint,
                        arbitration_as_of=arbitration_as_of,
                        temporal_projections=temporal_projections,
                        trust_projections=trust_projections,
                        semantic_conflict_authority=derived_conflict_authority,
                    ),
                    capability=self._write_capability,
                    authorization=authorization,
                )
                prepared_catch_up = self._policy_migration.prepare_write_catch_up(
                    temporal_projections=temporal_projections,
                    trust_projections=trust_projections,
                    trust_decay_command_digests=(
                        prepared_projection.publication.trust.generation.canonical_decay_command_digests
                    ),
                    graph_revision=next_state.graph_revision,
                    graph_delta_digest=graph_delta.delta_digest,
                    ledger_position=batch.log_position.sequence,
                    watermark=batch.source_event_batch_digest,
                    complete_read_set_digest=(request.expected_effective_read_set_digest),
                )
            except (
                PolicyMigrationError,
                ProjectionHistoryError,
                ProjectionSchedulerError,
            ) as exc:
                raise PreplanningStoreError("canonical semantic projection publication is invalid") from exc
            projection_records = (
                *prepared_projection.records,
                *prepared_catch_up.records,
            )
            projection_preconditions = (
                *prepared_projection.preconditions,
                *prepared_catch_up.preconditions,
            )
            projection_bindings = prepared_projection.publication.replay_bindings
            conflict_binding = (
                self._projection_history.semantic_conflict_replay_binding(
                    pending_records=prepared_projection.records,
                )
            )
        else:
            projection_bindings = current_projection_bindings
            conflict_binding = self._projection_history.semantic_conflict_replay_binding()
        checkpoint = None
        watermark_batch = (
            batch
            if batch is not None
            else (prior.latest_checkpoint.watermark_batch if prior.latest_checkpoint is not None else None)
        )
        if watermark_batch is not None:
            checkpoint = create_replay_checkpoint(
                state=next_state,
                watermark_batch=watermark_batch,
                writer_epoch=request.writer_commit_binding.expected_writer_epoch,
                authority=self._checkpoint_resume_authority,
                created_at=self._now(),
                reconstructed_replay_authority_digest=reconstructed.authority_digest,
                projection_history_bindings=projection_bindings,
                semantic_conflict_replay_binding=conflict_binding,
            )
        aggregate = advance_semantic_replay_authority(
            prior,
            graph_state=next_state,
            member_bindings=bindings,
            reconstructed_authority_digest=reconstructed.authority_digest,
            latest_checkpoint=checkpoint,
            projection_history_bindings=projection_bindings,
            semantic_conflict_replay_binding=conflict_binding,
        )
        now = self._now()
        records: list[CanonicalMemoryRecord] = []
        if batch is not None:
            if not isinstance(request, CommittedGroupAtomicWriteRequest):
                raise PreplanningStoreError("semantic event request type is invalid")
            records.extend((_semantic_event_batch_record(batch, now), _semantic_replay_state_record(next_state, now)))
            assert terminal_group_closure is not None and graph_delta is not None
            records.extend(
                self._identity_reservation_records(
                    terminal_group_closure.terminal,
                    graph_delta=graph_delta,
                    operation_fence_id=request.operation_fence_binding.operation_fence_id,
                    expected_graph_revision=request.expected_graph_revision,
                    timestamp=now,
                )
            )
            reference_record = self._memory_plane.get_record(_reference_integrity_ledger_id())
            if reference_record is not None:
                from memorii.core.memory_evolution.reference_integrity import (
                    advance_reference_integrity,
                )

                try:
                    prior_reference_snapshot = self.reference_integrity_snapshot()
                    reference_snapshot = advance_reference_integrity(
                        prior_reference_snapshot,
                        prior_state=prior_state,
                        next_state=next_state,
                        operation_id=graph_delta.operation_id,
                        completed_at=now,
                    )
                    self._validate_planned_identity_reference_mutations(
                        terminal_group_closure.terminal,
                        graph_delta=graph_delta,
                        operation_fence_id=(
                            request.operation_fence_binding.operation_fence_id
                        ),
                        graph_revision_before=request.expected_graph_revision,
                        graph_revision_after=request.graph_revision_after,
                        committed_at=batch.events[0].timestamp,
                        prior_reference_snapshot=prior_reference_snapshot,
                        next_reference_snapshot=reference_snapshot,
                    )
                except ValueError as exc:
                    raise PreplanningStoreError("reference integrity ledger advance failed") from exc
                records.append(_reference_integrity_ledger_record(reference_snapshot, now))
        records.extend(
            (
                _semantic_replay_authority_record(aggregate, now),
                _semantic_checkpoint_lifecycle_record(self._checkpoint_resume_authority, now),
                _semantic_registry_history_record(self._event_schema_registry_history, now),
            )
        )
        event_records = tuple(records)
        canonical_records = (*event_records, *projection_records)
        return (
            canonical_records,
            (
                *self._semantic_authority_record_preconditions(event_records, require_unfrozen=batch is not None),
                *projection_preconditions,
            ),
        )

    def _validate_planned_identity_reference_mutations(
        self,
        terminal,
        *,
        graph_delta,
        operation_fence_id: str,
        graph_revision_before: str,
        graph_revision_after: str,
        committed_at: datetime,
        prior_reference_snapshot,
        next_reference_snapshot,
    ) -> None:
        from memorii.core.memory_evolution.graph_planning import (
            MaterializedPlanningReferenceLedgerMutation,
            PlanningCommitValues,
            materialize_frozen_identity_graph_plan,
            materialize_frozen_identity_reference_mutations,
        )

        candidate_by_id = {item.candidate_id: item for item in terminal.candidates}
        analysis_by_id = {
            item.candidate_id: item for item in terminal.source_analyses
        }
        expected: list[MaterializedPlanningReferenceLedgerMutation] = []
        planned_keys: set[tuple[str, str]] = set()
        for sealed in terminal.sealed_operations:
            if sealed.kind != "identity":
                continue
            artifact = self.get_identity_graph_planning_artifact(
                operation_id=sealed.operation_id,
                sealed_operation_digest=sealed.sealed_operation_digest,
                candidate_digest=candidate_by_id[
                    sealed.candidate_id
                ].candidate_digest,
                source_analysis_digest=analysis_by_id[
                    sealed.candidate_id
                ].analysis_digest,
            )
            if artifact is None:
                raise ValueError("frozen identity planning artifact is absent")
            if artifact.accepted_operation_artifact.operation_fence_id != (
                operation_fence_id
            ):
                raise ValueError("frozen identity planning fence mismatch")
            commit_values = PlanningCommitValues(
                transaction_group_id=graph_delta.operation_id,
                graph_revision_before=graph_revision_before,
                graph_revision_after=graph_revision_after,
                committed_at=committed_at,
            )
            durable_records, _ = materialize_frozen_identity_graph_plan(
                artifact,
                commit_values=commit_values,
            )
            planned_keys.update(
                (item.payload_record_kind, item.record_id)
                for item in durable_records
            )
            expected.extend(
                materialize_frozen_identity_reference_mutations(
                    artifact,
                    commit_values=commit_values,
                    durable_records=durable_records,
                )
            )
        if not planned_keys:
            return
        appended = next_reference_snapshot.entries[
            len(prior_reference_snapshot.entries) :
        ]
        actual = tuple(
            MaterializedPlanningReferenceLedgerMutation(
                graph_revision=item.graph_revision,
                operation_id=item.operation_id,
                change=item.change,
                record_kind=item.record_kind,
                record_id=item.record_id,
                reference_path=item.reference_path,
                target=item.target,
                base_record_digest=item.base_record_digest,
            )
            for item in appended
            if (item.record_kind, item.record_id) in planned_keys
        )

        def mutation_key(item: MaterializedPlanningReferenceLedgerMutation):
            return (
                item.operation_id,
                item.change,
                item.record_kind,
                item.record_id,
                item.reference_path,
                item.target.kind,
                item.target.target_id,
                item.base_record_digest,
                item.graph_revision,
            )

        expected_keys = tuple(sorted(map(mutation_key, expected)))
        actual_keys = tuple(sorted(map(mutation_key, actual)))
        if expected_keys != actual_keys:
            missing = tuple(sorted(set(expected_keys) - set(actual_keys)))
            unexpected = tuple(sorted(set(actual_keys) - set(expected_keys)))
            raise ValueError(
                "planned reference ledger materialization mismatch:"
                f"missing={missing!r}:unexpected={unexpected!r}"
            )

    def _identity_reservation_records(
        self,
        terminal,
        *,
        graph_delta,
        operation_fence_id: str,
        expected_graph_revision: str,
        timestamp: datetime,
    ) -> tuple[CanonicalMemoryRecord, ...]:
        """Materialize allocation collision coordinates in the event transaction."""

        candidate_by_id = {item.candidate_id: item for item in terminal.candidates}
        analysis_by_id = {item.candidate_id: item for item in terminal.source_analyses}
        graph_entity_ids = {
            item.entity_revision_id
            for item in graph_delta.graph_records
            if item.record_kind == "entity_revision"
        }
        records: list[CanonicalMemoryRecord] = []
        for sealed in terminal.sealed_operations:
            if sealed.kind != "identity":
                continue
            artifact = self.get_accepted_identity_operation(
                operation_id=sealed.operation_id,
                sealed_operation_digest=sealed.sealed_operation_digest,
                candidate_digest=candidate_by_id[sealed.candidate_id].candidate_digest,
                source_analysis_digest=analysis_by_id[sealed.candidate_id].analysis_digest,
            )
            if artifact is None or artifact.operation_fence_id != operation_fence_id:
                raise PreplanningStoreError("accepted identity reservation authority is absent")
            for reservation in artifact.successor_reservations:
                extension = reservation.collision_read_set_extension
                if (
                    extension.operation_fence_id != operation_fence_id
                    or extension.graph_revision != expected_graph_revision
                    or reservation.planned_identity.entity_revision_id not in graph_entity_ids
                ):
                    raise PreplanningStoreError("identity reservation read set is stale")
                for intent in reservation.expected_absent_write_intents:
                    planned_record = _graph_identity_reservation_record(
                        record_key=intent.record_key,
                        reservation_digest=reservation.reservation_digest,
                        operation_id=sealed.operation_id,
                        operation_fence_id=operation_fence_id,
                        timestamp=timestamp,
                    )
                    current = self._memory_plane.get_record(
                        planned_record.memory_id
                    )
                    if current is not None:
                        if current.content != planned_record.content:
                            raise PreplanningStoreError(
                                "identity reservation is owned by another operation"
                            )
                        planned_record = current
                    records.append(planned_record)
        records.sort(key=lambda item: item.memory_id)
        ids = tuple(item.memory_id for item in records)
        if len(ids) != len(set(ids)):
            raise PreplanningStoreError("identity reservation coordinates collide")
        return tuple(records)

    def _semantic_authority_record_preconditions(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        require_unfrozen: bool,
    ) -> tuple[MemoryPlanePrecondition, ...]:
        """Bind an authority rewrite to the exact closure that was validated."""

        preconditions: list[MemoryPlanePrecondition] = []
        if require_unfrozen and self._uses_default_semantic_freeze_guard:
            # The corruption publisher and event admission contend on this
            # store-owned coordinate. Whichever transaction commits first is
            # the linearization winner; an affected event can never slip in
            # after the durable freeze.
            preconditions.append(RecordAbsentPrecondition(memory_id=_semantic_integrity_control_id()))
        for record in records:
            current = self._memory_plane.get_record(record.memory_id)
            if current is None:
                preconditions.append(RecordAbsentPrecondition(memory_id=record.memory_id))
            else:
                if (
                    record.source_kind
                    == "semantic_ingestion_graph_identity_reservation"
                    and current.content != record.content
                ):
                    raise PreplanningStoreError(
                        "identity reservation authority differs"
                    )
                if (
                    record.memory_id == _semantic_checkpoint_lifecycle_id()
                    and current.content.get("authority_digest")
                    != self._checkpoint_resume_authority.lifecycle.authority_digest
                ):
                    try:
                        from memorii.core.semantic_ingestion.event_replay import (
                            decode_replay_checkpoint_lifecycle,
                        )

                        prior_lifecycle = decode_replay_checkpoint_lifecycle(
                            bytes.fromhex(str(current.content["canonical_hex"]))
                        )
                    except (KeyError, TypeError, ValueError) as exc:
                        raise PreplanningStoreError("checkpoint lifecycle authority is corrupt") from exc
                    next_lifecycle = self._checkpoint_resume_authority.lifecycle
                    if (
                        next_lifecycle.authority_revision != prior_lifecycle.authority_revision + 1
                        or next_lifecycle.predecessor_authority_digest != prior_lifecycle.authority_digest
                    ):
                        raise PreplanningStoreError(
                            "checkpoint lifecycle authority is stale, substituted, or rolled back"
                        )
                if record.memory_id == _semantic_registry_history_id():
                    try:
                        from memorii.core.semantic_ingestion.event_replay import (
                            decode_event_schema_registry_history,
                        )

                        prior_history = decode_event_schema_registry_history(
                            bytes.fromhex(str(current.content["canonical_hex"]))
                        )
                    except (KeyError, TypeError, ValueError) as exc:
                        raise PreplanningStoreError("semantic registry history is corrupt") from exc
                    if (
                        self._event_schema_registry_history.registries[: len(prior_history.registries)]
                        != prior_history.registries
                    ):
                        raise PreplanningStoreError("semantic registry history is stale, substituted, or rolled back")
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=record.memory_id,
                        expected_digest=record_digest(current),
                    )
                )
        return tuple(preconditions)

    def _recover_published_generation(
        self,
        request: AtomicGenerationRequest,
    ) -> tuple[AtomicGenerationMember, ...] | None:
        """Recover an exact raced/lost-ack generation even after later progress."""
        self._writers.require_current(request.writer_commit_binding)
        control = _control_from_record(self._required_control_record(request.operation_fence_binding))
        if (
            control.operation_fence != request.operation_fence_binding
            or control.writer_binding != request.writer_commit_binding
        ):
            return None
        generation = request.expected_operation_generation + 1
        manifest = self._memory_plane.get_record(_generation_manifest_id(_control_namespace(control), generation))
        if manifest is None or manifest.source_kind != "semantic_ingestion_generation_manifest":
            return None
        if manifest.content.get("request_digest") != request.request_digest:
            return None
        members = self._read_generation_members(control, generation)
        return members if members == request.members else None

    def _recover_exact_generation_if_current(
        self, request: AtomicGenerationRequest
    ) -> tuple[AtomicGenerationMember, ...] | None:
        """Recover only after revalidating every mutable write authority."""

        control = self._require_current_generation_authority(request, allow_terminal_recovery=True)
        if control.last_request_digest == request.request_digest:
            return self._read_generation_members(control, control.generation)
        return None

    def _require_current_generation_authority(
        self,
        request: AtomicGenerationRequest,
        *,
        allow_terminal_recovery: bool = False,
    ) -> PreplanningOperationControl:
        """Return the exact control snapshot only while all mutable authority is current."""

        self._writers.require_current(request.writer_commit_binding)
        control = _control_from_record(self._required_control_record(request.operation_fence_binding))
        if (
            control.operation_fence != request.operation_fence_binding
            or control.writer_binding != request.writer_commit_binding
        ):
            raise PreplanningStoreError("generation does not bind the admitted operation")
        if request.request_digest != generation_request_digest(request):
            raise PreplanningStoreError("generation request digest is invalid")
        active_lease_matches = (
            control.lease is not None
            and self.lease_binding(control) == request.operation_lease_binding
            and request.operation_lease_binding.lease_expires_at > self._now()
        )
        terminal_recovery_matches = (
            allow_terminal_recovery
            and control.state == "terminal"
            and control.last_request_digest == request.request_digest
            and control.last_completed_lease_binding_digest == request.operation_lease_binding.binding_digest
        )
        if not active_lease_matches and not terminal_recovery_matches:
            raise PreplanningStoreError("generation lease is stale or expired")
        return control

    def _read_generation_members(
        self, control: PreplanningOperationControl, generation: int
    ) -> tuple[AtomicGenerationMember, ...]:
        manifest = self._memory_plane.get_record(_generation_manifest_id(_control_namespace(control), generation))
        if (
            manifest is None
            or manifest.source_kind != "semantic_ingestion_generation_manifest"
            or manifest.content.get("semantic_ingestion_kind") != "generation_manifest"
            or manifest.content.get("generation") != generation
        ):
            if self._is_bootstrap_v3_ready_generation(control, generation):
                return ()
            if control.group_result_digests:
                # The bootstrap graph plane advanced this control through its
                # own group-commit grammar, which leaves no generic manifest
                # at the generations it crosses; the generic terminal lease
                # session must not decode graph-owned generations.
                return ()
            graph_manifest = self._memory_plane.get_record(
                _bootstrap_graph_v3_manifest_id(_control_namespace(control), generation)
            )
            if (
                graph_manifest is not None
                and graph_manifest.source_kind
                == "semantic_ingestion_bootstrap_graph_v3_manifest"
                and graph_manifest.content.get("semantic_ingestion_kind")
                in {
                    "bootstrap_graph_v3_manifest",
                    "bootstrap_graph_v3_terminal_manifest",
                }
            ):
                # Bootstrap graph checkpoints and terminal publications have
                # a disjoint member grammar and their own generation scheme
                # (a record written while the control sits at one generation
                # lands at a graph-derived generation number, not
                # control_generation + 1); the generic terminal lease
                # session must not decode them.  The manifest id is
                # generation-keyed and the source and kind are checked
                # above, which is the binding this escape hatch needs.
                return ()
            raise PreplanningStoreError("committed generation manifest is absent")
        try:
            members = tuple(AtomicGenerationMember.model_validate(item) for item in manifest.content["members"])
        except (KeyError, ValueError, TypeError) as exc:
            raise PreplanningStoreError("committed generation manifest is corrupt") from exc
        if len({member.member_id for member in members}) != len(members):
            raise PreplanningStoreError("committed generation member identities collide")
        for member in members:
            if sha256(member.canonical_payload).hexdigest() != member.payload_digest:
                raise PreplanningStoreError("committed generation member digest is corrupt")
            record = self._memory_plane.get_record(
                _generation_member_id(_control_namespace(control), generation, member.member_id)
            )
            if (
                record is None
                or record.source_kind != "semantic_ingestion_generation_member"
                or record.content.get("semantic_ingestion_kind") != "generation_member"
                or record.content.get("member") != member.model_dump(mode="json")
            ):
                raise PreplanningStoreError("committed generation is incomplete")
        return members

    def _is_bootstrap_v3_ready_generation(
        self, control: PreplanningOperationControl, generation: int
    ) -> bool:
        """Recognize the manifest-free V3 recovery transition by its sealed index."""
        namespace = _control_namespace(control)
        for record in self._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
        ):
            content = record.content
            snapshot = content.get("control_snapshot")
            if (
                content.get("state") == "claimed"
                and isinstance(snapshot, dict)
                and snapshot.get("control_record", {}).get("operation_generation") == generation
                and snapshot.get("control_record", {}).get("operation_fence_digest")
                == control.operation_fence.binding_digest
            ):
                return True
            if (
                content.get("state") == "found"
                and content.get("namespace_id") == namespace
                and content.get("publication_operation_generation") == generation + 1
            ):
                return True
        return False

    def _control_by_operation_fence_id(self, operation_fence_id: str) -> PreplanningOperationControl:
        controls: list[PreplanningOperationControl] = []
        for record in self._memory_plane.list_records():
            if record.source_kind != "semantic_ingestion_preplanning_control":
                continue
            try:
                control = _control_from_record(record)
            except PreplanningStoreError:
                continue
            if control.operation_fence.operation_fence_id == operation_fence_id:
                controls.append(control)
        if len(controls) != 1:
            raise PreplanningStoreError("semantic replay operation fence is absent or ambiguous")
        return controls[0]

    def _replace_control(
        self,
        prior: CanonicalMemoryRecord,
        control: PreplanningOperationControl,
        writer_record: CanonicalMemoryRecord,
        *,
        writer_binding: SemanticWriterCommitBinding,
        expected_lease: PreplanningLease | None,
        require_active_lease: bool = False,
    ) -> None:
        updated = _control_record(control, prior.timestamp)
        preconditions: list[MemoryPlanePrecondition] = [
            RecordDigestPrecondition(memory_id=prior.memory_id, expected_digest=record_digest(prior)),
            RecordDigestPrecondition(memory_id=writer_record.memory_id, expected_digest=record_digest(writer_record)),
        ]
        if expected_lease is not None:
            preconditions.append(
                RecordFencePrecondition(
                    memory_id=prior.memory_id,
                    expected_fence=MemoryRecordFence(
                        execution_token=expected_lease.execution_token, ownership_epoch=expected_lease.ownership_epoch
                    ),
                )
            )
        self._memory_plane.conditionally_write_records(
            (updated,),
            preconditions=tuple(preconditions),
            authorization=self._writers._authorize_atomic(
                writer_binding,
                capability=self._write_capability,
                lease_expires_at=(
                    expected_lease.expires_at if expected_lease is not None and require_active_lease else None
                ),
                server_now=self._now if expected_lease is not None and require_active_lease else None,
            ),
        )

    def _validate_handoff(self, admission: SourceAdmissionAccepted, fence: OperationFenceBinding) -> None:
        if (
            admission.source_id != fence.source_id
            or admission.source_digest != fence.source_digest
            or admission.delivery_identity != fence.delivery_identity
        ):
            raise PreplanningStoreError("operation fence does not bind the admitted source")
        source = self._memory_plane.get_record(admission.source_id)
        index = self._memory_plane.get_record(
            f"semantic_ingestion:admission:{admission.delivery_identity.delivery_key_digest}"
        )
        if (
            source is None
            or index is None
            or source_admission_source_digest(source) != admission.source_digest
            or index.source_kind != "semantic_ingestion_admission_index"
            or sha256(encode_typed_value(index.content)).hexdigest() != admission.admission_index_digest
            or index.content.get("operation_fence_binding") != fence.model_dump(mode="json")
            or index.content.get("principal_binding_digest") != fence.delivery_principal_binding_digest
            or index.content.get("delivery_key_digest") != fence.delivery_key_digest
            or index.content.get("tenant_partition_id") != admission.required_outcome_scopes.tenant_partition_id
            or tuple(index.content.get("required_scopes", ())) != admission.required_outcome_scopes.scopes
            or index.content.get("required_scope_set_digest")
            != admission.required_outcome_scopes.required_scope_set_digest
        ):
            raise PreplanningStoreError("source handoff is not already governed-source admission-admitted")
        admitted_epoch = index.content.get("admitted_writer_epoch")
        admitted_digest = index.content.get("writer_admission_digest")
        if admitted_epoch is not None:
            current = self._writers.current()
            if admitted_epoch != current.writer_epoch or admitted_digest != current.admission_digest:
                raise PreplanningStoreError("source admission belongs to a stale writer epoch")

    def _recover_publication(
        self,
        existing: CanonicalMemoryRecord,
        admission: SourceAdmissionAccepted,
        fence: OperationFenceBinding,
        binding: SemanticWriterCommitBinding,
    ) -> PreplanningPublication:
        control = _control_from_record(existing)
        if control.operation_fence != fence or control.writer_binding != binding:
            raise PreplanningStoreError("operation is already bound differently")
        publication = _publication(
            control,
            self._read_artifact_bytes(control, "introduction"),
            self._read_artifact_bytes(control, "index"),
            self._read_artifact_bytes(control, "closure"),
        )
        if publication != _publication(control):
            raise PreplanningStoreError("preplanning artifact index or closure is inconsistent")
        return publication

    def _read_artifact_bytes(self, control: PreplanningOperationControl, kind: str) -> bytes:
        record = self._memory_plane.get_record(_artifact_id(_control_namespace(control), kind))
        encoded = None if record is None else record.content.get("canonical_bytes_base64")
        if not isinstance(encoded, str):
            raise PreplanningStoreError("preplanning artifact closure is incomplete")
        if record is None:
            raise PreplanningStoreError("preplanning artifact closure is incomplete")
        try:
            canonical_bytes = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise PreplanningStoreError("preplanning artifact closure is corrupt") from exc
        if (
            base64.b64encode(canonical_bytes).decode("ascii") != encoded
            or record.content.get("digest") != sha256(canonical_bytes).hexdigest()
        ):
            raise PreplanningStoreError("preplanning artifact closure is corrupt")
        return canonical_bytes

    def _required_control_record(self, operation_fence: OperationFenceBinding) -> CanonicalMemoryRecord:
        record = self._memory_plane.get_record(_control_id(operation_fence))
        if record is None:
            record = self._memory_plane.get_record(_legacy_control_id(operation_fence))
        if record is None:
            raise PreplanningStoreError("preplanning operation is absent")
        # A legacy raw-ID namespace is only a storage-family compatibility
        # fallback.  It is never an authority: the retained immutable fence
        # must still match exactly before a caller can observe or mutate it.
        if _control_from_record(record).operation_fence != operation_fence:
            raise PreplanningStoreError("preplanning operation is absent")
        return record

    def _required_control_record_by_operation_id(self, operation_id: str) -> CanonicalMemoryRecord:
        """Compatibility path for lease acquisition; ambiguity fails closed."""

        candidates = tuple(
            record
            for record in self._memory_plane.list_records()
            if record.source_kind == "semantic_ingestion_preplanning_control"
            and record.content.get("control", {}).get("operation_fence", {}).get("operation_id") == operation_id
        )
        if len(candidates) != 1:
            raise PreplanningStoreError("preplanning operation is absent or ambiguous")
        return candidates[0]

    def _lease_control_record(
        self, *, operation_fence: OperationFenceBinding | None, operation_id: str | None
    ) -> CanonicalMemoryRecord:
        """Use the immutable fence coordinate; legacy IDs work only when unique."""

        if operation_fence is not None:
            if operation_id is not None and operation_id != operation_fence.operation_id:
                raise PreplanningStoreError("operation ID does not match operation fence")
            return self._required_control_record(operation_fence)
        if operation_id is None:
            raise PreplanningStoreError("operation fence is required")
        return self._required_control_record_by_operation_id(operation_id)


def _operation_namespace(operation_fence: OperationFenceBinding) -> str:
    return operation_fence.operation_fence_id


def _control_namespace(control: PreplanningOperationControl) -> str:
    return control.persistence_namespace_id or control.operation_fence.operation_id


def _control_id(operation_fence: OperationFenceBinding) -> str:
    return f"semantic_ingestion:operation:{_operation_namespace(operation_fence)}"


def _authorization_authority_id(authority_scope_id: str) -> str:
    return f"semantic_ingestion:authorization:{sha256(authority_scope_id.encode('utf-8')).hexdigest()}"


def _authorization_authority_record(
    authority: SemanticAuthorizationAuthorityRecord,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=authority.authority_record_id,
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "authorization_authority",
            "authority": authority.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_authorization_authority",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _authorization_authority_from_record(
    record: CanonicalMemoryRecord,
) -> SemanticAuthorizationAuthorityRecord:
    if record.source_kind != "semantic_ingestion_authorization_authority":
        raise PreplanningStoreError("authorization authority record kind is invalid")
    try:
        return SemanticAuthorizationAuthorityRecord.model_validate(record.content["authority"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PreplanningStoreError("authorization authority record is corrupt") from exc


def _authorization_precondition(
    record: CanonicalMemoryRecord,
    authority: SemanticAuthorizationAuthorityRecord,
) -> AuthorizationReadSetPrecondition:
    return AuthorizationReadSetPrecondition(
        authority_record_id=record.memory_id,
        expected_authority_revision=authority.authority_revision,
        expected_coordinates_digest=authority.coordinates_digest,
        expected_record_digest=record_digest(record),
    )


def _legacy_control_id(operation_fence: OperationFenceBinding) -> str:
    return f"semantic_ingestion:operation:{operation_fence.operation_id}"


def _artifact_id(namespace_id: str, kind: str) -> str:
    return f"semantic_ingestion:artifact:{namespace_id}:{kind}"


def _generation_member_id(namespace_id: str, generation: int, member_id: str) -> str:
    return f"semantic_ingestion:generation:{namespace_id}:{generation}:{member_id}"


def _generation_manifest_id(namespace_id: str, generation: int) -> str:
    return f"semantic_ingestion:generation:{namespace_id}:{generation}:manifest"


def _bootstrap_graph_v3_member_id(namespace_id: str, generation: int, member_id: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:member:" + namespace_id + ":" + str(generation) + ":" + sha256(member_id.encode("utf-8")).hexdigest()


def _bootstrap_graph_v3_group_commit_primary_id(
    source_operation_id: str, transaction_group_id: str,
    operation_ids: tuple[str, ...], request_ctv_digest: str,
) -> str:
    key = encode_typed_value((source_operation_id, transaction_group_id, operation_ids, request_ctv_digest))
    return "semantic_ingestion:bootstrap-graph-v3:group-commit:" + sha256(key).hexdigest()


def _bootstrap_graph_v3_group_commit_fanout_id(
    source_operation_id: str, transaction_group_id: str, member_operation_id: str,
    request_ctv_digest: str,
) -> str:
    key = encode_typed_value((source_operation_id, transaction_group_id, member_operation_id, request_ctv_digest))
    return "semantic_ingestion:bootstrap-graph-v3:group-commit-fanout:" + sha256(key).hexdigest()


def _bootstrap_graph_v3_group_commit_primary_record(
    primary_id: str, request: object, reload: object, *, timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.contracts import encode_semantic_contract

    return CanonicalMemoryRecord(
        memory_id=primary_id, domain=MemoryDomain.EXECUTION, text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_group_commit_primary",
            "request_hex": encode_semantic_contract(request).hex(),
            "reload_hex": encode_semantic_contract(reload).hex(),
        }, status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_group_commit_fanout_record(
    *, source_operation_id: str, transaction_group_id: str, operation_ids: tuple[str, ...],
    member_operation_id: str, request_ctv_digest: str, primary_id: str,
    reload_digest: str, timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_group_commit_fanout_id(
            source_operation_id, transaction_group_id, member_operation_id, request_ctv_digest,
        ), domain=MemoryDomain.EXECUTION, text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_group_commit_fanout",
            "source_operation_id": source_operation_id,
            "transaction_group_id": transaction_group_id,
            "operation_ids": operation_ids,
            "member_operation_id": member_operation_id,
            "request_ctv_digest": request_ctv_digest,
            "primary_id": primary_id,
            "reload_digest": reload_digest,
        }, status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_fanout",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_group_commit_effect_record(
    *, primary_id: str, operation_id: str, kind: str, payload: bytes, timestamp: datetime,
    carrier_digest: str | None = None,
) -> CanonicalMemoryRecord:
    digest = sha256(payload).hexdigest()
    return CanonicalMemoryRecord(
        memory_id="semantic_ingestion:bootstrap-graph-v3:group-commit-effect:" + sha256(
            encode_typed_value((primary_id, operation_id, kind, digest))
        ).hexdigest(), domain=MemoryDomain.EXECUTION, text="",
        content={"semantic_ingestion_kind": "bootstrap_graph_v3_group_commit_effect", "primary_id": primary_id,
                 "operation_id": operation_id, "kind": kind, "payload_hex": payload.hex(),
                 "payload_digest": digest, "carrier_digest": carrier_digest or digest},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_effect",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_group_commit_request_from_record(record: CanonicalMemoryRecord) -> object:
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapGraphGroupCommitRequestV3,
        decode_semantic_contract,
    )

    try:
        raw = bytes.fromhex(record.content["request_hex"])
        request = decode_semantic_contract(raw, BootstrapGraphGroupCommitRequestV3)
    except (KeyError, TypeError, ValueError) as exc:
        raise PreplanningStoreError("bootstrap graph group commit primary is corrupt") from exc
    return request


def _bootstrap_graph_v3_group_commit_reload_from_record(record: CanonicalMemoryRecord, request: object) -> object:
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapGraphGroupCommitReloadV3,
        decode_semantic_contract,
        encode_semantic_contract,
    )

    try:
        raw = bytes.fromhex(record.content["reload_hex"])
        reload = decode_semantic_contract(raw, BootstrapGraphGroupCommitReloadV3)
    except (KeyError, TypeError, ValueError) as exc:
        raise PreplanningStoreError("bootstrap graph group commit primary is corrupt") from exc
    if (
        record.source_kind != "semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
        or encode_semantic_contract(reload) != raw
        or reload.source_operation_id != request.source_operation_id
        or reload.transaction_group_id != request.transaction_group_id
        or reload.operation_ids != request.operation_ids
        or reload.request_ctv_digest != request.request_ctv_digest
    ):
        raise PreplanningStoreError("bootstrap graph group commit primary is substituted")
    return reload


def _bootstrap_graph_v3_manifest_id(namespace_id: str, generation: int) -> str:
    return f"semantic_ingestion:bootstrap-graph-v3:manifest:{namespace_id}:{generation}"


def _bootstrap_graph_v3_idempotency_id(write_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:idempotency:" + write_digest


def _bootstrap_graph_v3_authority_id(projection_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:authority:" + projection_digest


def _bootstrap_canonical_identity_authority_id(reload_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:canonical-identity-authority:" + reload_digest


def _bootstrap_graph_v3_authority_index_id(
    recovery_key_digest: str, projection_digest: str,
) -> str:
    return (
        "semantic_ingestion:bootstrap-graph-v3:authority-index:"
        + recovery_key_digest + ":" + projection_digest
    )


def _bootstrap_graph_v3_retry_id(request_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:retry:" + request_digest


def _bootstrap_graph_v3_epoch_id(request_core_digest: str, epoch: int) -> str:
    return f"semantic_ingestion:bootstrap-graph-v3:epoch:{request_core_digest}:{epoch}"


def _bootstrap_graph_v3_epoch_head_id(request_core_digest: str) -> str:
    return f"semantic_ingestion:bootstrap-graph-v3:epoch-head:{request_core_digest}"


def _bootstrap_graph_v3_transition_id(transition_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:epoch-transition:" + transition_digest


def _bootstrap_graph_v3_terminal_locator_id(locator_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:terminal-locator:" + locator_digest


def _bootstrap_graph_v3_terminal_request_id(request_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:terminal-request:" + request_digest


def _bootstrap_graph_v3_terminal_recovery_id(recovery_key_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:terminal-recovery:" + recovery_key_digest


def _bootstrap_graph_v3_retry_recovery_id(operation_fence_binding_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:retry-recovery:" + operation_fence_binding_digest


def _bootstrap_graph_v3_terminal_control_id(locator_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:terminal-control:" + locator_digest


def _bootstrap_graph_v3_terminal_identity_id(locator_digest: str) -> str:
    return "semantic_ingestion:bootstrap-graph-v3:terminal-identity:" + locator_digest


@dataclass(frozen=True)
class _TerminalAuthorityRequest:
    """The common current-authority validator's deliberately small view."""

    request: object

    @property
    def control_epoch_digest(self) -> str:
        return self.request.control_epoch.epoch_digest

    @property
    def operation_fence_binding(self) -> OperationFenceBinding:
        return self.request.operation_fence_binding

    @property
    def operation_lease_binding(self) -> OperationLeaseBinding:
        return self.request.operation_lease_binding

    @property
    def writer_commit_binding(self) -> SemanticWriterCommitBinding:
        return self.request.writer_commit_binding

    @property
    def write_digest(self) -> str:
        return self.request.publication_request_digest


def _bootstrap_graph_v3_terminal_payloads(*, request: object, group_result_type: type,
                                          canonical_result_type: type) -> dict[str, tuple[object, ...]]:
    """Materialize the sealed nine-kind terminal grammar in its declared order."""
    group_results = tuple(
        group_result_type.model_validate(item.model_dump(mode="python"))
        for item in request.ordered_group_result_constructions
    )
    if tuple(item.transaction_group_id for item in group_results) != request.final_plan.canonical_group_order:
        raise PreplanningStoreError("bootstrap graph terminal group result order is invalid")
    entry_by_digest = {entry.entry_digest: entry for entry in request.complete_lineage.entries}
    latest_entries = tuple(
        entry_by_digest[digest] for _, digest in request.complete_lineage.latest_entry_by_group
    )
    if tuple(item.transaction_group_id for item in latest_entries) != request.final_plan.canonical_group_order:
        raise PreplanningStoreError("bootstrap graph terminal lineage is incomplete")
    canonical_result = canonical_result_type.create(
        request_digest=request.canonical_source_result_input.request_digest,
        normalization_replay_digest=request.canonical_source_result_input.normalization_replay_digest,
        source_plan_lineage_digest=request.canonical_source_result_input.source_plan_lineage_digest,
        ordered_group_result_digests=tuple(
            item.result_digest
            for item in request.ordered_group_result_constructions
        ),
        canonical_source_result=request.canonical_source_result_input.completed_canonical_source_result,
        control_epoch_digest=request.canonical_source_result_input.control_epoch_digest,
    )
    core = request.handoff_core
    if (
        core.ordered_group_result_digests != tuple(item.result_digest for item in group_results)
        or core.final_source_result_digest != canonical_result.result_digest
        or core.execution_manifest_digest != request.execution_manifest.manifest_digest
    ):
        raise PreplanningStoreError("bootstrap graph terminal handoff closure is substituted")
    return {
        "bootstrap_graph_coordinator_request": (request.coordinator_request,),
        "bootstrap_graph_control_epoch": (request.control_epoch,),
        "bootstrap_graph_dependent_attempt": (request.final_attempt,),
        "bootstrap_transaction_group_plan": (request.final_plan,),
        "bootstrap_source_plan_lineage_entry": request.complete_lineage.entries,
        "ingestion_execution_manifest": (request.execution_manifest,),
        "transaction_group_result": group_results,
        "bootstrap_graph_terminal_handoff": (request.handoff,),
        "bootstrap_graph_canonical_source_result": (canonical_result,),
    }


def _bootstrap_graph_v3_terminal_members(*, request: object, payloads: dict[str, tuple[object, ...]],
                                         member_type: type, encoder: Callable[[object], bytes]) -> tuple[object, ...]:
    digest_field_by_kind = {
        "bootstrap_graph_coordinator_request": "request_digest",
        "bootstrap_graph_control_epoch": "epoch_digest",
        "bootstrap_graph_dependent_attempt": "attempt_digest",
        "bootstrap_transaction_group_plan": "plan_digest",
        "bootstrap_source_plan_lineage_entry": "entry_digest",
        "ingestion_execution_manifest": "manifest_digest",
        "transaction_group_result": "result_digest",
        "bootstrap_graph_canonical_source_result": "result_digest",
    }
    members: list[object] = []
    offsets: dict[str, int] = {}
    for intent in request.publication_intent.member_intents:
        index = offsets.get(intent.kind, 0)
        values = payloads.get(intent.kind, ())
        if index >= len(values):
            raise PreplanningStoreError("bootstrap graph terminal member intent is incomplete")
        payload = values[index]
        offsets[intent.kind] = index + 1
        if intent.kind == "bootstrap_graph_terminal_handoff":
            payload_digest = payload.core.core_digest
        else:
            digest_field = digest_field_by_kind.get(intent.kind)
            payload_digest = getattr(payload, digest_field, None) if digest_field else None
        if payload_digest != intent.construction_input_digest:
            raise PreplanningStoreError("bootstrap graph terminal member intent is substituted")
        canonical_payload = encoder(payload)
        members.append(member_type.create(
            member_id=intent.member_id, kind=intent.kind, canonical_payload=canonical_payload,
            payload_digest=sha256(canonical_payload).hexdigest(),
        ))
    if any(offsets.get(kind, 0) != len(values) for kind, values in payloads.items()):
        raise PreplanningStoreError("bootstrap graph terminal member intent is incomplete")
    return tuple(members)


def _store_checkpoint_authority(
    *,
    registry: SemanticEventSchemaRegistry,
    registry_history: SemanticEventSchemaRegistryHistory,
    signature_authority: CheckpointSignatureAuthority,
    persistence_scope: Literal["ephemeral", "durable"],
    current_time_provider: Callable[[], datetime],
) -> ReplayCheckpointResumeAuthority:
    """Create authority from material owned by the selected store backend."""

    from memorii.core.semantic_ingestion.event_replay import (
        ReplayCheckpointLifecycleState,
        ReplayCheckpointResumeAuthority,
        ReplayCheckpointSigningKey,
        ReplayCheckpointTrustPolicy,
    )

    key = ReplayCheckpointSigningKey.create(
        key_id=signature_authority.key_id,
        issuer_id="semantic-ingestion-store",
        public_key_fingerprint=(signature_authority.public_key_fingerprint),
        valid_from=datetime(1970, 1, 1, tzinfo=UTC),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=1,
        authorized_repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id=_SEMANTIC_EVENT_REPOSITORY_ID,
        authority_revision=1,
        registry=registry,
        registry_history=registry_history,
        trust_policy=policy,
    )
    return ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda key_id: (
            signature_authority if key_id == signature_authority.key_id else None
        ),
        signing_key_id=signature_authority.key_id,
        registry_history=registry_history,
        persistence_scope=persistence_scope,
        current_time_provider=current_time_provider,
    )


def _semantic_event_batch_id(sequence: int) -> str:
    return f"semantic_ingestion:event-authority:batch:{sequence:020d}"


def _semantic_replay_state_id() -> str:
    return "semantic_ingestion:event-authority:state"


def _reference_integrity_ledger_id() -> str:
    return "semantic_ingestion:reference-integrity:ledger"


def _accepted_identity_operation_id(operation_id: str) -> str:
    return "semantic_ingestion:accepted-identity:" + sha256(operation_id.encode()).hexdigest()


def _graph_identity_reservation_id(record_key: str) -> str:
    return "semantic_ingestion:graph-reservation:" + sha256(record_key.encode()).hexdigest()


def _semantic_replay_authority_id() -> str:
    return "semantic_ingestion:event-authority:aggregate"


def _semantic_checkpoint_lifecycle_id() -> str:
    return "semantic_ingestion:event-authority:checkpoint-lifecycle"


def _semantic_registry_history_id() -> str:
    return "semantic_ingestion:event-authority:registry-history"


def _semantic_integrity_control_id() -> str:
    return "semantic_ingestion:event-authority:integrity-control"


def _semantic_integrity_attention_id(revision: int) -> str:
    return f"semantic_ingestion:event-authority:integrity-attention:{revision:020d}"


def _semantic_clean_recovery_request_id(request_digest: str) -> str:
    return f"semantic_ingestion:event-authority:clean-request:{request_digest}"


def _semantic_clean_generation_id(request_digest: str) -> str:
    return f"semantic_ingestion:event-authority:clean-generation:{request_digest}"


def _semantic_clean_generation_status_id(request_digest: str) -> str:
    return f"semantic_ingestion:event-authority:clean-status:{request_digest}"


def _semantic_integrity_digest(domain: bytes, value: object) -> str:
    return sha256(domain + encode_typed_value(value)).hexdigest()


def _nested_semantic_integrity_digests(value: object) -> set[str]:
    if isinstance(value, str):
        if len(value) == 64 and all(character in "0123456789abcdef" for character in value):
            return {value}
        return set()
    if isinstance(value, dict):
        result: set[str] = set()
        for item in value.values():
            result.update(_nested_semantic_integrity_digests(item))
        return result
    if isinstance(value, (tuple, list)):
        result = set()
        for item in value:
            result.update(_nested_semantic_integrity_digests(item))
        return result
    return set()


def _semantic_clean_recovery_request_record(
    request,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_semantic_clean_recovery_request_id(request.request_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "clean_recovery_request",
            "request_digest": request.request_digest,
            "canonical_hex": encode_typed_value(request.model_dump(mode="python")).hex(),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_clean_recovery_request",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_clean_generation_record(
    request_digest: str,
    body: object,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_semantic_clean_generation_id(request_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "clean_generation",
            "request_digest": request_digest,
            "canonical_hex": encode_typed_value(body).hex(),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_clean_generation",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_clean_generation_status_record(
    request_digest: str,
    *,
    clean_generation_digest: str,
    status: Literal["prepared", "activated"],
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_semantic_clean_generation_status_id(request_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "clean_generation_status",
            "request_digest": request_digest,
            "clean_generation_digest": clean_generation_digest,
            "status": status,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_clean_generation_status",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_retained_event_slot_record(
    record: CanonicalMemoryRecord,
    *,
    request_digest: str,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=record.memory_id,
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "retained_corrupt_event_batch_slot",
            "request_digest": request_digest,
            "retained_record_digest": record_digest(record),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_retained_corrupt_event_batch_slot",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _conflict_clarification_transaction_id(processing_operation_id: str) -> str:
    return f"semantic_ingestion:clarification:transaction:{processing_operation_id}"


def _conflict_clarification_receipt_id(processing_operation_id: str) -> str:
    return f"semantic_ingestion:clarification:receipt:{processing_operation_id}"


def _conflict_clarification_context_id(proposal_digest: str) -> str:
    return f"semantic_ingestion:clarification:context:{proposal_digest}"


def _conflict_clarification_recovery_authority_id(
    processing_operation_id: str,
) -> str:
    return f"semantic_ingestion:clarification:recovery:{processing_operation_id}"


def _conflict_clarification_recovery_authority_record(
    *,
    processing_operation_id: str,
    generation: int,
    batch: SemanticMemoryEventBatch,
    replay_aggregate: SemanticReplayAuthorityAggregate,
    transaction_record: CanonicalMemoryRecord,
    receipt_record: CanonicalMemoryRecord,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.event_replay import (
        encode_semantic_memory_event_batch,
        encode_semantic_replay_authority,
    )

    event_payload = encode_semantic_memory_event_batch(batch)
    replay_payload = encode_semantic_replay_authority(replay_aggregate)
    authority_record_id = _conflict_clarification_recovery_authority_id(processing_operation_id)
    binding = ClarificationEventRecoveryAuthorityBinding.create(
        processing_operation_id=processing_operation_id,
        generation=generation,
        event_batch_sequence=batch.log_position.sequence,
        transaction_record_id=transaction_record.memory_id,
        transaction_record_digest=record_digest(transaction_record),
        receipt_record_id=receipt_record.memory_id,
        receipt_record_digest=record_digest(receipt_record),
        authority_record_id=authority_record_id,
        event_batch_record_id=_semantic_event_batch_id(batch.log_position.sequence),
        event_payload_digest=sha256(event_payload).hexdigest(),
        source_event_batch_digest=batch.source_event_batch_digest,
        event_batch_digest=batch.event_batch_digest,
        replay_aggregate_payload_digest=sha256(replay_payload).hexdigest(),
        replay_aggregate_digest=replay_aggregate.aggregate_digest,
        graph_revision_before=batch.events[0].payload.graph_revision_before,
        graph_revision_after=batch.events[-1].payload.graph_revision_after,
    )
    return CanonicalMemoryRecord(
        memory_id=authority_record_id,
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": ("conflict_clarification_recovery_authority"),
            "binding": binding.model_dump(mode="json"),
            "event_batch_canonical_hex": event_payload.hex(),
            "replay_aggregate_canonical_hex": replay_payload.hex(),
        },
        status=CommitStatus.COMMITTED,
        source_kind=("semantic_ingestion_conflict_clarification_recovery_authority"),
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_event_batch_record(
    batch: SemanticMemoryEventBatch,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.event_replay import encode_semantic_memory_event_batch

    return CanonicalMemoryRecord(
        memory_id=_semantic_event_batch_id(batch.log_position.sequence),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "semantic_event_batch",
            "canonical_hex": encode_semantic_memory_event_batch(batch).hex(),
            "event_batch_digest": batch.event_batch_digest,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_event_batch",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_replay_state_record(
    state: SemanticReplayState,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.event_replay import encode_semantic_replay_state

    return CanonicalMemoryRecord(
        memory_id=_semantic_replay_state_id(),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "semantic_replay_state",
            "canonical_hex": encode_semantic_replay_state(state).hex(),
            "state_digest": state.state_digest,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_replay_state",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _reference_integrity_ledger_record(snapshot, timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_reference_integrity_ledger_id(),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "reference_integrity_ledger",
            "canonical_hex": encode_typed_value(snapshot.model_dump(mode="python")).hex(),
            "ledger_digest": snapshot.ledger_digest,
            "manifest_fingerprint": snapshot.manifest_fingerprint,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_reference_integrity",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _accepted_identity_operation_record(artifact, timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_accepted_identity_operation_id(artifact.operation.operation_id),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "accepted_identity_operation",
            "operation_id": artifact.operation.operation_id,
            "canonical_hex": encode_typed_value(artifact.model_dump(mode="python")).hex(),
            "artifact_digest": artifact.artifact_digest,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_accepted_identity_operation",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _graph_identity_reservation_record(
    *,
    record_key: str,
    reservation_digest: str,
    operation_id: str,
    operation_fence_id: str,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_graph_identity_reservation_id(record_key),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "graph_identity_reservation",
            "record_key": record_key,
            "reservation_digest": reservation_digest,
            "operation_id": operation_id,
            "operation_fence_id": operation_fence_id,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_graph_identity_reservation",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_replay_authority_record(
    aggregate: SemanticReplayAuthorityAggregate,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.event_replay import encode_semantic_replay_authority

    return CanonicalMemoryRecord(
        memory_id=_semantic_replay_authority_id(),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "semantic_replay_authority",
            "canonical_hex": encode_semantic_replay_authority(aggregate).hex(),
            "aggregate_digest": aggregate.aggregate_digest,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_replay_authority",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_checkpoint_lifecycle_record(
    authority: ReplayCheckpointResumeAuthority,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.event_replay import encode_replay_checkpoint_lifecycle

    lifecycle = authority.lifecycle
    return CanonicalMemoryRecord(
        memory_id=_semantic_checkpoint_lifecycle_id(),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "semantic_replay_checkpoint_lifecycle",
            "canonical_hex": encode_replay_checkpoint_lifecycle(lifecycle).hex(),
            "authority_digest": lifecycle.authority_digest,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_checkpoint_lifecycle",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_registry_history_record(
    history: SemanticEventSchemaRegistryHistory,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.event_replay import (
        encode_event_schema_registry_history,
    )

    return CanonicalMemoryRecord(
        memory_id=_semantic_registry_history_id(),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "semantic_event_schema_registry_history",
            "canonical_hex": encode_event_schema_registry_history(history).hex(),
            "history_digest": history.history_digest,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_event_schema_registry_history",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _projection_publication_envelope_record(
    *,
    publication_kind: Literal[
        "trust_decay_schedule",
        "trust_decay_threshold",
        "temporal_policy_migration",
        "trust_policy_migration",
    ],
    projection_kind: Literal["temporal", "trust"],
    repository_id: str,
    operation_id: str,
    authority_coordinate_digest: str,
    policy_snapshot_digest: str,
    active_policy_fingerprint: str,
    complete_read_set_digest: str,
    writer_epoch: int,
    certificate_digest: str,
    generation_digest: str,
    pointer_digest: str,
    pointer_publication_kind: Literal["projection_commit", "migration_cutover"],
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    body = {
        "semantic_ingestion_kind": "projection_publication",
        "publication_kind": publication_kind,
        "projection_kind": projection_kind,
        "repository_id": repository_id,
        "operation_id": operation_id,
        "authority_coordinate_digest": authority_coordinate_digest,
        "policy_snapshot_digest": policy_snapshot_digest,
        "active_policy_fingerprint": active_policy_fingerprint,
        "complete_read_set_digest": complete_read_set_digest,
        "writer_epoch": writer_epoch,
        "certificate_digest": certificate_digest,
        "generation_digest": generation_digest,
        "pointer_digest": pointer_digest,
        "pointer_publication_kind": pointer_publication_kind,
    }
    return CanonicalMemoryRecord(
        memory_id=(
            "semantic_ingestion:projection-publication:"
            + sha256(operation_id.encode()).hexdigest()
        ),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            **body,
            "envelope_digest": sha256(encode_typed_value(body)).hexdigest(),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_projection_publication",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _projection_migration_progress_envelope_record(
    *,
    projection_kind: Literal["temporal", "trust"],
    repository_id: str,
    operation_id: str,
    migration_plan_digest: str,
    catch_up_entry_digests: tuple[str, ...],
    result_digests: tuple[str, ...],
    writer_epoch: int,
    progress_digest: str,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    body = {
        "semantic_ingestion_kind": "projection_migration_progress",
        "publication_kind": f"{projection_kind}_policy_migration_progress",
        "projection_kind": projection_kind,
        "repository_id": repository_id,
        "operation_id": operation_id,
        "migration_plan_digest": migration_plan_digest,
        "catch_up_entry_digests": list(catch_up_entry_digests),
        "result_digests": list(result_digests),
        "writer_epoch": writer_epoch,
        "progress_digest": progress_digest,
    }
    return CanonicalMemoryRecord(
        memory_id=(
            "semantic_ingestion:projection-publication:"
            + sha256(operation_id.encode()).hexdigest()
        ),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            **body,
            "envelope_digest": sha256(encode_typed_value(body)).hexdigest(),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_projection_publication",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _conflict_clarification_transaction_record(
    transaction_id: str,
    transaction_body: dict[str, object],
    transaction_digest: str,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_conflict_clarification_transaction_id(str(transaction_body["processing_operation_id"])),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "conflict_clarification_transaction",
            "semantic_transaction_id": transaction_id,
            "semantic_transaction_digest": transaction_digest,
            "transaction": transaction_body,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_conflict_clarification_transaction",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _conflict_clarification_context_record(
    context: RetainedConflictClarificationContext,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.memory_evolution.conflict_attention import (
        RetainedConflictClarificationContext,
    )

    validated = RetainedConflictClarificationContext.model_validate(context.model_dump(mode="python"))
    return CanonicalMemoryRecord(
        memory_id=_conflict_clarification_context_id(validated.proposal_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "conflict_clarification_retained_context",
            "context": validated.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_conflict_clarification_context",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _conflict_clarification_receipt_record(
    receipt: ConflictClarificationProcessingReceipt,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_conflict_clarification_receipt_id(receipt.processing_operation_id),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "conflict_clarification_processing_receipt",
            "receipt": receipt.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_conflict_clarification_receipt",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _generation_member_record(
    control: PreplanningOperationControl, generation: int, member: AtomicGenerationMember, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_generation_member_id(_control_namespace(control), generation, member.member_id),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={"semantic_ingestion_kind": "generation_member", "member": member.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_generation_member",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _generation_manifest_record(
    control: PreplanningOperationControl, generation: int, request: AtomicGenerationRequest, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_generation_manifest_id(_control_namespace(control), generation),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "generation_manifest",
            "generation": generation,
            "request_digest": request.request_digest,
            "members": tuple(member.model_dump(mode="json") for member in request.members),
            "required_artifact_digests": request.required_artifact_digests,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_generation_manifest",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_authority_record(
    reload: object, timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.contracts import encode_semantic_contract

    projection = reload.publication_core.authority_projection
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_authority_id(projection.authority_projection_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_pre_epoch_authority",
            "projection_digest": projection.authority_projection_digest,
            "canonical_hex": encode_semantic_contract(reload).hex(),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_pre_epoch_authority",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_authority_index_record(
    reload: object, timestamp: datetime,
) -> CanonicalMemoryRecord:
    projection = reload.publication_core.authority_projection
    recovery_key = reload.publication_receipt.recovery_key_digest
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_authority_index_id(
            recovery_key, projection.authority_projection_digest,
        ),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_pre_epoch_authority_index",
            "recovery_key_digest": recovery_key,
            "projection_digest": projection.authority_projection_digest,
            "authority_record_id": _bootstrap_graph_v3_authority_id(
                projection.authority_projection_digest
            ),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_authority_index",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_authority_from_record(record: CanonicalMemoryRecord) -> object:
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapGraphTransactionAuthorityReloadV3,
        decode_semantic_contract,
        encode_semantic_contract,
    )

    try:
        raw = bytes.fromhex(record.content["canonical_hex"])
        reload = decode_semantic_contract(
            raw, BootstrapGraphTransactionAuthorityReloadV3,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PreplanningStoreError("bootstrap graph authority record is corrupt") from exc
    if (
        record.source_kind != "semantic_ingestion_bootstrap_graph_v3_pre_epoch_authority"
        or encode_semantic_contract(reload) != raw
        or record.content.get("projection_digest")
        != reload.publication_core.authority_projection.authority_projection_digest
    ):
        raise PreplanningStoreError("bootstrap graph authority record is substituted")
    return reload


def _bootstrap_canonical_identity_authority_from_record(record: CanonicalMemoryRecord) -> object:
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapCanonicalIdentityBindingAllocationReloadV3,
        decode_semantic_contract,
        encode_semantic_contract,
    )
    try:
        raw = bytes.fromhex(record.content["canonical_hex"])
        reload = decode_semantic_contract(
            raw, BootstrapCanonicalIdentityBindingAllocationReloadV3,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PreplanningStoreError("canonical identity authority record is corrupt") from exc
    if (
        record.source_kind != "semantic_ingestion_bootstrap_canonical_identity_authority_v3"
        or record.content.get("reload_digest") != reload.reload_digest
        or encode_semantic_contract(reload) != raw
    ):
        raise PreplanningStoreError("canonical identity authority record is substituted")
    return reload


def _bootstrap_graph_v3_member_record(
    *, namespace_id: str, generation: int, member: object, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_member_id(namespace_id, generation, member.member_id),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_member",
            "member": member.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_member",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_manifest_record(
    *, namespace_id: str, request: object, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_manifest_id(
            namespace_id, request.publication_operation_generation
        ),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_manifest",
            "request": request.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_manifest",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_terminal_manifest_record(
    *, namespace_id: str, generation: int, members: tuple[object, ...],
    manifest_digest: str, request: object, timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_manifest_id(namespace_id, generation),
        domain=MemoryDomain.EXECUTION, text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_terminal_manifest",
            "publication_request_digest": request.publication_request_digest,
            "locator_digest": request.publication_intent.locator_digest,
            "manifest_digest": manifest_digest,
            "members": tuple(member.model_dump(mode="json") for member in members),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_manifest",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_terminal_control_record(control: object, timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_terminal_control_id(control.locator_digest),
        domain=MemoryDomain.EXECUTION, text="",
        content={"semantic_ingestion_kind": "bootstrap_graph_v3_terminal_control", "terminal_control": control.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_control",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_terminal_identity_record(identity: object, timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_terminal_identity_id(identity.locator_digest),
        domain=MemoryDomain.EXECUTION, text="",
        content={"semantic_ingestion_kind": "bootstrap_graph_v3_terminal_identity", "identity": identity.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_identity",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_terminal_locator_record(
    *, locator_digest: str, handoff_digest: str, reload: object, timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_terminal_locator_id(locator_digest),
        domain=MemoryDomain.EXECUTION, text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_terminal_locator",
            "locator_digest": locator_digest, "handoff_digest": handoff_digest,
            "reload": reload.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_terminal_request_record(
    *, request_digest: str, locator_digest: str, reload: object, timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_terminal_request_id(request_digest),
        domain=MemoryDomain.EXECUTION, text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_terminal_locator",
            "coordinator_request_digest": request_digest,
            "locator_digest": locator_digest,
            "reload": reload.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_terminal_recovery_record(
    *, normalization_replay: object, locator_digest: str, reload: object,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_terminal_recovery_id(
            normalization_replay.recovery_key_digest
        ),
        domain=MemoryDomain.EXECUTION, text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_terminal_locator",
            "normalization_recovery_key_digest": normalization_replay.recovery_key_digest,
            "normalization_replay_digest": normalization_replay.replay_digest,
            "normalization_result_digest": (
                normalization_replay.source_normalization_result.result_digest
            ),
            "locator_digest": locator_digest,
            "reload": reload.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_idempotency_record(
    *, namespace_id: str, request: object, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_idempotency_id(request.write_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_idempotency",
            "request_write_digest": request.write_digest,
            "request_digest": request.request_digest,
            "namespace_id": namespace_id,
            "publication_operation_generation": request.publication_operation_generation,
            "publication_artifact_generation": request.publication_artifact_generation,
            "manifest_id": _bootstrap_graph_v3_manifest_id(
                namespace_id, request.publication_operation_generation
            ),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_idempotency",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_retry_record(
    *, request: object, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_retry_id(request.request_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_retry_index",
            "request_digest": request.request_digest,
            "write_digest": request.write_digest,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_retry_index",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_retry_recovery_record(
    *, request: object, delivery_principal_binding_digest: str,
    required_outcome_scopes: object, manifest_id: str, timestamp: datetime,
) -> CanonicalMemoryRecord:
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapGraphDurableRetryProgressV3,
        BootstrapGraphRetryRecoveryLocatorV3,
        decode_bootstrap_graph_atomic_member_payload_v3,
    )

    progress_members = tuple(
        member
        for member in request.members
        if member.kind == "bootstrap_graph_retry_progress"
    )
    if len(progress_members) != 1:
        raise PreplanningStoreError("bootstrap graph retry recovery progress is ambiguous")
    try:
        progress = BootstrapGraphDurableRetryProgressV3.model_validate(
            decode_bootstrap_graph_atomic_member_payload_v3(
                kind=progress_members[0].kind,
                raw=progress_members[0].canonical_payload,
            )
        )
        locator = BootstrapGraphRetryRecoveryLocatorV3.create(
            kind="bootstrap_graph_retry_recovery_locator",
            operation_fence_binding_digest=request.operation_fence_binding.binding_digest,
            normalization_replay_digest=request.normalization_replay_digest,
            normalization_result_digest=request.normalization_result_digest,
            delivery_principal_binding_digest=(
                delivery_principal_binding_digest
            ),
            required_scope_set_digest=required_outcome_scopes.required_scope_set_digest,
            request_digest=request.request_digest,
            checkpoint_write_digest=request.write_digest,
            checkpoint_manifest_id=manifest_id,
            checkpoint_request=request,
            progress=progress,
        )
    except (TypeError, ValueError) as exc:
        raise PreplanningStoreError(
            "bootstrap graph retry recovery progress is invalid"
        ) from exc
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_retry_recovery_id(
            request.operation_fence_binding.binding_digest
        ),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_retry_recovery_locator",
            "locator": locator.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_retry_recovery_locator",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_epoch_record(*, epoch: object, timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_epoch_id(epoch.request_core_digest, epoch.epoch),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={"semantic_ingestion_kind": "bootstrap_graph_v3_epoch", "epoch": epoch.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_epoch",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_epoch_head_record(*, epoch: object, timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_epoch_head_id(epoch.request_core_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_epoch_head",
            "request_core_digest": epoch.request_core_digest,
            "epoch": epoch.epoch,
            "epoch_digest": epoch.epoch_digest,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_epoch_head",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_transition_record(
    *, transition: object, epoch: object, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_graph_v3_transition_id(transition.transition_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "bootstrap_graph_v3_epoch_transition",
            "transition_digest": transition.transition_digest,
            "transition": transition.model_dump(mode="json"),
            "epoch": epoch.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_epoch_transition",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_graph_v3_epoch_from_record(record: CanonicalMemoryRecord) -> object:
    from memorii.core.semantic_ingestion.contracts import BootstrapGraphControlEpochV3

    if (
        record.source_kind != "semantic_ingestion_bootstrap_graph_v3_epoch"
        or record.content.get("semantic_ingestion_kind") != "bootstrap_graph_v3_epoch"
    ):
        raise PreplanningStoreError("bootstrap graph epoch record is corrupt")
    try:
        return BootstrapGraphControlEpochV3.model_validate(
            record.content["epoch"], strict=False
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PreplanningStoreError("bootstrap graph epoch record is corrupt") from exc


def _bootstrap_graph_v3_epoch_from_transition_record(record: CanonicalMemoryRecord) -> object:
    from memorii.core.semantic_ingestion.contracts import BootstrapGraphControlEpochV3

    if (
        record.source_kind != "semantic_ingestion_bootstrap_graph_v3_epoch_transition"
        or record.content.get("semantic_ingestion_kind") != "bootstrap_graph_v3_epoch_transition"
    ):
        raise PreplanningStoreError("bootstrap graph transition record is corrupt")
    try:
        return BootstrapGraphControlEpochV3.model_validate(
            record.content["epoch"], strict=False
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PreplanningStoreError("bootstrap graph transition record is corrupt") from exc


def _bootstrap_graph_v3_epoch_unavailable(request: object, reason: str) -> object:
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapGraphControlEpochUnavailableV3,
        contract_digest,
    )

    return BootstrapGraphControlEpochUnavailableV3.create(
        kind="unavailable",
        request_core_digest=request.request_core_digest,
        reason=reason,
        reason_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-control-epoch-unavailable-reason.v3",
            {"reason": reason},
        ),
    )


def _bootstrap_v3_recovery_index_record(
    *, control: PreplanningOperationControl, generation: int, request: object, timestamp: datetime
) -> CanonicalMemoryRecord:
    """Build the Found index record written in the publication CAS.

    The caller has already validated the V3 request type.  Keeping the index
    outside the member list makes it a lookup key rather than candidate data.
    """
    key = request.bootstrap_recovery_key
    claim = request.bootstrap_recovery_claim
    result = request.source_normalization_result
    content = {
        "schema_version": 3,
        "kind": "found",
        "state": "found",
        "recovery_key_digest": key.recovery_key_digest,
        "consumed_claim_digest": claim.claim_digest,
        "recovery_control_snapshot_digest": claim.control_snapshot.snapshot_digest,
        "predecessor_operation_generation": claim.control_snapshot.control_record.predecessor_operation_generation,
        "predecessor_artifact_generation": claim.control_snapshot.control_record.predecessor_artifact_generation,
        "publication_operation_generation": generation,
        "publication_artifact_generation": generation,
        "namespace_id": _control_namespace(control),
        "atomic_request_digest": request.request_digest,
        "result_digest": result.result_digest,
        "provenance_manifest_digest": request.evidence_manifest.manifest_digest,
    }
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_v3_recovery_id(key.recovery_key_digest),
        domain=MemoryDomain.EXECUTION,
        text="",
        content=content,
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_v3_recovery_id(recovery_key_digest: str) -> str:
    return "semantic_ingestion:bootstrap-v3-recovery:" + recovery_key_digest


def _bootstrap_v3_unclaimed_recovery_record(
    *, recovery_key: object, operation_generation: int, artifact_generation: int,
    marker: BootstrapWriterHandoffMarkerV3, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_bootstrap_v3_recovery_id(recovery_key.recovery_key_digest),
        domain=MemoryDomain.EXECUTION, text="",
        content={"schema_version": 3, "state": "unclaimed", "recovery_key_digest": recovery_key.recovery_key_digest,
                 "operation_fence_digest": recovery_key.operation_fence_digest,
                 "handoff_marker_digest": marker.marker_digest,
                 "predecessor_operation_generation": operation_generation,
                 "predecessor_artifact_generation": artifact_generation,
                 "predecessor_control_digest": marker.expected_predecessor_control_digest,
                 "operation_fence": marker.operation_fence_binding.model_dump(mode="json"),
                 "writer_commit_binding": marker.writer_commit_binding.model_dump(mode="json"),
                 "source_id": recovery_key.source_id, "source_digest": recovery_key.source_digest,
                 "preparation_fingerprint": recovery_key.preparation_fingerprint,
                 "operation_id": recovery_key.operation_id},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_bootstrap_v3_recovery_index",
        timestamp=timestamp, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _bootstrap_v3_unavailable(recovery_key_digest: str, reason: str) -> object:
    from memorii.core.semantic_ingestion.contracts import BootstrapRecoveryUnavailableV3, contract_digest
    core = {"kind": "unavailable", "recovery_key_digest": recovery_key_digest, "reason": reason}
    body = {**core, "reason_digest": contract_digest(b"memorii.semantic-ingestion.bootstrap-recovery-unavailable.v3", core)}
    return BootstrapRecoveryUnavailableV3(**body, response_digest=contract_digest(
        b"memorii.semantic-ingestion.bootstrap-recovery-unavailable.v3", body))


def _bootstrap_v3_aborted(recovery_key_digest: str, reason: str) -> object:
    from memorii.core.semantic_ingestion.contracts import BootstrapRecoveryAbortedV3, contract_digest
    core = {"kind": "aborted", "recovery_key_digest": recovery_key_digest, "reason": reason}
    body = {**core, "reason_digest": contract_digest(b"memorii.semantic-ingestion.bootstrap-recovery-aborted.v3", core)}
    return BootstrapRecoveryAbortedV3(**body, response_digest=contract_digest(
        b"memorii.semantic-ingestion.bootstrap-recovery-aborted.v3", body))


def generation_request_digest(request: AtomicGenerationRequest) -> str:
    return sha256(encode_typed_value(request.model_dump(mode="python", exclude={"request_digest"}))).hexdigest()


def _member_kind_counts(members: tuple[AtomicGenerationMember, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for member in members:
        counts[member.kind] = counts.get(member.kind, 0) + 1
    return counts


def _publication(
    control: PreplanningOperationControl,
    introduction: bytes | None = None,
    index: bytes | None = None,
    closure: bytes | None = None,
) -> PreplanningPublication:
    introduction = introduction or encode_typed_value(
        {
            "kind": "operation_introduction",
            "operation_fence": control.operation_fence.model_dump(mode="python"),
            "graph_record_ids": (),
            "event_ids": (),
            "terminal_group_ids": (),
        }
    )
    index = index or encode_typed_value(
        {"kind": "artifact_index", "members": (("introduction", sha256(introduction).hexdigest()),)}
    )
    closure = closure or encode_typed_value(
        {
            "kind": "artifact_closure",
            "members": (("introduction", sha256(introduction).hexdigest()), ("index", sha256(index).hexdigest())),
            "graph_record_ids": (),
            "event_ids": (),
            "terminal_group_ids": (),
        }
    )
    return PreplanningPublication(
        operation=control, introduction_bytes=introduction, artifact_index_bytes=index, artifact_closure_bytes=closure
    )


def _publication_records(publication: PreplanningPublication, timestamp: datetime) -> tuple[CanonicalMemoryRecord, ...]:
    control = publication.operation
    return (
        _control_record(publication.operation, timestamp),
        *(
            _artifact_record(_control_namespace(control), kind, value, timestamp)
            for kind, value in (
                ("introduction", publication.introduction_bytes),
                ("index", publication.artifact_index_bytes),
                ("closure", publication.artifact_closure_bytes),
            )
        ),
    )


def _control_record(control: PreplanningOperationControl, timestamp: datetime) -> CanonicalMemoryRecord:
    fence = (
        None
        if control.lease is None
        else MemoryRecordFence(
            execution_token=control.lease.execution_token, ownership_epoch=control.lease.ownership_epoch
        )
    )
    return CanonicalMemoryRecord(
        memory_id=f"semantic_ingestion:operation:{_control_namespace(control)}",
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "preplanning_operation_control",
            "control": control.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="semantic_ingestion_preplanning_control",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        mutation_fence=fence,
    )


def _artifact_record(
    namespace_id: str, kind: str, canonical_bytes: bytes, timestamp: datetime
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_artifact_id(namespace_id, kind),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": f"preplanning_{kind}",
            "canonical_bytes_base64": base64.b64encode(canonical_bytes).decode("ascii"),
            "digest": sha256(canonical_bytes).hexdigest(),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_preplanning_artifact",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _control_from_record(record: CanonicalMemoryRecord) -> PreplanningOperationControl:
    if (
        record.source_kind != "semantic_ingestion_preplanning_control"
        or record.content.get("semantic_ingestion_kind") != "preplanning_operation_control"
    ):
        raise PreplanningStoreError("preplanning control record is corrupt")
    value = record.content.get("control")
    if isinstance(value, dict) and value.get("state") == "retry_exhausted":
        raise PreplanningStoreError("legacy retry_exhausted control requires explicit terminal migration")
    try:
        return PreplanningOperationControl.model_validate(value)
    except ValueError as exc:
        raise PreplanningStoreError("preplanning control record is corrupt") from exc


def _same_admission_record(
    existing: CanonicalMemoryRecord | None,
    proposed: CanonicalMemoryRecord,
) -> bool:
    """Compare deterministic admission identity while ignoring retry wall-clock time."""
    if existing is None:
        return False
    return existing.model_copy(update={"timestamp": proposed.timestamp}) == proposed
