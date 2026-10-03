"""Revocation-directive record grammar, codec, and reference-edge contracts."""

from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.graph_records import (
    ClaimRevocationTarget,
    EntityRevocationTarget,
    GraphRecordKind,
    RecordRevocationTarget,
    RevocationClosureCoordinate,
    RevocationDirectiveRecord,
    SnapshotGraphRecord,
    SourceRevocationTarget,
    canonical_graph_codec_manifest,
    canonical_graph_record_adapter,
    graph_digest,
    graph_record_id,
    graph_record_union_member,
)
from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueError
from memorii.core.memory_evolution.reference_integrity import (
    ReferenceTarget,
    extract_reference_edges,
    generated_reference_schema_manifest,
)
from pydantic import ValidationError

NOW = datetime.now(UTC)
CLOSURE_EMPTY = graph_digest(b"memorii.revocation-closure.v1\0", ())
CODEC = {
    item.record_kind: item for item in canonical_graph_codec_manifest().entries
}["revocation_directive"]


def _directive(**overrides):
    values = {
        "operation_id": "governance:forget:0001",
        "revocation_id": "revocation:supp:0001",
        "suppression_id": "a" * 64,
        "revoked_targets": (EntityRevocationTarget(logical_entity_id="entity:alice"),),
        "closure_coordinates": (),
        "closure_digest": CLOSURE_EMPTY,
        "authority_capability_digest": "b" * 64,
        "control_journal_position": 1,
        "applied_at": NOW,
        "scope_note_digest": "c" * 64,
        "codec_fingerprint": CODEC.codec_fingerprint,
    }
    return RevocationDirectiveRecord.create(**(values | overrides))


def test_directive_is_a_closed_union_member_with_total_manifests() -> None:
    assert "revocation_directive" in GraphRecordKind.__args__
    codec_kinds = tuple(
        sorted(item.record_kind for item in canonical_graph_codec_manifest().entries)
    )
    assert codec_kinds == tuple(sorted(GraphRecordKind.__args__))
    reference_kinds = tuple(
        sorted(item.record_kind for item in generated_reference_schema_manifest().schema_entries)
    )
    assert reference_kinds == tuple(sorted(GraphRecordKind.__args__))


def test_directive_self_validates_and_round_trips_through_the_union() -> None:
    directive = _directive()
    assert graph_record_id(directive) == "revocation:supp:0001"
    assert graph_record_union_member(directive)
    roundtrip = canonical_graph_record_adapter().validate_python(
        directive.model_dump(mode="python")
    )
    assert roundtrip == directive


def test_snapshot_record_binding_accepts_a_directive_payload() -> None:
    directive = _directive()
    snapshot = SnapshotGraphRecord(
        record_id=directive.revocation_id,
        record_version=directive.record_version,
        payload=directive,
        codec_fingerprint=CODEC.codec_fingerprint,
        persistence_schema_fingerprint=CODEC.payload_schema_fingerprint,
        record_digest=directive.record_digest,
    )
    assert snapshot.payload_record_kind == "revocation_directive"


def test_every_target_variant_is_accepted_and_extracted() -> None:
    closure = (
        RevocationClosureCoordinate(record_kind="claim_assertion", record_id="claim:v1"),
        RevocationClosureCoordinate(record_kind="entity_revision", record_id="entity:alice:v1"),
    )
    closure_digest = graph_digest(
        b"memorii.revocation-closure.v1\0",
        tuple(item.model_dump(mode="python") for item in closure),
    )
    directive = _directive(
        revoked_targets=(
            ClaimRevocationTarget(claim_assertion_id="claim:v1"),
            EntityRevocationTarget(logical_entity_id="entity:alice"),
            RecordRevocationTarget(record_kind="entity_revision", record_id="entity:alice:v1"),
            SourceRevocationTarget(source_id="source:test"),
        ),
        closure_coordinates=closure,
        closure_digest=closure_digest,
    )
    edges = extract_reference_edges(directive)
    assert edges == (
        (
            "revoked_targets[].logical_entity_id",
            ReferenceTarget(kind="logical_entity", target_id="entity:alice"),
        ),
    )


def test_directive_rejects_non_canonical_and_incomplete_shapes() -> None:
    with pytest.raises(ValidationError):
        _directive(revoked_targets=())
    with pytest.raises(ValidationError):
        _directive(
            revoked_targets=(
                EntityRevocationTarget(logical_entity_id="entity:z"),
                EntityRevocationTarget(logical_entity_id="entity:a"),
            ),
        )
    with pytest.raises(ValidationError):
        _directive(revoked_targets=(SourceRevocationTarget(source_id="source:a"),),
                   closure_digest="0" * 64)
    with pytest.raises((ValidationError, CanonicalTypedValueError)):
        _directive(applied_at=datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        _directive(suppression_id="not-a-digest")
    with pytest.raises(ValidationError):
        _directive(control_journal_position=0)
    unknown_target = {"target_kind": "notebook", "logical_entity_id": "entity:x"}
    with pytest.raises(ValidationError):
        canonical_graph_record_adapter().validate_python(
            _directive().model_dump(mode="python")
            | {"revoked_targets": (unknown_target,)}
        )
    with pytest.raises(ValidationError):
        canonical_graph_record_adapter().validate_python(
            _directive().model_dump(mode="python") | {"unrecognized_field": True}
        )
    with pytest.raises(ValidationError):
        canonical_graph_record_adapter().validate_python(
            _directive().model_dump(mode="python") | {"record_kind": "revocation_report"}
        )


def test_directive_payload_carries_only_coordinates_and_digests() -> None:
    """The record is content-free: every field is an id, coordinate, digest, or clock."""

    allowed = {
        "record_kind", "operation_id", "record_version", "codec_fingerprint", "record_digest",
        "revocation_id", "suppression_id", "revoked_targets", "closure_coordinates",
        "closure_digest", "authority_capability_digest", "control_journal_position",
        "applied_at", "scope_note_digest",
    }
    assert set(RevocationDirectiveRecord.model_fields) == allowed
