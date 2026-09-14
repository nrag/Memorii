"""Closed target-manifest grammar and pure activation-target identity recipes.

This module deliberately has no filesystem, signature, provider, or activation
side effects.  Bootstrap and composition owners supply verified deployment and
publication facts before a later activation owner may use these values.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal

from memorii.core.memory_evolution.ingestion_contracts import length_prefixed
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    FrozenJsonValue,
    ProtectedDecoderSourceManifestLimits,
    parse_canonical_raw_json_object,
)
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_compilation import CompiledRegistryEntry

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DISTRIBUTION_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ASCII_ID = re.compile(r"[A-Za-z0-9._/-]+\Z")
_DECIMAL = re.compile(r"0|[1-9][0-9]*\Z")
_MANIFEST_ROLE: Final = "observation_activation_target"
_MANIFEST_VERSION: Final = "1"
_MEMORII_DISTRIBUTION: Final = "memorii"
_INSTALL_POLICY: Final = "wheel-no-compile-v1"
_CACHE_POLICY: Final = "fresh-private-prefix-v1"
_ORIGIN_POLICY: Final = "selected-distribution-root-v1"
_PAYLOAD_DOMAIN: Final = b"memorii.observation-activation.package-payload.v1"
_ENVIRONMENT_DOMAIN: Final = b"memorii.observation-activation.environment.v1"
_SCHEMA_DOMAIN: Final = b"memorii.observation-activation.schema.v1"
_CODEC_DOMAIN: Final = b"memorii.observation-activation.ledger-codec.v1"
_WRITER_DOMAIN: Final = b"memorii.observation-activation.writer.v1"
_MAXIMUM_DISTRIBUTIONS: Final = 512
_MAXIMUM_INSTALLED_FILES: Final = 250_000
_MAXIMUM_INSTALLED_BYTES: Final = 64 * 1024 * 1024 * 1024
_MAXIMUM_INSTALLED_FILE_BYTES: Final = 2 * 1024 * 1024 * 1024


class ObservationActivationTargetError(ValueError):
    """The protected target inputs cannot form a complete target authority."""


@dataclass(frozen=True)
class ProtectedObservationActivationTargetLimits:
    maximum_manifest_bytes: int = 2 * 1024 * 1024
    maximum_manifest_nodes: int = 64_000
    maximum_manifest_depth: int = 32
    maximum_package_files: int = 4_096
    maximum_payload_bytes: int = 32 * 1024 * 1024
    maximum_package_file_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in self.__dict__.values()):
            raise ValueError("observation_activation_target_limits_must_be_positive")


_DEFAULT_TARGET_LIMITS = ProtectedObservationActivationTargetLimits()


@dataclass(frozen=True)
class DistributionRow:
    normalized_name: str
    version: str
    wheel_sha256: str
    record_sha256: str
    top_level_roots: tuple[str, ...]

    def __post_init__(self) -> None:
        _distribution_name(self.normalized_name, "distribution.normalized_name")
        _ascii_nonempty(self.version, "distribution.version")
        _sha256_text(self.wheel_sha256, "distribution.wheel_sha256")
        _sha256_text(self.record_sha256, "distribution.record_sha256")
        if type(self.top_level_roots) is not tuple or not self.top_level_roots:
            raise ObservationActivationTargetError("distribution.top_level_roots_invalid")
        roots = tuple(_relative_path(root, "distribution.top_level_root") for root in self.top_level_roots)
        if roots != tuple(sorted(roots, key=_utf8)) or len(set(roots)) != len(roots):
            raise ObservationActivationTargetError("distribution.top_level_roots_order_invalid")


@dataclass(frozen=True)
class InstalledFileRow:
    normalized_distribution: str
    installed_relative_path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        _distribution_name(self.normalized_distribution, "installed_file.normalized_distribution")
        _installed_locator(self.installed_relative_path)
        _sha256_text(self.sha256, "installed_file.sha256")
        _nonnegative_int(self.size, "installed_file.size")


@dataclass(frozen=True)
class DeploymentConfiguration:
    installation_root: Path
    scripts_root: Path
    python_implementation: str
    python_version: str
    platform_tag: str
    install_policy: Literal["wheel-no-compile-v1"]
    cache_policy: Literal["fresh-private-prefix-v1"]
    origin_policy: Literal["selected-distribution-root-v1"]
    distributions: tuple[DistributionRow, ...]
    installed_files: tuple[InstalledFileRow, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.installation_root, Path) or not self.installation_root.is_absolute():
            raise ObservationActivationTargetError("deployment.installation_root_invalid")
        if not isinstance(self.scripts_root, Path) or not self.scripts_root.is_absolute():
            raise ObservationActivationTargetError("deployment.scripts_root_invalid")
        if ".." in self.installation_root.parts or ".." in self.scripts_root.parts:
            raise ObservationActivationTargetError("deployment.anchor_not_canonical")
        if self.installation_root.is_relative_to(self.scripts_root) or self.scripts_root.is_relative_to(
            self.installation_root
        ):
            raise ObservationActivationTargetError("deployment.anchors_overlap")
        _ascii_nonempty(self.python_implementation, "deployment.python_implementation")
        _ascii_nonempty(self.python_version, "deployment.python_version")
        _utf8_nonempty(self.platform_tag, "deployment.platform_tag")
        if (
            self.install_policy != _INSTALL_POLICY
            or self.cache_policy != _CACHE_POLICY
            or self.origin_policy != _ORIGIN_POLICY
        ):
            raise ObservationActivationTargetError("deployment.policy_invalid")
        if type(self.distributions) is not tuple or not self.distributions:
            raise ObservationActivationTargetError("deployment.distributions_invalid")
        if type(self.installed_files) is not tuple:
            raise ObservationActivationTargetError("deployment.installed_files_tuple_required")
        if len(self.distributions) > _MAXIMUM_DISTRIBUTIONS or len(self.installed_files) > _MAXIMUM_INSTALLED_FILES:
            raise ObservationActivationTargetError("deployment.cardinality_limit_exceeded")
        if any(type(row) is not DistributionRow for row in self.distributions):
            raise ObservationActivationTargetError("deployment.distribution_row_invalid")
        if any(type(row) is not InstalledFileRow for row in self.installed_files):
            raise ObservationActivationTargetError("deployment.installed_file_row_invalid")
        names = tuple(row.normalized_name for row in self.distributions)
        if (
            names != tuple(sorted(names, key=_utf8))
            or len(set(names)) != len(names)
            or names.count(_MEMORII_DISTRIBUTION) != 1
        ):
            raise ObservationActivationTargetError("deployment.distribution_order_or_memorii_invalid")
        file_keys = tuple((row.normalized_distribution, row.installed_relative_path) for row in self.installed_files)
        if file_keys != tuple(sorted(file_keys, key=lambda item: (_utf8(item[0]), _utf8(item[1])))) or len(
            set(file_keys)
        ) != len(file_keys):
            raise ObservationActivationTargetError("deployment.installed_file_order_invalid")
        if any(row.normalized_distribution not in names for row in self.installed_files):
            raise ObservationActivationTargetError("deployment.installed_file_distribution_unknown")
        locators = tuple(row.installed_relative_path for row in self.installed_files)
        if len(set(locators)) != len(locators):
            raise ObservationActivationTargetError("deployment.installed_file_locator_duplicate")
        if (
            any(row.size > _MAXIMUM_INSTALLED_FILE_BYTES for row in self.installed_files)
            or sum(row.size for row in self.installed_files) > _MAXIMUM_INSTALLED_BYTES
        ):
            raise ObservationActivationTargetError("deployment.installed_file_size_limit_exceeded")


@dataclass(frozen=True)
class DeploymentVerificationReceipt:
    configuration_identity_digest: str
    python_implementation: str
    python_version: str
    platform_tag: str
    distributions: tuple[DistributionRow, ...]
    installed_files: tuple[InstalledFileRow, ...]
    install_policy: Literal["wheel-no-compile-v1"]
    cache_policy: Literal["fresh-private-prefix-v1"]
    origin_policy: Literal["selected-distribution-root-v1"]

    def __post_init__(self) -> None:
        _sha256_text(self.configuration_identity_digest, "deployment_receipt.configuration_identity_digest")
        _ascii_nonempty(self.python_implementation, "deployment_receipt.python_implementation")
        _ascii_nonempty(self.python_version, "deployment_receipt.python_version")
        _utf8_nonempty(self.platform_tag, "deployment_receipt.platform_tag")
        if type(self.distributions) is not tuple or any(type(row) is not DistributionRow for row in self.distributions):
            raise ObservationActivationTargetError("deployment_receipt.distributions_invalid")
        if type(self.installed_files) is not tuple or any(
            type(row) is not InstalledFileRow for row in self.installed_files
        ):
            raise ObservationActivationTargetError("deployment_receipt.installed_files_invalid")
        if (self.install_policy, self.cache_policy, self.origin_policy) != (
            _INSTALL_POLICY,
            _CACHE_POLICY,
            _ORIGIN_POLICY,
        ):
            raise ObservationActivationTargetError("deployment_receipt.policy_invalid")


@dataclass(frozen=True)
class PackageFileRow:
    relative_path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        path = _relative_path(self.relative_path, "package_file.relative_path")
        if (
            not path.isascii()
            or not path.startswith("memorii/")
            or "/__pycache__/" in f"/{path}/"
            or path.endswith(".pyc")
        ):
            raise ObservationActivationTargetError("package_file.path_invalid")
        _sha256_text(self.sha256, "package_file.sha256")
        _nonnegative_int(self.size, "package_file.size")


@dataclass(frozen=True)
class ObservationActivationTargetManifest:
    raw_bytes: bytes
    target_id: str
    memorii_distribution_version: str
    memorii_wheel_sha256: str
    payload_inventory_digest: str
    writer_fingerprint: str
    observation_schema_fingerprint: str
    ledger_codec_fingerprint: str
    typed_value_publication_digest: str
    typed_value_registry_digest: str
    decoder_source_manifest_digest: str
    signature_profile_id: str
    public_key_digest: str
    package_files: tuple[PackageFileRow, ...]


@dataclass(frozen=True)
class ObservationActivationTargetIdentity:
    payload_inventory_digest: str
    deployment_configuration_identity_digest: str
    writer_fingerprint: str
    observation_schema_fingerprint: str
    ledger_codec_fingerprint: str


def parse_observation_activation_target_manifest(
    raw_bytes: bytes, *, limits: ProtectedObservationActivationTargetLimits = _DEFAULT_TARGET_LIMITS
) -> ObservationActivationTargetManifest:
    """Parse the closed raw-control manifest without trusting deployment facts."""
    if type(limits) is not ProtectedObservationActivationTargetLimits:
        raise ValueError("observation_activation_target_limits_invalid")
    parser_limits = ProtectedDecoderSourceManifestLimits(
        limits.maximum_manifest_bytes,
        limits.maximum_manifest_nodes,
        limits.maximum_manifest_depth,
        limits.maximum_package_files,
        limits.maximum_package_file_bytes,
    )
    try:
        root = parse_canonical_raw_json_object(raw_bytes, limits=parser_limits).value
    except ValueError as exc:
        raise ObservationActivationTargetError("observation_activation_target_manifest_raw_invalid") from exc
    _exact_keys(
        root,
        {
            "role",
            "version",
            "target_id",
            "memorii_distribution",
            "memorii_distribution_version",
            "memorii_wheel_sha256",
            "payload_inventory_digest",
            "writer_fingerprint",
            "observation_schema_fingerprint",
            "ledger_codec_fingerprint",
            "typed_value_publication_digest",
            "typed_value_registry_digest",
            "decoder_source_manifest_digest",
            "signature_profile_id",
            "public_key_digest",
            "package_files",
        },
        "manifest",
    )
    _literal(root, "role", _MANIFEST_ROLE, "manifest")
    _literal(root, "version", _MANIFEST_VERSION, "manifest")
    _literal(root, "memorii_distribution", _MEMORII_DISTRIBUTION, "manifest")
    target_id = _ascii_id(_string(root, "target_id", "manifest"), "manifest.target_id")
    version = _ascii_nonempty(
        _string(root, "memorii_distribution_version", "manifest"), "manifest.memorii_distribution_version"
    )
    strings = {
        name: _sha256_text(_string(root, name, "manifest"), f"manifest.{name}")
        for name in (
            "memorii_wheel_sha256",
            "payload_inventory_digest",
            "writer_fingerprint",
            "observation_schema_fingerprint",
            "ledger_codec_fingerprint",
            "typed_value_publication_digest",
            "typed_value_registry_digest",
            "decoder_source_manifest_digest",
            "public_key_digest",
        )
    }
    signature_profile_id = _ascii_nonempty(
        _string(root, "signature_profile_id", "manifest"), "manifest.signature_profile_id"
    )
    raw_rows = root["package_files"]
    if not isinstance(raw_rows, tuple) or len(raw_rows) > limits.maximum_package_files:
        raise ObservationActivationTargetError("manifest.package_files_invalid")
    rows = tuple(_parse_package_file(row) for row in raw_rows)
    if tuple(row.relative_path for row in rows) != tuple(sorted((row.relative_path for row in rows), key=_utf8)):
        raise ObservationActivationTargetError("manifest.package_files_order_invalid")
    if (
        len({row.relative_path for row in rows}) != len(rows)
        or sum(row.size for row in rows) > limits.maximum_payload_bytes
        or any(row.size > limits.maximum_package_file_bytes for row in rows)
    ):
        raise ObservationActivationTargetError("manifest.package_files_limits_invalid")
    return ObservationActivationTargetManifest(
        raw_bytes,
        target_id,
        version,
        strings["memorii_wheel_sha256"],
        strings["payload_inventory_digest"],
        strings["writer_fingerprint"],
        strings["observation_schema_fingerprint"],
        strings["ledger_codec_fingerprint"],
        strings["typed_value_publication_digest"],
        strings["typed_value_registry_digest"],
        strings["decoder_source_manifest_digest"],
        signature_profile_id,
        strings["public_key_digest"],
        rows,
    )


def deployment_configuration_identity(configuration: DeploymentConfiguration) -> str:
    """Compute E from the complete protected deployment configuration."""
    if type(configuration) is not DeploymentConfiguration:
        raise ObservationActivationTargetError("deployment_configuration_invalid")
    parts = [
        _ENVIRONMENT_DOMAIN,
        _utf8(configuration.python_implementation),
        _utf8(configuration.python_version),
        _utf8(configuration.platform_tag),
        _utf8(configuration.install_policy),
        _utf8(configuration.cache_policy),
        _utf8(configuration.origin_policy),
        _ascii_decimal(len(configuration.distributions)),
    ]
    for row in configuration.distributions:
        parts.extend(
            (
                _utf8(row.normalized_name),
                _utf8(row.version),
                _ascii(row.wheel_sha256),
                _ascii(row.record_sha256),
                _ascii_decimal(len(row.top_level_roots)),
            )
        )
        parts.extend(_utf8(root) for root in row.top_level_roots)
    parts.append(_ascii_decimal(len(configuration.installed_files)))
    for row in configuration.installed_files:
        parts.extend(
            (
                _utf8(row.normalized_distribution),
                _utf8(row.installed_relative_path),
                _ascii_decimal(row.size),
                _ascii(row.sha256),
            )
        )
    return sha256(length_prefixed(*parts)).hexdigest()


def payload_inventory_digest(package_files: Iterable[PackageFileRow]) -> str:
    """Compute P from an already validated UTF-8 ordered package inventory."""
    rows = tuple(package_files)
    if any(type(row) is not PackageFileRow for row in rows):
        raise ObservationActivationTargetError("package_files_row_invalid")
    if tuple(row.relative_path for row in rows) != tuple(sorted((row.relative_path for row in rows), key=_utf8)) or len(
        {row.relative_path for row in rows}
    ) != len(rows):
        raise ObservationActivationTargetError("package_files_order_invalid")
    parts = [_PAYLOAD_DOMAIN]
    for row in rows:
        parts.extend((_utf8(row.relative_path), _ascii_decimal(row.size), _ascii(row.sha256)))
    return sha256(length_prefixed(*parts)).hexdigest()


def derive_observation_activation_target_identity(
    configuration: DeploymentConfiguration,
    package_files: Iterable[PackageFileRow],
    publication: VerifiedTypedValuePublication,
    memorii_wheel_sha256: str,
) -> ObservationActivationTargetIdentity:
    """Derive P/E and the three target fingerprints from canonical owners."""
    if type(publication) is not VerifiedTypedValuePublication:
        raise ObservationActivationTargetError("typed_value_publication_invalid")
    _sha256_text(memorii_wheel_sha256, "memorii_wheel_sha256")
    package_rows = tuple(package_files)
    payload = payload_inventory_digest(package_rows)
    environment = deployment_configuration_identity(configuration)
    manifest = publication.publication_manifest
    registry = publication.compiled_registry
    entries = _ordered_entries(registry.entries)
    common = (
        _ascii(manifest.publication_digest),
        _ascii(registry.registry_digest),
        _ascii(manifest.decoder_source_manifest_digest),
        _ascii_decimal(len(entries)),
    )
    schema_parts = [_SCHEMA_DOMAIN, _ascii(payload), _ascii(environment), *common]
    codec_parts = [_CODEC_DOMAIN, _ascii(payload), _ascii(environment), *common]
    for entry in entries:
        fields = (
            _utf8(entry.schema_id),
            _ascii_canonical_version(entry.schema_version),
            _ascii(entry.schema_fingerprint),
            _ascii(entry.binding_digest),
            _ascii(entry.entry_digest),
        )
        schema_parts.extend(fields)
        codec_parts.extend((*fields, _utf8(entry.decoder_id), _ascii(entry.implementation_source_digest)))
    return ObservationActivationTargetIdentity(
        payload,
        environment,
        sha256(
            length_prefixed(_WRITER_DOMAIN, _ascii(payload), _ascii(environment), _ascii(memorii_wheel_sha256))
        ).hexdigest(),
        sha256(length_prefixed(*schema_parts)).hexdigest(),
        sha256(length_prefixed(*codec_parts)).hexdigest(),
    )


def manifest_preimage(manifest: ObservationActivationTargetManifest) -> bytes:
    """Return the detached-signature preimage; signature verification is external."""
    if type(manifest) is not ObservationActivationTargetManifest:
        raise ObservationActivationTargetError("manifest_invalid")
    return b"memorii.observation-activation-target-manifest.v1\x00" + manifest.raw_bytes


def _ordered_entries(entries: tuple[CompiledRegistryEntry, ...]) -> tuple[CompiledRegistryEntry, ...]:
    if any(type(entry) is not CompiledRegistryEntry for entry in entries):
        raise ObservationActivationTargetError("compiled_registry_entry_invalid")
    result = tuple(
        sorted(entries, key=lambda entry: (_utf8(entry.schema_id), _ascii_canonical_version(entry.schema_version)))
    )
    coordinates = tuple((entry.schema_id, entry.schema_version) for entry in result)
    if len(set(coordinates)) != len(coordinates):
        raise ObservationActivationTargetError("compiled_registry_coordinate_duplicate")
    return result


def _parse_package_file(value: FrozenJsonValue) -> PackageFileRow:
    if not isinstance(value, Mapping):
        raise ObservationActivationTargetError("manifest.package_file_must_be_object")
    _exact_keys(value, {"relative_path", "sha256", "size"}, "manifest.package_file")
    size = _decimal_text(_string(value, "size", "manifest.package_file"), "manifest.package_file.size")
    return PackageFileRow(
        _string(value, "relative_path", "manifest.package_file"),
        _string(value, "sha256", "manifest.package_file"),
        int(size),
    )


def _exact_keys(value: Mapping[str, FrozenJsonValue], expected: set[str], path: str) -> None:
    if set(value) != expected:
        raise ObservationActivationTargetError(f"{path}_keys_invalid")


def _string(value: Mapping[str, FrozenJsonValue], name: str, path: str) -> str:
    item = value.get(name)
    if not isinstance(item, str):
        raise ObservationActivationTargetError(f"{path}.{name}_must_be_string")
    return item


def _literal(value: Mapping[str, FrozenJsonValue], name: str, expected: str, path: str) -> None:
    if _string(value, name, path) != expected:
        raise ObservationActivationTargetError(f"{path}.{name}_literal_invalid")


def _distribution_name(value: str, path: str) -> str:
    if type(value) is not str or not _DISTRIBUTION_NAME.fullmatch(value):
        raise ObservationActivationTargetError(f"{path}_invalid")
    return value


def _ascii_id(value: str, path: str) -> str:
    if type(value) is not str or not _ASCII_ID.fullmatch(value):
        raise ObservationActivationTargetError(f"{path}_invalid")
    return value


def _relative_path(value: str, path: str) -> str:
    if type(value) is not str or not value.isascii() or value.startswith("/") or "\\" in value or "\x00" in value:
        raise ObservationActivationTargetError(f"{path}_invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ObservationActivationTargetError(f"{path}_invalid")
    return value


def _installed_locator(value: str) -> str:
    path = _relative_path(value, "installed_file.installed_relative_path")
    if not (path.startswith("site/") or path.startswith("scripts/")):
        raise ObservationActivationTargetError("installed_file.locator_invalid")
    return path


def _sha256_text(value: str, path: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ObservationActivationTargetError(f"{path}_invalid")
    return value


def _ascii_nonempty(value: str, path: str) -> str:
    if type(value) is not str or not value or not value.isascii():
        raise ObservationActivationTargetError(f"{path}_invalid")
    return value


def _utf8_nonempty(value: str, path: str) -> str:
    if type(value) is not str or not value:
        raise ObservationActivationTargetError(f"{path}_invalid")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise ObservationActivationTargetError(f"{path}_invalid") from exc
    return value


def _nonnegative_int(value: int, path: str) -> int:
    if type(value) is not int or value < 0:
        raise ObservationActivationTargetError(f"{path}_invalid")
    return value


def _decimal_text(value: str, path: str) -> str:
    if type(value) is not str or not _DECIMAL.fullmatch(value):
        raise ObservationActivationTargetError(f"{path}_invalid")
    return value


def _ascii_decimal(value: int) -> bytes:
    return _decimal_text(str(_nonnegative_int(value, "decimal")), "decimal").encode("ascii")


def _ascii_canonical_version(value: str) -> bytes:
    return _decimal_text(value, "compiled_registry.schema_version").encode("ascii")


def _ascii(value: str) -> bytes:
    return _ascii_nonempty(value, "identity_ascii").encode("ascii")


def _utf8(value: str) -> bytes:
    return _utf8_nonempty(value, "identity_utf8").encode("utf-8")
