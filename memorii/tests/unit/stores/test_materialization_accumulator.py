"""Verify canonical rebuild parity and immutable incremental manifest updates."""

from __future__ import annotations

import random

import pytest
from memorii.stores.sqlite.materialization_accumulator import MaterializationAccumulator, row_value_digest


def test_bulk_root_matches_both_directions_and_shuffled_mutation_orders() -> None:
    rows = [(index.to_bytes(4, "big"), f"fixture:{index}".encode()) for index in range(250)]
    expected = MaterializationAccumulator.from_sorted_rows(rows)
    assert expected.row_count == len(rows)
    rng = random.Random(17)
    assert expected.catalog_digest("first") != expected.catalog_digest("second")
    for permutation in (rows, reversed(rows), rng.sample(rows, len(rows))):
        result = MaterializationAccumulator.empty()
        for key, value in permutation:
            result = result.upsert(key, value)
        assert result.catalog_digest("memory") == expected.catalog_digest("memory")
        assert result.row_count == expected.row_count


def test_random_incremental_changes_match_a_fresh_bulk_rebuild() -> None:
    rng = random.Random(31)
    rows: dict[bytes, bytes] = {}
    current = MaterializationAccumulator.empty()
    for operation in range(500):
        key = rng.randrange(100).to_bytes(4, "big")
        previous = current
        prior_digest = previous.catalog_digest("memory_records")
        prior_lookup = previous.lookup_digest(key)
        if key in rows and operation % 3 == 0:
            del rows[key]
            current = current.delete(key)
            assert current.lookup_digest(key) is None
        else:
            value = f"change:{operation}:\x00".encode()
            rows[key] = value
            current = current.upsert_digest(key, row_value_digest(value))
            assert current.lookup_digest(key) == row_value_digest(value)
            assert current.upsert(key, value) is current
        assert previous.catalog_digest("memory_records") == prior_digest
        assert previous.lookup_digest(key) == prior_lookup
        expected = MaterializationAccumulator.from_sorted_rows(sorted(rows.items()))
        assert current.catalog_digest("memory_records") == expected.catalog_digest("memory_records")
        assert current.row_count == len(rows)


def test_arbitrary_encoded_keys_and_byte_boundaries_affect_the_commitment() -> None:
    empty = MaterializationAccumulator.empty()
    tree = MaterializationAccumulator.from_sorted_rows([(b"", b"x"), (b"\x00", b""), (b"x", b"\x00")])
    assert tree.lookup_digest(b"") == row_value_digest(b"x")
    assert tree.lookup_digest(b"\x00") == row_value_digest(b"")
    assert tree.catalog_digest("x") != empty.catalog_digest("x")
    assert tree.catalog_digest("x") != tree.upsert(b"x", b"").catalog_digest("x")
    assert tree.catalog_digest("x") != tree.delete(b"x").upsert(b"x\x00", b"").catalog_digest("x")
    assert tree.delete(b"x").delete(b"").delete(b"\x00").catalog_digest("x") == empty.catalog_digest("x")


def test_strict_key_order_digest_width_and_absent_delete() -> None:
    for rows in ([(b"z", b"first"), (b"a", b"second")], [(b"k", b"first"), (b"k", b"second")]):
        with pytest.raises(ValueError, match="strictly increasing"):
            MaterializationAccumulator.from_sorted_rows(rows)
    with pytest.raises(ValueError, match="digest length"):
        MaterializationAccumulator.from_sorted_digests([(b"key", b"invalid")])
    with pytest.raises(ValueError, match="digest length"):
        MaterializationAccumulator.empty().upsert_digest(b"key", b"invalid")
    with pytest.raises(KeyError):
        MaterializationAccumulator.empty().delete(b"key")
