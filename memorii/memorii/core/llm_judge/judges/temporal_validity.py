"""Temporal validity single-dimension judge and calibration fixtures."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Callable

from memorii.core.llm_judge.models import CalibrationExample, JudgeDimension, JudgeRubric, JudgeVerdict
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext

_TIME_BOUND_MARKERS = (
    "next week",
    "this week",
    "this sprint",
    "this trip",
    "for now",
    "temporary",
    "until launch",
    "during incident",
    "current workaround",
)

_EXPIRED_MARKERS = (
    "yesterday only",
    "last week only",
    "already obsolete",
    "no longer applies",
    "superseded",
)

_DURABLE_MARKERS = (
    "permanent preference",
    "always prefer",
    "durable",
    "finalized",
    "stable",
)


def temporal_validity_rubric() -> JudgeRubric:
    return JudgeRubric(
        judge_id="temporal_validity:v1",
        dimension=JudgeDimension.TEMPORAL_VALIDITY,
        name="Temporal Validity",
        description="Judge whether candidate memory is durable, time-bound, or clearly expired.",
        score_1_anchor="Clearly durable with no temporary or expiry scope.",
        score_0_5_anchor="Time-bound or temporally ambiguous and may need scoped storage.",
        score_0_anchor="Clearly temporary/expired and not durable as-is.",
        pass_threshold=0.7,
        failure_modes=[
            "temporary_scope",
            "expired_context",
            "time_bound_preference",
            "time_bound_project_fact",
            "ambiguous_temporal_scope",
        ],
    )


class TemporalValidityJudge:
    def __init__(self, *, rubric: JudgeRubric | None = None, created_at_factory: Callable[[], datetime] | None = None) -> None:
        self.rubric = rubric or temporal_validity_rubric()
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

        stable_key = {
            "judge_id": self.judge_id,
            "dimension": self.dimension.value,
            "snapshot_id": snapshot_id,
            "trace_id": trace_id,
            "input_payload": context.model_dump(mode="json"),
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
        candidate = input_payload.get("input_payload") if isinstance(input_payload.get("input_payload"), dict) else input_payload
        return PromotionContext.model_validate(candidate)

    def _score_context(self, *, context: PromotionContext) -> tuple[float, str, str | None]:
        content = context.content.lower()

        expired_hit = next((marker for marker in _EXPIRED_MARKERS if marker in content), None)
        if expired_hit:
            return 0.0, f"expired:{expired_hit}", "expired_context"

        time_bound_hit = next((marker for marker in _TIME_BOUND_MARKERS if marker in content), None)
        if time_bound_hit:
            if context.candidate_type == PromotionCandidateType.USER_MEMORY:
                return 0.5, f"time_bound_preference:{time_bound_hit}", "time_bound_preference"
            if context.candidate_type == PromotionCandidateType.PROJECT_FACT:
                return 0.5, f"time_bound_project_fact:{time_bound_hit}", "time_bound_project_fact"
            return 0.5, f"temporary_scope:{time_bound_hit}", "temporary_scope"

        if bool(context.metadata.get("temporal_ambiguous", False)):
            return 0.5, "ambiguous_temporal_scope", "ambiguous_temporal_scope"

        if context.explicit_user_memory_request and any(marker in content for marker in _DURABLE_MARKERS):
            return 1.0, "explicit_permanent_preference", None

        if context.created_from in {"decision_finalized", "investigation_conclusion"}:
            return 1.0, "finalized_without_time_scope", None

        if context.repeated_across_episodes >= 3 and context.candidate_type in {
            PromotionCandidateType.SEMANTIC,
            PromotionCandidateType.PROJECT_FACT,
        }:
            return 1.0, "stable_repeated_fact", None

        return 0.5, "ambiguous_temporal_scope", "ambiguous_temporal_scope"


def temporal_validity_calibration_v1() -> list[CalibrationExample]:
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
                dimension=JudgeDimension.TEMPORAL_VALIDITY,
                input_payload=payload,
                expected_passed=expected_passed,
                expected_score_min=score_min,
                expected_score_max=score_max,
                expected_failure_mode=failure_mode,
                tags=tags,
            )
        )

    durable_rows = [
        ("01", PromotionCandidateType.USER_MEMORY, "Remember this permanent preference: always concise responses.", "observation", ["domain:personal_assistant"]),
        ("02", PromotionCandidateType.PROJECT_FACT, "Finalized architecture decision to standardize retry middleware.", "decision_finalized", ["domain:architecture_decisions"]),
        ("03", PromotionCandidateType.SEMANTIC, "OAuth callback validation requires signed state token.", "observation", ["domain:software_engineering"]),
        ("04", PromotionCandidateType.EPISODIC, "Investigation conclusion: cache invalidation race caused stale dashboard.", "investigation_conclusion", ["domain:incident_debugging"]),
        ("05", PromotionCandidateType.PROJECT_FACT, "Customer ACME requires SSO enforcement for all seats.", "observation", ["domain:customer_support"]),
        ("06", PromotionCandidateType.SEMANTIC, "Runbook states incident severity paging thresholds by error budget.", "observation", ["domain:incident_debugging"]),
        ("07", PromotionCandidateType.PROJECT_FACT, "Roadmap depends on legal review before public launch.", "observation", ["domain:product_project_planning"]),
        ("08", PromotionCandidateType.SEMANTIC, "Benchmark harness normalizes fixture ordering deterministically.", "observation", ["domain:research"]),
        ("09", PromotionCandidateType.EPISODIC, "Completed migration outcome captured and verified by tests.", "task_outcome", ["domain:software_engineering"]),
        ("10", PromotionCandidateType.PROJECT_FACT, "Support escalation policy includes 24h enterprise response target.", "observation", ["domain:customer_support"]),
    ]
    for idx, ctype, content, created_from, tags in durable_rows:
        add(
            example_id=f"tv:pass:{idx}",
            payload=_payload(f"tv:cand:{idx}", ctype, content, created_from, repeat=4),
            expected_passed=True,
            score_min=1.0,
            score_max=1.0,
            failure_mode=None,
            tags=tags,
        )

    temp_rows = [
        ("11", PromotionCandidateType.PROJECT_FACT, "Use this workaround for now until launch.", "observation", "time_bound_project_fact", ["domain:product_project_planning"]),
        ("12", PromotionCandidateType.USER_MEMORY, "For this trip prefer SMS updates.", "observation", "time_bound_preference", ["domain:personal_assistant"]),
        ("13", PromotionCandidateType.EPISODIC, "During incident use current workaround and skip cache warmup.", "observation", "temporary_scope", ["domain:incident_debugging"]),
        ("14", PromotionCandidateType.PROJECT_FACT, "This sprint use manual approval path.", "observation", "time_bound_project_fact", ["domain:software_engineering"]),
        ("15", PromotionCandidateType.SEMANTIC, "Temporary schema patch next week for ingestion job.", "observation", "temporary_scope", ["domain:research"]),
        ("16", PromotionCandidateType.PROJECT_FACT, "For now keep support replies in macro-only mode.", "observation", "time_bound_project_fact", ["domain:customer_support"]),
        ("17", PromotionCandidateType.USER_MEMORY, "This week only, remind me at 8am.", "observation", "time_bound_preference", ["domain:personal_assistant"]),
        ("18", PromotionCandidateType.EPISODIC, "During incident rotate logs every hour.", "observation", "temporary_scope", ["domain:incident_debugging"]),
        ("19", PromotionCandidateType.PROJECT_FACT, "This trip customer asks for daily sync notes.", "observation", "time_bound_project_fact", ["domain:customer_support"]),
        ("20", PromotionCandidateType.SEMANTIC, "Current workaround applies this week.", "observation", "temporary_scope", ["domain:software_engineering"]),
    ]
    for idx, ctype, content, created_from, mode, tags in temp_rows:
        add(
            example_id=f"tv:amb:{idx}",
            payload=_payload(f"tv:cand:{idx}", ctype, content, created_from, repeat=2),
            expected_passed=False,
            score_min=0.5,
            score_max=0.5,
            failure_mode=mode,
            tags=tags,
        )

    expired_rows = [
        ("21", "This config was yesterday only and no longer applies.", "expired_context", ["domain:software_engineering"]),
        ("22", "Last week only workaround already obsolete.", "expired_context", ["domain:incident_debugging"]),
        ("23", "Deployment note was superseded by patch v2.", "expired_context", ["domain:product_project_planning"]),
        ("24", "Customer exception no longer applies after contract update.", "expired_context", ["domain:customer_support"]),
        ("25", "User reminder rule yesterday only.", "expired_context", ["domain:personal_assistant"]),
        ("26", "Research conclusion superseded by replicated experiment.", "expired_context", ["domain:research"]),
        ("27", "Old pager channel already obsolete and no longer applies.", "expired_context", ["domain:incident_debugging"]),
        ("28", "Temporary test toggle last week only.", "expired_context", ["domain:software_engineering"]),
        ("29", "Needs temporal review", "ambiguous_temporal_scope", ["domain:architecture_decisions"]),
        ("30", "Possibly still valid but unclear timing", "ambiguous_temporal_scope", ["domain:project_planning"]),
    ]
    for idx, content, mode, tags in expired_rows:
        add(
            example_id=f"tv:fail:{idx}",
            payload=_payload(
                f"tv:cand:{idx}",
                PromotionCandidateType.PROJECT_FACT,
                content,
                "observation",
                metadata={"temporal_ambiguous": mode == "ambiguous_temporal_scope"},
            ),
            expected_passed=False,
            score_min=0.5 if mode == "ambiguous_temporal_scope" else 0.0,
            score_max=0.5 if mode == "ambiguous_temporal_scope" else 0.0,
            failure_mode=mode,
            tags=tags,
        )

    return examples


def _payload(
    candidate_id: str,
    candidate_type: PromotionCandidateType,
    content: str,
    created_from: str,
    *,
    repeat: int = 0,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type.value,
        "content": content,
        "source_ids": ["src:test"],
        "related_memory_ids": [],
        "repeated_across_episodes": repeat,
        "explicit_user_memory_request": "remember" in content.lower(),
        "created_from": created_from,
        "metadata": metadata or {},
    }
