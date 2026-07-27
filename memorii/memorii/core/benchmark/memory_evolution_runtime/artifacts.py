"""Runtime benchmark artifact and report summary helpers."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import cast

from memorii.core.benchmark.artifact_rows import (
    AlignmentSummary,
    ArtifactJsonObject,
    DecisionMode,
    FinalOutputSource,
    ProviderHealthStatus,
    RuntimeCheckpointResultRow,
    RuntimeGraphAlignmentRow,
    RuntimeGraphSummary,
    RuntimeProviderHealth,
    RuntimeReportSummary,
    WarningPolicyEntry,
)
from memorii.core.benchmark.artifact_validation import write_json_atomic, write_typed_jsonl
from memorii.core.benchmark.failure_policy import WARNING_ONLY_BUCKET_RATIONALES
from memorii.core.benchmark.memory_evolution_runtime.ingestion_oracle import (
    IngestionPrefixAuditRow,
)
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeGraphItemRow,
    RuntimeGraphSnapshotRow,
    RuntimeIngestionTraceRow,
    RuntimeSuiteRows,
)
from memorii.core.memory_evolution import (
    ExtractionFailureCode,
    ExtractionRunStatus,
    FallbackOutcome,
    MemoryGraphEdgeType,
    MemoryGraphNodeType,
    ProviderAttemptStatus,
    RecordLifecycleState,
)
from memorii.core.memory_evolution.operation_models import EvolutionOperationStatus


def write_runtime_artifacts(*, run_dir: Path, rows: RuntimeSuiteRows) -> None:
    write_typed_jsonl(run_dir / "runtime_graph_items.jsonl", rows.graph_items, model_type=RuntimeGraphItemRow)
    write_typed_jsonl(run_dir / "runtime_graph_alignments.jsonl", rows.alignments, model_type=RuntimeGraphAlignmentRow)
    write_typed_jsonl(
        run_dir / "runtime_checkpoint_results.jsonl", rows.checkpoint_rows, model_type=RuntimeCheckpointResultRow
    )
    write_typed_jsonl(run_dir / "runtime_failures.jsonl", rows.runtime_failures, model_type=RuntimeCheckpointResultRow)
    write_json_atomic(run_dir / "runtime_graph_alignments_summary.json", runtime_alignment_summary(rows))
    snapshots = [snapshot.model_dump(mode="json") for snapshot in rows.graph_snapshots]
    write_json_atomic(run_dir / "runtime_graph_snapshot.json", snapshots)
    write_typed_jsonl(
        run_dir / "runtime_ingestion_traces.jsonl",
        rows.ingestion_traces,
        model_type=RuntimeIngestionTraceRow,
    )
    write_typed_jsonl(
        run_dir / "runtime_ingestion_prefix_audits.jsonl",
        rows.ingestion_prefix_audits,
        model_type=IngestionPrefixAuditRow,
    )


def horizon_distance_bucket(distance: int | float | object) -> str:
    value = int(distance) if isinstance(distance, (int, float)) else 0
    if value < 5:
        return "short"
    if value < 15:
        return "medium"
    if value < 40:
        return "long"
    return "very_long"


def interference_count_bucket(count: int | float | object) -> str:
    value = int(count) if isinstance(count, (int, float)) else 0
    if value == 0:
        return "none"
    if value < 10:
        return "low"
    if value < 25:
        return "medium"
    return "high"


def source_event_age_days_bucket(days: int | float | object) -> str:
    value = float(days) if isinstance(days, (int, float)) else 0.0
    if value < 7:
        return "fresh"
    if value < 30:
        return "aged"
    if value < 90:
        return "old"
    return "stale_long_horizon"


def _long_horizon_slice_counts(
    checkpoint_rows: list[RuntimeCheckpointResultRow],
) -> dict[str, dict[str, int]]:
    values = {
        "phase": (row.phase for row in checkpoint_rows),
        "horizon_distance_bucket": (row.horizon_distance_bucket for row in checkpoint_rows),
        "interference_count_bucket": (row.interference_count_bucket for row in checkpoint_rows),
        "source_event_age_days_bucket": (row.source_event_age_days_bucket for row in checkpoint_rows),
        "checkpoint_type": (row.checkpoint_type for row in checkpoint_rows),
        "required_retrieval_view": (row.required_retrieval_view for row in checkpoint_rows),
    }
    return {key: dict(sorted(Counter(items).items())) for key, items in values.items()}


def runtime_graph_completeness_metrics(rows: RuntimeSuiteRows) -> RuntimeGraphSummary:
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
    cumulative_graph_edge_count = 0
    cumulative_validation_error_count = 0
    final_snapshots: dict[str, RuntimeGraphSnapshotRow] = {}
    terminal_snapshot_counts: Counter[str] = Counter()
    has_explicit_terminal = any(snapshot.is_terminal for snapshot in rows.graph_snapshots)
    for snapshot in rows.graph_snapshots:
        scenario_id = snapshot.scenario_id
        if snapshot.is_terminal:
            terminal_snapshot_counts[scenario_id] += 1
            final_snapshots[scenario_id] = snapshot
        elif not has_explicit_terminal:
            # Test fixtures and imported artifacts must migrate to explicit
            # terminal markers, but keep deterministic last-row behavior while
            # reporting that the artifact is incomplete.
            final_snapshots[scenario_id] = snapshot
        cumulative_graph_edge_count += len(snapshot.edges)
        cumulative_validation_error_count += len(snapshot.validation_errors)
    for snapshot in final_snapshots.values():
        nodes = snapshot.nodes
        edges = snapshot.edges
        validation_error_count += len(snapshot.validation_errors)
        graph_edge_count += len(edges)
        node_type_by_id = {node.node_id: node.node_type for node in nodes}
        active_claim_node_ids = {
            node.node_id
            for node in nodes
            if node.node_type == MemoryGraphNodeType.CLAIM and node.lifecycle_state == RecordLifecycleState.ACTIVE
        }
        active_action_node_ids = {
            node.node_id
            for node in nodes
            if node.node_type == MemoryGraphNodeType.ACTION and node.lifecycle_state == RecordLifecycleState.ACTIVE
        }
        active_claim_count += len(active_claim_node_ids)
        active_action_count += len(active_action_node_ids)
        claim_has_subject: set[str] = set()
        claim_has_object: set[str] = set()
        claim_has_scope: set[str] = set()
        claim_has_observed_in: set[str] = set()
        action_has_observed_in: set[str] = set()
        for node in nodes:
            node_counts[node.node_type.value] += 1
            if node.node_type == MemoryGraphNodeType.SOURCE_OBSERVATION:
                source_observation_count += 1
        for edge in edges:
            edge_type = edge.edge_type
            edge_counts[edge_type.value] += 1
            source_id = edge.source_node_id
            target_id = edge.target_node_id
            if source_id in active_claim_node_ids:
                if edge_type == MemoryGraphEdgeType.HAS_SUBJECT:
                    claim_has_subject.add(source_id)
                elif edge_type in {MemoryGraphEdgeType.HAS_OBJECT, MemoryGraphEdgeType.HAS_LITERAL_OBJECT}:
                    claim_has_object.add(source_id)
                elif edge_type == MemoryGraphEdgeType.HAS_SCOPE:
                    claim_has_scope.add(source_id)
                elif (
                    edge_type == MemoryGraphEdgeType.OBSERVED_IN
                    and node_type_by_id.get(target_id) == MemoryGraphNodeType.SOURCE_OBSERVATION
                ):
                    claim_has_observed_in.add(source_id)
            if (
                source_id in active_action_node_ids
                and edge_type == MemoryGraphEdgeType.OBSERVED_IN
                and node_type_by_id.get(target_id) == MemoryGraphNodeType.SOURCE_OBSERVATION
            ):
                action_has_observed_in.add(source_id)
        claim_subject_count += len(claim_has_subject)
        claim_object_count += len(claim_has_object)
        claim_scope_count += len(claim_has_scope)
        claim_observed_in_count += len(claim_has_observed_in)
        action_observed_in_count += len(action_has_observed_in)
    unique_items: dict[tuple[str, str, str], RuntimeGraphItemRow] = {}
    for index, item in enumerate(rows.graph_items):
        key = (item.scenario_id, item.item_type, item.runtime_item_id or str(index))
        unique_items.setdefault(key, item)
    item_counts = Counter(item.item_type for item in unique_items.values())
    relation_support_modes = Counter()
    for row in rows.checkpoint_rows:
        for item in row.diagnostics.runtime_relation_support:
            relation_support_modes[item.support_mode] += 1
    return RuntimeGraphSummary(
        source_observation_count=source_observation_count,
        entity_count=node_counts.get("entity", 0),
        claim_count=node_counts.get("claim", 0),
        action_count=node_counts.get("action", 0),
        relation_item_count=item_counts.get("relation", 0),
        action_item_count=item_counts.get("action", 0),
        graph_edge_count=graph_edge_count,
        graph_edge_counts_by_type=dict(sorted(edge_counts.items())),
        runtime_graph_node_counts_by_type=dict(sorted(node_counts.items())),
        runtime_graph_item_counts_by_type=dict(sorted(item_counts.items())),
        runtime_relation_support_modes=dict(sorted(relation_support_modes.items())),
        evidence_edge_count=edge_counts.get("observed_in", 0),
        active_claim_count=active_claim_count,
        active_claim_with_subject_count=claim_subject_count,
        active_claim_with_object_or_literal_count=claim_object_count,
        active_claim_with_scope_count=claim_scope_count,
        active_claim_with_observed_in_count=claim_observed_in_count,
        active_action_count=active_action_count,
        active_action_with_observed_in_count=action_observed_in_count,
        active_claim_with_subject_rate=claim_subject_count / max(1, active_claim_count),
        active_claim_with_object_or_literal_rate=claim_object_count / max(1, active_claim_count),
        active_claim_with_scope_rate=claim_scope_count / max(1, active_claim_count),
        active_claim_with_observed_in_rate=claim_observed_in_count / max(1, active_claim_count),
        active_action_with_observed_in_rate=action_observed_in_count / max(1, active_action_count),
        runtime_graph_validation_error_count=validation_error_count,
        snapshot_count=len(final_snapshots),
        aggregation_scope="final_snapshot_per_scenario",
        cumulative_graph_edge_count=cumulative_graph_edge_count,
        cumulative_validation_error_count=cumulative_validation_error_count,
        terminal_snapshot_count=sum(terminal_snapshot_counts.values()),
        terminal_snapshot_anomaly_count=(
            sum(1 for count in terminal_snapshot_counts.values() if count != 1)
            if has_explicit_terminal
            else len(final_snapshots)
        ),
    )


def runtime_summary_metrics(rows: RuntimeSuiteRows) -> RuntimeReportSummary:
    checkpoint_rows = rows.checkpoint_rows
    checkpoint_count = len(checkpoint_rows)
    bucket_counts = Counter(bucket for row in checkpoint_rows for bucket in row.runtime_failure_buckets)
    final_output_source_counts = Counter(row.final_output_source for row in checkpoint_rows)
    extraction_successes = (
        0
        if rows.dry_run
        else sum(row.provider_attempt_status == ProviderAttemptStatus.SUCCEEDED for row in rows.llm_rows)
    )
    extraction_failures = 0 if rows.dry_run else _provider_failure_count(rows)
    query_calls, query_failures = _structured_query_call_counts(rows)
    provider_successes = extraction_successes + query_calls - query_failures
    provider_failures = extraction_failures + query_failures
    fallbacks = 0 if rows.dry_run else sum(row.fallback_outcome != FallbackOutcome.NOT_USED for row in rows.llm_rows)
    graph_summary = runtime_graph_completeness_metrics(rows)
    alignment_summary = runtime_alignment_summary(rows)
    return RuntimeReportSummary(
        runtime_checkpoint_count=checkpoint_count,
        runtime_failure_bucket_counts=dict(sorted(bucket_counts.items())),
        provider_successes=provider_successes,
        provider_failures=provider_failures,
        fallbacks=fallbacks,
        final_output_source_counts=dict(sorted(final_output_source_counts.items())),
        runtime_alignment_count=len(rows.alignments),
        runtime_graph_item_count=sum(graph_summary.runtime_graph_item_counts_by_type.values()),
        runtime_graph_item_observation_count=len(rows.graph_items),
        runtime_graph_summary=graph_summary,
        runtime_graph_alignments_summary=alignment_summary,
        long_horizon_slice_counts=ArtifactJsonObject.model_validate(_long_horizon_slice_counts(checkpoint_rows)),
        runtime_provider_health=runtime_provider_health(rows),
    )


def runtime_provider_health(rows: RuntimeSuiteRows) -> RuntimeProviderHealth:
    """Return the explicit provider gate for a runtime benchmark run.

    The configured LLM client already applies bounded retries. This report
    distinguishes a clean provider-backed run from a terminal provider,
    schema, or fallback failure without adding another retry layer.
    """

    effective_mode = cast(DecisionMode | None, rows.effective_mode)
    if effective_mode is None:
        effective_modes = {
            str(row.effective_decision_mode)
            for row in rows.checkpoint_rows
            if row.effective_decision_mode in {"rule", "llm", "hybrid"}
        }
        effective_mode = cast(
            DecisionMode | None,
            next(iter(effective_modes), None) if len(effective_modes) == 1 else None,
        )
    provider_backed = effective_mode in {"llm", "hybrid"} and not rows.dry_run
    extraction_successes = (
        0
        if rows.dry_run
        else sum(row.provider_attempt_status == ProviderAttemptStatus.SUCCEEDED for row in rows.llm_rows)
    )
    extraction_failures = 0 if rows.dry_run else _provider_failure_count(rows)
    query_calls, query_failures = _structured_query_call_counts(rows)
    provider_successes = extraction_successes + query_calls - query_failures
    provider_failures = extraction_failures + query_failures
    fallbacks = 0 if rows.dry_run else sum(row.fallback_outcome != FallbackOutcome.NOT_USED for row in rows.llm_rows)
    extraction_attempted_calls = extraction_successes + extraction_failures
    attempted_calls = extraction_attempted_calls + query_calls
    requested_model = rows.provider_metadata.get("model")
    model_identity_mismatches = (
        0
        if not provider_backed or not requested_model
        else sum(
            row.trace.requested_model != requested_model
            or not _actual_model_matches_requested(
                requested_model,
                row.trace.actual_model,
            )
            for row in rows.llm_rows
            if row.provider_attempt_status != ProviderAttemptStatus.NOT_ATTEMPTED
        )
    )
    provider_attempt_status_counts = Counter(row.provider_attempt_status.value for row in rows.llm_rows)
    provider_attempt_status_counts.update(
        {
            "structured_query_succeeded": query_calls - query_failures,
            "structured_query_failed": query_failures,
        }
    )
    extraction_status_counts = Counter(row.extraction_status.value for row in rows.llm_rows)
    fallback_outcome_counts = Counter(row.fallback_outcome.value for row in rows.llm_rows)
    failure_classifications = Counter(
        failure.value
        for row in rows.llm_rows
        for failure in (row.primary_failure_code, row.failure_code)
        if failure is not None
    )
    output_validation_failures = sum(
        row.failure_code == ExtractionFailureCode.OUTPUT_VALIDATION for row in rows.llm_rows
    )
    abstentions = sum(row.extraction_status == ExtractionRunStatus.ABSTAINED for row in rows.llm_rows)
    partial_extractions = sum(row.extraction_status == ExtractionRunStatus.PARTIAL for row in rows.llm_rows)
    operation_status_counts = Counter(
        row.operation_status.value for row in rows.llm_rows if row.operation_status is not None
    )
    operation_failure_classifications = Counter(
        row.operation_failure_code.value for row in rows.llm_rows if row.operation_failure_code is not None
    )
    operation_outcome_count = sum(operation_status_counts.values())
    committed_operations = operation_status_counts[EvolutionOperationStatus.COMMITTED.value]
    failed_operations = operation_status_counts[EvolutionOperationStatus.FAILED.value]
    missing_operation_outcomes = sum(row.operation_status is None for row in rows.llm_rows)
    failure_buckets: list[str] = []
    if provider_failures:
        failure_buckets.append("runtime_provider_failure")
    if fallbacks:
        failure_buckets.append("runtime_provider_fallback")
    if output_validation_failures:
        failure_buckets.append("runtime_output_validation_failure")
    if partial_extractions:
        failure_buckets.append("runtime_partial_extraction")
    if failed_operations:
        failure_buckets.append("runtime_evolution_operation_failure")
    if missing_operation_outcomes:
        failure_buckets.append("runtime_missing_evolution_outcome")
    if model_identity_mismatches:
        failure_buckets.append("runtime_provider_model_mismatch")
    nonterminal_operations = operation_outcome_count - committed_operations - failed_operations
    if nonterminal_operations:
        failure_buckets.append("runtime_nonterminal_evolution_outcome")
    if not provider_backed:
        status: ProviderHealthStatus = "not_applicable"
        clean_runtime_gate = True
        success_rate = None
    else:
        status = (
            "pass"
            if attempted_calls > 0
            and not provider_failures
            and not fallbacks
            and not output_validation_failures
            and not partial_extractions
            and not failed_operations
            and not missing_operation_outcomes
            and not nonterminal_operations
            and not model_identity_mismatches
            else "fail"
        )
        clean_runtime_gate = status == "pass"
        success_rate = provider_successes / attempted_calls if attempted_calls else 0.0
    output_sources = {str(row.final_output_source) for row in rows.checkpoint_rows if row.final_output_source}
    execution_source = cast(
        FinalOutputSource,
        next(iter(output_sources)) if len(output_sources) == 1 else "mixed",
    )
    return RuntimeProviderHealth(
        effective_decision_mode=effective_mode,
        attempted_calls=attempted_calls,
        extraction_attempted_calls=extraction_attempted_calls,
        structured_query_attempted_calls=query_calls,
        structured_query_failures=query_failures,
        model_identity_mismatches=model_identity_mismatches,
        provider_successes=provider_successes,
        provider_failures=provider_failures,
        fallbacks=fallbacks,
        provider_success_rate=success_rate,
        status=status,
        clean_runtime_gate=clean_runtime_gate,
        failure_buckets=failure_buckets,
        failure_classification_counts=dict(sorted(failure_classifications.items())),
        provider_attempt_status_counts=dict(sorted(provider_attempt_status_counts.items())),
        extraction_status_counts=dict(sorted(extraction_status_counts.items())),
        fallback_outcome_counts=dict(sorted(fallback_outcome_counts.items())),
        output_validation_failures=output_validation_failures,
        abstentions=abstentions,
        partial_extractions=partial_extractions,
        operation_outcome_count=operation_outcome_count,
        committed_operations=committed_operations,
        failed_operations=failed_operations,
        missing_operation_outcomes=missing_operation_outcomes,
        operation_status_counts=dict(sorted(operation_status_counts.items())),
        operation_failure_classification_counts=dict(sorted(operation_failure_classifications.items())),
        execution_source=execution_source,
        dry_run=rows.dry_run,
        fake_extractor_calls=sum(1 for row in rows.checkpoint_rows if row.final_output_source == "fake_oracle"),
        provider_metadata=dict(sorted(rows.provider_metadata.items())),
        policy={
            "provider_failures": "fail_runtime_gate",
            "fallbacks": "fail_runtime_gate",
            "retry_policy": "use_configured_bounded_client_retries",
            "rule_mode": "not_applicable",
            "dry_run": "not_provider_health",
            "fake_oracle": "never_provider_success",
            "operation_outcome": "require_committed_for_every_extraction",
            "model_identity": "require_requested_model_or_dated_snapshot",
        },
    )


def _actual_model_matches_requested(
    requested_model: str,
    actual_model: str | None,
) -> bool:
    if actual_model is None:
        return False
    return (
        actual_model == requested_model
        or re.fullmatch(
            rf"{re.escape(requested_model)}-\d{{4}}-\d{{2}}-\d{{2}}",
            actual_model,
        )
        is not None
    )


def _provider_failure_count(rows: RuntimeSuiteRows) -> int:
    failure_statuses = {
        ProviderAttemptStatus.PROVIDER_ERROR,
        ProviderAttemptStatus.INVALID_JSON,
        ProviderAttemptStatus.SCHEMA_ERROR,
    }
    return sum(row.provider_attempt_status in failure_statuses for row in rows.llm_rows)


def _structured_query_call_counts(rows: RuntimeSuiteRows) -> tuple[int, int]:
    if rows.dry_run:
        return 0, 0
    analyses = [
        decision.query_analysis
        for row in rows.checkpoint_rows
        if (decision := row.diagnostics.runtime_retrieval_decision) is not None and decision.query_analysis is not None
    ]
    calls = sum(analysis.structured_query_call_count for analysis in analyses)
    failures = sum(
        analysis.structured_query_call_count
        for analysis in analyses
        if analysis.failure_code is not None or analysis.provider_error is not None
    )
    return calls, failures


def runtime_alignment_summary(rows: RuntimeSuiteRows) -> AlignmentSummary:
    checkpoint_expected_ids: dict[tuple[str, str], set[str]] = {}
    for row in rows.checkpoint_rows:
        expected = row.expected
        expected_ids: set[str] = set()
        for values in (
            expected.expected_entity_ids,
            expected.expected_claim_ids,
            expected.expected_relation_ids,
            expected.expected_action_ids,
            expected.expected_citation_event_ids,
            expected.expected_execution_entity_ids,
            expected.expected_execution_claim_ids,
            expected.expected_execution_citation_event_ids,
        ):
            expected_ids.update(values)
        checkpoint_expected_ids[(row.scenario_id, row.checkpoint_id)] = expected_ids

    full_counts: Counter[str] = Counter()
    full_item_counts: Counter[str] = Counter()
    required_counts: Counter[str] = Counter()
    required_item_counts: Counter[str] = Counter()
    required_total = 0
    for alignment in rows.alignments:
        verdict = alignment.verdict
        item_type = alignment.item_type
        full_counts[verdict] += 1
        full_item_counts[f"{item_type}:{verdict}"] += 1
        key = (alignment.scenario_id, alignment.checkpoint_id)
        oracle_id = alignment.oracle_id
        if oracle_id and oracle_id in checkpoint_expected_ids.get(key, set()):
            required_total += 1
            required_counts[verdict] += 1
            required_item_counts[f"{item_type}:{verdict}"] += 1
    scored_verdict_counts = Counter(row.verdict for row in rows.checkpoint_rows)
    scored_verdict_counts = Counter({"pass": scored_verdict_counts["pass"], "fail": scored_verdict_counts["fail"]})
    scored_failure_bucket_counts = Counter(bucket for row in rows.checkpoint_rows for bucket in row.failure_buckets)
    return AlignmentSummary(
        alignment_summary_policy={
            "checkpoint_expected_alignment_audit": "Diagnostic-only alignment of checkpoint expected ids against runtime graph items; partial, ambiguous_alignment, and unmatched_runtime are not failures unless reflected in checkpoint_scored_* fields.",
            "full_graph_audit_alignment": "Diagnostic-only alignment over the broader recoverable latent graph slice.",
            "checkpoint_scored": "Authoritative checkpoint pass/fail/review interpretation copied from judged checkpoint rows.",
        },
        checkpoint_expected_alignment_audit_count=required_total,
        checkpoint_expected_alignment_audit_counts=dict(sorted(required_counts.items())),
        checkpoint_expected_alignment_audit_counts_by_item_type=dict(sorted(required_item_counts.items())),
        checkpoint_scored_verdict_counts=dict(sorted(scored_verdict_counts.items())),
        checkpoint_scored_review_required_count=sum(1 for row in rows.checkpoint_rows if row.review_required),
        checkpoint_scored_failure_bucket_counts=dict(sorted(scored_failure_bucket_counts.items())),
        full_graph_audit_alignment_count=len(rows.alignments),
        full_graph_audit_alignment_counts=dict(sorted(full_counts.items())),
        full_graph_audit_alignment_counts_by_item_type=dict(sorted(full_item_counts.items())),
    )


def runtime_warning_policy() -> dict[str, WarningPolicyEntry]:
    return {
        bucket: WarningPolicyEntry(level="warning_only", rationale=rationale)
        for bucket, rationale in sorted(WARNING_ONLY_BUCKET_RATIONALES.items())
    }
