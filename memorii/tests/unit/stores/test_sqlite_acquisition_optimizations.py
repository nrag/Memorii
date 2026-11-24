"""Exact digest parity and bounded raw payload verification for acquisition."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from hashlib import sha256

import pytest
from memorii.core.persistence.runtime_journal import (
    _BINDING_JSON,
    _MEMBER_JSON,
    _CheckpointBinding,
    _CheckpointMember,
    _member_digest,
)
from memorii.stores.sqlite import raw_memory_payloads
from memorii.stores.sqlite.materialization_sql import _catalog_digests, _key_bytes, _value_digest


def test_catalog_projection_matches_incremental_digest_framing() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE records (identity, record)")
        connection.executemany(
            "INSERT INTO records VALUES (?,?)",
            (("\u00e9\x00\U0001f4a1", "other\x00\u00e9\n"), ("large", "\u00e9" * 5_000), (1, None), (b"binary\x00", b"value")),
        )
        sql = "SELECT identity, record FROM records ORDER BY identity COLLATE BINARY"
        expected = [
            (_key_bytes((row["identity"],), allow_bytes=True), _value_digest(row, allow_bytes=True))
            for row in connection.execute(sql)
        ]
        assert list(_catalog_digests(
            connection.execute(sql), ("identity",), ("identity", "record"), allow_bytes=True,
        )) == expected

        composite_sql = "SELECT record, identity FROM records ORDER BY identity COLLATE BINARY"
        reordered = [
            (_key_bytes((row["identity"],), allow_bytes=True), _value_digest(row, allow_bytes=True))
            for row in connection.execute(composite_sql)
        ]
        assert list(_catalog_digests(
            connection.execute(composite_sql), ("identity",), ("record", "identity"), allow_bytes=True,
        )) == reordered


def _previous_checkpoint_digest(records: Sequence[_CheckpointMember | _CheckpointBinding]) -> str:
    digest = sha256()
    for item in records:
        payload = item.model_dump_json().encode("utf-8")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def test_checkpoint_byte_serialization_preserves_the_signed_member_digest() -> None:
    members = (
        _CheckpointMember(
            catalog="runtime_execution_nodes", key=("task:\u00e9\x00\U0001f4a1", "node:one"),
            indexed=("index", 1), owner_record_json='{"title":"\u00e9\U0001f4a1","escaped":"\\u0000"}',
        ),
        _CheckpointMember(
            catalog="runtime_tasks", key=("task:\u00e9",), indexed=(),
            owner_record_json='{"goal":"a\\tquoted \\"value\\""}',
        ),
    )
    bindings = (
        _CheckpointBinding(coordinate="1" * 64, owner_binding_json='{"event":"\u00e9\U0001f4a1"}'),
        _CheckpointBinding(coordinate="2" * 64, owner_binding_json='{"sequence":1}'),
    )
    assert _member_digest(members, _MEMBER_JSON) == _previous_checkpoint_digest(members)
    assert _member_digest(bindings, _BINDING_JSON) == _previous_checkpoint_digest(bindings)


def test_large_raw_payload_stream_still_rejects_a_changed_final_byte(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"z" * (raw_memory_payloads._MAX_QUEUED_PAYLOAD_BYTES + 1)
    key = raw_memory_payloads.payload_digest(body)

    def reject_buffering(raw: bytes, expected: bytes) -> None:
        pytest.fail("the payload exceeded the parallel verification buffer limit")

    monkeypatch.setattr(raw_memory_payloads, "_verify_buffer", reject_buffering)
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        for sql in raw_memory_payloads._SCHEMA.values():
            connection.execute(sql)
        connection.execute("INSERT INTO memory_payloads VALUES (?, ?, 0, ?)", (key, len(body), body))
        connection.execute("INSERT INTO memory_batches VALUES (1, 1, ?, 'time', 1)", ("a" * 64,))
        connection.execute("INSERT INTO memory_record_versions VALUES ('record', 1, ?)", (key,))
        connection.execute("INSERT INTO memory_batch_members VALUES (1, 0, 'record', ?)", (key,))
        connection.execute(
            "INSERT INTO memory_current_records VALUES ('record', 1, ?, 'active', 'work', 'test', 1, NULL)",
            (key,),
        )
        raw_memory_payloads.verify_raw_payloads(connection)
        with connection.blobopen("memory_payloads", "body", 1) as blob:
            blob.seek(len(body) - 1)
            blob.write(b"x")
        with pytest.raises(sqlite3.DatabaseError, match="raw memory payload digest differs"):
            raw_memory_payloads.verify_raw_payloads(connection)
