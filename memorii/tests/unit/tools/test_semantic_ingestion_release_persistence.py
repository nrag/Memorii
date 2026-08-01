"""Transaction semantics for corrected-v2 publication state."""

from __future__ import annotations

import os
import stat
from hashlib import sha256

import pytest
from memorii.tools.semantic_ingestion_acceptance_watermark_store import (
    FileTraceabilityReleaseWatermarkStore,
    WatermarkUnavailable,
)
from memorii.tools.semantic_ingestion_release_persistence import (
    FileMonotonicFenceStore,
    InMemoryTraceabilityReleasePublicationStore,
    PublicationTail,
)
from memorii.tools.semantic_ingestion_release_persistence import (
    FileTraceabilityReleasePublicationStore as _FileTraceabilityReleasePublicationStore,
)
from memorii.tools.semantic_ingestion_traceability_registry import canonical_document
from memorii.tools.semantic_ingestion_traceability_release import (
    AntiRollbackTrustResolver,
    TraceabilityGateAuthorized,
    TraceabilityGateRejected,
    TraceabilityGateUnavailable,
    TraceabilityReleasePublicationStore,
    VerifiedAntiRollbackRegistration,
    WatermarkAdvanced,
    WatermarkRejected,
    _commit_verified_release,
    _VerifiedReleaseCandidate,
    validate_anti_rollback_backend_registration,
)


def FileTraceabilityReleasePublicationStore(path):
    return _FileTraceabilityReleasePublicationStore(
        path,
        FileMonotonicFenceStore(
            path.parent / "fence-domain" / f"{path.name}.minimum.log"
        ),
    )


def _registration_artifact(
    store, backend_id: str, backend_kind: str, failure_domain: str
) -> bytes:
    payload = {
        "backend_id": backend_id,
        "backend_kind": backend_kind,
        "failure_domain": failure_domain,
        "publication_store_id": store.publication_store_id(),
    }
    payload_bytes = canonical_document(payload)
    signature = sha256(b"verifier-key" + payload_bytes).digest()
    return canonical_document({"payload": payload, "signature": signature.hex()})


def _resolver(*allowed: tuple[str, str, str]) -> AntiRollbackTrustResolver:
    return AntiRollbackTrustResolver(
        allowed_registrations=frozenset(allowed),
        verify_registration_signature=lambda payload, signature: signature
        == sha256(b"verifier-key" + payload).digest(),
    )


def _publish(store: TraceabilityReleasePublicationStore, sequence: int, marker: bytes):
    return store.compare_and_publish(
        epoch=1,
        sequence=sequence,
        release_digest=f"{sequence:064x}",
        release_artifact=b"release:" + marker,
        release_history_artifact=b"release-history:" + marker,
        active_pointer_artifact=b"pointer:" + marker,
        pointer_history_artifact=b"pointer-history:" + marker,
    )


def _fenced_publish(
    store: _FileTraceabilityReleasePublicationStore,
    sequence: int,
    marker: bytes,
):
    return store.compare_fence_and_publish(
        watermark_store=store,
        epoch=1,
        sequence=sequence,
        release_digest=f"{sequence:064x}",
        release_artifact=b"release:" + marker,
        release_history_artifact=b"release-history:" + marker,
        active_pointer_artifact=b"pointer:" + marker,
        pointer_history_artifact=b"pointer-history:" + marker,
    )


def test_corrected_v2_publication_is_atomic_monotonic_and_idempotent() -> None:
    store = InMemoryTraceabilityReleasePublicationStore()
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    first = store.current
    assert first is not None
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    assert store.current == first
    rejected = _publish(store, 1, b"substitution")
    assert isinstance(rejected, TraceabilityGateRejected)
    assert rejected.reason == "stale_pointer_cas"
    assert store.current == first
    assert isinstance(_publish(store, 2, b"two"), TraceabilityGateAuthorized)
    assert store.current is not None and store.current.sequence == 2


def test_publication_rejects_gaps_and_rewinds_without_partial_state() -> None:
    store = InMemoryTraceabilityReleasePublicationStore()
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    before = store.current
    gap = _publish(store, 3, b"three")
    assert isinstance(gap, TraceabilityGateRejected)
    assert gap.reason == "active_pointer_monotonicity"
    assert store.current == before
    rewind = _publish(store, 1, b"one")
    assert isinstance(rewind, TraceabilityGateAuthorized)
    assert store.current == before


def test_file_publication_recovers_the_complete_bundle_and_rejects_torn_state(tmp_path) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    reopened = FileTraceabilityReleasePublicationStore(path)
    assert isinstance(_publish(reopened, 1, b"one"), TraceabilityGateAuthorized)
    raw = path.read_bytes()
    path.write_bytes(raw[:-1])
    unavailable = _publish(FileTraceabilityReleasePublicationStore(path), 2, b"two")
    assert unavailable.__class__.__name__ == "TraceabilityGateUnavailable"


def test_file_publication_lost_ack_retries_the_exact_committed_bundle(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    original_fsync = os.fsync
    directory_syncs = 0

    def fail_directory_fsync(descriptor: int) -> None:
        nonlocal directory_syncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_syncs += 1
            # History is durable first; fail only after the current index
            # replacement has made the accepted tail visible.
            if directory_syncs == 2:
                raise OSError("injected directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    outcome = _publish(store, 2, b"two")
    assert isinstance(outcome, TraceabilityGateUnavailable)
    # The current index replacement occurred before the durability acknowledgement was lost.
    committed = path.read_bytes()
    assert b'"tail_digest"' in committed
    monkeypatch.setattr(os, "fsync", original_fsync)
    assert isinstance(_publish(FileTraceabilityReleasePublicationStore(path), 2, b"two"), TraceabilityGateAuthorized)
    assert path.read_bytes() == committed


def test_file_publication_interruption_before_replace_keeps_prior_tail(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    prior = path.read_bytes()
    original_replace = os.replace

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("injected replacement interruption")

    monkeypatch.setattr(os, "replace", fail_replace)
    outcome = _publish(store, 2, b"two")
    assert outcome.__class__.__name__ == "TraceabilityGateUnavailable"
    assert path.read_bytes() == prior
    assert list(path.parent.glob(f".{path.name}.*")) == []
    monkeypatch.setattr(os, "replace", original_replace)
    assert isinstance(_publish(FileTraceabilityReleasePublicationStore(path), 2, b"two"), TraceabilityGateAuthorized)


def test_file_publication_rollback_appends_a_new_monotonic_tail(tmp_path) -> None:
    store = FileTraceabilityReleasePublicationStore(tmp_path / "publication.json")
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    first = store.version_inventory().current
    assert first is not None
    assert isinstance(_publish(store, 2, b"two"), TraceabilityGateAuthorized)
    second = store.version_inventory().current
    assert second is not None

    replayed = store.rollback_to(
        first,
        epoch=1,
        sequence=3,
        expected_predecessor=second,
        release_artifact=b"release:one",
        release_history_artifact=b"release-history:one",
        active_pointer_artifact=b"pointer:one",
        pointer_history_artifact=b"pointer-history:one",
    )
    assert isinstance(replayed, TraceabilityGateRejected)
    assert replayed.reason == "rollback_pointer_bundle_replayed"

    outcome = store.rollback_to(
        first,
        epoch=1,
        sequence=3,
        expected_predecessor=second,
        release_artifact=b"release:one",
        release_history_artifact=b"release-history:rollback-one",
        active_pointer_artifact=b"pointer:rollback-one",
        pointer_history_artifact=b"pointer-history:rollback-one",
    )
    assert isinstance(outcome, TraceabilityGateAuthorized)
    inventory = FileTraceabilityReleasePublicationStore(tmp_path / "publication.json").version_inventory()
    assert inventory.state == "corrected_v2"
    assert inventory.corrected_v2_tail_count == 3
    assert inventory.current is not None
    assert inventory.current.sequence == 3
    assert inventory.current.release_digest == first.release_digest
    assert inventory.current.selected_tail_digest == first.tail_digest


def test_predecessor_cas_and_legacy_inventory_fail_closed(tmp_path) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    first = store.version_inventory().current
    assert first is not None
    assert isinstance(_publish(store, 2, b"two"), TraceabilityGateAuthorized)
    current = store.version_inventory().current
    assert current is not None

    stale = store.compare_and_publish_after(
        epoch=1,
        sequence=3,
        release_digest=f"{3:064x}",
        release_artifact=b"release:three",
        release_history_artifact=b"release-history:three",
        active_pointer_artifact=b"pointer:three",
        pointer_history_artifact=b"pointer-history:three",
        expected_predecessor=first,
    )
    assert isinstance(stale, TraceabilityGateRejected)
    assert stale.reason == "stale_pointer_predecessor_cas"
    assert store.version_inventory().current == current

    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_bytes(b'{"format":"legacy-v1"}\n')
    legacy = FileTraceabilityReleasePublicationStore(legacy_path)
    inventory = legacy.version_inventory()
    assert inventory.state == "corrupt" or inventory.state == "legacy"
    outcome = _publish(legacy, 1, b"one")
    assert outcome.__class__.__name__ == "TraceabilityGateUnavailable"
    rollback = legacy.rollback_to(
        PublicationTail(1, 1, "0" * 64, "0" * 64, "0" * 64),
        epoch=1,
        sequence=2,
        expected_predecessor=PublicationTail(1, 1, "0" * 64, "0" * 64, "0" * 64),
        release_artifact=b"release",
        release_history_artifact=b"history",
        active_pointer_artifact=b"pointer",
        pointer_history_artifact=b"pointer-history",
    )
    assert rollback.__class__.__name__ == "TraceabilityGateUnavailable"


def test_independent_fence_rejects_restored_older_valid_index(tmp_path) -> None:
    publication_path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(publication_path)
    assert store.provision(1, 1, f"{1:064x}").__class__.__name__ == "WatermarkAdvanced"
    assert isinstance(_fenced_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    old_index = publication_path.read_bytes()
    assert isinstance(_fenced_publish(store, 2, b"two"), TraceabilityGateAuthorized)
    new_index = publication_path.read_bytes()
    current = store.version_inventory().current
    assert current is not None
    assert current.sequence == 2

    # Simulate restoration of an intact older index while immutable tails and
    # the independently durable high-water fence remain current.
    publication_path.write_bytes(old_index)
    rejected = _fenced_publish(FileTraceabilityReleasePublicationStore(publication_path), 1, b"one")
    assert isinstance(rejected, TraceabilityGateRejected)
    assert rejected.reason == "active_pointer_watermark_rewind"
    assert publication_path.read_bytes() == new_index
    recovered = FileTraceabilityReleasePublicationStore(publication_path).version_inventory()
    assert recovered.current is not None and recovered.current.sequence == 2


def test_prepared_unselected_tail_is_ignored_and_reused_after_restart(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    prior_index = path.read_bytes()

    def fail_index(*args: object) -> None:
        raise OSError("injected failure after tail prepare")

    monkeypatch.setattr(store, "_write_index_locked", fail_index)
    assert isinstance(_publish(store, 2, b"two"), TraceabilityGateUnavailable)
    assert path.read_bytes() == prior_index

    reopened = FileTraceabilityReleasePublicationStore(path)
    inventory = reopened.version_inventory()
    assert inventory.corrected_v2_tail_count == 1
    assert inventory.current is not None and inventory.current.sequence == 1
    assert isinstance(_publish(reopened, 2, b"two"), TraceabilityGateAuthorized)
    assert reopened.version_inventory().corrected_v2_tail_count == 2


def test_index_without_commit_fence_deterministically_completes_after_restart(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    fence_path = path.parent / "fence-domain" / f"{path.name}.minimum.log"
    prior_commit = fence_path.read_bytes()

    original_append = store._append_commit_locked

    def fail_second_commit(
        tail_digest: str | None, epoch: int, sequence: int, release_digest: str
    ) -> None:
        if sequence == 2:
            raise OSError("injected failure after index replacement")
        original_append(tail_digest, epoch, sequence, release_digest)

    monkeypatch.setattr(store, "_append_commit_locked", fail_second_commit)
    assert isinstance(_publish(store, 2, b"two"), TraceabilityGateUnavailable)
    assert fence_path.read_bytes() == prior_commit

    reopened = FileTraceabilityReleasePublicationStore(path)
    inventory = reopened.version_inventory()
    assert inventory.current is not None and inventory.current.sequence == 2
    assert fence_path.read_bytes() != prior_commit
    assert isinstance(_publish(reopened, 2, b"two"), TraceabilityGateAuthorized)


def test_restored_index_and_history_cannot_override_newer_external_fence(tmp_path) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    assert isinstance(_publish(store, 1, b"one"), TraceabilityGateAuthorized)
    old_index = path.read_bytes()
    old_members = {member.name for member in store._history_path.iterdir()}
    assert isinstance(_publish(store, 2, b"two"), TraceabilityGateAuthorized)
    assert not path.with_name(f"{path.name}.commit-fence").exists()

    path.write_bytes(old_index)
    for member in store._history_path.iterdir():
        if member.name not in old_members:
            member.unlink()

    reopened = FileTraceabilityReleasePublicationStore(path)
    unavailable = _publish(reopened, 1, b"one")
    assert isinstance(unavailable, TraceabilityGateUnavailable)


def test_integrated_store_rejects_split_watermark_before_mutation(tmp_path) -> None:
    store = FileTraceabilityReleasePublicationStore(tmp_path / "publication.json")
    split = FileTraceabilityReleaseWatermarkStore(tmp_path / "watermark.json")
    assert split.provision(1, 1, f"{1:064x}").__class__.__name__ == "WatermarkAdvanced"
    outcome = store.compare_fence_and_publish(
        watermark_store=split,
        epoch=1,
        sequence=1,
        release_digest=f"{1:064x}",
        release_artifact=b"release:one",
        release_history_artifact=b"release-history:one",
        active_pointer_artifact=b"pointer:one",
        pointer_history_artifact=b"pointer-history:one",
    )
    assert isinstance(outcome, TraceabilityGateUnavailable)
    assert outcome.reason == "persistence_outcome_indeterminate"
    assert not (tmp_path / "publication.json").exists()


def test_missing_or_unavailable_external_fence_fails_closed(tmp_path) -> None:
    path = tmp_path / "publication.json"
    missing = _FileTraceabilityReleasePublicationStore(path, None)
    provision = missing.provision(1, 1, f"{1:064x}")
    assert provision.__class__.__name__ == "WatermarkUnavailable"
    assert not path.exists()

    class UnavailableFence:
        production_safe = True
        failure_domain = "unavailable-external-service"

        def records(self):
            return TraceabilityGateUnavailable("external_fence_unavailable")

        def advance(
            self, epoch: int, sequence: int, release_digest: str, tail_digest: str | None
        ):
            return WatermarkUnavailable("external_fence_unavailable")

    unavailable = _FileTraceabilityReleasePublicationStore(path, UnavailableFence())
    outcome = _publish(unavailable, 1, b"one")
    assert isinstance(outcome, TraceabilityGateUnavailable)
    assert not path.exists()


def test_fence_creation_directory_sync_failure_fails_closed(tmp_path, monkeypatch) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    original_fsync = os.fsync

    def fail_directory_sync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("injected fence creation directory sync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    outcome = store.provision(1, 1, f"{1:064x}")
    assert isinstance(outcome, WatermarkUnavailable)
    assert not path.exists()
    assert not (tmp_path / "fence-domain" / f"{path.name}.minimum.log").exists()


def test_production_safe_external_fence_survives_full_local_tree_restore(tmp_path) -> None:
    class ExternalFence:
        def __init__(self) -> None:
            self.values = []

        def durable_backend_id(self):
            return "external-1"

        def records(self):
            return list(self.values)

        def advance(self, epoch, sequence, release_digest, tail_digest):
            if self.values and (epoch, sequence) < self.values[-1][:2]:
                return WatermarkRejected("active_pointer_watermark_rewind")
            raw = f"{epoch}:{sequence}:{release_digest}:{tail_digest}".encode()
            record = (epoch, sequence, release_digest, tail_digest, sha256(raw).hexdigest())
            if not self.values or record[:4] != self.values[-1][:4]:
                self.values.append(record)
            return WatermarkAdvanced()

    path = tmp_path / "local-recovery" / "publication.json"
    fence = ExternalFence()
    store = _FileTraceabilityReleasePublicationStore(path, fence)
    resolver = _resolver(("external-1", "remote", "external-service"))
    token = resolver.register(
        signed_artifact=_registration_artifact(
            store, "external-1", "remote", "external-service"
        )
    )
    first_candidate = _VerifiedReleaseCandidate("release", f"{1:064x}", 1, 1, (), ())
    assert isinstance(_commit_verified_release(
        first_candidate, store, publication_store=store, release_artifact=b"release:one",
        release_history_artifact=b"release-history:one", active_pointer_artifact=b"pointer:one",
        pointer_history_artifact=b"pointer-history:one",
        verified_anti_rollback_registration=token,
        anti_rollback_resolver=resolver,
    ), TraceabilityGateAuthorized)
    old_index = path.read_bytes()
    old_history = {member.name: member.read_bytes() for member in store._history_path.iterdir()}
    second_candidate = _VerifiedReleaseCandidate("release-2", f"{2:064x}", 1, 2, (), ())
    assert isinstance(_commit_verified_release(
        second_candidate, store, publication_store=store, release_artifact=b"release:two",
        release_history_artifact=b"release-history:two", active_pointer_artifact=b"pointer:two",
        pointer_history_artifact=b"pointer-history:two",
        verified_anti_rollback_registration=token,
        anti_rollback_resolver=resolver,
    ), TraceabilityGateAuthorized)
    assert fence.values[-1][1] == 2

    path.write_bytes(old_index)
    for member in store._history_path.iterdir():
        member.unlink()
    for name, raw in old_history.items():
        (store._history_path / name).write_bytes(raw)

    outcome = _publish(_FileTraceabilityReleasePublicationStore(path, fence), 1, b"one")
    assert isinstance(outcome, TraceabilityGateUnavailable)
    assert fence.values[-1][1] == 2


def test_test_only_file_fence_is_rejected_by_production_commit_before_mutation(tmp_path) -> None:
    path = tmp_path / "publication.json"
    store = FileTraceabilityReleasePublicationStore(path)
    candidate = _VerifiedReleaseCandidate("release", f"{1:064x}", 1, 1, (), ())
    accepted = _commit_verified_release(
        candidate,
        store,
        publication_store=store,
        release_artifact=b"release",
        release_history_artifact=b"history",
        active_pointer_artifact=b"pointer",
        pointer_history_artifact=b"pointer-history",
        allow_test_file_fence=True,
    )
    assert isinstance(accepted, TraceabilityGateAuthorized)
    snapshot = {
        item.relative_to(tmp_path): item.read_bytes()
        for item in tmp_path.rglob("*")
        if item.is_file()
    }
    second = _VerifiedReleaseCandidate("release-2", f"{2:064x}", 1, 2, (), ())
    assert isinstance(
        _commit_verified_release(
            second,
            store,
            publication_store=store,
            release_artifact=b"release-2",
            release_history_artifact=b"history-2",
            active_pointer_artifact=b"pointer-2",
            pointer_history_artifact=b"pointer-history-2",
            allow_test_file_fence=True,
        ),
        TraceabilityGateAuthorized,
    )
    for item in tmp_path.rglob("*"):
        if item.is_file():
            item.unlink()
    for relative, raw in snapshot.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)

    restored = FileTraceabilityReleasePublicationStore(path)
    before = path.read_bytes()
    outcome = _commit_verified_release(
        candidate,
        restored,
        publication_store=restored,
        release_artifact=b"release",
        release_history_artifact=b"history",
        active_pointer_artifact=b"pointer",
        pointer_history_artifact=b"pointer-history",
    )
    assert isinstance(outcome, TraceabilityGateUnavailable)
    assert outcome.reason == "verified_anti_rollback_registration_required"
    assert path.read_bytes() == before


def test_same_failure_domain_registration_is_rejected(tmp_path) -> None:
    path = tmp_path / "publication.json"
    store = _FileTraceabilityReleasePublicationStore(
        path, FileMonotonicFenceStore(tmp_path / "fence.log")
    )
    resolver = _resolver(("backend", "remote", str(tmp_path.resolve())))
    token = resolver.register(signed_artifact=_registration_artifact(
        store, "backend", "remote", str(tmp_path.resolve())
    ))
    candidate = _VerifiedReleaseCandidate("release", f"{1:064x}", 1, 1, (), ())
    outcome = _commit_verified_release(
        candidate, store, publication_store=store, release_artifact=b"release",
        release_history_artifact=b"history", active_pointer_artifact=b"pointer",
        pointer_history_artifact=b"pointer-history",
        verified_anti_rollback_registration=token, anti_rollback_resolver=resolver,
    )
    assert isinstance(outcome, TraceabilityGateUnavailable)
    assert not path.exists()


def test_spoofed_subclass_forged_token_and_mismatched_instance_are_rejected(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="composition-owned"):
        validate_anti_rollback_backend_registration(
            allowed_registrations=frozenset({("attacker", "remote", "fake")}),
            verify_registration_signature=lambda payload, signature: True,
        )

    class SpoofedFileFence(FileMonotonicFenceStore):
        production_safe = True
        failure_domain = "remote-service"

    spoof = SpoofedFileFence(tmp_path / "remote" / "fence.log")
    store = _FileTraceabilityReleasePublicationStore(tmp_path / "publication.json", spoof)
    spoof_resolver = _resolver(("spoof", "remote", "remote-service"))
    spoof_token = spoof_resolver.register(signed_artifact=_registration_artifact(
        store, "spoof", "remote", "remote-service"
    ))
    candidate = _VerifiedReleaseCandidate("release", f"{1:064x}", 1, 1, (), ())
    spoof_rejected = _commit_verified_release(
        candidate, store, publication_store=store, release_artifact=b"release",
        release_history_artifact=b"history", active_pointer_artifact=b"pointer",
        pointer_history_artifact=b"pointer-history",
        verified_anti_rollback_registration=spoof_token,
        anti_rollback_resolver=spoof_resolver,
    )
    assert isinstance(spoof_rejected, TraceabilityGateUnavailable)
    forged = VerifiedAntiRollbackRegistration(spoof_token.payload, b"forged")
    rejected = _commit_verified_release(
        candidate, store, publication_store=store, release_artifact=b"release",
        release_history_artifact=b"history", active_pointer_artifact=b"pointer",
        pointer_history_artifact=b"pointer-history",
        verified_anti_rollback_registration=forged,
        anti_rollback_resolver=spoof_resolver,
    )
    assert isinstance(rejected, TraceabilityGateUnavailable)

    class RemoteFence:
        def durable_backend_id(self):
            return "remote-1"

        def records(self):
            return []

        def advance(self, epoch, sequence, release_digest, tail_digest):
            return WatermarkAdvanced()

    backend = RemoteFence()
    first = _FileTraceabilityReleasePublicationStore(tmp_path / "first.json", backend)
    second = _FileTraceabilityReleasePublicationStore(tmp_path / "second.json", backend)
    resolver = _resolver(("remote-1", "remote", "service-a"))
    token = resolver.register(signed_artifact=_registration_artifact(
        first, "remote-1", "remote", "service-a"
    ))
    mismatch = _commit_verified_release(
        candidate, second, publication_store=second, release_artifact=b"release",
        release_history_artifact=b"history", active_pointer_artifact=b"pointer",
        pointer_history_artifact=b"pointer-history",
        verified_anti_rollback_registration=token,
        anti_rollback_resolver=resolver,
    )
    assert isinstance(mismatch, TraceabilityGateUnavailable)

    attacker = AntiRollbackTrustResolver(
        allowed_registrations=frozenset({("remote-1", "remote", "service-a")}),
        verify_registration_signature=lambda payload, signature: True,
    )
    attacker_payload = {
        "backend_id": "remote-1", "backend_kind": "remote",
        "failure_domain": "service-a", "publication_store_id": first.publication_store_id(),
    }
    attacker_token = attacker.register(signed_artifact=canonical_document(
        {"payload": attacker_payload, "signature": b"attacker".hex()}
    ))
    wrong_issuer = _commit_verified_release(
        candidate, first, publication_store=first, release_artifact=b"release",
        release_history_artifact=b"history", active_pointer_artifact=b"pointer",
        pointer_history_artifact=b"pointer-history",
        verified_anti_rollback_registration=attacker_token,
        anti_rollback_resolver=resolver,
    )
    assert isinstance(wrong_issuer, TraceabilityGateUnavailable)
    with pytest.raises(ValueError, match="anti_rollback_backend_registration_invalid"):
        _resolver(("proxy", "proxy", "service-b")).register(
            signed_artifact=_registration_artifact(first, "proxy", "proxy", "service-b")
        )
