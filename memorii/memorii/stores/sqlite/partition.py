"""Shared SQLite application-data partition for durable memory stores.

One physical database per isolation partition. Domain-scoped stores compose
short transactions through this coordinator; the backend owns transaction
atomicity and storage layout only. Domain authority — preconditions, governed
write policies, visibility rules, revision semantics — stays with the
canonical domain owners.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memorii.core.memory_plane.file_lock import locked_file

PARTITION_SCHEMA_VERSION = 1
_DEFAULT_BUSY_TIMEOUT_MS = 5_000

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS partition_schema (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_batches (
        revision INTEGER PRIMARY KEY,
        data_revision INTEGER NOT NULL,
        checksum TEXT NOT NULL,
        batch_json TEXT NOT NULL,
        created_utc TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_record_versions (
        memory_id TEXT NOT NULL,
        batch_revision INTEGER NOT NULL REFERENCES memory_batches(revision),
        record_json TEXT NOT NULL,
        PRIMARY KEY (memory_id, batch_revision)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_current_records (
        memory_id TEXT PRIMARY KEY,
        record_json TEXT NOT NULL,
        status TEXT NOT NULL,
        domain TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        insertion_order INTEGER NOT NULL UNIQUE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS memory_current_records_status
        ON memory_current_records(status)
    """,
    """
    CREATE INDEX IF NOT EXISTS memory_current_records_domain
        ON memory_current_records(domain)
    """,
    """
    CREATE INDEX IF NOT EXISTS memory_current_records_source_kind
        ON memory_current_records(source_kind)
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_revision_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        write_revision INTEGER NOT NULL,
        data_revision INTEGER NOT NULL
    )
    """,
)


class PartitionDataRepository:
    """Coordinate one SQLite application-data partition (WAL, FULL synchronous)."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._database_path.parent / (self._database_path.name + ".lock")
        self._thread_lock = threading.RLock()
        self._connection = sqlite3.connect(
            self._database_path,
            timeout=busy_timeout_ms / 1000.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._configure(busy_timeout_ms)
        self._initialize_schema()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def close(self) -> None:
        with self._thread_lock, contextlib.suppress(sqlite3.ProgrammingError):
            self._connection.close()

    def __enter__(self) -> PartitionDataRepository:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()

    @contextmanager
    def transaction(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        """Hold one short partition transaction under the process-safe lock.

        Writers take the exclusive advisory lock plus ``BEGIN IMMEDIATE``;
        readers take a shared lock plus a deferred snapshot so a linearized
        read stays ordered with cross-process writers through release.
        """
        with self._thread_lock, locked_file(self._lock_path, exclusive=write):
            self._connection.execute("BEGIN IMMEDIATE" if write else "BEGIN DEFERRED")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    def read_revision_state(self, connection: sqlite3.Connection) -> tuple[int, int]:
        row = connection.execute(
            "SELECT write_revision, data_revision FROM memory_revision_state WHERE id = 1"
        ).fetchone()
        if row is None:
            raise sqlite3.DatabaseError("memory revision state is missing")
        return int(row["write_revision"]), int(row["data_revision"])

    def read_batch_rows(self, connection: sqlite3.Connection) -> Sequence[sqlite3.Row]:
        return connection.execute(
            "SELECT revision, data_revision, checksum, batch_json FROM memory_batches ORDER BY revision"
        ).fetchall()

    def read_current_record_rows(
        self,
        connection: sqlite3.Connection,
        *,
        status: str | None = None,
        domains: Sequence[str] | None = None,
        source_kind: str | None = None,
    ) -> Sequence[sqlite3.Row]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        if domains is not None:
            if not domains:
                return ()
            placeholders = ", ".join("?" for _ in domains)
            clauses.append(f"domain IN ({placeholders})")
            parameters.extend(sorted(domains))
        if source_kind is not None:
            clauses.append("source_kind = ?")
            parameters.append(source_kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return connection.execute(
            "SELECT memory_id, record_json FROM memory_current_records"
            f"{where} ORDER BY insertion_order",
            parameters,
        ).fetchall()

    def read_current_record_row(
        self,
        connection: sqlite3.Connection,
        memory_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT memory_id, record_json FROM memory_current_records WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()

    def append_memory_batch(
        self,
        connection: sqlite3.Connection,
        *,
        revision: int,
        data_revision: int,
        checksum: str,
        batch_json: str,
        records_json: Sequence[tuple[str, str, str, str, str]],
    ) -> None:
        """Append one immutable batch and its derived current-state rows.

        ``records_json`` carries ``(memory_id, record_json, status, domain,
        source_kind)`` tuples. Current rows keep their original
        first-insertion order; new identities take the next order value.
        """
        created_utc = datetime.now(UTC).isoformat()
        connection.execute(
            "INSERT INTO memory_batches (revision, data_revision, checksum, batch_json, created_utc)"
            " VALUES (?, ?, ?, ?, ?)",
            (revision, data_revision, checksum, batch_json, created_utc),
        )
        for memory_id, record_json, status, domain, source_kind in records_json:
            connection.execute(
                "INSERT INTO memory_record_versions (memory_id, batch_revision, record_json)"
                " VALUES (?, ?, ?)",
                (memory_id, revision, record_json),
            )
            connection.execute(
                "INSERT INTO memory_current_records"
                " (memory_id, record_json, status, domain, source_kind, insertion_order)"
                " VALUES (?, ?, ?, ?, ?,"
                " (SELECT COALESCE(MAX(insertion_order), 0) + 1 FROM memory_current_records))"
                " ON CONFLICT(memory_id) DO UPDATE SET"
                " record_json = excluded.record_json, status = excluded.status,"
                " domain = excluded.domain, source_kind = excluded.source_kind",
                (memory_id, record_json, status, domain, source_kind),
            )
        connection.execute(
            "UPDATE memory_revision_state SET write_revision = ?, data_revision = ? WHERE id = 1",
            (revision, data_revision),
        )

    def _configure(self, busy_timeout_ms: int) -> None:
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")

    def _initialize_schema(self) -> None:
        with self.transaction(write=True) as connection:
            catalog_row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'partition_schema'"
            ).fetchone()
            if catalog_row is not None:
                row = connection.execute(
                    "SELECT value FROM partition_schema WHERE key = 'schema_version'"
                ).fetchone()
                if row is not None:
                    version = int(row["value"])
                    if version != PARTITION_SCHEMA_VERSION:
                        raise sqlite3.DatabaseError(
                            f"unsupported partition schema version: {version}"
                        )
                    return
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO memory_revision_state (id, write_revision, data_revision)"
                " VALUES (1, 0, 0)"
            )
            connection.execute(
                "INSERT INTO partition_schema (key, value) VALUES ('schema_version', ?)",
                (str(PARTITION_SCHEMA_VERSION),),
            )
