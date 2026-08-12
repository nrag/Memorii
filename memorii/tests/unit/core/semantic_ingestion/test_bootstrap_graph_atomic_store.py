"""Durability invariants for the dedicated bootstrap V3 graph record grammar."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.atomic_store import (
    SemanticIngestionAtomicStore,
    _bootstrap_graph_v3_member_id,
    _bootstrap_graph_v3_member_record,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.semantic_ingestion.contracts import BootstrapGraphPlanAtomicMemberV3


def _member() -> BootstrapGraphPlanAtomicMemberV3:
    payload = b'{"bootstrap":"graph"}'
    return BootstrapGraphPlanAtomicMemberV3.create(
        member_id="graph-plan",
        kind="bootstrap_transaction_group_plan",
        canonical_payload=payload,
        payload_digest=sha256(payload).hexdigest(),
    )


def _record(member: BootstrapGraphPlanAtomicMemberV3):
    return _bootstrap_graph_v3_member_record(
        namespace_id="fence-fixture",
        generation=7,
        member=member,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _authorized_plane(*, path=None):
    plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(path) if path is not None else None
    )
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="graph-v3-fixture-writer",
            writer_implementation_fingerprint="graph-v3-fixture",
            graph_schema_fingerprint="graph-v3-schema",
        )
    )
    atomic = SemanticIngestionAtomicStore(plane, writers)
    return plane, writers._authorize_atomic(binding, capability=atomic._write_capability)


def test_graph_v3_member_is_rejected_without_its_atomic_control_in_memory() -> None:
    member = _member()
    record = _record(member)
    plane, authorization = _authorized_plane()
    with pytest.raises(SemanticWriterAdmissionError, match="atomic control"):
        plane.write_records((record,), authorization=authorization)
    assert record.memory_id == _bootstrap_graph_v3_member_id("fence-fixture", 7, "graph-plan")


def test_graph_v3_member_is_rejected_without_its_atomic_control_after_jsonl_reopen(tmp_path) -> None:
    member = _member()
    record = _record(member)
    path = tmp_path / "graph-v3"
    plane, authorization = _authorized_plane(path=path)
    with pytest.raises(SemanticWriterAdmissionError, match="atomic control"):
        plane.write_records((record,), authorization=authorization)
    assert MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)).get_record(record.memory_id) is None


def test_graph_v3_member_contract_rejects_payload_tampering() -> None:
    member = _member()
    with pytest.raises(ValueError, match="member_digest mismatch"):
        BootstrapGraphPlanAtomicMemberV3.model_validate(
            member.model_dump(mode="python") | {"canonical_payload": b"substituted"}
        )
