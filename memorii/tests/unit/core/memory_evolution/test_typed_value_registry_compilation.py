from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256

import pytest
from memorii.core.memory_evolution import typed_value_registry_compilation as compilation
from memorii.core.memory_evolution.typed_value_declarations import (
    GrammarRole,
    ProtectedDeclarationParseLimits,
    parse_typed_value_declaration,
)

LIMITS = ProtectedDeclarationParseLimits(20_000, 300, 30)


def _raw(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _grammar() -> dict[str, object]:
    return {"role": "grammar", "profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "grammar_revision": "operational-3", "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"}, "envelope": {"binding_fields": ["profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"], "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"], "permitted_value_kinds": ["bytes", "integer", "map", "scalar"]}, "tags": {"bytes": "rfc4648_standard_padded", "datetime": "utc_six_fractional_digits", "duration_microseconds": "signed_i64", "enum": "registered_qualified_member", "frozenset": "canonical_member_byte_order", "integer": "canonical_decimal_string", "list": "declared_order", "map": "encoded_json_string_key_order", "set": "canonical_member_byte_order", "tuple": "declared_order"}, "type_rules": {"bool_as_integer": False, "defaults_before_verification": False, "float_decimal": False, "map_keys": "string_only", "model_fields": "registered_exact", "optional": "registered_policy", "union": "one_registered_discriminator"}}


def _sources() -> list[bytes]:
    digest = "a" * 64
    return [_raw(_grammar()), _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "bool"}, "integrity_role": "ordinary"}]}), _raw({"role": "enum", "schema_id": "X", "schema_version": "1", "enums": []}), _raw({"role": "optional", "schema_id": "X", "schema_version": "1", "fields": [{"field_name": "value", "policy": "required"}]}), _raw({"role": "numeric", "schema_id": "X", "schema_version": "1", "fields": []}), _raw({"role": "digest-signature", "schema_id": "X", "schema_version": "1", "policy": {"kind": "ordinary"}}), _raw({"role": "decoder", "schema_id": "X", "schema_version": "1", "decoder_id": "decode-x", "typed_root_kind": "model", "implementation_source_digest": digest}), _raw({"role": "upcast", "schema_id": "X", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None})]


def _complete_sources() -> list[bytes]:
    return _with_registry(_sources())


def _with_registry(sources: list[bytes]) -> list[bytes]:
    return [*sources, compilation.author_typed_value_registry_role(sources, limits=LIMITS)]


def _registry_stub(sources: list[bytes]) -> list[bytes]:
    grammar = parse_typed_value_declaration(sources[0], limits=LIMITS)
    assert isinstance(grammar, GrammarRole)
    profile = compilation._compile_profile(grammar.raw_bytes, grammar.profile_id, grammar.profile_version, grammar.grammar_revision)
    return [*sources, _raw({"role": "registry", "profile": {"profile_id": profile.profile_id, "profile_version": profile.profile_version, "grammar_revision": profile.grammar_revision, "grammar_digest": profile.grammar_digest, "profile_digest": profile.profile_digest}, "entries": []})]


def _schema_roles(schema_id: str, fields: list[dict[str, object]], policy: Mapping[str, object], decoder_digest: str) -> list[bytes]:
    return [
        _raw({"role": "schema", "schema_id": schema_id, "schema_version": "1", "root_kind": "model", "fields": fields}),
        _raw({"role": "enum", "schema_id": schema_id, "schema_version": "1", "enums": []}),
        _raw({"role": "optional", "schema_id": schema_id, "schema_version": "1", "fields": [{"field_name": field["name"], "policy": "required"} for field in fields]}),
        _raw({"role": "numeric", "schema_id": schema_id, "schema_version": "1", "fields": []}),
        _raw({"role": "digest-signature", "schema_id": schema_id, "schema_version": "1", "policy": policy}),
        _raw({"role": "decoder", "schema_id": schema_id, "schema_version": "1", "decoder_id": f"decode-{schema_id}", "typed_root_kind": "model", "implementation_source_digest": decoder_digest}),
        _raw({"role": "upcast", "schema_id": schema_id, "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None}),
    ]


def _checkpoint_role_sources() -> list[bytes]:
    checkpoint_fields = [
        {"name": "body", "type": {"kind": "bool"}, "integrity_role": "ordinary"},
        {"name": "checkpoint_digest", "type": {"kind": "string", "lexical_rule": "sha256"}, "integrity_role": "self_digest"},
        {"name": "signature", "type": {"kind": "string", "lexical_rule": "signature_hex128"}, "integrity_role": "signature"},
    ]
    checkpoint_policy = {
        "kind": "external_signing_preimage",
        "result_digest_field": "checkpoint_digest",
        "result_signature_field": "signature",
        "preimage_schema_id": "ObservationCheckpointSigningPreimage",
        "preimage_schema_version": "1",
        "binding_kind": "observation_checkpoint_v1",
        "signature_purpose": "observation_checkpoint",
        "signature_domain": "checkpoint-domain",
    }
    preimage_fields = [
        {"name": "body", "type": {"kind": "bool"}, "integrity_role": "ordinary"},
        {"name": "purpose", "type": {"kind": "literal", "values": ["observation_checkpoint"]}, "integrity_role": "ordinary"},
    ]
    return [
        _raw(_grammar()),
        *_schema_roles("IngestionObservationReplayCheckpoint", checkpoint_fields, checkpoint_policy, "c" * 64),
        *_schema_roles("ObservationCheckpointSigningPreimage", preimage_fields, {"kind": "ordinary"}, "d" * 64),
    ]


_CHECKPOINT_REGISTRY = {
    "role": "registry",
    "profile": {
        "profile_id": "semantic_ingestion_typed_value",
        "profile_version": "3",
        "grammar_revision": "operational-3",
        "grammar_digest": "960df37a00b887f009941cc3ada0a5b84276de6af626bced51dc7747e890b822",
        "profile_digest": "a6da0b15af67134cf5199b4d925e6d3c225ff1c239c6e1c9d039753b5342ebe0",
    },
    "entries": [
        "7f43d4516d9d34b2be4e6981e6eda78ac14cc219bca1de80cfc5820670588609",
        "308b16f9874fb3306e1f31593076719372c7f1212f35981880f5d457be94cdf5",
    ],
}


def _checkpoint_sources() -> list[bytes]:
    # This is a closure-only fixture, not the complete production checkpoint schema.
    return [*_checkpoint_role_sources(), _raw(_CHECKPOINT_REGISTRY)]


def _decimal_sources() -> list[bytes]:
    sources = _sources()
    sources[1] = _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "canonical_decimal_quantity", "field_name": "value"}, "integrity_role": "ordinary"}]})
    sources[4] = _raw({"role": "numeric", "schema_id": "X", "schema_version": "1", "fields": [{"field_name": "value", "representation": "canonical_decimal_quantity", "encoding_spec_id": "example.quantity.v1", "unit": "", "scale": "2", "lower": "-1.25", "lower_inclusive": True, "upper": "0.00", "upper_inclusive": False, "reject_inexact": False}]})
    return sources


def _integrity_policy_sources(field: dict[str, object], policy: Mapping[str, object]) -> list[bytes]:
    sources = _sources()
    sources[1] = _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [field]})
    sources[3] = _raw({"role": "optional", "schema_id": "X", "schema_version": "1", "fields": [{"field_name": field["name"], "policy": "required"}]})
    sources[5] = _raw({"role": "digest-signature", "schema_id": "X", "schema_version": "1", "policy": policy})
    return sources


def test_compiles_reparsed_complete_sources_with_active_entry() -> None:
    registry = compilation.compile_typed_value_registry(_complete_sources(), limits=LIMITS)
    assert registry.entries[0].read_status == "active"
    assert registry.entries[0].decoder_id == "decode-x"
    assert registry.entries[0].implementation_source_digest == "a" * 64


def test_authors_canonical_registry_role_that_round_trips_through_compilation() -> None:
    sources = _sources()
    authored = compilation.author_typed_value_registry_role(sources, limits=LIMITS)
    parsed = parse_typed_value_declaration(authored, limits=LIMITS)
    assert isinstance(parsed, compilation.RegistryRole)
    assert authored == compilation.author_typed_value_registry_role(reversed(sources), limits=LIMITS)
    registry = compilation.compile_typed_value_registry([*sources, authored], limits=LIMITS)
    assert tuple(registry.entries[index].entry_digest for index in range(len(registry.entries))) == parsed.entries


def test_author_rejects_invalid_role_families_and_supplied_registry_roles() -> None:
    incomplete = _sources()
    incomplete.pop()
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="role_set_incomplete"):
        compilation.author_typed_value_registry_role(incomplete, limits=LIMITS)
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="registry_role_supplied_to_author"):
        compilation.author_typed_value_registry_role(_complete_sources(), limits=LIMITS)


def test_rejects_incomplete_policy_role_set_before_registry_build() -> None:
    sources = _complete_sources()
    sources.pop(4)
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="role_set_incomplete"):
        compilation.compile_typed_value_registry(sources, limits=LIMITS)


def test_rejects_duplicate_roles_and_cross_role_closure_violations() -> None:
    duplicate = _complete_sources()
    duplicate.append(duplicate[1])
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="coordinate_duplicate"):
        compilation.compile_typed_value_registry(duplicate, limits=LIMITS)
    optional_missing = _complete_sources()
    optional_missing[3] = _raw({"role": "optional", "schema_id": "X", "schema_version": "1", "fields": []})
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="optional_field_closure"):
        compilation.compile_typed_value_registry(optional_missing, limits=LIMITS)
    unresolved_enum = _complete_sources()
    unresolved_enum[1] = _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "enum_ref", "qualified_id": "Missing"}, "integrity_role": "ordinary"}]})
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="enum_reference_unresolved"):
        compilation.compile_typed_value_registry(unresolved_enum, limits=LIMITS)


def test_rejects_wrong_or_nested_numeric_wrapper_ownership() -> None:
    for type_expression in ({"kind": "canonical_decimal_quantity", "field_name": "other"}, {"kind": "list", "element": {"kind": "canonical_decimal_quantity", "field_name": "value"}}):
        sources = _complete_sources()
        sources[1] = _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": type_expression, "integrity_role": "ordinary"}]})
        with pytest.raises(compilation.TypedValueRegistryCompilationError, match="numeric_field_closure"):
            compilation.compile_typed_value_registry(sources, limits=LIMITS)


def test_uses_independent_lp_bytes_and_distinct_entry_and_closure_version_orders() -> None:
    independent_lp = (1).to_bytes(8, "big") + b"a" + (2).to_bytes(8, "big") + b"bc"
    assert compilation._digest(b"a", b"bc") == sha256(independent_lp).hexdigest()
    coordinates = [("X", "2"), ("X", "10")]
    assert sorted(coordinates, key=compilation._entry_coordinate_sort_key) == [("X", "10"), ("X", "2")]
    assert sorted(coordinates, key=compilation._closure_coordinate_sort_key) == [("X", "2"), ("X", "10")]


def test_rejects_unresolved_and_cyclic_model_references() -> None:
    unresolved = _complete_sources()
    unresolved[1] = _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "model_ref", "schema_id": "Missing", "schema_version": "1"}, "integrity_role": "ordinary"}]})
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="dependency_unresolved"):
        compilation.compile_typed_value_registry(unresolved, limits=LIMITS)
    cyclic = _sources()
    cyclic[1] = _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "model_ref", "schema_id": "Y", "schema_version": "1"}, "integrity_role": "ordinary"}]})
    cyclic.extend([_raw({"role": "schema", "schema_id": "Y", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "model_ref", "schema_id": "X", "schema_version": "1"}, "integrity_role": "ordinary"}]}), _raw({"role": "enum", "schema_id": "Y", "schema_version": "1", "enums": []}), _raw({"role": "optional", "schema_id": "Y", "schema_version": "1", "fields": [{"field_name": "value", "policy": "required"}]}), _raw({"role": "numeric", "schema_id": "Y", "schema_version": "1", "fields": []}), _raw({"role": "digest-signature", "schema_id": "Y", "schema_version": "1", "policy": {"kind": "ordinary"}}), _raw({"role": "decoder", "schema_id": "Y", "schema_version": "1", "decoder_id": "decode-y", "typed_root_kind": "model", "implementation_source_digest": "b" * 64}), _raw({"role": "upcast", "schema_id": "Y", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None})])
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="dependency_cycle"):
        compilation.compile_typed_value_registry(_registry_stub(cyclic), limits=LIMITS)


def test_enforces_union_discriminator_literal_closure() -> None:
    sources = _sources()
    sources[1] = _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "union", "discriminator": "kind", "alternatives": [{"discriminator_value": "y", "model": {"kind": "model_ref", "schema_id": "Y", "schema_version": "1"}}]}, "integrity_role": "ordinary"}]})
    sources.extend([_raw({"role": "schema", "schema_id": "Y", "schema_version": "1", "root_kind": "model", "fields": [{"name": "kind", "type": {"kind": "literal", "values": ["y"]}, "integrity_role": "ordinary"}]}), _raw({"role": "enum", "schema_id": "Y", "schema_version": "1", "enums": []}), _raw({"role": "optional", "schema_id": "Y", "schema_version": "1", "fields": [{"field_name": "kind", "policy": "required"}]}), _raw({"role": "numeric", "schema_id": "Y", "schema_version": "1", "fields": []}), _raw({"role": "digest-signature", "schema_id": "Y", "schema_version": "1", "policy": {"kind": "ordinary"}}), _raw({"role": "decoder", "schema_id": "Y", "schema_version": "1", "decoder_id": "decode-y", "typed_root_kind": "model", "implementation_source_digest": "b" * 64}), _raw({"role": "upcast", "schema_id": "Y", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None})])
    assert len(compilation.compile_typed_value_registry(_with_registry(sources), limits=LIMITS).entries) == 2
    sources[8] = _raw({"role": "schema", "schema_id": "Y", "schema_version": "1", "root_kind": "model", "fields": [{"name": "kind", "type": {"kind": "literal", "values": ["wrong"]}, "integrity_role": "ordinary"}]})
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="union_discriminator"):
        compilation.compile_typed_value_registry(_registry_stub(sources), limits=LIMITS)


def test_compiles_checkpoint_external_signing_preimage_with_static_registry_commitment() -> None:
    registry = compilation.compile_typed_value_registry(_checkpoint_sources(), limits=LIMITS)
    checkpoint = registry.entry_for("IngestionObservationReplayCheckpoint", "1")
    preimage = registry.entry_for("ObservationCheckpointSigningPreimage", "1")
    assert checkpoint.read_status == preimage.read_status == "active"
    assert checkpoint.policy_digests.digest_signature_field_policy_digest != preimage.policy_digests.digest_signature_field_policy_digest
    assert tuple(entry.entry_digest for entry in registry.entries) == tuple(_CHECKPOINT_REGISTRY["entries"])


@pytest.mark.parametrize(
    ("field", "policy"),
    [
        (
            {"name": "digest", "type": {"kind": "string", "lexical_rule": "sha256"}, "integrity_role": "self_digest"},
            {"kind": "self_digest", "digest_field": "digest", "digest_domain": "digest-domain"},
        ),
        (
            {"name": "signature", "type": {"kind": "string", "lexical_rule": "signature_hex128"}, "integrity_role": "signature"},
            {"kind": "signature_only", "signature_field": "signature", "signature_purpose": "purpose", "signature_domain": "signature-domain"},
        ),
    ],
)
def test_compiles_self_digest_and_signature_only_with_canonical_integrity_types(field: dict[str, object], policy: dict[str, object]) -> None:
    assert compilation.compile_typed_value_registry(_with_registry(_integrity_policy_sources(field, policy)), limits=LIMITS).entries[0].read_status == "active"


@pytest.mark.parametrize(
    "invalid_type",
    [
        {"kind": "bytes", "lexical_rule": "rfc4648_standard_padded"},
        {"kind": "bool"},
        {"kind": "string", "lexical_rule": "unicode_scalar"},
    ],
)
def test_rejects_noncanonical_self_digest_and_signature_integrity_types(invalid_type: dict[str, str]) -> None:
    cases = [
        (
            {"name": "digest", "type": invalid_type, "integrity_role": "self_digest"},
            {"kind": "self_digest", "digest_field": "digest", "digest_domain": "digest-domain"},
        ),
        (
            {"name": "signature", "type": invalid_type, "integrity_role": "signature"},
            {"kind": "signature_only", "signature_field": "signature", "signature_purpose": "purpose", "signature_domain": "signature-domain"},
        ),
    ]
    for field, policy in cases:
        with pytest.raises(compilation.TypedValueRegistryCompilationError, match="digest_signature_policy_closure"):
            compilation.compile_typed_value_registry(_registry_stub(_integrity_policy_sources(field, policy)), limits=LIMITS)


@pytest.mark.parametrize("field_name", ["checkpoint_digest", "signature"])
@pytest.mark.parametrize(
    "invalid_type",
    [
        {"kind": "bytes", "lexical_rule": "rfc4648_standard_padded"},
        {"kind": "bool"},
        {"kind": "string", "lexical_rule": "unicode_scalar"},
    ],
)
def test_rejects_noncanonical_external_checkpoint_integrity_types(field_name: str, invalid_type: dict[str, str]) -> None:
    sources = _checkpoint_sources()
    schema = json.loads(sources[1])
    next(field for field in schema["fields"] if field["name"] == field_name)["type"] = invalid_type
    sources[1] = _raw(schema)
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="digest_signature_policy_closure"):
        compilation.compile_typed_value_registry(sources, limits=LIMITS)


def test_rejects_external_signing_preimage_wrong_owner_and_missing_integrity_fields() -> None:
    wrong_owner = _sources()
    wrong_owner[5] = _raw({"role": "digest-signature", "schema_id": "X", "schema_version": "1", "policy": {"kind": "external_signing_preimage", "result_digest_field": "checkpoint_digest", "result_signature_field": "signature", "preimage_schema_id": "ObservationCheckpointSigningPreimage", "preimage_schema_version": "1", "binding_kind": "observation_checkpoint_v1", "signature_purpose": "observation_checkpoint", "signature_domain": "checkpoint-domain"}})
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="digest_signature_policy_closure"):
        compilation.compile_typed_value_registry(_registry_stub(wrong_owner), limits=LIMITS)

    missing = _checkpoint_sources()
    policy = json.loads(missing[5])
    policy["policy"]["result_digest_field"] = "missing"
    missing[5] = _raw(policy)
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="digest_signature_policy_closure"):
        compilation.compile_typed_value_registry(missing, limits=LIMITS)


def test_rejects_duplicate_checkpoint_integrity_role() -> None:
    sources = _checkpoint_sources()
    schema = json.loads(sources[1])
    schema["fields"].append({"name": "other_digest", "type": {"kind": "string", "lexical_rule": "sha256"}, "integrity_role": "self_digest"})
    schema["fields"].sort(key=lambda field: field["name"])
    sources[1] = _raw(schema)
    optional = json.loads(sources[3])
    optional["fields"].append({"field_name": "other_digest", "policy": "required"})
    optional["fields"].sort(key=lambda field: field["field_name"])
    sources[3] = _raw(optional)
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="digest_signature_policy_closure"):
        compilation.compile_typed_value_registry(sources, limits=LIMITS)


def test_rejects_nonordinary_and_cyclic_external_preimage_references() -> None:
    nonordinary = _checkpoint_sources()
    preimage_schema = json.loads(nonordinary[8])
    preimage_schema["fields"].append({"name": "signature", "type": {"kind": "string", "lexical_rule": "signature_hex128"}, "integrity_role": "signature"})
    nonordinary[8] = _raw(preimage_schema)
    preimage_optional = json.loads(nonordinary[10])
    preimage_optional["fields"].append({"field_name": "signature", "policy": "required"})
    preimage_optional["fields"].sort(key=lambda field: field["field_name"])
    nonordinary[10] = _raw(preimage_optional)
    nonordinary[12] = _raw({"role": "digest-signature", "schema_id": "ObservationCheckpointSigningPreimage", "schema_version": "1", "policy": {"kind": "signature_only", "signature_field": "signature", "signature_purpose": "observation_checkpoint", "signature_domain": "checkpoint-domain"}})
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="external_preimage_policy_invalid"):
        compilation.compile_typed_value_registry(nonordinary, limits=LIMITS)

    cyclic = _checkpoint_sources()
    preimage_schema = json.loads(cyclic[8])
    preimage_schema["fields"][0] = {"name": "body", "type": {"kind": "model_ref", "schema_id": "IngestionObservationReplayCheckpoint", "schema_version": "1"}, "integrity_role": "ordinary"}
    cyclic[8] = _raw(preimage_schema)
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="dependency_cycle"):
        compilation.compile_typed_value_registry(cyclic, limits=LIMITS)


def test_rejects_unresolved_external_preimage_reference() -> None:
    unresolved = _checkpoint_role_sources()[:8]
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="dependency_unresolved"):
        compilation.compile_typed_value_registry(_registry_stub(unresolved), limits=LIMITS)


@pytest.mark.parametrize("bound", ["1", "01.00", "1.0", "1.000", "+1.00", "1e0.00", "-0.00"])
def test_rejects_noncanonical_decimal_numeric_bounds(bound: str) -> None:
    sources = _decimal_sources()
    numeric = json.loads(sources[4])
    numeric["fields"][0]["lower"] = bound
    sources[4] = _raw(numeric)
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="numeric_decimal_bound_lexical"):
        compilation.compile_typed_value_registry(_registry_stub(sources), limits=LIMITS)


def test_accepts_empty_unit_and_false_reject_inexact_with_exact_decimal_bounds() -> None:
    assert compilation.compile_typed_value_registry(_with_registry(_decimal_sources()), limits=LIMITS).entries[0].schema_id == "X"


def test_rejects_duplicate_decimal_encoding_spec_id_across_schema_rows() -> None:
    sources = _decimal_sources()
    sources.extend(_schema_roles("Y", [{"name": "value", "type": {"kind": "canonical_decimal_quantity", "field_name": "value"}, "integrity_role": "ordinary"}], {"kind": "ordinary"}, "b" * 64))
    sources[-4] = _raw({"role": "numeric", "schema_id": "Y", "schema_version": "1", "fields": [{"field_name": "value", "representation": "canonical_decimal_quantity", "encoding_spec_id": "example.quantity.v1", "unit": "", "scale": "2", "lower": "0.00", "lower_inclusive": True, "upper": "1.00", "upper_inclusive": True, "reject_inexact": False}]})
    with pytest.raises(compilation.TypedValueRegistryCompilationError, match="encoding_spec_id_duplicate"):
        compilation.compile_typed_value_registry(_registry_stub(sources), limits=LIMITS)


def test_decimal_encoding_spec_id_mutation_changes_compiled_commitment_chain() -> None:
    baseline = compilation.compile_typed_value_registry(_with_registry(_decimal_sources()), limits=LIMITS)
    changed_sources = _decimal_sources()
    numeric = json.loads(changed_sources[4])
    numeric["fields"][0]["encoding_spec_id"] = "example.quantity.v2"
    changed_sources[4] = _raw(numeric)
    changed = compilation.compile_typed_value_registry(_with_registry(changed_sources), limits=LIMITS)
    assert changed.entries[0].policy_digests.numeric_encoding_spec_registry_digest != baseline.entries[0].policy_digests.numeric_encoding_spec_registry_digest
    assert changed.entries[0].binding_digest != baseline.entries[0].binding_digest
    assert changed.entries[0].entry_digest != baseline.entries[0].entry_digest
    assert changed.registry_digest != baseline.registry_digest
