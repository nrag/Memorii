from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.llm_decision.models import LLMDecisionTrace


class DecisionEngineResult(BaseModel):
    decision: dict[str, object]
    rule_trace: LLMDecisionTrace | None = None
    llm_trace: LLMDecisionTrace | None = None
    llm_used: bool = False
    llm_success: bool | None = None
    fallback_used: bool = False
    disagreement: bool = False
    errors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
