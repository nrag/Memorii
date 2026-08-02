"""Store-owned Section 3.13 writer admission for the bounded M2 slice."""

from __future__ import annotations

import base64
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
    encode_typed_value,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    MemoryPlaneWriteAuthorization,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_KINDS = frozenset(
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
    }
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


def bounded_preplanning_ownership_manifest() -> SemanticRecordOwnershipManifest:
    """Return the complete M2 governed-write inventory (legacy name retained)."""
    revision = "m2-semantic-generation-v2"
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
        self._transition_owner = object()
        self._memory_plane.install_governed_write_policy(SemanticGovernedWritePolicy(self))

    def governed_write_policy(self) -> SemanticGovernedWritePolicy:
        return SemanticGovernedWritePolicy(self)

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
            migration_plan, migration_checkpoint,
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
                expected_projections.append(DeliveryCoordinateMigrationTargetProjection(
                    **values, projection_digest=sha256(encode_typed_value(values)).hexdigest()
                ))
        target_projections = tuple(expected_projections)
        legacy_records = sorted(
            (
                record for record in self._memory_plane.list_records()
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
            if any(self._memory_plane.get_record(record.memory_id) != record for record in (*persisted, *target_records)):
                raise SemanticWriterAdmissionError("completed migration generation is partial or mismatched")
            return current
        if not current_record.content.get("draining", False):
            self._memory_plane.conditionally_write_records(
                (_record(current, self._manifest, current_record.timestamp, draining=True),),
                preconditions=(RecordDigestPrecondition(
                    memory_id=current_record.memory_id, expected_digest=record_digest(current_record)
                ),),
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
            migration_plan, migration_checkpoint, migration_certificate, migration_activation, at
            , target_projections
        )
        self._memory_plane.conditionally_write_records(
            (
                _record(successor, self._manifest, at, migration_activation_digest=migration_activation.activation_digest),
                *migration_records,
                *target_records,
            ),
            preconditions=(
                RecordDigestPrecondition(memory_id=current_record.memory_id, expected_digest=record_digest(current_record)),
                *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in migration_records),
                *(RecordAbsentPrecondition(memory_id=record.memory_id) for record in target_records),
            ),
            authorization=authorization,
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
        governed = [
            record
            for record in records
            if record.source_kind == "semantic_ingestion_writer_admission"
            or record.source_kind in {
                "semantic_ingestion_source",
                "semantic_ingestion_metadata_poor_snapshot",
                "semantic_ingestion_admission_index",
                "semantic_ingestion_profile_selection",
                "semantic_ingestion_profile_verification",
                "semantic_ingestion_profile_outcome",
                "semantic_ingestion_legacy_delivery_record",
            }
            or record.source_kind.startswith("semantic_ingestion_preplanning")
            or record.source_kind.startswith("semantic_ingestion_generation")
            or record.source_kind.startswith("semantic_ingestion_migration")
            or record.source_kind == "semantic_ingestion_migrated_target"
            or record.memory_id == writer_admission_memory_id()
            or record.memory_id.startswith("semantic_ingestion:operation:")
            or record.memory_id.startswith("semantic_ingestion:artifact:")
            or record.memory_id.startswith("semantic_ingestion:generation:")
            or record.memory_id.startswith("semantic_ingestion:migration:")
            or record.memory_id.startswith("semantic_ingestion:migrated:")
        ]
        if not governed:
            return
        if not isinstance(authorization, SemanticWriterWriteAuthorization):
            raise SemanticWriterAdmissionError("governed semantic write is not authorized")
        if authorization.manifest != self._admissions._manifest:
            raise SemanticWriterAdmissionError("governed semantic manifest is mismatched")
        if authorization.lease_expires_at is not None and (
            authorization.server_now is None or authorization.lease_expires_at <= authorization.server_now()
        ):
            raise SemanticWriterAdmissionError("semantic write lease expired before storage CAS")
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
            migration_records = [record for record in governed if record.source_kind.startswith("semantic_ingestion_migration")]
            if (
                len(migration_records) < 4
                or
                manifest != current_manifest
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
        controls = [
            record
            for record in governed
            if record.content.get("semantic_ingestion_kind") == "preplanning_operation_control"
        ]
        if len(controls) != 1:
            raise SemanticWriterAdmissionError("governed semantic write lacks one atomic control record")
        try:
            binding = SemanticWriterCommitBinding.model_validate(controls[0].content["control"]["writer_binding"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SemanticWriterAdmissionError("governed semantic control binding is corrupt") from exc
        if binding != self._admissions.commit_binding(current_admission):
            raise SemanticWriterAdmissionError("governed semantic control binding is mismatched")
        operation_fence = OperationFenceBinding.model_validate(controls[0].content["control"]["operation_fence"])
        control_id = f"semantic_ingestion:operation:{operation_fence.operation_id}"
        prior_control = next((record for record in current if record.memory_id == control_id), None)
        if prior_control is None:
            if current_record.content.get("draining", False):
                raise SemanticWriterAdmissionError("retiring writer epoch is frozen to new operations")
            preplanning = [
                record for record in governed
                if record.source_kind.startswith("semantic_ingestion_preplanning")
            ]
            _validate_initial_preplanning_generation(preplanning, controls[0], operation_fence)
            admission_records = [record for record in governed if record not in preplanning]
            if admission_records:
                _validate_atomic_admission_records(admission_records, operation_fence, binding)
            return
        current_generation = [
            record
            for record in current
            if record.memory_id == control_id
            or record.memory_id.startswith(f"semantic_ingestion:artifact:{operation_fence.operation_id}:")
        ]
        _validate_initial_preplanning_generation(current_generation, prior_control, operation_fence)
        if len(governed) == 1 and controls[0].memory_id == control_id:
            return
        generation_records = [record for record in governed if record.memory_id.startswith(
            f"semantic_ingestion:generation:{operation_fence.operation_id}:"
        )]
        if len(generation_records) != len(governed) - 1:
            raise SemanticWriterAdmissionError("generation contains cross-operation governed records")
        manifests = [
            record for record in generation_records
            if record.content.get("semantic_ingestion_kind") == "generation_manifest"
        ]
        if len(manifests) != 1:
            raise SemanticWriterAdmissionError("generation requires exactly one manifest")
        member_records = [
            record for record in generation_records
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
            record.content.get("member", {}).get("kind") in {"graph_delta", "event_batch"}
            for record in member_records
        ):
            raise SemanticWriterAdmissionError("evidence-only writer cannot publish graph or event effects")


def _validate_initial_preplanning_generation(
    records: list[CanonicalMemoryRecord],
    control: CanonicalMemoryRecord,
    fence: OperationFenceBinding,
) -> None:
    operation_id = fence.operation_id
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
        f"semantic_ingestion:artifact:{operation_id}:{kind}": (
            f"preplanning_{kind}",
            value,
        )
        for kind, value in (
            ("introduction", introduction),
            ("index", index),
            ("closure", closure),
        )
    }
    expected_ids = {f"semantic_ingestion:operation:{operation_id}", *expected_artifacts}
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
    sources = [record for record in records if record.source_kind in {
        "semantic_ingestion_source", "semantic_ingestion_metadata_poor_snapshot"
    }]
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
    draining: bool = False,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=writer_admission_memory_id(),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "writer_admission",
            "admission": admission.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
            "migration_activation_digest": migration_activation_digest,
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
