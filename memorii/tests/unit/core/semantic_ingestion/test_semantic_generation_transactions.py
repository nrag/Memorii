from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    CommittedGroupAtomicWriteRequest,
    NonCommittingGroupAtomicWriteRequest,
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
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, MemoryPlaneStore
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
        operation_id=publication.operation.operation_fence.operation_id,
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
        claimed = store.get_operation(claimed.operation_fence.operation_id)
    return plane, store, binding, claimed


def _member(member_id: str, kind: str) -> AtomicGenerationMember:
    payload = f"{kind}:{member_id}".encode()
    return AtomicGenerationMember(
        member_id=member_id, kind=kind, canonical_payload=payload, payload_digest=sha256(payload).hexdigest()
    )


def _seal(request):
    return request.model_copy(update={"request_digest": generation_request_digest(request)})


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
    terminal = store.get_operation(control.operation_fence.operation_id)
    assert terminal.state == "terminal" and terminal.lease is None
    with pytest.raises(PreplanningStoreError):
        store.lease_binding(terminal)
    with pytest.raises(PreplanningStoreError):
        store.acquire_lease(
            operation_id=control.operation_fence.operation_id,
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
    control = store.get_operation(control.operation_fence.operation_id)
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
        control = store.get_operation(control.operation_fence.operation_id)
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
    control = store.get_operation(control.operation_fence.operation_id)
    pre_graph = _seal(SourceFinalizationAtomicWriteRequest(
        operation_fence_binding=control.operation_fence, operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding, expected_operation_generation=3, expected_artifact_generation=3,
        members=required, required_artifact_digests=(), request_digest="0" * 64,
        source_summary_kind="pre_graph", expected_group_result_digests=(digest,),
    ))
    with pytest.raises(PreplanningStoreError, match="pre-graph"):
        store.finalize_source(pre_graph)
