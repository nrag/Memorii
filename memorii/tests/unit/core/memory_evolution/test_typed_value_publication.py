from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from memorii.core.memory_evolution import typed_value_registry_compilation as compilation
from memorii.core.memory_evolution.typed_value_declarations import (
    GrammarRole,
    ProtectedDeclarationParseLimits,
    parse_typed_value_declaration,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import ProtectedDecoderSourceManifestLimits
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationLimits,
    ProtectedTypedValuePublicationPins,
    TypedValuePublicationError,
    parse_typed_value_publication_manifest,
    verify_typed_value_publication,
)

DECLARATION_LIMITS = ProtectedDeclarationParseLimits(20_000, 300, 30)
SOURCE_LIMITS = ProtectedDecoderSourceManifestLimits(20_000, 300, 30, 10, 20_000)
LIMITS = ProtectedTypedValuePublicationLimits(DECLARATION_LIMITS, SOURCE_LIMITS, 20_000)


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _grammar() -> dict[str, object]:
    return {"role": "grammar", "profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "grammar_revision": "operational-3", "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"}, "envelope": {"binding_fields": ["profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"], "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"], "permitted_value_kinds": ["bytes", "integer", "map", "scalar"]}, "tags": {"bytes": "rfc4648_standard_padded", "datetime": "utc_six_fractional_digits", "duration_microseconds": "signed_i64", "enum": "registered_qualified_member", "frozenset": "canonical_member_byte_order", "integer": "canonical_decimal_string", "list": "declared_order", "map": "encoded_json_string_key_order", "set": "canonical_member_byte_order", "tuple": "declared_order"}, "type_rules": {"bool_as_integer": False, "defaults_before_verification": False, "float_decimal": False, "map_keys": "string_only", "model_fields": "registered_exact", "optional": "registered_policy", "union": "one_registered_discriminator"}}


def _source_role(name: str, value: dict[str, object]) -> tuple[str, bytes]:
    return name, _raw(value)


def _publication_inputs(
    tmp_path: Path, decoder_body: bytes = b"def decode(value):\n    return value\n"
) -> tuple[list[bytes], bytes, bytes, bytes, ProtectedTypedValuePublicationPins]:
    (tmp_path / "decoder").mkdir(exist_ok=True)
    (tmp_path / "decoder" / "native.py").write_bytes(decoder_body)
    decoder_manifest = _raw({"role": "decoder_source_manifest", "profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "files": [{"decoder_id": "decode-x", "source_file_id": "native", "relative_path": "decoder/native.py", "sha256": sha256(decoder_body).hexdigest()}]})
    snapshot = sha256(compilation.length_prefixed(b"semantic-ingestion-profile3-decoder-source-snapshot", b"decode-x", b"1", b"native", b"decoder/native.py", decoder_body)).hexdigest()
    sources = [
        _source_role("grammar", _grammar())[1],
        _source_role("schema/X/1", {"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "bool"}, "integrity_role": "ordinary"}]})[1],
        _source_role("enum/X/1", {"role": "enum", "schema_id": "X", "schema_version": "1", "enums": []})[1],
        _source_role("optional/X/1", {"role": "optional", "schema_id": "X", "schema_version": "1", "fields": [{"field_name": "value", "policy": "required"}]})[1],
        _source_role("numeric/X/1", {"role": "numeric", "schema_id": "X", "schema_version": "1", "fields": []})[1],
        _source_role("digest-signature/X/1", {"role": "digest-signature", "schema_id": "X", "schema_version": "1", "policy": {"kind": "ordinary"}})[1],
        _source_role("decoder/X/1", {"role": "decoder", "schema_id": "X", "schema_version": "1", "decoder_id": "decode-x", "typed_root_kind": "model", "implementation_source_digest": snapshot})[1],
        _source_role("upcast/X/1", {"role": "upcast", "schema_id": "X", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None})[1],
    ]
    parsed = tuple(parse_typed_value_declaration(raw, limits=DECLARATION_LIMITS) for raw in sources)
    grammar = next(item for item in parsed if item.role == "grammar")
    assert isinstance(grammar, GrammarRole)
    profile = compilation._compile_profile(grammar.raw_bytes, grammar.profile_id, grammar.profile_version, grammar.grammar_revision)
    entry = compilation._compile_entry(("X", "1"), compilation._index_roles(parsed), profile)
    sources.append(_raw({"role": "registry", "profile": {"profile_id": profile.profile_id, "profile_version": profile.profile_version, "grammar_revision": profile.grammar_revision, "grammar_digest": profile.grammar_digest, "profile_digest": profile.profile_digest}, "entries": [entry.entry_digest]}))
    role_files = []
    for raw in sources:
        item = parse_typed_value_declaration(raw, limits=DECLARATION_LIMITS)
        if item.role in {"grammar", "registry"}:
            role = item.role
        else:
            schema_id = getattr(item, "schema_id", None)
            schema_version = getattr(item, "schema_version", None)
            assert isinstance(schema_id, str)
            assert isinstance(schema_version, str)
            role = f"{item.role}/{schema_id}/{schema_version}"
        role_files.append({"role": role, "sha256": sha256(raw).hexdigest()})
    role_files.sort(key=lambda item: item["role"].encode("utf-8"))
    registry = compilation.compile_typed_value_registry(sources, limits=DECLARATION_LIMITS)
    publication = _raw({"role": "publication_manifest", "profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "files": role_files, "decoder_source_manifest_digest": sha256(decoder_manifest).hexdigest(), "decoder_source_snapshots": [{"decoder_id": "decode-x", "source_snapshot_digest": snapshot}], "registry_digest": registry.registry_digest})
    vector = b'{"independent":"vector"}'
    pins = ProtectedTypedValuePublicationPins(parse_typed_value_publication_manifest(publication, maximum_bytes=20_000).publication_digest, registry.registry_digest, (DecoderSourceSnapshotPin("decode-x", snapshot),), sha256(vector).hexdigest())
    return sources, decoder_manifest, publication, vector, pins


def test_verifies_complete_recomputed_publication_join(tmp_path: Path) -> None:
    sources, decoder_manifest, publication, vector, pins = _publication_inputs(tmp_path)
    verified = verify_typed_value_publication(sources, decoder_manifest, publication, vector, source_package_root=tmp_path, limits=LIMITS, pins=pins)
    assert verified.compiled_registry.entries[0].decoder_id == "decode-x"
    assert verified.publication_manifest.publication_digest == pins.publication_digest
    assert verified.verified_decoder_sources.snapshots[0].source_snapshot_digest == pins.decoder_source_snapshots[0].source_snapshot_digest


@pytest.mark.parametrize("mutation", ["wrong-role", "source-file-hash", "source-file-order", "decoder-snapshot"])
def test_rejects_manifest_join_mutations(tmp_path: Path, mutation: str) -> None:
    sources, decoder_manifest, publication, vector, pins = _publication_inputs(tmp_path)
    value = json.loads(publication)
    if mutation == "wrong-role":
        value["files"][0]["role"] = "unknown"
    elif mutation == "source-file-hash":
        value["files"][0]["sha256"] = "0" * 64
    elif mutation == "source-file-order":
        value["files"] = list(reversed(value["files"]))
    else:
        value["decoder_source_snapshots"][0]["source_snapshot_digest"] = "0" * 64
    raw = _raw(value)
    with pytest.raises(TypedValuePublicationError):
        verify_typed_value_publication(sources, decoder_manifest, raw, vector, source_package_root=tmp_path, limits=LIMITS, pins=pins)


def test_rejects_changed_raw_publication_with_same_decoder_snapshot_and_pin_mismatch(tmp_path: Path) -> None:
    sources, decoder_manifest, publication, vector, pins = _publication_inputs(tmp_path)
    changed = _raw({**json.loads(publication), "decoder_source_manifest_digest": "0" * 64})
    with pytest.raises(TypedValuePublicationError, match="decoder_source_manifest_digest_mismatch"):
        verify_typed_value_publication(sources, decoder_manifest, changed, vector, source_package_root=tmp_path, limits=LIMITS, pins=pins)
    wrong_pin = ProtectedTypedValuePublicationPins("0" * 64, pins.registry_digest, pins.decoder_source_snapshots, pins.independent_vector_manifest_digest)
    with pytest.raises(TypedValuePublicationError, match="pin_publication_digest_mismatch"):
        verify_typed_value_publication(sources, decoder_manifest, publication, vector, source_package_root=tmp_path, limits=LIMITS, pins=wrong_pin)
    with pytest.raises(TypedValuePublicationError, match="independent_vector_manifest_mismatch"):
        verify_typed_value_publication(sources, decoder_manifest, publication, vector + b"x", source_package_root=tmp_path, limits=LIMITS, pins=pins)


def test_source_change_updates_decoder_and_publication_not_binding(tmp_path: Path) -> None:
    first_inputs = _publication_inputs(tmp_path)
    first = verify_typed_value_publication(*first_inputs[:4], source_package_root=tmp_path, limits=LIMITS, pins=first_inputs[4])
    second_inputs = _publication_inputs(tmp_path, b"def decode(value):\n    return (value, value)\n")
    second = verify_typed_value_publication(*second_inputs[:4], source_package_root=tmp_path, limits=LIMITS, pins=second_inputs[4])
    first_entry = first.compiled_registry.entries[0]
    second_entry = second.compiled_registry.entries[0]
    assert first_entry.binding_digest == second_entry.binding_digest
    assert first.verified_decoder_sources.snapshots[0].source_snapshot_digest != second.verified_decoder_sources.snapshots[0].source_snapshot_digest
    assert first_entry.decoder_digest != second_entry.decoder_digest
    assert first_entry.entry_digest != second_entry.entry_digest
    assert first.publication_manifest.publication_digest != second.publication_manifest.publication_digest


def test_protected_pins_and_limits_reject_mutable_or_malformed_values() -> None:
    digest = "a" * 64
    snapshot = DecoderSourceSnapshotPin("decode-x", digest)
    with pytest.raises(ValueError, match="snapshots_tuple_required"):
        ProtectedTypedValuePublicationPins(digest, digest, cast(tuple[DecoderSourceSnapshotPin, ...], [snapshot]), digest)
    with pytest.raises(ValueError, match="snapshot_invalid"):
        ProtectedTypedValuePublicationPins(digest, digest, (cast(DecoderSourceSnapshotPin, object()),), digest)
    with pytest.raises(TypedValuePublicationError, match="sha256_invalid"):
        ProtectedTypedValuePublicationPins(cast(str, 1), digest, (snapshot,), digest)
    with pytest.raises(ValueError, match="declaration_limits_invalid"):
        ProtectedTypedValuePublicationLimits(cast(ProtectedDeclarationParseLimits, object()), SOURCE_LIMITS, 20_000)
    with pytest.raises(ValueError, match="decoder_source_limits_invalid"):
        ProtectedTypedValuePublicationLimits(DECLARATION_LIMITS, cast(ProtectedDecoderSourceManifestLimits, object()), 20_000)
