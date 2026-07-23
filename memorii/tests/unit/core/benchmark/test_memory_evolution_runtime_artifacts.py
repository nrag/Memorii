from __future__ import annotations

import pytest
from memorii.core.benchmark.artifact_rows import (
    FinalOutputSource,
    RuntimeExecutionStateSection,
    RuntimeExtractorOutput,
    RuntimeExtractorTracePayload,
    RuntimeExtractorTraceRow,
)
from memorii.core.benchmark.memory_evolution_runtime import (
    RuntimeGraphItem,
    RuntimeGraphItemRow,
    RuntimeGraphSnapshotRow,
    RuntimeSuiteRows,
    runtime_graph_completeness_metrics,
    runtime_provider_health,
    runtime_summary_metrics,
)
from memorii.core.benchmark.memory_evolution_runtime.extractors import (
    RecordedExtractionRun,
    RecordingMemoryExtractor,
)
from memorii.core.benchmark.memory_evolution_runtime.models import RUNTIME_GRAPH_ITEM_ADAPTER
from memorii.core.benchmark.memory_evolution_runtime.result_rows import (
    runtime_failure_classification,
    runtime_final_output_source,
)
from memorii.core.memory_evolution import (
    EnglishRuleMemoryExtractor,
    ExtractionFailureCode,
    ExtractionRunStatus,
    FallbackOutcome,
    ProviderAttemptStatus,
)
from memorii.core.memory_evolution import (
    FinalExtractionSource as MemoryFinalExtractionSource,
)
from memorii.core.memory_evolution.execution import (
    ContinuationDecision,
    ContinuationResolutionStatus,
    WorkStateSnapshot,
)
from tests.unit.core.benchmark.checkpoint_artifact_test_helpers import checkpoint_diagnostics_payload
from tests.unit.core.benchmark.memory_evolution_runtime_test_helpers import runtime_checkpoint_row


def runtime_graph_item(**overrides: object) -> RuntimeGraphItem:
    item_type = str(overrides.pop("item_type", "claim"))
    payload: dict[str, object] = {
        "item_type": item_type,
        "scenario_id": "scenario_1",
        "runtime_item_id": f"{item_type}:1",
        "lifecycle_state": "active",
    }
    payload.update(
        {
            "claim": {
                "claim_id": "claim:1",
                "subject_entity_id": "entity:1",
                "predicate": "status",
                "object_value": "active",
            },
            "entity": {
                "canonical_id": "entity:1",
                "canonical_name": "Entity",
                "entity_type": "unknown",
            },
            "relation": {
                "relation_type": "supersedes",
                "source": "claim:1",
                "target": "claim:2",
            },
            "action": {
                "action_id": "action:1",
                "action_type": "work",
                "status": "in_progress",
            },
        }[item_type]
    )
    payload.update(overrides)
    return RUNTIME_GRAPH_ITEM_ADAPTER.validate_python(payload)


def runtime_extractor_trace(
    *,
    extraction_status: ExtractionRunStatus = ExtractionRunStatus.SUCCEEDED,
    provider_attempt_status: ProviderAttemptStatus = ProviderAttemptStatus.SUCCEEDED,
    fallback_outcome: FallbackOutcome = FallbackOutcome.NOT_USED,
    final_output_source: FinalOutputSource = "live_llm",
) -> RuntimeExtractorTraceRow:
    fallback_used = fallback_outcome != FallbackOutcome.NOT_USED
    provider_failed = provider_attempt_status not in {
        ProviderAttemptStatus.NOT_ATTEMPTED,
        ProviderAttemptStatus.SUCCEEDED,
    }
    return RuntimeExtractorTraceRow.model_validate(
        {
            "scenario_id": "scenario_1",
            "transition_type": "runtime_memory_extraction",
            "decision_mode": "llm",
            "effective_decision_mode": "llm",
            "final_output_source": final_output_source,
            "trace": RuntimeExtractorTracePayload(
                provider="test",
                scenario_id="scenario_1",
                call_index=0,
                entity_count=0,
                claim_count=0,
                action_count=0,
            ),
            "extraction_status": extraction_status,
            "provider_attempt_status": provider_attempt_status,
            "fallback_outcome": fallback_outcome,
            "final_extraction_source": "fallback" if fallback_used else "primary",
            "failure_code": None,
            "primary_failure_code": "provider_error" if provider_failed else None,
            "fallback_provider": "english_rule" if fallback_used else None,
            "output": RuntimeExtractorOutput(),
        }
    )


def test_runtime_graph_items_are_typed_at_the_artifact_boundary() -> None:
    graph_item = runtime_graph_item(
        runtime_item_id="runtime:claim:1",
        confidence=0.8,
    )
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[],
        judge_rows=[],
        llm_rows=[],
        graph_items=[graph_item],
    )

    assert isinstance(rows.graph_items[0], RuntimeGraphItemRow)
    assert rows.graph_items[0].claim_id == "claim:1"

    with pytest.raises(TypeError, match="Runtime.*GraphItemRow"):
        RuntimeSuiteRows(
            scenario_rows=[],
            checkpoint_rows=[],
            judge_rows=[],
            llm_rows=[],
            graph_items=[graph_item.model_dump(mode="json")],  # type: ignore[list-item]
        )

    with pytest.raises(ValueError, match="extra_field"):
        RUNTIME_GRAPH_ITEM_ADAPTER.validate_python(
            {
                "item_type": "claim",
                "extra_field": "must_be_declared",
            }
        )

    with pytest.raises(ValueError, match="subject_entity_id"):
        RUNTIME_GRAPH_ITEM_ADAPTER.validate_python(
            {
                "scenario_id": "scenario_1",
                "runtime_item_id": "runtime:claim:1",
                "item_type": "claim",
                "claim_id": "claim:1",
                "lifecycle_state": "active",
            }
        )


def test_runtime_graph_snapshot_requires_identity() -> None:
    with pytest.raises(ValueError, match="snapshot_id must be non-empty"):
        RuntimeGraphSnapshotRow.model_validate({"scenario_id": "scenario_1", "checkpoint_id": "checkpoint_1"})


def test_runtime_missing_rejection_has_named_failure_classification() -> None:
    assert runtime_failure_classification(
        ["runtime_missing_expected_rejection"],
        checkpoint_diagnostics_payload(failure_classification=["unclassified_failure"]),
    ) == ["runtime_missing_expected_rejection"]


def test_runtime_checkpoint_diagnostics_cannot_drift_between_public_views() -> None:
    row = runtime_checkpoint_row(
        answer_match_type="semantic",
        required_judge_ids=["claim_spo_judge"],
    )

    assert row.answer_match_type == row.diagnostics.answer_match_type == "semantic"
    assert row.required_judge_ids == row.diagnostics.required_judge_ids == ["claim_spo_judge"]

    payload = row.model_dump(mode="json")
    payload["answer_match_type"] = "mismatch"
    with pytest.raises(ValueError, match="top-level diagnostics must match"):
        type(row).model_validate(payload)


def test_runtime_execution_artifact_nested_state_is_typed_and_json_readable() -> None:
    section = RuntimeExecutionStateSection(
        active_continuation_branch="branch:b",
        continuation_decision=ContinuationDecision(
            status=ContinuationResolutionStatus.RESOLVED,
            branch_id="branch:b",
            action_event_id="action:b",
            rationale="unique active branch",
        ),
        production_work_state=WorkStateSnapshot(active_branch_ids=["branch:b"]),
    )

    assert isinstance(section.production_work_state, WorkStateSnapshot)
    assert section.continuation_decision.status == "resolved"
    assert section.production_work_state.active_branch_ids == ["branch:b"]


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
        dry_run=True,
    )

    summary = runtime_summary_metrics(rows)

    assert summary.long_horizon_slice_counts["horizon_distance_bucket"] == {"long": 1}
    assert summary.long_horizon_slice_counts["interference_count_bucket"] == {"medium": 1}
    assert summary.runtime_graph_alignments_summary.checkpoint_scored_verdict_counts == {
        "fail": 0,
        "pass": 1,
    }


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
            runtime_graph_item(),
            runtime_graph_item(
                item_type="entity",
                runtime_item_id="entity:1",
                canonical_id="entity:1",
                canonical_name="Entity",
            ),
            runtime_graph_item(
                item_type="relation",
                runtime_item_id="relation:1",
                relation_type="supersedes",
                source="claim:1",
                target="entity:1",
            ),
            runtime_graph_item(
                item_type="action",
                runtime_item_id="action:1",
                action_id="action:1",
                action_type="work",
                status="in_progress",
            ),
        ],
        graph_snapshots=[
            RuntimeGraphSnapshotRow.model_validate(
                {
                    "snapshot_id": "snapshot:1",
                    "scenario_id": "scenario_1",
                    "checkpoint_id": "checkpoint_1",
                    "validation_errors": [],
                    "nodes": [
                        {
                            "node_id": "source:1",
                            "node_type": "source_observation",
                            "label": "source",
                            "lifecycle_state": "active",
                            "payload_ref": "source:1",
                            "confidence": 1.0,
                        },
                        {
                            "node_id": "claim:1",
                            "node_type": "claim",
                            "label": "claim",
                            "lifecycle_state": "active",
                            "payload_ref": "claim:1",
                            "confidence": 1.0,
                        },
                        {
                            "node_id": "action:1",
                            "node_type": "action",
                            "label": "action",
                            "lifecycle_state": "active",
                            "payload_ref": "action:1",
                            "confidence": 1.0,
                        },
                        {
                            "node_id": "entity:1",
                            "node_type": "entity",
                            "label": "entity",
                            "lifecycle_state": "active",
                            "payload_ref": "entity:1",
                            "confidence": 1.0,
                        },
                        {
                            "node_id": "literal:1",
                            "node_type": "literal",
                            "label": "literal",
                            "lifecycle_state": "active",
                            "payload_ref": "literal:1",
                            "confidence": 1.0,
                        },
                        {
                            "node_id": "scope:global",
                            "node_type": "scope",
                            "label": "scope",
                            "lifecycle_state": "active",
                            "payload_ref": "scope:global",
                            "confidence": 1.0,
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge:1",
                            "edge_type": "has_subject",
                            "source_node_id": "claim:1",
                            "target_node_id": "entity:1",
                            "lifecycle_state": "active",
                            "confidence": 1.0,
                        },
                        {
                            "edge_id": "edge:2",
                            "edge_type": "has_literal_object",
                            "source_node_id": "claim:1",
                            "target_node_id": "literal:1",
                            "lifecycle_state": "active",
                            "confidence": 1.0,
                        },
                        {
                            "edge_id": "edge:3",
                            "edge_type": "has_scope",
                            "source_node_id": "claim:1",
                            "target_node_id": "scope:global",
                            "lifecycle_state": "active",
                            "confidence": 1.0,
                        },
                        {
                            "edge_id": "edge:4",
                            "edge_type": "observed_in",
                            "source_node_id": "claim:1",
                            "target_node_id": "source:1",
                            "lifecycle_state": "active",
                            "confidence": 1.0,
                        },
                        {
                            "edge_id": "edge:5",
                            "edge_type": "observed_in",
                            "source_node_id": "action:1",
                            "target_node_id": "source:1",
                            "lifecycle_state": "active",
                            "confidence": 1.0,
                        },
                    ],
                }
            )
        ],
    )

    metrics = runtime_graph_completeness_metrics(rows)

    assert metrics.source_observation_count == 1
    assert metrics.entity_count == 1
    assert metrics.claim_count == 1
    assert metrics.relation_item_count == 1
    assert metrics.action_item_count == 1
    assert metrics.evidence_edge_count == 2
    assert metrics.active_claim_with_subject_rate == 1.0
    assert metrics.active_claim_with_object_or_literal_rate == 1.0
    assert metrics.active_claim_with_scope_rate == 1.0
    assert metrics.active_claim_with_observed_in_rate == 1.0
    assert metrics.action_count == 1
    assert metrics.active_action_count == 1
    assert metrics.active_action_with_observed_in_rate == 1.0
    assert metrics.runtime_relation_support_modes == {
        "claim_derived": 1,
        "runtime_relation_item": 1,
    }


def test_runtime_graph_item_metrics_dedupe_repeated_checkpoint_items() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[],
        judge_rows=[],
        llm_rows=[],
        graph_items=[
            runtime_graph_item(),
            runtime_graph_item(),
            runtime_graph_item(
                item_type="entity",
                runtime_item_id="entity:1",
                canonical_id="entity:1",
                canonical_name="Entity",
            ),
        ],
    )

    metrics = runtime_graph_completeness_metrics(rows)

    assert metrics.runtime_graph_item_counts_by_type == {"claim": 1, "entity": 1}


def test_runtime_provider_health_fails_for_terminal_provider_errors_and_fallbacks() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            runtime_checkpoint_row(
                effective_decision_mode="hybrid",
                final_output_source="live_llm",
            )
        ],
        judge_rows=[],
        llm_rows=[
            runtime_extractor_trace(),
            runtime_extractor_trace(
                provider_attempt_status=ProviderAttemptStatus.PROVIDER_ERROR,
                fallback_outcome=FallbackOutcome.SUCCEEDED,
                final_output_source="mixed",
            ),
        ],
        effective_mode="hybrid",
        provider_metadata={
            "backend": "live_provider",
            "provider": "openai",
            "model": "provider_default",
            "timeout_seconds": "60",
            "max_retries": "0",
        },
    )

    health = runtime_provider_health(rows)

    assert health.status == "fail"
    assert health.clean_runtime_gate is False
    assert health.provider_successes == 1
    assert health.provider_failures == 1
    assert health.fallbacks == 1
    assert health.provider_success_rate == 0.5
    assert health.failure_buckets == ["runtime_provider_failure", "runtime_provider_fallback"]
    assert health.failure_classification_counts == {"provider_error": 1}
    assert health.provider_metadata == {
        "backend": "live_provider",
        "max_retries": "0",
        "model": "provider_default",
        "provider": "openai",
        "timeout_seconds": "60",
    }


def test_runtime_provider_health_counts_valid_abstention_as_provider_success() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            runtime_checkpoint_row(
                effective_decision_mode="llm",
                final_output_source="live_llm",
            )
        ],
        judge_rows=[],
        llm_rows=[
            runtime_extractor_trace(
                extraction_status=ExtractionRunStatus.ABSTAINED,
                final_output_source="live_llm",
            )
        ],
        effective_mode="llm",
        provider_metadata={"backend": "live_provider"},
    )

    health = runtime_provider_health(rows)

    assert health.provider_successes == 1
    assert health.provider_failures == 0
    assert health.abstentions == 1
    assert health.failure_classification_counts == {}


def test_runtime_provider_metadata_rejects_credentials() -> None:
    with pytest.raises(ValueError, match="unsupported fields"):
        RuntimeSuiteRows(
            scenario_rows=[],
            checkpoint_rows=[],
            judge_rows=[],
            llm_rows=[],
            provider_metadata={"api_key": "must-not-be-recorded"},
        )


def test_runtime_provider_health_is_not_applicable_to_rule_mode() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[],
        judge_rows=[],
        llm_rows=[],
        effective_mode="rule",
    )

    health = runtime_provider_health(rows)

    assert health.status == "not_applicable"
    assert health.clean_runtime_gate is True
    assert health.provider_success_rate is None


def test_runtime_provider_health_does_not_count_fake_extraction_as_provider_success() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[runtime_checkpoint_row(effective_decision_mode="llm", final_output_source="fake_oracle")],
        judge_rows=[],
        llm_rows=[
            runtime_extractor_trace(
                provider_attempt_status=ProviderAttemptStatus.NOT_ATTEMPTED,
                final_output_source="fake_oracle",
            )
        ],
        effective_mode="llm",
        dry_run=True,
    )

    health = runtime_provider_health(rows)

    assert health.status == "not_applicable"
    assert health.dry_run is True
    assert health.provider_successes == 0
    assert health.fake_extractor_calls == 1
    assert health.execution_source == "fake_oracle"


def test_runtime_output_source_is_scoped_to_the_current_checkpoint_runs() -> None:
    def recorded_run(*, fallback_used: bool) -> RecordedExtractionRun:
        return RecordedExtractionRun(
            input_source_ids=["source:1"],
            provider="hybrid",
            model="test-model",
            prompt_hash="prompt-hash",
            extraction_status=ExtractionRunStatus.SUCCEEDED,
            provider_attempt_status=(
                ProviderAttemptStatus.PROVIDER_ERROR
                if fallback_used
                else ProviderAttemptStatus.SUCCEEDED
            ),
            fallback_outcome=(
                FallbackOutcome.SUCCEEDED if fallback_used else FallbackOutcome.NOT_USED
            ),
            final_output_source=(
                MemoryFinalExtractionSource.FALLBACK
                if fallback_used
                else MemoryFinalExtractionSource.PRIMARY
            ),
            failure_code=None,
            primary_failure_code=(
                ExtractionFailureCode.PROVIDER_ERROR if fallback_used else None
            ),
            fallback_provider="english_rule" if fallback_used else None,
            errors=["fallback_used:provider_failure"] if fallback_used else [],
            entity_count=0,
            claim_count=0,
            action_count=0,
            entity_ids=[],
            claim_ids=[],
            action_ids=[],
            validation_summary={},
        )

    extractor = RecordingMemoryExtractor(delegate=EnglishRuleMemoryExtractor())
    extractor.recorded_runs = [
        recorded_run(fallback_used=True),
        recorded_run(fallback_used=False),
    ]
    assert (
        runtime_final_output_source(
            effective_mode="hybrid",
            dry_run=False,
            extractor=extractor,
            recorded_runs=[extractor.recorded_runs[1]],
        )
        == "live_llm"
    )
    assert (
        runtime_final_output_source(
            effective_mode="hybrid",
            dry_run=False,
            extractor=extractor,
            recorded_runs=extractor.recorded_runs,
        )
        == "mixed"
    )
    assert (
        runtime_final_output_source(
            effective_mode="hybrid",
            dry_run=False,
            extractor=extractor,
            recorded_runs=[],
        )
        == "reused_runtime_state"
    )
