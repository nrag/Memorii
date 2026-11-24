"""Shared SQLite application-data partition for durable memory stores.

One physical database per isolation partition. Domain-scoped stores compose
short transactions through this coordinator; the backend owns transaction
atomicity and storage layout only. Domain authority — preconditions, governed
write policies, visibility rules, revision semantics — stays with the
canonical domain owners.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    # Imported lazily at runtime: the storage layer must not trigger the
    # eager memorii.core package initializer at import time (it pulls the
    # memory plane, which imports this module back).
    from memorii.core.memory_evolution.semantic_index import SemanticIndexProjection
    from memorii.core.persistence.contracts import MaterializationCatalogEntry
    from memorii.core.semantic_ingestion.ontology_index import OntologyIndexProjection

PARTITION_SCHEMA_VERSION = 5
_INITIAL_PARTITION_SCHEMA_VERSION = 1
_CONSOLIDATION_SCHEMA_VERSION = 2
_DELIVERY_SCHEMA_VERSION = 3
_RUNTIME_HISTORY_SCHEMA_VERSION = 4
_RUNTIME_SOURCE_RELEASE_SCHEMA_VERSION = 5
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
    """
    CREATE TABLE IF NOT EXISTS partition_publication (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        ordinal INTEGER NOT NULL,
        position_kind TEXT NOT NULL,
        position_sequence INTEGER,
        position_digest TEXT NOT NULL,
        tuple_digest TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        vector_json TEXT NOT NULL,
        manifest_digest TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS semantic_entities (
        logical_entity_id TEXT NOT NULL,
        entity_revision_id TEXT NOT NULL,
        lifecycle TEXT NOT NULL,
        record_id TEXT NOT NULL,
        record_digest TEXT NOT NULL,
        codec_fingerprint TEXT NOT NULL,
        PRIMARY KEY (logical_entity_id, entity_revision_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS semantic_claims (
        claim_assertion_id TEXT PRIMARY KEY,
        subject_entity_id TEXT NOT NULL,
        object_entity_id TEXT,
        predicate_id TEXT,
        record_id TEXT NOT NULL,
        record_digest TEXT NOT NULL,
        valid_from TEXT,
        valid_to TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS semantic_evidence_links (
        claim_assertion_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_digest TEXT NOT NULL,
        evidence_digest TEXT NOT NULL,
        PRIMARY KEY (claim_assertion_id, source_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS semantic_index_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        graph_revision TEXT NOT NULL,
        snapshot_digest TEXT NOT NULL,
        write_revision INTEGER NOT NULL,
        data_revision INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ontology_candidates (
        proposal_id TEXT PRIMARY KEY,
        lifecycle TEXT NOT NULL,
        record_digest TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ontology_versions (
        version_digest TEXT PRIMARY KEY,
        record_id TEXT NOT NULL,
        record_digest TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ontology_selections (
        scope_key TEXT PRIMARY KEY,
        selected_version_digest TEXT NOT NULL,
        selected_attempt_id TEXT NOT NULL,
        activation_sequence INTEGER NOT NULL,
        record_digest TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ontology_activation_attempts (
        attempt_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        record_digest TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ontology_replay_receipts (
        operation_id TEXT PRIMARY KEY,
        record_digest TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_revision_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        runtime_revision INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_tasks (
        task_id TEXT PRIMARY KEY,
        record_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_execution_nodes (
        task_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY (task_id, node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_execution_edges (
        task_id TEXT NOT NULL,
        edge_id TEXT NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY (task_id, edge_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_solver_runs (
        solver_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        record_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_solver_nodes (
        solver_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY (solver_id, node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_solver_edges (
        solver_id TEXT NOT NULL,
        edge_id TEXT NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY (solver_id, edge_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_overlay_versions (
        version_id TEXT PRIMARY KEY,
        solver_id TEXT NOT NULL,
        record_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_justifications (
        justification_id TEXT PRIMARY KEY,
        solver_id TEXT NOT NULL,
        record_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_action_attempts (
        action_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        recommendation_id TEXT NOT NULL,
        recommendation_revision INTEGER NOT NULL,
        record_json TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS runtime_action_attempts_reservation
        ON runtime_action_attempts (task_id, recommendation_id, recommendation_revision)
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_command_receipts (
        client_namespace TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY (client_namespace, operation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_operation_attempts (
        receipt_id TEXT NOT NULL,
        attempt_ordinal INTEGER NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY (receipt_id, attempt_ordinal)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_outbox_deliveries (
        delivery_id TEXT PRIMARY KEY,
        record_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        record_json TEXT NOT NULL
    )
    """,
)

_CONSOLIDATION_SCHEMA_STATEMENT = """
    CREATE TABLE consolidation_results (
        result_id TEXT PRIMARY KEY NOT NULL,
        record_json TEXT NOT NULL
    )
"""

_DELIVERY_CATALOGS = (
    ("writeback_decisions", "decision_id", "record_json"),
    ("runtime_work_projections", "delivery_id", "record_json"),
    ("runtime_target_receipts", "delivery_id", "record_json"),
)
_SKILL_CANDIDATE_CATALOG = ("runtime_skill_candidates", "candidate_id", "record_json")
_RUNTIME_SOURCE_RELEASE_CATALOG = ("runtime_source_release_grants", "grant_id", "record_json")
_CURRENT_DELIVERY_CATALOGS = (*_DELIVERY_CATALOGS, _SKILL_CANDIDATE_CATALOG)
DeliveryCatalog = Literal[
    "writeback_decisions", "runtime_work_projections", "runtime_target_receipts", "runtime_skill_candidates",
]

# Authoritative materialized catalogs covered by the signed manifest. The
# fold is canonical: per-row digest over (primary key, payload), chained in
# the catalog's primary-key order from a domain-separated per-catalog seed.
# The revision-state, publication and semantic-index-state rows are derived
# or self-referential and are excluded from the row root; the derived
# semantic tables ARE authoritative materialized state (rebuildable from
# canonical records, never independent facts) and are covered.
_INITIAL_MATERIALIZATION_CATALOGS = (
    ("memory_batches", "revision", "batch_json"),
    ("memory_record_versions", "memory_id || ':' || batch_revision", "record_json"),
    ("memory_current_records", "memory_id", "record_json"),
    (
        "semantic_entities",
        "logical_entity_id || ':' || entity_revision_id",
        "lifecycle || ':' || record_id || ':' || record_digest || ':' || codec_fingerprint",
    ),
    (
        "semantic_claims",
        "claim_assertion_id",
        "subject_entity_id || ':' || COALESCE(object_entity_id, '') || ':'"
        " || COALESCE(predicate_id, '') || ':' || record_id || ':' || record_digest"
        " || ':' || COALESCE(valid_from, '') || ':' || COALESCE(valid_to, '')",
    ),
    (
        "semantic_evidence_links",
        "claim_assertion_id || ':' || source_id",
        "source_digest || ':' || evidence_digest",
    ),
    ("ontology_candidates", "proposal_id", "lifecycle || ':' || record_digest"),
    ("ontology_versions", "version_digest", "record_id || ':' || record_digest"),
    (
        "ontology_selections",
        "scope_key",
        "selected_version_digest || ':' || selected_attempt_id || ':'"
        " || activation_sequence || ':' || record_digest",
    ),
    ("ontology_activation_attempts", "attempt_id", "status || ':' || record_digest"),
    ("ontology_replay_receipts", "operation_id", "record_digest"),
    ("runtime_tasks", "task_id", "record_json"),
    (
        "runtime_execution_nodes",
        "task_id || ':' || node_id",
        "record_json",
    ),
    ("runtime_execution_edges", "task_id || ':' || edge_id", "record_json"),
    ("runtime_solver_runs", "solver_id", "record_json"),
    ("runtime_solver_nodes", "solver_id || ':' || node_id", "record_json"),
    ("runtime_solver_edges", "solver_id || ':' || edge_id", "record_json"),
    ("runtime_overlay_versions", "version_id", "record_json"),
    ("runtime_justifications", "justification_id", "record_json"),
    ("runtime_action_attempts", "action_id", "record_json"),
    (
        "runtime_command_receipts",
        "client_namespace || ':' || operation_id",
        "record_json",
    ),
    (
        "runtime_operation_attempts",
        "receipt_id || ':' || attempt_ordinal",
        "record_json",
    ),
    ("runtime_outbox_deliveries", "delivery_id", "record_json"),
    ("runtime_checkpoints", "checkpoint_id", "record_json"),
)
_CONSOLIDATION_CATALOG = ("consolidation_results", "result_id", "record_json")
_RUNTIME_EVENT_INDEX_CATALOGS = (
    ("runtime_event_id_bindings", "event_id", "binding_json"),
    ("runtime_dedupe_bindings", "dedupe_key", "binding_json"),
    ("runtime_record_version_bindings", "record_version_id", "binding_json"),
)
_RUNTIME_HISTORY_TABLES = (
    "runtime_event_batches", _SKILL_CANDIDATE_CATALOG[0],
    *(catalog for catalog, _, _ in _RUNTIME_EVENT_INDEX_CATALOGS),
)
_MATERIALIZATION_CATALOGS_BY_VERSION = {
    _INITIAL_PARTITION_SCHEMA_VERSION: _INITIAL_MATERIALIZATION_CATALOGS,
    _CONSOLIDATION_SCHEMA_VERSION: (*_INITIAL_MATERIALIZATION_CATALOGS, _CONSOLIDATION_CATALOG),
    _DELIVERY_SCHEMA_VERSION: (
        *_INITIAL_MATERIALIZATION_CATALOGS, _CONSOLIDATION_CATALOG, *_DELIVERY_CATALOGS,
    ),
    _RUNTIME_HISTORY_SCHEMA_VERSION: (
        *_INITIAL_MATERIALIZATION_CATALOGS, _CONSOLIDATION_CATALOG, *_DELIVERY_CATALOGS,
        _SKILL_CANDIDATE_CATALOG, *_RUNTIME_EVENT_INDEX_CATALOGS,
    ),
    _RUNTIME_SOURCE_RELEASE_SCHEMA_VERSION: (
        *_INITIAL_MATERIALIZATION_CATALOGS, _CONSOLIDATION_CATALOG, *_DELIVERY_CATALOGS,
        _SKILL_CANDIDATE_CATALOG, *_RUNTIME_EVENT_INDEX_CATALOGS, _RUNTIME_SOURCE_RELEASE_CATALOG,
    ),
}
_CATALOG_SEED_DOMAIN = b"memorii.materialization-catalog.v1\x00"


def _placeholders(values: Sequence[str]) -> str:
    return ", ".join("?" for _ in values)


_RUNTIME_UPSERT_TABLES = frozenset(
    {
        "runtime_tasks",
        "runtime_execution_nodes",
        "runtime_execution_edges",
        "runtime_solver_runs",
        "runtime_solver_nodes",
        "runtime_solver_edges",
        "runtime_overlay_versions",
        "runtime_justifications",
        "runtime_action_attempts",
        "runtime_command_receipts",
        "runtime_operation_attempts",
        "runtime_outbox_deliveries",
        "runtime_checkpoints",
    }
)

# Physical materialization identity. The replay check compares the stored
# filtering coordinates as well as the exact owner-encoded record bytes.
_RUNTIME_ROW_LAYOUTS = {
    "runtime_tasks": (("task_id",), ()),
    "runtime_execution_nodes": (("task_id", "node_id"), ()),
    "runtime_execution_edges": (("task_id", "edge_id"), ()),
    "runtime_solver_runs": (("solver_id",), ("task_id",)),
    "runtime_solver_nodes": (("solver_id", "node_id"), ()),
    "runtime_solver_edges": (("solver_id", "edge_id"), ()),
    "runtime_overlay_versions": (("version_id",), ("solver_id",)),
    "runtime_justifications": (("justification_id",), ("solver_id",)),
    "runtime_action_attempts": (
        ("action_id",), ("task_id", "recommendation_id", "recommendation_revision"),
    ),
    "runtime_command_receipts": (("client_namespace", "operation_id"), ()),
    "runtime_operation_attempts": (("receipt_id", "attempt_ordinal"), ()),
    "runtime_outbox_deliveries": (("delivery_id",), ()),
    "runtime_checkpoints": (("checkpoint_id",), ("task_id",)),
    "consolidation_results": (("result_id",), ()),
    **{table: ((key,), ()) for table, key, _ in _CURRENT_DELIVERY_CATALOGS},
}


@dataclass(frozen=True)
class RuntimeMaterializedRow:
    catalog: str
    key: tuple[str | int, ...]
    indexed: tuple[str | int, ...]
    record_json: str


@dataclass(frozen=True)
class RuntimeRowChange:
    row: RuntimeMaterializedRow
    operation: Literal["create", "update"]
    prior_record_json: str | None


class PartitionWriteTransaction:
    """One manual-commit partition transaction owned by its coordinator."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.finished = False

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def commit(self) -> None:
        if self.finished:
            raise sqlite3.ProgrammingError("partition transaction is already finished")
        self._connection.execute("COMMIT")
        self.finished = True

    def _rollback(self) -> None:
        if not self.finished:
            with contextlib.suppress(sqlite3.Error):
                self._connection.execute("ROLLBACK")
            self.finished = True


class PartitionDataRepository:
    """Coordinate one SQLite application-data partition (WAL, FULL synchronous)."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
        require_existing: bool = False,
        transaction_guard: Callable[[sqlite3.Connection], None] | None = None,
        protected_storage_root: Path | None = None,
    ) -> None:
        self._database_path = Path(database_path)
        if not require_existing:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._database_path.parent / (self._database_path.name + ".lock")
        self._protected_storage_root = protected_storage_root or self._database_path.parent
        self._thread_lock = threading.RLock()
        self._transaction_guard: Callable[[sqlite3.Connection], None] | None = None
        self._connection = sqlite3.connect(
            self._database_path.absolute().as_uri() + "?mode=rw" if require_existing else self._database_path,
            timeout=busy_timeout_ms / 1000.0,
            isolation_level=None,
            check_same_thread=False,
            uri=require_existing,
        )
        self._connection.row_factory = sqlite3.Row
        if require_existing:
            self.read_schema_version(self._connection)
        self._configure(busy_timeout_ms)
        if not require_existing:
            self._initialize_schema()
        self._transaction_guard = transaction_guard

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def protected_storage_root(self) -> Path:
        """The owner-private key root can outlive replaceable data generations."""
        return self._protected_storage_root

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
        from memorii.core.memory_plane.file_lock import locked_file

        with self._thread_lock, locked_file(self._lock_path, exclusive=write):
            if self._transaction_guard is not None:
                self._transaction_guard(self._connection)
            self._connection.execute("BEGIN IMMEDIATE" if write else "BEGIN DEFERRED")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    @contextmanager
    def manual_write_transaction(self) -> Iterator[PartitionWriteTransaction]:
        """Open a partition write transaction whose commit the caller owns.

        The publication coordinator applies data rows, computes and signs the
        candidate tuple from the transaction's own view, persists the control
        intent, and only then commits — so recovery always sees either the
        exact old or the exact new data state, never a mixture. Exiting the
        context without an explicit commit rolls back.
        """
        from memorii.core.memory_plane.file_lock import locked_file

        with self._thread_lock, locked_file(self._lock_path, exclusive=True):
            if self._transaction_guard is not None:
                self._transaction_guard(self._connection)
            self._connection.execute("BEGIN IMMEDIATE")
            handle = PartitionWriteTransaction(self._connection)
            try:
                yield handle
            except BaseException:
                handle._rollback()
                raise
            if not handle.finished:
                handle._rollback()

    def compute_materialization_manifest(
        self, connection: sqlite3.Connection
    ) -> tuple[MaterializationCatalogEntry, ...]:
        from memorii.core.persistence.contracts import MaterializationCatalogEntry

        version = self.read_schema_version(connection)
        catalogs = _MATERIALIZATION_CATALOGS_BY_VERSION[version]
        if version == _INITIAL_PARTITION_SCHEMA_VERSION and self._has_consolidation_catalog(connection):
            raise sqlite3.DatabaseError("consolidation catalog is outside the declared partition schema")
        if version < _DELIVERY_SCHEMA_VERSION and any(
            self._has_catalog(connection, name) for name, _, _ in _DELIVERY_CATALOGS
        ):
            raise sqlite3.DatabaseError("delivery catalog is outside the declared partition schema")
        if version < _RUNTIME_HISTORY_SCHEMA_VERSION and any(
            self._has_catalog(connection, name) for name in _RUNTIME_HISTORY_TABLES
        ):
            raise sqlite3.DatabaseError("runtime history catalog is outside the declared partition schema")
        if version < _RUNTIME_SOURCE_RELEASE_SCHEMA_VERSION and self._has_catalog(
            connection, _RUNTIME_SOURCE_RELEASE_CATALOG[0],
        ):
            raise sqlite3.DatabaseError("runtime source release catalog is outside the declared partition schema")
        entries: list[MaterializationCatalogEntry] = []
        for catalog, key_expression, payload_column in catalogs:
            rows = connection.execute(
                f"SELECT {key_expression} AS sort_key, {payload_column} AS payload"
                f" FROM {catalog} ORDER BY {key_expression}"
            )
            chain = hashlib.sha256(_CATALOG_SEED_DOMAIN + catalog.encode("ascii")).digest()
            count = 0
            for row in rows:
                row_digest = hashlib.sha256(
                    str(row["sort_key"]).encode("utf-8")
                    + b"\x00"
                    + row["payload"].encode("utf-8")
                ).digest()
                chain = hashlib.sha256(chain + b"\x00" + row_digest).digest()
                count += 1
            entries.append(
                MaterializationCatalogEntry(
                    catalog=catalog,
                    row_count=count,
                    digest=chain.hex(),
                )
            )
        # Closed rule: the manifest covers exactly the declared catalogs —
        # one entry per name, no silent subset.
        if {entry.catalog for entry in entries} != {
            catalog for catalog, _, _ in catalogs
        }:
            raise sqlite3.DatabaseError(
                "materialization manifest does not cover the declared catalogs"
            )
        return tuple(sorted(entries, key=lambda entry: entry.catalog))

    @staticmethod
    def read_schema_version(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM partition_schema WHERE key = 'schema_version'"
        ).fetchone()
        if row is None or row[0] not in {str(version) for version in _MATERIALIZATION_CATALOGS_BY_VERSION}:
            raise sqlite3.DatabaseError("unsupported or missing partition schema version")
        return int(row[0])

    @staticmethod
    def requires_managed_restore(connection: sqlite3.Connection) -> bool:
        """Check for any generation that can issue managed operation proofs."""
        version = PartitionDataRepository.read_schema_version(connection)
        # Even a managed backup with no receipts can predate a signed intent
        # accepted later in this same generation.
        return version >= _CONSOLIDATION_SCHEMA_VERSION or connection.execute(
            "SELECT 1 FROM runtime_command_receipts "
            "WHERE json_type(record_json, '$.operation_origin') = 'object' LIMIT 1",
        ).fetchone() is not None

    @staticmethod
    def supports_managed_runtime(connection: sqlite3.Connection) -> bool:
        return PartitionDataRepository.read_schema_version(connection) >= _CONSOLIDATION_SCHEMA_VERSION

    @staticmethod
    def supports_runtime_history(connection: sqlite3.Connection) -> bool:
        return PartitionDataRepository.read_schema_version(connection) >= _RUNTIME_HISTORY_SCHEMA_VERSION

    @staticmethod
    def supports_runtime_source_release(connection: sqlite3.Connection) -> bool:
        return PartitionDataRepository.read_schema_version(connection) >= _RUNTIME_SOURCE_RELEASE_SCHEMA_VERSION

    @staticmethod
    def _runtime_row_layouts(connection: sqlite3.Connection) -> Iterator[tuple[str, tuple[tuple[str, ...], tuple[str, ...]]]]:
        yield from _RUNTIME_ROW_LAYOUTS.items()
        if PartitionDataRepository.supports_runtime_source_release(connection):
            yield _RUNTIME_SOURCE_RELEASE_CATALOG[0], ((_RUNTIME_SOURCE_RELEASE_CATALOG[1],), ())

    @staticmethod
    def verification_cookie(connection: sqlite3.Connection) -> tuple[int, int]:
        # SQLite's data_version advances for other connections. The local
        # change count invalidates a cached acquisition for this connection.
        return int(connection.execute("PRAGMA data_version").fetchone()[0]), connection.total_changes

    @staticmethod
    def _install_runtime_history(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE runtime_event_batches ("
            " sequence INTEGER PRIMARY KEY, record_json TEXT NOT NULL)"
        )
        for catalog, key, payload in (*_RUNTIME_EVENT_INDEX_CATALOGS, _SKILL_CANDIDATE_CATALOG):
            connection.execute(
                f"CREATE TABLE {catalog} ({key} TEXT PRIMARY KEY NOT NULL, {payload} TEXT NOT NULL)"
            )

    @contextmanager
    def capture_runtime_rows(self, connection: sqlite3.Connection) -> Iterator[list[RuntimeRowChange]]:
        """Collect exact materialization changes inside this publisher's transaction."""
        changes: list[RuntimeRowChange] = []
        if not self.supports_runtime_history(connection):
            yield changes
            return
        if not connection.in_transaction:
            raise sqlite3.DatabaseError("runtime write capture requires a transaction")
        connection.execute(
            "CREATE TEMP TABLE runtime_publication_changes ("
            " ordinal INTEGER PRIMARY KEY, catalog TEXT NOT NULL, operation TEXT NOT NULL,"
            " key_json TEXT NOT NULL, indexed_json TEXT NOT NULL, record_json TEXT NOT NULL,"
            " prior_record_json TEXT)"
        )
        triggers: list[str] = []
        try:
            for catalog, (keys, indexed) in self._runtime_row_layouts(connection):
                triggers.extend(self._capture_runtime_catalog(connection, catalog, keys, indexed))
            yield changes
            observed: dict[tuple[str, str], RuntimeRowChange] = {}
            for row in connection.execute(
                "SELECT catalog, operation, key_json, indexed_json, record_json, prior_record_json"
                " FROM runtime_publication_changes ORDER BY ordinal"
            ):
                coordinate = (str(row["catalog"]), str(row["key_json"]))
                previous = observed.get(coordinate)
                operation: Literal["create", "update"] = (
                    "create"
                    if row["operation"] == "create" or (previous is not None and previous.operation == "create")
                    else "update"
                )
                observed[coordinate] = RuntimeRowChange(RuntimeMaterializedRow(
                    catalog=coordinate[0],
                    key=tuple(json.loads(coordinate[1])),
                    indexed=tuple(json.loads(row["indexed_json"])),
                    record_json=str(row["record_json"]),
                ), operation, row["prior_record_json"] if previous is None else previous.prior_record_json)
            changes.extend(observed.values())
        finally:
            for trigger in triggers:
                connection.execute(f"DROP TRIGGER temp.{trigger}")
            connection.execute("DROP TABLE temp.runtime_publication_changes")

    @staticmethod
    def _capture_runtime_catalog(
        connection: sqlite3.Connection,
        catalog: str,
        keys: tuple[str, ...],
        indexed: tuple[str, ...],
    ) -> tuple[str, ...]:
        key_json = ", ".join(f"NEW.{column}" for column in keys)
        indexed_json = ", ".join(f"NEW.{column}" for column in indexed)
        key_changed = " OR ".join(f"OLD.{column} IS NOT NEW.{column}" for column in keys)
        row_changed = " OR ".join(f"OLD.{column} IS NOT NEW.{column}" for column in (*indexed, "record_json"))
        inserted = f"{catalog}_capture_insert"
        updated = f"{catalog}_capture_update"
        deleted = f"{catalog}_capture_delete"
        connection.execute(
            f"CREATE TEMP TRIGGER {inserted} AFTER INSERT ON main.{catalog} BEGIN"
            " INSERT INTO runtime_publication_changes"
            " (catalog, operation, key_json, indexed_json, record_json) VALUES"
            f" ('{catalog}', 'create', json_array({key_json}), json_array({indexed_json}), NEW.record_json); END"
        )
        connection.execute(
            f"CREATE TEMP TRIGGER {updated} AFTER UPDATE ON main.{catalog} BEGIN"
            f" SELECT RAISE(ABORT, 'runtime record identity is immutable') WHERE {key_changed};"
            " INSERT INTO runtime_publication_changes"
            " (catalog, operation, key_json, indexed_json, record_json, prior_record_json)"
            f" SELECT '{catalog}', 'update', json_array({key_json}), json_array({indexed_json}),"
            " NEW.record_json, OLD.record_json"
            f" WHERE {row_changed}; END"
        )
        connection.execute(
            f"CREATE TEMP TRIGGER {deleted} BEFORE DELETE ON main.{catalog}"
            " BEGIN SELECT RAISE(ABORT, 'runtime records require logical retirement'); END"
        )
        return inserted, updated, deleted

    @staticmethod
    def runtime_materialized_rows(connection: sqlite3.Connection) -> Iterator[RuntimeMaterializedRow]:
        for catalog, (keys, indexed) in PartitionDataRepository._runtime_row_layouts(connection):
            columns = ", ".join((*keys, *indexed, "record_json"))
            for row in connection.execute(f"SELECT {columns} FROM {catalog}"):
                yield RuntimeMaterializedRow(
                    catalog=catalog,
                    key=tuple(row[column] for column in keys),
                    indexed=tuple(row[column] for column in indexed),
                    record_json=str(row["record_json"]),
                )

    @staticmethod
    def runtime_event_batch_rows(connection: sqlite3.Connection) -> Iterator[tuple[int, str]]:
        for row in connection.execute("SELECT sequence, record_json FROM runtime_event_batches ORDER BY sequence"):
            yield int(row[0]), str(row[1])

    @staticmethod
    def runtime_replay_bindings(connection: sqlite3.Connection) -> tuple[dict[str, str], ...]:
        return tuple(
            {str(row[0]): str(row[1]) for row in connection.execute(f"SELECT {key}, {payload} FROM {catalog}")}
            for catalog, key, payload in _RUNTIME_EVENT_INDEX_CATALOGS
        )

    @staticmethod
    def insert_runtime_event_batch(
        connection: sqlite3.Connection,
        *,
        sequence: int,
        record_json: str,
        bindings: tuple[dict[str, str], dict[str, str], dict[str, str]],
    ) -> None:
        for (catalog, key, payload), identity_rows in zip(_RUNTIME_EVENT_INDEX_CATALOGS, bindings, strict=True):
            connection.executemany(
                f"INSERT INTO {catalog} ({key}, {payload}) VALUES (?, ?)",
                identity_rows.items(),
            )
        connection.execute(
            "INSERT INTO runtime_event_batches (sequence, record_json) VALUES (?, ?)",
            (sequence, record_json),
        )

    @staticmethod
    def _has_consolidation_catalog(connection: sqlite3.Connection) -> bool:
        return PartitionDataRepository._has_catalog(connection, "consolidation_results")

    @staticmethod
    def _has_catalog(connection: sqlite3.Connection, name: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,),
        ).fetchone() is not None

    def stage_consolidation_schema_upgrade(self, connection: sqlite3.Connection) -> None:
        """Install the new catalog on an unpublished staged generation.

        The administration owner must verify the old signed generation and
        publish this staged database as a distinct, signed generation before
        managed reads or writes use it.
        """
        if not connection.in_transaction or self.read_publication_row(connection) is not None:
            raise sqlite3.DatabaseError("schema upgrade requires an unpublished staging transaction")
        if self.read_schema_version(connection) != _INITIAL_PARTITION_SCHEMA_VERSION:
            raise sqlite3.DatabaseError("consolidation upgrade requires the initial partition format")
        self._install_consolidation_catalog(connection)
        connection.execute(
            "UPDATE partition_schema SET value = ? WHERE key = 'schema_version'",
            (str(_CONSOLIDATION_SCHEMA_VERSION),),
        )

    @staticmethod
    def _install_consolidation_catalog(connection: sqlite3.Connection) -> None:
        connection.execute(_CONSOLIDATION_SCHEMA_STATEMENT)

    def stage_delivery_schema_upgrade(self, connection: sqlite3.Connection) -> None:
        """Install delivery catalogs only before staged generation publication."""
        if not connection.in_transaction or self.read_publication_row(connection) is not None:
            raise sqlite3.DatabaseError("schema upgrade requires an unpublished staging transaction")
        if self.read_schema_version(connection) != _CONSOLIDATION_SCHEMA_VERSION:
            raise sqlite3.DatabaseError("delivery upgrade requires the consolidation partition format")
        self._install_delivery_catalogs(connection)
        connection.execute(
            "UPDATE partition_schema SET value = ? WHERE key = 'schema_version'",
            (str(_DELIVERY_SCHEMA_VERSION),),
        )

    @staticmethod
    def _install_delivery_catalogs(connection: sqlite3.Connection) -> None:
        for catalog, key, payload in _DELIVERY_CATALOGS:
            connection.execute(
                f"CREATE TABLE {catalog} ({key} TEXT PRIMARY KEY NOT NULL, {payload} TEXT NOT NULL)"
            )

    @staticmethod
    def require_delivery_catalogs(connection: sqlite3.Connection) -> None:
        if PartitionDataRepository.read_schema_version(connection) < _DELIVERY_SCHEMA_VERSION:
            raise sqlite3.DatabaseError("delivery partition schema upgrade required")

    @staticmethod
    def read_delivery_record(
        connection: sqlite3.Connection,
        *,
        catalog: DeliveryCatalog,
        record_id: str,
    ) -> str | None:
        PartitionDataRepository.require_delivery_catalogs(connection)
        key = PartitionDataRepository._delivery_catalog_key(connection, catalog)
        row = connection.execute(
            f"SELECT record_json FROM {catalog} WHERE {key} = ?", (record_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    @staticmethod
    def insert_delivery_record(
        connection: sqlite3.Connection,
        *,
        catalog: DeliveryCatalog,
        record_id: str,
        record_json: str,
    ) -> None:
        PartitionDataRepository.require_delivery_catalogs(connection)
        key = PartitionDataRepository._delivery_catalog_key(connection, catalog)
        connection.execute(
            f"INSERT INTO {catalog} ({key}, record_json) VALUES (?, ?)", (record_id, record_json),
        )

    @staticmethod
    def _delivery_catalog_key(connection: sqlite3.Connection, catalog: str) -> str:
        if catalog == _SKILL_CANDIDATE_CATALOG[0] and not PartitionDataRepository.supports_runtime_history(connection):
            raise sqlite3.DatabaseError("partition schema upgrade required for protected skill candidates")
        for known_catalog, key, _ in _CURRENT_DELIVERY_CATALOGS:
            if known_catalog == catalog:
                return key
        raise ValueError("unsupported delivery catalog")

    @staticmethod
    def read_runtime_source_release_grant(connection: sqlite3.Connection, grant_id: str) -> str | None:
        row = connection.execute(
            "SELECT record_json FROM runtime_source_release_grants WHERE grant_id = ?", (grant_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    @staticmethod
    def read_active_runtime_source_release_grants(
        connection: sqlite3.Connection, *, task_prefix: str, limit: int,
    ) -> tuple[str, ...]:
        rows = connection.execute(
            "SELECT record_json FROM runtime_source_release_grants"
            " WHERE grant_id GLOB ? AND json_extract(record_json, '$.status') = 'active'"
            " ORDER BY grant_id LIMIT ?",
            (task_prefix + "*", limit),
        )
        return tuple(str(row[0]) for row in rows)

    @staticmethod
    def write_runtime_source_release_grant(
        connection: sqlite3.Connection, *, grant_id: str, record_json: str, previous_json: str | None,
    ) -> None:
        if previous_json is None:
            connection.execute(
                "INSERT INTO runtime_source_release_grants (grant_id, record_json) VALUES (?, ?)",
                (grant_id, record_json),
            )
            return
        updated = connection.execute(
            "UPDATE runtime_source_release_grants SET record_json = ? WHERE grant_id = ? AND record_json = ?",
            (record_json, grant_id, previous_json),
        )
        if updated.rowcount != 1:
            raise sqlite3.DatabaseError("runtime source release grant no longer matches its previous state")

    def read_publication_row(self, connection: sqlite3.Connection) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT ordinal, position_kind, position_sequence, position_digest,"
            " tuple_digest, generation_id, vector_json, manifest_digest"
            " FROM partition_publication WHERE id = 1"
        ).fetchone()

    def write_publication_row(
        self,
        connection: sqlite3.Connection,
        *,
        ordinal: int,
        position_kind: str,
        position_sequence: int | None,
        position_digest: str,
        tuple_digest: str,
        generation_id: str,
        vector_json: str,
        manifest_digest: str,
    ) -> None:
        connection.execute(
            "INSERT INTO partition_publication (id, ordinal, position_kind, position_sequence,"
            " position_digest, tuple_digest, generation_id, vector_json, manifest_digest)"
            " VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET ordinal = excluded.ordinal,"
            " position_kind = excluded.position_kind,"
            " position_sequence = excluded.position_sequence,"
            " position_digest = excluded.position_digest,"
            " tuple_digest = excluded.tuple_digest,"
            " generation_id = excluded.generation_id,"
            " vector_json = excluded.vector_json,"
            " manifest_digest = excluded.manifest_digest",
            (
                ordinal,
                position_kind,
                position_sequence,
                position_digest,
                tuple_digest,
                generation_id,
                vector_json,
                manifest_digest,
            ),
        )

    def replace_derived_semantic_index(
        self,
        connection: sqlite3.Connection,
        projection: SemanticIndexProjection,
        *,
        write_revision: int,
        data_revision: int,
    ) -> None:
        """Replace the derived semantic index generation atomically.

        Rows are derived state: each generation is a full replace bound to
        the snapshot authority and revision counters recorded alongside it.
        """
        connection.execute("DELETE FROM semantic_entities")
        connection.execute("DELETE FROM semantic_claims")
        connection.execute("DELETE FROM semantic_evidence_links")
        for entity in projection.entities:
            connection.execute(
                "INSERT INTO semantic_entities (logical_entity_id, entity_revision_id,"
                " lifecycle, record_id, record_digest, codec_fingerprint)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entity.logical_entity_id,
                    entity.entity_revision_id,
                    entity.lifecycle,
                    entity.record_id,
                    entity.record_digest,
                    entity.codec_fingerprint,
                ),
            )
        for claim in projection.claims:
            connection.execute(
                "INSERT INTO semantic_claims (claim_assertion_id, subject_entity_id,"
                " object_entity_id, predicate_id, record_id, record_digest,"
                " valid_from, valid_to) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim.claim_assertion_id,
                    claim.subject_entity_id,
                    claim.object_entity_id,
                    claim.predicate_id,
                    claim.record_id,
                    claim.record_digest,
                    claim.valid_from,
                    claim.valid_to,
                ),
            )
        for link in projection.evidence_links:
            connection.execute(
                "INSERT INTO semantic_evidence_links (claim_assertion_id, source_id,"
                " source_digest, evidence_digest) VALUES (?, ?, ?, ?)",
                (
                    link.claim_assertion_id,
                    link.source_id,
                    link.source_digest,
                    link.evidence_digest,
                ),
            )
        connection.execute(
            "INSERT INTO semantic_index_state (id, graph_revision, snapshot_digest,"
            " write_revision, data_revision) VALUES (1, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET graph_revision = excluded.graph_revision,"
            " snapshot_digest = excluded.snapshot_digest,"
            " write_revision = excluded.write_revision,"
            " data_revision = excluded.data_revision",
            (
                projection.graph_revision,
                projection.snapshot_digest,
                write_revision,
                data_revision,
            ),
        )

    def replace_derived_ontology_index(
        self,
        connection: sqlite3.Connection,
        projection: OntologyIndexProjection,
    ) -> None:
        """Replace the derived ontology index generation atomically."""
        connection.execute("DELETE FROM ontology_candidates")
        connection.execute("DELETE FROM ontology_versions")
        connection.execute("DELETE FROM ontology_selections")
        connection.execute("DELETE FROM ontology_activation_attempts")
        connection.execute("DELETE FROM ontology_replay_receipts")
        for candidate in projection.candidates:
            connection.execute(
                "INSERT INTO ontology_candidates (proposal_id, lifecycle, record_digest)"
                " VALUES (?, ?, ?)",
                (candidate.proposal_id, candidate.lifecycle, candidate.record_digest),
            )
        for version in projection.versions:
            connection.execute(
                "INSERT INTO ontology_versions (version_digest, record_id, record_digest)"
                " VALUES (?, ?, ?)",
                (version.version_digest, version.record_id, version.record_digest),
            )
        for selection in projection.selections:
            connection.execute(
                "INSERT INTO ontology_selections (scope_key, selected_version_digest,"
                " selected_attempt_id, activation_sequence, record_digest)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    selection.scope_key,
                    selection.selected_version_digest,
                    selection.selected_attempt_id,
                    selection.activation_sequence,
                    selection.record_digest,
                ),
            )
        for attempt in projection.attempts:
            connection.execute(
                "INSERT INTO ontology_activation_attempts (attempt_id, status, record_digest)"
                " VALUES (?, ?, ?)",
                (attempt.attempt_id, attempt.status, attempt.record_digest),
            )
        for receipt in projection.replay_receipts:
            connection.execute(
                "INSERT INTO ontology_replay_receipts (operation_id, record_digest)"
                " VALUES (?, ?)",
                (receipt.operation_id, receipt.record_digest),
            )

    def query_catalog_history(
        self, connection: sqlite3.Connection
    ) -> Sequence[sqlite3.Row]:
        """Immutable catalog versions in digest order (catalog history)."""
        return connection.execute(
            "SELECT version_digest, record_id, record_digest FROM ontology_versions"
            " ORDER BY version_digest"
        ).fetchall()

    def read_current_catalog_selections(
        self, connection: sqlite3.Connection
    ) -> Sequence[sqlite3.Row]:
        return connection.execute(
            "SELECT scope_key, selected_version_digest, selected_attempt_id,"
            " activation_sequence FROM ontology_selections ORDER BY scope_key"
        ).fetchall()

    def read_semantic_index_state(
        self, connection: sqlite3.Connection
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT graph_revision, snapshot_digest, write_revision, data_revision"
            " FROM semantic_index_state WHERE id = 1"
        ).fetchone()

    def query_entity_neighborhood(
        self,
        connection: sqlite3.Connection,
        *,
        logical_entity_id: str,
        depth: int,
    ) -> Sequence[sqlite3.Row]:
        """Claims within ``depth`` hops of the entity.

        Depth d means claims whose traversal distance from the seed entity is
        at most d: the entity frontier expands d-1 times through claim
        endpoints, then all claims touching the closed frontier are returned.
        """
        if depth not in (1, 2):
            raise ValueError("neighborhood depth must be 1 or 2")
        frontier = {logical_entity_id}
        for _ in range(depth - 1):
            placeholders = ", ".join("?" for _ in frontier)
            rows = connection.execute(
                "SELECT DISTINCT claim_assertion_id, subject_entity_id, object_entity_id"
                f" FROM semantic_claims WHERE subject_entity_id IN ({placeholders})"
                f" OR object_entity_id IN ({placeholders})",
                (*frontier, *frontier),
            ).fetchall()
            next_frontier = set(frontier)
            for row in rows:
                next_frontier.add(str(row["subject_entity_id"]))
                if row["object_entity_id"] is not None:
                    next_frontier.add(str(row["object_entity_id"]))
            frontier = next_frontier
        placeholders = ", ".join("?" for _ in frontier)
        return connection.execute(
            "SELECT claim_assertion_id, subject_entity_id, object_entity_id,"
            " predicate_id, record_id, record_digest, valid_from, valid_to"
            f" FROM semantic_claims WHERE subject_entity_id IN ({placeholders})"
            f" OR object_entity_id IN ({placeholders})"
            " ORDER BY claim_assertion_id",
            (*frontier, *frontier),
        ).fetchall()

    def query_claim_evidence(
        self, connection: sqlite3.Connection, *, claim_assertion_id: str
    ) -> Sequence[sqlite3.Row]:
        return connection.execute(
            "SELECT claim_assertion_id, source_id, source_digest, evidence_digest"
            " FROM semantic_evidence_links WHERE claim_assertion_id = ?"
            " ORDER BY source_id",
            (claim_assertion_id,),
        ).fetchall()

    def read_revision_state(self, connection: sqlite3.Connection) -> tuple[int, int]:
        row = connection.execute(
            "SELECT write_revision, data_revision FROM memory_revision_state WHERE id = 1"
        ).fetchone()
        if row is None:
            raise sqlite3.DatabaseError("memory revision state is missing")
        return int(row["write_revision"]), int(row["data_revision"])

    @staticmethod
    def read_runtime_revision(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT runtime_revision FROM runtime_revision_state WHERE id = 1"
        ).fetchone()
        if row is None:
            raise sqlite3.DatabaseError("runtime revision state is missing")
        return int(row["runtime_revision"])

    def bump_runtime_revision(self, connection: sqlite3.Connection) -> int:
        current = self.read_runtime_revision(connection)
        connection.execute(
            "UPDATE runtime_revision_state SET runtime_revision = ? WHERE id = 1",
            (current + 1,),
        )
        return current + 1

    def upsert_runtime_row(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        keys: tuple[str, ...],
        values: tuple[object, ...],
        record_json: str,
        index_columns: tuple[str, ...] = (),
        index_values: tuple[object, ...] = (),
    ) -> None:
        """Upsert one typed runtime row.

        ``keys``/``values`` name the conflict-target identity; the optional
        index columns participate in the INSERT (filtering support) but are
        never updated on conflict — the record JSON stays authoritative.
        """
        if table not in _RUNTIME_UPSERT_TABLES:
            raise sqlite3.DatabaseError(f"unknown runtime catalog: {table}")
        columns = ", ".join([*keys, *index_columns, "record_json"])
        placeholders = ", ".join(
            "?" for _ in (*keys, *index_columns, "record_json")
        )
        connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            f" ON CONFLICT({', '.join(keys)}) DO UPDATE SET"
            " record_json = excluded.record_json",
            (*values, *index_values, record_json),
        )

    def read_runtime_rows(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        match: tuple[tuple[str, object], ...] = (),
    ) -> Sequence[sqlite3.Row]:
        if table not in _RUNTIME_UPSERT_TABLES:
            raise sqlite3.DatabaseError(f"unknown runtime catalog: {table}")
        clauses = ""
        parameters: list[object] = []
        if match:
            clauses = " WHERE " + " AND ".join(f"{key} = ?" for key, _ in match)
            parameters = [value for _, value in match]
        return connection.execute(
            f"SELECT record_json FROM {table}{clauses}", parameters
        ).fetchall()

    def read_runtime_row(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        match: tuple[tuple[str, object], ...],
    ) -> sqlite3.Row | None:
        rows = self.read_runtime_rows(connection, table=table, match=match)
        return rows[0] if rows else None

    def _require_consolidation_catalog(self, connection: sqlite3.Connection) -> None:
        if self.read_schema_version(connection) < _CONSOLIDATION_SCHEMA_VERSION:
            raise sqlite3.DatabaseError("partition schema upgrade required for consolidation results")

    def read_consolidation_rows(
        self, connection: sqlite3.Connection, *, result_id: str | None = None,
    ) -> Sequence[sqlite3.Row]:
        self._require_consolidation_catalog(connection)
        if result_id is not None:
            return connection.execute(
                "SELECT result_id, record_json FROM consolidation_results WHERE result_id = ?",
                (result_id,),
            ).fetchall()
        return connection.execute(
            "SELECT result_id, record_json FROM consolidation_results ORDER BY result_id"
        ).fetchall()

    def insert_consolidation_row(
        self, connection: sqlite3.Connection, *, result_id: str, record_json: str,
    ) -> None:
        self._require_consolidation_catalog(connection)
        connection.execute(
            "INSERT INTO consolidation_results (result_id, record_json) VALUES (?, ?)",
            (result_id, record_json),
        )

    def read_batch_rows(self, connection: sqlite3.Connection) -> Sequence[sqlite3.Row]:
        return connection.execute(
            "SELECT revision, data_revision, checksum, batch_json FROM memory_batches ORDER BY revision"
        ).fetchall()

    def read_current_record_rows(
        self,
        connection: sqlite3.Connection,
        *,
        statuses: Sequence[str] | None = None,
        domains: Sequence[str] | None = None,
        source_kinds: Sequence[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> Sequence[sqlite3.Row]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if statuses is not None:
            if not statuses:
                return ()
            clauses.append(f"status IN ({_placeholders(statuses)})")
            parameters.extend(sorted(statuses))
        if domains is not None:
            if not domains:
                return ()
            clauses.append(f"domain IN ({_placeholders(domains)})")
            parameters.extend(sorted(domains))
        if source_kinds is not None:
            if not source_kinds:
                return ()
            clauses.append(f"source_kind IN ({_placeholders(source_kinds)})")
            parameters.extend(sorted(source_kinds))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "" if limit is None else f" LIMIT {int(limit) + int(offset)}"
        return connection.execute(
            "SELECT memory_id, record_json FROM memory_current_records"
            f"{where} ORDER BY insertion_order{limit_clause}",
            parameters,
        ).fetchall()[offset:]

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
                self.read_schema_version(connection)
                return
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            if PARTITION_SCHEMA_VERSION >= _CONSOLIDATION_SCHEMA_VERSION:
                self._install_consolidation_catalog(connection)
            if PARTITION_SCHEMA_VERSION >= _DELIVERY_SCHEMA_VERSION:
                self._install_delivery_catalogs(connection)
            if PARTITION_SCHEMA_VERSION >= _RUNTIME_HISTORY_SCHEMA_VERSION:
                self._install_runtime_history(connection)
            if PARTITION_SCHEMA_VERSION >= _RUNTIME_SOURCE_RELEASE_SCHEMA_VERSION:
                connection.execute(
                    "CREATE TABLE runtime_source_release_grants ("
                    " grant_id TEXT PRIMARY KEY NOT NULL, record_json TEXT NOT NULL)"
                )
            connection.execute(
                "INSERT INTO memory_revision_state (id, write_revision, data_revision)"
                " VALUES (1, 0, 0)"
            )
            connection.execute(
                "INSERT INTO runtime_revision_state (id, runtime_revision)"
                " VALUES (1, 0)"
            )
            connection.execute(
                "INSERT INTO partition_schema (key, value) VALUES ('schema_version', ?)",
                (str(PARTITION_SCHEMA_VERSION),),
            )
