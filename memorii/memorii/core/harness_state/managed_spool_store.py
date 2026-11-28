"""Private SQLite storage for signed managed host intake."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from memorii.core.harness_state.consumer import (
    MAX_MANAGED_INTAKE_BYTES,
    ConsumerDeliveryError,
    ManagedSpoolEntry,
    ManagedSpoolItem,
    operation_key,
    parse_managed_intake,
)
from memorii.core.persistence.runtime_contracts import OperationOrigin, OperationOriginCoordinate, RuntimeCommandReceipt
from memorii.stores.sqlite.private_storage import prepare_private_sqlite

MAX_PENDING_PER_INSTALLATION = 1000
MAX_PENDING_PER_TASK = 100

_SCHEMA = """
PRAGMA user_version = 1;
CREATE TABLE spool_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    store_id TEXT NOT NULL
) STRICT;
CREATE TABLE intake (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_key TEXT NOT NULL UNIQUE,
    installation_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    principal TEXT NOT NULL,
    client_namespace TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    task_id TEXT,
    command_kind TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'committed', 'held')),
    original_payload BLOB NOT NULL,
    payload_digest TEXT NOT NULL
) STRICT;
CREATE INDEX pending_order ON intake(sequence) WHERE state = 'pending';
CREATE INDEX pending_generation_order ON intake(installation_id, repository_id, generation_id, sequence)
    WHERE state = 'pending';
CREATE INDEX pending_scope ON intake(
    installation_id, repository_id, generation_id, principal, client_namespace, task_id, command_kind, sequence
) WHERE state = 'pending';
CREATE INDEX pending_task ON intake(installation_id, repository_id, generation_id, task_id) WHERE state = 'pending';
"""


@dataclass(frozen=True)
class ManagedSpoolSnapshot:
    """Pinned intake database and exact sequence cut for a consistent backup."""

    connection: sqlite3.Connection
    store_id: str
    high_water_mark: int


def _store_file(directory: Path, store_id: str) -> Path:
    try:
        if UUID(store_id).hex != store_id:
            raise ValueError("noncanonical UUID")
    except (ValueError, AttributeError) as exc:
        raise ConsumerDeliveryError("invalid_request: managed spool identity is invalid") from exc
    return directory / f"store-{store_id}.sqlite3"


def _intake_columns(entry: ManagedSpoolEntry) -> tuple[str | None, ...]:
    coordinate = entry.operation_origin.coordinate
    return (
        operation_key(coordinate), coordinate.installation_id, coordinate.repository_id,
        coordinate.generation_id, coordinate.principal, coordinate.client_namespace,
        coordinate.operation_id, entry.delivery.command.task_id, entry.delivery.command.kind,
    )


def _decode(row: sqlite3.Row, *, include_held: bool = False) -> ManagedSpoolEntry:
    payload: bytes = row["original_payload"]
    if len(payload) > MAX_MANAGED_INTAKE_BYTES or hashlib.sha256(payload).hexdigest() != row["payload_digest"]:
        raise ConsumerDeliveryError("integrity_error: managed spool payload digest changed")
    entry = parse_managed_intake(payload)
    if tuple(row[name] for name in (
        "operation_key", "installation_id", "repository_id", "generation_id", "principal",
        "client_namespace", "operation_id", "task_id", "command_kind",
    )) != _intake_columns(entry):
        raise ConsumerDeliveryError("integrity_error: managed spool index does not match signed intake")
    state = row["state"]
    if state == "held":
        if include_held and entry.state == "pending":
            return entry
        raise ConsumerDeliveryError("needs_reconciliation: managed intake is held")
    if state == "committed":
        return entry.model_copy(update={"state": "committed"})
    if state != "pending" or entry.state != "pending":
        raise ConsumerDeliveryError("integrity_error: managed spool state is invalid")
    return entry


def verify_managed_spool_snapshot(
    path: Path,
    *,
    store_id: str,
    high_water_mark: int,
    installation_id: str,
    repository_id: str,
    verify_origin: Callable[[OperationOrigin], bool],
) -> None:
    """Validate the immutable backup copy, outside the publication fence."""
    try:
        prepare_private_sqlite(path, require_existing=True)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = path.with_name(path.name + suffix)
            if sidecar.exists() or sidecar.is_symlink():
                raise ConsumerDeliveryError("integrity_error: managed spool snapshot has a live sidecar")
        uri = path.absolute().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            identity = connection.execute("SELECT store_id FROM spool_identity WHERE singleton = 1").fetchone()
            cut = connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM intake").fetchone()
            if (
                identity != (store_id,) or cut != (high_water_mark,)
                or connection.execute("PRAGMA user_version").fetchone() != (1,)
                or connection.execute("PRAGMA integrity_check").fetchone() != ("ok",)
            ):
                raise ConsumerDeliveryError("integrity_error: managed spool snapshot has the wrong identity or cut")
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM intake ORDER BY sequence")
            for expected, row in enumerate(rows, start=1):
                if row["sequence"] != expected:
                    raise ConsumerDeliveryError("integrity_error: managed spool snapshot sequence has a gap")
                entry = _decode(row, include_held=True)
                origin = entry.operation_origin
                if (
                    origin.coordinate.installation_id != installation_id
                    or origin.coordinate.repository_id != repository_id
                    or not verify_origin(origin)
                ):
                    raise ConsumerDeliveryError("integrity_error: managed spool snapshot has an unauthenticated origin")
    except (OSError, sqlite3.Error) as exc:
        raise ConsumerDeliveryError("unavailable: managed spool snapshot could not be verified") from exc


class SqliteManagedSpool:
    """Selected spool data. The installation owner supplies the signed identity."""

    def __init__(self, directory: Path, store_id: str) -> None:
        self.store_id = store_id
        self.path = _store_file(directory, store_id)
        try:
            with self._open() as connection:
                if connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] != "wal":
                    raise ConsumerDeliveryError("unavailable: managed spool WAL could not start")
        except (OSError, sqlite3.Error) as exc:
            raise ConsumerDeliveryError("unavailable: registered managed spool cannot be opened") from exc

    @contextmanager
    def _open(self) -> Iterator[sqlite3.Connection]:
        prepare_private_sqlite(self.path, require_existing=True)
        uri = self.path.absolute().as_uri() + "?mode=rw"
        with closing(sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)) as connection:
            identity = connection.execute("SELECT store_id FROM spool_identity WHERE singleton = 1").fetchone()
            if identity != (self.store_id,) or connection.execute("PRAGMA user_version").fetchone() != (1,):
                raise ConsumerDeliveryError("integrity_error: registered managed spool has the wrong identity or format")
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous = FULL")
            yield connection

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        try:
            with self._open() as connection:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield connection
                connection.commit()
        except (OSError, sqlite3.Error) as exc:
            raise ConsumerDeliveryError("unavailable: managed spool transaction failed") from exc

    @classmethod
    @contextmanager
    def pin_backlog(cls, directory: Path, *, store_id: str) -> Iterator[sqlite3.Connection]:
        """Pin a selected spool via an observational, read-only connection."""
        path = _store_file(directory, store_id)
        try:
            prepare_private_sqlite(path, require_existing=True)
            uri = path.absolute().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)) as connection:
                connection.execute("BEGIN")
                identity = connection.execute("SELECT store_id FROM spool_identity WHERE singleton = 1").fetchone()
                if identity != (store_id,) or connection.execute("PRAGMA user_version").fetchone() != (1,):
                    raise ConsumerDeliveryError("integrity_error: registered managed spool has the wrong identity or format")
                yield connection
        except (OSError, sqlite3.Error) as exc:
            raise ConsumerDeliveryError("unavailable: registered spool backlog cannot be read") from exc

    @staticmethod
    def backlog_counts(
        connection: sqlite3.Connection, *, installation_id: str, repository_id: str, generation_id: str,
    ) -> tuple[int, int]:
        return connection.execute(
            """
            SELECT COUNT(*) FILTER (WHERE state = 'pending' AND generation_id = ?),
                   COUNT(*) FILTER (WHERE state = 'held' OR (state = 'pending' AND generation_id != ?))
            FROM intake WHERE installation_id = ? AND repository_id = ? AND state != 'committed'
            """,
            (generation_id, generation_id, installation_id, repository_id),
        ).fetchone()

    @classmethod
    def stage(
        cls, directory: Path, store_id: str, entries: Callable[[], Iterator[tuple[ManagedSpoolEntry, bytes]]],
    ) -> Path:
        """Prepare and verify a complete unopened store under the owner's legacy lock."""
        destination = _store_file(directory, store_id)
        if destination.exists() or destination.is_symlink():
            return cls.verify_stage(directory, store_id, entries)
        try:
            with tempfile.TemporaryDirectory(prefix=".spool-stage-", dir=directory) as staging:
                staged = Path(staging) / destination.name
                prepare_private_sqlite(staged)
                with closing(sqlite3.connect(staged)) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.executescript(_SCHEMA)
                    connection.execute("INSERT INTO spool_identity VALUES (1, ?)", (store_id,))
                    for entry, payload in entries():
                        cls._require_capacity(connection, entry)
                        cls._insert(connection, entry, payload)
                    connection.commit()
                cls.verify_stage(Path(staging), store_id, entries)
                with staged.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(staged, destination)
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise ConsumerDeliveryError("unavailable: managed spool staging failed") from exc
        return destination

    @staticmethod
    def verify_stage(
        directory: Path, store_id: str, entries: Callable[[], Iterator[tuple[ManagedSpoolEntry, bytes]]],
    ) -> Path:
        path = _store_file(directory, store_id)
        try:
            prepare_private_sqlite(path, require_existing=True)
            uri = path.absolute().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                identity = connection.execute("SELECT store_id FROM spool_identity WHERE singleton = 1").fetchone()
                if (
                    identity != (store_id,) or connection.execute("PRAGMA user_version").fetchone() != (1,)
                    or connection.execute("PRAGMA integrity_check").fetchone() != ("ok",)
                ):
                    raise ConsumerDeliveryError("integrity_error: staged managed spool has the wrong identity or format")
                connection.row_factory = sqlite3.Row
                ordered = connection.execute("SELECT * FROM intake ORDER BY sequence")
                for row, (entry, payload) in zip(ordered, entries(), strict=True):
                    if bytes(row["original_payload"]) != payload or _decode(row) != entry:
                        raise ConsumerDeliveryError("conflict: legacy intake changed before managed spool selection")
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise ConsumerDeliveryError("unavailable: staged managed spool could not be verified") from exc
        return path

    @staticmethod
    def _insert(connection: sqlite3.Connection, entry: ManagedSpoolEntry, payload: bytes) -> None:
        connection.execute(
            """
            INSERT INTO intake (
                operation_key, installation_id, repository_id, generation_id, principal,
                client_namespace, operation_id, task_id, command_kind, state, original_payload, payload_digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*_intake_columns(entry), entry.state, payload, hashlib.sha256(payload).hexdigest()),
        )

    @staticmethod
    def _require_capacity(connection: sqlite3.Connection, entry: ManagedSpoolEntry) -> None:
        if entry.state != "pending":
            return
        origin = entry.operation_origin.coordinate
        generation = (origin.installation_id, origin.repository_id, origin.generation_id)
        count = connection.execute(
            "SELECT COUNT(*) FROM intake INDEXED BY pending_task WHERE state = 'pending' "
            "AND installation_id = ? AND repository_id = ? AND generation_id = ?",
            generation,
        ).fetchone()[0]
        if count >= MAX_PENDING_PER_INSTALLATION:
            raise ConsumerDeliveryError("resource_exhausted: installation pending managed intake limit")
        if entry.delivery.command.task_id is not None:
            count = connection.execute(
                "SELECT COUNT(*) FROM intake INDEXED BY pending_task WHERE state = 'pending' "
                "AND installation_id = ? AND repository_id = ? AND generation_id = ? AND task_id = ?",
                (*generation, entry.delivery.command.task_id),
            ).fetchone()[0]
            if count >= MAX_PENDING_PER_TASK:
                raise ConsumerDeliveryError("resource_exhausted: task pending managed intake limit")

    def admit(self, entry: ManagedSpoolEntry) -> ManagedSpoolEntry:
        payload = entry.model_dump_json().encode()
        if len(payload) > MAX_MANAGED_INTAKE_BYTES:
            raise ConsumerDeliveryError("resource_exhausted: managed intake payload exceeds limit")
        parse_managed_intake(payload)
        with self._transaction(write=True) as connection:
            coordinate = entry.operation_origin.coordinate
            existing = self._find(connection, coordinate)
            if existing is not None:
                if existing.operation_origin != entry.operation_origin or existing.delivery.command != entry.delivery.command:
                    raise ConsumerDeliveryError("conflict: divergent managed intake")
                return existing
            self._require_capacity(connection, entry)
            self._insert(connection, entry, payload)
        return entry

    @staticmethod
    def _find(connection: sqlite3.Connection, coordinate: OperationOriginCoordinate) -> ManagedSpoolEntry | None:
        row = connection.execute("SELECT * FROM intake WHERE operation_key = ?", (operation_key(coordinate),)).fetchone()
        return None if row is None else _decode(row)

    def find(self, coordinate: OperationOriginCoordinate) -> ManagedSpoolEntry | None:
        with self._transaction() as connection:
            return self._find(connection, coordinate)

    def mark_committed(self, entry: ManagedSpoolEntry, receipt: RuntimeCommandReceipt | None) -> None:
        origin = entry.operation_origin
        if (
            receipt is None or receipt.status != "committed" or receipt.operation_origin != origin.coordinate
            or receipt.origin_proof_digest != origin.proof_digest()
        ):
            raise ConsumerDeliveryError("denied: managed intake acknowledgement requires the exact committed receipt")
        with self._transaction(write=True) as connection:
            existing = self._find(connection, origin.coordinate)
            if existing == entry.model_copy(update={"state": "committed"}):
                return
            if existing != entry or entry.state != "pending":
                raise ConsumerDeliveryError("conflict: managed intake changed before acknowledgement")
            connection.execute(
                "UPDATE intake SET state = 'committed' WHERE operation_key = ?", (operation_key(origin.coordinate),),
            )

    def pending_page(
        self, *, after_sequence: int, limit: int, through_sequence: int = (1 << 63) - 1,
        generation: tuple[str, str, str] | None = None,
    ) -> tuple[ManagedSpoolItem, ...]:
        with self._transaction() as connection:
            if generation is None:
                rows = connection.execute(
                    "SELECT * FROM intake INDEXED BY pending_order WHERE state = 'pending' "
                    "AND sequence > ? AND sequence <= ? "
                    "ORDER BY sequence LIMIT ?",
                    (after_sequence, through_sequence, limit),
                )
            else:
                rows = connection.execute(
                    "SELECT * FROM intake INDEXED BY pending_generation_order WHERE state = 'pending' "
                    "AND installation_id = ? AND repository_id = ? AND generation_id = ? "
                    "AND sequence > ? AND sequence <= ? "
                    "ORDER BY sequence LIMIT ?",
                    (*generation, after_sequence, through_sequence, limit),
                )
            return tuple(ManagedSpoolItem(row["sequence"], _decode(row)) for row in rows)

    def pending_resumes(
        self, *, installation_id: str, repository_id: str, generation_id: str,
        principal: str, client_namespace: str, task_id: str,
    ) -> tuple[ManagedSpoolEntry, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM intake INDEXED BY pending_scope
                WHERE state = 'pending' AND installation_id = ? AND repository_id = ? AND generation_id = ?
                  AND principal = ? AND client_namespace = ? AND task_id = ? AND command_kind = 'resume_task'
                ORDER BY sequence LIMIT ?
                """,
                (installation_id, repository_id, generation_id, principal, client_namespace, task_id, MAX_PENDING_PER_TASK + 1),
            )
            entries = tuple(_decode(row) for row in rows)
        if len(entries) > MAX_PENDING_PER_TASK:
            raise ConsumerDeliveryError("integrity_error: managed spool exceeds task pending limit")
        return entries

    @contextmanager
    def pin_snapshot(self) -> Iterator[ManagedSpoolSnapshot]:
        with self._transaction() as connection:
            high_water = connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM intake").fetchone()[0]
            yield ManagedSpoolSnapshot(connection, self.store_id, high_water)

    def hold_prior_generation(self, *, installation_id: str, repository_id: str, generation_id: str) -> None:
        """Keep old pending evidence inert in an offline restored copy."""
        with self._transaction(write=True) as connection:
            connection.execute(
                "UPDATE intake SET state = 'held' WHERE state = 'pending' AND installation_id = ? "
                "AND repository_id = ? AND generation_id != ?",
                (installation_id, repository_id, generation_id),
            )
