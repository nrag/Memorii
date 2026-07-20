"""Runtime benchmark suite orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

from memorii.core.benchmark.artifact_rows import (
    CheckpointDecisionTraceSection,
    CheckpointDiagnosticsPayload,
    CheckpointDiagnosticsSection,
    CheckpointHorizonSection,
    CheckpointVerdictSection,
    DecisionMode,
    FinalOutputSource,
    RuntimeCheckpointResultRow,
    RuntimeDiagnosticsSection,
    RuntimeExtractorOutput,
    RuntimeExtractorTracePayload,
    RuntimeExtractorTraceRow,
    RuntimeGraphAlignmentRow,
    SimScenarioResultRow,
    checkpoint_warning_buckets,
)
from memorii.core.benchmark.memory_evolution_runtime.artifacts import (
    _horizon_distance_bucket,
    _interference_count_bucket,
    _source_event_age_days_bucket,
)
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection import (
    _runtime_relation_support_rows,
    project_runtime_checkpoint,
    runtime_failure_buckets,
)
from memorii.core.benchmark.memory_evolution_runtime.execution_state_projection import (
    _action_alignment_failure_reason,
    _runtime_action_support_rows,
)
from memorii.core.benchmark.memory_evolution_runtime.graph_items import (
    _claim_quote,
    _entity_quote,
    _runtime_entity_type,
    _runtime_span_for_item,
    graph_items_from_snapshot,
)
from memorii.core.benchmark.memory_evolution_runtime.ingestion import IngestionContext, ingest_surface_observation
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeGraphItemRow,
    RuntimeGraphSnapshotRow,
    RuntimeProjection,
    RuntimeSuiteRows,
)
from memorii.core.benchmark.memory_evolution_runtime.utils import (
    _claim_by_id,
    _entity_by_id,
    _ordered_unique,
    _stable_id,
    _text_key,
)
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    LatentClaim,
    LatentGraphScenario,
    ObservabilityLabel,
    OracleCheckpoint,
    SimSystemOutput,
    SurfaceObservation,
    judge_sim_checkpoint,
    sim_checkpoint_diagnostics,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.calibration.alignment import normalize_alignment_value
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import DecisionModeName, LLMDecisionRuntimeConfig, LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution import (
    ClaimKey,
    EntityMention,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionRun,
    GraphAuditRequest,
    HybridMemoryExtractor,
    LLMMemoryExtractor,
    MemoryExtractor,
    MemoryGraphSnapshot,
    MemoryQueryRequest,
    RetrievalPurpose,
    RuleMemoryExtractor,
    SourceObservation,
)
from memorii.core.memory_evolution.models import ConfidenceComponents, MemoryScope, memory_scope_from_observation
from memorii.core.memory_plane import MemoryPlaneService
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

    def extract(
        self, observations: list[SourceObservation]
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        self.calls += 1
        run_id = _stable_id("runtime-fake-extraction", "|".join(obs.source_id for obs in observations))
        entity_by_scope: dict[tuple[str, str], EntityMention] = {}
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
                span = _runtime_span_for_item(
                    surface=surface,
                    runtime_observation=observation,
                    quote=_entity_quote(entity, surface),
                    cache=span_cache,
                )
                mention = EntityMention(
                    entity_id=entity.entity_id,
                    mention_text=entity.canonical_name,
                    normalized_name=normalize_alignment_value(entity.canonical_name),
                    aliases=[alias.alias_text for alias in entity.aliases],
                    entity_type=_runtime_entity_type(entity.entity_type),
                    evidence_spans=[span],
                    confidence=entity.confidence.calibrated,
                    scope=memory_scope_from_observation(observation),
                )
                entity_by_scope[(mention.entity_id, mention.scope.scope_key)] = mention
            for claim_id in surface.exposed_claim_ids:
                claim = _claim_by_id(self._scenario, claim_id)
                if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
                    continue
                quote = _claim_quote(claim, surface)
                span = _runtime_span_for_item(
                    surface=surface, runtime_observation=observation, quote=quote, cache=span_cache
                )
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
                claim_scope = _runtime_scope_for_claim(claim)
                for entity_id in [claim.subject.entity_id, claim.object.entity_id]:
                    entity = _entity_by_id(self._scenario, entity_id) if entity_id else None
                    if entity is None or entity.observability == ObservabilityLabel.HIDDEN:
                        continue
                    entity_by_scope.setdefault(
                        (entity.entity_id, claim_scope.scope_key),
                        EntityMention(
                            entity_id=entity.entity_id,
                            mention_text=entity.canonical_name,
                            normalized_name=normalize_alignment_value(entity.canonical_name),
                            aliases=[alias.alias_text for alias in entity.aliases],
                            entity_type=_runtime_entity_type(entity.entity_type),
                            evidence_spans=[span],
                            confidence=entity.confidence.calibrated,
                            scope=claim_scope,
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
                            task_id=(claim.scope.scope_key if claim.scope.scope_key != "global" else None),
                            scope_key=claim.scope.scope_key,
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
            entity_ids=sorted({entity_id for entity_id, _scope_key in entity_by_scope}),
            claim_ids=[claim.claim_id for claim in claims],
            action_ids=[action.action_id for action in actions],
            errors=errors,
        )
        return run, list(entity_by_scope.values()), claims, actions

    def _surface_for_runtime_observation(self, observation: SourceObservation) -> SurfaceObservation | None:
        candidates = self._observations_by_text.get(_text_key(observation.text), [])
        return candidates[0] if candidates else None


def _runtime_scope_for_claim(claim: LatentClaim) -> MemoryScope:
    """Translate simulator scope into the runtime's server-owned scope model."""

    return MemoryScope(
        scope_key=claim.scope.scope_key,
        task_id=claim.scope.task_id,
        session_id=claim.scope.session_id,
    )


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

    def extract(
        self, observations: list[SourceObservation]
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
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
                "failure_classification": _classify_extraction_failure(run.errors),
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
    live_client_factory: Callable[[LLMRuntimeConfig], LLMStructuredClient] = LLMClientFactory.from_config,
) -> MemoryExtractor:
    if effective_mode == "rule":
        delegate: MemoryExtractor = RuleMemoryExtractor()
    elif dry_run:
        delegate = OracleVisibleMemoryExtractor(scenario=scenario)
    else:
        runner = PromptLLMRunner(client=live_client_factory(runtime_config), config=runtime_config)
        llm_extractor = LLMMemoryExtractor(runner=runner, prompt_root=prompt_root)
        if effective_mode == "llm":
            delegate = llm_extractor
        elif effective_mode == "hybrid":
            delegate = HybridMemoryExtractor(llm_extractor=llm_extractor)
        else:
            delegate = RuleMemoryExtractor()
    return RecordingMemoryExtractor(delegate=delegate)


def validate_runtime_live_safety(
    *, mode: str, dry_run: bool, allow_live: bool
) -> tuple[DecisionMode, LLMRuntimeConfig]:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    decision_config = (
        LLMDecisionRuntimeConfig(mode=_decision_mode(mode))
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
        if not dry_run:
            runtime_config = runtime_config.model_copy(update={"max_retries": 0})
    return effective_mode, runtime_config


def run_runtime_scenarios(
    *,
    scenarios: list[LatentGraphScenario],
    mode: str,
    dry_run: bool,
    allow_live: bool,
    prompt_root: Path,
    live_client_factory: Callable[[LLMRuntimeConfig], LLMStructuredClient] = LLMClientFactory.from_config,
) -> RuntimeSuiteRows:
    requested_mode = _decision_mode(mode)
    effective_mode, runtime_config = validate_runtime_live_safety(mode=mode, dry_run=dry_run, allow_live=allow_live)
    scenario_rows: list[SimScenarioResultRow] = []
    checkpoint_rows: list[RuntimeCheckpointResultRow] = []
    judge_rows: list[JudgeAggregate] = []
    llm_rows: list[RuntimeExtractorTraceRow] = []
    graph_snapshots: list[RuntimeGraphSnapshotRow] = []
    graph_items: list[RuntimeGraphItemRow] = []
    alignments: list[RuntimeGraphAlignmentRow] = []
    runtime_failures: list[RuntimeCheckpointResultRow] = []

    for scenario in scenarios:
        extractor = build_runtime_extractor(
            scenario=scenario,
            effective_mode=effective_mode,
            dry_run=dry_run,
            runtime_config=runtime_config,
            prompt_root=prompt_root,
            live_client_factory=live_client_factory,
        )
        memory_plane = MemoryPlaneService()
        provider = ProviderMemoryService(
            memory_plane=memory_plane,
            memory_evolution_enabled=True,
            memory_evolution_extractor=extractor,
        )
        source_id_to_event_id: dict[str, str] = {}
        ordered_observations = sorted(scenario.observations, key=lambda item: (item.timestamp, item.event_id))
        observation_index = 0
        before_record_ids: set[str] = set()
        evolution_service = provider.memory_evolution_service
        if evolution_service is None:
            raise RuntimeError("runtime memory evolution service was not initialized")
        scenario_checkpoint_rows: list[RuntimeCheckpointResultRow] = []
        extractor_provider_successes = 0
        extractor_provider_failures = 0
        extractor_fallbacks = 0
        ingestion_context = IngestionContext()
        ordered_checkpoints = sorted(scenario.checkpoints, key=lambda item: (item.timestamp, item.checkpoint_id))
        for checkpoint_index, checkpoint in enumerate(ordered_checkpoints):
            checkpoint_run_start = len(_recorded_runs(extractor))
            while (
                observation_index < len(ordered_observations)
                and ordered_observations[observation_index].timestamp <= checkpoint.timestamp
            ):
                observation = ordered_observations[observation_index]
                source_id_to_event_id.update(
                    ingest_surface_observation(
                        provider=provider,
                        memory_plane=memory_plane,
                        observation=observation,
                        context=ingestion_context,
                        before_ids=before_record_ids,
                    )
                )
                before_record_ids = {record.memory_id for record in memory_plane.list_records()}
                observation_index += 1
            work_state = evolution_service.derive_work_state()
            # Keep the benchmark on the provider-facing production retrieval
            # contract. The benchmark may judge the result, but it must not
            # bypass the provider's decision boundary.
            is_graph_audit = checkpoint.checkpoint_type in {
                "entity_reconstruction",
                "conflict_audit",
                "claim_rekey",
            }
            request_task_id = checkpoint.request_task_id or ingestion_context.task_id
            request_session_id = checkpoint.request_session_id or ingestion_context.session_id
            request_user_id = checkpoint.request_user_id or ingestion_context.user_id
            request_scope_key = checkpoint.request_scope_key or request_task_id or request_session_id or request_user_id
            if is_graph_audit:
                retrieval_request: MemoryQueryRequest | GraphAuditRequest = GraphAuditRequest(
                    query=checkpoint.query_or_task,
                    reference_time=checkpoint.timestamp,
                    top_k=8,
                    include_context=True,
                    include_conflicts=True,
                    purpose=RetrievalPurpose.GRAPH_AUDIT,
                    scope_mode="full",
                    query_language=checkpoint.query_language,
                    scope=MemoryScope(
                        scope_key=request_scope_key or "global",
                        task_id=request_task_id,
                        session_id=request_session_id,
                        user_id=request_user_id,
                    ),
                )
            else:
                retrieval_request = MemoryQueryRequest(
                    query=checkpoint.query_or_task,
                    reference_time=checkpoint.timestamp,
                    top_k=8,
                    include_context=True,
                    include_conflicts=True,
                    purpose=(
                        RetrievalPurpose.EXECUTION
                        if checkpoint.checkpoint_type == "execution_continuation"
                        else RetrievalPurpose.ANSWER
                    ),
                    query_language=checkpoint.query_language,
                    scope=MemoryScope(
                        scope_key=request_scope_key or "global",
                        task_id=request_task_id,
                        session_id=request_session_id,
                        user_id=request_user_id,
                    ),
                )
            retrieval_decision = provider.retrieve_evolution_decision(retrieval_request)
            graph_snapshot = evolution_service.retrieve_graph_snapshot()
            normalization = graph_items_from_snapshot(
                scenario_id=scenario.scenario_id,
                snapshot=graph_snapshot,
                source_id_to_event_id=source_id_to_event_id,
            )
            runtime_graph_items = normalization.items
            graph_snapshots.append(
                RuntimeGraphSnapshotRow(
                    scenario_id=scenario.scenario_id,
                    checkpoint_id=checkpoint.checkpoint_id,
                    checkpoint_index=checkpoint_index,
                    is_terminal=checkpoint_index == len(ordered_checkpoints) - 1,
                    snapshot_id=graph_snapshot.snapshot_id,
                    nodes=list(graph_snapshot.nodes),
                    edges=list(graph_snapshot.edges),
                    validation_errors=[
                        *graph_snapshot.validation_errors,
                        *normalization.validation_errors,
                    ],
                    generated_at=graph_snapshot.generated_at.isoformat(),
                    source_run_id=graph_snapshot.source_run_id,
                )
            )
            graph_items.extend(runtime_graph_items)
            recorded_runs = _recorded_runs(extractor)
            extractor_provider_successes = sum(1 for run in recorded_runs if run.get("success") is True)
            extractor_provider_failures = sum(1 for run in recorded_runs if run.get("success") is not True)
            extractor_fallbacks = sum(1 for run in recorded_runs if run.get("fallback_used") is True)
            projection = project_runtime_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                graph_snapshot=graph_snapshot,
                graph_items=runtime_graph_items,
                source_id_to_event_id=source_id_to_event_id,
                work_state=work_state,
                retrieval_decision=retrieval_decision,
            )
            alignments.extend(
                RuntimeGraphAlignmentRow.from_alignment(
                    alignment,
                    scenario_id=scenario.scenario_id,
                    checkpoint_id=checkpoint.checkpoint_id,
                )
                for alignment in projection.alignments
            )
            raw_output = projection.output
            output = raw_output
            aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
            diagnostics = sim_checkpoint_diagnostics(
                scenario=scenario, checkpoint=checkpoint, output=output, aggregate=aggregate
            )
            runtime_buckets = runtime_failure_buckets(
                checkpoint=checkpoint,
                output=output,
                aggregate=aggregate,
                projection=projection,
                graph_snapshot=graph_snapshot,
            )
            success = aggregate.verdict.value == "pass" and not runtime_buckets
            checkpoint_runs = _recorded_runs(extractor)[checkpoint_run_start:]
            final_output_source = runtime_final_output_source(
                effective_mode=effective_mode,
                dry_run=dry_run,
                extractor=extractor,
                recorded_runs=checkpoint_runs,
            )
            row = _build_runtime_checkpoint_result_row(
                scenario=scenario,
                checkpoint=checkpoint,
                mode=requested_mode,
                effective_mode=effective_mode,
                final_output_source=final_output_source,
                success=success,
                aggregate=aggregate,
                diagnostics=diagnostics,
                runtime_buckets=runtime_buckets,
                graph_snapshot=graph_snapshot,
                projection=projection,
                raw_output=raw_output,
                output=output,
                provider_successes=extractor_provider_successes,
                provider_failures=extractor_provider_failures,
                fallbacks=extractor_fallbacks,
                fallback_used=any(run.get("fallback_used") is True for run in checkpoint_runs),
            )
            checkpoint_rows.append(row)
            scenario_checkpoint_rows.append(row)
            judge_rows.append(aggregate)
            if not success:
                runtime_failures.append(row)
        extractor_call_rows = extractor_trace_rows(
            scenario=scenario,
            extractor=extractor,
            effective_mode=effective_mode,
            dry_run=dry_run,
        )
        llm_rows.extend(extractor_call_rows)
        scenario_success = all(row.success is True for row in scenario_checkpoint_rows)
        scenario_rows.append(
            SimScenarioResultRow(
                scenario_id=scenario.scenario_id,
                semantic_world_fingerprint=scenario.semantic_world_fingerprint,
                family=scenario.family,
                profile=scenario.profile,
                decision_mode=requested_mode,
                effective_decision_mode=effective_mode,
                checkpoint_count=len(scenario_checkpoint_rows),
                success=scenario_success,
                failure_mode=None if scenario_success else "one_or_more_runtime_checkpoints_failed",
                checkpoints_passed=sum(row.success for row in scenario_checkpoint_rows),
                checkpoints_failed=sum(not row.success for row in scenario_checkpoint_rows),
            )
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
        effective_mode=effective_mode,
        dry_run=dry_run,
    )


def _classify_extraction_failure(errors: list[str]) -> str | None:
    """Classify extraction failures without exposing provider payloads."""

    if not errors:
        return None
    if any(error.startswith("provider_error") or "Provider request failed:" in error for error in errors):
        return "provider_request_error"
    if any("invalid_json" in error for error in errors):
        return "provider_invalid_json"
    if any("schema_validation" in error for error in errors):
        return "provider_schema_validation"
    if any(error.startswith("fallback_used:") for error in errors):
        return "runtime_extractor_fallback"
    return "runtime_extractor_failure"


def _build_runtime_checkpoint_result_row(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    mode: DecisionMode,
    effective_mode: DecisionMode,
    final_output_source: FinalOutputSource,
    success: bool,
    aggregate: JudgeAggregate,
    diagnostics: dict[str, object],
    runtime_buckets: list[str],
    graph_snapshot: MemoryGraphSnapshot,
    projection: RuntimeProjection,
    raw_output: SimSystemOutput,
    output: SimSystemOutput,
    provider_successes: int,
    provider_failures: int,
    fallbacks: int,
    fallback_used: bool,
) -> RuntimeCheckpointResultRow:
    runtime_failure_classification = _runtime_failure_classification(runtime_buckets, diagnostics)
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
        llm_call_made=effective_mode in {"llm", "hybrid"},
        fallback_used=fallback_used,
        fallback_reason="runtime_extractor_fallback" if fallback_used else None,
        final_output_source=final_output_source,
        request_id=f"memory_evolution_runtime:{mode}:{scenario.scenario_id}:{checkpoint.checkpoint_id}",
    )
    diagnostic_section = CheckpointDiagnosticsSection.model_validate(diagnostics)
    typed_candidate_cards = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    warning_buckets = checkpoint_warning_buckets(
        answer_match_type=diagnostic_section.answer_match_type,
        output=output,
    )
    verdict = CheckpointVerdictSection(
        success=success,
        passed=bool(aggregate.verdict.value == "pass" and not runtime_buckets),
        verdict="fail" if runtime_buckets else aggregate.verdict.value,
        score=aggregate.score,
        confidence=aggregate.confidence,
        review_required=aggregate.review_required or bool(runtime_buckets),
        failure_buckets=sorted({*aggregate.critical_failure_buckets, *runtime_buckets}),
        warning_buckets=warning_buckets,
    )
    runtime_section = RuntimeDiagnosticsSection(
        runtime_graph_validation_errors=list(graph_snapshot.validation_errors),
        runtime_relation_support=_runtime_relation_support_rows(projection),
        runtime_action_support=_runtime_action_support_rows(projection),
        runtime_action_alignments=projection.action_alignment_rows,
        runtime_execution_state=projection.execution_state,
        runtime_retrieval_decision=projection.retrieval_decision,
        active_continuation_branch=projection.execution_state.active_continuation_branch,
        suppressed_branch_ids=list(projection.execution_state.suppressed_branch_ids),
        action_alignment_failure_reason=_action_alignment_failure_reason(projection.action_alignment_rows),
    )
    return RuntimeCheckpointResultRow(
        scenario_id=scenario.scenario_id,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_type=checkpoint.checkpoint_type,
        success=verdict.success,
        passed=verdict.passed,
        verdict=verdict.verdict,
        score=verdict.score,
        confidence=verdict.confidence,
        review_required=verdict.review_required,
        failure_buckets=verdict.failure_buckets,
        warning_buckets=verdict.warning_buckets,
        diagnostics=CheckpointDiagnosticsPayload.from_sections(diagnostic_section, runtime_section),
        output=output,
        profile=horizon.profile,
        family=horizon.family,
        decision_mode=decision_trace.decision_mode,
        effective_decision_mode=decision_trace.effective_decision_mode,
        final_output_source=decision_trace.final_output_source,
        phase=horizon.phase,
        horizon_distance=horizon.horizon_distance,
        horizon_distance_bucket=horizon.horizon_distance_bucket,
        interference_count=horizon.interference_count,
        interference_count_bucket=horizon.interference_count_bucket,
        source_event_age_days=horizon.source_event_age_days,
        source_event_age_days_bucket=horizon.source_event_age_days_bucket,
        required_retrieval_view=horizon.required_retrieval_view,
        expected_stage_path=horizon.expected_stage_path,
        query_or_task=horizon.query_or_task,
        llm_call_made=decision_trace.llm_call_made,
        fallback_used=decision_trace.fallback_used,
        fallback_reason=decision_trace.fallback_reason,
        request_id=decision_trace.request_id,
        expected=checkpoint,
        candidate_cards=typed_candidate_cards,
        raw_output=raw_output,
        judge_aggregate=aggregate,
        runtime_failure_buckets=runtime_buckets,
        runtime_failure_classification=runtime_failure_classification,
        scenario_provider_successes=provider_successes,
        scenario_provider_failures=provider_failures,
        scenario_fallbacks=fallbacks,
        provider_successes=provider_successes,
        provider_failures=provider_failures,
        fallbacks=fallbacks,
        provider_count_scope="scenario_extractor_calls",
    )


def extractor_trace_rows(
    *,
    scenario: LatentGraphScenario,
    extractor: MemoryExtractor,
    effective_mode: DecisionMode,
    dry_run: bool,
) -> list[RuntimeExtractorTraceRow]:
    if effective_mode not in {"llm", "hybrid"}:
        return []
    recorded = _recorded_runs(extractor)
    rows: list[RuntimeExtractorTraceRow] = []
    for index, run in enumerate(recorded):
        rows.append(
            RuntimeExtractorTraceRow(
                scenario_id=scenario.scenario_id,
                checkpoint_id=None,
                transition_type="runtime_memory_extraction",
                decision_mode=effective_mode,
                effective_decision_mode=effective_mode,
                final_output_source=_run_output_source(
                    effective_mode=effective_mode,
                    dry_run=dry_run,
                    run=run,
                ),
                trace=RuntimeExtractorTracePayload(
                    provider=str(run.get("provider") or getattr(extractor, "provider", effective_mode)),
                    model=str(run["model"]) if run.get("model") else None,
                    prompt_hash=str(run.get("prompt_hash") or getattr(extractor, "prompt_hash", "")) or None,
                    scenario_id=scenario.scenario_id,
                    call_index=index,
                    input_source_ids=[str(item) for item in _json_sequence(run.get("input_source_ids"))],
                    failure_classification=(
                        str(run["failure_classification"]) if run.get("failure_classification") else None
                    ),
                    errors=[str(item) for item in _json_sequence(run.get("errors"))],
                    entity_count=_nonnegative_count(run.get("entity_count")),
                    claim_count=_nonnegative_count(run.get("claim_count")),
                    action_count=_nonnegative_count(run.get("action_count")),
                    validation_summary=_nonnegative_count_map(run.get("validation_summary")),
                ),
                success=bool(run.get("success")),
                fallback_used=bool(run.get("fallback_used")),
                failure_mode=None if run.get("success") else "runtime_extractor_failure",
                output=RuntimeExtractorOutput(
                    entity_ids=[str(item) for item in _json_sequence(run.get("entity_ids"))],
                    claim_ids=[str(item) for item in _json_sequence(run.get("claim_ids"))],
                    action_ids=[str(item) for item in _json_sequence(run.get("action_ids"))],
                ),
            )
        )
    return rows


def runtime_final_output_source(
    *,
    effective_mode: str,
    dry_run: bool,
    extractor: MemoryExtractor,
    recorded_runs: list[dict[str, object]] | None = None,
) -> FinalOutputSource:
    if effective_mode == "rule":
        return "rule"
    if dry_run:
        return "fake_oracle"
    runs = recorded_runs if recorded_runs is not None else _recorded_runs(extractor)
    if runs:
        sources = {_run_output_source(effective_mode=effective_mode, dry_run=dry_run, run=run) for run in runs}
        if len(sources) == 1:
            return cast(FinalOutputSource, next(iter(sources)))
        return "mixed"
    return "reused_runtime_state"


def _run_output_source(*, effective_mode: str, dry_run: bool, run: dict[str, object]) -> FinalOutputSource:
    if effective_mode == "rule":
        return "rule"
    if dry_run:
        return "fake_oracle"
    if run.get("fallback_used") is True:
        return "rule"
    return "live_llm"


def extractor_fallback_count(extractor: MemoryExtractor) -> int:
    recorded = _recorded_runs(extractor)
    if recorded:
        return sum(1 for run in recorded if run.get("fallback_used"))
    return int(getattr(extractor, "fallbacks", 0))


def _recorded_runs(extractor: MemoryExtractor) -> list[dict[str, object]]:
    recorded = getattr(extractor, "recorded_runs", [])
    if not isinstance(recorded, list):
        return []
    return [run for run in recorded if isinstance(run, dict)]


def _runtime_failure_classification(runtime_buckets: list[str], diagnostics: dict[str, object]) -> list[str]:
    classifications = [str(item) for item in _json_sequence(diagnostics.get("failure_classification"))]
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


def _decision_mode(mode: str) -> DecisionModeName:
    if mode in {"auto", "rule", "llm", "hybrid"}:
        return cast(DecisionModeName, mode)
    raise ValueError(f"Unsupported memory evolution runtime mode: {mode}")


def _json_sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _nonnegative_count(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"expected a non-negative integer count, got {value!r}")
    return value


def _nonnegative_count_map(value: object) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("expected a mapping of non-negative integer counts")
    return {str(key): _nonnegative_count(count) for key, count in value.items()}
