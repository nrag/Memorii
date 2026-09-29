"""Real semantic-ingestion owner paths over the managed shared partition.

The governed source admission, writer admission and atomic preplanning
owners run unchanged over the selected published partition: every write
commits through the signed publication protocol, survives independent
process reopen, and leaves the verification tiers green.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
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
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import select_persistent_memory_plane
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_FROZEN_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _handoff(plane: MemoryPlaneService) -> tuple[object, OperationFenceBinding]:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a",
        tenant_partition_id="tenant:a",
        provider_identity="provider:test",
    )
    identity = DeliveryIdentity.create(principal, "delivery:one")
    source = CanonicalMemoryRecord(
        memory_id="tx:one",
        domain=MemoryDomain.TRANSCRIPT,
        text="source",
        content={"text": "source"},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_source",
        timestamp=_FROZEN_NOW,
        is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:a", scopes=set()
        ),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:a", scopes=set()
        ),
    )
    admission = GovernedSourceAdmissionService(plane).admit(
        source=source,
        delivery_identity=identity,
        ingress=ingress,
        operation_id="op:one",
        evidence_only=True,
    )
    return admission, OperationFenceBinding.create(
        operation_id="op:one",
        source_id=admission.source_id,
        source_digest=admission.source_digest,
        delivery_identity=identity,
    )


def _run_preplanning_journey(root: Path) -> None:
    selection = select_persistent_memory_plane(root)
    assert selection.managed
    assert selection.administration is not None
    try:
        plane = selection.memory_plane
        admission, fence = _handoff(plane)
        del fence
        writers = SemanticWriterAdmissionStore(
            plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: _FROZEN_NOW,
        )
        binding = writers.commit_binding(
            writers.create_initial_evidence_only(
                admission_id="writer-admission",
                writer_implementation_fingerprint="writer-fingerprint",
                graph_schema_fingerprint="schema-fingerprint",
            )
        )
        store = SemanticIngestionAtomicStore(
            plane, writers, now_provider=lambda: _FROZEN_NOW
        )
        first = store._publish_preplanning(admission=admission, writer_binding=binding)
        second = store._publish_preplanning(admission=admission, writer_binding=binding)
        assert first == second
        partition_store = SqliteMemoryPlaneStore(selection.administration.partition())
        artifacts = partition_store.list_records(
            source_kind="semantic_ingestion_preplanning_artifact"
        )
        sources = partition_store.list_records(source_kind="semantic_ingestion_source")
        assert len(artifacts) == 3
        assert len(sources) == 1
        snapshot = selection.administration.acquire_verified_snapshot()
        assert snapshot.vector.memory_write_revision >= 2
        assert not (root / "memory-plane").exists()
    finally:
        selection.administration.close()


def test_atomic_preplanning_publishes_through_signed_publication(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
    _run_preplanning_journey(root)


_REOPEN_PROGRAM = '''
import sys
from pathlib import Path

from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import select_persistent_memory_plane

root = Path(sys.argv[1])
selection = select_persistent_memory_plane(root)
assert selection.managed
try:
    store = SqliteMemoryPlaneStore(selection.administration.partition())
    artifacts = store.list_records(source_kind="semantic_ingestion_preplanning_artifact")
    sources = store.list_records(source_kind="semantic_ingestion_source")
    snapshot = selection.administration.acquire_verified_snapshot()
    print(len(artifacts), len(sources), snapshot.ordinal > 0)
finally:
    selection.administration.close()
'''


def test_semantic_owner_state_survives_fresh_process(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
    _run_preplanning_journey(root)
    reopened = subprocess.run(
        [sys.executable, "-c", _REOPEN_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert reopened.stdout.strip() == "3 1 True"


def _sample_projection():
    from memorii.core.memory_evolution.semantic_index import (
        SemanticClaimIndexRow,
        SemanticEntityIndexRow,
        SemanticEvidenceLinkIndexRow,
        SemanticIndexProjection,
    )

    def digest(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()
    return SemanticIndexProjection(
        graph_revision="graph:generation:1",
        snapshot_digest=digest("snapshot"),
        entities=(
            SemanticEntityIndexRow(
                logical_entity_id="entity:atlas",
                entity_revision_id="entity-revision:atlas:1",
                lifecycle="active",
                record_id="record:atlas",
                record_digest=digest("record:atlas"),
                codec_fingerprint=digest("codec"),
            ),
            SemanticEntityIndexRow(
                logical_entity_id="entity:bob",
                entity_revision_id="entity-revision:bob:1",
                lifecycle="active",
                record_id="record:bob",
                record_digest=digest("record:bob"),
                codec_fingerprint=digest("codec"),
            ),
        ),
        claims=(
            SemanticClaimIndexRow(
                claim_assertion_id="claim:owner:1",
                subject_entity_id="entity:atlas",
                object_entity_id="entity:bob",
                predicate_id="owner_is",
                record_id="record:claim:1",
                record_digest=digest("record:claim:1"),
                valid_from="2026-01-01T00:00:00+00:00",
                valid_to=None,
            ),
        ),
        evidence_links=(
            SemanticEvidenceLinkIndexRow(
                claim_assertion_id="claim:owner:1",
                source_id="source:one",
                source_digest=digest("source"),
                evidence_digest=digest("evidence"),
            ),
        ),
    )


def test_derived_semantic_index_publishes_and_queries(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        projection = _sample_projection()
        outcome = service.publish_memory_plane_batch(
            (), store=service.memory_plane_store(), derived_semantic_index=projection
        )
        assert outcome.ordinal == 1
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            state = partition.read_semantic_index_state(connection)
            assert state is not None
            assert str(state["graph_revision"]) == "graph:generation:1"
            assert int(state["write_revision"]) == 1
            assert int(state["data_revision"]) == 0
            neighborhood = partition.query_entity_neighborhood(
                connection, logical_entity_id="entity:atlas", depth=2
            )
            evidence = partition.query_claim_evidence(
                connection, claim_assertion_id="claim:owner:1"
            )
        assert [str(row["claim_assertion_id"]) for row in neighborhood] == ["claim:owner:1"]
        assert [str(row["source_id"]) for row in evidence] == ["source:one"]
        # The signed manifest covers the derived tables: verification is
        # green with them, and tampering an index row is detected.
        snapshot = service.acquire_verified_snapshot()
        assert snapshot.ordinal == 1

    connection = sqlite3.connect(root / "partition" / "partition.sqlite3")
    try:
        connection.execute(
            "UPDATE semantic_claims SET predicate_id = 'tampered'"
            " WHERE claim_assertion_id = 'claim:owner:1'"
        )
        connection.commit()
    finally:
        connection.close()
    with StorageAdministrationService(root) as fresh_service:
        from memorii.core.storage_administration.service import (
            InstallationIntegrityError,
        )

        with pytest.raises(InstallationIntegrityError):
            fresh_service.acquire_verified_snapshot()


def test_ontology_activation_projects_into_derived_index(tmp_path: Path) -> None:
    from memorii.core.semantic_ingestion.ontology_index import (
        KIND_ATTEMPT,
        KIND_POINTER,
        KIND_PROPOSAL,
        KIND_REPLAY,
        KIND_VERSION,
        project_ontology_index,
    )
    from tests.unit.core.semantic_ingestion.test_learned_relation import (
        _approve_and_activate,
        _proposal,
        _ReplayWriter,
        _runtime,
    )

    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        selection = select_persistent_memory_plane(root)
        try:
            writer = _ReplayWriter()
            runtime = _runtime(writer, plane=selection.memory_plane)
            activated = _approve_and_activate(runtime, _proposal())
            assert activated is not None
            partition_store = SqliteMemoryPlaneStore(service.partition())
            ontology_records = [
                record
                for record in partition_store.list_records()
                if record.source_kind
                in {KIND_PROPOSAL, KIND_VERSION, KIND_POINTER, KIND_ATTEMPT, KIND_REPLAY}
            ]
            assert ontology_records
            projection = project_ontology_index(ontology_records)
            assert any(row.status == "selected" for row in projection.attempts)
            assert projection.selections and projection.versions
            outcome = service.publish_memory_plane_batch(
                (),
                store=service.memory_plane_store(),
                derived_ontology_index=projection,
            )
            assert outcome.ordinal >= 1
            partition = service.partition()
            with partition.transaction(write=False) as connection:
                selections = partition.read_current_catalog_selections(connection)
                history = partition.query_catalog_history(connection)
            assert len(selections) == len(projection.selections)
            assert [str(row["version_digest"]) for row in history] == [
                row.version_digest for row in projection.versions
            ]
            snapshot = service.acquire_verified_snapshot()
            assert snapshot.ordinal == outcome.ordinal
        finally:
            selection.administration.close()
