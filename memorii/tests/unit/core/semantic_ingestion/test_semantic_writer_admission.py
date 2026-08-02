from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    MemoryPlaneGovernedWritePolicyRequiredError,
    MemoryPlaneStore,
    RecordAbsentPrecondition,
)


def test_certified_current_writer_is_recoverable_and_exact() -> None:
    admission = SemanticWriterAdmissionStore(
        MemoryPlaneService(),
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    current = admission.create_initial_evidence_only(
        admission_id="writer-admission",
        writer_implementation_fingerprint="writer-fingerprint",
        graph_schema_fingerprint="schema-fingerprint",
    )
    binding = admission.commit_binding(current)

    assert admission.require_current(binding).content["admission"] == current.model_dump(mode="json")
    assert (
        admission.create_initial_evidence_only(
            admission_id="writer-admission",
            writer_implementation_fingerprint="writer-fingerprint",
            graph_schema_fingerprint="schema-fingerprint",
        )
        == current
    )


def test_stale_unbound_and_mismatched_writers_are_rejected() -> None:
    admission = SemanticWriterAdmissionStore(MemoryPlaneService(), bounded_preplanning_ownership_manifest())
    current = admission.create_initial_evidence_only(
        admission_id="writer-admission",
        writer_implementation_fingerprint="writer-fingerprint",
        graph_schema_fingerprint="schema-fingerprint",
    )
    stale = admission.commit_binding(current).model_copy(update={"expected_writer_epoch": 2})

    with pytest.raises(SemanticWriterAdmissionError):
        admission.require_current(stale)
    with pytest.raises(SemanticWriterAdmissionError):
        admission.create_initial_evidence_only(
            admission_id="other",
            writer_implementation_fingerprint="writer-fingerprint",
            graph_schema_fingerprint="schema-fingerprint",
        )
    assert (
        admission.require_current(admission.commit_binding(current)).memory_id
        == "semantic_ingestion:writer_admission:current"
    )


@pytest.mark.parametrize("backend_kind", ["memory", "jsonl"])
@pytest.mark.parametrize(
    "route",
    [
        "service_stage",
        "service_write",
        "service_upsert",
        "service_conditional",
        "unit_of_work",
        "store_stage",
        "store_write",
        "store_upsert",
        "store_apply",
    ],
)
def test_governed_writer_records_reject_every_unbound_generic_route(
    tmp_path: Path,
    backend_kind: str,
    route: str,
) -> None:
    backend: MemoryPlaneStore = (
        InMemoryMemoryPlaneStore() if backend_kind == "memory" else JsonlMemoryPlaneStore(tmp_path / route)
    )
    plane = MemoryPlaneService(record_store=backend)
    admissions = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    current = admissions.create_initial_evidence_only(
        admission_id="writer-admission",
        writer_implementation_fingerprint="writer-fingerprint",
        graph_schema_fingerprint="schema-fingerprint",
    )
    forged = admissions.require_current(admissions.commit_binding(current)).model_copy(
        update={"memory_id": "semantic_ingestion:forged-writer-admission"}
    )
    before = backend.read_snapshot()

    with pytest.raises(SemanticWriterAdmissionError):
        if route == "service_stage":
            plane.stage_record(forged)
        elif route == "service_write":
            plane.write_records((forged,))
        elif route == "service_upsert":
            plane.upsert_record(forged)
        elif route == "service_conditional":
            plane.conditionally_write_records(
                (forged,),
                preconditions=(RecordAbsentPrecondition(memory_id=forged.memory_id),),
            )
        elif route == "unit_of_work":
            with plane.unit_of_work() as unit_of_work:
                plane.write_records((forged,))
                unit_of_work.commit()
        elif route == "store_stage":
            backend.stage_record(forged)
        elif route == "store_write":
            backend.write_records((forged,))
        elif route == "store_upsert":
            backend.upsert_record(forged)
        else:
            backend.apply_batch(
                (forged,),
                expected_revision=backend.revision(),
                preconditions=(RecordAbsentPrecondition(memory_id=forged.memory_id),),
            )

    assert backend.read_snapshot() == before


def test_reopened_jsonl_backend_denies_governed_write_before_policy_reinstall(tmp_path: Path) -> None:
    path = tmp_path / "reopened"
    first_backend = JsonlMemoryPlaneStore(path)
    first_plane = MemoryPlaneService(record_store=first_backend)
    admissions = SemanticWriterAdmissionStore(first_plane, bounded_preplanning_ownership_manifest())
    current = admissions.create_initial_evidence_only(
        admission_id="writer-admission",
        writer_implementation_fingerprint="writer-fingerprint",
        graph_schema_fingerprint="schema-fingerprint",
    )
    forged = admissions.require_current(admissions.commit_binding(current)).model_copy(
        update={"memory_id": "semantic_ingestion:forged-after-reopen"}
    )
    reopened = JsonlMemoryPlaneStore(path)
    before = reopened.read_snapshot()

    with pytest.raises(MemoryPlaneGovernedWritePolicyRequiredError):
        reopened.write_records((forged,))

    assert reopened.read_snapshot() == before


@pytest.mark.parametrize("backend_kind", ["memory", "jsonl"])
@pytest.mark.parametrize("source_kind", [
    "semantic_ingestion_source",
    "semantic_ingestion_metadata_poor_snapshot",
    "semantic_ingestion_admission_index",
    "semantic_ingestion_profile_selection",
    "semantic_ingestion_profile_verification",
    "semantic_ingestion_profile_outcome",
])
def test_admission_records_reject_unbound_generic_writes(
    tmp_path: Path, backend_kind: str, source_kind: str
) -> None:
    backend: MemoryPlaneStore = (
        InMemoryMemoryPlaneStore()
        if backend_kind == "memory"
        else JsonlMemoryPlaneStore(tmp_path / source_kind)
    )
    plane = MemoryPlaneService(record_store=backend)
    admissions = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    current = admissions.create_initial_evidence_only(
        admission_id="writer-admission", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    )
    forged = admissions.require_current(admissions.commit_binding(current)).model_copy(update={
        "memory_id": f"semantic_ingestion:forged:{source_kind}", "source_kind": source_kind
    })
    before = backend.read_snapshot()
    with pytest.raises(SemanticWriterAdmissionError):
        plane.write_records((forged,))
    assert backend.read_snapshot() == before
