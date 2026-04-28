"""Offline runner for Wave 1 judges over deterministic eval results."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict

from memorii.core.llm_decision.models import EvalSnapshot
from memorii.core.llm_eval.models import EvalCaseResult, EvalRunReport
from memorii.core.llm_judge.calibration import (
    build_golden_candidate_reason_from_jury,
    should_promote_to_golden_candidate_from_jury,
)
from memorii.core.llm_judge.judge import SingleDimensionJudge, validate_single_dimension_judge
from memorii.core.llm_judge.judges import (
    AttributionJudge,
    BeliefDirectionJudge,
    MemoryPlaneJudge,
    PromotionPrecisionJudge,
    TemporalValidityJudge,
)
from memorii.core.llm_judge.jury import JuryAggregator
from memorii.core.llm_judge.models import JudgeVerdict, JuryVerdict

_ATTRIBUTION_FIELDS = {
    "source_actor",
    "source_kind",
    "asserted_by",
    "evidence_source",
    "agent_id",
    "user_id",
    "verifier_id",
}


class JudgeRunCaseResult(BaseModel):
    eval_snapshot_id: str
    decision_point: str
    eval_passed: bool
    eval_requires_judge_review: bool
    judge_verdicts: list[JudgeVerdict]
    jury_verdict: JuryVerdict
    golden_candidate_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class JudgeRunReport(BaseModel):
    run_id: str
    total_eval_cases: int
    judged_cases: int
    skipped_cases: int
    jury_passed_cases: int
    jury_failed_cases: int
    disagreement_cases: int
    human_review_cases: int
    golden_candidate_cases: int
    case_results: list[JudgeRunCaseResult]

    model_config = ConfigDict(extra="forbid")


class OfflineJudgeRunner:
    def __init__(
        self,
        *,
        promotion_judges: list[SingleDimensionJudge] | None = None,
        belief_judges: list[SingleDimensionJudge] | None = None,
        jury_aggregator: JuryAggregator | None = None,
        judge_all_cases: bool = False,
    ) -> None:
        self._promotion_judges = promotion_judges or [
            PromotionPrecisionJudge(),
            TemporalValidityJudge(),
            AttributionJudge(),
            MemoryPlaneJudge(),
        ]
        self._belief_judges = belief_judges or [
            AttributionJudge(),
            BeliefDirectionJudge(),
        ]
        for judge in [*self._promotion_judges, *self._belief_judges]:
            validate_single_dimension_judge(judge)

        self._jury_aggregator = jury_aggregator or JuryAggregator()
        self._judge_all_cases = judge_all_cases

    def run_eval_report(self, report: EvalRunReport, snapshots_by_id: dict[str, EvalSnapshot]) -> JudgeRunReport:
        return self.run_cases(cases=report.results, snapshots_by_id=snapshots_by_id)

    def run_cases(self, cases: list[EvalCaseResult], snapshots_by_id: dict[str, EvalSnapshot]) -> JudgeRunReport:
        skipped_cases = 0
        jury_passed_cases = 0
        jury_failed_cases = 0
        disagreement_cases = 0
        human_review_cases = 0
        golden_candidate_cases = 0
        case_results: list[JudgeRunCaseResult] = []

        for case in cases:
            if self._should_skip_case(case):
                skipped_cases += 1
                continue

            snapshot = snapshots_by_id.get(case.snapshot_id)
            judges = self._judges_for_case(case=case, snapshot=snapshot)
            if judges is None:
                skipped_cases += 1
                continue

            if snapshot is None:
                case_result = self._build_human_review_case_result(case=case, reason="missing_snapshot")
            else:
                case_result = self._run_judges_for_case(case=case, snapshot=snapshot, judges=judges)

            if case_result.jury_verdict.passed:
                jury_passed_cases += 1
            else:
                jury_failed_cases += 1
            if case_result.jury_verdict.disagreement:
                disagreement_cases += 1
            if case_result.jury_verdict.needs_human_review:
                human_review_cases += 1
            if case_result.golden_candidate_reason is not None:
                golden_candidate_cases += 1

            case_results.append(case_result)

        run_id = self._build_run_id(cases)

        return JudgeRunReport(
            run_id=run_id,
            total_eval_cases=len(cases),
            judged_cases=len(case_results),
            skipped_cases=skipped_cases,
            jury_passed_cases=jury_passed_cases,
            jury_failed_cases=jury_failed_cases,
            disagreement_cases=disagreement_cases,
            human_review_cases=human_review_cases,
            golden_candidate_cases=golden_candidate_cases,
            case_results=case_results,
        )

    def _should_skip_case(self, case: EvalCaseResult) -> bool:
        return not self._judge_all_cases and case.passed and not case.requires_judge_review

    def _build_human_review_case_result(self, *, case: EvalCaseResult, reason: str) -> JudgeRunCaseResult:
        jury = self._jury_aggregator.aggregate(
            verdicts=[],
            snapshot_id=case.snapshot_id,
            trace_id=case.trace_id,
        )
        return JudgeRunCaseResult(
            eval_snapshot_id=case.snapshot_id,
            decision_point=case.decision_point,
            eval_passed=case.passed,
            eval_requires_judge_review=case.requires_judge_review,
            judge_verdicts=[],
            jury_verdict=jury,
            golden_candidate_reason=reason,
        )

    def _run_judges_for_case(
        self,
        *,
        case: EvalCaseResult,
        snapshot: EvalSnapshot,
        judges: list[SingleDimensionJudge],
    ) -> JudgeRunCaseResult:
        judge_input_payload = {
            "input_payload": snapshot.input_payload,
            "expected_output": snapshot.expected_output,
            "actual_output": case.actual_output,
        }

        try:
            verdicts = [
                judge.judge(
                    input_payload=judge_input_payload,
                    snapshot_id=case.snapshot_id,
                    trace_id=case.trace_id,
                )
                for judge in judges
            ]
            jury = self._jury_aggregator.aggregate(
                verdicts=verdicts,
                snapshot_id=case.snapshot_id,
                trace_id=case.trace_id,
            )
            reason = None
            if should_promote_to_golden_candidate_from_jury(jury):
                reason = build_golden_candidate_reason_from_jury(jury)

            return JudgeRunCaseResult(
                eval_snapshot_id=case.snapshot_id,
                decision_point=case.decision_point,
                eval_passed=case.passed,
                eval_requires_judge_review=case.requires_judge_review,
                judge_verdicts=verdicts,
                jury_verdict=jury,
                golden_candidate_reason=reason,
            )
        except Exception:
            return self._build_human_review_case_result(case=case, reason="judge_execution_error")

    def _judges_for_case(
        self,
        *,
        case: EvalCaseResult,
        snapshot: EvalSnapshot | None,
    ) -> list[SingleDimensionJudge] | None:
        if case.decision_point == "promotion":
            return self._promotion_judges

        if case.decision_point == "belief_update":
            belief_judges: list[SingleDimensionJudge] = []
            has_attribution = self._has_attribution_fields(snapshot.input_payload) if snapshot is not None else False
            for judge in self._belief_judges:
                if judge.judge_id == "attribution:v1" and not has_attribution:
                    continue
                belief_judges.append(judge)
            return belief_judges

        return None

    def _has_attribution_fields(self, payload: dict[str, object]) -> bool:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        metadata_values = [str(metadata.get(field) or "").strip() for field in _ATTRIBUTION_FIELDS]
        direct_values = [str(payload.get(field) or "").strip() for field in _ATTRIBUTION_FIELDS]
        return any(metadata_values + direct_values)

    def _build_run_id(self, cases: list[EvalCaseResult]) -> str:
        judge_ids = sorted(
            {
                *(judge.judge_id for judge in self._promotion_judges),
                *(judge.judge_id for judge in self._belief_judges),
            }
        )
        case_fingerprints = [
            {
                "snapshot_id": case.snapshot_id,
                "decision_point": case.decision_point,
                "passed": case.passed,
                "requires_judge_review": case.requires_judge_review,
                "actual_output": case.actual_output,
                "trace_id": case.trace_id,
            }
            for case in cases
        ]
        case_fingerprints.sort(key=lambda value: json.dumps(value, sort_keys=True))
        run_id_key = {
            "cases": case_fingerprints,
            "judge_ids": judge_ids,
            "judge_all_cases": self._judge_all_cases,
        }
        run_id_digest = hashlib.sha256(json.dumps(run_id_key, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        return f"judge-run:{run_id_digest}"


def attach_judge_refs_to_eval_cases(
    cases: list[EvalCaseResult],
    judge_report: JudgeRunReport,
) -> list[EvalCaseResult]:
    verdict_ids_by_case_key = {
        (case_result.eval_snapshot_id, case_result.jury_verdict.trace_id): [
            verdict.verdict_id for verdict in case_result.judge_verdicts
        ]
        for case_result in judge_report.case_results
    }

    return [
        case.model_copy(
            update={
                "judge_verdict_refs": verdict_ids_by_case_key.get(
                    (case.snapshot_id, case.trace_id),
                    [],
                )
            }
        )
        for case in cases
    ]
