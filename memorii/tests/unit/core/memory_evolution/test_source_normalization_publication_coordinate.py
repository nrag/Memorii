"""Focused proof for the graph-free source-normalization publication coordinate."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
)
from memorii.core.memory_evolution.semantic_analysis.decision_contracts import (
    SourceNormalizationEvidenceEntry,
    SourceNormalizationEvidenceManifest,
    SourceNormalizationPublicationCoordinate,
)
from pydantic import ValidationError


def _fence() -> OperationFenceBinding:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:coordinate",
        tenant_partition_id="tenant:coordinate",
        provider_identity="provider:coordinate",
    )
    return OperationFenceBinding.create(
        operation_id="operation:coordinate",
        source_id="source:coordinate",
        source_digest=sha256(b"source:coordinate").hexdigest(),
        delivery_identity=DeliveryIdentity.create(principal, "delivery:coordinate"),
    )


def _hand_ctv(value: object) -> bytes:
    """Independent minimal CTV writer for the frozen coordinate vector."""
    def wire(item: object) -> object:
        if item is None or isinstance(item, (bool, str)):
            return item
        if isinstance(item, int):
            return {"$type": "integer", "value": str(item)}
        if isinstance(item, bytes):
            return {"$type": "bytes", "value": base64.b64encode(item).decode("ascii")}
        if isinstance(item, tuple):
            return {"$type": "tuple", "items": [wire(child) for child in item]}
        if isinstance(item, Mapping):
            return {"$type": "map", "entries": [[key, wire(item[key])] for key in sorted(item)]}
        raise TypeError(f"unsupported hand-authored CTV member: {type(item).__name__}")

    return json.dumps(wire(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _coordinate() -> SourceNormalizationPublicationCoordinate:
    return SourceNormalizationPublicationCoordinate.create(
        operation_fence_binding=_fence(), expected_current_artifact_generation=41
    )


def _digest(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


def _entry(*, kind: str = "parser", number: int = 1) -> SourceNormalizationEvidenceEntry:
    return SourceNormalizationEvidenceEntry.create(
        kind=kind,  # type: ignore[arg-type]
        operation_id=f"operation:{number}",
        proposal_id=f"proposal:{number}",
        segment_id=f"segment:{number}",
        preparation_fingerprint=_digest("preparation"),
        segment_language_route_digest=_digest(f"route:{number}"),
        artifact_digest=_digest(f"artifact:{number}"),
        selection_digest=_digest(f"selection:{number}"),
        retention="aligned" if number == 1 else "terminal_unaligned",
    )


def _manifest(entries: tuple[SourceNormalizationEvidenceEntry, ...] | None = None) -> SourceNormalizationEvidenceManifest:
    coordinate = _coordinate()
    return SourceNormalizationEvidenceManifest.create(
        source_id=coordinate.operation_fence_binding.source_id,
        source_digest=coordinate.operation_fence_binding.source_digest,
        preparation_fingerprint=_digest("preparation"),
        source_normalization_request_digest=_digest("request"),
        consensus_policy_selection_bundle_digest=_digest("selections"),
        language_construction_policy_bundle_digest=_digest("policies"),
        publication_coordinate=coordinate,
        retained_entries=entries if entries is not None else (_entry(kind="parser", number=1), _entry(kind="scope", number=2)),
    )


def test_coordinate_has_a_hand_authored_ctv_digest_vector() -> None:
    coordinate = _coordinate()
    body = {
        "operation_fence_binding": coordinate.operation_fence_binding.model_dump(mode="python"),
        "expected_current_artifact_generation": 41,
        "next_publication_generation": 42,
    }
    expected = sha256(
        b"memorii.semantic-ingestion.source-normalization-publication-coordinate.v1\0" + _hand_ctv(body)
    ).hexdigest()

    assert coordinate.coordinate_digest == expected
    assert SourceNormalizationPublicationCoordinate.model_validate(
        {**body, "coordinate_digest": expected}
    ) == coordinate


@pytest.mark.parametrize(
    "field, value",
    (
        ("operation_fence_binding", _fence().model_copy(update={"binding_digest": "0" * 64})),
        ("expected_current_artifact_generation", 40),
        ("next_publication_generation", 43),
        ("coordinate_digest", "0" * 64),
    ),
)
def test_coordinate_rejects_each_mutated_declared_field(field: str, value: object) -> None:
    coordinate = _coordinate()
    with pytest.raises(ValidationError):
        SourceNormalizationPublicationCoordinate.model_validate({**coordinate.model_dump(mode="python"), field: value})


@pytest.mark.parametrize("generation", (-1, True, "41"))
def test_coordinate_create_rejects_invalid_expected_generation(generation: object) -> None:
    with pytest.raises(ValueError):
        SourceNormalizationPublicationCoordinate.create(
            operation_fence_binding=_fence(), expected_current_artifact_generation=generation  # type: ignore[arg-type]
        )


def test_coordinate_is_closed_frozen_and_enforces_exact_successor_generation() -> None:
    coordinate = _coordinate()
    for required_field in type(coordinate).model_fields:
        payload = coordinate.model_dump(mode="python")
        del payload[required_field]
        with pytest.raises(ValidationError):
            SourceNormalizationPublicationCoordinate.model_validate(payload)
    with pytest.raises(ValidationError):
        SourceNormalizationPublicationCoordinate.model_validate(
            {**coordinate.model_dump(mode="python"), "unexpected": "field"}
        )
    with pytest.raises(ValidationError):
        SourceNormalizationPublicationCoordinate.model_validate(
            {**coordinate.model_dump(mode="python"), "expected_current_artifact_generation": "41"}
        )
    with pytest.raises(ValidationError):
        SourceNormalizationPublicationCoordinate.model_validate(
            {
                **coordinate.model_dump(mode="python"),
                "next_publication_generation": coordinate.expected_current_artifact_generation,
            }
        )
    with pytest.raises(ValidationError):
        coordinate.expected_current_artifact_generation = 99  # type: ignore[misc]


def test_evidence_entry_and_manifest_have_hand_authored_ctv_digest_vectors() -> None:
    entry = _entry()
    entry_body = entry.model_dump(mode="python", exclude={"entry_digest"})
    assert entry.entry_digest == sha256(
        b"memorii.semantic-ingestion.source-normalization-evidence-entry.v1\0" + _hand_ctv(entry_body)
    ).hexdigest()

    manifest = _manifest()
    manifest_body = manifest.model_dump(mode="python", exclude={"manifest_digest"})
    assert manifest.manifest_digest == sha256(
        b"memorii.semantic-ingestion.source-normalization-evidence-manifest.v1\0" + _hand_ctv(manifest_body)
    ).hexdigest()


def test_evidence_entry_rejects_every_field_mutation_and_wrong_literals() -> None:
    entry = _entry()
    mutations = {
        "kind": "other",
        "operation_id": "operation:other",
        "proposal_id": "proposal:other",
        "segment_id": "segment:other",
        "segment_language_route_digest": _digest("route:other"),
        "artifact_digest": _digest("artifact:other"),
        "selection_digest": _digest("selection:other"),
        "retention": "other",
        "entry_digest": "0" * 64,
    }
    for field, value in mutations.items():
        with pytest.raises(ValidationError):
            SourceNormalizationEvidenceEntry.model_validate({**entry.model_dump(mode="python"), field: value})
    with pytest.raises(ValidationError):
        SourceNormalizationEvidenceEntry.model_validate(
            {**entry.model_dump(mode="python"), "artifact_digest": "A" * 64}
        )


def test_manifest_rejects_every_field_mutation_and_wrong_literals() -> None:
    manifest = _manifest()
    forged_coordinate = manifest.publication_coordinate.model_copy(update={"coordinate_digest": "0" * 64})
    mutations = {
        "source_id": "source:other",
        "source_digest": _digest("source:other"),
        "source_normalization_request_digest": _digest("request:other"),
        "consensus_policy_selection_bundle_digest": _digest("selections:other"),
        "language_construction_policy_bundle_digest": _digest("policies:other"),
        "publication_coordinate": forged_coordinate,
        "retained_entries": tuple(reversed(manifest.retained_entries)),
        "completeness": "partial",
        "bijection_verified": False,
        "manifest_digest": "0" * 64,
    }
    for field, value in mutations.items():
        with pytest.raises(ValidationError):
            SourceNormalizationEvidenceManifest.model_validate({**manifest.model_dump(mode="python"), field: value})


def test_manifest_rejects_noncanonical_order_and_duplicate_coordinate_artifact_or_selection() -> None:
    first = _entry(kind="parser", number=1)
    second = _entry(kind="scope", number=2)
    with pytest.raises(ValidationError, match="canonically ordered"):
        SourceNormalizationEvidenceManifest.create(
            source_id=_coordinate().operation_fence_binding.source_id,
            source_digest=_coordinate().operation_fence_binding.source_digest,
            preparation_fingerprint=_digest("preparation"),
            source_normalization_request_digest=_digest("request"),
            consensus_policy_selection_bundle_digest=_digest("selections"),
            language_construction_policy_bundle_digest=_digest("policies"),
            publication_coordinate=_coordinate(),
            retained_entries=(second, first),
        )
    duplicate_coordinate = SourceNormalizationEvidenceEntry.create(
        kind=first.kind,
        operation_id=first.operation_id,
        proposal_id=first.proposal_id,
        segment_id=first.segment_id,
        preparation_fingerprint=first.preparation_fingerprint,
        segment_language_route_digest=first.segment_language_route_digest,
        artifact_digest=_digest("artifact:coordinate-duplicate"),
        selection_digest=_digest("selection:coordinate-duplicate"),
        retention=first.retention,
    )
    duplicate_artifact = SourceNormalizationEvidenceEntry.create(
        kind="scope",
        operation_id="operation:artifact-duplicate",
        proposal_id="proposal:artifact-duplicate",
        segment_id="segment:artifact-duplicate",
        preparation_fingerprint=first.preparation_fingerprint,
        segment_language_route_digest=_digest("route:artifact-duplicate"),
        artifact_digest=first.artifact_digest,
        selection_digest=_digest("selection:artifact-duplicate"),
        retention="aligned",
    )
    duplicate_selection = SourceNormalizationEvidenceEntry.create(
        kind="temporal_attachment",
        operation_id="operation:selection-duplicate",
        proposal_id="proposal:selection-duplicate",
        segment_id="segment:selection-duplicate",
        preparation_fingerprint=first.preparation_fingerprint,
        segment_language_route_digest=_digest("route:selection-duplicate"),
        artifact_digest=_digest("artifact:selection-duplicate"),
        selection_digest=first.selection_digest,
        retention="aligned",
    )
    for duplicate in (duplicate_coordinate, duplicate_artifact, duplicate_selection):
        with pytest.raises(ValidationError, match="one-to-one"):
            _manifest(tuple(sorted((first, duplicate), key=lambda entry: entry.canonical_order_key())))


def test_evidence_contracts_are_closed_frozen_and_require_every_field() -> None:
    for value, contract_type in (
        (_entry(), SourceNormalizationEvidenceEntry),
        (_manifest(), SourceNormalizationEvidenceManifest),
    ):
        for required_field in contract_type.model_fields:
            payload = value.model_dump(mode="python")
            del payload[required_field]
            with pytest.raises(ValidationError):
                contract_type.model_validate(payload)
        with pytest.raises(ValidationError):
            contract_type.model_validate({**value.model_dump(mode="python"), "unexpected": "field"})
        with pytest.raises(ValidationError):
            setattr(value, next(iter(contract_type.model_fields)), "mutated")
