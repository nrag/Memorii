"""Verified, rebuildable scope lookup for selected learned activations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from itertools import zip_longest

_ATTEMPT_KIND = "learned_ontology_activation_attempt_v1"
_TABLE = "catalog_selected_activations"
_INDEX = "catalog_selected_activations_by_scope"
_LAYOUT = {
    _TABLE: (
        f"CREATE TABLE {_TABLE} (memory_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL,"
        " agent_id TEXT NOT NULL) WITHOUT ROWID, STRICT"
    ),
    _INDEX: f"CREATE INDEX {_INDEX} ON {_TABLE}(principal_id, agent_id, memory_id)",
}


def has_catalog_selection_lookup(connection: sqlite3.Connection) -> bool:
    rows = dict(connection.execute(
        "SELECT name,sql FROM main.sqlite_schema WHERE name IN (?,?)", (_TABLE, _INDEX),
    ))
    if not rows:
        return False
    if rows != _LAYOUT:
        raise sqlite3.DatabaseError("catalog selection lookup differs from the declared layout")
    return True


def _scope(raw_record: str) -> tuple[str, str] | None:
    # Load lazily so the physical store can initialize before core services.
    from pydantic import ValidationError

    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.core.semantic_ingestion.learned_relation import OntologyActivation

    record = CanonicalMemoryRecord.model_validate_json(raw_record)
    try:
        attempt = OntologyActivation.model_validate(record.content.get("activation"))
    except ValidationError:
        # An invalid attempt does not establish a selected child in the
        # canonical reader. A present child pointer still blocks fallback.
        return None
    if attempt.status != "selected":
        return None
    return attempt.catalog_scope.principal_id, attempt.catalog_scope.agent_id


def _canonical_attempt_rows(connection: sqlite3.Connection) -> Iterator[tuple[str, str, str]]:
    # The kind index is covered by raw-payload Tier B parity before this
    # projection is verified. Installation backfill runs on a verified copy.
    rows = connection.execute(
        "SELECT c.memory_id, CAST(p.body AS TEXT)"
        " FROM memory_current_records c INDEXED BY memory_current_records_source_kind_lookup"
        " JOIN memory_payloads p USING (payload_digest) WHERE c.source_kind=? ORDER BY c.memory_id",
        (_ATTEMPT_KIND,),
    )
    for memory_id, raw_record in rows:
        if (scope := _scope(raw_record)) is not None:
            yield memory_id, *scope


def install_catalog_selection_lookup(connection: sqlite3.Connection) -> None:
    if has_catalog_selection_lookup(connection):
        return
    for statement in _LAYOUT.values():
        connection.execute(statement)
    connection.executemany(
        f"INSERT INTO {_TABLE}(memory_id,principal_id,agent_id) VALUES (?,?,?)",
        _canonical_attempt_rows(connection),
    )


def update_catalog_selection_lookup(
    connection: sqlite3.Connection, records: Iterable[tuple[str, str, str]],
) -> None:
    if not has_catalog_selection_lookup(connection):
        # Legacy formats keep their historical read path until owner staging.
        return
    for memory_id, source_kind, raw_record in records:
        scope = _scope(raw_record) if source_kind == _ATTEMPT_KIND else None
        if scope is None:
            connection.execute(f"DELETE FROM {_TABLE} WHERE memory_id=?", (memory_id,))
        else:
            connection.execute(
                f"INSERT INTO {_TABLE}(memory_id,principal_id,agent_id) VALUES (?,?,?)"
                " ON CONFLICT(memory_id) DO UPDATE SET principal_id=excluded.principal_id,agent_id=excluded.agent_id",
                (memory_id, *scope),
            )


def verify_catalog_selection_lookup(connection: sqlite3.Connection) -> None:
    if not has_catalog_selection_lookup(connection):
        return
    base = connection.execute(f"SELECT memory_id,principal_id,agent_id FROM {_TABLE} ORDER BY memory_id")
    if any(
        expected != (tuple(actual) if actual is not None else None)
        for expected, actual in zip_longest(_canonical_attempt_rows(connection), base)
    ):
        raise sqlite3.DatabaseError("catalog selection lookup differs from canonical records")
    table_rows = connection.execute(
        f"SELECT principal_id,agent_id,memory_id FROM {_TABLE} INDEXED BY sqlite_autoindex_{_TABLE}_1"
        " ORDER BY principal_id,agent_id,memory_id",
    )
    index_rows = connection.execute(
        f"SELECT principal_id,agent_id,memory_id FROM {_TABLE} INDEXED BY {_INDEX}"
        " ORDER BY principal_id,agent_id,memory_id",
    )
    if any(left != right for left, right in zip_longest(table_rows, index_rows)):
        raise sqlite3.DatabaseError("catalog selection index differs from its base rows")


def selected_catalog_activation_id(
    connection: sqlite3.Connection, *, principal_id: str, agent_id: str,
) -> str | None:
    if not has_catalog_selection_lookup(connection):
        raise sqlite3.DatabaseError("catalog metadata requires the verified selection scope lookup")
    row = connection.execute(
        f"SELECT memory_id FROM {_TABLE} INDEXED BY {_INDEX} WHERE principal_id=? AND agent_id=?"
        " ORDER BY memory_id LIMIT 1",
        (principal_id, agent_id),
    ).fetchone()
    return None if row is None else row[0]
