"""Composition-owned acceptance trust resolution.

Default runtime composition deliberately has no scenario-vector trust material.
Tests may install an explicit resolver, but candidate bytes never select it.
"""

from __future__ import annotations

from typing import Protocol

from memorii.tools.semantic_ingestion_traceability_release import AcceptanceTrustStore


class AcceptanceTrustResolver(Protocol):
    def resolve_registered_execution(self) -> AcceptanceTrustStore | None: ...


class DefaultAcceptanceTrustResolver:
    """Production default: no test-only trust root is installed."""

    def resolve_registered_execution(self) -> AcceptanceTrustStore | None:
        return None
