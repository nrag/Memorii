from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.artifact_rows import SimCheckpointResultRow
from memorii.core.benchmark.calibration.alignment import (
    RuntimeGraphAlignmentVerdict,
    align_by_normalized_fields,
    align_claim_by_fields,
    align_entity_by_fields,
    align_evidence_by_fields,
    align_relation_by_fields,
)
from memorii.core.benchmark.calibration.metrics import (
    brier_score,
    build_calibration_slices,
    expected_calibration_error,
    risk_coverage_curve,
    rolling_window_metrics,
    scenario_cluster_accuracy_interval,
    wilson_interval,
)
from memorii.core.benchmark.calibration.models import (
    CalibrationDecisionChannel,
    CalibrationEvent,
    CalibrationHierarchyLayer,
    CalibrationItemType,
    CalibrationLabel,
    CalibrationLabelSource,
    CalibrationResponseLevel,
    DecisionAction,
)
from memorii.core.benchmark.calibration.policy import response_for_failure_buckets, response_for_slice
from memorii.core.benchmark.calibration.reports import build_calibration_artifacts, build_decision_cost_report
from memorii.core.benchmark.memory_evolution_sim.schemas import SimCheckpointContract
from tests.unit.core.benchmark.checkpoint_artifact_test_helpers import checkpoint_diagnostics_payload


def _checkpoint_row(partial: dict[str, object]) -> SimCheckpointResultRow:
    """Build a complete typed row from the fields relevant to a calibration test."""

    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    checkpoint_type = str(partial.get("checkpoint_type", "current_truth"))
    success = bool(partial.get("success", True))
    output = dict(partial.get("output", {}))
    output.setdefault("rationale", "calibration test output")
    expected = dict(partial.get("expected", {}))
    expected.update(
        {
            "checkpoint_id": str(partial.get("checkpoint_id", "checkpoint")),
            "timestamp": timestamp,
            "checkpoint_type": checkpoint_type,
            "query_or_task": "calibration test",
            "checkpoint_contract": SimCheckpointContract().model_dump(mode="json"),
        }
    )
    cards = dict(partial.get("candidate_cards", {}))
    visible_events = []
    for event_value in cards.get("visible_events", []):
        event = dict(event_value)
        event.setdefault("timestamp", timestamp)
        event.setdefault("source_type", "tool")
        event.setdefault("text", "calibration test event")
        visible_events.append(event)
    visible_claims = []
    for claim_value in cards.get("visible_claims", []):
        claim = dict(claim_value)
        claim.setdefault("subject_entity_id", "entity:subject")
        claim.setdefault("subject_name", "subject")
        claim.setdefault("subject_entity_type", "entity")
        claim.setdefault("object_value", "value")
        claim.setdefault("evidence_quote", "calibration test evidence")
        visible_claims.append(claim)
    cards.update(
        {
            "scenario_id": str(partial.get("scenario_id", "scenario")),
            "surface_observations": [],
            "checkpoint": {
                "checkpoint_id": str(partial.get("checkpoint_id", "checkpoint")),
                "timestamp": timestamp,
                "query_or_task": "calibration test",
            },
            "visible_events": visible_events,
            "visible_claims": visible_claims,
        }
    )
    aggregate = dict(partial.get("judge_aggregate", {}))
    votes = [
        {
            "judge_id": str(dict(vote).get("judge_id", "judge")),
            "checkpoint_id": str(partial.get("checkpoint_id", "checkpoint")),
            "verdict": "pass" if success else "fail",
            "score": 1.0 if success else 0.0,
            "confidence": 1.0,
            "rationale": "calibration test vote",
        }
        for vote in aggregate.get("votes", [])
    ]
    aggregate.update(
        {
            "checkpoint_id": str(partial.get("checkpoint_id", "checkpoint")),
            "verdict": "pass" if success else "fail",
            "score": 1.0 if success else 0.0,
            "confidence": 1.0,
            "votes": votes,
            "rationale": "calibration test aggregate",
        }
    )
    payload: dict[str, object] = {
        "scenario_id": "scenario",
        "checkpoint_id": "checkpoint",
        "checkpoint_type": checkpoint_type,
        "success": success,
        "passed": success,
        "verdict": "pass" if success else "fail",
        "score": 1.0 if success else 0.0,
        "review_required": not success,
        "failure_buckets": [],
        "warning_buckets": [],
        "diagnostics": checkpoint_diagnostics_payload(),
        "profile": "adversarial",
        "family": "calibration",
        "decision_mode": "rule",
        "effective_decision_mode": "rule",
        "final_output_source": "rule",
    }
    payload.update(partial)
    payload.update(
        output=output,
        raw_output=output,
        expected=expected,
        candidate_cards=cards,
        judge_aggregate=aggregate,
    )
    return SimCheckpointResultRow.model_validate(payload)


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


def test_risk_coverage_is_confidence_ordered_and_deterministic() -> None:
    events = [
        _event(confidence=0.9, label=CalibrationLabel.INCORRECT),
        _event(confidence=0.6, label=CalibrationLabel.CORRECT),
        _event(confidence=0.2, label=CalibrationLabel.CORRECT),
    ]
    curve = risk_coverage_curve(events)
    assert [point.accepted_count for point in curve] == [1, 2, 3]
    assert [point.threshold for point in curve] == [0.9, 0.6, 0.2]
    assert curve[0].selective_risk == 1.0
    assert curve[-1].coverage == 1.0


def test_scenario_cluster_interval_is_deterministic_and_not_event_weighted() -> None:
    events = [
        _event(confidence=0.9, label=CalibrationLabel.CORRECT),
        _event(confidence=0.9, label=CalibrationLabel.CORRECT),
        _event(confidence=0.9, label=CalibrationLabel.INCORRECT),
    ]
    events[0].scenario_id = "large"
    events[1].scenario_id = "large"
    events[2].scenario_id = "small"
    first = scenario_cluster_accuracy_interval(events, seed=11, resamples=100)
    second = scenario_cluster_accuracy_interval(events, seed=11, resamples=100)
    assert first is not None and second is not None
    assert first == second
    assert first.estimate == 0.5
    assert first.scenario_count == 2
    assert first.observation_count == 3
    assert 0.0 <= first.lower <= first.estimate <= first.upper <= 1.0


def test_wilson_interval_and_slice_support_policy() -> None:
    low, high = wilson_interval(positives=8, n=10)
    assert low is not None and high is not None
    assert 0.0 <= low <= high <= 1.0
    supported_events = [_event(confidence=0.9, label=CalibrationLabel.INCORRECT) for _ in range(10)]
    for index, event in enumerate(supported_events):
        event.scenario_id = f"scenario-{index}"
    supported = build_calibration_slices(supported_events)
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
    rows = [_checkpoint_row(row) for row in [
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
    ]]
    events, report, slices, decision_report = build_calibration_artifacts(
        suite="memory_evolution_sim_v1",
        profile="adversarial",
        checkpoint_rows=rows,
    )
    layers = {event.hierarchy_layer for event in events}
    assert CalibrationHierarchyLayer.RETRIEVAL_DECISION in layers
    assert CalibrationHierarchyLayer.OBSERVATION not in layers
    assert report.input_telemetry_count == 2
    assert report.input_telemetry_by_type == {"visible_claims": 1, "visible_events": 1}
    assert report.label_source_counts[CalibrationLabelSource.LATENT_ORACLE.value] >= 1
    assert CalibrationHierarchyLayer.GRAPH.value not in report.hierarchy_layer_counts
    assert report.scenario_cluster_intervals["accuracy"].scenario_count == 1
    citation_event = next(event for event in events if event.item_id == "event_current" and event.decision_channel == CalibrationDecisionChannel.SUPPORTING)
    assert citation_event.item_type == CalibrationItemType.SOURCE_OBSERVATION
    selected_event = next(event for event in events if event.item_id == "claim_current" and event.decision_channel == CalibrationDecisionChannel.SELECTED)
    assert selected_event.label_source == CalibrationLabelSource.LATENT_ORACLE
    assert selected_event.label_history[0].label_source == CalibrationLabelSource.LATENT_ORACLE
    assert selected_event.decision_action == DecisionAction.ANSWER_CURRENT_TRUTH
    assert slices
    assert decision_report.regret_total == 0.0


def test_calibration_retrieval_decision_phase_comes_from_evidence_event() -> None:
    rows = [_checkpoint_row(row) for row in [
        {
            "scenario_id": "scenario",
            "checkpoint_id": "checkpoint",
            "checkpoint_type": "execution_continuation",
            "phase": "checkpoint",
            "success": True,
            "failure_buckets": [],
            "output": {
                "confidence": 0.86,
                "selected_claim_ids": ["claim_branch_progress"],
            },
            "expected": {
                "expected_claim_ids": ["claim_branch_progress"],
            },
            "candidate_cards": {
                "visible_events": [
                    {
                        "event_id": "event_branch_progress",
                        "modality": "assertion",
                        "trust_level": 4,
                        "phase": "evolution",
                    }
                ],
                "visible_claims": [
                    {
                        "claim_id": "claim_branch_progress",
                        "predicate_id": "action_state",
                        "scope_key": "task:atlas",
                        "lifecycle_state": "active",
                        "source_modality": "assertion",
                        "source_trust": 4,
                        "evidence_event_ids": ["event_branch_progress"],
                    }
                ],
            },
            "judge_aggregate": {"votes": [{"judge_id": "execution_branch_judge"}]},
        }
    ]]

    events, _report, slices, _decision_report = build_calibration_artifacts(
        suite="memory_evolution_runtime_v1",
        profile="long_horizon",
        checkpoint_rows=rows,
    )

    selected = next(
        event
        for event in events
        if event.item_id == "claim_branch_progress"
        and event.hierarchy_layer == CalibrationHierarchyLayer.RETRIEVAL_DECISION
    )
    assert selected.metadata["phase"] == "evolution"
    assert selected.metadata["evidence_phases"] == "evolution"
    phase_slices = [item for item in slices if item.slice_key == "phase"]
    assert any(item.slice_values == {"phase": "evolution"} for item in phase_slices)


def test_calibration_context_events_in_passing_rows_are_correct_audit_evidence() -> None:
    rows = [_checkpoint_row(row) for row in [
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
    ]]

    events, report, _slices, _decision_report = build_calibration_artifacts(
        suite="memory_evolution_sim_v1",
        profile="adversarial",
        checkpoint_rows=rows,
    )

    context_event = next(event for event in events if event.item_id == "claim_context")
    assert context_event.label == CalibrationLabel.CORRECT
    assert context_event.confidence == 0.95
    assert report.overconfident_wrong_count == 2
    assert report.overall_accuracy == 1 / 3



def test_calibration_rejected_expected_item_is_incorrect_but_rejected_excluded_is_correct() -> None:
    rows = [_checkpoint_row(row) for row in [
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
    ]]

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
    rows = [_checkpoint_row(row) for row in [
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
    ]]
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
        _checkpoint_row({"checkpoint_type": "current_truth", "failure_buckets": ["hidden_fact_hallucinated"]}),
        _checkpoint_row({"checkpoint_type": "current_truth", "failure_buckets": ["extra_provenance_noise"]}),
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
    rows = [_checkpoint_row(row) for row in [
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
    ]]
    events, report, slices, decision_report = build_calibration_artifacts(
        suite="memory_evolution_sim_v1",
        profile="adversarial",
        checkpoint_rows=rows,
    )
    assert events
    assert report.labeled_event_count == len(events)
    assert slices
    assert decision_report.decision_cost_total == 0.0
