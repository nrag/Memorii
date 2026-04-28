"""Attribution single-dimension judge and calibration fixtures."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Callable

from memorii.core.llm_judge.models import CalibrationExample, JudgeDimension, JudgeRubric, JudgeVerdict

_HIGH_RISK_HINTS = ("confirmed", "always", "must", "root cause", "final")


def attribution_rubric() -> JudgeRubric:
    return JudgeRubric(
        judge_id="attribution:v1",
        dimension=JudgeDimension.ATTRIBUTION,
        name="Attribution",
        description="Judge whether claim attribution/source ownership is correct.",
        score_1_anchor="Attribution is explicit, clear, and aligned to the asserted source.",
        score_0_5_anchor="Source metadata exists but authority is ambiguous.",
        score_0_anchor="Claim is misattributed or high-risk assertion lacks attribution.",
        pass_threshold=0.7,
        failure_modes=[
            "missing_attribution",
            "agent_claim_as_user_claim",
            "verifier_hypothesis_as_fact",
            "external_source_as_user_memory",
            "ambiguous_source",
        ],
    )


class AttributionJudge:
    def __init__(self, *, rubric: JudgeRubric | None = None, created_at_factory: Callable[[], datetime] | None = None) -> None:
        self.rubric = rubric or attribution_rubric()
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
            "input_payload": context,
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

    def _extract_context(self, *, input_payload: dict[str, object]) -> dict[str, object]:
        if isinstance(input_payload.get("input_payload"), dict):
            return dict(input_payload["input_payload"])
        if isinstance(input_payload.get("context"), dict):
            return dict(input_payload["context"])
        return dict(input_payload)

    def _score_context(self, *, context: dict[str, object]) -> tuple[float, str, str | None]:
        metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
        source_actor = str(context.get("source_actor") or metadata.get("source_actor") or "").lower()
        source_kind = str(context.get("source_kind") or metadata.get("source_kind") or "").lower()
        asserted_by = str(context.get("asserted_by") or metadata.get("asserted_by") or "").lower()
        evidence_source = str(context.get("evidence_source") or metadata.get("evidence_source") or "").lower()
        candidate_type = str(context.get("candidate_type") or "").lower()
        content = str(context.get("content") or "").lower()

        attribution_fields = [
            source_actor,
            source_kind,
            asserted_by,
            evidence_source,
            str(metadata.get("agent_id") or ""),
            str(metadata.get("user_id") or ""),
            str(metadata.get("verifier_id") or ""),
        ]

        high_risk = any(token in content for token in _HIGH_RISK_HINTS) or candidate_type in {"project_fact", "semantic"}

        if candidate_type == "user_memory" and source_actor == "agent":
            return 0.0, "agent_claim_as_user_claim", "agent_claim_as_user_claim"

        if source_actor == "verifier" and bool(metadata.get("is_hypothesis_promoted", False)):
            return 0.0, "verifier_hypothesis_as_fact", "verifier_hypothesis_as_fact"

        if candidate_type == "user_memory" and source_kind in {"external", "web", "document"}:
            return 0.0, "external_source_as_user_memory", "external_source_as_user_memory"

        if high_risk and not any(field.strip() for field in attribution_fields):
            return 0.0, "missing_attribution", "missing_attribution"

        if source_actor == "user" and candidate_type == "user_memory" and asserted_by in {"user", ""}:
            return 1.0, "explicit_user_claim", None
        if source_kind == "tool" and source_actor == "tool":
            return 1.0, "tool_observation_attributed", None
        if source_actor == "verifier" and asserted_by == "verifier":
            return 1.0, "verifier_downgrade_attributed", None
        if source_actor == "agent" and source_kind == "agent" and candidate_type in {"episodic", "project_fact"}:
            return 1.0, "agent_plan_attributed", None

        if source_kind and not asserted_by:
            return 0.5, "source_kind_without_asserted_by", "ambiguous_source"
        if source_actor in {"agent", "user", "tool", "verifier"} and asserted_by in {"agent", "user", "tool", "verifier"}:
            return 0.5, "multi_actor_chain_ambiguous", "ambiguous_source"

        return 0.5, "generic_source_only", "ambiguous_source"


def attribution_calibration_v1() -> list[CalibrationExample]:
    examples: list[CalibrationExample] = []

    def add(
        *,
        eid: str,
        payload: dict[str, object],
        passed: bool,
        score: float,
        failure_mode: str | None,
        tags: list[str],
    ) -> None:
        examples.append(
            CalibrationExample(
                example_id=eid,
                dimension=JudgeDimension.ATTRIBUTION,
                input_payload=payload,
                expected_passed=passed,
                expected_score_min=score,
                expected_score_max=score,
                expected_failure_mode=failure_mode,
                tags=tags,
            )
        )

    for idx in range(1, 11):
        add(
            eid=f"attr:pass:{idx:02d}",
            payload={
                "candidate_type": "user_memory" if idx <= 3 else "project_fact",
                "content": f"case {idx}",
                "source_actor": "user" if idx <= 3 else ("tool" if idx <= 6 else "verifier" if idx <= 8 else "agent"),
                "source_kind": "message" if idx <= 3 else ("tool" if idx <= 6 else "verifier" if idx <= 8 else "agent"),
                "asserted_by": "user" if idx <= 3 else ("tool" if idx <= 6 else "verifier" if idx <= 8 else "agent"),
                "metadata": {"user_id": "u1", "agent_id": "a1"},
            },
            passed=True,
            score=1.0,
            failure_mode=None,
            tags=[
                "domain:personal_assistant" if idx <= 3 else "domain:software_engineering",
                "hermes:multi_agent" if idx in {7, 8} else "domain:customer_support",
            ],
        )

    fail_cases = [
        ("01", "user_memory", "agent", "agent_claim_as_user_claim", "domain:personal_assistant"),
        ("02", "user_memory", "agent", "agent_claim_as_user_claim", "domain:customer_support"),
        ("03", "project_fact", "", "missing_attribution", "domain:incident_debugging"),
        ("04", "project_fact", "", "missing_attribution", "domain:research"),
        ("05", "user_memory", "", "external_source_as_user_memory", "domain:personal_assistant"),
        ("06", "user_memory", "", "external_source_as_user_memory", "domain:customer_support"),
        ("07", "project_fact", "verifier", "verifier_hypothesis_as_fact", "domain:incident_debugging"),
        ("08", "project_fact", "verifier", "verifier_hypothesis_as_fact", "domain:software_engineering"),
        ("09", "semantic", "", "missing_attribution", "domain:architecture_decisions"),
        ("10", "project_fact", "", "missing_attribution", "domain:product_project_planning"),
    ]
    for idx, ctype, actor, mode, domain in fail_cases:
        add(
            eid=f"attr:fail:{idx}",
            payload={
                "candidate_type": ctype,
                "content": "final root cause confirmed",
                "source_actor": actor,
                "source_kind": "external" if mode == "external_source_as_user_memory" else "",
                "asserted_by": "",
                "metadata": {"is_hypothesis_promoted": mode == "verifier_hypothesis_as_fact"},
            },
            passed=False,
            score=0.0,
            failure_mode=mode,
            tags=[domain, "hermes:attribution"],
        )

    for idx in range(1, 11):
        add(
            eid=f"attr:amb:{idx:02d}",
            payload={
                "candidate_type": "project_fact",
                "content": "status update",
                "source_actor": "agent" if idx % 2 == 0 else "user",
                "source_kind": "tool" if idx % 3 == 0 else "message",
                "asserted_by": "" if idx <= 6 else "agent",
                "metadata": {"agent_id": "a1"},
            },
            passed=False,
            score=0.5,
            failure_mode="ambiguous_source",
            tags=["domain:software_engineering", "hermes:multi_agent"],
        )

    return examples
