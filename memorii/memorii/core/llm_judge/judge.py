"""Single-dimension judge contracts and deterministic fake judge implementations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Callable, Protocol

from memorii.core.llm_judge.models import JudgeDimension, JudgeRubric, JudgeVerdict


class SingleDimensionJudge(Protocol):
    judge_id: str
    dimension: JudgeDimension
    rubric: JudgeRubric

    def judge(
        self,
        *,
        input_payload: dict[str, object],
        snapshot_id: str | None = None,
        trace_id: str | None = None,
    ) -> JudgeVerdict:
        ...


def validate_single_dimension_judge(judge: SingleDimensionJudge) -> None:
    if judge.dimension != judge.rubric.dimension:
        raise ValueError("judge dimension must match rubric dimension")
    if judge.judge_id != judge.rubric.judge_id:
        raise ValueError("judge_id must match rubric judge_id")

    if not judge.rubric.description.strip():
        raise ValueError("rubric description must be non-empty")

    anchors = [judge.rubric.score_1_anchor, judge.rubric.score_0_5_anchor, judge.rubric.score_0_anchor]
    if any(not anchor.strip() for anchor in anchors):
        raise ValueError("rubric score anchors must be non-empty")


class FakeSingleDimensionJudge:
    def __init__(
        self,
        *,
        judge_id: str,
        dimension: JudgeDimension,
        rubric: JudgeRubric,
        default_score: float,
        default_rationale: str,
        default_failure_mode: str | None = None,
        default_needs_human_review: bool = False,
        score_by_input_field_value: dict[str, dict[object, float]] | None = None,
        failure_mode_by_input_field_value: dict[str, dict[object, str | None]] | None = None,
        created_at_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.judge_id = judge_id
        self.dimension = dimension
        self.rubric = rubric
        self.default_score = default_score
        self.default_rationale = default_rationale
        self.default_failure_mode = default_failure_mode
        self.default_needs_human_review = default_needs_human_review
        self.score_by_input_field_value = score_by_input_field_value or {}
        self.failure_mode_by_input_field_value = failure_mode_by_input_field_value or {}
        self.created_at_factory = created_at_factory or (lambda: datetime.now(UTC))

    def judge(
        self,
        *,
        input_payload: dict[str, object],
        snapshot_id: str | None = None,
        trace_id: str | None = None,
    ) -> JudgeVerdict:
        score = self.default_score
        failure_mode = self.default_failure_mode

        for field_name, value_scores in self.score_by_input_field_value.items():
            if field_name in input_payload and input_payload[field_name] in value_scores:
                score = value_scores[input_payload[field_name]]

        for field_name, value_modes in self.failure_mode_by_input_field_value.items():
            if field_name in input_payload and input_payload[field_name] in value_modes:
                failure_mode = value_modes[input_payload[field_name]]

        passed = score >= self.rubric.pass_threshold
        stable_key = {
            "judge_id": self.judge_id,
            "dimension": self.dimension.value,
            "snapshot_id": snapshot_id,
            "trace_id": trace_id,
            "input_payload": input_payload,
        }
        digest = hashlib.sha256(json.dumps(stable_key, sort_keys=True).encode("utf-8")).hexdigest()[:16]

        return JudgeVerdict(
            verdict_id=f"judgeverdict:{digest}",
            judge_id=self.judge_id,
            dimension=self.dimension,
            snapshot_id=snapshot_id,
            trace_id=trace_id,
            passed=passed,
            score=score,
            rationale=self.default_rationale,
            failure_mode=failure_mode,
            needs_human_review=self.default_needs_human_review,
            created_at=self.created_at_factory(),
        )
