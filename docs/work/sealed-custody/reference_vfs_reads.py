"""Read the two retained synthetic main images against independently measured roots."""

from __future__ import annotations

import argparse
import json
import sqlite3
from functools import partial
from pathlib import Path
from time import monotonic_ns

from memorii.stores.sqlite.raw_memory_payloads import payload_digest
from retained_vfs_probe import retained_reader


def choose_payload(connection: sqlite3.Connection) -> tuple[bytes, int]:
    return connection.execute(
        "SELECT payload_digest,rowid FROM memory_payloads NOT INDEXED "
        "WHERE rowid >= 10000 AND raw_size >= 262144 ORDER BY rowid LIMIT 1",
    ).fetchone()


def lookup(connection: sqlite3.Connection, digest: bytes, rowid: int) -> None:
    query = "SELECT rowid FROM memory_payloads INDEXED BY memory_payloads_digest WHERE payload_digest=?"
    plan = connection.execute("EXPLAIN QUERY PLAN " + query, (digest,)).fetchall()
    if not any("COVERING INDEX memory_payloads_digest" in row[3] for row in plan):
        raise RuntimeError("reference lookup did not use its covering index")
    if connection.execute(query, (digest,)).fetchone() != (rowid,):
        raise RuntimeError("reference lookup did not match its base row")


def authenticate_blob(connection: sqlite3.Connection, digest: bytes, rowid: int) -> int:
    with connection.blobopen("memory_payloads", "body", rowid, readonly=True) as body:
        raw = body.read()
    if payload_digest(raw) != digest:
        raise RuntimeError("reference BLOB no longer matches its logical digest")
    return len(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--extension", type=Path, required=True)
    args = parser.parse_args()
    for line in args.roots.read_text().splitlines():
        row = json.loads(line)
        distribution = row["distribution"]
        path, = (args.fixtures / distribution).glob("partition/generations/*/partition.sqlite3")
        start = monotonic_ns()
        with retained_reader(path, row["root"], args.extension) as reader:
            opened = monotonic_ns()
            digest, rowid = reader.release(choose_payload)
            initial = reader.stats()
            reader.release(partial(lookup, digest=digest, rowid=rowid))
            indexed = reader.stats()
            size = reader.release(partial(authenticate_blob, digest=digest, rowid=rowid))
            finished = reader.stats()
            if not initial.blocks < indexed.blocks < finished.blocks or finished.failed:
                raise RuntimeError("native verified read counters did not advance")
        print(json.dumps({
            "distribution": distribution, "root": row["root"], "sqlite_version": sqlite3.sqlite_version,
            "opening_ns": opened - start, "lookup_native_calls": indexed.calls - initial.calls,
            "blob_native_calls": finished.calls - indexed.calls,
            "lookup_blocks_verified": indexed.blocks - initial.blocks,
            "blob_blocks_verified": finished.blocks - indexed.blocks, "blob_bytes": size,
        }, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
