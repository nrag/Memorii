"""Verified ordered candidate indexes over signed observation receipts."""

from __future__ import annotations

import sqlite3
from itertools import zip_longest

_TASK = "json_extract(record_json, '$.source_admission.task_id')"
_SOURCE_ID = "json_extract(record_json, '$.source_admission.source_id')"
_SOURCE_DIGEST = "json_extract(record_json, '$.source_admission.source_record_digest')"
_SOURCE_REVISION = "json_extract(record_json, '$.source_admission.source_write_revision')"
_OBSERVATIONS = f"{_TASK} IS NOT NULL"
_NATIVE = f"{_OBSERVATIONS} AND operation_id >= 'native-source:' AND operation_id < 'native-source;'"
_SOURCE_INDEX = "runtime_task_observation_sources"
_RECALL_INDEX = "runtime_native_source_recall"
_INDEXES = {
    _SOURCE_INDEX: (
        f"CREATE INDEX {_SOURCE_INDEX} ON runtime_command_receipts ({_TASK}, {_SOURCE_ID}, {_SOURCE_DIGEST})"
        f" WHERE {_OBSERVATIONS}"
    ),
    _RECALL_INDEX: (
        f"CREATE INDEX {_RECALL_INDEX} ON runtime_command_receipts"
        f" (client_namespace, {_TASK}, {_SOURCE_REVISION} DESC, operation_id) WHERE {_NATIVE}"
    ),
}


def has_native_receipt_indexes(connection: sqlite3.Connection) -> bool:
    rows = dict(connection.execute(
        "SELECT name,sql FROM main.sqlite_schema WHERE type='index' AND name IN (?,?)",
        (_SOURCE_INDEX, _RECALL_INDEX),
    ).fetchall())
    if not rows:
        return False
    if rows != _INDEXES:
        raise sqlite3.DatabaseError("native receipt indexes differ from the declared layout")
    return True


def install_native_receipt_indexes(connection: sqlite3.Connection) -> None:
    if not has_native_receipt_indexes(connection):
        for statement in _INDEXES.values():
            connection.execute(statement)


def verify_native_receipt_indexes(connection: sqlite3.Connection) -> None:
    """Compare separate base and forced-index walks for each declared key."""
    if not has_native_receipt_indexes(connection):
        return
    for index, columns, predicate, order in (
        (_SOURCE_INDEX, f"{_TASK}, {_SOURCE_ID}, {_SOURCE_DIGEST}, rowid", _OBSERVATIONS, "1,2,3,4"),
        (
            _RECALL_INDEX, f"client_namespace, {_TASK}, {_SOURCE_REVISION}, operation_id, rowid",
            _NATIVE, "1,2,3 DESC,4,5",
        ),
    ):
        base = connection.execute(
            f"SELECT {columns} FROM runtime_command_receipts NOT INDEXED WHERE {predicate} ORDER BY {order}"
        )
        indexed = connection.execute(
            f"SELECT {columns} FROM runtime_command_receipts INDEXED BY {index} WHERE {predicate} ORDER BY {order}"
        )
        if any(left != right for left, right in zip_longest(base, indexed)):
            raise sqlite3.DatabaseError("native receipt index differs from its base rows")


def native_recall_candidates(
    connection: sqlite3.Connection, *, namespace: str, task_id: str, stop_after: int,
) -> sqlite3.Cursor:
    if not has_native_receipt_indexes(connection):
        raise sqlite3.DatabaseError("native recall requires the verified observation indexes")
    return connection.execute(
        f"SELECT record_json FROM runtime_command_receipts INDEXED BY {_RECALL_INDEX}"
        f" WHERE {_NATIVE} AND client_namespace=? AND {_TASK}=?"
        f" ORDER BY {_SOURCE_REVISION} DESC, operation_id LIMIT ?",
        (namespace, task_id, stop_after),
    )


def task_observation_source_keys(
    connection: sqlite3.Connection, *, task_id: str, limit: int,
) -> sqlite3.Cursor:
    selector = f" INDEXED BY {_SOURCE_INDEX}" if has_native_receipt_indexes(connection) else ""
    return connection.execute(
        f"SELECT DISTINCT {_SOURCE_ID} AS source_id, {_SOURCE_DIGEST} AS source_digest"
        f" FROM runtime_command_receipts{selector} WHERE {_OBSERVATIONS} AND {_TASK}=? LIMIT ?",
        (task_id, limit),
    )
