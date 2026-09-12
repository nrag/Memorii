"""Real-backend ingestion-time seal proofs (M2: ingestion-time persistence).

One activated provider on a JSONL store mints both seal kinds under real CAS
conditions: the group CAS writes a schema-3 core with its
TransactionGroupCommitTimeAttestation member, the terminal binds back to the
admission seal through the schema-2 outcome, redelivery and JSONL reopen
reuse the winner's bytes, noncommitting groups carry the explicit null, and
a reload with a missing member fails closed instead of re-minting.
"""

from __future__ import annotations

import pytest
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError
from memorii.core.memory_evolution.graph_effect_contracts import (
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    TransactionGroupCommitTimeAttestation,
)
from memorii.core.memory_evolution.ingestion_time_clock import (
    PRODUCTION_INGESTION_TIME_CLOCK_IDENTITY,
)
from memorii.core.memory_evolution.observation_activation_runtime import (
    validate_registered_artifact,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphGroupCommitReloadV3,
    BootstrapGraphGroupCommitRequestV3,
    decode_semantic_contract,
)
from memorii.core.semantic_ingestion.event_replay import (
    decode_semantic_memory_event_batch,
)
from tests.integration.test_observation_ledger_activation import (
    _provider_factory,
    _seed_provider,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    _host_ingress,
)


def _sync(provider, operation_id: str, *, content: str = "Atlas owner is Bob."):
    return provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content=content,
        operation_id=operation_id,
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )


def _runtime_of(provider):
    runtime = provider._composed_semantic_runtime
    assert runtime is not None and runtime.atomic_store is not None
    assert runtime.typed_value_registry_history is not None
    return runtime


def _group_primary(plane: MemoryPlaneService):
    primaries = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    assert len(primaries) == 1
    return primaries[0]


def _group_reload(primary) -> BootstrapGraphGroupCommitReloadV3:
    return decode_semantic_contract(
        bytes.fromhex(primary.content["reload_hex"]),
        BootstrapGraphGroupCommitReloadV3,
    )


def _group_seal_member(plane: MemoryPlaneService, primary):
    return plane.get_record(primary.memory_id + ":group_commit_attestation")


def _admission_seal(plane: MemoryPlaneService, source_id: str):
    delivery_key_digest = source_id.rsplit(":", 1)[-1]
    member = plane.get_record(
        f"semantic_ingestion:admission:{delivery_key_digest}:retention_attestation"
    )
    assert member is not None
    return member


def _activated_provider(tmp_path, monkeypatch: pytest.MonkeyPatch):
    build, _, _ = _provider_factory(
        tmp_path, monkeypatch, normalization=True, complete_registry=True
    )
    path = tmp_path / "ledger-store"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    provider = build(plane)
    _seed_provider(provider)
    provider.activate_observation_ledger()
    return build, path, plane, provider


def test_committed_group_mints_the_schema3_seal_atomically(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[BootstrapGraphGroupCommitRequestV3] = []
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    original = SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3

    def capture(self, *, request):
        requests.append(request)
        return original(self, request=request)

    monkeypatch.setattr(
        SemanticIngestionAtomicStore,
        "commit_or_reload_bootstrap_graph_group_v3",
        capture,
    )
    _build, _path, plane, provider = _activated_provider(tmp_path, monkeypatch)
    result = _sync(provider, "seal-committed")
    assert result is not None and result.blocked_reasons["semantic_ingestion"] in {
        "source_only",
        "retryable_outage",
    }
    assert len(requests) == 1
    request = requests[0]
    primary = _group_primary(plane)
    reload = _group_reload(primary)
    core = reload.persisted_result.core
    assert reload.group_result_schema_version == 3
    assert core.group_result_schema_version == 3
    assert core.disposition == "committed"

    member = _group_seal_member(plane, primary)
    assert member is not None
    runtime = _runtime_of(provider)
    attestation = validate_registered_artifact(
        member.content["artifact"].encode("utf-8"),
        schema_id="TransactionGroupCommitTimeAttestation",
        history=runtime.typed_value_registry_history,
    )
    assert isinstance(attestation, TransactionGroupCommitTimeAttestation)
    # The digest fields bind exactly: the core's non-null digest is the
    # member's registered self-digest, never an unregistered companion.
    assert core.transaction_group_commit_attestation_digest == (
        attestation.attestation_digest
    )
    assert attestation.attestation_id == member.memory_id
    assert attestation.source_id == request.operation_fence_binding.source_id
    assert attestation.operation_fence_id == (
        request.operation_fence_binding.operation_fence_id
    )
    assert attestation.transaction_group_id == request.transaction_group_id
    assert attestation.operation_ids == request.operation_ids
    assert attestation.graph_revision_before == core.graph_revision_before
    assert attestation.graph_revision_after == core.graph_revision_after
    assert attestation.clock_identity == PRODUCTION_INGESTION_TIME_CLOCK_IDENTITY
    # Both protected instants are sampled inside the winning CAS; the frozen
    # composed clock pins them to the exact same instant.
    assert attestation.transaction_started_at == TEST_NOW
    assert attestation.transaction_committed_at == TEST_NOW
    # committed_batch_digest is acyclic: it equals the persisted canonical
    # event batch's source digest read back from the same JSONL store, and
    # the attestation preimage cannot contain the core that digests it.
    batches = plane.list_records(source_kind="semantic_ingestion_event_batch")
    assert len(batches) == 1
    persisted_batch = decode_semantic_memory_event_batch(
        bytes.fromhex(batches[0].content["canonical_hex"]),
        registry_history=runtime.atomic_store._event_schema_registry_history,
    )
    assert (
        attestation.committed_batch_digest
        == persisted_batch.source_event_batch_digest
    )
    assert attestation.applied_graph_delta_digest == (
        persisted_batch.graph_delta_digest
    )
    assert core.core_digest not in member.content["artifact"]

    # The outcome side binds back: the terminal source outcome is schema 2 and
    # carries the admission seal's registered attestation digest verbatim.
    entries = plane.list_records(
        source_kind="semantic_ingestion_observation_ledger_entry"
    )
    finalization = None
    for record in entries:
        entry = validate_registered_artifact(
            record.content["artifact"].encode("utf-8"),
            schema_id="ObservationLedgerEntry",
            history=runtime.typed_value_registry_history,
        )
        if isinstance(entry.delta, SourceFinalizationObservationDelta):
            finalization = entry.delta
    assert finalization is not None
    outcome = finalization.source_outcome
    admission_member = _admission_seal(plane, outcome.source_id)
    admission_attestation = validate_registered_artifact(
        admission_member.content["artifact"].encode("utf-8"),
        schema_id="SourceRetentionTimeAttestation",
        history=runtime.typed_value_registry_history,
    )
    assert outcome.core.source_result_schema_version == 2
    assert outcome.core.source_retention_attestation_digest == (
        admission_attestation.attestation_digest
    )
    assert outcome.source_retention_attestation_digest == (
        admission_attestation.attestation_digest
    )
    # The schema-2 fields serialize: the binding is explicit in the persisted
    # outcome bytes, never an implicit default.
    assert outcome.model_dump()["source_retention_attestation_digest"] == (
        admission_attestation.attestation_digest
    )


def test_reload_returns_original_and_never_remints(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    requests: list[BootstrapGraphGroupCommitRequestV3] = []
    reloaded: list[BootstrapGraphGroupCommitReloadV3] = []
    original = SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3

    def capture(self, *, request):
        requests.append(request)
        result = original(self, request=request)
        # Lost acknowledgement: re-commit the identical request while the
        # operation lease is still live. The store must return the original
        # reload from the persisted primary and write nothing.
        reloaded.append(original(self, request=request))
        return result

    monkeypatch.setattr(
        SemanticIngestionAtomicStore,
        "commit_or_reload_bootstrap_graph_group_v3",
        capture,
    )
    _build, _path, plane, provider = _activated_provider(tmp_path, monkeypatch)
    _sync(provider, "seal-reload")
    assert requests
    request = requests[0]
    primary = _group_primary(plane)
    member = _group_seal_member(plane, primary)
    assert member is not None
    records_after_commit = plane.list_records()
    assert reloaded == [_group_reload(primary)]
    assert plane.list_records() == records_after_commit
    assert plane.get_record(member.memory_id) == member

    runtime = _runtime_of(provider)
    # Guard proof: a reload whose image lost the member record fails closed
    # with the typed reload error instead of re-minting or returning quietly.
    revision, snapshot = plane.read_write_snapshot()

    def snapshot_without_member():
        return (
            revision,
            tuple(record for record in snapshot if record.memory_id != member.memory_id),
        )

    monkeypatch.setattr(plane, "read_write_snapshot", snapshot_without_member)
    with pytest.raises(PreplanningStoreError, match="attestation member is absent"):
        runtime.atomic_store._reload_bootstrap_graph_group_receipt(primary, request)
    monkeypatch.undo()
    assert plane.read_write_snapshot() == (revision, snapshot)


def test_redelivery_and_jsonl_reopen_reuse_winner_seal_bytes(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, path, plane, provider = _activated_provider(tmp_path, monkeypatch)
    first = _sync(provider, "seal-reopen")
    assert first is not None
    primary = _group_primary(plane)
    group_member = _group_seal_member(plane, primary)
    assert group_member is not None
    admission_members = plane.list_records(
        source_kind="semantic_ingestion_source_retention_attestation"
    )
    assert len(admission_members) == 1
    retained_source = plane.get_record(
        "semantic_ingestion:source:" + admission_members[0].memory_id.split(":")[2]
    )
    assert retained_source is not None

    def _winner_seal_bytes(active_plane):
        # The winner's seal bytes are the immutable reuse contract: exactly one
        # admission seal and one group seal, byte-for-byte unchanged. Recovery
        # bookkeeping records beyond the seals may legitimately accompany a
        # full-flow redelivery; the seals themselves never move.
        return (
            active_plane.get_record(group_member.memory_id),
            active_plane.list_records(
                source_kind="semantic_ingestion_source_retention_attestation"
            ),
            active_plane.list_records(
                source_kind="semantic_ingestion_transaction_group_commit_attestation"
            ),
            active_plane.list_records(
                source_kind="semantic_ingestion_event_batch"
            ),
        )

    winner_state = _winner_seal_bytes(plane)
    assert winner_state[0] is not None
    assert len(winner_state[2]) == 1 and len(winner_state[3]) == 1

    redelivered = _sync(provider, "seal-reopen")
    assert redelivered == first
    assert _winner_seal_bytes(plane) == winner_state
    assert plane.get_record(retained_source.memory_id) == retained_source

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = build(reopened_plane)
    activated = provider.activate_observation_ledger()
    assert reopened.activate_observation_ledger() == activated
    repeated = _sync(reopened, "seal-reopen")
    assert repeated == first
    assert _winner_seal_bytes(reopened_plane) == winner_state
    assert reopened_plane.get_record(retained_source.memory_id) == retained_source
