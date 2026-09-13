from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from memorii.core.memory_evolution import typed_value_model_codec as codec
from memorii.core.memory_evolution import typed_value_registry_compilation as compilation
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.typed_value_body_validation import (
    ProtectedTypedValueBodyLimits,
    validate_typed_value_body,
)
from memorii.core.memory_evolution.typed_value_declarations import (
    CollectionTypeExpr,
    ProtectedDeclarationParseLimits,
    ScalarTypeExpr,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifest,
    DecoderSourceSnapshot,
    VerifiedDecoderSourceManifest,
)
from memorii.core.memory_evolution.typed_value_model_codec import (
    TypedValueModelCodecError,
    _BoundedWriter,
    _emit_value,
    _integer_text,
    _parse_integer,
    materialize_typed_value_model,
    reencode_materialized_typed_value_model,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationPins,
    PublicationDecoderSourceSnapshot,
    TypedValuePublicationManifest,
    VerifiedTypedValuePublication,
)
from memorii.core.semantic_ingestion.contracts import (
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
)
from memorii.domain.enums import SourceModality

_LIMITS = ProtectedDeclarationParseLimits(10_000, 200, 20)
_BODY_LIMITS = ProtectedTypedValueBodyLimits(10_000, 200, 20)
_DECODER_ID = "memorii.semantic_ingestion.observation.MemoryScope.v1"
_SOURCE_DIGEST = "a" * 64
_OBSERVATION_REGISTRY_SOURCES = (
    Path(__file__).resolve().parents[4]
    / "memorii"
    / "core"
    / "memory_evolution"
    / "observation_registry_sources"
)
_NESTED_DECODER_IDS = (
    "memorii.semantic_ingestion.observation.SegmentGovernanceBinding.v1",
    "memorii.semantic_ingestion.observation.SegmentGovernanceCarrierSet.v1",
)
_NESTED_SOURCE_DIGEST = "f" * 64


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _registry():
    grammar = {
        "role": "grammar",
        "profile_id": "semantic_ingestion_typed_value",
        "profile_version": "3",
        "grammar_revision": "operational-3",
        "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"},
        "envelope": {"binding_fields": ["profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"], "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"], "permitted_value_kinds": ["bytes", "integer", "map", "scalar"]},
        "tags": {"bytes": "rfc4648_standard_padded", "datetime": "utc_six_fractional_digits", "duration_microseconds": "signed_i64", "enum": "registered_qualified_member", "frozenset": "canonical_member_byte_order", "integer": "canonical_decimal_string", "list": "declared_order", "map": "encoded_json_string_key_order", "set": "canonical_member_byte_order", "tuple": "declared_order"},
        "type_rules": {"bool_as_integer": False, "defaults_before_verification": False, "float_decimal": False, "map_keys": "string_only", "model_fields": "registered_exact", "optional": "registered_policy", "union": "one_registered_discriminator"},
    }
    sources = [
        _raw(grammar),
        _raw({"role": "schema", "schema_id": "MemoryScope", "schema_version": "1", "root_kind": "model", "fields": [{"name": "session_id", "type": {"kind": "string", "lexical_rule": "unicode_scalar"}, "integrity_role": "ordinary"}, {"name": "task_id", "type": {"kind": "string", "lexical_rule": "unicode_scalar"}, "integrity_role": "ordinary"}, {"name": "user_id", "type": {"kind": "string", "lexical_rule": "unicode_scalar"}, "integrity_role": "ordinary"}]}),
        _raw({"role": "enum", "schema_id": "MemoryScope", "schema_version": "1", "enums": []}),
        _raw({"role": "optional", "schema_id": "MemoryScope", "schema_version": "1", "fields": [{"field_name": "session_id", "policy": "required_nullable"}, {"field_name": "task_id", "policy": "required_nullable"}, {"field_name": "user_id", "policy": "required_nullable"}]}),
        _raw({"role": "numeric", "schema_id": "MemoryScope", "schema_version": "1", "fields": []}),
        _raw({"role": "digest-signature", "schema_id": "MemoryScope", "schema_version": "1", "policy": {"kind": "ordinary"}}),
        _raw({"role": "decoder", "schema_id": "MemoryScope", "schema_version": "1", "decoder_id": _DECODER_ID, "typed_root_kind": "model", "implementation_source_digest": _SOURCE_DIGEST}),
        _raw({"role": "upcast", "schema_id": "MemoryScope", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None}),
    ]
    sources.append(compilation.author_typed_value_registry_role(sources, limits=_LIMITS))
    return compilation.compile_typed_value_registry(sources, limits=_LIMITS)


def _publication():
    registry = _registry()
    manifest = DecoderSourceManifest(b"{}", "b" * 64, "semantic_ingestion_typed_value", "3", ())
    sources = VerifiedDecoderSourceManifest(manifest, (), (DecoderSourceSnapshot(_DECODER_ID, _SOURCE_DIGEST, ()),))
    publication = TypedValuePublicationManifest(b"{}", "c" * 64, "semantic_ingestion_typed_value", "3", (), "d" * 64, (PublicationDecoderSourceSnapshot(_DECODER_ID, _SOURCE_DIGEST),), registry.registry_digest)
    pins = ProtectedTypedValuePublicationPins(
        "c" * 64,
        registry.registry_digest,
        (DecoderSourceSnapshotPin(_DECODER_ID, _SOURCE_DIGEST),),
        "e" * 64,
    )
    return VerifiedTypedValuePublication(registry, sources, publication, pins, "e" * 64)


def _body(publication: VerifiedTypedValuePublication):
    raw = b'{"$type":"map","entries":[["session_id",null],["task_id",null],["user_id",null]]}'
    return validate_typed_value_body(raw, registry=publication.compiled_registry, entry=publication.compiled_registry.entries[0], limits=_BODY_LIMITS)


def _registry_source(role: str, schema_id: str | None = None) -> bytes:
    path = _OBSERVATION_REGISTRY_SOURCES / ("grammar.json" if schema_id is None else f"{role}/{schema_id}/1.json")
    return path.read_bytes()


def _nested_registry(*, assertion_wire_value: str = "assertion"):
    """Compile only the real two-model source closure used by this local codec proof."""
    sources = [_registry_source("grammar")]
    for schema_id in ("SegmentGovernanceBinding", "SegmentGovernanceCarrierSet"):
        for role in ("schema", "enum", "optional", "numeric", "digest-signature", "upcast"):
            raw = _registry_source(role, schema_id)
            if schema_id == "SegmentGovernanceBinding" and role == "enum" and assertion_wire_value != "assertion":
                declaration = json.loads(raw)
                declaration["enums"][0]["members"][0]["wire_value"] = assertion_wire_value
                raw = _raw(declaration)
            sources.append(raw)
        sources.append(
            _raw(
                {
                    "role": "decoder",
                    "schema_id": schema_id,
                    "schema_version": "1",
                    "decoder_id": f"memorii.semantic_ingestion.observation.{schema_id}.v1",
                    "typed_root_kind": "model",
                    # This is a local conversion identity fixture, not a publication claim.
                    "implementation_source_digest": _NESTED_SOURCE_DIGEST,
                }
            )
        )
    sources.append(compilation.author_typed_value_registry_role(sources, limits=_LIMITS))
    return compilation.compile_typed_value_registry(sources, limits=_LIMITS)


def _nested_publication(*, assertion_wire_value: str = "assertion") -> VerifiedTypedValuePublication:
    registry = _nested_registry(assertion_wire_value=assertion_wire_value)
    snapshots = tuple(DecoderSourceSnapshot(decoder_id, _NESTED_SOURCE_DIGEST, ()) for decoder_id in _NESTED_DECODER_IDS)
    sources = VerifiedDecoderSourceManifest(
        DecoderSourceManifest(b"{}", "b" * 64, "semantic_ingestion_typed_value", "3", ()),
        (),
        snapshots,
    )
    published = tuple(PublicationDecoderSourceSnapshot(item.decoder_id, item.source_snapshot_digest) for item in snapshots)
    manifest = TypedValuePublicationManifest(b"{}", "c" * 64, "semantic_ingestion_typed_value", "3", (), "d" * 64, published, registry.registry_digest)
    pins = ProtectedTypedValuePublicationPins(
        "c" * 64,
        registry.registry_digest,
        tuple(DecoderSourceSnapshotPin(item.decoder_id, item.source_snapshot_digest) for item in snapshots),
        "e" * 64,
    )
    return VerifiedTypedValuePublication(registry, sources, manifest, pins, "e" * 64)


def _nested_value() -> SegmentGovernanceCarrierSet:
    binding = SegmentGovernanceBinding.create(
        source_id="source-1",
        segment_id="segment-1",
        message_semantic_context_digest="1" * 64,
        effective_scope_digest="2" * 64,
        authority_digest="3" * 64,
        data_classification="internal",
        modality=SourceModality.ASSERTION,
        provider_egress_decision_digest="4" * 64,
        egress_disposition="allow_verbatim",
    )
    return SegmentGovernanceCarrierSet.create(source_id="source-1", bindings=(binding,))


def _nested_body(publication: VerifiedTypedValuePublication):
    value = _nested_value()
    binding = value.bindings[0]
    fields = {
        "authority_digest": binding.authority_digest,
        "binding_digest": binding.binding_digest,
        "data_classification": binding.data_classification,
        "effective_scope_digest": binding.effective_scope_digest,
        "egress_disposition": binding.egress_disposition,
        "message_semantic_context_digest": binding.message_semantic_context_digest,
        "modality": {"$type": "enum", "enum_type": "memorii.domain.SourceModality", "member": "ASSERTION"},
        "provider_egress_decision_digest": binding.provider_egress_decision_digest,
        "segment_id": binding.segment_id,
        "source_id": binding.source_id,
    }
    nested = {"$type": "map", "entries": [[name, child] for name, child in fields.items()]}
    raw = _raw(
        {
            "$type": "map",
            "entries": [
                ["bindings", {"$type": "tuple", "items": [nested]}],
                ["carrier_set_digest", value.carrier_set_digest],
                ["source_id", value.source_id],
            ],
        }
    )
    entry = publication.compiled_registry.entry_for("SegmentGovernanceCarrierSet", "1")
    return validate_typed_value_body(raw, registry=publication.compiled_registry, entry=entry, limits=_BODY_LIMITS)


def test_materializes_real_native_public_root_and_reencodes_exact_bytes() -> None:
    publication = _publication()
    materialized = materialize_typed_value_model(_body(publication), publication=publication, maximum_bytes=10_000, maximum_nodes=200, maximum_depth=20)

    assert materialized.value == MemoryScope()
    assert materialized.present_fields == frozenset({"session_id", "task_id", "user_id"})
    assert reencode_materialized_typed_value_model(materialized, publication=publication, maximum_bytes=10_000, maximum_nodes=200, maximum_depth=20) == materialized.body.raw_bytes


@pytest.mark.parametrize("change", ["entry", "source", "publication"])
def test_rejects_wrong_decoder_or_source_identity_before_native_dispatch(change: str) -> None:
    publication = _publication()
    body = _body(publication)
    if change == "entry":
        body = replace(body, entry=replace(body.entry, decoder_id="memorii.semantic_ingestion.observation.Unknown.v1"))
    elif change == "source":
        body = replace(body, entry=replace(body.entry, implementation_source_digest="f" * 64))
    else:
        publication = replace(publication, publication_manifest=replace(publication.publication_manifest, decoder_source_snapshots=(PublicationDecoderSourceSnapshot(_DECODER_ID, "f" * 64),)))

    with pytest.raises(TypedValueModelCodecError):
        materialize_typed_value_model(body, publication=publication, maximum_bytes=10_000, maximum_nodes=200, maximum_depth=20)


def test_rechecks_protected_tree_limits_before_native_dispatch() -> None:
    publication = _publication()

    with pytest.raises(TypedValueModelCodecError, match="nodes_limit_exceeded"):
        materialize_typed_value_model(
            _body(publication),
            publication=publication,
            maximum_bytes=10_000,
            maximum_nodes=1,
            maximum_depth=20,
        )


def test_chunked_unbounded_integer_conversion_does_not_use_runtime_digit_limits() -> None:
    text = "9" * 4_301

    assert _integer_text(_parse_integer(text)) == text


def test_rejects_body_at_one_byte_less_before_native_dispatch() -> None:
    publication = _publication()
    body = _body(publication)

    with pytest.raises(TypedValueModelCodecError, match="bytes_limit_exceeded"):
        materialize_typed_value_model(body, publication=publication, maximum_bytes=len(body.raw_bytes) - 1, maximum_nodes=200, maximum_depth=20)


def test_native_emitter_rejects_collection_coercion_and_formats_early_utc() -> None:
    writer = _BoundedWriter(1_000, 50, 10)
    publication = _publication()
    registry = publication.compiled_registry
    with pytest.raises(TypedValueModelCodecError, match="collection_kind_invalid"):
        _emit_value(writer, [], CollectionTypeExpr("variadic_tuple", ScalarTypeExpr("string")), None, registry, publication, registry.entries[0], 1)

    writer = _BoundedWriter(1_000, 50, 10)
    _emit_value(writer, datetime(1, 1, 1, tzinfo=UTC), ScalarTypeExpr("datetime"), None, registry, publication, registry.entries[0], 1)
    assert writer.finish() == b'{"$type":"datetime","value":"0001-01-01T00:00:00.000000Z"}'


def test_materializes_real_nested_model_and_source_modality_from_source_declarations() -> None:
    publication = _nested_publication()
    body = _nested_body(publication)

    materialized = materialize_typed_value_model(body, publication=publication, maximum_bytes=10_000, maximum_nodes=200, maximum_depth=20)

    assert materialized.value == _nested_value()
    assert isinstance(materialized.value, SegmentGovernanceCarrierSet)
    assert materialized.value.bindings[0].modality is SourceModality.ASSERTION
    assert reencode_materialized_typed_value_model(materialized, publication=publication, maximum_bytes=10_000, maximum_nodes=200, maximum_depth=20) == body.raw_bytes


def test_nested_model_rejects_wrong_source_identity_before_native_dispatch() -> None:
    publication = _nested_publication()
    body = _nested_body(publication)
    snapshots = (
        DecoderSourceSnapshot(_NESTED_DECODER_IDS[0], "0" * 64, ()),
        DecoderSourceSnapshot(_NESTED_DECODER_IDS[1], _NESTED_SOURCE_DIGEST, ()),
    )
    published = tuple(PublicationDecoderSourceSnapshot(item.decoder_id, item.source_snapshot_digest) for item in snapshots)
    altered = replace(
        publication,
        verified_decoder_sources=replace(publication.verified_decoder_sources, snapshots=snapshots),
        publication_manifest=replace(publication.publication_manifest, decoder_source_snapshots=published),
    )

    with (
        patch.object(codec, "decode_native_observation") as decode,
        pytest.raises(TypedValueModelCodecError, match="decoder_source_identity_mismatch"),
    ):
        materialize_typed_value_model(body, publication=altered, maximum_bytes=10_000, maximum_nodes=200, maximum_depth=20)

    decode.assert_not_called()


def test_source_modality_rejects_declared_wire_mismatch_before_native_validation() -> None:
    publication = _nested_publication(assertion_wire_value="wrong-wire")

    with (
        patch.object(codec, "decode_native_observation") as decode,
        pytest.raises(TypedValueModelCodecError, match="source_modality_wire_mismatch"),
    ):
        materialize_typed_value_model(_nested_body(publication), publication=publication, maximum_bytes=10_000, maximum_nodes=200, maximum_depth=20)

    decode.assert_not_called()


def test_nested_model_preserves_native_digest_validation() -> None:
    publication = _nested_publication()
    body = _nested_body(publication)
    raw = json.loads(body.raw_bytes)
    nested_entries = raw["entries"][0][1]["items"][0]["entries"]
    for index, (name, _) in enumerate(nested_entries):
        if name == "binding_digest":
            nested_entries[index][1] = "0" * 64
            break
    else:
        raise AssertionError("nested binding digest field missing")
    altered = validate_typed_value_body(
        _raw(raw),
        registry=publication.compiled_registry,
        entry=body.entry,
        limits=_BODY_LIMITS,
    )

    with pytest.raises(TypedValueModelCodecError, match="nested_native_decode_invalid"):
        materialize_typed_value_model(altered, publication=publication, maximum_bytes=10_000, maximum_nodes=200, maximum_depth=20)
