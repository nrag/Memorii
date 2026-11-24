"""Experimental byte-exact SQLite payload projection for capacity diagnostics."""

from __future__ import annotations

import hashlib
import sqlite3
import zlib
from collections.abc import Iterable, Iterator
from contextlib import closing
from pathlib import Path
from time import perf_counter_ns

from memorii.core.memory_plane.store import PersistedBatch
from memorii.core.persistence.contracts import MaterializationCatalogEntry, RuntimeMaterializationManifest
from memorii.stores.sqlite.materialization_accumulator import MaterializationAccumulator
from memorii.stores.sqlite.materialization_sql import _key_bytes, _value_digest

_MAX_PAYLOAD_BYTES = 16 * 1024**2
_MAX_BATCH_BYTES = 64 * 1024**2
_CATALOGS = ("memory_batches", "memory_current_records", "memory_record_versions")
_KEY_LENGTH = {"memory_batches": 1, "memory_current_records": 1, "memory_record_versions": 2}
_ORIGINAL_SQL = {
    "memory_batches": "SELECT revision,data_revision,checksum,batch_json,created_utc FROM memory_batches ORDER BY revision",
    "memory_current_records": (
        "SELECT memory_id,record_json,status,domain,source_kind,insertion_order FROM memory_current_records "
        "ORDER BY memory_id COLLATE BINARY"
    ),
    "memory_record_versions": (
        "SELECT memory_id,batch_revision,record_json FROM memory_record_versions "
        "ORDER BY memory_id COLLATE BINARY,batch_revision"
    ),
}
_SCHEMA = """
CREATE TABLE probe_payloads (
    digest BLOB PRIMARY KEY NOT NULL CHECK(length(digest) = 32),
    codec INTEGER NOT NULL CHECK(codec IN (0, 1)),
    raw_size INTEGER NOT NULL CHECK(raw_size > 0),
    body BLOB NOT NULL
) WITHOUT ROWID;
CREATE TABLE probe_batches (
    revision INTEGER PRIMARY KEY,
    data_revision INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    member_count INTEGER NOT NULL
);
CREATE TABLE probe_members (
    revision INTEGER NOT NULL REFERENCES probe_batches(revision),
    ordinal INTEGER NOT NULL,
    digest BLOB NOT NULL REFERENCES probe_payloads(digest),
    PRIMARY KEY(revision, ordinal)
) WITHOUT ROWID;
CREATE TABLE probe_current (
    memory_id TEXT PRIMARY KEY,
    digest BLOB NOT NULL REFERENCES probe_payloads(digest),
    status TEXT NOT NULL,
    domain TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    insertion_order INTEGER NOT NULL UNIQUE
) WITHOUT ROWID;
CREATE TABLE probe_versions (
    memory_id TEXT NOT NULL,
    revision INTEGER NOT NULL REFERENCES probe_batches(revision),
    digest BLOB NOT NULL REFERENCES probe_payloads(digest),
    PRIMARY KEY(memory_id, revision)
) WITHOUT ROWID;
CREATE INDEX probe_members_digest ON probe_members(digest);
CREATE INDEX probe_current_digest ON probe_current(digest);
CREATE INDEX probe_versions_digest ON probe_versions(digest);
"""
_Scalar = int | str | None


class PayloadProbeError(ValueError):
    """The diagnostic projection fails an input or parity check."""


def _read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _require_v7(connection: sqlite3.Connection) -> None:
    row = connection.execute("SELECT value FROM partition_schema WHERE key='schema_version'").fetchone()
    if row is None or row[0] != "7":
        raise PayloadProbeError("payload probe expects partition schema v7")


def _catalog(catalog: str, rows: Iterable[tuple[bytes, bytes]]) -> MaterializationCatalogEntry:
    tree = MaterializationAccumulator.from_sorted_digests(rows)
    return MaterializationCatalogEntry(catalog=catalog, row_count=tree.row_count, digest=tree.catalog_digest(catalog))


def read_legacy_payload_manifests(source: Path) -> RuntimeMaterializationManifest:
    """Recompute the original three v7 catalogs from a caller-verified snapshot."""
    entries = []
    with closing(_read_only(source)) as connection:
        connection.execute("BEGIN")
        _require_v7(connection)
        for catalog, query in _ORIGINAL_SQL.items():
            rows = connection.execute(query)
            key_length = _KEY_LENGTH[catalog]
            entries.append(
                _catalog(catalog, ((_key_bytes(tuple(row)[:key_length]), _value_digest(row)) for row in rows))
            )
    return RuntimeMaterializationManifest(catalogs=tuple(entries))


def _put_payload(connection: sqlite3.Connection, raw: bytes, compress: bool) -> bytes:
    if not 0 < len(raw) <= _MAX_PAYLOAD_BYTES:
        raise PayloadProbeError("payload exceeds the diagnostic format limit")
    digest = hashlib.sha256(raw).digest()
    if connection.execute("SELECT 1 FROM probe_payloads WHERE digest = ?", (digest,)).fetchone() is None:
        packed = zlib.compress(raw, level=1) if compress else raw
        codec = int(len(packed) < len(raw))
        connection.execute(
            "INSERT INTO probe_payloads VALUES (?, ?, ?, ?)",
            (
                digest,
                codec,
                len(raw),
                packed if codec else raw,
            ),
        )
    return digest


def _load_payload(row: sqlite3.Row) -> bytes:
    digest, codec, raw_size, body = row["digest"], row["codec"], row["raw_size"], row["body"]
    if (
        not isinstance(digest, bytes)
        or len(digest) != 32
        or type(raw_size) is not int
        or not 0 < raw_size <= _MAX_PAYLOAD_BYTES
        or not isinstance(body, bytes)
        or not 0 < len(body) <= raw_size
    ):
        raise PayloadProbeError("invalid payload digest, size, or storage type")
    if codec == 0:
        raw = body
    elif codec == 1:
        try:
            decoder = zlib.decompressobj()
            raw = decoder.decompress(body, raw_size + 1)
        except zlib.error as exc:
            raise PayloadProbeError("invalid compressed payload") from exc
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise PayloadProbeError("invalid compressed payload extent")
    else:
        raise PayloadProbeError("unknown payload codec")
    if len(raw) != raw_size or hashlib.sha256(raw).digest() != digest:
        raise PayloadProbeError("payload digest or size mismatch")
    return raw


def _batch_wire(revision: int, data_revision: int, checksum: str, members: list[bytes]) -> str:
    prefix = f'{{"revision":{revision},"data_revision":{data_revision},"records":['.encode()
    suffix = f'],"checksum":"{checksum}"}}'.encode()
    if len(prefix) + len(suffix) + len(members) + sum(map(len, members)) > _MAX_BATCH_BYTES:
        raise PayloadProbeError("batch exceeds the diagnostic format limit")
    return (prefix + b",".join(members) + suffix).decode("utf-8")


def build_payload_probe(source: Path, destination: Path, *, compress: bool = False) -> dict[str, int | str]:
    """Produce a new standalone experiment database from a verified v7 fixture."""
    start = perf_counter_ns()
    with destination.open("xb"):
        pass
    with closing(_read_only(source)) as original, closing(sqlite3.connect(destination)) as packed:
        original.execute("BEGIN")
        _require_v7(original)
        packed.execute("PRAGMA foreign_keys=ON")
        packed.executescript(_SCHEMA)
        with packed:
            for revision, data_revision, checksum, wire, created in original.execute(_ORIGINAL_SQL["memory_batches"]):
                if len(wire.encode()) > _MAX_BATCH_BYTES:
                    raise PayloadProbeError("source batch exceeds the diagnostic format limit")
                batch = PersistedBatch.model_validate_json(wire)
                members = [record.model_dump_json().encode() for record in batch.records]
                if _batch_wire(revision, data_revision, checksum, members) != wire:
                    raise PayloadProbeError("original batch cannot be reconstructed byte for byte")
                packed.execute(
                    "INSERT INTO probe_batches VALUES (?, ?, ?, ?, ?)",
                    (
                        revision,
                        data_revision,
                        checksum,
                        created,
                        len(members),
                    ),
                )
                packed.executemany(
                    "INSERT INTO probe_members VALUES (?, ?, ?)",
                    ((revision, index, _put_payload(packed, raw, compress)) for index, raw in enumerate(members)),
                )
            for memory_id, wire, status, domain, kind, position in original.execute(
                _ORIGINAL_SQL["memory_current_records"]
            ):
                digest = _put_payload(packed, wire.encode(), compress)
                packed.execute(
                    "INSERT INTO probe_current VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        memory_id,
                        digest,
                        status,
                        domain,
                        kind,
                        position,
                    ),
                )
            for memory_id, revision, wire in original.execute(_ORIGINAL_SQL["memory_record_versions"]):
                packed.execute(
                    "INSERT INTO probe_versions VALUES (?, ?, ?)",
                    (
                        memory_id,
                        revision,
                        _put_payload(packed, wire.encode(), compress),
                    ),
                )
        unique_count, raw_bytes, stored_bytes, compressed_count = packed.execute(
            "SELECT count(*),coalesce(sum(raw_size),0),coalesce(sum(length(body)),0),coalesce(sum(codec),0) FROM probe_payloads",
        ).fetchone()
        original_pages = original.execute(
            "SELECT coalesce(sum(pgsize),0) FROM dbstat WHERE name IN (?, ?, ?)",
            _CATALOGS,
        ).fetchone()[0]
    return {
        "variant": "adaptive_zlib" if compress else "raw",
        "source_bytes": source.stat().st_size,
        "source_catalog_bytes": original_pages,
        "probe_bytes": destination.stat().st_size,
        "unique_payloads": unique_count,
        "unique_raw_bytes": raw_bytes,
        "stored_payload_bytes": stored_bytes,
        "compressed_payloads": compressed_count,
        "build_ns": perf_counter_ns() - start,
    }


def _reconstructed_batches(connection: sqlite3.Connection) -> Iterator[tuple[_Scalar, ...]]:
    for revision, data_revision, checksum, created, member_count in connection.execute(
        "SELECT revision,data_revision,checksum,created_utc,member_count FROM probe_batches ORDER BY revision",
    ):
        members = []
        total_size = 0
        for expected, row in enumerate(
            connection.execute(
                "SELECT ordinal,p.* FROM probe_members AS m JOIN probe_payloads AS p USING(digest) "
                "WHERE m.revision=? ORDER BY m.ordinal",
                (revision,),
            )
        ):
            if row["ordinal"] != expected:
                raise PayloadProbeError("unexpected batch member ordinal")
            raw = _load_payload(row)
            total_size += len(raw)
            if total_size > _MAX_BATCH_BYTES:
                raise PayloadProbeError("reconstructed batch exceeds diagnostic limit")
            members.append(raw)
        if len(members) != member_count:
            raise PayloadProbeError("batch member count mismatch")
        yield revision, data_revision, checksum, _batch_wire(revision, data_revision, checksum, members), created


def _reconstructed_rows(connection: sqlite3.Connection, catalog: str) -> Iterator[tuple[_Scalar, ...]]:
    if catalog == "memory_batches":
        yield from _reconstructed_batches(connection)
    elif catalog == "memory_current_records":
        for row in connection.execute(
            "SELECT c.memory_id,c.status,c.domain,c.source_kind,c.insertion_order,p.* FROM probe_current c "
            "JOIN probe_payloads p USING(digest) ORDER BY c.memory_id COLLATE BINARY",
        ):
            yield (
                row["memory_id"],
                _load_payload(row).decode(),
                row["status"],
                row["domain"],
                row["source_kind"],
                row["insertion_order"],
            )
    else:
        for row in connection.execute(
            "SELECT v.memory_id,v.revision,p.* FROM probe_versions v JOIN probe_payloads p USING(digest) "
            "ORDER BY v.memory_id COLLATE BINARY,v.revision",
        ):
            yield row["memory_id"], row["revision"], _load_payload(row).decode()


def _reconstructed_digest(row: tuple[_Scalar, ...]) -> bytes:
    # Independent from the production implementation used for the baseline.
    digest = hashlib.sha256(b"memorii.materialization-row.v2\x00")
    for value in row:
        if isinstance(value, str):
            encoded = value.encode()
            digest.update(b"s" + len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        elif isinstance(value, int):
            digest.update(b"i" + value.to_bytes(8, "big", signed=True))
        elif value is None:
            digest.update(b"n")
        else:
            raise PayloadProbeError("unexpected reconstructed value type")
    return digest.digest()


def verify_payload_probe_against(
    destination: Path,
    exact_manifest: RuntimeMaterializationManifest,
) -> dict[str, int | str]:
    """Rebuild all three original catalog roots and fail closed on drift."""
    start = perf_counter_ns()
    entries = []
    with closing(_read_only(destination)) as connection:
        connection.execute("BEGIN")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise PayloadProbeError("dangling payload or batch reference")
        if (
            connection.execute("""
            SELECT 1 FROM probe_payloads p WHERE
                NOT EXISTS(SELECT 1 FROM probe_members m WHERE m.digest=p.digest)
                AND NOT EXISTS(SELECT 1 FROM probe_current c WHERE c.digest=p.digest)
                AND NOT EXISTS(SELECT 1 FROM probe_versions v WHERE v.digest=p.digest)
            LIMIT 1
        """).fetchone()
            is not None
        ):
            raise PayloadProbeError("unexpected orphan payload")
        for catalog in _CATALOGS:
            key_length = _KEY_LENGTH[catalog]
            entries.append(
                _catalog(
                    catalog,
                    (
                        (_key_bytes(row[:key_length]), _reconstructed_digest(row))
                        for row in _reconstructed_rows(connection, catalog)
                    ),
                )
            )
    manifest = RuntimeMaterializationManifest(catalogs=tuple(entries))
    if manifest != exact_manifest:
        raise PayloadProbeError("reconstructed materializations differ from original catalog roots")
    return {"manifest_digest": manifest.digest(), "verify_ns": perf_counter_ns() - start}


def verify_payload_probe(source: Path, destination: Path) -> dict[str, int | str]:
    start = perf_counter_ns()
    manifest = read_legacy_payload_manifests(source)
    source_verify_ns = perf_counter_ns() - start
    return {**verify_payload_probe_against(destination, manifest), "source_verify_ns": source_verify_ns}
