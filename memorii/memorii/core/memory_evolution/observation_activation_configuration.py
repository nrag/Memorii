"""Protected retained-target selection and package revalidation.

This construction owner verifies authority only.  It never activates a writer,
mutates a store, or grants a runtime capability.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol, TypeAlias

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
_PACKAGE_ROOT_DIGEST_CACHE: dict[Path, tuple[tuple[tuple[str, int, int], ...], str]] = {}


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


@dataclass(frozen=True)
class LocalLevel2ObservationActivationTargetConfiguration:
    """Installation-bound activation authority for the current Level 2 runtime.

    This arm deliberately has no signing key, wheel claim, or retained target
    manifest.  It is usable only with the local operator authorization and the
    exact checked-in typed registry that the current Bootstrap runtime ships.
    """

    sidecar_authorization_digest: str
    bootstrap_profile_verification_digest: str
    component_root_digest: str
    resource_policy_digest: str
    package_root: Path
    package_root_digest: str
    typed_value_publication_digest: str
    typed_value_registry_digest: str
    decoder_source_manifest_digest: str
    expires_at: datetime
    now_provider: Callable[[], datetime]

    def __post_init__(self) -> None:
        for value in (
            self.sidecar_authorization_digest,
            self.bootstrap_profile_verification_digest,
            self.component_root_digest,
            self.resource_policy_digest,
            self.package_root_digest,
            self.typed_value_publication_digest,
            self.typed_value_registry_digest,
            self.decoder_source_manifest_digest,
        ):
            if type(value) is not str or not _SHA256.fullmatch(value):
                raise ObservationActivationTargetConfigurationError(
                    "local_level2_observation_activation_digest_invalid"
                )
        if not isinstance(self.package_root, Path) or not self.package_root.is_absolute():
            raise ObservationActivationTargetConfigurationError(
                "local_level2_observation_activation_package_root_invalid"
            )
        if self.expires_at.tzinfo is None or not callable(self.now_provider):
            raise ObservationActivationTargetConfigurationError(
                "local_level2_observation_activation_lifetime_invalid"
            )


@dataclass(frozen=True)
class VerifiedLocalLevel2InstallationEvidence:
    """The immutable installation joins checked when a local runtime starts.

    Resolving a local target is deliberately expensive: it measures the full
    installed package and verifies the generated typed-value publication.  A
    protected write only needs to establish that it is still using this exact
    already-verified target, registry history, and unexpired authorization.
    """

    package_root_digest: str
    typed_value_publication_digest: str
    typed_value_registry_digest: str
    decoder_source_manifest_digest: str

    def __post_init__(self) -> None:
        for value in (
            self.package_root_digest,
            self.typed_value_publication_digest,
            self.typed_value_registry_digest,
            self.decoder_source_manifest_digest,
        ):
            if type(value) is not str or not _SHA256.fullmatch(value):
                raise ObservationActivationTargetConfigurationError(
                    "local_level2_observation_activation_evidence_invalid"
                )


@dataclass(frozen=True)
class VerifiedLocalLevel2ObservationActivationTarget:
    """Resolved local activation target with the same runtime surface as wheel targets."""

    configuration: LocalLevel2ObservationActivationTargetConfiguration
    publication: VerifiedTypedValuePublication
    identity: ObservationActivationTargetIdentity
    installation_evidence: VerifiedLocalLevel2InstallationEvidence
    registry_history: ProtectedTypedValueRegistryHistory = field(repr=False, compare=False)


ObservationActivationTargetConfigurationVariant: TypeAlias = (
    ObservationActivationTargetConfiguration | LocalLevel2ObservationActivationTargetConfiguration
)
VerifiedObservationActivationTargetVariant: TypeAlias = (
    VerifiedObservationActivationTarget | VerifiedLocalLevel2ObservationActivationTarget
)


def resolve_verified_observation_activation_target(
    configuration: ObservationActivationTargetConfigurationVariant,
    registry_history: ProtectedTypedValueRegistryHistory,
) -> VerifiedObservationActivationTargetVariant:
    """Resolve exactly one retained signed target and revalidate all local joins."""
    if type(configuration) is LocalLevel2ObservationActivationTargetConfiguration:
        return _resolve_local_level2_target(configuration, registry_history)
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


def revalidate_verified_observation_activation_target(
    target: VerifiedObservationActivationTargetVariant,
    registry_history: ProtectedTypedValueRegistryHistory,
) -> VerifiedObservationActivationTargetVariant:
    """Recheck the selected closed target arm before each protected write."""
    if type(target) is VerifiedObservationActivationTarget:
        resolved = resolve_verified_observation_activation_target(target.configuration, registry_history)
    elif type(target) is VerifiedLocalLevel2ObservationActivationTarget:
        _revalidate_local_level2_target(target, registry_history)
        return target
    else:
        raise ObservationActivationTargetConfigurationError("observation_activation_target_variant_invalid")
    if resolved != target:
        raise ObservationActivationTargetConfigurationError("observation_activation_target_revalidation_mismatch")
    return resolved


def _resolve_local_level2_target(
    configuration: LocalLevel2ObservationActivationTargetConfiguration,
    registry_history: ProtectedTypedValueRegistryHistory,
) -> VerifiedLocalLevel2ObservationActivationTarget:
    if type(registry_history) is not ProtectedTypedValueRegistryHistory:
        raise ObservationActivationTargetConfigurationError("observation_activation_target_registry_history_invalid")
    now = configuration.now_provider()
    if not isinstance(now, datetime) or now.tzinfo is None or now >= configuration.expires_at:
        raise ObservationActivationTargetConfigurationError("local_level2_observation_activation_expired")
    if _package_root_digest(configuration.package_root) != configuration.package_root_digest:
        raise ObservationActivationTargetConfigurationError("local_level2_observation_activation_package_root_changed")
    matches = tuple(
        publication
        for publication in registry_history.publications
        if publication.publication_manifest.publication_digest == configuration.typed_value_publication_digest
    )
    if len(matches) != 1:
        raise ObservationActivationTargetConfigurationError("local_level2_observation_activation_publication_missing")
    publication = matches[0]
    if (
        publication.compiled_registry.registry_digest != configuration.typed_value_registry_digest
        or publication.publication_manifest.decoder_source_manifest_digest
        != configuration.decoder_source_manifest_digest
    ):
        raise ObservationActivationTargetConfigurationError("local_level2_observation_activation_registry_mismatch")
    evidence = VerifiedLocalLevel2InstallationEvidence(
        package_root_digest=configuration.package_root_digest,
        typed_value_publication_digest=publication.publication_manifest.publication_digest,
        typed_value_registry_digest=publication.compiled_registry.registry_digest,
        decoder_source_manifest_digest=publication.publication_manifest.decoder_source_manifest_digest,
    )
    identity = _local_level2_identity(configuration, publication)
    return VerifiedLocalLevel2ObservationActivationTarget(
        configuration,
        publication,
        identity,
        evidence,
        registry_history,
    )


def _revalidate_local_level2_target(
    target: VerifiedLocalLevel2ObservationActivationTarget,
    registry_history: ProtectedTypedValueRegistryHistory,
) -> None:
    """Perform the O(1) write-time checks for a resolved local target.

    Package-tree hashing and publication decoding happen only in
    ``_resolve_local_level2_target``.  The history object is immutable, so its
    identity is the registry generation witness for the lifetime of this
    runtime.  A new history must go through full target resolution.
    """
    configuration = target.configuration
    if type(registry_history) is not ProtectedTypedValueRegistryHistory:
        raise ObservationActivationTargetConfigurationError("observation_activation_target_registry_history_invalid")
    now = configuration.now_provider()
    if not isinstance(now, datetime) or now.tzinfo is None or now >= configuration.expires_at:
        raise ObservationActivationTargetConfigurationError("local_level2_observation_activation_expired")
    evidence = target.installation_evidence
    if (
        registry_history is not target.registry_history
        or evidence.package_root_digest != configuration.package_root_digest
        or evidence.typed_value_publication_digest != configuration.typed_value_publication_digest
        or evidence.typed_value_registry_digest != configuration.typed_value_registry_digest
        or evidence.decoder_source_manifest_digest != configuration.decoder_source_manifest_digest
        or target.publication.publication_manifest.publication_digest != evidence.typed_value_publication_digest
        or target.publication.compiled_registry.registry_digest != evidence.typed_value_registry_digest
        or target.publication.publication_manifest.decoder_source_manifest_digest
        != evidence.decoder_source_manifest_digest
        or target.identity != _local_level2_identity(configuration, target.publication)
    ):
        raise ObservationActivationTargetConfigurationError("local_level2_observation_activation_target_changed")


def _package_root_digest(root: Path) -> str:
    try:
        resolved = root.resolve(strict=True)
        paths = _package_root_paths(resolved)
        witness = tuple(
            (
                path.relative_to(resolved).as_posix(),
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in paths
        )
        cached = _PACKAGE_ROOT_DIGEST_CACHE.get(resolved)
        if cached is not None and cached[0] == witness:
            return cached[1]
        parts = [b"memorii.local-level2-observation-package-root.v1"]
        for path in paths:
            relative = path.relative_to(resolved).as_posix().encode("utf-8")
            raw = path.read_bytes()
            parts.extend((relative, str(len(raw)).encode("ascii"), sha256(raw).digest()))
        digest = sha256(b"".join(len(part).to_bytes(8, "big") + part for part in parts)).hexdigest()
        _PACKAGE_ROOT_DIGEST_CACHE[resolved] = (witness, digest)
        return digest
    except OSError as exc:
        raise ObservationActivationTargetConfigurationError(
            "local_level2_observation_activation_package_root_unavailable"
        ) from exc


def _package_root_paths(root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path for path in root.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            ),
            key=lambda path: path.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def local_level2_package_root_digest(root: Path) -> str:
    """Expose the canonical package-root measurement to the composition root."""
    return _package_root_digest(root)


def _local_level2_identity(
    configuration: LocalLevel2ObservationActivationTargetConfiguration,
    publication: VerifiedTypedValuePublication,
) -> ObservationActivationTargetIdentity:
    common = (
        configuration.sidecar_authorization_digest,
        configuration.bootstrap_profile_verification_digest,
        configuration.component_root_digest,
        configuration.resource_policy_digest,
        configuration.package_root_digest,
        publication.publication_manifest.publication_digest,
        publication.compiled_registry.registry_digest,
        publication.publication_manifest.decoder_source_manifest_digest,
    )

    def digest(label: str) -> str:
        return sha256(
            b"".join(
                len(part).to_bytes(8, "big") + part
                for part in (label.encode("ascii"), *(value.encode("ascii") for value in common))
            )
        ).hexdigest()

    return ObservationActivationTargetIdentity(
        payload_inventory_digest=configuration.package_root_digest,
        deployment_configuration_identity_digest=configuration.sidecar_authorization_digest,
        writer_fingerprint=digest("writer"),
        observation_schema_fingerprint=digest("schema"),
        ledger_codec_fingerprint=digest("codec"),
    )


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
