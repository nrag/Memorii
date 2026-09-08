"""Trusted-host conversion and unsigned observation activation target preparation."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol

from memorii.core.memory_evolution.observation_activation_package import verify_installed_observation_target
from memorii.core.memory_evolution.observation_activation_target import (
    DeploymentConfiguration,
    DeploymentVerificationReceipt,
    DistributionRow,
    InstalledFileRow,
    ObservationActivationTargetError,
    ObservationActivationTargetIdentity,
    PackageFileRow,
    ProtectedObservationActivationTargetLimits,
    deployment_configuration_identity,
    derive_observation_activation_target_identity,
    manifest_preimage,
    parse_observation_activation_target_manifest,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    _open_canonical_source_root,
    _read_whole_file,
)
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication

_MAXIMUM_PACKAGE_FILE_BYTES = 4 * 1024 * 1024


class BootstrapDistributionRow(Protocol):
    @property
    def normalized_name(self) -> str: ...
    @property
    def version(self) -> str: ...
    @property
    def wheel_sha256(self) -> str: ...
    @property
    def record_sha256(self) -> str: ...
    @property
    def top_level_roots(self) -> tuple[str, ...]: ...


class BootstrapInstalledFileRow(Protocol):
    @property
    def normalized_distribution(self) -> str: ...
    @property
    def installed_relative_path(self) -> str: ...
    @property
    def sha256(self) -> str: ...
    @property
    def size(self) -> int: ...


class BootstrapDeploymentConfiguration(Protocol):
    @property
    def installation_root(self) -> Path: ...
    @property
    def scripts_root(self) -> Path: ...
    @property
    def python_implementation(self) -> str: ...
    @property
    def python_version(self) -> str: ...
    @property
    def platform_tag(self) -> str: ...
    @property
    def install_policy(self) -> Literal["wheel-no-compile-v1"]: ...
    @property
    def cache_policy(self) -> Literal["fresh-private-prefix-v1"]: ...
    @property
    def origin_policy(self) -> Literal["selected-distribution-root-v1"]: ...
    @property
    def distributions(self) -> tuple[BootstrapDistributionRow, ...]: ...
    @property
    def installed_files(self) -> tuple[BootstrapInstalledFileRow, ...]: ...


class BootstrapDeploymentVerificationFacts(Protocol):
    @property
    def configuration_identity_digest(self) -> str: ...
    @property
    def python_implementation(self) -> str: ...
    @property
    def python_version(self) -> str: ...
    @property
    def platform_tag(self) -> str: ...
    @property
    def distributions(self) -> tuple[BootstrapDistributionRow, ...]: ...
    @property
    def installed_files(self) -> tuple[BootstrapInstalledFileRow, ...]: ...
    @property
    def install_policy(self) -> Literal["wheel-no-compile-v1"]: ...
    @property
    def cache_policy(self) -> Literal["fresh-private-prefix-v1"]: ...
    @property
    def origin_policy(self) -> Literal["selected-distribution-root-v1"]: ...


@dataclass(frozen=True)
class ObservationActivationPreparationInputs:
    deployment_configuration: DeploymentConfiguration
    deployment_verification_receipt: DeploymentVerificationReceipt
    verified_typed_value_publication: VerifiedTypedValuePublication

    def __post_init__(self) -> None:
        if type(self.deployment_configuration) is not DeploymentConfiguration:
            raise ObservationActivationTargetError("observation_activation_preparation_configuration_invalid")
        if type(self.deployment_verification_receipt) is not DeploymentVerificationReceipt:
            raise ObservationActivationTargetError("observation_activation_preparation_receipt_invalid")
        if type(self.verified_typed_value_publication) is not VerifiedTypedValuePublication:
            raise ObservationActivationTargetError("observation_activation_preparation_publication_invalid")


@dataclass(frozen=True)
class PreparedObservationActivationTarget:
    manifest_raw_bytes: bytes
    preimage: bytes
    manifest_sha256: str
    identity: ObservationActivationTargetIdentity

    def __post_init__(self) -> None:
        if type(self.manifest_raw_bytes) is not bytes or type(self.preimage) is not bytes:
            raise ObservationActivationTargetError("prepared_observation_activation_target_bytes_invalid")
        if type(self.manifest_sha256) is not str or len(self.manifest_sha256) != 64:
            raise ObservationActivationTargetError("prepared_observation_activation_target_digest_invalid")
        if type(self.identity) is not ObservationActivationTargetIdentity:
            raise ObservationActivationTargetError("prepared_observation_activation_target_identity_invalid")


def deployment_configuration_from_bootstrap(value: BootstrapDeploymentConfiguration) -> DeploymentConfiguration:
    """Copy structural trusted-bootstrap data into the closed core configuration."""
    try:
        return DeploymentConfiguration(
            value.installation_root, value.scripts_root, value.python_implementation, value.python_version,
            value.platform_tag, value.install_policy, value.cache_policy, value.origin_policy,
            tuple(
                DistributionRow(row.normalized_name, row.version, row.wheel_sha256, row.record_sha256, row.top_level_roots)
                for row in value.distributions
            ),
            tuple(
                InstalledFileRow(row.normalized_distribution, row.installed_relative_path, row.sha256, row.size)
                for row in value.installed_files
            ),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ObservationActivationTargetError("bootstrap_deployment_configuration_invalid") from exc


def deployment_verification_receipt_from_bootstrap(
    value: BootstrapDeploymentVerificationFacts,
) -> DeploymentVerificationReceipt:
    """Copy trusted bootstrap verification facts into the closed core receipt."""
    try:
        return DeploymentVerificationReceipt(
            value.configuration_identity_digest, value.python_implementation, value.python_version,
            value.platform_tag,
            tuple(
                DistributionRow(row.normalized_name, row.version, row.wheel_sha256, row.record_sha256, row.top_level_roots)
                for row in value.distributions
            ),
            tuple(
                InstalledFileRow(row.normalized_distribution, row.installed_relative_path, row.sha256, row.size)
                for row in value.installed_files
            ),
            value.install_policy, value.cache_policy, value.origin_policy,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ObservationActivationTargetError("bootstrap_deployment_receipt_invalid") from exc


def prepare_observation_activation_target(
    inputs: ObservationActivationPreparationInputs,
    target_id: str,
    signature_profile_id: str,
    public_key_digest: str,
) -> PreparedObservationActivationTarget:
    """Build and revalidate an unsigned target from protected inputs and real files."""
    if type(inputs) is not ObservationActivationPreparationInputs:
        raise ObservationActivationTargetError("observation_activation_preparation_inputs_invalid")
    _verify_receipt(inputs.deployment_configuration, inputs.deployment_verification_receipt)
    package_files = _installed_memorii_package_files(inputs.deployment_configuration)
    memorii = next(
        row for row in inputs.deployment_configuration.distributions if row.normalized_name == "memorii"
    )
    identity = derive_observation_activation_target_identity(
        inputs.deployment_configuration, package_files, inputs.verified_typed_value_publication, memorii.wheel_sha256
    )
    publication = inputs.verified_typed_value_publication.publication_manifest
    registry = inputs.verified_typed_value_publication.compiled_registry
    raw = _canonical_manifest(
        target_id,
        signature_profile_id,
        public_key_digest,
        memorii.version,
        memorii.wheel_sha256,
        identity,
        publication.publication_digest,
        registry.registry_digest,
        publication.decoder_source_manifest_digest,
        package_files,
    )
    manifest = parse_observation_activation_target_manifest(raw)
    # Reuse the race-resistant owner after deriving the inventory from the actual
    # payload; this checks metadata, RECORD membership, and two-read file bytes.
    verify_installed_observation_target(inputs.deployment_configuration, manifest)
    if derive_observation_activation_target_identity(
        inputs.deployment_configuration, manifest.package_files, inputs.verified_typed_value_publication,
        memorii.wheel_sha256,
    ) != identity:
        raise ObservationActivationTargetError("observation_activation_preparation_identity_changed")
    return PreparedObservationActivationTarget(raw, manifest_preimage(manifest), sha256(raw).hexdigest(), identity)


def _verify_receipt(configuration: DeploymentConfiguration, receipt: DeploymentVerificationReceipt) -> None:
    if (
        receipt.configuration_identity_digest != deployment_configuration_identity(configuration)
        or receipt.python_implementation != configuration.python_implementation
        or receipt.python_version != configuration.python_version
        or receipt.platform_tag != configuration.platform_tag
        or receipt.distributions != configuration.distributions
        or receipt.installed_files != configuration.installed_files
        or (receipt.install_policy, receipt.cache_policy, receipt.origin_policy)
        != (configuration.install_policy, configuration.cache_policy, configuration.origin_policy)
    ):
        raise ObservationActivationTargetError("observation_activation_preparation_receipt_mismatch")


def _installed_memorii_package_files(configuration: DeploymentConfiguration) -> tuple[PackageFileRow, ...]:
    selected = tuple(row for row in configuration.installed_files
        if row.normalized_distribution == "memorii" and row.installed_relative_path.startswith("site/memorii/"))
    limits = ProtectedObservationActivationTargetLimits()
    if len(selected) > limits.maximum_package_files or sum(row.size for row in selected) > limits.maximum_payload_bytes:
        raise ObservationActivationTargetError("observation_activation_preparation_package_inventory_limit")
    rows: list[PackageFileRow] = []
    descriptor = _open_canonical_source_root(configuration.installation_root)
    try:
        for installed in selected:
            relative = installed.installed_relative_path.removeprefix("site/")
            if "/__pycache__/" in f"/{relative}/" or relative.endswith(".pyc"):
                raise ObservationActivationTargetError("observation_activation_preparation_package_bytecode")
            if installed.size > _MAXIMUM_PACKAGE_FILE_BYTES:
                raise ObservationActivationTargetError("observation_activation_preparation_package_file_too_large")
            raw = _read_whole_file(descriptor, relative, _MAXIMUM_PACKAGE_FILE_BYTES)
            row = PackageFileRow(relative, sha256(raw).hexdigest(), len(raw))
            if (row.sha256, row.size) != (installed.sha256, installed.size):
                raise ObservationActivationTargetError("observation_activation_preparation_package_pin_mismatch")
            rows.append(row)
    finally:
        os.close(descriptor)
    return tuple(sorted(rows, key=lambda row: row.relative_path.encode("utf-8")))


def _canonical_manifest(
    target_id: str,
    profile_id: str,
    key_digest: str,
    version: str,
    wheel_digest: str,
    identity: ObservationActivationTargetIdentity,
    publication_digest: str,
    registry_digest: str,
    decoder_manifest_digest: str,
    package_files: Iterable[PackageFileRow],
) -> bytes:
    value = {
        "role": "observation_activation_target", "version": "1", "target_id": target_id,
        "memorii_distribution": "memorii", "memorii_distribution_version": version,
        "memorii_wheel_sha256": wheel_digest, "payload_inventory_digest": identity.payload_inventory_digest,
        "writer_fingerprint": identity.writer_fingerprint,
        "observation_schema_fingerprint": identity.observation_schema_fingerprint,
        "ledger_codec_fingerprint": identity.ledger_codec_fingerprint,
        "typed_value_publication_digest": publication_digest, "typed_value_registry_digest": registry_digest,
        "decoder_source_manifest_digest": decoder_manifest_digest, "signature_profile_id": profile_id,
        "public_key_digest": key_digest,
        "package_files": [
            {"relative_path": row.relative_path, "sha256": row.sha256, "size": str(row.size)} for row in package_files
        ],
    }
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    ).encode("utf-8")
