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

    pass_cases = [
        ("attr:pass:01", "user_memory", "Remember I prefer concise release notes.", "user", "message", "user", ["domain:personal_assistant"]),
        ("attr:pass:02", "user_memory", "Please remember my timezone is Pacific.", "user", "message", "user", ["domain:personal_assistant"]),
        ("attr:pass:03", "project_fact", "Tool output: incident ticket INC-431 is resolved.", "tool", "tool", "tool", ["domain:incident_debugging"]),
        ("attr:pass:04", "project_fact", "Tool observed latency dropped under SLO for 24h.", "tool", "tool", "tool", ["domain:incident_debugging"]),
        ("attr:pass:05", "project_fact", "Verifier downgraded claim due to missing log shard.", "verifier", "verifier", "verifier", ["domain:research", "hermes:multi_agent"]),
        ("attr:pass:06", "project_fact", "Verifier marked hypothesis unproven after replay.", "verifier", "verifier", "verifier", ["domain:software_engineering", "hermes:multi_agent"]),
        ("attr:pass:07", "project_fact", "Agent planned migration rollback checklist.", "agent", "agent", "agent", ["domain:project_planning"]),
        ("attr:pass:08", "episodic", "Agent completed customer escalation timeline.", "agent", "agent", "agent", ["domain:customer_support"]),
        ("attr:pass:09", "project_fact", "Tool emitted billing export checksum mismatch.", "tool", "tool", "tool", ["domain:customer_support"]),
        ("attr:pass:10", "project_fact", "Tool detected schema drift in nightly ETL.", "tool", "tool", "tool", ["domain:research"]),
    ]
    for eid, ctype, content, actor, skind, asserted, tags in pass_cases:
        add(
            eid=eid,
            payload={
                "candidate_type": ctype,
                "content": content,
                "source_actor": actor,
                "source_kind": skind,
                "asserted_by": asserted,
                "metadata": {"agent_id": "agent:planner", "user_id": "user:1"},
            },
            passed=True,
            score=1.0,
            failure_mode=None,
            tags=tags,
        )

    fail_cases = [
        ("attr:fail:01", "user_memory", "Agent says user always wants terse mode.", "agent", "agent", "", "agent_claim_as_user_claim", ["domain:personal_assistant"]),
        ("attr:fail:02", "user_memory", "Assistant inferred user prefers markdown tables.", "agent", "agent", "", "agent_claim_as_user_claim", ["domain:customer_support"]),
        ("attr:fail:03", "project_fact", "Root cause confirmed.", "", "", "", "missing_attribution", ["domain:incident_debugging"]),
        ("attr:fail:04", "semantic", "Final architecture rule is now mandatory.", "", "", "", "missing_attribution", ["domain:architecture_decisions"]),
        ("attr:fail:05", "user_memory", "External blog says user must receive JSON.", "", "external", "", "external_source_as_user_memory", ["domain:personal_assistant"]),
        ("attr:fail:06", "user_memory", "Vendor document claims user likes long answers.", "", "document", "", "external_source_as_user_memory", ["domain:customer_support"]),
        ("attr:fail:07", "project_fact", "Verifier hypothesis treated as final root cause.", "verifier", "verifier", "", "verifier_hypothesis_as_fact", ["domain:incident_debugging", "hermes:multi_agent"]),
        ("attr:fail:08", "project_fact", "Verifier guess persisted as confirmed conclusion.", "verifier", "verifier", "", "verifier_hypothesis_as_fact", ["domain:software_engineering", "hermes:multi_agent"]),
        ("attr:fail:09", "project_fact", "Customer contract requirement confirmed.", "", "", "", "missing_attribution", ["domain:customer_support"]),
        ("attr:fail:10", "semantic", "Always retry webhook three times.", "", "", "", "missing_attribution", ["domain:research"]),
    ]
    for eid, ctype, content, actor, skind, asserted, failure_mode, tags in fail_cases:
        add(
            eid=eid,
            payload={
                "candidate_type": ctype,
                "content": content,
                "source_actor": actor,
                "source_kind": skind,
                "asserted_by": asserted,
                "metadata": {"is_hypothesis_promoted": failure_mode == "verifier_hypothesis_as_fact"},
            },
            passed=False,
            score=0.0,
            failure_mode=failure_mode,
            tags=tags,
        )

    ambiguous_cases = [
        ("attr:amb:01", "project_fact", "Router team says patch might be enough.", "agent", "message", "user"),
        ("attr:amb:02", "project_fact", "Support lead relayed tool result verbally.", "user", "tool", ""),
        ("attr:amb:03", "project_fact", "Another agent requested temporary policy update.", "agent", "agent", "user"),
        ("attr:amb:04", "project_fact", "Tool finding cited in handoff without owner.", "agent", "tool", ""),
        ("attr:amb:05", "project_fact", "Verifier note copied by planner.", "agent", "verifier", "agent"),
        ("attr:amb:06", "project_fact", "Runtime worker reported flake, source unclear.", "user", "message", ""),
        ("attr:amb:07", "project_fact", "Escalation summary came from multi-agent thread.", "agent", "message", "agent"),
        ("attr:amb:08", "project_fact", "Partner shared dashboard observation through CSM.", "user", "external", ""),
        ("attr:amb:09", "project_fact", "Tool observation was paraphrased by reviewer.", "user", "tool", "user"),
        ("attr:amb:10", "project_fact", "Unclear who confirmed rollout readiness.", "agent", "message", ""),
    ]
    for eid, ctype, content, actor, skind, asserted in ambiguous_cases:
        add(
            eid=eid,
            payload={
                "candidate_type": ctype,
                "content": content,
                "source_actor": actor,
                "source_kind": skind,
                "asserted_by": asserted,
                "metadata": {"agent_id": "agent:hermes-sub", "user_id": "user:1"},
            },
            passed=False,
            score=0.5,
            failure_mode="ambiguous_source",
            tags=["domain:software_engineering", "hermes:multi_agent"],
        )

    return examples
