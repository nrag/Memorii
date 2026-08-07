from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution import atomic_store as atomic_store_module
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.graph_records import (
    AcceptedIdentityOperationArtifact,
    GraphPartitionVersion,
    GraphReadSet,
    GraphReadSetExtension,
    GraphRecordKind,
    GraphStateSnapshot,
    GraphWriteIntent,
    PlannedEntityIdentity,
    PlannedIdentityReservation,
    canonical_graph_codec_manifest,
    graph_digest,
)
from memorii.core.memory_evolution.identity_lineage import (
    AtomicStoreAcceptedIdentityOperationPlanner,
    ProductionIdentityLineageCompiler,
    identity_lineage_genesis_digest,
)
from memorii.core.memory_evolution.reference_integrity import (
    ReferenceAuditCertificate,
    ReferenceEdgeLedgerSnapshot,
    bootstrap_reference_integrity,
    generated_reference_schema_manifest,
    validate_reference_integrity_converse,
)
from memorii.core.memory_evolution.semantic_state import (
    AcceptedIdentityOperation,
    LineageEntityIdentity,
    LineageEvidenceReference,
)
from memorii.core.memory_evolution.transaction_coordinator import (
    SemanticIngestionTransactionCoordinator,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.semantic_ingestion.capability import (
    build_authorized_local_semantic_runtime,
)
from memorii.core.semantic_ingestion.event_replay import SemanticReplayState
from pydantic import ValidationError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _evidence() -> LineageEvidenceReference:
    return LineageEvidenceReference(
        source_id="source:alias",
        start=0,
        end=5,
        evidence_digest=sha256(b"alias evidence").hexdigest(),
    )


class _Reader:
    def __init__(self, state: SemanticReplayState, ledger: ReferenceEdgeLedgerSnapshot) -> None:
        self.state = state
        self.ledger = ledger

    def semantic_replay_state(self) -> SemanticReplayState:
        return self.state

    def reference_integrity_snapshot(self) -> ReferenceEdgeLedgerSnapshot:
        return self.ledger

    def graph_state_snapshot(self) -> GraphStateSnapshot:
        codec = canonical_graph_codec_manifest()
        read_set = GraphReadSet.create(
            record_keys=(),
            partition_versions=(
                GraphPartitionVersion(partition_id="canonical_graph", version=self.state.state_digest),
                GraphPartitionVersion(partition_id="reference_ledger", version=self.ledger.ledger_digest),
            ),
            manifest_fingerprints=tuple(sorted((
                codec.manifest_fingerprint,
                generated_reference_schema_manifest().manifest_fingerprint,
            ))),
        )
        values = {
            "snapshot_token": graph_digest(b"test.snapshot\0", self.state.state_digest),
            "graph_revision": self.state.graph_revision,
            "system_as_of": NOW,
            "records": (),
            "exact_record_counts_by_kind": tuple((kind, 0) for kind in sorted(GraphRecordKind.__args__)),
            "codec_manifest_fingerprint": codec.manifest_fingerprint,
            "governance_policy_fingerprints": (),
            "read_set": read_set,
        }
        return GraphStateSnapshot.model_validate(values | {
            "snapshot_digest": graph_digest(b"memorii.graph-state-snapshot.v1\0", values)
        })


def _artifact(
    accepted: AcceptedIdentityOperation,
    *,
    sealed_operation_digest: str = "1" * 64,
    candidate_digest: str = "2" * 64,
    source_analysis_digest: str = "3" * 64,
) -> AcceptedIdentityOperationArtifact:
    reservations = []
    for successor in accepted.successors:
        keys = tuple(sorted((
            f"entity_revision:{successor.entity_revision_id}",
            f"logical_entity:{successor.logical_entity_id}",
        )))
        extension = GraphReadSetExtension.create(
            snapshot_token="snapshot",
            graph_revision="genesis",
            segment_governance_binding_digests=(),
            operation_fence_id="fence",
            issuer_repository_id="semantic_ingestion",
            issuer_contract_fingerprint="4" * 64,
            dependency_kind="identity_allocation",
            record_keys=keys,
            partition_versions=(),
            manifest_fingerprints=(canonical_graph_codec_manifest().manifest_fingerprint,),
        )
        reservations.append(PlannedIdentityReservation.create(
            planned_identity=PlannedEntityIdentity(
                allocation_key=successor.entity_revision_id,
                entity_revision_id=successor.entity_revision_id,
                logical_entity_id=successor.logical_entity_id,
                allocation_namespace_id="test",
                allocation_policy_fingerprint="5" * 64,
            ),
            collision_read_set_extension=extension,
            expected_absent_write_intents=tuple(
                GraphWriteIntent(record_key=key, expected_before_digest=None) for key in keys
            ),
        ))
    values = {
        "operation": accepted,
        "operation_fence_id": "fence",
        "sealed_operation_digest": sealed_operation_digest,
        "candidate_digest": candidate_digest,
        "source_analysis_digest": source_analysis_digest,
        "source_evidence_digests": tuple(sorted(item.evidence_digest for item in accepted.source_evidence)),
        "semantic_authorization_read_set_digest": "6" * 64,
        "authority_digest": "7" * 64,
        "verified_decision_digest": "8" * 64,
        "authority_record_id": "authority:test",
        "authority_record_digest": "9" * 64,
        "authority_verification_digest": "7" * 64,
        "successor_reservations": tuple(reservations),
        "alias_payload": None,
    }
    if accepted.operation == "alias":
        from memorii.core.memory_evolution.graph_records import SourceGroundedAliasPayload
        values["alias_payload"] = SourceGroundedAliasPayload.create(
            alias_namespace="test",
            normalized_alias_key="alias",
            entity_revision_id="alias-target:v1",
            logical_entity_id="alias-target",
            source_evidence=accepted.source_evidence,
        )
    return AcceptedIdentityOperationArtifact.create(**values)


class _AcceptedRepository:
    def __init__(self, accepted: AcceptedIdentityOperation) -> None:
        self.accepted = accepted

    def get_accepted_identity_operation(self, **bindings):
        assert bindings.pop("operation_id") == self.accepted.operation_id
        return _artifact(self.accepted, **bindings)


def test_generated_manifest_is_total_and_zero_reference_kinds_are_explicit() -> None:
    manifest = generated_reference_schema_manifest()
    assert tuple(item.record_kind for item in manifest.schema_entries) == tuple(
        sorted(GraphRecordKind.__args__)
    )
    by_kind = {item.record_kind: item.reference_fields for item in manifest.schema_entries}
    assert by_kind["action_revision"] == ()
    assert by_kind["temporal_transition"] == ()
    assert {field.target_kind for field in by_kind["claim_assertion"]} == {
        "entity_revision",
        "logical_entity",
    }
    assert {
        field.reference_path: field.lifecycle_semantics
        for field in by_kind["identity_lineage"]
    } == {
        "transition.predecessors[].entity_revision_id": "immutable_revision",
        "transition.predecessors[].logical_entity_id": "immutable_revision",
        "transition.successors[].entity_revision_id": "immutable_revision",
        "transition.successors[].logical_entity_id": "immutable_revision",
    }
    assert {
        field.lifecycle_semantics for field in by_kind["claim_assertion"]
    } == {"immutable_revision"}


def test_bootstrap_snapshot_round_trips_and_rejects_certificate_mutation() -> None:
    state = SemanticReplayState.genesis("semantic_ingestion")
    snapshot = bootstrap_reference_integrity(state, completed_at=NOW)
    assert snapshot.active
    assert ReferenceEdgeLedgerSnapshot.model_validate(snapshot.model_dump(mode="python")) == snapshot
    body = snapshot.model_dump(mode="python")
    body["audit_certificate"]["base_record_count"] = 1
    with pytest.raises(ValidationError):
        ReferenceEdgeLedgerSnapshot.model_validate(body)


def test_reference_audit_certificate_is_recomputed_against_replay_state() -> None:
    state = SemanticReplayState.genesis("semantic_ingestion")
    snapshot = bootstrap_reference_integrity(state, completed_at=NOW)
    assert snapshot.audit_certificate is not None
    values = snapshot.audit_certificate.model_dump(
        mode="python", exclude={"certificate_id", "certificate_digest"}
    )
    values["base_record_count"] = 999
    forged = ReferenceAuditCertificate.create(**values)
    rewrapped = ReferenceEdgeLedgerSnapshot.create(
        manifest_fingerprint=snapshot.manifest_fingerprint,
        entries=snapshot.entries,
        audit_certificate=forged,
        active=True,
    )

    with pytest.raises(ValueError, match="certificate_state_mismatch"):
        validate_reference_integrity_converse(rewrapped, state)


def test_transaction_snapshot_rejects_a_mixed_graph_read() -> None:
    state = SemanticReplayState.genesis("semantic_ingestion")
    reader = _Reader(state, bootstrap_reference_integrity(state, completed_at=NOW))
    calls = 0

    def changing_state() -> SemanticReplayState:
        nonlocal calls
        calls += 1
        if calls == 1:
            return state
        return state.model_copy(update={"graph_revision": "changed"})

    reader.semantic_replay_state = changing_state  # type: ignore[method-assign]
    coordinator = SemanticIngestionTransactionCoordinator(reader, now_provider=lambda: NOW)
    with pytest.raises(ValueError, match="stale_graph_snapshot"):
        coordinator.acquire_snapshot()


def test_production_compiler_consumes_accepted_ir_and_sealed_authorities() -> None:
    state = SemanticReplayState.genesis("semantic_ingestion")
    reader = _Reader(state, bootstrap_reference_integrity(state, completed_at=NOW))
    coordinator = SemanticIngestionTransactionCoordinator(reader, now_provider=lambda: NOW)
    accepted = AcceptedIdentityOperation.create(
        operation_id="operation:alias",
        operation="alias",
        predecessors=(),
        successors=(),
        source_evidence=(_evidence(),),
        reference_assignments=(),
    )
    compiler = ProductionIdentityLineageCompiler(
        coordinator, _AcceptedRepository(accepted)
    )
    transition = compiler.compile_transition(
        operation=SimpleNamespace(
            operation_id="operation:alias", candidate_id="candidate:alias", kind="identity"
            , sealed_operation_digest="1" * 64
        ),
        candidate=SimpleNamespace(candidate_id="candidate:alias", candidate_digest="2" * 64),
        source_analysis=SimpleNamespace(candidate_id="candidate:alias", analysis_digest="3" * 64),
    )
    assert transition.operation == "alias"
    assert transition.graph_revision_before == "genesis"
    assert transition.lineage_snapshot_before_digest == identity_lineage_genesis_digest(
        "semantic_ingestion"
    )


@pytest.mark.parametrize(
    ("operation_kind", "predecessors", "successors"),
    (
        (
            "rekey",
            (LineageEntityIdentity(entity_revision_id="alice:v1", logical_entity_id="alice"),),
            (LineageEntityIdentity(entity_revision_id="alice:v2", logical_entity_id="alice"),),
        ),
        (
            "merge",
            (
                LineageEntityIdentity(entity_revision_id="alice:v1", logical_entity_id="alice"),
                LineageEntityIdentity(entity_revision_id="bob:v1", logical_entity_id="bob"),
            ),
            (LineageEntityIdentity(entity_revision_id="people:v1", logical_entity_id="people"),),
        ),
        (
            "split",
            (LineageEntityIdentity(entity_revision_id="team:v1", logical_entity_id="team"),),
            (
                LineageEntityIdentity(entity_revision_id="team-a:v1", logical_entity_id="team-a"),
                LineageEntityIdentity(entity_revision_id="team-b:v1", logical_entity_id="team-b"),
            ),
        ),
    ),
)
def test_production_compiler_accepts_each_revision_operation_after_bootstrap(
    operation_kind,
    predecessors,
    successors,
) -> None:
    state = SemanticReplayState.genesis("semantic_ingestion")
    coordinator = SemanticIngestionTransactionCoordinator(
        _Reader(state, bootstrap_reference_integrity(state, completed_at=NOW)),
        now_provider=lambda: NOW,
    )
    accepted = AcceptedIdentityOperation.create(
        operation_id=f"operation:{operation_kind}",
        operation=operation_kind,
        predecessors=predecessors,
        successors=successors,
        source_evidence=(_evidence(),),
        reference_assignments=(),
    )
    compiler = ProductionIdentityLineageCompiler(coordinator, _AcceptedRepository(accepted))
    transition = compiler.compile_transition(
        operation=SimpleNamespace(
            operation_id=accepted.operation_id,
            candidate_id=f"candidate:{operation_kind}",
            kind="identity",
            sealed_operation_digest="1" * 64,
        ),
        candidate=SimpleNamespace(candidate_id=f"candidate:{operation_kind}", candidate_digest="2" * 64),
        source_analysis=SimpleNamespace(candidate_id=f"candidate:{operation_kind}", analysis_digest="3" * 64),
    )
    assert transition.operation == operation_kind
    assert transition.predecessors == predecessors
    assert transition.successors == successors


def test_atomic_store_bootstrap_is_durable_and_idempotent_on_reopen() -> None:
    plane = MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="semantic-ingestion",
            writer_implementation_fingerprint="writer",
            graph_schema_fingerprint="schema",
        )
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    activated = store.bootstrap_reference_integrity(writer_binding=binding)
    reopened = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    assert reopened.reference_integrity_snapshot() == activated
    assert reopened.bootstrap_reference_integrity(writer_binding=binding) == activated


def test_reference_integrity_bootstrap_retries_if_replay_state_appears_during_audit() -> None:
    plane = MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="semantic-ingestion",
            writer_implementation_fingerprint="writer",
            graph_schema_fingerprint="schema",
        )
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    original = plane.conditionally_write_records
    inserted = False

    def racing_write(records, *, preconditions=(), authorization=None, **kwargs):
        nonlocal inserted
        if (
            not inserted
            and records[0].source_kind == "semantic_ingestion_reference_integrity"
        ):
            inserted = True
            replay = atomic_store_module._semantic_replay_state_record(
                SemanticReplayState.genesis("semantic_ingestion"), NOW
            )
            backend = plane._records
            with backend._lock:
                backend._records[replay.memory_id] = replay
                backend._revision += 1
        return original(
            records,
            preconditions=preconditions,
            authorization=authorization,
            **kwargs,
        )

    plane.conditionally_write_records = racing_write  # type: ignore[method-assign]
    snapshot = store.bootstrap_reference_integrity(writer_binding=binding)

    assert inserted
    assert snapshot == store.reference_integrity_snapshot()


def test_ordinary_local_runtime_composes_the_production_lineage_compiler() -> None:
    plane = MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    writers.create_initial_evidence_only(
        admission_id="semantic-ingestion",
        writer_implementation_fingerprint="writer",
        graph_schema_fingerprint="schema",
    )
    verifier = SimpleNamespace(
        verify_identity_decision_authority=lambda decision: None
    )
    store = SemanticIngestionAtomicStore(
        plane,
        writers,
        now_provider=lambda: NOW,
        identity_decision_authority_verifier=verifier,
    )
    runtime = build_authorized_local_semantic_runtime(
        authorization_bytes=b"authority",
        authorization_verifier=SimpleNamespace(),
        policy_provider=SimpleNamespace(),
        writer_admission=writers,
        atomic_store=store,
        identity_operation_resolver=SimpleNamespace(
            resolve_accepted_identity_operation=lambda **kwargs: None
        ),
        identity_decision_authority_verifier=verifier,
    )
    assert isinstance(
        runtime.pipeline._identity_lineage_compiler,
        ProductionIdentityLineageCompiler,
    )
    assert isinstance(
        runtime.pipeline._identity_operation_planner,
        AtomicStoreAcceptedIdentityOperationPlanner,
    )


@pytest.mark.parametrize(
    "kwargs",
    (
        {
            "identity_operation_resolver": SimpleNamespace(
                resolve_accepted_identity_operation=lambda **values: None
            )
        },
        {
            "identity_operation_resolver": SimpleNamespace(),
            "identity_decision_authority_verifier": SimpleNamespace(
                verify_identity_decision_authority=lambda decision: None
            ),
        },
    ),
)
def test_local_runtime_rejects_incomplete_or_malformed_identity_authority(
    kwargs,
) -> None:
    plane = MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    writers.create_initial_evidence_only(
        admission_id="semantic-ingestion",
        writer_implementation_fingerprint="writer",
        graph_schema_fingerprint="schema",
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)

    with pytest.raises(ValueError, match="identity operation authority"):
        build_authorized_local_semantic_runtime(
            authorization_bytes=b"authority",
            authorization_verifier=SimpleNamespace(),
            policy_provider=SimpleNamespace(),
            writer_admission=writers,
            atomic_store=store,
            **kwargs,
        )


def test_local_runtime_rejects_verifier_not_owned_by_atomic_store() -> None:
    plane = MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    writers.create_initial_evidence_only(
        admission_id="semantic-ingestion",
        writer_implementation_fingerprint="writer",
        graph_schema_fingerprint="schema",
    )
    store_verifier = SimpleNamespace(
        verify_identity_decision_authority=lambda decision: None
    )
    store = SemanticIngestionAtomicStore(
        plane,
        writers,
        now_provider=lambda: NOW,
        identity_decision_authority_verifier=store_verifier,
    )

    with pytest.raises(ValueError, match="verifier is not store-owned"):
        build_authorized_local_semantic_runtime(
            authorization_bytes=b"authority",
            authorization_verifier=SimpleNamespace(),
            policy_provider=SimpleNamespace(),
            writer_admission=writers,
            atomic_store=store,
            identity_operation_resolver=SimpleNamespace(
                resolve_accepted_identity_operation=lambda **values: None
            ),
            identity_decision_authority_verifier=SimpleNamespace(
                verify_identity_decision_authority=lambda decision: None
            ),
        )


def test_local_runtime_without_identity_authority_remains_nonplanning() -> None:
    plane = MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    writers.create_initial_evidence_only(
        admission_id="semantic-ingestion",
        writer_implementation_fingerprint="writer",
        graph_schema_fingerprint="schema",
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    runtime = build_authorized_local_semantic_runtime(
        authorization_bytes=b"authority",
        authorization_verifier=SimpleNamespace(),
        policy_provider=SimpleNamespace(),
        writer_admission=writers,
        atomic_store=store,
    )

    assert runtime.pipeline._identity_operation_planner is None
