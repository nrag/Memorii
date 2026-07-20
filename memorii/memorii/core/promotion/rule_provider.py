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
from memorii.core.promotion.assessment import (
    PromotionAssessment,
    PromotionAssessmentContext,
    PromotionCandidateType,
    PromotionFailureMode,
    PromotionReason,
)


class RuleBasedPromotionAssessmentProvider:
    def decide(self, *, context: PromotionAssessmentContext) -> tuple[PromotionAssessment, LLMDecisionTrace]:
        decision = self._decide_without_trace(context=context)
        trace = LLMDecisionTrace(
            trace_id=f"trace:{uuid4().hex}",
            decision_point=LLMDecisionPoint.PROMOTION,
            mode=LLMDecisionMode.RULE,
            input_payload=context.model_dump(mode="json"),
            parsed_output=decision.model_dump(mode="json"),
            final_output=decision.model_dump(mode="json"),
            status=LLMDecisionStatus.SUCCEEDED,
            created_at=datetime.now(UTC),
        )
        return decision.model_copy(update={"trace_id": trace.trace_id}), trace

    def _decide_without_trace(self, *, context: PromotionAssessmentContext) -> PromotionAssessment:
        if context.created_from in {"decision_finalized", "task_outcome", "investigation_conclusion"}:
            return PromotionAssessment(
                promote=True,
                target_plane="episodic",
                confidence=0.8,
                reason_code=PromotionReason(context.created_from),
                rationale=context.created_from,
                failure_mode=None,
                requires_judge_review=False,
                tags=[context.created_from],
            )

        if context.candidate_type == PromotionCandidateType.USER_MEMORY:
            if context.explicit_user_memory_request:
                return PromotionAssessment(
                    promote=True,
                    target_plane=PromotionCandidateType.USER_MEMORY.value,
                    confidence=0.9,
                    reason_code=PromotionReason.EXPLICIT_USER_MEMORY_REQUEST,
                    rationale="explicit_user_memory_request",
                    failure_mode=None,
                    requires_judge_review=False,
                    tags=["explicit_user_memory_request"],
                )
            return PromotionAssessment(
                promote=False,
                confidence=0.2,
                reason_code=PromotionReason.OBSERVATION_NOT_PROMOTED,
                rationale="observation_not_promoted",
                failure_mode=PromotionFailureMode.ONE_OFF_PREFERENCE,
                requires_judge_review=False,
                tags=["observation_not_promoted"],
            )

        if (
            context.candidate_type in {PromotionCandidateType.SEMANTIC, PromotionCandidateType.PROJECT_FACT}
            and context.repeated_across_episodes >= 3
        ):
            return PromotionAssessment(
                promote=True,
                target_plane=context.candidate_type.value,
                confidence=0.7,
                reason_code=PromotionReason.REPEATED_ACROSS_EPISODES,
                rationale="repeated_across_episodes",
                failure_mode=None,
                requires_judge_review=False,
                tags=["repeated_across_episodes"],
            )

        return PromotionAssessment(
            promote=False,
            confidence=0.2,
            reason_code=PromotionReason.OBSERVATION_NOT_PROMOTED,
            rationale="observation_not_promoted",
            failure_mode=PromotionFailureMode.INSUFFICIENT_REPETITION,
            requires_judge_review=False,
            tags=["observation_not_promoted"],
        )
