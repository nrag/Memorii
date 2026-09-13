"""Lexical canonical-emission lifetime for detached observation reads."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Barrier, Thread

import pytest
from memorii.core.memory_evolution import ingestion_contracts
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value, encode_typed_value
from memorii.core.semantic_ingestion import canonical_evidence_arena


class _StopDetachedRead(Exception):
    pass


def test_detached_read_scopes_exact_raw_replay_to_one_call(monkeypatch) -> None:
    store = object.__new__(SemanticIngestionAtomicStore)
    raw = encode_typed_value({"artifact": b"same registered bytes"})
    reencode_calls = 0
    pushes: list[object] = []
    pops: list[object] = []
    original_normalize = ingestion_contracts._normalized_typed_json
    original_push = ingestion_contracts.push_emission_scope
    original_pop = ingestion_contracts.pop_emission_scope

    def count_normalize(*args, **kwargs):
        nonlocal reencode_calls
        if isinstance(args[0], dict):
            reencode_calls += 1
        return original_normalize(*args, **kwargs)

    def track_push(scope):
        pushes.append(scope)
        original_push(scope)

    def track_pop(scope):
        pops.append(scope)
        original_pop(scope)

    def replay(**_kwargs):
        assert decode_typed_value(raw) == decode_typed_value(raw)
        raise _StopDetachedRead

    monkeypatch.setattr(ingestion_contracts, "_normalized_typed_json", count_normalize)
    monkeypatch.setattr(ingestion_contracts, "push_emission_scope", track_push)
    monkeypatch.setattr(ingestion_contracts, "pop_emission_scope", track_pop)
    monkeypatch.setattr(store, "_replay_schema3_observation_ledger", replay)

    for _ in range(2):
        with pytest.raises(_StopDetachedRead):
            store.read_detached_observation_authority(
                write_revision=0,
                records=(),
                snapshot_created_at=datetime(2026, 9, 13, tzinfo=UTC),
            )

    # Each detached read owns one push/pop pair.  Repeated raw bytes reuse a
    # verdict inside a read, but the next detached image starts clean.
    assert pushes == pops
    assert len(pushes) == 2
    assert reencode_calls == 2


def test_detached_read_uses_lexical_digest_scope_without_constructing_an_arena(monkeypatch) -> None:
    store = object.__new__(SemanticIngestionAtomicStore)
    pushes: list[object] = []
    pops: list[object] = []
    original_push = canonical_evidence_arena._push_digest_verification_scope
    original_pop = canonical_evidence_arena._pop_digest_verification_scope

    def track_push(scope):
        pushes.append(scope)
        original_push(scope)

    def track_pop(scope):
        pops.append(scope)
        original_pop(scope)

    class _ArenaMustNotBeConstructed:
        def __init__(self, *args, **kwargs):
            raise AssertionError("detached read must not construct an evidence arena")

    def replay(**_kwargs):
        assert canonical_evidence_arena.current_digest_verification_scope() is pushes[0]
        raise _StopDetachedRead

    monkeypatch.setattr(canonical_evidence_arena, "_push_digest_verification_scope", track_push)
    monkeypatch.setattr(canonical_evidence_arena, "_pop_digest_verification_scope", track_pop)
    monkeypatch.setattr(canonical_evidence_arena, "CanonicalEvidenceArena", _ArenaMustNotBeConstructed)
    monkeypatch.setattr(store, "_replay_schema3_observation_ledger", replay)

    with pytest.raises(_StopDetachedRead):
        store.read_detached_observation_authority(
            write_revision=0,
            records=(),
            snapshot_created_at=datetime(2026, 9, 13, tzinfo=UTC),
        )

    assert pushes == pops
    assert len(pushes) == 1
    assert canonical_evidence_arena.current_digest_verification_scope() is None


def test_canonical_emission_scopes_do_not_cross_threads() -> None:
    """A simultaneous detached-read scope never reuses another thread's memo."""
    barrier = Barrier(2)
    observed: list[object] = []

    def enter_scope() -> None:
        with ingestion_contracts.canonical_emission_scope() as scope:
            barrier.wait()
            assert ingestion_contracts.current_emission_scope() is scope
            observed.append(scope)
        assert ingestion_contracts.current_emission_scope() is None

    workers = [Thread(target=enter_scope), Thread(target=enter_scope)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert len(observed) == 2
    assert observed[0] is not observed[1]
