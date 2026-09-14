from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.typed_value_declarations import ProtectedDeclarationParseLimits
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceSelection,
    ProtectedDecoderSourceManifestLimits,
    capture_decoder_source_files,
    verify_decoder_source_manifest,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationLimits,
    ProtectedTypedValuePublicationPins,
    TypedValuePublicationError,
    parse_typed_value_publication_manifest,
    verify_typed_value_publication,
)
from memorii.core.memory_evolution.typed_value_publication_authoring import (
    TypedValuePublicationAuthoringError,
    author_typed_value_publication_package,
)

DECLARATION_LIMITS = ProtectedDeclarationParseLimits(20_000, 300, 30)
SOURCE_LIMITS = ProtectedDecoderSourceManifestLimits(20_000, 300, 30, 10, 20_000)
LIMITS = ProtectedTypedValuePublicationLimits(DECLARATION_LIMITS, SOURCE_LIMITS, 20_000)


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _grammar() -> dict[str, object]:
    return {
        "role": "grammar",
        "profile_id": "semantic_ingestion_typed_value",
        "profile_version": "3",
        "grammar_revision": "operational-3",
        "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"},
        "envelope": {"binding_fields": ["profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"], "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"], "permitted_value_kinds": ["bytes", "integer", "map", "scalar"]},
        "tags": {"bytes": "rfc4648_standard_padded", "datetime": "utc_six_fractional_digits", "duration_microseconds": "signed_i64", "enum": "registered_qualified_member", "frozenset": "canonical_member_byte_order", "integer": "canonical_decimal_string", "list": "declared_order", "map": "encoded_json_string_key_order", "set": "canonical_member_byte_order", "tuple": "declared_order"},
        "type_rules": {"bool_as_integer": False, "defaults_before_verification": False, "float_decimal": False, "map_keys": "string_only", "model_fields": "registered_exact", "optional": "registered_policy", "union": "one_registered_discriminator"},
    }


def _raw_roles() -> tuple[bytes, ...]:
    return (
        _raw(_grammar()),
        _raw({"role": "schema", "schema_id": "X", "schema_version": "1", "root_kind": "model", "fields": [{"name": "value", "type": {"kind": "bool"}, "integrity_role": "ordinary"}]}),
        _raw({"role": "enum", "schema_id": "X", "schema_version": "1", "enums": []}),
        _raw({"role": "optional", "schema_id": "X", "schema_version": "1", "fields": [{"field_name": "value", "policy": "required"}]}),
        _raw({"role": "numeric", "schema_id": "X", "schema_version": "1", "fields": []}),
        _raw({"role": "digest-signature", "schema_id": "X", "schema_version": "1", "policy": {"kind": "ordinary"}}),
        _raw({"role": "upcast", "schema_id": "X", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None}),
    )


def _selection() -> tuple[DecoderSourceSelection, ...]:
    return (DecoderSourceSelection("memorii.semantic_ingestion.observation.X.v1", "native", "decoder/native.py"),)


def _package(tmp_path: Path):  # type: ignore[no-untyped-def]
    (tmp_path / "decoder").mkdir(exist_ok=True)
    (tmp_path / "decoder" / "native.py").write_bytes(b"def decode(value):\n    return value\n")
    return author_typed_value_publication_package(_raw_roles(), _selection(), source_package_root=tmp_path, limits=LIMITS)


def _pins(package, vector: bytes) -> ProtectedTypedValuePublicationPins:  # type: ignore[no-untyped-def]
    publication = parse_typed_value_publication_manifest(package.raw_publication_manifest, maximum_bytes=20_000)
    return ProtectedTypedValuePublicationPins(
        publication.publication_digest,
        package.compiled_registry.registry_digest,
        tuple(DecoderSourceSnapshotPin(item.decoder_id, item.source_snapshot_digest) for item in package.verified_decoder_sources.snapshots),
        sha256(vector).hexdigest(),
    )


def test_authors_deterministic_immutable_package_and_round_trips_verifier(tmp_path: Path) -> None:
    first = _package(tmp_path)
    second = author_typed_value_publication_package(reversed(_raw_roles()), _selection(), source_package_root=tmp_path, limits=LIMITS)
    assert first.raw_decoder_source_manifest == second.raw_decoder_source_manifest
    assert first.raw_publication_manifest == second.raw_publication_manifest
    vector = b'{"independent":"test-vector-only"}'
    verified = verify_typed_value_publication(
        first.raw_role_sources,
        first.raw_decoder_source_manifest,
        first.raw_publication_manifest,
        vector,
        source_package_root=tmp_path,
        limits=LIMITS,
        pins=_pins(first, vector),
    )
    assert verified.compiled_registry.entries[0].decoder_id == "memorii.semantic_ingestion.observation.X.v1"
    assert tuple(type(item) for item in first.raw_role_sources) == (bytes,) * len(first.raw_role_sources)


def test_rejects_supplied_decoder_registry_and_selection_closure(tmp_path: Path) -> None:
    _package(tmp_path)
    decoder = _raw({"role": "decoder", "schema_id": "X", "schema_version": "1", "decoder_id": "memorii.semantic_ingestion.observation.X.v1", "typed_root_kind": "model", "implementation_source_digest": "a" * 64})
    with pytest.raises(TypedValuePublicationAuthoringError, match="supplied_decoder_or_registry"):
        author_typed_value_publication_package((*_raw_roles(), decoder), _selection(), source_package_root=tmp_path, limits=LIMITS)
    with pytest.raises(TypedValuePublicationAuthoringError, match="selection_closure"):
        author_typed_value_publication_package(_raw_roles(), (), source_package_root=tmp_path, limits=LIMITS)
    with pytest.raises(TypedValuePublicationAuthoringError, match="selection_closure"):
        author_typed_value_publication_package(_raw_roles(), (*_selection(), DecoderSourceSelection("other", "extra", "decoder/native.py")), source_package_root=tmp_path, limits=LIMITS)


def test_rejects_traversal_and_detects_post_authoring_source_tamper(tmp_path: Path) -> None:
    package = _package(tmp_path)
    invalid = (DecoderSourceSelection("memorii.semantic_ingestion.observation.X.v1", "native", "../native.py"),)
    with pytest.raises(TypedValuePublicationAuthoringError, match="source_capture_invalid"):
        author_typed_value_publication_package(_raw_roles(), invalid, source_package_root=tmp_path, limits=LIMITS)
    vector = b'{"independent":"test-vector-only"}'
    (tmp_path / "decoder" / "native.py").write_bytes(b"def decode(value):\n    return False\n")
    with pytest.raises(TypedValuePublicationError, match="decoder_sources_invalid"):
        verify_typed_value_publication(
            package.raw_role_sources,
            package.raw_decoder_source_manifest,
            package.raw_publication_manifest,
            vector,
            source_package_root=tmp_path,
            limits=LIMITS,
            pins=_pins(package, vector),
        )


def test_shared_source_rows_reread_and_reuse_the_same_immutable_bytes_object(tmp_path: Path) -> None:
    (tmp_path / "shared.py").write_bytes(b"def common():\n    return True\n")
    source_rows = (
        DecoderSourceSelection("decode-a", "shared", "shared.py"),
        DecoderSourceSelection("decode-b", "shared", "shared.py"),
    )
    captured = capture_decoder_source_files(source_rows, source_package_root=tmp_path, limits=SOURCE_LIMITS)
    assert captured[0].raw_bytes is captured[1].raw_bytes
    manifest = _raw(
        {
            "role": "decoder_source_manifest",
            "profile_id": "semantic_ingestion_typed_value",
            "profile_version": "3",
            "files": [
                {"decoder_id": item.decoder_id, "source_file_id": item.source_file_id, "relative_path": item.relative_path, "sha256": item.sha256}
                for item in captured
            ],
        }
    )
    verified = verify_decoder_source_manifest(manifest, source_package_root=tmp_path, limits=SOURCE_LIMITS)
    assert verified.files[0].raw_bytes is verified.files[1].raw_bytes


@pytest.mark.parametrize(
    "generated_path",
    (
        "core/memory_evolution/observation_registry_sources/decoder/Generated/1.json",
        "core/memory_evolution/observation_registry_sources/registry.json",
        "core/memory_evolution/observation_registry_sources/decoder-source-manifest.json",
        "core/memory_evolution/observation_registry_sources/publication-manifest.json",
    ),
)
def test_authoring_default_source_exclusion_rejects_generated_registry_artifacts(tmp_path: Path, generated_path: str) -> None:
    generated = tmp_path / generated_path
    generated.parent.mkdir(parents=True)
    generated.write_bytes(b'{"generated":true}')
    selection = (DecoderSourceSelection("memorii.semantic_ingestion.observation.X.v1", "generated", generated_path),)

    with pytest.raises(TypedValuePublicationAuthoringError, match="source_capture_invalid"):
        author_typed_value_publication_package(_raw_roles(), selection, source_package_root=tmp_path, limits=LIMITS)
