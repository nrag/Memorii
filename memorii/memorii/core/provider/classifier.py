"""Deterministic provider-operation classification helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.provider.models import ProviderEvent, ProviderOperation


def build_event_id(prefix: str, *, session_id: str | None, task_id: str | None, sequence: int) -> str:
    identity = session_id or task_id or "global"
    return f"prov:{prefix}:{identity}:{sequence}"


def classify_memory_target(target: str) -> ProviderOperation:
    normalized = target.strip().lower()
    if normalized in {"memory", "long_term", "semantic", "knowledge"}:
        return ProviderOperation.MEMORY_WRITE_LONGTERM
    if normalized in {"user", "profile", "preference"}:
        return ProviderOperation.MEMORY_WRITE_USER
    if normalized in {"dailylog", "daily_log", "transcript", "log"}:
        return ProviderOperation.MEMORY_WRITE_DAILYLOG
    return ProviderOperation.UNKNOWN


def make_event(
    *,
    event_id: str,
    operation: ProviderOperation,
    content: str | None = None,
    role: str | None = None,
    target: str | None = None,
    action: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
    timestamp: datetime | None = None,
) -> ProviderEvent:
    return ProviderEvent(
        event_id=event_id,
        operation=operation,
        content=content,
        role=role,
        target=target,
        action=action,
        session_id=session_id,
        task_id=task_id,
        user_id=user_id,
        timestamp=timestamp or datetime.now(UTC),
    )
