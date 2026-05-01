from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class LLMTracePolicy(BaseModel):
    trace_successes: bool = False
    trace_failures: bool = True
    trace_fallbacks: bool = True
    trace_disagreements: bool = True
    trace_human_review: bool = True
    min_judge_score_to_keep: float | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("min_judge_score_to_keep")
    @classmethod
    def _validate_min_judge_score_to_keep(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < 0.0 or value > 1.0:
            raise ValueError("min_judge_score_to_keep must be between 0.0 and 1.0")
        return value

    def should_persist(self, *, llm_used: bool, llm_success: bool | None, fallback_used: bool, disagreement: bool, requires_judge_review: bool, judge_score: float | None = None) -> bool:
        if fallback_used and self.trace_fallbacks:
            return True
        if disagreement and self.trace_disagreements:
            return True
        if requires_judge_review and self.trace_human_review:
            return True
        if llm_used and llm_success is False and self.trace_failures:
            return True
        if llm_used and llm_success is True and self.trace_successes:
            return True
        if self.min_judge_score_to_keep is not None and judge_score is not None:
            return judge_score <= self.min_judge_score_to_keep
        return False
