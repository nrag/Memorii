"""Production-root canonical-evidence admission-boundary proofs.

Covers the three closure boundaries that must hold through real composition
roots rather than arena-local units: exhausting the process reservation makes
the next real delivery fall back to the identical full validated path,
concurrently in-flight writers hold isolated sealed leases at the durable
boundary, and terminal snapshots carry none of the delivery's content-bearing
sentinels in any field name or value.
"""

from __future__ import annotations

import dataclasses
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread, current_thread
from typing import Any

from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_coordinator_v3 import (
    _delivery,
    _production_recovery_service,
)


def _string_leaves(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list, set, frozenset)):
        leaves: list[str] = []
        for item in value:
            leaves.extend(_string_leaves(item))
        return leaves
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        leaves = []
        for field in dataclasses.fields(value):
            leaves.append(field.name)
            leaves.extend(_string_leaves(getattr(value, field.name)))
        return leaves
    if isinstance(value, dict):
        leaves = []
        for key, item in value.items():
            leaves.extend(_string_leaves(key))
            leaves.extend(_string_leaves(item))
        return leaves
    return []


def _assert_snapshots_carry_no_sentinels(snapshots, sentinels) -> None:
    for snapshot in snapshots:
        for text in _string_leaves(snapshot):
            for sentinel in sentinels:
                assert sentinel not in text


def _observe_arena_construction(monkeypatch, constructed: list) -> None:
    from memorii.core.semantic_ingestion.canonical_evidence_arena import (
        CanonicalEvidenceArena,
    )

    original_init = CanonicalEvidenceArena.__init__

    def observe_init(self, *args, **kwargs):
        constructed.append(self)
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(CanonicalEvidenceArena, "__init__", observe_init)


def test_process_reservation_exhaustion_at_the_root_uses_the_full_path(
    monkeypatch, tmp_path: Path,
) -> None:
    service = _production_recovery_service(
        plane=MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(tmp_path / "reservation-exhaustion")
        )
    )
    warm = _delivery(service, "reservation-warm")
    assert warm is not None
    assert service._canonical_closure_dispatcher.snapshots[-1].mode == "enabled"

    constructed: list[object] = []
    _observe_arena_construction(monkeypatch, constructed)

    atomic = service._provider_ingestion._atomic_store
    original_handoff = atomic.bootstrap_writer_handoff
    handoff_leases: list[object] = []
    all_holders_paused = Event()
    holder_releases = [Event() for _ in range(4)]
    # Arrival order and thread start order diverge under load; the release
    # loop must pair each event with the thread that actually paused on it.
    holders_in_arrival_order: list[Thread] = []
    remaining = {"count": 4}
    guard = Lock()

    def observe_handoff(request, *, canonical_evidence_lease=None):
        pause_index: int | None = None
        last = False
        with guard:
            if remaining["count"] > 0:
                remaining["count"] -= 1
                pause_index = 4 - remaining["count"] - 1
                last = remaining["count"] == 0
                holders_in_arrival_order.append(current_thread())
        handoff_leases.append(canonical_evidence_lease)
        if pause_index is not None:
            if last:
                all_holders_paused.set()
            # The full-path delivery that exhausts the reservation runs while
            # the holders wait, and it costs minutes, not seconds.
            assert holder_releases[pause_index].wait(timeout=3600), "holder never released"
        return original_handoff(request, canonical_evidence_lease=canonical_evidence_lease)

    monkeypatch.setattr(atomic, "bootstrap_writer_handoff", observe_handoff)

    failures: list[BaseException] = []

    def hold_delivery(index: int) -> None:
        try:
            _delivery(service, f"reservation-hold-{index}")
        except BaseException as error:  # surfaced through the join assertion
            failures.append(error)

    threads = [
        Thread(
            target=hold_delivery,
            args=(index,),
            name=f"canonical-evidence-reservation-hold-{index}",
            daemon=True,
        )
        for index in range(4)
    ]
    for thread in threads:
        thread.start()
    assert all_holders_paused.wait(timeout=1800), "four holders never reached handoff"
    # The refusal proof is coupled to exactly these four open arenas: the
    # fifth delivery's arena must be the process reservation's fifth
    # simultaneous request.
    assert len(constructed) == 4

    snapshots_before = len(service._canonical_closure_dispatcher.snapshots)
    refused = _delivery(service, "reservation-refused-root")
    assert refused is not None
    assert (
        refused.blocked_reasons["semantic_ingestion"]
        == warm.blocked_reasons["semantic_ingestion"]
    )
    refused_snapshots = service._canonical_closure_dispatcher.snapshots[
        snapshots_before:
    ]
    assert [snapshot.mode for snapshot in refused_snapshots] == [
        "capacity_rejected_full_path"
    ]
    assert refused_snapshots[0].terminal_reason == "capacity-refused"
    assert refused_snapshots[0].released
    assert refused_snapshots[0].reserved_bytes == 0
    assert len(handoff_leases) == 5
    assert handoff_leases[4] is None

    for release, holder in zip(holder_releases, holders_in_arrival_order, strict=True):
        release.set()
        holder.join(timeout=1800)
        assert not holder.is_alive()
    assert failures == []
    assert all(lease is not None for lease in handoff_leases[:4])
    assert all(lease._released for lease in handoff_leases[:4])
    assert len(constructed) == 5

    phase_snapshots = service._canonical_closure_dispatcher.snapshots[
        snapshots_before:
    ]
    assert len(phase_snapshots) == 5
    assert sorted(snapshot.mode for snapshot in phase_snapshots) == [
        "capacity_rejected_full_path",
        "enabled",
        "enabled",
        "enabled",
        "enabled",
    ]
    assert all(snapshot.released for snapshot in phase_snapshots)
    _assert_snapshots_carry_no_sentinels(
        phase_snapshots,
        ("Atlas owner is Bob.", "task:one", "user:alice"),
    )

    reacquired = _delivery(service, "reservation-reacquired")
    assert reacquired is not None
    assert service._canonical_closure_dispatcher.snapshots[-1].mode == "enabled"

    controls = service._memory_plane.list_records(
        source_kind="semantic_ingestion_preplanning_control"
    )
    assert controls
    assert all(
        control.content["control"]["state"] == "terminal" for control in controls
    )


def test_concurrent_inflight_writers_hold_isolated_leases_at_the_durable_boundary(
    monkeypatch, tmp_path: Path,
) -> None:
    service = _production_recovery_service(
        plane=MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(tmp_path / "inflight-writers")
        )
    )
    assert _delivery(service, "inflight-warm") is not None

    constructed: list[object] = []
    _observe_arena_construction(monkeypatch, constructed)

    atomic = service._provider_ingestion._atomic_store
    handoff_leases: list[object] = []
    first_writer_paused = Event()
    release_first_writer = Event()
    paused = {"done": False}
    original_handoff = atomic.bootstrap_writer_handoff

    def observe_handoff(request, *, canonical_evidence_lease=None):
        if not paused["done"]:
            paused["done"] = True
            first_writer_paused.set()
            assert release_first_writer.wait(timeout=60), "first writer never released"
        handoff_leases.append(canonical_evidence_lease)
        return original_handoff(request, canonical_evidence_lease=canonical_evidence_lease)

    monkeypatch.setattr(atomic, "bootstrap_writer_handoff", observe_handoff)

    snapshots_before = len(service._canonical_closure_dispatcher.snapshots)
    failures: list[BaseException] = []

    def first_writer_delivery() -> None:
        try:
            _delivery(service, "inflight-writer-first")
        except BaseException as error:  # surfaced through the join assertion
            failures.append(error)

    thread = Thread(
        target=first_writer_delivery, name="canonical-evidence-inflight-first", daemon=True
    )
    thread.start()
    assert first_writer_paused.wait(timeout=60), "first writer never reached handoff"

    second_result = _delivery(service, "inflight-writer-second")
    assert second_result is not None
    release_first_writer.set()
    thread.join(timeout=120)
    assert not thread.is_alive()
    assert failures == []

    assert len(constructed) == 2
    first_lease, second_lease = handoff_leases
    assert first_lease is not None
    assert second_lease is not None
    assert first_lease is not second_lease
    assert first_lease._token != second_lease._token
    assert first_lease._owner is not second_lease._owner
    assert first_lease.scope != second_lease.scope
    assert first_lease.result.member_evidence
    assert second_lease.result.member_evidence
    assert first_lease._released
    assert second_lease._released

    snapshots = service._canonical_closure_dispatcher.snapshots[snapshots_before:]
    assert len(snapshots) == 2
    assert {snapshot.terminal_reason for snapshot in snapshots} == {"completed"}
    assert all(
        snapshot.mode == "enabled" and snapshot.released for snapshot in snapshots
    )
    _assert_snapshots_carry_no_sentinels(
        snapshots,
        ("Atlas owner is Bob.", "task:one", "user:alice"),
    )
    controls = service._memory_plane.list_records(
        source_kind="semantic_ingestion_preplanning_control"
    )
    assert controls
    assert all(
        control.content["control"]["state"] == "terminal" for control in controls
    )


def test_terminal_snapshots_carry_no_delivery_sentinel_in_any_field(
    monkeypatch, tmp_path: Path,
) -> None:
    service = _production_recovery_service(
        plane=MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(tmp_path / "snapshot-privacy")
        )
    )
    atomic = service._provider_ingestion._atomic_store
    handoff_leases: list[object] = []
    original_handoff = atomic.bootstrap_writer_handoff

    def observe_handoff(request, *, canonical_evidence_lease=None):
        handoff_leases.append(canonical_evidence_lease)
        return original_handoff(request, canonical_evidence_lease=canonical_evidence_lease)

    monkeypatch.setattr(atomic, "bootstrap_writer_handoff", observe_handoff)

    snapshots_before = len(service._canonical_closure_dispatcher.snapshots)
    assert _delivery(service, "snapshot-privacy-root") is not None

    snapshots = service._canonical_closure_dispatcher.snapshots[snapshots_before:]
    assert len(snapshots) == 1
    assert snapshots[0].mode == "enabled"
    lease = handoff_leases[0]
    assert lease is not None
    member_index = lease.result.canonical_member_index
    evidence = lease.result.member_evidence[0]
    sentinels = (
        "Atlas owner is Bob.",
        sha256(b"Atlas owner is Bob.").hexdigest(),
        member_index.canonical_digest,
        member_index.contract_type,
        evidence.profile_revision,
        evidence.codec_revision,
        evidence.domain.decode("utf-8", "replace"),
        evidence.schema,
        "task:one",
        "user:alice",
    )
    _assert_snapshots_carry_no_sentinels(snapshots, sentinels)
