"""Production receipt indexes scope admission and order recall candidates."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from memorii.stores.sqlite.native_receipts import (
    native_recall_candidates,
    task_observation_source_keys,
    verify_native_receipt_indexes,
)
from memorii.stores.sqlite.partition import PartitionDataRepository


def _receipt(task: str, source: str, revision: int) -> str:
    return json.dumps({"source_admission": {
        "task_id": task, "source_id": source, "source_record_digest": source, "source_write_revision": revision,
    }})


def test_receipt_indexes_keep_exact_task_order_and_unique_sources(tmp_path: Path) -> None:
    with (
        PartitionDataRepository(tmp_path / "partition.sqlite3") as partition,
        partition.transaction(write=True) as connection,
    ):
        connection.executemany(
            "INSERT INTO runtime_command_receipts VALUES (?,?,?)",
            (
                ("scope", f"native-source:{ordinal}", _receipt(f"other:{ordinal}", "unrelated", ordinal))
                for ordinal in range(1000)
            ),
        )
        connection.executemany(
            "INSERT INTO runtime_command_receipts VALUES (?,?,?)",
            [
                ("scope", "native-source:older", _receipt("target", "first", 1)),
                ("scope", "native-source:a", _receipt("target", "duplicate", 2)),
                ("scope", "native-source:b", _receipt("target", "duplicate", 2)),
                ("elsewhere", "native-source:z", _receipt("target", "not-for-recall", 10)),
            ],
        )
        verify_native_receipt_indexes(connection)
        candidates = native_recall_candidates(connection, namespace="scope", task_id="target", stop_after=3)
        assert tuple(row[0] for row in candidates) == (
            _receipt("target", "duplicate", 2), _receipt("target", "duplicate", 2), _receipt("target", "first", 1),
        )
        distinct = task_observation_source_keys(connection, task_id="target", limit=4)
        assert {tuple(row) for row in distinct} == {
            ("first", "first"), ("duplicate", "duplicate"), ("not-for-recall", "not-for-recall"),
        }


def test_receipt_index_loss_fails_closed_even_with_base_rows(tmp_path: Path) -> None:
    with PartitionDataRepository(tmp_path / "partition.sqlite3") as partition:
        with partition.transaction(write=True) as connection:
            connection.execute(
                "INSERT INTO runtime_command_receipts VALUES (?,?,?)",
                ("scope", "native-source:retained", _receipt("target", "source", 1)),
            )
            connection.execute("DROP INDEX runtime_native_source_recall")
        with partition.transaction(write=False) as connection:
            with pytest.raises(sqlite3.DatabaseError, match="declared layout"):
                verify_native_receipt_indexes(connection)
            with pytest.raises(sqlite3.DatabaseError, match="declared layout"):
                native_recall_candidates(connection, namespace="scope", task_id="target", stop_after=3)
