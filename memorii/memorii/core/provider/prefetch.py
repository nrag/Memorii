"""Provider prefetch query classification and formatting."""

from __future__ import annotations

from memorii.core.provider.models import ProviderQueryClass, ProviderStoredRecord


def classify_prefetch_query(query: str) -> ProviderQueryClass:
    normalized = query.lower()
    if any(token in normalized for token in ("prefer", "preference", "my style", "for me", "profile")):
        return ProviderQueryClass.PREFERENCE_PROFILE
    if any(token in normalized for token in ("config", "setting", "fact", "policy", "default", "what is")):
        return ProviderQueryClass.FACT_CONFIG
    if any(token in normalized for token in ("last", "previous", "history", "earlier", "session")):
        return ProviderQueryClass.EVENT_HISTORY
    return ProviderQueryClass.GENERAL_CONTINUITY


def format_prefetch_context(records: list[ProviderStoredRecord]) -> str:
    if not records:
        return "No durable memory context available."
    lines = ["Memorii context:"]
    for record in records:
        lines.append(f"- [{record.domain.value}] {record.text}")
    return "\n".join(lines)
