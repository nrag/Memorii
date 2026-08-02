from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.delivery_coordinate_migration import (
    DeliveryCoordinateMigrationCheckpoint,
    DeliveryCoordinateMigrationEntry,
    DeliveryCoordinateMigrationError,
    activate_migration,
    build_migration_plan,
    certify_migration,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, record_digest
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from test_semantic_atomic_store import _handoff

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _target(record_id: str, source_epoch: int) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"semantic_ingestion:migrated:{source_epoch + 1}:{record_id}", domain=MemoryDomain.EXECUTION,
        text="", content={
            "legacy_record_id": record_id,
            "target_delivery_key_digest": sha256(f"t:{record_id}".encode()).hexdigest(),
            "target_generation": 7,
        }, status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_migrated_target", timestamp=NOW,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _legacy(record_id: str, source_epoch: int) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=record_id, domain=MemoryDomain.EXECUTION, text="",
        content={"source_writer_epoch": source_epoch, "legacy_delivery_bytes": record_id.encode()},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_legacy_delivery_record",
        timestamp=NOW, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _entry(record: CanonicalMemoryRecord, source_epoch: int) -> DeliveryCoordinateMigrationEntry:
    record_id = record.memory_id
    values = {
        "legacy_record_id": record_id,
        "legacy_evidence_digest": record_digest(record),
        "target_delivery_key_digest": sha256(f"t:{record_id}".encode()).hexdigest(),
        "migrated_state_digests": (record_digest(_target(record_id, source_epoch)),),
        "owner_disposition_digest": None,
    }
    return DeliveryCoordinateMigrationEntry(
        **values, entry_digest=sha256(encode_typed_value(values)).hexdigest()
    )


def _certified_activation(plane: MemoryPlaneService, source_epoch: int = 1):
    records = tuple(_legacy(f"legacy:{source_epoch}:{suffix}", source_epoch) for suffix in ("b", "a"))
    missing = tuple(record for record in records if plane.get_record(record.memory_id) is None)
    if missing:
        plane.write_records(missing)
    entries = tuple(_entry(record, source_epoch) for record in records)
    inventory = tuple(sorted((record.memory_id, record_digest(record)) for record in records))
    plan = build_migration_plan(
        migration_plan_id=f"plan:{source_epoch}", source_writer_epoch=source_epoch,
        legacy_snapshot_token=sha256(encode_typed_value(inventory)).hexdigest(),
        entries=entries,
    )
    completed = tuple(entry.entry_digest for entry in plan.entries)
    checkpoint_values = {
        "migration_plan_id": plan.migration_plan_id, "plan_digest": plan.plan_digest,
        "completed_entry_digests": completed, "target_generation": 7,
    }
    checkpoint = DeliveryCoordinateMigrationCheckpoint(
        **checkpoint_values, checkpoint_digest=sha256(encode_typed_value(checkpoint_values)).hexdigest()
    )
    certificate = certify_migration(plan, checkpoint, independent_verifier_fingerprint="verifier:v1")
    return plan, checkpoint, certificate, activate_migration(plan, certificate), tuple(
        _target(record_id, source_epoch) for record_id in plan.complete_legacy_record_ids
    )


def test_inventory_is_canonical_complete_and_certificate_activates_exact_target() -> None:
    plan, _, certificate, activation, _ = _certified_activation(MemoryPlaneService())
    assert plan.complete_legacy_record_ids == ("legacy:1:a", "legacy:1:b")
    assert certificate.verified_entry_digests == tuple(entry.entry_digest for entry in plan.entries)
    assert activation.target_writer_epoch == 2
    assert activation.target_generation == 7


def test_incomplete_target_generation_cannot_be_certified() -> None:
    plan, _, _, _, _ = _certified_activation(MemoryPlaneService())
    values = {
        "migration_plan_id": plan.migration_plan_id, "plan_digest": plan.plan_digest,
        "completed_entry_digests": (), "target_generation": 7,
    }
    checkpoint = DeliveryCoordinateMigrationCheckpoint(
        **values, checkpoint_digest=sha256(encode_typed_value(values)).hexdigest()
    )
    with pytest.raises(DeliveryCoordinateMigrationError, match="incomplete"):
        certify_migration(plan, checkpoint, independent_verifier_fingerprint="verifier:v1")


def test_cutover_is_monotonic_drained_and_stales_previous_binding() -> None:
    plane = MemoryPlaneService()
    plan, checkpoint, certificate, activation, targets = _certified_activation(plane)
    admissions = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    initial = admissions.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    old_binding = admissions.commit_binding(initial)
    successor = admissions.transition(
        expected=old_binding, admission_id="writer:2", runtime_mode="verified_semantic",
        writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
        migration_activation=activation,
        migration_plan=plan, migration_checkpoint=checkpoint, migration_certificate=certificate,
        target_records=targets,
    )
    assert successor.writer_epoch == 2
    assert successor.previous_admission_digest == initial.admission_digest
    with pytest.raises(SemanticWriterAdmissionError, match="stale"):
        admissions.require_current(old_binding)


def test_cutover_rejects_active_leases_and_rollback_is_forward_evidence_only_epoch() -> None:
    plane = MemoryPlaneService()
    plan, checkpoint, certificate, activation, targets = _certified_activation(plane)
    source_admission, _ = _handoff(plane)
    admissions = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    initial = admissions.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    atomic = SemanticIngestionAtomicStore(plane, admissions, now_provider=lambda: NOW)
    atomic._publish_preplanning(
        admission=source_admission, writer_binding=admissions.commit_binding(initial)
    )
    atomic.acquire_lease(
        operation_id=source_admission.operation_fence_binding.operation_id,
        writer_binding=admissions.commit_binding(initial), execution_token="old-owner",
        duration=timedelta(minutes=5),
    )
    with pytest.raises(SemanticWriterAdmissionError, match="not drained"):
        admissions.transition(
            expected=admissions.commit_binding(initial), admission_id="writer:2", runtime_mode="verified_semantic",
            writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
            migration_activation=activation,
            migration_plan=plan, migration_checkpoint=checkpoint, migration_certificate=certificate,
            target_records=targets,
        )
    # A separate drained repository can activate and then roll back by advancing again.
    drained_plane = MemoryPlaneService()
    drained_plan, drained_checkpoint, drained_certificate, drained_activation, drained_targets = _certified_activation(drained_plane)
    rollback_plan, rollback_checkpoint, rollback_certificate, rollback_activation, rollback_targets = _certified_activation(drained_plane, 2)
    legacy_plan, legacy_checkpoint, legacy_certificate, legacy_activation, legacy_targets = _certified_activation(drained_plane, 3)
    drained = SemanticWriterAdmissionStore(drained_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    drained_initial = drained.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    cutover = drained.transition(
        expected=drained.commit_binding(drained_initial), admission_id="writer:2", runtime_mode="verified_semantic",
        writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2", migration_activation=drained_activation,
        migration_plan=drained_plan, migration_checkpoint=drained_checkpoint, migration_certificate=drained_certificate,
        target_records=drained_targets,
    )
    rollback = drained.transition(
        expected=drained.commit_binding(cutover), admission_id="writer:3", runtime_mode="evidence_only",
        writer_implementation_fingerprint="safe", graph_schema_fingerprint="schema:2",
        migration_activation=rollback_activation,
        migration_plan=rollback_plan, migration_checkpoint=rollback_checkpoint,
        migration_certificate=rollback_certificate, target_records=rollback_targets,
    )
    assert rollback.writer_epoch == 3
    with pytest.raises(SemanticWriterAdmissionError, match="legacy"):
        drained.transition(
            expected=drained.commit_binding(rollback), admission_id="writer:4", runtime_mode="legacy_pre_cutover",
            writer_implementation_fingerprint="legacy", graph_schema_fingerprint="schema:1",
            migration_activation=legacy_activation,
            migration_plan=legacy_plan, migration_checkpoint=legacy_checkpoint,
            migration_certificate=legacy_certificate, target_records=legacy_targets,
        )


def test_jsonl_cutover_persists_certified_migration_and_reopens_current_epoch(tmp_path) -> None:
    path = tmp_path / "migration"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    plan, checkpoint, certificate, activation, targets = _certified_activation(plane)
    admissions = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    initial = admissions.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    successor = admissions.transition(
        expected=admissions.commit_binding(initial), admission_id="writer:2", runtime_mode="verified_semantic",
        writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
        migration_activation=activation, migration_plan=plan, migration_checkpoint=checkpoint,
        migration_certificate=certificate, target_records=targets,
    )
    assert len([record for record in plane.list_records() if record.source_kind.startswith("semantic_ingestion_migration")]) == 6
    assert len([record for record in plane.list_records() if record.source_kind == "semantic_ingestion_migrated_target"]) == 2
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = SemanticWriterAdmissionStore(reopened_plane, bounded_preplanning_ownership_manifest())
    assert reopened.current() == successor
    assert tuple(reopened_plane.get_record(record.memory_id) for record in targets) == targets


def test_jsonl_cutover_failure_is_prior_state_and_lost_ack_retry_recovers(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed_path = tmp_path / "failed-cutover"
    failed_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(failed_path))
    plan, checkpoint, certificate, activation, targets = _certified_activation(failed_plane)
    failed = SemanticWriterAdmissionStore(failed_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    initial = failed.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    monkeypatch.setattr(
        "memorii.core.memory_plane.store.os.replace",
        lambda source, target: (_ for _ in ()).throw(OSError("cutover replace failure")),
    )
    with pytest.raises(OSError, match="cutover replace failure"):
        failed.transition(
            expected=failed.commit_binding(initial), admission_id="writer:2", runtime_mode="verified_semantic",
            writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
            migration_activation=activation, migration_plan=plan, migration_checkpoint=checkpoint,
            migration_certificate=certificate, target_records=targets,
        )
    monkeypatch.undo()
    failed_reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(failed_path))
    failed_reopened = SemanticWriterAdmissionStore(failed_reopened_plane, bounded_preplanning_ownership_manifest())
    assert failed_reopened.current() == initial
    assert not any(record.source_kind.startswith("semantic_ingestion_migration") for record in failed_reopened_plane.list_records())

    ack_path = tmp_path / "lost-ack-cutover"
    ack_store = JsonlMemoryPlaneStore(ack_path)
    ack_plane = MemoryPlaneService(record_store=ack_store)
    ack_plan, ack_checkpoint, ack_certificate, ack_activation, ack_targets = _certified_activation(ack_plane)
    admissions = SemanticWriterAdmissionStore(ack_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    old = admissions.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    original_apply = ack_store.apply_batch
    calls = [0]

    def fail_second_ack(*args, **kwargs):
        calls[0] += 1
        result = original_apply(*args, **kwargs)
        if calls[0] == 2:
            raise OSError("cutover lost acknowledgement")
        return result

    monkeypatch.setattr(ack_store, "apply_batch", fail_second_ack)
    with pytest.raises(OSError, match="lost acknowledgement"):
        admissions.transition(
            expected=admissions.commit_binding(old), admission_id="writer:2", runtime_mode="verified_semantic",
            writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
            migration_activation=ack_activation, migration_plan=ack_plan, migration_checkpoint=ack_checkpoint,
            migration_certificate=ack_certificate, target_records=ack_targets,
        )
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(ack_path))
    reopened = SemanticWriterAdmissionStore(reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    successor = reopened.transition(
        expected=reopened.commit_binding(old), admission_id="writer:2", runtime_mode="verified_semantic",
        writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
        migration_activation=ack_activation, migration_plan=ack_plan, migration_checkpoint=ack_checkpoint,
        migration_certificate=ack_certificate, target_records=ack_targets,
    )
    assert successor.writer_epoch == 2


def test_cutover_rejects_duplicate_target_coordinate() -> None:
    plane = MemoryPlaneService()
    plan, checkpoint, certificate, activation, targets = _certified_activation(plane)
    admissions = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    initial = admissions.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    duplicate_key = targets[0].content["target_delivery_key_digest"]
    duplicate_target = targets[1].model_copy(update={
        "content": {**targets[1].content, "target_delivery_key_digest": duplicate_key}
    })
    second_entry = plan.entries[1]
    second_values = {
        **second_entry.model_dump(mode="python", exclude={"entry_digest", "migrated_state_digests", "target_delivery_key_digest"}),
        "target_delivery_key_digest": duplicate_key,
        "migrated_state_digests": (record_digest(duplicate_target),),
    }
    mutated_entry = DeliveryCoordinateMigrationEntry(
        **second_values, entry_digest=sha256(encode_typed_value(second_values)).hexdigest()
    )
    collision_plan = build_migration_plan(
        migration_plan_id="collision", source_writer_epoch=1, legacy_snapshot_token=plan.legacy_snapshot_token,
        entries=(plan.entries[0], mutated_entry),
    )
    completed = tuple(entry.entry_digest for entry in collision_plan.entries)
    checkpoint_values = {
        "migration_plan_id": collision_plan.migration_plan_id, "plan_digest": collision_plan.plan_digest,
        "completed_entry_digests": completed, "target_generation": 7,
    }
    collision_checkpoint = DeliveryCoordinateMigrationCheckpoint(
        **checkpoint_values, checkpoint_digest=sha256(encode_typed_value(checkpoint_values)).hexdigest()
    )
    collision_certificate = certify_migration(collision_plan, collision_checkpoint, independent_verifier_fingerprint="v")
    before = plane.list_records()
    with pytest.raises(SemanticWriterAdmissionError, match="collision"):
        admissions.transition(
            expected=admissions.commit_binding(initial), admission_id="writer:2", runtime_mode="verified_semantic",
            writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
            migration_activation=activate_migration(collision_plan, collision_certificate),
            migration_plan=collision_plan, migration_checkpoint=collision_checkpoint,
            migration_certificate=collision_certificate, target_records=(targets[0], duplicate_target),
        )
    assert plane.list_records() == before


def test_cutover_rejects_missing_target_generation_before_freezing_writer() -> None:
    plane = MemoryPlaneService()
    plan, checkpoint, certificate, activation, _ = _certified_activation(plane)
    admissions = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    initial = admissions.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    before = plane.list_records()
    with pytest.raises(SemanticWriterAdmissionError, match="target generation"):
        admissions.transition(
            expected=admissions.commit_binding(initial), admission_id="writer:2", runtime_mode="verified_semantic",
            writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
            migration_activation=activation, migration_plan=plan, migration_checkpoint=checkpoint,
            migration_certificate=certificate, target_records=(),
        )
    assert plane.list_records() == before
