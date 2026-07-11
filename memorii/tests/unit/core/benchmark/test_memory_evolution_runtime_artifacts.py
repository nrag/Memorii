from __future__ import annotations

from memorii.core.benchmark.memory_evolution_runtime import (
    RuntimeSuiteRows,
    runtime_graph_completeness_metrics,
    runtime_summary_metrics,
)
from tests.unit.core.benchmark.memory_evolution_runtime_test_helpers import runtime_checkpoint_row


def test_runtime_summary_reports_long_horizon_slice_counts() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            runtime_checkpoint_row(
                checkpoint_type="current_truth",
                phase="checkpoint",
                horizon_distance_bucket="long",
                interference_count_bucket="medium",
                source_event_age_days_bucket="old",
                required_retrieval_view="current",
            )
        ],
        judge_rows=[],
        llm_rows=[],
    )

    summary = runtime_summary_metrics(rows)

    assert summary["long_horizon_slice_counts"]["horizon_distance_bucket"] == {"long": 1}
    assert summary["long_horizon_slice_counts"]["interference_count_bucket"] == {"medium": 1}
    assert summary["runtime_graph_alignments_summary"]["checkpoint_scored_verdict_counts"] == {"pass": 1}



def test_runtime_graph_completeness_metrics_report_claim_provenance_and_edge_counts() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            runtime_checkpoint_row(
                runtime_relation_support=[
                    {"relation_id": "rel_claim_derived", "support_mode": "claim_derived"},
                    {"relation_id": "rel_item", "support_mode": "runtime_relation_item"},
                ]
            )
        ],
        judge_rows=[],
        llm_rows=[],
        graph_items=[
            {"item_type": "claim"},
            {"item_type": "entity"},
            {"item_type": "relation"},
            {"item_type": "action"},
        ],
        graph_snapshots=[
            {
                "validation_errors": [],
                "nodes": [
                    {"node_id": "source:1", "node_type": "source_observation"},
                    {"node_id": "claim:1", "node_type": "claim", "lifecycle_state": "active"},
                    {"node_id": "action:1", "node_type": "action", "lifecycle_state": "active"},
                    {"node_id": "entity:1", "node_type": "entity"},
                    {"node_id": "literal:1", "node_type": "literal"},
                    {"node_id": "scope:global", "node_type": "scope"},
                ],
                "edges": [
                    {"edge_type": "has_subject", "source_node_id": "claim:1", "target_node_id": "entity:1"},
                    {"edge_type": "has_literal_object", "source_node_id": "claim:1", "target_node_id": "literal:1"},
                    {"edge_type": "has_scope", "source_node_id": "claim:1", "target_node_id": "scope:global"},
                    {"edge_type": "observed_in", "source_node_id": "claim:1", "target_node_id": "source:1"},
                    {"edge_type": "observed_in", "source_node_id": "action:1", "target_node_id": "source:1"},
                ],
            }
        ],
    )

    metrics = runtime_graph_completeness_metrics(rows)

    assert metrics["source_observation_count"] == 1
    assert metrics["entity_count"] == 1
    assert metrics["claim_count"] == 1
    assert metrics["relation_item_count"] == 1
    assert metrics["action_item_count"] == 1
    assert metrics["evidence_edge_count"] == 2
    assert metrics["active_claim_with_subject_rate"] == 1.0
    assert metrics["active_claim_with_object_or_literal_rate"] == 1.0
    assert metrics["active_claim_with_scope_rate"] == 1.0
    assert metrics["active_claim_with_observed_in_rate"] == 1.0
    assert metrics["action_count"] == 1
    assert metrics["active_action_count"] == 1
    assert metrics["active_action_with_observed_in_rate"] == 1.0
    assert metrics["runtime_relation_support_modes"] == {
        "claim_derived": 1,
        "runtime_relation_item": 1,
    }

