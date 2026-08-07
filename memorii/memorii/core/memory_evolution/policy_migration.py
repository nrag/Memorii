"""Typed, deterministic temporal and trust policy migration preparation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.projection_history import (
    PreparedTemporalProjectionPublication,
    PreparedTrustProjectionPublication,
    ProjectionHistoryRepository,
    TemporalPolicyMigrationAdvanceRequest,
    TrustPolicyMigrationAdvanceRequest,
)
from memorii.core.memory_evolution.projection_scheduler import (
    ProjectionScheduler,
    ProjectionSchedulerError,
    TrustDecayCommand,
)
from memorii.core.memory_evolution.semantic_state import (
    SemanticClaimSlotKey,
    TemporalProjectionRecord,
    TemporalProjectionView,
    TrustProjectionRecord,
    TrustProjectionView,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterWriteAuthorization,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlanePrecondition,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.semantic_ingestion.contracts import (
    ClaimAssertion,
    TemporalPolicySnapshot,
    TrustPolicySnapshot,
)
from memorii.core.semantic_ingestion.event_replay import (
    SemanticEventReplayError,
    decode_semantic_replay_state,
)
from memorii.core.semantic_ingestion.pipeline import TemporalEvidenceResolver
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

MigrationKind = Literal["temporal", "trust"]
MigrationFailureReason = Literal[
    "missing_retained_evidence",
    "invalid_policy_binding",
    "stale_slot_membership",
    "operator_action_required",
]
PolicyMigrationErrorCode = Literal[
    "policy_migration_policy_mismatch",
    "policy_migration_stale_plan",
    "policy_migration_incomplete",
    "policy_migration_integrity_error",
    "policy_migration_unauthorized",
]

_PLAN_DOMAIN = b"memorii.policy-migration-plan.v1\0"
_SLOT_DOMAIN = b"memorii.policy-migration-slot-plan.v1\0"
_CATCH_UP_DOMAIN = b"memorii.policy-migration-catch-up.v1\0"
_RESULT_DOMAIN = b"memorii.policy-migration-result.v1\0"
_CUTOVER_DOMAIN = b"memorii.policy-migration-cutover.v1\0"
_TEMPORAL_COMMAND_ID_DOMAIN = b"memorii.temporal-reprojection-command-id.v1\0"
_TEMPORAL_COMMAND_DOMAIN = b"memorii.temporal-reprojection-command.v1\0"


class PolicyMigrationError(ValueError):
    def __init__(self, code: PolicyMigrationErrorCode) -> None:
        super().__init__(code)
        self.code = code


def _canonical(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def _contract_digest(domain: bytes, value: object) -> str:
    return sha256(domain + encode_typed_value(_canonical(value))).hexdigest()


def _digest(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(_digest(item) for item in value)
    if not isinstance(value, str):
        raise TypeError("policy migration digest must be a string")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("policy migration digest must be lowercase hexadecimal")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("policy migration time must be UTC")
    return value.astimezone(UTC)


class TemporalMigrationSlotPlan(BaseModel):
    migration_kind: Literal["temporal"] = "temporal"
    claim_slot_key: SemanticClaimSlotKey
    assertion_ids: tuple[str, ...]
    projection_digests: tuple[str, ...]
    slot_plan_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator("projection_digests", "slot_plan_digest")(_digest)

    @model_validator(mode="after")
    def validate_plan(self) -> TemporalMigrationSlotPlan:
        if (
            self.assertion_ids != tuple(sorted(set(self.assertion_ids)))
            or self.projection_digests != tuple(sorted(set(self.projection_digests)))
            or self.slot_plan_digest
            != _contract_digest(
                _SLOT_DOMAIN,
                self.model_dump(mode="python", exclude={"slot_plan_digest"}),
            )
        ):
            raise ValueError("temporal migration slot plan is invalid")
        return self


class TrustMigrationSlotPlan(BaseModel):
    migration_kind: Literal["trust"] = "trust"
    claim_slot_key: SemanticClaimSlotKey
    assertion_ids: tuple[str, ...]
    projection_digests: tuple[str, ...]
    decay_command_digests: tuple[str, ...]
    slot_plan_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "projection_digests", "decay_command_digests", "slot_plan_digest"
    )(_digest)

    @model_validator(mode="after")
    def validate_plan(self) -> TrustMigrationSlotPlan:
        canonical = (
            self.assertion_ids,
            self.projection_digests,
            self.decay_command_digests,
        )
        if (
            any(values != tuple(sorted(set(values))) for values in canonical)
            or self.slot_plan_digest
            != _contract_digest(
                _SLOT_DOMAIN,
                self.model_dump(mode="python", exclude={"slot_plan_digest"}),
            )
        ):
            raise ValueError("trust migration slot plan is invalid")
        return self


class TemporalPolicyMigrationPlan(BaseModel):
    migration_kind: Literal["temporal"] = "temporal"
    repository_id: str = Field(min_length=1)
    active_policy_fingerprint: str
    active_policy_snapshot_digest: str
    active_trust_policy_fingerprint: str
    active_trust_policy_snapshot_digest: str
    pending_policy_fingerprint: str
    pending_policy_snapshot_digest: str
    base_snapshot_token: str
    base_graph_revision: str = Field(min_length=1)
    base_catch_up_watermark: str = Field(min_length=1)
    policy_effective_at: datetime
    writer_epoch: int = Field(ge=1)
    migration_partition_revision: int = Field(ge=0)
    changed_predicate_ids: tuple[str, ...]
    slot_plans: tuple[TemporalMigrationSlotPlan, ...]
    plan_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "active_policy_fingerprint",
        "active_policy_snapshot_digest",
        "active_trust_policy_fingerprint",
        "active_trust_policy_snapshot_digest",
        "pending_policy_fingerprint",
        "pending_policy_snapshot_digest",
        "base_snapshot_token",
        "plan_digest",
    )(_digest)
    _validate_time = field_validator("policy_effective_at")(_utc)

    @model_validator(mode="after")
    def validate_plan(self) -> TemporalPolicyMigrationPlan:
        slot_digests = tuple(item.slot_plan_digest for item in self.slot_plans)
        if (
            self.active_policy_fingerprint == self.pending_policy_fingerprint
            or self.changed_predicate_ids
            != tuple(sorted(set(self.changed_predicate_ids)))
            or slot_digests != tuple(sorted(set(slot_digests)))
            or self.plan_digest
            != _contract_digest(
                _PLAN_DOMAIN,
                self.model_dump(mode="python", exclude={"plan_digest"}),
            )
        ):
            raise ValueError("temporal policy migration plan is invalid")
        return self


class TrustPolicyMigrationPlan(BaseModel):
    migration_kind: Literal["trust"] = "trust"
    repository_id: str = Field(min_length=1)
    active_policy_fingerprint: str
    active_policy_snapshot_digest: str
    pending_policy_fingerprint: str
    pending_policy_snapshot_digest: str
    base_snapshot_token: str
    base_graph_revision: str = Field(min_length=1)
    base_catch_up_watermark: str = Field(min_length=1)
    arbitration_as_of: datetime
    writer_epoch: int = Field(ge=1)
    migration_partition_revision: int = Field(ge=0)
    changed_predicate_ids: tuple[str, ...]
    slot_plans: tuple[TrustMigrationSlotPlan, ...]
    plan_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "active_policy_fingerprint",
        "active_policy_snapshot_digest",
        "pending_policy_fingerprint",
        "pending_policy_snapshot_digest",
        "base_snapshot_token",
        "plan_digest",
    )(_digest)
    _validate_time = field_validator("arbitration_as_of")(_utc)

    @model_validator(mode="after")
    def validate_plan(self) -> TrustPolicyMigrationPlan:
        slot_digests = tuple(item.slot_plan_digest for item in self.slot_plans)
        if (
            self.active_policy_fingerprint == self.pending_policy_fingerprint
            or self.changed_predicate_ids
            != tuple(sorted(set(self.changed_predicate_ids)))
            or slot_digests != tuple(sorted(set(slot_digests)))
            or self.plan_digest
            != _contract_digest(
                _PLAN_DOMAIN,
                self.model_dump(mode="python", exclude={"plan_digest"}),
            )
        ):
            raise ValueError("trust policy migration plan is invalid")
        return self


class TemporalMigrationCatchUpEntry(BaseModel):
    migration_kind: Literal["temporal"] = "temporal"
    migration_plan_digest: str
    active_policy_fingerprint: str
    pending_policy_fingerprint: str
    writer_epoch: int = Field(ge=1)
    slot_plan: TemporalMigrationSlotPlan
    graph_revision: str = Field(min_length=1)
    graph_delta_digest: str
    event_batch_digest: str
    ledger_position: int = Field(ge=1)
    watermark: str = Field(min_length=1)
    complete_read_set_digest: str
    membership_digest: str
    partition_revision_before: int = Field(ge=0)
    partition_revision: int = Field(ge=1)
    entry_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "active_policy_fingerprint",
        "pending_policy_fingerprint",
        "graph_delta_digest",
        "event_batch_digest",
        "complete_read_set_digest",
        "membership_digest",
        "entry_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_entry(self) -> TemporalMigrationCatchUpEntry:
        expected_membership = _catch_up_membership_digest(self.slot_plan)
        if (
            self.active_policy_fingerprint == self.pending_policy_fingerprint
            or self.event_batch_digest != self.watermark
            or self.partition_revision != self.partition_revision_before + 1
            or self.membership_digest != expected_membership
            or self.entry_digest
            != _contract_digest(
                _CATCH_UP_DOMAIN,
                self.model_dump(mode="python", exclude={"entry_digest"}),
            )
        ):
            raise ValueError("temporal migration catch-up digest mismatch")
        return self


class TrustMigrationCatchUpEntry(BaseModel):
    migration_kind: Literal["trust"] = "trust"
    migration_plan_digest: str
    active_policy_fingerprint: str
    pending_policy_fingerprint: str
    writer_epoch: int = Field(ge=1)
    slot_plan: TrustMigrationSlotPlan
    graph_revision: str = Field(min_length=1)
    graph_delta_digest: str
    event_batch_digest: str
    ledger_position: int = Field(ge=1)
    watermark: str = Field(min_length=1)
    complete_read_set_digest: str
    membership_digest: str
    partition_revision_before: int = Field(ge=0)
    partition_revision: int = Field(ge=1)
    entry_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "active_policy_fingerprint",
        "pending_policy_fingerprint",
        "graph_delta_digest",
        "event_batch_digest",
        "complete_read_set_digest",
        "membership_digest",
        "entry_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_entry(self) -> TrustMigrationCatchUpEntry:
        expected_membership = _catch_up_membership_digest(self.slot_plan)
        if (
            self.active_policy_fingerprint == self.pending_policy_fingerprint
            or self.event_batch_digest != self.watermark
            or self.partition_revision != self.partition_revision_before + 1
            or self.membership_digest != expected_membership
            or self.entry_digest
            != _contract_digest(
                _CATCH_UP_DOMAIN,
                self.model_dump(mode="python", exclude={"entry_digest"}),
            )
        ):
            raise ValueError("trust migration catch-up digest mismatch")
        return self


class TemporalReprojectionCommand(BaseModel):
    migration_kind: Literal["temporal"] = "temporal"
    migration_plan_digest: str
    migration_work_item_digest: str
    slot_plan_digest: str
    active_policy_fingerprint: str
    active_trust_policy_fingerprint: str
    active_trust_policy_snapshot_digest: str
    pending_policy_fingerprint: str
    pending_policy_snapshot_digest: str
    policy_effective_at: datetime
    writer_epoch: int = Field(ge=1)
    graph_revision: str = Field(min_length=1)
    complete_read_set_digest: str
    command_phase: Literal["base", "catch_up"]
    command_id: str
    command_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "migration_work_item_digest",
        "slot_plan_digest",
        "active_policy_fingerprint",
        "active_trust_policy_fingerprint",
        "active_trust_policy_snapshot_digest",
        "pending_policy_fingerprint",
        "pending_policy_snapshot_digest",
        "complete_read_set_digest",
        "command_id",
        "command_digest",
    )(_digest)
    _validate_time = field_validator("policy_effective_at")(_utc)

    @model_validator(mode="after")
    def validate_command(self) -> TemporalReprojectionCommand:
        body = self.model_dump(
            mode="python", exclude={"command_id", "command_digest"}
        )
        raw_command_id = _contract_digest(_TEMPORAL_COMMAND_ID_DOMAIN, body)
        command_id = (
            "0" if self.command_phase == "base" else "1"
        ) + raw_command_id[1:]
        if (
            self.active_policy_fingerprint == self.pending_policy_fingerprint
            or self.command_id != command_id
            or self.command_digest
            != _contract_digest(
                _TEMPORAL_COMMAND_DOMAIN,
                {**body, "command_id": command_id},
            )
        ):
            raise ValueError("temporal reprojection command is invalid")
        return self

    @classmethod
    def create(cls, **values: object) -> TemporalReprojectionCommand:
        command_values = {"migration_kind": "temporal", **values}
        raw_command_id = _contract_digest(
            _TEMPORAL_COMMAND_ID_DOMAIN, command_values
        )
        command_id = (
            "0" if command_values.get("command_phase") == "base" else "1"
        ) + raw_command_id[1:]
        body = {**command_values, "command_id": command_id}
        return cls.model_validate(
            {
                **body,
                "command_digest": _contract_digest(
                    _TEMPORAL_COMMAND_DOMAIN, body
                ),
            }
        )


class TemporalMigrationCommittedResult(BaseModel):
    migration_kind: Literal["temporal"] = "temporal"
    status: Literal["committed"] = "committed"
    migration_plan_digest: str
    slot_plan_digest: str
    migration_work_item_digest: str
    graph_revision: str = Field(min_length=1)
    graph_delta_digest: str
    command: TemporalReprojectionCommand
    command_digest: str
    projections: tuple[TemporalProjectionRecord, ...]
    result_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "slot_plan_digest",
        "migration_work_item_digest",
        "graph_delta_digest",
        "command_digest",
        "result_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_result(self) -> TemporalMigrationCommittedResult:
        digests = tuple(item.projection_digest for item in self.projections)
        if (
            digests != tuple(sorted(set(digests)))
            or self.command_digest != self.command.command_digest
            or self.command.migration_plan_digest != self.migration_plan_digest
            or self.command.migration_work_item_digest
            != self.migration_work_item_digest
            or self.command.slot_plan_digest != self.slot_plan_digest
            or self.command.graph_revision != self.graph_revision
            or self.result_digest
            != _contract_digest(
                _RESULT_DOMAIN,
                self.model_dump(mode="python", exclude={"result_digest"}),
            )
        ):
            raise ValueError("temporal migration result is invalid")
        return self


class TrustMigrationCommittedResult(BaseModel):
    migration_kind: Literal["trust"] = "trust"
    status: Literal["committed"] = "committed"
    migration_plan_digest: str
    slot_plan_digest: str
    migration_work_item_digest: str
    graph_revision: str = Field(min_length=1)
    graph_delta_digest: str
    projections: tuple[TrustProjectionRecord, ...]
    decay_commands: tuple[TrustDecayCommand, ...]
    decay_command_digests: tuple[str, ...]
    result_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "slot_plan_digest",
        "migration_work_item_digest",
        "graph_delta_digest",
        "decay_command_digests",
        "result_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_result(self) -> TrustMigrationCommittedResult:
        digests = tuple(item.projection_digest for item in self.projections)
        if (
            digests != tuple(sorted(set(digests)))
            or self.decay_command_digests
            != tuple(sorted(set(self.decay_command_digests)))
            or self.decay_command_digests
            != tuple(sorted(item.command_digest for item in self.decay_commands))
            or self.result_digest
            != _contract_digest(
                _RESULT_DOMAIN,
                self.model_dump(mode="python", exclude={"result_digest"}),
            )
        ):
            raise ValueError("trust migration result is invalid")
        return self


class TemporalMigrationUnavailableResult(BaseModel):
    migration_kind: Literal["temporal"] = "temporal"
    status: Literal["unavailable"] = "unavailable"
    migration_plan_digest: str
    slot_plan_digest: str
    migration_work_item_digest: str
    reason: MigrationFailureReason
    retryable: bool
    result_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "slot_plan_digest",
        "migration_work_item_digest",
        "result_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_result(self) -> TemporalMigrationUnavailableResult:
        if self.result_digest != _contract_digest(
            _RESULT_DOMAIN,
            self.model_dump(mode="python", exclude={"result_digest"}),
        ):
            raise ValueError("temporal unavailable result digest mismatch")
        return self


class TrustMigrationUnavailableResult(BaseModel):
    migration_kind: Literal["trust"] = "trust"
    status: Literal["unavailable"] = "unavailable"
    migration_plan_digest: str
    slot_plan_digest: str
    migration_work_item_digest: str
    reason: MigrationFailureReason
    retryable: bool
    result_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "slot_plan_digest",
        "migration_work_item_digest",
        "result_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_result(self) -> TrustMigrationUnavailableResult:
        if self.result_digest != _contract_digest(
            _RESULT_DOMAIN,
            self.model_dump(mode="python", exclude={"result_digest"}),
        ):
            raise ValueError("trust unavailable result digest mismatch")
        return self


TemporalMigrationResult = TemporalMigrationCommittedResult | TemporalMigrationUnavailableResult
TrustMigrationResult = TrustMigrationCommittedResult | TrustMigrationUnavailableResult


class TemporalPolicyCutover(BaseModel):
    migration_kind: Literal["temporal"] = "temporal"
    migration_plan_digest: str
    active_policy_fingerprint_before: str
    pending_policy_fingerprint: str
    expected_base_slot_plan_digests: tuple[str, ...]
    expected_catch_up_entry_digests: tuple[str, ...]
    committed_result_digests: tuple[str, ...]
    final_catch_up_watermark: str = Field(min_length=1)
    expected_partition_revision: int = Field(ge=0)
    expected_writer_epoch: int = Field(ge=1)
    activated_writer_epoch: int = Field(ge=1)
    complete_read_set_digest: str
    cutover_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "active_policy_fingerprint_before",
        "pending_policy_fingerprint",
        "expected_base_slot_plan_digests",
        "expected_catch_up_entry_digests",
        "committed_result_digests",
        "complete_read_set_digest",
        "cutover_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_cutover(self) -> TemporalPolicyCutover:
        sequences = (
            self.expected_base_slot_plan_digests,
            self.expected_catch_up_entry_digests,
            self.committed_result_digests,
        )
        if (
            any(values != tuple(sorted(set(values))) for values in sequences)
            or self.activated_writer_epoch != self.expected_writer_epoch + 1
            or self.cutover_digest
            != _contract_digest(
                _CUTOVER_DOMAIN,
                self.model_dump(mode="python", exclude={"cutover_digest"}),
            )
        ):
            raise ValueError("temporal policy cutover is invalid")
        return self


class TrustPolicyCutover(BaseModel):
    migration_kind: Literal["trust"] = "trust"
    migration_plan_digest: str
    active_policy_fingerprint_before: str
    pending_policy_fingerprint: str
    expected_base_slot_plan_digests: tuple[str, ...]
    expected_catch_up_entry_digests: tuple[str, ...]
    committed_result_digests: tuple[str, ...]
    final_catch_up_watermark: str = Field(min_length=1)
    expected_partition_revision: int = Field(ge=0)
    expected_writer_epoch: int = Field(ge=1)
    activated_writer_epoch: int = Field(ge=1)
    complete_read_set_digest: str
    cutover_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    _validate_digests = field_validator(
        "migration_plan_digest",
        "active_policy_fingerprint_before",
        "pending_policy_fingerprint",
        "expected_base_slot_plan_digests",
        "expected_catch_up_entry_digests",
        "committed_result_digests",
        "complete_read_set_digest",
        "cutover_digest",
    )(_digest)

    @model_validator(mode="after")
    def validate_cutover(self) -> TrustPolicyCutover:
        sequences = (
            self.expected_base_slot_plan_digests,
            self.expected_catch_up_entry_digests,
            self.committed_result_digests,
        )
        if (
            any(values != tuple(sorted(set(values))) for values in sequences)
            or self.activated_writer_epoch != self.expected_writer_epoch + 1
            or self.cutover_digest
            != _contract_digest(
                _CUTOVER_DOMAIN,
                self.model_dump(mode="python", exclude={"cutover_digest"}),
            )
        ):
            raise ValueError("trust policy cutover is invalid")
        return self


@dataclass(frozen=True)
class PreparedTemporalPolicyMigration:
    plan: TemporalPolicyMigrationPlan
    cutover: TemporalPolicyCutover
    publication: PreparedTemporalProjectionPublication
    authority_records: tuple[CanonicalMemoryRecord, ...]
    authority_preconditions: tuple[MemoryPlanePrecondition, ...]


@dataclass(frozen=True)
class PreparedTrustPolicyMigration:
    plan: TrustPolicyMigrationPlan
    cutover: TrustPolicyCutover
    publication: PreparedTrustProjectionPublication
    authority_records: tuple[CanonicalMemoryRecord, ...]
    authority_preconditions: tuple[MemoryPlanePrecondition, ...]


@dataclass(frozen=True)
class PreparedPolicyMigrationProgress:
    migration_kind: MigrationKind
    migration_plan_digest: str
    records: tuple[CanonicalMemoryRecord, ...]
    preconditions: tuple[MemoryPlanePrecondition, ...]
    catch_up_entry_digests: tuple[str, ...]
    result_digests: tuple[str, ...]
    progress_digest: str


@dataclass(frozen=True)
class PreparedPolicyMigrationCatchUp:
    """Catch-up authority that must share the graph/event writer CAS."""

    temporal_entries: tuple[TemporalMigrationCatchUpEntry, ...]
    trust_entries: tuple[TrustMigrationCatchUpEntry, ...]
    records: tuple[CanonicalMemoryRecord, ...]
    preconditions: tuple[MemoryPlanePrecondition, ...]


class PolicyMigrationRepository:
    """Server-derived migration planner and cutover closure verifier."""

    def __init__(
        self,
        memory_plane: MemoryPlaneService,
        history: ProjectionHistoryRepository,
        scheduler: ProjectionScheduler,
        *,
        repository_id: str,
        now_provider=lambda: datetime.now(UTC),
        publication_capability: object,
    ) -> None:
        self._memory_plane = memory_plane
        self._history = history
        self._scheduler = scheduler
        self._repository_id = repository_id
        self._repository_token = sha256(repository_id.encode()).hexdigest()
        self._now = now_provider
        self._publication_capability = publication_capability

    def plan_temporal(
        self,
        active: TemporalPolicySnapshot,
        pending: TemporalPolicySnapshot,
        active_trust: TrustPolicySnapshot,
        *,
        writer_epoch: int,
        migration_partition_revision: int = 0,
    ) -> TemporalPolicyMigrationPlan:
        if self._active_plan("trust") is not None:
            raise PolicyMigrationError("policy_migration_stale_plan")
        view = self._history.active_temporal_authority()
        if view.pointer.policy_fingerprint != active.fingerprint:
            raise PolicyMigrationError("policy_migration_policy_mismatch")
        if (
            self._history.active_trust_authority().pointer.policy_fingerprint
            != active_trust.fingerprint
        ):
            raise PolicyMigrationError("policy_migration_policy_mismatch")
        changed = _changed_predicates(active.rules, pending.rules)
        slots = tuple(
            self._temporal_slot_plan(slot, projections)
            for slot, projections in _slot_groups(view.projections, changed)
        )
        values = {
            "migration_kind": "temporal",
            "repository_id": self._repository_id,
            "active_policy_fingerprint": active.fingerprint,
            "active_policy_snapshot_digest": active.snapshot_digest,
            "active_trust_policy_fingerprint": active_trust.fingerprint,
            "active_trust_policy_snapshot_digest": active_trust.snapshot_digest,
            "pending_policy_fingerprint": pending.fingerprint,
            "pending_policy_snapshot_digest": pending.snapshot_digest,
            "base_snapshot_token": _base_snapshot_token(view),
            "base_graph_revision": view.generation.base_graph_revision,
            "base_catch_up_watermark": view.generation.final_catch_up_watermark,
            "policy_effective_at": pending.system_effective_interval.start,
            "writer_epoch": writer_epoch,
            "migration_partition_revision": migration_partition_revision,
            "changed_predicate_ids": changed,
            "slot_plans": tuple(sorted(slots, key=lambda item: item.slot_plan_digest)),
        }
        plan = TemporalPolicyMigrationPlan.model_validate(
            {**values, "plan_digest": _contract_digest(_PLAN_DOMAIN, values)}
        )
        active_plan = self._active_plan("temporal")
        if active_plan is not None and active_plan[0] != plan:
            raise PolicyMigrationError("policy_migration_stale_plan")
        return plan

    def plan_trust(
        self,
        active: TrustPolicySnapshot,
        pending: TrustPolicySnapshot,
        *,
        arbitration_as_of: datetime,
        writer_epoch: int,
        migration_partition_revision: int = 0,
    ) -> TrustPolicyMigrationPlan:
        if self._active_plan("temporal") is not None:
            raise PolicyMigrationError("policy_migration_stale_plan")
        view = self._history.active_trust_authority()
        if view.pointer.policy_fingerprint != active.fingerprint:
            raise PolicyMigrationError("policy_migration_policy_mismatch")
        changed = _changed_predicates(active.rules, pending.rules)
        slots = tuple(
            self._trust_slot_plan(view, slot, projections)
            for slot, projections in _slot_groups(view.projections, changed)
        )
        values = {
            "migration_kind": "trust",
            "repository_id": self._repository_id,
            "active_policy_fingerprint": active.fingerprint,
            "active_policy_snapshot_digest": active.snapshot_digest,
            "pending_policy_fingerprint": pending.fingerprint,
            "pending_policy_snapshot_digest": pending.snapshot_digest,
            "base_snapshot_token": _base_snapshot_token(view),
            "base_graph_revision": view.generation.base_graph_revision,
            "base_catch_up_watermark": view.generation.final_catch_up_watermark,
            "arbitration_as_of": _utc(arbitration_as_of),
            "writer_epoch": writer_epoch,
            "migration_partition_revision": migration_partition_revision,
            "changed_predicate_ids": changed,
            "slot_plans": tuple(sorted(slots, key=lambda item: item.slot_plan_digest)),
        }
        plan = TrustPolicyMigrationPlan.model_validate(
            {**values, "plan_digest": _contract_digest(_PLAN_DOMAIN, values)}
        )
        active_plan = self._active_plan("trust")
        if active_plan is not None and active_plan[0] != plan:
            raise PolicyMigrationError("policy_migration_stale_plan")
        return plan

    def temporal_result(
        self,
        plan: TemporalPolicyMigrationPlan,
        slot_plan: TemporalMigrationSlotPlan,
        pending_policy: TemporalPolicySnapshot,
        active_trust_policy: TrustPolicySnapshot,
        *,
        catch_up_entry: TemporalMigrationCatchUpEntry | None = None,
    ) -> TemporalMigrationCommittedResult:
        """Reject direct result construction; the atomic runner owns execution."""

        del plan, slot_plan, pending_policy, active_trust_policy, catch_up_entry
        raise PolicyMigrationError("policy_migration_unauthorized")

    def _execute_next_temporal(
        self,
        plan: TemporalPolicyMigrationPlan,
        pending_policy: TemporalPolicySnapshot,
        active_trust_policy: TrustPolicySnapshot,
        *,
        capability: object,
    ) -> TemporalMigrationCommittedResult | None:
        """Execute exactly the next durable temporal command in recovery order."""

        if capability is not self._publication_capability:
            raise PolicyMigrationError("policy_migration_unauthorized")
        catch_up, persisted_results = self._load_temporal_progress(plan)
        committed = tuple(
            item
            for item in persisted_results
            if isinstance(item, TemporalMigrationCommittedResult)
        )
        commands = self.temporal_commands(plan)
        command_by_work = {
            item.migration_work_item_digest: item for item in commands
        }
        if any(
            item.command != command_by_work.get(item.migration_work_item_digest)
            for item in committed
        ):
            raise PolicyMigrationError("policy_migration_integrity_error")
        completed_work = {
            item.migration_work_item_digest for item in persisted_results
        }
        command = next(
            (
                item
                for item in commands
                if item.migration_work_item_digest not in completed_work
            ),
            None,
        )
        if command is None:
            return None
        catch_up_entry = next(
            (
                item
                for item in catch_up
                if item.entry_digest == command.migration_work_item_digest
            ),
            None,
        )
        slot_plan = next(
            (
                item
                for item in plan.slot_plans
                if item.slot_plan_digest == command.migration_work_item_digest
            ),
            None,
        )
        if catch_up_entry is not None:
            slot_plan = catch_up_entry.slot_plan
        if slot_plan is None:
            raise PolicyMigrationError("policy_migration_integrity_error")
        return self._temporal_result_for_command(
            plan,
            slot_plan,
            pending_policy,
            active_trust_policy,
            command=command,
            catch_up_entry=catch_up_entry,
        )

    def _temporal_result_for_command(
        self,
        plan: TemporalPolicyMigrationPlan,
        slot_plan: TemporalMigrationSlotPlan,
        pending_policy: TemporalPolicySnapshot,
        active_trust_policy: TrustPolicySnapshot,
        *,
        command: TemporalReprojectionCommand,
        catch_up_entry: TemporalMigrationCatchUpEntry | None,
    ) -> TemporalMigrationCommittedResult:

        if (
            pending_policy.fingerprint != plan.pending_policy_fingerprint
            or pending_policy.snapshot_digest != plan.pending_policy_snapshot_digest
            or active_trust_policy.fingerprint
            != plan.active_trust_policy_fingerprint
            or active_trust_policy.snapshot_digest
            != plan.active_trust_policy_snapshot_digest
        ):
            raise PolicyMigrationError("policy_migration_policy_mismatch")
        source = self._temporal_slot_projections(slot_plan)
        projections = tuple(
            self._apply_temporal_policy(
                item,
                pending_policy,
                active_trust_policy,
            )
            for item in source
        )
        self._validate_temporal_result_membership(plan, slot_plan, projections)
        graph_revision = (
            catch_up_entry.graph_revision
            if catch_up_entry is not None
            else plan.base_graph_revision
        )
        graph_delta_digest = (
            catch_up_entry.graph_delta_digest
            if catch_up_entry is not None
            else _contract_digest(
                _RESULT_DOMAIN,
                {
                    "base_snapshot_token": plan.base_snapshot_token,
                    "base_graph_revision": plan.base_graph_revision,
                },
            )
        )
        work_item_digest = (
            catch_up_entry.entry_digest
            if catch_up_entry is not None
            else slot_plan.slot_plan_digest
        )
        expected_command = self._temporal_command(
            plan,
            slot_plan,
            graph_revision=graph_revision,
            complete_read_set_digest=(
                catch_up_entry.complete_read_set_digest
                if catch_up_entry is not None
                else plan.base_snapshot_token
            ),
            work_item_digest=work_item_digest,
            command_phase=("catch_up" if catch_up_entry is not None else "base"),
        )
        if command != expected_command:
            raise PolicyMigrationError("policy_migration_stale_plan")
        values = {
            "migration_kind": "temporal",
            "status": "committed",
            "migration_plan_digest": plan.plan_digest,
            "slot_plan_digest": slot_plan.slot_plan_digest,
            "migration_work_item_digest": work_item_digest,
            "graph_revision": graph_revision,
            "graph_delta_digest": graph_delta_digest,
            "command": command,
            "command_digest": command.command_digest,
            "projections": projections,
        }
        return TemporalMigrationCommittedResult.model_validate(
            {**values, "result_digest": _contract_digest(_RESULT_DOMAIN, values)}
        )

    def temporal_commands(
        self,
        plan: TemporalPolicyMigrationPlan,
    ) -> tuple[TemporalReprojectionCommand, ...]:
        """Return the complete durable command queue in recovery order."""

        catch_up, _ = self._load_temporal_progress(plan)
        expected = self._temporal_commands_for(plan, catch_up)
        observed = tuple(
            item
            for item in self._load_progress_values(
                "temporal",
                "migration_command",
                TemporalReprojectionCommand,
                digest_field="command_digest",
            )
            if item.migration_plan_digest == plan.plan_digest
        )
        if {item.command_digest for item in observed} != {
            item.command_digest for item in expected
        }:
            raise PolicyMigrationError("policy_migration_integrity_error")
        return tuple(sorted(observed, key=lambda item: (item.policy_effective_at, item.command_id)))

    def prepare_progress(
        self,
        plan: TemporalPolicyMigrationPlan | TrustPolicyMigrationPlan,
        *,
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...]
        | tuple[TrustMigrationCatchUpEntry, ...] = (),
        results: tuple[TemporalMigrationResult, ...]
        | tuple[TrustMigrationResult, ...] = (),
    ) -> PreparedPolicyMigrationProgress:
        """Prepare retained migration progress without activating a policy."""

        if (
            plan.repository_id != self._repository_id
            or any(item.migration_plan_digest != plan.plan_digest for item in catch_up)
            or any(item.migration_plan_digest != plan.plan_digest for item in results)
        ):
            raise PolicyMigrationError("policy_migration_stale_plan")
        if catch_up:
            persisted = (
                self._load_temporal_progress(plan)[0]
                if isinstance(plan, TemporalPolicyMigrationPlan)
                else self._load_trust_progress(plan)[0]
            )
            if tuple(catch_up) != persisted:
                raise PolicyMigrationError("policy_migration_stale_plan")
        records, preconditions = self._progress_closure(plan, catch_up, results)
        catch_up_digests = tuple(sorted(item.entry_digest for item in catch_up))
        result_digests = tuple(sorted(item.result_digest for item in results))
        progress_digest = _contract_digest(
            _PLAN_DOMAIN,
            {
                "migration_kind": plan.migration_kind,
                "migration_plan_digest": plan.plan_digest,
                "catch_up_entry_digests": catch_up_digests,
                "result_digests": result_digests,
                "writer_epoch": plan.writer_epoch,
            },
        )
        return PreparedPolicyMigrationProgress(
            migration_kind=plan.migration_kind,
            migration_plan_digest=plan.plan_digest,
            records=records,
            preconditions=preconditions,
            catch_up_entry_digests=catch_up_digests,
            result_digests=result_digests,
            progress_digest=progress_digest,
        )

    def prepare_write_catch_up(
        self,
        *,
        temporal_projections: tuple[TemporalProjectionRecord, ...],
        trust_projections: tuple[TrustProjectionRecord, ...],
        trust_decay_command_digests: tuple[str, ...],
        graph_revision: str,
        graph_delta_digest: str,
        ledger_position: int,
        watermark: str,
        complete_read_set_digest: str,
    ) -> PreparedPolicyMigrationCatchUp:
        """Derive migration catch-up from one complete post-write projection view.

        The caller must commit the returned records and preconditions in the same
        CAS as the graph delta, event batch, and projection generations.
        """

        temporal_entries: tuple[TemporalMigrationCatchUpEntry, ...] = ()
        trust_entries: tuple[TrustMigrationCatchUpEntry, ...] = ()
        records: list[CanonicalMemoryRecord] = []
        preconditions: list[MemoryPlanePrecondition] = []

        temporal_active = self._active_plan("temporal")
        if temporal_active is not None:
            temporal_plan, plan_record = temporal_active
            if not isinstance(temporal_plan, TemporalPolicyMigrationPlan):
                raise PolicyMigrationError("policy_migration_integrity_error")
            persisted, _ = self._load_temporal_progress(temporal_plan)
            temporal_entries = self._temporal_write_catch_up_entries(
                temporal_plan,
                persisted,
                temporal_projections,
                graph_revision=graph_revision,
                graph_delta_digest=graph_delta_digest,
                ledger_position=ledger_position,
                watermark=watermark,
                complete_read_set_digest=complete_read_set_digest,
            )
            if temporal_entries:
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=plan_record.memory_id,
                        expected_digest=record_digest(plan_record),
                    )
                )

        trust_active = self._active_plan("trust")
        if trust_active is not None:
            trust_plan, plan_record = trust_active
            if not isinstance(trust_plan, TrustPolicyMigrationPlan):
                raise PolicyMigrationError("policy_migration_integrity_error")
            persisted, _ = self._load_trust_progress(trust_plan)
            trust_entries = self._trust_write_catch_up_entries(
                trust_plan,
                persisted,
                trust_projections,
                trust_decay_command_digests=trust_decay_command_digests,
                graph_revision=graph_revision,
                graph_delta_digest=graph_delta_digest,
                ledger_position=ledger_position,
                watermark=watermark,
                complete_read_set_digest=complete_read_set_digest,
            )
            if trust_entries:
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=plan_record.memory_id,
                        expected_digest=record_digest(plan_record),
                    )
                )

        for kind, entries in (
            ("temporal", temporal_entries),
            ("trust", trust_entries),
        ):
            for entry in entries:
                record = self._authority_record(
                    kind, "migration_catch_up", entry, entry.entry_digest
                )
                if self._memory_plane.get_record(record.memory_id) is not None:
                    raise PolicyMigrationError("policy_migration_integrity_error")
                records.append(record)
                preconditions.append(
                    RecordAbsentPrecondition(memory_id=record.memory_id)
                )
                if kind == "temporal":
                    assert isinstance(entry, TemporalMigrationCatchUpEntry)
                    command = self._temporal_command(
                        temporal_plan,
                        entry.slot_plan,
                        graph_revision=entry.graph_revision,
                        complete_read_set_digest=entry.complete_read_set_digest,
                        work_item_digest=entry.entry_digest,
                        command_phase="catch_up",
                    )
                    command_record = self._authority_record(
                        kind,
                        "migration_command",
                        command,
                        command.command_digest,
                    )
                    if self._memory_plane.get_record(command_record.memory_id) is not None:
                        raise PolicyMigrationError("policy_migration_integrity_error")
                    records.append(command_record)
                    preconditions.append(
                        RecordAbsentPrecondition(memory_id=command_record.memory_id)
                    )

        return PreparedPolicyMigrationCatchUp(
            temporal_entries=temporal_entries,
            trust_entries=trust_entries,
            records=tuple(records),
            preconditions=tuple(preconditions),
        )

    def trust_result(
        self,
        plan: TrustPolicyMigrationPlan,
        slot_plan: TrustMigrationSlotPlan,
        pending_policy: TrustPolicySnapshot,
        *,
        complete_read_set_digest: str,
        catch_up_entry: TrustMigrationCatchUpEntry | None = None,
    ) -> TrustMigrationCommittedResult:
        """Close one trust command only over its server-derived slot plan."""

        if (
            pending_policy.fingerprint != plan.pending_policy_fingerprint
            or pending_policy.snapshot_digest != plan.pending_policy_snapshot_digest
        ):
            raise PolicyMigrationError("policy_migration_policy_mismatch")
        view = self._history.active_trust_authority()
        source = self._trust_slot_projections(slot_plan)
        source_view = view.model_copy(update={"projections": source})
        projected = self._scheduler.project_for_migration(
            source_view, pending_policy, plan.arbitration_as_of
        )
        projections = tuple(
            item
            for item in projected
            if item.claim_slot_key == slot_plan.claim_slot_key
        )
        self._validate_trust_result_membership(plan, slot_plan, projections)
        commands = self._scheduler.commands_for_migration(
            source_view,
            projections,
            pending_policy,
            arbitration_as_of=plan.arbitration_as_of,
            writer_epoch=plan.writer_epoch + 1,
            complete_read_set_digest=complete_read_set_digest,
        )
        graph_revision = (
            catch_up_entry.graph_revision
            if catch_up_entry is not None
            else plan.base_graph_revision
        )
        graph_delta_digest = (
            catch_up_entry.graph_delta_digest
            if catch_up_entry is not None
            else _contract_digest(
                _RESULT_DOMAIN,
                {
                    "base_snapshot_token": plan.base_snapshot_token,
                    "base_graph_revision": plan.base_graph_revision,
                },
            )
        )
        work_item_digest = (
            catch_up_entry.entry_digest
            if catch_up_entry is not None
            else slot_plan.slot_plan_digest
        )
        values = {
            "migration_kind": "trust",
            "status": "committed",
            "migration_plan_digest": plan.plan_digest,
            "slot_plan_digest": slot_plan.slot_plan_digest,
            "migration_work_item_digest": work_item_digest,
            "graph_revision": graph_revision,
            "graph_delta_digest": graph_delta_digest,
            "projections": projections,
            "decay_commands": commands,
            "decay_command_digests": tuple(
                sorted(item.command_digest for item in commands)
            ),
        }
        return TrustMigrationCommittedResult.model_validate(
            {**values, "result_digest": _contract_digest(_RESULT_DOMAIN, values)}
        )

    def unavailable_temporal_result(
        self,
        plan: TemporalPolicyMigrationPlan,
        slot_plan: TemporalMigrationSlotPlan,
        *,
        reason: MigrationFailureReason,
        retryable: bool,
        catch_up_entry_digest: str | None = None,
    ) -> TemporalMigrationUnavailableResult:
        values = {
            "migration_kind": "temporal",
            "status": "unavailable",
            "migration_plan_digest": plan.plan_digest,
            "slot_plan_digest": slot_plan.slot_plan_digest,
            "migration_work_item_digest": (
                catch_up_entry_digest or slot_plan.slot_plan_digest
            ),
            "reason": reason,
            "retryable": retryable,
        }
        return TemporalMigrationUnavailableResult.model_validate(
            {**values, "result_digest": _contract_digest(_RESULT_DOMAIN, values)}
        )

    def unavailable_trust_result(
        self,
        plan: TrustPolicyMigrationPlan,
        slot_plan: TrustMigrationSlotPlan,
        *,
        reason: MigrationFailureReason,
        retryable: bool,
        catch_up_entry_digest: str | None = None,
    ) -> TrustMigrationUnavailableResult:
        values = {
            "migration_kind": "trust",
            "status": "unavailable",
            "migration_plan_digest": plan.plan_digest,
            "slot_plan_digest": slot_plan.slot_plan_digest,
            "migration_work_item_digest": (
                catch_up_entry_digest or slot_plan.slot_plan_digest
            ),
            "reason": reason,
            "retryable": retryable,
        }
        return TrustMigrationUnavailableResult.model_validate(
            {**values, "result_digest": _contract_digest(_RESULT_DOMAIN, values)}
        )

    def temporal_catch_up(
        self,
        plan: TemporalPolicyMigrationPlan,
        projections: tuple[TemporalProjectionRecord, ...],
        *,
        graph_revision: str,
        graph_delta_digest: str,
        ledger_position: int,
        watermark: str,
        complete_read_set_digest: str,
        partition_revision: int,
    ) -> TemporalMigrationCatchUpEntry:
        slot = _one_slot(projections, plan.changed_predicate_ids)
        slot_plan = self._temporal_slot_plan(slot, projections)
        values = {
            "migration_kind": "temporal",
            "migration_plan_digest": plan.plan_digest,
            "active_policy_fingerprint": plan.active_policy_fingerprint,
            "pending_policy_fingerprint": plan.pending_policy_fingerprint,
            "writer_epoch": plan.writer_epoch,
            "slot_plan": slot_plan,
            "graph_revision": graph_revision,
            "graph_delta_digest": graph_delta_digest,
            "event_batch_digest": watermark,
            "ledger_position": ledger_position,
            "watermark": watermark,
            "complete_read_set_digest": complete_read_set_digest,
            "membership_digest": _catch_up_membership_digest(slot_plan),
            "partition_revision_before": partition_revision - 1,
            "partition_revision": partition_revision,
        }
        return TemporalMigrationCatchUpEntry.model_validate(
            {**values, "entry_digest": _contract_digest(_CATCH_UP_DOMAIN, values)}
        )

    def trust_catch_up(
        self,
        plan: TrustPolicyMigrationPlan,
        projections: tuple[TrustProjectionRecord, ...],
        *,
        view: TrustProjectionView,
        graph_revision: str,
        graph_delta_digest: str,
        ledger_position: int,
        watermark: str,
        complete_read_set_digest: str,
        partition_revision: int,
    ) -> TrustMigrationCatchUpEntry:
        slot = _one_slot(projections, plan.changed_predicate_ids)
        slot_plan = self._trust_slot_plan(view, slot, projections)
        values = {
            "migration_kind": "trust",
            "migration_plan_digest": plan.plan_digest,
            "active_policy_fingerprint": plan.active_policy_fingerprint,
            "pending_policy_fingerprint": plan.pending_policy_fingerprint,
            "writer_epoch": plan.writer_epoch,
            "slot_plan": slot_plan,
            "graph_revision": graph_revision,
            "graph_delta_digest": graph_delta_digest,
            "event_batch_digest": watermark,
            "ledger_position": ledger_position,
            "watermark": watermark,
            "complete_read_set_digest": complete_read_set_digest,
            "membership_digest": _catch_up_membership_digest(slot_plan),
            "partition_revision_before": partition_revision - 1,
            "partition_revision": partition_revision,
        }
        return TrustMigrationCatchUpEntry.model_validate(
            {**values, "entry_digest": _contract_digest(_CATCH_UP_DOMAIN, values)}
        )

    def prepare_temporal_cutover(
        self,
        plan: TemporalPolicyMigrationPlan,
        pending: TemporalPolicySnapshot,
        results: tuple[TemporalMigrationResult, ...],
        *,
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...] = (),
        final_catch_up_watermark: str,
        expected_partition_revision: int,
        complete_read_set_digest: str,
        authorization: SemanticWriterWriteAuthorization,
    ) -> PreparedTemporalPolicyMigration:
        view = self._history.active_temporal_authority()
        persisted_catch_up, persisted_results = self._load_temporal_progress(plan)
        if (
            tuple(sorted(catch_up, key=lambda item: item.partition_revision))
            != persisted_catch_up
            or tuple(sorted(results, key=lambda item: item.result_digest))
            != persisted_results
            or final_catch_up_watermark
            != (
                persisted_catch_up[-1].watermark
                if persisted_catch_up
                else view.generation.final_catch_up_watermark
            )
            or expected_partition_revision
            != (
                persisted_catch_up[-1].partition_revision
                if persisted_catch_up
                else plan.migration_partition_revision
            )
        ):
            raise PolicyMigrationError("policy_migration_stale_plan")
        catch_up = persisted_catch_up
        results = persisted_results
        self._validate_cutover_coordinates(
            plan, pending.fingerprint, view, catch_up, expected_partition_revision
        )
        _require_committed_results(plan, catch_up, results)
        committed = tuple(
            item
            for item in results
            if isinstance(item, TemporalMigrationCommittedResult)
        )
        outputs = self._temporal_outputs(view, plan, catch_up, committed)
        cutover_values = _cutover_values(
            plan, catch_up, committed, final_catch_up_watermark,
            expected_partition_revision, complete_read_set_digest,
        )
        cutover = TemporalPolicyCutover.model_validate(
            {**cutover_values, "cutover_digest": _contract_digest(_CUTOVER_DOMAIN, cutover_values)}
        )
        publication = self._history.prepare_temporal_migration(
            TemporalPolicyMigrationAdvanceRequest(
                repository_id=self._repository_id,
                migration_plan_digest=plan.plan_digest,
                active_policy_fingerprint_before=plan.active_policy_fingerprint,
                pending_policy_fingerprint=plan.pending_policy_fingerprint,
                base_snapshot_token=plan.base_snapshot_token,
                base_graph_revision=view.generation.base_graph_revision,
                final_catch_up_watermark=final_catch_up_watermark,
                server_derived_base_slot_plan_digests=tuple(item.slot_plan_digest for item in plan.slot_plans),
                server_derived_catch_up_entry_digests=tuple(sorted(item.entry_digest for item in catch_up)),
                canonical_slot_result_digests=tuple(sorted(item.result_digest for item in committed)),
                complete_read_set_digest=complete_read_set_digest,
                cutover_digest=cutover.cutover_digest,
                writer_epoch_before=plan.writer_epoch,
                activated_writer_epoch=plan.writer_epoch + 1,
                temporal_projections=outputs,
                semantic_conflict_authority=(
                    self._history.resolve_semantic_conflict_authority(
                        temporal_projections=outputs,
                    )
                ),
            ),
            capability=self._publication_capability,
            authorization=authorization,
        )
        records, preconditions = self._authority_closure(plan, catch_up, results, cutover)
        return PreparedTemporalPolicyMigration(plan, cutover, publication, records, preconditions)

    def prepare_trust_cutover(
        self,
        plan: TrustPolicyMigrationPlan,
        pending: TrustPolicySnapshot,
        results: tuple[TrustMigrationResult, ...],
        *,
        catch_up: tuple[TrustMigrationCatchUpEntry, ...] = (),
        final_catch_up_watermark: str,
        expected_partition_revision: int,
        complete_read_set_digest: str,
        authorization: SemanticWriterWriteAuthorization,
    ) -> PreparedTrustPolicyMigration:
        view = self._history.active_trust_authority()
        persisted_catch_up, persisted_results = self._load_trust_progress(plan)
        if (
            tuple(sorted(catch_up, key=lambda item: item.partition_revision))
            != persisted_catch_up
            or tuple(sorted(results, key=lambda item: item.result_digest))
            != persisted_results
            or final_catch_up_watermark
            != (
                persisted_catch_up[-1].watermark
                if persisted_catch_up
                else view.generation.final_catch_up_watermark
            )
            or expected_partition_revision
            != (
                persisted_catch_up[-1].partition_revision
                if persisted_catch_up
                else plan.migration_partition_revision
            )
        ):
            raise PolicyMigrationError("policy_migration_stale_plan")
        catch_up = persisted_catch_up
        results = persisted_results
        self._validate_cutover_coordinates(
            plan, pending.fingerprint, view, catch_up, expected_partition_revision
        )
        _require_committed_results(plan, catch_up, results)
        committed = tuple(
            item
            for item in results
            if isinstance(item, TrustMigrationCommittedResult)
        )
        outputs, _ = self._trust_outputs(view, plan, catch_up, committed)
        cutover_commands = self._scheduler.commands_for_migration(
            view,
            outputs,
            pending,
            arbitration_as_of=plan.arbitration_as_of,
            writer_epoch=plan.writer_epoch + 1,
            complete_read_set_digest=complete_read_set_digest,
        )
        commands = tuple(
            sorted(item.command_digest for item in cutover_commands)
        )
        cutover_values = _cutover_values(
            plan, catch_up, committed, final_catch_up_watermark,
            expected_partition_revision, complete_read_set_digest,
        )
        cutover = TrustPolicyCutover.model_validate(
            {**cutover_values, "cutover_digest": _contract_digest(_CUTOVER_DOMAIN, cutover_values)}
        )
        publication = self._history.prepare_trust_migration(
            TrustPolicyMigrationAdvanceRequest(
                repository_id=self._repository_id,
                migration_plan_digest=plan.plan_digest,
                active_policy_fingerprint_before=plan.active_policy_fingerprint,
                pending_policy_fingerprint=plan.pending_policy_fingerprint,
                base_snapshot_token=plan.base_snapshot_token,
                base_graph_revision=view.generation.base_graph_revision,
                final_catch_up_watermark=final_catch_up_watermark,
                server_derived_base_slot_plan_digests=tuple(item.slot_plan_digest for item in plan.slot_plans),
                server_derived_catch_up_entry_digests=tuple(sorted(item.entry_digest for item in catch_up)),
                canonical_slot_result_digests=tuple(sorted(item.result_digest for item in committed)),
                complete_read_set_digest=complete_read_set_digest,
                cutover_digest=cutover.cutover_digest,
                writer_epoch_before=plan.writer_epoch,
                activated_writer_epoch=plan.writer_epoch + 1,
                arbitration_as_of=plan.arbitration_as_of,
                trust_projections=outputs,
                semantic_conflict_authority=(
                    self._history.resolve_semantic_conflict_authority(
                        trust_projections=outputs,
                    )
                ),
                trust_decay_command_digests=commands,
            ),
            capability=self._publication_capability,
            authorization=authorization,
        )
        records, preconditions = self._authority_closure(
            plan,
            catch_up,
            results,
            cutover,
            extra_decay_commands=cutover_commands,
        )
        return PreparedTrustPolicyMigration(plan, cutover, publication, records, preconditions)

    def _temporal_slot_plan(
        self,
        slot: SemanticClaimSlotKey,
        projections: tuple[TemporalProjectionRecord, ...],
    ) -> TemporalMigrationSlotPlan:
        values = {
            "migration_kind": "temporal",
            "claim_slot_key": slot,
            "assertion_ids": _assertion_ids(projections),
            "projection_digests": tuple(item.projection_digest for item in projections),
        }
        return TemporalMigrationSlotPlan.model_validate(
            {**values, "slot_plan_digest": _contract_digest(_SLOT_DOMAIN, values)}
        )

    def _trust_slot_plan(
        self,
        view: TrustProjectionView,
        slot: SemanticClaimSlotKey,
        projections: tuple[TrustProjectionRecord, ...],
    ) -> TrustMigrationSlotPlan:
        values = {
            "migration_kind": "trust",
            "claim_slot_key": slot,
            "assertion_ids": _assertion_ids(projections),
            "projection_digests": tuple(item.projection_digest for item in projections),
            "decay_command_digests": self._scheduler.command_digests_for_slot(view, slot),
        }
        return TrustMigrationSlotPlan.model_validate(
            {**values, "slot_plan_digest": _contract_digest(_SLOT_DOMAIN, values)}
        )

    def _temporal_write_catch_up_entries(
        self,
        plan: TemporalPolicyMigrationPlan,
        persisted: tuple[TemporalMigrationCatchUpEntry, ...],
        projections: tuple[TemporalProjectionRecord, ...],
        *,
        graph_revision: str,
        graph_delta_digest: str,
        ledger_position: int,
        watermark: str,
        complete_read_set_digest: str,
    ) -> tuple[TemporalMigrationCatchUpEntry, ...]:
        latest = {
            _slot_coordinate(item.claim_slot_key): item for item in plan.slot_plans
        }
        for entry in persisted:
            latest[_slot_coordinate(entry.slot_plan.claim_slot_key)] = entry.slot_plan
        current = {
            _slot_coordinate(slot): self._temporal_slot_plan(slot, members)
            for slot, members in _slot_groups(
                projections, plan.changed_predicate_ids
            )
        }
        revision = (
            persisted[-1].partition_revision
            if persisted
            else plan.migration_partition_revision
        )
        entries: list[TemporalMigrationCatchUpEntry] = []
        for coordinate in sorted(set(latest) | set(current)):
            before = latest.get(coordinate)
            after = current.get(coordinate)
            if before == after:
                continue
            if after is not None:
                slot_plan = after
            elif before is not None:
                slot_plan = self._temporal_slot_plan(before.claim_slot_key, ())
            else:
                raise PolicyMigrationError("policy_migration_integrity_error")
            revision += 1
            values = {
                "migration_kind": "temporal",
                "migration_plan_digest": plan.plan_digest,
                "active_policy_fingerprint": plan.active_policy_fingerprint,
                "pending_policy_fingerprint": plan.pending_policy_fingerprint,
                "writer_epoch": plan.writer_epoch,
                "slot_plan": slot_plan,
                "graph_revision": graph_revision,
                "graph_delta_digest": graph_delta_digest,
                "event_batch_digest": watermark,
                "ledger_position": ledger_position,
                "watermark": watermark,
                "complete_read_set_digest": complete_read_set_digest,
                "membership_digest": _catch_up_membership_digest(slot_plan),
                "partition_revision_before": revision - 1,
                "partition_revision": revision,
            }
            entries.append(
                TemporalMigrationCatchUpEntry.model_validate(
                    {
                        **values,
                        "entry_digest": _contract_digest(_CATCH_UP_DOMAIN, values),
                    }
                )
            )
        return tuple(entries)

    def _trust_write_catch_up_entries(
        self,
        plan: TrustPolicyMigrationPlan,
        persisted: tuple[TrustMigrationCatchUpEntry, ...],
        projections: tuple[TrustProjectionRecord, ...],
        *,
        trust_decay_command_digests: tuple[str, ...],
        graph_revision: str,
        graph_delta_digest: str,
        ledger_position: int,
        watermark: str,
        complete_read_set_digest: str,
    ) -> tuple[TrustMigrationCatchUpEntry, ...]:
        latest = {
            _slot_coordinate(item.claim_slot_key): item for item in plan.slot_plans
        }
        for entry in persisted:
            latest[_slot_coordinate(entry.slot_plan.claim_slot_key)] = entry.slot_plan
        current = {
            _slot_coordinate(slot): self._trust_slot_plan_from_membership(
                slot,
                members,
                trust_decay_command_digests,
            )
            for slot, members in _slot_groups(
                projections, plan.changed_predicate_ids
            )
        }
        revision = (
            persisted[-1].partition_revision
            if persisted
            else plan.migration_partition_revision
        )
        entries: list[TrustMigrationCatchUpEntry] = []
        for coordinate in sorted(set(latest) | set(current)):
            before = latest.get(coordinate)
            after = current.get(coordinate)
            if before == after:
                continue
            if after is not None:
                slot_plan = after
            elif before is not None:
                slot_plan = self._trust_slot_plan_from_membership(
                    before.claim_slot_key,
                    (),
                    trust_decay_command_digests,
                )
            else:
                raise PolicyMigrationError("policy_migration_integrity_error")
            revision += 1
            values = {
                "migration_kind": "trust",
                "migration_plan_digest": plan.plan_digest,
                "active_policy_fingerprint": plan.active_policy_fingerprint,
                "pending_policy_fingerprint": plan.pending_policy_fingerprint,
                "writer_epoch": plan.writer_epoch,
                "slot_plan": slot_plan,
                "graph_revision": graph_revision,
                "graph_delta_digest": graph_delta_digest,
                "event_batch_digest": watermark,
                "ledger_position": ledger_position,
                "watermark": watermark,
                "complete_read_set_digest": complete_read_set_digest,
                "membership_digest": _catch_up_membership_digest(slot_plan),
                "partition_revision_before": revision - 1,
                "partition_revision": revision,
            }
            entries.append(
                TrustMigrationCatchUpEntry.model_validate(
                    {
                        **values,
                        "entry_digest": _contract_digest(_CATCH_UP_DOMAIN, values),
                    }
                )
            )
        return tuple(entries)

    def _trust_slot_plan_from_membership(
        self,
        slot: SemanticClaimSlotKey,
        projections: tuple[TrustProjectionRecord, ...],
        command_digests: tuple[str, ...],
    ) -> TrustMigrationSlotPlan:
        values = {
            "migration_kind": "trust",
            "claim_slot_key": slot,
            "assertion_ids": _assertion_ids(projections),
            "projection_digests": tuple(
                item.projection_digest for item in projections
            ),
            "decay_command_digests": (
                self._scheduler.command_digests_for_slot_membership(
                    command_digests, slot
                )
            ),
        }
        return TrustMigrationSlotPlan.model_validate(
            {**values, "slot_plan_digest": _contract_digest(_SLOT_DOMAIN, values)}
        )

    def _temporal_slot_projections(
        self,
        slot_plan: TemporalMigrationSlotPlan,
    ) -> tuple[TemporalProjectionRecord, ...]:
        projections = tuple(
            self._load_projection("temporal", digest, TemporalProjectionRecord)
            for digest in slot_plan.projection_digests
        )
        if any(
            item.claim_slot_key != slot_plan.claim_slot_key for item in projections
        ):
            raise PolicyMigrationError("policy_migration_integrity_error")
        return projections

    @staticmethod
    def _temporal_command(
        plan: TemporalPolicyMigrationPlan,
        slot_plan: TemporalMigrationSlotPlan,
        *,
        graph_revision: str,
        complete_read_set_digest: str,
        work_item_digest: str,
        command_phase: Literal["base", "catch_up"],
    ) -> TemporalReprojectionCommand:
        return TemporalReprojectionCommand.create(
            migration_plan_digest=plan.plan_digest,
            migration_work_item_digest=work_item_digest,
            slot_plan_digest=slot_plan.slot_plan_digest,
            active_policy_fingerprint=plan.active_policy_fingerprint,
            active_trust_policy_fingerprint=plan.active_trust_policy_fingerprint,
            active_trust_policy_snapshot_digest=(
                plan.active_trust_policy_snapshot_digest
            ),
            pending_policy_fingerprint=plan.pending_policy_fingerprint,
            pending_policy_snapshot_digest=plan.pending_policy_snapshot_digest,
            policy_effective_at=plan.policy_effective_at,
            writer_epoch=plan.writer_epoch,
            graph_revision=graph_revision,
            complete_read_set_digest=complete_read_set_digest,
            command_phase=command_phase,
        )

    def _temporal_commands_for(
        self,
        plan: TemporalPolicyMigrationPlan,
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...]
        | tuple[TrustMigrationCatchUpEntry, ...],
    ) -> tuple[TemporalReprojectionCommand, ...]:
        temporal_catch_up = tuple(
            entry
            for entry in catch_up
            if isinstance(entry, TemporalMigrationCatchUpEntry)
        )
        if len(temporal_catch_up) != len(catch_up):
            raise PolicyMigrationError("policy_migration_integrity_error")
        commands = [
            self._temporal_command(
                plan,
                slot_plan,
                graph_revision=plan.base_graph_revision,
                complete_read_set_digest=plan.base_snapshot_token,
                work_item_digest=slot_plan.slot_plan_digest,
                command_phase="base",
            )
            for slot_plan in plan.slot_plans
        ]
        commands.extend(
            self._temporal_command(
                plan,
                entry.slot_plan,
                graph_revision=entry.graph_revision,
                complete_read_set_digest=entry.complete_read_set_digest,
                work_item_digest=entry.entry_digest,
                command_phase="catch_up",
            )
            for entry in temporal_catch_up
        )
        return tuple(
            sorted(commands, key=lambda item: (item.policy_effective_at, item.command_id))
        )

    def _apply_temporal_policy(
        self,
        projection: TemporalProjectionRecord,
        policy: TemporalPolicySnapshot,
        active_trust_policy: TrustPolicySnapshot,
    ) -> TemporalProjectionRecord:
        slot = projection.claim_slot_key
        if slot is None:
            return _retag_temporal(projection, policy.fingerprint)
        retained_claims = self._retained_claims(projection)
        if retained_claims is not None:
            return self._resolve_retained_temporal_evidence(
                projection,
                retained_claims,
                policy,
                active_trust_policy,
            )
        rules = tuple(
            rule for rule in policy.rules if rule.predicate_id == slot.predicate_id
        )
        if len(rules) != 1:
            raise PolicyMigrationError("policy_migration_policy_mismatch")
        rule = rules[0]
        interval = projection.valid_interval
        valid = (
            rule.valid_time_requirement == "optional"
            or (
                rule.valid_time_requirement == "required"
                and interval is not None
                and (rule.allow_open_end or interval.end is not None)
            )
            or (
                rule.valid_time_requirement == "atemporal"
                and interval is None
            )
        )
        values = projection.model_dump(
            mode="python",
            exclude={
                "temporal_policy_fingerprint",
                "selected_assertion_ids",
                "contested_assertion_ids",
                "retained_assertion_ids",
                "outcome",
                "evidence",
                "projection_digest",
            },
        )
        if valid:
            return TemporalProjectionRecord.create(
                **values,
                temporal_policy_fingerprint=policy.fingerprint,
                selected_assertion_ids=projection.selected_assertion_ids,
                contested_assertion_ids=projection.contested_assertion_ids,
                retained_assertion_ids=projection.retained_assertion_ids,
                outcome=projection.outcome,
                evidence=projection.evidence,
            )
        evidence = tuple(
            item.model_copy(update={"authority_relation": "retained_noncurrent"})
            for item in projection.evidence
        )
        return TemporalProjectionRecord.create(
            **values,
            temporal_policy_fingerprint=policy.fingerprint,
            selected_assertion_ids=(),
            contested_assertion_ids=(),
            retained_assertion_ids=tuple(
                sorted(item.candidate_id for item in evidence)
            ),
            outcome="unknown",
            evidence=evidence,
        )

    def _retained_claims(
        self,
        projection: TemporalProjectionRecord,
    ) -> tuple[ClaimAssertion, ...] | None:
        record = self._memory_plane.get_record(
            "semantic_ingestion:event-authority:state"
        )
        if record is None:
            return None
        canonical_hex = record.content.get("canonical_hex")
        if not isinstance(canonical_hex, str):
            raise PolicyMigrationError("policy_migration_integrity_error")
        try:
            state = decode_semantic_replay_state(bytes.fromhex(canonical_hex))
        except (SemanticEventReplayError, TypeError, ValueError) as exc:
            raise PolicyMigrationError("policy_migration_integrity_error") from exc
        if (
            state.repository_id != self._repository_id
            or record.content.get("state_digest") != state.state_digest
        ):
            raise PolicyMigrationError("policy_migration_integrity_error")
        expected = set(_assertion_ids((projection,)))
        claims = tuple(
            item.record
            for item in state.materialized_records
            if isinstance(item.record, ClaimAssertion)
            and item.record.claim_assertion_id in expected
        )
        if {item.claim_assertion_id for item in claims} != expected:
            raise PolicyMigrationError("policy_migration_integrity_error")
        evidence_digests = {
            item.candidate_id: item.candidate_digest for item in projection.evidence
        }
        if any(
            evidence_digests.get(claim.claim_assertion_id) != claim.record_digest
            for claim in claims
        ):
            raise PolicyMigrationError("policy_migration_integrity_error")
        return tuple(sorted(claims, key=lambda item: item.claim_assertion_id))

    @staticmethod
    def _resolve_retained_temporal_evidence(
        projection: TemporalProjectionRecord,
        claims: tuple[ClaimAssertion, ...],
        policy: TemporalPolicySnapshot,
        trust_policy: TrustPolicySnapshot,
    ) -> TemporalProjectionRecord:
        slot = projection.claim_slot_key
        if slot is None:
            raise PolicyMigrationError("policy_migration_integrity_error")
        candidates = tuple(
            sorted(
                (
                    candidate
                    for claim in claims
                    for candidate in claim.temporal_evidence.decision_closure.candidates
                ),
                key=lambda item: item.candidate_id,
            )
        )
        if len({item.candidate_id for item in candidates}) != len(candidates):
            raise PolicyMigrationError("policy_migration_integrity_error")
        references = tuple(
            claim.temporal_evidence.reference_evidence
            for claim in claims
            if claim.temporal_evidence.reference_evidence is not None
        )
        reference = references[0] if references and all(
            item == references[0] for item in references
        ) else None
        closure = TemporalEvidenceResolver().resolve(
            predicate_id=slot.predicate_id,
            candidates=candidates,
            reference_evidence=reference,
            source_present_attachment=bool(candidates),
            trust_policy=trust_policy,
            temporal_policy=policy,
            arbitration_as_of=max(
                claim.temporal_evidence.decision_closure.arbitration_as_of
                for claim in claims
            ),
        )
        candidate_claims = {
            candidate.candidate_id: claim.claim_assertion_id
            for claim in claims
            for candidate in claim.temporal_evidence.decision_closure.candidates
        }
        if closure.resolution_rule in {
            "atemporal",
            "authenticated_reference_open_start",
        }:
            selected = projection.selected_assertion_ids
        else:
            selected = tuple(
                sorted(
                    {
                        candidate_claims[candidate_id]
                        for candidate_id in closure.selected_candidate_ids
                    }
                )
            )
        contested = tuple(
            sorted(
                {
                    candidate_claims[candidate_id]
                    for candidate_id in closure.contested_candidate_ids
                }
            )
        )
        if closure.outcome != "pass":
            selected = ()
        retained = tuple(
            sorted(
                set(_assertion_ids((projection,))) - set(selected) - set(contested)
            )
        )
        evidence = tuple(
            item.model_copy(
                update={
                    "authority_relation": (
                        "winner"
                        if item.candidate_id in selected
                        else "contested_top"
                        if item.candidate_id in contested
                        else "retained_noncurrent"
                    )
                }
            )
            for item in projection.evidence
        )
        return TemporalProjectionRecord.create(
            **projection.model_dump(
                mode="python",
                exclude={
                    "temporal_policy_fingerprint",
                    "valid_interval",
                    "outcome",
                    "evidence",
                    "selected_assertion_ids",
                    "contested_assertion_ids",
                    "retained_assertion_ids",
                    "projection_digest",
                },
            ),
            temporal_policy_fingerprint=policy.fingerprint,
            valid_interval=closure.resolved_interval,
            outcome=closure.outcome,
            evidence=evidence,
            selected_assertion_ids=selected,
            contested_assertion_ids=contested,
            retained_assertion_ids=retained,
        )

    def _trust_slot_projections(
        self,
        slot_plan: TrustMigrationSlotPlan,
    ) -> tuple[TrustProjectionRecord, ...]:
        projections = tuple(
            self._load_projection("trust", digest, TrustProjectionRecord)
            for digest in slot_plan.projection_digests
        )
        if any(
            item.claim_slot_key != slot_plan.claim_slot_key for item in projections
        ):
            raise PolicyMigrationError("policy_migration_integrity_error")
        return projections

    def _load_projection(
        self,
        kind: MigrationKind,
        digest: str,
        model: type[_ProjectionT],
    ) -> _ProjectionT:
        matches = tuple(
            record
            for record in self._memory_plane.list_records(
                source_kind=f"semantic_projection_{kind}_projection"
            )
            if record.memory_id.endswith(f":{digest}")
        )
        if len(matches) != 1:
            raise PolicyMigrationError("policy_migration_integrity_error")
        record = matches[0]
        canonical_hex = record.content.get("canonical_hex")
        if not isinstance(canonical_hex, str):
            raise PolicyMigrationError("policy_migration_integrity_error")
        try:
            canonical_bytes = bytes.fromhex(canonical_hex)
            raw = decode_typed_value(canonical_bytes)
            value = model.model_validate(raw)
        except (CanonicalTypedValueError, TypeError, ValueError) as exc:
            raise PolicyMigrationError("policy_migration_integrity_error") from exc
        if (
            value.projection_digest != digest
            or record.content.get("authority_digest")
            != sha256(canonical_bytes).hexdigest()
            or not record.memory_id.startswith(
                f"semantic_projection:{self._repository_token}:{kind}:projection:"
            )
        ):
            raise PolicyMigrationError("policy_migration_integrity_error")
        return value

    def _validate_temporal_result_membership(
        self,
        plan: TemporalPolicyMigrationPlan,
        slot_plan: TemporalMigrationSlotPlan,
        projections: tuple[TemporalProjectionRecord, ...],
    ) -> None:
        if (
            slot_plan.claim_slot_key.predicate_id not in plan.changed_predicate_ids
            or _assertion_ids(projections) != slot_plan.assertion_ids
            or any(
                item.claim_slot_key != slot_plan.claim_slot_key
                or item.temporal_policy_fingerprint
                != plan.pending_policy_fingerprint
                for item in projections
            )
        ):
            raise PolicyMigrationError("policy_migration_stale_plan")

    def _validate_trust_result_membership(
        self,
        plan: TrustPolicyMigrationPlan,
        slot_plan: TrustMigrationSlotPlan,
        projections: tuple[TrustProjectionRecord, ...],
    ) -> None:
        if (
            slot_plan.claim_slot_key.predicate_id not in plan.changed_predicate_ids
            or _assertion_ids(projections) != slot_plan.assertion_ids
            or any(
                item.claim_slot_key != slot_plan.claim_slot_key
                or item.trust_policy_fingerprint != plan.pending_policy_fingerprint
                or item.arbitration_as_of != plan.arbitration_as_of
                for item in projections
            )
        ):
            raise PolicyMigrationError("policy_migration_stale_plan")

    def _validate_cutover_coordinates(
        self,
        plan: TemporalPolicyMigrationPlan | TrustPolicyMigrationPlan,
        pending_fingerprint: str,
        view: TemporalProjectionView | TrustProjectionView,
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...] | tuple[TrustMigrationCatchUpEntry, ...],
        expected_partition_revision: int,
    ) -> None:
        if (
            plan.repository_id != self._repository_id
            or plan.pending_policy_fingerprint != pending_fingerprint
            or view.pointer.policy_fingerprint != plan.active_policy_fingerprint
            or view.pointer.writer_epoch != plan.writer_epoch
        ):
            raise PolicyMigrationError("policy_migration_stale_plan")
        revisions = tuple(item.partition_revision for item in catch_up)
        expected = tuple(range(plan.migration_partition_revision + 1, expected_partition_revision + 1))
        if (
            revisions != expected
            or any(item.migration_plan_digest != plan.plan_digest for item in catch_up)
            or any(
                item.active_policy_fingerprint != plan.active_policy_fingerprint
                or item.pending_policy_fingerprint
                != plan.pending_policy_fingerprint
                or item.writer_epoch != plan.writer_epoch
                or item.partition_revision_before
                != item.partition_revision - 1
                for item in catch_up
            )
            or tuple(item.ledger_position for item in catch_up)
            != tuple(sorted(item.ledger_position for item in catch_up))
        ):
            raise PolicyMigrationError("policy_migration_stale_plan")
        if (
            catch_up
            and catch_up[-1].graph_revision
            != view.generation.base_graph_revision
        ):
            raise PolicyMigrationError("policy_migration_stale_plan")
        latest = {
            _slot_coordinate(item.claim_slot_key): item for item in plan.slot_plans
        }
        for entry in catch_up:
            latest[_slot_coordinate(entry.slot_plan.claim_slot_key)] = entry.slot_plan
        latest = {
            coordinate: slot_plan
            for coordinate, slot_plan in latest.items()
            if slot_plan.projection_digests
        }
        if isinstance(plan, TemporalPolicyMigrationPlan):
            if not isinstance(view, TemporalProjectionView):
                raise PolicyMigrationError("policy_migration_stale_plan")
            current = {
                _slot_coordinate(slot): self._temporal_slot_plan(slot, projections)
                for slot, projections in _slot_groups(
                    view.projections, plan.changed_predicate_ids
                )
            }
        else:
            if not isinstance(view, TrustProjectionView):
                raise PolicyMigrationError("policy_migration_stale_plan")
            current = {
                _slot_coordinate(slot): self._trust_slot_plan(view, slot, projections)
                for slot, projections in _slot_groups(
                    view.projections, plan.changed_predicate_ids
                )
            }
        if current != latest:
            raise PolicyMigrationError("policy_migration_stale_plan")

    def _temporal_outputs(
        self,
        view: TemporalProjectionView,
        plan: TemporalPolicyMigrationPlan,
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...],
        results: tuple[TemporalMigrationCommittedResult, ...],
    ) -> tuple[TemporalProjectionRecord, ...]:
        replacements = _latest_results(plan.slot_plans, catch_up, results)
        changed_slots = set(replacements)
        outputs = [
            _retag_temporal(item, plan.pending_policy_fingerprint)
            for item in view.projections
            if _slot_coordinate(item.claim_slot_key) not in changed_slots
        ]
        for result in replacements.values():
            outputs.extend(result.projections)
        return tuple(sorted(outputs, key=lambda item: item.projection_digest))

    def _trust_outputs(
        self,
        view: TrustProjectionView,
        plan: TrustPolicyMigrationPlan,
        catch_up: tuple[TrustMigrationCatchUpEntry, ...],
        results: tuple[TrustMigrationCommittedResult, ...],
    ) -> tuple[tuple[TrustProjectionRecord, ...], tuple[str, ...]]:
        replacements = _latest_results(plan.slot_plans, catch_up, results)
        changed_slots = set(replacements)
        outputs = [
            _retag_trust(item, plan.pending_policy_fingerprint, plan.arbitration_as_of)
            for item in view.projections
            if _slot_coordinate(item.claim_slot_key) not in changed_slots
        ]
        commands: set[str] = set()
        for result in replacements.values():
            outputs.extend(result.projections)
            commands.update(result.decay_command_digests)
        return (
            tuple(sorted(outputs, key=lambda item: item.projection_digest)),
            tuple(sorted(commands)),
        )

    def _authority_closure(
        self,
        plan: TemporalPolicyMigrationPlan | TrustPolicyMigrationPlan,
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...]
        | tuple[TrustMigrationCatchUpEntry, ...],
        results: tuple[TemporalMigrationResult, ...]
        | tuple[TrustMigrationResult, ...],
        cutover: TemporalPolicyCutover | TrustPolicyCutover,
        *,
        extra_decay_commands: tuple[TrustDecayCommand, ...] = (),
    ) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[MemoryPlanePrecondition, ...]]:
        result_commands = self._validated_trust_decay_commands(results)
        commands = {
            command.command_digest: command
            for command in (*result_commands, *extra_decay_commands)
        }
        try:
            command_records, command_preconditions = (
                self._scheduler.prepare_command_records(tuple(commands.values()))
            )
        except ProjectionSchedulerError as exc:
            raise PolicyMigrationError("policy_migration_integrity_error") from exc
        temporal_commands = (
            self._temporal_commands_for(plan, catch_up)
            if isinstance(plan, TemporalPolicyMigrationPlan)
            else ()
        )
        values = (
            ("migration_plan", plan, plan.plan_digest),
            *(("migration_catch_up", item, item.entry_digest) for item in catch_up),
            *(("migration_result", item, item.result_digest) for item in results),
            *(
                ("migration_command", command, command.command_digest)
                for command in temporal_commands
            ),
            ("migration_cutover", cutover, cutover.cutover_digest),
        )
        records: list[CanonicalMemoryRecord] = []
        preconditions: list[MemoryPlanePrecondition] = []
        kind = plan.migration_kind
        for authority_kind, value, digest in values:
            record = self._authority_record(kind, authority_kind, value, digest)
            current = self._memory_plane.get_record(record.memory_id)
            if current is None:
                records.append(record)
                preconditions.append(RecordAbsentPrecondition(memory_id=record.memory_id))
            elif current.source_kind == record.source_kind and current.content == record.content:
                records.append(current)
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=current.memory_id,
                        expected_digest=record_digest(current),
                    )
                )
            else:
                raise PolicyMigrationError("policy_migration_integrity_error")
        return (
            (*records, *command_records),
            (*preconditions, *command_preconditions),
        )

    def _progress_closure(
        self,
        plan: TemporalPolicyMigrationPlan | TrustPolicyMigrationPlan,
        catch_up: tuple[TemporalMigrationCatchUpEntry, ...]
        | tuple[TrustMigrationCatchUpEntry, ...],
        results: tuple[TemporalMigrationResult, ...]
        | tuple[TrustMigrationResult, ...],
    ) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[MemoryPlanePrecondition, ...]]:
        temporal_commands = (
            self._temporal_commands_for(plan, catch_up)
            if isinstance(plan, TemporalPolicyMigrationPlan)
            else ()
        )
        decay_commands = self._validated_trust_decay_commands(results)
        try:
            command_records, command_preconditions = (
                self._scheduler.prepare_command_records(decay_commands)
            )
        except ProjectionSchedulerError as exc:
            raise PolicyMigrationError("policy_migration_integrity_error") from exc
        values = (
            ("migration_plan", plan, plan.plan_digest),
            *(("migration_catch_up", item, item.entry_digest) for item in catch_up),
            *(("migration_result", item, item.result_digest) for item in results),
            *(
                ("migration_command", command, command.command_digest)
                for command in temporal_commands
            ),
        )
        records: list[CanonicalMemoryRecord] = []
        preconditions: list[MemoryPlanePrecondition] = []
        for authority_kind, value, digest in values:
            record = self._authority_record(
                plan.migration_kind, authority_kind, value, digest
            )
            current = self._memory_plane.get_record(record.memory_id)
            if current is None:
                records.append(record)
                preconditions.append(RecordAbsentPrecondition(memory_id=record.memory_id))
            elif current.source_kind == record.source_kind and current.content == record.content:
                records.append(current)
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=current.memory_id,
                        expected_digest=record_digest(current),
                    )
                )
            else:
                raise PolicyMigrationError("policy_migration_integrity_error")
        return (
            (*records, *command_records),
            (*preconditions, *command_preconditions),
        )

    @staticmethod
    def _validated_trust_decay_commands(
        results: tuple[TemporalMigrationResult, ...]
        | tuple[TrustMigrationResult, ...],
    ) -> tuple[TrustDecayCommand, ...]:
        commands: list[TrustDecayCommand] = []
        try:
            for item in results:
                if isinstance(item, TrustMigrationCommittedResult):
                    validated = TrustMigrationCommittedResult.model_validate(
                        item.model_dump(mode="python")
                    )
                    if validated != item:
                        raise ValueError("trust migration result changed during validation")
                    for command in validated.decay_commands:
                        canonical = TrustDecayCommand.model_validate(
                            command.model_dump(mode="python")
                        )
                        if canonical != command:
                            raise ValueError("trust decay command changed during validation")
                        commands.append(canonical)
                elif isinstance(item, TrustMigrationUnavailableResult):
                    validated = TrustMigrationUnavailableResult.model_validate(
                        item.model_dump(mode="python")
                    )
                    if validated != item:
                        raise ValueError("trust migration result changed during validation")
        except (TypeError, ValueError) as exc:
            raise PolicyMigrationError("policy_migration_integrity_error") from exc
        return tuple(commands)

    def _load_temporal_progress(
        self,
        plan: TemporalPolicyMigrationPlan,
    ) -> tuple[
        tuple[TemporalMigrationCatchUpEntry, ...],
        tuple[TemporalMigrationResult, ...],
    ]:
        persisted_plan = self._load_plan("temporal", plan.plan_digest)
        if persisted_plan != plan:
            raise PolicyMigrationError("policy_migration_stale_plan")
        catch_up = tuple(
            item
            for item in self._load_progress_values(
                "temporal", "migration_catch_up", TemporalMigrationCatchUpEntry
            )
            if item.migration_plan_digest == plan.plan_digest
        )
        results: list[TemporalMigrationResult] = []
        for raw, record in self._raw_progress_records("temporal", "migration_result"):
            model = (
                TemporalMigrationCommittedResult
                if raw.get("status") == "committed"
                else TemporalMigrationUnavailableResult
                if raw.get("status") == "unavailable"
                else None
            )
            if model is None:
                raise PolicyMigrationError("policy_migration_integrity_error")
            item = self._validate_authority_value(record, raw, model, "result_digest")
            if item.migration_plan_digest == plan.plan_digest:
                results.append(item)
        return (
            tuple(sorted(catch_up, key=lambda item: item.partition_revision)),
            tuple(sorted(results, key=lambda item: item.result_digest)),
        )

    def _load_trust_progress(
        self,
        plan: TrustPolicyMigrationPlan,
    ) -> tuple[
        tuple[TrustMigrationCatchUpEntry, ...],
        tuple[TrustMigrationResult, ...],
    ]:
        persisted_plan = self._load_plan("trust", plan.plan_digest)
        if persisted_plan != plan:
            raise PolicyMigrationError("policy_migration_stale_plan")
        catch_up = tuple(
            item
            for item in self._load_progress_values(
                "trust", "migration_catch_up", TrustMigrationCatchUpEntry
            )
            if item.migration_plan_digest == plan.plan_digest
        )
        results: list[TrustMigrationResult] = []
        for raw, record in self._raw_progress_records("trust", "migration_result"):
            model = (
                TrustMigrationCommittedResult
                if raw.get("status") == "committed"
                else TrustMigrationUnavailableResult
                if raw.get("status") == "unavailable"
                else None
            )
            if model is None:
                raise PolicyMigrationError("policy_migration_integrity_error")
            item = self._validate_authority_value(record, raw, model, "result_digest")
            if item.migration_plan_digest == plan.plan_digest:
                results.append(item)
        return (
            tuple(sorted(catch_up, key=lambda item: item.partition_revision)),
            tuple(sorted(results, key=lambda item: item.result_digest)),
        )

    def _load_plan(
        self,
        kind: MigrationKind,
        plan_digest: str,
    ) -> TemporalPolicyMigrationPlan | TrustPolicyMigrationPlan:
        model = (
            TemporalPolicyMigrationPlan
            if kind == "temporal"
            else TrustPolicyMigrationPlan
        )
        matches = tuple(
            item
            for item in self._load_progress_values(
                kind, "migration_plan", model, digest_field="plan_digest"
            )
            if item.plan_digest == plan_digest
        )
        if len(matches) != 1:
            raise PolicyMigrationError("policy_migration_stale_plan")
        return matches[0]

    def _active_plan(
        self,
        kind: MigrationKind,
    ) -> tuple[
        TemporalPolicyMigrationPlan | TrustPolicyMigrationPlan,
        CanonicalMemoryRecord,
    ] | None:
        plan_model = (
            TemporalPolicyMigrationPlan
            if kind == "temporal"
            else TrustPolicyMigrationPlan
        )
        cutover_model = (
            TemporalPolicyCutover if kind == "temporal" else TrustPolicyCutover
        )
        completed = {
            item.migration_plan_digest
            for item in self._load_progress_values(
                kind,
                "migration_cutover",
                cutover_model,
                digest_field="cutover_digest",
            )
        }
        candidates: list[
            tuple[
                TemporalPolicyMigrationPlan | TrustPolicyMigrationPlan,
                CanonicalMemoryRecord,
            ]
        ] = []
        for raw, record in self._raw_progress_records(kind, "migration_plan"):
            plan = self._validate_authority_value(
                record, raw, plan_model, "plan_digest"
            )
            if plan.plan_digest not in completed:
                candidates.append((plan, record))
        if len(candidates) > 1:
            raise PolicyMigrationError("policy_migration_integrity_error")
        return candidates[0] if candidates else None

    def _load_progress_values(
        self,
        kind: MigrationKind,
        authority_kind: str,
        model,
        *,
        digest_field: str = "entry_digest",
    ):
        return tuple(
            self._validate_authority_value(
                record, raw, model, digest_field
            )
            for raw, record in self._raw_progress_records(kind, authority_kind)
        )

    def _raw_progress_records(
        self,
        kind: MigrationKind,
        authority_kind: str,
    ) -> tuple[tuple[dict[str, object], CanonicalMemoryRecord], ...]:
        values: list[tuple[dict[str, object], CanonicalMemoryRecord]] = []
        prefix = f"semantic_projection:{self._repository_token}:{kind}:"
        source_kind = f"semantic_projection_{kind}_{authority_kind}"
        for record in self._memory_plane.list_records(source_kind=source_kind):
            if (
                not record.memory_id.startswith(prefix)
                or record.content.get("projection_authority_kind") != authority_kind
            ):
                raise PolicyMigrationError("policy_migration_integrity_error")
            canonical_hex = record.content.get("canonical_hex")
            if not isinstance(canonical_hex, str):
                raise PolicyMigrationError("policy_migration_integrity_error")
            try:
                raw = decode_typed_value(bytes.fromhex(canonical_hex))
            except (CanonicalTypedValueError, TypeError, ValueError) as exc:
                raise PolicyMigrationError("policy_migration_integrity_error") from exc
            if not isinstance(raw, dict):
                raise PolicyMigrationError("policy_migration_integrity_error")
            values.append((raw, record))
        return tuple(values)

    def _validate_authority_value(
        self,
        record: CanonicalMemoryRecord,
        raw: dict[str, object],
        model,
        digest_field: str,
    ):
        try:
            value = model.model_validate(raw)
            digest = getattr(value, digest_field)
        except (AttributeError, TypeError, ValueError) as exc:
            raise PolicyMigrationError("policy_migration_integrity_error") from exc
        if (
            record.content.get("authority_digest") != digest
            or not record.memory_id.endswith(f":{digest}")
        ):
            raise PolicyMigrationError("policy_migration_integrity_error")
        return value

    def _authority_record(
        self,
        kind: str,
        authority_kind: str,
        value: BaseModel,
        digest: str,
    ) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(
            memory_id=(
                f"semantic_projection:{self._repository_token}:{kind}:"
                f"{authority_kind}:{digest}"
            ),
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "projection_authority_kind": authority_kind,
                "canonical_hex": encode_typed_value(value.model_dump(mode="python")).hex(),
                "authority_digest": digest,
            },
            status=CommitStatus.COMMITTED,
            source_kind=f"semantic_projection_{kind}_{authority_kind}",
            timestamp=_utc(self._now()),
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )


class _PredicateRule(Protocol):
    predicate_id: str


def _changed_predicates(
    active: tuple[_PredicateRule, ...],
    pending: tuple[_PredicateRule, ...],
) -> tuple[str, ...]:
    before = {item.predicate_id: item for item in active}
    after = {item.predicate_id: item for item in pending}
    return tuple(
        sorted(
            predicate_id
            for predicate_id in set(before) | set(after)
            if before.get(predicate_id) != after.get(predicate_id)
        )
    )


_ProjectionT = TypeVar(
    "_ProjectionT", TemporalProjectionRecord, TrustProjectionRecord
)


def _slot_groups(
    projections: tuple[_ProjectionT, ...],
    predicates: tuple[str, ...],
) -> tuple[tuple[SemanticClaimSlotKey, tuple[_ProjectionT, ...]], ...]:
    groups: dict[bytes, tuple[SemanticClaimSlotKey, list[_ProjectionT]]] = {}
    for projection in projections:
        slot = projection.claim_slot_key
        if not isinstance(slot, SemanticClaimSlotKey) or slot.predicate_id not in predicates:
            continue
        key = encode_typed_value(slot.model_dump(mode="python"))
        if key not in groups:
            groups[key] = (slot, [])
        groups[key][1].append(projection)
    return tuple(
        (slot, tuple(sorted(items, key=lambda item: item.projection_digest)))
        for _, (slot, items) in sorted(groups.items())
    )


def _assertion_ids(projections: tuple[_ProjectionT, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                item.candidate_id
                for projection in projections
                for item in projection.evidence
                if item.assertion_key is not None
            }
        )
    )


def _catch_up_membership_digest(
    slot_plan: TemporalMigrationSlotPlan | TrustMigrationSlotPlan,
) -> str:
    values: dict[str, object] = {
        "migration_kind": slot_plan.migration_kind,
        "claim_slot_key": slot_plan.claim_slot_key,
        "assertion_ids": slot_plan.assertion_ids,
        "projection_digests": slot_plan.projection_digests,
    }
    if isinstance(slot_plan, TrustMigrationSlotPlan):
        values["decay_command_digests"] = slot_plan.decay_command_digests
    return _contract_digest(_CATCH_UP_DOMAIN, values)


def _one_slot(
    projections: tuple[_ProjectionT, ...],
    changed_predicate_ids: tuple[str, ...],
) -> SemanticClaimSlotKey:
    if not projections or projections[0].claim_slot_key is None:
        raise PolicyMigrationError("policy_migration_stale_plan")
    slot = projections[0].claim_slot_key
    if (
        slot.predicate_id not in changed_predicate_ids
        or any(item.claim_slot_key != slot for item in projections)
    ):
        raise PolicyMigrationError("policy_migration_stale_plan")
    return slot


def _slot_coordinate(slot: SemanticClaimSlotKey | None) -> bytes:
    return (
        b"legacy-projection"
        if slot is None
        else encode_typed_value(slot.model_dump(mode="python"))
    )


def _base_snapshot_token(view: TemporalProjectionView | TrustProjectionView) -> str:
    return _contract_digest(
        _PLAN_DOMAIN,
        {
            "pointer_digest": view.pointer.pointer_digest,
            "generation_digest": view.generation.generation_digest,
            "base_graph_revision": view.generation.base_graph_revision,
            "projection_digests": tuple(item.projection_digest for item in view.projections),
        },
    )


def _require_committed_results(plan, catch_up, results):
    if any(item.status != "committed" for item in results):
        raise PolicyMigrationError("policy_migration_incomplete")
    expected = {
        *(item.slot_plan_digest for item in plan.slot_plans),
        *(item.entry_digest for item in catch_up),
    }
    observed = {item.migration_work_item_digest for item in results}
    if (
        expected != observed
        or len(results) != len(expected)
        or any(item.migration_plan_digest != plan.plan_digest for item in results)
    ):
        raise PolicyMigrationError("policy_migration_incomplete")
    return results


def _latest_results(base_plans, catch_up, results):
    by_digest = {item.migration_work_item_digest: item for item in results}
    latest = {
        _slot_coordinate(item.claim_slot_key): by_digest[item.slot_plan_digest]
        for item in base_plans
    }
    for entry in catch_up:
        latest[_slot_coordinate(entry.slot_plan.claim_slot_key)] = by_digest[entry.entry_digest]
    return latest


def _cutover_values(plan, catch_up, results, watermark, partition_revision, read_set):
    return {
        "migration_kind": plan.migration_kind,
        "migration_plan_digest": plan.plan_digest,
        "active_policy_fingerprint_before": plan.active_policy_fingerprint,
        "pending_policy_fingerprint": plan.pending_policy_fingerprint,
        "expected_base_slot_plan_digests": tuple(item.slot_plan_digest for item in plan.slot_plans),
        "expected_catch_up_entry_digests": tuple(sorted(item.entry_digest for item in catch_up)),
        "committed_result_digests": tuple(sorted(item.result_digest for item in results)),
        "final_catch_up_watermark": watermark,
        "expected_partition_revision": partition_revision,
        "expected_writer_epoch": plan.writer_epoch,
        "activated_writer_epoch": plan.writer_epoch + 1,
        "complete_read_set_digest": read_set,
    }


def _retag_temporal(item: TemporalProjectionRecord, policy_fingerprint: str) -> TemporalProjectionRecord:
    return TemporalProjectionRecord.create(
        **item.model_dump(
            mode="python",
            exclude={"temporal_policy_fingerprint", "projection_digest"},
        ),
        temporal_policy_fingerprint=policy_fingerprint,
    )


def _retag_trust(
    item: TrustProjectionRecord,
    policy_fingerprint: str,
    arbitration_as_of: datetime,
) -> TrustProjectionRecord:
    return TrustProjectionRecord.create(
        **item.model_dump(
            mode="python",
            exclude={"trust_policy_fingerprint", "arbitration_as_of", "projection_digest"},
        ),
        trust_policy_fingerprint=policy_fingerprint,
        arbitration_as_of=arbitration_as_of,
    )


__all__ = [
    "PolicyMigrationError",
    "PolicyMigrationRepository",
    "PreparedPolicyMigrationCatchUp",
    "PreparedPolicyMigrationProgress",
    "PreparedTemporalPolicyMigration",
    "PreparedTrustPolicyMigration",
    "TemporalMigrationCatchUpEntry",
    "TemporalMigrationCommittedResult",
    "TemporalMigrationSlotPlan",
    "TemporalMigrationUnavailableResult",
    "TemporalPolicyCutover",
    "TemporalPolicyMigrationPlan",
    "TemporalReprojectionCommand",
    "TrustMigrationCatchUpEntry",
    "TrustMigrationCommittedResult",
    "TrustMigrationSlotPlan",
    "TrustMigrationUnavailableResult",
    "TrustPolicyCutover",
    "TrustPolicyMigrationPlan",
]
