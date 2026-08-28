"""Atomic immutable temporal and trust projection-history repository."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal, TypeGuard, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memorii.core.memory_evolution.admission import source_admission_source_digest
from memorii.core.memory_evolution.conflict_attention import (
    ActiveSemanticConflict,
    ActiveSemanticConflictResolverAuthority,
    AgentClarificationProposal,
    ClarificationAttemptOutcome,
    ConflictAttention,
    ConflictAudience,
    ConflictClarificationAttempt,
    ConflictClarificationAttemptResult,
    ConflictClarificationWork,
    ConflictKind,
    ConflictStatus,
    ContenderAdmissionBinding,
    SemanticConflictAuthorityCommitInput,
    SemanticConflictAuthorityResolutionRequest,
    SemanticConflictAuthorityResolver,
    SemanticConflictCandidateBinding,
    SemanticConflictClarificationNonceConsumption,
    SemanticConflictClarificationSubmissionGeneration,
    SemanticConflictClarificationSubmissionOperation,
    SemanticConflictClarificationTransition,
    SemanticConflictClarificationWorkGeneration,
    SemanticConflictContestKey,
    SemanticConflictIntroduction,
    SemanticConflictLedgerHead,
    SemanticConflictPointerPrecondition,
    SemanticConflictProjectionBinding,
    SemanticConflictProjectionTransition,
    SemanticConflictReplayBinding,
    SemanticConflictResolverAuthority,
    SemanticConflictScopeBinding,
    VerifiedUserConfirmation,
    conflict_clarification_processing_operation_id,
    decode_persisted_conflict_generation,
    verified_user_confirmation_digest,
    verified_user_confirmation_nonce_digest,
)
from memorii.core.memory_evolution.identity_lineage import (
    IdentityLineageError,
    replay_identity_lineage,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.semantic_state import (
    ActiveTemporalProjectionPointer,
    ActiveTrustProjectionPointer,
    ProjectionEvidenceRecord,
    ProjectionHistoryReplayBinding,
    ProjectionKind,
    SemanticAssertionKey,
    SemanticClaimSlotKey,
    TemporalPolicyMigrationCertificate,
    TemporalProjectionCommitCertificate,
    TemporalProjectionGeneration,
    TemporalProjectionHistoryEntry,
    TemporalProjectionRecord,
    TemporalProjectionView,
    TrustPolicyMigrationCertificate,
    TrustProjectionCommitCertificate,
    TrustProjectionGeneration,
    TrustProjectionHistoryEntry,
    TrustProjectionRecord,
    TrustProjectionView,
    projection_contract_digest,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.memory_evolution.writer_admission import (
    SemanticConflictAuthorityAdministrationAuthorization,
    SemanticConflictAuthorityAdministrationGrant,
    SemanticWriterAdmissionStore,
    SemanticWriterWriteAuthorization,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlanePrecondition,
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.semantic_ingestion.contracts import (
    ActionRevision,
    ClaimAssertion,
    IdentityLineageRecord,
    PredicateTrustRule,
    SemanticDurableCarrier,
    TemporalPolicySnapshot,
    TemporalTransitionRecord,
    TrustPolicySnapshot,
)
from memorii.core.semantic_ingestion.event_replay import (
    SemanticMaterializedMemoryRecord,
    SemanticReplayState,
)
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
)

ProjectionHistoryErrorCode = Literal[
    "projection_history_unavailable",
    "stale_materialized_projection",
    "projection_history_integrity_error",
    "projection_publication_diverged",
    "projection_publication_time_regression",
    "projection_publication_unauthorized",
]

_ModelT = TypeVar("_ModelT", bound=BaseModel)

_CONFLICT_AUTHORITY_SCHEMA = "memorii.semantic-conflict-authority.v1"
_CONFLICT_LEDGER_HEAD_ID = "semantic_ingestion:conflict-authority:ledger-head"


def _conflict_authority_record_type(memory_id: str) -> str | None:
    prefixes = (
        ("semantic_ingestion:conflict-authority:introduction:", "introduction"),
        ("semantic_ingestion:conflict-authority:transition:", "transition"),
        ("semantic_ingestion:conflict-authority:clarification-transition:", "clarification_transition"),
        ("semantic_ingestion:conflict-authority:clarification-submission:", "clarification_submission"),
        ("semantic_ingestion:conflict-authority:clarification-submission-operation:", "clarification_submission_operation"),
        ("semantic_ingestion:conflict-authority:clarification-confirmation-proof:", "clarification_confirmation_proof"),
        ("semantic_ingestion:conflict-authority:clarification-nonce-consumption:", "clarification_nonce_consumption"),
        ("semantic_ingestion:conflict-authority:clarification-work:", "clarification_work"),
        ("semantic_ingestion:conflict-authority:clarification-work-member:", "clarification_work_member"),
        ("semantic_ingestion:conflict-authority:clarification-attempt-member:", "clarification_attempt_member"),
        ("semantic_ingestion:conflict-authority:clarification-attempt-result-member:", "clarification_attempt_result_member"),
        ("semantic_ingestion:conflict-authority:pointer-history:", "pointer_history"),
        ("semantic_ingestion:conflict-authority:pointer:", "active_pointer"),
        (
            "semantic_ingestion:conflict-authority:resolver-pointer-history:",
            "resolver_pointer_history",
        ),
        ("semantic_ingestion:conflict-authority:resolver-pointer:", "resolver_pointer"),
        ("semantic_ingestion:conflict-authority:resolver:", "resolver_authority"),
    )
    if memory_id == _CONFLICT_LEDGER_HEAD_ID:
        return "ledger_head"
    return next(
        (record_type for prefix, record_type in prefixes if memory_id.startswith(prefix)),
        None,
    )


def _decode_conflict_authority_record(
    record: CanonicalMemoryRecord,
) -> tuple[str, object, int | None]:
    record_type = _conflict_authority_record_type(record.memory_id)
    expected_fields = {
        "authority_schema",
        "authority_record_type",
        "immutable_record_coordinate",
        "canonical_hex",
        "authority_digest",
    }
    try:
        canonical_hex = record.content["canonical_hex"]
        raw = bytes.fromhex(str(canonical_hex))
        coordinate = record.content["immutable_record_coordinate"]
        if (
            record.source_kind != "semantic_ingestion_conflict_authority"
            or record_type is None
            or set(record.content) != expected_fields
            or record.content["authority_schema"] != _CONFLICT_AUTHORITY_SCHEMA
            or record.content["authority_record_type"] != record_type
            or not isinstance(canonical_hex, str)
            or record.content["authority_digest"] != sha256(raw).hexdigest()
            or (
                record_type in {"introduction", "transition", "clarification_transition"}
                and (isinstance(coordinate, bool) or not isinstance(coordinate, int) or coordinate < 1)
            )
            or (
                record_type not in {"introduction", "transition", "clarification_transition"}
                and coordinate is not None
            )
        ):
            raise ValueError
        decoded = decode_typed_value(raw)
        if (
            record_type in {"introduction", "transition", "clarification_transition"}
            and (
                not isinstance(decoded, dict)
                or decoded.get("record_coordinate") != coordinate
            )
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, CanonicalTypedValueError) as exc:
        raise ProjectionHistoryError("projection_history_integrity_error") from exc
    return record_type, decoded, coordinate


class ProjectionHistoryError(ValueError):
    """Typed closed projection-history failure."""

    def __init__(self, code: ProjectionHistoryErrorCode) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CurrentClarificationWork:
    """The one replay-validated queue image for a submitted conflict."""

    proposal: AgentClarificationProposal
    work: ConflictClarificationWork
    attempt: ConflictClarificationAttempt | None


class SemanticConflictResolverAuthorityRepository:
    """Host-writer administration boundary for resolver authority rotation."""

    def __init__(
        self,
        memory_plane: MemoryPlaneService,
        admissions: SemanticWriterAdmissionStore,
        *,
        administration_capability: SemanticConflictAuthorityAdministrationGrant,
        now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._memory_plane = memory_plane
        self._admissions = admissions
        self._capability = administration_capability
        self._now = now_provider
        if (
            administration_capability
            is not admissions._conflict_authority_administration_grant
            or administration_capability._issuer is not admissions
        ):
            raise ProjectionHistoryError("projection_publication_unauthorized")

    def install(
        self,
        *,
        authority: SemanticConflictResolverAuthority,
        pointer: ActiveSemanticConflictResolverAuthority,
        capability: object,
    ) -> ActiveSemanticConflictResolverAuthority:
        return self._publish(
            authority=authority,
            pointer=pointer,
            expected_pointer=None,
            capability=capability,
        )

    def replace(
        self,
        *,
        authority: SemanticConflictResolverAuthority,
        pointer: ActiveSemanticConflictResolverAuthority,
        expected_pointer: ActiveSemanticConflictResolverAuthority,
        capability: object,
    ) -> ActiveSemanticConflictResolverAuthority:
        return self._publish(
            authority=authority,
            pointer=pointer,
            expected_pointer=expected_pointer,
            capability=capability,
        )

    def _publish(
        self,
        *,
        authority: SemanticConflictResolverAuthority,
        pointer: ActiveSemanticConflictResolverAuthority,
        expected_pointer: ActiveSemanticConflictResolverAuthority | None,
        capability: object,
    ) -> ActiveSemanticConflictResolverAuthority:
        if capability is not self._capability:
            raise ProjectionHistoryError("projection_publication_unauthorized")
        authority_id = (
            "semantic_ingestion:conflict-authority:resolver:"
            f"{authority.authority_record_id}"
        )
        pointer_id = (
            "semantic_ingestion:conflict-authority:resolver-pointer:"
            f"{pointer.tenant_partition_id}:{pointer.renderer_schema}"
        )
        pointer_history_id = (
            "semantic_ingestion:conflict-authority:resolver-pointer-history:"
            f"{pointer.tenant_partition_id}:{pointer.renderer_schema}:"
            f"{pointer.pointer_revision}"
        )
        if (
            pointer.authority_record_id != authority.authority_record_id
            or pointer.authority_record_digest != authority.authority_record_digest
            or pointer.tenant_partition_id != authority.tenant_partition_id
            or pointer.renderer_schema != authority.renderer_schema
            or (expected_pointer is None)
            != (
                authority.authority_revision == 1
                and authority.status == "active"
                and pointer.pointer_revision == 1
                and pointer.predecessor_pointer_digest is None
            )
            or (
                expected_pointer is not None
                and (
                    pointer.pointer_revision != expected_pointer.pointer_revision + 1
                    or pointer.predecessor_pointer_digest
                    != expected_pointer.pointer_digest
                )
            )
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        existing_authority = self._memory_plane.get_record(authority_id)
        existing_pointer_record = self._memory_plane.get_record(pointer_id)
        existing_pointer_history = self._memory_plane.get_record(pointer_history_id)
        if existing_authority is not None and existing_pointer_record is not None:
            try:
                recovered_authority = SemanticConflictResolverAuthority.model_validate(
                    _decode_conflict_authority_record(existing_authority)[1]
                )
                recovered_pointer = ActiveSemanticConflictResolverAuthority.model_validate(
                    _decode_conflict_authority_record(existing_pointer_record)[1]
                )
                recovered_pointer_history = (
                    ActiveSemanticConflictResolverAuthority.model_validate(
                        _decode_conflict_authority_record(existing_pointer_history)[1]
                    )
                    if existing_pointer_history is not None
                    else None
                )
            except ValueError as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            if (
                recovered_authority == authority
                and recovered_pointer == pointer
                and recovered_pointer_history == pointer
            ):
                return recovered_pointer
        if existing_authority is not None:
            raise ProjectionHistoryError("stale_materialized_projection")
        if expected_pointer is None:
            if existing_pointer_record is not None:
                raise ProjectionHistoryError("stale_materialized_projection")
            pointer_precondition: MemoryPlanePrecondition = RecordAbsentPrecondition(
                memory_id=pointer_id
            )
        else:
            if existing_pointer_record is None:
                raise ProjectionHistoryError("stale_materialized_projection")
            try:
                current_pointer = ActiveSemanticConflictResolverAuthority.model_validate(
                    _decode_conflict_authority_record(existing_pointer_record)[1]
                )
            except ValueError as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            if current_pointer != expected_pointer:
                raise ProjectionHistoryError("stale_materialized_projection")
            current_authority_record = self._memory_plane.get_record(
                "semantic_ingestion:conflict-authority:resolver:"
                f"{expected_pointer.authority_record_id}"
            )
            if current_authority_record is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            try:
                current_authority = SemanticConflictResolverAuthority.model_validate(
                    _decode_conflict_authority_record(current_authority_record)[1]
                )
            except ValueError as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            if (
                current_authority.authority_record_digest
                != expected_pointer.authority_record_digest
                or authority.authority_revision
                != current_authority.authority_revision + 1
                or authority.predecessor_authority_record_digest
                != current_authority.authority_record_digest
            ):
                raise ProjectionHistoryError("stale_materialized_projection")
            pointer_precondition = RecordDigestPrecondition(
                memory_id=pointer_id,
                expected_digest=record_digest(existing_pointer_record),
            )
        at = _utc(self._now())
        records = (
            ProjectionHistoryRepository._conflict_authority_record(
                authority_id, authority, at
            ),
            ProjectionHistoryRepository._conflict_authority_record(
                pointer_history_id, pointer, at
            ),
            ProjectionHistoryRepository._conflict_authority_record(
                pointer_id, pointer, at
            ),
        )
        self._memory_plane.conditionally_write_records(
            records,
            preconditions=(
                RecordAbsentPrecondition(memory_id=authority_id),
                RecordAbsentPrecondition(memory_id=pointer_history_id),
                pointer_precondition,
            ),
            authorization=SemanticConflictAuthorityAdministrationAuthorization(
                owner=self._capability
            ),
        )
        return pointer


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProjectionHistoryError("projection_history_integrity_error")
    normalized = value.astimezone(UTC)
    return normalized


def _digest(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(_digest(item) for item in value)
    if not isinstance(value, str):
        raise TypeError("projection publication digest must be a string")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("projection publication digest is invalid")
    return value


def _conflict_contract_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _conflict_contract_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {
            key: _conflict_contract_value(item) for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_conflict_contract_value(item) for item in value)
    if isinstance(value, list):
        return [_conflict_contract_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return type(value)(_conflict_contract_value(item) for item in value)
    return value


def _expected_conflict_shapes(
    *,
    temporal: tuple[TemporalProjectionRecord, ...] = (),
    trust: tuple[TrustProjectionRecord, ...] = (),
) -> dict[tuple[SemanticClaimSlotKey, str, tuple[tuple[str, str], ...]], set[str]]:
    expected: dict[
        tuple[SemanticClaimSlotKey, str, tuple[tuple[str, str], ...]], set[str]
    ] = {}
    for basis, projections in (("temporal", temporal), ("trust", trust)):
        for projection in projections:
            if projection.outcome != "contested" or projection.claim_slot_key is None:
                continue
            candidates = tuple(
                sorted(
                    (evidence.candidate_id, evidence.candidate_digest)
                    for evidence in projection.evidence
                    if evidence.authority_relation == "contested_top"
                )
            )
            partition = sha256(
                encode_typed_value(
                    projection.valid_interval.model_dump(mode="python")
                    if projection.valid_interval is not None
                    else None
                )
            ).hexdigest()
            expected.setdefault(
                (projection.claim_slot_key, partition, candidates), set()
            ).add(basis)
    return expected


def _validate_semantic_conflict_authority(
    authority: SemanticConflictAuthorityCommitInput,
    *,
    temporal: tuple[TemporalProjectionRecord, ...] = (),
    trust: tuple[TrustProjectionRecord, ...] = (),
) -> None:
    expected = _expected_conflict_shapes(temporal=temporal, trust=trust)
    supplied = {
        (
            resolution.contest_key.claim_slot_key,
            resolution.contest_key.valid_time_partition_digest,
            resolution.contest_key.candidate_set,
        ): set(resolution.contest_key.bases)
        for resolution in authority.resolutions
    }
    if supplied != expected:
        raise ValueError(
            "semantic conflict authority resolutions do not biject contested projections"
        )


class ProjectionCommitRequest(BaseModel):
    repository_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    graph_revision: str = Field(min_length=1)
    event_batch_sequence: int = Field(ge=0)
    event_batch_digest: str
    complete_read_set_digest: str
    writer_epoch: int = Field(ge=1)
    base_snapshot_token: str = Field(min_length=1)
    temporal_policy_fingerprint: str
    trust_policy_fingerprint: str
    arbitration_as_of: datetime
    temporal_projections: tuple[TemporalProjectionRecord, ...]
    trust_projections: tuple[TrustProjectionRecord, ...]
    semantic_conflict_authority: SemanticConflictAuthorityCommitInput
    terminal_clarification_conflict_ids: tuple[str, ...] = ()
    trust_decay_command_digests: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "event_batch_digest",
        "complete_read_set_digest",
        "temporal_policy_fingerprint",
        "trust_policy_fingerprint",
        "trust_decay_command_digests",
    )(_digest)

    @field_validator("arbitration_as_of")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_request(self) -> ProjectionCommitRequest:
        temporal = tuple(item.projection_digest for item in self.temporal_projections)
        trust = tuple(item.projection_digest for item in self.trust_projections)
        if (
            temporal != tuple(sorted(set(temporal)))
            or trust != tuple(sorted(set(trust)))
            or self.trust_decay_command_digests != tuple(sorted(set(self.trust_decay_command_digests)))
            or any(
                item.repository_id != self.repository_id
                or item.temporal_policy_fingerprint != self.temporal_policy_fingerprint
                for item in self.temporal_projections
            )
            or any(
                item.repository_id != self.repository_id
                or item.trust_policy_fingerprint != self.trust_policy_fingerprint
                or item.arbitration_as_of != self.arbitration_as_of
                for item in self.trust_projections
            )
            or self.terminal_clarification_conflict_ids
            != tuple(sorted(set(self.terminal_clarification_conflict_ids)))
        ):
            raise ValueError("projection commit request closure is invalid")
        _validate_semantic_conflict_authority(
            self.semantic_conflict_authority,
            temporal=self.temporal_projections,
            trust=self.trust_projections,
        )
        return self


class TrustProjectionAdvanceRequest(BaseModel):
    """One trust-only successor; temporal authority is deliberately untouched."""

    repository_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    graph_revision: str = Field(min_length=1)
    event_batch_sequence: int = Field(ge=0)
    event_batch_digest: str
    complete_read_set_digest: str
    writer_epoch: int = Field(ge=1)
    base_snapshot_token: str = Field(min_length=1)
    trust_policy_fingerprint: str
    arbitration_as_of: datetime
    trust_projections: tuple[TrustProjectionRecord, ...]
    semantic_conflict_authority: SemanticConflictAuthorityCommitInput
    trust_decay_command_digests: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "event_batch_digest",
        "complete_read_set_digest",
        "trust_policy_fingerprint",
        "trust_decay_command_digests",
    )(_digest)

    @field_validator("arbitration_as_of")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_request(self) -> TrustProjectionAdvanceRequest:
        members = tuple(item.projection_digest for item in self.trust_projections)
        if (
            members != tuple(sorted(set(members)))
            or self.trust_decay_command_digests
            != tuple(sorted(set(self.trust_decay_command_digests)))
            or any(
                item.repository_id != self.repository_id
                or item.trust_policy_fingerprint != self.trust_policy_fingerprint
                or item.arbitration_as_of != self.arbitration_as_of
                for item in self.trust_projections
            )
        ):
            raise ValueError("trust projection advance closure is invalid")
        _validate_semantic_conflict_authority(
            self.semantic_conflict_authority,
            trust=self.trust_projections,
        )
        return self


class TemporalProjectionAdvanceRequest(BaseModel):
    """One temporal-only successor; trust authority is deliberately untouched."""

    repository_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    graph_revision: str = Field(min_length=1)
    event_batch_sequence: int = Field(ge=0)
    event_batch_digest: str
    complete_read_set_digest: str
    writer_epoch: int = Field(ge=1)
    base_snapshot_token: str = Field(min_length=1)
    temporal_policy_fingerprint: str
    temporal_projections: tuple[TemporalProjectionRecord, ...]
    semantic_conflict_authority: SemanticConflictAuthorityCommitInput

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "event_batch_digest",
        "complete_read_set_digest",
        "temporal_policy_fingerprint",
    )(_digest)

    @model_validator(mode="after")
    def validate_request(self) -> TemporalProjectionAdvanceRequest:
        members = tuple(item.projection_digest for item in self.temporal_projections)
        if (
            members != tuple(sorted(set(members)))
            or any(
                item.repository_id != self.repository_id
                or item.temporal_policy_fingerprint
                != self.temporal_policy_fingerprint
                for item in self.temporal_projections
            )
        ):
            raise ValueError("temporal projection advance closure is invalid")
        _validate_semantic_conflict_authority(
            self.semantic_conflict_authority,
            temporal=self.temporal_projections,
        )
        return self


class TemporalPolicyMigrationAdvanceRequest(BaseModel):
    """Complete temporal cutover closure prepared by the migration repository."""

    repository_id: str = Field(min_length=1)
    migration_plan_digest: str
    active_policy_fingerprint_before: str
    pending_policy_fingerprint: str
    base_snapshot_token: str = Field(min_length=1)
    base_graph_revision: str = Field(min_length=1)
    final_catch_up_watermark: str = Field(min_length=1)
    server_derived_base_slot_plan_digests: tuple[str, ...]
    server_derived_catch_up_entry_digests: tuple[str, ...]
    canonical_slot_result_digests: tuple[str, ...]
    complete_read_set_digest: str
    cutover_digest: str
    writer_epoch_before: int = Field(ge=1)
    activated_writer_epoch: int = Field(ge=1)
    temporal_projections: tuple[TemporalProjectionRecord, ...]
    semantic_conflict_authority: SemanticConflictAuthorityCommitInput

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "migration_plan_digest",
        "active_policy_fingerprint_before",
        "pending_policy_fingerprint",
        "server_derived_base_slot_plan_digests",
        "server_derived_catch_up_entry_digests",
        "canonical_slot_result_digests",
        "complete_read_set_digest",
        "cutover_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_request(self) -> TemporalPolicyMigrationAdvanceRequest:
        members = tuple(item.projection_digest for item in self.temporal_projections)
        canonical_sets = (
            self.server_derived_base_slot_plan_digests,
            self.server_derived_catch_up_entry_digests,
            self.canonical_slot_result_digests,
            members,
        )
        if (
            self.active_policy_fingerprint_before == self.pending_policy_fingerprint
            or self.activated_writer_epoch <= self.writer_epoch_before
            or any(values != tuple(sorted(set(values))) for values in canonical_sets)
            or any(
                item.repository_id != self.repository_id
                or item.temporal_policy_fingerprint != self.pending_policy_fingerprint
                for item in self.temporal_projections
            )
        ):
            raise ValueError("temporal policy migration closure is invalid")
        _validate_semantic_conflict_authority(
            self.semantic_conflict_authority,
            temporal=self.temporal_projections,
        )
        return self


class TrustPolicyMigrationAdvanceRequest(BaseModel):
    """Complete trust cutover closure prepared by the migration repository."""

    repository_id: str = Field(min_length=1)
    migration_plan_digest: str
    active_policy_fingerprint_before: str
    pending_policy_fingerprint: str
    base_snapshot_token: str = Field(min_length=1)
    base_graph_revision: str = Field(min_length=1)
    final_catch_up_watermark: str = Field(min_length=1)
    server_derived_base_slot_plan_digests: tuple[str, ...]
    server_derived_catch_up_entry_digests: tuple[str, ...]
    canonical_slot_result_digests: tuple[str, ...]
    complete_read_set_digest: str
    cutover_digest: str
    writer_epoch_before: int = Field(ge=1)
    activated_writer_epoch: int = Field(ge=1)
    arbitration_as_of: datetime
    trust_projections: tuple[TrustProjectionRecord, ...]
    semantic_conflict_authority: SemanticConflictAuthorityCommitInput
    trust_decay_command_digests: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "migration_plan_digest",
        "active_policy_fingerprint_before",
        "pending_policy_fingerprint",
        "server_derived_base_slot_plan_digests",
        "server_derived_catch_up_entry_digests",
        "canonical_slot_result_digests",
        "complete_read_set_digest",
        "cutover_digest",
        "trust_decay_command_digests",
    )(_digest)

    @field_validator("arbitration_as_of")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_request(self) -> TrustPolicyMigrationAdvanceRequest:
        members = tuple(item.projection_digest for item in self.trust_projections)
        canonical_sets = (
            self.server_derived_base_slot_plan_digests,
            self.server_derived_catch_up_entry_digests,
            self.canonical_slot_result_digests,
            self.trust_decay_command_digests,
            members,
        )
        if (
            self.active_policy_fingerprint_before == self.pending_policy_fingerprint
            or self.activated_writer_epoch <= self.writer_epoch_before
            or any(values != tuple(sorted(set(values))) for values in canonical_sets)
            or any(
                item.repository_id != self.repository_id
                or item.trust_policy_fingerprint != self.pending_policy_fingerprint
                or item.arbitration_as_of != self.arbitration_as_of
                for item in self.trust_projections
            )
        ):
            raise ValueError("trust policy migration closure is invalid")
        _validate_semantic_conflict_authority(
            self.semantic_conflict_authority,
            trust=self.trust_projections,
        )
        return self


class TemporalProjectionPublication(BaseModel):
    certificate: TemporalProjectionCommitCertificate | TemporalPolicyMigrationCertificate
    generation: TemporalProjectionGeneration
    history_entry: TemporalProjectionHistoryEntry
    active_pointer: ActiveTemporalProjectionPointer

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TrustProjectionPublication(BaseModel):
    certificate: TrustProjectionCommitCertificate | TrustPolicyMigrationCertificate
    generation: TrustProjectionGeneration
    history_entry: TrustProjectionHistoryEntry
    active_pointer: ActiveTrustProjectionPointer

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProjectionPublication(BaseModel):
    temporal: TemporalProjectionPublication
    trust: TrustProjectionPublication
    replay_bindings: tuple[ProjectionHistoryReplayBinding, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_publication(self) -> ProjectionPublication:
        if (
            tuple(item.projection_kind for item in self.replay_bindings) != ("temporal", "trust")
            or self.temporal.active_pointer.repository_id != self.trust.active_pointer.repository_id
        ):
            raise ValueError("projection publication does not close both kinds")
        return self


@dataclass(frozen=True)
class PreparedProjectionPublication:
    publication: ProjectionPublication
    records: tuple[CanonicalMemoryRecord, ...]
    preconditions: tuple[MemoryPlanePrecondition, ...]


@dataclass(frozen=True)
class PreparedTemporalProjectionPublication:
    publication: TemporalProjectionPublication
    records: tuple[CanonicalMemoryRecord, ...]
    preconditions: tuple[MemoryPlanePrecondition, ...]


@dataclass(frozen=True)
class PreparedTrustProjectionPublication:
    publication: TrustProjectionPublication
    records: tuple[CanonicalMemoryRecord, ...]
    preconditions: tuple[MemoryPlanePrecondition, ...]


@dataclass(frozen=True)
class PreparedClarificationTransitionClosure:
    """Records and fences for a same-plane clarification lifecycle edge.

    Completion needs to join this closure with the semantic receipt and event
    effect in one memory-plane write, so it must be constructible without
    performing the write itself.
    """

    successor: ActiveSemanticConflict
    records: tuple[CanonicalMemoryRecord, ...]
    preconditions: tuple[MemoryPlanePrecondition, ...]


@dataclass(frozen=True)
class _LoadedKind:
    kind: ProjectionKind
    entries: tuple[TemporalProjectionHistoryEntry | TrustProjectionHistoryEntry, ...]
    generations: dict[str, TemporalProjectionGeneration | TrustProjectionGeneration]
    certificates: dict[
        str,
        TemporalProjectionCommitCertificate
        | TrustProjectionCommitCertificate
        | TemporalPolicyMigrationCertificate
        | TrustPolicyMigrationCertificate,
    ]
    temporal_projections: dict[str, TemporalProjectionRecord]
    trust_projections: dict[str, TrustProjectionRecord]
    active: ActiveTemporalProjectionPointer | ActiveTrustProjectionPointer | None
    active_record: CanonicalMemoryRecord | None


class ProjectionHistoryRepository:
    """Own both policy-relative projection histories without merging their schemas."""

    def __init__(
        self,
        memory_plane: MemoryPlaneService,
        *,
        repository_id: str,
        now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
        publication_capability: object | None = None,
        current_replay_authority_resolver: Callable[[], tuple[str, tuple[ProjectionHistoryReplayBinding, ...]]]
        | None = None,
        semantic_conflict_authority_resolver: SemanticConflictAuthorityResolver | None = None,
    ) -> None:
        if not repository_id:
            raise ValueError("projection repository ID is empty")
        self._memory_plane = memory_plane
        self._repository_id = repository_id
        self._now = now_provider
        self._repository_token = sha256(repository_id.encode("utf-8")).hexdigest()
        self._publication_capability = publication_capability or object()
        self._current_replay_authority_resolver = current_replay_authority_resolver
        self._semantic_conflict_authority_resolver = semantic_conflict_authority_resolver

    @property
    def repository_id(self) -> str:
        return self._repository_id

    def append_clarification_transition(
        self,
        transition: SemanticConflictClarificationTransition,
        *,
        authorization: SemanticWriterWriteAuthorization,
        submission_generation: SemanticConflictClarificationSubmissionGeneration | None = None,
    ) -> ActiveSemanticConflict:
        """Append one already-decided clarification lifecycle edge in the plane.

        This is deliberately the only detached clarification mutation: callers
        supply the semantic writer authorization and the exact predecessor is
        re-read here before the pointer/history/head CAS is assembled.
        """
        transition = SemanticConflictClarificationTransition.model_validate(
            transition.model_dump(mode="python")
        )
        if transition.reason.value == "submitted" and submission_generation is None:
            raise ProjectionHistoryError("projection_publication_unauthorized")
        if submission_generation is not None:
            submission_generation = SemanticConflictClarificationSubmissionGeneration.model_validate(
                submission_generation.model_dump(mode="python")
            )
            if submission_generation.transition != transition:
                raise ProjectionHistoryError("projection_history_integrity_error")
        transition_id = (
            "semantic_ingestion:conflict-authority:clarification-transition:"
            f"{transition.transition_digest}"
        )
        # A lost acknowledgement retries the complete immutable closure after
        # the pointer has advanced, so recognize its exact retained edge
        # before applying predecessor freshness checks for a new append.
        retained_transition_record = self._memory_plane.get_record(transition_id)
        if retained_transition_record is not None:
            try:
                record_type, payload, _ = _decode_conflict_authority_record(retained_transition_record)
                retained_transition = decode_persisted_conflict_generation(
                    payload, SemanticConflictClarificationTransition
                )
                pointer_record = self._memory_plane.get_record(
                    f"semantic_ingestion:conflict-authority:pointer:{transition.conflict_id}"
                )
                retained_pointer = ActiveSemanticConflict.model_validate(
                    _decode_conflict_authority_record(pointer_record)[1]
                ) if pointer_record is not None else None
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise ProjectionHistoryError("projection_history_integrity_error") from exc
            if (
                record_type == "clarification_transition"
                and retained_transition == transition
                and retained_pointer is not None
                and retained_pointer.current_record_id == transition_id
                and retained_pointer.current_record_digest == transition.transition_digest
            ):
                if submission_generation is not None:
                    work_member = self._memory_plane.get_record(
                        "semantic_ingestion:conflict-authority:clarification-work-member:"
                        f"{submission_generation.work.work_digest}"
                    )
                    try:
                        generation_record = self._memory_plane.get_record(
                            "semantic_ingestion:conflict-authority:clarification-submission:"
                            f"{submission_generation.generation_digest}"
                        )
                        expected_operation = SemanticConflictClarificationSubmissionOperation.create(
                            operation_id=submission_generation.operation_receipt.operation_id,
                            request_digest=submission_generation.operation_receipt.request_digest,
                            proposal_digest=submission_generation.operation_receipt.proposal_digest,
                            operation_receipt_digest=submission_generation.operation_receipt.receipt_digest,
                            generation_digest=submission_generation.generation_digest,
                            verified_confirmation_digest=submission_generation.operation_receipt.verified_confirmation_digest,
                        )
                        operation_record = self._memory_plane.get_record(
                            "semantic_ingestion:conflict-authority:clarification-submission-operation:"
                            f"{expected_operation.operation_id}"
                        )
                        if work_member is None or generation_record is None or operation_record is None:
                            raise ValueError
                        member_type, member_payload, _ = _decode_conflict_authority_record(
                            work_member
                        )
                        generation_type, generation_payload, _ = _decode_conflict_authority_record(
                            generation_record
                        )
                        operation_type, operation_payload, _ = _decode_conflict_authority_record(
                            operation_record
                        )
                        if (
                            member_type != "clarification_work_member"
                            or decode_persisted_conflict_generation(
                                member_payload, ConflictClarificationWork
                            )
                            != submission_generation.work
                            or generation_type != "clarification_submission"
                            or decode_persisted_conflict_generation(
                                generation_payload, SemanticConflictClarificationSubmissionGeneration
                            ) != submission_generation
                            or operation_type != "clarification_submission_operation"
                            or decode_persisted_conflict_generation(
                                operation_payload, SemanticConflictClarificationSubmissionOperation
                            ) != expected_operation
                        ):
                            raise ValueError
                        if submission_generation.verified_confirmation is not None:
                            proof_digest = verified_user_confirmation_digest(
                                submission_generation.verified_confirmation
                            )
                            proof_record = self._memory_plane.get_record(
                                "semantic_ingestion:conflict-authority:clarification-confirmation-proof:"
                                f"{proof_digest}"
                            )
                            if proof_record is None:
                                raise ValueError
                            proof_type, proof_payload, _ = _decode_conflict_authority_record(proof_record)
                            if (
                                proof_type != "clarification_confirmation_proof"
                                or decode_persisted_conflict_generation(
                                    proof_payload, VerifiedUserConfirmation
                                ) != submission_generation.verified_confirmation
                            ):
                                raise ValueError
                            expected_nonce = SemanticConflictClarificationNonceConsumption.create(
                                nonce_digest=verified_user_confirmation_nonce_digest(
                                    submission_generation.verified_confirmation
                                ),
                                verified_confirmation_digest=verified_user_confirmation_digest(
                                    submission_generation.verified_confirmation
                                ),
                                operation_id=submission_generation.operation_receipt.operation_id,
                            )
                            nonce_record = self._memory_plane.get_record(
                                "semantic_ingestion:conflict-authority:clarification-nonce-consumption:"
                                f"{expected_nonce.nonce_digest}"
                            )
                            if nonce_record is None:
                                raise ValueError
                            nonce_type, nonce_payload, _ = _decode_conflict_authority_record(nonce_record)
                            if (
                                nonce_type != "clarification_nonce_consumption"
                                or decode_persisted_conflict_generation(
                                    nonce_payload, SemanticConflictClarificationNonceConsumption
                                ) != expected_nonce
                            ):
                                raise ValueError
                    except (TypeError, ValueError, ProjectionHistoryError) as exc:
                        raise ProjectionHistoryError("projection_history_integrity_error") from exc
                return retained_pointer
            raise ProjectionHistoryError("projection_history_integrity_error")
        pointer_id = (
            "semantic_ingestion:conflict-authority:pointer:"
            f"{transition.conflict_id}"
        )
        pointer_record = self._memory_plane.get_record(pointer_id)
        head_record = self._memory_plane.get_record(_CONFLICT_LEDGER_HEAD_ID)
        try:
            if pointer_record is None or head_record is None:
                raise ValueError
            pointer = ActiveSemanticConflict.model_validate(
                _decode_conflict_authority_record(pointer_record)[1]
            )
            head = SemanticConflictLedgerHead.model_validate(
                _decode_conflict_authority_record(head_record)[1]
            )
            if (
                head.repository_id != self._repository_id
                or transition.record_coordinate != head.last_record_coordinate + 1
                or transition.transition_coordinate != pointer.pointer_revision + 1
                or transition.predecessor_conflict_revision
                != pointer.current_conflict_revision
                or transition.predecessor_record_digest != pointer.current_record_digest
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, ProjectionHistoryError) as exc:
            raise ProjectionHistoryError("stale_materialized_projection") from exc
        # The current payload is authoritative for the predecessor status.
        current = self._current_semantic_conflicts().get(transition.conflict_id)
        if current is None:
            raise ProjectionHistoryError("stale_materialized_projection")
        predecessor = current[1]
        predecessor_status = (
            predecessor.status
            if isinstance(predecessor, SemanticConflictIntroduction)
            else predecessor.resulting_attention.status
        )
        if transition.predecessor_status != predecessor_status:
            raise ProjectionHistoryError("stale_materialized_projection")
        generation_id = (
            "semantic_ingestion:conflict-authority:clarification-submission:"
            f"{submission_generation.generation_digest}"
            if submission_generation is not None
            else None
        )
        if generation_id is not None:
            existing_generation = self._memory_plane.get_record(generation_id)
            if existing_generation is not None:
                try:
                    generation_type, generation_payload, _ = _decode_conflict_authority_record(existing_generation)
                    retained_generation = decode_persisted_conflict_generation(
                        generation_payload, SemanticConflictClarificationSubmissionGeneration
                    )
                except (TypeError, ValueError, ProjectionHistoryError) as exc:
                    raise ProjectionHistoryError("projection_history_integrity_error") from exc
                if generation_type != "clarification_submission" or retained_generation != submission_generation:
                    raise ProjectionHistoryError("projection_history_integrity_error")
        existing_transition = self._memory_plane.get_record(transition_id)
        if generation_id is not None and self._memory_plane.get_record(generation_id) is not None and existing_transition is None:
            raise ProjectionHistoryError("projection_history_integrity_error")
        if existing_transition is not None:
            try:
                existing_type, existing_payload, _ = _decode_conflict_authority_record(
                    existing_transition
                )
                existing = decode_persisted_conflict_generation(
                    existing_payload, SemanticConflictClarificationTransition
                )
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise ProjectionHistoryError("projection_history_integrity_error") from exc
            if existing_type != "clarification_transition" or existing != transition:
                raise ProjectionHistoryError("projection_history_integrity_error")
            current_pointer = self._memory_plane.get_record(pointer_id)
            if current_pointer is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            try:
                retained = ActiveSemanticConflict.model_validate(
                    _decode_conflict_authority_record(current_pointer)[1]
                )
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise ProjectionHistoryError("projection_history_integrity_error") from exc
            if (
                retained.current_record_id == transition_id
                and retained.current_record_digest == transition.transition_digest
            ):
                return retained
            raise ProjectionHistoryError("stale_materialized_projection")
        pointer_body = {
            "conflict_id": transition.conflict_id,
            "current_conflict_revision": transition.resulting_attention.conflict_revision,
            "current_record_id": transition_id,
            "current_record_digest": transition.transition_digest,
            "pointer_revision": pointer.pointer_revision + 1,
            "predecessor_pointer_digest": pointer.pointer_digest,
        }
        successor_pointer = ActiveSemanticConflict(
            **pointer_body,
            pointer_digest=sha256(
                b"memorii.semantic-conflict-active-pointer.v1\0"
                + encode_typed_value(pointer_body)
            ).hexdigest(),
        )
        history_id = (
            "semantic_ingestion:conflict-authority:pointer-history:"
            f"{transition.conflict_id}:{successor_pointer.pointer_revision}"
        )
        successor_head = SemanticConflictLedgerHead.create(
            repository_id=self._repository_id,
            last_record_coordinate=transition.record_coordinate,
            head_revision=head.head_revision + 1,
            predecessor_head_digest=head.head_digest,
        )
        timestamp = self._now()
        submission_member_records: tuple[CanonicalMemoryRecord, ...] = ()
        submission_member_preconditions: tuple[MemoryPlanePrecondition, ...] = ()
        if submission_generation is not None:
            work_member_id = (
                "semantic_ingestion:conflict-authority:clarification-work-member:"
                f"{submission_generation.work.work_digest}"
            )
            retained_work_member = self._memory_plane.get_record(work_member_id)
            if retained_work_member is not None:
                try:
                    member_type, member_payload, _ = _decode_conflict_authority_record(
                        retained_work_member
                    )
                    retained_work = decode_persisted_conflict_generation(
                        member_payload, ConflictClarificationWork
                    )
                except (TypeError, ValueError, ProjectionHistoryError) as exc:
                    raise ProjectionHistoryError("projection_history_integrity_error") from exc
                if (
                    member_type != "clarification_work_member"
                    or retained_work != submission_generation.work
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
            else:
                submission_member_records = (
                    self._conflict_authority_record(
                        work_member_id, submission_generation.work, timestamp
                    ),
                )
                submission_member_preconditions = (
                    RecordAbsentPrecondition(memory_id=work_member_id),
                )
        records = (
            *((self._conflict_authority_record(generation_id, submission_generation, timestamp),)
              if generation_id is not None and self._memory_plane.get_record(generation_id) is None else ()),
            *submission_member_records,
            self._conflict_authority_record(transition_id, transition, timestamp),
            self._conflict_authority_record(history_id, successor_pointer, timestamp),
            self._conflict_authority_record(pointer_id, successor_pointer, timestamp),
            self._conflict_authority_record(_CONFLICT_LEDGER_HEAD_ID, successor_head, timestamp),
        )
        try:
            self._memory_plane.conditionally_write_records(
                records,
                preconditions=(
                    *((RecordAbsentPrecondition(memory_id=generation_id),)
                      if generation_id is not None and self._memory_plane.get_record(generation_id) is None else ()),
                    *submission_member_preconditions,
                    RecordAbsentPrecondition(memory_id=transition_id),
                    RecordAbsentPrecondition(memory_id=history_id),
                    RecordDigestPrecondition(memory_id=pointer_id, expected_digest=record_digest(pointer_record)),
                    RecordDigestPrecondition(memory_id=_CONFLICT_LEDGER_HEAD_ID, expected_digest=record_digest(head_record)),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            raise ProjectionHistoryError("stale_materialized_projection") from exc
        return successor_pointer

    def prepare_clarification_transition_closure(
        self,
        transition: SemanticConflictClarificationTransition,
        *,
        submission_generation: SemanticConflictClarificationSubmissionGeneration | None = None,
        include_ledger_head: bool = True,
    ) -> PreparedClarificationTransitionClosure:
        """Prepare, but do not publish, one clarification lifecycle CAS.

        The caller owns the one composite transaction, including the replay
        authority that binds this pointer advance.  A submitted transition has
        one mandatory generation and initial work member; keeping them here
        prevents a detached submission/pointer write.
        """
        transition = SemanticConflictClarificationTransition.model_validate(
            transition.model_dump(mode="python")
        )
        if transition.reason.value == "submitted" and submission_generation is None:
            raise ProjectionHistoryError("projection_publication_unauthorized")
        if transition.reason.value != "submitted" and submission_generation is not None:
            raise ProjectionHistoryError("projection_history_integrity_error")
        if submission_generation is not None:
            submission_generation = SemanticConflictClarificationSubmissionGeneration.model_validate(
                submission_generation.model_dump(mode="python")
            )
            if submission_generation.transition != transition:
                raise ProjectionHistoryError("projection_history_integrity_error")
            expected_processing_operation = conflict_clarification_processing_operation_id(
                repository_id=self._repository_id,
                conflict_revision=transition.resulting_attention.conflict_revision,
                proposal_digest=submission_generation.proposal.proposal_digest,
                policy_fingerprint=submission_generation.work.policy_fingerprint,
            )
            if submission_generation.work.processing_operation_id != expected_processing_operation:
                raise ProjectionHistoryError("projection_history_integrity_error")
        transition_id = (
            "semantic_ingestion:conflict-authority:clarification-transition:"
            f"{transition.transition_digest}"
        )
        pointer_id = (
            "semantic_ingestion:conflict-authority:pointer:"
            f"{transition.conflict_id}"
        )
        pointer_record = self._memory_plane.get_record(pointer_id)
        head_record = self._memory_plane.get_record(_CONFLICT_LEDGER_HEAD_ID)
        if self._memory_plane.get_record(transition_id) is not None:
            raise ProjectionHistoryError("projection_history_integrity_error")
        try:
            if pointer_record is None or head_record is None:
                raise ValueError
            pointer = ActiveSemanticConflict.model_validate(
                _decode_conflict_authority_record(pointer_record)[1]
            )
            head = SemanticConflictLedgerHead.model_validate(
                _decode_conflict_authority_record(head_record)[1]
            )
            current = self._current_semantic_conflicts().get(transition.conflict_id)
            if current is None:
                raise ValueError
            predecessor = current[1]
            predecessor_status = (
                predecessor.status
                if isinstance(predecessor, SemanticConflictIntroduction)
                else predecessor.resulting_attention.status
            )
            if (
                head.repository_id != self._repository_id
                or transition.record_coordinate != head.last_record_coordinate + 1
                or transition.transition_coordinate != pointer.pointer_revision + 1
                or transition.predecessor_conflict_revision
                != pointer.current_conflict_revision
                or transition.predecessor_record_digest != pointer.current_record_digest
                or transition.predecessor_status != predecessor_status
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, ProjectionHistoryError) as exc:
            raise ProjectionHistoryError("stale_materialized_projection") from exc
        pointer_body = {
            "conflict_id": transition.conflict_id,
            "current_conflict_revision": transition.resulting_attention.conflict_revision,
            "current_record_id": transition_id,
            "current_record_digest": transition.transition_digest,
            "pointer_revision": pointer.pointer_revision + 1,
            "predecessor_pointer_digest": pointer.pointer_digest,
        }
        successor = ActiveSemanticConflict(
            **pointer_body,
            pointer_digest=sha256(
                b"memorii.semantic-conflict-active-pointer.v1\0"
                + encode_typed_value(pointer_body)
            ).hexdigest(),
        )
        history_id = (
            "semantic_ingestion:conflict-authority:pointer-history:"
            f"{transition.conflict_id}:{successor.pointer_revision}"
        )
        successor_head = SemanticConflictLedgerHead.create(
            repository_id=self._repository_id,
            last_record_coordinate=transition.record_coordinate,
            head_revision=head.head_revision + 1,
            predecessor_head_digest=head.head_digest,
        )
        timestamp = self._now()
        submission_records: tuple[CanonicalMemoryRecord, ...] = ()
        submission_preconditions: tuple[MemoryPlanePrecondition, ...] = ()
        if submission_generation is not None:
            generation_id = (
                "semantic_ingestion:conflict-authority:clarification-submission:"
                f"{submission_generation.generation_digest}"
            )
            work_member_id = (
                "semantic_ingestion:conflict-authority:clarification-work-member:"
                f"{submission_generation.work.work_digest}"
            )
            operation = SemanticConflictClarificationSubmissionOperation.create(
                operation_id=submission_generation.operation_receipt.operation_id,
                request_digest=submission_generation.operation_receipt.request_digest,
                proposal_digest=submission_generation.operation_receipt.proposal_digest,
                operation_receipt_digest=submission_generation.operation_receipt.receipt_digest,
                generation_digest=submission_generation.generation_digest,
                verified_confirmation_digest=submission_generation.operation_receipt.verified_confirmation_digest,
            )
            operation_id = (
                "semantic_ingestion:conflict-authority:clarification-submission-operation:"
                f"{operation.operation_id}"
            )
            nonce_consumption = None
            nonce_id = None
            proof_id = None
            if submission_generation.verified_confirmation is not None:
                proof_id = (
                    "semantic_ingestion:conflict-authority:clarification-confirmation-proof:"
                    f"{verified_user_confirmation_digest(submission_generation.verified_confirmation)}"
                )
                nonce_consumption = SemanticConflictClarificationNonceConsumption.create(
                    nonce_digest=verified_user_confirmation_nonce_digest(
                        submission_generation.verified_confirmation
                    ),
                    verified_confirmation_digest=verified_user_confirmation_digest(
                        submission_generation.verified_confirmation
                    ),
                    operation_id=operation.operation_id,
                )
                nonce_id = (
                    "semantic_ingestion:conflict-authority:clarification-nonce-consumption:"
                    f"{nonce_consumption.nonce_digest}"
                )
            if (
                self._memory_plane.get_record(generation_id) is not None
                or self._memory_plane.get_record(work_member_id) is not None
                or self._memory_plane.get_record(operation_id) is not None
                or (proof_id is not None and self._memory_plane.get_record(proof_id) is not None)
                or (nonce_id is not None and self._memory_plane.get_record(nonce_id) is not None)
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            submission_records = (
                self._conflict_authority_record(generation_id, submission_generation, timestamp),
                self._conflict_authority_record(operation_id, operation, timestamp),
                *((self._conflict_authority_record(
                    proof_id, submission_generation.verified_confirmation, timestamp
                ),) if proof_id is not None and submission_generation.verified_confirmation is not None else ()),
                *((self._conflict_authority_record(nonce_id, nonce_consumption, timestamp),)
                  if nonce_id is not None and nonce_consumption is not None else ()),
                self._conflict_authority_record(work_member_id, submission_generation.work, timestamp),
            )
            submission_preconditions = (
                RecordAbsentPrecondition(memory_id=generation_id),
                RecordAbsentPrecondition(memory_id=operation_id),
                *((RecordAbsentPrecondition(memory_id=proof_id),) if proof_id is not None else ()),
                *((RecordAbsentPrecondition(memory_id=nonce_id),) if nonce_id is not None else ()),
                RecordAbsentPrecondition(memory_id=work_member_id),
            )
        return PreparedClarificationTransitionClosure(
            successor=successor,
            records=(
                *submission_records,
                self._conflict_authority_record(transition_id, transition, timestamp),
                self._conflict_authority_record(history_id, successor, timestamp),
                self._conflict_authority_record(pointer_id, successor, timestamp),
                *((self._conflict_authority_record(_CONFLICT_LEDGER_HEAD_ID, successor_head, timestamp),)
                  if include_ledger_head else ()),
            ),
            preconditions=(
                *submission_preconditions,
                RecordAbsentPrecondition(memory_id=transition_id),
                RecordAbsentPrecondition(memory_id=history_id),
                RecordDigestPrecondition(memory_id=pointer_id, expected_digest=record_digest(pointer_record)),
                *((RecordDigestPrecondition(memory_id=_CONFLICT_LEDGER_HEAD_ID, expected_digest=record_digest(head_record)),)
                  if include_ledger_head else ()),
            ),
        )

    def current_clarification_work(self) -> dict[str, CurrentClarificationWork]:
        """Reconstruct submitted clarification queue state from canonical records.

        Work has no mutable head record.  Its immutable predecessor chain is
        therefore the authority for ownership, and any fork, orphan, or
        attempt that does not match the current owner is corruption.
        """
        current_conflicts = self._current_semantic_conflicts()
        submissions: dict[str, SemanticConflictClarificationSubmissionGeneration] = {}
        successors: dict[str, SemanticConflictClarificationWorkGeneration] = {}
        all_generations: list[SemanticConflictClarificationWorkGeneration] = []
        work_members: dict[str, ConflictClarificationWork] = {}
        attempt_members: dict[str, ConflictClarificationAttempt] = {}
        result_members: dict[str, ConflictClarificationAttemptResult] = {}
        for record in self._memory_plane.list_records():
            if record.source_kind != "semantic_ingestion_conflict_authority":
                continue
            try:
                record_type, payload, _ = _decode_conflict_authority_record(record)
                if record_type == "clarification_submission":
                    generation = decode_persisted_conflict_generation(
                        payload, SemanticConflictClarificationSubmissionGeneration
                    )
                    if record.memory_id != (
                        "semantic_ingestion:conflict-authority:clarification-submission:"
                        f"{generation.generation_digest}"
                    ) or generation.work.work_digest in submissions:
                        raise ValueError
                    submissions[generation.work.work_digest] = generation
                elif record_type == "clarification_work":
                    generation = decode_persisted_conflict_generation(
                        payload, SemanticConflictClarificationWorkGeneration
                    )
                    if record.memory_id != (
                        "semantic_ingestion:conflict-authority:clarification-work:"
                        f"{generation.predecessor_work_digest}"
                    ) or generation.predecessor_work_digest in successors:
                        raise ValueError
                    successors[generation.predecessor_work_digest] = generation
                    all_generations.append(generation)
                elif record_type == "clarification_work_member":
                    member = decode_persisted_conflict_generation(
                        payload, ConflictClarificationWork
                    )
                    if (
                        record.memory_id
                        != "semantic_ingestion:conflict-authority:clarification-work-member:"
                        f"{member.work_digest}"
                        or member.work_digest in work_members
                    ):
                        raise ValueError
                    work_members[member.work_digest] = member
                elif record_type == "clarification_attempt_member":
                    member = decode_persisted_conflict_generation(
                        payload, ConflictClarificationAttempt
                    )
                    if (
                        record.memory_id
                        != "semantic_ingestion:conflict-authority:clarification-attempt-member:"
                        f"{member.attempt_digest}"
                        or member.attempt_digest in attempt_members
                    ):
                        raise ValueError
                    attempt_members[member.attempt_digest] = member
                elif record_type == "clarification_attempt_result_member":
                    member = decode_persisted_conflict_generation(
                        payload, ConflictClarificationAttemptResult
                    )
                    if (
                        record.memory_id
                        != "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
                        f"{member.result_digest}"
                        or member.result_digest in result_members
                    ):
                        raise ValueError
                    result_members[member.result_digest] = member
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise ProjectionHistoryError("projection_history_integrity_error") from exc

        expected_works = {submission.work.work_digest: submission.work for submission in submissions.values()}
        expected_attempts: dict[str, ConflictClarificationAttempt] = {}
        expected_results: dict[str, ConflictClarificationAttemptResult] = {}
        for generation in all_generations:
            expected_works[generation.work.work_digest] = generation.work
            if generation.attempt is not None:
                expected_attempts[generation.attempt.attempt_digest] = generation.attempt
            if generation.attempt_result is not None:
                expected_results[generation.attempt_result.result_digest] = generation.attempt_result
        if (
            work_members != expected_works
            or attempt_members != expected_attempts
            or result_members != expected_results
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")

        states: dict[str, CurrentClarificationWork] = {}
        consumed_successors: set[str] = set()
        for _root_digest, submission in submissions.items():
            current = submission.work
            attempt: ConflictClarificationAttempt | None = None
            last_successor: SemanticConflictClarificationWorkGeneration | None = None
            while (successor := successors.get(current.work_digest)) is not None:
                consumed_successors.add(successor.generation_digest)
                last_successor = successor
                previous = current
                current = successor.work
                if (
                    current.conflict_id != previous.conflict_id
                    or current.conflict_revision != previous.conflict_revision
                    or current.proposal_digest != previous.proposal_digest
                    or current.processing_operation_id != previous.processing_operation_id
                    or current.work_revision != previous.work_revision + 1
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
                if previous.owner_token is None:
                    if successor.attempt is None:
                        # A projection may win while submitted work is still
                        # unclaimed. It closes the work without inventing an
                        # attempt result or consuming retry budget.
                        if (
                            successor.attempt_result is not None
                            or current.owner_token is not None
                            or current.ownership_epoch != previous.ownership_epoch
                            or current.attempt_count != previous.attempt_count
                        ):
                            raise ProjectionHistoryError("projection_history_integrity_error")
                        attempt = None
                    elif (
                        current.ownership_epoch != previous.ownership_epoch + 1
                        or current.attempt_count != previous.attempt_count
                    ):
                        raise ProjectionHistoryError("projection_history_integrity_error")
                    else:
                        attempt = successor.attempt
                else:
                    result = successor.attempt_result
                    if successor.attempt is not None:
                        # Lease reclaim closes the abandoned attempt and starts
                        # a fresh epoch without consuming retry budget.
                        if (
                            attempt is None
                            or result is None
                            or result.outcome.value != "lease_expired"
                            or result.attempt_digest != attempt.attempt_digest
                            or current.owner_token is None
                            or current.ownership_epoch != previous.ownership_epoch + 1
                            or current.attempt_count != previous.attempt_count
                        ):
                            raise ProjectionHistoryError("projection_history_integrity_error")
                        attempt = successor.attempt
                    elif current.owner_token is None:
                        # A non-semantic failure closes the current attempt.
                        if (
                            attempt is None
                            or result is None
                            or result.attempt_digest != attempt.attempt_digest
                            or current.ownership_epoch != previous.ownership_epoch
                        ):
                            raise ProjectionHistoryError("projection_history_integrity_error")
                        expected_count = previous.attempt_count + (
                            1 if result.outcome.value == "retryable_failure" else 0
                        )
                        if current.attempt_count != expected_count:
                            raise ProjectionHistoryError("projection_history_integrity_error")
                        attempt = None
                    elif (
                        result is not None
                        or current.owner_token != previous.owner_token
                        or current.ownership_epoch != previous.ownership_epoch
                        or current.attempt_count != previous.attempt_count
                    ):
                        raise ProjectionHistoryError("projection_history_integrity_error")
            if current.owner_token is not None and (
                attempt is None
                or attempt.ownership_epoch != current.ownership_epoch
                or attempt.owner_token_digest != sha256(current.owner_token.encode("utf-8")).hexdigest()
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            conflict = current_conflicts.get(current.conflict_id)
            # A later answer to the same conflict is a new submitted
            # generation.  Its active pointer intentionally no longer names
            # the historic exhausted chain, which remains replayable audit
            # history but is not claimable or extendable.
            if (
                conflict is not None
                and isinstance(conflict[1], SemanticConflictClarificationTransition)
                and conflict[1].transition_digest != submission.transition.transition_digest
            ):
                if (
                    last_successor is not None
                    and (
                        (
                            last_successor.transition is not None
                            and last_successor.transition.reason.value
                            == "processing_exhausted"
                        )
                        or (
                            last_successor.attempt_result is not None
                            and last_successor.attempt_result.outcome.value
                            in {"accepted", "rejected", "insufficient"}
                            and conflict[1].reason.value
                            == last_successor.attempt_result.outcome.value
                            and conflict[1].processing_operation_id
                            == current.processing_operation_id
                            and conflict[1].proposal_digest == current.proposal_digest
                        )
                    )
                ):
                    continue
                raise ProjectionHistoryError("projection_history_integrity_error")
            # Accepted, rejected, and insufficient processing outcomes close
            # the claimed queue item and move the conflict pointer away from
            # the submitted state in the same CAS.  The immutable successor
            # remains audit history, but is not a claimable work item.
            if (
                last_successor is not None
                and last_successor.attempt_result is not None
                and last_successor.attempt_result.outcome.value
                in {"accepted", "rejected", "insufficient"}
            ):
                if (
                    conflict is None
                    or not isinstance(
                        conflict[1], SemanticConflictClarificationTransition
                    )
                    or conflict[1].reason.value
                    != last_successor.attempt_result.outcome.value
                    or conflict[1].processing_operation_id
                    != current.processing_operation_id
                    or conflict[1].proposal_digest != current.proposal_digest
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
                continue
            if (
                last_successor is not None
                and (
                    last_successor.attempt_result is None
                    or last_successor.attempt_result.outcome.value == "superseded"
                )
                and conflict is not None
                and isinstance(conflict[1], SemanticConflictProjectionTransition)
            ):
                if (
                    last_successor.attempt_result is not None
                        and last_successor.attempt_result.superseded_by_conflict_revision
                    != conflict[2].current_conflict_revision
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
                continue
            if (
                conflict is None
                or not isinstance(conflict[1], SemanticConflictClarificationTransition)
                or conflict[1].resulting_attention.status != ConflictStatus.CLARIFICATION_SUBMITTED
                # Proposal identifies the OPEN revision it answered; work is
                # fenced to the successor submitted lifecycle revision.
                or conflict[1].resulting_attention.conflict_revision != current.conflict_revision
                or conflict[1].proposal_digest != current.proposal_digest
                or current.conflict_id in states
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            states[current.conflict_id] = CurrentClarificationWork(
                proposal=submission.proposal,
                work=current,
                attempt=attempt,
            )
        if len(consumed_successors) != len(all_generations):
            raise ProjectionHistoryError("projection_history_integrity_error")
        return states

    def _clarification_generation_member_records(
        self,
        generation: SemanticConflictClarificationWorkGeneration,
        timestamp: datetime,
    ) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[MemoryPlanePrecondition, ...]]:
        """Materialize the exact CAS-addressable members of one work closure."""
        members: list[tuple[str, BaseModel]] = [
            (
                "semantic_ingestion:conflict-authority:clarification-work-member:"
                f"{generation.work.work_digest}",
                generation.work,
            )
        ]
        if generation.attempt is not None:
            members.append((
                "semantic_ingestion:conflict-authority:clarification-attempt-member:"
                f"{generation.attempt.attempt_digest}",
                generation.attempt,
            ))
        if generation.attempt_result is not None:
            members.append((
                "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
                f"{generation.attempt_result.result_digest}",
                generation.attempt_result,
            ))
        records: list[CanonicalMemoryRecord] = []
        preconditions: list[MemoryPlanePrecondition] = []
        for member_id, member in members:
            existing = self._memory_plane.get_record(member_id)
            if existing is not None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            records.append(self._conflict_authority_record(member_id, member, timestamp))
            preconditions.append(RecordAbsentPrecondition(memory_id=member_id))
        return tuple(records), tuple(preconditions)

    def _validate_clarification_generation_members(
        self,
        generation: SemanticConflictClarificationWorkGeneration,
    ) -> None:
        expected_values: list[tuple[str, BaseModel]] = [
            (
                "semantic_ingestion:conflict-authority:clarification-work-member:"
                f"{generation.work.work_digest}",
                generation.work,
            )
        ]
        if generation.attempt is not None:
            expected_values.append((
                "semantic_ingestion:conflict-authority:clarification-attempt-member:"
                f"{generation.attempt.attempt_digest}",
                generation.attempt,
            ))
        if generation.attempt_result is not None:
            expected_values.append((
                "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
                f"{generation.attempt_result.result_digest}",
                generation.attempt_result,
            ))
        model_by_type: dict[str, type[BaseModel]] = {
            "clarification_work_member": ConflictClarificationWork,
            "clarification_attempt_member": ConflictClarificationAttempt,
            "clarification_attempt_result_member": ConflictClarificationAttemptResult,
        }
        for member_id, expected_value in expected_values:
            record = self._memory_plane.get_record(member_id)
            try:
                if record is None:
                    raise ValueError
                record_type, payload, _ = _decode_conflict_authority_record(record)
                if (
                    record_type not in model_by_type
                    or decode_persisted_conflict_generation(
                        payload, model_by_type[record_type]
                    )
                    != expected_value
                ):
                    raise ValueError
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise ProjectionHistoryError("projection_history_integrity_error") from exc

    def append_clarification_work_generation(
        self,
        generation: SemanticConflictClarificationWorkGeneration,
        *,
        authorization: SemanticWriterWriteAuthorization,
        prepare_only: bool = False,
    ) -> SemanticConflictClarificationWorkGeneration | tuple[
        tuple[CanonicalMemoryRecord, ...], tuple[MemoryPlanePrecondition, ...]
    ]:
        """CAS one claim/renewal work successor against its exact predecessor."""
        generation = SemanticConflictClarificationWorkGeneration.model_validate(
            generation.model_dump(mode="python")
        )
        record_id = (
            "semantic_ingestion:conflict-authority:clarification-work:"
            f"{generation.predecessor_work_digest}"
        )
        # Retry the retained predecessor-keyed child before interpreting the
        # current leaf.  A lost acknowledgement necessarily means the active
        # leaf is already the successor, while the exact immutable generation
        # is still the only legal response.
        existing = self._memory_plane.get_record(record_id)
        if existing is not None:
            try:
                record_type, payload, _ = _decode_conflict_authority_record(existing)
                retained = decode_persisted_conflict_generation(
                    payload, SemanticConflictClarificationWorkGeneration
                )
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise ProjectionHistoryError("projection_history_integrity_error") from exc
            if record_type == "clarification_work" and retained == generation:
                self._validate_clarification_generation_members(generation)
                if prepare_only:
                    raise ProjectionHistoryError("projection_history_integrity_error")
                return retained
            raise ProjectionHistoryError("projection_history_integrity_error")
        current = self._current_semantic_conflicts().get(generation.work.conflict_id)
        if (
            current is None
            or not isinstance(current[1], SemanticConflictClarificationTransition)
            or current[1].resulting_attention.status != ConflictStatus.CLARIFICATION_SUBMITTED
        ):
            raise ProjectionHistoryError("stale_materialized_projection")
        # Reconstructing the queue first binds the predecessor to the one
        # currently submitted generation.  This rejects a stale child from an
        # exhausted generation after a later user resubmission before any CAS
        # record is assembled.
        try:
            active_work = self.current_clarification_work().get(generation.work.conflict_id)
        except ProjectionHistoryError:
            raise
        if (
            active_work is None
            or active_work.work.work_digest != generation.predecessor_work_digest
        ):
            raise ProjectionHistoryError("stale_materialized_projection")
        predecessor_record = None
        for record in self._memory_plane.list_records():
            if record.source_kind != "semantic_ingestion_conflict_authority":
                continue
            try:
                record_type, payload, _ = _decode_conflict_authority_record(record)
                work = (
                    decode_persisted_conflict_generation(
                        payload, SemanticConflictClarificationSubmissionGeneration
                    ).work
                    if record_type == "clarification_submission"
                    else decode_persisted_conflict_generation(
                        payload, SemanticConflictClarificationWorkGeneration
                    ).work
                    if record_type == "clarification_work"
                    else None
                )
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise ProjectionHistoryError("projection_history_integrity_error") from exc
            if work is not None and work.work_digest == generation.predecessor_work_digest:
                predecessor_record = record
        if predecessor_record is None:
            raise ProjectionHistoryError("stale_materialized_projection")
        # A work successor is keyed by the immutable predecessor, rather than
        # by its own digest.  That makes the append a real single-successor
        # CAS: two claimers cannot both create distinct children for one work
        # image, while an acknowledgement retry retains the same child.
        timestamp = self._now()
        record = self._conflict_authority_record(record_id, generation, timestamp)
        member_records, member_preconditions = self._clarification_generation_member_records(
            generation, timestamp
        )
        records: tuple[CanonicalMemoryRecord, ...] = (record, *member_records)
        preconditions: tuple[MemoryPlanePrecondition, ...] = (
            RecordAbsentPrecondition(memory_id=record_id),
            RecordDigestPrecondition(
                memory_id=predecessor_record.memory_id,
                expected_digest=record_digest(predecessor_record),
            ),
            *member_preconditions,
        )
        if prepare_only and generation.transition is None:
            return records, preconditions
        if generation.transition is not None:
            transition = generation.transition
            pointer_id = f"semantic_ingestion:conflict-authority:pointer:{transition.conflict_id}"
            pointer_record = self._memory_plane.get_record(pointer_id)
            head_record = self._memory_plane.get_record(_CONFLICT_LEDGER_HEAD_ID)
            if pointer_record is None or head_record is None:
                raise ProjectionHistoryError("stale_materialized_projection")
            try:
                pointer = ActiveSemanticConflict.model_validate(
                    _decode_conflict_authority_record(pointer_record)[1]
                )
                head = SemanticConflictLedgerHead.model_validate(
                    _decode_conflict_authority_record(head_record)[1]
                )
                if (
                    transition.predecessor_conflict_revision != pointer.current_conflict_revision
                    or transition.predecessor_record_digest != pointer.current_record_digest
                    or transition.predecessor_status != ConflictStatus.CLARIFICATION_SUBMITTED
                    or transition.record_coordinate != head.last_record_coordinate + 1
                    or transition.transition_coordinate != pointer.pointer_revision + 1
                ):
                    raise ValueError
            except (TypeError, ValueError, ProjectionHistoryError) as exc:
                raise ProjectionHistoryError("stale_materialized_projection") from exc
            transition_id = (
                "semantic_ingestion:conflict-authority:clarification-transition:"
                f"{transition.transition_digest}"
            )
            successor_body = {
                "conflict_id": transition.conflict_id,
                "current_conflict_revision": transition.resulting_attention.conflict_revision,
                "current_record_id": transition_id,
                "current_record_digest": transition.transition_digest,
                "pointer_revision": pointer.pointer_revision + 1,
                "predecessor_pointer_digest": pointer.pointer_digest,
            }
            successor_pointer = ActiveSemanticConflict(
                **successor_body,
                pointer_digest=sha256(
                    b"memorii.semantic-conflict-active-pointer.v1\0" + encode_typed_value(successor_body)
                ).hexdigest(),
            )
            history_id = (
                "semantic_ingestion:conflict-authority:pointer-history:"
                f"{transition.conflict_id}:{successor_pointer.pointer_revision}"
            )
            successor_head = SemanticConflictLedgerHead.create(
                repository_id=self._repository_id,
                last_record_coordinate=transition.record_coordinate,
                head_revision=head.head_revision + 1,
                predecessor_head_digest=head.head_digest,
            )
            records = (
                record,
                *member_records,
                self._conflict_authority_record(transition_id, transition, timestamp),
                self._conflict_authority_record(history_id, successor_pointer, timestamp),
                self._conflict_authority_record(pointer_id, successor_pointer, timestamp),
                self._conflict_authority_record(_CONFLICT_LEDGER_HEAD_ID, successor_head, timestamp),
            )
            preconditions += (
                RecordAbsentPrecondition(memory_id=transition_id),
                RecordAbsentPrecondition(memory_id=history_id),
                RecordDigestPrecondition(memory_id=pointer_id, expected_digest=record_digest(pointer_record)),
                RecordDigestPrecondition(memory_id=_CONFLICT_LEDGER_HEAD_ID, expected_digest=record_digest(head_record)),
            )
        if prepare_only:
            return records, preconditions
        try:
            self._memory_plane.conditionally_write_records(
                records,
                preconditions=preconditions,
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            raise ProjectionHistoryError("stale_materialized_projection") from exc
        return generation

    def resolve_semantic_conflict_authority(
        self,
        *,
        temporal_projections: tuple[TemporalProjectionRecord, ...] = (),
        trust_projections: tuple[TrustProjectionRecord, ...] = (),
    ) -> SemanticConflictAuthorityCommitInput:
        """Resolve display authority over a server-derived provenance/scope closure."""

        requests = self._semantic_conflict_resolution_requests(
            temporal_projections=temporal_projections,
            trust_projections=trust_projections,
        )
        resolver = self._semantic_conflict_authority_resolver
        if requests and resolver is None:
            raise ProjectionHistoryError("projection_publication_unauthorized")
        resolutions = (
            resolver.resolve_semantic_conflicts(requests)
            if resolver is not None and requests
            else ()
        )
        if len(resolutions) != len(requests) or any(
            resolution.contest_key != request.contest_key
            or resolution.scope != request.scope
            for resolution, request in zip(resolutions, requests, strict=True)
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        prospective_ids = {
            self._semantic_conflict_id(resolution.contest_key)
            for resolution in resolutions
        }
        affected_projection_slots = tuple(
            projection
            for projection in (*temporal_projections, *trust_projections)
            if projection.claim_slot_key is not None
        )
        affected_slots = {
            (
                projection.claim_slot_key,
                sha256(
                    encode_typed_value(
                        projection.valid_interval.model_dump(mode="python")
                        if projection.valid_interval is not None
                        else None
                    )
                ).hexdigest(),
            )
            for projection in affected_projection_slots
        }
        current = self._current_semantic_conflicts()
        for conflict_id, (introduction, _, _) in current.items():
            partition = sha256(
                encode_typed_value(
                    introduction.valid_interval.model_dump(mode="python")
                    if introduction.valid_interval is not None
                    else None
                )
            ).hexdigest()
            if (introduction.claim_slot_key, partition) in affected_slots:
                prospective_ids.add(conflict_id)
        preconditions = []
        for conflict_id in sorted(prospective_ids, key=lambda value: value.encode("utf-8")):
            current_value = current.get(conflict_id)
            pointer = current_value[2] if current_value is not None else None
            preconditions.append(
                SemanticConflictPointerPrecondition.create(
                    conflict_id=conflict_id,
                    expected_pointer_digest=(pointer.pointer_digest if pointer is not None else None),
                    expected_pointer_revision=(pointer.pointer_revision if pointer is not None else 0),
                )
            )
        return SemanticConflictAuthorityCommitInput.create(
            resolutions=resolutions,
            pointer_preconditions=tuple(preconditions),
        )

    def _semantic_conflict_resolution_requests(
        self,
        *,
        temporal_projections: tuple[TemporalProjectionRecord, ...],
        trust_projections: tuple[TrustProjectionRecord, ...],
        provenance_read_records: dict[str, CanonicalMemoryRecord] | None = None,
    ) -> tuple[SemanticConflictAuthorityResolutionRequest, ...]:
        grouped: dict[
            tuple[SemanticClaimSlotKey, str, tuple[tuple[str, str], ...]],
            dict[str, object],
        ] = {}
        for basis, projections in (
            ("temporal", temporal_projections),
            ("trust", trust_projections),
        ):
            for projection in projections:
                if projection.outcome != "contested" or projection.claim_slot_key is None:
                    continue
                contested = tuple(
                    evidence
                    for evidence in projection.evidence
                    if evidence.authority_relation == "contested_top"
                )
                candidate_set = tuple(
                    sorted((value.candidate_id, value.candidate_digest) for value in contested)
                )
                if not 2 <= len(candidate_set) <= 16:
                    raise ProjectionHistoryError("projection_history_integrity_error")
                partition = sha256(
                    encode_typed_value(
                        projection.valid_interval.model_dump(mode="python")
                        if projection.valid_interval is not None
                        else None
                    )
                ).hexdigest()
                key = projection.claim_slot_key, partition, candidate_set
                state = grouped.setdefault(key, {"bases": set(), "evidence": {}})
                bases = state["bases"]
                evidence_by_id = state["evidence"]
                assert isinstance(bases, set) and isinstance(evidence_by_id, dict)
                bases.add(basis)
                for evidence in contested:
                    previous = evidence_by_id.setdefault(evidence.candidate_id, evidence)
                    if previous != evidence:
                        raise ProjectionHistoryError("projection_history_integrity_error")
        requests = []
        for (slot, partition, candidate_set), state in grouped.items():
            evidence_by_id = state["evidence"]
            bases = state["bases"]
            assert isinstance(evidence_by_id, dict) and isinstance(bases, set)
            scope = self._derive_semantic_conflict_scope(
                tuple(evidence_by_id[candidate_id] for candidate_id, _ in candidate_set),
                provenance_read_records=provenance_read_records,
            )
            contest_values = {
                "tenant_partition_id": scope.tenant_partition_id,
                "claim_slot_key": slot,
                "valid_time_partition_digest": partition,
                "bases": tuple(sorted(bases)),
                "candidate_set": candidate_set,
            }
            contest = SemanticConflictContestKey(
                **contest_values,
                contest_key_digest=sha256(
                    b"memorii.semantic-conflict-contest-key.v1\0"
                    + encode_typed_value(_conflict_contract_value(contest_values))
                ).hexdigest(),
            )
            requests.append(
                SemanticConflictAuthorityResolutionRequest(
                    contest_key=contest,
                    scope=scope,
                )
            )
        return tuple(
            sorted(requests, key=lambda value: value.contest_key.contest_key_digest)
        )

    def _derive_semantic_conflict_scope(
        self,
        evidence: tuple[ProjectionEvidenceRecord, ...],
        *,
        provenance_read_records: dict[str, CanonicalMemoryRecord] | None = None,
    ) -> SemanticConflictScopeBinding:
        admissions = []
        tenants = set()
        scopes = set()
        for contender in evidence:
            if (
                contender.source_id is None
                or contender.source_event_id is None
                or contender.source_event_digest is None
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            candidates = []
            for record in self._memory_plane.list_records():
                if record.source_kind != "semantic_ingestion_admission_index":
                    continue
                try:
                    fence = OperationFenceBinding.model_validate(
                        record.content["operation_fence_binding"]
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                if (
                    fence.source_id == contender.source_id
                ):
                    candidates.append((record, fence))
            if len(candidates) != 1:
                raise ProjectionHistoryError("projection_history_integrity_error")
            index, fence = candidates[0]
            source = self._memory_plane.get_record(contender.source_id)
            operation = self._memory_plane.get_record(
                f"semantic_ingestion:operation:{fence.operation_fence_id}"
            )
            required_scopes = tuple(index.content.get("required_scopes", ()))
            tenant = index.content.get("tenant_partition_id")
            required_scope_digest = index.content.get("required_scope_set_digest")
            try:
                required_scope_set = RequiredOutcomeScopeSet(
                    tenant_partition_id=tenant,
                    scopes=required_scopes,
                    required_scope_set_digest=required_scope_digest,
                )
            except (TypeError, ValueError) as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            if (
                source is None
                or operation is None
                or operation.source_kind
                != "semantic_ingestion_preplanning_control"
                or not isinstance(tenant, str)
                or not isinstance(required_scope_digest, str)
                or index.memory_id
                != f"semantic_ingestion:admission:{fence.delivery_key_digest}"
                or source_admission_source_digest(source) != fence.source_digest
                or index.content.get("delivery_key_digest") != fence.delivery_key_digest
                or index.content.get("principal_binding_digest")
                != fence.delivery_principal_binding_digest
                or required_scope_set.tenant_partition_id != tenant
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            try:
                operation_fence = OperationFenceBinding.model_validate(
                    operation.content["control"]["operation_fence"]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            if operation_fence != fence:
                raise ProjectionHistoryError("projection_history_integrity_error")
            if provenance_read_records is not None:
                for read_record in (source, index, operation):
                    previous = provenance_read_records.setdefault(
                        read_record.memory_id, read_record
                    )
                    if record_digest(previous) != record_digest(read_record):
                        raise ProjectionHistoryError(
                            "projection_history_integrity_error"
                        )
            tenants.add(tenant)
            scopes.update(required_scopes)
            admissions.append(
                ContenderAdmissionBinding(
                    candidate_id=contender.candidate_id,
                    source_id=contender.source_id,
                    source_digest=fence.source_digest,
                    admission_index_id=index.memory_id,
                    admission_index_digest=sha256(
                        encode_typed_value(index.content)
                    ).hexdigest(),
                    required_scope_set_digest=required_scope_digest,
                )
            )
        if len(tenants) != 1:
            raise ProjectionHistoryError("projection_history_integrity_error")
        scope_values = {
            "tenant_partition_id": next(iter(tenants)),
            "scope_ids": tuple(sorted(scopes)),
            "contender_admissions": tuple(
                sorted(admissions, key=lambda value: value.candidate_id)
            ),
        }
        return SemanticConflictScopeBinding(
            **scope_values,
            scope_digest=sha256(
                b"memorii.semantic-conflict-scope.v1\0"
                + encode_typed_value(_conflict_contract_value(scope_values))
            ).hexdigest(),
        )

    def _semantic_conflict_id(self, contest: SemanticConflictContestKey) -> str:
        return sha256(
            b"memorii.semantic-conflict-id.v1\0"
            + encode_typed_value(
                _conflict_contract_value({
                    "repository_id": self._repository_id,
                    "tenant_partition_id": contest.tenant_partition_id,
                    "claim_slot_key": contest.claim_slot_key,
                    "valid_time_partition_digest": contest.valid_time_partition_digest,
                    "bases": contest.bases,
                })
            )
        ).hexdigest()

    def _current_semantic_conflicts(
        self,
    ) -> dict[
        str,
        tuple[
            SemanticConflictIntroduction,
            SemanticConflictIntroduction | SemanticConflictProjectionTransition | SemanticConflictClarificationTransition,
            ActiveSemanticConflict,
        ],
    ]:
        # Validate the complete immutable coordinate prefix before following a
        # pointer.  A current pointer alone cannot prove that a clarification
        # edge has its required predecessor.
        self.semantic_conflict_replay_binding()
        immutable: dict[
            str, SemanticConflictIntroduction | SemanticConflictProjectionTransition | SemanticConflictClarificationTransition
        ] = {}
        submissions: dict[str, SemanticConflictClarificationSubmissionGeneration] = {}
        submission_operations: dict[str, SemanticConflictClarificationSubmissionOperation] = {}
        confirmation_proofs: dict[str, object] = {}
        nonce_consumptions: dict[str, SemanticConflictClarificationNonceConsumption] = {}
        introductions: dict[str, SemanticConflictIntroduction] = {}
        pointers: dict[str, ActiveSemanticConflict] = {}
        for record in self._memory_plane.list_records():
            if record.source_kind != "semantic_ingestion_conflict_authority":
                continue
            try:
                record_type, decoded, _ = _decode_conflict_authority_record(record)
                if record_type == "introduction":
                    introduction = decode_persisted_conflict_generation(
                        decoded, SemanticConflictIntroduction
                    )
                    immutable[record.memory_id] = introduction
                    introductions[introduction.conflict_id] = introduction
                elif record_type == "transition":
                    immutable[record.memory_id] = (
                        decode_persisted_conflict_generation(
                            decoded, SemanticConflictProjectionTransition
                        )
                    )
                elif record_type == "clarification_transition":
                    immutable[record.memory_id] = (
                        decode_persisted_conflict_generation(
                            decoded, SemanticConflictClarificationTransition
                        )
                    )
                elif record_type == "clarification_submission":
                    generation = decode_persisted_conflict_generation(
                        decoded, SemanticConflictClarificationSubmissionGeneration
                    )
                    if record.memory_id != (
                        "semantic_ingestion:conflict-authority:clarification-submission:"
                        f"{generation.generation_digest}"
                    ):
                        raise ValueError
                    submissions[generation.transition.transition_digest] = generation
                elif record_type == "clarification_submission_operation":
                    operation = decode_persisted_conflict_generation(
                        decoded, SemanticConflictClarificationSubmissionOperation
                    )
                    if record.memory_id != (
                        "semantic_ingestion:conflict-authority:clarification-submission-operation:"
                        f"{operation.operation_id}"
                    ) or operation.operation_id in submission_operations:
                        raise ValueError
                    submission_operations[operation.operation_id] = operation
                elif record_type == "clarification_confirmation_proof":
                    proof = decode_persisted_conflict_generation(decoded, VerifiedUserConfirmation)
                    proof_digest = verified_user_confirmation_digest(proof)
                    if record.memory_id != (
                        "semantic_ingestion:conflict-authority:clarification-confirmation-proof:"
                        f"{proof_digest}"
                    ) or proof_digest in confirmation_proofs:
                        raise ValueError
                    confirmation_proofs[proof_digest] = proof
                elif record_type == "clarification_nonce_consumption":
                    consumption = decode_persisted_conflict_generation(
                        decoded, SemanticConflictClarificationNonceConsumption
                    )
                    if record.memory_id != (
                        "semantic_ingestion:conflict-authority:clarification-nonce-consumption:"
                        f"{consumption.nonce_digest}"
                    ) or consumption.nonce_digest in nonce_consumptions:
                        raise ValueError
                    nonce_consumptions[consumption.nonce_digest] = consumption
                elif record_type == "active_pointer":
                    pointer = ActiveSemanticConflict.model_validate(decoded)
                    pointers[pointer.conflict_id] = pointer
            except (KeyError, TypeError, ValueError, CanonicalTypedValueError) as exc:
                raise ProjectionHistoryError("projection_history_integrity_error") from exc
        if set(introductions) != set(pointers):
            raise ProjectionHistoryError("projection_history_integrity_error")
        for transition_digest, generation in submissions.items():
            transition_id = (
                "semantic_ingestion:conflict-authority:clarification-transition:"
                f"{transition_digest}"
            )
            if immutable.get(transition_id) != generation.transition:
                raise ProjectionHistoryError("projection_history_integrity_error")
            expected_operation = SemanticConflictClarificationSubmissionOperation.create(
                operation_id=generation.operation_receipt.operation_id,
                request_digest=generation.operation_receipt.request_digest,
                proposal_digest=generation.operation_receipt.proposal_digest,
                operation_receipt_digest=generation.operation_receipt.receipt_digest,
                generation_digest=generation.generation_digest,
                verified_confirmation_digest=generation.operation_receipt.verified_confirmation_digest,
            )
            if submission_operations.get(expected_operation.operation_id) != expected_operation:
                raise ProjectionHistoryError("projection_history_integrity_error")
            if generation.verified_confirmation is None:
                if generation.operation_receipt.verified_confirmation_digest is not None:
                    raise ProjectionHistoryError("projection_history_integrity_error")
            else:
                proof_digest = verified_user_confirmation_digest(generation.verified_confirmation)
                if confirmation_proofs.get(proof_digest) != generation.verified_confirmation:
                    raise ProjectionHistoryError("projection_history_integrity_error")
                expected_consumption = SemanticConflictClarificationNonceConsumption.create(
                    nonce_digest=verified_user_confirmation_nonce_digest(generation.verified_confirmation),
                    verified_confirmation_digest=verified_user_confirmation_digest(generation.verified_confirmation),
                    operation_id=generation.operation_receipt.operation_id,
                )
                if nonce_consumptions.get(expected_consumption.nonce_digest) != expected_consumption:
                    raise ProjectionHistoryError("projection_history_integrity_error")
        # Every auxiliary record must close one submitted generation.  This
        # catches substituted operation indexes and orphan nonce use on replay.
        if len(submission_operations) != len(submissions) or len(confirmation_proofs) != sum(
            1 for generation in submissions.values() if generation.verified_confirmation is not None
        ) or len(nonce_consumptions) != sum(
            1 for generation in submissions.values() if generation.verified_confirmation is not None
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        for payload in immutable.values():
            if (
                isinstance(payload, SemanticConflictClarificationTransition)
                and payload.reason.value == "submitted"
                and payload.transition_digest not in submissions
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
        for payload in immutable.values():
            if not isinstance(payload, SemanticConflictClarificationTransition):
                continue
            predecessors = [
                candidate
                for candidate in immutable.values()
                if candidate.conflict_id == payload.conflict_id
                and (
                    candidate.introduction_digest
                    if isinstance(candidate, SemanticConflictIntroduction)
                    else candidate.transition_digest
                )
                == payload.predecessor_record_digest
            ]
            if len(predecessors) != 1:
                raise ProjectionHistoryError("projection_history_integrity_error")
            predecessor = predecessors[0]
            predecessor_revision = (
                predecessor.conflict_revision
                if isinstance(predecessor, SemanticConflictIntroduction)
                else predecessor.resulting_attention.conflict_revision
            )
            predecessor_status = (
                predecessor.status
                if isinstance(predecessor, SemanticConflictIntroduction)
                else predecessor.resulting_attention.status
            )
            predecessor_coordinate = predecessor.record_coordinate
            if (
                predecessor_revision != payload.predecessor_conflict_revision
                or predecessor_status != payload.predecessor_status
                or predecessor_coordinate + 1 != payload.record_coordinate
                or payload.transition_coordinate != payload.record_coordinate
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
        current = {}
        for conflict_id, pointer in pointers.items():
            payload = immutable.get(pointer.current_record_id)
            if payload is None or payload.conflict_id != conflict_id:
                raise ProjectionHistoryError("projection_history_integrity_error")
            if (
                isinstance(payload, SemanticConflictClarificationTransition)
                and payload.reason.value == "superseded"
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            payload_digest = (
                payload.introduction_digest
                if isinstance(payload, SemanticConflictIntroduction)
                else payload.transition_digest
            )
            if payload_digest != pointer.current_record_digest:
                raise ProjectionHistoryError("projection_history_integrity_error")
            if (
                not isinstance(payload, SemanticConflictIntroduction)
                and pointer.pointer_revision != payload.transition_coordinate
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            current[conflict_id] = (introductions[conflict_id], payload, pointer)
        return current

    def semantic_conflict_replay_binding(
        self,
        *,
        pending_records: tuple[CanonicalMemoryRecord, ...] = (),
    ) -> SemanticConflictReplayBinding:
        """Derive the prospective conflict replay binding for the same root CAS."""

        records = {
            record.memory_id: record
            for record in self._memory_plane.list_records()
            if record.source_kind == "semantic_ingestion_conflict_authority"
        }
        for record in pending_records:
            if record.source_kind == "semantic_ingestion_conflict_authority":
                records[record.memory_id] = record
        decoded_records = {
            memory_id: _decode_conflict_authority_record(record)
            for memory_id, record in records.items()
        }
        immutable = tuple(
            sorted(
                (
                    (coordinate, memory_id, record_digest(records[memory_id]))
                    for memory_id, (record_type, _, coordinate) in decoded_records.items()
                    if record_type in {"introduction", "transition", "clarification_transition"}
                    and coordinate is not None
                ),
                key=lambda value: value[0],
            )
        )
        if tuple(item[0] for item in immutable) != tuple(
            range(1, len(immutable) + 1)
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        head_values = tuple(
            decoded
            for record_type, decoded, _ in decoded_records.values()
            if record_type == "ledger_head"
        )
        if immutable and len(head_values) != 1:
            raise ProjectionHistoryError("projection_history_integrity_error")
        head = (
            SemanticConflictLedgerHead.model_validate(head_values[0])
            if head_values
            else None
        )
        if head is not None and head.last_record_coordinate != len(immutable):
            raise ProjectionHistoryError("projection_history_integrity_error")
        pointer_history = tuple(
            sorted(
                (
                    (memory_id, record_digest(record))
                    for memory_id, record in records.items()
                    if decoded_records[memory_id][0] == "pointer_history"
                ),
                key=lambda value: (value[0].encode("utf-8"), value[1]),
            )
        )
        current_pointers = tuple(
            sorted(
                (
                    (memory_id, record_digest(record))
                    for memory_id, record in records.items()
                    if decoded_records[memory_id][0] == "active_pointer"
                ),
                key=lambda value: value[0].encode("utf-8"),
            )
        )
        authority_pointers = tuple(
            sorted(
                (
                    (memory_id, record_digest(record))
                    for memory_id, record in records.items()
                    if decoded_records[memory_id][0] == "resolver_pointer"
                ),
                key=lambda value: value[0].encode("utf-8"),
            )
        )
        authority_pointer_history_values: list[
            tuple[
                str,
                str,
                int,
                str,
                str,
                ActiveSemanticConflictResolverAuthority,
            ]
        ] = []
        for memory_id, record in records.items():
            record_type, decoded, _ = decoded_records[memory_id]
            if record_type != "resolver_pointer_history":
                continue
            try:
                pointer = ActiveSemanticConflictResolverAuthority.model_validate(
                    decoded
                )
            except ValueError as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            authority_pointer_history_values.append(
                (
                    pointer.tenant_partition_id,
                    pointer.renderer_schema,
                    pointer.pointer_revision,
                    memory_id,
                    record_digest(record),
                    pointer,
                )
            )
        authority_pointer_history_values.sort(key=lambda value: value[:3])
        history_by_scope: dict[
            tuple[str, str], list[ActiveSemanticConflictResolverAuthority]
        ] = {}
        for tenant, renderer, _, _, _, pointer in authority_pointer_history_values:
            history_by_scope.setdefault((tenant, renderer), []).append(pointer)
        current_authority_by_scope: dict[
            tuple[str, str], ActiveSemanticConflictResolverAuthority
        ] = {}
        for memory_id, _ in authority_pointers:
            try:
                pointer = ActiveSemanticConflictResolverAuthority.model_validate(
                    decoded_records[memory_id][1]
                )
            except ValueError as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            current_authority_by_scope[
                (pointer.tenant_partition_id, pointer.renderer_schema)
            ] = pointer
        if set(history_by_scope) != set(current_authority_by_scope):
            raise ProjectionHistoryError("projection_history_integrity_error")
        for scope, history_values in history_by_scope.items():
            for index, pointer in enumerate(history_values, start=1):
                predecessor = history_values[index - 2] if index > 1 else None
                if (
                    pointer.pointer_revision != index
                    or pointer.predecessor_pointer_digest
                    != (predecessor.pointer_digest if predecessor else None)
                ):
                    raise ProjectionHistoryError(
                        "projection_history_integrity_error"
                    )
                authority_memory_id = (
                    "semantic_ingestion:conflict-authority:resolver:"
                    f"{pointer.authority_record_id}"
                )
                authority_value = decoded_records.get(authority_memory_id)
                if authority_value is None or authority_value[0] != "resolver_authority":
                    raise ProjectionHistoryError(
                        "projection_history_integrity_error"
                    )
                try:
                    authority = SemanticConflictResolverAuthority.model_validate(
                        authority_value[1]
                    )
                except ValueError as exc:
                    raise ProjectionHistoryError(
                        "projection_history_integrity_error"
                    ) from exc
                if (
                    authority.authority_record_id != pointer.authority_record_id
                    or authority.authority_record_digest
                    != pointer.authority_record_digest
                    or authority.tenant_partition_id != pointer.tenant_partition_id
                    or authority.renderer_schema != pointer.renderer_schema
                ):
                    raise ProjectionHistoryError(
                        "projection_history_integrity_error"
                    )
            if history_values[-1] != current_authority_by_scope[scope]:
                raise ProjectionHistoryError("projection_history_integrity_error")
        referenced_authority_ids = {
            pointer.authority_record_id
            for history_values in history_by_scope.values()
            for pointer in history_values
        }
        persisted_authority_ids = {
            SemanticConflictResolverAuthority.model_validate(decoded).authority_record_id
            for record_type, decoded, _ in decoded_records.values()
            if record_type == "resolver_authority"
        }
        if referenced_authority_ids != persisted_authority_ids:
            raise ProjectionHistoryError("projection_history_integrity_error")
        authority_pointer_history = tuple(
            value[:5] for value in authority_pointer_history_values
        )
        empty = SemanticConflictReplayBinding.genesis(self._repository_id)
        body = {
            "repository_id": self._repository_id,
            "immutable_record_count": len(immutable),
            "immutable_record_prefix_digest": (
                empty.immutable_record_prefix_digest
                if not immutable
                else sha256(
                    b"memorii.semantic-conflict-immutable-prefix.v1\0"
                    + encode_typed_value(immutable)
                ).hexdigest()
            ),
            "last_record_coordinate": immutable[-1][0] if immutable else 0,
            "last_record_id": immutable[-1][1] if immutable else None,
            "last_record_digest": immutable[-1][2] if immutable else None,
            "pointer_history_count": len(pointer_history),
            "pointer_history_prefix_digest": (
                empty.pointer_history_prefix_digest
                if not pointer_history
                else sha256(
                    b"memorii.semantic-conflict-pointer-prefix.v1\0"
                    + encode_typed_value(pointer_history)
                ).hexdigest()
            ),
            "current_pointer_set_digest": sha256(
                b"memorii.semantic-conflict-pointer-set.v1\0"
                + encode_typed_value(current_pointers)
            ).hexdigest(),
            "authority_pointer_history_count": len(authority_pointer_history),
            "authority_pointer_history_prefix_digest": (
                empty.authority_pointer_history_prefix_digest
                if not authority_pointer_history
                else sha256(
                    b"memorii.semantic-conflict-authority-pointer-history.v1\0"
                    + encode_typed_value(authority_pointer_history)
                ).hexdigest()
            ),
            "authority_pointer_set_digest": sha256(
                b"memorii.semantic-conflict-authority-pointer-set.v1\0"
                + encode_typed_value(authority_pointers)
            ).hexdigest(),
        }
        if not records:
            return empty
        return SemanticConflictReplayBinding(
            **body,
            binding_digest=sha256(
                b"memorii.semantic-conflict-replay-binding.v1\0"
                + encode_typed_value(body)
            ).hexdigest(),
        )

    def validate_semantic_conflict_replay_binding(
        self,
        binding: SemanticConflictReplayBinding,
    ) -> None:
        if binding != self.semantic_conflict_replay_binding():
            raise ProjectionHistoryError("projection_history_integrity_error")

    def publish(
        self,
        request: ProjectionCommitRequest,
        *,
        capability: object | None = None,
        authorization: SemanticWriterWriteAuthorization | None = None,
    ) -> ProjectionPublication:
        """Publish only for the registered atomic semantic writer.

        Production semantic commits use ``prepare`` and include the returned
        records in the graph/event CAS.  This method remains an exact-retry
        primitive for the owner, but cannot be used as detached authority.
        """

        self._require_publication_authority(capability, authorization)
        if request.repository_id != self._repository_id:
            raise ProjectionHistoryError("projection_history_integrity_error")
        for _ in range(2):
            prepared = self.prepare(
                request,
                capability=capability,
                authorization=authorization,
            )
            if not prepared.records:
                return prepared.publication
            try:
                self._memory_plane.conditionally_write_records(
                    prepared.records,
                    preconditions=prepared.preconditions,
                    authorization=authorization,
                )
            except MemoryPlaneRevisionConflictError:
                continue
            return prepared.publication
        prepared = self.prepare(
            request,
            capability=capability,
            authorization=authorization,
        )
        if prepared.records:
            raise MemoryPlaneRevisionConflictError("projection history publication contended")
        return prepared.publication

    def prepare(
        self,
        request: ProjectionCommitRequest,
        *,
        capability: object | None = None,
        authorization: SemanticWriterWriteAuthorization | None = None,
        pending_conflict_immutable_prefix_count: int = 0,
    ) -> PreparedProjectionPublication:
        """Prepare complete immutable authority records for a caller-owned atomic CAS."""

        self._require_publication_authority(capability, authorization)
        if pending_conflict_immutable_prefix_count < 0:
            raise ProjectionHistoryError("projection_history_integrity_error")
        if request.repository_id != self._repository_id:
            raise ProjectionHistoryError("projection_history_integrity_error")
        temporal = self._load_kind("temporal")
        trust = self._load_kind("trust")
        existing_temporal = self._certificate_for_operation(temporal, request.operation_id)
        existing_trust = self._certificate_for_operation(trust, request.operation_id)
        if (existing_temporal is None) != (existing_trust is None):
            raise ProjectionHistoryError("projection_history_integrity_error")
        if existing_temporal is not None and existing_trust is not None:
            publication = self._existing_publication(
                request,
                temporal=temporal,
                trust=trust,
                temporal_certificate=existing_temporal,
                trust_certificate=existing_trust,
            )
            self._validate_conflict_authority_retry(request)
            return PreparedProjectionPublication(publication, (), ())

        published_at = _utc(self._now())
        prior_temporal = self._last_pointer(temporal)
        prior_trust = self._last_pointer(trust)
        for prior in (prior_temporal, prior_trust):
            if prior is not None and published_at < prior.published_at:
                raise ProjectionHistoryError("projection_publication_time_regression")
        temporal_publication = self._build_temporal_publication(request, temporal, published_at)
        trust_publication = self._build_trust_publication(request, trust, published_at)
        temporal_entries = (
            *temporal.entries,
            temporal_publication.history_entry,
        )
        trust_entries = (*trust.entries, trust_publication.history_entry)
        bindings = (
            self._binding("temporal", temporal_entries),
            self._binding("trust", trust_entries),
        )
        records: list[CanonicalMemoryRecord] = []
        preconditions: list[MemoryPlanePrecondition] = []
        for projection in (
            *request.temporal_projections,
            *request.trust_projections,
        ):
            record = self._projection_record(projection, published_at)
            current = self._memory_plane.get_record(record.memory_id)
            if current is None:
                records.append(record)
                preconditions.append(RecordAbsentPrecondition(memory_id=record.memory_id))
            elif current.source_kind != record.source_kind or current.content != record.content:
                raise ProjectionHistoryError("projection_history_integrity_error")
            else:
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=current.memory_id,
                        expected_digest=record_digest(current),
                    )
                )
        publication_sets: tuple[
            tuple[
                ProjectionKind,
                _LoadedKind,
                TemporalProjectionPublication | TrustProjectionPublication,
            ],
            ...,
        ] = (
            ("temporal", temporal, temporal_publication),
            ("trust", trust, trust_publication),
        )
        for kind, loaded, publication in publication_sets:
            immutable = (
                self._authority_record(publication.certificate, kind, "certificate", published_at),
                self._authority_record(publication.generation, kind, "generation", published_at),
                self._authority_record(publication.history_entry, kind, "history_entry", published_at),
            )
            for record in immutable:
                records.append(record)
                preconditions.append(RecordAbsentPrecondition(memory_id=record.memory_id))
            active_record = self._authority_record(publication.active_pointer, kind, "active_pointer", published_at)
            records.append(active_record)
            if loaded.active_record is None:
                preconditions.append(RecordAbsentPrecondition(memory_id=active_record.memory_id))
            else:
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=loaded.active_record.memory_id,
                        expected_digest=record_digest(loaded.active_record),
                    )
                )
        publication = ProjectionPublication(
            temporal=temporal_publication,
            trust=trust_publication,
            replay_bindings=bindings,
        )
        conflict_records, conflict_preconditions = self._prepare_conflict_authority(
            request,
            published_at,
            temporal_publication=publication.temporal,
            trust_publication=publication.trust,
            pending_immutable_prefix_count=pending_conflict_immutable_prefix_count,
        )
        records.extend(conflict_records)
        preconditions.extend(conflict_preconditions)
        record_ids = tuple(record.memory_id for record in records)
        if len(record_ids) != len(set(record_ids)):
            raise ProjectionHistoryError("projection_history_integrity_error")
        return PreparedProjectionPublication(
            publication=publication,
            records=tuple(records),
            preconditions=tuple(preconditions),
        )

    def _prepare_conflict_authority(
        self,
        request: ProjectionCommitRequest
        | TemporalProjectionAdvanceRequest
        | TrustProjectionAdvanceRequest
        | TemporalPolicyMigrationAdvanceRequest
        | TrustPolicyMigrationAdvanceRequest,
        published_at: datetime,
        *,
        temporal_publication: TemporalProjectionPublication | None = None,
        trust_publication: TrustProjectionPublication | None = None,
        pending_immutable_prefix_count: int = 0,
    ) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[MemoryPlanePrecondition, ...]]:
        """Prepare the authority records before the caller's single semantic CAS.

        The commit input is host-resolved; this method independently binds it
        to the newly prepared projection output and refuses a detached or
        substituted resolution before any record is visible.
        """

        authority = request.semantic_conflict_authority
        if not authority.resolutions and not authority.pointer_preconditions:
            return (), ()
        records: list[CanonicalMemoryRecord] = []
        preconditions: list[MemoryPlanePrecondition] = []
        current_conflicts = self._current_semantic_conflicts()
        ledger_head_record = self._memory_plane.get_record(_CONFLICT_LEDGER_HEAD_ID)
        if ledger_head_record is None:
            ledger_head = None
            next_record_coordinate = 1
        else:
            record_type, decoded_head, _ = _decode_conflict_authority_record(
                ledger_head_record
            )
            if record_type != "ledger_head":
                raise ProjectionHistoryError("projection_history_integrity_error")
            try:
                ledger_head = SemanticConflictLedgerHead.model_validate(decoded_head)
            except ValueError as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            if ledger_head.repository_id != self._repository_id:
                raise ProjectionHistoryError("projection_history_integrity_error")
            next_record_coordinate = (
                ledger_head.last_record_coordinate + pending_immutable_prefix_count + 1
            )
        initial_record_coordinate = next_record_coordinate

        def allocate_record_coordinate() -> int:
            nonlocal next_record_coordinate
            coordinate = next_record_coordinate
            next_record_coordinate += 1
            return coordinate

        expected_by_id = {
            value.conflict_id: value for value in authority.pointer_preconditions
        }
        successor_ids: set[str] = set()
        for conflict_id in getattr(request, "terminal_clarification_conflict_ids", ()):
            current_value = current_conflicts.get(conflict_id)
            expected = expected_by_id.get(conflict_id)
            if (
                current_value is None
                or expected is None
                or not isinstance(
                    current_value[1], SemanticConflictClarificationTransition
                )
                or current_value[1].reason.value != "submitted"
                or current_value[1].resulting_attention.status
                != ConflictStatus.CLARIFICATION_SUBMITTED
                or current_value[2].pointer_digest != expected.expected_pointer_digest
                or current_value[2].pointer_revision != expected.expected_pointer_revision
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            # The same root CAS supplies the terminal clarification edge.  Do
            # not manufacture a competing projection transition for its live
            # submitted pointer.
            successor_ids.add(conflict_id)
        prepared_by_basis = {
            basis: value
            for basis, value in (
                ("temporal", temporal_publication),
                ("trust", trust_publication),
            )
            if value is not None
        }
        projection_by_basis = {
            "temporal": {
                value.projection_digest: value
                for value in getattr(request, "temporal_projections", ())
            },
            "trust": {
                value.projection_digest: value
                for value in getattr(request, "trust_projections", ())
            },
        }
        graph_revision = getattr(
            request, "graph_revision", getattr(request, "base_graph_revision", "")
        )
        event_batch_sequence = getattr(request, "event_batch_sequence", 0)
        event_batch_digest = getattr(
            request, "event_batch_digest", getattr(request, "cutover_digest", "")
        )
        provenance_read_records: dict[str, CanonicalMemoryRecord] = {}
        derived_resolution_requests = {
            value.contest_key.contest_key_digest: value
            for value in self._semantic_conflict_resolution_requests(
                temporal_projections=getattr(request, "temporal_projections", ()),
                trust_projections=getattr(request, "trust_projections", ()),
                provenance_read_records=provenance_read_records,
            )
        }

        def append_pointer_update(
            *,
            conflict_id: str,
            record_id: str,
            payload: SemanticConflictIntroduction
            | SemanticConflictProjectionTransition,
            conflict_revision: str,
            expected: SemanticConflictPointerPrecondition,
            existing_pointer_record: CanonicalMemoryRecord | None,
        ) -> None:
            payload_digest = (
                payload.introduction_digest
                if isinstance(payload, SemanticConflictIntroduction)
                else payload.transition_digest
            )
            pointer_body = {
                "conflict_id": conflict_id,
                "current_conflict_revision": conflict_revision,
                "current_record_id": record_id,
                "current_record_digest": payload_digest,
                "pointer_revision": expected.expected_pointer_revision + 1,
                "predecessor_pointer_digest": expected.expected_pointer_digest,
            }
            pointer = ActiveSemanticConflict(
                **pointer_body,
                pointer_digest=sha256(
                    b"memorii.semantic-conflict-active-pointer.v1\0"
                    + encode_typed_value(pointer_body)
                ).hexdigest(),
            )
            pointer_id = (
                f"semantic_ingestion:conflict-authority:pointer:{conflict_id}"
            )
            pointer_history_id = (
                "semantic_ingestion:conflict-authority:pointer-history:"
                f"{conflict_id}:{pointer.pointer_revision}"
            )
            for authority_record_id, authority_payload in (
                (record_id, payload),
                (pointer_history_id, pointer),
                (pointer_id, pointer),
            ):
                record = self._conflict_authority_record(
                    authority_record_id, authority_payload, published_at
                )
                records.append(record)
                if authority_record_id == pointer_id and existing_pointer_record is not None:
                    preconditions.append(
                        RecordDigestPrecondition(
                            memory_id=authority_record_id,
                            expected_digest=record_digest(existing_pointer_record),
                        )
                    )
                else:
                    preconditions.append(
                        RecordAbsentPrecondition(memory_id=authority_record_id)
                    )

        def append_superseded_work(
            *, conflict_id: str, successor_conflict_revision: str
        ) -> None:
            """Terminally fence submitted queue work behind a projection winner."""
            if (
                isinstance(request, ProjectionCommitRequest)
                and conflict_id in request.terminal_clarification_conflict_ids
            ):
                # This projection is the semantic effect of the clarification
                # completion that already owns the queue/pointer successor.
                # Only an independent natural projection supersedes that work.
                return
            current = current_conflicts.get(conflict_id)
            if (
                current is None
                or not isinstance(current[1], SemanticConflictClarificationTransition)
                or current[1].reason.value != "submitted"
            ):
                return
            state = self.current_clarification_work().get(conflict_id)
            if state is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            previous = state.work
            values = previous.model_dump(mode="python", exclude={"work_digest"})
            values.update(
                owner_token=None,
                lease_expires_at=None,
                downstream_receipt_digest=None,
                work_revision=previous.work_revision + 1,
                predecessor_work_digest=previous.work_digest,
            )
            provisional_work = ConflictClarificationWork.model_construct(
                **values, work_digest="0" * 64
            )
            work = ConflictClarificationWork(
                **values,
                work_digest=sha256(
                    b"memorii.conflict-clarification-work.v1\0"
                    + encode_typed_value(
                        provisional_work.model_dump(mode="json", exclude={"work_digest"})
                    )
                ).hexdigest(),
            )
            result = None
            if state.attempt is not None:
                result_values = {
                    "attempt_id": state.attempt.attempt_id,
                    "attempt_digest": state.attempt.attempt_digest,
                    "processing_operation_id": previous.processing_operation_id,
                    "ownership_epoch": state.attempt.ownership_epoch,
                    "owner_token_digest": state.attempt.owner_token_digest,
                    "outcome": ClarificationAttemptOutcome.SUPERSEDED,
                    "attempt_count_after": previous.attempt_count,
                    "downstream_receipt_digest": None,
                    "superseded_by_conflict_revision": successor_conflict_revision,
                    "completed_at": published_at,
                }
                provisional_result = ConflictClarificationAttemptResult.model_construct(
                    **result_values, result_digest="0" * 64
                )
                result = ConflictClarificationAttemptResult(
                    **result_values,
                    result_digest=sha256(
                        b"memorii.conflict-clarification-attempt-result.v1\0"
                        + encode_typed_value(
                            provisional_result.model_dump(mode="json", exclude={"result_digest"})
                        )
                    ).hexdigest(),
                )
            generation = SemanticConflictClarificationWorkGeneration.create(
                predecessor_work_digest=previous.work_digest,
                work=work,
                attempt_result=result,
            )
            generated_records, generated_preconditions = self.append_clarification_work_generation(
                generation, authorization=None, prepare_only=True  # type: ignore[arg-type]
            )
            records.extend(generated_records)
            preconditions.extend(generated_preconditions)
        for resolution in authority.resolutions:
            derived_request = derived_resolution_requests.get(
                resolution.contest_key.contest_key_digest
            )
            if (
                derived_request is None
                or derived_request.contest_key != resolution.contest_key
                or derived_request.scope != resolution.scope
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            if not (
                resolution.resolver_authority_record.status == "active"
                and resolution.resolver_authority_record.valid_from
                <= published_at
                < resolution.resolver_authority_record.valid_until
            ):
                raise ProjectionHistoryError("projection_publication_unauthorized")
            contest = resolution.contest_key
            conflict_id = sha256(
                b"memorii.semantic-conflict-id.v1\0"
                + encode_typed_value(
                    _conflict_contract_value({
                        "repository_id": request.repository_id,
                        "tenant_partition_id": contest.tenant_partition_id,
                        "claim_slot_key": contest.claim_slot_key,
                        "valid_time_partition_digest": contest.valid_time_partition_digest,
                        "bases": contest.bases,
                    })
                )
            ).hexdigest()
            pointer_id = f"semantic_ingestion:conflict-authority:pointer:{conflict_id}"
            existing_pointer = self._memory_plane.get_record(pointer_id)
            successor_ids.add(conflict_id)
            expected = expected_by_id.get(conflict_id)
            if expected is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            if existing_pointer is None:
                if expected.expected_pointer_digest is not None:
                    raise ProjectionHistoryError("stale_materialized_projection")
            else:
                try:
                    current_pointer = ActiveSemanticConflict.model_validate(
                        _decode_conflict_authority_record(existing_pointer)[1]
                    )
                except (KeyError, TypeError, ValueError, CanonicalTypedValueError) as exc:
                    raise ProjectionHistoryError("projection_history_integrity_error") from exc
                if (
                    current_pointer.pointer_digest != expected.expected_pointer_digest
                    or current_pointer.pointer_revision != expected.expected_pointer_revision
                ):
                    raise ProjectionHistoryError("stale_materialized_projection")
            bindings: list[SemanticConflictProjectionBinding] = []
            candidates: dict[str, SemanticConflictCandidateBinding] = {}
            valid_interval = None
            for basis in contest.bases:
                prepared = prepared_by_basis[basis]
                projections = projection_by_basis[basis]
                matching = tuple(
                    projection
                    for projection in projections.values()
                    if projection.outcome == "contested"
                    and projection.claim_slot_key == contest.claim_slot_key
                    and sha256(
                        encode_typed_value(
                            projection.valid_interval.model_dump(mode="python")
                            if projection.valid_interval is not None
                            else None
                        )
                    ).hexdigest()
                    == contest.valid_time_partition_digest
                    and tuple(sorted((e.candidate_id, e.candidate_digest) for e in projection.evidence if e.authority_relation == "contested_top"))
                    == contest.candidate_set
                )
                if len(matching) != 1:
                    raise ProjectionHistoryError("projection_history_integrity_error")
                projection = matching[0]
                if basis == "temporal":
                    bindings.append(
                        SemanticConflictProjectionBinding(
                            basis=basis,
                            projection_id=projection.projection_id,
                            projection_digest=projection.projection_digest,
                            generation_digest=prepared.generation.generation_digest,
                            certificate_digest=prepared.certificate.certificate_digest,
                            pointer_digest=prepared.active_pointer.pointer_digest,
                            policy_fingerprint=projection.temporal_policy_fingerprint,
                        )
                    )
                else:
                    bindings.append(
                        SemanticConflictProjectionBinding(
                            basis=basis,
                            projection_id=projection.projection_id,
                            projection_digest=projection.projection_digest,
                            generation_digest=prepared.generation.generation_digest,
                            certificate_digest=prepared.certificate.certificate_digest,
                            pointer_digest=prepared.active_pointer.pointer_digest,
                            policy_fingerprint=projection.trust_policy_fingerprint,
                            arbitration_as_of=projection.arbitration_as_of,
                        )
                    )
                valid_interval = projection.valid_interval
                admission_by_candidate = {value.candidate_id: value for value in resolution.scope.contender_admissions}
                for evidence in projection.evidence:
                    if evidence.authority_relation != "contested_top":
                        continue
                    if (
                        evidence.assertion_key is None
                        or evidence.source_event_id is None
                        or evidence.source_event_digest is None
                        or evidence.source_authority_evidence_digest is None
                        or evidence.candidate_id not in admission_by_candidate
                    ):
                        raise ProjectionHistoryError("projection_history_integrity_error")
                    admission = admission_by_candidate[evidence.candidate_id]
                    candidates[evidence.candidate_id] = SemanticConflictCandidateBinding(
                        candidate_id=evidence.candidate_id,
                        candidate_digest=evidence.candidate_digest,
                        assertion_key=evidence.assertion_key,
                        assertion_record_digest=evidence.candidate_digest,
                        source_event_id=evidence.source_event_id,
                        source_event_digest=evidence.source_event_digest,
                        source_authority_evidence_digest=evidence.source_authority_evidence_digest,
                        admission_binding_digest=sha256(encode_typed_value(admission.model_dump(mode="python"))).hexdigest(),
                        display_evidence_digest=evidence.candidate_digest,
                    )
            candidate_values = tuple(candidates[key] for key, _ in contest.candidate_set)
            if tuple(value.candidate_id for value in candidate_values) != tuple(item.candidate_id for item in resolution.scope.contender_admissions):
                raise ProjectionHistoryError("projection_history_integrity_error")
            revision_body = {
                "conflict_id": conflict_id,
                "candidates": candidate_values,
                "scope": resolution.scope,
                "projections": tuple(bindings),
                "display": resolution.display,
                "graph_revision": graph_revision,
                "event_batch_digest": event_batch_digest,
            }
            conflict_revision = sha256(
                b"memorii.semantic-conflict-revision.v1\0"
                + encode_typed_value(_conflict_contract_value(revision_body))
            ).hexdigest()
            if existing_pointer is None:
                introduction_id = (
                    "semantic_ingestion:conflict-authority:introduction:"
                    f"{conflict_revision}"
                )
                introduction_body = {
                    "repository_id": request.repository_id,
                    "conflict_id": conflict_id,
                    "conflict_revision": conflict_revision,
                    "claim_slot_key": contest.claim_slot_key,
                    "valid_interval": valid_interval,
                    "bases": contest.bases,
                    "scope": resolution.scope,
                    "candidates": candidate_values,
                    "projections": tuple(bindings),
                    "display": resolution.display,
                    "graph_revision": graph_revision,
                    "event_batch_sequence": event_batch_sequence,
                    "event_batch_digest": event_batch_digest,
                    "record_coordinate": allocate_record_coordinate(),
                    "creation_coordinate": event_batch_sequence,
                    "created_at": published_at,
                }
                # Validate and digest the same fully materialized body.  In
                # particular, Pydantic's explicit predecessor/status defaults
                # are part of the persisted introduction contract.
                introduction_body = {
                    **introduction_body,
                    "predecessor_conflict_revision": None,
                    "predecessor_record_digest": None,
                    "status": "open",
                }
                introduction = SemanticConflictIntroduction(
                    **introduction_body,
                    introduction_digest=sha256(
                        b"memorii.semantic-conflict-introduction.v1\0"
                        + encode_typed_value(
                            _conflict_contract_value(introduction_body)
                        )
                    ).hexdigest(),
                )
                append_pointer_update(
                    conflict_id=conflict_id,
                    record_id=introduction_id,
                    payload=introduction,
                    conflict_revision=conflict_revision,
                    expected=expected,
                    existing_pointer_record=None,
                )
            elif current_pointer.current_conflict_revision != conflict_revision:
                attention = ConflictAttention(
                    conflict_id=conflict_id,
                    conflict_revision=conflict_revision,
                    kind=ConflictKind.SEMANTIC_DISAGREEMENT,
                    audience=ConflictAudience.USER,
                    status=ConflictStatus.OPEN,
                    question=resolution.display.question,
                    options=resolution.display.options,
                    created_at=published_at,
                    creation_coordinate=expected.expected_pointer_revision + 1,
                    scope_digest=resolution.scope.scope_digest,
                )
                transition_body = {
                    "conflict_id": conflict_id,
                    "predecessor_conflict_revision": current_pointer.current_conflict_revision,
                    "predecessor_record_digest": current_pointer.current_record_digest,
                    "resulting_attention": attention,
                    "reason": "projection_changed",
                    "scope": resolution.scope,
                    "candidates": candidate_values,
                    "projections": tuple(bindings),
                    "display": resolution.display,
                    "graph_revision": graph_revision,
                    "event_batch_sequence": event_batch_sequence,
                    "event_batch_digest": event_batch_digest,
                    "record_coordinate": allocate_record_coordinate(),
                    "transition_coordinate": expected.expected_pointer_revision + 1,
                    "transitioned_at": published_at,
                }
                transition = SemanticConflictProjectionTransition(
                    **transition_body,
                    transition_digest=sha256(
                        b"memorii.semantic-conflict-projection-transition.v1\0"
                        + encode_typed_value(
                            _conflict_contract_value(transition_body)
                        )
                    ).hexdigest(),
                )
                transition_id = (
                    "semantic_ingestion:conflict-authority:transition:"
                    f"{transition.transition_digest}"
                )
                append_pointer_update(
                    conflict_id=conflict_id,
                    record_id=transition_id,
                    payload=transition,
                    conflict_revision=conflict_revision,
                    expected=expected,
                    existing_pointer_record=existing_pointer,
                )
                append_superseded_work(
                    conflict_id=conflict_id,
                    successor_conflict_revision=conflict_revision,
                )
            else:
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=pointer_id,
                        expected_digest=record_digest(existing_pointer),
                    )
                )
            # Resolver authority must still be current at the semantic write.
            resolver_id = f"semantic_ingestion:conflict-authority:resolver:{resolution.resolver_authority_record.authority_record_id}"
            resolver_pointer_id = (
                "semantic_ingestion:conflict-authority:resolver-pointer:"
                f"{resolution.resolver_authority_pointer.tenant_partition_id}:"
                f"{resolution.resolver_authority_pointer.renderer_schema}"
            )
            for record_id, payload in (
                (resolver_id, resolution.resolver_authority_record),
                (resolver_pointer_id, resolution.resolver_authority_pointer),
            ):
                current = self._memory_plane.get_record(record_id)
                if current is None:
                    raise ProjectionHistoryError("projection_history_integrity_error")
                try:
                    _, decoded, _ = _decode_conflict_authority_record(current)
                    actual_digest = (
                        SemanticConflictResolverAuthority.model_validate(decoded).authority_record_digest
                        if isinstance(payload, SemanticConflictResolverAuthority)
                        else ActiveSemanticConflictResolverAuthority.model_validate(decoded).pointer_digest
                    )
                except (KeyError, TypeError, ValueError, CanonicalTypedValueError) as exc:
                    raise ProjectionHistoryError("projection_history_integrity_error") from exc
                expected_digest = (
                    payload.authority_record_digest
                    if isinstance(payload, SemanticConflictResolverAuthority)
                    else payload.pointer_digest
                )
                if actual_digest != expected_digest:
                    raise ProjectionHistoryError("stale_materialized_projection")
                preconditions.append(RecordDigestPrecondition(memory_id=record_id, expected_digest=record_digest(current)))

        affected_slots = {
            (
                projection.claim_slot_key,
                sha256(
                    encode_typed_value(
                        projection.valid_interval.model_dump(mode="python")
                        if projection.valid_interval is not None
                        else None
                    )
                ).hexdigest(),
            )
            for projection in (
                *getattr(request, "temporal_projections", ()),
                *getattr(request, "trust_projections", ()),
            )
            if projection.claim_slot_key is not None
        }
        for conflict_id in sorted(set(expected_by_id) - successor_ids):
            current_value = current_conflicts.get(conflict_id)
            if current_value is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            introduction, current_payload, current_pointer = current_value
            partition = sha256(
                encode_typed_value(
                    introduction.valid_interval.model_dump(mode="python")
                    if introduction.valid_interval is not None
                    else None
                )
            ).hexdigest()
            if (introduction.claim_slot_key, partition) not in affected_slots:
                raise ProjectionHistoryError("projection_history_integrity_error")
            expected = expected_by_id[conflict_id]
            pointer_id = (
                f"semantic_ingestion:conflict-authority:pointer:{conflict_id}"
            )
            existing_pointer = self._memory_plane.get_record(pointer_id)
            if (
                existing_pointer is None
                or current_pointer.pointer_digest
                != expected.expected_pointer_digest
                or current_pointer.pointer_revision
                != expected.expected_pointer_revision
            ):
                raise ProjectionHistoryError("stale_materialized_projection")
            if (
                isinstance(
                    current_payload,
                    (
                        SemanticConflictProjectionTransition,
                        SemanticConflictClarificationTransition,
                    ),
                )
                and current_payload.resulting_attention.status
                == ConflictStatus.RESOLVED
            ):
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=pointer_id,
                        expected_digest=record_digest(existing_pointer),
                    )
                )
                continue
            resolution_revision_body = {
                "conflict_id": conflict_id,
                "predecessor_conflict_revision": current_pointer.current_conflict_revision,
                "status": ConflictStatus.RESOLVED,
                "graph_revision": graph_revision,
                "event_batch_digest": event_batch_digest,
            }
            conflict_revision = sha256(
                b"memorii.semantic-conflict-revision.v1\0"
                + encode_typed_value(
                    _conflict_contract_value(resolution_revision_body)
                )
            ).hexdigest()
            attention = ConflictAttention(
                conflict_id=conflict_id,
                conflict_revision=conflict_revision,
                kind=ConflictKind.SEMANTIC_DISAGREEMENT,
                audience=ConflictAudience.USER,
                status=ConflictStatus.RESOLVED,
                # Clarification transitions deliberately retain only their
                # lifecycle edge and resulting attention.  Display/provenance
                # stays anchored on the immutable introduction so a later
                # semantic publication cannot manufacture or dereference
                # fields that a clarification transition does not own.
                question=introduction.display.question,
                options=introduction.display.options,
                created_at=published_at,
                creation_coordinate=expected.expected_pointer_revision + 1,
                scope_digest=introduction.scope.scope_digest,
            )
            transition_body = {
                "conflict_id": conflict_id,
                "predecessor_conflict_revision": current_pointer.current_conflict_revision,
                "predecessor_record_digest": current_pointer.current_record_digest,
                "resulting_attention": attention,
                "reason": "projection_resolved",
                "scope": introduction.scope,
                "candidates": introduction.candidates,
                "projections": introduction.projections,
                "display": introduction.display,
                "graph_revision": graph_revision,
                "event_batch_sequence": event_batch_sequence,
                "event_batch_digest": event_batch_digest,
                "record_coordinate": allocate_record_coordinate(),
                "transition_coordinate": expected.expected_pointer_revision + 1,
                "transitioned_at": published_at,
            }
            transition = SemanticConflictProjectionTransition(
                **transition_body,
                transition_digest=sha256(
                    b"memorii.semantic-conflict-projection-transition.v1\0"
                    + encode_typed_value(_conflict_contract_value(transition_body))
                ).hexdigest(),
            )
            append_pointer_update(
                conflict_id=conflict_id,
                record_id=(
                    "semantic_ingestion:conflict-authority:transition:"
                    f"{transition.transition_digest}"
                ),
                payload=transition,
                conflict_revision=conflict_revision,
                expected=expected,
                existing_pointer_record=existing_pointer,
            )
            append_superseded_work(
                conflict_id=conflict_id,
                successor_conflict_revision=conflict_revision,
            )
        if next_record_coordinate != initial_record_coordinate:
            updated_head = SemanticConflictLedgerHead.create(
                repository_id=self._repository_id,
                last_record_coordinate=next_record_coordinate - 1,
                head_revision=(ledger_head.head_revision + 1 if ledger_head else 1),
                predecessor_head_digest=(ledger_head.head_digest if ledger_head else None),
            )
            records.append(
                self._conflict_authority_record(
                    _CONFLICT_LEDGER_HEAD_ID, updated_head, published_at
                )
            )
            preconditions.append(
                RecordDigestPrecondition(
                    memory_id=_CONFLICT_LEDGER_HEAD_ID,
                    expected_digest=record_digest(ledger_head_record),
                )
                if ledger_head_record is not None
                else RecordAbsentPrecondition(memory_id=_CONFLICT_LEDGER_HEAD_ID)
            )
        preconditions.extend(
            RecordDigestPrecondition(
                memory_id=memory_id,
                expected_digest=record_digest(record),
            )
            for memory_id, record in sorted(provenance_read_records.items())
        )
        return tuple(records), tuple(preconditions)

    def _validate_conflict_authority_retry(
        self,
        request: ProjectionCommitRequest
        | TemporalProjectionAdvanceRequest
        | TrustProjectionAdvanceRequest
        | TemporalPolicyMigrationAdvanceRequest
        | TrustPolicyMigrationAdvanceRequest,
    ) -> None:
        """Fail closed when a certificate survives without its authority closure."""

        authority = request.semantic_conflict_authority
        if not authority.resolutions and not authority.pointer_preconditions:
            return
        self.semantic_conflict_replay_binding()
        current = self._current_semantic_conflicts()
        expected_ids = {
            precondition.conflict_id
            for precondition in authority.pointer_preconditions
        }
        resolution_ids = {
            self._semantic_conflict_id(resolution.contest_key)
            for resolution in authority.resolutions
        }
        if not resolution_ids <= expected_ids or not expected_ids <= set(current):
            raise ProjectionHistoryError("projection_history_integrity_error")
        for resolution in authority.resolutions:
            resolver_id = (
                "semantic_ingestion:conflict-authority:resolver:"
                f"{resolution.resolver_authority_record.authority_record_id}"
            )
            resolver_record = self._memory_plane.get_record(resolver_id)
            if resolver_record is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            try:
                decoded = SemanticConflictResolverAuthority.model_validate(
                    _decode_conflict_authority_record(resolver_record)[1]
                )
            except (KeyError, TypeError, ValueError, CanonicalTypedValueError) as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            if (
                decoded.authority_record_digest
                != resolution.resolver_authority_record.authority_record_digest
            ):
                raise ProjectionHistoryError("projection_publication_diverged")

    @staticmethod
    def _conflict_authority_record(
        record_id: str,
        payload: BaseModel,
        timestamp: datetime,
    ) -> CanonicalMemoryRecord:
        raw = encode_typed_value(payload.model_dump(mode="python"))
        record_type = _conflict_authority_record_type(record_id)
        if record_type is None:
            raise ProjectionHistoryError("projection_history_integrity_error")
        immutable_coordinate = (
            payload.record_coordinate
            if isinstance(
                payload,
                (SemanticConflictIntroduction, SemanticConflictProjectionTransition, SemanticConflictClarificationTransition),
            )
            else None
        )
        return CanonicalMemoryRecord(
            memory_id=record_id,
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "authority_schema": _CONFLICT_AUTHORITY_SCHEMA,
                "authority_record_type": record_type,
                "immutable_record_coordinate": immutable_coordinate,
                "canonical_hex": raw.hex(),
                "authority_digest": sha256(raw).hexdigest(),
            },
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_conflict_authority",
            timestamp=timestamp,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )

    def prepare_trust(
        self,
        request: TrustProjectionAdvanceRequest,
        *,
        capability: object | None = None,
        authorization: SemanticWriterWriteAuthorization | None = None,
    ) -> PreparedTrustProjectionPublication:
        """Prepare one trust-only atomic successor for scheduler-owned work."""

        self._require_publication_authority(capability, authorization)
        if request.repository_id != self._repository_id:
            raise ProjectionHistoryError("projection_history_integrity_error")
        loaded = self._load_kind("trust")
        existing = self._certificate_for_operation(loaded, request.operation_id)
        if existing is not None:
            if not isinstance(existing, TrustProjectionCommitCertificate):
                raise ProjectionHistoryError("projection_publication_diverged")
            generation = loaded.generations.get(existing.output_generation_digest)
            entry = next(
                (
                    value
                    for value in loaded.entries
                    if value.pointer.publication_certificate_digest
                    == existing.certificate_digest
                ),
                None,
            )
            if (
                not isinstance(generation, TrustProjectionGeneration)
                or not isinstance(entry, TrustProjectionHistoryEntry)
                or not self._expected_trust_advance(request, existing, generation)
            ):
                raise ProjectionHistoryError("projection_publication_diverged")
            self._validate_conflict_authority_retry(request)
            return PreparedTrustProjectionPublication(
                publication=TrustProjectionPublication(
                    certificate=existing,
                    generation=generation,
                    history_entry=entry,
                    active_pointer=entry.pointer,
                ),
                records=(),
                preconditions=(),
            )
        published_at = _utc(self._now())
        prior = self._last_pointer(loaded)
        if prior is not None and published_at < prior.published_at:
            raise ProjectionHistoryError("projection_publication_time_regression")
        publication = self._build_trust_publication(request, loaded, published_at)
        records, preconditions = self._prepare_kind_records(
            kind="trust",
            loaded=loaded,
            publication=publication,
            projections=request.trust_projections,
            published_at=published_at,
        )
        conflict_records, conflict_preconditions = self._prepare_conflict_authority(
            request,
            published_at,
            trust_publication=publication,
        )
        return PreparedTrustProjectionPublication(
            publication=publication,
            records=(*records, *conflict_records),
            preconditions=(*preconditions, *conflict_preconditions),
        )

    def prepare_temporal(
        self,
        request: TemporalProjectionAdvanceRequest,
        *,
        capability: object | None = None,
        authorization: SemanticWriterWriteAuthorization | None = None,
    ) -> PreparedTemporalProjectionPublication:
        """Prepare one temporal-only atomic successor for migration work."""

        self._require_publication_authority(capability, authorization)
        if request.repository_id != self._repository_id:
            raise ProjectionHistoryError("projection_history_integrity_error")
        loaded = self._load_kind("temporal")
        existing = self._certificate_for_operation(loaded, request.operation_id)
        if existing is not None:
            if not isinstance(existing, TemporalProjectionCommitCertificate):
                raise ProjectionHistoryError("projection_publication_diverged")
            generation = loaded.generations.get(existing.output_generation_digest)
            entry = next(
                (
                    value
                    for value in loaded.entries
                    if value.pointer.publication_certificate_digest
                    == existing.certificate_digest
                ),
                None,
            )
            if (
                not isinstance(generation, TemporalProjectionGeneration)
                or not isinstance(entry, TemporalProjectionHistoryEntry)
                or not self._expected_temporal_advance(request, existing, generation)
            ):
                raise ProjectionHistoryError("projection_publication_diverged")
            self._validate_conflict_authority_retry(request)
            return PreparedTemporalProjectionPublication(
                publication=TemporalProjectionPublication(
                    certificate=existing,
                    generation=generation,
                    history_entry=entry,
                    active_pointer=entry.pointer,
                ),
                records=(),
                preconditions=(),
            )
        published_at = _utc(self._now())
        prior = self._last_pointer(loaded)
        if prior is not None and published_at < prior.published_at:
            raise ProjectionHistoryError("projection_publication_time_regression")
        publication = self._build_temporal_publication(request, loaded, published_at)
        records, preconditions = self._prepare_kind_records(
            kind="temporal",
            loaded=loaded,
            publication=publication,
            projections=request.temporal_projections,
            published_at=published_at,
        )
        conflict_records, conflict_preconditions = self._prepare_conflict_authority(
            request,
            published_at,
            temporal_publication=publication,
        )
        return PreparedTemporalProjectionPublication(
            publication=publication,
            records=(*records, *conflict_records),
            preconditions=(*preconditions, *conflict_preconditions),
        )

    def prepare_temporal_migration(
        self,
        request: TemporalPolicyMigrationAdvanceRequest,
        *,
        capability: object | None = None,
        authorization: SemanticWriterWriteAuthorization | None = None,
    ) -> PreparedTemporalProjectionPublication:
        """Prepare one all-or-nothing temporal policy cutover."""

        self._require_publication_authority(capability, authorization)
        if request.repository_id != self._repository_id:
            raise ProjectionHistoryError("projection_history_integrity_error")
        loaded = self._load_kind("temporal")
        existing = self._certificate_for_migration(
            loaded, request.migration_plan_digest
        )
        if existing is not None:
            generation = loaded.generations.get(existing.output_generation_digest)
            entry = self._entry_for_certificate(loaded, existing.certificate_digest)
            if (
                not isinstance(existing, TemporalPolicyMigrationCertificate)
                or not isinstance(generation, TemporalProjectionGeneration)
                or not isinstance(entry, TemporalProjectionHistoryEntry)
                or not self._expected_temporal_migration(
                    request, existing, generation
                )
            ):
                raise ProjectionHistoryError("projection_publication_diverged")
            self._validate_conflict_authority_retry(request)
            return PreparedTemporalProjectionPublication(
                publication=TemporalProjectionPublication(
                    certificate=existing,
                    generation=generation,
                    history_entry=entry,
                    active_pointer=entry.pointer,
                ),
                records=(),
                preconditions=(),
            )
        published_at = _utc(self._now())
        prior = self._last_pointer(loaded)
        if prior is not None and published_at < prior.published_at:
            raise ProjectionHistoryError("projection_publication_time_regression")
        publication = self._build_temporal_migration_publication(
            request, loaded, published_at
        )
        records, preconditions = self._prepare_kind_records(
            kind="temporal",
            loaded=loaded,
            publication=publication,
            projections=request.temporal_projections,
            published_at=published_at,
        )
        conflict_records, conflict_preconditions = self._prepare_conflict_authority(
            request,
            published_at,
            temporal_publication=publication,
        )
        return PreparedTemporalProjectionPublication(
            publication=publication,
            records=(*records, *conflict_records),
            preconditions=(*preconditions, *conflict_preconditions),
        )

    def prepare_trust_migration(
        self,
        request: TrustPolicyMigrationAdvanceRequest,
        *,
        capability: object | None = None,
        authorization: SemanticWriterWriteAuthorization | None = None,
    ) -> PreparedTrustProjectionPublication:
        """Prepare one all-or-nothing trust policy cutover."""

        self._require_publication_authority(capability, authorization)
        if request.repository_id != self._repository_id:
            raise ProjectionHistoryError("projection_history_integrity_error")
        loaded = self._load_kind("trust")
        existing = self._certificate_for_migration(
            loaded, request.migration_plan_digest
        )
        if existing is not None:
            generation = loaded.generations.get(existing.output_generation_digest)
            entry = self._entry_for_certificate(loaded, existing.certificate_digest)
            if (
                not isinstance(existing, TrustPolicyMigrationCertificate)
                or not isinstance(generation, TrustProjectionGeneration)
                or not isinstance(entry, TrustProjectionHistoryEntry)
                or not self._expected_trust_migration(request, existing, generation)
            ):
                raise ProjectionHistoryError("projection_publication_diverged")
            self._validate_conflict_authority_retry(request)
            return PreparedTrustProjectionPublication(
                publication=TrustProjectionPublication(
                    certificate=existing,
                    generation=generation,
                    history_entry=entry,
                    active_pointer=entry.pointer,
                ),
                records=(),
                preconditions=(),
            )
        published_at = _utc(self._now())
        prior = self._last_pointer(loaded)
        if prior is not None and published_at < prior.published_at:
            raise ProjectionHistoryError("projection_publication_time_regression")
        publication = self._build_trust_migration_publication(
            request, loaded, published_at
        )
        records, preconditions = self._prepare_kind_records(
            kind="trust",
            loaded=loaded,
            publication=publication,
            projections=request.trust_projections,
            published_at=published_at,
        )
        conflict_records, conflict_preconditions = self._prepare_conflict_authority(
            request,
            published_at,
            trust_publication=publication,
        )
        return PreparedTrustProjectionPublication(
            publication=publication,
            records=(*records, *conflict_records),
            preconditions=(*preconditions, *conflict_preconditions),
        )

    def _prepare_kind_records(
        self,
        *,
        kind: ProjectionKind,
        loaded: _LoadedKind,
        publication: TemporalProjectionPublication | TrustProjectionPublication,
        projections: tuple[TemporalProjectionRecord, ...]
        | tuple[TrustProjectionRecord, ...],
        published_at: datetime,
    ) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[MemoryPlanePrecondition, ...]]:
        records: list[CanonicalMemoryRecord] = []
        preconditions: list[MemoryPlanePrecondition] = []
        for projection in projections:
            record = self._projection_record(projection, published_at)
            current = self._memory_plane.get_record(record.memory_id)
            if current is None:
                records.append(record)
                preconditions.append(RecordAbsentPrecondition(memory_id=record.memory_id))
            elif current.source_kind != record.source_kind or current.content != record.content:
                raise ProjectionHistoryError("projection_history_integrity_error")
            else:
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=current.memory_id,
                        expected_digest=record_digest(current),
                    )
                )
        for record in (
            self._authority_record(publication.certificate, kind, "certificate", published_at),
            self._authority_record(publication.generation, kind, "generation", published_at),
            self._authority_record(publication.history_entry, kind, "history_entry", published_at),
        ):
            records.append(record)
            preconditions.append(RecordAbsentPrecondition(memory_id=record.memory_id))
        active_record = self._authority_record(
            publication.active_pointer,
            kind,
            "active_pointer",
            published_at,
        )
        records.append(active_record)
        if loaded.active_record is None:
            preconditions.append(RecordAbsentPrecondition(memory_id=active_record.memory_id))
        else:
            preconditions.append(
                RecordDigestPrecondition(
                    memory_id=loaded.active_record.memory_id,
                    expected_digest=record_digest(loaded.active_record),
                )
            )
        if len({record.memory_id for record in records}) != len(records):
            raise ProjectionHistoryError("projection_history_integrity_error")
        return tuple(records), tuple(preconditions)

    def current_temporal(
        self,
        *,
        policy_fingerprint: str,
    ) -> TemporalProjectionView:
        loaded = self._load_kind("temporal")
        if loaded.active is None:
            raise ProjectionHistoryError("projection_history_unavailable")
        if not isinstance(loaded.active, ActiveTemporalProjectionPointer):
            raise ProjectionHistoryError("projection_history_integrity_error")
        generation = loaded.generations.get(loaded.active.generation_digest)
        if not isinstance(generation, TemporalProjectionGeneration):
            raise ProjectionHistoryError("projection_history_integrity_error")
        graph_revision = self._authoritative_current_graph_revision()
        if (
            loaded.active.policy_fingerprint != policy_fingerprint
            or generation.temporal_policy_fingerprint != policy_fingerprint
            or generation.base_graph_revision != graph_revision
        ):
            raise ProjectionHistoryError("stale_materialized_projection")
        return self._temporal_view(loaded, loaded.active)

    def current_trust(
        self,
        *,
        policy_fingerprint: str,
        system_as_of: datetime | None = None,
    ) -> TrustProjectionView:
        loaded = self._load_kind("trust")
        if loaded.active is None:
            raise ProjectionHistoryError("projection_history_unavailable")
        if not isinstance(loaded.active, ActiveTrustProjectionPointer):
            raise ProjectionHistoryError("projection_history_integrity_error")
        generation = loaded.generations.get(loaded.active.generation_digest)
        if not isinstance(generation, TrustProjectionGeneration):
            raise ProjectionHistoryError("projection_history_integrity_error")
        graph_revision = self._authoritative_current_graph_revision()
        if (
            loaded.active.policy_fingerprint != policy_fingerprint
            or generation.trust_policy_fingerprint != policy_fingerprint
            or generation.base_graph_revision != graph_revision
        ):
            raise ProjectionHistoryError("stale_materialized_projection")
        requested_at = _utc(system_as_of if system_as_of is not None else self._now())
        if self._trust_has_due_unmaterialized_command(generation, requested_at):
            raise ProjectionHistoryError("stale_materialized_projection")
        return self._trust_view(loaded, loaded.active)

    def _trust_has_due_unmaterialized_command(
        self,
        generation: TrustProjectionGeneration,
        requested_at: datetime,
    ) -> bool:
        expected = set(generation.canonical_decay_command_digests)
        if not expected:
            return False
        observed: set[str] = set()
        due = False
        for record in self._records("trust", "decay_command"):
            canonical_hex = record.content.get("canonical_hex")
            if not isinstance(canonical_hex, str):
                raise ProjectionHistoryError("projection_history_integrity_error")
            try:
                value = decode_typed_value(bytes.fromhex(canonical_hex))
            except (CanonicalTypedValueError, TypeError, ValueError) as exc:
                raise ProjectionHistoryError(
                    "projection_history_integrity_error"
                ) from exc
            if not isinstance(value, dict):
                raise ProjectionHistoryError("projection_history_integrity_error")
            digest = value.get("command_digest")
            if digest not in expected:
                continue
            if not isinstance(digest, str) or digest in observed:
                raise ProjectionHistoryError("projection_history_integrity_error")
            threshold = value.get("threshold_time")
            if not isinstance(threshold, datetime):
                raise ProjectionHistoryError("projection_history_integrity_error")
            observed.add(digest)
            due = due or (
                generation.arbitration_as_of < threshold <= requested_at
            )
        if observed != expected:
            raise ProjectionHistoryError("projection_history_integrity_error")
        return due

    def contested_temporal(
        self,
        *,
        policy_fingerprint: str,
    ) -> tuple[TemporalProjectionRecord, ...]:
        """Return current contested temporal projections without inventing a winner."""

        return self.current_temporal(
            policy_fingerprint=policy_fingerprint,
        ).contested

    def contested_trust(
        self,
        *,
        policy_fingerprint: str,
    ) -> tuple[TrustProjectionRecord, ...]:
        """Return current contested trust projections without inventing a winner."""

        return self.current_trust(
            policy_fingerprint=policy_fingerprint,
        ).contested

    def historical_temporal(self, *, system_as_of: datetime) -> TemporalProjectionView:
        loaded = self._load_kind("temporal")
        pointer = self._historical_pointer(loaded, system_as_of)
        if not isinstance(pointer, ActiveTemporalProjectionPointer):
            raise ProjectionHistoryError("projection_history_integrity_error")
        return self._temporal_view(loaded, pointer)

    def historical_trust(self, *, system_as_of: datetime) -> TrustProjectionView:
        loaded = self._load_kind("trust")
        pointer = self._historical_pointer(loaded, system_as_of)
        if not isinstance(pointer, ActiveTrustProjectionPointer):
            raise ProjectionHistoryError("projection_history_integrity_error")
        return self._trust_view(loaded, pointer)

    def active_temporal_authority(self) -> TemporalProjectionView:
        """Read the persisted pointer without consulting the replay aggregate."""

        loaded = self._load_kind("temporal")
        if not isinstance(loaded.active, ActiveTemporalProjectionPointer):
            raise ProjectionHistoryError("projection_history_unavailable")
        return self._temporal_view(loaded, loaded.active)

    def active_trust_authority(self) -> TrustProjectionView:
        """Read the persisted pointer without consulting the replay aggregate."""

        loaded = self._load_kind("trust")
        if not isinstance(loaded.active, ActiveTrustProjectionPointer):
            raise ProjectionHistoryError("projection_history_unavailable")
        return self._trust_view(loaded, loaded.active)

    def completed_temporal_migration(
        self,
        migration_plan_digest: str,
    ) -> TemporalPolicyMigrationCertificate | None:
        loaded = self._load_kind("temporal")
        if loaded.active is None:
            return None
        certificate = loaded.certificates.get(
            loaded.active.publication_certificate_digest
        )
        return (
            certificate
            if isinstance(certificate, TemporalPolicyMigrationCertificate)
            and certificate.migration_plan_digest == migration_plan_digest
            else None
        )

    def completed_trust_migration(
        self,
        migration_plan_digest: str,
    ) -> TrustPolicyMigrationCertificate | None:
        loaded = self._load_kind("trust")
        if loaded.active is None:
            return None
        certificate = loaded.certificates.get(
            loaded.active.publication_certificate_digest
        )
        return (
            certificate
            if isinstance(certificate, TrustPolicyMigrationCertificate)
            and certificate.migration_plan_digest == migration_plan_digest
            else None
        )

    def replay_bindings_with_temporal(
        self,
        prepared: PreparedTemporalProjectionPublication,
    ) -> tuple[ProjectionHistoryReplayBinding, ...]:
        temporal = self._load_kind("temporal")
        trust = self._load_kind("trust")
        entries = temporal.entries
        if prepared.records:
            entries = (*entries, prepared.publication.history_entry)
        if not entries or not trust.entries:
            raise ProjectionHistoryError("projection_history_integrity_error")
        return (
            self._binding("temporal", entries),
            self._binding("trust", trust.entries),
        )

    def replay_bindings_with_trust(
        self,
        prepared: PreparedTrustProjectionPublication,
    ) -> tuple[ProjectionHistoryReplayBinding, ...]:
        temporal = self._load_kind("temporal")
        trust = self._load_kind("trust")
        entries = trust.entries
        if prepared.records:
            entries = (*entries, prepared.publication.history_entry)
        if not temporal.entries or not entries:
            raise ProjectionHistoryError("projection_history_integrity_error")
        return (
            self._binding("temporal", temporal.entries),
            self._binding("trust", entries),
        )

    def replay_bindings(self) -> tuple[ProjectionHistoryReplayBinding, ...]:
        temporal = self._load_kind("temporal")
        trust = self._load_kind("trust")
        if not temporal.entries and not trust.entries:
            return ()
        if not temporal.entries or not trust.entries:
            raise ProjectionHistoryError("projection_history_integrity_error")
        return (
            self._binding("temporal", temporal.entries),
            self._binding("trust", trust.entries),
        )

    def validate_replay_bindings(self, bindings: tuple[ProjectionHistoryReplayBinding, ...]) -> None:
        if bindings != self.replay_bindings():
            raise ProjectionHistoryError("projection_history_integrity_error")

    def validate_checkpoint_bindings(
        self,
        bindings: tuple[ProjectionHistoryReplayBinding, ...],
        *,
        graph_revision: str,
    ) -> None:
        """Validate a signed checkpoint against complete persisted authority."""

        self.validate_replay_bindings(bindings)
        self.validate_active_graph_revision(graph_revision)

    def validate_active_graph_revision(self, graph_revision: str) -> None:
        """Require every active projection authority to name the replayed graph."""

        temporal = self._load_kind("temporal")
        trust = self._load_kind("trust")
        if temporal.active is None and trust.active is None:
            return
        if temporal.active is None or trust.active is None:
            raise ProjectionHistoryError("projection_history_integrity_error")
        temporal_generation = temporal.generations.get(temporal.active.generation_digest)
        trust_generation = trust.generations.get(trust.active.generation_digest)
        if (
            not isinstance(temporal_generation, TemporalProjectionGeneration)
            or not isinstance(trust_generation, TrustProjectionGeneration)
            or temporal_generation.base_graph_revision != graph_revision
            or trust_generation.base_graph_revision != graph_revision
        ):
            raise ProjectionHistoryError("stale_materialized_projection")

    def _require_publication_authority(
        self,
        capability: object | None,
        authorization: SemanticWriterWriteAuthorization | None,
    ) -> None:
        if (
            capability is not self._publication_capability
            or not isinstance(authorization, SemanticWriterWriteAuthorization)
            or authorization.owner is not capability
        ):
            raise ProjectionHistoryError("projection_publication_unauthorized")

    def _authoritative_current_graph_revision(self) -> str:
        resolver = self._current_replay_authority_resolver
        if resolver is None:
            raise ProjectionHistoryError("projection_history_unavailable")
        try:
            graph_revision, bindings = resolver()
            if not graph_revision:
                raise ValueError("authoritative graph revision is empty")
            self.validate_replay_bindings(bindings)
            self.validate_active_graph_revision(graph_revision)
        except ProjectionHistoryError:
            raise
        except (TypeError, ValueError) as exc:
            raise ProjectionHistoryError("projection_history_integrity_error") from exc
        return graph_revision

    def _build_temporal_publication(
        self,
        request: ProjectionCommitRequest | TemporalProjectionAdvanceRequest,
        loaded: _LoadedKind,
        published_at: datetime,
    ) -> TemporalProjectionPublication:
        prior = self._last_pointer(loaded)
        sequence = len(loaded.entries) + 1
        predecessor = prior.generation_digest if prior is not None else self._genesis_generation_digest("temporal")
        prior_members = self._generation_members(loaded, prior)
        members = tuple(item.projection_digest for item in request.temporal_projections)
        added = tuple(sorted(set(members) - set(prior_members)))
        removed = tuple(sorted(set(prior_members) - set(members)))
        generation_values = {
            "generation_id": self._generation_id("temporal", sequence, request),
            "repository_id": self._repository_id,
            "temporal_policy_fingerprint": request.temporal_policy_fingerprint,
            "predecessor_generation_digest": (prior.generation_digest if prior is not None else None),
            "migration_plan_digest": self._commit_plan_digest("temporal", request),
            "base_snapshot_token": request.base_snapshot_token,
            "base_graph_revision": request.graph_revision,
            "final_catch_up_watermark": request.event_batch_digest,
            "canonical_slot_result_digests": (),
            "canonical_projection_digests": members,
            "publication_kind": "projection_commit",
            "activated_writer_epoch": request.writer_epoch,
            "activated_at": published_at,
        }
        generation_digest = projection_contract_digest("temporal_generation", generation_values)
        certificate_values = {
            "publication_kind": "projection_commit",
            "repository_id": self._repository_id,
            "operation_id": request.operation_id,
            "temporal_policy_fingerprint": request.temporal_policy_fingerprint,
            "predecessor_generation_digest": predecessor,
            "output_generation_digest": generation_digest,
            "graph_revision": request.graph_revision,
            "event_batch_sequence": request.event_batch_sequence,
            "event_batch_digest": request.event_batch_digest,
            "complete_read_set_digest": request.complete_read_set_digest,
            "semantic_conflict_authority_input_digest": request.semantic_conflict_authority.input_digest,
            "added_projection_digests": added,
            "removed_projection_digests": removed,
            "writer_epoch": request.writer_epoch,
        }
        certificate = TemporalProjectionCommitCertificate.model_validate(
            {
                **certificate_values,
                "certificate_digest": projection_contract_digest("temporal_certificate", certificate_values),
            }
        )
        generation = TemporalProjectionGeneration.model_validate(
            {
                **generation_values,
                "publication_certificate_digest": certificate.certificate_digest,
                "generation_digest": generation_digest,
            }
        )
        pointer_values = {
            "repository_id": self._repository_id,
            "policy_fingerprint": request.temporal_policy_fingerprint,
            "generation_digest": generation.generation_digest,
            "publication_kind": "projection_commit",
            "publication_certificate_digest": certificate.certificate_digest,
            "writer_epoch": request.writer_epoch,
            "pointer_revision": sequence,
            "published_at": published_at,
            "publication_sequence": sequence,
            "predecessor_pointer_digest": (prior.pointer_digest if prior is not None else None),
        }
        pointer = ActiveTemporalProjectionPointer.model_validate(
            {
                **pointer_values,
                "pointer_digest": projection_contract_digest("temporal_pointer", pointer_values),
            }
        )
        entry_values = {
            "projection_kind": "temporal",
            "repository_id": self._repository_id,
            "pointer": pointer,
        }
        entry = TemporalProjectionHistoryEntry.model_validate(
            {
                **entry_values,
                "entry_digest": projection_contract_digest("history_entry", entry_values),
            }
        )
        return TemporalProjectionPublication(
            certificate=certificate,
            generation=generation,
            history_entry=entry,
            active_pointer=pointer,
        )

    def _build_trust_publication(
        self,
        request: ProjectionCommitRequest | TrustProjectionAdvanceRequest,
        loaded: _LoadedKind,
        published_at: datetime,
    ) -> TrustProjectionPublication:
        prior = self._last_pointer(loaded)
        sequence = len(loaded.entries) + 1
        predecessor = prior.generation_digest if prior is not None else self._genesis_generation_digest("trust")
        prior_members = self._generation_members(loaded, prior)
        prior_decay_commands = self._trust_generation_decay_commands(loaded, prior)
        members = tuple(item.projection_digest for item in request.trust_projections)
        added = tuple(sorted(set(members) - set(prior_members)))
        removed = tuple(sorted(set(prior_members) - set(members)))
        added_decay_commands = tuple(sorted(set(request.trust_decay_command_digests) - set(prior_decay_commands)))
        removed_decay_commands = tuple(sorted(set(prior_decay_commands) - set(request.trust_decay_command_digests)))
        generation_values = {
            "generation_id": self._generation_id("trust", sequence, request),
            "repository_id": self._repository_id,
            "trust_policy_fingerprint": request.trust_policy_fingerprint,
            "predecessor_generation_digest": (prior.generation_digest if prior is not None else None),
            "migration_plan_digest": self._commit_plan_digest("trust", request),
            "base_snapshot_token": request.base_snapshot_token,
            "base_graph_revision": request.graph_revision,
            "final_catch_up_watermark": request.event_batch_digest,
            "canonical_slot_result_digests": (),
            "canonical_projection_digests": members,
            "canonical_decay_command_digests": request.trust_decay_command_digests,
            "publication_kind": "projection_commit",
            "arbitration_as_of": request.arbitration_as_of,
            "activated_writer_epoch": request.writer_epoch,
            "activated_at": published_at,
        }
        generation_digest = projection_contract_digest("trust_generation", generation_values)
        certificate_values = {
            "publication_kind": "projection_commit",
            "repository_id": self._repository_id,
            "operation_id": request.operation_id,
            "trust_policy_fingerprint": request.trust_policy_fingerprint,
            "predecessor_generation_digest": predecessor,
            "output_generation_digest": generation_digest,
            "graph_revision": request.graph_revision,
            "event_batch_sequence": request.event_batch_sequence,
            "event_batch_digest": request.event_batch_digest,
            "complete_read_set_digest": request.complete_read_set_digest,
            "semantic_conflict_authority_input_digest": request.semantic_conflict_authority.input_digest,
            "added_projection_digests": added,
            "removed_projection_digests": removed,
            "added_decay_command_digests": added_decay_commands,
            "removed_decay_command_digests": removed_decay_commands,
            "arbitration_as_of": request.arbitration_as_of,
            "writer_epoch": request.writer_epoch,
        }
        certificate = TrustProjectionCommitCertificate.model_validate(
            {
                **certificate_values,
                "certificate_digest": projection_contract_digest("trust_certificate", certificate_values),
            }
        )
        generation = TrustProjectionGeneration.model_validate(
            {
                **generation_values,
                "publication_certificate_digest": certificate.certificate_digest,
                "generation_digest": generation_digest,
            }
        )
        pointer_values = {
            "repository_id": self._repository_id,
            "policy_fingerprint": request.trust_policy_fingerprint,
            "generation_digest": generation.generation_digest,
            "publication_kind": "projection_commit",
            "publication_certificate_digest": certificate.certificate_digest,
            "writer_epoch": request.writer_epoch,
            "pointer_revision": sequence,
            "published_at": published_at,
            "publication_sequence": sequence,
            "predecessor_pointer_digest": (prior.pointer_digest if prior is not None else None),
        }
        pointer = ActiveTrustProjectionPointer.model_validate(
            {
                **pointer_values,
                "pointer_digest": projection_contract_digest("trust_pointer", pointer_values),
            }
        )
        entry_values = {
            "projection_kind": "trust",
            "repository_id": self._repository_id,
            "pointer": pointer,
        }
        entry = TrustProjectionHistoryEntry.model_validate(
            {
                **entry_values,
                "entry_digest": projection_contract_digest("history_entry", entry_values),
            }
        )
        return TrustProjectionPublication(
            certificate=certificate,
            generation=generation,
            history_entry=entry,
            active_pointer=pointer,
        )

    def _build_temporal_migration_publication(
        self,
        request: TemporalPolicyMigrationAdvanceRequest,
        loaded: _LoadedKind,
        published_at: datetime,
    ) -> TemporalProjectionPublication:
        prior = self._last_pointer(loaded)
        if (
            not isinstance(prior, ActiveTemporalProjectionPointer)
            or prior.policy_fingerprint != request.active_policy_fingerprint_before
            or prior.writer_epoch != request.writer_epoch_before
        ):
            raise ProjectionHistoryError("projection_publication_diverged")
        sequence = len(loaded.entries) + 1
        members = tuple(item.projection_digest for item in request.temporal_projections)
        generation_values = {
            "generation_id": self._migration_generation_id(
                "temporal", sequence, request.migration_plan_digest
            ),
            "repository_id": self._repository_id,
            "temporal_policy_fingerprint": request.pending_policy_fingerprint,
            "predecessor_generation_digest": prior.generation_digest,
            "migration_plan_digest": request.migration_plan_digest,
            "base_snapshot_token": request.base_snapshot_token,
            "base_graph_revision": request.base_graph_revision,
            "final_catch_up_watermark": request.final_catch_up_watermark,
            "canonical_slot_result_digests": request.canonical_slot_result_digests,
            "canonical_projection_digests": members,
            "publication_kind": "migration_cutover",
            "activated_writer_epoch": request.activated_writer_epoch,
            "activated_at": published_at,
        }
        generation_digest = projection_contract_digest(
            "temporal_generation", generation_values
        )
        certificate_values = {
            "migration_kind": "temporal",
            "publication_kind": "migration_cutover",
            "repository_id": self._repository_id,
            "migration_plan_digest": request.migration_plan_digest,
            "active_policy_fingerprint_before": request.active_policy_fingerprint_before,
            "pending_policy_fingerprint": request.pending_policy_fingerprint,
            "active_generation_digest_before": prior.generation_digest,
            "output_generation_digest": generation_digest,
            "server_derived_base_slot_plan_digests": request.server_derived_base_slot_plan_digests,
            "server_derived_catch_up_entry_digests": request.server_derived_catch_up_entry_digests,
            "final_catch_up_watermark": request.final_catch_up_watermark,
            "complete_read_set_digest": request.complete_read_set_digest,
            "semantic_conflict_authority_input_digest": request.semantic_conflict_authority.input_digest,
            "cutover_digest": request.cutover_digest,
            "writer_epoch_before": request.writer_epoch_before,
            "activated_writer_epoch": request.activated_writer_epoch,
        }
        certificate = TemporalPolicyMigrationCertificate.model_validate(
            {
                **certificate_values,
                "certificate_digest": projection_contract_digest(
                    "temporal_certificate", certificate_values
                ),
            }
        )
        generation = TemporalProjectionGeneration.model_validate(
            {
                **generation_values,
                "publication_certificate_digest": certificate.certificate_digest,
                "generation_digest": generation_digest,
            }
        )
        pointer_values = {
            "repository_id": self._repository_id,
            "policy_fingerprint": request.pending_policy_fingerprint,
            "generation_digest": generation.generation_digest,
            "publication_kind": "migration_cutover",
            "publication_certificate_digest": certificate.certificate_digest,
            "writer_epoch": request.activated_writer_epoch,
            "pointer_revision": sequence,
            "published_at": published_at,
            "publication_sequence": sequence,
            "predecessor_pointer_digest": prior.pointer_digest,
        }
        pointer = ActiveTemporalProjectionPointer.model_validate(
            {
                **pointer_values,
                "pointer_digest": projection_contract_digest(
                    "temporal_pointer", pointer_values
                ),
            }
        )
        entry_values = {
            "projection_kind": "temporal",
            "repository_id": self._repository_id,
            "pointer": pointer,
        }
        entry = TemporalProjectionHistoryEntry.model_validate(
            {
                **entry_values,
                "entry_digest": projection_contract_digest(
                    "history_entry", entry_values
                ),
            }
        )
        return TemporalProjectionPublication(
            certificate=certificate,
            generation=generation,
            history_entry=entry,
            active_pointer=pointer,
        )

    def _build_trust_migration_publication(
        self,
        request: TrustPolicyMigrationAdvanceRequest,
        loaded: _LoadedKind,
        published_at: datetime,
    ) -> TrustProjectionPublication:
        prior = self._last_pointer(loaded)
        if (
            not isinstance(prior, ActiveTrustProjectionPointer)
            or prior.policy_fingerprint != request.active_policy_fingerprint_before
            or prior.writer_epoch != request.writer_epoch_before
        ):
            raise ProjectionHistoryError("projection_publication_diverged")
        sequence = len(loaded.entries) + 1
        members = tuple(item.projection_digest for item in request.trust_projections)
        generation_values = {
            "generation_id": self._migration_generation_id(
                "trust", sequence, request.migration_plan_digest
            ),
            "repository_id": self._repository_id,
            "trust_policy_fingerprint": request.pending_policy_fingerprint,
            "predecessor_generation_digest": prior.generation_digest,
            "migration_plan_digest": request.migration_plan_digest,
            "base_snapshot_token": request.base_snapshot_token,
            "base_graph_revision": request.base_graph_revision,
            "final_catch_up_watermark": request.final_catch_up_watermark,
            "canonical_slot_result_digests": request.canonical_slot_result_digests,
            "canonical_projection_digests": members,
            "canonical_decay_command_digests": request.trust_decay_command_digests,
            "publication_kind": "migration_cutover",
            "arbitration_as_of": request.arbitration_as_of,
            "activated_writer_epoch": request.activated_writer_epoch,
            "activated_at": published_at,
        }
        generation_digest = projection_contract_digest(
            "trust_generation", generation_values
        )
        certificate_values = {
            "migration_kind": "trust",
            "publication_kind": "migration_cutover",
            "repository_id": self._repository_id,
            "migration_plan_digest": request.migration_plan_digest,
            "active_policy_fingerprint_before": request.active_policy_fingerprint_before,
            "pending_policy_fingerprint": request.pending_policy_fingerprint,
            "active_generation_digest_before": prior.generation_digest,
            "output_generation_digest": generation_digest,
            "server_derived_base_slot_plan_digests": request.server_derived_base_slot_plan_digests,
            "server_derived_catch_up_entry_digests": request.server_derived_catch_up_entry_digests,
            "final_catch_up_watermark": request.final_catch_up_watermark,
            "complete_read_set_digest": request.complete_read_set_digest,
            "semantic_conflict_authority_input_digest": request.semantic_conflict_authority.input_digest,
            "cutover_digest": request.cutover_digest,
            "writer_epoch_before": request.writer_epoch_before,
            "activated_writer_epoch": request.activated_writer_epoch,
        }
        certificate = TrustPolicyMigrationCertificate.model_validate(
            {
                **certificate_values,
                "certificate_digest": projection_contract_digest(
                    "trust_certificate", certificate_values
                ),
            }
        )
        generation = TrustProjectionGeneration.model_validate(
            {
                **generation_values,
                "publication_certificate_digest": certificate.certificate_digest,
                "generation_digest": generation_digest,
            }
        )
        pointer_values = {
            "repository_id": self._repository_id,
            "policy_fingerprint": request.pending_policy_fingerprint,
            "generation_digest": generation.generation_digest,
            "publication_kind": "migration_cutover",
            "publication_certificate_digest": certificate.certificate_digest,
            "writer_epoch": request.activated_writer_epoch,
            "pointer_revision": sequence,
            "published_at": published_at,
            "publication_sequence": sequence,
            "predecessor_pointer_digest": prior.pointer_digest,
        }
        pointer = ActiveTrustProjectionPointer.model_validate(
            {
                **pointer_values,
                "pointer_digest": projection_contract_digest(
                    "trust_pointer", pointer_values
                ),
            }
        )
        entry_values = {
            "projection_kind": "trust",
            "repository_id": self._repository_id,
            "pointer": pointer,
        }
        entry = TrustProjectionHistoryEntry.model_validate(
            {
                **entry_values,
                "entry_digest": projection_contract_digest(
                    "history_entry", entry_values
                ),
            }
        )
        return TrustProjectionPublication(
            certificate=certificate,
            generation=generation,
            history_entry=entry,
            active_pointer=pointer,
        )

    def _load_kind(self, kind: ProjectionKind) -> _LoadedKind:
        try:
            self._validate_namespace_inventory(kind)
            entries = self._decode_all(
                kind,
                "history_entry",
                TemporalProjectionHistoryEntry if kind == "temporal" else TrustProjectionHistoryEntry,
            )
            generations = self._decode_all(
                kind,
                "generation",
                TemporalProjectionGeneration if kind == "temporal" else TrustProjectionGeneration,
            )
            certificates = self._decode_certificates(kind)
            temporal_projections: tuple[TemporalProjectionRecord, ...] = ()
            trust_projections: tuple[TrustProjectionRecord, ...] = ()
            if kind == "temporal":
                temporal_projections = self._decode_all(
                    kind,
                    "projection",
                    TemporalProjectionRecord,
                )
            else:
                trust_projections = self._decode_all(
                    kind,
                    "projection",
                    TrustProjectionRecord,
                )
            active_records = self._records(kind, "active_pointer")
            if len(active_records) > 1:
                raise ValueError
            active = (
                self._decode(
                    active_records[0],
                    ActiveTemporalProjectionPointer if kind == "temporal" else ActiveTrustProjectionPointer,
                )
                if active_records
                else None
            )
            loaded = _LoadedKind(
                kind=kind,
                entries=tuple(
                    sorted(
                        entries,
                        key=lambda item: item.pointer.publication_sequence,
                    )
                ),
                generations=self._unique_by(generations, lambda item: item.generation_digest),
                certificates=self._unique_by(certificates, lambda item: item.certificate_digest),
                temporal_projections=(
                    self._unique_by(
                        temporal_projections,
                        lambda item: item.projection_digest,
                    )
                    if kind == "temporal"
                    else {}
                ),
                trust_projections=(
                    self._unique_by(
                        trust_projections,
                        lambda item: item.projection_digest,
                    )
                    if kind == "trust"
                    else {}
                ),
                active=active,
                active_record=active_records[0] if active_records else None,
            )
            self._validate_loaded(loaded)
            return loaded
        except (CanonicalTypedValueError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ProjectionHistoryError):
                raise
            raise ProjectionHistoryError("projection_history_integrity_error") from exc

    def _validate_loaded(self, loaded: _LoadedKind) -> None:
        if not loaded.entries:
            if (
                loaded.generations
                or loaded.certificates
                or loaded.temporal_projections
                or loaded.trust_projections
                or loaded.active is not None
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            return
        if loaded.active is None or loaded.active != loaded.entries[-1].pointer:
            raise ProjectionHistoryError("projection_history_integrity_error")
        referenced_generations: set[str] = set()
        referenced_certificates: set[str] = set()
        referenced_projections: set[str] = set()
        operations: set[str] = set()
        prior_pointer: ActiveTemporalProjectionPointer | ActiveTrustProjectionPointer | None = None
        prior_generation: TemporalProjectionGeneration | TrustProjectionGeneration | None = None
        prior_members: tuple[str, ...] = ()
        prior_decay_commands: tuple[str, ...] = ()
        for sequence, entry in enumerate(loaded.entries, start=1):
            pointer = entry.pointer
            if (
                entry.repository_id != self._repository_id
                or pointer.repository_id != self._repository_id
                or pointer.publication_sequence != sequence
                or pointer.pointer_revision != sequence
                or pointer.predecessor_pointer_digest
                != (prior_pointer.pointer_digest if prior_pointer is not None else None)
                or (prior_pointer is not None and pointer.published_at < prior_pointer.published_at)
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            generation = loaded.generations.get(pointer.generation_digest)
            certificate = loaded.certificates.get(pointer.publication_certificate_digest)
            if generation is None or certificate is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            operation_coordinate = (
                certificate.operation_id
                if isinstance(
                    certificate,
                    (
                        TemporalProjectionCommitCertificate,
                        TrustProjectionCommitCertificate,
                    ),
                )
                else f"migration:{certificate.migration_kind}:{certificate.migration_plan_digest}"
            )
            if operation_coordinate in operations:
                raise ProjectionHistoryError("projection_history_integrity_error")
            operations.add(operation_coordinate)
            referenced_generations.add(pointer.generation_digest)
            referenced_certificates.add(pointer.publication_certificate_digest)
            if loaded.kind == "temporal":
                if not (
                    isinstance(pointer, ActiveTemporalProjectionPointer)
                    and isinstance(generation, TemporalProjectionGeneration)
                    and isinstance(
                        certificate,
                        (
                            TemporalProjectionCommitCertificate,
                            TemporalPolicyMigrationCertificate,
                        ),
                    )
                    and pointer.policy_fingerprint
                    == generation.temporal_policy_fingerprint
                    == (
                        certificate.temporal_policy_fingerprint
                        if isinstance(certificate, TemporalProjectionCommitCertificate)
                        else certificate.pending_policy_fingerprint
                    )
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
                members = generation.canonical_projection_digests
                projections = loaded.temporal_projections
            else:
                if not (
                    isinstance(pointer, ActiveTrustProjectionPointer)
                    and isinstance(generation, TrustProjectionGeneration)
                    and isinstance(
                        certificate,
                        (
                            TrustProjectionCommitCertificate,
                            TrustPolicyMigrationCertificate,
                        ),
                    )
                    and pointer.policy_fingerprint
                    == generation.trust_policy_fingerprint
                    == (
                        certificate.trust_policy_fingerprint
                        if isinstance(certificate, TrustProjectionCommitCertificate)
                        else certificate.pending_policy_fingerprint
                    )
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
                members = generation.canonical_projection_digests
                projections = loaded.trust_projections
            expected_predecessor = (
                prior_generation.generation_digest
                if prior_generation is not None
                else self._genesis_generation_digest(loaded.kind)
            )
            if (
                generation.repository_id != self._repository_id
                or generation.predecessor_generation_digest
                != (prior_generation.generation_digest if prior_generation is not None else None)
                or certificate.repository_id != self._repository_id
                or certificate.output_generation_digest != generation.generation_digest
                or certificate.certificate_digest != generation.publication_certificate_digest
                or certificate.certificate_digest != pointer.publication_certificate_digest
                or certificate.publication_kind != generation.publication_kind
                or certificate.publication_kind != pointer.publication_kind
                or any(member not in projections for member in members)
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            if isinstance(
                certificate,
                (TemporalProjectionCommitCertificate, TrustProjectionCommitCertificate),
            ):
                if (
                    certificate.predecessor_generation_digest != expected_predecessor
                    or certificate.writer_epoch != generation.activated_writer_epoch
                    or certificate.writer_epoch != pointer.writer_epoch
                    or certificate.graph_revision != generation.base_graph_revision
                    or certificate.event_batch_digest != generation.final_catch_up_watermark
                    or set(certificate.added_projection_digests)
                    != set(members) - set(prior_members)
                    or set(certificate.removed_projection_digests)
                    != set(prior_members) - set(members)
                    or (
                        prior_pointer is not None
                        and pointer.policy_fingerprint != prior_pointer.policy_fingerprint
                    )
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
            elif (
                prior_pointer is None
                or certificate.active_generation_digest_before != expected_predecessor
                or certificate.active_policy_fingerprint_before
                != prior_pointer.policy_fingerprint
                or certificate.pending_policy_fingerprint
                == certificate.active_policy_fingerprint_before
                or certificate.migration_plan_digest != generation.migration_plan_digest
                or certificate.final_catch_up_watermark
                != generation.final_catch_up_watermark
                or certificate.activated_writer_epoch
                != generation.activated_writer_epoch
                or certificate.activated_writer_epoch != pointer.writer_epoch
                or certificate.writer_epoch_before != prior_pointer.writer_epoch
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            if loaded.kind == "trust" and (
                not isinstance(generation, TrustProjectionGeneration)
                or (
                    isinstance(certificate, TrustProjectionCommitCertificate)
                    and (
                        generation.arbitration_as_of != certificate.arbitration_as_of
                        or set(certificate.added_decay_command_digests)
                        != set(generation.canonical_decay_command_digests)
                        - set(prior_decay_commands)
                        or set(certificate.removed_decay_command_digests)
                        != set(prior_decay_commands)
                        - set(generation.canonical_decay_command_digests)
                    )
                )
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            for member in members:
                projection = projections[member]
                if projection.repository_id != self._repository_id:
                    raise ProjectionHistoryError("projection_history_integrity_error")
                if loaded.kind == "temporal" and (
                    not isinstance(projection, TemporalProjectionRecord)
                    or projection.temporal_policy_fingerprint != pointer.policy_fingerprint
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
                if loaded.kind == "trust" and (
                    not isinstance(projection, TrustProjectionRecord)
                    or projection.trust_policy_fingerprint != pointer.policy_fingerprint
                ):
                    raise ProjectionHistoryError("projection_history_integrity_error")
            referenced_projections.update(members)
            prior_pointer = pointer
            prior_generation = generation
            prior_members = members
            prior_decay_commands = (
                generation.canonical_decay_command_digests if isinstance(generation, TrustProjectionGeneration) else ()
            )
        if (
            referenced_generations != set(loaded.generations)
            or referenced_certificates != set(loaded.certificates)
            or referenced_projections
            != set(loaded.temporal_projections if loaded.kind == "temporal" else loaded.trust_projections)
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")

    def _decode_certificates(
        self,
        kind: ProjectionKind,
    ) -> tuple[
        TemporalProjectionCommitCertificate
        | TrustProjectionCommitCertificate
        | TemporalPolicyMigrationCertificate
        | TrustPolicyMigrationCertificate,
        ...,
    ]:
        values: list[
            TemporalProjectionCommitCertificate
            | TrustProjectionCommitCertificate
            | TemporalPolicyMigrationCertificate
            | TrustPolicyMigrationCertificate
        ] = []
        for record in self._records(kind, "certificate"):
            canonical_hex = record.content.get("canonical_hex")
            if not isinstance(canonical_hex, str):
                raise ProjectionHistoryError("projection_history_integrity_error")
            raw = decode_typed_value(bytes.fromhex(canonical_hex))
            if not isinstance(raw, dict):
                raise ProjectionHistoryError("projection_history_integrity_error")
            publication_kind = raw.get("publication_kind")
            if kind == "temporal":
                model = (
                    TemporalProjectionCommitCertificate
                    if publication_kind == "projection_commit"
                    else TemporalPolicyMigrationCertificate
                    if publication_kind == "migration_cutover"
                    else None
                )
            else:
                model = (
                    TrustProjectionCommitCertificate
                    if publication_kind == "projection_commit"
                    else TrustPolicyMigrationCertificate
                    if publication_kind == "migration_cutover"
                    else None
                )
            if model is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            values.append(self._decode(record, model))
        return tuple(values)

    def _existing_publication(
        self,
        request: ProjectionCommitRequest,
        *,
        temporal: _LoadedKind,
        trust: _LoadedKind,
        temporal_certificate: TemporalProjectionCommitCertificate | TrustProjectionCommitCertificate,
        trust_certificate: TemporalProjectionCommitCertificate | TrustProjectionCommitCertificate,
    ) -> ProjectionPublication:
        if not isinstance(temporal_certificate, TemporalProjectionCommitCertificate) or not isinstance(
            trust_certificate, TrustProjectionCommitCertificate
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        temporal_entry = next(
            (
                entry
                for entry in temporal.entries
                if entry.pointer.publication_certificate_digest == temporal_certificate.certificate_digest
            ),
            None,
        )
        trust_entry = next(
            (
                entry
                for entry in trust.entries
                if entry.pointer.publication_certificate_digest == trust_certificate.certificate_digest
            ),
            None,
        )
        if not isinstance(temporal_entry, TemporalProjectionHistoryEntry) or not isinstance(
            trust_entry, TrustProjectionHistoryEntry
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        temporal_generation = temporal.generations.get(temporal_certificate.output_generation_digest)
        trust_generation = trust.generations.get(trust_certificate.output_generation_digest)
        if not isinstance(temporal_generation, TemporalProjectionGeneration) or not isinstance(
            trust_generation, TrustProjectionGeneration
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        expected_temporal = self._expected_temporal_request(request, temporal_certificate, temporal_generation)
        expected_trust = self._expected_trust_request(request, trust_certificate, trust_generation)
        if not expected_temporal or not expected_trust:
            raise ProjectionHistoryError("projection_publication_diverged")
        return ProjectionPublication(
            temporal=TemporalProjectionPublication(
                certificate=temporal_certificate,
                generation=temporal_generation,
                history_entry=temporal_entry,
                active_pointer=temporal_entry.pointer,
            ),
            trust=TrustProjectionPublication(
                certificate=trust_certificate,
                generation=trust_generation,
                history_entry=trust_entry,
                active_pointer=trust_entry.pointer,
            ),
            replay_bindings=(
                self._binding("temporal", temporal.entries),
                self._binding("trust", trust.entries),
            ),
        )

    def _expected_temporal_request(
        self,
        request: ProjectionCommitRequest,
        certificate: TemporalProjectionCommitCertificate,
        generation: TemporalProjectionGeneration,
    ) -> bool:
        return (
            certificate.repository_id == request.repository_id
            and certificate.operation_id == request.operation_id
            and certificate.temporal_policy_fingerprint == request.temporal_policy_fingerprint
            and certificate.graph_revision == request.graph_revision
            and certificate.event_batch_sequence == request.event_batch_sequence
            and certificate.event_batch_digest == request.event_batch_digest
            and certificate.complete_read_set_digest == request.complete_read_set_digest
            and certificate.semantic_conflict_authority_input_digest
            == request.semantic_conflict_authority.input_digest
            and certificate.writer_epoch == request.writer_epoch
            and generation.base_snapshot_token == request.base_snapshot_token
            and generation.canonical_projection_digests
            == tuple(item.projection_digest for item in request.temporal_projections)
        )

    def _expected_trust_request(
        self,
        request: ProjectionCommitRequest,
        certificate: TrustProjectionCommitCertificate,
        generation: TrustProjectionGeneration,
    ) -> bool:
        return (
            certificate.repository_id == request.repository_id
            and certificate.operation_id == request.operation_id
            and certificate.trust_policy_fingerprint == request.trust_policy_fingerprint
            and certificate.graph_revision == request.graph_revision
            and certificate.event_batch_sequence == request.event_batch_sequence
            and certificate.event_batch_digest == request.event_batch_digest
            and certificate.complete_read_set_digest == request.complete_read_set_digest
            and certificate.semantic_conflict_authority_input_digest
            == request.semantic_conflict_authority.input_digest
            and certificate.writer_epoch == request.writer_epoch
            and certificate.arbitration_as_of == request.arbitration_as_of
            and generation.base_snapshot_token == request.base_snapshot_token
            and generation.canonical_projection_digests
            == tuple(item.projection_digest for item in request.trust_projections)
            and generation.canonical_decay_command_digests == request.trust_decay_command_digests
        )

    def _expected_trust_advance(
        self,
        request: TrustProjectionAdvanceRequest,
        certificate: TrustProjectionCommitCertificate,
        generation: TrustProjectionGeneration,
    ) -> bool:
        return (
            certificate.repository_id == request.repository_id
            and certificate.operation_id == request.operation_id
            and certificate.trust_policy_fingerprint
            == request.trust_policy_fingerprint
            and certificate.graph_revision == request.graph_revision
            and certificate.event_batch_sequence == request.event_batch_sequence
            and certificate.event_batch_digest == request.event_batch_digest
            and certificate.complete_read_set_digest
            == request.complete_read_set_digest
            and certificate.semantic_conflict_authority_input_digest
            == request.semantic_conflict_authority.input_digest
            and certificate.writer_epoch == request.writer_epoch
            and certificate.arbitration_as_of == request.arbitration_as_of
            and generation.base_snapshot_token == request.base_snapshot_token
            and generation.canonical_projection_digests
            == tuple(item.projection_digest for item in request.trust_projections)
            and generation.canonical_decay_command_digests
            == request.trust_decay_command_digests
        )

    def _expected_temporal_advance(
        self,
        request: TemporalProjectionAdvanceRequest,
        certificate: TemporalProjectionCommitCertificate,
        generation: TemporalProjectionGeneration,
    ) -> bool:
        return (
            certificate.repository_id == request.repository_id
            and certificate.operation_id == request.operation_id
            and certificate.temporal_policy_fingerprint
            == request.temporal_policy_fingerprint
            and certificate.graph_revision == request.graph_revision
            and certificate.event_batch_sequence == request.event_batch_sequence
            and certificate.event_batch_digest == request.event_batch_digest
            and certificate.complete_read_set_digest
            == request.complete_read_set_digest
            and certificate.semantic_conflict_authority_input_digest
            == request.semantic_conflict_authority.input_digest
            and certificate.writer_epoch == request.writer_epoch
            and generation.base_snapshot_token == request.base_snapshot_token
            and generation.canonical_projection_digests
            == tuple(item.projection_digest for item in request.temporal_projections)
        )

    def _expected_temporal_migration(
        self,
        request: TemporalPolicyMigrationAdvanceRequest,
        certificate: TemporalPolicyMigrationCertificate,
        generation: TemporalProjectionGeneration,
    ) -> bool:
        return (
            certificate.repository_id == request.repository_id
            and certificate.migration_plan_digest == request.migration_plan_digest
            and certificate.active_policy_fingerprint_before
            == request.active_policy_fingerprint_before
            and certificate.pending_policy_fingerprint
            == request.pending_policy_fingerprint
            and certificate.server_derived_base_slot_plan_digests
            == request.server_derived_base_slot_plan_digests
            and certificate.server_derived_catch_up_entry_digests
            == request.server_derived_catch_up_entry_digests
            and certificate.final_catch_up_watermark
            == request.final_catch_up_watermark
            and certificate.complete_read_set_digest
            == request.complete_read_set_digest
            and certificate.semantic_conflict_authority_input_digest
            == request.semantic_conflict_authority.input_digest
            and certificate.cutover_digest == request.cutover_digest
            and certificate.writer_epoch_before == request.writer_epoch_before
            and certificate.activated_writer_epoch
            == request.activated_writer_epoch
            and generation.base_snapshot_token == request.base_snapshot_token
            and generation.base_graph_revision == request.base_graph_revision
            and generation.canonical_slot_result_digests
            == request.canonical_slot_result_digests
            and generation.canonical_projection_digests
            == tuple(item.projection_digest for item in request.temporal_projections)
        )

    def _expected_trust_migration(
        self,
        request: TrustPolicyMigrationAdvanceRequest,
        certificate: TrustPolicyMigrationCertificate,
        generation: TrustProjectionGeneration,
    ) -> bool:
        return (
            certificate.repository_id == request.repository_id
            and certificate.migration_plan_digest == request.migration_plan_digest
            and certificate.active_policy_fingerprint_before
            == request.active_policy_fingerprint_before
            and certificate.pending_policy_fingerprint
            == request.pending_policy_fingerprint
            and certificate.server_derived_base_slot_plan_digests
            == request.server_derived_base_slot_plan_digests
            and certificate.server_derived_catch_up_entry_digests
            == request.server_derived_catch_up_entry_digests
            and certificate.final_catch_up_watermark
            == request.final_catch_up_watermark
            and certificate.complete_read_set_digest
            == request.complete_read_set_digest
            and certificate.semantic_conflict_authority_input_digest
            == request.semantic_conflict_authority.input_digest
            and certificate.cutover_digest == request.cutover_digest
            and certificate.writer_epoch_before == request.writer_epoch_before
            and certificate.activated_writer_epoch
            == request.activated_writer_epoch
            and generation.base_snapshot_token == request.base_snapshot_token
            and generation.base_graph_revision == request.base_graph_revision
            and generation.arbitration_as_of == request.arbitration_as_of
            and generation.canonical_slot_result_digests
            == request.canonical_slot_result_digests
            and generation.canonical_projection_digests
            == tuple(item.projection_digest for item in request.trust_projections)
            and generation.canonical_decay_command_digests
            == request.trust_decay_command_digests
        )

    def _historical_pointer(
        self, loaded: _LoadedKind, system_as_of: datetime
    ) -> ActiveTemporalProjectionPointer | ActiveTrustProjectionPointer:
        at = _utc(system_as_of)
        candidates = tuple(entry.pointer for entry in loaded.entries if entry.pointer.published_at <= at)
        if not candidates:
            raise ProjectionHistoryError("projection_history_unavailable")
        return max(
            candidates,
            key=lambda pointer: (
                pointer.published_at,
                pointer.publication_sequence,
            ),
        )

    def _temporal_view(self, loaded: _LoadedKind, pointer: ActiveTemporalProjectionPointer) -> TemporalProjectionView:
        generation = loaded.generations.get(pointer.generation_digest)
        if not isinstance(generation, TemporalProjectionGeneration):
            raise ProjectionHistoryError("projection_history_integrity_error")
        projections = tuple(loaded.temporal_projections[digest] for digest in generation.canonical_projection_digests)
        return TemporalProjectionView(pointer=pointer, generation=generation, projections=projections)

    def _trust_view(self, loaded: _LoadedKind, pointer: ActiveTrustProjectionPointer) -> TrustProjectionView:
        generation = loaded.generations.get(pointer.generation_digest)
        if not isinstance(generation, TrustProjectionGeneration):
            raise ProjectionHistoryError("projection_history_integrity_error")
        projections = tuple(loaded.trust_projections[digest] for digest in generation.canonical_projection_digests)
        return TrustProjectionView(pointer=pointer, generation=generation, projections=projections)

    def _binding(
        self,
        kind: ProjectionKind,
        entries: tuple[TemporalProjectionHistoryEntry | TrustProjectionHistoryEntry, ...],
    ) -> ProjectionHistoryReplayBinding:
        if not entries:
            raise ProjectionHistoryError("projection_history_integrity_error")
        pointer = entries[-1].pointer
        return ProjectionHistoryReplayBinding.create(
            projection_kind=kind,
            repository_id=self._repository_id,
            history_prefix_digest=projection_contract_digest(
                "history_prefix",
                {
                    "projection_kind": kind,
                    "repository_id": self._repository_id,
                    "entry_digests": tuple(entry.entry_digest for entry in entries),
                },
            ),
            active_pointer_digest=pointer.pointer_digest,
            generation_digest=pointer.generation_digest,
        )

    def _last_pointer(
        self, loaded: _LoadedKind
    ) -> ActiveTemporalProjectionPointer | ActiveTrustProjectionPointer | None:
        return loaded.entries[-1].pointer if loaded.entries else None

    def _generation_members(
        self,
        loaded: _LoadedKind,
        pointer: ActiveTemporalProjectionPointer | ActiveTrustProjectionPointer | None,
    ) -> tuple[str, ...]:
        if pointer is None:
            return ()
        generation = loaded.generations[pointer.generation_digest]
        return generation.canonical_projection_digests

    def _trust_generation_decay_commands(
        self,
        loaded: _LoadedKind,
        pointer: ActiveTemporalProjectionPointer | ActiveTrustProjectionPointer | None,
    ) -> tuple[str, ...]:
        if pointer is None:
            return ()
        generation = loaded.generations[pointer.generation_digest]
        if not isinstance(generation, TrustProjectionGeneration):
            raise ProjectionHistoryError("projection_history_integrity_error")
        return generation.canonical_decay_command_digests

    def _certificate_for_operation(
        self, loaded: _LoadedKind, operation_id: str
    ) -> TemporalProjectionCommitCertificate | TrustProjectionCommitCertificate | None:
        matches = tuple(
            certificate
            for certificate in loaded.certificates.values()
            if isinstance(
                certificate,
                (
                    TemporalProjectionCommitCertificate,
                    TrustProjectionCommitCertificate,
                ),
            )
            and certificate.operation_id == operation_id
        )
        if len(matches) > 1:
            raise ProjectionHistoryError("projection_history_integrity_error")
        return matches[0] if matches else None

    def _certificate_for_migration(
        self,
        loaded: _LoadedKind,
        migration_plan_digest: str,
    ) -> TemporalPolicyMigrationCertificate | TrustPolicyMigrationCertificate | None:
        matches = tuple(
            certificate
            for certificate in loaded.certificates.values()
            if isinstance(
                certificate,
                (
                    TemporalPolicyMigrationCertificate,
                    TrustPolicyMigrationCertificate,
                ),
            )
            and certificate.migration_plan_digest == migration_plan_digest
        )
        if len(matches) > 1:
            raise ProjectionHistoryError("projection_history_integrity_error")
        return matches[0] if matches else None

    def _entry_for_certificate(
        self,
        loaded: _LoadedKind,
        certificate_digest: str,
    ) -> TemporalProjectionHistoryEntry | TrustProjectionHistoryEntry | None:
        matches = tuple(
            entry
            for entry in loaded.entries
            if entry.pointer.publication_certificate_digest == certificate_digest
        )
        if len(matches) > 1:
            raise ProjectionHistoryError("projection_history_integrity_error")
        return matches[0] if matches else None

    def _genesis_generation_digest(self, kind: ProjectionKind) -> str:
        return projection_contract_digest(
            "projection_genesis",
            {"repository_id": self._repository_id, "projection_kind": kind},
        )

    def _generation_id(
        self,
        kind: ProjectionKind,
        sequence: int,
        request: ProjectionCommitRequest
        | TemporalProjectionAdvanceRequest
        | TrustProjectionAdvanceRequest,
    ) -> str:
        return projection_contract_digest(
            "projection_generation_id",
            {
                "repository_id": self._repository_id,
                "projection_kind": kind,
                "publication_sequence": sequence,
                "operation_id": request.operation_id,
                "event_batch_digest": request.event_batch_digest,
            },
        )

    def _migration_generation_id(
        self,
        kind: ProjectionKind,
        sequence: int,
        migration_plan_digest: str,
    ) -> str:
        return projection_contract_digest(
            "projection_generation_id",
            {
                "repository_id": self._repository_id,
                "projection_kind": kind,
                "publication_sequence": sequence,
                "migration_plan_digest": migration_plan_digest,
            },
        )

    def _commit_plan_digest(
        self,
        kind: ProjectionKind,
        request: ProjectionCommitRequest
        | TemporalProjectionAdvanceRequest
        | TrustProjectionAdvanceRequest,
    ) -> str:
        return projection_contract_digest(
            "projection_commit_plan",
            {
                "repository_id": self._repository_id,
                "projection_kind": kind,
                "operation_id": request.operation_id,
                "complete_read_set_digest": request.complete_read_set_digest,
                "event_batch_digest": request.event_batch_digest,
            },
        )

    def _record_prefix(self, kind: ProjectionKind) -> str:
        return f"semantic_projection:{self._repository_token}:{kind}:"

    def _records(self, kind: ProjectionKind, authority_kind: str) -> tuple[CanonicalMemoryRecord, ...]:
        prefix = self._record_prefix(kind)
        source_kind = f"semantic_projection_{kind}_{authority_kind}"
        return tuple(
            record
            for record in self._memory_plane.list_records(source_kind=source_kind)
            if record.memory_id.startswith(prefix)
        )

    def _validate_namespace_inventory(self, kind: ProjectionKind) -> None:
        prefix = self._record_prefix(kind)
        allowed = {
            "certificate",
            "generation",
            "history_entry",
            "active_pointer",
            "projection",
            "decay_command",
            "migration_command",
            "migration_plan",
            "migration_catch_up",
            "migration_result",
            "migration_cutover",
        }
        for record in self._memory_plane.list_records():
            if not record.memory_id.startswith(prefix):
                continue
            authority_kind = record.content.get("projection_authority_kind")
            if (
                authority_kind not in allowed
                or record.source_kind != f"semantic_projection_{kind}_{authority_kind}"
                or record.domain != MemoryDomain.EXECUTION
                or record.status != CommitStatus.COMMITTED
                or record.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
                or record.text
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")

    def _decode_all(self, kind: ProjectionKind, authority_kind: str, model: type[_ModelT]) -> tuple[_ModelT, ...]:
        values: list[_ModelT] = []
        for record in self._records(kind, authority_kind):
            value = self._decode(record, model)
            if authority_kind == "certificate":
                coordinate = getattr(value, "certificate_digest", None)
            elif authority_kind == "generation":
                coordinate = getattr(value, "generation_digest", None)
            elif authority_kind == "history_entry":
                pointer = getattr(value, "pointer", None)
                sequence = getattr(pointer, "publication_sequence", None)
                coordinate = f"{sequence:020d}" if isinstance(sequence, int) else None
            elif authority_kind == "active_pointer":
                coordinate = "active"
            else:
                coordinate = getattr(value, "projection_digest", None)
            if (
                not isinstance(coordinate, str)
                or record.memory_id != f"{self._record_prefix(kind)}{authority_kind}:{coordinate}"
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            values.append(value)
        return tuple(values)

    @staticmethod
    def _decode(record: CanonicalMemoryRecord, model: type[_ModelT]) -> _ModelT:
        if set(record.content) != {
            "projection_authority_kind",
            "canonical_hex",
            "authority_digest",
        }:
            raise ValueError("projection authority record shape is invalid")
        if not isinstance(record.content["projection_authority_kind"], str):
            raise TypeError("projection authority kind is invalid")
        canonical_hex = record.content["canonical_hex"]
        if not isinstance(canonical_hex, str):
            raise TypeError("projection authority encoding is invalid")
        raw = bytes.fromhex(canonical_hex)
        value = model.model_validate(decode_typed_value(raw))
        authority_digest = record.content["authority_digest"]
        if not isinstance(authority_digest, str) or sha256(raw).hexdigest() != authority_digest:
            raise ValueError("projection authority bytes are substituted")
        return value

    @staticmethod
    def _unique_by(values: tuple[_ModelT, ...], key: Callable[[_ModelT], str]) -> dict[str, _ModelT]:
        result = {key(value): value for value in values}
        if len(result) != len(values):
            raise ValueError("projection authority coordinate is duplicated")
        return result

    def _authority_record(
        self,
        value: (
            TemporalProjectionCommitCertificate
            | TrustProjectionCommitCertificate
            | TemporalPolicyMigrationCertificate
            | TrustPolicyMigrationCertificate
            | TemporalProjectionGeneration
            | TrustProjectionGeneration
            | TemporalProjectionHistoryEntry
            | TrustProjectionHistoryEntry
            | ActiveTemporalProjectionPointer
            | ActiveTrustProjectionPointer
        ),
        kind: ProjectionKind,
        authority_kind: Literal["certificate", "generation", "history_entry", "active_pointer"],
        timestamp: datetime,
    ) -> CanonicalMemoryRecord:
        raw = encode_typed_value(value.model_dump(mode="python"))
        if authority_kind == "certificate":
            if not isinstance(
                value,
                (
                    TemporalProjectionCommitCertificate,
                    TrustProjectionCommitCertificate,
                    TemporalPolicyMigrationCertificate,
                    TrustPolicyMigrationCertificate,
                ),
            ):
                raise TypeError("projection certificate record has the wrong model")
            coordinate = value.certificate_digest
        elif authority_kind == "generation":
            if not isinstance(value, (TemporalProjectionGeneration, TrustProjectionGeneration)):
                raise TypeError("projection generation record has the wrong model")
            coordinate = value.generation_digest
        elif authority_kind == "history_entry":
            if not isinstance(
                value,
                (TemporalProjectionHistoryEntry, TrustProjectionHistoryEntry),
            ):
                raise TypeError("projection history record has the wrong model")
            coordinate = f"{value.pointer.publication_sequence:020d}"
        else:
            if not isinstance(
                value,
                (
                    ActiveTemporalProjectionPointer,
                    ActiveTrustProjectionPointer,
                ),
            ):
                raise TypeError("active projection record has the wrong model")
            coordinate = "active"
        return CanonicalMemoryRecord(
            memory_id=f"{self._record_prefix(kind)}{authority_kind}:{coordinate}",
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "projection_authority_kind": authority_kind,
                "canonical_hex": raw.hex(),
                "authority_digest": sha256(raw).hexdigest(),
            },
            status=CommitStatus.COMMITTED,
            source_kind=f"semantic_projection_{kind}_{authority_kind}",
            timestamp=timestamp,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )

    def _projection_record(
        self,
        value: TemporalProjectionRecord | TrustProjectionRecord,
        timestamp: datetime,
    ) -> CanonicalMemoryRecord:
        kind: ProjectionKind = "temporal" if isinstance(value, TemporalProjectionRecord) else "trust"
        raw = encode_typed_value(value.model_dump(mode="python"))
        return CanonicalMemoryRecord(
            memory_id=f"{self._record_prefix(kind)}projection:{value.projection_digest}",
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "projection_authority_kind": "projection",
                "canonical_hex": raw.hex(),
                "authority_digest": sha256(raw).hexdigest(),
            },
            status=CommitStatus.COMMITTED,
            source_kind=f"semantic_projection_{kind}_projection",
            timestamp=timestamp,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )


def projection_records_from_replay_state(
    state: SemanticReplayState,
    *,
    active_temporal: TemporalProjectionView | None = None,
    active_trust: TrustProjectionView | None = None,
    active_temporal_policy: TemporalPolicySnapshot | None = None,
    active_trust_policy: TrustPolicySnapshot | None = None,
) -> tuple[
    tuple[TemporalProjectionRecord, ...],
    tuple[TrustProjectionRecord, ...],
    str,
    str,
    datetime,
]:
    """Derive complete policy-relative records from canonical replay state."""

    try:
        identity_lineage = replay_identity_lineage(state)
    except IdentityLineageError as exc:
        raise ProjectionHistoryError("projection_history_integrity_error") from exc
    temporal: list[TemporalProjectionRecord] = []
    trust: list[TrustProjectionRecord] = []
    temporal_fingerprints: set[str] = set()
    trust_fingerprints: set[str] = set()
    arbitration_times: set[datetime] = set()
    if (active_temporal is None) != (active_trust is None):
        raise ProjectionHistoryError("projection_history_integrity_error")
    if (active_temporal_policy is None) != (active_trust_policy is None):
        raise ProjectionHistoryError("projection_history_integrity_error")
    target_temporal_fingerprint = (
        active_temporal.pointer.policy_fingerprint
        if active_temporal is not None
        else None
    )
    target_trust_fingerprint = (
        active_trust.pointer.policy_fingerprint
        if active_trust is not None
        else None
    )
    target_arbitration_as_of = (
        active_trust.generation.arbitration_as_of
        if active_trust is not None
        else None
    )
    if active_temporal_policy is not None and (
        active_trust_policy is None
        or (
            target_temporal_fingerprint != active_temporal_policy.fingerprint
            or target_trust_fingerprint != active_trust_policy.fingerprint
        )
    ):
        raise ProjectionHistoryError("projection_history_integrity_error")
    baseline_temporal = {
        (item.source_record_kind, item.source_record_id): item
        for item in active_temporal.projections
    } if active_temporal is not None else {}
    baseline_trust = {
        (item.source_record_kind, item.source_record_id): item
        for item in active_trust.projections
    } if active_trust is not None else {}
    typed_claims: list[SemanticMaterializedMemoryRecord] = []
    resolved_claim_keys: dict[str, SemanticAssertionKey] = {}
    for materialized in state.materialized_records:
        record = materialized.record
        # Non-owning canonical graph records participate in replay/reference
        # authority but never manufacture temporal or trust projections.
        if not _is_semantic_durable_carrier(record):
            continue
        closure = record.temporal_evidence.decision_closure
        temporal_fingerprints.add(closure.temporal_policy_fingerprint)
        trust_fingerprints.add(closure.trust_policy_fingerprint)
        arbitration_times.add(closure.arbitration_as_of)
        if isinstance(record, ClaimAssertion) and record.claim_identity is not None:
            typed_claims.append(materialized)
            resolved_claim_keys[record.claim_assertion_id] = identity_lineage.resolve_claim(
                materialized
            ).resolved_assertion_key
            continue
        source_record_id = _source_record_id(record)
        if (
            active_temporal_policy is None
            and
            target_temporal_fingerprint is not None
            and target_trust_fingerprint is not None
            and (
                closure.temporal_policy_fingerprint
                != target_temporal_fingerprint
                or closure.trust_policy_fingerprint != target_trust_fingerprint
            )
        ):
            key = (materialized.record_kind, source_record_id)
            prior_temporal = baseline_temporal.get(key)
            prior_trust = baseline_trust.get(key)
            if (
                prior_temporal is None
                or prior_trust is None
                or prior_temporal.source_record_digest != materialized.record_digest
                or prior_trust.source_record_digest != materialized.record_digest
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            temporal.append(prior_temporal)
            trust.append(prior_trust)
            continue
        evidence = tuple(
            ProjectionEvidenceRecord(
                candidate_id=candidate.candidate_id,
                candidate_digest=candidate.candidate_digest,
                authority_relation=(
                    "winner"
                    if candidate.candidate_id in closure.selected_candidate_ids
                    else (
                        "contested_top"
                        if candidate.candidate_id in closure.contested_candidate_ids
                        else "retained_noncurrent"
                    )
                ),
            )
            for candidate in closure.candidates
        )
        projection_id_body = {
            "repository_id": state.repository_id,
            "source_record_kind": materialized.record_kind,
            "source_record_id": source_record_id,
            "source_record_digest": materialized.record_digest,
        }
        projection_id = projection_contract_digest("projection_record_id", projection_id_body)
        temporal.append(
            TemporalProjectionRecord.create(
                projection_id=projection_id,
                repository_id=state.repository_id,
                source_record_kind=materialized.record_kind,
                source_record_id=source_record_id,
                source_record_version=materialized.record_version,
                source_record_digest=materialized.record_digest,
                temporal_policy_fingerprint=(
                    target_temporal_fingerprint
                    or closure.temporal_policy_fingerprint
                ),
                valid_interval=record.valid_interval,
                outcome=closure.outcome,
                evidence=evidence,
            )
        )
        trust.append(
            TrustProjectionRecord.create(
                projection_id=projection_id,
                repository_id=state.repository_id,
                source_record_kind=materialized.record_kind,
                source_record_id=source_record_id,
                source_record_version=materialized.record_version,
                source_record_digest=materialized.record_digest,
                trust_policy_fingerprint=(
                    target_trust_fingerprint
                    or closure.trust_policy_fingerprint
                ),
                arbitration_as_of=(
                    target_arbitration_as_of or closure.arbitration_as_of
                ),
                outcome=closure.outcome,
                evidence=evidence,
            )
        )
    claim_groups: dict[bytes, list[SemanticMaterializedMemoryRecord]] = {}
    for materialized in typed_claims:
        record = materialized.record
        assert isinstance(record, ClaimAssertion)
        assert record.claim_identity is not None
        slot = resolved_claim_keys[record.claim_assertion_id].slot
        claim_groups.setdefault(encode_typed_value(slot.model_dump(mode="python")), []).append(materialized)
    event_order = {
        item.event_id: (item.batch_sequence, item.event_offset)
        for item in state.event_bindings
    }
    for slot_key in sorted(claim_groups):
        group = tuple(
            sorted(
                claim_groups[slot_key],
                key=lambda item: _source_record_id(item.record),
            )
        )
        first = group[0].record
        assert isinstance(first, ClaimAssertion)
        assert first.claim_identity is not None
        state_rule = first.claim_identity.predicate_state_rule
        policy_source_materialized = max(
            group,
            key=lambda item: event_order.get(item.source_event_id, (0, 0)),
        )
        policy_source = policy_source_materialized.record
        assert isinstance(policy_source, ClaimAssertion)
        policy_closure = policy_source.temporal_evidence.decision_closure
        if any(
            not isinstance(item.record, ClaimAssertion)
            or item.record.claim_identity is None
            or item.record.claim_identity.predicate_state_rule != state_rule
            for item in group
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        if active_temporal is None and any(
            not isinstance(item.record, ClaimAssertion)
            or item.record.predicate_trust_rule != first.predicate_trust_rule
            for item in group
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        if (
            active_temporal_policy is None
            and
            target_temporal_fingerprint is not None
            and target_trust_fingerprint is not None
            and (
                policy_closure.temporal_policy_fingerprint
                != target_temporal_fingerprint
                or policy_closure.trust_policy_fingerprint
                != target_trust_fingerprint
            )
        ):
            if active_temporal is None or active_trust is None:
                raise ProjectionHistoryError("projection_history_integrity_error")
            slot = resolved_claim_keys[first.claim_assertion_id].slot
            prior_temporal = tuple(
                item
                for item in active_temporal.projections
                if item.claim_slot_key == slot
            )
            prior_trust = tuple(
                item
                for item in active_trust.projections
                if item.claim_slot_key == slot
            )
            expected_evidence = {
                item.record.claim_assertion_id: item.record.record_digest
                for item in group
                if isinstance(item.record, ClaimAssertion)
            }
            temporal_evidence = {
                item.candidate_id: item.candidate_digest
                for projection in prior_temporal
                for item in projection.evidence
            }
            trust_evidence = {
                item.candidate_id: item.candidate_digest
                for projection in prior_trust
                for item in projection.evidence
            }
            if (
                not prior_temporal
                or not prior_trust
                or temporal_evidence != expected_evidence
                or trust_evidence != expected_evidence
            ):
                raise ProjectionHistoryError("projection_history_integrity_error")
            temporal.extend(prior_temporal)
            trust.extend(prior_trust)
            continue
        if state_rule.cardinality == "single":
            partitions = _valid_time_partitions(group)
        else:
            by_value: dict[bytes, list[SemanticMaterializedMemoryRecord]] = {}
            for item in group:
                record = item.record
                assert isinstance(record, ClaimAssertion)
                assert record.claim_identity is not None
                value = resolved_claim_keys[record.claim_assertion_id].value
                by_value.setdefault(encode_typed_value(value.model_dump(mode="python")), []).append(item)
            partitions = tuple(
                partition
                for value_key in sorted(by_value)
                for partition in _valid_time_partitions(
                    tuple(
                        sorted(
                            by_value[value_key],
                            key=lambda item: _source_record_id(item.record),
                        )
                    )
                )
            )
        for projected_interval, partition in partitions:
            trust_rule = (
                active_trust_policy.rule_for(
                    first.claim_identity.assertion_key_at_recording.slot.predicate_id
                )
                if active_trust_policy is not None
                else None
            )
            temporal_record, trust_record = _typed_claim_projection_records(
                state=state,
                records=partition,
                projected_interval=projected_interval,
                policy_source=policy_source,
                temporal_policy_fingerprint=target_temporal_fingerprint,
                trust_policy_fingerprint=target_trust_fingerprint,
                arbitration_as_of=target_arbitration_as_of,
                temporal_policy_override=active_temporal_policy,
                trust_policy_override=active_trust_policy,
                trust_rule_override=trust_rule,
                resolved_assertion_keys=resolved_claim_keys,
            )
            temporal.append(temporal_record)
            trust.append(trust_record)
    if not temporal:
        raise ProjectionHistoryError("projection_history_integrity_error")
    if active_temporal is None:
        if (
            len(temporal_fingerprints) != 1
            or len(trust_fingerprints) != 1
            or len(arbitration_times) != 1
        ):
            raise ProjectionHistoryError("projection_history_integrity_error")
        target_temporal_fingerprint = next(iter(temporal_fingerprints))
        target_trust_fingerprint = next(iter(trust_fingerprints))
        target_arbitration_as_of = next(iter(arbitration_times))
    if (
        target_temporal_fingerprint is None
        or target_trust_fingerprint is None
        or target_arbitration_as_of is None
    ):
        raise ProjectionHistoryError("projection_history_integrity_error")
    return (
        tuple(sorted(temporal, key=lambda item: item.projection_digest)),
        tuple(sorted(trust, key=lambda item: item.projection_digest)),
        target_temporal_fingerprint,
        target_trust_fingerprint,
        target_arbitration_as_of,
    )


def _valid_time_partitions(
    records: tuple[SemanticMaterializedMemoryRecord, ...],
) -> tuple[tuple[TimeInterval | None, tuple[SemanticMaterializedMemoryRecord, ...]], ...]:
    """Partition one value/slot into covered half-open valid-time atoms."""

    atemporal = tuple(record for record in records if _carrier_valid_interval(record) is None)
    temporal = tuple(record for record in records if _carrier_valid_interval(record) is not None)
    partitions: list[tuple[TimeInterval | None, tuple[SemanticMaterializedMemoryRecord, ...]]] = []
    if atemporal:
        partitions.append((None, atemporal))
    if not temporal:
        return tuple(partitions)
    endpoint_values: set[datetime] = set()
    for materialized in temporal:
        interval = _carrier_valid_interval(materialized)
        assert interval is not None
        endpoint_values.add(interval.start)
        if interval.end is not None:
            endpoint_values.add(interval.end)
    endpoints = tuple(sorted(endpoint_values))

    def covering(
        start: datetime,
        end: datetime | None,
    ) -> tuple[SemanticMaterializedMemoryRecord, ...]:
        covered = []
        for materialized in temporal:
            interval = _carrier_valid_interval(materialized)
            assert interval is not None
            if interval.start > start:
                continue
            if end is None:
                if interval.end is None:
                    covered.append(materialized)
            elif interval.end is None or end <= interval.end:
                covered.append(materialized)
        return tuple(covered)

    atoms: list[tuple[TimeInterval, tuple[SemanticMaterializedMemoryRecord, ...]]] = []
    for start, end in zip(endpoints, endpoints[1:], strict=False):
        covered = covering(start, end)
        if covered:
            atoms.append((TimeInterval(start=start, end=end), covered))
    tail = covering(endpoints[-1], None)
    if tail:
        atoms.append((TimeInterval(start=endpoints[-1], end=None), tail))
    for interval, covered in atoms:
        if partitions:
            previous_interval, previous_covered = partitions[-1]
            if (
                previous_interval is not None
                and previous_interval.end == interval.start
                and previous_covered == covered
            ):
                partitions[-1] = (
                    TimeInterval(start=previous_interval.start, end=interval.end),
                    covered,
                )
                continue
        partitions.append((interval, covered))
    return tuple(partitions)


def _typed_claim_projection_records(
    *,
    state: SemanticReplayState,
    records: tuple[SemanticMaterializedMemoryRecord, ...],
    projected_interval: TimeInterval | None,
    policy_source: ClaimAssertion | None = None,
    temporal_policy_fingerprint: str | None = None,
    trust_policy_fingerprint: str | None = None,
    arbitration_as_of: datetime | None = None,
    temporal_policy_override: TemporalPolicySnapshot | None = None,
    trust_policy_override: TrustPolicySnapshot | None = None,
    trust_rule_override: PredicateTrustRule | None = None,
    resolved_assertion_keys: Mapping[str, SemanticAssertionKey] | None = None,
) -> tuple[TemporalProjectionRecord, TrustProjectionRecord]:
    claims = tuple(item.record for item in records)
    if not claims or any(not isinstance(record, ClaimAssertion) for record in claims):
        raise ProjectionHistoryError("projection_history_integrity_error")
    typed_claims = tuple(record for record in claims if isinstance(record, ClaimAssertion))
    if any(
        record.claim_identity is None or record.source_authority_evidence is None or record.predicate_trust_rule is None
        for record in typed_claims
    ):
        raise ProjectionHistoryError("projection_history_integrity_error")
    first = typed_claims[0]
    assert first.claim_identity is not None
    assert first.predicate_trust_rule is not None
    resolved_assertion_keys = resolved_assertion_keys or {
        record.claim_assertion_id: record.claim_identity.assertion_key_at_recording
        for record in typed_claims
        if record.claim_identity is not None
    }
    if set(record.claim_assertion_id for record in typed_claims) - set(resolved_assertion_keys):
        raise ProjectionHistoryError("projection_history_integrity_error")
    slot = resolved_assertion_keys[first.claim_assertion_id].slot
    state_rule = first.claim_identity.predicate_state_rule
    policy_source = policy_source or first
    if (
        policy_source.claim_identity is None
        or policy_source.predicate_trust_rule is None
        or policy_source.claim_identity.predicate_state_rule != state_rule
    ):
        raise ProjectionHistoryError("projection_history_integrity_error")
    trust_rule = trust_rule_override or policy_source.predicate_trust_rule
    if any(
        record.claim_identity is None
        or resolved_assertion_keys[record.claim_assertion_id].slot != slot
        or record.claim_identity.predicate_state_rule != state_rule
        for record in typed_claims
    ):
        raise ProjectionHistoryError("projection_history_integrity_error")

    eligible = tuple(
        index
        for index, record in enumerate(typed_claims)
        if record.source_authority_evidence is not None
        and record.source_authority_evidence.authority.authority_class in trust_rule.eligible_authority_classes
    )
    incomparable = set(trust_rule.incomparable_class_pairs)

    def authority_class(index: int) -> str:
        evidence = typed_claims[index].source_authority_evidence
        assert evidence is not None
        return evidence.authority.authority_class

    def claim_identity(index: int):
        identity = typed_claims[index].claim_identity
        assert identity is not None
        return identity

    def value_key(index: int) -> bytes:
        return encode_typed_value(
            resolved_assertion_keys[typed_claims[index].claim_assertion_id].value.model_dump(mode="python")
        )

    def dominated(index: int) -> bool:
        current_class = authority_class(index)
        current_rank = trust_rule.authority_rank_by_class[current_class]
        return any(
            other != index
            and tuple(sorted((current_class, authority_class(other)))) not in incomparable
            and trust_rule.authority_rank_by_class[authority_class(other)] > current_rank
            for other in eligible
        )

    maximal = tuple(index for index in eligible if not dominated(index))
    trust_outcome: Literal["pass", "unknown", "contested"]
    selected: tuple[int, ...]
    contested: tuple[int, ...]
    if not maximal:
        trust_outcome = "unknown"
        selected = ()
        contested = ()
    else:
        maximal_values = {value_key(index) for index in maximal}
        if state_rule.cardinality == "single" and len(maximal_values) > 1:
            trust_outcome = "contested"
            selected = ()
            contested = tuple(index for index in eligible if value_key(index) in maximal_values)
        else:
            trust_outcome = "pass"
            selected = tuple(index for index in eligible if value_key(index) in maximal_values)
            contested = ()
    retained = tuple(index for index in range(len(typed_claims)) if index not in selected + contested)

    trust_relations: dict[int, Literal["winner", "contested_top", "retained_noncurrent"]] = {
        **{index: "winner" for index in selected},
        **{index: "contested_top" for index in contested},
        **{index: "retained_noncurrent" for index in retained},
    }
    temporal_outcome = trust_outcome
    temporal_selected = selected
    temporal_contested = contested
    if (temporal_policy_override is None) != (trust_policy_override is None):
        raise ProjectionHistoryError("projection_history_integrity_error")
    if temporal_policy_override is not None and trust_policy_override is not None:
        from memorii.core.semantic_ingestion.temporal_evidence_resolution import TemporalEvidenceResolver

        candidates = tuple(
            sorted(
                (
                    candidate
                    for claim in typed_claims
                    for candidate in claim.temporal_evidence.decision_closure.candidates
                ),
                key=lambda item: item.candidate_id,
            )
        )
        if len({item.candidate_id for item in candidates}) != len(candidates):
            raise ProjectionHistoryError("projection_history_integrity_error")
        references = tuple(
            claim.temporal_evidence.reference_evidence
            for claim in typed_claims
            if claim.temporal_evidence.reference_evidence is not None
        )
        reference = (
            references[0]
            if references and all(item == references[0] for item in references)
            else None
        )
        resolved = TemporalEvidenceResolver().resolve(
            predicate_id=slot.predicate_id,
            candidates=candidates,
            reference_evidence=reference,
            source_present_attachment=bool(candidates),
            trust_policy=trust_policy_override,
            temporal_policy=temporal_policy_override,
            arbitration_as_of=(
                arbitration_as_of
                or max(
                    claim.temporal_evidence.decision_closure.arbitration_as_of
                    for claim in typed_claims
                )
            ),
        )
        candidate_indexes = {
            candidate.candidate_id: index
            for index, claim in enumerate(typed_claims)
            for candidate in claim.temporal_evidence.decision_closure.candidates
        }
        resolver_selected = tuple(
            sorted(
                {
                    candidate_indexes[candidate_id]
                    for candidate_id in resolved.selected_candidate_ids
                }
            )
        )
        temporal_contested = tuple(
            sorted(
                {
                    candidate_indexes[candidate_id]
                    for candidate_id in resolved.contested_candidate_ids
                }
            )
        )
        if resolved.resolution_rule in {
            "atemporal",
            "authenticated_reference_open_start",
        }:
            if temporal_contested:
                # Promoting a partition to atemporal or reference-only
                # resolution must not erase a real contest: the claim keeps
                # its contested temporal projection instead of fabricating a
                # passing projection with no winner.
                temporal_selected = ()
                temporal_outcome = "contested"
            elif resolved.outcome == "pass" and resolver_selected:
                temporal_selected = resolver_selected
                temporal_outcome = resolved.outcome
            elif resolved.outcome == "pass":
                # A passing resolution that selected no candidate has no
                # winner to expose; the projection is unknown, not passing.
                temporal_selected = ()
                temporal_outcome = "unknown"
            else:
                temporal_selected = ()
                temporal_outcome = resolved.outcome
        else:
            temporal_selected = tuple(
                sorted(
                    {
                        candidate_indexes[candidate_id]
                        for candidate_id in resolved.selected_candidate_ids
                    }
                )
            )
            temporal_outcome = resolved.outcome
        # Partitioning owns finite valid-time topology. Re-arbitration may
        # promote an atemporal/reference-only partition, but it must not widen
        # or erase an already-derived finite atom using whole-claim evidence.
        if projected_interval is None:
            projected_interval = resolved.resolved_interval
    temporal_retained = tuple(
        index for index in range(len(typed_claims)) if index not in temporal_selected + temporal_contested
    )
    temporal_relations: dict[int, Literal["winner", "contested_top", "retained_noncurrent"]] = {
        **{index: "winner" for index in temporal_selected},
        **{index: "contested_top" for index in temporal_contested},
        **{index: "retained_noncurrent" for index in temporal_retained},
    }

    def evidence(
        relations: dict[int, Literal["winner", "contested_top", "retained_noncurrent"]],
    ) -> tuple[ProjectionEvidenceRecord, ...]:
        values = []
        for index, (materialized, record) in enumerate(zip(records, typed_claims, strict=True)):
            assert record.claim_identity is not None
            assert record.source_authority_evidence is not None
            values.append(
                ProjectionEvidenceRecord(
                    candidate_id=record.claim_assertion_id,
                    candidate_digest=record.record_digest,
                    authority_relation=relations[index],
                    assertion_key=resolved_assertion_keys[record.claim_assertion_id],
                    source_id=record.source_authority_evidence.source_id,
                    source_authority_class=(record.source_authority_evidence.authority.authority_class),
                    source_authority_evidence_digest=(record.source_authority_evidence.evidence_digest),
                    source_event_id=materialized.source_event_id,
                    source_event_digest=materialized.source_event_digest,
                    transaction_group_id=materialized.transaction_group_id,
                    valid_interval=record.valid_interval,
                    system_valid_from=materialized.system_valid_from,
                )
            )
        return tuple(sorted(values, key=lambda item: item.candidate_id))

    source_record_digest = projection_contract_digest(
        "projection_record_id",
        tuple(sorted(record.record_digest for record in typed_claims)),
    )
    source_record_id = "claim_slot:" + projection_contract_digest(
        "projection_record_id",
        {
            "slot": slot,
            "value_partition": (
                resolved_assertion_keys[first.claim_assertion_id].value if state_rule.cardinality == "multi" else None
            ),
            "valid_time_partition": projected_interval,
        },
    )
    projection_id = projection_contract_digest(
        "projection_record_id",
        {"repository_id": state.repository_id, "source_record_id": source_record_id},
    )
    system_valid_from = max(item.system_valid_from for item in records)
    closure = policy_source.temporal_evidence.decision_closure

    def ids(indexes: tuple[int, ...]) -> tuple[str, ...]:
        return tuple(sorted(typed_claims[index].claim_assertion_id for index in indexes))

    common = {
        "projection_id": projection_id,
        "repository_id": state.repository_id,
        "source_record_kind": "claim_assertion",
        "source_record_id": source_record_id,
        "source_record_version": max(record.record_version for record in typed_claims),
        "source_record_digest": source_record_digest,
        "claim_slot_key": slot,
        "predicate_state_policy_fingerprint": state_rule.policy_fingerprint,
        "system_valid_from": system_valid_from,
    }
    temporal = TemporalProjectionRecord.create(
        **common,
        temporal_policy_fingerprint=(
            temporal_policy_fingerprint or closure.temporal_policy_fingerprint
        ),
        valid_interval=projected_interval,
        outcome=temporal_outcome,
        evidence=evidence(temporal_relations),
        selected_assertion_ids=ids(temporal_selected),
        contested_assertion_ids=ids(temporal_contested),
        retained_assertion_ids=ids(temporal_retained),
    )
    trust = TrustProjectionRecord.create(
        **common,
        trust_policy_fingerprint=(
            trust_policy_fingerprint or closure.trust_policy_fingerprint
        ),
        arbitration_as_of=(arbitration_as_of or closure.arbitration_as_of),
        valid_interval=projected_interval,
        outcome=trust_outcome,
        evidence=evidence(trust_relations),
        selected_assertion_ids=ids(selected),
        contested_assertion_ids=ids(contested),
        retained_assertion_ids=ids(retained),
    )
    return temporal, trust


def _source_record_id(record: object) -> str:
    for attribute in (
        "claim_assertion_id",
        "action_revision_id",
        "identity_lineage_id",
        "transition_id",
    ):
        value = getattr(record, attribute, None)
        if isinstance(value, str) and value:
            return value
    raise ProjectionHistoryError("projection_history_integrity_error")


def _is_semantic_durable_carrier(value: object) -> TypeGuard[SemanticDurableCarrier]:
    return isinstance(
        value,
        (ClaimAssertion, ActionRevision, IdentityLineageRecord, TemporalTransitionRecord),
    )


def _carrier_valid_interval(
    materialized: SemanticMaterializedMemoryRecord,
) -> TimeInterval | None:
    if not _is_semantic_durable_carrier(materialized.record):
        raise ProjectionHistoryError("projection_history_integrity_error")
    return materialized.record.valid_interval


__all__ = [
    "PreparedProjectionPublication",
    "PreparedTemporalProjectionPublication",
    "PreparedTrustProjectionPublication",
    "ProjectionCommitRequest",
    "ProjectionHistoryError",
    "ProjectionHistoryRepository",
    "ProjectionPublication",
    "TemporalPolicyMigrationAdvanceRequest",
    "TemporalProjectionAdvanceRequest",
    "TemporalProjectionPublication",
    "TrustPolicyMigrationAdvanceRequest",
    "TrustProjectionAdvanceRequest",
    "TrustProjectionPublication",
    "projection_records_from_replay_state",
]
