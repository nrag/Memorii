"""SQLite memory-plane store durability, parity and fail-closed behavior."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    MemoryPlaneCorruptionError,
    MemoryPlaneRevisionConflictError,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from memorii.stores.sqlite.partition import PartitionDataRepository


def _record(
    memory_id: str,
    *,
    marker: str = "original",
    visibility: MemoryRecordVisibility = MemoryRecordVisibility.RUNTIME_CONTEXT,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.SEMANTIC,
        text=marker,
        content={"nested": {"marker": marker}},
        status=CommitStatus.COMMITTED,
        source_kind="sqlite_store",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=visibility,
    )


def _internal_record(memory_id: str) -> CanonicalMemoryRecord:
    return _record(memory_id, visibility=MemoryRecordVisibility.INTERNAL_CONTROL)


def test_fresh_handle_restores_records_and_both_revisions(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    store.stage_record(_record("mem:one"))
    store.stage_record(_internal_record("mem:internal"))
    store.stage_record(_record("mem:two"))
    assert store.revision() == 2

    reopened = SqliteMemoryPlaneStore(partition_dir)
    revision, records = reopened.read_snapshot()
    write_revision, _ = reopened.read_write_snapshot()
    assert revision == 2
    assert write_revision == 3
    assert [record.memory_id for record in records] == ["mem:one", "mem:internal", "mem:two"]


def test_internal_only_batches_do_not_advance_data_revision(tmp_path: Path) -> None:
    store = SqliteMemoryPlaneStore(tmp_path / "store")
    store.stage_record(_internal_record("mem:control"))
    assert store.revision() == 0
    assert store.read_write_snapshot()[0] == 1


def test_record_versions_retain_every_batch(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    store.stage_record(_record("mem:one", marker="first"))
    store.stage_record(_record("mem:one", marker="second"))
    store.stage_record(_record("mem:one", marker="third"))

    connection = sqlite3.connect(partition_dir / "partition.sqlite3")
    try:
        versions = connection.execute(
            "SELECT batch_revision, record_json FROM memory_record_versions"
            " WHERE memory_id = ? ORDER BY batch_revision",
            ("mem:one",),
        ).fetchall()
    finally:
        connection.close()
    assert [row[0] for row in versions] == [1, 2, 3]
    assert '"first"' in versions[0][1]
    assert '"third"' in versions[2][1]
    current = store.get_record("mem:one")
    assert current is not None and current.text == "third"


def test_second_handle_write_is_visible_and_revalidated(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    first = SqliteMemoryPlaneStore(partition_dir)
    second = SqliteMemoryPlaneStore(partition_dir)
    first.stage_record(_record("mem:first"))
    second.stage_record(_record("mem:second"))
    assert first.revision() == 2
    revision, records = first.read_snapshot()
    assert revision == 2
    assert [record.memory_id for record in records] == ["mem:first", "mem:second"]


def test_first_insertion_order_survives_updates(tmp_path: Path) -> None:
    store = SqliteMemoryPlaneStore(tmp_path / "store")
    store.stage_record(_record("mem:a"))
    store.stage_record(_record("mem:b"))
    store.stage_record(_record("mem:c"))
    store.stage_record(_record("mem:a", marker="updated"))
    store.stage_record(_record("mem:b", marker="updated"))
    assert [record.memory_id for record in store.list_records()] == ["mem:a", "mem:b", "mem:c"]
    assert store.get_record("mem:a") is not None and store.get_record("mem:a").text == "updated"


def test_list_records_filters_match_the_in_memory_reference(tmp_path: Path) -> None:
    reference = InMemoryMemoryPlaneStore()
    store = SqliteMemoryPlaneStore(tmp_path / "store")
    for record in (
        _record("mem:semantic"),
        _internal_record("mem:internal"),
        _record("mem:other-kind", marker="kind"),
    ):
        reference.stage_record(record.model_copy(deep=True))
        store.stage_record(record)
    reference_records = reference.list_records(status=CommitStatus.COMMITTED)
    store_records = store.list_records(status=CommitStatus.COMMITTED)
    assert [r.memory_id for r in store_records] == [r.memory_id for r in reference_records]


def test_precondition_rejection_leaves_no_partial_batch(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    store.stage_record(_record("mem:one"))
    from memorii.core.memory_plane.store import RecordDigestPrecondition

    with pytest.raises(MemoryPlaneRevisionConflictError):
        store.apply_batch(
            (_record("mem:two"),),
            expected_revision=None,
            preconditions=(
                RecordDigestPrecondition(memory_id="mem:one", expected_digest="0" * 64),
            ),
        )
    reopened = SqliteMemoryPlaneStore(partition_dir)
    assert reopened.read_write_snapshot()[0] == 1
    assert reopened.get_record("mem:two") is None


def test_tampered_batch_bytes_fail_closed_on_read_and_write(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    store.stage_record(_record("mem:one"))
    store.stage_record(_record("mem:two"))

    connection = sqlite3.connect(partition_dir / "partition.sqlite3")
    try:
        connection.execute("UPDATE memory_batches SET batch_json = '{\"tampered\": true}' WHERE revision = 1")
        connection.commit()
    finally:
        connection.close()

    reopened = SqliteMemoryPlaneStore(partition_dir)
    with pytest.raises(MemoryPlaneCorruptionError):
        reopened.list_records()
    with pytest.raises(MemoryPlaneCorruptionError):
        reopened.stage_record(_record("mem:three"))


def test_tampered_checksum_column_fails_closed(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    store.stage_record(_record("mem:one"))

    connection = sqlite3.connect(partition_dir / "partition.sqlite3")
    try:
        connection.execute("UPDATE memory_batches SET checksum = '0' * 64 WHERE revision = 1")
        connection.commit()
    finally:
        connection.close()

    reopened = SqliteMemoryPlaneStore(partition_dir)
    with pytest.raises(MemoryPlaneCorruptionError):
        reopened.read_snapshot()


def test_revision_state_desync_fails_closed(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    store.stage_record(_record("mem:one"))

    connection = sqlite3.connect(partition_dir / "partition.sqlite3")
    try:
        connection.execute("UPDATE memory_revision_state SET data_revision = 5 WHERE id = 1")
        connection.commit()
    finally:
        connection.close()

    reopened = SqliteMemoryPlaneStore(partition_dir)
    with pytest.raises(MemoryPlaneCorruptionError):
        reopened.revision()


def test_partition_rejects_unknown_future_schema(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    store.stage_record(_record("mem:one"))
    store.partition.close()

    connection = sqlite3.connect(partition_dir / "partition.sqlite3")
    try:
        connection.execute("UPDATE partition_schema SET value = '999' WHERE key = 'schema_version'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(sqlite3.DatabaseError, match="unsupported partition schema"):
        SqliteMemoryPlaneStore(partition_dir)


def test_protected_secret_permissions_are_owner_only(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    secret = store.load_or_create_protected_secret(purpose="sqlite-store-test", length=32)
    again = SqliteMemoryPlaneStore(partition_dir).load_or_create_protected_secret(
        purpose="sqlite-store-test", length=32
    )
    assert secret == again
    secret_path = next((partition_dir / ".protected").glob("*.key"))
    assert secret_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(MemoryPlaneCorruptionError):
        store.load_or_create_protected_secret(purpose="sqlite-store-test", length=64)


def test_batches_are_appended_without_rewriting_history(tmp_path: Path) -> None:
    partition_dir = tmp_path / "store"
    store = SqliteMemoryPlaneStore(partition_dir)
    store.stage_record(_record("mem:one"))
    connection = sqlite3.connect(partition_dir / "partition.sqlite3")
    try:
        first_row = connection.execute(
            "SELECT rowid, batch_json FROM memory_batches WHERE revision = 1"
        ).fetchone()
    finally:
        connection.close()
    for index in range(5):
        store.stage_record(_record(f"mem:extra:{index}"))
    connection = sqlite3.connect(partition_dir / "partition.sqlite3")
    try:
        first_row_after = connection.execute(
            "SELECT rowid, batch_json FROM memory_batches WHERE revision = 1"
        ).fetchone()
        count = connection.execute("SELECT COUNT(*) FROM memory_batches").fetchone()[0]
    finally:
        connection.close()
    assert first_row == first_row_after
    assert count == 6


def test_shared_partition_serves_two_domain_store_views(tmp_path: Path) -> None:
    partition = PartitionDataRepository(tmp_path / "store" / "partition.sqlite3")
    try:
        first = SqliteMemoryPlaneStore(partition)
        second = SqliteMemoryPlaneStore(partition)
        first.stage_record(_record("mem:first"))
        revision, records = second.read_snapshot()
        assert revision == 1
        assert [record.memory_id for record in records] == ["mem:first"]
    finally:
        partition.close()
