"""Framework-oriented provider integrations."""

from memorii.integrations.authenticated_source import (
    AuthenticatedSourceAdapter,
    AuthenticatedSourceSubmission,
)
from memorii.integrations.hermes_provider import HermesMemoryProvider
from memorii.integrations.provider_interface import MemoryProviderInterface

__all__ = [
    "AuthenticatedSourceAdapter",
    "AuthenticatedSourceSubmission",
    "HermesMemoryProvider",
    "MemoryProviderInterface",
]
