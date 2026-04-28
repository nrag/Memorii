"""Belief direction single-dimension judge and calibration fixtures."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Callable

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.llm_judge.models import CalibrationExample, JudgeDimension, JudgeRubric, JudgeVerdict
from memorii.core.solver.abstention import SolverDecision


def belief_direction_rubric() -> JudgeRubric:
    return JudgeRubric(
        judge_id="belief_direction:v1",
        dimension=JudgeDimension.BELIEF_DIRECTION,
        name="Belief Direction",
        description="Judge whether belief moved in the correct directional sense from evidence/decision.",
        score_1_anchor="Belief moved in expected direction (increase/decrease/hold).",
        score_0_5_anchor="Direction is ambiguous due to conflict/downgrade/missing evidence.",
        score_0_anchor="Belief moved in wrong direction.",
        pass_threshold=0.7,
        failure_modes=[
            "should_increase",
            "should_decrease",
            "should_not_increase",
            "should_remain_uncertain",
            "ambiguous_direction",
        ],
    )


class BeliefDirectionJudge:
    def __init__(self, *, rubric: JudgeRubric | None = None, created_at_factory: Callable[[], datetime] | None = None) -> None:
        self.rubric = rubric or belief_direction_rubric()
        self.judge_id = self.rubric.judge_id
        self.dimension = self.rubric.dimension
        self.created_at_factory = created_at_factory or (lambda: datetime.now(UTC))

    def judge(
        self,
        *,
        input_payload: dict[str, object],
        snapshot_id: str | None = None,
        trace_id: str | None = None,
    ) -> JudgeVerdict:
        context, actual_output = self._extract_context_and_output(input_payload=input_payload)
        score, rationale, failure_mode = self._score(context=context, actual_output=actual_output)
        passed = score >= self.rubric.pass_threshold
        if passed:
            failure_mode = None

        stable_key = {
            "judge_id": self.judge_id,
            "dimension": self.dimension.value,
            "snapshot_id": snapshot_id,
            "trace_id": trace_id,
            "context": context.model_dump(mode="json"),
            "actual_output": actual_output,
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
            rationale=rationale,
            failure_mode=failure_mode,
            created_at=self.created_at_factory(),
        )

    def _extract_context_and_output(self, *, input_payload: dict[str, object]) -> tuple[BeliefUpdateContext, dict[str, object] | None]:
        if isinstance(input_payload.get("input_payload"), dict):
            ctx_raw = input_payload["input_payload"]
            actual = input_payload.get("actual_output")
        elif isinstance(input_payload.get("context"), dict):
            ctx_raw = input_payload["context"]
            actual = input_payload.get("actual_output")
        else:
            ctx_raw = input_payload
            actual = input_payload.get("actual_output") if isinstance(input_payload.get("actual_output"), dict) else None

        context = BeliefUpdateContext.model_validate(ctx_raw)
        actual_output = actual if isinstance(actual, dict) else None
        return context, actual_output

    def _expected_direction(self, context: BeliefUpdateContext) -> str:
        if context.decision == SolverDecision.REFUTED:
            return "decrease"
        if context.decision in {SolverDecision.INSUFFICIENT_EVIDENCE, SolverDecision.NEEDS_TEST}:
            return "no_increase"
        if context.verifier_downgraded or context.conflict_count > 0 or context.missing_evidence_count > 0:
            return "ambiguous"
        if context.decision == SolverDecision.SUPPORTED:
            return "increase"
        return "ambiguous"

    def _score(self, *, context: BeliefUpdateContext, actual_output: dict[str, object] | None) -> tuple[float, str, str | None]:
        expected = self._expected_direction(context)
        prior = context.prior_belief

        if actual_output is None or not isinstance(actual_output.get("belief"), (int, float)) or prior is None:
            if expected == "ambiguous":
                return 0.5, "expected_direction_ambiguous", "ambiguous_direction"
            if expected == "increase":
                return 1.0, "expected_increase_without_actual_output", None
            if expected == "decrease":
                return 1.0, "expected_decrease_without_actual_output", None
            return 1.0, "expected_no_material_increase_without_actual_output", None

        actual_belief = float(actual_output["belief"])
        delta = actual_belief - prior

        if expected == "increase":
            if delta > 0.02:
                return 1.0, "increased_as_expected", None
            return 0.0, "should_increase", "should_increase"

        if expected == "decrease":
            if delta < -0.02:
                return 1.0, "decreased_as_expected", None
            return 0.0, "should_decrease", "should_decrease"

        if expected == "no_increase":
            if delta <= 0.02:
                return 1.0, "did_not_increase_materially", None
            return 0.0, "should_not_increase", "should_not_increase"

        if -0.05 <= delta <= 0.05:
            return 0.5, "ambiguous_conflict_case", "ambiguous_direction"
        if delta > 0.05:
            return 0.0, "should_remain_uncertain", "should_remain_uncertain"
        return 0.5, "ambiguous_conflict_case", "ambiguous_direction"


def belief_direction_calibration_v1() -> list[CalibrationExample]:
    examples: list[CalibrationExample] = []

    def add(eid: str, payload: dict[str, object], passed: bool, score: float, failure: str | None, tags: list[str]) -> None:
        examples.append(
            CalibrationExample(
                example_id=eid,
                dimension=JudgeDimension.BELIEF_DIRECTION,
                input_payload=payload,
                expected_passed=passed,
                expected_score_min=score,
                expected_score_max=score,
                expected_failure_mode=failure,
                tags=tags,
            )
        )

    for idx in range(1, 11):
        add(
            f"bd:pass:{idx:02d}",
            {
                "context": _ctx(SolverDecision.SUPPORTED, prior=0.35),
                "actual_output": {"belief": 0.75},
            },
            True,
            1.0,
            None,
            ["domain:software_engineering" if idx <= 5 else "domain:customer_support"],
        )

    for idx in range(1, 9):
        add(
            f"bd:refute:{idx:02d}",
            {
                "context": _ctx(SolverDecision.REFUTED, prior=0.72),
                "actual_output": {"belief": 0.2},
            },
            True,
            1.0,
            None,
            ["domain:incident_debugging" if idx <= 4 else "domain:research"],
        )

    for idx in range(1, 7):
        add(
            f"bd:noinc:{idx:02d}",
            {
                "context": _ctx(SolverDecision.INSUFFICIENT_EVIDENCE if idx <= 3 else SolverDecision.NEEDS_TEST, prior=0.45),
                "actual_output": {"belief": 0.46},
            },
            True,
            1.0,
            None,
            ["domain:project_planning"],
        )

    for idx in range(1, 7):
        add(
            f"bd:amb:{idx:02d}",
            {
                "context": _ctx(SolverDecision.SUPPORTED, prior=0.5, conflicts=1 if idx % 2 == 0 else 0, downgraded=idx % 3 == 0, missing=1 if idx % 5 == 0 else 0),
                "actual_output": {"belief": 0.52},
            },
            False,
            0.5,
            "ambiguous_direction",
            ["domain:agent_runtime", "domain:incident_debugging"],
        )

    return examples


def _ctx(
    decision: SolverDecision,
    *,
    prior: float,
    conflicts: int = 0,
    downgraded: bool = False,
    missing: int = 0,
) -> dict[str, object]:
    return {
        "prior_belief": prior,
        "decision": decision.value,
        "evidence_count": 2,
        "missing_evidence_count": missing,
        "verifier_downgraded": downgraded,
        "conflict_count": conflicts,
        "evidence_ids": ["ev:1"],
        "missing_evidence": ["missing"] if missing else [],
        "metadata": {},
    }
