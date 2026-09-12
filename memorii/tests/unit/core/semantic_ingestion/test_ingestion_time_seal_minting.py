"""Source retention seal minting proofs (M2: ingestion-time persistence).

The admission anchor is one CAS: the retained source record and its
``SourceRetentionTimeAttestation`` seal member appear and disappear together.
CAS losers mint nothing, exact redeliveries reuse the winner's seal bytes
verbatim even after the live graph revision advanced, and a tampered or
partial member fails closed. Unsealed stores keep their legacy admission
bytes with no member at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
)
from memorii.core.memory_evolution.atomic_store import (
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
    _source_retention_seal_member_id,
)
from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    SourceRetentionTimeAttestation,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_evolution.ingestion_time_clock import IngestionTimeClock
from memorii.core.memory_evolution.observation_activation_runtime import (
    validate_registered_artifact,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import record_digest
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import (
    _publication,
)

CLOCK_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
SEAL_SCHEMAS = (
    "SourceRetentionTimeAttestation",
    "TransactionGroupCommitTimeAttestation",
)


def _governed_source(timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id="semantic_ingestion:source:seal-fixture",
        domain=MemoryDomain.TRANSCRIPT,
        text="Atlas owner is Bob.",
        content={"text": "Atlas owner is Bob."},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_source",
        timestamp=timestamp,
        is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _prepared(plane: MemoryPlaneService, *, timestamp: datetime = CLOCK_NOW):
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a",
        tenant_partition_id="tenant:a",
        provider_identity="provider:test",
    )
    identity = DeliveryIdentity.create(principal, "seal-delivery")
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:a", scopes=set()
        ),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:a", scopes=set()
        ),
    )
    return GovernedSourceAdmissionService(plane).prepare_atomic(
        source=_governed_source(timestamp),
        delivery_identity=identity,
        ingress=ingress,
        operation_id="op:seal",
        evidence_only=True,
    )


def _sealed_store(tmp_path, *, seal_schemas=SEAL_SCHEMAS):
    plane = MemoryPlaneService()
    clock = [CLOCK_NOW]
    history = None if seal_schemas is None else _publication(tmp_path, schemas=seal_schemas)
    writers = SemanticWriterAdmissionStore(
        plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: clock[0],
        typed_value_registry_history=history,
    )
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="seal-writer",
            writer_implementation_fingerprint="seal-writer",
            graph_schema_fingerprint="graph",
        )
    )
    store = SemanticIngestionAtomicStore(
        plane,
        writers,
        now_provider=lambda: clock[0],
        ingestion_time_clock=IngestionTimeClock(
            identity="test-seal-clock", now_provider=lambda: clock[0]
        ),
        typed_value_registry_history=history,
    )
    return plane, store, binding, clock


def _seal_member(plane: MemoryPlaneService, prepared):
    return plane.get_record(
        _source_retention_seal_member_id(
            prepared.accepted.delivery_identity.delivery_key_digest
        )
    )


def _decoded_seal(plane: MemoryPlaneService, store, prepared) -> SourceRetentionTimeAttestation:
    member = _seal_member(plane, prepared)
    assert member is not None
    value = validate_registered_artifact(
        member.content["artifact"].encode("utf-8"),
        schema_id="SourceRetentionTimeAttestation",
        history=store._typed_value_registry_history,
        limits=store._observation_artifact_limits,
    )
    assert isinstance(value, SourceRetentionTimeAttestation)
    return value


def test_publish_admitted_source_mints_the_seal_in_the_same_cas(tmp_path) -> None:
    plane, store, binding, _clock = _sealed_store(tmp_path)
    prepared = _prepared(plane)
    member_id = _source_retention_seal_member_id(
        prepared.accepted.delivery_identity.delivery_key_digest
    )
    assert plane.get_record(member_id) is None
    accepted = store.publish_admitted_source(
        prepared=prepared, writer_binding=binding
    )
    assert accepted == prepared.accepted
    member = plane.get_record(member_id)
    retained = plane.get_record(prepared.accepted.source_id)
    assert member is not None and retained is not None
    # Member present exactly because the source record is present.
    assert member.source_kind == "semantic_ingestion_source_retention_attestation"
    assert member.content["semantic_ingestion_kind"] == "source_retention_attestation"
    assert set(member.content) == {"semantic_ingestion_kind", "artifact"}
    attestation = _decoded_seal(plane, store, prepared)
    fence = prepared.accepted.operation_fence_binding
    retained_record = next(
        record for record in prepared.records
        if record.memory_id == prepared.accepted.source_id
    )
    assert attestation.attestation_id == member_id
    assert attestation.source_id == fence.source_id
    assert attestation.operation_fence_id == fence.operation_fence_id
    # retained_at is the single M0 protected sample (the retained record
    # timestamp), never a fresh sample at mint time.
    assert attestation.retained_at == retained_record.timestamp
    assert attestation.clock_identity == "test-seal-clock"
    assert attestation.graph_revision == store.semantic_replay_state().graph_revision
    # source_record_digest covers the exact committed record and is never the
    # logical retry digest that excludes the retention timestamp.
    assert attestation.source_record_digest == record_digest(retained_record)
    from memorii.core.memory_evolution.admission import source_admission_source_digest

    assert (
        attestation.source_record_digest
        != source_admission_source_digest(retained_record)
    )
    assert attestation.attestation_digest != "0" * 64


def test_admit_source_mints_the_identical_seal_member(tmp_path) -> None:
    plane, store, binding, _clock = _sealed_store(tmp_path)
    prepared = _prepared(plane)
    publication = store.admit_source(prepared=prepared, writer_binding=binding)
    assert (
        publication.operation.operation_fence
        == prepared.accepted.operation_fence_binding
    )
    attestation = _decoded_seal(plane, store, prepared)
    member = _seal_member(plane, prepared)
    assert member is not None
    assert attestation.attestation_id == member.memory_id
    assert attestation.source_record_digest == record_digest(
        plane.get_record(prepared.accepted.source_id)
    )


def test_unsealed_store_admits_without_any_member(tmp_path) -> None:
    plane, store, binding, _clock = _sealed_store(tmp_path, seal_schemas=None)
    prepared = _prepared(plane)
    store.publish_admitted_source(prepared=prepared, writer_binding=binding)
    assert _seal_member(plane, prepared) is None
    assert plane.get_record(prepared.accepted.source_id) is not None


def test_publish_cas_loser_mints_no_seal(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    plane, store, binding, _clock = _sealed_store(tmp_path)
    prepared = _prepared(plane)
    member_id = _source_retention_seal_member_id(
        prepared.accepted.delivery_identity.delivery_key_digest
    )
    store.publish_admitted_source(prepared=prepared, writer_binding=binding)
    winner_member = plane.get_record(member_id)
    records_after_winner = plane.list_records()

    # Force the loser through the CAS-conflict branch: its pre-check reads no
    # existing records, so it re-attempts the full CAS and loses it. Only the
    # pre-check is blinded; the post-conflict exactness reads see the winner.
    real_get = plane.get_record
    hidden = {record.memory_id for record in prepared.records} | {winner_member.memory_id}
    hidden_reads = [0]

    def hiding_get(memory_id):
        if memory_id in hidden:
            hidden_reads[0] += 1
            if hidden_reads[0] <= len(hidden):
                return None
        return real_get(memory_id)

    monkeypatch.setattr(plane, "get_record", hiding_get)
    loser_result = store.publish_admitted_source(
        prepared=prepared, writer_binding=binding
    )
    monkeypatch.undo()
    assert loser_result == prepared.accepted
    # The loser minted nothing: the winner's bytes are the complete set.
    assert plane.get_record(member_id) == winner_member
    assert plane.list_records() == records_after_winner


def test_exact_redelivery_reuses_winner_seal_bytes_after_graph_revision(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane, store, binding, clock = _sealed_store(tmp_path)
    prepared = _prepared(plane)
    member_id = _source_retention_seal_member_id(
        prepared.accepted.delivery_identity.delivery_key_digest
    )
    store.publish_admitted_source(prepared=prepared, writer_binding=binding)
    winner_member = plane.get_record(member_id)
    records_after_winner = plane.list_records()

    # Redelivery arrives after the live graph revision advanced and the
    # protected clock moved: neither may break the exact committed retry or
    # relabel the winner's seal. The graph revision is descriptive only.
    clock[0] = CLOCK_NOW + timedelta(days=30)
    advanced = SimpleNamespace(graph_revision="revision:advanced")
    monkeypatch.setattr(
        SemanticIngestionAtomicStore, "semantic_replay_state", lambda self: advanced
    )
    store._ingestion_time_seal_authority_cache = None
    recovered = store.publish_admitted_source(
        prepared=prepared, writer_binding=binding
    )
    monkeypatch.undo()
    assert recovered == prepared.accepted
    assert plane.get_record(member_id) == winner_member
    assert plane.list_records() == records_after_winner


def test_tampered_seal_member_fails_the_redelivery_closed(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane, store, binding, _clock = _sealed_store(tmp_path)
    prepared = _prepared(plane)
    member_id = _source_retention_seal_member_id(
        prepared.accepted.delivery_identity.delivery_key_digest
    )
    store.publish_admitted_source(prepared=prepared, writer_binding=binding)
    winner = plane.get_record(member_id)
    assert winner is not None
    substituted = winner.model_copy(
        update={"content": {**winner.content, "artifact": "{}"}}
    )
    real_get = plane.get_record
    monkeypatch.setattr(
        plane,
        "get_record",
        lambda memory_id: substituted if memory_id == member_id else real_get(memory_id),
    )
    with pytest.raises(
        PreplanningStoreError, match="partial or mismatched"
    ):
        store.publish_admitted_source(prepared=prepared, writer_binding=binding)
    # Guard-deletion control: with the exactness validator deleted, the same
    # tampered redelivery would silently pass, proving the guard is the
    # load-bearing check.
    monkeypatch.setattr(
        SemanticIngestionAtomicStore,
        "_validate_retention_seal_member",
        lambda self, existing, proposed: True,
    )
    assert (
        store.publish_admitted_source(prepared=prepared, writer_binding=binding)
        == prepared.accepted
    )


def test_partial_publication_without_a_member_fails_closed(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane, store, binding, _clock = _sealed_store(tmp_path)
    prepared = _prepared(plane)
    member_id = _source_retention_seal_member_id(
        prepared.accepted.delivery_identity.delivery_key_digest
    )
    store.publish_admitted_source(prepared=prepared, writer_binding=binding)
    real_get = plane.get_record
    monkeypatch.setattr(
        plane,
        "get_record",
        lambda memory_id: None if memory_id == member_id else real_get(memory_id),
    )
    with pytest.raises(PreplanningStoreError, match="partial or mismatched"):
        store.publish_admitted_source(prepared=prepared, writer_binding=binding)


def test_terminal_digest_accessor_joins_the_sealed_member(tmp_path) -> None:
    plane, store, binding, _clock = _sealed_store(tmp_path)
    prepared = _prepared(plane)
    store.publish_admitted_source(prepared=prepared, writer_binding=binding)
    fence = prepared.accepted.operation_fence_binding
    digest = store.source_retention_attestation_digest(
        delivery_key_digest=prepared.accepted.delivery_identity.delivery_key_digest,
        operation_fence=fence,
    )
    assert digest == _decoded_seal(plane, store, prepared).attestation_digest
    # An unrelated fence cannot join the sealed member.
    with pytest.raises(PreplanningStoreError, match="substituted"):
        store.source_retention_attestation_digest(
            delivery_key_digest=prepared.accepted.delivery_identity.delivery_key_digest,
            operation_fence=fence.model_copy(update={"operation_fence_id": "other:fence"}),
        )


def test_noncommitting_schema3_outcome_is_explicit_null_without_a_member(
    tmp_path,
) -> None:
    """Schema-3 noncommitting closure (contract + reload failpoint).

    The composed-provider fixtures abort an all-unavailable plan before the
    group CAS, so the noncommitting-with-seal closure is proven at the two
    boundaries that enforce it: the schema-3 core contract accepts exactly
    null (and serializes it explicitly), and the reload verification branch
    accepts only null-plus-no-member.
    """

    from tests.unit.core.semantic_ingestion.test_group_result_attestation_schemas import (
        _clause_core,
        _construct_core,
    )

    core = _clause_core("noncommitting", None)
    assert core.validate_core() is not None
    # The null binding serializes explicitly (never an omitted field).
    assert (
        _construct_core(3, "noncommitting", None).model_dump()[
            "transaction_group_commit_attestation_digest"
        ]
        is None
    )

    plane, store, _binding, _clock = _sealed_store(tmp_path)
    primary = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:bootstrap-graph-v3:group-commit:" + "a" * 64,
        domain=MemoryDomain.EXECUTION,
        text="",
        content={},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary",
        timestamp=CLOCK_NOW,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    member_id = primary.memory_id + ":group_commit_attestation"
    orphan = primary.model_copy(
        update={
            "memory_id": member_id,
            "source_kind": "semantic_ingestion_transaction_group_commit_attestation",
            "content": {
                "semantic_ingestion_kind": "transaction_group_commit_attestation",
                "artifact": "{}",
            },
        }
    )

    def reload_with(digest):
        return SimpleNamespace(
            group_result_schema_version=3,
            ledger_entry_id="entry",
            ledger_entry_digest="b" * 64,
            persisted_result=SimpleNamespace(
                core=SimpleNamespace(
                    disposition="noncommitting",
                    transaction_group_commit_attestation_digest=digest,
                ),
            ),
        )

    request = SimpleNamespace()
    snapshot = {primary.memory_id: primary}
    # Explicit null with no member is the one accepted noncommitting closure.
    store._verify_group_commit_seal_snapshot(
        primary, reload_with(None), request, snapshot_records=snapshot
    )
    # An orphan member on a noncommitting result is a partial publication.
    with pytest.raises(PreplanningStoreError, match="noncommitting result"):
        store._verify_group_commit_seal_snapshot(
            primary,
            reload_with(None),
            request,
            snapshot_records={**snapshot, member_id: orphan},
        )
    # A non-null digest on a noncommitting result is equally rejected.
    with pytest.raises(PreplanningStoreError, match="noncommitting result"):
        store._verify_group_commit_seal_snapshot(
            primary, reload_with("c" * 64), request, snapshot_records=snapshot
        )
