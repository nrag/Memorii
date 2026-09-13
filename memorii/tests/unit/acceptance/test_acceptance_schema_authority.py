from __future__ import annotations

from datetime import UTC, datetime

import pytest
from acceptance.ctv import NumericCtvError, encode_typed_value
from acceptance.schema_registry import canonical_digest, canonical_profile_binding_bytes, load_manifest, load_registry


def test_registered_authority_manifest_matches_complete_registry() -> None:
    registry = load_registry()
    manifest = load_manifest()
    assert len(registry["schemas"]) == 9
    assert [row["id"] for row in manifest["schemas"]] == [row["id"] for row in registry["schemas"]]


def test_acceptance_ctv_orders_unicode_maps_and_binds_profile_digest() -> None:
    value = {"z": 1, "ä": b"x", "at": datetime(2026, 9, 12, tzinfo=UTC)}
    assert encode_typed_value(value).startswith(b'{"$type":"map"')
    assert canonical_digest("memorii.acceptance.test.v1", "memorii.acceptance.canonical-map.v1", value) == canonical_digest(
        "memorii.acceptance.test.v1", "memorii.acceptance.canonical-map.v1", value
    )
    with pytest.raises(NumericCtvError, match="timestamp"):
        encode_typed_value(datetime(2026, 9, 12))


def test_registered_digest_binds_complete_profile_not_only_its_identifier() -> None:
    assert canonical_profile_binding_bytes().startswith(b'{"$type":"map"')
    assert canonical_digest("memorii.acceptance.test.v1", "registered", {"a": 1}) != canonical_digest(
        "memorii.acceptance.test.v1", "memorii.acceptance.canonical-map.v1", {"a": 1}
    )
