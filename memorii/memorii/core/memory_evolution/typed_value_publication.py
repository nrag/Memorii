"""Protected join of typed-value declaration, decoder-source, and deployment inputs."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from memorii.core.memory_evolution.ingestion_contracts import length_prefixed
from memorii.core.memory_evolution.typed_value_declarations import (
    DeclarationParseError,
    ProtectedDeclarationParseLimits,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    FrozenJsonValue,
    ProtectedDecoderSourceManifestLimits,
    VerifiedDecoderSourceManifest,
    parse_canonical_manifest_object,
    verify_decoder_source_manifest,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledTypedValueRegistry,
    TypedValueRegistryCompilationError,
    compile_typed_value_registry,
    typed_value_declaration_role_descriptor,
)

_ASCII_ROLE = re.compile(r"[A-Za-z0-9._/-]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PROFILE_ID = "semantic_ingestion_typed_value"
_PROFILE_VERSION = "3"
_ROLE = "publication_manifest"
_DOMAIN = b"semantic-ingestion-profile3-publication-manifest"


class TypedValuePublicationError(ValueError):
    """The protected profile-3 publication inputs do not form one authority."""


@dataclass(frozen=True)
class ProtectedTypedValuePublicationLimits:
    declaration_limits: ProtectedDeclarationParseLimits
    decoder_source_limits: ProtectedDecoderSourceManifestLimits
    maximum_publication_manifest_bytes: int

    def __post_init__(self) -> None:
        if type(self.declaration_limits) is not ProtectedDeclarationParseLimits:
            raise ValueError("typed_value_publication_declaration_limits_invalid")
        if type(self.decoder_source_limits) is not ProtectedDecoderSourceManifestLimits:
            raise ValueError("typed_value_publication_decoder_source_limits_invalid")
        if type(self.maximum_publication_manifest_bytes) is not int or self.maximum_publication_manifest_bytes <= 0:
            raise ValueError("typed_value_publication_maximum_manifest_bytes_must_be_positive")


@dataclass(frozen=True)
class PublicationSourceFile:
    role: str
    sha256: str


@dataclass(frozen=True)
class PublicationDecoderSourceSnapshot:
    decoder_id: str
    source_snapshot_digest: str


@dataclass(frozen=True)
class TypedValuePublicationManifest:
    raw_bytes: bytes
    publication_digest: str
    profile_id: str
    profile_version: str
    files: tuple[PublicationSourceFile, ...]
    decoder_source_manifest_digest: str
    decoder_source_snapshots: tuple[PublicationDecoderSourceSnapshot, ...]
    registry_digest: str


@dataclass(frozen=True)
class DecoderSourceSnapshotPin:
    decoder_id: str
    source_snapshot_digest: str


@dataclass(frozen=True)
class ProtectedTypedValuePublicationPins:
    publication_digest: str
    registry_digest: str
    decoder_source_snapshots: tuple[DecoderSourceSnapshotPin, ...]
    independent_vector_manifest_digest: str

    def __post_init__(self) -> None:
        if type(self.decoder_source_snapshots) is not tuple:
            raise ValueError("typed_value_publication_pins_decoder_source_snapshots_tuple_required")
        if any(type(item) is not DecoderSourceSnapshotPin for item in self.decoder_source_snapshots):
            raise ValueError("typed_value_publication_pins_decoder_source_snapshot_invalid")
        for name, value in (
            ("publication_digest", self.publication_digest),
            ("registry_digest", self.registry_digest),
            ("independent_vector_manifest_digest", self.independent_vector_manifest_digest),
        ):
            _sha256_text(value, f"typed_value_publication.pins.{name}")
        _validate_snapshots(self.decoder_source_snapshots, "typed_value_publication.pins.decoder_source_snapshots")


@dataclass(frozen=True)
class VerifiedTypedValuePublication:
    compiled_registry: CompiledTypedValueRegistry
    verified_decoder_sources: VerifiedDecoderSourceManifest
    publication_manifest: TypedValuePublicationManifest
    pins: ProtectedTypedValuePublicationPins
    independent_vector_manifest_digest: str


def parse_typed_value_publication_manifest(
    raw_bytes: bytes, *, maximum_bytes: int
) -> TypedValuePublicationManifest:
    """Parse only the strict raw external publication-manifest grammar."""
    try:
        root = parse_canonical_manifest_object(raw_bytes, maximum_bytes=maximum_bytes)
    except DecoderSourceManifestError as exc:
        raise TypedValuePublicationError("typed_value_publication_manifest_raw_invalid") from exc
    _exact_keys(
        root,
        {
            "role",
            "profile_id",
            "profile_version",
            "files",
            "decoder_source_manifest_digest",
            "decoder_source_snapshots",
            "registry_digest",
        },
        "typed_value_publication_manifest",
    )
    _literal(root, "role", _ROLE, "typed_value_publication_manifest")
    _literal(root, "profile_id", _PROFILE_ID, "typed_value_publication_manifest")
    _literal(root, "profile_version", _PROFILE_VERSION, "typed_value_publication_manifest")
    files_value = root["files"]
    snapshots_value = root["decoder_source_snapshots"]
    if not isinstance(files_value, tuple) or not files_value:
        raise TypedValuePublicationError("typed_value_publication_manifest.files_invalid")
    if not isinstance(snapshots_value, tuple) or not snapshots_value:
        raise TypedValuePublicationError("typed_value_publication_manifest.decoder_source_snapshots_invalid")
    files = tuple(_parse_source_file(item) for item in files_value)
    snapshots = tuple(_parse_snapshot(item) for item in snapshots_value)
    _validate_source_files(files)
    _validate_snapshots(snapshots, "typed_value_publication_manifest.decoder_source_snapshots")
    decoder_source_manifest_digest = _sha256(root, "decoder_source_manifest_digest", "typed_value_publication_manifest")
    registry_digest = _sha256(root, "registry_digest", "typed_value_publication_manifest")
    publication_digest = _publication_digest(
        files,
        decoder_source_manifest_digest,
        snapshots,
        registry_digest,
    )
    return TypedValuePublicationManifest(
        raw_bytes=raw_bytes,
        publication_digest=publication_digest,
        profile_id=_PROFILE_ID,
        profile_version=_PROFILE_VERSION,
        files=files,
        decoder_source_manifest_digest=decoder_source_manifest_digest,
        decoder_source_snapshots=snapshots,
        registry_digest=registry_digest,
    )


def verify_typed_value_publication(
    raw_role_sources: Iterable[bytes],
    raw_decoder_source_manifest: bytes,
    raw_publication_manifest: bytes,
    raw_independent_vector_manifest: bytes,
    *,
    source_package_root: Path,
    limits: ProtectedTypedValuePublicationLimits,
    pins: ProtectedTypedValuePublicationPins,
    forbidden_decoder_source_paths: frozenset[str] = frozenset(),
) -> VerifiedTypedValuePublication:
    """Recompute every construction input before returning a protected result."""
    sources = tuple(raw_role_sources)
    try:
        registry = compile_typed_value_registry(sources, limits=limits.declaration_limits)
    except (DeclarationParseError, TypedValueRegistryCompilationError) as exc:
        raise TypedValuePublicationError("typed_value_publication_registry_compile_invalid") from exc
    try:
        decoder_sources = verify_decoder_source_manifest(
            raw_decoder_source_manifest,
            source_package_root=source_package_root,
            limits=limits.decoder_source_limits,
            forbidden_relative_paths=forbidden_decoder_source_paths,
        )
    except DecoderSourceManifestError as exc:
        raise TypedValuePublicationError("typed_value_publication_decoder_sources_invalid") from exc
    publication = parse_typed_value_publication_manifest(
        raw_publication_manifest,
        maximum_bytes=limits.maximum_publication_manifest_bytes,
    )
    _verify_source_role_files(sources, registry, publication.files)
    if publication.decoder_source_manifest_digest != decoder_sources.manifest.manifest_digest:
        raise TypedValuePublicationError("typed_value_publication_decoder_source_manifest_digest_mismatch")
    actual_snapshots = tuple(
        PublicationDecoderSourceSnapshot(item.decoder_id, item.source_snapshot_digest)
        for item in decoder_sources.snapshots
    )
    if publication.decoder_source_snapshots != actual_snapshots:
        raise TypedValuePublicationError("typed_value_publication_decoder_source_snapshots_mismatch")
    if publication.registry_digest != registry.registry_digest:
        raise TypedValuePublicationError("typed_value_publication_registry_digest_mismatch")
    _verify_decoder_entry_closure(registry, decoder_sources)
    _verify_pins(publication, registry, actual_snapshots, raw_independent_vector_manifest, pins)
    return VerifiedTypedValuePublication(
        compiled_registry=registry,
        verified_decoder_sources=decoder_sources,
        publication_manifest=publication,
        pins=pins,
        independent_vector_manifest_digest=sha256(raw_independent_vector_manifest).hexdigest(),
    )


def _verify_source_role_files(
    raw_role_sources: tuple[bytes, ...],
    registry: CompiledTypedValueRegistry,
    manifest_files: tuple[PublicationSourceFile, ...],
) -> None:
    expected: dict[str, str] = {}
    for parsed in registry.parsed_roles:
        role = typed_value_declaration_role_descriptor(parsed)
        digest = sha256(parsed.raw_bytes).hexdigest()
        if role in expected:
            raise TypedValuePublicationError("typed_value_publication_source_role_duplicate")
        expected[role] = digest
    if len(raw_role_sources) != len(expected):
        raise TypedValuePublicationError("typed_value_publication_source_role_count_mismatch")
    actual = tuple((item.role, item.sha256) for item in manifest_files)
    expected_files = tuple(sorted(expected.items(), key=lambda item: item[0].encode("utf-8")))
    if actual != expected_files:
        raise TypedValuePublicationError("typed_value_publication_source_role_files_mismatch")


def _verify_decoder_entry_closure(
    registry: CompiledTypedValueRegistry, decoder_sources: VerifiedDecoderSourceManifest
) -> None:
    snapshots = {item.decoder_id: item.source_snapshot_digest for item in decoder_sources.snapshots}
    entries = {entry.decoder_id: entry.implementation_source_digest for entry in registry.entries}
    if len(entries) != len(registry.entries) or entries != snapshots:
        raise TypedValuePublicationError("typed_value_publication_decoder_snapshot_closure_mismatch")


def _verify_pins(
    publication: TypedValuePublicationManifest,
    registry: CompiledTypedValueRegistry,
    snapshots: tuple[PublicationDecoderSourceSnapshot, ...],
    raw_independent_vector_manifest: bytes,
    pins: ProtectedTypedValuePublicationPins,
) -> None:
    if not isinstance(raw_independent_vector_manifest, bytes):
        raise TypedValuePublicationError("typed_value_publication_independent_vector_raw_bytes_required")
    if publication.publication_digest != pins.publication_digest:
        raise TypedValuePublicationError("typed_value_publication_pin_publication_digest_mismatch")
    if registry.registry_digest != pins.registry_digest:
        raise TypedValuePublicationError("typed_value_publication_pin_registry_digest_mismatch")
    pin_snapshots = tuple(
        PublicationDecoderSourceSnapshot(item.decoder_id, item.source_snapshot_digest)
        for item in pins.decoder_source_snapshots
    )
    if snapshots != pin_snapshots:
        raise TypedValuePublicationError("typed_value_publication_pin_decoder_source_snapshots_mismatch")
    if sha256(raw_independent_vector_manifest).hexdigest() != pins.independent_vector_manifest_digest:
        raise TypedValuePublicationError("typed_value_publication_pin_independent_vector_manifest_mismatch")


def _publication_digest(
    files: tuple[PublicationSourceFile, ...],
    decoder_source_manifest_digest: str,
    snapshots: tuple[PublicationDecoderSourceSnapshot, ...],
    registry_digest: str,
) -> str:
    parts: list[bytes] = [
        _DOMAIN,
        _PROFILE_ID.encode("utf-8"),
        _PROFILE_VERSION.encode("ascii"),
        str(len(files)).encode("ascii"),
    ]
    for item in files:
        parts.extend((item.role.encode("utf-8"), item.sha256.encode("ascii")))
    parts.extend((decoder_source_manifest_digest.encode("ascii"), str(len(snapshots)).encode("ascii")))
    for item in snapshots:
        parts.extend((item.decoder_id.encode("utf-8"), item.source_snapshot_digest.encode("ascii")))
    parts.append(registry_digest.encode("ascii"))
    return sha256(length_prefixed(*parts)).hexdigest()


def _parse_source_file(value: FrozenJsonValue) -> PublicationSourceFile:
    if not isinstance(value, Mapping):
        raise TypedValuePublicationError("typed_value_publication_manifest.file_must_be_object")
    _exact_keys(value, {"role", "sha256"}, "typed_value_publication_manifest.file")
    role = _string(value, "role", "typed_value_publication_manifest.file")
    if not _ASCII_ROLE.fullmatch(role):
        raise TypedValuePublicationError("typed_value_publication_manifest.file.role_invalid")
    return PublicationSourceFile(role, _sha256(value, "sha256", "typed_value_publication_manifest.file"))


def _parse_snapshot(value: FrozenJsonValue) -> PublicationDecoderSourceSnapshot:
    if not isinstance(value, Mapping):
        raise TypedValuePublicationError("typed_value_publication_manifest.snapshot_must_be_object")
    _exact_keys(value, {"decoder_id", "source_snapshot_digest"}, "typed_value_publication_manifest.snapshot")
    decoder_id = _string(value, "decoder_id", "typed_value_publication_manifest.snapshot")
    if not _ASCII_ROLE.fullmatch(decoder_id):
        raise TypedValuePublicationError("typed_value_publication_manifest.snapshot.decoder_id_invalid")
    return PublicationDecoderSourceSnapshot(
        decoder_id,
        _sha256(value, "source_snapshot_digest", "typed_value_publication_manifest.snapshot"),
    )


def _validate_source_files(files: tuple[PublicationSourceFile, ...]) -> None:
    roles = tuple(item.role.encode("utf-8") for item in files)
    if roles != tuple(sorted(roles)) or len(set(roles)) != len(roles):
        raise TypedValuePublicationError("typed_value_publication_manifest.files_not_unique_sorted")


def _validate_snapshots(
    snapshots: tuple[PublicationDecoderSourceSnapshot, ...] | tuple[DecoderSourceSnapshotPin, ...], path: str
) -> None:
    identities = tuple(item.decoder_id.encode("utf-8") for item in snapshots)
    if not identities or identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
        raise TypedValuePublicationError(f"{path}_not_unique_sorted")
    for item in snapshots:
        if not _ASCII_ROLE.fullmatch(item.decoder_id):
            raise TypedValuePublicationError(f"{path}_decoder_id_invalid")
        _sha256_text(item.source_snapshot_digest, f"{path}_source_snapshot_digest")


def _exact_keys(value: Mapping[str, FrozenJsonValue], expected: set[str], path: str) -> None:
    if set(value) != expected:
        raise TypedValuePublicationError(f"{path}_keys_invalid")


def _string(value: Mapping[str, FrozenJsonValue], name: str, path: str) -> str:
    item = value.get(name)
    if not isinstance(item, str):
        raise TypedValuePublicationError(f"{path}.{name}_must_be_string")
    return item


def _literal(value: Mapping[str, FrozenJsonValue], name: str, expected: str, path: str) -> None:
    if _string(value, name, path) != expected:
        raise TypedValuePublicationError(f"{path}.{name}_literal_invalid")


def _sha256(value: Mapping[str, FrozenJsonValue], name: str, path: str) -> str:
    return _sha256_text(_string(value, name, path), f"{path}.{name}")


def _sha256_text(value: object, path: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise TypedValuePublicationError(f"{path}_sha256_invalid")
    return value
