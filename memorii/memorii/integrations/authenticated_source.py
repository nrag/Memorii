"""Framework-neutral adapter for authenticated retained memory sources."""

from __future__ import annotations

from collections.abc import Callable
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


class AuthenticatedSourceRuntime:
    """Non-Hermes composition root with a host-owned ingress issuer."""

    def __init__(
        self,
        *,
        adapter: AuthenticatedSourceAdapter,
        issue_ingress: Callable[[AuthenticatedSourceSubmission], AuthenticatedHostIngress],
    ) -> None:
        self._adapter = adapter
        self._issue_ingress = issue_ingress

    def submit(self, submission: AuthenticatedSourceSubmission) -> ProviderSyncResult:
        ingress = self._issue_ingress(submission)
        if not isinstance(ingress, AuthenticatedHostIngress):
            raise TypeError("authenticated source host returned invalid ingress")
        return self._adapter.submit(
            submission,
            authenticated_host_ingress=ingress,
        )


def build_authenticated_source_runtime(
    *,
    issue_ingress: Callable[
        [AuthenticatedSourceSubmission], AuthenticatedHostIngress
    ],
    verified_production_host_authority: VerifiedProductionHostAuthority,
    memory_plane: MemoryPlaneService | None = None,
    now_provider: Callable[[], datetime] | None = None,
    verified_capability_monitoring_authorities: tuple[
        VerifiedCapabilityMonitoringAuthority, ...
    ] = (),
) -> AuthenticatedSourceRuntime:
    """Build the public non-Hermes source root from verified host authority."""

    service = build_provider_memory_service_from_env(
        memory_plane=memory_plane,
        verified_production_host_authority=verified_production_host_authority,
        verified_capability_monitoring_authorities=(
            verified_capability_monitoring_authorities
        ),
        now_provider=now_provider,
    )
    return AuthenticatedSourceRuntime(
        adapter=AuthenticatedSourceAdapter(service),
        issue_ingress=issue_ingress,
    )


__all__ = [
    "AuthenticatedSourceAdapter",
    "AuthenticatedSourceRuntime",
    "AuthenticatedSourceSubmission",
    "build_authenticated_source_runtime",
]
