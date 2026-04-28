"""Memory plane single-dimension judge and calibration fixtures."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Callable

from memorii.core.llm_judge.models import CalibrationExample, JudgeDimension, JudgeRubric, JudgeVerdict
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext

_VALID_PLANES = {"episodic", "semantic", "user_memory", "project_fact"}


def memory_plane_rubric() -> JudgeRubric:
    return JudgeRubric(
        judge_id="memory_plane:v1",
        dimension=JudgeDimension.MEMORY_PLANE,
        name="Memory Plane",
        description="Judge whether selected target memory plane is correct.",
        score_1_anchor="Target plane clearly matches memory kind.",
        score_0_5_anchor="More than one plane plausible / review needed.",
        score_0_anchor="Target plane clearly wrong.",
        pass_threshold=0.7,
        failure_modes=[
            "should_be_episodic",
            "should_be_semantic",
            "should_be_user_memory",
            "should_be_project_fact",
            "ambiguous_plane",
        ],
    )


class MemoryPlaneJudge:
    def __init__(self, *, rubric: JudgeRubric | None = None, created_at_factory: Callable[[], datetime] | None = None) -> None:
        self.rubric = rubric or memory_plane_rubric()
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

    def _extract_context_and_output(self, *, input_payload: dict[str, object]) -> tuple[PromotionContext, dict[str, object] | None]:
        if isinstance(input_payload.get("input_payload"), dict):
            context = PromotionContext.model_validate(input_payload["input_payload"])
            actual = input_payload.get("actual_output")
        elif isinstance(input_payload.get("context"), dict):
            context = PromotionContext.model_validate(input_payload["context"])
            actual = input_payload.get("actual_output")
        else:
            context = PromotionContext.model_validate(input_payload)
            actual = input_payload.get("actual_output") if isinstance(input_payload.get("actual_output"), dict) else None

        return context, actual if isinstance(actual, dict) else None

    def _expected_plane(self, context: PromotionContext) -> str:
        content = context.content.lower()
        if bool(context.metadata.get("inferred_user_preference", False)) or context.related_memory_ids:
            return "ambiguous"
        if context.candidate_type == PromotionCandidateType.USER_MEMORY or context.explicit_user_memory_request:
            return "user_memory"
        if context.created_from in {"task_outcome", "investigation_conclusion", "decision_finalized"}:
            return "episodic"
        if context.candidate_type == PromotionCandidateType.SEMANTIC:
            return "semantic"
        if context.candidate_type == PromotionCandidateType.PROJECT_FACT or any(token in content for token in ("customer", "project", "roadmap")):
            return "project_fact"
        return "ambiguous"

    def _score(self, *, context: PromotionContext, actual_output: dict[str, object] | None) -> tuple[float, str, str | None]:
        expected = self._expected_plane(context)
        actual_plane = str(actual_output.get("target_plane", "")) if actual_output else ""

        if expected == "ambiguous":
            return 0.5, "ambiguous_plane_boundary", "ambiguous_plane"

        if not actual_plane:
            return 1.0, f"expected_plane:{expected}", None

        if actual_plane not in _VALID_PLANES:
            return 0.5, "invalid_plane_name", "ambiguous_plane"

        if actual_plane == expected:
            return 1.0, "target_plane_correct", None

        if expected == "episodic":
            return 0.0, "should_be_episodic", "should_be_episodic"
        if expected == "semantic":
            return 0.0, "should_be_semantic", "should_be_semantic"
        if expected == "user_memory":
            return 0.0, "should_be_user_memory", "should_be_user_memory"
        return 0.0, "should_be_project_fact", "should_be_project_fact"


def memory_plane_calibration_v1() -> list[CalibrationExample]:
    examples: list[CalibrationExample] = []

    def add(eid: str, payload: dict[str, object], passed: bool, score: float, failure: str | None, tags: list[str]) -> None:
        examples.append(
            CalibrationExample(
                example_id=eid,
                dimension=JudgeDimension.MEMORY_PLANE,
                input_payload=payload,
                expected_passed=passed,
                expected_score_min=score,
                expected_score_max=score,
                expected_failure_mode=failure,
                tags=tags,
            )
        )

    categories = [
        ("episodic", PromotionCandidateType.EPISODIC, "task_outcome", "incident outcome closed", "domain:incident_outcomes"),
        ("semantic", PromotionCandidateType.SEMANTIC, "observation", "general parser rule", "domain:research"),
        ("user_memory", PromotionCandidateType.USER_MEMORY, "observation", "remember my timezone preference", "domain:user_preferences"),
        ("project_fact", PromotionCandidateType.PROJECT_FACT, "observation", "customer contract requires SSO", "domain:customer_support"),
    ]

    counter = 1
    for plane, ctype, created_from, content, domain in categories:
        for _ in range(8):
            add(
                f"mp:pass:{counter:02d}",
                {
                    "context": _payload(f"mp:cand:{counter}", ctype, content, created_from),
                    "actual_output": {"target_plane": plane},
                },
                True,
                1.0,
                None,
                [domain],
            )
            counter += 1

    for idx in range(1, 9):
        add(
            f"mp:amb:{idx:02d}",
            {
                "context": _payload(
                    f"mp:amb:{idx}",
                    PromotionCandidateType.USER_MEMORY,
                    "inferred preference from tone",
                    "observation",
                    metadata={"inferred_user_preference": True},
                ),
                "actual_output": {"target_plane": "user_memory"},
            },
            False,
            0.5,
            "ambiguous_plane",
            ["domain:user_preferences", "domain:architecture_decisions"],
        )

    return examples


def _payload(
    candidate_id: str,
    ctype: PromotionCandidateType,
    content: str,
    created_from: str,
    *,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": ctype.value,
        "content": content,
        "source_ids": ["src:1"],
        "related_memory_ids": [],
        "repeated_across_episodes": 3,
        "explicit_user_memory_request": ctype == PromotionCandidateType.USER_MEMORY,
        "created_from": created_from,
        "metadata": metadata or {},
    }
