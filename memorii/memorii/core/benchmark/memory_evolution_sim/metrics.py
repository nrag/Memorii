"""Simulator metric helpers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence


def _json_sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _row_value(row: dict[str, object], key: str, default: object = None) -> object:
    if key in row:
        return row[key]
    diagnostics = row.get("diagnostics")
    if isinstance(diagnostics, dict):
        return diagnostics.get(key, default)
    return default


def sim_metrics_from_rows(rows: list[dict[str, object]]) -> dict[str, float]:
    if not rows:
        return {}
    total = len(rows)
    passed = sum(1 for row in rows if row.get("success") is True)
    bucket_counts = Counter(
        bucket
        for row in rows
        for bucket in _json_sequence(row.get("failure_buckets"))
    )
    return {
        "checkpoint_accuracy": passed / total,
        "judge_review_required_rate": sum(1 for row in rows if row.get("review_required")) / total,
        "hidden_hallucination_rate": bucket_counts["hidden_fact_hallucinated"] / total,
        "ambiguous_overcommit_rate": bucket_counts["ambiguous_fact_overcommitted"] / total,
        "selection_precision": sum(
            1
            for row in rows
            if not _row_value(row, "selected_excluded_ids")
            and not _row_value(row, "selected_noncurrent_claim_ids")
            and not _row_value(row, "selected_entity_role_mismatches")
        )
        / total,
        "provenance_precision": sum(1 for row in rows if not _row_value(row, "supporting_noisy_citation_event_ids")) / total,
        "excluded_selection_rate": sum(1 for row in rows if _row_value(row, "selected_excluded_ids") or _row_value(row, "supporting_excluded_ids")) / total,
        "noise_provenance_rate": sum(1 for row in rows if _row_value(row, "supporting_noisy_citation_event_ids")) / total,
        "precision_review_required_rate": sum(1 for row in rows if _row_value(row, "precision_failure_classification")) / total,
    }
