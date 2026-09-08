"""Protected retained-target selection and package revalidation.

This construction owner verifies authority only.  It never activates a writer,
mutates a store, or grants a runtime capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from memorii.core.memory_evolution.observation_activation_package import verify_installed_observation_target
from memorii.core.memory_evolution.observation_activation_target import (
    DeploymentConfiguration,
    DeploymentVerificationReceipt,
    ObservationActivationTargetError,
    ObservationActivationTargetIdentity,
    ObservationActivationTargetManifest,
    deployment_configuration_identity,
    derive_observation_activation_target_identity,
    manifest_preimage,
    parse_observation_activation_target_manifest,
)
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ObservationActivationTargetConfigurationError(ValueError):
    """Configured target authority is absent, ambiguous, or fails revalidation."""


class ObservationActivationTargetSignatureVerifier(Protocol):
    def verify(self, profile_id: str, public_key_digest: str, payload: bytes, signature: bytes) -> bool: ...


@dataclass(frozen=True)
class RetainedObservationActivationTargetRecord:
    raw_manifest: bytes
    signature: bytes
    deployment_configuration_identity_digest: str

    def __post_init__(self) -> None:
        if type(self.raw_manifest) is not bytes or type(self.signature) is not bytes or len(self.signature) != 64:
            raise ObservationActivationTargetConfigurationError("observation_activation_target_record_raw_invalid")
        if type(self.deployment_configuration_identity_digest) is not str or not _SHA256.fullmatch(
            self.deployment_configuration_identity_digest
        ):
            raise ObservationActivationTargetConfigurationError("observation_activation_target_record_identity_invalid")


@dataclass(frozen=True)
class ObservationActivationTargetConfiguration:
    deployment_configuration: DeploymentConfiguration
    deployment_verification_receipt: DeploymentVerificationReceipt
    signature_verifier: ObservationActivationTargetSignatureVerifier
    retained_records: tuple[RetainedObservationActivationTargetRecord, ...]
    selected_manifest_sha256: str

    def __post_init__(self) -> None:
        if type(self.deployment_configuration) is not DeploymentConfiguration:
            raise ObservationActivationTargetConfigurationError(
                "observation_activation_target_configuration_deployment_invalid"
            )
        if type(self.deployment_verification_receipt) is not DeploymentVerificationReceipt:
            raise ObservationActivationTargetConfigurationError(
                "observation_activation_target_configuration_receipt_invalid"
            )
        if type(self.retained_records) is not tuple or not self.retained_records:
            raise ObservationActivationTargetConfigurationError(
                "observation_activation_target_configuration_records_invalid"
            )
        if any(type(record) is not RetainedObservationActivationTargetRecord for record in self.retained_records):
            raise ObservationActivationTargetConfigurationError(
                "observation_activation_target_configuration_record_invalid"
            )
        if type(self.selected_manifest_sha256) is not str or not _SHA256.fullmatch(self.selected_manifest_sha256):
            raise ObservationActivationTargetConfigurationError(
                "observation_activation_target_configuration_selected_digest_invalid"
            )
        if not callable(getattr(self.signature_verifier, "verify", None)):
            raise ObservationActivationTargetConfigurationError(
                "observation_activation_target_configuration_verifier_invalid"
            )


@dataclass(frozen=True)
class VerifiedObservationActivationTarget:
    """Immutable revalidation context retained by later runtime owners."""

    configuration: ObservationActivationTargetConfiguration
    manifest: ObservationActivationTargetManifest
    record: RetainedObservationActivationTargetRecord
    publication: VerifiedTypedValuePublication
    identity: ObservationActivationTargetIdentity


def resolve_verified_observation_activation_target(
    configuration: ObservationActivationTargetConfiguration,
    registry_history: ProtectedTypedValueRegistryHistory,
) -> VerifiedObservationActivationTarget:
    """Resolve exactly one retained signed target and revalidate all local joins."""
    if type(configuration) is not ObservationActivationTargetConfiguration:
        raise ObservationActivationTargetConfigurationError("observation_activation_target_configuration_invalid")
    if type(registry_history) is not ProtectedTypedValueRegistryHistory:
        raise ObservationActivationTargetConfigurationError("observation_activation_target_registry_history_invalid")
    try:
        _verify_receipt(configuration.deployment_configuration, configuration.deployment_verification_receipt)
        record, manifest = _select_record(configuration)
        if record.deployment_configuration_identity_digest != deployment_configuration_identity(
            configuration.deployment_configuration
        ):
            raise ObservationActivationTargetConfigurationError(
                "observation_activation_target_record_deployment_identity_mismatch"
            )
        if (
            configuration.signature_verifier.verify(
                manifest.signature_profile_id,
                manifest.public_key_digest,
                manifest_preimage(manifest),
                record.signature,
            )
            is not True
        ):
            raise ObservationActivationTargetConfigurationError("observation_activation_target_signature_invalid")
        publication = _select_publication(registry_history, manifest.typed_value_publication_digest)
        if (
            publication.compiled_registry.registry_digest != manifest.typed_value_registry_digest
            or publication.publication_manifest.decoder_source_manifest_digest
            != manifest.decoder_source_manifest_digest
        ):
            raise ObservationActivationTargetConfigurationError(
                "observation_activation_target_publication_join_invalid"
            )
        verify_installed_observation_target(configuration.deployment_configuration, manifest)
        identity = derive_observation_activation_target_identity(
            configuration.deployment_configuration,
            manifest.package_files,
            publication,
            manifest.memorii_wheel_sha256,
        )
        if (
            identity.payload_inventory_digest != manifest.payload_inventory_digest
            or identity.writer_fingerprint != manifest.writer_fingerprint
            or identity.observation_schema_fingerprint != manifest.observation_schema_fingerprint
            or identity.ledger_codec_fingerprint != manifest.ledger_codec_fingerprint
        ):
            raise ObservationActivationTargetConfigurationError("observation_activation_target_fingerprint_mismatch")
        return VerifiedObservationActivationTarget(configuration, manifest, record, publication, identity)
    except ObservationActivationTargetConfigurationError:
        raise
    except (ObservationActivationTargetError, OSError, ValueError) as exc:
        raise ObservationActivationTargetConfigurationError(
            "observation_activation_target_verification_failed"
        ) from exc


def _verify_receipt(configuration: DeploymentConfiguration, receipt: DeploymentVerificationReceipt) -> None:
    identity = deployment_configuration_identity(configuration)
    if (
        receipt.configuration_identity_digest != identity
        or receipt.python_implementation != configuration.python_implementation
        or receipt.python_version != configuration.python_version
        or receipt.platform_tag != configuration.platform_tag
        or receipt.distributions != configuration.distributions
        or receipt.installed_files != configuration.installed_files
        or receipt.install_policy != configuration.install_policy
        or receipt.cache_policy != configuration.cache_policy
        or receipt.origin_policy != configuration.origin_policy
    ):
        raise ObservationActivationTargetConfigurationError("observation_activation_target_receipt_mismatch")


def _select_record(
    configuration: ObservationActivationTargetConfiguration,
) -> tuple[RetainedObservationActivationTargetRecord, ObservationActivationTargetManifest]:
    parsed: list[tuple[RetainedObservationActivationTargetRecord, ObservationActivationTargetManifest]] = []
    retained: dict[tuple[str, str, str], RetainedObservationActivationTargetRecord] = {}
    for record in configuration.retained_records:
        manifest = parse_observation_activation_target_manifest(record.raw_manifest)
        key = (manifest.writer_fingerprint, manifest.observation_schema_fingerprint, manifest.ledger_codec_fingerprint)
        prior = retained.get(key)
        if prior is not None and prior != record:
            raise ObservationActivationTargetConfigurationError("observation_activation_target_retained_conflict")
        if prior is not None:
            continue
        retained[key] = record
        if sha256(record.raw_manifest).hexdigest() == configuration.selected_manifest_sha256:
            parsed.append((record, manifest))
    if len(parsed) != 1:
        raise ObservationActivationTargetConfigurationError("observation_activation_target_selection_ambiguous")
    return parsed[0]


def _select_publication(
    history: ProtectedTypedValueRegistryHistory, publication_digest: str
) -> VerifiedTypedValuePublication:
    matches = tuple(
        publication
        for publication in history.publications
        if publication.publication_manifest.publication_digest == publication_digest
    )
    if len(matches) != 1:
        raise ObservationActivationTargetConfigurationError(
            "observation_activation_target_publication_selection_invalid"
        )
    return matches[0]
