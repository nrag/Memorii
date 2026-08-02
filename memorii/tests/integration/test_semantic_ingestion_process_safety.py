from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path

from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.delivery_coordinate_migration import (
    DeliveryCoordinateMigrationCheckpoint,
    activate_migration,
    build_migration_plan,
    certify_migration,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


def _publish(path: str, delivery_id: str, operation_id: str, queue, barrier) -> None:
    try:
        plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
        principal = DeliveryPrincipalBinding.create(
            principal_subject_id="principal:a", tenant_partition_id="tenant:a", provider_identity="provider:test"
        )
        identity = DeliveryIdentity.create(principal, delivery_id)
        source = CanonicalMemoryRecord(
            memory_id=f"tx:{delivery_id}", domain=MemoryDomain.TRANSCRIPT, text="source",
            content={"text": "source"}, status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_source", timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            is_raw_event=True, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        ingress = AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            required_outcome_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
            current_authorized_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
        )
        queue.put(("ready", operation_id))
        if not barrier.wait(timeout=20):
            raise RuntimeError("process contention barrier timed out")
        admission = GovernedSourceAdmissionService(plane).admit(
            source=source, delivery_identity=identity, ingress=ingress,
            operation_id=operation_id, evidence_only=True,
        )
        writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
        current = writers.create_initial_evidence_only(
            admission_id="m2", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
        )
        publication = SemanticIngestionAtomicStore(plane, writers)._publish_preplanning(
            admission=admission, writer_binding=writers.commit_binding(current)
        )
        queue.put(("ok", publication.model_dump_json()))
    except Exception as exc:  # process boundary reports the exact failure to the parent
        queue.put(("error", f"{type(exc).__name__}:{exc}"))


def _run_pair(path: Path, args: tuple[tuple[str, str], tuple[str, str]]):
    context = get_context("spawn")
    queue = context.Queue()
    barrier = context.Event()
    processes = [
        context.Process(target=_publish, args=(str(path), delivery, operation, queue, barrier))
        for delivery, operation in args
    ]
    for process in processes:
        process.start()
    ready = [queue.get(timeout=20) for _ in processes]
    assert all(status == "ready" for status, _ in ready)
    barrier.set()
    results = [queue.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    return results


def test_two_processes_same_delivery_publish_one_byte_identical_generation(tmp_path: Path) -> None:
    results = _run_pair(tmp_path / "same", (("one", "op:one"), ("one", "op:one")))
    assert [status for status, _ in results] == ["ok", "ok"]
    assert results[0][1] == results[1][1]
    records = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "same")).list_records()
    assert len([record for record in records if record.source_kind == "semantic_ingestion_preplanning_control"]) == 1
    assert len([record for record in records if record.source_kind == "semantic_ingestion_preplanning_artifact"]) == 3


def test_two_processes_distinct_deliveries_do_not_lose_updates(tmp_path: Path) -> None:
    results = _run_pair(tmp_path / "distinct", (("one", "op:one"), ("two", "op:two")))
    assert [status for status, _ in results] == ["ok", "ok"]
    records = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "distinct")).list_records()
    assert len([record for record in records if record.source_kind == "semantic_ingestion_preplanning_control"]) == 2
    assert len([record for record in records if record.source_kind == "semantic_ingestion_preplanning_artifact"]) == 6


def _paused_old_epoch_admission(path: str, ready, release, queue) -> None:
    try:
        plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
        writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
        old_binding = writers.commit_binding(writers.current())
        principal = DeliveryPrincipalBinding.create(
            principal_subject_id="principal:a", tenant_partition_id="tenant:a", provider_identity="provider:test"
        )
        identity = DeliveryIdentity.create(principal, "delivery:stale")
        source = CanonicalMemoryRecord(
            memory_id="tx:stale", domain=MemoryDomain.TRANSCRIPT, text="source", content={"text": "source"},
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC), is_raw_event=True,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        prepared = GovernedSourceAdmissionService(plane).prepare_atomic(
            source=source, delivery_identity=identity,
            ingress=AuthenticatedIngressContext(
                delivery_principal_binding=principal,
                required_outcome_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
                current_authorized_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
            ),
            operation_id="op:stale", evidence_only=True,
        )
        ready.set()
        if not release.wait(timeout=20):
            raise RuntimeError("cross-cutover release timed out")
        SemanticIngestionAtomicStore(plane, writers).admit_source(prepared=prepared, writer_binding=old_binding)
        queue.put(("unexpected_success", ""))
    except Exception as exc:  # process boundary reports the exact stale-writer failure
        queue.put((type(exc).__name__, str(exc)))


def test_paused_old_epoch_process_cannot_publish_after_shared_store_cutover(tmp_path: Path) -> None:
    path = tmp_path / "cutover"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    initial = writers.create_initial_evidence_only(
        admission_id="writer:1", writer_implementation_fingerprint="old", graph_schema_fingerprint="schema:1"
    )
    context = get_context("spawn")
    ready, release, queue = context.Event(), context.Event(), context.Queue()
    process = context.Process(target=_paused_old_epoch_admission, args=(str(path), ready, release, queue))
    process.start()
    assert ready.wait(timeout=20)
    plan = build_migration_plan(
        migration_plan_id="plan:cutover", source_writer_epoch=1,
        legacy_snapshot_token=sha256(encode_typed_value(())).hexdigest(), entries=(),
    )
    checkpoint_values = {
        "migration_plan_id": plan.migration_plan_id, "plan_digest": plan.plan_digest,
        "completed_entry_digests": (), "target_generation": 1,
    }
    checkpoint = DeliveryCoordinateMigrationCheckpoint(
        **checkpoint_values,
        checkpoint_digest=sha256(encode_typed_value(checkpoint_values)).hexdigest(),
    )
    certificate = certify_migration(plan, checkpoint, independent_verifier_fingerprint="verifier")
    activation = activate_migration(plan, certificate)
    successor = writers.transition(
        expected=writers.commit_binding(initial), admission_id="writer:2", runtime_mode="verified_semantic",
        writer_implementation_fingerprint="new", graph_schema_fingerprint="schema:2",
        migration_activation=activation, migration_plan=plan, migration_checkpoint=checkpoint,
        migration_certificate=certificate, target_records=(),
    )
    after_cutover = JsonlMemoryPlaneStore(path).read_snapshot()
    release.set()
    error_type, message = queue.get(timeout=20)
    process.join(timeout=20)
    assert process.exitcode == 0
    assert error_type == "SemanticWriterAdmissionError" and "stale" in message
    assert JsonlMemoryPlaneStore(path).read_snapshot() == after_cutover
    assert writers.current() == successor
