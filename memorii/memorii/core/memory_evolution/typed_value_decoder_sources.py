"""Fail-closed intake for the profile-3 decoder source manifest.

This module only verifies source bytes and derives source snapshots.  Decoder
selection and importing belong to the later registry composition owner.
"""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import TypeAlias, cast

from memorii.core.memory_evolution.ingestion_contracts import _length_prefixed

_ASCII_ID = re.compile(r"[A-Za-z0-9._/-]+\Z")
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9._-]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PROFILE_ID = "semantic_ingestion_typed_value"
_PROFILE_VERSION = "3"
_ROLE = "decoder_source_manifest"
_SNAPSHOT_DOMAIN = b"semantic-ingestion-profile3-decoder-source-snapshot"
_RESERVED_GENERATED_SOURCE_DIRECTORY = "observation_registry_sources"


class DecoderSourceManifestError(ValueError):
    """The external decoder source manifest or one named file is invalid."""


JsonScalar: TypeAlias = str | bool | None
FrozenJsonValue: TypeAlias = JsonScalar | tuple["FrozenJsonValue", ...] | Mapping[str, "FrozenJsonValue"]


@dataclass(frozen=True)
class ProtectedDecoderSourceManifestLimits:
    """Protected parsing and source-read limits outside profile commitments."""

    maximum_manifest_bytes: int
    maximum_manifest_nodes: int
    maximum_manifest_depth: int
    maximum_files: int
    maximum_file_bytes: int

    def __post_init__(self) -> None:
        values = (
            self.maximum_manifest_bytes,
            self.maximum_manifest_nodes,
            self.maximum_manifest_depth,
            self.maximum_files,
            self.maximum_file_bytes,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("decoder_source_manifest_limits_must_be_positive")


@dataclass(frozen=True)
class CanonicalRawJsonObject:
    """Exact validated raw JSON and an immutable representation of its root."""

    raw_bytes: bytes
    value: Mapping[str, FrozenJsonValue]


@dataclass(frozen=True)
class DecoderSourceManifestFile:
    decoder_id: str
    source_file_id: str
    relative_path: str
    sha256: str


@dataclass(frozen=True)
class DecoderSourceSelection:
    """One explicit whole-file selection used by offline publication authoring."""

    decoder_id: str
    source_file_id: str
    relative_path: str


@dataclass(frozen=True)
class DecoderSourceManifest:
    raw_bytes: bytes
    manifest_digest: str
    profile_id: str
    profile_version: str
    files: tuple[DecoderSourceManifestFile, ...]


@dataclass(frozen=True)
class VerifiedDecoderSourceFile:
    decoder_id: str
    source_file_id: str
    relative_path: str
    sha256: str
    raw_bytes: bytes


@dataclass(frozen=True)
class DecoderSourceSnapshot:
    decoder_id: str
    source_snapshot_digest: str
    files: tuple[VerifiedDecoderSourceFile, ...]


@dataclass(frozen=True)
class VerifiedDecoderSourceManifest:
    manifest: DecoderSourceManifest
    files: tuple[VerifiedDecoderSourceFile, ...]
    snapshots: tuple[DecoderSourceSnapshot, ...]


def parse_canonical_raw_json_object(
    raw_bytes: bytes, *, limits: ProtectedDecoderSourceManifestLimits
) -> CanonicalRawJsonObject:
    """Parse strict canonical JSON once for external publication manifests.

    This is deliberately reusable by the later publication-manifest owner so
    that external source-manifest intake has one strict grammar boundary.
    """
    try:
        return _parse_canonical_raw_json_object(raw_bytes, limits=limits)
    except RecursionError as exc:
        raise DecoderSourceManifestError("decoder_source_manifest_depth_limit_exceeded") from exc


def _parse_canonical_raw_json_object(
    raw_bytes: bytes, *, limits: ProtectedDecoderSourceManifestLimits
) -> CanonicalRawJsonObject:
    if not isinstance(raw_bytes, bytes):
        raise DecoderSourceManifestError("decoder_source_manifest_raw_bytes_required")
    if len(raw_bytes) > limits.maximum_manifest_bytes:
        raise DecoderSourceManifestError("decoder_source_manifest_bytes_limit_exceeded")
    if raw_bytes.endswith(b"\n"):
        raise DecoderSourceManifestError("decoder_source_manifest_terminal_lf_forbidden")
    _precheck_nesting(raw_bytes, limits.maximum_manifest_depth)
    value = _decode_json(raw_bytes)
    _check_tree_limits(value, limits)
    if _canonical_json(value) != raw_bytes:
        raise DecoderSourceManifestError("decoder_source_manifest_not_rfc8785_canonical")
    if not isinstance(value, dict):
        raise DecoderSourceManifestError("decoder_source_manifest_must_be_object")
    return CanonicalRawJsonObject(raw_bytes=raw_bytes, value=cast(Mapping[str, FrozenJsonValue], _freeze_json(value)))


def parse_canonical_manifest_object(raw_bytes: bytes, *, maximum_bytes: int) -> Mapping[str, FrozenJsonValue]:
    """Return an immutable strict-canonical external manifest object.

    The later publication-manifest owner can use this shared intake boundary
    without inheriting decoder-source file-read policy.  Its depth and node
    ceilings are derived solely from the protected byte ceiling.
    """
    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        raise ValueError("canonical_manifest_maximum_bytes_must_be_positive")
    limits = ProtectedDecoderSourceManifestLimits(
        maximum_manifest_bytes=maximum_bytes,
        maximum_manifest_nodes=maximum_bytes,
        maximum_manifest_depth=min(maximum_bytes, 64),
        maximum_files=maximum_bytes,
        maximum_file_bytes=maximum_bytes,
    )
    return parse_canonical_raw_json_object(raw_bytes, limits=limits).value


def parse_decoder_source_manifest(
    raw_bytes: bytes, *, limits: ProtectedDecoderSourceManifestLimits
) -> DecoderSourceManifest:
    """Parse the exact profile-3 decoder source manifest without reading files."""
    parsed = parse_canonical_raw_json_object(raw_bytes, limits=limits)
    root = parsed.value
    _exact_keys(root, {"role", "profile_id", "profile_version", "files"}, "decoder_source_manifest")
    _literal(root, "role", _ROLE, "decoder_source_manifest")
    _literal(root, "profile_id", _PROFILE_ID, "decoder_source_manifest")
    _literal(root, "profile_version", _PROFILE_VERSION, "decoder_source_manifest")
    files_value = root["files"]
    if not isinstance(files_value, tuple):
        raise DecoderSourceManifestError("decoder_source_manifest.files_must_be_array")
    if not files_value:
        raise DecoderSourceManifestError("decoder_source_manifest.files_empty")
    if len(files_value) > limits.maximum_files:
        raise DecoderSourceManifestError("decoder_source_manifest.files_limit_exceeded")
    files = tuple(_parse_file(item) for item in files_value)
    _validate_file_rows(files)
    return DecoderSourceManifest(
        raw_bytes=raw_bytes,
        manifest_digest=sha256(raw_bytes).hexdigest(),
        profile_id=_PROFILE_ID,
        profile_version=_PROFILE_VERSION,
        files=files,
    )


def verify_decoder_source_manifest(
    raw_bytes: bytes,
    *,
    source_package_root: Path,
    limits: ProtectedDecoderSourceManifestLimits,
    forbidden_relative_paths: frozenset[str] = frozenset(),
) -> VerifiedDecoderSourceManifest:
    """Verify named whole files beneath a protected canonical source root."""
    manifest = parse_decoder_source_manifest(raw_bytes, limits=limits)
    forbidden = _validated_supplemental_forbidden_paths(forbidden_relative_paths)
    root_descriptor = _open_canonical_source_root(source_package_root)
    verified: list[VerifiedDecoderSourceFile] = []
    shared_paths: dict[str, tuple[str, bytes]] = {}
    try:
        for row in manifest.files:
            if _is_forbidden_source_path(row.relative_path, forbidden):
                raise DecoderSourceManifestError("decoder_source_manifest.generated_source_forbidden")
            raw_file = _read_whole_file(root_descriptor, row.relative_path, limits.maximum_file_bytes)
            _validate_utf8(raw_file, "decoder_source_manifest.source_file_utf8_invalid")
            actual_digest = sha256(raw_file).hexdigest()
            if actual_digest != row.sha256:
                raise DecoderSourceManifestError("decoder_source_manifest.source_file_sha256_mismatch")
            prior = shared_paths.get(row.relative_path)
            if prior is not None and prior != (row.source_file_id, raw_file):
                raise DecoderSourceManifestError("decoder_source_manifest.shared_path_conflict")
            if prior is not None:
                # Reuse immutable bytes after this row independently re-read and
                # re-hashed the same path; large shared native owners otherwise
                # retain one identical bytes object per decoder row.
                raw_file = prior[1]
            else:
                shared_paths[row.relative_path] = (row.source_file_id, raw_file)
            verified.append(
                VerifiedDecoderSourceFile(
                    decoder_id=row.decoder_id,
                    source_file_id=row.source_file_id,
                    relative_path=row.relative_path,
                    sha256=row.sha256,
                    raw_bytes=raw_file,
                )
            )
    finally:
        os.close(root_descriptor)
    files = tuple(verified)
    snapshots = _snapshots(files)
    return VerifiedDecoderSourceManifest(manifest=manifest, files=files, snapshots=snapshots)


def capture_decoder_source_files(
    selections: tuple[DecoderSourceSelection, ...],
    *,
    source_package_root: Path,
    limits: ProtectedDecoderSourceManifestLimits,
    forbidden_relative_paths: frozenset[str] = frozenset(),
) -> tuple[VerifiedDecoderSourceFile, ...]:
    """Capture explicit selected UTF-8 whole files under the protected root.

    This is an offline authoring primitive.  It validates every selection and
    generated-file exclusion before it opens a selected source file.
    """
    if type(selections) is not tuple or not selections:
        raise DecoderSourceManifestError("decoder_source_selection_tuple_nonempty_required")
    if len(selections) > limits.maximum_files:
        raise DecoderSourceManifestError("decoder_source_manifest.files_limit_exceeded")
    rows: list[DecoderSourceManifestFile] = []
    for selection in selections:
        if type(selection) is not DecoderSourceSelection:
            raise DecoderSourceManifestError("decoder_source_selection_invalid")
        rows.append(
            DecoderSourceManifestFile(
                decoder_id=_ascii_text(selection.decoder_id, "decoder_source_selection.decoder_id"),
                source_file_id=_ascii_text(selection.source_file_id, "decoder_source_selection.source_file_id"),
                relative_path=_validate_relative_path(selection.relative_path),
                sha256="0" * 64,
            )
        )
    rows.sort(key=lambda item: (item.decoder_id.encode("utf-8"), item.source_file_id.encode("utf-8")))
    _validate_file_rows(tuple(rows))
    forbidden = _validated_supplemental_forbidden_paths(forbidden_relative_paths)
    if any(_is_forbidden_source_path(row.relative_path, forbidden) for row in rows):
        raise DecoderSourceManifestError("decoder_source_manifest.generated_source_forbidden")
    root_descriptor = _open_canonical_source_root(source_package_root)
    try:
        captured: list[VerifiedDecoderSourceFile] = []
        shared_paths: dict[str, tuple[str, bytes]] = {}
        for row in rows:
            raw_file = _read_whole_file(root_descriptor, row.relative_path, limits.maximum_file_bytes)
            _validate_utf8(raw_file, "decoder_source_manifest.source_file_utf8_invalid")
            prior = shared_paths.get(row.relative_path)
            if prior is not None and prior != (row.source_file_id, raw_file):
                raise DecoderSourceManifestError("decoder_source_manifest.shared_path_conflict")
            if prior is not None:
                raw_file = prior[1]
            else:
                shared_paths[row.relative_path] = (row.source_file_id, raw_file)
            captured.append(
                VerifiedDecoderSourceFile(
                    decoder_id=row.decoder_id,
                    source_file_id=row.source_file_id,
                    relative_path=row.relative_path,
                    sha256=sha256(raw_file).hexdigest(),
                    raw_bytes=raw_file,
                )
            )
        return tuple(captured)
    finally:
        os.close(root_descriptor)


def _parse_file(value: FrozenJsonValue) -> DecoderSourceManifestFile:
    if not isinstance(value, Mapping):
        raise DecoderSourceManifestError("decoder_source_manifest.file_must_be_object")
    _exact_keys(value, {"decoder_id", "source_file_id", "relative_path", "sha256"}, "decoder_source_manifest.file")
    return DecoderSourceManifestFile(
        decoder_id=_ascii_id(value, "decoder_id", "decoder_source_manifest.file"),
        source_file_id=_ascii_id(value, "source_file_id", "decoder_source_manifest.file"),
        relative_path=_validate_relative_path(_string(value, "relative_path", "decoder_source_manifest.file")),
        sha256=_sha256(value, "sha256", "decoder_source_manifest.file"),
    )


def _ascii_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not _ASCII_ID.fullmatch(value):
        raise DecoderSourceManifestError(f"{path}_invalid")
    return value


def _validate_file_rows(files: tuple[DecoderSourceManifestFile, ...]) -> None:
    ordered = tuple((item.decoder_id.encode("utf-8"), item.source_file_id.encode("utf-8")) for item in files)
    if ordered != tuple(sorted(ordered)):
        raise DecoderSourceManifestError("decoder_source_manifest.files_not_sorted")
    pairs = set[tuple[str, str]]()
    paths = set[tuple[str, str]]()
    shared: dict[str, tuple[str, str]] = {}
    for item in files:
        identity = (item.decoder_id, item.source_file_id)
        path_identity = (item.decoder_id, item.relative_path)
        if identity in pairs:
            raise DecoderSourceManifestError("decoder_source_manifest.decoder_source_file_duplicate")
        if path_identity in paths:
            raise DecoderSourceManifestError("decoder_source_manifest.decoder_relative_path_duplicate")
        pairs.add(identity)
        paths.add(path_identity)
        previous = shared.setdefault(item.relative_path, (item.source_file_id, item.sha256))
        if previous != (item.source_file_id, item.sha256):
            raise DecoderSourceManifestError("decoder_source_manifest.shared_path_metadata_conflict")


def _snapshots(files: tuple[VerifiedDecoderSourceFile, ...]) -> tuple[DecoderSourceSnapshot, ...]:
    grouped: dict[str, list[VerifiedDecoderSourceFile]] = {}
    for item in files:
        grouped.setdefault(item.decoder_id, []).append(item)
    snapshots: list[DecoderSourceSnapshot] = []
    for decoder_id in sorted(grouped, key=lambda item: item.encode("utf-8")):
        rows = tuple(grouped[decoder_id])
        parts: list[bytes] = [_SNAPSHOT_DOMAIN, decoder_id.encode("utf-8"), str(len(rows)).encode("ascii")]
        for row in rows:
            parts.extend((row.source_file_id.encode("utf-8"), row.relative_path.encode("ascii"), row.raw_bytes))
        snapshots.append(DecoderSourceSnapshot(decoder_id, sha256(_length_prefixed(*parts)).hexdigest(), rows))
    return tuple(snapshots)


def _open_canonical_source_root(source_package_root: Path) -> int:
    if not isinstance(source_package_root, Path) or not source_package_root.is_absolute():
        raise DecoderSourceManifestError("decoder_source_manifest.source_root_must_be_absolute")
    try:
        resolved = source_package_root.resolve(strict=True)
    except OSError as exc:
        raise DecoderSourceManifestError("decoder_source_manifest.source_root_invalid") from exc
    if resolved != source_package_root:
        raise DecoderSourceManifestError("decoder_source_manifest.source_root_not_canonical")
    _reject_reserved_generated_source_root(resolved)
    descriptors: list[int] = []
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        for component in source_package_root.parts[1:]:
            descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptors[-1],
            )
            descriptors.append(descriptor)
        status = os.fstat(descriptors[-1])
        if not stat.S_ISDIR(status.st_mode):
            raise DecoderSourceManifestError("decoder_source_manifest.source_root_invalid")
        return descriptors.pop()
    except DecoderSourceManifestError:
        raise
    except OSError as exc:
        raise DecoderSourceManifestError("decoder_source_manifest.source_root_invalid") from exc
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def _validated_supplemental_forbidden_paths(forbidden_relative_paths: frozenset[str]) -> frozenset[str]:
    """Validate caller exclusions before opening the protected source root."""
    if not isinstance(forbidden_relative_paths, frozenset):
        raise DecoderSourceManifestError("decoder_source_manifest.forbidden_relative_paths_invalid")
    return frozenset(_validate_relative_path(path) for path in forbidden_relative_paths)


def _reject_reserved_generated_source_root(source_package_root: Path) -> None:
    """A source-root depth change cannot turn generated package files into sources."""
    if isinstance(source_package_root, Path) and _RESERVED_GENERATED_SOURCE_DIRECTORY in source_package_root.parts:
        raise DecoderSourceManifestError("decoder_source_manifest.generated_source_forbidden")


def _is_forbidden_source_path(relative_path: str, supplemental_forbidden_paths: frozenset[str]) -> bool:
    return (
        relative_path in supplemental_forbidden_paths
        or _RESERVED_GENERATED_SOURCE_DIRECTORY in relative_path.split("/")
    )


def _read_whole_file(root_descriptor: int, relative_path: str, maximum_file_bytes: int) -> bytes:
    segments = relative_path.split("/")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptors: list[int] = []
    try:
        descriptor = os.dup(root_descriptor)
        descriptors.append(descriptor)
        for index, segment in enumerate(segments):
            is_last = index == len(segments) - 1
            descriptor = os.open(segment, file_flags if is_last else directory_flags, dir_fd=descriptors[-1])
            descriptors.append(descriptor)
        file_status = os.fstat(descriptors[-1])
        if not stat.S_ISREG(file_status.st_mode):
            raise DecoderSourceManifestError("decoder_source_manifest.source_file_not_regular")
        if file_status.st_size > maximum_file_bytes:
            raise DecoderSourceManifestError("decoder_source_manifest.source_file_limit_exceeded")
        with os.fdopen(descriptors.pop(), "rb", closefd=True) as source_file:
            raw = source_file.read(maximum_file_bytes + 1)
        if len(raw) > maximum_file_bytes:
            raise DecoderSourceManifestError("decoder_source_manifest.source_file_limit_exceeded")
        return raw
    except DecoderSourceManifestError:
        raise
    except OSError as exc:
        raise DecoderSourceManifestError("decoder_source_manifest.source_file_open_failed") from exc
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def _decode_json(raw: bytes) -> object:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_no_duplicate_object,
            parse_int=_no_json_number,
            parse_float=_no_json_number,
            parse_constant=_no_json_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecoderSourceManifestError("decoder_source_manifest_json_invalid") from exc
    _validate_json_tree(value)
    return value


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DecoderSourceManifestError("decoder_source_manifest_duplicate_key")
        result[key] = value
    return result


def _no_json_number(_: str) -> object:
    raise DecoderSourceManifestError("decoder_source_manifest_json_number_forbidden")


def _validate_json_tree(value: object) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            try:
                _validate_utf8(item.encode("utf-8", "strict"), "decoder_source_manifest_unicode_scalar_invalid")
            except UnicodeEncodeError as exc:
                raise DecoderSourceManifestError("decoder_source_manifest_unicode_scalar_invalid") from exc
        elif isinstance(item, dict):
            for key, nested in item.items():
                if not key or not key.isascii():
                    raise DecoderSourceManifestError("decoder_source_manifest_object_key_invalid")
                pending.append(nested)
        elif isinstance(item, list):
            pending.extend(item)
        elif item is not None and not isinstance(item, bool):
            raise DecoderSourceManifestError("decoder_source_manifest_json_value_invalid")


def _freeze_json(value: object) -> FrozenJsonValue:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool)):
        return value
    raise DecoderSourceManifestError("decoder_source_manifest_json_value_invalid")


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8", "strict")
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise DecoderSourceManifestError("decoder_source_manifest_json_value_invalid") from exc


def _precheck_nesting(raw: bytes, maximum_depth: int) -> None:
    depth = 0
    quoted = False
    escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                quoted = False
        elif byte == 0x22:
            quoted = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            if depth > maximum_depth:
                raise DecoderSourceManifestError("decoder_source_manifest_depth_limit_exceeded")
        elif byte in (0x5D, 0x7D):
            depth -= 1


def _check_tree_limits(value: object, limits: ProtectedDecoderSourceManifestLimits) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > limits.maximum_manifest_nodes:
            raise DecoderSourceManifestError("decoder_source_manifest_nodes_limit_exceeded")
        if depth > limits.maximum_manifest_depth:
            raise DecoderSourceManifestError("decoder_source_manifest_depth_limit_exceeded")
        if isinstance(item, dict):
            pending.extend((nested, depth + 1) for nested in item.values())
        elif isinstance(item, list):
            pending.extend((nested, depth + 1) for nested in item)


def _exact_keys(value: Mapping[str, FrozenJsonValue], expected: set[str], path: str) -> None:
    if set(value) != expected:
        raise DecoderSourceManifestError(f"{path}_keys_invalid")


def _string(value: Mapping[str, FrozenJsonValue], name: str, path: str) -> str:
    item = value.get(name)
    if not isinstance(item, str):
        raise DecoderSourceManifestError(f"{path}.{name}_must_be_string")
    return item


def _literal(value: Mapping[str, FrozenJsonValue], name: str, expected: str, path: str) -> None:
    if _string(value, name, path) != expected:
        raise DecoderSourceManifestError(f"{path}.{name}_literal_invalid")


def _ascii_id(value: Mapping[str, FrozenJsonValue], name: str, path: str) -> str:
    item = _string(value, name, path)
    if not _ASCII_ID.fullmatch(item):
        raise DecoderSourceManifestError(f"{path}.{name}_ascii_id_invalid")
    return item


def _sha256(value: Mapping[str, FrozenJsonValue], name: str, path: str) -> str:
    item = _string(value, name, path)
    if not _SHA256.fullmatch(item):
        raise DecoderSourceManifestError(f"{path}.{name}_sha256_invalid")
    return item


def _validate_relative_path(value: str) -> str:
    try:
        value.encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise DecoderSourceManifestError("decoder_source_manifest.relative_path_invalid") from exc
    if not value or value.startswith("/") or value.endswith("/") or "\\" in value or "%" in value:
        raise DecoderSourceManifestError("decoder_source_manifest.relative_path_invalid")
    segments = value.split("/")
    if any(segment in {"", ".", ".."} or not _PATH_SEGMENT.fullmatch(segment) for segment in segments):
        raise DecoderSourceManifestError("decoder_source_manifest.relative_path_invalid")
    return value


def _validate_utf8(raw: bytes, error: str) -> None:
    try:
        raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise DecoderSourceManifestError(error) from exc
