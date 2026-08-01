"""Hermes-style adapter over ProviderMemoryService."""

from __future__ import annotations

import json
from datetime import datetime

from memorii.core.memory_evolution.admission import (
    SemanticIngestionOutcomeLookupRequest,
    SemanticIngestionOutcomeLookupResponse,
)
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.provider.classifier import classify_memory_target
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import (
    ProviderOperation,
    ProviderSyncResult,
    ProviderWriteDecision,
    normalize_delivery_id,
)
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.provider_interface import MemoryProviderInterface


class HermesMemoryProvider(MemoryProviderInterface):
    def __init__(
        self,
        service: ProviderMemoryService | None = None,
    ) -> None:
        self._service = service or build_provider_memory_service_from_env()

    def prefetch(
        self,
        query: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        query_language: str = "en",
        reference_time: datetime | None = None,
    ) -> str:
        return self._service.prefetch(
            query,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            query_language=query_language,
            reference_time=reference_time,
        )

    def lookup_semantic_ingestion_outcome(
        self,
        request: SemanticIngestionOutcomeLookupRequest,
        *,
        authenticated_host_ingress: AuthenticatedHostIngress,
    ) -> SemanticIngestionOutcomeLookupResponse:
        return self._service.lookup_semantic_ingestion_outcome(
            request, authenticated_host_ingress=authenticated_host_ingress
        )

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        operation_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        authenticated_host_ingress: AuthenticatedHostIngress | None = None,
    ) -> ProviderSyncResult:
        user_result = self._service._sync_composite_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content=user_content,
            role="user",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            composite_operation_id=_child_operation_id(operation_id, "user"),
            authenticated_host_ingress=authenticated_host_ingress,
        )
        assistant_result = self._service._sync_composite_event(
            operation=ProviderOperation.CHAT_ASSISTANT_TURN,
            content=assistant_content,
            role="assistant",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            composite_operation_id=_child_operation_id(operation_id, "assistant"),
            authenticated_host_ingress=authenticated_host_ingress,
        )
        return ProviderSyncResult(
            transcript_ids=[*user_result.transcript_ids, *assistant_result.transcript_ids],
            candidate_ids=[*user_result.candidate_ids, *assistant_result.candidate_ids],
            blocked_domains=sorted(
                set(user_result.blocked_domains) | set(assistant_result.blocked_domains), key=lambda domain: domain.value
            ),
            blocked_reasons={**user_result.blocked_reasons, **assistant_result.blocked_reasons},
            allowed_candidate_domains=sorted(
                set(user_result.allowed_candidate_domains) | set(assistant_result.allowed_candidate_domains),
                key=lambda domain: domain.value,
            ),
            raw_append_domains=sorted(
                set(user_result.raw_append_domains) | set(assistant_result.raw_append_domains),
                key=lambda domain: domain.value,
            ),
            blocked_commit_domains=sorted(
                set(user_result.blocked_commit_domains) | set(assistant_result.blocked_commit_domains),
                key=lambda domain: domain.value,
            ),
            evolution_outcomes=[
                *user_result.evolution_outcomes,
                *assistant_result.evolution_outcomes,
            ],
        )

    def on_session_end(
        self,
        messages: list[dict[str, object]] | list[str],
        *,
        operation_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        authenticated_host_ingress: AuthenticatedHostIngress | None = None,
    ) -> ProviderSyncResult:
        return self._service.sync_event(
            operation=ProviderOperation.SESSION_END,
            content=_messages_to_snapshot_text(messages),
            role="system",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            operation_id=operation_id,
            authenticated_host_ingress=authenticated_host_ingress,
        )

    def on_pre_compress(
        self,
        messages: list[dict[str, object]] | list[str],
        *,
        operation_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        authenticated_host_ingress: AuthenticatedHostIngress | None = None,
    ) -> ProviderSyncResult:
        return self._service.sync_event(
            operation=ProviderOperation.PRE_COMPRESS,
            content=_messages_to_snapshot_text(messages),
            role="system",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            operation_id=operation_id,
            authenticated_host_ingress=authenticated_host_ingress,
        )

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        *,
        operation_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        authenticated_host_ingress: AuthenticatedHostIngress | None = None,
    ) -> ProviderWriteDecision:
        return self._service.apply_memory_write(
            operation=classify_memory_target(target),
            content=content,
            action=action,
            target=target,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            operation_id=operation_id,
            authenticated_host_ingress=authenticated_host_ingress,
        )

    def on_delegation(
        self,
        task: str,
        result: str,
        *,
        operation_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        authenticated_host_ingress: AuthenticatedHostIngress | None = None,
    ) -> ProviderSyncResult:
        return self._service.sync_event(
            operation=ProviderOperation.DELEGATION_RESULT,
            content=f"Task: {task}\nResult: {result}",
            role="system",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            operation_id=operation_id,
            authenticated_host_ingress=authenticated_host_ingress,
        )


def _messages_to_snapshot_text(messages: list[dict[str, object]] | list[str]) -> str:
    """Preserve the adapter-visible shape and scalar values in canonical UTF-8 JSON."""

    return json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _child_operation_id(parent: str, child: str) -> str:
    # Delay the canonical-contract import to avoid the provider/package import
    # cycle during application composition.
    from memorii.core.memory_evolution.ingestion_contracts import derive_composite_child_delivery_id

    return derive_composite_child_delivery_id(normalize_delivery_id(parent), child)
