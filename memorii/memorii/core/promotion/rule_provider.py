"""Deterministic promotion decision provider."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext, PromotionDecision


class RuleBasedPromotionDecisionProvider:
    def decide(self, *, context: PromotionContext) -> tuple[PromotionDecision, LLMDecisionTrace]:
        decision = self._decide_without_trace(context=context)
        trace = LLMDecisionTrace(
            trace_id=f"trace:{uuid4().hex}",
            decision_point=LLMDecisionPoint.PROMOTION,
            mode=LLMDecisionMode.RULE_BASED,
            input_payload=context.model_dump(mode="json"),
            parsed_output=decision.model_dump(mode="json"),
            final_output=decision.model_dump(mode="json"),
            status=LLMDecisionStatus.SUCCEEDED,
            created_at=datetime.now(UTC),
        )
        return decision.model_copy(update={"trace_id": trace.trace_id}), trace

    def _decide_without_trace(self, *, context: PromotionContext) -> PromotionDecision:
        if context.created_from in {"decision_finalized", "task_outcome", "investigation_conclusion"}:
            return PromotionDecision(
                promote=True,
                target_plane="episodic",
                confidence=0.8,
                rationale=context.created_from,
                tags=[context.created_from],
            )

        if context.candidate_type == PromotionCandidateType.USER_MEMORY:
            if context.explicit_user_memory_request:
                return PromotionDecision(
                    promote=True,
                    target_plane=PromotionCandidateType.USER_MEMORY.value,
                    confidence=0.9,
                    rationale="explicit_user_memory_request",
                    tags=["explicit_user_memory_request"],
                )
            return PromotionDecision(
                promote=False,
                confidence=0.2,
                rationale="observation_not_promoted",
                tags=["observation_not_promoted"],
            )

        if context.candidate_type in {PromotionCandidateType.SEMANTIC, PromotionCandidateType.PROJECT_FACT}:
            if context.repeated_across_episodes >= 3:
                return PromotionDecision(
                    promote=True,
                    target_plane=context.candidate_type.value,
                    confidence=0.7,
                    rationale="repeated_across_episodes",
                    tags=["repeated_across_episodes"],
                )

        return PromotionDecision(
            promote=False,
            confidence=0.2,
            rationale="observation_not_promoted",
            tags=["observation_not_promoted"],
        )
