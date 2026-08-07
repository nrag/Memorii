"""Store-owned Section 3.13 writer admission for the bounded writer-safe preplanning slice."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from memorii.core.memory_evolution.delivery_coordinate_migration import (
    DeliveryCoordinateMigrationActivation,
    DeliveryCoordinateMigrationCertificate,
    DeliveryCoordinateMigrationCheckpoint,
    DeliveryCoordinateMigrationPlan,
    DeliveryCoordinateMigrationTargetProjection,
    activate_migration,
    certify_migration,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
    SemanticRecordOwnershipManifest,
    SemanticWriterAdmission,
    SemanticWriterCommitBinding,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.semantic_control import (
    SEMANTIC_PROJECTION_SOURCE_KINDS,
    is_semantic_control_record,
    semantic_control_class,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlanePrecondition,
    MemoryPlaneRevisionConflictError,
    MemoryPlaneWriteAuthorization,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_SEMANTIC_PROJECTION_SOURCE_KINDS = SEMANTIC_PROJECTION_SOURCE_KINDS

_KINDS = (
    frozenset(
        {
            "admitted_source",
            "admission_index",
            "profile_selection",
            "profile_verification",
            "profile_outcome",
            "legacy_delivery_record",
            "preplanning_operation_control",
            "preplanning_introduction",
            "preplanning_artifact_index",
            "preplanning_artifact_closure",
            "operation_control",
            "generation_member",
            "generation_manifest",
            "migration_plan",
            "migration_checkpoint",
            "migration_certificate",
            "authorization_authority",
            "semantic_event_batch",
            "semantic_replay_state",
            "reference_integrity_ledger",
            "accepted_identity_operation",
            "graph_identity_reservation",
        }
    )
    | _SEMANTIC_PROJECTION_SOURCE_KINDS
)
_METHODS = frozenset(
    {
        "admit_source",
        "checkpoint_source_progress",
        "persist_terminal_group",
        "finalize_source",
        "conditionally_write_records",
        "apply_batch",
        "stage_record",
        "upsert_record",
        "write_records",
        "unit_of_work.commit",
    }
)


class SemanticWriterAdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class SemanticWriterWriteAuthorization(MemoryPlaneWriteAuthorization):
    admission: SemanticWriterAdmission
    manifest: SemanticRecordOwnershipManifest
    owner: object | None
    lease_expires_at: datetime | None = None
    server_now: Callable[[], datetime] | None = None


@dataclass(frozen=True)
class SemanticConflictAuthorityAdministrationAuthorization(
    MemoryPlaneWriteAuthorization
):
    owner: object


@dataclass(frozen=True)
class SemanticConflictAuthorityAdministrationGrant:
    _issuer: object
    _owner: object


def bounded_preplanning_ownership_manifest() -> SemanticRecordOwnershipManifest:
    """Return the complete writer-safe preplanning governed-write inventory (legacy name retained)."""
    revision = "semantic-generation-v2"
    return SemanticRecordOwnershipManifest(
        manifest_revision=revision,
        governed_record_kinds=_KINDS,
        semantic_store_methods=_METHODS,
        manifest_digest=sha256(
            encode_typed_value(
                {"manifest_revision": revision, "governed_record_kinds": _KINDS, "semantic_store_methods": _METHODS}
            )
        ).hexdigest(),
    )


def writer_admission_memory_id() -> str:
    return "semantic_ingestion:writer_admission:current"


class SemanticWriterAdmissionStore:
    def __init__(
        self,
        memory_plane: MemoryPlaneService,
        manifest: SemanticRecordOwnershipManifest,
        *,
        now_provider=lambda: datetime.now(UTC),
    ) -> None:
        if manifest != bounded_preplanning_ownership_manifest():
            raise SemanticWriterAdmissionError("unsupported semantic ownership manifest")
        self._memory_plane, self._manifest, self._now = memory_plane, manifest, now_provider
        self._atomic_owners: set[object] = set()
        self._conflict_authority_administration_owner: object | None = None
        self._conflict_authority_administration_grant: (
            SemanticConflictAuthorityAdministrationGrant | None
        ) = None
        self._transition_owner = object()
        self._memory_plane.install_governed_write_policy(SemanticGovernedWritePolicy(self))

    def governed_write_policy(self) -> SemanticGovernedWritePolicy:
        return SemanticGovernedWritePolicy(self)

    def _claim_conflict_authority_administration(
        self, *, owner: object
    ) -> SemanticConflictAuthorityAdministrationGrant:
        if self._conflict_authority_administration_owner is None:
            self._conflict_authority_administration_owner = owner
            self._conflict_authority_administration_grant = (
                SemanticConflictAuthorityAdministrationGrant(
                    _issuer=self, _owner=owner
                )
            )
        elif self._conflict_authority_administration_owner is not owner:
            raise SemanticWriterAdmissionError(
                "conflict authority administration is already owned"
            )
        assert self._conflict_authority_administration_grant is not None
        return self._conflict_authority_administration_grant

    def create_initial_evidence_only(
        self, *, admission_id: str, writer_implementation_fingerprint: str, graph_schema_fingerprint: str
    ) -> SemanticWriterAdmission:
        existing = self._memory_plane.get_record(writer_admission_memory_id())
        if existing is not None:
            current, manifest = _from_record(existing)
            if not _matches_initial_evidence_only(
                current,
                manifest,
                expected_manifest=self._manifest,
                admission_id=admission_id,
                writer_implementation_fingerprint=writer_implementation_fingerprint,
                graph_schema_fingerprint=graph_schema_fingerprint,
            ):
                raise SemanticWriterAdmissionError("writer admission is already bound differently")
            return current
        at = self._now()
        admission = SemanticWriterAdmission(
            admission_id=admission_id,
            writer_namespace="semantic_ingestion",
            active_runtime_mode="evidence_only",
            active_writer_implementation_fingerprint=writer_implementation_fingerprint,
            accepted_graph_schema_fingerprint=graph_schema_fingerprint,
            writer_epoch=1,
            activated_at=at,
            previous_admission_digest=None,
            admission_digest=_admission_digest(
                admission_id, "evidence_only", writer_implementation_fingerprint, graph_schema_fingerprint, 1, at, None
            ),
        )
        record = _record(admission, self._manifest, at)
        authorization = SemanticWriterWriteAuthorization(
            admission=admission,
            manifest=self._manifest,
            owner=None,
        )
        try:
            self._memory_plane.conditionally_write_records(
                (record,),
                preconditions=(RecordAbsentPrecondition(memory_id=record.memory_id),),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._memory_plane.get_record(record.memory_id)
            if existing is None:
                raise
            current, manifest = _from_record(existing)
            if not _matches_initial_evidence_only(
                current,
                manifest,
                expected_manifest=self._manifest,
                admission_id=admission_id,
                writer_implementation_fingerprint=writer_implementation_fingerprint,
                graph_schema_fingerprint=graph_schema_fingerprint,
            ):
                raise SemanticWriterAdmissionError("writer admission is already bound differently") from exc
            return current
        return admission

    def commit_binding(self, admission: SemanticWriterAdmission) -> SemanticWriterCommitBinding:
        return SemanticWriterCommitBinding(
            admission_id=admission.admission_id,
            admission_digest=admission.admission_digest,
            writer_namespace=admission.writer_namespace,
            expected_writer_epoch=admission.writer_epoch,
            runtime_mode=admission.active_runtime_mode,
            writer_implementation_fingerprint=admission.active_writer_implementation_fingerprint,
            graph_schema_fingerprint=admission.accepted_graph_schema_fingerprint,
        )

    def require_current(self, binding: SemanticWriterCommitBinding) -> CanonicalMemoryRecord:
        record = self._memory_plane.get_record(writer_admission_memory_id())
        if record is None:
            raise SemanticWriterAdmissionError("semantic writer is unbound")
        admission, manifest = _from_record(record)
        expected = self.commit_binding(admission)
        if manifest != self._manifest or binding != expected:
            raise SemanticWriterAdmissionError("semantic writer binding is stale or mismatched")
        return record

    def current(self) -> SemanticWriterAdmission:
        record = self._memory_plane.get_record(writer_admission_memory_id())
        if record is None:
            raise SemanticWriterAdmissionError("semantic writer is unbound")
        admission, manifest = _from_record(record)
        if manifest != self._manifest:
            raise SemanticWriterAdmissionError("semantic writer manifest is mismatched")
        return admission

    def transition(
        self,
        *,
        expected: SemanticWriterCommitBinding,
        admission_id: str,
        runtime_mode: Literal["verified_semantic", "evidence_only", "legacy_pre_cutover"],
        writer_implementation_fingerprint: str,
        graph_schema_fingerprint: str,
        migration_activation: DeliveryCoordinateMigrationActivation,
        migration_plan: DeliveryCoordinateMigrationPlan,
        migration_certificate: DeliveryCoordinateMigrationCertificate,
        migration_checkpoint: DeliveryCoordinateMigrationCheckpoint,
        target_records: tuple[CanonicalMemoryRecord, ...],
    ) -> SemanticWriterAdmission:
        """Advance writer authority by one epoch after certified drain/activation."""
        if runtime_mode not in {"verified_semantic", "evidence_only"}:
            raise SemanticWriterAdmissionError("legacy writer authority cannot be reissued")
        verified_certificate = certify_migration(
            migration_plan,
            migration_checkpoint,
            independent_verifier_fingerprint=migration_certificate.independent_verifier_fingerprint,
        )
        if verified_certificate != migration_certificate:
            raise SemanticWriterAdmissionError("migration certificate does not verify persisted checkpoint")
        verified_activation = activate_migration(migration_plan, migration_certificate)
        if verified_activation != migration_activation:
            raise SemanticWriterAdmissionError("migration activation is not certified by the supplied plan")
        if (
            migration_activation.source_writer_epoch != expected.expected_writer_epoch
            or migration_activation.target_writer_epoch != expected.expected_writer_epoch + 1
        ):
            raise SemanticWriterAdmissionError("certified migration activation targets another epoch")
        expected_target_digests = sorted(
            digest for entry in migration_plan.entries for digest in entry.migrated_state_digests
        )
        actual_target_digests = sorted(record_digest(record) for record in target_records)
        if expected_target_digests != actual_target_digests or any(
            not record.memory_id.startswith("semantic_ingestion:migrated:")
            or record.source_kind != "semantic_ingestion_migrated_target"
            for record in target_records
        ):
            raise SemanticWriterAdmissionError("migration target generation is incomplete")
        if len({record.memory_id for record in target_records}) != len(target_records):
            raise SemanticWriterAdmissionError("migration target identities collide")
        records_by_digest = {record_digest(record): record for record in target_records}
        expected_projections = []
        target_coordinate_keys: set[tuple[str, int]] = set()
        for entry in migration_plan.entries:
            coordinate_key = (entry.target_delivery_key_digest, migration_certificate.target_generation)
            if coordinate_key in target_coordinate_keys:
                raise SemanticWriterAdmissionError("migration target coordinate collision")
            target_coordinate_keys.add(coordinate_key)
            for target_digest in entry.migrated_state_digests:
                target = records_by_digest.get(target_digest)
                if (
                    target is None
                    or target.content.get("target_delivery_key_digest") != entry.target_delivery_key_digest
                    or target.content.get("target_generation") != migration_certificate.target_generation
                ):
                    raise SemanticWriterAdmissionError("migration target coordinate projection is mismatched")
                values = {
                    "entry_digest": entry.entry_digest,
                    "target_delivery_key_digest": entry.target_delivery_key_digest,
                    "target_generation": migration_certificate.target_generation,
                    "target_record_id": target.memory_id,
                    "target_record_digest": target_digest,
                }
                expected_projections.append(
                    DeliveryCoordinateMigrationTargetProjection(
                        **values, projection_digest=sha256(encode_typed_value(values)).hexdigest()
                    )
                )
        target_projections = tuple(expected_projections)
        legacy_records = sorted(
            (
                record
                for record in self._memory_plane.list_records()
                if record.source_kind == "semantic_ingestion_legacy_delivery_record"
                and record.content.get("source_writer_epoch") == expected.expected_writer_epoch
            ),
            key=lambda record: record.memory_id,
        )
        inventory = tuple((record.memory_id, record_digest(record)) for record in legacy_records)
        planned_inventory = tuple(
            sorted((entry.legacy_record_id, entry.legacy_evidence_digest) for entry in migration_plan.entries)
        )
        if (
            inventory != planned_inventory
            or migration_plan.legacy_snapshot_token != sha256(encode_typed_value(inventory)).hexdigest()
        ):
            raise SemanticWriterAdmissionError("migration plan does not match the complete persisted legacy snapshot")
        current_record = self._memory_plane.get_record(writer_admission_memory_id())
        if current_record is None:
            raise SemanticWriterAdmissionError("semantic writer is unbound")
        current, manifest = _from_record(current_record)
        if manifest != self._manifest:
            raise SemanticWriterAdmissionError("semantic writer manifest is mismatched")
        if self.commit_binding(current) != expected:
            if not _matches_completed_transition(
                current,
                expected=expected,
                admission_id=admission_id,
                runtime_mode=runtime_mode,
                writer_implementation_fingerprint=writer_implementation_fingerprint,
                graph_schema_fingerprint=graph_schema_fingerprint,
                migration_activation=migration_activation,
                current_record=current_record,
            ):
                raise SemanticWriterAdmissionError("semantic writer binding is stale or mismatched")
            persisted = _migration_records(
                migration_plan,
                migration_checkpoint,
                migration_certificate,
                migration_activation,
                current.activated_at,
                target_projections,
            )
            if any(
                self._memory_plane.get_record(record.memory_id) != record for record in (*persisted, *target_records)
            ):
                raise SemanticWriterAdmissionError("completed migration generation is partial or mismatched")
            return current
        if not current_record.content.get("draining", False):
            self._memory_plane.conditionally_write_records(
                (_record(current, self._manifest, current_record.timestamp, draining=True),),
                preconditions=(
                    RecordDigestPrecondition(
                        memory_id=current_record.memory_id, expected_digest=record_digest(current_record)
                    ),
                ),
                authorization=SemanticWriterWriteAuthorization(
                    admission=current, manifest=self._manifest, owner=self._transition_owner
                ),
            )
            current_record = self.require_current(expected)
        for record in self._memory_plane.list_records():
            if record.source_kind != "semantic_ingestion_preplanning_control":
                continue
            try:
                control = record.content["control"]
                binding = SemanticWriterCommitBinding.model_validate(control["writer_binding"])
                state = control["state"]
                lease = control.get("lease")
            except (KeyError, TypeError, ValueError) as exc:
                raise SemanticWriterAdmissionError("retiring operation inventory is corrupt") from exc
            if binding.expected_writer_epoch == current.writer_epoch and (
                state not in {"terminal", "lease_recovery_exhausted"} or lease is not None
            ):
                raise SemanticWriterAdmissionError("retiring writer epoch is not drained")
        at = self._now()
        successor = SemanticWriterAdmission(
            admission_id=admission_id,
            writer_namespace="semantic_ingestion",
            active_runtime_mode=runtime_mode,
            active_writer_implementation_fingerprint=writer_implementation_fingerprint,
            accepted_graph_schema_fingerprint=graph_schema_fingerprint,
            writer_epoch=current.writer_epoch + 1,
            activated_at=at,
            previous_admission_digest=current.admission_digest,
            admission_digest=_admission_digest(
                admission_id,
                runtime_mode,
                writer_implementation_fingerprint,
                graph_schema_fingerprint,
                current.writer_epoch + 1,
                at,
                current.admission_digest,
            ),
        )
        authorization = SemanticWriterWriteAuthorization(
            admission=current, manifest=self._manifest, owner=self._transition_owner
        )
        migration_records = _migration_records(
            migration_plan, migration_checkpoint, migration_certificate, migration_activation, at, target_projections
        )
        self._memory_plane.conditionally_write_records(
            (
                _record(
                    successor, self._manifest, at, migration_activation_digest=migration_activation.activation_digest
                ),
                *migration_records,
                *target_records,
            ),
            preconditions=(
                RecordDigestPrecondition(
                    memory_id=current_record.memory_id, expected_digest=record_digest(current_record)
                ),
                *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in migration_records),
                *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in target_records),
            ),
            authorization=authorization,
        )
        return successor

    def advance_policy_epoch(
        self,
        *,
        expected: SemanticWriterCommitBinding,
        policy_activation_digest: str,
        records: tuple[CanonicalMemoryRecord, ...],
        preconditions: tuple[MemoryPlanePrecondition, ...],
    ) -> SemanticWriterAdmission:
        """Fence a policy cutover with the same CAS that advances writer epoch."""

        if (
            len(policy_activation_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in policy_activation_digest
            )
        ):
            raise SemanticWriterAdmissionError("policy activation digest is invalid")
        current_record = self._memory_plane.get_record(writer_admission_memory_id())
        if current_record is None:
            raise SemanticWriterAdmissionError("semantic writer is unbound")
        current, manifest = _from_record(current_record)
        if manifest != self._manifest or self.commit_binding(current) != expected:
            if (
                current.previous_admission_digest == expected.admission_digest
                and current.writer_epoch == expected.expected_writer_epoch + 1
                and current_record.content.get("policy_activation_digest")
                == policy_activation_digest
            ):
                return current
            raise SemanticWriterAdmissionError(
                "semantic writer binding is stale or mismatched"
            )
        at = self._now()
        successor = SemanticWriterAdmission(
            admission_id=current.admission_id,
            writer_namespace=current.writer_namespace,
            active_runtime_mode=current.active_runtime_mode,
            active_writer_implementation_fingerprint=(
                current.active_writer_implementation_fingerprint
            ),
            accepted_graph_schema_fingerprint=(
                current.accepted_graph_schema_fingerprint
            ),
            writer_epoch=current.writer_epoch + 1,
            activated_at=at,
            previous_admission_digest=current.admission_digest,
            admission_digest=_admission_digest(
                current.admission_id,
                current.active_runtime_mode,
                current.active_writer_implementation_fingerprint,
                current.accepted_graph_schema_fingerprint,
                current.writer_epoch + 1,
                at,
                current.admission_digest,
            ),
        )
        self._memory_plane.conditionally_write_records(
            (
                _record(
                    successor,
                    self._manifest,
                    at,
                    policy_activation_digest=policy_activation_digest,
                ),
                *records,
            ),
            preconditions=(
                RecordDigestPrecondition(
                    memory_id=current_record.memory_id,
                    expected_digest=record_digest(current_record),
                ),
                *preconditions,
            ),
            authorization=SemanticWriterWriteAuthorization(
                admission=current,
                manifest=self._manifest,
                owner=self._transition_owner,
            ),
        )
        return successor

    def _register_atomic_owner(self) -> object:
        capability = object()
        self._atomic_owners.add(capability)
        return capability

    def _authorize_atomic(
        self,
        binding: SemanticWriterCommitBinding,
        *,
        capability: object,
        lease_expires_at: datetime | None = None,
        server_now: Callable[[], datetime] | None = None,
    ) -> SemanticWriterWriteAuthorization:
        if capability not in self._atomic_owners:
            raise SemanticWriterAdmissionError("semantic atomic writer is not registered")
        record = self.require_current(binding)
        admission, manifest = _from_record(record)
        return SemanticWriterWriteAuthorization(
            admission=admission,
            manifest=manifest,
            owner=capability,
            lease_expires_at=lease_expires_at,
            server_now=server_now,
        )


class SemanticGovernedWritePolicy:
    """Feature policy supplied to memory_plane without a reverse import."""

    def __init__(self, admissions: SemanticWriterAdmissionStore) -> None:
        self._admissions = admissions

    def validate(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        current: tuple[CanonicalMemoryRecord, ...],
        authorization: MemoryPlaneWriteAuthorization | None,
    ) -> None:
        governed = [record for record in records if is_semantic_control_record(record)]
        if not governed:
            return
        conflict_authority_records = [
            record
            for record in governed
            if record.source_kind == "semantic_ingestion_conflict_authority"
        ]
        if isinstance(
            authorization,
            SemanticConflictAuthorityAdministrationAuthorization,
        ):
            if (
                authorization.owner
                is not self._admissions._conflict_authority_administration_grant
                or len(conflict_authority_records) != len(governed)
            ):
                raise SemanticWriterAdmissionError(
                    "conflict authority administration is not authorized"
                )
            _validate_conflict_authority_administration_write(
                tuple(conflict_authority_records), current
            )
            return
        if not isinstance(authorization, SemanticWriterWriteAuthorization):
            raise SemanticWriterAdmissionError("governed semantic write is not authorized")
        if authorization.manifest != self._admissions._manifest:
            raise SemanticWriterAdmissionError("governed semantic manifest is mismatched")
        if authorization.lease_expires_at is not None and (
            authorization.server_now is None or authorization.lease_expires_at <= authorization.server_now()
        ):
            raise SemanticWriterAdmissionError("semantic write lease expired before storage CAS")
        if conflict_authority_records:
            _validate_conflict_authority_atomic_closure(
                tuple(conflict_authority_records),
                records,
                current,
                (
                    authorization.server_now()
                    if authorization.server_now is not None
                    else self._admissions._now()
                ),
            )
            records = tuple(
                record for record in records if record not in conflict_authority_records
            )
            governed = [
                record for record in governed if record not in conflict_authority_records
            ]
            if not governed:
                return
        had_conflict_authority_records = bool(conflict_authority_records)
        current_record = next(
            (record for record in current if record.memory_id == writer_admission_memory_id()),
            None,
        )
        if current_record is None:
            if authorization.owner is not None:
                raise SemanticWriterAdmissionError("initial writer admission authorization is invalid")
            if len(governed) != 1 or governed[0].source_kind != "semantic_ingestion_writer_admission":
                raise SemanticWriterAdmissionError("initial writer admission is not an isolated write")
            proposed, manifest = _from_record(governed[0])
            if proposed != authorization.admission or manifest != authorization.manifest:
                raise SemanticWriterAdmissionError("initial writer admission authorization is mismatched")
            return
        current_admission, current_manifest = _from_record(current_record)
        if authorization.owner is self._admissions._transition_owner:
            writer_records = [record for record in governed if record.memory_id == writer_admission_memory_id()]
            if len(writer_records) != 1:
                raise SemanticWriterAdmissionError("writer transition lacks one authority record")
            proposed_record = writer_records[0]
            proposed, manifest = _from_record(proposed_record)
            if proposed == current_admission:
                if len(governed) != 1 or not proposed_record.content.get("draining", False):
                    raise SemanticWriterAdmissionError("writer drain freeze is invalid")
                return
            policy_records = tuple(record for record in records if record not in writer_records)
            policy_projection_records = [
                record
                for record in policy_records
                if record.source_kind.startswith("semantic_projection_")
                or record.memory_id.startswith("semantic_projection:")
            ]
            policy_activation_digest = proposed_record.content.get(
                "policy_activation_digest"
            )
            if policy_activation_digest is not None:
                if (
                    not isinstance(policy_activation_digest, str)
                    or manifest != current_manifest
                    or proposed.admission_id != current_admission.admission_id
                    or proposed.writer_epoch != current_admission.writer_epoch + 1
                    or proposed.previous_admission_digest
                    != current_admission.admission_digest
                    or proposed.active_runtime_mode
                    != current_admission.active_runtime_mode
                    or proposed.active_writer_implementation_fingerprint
                    != current_admission.active_writer_implementation_fingerprint
                    or proposed.accepted_graph_schema_fingerprint
                    != current_admission.accepted_graph_schema_fingerprint
                    or not _is_atomic_projection_publication_write(
                        policy_records,
                        policy_projection_records,
                    )
                    or not any(
                        record.source_kind
                        == "semantic_ingestion_projection_publication"
                        and record.content.get("authority_coordinate_digest")
                        == policy_activation_digest
                        and record.content.get("writer_epoch")
                        == proposed.writer_epoch
                        for record in policy_records
                    )
                ):
                    raise SemanticWriterAdmissionError(
                        "policy writer transition is invalid"
                    )
                return
            migration_records = [
                record for record in governed if record.source_kind.startswith("semantic_ingestion_migration")
            ]
            if (
                len(migration_records) < 4
                or manifest != current_manifest
                or proposed.writer_epoch != current_admission.writer_epoch + 1
                or proposed.previous_admission_digest != current_admission.admission_digest
                or proposed.active_runtime_mode == "legacy_pre_cutover"
                or not proposed_record.content.get("migration_activation_digest")
            ):
                raise SemanticWriterAdmissionError("writer transition is invalid")
            return
        if authorization.owner not in self._admissions._atomic_owners:
            raise SemanticWriterAdmissionError("governed semantic writer is not the atomic owner")
        if authorization.admission != current_admission or authorization.manifest != current_manifest:
            raise SemanticWriterAdmissionError("governed semantic authorization is stale")
        if any(record.source_kind == "semantic_ingestion_writer_admission" for record in governed):
            raise SemanticWriterAdmissionError("writer admission transition lacks transition authority")
        if any(semantic_control_class(record) == "unknown" for record in governed):
            raise SemanticWriterAdmissionError("unknown semantic control namespace is forbidden")
        projection_records = [
            record
            for record in governed
            if record.source_kind.startswith("semantic_projection_")
            or record.memory_id.startswith("semantic_projection:")
        ]
        _validate_projection_namespace_records(projection_records)
        if all(record.source_kind == "semantic_ingestion_authorization_authority" for record in governed):
            if len(governed) != 1:
                raise SemanticWriterAdmissionError("authorization authority transition is not isolated")
            return
        controls = [
            record
            for record in governed
            if record.content.get("semantic_ingestion_kind") == "preplanning_operation_control"
        ]
        if len(controls) != 1:
            # A clarification pointer closure is independently validated
            # above. Its replay aggregate is the only additional governed
            # member and must travel in that same write; it is not a free
            # standing replay-authority mutation.
            if (
                had_conflict_authority_records
                and frozenset(record.source_kind for record in governed)
                in {
                    frozenset({"semantic_ingestion_replay_authority"}),
                    frozenset({
                        "semantic_ingestion_conflict_clarification_transaction",
                        "semantic_ingestion_conflict_clarification_receipt",
                        "semantic_ingestion_replay_authority",
                    }),
                }
                and len(governed)
                in {1, 3}
            ):
                return
            if _is_atomic_projection_publication_write(
                records,
                projection_records,
            ):
                return
            if _is_atomic_projection_migration_progress_write(
                records,
                projection_records,
            ):
                return
            if _is_atomic_clarification_projection_write(
                records,
                projection_records,
            ):
                return
            if _is_semantic_integrity_incident_write(governed):
                return
            if _is_semantic_clean_recovery_write(governed):
                return
            if _is_reference_integrity_bootstrap_write(governed):
                return
            if _is_accepted_identity_operation_write(governed):
                return
            raise SemanticWriterAdmissionError("governed semantic write lacks one atomic control record")
        try:
            binding = SemanticWriterCommitBinding.model_validate(controls[0].content["control"]["writer_binding"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SemanticWriterAdmissionError("governed semantic control binding is corrupt") from exc
        if binding != self._admissions.commit_binding(current_admission):
            raise SemanticWriterAdmissionError("governed semantic control binding is mismatched")
        control_body = controls[0].content["control"]
        operation_fence = OperationFenceBinding.model_validate(control_body["operation_fence"])
        operation_namespace = control_body.get("persistence_namespace_id") or operation_fence.operation_id
        control_id = f"semantic_ingestion:operation:{operation_namespace}"
        prior_control = next((record for record in current if record.memory_id == control_id), None)
        if prior_control is None:
            if current_record.content.get("draining", False):
                raise SemanticWriterAdmissionError("retiring writer epoch is frozen to new operations")
            preplanning = [
                record for record in governed if record.source_kind.startswith("semantic_ingestion_preplanning")
            ]
            _validate_initial_preplanning_generation(preplanning, controls[0], operation_fence, operation_namespace)
            admission_records = [record for record in governed if record not in preplanning]
            if admission_records:
                _validate_atomic_admission_records(admission_records, operation_fence, binding)
            return
        current_generation = [
            record
            for record in current
            if record.memory_id == control_id
            or record.memory_id.startswith(f"semantic_ingestion:artifact:{operation_namespace}:")
        ]
        _validate_initial_preplanning_generation(
            current_generation, prior_control, operation_fence, operation_namespace
        )
        if len(governed) == 1 and controls[0].memory_id == control_id:
            return
        generation_records = [
            record
            for record in governed
            if record.memory_id.startswith(f"semantic_ingestion:generation:{operation_namespace}:")
        ]
        replay_authority_records = [
            record for record in governed if semantic_control_class(record) == "replay_authority"
        ]
        if len(generation_records) != (len(governed) - len(projection_records) - len(replay_authority_records) - 1):
            raise SemanticWriterAdmissionError("generation contains cross-operation governed records")
        manifests = [
            record
            for record in generation_records
            if record.content.get("semantic_ingestion_kind") == "generation_manifest"
        ]
        if len(manifests) != 1:
            raise SemanticWriterAdmissionError("generation requires exactly one manifest")
        member_records = [
            record
            for record in generation_records
            if record.content.get("semantic_ingestion_kind") == "generation_member"
        ]
        manifest_members = manifests[0].content.get("members")
        if not isinstance(manifest_members, (list, tuple)) or len(manifest_members) != len(member_records):
            raise SemanticWriterAdmissionError("generation manifest membership is incomplete")
        expected = {item.get("member_id") for item in manifest_members if isinstance(item, dict)}
        actual = {record.content.get("member", {}).get("member_id") for record in member_records}
        if expected != actual or len(expected) != len(member_records):
            raise SemanticWriterAdmissionError("generation manifest membership is inconsistent")
        if current_admission.active_runtime_mode == "evidence_only" and any(
            record.content.get("member", {}).get("kind") in {"graph_delta", "event_batch"} for record in member_records
        ):
            raise SemanticWriterAdmissionError("evidence-only writer cannot publish graph or event effects")
        if projection_records and not any(
            record.content.get("member", {}).get("kind") == "event_batch" for record in member_records
        ):
            raise SemanticWriterAdmissionError("projection publication lacks its atomic event generation")
        has_event_member = any(
            record.content.get("member", {}).get("kind") == "event_batch" for record in member_records
        )
        if has_event_member:
            _validate_replay_authority_closure(replay_authority_records)
        elif replay_authority_records:
            _validate_non_event_replay_authority_closure(replay_authority_records)


def _validate_conflict_authority_administration_write(
    records: tuple[CanonicalMemoryRecord, ...],
    current: tuple[CanonicalMemoryRecord, ...],
) -> None:
    from memorii.core.memory_evolution.conflict_attention import (
        ActiveSemanticConflictResolverAuthority,
        SemanticConflictResolverAuthority,
    )
    from memorii.core.memory_evolution.projection_history import (
        ProjectionHistoryError,
        _decode_conflict_authority_record,
    )

    try:
        decoded = tuple(_decode_conflict_authority_record(record) for record in records)
        by_type = {record_type: value for record_type, value, _ in decoded}
        if (
            len(records) != 3
            or set(by_type)
            != {
                "resolver_authority",
                "resolver_pointer_history",
                "resolver_pointer",
            }
        ):
            raise ValueError
        authority = SemanticConflictResolverAuthority.model_validate(
            by_type["resolver_authority"]
        )
        pointer = ActiveSemanticConflictResolverAuthority.model_validate(
            by_type["resolver_pointer"]
        )
        pointer_history = ActiveSemanticConflictResolverAuthority.model_validate(
            by_type["resolver_pointer_history"]
        )
    except (ProjectionHistoryError, TypeError, ValueError) as exc:
        raise SemanticWriterAdmissionError(
            "conflict authority administration closure is invalid"
        ) from exc
    expected_authority_id = (
        "semantic_ingestion:conflict-authority:resolver:"
        f"{authority.authority_record_id}"
    )
    expected_pointer_id = (
        "semantic_ingestion:conflict-authority:resolver-pointer:"
        f"{pointer.tenant_partition_id}:{pointer.renderer_schema}"
    )
    expected_pointer_history_id = (
        "semantic_ingestion:conflict-authority:resolver-pointer-history:"
        f"{pointer.tenant_partition_id}:{pointer.renderer_schema}:"
        f"{pointer.pointer_revision}"
    )
    proposed_ids = {record.memory_id for record in records}
    current_pointer_record = next(
        (record for record in current if record.memory_id == expected_pointer_id), None
    )
    if (
        proposed_ids
        != {
            expected_authority_id,
            expected_pointer_history_id,
            expected_pointer_id,
        }
        or pointer_history != pointer
        or pointer.authority_record_id != authority.authority_record_id
        or pointer.authority_record_digest != authority.authority_record_digest
        or pointer.tenant_partition_id != authority.tenant_partition_id
        or pointer.renderer_schema != authority.renderer_schema
        or (
            current_pointer_record is None
            and (
                authority.authority_revision != 1
                or pointer.pointer_revision != 1
                or pointer.predecessor_pointer_digest is not None
            )
        )
    ):
        raise SemanticWriterAdmissionError(
            "conflict authority administration closure is invalid"
        )
    if current_pointer_record is not None:
        try:
            _, current_value, _ = _decode_conflict_authority_record(
                current_pointer_record
            )
            current_pointer = ActiveSemanticConflictResolverAuthority.model_validate(
                current_value
            )
        except (ProjectionHistoryError, ValueError) as exc:
            raise SemanticWriterAdmissionError(
                "current conflict authority pointer is corrupt"
            ) from exc
        if (
            pointer.pointer_revision != current_pointer.pointer_revision + 1
            or pointer.predecessor_pointer_digest != current_pointer.pointer_digest
        ):
            raise SemanticWriterAdmissionError(
                "conflict authority administration revision is invalid"
            )
        current_authority_record = next(
            (
                record
                for record in current
                if record.memory_id
                == "semantic_ingestion:conflict-authority:resolver:"
                f"{current_pointer.authority_record_id}"
            ),
            None,
        )
        if current_authority_record is None:
            raise SemanticWriterAdmissionError(
                "current conflict authority record is absent"
            )
        try:
            _, current_authority_value, _ = _decode_conflict_authority_record(
                current_authority_record
            )
            current_authority = SemanticConflictResolverAuthority.model_validate(
                current_authority_value
            )
        except (ProjectionHistoryError, ValueError) as exc:
            raise SemanticWriterAdmissionError(
                "current conflict authority record is corrupt"
            ) from exc
        if (
            authority.authority_revision != current_authority.authority_revision + 1
            or authority.predecessor_authority_record_digest
            != current_authority.authority_record_digest
        ):
            raise SemanticWriterAdmissionError(
                "conflict authority administration revision is invalid"
            )


def _validate_conflict_authority_atomic_closure(
    records: tuple[CanonicalMemoryRecord, ...],
    complete_write: tuple[CanonicalMemoryRecord, ...],
    current: tuple[CanonicalMemoryRecord, ...],
    server_now: datetime,
) -> None:
    from memorii.core.memory_evolution.conflict_attention import (
        ActiveSemanticConflict,
        ActiveSemanticConflictResolverAuthority,
        ConflictClarificationAttempt,
        ConflictClarificationAttemptResult,
        ConflictClarificationProcessingReceipt,
        ConflictClarificationWork,
        SemanticConflictClarificationNonceConsumption,
        SemanticConflictClarificationSubmissionGeneration,
        SemanticConflictClarificationSubmissionOperation,
        SemanticConflictClarificationTransition,
        SemanticConflictClarificationWorkGeneration,
        SemanticConflictLedgerHead,
        SemanticConflictResolverAuthority,
        VerifiedUserConfirmation,
        decode_persisted_conflict_generation,
        verified_user_confirmation_digest,
    )
    from memorii.core.memory_evolution.projection_history import (
        ProjectionHistoryError,
        _decode_conflict_authority_record,
    )

    try:
        decoded = tuple(_decode_conflict_authority_record(record) for record in records)
        record_types = tuple(value[0] for value in decoded)
        immutable_coordinates = tuple(
            coordinate
            for record_type, _, coordinate in decoded
            if record_type in {"introduction", "transition", "clarification_transition"}
            and coordinate is not None
        )
        heads = tuple(
            SemanticConflictLedgerHead.model_validate(value)
            for record_type, value, _ in decoded
            if record_type == "ledger_head"
        )
    except (ProjectionHistoryError, TypeError, ValueError) as exc:
        raise SemanticWriterAdmissionError(
            "semantic conflict authority closure is invalid"
        ) from exc
    try:
        submissions = tuple(
            decode_persisted_conflict_generation(
                value, SemanticConflictClarificationSubmissionGeneration
            )
            for record_type, value, _ in decoded
            if record_type == "clarification_submission"
        )
        submission_operations = tuple(
            decode_persisted_conflict_generation(
                value, SemanticConflictClarificationSubmissionOperation
            )
            for record_type, value, _ in decoded
            if record_type == "clarification_submission_operation"
        )
        nonce_consumptions = tuple(
            decode_persisted_conflict_generation(
                value, SemanticConflictClarificationNonceConsumption
            )
            for record_type, value, _ in decoded
            if record_type == "clarification_nonce_consumption"
        )
        confirmation_proofs = tuple(
            decode_persisted_conflict_generation(value, VerifiedUserConfirmation)
            for record_type, value, _ in decoded
            if record_type == "clarification_confirmation_proof"
        )
        work_generations = tuple(
            decode_persisted_conflict_generation(
                value, SemanticConflictClarificationWorkGeneration
            )
            for record_type, value, _ in decoded
            if record_type == "clarification_work"
        )
        work_members = tuple(
            decode_persisted_conflict_generation(value, ConflictClarificationWork)
            for record_type, value, _ in decoded
            if record_type == "clarification_work_member"
        )
        attempt_members = tuple(
            decode_persisted_conflict_generation(value, ConflictClarificationAttempt)
            for record_type, value, _ in decoded
            if record_type == "clarification_attempt_member"
        )
        result_members = tuple(
            decode_persisted_conflict_generation(value, ConflictClarificationAttemptResult)
            for record_type, value, _ in decoded
            if record_type == "clarification_attempt_result_member"
        )
    except (TypeError, ValueError) as exc:
        raise SemanticWriterAdmissionError(
            "semantic conflict authority closure is invalid"
        ) from exc
    try:
        for record, (record_type, value, _) in zip(records, decoded, strict=True):
            if record_type == "clarification_work_member":
                member = decode_persisted_conflict_generation(
                    value, ConflictClarificationWork
                )
                expected_id = (
                    "semantic_ingestion:conflict-authority:clarification-work-member:"
                    f"{member.work_digest}"
                )
            elif record_type == "clarification_attempt_member":
                member = decode_persisted_conflict_generation(
                    value, ConflictClarificationAttempt
                )
                expected_id = (
                    "semantic_ingestion:conflict-authority:clarification-attempt-member:"
                    f"{member.attempt_digest}"
                )
            elif record_type == "clarification_attempt_result_member":
                member = decode_persisted_conflict_generation(
                    value, ConflictClarificationAttemptResult
                )
                expected_id = (
                    "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
                    f"{member.result_digest}"
                )
            elif record_type == "clarification_submission_operation":
                member = decode_persisted_conflict_generation(
                    value, SemanticConflictClarificationSubmissionOperation
                )
                expected_id = (
                    "semantic_ingestion:conflict-authority:clarification-submission-operation:"
                    f"{member.operation_id}"
                )
            elif record_type == "clarification_nonce_consumption":
                member = decode_persisted_conflict_generation(
                    value, SemanticConflictClarificationNonceConsumption
                )
                expected_id = (
                    "semantic_ingestion:conflict-authority:clarification-nonce-consumption:"
                    f"{member.nonce_digest}"
                )
            elif record_type == "clarification_confirmation_proof":
                member = decode_persisted_conflict_generation(
                    value, VerifiedUserConfirmation
                )
                expected_id = (
                    "semantic_ingestion:conflict-authority:clarification-confirmation-proof:"
                    f"{verified_user_confirmation_digest(member)}"
                )
            else:
                continue
            if record.memory_id != expected_id:
                raise ValueError
    except (TypeError, ValueError) as exc:
        raise SemanticWriterAdmissionError(
            "semantic conflict authority closure is invalid"
        ) from exc
    allowed_types = {
        "introduction",
        "transition",
        "clarification_transition",
        "clarification_submission",
        "clarification_submission_operation",
        "clarification_confirmation_proof",
        "clarification_nonce_consumption",
        "clarification_work",
        "clarification_work_member",
        "clarification_attempt_member",
        "clarification_attempt_result_member",
        "pointer_history",
        "active_pointer",
        "ledger_head",
    }
    projection_records = tuple(
        record
        for record in complete_write
        if record.source_kind.startswith("semantic_projection_")
    )
    if work_generations:
        # Claim and renewal append no pointer transition: their complete CAS is
        # one immutable successor keyed by an already durable predecessor.
        # Do not let an arbitrary record type piggyback on that narrow closure.
        if len(work_generations) != 1:
            raise SemanticWriterAdmissionError(
                "semantic conflict authority closure is invalid"
            )
        generation = work_generations[0]
        projection_supersession = (
            generation.transition is None
            and "transition" in record_types
            and not any(
                record.source_kind
                == "semantic_ingestion_conflict_clarification_receipt"
                for record in complete_write
            )
        )
        transitions = tuple(
            decode_persisted_conflict_generation(
                value, SemanticConflictClarificationTransition
            )
            for record_type, value, _ in decoded
            if record_type == "clarification_transition"
        )
        expected_members = (
            1 + (1 if generation.attempt is not None else 0)
            + (1 if generation.attempt_result is not None else 0)
        )
        if (
            len(work_members) != 1
            or work_members[0] != generation.work
            or len(attempt_members) != (1 if generation.attempt is not None else 0)
            or (generation.attempt is not None and attempt_members[0] != generation.attempt)
            or len(result_members) != (1 if generation.attempt_result is not None else 0)
            or (
                generation.attempt_result is not None
                and result_members[0] != generation.attempt_result
            )
            or (
                generation.transition is None
                # Terminal semantic completion appends its ordinary work
                # successor together with receipt/effect records.  Its exact
                # composite closure is checked in the terminal branch below.
                and not any(
                    record.source_kind
                    == "semantic_ingestion_conflict_clarification_receipt"
                    for record in complete_write
                )
                and not projection_supersession
                and len(records) != 1 + expected_members
            )
        ):
            raise SemanticWriterAdmissionError(
                "semantic conflict authority closure is invalid"
            )
        predecessor: ConflictClarificationWork | None = None
        try:
            submissions_by_transition_digest = {}
            successors_by_predecessor_digest = {}
            active_pointer = None
            current_head = None
            for record in current:
                if record.source_kind != "semantic_ingestion_conflict_authority":
                    continue
                record_type, value, _ = _decode_conflict_authority_record(record)
                if (
                    record_type == "active_pointer"
                    and record.memory_id
                    == "semantic_ingestion:conflict-authority:pointer:"
                    f"{generation.work.conflict_id}"
                ):
                    active_pointer = ActiveSemanticConflict.model_validate(value)
                    continue
                if record_type == "ledger_head":
                    if current_head is not None:
                        raise ValueError
                    current_head = SemanticConflictLedgerHead.model_validate(value)
                    continue
                if record_type == "clarification_submission":
                    submission = decode_persisted_conflict_generation(
                        value, SemanticConflictClarificationSubmissionGeneration
                    )
                    submissions_by_transition_digest[submission.transition.transition_digest] = submission
                    candidate = submission.work
                elif record_type == "clarification_work":
                    successor = decode_persisted_conflict_generation(
                        value, SemanticConflictClarificationWorkGeneration
                    )
                    if successor.predecessor_work_digest in successors_by_predecessor_digest:
                        raise ValueError
                    successors_by_predecessor_digest[successor.predecessor_work_digest] = successor
                    candidate = successor.work
                else:
                    candidate = None
                if candidate is not None and candidate.work_digest == generation.predecessor_work_digest:
                    if predecessor is not None:
                        raise ValueError
                    predecessor = candidate
            # A queue successor may only extend the submitted generation that
            # is live at this conflict's active pointer.  Historic exhausted
            # chains remain immutable audit data, never writable queue roots.
            if active_pointer is None:
                raise ValueError
            active_submission = submissions_by_transition_digest.get(
                active_pointer.current_record_digest
            )
            if active_submission is None:
                raise ValueError
            current_work = active_submission.work
            seen_work_digests = set()
            while current_work.work_digest in successors_by_predecessor_digest:
                if current_work.work_digest in seen_work_digests:
                    raise ValueError
                seen_work_digests.add(current_work.work_digest)
                current_work = successors_by_predecessor_digest[current_work.work_digest].work
            if current_work.work_digest != generation.predecessor_work_digest:
                raise ValueError
        except (ProjectionHistoryError, TypeError, ValueError) as exc:
            raise SemanticWriterAdmissionError(
                "semantic conflict authority closure is invalid"
            ) from exc
        if (
            predecessor is None
            or generation.work.conflict_id != predecessor.conflict_id
            or generation.work.conflict_revision != predecessor.conflict_revision
            or generation.work.proposal_digest != predecessor.proposal_digest
            or generation.work.processing_operation_id != predecessor.processing_operation_id
            or generation.work.work_revision != predecessor.work_revision + 1
            or (predecessor.owner_token is None and (
                not (
                    projection_supersession
                    and generation.attempt is None
                    and generation.attempt_result is None
                    and generation.work.owner_token is None
                    and generation.work.ownership_epoch == predecessor.ownership_epoch
                    and generation.work.attempt_count == predecessor.attempt_count
                )
                and (
                    generation.attempt is None
                    or generation.attempt_result is not None
                    or generation.work.owner_token is None
                    or generation.work.ownership_epoch != predecessor.ownership_epoch + 1
                    or generation.work.attempt_count != predecessor.attempt_count
                )
            ))
            or (predecessor.owner_token is not None and not (
                # Renewal preserves the attempt and ownership epoch.
                (
                    generation.attempt is None
                    and generation.attempt_result is None
                    and generation.transition is None
                    and generation.work.owner_token == predecessor.owner_token
                    and generation.work.ownership_epoch == predecessor.ownership_epoch
                    and generation.work.attempt_count == predecessor.attempt_count
                )
                # Reclaim closes the expired attempt and starts a fresh epoch.
                or (
                    projection_supersession
                    and generation.attempt is None
                    and generation.attempt_result is not None
                    and generation.attempt_result.outcome.value == "superseded"
                    and generation.work.owner_token is None
                    and generation.work.ownership_epoch == predecessor.ownership_epoch
                    and generation.work.attempt_count == predecessor.attempt_count
                    and generation.attempt_result.downstream_receipt_digest is None
                    and generation.attempt_result.superseded_by_conflict_revision is not None
                )
                or (
                    generation.attempt is not None
                    and generation.attempt_result is not None
                    and generation.attempt_result.outcome.value == "lease_expired"
                    and generation.work.owner_token is not None
                    and generation.work.ownership_epoch == predecessor.ownership_epoch + 1
                    and generation.work.attempt_count == predecessor.attempt_count
                )
                # Failure closes the current attempt and makes work unowned.
                or (
                    generation.attempt is None
                    and generation.attempt_result is not None
                    and generation.attempt_result.outcome.value
                    in {
                        "retryable_failure",
                        "terminal_failure",
                        "accepted",
                        "rejected",
                        "insufficient",
                    }
                    and generation.work.owner_token is None
                    and generation.work.ownership_epoch == predecessor.ownership_epoch
                    and generation.work.attempt_count
                    == predecessor.attempt_count
                    + (
                        1
                        if generation.attempt_result.outcome.value
                        == "retryable_failure"
                        else 0
                    )
                )
            ))
        ):
            raise SemanticWriterAdmissionError(
                "semantic conflict authority closure is invalid"
            )
        if generation.transition is not None:
            # Exhaustion is not a queue-only successor.  It is the same-plane
            # lifecycle CAS that reopens the conflict, so the work generation
            # must carry the exact transition, pointer/history pair, and ledger
            # head which ProjectionHistoryRepository writes atomically.
            transition = generation.transition
            try:
                if (
                    len(transitions) != 1
                    or transitions[0] != transition
                    or current_head is None
                    or transition.conflict_id != generation.work.conflict_id
                    or transition.predecessor_conflict_revision
                    != active_pointer.current_conflict_revision
                    or transition.predecessor_record_digest
                    != active_pointer.current_record_digest
                    or transition.predecessor_status.value
                    != "clarification_submitted"
                    or transition.record_coordinate
                    != current_head.last_record_coordinate + 1
                    or transition.transition_coordinate
                    != active_pointer.pointer_revision + 1
                    or len(records) != 1 + expected_members + 4
                    or record_types.count("clarification_transition") != 1
                    or record_types.count("pointer_history") != 1
                    or record_types.count("active_pointer") != 1
                    or record_types.count("ledger_head") != 1
                ):
                    raise ValueError
                transition_id = (
                    "semantic_ingestion:conflict-authority:clarification-transition:"
                    f"{transition.transition_digest}"
                )
                successor_body = {
                    "conflict_id": transition.conflict_id,
                    "current_conflict_revision": transition.resulting_attention.conflict_revision,
                    "current_record_id": transition_id,
                    "current_record_digest": transition.transition_digest,
                    "pointer_revision": active_pointer.pointer_revision + 1,
                    "predecessor_pointer_digest": active_pointer.pointer_digest,
                }
                successor_pointer = ActiveSemanticConflict(
                    **successor_body,
                    pointer_digest=sha256(
                        b"memorii.semantic-conflict-active-pointer.v1\0"
                        + encode_typed_value(successor_body)
                    ).hexdigest(),
                )
                successor_head = SemanticConflictLedgerHead.create(
                    repository_id=current_head.repository_id,
                    last_record_coordinate=transition.record_coordinate,
                    head_revision=current_head.head_revision + 1,
                    predecessor_head_digest=current_head.head_digest,
                )
                by_type = {
                    record_type: (record, value)
                    for record, (record_type, value, _) in zip(
                        records, decoded, strict=True
                    )
                    if record_type
                    in {"clarification_transition", "pointer_history", "active_pointer", "ledger_head"}
                }
                history_id = (
                    "semantic_ingestion:conflict-authority:pointer-history:"
                    f"{transition.conflict_id}:{successor_pointer.pointer_revision}"
                )
                pointer_id = (
                    "semantic_ingestion:conflict-authority:pointer:"
                    f"{transition.conflict_id}"
                )
                if (
                    by_type["clarification_transition"][0].memory_id != transition_id
                    or by_type["pointer_history"][0].memory_id != history_id
                    or by_type["active_pointer"][0].memory_id != pointer_id
                    or by_type["ledger_head"][0].memory_id
                    != "semantic_ingestion:conflict-authority:ledger-head"
                    or ActiveSemanticConflict.model_validate(by_type["pointer_history"][1])
                    != successor_pointer
                    or ActiveSemanticConflict.model_validate(by_type["active_pointer"][1])
                    != successor_pointer
                    or SemanticConflictLedgerHead.model_validate(by_type["ledger_head"][1])
                    != successor_head
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError) as exc:
                raise SemanticWriterAdmissionError(
                    "semantic conflict authority closure is invalid"
                ) from exc
        if not any(
            record.source_kind
            == "semantic_ingestion_conflict_clarification_receipt"
            for record in complete_write
        ):
            return
    if submissions:
        # Submission is a pointer transition plus its immutable operation,
        # proposal, and initial unclaimed work.  The generation's strict model
        # validation binds all those members; require the exact transition to
        # be present in this same write before accepting the pointer closure.
        transitions = tuple(
            decode_persisted_conflict_generation(
                value, SemanticConflictClarificationTransition
            )
            for record_type, value, _ in decoded
            if record_type == "clarification_transition"
        )
        if (
            len(submissions) != 1
            or len(transitions) != 1
            or submissions[0].transition != transitions[0]
            or len(submission_operations) != 1
            or submission_operations[0].operation_id != submissions[0].operation_receipt.operation_id
            or submission_operations[0].request_digest != submissions[0].operation_receipt.request_digest
            or submission_operations[0].proposal_digest != submissions[0].operation_receipt.proposal_digest
            or submission_operations[0].operation_receipt_digest != submissions[0].operation_receipt.receipt_digest
            or submission_operations[0].generation_digest != submissions[0].generation_digest
            or submission_operations[0].verified_confirmation_digest != submissions[0].operation_receipt.verified_confirmation_digest
            or len(nonce_consumptions) != (1 if submissions[0].verified_confirmation is not None else 0)
            or len(confirmation_proofs) != (1 if submissions[0].verified_confirmation is not None else 0)
            or (
                submissions[0].verified_confirmation is not None
                and confirmation_proofs[0] != submissions[0].verified_confirmation
            )
            or (submissions[0].verified_confirmation is not None and nonce_consumptions[0].operation_id != submissions[0].operation_receipt.operation_id)
            or len(work_members) != 1
            or work_members[0] != submissions[0].work
            or attempt_members
            or result_members
        ):
            raise SemanticWriterAdmissionError(
                "semantic conflict authority closure is invalid"
            )
    terminal_transitions = tuple(
        decode_persisted_conflict_generation(value, SemanticConflictClarificationTransition)
        for record_type, value, _ in decoded
        if record_type == "clarification_transition"
    )
    if (
        not submissions
        and len(terminal_transitions) == 1
        and terminal_transitions[0].reason.value in {"accepted", "rejected", "insufficient"}
    ):
        # Semantic completion is a composite write, never a loose pointer
        # edge.  The already durable attempt is intentionally not repeated;
        # its terminal work successor and result member bind it to the one
        # receipt carried by the same complete memory-plane write.
        transition = terminal_transitions[0]
        receipts = tuple(
            record
            for record in complete_write
            if record.source_kind == "semantic_ingestion_conflict_clarification_receipt"
        )
        transactions = tuple(
            record
            for record in complete_write
            if record.source_kind == "semantic_ingestion_conflict_clarification_transaction"
        )
        try:
            if len(result_members) != 1:
                raise ValueError
            receipt = (
                ConflictClarificationProcessingReceipt.model_validate_json(
                    json.dumps(receipts[0].content["receipt"])
                )
                if len(receipts) == 1
                else None
            )
            current_attempt = next(
                decode_persisted_conflict_generation(value, ConflictClarificationAttempt)
                for record in current
                if record.memory_id
                == "semantic_ingestion:conflict-authority:clarification-attempt-member:"
                f"{result_members[0].attempt_digest}"
                for record_type, value, _ in (_decode_conflict_authority_record(record),)
                if record_type == "clarification_attempt_member"
            )
            if (
                len(transactions) != 1
                or receipt is None
                or len(work_generations) != 1
                or len(work_members) != 1
                or len(result_members) != 1
                or attempt_members
                or transition.resulting_attention.status.value
                != ("resolved" if transition.reason.value == "accepted" else "open")
                or receipt.conflict_id != transition.conflict_id
                or receipt.conflict_revision != transition.resulting_attention.conflict_revision
                or receipt.proposal_digest != transition.proposal_digest
                or receipt.processing_operation_id != transition.processing_operation_id
                or receipt.committed_outcome != transition.reason.value
                or result_members[0].outcome.value != transition.reason.value
                or result_members[0].downstream_receipt_digest != receipt.receipt_digest
                or result_members[0].attempt_digest != current_attempt.attempt_digest
                or result_members[0].processing_operation_id != receipt.processing_operation_id
                or work_members[0].owner_token is not None
                or work_members[0].lease_expires_at is not None
                or work_members[0].downstream_receipt_digest != receipt.receipt_digest
                or work_members[0].predecessor_work_digest is None
                or work_members[0].processing_operation_id != receipt.processing_operation_id
                or work_generations[0].predecessor_work_digest
                != work_members[0].predecessor_work_digest
                or work_generations[0].work != work_members[0]
                or work_generations[0].attempt is not None
                or work_generations[0].attempt_result != result_members[0]
                or work_generations[0].transition is not None
            ):
                raise ValueError
            if transition.reason.value == "accepted" and not any(
                record.source_kind == "semantic_ingestion_event_batch"
                for record in complete_write
            ):
                raise ValueError
            if transition.reason.value != "accepted" and any(
                record.source_kind == "semantic_ingestion_event_batch"
                for record in complete_write
            ):
                raise ValueError
        except (IndexError, KeyError, StopIteration, TypeError, ValueError) as exc:
            raise SemanticWriterAdmissionError(
                "semantic clarification completion closure is invalid"
            ) from exc
    if (
        # Projection publication supplies the ordinary conflict closure.  A
        # clarification lifecycle edge is independently complete: it carries
        # its own pointer/history/head CAS and must not be routed through the
        # resolver-authority administration capability.
        not projection_records
        and not any(record_type == "clarification_transition" for record_type in record_types)
        or not set(record_types) <= allowed_types
        or len(heads) != (1 if immutable_coordinates else 0)
        or record_types.count("pointer_history") != len(immutable_coordinates)
        or record_types.count("active_pointer")
        != len(immutable_coordinates)
        or record_types.count("active_pointer")
        != len(
            {
                record.memory_id
                for record in records
                if record.content.get("authority_record_type") == "active_pointer"
            }
        )
        or (
            immutable_coordinates
            and (
                tuple(sorted(immutable_coordinates))
                != tuple(
                    range(
                        min(immutable_coordinates),
                        max(immutable_coordinates) + 1,
                    )
                )
                or heads[0].last_record_coordinate != max(immutable_coordinates)
            )
        )
    ):
        raise SemanticWriterAdmissionError(
            "semantic conflict authority closure is invalid"
        )
    at = server_now.astimezone(UTC)
    current_by_id = {record.memory_id: record for record in current}
    for record_type, value, _ in decoded:
        if record_type not in {"introduction", "transition"} or not isinstance(
            value, dict
        ):
            continue
        if (
            record_type == "transition"
            and value.get("reason") == "projection_resolved"
        ):
            continue
        display = value.get("display")
        if not isinstance(display, dict):
            raise SemanticWriterAdmissionError(
                "semantic conflict resolver closure is invalid"
            )
        authority_id = (
            "semantic_ingestion:conflict-authority:resolver:"
            f"{display.get('authority_record_id')}"
        )
        pointer_id = (
            "semantic_ingestion:conflict-authority:resolver-pointer:"
            f"{value.get('scope', {}).get('tenant_partition_id')}:"
            f"{display.get('renderer_schema')}"
        )
        authority_record = current_by_id.get(authority_id)
        pointer_record = current_by_id.get(pointer_id)
        if authority_record is None or pointer_record is None:
            raise SemanticWriterAdmissionError(
                "semantic conflict resolver closure is absent"
            )
        try:
            authority = SemanticConflictResolverAuthority.model_validate(
                _decode_conflict_authority_record(authority_record)[1]
            )
            pointer = ActiveSemanticConflictResolverAuthority.model_validate(
                _decode_conflict_authority_record(pointer_record)[1]
            )
        except (ProjectionHistoryError, ValueError) as exc:
            raise SemanticWriterAdmissionError(
                "semantic conflict resolver closure is corrupt"
            ) from exc
        if (
            authority.status != "active"
            or not authority.valid_from <= at < authority.valid_until
            or authority.authority_record_id != display.get("authority_record_id")
            or authority.authority_record_digest
            != display.get("authority_record_digest")
            or authority.valid_until != display.get("authority_valid_until")
            or pointer.authority_record_id != authority.authority_record_id
            or pointer.authority_record_digest != authority.authority_record_digest
            or pointer.pointer_digest != display.get("authority_pointer_digest")
        ):
            raise SemanticWriterAdmissionError(
                "semantic conflict resolver closure is stale or expired"
            )


def _validate_projection_namespace_records(
    records: list[CanonicalMemoryRecord],
) -> None:
    for record in records:
        if (
            record.source_kind not in _SEMANTIC_PROJECTION_SOURCE_KINDS
            or not record.memory_id.startswith("semantic_projection:")
            or record.content.get("projection_authority_kind")
            not in {
                "certificate",
                "generation",
                "history_entry",
                "active_pointer",
                "projection",
                "decay_command",
                "migration_plan",
                "migration_catch_up",
                "migration_command",
                "migration_result",
                "migration_cutover",
            }
        ):
            raise SemanticWriterAdmissionError("semantic projection namespace or source kind is invalid")


def _is_atomic_projection_publication_write(
    records: tuple[CanonicalMemoryRecord, ...],
    projection_records: list[CanonicalMemoryRecord],
) -> bool:
    envelopes = tuple(
        record
        for record in records
        if record.source_kind == "semantic_ingestion_projection_publication"
    )
    non_projection = tuple(
        record for record in records if record not in projection_records
    )
    replay_kinds = {
        "semantic_ingestion_replay_authority",
        "semantic_ingestion_checkpoint_lifecycle",
        "semantic_ingestion_event_schema_registry_history",
    }
    if (
        len(envelopes) != 1
        or len(non_projection) != 1 + len(replay_kinds)
        or {record.source_kind for record in non_projection if record not in envelopes}
        != replay_kinds
    ):
        return False
    envelope = envelopes[0]
    expected_fields = {
        "semantic_ingestion_kind",
        "publication_kind",
        "projection_kind",
        "repository_id",
        "operation_id",
        "authority_coordinate_digest",
        "policy_snapshot_digest",
        "active_policy_fingerprint",
        "complete_read_set_digest",
        "writer_epoch",
        "certificate_digest",
        "generation_digest",
        "pointer_digest",
        "pointer_publication_kind",
        "envelope_digest",
    }
    content = envelope.content
    if (
        set(content) != expected_fields
        or content.get("semantic_ingestion_kind") != "projection_publication"
        or content.get("publication_kind")
        not in {
            "trust_decay_schedule",
            "trust_decay_threshold",
            "temporal_policy_migration",
            "trust_policy_migration",
        }
        or content.get("projection_kind") not in {"temporal", "trust"}
        or content.get("pointer_publication_kind")
        not in {"projection_commit", "migration_cutover"}
        or not isinstance(content.get("writer_epoch"), int)
        or content["writer_epoch"] < 1
    ):
        return False
    digest_fields = (
        "authority_coordinate_digest",
        "policy_snapshot_digest",
        "active_policy_fingerprint",
        "complete_read_set_digest",
        "certificate_digest",
        "generation_digest",
        "pointer_digest",
        "envelope_digest",
    )
    if any(
        not isinstance(content.get(field), str)
        or len(content[field]) != 64
        or any(character not in "0123456789abcdef" for character in content[field])
        for field in digest_fields
    ):
        return False
    envelope_body = {key: value for key, value in content.items() if key != "envelope_digest"}
    if (
        content["envelope_digest"] != sha256(encode_typed_value(envelope_body)).hexdigest()
        or envelope.memory_id
        != "semantic_ingestion:projection-publication:"
        + sha256(str(content["operation_id"]).encode()).hexdigest()
        or envelope.domain != MemoryDomain.EXECUTION
        or envelope.status != CommitStatus.COMMITTED
        or envelope.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
        or envelope.text
    ):
        return False
    projection_kind = content["projection_kind"]
    if any(
        not record.source_kind.startswith(f"semantic_projection_{projection_kind}_")
        for record in projection_records
    ):
        return False
    by_kind: dict[str, list[CanonicalMemoryRecord]] = {}
    for record in projection_records:
        authority_kind = record.content.get("projection_authority_kind")
        if not isinstance(authority_kind, str):
            return False
        by_kind.setdefault(authority_kind, []).append(record)
    if any(len(by_kind.get(kind, ())) != 1 for kind in ("certificate", "generation", "history_entry", "active_pointer")):
        return False
    try:
        certificate = decode_typed_value(
            bytes.fromhex(str(by_kind["certificate"][0].content["canonical_hex"]))
        )
        generation = decode_typed_value(
            bytes.fromhex(str(by_kind["generation"][0].content["canonical_hex"]))
        )
        pointer = decode_typed_value(
            bytes.fromhex(str(by_kind["active_pointer"][0].content["canonical_hex"]))
        )
    except (KeyError, TypeError, ValueError):
        return False
    if not all(isinstance(value, dict) for value in (certificate, generation, pointer)):
        return False
    assert isinstance(certificate, dict)
    assert isinstance(generation, dict)
    assert isinstance(pointer, dict)
    policy_field = (
        "temporal_policy_fingerprint"
        if projection_kind == "temporal"
        else "trust_policy_fingerprint"
    )
    certificate_policy = certificate.get(
        policy_field,
        certificate.get("pending_policy_fingerprint"),
    )
    return bool(
        certificate.get("certificate_digest") == content["certificate_digest"]
        and generation.get("generation_digest") == content["generation_digest"]
        and pointer.get("pointer_digest") == content["pointer_digest"]
        and pointer.get("generation_digest") == content["generation_digest"]
        and pointer.get("publication_certificate_digest")
        == content["certificate_digest"]
        and pointer.get("publication_kind") == content["pointer_publication_kind"]
        and pointer.get("writer_epoch") == content["writer_epoch"]
        and pointer.get("policy_fingerprint") == content["active_policy_fingerprint"]
        and generation.get(policy_field) == content["active_policy_fingerprint"]
        and certificate_policy == content["active_policy_fingerprint"]
    )


def _is_atomic_projection_migration_progress_write(
    records: tuple[CanonicalMemoryRecord, ...],
    projection_records: list[CanonicalMemoryRecord],
) -> bool:
    envelopes = tuple(
        record
        for record in records
        if record.source_kind == "semantic_ingestion_projection_publication"
        and record.content.get("semantic_ingestion_kind")
        == "projection_migration_progress"
    )
    if len(envelopes) != 1 or len(records) != len(projection_records) + 1:
        return False
    envelope = envelopes[0]
    content = envelope.content
    expected_fields = {
        "semantic_ingestion_kind",
        "publication_kind",
        "projection_kind",
        "repository_id",
        "operation_id",
        "migration_plan_digest",
        "catch_up_entry_digests",
        "result_digests",
        "writer_epoch",
        "progress_digest",
        "envelope_digest",
    }
    if (
        set(content) != expected_fields
        or content.get("publication_kind")
        not in {
            "temporal_policy_migration_progress",
            "trust_policy_migration_progress",
        }
        or content.get("projection_kind") not in {"temporal", "trust"}
        or not isinstance(content.get("writer_epoch"), int)
        or content["writer_epoch"] < 1
        or not isinstance(content.get("catch_up_entry_digests"), (list, tuple))
        or not isinstance(content.get("result_digests"), (list, tuple))
    ):
        return False
    digest_fields = ("migration_plan_digest", "progress_digest", "envelope_digest")
    digest_sequences = ("catch_up_entry_digests", "result_digests")
    if any(not _is_lower_hex_digest(content.get(field)) for field in digest_fields):
        return False
    if any(
        tuple(content[field]) != tuple(sorted(set(content[field])))
        or any(not _is_lower_hex_digest(value) for value in content[field])
        for field in digest_sequences
    ):
        return False
    envelope_body = {
        key: value for key, value in content.items() if key != "envelope_digest"
    }
    progress_body = {
        "migration_kind": content["projection_kind"],
        "migration_plan_digest": content["migration_plan_digest"],
        "catch_up_entry_digests": tuple(content["catch_up_entry_digests"]),
        "result_digests": tuple(content["result_digests"]),
        "writer_epoch": content["writer_epoch"],
    }
    if (
        content["envelope_digest"]
        != sha256(encode_typed_value(envelope_body)).hexdigest()
        or content["progress_digest"]
        != sha256(
            b"memorii.policy-migration-plan.v1\0"
            + encode_typed_value(progress_body)
        ).hexdigest()
        or envelope.memory_id
        != "semantic_ingestion:projection-publication:"
        + sha256(str(content["operation_id"]).encode()).hexdigest()
        or envelope.domain != MemoryDomain.EXECUTION
        or envelope.status != CommitStatus.COMMITTED
        or envelope.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
        or envelope.text
    ):
        return False
    projection_kind = content["projection_kind"]
    if any(
        record.source_kind
        != f"semantic_projection_{projection_kind}_{record.content.get('projection_authority_kind')}"
        for record in projection_records
    ):
        return False
    by_kind: dict[str, list[dict[str, object]]] = {}
    for record in projection_records:
        authority_kind = record.content.get("projection_authority_kind")
        if authority_kind not in {
            "migration_plan",
            "migration_catch_up",
            "migration_command",
            "migration_result",
            "decay_command",
        }:
            return False
        try:
            raw = bytes.fromhex(str(record.content["canonical_hex"]))
            value = decode_typed_value(raw)
        except (KeyError, TypeError, ValueError):
            return False
        if not isinstance(value, dict):
            return False
        if authority_kind == "decay_command":
            command_digest = value.get("command_digest")
            if (
                set(record.content)
                != {"projection_authority_kind", "canonical_hex", "authority_digest"}
                or not _is_lower_hex_digest(command_digest)
                or record.content.get("authority_digest") != sha256(raw).hexdigest()
                or not record.memory_id.endswith(f":{command_digest}")
            ):
                return False
            by_kind.setdefault(str(authority_kind), []).append(value)
            continue
        digest_field = {
            "migration_plan": "plan_digest",
            "migration_catch_up": "entry_digest",
            "migration_command": "command_digest",
            "migration_result": "result_digest",
        }[str(authority_kind)]
        authority_digest = value.get(digest_field)
        if (
            not _is_lower_hex_digest(authority_digest)
            or record.content.get("authority_digest") != authority_digest
            or not record.memory_id.endswith(f":{authority_digest}")
        ):
            return False
        by_kind.setdefault(str(authority_kind), []).append(value)
    plans = by_kind.get("migration_plan", [])
    if len(plans) != 1:
        return False
    plan = plans[0]
    catch_up = by_kind.get("migration_catch_up", [])
    results = by_kind.get("migration_result", [])
    commands = by_kind.get("decay_command", [])
    migration_commands = by_kind.get("migration_command", [])
    expected_command_values: list[str] = []
    for item in results:
        raw_digests = item.get("decay_command_digests", ())
        if not isinstance(raw_digests, (list, tuple)):
            return False
        expected_command_values.extend(str(digest) for digest in raw_digests)
    expected_commands = tuple(sorted(expected_command_values))
    raw_plan_slots = plan.get("slot_plans", ())
    if not isinstance(raw_plan_slots, (list, tuple)) or any(
        not isinstance(item, dict) for item in raw_plan_slots
    ):
        return False
    expected_migration_work_items = (
        {
            *(str(item.get("slot_plan_digest")) for item in raw_plan_slots),
            *(str(item.get("entry_digest")) for item in catch_up),
        }
        if projection_kind == "temporal"
        else set()
    )
    return bool(
        plan.get("migration_kind") == projection_kind
        and plan.get("plan_digest") == content["migration_plan_digest"]
        and plan.get("writer_epoch") == content["writer_epoch"]
        and all(
            item.get("migration_plan_digest") == content["migration_plan_digest"]
            for item in (*catch_up, *results)
        )
        and tuple(sorted(str(item.get("entry_digest")) for item in catch_up))
        == tuple(content["catch_up_entry_digests"])
        and tuple(sorted(str(item.get("result_digest")) for item in results))
        == tuple(content["result_digests"])
        and tuple(sorted(str(item.get("command_digest")) for item in commands))
        == expected_commands
        and {
            str(item.get("migration_work_item_digest"))
            for item in migration_commands
        }
        == expected_migration_work_items
        and len(migration_commands) == len(expected_migration_work_items)
        and all(
            item.get("migration_plan_digest") == content["migration_plan_digest"]
            and item.get("migration_kind") == "temporal"
            for item in migration_commands
        )
        and all(
            item.get("migration_kind") != "temporal"
            or item.get("status") != "committed"
            or item.get("command_digest")
            in {
                command.get("command_digest") for command in migration_commands
            }
            for item in results
        )
    )


def _is_lower_hex_digest(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_atomic_clarification_projection_write(
    records: tuple[CanonicalMemoryRecord, ...],
    projection_records: list[CanonicalMemoryRecord],
) -> bool:
    if (
        not projection_records
        and len(records) == 1
        and records[0].source_kind == "semantic_ingestion_conflict_clarification_context"
        and records[0].memory_id.startswith("semantic_ingestion:clarification:context:")
    ):
        return True
    required = {
        "semantic_ingestion_conflict_clarification_transaction",
        "semantic_ingestion_conflict_clarification_receipt",
        "semantic_ingestion_conflict_clarification_recovery_authority",
        "semantic_ingestion_event_batch",
        "semantic_ingestion_replay_state",
        "semantic_ingestion_replay_authority",
        "semantic_ingestion_checkpoint_lifecycle",
        "semantic_ingestion_event_schema_registry_history",
    }
    optional = {
        "semantic_ingestion_reference_integrity",
        "semantic_ingestion_graph_identity_reservation",
    }
    non_projection = tuple(record for record in records if record not in projection_records)
    kinds = {record.source_kind for record in non_projection}
    singleton_records = tuple(
        record
        for record in non_projection
        if record.source_kind != "semantic_ingestion_graph_identity_reservation"
    )
    reservation_ids = tuple(
        record.memory_id
        for record in non_projection
        if record.source_kind == "semantic_ingestion_graph_identity_reservation"
    )
    return (
        required.issubset(kinds)
        and kinds.issubset(required | optional)
        and len(singleton_records)
        == len({record.source_kind for record in singleton_records})
        and reservation_ids == tuple(sorted(set(reservation_ids)))
    )


def _is_atomic_clarification_terminal_pair(
    records: tuple[CanonicalMemoryRecord, ...],
) -> bool:
    """Recognize the exact no-projection clarification transaction closure."""

    from memorii.core.memory_evolution.conflict_attention import (
        ConflictClarificationProcessingReceipt,
    )

    if len(records) != 2:
        return False
    by_kind = {record.source_kind: record for record in records}
    if set(by_kind) != {
        "semantic_ingestion_conflict_clarification_transaction",
        "semantic_ingestion_conflict_clarification_receipt",
    }:
        return False
    transaction_record = by_kind["semantic_ingestion_conflict_clarification_transaction"]
    receipt_record = by_kind["semantic_ingestion_conflict_clarification_receipt"]
    if (
        set(transaction_record.content)
        != {
            "semantic_ingestion_kind",
            "semantic_transaction_id",
            "semantic_transaction_digest",
            "transaction",
        }
        or set(receipt_record.content)
        != {"semantic_ingestion_kind", "receipt"}
        or
        transaction_record.content.get("semantic_ingestion_kind")
        != "conflict_clarification_transaction"
        or receipt_record.content.get("semantic_ingestion_kind")
        != "conflict_clarification_processing_receipt"
    ):
        return False
    body = transaction_record.content.get("transaction")
    try:
        receipt = ConflictClarificationProcessingReceipt.model_validate_json(
            json.dumps(
                receipt_record.content["receipt"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    except (KeyError, TypeError, ValueError):
        return False
    if not isinstance(body, dict):
        return False
    if set(body) != {
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
    }:
        return False
    processing_operation_id = body.get("processing_operation_id")
    committed_outcome = body.get("committed_outcome")
    transaction_id = transaction_record.content.get("semantic_transaction_id")
    transaction_digest = transaction_record.content.get("semantic_transaction_digest")
    if (
        not isinstance(processing_operation_id, str)
        or not processing_operation_id
        or committed_outcome not in {"rejected", "insufficient"}
        or transaction_id != f"clarification-{processing_operation_id}"
        or transaction_digest != sha256(encode_typed_value(body)).hexdigest()
        or transaction_record.memory_id
        != f"semantic_ingestion:clarification:transaction:{processing_operation_id}"
        or receipt_record.memory_id
        != f"semantic_ingestion:clarification:receipt:{processing_operation_id}"
    ):
        return False
    return (
        receipt.processing_operation_id == processing_operation_id
        and receipt.semantic_transaction_id == transaction_id
        and receipt.semantic_transaction_digest == transaction_digest
        and receipt.conflict_id == body.get("conflict_id")
        and receipt.conflict_revision == body.get("resulting_conflict_revision")
        and receipt.proposal_digest == body.get("proposal_digest")
        and receipt.policy_fingerprint == body.get("policy_fingerprint")
        and receipt.semantic_result_digest == body.get("semantic_result_digest")
        and receipt.committed_outcome == committed_outcome
        and isinstance(body.get("source_user_event_id"), str)
        and bool(body["source_user_event_id"])
        and _is_lower_hex_digest(body.get("source_user_event_digest"))
        and (
            body.get("clarification_cas_input_digest") is None
            or _is_lower_hex_digest(body.get("clarification_cas_input_digest"))
        )
    )


def _validate_replay_authority_closure(
    records: list[CanonicalMemoryRecord],
) -> None:
    required = {
        "semantic_ingestion_event_batch",
        "semantic_ingestion_replay_state",
        "semantic_ingestion_replay_authority",
        "semantic_ingestion_checkpoint_lifecycle",
        "semantic_ingestion_event_schema_registry_history",
    }
    optional = {
        "semantic_ingestion_reference_integrity",
        "semantic_ingestion_graph_identity_reservation",
    }
    kinds = {record.source_kind for record in records}
    singleton_records = tuple(
        record
        for record in records
        if record.source_kind != "semantic_ingestion_graph_identity_reservation"
    )
    reservation_ids = tuple(
        record.memory_id
        for record in records
        if record.source_kind == "semantic_ingestion_graph_identity_reservation"
    )
    if (
        not required.issubset(kinds)
        or not kinds.issubset(required | optional)
        or len(singleton_records) != len({record.source_kind for record in singleton_records})
        or reservation_ids != tuple(sorted(set(reservation_ids)))
    ):
        raise SemanticWriterAdmissionError("semantic replay authority closure is incomplete")


def _validate_non_event_replay_authority_closure(
    records: list[CanonicalMemoryRecord],
) -> None:
    required = {
        "semantic_ingestion_replay_authority",
        "semantic_ingestion_checkpoint_lifecycle",
        "semantic_ingestion_event_schema_registry_history",
    }
    if len(records) != len(required) or {record.source_kind for record in records} != required:
        raise SemanticWriterAdmissionError("semantic checkpoint authority closure is incomplete")


def _is_semantic_integrity_incident_write(
    records: list[CanonicalMemoryRecord],
) -> bool:
    kinds = tuple(sorted(record.source_kind for record in records))
    return kinds == (
        "semantic_ingestion_replay_integrity_attention",
        "semantic_ingestion_replay_integrity_control",
    ) and all(record.memory_id.startswith("semantic_ingestion:event-authority:integrity-") for record in records)


def _is_reference_integrity_bootstrap_write(records: list[CanonicalMemoryRecord]) -> bool:
    return (
        len(records) == 1
        and records[0].source_kind == "semantic_ingestion_reference_integrity"
        and records[0].memory_id == "semantic_ingestion:reference-integrity:ledger"
        and records[0].content.get("semantic_ingestion_kind") == "reference_integrity_ledger"
    )


def _is_accepted_identity_operation_write(records: list[CanonicalMemoryRecord]) -> bool:
    plans = tuple(
        record
        for record in records
        if record.source_kind == "semantic_ingestion_accepted_identity_operation"
    )
    reservations = tuple(record for record in records if record not in plans)
    if (
        len(plans) != 1
        or not plans[0].memory_id.startswith("semantic_ingestion:accepted-identity:")
        or plans[0].content.get("semantic_ingestion_kind")
        != "accepted_identity_operation"
    ):
        return False
    operation_id = plans[0].content.get("operation_id")
    return all(
        record.source_kind == "semantic_ingestion_graph_identity_reservation"
        and record.memory_id.startswith("semantic_ingestion:graph-reservation:")
        and record.content.get("semantic_ingestion_kind")
        == "graph_identity_reservation"
        and record.content.get("operation_id") == operation_id
        for record in reservations
    )


def _is_semantic_clean_recovery_write(
    records: list[CanonicalMemoryRecord],
) -> bool:
    if not records or any(semantic_control_class(record) not in {"recovery", "replay_authority"} for record in records):
        return False
    kinds = tuple(sorted(record.source_kind for record in records))
    if kinds == ("semantic_ingestion_clean_recovery_request",):
        return records[0].content.get("semantic_ingestion_kind") == "clean_recovery_request"
    if kinds == (
        "semantic_ingestion_clean_generation",
        "semantic_ingestion_clean_generation_status",
    ):
        request_digests = {record.content.get("request_digest") for record in records}
        return len(request_digests) == 1 and None not in request_digests
    required = {
        "semantic_ingestion_clean_generation_status",
        "semantic_ingestion_replay_authority",
        "semantic_ingestion_replay_state",
    }
    observed = {record.source_kind for record in records}
    allowed = required | {
        "semantic_ingestion_event_batch",
        "semantic_ingestion_retained_corrupt_event_batch_slot",
    }
    return (
        required <= observed
        and observed <= allowed
        and all(sum(record.source_kind == required_kind for record in records) == 1 for required_kind in required)
        and any(record.source_kind == "semantic_ingestion_event_batch" for record in records)
        and next(
            record for record in records if record.source_kind == "semantic_ingestion_clean_generation_status"
        ).content.get("status")
        == "activated"
    )


def _validate_initial_preplanning_generation(
    records: list[CanonicalMemoryRecord],
    control: CanonicalMemoryRecord,
    fence: OperationFenceBinding,
    operation_namespace: str,
) -> None:
    introduction = encode_typed_value(
        {
            "kind": "operation_introduction",
            "operation_fence": fence.model_dump(mode="python"),
            "graph_record_ids": (),
            "event_ids": (),
            "terminal_group_ids": (),
        }
    )
    index = encode_typed_value(
        {
            "kind": "artifact_index",
            "members": (("introduction", sha256(introduction).hexdigest()),),
        }
    )
    closure = encode_typed_value(
        {
            "kind": "artifact_closure",
            "members": (
                ("introduction", sha256(introduction).hexdigest()),
                ("index", sha256(index).hexdigest()),
            ),
            "graph_record_ids": (),
            "event_ids": (),
            "terminal_group_ids": (),
        }
    )
    expected_artifacts = {
        f"semantic_ingestion:artifact:{operation_namespace}:{kind}": (
            f"preplanning_{kind}",
            value,
        )
        for kind, value in (
            ("introduction", introduction),
            ("index", index),
            ("closure", closure),
        )
    }
    expected_ids = {f"semantic_ingestion:operation:{operation_namespace}", *expected_artifacts}
    if {record.memory_id for record in records} != expected_ids:
        raise SemanticWriterAdmissionError("preplanning generation membership is incomplete")
    for record in records:
        if record.memory_id == control.memory_id:
            if record.source_kind != "semantic_ingestion_preplanning_control":
                raise SemanticWriterAdmissionError("preplanning control record kind is invalid")
            continue
        kind, value = expected_artifacts[record.memory_id]
        if record.source_kind != "semantic_ingestion_preplanning_artifact" or record.content != {
            "semantic_ingestion_kind": kind,
            "canonical_bytes_base64": base64.b64encode(value).decode("ascii"),
            "digest": sha256(value).hexdigest(),
        }:
            raise SemanticWriterAdmissionError("preplanning artifact closure is invalid")


def _validate_atomic_admission_records(
    records: list[CanonicalMemoryRecord],
    fence: OperationFenceBinding,
    binding: SemanticWriterCommitBinding,
) -> None:
    sources = [
        record
        for record in records
        if record.source_kind in {"semantic_ingestion_source", "semantic_ingestion_metadata_poor_snapshot"}
    ]
    indexes = [record for record in records if record.source_kind == "semantic_ingestion_admission_index"]
    profile_kinds = {
        "semantic_ingestion_profile_selection",
        "semantic_ingestion_profile_verification",
        "semantic_ingestion_profile_outcome",
    }
    profiles = [record for record in records if record.source_kind in profile_kinds]
    if len(sources) != 1 or len(indexes) != 1 or {record.source_kind for record in profiles} != profile_kinds:
        raise SemanticWriterAdmissionError("atomic admission generation membership is incomplete")
    if len(records) != 5 or sources[0].memory_id != fence.source_id:
        raise SemanticWriterAdmissionError("atomic admission source binding is mismatched")
    index = indexes[0]
    if (
        index.content.get("operation_fence_binding") != fence.model_dump(mode="json")
        or index.content.get("admitted_writer_epoch") != binding.expected_writer_epoch
        or index.content.get("writer_admission_digest") != binding.admission_digest
    ):
        raise SemanticWriterAdmissionError("atomic admission index binding is mismatched")


def _admission_digest(
    admission_id: str, mode: str, writer: str, schema: str, epoch: int, activated_at: datetime, previous: str | None
) -> str:
    return sha256(
        encode_typed_value(
            {
                "admission_id": admission_id,
                "writer_namespace": "semantic_ingestion",
                "active_runtime_mode": mode,
                "active_writer_implementation_fingerprint": writer,
                "accepted_graph_schema_fingerprint": schema,
                "writer_epoch": epoch,
                "activated_at": activated_at,
                "previous_admission_digest": previous,
            }
        )
    ).hexdigest()


def _matches_initial_evidence_only(
    admission: SemanticWriterAdmission,
    manifest: SemanticRecordOwnershipManifest,
    *,
    expected_manifest: SemanticRecordOwnershipManifest,
    admission_id: str,
    writer_implementation_fingerprint: str,
    graph_schema_fingerprint: str,
) -> bool:
    return (
        manifest == expected_manifest
        and admission.admission_id == admission_id
        and admission.active_runtime_mode == "evidence_only"
        and admission.active_writer_implementation_fingerprint == writer_implementation_fingerprint
        and admission.accepted_graph_schema_fingerprint == graph_schema_fingerprint
        and admission.writer_epoch == 1
        and admission.previous_admission_digest is None
    )


def _matches_completed_transition(
    admission: SemanticWriterAdmission,
    *,
    expected: SemanticWriterCommitBinding,
    admission_id: str,
    runtime_mode: str,
    writer_implementation_fingerprint: str,
    graph_schema_fingerprint: str,
    migration_activation: DeliveryCoordinateMigrationActivation,
    current_record: CanonicalMemoryRecord,
) -> bool:
    return (
        admission.admission_id == admission_id
        and admission.active_runtime_mode == runtime_mode
        and admission.active_writer_implementation_fingerprint == writer_implementation_fingerprint
        and admission.accepted_graph_schema_fingerprint == graph_schema_fingerprint
        and admission.writer_epoch == expected.expected_writer_epoch + 1
        and admission.previous_admission_digest == expected.admission_digest
        and migration_activation.source_writer_epoch == expected.expected_writer_epoch
        and migration_activation.target_writer_epoch == admission.writer_epoch
        and current_record.content.get("migration_activation_digest") == migration_activation.activation_digest
    )


def _record(
    admission: SemanticWriterAdmission,
    manifest: SemanticRecordOwnershipManifest,
    timestamp: datetime,
    *,
    migration_activation_digest: str | None = None,
    policy_activation_digest: str | None = None,
    draining: bool = False,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=writer_admission_memory_id(),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "writer_admission",
            "admission": admission.model_dump(mode="json"),
            "manifest": {
                "manifest_revision": manifest.manifest_revision,
                "governed_record_kinds": sorted(manifest.governed_record_kinds),
                "semantic_store_methods": sorted(manifest.semantic_store_methods),
                "manifest_digest": manifest.manifest_digest,
            },
            "migration_activation_digest": migration_activation_digest,
            **(
                {"policy_activation_digest": policy_activation_digest}
                if policy_activation_digest is not None
                else {}
            ),
            "draining": draining,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_writer_admission",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _migration_records(
    plan: DeliveryCoordinateMigrationPlan,
    checkpoint: DeliveryCoordinateMigrationCheckpoint,
    certificate: DeliveryCoordinateMigrationCertificate,
    activation: DeliveryCoordinateMigrationActivation,
    timestamp: datetime,
    target_projections: tuple[DeliveryCoordinateMigrationTargetProjection, ...],
) -> tuple[CanonicalMemoryRecord, ...]:
    values = (
        ("plan", plan.plan_digest, plan.model_dump(mode="json")),
        ("checkpoint", checkpoint.checkpoint_digest, checkpoint.model_dump(mode="json")),
        ("certificate", certificate.certificate_digest, certificate.model_dump(mode="json")),
        ("activation", activation.activation_digest, activation.model_dump(mode="json")),
        *(
            ("target_projection", projection.projection_digest, projection.model_dump(mode="json"))
            for projection in target_projections
        ),
    )
    return tuple(
        CanonicalMemoryRecord(
            memory_id=f"semantic_ingestion:migration:{kind}:{digest}",
            domain=MemoryDomain.EXECUTION,
            text="",
            content={"semantic_ingestion_kind": f"migration_{kind}", kind: value},
            status=CommitStatus.COMMITTED,
            source_kind=f"semantic_ingestion_migration_{kind}",
            timestamp=timestamp,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        for kind, digest, value in values
    )


def _from_record(record: CanonicalMemoryRecord) -> tuple[SemanticWriterAdmission, SemanticRecordOwnershipManifest]:
    if (
        record.source_kind != "semantic_ingestion_writer_admission"
        or record.content.get("semantic_ingestion_kind") != "writer_admission"
    ):
        raise SemanticWriterAdmissionError("stored writer admission is corrupt")
    try:
        admission = SemanticWriterAdmission.model_validate(record.content["admission"])
        manifest = SemanticRecordOwnershipManifest.model_validate(record.content["manifest"])
        if admission.admission_digest != _admission_digest(
            admission.admission_id,
            admission.active_runtime_mode,
            admission.active_writer_implementation_fingerprint,
            admission.accepted_graph_schema_fingerprint,
            admission.writer_epoch,
            admission.activated_at,
            admission.previous_admission_digest,
        ):
            raise SemanticWriterAdmissionError("stored writer admission digest is corrupt")
        if (
            manifest.manifest_digest
            != sha256(
                encode_typed_value(
                    {
                        "manifest_revision": manifest.manifest_revision,
                        "governed_record_kinds": manifest.governed_record_kinds,
                        "semantic_store_methods": manifest.semantic_store_methods,
                    }
                )
            ).hexdigest()
        ):
            raise SemanticWriterAdmissionError("stored writer manifest digest is corrupt")
        return admission, manifest
    except (KeyError, ValueError) as exc:
        raise SemanticWriterAdmissionError("stored writer admission is corrupt") from exc
