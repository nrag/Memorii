from __future__ import annotations

import json

import pytest
from memorii.core.memory_evolution import typed_value_registry_compilation as compilation
from memorii.core.memory_evolution.typed_value_body_validation import (
    ProtectedTypedValueBodyLimits,
    TypedValueBodyValidationError,
    validate_typed_value_body,
)
from memorii.core.memory_evolution.typed_value_declarations import (
    ProtectedDeclarationParseLimits,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledTypedValueRegistry,
)

DECLARATION_LIMITS = ProtectedDeclarationParseLimits(50_000, 2_000, 80)
BODY_LIMITS = ProtectedTypedValueBodyLimits(50_000, 2_000, 80)


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _grammar() -> dict[str, object]:
    return {"role": "grammar", "profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "grammar_revision": "operational-3", "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"}, "envelope": {"binding_fields": ["profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"], "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"], "permitted_value_kinds": ["bytes", "integer", "map", "scalar"]}, "tags": {"bytes": "rfc4648_standard_padded", "datetime": "utc_six_fractional_digits", "duration_microseconds": "signed_i64", "enum": "registered_qualified_member", "frozenset": "canonical_member_byte_order", "integer": "canonical_decimal_string", "list": "declared_order", "map": "encoded_json_string_key_order", "set": "canonical_member_byte_order", "tuple": "declared_order"}, "type_rules": {"bool_as_integer": False, "defaults_before_verification": False, "float_decimal": False, "map_keys": "string_only", "model_fields": "registered_exact", "optional": "registered_policy", "union": "one_registered_discriminator"}}


def _roles(schema_id: str, fields: list[dict[str, object]], optional: list[dict[str, str]], numeric: list[dict[str, object]], enums: list[dict[str, object]]) -> list[bytes]:
    return [
        _raw({"role": "schema", "schema_id": schema_id, "schema_version": "1", "root_kind": "model", "fields": fields}),
        _raw({"role": "enum", "schema_id": schema_id, "schema_version": "1", "enums": enums}),
        _raw({"role": "optional", "schema_id": schema_id, "schema_version": "1", "fields": optional}),
        _raw({"role": "numeric", "schema_id": schema_id, "schema_version": "1", "fields": numeric}),
        _raw({"role": "digest-signature", "schema_id": schema_id, "schema_version": "1", "policy": {"kind": "ordinary"}}),
        _raw({"role": "decoder", "schema_id": schema_id, "schema_version": "1", "decoder_id": f"decode-{schema_id}", "typed_root_kind": "model", "implementation_source_digest": "a" * 64}),
        _raw({"role": "upcast", "schema_id": schema_id, "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None}),
    ]


def _registry() -> CompiledTypedValueRegistry:
    alt_fields = [{"name": "kind", "type": {"kind": "literal", "values": ["alt"]}, "integrity_role": "ordinary"}]
    fields = [
        {"name": "binary", "type": {"kind": "canonical_finite_binary64", "field_name": "binary"}, "integrity_role": "ordinary"},
        {"name": "bytes", "type": {"kind": "bytes", "lexical_rule": "rfc4648_standard_padded"}, "integrity_role": "ordinary"},
        {"name": "choice", "type": {"kind": "union", "discriminator": "kind", "alternatives": [{"discriminator_value": "alt", "model": {"kind": "model_ref", "schema_id": "Alt", "schema_version": "1"}}]}, "integrity_role": "ordinary"},
        {"name": "decimal", "type": {"kind": "canonical_decimal_quantity", "field_name": "decimal"}, "integrity_role": "ordinary"},
        {"name": "duration", "type": {"kind": "duration_microseconds", "lexical_rule": "signed_i64"}, "integrity_role": "ordinary"},
        {"name": "enum", "type": {"kind": "enum_ref", "qualified_id": "Colour"}, "integrity_role": "ordinary"},
        {"name": "integer", "type": {"kind": "integer", "lexical_rule": "canonical_decimal", "minimum": "-999999999999999999999999999999", "maximum": "999999999999999999999999999999"}, "integrity_role": "ordinary"},
        {"name": "items", "type": {"kind": "fixed_tuple", "items": [{"kind": "list", "element": {"kind": "string", "lexical_rule": "unicode_scalar"}}, {"kind": "set", "element": {"kind": "integer", "lexical_rule": "canonical_decimal", "minimum": None, "maximum": None}}, {"kind": "frozenset", "element": {"kind": "bool"}}, {"kind": "variadic_tuple", "element": {"kind": "null"}}]}, "integrity_role": "ordinary"},
        {"name": "mapping", "type": {"kind": "map", "key_kind": "string", "value": {"kind": "datetime", "lexical_rule": "utc_six_fractional_digits"}}, "integrity_role": "ordinary"},
        {"name": "maybe", "type": {"kind": "string", "lexical_rule": "nonempty_unicode_scalar"}, "integrity_role": "ordinary"},
    ]
    optional = [{"field_name": field["name"], "policy": "omittable_nullable" if field["name"] == "maybe" else "required"} for field in fields]
    numeric = [
        {"field_name": "binary", "representation": "canonical_finite_binary64", "encoding_spec_id": None, "unit": None, "scale": None, "lower": None, "lower_inclusive": None, "upper": None, "upper_inclusive": None, "reject_inexact": None},
        {"field_name": "decimal", "representation": "canonical_decimal_quantity", "encoding_spec_id": "example.quantity.v1", "unit": "", "scale": "2", "lower": "0.00", "lower_inclusive": True, "upper": "2.00", "upper_inclusive": True, "reject_inexact": True},
    ]
    sources = [_raw(_grammar()), *_roles("Root", fields, optional, numeric, [{"qualified_id": "Colour", "members": [{"member_id": "red", "wire_value": "red"}]}]), *_roles("Alt", alt_fields, [{"field_name": "kind", "policy": "required"}], [], []), *_roles("Sibling", [{"name": "value", "type": {"kind": "bool"}, "integrity_role": "ordinary"}], [{"field_name": "value", "policy": "required"}], [], [{"qualified_id": "Colour", "members": [{"member_id": "blue", "wire_value": "blue"}]}])]
    sources.append(compilation.author_typed_value_registry_role(sources, limits=DECLARATION_LIMITS))
    return compilation.compile_typed_value_registry(sources, limits=DECLARATION_LIMITS)


def _body() -> bytes:
    return _raw({"$type": "map", "entries": [["binary", {"$type": "map", "entries": [["ieee754_hex", "3ff0000000000000"]]}], ["bytes", {"$type": "bytes", "value": "AA=="}], ["choice", {"$type": "map", "entries": [["kind", "alt"]]}], ["decimal", {"$type": "map", "entries": [["encoding_spec_id", "example.quantity.v1"], ["fixed_scale_value", "1.25"]]}], ["duration", {"$type": "duration_microseconds", "value": "-1"}], ["enum", {"$type": "enum", "enum_type": "Colour", "member": "red"}], ["integer", {"$type": "integer", "value": "999999999999999999999999999999"}], ["items", {"$type": "tuple", "items": [{"$type": "list", "items": ["x"]}, {"$type": "set", "items": [{"$type": "integer", "value": "1"}, {"$type": "integer", "value": "2"}]}, {"$type": "frozenset", "items": [False, True]}, {"$type": "tuple", "items": [None]}]}], ["mapping", {"$type": "map", "entries": [["a", {"$type": "datetime", "value": "2026-09-07T12:34:56.000001Z"}]]}]]})


def _nullable_body() -> bytes:
    value = json.loads(_body())
    value["entries"].append(["maybe", None])
    return _raw(value)


def test_validates_every_type_family_and_returns_immutable_tree() -> None:
    registry = _registry()
    validated = validate_typed_value_body(_nullable_body(), registry=registry, entry=registry.entry_for("Root", "1"), limits=BODY_LIMITS)
    assert validated.raw_bytes == _nullable_body()
    assert validate_typed_value_body(_body().replace(b"2026-09-07T12:34:56.000001Z", b"0001-01-01T00:00:00.000000Z"), registry=registry, entry=registry.entry_for("Root", "1"), limits=BODY_LIMITS).raw_bytes
    with pytest.raises(TypeError):
        validated.tree["new"] = None  # type: ignore[index]


@pytest.mark.parametrize("mutate", [
    lambda body: body.replace(b'"AA=="', b'"AA"'),
    lambda body: body.replace(b'"member":"red"', b'"member":"blue"'),
    lambda body: body.replace(b'"value":"-1"', b'"value":"-0"'),
    lambda body: body.replace(b'"kind","alt"', b'"kind","other"'),
])
def test_rejects_adversarial_tag_enum_integer_and_union_forms(mutate: object) -> None:
    registry = _registry()
    with pytest.raises(TypedValueBodyValidationError):
        validate_typed_value_body(mutate(_body()), registry=registry, entry=registry.entry_for("Root", "1"), limits=BODY_LIMITS)  # type: ignore[operator]


def test_rejects_missing_required_field_and_protected_limits() -> None:
    registry = _registry()
    with pytest.raises(TypedValueBodyValidationError):
        validate_typed_value_body(_body().replace(b'"mapping"', b'"zzz"'), registry=registry, entry=registry.entry_for("Root", "1"), limits=BODY_LIMITS)
    with pytest.raises(TypedValueBodyValidationError):
        validate_typed_value_body(_body().replace(b'"AA=="', b"null"), registry=registry, entry=registry.entry_for("Root", "1"), limits=BODY_LIMITS)
    with pytest.raises(TypedValueBodyValidationError):
        validate_typed_value_body(_body(), registry=registry, entry=registry.entry_for("Root", "1"), limits=ProtectedTypedValueBodyLimits(10, 20, 5))
