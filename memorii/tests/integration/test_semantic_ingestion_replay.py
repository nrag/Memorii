from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_evolution.conflict_integrity import (
    ConflictCleanReplayVerification,
    ConflictIntegrityError,
    ConflictRepositoryIntegritySnapshot,
    ConflictRepositoryPartitionSnapshot,
    FileConflictIntegrityRepository,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _snapshot() -> ConflictRepositoryIntegritySnapshot:
    return ConflictRepositoryIntegritySnapshot.create(
        repository_id="repository",
        partitions=(
            ConflictRepositoryPartitionSnapshot(
                partition_id="partition-a",
                scope_digest=_digest("scope-a"),
                retained_byte_digests=(_digest("byte-a"),),
            ),
            ConflictRepositoryPartitionSnapshot(
                partition_id="partition-b",
                scope_digest=_digest("scope-b"),
                retained_byte_digests=(_digest("byte-b"),),
            ),
        ),
        conflict_ledger_start_coordinate=3,
        conflict_ledger_end_coordinate=9,
        last_verified_event_batch_sequence=8,
        store_topology_fingerprint=_digest("topology"),
    )


def _repository(path: Path, snapshot: ConflictRepositoryIntegritySnapshot) -> FileConflictIntegrityRepository:
    def verify(
        repaired_partition_ids: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
    ) -> ConflictCleanReplayVerification:
        return ConflictCleanReplayVerification.create(
            repository_id="repository",
            repaired_partition_ids=repaired_partition_ids,
            retained_conflicting_byte_digests=retained_conflicting_byte_digests,
            authority_source_digests=authority_source_digests,
            clean_generation_id=_digest("clean-generation"),
            clean_generation_digest=_digest("clean-generation"),
            retained_corrupt_generation_digest=_digest("corrupt-generation"),
            replay_start_event_batch_sequence=9,
            replay_final_event_batch_sequence=12,
            replay_final_batch_digest=_digest("batch-12"),
            replay_repository_state_digest=_digest("state-12"),
            verified_at=datetime(2026, 8, 2, tzinfo=UTC),
        )

    return FileConflictIntegrityRepository(
        path,
        repository_id="repository",
        snapshot_provider=lambda: snapshot,
        clean_replay_verifier=verify,
        now_provider=lambda: datetime(2026, 8, 2, tzinfo=UTC),
    )


def test_concurrent_initial_incidents_publish_one_control_and_restart_replays_winner(tmp_path: Path) -> None:
    path = tmp_path / "integrity.jsonl"
    snapshot = _snapshot()

    def isolate(byte_digest: str) -> tuple[str, ...] | str:
        try:
            return _repository(path, snapshot).isolate(
                supplied_snapshot=snapshot,
                conflicting_byte_digests=(byte_digest,),
                expected_control_digest=None,
            ).frozen_partition_ids
        except ConflictIntegrityError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(isolate, (_digest("byte-a"), _digest("byte-b"))))

    assert outcomes.count("stale_freeze_control") == 1
    winner = next(outcome for outcome in outcomes if isinstance(outcome, tuple))
    restarted = _repository(path, snapshot)
    assert restarted.current_control() is not None
    assert restarted.current_control().frozen_partition_ids == winner  # type: ignore[union-attr]


def test_concurrent_release_is_cas_linearized_and_only_one_proof_wins(
    tmp_path: Path,
) -> None:
    path = tmp_path / "integrity.jsonl"
    snapshot = _snapshot()
    repository = _repository(path, snapshot)
    control = repository.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-a"),),
        expected_control_digest=None,
    )
    repair = repository.append_repair(
        repaired_partition_ids=("partition-a",),
        authority_source_digests=(_digest("authority-a"),),
        retained_conflicting_byte_digests=(_digest("byte-a"),),
    )

    def release() -> tuple[str, ...] | str:
        try:
            return _repository(path, snapshot).release(
                repair_generation_digest=repair.repair_generation_digest,
                supplied_snapshot=snapshot,
                expected_control_digest=control.control_digest,
            ).frozen_partition_ids
        except ConflictIntegrityError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: release(), range(2)))

    assert outcomes.count(()) == 1
    assert outcomes.count("stale_freeze_control") == 1


def test_repair_and_partial_release_survive_restart_with_original_evidence_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "integrity.jsonl"
    snapshot = _snapshot()
    repository = _repository(path, snapshot)
    initial = repository.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-a"),),
        expected_control_digest=None,
    )
    frozen = repository.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-b"),),
        expected_control_digest=initial.control_digest,
    )
    evidence = tmp_path / "event-ledger.bin"
    evidence.write_bytes(b"retained event bytes\x00with conflict")
    before = evidence.read_bytes()

    repair = repository.append_repair(
        repaired_partition_ids=("partition-a",),
        authority_source_digests=(_digest("authority-a"),),
        retained_conflicting_byte_digests=(_digest("byte-a"),),
    )
    restarted = _repository(path, snapshot)
    control = restarted.release(
        repair_generation_digest=repair.repair_generation_digest,
        supplied_snapshot=snapshot,
        expected_control_digest=frozen.control_digest,
    )

    assert control.frozen_partition_ids == ("partition-b",)
    assert _repository(path, snapshot).current_control() == control
    assert evidence.read_bytes() == before
