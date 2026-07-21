"""Shared artifact aggregation and persistence for memory-evolution suites."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from memorii.core.benchmark.artifact_rows import (
    ArtifactJsonObject,
    BenchmarkReportSummary,
    BenchmarkSuiteName,
    DecisionMode,
    FinalOutputSource,
    JudgeVoteRow,
    RuntimeExtractorTraceRow,
    RuntimeReportSummary,
    SimCheckpointResultRow,
    SimLLMTraceRow,
    SimScenarioResultRow,
    ValidationScenarioCatalogRow,
    WarningExampleRow,
    WarningPolicyEntry,
    artifact_rows_to_json,
    execution_source_from_counts,
)
from memorii.core.benchmark.artifact_validation import (
    write_json_atomic,
    write_text_atomic,
    write_typed_jsonl,
)
from memorii.core.benchmark.calibration.models import CalibrationEvent
from memorii.core.benchmark.calibration.reports import build_calibration_artifacts
from memorii.core.benchmark.failure_policy import (
    WARNING_ONLY_BUCKET_RATIONALES,
    is_critical_failure_bucket,
)
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    LatentGraphScenario,
    sim_metrics_from_rows,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.models import BenchmarkRunConfig
from memorii.core.benchmark.reproducibility import (
    build_benchmark_fingerprint,
    build_run_id,
    build_source_tree_fingerprint,
    resolve_source_revision,
    resolve_source_state,
)
from memorii.tools.benchmark_suites.artifact_io import write_jsonl

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
LLMArtifactRow = SimLLMTraceRow | RuntimeExtractorTraceRow


def _mapping_has_values(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return any(bool(item) for item in value.values())


def write_memory_evolution_artifacts(
    *,
    scenarios: list[LatentGraphScenario],
    scenario_rows: Sequence[SimScenarioResultRow],
    checkpoint_rows: Sequence[SimCheckpointResultRow],
    judge_rows: Sequence[JudgeAggregate],
    llm_rows: Sequence[LLMArtifactRow],
    suite: str,
    mode: str,
    storage_root: str,
    fixture_source: str,
    args: argparse.Namespace,
    runtime_report: RuntimeReportSummary | None = None,
    warning_policy: Mapping[str, WarningPolicyEntry] | None = None,
) -> Path:
    """Persist the common memory-evolution artifact contract for both suites."""
    benchmark_key = build_run_id(
        config=BenchmarkRunConfig(seed=args.seed, run_label=f"{suite}_{mode}_{args.sim_profile}"),
        fixtures=[],
    )
    replicate_key = f"rep{args.inference_replicate}"
    run_id = (
        f"{benchmark_key}-{replicate_key}"
        if args.dry_run
        else f"{benchmark_key}-{replicate_key}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    run_dir = Path(storage_root) / "benchmark_runs" / suite / mode / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in scenario_rows if row.success)
    failed = len(scenario_rows) - passed
    failure_bucket_counts = Counter(str(bucket) for row in checkpoint_rows for bucket in row.failure_buckets)
    warning_bucket_counts = Counter(
        str(bucket)
        for row in judge_rows
        for vote in row.votes
        if vote.verdict.value == "pass"
        for bucket in vote.failure_buckets
    )
    graph_answer_optional_missing_count = sum(
        1 for row in checkpoint_rows if row.answer_match_type == "optional_missing"
    )
    extra_context_provenance_count = sum(1 for row in checkpoint_rows if _sim_row_has_extra_context_provenance(row))
    if extra_context_provenance_count:
        warning_bucket_counts["extra_context_provenance"] += extra_context_provenance_count
    supporting_pollution_count = sum(
        1 for row in checkpoint_rows if row.supporting_excluded_ids or row.supporting_noisy_citation_event_ids
    )
    selected_pollution_count = sum(
        1
        for row in checkpoint_rows
        if row.selected_excluded_ids or row.selected_noncurrent_claim_ids or row.selected_entity_role_mismatches
    )
    warning_examples = _sim_warning_examples(checkpoint_rows)
    review_bucket_counts = Counter(
        str(bucket)
        for row in checkpoint_rows
        if _sim_row_needs_review(row)
        for bucket in [*row.failure_buckets, *row.precision_failure_classification]
    )
    required_judge_failures = sum(
        1
        for row in judge_rows
        for vote in row.votes
        if vote.verdict.value == "fail" and vote.judge_id in set(row.required_judge_ids)
    )
    judge_coverage = {
        "votes": sum(len(row.votes) for row in judge_rows),
        "abstentions": sum(1 for row in judge_rows for vote in row.votes if vote.verdict.value == "abstain"),
        "failures": sum(1 for row in judge_rows for vote in row.votes if vote.verdict.value == "fail"),
        "required_judge_failures": required_judge_failures,
        "review_required": sum(1 for row in checkpoint_rows if row.review_required),
    }
    fixture_payload = [scenario.model_dump(mode="json") for scenario in scenarios]
    latent_graph_json = json.dumps(fixture_payload, indent=2, sort_keys=True)
    surface_rows = [
        observation.model_dump(mode="json") for scenario in scenarios for observation in scenario.observations
    ]
    checkpoint_payload = [
        checkpoint.model_dump(mode="json") for scenario in scenarios for checkpoint in scenario.checkpoints
    ]
    validation_scenario_catalog = [
        ValidationScenarioCatalogRow(
            scenario_id=scenario.scenario_id,
            semantic_world_fingerprint=scenario.semantic_world_fingerprint,
            family=scenario.family,
            profile=scenario.profile,
            observation_count=len(scenario.observations),
            checkpoint_count=len(scenario.checkpoints),
            checkpoint_types=sorted({checkpoint.checkpoint_type for checkpoint in scenario.checkpoints}),
            difficulty_tags=sorted({tag for checkpoint in scenario.checkpoints for tag in checkpoint.difficulty_tags}),
            phase_counts=dict(sorted(Counter(observation.phase for observation in scenario.observations).items())),
            max_horizon_distance=max((checkpoint.horizon_distance for checkpoint in scenario.checkpoints), default=0),
            max_interference_count=max(
                (checkpoint.interference_count for checkpoint in scenario.checkpoints), default=0
            ),
            hidden_item_count=sum(
                1
                for collection_name in ("entities", "claims", "relations")
                for item in getattr(scenario, collection_name)
                if getattr(item, "observability", None) == "hidden"
            ),
            observed_claim_count=sum(
                1 for claim in scenario.claims if getattr(claim, "observability", None) == "observed"
            ),
            inferable_claim_count=sum(
                1 for claim in scenario.claims if getattr(claim, "observability", None) == "inferable"
            ),
        )
        for scenario in scenarios
    ]
    candidate_card_payload = [
        sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint).model_dump(mode="json")
        for scenario in scenarios
        for checkpoint in scenario.checkpoints
    ]
    surface_jsonl = "\n".join(json.dumps(row, sort_keys=True) for row in surface_rows)
    checkpoint_jsonl = "\n".join(json.dumps(row, sort_keys=True) for row in checkpoint_payload)
    candidate_card_jsonl = "\n".join(json.dumps(row, sort_keys=True) for row in candidate_card_payload)
    fixture_hashes = {
        "latent_graphs": hashlib.sha256(latent_graph_json.encode("utf-8")).hexdigest(),
        "surface_observations": hashlib.sha256(surface_jsonl.encode("utf-8")).hexdigest(),
        "oracle_checkpoints": hashlib.sha256(checkpoint_jsonl.encode("utf-8")).hexdigest(),
        "candidate_cards": hashlib.sha256(candidate_card_jsonl.encode("utf-8")).hexdigest(),
    }
    fixture_fingerprint_config: dict[str, object] = {
        "profile": args.sim_profile,
        "scenario_count": args.sim_scenario_count,
        "min_events": args.sim_min_events,
        "max_events": args.sim_max_events,
        "noise_rate": args.sim_noise_rate,
        "fixture_source": fixture_source.split(":seed=", 1)[0],
        # Fixture hashes are retained in the report as per-seed evidence. The
        # generated fixture contents intentionally vary by seed, so they must
        # not participate in the seed-invariant gate configuration fingerprint.
        "fixture_contract": "memory_evolution_surface_contract_v1",
        "source_hash": build_source_tree_fingerprint(
            root=_PROJECT_ROOT,
            relative_paths=[
                "memorii/core/benchmark/memory_evolution_sim/generation.py",
                "memorii/core/benchmark/memory_evolution_sim/schemas.py",
            ],
        ),
    }
    evaluation_fingerprint_config: dict[str, object] = {
        "suite": suite,
        "evaluation_contract": "memory_evolution_judges_v1",
        "failure_policy_contract": "fail_closed_v1",
        "artifact_contract": 1,
        "source_hash": build_source_tree_fingerprint(
            root=_PROJECT_ROOT,
            relative_paths=[
                "memorii/core/benchmark/artifact_rows",
                "memorii/core/benchmark/artifact_validation.py",
                "memorii/core/benchmark/failure_policy.py",
                "memorii/core/benchmark/memory_evolution_sim/diagnostics.py",
                "memorii/core/benchmark/memory_evolution_sim/judges.py",
                "memorii/core/benchmark/memory_evolution_sim/schemas.py",
                "memorii/core/benchmark/memory_evolution_sim/utils.py",
                "memorii/core/benchmark/calibration",
                *(
                    [
                        "memorii/core/benchmark/memory_evolution_runtime/alignment.py",
                        "memorii/core/benchmark/memory_evolution_runtime/artifacts.py",
                        "memorii/core/benchmark/memory_evolution_runtime/checkpoint_projection.py",
                    ]
                    if runtime_report is not None
                    else []
                ),
            ],
        ),
    }
    source_revision = resolve_source_revision(root=_PROJECT_ROOT, dry_run=args.dry_run)
    source_state = resolve_source_state(root=_PROJECT_ROOT)
    source_tree_digest = build_source_tree_fingerprint(
        root=_PROJECT_ROOT,
        relative_paths=["memorii", "pyproject.toml"],
    )
    system_fingerprint_config: dict[str, object] = {
        "mode": mode,
        "source_revision": source_revision,
        "source_hash": source_tree_digest,
        # Rendered hashes include seed-specific context. Prompt refs identify
        # the stable system contract; per-call hashes remain in llm traces.
        "prompt_contract_refs": sorted(
            {prompt_ref for row in llm_rows if (prompt_ref := _trace_prompt_ref(row)) is not None}
        ),
        "provider_models": sorted({model for row in llm_rows if (model := _trace_model(row)) is not None}),
        "providers": sorted({provider for row in llm_rows if (provider := _trace_provider(row)) is not None}),
    }
    if runtime_report is not None:
        metadata = runtime_report.runtime_provider_health.provider_metadata
        system_fingerprint_config["provider_metadata"] = {
            key: metadata[key] for key in ("provider", "model") if key in metadata
        }
    final_output_source_counts = Counter(row.final_output_source for row in checkpoint_rows)
    llm_successes = sum(1 for row in llm_rows if row.success)
    provider_successes = (
        runtime_report.provider_successes if runtime_report is not None else 0 if args.dry_run else llm_successes
    )
    provider_failures = (
        runtime_report.provider_failures
        if runtime_report is not None
        else 0
        if args.dry_run
        else len(llm_rows) - llm_successes
    )
    fake_calls = len(llm_rows) if args.dry_run else 0
    fallbacks = (
        runtime_report.fallbacks
        if runtime_report is not None
        else 0
        if args.dry_run
        else sum(1 for row in checkpoint_rows if row.fallback_used)
    )
    hidden_item_count = sum(
        1
        for scenario in scenarios
        for collection_name in ("entities", "claims", "relations")
        for item in getattr(scenario, collection_name)
        if getattr(item, "observability", None) == "hidden"
    )
    hidden_pressure_checkpoint_count = len(checkpoint_rows) if hidden_item_count else 0
    base_metrics = sim_metrics_from_rows(checkpoint_rows)
    base_metrics.update(
        {
            "hidden_item_count": float(hidden_item_count),
            "hidden_pressure_checkpoint_count": float(hidden_pressure_checkpoint_count),
            "hidden_answer_leak_rate": (
                sum(1 for row in checkpoint_rows if "hidden_fact_answer_leak" in set(row.failure_buckets))
                / max(1, len(checkpoint_rows))
            ),
            "graph_answer_optional_missing_count": float(graph_answer_optional_missing_count),
            "extra_context_provenance_count": float(extra_context_provenance_count),
            "extra_context_provenance_rate": extra_context_provenance_count / max(1, len(checkpoint_rows)),
            "supporting_pollution_count": float(supporting_pollution_count),
            "selected_pollution_count": float(selected_pollution_count),
        }
    )
    calibration_events, calibration_report, calibration_slices, decision_cost_report = build_calibration_artifacts(
        suite=suite,
        profile=args.sim_profile,
        checkpoint_rows=list(checkpoint_rows),
    )
    runtime_metric_scalars: dict[str, object] = {}
    if runtime_report is not None:
        runtime_metric_scalars = {
            "runtime_checkpoint_count": runtime_report.runtime_checkpoint_count,
            "runtime_alignment_count": runtime_report.runtime_alignment_count,
            "runtime_graph_item_count": runtime_report.runtime_graph_item_count,
            "runtime_graph_item_observation_count": runtime_report.runtime_graph_item_observation_count,
            "provider_successes": runtime_report.provider_successes,
            "provider_failures": runtime_report.provider_failures,
            "fallbacks": runtime_report.fallbacks,
        }
    execution_source = execution_source_from_counts(final_output_source_counts)
    if (
        runtime_report is not None
        and runtime_report.runtime_provider_health.execution_source != execution_source
    ):
        raise ValueError("runtime provider health disagrees with checkpoint output sources")
    long_horizon_slices = (
        runtime_report.long_horizon_slice_counts
        if runtime_report is not None
        else ArtifactJsonObject.model_validate(_long_horizon_slice_counts(checkpoint_rows))
    )
    effective_warning_policy = {
        bucket: WarningPolicyEntry(level="warning_only", rationale=rationale)
        for bucket, rationale in sorted(WARNING_ONLY_BUCKET_RATIONALES.items())
    }
    effective_warning_policy.update(warning_policy or {})
    report_model = BenchmarkReportSummary(
        suite=cast(BenchmarkSuiteName, suite),
        mode=cast(DecisionMode, mode),
        profile=args.sim_profile,
        seed=args.seed,
        benchmark_key=benchmark_key,
        fixture_fingerprint=build_benchmark_fingerprint(fixture_fingerprint_config),
        evaluation_fingerprint=build_benchmark_fingerprint(evaluation_fingerprint_config),
        system_fingerprint=build_benchmark_fingerprint(system_fingerprint_config),
        source_revision=source_revision,
        source_tree_digest=source_tree_digest,
        source_state=source_state,
        report_content_digest="0" * 64,
        artifact_manifest_digest="0" * 64,
        inference_replicate=args.inference_replicate,
        run_id=run_id,
        generated_at=datetime.now(UTC).isoformat(),
        fixture_source=fixture_source,
        fixture_hashes=fixture_hashes,
        scenario_count=len(scenario_rows),
        validation_scenario_catalog=validation_scenario_catalog,
        event_count=sum(len(scenario.observations) for scenario in scenarios),
        checkpoint_count=len(checkpoint_rows),
        passed=passed,
        failed=failed,
        llm_calls=len(llm_rows),
        provider_successes=provider_successes,
        provider_failures=provider_failures,
        fallbacks=fallbacks,
        fake_calls=fake_calls,
        dry_run=args.dry_run,
        execution_source=cast(FinalOutputSource, execution_source),
        final_output_source_counts=dict(sorted(final_output_source_counts.items())),
        hidden_item_count=hidden_item_count,
        hidden_hallucination_rate=float(base_metrics["hidden_hallucination_rate"]),
        hidden_answer_leak_rate=float(base_metrics["hidden_answer_leak_rate"]),
        metrics=ArtifactJsonObject(root={**base_metrics, **runtime_metric_scalars}),
        long_horizon_slice_counts=long_horizon_slices,
        calibration=calibration_report,
        decision_quality=decision_cost_report,
        failure_bucket_counts=dict(sorted(failure_bucket_counts.items())),
        critical_failure_bucket_counts=dict(
            sorted(
                (bucket, count) for bucket, count in failure_bucket_counts.items() if is_critical_failure_bucket(bucket)
            )
        ),
        warning_bucket_counts=dict(sorted(warning_bucket_counts.items())),
        review_bucket_counts=dict(sorted(review_bucket_counts.items())),
        judge_metrics=ArtifactJsonObject.model_validate(judge_coverage),
        baseline_scores=ArtifactJsonObject(root={}),
        artifact_version=1,
        scenario_results=list(scenario_rows),
        checkpoint_results=list(checkpoint_rows),
        runtime=runtime_report,
        runtime_graph_summary=(runtime_report.runtime_graph_summary if runtime_report is not None else None),
        runtime_graph_alignments_summary=(
            runtime_report.runtime_graph_alignments_summary if runtime_report is not None else None
        ),
        runtime_failure_bucket_counts=(
            runtime_report.runtime_failure_bucket_counts if runtime_report is not None else {}
        ),
        runtime_provider_health=(runtime_report.runtime_provider_health if runtime_report is not None else None),
        warning_policy=effective_warning_policy,
    )
    report = report_model.to_json_row()
    report_md = (
        f"# {suite}\n\n"
        f"mode={mode} profile={args.sim_profile} scenarios={len(scenario_rows)} "
        f"events={report['event_count']} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} llm_calls={len(llm_rows)}\n"
    )
    write_json_atomic(run_dir / "report.json", report)
    write_text_atomic(run_dir / "report.md", report_md)
    latent_graph_payload = json.loads(latent_graph_json)
    write_json_atomic(run_dir / "fixtures.json", latent_graph_payload)
    write_json_atomic(run_dir / "latent_graphs.json", latent_graph_payload)
    write_jsonl(
        run_dir / "world_transitions.jsonl",
        [transition.model_dump(mode="json") for scenario in scenarios for transition in scenario.transitions],
    )
    write_jsonl(
        run_dir / "surface_observations.jsonl",
        surface_rows,
    )
    write_jsonl(
        run_dir / "oracle_checkpoints.jsonl",
        checkpoint_payload,
    )
    write_jsonl(run_dir / "candidate_cards.jsonl", candidate_card_payload)
    write_json_atomic(
        run_dir / "validation_scenario_catalog.json",
        artifact_rows_to_json(validation_scenario_catalog),
    )
    write_typed_jsonl(run_dir / "sim_checkpoint_results.jsonl", checkpoint_rows, model_type=SimCheckpointResultRow)
    write_typed_jsonl(run_dir / "calibration_events.jsonl", calibration_events, model_type=CalibrationEvent)
    write_json_atomic(run_dir / "calibration_report.json", calibration_report)
    write_json_atomic(run_dir / "slice_calibration_report.json", calibration_slices)
    write_json_atomic(run_dir / "decision_quality_report.json", decision_cost_report)
    judge_vote_rows = [
        JudgeVoteRow.from_vote(vote) for row in judge_rows for vote in row.votes
    ]
    write_typed_jsonl(run_dir / "judge_votes.jsonl", judge_vote_rows, model_type=JudgeVoteRow)
    judge_rows_json = [row.model_dump(mode="json") for row in judge_rows]
    write_json_atomic(run_dir / "judge_aggregate.json", judge_rows_json)
    write_jsonl(
        run_dir / "judge_conflicts.jsonl",
        [row.model_dump(mode="json") for row in judge_rows if _judge_row_has_conflict(row)],
    )
    write_json_atomic(run_dir / "judge_coverage.json", judge_coverage)
    write_json_atomic(run_dir / "sim_failure_buckets.json", dict(sorted(failure_bucket_counts.items())))
    write_jsonl(run_dir / "llm_traces.jsonl", artifact_rows_to_json(llm_rows))
    write_typed_jsonl(
        run_dir / "failures.jsonl",
        [row for row in checkpoint_rows if row.success is False],
        model_type=SimCheckpointResultRow,
    )
    write_typed_jsonl(run_dir / "sim_warning_examples.jsonl", warning_examples, model_type=WarningExampleRow)
    write_jsonl(
        run_dir / "review_candidates.jsonl",
        artifact_rows_to_json([row for row in checkpoint_rows if _sim_row_needs_review(row)]),
    )
    if args.sim_freeze_output:
        write_json_atomic(
            run_dir / "frozen_fixture.json",
            [scenario.model_dump(mode="json") for scenario in scenarios],
        )
    if args.sim_export_review_set:
        write_jsonl(
            Path(args.sim_export_review_set),
            artifact_rows_to_json([row for row in checkpoint_rows if _sim_row_needs_review(row)]),
        )
    return run_dir


def _judge_row_has_conflict(row: JudgeAggregate) -> bool:
    concrete = {vote.verdict.value for vote in row.votes if vote.verdict.value != "abstain"}
    return "pass" in concrete and "fail" in concrete


def _sim_row_has_extra_context_provenance(row: SimCheckpointResultRow) -> bool:
    output = row.output
    return bool(
        output.context_claim_ids
        or output.context_entity_ids
        or output.context_relation_ids
        or output.context_citation_event_ids
    )


def _sim_warning_examples(
    checkpoint_rows: Sequence[SimCheckpointResultRow],
) -> list[WarningExampleRow]:
    examples: list[WarningExampleRow] = []
    for row in checkpoint_rows:
        output = row.output
        if row.answer_match_type == "optional_missing":
            examples.append(
                WarningExampleRow(
                    scenario_id=row.scenario_id,
                    checkpoint_id=row.checkpoint_id,
                    checkpoint_type=row.checkpoint_type,
                    warning_bucket="graph_answer_optional_missing",
                    warning_buckets=["graph_answer_optional_missing"],
                    reason="answer text is optional for this checkpoint; structured graph/action channels are authoritative",
                    selected_claim_ids=list(output.selected_claim_ids),
                    selected_entity_ids=list(output.selected_entity_ids),
                )
            )
        if _sim_row_has_extra_context_provenance(row):
            examples.append(
                WarningExampleRow(
                    scenario_id=row.scenario_id,
                    checkpoint_id=row.checkpoint_id,
                    checkpoint_type=row.checkpoint_type,
                    warning_bucket="extra_context_provenance",
                    warning_buckets=["extra_context_provenance"],
                    reason="context/audit evidence is broader than selected support but is not selected or supporting truth",
                    context_claim_ids=list(output.context_claim_ids),
                    context_entity_ids=list(output.context_entity_ids),
                    context_relation_ids=list(output.context_relation_ids),
                    context_citation_event_ids=list(output.context_citation_event_ids),
                )
            )
        for vote in row.judge_aggregate.votes:
            if vote.verdict.value != "pass":
                continue
            for bucket in vote.failure_buckets:
                examples.append(
                    WarningExampleRow(
                        scenario_id=row.scenario_id,
                        checkpoint_id=row.checkpoint_id,
                        checkpoint_type=row.checkpoint_type,
                        warning_bucket=bucket,
                        warning_buckets=[bucket],
                        reason=vote.rationale,
                        failed_ids=list(vote.failed_ids),
                        covered_ids=list(vote.covered_ids),
                    )
                )
    deduped: list[WarningExampleRow] = []
    seen: set[tuple[str, str, str]] = set()
    for example in examples:
        key = (example.scenario_id, example.checkpoint_id, example.warning_bucket)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(example)
    return deduped


def _sim_row_needs_review(row: SimCheckpointResultRow) -> bool:
    if not row.success:
        return True
    if _mapping_has_values(row.selected_excluded_ids) or _mapping_has_values(row.supporting_excluded_ids):
        return True
    if row.supporting_noisy_citation_event_ids:
        return True
    if _mapping_has_values(row.supporting_role_violations):
        return True
    if _mapping_has_values(row.supporting_rejection_provenance_overlap):
        return True
    precision_failures = set(row.precision_failure_classification)
    actionable_precision_failures = {
        "selected_excluded_id",
        "supporting_excluded_id",
        "selected_noncurrent_claim",
        "supporting_noisy_or_stale_provenance",
        "supporting_role_violation",
        "wrong_entity_support_used",
        "disambiguation_evidence_used_as_support",
        "missing_wrong_entity_rejection",
        "selected_claim_support_missing",
        "selected_claim_provenance_missing",
        "active_action_provenance_missing",
        "selected_rejected_channel_overlap",
        "supporting_rejected_channel_overlap",
        "supporting_rejection_provenance_overlap",
    }
    if precision_failures & actionable_precision_failures:
        return True
    buckets = set(row.failure_buckets)
    return bool(buckets & {"hidden_fact_hallucinated", "overconfident_wrong_answer", "ambiguous_fact_overcommitted"})


def _trace_prompt_ref(row: LLMArtifactRow) -> str | None:
    if isinstance(row, SimLLMTraceRow):
        value = row.trace.input_payload.get("prompt_ref")
        return str(value) if value else None
    return row.trace.prompt_hash


def _trace_model(row: LLMArtifactRow) -> str | None:
    if isinstance(row, SimLLMTraceRow):
        return row.trace.model_name
    return row.trace.model


def _trace_provider(row: LLMArtifactRow) -> str | None:
    if isinstance(row, SimLLMTraceRow):
        value = row.trace.input_payload.get("provider")
        return str(value) if value else None
    return row.trace.provider


def print_memory_evolution_summary(
    *,
    suite: str,
    mode: str,
    profile: str,
    run_dir: Path,
    scenarios: list[LatentGraphScenario],
    scenario_rows: Sequence[SimScenarioResultRow],
    checkpoint_rows: Sequence[SimCheckpointResultRow],
    llm_rows: Sequence[LLMArtifactRow],
) -> None:
    """Print the common benchmark summary for a completed suite run."""
    passed = sum(1 for row in scenario_rows if row.success)
    failed = len(scenario_rows) - passed
    event_count = sum(len(scenario.observations) for scenario in scenarios)
    print(
        f"suite={suite} mode={mode} systems=memorii profile={profile} "
        f"scenarios={len(scenario_rows)} events={event_count} checkpoints={len(checkpoint_rows)} "
        f"passed={passed} failed={failed} "
        f"llm_calls={len(llm_rows)} artifacts={run_dir}"
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
    checkpoint_rows: Sequence[SimCheckpointResultRow],
) -> dict[str, dict[str, int]]:
    slice_keys = [
        "phase",
        "horizon_distance_bucket",
        "interference_count_bucket",
        "source_event_age_days_bucket",
        "checkpoint_type",
        "required_retrieval_view",
    ]
    return {
        key: dict(sorted(Counter(str(getattr(row, key, "unknown")) for row in checkpoint_rows).items()))
        for key in slice_keys
    }
