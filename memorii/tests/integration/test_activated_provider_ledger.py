"""The ordinary provider must append and recover after ledger activation."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.graph_observation_cohort import resolve_observation_membership
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_paging import ObservationCohortUnavailableError
from memorii.core.memory_evolution.graph_observation_public_contracts import AuthenticatedGraphObservationContext
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.models import ProviderOperation
from tests.integration.test_observation_ledger_activation import _provider_factory, _seed_provider
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import _host_ingress


def test_activated_provider_ingests_and_reopens_global_ledger(tmp_path, monkeypatch):
    build, _, _ = _provider_factory(tmp_path, monkeypatch, normalization=True, complete_registry=True)
    path = tmp_path / "ledger-store"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    provider = build(plane)
    _seed_provider(provider)
    activated = provider.activate_observation_ledger()
    result = provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="activated-source", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    entries = plane.list_records(source_kind="semantic_ingestion_observation_ledger_entry")
    assert len(entries) == 2
    assert result is not None
    runtime = provider._composed_semantic_runtime
    assert runtime is not None and runtime.typed_value_registry_history is not None
    history = runtime.typed_value_registry_history
    from memorii.core.memory_evolution.graph_effect_contracts import (
        IngestionObservationDelta,
        SourceFinalizationObservationDelta,
    )
    from memorii.core.memory_evolution.observation_activation_runtime import validate_registered_artifact
    from memorii.core.memory_evolution.observation_ledger_contracts import (
        ObservationGroupResultLocator,
        ObservationLedgerEntry,
        ObservationSourceResultLocator,
    )
    def decode_entry(record):
        entry = validate_registered_artifact(
            record.content["artifact"].encode("utf-8"), schema_id="ObservationLedgerEntry",
            history=history,
        )
        assert isinstance(entry, ObservationLedgerEntry)
        return entry
    decoded = sorted(map(decode_entry, entries), key=lambda entry: entry.sequence)
    assert [entry.sequence for entry in decoded] == [1, 2]
    assert isinstance(decoded[0].result_locator, ObservationGroupResultLocator)
    assert isinstance(decoded[1].result_locator, ObservationSourceResultLocator)
    assert isinstance(decoded[0].delta, IngestionObservationDelta)
    assert isinstance(decoded[1].delta, SourceFinalizationObservationDelta)
    assert decoded[0].delta.graph_revision_delta_digest is not None
    assert decoded[1].previous_entry_digest == decoded[0].entry_digest
    assert runtime.atomic_store is not None
    revision, records = plane.read_write_snapshot()
    snapshot_time = datetime(2026, 9, 8, tzinfo=UTC)
    def clock_must_not_be_resampled():
        raise AssertionError("detached graph authority resampled the live clock")
    with monkeypatch.context() as detached_clock:
        detached_clock.setattr(runtime.atomic_store, "_now", clock_must_not_be_resampled)
        authority = runtime.atomic_store.read_detached_observation_authority(
            write_revision=revision, records=records, snapshot_created_at=snapshot_time,
        )
    assert authority.graph.system_as_of == snapshot_time
    source_id = decoded[0].delta.source_id
    context = AuthenticatedGraphObservationContext(
        principal_subject_id="user:alice",
        tenant_partition_id=decoded[1].delta.required_outcome_scopes.tenant_partition_id,
        authorized_scope_set_digest="a" * 64, authentication_session_id="test-session",
        context_digest="b" * 64,
    )
    grant = MemoryScope(user_id="user:alice", task_id="task:one")
    selector = GraphObservationCohortSelector(
        seed_source_ids=(source_id,), seed_operation_ids=(), include_referenced_boundary_entities=True,
    )
    membership = resolve_observation_membership(authority, context, grant, selector)
    assert membership.source_ids == (source_id,)
    assert membership.operation_ids == decoded[0].delta.operation_ids
    assert len(membership.graph_deltas) == 1
    assert len(authority.group_requests) == 1
    operation_membership = resolve_observation_membership(
        authority, context, grant, GraphObservationCohortSelector(
            seed_source_ids=(), seed_operation_ids=membership.operation_ids,
            include_referenced_boundary_entities=True,
        ),
    )
    assert operation_membership.source_finalizations == membership.source_finalizations
    with pytest.raises(ObservationCohortUnavailableError, match="scope"):
        resolve_observation_membership(authority, context, MemoryScope(user_id="user:other"), selector)
    with pytest.raises(ObservationCohortUnavailableError, match="graph closure"):
        resolve_observation_membership(replace(authority, graph_deltas=()), context, grant, selector)
    first_entries = {record.memory_id: record for record in entries}
    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="later-source", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    persisted = {record.memory_id: record for record in plane.list_records(
        source_kind="semantic_ingestion_observation_ledger_entry"
    )}
    assert len(persisted) == 4
    assert all(persisted[identity] == record for identity, record in first_entries.items())
    # A detached read remains pinned after the live writer advances.
    assert resolve_observation_membership(authority, context, grant, selector) == membership
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = build(reopened_plane)
    assert reopened.activate_observation_ledger() == activated
    assert {record.memory_id: record for record in reopened_plane.list_records(
        source_kind="semantic_ingestion_observation_ledger_entry"
    )} == persisted
    repeated = reopened.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="activated-source", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert repeated == result
    assert {record.memory_id: record for record in reopened_plane.list_records(
        source_kind="semantic_ingestion_observation_ledger_entry"
    )} == persisted
