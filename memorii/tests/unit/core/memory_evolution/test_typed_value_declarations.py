from __future__ import annotations

import json
from typing import cast

import pytest
from memorii.core.memory_evolution.typed_value_declarations import (
    DeclarationParseError,
    ProtectedDeclarationParseLimits,
    SchemaRole,
    parse_typed_value_declaration,
)

LIMITS = ProtectedDeclarationParseLimits(maximum_bytes=20_000, maximum_nodes=200, maximum_depth=20)


def _raw(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _schema() -> dict[str, object]:
    return {
        "role": "schema",
        "schema_id": "Example.v1",
        "schema_version": "1",
        "root_kind": "model",
        "fields": [
            {"name": "count", "type": {"kind": "integer", "lexical_rule": "canonical_decimal", "minimum": "0", "maximum": "9"}, "integrity_role": "ordinary"},
            {"name": "kind", "type": {"kind": "literal", "values": ["a", "b"]}, "integrity_role": "ordinary"},
        ],
    }


def test_parses_closed_schema_and_preserves_exact_bytes() -> None:
    raw = _raw(_schema())
    parsed = parse_typed_value_declaration(raw, limits=LIMITS)
    assert isinstance(parsed, SchemaRole)
    assert parsed.raw_bytes == raw
    assert parsed.fields[0].name == "count"


def test_rejects_unknown_field() -> None:
    value = _schema()
    value["extra"] = "x"
    with pytest.raises(DeclarationParseError, match="keys_invalid"):
        parse_typed_value_declaration(_raw(value), limits=LIMITS)


def test_rejects_unsorted_fields() -> None:
    value = _schema()
    value["fields"] = [
        {"name": "kind", "type": {"kind": "bool"}, "integrity_role": "ordinary"},
        {"name": "count", "type": {"kind": "bool"}, "integrity_role": "ordinary"},
    ]
    with pytest.raises(DeclarationParseError, match="not_unique_sorted"):
        parse_typed_value_declaration(_raw(value), limits=LIMITS)


def test_rejects_json_number_duplicate_key_and_noncanonical_bytes() -> None:
    number = b'{"fields":[],"role":"schema","root_kind":"model","schema_id":"X","schema_version":1}'
    duplicate = b'{"fields":[],"role":"schema","role":"schema","root_kind":"model","schema_id":"X","schema_version":"1"}'
    whitespace = b'{ "fields":[],"role":"schema","root_kind":"model","schema_id":"X","schema_version":"1"}'
    for raw in (number, duplicate, whitespace):
        with pytest.raises(DeclarationParseError):
            parse_typed_value_declaration(raw, limits=LIMITS)


def test_rejects_invalid_literal_integer_and_invalid_bounds() -> None:
    value = _schema()
    value["fields"] = [{"name": "kind", "type": {"kind": "literal", "values": [True, {"integer_value": True}]}, "integrity_role": "ordinary"}]
    with pytest.raises(DeclarationParseError, match="integer_invalid"):
        parse_typed_value_declaration(_raw(value), limits=LIMITS)


def test_compares_unbounded_canonical_integer_strings_without_python_conversion() -> None:
    large = "9" * 5_000
    value = _schema()
    value["fields"] = [{"name": "count", "type": {"kind": "integer", "lexical_rule": "canonical_decimal", "minimum": "-" + large, "maximum": large}, "integrity_role": "ordinary"}]
    assert parse_typed_value_declaration(_raw(value), limits=ProtectedDeclarationParseLimits(20_000, 200, 20)).role == "schema"
    value["fields"] = [{"name": "count", "type": {"kind": "integer", "lexical_rule": "canonical_decimal", "minimum": "-1", "maximum": "-2"}, "integrity_role": "ordinary"}]
    with pytest.raises(DeclarationParseError, match="bounds_invalid"):
        parse_typed_value_declaration(_raw(value), limits=LIMITS)
    value["fields"] = [{"name": "count", "type": {"kind": "integer", "lexical_rule": "canonical_decimal", "minimum": "9", "maximum": "0"}, "integrity_role": "ordinary"}]
    with pytest.raises(DeclarationParseError, match="bounds_invalid"):
        parse_typed_value_declaration(_raw(value), limits=LIMITS)


def test_parses_decoder_and_upcast_roles_and_rejects_non_null_upcast() -> None:
    digest = "a" * 64
    decoder = {"role": "decoder", "schema_id": "X", "schema_version": "1", "decoder_id": "decode-x", "typed_root_kind": "model", "implementation_source_digest": digest}
    assert parse_typed_value_declaration(_raw(decoder), limits=LIMITS).role == "decoder"
    upcast = {"role": "upcast", "schema_id": "X", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None}
    assert parse_typed_value_declaration(_raw(upcast), limits=LIMITS).role == "upcast"
    upcast["upcaster_id"] = "forbidden"
    with pytest.raises(DeclarationParseError, match="must_be_null"):
        parse_typed_value_declaration(_raw(upcast), limits=LIMITS)


def test_parses_remaining_role_forms_and_rejects_enum_aliases() -> None:
    digest = "a" * 64
    roles = [
        {"role": "enum", "schema_id": "X", "schema_version": "1", "enums": [{"qualified_id": "X.Kind", "members": [{"member_id": "a", "wire_value": "a"}]}]},
        {"role": "optional", "schema_id": "X", "schema_version": "1", "fields": []},
        {"role": "numeric", "schema_id": "X", "schema_version": "1", "fields": []},
        {"role": "digest-signature", "schema_id": "X", "schema_version": "1", "policy": {"kind": "ordinary"}},
        {"role": "registry", "profile": {"profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "grammar_revision": "operational-3", "grammar_digest": digest, "profile_digest": digest}, "entries": [digest]},
    ]
    assert [parse_typed_value_declaration(_raw(role), limits=LIMITS).role for role in roles] == ["enum", "optional", "numeric", "digest-signature", "registry"]
    alias = roles[0]
    alias["enums"] = [{"qualified_id": "X.Kind", "members": [{"member_id": "a", "wire_value": "same"}, {"member_id": "b", "wire_value": "same"}]}]
    with pytest.raises(DeclarationParseError, match="wire_values_duplicate"):
        parse_typed_value_declaration(_raw(alias), limits=LIMITS)


def test_numeric_fields_require_representation_specific_encoding_spec_id() -> None:
    decimal = {"role": "numeric", "schema_id": "X", "schema_version": "1", "fields": [{"field_name": "quantity", "representation": "canonical_decimal_quantity", "encoding_spec_id": "example.quantity.v1", "unit": "", "scale": "2", "lower": "0.00", "lower_inclusive": True, "upper": "1.00", "upper_inclusive": True, "reject_inexact": False}]}
    assert parse_typed_value_declaration(_raw(decimal), limits=LIMITS).role == "numeric"
    for replacement in ({}, {"encoding_spec_id": None}):
        value = json.loads(_raw(decimal))
        value["fields"][0].update(replacement)
        if not replacement:
            del value["fields"][0]["encoding_spec_id"]
        with pytest.raises(DeclarationParseError):
            parse_typed_value_declaration(_raw(value), limits=LIMITS)
    binary = {"role": "numeric", "schema_id": "X", "schema_version": "1", "fields": [{"field_name": "ratio", "representation": "canonical_finite_binary64", "encoding_spec_id": None, "unit": None, "scale": None, "lower": None, "lower_inclusive": None, "upper": None, "upper_inclusive": None, "reject_inexact": None}]}
    assert parse_typed_value_declaration(_raw(binary), limits=LIMITS).role == "numeric"


def test_enforces_protected_byte_node_and_depth_limits_before_recursive_type_parse() -> None:
    raw = _raw(_schema())
    with pytest.raises(DeclarationParseError, match="bytes_limit"):
        parse_typed_value_declaration(raw, limits=ProtectedDeclarationParseLimits(1, 200, 20))
    with pytest.raises(DeclarationParseError, match="nodes_limit"):
        parse_typed_value_declaration(raw, limits=ProtectedDeclarationParseLimits(20_000, 1, 20))
    noncanonical = b'{ "fields":[],"role":"schema","root_kind":"model","schema_id":"X","schema_version":"1"}'
    with pytest.raises(DeclarationParseError, match="nodes_limit"):
        parse_typed_value_declaration(noncanonical, limits=ProtectedDeclarationParseLimits(20_000, 1, 20))
    nested = b"[" * 30 + b"null" + b"]" * 30
    with pytest.raises(DeclarationParseError, match="depth_limit"):
        parse_typed_value_declaration(nested, limits=ProtectedDeclarationParseLimits(20_000, 200, 5))


@pytest.mark.parametrize("invalid", [True, 1.5, 0])
def test_requires_exact_positive_integer_protected_limits(invalid: object) -> None:
    with pytest.raises(ValueError, match="limits_must_be_positive"):
        ProtectedDeclarationParseLimits(cast(int, invalid), 2, 2)


def test_rejects_mutable_bytearray_input_before_ir_construction() -> None:
    with pytest.raises(DeclarationParseError, match="raw_bytes_required"):
        parse_typed_value_declaration(cast(bytes, bytearray(_raw(_schema()))), limits=LIMITS)
