"""Composition-owned acceptance trust resolution.

Default runtime composition deliberately has no scenario-vector trust material.
Tests may install an explicit resolver, but candidate bytes never select it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from memorii.tools.semantic_ingestion_traceability_release import AcceptanceTrustStore

if TYPE_CHECKING:
    from memorii.tools.semantic_ingestion_signature_verifier import Ed25519VerificationKeyBinding


class AcceptanceTrustResolver(Protocol):
    def resolve_registered_execution(self) -> AcceptanceTrustStore | None: ...


class DefaultAcceptanceTrustResolver:
    """Production default: no test-only trust root is installed."""

    def resolve_registered_execution(self) -> AcceptanceTrustStore | None:
        return None


class ConfiguredAcceptanceTrustResolver:
    """Registered runtime trust assembled from independently supplied bindings.

    This composition owner deliberately receives the release-independent trust
    store and key bindings separately. Candidate artifacts cannot replace the
    verifier selected here.
    """

    def __init__(
        self,
        *,
        authority: AcceptanceTrustStore,
        signature_bindings: tuple[Ed25519VerificationKeyBinding, ...],
    ) -> None:
        from memorii.tools.semantic_ingestion_signature_verifier import Ed25519SignatureVerifier

        verifier = Ed25519SignatureVerifier(signature_bindings)
        self._authority = replace(
            authority,
            material=replace(authority.material, verify_signature=verifier.verify),
        )

    def resolve_registered_execution(self) -> AcceptanceTrustStore | None:
        return self._authority
