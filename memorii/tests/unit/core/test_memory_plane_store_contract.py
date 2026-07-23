from __future__ import annotations

import sys
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from memorii.core.memory_plane import file_lock
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    MemoryPlaneCorruptionError,
    MemoryPlaneRevisionConflictError,
    MemoryPlaneStore,
)
from memorii.domain.enums import CommitStatus, MemoryDomain

StoreFactory = Callable[[Path], MemoryPlaneStore]


@pytest.fixture(params=["memory", "jsonl"])
def store_factory(request: pytest.FixtureRequest) -> StoreFactory:
    if request.param == "memory":
        return lambda _: InMemoryMemoryPlaneStore()
    return lambda path: JsonlMemoryPlaneStore(path)


def _record(memory_id: str, *, marker: str = "original") -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text=marker,
        content={"nested": {"marker": marker}},
        status=CommitStatus.COMMITTED,
        source_kind="store_contract",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _write_record_in_process(arguments: tuple[str, int]) -> int:
    path, index = arguments
    store = JsonlMemoryPlaneStore(path)
    return store.write_records((_record(f"mem:process:{index}"),))


def test_write_captures_a_detached_snapshot(store_factory: StoreFactory, tmp_path: Path) -> None:
    store = store_factory(tmp_path / "store")
    record = _record("mem:one")
    store.stage_record(record)

    record.content["nested"]["marker"] = "mutated"

    loaded = store.get_record("mem:one")
    assert loaded is not None
    assert loaded.content["nested"] == {"marker": "original"}
    assert store.revision() == 1


def test_read_returns_a_detached_snapshot(store_factory: StoreFactory, tmp_path: Path) -> None:
    store = store_factory(tmp_path / "store")
    store.stage_record(_record("mem:one"))
    loaded = store.get_record("mem:one")
    assert loaded is not None

    loaded.content["nested"]["marker"] = "mutated"

    reread = store.get_record("mem:one")
    assert reread is not None
    assert reread.content["nested"] == {"marker": "original"}
    assert store.revision() == 1


def test_compare_and_swap_rejects_a_stale_revision(store_factory: StoreFactory, tmp_path: Path) -> None:
    store = store_factory(tmp_path / "store")
    store.stage_record(_record("mem:one"))
    stale_revision = store.revision()
    store.stage_record(_record("mem:two"))

    with pytest.raises(MemoryPlaneRevisionConflictError):
        store.apply_batch((_record("mem:stale"),), expected_revision=stale_revision)

    assert store.get_record("mem:stale") is None


def test_concurrent_unconditional_writes_are_all_visible(
    store_factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = store_factory(tmp_path / "store")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda index: store.stage_record(_record(f"mem:{index}")), range(24)))

    assert store.revision() == 24
    assert {record.memory_id for record in store.list_records()} == {f"mem:{index}" for index in range(24)}


def test_jsonl_independent_instances_serialize_concurrent_writes(tmp_path: Path) -> None:
    path = tmp_path / "store"

    def write(index: int) -> int:
        return JsonlMemoryPlaneStore(path).write_records((_record(f"mem:instance:{index}"),))

    with ThreadPoolExecutor(max_workers=8) as executor:
        revisions = list(executor.map(write, range(24)))

    reopened = JsonlMemoryPlaneStore(path)
    assert sorted(revisions) == list(range(1, 25))
    assert reopened.revision() == 24
    assert {record.memory_id for record in reopened.list_records()} == {
        f"mem:instance:{index}" for index in range(24)
    }


def test_jsonl_processes_serialize_concurrent_writes(tmp_path: Path) -> None:
    path = tmp_path / "store"
    arguments = [(str(path), index) for index in range(12)]

    with ProcessPoolExecutor(max_workers=4) as executor:
        revisions = list(executor.map(_write_record_in_process, arguments))

    reopened = JsonlMemoryPlaneStore(path)
    assert sorted(revisions) == list(range(1, 13))
    assert reopened.revision() == 12
    assert {record.memory_id for record in reopened.list_records()} == {
        f"mem:process:{index}" for index in range(12)
    }


def test_jsonl_failed_atomic_replace_preserves_previous_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "store"
    store = JsonlMemoryPlaneStore(path)
    store.stage_record(_record("mem:one"))

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr("memorii.core.memory_plane.store.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        store.stage_record(_record("mem:two"))

    reopened = JsonlMemoryPlaneStore(path)
    assert reopened.revision() == 1
    assert [record.memory_id for record in reopened.list_records()] == ["mem:one"]
    assert list(path.glob(".memory_records.jsonl.*.tmp")) == []


@pytest.mark.parametrize("corrupt_payload", ["not-json\n", '{"revision":2}\n', "not-json"])
def test_jsonl_corruption_fails_closed_and_refuses_new_writes(
    tmp_path: Path,
    corrupt_payload: str,
) -> None:
    path = tmp_path / "store"
    store = JsonlMemoryPlaneStore(path)
    store.stage_record(_record("mem:one"))
    records_path = path / "memory_records.jsonl"
    with records_path.open("a", encoding="utf-8") as handle:
        handle.write(corrupt_payload)
    size_before = records_path.stat().st_size

    with pytest.raises(MemoryPlaneCorruptionError):
        store.list_records()
    with pytest.raises(MemoryPlaneCorruptionError):
        store.stage_record(_record("mem:two"))

    assert records_path.stat().st_size == size_before


@pytest.mark.parametrize(("exclusive", "expected_mode"), [(False, 2), (True, 1)])
def test_windows_file_lock_uses_a_lockable_byte_and_releases_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exclusive: bool,
    expected_mode: int,
) -> None:
    calls: list[tuple[int, int]] = []
    fake_msvcrt = ModuleType("msvcrt")
    fake_msvcrt.LK_LOCK = 1
    fake_msvcrt.LK_RLCK = 2
    fake_msvcrt.LK_UNLCK = 3

    def locking(_file_descriptor: int, mode: int, byte_count: int) -> None:
        calls.append((mode, byte_count))

    fake_msvcrt.locking = locking
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(file_lock, "_WINDOWS", True)
    lock_path = tmp_path / "memory.lock"

    with file_lock.locked_file(lock_path, exclusive=exclusive):
        assert lock_path.read_bytes() == b"\0"

    assert calls == [(expected_mode, 1), (fake_msvcrt.LK_UNLCK, 1)]
