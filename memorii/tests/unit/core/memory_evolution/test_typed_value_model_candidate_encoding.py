from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.typed_value_body_validation import (
    TypedValueBodyValidationError,
)
from memorii.core.memory_evolution.typed_value_declarations import (
    ProtectedDeclarationParseLimits,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    DecoderSourceSelection,
    ProtectedDecoderSourceManifestLimits,
)
from memorii.core.memory_evolution.typed_value_model_codec import (
    TypedValueModelCodecError,
    encode_typed_value_model_candidate,
    reencode_materialized_typed_value_model,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationLimits,
    ProtectedTypedValuePublicationPins,
    PublicationDecoderSourceSnapshot,
    VerifiedTypedValuePublication,
    parse_typed_value_publication_manifest,
    verify_typed_value_publication,
)
from memorii.core.memory_evolution.typed_value_publication_authoring import (
    author_typed_value_publication_package,
)
from memorii.core.semantic_ingestion.contracts import (
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
    SourceSpan,
)
from memorii.domain.enums import SourceModality
from pydantic import BaseModel

_LIMITS = ProtectedDeclarationParseLimits(20_000, 500, 40)
_PUBLICATION_LIMITS = ProtectedTypedValuePublicationLimits(
    _LIMITS,
    ProtectedDecoderSourceManifestLimits(20_000, 500, 40, 3, 20_000),
    20_000,
)
_SOURCE_ROOT = (
    Path(__file__).resolve().parents[4]
    / "memorii"
    / "core"
    / "memory_evolution"
    / "observation_registry_sources"
)
_SCHEMA_IDS = (
    "SegmentGovernanceBinding",
    "SegmentGovernanceCarrierSet",
    "SourceSpan",
)


class _ImpostorCarrierSet(BaseModel):
    source_id: str
    bindings: tuple[SegmentGovernanceBinding, ...]
    carrier_set_digest: str


def _source_bytes(role: str, schema_id: str | None = None) -> bytes:
    path = _SOURCE_ROOT / (
        "grammar.json" if schema_id is None else f"{role}/{schema_id}/1.json"
    )
    return path.read_bytes()


def _publication(tmp_path: Path) -> VerifiedTypedValuePublication:
    sources = [_source_bytes("grammar")]
    for schema_id in _SCHEMA_IDS:
        for role in (
            "schema",
            "enum",
            "optional",
            "numeric",
            "digest-signature",
            "upcast",
        ):
            sources.append(_source_bytes(role, schema_id))
    source_file = tmp_path / "candidate_construction_decoder.py"
    source_file.write_bytes(b"# construction-only source snapshot\n")
    selections = tuple(
        DecoderSourceSelection(
            f"memorii.semantic_ingestion.observation.{schema_id}.v1",
            "candidate-construction",
            source_file.name,
        )
        for schema_id in _SCHEMA_IDS
    )
    package = author_typed_value_publication_package(
        sources,
        selections,
        source_package_root=tmp_path,
        limits=_PUBLICATION_LIMITS,
    )
    publication_manifest = parse_typed_value_publication_manifest(
        package.raw_publication_manifest,
        maximum_bytes=_PUBLICATION_LIMITS.maximum_publication_manifest_bytes,
    )
    independent_vector = b'{"candidate":"construction-only"}'
    pins = ProtectedTypedValuePublicationPins(
        publication_manifest.publication_digest,
        package.compiled_registry.registry_digest,
        tuple(
            DecoderSourceSnapshotPin(item.decoder_id, item.source_snapshot_digest)
            for item in package.verified_decoder_sources.snapshots
        ),
        sha256(independent_vector).hexdigest(),
    )
    return verify_typed_value_publication(
        package.raw_role_sources,
        package.raw_decoder_source_manifest,
        package.raw_publication_manifest,
        independent_vector,
        source_package_root=tmp_path,
        limits=_PUBLICATION_LIMITS,
        pins=pins,
    )


def _carrier_set() -> SegmentGovernanceCarrierSet:
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


def _encode(
    value: object,
    schema_id: str,
    publication: VerifiedTypedValuePublication,
    *,
    maximum_bytes: int = 20_000,
    maximum_nodes: int = 500,
    maximum_depth: int = 40,
):
    return encode_typed_value_model_candidate(
        value,  # type: ignore[arg-type]
        entry=publication.compiled_registry.entry_for(schema_id, "1"),
        publication=publication,
        maximum_bytes=maximum_bytes,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
    )


def _raw_tree_limits(raw_bytes: bytes) -> tuple[int, int]:
    """Independently measure the decoded raw JSON tree used by body validation."""
    pending: list[tuple[object, int]] = [(json.loads(raw_bytes), 1)]
    nodes = 0
    maximum_depth = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        maximum_depth = max(maximum_depth, depth)
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return nodes, maximum_depth


def _assert_body_limit_cause(
    error: TypedValueModelCodecError, limit_name: str
) -> None:
    assert str(error) == "typed_value_model_codec_candidate_body_invalid"
    assert isinstance(error.__cause__, TypedValueBodyValidationError)
    assert str(error.__cause__) == "typed_value_body_raw_invalid"
    assert isinstance(error.__cause__.__cause__, DecoderSourceManifestError)
    assert str(error.__cause__.__cause__) == (
        f"decoder_source_manifest_{limit_name}_limit_exceeded"
    )


def _source_span_oracle(value: SourceSpan) -> bytes:
    return (
        b'{"$type":"map","entries":[["end",{"$type":"integer","value":"'
        + str(value.end).encode("ascii")
        + b'"}],["source_id","'
        + value.source_id.encode("ascii")
        + b'"],["start",{"$type":"integer","value":"'
        + str(value.start).encode("ascii")
        + b'"}]]}'
    )


def _carrier_set_oracle(value: SegmentGovernanceCarrierSet) -> bytes:
    binding = value.bindings[0]
    return (
        b'{"$type":"map","entries":[["bindings",{"$type":"tuple","items":[{"$type":"map","entries":['
        b'["authority_digest","' + binding.authority_digest.encode("ascii")
        + b'"],["binding_digest","' + binding.binding_digest.encode("ascii")
        + b'"],["data_classification","' + binding.data_classification.encode("ascii")
        + b'"],["effective_scope_digest","' + binding.effective_scope_digest.encode("ascii")
        + b'"],["egress_disposition","' + binding.egress_disposition.encode("ascii")
        + b'"],["message_semantic_context_digest","' + binding.message_semantic_context_digest.encode("ascii")
        + b'"],["modality",{"$type":"enum","enum_type":"memorii.domain.SourceModality","member":"ASSERTION"}]'
        + b',["provider_egress_decision_digest","' + binding.provider_egress_decision_digest.encode("ascii")
        + b'"],["segment_id","' + binding.segment_id.encode("ascii")
        + b'"],["source_id","' + binding.source_id.encode("ascii")
        + b'"]]}]}],["carrier_set_digest","' + value.carrier_set_digest.encode("ascii")
        + b'"],["source_id","' + value.source_id.encode("ascii") + b'"]]}'
    )


def test_encodes_source_selected_native_nested_enum_and_integer_models(tmp_path: Path) -> None:
    publication = _publication(tmp_path)
    carrier_set = _carrier_set()
    source_span = SourceSpan(source_id="source-1", start=2, end=7)

    materialized = _encode(carrier_set, "SegmentGovernanceCarrierSet", publication)
    integer_materialized = _encode(source_span, "SourceSpan", publication)

    assert materialized.value == carrier_set
    assert isinstance(materialized.value, SegmentGovernanceCarrierSet)
    assert materialized.value.bindings[0].modality is SourceModality.ASSERTION
    assert integer_materialized.value == source_span
    assert materialized.body.raw_bytes == _carrier_set_oracle(carrier_set)
    assert integer_materialized.body.raw_bytes == _source_span_oracle(source_span)
    assert reencode_materialized_typed_value_model(
        materialized,
        publication=publication,
        maximum_bytes=20_000,
        maximum_nodes=500,
        maximum_depth=40,
    ) == materialized.body.raw_bytes


def test_candidate_encoding_rejects_wrong_entry_publication_native_type_and_required_omission(tmp_path: Path) -> None:
    publication = _publication(tmp_path)
    carrier_entry = publication.compiled_registry.entry_for("SegmentGovernanceCarrierSet", "1")
    with pytest.raises(TypedValueModelCodecError, match="entry_identity_mismatch"):
        encode_typed_value_model_candidate(
            _carrier_set(),
            entry=replace(carrier_entry, decoder_id="memorii.semantic_ingestion.observation.Unknown.v1"),
            publication=publication,
            maximum_bytes=20_000,
            maximum_nodes=500,
            maximum_depth=40,
        )
    with pytest.raises(TypedValueModelCodecError, match="publication_snapshot_mismatch"):
        _encode(
            _carrier_set(),
            "SegmentGovernanceCarrierSet",
            replace(
                publication,
                publication_manifest=replace(
                    publication.publication_manifest,
                    decoder_source_snapshots=(
                        PublicationDecoderSourceSnapshot(
                            carrier_entry.decoder_id, "f" * 64
                        ),
                    ),
                ),
            ),
        )
    with pytest.raises(TypedValueModelCodecError, match="native_fields_invalid"):
        _encode(MemoryScope(), "SegmentGovernanceCarrierSet", publication)
    carrier_set = _carrier_set()
    with pytest.raises(TypedValueModelCodecError, match="candidate_native_roundtrip_mismatch"):
        _encode(
            _ImpostorCarrierSet(**carrier_set.__dict__),
            "SegmentGovernanceCarrierSet",
            publication,
        )
    with pytest.raises(TypedValueModelCodecError, match="native_fields_invalid"):
        _encode(
            SourceSpan.model_construct(source_id="source-1", start=2),
            "SourceSpan",
            publication,
        )
    with pytest.raises(TypedValueModelCodecError, match="native_integer_invalid"):
        _encode(
            SourceSpan.model_construct(source_id="source-1", start="2", end=7),
            "SourceSpan",
            publication,
        )


def test_candidate_encoding_obeys_exact_and_one_below_byte_node_and_depth_limits(tmp_path: Path) -> None:
    publication = _publication(tmp_path)
    value = _carrier_set()
    full = _encode(value, "SegmentGovernanceCarrierSet", publication)
    exact_bytes = len(full.body.raw_bytes)

    assert _encode(value, "SegmentGovernanceCarrierSet", publication, maximum_bytes=exact_bytes).body.raw_bytes == full.body.raw_bytes
    with pytest.raises(TypedValueModelCodecError, match="bytes_limit_exceeded"):
        _encode(value, "SegmentGovernanceCarrierSet", publication, maximum_bytes=exact_bytes - 1)

    exact_nodes, exact_depth = _raw_tree_limits(full.body.raw_bytes)
    assert exact_nodes == 50
    assert exact_depth > 1
    assert _encode(value, "SegmentGovernanceCarrierSet", publication, maximum_nodes=exact_nodes).body.raw_bytes == full.body.raw_bytes
    with pytest.raises(TypedValueModelCodecError) as node_error:
        _encode(value, "SegmentGovernanceCarrierSet", publication, maximum_nodes=exact_nodes - 1)
    _assert_body_limit_cause(node_error.value, "nodes")

    assert _encode(value, "SegmentGovernanceCarrierSet", publication, maximum_depth=exact_depth).body.raw_bytes == full.body.raw_bytes
    with pytest.raises(TypedValueModelCodecError) as depth_error:
        _encode(value, "SegmentGovernanceCarrierSet", publication, maximum_depth=exact_depth - 1)
    _assert_body_limit_cause(depth_error.value, "depth")
