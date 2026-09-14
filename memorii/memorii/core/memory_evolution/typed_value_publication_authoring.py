"""Offline construction of an immutable profile-3 publication package.

The author accepts already-read declaration bytes and an explicit finite source
selection.  It neither imports decoders nor creates deployment pins or vector
claims; those boundaries remain with later publication and composition owners.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from memorii.core.memory_evolution.typed_value_declarations import (
    DeclarationParseError,
    DecoderRole,
    ParsedDeclaration,
    ProtectedDeclarationParseLimits,
    RegistryRole,
    SchemaRole,
    parse_typed_value_declaration,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    DecoderSourceSelection,
    VerifiedDecoderSourceManifest,
    capture_decoder_source_files,
    verify_decoder_source_manifest,
)
from memorii.core.memory_evolution.typed_value_publication import (
    ProtectedTypedValuePublicationLimits,
    TypedValuePublicationError,
    parse_typed_value_publication_manifest,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledTypedValueRegistry,
    TypedValueRegistryCompilationError,
    author_typed_value_registry_role,
    compile_typed_value_registry,
    typed_value_declaration_role_descriptor,
)

_DECODER_PREFIX = "memorii.semantic_ingestion.observation."


class TypedValuePublicationAuthoringError(ValueError):
    """Offline package inputs cannot form one closed publication authority."""


@dataclass(frozen=True)
class AuthoredTypedValuePublicationPackage:
    """Exact immutable construction bytes, without deployment verification claims."""

    raw_role_sources: tuple[bytes, ...]
    raw_decoder_source_manifest: bytes
    raw_publication_manifest: bytes
    compiled_registry: CompiledTypedValueRegistry
    verified_decoder_sources: VerifiedDecoderSourceManifest


def author_typed_value_publication_package(
    raw_non_decoder_non_registry_role_sources: Iterable[bytes],
    decoder_source_selections: tuple[DecoderSourceSelection, ...],
    *,
    source_package_root: Path,
    limits: ProtectedTypedValuePublicationLimits,
    forbidden_decoder_source_paths: frozenset[str] = frozenset(),
) -> AuthoredTypedValuePublicationPackage:
    """Build canonical package bytes from finite raw roles and file selections.

    Decoder declarations and the registry declaration are derived here so no
    caller can supply stale source digests or registry entry commitments.
    """
    raw_roles = tuple(raw_non_decoder_non_registry_role_sources)
    parsed = _parse_authoring_roles(raw_roles, limits.declaration_limits)
    expected_decoder_ids = _expected_decoder_ids(parsed)
    _validate_selection_closure(decoder_source_selections, expected_decoder_ids)
    try:
        captured = capture_decoder_source_files(
            decoder_source_selections,
            source_package_root=source_package_root,
            limits=limits.decoder_source_limits,
            forbidden_relative_paths=forbidden_decoder_source_paths,
        )
    except DecoderSourceManifestError as exc:
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_source_capture_invalid") from exc
    raw_decoder_manifest = _canonical_json(
        {
            "role": "decoder_source_manifest",
            "profile_id": "semantic_ingestion_typed_value",
            "profile_version": "3",
            "files": [
                {
                    "decoder_id": item.decoder_id,
                    "source_file_id": item.source_file_id,
                    "relative_path": item.relative_path,
                    "sha256": item.sha256,
                }
                for item in captured
            ],
        }
    )
    try:
        verified_sources = verify_decoder_source_manifest(
            raw_decoder_manifest,
            source_package_root=source_package_root,
            limits=limits.decoder_source_limits,
            forbidden_relative_paths=forbidden_decoder_source_paths,
        )
    except DecoderSourceManifestError as exc:
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_source_manifest_invalid") from exc
    decoder_digests = {item.decoder_id: item.source_snapshot_digest for item in verified_sources.snapshots}
    decoder_roles = _author_decoder_roles(parsed, decoder_digests)
    non_registry_roles = (*raw_roles, *decoder_roles)
    try:
        raw_registry_role = author_typed_value_registry_role(non_registry_roles, limits=limits.declaration_limits)
        all_roles = (*non_registry_roles, raw_registry_role)
        registry = compile_typed_value_registry(all_roles, limits=limits.declaration_limits)
    except (DeclarationParseError, TypedValueRegistryCompilationError) as exc:
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_registry_invalid") from exc
    raw_publication_manifest = _canonical_json(
        {
            "role": "publication_manifest",
            "profile_id": "semantic_ingestion_typed_value",
            "profile_version": "3",
            "files": [
                {"role": typed_value_declaration_role_descriptor(item), "sha256": sha256(item.raw_bytes).hexdigest()}
                for item in sorted(registry.parsed_roles, key=lambda item: typed_value_declaration_role_descriptor(item).encode("utf-8"))
            ],
            "decoder_source_manifest_digest": sha256(raw_decoder_manifest).hexdigest(),
            "decoder_source_snapshots": [
                {"decoder_id": item.decoder_id, "source_snapshot_digest": item.source_snapshot_digest}
                for item in verified_sources.snapshots
            ],
            "registry_digest": registry.registry_digest,
        }
    )
    try:
        parse_typed_value_publication_manifest(
            raw_publication_manifest, maximum_bytes=limits.maximum_publication_manifest_bytes
        )
    except TypedValuePublicationError as exc:
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_manifest_invalid") from exc
    return AuthoredTypedValuePublicationPackage(
        raw_role_sources=all_roles,
        raw_decoder_source_manifest=raw_decoder_manifest,
        raw_publication_manifest=raw_publication_manifest,
        compiled_registry=registry,
        verified_decoder_sources=verified_sources,
    )


def _parse_authoring_roles(
    raw_roles: tuple[bytes, ...], limits: ProtectedDeclarationParseLimits
) -> tuple[ParsedDeclaration, ...]:
    try:
        parsed = tuple(parse_typed_value_declaration(raw, limits=limits) for raw in raw_roles)
    except DeclarationParseError as exc:
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_raw_role_invalid") from exc
    if any(isinstance(item, (DecoderRole, RegistryRole)) for item in parsed):
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_supplied_decoder_or_registry_role")
    return parsed


def _expected_decoder_ids(parsed: tuple[ParsedDeclaration, ...]) -> dict[tuple[str, str], str]:
    schemas = [item for item in parsed if isinstance(item, SchemaRole)]
    expected = {
        (item.schema_id, item.schema_version): f"{_DECODER_PREFIX}{item.schema_id}.v{item.schema_version}"
        for item in schemas
    }
    if len(expected) != len(schemas):
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_schema_coordinate_duplicate")
    return expected


def _validate_selection_closure(
    selections: tuple[DecoderSourceSelection, ...], expected: dict[tuple[str, str], str]
) -> None:
    if type(selections) is not tuple:
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_selection_tuple_required")
    selected_ids: set[str] = set()
    for selection in selections:
        if type(selection) is not DecoderSourceSelection:
            raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_selection_invalid")
        selected_ids.add(selection.decoder_id)
    expected_ids = set(expected.values())
    if selected_ids != expected_ids:
        raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_decoder_selection_closure_invalid")


def _author_decoder_roles(
    parsed: tuple[ParsedDeclaration, ...], decoder_digests: dict[str, str]
) -> tuple[bytes, ...]:
    schemas = sorted(
        (item for item in parsed if isinstance(item, SchemaRole)),
        key=lambda item: (item.schema_id.encode("utf-8"), item.schema_version.encode("utf-8")),
    )
    result: list[bytes] = []
    for schema in schemas:
        decoder_id = f"{_DECODER_PREFIX}{schema.schema_id}.v{schema.schema_version}"
        digest = decoder_digests.get(decoder_id)
        if digest is None:
            raise TypedValuePublicationAuthoringError("typed_value_publication_authoring_decoder_snapshot_missing")
        result.append(
            _canonical_json(
                {
                    "role": "decoder",
                    "schema_id": schema.schema_id,
                    "schema_version": schema.schema_version,
                    "decoder_id": decoder_id,
                        "typed_root_kind": "model",
                    "implementation_source_digest": digest,
                }
            )
        )
    return tuple(result)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8", "strict")
