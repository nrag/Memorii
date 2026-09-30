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
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Imported lazily at runtime: the storage layer must not trigger the
    # eager memorii.core package initializer at import time (it pulls the
    # memory plane, which imports this module back).
    from memorii.core.memory_evolution.semantic_index import SemanticIndexProjection
    from memorii.core.persistence.contracts import MaterializationCatalogEntry
    from memorii.core.semantic_ingestion.ontology_index import OntologyIndexProjection

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
)

# Authoritative materialized catalogs covered by the signed manifest. The
# fold is canonical: per-row digest over (primary key, payload), chained in
# the catalog's primary-key order from a domain-separated per-catalog seed.
# The revision-state, publication and semantic-index-state rows are derived
# or self-referential and are excluded from the row root; the derived
# semantic tables ARE authoritative materialized state (rebuildable from
# canonical records, never independent facts) and are covered.
_MATERIALIZATION_CATALOGS = (
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
)
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
    }
)


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
        from memorii.core.memory_plane.file_lock import locked_file

        with self._thread_lock, locked_file(self._lock_path, exclusive=write):
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

        entries: list[MaterializationCatalogEntry] = []
        for catalog, key_expression, payload_column in _MATERIALIZATION_CATALOGS:
            rows = connection.execute(
                f"SELECT {key_expression} AS sort_key, {payload_column} AS payload"
                f" FROM {catalog} ORDER BY {key_expression}"
            ).fetchall()
            chain = hashlib.sha256(_CATALOG_SEED_DOMAIN + catalog.encode("ascii")).digest()
            for row in rows:
                row_digest = hashlib.sha256(
                    str(row["sort_key"]).encode("utf-8")
                    + b"\x00"
                    + row["payload"].encode("utf-8")
                ).digest()
                chain = hashlib.sha256(chain + b"\x00" + row_digest).digest()
            entries.append(
                MaterializationCatalogEntry(
                    catalog=catalog,
                    row_count=len(rows),
                    digest=chain.hex(),
                )
            )
        # Closed rule: the manifest covers exactly the declared catalogs —
        # one entry per name, no silent subset.
        if {entry.catalog for entry in entries} != {
            catalog for catalog, _, _ in _MATERIALIZATION_CATALOGS
        }:
            raise sqlite3.DatabaseError(
                "materialization manifest does not cover the declared catalogs"
            )
        return tuple(sorted(entries, key=lambda entry: entry.catalog))

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

    def read_runtime_revision(self, connection: sqlite3.Connection) -> int:
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
        match: tuple[str, object, ...] = (),
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
        match: tuple[str, object, ...],
    ) -> sqlite3.Row | None:
        rows = self.read_runtime_rows(connection, table=table, match=match)
        return rows[0] if rows else None

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
                "INSERT INTO runtime_revision_state (id, runtime_revision)"
                " VALUES (1, 0)"
            )
            connection.execute(
                "INSERT INTO partition_schema (key, value) VALUES ('schema_version', ?)",
                (str(PARTITION_SCHEMA_VERSION),),
            )
