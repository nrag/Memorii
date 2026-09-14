"""Host-held immutable inputs for verified profile-3 registry composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memorii.core.memory_evolution.typed_value_publication import (
    ProtectedTypedValuePublicationLimits,
    ProtectedTypedValuePublicationPins,
    TypedValuePublicationError,
    verify_typed_value_publication,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
    TypedValueRegistryHistoryError,
)


class TypedValueRegistryConfigurationError(ValueError):
    """Configured registry material is incomplete, mutable, or unverifiable."""


@dataclass(frozen=True)
class ProtectedTypedValueRegistryPublicationConfiguration:
    """One complete raw publication and its host-owned verification limits/pins."""

    raw_role_sources: tuple[bytes, ...]
    raw_decoder_source_manifest: bytes
    raw_publication_manifest: bytes
    raw_independent_vector_manifest: bytes
    source_package_root: Path
    limits: ProtectedTypedValuePublicationLimits
    pins: ProtectedTypedValuePublicationPins

    def __post_init__(self) -> None:
        if type(self.raw_role_sources) is not tuple or not self.raw_role_sources:
            raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_role_sources_required")
        if any(type(item) is not bytes for item in self.raw_role_sources):
            raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_role_source_invalid")
        if any(type(item) is not bytes for item in (
            self.raw_decoder_source_manifest,
            self.raw_publication_manifest,
            self.raw_independent_vector_manifest,
        )):
            raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_raw_input_invalid")
        if not isinstance(self.source_package_root, Path):
            raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_source_root_invalid")
        if type(self.limits) is not ProtectedTypedValuePublicationLimits:
            raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_limits_invalid")
        if type(self.pins) is not ProtectedTypedValuePublicationPins:
            raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_pins_invalid")


@dataclass(frozen=True)
class ProtectedTypedValueRegistryConfiguration:
    """The complete configured publications a host may expose to its runtime."""

    publications: tuple[ProtectedTypedValueRegistryPublicationConfiguration, ...]

    def __post_init__(self) -> None:
        if type(self.publications) is not tuple or not self.publications:
            raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_publications_required")
        if any(type(item) is not ProtectedTypedValueRegistryPublicationConfiguration for item in self.publications):
            raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_publication_invalid")


def verify_configured_typed_value_registry_history(
    configuration: ProtectedTypedValueRegistryConfiguration,
) -> ProtectedTypedValueRegistryHistory:
    """Verify every configured publication before any runtime owner is created."""
    if type(configuration) is not ProtectedTypedValueRegistryConfiguration:
        raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_invalid")
    try:
        publications = tuple(
            verify_typed_value_publication(
                publication.raw_role_sources,
                publication.raw_decoder_source_manifest,
                publication.raw_publication_manifest,
                publication.raw_independent_vector_manifest,
                source_package_root=publication.source_package_root,
                limits=publication.limits,
                pins=publication.pins,
            )
            for publication in configuration.publications
        )
        return ProtectedTypedValueRegistryHistory(publications)
    except (OSError, TypedValuePublicationError, TypedValueRegistryHistoryError, ValueError) as exc:
        raise TypedValueRegistryConfigurationError("typed_value_registry_configuration_verification_failed") from exc


__all__ = [
    "ProtectedTypedValueRegistryConfiguration",
    "ProtectedTypedValueRegistryPublicationConfiguration",
    "TypedValueRegistryConfigurationError",
    "verify_configured_typed_value_registry_history",
]
