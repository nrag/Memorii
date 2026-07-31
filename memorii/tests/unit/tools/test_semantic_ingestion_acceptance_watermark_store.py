from __future__ import annotations

import json
import multiprocessing
import os
import stat
import threading
from pathlib import Path
from typing import Any

import pytest
from memorii.tools.semantic_ingestion_acceptance_watermark_store import (
    FileTraceabilityReleaseWatermarkStore,
    WatermarkAdvanced,
    WatermarkRejected,
    WatermarkUnavailable,
)


def _digest(number: int) -> str:
    return f"{number:064x}"


def _advance(path: str, epoch: int, sequence: int, digest: str, start: Any, outcomes: Any) -> None:
    try:
        start.wait(timeout=10)
    except threading.BrokenBarrierError:
        outcomes.put((sequence, "timeout", None))
        return
    result = FileTraceabilityReleaseWatermarkStore(Path(path)).compare_and_advance(epoch, sequence, digest)
    outcomes.put((sequence, type(result).__name__, getattr(result, "reason", None)))


def _provision(path: str, digest: str, start: Any, outcomes: Any) -> None:
    try:
        start.wait(timeout=10)
    except threading.BrokenBarrierError:
        outcomes.put((digest, "timeout", None))
        return
    result = FileTraceabilityReleaseWatermarkStore(Path(path)).provision(1, 1, digest)
    outcomes.put((digest, type(result).__name__, getattr(result, "reason", None)))


def _advance_same_coordinate(path: str, digest: str, start: Any, outcomes: Any) -> None:
    try:
        start.wait(timeout=10)
    except threading.BrokenBarrierError:
        outcomes.put((digest, "timeout", None))
        return
    result = FileTraceabilityReleaseWatermarkStore(Path(path)).compare_and_advance(1, 2, digest)
    outcomes.put((digest, type(result).__name__, getattr(result, "reason", None)))


def _join(processes: list[multiprocessing.Process]) -> None:
    for process in processes:
        process.join(timeout=15)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            pytest.fail("watermark child process deadlocked")
        assert process.exitcode == 0


def _release_after_all_children_are_ready(barrier: Any) -> None:
    """The parent crosses only after every contender is waiting at the barrier."""
    try:
        barrier.wait(timeout=10)
    except threading.BrokenBarrierError:
        pytest.fail("watermark children did not reach the start barrier")


def test_file_store_is_durable_idempotent_and_rejects_rewind_or_substitution(tmp_path: Path) -> None:
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkAdvanced)
    before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    assert isinstance(store.compare_and_advance(1, 1, _digest(1)), WatermarkAdvanced)
    assert path.read_bytes() == before
    assert seal.read_bytes() == seal_before
    assert isinstance(store.compare_and_advance(1, 1, _digest(2)), WatermarkRejected)
    assert path.read_bytes() == before
    assert isinstance(store.compare_and_advance(1, 0, _digest(3)), WatermarkUnavailable)
    assert path.read_bytes() == before
    assert isinstance(store.compare_and_advance(2, 1, _digest(4)), WatermarkAdvanced)
    reopened = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(reopened.compare_and_advance(1, 1, _digest(1)), WatermarkRejected)


@pytest.mark.parametrize(
    "raw",
    [
        b"not canonical",
        b'{"epoch":1.0,"format":"memorii.semantic-ingestion.acceptance-watermark.v1","release_digest":"0000000000000000000000000000000000000000000000000000000000000001","sequence":1}',
        b'{"epoch":true,"format":"memorii.semantic-ingestion.acceptance-watermark.v1","release_digest":"0000000000000000000000000000000000000000000000000000000000000001","sequence":1}',
        b'{"epoch":1,"format":"memorii.semantic-ingestion.acceptance-watermark.v1","release_digest":"bad","sequence":1}',
        b'{"epoch":1,"extra":null,"format":"memorii.semantic-ingestion.acceptance-watermark.v1","release_digest":"0000000000000000000000000000000000000000000000000000000000000001","sequence":1}',
        b'{"epoch":1',
    ],
)
def test_file_store_corruption_is_unavailable_without_authorization(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "watermark.json"
    path.write_bytes(raw)
    assert isinstance(FileTraceabilityReleaseWatermarkStore(path).compare_and_advance(1, 1, _digest(1)), WatermarkUnavailable)
    assert path.read_bytes() == raw


def test_file_store_contention_cannot_lower_the_final_coordinate(tmp_path: Path) -> None:
    path = tmp_path / "watermark.json"
    assert isinstance(FileTraceabilityReleaseWatermarkStore(path).provision(1, 1, _digest(1)), WatermarkAdvanced)
    outcomes = multiprocessing.Queue()
    start = multiprocessing.Barrier(len(range(1, 17)) + 1)
    processes = [
        multiprocessing.Process(target=_advance, args=(str(path), 1, sequence, _digest(sequence), start, outcomes))
        for sequence in range(1, 17)
    ]
    for process in processes:
        process.start()
    _release_after_all_children_are_ready(start)
    _join(processes)
    results = [outcomes.get(timeout=5) for _ in processes]
    assert all(kind != "WatermarkUnavailable" for _, kind, _ in results)
    assert (16, "WatermarkAdvanced", None) in results
    assert all(kind in {"WatermarkAdvanced", "WatermarkRejected"} for _, kind, _ in results)
    record = json.loads(path.read_bytes())
    assert record == {
        "epoch": 1,
        "format": "memorii.semantic-ingestion.acceptance-watermark.v1",
        "release_digest": _digest(16),
        "sequence": 16,
    }


def test_concurrent_conflicting_provisioning_seals_exactly_one_genesis(tmp_path: Path) -> None:
    path = tmp_path / "watermark.json"
    outcomes = multiprocessing.Queue()
    start = multiprocessing.Barrier(len(range(1, 9)) + 1)
    processes = [
        multiprocessing.Process(target=_provision, args=(str(path), _digest(number), start, outcomes))
        for number in range(1, 9)
    ]
    for process in processes:
        process.start()
    _release_after_all_children_are_ready(start)
    _join(processes)
    results = [outcomes.get(timeout=5) for _ in processes]
    winners = [digest for digest, kind, _ in results if kind == "WatermarkAdvanced"]
    assert len(winners) == 1
    assert all(kind in {"WatermarkAdvanced", "WatermarkRejected"} for _, kind, _ in results)
    winner = winners[0]
    assert json.loads(path.read_bytes())["release_digest"] == winner
    assert json.loads(path.with_name(f"{path.name}.bootstrap-seal").read_bytes())["release_digest"] == winner


def test_concurrent_same_coordinate_substitution_accepts_one_digest_and_rejects_the_other(
    tmp_path: Path,
) -> None:
    path = tmp_path / "watermark.json"
    assert isinstance(FileTraceabilityReleaseWatermarkStore(path).provision(1, 1, _digest(1)), WatermarkAdvanced)
    outcomes = multiprocessing.Queue()
    start = multiprocessing.Barrier(3)
    processes = [
        multiprocessing.Process(target=_advance_same_coordinate, args=(str(path), digest, start, outcomes))
        for digest in (_digest(2), _digest(3))
    ]
    for process in processes:
        process.start()
    _release_after_all_children_are_ready(start)
    _join(processes)
    results = [outcomes.get(timeout=5) for _ in processes]
    winners = [digest for digest, kind, _ in results if kind == "WatermarkAdvanced"]
    assert len(winners) == 1
    assert any(
        kind == "WatermarkRejected" and reason == "active_pointer_watermark_substitution"
        for _, kind, reason in results
    )
    assert json.loads(path.read_bytes())["release_digest"] == winners[0]


def test_missing_after_advance_is_unavailable_and_cannot_rewind(tmp_path: Path) -> None:
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkAdvanced)
    assert isinstance(store.compare_and_advance(1, 2, _digest(2)), WatermarkAdvanced)
    path.unlink()
    assert isinstance(store.compare_and_advance(1, 1, _digest(1)), WatermarkUnavailable)
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkUnavailable)
    assert not path.exists()


@pytest.mark.parametrize("missing", ["record", "seal"])
def test_partial_member_loss_is_unavailable_and_never_reprovisions(tmp_path: Path, missing: str) -> None:
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkAdvanced)
    assert isinstance(store.compare_and_advance(1, 2, _digest(2)), WatermarkAdvanced)
    target = path if missing == "record" else path.with_name(f"{path.name}.bootstrap-seal")
    survivor = path.with_name(f"{path.name}.bootstrap-seal") if missing == "record" else path
    survivor_bytes = survivor.read_bytes()
    target.unlink()
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkUnavailable)
    assert isinstance(store.compare_and_advance(1, 3, _digest(3)), WatermarkUnavailable)
    assert not target.exists()
    assert survivor.read_bytes() == survivor_bytes


def test_publication_failure_preserves_prior_record_and_retry_advances(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkAdvanced)
    before_record = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    before_seal = seal.read_bytes()
    original_replace = os.replace

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("injected publication failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    result = store.compare_and_advance(1, 2, _digest(2))
    assert isinstance(result, WatermarkUnavailable)
    assert path.read_bytes() == before_record
    assert seal.read_bytes() == before_seal
    assert list(path.parent.glob(f".{path.name}.*")) == []
    monkeypatch.setattr(os, "replace", original_replace)
    assert isinstance(store.compare_and_advance(1, 2, _digest(2)), WatermarkAdvanced)
    advanced = path.read_bytes()
    assert isinstance(store.compare_and_advance(1, 2, _digest(2)), WatermarkAdvanced)
    assert path.read_bytes() == advanced


def test_directory_fsync_failure_after_advance_is_lost_acknowledgement_and_retry_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkAdvanced)
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    original_fsync = os.fsync

    def fail_directory_fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("injected directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    assert isinstance(store.compare_and_advance(1, 2, _digest(2)), WatermarkUnavailable)
    # Replace happened before the failed directory durability acknowledgement.
    assert json.loads(path.read_bytes())["release_digest"] == _digest(2)
    assert seal.read_bytes() == seal_before
    assert list(path.parent.glob(f".{path.name}.*")) == []
    monkeypatch.setattr(os, "fsync", original_fsync)
    retry = store.compare_and_advance(1, 2, _digest(2))
    assert isinstance(retry, WatermarkAdvanced)
    assert json.loads(path.read_bytes())["release_digest"] == _digest(2)
    assert seal.read_bytes() == seal_before
    assert list(path.parent.glob(f".{path.name}.*")) == []


def test_directory_fsync_failure_after_genesis_seal_never_silently_completes_or_resets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    original_fsync = os.fsync

    def fail_directory_fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("injected directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkUnavailable)
    # Seal-first publication is visible, while no mutable current record exists.
    assert json.loads(seal.read_bytes())["release_digest"] == _digest(1)
    assert not path.exists()
    assert list(path.parent.glob(f".{path.name}.*")) == []
    monkeypatch.setattr(os, "fsync", original_fsync)
    assert isinstance(store.provision(1, 1, _digest(1)), WatermarkUnavailable)
    assert isinstance(store.compare_and_advance(1, 1, _digest(1)), WatermarkUnavailable)
    assert json.loads(seal.read_bytes())["release_digest"] == _digest(1)
    assert not path.exists()
