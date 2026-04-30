"""Offline deterministic eval result models for LLM decision points."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvalCaseResult(BaseModel):
    snapshot_id: str
    decision_point: str
    passed: bool
    score: float
    errors: list[str] = Field(default_factory=list)
    actual_output: dict[str, object]
    expected_output: dict[str, object] | None = None
    trace_id: str | None = None
    judge_verdict_refs: list[str] = Field(default_factory=list)
    requires_judge_review: bool = False
    decision_mode: str = "rule"
    llm_used: bool = False
    llm_success: bool | None = None
    fallback_used: bool = False
    disagreement: bool = False

    model_config = ConfigDict(extra="forbid")


class EvalRunReport(BaseModel):
    run_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    average_score: float
    results: list[EvalCaseResult]
    count_by_decision_point: dict[str, int]
    pass_rate_by_decision_point: dict[str, float]

    model_config = ConfigDict(extra="forbid")
