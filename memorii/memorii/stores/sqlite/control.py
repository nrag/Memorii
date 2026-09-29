"""Owner-only SQLite control database for installation authority.

Holds current control state, the trust registry, finalized publication
tuples, pending publication intents and the append-only signed control
journal. Record updates and journal entries commit atomically; an unknown
format, a broken journal chain or an invalid signature rejects startup.
This database is never part of a replaceable application-data generation.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import (
    RUNTIME_CONTROL_JOURNAL_SIGNATURE_PURPOSE,
    InstallationControlJournalEntry,
    InstallationControlState,
    RuntimePublicationIntent,
    RuntimePublicationState,
    TrustRegistryEntry,
    canonical_json_digest,
    empty_chain_commitment,
)

CONTROL_SCHEMA_VERSION = 1
JournalVerifier = Callable[[str, str, str, str], bool]

_ControlModel = TypeVar("_ControlModel", bound=BaseModel)

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS control_schema (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS installation_control (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        state_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trust_registry (
        key_id TEXT PRIMARY KEY,
        entry_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS publication_states (
        repository_id TEXT PRIMARY KEY,
        state_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS publication_intents (
        repository_id TEXT PRIMARY KEY,
        intent_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS control_journal (
        revision INTEGER PRIMARY KEY,
        entry_json TEXT NOT NULL
    )
    """,
)


class ControlStateError(RuntimeError):
    """Control records are inconsistent, unknown or fail validation."""


class ControlJournalChainError(RuntimeError):
    """The control journal chain or one of its signatures is invalid."""


class ControlDatabase:
    """Coordinate the independent installation-control authority."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        journal_verifier: JournalVerifier | None = None,
    ) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = path.parent / (path.name + ".lock")
        self._thread_lock = threading.RLock()
        self._journal_verifier = journal_verifier
        self._connection = sqlite3.connect(
            path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._initialize_schema()

    def close(self) -> None:
        with self._thread_lock, contextlib.suppress(sqlite3.ProgrammingError):
            self._connection.close()

    def __enter__(self) -> ControlDatabase:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()

    @contextmanager
    def transaction(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        with self._thread_lock, locked_file(self._lock_path, exclusive=write):
            self._connection.execute("BEGIN IMMEDIATE" if write else "BEGIN DEFERRED")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    # --- reading -------------------------------------------------------

    def read_control_state(self) -> InstallationControlState | None:
        with self.transaction(write=False) as connection:
            row = connection.execute(
                "SELECT state_json FROM installation_control WHERE id = 1"
            ).fetchone()
        return None if row is None else _decode(InstallationControlState, row["state_json"])

    def list_trust_entries(self) -> Sequence[TrustRegistryEntry]:
        with self.transaction(write=False) as connection:
            rows = connection.execute(
                "SELECT entry_json FROM trust_registry ORDER BY key_id"
            ).fetchall()
        return [_decode(TrustRegistryEntry, row["entry_json"]) for row in rows]

    def read_publication_state(
        self, repository_id: str
    ) -> RuntimePublicationState | None:
        with self.transaction(write=False) as connection:
            row = connection.execute(
                "SELECT state_json FROM publication_states WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        return None if row is None else _decode(RuntimePublicationState, row["state_json"])

    def read_pending_intent(self, repository_id: str) -> RuntimePublicationIntent | None:
        with self.transaction(write=False) as connection:
            row = connection.execute(
                "SELECT intent_json FROM publication_intents WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        if row is None:
            return None
        intent = _decode(RuntimePublicationIntent, row["intent_json"])
        return intent if intent.phase == "prepared" else None

    def read_journal(self) -> Sequence[InstallationControlJournalEntry]:
        with self.transaction(write=False) as connection:
            rows = connection.execute(
                "SELECT entry_json FROM control_journal ORDER BY revision"
            ).fetchall()
        return [_decode(InstallationControlJournalEntry, row["entry_json"]) for row in rows]

    def validate_journal(self) -> None:
        """Fail closed on a broken chain, unknown records or bad signatures."""
        entries = self.read_journal()
        prior_digest = empty_chain_commitment()
        for expected_revision, entry in enumerate(entries, start=1):
            if entry.revision != expected_revision:
                raise ControlJournalChainError(
                    f"control journal revision gap: expected {expected_revision},"
                    f" got {entry.revision}"
                )
            if entry.prior_digest != prior_digest:
                raise ControlJournalChainError(
                    f"control journal chain break at revision {entry.revision}"
                )
            if entry.entry_digest != _entry_digest(entry):
                raise ControlJournalChainError(
                    f"control journal entry digest mismatch at revision {entry.revision}"
                )
            if self._journal_verifier is not None and not self._journal_verifier(
                entry.signer_key_id,
                RUNTIME_CONTROL_JOURNAL_SIGNATURE_PURPOSE,
                entry.entry_digest,
                entry.signature,
            ):
                raise ControlJournalChainError(
                    f"control journal signature is invalid at revision {entry.revision}"
                )
            prior_digest = entry.entry_digest

    # --- writing -------------------------------------------------------

    def next_journal_position(self) -> tuple[int, str]:
        """Return the next journal revision and the current chain digest."""
        with self.transaction(write=False) as connection:
            row = connection.execute(
                "SELECT entry_json FROM control_journal ORDER BY revision DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return 1, empty_chain_commitment()
        latest = _decode(InstallationControlJournalEntry, row["entry_json"])
        return latest.revision + 1, latest.entry_digest

    def initialize_installation(
        self,
        state: InstallationControlState,
        trust_entry: TrustRegistryEntry,
        intent: RuntimePublicationIntent,
        journal_entry: InstallationControlJournalEntry,
    ) -> None:
        """Create registry, state and prepared intent in one control transaction."""
        with self.transaction(write=True) as connection:
            if _read_control_state_unlocked(connection) is not None:
                raise ControlStateError("installation control state already exists")
            _append_journal_unlocked(connection, journal_entry)
            connection.execute(
                "INSERT INTO trust_registry (key_id, entry_json) VALUES (?, ?)",
                (trust_entry.key_id, trust_entry.model_dump_json()),
            )
            connection.execute(
                "INSERT INTO installation_control (id, state_json) VALUES (1, ?)",
                (state.model_dump_json(),),
            )
            connection.execute(
                "INSERT INTO publication_intents (repository_id, intent_json) VALUES (?, ?)",
                (intent.repository_id, intent.model_dump_json()),
            )

    def install_trust_entry(self, entry: TrustRegistryEntry) -> None:
        with self.transaction(write=True) as connection:
            connection.execute(
                "INSERT INTO trust_registry (key_id, entry_json) VALUES (?, ?)"
                " ON CONFLICT(key_id) DO UPDATE SET entry_json = excluded.entry_json",
                (entry.key_id, entry.model_dump_json()),
            )

    def write_control_state(
        self,
        next_state: InstallationControlState,
        journal_entry: InstallationControlJournalEntry,
    ) -> None:
        with self.transaction(write=True) as connection:
            current = _read_control_state_unlocked(connection)
            if current is not None and next_state.control_revision != current.control_revision + 1:
                raise ControlStateError(
                    "control revision must increase by exactly one: "
                    f"current {current.control_revision}, proposed {next_state.control_revision}"
                )
            if current is not None and next_state.installation_id != current.installation_id:
                raise ControlStateError("installation identity cannot change")
            _append_journal_unlocked(connection, journal_entry)
            connection.execute(
                "INSERT INTO installation_control (id, state_json) VALUES (1, ?)"
                " ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json",
                (next_state.model_dump_json(),),
            )

    def write_publication_state(
        self,
        repository_id: str,
        state: RuntimePublicationState,
        journal_entry: InstallationControlJournalEntry,
    ) -> None:
        with self.transaction(write=True) as connection:
            _append_journal_unlocked(connection, journal_entry)
            connection.execute(
                "INSERT INTO publication_states (repository_id, state_json) VALUES (?, ?)"
                " ON CONFLICT(repository_id) DO UPDATE SET state_json = excluded.state_json",
                (repository_id, state.model_dump_json()),
            )

    def write_intent(
        self,
        intent: RuntimePublicationIntent,
        journal_entry: InstallationControlJournalEntry,
    ) -> None:
        with self.transaction(write=True) as connection:
            existing = connection.execute(
                "SELECT intent_json FROM publication_intents WHERE repository_id = ?",
                (intent.repository_id,),
            ).fetchone()
            if existing is not None:
                existing_intent = _decode(RuntimePublicationIntent, existing["intent_json"])
                if (
                    existing_intent.phase == "prepared"
                    and intent.phase == "prepared"
                    and existing_intent.intent_id != intent.intent_id
                ):
                    raise ControlStateError(
                        "a prepared publication intent already exists for this repository"
                    )
            _append_journal_unlocked(connection, journal_entry)
            connection.execute(
                "INSERT INTO publication_intents (repository_id, intent_json) VALUES (?, ?)"
                " ON CONFLICT(repository_id) DO UPDATE SET intent_json = excluded.intent_json",
                (intent.repository_id, intent.model_dump_json()),
            )

    def _initialize_schema(self) -> None:
        with self.transaction(write=True) as connection:
            catalog_row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'control_schema'"
            ).fetchone()
            if catalog_row is not None:
                row = connection.execute(
                    "SELECT value FROM control_schema WHERE key = 'schema_version'"
                ).fetchone()
                if row is not None and int(row["value"]) != CONTROL_SCHEMA_VERSION:
                    raise ControlStateError(
                        f"unsupported control schema version: {row['value']}"
                    )
                return
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO control_schema (key, value) VALUES ('schema_version', ?)",
                (str(CONTROL_SCHEMA_VERSION),),
            )


def _read_control_state_unlocked(
    connection: sqlite3.Connection,
) -> InstallationControlState | None:
    row = connection.execute(
        "SELECT state_json FROM installation_control WHERE id = 1"
    ).fetchone()
    return None if row is None else _decode(InstallationControlState, row["state_json"])


def _append_journal_unlocked(
    connection: sqlite3.Connection,
    entry: InstallationControlJournalEntry,
) -> None:
    row = connection.execute(
        "SELECT entry_json FROM control_journal ORDER BY revision DESC LIMIT 1"
    ).fetchone()
    expected_revision = 1
    prior_digest = empty_chain_commitment()
    if row is not None:
        latest = _decode(InstallationControlJournalEntry, row["entry_json"])
        expected_revision = latest.revision + 1
        prior_digest = latest.entry_digest
    if entry.revision != expected_revision or entry.prior_digest != prior_digest:
        raise ControlJournalChainError(
            "journal entry does not extend the chain: "
            f"expected revision {expected_revision}, got {entry.revision}"
        )
    if entry.entry_digest != _entry_digest(entry):
        raise ControlJournalChainError("journal entry digest does not match its payload")
    connection.execute(
        "INSERT INTO control_journal (revision, entry_json) VALUES (?, ?)",
        (entry.revision, entry.model_dump_json()),
    )


def _entry_digest(entry: InstallationControlJournalEntry) -> str:
    return canonical_json_digest(entry.unsigned_payload())


def _decode(model_cls: type[_ControlModel], payload: str) -> _ControlModel:
    try:
        return model_cls.model_validate_json(payload)
    except ValidationError as exc:
        raise ControlStateError(f"control record fails closed validation: {exc}") from exc


__all__ = [
    "CONTROL_SCHEMA_VERSION",
    "ControlDatabase",
    "ControlJournalChainError",
    "ControlStateError",
    "JournalVerifier",
]
