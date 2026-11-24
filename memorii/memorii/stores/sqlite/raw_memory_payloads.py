"""Partition-local raw memory payloads and exact conversion from format 7."""

from __future__ import annotations

import hashlib
import sqlite3
from collections import deque
from collections.abc import Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from itertools import zip_longest
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.core.memory_plane.store import PersistedBatch

RAW_SCHEMA_VERSION = 8
RAW_CATALOG_NAMES = frozenset({"memory_payloads", "memory_batch_members"})

RAW_MEMORY_LAYOUTS = {
    "memory_batches": (("revision",), ("revision", "data_revision", "checksum", "created_utc", "member_count")),
    "memory_batch_members": (
        ("revision", "ordinal"), ("revision", "ordinal", "memory_id", "payload_digest"),
    ),
    "memory_current_records": (
        ("memory_id",),
        ("memory_id", "batch_revision", "payload_digest", "status", "domain", "source_kind", "insertion_order", "task_id"),
    ),
    "memory_payloads": (("payload_digest",), ("payload_digest", "raw_size", "codec")),
    "memory_record_versions": (
        ("memory_id", "batch_revision"), ("memory_id", "batch_revision", "payload_digest"),
    ),
}
RAW_CURRENT_BASE_SELECTOR = "INDEXED BY sqlite_autoindex_memory_current_records_1"
_LEGACY_TABLES = ("memory_batches", "memory_record_versions", "memory_current_records")
_CURRENT_INDEXES = {
    "insertion_order": "memory_current_records_insertion_order",
    "task_id": "memory_current_records_task_id",
    "status": "memory_current_records_status_lookup",
    "domain": "memory_current_records_domain_lookup",
    "source_kind": "memory_current_records_source_kind_lookup",
}
_SCHEMA = {
    "memory_payloads": """
        CREATE TABLE memory_payloads (
            payload_digest BLOB NOT NULL CHECK(length(payload_digest) = 32),
            raw_size INTEGER NOT NULL CHECK(raw_size > 0),
            codec INTEGER NOT NULL CHECK(codec = 0),
            body BLOB NOT NULL CHECK(length(body) = raw_size)
        ) STRICT
    """,
    "memory_payloads_digest": """
        CREATE UNIQUE INDEX memory_payloads_digest ON memory_payloads(payload_digest)
    """,
    "memory_batches": """
        CREATE TABLE memory_batches (
            revision INTEGER PRIMARY KEY CHECK(revision > 0),
            data_revision INTEGER NOT NULL CHECK(data_revision >= 0),
            checksum TEXT NOT NULL CHECK(length(checksum) = 64 AND checksum NOT GLOB '*[^0-9a-f]*'),
            created_utc TEXT NOT NULL,
            member_count INTEGER NOT NULL CHECK(member_count >= 0)
        ) STRICT
    """,
    "memory_record_versions": """
        CREATE TABLE memory_record_versions (
            memory_id TEXT NOT NULL,
            batch_revision INTEGER NOT NULL REFERENCES memory_batches(revision),
            payload_digest BLOB NOT NULL REFERENCES memory_payloads(payload_digest),
            PRIMARY KEY (memory_id, batch_revision)
        ) WITHOUT ROWID, STRICT
    """,
    "memory_batch_members": """
        CREATE TABLE memory_batch_members (
            revision INTEGER NOT NULL,
            ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
            memory_id TEXT NOT NULL,
            payload_digest BLOB NOT NULL REFERENCES memory_payloads(payload_digest),
            PRIMARY KEY (revision, ordinal),
            FOREIGN KEY (memory_id, revision) REFERENCES memory_record_versions(memory_id, batch_revision)
        ) WITHOUT ROWID, STRICT
    """,
    "memory_current_records": """
        CREATE TABLE memory_current_records (
            memory_id TEXT PRIMARY KEY,
            batch_revision INTEGER NOT NULL,
            payload_digest BLOB NOT NULL REFERENCES memory_payloads(payload_digest),
            status TEXT NOT NULL,
            domain TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            insertion_order INTEGER NOT NULL CHECK(insertion_order > 0),
            task_id TEXT,
            FOREIGN KEY (memory_id, batch_revision) REFERENCES memory_record_versions(memory_id, batch_revision)
        ) WITHOUT ROWID, STRICT
    """,
    **{
        index: f"CREATE {'UNIQUE ' if column == 'insertion_order' else ''}"
        f"INDEX {index} ON memory_current_records({column})"
        for column, index in _CURRENT_INDEXES.items()
    },
}
_PAYLOAD_DOMAIN = b"memorii.memory-record-payload.v1\x00"
_CHUNK_BYTES = 256 * 1024
_MAX_QUEUED_PAYLOAD_BYTES = 4 * 1024 * 1024
_MAX_PENDING_HASHES = 4
_RecordInput = tuple[str, str, str, str, str]


class RawPayloadFramingError(sqlite3.DatabaseError):
    """A valid historical batch has an unsupported exact byte framing."""


def payload_digest(raw: bytes) -> bytes:
    digest = hashlib.sha256(_PAYLOAD_DOMAIN)
    digest.update(raw)
    return digest.digest()


def validate_raw_schema(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA main.encoding").fetchone()[0] != "UTF-8":
        raise sqlite3.DatabaseError("raw payload storage requires UTF-8 SQLite")
    names = tuple(RAW_MEMORY_LAYOUTS)
    placeholders = ",".join("?" for _ in names)
    entries = dict(
        connection.execute(
            f"SELECT name,sql FROM main.sqlite_schema WHERE tbl_name IN ({placeholders})", names,
        ).fetchall()
    )
    if entries != {name: sql.strip() for name, sql in _SCHEMA.items()}:
        raise sqlite3.DatabaseError("raw memory payload schema differs from its declared format")


def _require_index_parity(
    connection: sqlite3.Connection, query: str, index: str, *, base_selector: str = "NOT INDEXED",
) -> None:
    table_rows = connection.execute(query.format(selector=base_selector))
    index_rows = connection.execute(query.format(selector=f"INDEXED BY {index}"))
    # Separate walks catch independent covering-index and base-table page changes.
    if any(left != right for left, right in zip_longest(table_rows, index_rows)):
        raise sqlite3.DatabaseError(f"raw memory lookup index differs from its base table: {index}")


def _payload_location(row: sqlite3.Row) -> tuple[int, bytes, int]:
    rowid, expected, size, codec, body_type = row[:5]
    if (
        not isinstance(expected, bytes) or len(expected) != 32
        or type(size) is not int or size <= 0 or codec != 0 or body_type != "blob"
    ):
        raise sqlite3.DatabaseError("invalid raw memory payload metadata")
    return rowid, expected, size


@contextmanager
def _open_raw_body(connection: sqlite3.Connection, rowid: int, size: int) -> Iterator[sqlite3.Blob]:
    with connection.blobopen("memory_payloads", "body", rowid, readonly=True) as blob:
        if len(blob) != size:
            raise sqlite3.DatabaseError("raw memory payload length differs")
        yield blob


def _verify_body(connection: sqlite3.Connection, rowid: int, expected: bytes, size: int) -> None:
    with _open_raw_body(connection, rowid, size) as blob:
        digest = hashlib.sha256(_PAYLOAD_DOMAIN)
        for chunk in iter(lambda: blob.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
        if digest.digest() != expected:
            raise sqlite3.DatabaseError("raw memory payload digest differs")


def _verify_buffer(raw: bytes, expected: bytes) -> None:
    if payload_digest(raw) != expected:
        raise sqlite3.DatabaseError("raw memory payload digest differs")


def verify_payload_at_digest(connection: sqlite3.Connection, digest: bytes) -> None:
    row = connection.execute(
        "SELECT rowid,payload_digest,raw_size,codec,typeof(body) FROM main.memory_payloads WHERE payload_digest = ?",
        (digest,),
    ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError("missing updated memory payload")
    _verify_body(connection, *_payload_location(row))


def _require_reference_closure(connection: sqlite3.Connection) -> None:
    incomplete_header = connection.execute("""
        SELECT 1 FROM memory_batches AS b LEFT JOIN (
            SELECT revision, count(*) AS members, min(ordinal) AS first, max(ordinal) AS last
            FROM memory_batch_members GROUP BY revision
        ) AS m USING(revision)
        WHERE b.member_count != coalesce(m.members,0)
           OR (b.member_count > 0 AND (m.first != 0 OR m.last != b.member_count-1))
        LIMIT 1
    """).fetchone()
    if incomplete_header is not None:
        raise sqlite3.DatabaseError("raw memory batch member positions differ from its header")
    versions: dict[tuple[str, int], bytes] = {}
    latest: dict[str, tuple[int, bytes]] = {}
    revisions = {row[0] for row in connection.execute("SELECT revision FROM memory_batches")}
    for identity, revision, key in connection.execute("""
        SELECT memory_id,batch_revision,payload_digest
        FROM memory_record_versions ORDER BY memory_id,batch_revision
    """):
        if revision not in revisions:
            raise sqlite3.DatabaseError("raw memory version references a missing batch")
        versions[identity, revision] = key
        latest[identity] = revision, key
    for revision, identity, key in connection.execute(
        "SELECT revision,memory_id,payload_digest FROM memory_batch_members",
    ):
        if versions.pop((identity, revision), None) != key:
            raise sqlite3.DatabaseError("raw memory batch member differs from its version")
    if versions:
        raise sqlite3.DatabaseError("raw memory versions include an unlisted batch member")
    ordering = set()
    for identity, revision, key, position in connection.execute(
        "SELECT memory_id,batch_revision,payload_digest,insertion_order FROM memory_current_records",
    ):
        if latest.pop(identity, None) != (revision, key) or position in ordering or position <= 0:
            raise sqlite3.DatabaseError("raw memory current record differs from its latest version")
        ordering.add(position)
    if latest:
        raise sqlite3.DatabaseError("raw memory current projection is incomplete")
    expected_keys = {row[0] for row in connection.execute("SELECT payload_digest FROM memory_record_versions")}
    actual_keys = {
        row[0] for row in connection.execute("SELECT payload_digest FROM memory_payloads NOT INDEXED")
    }
    if expected_keys != actual_keys:
        raise sqlite3.DatabaseError("raw memory payloads include missing or unreferenced rows")


def _bounded_payload_rows(connection: sqlite3.Connection) -> sqlite3.Cursor:
    # Check the actual SQLite BLOB length before materializing a body. The
    # stored size is still untrusted at this point in acquisition.
    return connection.execute("""
        SELECT rowid,payload_digest,raw_size,codec,typeof(body),
               CASE WHEN typeof(body) = 'blob' THEN
                   CASE WHEN length(body) BETWEEN 1 AND ? AND length(body) = raw_size THEN body END
               END
        FROM main.memory_payloads NOT INDEXED ORDER BY rowid
    """, (_MAX_QUEUED_PAYLOAD_BYTES,))


def verify_raw_payloads(connection: sqlite3.Connection) -> None:
    """Check each raw body once and bind base-table metadata to its lookup order."""
    _require_index_parity(
        connection,
        "SELECT payload_digest,rowid FROM main.memory_payloads {selector} ORDER BY payload_digest",
        "memory_payloads_digest",
    )
    for column, index in _CURRENT_INDEXES.items():
        _require_index_parity(
            connection,
            f"SELECT {column},memory_id FROM main.memory_current_records {{selector}} ORDER BY {column},memory_id",
            index,
            base_selector=RAW_CURRENT_BASE_SELECTOR,
        )
    _require_reference_closure(connection)
    rows = _bounded_payload_rows(connection)
    # Keep reads on the verified transaction and drain the queue before fetching
    # another body. Bounded Python buffers occupy at most 16 MiB per scan.
    pending: deque[Future[None]] = deque()
    with ThreadPoolExecutor(max_workers=2) as workers:
        while True:
            if len(pending) == _MAX_PENDING_HASHES:
                pending.popleft().result()
            row = rows.fetchone()
            if row is None:
                break
            rowid, expected, size = _payload_location(row)
            raw = row[5]
            if raw is None:
                _verify_body(connection, rowid, expected, size)
            elif not isinstance(raw, bytes) or len(raw) != size:
                raise sqlite3.DatabaseError("raw memory payload length differs")
            elif size < _CHUNK_BYTES:
                _verify_buffer(raw, expected)
            else:
                pending.append(workers.submit(_verify_buffer, raw, expected))
        for result in pending:
            result.result()


def iter_batch_rows(connection: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    return iter(connection.execute("""
        SELECT b.revision,b.data_revision,b.checksum,
               '{"revision":' || b.revision || ',"data_revision":' || b.data_revision ||
               ',"records":[' || coalesce((
                   SELECT group_concat(wire, ',') FROM (
                       SELECT CAST(p.body AS TEXT) AS wire
                       FROM memory_batch_members AS m JOIN memory_payloads AS p USING(payload_digest)
                       WHERE m.revision = b.revision ORDER BY m.ordinal
                   )
               ),'') || '],"checksum":"' || b.checksum || '"}' AS batch_json
        FROM memory_batches AS b ORDER BY b.revision
    """))


def _validated_batch(row: sqlite3.Row | tuple[int, int, str, str]) -> PersistedBatch:
    from memorii.core.memory_plane.store import PersistedBatch

    revision, data_revision, checksum, wire = row
    try:
        batch = PersistedBatch.model_validate_json(wire)
    except ValueError:
        raise sqlite3.DatabaseError(f"invalid memory batch at revision {revision}") from None
    if (batch.revision, batch.data_revision, batch.checksum) != (revision, data_revision, checksum):
        raise sqlite3.DatabaseError(f"memory batch metadata differs at revision {revision}")
    if batch.model_dump_json() != wire:
        raise RawPayloadFramingError(f"unsupported exact memory batch framing at revision {revision}")
    return batch


def _legacy_batches(connection: sqlite3.Connection, table: str) -> Iterator[tuple[PersistedBatch, str]]:
    from memorii.core.memory_plane.store import contains_runtime_context

    state = connection.execute("SELECT write_revision,data_revision FROM memory_revision_state WHERE id=1").fetchone()
    revision = data_revision = 0
    for row in connection.execute(
        f"SELECT revision,data_revision,checksum,batch_json,created_utc FROM {table} NOT INDEXED ORDER BY revision",
    ):
        batch = _validated_batch(tuple(row[:4]))
        revision += 1
        data_revision += int(contains_runtime_context(batch.records))
        if (batch.revision, batch.data_revision) != (revision, data_revision):
            raise sqlite3.DatabaseError(f"memory batch revision chain differs at revision {batch.revision}")
        yield batch, row["created_utc"]
    if state is None or tuple(state) != (revision, data_revision):
        raise sqlite3.DatabaseError("memory revision state differs from legacy batch chain")


def validate_upgrade_framing(connection: sqlite3.Connection) -> None:
    """Validate the historical writer's framing and logical chain in a read-only snapshot."""
    for _ in _legacy_batches(connection, "memory_batches"):
        pass


def _insert_payload(connection: sqlite3.Connection, raw: bytes) -> bytes:
    digest = payload_digest(raw)
    inserted = connection.execute("""
        INSERT INTO memory_payloads VALUES (?, ?, 0, ?)
        ON CONFLICT(payload_digest) DO NOTHING
        RETURNING payload_digest
    """, (digest, len(raw), raw)).fetchone()
    if inserted is None:
        existing = connection.execute(
            "SELECT raw_size,codec,body FROM memory_payloads WHERE payload_digest = ?", (digest,),
        ).fetchone()
        if existing is None or tuple(existing) != (len(raw), 0, raw):
            raise sqlite3.DatabaseError("reused memory payload differs from its content coordinate")
    return digest


def _append_validated_batch(
    connection: sqlite3.Connection, batch: PersistedBatch, created_utc: str,
    records: Sequence[tuple[CanonicalMemoryRecord, str]],
) -> None:
    connection.execute(
        "INSERT INTO memory_batches VALUES (?, ?, ?, ?, ?)",
        (batch.revision, batch.data_revision, batch.checksum, created_utc, len(records)),
    )
    position = connection.execute(
        "SELECT COALESCE(MAX(insertion_order), 0) FROM memory_current_records",
    ).fetchone()[0]
    for ordinal, (record, wire) in enumerate(records):
        key = _insert_payload(connection, wire.encode("utf-8"))
        connection.execute(
            "INSERT INTO memory_record_versions VALUES (?, ?, ?)",
            (record.memory_id, batch.revision, key),
        )
        connection.execute(
            "INSERT INTO memory_batch_members VALUES (?, ?, ?, ?)",
            (batch.revision, ordinal, record.memory_id, key),
        )
        existing = connection.execute(
            "SELECT 1 FROM memory_current_records WHERE memory_id = ?", (record.memory_id,),
        ).fetchone()
        position += int(existing is None)
        connection.execute("""
            INSERT INTO memory_current_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                batch_revision = excluded.batch_revision, payload_digest = excluded.payload_digest,
                status = excluded.status, domain = excluded.domain, source_kind = excluded.source_kind,
                task_id = excluded.task_id
        """, (
            record.memory_id, batch.revision, key, record.status.value, record.domain.value,
            record.source_kind, position, record.task_id,
        ))


def append_batch(
    connection: sqlite3.Connection, *, revision: int, data_revision: int, checksum: str,
    batch_json: str, records_json: Sequence[_RecordInput], created_utc: str,
) -> None:
    batch = _validated_batch((revision, data_revision, checksum, batch_json))
    records = tuple((record, record.model_dump_json()) for record in batch.records)
    if tuple(records_json) != tuple(
        (record.memory_id, wire, record.status.value, record.domain.value, record.source_kind)
        for record, wire in records
    ):
        raise sqlite3.DatabaseError("raw memory append selectors differ from the typed batch")
    _append_validated_batch(connection, batch, created_utc, records)
    connection.execute(
        "UPDATE memory_revision_state SET write_revision = ?, data_revision = ? WHERE id = 1",
        (revision, data_revision),
    )


def _require_exact_legacy_rows(connection: sqlite3.Connection) -> None:
    versions = {
        (identity, rev): key
        for identity, rev, key in connection.execute("SELECT * FROM memory_record_versions")
    }
    for identity, rev, wire in connection.execute(
        "SELECT memory_id,batch_revision,record_json FROM legacy_memory_record_versions NOT INDEXED",
    ):
        if versions.pop((identity, rev), None) != payload_digest(wire.encode("utf-8")):
            raise sqlite3.DatabaseError("legacy memory record version differs from its exact batch member")
    if versions:
        raise sqlite3.DatabaseError("legacy memory version catalog is incomplete")
    current = {
        identity: (key, status, domain, kind, position)
        for identity, key, status, domain, kind, position in connection.execute(
            "SELECT memory_id,payload_digest,status,domain,source_kind,insertion_order FROM memory_current_records",
        )
    }
    for identity, wire, status, domain, kind, position in connection.execute(
        "SELECT memory_id,record_json,status,domain,source_kind,insertion_order "
        "FROM legacy_memory_current_records NOT INDEXED",
    ):
        if current.pop(identity, None) != (payload_digest(wire.encode("utf-8")), status, domain, kind, position):
            raise sqlite3.DatabaseError("legacy memory current record differs from its exact latest batch member")
    if current:
        raise sqlite3.DatabaseError("legacy current memory catalog is incomplete")


def convert_v7(connection: sqlite3.Connection) -> None:
    """Replace the three legacy catalogs within the owner staging transaction."""
    version = connection.execute("SELECT value FROM partition_schema WHERE key='schema_version'").fetchone()
    if not connection.in_transaction or version is None or version[0] != "7":
        raise sqlite3.DatabaseError("raw payload conversion requires a staged format 7 transaction")
    for name in _LEGACY_TABLES:
        connection.execute(f"ALTER TABLE {name} RENAME TO legacy_{name}")
    for sql in _SCHEMA.values():
        connection.execute(sql.strip())
    for batch, created in _legacy_batches(connection, "legacy_memory_batches"):
        records = tuple((record, record.model_dump_json()) for record in batch.records)
        _append_validated_batch(connection, batch, created, records)
    _require_exact_legacy_rows(connection)
    for name in reversed(_LEGACY_TABLES):
        connection.execute(f"DROP TABLE legacy_{name}")
    connection.execute(
        "UPDATE partition_schema SET value=? WHERE key='schema_version'", (str(RAW_SCHEMA_VERSION),),
    )
