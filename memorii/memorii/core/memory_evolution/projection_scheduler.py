"""Deterministic persisted trust-decay scheduling without model calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.projection_history import (
    PreparedTrustProjectionPublication,
    ProjectionHistoryError,
    ProjectionHistoryRepository,
    TrustProjectionAdvanceRequest,
)
from memorii.core.memory_evolution.semantic_state import (
    ProjectionEvidenceRecord,
    SemanticClaimSlotKey,
    TrustProjectionRecord,
    TrustProjectionView,
    projection_contract_digest,
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
    PredicateTrustRule,
    TrustDecayStep,
    TrustPolicySnapshot,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

TrustDecayErrorCode = Literal[
    "trust_decay_policy_mismatch",
    "trust_decay_policy_invalid",
    "trust_decay_anchor_unavailable",
    "trust_decay_anchor_in_future",
    "trust_decay_command_stale",
    "trust_decay_integrity_error",
    "trust_decay_unauthorized",
]

_COMMAND_DOMAIN = b"memorii.trust-decay-command.v1\0"
_COMMAND_ID_DOMAIN = b"memorii.trust-decay-command-id.v1\0"
_THRESHOLD_BATCH_DOMAIN = b"memorii.trust-decay-threshold-batch.v1\0"


class ProjectionSchedulerError(ValueError):
    def __init__(self, code: TrustDecayErrorCode) -> None:
        super().__init__(code)
        self.code = code


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProjectionSchedulerError("trust_decay_policy_invalid")
    return value.astimezone(UTC)


def _digest(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(_digest(item) for item in value)
    if not isinstance(value, str):
        raise TypeError("trust decay digest must be a string")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("trust decay digest must be lowercase hexadecimal")
    return value


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


class TrustDecayAssertionEffect(BaseModel):
    assertion_id: str = Field(min_length=1)
    authority_class: str = Field(min_length=1)
    anchor_time: datetime
    base_rank: int
    authority_loss: int = Field(ge=0)
    effective_rank: int
    eligibility: Literal["eligible", "ineligible"]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @field_validator("anchor_time")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_effect(self) -> TrustDecayAssertionEffect:
        if self.effective_rank != self.base_rank - self.authority_loss:
            raise ValueError("trust decay effective rank is not base rank minus loss")
        return self


class TrustDecayCommand(BaseModel):
    repository_id: str = Field(min_length=1)
    claim_slot_key: SemanticClaimSlotKey
    assertion_ids: tuple[str, ...]
    threshold_assertion_ids: tuple[str, ...]
    trust_policy_fingerprint: str
    trust_policy_snapshot_digest: str
    arbitration_coordinate_before: datetime
    threshold_time: datetime
    threshold_effects: tuple[TrustDecayAssertionEffect, ...]
    writer_epoch: int = Field(ge=1)
    graph_revision: str = Field(min_length=1)
    complete_read_set_digest: str
    predecessor_generation_digest: str
    command_id: str
    command_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "trust_policy_fingerprint",
        "trust_policy_snapshot_digest",
        "complete_read_set_digest",
        "predecessor_generation_digest",
        "command_id",
        "command_digest",
    )(_digest)

    @field_validator("arbitration_coordinate_before", "threshold_time")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_command(self) -> TrustDecayCommand:
        if (
            self.assertion_ids != tuple(sorted(set(self.assertion_ids)))
            or not self.assertion_ids
            or self.threshold_assertion_ids
            != tuple(sorted(set(self.threshold_assertion_ids)))
            or not self.threshold_assertion_ids
            or not set(self.threshold_assertion_ids).issubset(self.assertion_ids)
            or tuple(item.assertion_id for item in self.threshold_effects)
            != self.assertion_ids
            or self.threshold_time <= self.arbitration_coordinate_before
        ):
            raise ValueError("trust decay command membership is invalid")
        body = self.model_dump(mode="python", exclude={"command_id", "command_digest"})
        command_id = sha256(
            _COMMAND_ID_DOMAIN + encode_typed_value(_canonical(body))
        ).hexdigest()
        if self.command_id != command_id:
            raise ValueError("trust decay command ID mismatch")
        digest_body = {**body, "command_id": command_id}
        if self.command_digest != sha256(
            _COMMAND_DOMAIN + encode_typed_value(_canonical(digest_body))
        ).hexdigest():
            raise ValueError("trust decay command digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> TrustDecayCommand:
        command_id = sha256(
            _COMMAND_ID_DOMAIN + encode_typed_value(_canonical(values))
        ).hexdigest()
        body = {**values, "command_id": command_id}
        return cls(
            **body,
            command_digest=sha256(
                _COMMAND_DOMAIN + encode_typed_value(_canonical(body))
            ).hexdigest(),
        )


@dataclass(frozen=True)
class PreparedTrustDecayPublication:
    publication_kind: Literal["trust_decay_schedule", "trust_decay_threshold"]
    operation_id: str
    policy_snapshot_digest: str
    command_digest: str
    executed_command_digests: tuple[str, ...]
    projection: PreparedTrustProjectionPublication
    command_records: tuple[CanonicalMemoryRecord, ...]
    command_preconditions: tuple[MemoryPlanePrecondition, ...]


class ProjectionScheduler:
    """Purely derives commands and one trust successor for the atomic store."""

    def __init__(
        self,
        memory_plane: MemoryPlaneService,
        projection_history: ProjectionHistoryRepository,
        *,
        repository_id: str,
        now_provider=lambda: datetime.now(UTC),
        publication_capability: object,
    ) -> None:
        self._memory_plane = memory_plane
        self._history = projection_history
        self._repository_id = repository_id
        self._now = now_provider
        self._capability = publication_capability
        self._repository_token = sha256(repository_id.encode()).hexdigest()

    def prepare_schedule(
        self,
        policy: TrustPolicySnapshot,
        *,
        writer_epoch: int,
        complete_read_set_digest: str,
        authorization: SemanticWriterWriteAuthorization,
    ) -> PreparedTrustDecayPublication | None:
        view = self._active_view(policy)
        pending = self._pending_commands(view)
        if pending:
            predecessors = {
                item.predecessor_generation_digest for item in pending
            }
            if (
                len(predecessors) != 1
                or view.generation.predecessor_generation_digest
                != next(iter(predecessors))
            ):
                raise ProjectionSchedulerError("trust_decay_command_stale")
            expected = self._derive_commands(
                view,
                policy,
                writer_epoch=writer_epoch,
                complete_read_set_digest=complete_read_set_digest,
                predecessor_generation_digest=next(iter(predecessors)),
            )
            if pending != expected:
                raise ProjectionSchedulerError("trust_decay_command_stale")
            return None
        expected = self._derive_commands(
            view,
            policy,
            writer_epoch=writer_epoch,
            complete_read_set_digest=complete_read_set_digest,
        )
        if not expected:
            return None
        operation_digest = projection_contract_digest(
            "trust_decay_schedule",
            {
                "repository_id": self._repository_id,
                "policy_snapshot_digest": policy.snapshot_digest,
                "predecessor_generation_digest": view.generation.generation_digest,
                "command_digests": tuple(item.command_digest for item in expected),
                "complete_read_set_digest": complete_read_set_digest,
                "writer_epoch": writer_epoch,
            },
        )
        return self._prepare_publication(
            publication_kind="trust_decay_schedule",
            operation_id=f"trust-decay-schedule:{operation_digest}",
            command_digest=operation_digest,
            executed_command_digests=(),
            view=view,
            policy=policy,
            projections=view.projections,
            commands=expected,
            arbitration_as_of=view.generation.arbitration_as_of,
            writer_epoch=writer_epoch,
            complete_read_set_digest=complete_read_set_digest,
            authorization=authorization,
        )

    def prepare_next_due(
        self,
        policy: TrustPolicySnapshot,
        *,
        writer_epoch: int,
        complete_read_set_digest: str,
        authorization: SemanticWriterWriteAuthorization,
    ) -> PreparedTrustDecayPublication | None:
        view = self._active_view(policy)
        pending = self._pending_commands(view)
        if not pending:
            return None
        now = _utc(self._now())
        command = min(pending, key=lambda item: (item.threshold_time, item.command_id))
        if command.threshold_time > now:
            return None
        due_batch = tuple(
            item for item in pending if item.threshold_time == command.threshold_time
        )
        for due in due_batch:
            self._validate_command_against_view(
                due,
                view,
                policy,
                writer_epoch=writer_epoch,
                complete_read_set_digest=complete_read_set_digest,
            )
        executed_command_digests = tuple(
            item.command_digest for item in due_batch
        )
        threshold_operation_digest = (
            command.command_digest
            if len(due_batch) == 1
            else sha256(
                _THRESHOLD_BATCH_DOMAIN
                + encode_typed_value(
                    _canonical(
                        {
                    "repository_id": self._repository_id,
                    "threshold_time": command.threshold_time,
                    "command_digests": executed_command_digests,
                    "predecessor_generation_digest": (
                        view.generation.generation_digest
                    ),
                    "writer_epoch": writer_epoch,
                    "complete_read_set_digest": complete_read_set_digest,
                        }
                    )
                )
            ).hexdigest()
        )
        projections = self._project_at(view, policy, command.threshold_time)
        successor_view = view.model_copy(
            update={
                "projections": projections,
                "generation": view.generation.model_copy(
                    update={"arbitration_as_of": command.threshold_time}
                ),
            }
        )
        commands = self._derive_commands(
            successor_view,
            policy,
            writer_epoch=writer_epoch,
            complete_read_set_digest=complete_read_set_digest,
            predecessor_generation_digest=view.generation.generation_digest,
        )
        return self._prepare_publication(
            publication_kind="trust_decay_threshold",
            operation_id=f"trust-decay-threshold:{threshold_operation_digest}",
            command_digest=threshold_operation_digest,
            executed_command_digests=executed_command_digests,
            view=view,
            policy=policy,
            projections=projections,
            commands=commands,
            arbitration_as_of=command.threshold_time,
            writer_epoch=writer_epoch,
            complete_read_set_digest=complete_read_set_digest,
            authorization=authorization,
        )

    def pending_commands(self, policy: TrustPolicySnapshot) -> tuple[TrustDecayCommand, ...]:
        return self._pending_commands(self._active_view(policy))

    def command_digests_for_slot(
        self,
        view: TrustProjectionView,
        claim_slot_key: SemanticClaimSlotKey,
    ) -> tuple[str, ...]:
        """Return exact persisted command membership for one claim slot."""

        return tuple(
            sorted(
                command.command_digest
                for command in self._load_commands()
                if command.command_digest
                in view.generation.canonical_decay_command_digests
                and command.claim_slot_key == claim_slot_key
            )
        )

    def command_digests_for_slot_membership(
        self,
        command_digests: tuple[str, ...],
        claim_slot_key: SemanticClaimSlotKey,
    ) -> tuple[str, ...]:
        """Partition one proposed generation's persisted commands by slot."""

        requested = set(command_digests)
        commands = {
            command.command_digest: command for command in self._load_commands()
        }
        if not requested.issubset(commands):
            raise ProjectionSchedulerError("trust_decay_integrity_error")
        return tuple(
            sorted(
                digest
                for digest in requested
                if commands[digest].claim_slot_key == claim_slot_key
            )
        )

    def project_for_migration(
        self,
        view: TrustProjectionView,
        policy: TrustPolicySnapshot,
        arbitration_as_of: datetime,
    ) -> tuple[TrustProjectionRecord, ...]:
        """Run the same provider-free trust algebra for a pending policy."""

        return self._project_at(view, policy, _utc(arbitration_as_of))

    def commands_for_migration(
        self,
        view: TrustProjectionView,
        projections: tuple[TrustProjectionRecord, ...],
        policy: TrustPolicySnapshot,
        *,
        arbitration_as_of: datetime,
        writer_epoch: int,
        complete_read_set_digest: str,
    ) -> tuple[TrustDecayCommand, ...]:
        """Derive target-policy commands from retained evidence for cutover."""

        at = _utc(arbitration_as_of)
        target_view = view.model_copy(
            update={
                "generation": view.generation.model_copy(
                    update={"arbitration_as_of": at}
                ),
                "projections": projections,
            }
        )
        return self._derive_commands(
            target_view,
            policy,
            writer_epoch=writer_epoch,
            complete_read_set_digest=complete_read_set_digest,
            predecessor_generation_digest=view.generation.generation_digest,
        )

    def _active_view(self, policy: TrustPolicySnapshot) -> TrustProjectionView:
        try:
            view = self._history.active_trust_authority()
        except ProjectionHistoryError as exc:
            raise ProjectionSchedulerError("trust_decay_integrity_error") from exc
        if (
            view.pointer.policy_fingerprint != policy.fingerprint
            or view.generation.trust_policy_fingerprint != policy.fingerprint
        ):
            raise ProjectionSchedulerError("trust_decay_policy_mismatch")
        return view

    def _derive_commands(
        self,
        view: TrustProjectionView,
        policy: TrustPolicySnapshot,
        *,
        writer_epoch: int,
        complete_read_set_digest: str,
        predecessor_generation_digest: str | None = None,
    ) -> tuple[TrustDecayCommand, ...]:
        predecessor = predecessor_generation_digest or view.generation.generation_digest
        commands: list[TrustDecayCommand] = []
        for projection in view.projections:
            if projection.claim_slot_key is None:
                continue
            rule = self._rule(policy, projection.claim_slot_key.predicate_id)
            evidence = projection.evidence
            assertion_ids = tuple(item.candidate_id for item in evidence)
            thresholds: dict[datetime, set[str]] = {}
            for item in evidence:
                authority_class = self._authority_class(item, rule)
                anchor = self._anchor(item, rule, view.generation.arbitration_as_of)
                for step in rule.decay_schedule_by_class.get(authority_class, ()):
                    threshold = anchor + step.minimum_age
                    if threshold > view.generation.arbitration_as_of:
                        thresholds.setdefault(threshold, set()).add(item.candidate_id)
            for threshold in sorted(thresholds):
                effects = tuple(
                    self._effect(item, rule, threshold)
                    for item in evidence
                )
                commands.append(
                    TrustDecayCommand.create(
                        repository_id=self._repository_id,
                        claim_slot_key=projection.claim_slot_key,
                        assertion_ids=assertion_ids,
                        threshold_assertion_ids=tuple(sorted(thresholds[threshold])),
                        trust_policy_fingerprint=policy.fingerprint,
                        trust_policy_snapshot_digest=policy.snapshot_digest,
                        arbitration_coordinate_before=view.generation.arbitration_as_of,
                        threshold_time=threshold,
                        threshold_effects=effects,
                        writer_epoch=writer_epoch,
                        graph_revision=view.generation.base_graph_revision,
                        complete_read_set_digest=complete_read_set_digest,
                        predecessor_generation_digest=predecessor,
                    )
                )
        return tuple(sorted(commands, key=lambda item: (item.threshold_time, item.command_id)))

    def _validate_command_against_view(
        self,
        command: TrustDecayCommand,
        view: TrustProjectionView,
        policy: TrustPolicySnapshot,
        *,
        writer_epoch: int,
        complete_read_set_digest: str,
    ) -> None:
        expected = self._derive_commands(
            view,
            policy,
            writer_epoch=writer_epoch,
            complete_read_set_digest=complete_read_set_digest,
            predecessor_generation_digest=command.predecessor_generation_digest,
        )
        if (
            view.generation.predecessor_generation_digest
            != command.predecessor_generation_digest
            or command not in expected
        ):
            raise ProjectionSchedulerError("trust_decay_command_stale")

    def _project_at(
        self,
        view: TrustProjectionView,
        policy: TrustPolicySnapshot,
        at: datetime,
    ) -> tuple[TrustProjectionRecord, ...]:
        projections = tuple(self._project_one(item, policy, at) for item in view.projections)
        return tuple(sorted(projections, key=lambda item: item.projection_digest))

    def _project_one(
        self,
        projection: TrustProjectionRecord,
        policy: TrustPolicySnapshot,
        at: datetime,
    ) -> TrustProjectionRecord:
        if projection.claim_slot_key is None:
            return projection
        rule = self._rule(policy, projection.claim_slot_key.predicate_id)
        ranked: list[tuple[ProjectionEvidenceRecord, TrustDecayAssertionEffect]] = []
        for item in projection.evidence:
            ranked.append((item, self._effect(item, rule, at)))
        eligible = tuple(item for item in ranked if item[1].eligibility == "eligible")
        selected: set[str] = set()
        contested: set[str] = set()
        if eligible:
            nondominated: list[tuple[ProjectionEvidenceRecord, TrustDecayAssertionEffect]] = []
            for item, effect in eligible:
                dominated = False
                for other, other_effect in eligible:
                    if other.candidate_id == item.candidate_id:
                        continue
                    if self._same_value(item, other):
                        continue
                    pair = tuple(sorted((effect.authority_class, other_effect.authority_class)))
                    if pair in rule.incomparable_class_pairs:
                        continue
                    if other_effect.effective_rank > effect.effective_rank:
                        dominated = True
                        break
                if not dominated:
                    nondominated.append((item, effect))
            values = {
                encode_typed_value(item.assertion_key.value.model_dump(mode="python")).hex()
                for item, _ in nondominated
                if item.assertion_key is not None
            }
            ids = {item.candidate_id for item, _ in nondominated}
            if len(values) <= 1:
                selected = ids
            else:
                contested = ids
        retained = {
            item.candidate_id for item, _ in ranked
        } - selected - contested
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
            for item, _ in ranked
        )
        outcome: Literal["pass", "unknown", "contested"] = (
            "contested" if contested else "pass" if selected else "unknown"
        )
        return TrustProjectionRecord.create(
            **projection.model_dump(
                mode="python",
                exclude={
                    "projection_id",
                    "projection_digest",
                    "trust_policy_fingerprint",
                    "arbitration_as_of",
                    "system_valid_from",
                    "outcome",
                    "evidence",
                    "selected_assertion_ids",
                    "contested_assertion_ids",
                    "retained_assertion_ids",
                },
            ),
            projection_id=projection_contract_digest(
                "trust_decay_projection_id",
                {
                    "predecessor_projection_digest": projection.projection_digest,
                    "arbitration_as_of": at,
                    "policy_fingerprint": policy.fingerprint,
                },
            ),
            trust_policy_fingerprint=policy.fingerprint,
            arbitration_as_of=at,
            system_valid_from=at,
            outcome=outcome,
            evidence=evidence,
            selected_assertion_ids=tuple(sorted(selected)),
            contested_assertion_ids=tuple(sorted(contested)),
            retained_assertion_ids=tuple(sorted(retained)),
        )

    @staticmethod
    def _same_value(left: ProjectionEvidenceRecord, right: ProjectionEvidenceRecord) -> bool:
        return (
            left.assertion_key is not None
            and right.assertion_key is not None
            and left.assertion_key.value == right.assertion_key.value
        )

    def _effect(
        self,
        item: ProjectionEvidenceRecord,
        rule: PredicateTrustRule,
        at: datetime,
    ) -> TrustDecayAssertionEffect:
        authority_class = self._authority_class(item, rule)
        anchor = self._anchor(item, rule, at)
        age = at - anchor
        step: TrustDecayStep | None = None
        for candidate in rule.decay_schedule_by_class.get(authority_class, ()):
            if candidate.minimum_age <= age:
                step = candidate
            else:
                break
        loss = step.authority_loss if step is not None else 0
        eligibility: Literal["eligible", "ineligible"] = (
            step.eligibility
            if step is not None
            else "eligible"
            if authority_class in rule.eligible_authority_classes
            else "ineligible"
        )
        base_rank = rule.authority_rank_by_class[authority_class]
        return TrustDecayAssertionEffect(
            assertion_id=item.candidate_id,
            authority_class=authority_class,
            anchor_time=anchor,
            base_rank=base_rank,
            authority_loss=loss,
            effective_rank=base_rank - loss,
            eligibility=eligibility,
        )

    @staticmethod
    def _authority_class(
        item: ProjectionEvidenceRecord,
        rule: PredicateTrustRule,
    ) -> str:
        authority_class = item.source_authority_class
        if authority_class is None or authority_class not in rule.authority_rank_by_class:
            raise ProjectionSchedulerError("trust_decay_policy_invalid")
        return authority_class

    @staticmethod
    def _anchor(
        item: ProjectionEvidenceRecord,
        rule: PredicateTrustRule,
        at: datetime,
    ) -> datetime:
        anchor = (
            item.system_valid_from
            if rule.decay_age_basis == "assertion_system_start"
            else item.valid_interval.start
            if item.valid_interval is not None
            else None
        )
        if anchor is None:
            raise ProjectionSchedulerError("trust_decay_anchor_unavailable")
        anchor = _utc(anchor)
        if anchor > at:
            raise ProjectionSchedulerError("trust_decay_anchor_in_future")
        return anchor

    @staticmethod
    def _rule(policy: TrustPolicySnapshot, predicate_id: str) -> PredicateTrustRule:
        try:
            return policy.rule_for(predicate_id)
        except ValueError as exc:
            raise ProjectionSchedulerError("trust_decay_policy_invalid") from exc

    def _prepare_publication(
        self,
        *,
        publication_kind: Literal["trust_decay_schedule", "trust_decay_threshold"],
        operation_id: str,
        command_digest: str,
        executed_command_digests: tuple[str, ...],
        view: TrustProjectionView,
        policy: TrustPolicySnapshot,
        projections: tuple[TrustProjectionRecord, ...],
        commands: tuple[TrustDecayCommand, ...],
        arbitration_as_of: datetime,
        writer_epoch: int,
        complete_read_set_digest: str,
        authorization: SemanticWriterWriteAuthorization,
    ) -> PreparedTrustDecayPublication:
        projection = self._history.prepare_trust(
            TrustProjectionAdvanceRequest(
                repository_id=self._repository_id,
                operation_id=operation_id,
                graph_revision=view.generation.base_graph_revision,
                event_batch_sequence=0,
                event_batch_digest=command_digest,
                complete_read_set_digest=complete_read_set_digest,
                writer_epoch=writer_epoch,
                base_snapshot_token=view.generation.generation_digest,
                trust_policy_fingerprint=policy.fingerprint,
                arbitration_as_of=arbitration_as_of,
                trust_projections=projections,
                semantic_conflict_authority=(
                    self._history.resolve_semantic_conflict_authority(
                        trust_projections=projections,
                    )
                ),
                trust_decay_command_digests=tuple(
                    sorted(item.command_digest for item in commands)
                ),
            ),
            capability=self._capability,
            authorization=authorization,
        )
        records, preconditions = self.prepare_command_records(commands)
        return PreparedTrustDecayPublication(
            publication_kind=publication_kind,
            operation_id=operation_id,
            policy_snapshot_digest=policy.snapshot_digest,
            command_digest=command_digest,
            executed_command_digests=executed_command_digests,
            projection=projection,
            command_records=records,
            command_preconditions=preconditions,
        )

    def prepare_command_records(
        self,
        commands: tuple[TrustDecayCommand, ...],
    ) -> tuple[tuple[CanonicalMemoryRecord, ...], tuple[MemoryPlanePrecondition, ...]]:
        """Prepare one deduplicated, fail-closed decay-command persistence set."""

        by_digest = {command.command_digest: command for command in commands}
        if len(by_digest) != len(commands):
            raise ProjectionSchedulerError("trust_decay_integrity_error")
        records: list[CanonicalMemoryRecord] = []
        preconditions: list[MemoryPlanePrecondition] = []
        for digest in sorted(by_digest):
            record = self._command_record(by_digest[digest])
            current = self._memory_plane.get_record(record.memory_id)
            if current is None:
                records.append(record)
                preconditions.append(RecordAbsentPrecondition(memory_id=record.memory_id))
            elif current.content != record.content or current.source_kind != record.source_kind:
                raise ProjectionSchedulerError("trust_decay_integrity_error")
            else:
                preconditions.append(
                    RecordDigestPrecondition(
                        memory_id=current.memory_id,
                        expected_digest=record_digest(current),
                    )
                )
        return tuple(records), tuple(preconditions)

    def _pending_commands(self, view: TrustProjectionView) -> tuple[TrustDecayCommand, ...]:
        commands = {item.command_digest: item for item in self._load_commands()}
        pending: list[TrustDecayCommand] = []
        for digest in view.generation.canonical_decay_command_digests:
            command = commands.get(digest)
            if command is None:
                raise ProjectionSchedulerError("trust_decay_integrity_error")
            pending.append(command)
        return tuple(sorted(pending, key=lambda item: (item.threshold_time, item.command_id)))

    def _load_commands(self) -> tuple[TrustDecayCommand, ...]:
        values: list[TrustDecayCommand] = []
        for record in self._memory_plane.list_records(
            source_kind="semantic_projection_trust_decay_command"
        ):
            if not record.memory_id.startswith(self._command_prefix()):
                raise ProjectionSchedulerError("trust_decay_integrity_error")
            try:
                raw = bytes.fromhex(str(record.content["canonical_hex"]))
                value = TrustDecayCommand.model_validate(decode_typed_value(raw))
            except (CanonicalTypedValueError, KeyError, TypeError, ValueError) as exc:
                raise ProjectionSchedulerError("trust_decay_integrity_error") from exc
            if (
                set(record.content)
                != {"projection_authority_kind", "canonical_hex", "authority_digest"}
                or record.content["projection_authority_kind"] != "decay_command"
                or record.content["authority_digest"] != sha256(raw).hexdigest()
                or record.memory_id != f"{self._command_prefix()}{value.command_digest}"
                or value.repository_id != self._repository_id
            ):
                raise ProjectionSchedulerError("trust_decay_integrity_error")
            values.append(value)
        if len({item.command_digest for item in values}) != len(values):
            raise ProjectionSchedulerError("trust_decay_integrity_error")
        return tuple(values)

    def _command_prefix(self) -> str:
        return f"semantic_projection:{self._repository_token}:trust:decay_command:"

    def _command_record(self, command: TrustDecayCommand) -> CanonicalMemoryRecord:
        raw = encode_typed_value(command.model_dump(mode="python"))
        return CanonicalMemoryRecord(
            memory_id=f"{self._command_prefix()}{command.command_digest}",
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "projection_authority_kind": "decay_command",
                "canonical_hex": raw.hex(),
                "authority_digest": sha256(raw).hexdigest(),
            },
            status=CommitStatus.COMMITTED,
            source_kind="semantic_projection_trust_decay_command",
            timestamp=_utc(self._now()),
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
