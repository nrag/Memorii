from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event, Lock, Thread

import pytest
from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService, SourceAdmissionAccepted
from memorii.core.memory_evolution.atomic_store import (
    BootstrapPreparedPublishedAuthorityUnavailable,
    BootstrapRetainedPendingAuthorityUnavailable,
    BootstrapWriterHandoffMarkerV3,
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapAuthenticatedLanguageEvidence,
    CurrentBootstrapReleaseAssertion,
    HostVerifiedBootstrapReleaseEvidence,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    CanonicalTypedValueError,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.source_admission import DeliveryAuthorizationRequest
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    MemoryPlaneCorruptionError,
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


def _handoff(plane: MemoryPlaneService) -> tuple[SourceAdmissionAccepted, OperationFenceBinding]:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a", tenant_partition_id="tenant:a", provider_identity="provider:test"
    )
    identity = DeliveryIdentity.create(principal, "delivery:one")
    source = CanonicalMemoryRecord(
        memory_id="tx:one",
        domain=MemoryDomain.TRANSCRIPT,
        text="source",
        content={"text": "source"},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_source",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
    )
    admission = GovernedSourceAdmissionService(plane).admit(
        source=source, delivery_identity=identity, ingress=ingress, operation_id="op:one", evidence_only=True
    )
    return admission, OperationFenceBinding.create(
        operation_id="op:one",
        source_id=admission.source_id,
        source_digest=admission.source_digest,
        delivery_identity=identity,
    )


def test_preplanning_publication_is_atomic_idempotent_and_has_empty_future_effect_sets() -> None:
    backing_store = InMemoryMemoryPlaneStore()
    plane = MemoryPlaneService(record_store=backing_store)
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="writer-admission",
            writer_implementation_fingerprint="writer-fingerprint",
            graph_schema_fingerprint="schema-fingerprint",
        )
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    first = store._publish_preplanning(admission=admission, writer_binding=binding)
    second = store._publish_preplanning(admission=admission, writer_binding=binding)

    assert first == second
    assert first.operation.graph_record_ids == first.operation.event_ids == first.operation.terminal_group_ids == ()
    assert len([r for r in plane.list_records() if r.source_kind == "semantic_ingestion_preplanning_artifact"]) == 3


def test_same_public_operation_id_has_distinct_fence_derived_writer_namespaces() -> None:
    plane = MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="writer-admission", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    store = SemanticIngestionAtomicStore(plane, writers)
    prepared_admissions = []
    for suffix in ("alice", "bob"):
        principal = DeliveryPrincipalBinding.create(
            principal_subject_id=f"principal:{suffix}", tenant_partition_id=f"tenant:{suffix}",
            provider_identity="provider:test",
        )
        identity = DeliveryIdentity.create(principal, "same-public-delivery")
        source = CanonicalMemoryRecord(
            memory_id=f"tx:{suffix}", domain=MemoryDomain.TRANSCRIPT, text="source", content={"text": "source"},
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC), is_raw_event=True,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        ingress = AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            required_outcome_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id=f"tenant:{suffix}", scopes=set()
            ),
            current_authorized_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id=f"tenant:{suffix}", scopes=set()
            ),
        )
        prepared_admissions.append(GovernedSourceAdmissionService(plane).prepare_atomic(
            source=source, delivery_identity=identity, ingress=ingress, operation_id="same-public-operation",
            evidence_only=True,
        ))
    publications = tuple(
        store.admit_source(prepared=prepared, writer_binding=binding) for prepared in prepared_admissions
    )
    assert publications[0].operation.operation_fence.operation_id == publications[1].operation.operation_fence.operation_id
    assert publications[0].operation.operation_fence.operation_fence_id != publications[1].operation.operation_fence.operation_fence_id
    control_ids = [record.memory_id for record in plane.list_records() if record.source_kind == "semantic_ingestion_preplanning_control"]
    assert len(control_ids) == len(set(control_ids)) == 2
    leased = tuple(
        store.acquire_lease(
            operation_fence=publication.operation.operation_fence,
            writer_binding=binding,
            execution_token=f"worker:{index}",
            duration=timedelta(minutes=1),
        )
        for index, publication in enumerate(publications)
    )
    assert tuple(
        store.get_operation(publication.operation.operation_fence) for publication in publications
    ) == leased
    with pytest.raises(PreplanningStoreError, match="absent or ambiguous"):
        store.acquire_lease(
            operation_id="same-public-operation",
            writer_binding=binding,
            execution_token="ambiguous",
            duration=timedelta(minutes=1),
        )


def test_unadmitted_or_mismatched_handoff_changes_no_record_set() -> None:
    plane = MemoryPlaneService()
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="writer-admission",
            writer_implementation_fingerprint="writer-fingerprint",
            graph_schema_fingerprint="schema-fingerprint",
        )
    )
    store = SemanticIngestionAtomicStore(plane, writers)
    bad = fence.model_copy(update={"source_id": "tx:other"})
    before = plane.list_records()

    with pytest.raises((PreplanningStoreError, ValueError)):
        store._publish_preplanning(
            admission=admission.model_copy(update={"operation_fence_binding": bad}), writer_binding=binding
        )

    assert plane.list_records() == before


def test_substituted_required_scope_tenant_changes_no_record_set() -> None:
    plane = MemoryPlaneService()
    admission, _ = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="writer-admission",
            writer_implementation_fingerprint="writer-fingerprint",
            graph_schema_fingerprint="schema-fingerprint",
        )
    )
    store = SemanticIngestionAtomicStore(plane, writers)
    substituted = admission.model_copy(
        update={
            "required_outcome_scopes": RequiredOutcomeScopeSet.create(
                tenant_partition_id="tenant:b",
                scopes=set(),
            )
        }
    )
    before = plane.list_records()

    with pytest.raises(PreplanningStoreError):
        store._publish_preplanning(admission=substituted, writer_binding=binding)

    assert plane.list_records() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_mode", "verified_semantic"),
        ("writer_implementation_fingerprint", "wrong-writer"),
        ("graph_schema_fingerprint", "wrong-schema"),
        ("expected_writer_epoch", 2),
        ("admission_digest", "0" * 64),
    ],
)
def test_invalid_complete_writer_binding_changes_no_revision_or_record_set(field: str, value: object) -> None:
    backing_store = InMemoryMemoryPlaneStore()
    plane = MemoryPlaneService(record_store=backing_store)
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="writer-admission",
            writer_implementation_fingerprint="writer-fingerprint",
            graph_schema_fingerprint="schema-fingerprint",
        )
    )
    store = SemanticIngestionAtomicStore(plane, writers)
    before = backing_store.read_snapshot()

    with pytest.raises(SemanticWriterAdmissionError):
        store._publish_preplanning(admission=admission, writer_binding=binding.model_copy(update={field: value}))

    assert backing_store.read_snapshot() == before


def test_jsonl_reopen_recovers_byte_identical_preplanning_publication(tmp_path: Path) -> None:
    path = tmp_path / "semantic-ingestion"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="writer-admission",
            writer_implementation_fingerprint="writer-fingerprint",
            graph_schema_fingerprint="schema-fingerprint",
        )
    )
    first = SemanticIngestionAtomicStore(
        plane, writers, now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )._publish_preplanning(admission=admission, writer_binding=binding)

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened_writers = SemanticWriterAdmissionStore(reopened_plane, bounded_preplanning_ownership_manifest())
    reopened = SemanticIngestionAtomicStore(
        reopened_plane, reopened_writers, now_provider=lambda: datetime(2026, 1, 2, tzinfo=UTC)
    )._publish_preplanning(admission=admission, writer_binding=binding)
    assert reopened == first


def test_independent_jsonl_instances_linearize_same_absent_record_race(
    tmp_path: Path,
) -> None:
    path = tmp_path / "independent-race"
    stores = (JsonlMemoryPlaneStore(path), JsonlMemoryPlaneStore(path))
    barrier = Barrier(2)
    lock = Lock()
    outcomes: list[tuple[str, str]] = []

    def compete(index: int) -> None:
        record = CanonicalMemoryRecord(
            memory_id="race:winner",
            domain=MemoryDomain.TRANSCRIPT,
            text=f"writer-{index}",
            content={"writer": index},
            status=CommitStatus.COMMITTED,
            source_kind="test_race",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        barrier.wait()
        try:
            stores[index].apply_batch(
                (record,),
                expected_revision=None,
                preconditions=(
                    RecordAbsentPrecondition(memory_id=record.memory_id),
                ),
            )
            outcome = ("committed", record.text)
        except MemoryPlaneRevisionConflictError:
            outcome = ("conflict", record.text)
        with lock:
            outcomes.append(outcome)

    threads = tuple(Thread(target=compete, args=(index,)) for index in range(2))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(value for value, _ in outcomes) == ["committed", "conflict"]
    _, records = JsonlMemoryPlaneStore(path).read_snapshot()
    winner = next(record for record in records if record.memory_id == "race:winner")
    assert winner.text == next(text for status, text in outcomes if status == "committed")


def test_jsonl_transaction_barrier_rechecks_freeze_after_request_construction(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transaction-barrier"
    writer = JsonlMemoryPlaneStore(path)
    observer = JsonlMemoryPlaneStore(path)
    entered = Event()
    release = Event()
    frozen = Event()
    failures: list[str] = []
    record = CanonicalMemoryRecord(
        memory_id="barrier:terminal",
        domain=MemoryDomain.TRANSCRIPT,
        text="terminal",
        content={"state": "prepared"},
        status=CommitStatus.COMMITTED,
        source_kind="test_barrier",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    def freeze_guard() -> None:
        entered.set()
        release.wait(timeout=5)
        if frozen.is_set():
            raise ValueError("semantic writes are frozen")

    def commit() -> None:
        try:
            writer.apply_batch(
                (record,),
                expected_revision=None,
                preconditions=(
                    RecordAbsentPrecondition(memory_id=record.memory_id),
                ),
                transaction_precondition=freeze_guard,
            )
        except ValueError as exc:
            failures.append(str(exc))

    thread = Thread(target=commit)
    thread.start()
    assert entered.wait(timeout=5)
    frozen.set()
    release.set()
    thread.join(timeout=5)

    assert failures == ["semantic writes are frozen"]
    assert all(
        item.memory_id != record.memory_id for item in observer.read_snapshot()[1]
    )


class _LostAckStore(InMemoryMemoryPlaneStore):
    armed = False

    def apply_batch(self, *args, **kwargs):
        result = super().apply_batch(*args, **kwargs)
        if self.armed:
            self.armed = False
            raise RuntimeError("simulated lost acknowledgement")
        return result


def test_lost_ack_retry_returns_exact_committed_preplanning_generation() -> None:
    backend = _LostAckStore()
    plane = MemoryPlaneService(record_store=backend)
    admission, _ = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="writer-admission", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    store = SemanticIngestionAtomicStore(plane, writers)
    backend.armed = True
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        store._publish_preplanning(admission=admission, writer_binding=binding)
    recovered = store._publish_preplanning(admission=admission, writer_binding=binding)
    assert recovered.operation.operation_fence.operation_id == "op:one"
    assert len([record for record in plane.list_records() if record.source_kind == "semantic_ingestion_preplanning_artifact"]) == 3


def test_jsonl_replace_failure_preserves_prior_complete_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "failpoint"
    backend = JsonlMemoryPlaneStore(path)
    plane = MemoryPlaneService(record_store=backend)
    admission, _ = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="writer-admission", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    before = JsonlMemoryPlaneStore(path).read_snapshot()
    monkeypatch.setattr(backend, "_replace_batches", lambda batches: (_ for _ in ()).throw(RuntimeError("failpoint")))
    with pytest.raises(RuntimeError, match="failpoint"):
        SemanticIngestionAtomicStore(plane, writers)._publish_preplanning(admission=admission, writer_binding=binding)
    assert JsonlMemoryPlaneStore(path).read_snapshot() == before


def test_jsonl_truncated_batch_blocks_reopen_instead_of_exposing_partial_state(tmp_path: Path) -> None:
    path = tmp_path / "corrupt"
    backend = JsonlMemoryPlaneStore(path)
    plane = MemoryPlaneService(record_store=backend)
    admission, _ = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="writer-admission", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    SemanticIngestionAtomicStore(plane, writers)._publish_preplanning(admission=admission, writer_binding=binding)
    records_path = path / "memory_records.jsonl"
    records_path.write_bytes(records_path.read_bytes()[:-1])
    with pytest.raises(MemoryPlaneCorruptionError, match="incomplete"):
        JsonlMemoryPlaneStore(path).read_snapshot()


def test_atomic_admission_publishes_source_evidence_and_pending_generation_together() -> None:
    plane = MemoryPlaneService()
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a", tenant_partition_id="tenant:a", provider_identity="provider:test"
    )
    identity = DeliveryIdentity.create(principal, "delivery:atomic")
    source = CanonicalMemoryRecord(
        memory_id="tx:atomic", domain=MemoryDomain.TRANSCRIPT, text="source", content={"text": "source"},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC), is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
    )
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="writer-admission", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    prepared = GovernedSourceAdmissionService(plane).prepare_atomic(
        source=source, delivery_identity=identity, ingress=ingress,
        operation_id="op:atomic", evidence_only=True,
    )
    store = SemanticIngestionAtomicStore(plane, writers)
    with pytest.raises(PreplanningStoreError, match="atomic source admission"):
        store.publish_preplanning(admission=prepared.accepted, writer_binding=binding)
    first = store.admit_source(prepared=prepared, writer_binding=binding)
    second = store.admit_source(prepared=prepared, writer_binding=binding)
    assert first == second
    assert all(plane.get_record(record.memory_id) == record for record in prepared.records)
    assert len([record for record in plane.list_records() if record.source_kind == "semantic_ingestion_preplanning_artifact"]) == 3


def test_authorization_rotation_preserves_delivery_fence_and_allocation_identity() -> None:
    plane = MemoryPlaneService()
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a", tenant_partition_id="tenant:a", provider_identity="provider:test"
    )
    identity = DeliveryIdentity.create(principal, "delivery:rotation")
    source = CanonicalMemoryRecord(
        memory_id="tx:rotation", domain=MemoryDomain.TRANSCRIPT, text="source", content={"text": "source"},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC), is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    service = GovernedSourceAdmissionService(plane)
    first = service.admit(
        source=source, delivery_identity=identity,
        ingress=AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            required_outcome_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
            current_authorized_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
        ),
        operation_id="op:rotation", evidence_only=True,
    )
    rotated = service.admit(
        source=source, delivery_identity=identity,
        ingress=AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            required_outcome_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
            current_authorized_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id="tenant:a", scopes={"session:new-authority"}
            ),
        ),
        operation_id="op:rotation", evidence_only=True,
    )
    assert rotated.delivery_identity == first.delivery_identity
    assert rotated.operation_fence_binding == first.operation_fence_binding
    assert rotated.operation_fence_binding.allocation_namespace_id == first.operation_fence_binding.allocation_namespace_id


def test_ctv_encoder_still_rejects_raw_delivery_identity_models() -> None:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a",
        tenant_partition_id="tenant:a",
        provider_identity="provider:test",
    )
    identity = DeliveryIdentity.create(principal, "delivery:raw-model")

    with pytest.raises(CanonicalTypedValueError, match="canonical_value_type_invalid"):
        encode_typed_value(identity)


def test_bootstrap_writer_handoff_marker_v3_create_lowers_typed_nested_members() -> None:
    plane = MemoryPlaneService()
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="writer-admission",
            writer_implementation_fingerprint="writer",
            graph_schema_fingerprint="schema",
        )
    )

    marker = BootstrapWriterHandoffMarkerV3.create(
        schema_version=3,
        source_id=admission.source_id,
        source_digest=admission.source_digest,
        handoff_request_digest="1" * 64,
        recovery_key_digest="2" * 64,
        expected_predecessor_operation_generation=1,
        expected_predecessor_artifact_generation=1,
        expected_predecessor_control_digest="8" * 64,
        prepared_generation=1,
        prepared_source_digest="3" * 64,
        authority_pin_digest="4" * 64,
        release_evidence_digest="5" * 64,
        bootstrap_language_evidence_digest="6" * 64,
        delivery_identity=fence.delivery_identity,
        operation_fence_binding=fence,
        writer_commit_binding=binding,
        pending_operation_id=fence.operation_fence_id,
        pending_operation_digest="7" * 64,
    )

    assert BootstrapWriterHandoffMarkerV3.model_validate(marker.model_dump(mode="python")) == marker


@pytest.mark.parametrize("durable", (False, True))
@pytest.mark.parametrize("prepared", (False, True))
def test_bootstrap_authority_unavailable_terminals_are_exactly_idempotent_and_reopen(
    tmp_path: Path, durable: bool, prepared: bool
) -> None:
    plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "bootstrap") if durable else InMemoryMemoryPlaneStore()
    )
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    writers.create_initial_evidence_only(
        admission_id="writer-admission", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    )
    store = SemanticIngestionAtomicStore(plane, writers)
    common = {
        "source_id": admission.source_id,
        "source_digest": admission.source_digest,
        "authority_pin_digest": "1" * 64,
        "release_evidence_digest": "2" * 64,
        "bootstrap_language_evidence_digest": "3" * 64,
        "delivery_identity": fence.delivery_identity,
        "operation_fence_binding": fence,
    }
    terminal = (
        BootstrapPreparedPublishedAuthorityUnavailable.create(
            **common, prepared_generation=1, prepared_source_digest="4" * 64, reason="release_unavailable"
        )
        if prepared
        else BootstrapRetainedPendingAuthorityUnavailable.create(**common, reason="pin_mismatch")
    )
    assert store._persist_bootstrap_authority_terminal_if_absent(terminal) == terminal
    assert store._persist_bootstrap_authority_terminal_if_absent(terminal) == terminal
    before_retry = tuple(plane.list_records())
    rejected_write = CanonicalMemoryRecord(
        memory_id="bootstrap:must-not-reopen",
        domain=MemoryDomain.TRANSCRIPT,
        text="",
        content={},
        status=CommitStatus.COMMITTED,
        source_kind="test_bootstrap_authority_terminal",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    with pytest.raises(MemoryPlaneRevisionConflictError, match="record_absent"):
        plane.conditionally_write_records(
            (rejected_write,),
            preconditions=(
                RecordAbsentPrecondition(memory_id=rejected_write.memory_id),
                RecordAbsentPrecondition(
                    memory_id=store._bootstrap_authority_terminal_record_id(
                        admission.source_id
                    )
                ),
            ),
        )
    assert tuple(plane.list_records()) == before_retry
    if durable:
        reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "bootstrap"))
        reopened = SemanticIngestionAtomicStore(
            reopened_plane,
            SemanticWriterAdmissionStore(reopened_plane, bounded_preplanning_ownership_manifest()),
        )
        assert reopened._load_bootstrap_authority_terminal(
            source_id=admission.source_id, source_digest=admission.source_digest
        ) == terminal
    else:
        assert store._load_bootstrap_authority_terminal(
            source_id=admission.source_id, source_digest=admission.source_digest
        ) == terminal


def test_current_bootstrap_release_verifier_is_invoked_for_each_exact_phase() -> None:
    plane = MemoryPlaneService()
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    evidence = HostVerifiedBootstrapReleaseEvidence.model_construct(
        coordinate=BOOTSTRAP_COORDINATE,
        signed_release_digest="1" * 64,
        bootstrap_anchor_digest="2" * 64,
        external_root_digest="3" * 64,
        active_lifecycle_snapshot_digest="4" * 64,
        lifecycle_state="active",
        verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        evidence_digest="5" * 64,
    )
    language = BootstrapAuthenticatedLanguageEvidence.model_construct(
        source_id=admission.source_id,
        source_digest=admission.source_digest,
        delivery_principal_binding_digest=fence.delivery_identity.delivery_principal_binding_digest,
    )

    class Verifier:
        phases: list[str] = []

        def assert_current(self, *, authorization, release_evidence, assertion_phase):
            self.phases.append(assertion_phase)
            return CurrentBootstrapReleaseAssertion.model_construct(
                coordinate=release_evidence.coordinate,
                signed_release_digest=release_evidence.signed_release_digest,
                bootstrap_anchor_digest=release_evidence.bootstrap_anchor_digest,
                active_lifecycle_snapshot_digest=release_evidence.active_lifecycle_snapshot_digest,
                assertion_phase=assertion_phase,
                assertion_nonce=assertion_phase,
                assertion_digest="6" * 64,
            )

    verifier = Verifier()
    store = SemanticIngestionAtomicStore(plane, writers, current_bootstrap_release_verifier=verifier)
    authorization = DeliveryAuthorizationRequest(
        delivery_identity=fence.delivery_identity,
        ingress=AuthenticatedIngressContext(
            delivery_principal_binding=DeliveryPrincipalBinding.create(
                principal_subject_id="principal:a", tenant_partition_id="tenant:a", provider_identity="provider:test"
            ),
            required_outcome_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
            current_authorized_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:a", scopes=set()),
        ),
    )
    # The host fixture intentionally returns an unchecked model_construct()
    # value.  A final release check must fail closed instead of trusting it.
    assert not store._current_bootstrap_access_is_valid(
        authorization=authorization, release_evidence=evidence, assertion_phase="prepared_publication",
        expected_delivery_identity=fence.delivery_identity, language_evidence=language,
    )
    assert verifier.phases == ["prepared_publication"]


@pytest.mark.parametrize("durable", (False, True))
def test_final_bootstrap_release_recheck_fails_closed_before_any_write(
    tmp_path: Path, durable: bool
) -> None:
    plane = MemoryPlaneService(
        record_store=(
            JsonlMemoryPlaneStore(tmp_path / "final-release-check")
            if durable
            else InMemoryMemoryPlaneStore()
        )
    )
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    writers.create_initial_evidence_only(
        admission_id="writer-admission",
        writer_implementation_fingerprint="writer",
        graph_schema_fingerprint="schema",
    )

    class RevokedAtCommit:
        def assert_current(self, **_kwargs):
            raise OSError("release authority revoked")

    store = SemanticIngestionAtomicStore(
        plane, writers, current_bootstrap_release_verifier=RevokedAtCommit()
    )
    record = CanonicalMemoryRecord(
        memory_id="bootstrap:final-check-must-not-write",
        domain=MemoryDomain.TRANSCRIPT,
        text="",
        content={},
        status=CommitStatus.COMMITTED,
        source_kind="test_bootstrap_final_check",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    authorization = DeliveryAuthorizationRequest(
        delivery_identity=fence.delivery_identity,
        ingress=AuthenticatedIngressContext(
            delivery_principal_binding=DeliveryPrincipalBinding.create(
                principal_subject_id="principal:a",
                tenant_partition_id="tenant:a",
                provider_identity="provider:test",
            ),
            required_outcome_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id="tenant:a", scopes=set()
            ),
            current_authorized_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id="tenant:a", scopes=set()
            ),
        ),
    )
    language = BootstrapAuthenticatedLanguageEvidence.model_construct(
        source_id=admission.source_id,
        source_digest=admission.source_digest,
        delivery_principal_binding_digest=fence.delivery_identity.delivery_principal_binding_digest,
    )
    before = tuple(plane.list_records())
    with pytest.raises(PreplanningStoreError, match="unavailable at write commit"):
        plane.conditionally_write_records(
            (record,),
            preconditions=(RecordAbsentPrecondition(memory_id=record.memory_id),),
            transaction_precondition=store._bootstrap_current_precondition(
                authorization=authorization,
                release_evidence=HostVerifiedBootstrapReleaseEvidence.model_construct(),
                assertion_phase="prepared_publication",
                expected_delivery_identity=fence.delivery_identity,
                language_evidence=language,
            ),
        )
    assert tuple(plane.list_records()) == before
