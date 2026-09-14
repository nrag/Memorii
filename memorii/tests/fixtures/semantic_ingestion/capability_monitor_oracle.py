"""Independent standard-library oracle for the frozen monitor confidence vector."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path


def main() -> int:
    fixture = json.loads(Path(sys.argv[1]).read_text(encoding="ascii"))
    now = datetime.fromisoformat(fixture["server_time"])
    label_at = datetime.fromisoformat(fixture["latest_independent_label_at"])
    canary_at = datetime.fromisoformat(fixture["latest_canary_success_at"])
    observations = tuple(fixture["observations"])
    if len({item["event_id"] for item in observations}) != len(observations):
        raise ValueError("duplicate event")
    if len({item["cluster_id"] for item in observations}) != len(observations):
        raise ValueError("duplicate cluster")
    selected = tuple(
        item
        for item in observations
        if item["metric_id"] == fixture["metric_id"]
        and timedelta(0)
        <= label_at - datetime.fromisoformat(item["observed_at"])
        <= timedelta(seconds=fixture["maximum_label_delay_seconds"])
    )
    values = tuple(Decimal(item["value"]) for item in selected)
    lower = Decimal(fixture["bounded_value_lower"])
    upper = Decimal(fixture["bounded_value_upper"])
    alpha = Decimal(fixture["alpha_budget"])
    with localcontext() as context:
        context.prec = 50
        count = Decimal(len(values))
        estimate = sum(values, Decimal(0)) / count
        allocated = alpha / (count * (count + 1))
        radius = (-(allocated / Decimal(2)).ln() / (Decimal(2) * count)).sqrt()
        upper_bound = min(upper, estimate + radius)
        lower_bound = max(lower, estimate - radius)
        metric_status = (
            "breach"
            if upper_bound >= Decimal(fixture["breach_threshold"])
            else "warning"
            if upper_bound >= Decimal(fixture["warning_threshold"])
            else "healthy"
        )
        labels_fresh = now - label_at < timedelta(
            seconds=fixture["maximum_label_age_seconds"]
        )
        canary_fresh = now - canary_at < timedelta(
            seconds=fixture["maximum_canary_age_seconds"]
        )
        freshness = (
            "fresh"
            if labels_fresh
            and canary_fresh
            and len(observations) >= fixture["minimum_labeled_clusters_per_window"]
            else "stale"
        )
        reasons = []
        if freshness == "stale":
            reasons.append("stale_evidence")
        if len(selected) < fixture["minimum_independent_clusters"]:
            reasons.append("insufficient_metric_evidence")
        if fixture["implementation_fingerprint"] != fixture["expected_implementation_fingerprint"]:
            reasons.append("insufficient_metric_evidence")
        if metric_status == "breach":
            reasons.append("metric_breach")
        result = {
            "eligible_event_ids": [item["event_id"] for item in selected],
            "freshness": freshness,
            "freshness_reason": "fresh" if freshness == "fresh" else "independent_labels_stale_or_insufficient",
            "labeled_cluster_count": len(observations),
            "metric_id": fixture["metric_id"],
            "independent_cluster_count": len(selected),
            "estimate": str(estimate.normalize()),
            "lower_bound": str(lower_bound.normalize()),
            "upper_bound": str(upper_bound.normalize()),
            "alpha_spent": fixture["alpha_budget"],
            "metric_status": metric_status,
            "action": "evidence_only" if reasons else "remain_active",
            "reason_codes": sorted(set(reasons)),
        }
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
