from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService, SourceAdmissionAccepted
from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
    SourceCheckpointAtomicWriteRequest,
    generation_request_digest,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


def _handoff(plane: MemoryPlaneService) -> tuple[SourceAdmissionAccepted, OperationFenceBinding]:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a", tenant_partition_id="tenant:a", provider_identity="provider:test"
    )
    identity = DeliveryIdentity.create(principal, "delivery:lease")
    source = CanonicalMemoryRecord(
        memory_id="tx:lease",
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
        source=source, delivery_identity=identity, ingress=ingress, operation_id="op:lease", evidence_only=True
    )
    return admission, OperationFenceBinding.create(
        operation_id="op:lease",
        source_id=admission.source_id,
        source_digest=admission.source_digest,
        delivery_identity=identity,
    )


def test_lease_renews_fences_stale_tokens_and_bounds_recovery() -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    plane = MemoryPlaneService()
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0])
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="m2",
            writer_implementation_fingerprint="writer-fingerprint",
            graph_schema_fingerprint="schema-fingerprint",
        )
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now[0])
    store._publish_preplanning(admission=admission, writer_binding=binding)
    claimed = store.acquire_lease(
        operation_id=fence.operation_id,
        writer_binding=binding,
        execution_token="token:one",
        duration=timedelta(seconds=10),
    )
    assert claimed.lease is not None
    renewed = store.renew_lease(
        operation_id=fence.operation_id, writer_binding=binding, lease=claimed.lease, duration=timedelta(seconds=10)
    )
    assert renewed.lease is not None and renewed.lease.ownership_epoch == 1
    renewed_lease = renewed.lease

    now[0] += timedelta(seconds=11)
    reclaimed = store.acquire_lease(
        operation_id=fence.operation_id,
        writer_binding=binding,
        execution_token="token:one",
        duration=timedelta(seconds=10),
    )
    assert reclaimed.lease is not None and reclaimed.lease.ownership_epoch == 2
    with pytest.raises(PreplanningStoreError):
        store.renew_lease(
            operation_id=fence.operation_id, writer_binding=binding, lease=renewed_lease, duration=timedelta(seconds=10)
        )

    now[0] += timedelta(seconds=11)
    exhausted = store.acquire_lease(
        operation_id=fence.operation_id,
        writer_binding=binding,
        execution_token="token:one",
        duration=timedelta(seconds=10),
    )
    assert exhausted.state == "lease_recovery_exhausted"
    with pytest.raises(PreplanningStoreError):
        store.acquire_lease(
            operation_id=fence.operation_id,
            writer_binding=binding,
            execution_token="token:four",
            duration=timedelta(seconds=10),
        )


def test_lease_acquisition_exact_retry_returns_persisted_binding() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now)
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="m2", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now)
    store._publish_preplanning(admission=admission, writer_binding=binding)
    first = store.acquire_lease(
        operation_id=fence.operation_id, writer_binding=binding,
        execution_token="stable-token", owner_id="owner", duration=timedelta(seconds=5),
    )
    assert store.acquire_lease(
        operation_id=fence.operation_id, writer_binding=binding,
        execution_token="stable-token", owner_id="owner", duration=timedelta(seconds=5),
    ) == first


def test_planned_operation_lease_expires_and_reclaims_with_next_fence_epoch() -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    plane = MemoryPlaneService()
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0])
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="m2", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now[0])
    store._publish_preplanning(admission=admission, writer_binding=binding)
    claimed = store.acquire_lease(
        operation_id=fence.operation_id, writer_binding=binding, execution_token="one", duration=timedelta(seconds=5)
    )
    members = []
    for kind in (
        "artifact_closure", "artifact_index", "independence_certificate", "plan",
        "planning_artifact", "planning_authorization", "progress",
    ):
        payload = kind.encode()
        members.append(AtomicGenerationMember(
            member_id=kind, kind=kind, canonical_payload=payload,
            payload_digest=sha256(payload).hexdigest(),
        ))
    request = SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=fence, operation_lease_binding=store.lease_binding(claimed),
        writer_commit_binding=binding, expected_operation_generation=1, expected_artifact_generation=1,
        members=tuple(members), required_artifact_digests=(), request_digest="0" * 64, progress_state="planned",
    )
    store.checkpoint_source_progress(request.model_copy(update={
        "request_digest": generation_request_digest(request)
    }))
    now[0] += timedelta(seconds=6)
    reclaimed = store.acquire_lease(
        operation_id=fence.operation_id, writer_binding=binding, execution_token="two", duration=timedelta(seconds=5)
    )
    assert reclaimed.state == "planned"
    assert reclaimed.lease is not None and reclaimed.lease.ownership_epoch == 2


def test_renewal_that_crosses_expiry_before_storage_cas_is_rejected() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    current = [base]
    plane = MemoryPlaneService()
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: current[0])
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="m2", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: current[0])
    store._publish_preplanning(admission=admission, writer_binding=binding)
    claimed = store.acquire_lease(
        operation_id=fence.operation_id, writer_binding=binding, execution_token="one", duration=timedelta(seconds=5)
    )
    assert claimed.lease is not None
    calls = [0]
    def crossing_clock() -> datetime:
        calls[0] += 1
        return base if calls[0] < 3 else base + timedelta(seconds=6)
    store._now = crossing_clock
    with pytest.raises(ValueError, match="expired before storage CAS"):
        store.renew_lease(
            operation_id=fence.operation_id, writer_binding=binding,
            lease=claimed.lease, duration=timedelta(seconds=5),
        )


def test_jsonl_restart_reclaims_same_operation_identity_and_fences_old_owner(tmp_path: Path) -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    path = tmp_path / "lease-restart"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0])
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="m2", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now[0])
    store._publish_preplanning(admission=admission, writer_binding=binding)
    owner_a = store.acquire_lease(
        operation_id=fence.operation_id, writer_binding=binding,
        execution_token="owner:a", duration=timedelta(seconds=5),
    )
    saved_a = store.lease_binding(owner_a)

    now[0] += timedelta(seconds=6)
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
    )
    reopened = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: now[0])
    owner_b = reopened.acquire_lease(
        operation_id=fence.operation_id, writer_binding=binding,
        execution_token="owner:b", duration=timedelta(seconds=5),
    )
    saved_b = reopened.lease_binding(owner_b)
    assert saved_b.ownership_epoch == saved_a.ownership_epoch + 1
    assert saved_b.operation_fence_binding == saved_a.operation_fence_binding
    assert saved_b.allocation_namespace_id == saved_a.allocation_namespace_id
    assert saved_b.delivery_key_digest == saved_a.delivery_key_digest

    member = AtomicGenerationMember(
        member_id="progress", kind="progress", canonical_payload=b"progress",
        payload_digest=sha256(b"progress").hexdigest(),
    )
    stale = SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=fence, operation_lease_binding=saved_a,
        writer_commit_binding=binding, expected_operation_generation=1,
        expected_artifact_generation=1, members=(member,), required_artifact_digests=(),
        request_digest="0" * 64, progress_state="preplanning",
    )
    before = reopened_plane.list_records()
    with pytest.raises(PreplanningStoreError, match="lease"):
        reopened.checkpoint_source_progress(stale.model_copy(update={
            "request_digest": generation_request_digest(stale)
        }))
    assert reopened_plane.list_records() == before


def test_jsonl_lease_lost_ack_reopens_to_exact_same_owner_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    path = tmp_path / "lease-lost-ack"
    backend = JsonlMemoryPlaneStore(path)
    plane = MemoryPlaneService(record_store=backend)
    admission, fence = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now)
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="m2", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now)
    store._publish_preplanning(admission=admission, writer_binding=binding)
    original_apply = backend.apply_batch

    def apply_then_lose_ack(*args, **kwargs):
        original_apply(*args, **kwargs)
        raise OSError("lease acknowledgement lost")

    monkeypatch.setattr(backend, "apply_batch", apply_then_lose_ack)
    with pytest.raises(OSError, match="acknowledgement lost"):
        store.acquire_lease(
            operation_id=fence.operation_id, writer_binding=binding,
            execution_token="stable-token", owner_id="stable-owner", duration=timedelta(seconds=5),
        )
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now
    )
    reopened = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: now)
    persisted = reopened.get_operation(fence.operation_id)
    retry = reopened.acquire_lease(
        operation_id=fence.operation_id, writer_binding=binding,
        execution_token="stable-token", owner_id="stable-owner", duration=timedelta(seconds=5),
    )
    assert retry == persisted
    assert reopened.lease_binding(retry).ownership_epoch == 1
    with pytest.raises(PreplanningStoreError, match="another owner"):
        reopened.acquire_lease(
            operation_id=fence.operation_id, writer_binding=binding,
            execution_token="other-token", owner_id="other-owner", duration=timedelta(seconds=5),
        )
