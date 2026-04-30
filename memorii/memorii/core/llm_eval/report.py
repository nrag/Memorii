"""Plain-text report helper for offline LLM eval runs."""

from __future__ import annotations

from memorii.core.llm_eval.models import EvalRunReport


def summarize_eval_report(report: EvalRunReport) -> str:
    lines: list[str] = []
    lines.append(f"run_id: {report.run_id}")
    lines.append(f"total: {report.total_cases}")
    lines.append(f"passed: {report.passed_cases}")
    lines.append(f"failed: {report.failed_cases}")
    lines.append(f"average_score: {report.average_score:.4f}")
    lines.append("pass_rate_by_decision_point:")

    for decision_point in sorted(report.pass_rate_by_decision_point):
        pass_rate = report.pass_rate_by_decision_point[decision_point]
        lines.append(f"  - {decision_point}: {pass_rate:.4f}")

    requires_review_ids = [result.snapshot_id for result in report.results if result.requires_judge_review]
    lines.append(f"requires_judge_review_cases: {len(requires_review_ids)}")
    if requires_review_ids:
        lines.append(f"requires_judge_review_snapshot_ids: {','.join(requires_review_ids)}")

    fallback_ids = [result.snapshot_id for result in report.results if result.fallback_used]
    disagreement_ids = [result.snapshot_id for result in report.results if result.disagreement]
    lines.append(f"fallback_cases: {len(fallback_ids)}")
    if fallback_ids:
        lines.append(f"fallback_snapshot_ids: {','.join(fallback_ids)}")
    lines.append(f"disagreement_cases: {len(disagreement_ids)}")
    if disagreement_ids:
        lines.append(f"disagreement_snapshot_ids: {','.join(disagreement_ids)}")

    failed_ids = [result.snapshot_id for result in report.results if not result.passed]
    lines.append(f"failed_snapshot_ids: {','.join(failed_ids) if failed_ids else '(none)'}")
    return "\n".join(lines)
