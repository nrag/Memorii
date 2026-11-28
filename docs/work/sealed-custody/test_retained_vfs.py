"""Installed-SQLite tests for the native descriptor and release checks."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from retained_vfs_probe import ReleaseDenied, block_table, retained_reader

_HOT = b"already-authenticated-response"
_MARKER = b"physical-mutation-marker"
_COLD = b"x" * 425_000 + _MARKER


def _root(path: Path) -> str:
    with path.open("rb") as image:
        return block_table(image.fileno())[2]


def _found_index(connection: sqlite3.Connection) -> tuple[str, int]:
    query = "SELECT name, id FROM payloads INDEXED BY payload_lookup WHERE name = ?"
    plan = connection.execute("EXPLAIN QUERY PLAN " + query, ("item-0999",)).fetchall()
    assert any("COVERING INDEX payload_lookup" in row[3] for row in plan)
    row = connection.execute(query, ("item-0999",)).fetchone()
    assert row is not None
    return row


def _read_blob(connection: sqlite3.Connection, rowid: int, *, tail: bool = False) -> bytes:
    with connection.blobopen("payloads", "body", rowid, readonly=True) as blob:
        if tail:
            blob.seek(-len(_MARKER), 2)
        return blob.read()


@pytest.fixture
def image(tmp_path: Path) -> tuple[Path, str, int]:
    path = tmp_path / "partition.sqlite3"
    with closing(sqlite3.connect(path)) as owner, owner:
        owner.execute("CREATE TABLE payloads(id INTEGER PRIMARY KEY, name TEXT, body BLOB)")
        owner.executemany("INSERT INTO payloads VALUES (?, ?, ?)", [
            (1, "hot", _HOT), (2, "cold", _COLD),
            *((index + 3, f"item-{index:04}", b"") for index in range(1000)),
        ])
        owner.execute("CREATE INDEX payload_lookup ON payloads(name)")
    physical = path.read_bytes()
    offset = physical.index(_MARKER)
    assert offset > 4 * 65_536
    return path, _root(path), offset


def test_native_index_and_blob_read_original_inode_after_path_swap(
    image: tuple[Path, str, int], extension: Path,
) -> None:
    path, root, _ = image
    with retained_reader(path, root, extension) as reader:
        prior = reader.stats()
        path.replace(path.with_suffix(".retired"))
        with closing(sqlite3.connect(path)) as replacement, replacement:
            replacement.execute("CREATE TABLE unrelated(record TEXT)")
        assert reader.release(_found_index) == ("item-0999", 1002)
        indexed = reader.stats()
        assert indexed.blocks > prior.blocks
        assert reader.release(lambda conn: _read_blob(conn, 2)) == _COLD
        blob = reader.stats()
        assert blob.blocks > indexed.blocks
        assert not blob.failed
        with pytest.raises(sqlite3.DatabaseError):
            reader.release(lambda conn: conn.execute("ATTACH DATABASE ? AS foreign_db", (str(path),)).fetchall())


def test_mutation_after_ready_denies_blob_and_further_cached_release(
    image: tuple[Path, str, int], extension: Path,
) -> None:
    path, root, position = image
    with retained_reader(path, root, extension) as reader:
        assert reader.release(lambda conn: _read_blob(conn, 1)) == _HOT
        with path.open("r+b", buffering=0) as external:
            external.seek(position)
            external.write(b"!")
        with pytest.raises(ReleaseDenied, match="latched closed"):
            reader.release(lambda conn: _read_blob(conn, 2, tail=True))
        denied = reader.stats()
        assert denied.failed
        with pytest.raises(ReleaseDenied, match="latched closed"):
            reader.release(lambda conn: _read_blob(conn, 1))
        assert reader.stats() == denied


def test_late_covering_index_corruption_denies_release(
    image: tuple[Path, str, int], extension: Path,
) -> None:
    path, root, _ = image
    with closing(sqlite3.connect(path)) as ordinary:
        page_size, = ordinary.execute("PRAGMA page_size").fetchone()
        pages = ordinary.execute("SELECT pageno FROM dbstat WHERE name='payload_lookup'").fetchall()
    raw = path.read_bytes()
    hits = []
    for page, in pages:
        start = (page - 1) * page_size
        offset = raw.find(b"item-0999", start, start + page_size)
        if offset >= 0:
            hits.append(offset)
    (offset,) = hits
    with retained_reader(path, root, extension) as reader:
        assert reader.release(lambda conn: _read_blob(conn, 1)) == _HOT
        with path.open("r+b", buffering=0) as external:
            external.seek(offset)
            external.write(b"!")
        with pytest.raises(ReleaseDenied, match="latched closed"):
            reader.release(_found_index)
        assert reader.stats().failed


def test_buffered_result_stays_private_after_another_read_detects_corruption(
    image: tuple[Path, str, int], extension: Path,
) -> None:
    path, root, position = image
    with retained_reader(path, root, extension) as reader:
        def tamper_then_read() -> None:
            with path.open("r+b", buffering=0) as external:
                external.seek(position)
                external.write(b"!")
            with pytest.raises(ReleaseDenied, match="latched closed"):
                reader.release(lambda conn: _read_blob(conn, 2, tail=True))

        with pytest.raises(ReleaseDenied, match="latched closed"):
            reader.release(lambda conn: _read_blob(conn, 1), before_release=tamper_then_read)


def test_short_read_inside_signed_image_blocks_release(
    image: tuple[Path, str, int], extension: Path,
) -> None:
    path, root, position = image
    with retained_reader(path, root, extension) as reader:
        assert reader.release(lambda conn: _read_blob(conn, 1)) == _HOT
        os.truncate(path, position - 1)
        with pytest.raises(ReleaseDenied, match="latched closed"):
            reader.release(lambda conn: _read_blob(conn, 2, tail=True))
        assert reader.stats().failed


def test_different_bytes_cannot_start(
    image: tuple[Path, str, int], extension: Path,
) -> None:
    path, root, position = image
    with path.open("r+b", buffering=0) as external:
        external.seek(position)
        external.write(b"!")
    with pytest.raises(ReleaseDenied, match="image root differs"), retained_reader(path, root, extension):
        pytest.fail("an unauthenticated root reached readiness")
