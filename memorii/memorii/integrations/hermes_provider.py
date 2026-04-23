"""Hermes-style adapter over ProviderMemoryService."""

from __future__ import annotations

from memorii.core.provider.classifier import classify_memory_target
from memorii.core.provider.models import ProviderOperation, ProviderSyncResult, ProviderWriteDecision
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.provider_interface import MemoryProviderInterface


class HermesMemoryProvider(MemoryProviderInterface):
    def __init__(self, service: ProviderMemoryService | None = None) -> None:
        self._service = service or ProviderMemoryService()

    def prefetch(
        self,
        query: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        return self._service.prefetch(query, session_id=session_id, task_id=task_id, user_id=user_id)

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult:
        user_result = self._service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content=user_content,
            role="user",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )
        assistant_result = self._service.sync_event(
            operation=ProviderOperation.CHAT_ASSISTANT_TURN,
            content=assistant_content,
            role="assistant",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
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
        )

    def on_session_end(
        self,
        messages: list[dict[str, object]] | list[str],
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult:
        return self._service.sync_event(
            operation=ProviderOperation.SESSION_END,
            content=_messages_to_text(messages),
            role="system",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )

    def on_pre_compress(
        self,
        messages: list[dict[str, object]] | list[str],
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult:
        return self._service.sync_event(
            operation=ProviderOperation.PRE_COMPRESS,
            content=_messages_to_text(messages),
            role="system",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderWriteDecision:
        return self._service.apply_memory_write(
            operation=classify_memory_target(target),
            content=content,
            action=action,
            target=target,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )

    def on_delegation(
        self,
        task: str,
        result: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult:
        return self._service.sync_event(
            operation=ProviderOperation.DELEGATION_RESULT,
            content=f"Task: {task}\nResult: {result}",
            role="system",
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )


def _messages_to_text(messages: list[dict[str, object]] | list[str]) -> str:
    serialized: list[str] = []
    for item in messages:
        if isinstance(item, str):
            serialized.append(item)
        else:
            role = str(item.get("role", "unknown"))
            content = str(item.get("content", ""))
            serialized.append(f"{role}: {content}")
    return "\n".join(serialized)
