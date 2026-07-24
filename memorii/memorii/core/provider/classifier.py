"""Deterministic provider-operation classification helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from memorii.core.provider.models import ProviderEvent, ProviderOperation
from memorii.domain.enums import SourceModality


def build_event_id(prefix: str, *, session_id: str | None, task_id: str | None) -> str:
    """Return a process-independent identifier for a newly observed event.

    Generated identifiers express uniqueness, not replay identity. Integrations
    that can recognize a replay must pass their own stable ``operation_id``.
    """

    identity = session_id or task_id or "global"
    return f"prov:{prefix}:{identity}:{uuid4()}"


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
    language: str = "en",
    timestamp: datetime | None = None,
    source_modality: SourceModality | None = None,
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
        language=language,
        timestamp=timestamp or datetime.now(UTC),
        source_modality=source_modality,
    )
