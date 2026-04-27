"""Provider interfaces for LLM-backed decision points."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)


class LLMDecisionProvider(Protocol):
    def decide(
        self,
        *,
        decision_point: LLMDecisionPoint,
        input_payload: dict[str, object],
        prompt_version: str | None = None,
    ) -> LLMDecisionTrace: ...


class DisabledLLMDecisionProvider:
    """Deterministic provider that always emits a fallback trace."""

    def decide(
        self,
        *,
        decision_point: LLMDecisionPoint,
        input_payload: dict[str, object],
        prompt_version: str | None = None,
    ) -> LLMDecisionTrace:
        return LLMDecisionTrace(
            trace_id=f"trace:{uuid4().hex}",
            decision_point=decision_point,
            mode=LLMDecisionMode.RULE_BASED,
            prompt_version=prompt_version,
            input_payload=input_payload,
            fallback_used=True,
            final_output={},
            status=LLMDecisionStatus.FALLBACK_USED,
            created_at=datetime.now(UTC),
        )
