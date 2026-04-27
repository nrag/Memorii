"""Deterministic decision-state summaries for provider recall/state output."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.decision_state.models import DecisionState


class DecisionStateSummary(BaseModel):
    decision_id: str
    question: str
    status: str
    option_labels: list[str] = Field(default_factory=list)
    criteria_labels: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    final_decision: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def summarize_decision_state(decision: DecisionState) -> DecisionStateSummary:
    return DecisionStateSummary(
        decision_id=decision.decision_id,
        question=decision.question,
        status=decision.status.value,
        option_labels=[option.label for option in decision.options],
        criteria_labels=[criterion.label for criterion in decision.criteria],
        recommendation=decision.current_recommendation,
        final_decision=decision.final_decision,
        unresolved_questions=list(decision.unresolved_questions),
    )
