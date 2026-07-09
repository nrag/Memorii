"""Runtime benchmark artifact and report summary helpers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeSuiteRows


def write_runtime_artifacts(*, run_dir: Path, rows: RuntimeSuiteRows) -> None:
    _write_jsonl(run_dir / "runtime_graph_items.jsonl", rows.graph_items)
    _write_jsonl(run_dir / "runtime_graph_alignments.jsonl", rows.alignments)
    _write_jsonl(run_dir / "runtime_checkpoint_results.jsonl", rows.checkpoint_rows)
    _write_jsonl(run_dir / "runtime_failures.jsonl", rows.runtime_failures)
    (run_dir / "runtime_graph_alignments_summary.json").write_text(
        json.dumps(runtime_alignment_summary(rows), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    snapshots = rows.graph_snapshots
    (run_dir / "runtime_graph_snapshot.json").write_text(json.dumps(snapshots, indent=2, sort_keys=True), encoding="utf-8")

def _horizon_distance_bucket(distance: int | float | object) -> str:
    value = int(distance) if isinstance(distance, (int, float)) else 0
    if value < 5:
        return "short"
    if value < 15:
        return "medium"
    if value < 40:
        return "long"
    return "very_long"

def _interference_count_bucket(count: int | float | object) -> str:
    value = int(count) if isinstance(count, (int, float)) else 0
    if value == 0:
        return "none"
    if value < 10:
        return "low"
    if value < 25:
        return "medium"
    return "high"

def _source_event_age_days_bucket(days: int | float | object) -> str:
    value = float(days) if isinstance(days, (int, float)) else 0.0
    if value < 7:
        return "fresh"
    if value < 30:
        return "aged"
    if value < 90:
        return "old"
    return "stale_long_horizon"

def _long_horizon_slice_counts(checkpoint_rows: list[dict[str, object]]) -> dict[str, dict[str, int]]:
    slice_keys = [
        "phase",
        "horizon_distance_bucket",
        "interference_count_bucket",
        "source_event_age_days_bucket",
        "checkpoint_type",
        "required_retrieval_view",
    ]
    return {
        key: dict(sorted(Counter(str(row.get(key, "unknown")) for row in checkpoint_rows).items()))
        for key in slice_keys
    }

def runtime_graph_completeness_metrics(rows: RuntimeSuiteRows) -> dict[str, object]:
    node_counts: Counter[str] = Counter()
    edge_counts: Counter[str] = Counter()
    validation_error_count = 0
    source_observation_count = 0
    active_claim_count = 0
    claim_subject_count = 0
    claim_object_count = 0
    claim_scope_count = 0
    claim_observed_in_count = 0
    active_action_count = 0
    action_observed_in_count = 0
    graph_edge_count = 0
    for snapshot in rows.graph_snapshots:
        nodes = snapshot.get("nodes", []) if isinstance(snapshot, dict) else []
        edges = snapshot.get("edges", []) if isinstance(snapshot, dict) else []
        validation_error_count += len(snapshot.get("validation_errors", []) or []) if isinstance(snapshot, dict) else 0
        graph_edge_count += len(edges)
        node_type_by_id = {str(node.get("node_id")): str(node.get("node_type")) for node in nodes if isinstance(node, dict)}
        active_claim_node_ids = {
            str(node.get("node_id"))
            for node in nodes
            if isinstance(node, dict) and node.get("node_type") == "claim" and node.get("lifecycle_state") == "active"
        }
        active_action_node_ids = {
            str(node.get("node_id"))
            for node in nodes
            if isinstance(node, dict) and node.get("node_type") == "action" and node.get("lifecycle_state") == "active"
        }
        active_claim_count += len(active_claim_node_ids)
        active_action_count += len(active_action_node_ids)
        claim_has_subject: set[str] = set()
        claim_has_object: set[str] = set()
        claim_has_scope: set[str] = set()
        claim_has_observed_in: set[str] = set()
        action_has_observed_in: set[str] = set()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("node_type", "unknown"))
            node_counts[node_type] += 1
            if node_type == "source_observation":
                source_observation_count += 1
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            edge_type = str(edge.get("edge_type", "unknown"))
            edge_counts[edge_type] += 1
            source_id = str(edge.get("source_node_id", ""))
            target_id = str(edge.get("target_node_id", ""))
            if source_id in active_claim_node_ids:
                if edge_type == "has_subject":
                    claim_has_subject.add(source_id)
                elif edge_type in {"has_object", "has_literal_object"}:
                    claim_has_object.add(source_id)
                elif edge_type == "has_scope":
                    claim_has_scope.add(source_id)
                elif edge_type == "observed_in" and node_type_by_id.get(target_id) == "source_observation":
                    claim_has_observed_in.add(source_id)
            if (
                source_id in active_action_node_ids
                and edge_type == "observed_in"
                and node_type_by_id.get(target_id) == "source_observation"
            ):
                action_has_observed_in.add(source_id)
        claim_subject_count += len(claim_has_subject)
        claim_object_count += len(claim_has_object)
        claim_scope_count += len(claim_has_scope)
        claim_observed_in_count += len(claim_has_observed_in)
        action_observed_in_count += len(action_has_observed_in)
    item_counts = Counter(str(item.get("item_type", "unknown")) for item in rows.graph_items)
    relation_support_modes = Counter()
    for row in rows.checkpoint_rows:
        for item in row.get("runtime_relation_support", []) or []:
            if isinstance(item, dict):
                relation_support_modes[str(item.get("support_mode", "unknown"))] += 1
    return {
        "source_observation_count": source_observation_count,
        "entity_count": node_counts.get("entity", 0),
        "claim_count": node_counts.get("claim", 0),
        "action_count": node_counts.get("action", 0),
        "relation_item_count": item_counts.get("relation", 0),
        "action_item_count": item_counts.get("action", 0),
        "graph_edge_count": graph_edge_count,
        "graph_edge_counts_by_type": dict(sorted(edge_counts.items())),
        "runtime_graph_node_counts_by_type": dict(sorted(node_counts.items())),
        "runtime_graph_item_counts_by_type": dict(sorted(item_counts.items())),
        "runtime_relation_support_modes": dict(sorted(relation_support_modes.items())),
        "evidence_edge_count": edge_counts.get("observed_in", 0),
        "active_claim_count": active_claim_count,
        "active_claim_with_subject_count": claim_subject_count,
        "active_claim_with_object_or_literal_count": claim_object_count,
        "active_claim_with_scope_count": claim_scope_count,
        "active_claim_with_observed_in_count": claim_observed_in_count,
        "active_action_count": active_action_count,
        "active_action_with_observed_in_count": action_observed_in_count,
        "active_claim_with_subject_rate": claim_subject_count / max(1, active_claim_count),
        "active_claim_with_object_or_literal_rate": claim_object_count / max(1, active_claim_count),
        "active_claim_with_scope_rate": claim_scope_count / max(1, active_claim_count),
        "active_claim_with_observed_in_rate": claim_observed_in_count / max(1, active_claim_count),
        "active_action_with_observed_in_rate": action_observed_in_count / max(1, active_action_count),
        "runtime_graph_validation_error_count": validation_error_count,
    }

def runtime_summary_metrics(rows: RuntimeSuiteRows) -> dict[str, object]:
    checkpoint_count = len(rows.checkpoint_rows)
    bucket_counts = Counter(bucket for row in rows.checkpoint_rows for bucket in row.get("runtime_failure_buckets", []))
    final_output_source_counts = Counter(str(row.get("final_output_source", "unknown")) for row in rows.checkpoint_rows)
    provider_successes = sum(int(row.get("provider_successes", 0) or 0) for row in rows.checkpoint_rows)
    provider_failures = sum(int(row.get("provider_failures", 0) or 0) for row in rows.checkpoint_rows)
    fallbacks = sum(int(row.get("fallbacks", 0) or 0) for row in rows.checkpoint_rows)
    graph_summary = runtime_graph_completeness_metrics(rows)
    alignment_summary = runtime_alignment_summary(rows)
    summary: dict[str, object] = {
        "runtime_checkpoint_count": checkpoint_count,
        "runtime_failure_bucket_counts": dict(sorted(bucket_counts.items())),
        "provider_successes": provider_successes,
        "provider_failures": provider_failures,
        "fallbacks": fallbacks,
        "final_output_source_counts": dict(sorted(final_output_source_counts.items())),
        "runtime_alignment_count": len(rows.alignments),
        "runtime_graph_item_count": len(rows.graph_items),
        "runtime_graph_summary": graph_summary,
        "runtime_graph_alignments_summary": alignment_summary,
        "long_horizon_slice_counts": _long_horizon_slice_counts(rows.checkpoint_rows),
    }
    summary.update(graph_summary)
    return summary

def runtime_alignment_summary(rows: RuntimeSuiteRows) -> dict[str, object]:
    checkpoint_expected_ids: dict[tuple[str, str], set[str]] = {}
    for row in rows.checkpoint_rows:
        expected = row.get("expected") if isinstance(row.get("expected"), dict) else {}
        expected_ids: set[str] = set()
        if isinstance(expected, dict):
            for key in ("expected_entity_ids", "expected_claim_ids", "expected_relation_ids", "expected_citation_event_ids"):
                expected_ids.update(str(value) for value in expected.get(key, []) or [])
        checkpoint_expected_ids[(str(row.get("scenario_id")), str(row.get("checkpoint_id")))] = expected_ids

    full_counts: Counter[str] = Counter()
    full_item_counts: Counter[str] = Counter()
    required_counts: Counter[str] = Counter()
    required_item_counts: Counter[str] = Counter()
    required_total = 0
    for alignment in rows.alignments:
        if not isinstance(alignment, dict):
            continue
        verdict = str(alignment.get("verdict", "unknown"))
        item_type = str(alignment.get("item_type", "unknown"))
        full_counts[verdict] += 1
        full_item_counts[f"{item_type}:{verdict}"] += 1
        key = (str(alignment.get("scenario_id")), str(alignment.get("checkpoint_id")))
        oracle_id = str(alignment.get("oracle_item_id") or "")
        if oracle_id and oracle_id in checkpoint_expected_ids.get(key, set()):
            required_total += 1
            required_counts[verdict] += 1
            required_item_counts[f"{item_type}:{verdict}"] += 1
    scored_verdict_counts = Counter(str(row.get("verdict", "unknown")) for row in rows.checkpoint_rows)
    scored_failure_bucket_counts = Counter(
        str(bucket)
        for row in rows.checkpoint_rows
        for bucket in row.get("failure_buckets", []) or []
    )
    return {
        "alignment_summary_policy": {
            "checkpoint_expected_alignment_audit": "Diagnostic-only alignment of checkpoint expected ids against runtime graph items; partial, ambiguous_alignment, and unmatched_runtime are not failures unless reflected in checkpoint_scored_* fields.",
            "full_graph_audit_alignment": "Diagnostic-only alignment over the broader recoverable latent graph slice.",
            "checkpoint_scored": "Authoritative checkpoint pass/fail/review interpretation copied from judged checkpoint rows.",
        },
        "checkpoint_expected_alignment_audit_count": required_total,
        "checkpoint_expected_alignment_audit_counts": dict(sorted(required_counts.items())),
        "checkpoint_expected_alignment_audit_counts_by_item_type": dict(sorted(required_item_counts.items())),
        "checkpoint_scored_verdict_counts": dict(sorted(scored_verdict_counts.items())),
        "checkpoint_scored_review_required_count": sum(1 for row in rows.checkpoint_rows if row.get("review_required") is True),
        "checkpoint_scored_failure_bucket_counts": dict(sorted(scored_failure_bucket_counts.items())),
        "full_graph_audit_alignment_count": len(rows.alignments),
        "full_graph_audit_alignment_counts": dict(sorted(full_counts.items())),
        "full_graph_audit_alignment_counts_by_item_type": dict(sorted(full_item_counts.items())),
    }

def runtime_warning_policy() -> dict[str, dict[str, str]]:
    return {
        "extra_provenance_noise": {
            "level": "warning_only",
            "rationale": "Extra non-support provenance is tracked for precision analysis but is not selected/supporting truth.",
        },
        "extra_context_provenance": {
            "level": "warning_only",
            "rationale": "Context channels may include broader audit evidence when selected/supporting channels remain clean.",
        },
        "graph_answer_optional_missing": {
            "level": "warning_only",
            "rationale": "For graph reconstruction checkpoints, structured graph channels are authoritative and natural-language answer text is optional.",
        },
    }

def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows), encoding="utf-8")
