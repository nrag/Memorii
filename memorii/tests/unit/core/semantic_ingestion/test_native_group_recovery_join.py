"""Recovery must join its own entry even after the complete-prefix check passes."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution import atomic_store
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import CommitStatus, MemoryDomain


@pytest.mark.parametrize("entry_present", (False, True))
def test_recovery_rejects_dangling_or_substituted_receipt_entry(monkeypatch, entry_present):
    # Isolate the post-decode join: artifact and complete-prefix validation have
    # their own registered integration tests. Neither supplies this receipt join.
    receipt = SimpleNamespace(
        group_result_schema_version=2, ledger_entry_id="entry", ledger_entry_digest="a" * 64,
    )
    monkeypatch.setattr(atomic_store, "_bootstrap_graph_v3_group_commit_reload_from_record", lambda *_: receipt)
    monkeypatch.setattr(atomic_store, "_ledger_entry_from_record", lambda *args, **kwargs: SimpleNamespace(entry_digest="b" * 64))
    replayed = []
    monkeypatch.setattr(SemanticIngestionAtomicStore, "_replay_schema3_observation_ledger", lambda *args, **kwargs: replayed.append(True))

    def record(identity):
        return CanonicalMemoryRecord(
            memory_id=identity, domain=MemoryDomain.EXECUTION, text="", content={},
            status=CommitStatus.COMMITTED, source_kind="test", timestamp=datetime(2026, 9, 8, tzinfo=UTC),
        )

    primary = record("primary")
    plane = MemoryPlaneService()
    plane.write_records((primary, record("entry")) if entry_present else (primary,))
    store = object.__new__(SemanticIngestionAtomicStore)
    store._memory_plane = plane
    store._typed_value_registry_history = None
    store._observation_artifact_limits = None
    with pytest.raises(atomic_store.PreplanningStoreError, match="ledger entry is (absent|substituted)"):
        store._reload_bootstrap_graph_group_receipt(primary, object())
    assert replayed == [True]
