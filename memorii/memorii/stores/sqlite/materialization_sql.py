"""Typed SQLite catalog projection and transaction-local change capture."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from memorii.core.persistence.contracts import MaterializationCatalogEntry, RuntimeMaterializationManifest
from memorii.stores.sqlite.materialization_accumulator import MaterializationAccumulator

_Layout = tuple[tuple[str, ...], tuple[str, ...]]
_Value = str | int | None

# Format 7 commits every stored column of each authoritative catalog, including
# persisted filtering coordinates omitted by the historical ordered fold.
_LAYOUTS: dict[str, _Layout] = {
    "consolidation_results": (("result_id",), ("result_id", "record_json")),
    "memory_batches": (("revision",), ("revision", "data_revision", "checksum", "batch_json", "created_utc")),
    "memory_current_records": (("memory_id",), ("memory_id", "record_json", "status", "domain", "source_kind", "insertion_order")),
    "memory_record_versions": (("memory_id", "batch_revision"), ("memory_id", "batch_revision", "record_json")),
    "ontology_activation_attempts": (("attempt_id",), ("attempt_id", "status", "record_digest")),
    "ontology_candidates": (("proposal_id",), ("proposal_id", "lifecycle", "record_digest")),
    "ontology_replay_receipts": (("operation_id",), ("operation_id", "record_digest")),
    "ontology_selections": (("scope_key",), ("scope_key", "selected_version_digest", "selected_attempt_id", "activation_sequence", "record_digest")),
    "ontology_versions": (("version_digest",), ("version_digest", "record_id", "record_digest")),
    "runtime_action_attempts": (("action_id",), ("action_id", "task_id", "recommendation_id", "recommendation_revision", "record_json")),
    "runtime_checkpoints": (("checkpoint_id",), ("checkpoint_id", "task_id", "record_json")),
    "runtime_command_receipts": (("client_namespace", "operation_id"), ("client_namespace", "operation_id", "record_json")),
    "runtime_dedupe_bindings": (("dedupe_key",), ("dedupe_key", "binding_json")),
    "runtime_delivery_restore_holds": (("hold_id",), ("hold_id", "record_json")),
    "runtime_event_id_bindings": (("event_id",), ("event_id", "binding_json")),
    "runtime_execution_edges": (("task_id", "edge_id"), ("task_id", "edge_id", "record_json")),
    "runtime_execution_nodes": (("task_id", "node_id"), ("task_id", "node_id", "record_json")),
    "runtime_justifications": (("justification_id",), ("justification_id", "solver_id", "record_json")),
    "runtime_operation_attempts": (("receipt_id", "attempt_ordinal"), ("receipt_id", "attempt_ordinal", "record_json")),
    "runtime_outbox_deliveries": (("delivery_id",), ("delivery_id", "record_json")),
    "runtime_overlay_versions": (("version_id",), ("version_id", "solver_id", "record_json")),
    "runtime_record_version_bindings": (("record_version_id",), ("record_version_id", "binding_json")),
    "runtime_skill_candidates": (("candidate_id",), ("candidate_id", "record_json")),
    "runtime_solver_edges": (("solver_id", "edge_id"), ("solver_id", "edge_id", "record_json")),
    "runtime_solver_nodes": (("solver_id", "node_id"), ("solver_id", "node_id", "record_json")),
    "runtime_solver_runs": (("solver_id",), ("solver_id", "task_id", "record_json")),
    "runtime_source_release_grants": (("grant_id",), ("grant_id", "record_json")),
    "runtime_target_receipts": (("delivery_id",), ("delivery_id", "record_json")),
    "runtime_tasks": (("task_id",), ("task_id", "record_json")),
    "runtime_work_projections": (("delivery_id",), ("delivery_id", "record_json")),
    "semantic_claims": (("claim_assertion_id",), ("claim_assertion_id", "subject_entity_id", "object_entity_id", "predicate_id", "record_id", "record_digest", "valid_from", "valid_to")),
    "semantic_entities": (("logical_entity_id", "entity_revision_id"), ("logical_entity_id", "entity_revision_id", "lifecycle", "record_id", "record_digest", "codec_fingerprint")),
    "semantic_evidence_links": (("claim_assertion_id", "source_id"), ("claim_assertion_id", "source_id", "source_digest", "evidence_digest")),
    "writeback_decisions": (("decision_id",), ("decision_id", "record_json")),
}

_CAPTURE_TABLE = "manifest_changed_keys"


def _key_bytes(values: tuple[_Value, ...]) -> bytes:
    components: list[bytes] = []
    for value in values:
        if isinstance(value, str):
            # Preserve SQLite BINARY order, including embedded NUL bytes.
            components.append(b"s" + value.encode("utf-8").replace(b"\x00", b"\x00\xff") + b"\x00\x00")
        elif isinstance(value, int):
            components.append(b"i" + (value + 2**63).to_bytes(8, "big"))
        else:
            raise sqlite3.DatabaseError("materialization catalog key must be text or integer")
    return b"".join(components)


def _value_digest(row: sqlite3.Row) -> bytes:
    digest = hashlib.sha256(b"memorii.materialization-row.v2\x00")
    for value in row:
        if isinstance(value, str):
            encoded = value.encode("utf-8")
            digest.update(b"s" + len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        elif isinstance(value, int):
            digest.update(b"i" + value.to_bytes(8, "big", signed=True))
        elif value is None:
            digest.update(b"n")
        else:
            raise sqlite3.DatabaseError("unsupported storage type in materialization catalog")
    return digest.digest()


def _validate_layout(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT 1 FROM main.sqlite_schema WHERE type = 'trigger'").fetchone() is not None:
        raise sqlite3.DatabaseError("persistent triggers are outside the partition schema")
    for catalog, (key, columns) in _LAYOUTS.items():
        info = tuple(connection.execute(f"PRAGMA main.table_xinfo({catalog})"))
        if (
            tuple(row["name"] for row in info) != columns
            or tuple(row["name"] for row in sorted(info, key=lambda item: item["pk"]) if row["pk"]) != key
            or any(row["hidden"] for row in info)
        ):
            raise sqlite3.DatabaseError(f"materialization catalog layout changed: {catalog}")


def _catalog_entry(name: str, tree: MaterializationAccumulator) -> MaterializationCatalogEntry:
    return MaterializationCatalogEntry(catalog=name, row_count=tree.row_count, digest=tree.catalog_digest(name))


@dataclass(frozen=True)
class MaterializationForest:
    trees: tuple[tuple[str, MaterializationAccumulator], ...]
    manifest: RuntimeMaterializationManifest


def rebuild_manifest(connection: sqlite3.Connection, catalog_names: frozenset[str]) -> MaterializationForest:
    if catalog_names != _LAYOUTS.keys():
        raise sqlite3.DatabaseError("manifest accumulator does not cover the declared catalogs")
    _validate_layout(connection)
    trees = []
    for catalog, (key, columns) in _LAYOUTS.items():
        order = ", ".join(f"{column} COLLATE BINARY" for column in key)
        rows = connection.execute(f"SELECT {', '.join(columns)} FROM main.{catalog} ORDER BY {order}")
        tree = MaterializationAccumulator.from_sorted_digests(
            (_key_bytes(tuple(row[column] for column in key)), _value_digest(row)) for row in rows
        )
        trees.append((catalog, tree))
    return MaterializationForest(tuple(trees), RuntimeMaterializationManifest(
        catalogs=tuple(_catalog_entry(name, tree) for name, tree in trees),
    ))


@dataclass
class MaterializationCapture:
    result: MaterializationForest | None = None


@contextmanager
def capture_manifest_changes(
    connection: sqlite3.Connection, base: MaterializationForest,
) -> Iterator[MaterializationCapture]:
    """Track only affected keys, transactionally, including rolled-back statements."""
    schema_version = connection.execute("PRAGMA main.schema_version").fetchone()[0]
    recursive_triggers = connection.execute("PRAGMA recursive_triggers").fetchone()[0]
    connection.execute("PRAGMA recursive_triggers = ON")
    trigger_names: list[str] = []
    connection.execute(
        f"CREATE TEMP TABLE {_CAPTURE_TABLE} (catalog TEXT, first_key, second_key, "
        "PRIMARY KEY (catalog, first_key, second_key)) WITHOUT ROWID"
    )
    capture = MaterializationCapture()
    try:
        for catalog, (key, _) in _LAYOUTS.items():
            for operation, sources in (("INSERT", ("NEW",)), ("DELETE", ("OLD",)), ("UPDATE", ("OLD", "NEW"))):
                name = f"memorii_manifest_{catalog}_{operation.lower()}"
                statements = []
                for source in sources:
                    first = f"{source}.{key[0]}"
                    second = f"{source}.{key[1]}" if len(key) == 2 else "''"
                    statements.append(
                        f"INSERT INTO {_CAPTURE_TABLE} VALUES ('{catalog}', {first}, {second}) ON CONFLICT DO NOTHING;"
                    )
                connection.execute(f"CREATE TEMP TRIGGER {name} AFTER {operation} ON main.{catalog} BEGIN "
                                   f"{' '.join(statements)} END")
                trigger_names.append(name)
        yield capture
        if connection.execute("PRAGMA main.schema_version").fetchone()[0] != schema_version:
            raise sqlite3.DatabaseError("partition schema changed during materialization capture")
        capture.result = _apply_changes(connection, base)
    finally:
        for name in trigger_names:
            connection.execute(f"DROP TRIGGER temp.{name}")
        connection.execute(f"DROP TABLE temp.{_CAPTURE_TABLE}")
        connection.execute(f"PRAGMA recursive_triggers = {int(recursive_triggers)}")


def _apply_changes(connection: sqlite3.Connection, base: MaterializationForest) -> MaterializationForest:
    trees = dict(base.trees)
    entries = {entry.catalog: entry for entry in base.manifest.catalogs}
    for name, first_key, second_key in connection.execute(f"SELECT * FROM temp.{_CAPTURE_TABLE}"):
        key, columns = _LAYOUTS[name]
        coordinates = (first_key, second_key)[:len(key)]
        encoded = _key_bytes(coordinates)
        selector = " AND ".join(f"{column} COLLATE BINARY = ?" for column in key)
        row = connection.execute(
            f"SELECT {', '.join(columns)} FROM main.{name} WHERE {selector}", coordinates,
        ).fetchone()
        tree = trees[name]
        if row is not None:
            tree = tree.upsert_digest(encoded, _value_digest(row))
        elif tree.lookup_digest(encoded) is not None:
            tree = tree.delete(encoded)
        trees[name] = tree
        entries[name] = _catalog_entry(name, tree)
    return MaterializationForest(tuple(trees.items()), RuntimeMaterializationManifest(catalogs=tuple(entries.values())))


def verify_legacy_memory_selectors(connection: sqlite3.Connection) -> None:
    """Validate selectors omitted by the legacy root before signing them in v7."""
    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.core.memory_plane.store import PersistedBatch

    current: dict[str, tuple[int, bytes]] = {}
    batches = connection.execute(
        "SELECT revision, data_revision, checksum, batch_json FROM memory_batches ORDER BY revision",
    )
    for row in batches:
        batch = PersistedBatch.model_validate_json(row["batch_json"])
        if (batch.revision, batch.data_revision, batch.checksum) != (row["revision"], row["data_revision"], row["checksum"]):
            raise sqlite3.DatabaseError("legacy batch selectors differ from signed records")
        for record in batch.records:
            prior = current.get(record.memory_id)
            order = len(current) + 1 if prior is None else prior[0]
            current[record.memory_id] = order, hashlib.sha256(record.model_dump_json().encode()).digest()
    rows = connection.execute(
        "SELECT memory_id, record_json, status, domain, source_kind, insertion_order FROM memory_current_records",
    )
    for row in rows:
        record = CanonicalMemoryRecord.model_validate_json(row["record_json"])
        expected = current.pop(row["memory_id"], None)
        if (
            record.memory_id != row["memory_id"]
            or (record.status.value, record.domain.value, record.source_kind) != (
                row["status"], row["domain"], row["source_kind"],
            )
            or expected != (row["insertion_order"], hashlib.sha256(record.model_dump_json().encode()).digest())
        ):
            raise sqlite3.DatabaseError("legacy current selectors differ from signed records")
    if current:
        raise sqlite3.DatabaseError("legacy current record projection is incomplete")
