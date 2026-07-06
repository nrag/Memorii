from __future__ import annotations

from memorii.core.calibration.alignment import (
    RuntimeGraphAlignmentVerdict,
    align_by_normalized_fields,
    align_claim_by_fields,
    align_entity_by_fields,
    align_evidence_by_fields,
    align_relation_by_fields,
)
from memorii.core.calibration.metrics import (
    brier_score,
    build_calibration_slices,
    expected_calibration_error,
    rolling_window_metrics,
    wilson_interval,
)
from memorii.core.calibration.models import (
    CalibrationDecisionChannel,
    CalibrationEvent,
    CalibrationHierarchyLayer,
    CalibrationItemType,
    CalibrationLabel,
    CalibrationLabelSource,
    CalibrationResponseLevel,
    DecisionAction,
)
from memorii.core.calibration.policy import response_for_failure_buckets, response_for_slice
from memorii.core.calibration.reports import build_calibration_artifacts, build_decision_cost_report


def _event(*, confidence: float, label: CalibrationLabel, source: CalibrationLabelSource = CalibrationLabelSource.PROGRAMMATIC_JUDGE, modality: str = "assertion") -> CalibrationEvent:
    return CalibrationEvent(
        event_id=f"event-{confidence}-{label.value}-{modality}",
        suite="memory_evolution_sim_v1",
        scenario_id="scenario",
        checkpoint_id="checkpoint",
        item_id="claim",
        item_type=CalibrationItemType.CLAIM,
        hierarchy_layer=CalibrationHierarchyLayer.RETRIEVAL_DECISION,
        decision_channel=CalibrationDecisionChannel.SELECTED,
        confidence=confidence,
        label=label,
        label_source=source,
        label_rationale="test",
        source_modality=modality,
        predicate_id="owner",
        lifecycle_state="active",
        scope_key="global",
        metadata={"checkpoint_type": "current_truth", "profile": "adversarial"},
    )


def test_calibration_metrics_exclude_runtime_unknown() -> None:
    events = [
        _event(confidence=0.9, label=CalibrationLabel.CORRECT),
        _event(confidence=0.8, label=CalibrationLabel.INCORRECT),
        _event(confidence=1.0, label=CalibrationLabel.UNKNOWN, source=CalibrationLabelSource.RUNTIME_UNKNOWN),
    ]
    assert expected_calibration_error(events) is not None
    assert brier_score(events) == ((0.9 - 1.0) ** 2 + (0.8 - 0.0) ** 2) / 2


def test_wilson_interval_and_slice_support_policy() -> None:
    low, high = wilson_interval(positives=8, n=10)
    assert low is not None and high is not None
    assert 0.0 <= low <= high <= 1.0
    supported = build_calibration_slices([_event(confidence=0.9, label=CalibrationLabel.INCORRECT) for _ in range(10)])
    info = build_calibration_slices([_event(confidence=0.9, label=CalibrationLabel.INCORRECT) for _ in range(4)])
    assert any(item.eligible_for_failure for item in supported)
    assert all(not item.eligible_for_failure for item in info)


def test_slice_policy_uses_wilson_uncertainty_before_hard_failure() -> None:
    response = response_for_slice(
        n=10,
        ece=0.30,
        overconfident_wrong_rate=0.0,
        accuracy=1.0,
        mean_confidence=0.70,
        wilson_high=1.0,
    )
    assert response == CalibrationResponseLevel.REVIEW


def test_calibration_artifacts_emit_hierarchy_and_label_provenance() -> None:
    rows = [
        {
            "scenario_id": "scenario",
            "checkpoint_id": "checkpoint",
            "checkpoint_type": "current_truth",
            "success": True,
            "failure_buckets": [],
            "output": {
                "confidence": 0.8,
                "selected_claim_ids": ["claim_current"],
                "supporting_citation_event_ids": ["event_current"],
            },
            "expected": {
                "expected_claim_ids": ["claim_current"],
                "expected_citation_event_ids": ["event_current"],
                "expected_excluded_claim_ids": ["claim_old"],
            },
            "candidate_cards": {
                "visible_events": [
                    {
                        "event_id": "event_current",
                        "modality": "tool_result",
                        "trust_level": 5,
                    }
                ],
                "visible_claims": [
                    {
                        "claim_id": "claim_current",
                        "predicate_id": "owner",
                        "scope_key": "global",
                        "lifecycle_state": "active",
                        "source_modality": "tool_result",
                        "source_trust": 5,
                        "evidence_event_ids": ["event_current"],
                    }
                ],
            },
            "judge_aggregate": {"votes": [{"judge_id": "claim_spo_judge"}]},
        }
    ]
    events, report, slices, decision_report = build_calibration_artifacts(
        suite="memory_evolution_sim_v1",
        profile="adversarial",
        checkpoint_rows=rows,
    )
    layers = {event.hierarchy_layer for event in events}
    assert CalibrationHierarchyLayer.OBSERVATION in layers
    assert CalibrationHierarchyLayer.EXTRACTION in layers
    assert CalibrationHierarchyLayer.VALIDATION in layers
    assert CalibrationHierarchyLayer.GRAPH in layers
    assert CalibrationHierarchyLayer.RETRIEVAL_DECISION in layers
    assert report.label_source_counts[CalibrationLabelSource.LATENT_ORACLE.value] >= 1
    assert report.hierarchy_layer_counts[CalibrationHierarchyLayer.GRAPH.value] >= 1
    citation_event = next(event for event in events if event.item_id == "event_current" and event.decision_channel == CalibrationDecisionChannel.SUPPORTING)
    assert citation_event.item_type == CalibrationItemType.SOURCE_OBSERVATION
    selected_event = next(event for event in events if event.item_id == "claim_current" and event.decision_channel == CalibrationDecisionChannel.SELECTED)
    assert selected_event.label_source == CalibrationLabelSource.LATENT_ORACLE
    assert selected_event.label_history[0].label_source == CalibrationLabelSource.LATENT_ORACLE
    assert selected_event.decision_action == DecisionAction.ANSWER_CURRENT_TRUTH
    assert slices
    assert decision_report.regret_total == 0.0


def test_calibration_context_events_in_passing_rows_are_correct_audit_evidence() -> None:
    rows = [
        {
            "scenario_id": "scenario",
            "checkpoint_id": "checkpoint",
            "checkpoint_type": "current_truth",
            "success": True,
            "failure_buckets": [],
            "output": {
                "confidence": 0.95,
                "context_claim_ids": ["claim_context"],
            },
            "expected": {"expected_claim_ids": ["claim_current"]},
            "judge_aggregate": {"votes": [{"judge_id": "graph_context_judge"}]},
        }
    ]

    events, report, _slices, _decision_report = build_calibration_artifacts(
        suite="memory_evolution_sim_v1",
        profile="adversarial",
        checkpoint_rows=rows,
    )

    context_event = next(event for event in events if event.item_id == "claim_context")
    assert context_event.label == CalibrationLabel.CORRECT
    assert context_event.confidence == 0.95
    assert report.overconfident_wrong_count == 0
    assert report.overall_accuracy == 1.0



def test_calibration_rejected_expected_item_is_incorrect_but_rejected_excluded_is_correct() -> None:
    rows = [
        {
            "scenario_id": "scenario",
            "checkpoint_id": "checkpoint",
            "checkpoint_type": "current_truth",
            "success": True,
            "failure_buckets": [],
            "output": {
                "confidence": 0.9,
                "rejected_claim_ids": ["claim_current", "claim_old"],
            },
            "expected": {
                "expected_claim_ids": ["claim_current"],
                "expected_excluded_claim_ids": ["claim_old"],
            },
            "judge_aggregate": {"votes": [{"judge_id": "rejection_classification_judge"}]},
        }
    ]

    events, _report, _slices, _decision_report = build_calibration_artifacts(
        suite="memory_evolution_sim_v1",
        profile="adversarial",
        checkpoint_rows=rows,
    )

    current = next(event for event in events if event.item_id == "claim_current")
    old = next(event for event in events if event.item_id == "claim_old")
    assert current.label == CalibrationLabel.INCORRECT
    assert "expected_item_rejected" in current.failure_buckets
    assert old.label == CalibrationLabel.CORRECT

def test_calibration_artifacts_mark_excluded_support_as_oracle_failure() -> None:
    rows = [
        {
            "scenario_id": "scenario",
            "checkpoint_id": "checkpoint",
            "checkpoint_type": "current_truth",
            "success": False,
            "failure_buckets": ["wrong_current_truth"],
            "output": {
                "confidence": 0.91,
                "supporting_claim_ids": ["claim_old"],
            },
            "expected": {
                "expected_claim_ids": ["claim_current"],
                "expected_excluded_claim_ids": ["claim_old"],
            },
            "judge_aggregate": {"votes": [{"judge_id": "selected_truth_precision_judge"}]},
        }
    ]
    events, report, _slices, decision_report = build_calibration_artifacts(
        suite="memory_evolution_sim_v1",
        profile="adversarial",
        checkpoint_rows=rows,
    )
    stale_event = next(event for event in events if event.item_id == "claim_old")
    assert stale_event.label == CalibrationLabel.INCORRECT
    assert stale_event.label_source == CalibrationLabelSource.LATENT_ORACLE
    assert CalibrationLabelSource.PROGRAMMATIC_JUDGE in stale_event.label_sources
    assert "stale_memory_selected" in stale_event.failure_buckets
    assert report.overconfident_wrong_count >= 1
    assert decision_report.cost_by_decision_action[DecisionAction.ANSWER_CURRENT_TRUTH.value] >= 50.0
    assert decision_report.regret_total >= 50.0


def test_response_policy_marks_hidden_hallucination_as_benchmark_fail() -> None:
    assert response_for_failure_buckets(["hidden_fact_hallucinated"]) == CalibrationResponseLevel.BENCHMARK_FAIL
    assert response_for_failure_buckets(["extra_provenance_noise"]) == CalibrationResponseLevel.REPORT_ONLY


def test_rolling_metrics_emit_drift_windows() -> None:
    events = [_event(confidence=0.9, label=CalibrationLabel.CORRECT) for _ in range(10)]
    events.extend(_event(confidence=0.9, label=CalibrationLabel.INCORRECT) for _ in range(10))
    rolling = rolling_window_metrics(events, windows=(10,))
    assert "10" in rolling
    assert rolling["10"]


def test_decision_cost_report_uses_failure_bucket_costs() -> None:
    report = build_decision_cost_report([
        {"checkpoint_type": "current_truth", "failure_buckets": ["hidden_fact_hallucinated"]},
        {"checkpoint_type": "current_truth", "failure_buckets": ["extra_provenance_noise"]},
    ])
    assert report.decision_cost_total == 102.0
    assert report.cost_by_failure_bucket["hidden_fact_hallucinated"] == 100.0


def test_runtime_graph_alignment_exact_and_partial() -> None:
    exact = align_by_normalized_fields(
        runtime_item_id="runtime",
        oracle_item_id="oracle",
        item_type="claim",
        runtime_fields={"subject": "Atlas", "predicate": "owner"},
        oracle_fields={"subject": " atlas ", "predicate": "owner"},
        required_fields=["subject", "predicate"],
    )
    partial = align_by_normalized_fields(
        runtime_item_id="runtime",
        oracle_item_id="oracle",
        item_type="claim",
        runtime_fields={"subject": "Atlas", "predicate": "approver"},
        oracle_fields={"subject": "Atlas", "predicate": "owner"},
        required_fields=["subject", "predicate"],
    )
    assert exact.verdict == RuntimeGraphAlignmentVerdict.ALIGNED
    assert partial.verdict == RuntimeGraphAlignmentVerdict.PARTIAL


def test_runtime_graph_alignment_protocol_helpers() -> None:
    entity = align_entity_by_fields(
        runtime_item_id="runtime_entity",
        oracle_item_id="oracle_entity",
        runtime_fields={"canonical_name": "Atlas Billing", "entity_type": "project", "aliases": ["Atlas"], "evidence_event_ids": ["event_1"]},
        oracle_fields={"canonical_name": "Atlas", "entity_type": "project", "aliases": [], "evidence_event_ids": ["event_1"]},
    )
    claim = align_claim_by_fields(
        runtime_item_id="runtime_claim",
        oracle_item_id="oracle_claim",
        runtime_fields={"subject": "Atlas", "predicate": "owner", "object": "Bob", "scope": "global", "valid_time": "2026-03"},
        oracle_fields={"subject": " atlas ", "predicate": "owner", "object": "bob", "scope": "global", "valid_time": "2026-03"},
    )
    relation = align_relation_by_fields(
        runtime_item_id="runtime_relation",
        oracle_item_id="oracle_relation",
        runtime_fields={"source": "claim_new", "target": "claim_old", "relation_type": "supersedes", "directionality": "directed"},
        oracle_fields={"source": "claim_new", "target": "claim_old", "relation_type": "supersedes", "directionality": "directed"},
    )
    evidence = align_evidence_by_fields(
        runtime_item_id="runtime_evidence",
        oracle_item_id="oracle_evidence",
        runtime_fields={"source_event_id": "event_1", "quote": "Atlas owner is Bob"},
        oracle_fields={"source_event_id": "event_1", "quote": "Atlas owner is Bob as of March"},
    )
    assert entity.verdict == RuntimeGraphAlignmentVerdict.ALIGNED
    assert claim.verdict == RuntimeGraphAlignmentVerdict.ALIGNED
    assert relation.verdict == RuntimeGraphAlignmentVerdict.ALIGNED
    assert evidence.verdict in {RuntimeGraphAlignmentVerdict.ALIGNED, RuntimeGraphAlignmentVerdict.PARTIAL}
    assert "quote_overlap" in evidence.matched_on


def test_build_calibration_artifacts_from_checkpoint_rows() -> None:
    rows = [
        {
            "scenario_id": "scenario",
            "checkpoint_id": "checkpoint",
            "checkpoint_type": "current_truth",
            "success": True,
            "failure_buckets": [],
            "output": {
                "confidence": 0.8,
                "selected_claim_ids": ["claim_current"],
                "supporting_citation_event_ids": ["event_current"],
            },
            "expected": {
                "expected_claim_ids": ["claim_current"],
                "expected_citation_event_ids": ["event_current"],
                "expected_excluded_claim_ids": ["claim_old"],
            },
            "judge_aggregate": {"votes": [{"judge_id": "claim_spo_judge"}]},
        }
    ]
    events, report, slices, decision_report = build_calibration_artifacts(
        suite="memory_evolution_sim_v1",
        profile="adversarial",
        checkpoint_rows=rows,
    )
    assert events
    assert report.labeled_event_count == len(events)
    assert slices
    assert decision_report.decision_cost_total == 0.0
