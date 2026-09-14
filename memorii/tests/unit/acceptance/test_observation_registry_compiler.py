from __future__ import annotations

import hashlib
import json
import os
import struct
from dataclasses import replace
from pathlib import Path

import pytest
from acceptance.observation_registry_compiler import (
    RegistrySourceError,
    SourceLimits,
    compile_observation_registry,
    derive_observation_registry,
)
from acceptance.observation_registry_vectors import RegistryRejectionVector, build_rejection_vectors


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _lp(*parts: str | bytes) -> bytes:
    return b"".join(
        struct.pack(">Q", len(part.encode("utf-8") if isinstance(part, str) else part))
        + (part.encode("utf-8") if isinstance(part, str) else part)
        for part in parts
    )


def _roles() -> list[tuple[str, bytes]]:
    grammar = _raw(
        {
            "envelope": {
                "binding_fields": [
                    "profile_id",
                    "profile_version",
                    "profile_digest",
                    "schema_id",
                    "schema_version",
                    "binding_digest",
                ],
                "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"],
                "permitted_value_kinds": ["bytes", "integer", "map", "scalar"],
            },
            "grammar_revision": "operational-3",
            "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"},
            "profile_id": "semantic_ingestion_typed_value",
            "profile_version": "3",
            "role": "grammar",
            "tags": {
                "bytes": "rfc4648_standard_padded",
                "datetime": "utc_six_fractional_digits",
                "duration_microseconds": "signed_i64",
                "enum": "registered_qualified_member",
                "frozenset": "canonical_member_byte_order",
                "integer": "canonical_decimal_string",
                "list": "declared_order",
                "map": "encoded_json_string_key_order",
                "set": "canonical_member_byte_order",
                "tuple": "declared_order",
            },
            "type_rules": {
                "bool_as_integer": False,
                "defaults_before_verification": False,
                "float_decimal": False,
                "map_keys": "string_only",
                "model_fields": "registered_exact",
                "optional": "registered_policy",
                "union": "one_registered_discriminator",
            },
        }
    )
    root = "ExampleRoot"
    version = "1"
    digest = "a" * 64
    return [
        ("grammar", grammar),
        (
            f"schema/{root}/{version}",
            _raw(
                {
                    "fields": [
                        {
                            "integrity_role": "ordinary",
                            "name": "value",
                            "type": {"kind": "string", "lexical_rule": "nonempty_unicode_scalar"},
                        }
                    ],
                    "role": "schema",
                    "root_kind": "model",
                    "schema_id": root,
                    "schema_version": version,
                }
            ),
        ),
        (f"enum/{root}/{version}", _raw({"enums": [], "role": "enum", "schema_id": root, "schema_version": version})),
        (
            f"optional/{root}/{version}",
            _raw(
                {
                    "fields": [{"field_name": "value", "policy": "required"}],
                    "role": "optional",
                    "schema_id": root,
                    "schema_version": version,
                }
            ),
        ),
        (
            f"numeric/{root}/{version}",
            _raw({"fields": [], "role": "numeric", "schema_id": root, "schema_version": version}),
        ),
        (
            f"digest-signature/{root}/{version}",
            _raw(
                {
                    "policy": {"kind": "ordinary"},
                    "role": "digest-signature",
                    "schema_id": root,
                    "schema_version": version,
                }
            ),
        ),
        (
            f"decoder/{root}/{version}",
            _raw(
                {
                    "decoder_id": "example.decoder",
                    "implementation_source_digest": digest,
                    "role": "decoder",
                    "schema_id": root,
                    "schema_version": version,
                    "typed_root_kind": "model",
                }
            ),
        ),
        (
            f"upcast/{root}/{version}",
            _raw(
                {
                    "implementation_source_digest": None,
                    "role": "upcast",
                    "schema_id": root,
                    "schema_version": version,
                    "target_binding": None,
                    "upcaster_id": None,
                }
            ),
        ),
    ]


def _complete_roles(roles: list[tuple[str, bytes]] | None = None) -> list[tuple[str, bytes]]:
    roles = _roles() if roles is None else roles
    derived = derive_observation_registry(roles)
    return roles + [
        (
            "registry",
            _raw(
                {
                    "entries": [derived.entries[0].entry_digest],
                    "profile": {
                        "grammar_digest": hashlib.sha256(roles[0][1]).hexdigest(),
                        "grammar_revision": "operational-3",
                        "profile_digest": derived.profile_digest,
                        "profile_id": "semantic_ingestion_typed_value",
                        "profile_version": "3",
                    },
                    "role": "registry",
                }
            ),
        )
    ]


def _decimal_roles(
    *,
    field_name: str = "value",
    representation: str = "canonical_decimal_quantity",
    lower: str = "0.00",
    upper: str = "2.00",
    scale: str | None = "2",
) -> list[tuple[str, bytes]]:
    roles = _roles()
    schema = json.loads(roles[1][1])
    schema["fields"][0]["type"] = {"field_name": field_name, "kind": "canonical_decimal_quantity"}
    roles[1] = (roles[1][0], _raw(schema))
    if representation == "canonical_decimal_quantity":
        row = {
            "encoding_spec_id": "example.quantity.v1",
            "field_name": "value",
            "lower": lower,
            "lower_inclusive": True,
            "reject_inexact": True,
            "representation": representation,
            "scale": scale,
            "unit": "units",
            "upper": upper,
            "upper_inclusive": True,
        }
    else:
        row = {
            "encoding_spec_id": None,
            "field_name": "value",
            "lower": None,
            "lower_inclusive": None,
            "reject_inexact": None,
            "representation": representation,
            "scale": None,
            "unit": None,
            "upper": None,
            "upper_inclusive": None,
        }
    roles[4] = (
        roles[4][0],
        _raw({"fields": [row], "role": "numeric", "schema_id": "ExampleRoot", "schema_version": "1"}),
    )
    return roles


def test_compiles_complete_role_set_and_returns_full_preimages() -> None:
    roles = _complete_roles()

    report = compile_observation_registry(roles)

    assert report.entries[0].entry_preimage == _lp(
        "semantic-ingestion-typed-value-registry-entry",
        "semantic_ingestion_typed_value",
        "3",
        report.profile_digest,
        "ExampleRoot",
        "1",
        report.entries[0].binding_digest,
        report.entries[0].schema_fingerprint,
        report.entries[0].enum_registry_digest,
        report.entries[0].optional_field_policy_digest,
        report.entries[0].numeric_encoding_spec_registry_digest,
        report.entries[0].digest_signature_field_policy_digest,
        report.entries[0].decoder_digest,
        "0",
        b"",
        b"",
        "active",
    )
    assert report.source_identities[0].raw_bytes
    assert report.registry_preimage.endswith(report.entries[0].entry_digest.encode("ascii"))


def test_rejects_missing_required_role_before_registry_derivation() -> None:
    roles = [item for item in _roles() if not item[0].startswith("upcast/")]

    with pytest.raises(RegistrySourceError, match="every schema requires"):
        compile_observation_registry(roles)


def test_complete_compile_requires_registry_role() -> None:
    with pytest.raises(RegistrySourceError, match="requires exactly one registry"):
        compile_observation_registry(_roles())


def test_rejects_changed_grammar_even_when_declarations_are_rederived() -> None:
    roles = _roles()
    grammar = json.loads(roles[0][1])
    grammar["tags"]["map"] = "wrong"
    roles[0] = ("grammar", _raw(grammar))

    with pytest.raises(RegistrySourceError, match="complete approved literal"):
        derive_observation_registry(roles)


def test_rejects_extra_optional_row() -> None:
    roles = _roles()
    optional = json.loads(roles[3][1])
    optional["fields"].append({"field_name": "extra", "policy": "required"})
    roles[3] = (roles[3][0], _raw(optional))

    with pytest.raises(RegistrySourceError, match="optional fields"):
        derive_observation_registry(roles)


def test_enforces_protected_source_limits() -> None:
    with pytest.raises(RegistrySourceError, match="raw-byte limit"):
        derive_observation_registry(
            _roles(), limits=SourceLimits(max_raw_bytes=12, max_json_nodes=100, max_json_depth=10)
        )
    with pytest.raises(RegistrySourceError, match="node limit"):
        derive_observation_registry(
            _roles(), limits=SourceLimits(max_raw_bytes=100_000, max_json_nodes=1, max_json_depth=100)
        )
    with pytest.raises(RegistrySourceError, match="depth limit"):
        derive_observation_registry(
            _roles(), limits=SourceLimits(max_raw_bytes=100_000, max_json_nodes=100_000, max_json_depth=1)
        )


def test_rejects_numeric_wrapper_with_a_different_owning_field() -> None:
    with pytest.raises(RegistrySourceError, match="owning root-model"):
        derive_observation_registry(_decimal_roles(field_name="other"))


def test_rejects_numeric_row_with_wrong_representation() -> None:
    with pytest.raises(RegistrySourceError, match="binary64 row does not match"):
        derive_observation_registry(_decimal_roles(representation="canonical_finite_binary64"))


def test_accepts_inverted_canonical_decimal_bounds_as_a_declaration() -> None:
    derive_observation_registry(_decimal_roles(lower="11.00", upper="10.00"))


@pytest.mark.parametrize(
    ("lower", "upper", "scale"),
    [("0.0", "2.00", "2"), ("0.00", "2.0", "2"), ("0.00", "2.00", None)],
)
def test_rejects_missing_or_wrong_decimal_bound_scale(
    lower: str, upper: str, scale: str | None
) -> None:
    with pytest.raises(RegistrySourceError, match="decimal (lower|upper|scale)"):
        derive_observation_registry(_decimal_roles(lower=lower, upper=upper, scale=scale))


def _vector_by_name(name: str) -> RegistryRejectionVector:
    return next(vector for vector in build_rejection_vectors() if vector.name == name)


def _materialize_vector_sources(tmp_path: Path, vector: RegistryRejectionVector) -> Path:
    root = tmp_path / vector.source_root_relative_path
    actual_root = tmp_path / (vector.source_root_symlink_target or vector.source_root_relative_path)
    actual_root.mkdir(parents=True, exist_ok=True)
    ordinary = [item for item in vector.decoder_source_files if item.symlink_target is None]
    aliases = [item for item in vector.decoder_source_files if item.symlink_target is not None]
    for item in ordinary:
        target = actual_root / item.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.raw_bytes)
    for item in aliases:
        assert item.symlink_target is not None
        target = actual_root / item.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(item.symlink_target)
    if vector.source_root_symlink_target is not None:
        root.symlink_to(vector.source_root_symlink_target, target_is_directory=True)
    return root


def _compile_vector_source(tmp_path: Path, vector: RegistryRejectionVector, limits: SourceLimits | None = None) -> None:
    compile_observation_registry(
        vector.raw_role_pairs,
        decoder_source_manifest_bytes=vector.decoder_source_manifest_bytes,
        decoder_source_root=_materialize_vector_sources(tmp_path, vector),
        publication_manifest_bytes=vector.publication_manifest_bytes,
        limits=limits or SourceLimits(),
    )


def test_decoder_source_intake_accepts_native_regular_file(tmp_path: Path) -> None:
    _compile_vector_source(tmp_path, _vector_by_name("valid_complete_package"))


@pytest.mark.parametrize(
    "name",
    [
        "decoder_file_symlink",
        "decoder_directory_symlink",
        "decoder_source_root_symlink",
        "generated_namespace_source",
        "generated_namespace_nested_source",
        "generated_namespace_source_root",
        "decoder_source_root_parent_alias",
    ],
)
def test_decoder_source_intake_rejects_no_follow_and_generated_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(RegistrySourceError):
        _compile_vector_source(tmp_path, _vector_by_name(name))


def test_decoder_source_intake_rejects_nonregular_file_and_size_overflow(tmp_path: Path) -> None:
    vector = _vector_by_name("valid_complete_package")
    root = _materialize_vector_sources(tmp_path / "fifo", vector)
    leaf = root / "native/leaf.py"
    leaf.unlink()
    os.mkfifo(leaf)
    with pytest.raises(RegistrySourceError, match="not a regular file"):
        compile_observation_registry(
            vector.raw_role_pairs,
            decoder_source_manifest_bytes=vector.decoder_source_manifest_bytes,
            decoder_source_root=root,
            publication_manifest_bytes=vector.publication_manifest_bytes,
        )
    with pytest.raises(RegistrySourceError, match="raw-byte limit"):
        _compile_vector_source(tmp_path / "bounded", vector, SourceLimits(max_raw_bytes=8, max_json_nodes=1_000, max_json_depth=64))


def test_decoder_source_intake_rejects_ancestor_symlink_root(tmp_path: Path) -> None:
    vector = replace(_vector_by_name("valid_complete_package"), source_root_relative_path="source")
    real_parent = tmp_path / "real"
    source_root = _materialize_vector_sources(real_parent, vector)
    (tmp_path / "alias").symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(RegistrySourceError, match="canonical"):
        compile_observation_registry(
            vector.raw_role_pairs,
            decoder_source_manifest_bytes=vector.decoder_source_manifest_bytes,
            decoder_source_root=tmp_path / "alias" / source_root.name,
            publication_manifest_bytes=vector.publication_manifest_bytes,
        )


def test_rejects_noncanonical_raw_bytes() -> None:
    roles = _roles()
    roles[1] = (roles[1][0], roles[1][1] + b"\n")

    with pytest.raises(RegistrySourceError, match="terminal LF"):
        compile_observation_registry(roles)
