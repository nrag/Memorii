"""Runtime benchmark artifact and report summary helpers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from pydantic import BaseModel

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
    artifact_rows_to_json,
)
from memorii.core.benchmark.artifact_validation import write_json_atomic, write_typed_jsonl
from memorii.core.benchmark.failure_policy import WARNING_ONLY_BUCKET_RATIONALES
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeGraphItemRow, RuntimeSuiteRows


def write_runtime_artifacts(*, run_dir: Path, rows: RuntimeSuiteRows) -> None:
    write_typed_jsonl(run_dir / "runtime_graph_items.jsonl", rows.graph_items, model_type=RuntimeGraphItemRow)
    write_typed_jsonl(run_dir / "runtime_graph_alignments.jsonl", rows.alignments, model_type=RuntimeGraphAlignmentRow)
    write_typed_jsonl(run_dir / "runtime_checkpoint_results.jsonl", rows.checkpoint_rows, model_type=RuntimeCheckpointResultRow)
    write_typed_jsonl(run_dir / "runtime_failures.jsonl", rows.runtime_failures, model_type=RuntimeCheckpointResultRow)
    write_json_atomic(run_dir / "runtime_graph_alignments_summary.json", runtime_alignment_summary(rows))
    snapshots = [snapshot.model_dump(mode="json") for snapshot in rows.graph_snapshots]
    write_json_atomic(run_dir / "runtime_graph_snapshot.json", snapshots)

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


def _json_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, BaseModel):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def _json_sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()

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

def runtime_graph_completeness_metrics(rows: RuntimeSuiteRows) -> RuntimeGraphSummary:
    checkpoint_rows = artifact_rows_to_json(rows.checkpoint_rows)
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
    final_snapshots: dict[str, Mapping[str, object]] = {}
    terminal_snapshot_counts: Counter[str] = Counter()
    has_explicit_terminal = any(_json_mapping(snapshot).get("is_terminal") is True for snapshot in rows.graph_snapshots)
    for raw_snapshot in rows.graph_snapshots:
        snapshot_map = _json_mapping(raw_snapshot)
        scenario_id = str(snapshot_map.get("scenario_id", len(final_snapshots)))
        if snapshot_map.get("is_terminal") is True:
            terminal_snapshot_counts[scenario_id] += 1
            final_snapshots[scenario_id] = snapshot_map
        elif not has_explicit_terminal:
            # Test fixtures and imported artifacts must migrate to explicit
            # terminal markers, but keep deterministic last-row behavior while
            # reporting that the artifact is incomplete.
            final_snapshots[scenario_id] = snapshot_map
        cumulative_graph_edge_count += len(_json_sequence(snapshot_map.get("edges")))
        cumulative_validation_error_count += len(_json_sequence(snapshot_map.get("validation_errors")))
    for snapshot in final_snapshots.values():
        snapshot_map = _json_mapping(snapshot)
        nodes = _json_sequence(snapshot_map.get("nodes"))
        edges = _json_sequence(snapshot_map.get("edges"))
        validation_error_count += len(_json_sequence(snapshot_map.get("validation_errors")))
        graph_edge_count += len(edges)
        node_type_by_id = {str(node.get("node_id")): str(node.get("node_type")) for node in nodes if isinstance(node, Mapping)}
        active_claim_node_ids = {
            str(node.get("node_id"))
            for node in nodes
            if isinstance(node, Mapping) and node.get("node_type") == "claim" and node.get("lifecycle_state") == "active"
        }
        active_action_node_ids = {
            str(node.get("node_id"))
            for node in nodes
            if isinstance(node, Mapping) and node.get("node_type") == "action" and node.get("lifecycle_state") == "active"
        }
        active_claim_count += len(active_claim_node_ids)
        active_action_count += len(active_action_node_ids)
        claim_has_subject: set[str] = set()
        claim_has_object: set[str] = set()
        claim_has_scope: set[str] = set()
        claim_has_observed_in: set[str] = set()
        action_has_observed_in: set[str] = set()
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            node_type = str(node.get("node_type", "unknown"))
            node_counts[node_type] += 1
            if node_type == "source_observation":
                source_observation_count += 1
        for edge in edges:
            if not isinstance(edge, Mapping):
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
    unique_items: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for index, item in enumerate(rows.graph_items):
        item_map = _json_mapping(item)
        scenario_id = str(item_map.get("scenario_id", ""))
        runtime_item_id = str(item_map.get("runtime_item_id", ""))
        # Malformed/fixture rows without identity must remain visible as
        # separate diagnostics; only identified rows can be safely deduped.
        key = (scenario_id, str(item_map.get("item_type", "unknown")), runtime_item_id or str(index))
        unique_items.setdefault(key, item_map)
    item_counts = Counter(str(item.get("item_type", "unknown")) for item in unique_items.values())
    relation_support_modes = Counter()
    for row in checkpoint_rows:
        diagnostics = _json_mapping(row.get("diagnostics"))
        for item in _json_sequence(row.get("runtime_relation_support") or diagnostics.get("runtime_relation_support")):
            if isinstance(item, Mapping):
                relation_support_modes[str(item.get("support_mode", "unknown"))] += 1
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
    checkpoint_rows = artifact_rows_to_json(rows.checkpoint_rows)
    checkpoint_count = len(checkpoint_rows)
    bucket_counts = Counter(
        str(bucket)
        for row in checkpoint_rows
        for bucket in _json_sequence(row.get("runtime_failure_buckets"))
    )
    final_output_source_counts = Counter(str(row.get("final_output_source", "unknown")) for row in checkpoint_rows)
    provider_successes = 0 if rows.dry_run else sum(1 for row in rows.llm_rows if row.success)
    provider_failures = 0 if rows.dry_run else sum(1 for row in rows.llm_rows if not row.success)
    fallbacks = 0 if rows.dry_run else sum(1 for row in rows.llm_rows if row.fallback_used)
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
        long_horizon_slice_counts=ArtifactJsonObject.model_validate(
            _long_horizon_slice_counts(checkpoint_rows)
        ),
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
    provider_successes = 0 if rows.dry_run else sum(1 for row in rows.llm_rows if row.success)
    provider_failures = 0 if rows.dry_run else sum(1 for row in rows.llm_rows if not row.success)
    fallbacks = 0 if rows.dry_run else sum(1 for row in rows.llm_rows if row.fallback_used)
    attempted_calls = provider_successes + provider_failures
    failure_classifications = Counter(
        str(row.trace.failure_classification)
        for row in rows.llm_rows
        if not row.success and row.trace.failure_classification
    )
    failure_buckets: list[str] = []
    if provider_failures:
        failure_buckets.append("runtime_provider_failure")
    if fallbacks:
        failure_buckets.append("runtime_provider_fallback")
    if not provider_backed:
        status: ProviderHealthStatus = "not_applicable"
        clean_runtime_gate = True
        success_rate = None
    else:
        status = "pass" if attempted_calls > 0 and not provider_failures and not fallbacks else "fail"
        clean_runtime_gate = status == "pass"
        success_rate = provider_successes / attempted_calls if attempted_calls else 0.0
    output_sources = {
        str(row.final_output_source)
        for row in rows.checkpoint_rows
        if row.final_output_source
    }
    execution_source = cast(
        FinalOutputSource,
        next(iter(output_sources)) if len(output_sources) == 1 else "mixed",
    )
    metadata: dict[str, str] = {}
    for trace_row in rows.llm_rows:
        for key, value in {
            "provider": trace_row.trace.provider,
            "model": trace_row.trace.model,
            "prompt_hash": trace_row.trace.prompt_hash,
        }.items():
            if value is not None:
                metadata[key] = str(value)
        if metadata:
            break
    return RuntimeProviderHealth(
        effective_decision_mode=effective_mode,
        attempted_calls=attempted_calls,
        provider_successes=provider_successes,
        provider_failures=provider_failures,
        fallbacks=fallbacks,
        provider_success_rate=success_rate,
        status=status,
        clean_runtime_gate=clean_runtime_gate,
        failure_buckets=failure_buckets,
        failure_classification_counts=dict(sorted(failure_classifications.items())),
        execution_source=execution_source,
        dry_run=rows.dry_run,
        fake_extractor_calls=sum(
            1 for row in rows.checkpoint_rows if row.final_output_source == "fake_oracle"
        ),
        provider_metadata=metadata,
        policy={
            "provider_failures": "fail_runtime_gate",
            "fallbacks": "fail_runtime_gate",
            "retry_policy": "use_configured_bounded_client_retries",
            "rule_mode": "not_applicable",
            "dry_run": "not_provider_health",
            "fake_oracle": "never_provider_success",
        },
    )

def runtime_alignment_summary(rows: RuntimeSuiteRows) -> AlignmentSummary:
    checkpoint_rows = artifact_rows_to_json(rows.checkpoint_rows)
    alignments = artifact_rows_to_json(rows.alignments)
    checkpoint_expected_ids: dict[tuple[str, str], set[str]] = {}
    for row in checkpoint_rows:
        expected = _json_mapping(row.get("expected"))
        expected_ids: set[str] = set()
        for key in (
            "expected_entity_ids",
            "expected_claim_ids",
            "expected_relation_ids",
            "expected_action_ids",
            "expected_citation_event_ids",
            "expected_execution_entity_ids",
            "expected_execution_claim_ids",
            "expected_execution_citation_event_ids",
        ):
            expected_ids.update(str(value) for value in _json_sequence(expected.get(key)))
        checkpoint_expected_ids[(str(row.get("scenario_id")), str(row.get("checkpoint_id")))] = expected_ids

    full_counts: Counter[str] = Counter()
    full_item_counts: Counter[str] = Counter()
    required_counts: Counter[str] = Counter()
    required_item_counts: Counter[str] = Counter()
    required_total = 0
    for alignment in alignments:
        if not isinstance(alignment, Mapping):
            continue
        verdict = str(alignment.get("verdict", "unknown"))
        item_type = str(alignment.get("item_type", "unknown"))
        full_counts[verdict] += 1
        full_item_counts[f"{item_type}:{verdict}"] += 1
        key = (str(alignment.get("scenario_id")), str(alignment.get("checkpoint_id")))
        oracle_id = str(alignment.get("oracle_id") or alignment.get("oracle_item_id") or "")
        if oracle_id and oracle_id in checkpoint_expected_ids.get(key, set()):
            required_total += 1
            required_counts[verdict] += 1
            required_item_counts[f"{item_type}:{verdict}"] += 1
    scored_verdict_counts = Counter(str(row.get("verdict", "unknown")) for row in checkpoint_rows)
    scored_failure_bucket_counts = Counter(
        str(bucket)
        for row in checkpoint_rows
        for bucket in _json_sequence(row.get("failure_buckets"))
    )
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
        checkpoint_scored_review_required_count=sum(1 for row in checkpoint_rows if row.get("review_required") is True),
        checkpoint_scored_failure_bucket_counts=dict(sorted(scored_failure_bucket_counts.items())),
        full_graph_audit_alignment_count=len(alignments),
        full_graph_audit_alignment_counts=dict(sorted(full_counts.items())),
        full_graph_audit_alignment_counts_by_item_type=dict(sorted(full_item_counts.items())),
    )

def runtime_warning_policy() -> dict[str, WarningPolicyEntry]:
    return {
        bucket: WarningPolicyEntry(level="warning_only", rationale=rationale)
        for bucket, rationale in sorted(WARNING_ONLY_BUCKET_RATIONALES.items())
    }
