"""Framework-neutral adapter for authenticated retained memory sources."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation, ProviderSyncResult
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.production_authority import (
    VerifiedCapabilityMonitoringAuthority,
    VerifiedProductionHostAuthority,
)
from memorii.core.semantic_ingestion.structured_fact_read import (
    StructuredFactReadRequest,
    StructuredFactReadResponse,
)
from memorii.core.storage_administration.revoked_identity_view import (
    RevokedIdentityServingGate,
)
from memorii.domain.enums import SourceModality


class AuthenticatedSourceSubmission(BaseModel):
    operation: ProviderOperation
    content: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    role: str | None = None
    target: str | None = None
    action: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    language: str = "en"
    speaker_id: str | None = None
    timestamp: datetime | None = None
    source_modality: SourceModality | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthenticatedSourceAdapter:
    """Submit one host-authenticated source through the canonical provider root."""

    def __init__(self, service: ProviderMemoryService) -> None:
        self._service = service

    def submit(
        self,
        submission: AuthenticatedSourceSubmission,
        *,
        authenticated_host_ingress: AuthenticatedHostIngress,
    ) -> ProviderSyncResult:
        return self._service.sync_event(
            operation=submission.operation,
            content=submission.content,
            operation_id=submission.operation_id,
            role=submission.role,
            target=submission.target,
            action=submission.action,
            session_id=submission.session_id,
            task_id=submission.task_id,
            user_id=submission.user_id,
            language=submission.language,
            speaker_id=submission.speaker_id,
            timestamp=submission.timestamp,
            source_modality=submission.source_modality,
            authenticated_host_ingress=authenticated_host_ingress,
        )


@dataclass(frozen=True)
class AuthenticatedSourceLearnedOntologyBinding:
    """Host-issued operations for the core-owned learned ontology journey.

    The source adapter receives no scope, proposal, catalog, or evaluator
    coordinate.  Those values stay behind the verified composition boundary.
    """

    activate_candidate: Callable[[str], object]
    approve_candidate: Callable[[str], object]
    status: Callable[[], object]
    read_structured_facts: Callable[[StructuredFactReadRequest], StructuredFactReadResponse]
    close: Callable[[], None] | None = None


class AuthenticatedSourceRuntime:
    """Non-Hermes composition root with a host-owned ingress issuer."""

    def __init__(
        self,
        *,
        adapter: AuthenticatedSourceAdapter,
        issue_ingress: Callable[[AuthenticatedSourceSubmission], AuthenticatedHostIngress],
        learned_ontology: AuthenticatedSourceLearnedOntologyBinding | None = None,
    ) -> None:
        self._adapter = adapter
        self._issue_ingress = issue_ingress
        self._learned_ontology = learned_ontology

    def submit(self, submission: AuthenticatedSourceSubmission) -> ProviderSyncResult:
        ingress = self._issue_ingress(submission)
        if not isinstance(ingress, AuthenticatedHostIngress):
            raise TypeError("authenticated source host returned invalid ingress")
        return self._adapter.submit(
            submission,
            authenticated_host_ingress=ingress,
        )

    def activate_learned_candidate(self, proposal_id: str) -> object:
        """Ask the verified owner binding to select an evaluated candidate."""
        if self._learned_ontology is None:
            raise RuntimeError("learned ontology activation is unavailable")
        return self._learned_ontology.activate_candidate(proposal_id)

    def approve_learned_candidate(self, proposal_id: str) -> object:
        """Record the signed-in owner's decision before activation."""
        if self._learned_ontology is None:
            raise RuntimeError("learned ontology approval is unavailable")
        return self._learned_ontology.approve_candidate(proposal_id)

    def lookup_learned_ontology_status(self) -> object:
        """Return source-text-free learner status from the installed root."""
        if self._learned_ontology is None:
            return {"status": "unavailable"}
        return self._learned_ontology.status()

    def read_structured_facts(
        self, request: StructuredFactReadRequest,
    ) -> StructuredFactReadResponse:
        """Release facts only through the factory-issued protected reader."""
        if self._learned_ontology is None:
            return StructuredFactReadResponse(status="unavailable")
        return self._learned_ontology.read_structured_facts(request)

    def close(self) -> None:
        """Release resources owned by the installed learned runtime."""
        if self._learned_ontology is not None and self._learned_ontology.close is not None:
            self._learned_ontology.close()


def build_authenticated_source_runtime(
    *,
    issue_ingress: Callable[
        [AuthenticatedSourceSubmission], AuthenticatedHostIngress
    ],
    verified_production_host_authority: VerifiedProductionHostAuthority | None = None,
    provider_service: ProviderMemoryService | None = None,
    memory_plane: MemoryPlaneService | None = None,
    revoked_view: RevokedIdentityServingGate | None = None,
    now_provider: Callable[[], datetime] | None = None,
    verified_capability_monitoring_authorities: tuple[
        VerifiedCapabilityMonitoringAuthority, ...
    ] = (),
    learned_ontology: AuthenticatedSourceLearnedOntologyBinding | None = None,
) -> AuthenticatedSourceRuntime:
    """Build the public non-Hermes source root from verified host authority."""

    if provider_service is not None:
        if memory_plane is not None or verified_production_host_authority is not None:
            raise ValueError("authenticated source runtime service composition is ambiguous")
        service = provider_service
    else:
        if verified_production_host_authority is None:
            raise ValueError("authenticated source runtime requires verified host authority")
        if revoked_view is None:
            raise ValueError(
                "revoked_view is required: derive it from the installation"
                " control root (RefreshingRevokedIdentityView) or state an"
                " explicit empty view for ephemeral planes"
            )
        service = build_provider_memory_service_from_env(
            memory_plane=memory_plane,
            revoked_view=revoked_view,
            verified_production_host_authority=verified_production_host_authority,
            verified_capability_monitoring_authorities=(
                verified_capability_monitoring_authorities
            ),
            now_provider=now_provider,
        )
    return AuthenticatedSourceRuntime(
        adapter=AuthenticatedSourceAdapter(service),
        issue_ingress=issue_ingress,
        learned_ontology=learned_ontology,
    )


__all__ = [
    "AuthenticatedSourceAdapter",
    "AuthenticatedSourceLearnedOntologyBinding",
    "AuthenticatedSourceRuntime",
    "AuthenticatedSourceSubmission",
    "build_authenticated_source_runtime",
]
