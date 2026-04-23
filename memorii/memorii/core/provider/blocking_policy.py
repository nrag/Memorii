"""Deterministic feature extraction and provider-level blocking policy."""

from __future__ import annotations

import re

from memorii.core.provider.models import ProviderOperation, ProviderTextFeatures
from memorii.domain.enums import MemoryDomain

_EVENT_RE = re.compile(r"\b(yesterday|today|incident|error|failed|resolved|fixed|deployed|happened)\b", re.IGNORECASE)
_FACT_RE = re.compile(r"\b(always|must|requires|uses|is|are|configured|policy|default)\b", re.IGNORECASE)
_USER_PREF_RE = re.compile(r"\b(i prefer|i like|my preference|for me|my timezone|i usually|my style)\b", re.IGNORECASE)
_USER_GROUND_RE = re.compile(r"\b(user said|the user said|i am|my |for me|as a user)\b", re.IGNORECASE)
_UNCERTAINTY_RE = re.compile(r"\b(maybe|might|guess|probably|possibly|seems|speculative|uncertain)\b", re.IGNORECASE)
_TEMPORAL_RE = re.compile(r"\b(today|tomorrow|yesterday|last week|this week|at \d|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_LOG_RE = re.compile(r"(traceback|stack trace|log\s*:\s|\[info\]|\[error\]|http\s\d{3})", re.IGNORECASE)


def extract_text_features(text: str) -> ProviderTextFeatures:
    normalized = text.strip()
    if len(normalized) < 50:
        length_bucket = "short"
    elif len(normalized) < 240:
        length_bucket = "medium"
    else:
        length_bucket = "long"
    return ProviderTextFeatures(
        looks_like_event=bool(_EVENT_RE.search(normalized)),
        looks_like_stable_fact=bool(_FACT_RE.search(normalized)) and not bool(_TEMPORAL_RE.search(normalized)),
        looks_like_user_preference=bool(_USER_PREF_RE.search(normalized)),
        has_explicit_user_grounding=bool(_USER_GROUND_RE.search(normalized)),
        has_uncertainty_marker=bool(_UNCERTAINTY_RE.search(normalized)),
        has_temporal_marker=bool(_TEMPORAL_RE.search(normalized)),
        looks_like_log_dump=bool(_LOG_RE.search(normalized)),
        length_bucket=length_bucket,
    )


def evaluate_operation_policy(
    *, operation: ProviderOperation, features: ProviderTextFeatures
) -> tuple[list[MemoryDomain], list[MemoryDomain], dict[str, str]]:
    blocked: list[MemoryDomain] = []
    allowed_candidates: list[MemoryDomain] = []
    reasons: dict[str, str] = {}

    if operation in {ProviderOperation.CHAT_USER_TURN, ProviderOperation.CHAT_ASSISTANT_TURN}:
        blocked.extend([MemoryDomain.SEMANTIC, MemoryDomain.USER])
        reasons[MemoryDomain.SEMANTIC.value] = "turn-level text cannot directly commit semantic memory"
        reasons[MemoryDomain.USER.value] = "turn-level text cannot directly commit user memory"
        if features.looks_like_event:
            allowed_candidates.append(MemoryDomain.EPISODIC)
        else:
            blocked.append(MemoryDomain.EPISODIC)
            reasons[MemoryDomain.EPISODIC.value] = "non-event turn did not meet episodic candidate threshold"

    if operation == ProviderOperation.MEMORY_WRITE_LONGTERM:
        blocked.extend([MemoryDomain.SEMANTIC, MemoryDomain.USER])
        reasons[MemoryDomain.USER.value] = "long-term memory target cannot write user profile directly"
        if (
            features.looks_like_stable_fact
            and not features.has_uncertainty_marker
            and not features.looks_like_log_dump
            and not features.looks_like_user_preference
            and not features.has_temporal_marker
        ):
            allowed_candidates.append(MemoryDomain.SEMANTIC)
        else:
            reasons[MemoryDomain.SEMANTIC.value] = "semantic write blocked: speculative/transient or log-like"

    if operation == ProviderOperation.MEMORY_WRITE_USER:
        blocked.extend([MemoryDomain.SEMANTIC, MemoryDomain.USER])
        reasons[MemoryDomain.SEMANTIC.value] = "user-targeted write not eligible for semantic domain"
        if (
            features.looks_like_user_preference
            and features.has_explicit_user_grounding
            and not features.has_uncertainty_marker
            and not features.looks_like_log_dump
        ):
            allowed_candidates.append(MemoryDomain.USER)
            blocked = [d for d in blocked if d != MemoryDomain.USER]
            reasons.pop(MemoryDomain.USER.value, None)
        else:
            reasons[MemoryDomain.USER.value] = "user write blocked: missing explicit durable user grounding"

    if operation in {ProviderOperation.SESSION_END, ProviderOperation.PRE_COMPRESS}:
        blocked.extend([MemoryDomain.SEMANTIC, MemoryDomain.USER])
        reasons[MemoryDomain.SEMANTIC.value] = "session summary cannot directly commit semantic memory"
        reasons[MemoryDomain.USER.value] = "session summary cannot directly commit user memory"
        if features.looks_like_event and not features.has_uncertainty_marker:
            allowed_candidates.append(MemoryDomain.EPISODIC)
        else:
            reasons[MemoryDomain.EPISODIC.value] = "session summary not event-grounded enough for episodic candidate"
            blocked.append(MemoryDomain.EPISODIC)

    if operation == ProviderOperation.DELEGATION_RESULT:
        blocked.extend([MemoryDomain.SEMANTIC, MemoryDomain.USER])
        reasons[MemoryDomain.SEMANTIC.value] = "delegation output blocked from direct semantic commit"
        reasons[MemoryDomain.USER.value] = "delegation output blocked from direct user commit"
        if features.looks_like_event:
            allowed_candidates.append(MemoryDomain.EPISODIC)

    return sorted(set(blocked), key=lambda domain: domain.value), sorted(
        set(allowed_candidates), key=lambda domain: domain.value
    ), reasons
