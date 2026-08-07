"""Graph-free decision contracts owned by semantic analysis."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import OperationFenceBinding, encode_typed_value

_PUBLICATION_COORDINATE_DOMAIN = b"memorii.semantic-ingestion.source-normalization-publication-coordinate.v1"
_EVIDENCE_ENTRY_DOMAIN = b"memorii.semantic-ingestion.source-normalization-evidence-entry.v1"
_EVIDENCE_MANIFEST_DOMAIN = b"memorii.semantic-ingestion.source-normalization-evidence-manifest.v1"


def _canonical_ctv_value(value: object) -> object:
    """Lower typed contract values to the CTV data algebra before hashing."""
    if isinstance(value, BaseModel):
        return {name: _canonical_ctv_value(getattr(value, name)) for name in type(value).model_fields}
    if isinstance(value, Mapping):
        return {key: _canonical_ctv_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical_ctv_value(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_canonical_ctv_value(item) for item in value)
    return value


def _coordinate_digest(
    operation_fence_binding: OperationFenceBinding,
    expected_current_artifact_generation: int,
    next_publication_generation: int,
) -> str:
    body = {
        "operation_fence_binding": operation_fence_binding,
        "expected_current_artifact_generation": expected_current_artifact_generation,
        "next_publication_generation": next_publication_generation,
    }
    return sha256(_PUBLICATION_COORDINATE_DOMAIN + b"\0" + encode_typed_value(_canonical_ctv_value(body))).hexdigest()


def _content_digest(domain: bytes, body: object) -> str:
    return sha256(domain + b"\0" + encode_typed_value(_canonical_ctv_value(body))).hexdigest()


class SourceNormalizationPublicationCoordinate(BaseModel):
    """Exact fence and generation pair required before source normalization publishes."""

    operation_fence_binding: OperationFenceBinding
    expected_current_artifact_generation: int = Field(ge=0)
    next_publication_generation: int = Field(ge=1)
    coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_coordinate(self) -> SourceNormalizationPublicationCoordinate:
        try:
            OperationFenceBinding.model_validate(self.operation_fence_binding.model_dump(mode="python"))
        except (TypeError, ValueError) as exc:
            raise ValueError("source normalization publication fence is invalid") from exc
        if self.next_publication_generation != self.expected_current_artifact_generation + 1:
            raise ValueError("next publication generation must equal expected current generation plus one")
        if self.coordinate_digest != _coordinate_digest(
            self.operation_fence_binding,
            self.expected_current_artifact_generation,
            self.next_publication_generation,
        ):
            raise ValueError("source normalization publication coordinate digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        operation_fence_binding: OperationFenceBinding,
        expected_current_artifact_generation: int,
    ) -> SourceNormalizationPublicationCoordinate:
        """Create the only valid successor coordinate for a current generation."""
        if type(expected_current_artifact_generation) is not int or expected_current_artifact_generation < 0:
            raise ValueError("expected current artifact generation must be a non-negative integer")
        if not isinstance(operation_fence_binding, OperationFenceBinding):
            raise ValueError("operation fence binding must be an OperationFenceBinding")
        validated_fence = OperationFenceBinding.model_validate(operation_fence_binding.model_dump(mode="python"))
        next_publication_generation = expected_current_artifact_generation + 1
        return cls(
            operation_fence_binding=validated_fence,
            expected_current_artifact_generation=expected_current_artifact_generation,
            next_publication_generation=next_publication_generation,
            coordinate_digest=_coordinate_digest(
                validated_fence,
                expected_current_artifact_generation,
                next_publication_generation,
            ),
        )


class SourceNormalizationEvidenceEntry(BaseModel):
    """One retained graph-free consensus artifact and its exact selection."""

    kind: Literal["parser", "scope", "temporal_attachment"]
    operation_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    retention: Literal["aligned", "terminal_unaligned"]
    entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_entry_digest(self) -> SourceNormalizationEvidenceEntry:
        body = {name: getattr(self, name) for name in type(self).model_fields if name != "entry_digest"}
        if self.entry_digest != _content_digest(_EVIDENCE_ENTRY_DOMAIN, body):
            raise ValueError("source normalization evidence entry digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        kind: Literal["parser", "scope", "temporal_attachment"],
        operation_id: str,
        proposal_id: str,
        segment_id: str,
        preparation_fingerprint: str,
        segment_language_route_digest: str,
        artifact_digest: str,
        selection_digest: str,
        retention: Literal["aligned", "terminal_unaligned"],
    ) -> SourceNormalizationEvidenceEntry:
        """Create an entry from its complete retained-artifact coordinate."""
        body = {
            "kind": kind,
            "operation_id": operation_id,
            "proposal_id": proposal_id,
            "segment_id": segment_id,
            "preparation_fingerprint": preparation_fingerprint,
            "segment_language_route_digest": segment_language_route_digest,
            "artifact_digest": artifact_digest,
            "selection_digest": selection_digest,
            "retention": retention,
        }
        return cls(**body, entry_digest=_content_digest(_EVIDENCE_ENTRY_DOMAIN, body))

    def canonical_order_key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.kind,
            self.operation_id,
            self.proposal_id,
            self.segment_id,
            self.segment_language_route_digest,
            self.artifact_digest,
        )

    def coordinate_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.kind,
            self.operation_id,
            self.proposal_id,
            self.segment_id,
            self.segment_language_route_digest,
        )


class SourceNormalizationEvidenceManifest(BaseModel):
    """Complete, replay-authoritative retained evidence for one normalized source."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_normalization_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_policy_selection_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_construction_policy_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_coordinate: SourceNormalizationPublicationCoordinate
    retained_entries: tuple[SourceNormalizationEvidenceEntry, ...]
    completeness: Literal["complete"]
    bijection_verified: Literal[True]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_manifest(self) -> SourceNormalizationEvidenceManifest:
        try:
            coordinate = SourceNormalizationPublicationCoordinate.model_validate(
                self.publication_coordinate.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("source normalization evidence manifest publication coordinate is invalid") from exc
        if (
            coordinate.operation_fence_binding.source_id != self.source_id
            or coordinate.operation_fence_binding.source_digest != self.source_digest
        ):
            raise ValueError("source normalization evidence manifest source does not match publication coordinate")
        if any(entry.preparation_fingerprint != self.preparation_fingerprint for entry in self.retained_entries):
            raise ValueError("source normalization retained entries must match preparation fingerprint")
        ordered_keys = tuple(entry.canonical_order_key() for entry in self.retained_entries)
        if ordered_keys != tuple(sorted(ordered_keys)):
            raise ValueError("source normalization retained entries must be canonically ordered")
        coordinate_keys = tuple(entry.coordinate_key() for entry in self.retained_entries)
        artifact_digests = tuple(entry.artifact_digest for entry in self.retained_entries)
        selection_digests = tuple(entry.selection_digest for entry in self.retained_entries)
        if (
            len(set(coordinate_keys)) != len(coordinate_keys)
            or len(set(artifact_digests)) != len(artifact_digests)
            or len(set(selection_digests)) != len(selection_digests)
        ):
            raise ValueError("source normalization retained entries must form a one-to-one coordinate, artifact, and selection map")
        body = {name: getattr(self, name) for name in type(self).model_fields if name != "manifest_digest"}
        if self.manifest_digest != _content_digest(_EVIDENCE_MANIFEST_DOMAIN, body):
            raise ValueError("source normalization evidence manifest digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        source_digest: str,
        preparation_fingerprint: str,
        source_normalization_request_digest: str,
        consensus_policy_selection_bundle_digest: str,
        language_construction_policy_bundle_digest: str,
        publication_coordinate: SourceNormalizationPublicationCoordinate,
        retained_entries: tuple[SourceNormalizationEvidenceEntry, ...],
    ) -> SourceNormalizationEvidenceManifest:
        """Create a complete manifest with its required closed literals."""
        body = {
            "source_id": source_id,
            "source_digest": source_digest,
            "preparation_fingerprint": preparation_fingerprint,
            "source_normalization_request_digest": source_normalization_request_digest,
            "consensus_policy_selection_bundle_digest": consensus_policy_selection_bundle_digest,
            "language_construction_policy_bundle_digest": language_construction_policy_bundle_digest,
            "publication_coordinate": publication_coordinate,
            "retained_entries": retained_entries,
            "completeness": "complete",
            "bijection_verified": True,
        }
        return cls(**body, manifest_digest=_content_digest(_EVIDENCE_MANIFEST_DOMAIN, body))


__all__ = [
    "SourceNormalizationEvidenceEntry",
    "SourceNormalizationEvidenceManifest",
    "SourceNormalizationPublicationCoordinate",
]
