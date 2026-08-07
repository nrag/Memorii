from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.conflict_attention import (
    ConflictClarificationProcessingReceipt,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    _is_atomic_clarification_projection_write,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.semantic_control import (
    SEMANTIC_CONTROL_ID_PREFIXES,
    SEMANTIC_CONTROL_SOURCE_KINDS,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    MemoryPlaneGovernedWritePolicyRequiredError,
    MemoryPlaneStore,
    RecordAbsentPrecondition,
)
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
)


def _clarification_terminal_pair(
    outcome: str = "rejected",
) -> tuple[CanonicalMemoryRecord, CanonicalMemoryRecord]:
    operation_id = sha256(b"clarification-operation").hexdigest()
    conflict_revision = sha256(b"conflict-revision").hexdigest()
    resulting_revision = sha256(b"resulting-revision").hexdigest()
    proposal_digest = sha256(b"proposal").hexdigest()
    policy_fingerprint = sha256(b"policy").hexdigest()
    semantic_result_digest = sha256(b"semantic-result").hexdigest()
    body: dict[str, object] = {
        "processing_operation_id": operation_id,
        "conflict_id": "conflict",
        "conflict_revision": conflict_revision,
        "resulting_conflict_revision": resulting_revision,
        "proposal_digest": proposal_digest,
        "source_user_event_id": "user-event",
        "source_user_event_digest": sha256(b"user-event").hexdigest(),
        "policy_fingerprint": policy_fingerprint,
        "committed_outcome": outcome,
        "semantic_result_digest": semantic_result_digest,
        "semantic_terminal_hex": None,
        "graph_delta_hex": None,
        "graph_delta_digest": None,
        "semantic_event_batch_id": None,
        "semantic_event_batch_digest": None,
        "graph_revision_before": None,
        "graph_revision_after": None,
        "semantic_recovery_authority_generation": None,
        "semantic_recovery_authority_id": None,
    }
    transaction_id = f"clarification-{operation_id}"
    transaction_digest = sha256(encode_typed_value(body)).hexdigest()
    receipt = ConflictClarificationProcessingReceipt.create(
        processing_operation_id=operation_id,
        conflict_id="conflict",
        conflict_revision=resulting_revision,
        proposal_digest=proposal_digest,
        policy_fingerprint=policy_fingerprint,
        semantic_transaction_id=transaction_id,
        semantic_transaction_digest=transaction_digest,
        semantic_result_digest=semantic_result_digest,
        committed_outcome=outcome,
        committed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    transaction_record = CanonicalMemoryRecord(
        memory_id=f"semantic_ingestion:clarification:transaction:{operation_id}",
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "conflict_clarification_transaction",
            "semantic_transaction_id": transaction_id,
            "semantic_transaction_digest": transaction_digest,
            "transaction": body,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_conflict_clarification_transaction",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    receipt_record = CanonicalMemoryRecord(
        memory_id=f"semantic_ingestion:clarification:receipt:{operation_id}",
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "conflict_clarification_processing_receipt",
            "receipt": receipt.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_conflict_clarification_receipt",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    return transaction_record, receipt_record


@pytest.mark.parametrize("outcome", ["rejected", "insufficient"])
def test_detached_clarification_terminal_pair_is_not_admitted(
    outcome: str,
) -> None:
    """A receipt pair cannot stand in for its same-plane conflict closure."""
    records = _clarification_terminal_pair(outcome)
    assert not _is_atomic_clarification_projection_write(records, [])


def test_direct_governed_write_rejects_detached_clarification_receipt_pair() -> None:
    """The MemoryPlane policy, not just its helper, rejects the loose pair."""

    backend = InMemoryMemoryPlaneStore()
    plane = MemoryPlaneService(record_store=backend)
    admissions = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest()
    )
    admission = admissions.create_initial_evidence_only(
        admission_id="writer-admission",
        writer_implementation_fingerprint="writer-fingerprint",
        graph_schema_fingerprint="schema-fingerprint",
    )
    atomic = SemanticIngestionAtomicStore(plane, admissions)
    authorization = admissions._authorize_atomic(
        admissions.commit_binding(admission), capability=atomic._write_capability
    )
    records = _clarification_terminal_pair()
    before = backend.read_snapshot()

    with pytest.raises(SemanticWriterAdmissionError):
        plane.conditionally_write_records(
            records,
            preconditions=tuple(
                RecordAbsentPrecondition(memory_id=record.memory_id)
                for record in records
            ),
            authorization=authorization,
        )

    assert backend.read_snapshot() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "foreign_kind",
        "mismatched_operation_ids",
        "wrong_prefix",
        "divergent_binding",
    ],
)
def test_no_projection_clarification_terminal_pair_rejects_every_mutated_family(
    mutation: str,
) -> None:
    transaction, receipt = _clarification_terminal_pair()
    if mutation == "missing":
        records = (transaction,)
    elif mutation == "duplicate":
        records = (transaction, receipt, receipt)
    elif mutation == "foreign_kind":
        records = (transaction, receipt.model_copy(update={"source_kind": "semantic_ingestion_event_batch"}))
    elif mutation == "mismatched_operation_ids":
        body = dict(transaction.content["transaction"])
        body["processing_operation_id"] = sha256(b"other-operation").hexdigest()
        records = (
            transaction.model_copy(
                update={
                    "content": transaction.content
                    | {
                        "semantic_transaction_digest": sha256(encode_typed_value(body)).hexdigest(),
                        "transaction": body,
                    }
                }
            ),
            receipt,
        )
    elif mutation == "wrong_prefix":
        records = (transaction, receipt.model_copy(update={"memory_id": "clarification:receipt:wrong"}))
    else:
        body = dict(transaction.content["transaction"])
        body["proposal_digest"] = sha256(b"other-proposal").hexdigest()
        records = (
            transaction.model_copy(
                update={
                    "content": transaction.content
                    | {
                        "semantic_transaction_digest": sha256(encode_typed_value(body)).hexdigest(),
                        "transaction": body,
                    }
                }
            ),
            receipt,
        )
    assert not _is_atomic_clarification_projection_write(records, [])


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
@pytest.mark.parametrize(
    "source_kind",
    [
        "semantic_ingestion_source",
        "semantic_ingestion_metadata_poor_snapshot",
        "semantic_ingestion_admission_index",
        "semantic_ingestion_profile_selection",
        "semantic_ingestion_profile_verification",
        "semantic_ingestion_profile_outcome",
    ],
)
def test_admission_records_reject_unbound_generic_writes(tmp_path: Path, backend_kind: str, source_kind: str) -> None:
    backend: MemoryPlaneStore = (
        InMemoryMemoryPlaneStore() if backend_kind == "memory" else JsonlMemoryPlaneStore(tmp_path / source_kind)
    )
    plane = MemoryPlaneService(record_store=backend)
    admissions = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    current = admissions.create_initial_evidence_only(
        admission_id="writer-admission", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    )
    forged = admissions.require_current(admissions.commit_binding(current)).model_copy(
        update={"memory_id": f"semantic_ingestion:forged:{source_kind}", "source_kind": source_kind}
    )
    before = backend.read_snapshot()
    with pytest.raises(SemanticWriterAdmissionError):
        plane.write_records((forged,))
    assert backend.read_snapshot() == before


@pytest.mark.parametrize(
    ("memory_id", "source_kind"),
    (
        *tuple(
            (f"ordinary:semantic-control-source:{index}", source_kind)
            for index, source_kind in enumerate(sorted(SEMANTIC_CONTROL_SOURCE_KINDS))
        ),
        *tuple((f"{prefix}direct-cas-probe", "ordinary") for prefix in SEMANTIC_CONTROL_ID_PREFIXES),
    ),
)
def test_every_semantic_control_source_and_namespace_rejects_direct_cas(
    memory_id: str,
    source_kind: str,
) -> None:
    backend = InMemoryMemoryPlaneStore()
    plane = MemoryPlaneService(record_store=backend)
    admissions = SemanticWriterAdmissionStore(
        plane,
        bounded_preplanning_ownership_manifest(),
    )
    admissions.create_initial_evidence_only(
        admission_id="writer-admission",
        writer_implementation_fingerprint="writer-fingerprint",
        graph_schema_fingerprint="schema-fingerprint",
    )
    forged = CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text="forged semantic control",
        content={},
        status=CommitStatus.COMMITTED,
        source_kind=source_kind,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    before = backend.read_snapshot()

    with pytest.raises(SemanticWriterAdmissionError):
        plane.conditionally_write_records(
            (forged,),
            preconditions=(RecordAbsentPrecondition(memory_id=forged.memory_id),),
        )

    assert backend.read_snapshot() == before
