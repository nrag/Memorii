"""Runtime benchmark suite orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from memorii.core.benchmark.memory_evolution_sim import (
    LatentGraphScenario,
    ObservabilityLabel,
    SurfaceObservation,
    judge_sim_checkpoint,
    normalize_sim_system_output_for_checkpoint,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_runtime.artifacts import _horizon_distance_bucket, _interference_count_bucket, _source_event_age_days_bucket
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection import _runtime_relation_support_rows, project_runtime_checkpoint, runtime_failure_buckets
from memorii.core.benchmark.memory_evolution_runtime.execution_state_projection import _action_alignment_failure_reason, _runtime_action_support_rows
from memorii.core.benchmark.memory_evolution_runtime.graph_items import (
    _claim_quote,
    _entity_quote,
    _runtime_entity_type,
    _runtime_span_for_item,
    graph_items_from_snapshot,
)
from memorii.core.benchmark.memory_evolution_runtime.ingestion import ingest_scenario_surface_observations
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeSuiteRows
from memorii.core.benchmark.memory_evolution_runtime.utils import _claim_by_id, _entity_by_id, _ordered_unique, _stable_id, _text_key
from memorii.core.calibration.alignment import normalize_alignment_value
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import LLMDecisionRuntimeConfig, LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution import (
    ClaimKey,
    EntityMention,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionRun,
    HybridMemoryExtractor,
    LLMMemoryExtractor,
    MemoryExtractor,
    MemoryGraphEdgeType,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    RuleMemoryExtractor,
    SourceObservation,
)
from memorii.core.memory_evolution.models import ConfidenceComponents
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.tools.run_live_llm_eval import _validate_live_safety


class OracleVisibleMemoryExtractor:
    """Dry-run extractor that emits only visible scenario items.

    This is plumbing-only. It consumes runtime SourceObservation records and
    matches them to simulator surface text, then emits the latent items that the
    observation explicitly exposes. Hidden items are never emitted.
    """

    provider = "fake_oracle"
    model = "fake-visible-oracle"
    prompt_hash = "memory_evolution_runtime_fake_extractor:v1"

    def __init__(self, *, scenario: LatentGraphScenario) -> None:
        self._scenario = scenario
        self._observations_by_text: dict[str, list[SurfaceObservation]] = {}
        for observation in scenario.observations:
            self._observations_by_text.setdefault(_text_key(observation.text), []).append(observation)
        self.calls = 0
        self.failures = 0
        self.fallbacks = 0

    def extract(self, observations: list[SourceObservation]) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        self.calls += 1
        run_id = _stable_id("runtime-fake-extraction", "|".join(obs.source_id for obs in observations))
        entity_by_id: dict[str, EntityMention] = {}
        claims: list[ExtractedClaim] = []
        actions: list[ExtractedAction] = []
        errors: list[str] = []
        for observation in observations:
            surface = self._surface_for_runtime_observation(observation)
            if surface is None:
                errors.append(f"unmatched_surface_observation:{observation.source_id}")
                continue
            span_cache: dict[str, EvidenceSpan] = {}
            for entity_id in surface.exposed_entity_ids:
                entity = _entity_by_id(self._scenario, entity_id)
                if entity is None or entity.observability == ObservabilityLabel.HIDDEN:
                    continue
                span = _runtime_span_for_item(surface=surface, runtime_observation=observation, quote=_entity_quote(entity, surface), cache=span_cache)
                entity_by_id[entity.entity_id] = EntityMention(
                    entity_id=entity.entity_id,
                    mention_text=entity.canonical_name,
                    normalized_name=normalize_alignment_value(entity.canonical_name),
                    entity_type=_runtime_entity_type(entity.entity_type),
                    evidence_spans=[span],
                    confidence=entity.confidence.calibrated,
                )
            for claim_id in surface.exposed_claim_ids:
                claim = _claim_by_id(self._scenario, claim_id)
                if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
                    continue
                quote = _claim_quote(claim, surface)
                span = _runtime_span_for_item(surface=surface, runtime_observation=observation, quote=quote, cache=span_cache)
                claims.append(
                    ExtractedClaim(
                        claim_id=claim.claim_id,
                        claim_key=ClaimKey(
                            subject_entity_id=claim.subject.entity_id,
                            predicate_id=claim.predicate.predicate_id,
                            scope_key=claim.scope.scope_key,
                            qualifier_key="default",
                        ),
                        object_value=claim.object.value,
                        object_entity_id=claim.object.entity_id,
                        valid_from=claim.lifecycle.valid_from,
                        valid_to=claim.lifecycle.valid_to,
                        evidence_spans=[span],
                        confidence=ConfidenceComponents(
                            extraction=claim.confidence.extraction,
                            evidence=claim.confidence.evidence,
                            source_trust=claim.confidence.source_trust,
                            agreement=claim.confidence.agreement,
                            contradiction=claim.confidence.contradiction,
                            calibrated=claim.confidence.calibrated,
                        ),
                        extraction_run_id=run_id,
                    )
                )
                for entity_id in [claim.subject.entity_id, claim.object.entity_id]:
                    entity = _entity_by_id(self._scenario, entity_id) if entity_id else None
                    if entity is None or entity.observability == ObservabilityLabel.HIDDEN:
                        continue
                    entity_by_id.setdefault(
                        entity.entity_id,
                        EntityMention(
                            entity_id=entity.entity_id,
                            mention_text=entity.canonical_name,
                            normalized_name=normalize_alignment_value(entity.canonical_name),
                            entity_type=_runtime_entity_type(entity.entity_type),
                            evidence_spans=[span],
                            confidence=entity.confidence.calibrated,
                        ),
                    )
                if claim.claim_kind == "action_state":
                    actions.append(
                        ExtractedAction(
                            action_id=f"action:{claim.claim_id}",
                            action_type=claim.predicate.predicate_id,
                            target_entity_ids=[claim.subject.entity_id],
                            status=claim.object.normalized_value or claim.object.value,
                            timestamp=claim.lifecycle.valid_from or surface.timestamp,
                            evidence_spans=[span],
                            extraction_run_id=run_id,
                        )
                    )
        if errors:
            self.failures += 1
        run = ExtractionRun(
            extraction_run_id=run_id,
            provider=self.provider,
            model=self.model,
            prompt_hash=self.prompt_hash,
            input_source_ids=[obs.source_id for obs in observations],
            entity_ids=sorted(entity_by_id),
            claim_ids=[claim.claim_id for claim in claims],
            action_ids=[action.action_id for action in actions],
            errors=errors,
        )
        return run, list(entity_by_id.values()), claims, actions

    def _surface_for_runtime_observation(self, observation: SourceObservation) -> SurfaceObservation | None:
        candidates = self._observations_by_text.get(_text_key(observation.text), [])
        return candidates[0] if candidates else None

class RecordingMemoryExtractor:
    """Benchmark wrapper that records runtime extraction outcomes."""

    def __init__(self, *, delegate: MemoryExtractor) -> None:
        self._delegate = delegate
        self.recorded_runs: list[dict[str, object]] = []

    @property
    def provider(self) -> str:
        return getattr(self._delegate, "provider", "unknown")

    @property
    def model(self) -> str | None:
        return getattr(self._delegate, "model", None)

    @property
    def prompt_hash(self) -> str | None:
        return getattr(self._delegate, "prompt_hash", None)

    def extract(self, observations: list[SourceObservation]) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        run, entities, claims, actions = self._delegate.extract(observations)
        fallback_used = any("fallback_used" in error for error in run.errors)
        self.recorded_runs.append(
            {
                "input_source_ids": list(run.input_source_ids),
                "provider": run.provider,
                "model": run.model,
                "prompt_hash": run.prompt_hash,
                "success": not run.errors,
                "fallback_used": fallback_used,
                "errors": list(run.errors),
                "entity_count": len(entities),
                "claim_count": len(claims),
                "action_count": len(actions),
                "entity_ids": [entity.entity_id for entity in entities],
                "claim_ids": [claim.claim_id for claim in claims],
                "action_ids": [action.action_id for action in actions],
                "validation_summary": dict(run.validation_summary),
            }
        )
        return run, entities, claims, actions

def build_runtime_extractor(
    *,
    scenario: LatentGraphScenario,
    effective_mode: str,
    dry_run: bool,
    runtime_config: LLMRuntimeConfig,
    prompt_root: Path,
) -> MemoryExtractor:
    if effective_mode == "rule":
        delegate: MemoryExtractor = RuleMemoryExtractor()
    elif dry_run:
        delegate = OracleVisibleMemoryExtractor(scenario=scenario)
    else:
        runner = PromptLLMRunner(client=LLMClientFactory.from_config(runtime_config), config=runtime_config)
        llm_extractor = LLMMemoryExtractor(runner=runner, prompt_root=prompt_root)
        if effective_mode == "llm":
            delegate = llm_extractor
        elif effective_mode == "hybrid":
            delegate = HybridMemoryExtractor(llm_extractor=llm_extractor)
        else:
            delegate = RuleMemoryExtractor()
    return RecordingMemoryExtractor(delegate=delegate)

def validate_runtime_live_safety(*, mode: str, dry_run: bool, allow_live: bool) -> tuple[str, LLMRuntimeConfig]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = LLMDecisionRuntimeConfig(mode=mode) if mode != "auto" else LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
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
    return effective_mode, runtime_config

def run_runtime_scenarios(
    *,
    scenarios: list[LatentGraphScenario],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
) -> RuntimeSuiteRows:
    effective_mode, runtime_config = validate_runtime_live_safety(mode=mode, dry_run=dry_run, allow_live=allow_live)
    scenario_rows: list[dict[str, object]] = []
    checkpoint_rows: list[dict[str, object]] = []
    judge_rows: list[dict[str, object]] = []
    llm_rows: list[dict[str, object]] = []
    graph_snapshots: list[dict[str, object]] = []
    graph_items: list[dict[str, object]] = []
    alignments: list[dict[str, object]] = []
    runtime_failures: list[dict[str, object]] = []

    for scenario in scenarios:
        extractor = build_runtime_extractor(
            scenario=scenario,
            effective_mode=effective_mode,
            dry_run=dry_run,
            runtime_config=runtime_config,
            prompt_root=prompt_root,
        )
        memory_plane = MemoryPlaneService()
        provider = ProviderMemoryService(
            memory_plane=memory_plane,
            memory_evolution_enabled=True,
            memory_evolution_extractor=extractor,
        )
        source_id_to_event_id = ingest_scenario_surface_observations(provider=provider, memory_plane=memory_plane, scenario=scenario)
        evolution_service = provider._memory_evolution_service  # benchmark bridge over provider-owned runtime service
        if evolution_service is None:
            raise RuntimeError("runtime memory evolution service was not initialized")
        graph_snapshot = evolution_service.retrieve_graph_snapshot()
        graph_snapshot_payload = graph_snapshot.model_dump(mode="json")
        graph_snapshot_payload["scenario_id"] = scenario.scenario_id
        graph_snapshots.append(graph_snapshot_payload)
        runtime_graph_items = graph_items_from_snapshot(
            scenario_id=scenario.scenario_id,
            snapshot=graph_snapshot,
            source_id_to_event_id=source_id_to_event_id,
        )
        graph_items.extend(runtime_graph_items)

        scenario_checkpoint_rows: list[dict[str, object]] = []
        extractor_call_rows = extractor_trace_rows(
            scenario=scenario,
            extractor=extractor,
            effective_mode=effective_mode,
            dry_run=dry_run,
        )
        llm_rows.extend(extractor_call_rows)
        for checkpoint in scenario.checkpoints:
            projection = project_runtime_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                graph_snapshot=graph_snapshot,
                graph_items=runtime_graph_items,
                source_id_to_event_id=source_id_to_event_id,
            )
            alignments.extend([
                {"scenario_id": scenario.scenario_id, "checkpoint_id": checkpoint.checkpoint_id, **alignment.model_dump(mode="json")}
                for alignment in projection.alignments
            ])
            raw_output = projection.output
            output, normalization = normalize_sim_system_output_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                output=raw_output,
            )
            aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
            diagnostics = sim_checkpoint_diagnostics(scenario=scenario, checkpoint=checkpoint, output=output, aggregate=aggregate)
            runtime_buckets = runtime_failure_buckets(
                checkpoint=checkpoint,
                output=output,
                aggregate=aggregate,
                projection=projection,
                graph_snapshot=graph_snapshot,
            )
            success = aggregate.verdict.value == "pass" and not runtime_buckets
            final_output_source = runtime_final_output_source(effective_mode=effective_mode, dry_run=dry_run, extractor=extractor)
            row = {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "profile": scenario.profile,
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_type": checkpoint.checkpoint_type,
                "phase": "checkpoint",
                "horizon_distance": checkpoint.horizon_distance,
                "horizon_distance_bucket": _horizon_distance_bucket(checkpoint.horizon_distance),
                "interference_count": checkpoint.interference_count,
                "interference_count_bucket": _interference_count_bucket(checkpoint.interference_count),
                "source_event_age_days": checkpoint.source_event_age_days,
                "source_event_age_days_bucket": _source_event_age_days_bucket(checkpoint.source_event_age_days),
                "required_retrieval_view": checkpoint.required_retrieval_view,
                "expected_stage_path": list(checkpoint.expected_stage_path),
                "query_or_task": checkpoint.query_or_task,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "llm_call_made": effective_mode in {"llm", "hybrid"},
                "fallback_used": extractor_fallback_count(extractor) > 0,
                "fallback_reason": "runtime_extractor_fallback" if extractor_fallback_count(extractor) > 0 else None,
                "final_output_source": final_output_source,
                "request_id": f"memory_evolution_runtime:{mode}:{scenario.scenario_id}:{checkpoint.checkpoint_id}",
                "success": success,
                "passed": True if aggregate.verdict.value == "pass" and not runtime_buckets else False,
                "verdict": "fail" if runtime_buckets else aggregate.verdict.value,
                "score": aggregate.score,
                "confidence": aggregate.confidence,
                "review_required": aggregate.review_required or bool(runtime_buckets),
                "failure_buckets": sorted({*aggregate.critical_failure_buckets, *runtime_buckets}),
                "runtime_failure_buckets": runtime_buckets,
                "missing_expected_ids": diagnostics["missing_expected_ids"],
                "extra_selected_ids": diagnostics["extra_selected_ids"],
                "answer_match_type": diagnostics["answer_match_type"],
                "failure_classification": _runtime_failure_classification(runtime_buckets, diagnostics),
                "runtime_failure_classification": _runtime_failure_classification(runtime_buckets, diagnostics),
                "selected_excluded_ids": diagnostics["selected_excluded_ids"],
                "supporting_excluded_ids": diagnostics["supporting_excluded_ids"],
                "rejected_expected_ids": diagnostics["rejected_expected_ids"],
                "missing_rejected_ids": diagnostics["missing_rejected_ids"],
                "missing_rejected_claim_subject_entity_ids": diagnostics["missing_rejected_claim_subject_entity_ids"],
                "supporting_wrong_entity_claim_ids": diagnostics["supporting_wrong_entity_claim_ids"],
                "auto_closed_selected_entity_ids": normalization.auto_closed_selected_entity_ids,
                "auto_closed_rejected_entity_ids": normalization.auto_closed_rejected_entity_ids,
                "auto_closed_context_entity_ids": normalization.auto_closed_context_entity_ids,
                "auto_closed_context_relation_ids": normalization.auto_closed_context_relation_ids,
                "auto_promoted_selected_claim_ids": normalization.auto_promoted_selected_claim_ids,
                "auto_promoted_supporting_claim_ids": normalization.auto_promoted_supporting_claim_ids,
                "auto_promoted_supporting_citation_event_ids": normalization.auto_promoted_supporting_citation_event_ids,
                "auto_rejected_claim_ids": normalization.auto_rejected_claim_ids,
                "normalization_reason_codes": normalization.normalization_reason_codes,
                "normalization_applied": normalization.normalization_applied,
                "selected_noncurrent_claim_ids": diagnostics["selected_noncurrent_claim_ids"],
                "required_definition_claim_ids": diagnostics["required_definition_claim_ids"],
                "missing_definition_claim_ids": diagnostics["missing_definition_claim_ids"],
                "missing_definition_support_claim_ids": diagnostics["missing_definition_support_claim_ids"],
                "selected_entity_role_mismatches": diagnostics["selected_entity_role_mismatches"],
                "missing_selected_subject_entity_ids": diagnostics["missing_selected_subject_entity_ids"],
                "selected_object_entity_instead_of_subject_ids": diagnostics["selected_object_entity_instead_of_subject_ids"],
                "selected_graph_entity_overbreadth": diagnostics["selected_graph_entity_overbreadth"],
                "selected_nonrequired_graph_entity_ids": diagnostics["selected_nonrequired_graph_entity_ids"],
                "selected_context_only_entity_ids": diagnostics["selected_context_only_entity_ids"],
                "selected_rejected_or_context_entity_ids": diagnostics["selected_rejected_or_context_entity_ids"],
                "supporting_noisy_citation_event_ids": diagnostics["supporting_noisy_citation_event_ids"],
                "context_only_noise_event_ids": diagnostics["context_only_noise_event_ids"],
                "role_misclassification": diagnostics["role_misclassification"],
                "precision_failure_classification": diagnostics["precision_failure_classification"],
                "required_judge_ids": diagnostics["required_judge_ids"],
                "runtime_graph_validation_errors": list(graph_snapshot.validation_errors),
                "runtime_relation_support": _runtime_relation_support_rows(projection),
                "runtime_action_support": _runtime_action_support_rows(projection),
                "runtime_action_alignments": list(projection.action_alignment_rows),
                "runtime_execution_state": dict(projection.execution_state),
                "active_continuation_branch": projection.execution_state.get("active_continuation_branch"),
                "suppressed_branch_ids": list(projection.execution_state.get("suppressed_branch_ids", [])),
                "action_alignment_failure_reason": _action_alignment_failure_reason(projection.action_alignment_rows),
                "expected": checkpoint.model_dump(mode="json"),
                "candidate_cards": sim_reconstruction_context_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                ).model_dump(mode="json"),
                "raw_output": raw_output.model_dump(mode="json"),
                "normalized_output": output.model_dump(mode="json"),
                "output": output.model_dump(mode="json"),
                "judge_aggregate": aggregate.model_dump(mode="json"),
            }
            checkpoint_rows.append(row)
            scenario_checkpoint_rows.append(row)
            judge_rows.append(aggregate.model_dump(mode="json"))
            if not success:
                runtime_failures.append(row)
        scenario_success = all(row["success"] is True for row in scenario_checkpoint_rows)
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "profile": scenario.profile,
                "decision_mode": mode,
                "effective_decision_mode": effective_mode,
                "checkpoint_count": len(scenario_checkpoint_rows),
                "success": scenario_success,
                "failure_mode": None if scenario_success else "one_or_more_runtime_checkpoints_failed",
                "checkpoints_passed": sum(1 for row in scenario_checkpoint_rows if row["success"] is True),
                "checkpoints_failed": sum(1 for row in scenario_checkpoint_rows if row["success"] is False),
            }
        )
    return RuntimeSuiteRows(
        scenario_rows=scenario_rows,
        checkpoint_rows=checkpoint_rows,
        judge_rows=judge_rows,
        llm_rows=llm_rows,
        graph_snapshots=graph_snapshots,
        graph_items=graph_items,
        alignments=alignments,
        runtime_failures=runtime_failures,
    )

def extractor_trace_rows(*, scenario: LatentGraphScenario, extractor: MemoryExtractor, effective_mode: str, dry_run: bool) -> list[dict[str, object]]:
    if effective_mode not in {"llm", "hybrid"}:
        return []
    recorded = list(getattr(extractor, "recorded_runs", []))
    rows: list[dict[str, object]] = []
    for index, run in enumerate(recorded):
        rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "checkpoint_id": None,
                "transition_type": "runtime_memory_extraction",
                "decision_mode": effective_mode,
                "effective_decision_mode": effective_mode,
                "final_output_source": runtime_final_output_source(effective_mode=effective_mode, dry_run=dry_run, extractor=extractor),
                "trace": {
                    "provider": run.get("provider") or getattr(extractor, "provider", effective_mode),
                    "model": run.get("model"),
                    "prompt_hash": run.get("prompt_hash") or getattr(extractor, "prompt_hash", None),
                    "scenario_id": scenario.scenario_id,
                    "call_index": index,
                    "input_source_ids": run.get("input_source_ids", []),
                    "errors": run.get("errors", []),
                    "entity_count": run.get("entity_count", 0),
                    "claim_count": run.get("claim_count", 0),
                    "action_count": run.get("action_count", 0),
                    "validation_summary": run.get("validation_summary", {}),
                },
                "success": bool(run.get("success")),
                "fallback_used": bool(run.get("fallback_used")),
                "failure_mode": None if run.get("success") else "runtime_extractor_failure",
                "output": {
                    "entity_ids": run.get("entity_ids", []),
                    "claim_ids": run.get("claim_ids", []),
                    "action_ids": run.get("action_ids", []),
                },
            }
        )
    return rows

def runtime_final_output_source(*, effective_mode: str, dry_run: bool, extractor: MemoryExtractor) -> str:
    if effective_mode == "rule":
        return "rule"
    if dry_run:
        return "fake_oracle"
    if getattr(extractor, "provider", "") == "hybrid" and extractor_fallback_count(extractor):
        return "rule"
    return "live_llm"

def extractor_fallback_count(extractor: MemoryExtractor) -> int:
    recorded = getattr(extractor, "recorded_runs", [])
    if recorded:
        return sum(1 for run in recorded if run.get("fallback_used"))
    return int(getattr(extractor, "fallbacks", 0))

def _runtime_failure_classification(runtime_buckets: list[str], diagnostics: dict[str, object]) -> list[str]:
    classifications = list(diagnostics.get("failure_classification", []) or [])
    mapping = {
        "runtime_missing_expected_entity": "runtime_missing_expected_entity",
        "runtime_missing_expected_claim": "runtime_missing_expected_claim",
        "runtime_missing_expected_relation": "runtime_missing_expected_relation",
        "runtime_missing_expected_action": "runtime_missing_expected_action",
        "runtime_action_target_mismatch": "runtime_action_target_mismatch",
        "runtime_action_status_mismatch": "runtime_action_status_mismatch",
        "runtime_action_evidence_missing": "runtime_action_evidence_missing",
        "runtime_execution_state_missing": "runtime_execution_state_missing",
        "runtime_execution_state_ambiguous": "runtime_execution_state_ambiguous",
        "runtime_extra_hidden_fact": "runtime_extra_hidden_fact",
        "runtime_modality_false_positive": "runtime_modality_false_positive",
        "runtime_scope_leak": "runtime_scope_leak",
        "runtime_provenance_missing": "runtime_provenance_missing",
        "runtime_alignment_ambiguous": "runtime_alignment_ambiguous",
        "runtime_graph_validation_error": "runtime_graph_validation_error",
        "long_horizon_retrieval_miss": "long_horizon_retrieval_miss",
        "stale_fact_resurfaced": "stale_fact_resurfaced",
        "historical_fact_lost": "historical_fact_lost",
        "scope_decay": "scope_decay",
        "source_trust_decay": "source_trust_decay",
        "entity_rekey_lost": "entity_rekey_lost",
        "branch_state_decay": "branch_state_decay",
        "branch_state_not_projected": "branch_state_not_projected",
        "blocked_branch_selected": "blocked_branch_selected",
        "provenance_chain_broken": "provenance_chain_broken",
        "hidden_fact_leak": "hidden_fact_leak",
        "calibration_drift": "calibration_drift",
    }
    classifications.extend(mapping[bucket] for bucket in runtime_buckets if bucket in mapping)
    return _ordered_unique(classifications)
