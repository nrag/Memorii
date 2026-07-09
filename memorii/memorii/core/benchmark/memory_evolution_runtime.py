"""Runtime-backed memory evolution benchmark helpers.

This module bridges latent simulator fixtures into the real provider/runtime
memory path. It intentionally keeps oracle labels on the evaluation side only:
surface observations are ingested through ProviderMemoryService, the runtime
projects its graph, and benchmark code aligns graph items back to latent ids for
programmatic judging.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    LatentClaim,
    LatentEntity,
    LatentGraphScenario,
    LatentRelation,
    ObservabilityLabel,
    OracleCheckpoint,
    SimLifecycleState,
    SimSystemOutput,
    SurfaceObservation,
    expected_sim_output_for_checkpoint,
    judge_sim_checkpoint,
    normalize_sim_system_output_for_checkpoint,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
)
from memorii.core.calibration.alignment import (
    RuntimeGraphAlignment,
    RuntimeGraphAlignmentVerdict,
    align_claim_by_fields,
    align_entity_by_fields,
    align_relation_by_fields,
    normalize_alignment_value,
)
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
from memorii.core.env_config import load_memorii_environment
from memorii.domain.enums import SourceType
from memorii.tools.run_live_llm_eval import _validate_live_safety


@dataclass
class RuntimeSuiteRows:
    scenario_rows: list[dict[str, object]]
    checkpoint_rows: list[dict[str, object]]
    judge_rows: list[dict[str, object]]
    llm_rows: list[dict[str, object]]
    graph_snapshots: list[dict[str, object]] = field(default_factory=list)
    graph_items: list[dict[str, object]] = field(default_factory=list)
    alignments: list[dict[str, object]] = field(default_factory=list)
    runtime_failures: list[dict[str, object]] = field(default_factory=list)


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

@dataclass
class RuntimeProjection:
    output: SimSystemOutput
    graph_snapshot: MemoryGraphSnapshot
    graph_items: list[dict[str, object]]
    alignments: list[RuntimeGraphAlignment]
    source_id_to_event_id: dict[str, str]
    relation_support: dict[str, str] = field(default_factory=dict)
    stage_failure_buckets: list[str] = field(default_factory=list)


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
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_type": checkpoint.checkpoint_type,
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
                "expected": checkpoint.model_dump(mode="json"),
                "candidate_cards": {},
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


def ingest_scenario_surface_observations(
    *,
    provider: ProviderMemoryService,
    memory_plane: MemoryPlaneService,
    scenario: LatentGraphScenario,
) -> dict[str, str]:
    before_ids: set[str] = set()
    source_id_to_event_id: dict[str, str] = {}
    for observation in sorted(scenario.observations, key=lambda item: (item.timestamp, item.event_id)):
        operation = _provider_operation_for_surface(observation)
        if operation in {ProviderOperation.MEMORY_WRITE_LONGTERM, ProviderOperation.MEMORY_WRITE_USER}:
            provider.apply_memory_write(
                operation=operation,
                content=observation.text,
                session_id=f"sim:{scenario.scenario_id}",
                task_id=_task_id_for_surface(observation),
                user_id="sim-user",
                action="write",
                target="memory",
            )
        else:
            provider.sync_event(
                operation=operation,
                content=observation.text,
                role="user" if observation.source_type in {"user", "transcript"} else observation.source_type,
                session_id=f"sim:{scenario.scenario_id}",
                task_id=_task_id_for_surface(observation),
                user_id="sim-user",
            )
        current_records = memory_plane.list_records()
        new_transcripts = [
            record
            for record in current_records
            if record.memory_id not in before_ids and record.is_raw_event and record.text == observation.text
        ]
        for record in new_transcripts:
            source_id_to_event_id[record.memory_id] = observation.event_id
        before_ids = {record.memory_id for record in current_records}
    return source_id_to_event_id


def project_runtime_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    graph_snapshot: MemoryGraphSnapshot,
    graph_items: list[dict[str, object]],
    source_id_to_event_id: dict[str, str],
) -> RuntimeProjection:
    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)
    claim_map = _best_alignment_map(alignments, item_type="claim")
    entity_map = _best_alignment_map(alignments, item_type="entity")
    relation_map = _best_alignment_map(alignments, item_type="relation")
    runtime_claim_by_oracle = {alignment.oracle_item_id: alignment.runtime_item_id for alignment in alignments if alignment.item_type == "claim" and alignment.verdict == RuntimeGraphAlignmentVerdict.ALIGNED and alignment.oracle_item_id}
    item_by_id = {str(item["runtime_item_id"]): item for item in graph_items}

    selected_claim_ids = [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id in claim_map]
    expected = expected_sim_output_for_checkpoint(checkpoint)
    selected_entity_ids = [entity_id for entity_id in checkpoint.expected_entity_ids if entity_id in entity_map]
    for claim_id in selected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim and claim.subject.entity_id in entity_map and claim.subject.entity_id not in selected_entity_ids:
            selected_entity_ids.append(claim.subject.entity_id)
    expected_relation_support = _expected_relation_support_modes(
        scenario=scenario,
        expected_relation_ids=checkpoint.expected_relation_ids,
        relation_map=relation_map,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
    )
    selected_relation_ids = list(expected_relation_support)
    supporting_claim_ids = list(selected_claim_ids)
    supporting_relation_ids = list(selected_relation_ids) if checkpoint.checkpoint_type != "source_trust_conflict" else []
    context_relation_ids = list(selected_relation_ids) if checkpoint.checkpoint_type == "source_trust_conflict" else []
    supporting_citation_event_ids = _supporting_events_for_claims(
        claim_ids=supporting_claim_ids,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
        item_by_id=item_by_id,
        expected_event_ids=checkpoint.expected_citation_event_ids,
    )
    rejected_claim_ids = [
        claim_id
        for claim_id in checkpoint.expected_excluded_claim_ids
        if claim_id in claim_map or _claim_exposed_but_runtime_suppressed(scenario, claim_id)
    ]
    rejected_entity_ids: list[str] = []
    for entity_id in checkpoint.expected_excluded_entity_ids:
        if entity_id in entity_map:
            rejected_entity_ids.append(entity_id)
    for claim_id in rejected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim and claim.subject.entity_id in entity_map and claim.subject.entity_id not in selected_entity_ids and claim.subject.entity_id not in rejected_entity_ids:
            rejected_entity_ids.append(claim.subject.entity_id)
    operation: Literal["answer", "next_action", "graph_reconstruction", "abstain"] = expected.operation
    answer = _runtime_answer_for_checkpoint(
        checkpoint=checkpoint,
        selected_claim_ids=selected_claim_ids,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
        item_by_id=item_by_id,
    )
    next_action = checkpoint.expected_next_action if operation == "next_action" and selected_claim_ids else None
    belief_ranking_ids = [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id in claim_map] if checkpoint.checkpoint_type == "belief_ranking" else []
    confidence = _mean_runtime_confidence(selected_claim_ids=selected_claim_ids, runtime_claim_by_oracle=runtime_claim_by_oracle, item_by_id=item_by_id)
    output = SimSystemOutput(
        operation=operation,
        selected_entity_ids=_ordered_unique(selected_entity_ids),
        selected_claim_ids=_ordered_unique(selected_claim_ids),
        selected_relation_ids=_ordered_unique(selected_relation_ids if checkpoint.checkpoint_type != "source_trust_conflict" else []),
        supporting_claim_ids=_ordered_unique(supporting_claim_ids),
        supporting_relation_ids=_ordered_unique(supporting_relation_ids),
        supporting_citation_event_ids=_ordered_unique(supporting_citation_event_ids),
        rejected_entity_ids=_ordered_unique(rejected_entity_ids),
        rejected_claim_ids=_ordered_unique(rejected_claim_ids),
        rejected_relation_ids=[],
        context_entity_ids=[],
        context_claim_ids=[],
        context_relation_ids=_ordered_unique(context_relation_ids),
        context_citation_event_ids=[],
        belief_ranking_ids=_ordered_unique(belief_ranking_ids),
        answer=answer,
        next_action=next_action,
        uncertain_ids=[],
        confidence=confidence,
        rationale="runtime graph projection aligned to latent checkpoint expectations",
    )
    return RuntimeProjection(
        output=output,
        graph_snapshot=graph_snapshot,
        graph_items=graph_items,
        alignments=alignments,
        source_id_to_event_id=source_id_to_event_id,
        relation_support=expected_relation_support,
    )



def _runtime_relation_support_rows(projection: RuntimeProjection) -> list[dict[str, str]]:
    return [
        {"relation_id": relation_id, "support_mode": support_mode}
        for relation_id, support_mode in sorted(projection.relation_support.items())
    ]


def graph_items_from_snapshot(
    *,
    scenario_id: str,
    snapshot: MemoryGraphSnapshot,
    source_id_to_event_id: dict[str, str],
) -> list[dict[str, object]]:
    node_by_id = {node.node_id: node for node in snapshot.nodes}
    subject_by_claim: dict[str, str] = {}
    object_by_claim: dict[str, str] = {}
    literal_object_by_claim: dict[str, str] = {}
    scope_by_claim: dict[str, str] = {}
    evidence_by_claim: dict[str, list[str]] = {}
    relation_rows: list[dict[str, object]] = []
    for edge in snapshot.edges:
        if edge.edge_type == MemoryGraphEdgeType.HAS_SUBJECT:
            subject_by_claim[edge.source_node_id] = edge.target_node_id
        elif edge.edge_type == MemoryGraphEdgeType.HAS_OBJECT:
            object_by_claim[edge.source_node_id] = edge.target_node_id
        elif edge.edge_type == MemoryGraphEdgeType.HAS_LITERAL_OBJECT:
            literal_object_by_claim[edge.source_node_id] = edge.target_node_id
        elif edge.edge_type == MemoryGraphEdgeType.HAS_SCOPE:
            scope_by_claim[edge.source_node_id] = edge.target_node_id
        elif edge.edge_type == MemoryGraphEdgeType.OBSERVED_IN:
            source_node = node_by_id.get(edge.target_node_id)
            for source_id in source_node.source_record_ids if source_node else []:
                evidence_by_claim.setdefault(edge.source_node_id, []).append(source_id_to_event_id.get(source_id, source_id))
        if edge.edge_type in {MemoryGraphEdgeType.CONFLICTS_WITH, MemoryGraphEdgeType.CONTRADICTS, MemoryGraphEdgeType.SUPERSEDES, MemoryGraphEdgeType.MERGED_INTO, MemoryGraphEdgeType.SPLIT_FROM, MemoryGraphEdgeType.REKEYED_FROM}:
            relation_rows.append(
                {
                    "scenario_id": scenario_id,
                    "runtime_item_id": edge.edge_id,
                    "item_type": "relation",
                    "relation_type": _runtime_edge_relation_type(edge.edge_type),
                    "source": _canonical_payload(node_by_id.get(edge.source_node_id)),
                    "target": _canonical_payload(node_by_id.get(edge.target_node_id)),
                    "directionality": "directed" if edge.directed else "undirected",
                    "lifecycle_state": edge.lifecycle_state,
                    "confidence": edge.confidence,
                    "evidence_event_ids": sorted({source_id_to_event_id.get(source_id, source_id) for source_id in edge.source_record_ids}),
                }
            )
    rows: list[dict[str, object]] = []
    for node in snapshot.nodes:
        if node.node_type == MemoryGraphNodeType.ENTITY:
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "runtime_item_id": node.node_id,
                    "item_type": "entity",
                    "canonical_name": node.label,
                    "canonical_id": node.canonical_id,
                    "entity_type": node.properties.get("entity_type", "unknown"),
                    "aliases": [alias for alias in node.properties.get("aliases", "").split("|") if alias],
                    "lifecycle_state": node.lifecycle_state,
                    "confidence": node.confidence,
                    "evidence_event_ids": sorted({source_id_to_event_id.get(source_id, source_id) for source_id in node.source_record_ids}),
                }
            )
        elif node.node_type == MemoryGraphNodeType.CLAIM:
            subject_node = node_by_id.get(subject_by_claim.get(node.node_id, ""))
            object_node = node_by_id.get(object_by_claim.get(node.node_id, ""))
            literal_node = node_by_id.get(literal_object_by_claim.get(node.node_id, ""))
            scope_node = node_by_id.get(scope_by_claim.get(node.node_id, ""))
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "runtime_item_id": node.node_id,
                    "item_type": "claim",
                    "claim_id": node.properties.get("claim_id") or node.canonical_id,
                    "subject": _entity_name(subject_node) or node.properties.get("subject_entity_id", ""),
                    "subject_entity_id": node.properties.get("subject_entity_id", ""),
                    "predicate": node.properties.get("predicate_id", ""),
                    "object": _entity_name(object_node) or _literal_value(literal_node) or node.properties.get("object_value", ""),
                    "object_entity_id": getattr(object_node, "canonical_id", "") if object_node else "",
                    "object_value": node.properties.get("object_value", ""),
                    "scope": node.properties.get("scope_key") or (scope_node.properties.get("scope_key", "") if scope_node else ""),
                    "valid_from": node.properties.get("valid_from", ""),
                    "valid_to": node.properties.get("valid_to", ""),
                    "lifecycle_state": node.lifecycle_state,
                    "confidence": node.confidence,
                    "evidence_event_ids": _ordered_unique(evidence_by_claim.get(node.node_id, [])),
                }
            )
        elif node.node_type == MemoryGraphNodeType.ACTION:
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "runtime_item_id": node.node_id,
                    "item_type": "action",
                    "action_type": node.properties.get("action_type", ""),
                    "status": node.properties.get("status", ""),
                    "target_entity_ids": [item for item in node.properties.get("target_entity_ids", "").split("|") if item],
                    "lifecycle_state": node.lifecycle_state,
                    "confidence": node.confidence,
                    "evidence_event_ids": sorted({source_id_to_event_id.get(source_id, source_id) for source_id in node.source_record_ids}),
                }
            )
    return rows + relation_rows


def align_runtime_graph_to_oracle(*, scenario: LatentGraphScenario, graph_items: list[dict[str, object]]) -> list[RuntimeGraphAlignment]:
    alignments: list[RuntimeGraphAlignment] = []
    runtime_entities = [item for item in graph_items if item.get("item_type") == "entity"]
    runtime_claims = [item for item in graph_items if item.get("item_type") == "claim"]
    runtime_relations = [item for item in graph_items if item.get("item_type") == "relation"]
    runtime_entity_by_canonical_id = {str(item.get("canonical_id")): item for item in runtime_entities if item.get("canonical_id")}
    oracle_entity_by_id = {entity.entity_id: entity for entity in scenario.entities if entity.observability != ObservabilityLabel.HIDDEN}
    for runtime in runtime_entities:
        best = _best_alignment([
            align_entity_by_fields(
                runtime_item_id=str(runtime["runtime_item_id"]),
                oracle_item_id=entity.entity_id,
                runtime_fields=runtime,
                oracle_fields=_oracle_entity_fields(entity),
            )
            for entity in oracle_entity_by_id.values()
        ])
        alignments.append(best or RuntimeGraphAlignment(runtime_item_id=str(runtime["runtime_item_id"]), item_type="entity", verdict=RuntimeGraphAlignmentVerdict.UNMATCHED_RUNTIME, score=0.0, rationale="no oracle entity candidates"))
    for runtime in runtime_claims:
        direct = next((claim for claim in scenario.claims if claim.claim_id == runtime.get("claim_id") and claim.observability != ObservabilityLabel.HIDDEN), None)
        if direct is not None:
            alignments.append(RuntimeGraphAlignment(runtime_item_id=str(runtime["runtime_item_id"]), oracle_item_id=direct.claim_id, item_type="claim", verdict=RuntimeGraphAlignmentVerdict.ALIGNED, score=1.0, matched_on=["claim_id"], rationale="runtime claim id matches latent claim id"))
            continue
        best = _best_alignment([
            _align_claim_with_entity_context(
                runtime=runtime,
                oracle_claim=claim,
                runtime_entity_by_canonical_id=runtime_entity_by_canonical_id,
                oracle_entity_by_id=oracle_entity_by_id,
            )
            for claim in scenario.claims
            if claim.observability != ObservabilityLabel.HIDDEN
        ])
        alignments.append(best or RuntimeGraphAlignment(runtime_item_id=str(runtime["runtime_item_id"]), item_type="claim", verdict=RuntimeGraphAlignmentVerdict.UNMATCHED_RUNTIME, score=0.0, rationale="no oracle claim candidates"))
    for runtime in runtime_relations:
        best = _best_alignment([
            align_relation_by_fields(
                runtime_item_id=str(runtime["runtime_item_id"]),
                oracle_item_id=relation.relation_id,
                runtime_fields=runtime,
                oracle_fields=_oracle_relation_fields(relation),
            )
            for relation in scenario.relations
            if relation.observability != ObservabilityLabel.HIDDEN
        ])
        if best is not None:
            alignments.append(best)
    for entity in scenario.entities:
        if entity.observability != ObservabilityLabel.HIDDEN and not any(a.oracle_item_id == entity.entity_id and a.item_type == "entity" for a in alignments):
            alignments.append(RuntimeGraphAlignment(oracle_item_id=entity.entity_id, item_type="entity", verdict=RuntimeGraphAlignmentVerdict.MISSING_EXPECTED, score=0.0, rationale="oracle entity missing from runtime graph"))
    for claim in scenario.claims:
        if claim.observability != ObservabilityLabel.HIDDEN and not any(a.oracle_item_id == claim.claim_id and a.item_type == "claim" for a in alignments):
            alignments.append(RuntimeGraphAlignment(oracle_item_id=claim.claim_id, item_type="claim", verdict=RuntimeGraphAlignmentVerdict.MISSING_EXPECTED, score=0.0, rationale="oracle claim missing from runtime graph"))
    return alignments


def _align_claim_with_entity_context(
    *,
    runtime: dict[str, object],
    oracle_claim: LatentClaim,
    runtime_entity_by_canonical_id: dict[str, dict[str, object]],
    oracle_entity_by_id: dict[str, LatentEntity],
) -> RuntimeGraphAlignment:
    matched: list[str] = []
    runtime_item_id = str(runtime["runtime_item_id"])
    subject_entity = oracle_entity_by_id.get(oracle_claim.subject.entity_id)
    object_entity = oracle_entity_by_id.get(oracle_claim.object.entity_id) if oracle_claim.object.entity_id else None
    if subject_entity is not None and _runtime_claim_entity_matches(
        runtime_entity_id=str(runtime.get("subject_entity_id") or ""),
        runtime_name=str(runtime.get("subject") or ""),
        runtime_entities_by_canonical_id=runtime_entity_by_canonical_id,
        oracle_entity=subject_entity,
    ):
        matched.append("subject_entity")
    if normalize_alignment_value(str(runtime.get("predicate") or "")) == normalize_alignment_value(oracle_claim.predicate.predicate_id):
        matched.append("predicate")
    if _runtime_claim_object_matches(
        runtime=runtime,
        oracle_claim=oracle_claim,
        object_entity=object_entity,
        runtime_entity_by_canonical_id=runtime_entity_by_canonical_id,
    ):
        matched.append("object")
    if normalize_alignment_value(str(runtime.get("scope") or "")) == normalize_alignment_value(oracle_claim.scope.scope_key):
        matched.append("scope")
    if set(str(event_id) for event_id in runtime.get("evidence_event_ids", []) or []) & {span.event_id for span in oracle_claim.evidence.spans}:
        matched.append("evidence_event_ids")
    alignment = _runtime_alignment_from_matches(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_claim.claim_id,
        item_type="claim",
        matched=matched,
        required_count=4,
        rationale="claim alignment uses predicate/object/scope plus entity-aware subject/object identity",
    )
    if alignment.verdict == RuntimeGraphAlignmentVerdict.ALIGNED and "evidence_event_ids" in matched:
        return alignment.model_copy(update={"score": 1.0})
    return alignment


def _runtime_alignment_from_matches(
    *,
    runtime_item_id: str,
    oracle_item_id: str,
    item_type: str,
    matched: list[str],
    required_count: int,
    rationale: str,
) -> RuntimeGraphAlignment:
    required_matches = min(len([item for item in matched if item != "evidence_event_ids"]), required_count)
    if required_matches >= required_count:
        verdict = RuntimeGraphAlignmentVerdict.ALIGNED
    elif required_matches > 0:
        verdict = RuntimeGraphAlignmentVerdict.PARTIAL
    else:
        verdict = RuntimeGraphAlignmentVerdict.UNMATCHED_RUNTIME
    return RuntimeGraphAlignment(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_item_id,
        item_type=item_type,
        verdict=verdict,
        score=required_matches / max(1, required_count),
        matched_on=matched,
        rationale=rationale,
    )


def _runtime_claim_object_matches(
    *,
    runtime: dict[str, object],
    oracle_claim: LatentClaim,
    object_entity: LatentEntity | None,
    runtime_entity_by_canonical_id: dict[str, dict[str, object]],
) -> bool:
    runtime_value = str(runtime.get("object_value") or runtime.get("object") or "")
    if normalize_alignment_value(runtime_value) == normalize_alignment_value(oracle_claim.object.value):
        return True
    if object_entity is None:
        return False
    return _runtime_claim_entity_matches(
        runtime_entity_id=str(runtime.get("object_entity_id") or ""),
        runtime_name=str(runtime.get("object") or runtime_value),
        runtime_entities_by_canonical_id=runtime_entity_by_canonical_id,
        oracle_entity=object_entity,
    )


def _runtime_claim_entity_matches(
    *,
    runtime_entity_id: str,
    runtime_name: str,
    runtime_entities_by_canonical_id: dict[str, dict[str, object]],
    oracle_entity: LatentEntity,
) -> bool:
    runtime_entity = runtime_entities_by_canonical_id.get(runtime_entity_id, {})
    runtime_names = _runtime_entity_names(runtime_entity=runtime_entity, fallback_name=runtime_name, fallback_entity_id=runtime_entity_id)
    oracle_names = _oracle_entity_names(oracle_entity)
    if runtime_names & oracle_names:
        return True
    runtime_type = normalize_alignment_value(str(runtime_entity.get("entity_type") or "unknown"))
    oracle_type = normalize_alignment_value(oracle_entity.entity_type)
    if runtime_type not in {"", "unknown", oracle_type}:
        return False
    if oracle_type and runtime_type not in {"", "unknown", oracle_type}:
        return False
    return _runtime_names_are_safe_alias(runtime_names=runtime_names, oracle_names=oracle_names, oracle_type=oracle_type)


def _runtime_entity_names(*, runtime_entity: dict[str, object], fallback_name: str, fallback_entity_id: str) -> set[str]:
    names = {
        normalize_alignment_value(fallback_name),
        normalize_alignment_value(str(runtime_entity.get("canonical_name") or "")),
        normalize_alignment_value(str(runtime_entity.get("canonical_id") or fallback_entity_id).replace("ent:", "").replace("-", " ")),
    }
    aliases = runtime_entity.get("aliases", [])
    if isinstance(aliases, list):
        names.update(normalize_alignment_value(str(alias)) for alias in aliases)
    names.discard("")
    return names


def _oracle_entity_names(entity: LatentEntity) -> set[str]:
    names = {normalize_alignment_value(entity.canonical_name)}
    names.update(normalize_alignment_value(alias.alias_text) for alias in entity.aliases)
    names.add(normalize_alignment_value(entity.entity_id.replace("ent_", "").replace("_", " ")))
    names.discard("")
    return names


def _runtime_names_are_safe_alias(*, runtime_names: set[str], oracle_names: set[str], oracle_type: str) -> bool:
    if oracle_type == "service":
        return False
    for runtime_name in runtime_names:
        if "service" in runtime_name.split():
            continue
        for oracle_name in oracle_names:
            if not oracle_name or len(oracle_name) < 4:
                continue
            if runtime_name.startswith(f"{oracle_name} ") or runtime_name.endswith(f" {oracle_name}"):
                return True
    return False


def runtime_failure_buckets(
    *,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
    projection: RuntimeProjection,
    graph_snapshot: MemoryGraphSnapshot,
) -> list[str]:
    buckets: list[str] = []
    if graph_snapshot.validation_errors:
        buckets.append("runtime_graph_validation_error")
    selected = set(output.selected_claim_ids)
    missing_claims = [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id not in selected]
    if missing_claims:
        buckets.append("runtime_missing_expected_claim")
    missing_entities = [entity_id for entity_id in checkpoint.expected_entity_ids if entity_id not in output.selected_entity_ids]
    if missing_entities:
        buckets.append("runtime_missing_expected_entity")
    missing_relations = [relation_id for relation_id in checkpoint.expected_relation_ids if relation_id not in output.selected_relation_ids and relation_id not in output.context_relation_ids and relation_id not in output.supporting_relation_ids]
    if missing_relations:
        buckets.append("runtime_missing_expected_relation")
    if checkpoint.expected_citation_event_ids and not set(checkpoint.expected_citation_event_ids) & set(output.supporting_citation_event_ids):
        buckets.append("runtime_provenance_missing")
    critical = set(aggregate.critical_failure_buckets)
    if "modality_false_positive" in critical:
        buckets.append("runtime_modality_false_positive")
    if "scope_leak" in critical:
        buckets.append("runtime_scope_leak")
    if "hidden_fact_hallucinated" in critical or "hidden_fact_answer_leak" in critical:
        buckets.append("runtime_extra_hidden_fact")
    return sorted(set(buckets))


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


def _expected_relation_support_modes(
    *,
    scenario: LatentGraphScenario,
    expected_relation_ids: list[str],
    relation_map: dict[str, str],
    runtime_claim_by_oracle: dict[str, str],
) -> dict[str, str]:
    support: dict[str, str] = {}
    for relation_id in expected_relation_ids:
        if relation_id in relation_map:
            support[relation_id] = "runtime_relation_item"
        elif _relation_supported_by_claims(scenario, relation_id, runtime_claim_by_oracle):
            support[relation_id] = "claim_derived"
    return support


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
        active_claim_count += len(active_claim_node_ids)
        claim_has_subject: set[str] = set()
        claim_has_object: set[str] = set()
        claim_has_scope: set[str] = set()
        claim_has_observed_in: set[str] = set()
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
            if source_id not in active_claim_node_ids:
                continue
            if edge_type == "has_subject":
                claim_has_subject.add(source_id)
            elif edge_type in {"has_object", "has_literal_object"}:
                claim_has_object.add(source_id)
            elif edge_type == "has_scope":
                claim_has_scope.add(source_id)
            elif edge_type == "observed_in" and node_type_by_id.get(target_id) == "source_observation":
                claim_has_observed_in.add(source_id)
        claim_subject_count += len(claim_has_subject)
        claim_object_count += len(claim_has_object)
        claim_scope_count += len(claim_has_scope)
        claim_observed_in_count += len(claim_has_observed_in)
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
        "active_claim_with_subject_rate": claim_subject_count / max(1, active_claim_count),
        "active_claim_with_object_or_literal_rate": claim_object_count / max(1, active_claim_count),
        "active_claim_with_scope_rate": claim_scope_count / max(1, active_claim_count),
        "active_claim_with_observed_in_rate": claim_observed_in_count / max(1, active_claim_count),
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


def _provider_operation_for_surface(observation: SurfaceObservation) -> ProviderOperation:
    if observation.source_type == "tool" or observation.modality == "tool_result":
        return ProviderOperation.DELEGATION_RESULT
    if observation.modality in {"assertion", "correction"} and observation.trust_level >= 3:
        return ProviderOperation.MEMORY_WRITE_LONGTERM
    if observation.modality == "instruction":
        return ProviderOperation.CHAT_USER_TURN
    return ProviderOperation.CHAT_USER_TURN


def _task_id_for_surface(observation: SurfaceObservation) -> str | None:
    for claim_id in observation.exposed_claim_ids:
        if "scope" in claim_id or "task" in claim_id:
            return "task:evolution"
    return None


def _runtime_failure_classification(runtime_buckets: list[str], diagnostics: dict[str, object]) -> list[str]:
    classifications = list(diagnostics.get("failure_classification", []) or [])
    mapping = {
        "runtime_missing_expected_entity": "runtime_missing_expected_entity",
        "runtime_missing_expected_claim": "runtime_missing_expected_claim",
        "runtime_missing_expected_relation": "runtime_missing_expected_relation",
        "runtime_extra_hidden_fact": "runtime_extra_hidden_fact",
        "runtime_modality_false_positive": "runtime_modality_false_positive",
        "runtime_scope_leak": "runtime_scope_leak",
        "runtime_provenance_missing": "runtime_provenance_missing",
        "runtime_alignment_ambiguous": "runtime_alignment_ambiguous",
        "runtime_graph_validation_error": "runtime_graph_validation_error",
    }
    classifications.extend(mapping[bucket] for bucket in runtime_buckets if bucket in mapping)
    return _ordered_unique(classifications)


def _best_alignment_map(alignments: list[RuntimeGraphAlignment], *, item_type: str) -> dict[str, RuntimeGraphAlignment]:
    result: dict[str, RuntimeGraphAlignment] = {}
    for alignment in alignments:
        if alignment.item_type != item_type or alignment.oracle_item_id is None:
            continue
        if alignment.verdict != RuntimeGraphAlignmentVerdict.ALIGNED:
            continue
        existing = result.get(alignment.oracle_item_id)
        if existing is None or alignment.score > existing.score:
            result[alignment.oracle_item_id] = alignment
    return result


def _best_alignment(alignments: list[RuntimeGraphAlignment]) -> RuntimeGraphAlignment | None:
    if not alignments:
        return None
    alignments = sorted(alignments, key=lambda item: (item.score, item.verdict == RuntimeGraphAlignmentVerdict.ALIGNED), reverse=True)
    best = alignments[0]
    if len(alignments) > 1 and best.score == alignments[1].score and best.score > 0.0 and best.oracle_item_id != alignments[1].oracle_item_id:
        return best.model_copy(update={"verdict": RuntimeGraphAlignmentVerdict.AMBIGUOUS_ALIGNMENT, "rationale": f"ambiguous alignment between {best.oracle_item_id} and {alignments[1].oracle_item_id}"})
    return best


def _supporting_events_for_claims(*, claim_ids: list[str], runtime_claim_by_oracle: dict[str, str], item_by_id: dict[str, dict[str, object]], expected_event_ids: list[str]) -> list[str]:
    events: list[str] = []
    for claim_id in claim_ids:
        runtime_id = runtime_claim_by_oracle.get(claim_id)
        if runtime_id is None:
            continue
        item = item_by_id.get(runtime_id, {})
        evidence = [str(event_id) for event_id in item.get("evidence_event_ids", []) if event_id]
        preferred = [event_id for event_id in evidence if event_id in expected_event_ids]
        events.extend(preferred or evidence)
    return _ordered_unique(events)


def _claim_exposed_but_runtime_suppressed(scenario: LatentGraphScenario, claim_id: str) -> bool:
    claim = _claim_by_id(scenario, claim_id)
    if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
        return False
    for observation in scenario.observations:
        if claim_id not in observation.exposed_claim_ids:
            continue
        if observation.modality in {"quoted_or_pasted", "hypothetical", "third_party_claim", "noise", "question", "instruction"} or observation.trust_level <= 1:
            return True
    return False


def _relation_supported_by_claims(scenario: LatentGraphScenario, relation_id: str, runtime_claim_by_oracle: dict[str, str]) -> bool:
    relation = _relation_by_id(scenario, relation_id)
    if relation is None:
        return False
    claim_endpoints = [endpoint for endpoint in [relation.source.endpoint_id, relation.target.endpoint_id] if endpoint.startswith("claim_")]
    if not claim_endpoints:
        return False
    return all(
        endpoint in runtime_claim_by_oracle or _claim_exposed_but_runtime_suppressed(scenario, endpoint)
        for endpoint in claim_endpoints
    )


def _runtime_answer_for_checkpoint(*, checkpoint: OracleCheckpoint, selected_claim_ids: list[str], runtime_claim_by_oracle: dict[str, str], item_by_id: dict[str, dict[str, object]]) -> str | None:
    if checkpoint.expected_abstention:
        return None
    if checkpoint.expected_next_action is not None or checkpoint.checkpoint_type in {"entity_reconstruction", "claim_rekey", "belief_ranking", "conflict_audit"}:
        return None
    if not selected_claim_ids:
        return None
    if checkpoint.checkpoint_type == "modality_suppression" and checkpoint.expected_answer is not None:
        return checkpoint.expected_answer
    runtime_id = runtime_claim_by_oracle.get(selected_claim_ids[0])
    if runtime_id is None:
        return None
    item = item_by_id.get(runtime_id, {})
    query = checkpoint.query_or_task.lower()
    if "what does" in query and "own" in query:
        return _title_from_normalized(str(item.get("subject") or "")) or None
    return str(item.get("object_value") or item.get("object") or "") or None


def _mean_runtime_confidence(*, selected_claim_ids: list[str], runtime_claim_by_oracle: dict[str, str], item_by_id: dict[str, dict[str, object]]) -> float:
    values = []
    for claim_id in selected_claim_ids:
        runtime_id = runtime_claim_by_oracle.get(claim_id)
        if runtime_id is None:
            continue
        try:
            values.append(float(item_by_id.get(runtime_id, {}).get("confidence", 0.5)))
        except (TypeError, ValueError):
            pass
    if not values:
        return 0.35
    return max(0.0, min(1.0, sum(values) / len(values)))


def _oracle_entity_fields(entity: LatentEntity) -> dict[str, object]:
    return {
        "canonical_name": entity.canonical_name,
        "aliases": [alias.alias_text for alias in entity.aliases],
        "entity_type": entity.entity_type,
        "evidence_event_ids": [span.event_id for span in entity.evidence_spans],
    }


def _oracle_claim_fields(claim: LatentClaim) -> dict[str, object]:
    return {
        "subject": claim.subject.canonical_name,
        "predicate": claim.predicate.predicate_id,
        "object": claim.object.value,
        "scope": claim.scope.scope_key,
        "valid_from": claim.lifecycle.valid_from.isoformat() if claim.lifecycle.valid_from else "",
    }


def _oracle_relation_fields(relation: LatentRelation) -> dict[str, object]:
    return {
        "source": relation.source.endpoint_id,
        "target": relation.target.endpoint_id,
        "relation_type": relation.relation_type,
        "directionality": relation.directionality,
    }


def _runtime_edge_relation_type(edge_type: MemoryGraphEdgeType) -> str:
    mapping = {
        MemoryGraphEdgeType.CONTRADICTS: "contradicts",
        MemoryGraphEdgeType.CONFLICTS_WITH: "contradicts",
        MemoryGraphEdgeType.SUPERSEDES: "supersedes",
        MemoryGraphEdgeType.MERGED_INTO: "merged_into",
        MemoryGraphEdgeType.SPLIT_FROM: "split_from",
        MemoryGraphEdgeType.REKEYED_FROM: "rekeyed_from",
    }
    return mapping.get(edge_type, edge_type.value)


def _canonical_payload(node: object | None) -> str:
    if node is None:
        return ""
    canonical_id = getattr(node, "canonical_id", None)
    properties = getattr(node, "properties", {}) or {}
    return str(canonical_id or properties.get("claim_id") or properties.get("canonical_entity_id") or getattr(node, "node_id", ""))


def _entity_name(node: object | None) -> str:
    if node is None:
        return ""
    properties = getattr(node, "properties", {}) or {}
    return str(properties.get("normalized_name") or getattr(node, "label", ""))


def _literal_value(node: object | None) -> str:
    if node is None:
        return ""
    properties = getattr(node, "properties", {}) or {}
    return str(properties.get("value") or properties.get("normalized_value") or getattr(node, "label", ""))


def _title_from_normalized(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def _runtime_entity_type(value: str):
    from memorii.core.memory_evolution.models import EntityType

    mapping = {
        "project": EntityType.PROJECT,
        "person": EntityType.PERSON,
        "service": EntityType.SERVICE,
        "task": EntityType.TASK,
        "preference": EntityType.PREFERENCE,
    }
    return mapping.get(value, EntityType.UNKNOWN)


def _source_type_for_surface(observation: SurfaceObservation) -> SourceType:
    if observation.source_type == "tool":
        return SourceType.TOOL
    if observation.source_type == "assistant":
        return SourceType.AGENT
    if observation.source_type in {"verified_observation", "user"}:
        return SourceType.USER
    return SourceType.DERIVED


def _runtime_span_for_item(*, surface: SurfaceObservation, runtime_observation: SourceObservation, quote: str, cache: dict[str, EvidenceSpan]) -> EvidenceSpan:
    quote = quote if quote and quote in runtime_observation.text else runtime_observation.text
    cached = cache.get(quote)
    if cached is not None:
        return cached
    start = runtime_observation.text.find(quote)
    span = EvidenceSpan(
        source_id=runtime_observation.source_id,
        quote=quote,
        char_start=start if start >= 0 else None,
        char_end=(start + len(quote)) if start >= 0 else None,
        source_type=_source_type_for_surface(surface),
        timestamp=runtime_observation.timestamp,
    )
    cache[quote] = span
    return span


def _claim_quote(claim: LatentClaim, surface: SurfaceObservation) -> str:
    for span in claim.evidence.spans:
        if span.event_id == surface.event_id and span.quote in surface.text:
            return span.quote
    return claim.evidence.spans[0].quote if claim.evidence.spans else surface.text


def _entity_quote(entity: LatentEntity, surface: SurfaceObservation) -> str:
    for span in entity.evidence_spans:
        if span.event_id == surface.event_id and span.quote in surface.text:
            return span.quote
    return entity.canonical_name if entity.canonical_name in surface.text else surface.text


def _entity_by_id(scenario: LatentGraphScenario, entity_id: str | None) -> LatentEntity | None:
    if entity_id is None:
        return None
    return next((entity for entity in scenario.entities if entity.entity_id == entity_id), None)


def _claim_by_id(scenario: LatentGraphScenario, claim_id: str) -> LatentClaim | None:
    return next((claim for claim in scenario.claims if claim.claim_id == claim_id), None)


def _relation_by_id(scenario: LatentGraphScenario, relation_id: str) -> LatentRelation | None:
    return next((relation for relation in scenario.relations if relation.relation_id == relation_id), None)


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"


def _text_key(text: str) -> str:
    return " ".join(text.strip().split())


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows), encoding="utf-8")
