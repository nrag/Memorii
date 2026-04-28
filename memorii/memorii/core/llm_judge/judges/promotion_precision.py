"""Promotion precision single-dimension judge and calibration fixtures."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Callable

from pydantic import ValidationError

from memorii.core.llm_decision.models import EvalSnapshot
from memorii.core.llm_judge.models import CalibrationExample, JudgeDimension, JudgeRubric, JudgeVerdict
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext

_TIME_BOUND_MARKERS = (
    "next week",
    "this trip",
    "this sprint",
    "temporary",
    "for now",
)

_HIGH_VALUE_CREATED_FROM = {"task_outcome", "investigation_conclusion", "decision_finalized"}
_LOW_VALUE_MARKERS = (
    "user asked",
    "quick note",
    "fyi",
    "just checking",
    "status ping",
)


def promotion_precision_rubric() -> JudgeRubric:
    return JudgeRubric(
        judge_id="promotion_precision:v1",
        dimension=JudgeDimension.PROMOTION_PRECISION,
        name="Promotion Precision",
        description="Judge whether a promotion candidate should become durable memory at all.",
        score_1_anchor=(
            "Candidate clearly should become durable memory: completed outcome, explicit user memory request, "
            "stable repeated project fact, durable semantic fact, or investigation/decision conclusion."
        ),
        score_0_5_anchor=(
            "Candidate may be useful but needs review: repeated but inferred, scope-limited/time-bound, "
            "duplicate-prone, or incomplete evidence."
        ),
        score_0_anchor=(
            "Candidate should not become durable memory: noise, one-off context, transient planning, "
            "unconfirmed observation, temporary preference, or speculation."
        ),
        pass_threshold=0.7,
        failure_modes=[
            "noise",
            "one_off_preference",
            "unsupported_inference",
            "speculative_claim",
            "insufficient_repetition",
            "ambiguous_scope",
        ],
    )


class PromotionPrecisionJudge:
    def __init__(
        self,
        *,
        rubric: JudgeRubric | None = None,
        created_at_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.rubric = rubric or promotion_precision_rubric()
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
        context = self._extract_context(input_payload=input_payload)
        score, rationale, failure_mode = self._score_context(context=context)
        passed = score >= self.rubric.pass_threshold
        if passed:
            failure_mode = None

        normalized_payload = context.model_dump(mode="json")
        stable_key = {
            "judge_id": self.judge_id,
            "dimension": self.dimension.value,
            "snapshot_id": snapshot_id,
            "trace_id": trace_id,
            "input_payload": normalized_payload,
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

    def _extract_context(self, *, input_payload: dict[str, object]) -> PromotionContext:
        if isinstance(input_payload.get("input_payload"), dict):
            try:
                return PromotionContext.model_validate(input_payload["input_payload"])
            except ValidationError:
                snapshot = EvalSnapshot.model_validate(input_payload)
                return PromotionContext.model_validate(snapshot.input_payload)
        return PromotionContext.model_validate(input_payload)

    def _score_context(self, *, context: PromotionContext) -> tuple[float, str, str | None]:
        content = context.content.lower()
        marker_hit = next((marker for marker in _TIME_BOUND_MARKERS if marker in content), None)
        low_value_hit = next((marker for marker in _LOW_VALUE_MARKERS if marker in content), None)

        if context.metadata.get("speculative", False):
            return 0.0, "speculative_claim", "speculative_claim"

        if (
            context.candidate_type == PromotionCandidateType.USER_MEMORY
            and not context.explicit_user_memory_request
            and context.repeated_across_episodes < 3
        ):
            return 0.0, "one_off_preference", "one_off_preference"

        if marker_hit is not None:
            return 0.5, f"time_or_scope_bound:{marker_hit}", "ambiguous_scope"

        if low_value_hit is not None:
            return 0.0, f"low_value_noise:{low_value_hit}", "noise"

        if context.explicit_user_memory_request:
            return 1.0, "explicit_user_memory_request", None

        if context.created_from in _HIGH_VALUE_CREATED_FROM:
            return 1.0, context.created_from, None

        if (
            context.candidate_type in {PromotionCandidateType.SEMANTIC, PromotionCandidateType.PROJECT_FACT}
            and context.repeated_across_episodes >= 3
            and not context.related_memory_ids
        ):
            return 1.0, "repeated_durable_fact", None

        if context.candidate_type == PromotionCandidateType.USER_MEMORY and context.repeated_across_episodes >= 3:
            return 0.5, "inferred_repeated_preference", "ambiguous_scope"

        if context.related_memory_ids:
            return 0.5, "duplicate_prone_candidate", "ambiguous_scope"

        if bool(context.metadata.get("llm_followup_expected", False)):
            return 0.5, "llm_followup_expected", "ambiguous_scope"

        if (
            context.candidate_type in {PromotionCandidateType.SEMANTIC, PromotionCandidateType.PROJECT_FACT}
            and context.repeated_across_episodes < 3
        ):
            return 0.0, "insufficient_repetition", "insufficient_repetition"

        if context.created_from == "observation" and context.repeated_across_episodes < 3:
            if any(token in content for token in ("maybe", "might", "possibly", "guess", "seems")):
                return 0.0, "speculative_claim", "speculative_claim"
            return 0.0, "noise", "noise"

        return 0.0, "unsupported_inference", "unsupported_inference"


def promotion_precision_calibration_v1() -> list[CalibrationExample]:
    examples: list[CalibrationExample] = []

    def add(
        *,
        example_id: str,
        payload: dict[str, object],
        expected_passed: bool,
        score_min: float,
        score_max: float,
        failure_mode: str | None,
        tags: list[str],
    ) -> None:
        examples.append(
            CalibrationExample(
                example_id=example_id,
                dimension=JudgeDimension.PROMOTION_PRECISION,
                input_payload=payload,
                expected_passed=expected_passed,
                expected_score_min=score_min,
                expected_score_max=score_max,
                expected_failure_mode=failure_mode,
                tags=tags,
            )
        )

    # 10 clear pass.
    add(
        example_id="pp:pass:01",
        payload=_payload("cand:pass:01", PromotionCandidateType.USER_MEMORY, "Remember this preference permanently.", "observation", explicit=True),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:personal_assistant", "explicit_memory_request"],
    )
    add(
        example_id="pp:pass:02",
        payload=_payload("cand:pass:02", PromotionCandidateType.EPISODIC, "Shipped OAuth retry fix and closed incident.", "task_outcome"),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:incident_debugging", "completed_task_outcome"],
    )
    add(
        example_id="pp:pass:03",
        payload=_payload("cand:pass:03", PromotionCandidateType.EPISODIC, "Root cause identified: stale cache key in auth middleware.", "investigation_conclusion"),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:research", "investigation_conclusion"],
    )
    add(
        example_id="pp:pass:04",
        payload=_payload("cand:pass:04", PromotionCandidateType.EPISODIC, "Finalized decision to use Terraform modules for all new services.", "decision_finalized"),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:architecture_decisions", "finalized_decision"],
    )
    add(
        example_id="pp:pass:05",
        payload=_payload("cand:pass:05", PromotionCandidateType.SEMANTIC, "The ingestion worker is idempotent by dedupe key.", "observation", repeat=3),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:software_engineering", "repeated_semantic_fact"],
    )
    add(
        example_id="pp:pass:06",
        payload=_payload("cand:pass:06", PromotionCandidateType.PROJECT_FACT, "Beta launch depends on SOC2 vendor sign-off.", "observation", repeat=4),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:product_project_planning", "repeated_project_fact"],
    )
    add(
        example_id="pp:pass:07",
        payload=_payload("cand:pass:07", PromotionCandidateType.EPISODIC, "Closed support escalation after restoring webhook secret.", "task_outcome"),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:customer_support", "completed_task_outcome"],
    )
    add(
        example_id="pp:pass:08",
        payload=_payload("cand:pass:08", PromotionCandidateType.SEMANTIC, "Index rebuild requires write lock in this datastore.", "observation", repeat=5),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:architecture_decisions", "repeated_semantic_fact"],
    )
    add(
        example_id="pp:pass:09",
        payload=_payload("cand:pass:09", PromotionCandidateType.PROJECT_FACT, "Customer rollout checklist includes legal review stage.", "observation", repeat=3),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:customer_support", "repeated_project_fact"],
    )
    add(
        example_id="pp:pass:10",
        payload=_payload("cand:pass:10", PromotionCandidateType.USER_MEMORY, "Please remember I want weekly summaries by default.", "observation", explicit=True),
        expected_passed=True,
        score_min=1.0,
        score_max=1.0,
        failure_mode=None,
        tags=["domain:personal_assistant", "explicit_memory_request"],
    )

    # 10 clear fail.
    add(
        example_id="pp:fail:01",
        payload=_payload("cand:fail:01", PromotionCandidateType.EPISODIC, "User asked if tests passed.", "observation", repeat=1),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="noise",
        tags=["domain:software_engineering", "noisy_observation"],
    )
    add(
        example_id="pp:fail:02",
        payload=_payload("cand:fail:02", PromotionCandidateType.USER_MEMORY, "For this trip, I want aisle seats.", "observation", repeat=1),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="one_off_preference",
        tags=["domain:personal_assistant", "one_off_preference"],
    )
    add(
        example_id="pp:fail:03",
        payload=_payload("cand:fail:03", PromotionCandidateType.SEMANTIC, "Feature flags maybe caused the outage.", "observation", repeat=1, metadata={"speculative": True}),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="speculative_claim",
        tags=["domain:incident_debugging", "speculative_claim"],
    )
    add(
        example_id="pp:fail:04",
        payload=_payload("cand:fail:04", PromotionCandidateType.PROJECT_FACT, "Roadmap includes optional analytics cleanup.", "observation", repeat=1),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="insufficient_repetition",
        tags=["domain:product_project_planning", "insufficient_repetition"],
    )
    add(
        example_id="pp:fail:05",
        payload=_payload("cand:fail:05", PromotionCandidateType.USER_MEMORY, "User likes dark mode, probably.", "observation", repeat=2),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="one_off_preference",
        tags=["domain:personal_assistant", "inferred_preference_low_evidence"],
    )
    add(
        example_id="pp:fail:06",
        payload=_payload("cand:fail:06", PromotionCandidateType.EPISODIC, "Maybe infra issue fixed itself.", "observation", repeat=1),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="speculative_claim",
        tags=["domain:incident_debugging", "speculative_claim"],
    )
    add(
        example_id="pp:fail:07",
        payload=_payload("cand:fail:07", PromotionCandidateType.SEMANTIC, "The migration script usually works.", "observation", repeat=2),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="insufficient_repetition",
        tags=["domain:software_engineering", "insufficient_repetition"],
    )
    add(
        example_id="pp:fail:08",
        payload=_payload("cand:fail:08", PromotionCandidateType.PROJECT_FACT, "Support queue seemed calmer today.", "observation", repeat=1),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="insufficient_repetition",
        tags=["domain:customer_support", "noisy_observation"],
    )
    add(
        example_id="pp:fail:09",
        payload=_payload("cand:fail:09", PromotionCandidateType.EPISODIC, "Potential root cause might be DNS jitter.", "observation", repeat=1),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="speculative_claim",
        tags=["domain:research", "speculative_claim"],
    )
    add(
        example_id="pp:fail:10",
        payload=_payload("cand:fail:10", PromotionCandidateType.USER_MEMORY, "User asked for longer answer this one time.", "observation", repeat=1),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="one_off_preference",
        tags=["domain:personal_assistant", "one_off_preference"],
    )
    add(
        example_id="pp:fail:11",
        payload=_payload(
            "cand:fail:11",
            PromotionCandidateType.USER_MEMORY,
            "Remember this: quick note from today standup only.",
            "observation",
            explicit=True,
        ),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="noise",
        tags=["domain:software_engineering", "adversarial", "explicit_but_noisy"],
    )
    add(
        example_id="pp:fail:12",
        payload=_payload(
            "cand:fail:12",
            PromotionCandidateType.EPISODIC,
            "Task outcome: FYI user asked whether docs exist.",
            "task_outcome",
        ),
        expected_passed=False,
        score_min=0.0,
        score_max=0.0,
        failure_mode="noise",
        tags=["domain:customer_support", "adversarial", "high_value_but_noisy"],
    )

    # 10 ambiguous.
    add(
        example_id="pp:amb:01",
        payload=_payload("cand:amb:01", PromotionCandidateType.USER_MEMORY, "User often asks for concise tables.", "observation", repeat=3),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:personal_assistant", "inferred_repeated_preference"],
    )
    add(
        example_id="pp:amb:02",
        payload=_payload("cand:amb:02", PromotionCandidateType.PROJECT_FACT, "Deploy this sprint with a temporary feature flag for now.", "observation", repeat=4),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:product_project_planning", "time_bound_project_fact"],
    )
    add(
        example_id="pp:amb:03",
        payload=_payload(
            "cand:amb:03",
            PromotionCandidateType.SEMANTIC,
            "Auth retries cap at three attempts.",
            "observation",
            repeat=4,
            related=["mem:semantic:auth-retry-cap"],
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:software_engineering", "duplicate_prone_candidate"],
    )
    add(
        example_id="pp:amb:04",
        payload=_payload(
            "cand:amb:04",
            PromotionCandidateType.EPISODIC,
            "Need follow-up validation from logs.",
            "observation",
            metadata={"llm_followup_expected": True},
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:incident_debugging", "incomplete_evidence"],
    )
    add(
        example_id="pp:amb:05",
        payload=_payload("cand:amb:05", PromotionCandidateType.USER_MEMORY, "User often asks for short bullet updates.", "observation", repeat=5),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:customer_support", "inferred_repeated_preference"],
    )
    add(
        example_id="pp:amb:06",
        payload=_payload("cand:amb:06", PromotionCandidateType.PROJECT_FACT, "This trip requires daily check-ins for now.", "observation", repeat=3),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:product_project_planning", "temporary_planning"],
    )
    add(
        example_id="pp:amb:07",
        payload=_payload(
            "cand:amb:07",
            PromotionCandidateType.SEMANTIC,
            "Cache eviction runs every 60 minutes.",
            "observation",
            repeat=3,
            related=["mem:semantic:cache-eviction-60m"],
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:architecture_decisions", "duplicate_prone_candidate"],
    )
    add(
        example_id="pp:amb:08",
        payload=_payload(
            "cand:amb:08",
            PromotionCandidateType.EPISODIC,
            "Investigate flaky test timing next week.",
            "observation",
            metadata={"llm_followup_expected": True},
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:software_engineering", "temporary_planning"],
    )
    add(
        example_id="pp:amb:09",
        payload=_payload("cand:amb:09", PromotionCandidateType.USER_MEMORY, "Across interactions user appears to prefer terse updates.", "observation", repeat=3),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:research", "inferred_repeated_preference"],
    )
    add(
        example_id="pp:amb:10",
        payload=_payload("cand:amb:10", PromotionCandidateType.PROJECT_FACT, "Use temporary rollback policy this sprint.", "observation", repeat=3),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:architecture_decisions", "time_bound_project_fact"],
    )
    add(
        example_id="pp:amb:11",
        payload=_payload(
            "cand:amb:11",
            PromotionCandidateType.USER_MEMORY,
            "Please remember this sprint I prefer brief updates.",
            "observation",
            explicit=True,
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:product_project_planning", "adversarial", "explicit_but_temporary"],
    )
    add(
        example_id="pp:amb:12",
        payload=_payload(
            "cand:amb:12",
            PromotionCandidateType.EPISODIC,
            "Task outcome for now: keep workaround until next week.",
            "task_outcome",
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:incident_debugging", "adversarial", "high_value_but_temporary"],
    )
    add(
        example_id="pp:amb:13",
        payload=_payload(
            "cand:amb:13",
            PromotionCandidateType.PROJECT_FACT,
            "Use this trip's checklist template for now.",
            "observation",
            repeat=5,
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:product_project_planning", "adversarial", "time_scope_bound"],
    )
    add(
        example_id="pp:amb:14",
        payload=_payload(
            "cand:amb:14",
            PromotionCandidateType.USER_MEMORY,
            "Remember next week only: send verbose detail.",
            "observation",
            explicit=True,
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:personal_assistant", "adversarial", "explicit_but_time_bound"],
    )
    add(
        example_id="pp:amb:15",
        payload=_payload(
            "cand:amb:15",
            PromotionCandidateType.EPISODIC,
            "Investigation conclusion for now pending next week follow-up.",
            "investigation_conclusion",
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:research", "adversarial", "high_value_but_time_bound"],
    )
    add(
        example_id="pp:amb:16",
        payload=_payload(
            "cand:amb:16",
            PromotionCandidateType.EPISODIC,
            "Decision finalized for this sprint only.",
            "decision_finalized",
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:architecture_decisions", "adversarial", "decision_time_bound"],
    )
    add(
        example_id="pp:amb:17",
        payload=_payload(
            "cand:amb:17",
            PromotionCandidateType.USER_MEMORY,
            "Remember this trip preference permanently for now.",
            "observation",
            explicit=True,
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:personal_assistant", "adversarial", "scope_conflict"],
    )
    add(
        example_id="pp:amb:18",
        payload=_payload(
            "cand:amb:18",
            PromotionCandidateType.PROJECT_FACT,
            "Repeated rule: temporary routing override this sprint.",
            "observation",
            repeat=4,
        ),
        expected_passed=False,
        score_min=0.5,
        score_max=0.5,
        failure_mode="ambiguous_scope",
        tags=["domain:software_engineering", "adversarial", "repeated_but_temporary"],
    )

    return examples


def _payload(
    candidate_id: str,
    candidate_type: PromotionCandidateType,
    content: str,
    created_from: str,
    *,
    repeat: int = 0,
    explicit: bool = False,
    related: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type.value,
        "content": content,
        "source_ids": [f"src:{candidate_id}"],
        "related_memory_ids": related or [],
        "repeated_across_episodes": repeat,
        "explicit_user_memory_request": explicit,
        "created_from": created_from,
        "metadata": metadata or {},
    }
