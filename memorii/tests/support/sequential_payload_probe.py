"""Raw rowid payload verification over an isolated, v7-parity-checked projection."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from memorii.core.persistence.contracts import RuntimeMaterializationManifest
from memorii.stores.sqlite.materialization_sql import _key_bytes, _value_digest

from tests.support import payload_storage_probe as legacy

ReadMode = Literal["select", "blob"]
_CHUNK_BYTES = 256 * 1024
_CATALOGS = {
    "probe_batches": ("revision", "revision,data_revision,checksum,created_utc,member_count"),
    "probe_current": (
        "memory_id COLLATE BINARY",
        "memory_id,hex(digest),status,domain,source_kind,insertion_order,typeof(digest)",
    ),
    "probe_members": ("revision,ordinal", "revision,ordinal,hex(digest),typeof(digest)"),
    "probe_payloads": ("digest", "hex(digest),codec,raw_size,typeof(digest),typeof(body)"),
    "probe_versions": (
        "memory_id COLLATE BINARY,revision",
        "memory_id,revision,hex(digest),typeof(digest)",
    ),
}
_SCHEMA = legacy._SCHEMA.replace(") WITHOUT ROWID;", ");", 1)


def _reference_manifest(connection: sqlite3.Connection) -> RuntimeMaterializationManifest:
    entries = []
    for catalog, (order, columns) in _CATALOGS.items():
        key_length = len(order.split(","))
        rows = connection.execute(f"SELECT {columns} FROM {catalog} NOT INDEXED ORDER BY {order}")
        entries.append(
            legacy._catalog(catalog, ((_key_bytes(tuple(row)[:key_length]), _value_digest(row)) for row in rows))
        )
    return RuntimeMaterializationManifest(catalogs=tuple(entries))


def _require_payload_index(connection: sqlite3.Connection) -> None:
    query = "SELECT digest,rowid FROM probe_payloads {} ORDER BY digest"
    from_table = connection.execute(query.format("NOT INDEXED"))
    from_index = connection.execute(query.format("INDEXED BY sqlite_autoindex_probe_payloads_1"))
    # A damaged covering index may otherwise authenticate metadata for a different body.
    if tuple(from_table) != tuple(from_index):
        raise legacy.PayloadProbeError("payload digest index differs from the base table")


def build_sequential_projection(source: Path, destination: Path) -> RuntimeMaterializationManifest:
    """Copy the raw experiment to a rowid table with a separate digest index."""
    with destination.open("xb"):
        pass
    with closing(sqlite3.connect(destination, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("ATTACH DATABASE ? AS original", (source.resolve().as_uri() + "?mode=ro",))
        connection.executescript(_SCHEMA)
        with connection:
            for catalog in ("probe_payloads", "probe_batches", "probe_members", "probe_current", "probe_versions"):
                connection.execute(f"INSERT INTO main.{catalog} SELECT * FROM original.{catalog}")
            return _reference_manifest(connection)


def _require_reference_closure(connection: sqlite3.Connection) -> None:
    for catalog in ("probe_members", "probe_current", "probe_versions"):
        if connection.execute(f"""
            SELECT 1 FROM {catalog} AS source
            LEFT JOIN probe_payloads AS payload ON source.digest=payload.digest
            WHERE payload.digest IS NULL LIMIT 1
            """).fetchone() is not None:
            raise legacy.PayloadProbeError("dangling payload reference")
    if connection.execute("""
        SELECT 1 FROM probe_payloads p WHERE
            NOT EXISTS(SELECT 1 FROM probe_members m WHERE m.digest=p.digest)
            AND NOT EXISTS(SELECT 1 FROM probe_current c WHERE c.digest=p.digest)
            AND NOT EXISTS(SELECT 1 FROM probe_versions v WHERE v.digest=p.digest)
        LIMIT 1
        """).fetchone() is not None:
        raise legacy.PayloadProbeError("unexpected orphan payload")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise legacy.PayloadProbeError("dangling batch reference")


def _scan_with_blob_handles(connection: sqlite3.Connection) -> None:
    for rowid, expected, codec, raw_size, storage in connection.execute(
        "SELECT rowid,digest,codec,raw_size,typeof(body) FROM probe_payloads ORDER BY rowid"
    ):
        if (
            not isinstance(expected, bytes)
            or len(expected) != 32
            or codec != 0
            or type(raw_size) is not int
            or not 0 < raw_size <= legacy._MAX_PAYLOAD_BYTES
            or storage != "blob"
        ):
            raise legacy.PayloadProbeError("invalid raw payload metadata")
        with connection.blobopen("probe_payloads", "body", rowid, readonly=True) as blob:
            if len(blob) != raw_size:
                raise legacy.PayloadProbeError("invalid raw payload size")
            digest = hashlib.sha256()
            for chunk in iter(lambda: blob.read(_CHUNK_BYTES), b""):
                digest.update(chunk)
        if digest.digest() != expected:
            raise legacy.PayloadProbeError("payload digest mismatch")


def verify_sequential_projection(
    destination: Path,
    expected: RuntimeMaterializationManifest,
    *,
    read_mode: ReadMode = "select",
    mmap_bytes: int = 0,
) -> None:
    """Verify each raw body once and reconstruct the expected typed reference roots."""
    with closing(legacy._read_only(destination)) as connection:
        # mmap is measured only on frozen fixtures. Production use needs a separate fault review.
        connection.execute(f"PRAGMA mmap_size={int(mmap_bytes)}")
        connection.execute("BEGIN")
        if _reference_manifest(connection) != expected:
            raise legacy.PayloadProbeError("projected catalog commitments differ")
        _require_payload_index(connection)
        _require_reference_closure(connection)
        if read_mode == "select":
            for row in connection.execute("SELECT digest,codec,raw_size,body FROM probe_payloads ORDER BY rowid"):
                if row["codec"] != 0:
                    raise legacy.PayloadProbeError("unsupported codec in raw projection")
                legacy._load_payload(row)
        elif read_mode == "blob":
            _scan_with_blob_handles(connection)
        else:
            raise legacy.PayloadProbeError("unsupported sequential read mode")
