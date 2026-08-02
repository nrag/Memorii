from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService
from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    CommittedGroupAtomicWriteRequest,
    NonCommittingGroupAtomicWriteRequest,
    PreplanningOperationControl,
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
    SourceCheckpointAtomicWriteRequest,
    SourceFinalizationAtomicWriteRequest,
    generation_request_digest,
)
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
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, MemoryPlaneStore, _PersistedBatch
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from test_semantic_atomic_store import _handoff

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _setup(*, verified: bool = False, planned: bool = False, backend: MemoryPlaneStore | None = None):
    plane = MemoryPlaneService(record_store=backend) if backend is not None else MemoryPlaneService()
    admission, _ = _handoff(plane)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="m2", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    if verified:
        plan = build_migration_plan(
            migration_plan_id="plan:verified", source_writer_epoch=1,
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
        binding = writers.commit_binding(writers.transition(
            expected=binding, admission_id="m2:verified", runtime_mode="verified_semantic",
            writer_implementation_fingerprint="writer:verified", graph_schema_fingerprint="schema",
            migration_activation=activation, migration_plan=plan, migration_checkpoint=checkpoint,
            migration_certificate=certificate, target_records=(),
        ))
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    publication = store._publish_preplanning(admission=admission, writer_binding=binding)
    claimed = store.acquire_lease(
        operation_fence=publication.operation.operation_fence,
        writer_binding=binding,
        execution_token="worker",
        duration=timedelta(minutes=5),
    )
    assert claimed.lease is not None
    if planned:
        members = tuple(_member(kind, kind) for kind in (
            "artifact_closure", "artifact_index", "independence_certificate", "plan",
            "planning_artifact", "planning_authorization", "progress",
        ))
        request = SourceCheckpointAtomicWriteRequest(
            operation_fence_binding=claimed.operation_fence,
            operation_lease_binding=store.lease_binding(claimed), writer_commit_binding=binding,
            expected_operation_generation=1, expected_artifact_generation=1, members=members,
            required_artifact_digests=(), request_digest="0" * 64, progress_state="planned",
        )
        store.checkpoint_source_progress(_seal(request))
        claimed = store.get_operation(claimed.operation_fence)
    return plane, store, binding, claimed


def _member(member_id: str, kind: str) -> AtomicGenerationMember:
    payload = f"{kind}:{member_id}".encode()
    return AtomicGenerationMember(
        member_id=member_id, kind=kind, canonical_payload=payload, payload_digest=sha256(payload).hexdigest()
    )


def _seal(request):
    return request.model_copy(update={"request_digest": generation_request_digest(request)})


def _rewrite_operation_family_to_legacy_raw_ids(
    backend: JsonlMemoryPlaneStore, control: PreplanningOperationControl
) -> None:
    """Build a deterministic pre-remediation fixture from a valid generation."""

    fence = control.operation_fence
    modern = fence.operation_fence_id
    legacy = fence.operation_id
    rewritten_batches = []
    for batch in backend._read_batches_unlocked():
        records = []
        for record in batch.records:
            replacement = record.memory_id.replace(f":{modern}:", f":{legacy}:")
            if record.memory_id == f"semantic_ingestion:operation:{modern}":
                replacement = f"semantic_ingestion:operation:{legacy}"
            content = record.content
            if replacement == f"semantic_ingestion:operation:{legacy}":
                content = dict(content)
                control_body = dict(content["control"])
                control_body.pop("persistence_namespace_id", None)
                content["control"] = control_body
            records.append(record.model_copy(update={"memory_id": replacement, "content": content}))
        rewritten_batches.append(
            _PersistedBatch.create(
                revision=batch.revision, data_revision=batch.data_revision, records=tuple(records)
            )
        )
    backend._replace_batches(rewritten_batches)


def test_checkpoint_is_atomic_idempotent_and_cannot_regress_planned_state() -> None:
    plane, store, binding, control = _setup()
    request = _seal(SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=1, expected_artifact_generation=1,
        members=tuple(_member(kind, kind) for kind in (
            "artifact_closure", "artifact_index", "independence_certificate", "plan",
            "planning_artifact", "planning_authorization", "progress",
        )), required_artifact_digests=(),
        request_digest="0" * 64, progress_state="planned",
    ))
    first = store.checkpoint_source_progress(request)
    assert store.checkpoint_source_progress(request) == first
    assert len([record for record in plane.list_records() if record.source_kind == "semantic_ingestion_generation_manifest"]) == 1

    stale = _seal(request.model_copy(update={
        "request_digest": "0" * 64, "expected_operation_generation": 2, "expected_artifact_generation": 2,
        "progress_state": "preplanning", "members": (_member("regress", "progress"),),
    }))
    with pytest.raises(PreplanningStoreError, match="cannot regress"):
        store.checkpoint_source_progress(stale)


def test_preplanning_control_rejects_substituted_persistence_namespace() -> None:
    _, _, _, control = _setup()
    with pytest.raises(ValueError, match="namespace"):
        PreplanningOperationControl.model_validate(
            control.model_dump(mode="python") | {"persistence_namespace_id": "substituted"}
        )


def test_exact_generation_recovery_rejects_a_renewed_lease_owner() -> None:
    _, store, binding, control = _setup()
    request = _seal(SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=control.operation_fence,
        operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding,
        expected_operation_generation=1,
        expected_artifact_generation=1,
        members=(_member("progress", "progress"),),
        required_artifact_digests=(),
        request_digest="0" * 64,
        progress_state="preplanning",
    ))
    assert store.checkpoint_source_progress(request) == request.members
    assert control.lease is not None
    store.renew_lease(
        operation_fence=control.operation_fence,
        writer_binding=binding,
        lease=control.lease,
        duration=timedelta(minutes=5),
    )
    with pytest.raises(PreplanningStoreError, match="lease is stale or expired"):
        store.checkpoint_source_progress(request)


@pytest.mark.parametrize("committed", [False, True])
def test_terminal_group_enforces_committing_and_noncommitting_member_sets(committed: bool) -> None:
    _, store, binding, control = _setup(verified=committed, planned=True)
    common = dict(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        required_artifact_digests=(), request_digest="0" * 64,
    )
    if committed:
        request = CommittedGroupAtomicWriteRequest(
            **common,
            members=tuple(_member(kind, kind) for kind in ("event_batch", "graph_delta", "group_result", "observation_delta")),
            expected_graph_revision="genesis", expected_observation_revision="genesis",
            expected_effective_read_set_digest="0" * 64,
            graph_revision_after="g2", observation_revision_after="o2",
        )
    else:
        request = NonCommittingGroupAtomicWriteRequest(
            **common,
            members=tuple(_member(kind, kind) for kind in ("group_result", "observation_delta")),
            expected_observation_revision="genesis", observation_revision_after="o2",
        )
    request = _seal(request)
    assert store.persist_terminal_group(request) == request.members


def test_finalization_requires_complete_lifecycle_generation_and_closes_operation() -> None:
    _, store, binding, control = _setup(planned=True)
    group = _seal(NonCommittingGroupAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=tuple(_member(kind, kind) for kind in ("group_result", "observation_delta")),
        required_artifact_digests=(), request_digest="0" * 64,
        expected_observation_revision="genesis", observation_revision_after="o2",
    ))
    store.persist_terminal_group(group)
    group_digest = next(member.payload_digest for member in group.members if member.kind == "group_result")
    request = _seal(SourceFinalizationAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=3, expected_artifact_generation=3,
        members=tuple(_member(kind, kind) for kind in (
            "lifecycle", "observation_delta", "source_result", "source_summary", "terminal_operation"
        )),
        required_artifact_digests=(), request_digest="0" * 64,
        source_summary_kind="graph_bound", expected_group_result_digests=(group_digest,),
    ))
    assert store.finalize_source(request) == request.members
    assert store.finalize_source(request) == request.members
    terminal = store.get_operation(control.operation_fence)
    assert terminal.state == "terminal" and terminal.lease is None
    with pytest.raises(PreplanningStoreError):
        store.lease_binding(terminal)
    with pytest.raises(PreplanningStoreError):
        store.acquire_lease(
            operation_fence=control.operation_fence,
            writer_binding=binding,
            execution_token="revive",
            duration=timedelta(minutes=5),
        )


def test_missing_artifact_or_invalid_digest_changes_nothing() -> None:
    plane, store, binding, control = _setup()
    member = _member("progress", "progress")
    request = _seal(SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=1, expected_artifact_generation=1,
        members=(member,), required_artifact_digests=("f" * 64,), request_digest="0" * 64,
        progress_state="preplanning",
    ))
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="closure"):
        store.checkpoint_source_progress(request)
    assert plane.list_records() == before


def test_terminal_group_stale_graph_or_observation_revision_changes_nothing() -> None:
    plane, store, binding, control = _setup(verified=True, planned=True)
    base = CommittedGroupAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=tuple(_member(kind, kind) for kind in ("event_batch", "graph_delta", "group_result", "observation_delta")),
        required_artifact_digests=(), request_digest="0" * 64,
        expected_graph_revision="stale", expected_observation_revision="genesis",
        expected_effective_read_set_digest="0" * 64, graph_revision_after="g2", observation_revision_after="o2",
    )
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="graph/read-set"):
        store.persist_terminal_group(_seal(base))
    with pytest.raises(PreplanningStoreError, match="observation"):
        store.persist_terminal_group(_seal(base.model_copy(update={
            "request_digest": "0" * 64, "expected_graph_revision": "genesis",
            "expected_observation_revision": "stale",
        })))
    assert plane.list_records() == before


def test_finalization_rejects_missing_or_substituted_group_result_closure() -> None:
    plane, store, binding, control = _setup(planned=True)
    group = _seal(NonCommittingGroupAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=tuple(_member(kind, kind) for kind in ("group_result", "observation_delta")),
        required_artifact_digests=(), request_digest="0" * 64,
        expected_observation_revision="genesis", observation_revision_after="o2",
    ))
    store.persist_terminal_group(group)
    members = tuple(_member(f"final:{kind}", kind) for kind in (
        "lifecycle", "observation_delta", "source_result", "source_summary", "terminal_operation"
    ))
    bad = _seal(SourceFinalizationAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=3, expected_artifact_generation=3,
        members=members, required_artifact_digests=(), request_digest="0" * 64,
        source_summary_kind="graph_bound", expected_group_result_digests=("f" * 64,),
    ))
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="closure"):
        store.finalize_source(bad)
    assert plane.list_records() == before


def test_evidence_only_writer_rejects_committed_graph_and_event_generation() -> None:
    plane, store, binding, control = _setup(planned=True)
    request = _seal(CommittedGroupAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=tuple(_member(kind, kind) for kind in ("event_batch", "graph_delta", "group_result", "observation_delta")),
        required_artifact_digests=(), request_digest="0" * 64,
        expected_graph_revision="genesis", expected_observation_revision="genesis",
        expected_effective_read_set_digest="0" * 64, graph_revision_after="g2", observation_revision_after="o2",
    ))
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="evidence-only"):
        store.persist_terminal_group(request)
    assert plane.list_records() == before


def test_reserved_manifest_member_id_is_rejected_without_visibility() -> None:
    plane, store, binding, control = _setup()
    request = _seal(SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=1, expected_artifact_generation=1,
        members=(_member("manifest", "progress"),), required_artifact_digests=(), request_digest="0" * 64,
        progress_state="preplanning",
    ))
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="canonical order"):
        store.checkpoint_source_progress(request)
    assert plane.list_records() == before


def test_empty_checkpoint_and_duplicate_terminal_singletons_are_rejected() -> None:
    plane, store, binding, control = _setup()
    empty = _seal(SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=1, expected_artifact_generation=1,
        members=(), required_artifact_digests=(), request_digest="0" * 64, progress_state="preplanning",
    ))
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="exactly one progress"):
        store.checkpoint_source_progress(empty)
    assert plane.list_records() == before

    _, planned_store, planned_binding, planned_control = _setup(planned=True)
    duplicate = _seal(NonCommittingGroupAtomicWriteRequest(
        operation_fence_binding=planned_control.operation_fence,
        operation_lease_binding=planned_store.lease_binding(planned_control),
        writer_commit_binding=planned_binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=(
            _member("group:a", "group_result"), _member("group:b", "group_result"),
            _member("observation", "observation_delta"),
        ),
        required_artifact_digests=(), request_digest="0" * 64,
        expected_observation_revision="genesis", observation_revision_after="o2",
    ))
    with pytest.raises(PreplanningStoreError, match="incomplete"):
        planned_store.persist_terminal_group(duplicate)


def test_later_generation_reuses_prior_complete_replay_artifact() -> None:
    _, store, binding, control = _setup(planned=True)
    artifact = _member("artifact:a", "replay_artifact")
    checkpoint = _seal(SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=(artifact, _member("progress", "progress")),
        required_artifact_digests=(artifact.payload_digest,), request_digest="0" * 64, progress_state="planned",
    ))
    store.checkpoint_source_progress(checkpoint)
    group = _seal(NonCommittingGroupAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=3, expected_artifact_generation=3,
        members=tuple(_member(kind, kind) for kind in ("group_result", "observation_delta")),
        required_artifact_digests=(artifact.payload_digest,), request_digest="0" * 64,
        expected_observation_revision="genesis", observation_revision_after="o2",
    ))
    assert store.persist_terminal_group(group) == group.members


class _JsonlLostAckStore(JsonlMemoryPlaneStore):
    armed = False

    def _replace_batches(self, batches):
        super()._replace_batches(batches)
        if self.armed:
            self.armed = False
            raise RuntimeError("simulated lost acknowledgement")


def test_jsonl_group_and_finalization_lost_ack_recover_exact_generations(tmp_path: Path) -> None:
    path = tmp_path / "generations"
    backend = _JsonlLostAckStore(path)
    _, store, binding, control = _setup(planned=True, backend=backend)
    group = _seal(NonCommittingGroupAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=tuple(_member(kind, kind) for kind in ("group_result", "observation_delta")),
        required_artifact_digests=(), request_digest="0" * 64,
        expected_observation_revision="genesis", observation_revision_after="o2",
    ))
    backend.armed = True
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        store.persist_terminal_group(group)
    assert store.persist_terminal_group(group) == group.members
    control = store.get_operation(control.operation_fence)
    group_digest = next(member.payload_digest for member in group.members if member.kind == "group_result")
    final = _seal(SourceFinalizationAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=3, expected_artifact_generation=3,
        members=tuple(_member(f"final:{kind}", kind) for kind in (
            "lifecycle", "observation_delta", "source_result", "source_summary", "terminal_operation"
        )),
        required_artifact_digests=(), request_digest="0" * 64,
        source_summary_kind="graph_bound", expected_group_result_digests=(group_digest,),
    ))
    backend.armed = True
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        store.finalize_source(final)
    assert store.finalize_source(final) == final.members
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    assert len([record for record in reopened.list_records() if record.source_kind == "semantic_ingestion_generation_manifest"]) == 3


@pytest.mark.parametrize("phase", ["checkpoint", "group", "finalization"])
def test_jsonl_restart_recovers_exact_generation_after_lost_ack_at_each_boundary(
    tmp_path: Path, phase: str
) -> None:
    path = tmp_path / phase
    backend = _JsonlLostAckStore(path)
    _, store, binding, control = _setup(planned=phase != "checkpoint", backend=backend)
    if phase == "checkpoint":
        request = _seal(SourceCheckpointAtomicWriteRequest(
            operation_fence_binding=control.operation_fence,
            operation_lease_binding=store.lease_binding(control),
            writer_commit_binding=binding,
            expected_operation_generation=1,
            expected_artifact_generation=1,
            members=(_member("restart:progress", "progress"),),
            required_artifact_digests=(),
            request_digest="0" * 64,
            progress_state="preplanning",
        ))
        publish = store.checkpoint_source_progress
    else:
        group = _seal(NonCommittingGroupAtomicWriteRequest(
            operation_fence_binding=control.operation_fence,
            operation_lease_binding=store.lease_binding(control),
            writer_commit_binding=binding,
            expected_operation_generation=2,
            expected_artifact_generation=2,
            members=(_member("restart:group", "group_result"), _member("restart:observation", "observation_delta")),
            required_artifact_digests=(),
            request_digest="0" * 64,
            expected_observation_revision="genesis",
            observation_revision_after="restart-o2",
        ))
        if phase == "group":
            request = group
            publish = store.persist_terminal_group
        else:
            assert store.persist_terminal_group(group) == group.members
            control = store.get_operation(control.operation_fence)
            request = _seal(SourceFinalizationAtomicWriteRequest(
                operation_fence_binding=control.operation_fence,
                operation_lease_binding=store.lease_binding(control),
                writer_commit_binding=binding,
                expected_operation_generation=3,
                expected_artifact_generation=3,
                members=tuple(_member(f"restart:final:{kind}", kind) for kind in (
                    "lifecycle", "observation_delta", "source_result", "source_summary", "terminal_operation"
                )),
                required_artifact_digests=(),
                request_digest="0" * 64,
                source_summary_kind="graph_bound",
                expected_group_result_digests=(group.members[0].payload_digest,),
            ))
            publish = store.finalize_source
    backend.armed = True
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        publish(request)

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    reopened = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: NOW)
    retry_publish = {
        "checkpoint": reopened.checkpoint_source_progress,
        "group": reopened.persist_terminal_group,
        "finalization": reopened.finalize_source,
    }[phase]
    before_retry = reopened_plane.list_records()
    assert retry_publish(request) == request.members
    assert reopened_plane.list_records() == before_retry
    current = reopened.get_operation(request.operation_fence_binding)
    assert current.state == ("terminal" if phase == "finalization" else ("planned" if phase == "group" else "preplanning"))
    altered_lease = request.operation_lease_binding.model_copy(update={"execution_token": "altered"})
    altered = _seal(request.model_copy(update={"operation_lease_binding": altered_lease, "request_digest": "0" * 64}))
    before_altered = reopened_plane.list_records()
    with pytest.raises((PreplanningStoreError, ValueError), match="lease|digest"):
        retry_publish(altered)
    assert reopened_plane.list_records() == before_altered


def test_legacy_raw_namespace_reopen_keeps_lease_and_generation_family_isolated(tmp_path: Path) -> None:
    path = tmp_path / "legacy-family"
    backend = _JsonlLostAckStore(path)
    _, _, binding, control = _setup(planned=True, backend=backend)
    _rewrite_operation_family_to_legacy_raw_ids(backend, control)

    now = [NOW + timedelta(minutes=6)]
    reopened_backend = _JsonlLostAckStore(path)
    reopened_plane = MemoryPlaneService(record_store=reopened_backend)
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
    )
    reopened = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: now[0])
    reclaimed = reopened.acquire_lease(
        operation_fence=control.operation_fence,
        writer_binding=binding,
        execution_token="legacy-reclaimer",
        duration=timedelta(minutes=5),
    )
    group = _seal(NonCommittingGroupAtomicWriteRequest(
        operation_fence_binding=reclaimed.operation_fence,
        operation_lease_binding=reopened.lease_binding(reclaimed),
        writer_commit_binding=binding,
        expected_operation_generation=2,
        expected_artifact_generation=2,
        members=(_member("legacy:group", "group_result"), _member("legacy:observation", "observation_delta")),
        required_artifact_digests=(),
        request_digest="0" * 64,
        expected_observation_revision="genesis",
        observation_revision_after="legacy-o2",
    ))
    assert reopened.persist_terminal_group(group) == group.members
    current = reopened.get_operation(control.operation_fence)
    group_digest = group.members[0].payload_digest
    final = _seal(SourceFinalizationAtomicWriteRequest(
        operation_fence_binding=current.operation_fence,
        operation_lease_binding=reopened.lease_binding(current),
        writer_commit_binding=binding,
        expected_operation_generation=3,
        expected_artifact_generation=3,
        members=tuple(_member(f"legacy:final:{kind}", kind) for kind in (
            "lifecycle", "observation_delta", "source_result", "source_summary", "terminal_operation"
        )),
        required_artifact_digests=(),
        request_digest="0" * 64,
        source_summary_kind="graph_bound",
        expected_group_result_digests=(group_digest,),
    ))
    reopened_backend.armed = True
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        reopened.finalize_source(final)

    retry_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    retry_writers = SemanticWriterAdmissionStore(
        retry_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
    )
    retry = SemanticIngestionAtomicStore(retry_plane, retry_writers, now_provider=lambda: now[0])
    assert retry.finalize_source(final) == final.members
    ids = {record.memory_id for record in retry_plane.list_records()}
    assert any(f"semantic_ingestion:operation:{control.operation_fence.operation_id}" == value for value in ids)
    assert not any(control.operation_fence.operation_fence_id in value for value in ids)


def test_jsonl_same_public_operation_id_has_two_fence_isolated_generations_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "two-tenants"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="m2", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    publications = []
    for tenant in ("one", "two"):
        principal = DeliveryPrincipalBinding.create(
            principal_subject_id=f"principal:{tenant}", tenant_partition_id=f"tenant:{tenant}",
            provider_identity="provider:test",
        )
        identity = DeliveryIdentity.create(principal, "same-public-delivery")
        ingress = AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            required_outcome_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id=f"tenant:{tenant}", scopes=set()
            ),
            current_authorized_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id=f"tenant:{tenant}", scopes=set()
            ),
        )
        source = CanonicalMemoryRecord(
            memory_id=f"tx:{tenant}", domain=MemoryDomain.TRANSCRIPT, text="source", content={"text": tenant},
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source", timestamp=NOW,
            is_raw_event=True, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        prepared = GovernedSourceAdmissionService(plane).prepare_atomic(
            source=source, delivery_identity=identity, ingress=ingress,
            operation_id="same-public-operation", evidence_only=True,
        )
        publications.append(store.admit_source(prepared=prepared, writer_binding=binding))
    controls = []
    for index, publication in enumerate(publications):
        claimed = store.acquire_lease(
            operation_fence=publication.operation.operation_fence,
            writer_binding=binding,
            execution_token=f"tenant-worker:{index}",
            duration=timedelta(minutes=5),
        )
        request = _seal(SourceCheckpointAtomicWriteRequest(
            operation_fence_binding=claimed.operation_fence,
            operation_lease_binding=store.lease_binding(claimed),
            writer_commit_binding=binding,
            expected_operation_generation=1,
            expected_artifact_generation=1,
            members=(_member(f"tenant:{index}:progress", "progress"),),
            required_artifact_digests=(),
            request_digest="0" * 64,
            progress_state="preplanning",
        ))
        assert store.checkpoint_source_progress(request) == request.members
        controls.append(claimed.operation_fence)
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    reopened = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: NOW)
    reopened_controls = tuple(reopened.get_operation(fence) for fence in controls)
    assert all(control.generation == 2 for control in reopened_controls)
    ids = {record.memory_id for record in reopened_plane.list_records()}
    for fence in controls:
        assert f"semantic_ingestion:operation:{fence.operation_fence_id}" in ids
        assert f"semantic_ingestion:generation:{fence.operation_fence_id}:2:manifest" in ids
    before = reopened_plane.list_records()
    with pytest.raises(PreplanningStoreError, match="absent or ambiguous"):
        reopened.acquire_lease(
            operation_id="same-public-operation", writer_binding=binding,
            execution_token="ambiguous", duration=timedelta(minutes=5),
        )
    assert reopened_plane.list_records() == before


def test_legacy_raw_namespace_never_crosses_tenant_fence_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "legacy-foreign-fence"
    backend = JsonlMemoryPlaneStore(path)
    _, _, binding, control = _setup(planned=True, backend=backend)
    _rewrite_operation_family_to_legacy_raw_ids(backend, control)
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    foreign_principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:foreign", tenant_partition_id="tenant:foreign", provider_identity="provider:test"
    )
    foreign_fence = OperationFenceBinding.create(
        operation_id=control.operation_fence.operation_id,
        source_id=control.operation_fence.source_id,
        source_digest=control.operation_fence.source_digest,
        delivery_identity=DeliveryIdentity.create(foreign_principal, "foreign-delivery"),
    )
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="absent"):
        store.get_operation(foreign_fence)
    with pytest.raises(PreplanningStoreError, match="absent"):
        store.acquire_lease(
            operation_fence=foreign_fence, writer_binding=binding,
            execution_token="foreign", duration=timedelta(minutes=1),
        )
    current = store.get_operation(control.operation_fence)
    assert current.lease is not None
    with pytest.raises(PreplanningStoreError, match="absent"):
        store.renew_lease(
            operation_fence=foreign_fence,
            writer_binding=binding,
            lease=current.lease,
            duration=timedelta(minutes=1),
        )
    request = _seal(SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=foreign_fence,
        operation_lease_binding=store.lease_binding(current),
        writer_commit_binding=binding,
        expected_operation_generation=current.generation,
        expected_artifact_generation=current.generation,
        members=(_member("foreign-progress", "progress"),),
        required_artifact_digests=(),
        request_digest="0" * 64,
        progress_state="planned",
    ))
    with pytest.raises(PreplanningStoreError, match="absent"):
        store.checkpoint_source_progress(request)
    assert plane.list_records() == before


def test_multigroup_finalization_requires_exact_persisted_order() -> None:
    plane, store, binding, control = _setup(planned=True)
    digests = []
    for generation, before, after, suffix in ((2, "genesis", "o2", "a"), (3, "o2", "o3", "b")):
        group = _seal(NonCommittingGroupAtomicWriteRequest(
            operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
            writer_commit_binding=binding, expected_operation_generation=generation,
            expected_artifact_generation=generation,
            members=(
                _member(f"group:{suffix}", "group_result"),
                _member(f"observation:{suffix}", "observation_delta"),
            ),
            required_artifact_digests=(), request_digest="0" * 64,
            expected_observation_revision=before, observation_revision_after=after,
        ))
        store.persist_terminal_group(group)
        digests.append(next(member.payload_digest for member in group.members if member.kind == "group_result"))
        control = store.get_operation(control.operation_fence)
    final_members = tuple(_member(f"final:{kind}", kind) for kind in (
        "lifecycle", "observation_delta", "source_result", "source_summary", "terminal_operation"
    ))
    base = SourceFinalizationAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=4, expected_artifact_generation=4,
        members=final_members, required_artifact_digests=(), request_digest="0" * 64,
        source_summary_kind="graph_bound", expected_group_result_digests=tuple(reversed(digests)),
    )
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="closure"):
        store.finalize_source(_seal(base))
    assert plane.list_records() == before
    exact = _seal(base.model_copy(update={
        "request_digest": "0" * 64, "expected_group_result_digests": tuple(digests)
    }))
    assert store.finalize_source(exact) == exact.members


def test_finalization_rejects_duplicate_members_and_summary_group_mismatches() -> None:
    plane, store, binding, control = _setup(planned=True)
    required = tuple(_member(f"final:{kind}", kind) for kind in (
        "lifecycle", "observation_delta", "source_result", "source_summary", "terminal_operation"
    ))
    duplicate = _seal(SourceFinalizationAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=(*required, _member("final:lifecycle:duplicate", "lifecycle")),
        required_artifact_digests=(), request_digest="0" * 64,
        source_summary_kind="pre_graph", expected_group_result_digests=(),
    ))
    before = plane.list_records()
    with pytest.raises(PreplanningStoreError, match="incomplete"):
        store.finalize_source(duplicate)
    graph_bound = _seal(duplicate.model_copy(update={
        "request_digest": "0" * 64, "members": required, "source_summary_kind": "graph_bound"
    }))
    with pytest.raises(PreplanningStoreError, match="no terminal group"):
        store.finalize_source(graph_bound)
    assert plane.list_records() == before

    group = _seal(NonCommittingGroupAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=2, expected_artifact_generation=2,
        members=(_member("group", "group_result"), _member("observation", "observation_delta")),
        required_artifact_digests=(), request_digest="0" * 64,
        expected_observation_revision="genesis", observation_revision_after="o2",
    ))
    store.persist_terminal_group(group)
    digest = next(member.payload_digest for member in group.members if member.kind == "group_result")
    control = store.get_operation(control.operation_fence)
    pre_graph = _seal(SourceFinalizationAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=3, expected_artifact_generation=3,
        members=required, required_artifact_digests=(), request_digest="0" * 64,
        source_summary_kind="pre_graph", expected_group_result_digests=(digest,),
    ))
    with pytest.raises(PreplanningStoreError, match="pre-graph"):
        store.finalize_source(pre_graph)
