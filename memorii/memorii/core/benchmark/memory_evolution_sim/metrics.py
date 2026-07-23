"""Simulator metric helpers over the typed checkpoint-row contract."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Protocol


class SimMetricRow(Protocol):
    """Structural view needed by simulator metrics.

    Keeping this protocol in the simulator package avoids a dependency from
    simulator semantics back into the artifact model module.
    """

    success: bool
    review_required: bool
    failure_buckets: list[str]
    selected_excluded_ids: dict[str, list[str]]
    supporting_excluded_ids: dict[str, list[str]]
    selected_noncurrent_claim_ids: list[str]
    selected_entity_role_mismatches: list[str]
    supporting_noisy_citation_event_ids: list[str]
    precision_failure_classification: list[str]


def sim_metrics_from_rows(rows: Sequence[SimMetricRow]) -> dict[str, float]:
    if not rows:
        return {}
    total = len(rows)
    passed = sum(row.success for row in rows)
    bucket_counts = Counter(bucket for row in rows for bucket in row.failure_buckets)
    return {
        "checkpoint_accuracy": passed / total,
        "judge_review_required_rate": sum(row.review_required for row in rows) / total,
        "hidden_hallucination_rate": bucket_counts["hidden_fact_hallucinated"] / total,
        "ambiguous_overcommit_rate": bucket_counts["ambiguous_fact_overcommitted"] / total,
        "selection_precision": sum(
            not row.selected_excluded_ids
            and not row.selected_noncurrent_claim_ids
            and not row.selected_entity_role_mismatches
            for row in rows
        )
        / total,
        "provenance_precision": sum(not row.supporting_noisy_citation_event_ids for row in rows) / total,
        "excluded_selection_rate": sum(bool(row.selected_excluded_ids or row.supporting_excluded_ids) for row in rows)
        / total,
        "noise_provenance_rate": sum(bool(row.supporting_noisy_citation_event_ids) for row in rows) / total,
        "precision_review_required_rate": sum(bool(row.precision_failure_classification) for row in rows) / total,
    }
