"""Protected profile-3 envelope intake before body interpretation.

The fixed envelope chooses an immutable historical entry before its opaque body
is parsed.  This is deliberately separate from the profile-2 artifact reader.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding, artifact_preimage
from memorii.core.memory_evolution.typed_value_body_validation import (
    ProtectedTypedValueBodyLimits,
    TypedValueBodyValidationError,
    ValidatedTypedValueBody,
    validate_typed_value_body,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    FrozenJsonValue,
    ProtectedDecoderSourceManifestLimits,
    parse_canonical_raw_json_object,
)
from memorii.core.memory_evolution.typed_value_model_codec import (
    MaterializedTypedValueModel,
    TypedValueModelCodecError,
    materialize_typed_value_model,
    reencode_materialized_typed_value_model,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
    ResolvedTypedValueRegistryHistoryEntry,
    TypedValueRegistryHistoryError,
    TypedValueRegistryReadRoute,
)

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_POSITIVE_UINT = re.compile(r"[1-9][0-9]*\Z")
_ENVELOPE_FIELDS = frozenset(("binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"))
_BINDING_FIELDS = frozenset(("profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"))


class TypedValueArtifactReaderError(ValueError):
    """The fixed profile-3 envelope is malformed or cannot select an entry."""


@dataclass(frozen=True)
class ProtectedTypedValueArtifactReaderLimits:
    maximum_envelope_bytes: int
    maximum_envelope_nodes: int
    maximum_envelope_depth: int
    body_limits: ProtectedTypedValueBodyLimits

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in (self.maximum_envelope_bytes, self.maximum_envelope_nodes, self.maximum_envelope_depth)):
            raise ValueError("typed_value_artifact_reader_envelope_limits_must_be_positive")
        if type(self.body_limits) is not ProtectedTypedValueBodyLimits:
            raise ValueError("typed_value_artifact_reader_body_limits_invalid")


@dataclass(frozen=True)
class CheckedTypedValueArtifact:
    """An envelope whose binding and exact opaque bytes have been checked."""

    raw_bytes: bytes
    binding: CanonicalTypedValueProfileBinding
    canonical_value_bytes: bytes
    canonical_value_digest: str
    artifact_digest: str
    selected_entry: ResolvedTypedValueRegistryHistoryEntry


@dataclass(frozen=True)
class UnauthenticatedTypedValueMaterialization:
    """Selected conversion only; it conveys no integrity or persistence authority."""

    checked_artifact: CheckedTypedValueArtifact
    validated_body: ValidatedTypedValueBody
    materialized: MaterializedTypedValueModel


def read_protected_typed_value_artifact(
    raw_bytes: bytes,
    *,
    history: ProtectedTypedValueRegistryHistory,
    route: TypedValueRegistryReadRoute,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> CheckedTypedValueArtifact:
    """Check fixed outer syntax, history-selected binding, and exact digests.

    The body is intentionally opaque until history resolution succeeds.
    """
    if type(history) is not ProtectedTypedValueRegistryHistory:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_history_invalid")
    if type(route) is not TypedValueRegistryReadRoute:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_route_invalid")
    try:
        parsed = parse_canonical_raw_json_object(raw_bytes, limits=_raw_limits(limits))
        outer = _map_fields(parsed.value, "envelope")
        if frozenset(outer) != _ENVELOPE_FIELDS:
            raise TypedValueArtifactReaderError("typed_value_artifact_reader_envelope_fields_invalid")
        binding = _binding(_map_fields(outer["binding"], "binding"))
        body = _bytes(outer["canonical_value_bytes"], "canonical_value_bytes")
        body_digest = _digest(outer["canonical_value_digest"], "canonical_value_digest")
        artifact_digest = _digest(outer["artifact_digest"], "artifact_digest")
    except DecoderSourceManifestError as exc:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_outer_invalid") from exc
    selected = _resolve(history, binding, route)
    if sha256(body).hexdigest() != body_digest:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_body_digest_mismatch")
    if sha256(artifact_preimage(binding, body)).hexdigest() != artifact_digest:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_artifact_digest_mismatch")
    return CheckedTypedValueArtifact(raw_bytes, binding, body, body_digest, artifact_digest, selected)


def validate_materialize_and_reencode_checked_typed_value_artifact(
    checked: CheckedTypedValueArtifact,
    *,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> UnauthenticatedTypedValueMaterialization:
    """Explicit later conversion after envelope checks; this is not authentication."""
    if type(checked) is not CheckedTypedValueArtifact:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_checked_artifact_invalid")
    selected = checked.selected_entry
    try:
        body = validate_typed_value_body(
            checked.canonical_value_bytes,
            registry=selected.publication.compiled_registry,
            entry=selected.entry,
            limits=limits.body_limits,
        )
        materialized = materialize_typed_value_model(
            body,
            publication=selected.publication,
            maximum_bytes=limits.body_limits.maximum_bytes,
            maximum_nodes=limits.body_limits.maximum_nodes,
            maximum_depth=limits.body_limits.maximum_depth,
        )
        if reencode_materialized_typed_value_model(
            materialized,
            publication=selected.publication,
            maximum_bytes=limits.body_limits.maximum_bytes,
            maximum_nodes=limits.body_limits.maximum_nodes,
            maximum_depth=limits.body_limits.maximum_depth,
        ) != checked.canonical_value_bytes:
            raise TypedValueArtifactReaderError("typed_value_artifact_reader_native_reencode_mismatch")
    except (TypedValueBodyValidationError, TypedValueModelCodecError) as exc:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_selected_body_invalid") from exc
    return UnauthenticatedTypedValueMaterialization(checked, body, materialized)


def _raw_limits(limits: ProtectedTypedValueArtifactReaderLimits) -> ProtectedDecoderSourceManifestLimits:
    return ProtectedDecoderSourceManifestLimits(limits.maximum_envelope_bytes, limits.maximum_envelope_nodes, limits.maximum_envelope_depth, 1, limits.maximum_envelope_bytes)


def _map_fields(value: FrozenJsonValue, path: str) -> dict[str, FrozenJsonValue]:
    if not isinstance(value, Mapping) or set(value) != {"$type", "entries"} or value.get("$type") != "map" or not isinstance(value.get("entries"), tuple):
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_map_invalid")
    result: dict[str, FrozenJsonValue] = {}
    previous: bytes | None = None
    entries = value["entries"]
    assert isinstance(entries, tuple)
    for pair in entries:
        if not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str):
            raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_entry_invalid")
        encoded = json.dumps(pair[0], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if previous is not None and encoded <= previous:
            raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_order_invalid")
        previous = encoded
        if pair[0] in result:
            raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_duplicate_invalid")
        result[pair[0]] = pair[1]
    return result


def _binding(value: dict[str, FrozenJsonValue]) -> CanonicalTypedValueProfileBinding:
    if frozenset(value) != _BINDING_FIELDS:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_binding_fields_invalid")
    profile_id = _string(value["profile_id"], "binding_profile_id")
    schema_id = _string(value["schema_id"], "binding_schema_id")
    profile_version = _positive_integer(value["profile_version"], "binding_profile_version")
    schema_version = _positive_integer(value["schema_version"], "binding_schema_version")
    return CanonicalTypedValueProfileBinding(profile_id, profile_version, _digest(value["profile_digest"], "binding_profile_digest"), schema_id, schema_version, _digest(value["binding_digest"], "binding_digest"))


def _string(value: FrozenJsonValue, path: str) -> str:
    if not isinstance(value, str):
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_invalid")
    return value


def _digest(value: FrozenJsonValue, path: str) -> str:
    result = _string(value, path)
    if _HEX.fullmatch(result) is None:
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_invalid")
    return result


def _positive_integer(value: FrozenJsonValue, path: str) -> int:
    if not isinstance(value, Mapping) or set(value) != {"$type", "value"} or value.get("$type") != "integer":
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_invalid")
    text = value.get("value")
    if not isinstance(text, str) or _POSITIVE_UINT.fullmatch(text) is None:
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_invalid")
    result = 0
    for offset in range(0, len(text), 9):
        chunk = text[offset:offset + 9]
        result = result * 10 ** len(chunk) + int(chunk)
    return result


def _bytes(value: FrozenJsonValue, path: str) -> bytes:
    if not isinstance(value, Mapping) or set(value) != {"$type", "value"} or value.get("$type") != "bytes" or not isinstance(value.get("value"), str):
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_invalid")
    encoded = value.get("value")
    if not isinstance(encoded, str):
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_invalid")
    try:
        result = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_invalid") from exc
    if base64.b64encode(result).decode("ascii") != encoded:
        raise TypedValueArtifactReaderError(f"typed_value_artifact_reader_{path}_invalid")
    return result


def _resolve(history: ProtectedTypedValueRegistryHistory, binding: CanonicalTypedValueProfileBinding, route: TypedValueRegistryReadRoute) -> ResolvedTypedValueRegistryHistoryEntry:
    try:
        return history.resolve(binding, route=route)
    except TypedValueRegistryHistoryError as exc:
        raise TypedValueArtifactReaderError("typed_value_artifact_reader_binding_unresolved") from exc

