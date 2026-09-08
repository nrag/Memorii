"""The ordinary provider must append and recover after ledger activation."""

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
    from memorii.core.memory_evolution.graph_effect_contracts import IngestionObservationDelta
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
    assert decoded[0].delta.graph_revision_delta_digest is not None
    assert decoded[1].previous_entry_digest == decoded[0].entry_digest
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
