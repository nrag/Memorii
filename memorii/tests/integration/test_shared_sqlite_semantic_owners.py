"""Real semantic-ingestion owner paths over the managed shared partition.

The governed source admission, writer admission and atomic preplanning
owners run unchanged over the selected published partition: every write
commits through the signed publication protocol, survives independent
process reopen, and leaves the verification tiers green.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

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
