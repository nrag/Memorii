"""Framework-oriented provider integrations."""

from memorii.integrations.authenticated_source import (
    AuthenticatedSourceAdapter,
    AuthenticatedSourceRuntime,
    AuthenticatedSourceSubmission,
    build_authenticated_source_runtime,
)
from memorii.integrations.hermes_provider import HermesMemoryProvider
from memorii.integrations.provider_interface import MemoryProviderInterface

__all__ = [
    "AuthenticatedSourceAdapter",
    "AuthenticatedSourceRuntime",
    "AuthenticatedSourceSubmission",
    "build_authenticated_source_runtime",
    "HermesMemoryProvider",
    "MemoryProviderInterface",
]
