from __future__ import annotations

from hashlib import sha256
from threading import Barrier, Thread

import pytest
from memorii.core.semantic_ingestion.canonical_evidence_arena import (
    CANONICAL_CODEC_REVISION,
    CANONICAL_PROFILE_REVISION,
    MAX_ARENA_CHARGED_BYTES,
    MAX_ARENA_ENTRIES,
    MAX_CANONICAL_BYTES_PER_ENTRY,
    CanonicalBinding,
    CanonicalClosureObservabilityDispatcher,
    CanonicalEvidenceArena,
    CanonicalMemberIndex,
    CanonicalValidationScope,
    RetainingCanonicalClosureObservabilityDispatcher,
    ValidatedCanonicalEvidenceResult,
)
from memorii.core.semantic_ingestion.contracts import (
    RetainedSourceTextArtifact,
    SemanticContractCodecError,
    encode_semantic_contract,
    encode_semantic_contract_result,
)


def _artifact(*, artifact_id: str = "artifact") -> RetainedSourceTextArtifact:
    return RetainedSourceTextArtifact.create(
        artifact_id=artifact_id,
        content_digest="0" * 64,
        unicode_scalar_length=0,
    )


def _admit(arena: CanonicalEvidenceArena, value: RetainedSourceTextArtifact, raw: bytes) -> bool:
    return arena.admit_success(
        canonical_contract_bytes=raw,
        concrete_contract_type=type(value),
        profile_revision=CANONICAL_PROFILE_REVISION,
        codec_revision=CANONICAL_CODEC_REVISION,
        domain=b"domain",
        result=ValidatedCanonicalEvidenceResult(
            contract=value,
            canonical_contract_bytes=raw,
            canonical_member_index=CanonicalMemberIndex(
                contract_type=f"{type(value).__module__}.{type(value).__qualname__}",
                member_paths=1,
                canonical_digest=sha256(raw).hexdigest(),
            ),
            validation_provenance=("test",),
        ),
    )


def _sealed_arena_with_entry(
    *, dispatcher: CanonicalClosureObservabilityDispatcher | None = None,
) -> tuple[CanonicalEvidenceArena, RetainedSourceTextArtifact, bytes, CanonicalBinding]:
    value = _artifact()
    raw = b"canonical"
    arena = CanonicalEvidenceArena(
        scope=CanonicalValidationScope("tenant", "operation", 1, "fence", "writer"),
        observability_dispatcher=dispatcher,
    )
    assert _admit(arena, value, raw)
    return arena, value, raw, arena.seal()


def _lookup(
    arena: CanonicalEvidenceArena,
    value: RetainedSourceTextArtifact,
    raw: bytes,
    binding: CanonicalBinding,
):
    return arena.lookup_sealed(
        binding=binding,
        scope=arena.scope,
        canonical_contract_bytes=raw,
        concrete_contract_type=type(value),
        profile_revision=CANONICAL_PROFILE_REVISION,
        codec_revision=CANONICAL_CODEC_REVISION,
        domain=b"domain",
    )


def test_codec_does_not_reuse_ambient_preseal_arena_entries() -> None:
    value = _artifact()
    with CanonicalEvidenceArena() as arena:
        first = encode_semantic_contract(value)
        second = encode_semantic_contract(value)
        snapshot = arena.snapshot()
        assert first == second
        assert snapshot.entries == 0
        assert snapshot.hits == 0

    assert arena.snapshot().closed
    assert arena.snapshot().entries == 0


def test_nonce_and_arena_identity_fail_closed() -> None:
    first = CanonicalEvidenceArena()
    second = CanonicalEvidenceArena()
    with first, pytest.raises(ValueError, match="stale or substituted"):
        first.require_active_nonce(second.nonce)
    second.close()


def test_disabled_arena_allows_nonce_validation_for_full_fallback_path() -> None:
    with CanonicalEvidenceArena(enabled=False) as arena:
        arena.require_active_nonce(arena.nonce)


def test_capacity_rejected_arena_allows_nonce_validation_for_full_fallback_path() -> None:
    arenas = [CanonicalEvidenceArena() for _ in range(5)]
    try:
        rejected = arenas[-1]
        with rejected:
            rejected.require_active_nonce(rejected.nonce)
    finally:
        for arena in arenas:
            arena.close()


def test_invalid_contract_never_populates_success_entry() -> None:
    forged = _artifact().model_copy(update={"artifact_digest": "f" * 64})
    with CanonicalEvidenceArena() as arena:
        with pytest.raises(SemanticContractCodecError):
            encode_semantic_contract(forged)
        assert arena.snapshot().entries == 0


def test_entry_count_and_single_entry_byte_limits_fall_back_without_eviction() -> None:
    value = _artifact()
    with CanonicalEvidenceArena() as arena:
        for index in range(MAX_ARENA_ENTRIES):
            assert _admit(arena, value, index.to_bytes(2, "big"))
        assert not _admit(arena, value, b"overflow")
        assert arena.snapshot().entries == 0
        assert arena.snapshot().mode == "capacity_rejected_full_path"

    with CanonicalEvidenceArena() as arena:
        assert not _admit(arena, value, b"x" * (MAX_CANONICAL_BYTES_PER_ENTRY + 1))
        assert arena.snapshot().entries == 0
        assert arena.snapshot().capacity_fallbacks == 1


def test_concurrent_arena_cannot_read_another_arena_entry() -> None:
    value = _artifact()
    raw = b"canonical"
    first = CanonicalEvidenceArena()
    second = CanonicalEvidenceArena()
    try:
        with first:
            assert _admit(first, value, raw)
        with second, pytest.raises(ValueError, match="sealed authority"):
            second.lookup(
                canonical_contract_bytes=raw,
                concrete_contract_type=type(value),
                profile_revision="profile-v1",
                codec_revision="codec-v1",
                domain=b"domain",
            )
    finally:
        first.close()
        second.close()


def test_operation_charge_rejects_first_entry_above_budget_without_eviction() -> None:
    value = _artifact()
    domain = b"domain"
    per_entry_charge = MAX_CANONICAL_BYTES_PER_ENTRY + len(domain) + 512
    accepted = MAX_ARENA_CHARGED_BYTES // per_entry_charge
    with CanonicalEvidenceArena() as arena:
        for index in range(accepted):
            raw = index.to_bytes(2, "big") + b"x" * (MAX_CANONICAL_BYTES_PER_ENTRY - 2)
            assert _admit(arena, value, raw)
        before = arena.snapshot()
        overflow = accepted.to_bytes(2, "big") + b"x" * (MAX_CANONICAL_BYTES_PER_ENTRY - 2)
        assert not _admit(arena, value, overflow)
        after = arena.snapshot()
        assert after.entries == 0
        assert after.charged_bytes == 0
        assert after.capacity_fallbacks == before.capacity_fallbacks + 1


def test_process_reservation_rejects_fifth_arena_and_recovers_after_close() -> None:
    arenas = [CanonicalEvidenceArena() for _ in range(5)]
    try:
        assert sum(arena.snapshot().reservation_acquired for arena in arenas) == 4
        assert not arenas[-1].snapshot().reservation_acquired
    finally:
        for arena in arenas:
            arena.close()
    replacement = CanonicalEvidenceArena()
    try:
        assert replacement.snapshot().reservation_acquired
    finally:
        replacement.close()


def test_exception_teardown_is_idempotent_and_returns_reservation() -> None:
    arena = CanonicalEvidenceArena()
    with pytest.raises(RuntimeError, match="abort"), arena:
        raise RuntimeError("abort")
    arena.close()
    assert arena.snapshot().closed
    replacement = CanonicalEvidenceArena()
    try:
        assert replacement.snapshot().reservation_acquired
    finally:
        replacement.close()


def test_concurrent_contexts_keep_nonce_and_entries_operation_local() -> None:
    barrier = Barrier(2)
    snapshots = []

    def run() -> None:
        value = _artifact()
        with CanonicalEvidenceArena() as arena:
            barrier.wait()
            encode_semantic_contract(value)
            encode_semantic_contract(value)
            snapshots.append(arena.snapshot())

    threads = [Thread(target=run), Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(snapshots) == 2
    assert snapshots[0].nonce != snapshots[1].nonce
    assert all(snapshot.entries == 0 and snapshot.hits == 0 for snapshot in snapshots)


def test_preseal_lookup_rejects_and_postseal_admission_rejects() -> None:
    value = _artifact()
    raw = b"root"
    arena = CanonicalEvidenceArena(
        scope=CanonicalValidationScope("tenant", "operation", 1, 2, "writer")
    )
    try:
        with pytest.raises(ValueError, match="sealed authority"):
            arena.lookup(
                canonical_contract_bytes=raw,
                concrete_contract_type=type(value),
                profile_revision=CANONICAL_PROFILE_REVISION,
                codec_revision=CANONICAL_CODEC_REVISION,
                domain=b"domain",
            )
        assert _admit(arena, value, raw)
        binding = arena.seal()
        assert not _admit(arena, value, b"later")
        lease = arena.lookup_sealed(
            binding=binding,
            scope=arena.scope,
            canonical_contract_bytes=raw,
            concrete_contract_type=type(value),
            profile_revision=CANONICAL_PROFILE_REVISION,
            codec_revision=CANONICAL_CODEC_REVISION,
            domain=b"domain",
        )
        assert lease is not None
        arena.close()
        lease.release()
        assert arena.snapshot().terminal_reason == "completed"
    finally:
        arena.close()


@pytest.mark.parametrize("coordinate", ["tenant", "operation", "generation", "fence", "writer"])
def test_sealed_lookup_rejects_each_foreign_scope_coordinate(coordinate: str) -> None:
    value = _artifact()
    raw = b"root"
    scope = CanonicalValidationScope("tenant", "operation", 1, 2, "writer")
    arena = CanonicalEvidenceArena(scope=scope)
    try:
        assert _admit(arena, value, raw)
        binding = arena.seal()
        changed = dict(tenant="tenant", operation="operation", generation=1, fence=2, writer="writer")
        changed[coordinate] = 3 if coordinate in {"generation", "fence"} else "foreign"
        with pytest.raises(ValueError, match="foreign scope"):
            arena.lookup_sealed(
                binding=binding,
                scope=CanonicalValidationScope(**changed),  # type: ignore[arg-type]
                canonical_contract_bytes=raw,
                concrete_contract_type=type(value),
                profile_revision=CANONICAL_PROFILE_REVISION,
                codec_revision=CANONICAL_CODEC_REVISION,
                domain=b"domain",
            )
    finally:
        arena.close()


def test_codec_issues_exact_unique_spans_and_stages_only_when_explicit() -> None:
    value = _artifact(artifact_id="same")
    arena = CanonicalEvidenceArena(
        scope=CanonicalValidationScope("tenant", "operation", 1, 2, "writer")
    )
    try:
        result = encode_semantic_contract_result(value, canonical_staging=arena)
        assert result.canonical_contract_bytes == encode_semantic_contract(value)
        assert result.canonical_member_index.member_paths == len(result.member_evidence)
        assert len({member.path for member in result.member_evidence}) == len(result.member_evidence)
        assert all(
            result.canonical_contract_bytes[member.begin : member.end]
            for member in result.member_evidence
        )
        assert arena.snapshot().entries == 1
    finally:
        arena.close()


@pytest.mark.parametrize("lease_count,release_order", [(2, (0, 1)), (2, (1, 0)), (4, (3, 1, 0, 2))])
def test_same_cached_entry_issues_independent_leases_and_drains_after_close(
    lease_count: int, release_order: tuple[int, ...]
) -> None:
    arena, value, raw, binding = _sealed_arena_with_entry()
    try:
        leases = [_lookup(arena, value, raw, binding) for _ in range(lease_count)]
        assert all(lease is not None for lease in leases)
        assert len({lease._token for lease in leases if lease is not None}) == lease_count
        arena.close()
        assert arena.snapshot().state == "closing"
        for index in release_order[:-1]:
            assert leases[index] is not None
            leases[index].release()
            assert arena.snapshot().state == "closing"
        final_lease = leases[release_order[-1]]
        assert final_lease is not None
        final_lease.release()
        snapshot = arena.snapshot()
        assert snapshot.closed
        assert snapshot.released
        assert snapshot.hits == lease_count
        assert snapshot.terminal_reason == "completed"
    finally:
        arena.close()


def test_lease_token_rejects_duplicate_stale_and_foreign_release_without_underflow() -> None:
    arena, value, raw, binding = _sealed_arena_with_entry()
    try:
        lease = _lookup(arena, value, raw, binding)
        assert lease is not None
        foreign = CanonicalEvidenceArena()
        try:
            with pytest.raises(RuntimeError, match="foreign, stale, or duplicate"):
                foreign.release_lease(lease._token)
        finally:
            foreign.close()
        arena.close()
        lease.release()
        with pytest.raises(RuntimeError, match="already released"):
            lease.release()
        with pytest.raises(RuntimeError, match="foreign, stale, or duplicate"):
            arena.release_lease(lease._token)
        snapshot = arena.snapshot()
        assert snapshot.closed
        assert snapshot.released
        assert snapshot.terminal_reason == "completed"
    finally:
        arena.close()


def test_close_and_last_release_barrier_linearizes_to_one_terminal_snapshot() -> None:
    dispatcher = RetainingCanonicalClosureObservabilityDispatcher()
    arena, value, raw, binding = _sealed_arena_with_entry(dispatcher=dispatcher)
    lease = _lookup(arena, value, raw, binding)
    assert lease is not None
    barrier = Barrier(2)
    failures: list[BaseException] = []

    def close() -> None:
        try:
            barrier.wait()
            arena.close()
        except BaseException as exc:  # pragma: no cover - test thread propagation
            failures.append(exc)

    def release() -> None:
        try:
            barrier.wait()
            lease.release()
        except BaseException as exc:  # pragma: no cover - test thread propagation
            failures.append(exc)

    closer = Thread(target=close)
    releaser = Thread(target=release)
    closer.start()
    releaser.start()
    closer.join()
    releaser.join()
    assert failures == []
    snapshot = arena.snapshot()
    assert snapshot.closed
    assert snapshot.released
    assert len(dispatcher.snapshots) == 1
    replacement = CanonicalEvidenceArena()
    try:
        assert replacement.snapshot().reservation_acquired
    finally:
        replacement.close()


class _UnavailableDispatcher(CanonicalClosureObservabilityDispatcher):
    def __init__(self, *, raises: bool = False) -> None:
        self.calls = 0
        self.raises = raises

    def record(self, snapshot):
        self.calls += 1
        if self.raises:
            raise OSError("unavailable")
        return "unavailable"


@pytest.mark.parametrize(
    ("reason", "enabled"),
    [
        ("completed", True),
        ("validation-failed", True),
        ("exception", True),
        ("cancelled", True),
        ("feature-disabled", False),
    ],
)
def test_terminal_dispatcher_records_one_content_free_snapshot_for_each_terminal_reason(
    reason: str, enabled: bool
) -> None:
    dispatcher = RetainingCanonicalClosureObservabilityDispatcher()
    arena = CanonicalEvidenceArena(enabled=enabled, observability_dispatcher=dispatcher)
    if enabled:
        if reason == "completed":
            arena.close()
        elif reason == "exception":
            arena.close_as_exception()
        else:
            arena.abort(reason)  # type: ignore[arg-type]
    snapshot = arena.snapshot()
    assert snapshot.terminal_reason == reason
    assert snapshot.released
    assert len(dispatcher.snapshots) == 1
    terminal = dispatcher.snapshots[0]
    assert terminal.terminal_reason == reason
    serialized = repr(terminal)
    assert "artifact" not in serialized
    assert "canonical" not in serialized
    arena.close()
    assert len(dispatcher.snapshots) == 1


def test_capacity_refusal_emits_one_content_free_snapshot_and_unavailable_sink_preserves_terminal_outcome() -> None:
    dispatcher = RetainingCanonicalClosureObservabilityDispatcher()
    arenas = [CanonicalEvidenceArena(observability_dispatcher=dispatcher) for _ in range(5)]
    try:
        refused = arenas[-1]
        assert refused.snapshot().terminal_reason == "capacity-refused"
        assert len(dispatcher.snapshots) == 1
    finally:
        for arena in arenas:
            arena.close()
    unavailable = _UnavailableDispatcher(raises=True)
    failing_arena = CanonicalEvidenceArena(observability_dispatcher=unavailable)
    failing_arena.close()
    assert failing_arena.snapshot().terminal_reason == "completed"
    assert failing_arena.snapshot().released
    assert unavailable.calls == 1
