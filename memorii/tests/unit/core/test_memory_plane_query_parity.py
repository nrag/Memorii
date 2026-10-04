"""Indexed typed queries equal authorized scans, with authenticated cursors."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.query import (
    MemoryPlaneCursorError,
    MemoryPlaneQuery,
    QueryCursorCodec,
)
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


def _record(memory_id: str, *, domain: MemoryDomain, status: CommitStatus, kind: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=domain,
        text=memory_id,
        status=status,
        source_kind=kind,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _seeded_store(tmp_path: Path) -> SqliteMemoryPlaneStore:
    store = SqliteMemoryPlaneStore(tmp_path / "store")
    records = []
    for index in range(60):
        domain = [MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC, MemoryDomain.USER][index % 3]
        status = [CommitStatus.COMMITTED, CommitStatus.CANDIDATE][index % 2]
        kind = ["provider", "hermes", "runtime"][index % 3]
        records.append(_record(f"mem:parity:{index}", domain=domain, status=status, kind=kind))
    store.write_records(tuple(records))
    return store


def _authorized_scan(store: SqliteMemoryPlaneStore, query: MemoryPlaneQuery) -> list[CanonicalMemoryRecord]:
    reference = store.list_records(
        status=query.statuses[0] if len(query.statuses) == 1 else None,
        domains=[query.domains[0]] if len(query.domains) == 1 else None,
        source_kind=query.source_kinds[0] if len(query.source_kinds) == 1 else None,
    )
    return [
        record
        for record in reference
        if (not query.statuses or record.status in query.statuses)
        and (not query.domains or record.domain in query.domains)
        and (not query.source_kinds or record.source_kind in query.source_kinds)
    ]


@pytest.mark.parametrize(
    "query",
    [
        MemoryPlaneQuery(kind="filtered_records"),
        MemoryPlaneQuery(kind="filtered_records", domains=(MemoryDomain.SEMANTIC,)),
        MemoryPlaneQuery(
            kind="filtered_records",
            domains=(MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC),
            statuses=(CommitStatus.COMMITTED,),
        ),
        MemoryPlaneQuery(kind="filtered_records", source_kinds=("provider", "runtime")),
        MemoryPlaneQuery(
            kind="filtered_records",
            statuses=(CommitStatus.CANDIDATE,),
            source_kinds=("hermes",),
        ),
    ],
)
def test_indexed_query_equals_authorized_scan(tmp_path: Path, query: MemoryPlaneQuery) -> None:
    store = _seeded_store(tmp_path)
    collected: list[CanonicalMemoryRecord] = []
    cursor = None
    while True:
        page = store.query_records(query, cursor=cursor)
        collected.extend(page.records)
        if page.next_cursor is None:
            assert not page.truncated
            break
        cursor = page.next_cursor
    reference = _authorized_scan(store, query)
    assert [record.memory_id for record in collected] == [
        record.memory_id for record in reference
    ]


def test_pagination_walks_the_complete_set_in_order(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    query = MemoryPlaneQuery(kind="filtered_records", page_size=7)
    ids: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = store.query_records(query, cursor=cursor)
        assert len(page.records) <= 7
        ids.extend(record.memory_id for record in page.records)
        pages += 1
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert ids == [record.memory_id for record in store.list_records()]
    assert pages == 9  # 60 records in pages of 7


def test_record_lookup_returns_one_record(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    page = store.query_records(MemoryPlaneQuery(kind="record_lookup", memory_id="mem:parity:10"))
    assert [record.memory_id for record in page.records] == ["mem:parity:10"]
    assert page.next_cursor is None


def test_record_lookup_respects_filters(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    query = MemoryPlaneQuery(
        kind="record_lookup",
        memory_id="mem:parity:10",
        domains=(MemoryDomain.USER,),
    )
    assert store.query_records(query).records == ()


def test_cursor_rejects_revision_change_and_forgery(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    query = MemoryPlaneQuery(kind="filtered_records", page_size=10)
    first = store.query_records(query)
    assert first.next_cursor is not None

    stale_query = MemoryPlaneQuery(
        kind="filtered_records", page_size=10, source_kinds=("provider",)
    )
    with pytest.raises(MemoryPlaneCursorError, match="another query"):
        store.query_records(stale_query, cursor=first.next_cursor)

    store.write_records((_record("mem:parity:new", domain=MemoryDomain.SEMANTIC, status=CommitStatus.COMMITTED, kind="provider"),))
    with pytest.raises(MemoryPlaneCursorError, match="stale"):
        store.query_records(query, cursor=first.next_cursor)

    forged = first.next_cursor[:-4] + "beef"
    with pytest.raises(MemoryPlaneCursorError, match="signature"):
        store.query_records(query, cursor=forged)


def test_cursor_expires(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    query = MemoryPlaneQuery(kind="filtered_records", page_size=10)
    clock = datetime(2026, 1, 1, tzinfo=UTC)
    first = store.query_records(query, now=lambda: clock)
    assert first.next_cursor is not None
    expired_now = clock + timedelta(minutes=6)
    with pytest.raises(MemoryPlaneCursorError, match="expired"):
        store.query_records(query, cursor=first.next_cursor, now=lambda: expired_now)


def test_page_size_bounds_are_enforced() -> None:
    with pytest.raises(ValueError):
        MemoryPlaneQuery(kind="filtered_records", page_size=0)
    with pytest.raises(ValueError):
        MemoryPlaneQuery(kind="filtered_records", page_size=501)
    with pytest.raises(ValueError):
        MemoryPlaneQuery(kind="filtered_records", domains=(MemoryDomain.SEMANTIC,), extra=True)  # type: ignore[call-arg]


def test_cursor_codec_requires_a_strong_key() -> None:
    with pytest.raises(ValueError):
        QueryCursorCodec(b"short")


def test_visibility_rule_unchanged_for_queries(tmp_path: Path) -> None:
    store = SqliteMemoryPlaneStore(tmp_path / "store")
    store.write_records(
        (
            _record(
                "mem:internal",
                domain=MemoryDomain.SEMANTIC,
                status=CommitStatus.COMMITTED,
                kind="control",
            ).model_copy(update={"visibility": MemoryRecordVisibility.INTERNAL_CONTROL}),
        )
    )
    page = store.query_records(MemoryPlaneQuery(kind="filtered_records"))
    # Internal-control records are stored and queryable by their owning
    # domain readers; the runtime-context visibility rule governs revisions,
    # not query eligibility.
    assert [record.memory_id for record in page.records] == ["mem:internal"]
    assert store.revision() == 0
