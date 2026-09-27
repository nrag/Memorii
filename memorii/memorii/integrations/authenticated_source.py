"""Framework-neutral adapter for authenticated retained memory sources."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.provider.models import ProviderOperation, ProviderSyncResult
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import SourceModality


class AuthenticatedSourceSubmission(BaseModel):
    operation: ProviderOperation
    content: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
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
            session_id=submission.session_id,
            task_id=submission.task_id,
            user_id=submission.user_id,
            language=submission.language,
            speaker_id=submission.speaker_id,
            timestamp=submission.timestamp,
            source_modality=submission.source_modality,
            authenticated_host_ingress=authenticated_host_ingress,
        )


__all__ = ["AuthenticatedSourceAdapter", "AuthenticatedSourceSubmission"]
