from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    MemoryPlaneRevisionConflictError,
    MemoryPlaneStore,
    ReadOnlyMemoryPlaneSnapshotStore,
    RecordAbsentPrecondition,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

StoreFactory = Callable[[Path], MemoryPlaneStore]


@pytest.fixture(params=["memory", "jsonl"])
def store_factory(request: pytest.FixtureRequest) -> StoreFactory:
    if request.param == "memory":
        return lambda _: InMemoryMemoryPlaneStore()
    return lambda path: JsonlMemoryPlaneStore(path)


def _record(memory_id: str, *, internal: bool = False) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text=memory_id,
        content={"nested": {"memory_id": memory_id}},
        status=CommitStatus.COMMITTED,
        source_kind="write_snapshot_test",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=(
            MemoryRecordVisibility.INTERNAL_CONTROL
            if internal
            else MemoryRecordVisibility.RUNTIME_CONTEXT
        ),
    )


def _write_with_deadline(store: MemoryPlaneStore, memory_id: str) -> None:
    completed = Event()

    def write() -> None:
        store.stage_record(_record(memory_id, internal=True))
        completed.set()

    thread = Thread(target=write, daemon=True)
    thread.start()
    assert completed.wait(5), "snapshot failure retained the backend lock"
    thread.join(timeout=1)


def test_detached_reader_preserves_inventory_and_rejects_every_mutation_route():
    record = _record("detached")
    store = ReadOnlyMemoryPlaneSnapshotStore(write_revision=7, records=(record,))
    record.content["nested"]["memory_id"] = "caller mutation"
    original = store.read_write_snapshot()
    assert original[0] == 7
    assert original[1][0].content["nested"]["memory_id"] == "detached"
    original[1][0].content.clear()
    retained = store.get_record("detached")
    assert retained is not None and retained.content
    for mutate in (
        lambda: store.stage_record(_record("new")),
        lambda: store.upsert_record(_record("new")),
        lambda: store.write_records((_record("new"),)),
        lambda: store.apply_batch((), expected_revision=None),
        lambda: store.load_or_create_protected_secret(purpose="test", length=32),
        lambda: store._claim_semantic_checkpoint_signature_authority(owner=object()),
        store.revision, store.read_snapshot,
    ):
        with pytest.raises(PermissionError):
            mutate()
    assert store.read_write_snapshot()[0] == 7
    assert tuple(item.memory_id for item in store.list_records()) == ("detached",)
    with pytest.raises(PermissionError, match="timed write authority"):
        store.read_timed_write_snapshot(
            now=lambda: (_ for _ in ()).throw(AssertionError("clock must not be called"))
        )
    with pytest.raises(ValueError):
        ReadOnlyMemoryPlaneSnapshotStore(write_revision=True, records=())


def test_timed_write_snapshot_is_detached_and_rejects_non_utc_clock(
    store_factory: StoreFactory, tmp_path: Path,
) -> None:
    store = store_factory(tmp_path / "store")
    store.stage_record(_record("timed", internal=True))
    snapshot = store.read_timed_write_snapshot(now=lambda: datetime(2026, 1, 2, tzinfo=UTC))
    assert snapshot.write_revision == 1
    assert snapshot.created_at == datetime(2026, 1, 2, tzinfo=UTC)
    snapshot.records[0].content["nested"]["memory_id"] = "caller mutation"
    retained = store.get_record("timed")
    assert retained is not None and retained.content["nested"]["memory_id"] == "timed"
    writer = store_factory(tmp_path / "store") if store.durable else store
    for index, invalid in enumerate((
        datetime(2026, 1, 2),
        datetime(2026, 1, 2, 1, tzinfo=timezone(timedelta(hours=1))),
    )):
        with pytest.raises(ValueError, match="created_at"):
            store.read_timed_write_snapshot(now=lambda value=invalid: value)
        memory_id = f"after-invalid-clock-{index}"
        _write_with_deadline(writer, memory_id)
        later = store.read_timed_write_snapshot(now=lambda: datetime(2026, 1, 2, tzinfo=UTC))
        assert memory_id in {record.memory_id for record in later.records}


def test_timed_write_snapshot_blocks_competing_writer_and_clock_failure_releases_lock(
    store_factory: StoreFactory, tmp_path: Path,
) -> None:
    path = tmp_path / "store"
    first = store_factory(path)
    second = store_factory(path) if first.durable else first
    first.stage_record(_record("before", internal=True))
    entered, release = Event(), Event()

    def clock() -> datetime:
        entered.set()
        assert release.wait(10)
        return datetime(2026, 1, 2, tzinfo=UTC)

    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshot = executor.submit(first.read_timed_write_snapshot, now=clock)
        assert entered.wait(10)
        writer_started = Event()

        def write() -> None:
            writer_started.set()
            second.stage_record(_record("contending", internal=True))

        writer = executor.submit(write)
        assert writer_started.wait(10)
        assert not writer.done()
        release.set()
        captured = snapshot.result(timeout=10)
        assert captured.write_revision == 1
        assert tuple(record.memory_id for record in captured.records) == ("before",)
        writer.result(timeout=10)

    with pytest.raises(RuntimeError, match="clock failure"):
        first.read_timed_write_snapshot(
            now=lambda: (_ for _ in ()).throw(RuntimeError("clock failure"))
        )
    _write_with_deadline(second, "after-clock-failure")
    later = first.read_timed_write_snapshot(now=lambda: datetime(2026, 1, 2, tzinfo=UTC))
    assert "after-clock-failure" in {record.memory_id for record in later.records}


def test_full_write_snapshot_covers_control_runtime_mixed_empty_and_all_write_paths(
    store_factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = store_factory(tmp_path / "store")

    store.stage_record(_record("control:stage", internal=True))
    assert store.read_snapshot()[0] == 0
    assert store.read_write_snapshot()[0] == 1

    store.upsert_record(_record("control:upsert", internal=True))
    store.write_records((_record("runtime:write"),))
    store.apply_batch(
        (_record("control:mixed", internal=True), _record("runtime:mixed")),
        expected_revision=1,
    )
    store.apply_batch((), expected_revision=2)

    data_revision, records = store.read_snapshot()
    write_revision, write_records = store.read_write_snapshot()
    assert data_revision == 2
    assert write_revision == 5
    assert {record.memory_id for record in records} == {
        "control:stage",
        "control:upsert",
        "runtime:write",
        "control:mixed",
        "runtime:mixed",
    }
    assert {record.memory_id for record in write_records} == {record.memory_id for record in records}


def test_write_snapshot_is_detached_for_nested_internal_records(
    store_factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = store_factory(tmp_path / "store")
    store.stage_record(_record("control:one", internal=True))

    write_revision, records = store.read_write_snapshot()
    records[0].content["nested"]["memory_id"] = "changed"

    reread_revision, reread = store.read_write_snapshot()
    assert write_revision == reread_revision == 1
    assert reread[0].content == {"nested": {"memory_id": "control:one"}}


def test_both_current_guards_commit_mixed_batch_and_advance_both_revisions(
    store_factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = store_factory(tmp_path / "store")
    store.stage_record(_record("control:prior", internal=True))
    expected_data_revision, _ = store.read_snapshot()
    expected_write_revision, _ = store.read_write_snapshot()

    committed_data_revision = store.apply_batch(
        (_record("control:mixed", internal=True), _record("runtime:mixed")),
        expected_revision=expected_data_revision,
        expected_write_revision=expected_write_revision,
    )

    data_revision, records = store.read_snapshot()
    write_revision, write_records = store.read_write_snapshot()
    assert committed_data_revision == data_revision == expected_data_revision + 1
    assert write_revision == expected_write_revision + 1
    assert {record.memory_id for record in records} == {
        "control:prior",
        "control:mixed",
        "runtime:mixed",
    }
    assert {record.memory_id for record in write_records} == {record.memory_id for record in records}


@pytest.mark.parametrize("invalid", [-1, True])
def test_invalid_write_guard_rejects_before_callback_or_mutation(
    store_factory: StoreFactory,
    tmp_path: Path,
    invalid: int,
) -> None:
    store = store_factory(tmp_path / "store")
    before = store.read_write_snapshot()
    callback_called = False

    def callback() -> None:
        nonlocal callback_called
        callback_called = True

    with pytest.raises(ValueError, match="nonnegative integer"):
        store.apply_batch(
            (_record("runtime:invalid"),),
            expected_revision=0,
            expected_write_revision=invalid,
            transaction_precondition=callback,
        )

    assert callback_called is False
    assert store.read_write_snapshot() == before


def test_stale_dual_guards_and_failed_preconditions_do_not_change_snapshot(
    store_factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = store_factory(tmp_path / "store")
    store.stage_record(_record("control:one", internal=True))
    stale_data_revision, _ = store.read_snapshot()
    stale_write_revision, _ = store.read_write_snapshot()
    store.stage_record(_record("runtime:two"))
    before = store.read_write_snapshot()

    with pytest.raises(MemoryPlaneRevisionConflictError):
        store.apply_batch(
            (_record("runtime:stale-write"),),
            expected_revision=1,
            expected_write_revision=stale_write_revision,
        )
    with pytest.raises(MemoryPlaneRevisionConflictError):
        store.apply_batch(
            (_record("runtime:stale-data"),),
            expected_revision=stale_data_revision,
            expected_write_revision=2,
        )
    with pytest.raises(MemoryPlaneRevisionConflictError):
        store.apply_batch(
            (_record("runtime:precondition"),),
            expected_revision=1,
            expected_write_revision=2,
            preconditions=(RecordAbsentPrecondition(memory_id="runtime:two"),),
        )

    assert store.read_write_snapshot() == before
    assert store.get_record("runtime:stale-write") is None
    assert store.get_record("runtime:stale-data") is None
    assert store.get_record("runtime:precondition") is None


class _RejectingPolicy:
    def validate(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        current: tuple[CanonicalMemoryRecord, ...],
        authorization: object | None,
    ) -> None:
        del records, current, authorization
        raise RuntimeError("rejected by test policy")


def test_policy_and_callback_failure_leave_write_snapshot_unchanged(
    store_factory: StoreFactory,
    tmp_path: Path,
) -> None:
    store = store_factory(tmp_path / "store")
    before = store.read_write_snapshot()

    with pytest.raises(RuntimeError, match="callback failure"):
        store.apply_batch(
            (_record("runtime:callback"),),
            expected_revision=0,
            expected_write_revision=0,
            transaction_precondition=lambda: (_ for _ in ()).throw(RuntimeError("callback failure")),
        )
    assert store.read_write_snapshot() == before

    store.install_governed_write_policy(_RejectingPolicy())
    with pytest.raises(RuntimeError, match="test policy"):
        store.apply_batch(
            (_record("runtime:policy"),),
            expected_revision=0,
            expected_write_revision=0,
        )
    assert store.read_write_snapshot() == before


def test_service_forwards_write_guard_only_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = InMemoryMemoryPlaneStore()
    original_apply_batch = legacy.apply_batch

    def old_apply_batch(
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions=(),
        authorization=None,
        transaction_precondition=None,
    ) -> int:
        return original_apply_batch(
            records,
            expected_revision=expected_revision,
            preconditions=preconditions,
            authorization=authorization,
            transaction_precondition=transaction_precondition,
        )

    monkeypatch.setattr(legacy, "apply_batch", old_apply_batch)
    service = MemoryPlaneService(record_store=legacy)
    service.conditionally_write_records((_record("control:legacy", internal=True),), preconditions=())
    assert legacy.read_write_snapshot()[0] == 1

    guarded_service = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    write_revision, _ = guarded_service.read_write_snapshot()
    guarded_service.conditionally_write_records(
        (_record("control:guarded", internal=True),),
        preconditions=(),
        expected_write_revision=write_revision,
    )
    assert guarded_service.read_write_snapshot()[0] == 1


def test_unit_of_work_commit_advances_full_write_revision() -> None:
    store = InMemoryMemoryPlaneStore()
    service = MemoryPlaneService(record_store=store)

    with service.unit_of_work() as unit_of_work:
        unit_of_work.stage_record(_record("control:uow", internal=True))
        unit_of_work.commit()

    assert store.read_snapshot()[0] == 0
    assert store.read_write_snapshot()[0] == 1


def test_unit_of_work_rejects_root_only_write_snapshot_and_guard() -> None:
    store = InMemoryMemoryPlaneStore()
    service = MemoryPlaneService(record_store=store)

    with service.unit_of_work() as unit_of_work:
        unit_of_work.stage_record(_record("control:pending", internal=True))
        pending = unit_of_work.pending_records
        with pytest.raises(RuntimeError, match="root memory-plane store"):
            service.read_write_snapshot()
        called = False

        def clock() -> datetime:
            nonlocal called
            called = True
            return datetime(2026, 1, 1, tzinfo=UTC)

        with pytest.raises(RuntimeError, match="root memory-plane store"):
            service.read_timed_write_snapshot(now=clock)
        assert called is False
        with pytest.raises(RuntimeError, match="root memory-plane store"):
            unit_of_work.apply_batch(
                (_record("control:guarded", internal=True),),
                expected_revision=0,
                expected_write_revision=0,
            )
        assert unit_of_work.pending_records == pending


def test_jsonl_reopen_and_competing_instances_use_persisted_write_revision(tmp_path: Path) -> None:
    path = tmp_path / "store"
    first = JsonlMemoryPlaneStore(path)
    second = JsonlMemoryPlaneStore(path)
    expected_write_revision, _ = first.read_write_snapshot()

    def apply(store: JsonlMemoryPlaneStore, memory_id: str) -> bool:
        try:
            store.apply_batch(
                (_record(memory_id, internal=True),),
                expected_revision=0,
                expected_write_revision=expected_write_revision,
            )
        except MemoryPlaneRevisionConflictError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda values: apply(*values), ((first, "control:first"), (second, "control:second"))))

    assert results.count(True) == 1
    reopened = JsonlMemoryPlaneStore(path)
    assert reopened.read_snapshot()[0] == 0
    assert reopened.read_write_snapshot()[0] == 1


def test_jsonl_replace_failure_preserves_write_snapshot_and_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "store"
    store = JsonlMemoryPlaneStore(path)
    store.stage_record(_record("control:one", internal=True))
    bytes_before = (path / "memory_records.jsonl").read_bytes()
    snapshot_before = store.read_write_snapshot()

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr("memorii.core.memory_plane.store.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        store.apply_batch(
            (_record("control:two", internal=True),),
            expected_revision=0,
            expected_write_revision=1,
        )

    assert (path / "memory_records.jsonl").read_bytes() == bytes_before
    assert store.read_write_snapshot() == snapshot_before
