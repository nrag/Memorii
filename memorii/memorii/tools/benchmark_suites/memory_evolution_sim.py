"""Latent graph memory evolution simulator benchmark suite runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import (
    UTC,
    datetime,
)
from pathlib import Path
from typing import cast

from memorii.core.benchmark.artifact_rows import (
    BenchmarkReportSummary,
    CheckpointDecisionTraceSection,
    CheckpointDiagnosticsSection,
    CheckpointHorizonSection,
    CheckpointVerdictSection,
    DecisionMode,
    FinalOutputSource,
    JudgeVoteRow,
    NormalizationDiagnosticsSection,
    SimCheckpointResultRow,
    WarningExampleRow,
    artifact_rows_to_json,
    checkpoint_warning_buckets,
)
from memorii.core.benchmark.artifact_validation import (
    validate_memory_evolution_run,
    write_json_atomic,
    write_text_atomic,
    write_typed_jsonl,
)
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    OracleCheckpoint,
    SimOutputNormalization,
    SimSystemOutput,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    memory_evolution_sim_engine_result_from_llm,
    memory_evolution_sim_trace_for_rule,
    normalize_sim_system_output_for_checkpoint,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
    sim_metrics_from_rows,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.models import BenchmarkRunConfig
from memorii.core.benchmark.reproducibility import build_run_config_fingerprint, build_run_id
from memorii.core.calibration.gates import DEFAULT_CRITICAL_FAILURE_BUCKETS
from memorii.core.calibration.models import CalibrationEvent
from memorii.core.calibration.reports import build_calibration_artifacts
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import (
    DecisionModeName,
    LLMDecisionRuntimeConfig,
    LLMLiveTestConfig,
    LLMRuntimeConfig,
)
from memorii.core.llm_decision.adapters import LLMMemoryEvolutionSimReconstructionAdapter
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.tools.benchmark_registry import BenchmarkSuiteRunner, FunctionBenchmarkSuiteRunner
from memorii.tools.benchmark_suites.artifact_io import _write_jsonl
from memorii.tools.benchmark_suites.common import ALL_DECISION_MODES, require_memorii_only
from memorii.tools.benchmark_suites.fake_adapters import _ExpectedMemoryEvolutionSimFakeAdapter
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from memorii.tools.run_live_llm_eval import _validate_live_safety

SUITE_NAME = "memory_evolution_sim_v1"
_INVALID_REFERENCE_ID_BUCKET = "invalid_reference_id"


def _decision_modes_from_args(mode: str) -> list[DecisionModeName]:
    if mode == "all":
        return ["rule", "llm", "hybrid"]
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return [cast(DecisionModeName, mode)]
    raise ValueError(f"Unsupported memory evolution sim mode: {mode}")


def _json_sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _ordered_unique(values: Sequence[object]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _mapping_has_values(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return any(bool(item) for item in value.values())


def _row_value(row: dict[str, object], key: str, default: object = None) -> object:
    if key in row:
        return row[key]
    diagnostics = row.get("diagnostics")
    if isinstance(diagnostics, Mapping):
        return diagnostics.get(key, default)
    return default


def load_memory_evolution_scenarios(args: argparse.Namespace) -> tuple[list[LatentGraphScenario], str]:
    """Load the shared latent scenario surface for sim and runtime suites."""
    if args.sim_fixture_path:
        payload = json.loads(Path(args.sim_fixture_path).read_text(encoding="utf-8"))
        return (
            [LatentGraphScenario.model_validate(item) for item in payload],
            str(args.sim_fixture_path),
        )
    return (
        generate_memory_evolution_sim_scenarios(
            profile=args.sim_profile,
            scenario_count=args.sim_scenario_count,
            seed=args.seed,
            min_events=args.sim_min_events,
            max_events=args.sim_max_events,
            noise_rate=args.sim_noise_rate,
        ),
        f"generated:{args.sim_profile}:seed={args.seed}",
    )

def _run_memory_evolution_sim_transitions(
    *,
    scenarios: list[LatentGraphScenario],
    mode: DecisionModeName,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> tuple[list[dict[str, object]], list[SimCheckpointResultRow], list[dict[str, object]], list[dict[str, object]]]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=mode)
        if mode != "auto"
        else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
    )
    effective_mode = decision_config.resolve(runtime_config)
    if effective_mode in {"llm", "hybrid"}:
        live_config = LLMLiveTestConfig.from_env(env_snapshot.env)
        _validate_live_safety(
            modes=[effective_mode],
            dry_run=dry_run,
            allow_live=allow_live,
            runtime_config=runtime_config,
            live_config=live_config,
        )

    registry = PromptRegistry(prompt_root=prompt_root)
    adapter = None
    if effective_mode in {"llm", "hybrid"}:
        client = dependencies.eval_fake_client_cls() if dry_run else dependencies.llm_client_factory.from_config(runtime_config)
        runner = PromptLLMRunner(client=client, config=runtime_config)
        adapter = (
            _ExpectedMemoryEvolutionSimFakeAdapter(scenarios=scenarios, registry=registry)
            if dry_run and dependencies.is_default_fake_client()
            else LLMMemoryEvolutionSimReconstructionAdapter(runner=runner, registry=registry)
        )

    scenario_rows: list[dict[str, object]] = []
    checkpoint_rows: list[SimCheckpointResultRow] = []
    judge_rows: list[dict[str, object]] = []
    llm_rows: list[dict[str, object]] = []

    for scenario in scenarios:
        scenario_checkpoint_rows: list[SimCheckpointResultRow] = []
        for checkpoint in scenario.checkpoints:
            context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
            rule_output = rule_sim_output_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
            rule_output_json = rule_output.model_dump(mode="json")
            rule_trace = memory_evolution_sim_trace_for_rule(context=context, decision=rule_output, mode="rule")
            request_id = f"memory_evolution_sim:{mode}:{scenario.scenario_id}:{checkpoint.checkpoint_id}"
            output_json = rule_output_json
            llm_call_made = False
            llm_success = False
            fallback_used = effective_mode in {"auto", "hybrid"} and effective_mode == "rule"
            fallback_reason = "llm_not_configured" if fallback_used else None
            final_output_source = "rule"
            llm_trace = rule_trace

            if effective_mode in {"llm", "hybrid"} and adapter is not None:
                llm_call_made = True
                result = adapter.decide(
                    context,
                    request_id=request_id,
                    metadata={
                        "suite": "memory_evolution_sim_v1",
                        "scenario_id": scenario.scenario_id,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "decision_mode": mode,
                        "effective_decision_mode": effective_mode,
                        "transition_type": "memory_evolution_sim_reconstruction",
                    },
                )
                output_json, llm_trace, llm_success, fallback_reason = memory_evolution_sim_engine_result_from_llm(
                    result=result,
                    mode=LLMDecisionMode(effective_mode),
                    scenario=scenario,
                    rule_output=rule_output_json,
                )
                invalid_reference_failure = fallback_reason == "llm_output_referenced_invalid_ids"
                if dry_run and dependencies.is_default_fake_client() and llm_success:
                    final_output_source = "fake_oracle"
                elif llm_success or invalid_reference_failure:
                    final_output_source = "live_llm"
                else:
                    final_output_source = "rule"
                fallback_used = not llm_success and not invalid_reference_failure
                llm_rows.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "transition_type": "memory_evolution_sim_reconstruction",
                        "decision_mode": mode,
                        "effective_decision_mode": effective_mode,
                        "final_output_source": final_output_source,
                        "trace": llm_trace.model_dump(mode="json"),
                        "success": llm_success,
                        "fallback_used": fallback_used,
                        "failure_mode": fallback_reason,
                        "output": output_json,
                    }
                )

            raw_output = SimSystemOutput.model_validate(output_json)
            raw_output_json = raw_output.model_dump(mode="json")
            _diagnostic_output, normalization = normalize_sim_system_output_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                output=raw_output,
            )
            # The raw system output is authoritative for scoring. The
            # normalizer is retained only as an audit diagnostic; promoting a
            # context item or completing a missing channel would otherwise
            # turn a semantic system failure into a passing benchmark row.
            output = raw_output
            output_json = output.model_dump(mode="json")
            aggregate = judge_sim_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                output=output,
            )
            invalid_reference_failure = fallback_reason == "llm_output_referenced_invalid_ids"
            diagnostics = sim_checkpoint_diagnostics(
                scenario=scenario,
                checkpoint=checkpoint,
                output=output,
                aggregate=aggregate,
            )
            engine_failure_buckets = [_INVALID_REFERENCE_ID_BUCKET] if invalid_reference_failure else []
            success = (
                aggregate.verdict.value == "pass"
                and (effective_mode != "llm" or llm_success or not llm_call_made)
                and not invalid_reference_failure
            )
            warning_buckets = checkpoint_warning_buckets(
                answer_match_type=diagnostics["answer_match_type"],
                output=output_json,
            )
            if normalization.repaired_definition_claim_conflict_ids:
                warning_buckets.append("definition_claim_conflict_repaired")
            if normalization.auto_demoted_execution_context_claim_ids:
                warning_buckets.append("execution_context_support_demoted")
            checkpoint_row = _build_sim_checkpoint_result_row(
                scenario=scenario,
                checkpoint=checkpoint,
                context_json=context.model_dump(mode="json"),
                mode=mode,
                effective_mode=effective_mode,
                llm_call_made=llm_call_made,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                final_output_source=final_output_source,
                request_id=request_id if llm_call_made else llm_trace.trace_id,
                success=success,
                aggregate=aggregate,
                diagnostics=diagnostics,
                engine_failure_buckets=engine_failure_buckets,
                normalization=normalization,
                warning_buckets=warning_buckets,
                raw_output_json=raw_output_json,
                output_json=output_json,
            )
            checkpoint_rows.append(checkpoint_row)
            scenario_checkpoint_rows.append(checkpoint_row)
            judge_rows.append(aggregate.model_dump(mode="json"))

        scenario_success = all(row.success is True for row in scenario_checkpoint_rows)
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "profile": scenario.profile,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "checkpoint_count": len(scenario_checkpoint_rows),
                "success": scenario_success,
                "failure_mode": None if scenario_success else "one_or_more_checkpoints_failed",
                "checkpoints_passed": sum(1 for row in scenario_checkpoint_rows if row.success is True),
                "checkpoints_failed": sum(1 for row in scenario_checkpoint_rows if row.success is False),
            }
        )
    return scenario_rows, checkpoint_rows, judge_rows, llm_rows


def _build_sim_checkpoint_result_row(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    context_json: dict[str, object],
    mode: DecisionMode,
    effective_mode: DecisionMode,
    llm_call_made: bool,
    fallback_used: bool,
    fallback_reason: str | None,
    final_output_source: FinalOutputSource,
    request_id: str,
    success: bool,
    aggregate: JudgeAggregate,
    diagnostics: dict[str, object],
    engine_failure_buckets: list[str],
    normalization: SimOutputNormalization,
    warning_buckets: list[str],
    raw_output_json: dict[str, object],
    output_json: dict[str, object],
) -> SimCheckpointResultRow:
    horizon = CheckpointHorizonSection(
        family=scenario.family,
        profile=scenario.profile,
        horizon_distance=checkpoint.horizon_distance,
        horizon_distance_bucket=_horizon_distance_bucket(checkpoint.horizon_distance),
        interference_count=checkpoint.interference_count,
        interference_count_bucket=_interference_count_bucket(checkpoint.interference_count),
        source_event_age_days=checkpoint.source_event_age_days,
        source_event_age_days_bucket=_source_event_age_days_bucket(checkpoint.source_event_age_days),
        required_retrieval_view=checkpoint.required_retrieval_view,
        expected_stage_path=list(checkpoint.expected_stage_path),
        query_or_task=checkpoint.query_or_task,
    )
    decision_trace = CheckpointDecisionTraceSection(
        decision_mode=mode,
        effective_decision_mode=effective_mode,
        llm_call_made=llm_call_made,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        final_output_source=final_output_source,
        request_id=request_id,
    )
    verdict = CheckpointVerdictSection(
        success=success,
        passed=bool(success),
        verdict=aggregate.verdict.value,
        score=aggregate.score,
        confidence=aggregate.confidence,
        review_required=aggregate.review_required or bool(engine_failure_buckets),
        failure_buckets=_ordered_unique([*aggregate.critical_failure_buckets, *engine_failure_buckets]),
        warning_buckets=warning_buckets,
    )
    diagnostic_section = CheckpointDiagnosticsSection.model_validate(diagnostics)
    normalization_section = NormalizationDiagnosticsSection.from_normalization(normalization)
    diagnostics_payload = {
        **diagnostic_section.to_flat_fields(),
        **normalization_section.to_flat_fields(),
    }
    if engine_failure_buckets:
        diagnostics_payload["failure_classification"] = _ordered_unique(
            [
                *_json_sequence(diagnostics_payload.get("failure_classification")),
                *engine_failure_buckets,
            ]
        )
        diagnostics_payload["precision_failure_classification"] = _ordered_unique(
            [
                *_json_sequence(diagnostics_payload.get("precision_failure_classification")),
                *engine_failure_buckets,
            ]
        )
    typed_output = SimSystemOutput.model_validate(output_json)
    typed_raw_output = SimSystemOutput.model_validate(raw_output_json)
    typed_candidate_cards = MemoryEvolutionSimReconstructionContext.model_validate(context_json)
    row_data: dict[str, object] = {
        "scenario_id": scenario.scenario_id,
        "checkpoint_id": checkpoint.checkpoint_id,
        "checkpoint_type": checkpoint.checkpoint_type,
        "success": verdict.success,
        "passed": verdict.passed,
        "verdict": verdict.verdict,
        "score": verdict.score,
        "confidence": verdict.confidence,
        "review_required": verdict.review_required,
        "failure_buckets": verdict.failure_buckets,
        "warning_buckets": verdict.warning_buckets,
        "diagnostics": diagnostics_payload,
        "output": typed_output,
        "profile": horizon.profile,
        "family": horizon.family,
        "decision_mode": decision_trace.decision_mode,
        "effective_decision_mode": decision_trace.effective_decision_mode,
        "final_output_source": decision_trace.final_output_source,
        "phase": horizon.phase,
        "horizon_distance": horizon.horizon_distance,
        "horizon_distance_bucket": horizon.horizon_distance_bucket,
        "interference_count": horizon.interference_count,
        "interference_count_bucket": horizon.interference_count_bucket,
        "source_event_age_days": horizon.source_event_age_days,
        "source_event_age_days_bucket": horizon.source_event_age_days_bucket,
        "required_retrieval_view": horizon.required_retrieval_view,
        "expected_stage_path": horizon.expected_stage_path,
        "query_or_task": horizon.query_or_task,
        "llm_call_made": decision_trace.llm_call_made,
        "fallback_used": decision_trace.fallback_used,
        "fallback_reason": decision_trace.fallback_reason,
        "request_id": decision_trace.request_id,
        "expected": checkpoint,
        "candidate_cards": typed_candidate_cards,
        "raw_output": typed_raw_output,
        "normalized_output": typed_output,
        "judge_aggregate": aggregate,
    }
    row_data.update(diagnostic_section.to_flat_fields())
    return SimCheckpointResultRow.model_validate(row_data)


def write_memory_evolution_artifacts(
    *,
    scenarios: list[LatentGraphScenario],
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: Sequence[SimCheckpointResultRow],
    judge_rows: list[dict[str, object]],
    llm_rows: list[dict[str, object]],
    suite: str,
    mode: str,
    storage_root: str,
    fixture_source: str,
    args: argparse.Namespace,
    report_overrides: Mapping[str, object] | None = None,
) -> Path:
    """Persist the common memory-evolution artifact contract for both suites."""
    checkpoint_rows_json = artifact_rows_to_json(checkpoint_rows)
    benchmark_key = build_run_id(
        config=BenchmarkRunConfig(seed=args.seed, run_label=f"{suite}_{mode}_{args.sim_profile}"),
        fixtures=[],
    )
    run_id = benchmark_key if args.dry_run else f"{benchmark_key}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = Path(storage_root) / "benchmark_runs" / suite / mode / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    failure_bucket_counts = Counter(
        bucket
        for row in checkpoint_rows_json
        for bucket in _json_sequence(row.get("failure_buckets"))
    )
    warning_bucket_counts = Counter(
        bucket
        for row in judge_rows
        for vote in _json_sequence(row.get("votes"))
        if isinstance(vote, Mapping) and vote.get("verdict") == "pass"
        for bucket in _json_sequence(vote.get("failure_buckets"))
    )
    graph_answer_optional_missing_count = sum(
        1 for row in checkpoint_rows_json if _row_value(row, "answer_match_type") == "optional_missing"
    )
    extra_context_provenance_count = sum(1 for row in checkpoint_rows_json if _sim_row_has_extra_context_provenance(row))
    if extra_context_provenance_count:
        warning_bucket_counts["extra_context_provenance"] += extra_context_provenance_count
    supporting_pollution_count = sum(
        1
        for row in checkpoint_rows_json
        if _row_value(row, "supporting_excluded_ids") or _row_value(row, "supporting_noisy_citation_event_ids")
    )
    selected_pollution_count = sum(
        1
        for row in checkpoint_rows_json
        if _row_value(row, "selected_excluded_ids")
        or _row_value(row, "selected_noncurrent_claim_ids")
        or _row_value(row, "selected_entity_role_mismatches")
    )
    warning_examples = _sim_warning_examples(checkpoint_rows_json)
    review_bucket_counts = Counter(
        bucket
        for row in checkpoint_rows_json
        if _sim_row_needs_review(row)
        for bucket in [
            *_json_sequence(row.get("failure_buckets")),
            *_json_sequence(_row_value(row, "precision_failure_classification")),
        ]
    )
    required_judge_failures = sum(
        1
        for row in judge_rows
        for vote in _json_sequence(row.get("votes"))
        if isinstance(vote, Mapping) and vote.get("verdict") == "fail" and vote.get("judge_id") in _required_judge_ids_from_row(row)
    )
    judge_coverage = {
        "votes": sum(len(_json_sequence(row.get("votes"))) for row in judge_rows),
        "abstentions": sum(
            1
            for row in judge_rows
            for vote in _json_sequence(row.get("votes"))
            if isinstance(vote, Mapping) and vote.get("verdict") == "abstain"
        ),
        "failures": sum(
            1
            for row in judge_rows
            for vote in _json_sequence(row.get("votes"))
            if isinstance(vote, Mapping) and vote.get("verdict") == "fail"
        ),
        "required_judge_failures": required_judge_failures,
        "review_required": sum(1 for row in checkpoint_rows_json if row.get("review_required")),
    }
    fixture_payload = [scenario.model_dump(mode="json") for scenario in scenarios]
    latent_graph_json = json.dumps(fixture_payload, indent=2, sort_keys=True)
    surface_rows = [observation.model_dump(mode="json") for scenario in scenarios for observation in scenario.observations]
    checkpoint_payload = [checkpoint.model_dump(mode="json") for scenario in scenarios for checkpoint in scenario.checkpoints]
    validation_scenario_catalog = [
        {
            "scenario_id": scenario.scenario_id,
            "family": scenario.family,
            "profile": scenario.profile,
            "observation_count": len(scenario.observations),
            "checkpoint_count": len(scenario.checkpoints),
            "checkpoint_types": sorted({checkpoint.checkpoint_type for checkpoint in scenario.checkpoints}),
            "difficulty_tags": sorted({tag for checkpoint in scenario.checkpoints for tag in checkpoint.difficulty_tags}),
            "phase_counts": dict(sorted(Counter(observation.phase for observation in scenario.observations).items())),
            "max_horizon_distance": max((checkpoint.horizon_distance for checkpoint in scenario.checkpoints), default=0),
            "max_interference_count": max((checkpoint.interference_count for checkpoint in scenario.checkpoints), default=0),
            "hidden_item_count": sum(
                1
                for collection_name in ("entities", "claims", "relations")
                for item in getattr(scenario, collection_name)
                if getattr(item, "observability", None) == "hidden"
            ),
            "observed_claim_count": sum(1 for claim in scenario.claims if getattr(claim, "observability", None) == "observed"),
            "inferable_claim_count": sum(1 for claim in scenario.claims if getattr(claim, "observability", None) == "inferable"),
        }
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
    fingerprint_config: dict[str, object] = {
        "suite": suite,
        "mode": mode,
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
        "dry_run": args.dry_run,
        "allow_live": args.allow_live,
        "source_revision": os.environ.get("MEMORII_SOURCE_REVISION", "working-tree"),
        # Rendered prompt hashes depend on seed-specific candidate content.
        # The prompt contract ref and source revision provide the stable gate
        # identity; per-call rendered hashes remain in llm_traces.jsonl.
        "prompt_contract_refs": sorted(
            {
                str(trace.get("prompt_ref"))
                for row in llm_rows
                for trace in [row.get("trace")]
                if isinstance(trace, Mapping) and trace.get("prompt_ref")
            }
        ),
        "provider_models": sorted(
            {
                str(trace.get("model"))
                for row in llm_rows
                for trace in [row.get("trace")]
                if isinstance(trace, Mapping) and trace.get("model")
            }
        ),
        "providers": sorted(
            {
                str(trace.get("provider"))
                for row in llm_rows
                for trace in [row.get("trace")]
                if isinstance(trace, Mapping) and trace.get("provider")
            }
        ),
    }
    if report_overrides:
        health = report_overrides.get("runtime_provider_health")
        if isinstance(health, Mapping):
            metadata = health.get("provider_metadata")
            if isinstance(metadata, Mapping):
                fingerprint_config["provider_metadata"] = {
                    key: str(metadata[key])
                    for key in ("provider", "model")
                    if metadata.get(key) is not None
                }
    final_output_source_counts = Counter(str(row.get("final_output_source", "unknown")) for row in checkpoint_rows_json)
    llm_successes = sum(1 for row in llm_rows if row.get("success") is True)
    provider_successes = 0 if args.dry_run else llm_successes
    provider_failures = 0 if args.dry_run else len(llm_rows) - llm_successes
    fake_calls = len(llm_rows) if args.dry_run else 0
    fallbacks = (
        0
        if args.dry_run
        else sum(1 for row in checkpoint_rows_json if row.get("fallback_used") is True)
    )
    hidden_item_count = sum(
        1
        for scenario in scenarios
        for collection_name in ("entities", "claims", "relations")
        for item in getattr(scenario, collection_name)
        if getattr(item, "observability", None) == "hidden"
    )
    hidden_pressure_checkpoint_count = len(checkpoint_rows_json) if hidden_item_count else 0
    base_metrics = sim_metrics_from_rows(checkpoint_rows_json)
    base_metrics.update(
        {
            "hidden_item_count": float(hidden_item_count),
            "hidden_pressure_checkpoint_count": float(hidden_pressure_checkpoint_count),
            "hidden_answer_leak_rate": (
                sum(
                    1
                    for row in checkpoint_rows_json
                    if "hidden_fact_answer_leak" in {str(bucket) for bucket in _json_sequence(row.get("failure_buckets"))}
                )
                / max(1, len(checkpoint_rows_json))
            ),
            "graph_answer_optional_missing_count": float(graph_answer_optional_missing_count),
            "extra_context_provenance_count": float(extra_context_provenance_count),
            "extra_context_provenance_rate": extra_context_provenance_count / max(1, len(checkpoint_rows_json)),
            "supporting_pollution_count": float(supporting_pollution_count),
            "selected_pollution_count": float(selected_pollution_count),
        }
    )
    calibration_events, calibration_report, calibration_slices, decision_cost_report = build_calibration_artifacts(
        suite=suite,
        profile=args.sim_profile,
        checkpoint_rows=checkpoint_rows_json,
    )
    report_payload: dict[str, object] = {
        "suite": suite,
        "mode": mode,
        "profile": args.sim_profile,
        "seed": args.seed,
        "benchmark_key": benchmark_key,
        "run_config_fingerprint": build_run_config_fingerprint(fingerprint_config),
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_source": fixture_source,
        "fixture_hashes": fixture_hashes,
        "scenario_count": len(scenario_rows),
        "validation_scenario_catalog": validation_scenario_catalog,
        "event_count": sum(len(scenario.observations) for scenario in scenarios),
        "checkpoint_count": len(checkpoint_rows_json),
        "passed": passed,
        "failed": failed,
        "llm_calls": len(llm_rows),
        "provider_successes": provider_successes,
        "provider_failures": provider_failures,
        "fallbacks": fallbacks,
        "fake_calls": fake_calls,
        "dry_run": args.dry_run,
        "execution_source": (
            "fake_oracle"
            if args.dry_run
            else next(iter(final_output_source_counts), "mixed")
            if len(final_output_source_counts) == 1
            else "mixed"
        ),
        "final_output_source_counts": dict(sorted(final_output_source_counts.items())),
        "hidden_item_count": base_metrics["hidden_item_count"],
        "hidden_hallucination_rate": base_metrics["hidden_hallucination_rate"],
        "hidden_answer_leak_rate": base_metrics["hidden_answer_leak_rate"],
        "metrics": base_metrics,
        "long_horizon_slice_counts": _long_horizon_slice_counts(checkpoint_rows_json),
        "calibration": calibration_report.model_dump(mode="json"),
        "decision_quality": decision_cost_report.model_dump(mode="json"),
        "failure_bucket_counts": dict(sorted(failure_bucket_counts.items())),
        "critical_failure_bucket_counts": dict(
            sorted(
                (bucket, count)
                for bucket, count in failure_bucket_counts.items()
                if bucket in DEFAULT_CRITICAL_FAILURE_BUCKETS
            )
        ),
        "warning_bucket_counts": dict(sorted(warning_bucket_counts.items())),
        "review_bucket_counts": dict(sorted(review_bucket_counts.items())),
        "judge_metrics": judge_coverage,
        "baseline_scores": {},
        "artifact_version": 1,
        "scenario_results": scenario_rows,
        "checkpoint_results": checkpoint_rows_json,
    }
    if report_overrides:
        report_payload.update(report_overrides)
        metrics_override = report_overrides.get("metrics")
        if isinstance(metrics_override, Mapping):
            report_payload["metrics"] = {
                **base_metrics,
                **metrics_override,
            }
    report = BenchmarkReportSummary.from_flat_row(report_payload).to_json_row()
    report_md = (
        f"# {suite}\n\n"
        f"mode={mode} profile={args.sim_profile} scenarios={len(scenario_rows)} "
        f"events={report['event_count']} checkpoints={len(checkpoint_rows_json)} "
        f"passed={passed} failed={failed} llm_calls={len(llm_rows)}\n"
    )
    write_json_atomic(run_dir / "report.json", report)
    write_text_atomic(run_dir / "report.md", report_md)
    latent_graph_payload = json.loads(latent_graph_json)
    write_json_atomic(run_dir / "fixtures.json", latent_graph_payload)
    write_json_atomic(run_dir / "latent_graphs.json", latent_graph_payload)
    _write_jsonl(
        run_dir / "world_transitions.jsonl",
        [transition.model_dump(mode="json") for scenario in scenarios for transition in scenario.transitions],
    )
    _write_jsonl(
        run_dir / "surface_observations.jsonl",
        surface_rows,
    )
    _write_jsonl(
        run_dir / "oracle_checkpoints.jsonl",
        checkpoint_payload,
    )
    _write_jsonl(run_dir / "candidate_cards.jsonl", candidate_card_payload)
    write_json_atomic(run_dir / "validation_scenario_catalog.json", validation_scenario_catalog)
    write_typed_jsonl(run_dir / "sim_checkpoint_results.jsonl", checkpoint_rows, model_type=SimCheckpointResultRow)
    write_typed_jsonl(run_dir / "calibration_events.jsonl", calibration_events, model_type=CalibrationEvent)
    write_json_atomic(run_dir / "calibration_report.json", calibration_report)
    write_json_atomic(run_dir / "slice_calibration_report.json", calibration_slices)
    write_json_atomic(run_dir / "decision_quality_report.json", decision_cost_report)
    judge_vote_rows = [
        JudgeVoteRow.from_flat_row(vote)
        for row in judge_rows
        for vote in _json_sequence(row.get("votes"))
        if isinstance(vote, dict)
    ]
    write_typed_jsonl(run_dir / "judge_votes.jsonl", judge_vote_rows, model_type=JudgeVoteRow)
    write_json_atomic(run_dir / "judge_aggregate.json", judge_rows)
    _write_jsonl(
        run_dir / "judge_conflicts.jsonl",
        [row for row in judge_rows if _judge_row_has_conflict(row)],
    )
    write_json_atomic(run_dir / "judge_coverage.json", judge_coverage)
    write_json_atomic(run_dir / "sim_failure_buckets.json", dict(sorted(failure_bucket_counts.items())))
    _write_jsonl(run_dir / "llm_traces.jsonl", llm_rows)
    write_typed_jsonl(
        run_dir / "failures.jsonl",
        [row for row in checkpoint_rows if row.success is False],
        model_type=SimCheckpointResultRow,
    )
    write_typed_jsonl(run_dir / "sim_warning_examples.jsonl", warning_examples, model_type=WarningExampleRow)
    _write_jsonl(run_dir / "review_candidates.jsonl", [row for row in checkpoint_rows_json if _sim_row_needs_review(row)])
    if args.sim_freeze_output:
        write_json_atomic(
            run_dir / "frozen_fixture.json",
            [scenario.model_dump(mode="json") for scenario in scenarios],
        )
    if args.sim_export_review_set:
        _write_jsonl(Path(args.sim_export_review_set), [row for row in checkpoint_rows_json if _sim_row_needs_review(row)])
    return run_dir

def _required_judge_ids_from_row(row: dict[str, object]) -> set[str]:
    required = row.get("required_judge_ids", [])
    if isinstance(required, list):
        return {str(judge_id) for judge_id in required}
    return set()

def _judge_row_has_conflict(row: dict[str, object]) -> bool:
    votes = row.get("votes", [])
    if not isinstance(votes, list):
        return False
    concrete = {vote.get("verdict") for vote in votes if vote.get("verdict") != "abstain"}
    return "pass" in concrete and "fail" in concrete

def _sim_row_has_extra_context_provenance(row: dict[str, object]) -> bool:
    output = row.get("output")
    if not isinstance(output, dict):
        return False
    return bool(
        output.get("context_claim_ids")
        or output.get("context_entity_ids")
        or output.get("context_relation_ids")
        or output.get("context_citation_event_ids")
    )

def _sim_warning_examples(checkpoint_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    examples: list[dict[str, object]] = []
    for row in checkpoint_rows:
        output = row.get("output") if isinstance(row.get("output"), dict) else {}
        if not isinstance(output, dict):
            output = {}
        if _row_value(row, "answer_match_type") == "optional_missing":
            examples.append(
                WarningExampleRow.from_flat_row({
                    "scenario_id": row.get("scenario_id"),
                    "checkpoint_id": row.get("checkpoint_id"),
                    "checkpoint_type": row.get("checkpoint_type"),
                    "warning_bucket": "graph_answer_optional_missing",
                    "warning_buckets": ["graph_answer_optional_missing"],
                    "reason": "answer text is optional for this checkpoint; structured graph/action channels are authoritative",
                    "selected_claim_ids": output.get("selected_claim_ids", []),
                    "selected_entity_ids": output.get("selected_entity_ids", []),
                }).to_json_row()
            )
        if _sim_row_has_extra_context_provenance(row):
            examples.append(
                WarningExampleRow.from_flat_row({
                    "scenario_id": row.get("scenario_id"),
                    "checkpoint_id": row.get("checkpoint_id"),
                    "checkpoint_type": row.get("checkpoint_type"),
                    "warning_bucket": "extra_context_provenance",
                    "warning_buckets": ["extra_context_provenance"],
                    "reason": "context/audit evidence is broader than selected support but is not selected or supporting truth",
                    "context_claim_ids": output.get("context_claim_ids", []),
                    "context_entity_ids": output.get("context_entity_ids", []),
                    "context_relation_ids": output.get("context_relation_ids", []),
                    "context_citation_event_ids": output.get("context_citation_event_ids", []),
                }).to_json_row()
            )
        aggregate = row.get("judge_aggregate")
        votes = aggregate.get("votes", []) if isinstance(aggregate, dict) else []
        if isinstance(votes, list):
            for vote in votes:
                if not isinstance(vote, dict) or vote.get("verdict") != "pass":
                    continue
                for bucket in vote.get("failure_buckets", []) or []:
                    examples.append(
                        WarningExampleRow.from_flat_row({
                            "scenario_id": row.get("scenario_id"),
                            "checkpoint_id": row.get("checkpoint_id"),
                            "checkpoint_type": row.get("checkpoint_type"),
                            "warning_bucket": bucket,
                            "warning_buckets": [bucket],
                            "reason": vote.get("rationale", "warning emitted by passing judge"),
                            "failed_ids": vote.get("failed_ids", []),
                            "covered_ids": vote.get("covered_ids", []),
                        }).to_json_row()
                    )
    deduped: list[dict[str, object]] = []
    seen: set[tuple[object, object, object]] = set()
    for example in examples:
        key = (example.get("scenario_id"), example.get("checkpoint_id"), example.get("warning_bucket"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(example)
    return deduped

def _sim_row_needs_review(row: dict[str, object]) -> bool:
    if row.get("success") is False:
        return True
    if _mapping_has_values(_row_value(row, "selected_excluded_ids")) or _mapping_has_values(_row_value(row, "supporting_excluded_ids")):
        return True
    if _row_value(row, "supporting_noisy_citation_event_ids"):
        return True
    if _mapping_has_values(_row_value(row, "supporting_role_violations")):
        return True
    if _mapping_has_values(_row_value(row, "supporting_rejection_provenance_overlap")):
        return True
    precision_failures = {str(item) for item in _json_sequence(_row_value(row, "precision_failure_classification"))}
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
    buckets = {str(bucket) for bucket in _json_sequence(row.get("failure_buckets"))}
    return bool(buckets & {"hidden_fact_hallucinated", "overconfident_wrong_answer", "ambiguous_fact_overcommitted"})

def print_memory_evolution_summary(
    *,
    suite: str,
    mode: str,
    profile: str,
    run_dir: Path,
    scenarios: list[LatentGraphScenario],
    scenario_rows: list[dict[str, object]],
    checkpoint_rows: Sequence[SimCheckpointResultRow],
    llm_rows: list[dict[str, object]],
) -> None:
    """Print the common benchmark summary for a completed suite run."""
    checkpoint_rows_json = artifact_rows_to_json(checkpoint_rows)
    passed = sum(1 for row in scenario_rows if row["success"] is True)
    failed = len(scenario_rows) - passed
    event_count = sum(len(scenario.observations) for scenario in scenarios)
    print(
        f"suite={suite} mode={mode} systems=memorii profile={profile} "
        f"scenarios={len(scenario_rows)} events={event_count} checkpoints={len(checkpoint_rows_json)} "
        f"passed={passed} failed={failed} "
        f"llm_calls={len(llm_rows)} artifacts={run_dir}"
    )

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

def _run_memory_evolution_sim_suite(
    args: argparse.Namespace,
    *,
    prompt_root: Path,
    dependencies: BenchmarkRuntimeDependencies,
) -> int:
    scenarios, fixture_source = load_memory_evolution_scenarios(args)
    modes = _decision_modes_from_args(args.mode)
    benchmark_failed = False
    for mode in modes:
        scenario_rows, checkpoint_rows, judge_rows, llm_rows = _run_memory_evolution_sim_transitions(
            scenarios=scenarios,
            mode=mode,
            dry_run=args.dry_run,
            allow_live=args.allow_live,
            prompt_root=prompt_root,
            dependencies=dependencies,
        )
        run_dir = write_memory_evolution_artifacts(
            scenarios=scenarios,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            judge_rows=judge_rows,
            llm_rows=llm_rows,
            suite=SUITE_NAME,
            mode=mode,
            storage_root=args.storage_root,
            fixture_source=fixture_source,
            args=args,
        )
        validate_memory_evolution_run(run_dir, suite=SUITE_NAME)
        print_memory_evolution_summary(
            suite=SUITE_NAME,
            mode=mode,
            profile=args.sim_profile,
            run_dir=run_dir,
            scenarios=scenarios,
            scenario_rows=scenario_rows,
            checkpoint_rows=checkpoint_rows,
            llm_rows=llm_rows,
        )
        benchmark_failed = benchmark_failed or any(not row.success for row in checkpoint_rows)
    if getattr(args, "fail_on_benchmark_failure", False) and benchmark_failed:
        return 1
    return 0



def run(args: argparse.Namespace, prompt_root: Path, *, dependencies: BenchmarkRuntimeDependencies) -> int:
    require_memorii_only(args, SUITE_NAME)
    return _run_memory_evolution_sim_suite(args, prompt_root=prompt_root, dependencies=dependencies)


def build_runner(*, dependencies: BenchmarkRuntimeDependencies) -> BenchmarkSuiteRunner:
    return FunctionBenchmarkSuiteRunner(
        SUITE_NAME,
        lambda args, prompt_root: run(args, prompt_root, dependencies=dependencies),
        ALL_DECISION_MODES,
    )
