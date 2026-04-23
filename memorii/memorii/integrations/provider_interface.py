"""Provider-facing protocol for Hermes-style memory hooks."""

from __future__ import annotations

from typing import Protocol

from memorii.core.provider.models import ProviderSyncResult, ProviderWriteDecision


class MemoryProviderInterface(Protocol):
    def prefetch(
        self,
        query: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> str: ...

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult: ...

    def on_session_end(
        self,
        messages: list[dict[str, object]] | list[str],
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult: ...

    def on_pre_compress(
        self,
        messages: list[dict[str, object]] | list[str],
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult: ...

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderWriteDecision: ...

    def on_delegation(
        self,
        task: str,
        result: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult: ...
