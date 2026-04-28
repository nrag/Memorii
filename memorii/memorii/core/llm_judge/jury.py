"""Jury aggregation for single-dimension judge verdicts."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.llm_judge.models import JudgeVerdict, JuryVerdict


class JuryAggregator:
    def aggregate(
        self,
        *,
        verdicts: list[JudgeVerdict],
        snapshot_id: str | None = None,
        trace_id: str | None = None,
    ) -> JuryVerdict:
        if not verdicts:
            return JuryVerdict(
                jury_id="jury:aggregate",
                snapshot_id=snapshot_id,
                trace_id=trace_id,
                verdicts=[],
                passed=False,
                aggregate_score=0.0,
                disagreement=False,
                needs_human_review=True,
                created_at=datetime.now(UTC),
            )

        aggregate_score = sum(verdict.score for verdict in verdicts) / len(verdicts)
        passed_values = [verdict.passed for verdict in verdicts]
        all_passed = all(passed_values)

        min_score = min(verdict.score for verdict in verdicts)
        max_score = max(verdict.score for verdict in verdicts)
        score_range = max_score - min_score
        pass_fail_disagreement = any(passed_values) and not all_passed
        disagreement = pass_fail_disagreement or score_range >= 0.4

        needs_human_review = disagreement or any(verdict.needs_human_review for verdict in verdicts)

        return JuryVerdict(
            jury_id="jury:aggregate",
            snapshot_id=snapshot_id,
            trace_id=trace_id,
            verdicts=verdicts,
            passed=all_passed,
            aggregate_score=aggregate_score,
            disagreement=disagreement,
            needs_human_review=needs_human_review,
            created_at=datetime.now(UTC),
        )
