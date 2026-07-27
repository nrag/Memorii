"""Runtime extractor construction and benchmark telemetry."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from memorii.core.benchmark.calibration.alignment import normalize_alignment_value
from memorii.core.benchmark.memory_evolution_runtime.graph_items import (
    claim_quote,
    entity_mention_text,
    entity_quote,
    runtime_entity_type,
    runtime_span_for_item,
)
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeGraphDelta,
    RuntimeIngestionTraceRow,
    RuntimeSourceObservationTrace,
)
from memorii.core.benchmark.memory_evolution_runtime.utils import (
    claim_by_id,
    entity_by_id,
    relation_by_id,
    stable_id,
    text_key,
)
from memorii.core.benchmark.memory_evolution_sim import (
    LatentClaim,
    LatentGraphScenario,
    ObservabilityLabel,
    SurfaceObservation,
)
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution import (
    ClaimKey,
    EnglishRuleMemoryExtractor,
    EntityIdentityRelationType,
    EntityMention,
    EntityType,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractedIdentityRelation,
    ExtractionRun,
    HybridMemoryExtractor,
    LLMMemoryExtractor,
    MemoryEvolutionResult,
    MemoryExtractionProposal,
    MemoryExtractor,
    MemoryGraphEdge,
    MemoryGraphNode,
    SourceObservation,
)
from memorii.core.memory_evolution.extraction_contracts import (
    MemoryExtractionOutput,
    StructuredProposalProvider,
)
from memorii.core.memory_evolution.models import (
    ConfidenceComponents,
    ExtractionFailureCode,
    ExtractionRunStatus,
    FallbackOutcome,
    FinalExtractionSource,
    MemoryScope,
    ProviderAttemptStatus,
    memory_scope_from_observation,
)
from memorii.core.memory_evolution.operation_models import (
    EvolutionFailureCategory,
    EvolutionOperationStatus,
)
from memorii.core.provider.models import ProviderEvolutionOutcome


class RecordedExtractionRun(RuntimeIngestionTraceRow):
    """Validated telemetry for one runtime extraction call."""


class OracleVisibleMemoryExtractor:
    """Dry-run extractor that emits only explicitly visible scenario items."""

    provider = "fake_oracle"
    model = "fake-visible-oracle"
    prompt_hash = "memory_evolution_runtime_fake_extractor:v1"

    def __init__(self, *, scenario: LatentGraphScenario) -> None:
        self._scenario = scenario
        self._observations_by_text: dict[str, list[SurfaceObservation]] = {}
        for observation in scenario.observations:
            self._observations_by_text.setdefault(text_key(observation.text), []).append(observation)
        self.calls = 0
        self.failures = 0
        self.fallbacks = 0

    @property
    def structured_proposal(self) -> MemoryExtractionOutput | None:
        return None

    def extract(self, observations: list[SourceObservation]) -> MemoryExtractionProposal:
        self.calls += 1
        run_id = stable_id("runtime-fake-extraction", "|".join(obs.source_id for obs in observations))
        if not observations:
            return MemoryExtractionProposal(
                run=ExtractionRun(
                    extraction_run_id=run_id,
                    provider=self.provider,
                    model=self.model,
                    prompt_hash=self.prompt_hash,
                    input_source_ids=[],
                    status=ExtractionRunStatus.ABSTAINED,
                    provider_attempt_status=ProviderAttemptStatus.NOT_ATTEMPTED,
                    final_output_source=FinalExtractionSource.NONE,
                )
            )
        entity_by_scope: dict[tuple[str, str], EntityMention] = {}
        claims: list[ExtractedClaim] = []
        actions: list[ExtractedAction] = []
        identity_relations: list[ExtractedIdentityRelation] = []
        errors: list[str] = []
        for observation in observations:
            surface = self._surface_for_runtime_observation(observation)
            if surface is None:
                errors.append(f"unmatched_surface_observation:{observation.source_id}")
                continue
            span_cache: dict[str, EvidenceSpan] = {}
            for entity_id in surface.exposed_entity_ids:
                entity = entity_by_id(self._scenario, entity_id)
                if entity is None or entity.observability == ObservabilityLabel.HIDDEN:
                    continue
                span = runtime_span_for_item(
                    surface=surface,
                    runtime_observation=observation,
                    quote=entity_quote(entity, surface),
                    cache=span_cache,
                )
                mention = EntityMention(
                    entity_id=entity.entity_id,
                    mention_text=entity_mention_text(entity, span.quote),
                    normalized_name=normalize_alignment_value(entity_mention_text(entity, span.quote)),
                    entity_type=runtime_entity_type(entity.entity_type),
                    evidence_spans=[span],
                    confidence=entity.confidence.calibrated,
                    scope=memory_scope_from_observation(observation),
                )
                entity_by_scope[(mention.entity_id, mention.scope.scope_key)] = mention
            for claim_id in surface.exposed_claim_ids:
                claim = claim_by_id(self._scenario, claim_id)
                if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
                    continue
                quote = claim_quote(claim, surface)
                span = runtime_span_for_item(
                    surface=surface,
                    runtime_observation=observation,
                    quote=quote,
                    cache=span_cache,
                )
                claims.append(
                    ExtractedClaim(
                        claim_id=claim.claim_id,
                        claim_key=ClaimKey(
                            subject_entity_id=claim.subject.entity_id,
                            predicate_id=claim.predicate.predicate_id,
                            scope=runtime_scope_for_claim(claim),
                            qualifier_key="default",
                        ),
                        object_value=claim.object.value,
                        object_entity_id=claim.object.entity_id,
                        valid_from=claim.lifecycle.valid_from,
                        valid_to=(
                            claim.lifecycle.valid_to
                            if claim.lifecycle.valid_to is not None
                            and observation.timestamp >= claim.lifecycle.valid_to
                            else None
                        ),
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
                claim_scope = runtime_scope_for_claim(claim)
                for entity_id in (claim.subject.entity_id, claim.object.entity_id):
                    entity = entity_by_id(self._scenario, entity_id) if entity_id else None
                    if entity is None or entity.observability == ObservabilityLabel.HIDDEN:
                        continue
                    entity_by_scope.setdefault(
                        (entity.entity_id, claim_scope.scope_key),
                        EntityMention(
                            entity_id=entity.entity_id,
                            mention_text=entity_mention_text(entity, span.quote),
                            normalized_name=normalize_alignment_value(entity_mention_text(entity, span.quote)),
                            entity_type=runtime_entity_type(entity.entity_type),
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
                            scope=runtime_scope_for_claim(claim),
                            evidence_spans=[span],
                            extraction_run_id=run_id,
                        )
                    )
            for relation_id in surface.exposed_relation_ids:
                relation = relation_by_id(self._scenario, relation_id)
                if (
                    relation is None
                    or relation.observability == ObservabilityLabel.HIDDEN
                    or relation.relation_type not in {"alias_of", "same_as", "split_from", "merged_into"}
                ):
                    continue
                relation_span = runtime_span_for_item(
                    surface=surface,
                    runtime_observation=observation,
                    quote=next(
                        (
                            span.quote
                            for span in relation.evidence_spans
                            if span.event_id == surface.event_id and span.quote
                        ),
                        surface.text,
                    ),
                    cache=span_cache,
                )
                relation_scope = memory_scope_from_observation(observation)
                endpoint_ids: list[str] = []
                for endpoint in (relation.source, relation.target):
                    latent_entity = (
                        entity_by_id(self._scenario, endpoint.endpoint_id)
                        if endpoint.endpoint_type == "entity"
                        else None
                    )
                    endpoint_id = latent_entity.entity_id if latent_entity is not None else endpoint.endpoint_id
                    endpoint_name = (
                        entity_mention_text(latent_entity, relation_span.quote)
                        if latent_entity is not None
                        else endpoint.label
                    )
                    endpoint_type = (
                        runtime_entity_type(latent_entity.entity_type)
                        if latent_entity is not None
                        else EntityType.UNKNOWN
                    )
                    endpoint_ids.append(endpoint_id)
                    entity_by_scope.setdefault(
                        (endpoint_id, relation_scope.scope_key),
                        EntityMention(
                            entity_id=endpoint_id,
                            mention_text=endpoint_name,
                            normalized_name=normalize_alignment_value(endpoint_name),
                            entity_type=endpoint_type,
                            evidence_spans=[relation_span],
                            confidence=relation.confidence.calibrated,
                            scope=relation_scope,
                        ),
                    )
                identity_relations.append(
                    ExtractedIdentityRelation(
                        relation_id=relation.relation_id,
                        relation_type=EntityIdentityRelationType(relation.relation_type),
                        source_entity_id=endpoint_ids[0],
                        target_entity_id=endpoint_ids[1],
                        evidence_spans=[relation_span],
                        confidence=relation.confidence.calibrated,
                        scope=relation_scope,
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
            identity_relation_ids=[relation.relation_id for relation in identity_relations],
            status=ExtractionRunStatus.PARTIAL if errors else ExtractionRunStatus.SUCCEEDED,
            failure_code=ExtractionFailureCode.OUTPUT_VALIDATION if errors else None,
            errors=errors,
        )
        return MemoryExtractionProposal(
            run=run,
            entities=list(entity_by_scope.values()),
            claims=claims,
            actions=actions,
            identity_relations=identity_relations,
        )

    def _surface_for_runtime_observation(self, observation: SourceObservation) -> SurfaceObservation | None:
        candidates = self._observations_by_text.get(text_key(observation.text), [])
        return candidates[0] if candidates else None


def runtime_scope_for_claim(claim: LatentClaim) -> MemoryScope:
    """Translate simulator scope into the runtime's server-owned scope model."""

    return MemoryScope(
        task_id=claim.scope.task_id,
        session_id=claim.scope.session_id,
    )


class RecordingMemoryExtractor:
    """Benchmark wrapper that records validated runtime extraction outcomes."""

    def __init__(self, *, delegate: MemoryExtractor) -> None:
        self._delegate = delegate
        self.recorded_runs: list[RecordedExtractionRun] = []
        self._graph_nodes: dict[str, MemoryGraphNode] = {}
        self._graph_edges: dict[str, MemoryGraphEdge] = {}

    @property
    def provider(self) -> str:
        return self._delegate.provider

    @property
    def model(self) -> str | None:
        return self._delegate.model

    @property
    def prompt_hash(self) -> str | None:
        return self._delegate.prompt_hash

    def extract(self, observations: list[SourceObservation]) -> MemoryExtractionProposal:
        proposal = self._delegate.extract(observations)
        run = proposal.run
        entities = proposal.entities
        claims = proposal.claims
        actions = proposal.actions
        self.recorded_runs.append(
            RecordedExtractionRun(
                input_source_ids=list(run.input_source_ids),
                provider=run.provider,
                model=run.model,
                requested_model=run.requested_model,
                actual_model=run.actual_model,
                prompt_hash=run.prompt_hash,
                extraction_status=run.status,
                provider_attempt_status=run.provider_attempt_status,
                fallback_outcome=run.fallback_outcome,
                final_output_source=run.final_output_source,
                failure_code=run.failure_code,
                primary_failure_code=run.primary_failure_code,
                fallback_provider=run.fallback_provider,
                errors=list(run.errors),
                input_observations=[
                    RuntimeSourceObservationTrace(
                        source_id=observation.source_id,
                        source_type=observation.source_type.value,
                        timestamp=observation.timestamp.isoformat(),
                        modality=observation.modality.value,
                        trigger_mode=observation.trigger_mode.value,
                        language=observation.language,
                        task_id=observation.task_id,
                        session_id=observation.session_id,
                        user_id=observation.user_id,
                    )
                    for observation in observations
                ],
                structured_proposal=(
                    self._delegate.structured_proposal
                    if isinstance(self._delegate, StructuredProposalProvider)
                    else None
                ),
                proposed_entities=list(entities),
                proposed_claims=list(claims),
                proposed_actions=list(actions),
                proposed_identity_relations=list(proposal.identity_relations),
                entity_count=len(entities),
                claim_count=len(claims),
                action_count=len(actions),
                identity_relation_count=len(proposal.identity_relations),
                entity_ids=[entity.entity_id for entity in entities],
                claim_ids=[claim.claim_id for claim in claims],
                action_ids=[action.action_id for action in actions],
                identity_relation_ids=[relation.relation_id for relation in proposal.identity_relations],
                language_capability_ids=list(run.language_capability_ids),
                validation_summary=dict(run.validation_summary),
            )
        )
        return proposal

    def record_evolution_results(
        self,
        results: list[MemoryEvolutionResult],
    ) -> None:
        """Attach deterministic compilation and projection evidence in call order."""

        if not results:
            return
        if len(results) > len(self.recorded_runs):
            raise RuntimeError("evolution results exceed recorded extraction runs")
        target_indexes = range(
            len(self.recorded_runs) - len(results),
            len(self.recorded_runs),
        )
        for index, result in zip(target_indexes, results, strict=True):
            run = self.recorded_runs[index]
            if run.evolution_result_recorded:
                raise RuntimeError("recorded extraction already has an evolution result")
            current_nodes = {node.node_id: node for node in result.graph_nodes}
            current_edges = {edge.edge_id: edge for edge in result.graph_edges}
            graph_delta = RuntimeGraphDelta(
                added_nodes=[node for node_id, node in current_nodes.items() if node_id not in self._graph_nodes],
                updated_nodes=[
                    node
                    for node_id, node in current_nodes.items()
                    if node_id in self._graph_nodes and node != self._graph_nodes[node_id]
                ],
                removed_node_ids=sorted(set(self._graph_nodes) - set(current_nodes)),
                added_edges=[edge for edge_id, edge in current_edges.items() if edge_id not in self._graph_edges],
                updated_edges=[
                    edge
                    for edge_id, edge in current_edges.items()
                    if edge_id in self._graph_edges and edge != self._graph_edges[edge_id]
                ],
                removed_edge_ids=sorted(set(self._graph_edges) - set(current_edges)),
            )
            self.recorded_runs[index] = run.model_copy(
                update={
                    "validation_results": {
                        claim_id: list(values) for claim_id, values in result.validation_results.items()
                    },
                    "entity_identity_decisions": list(result.entity_identity_decisions),
                    "evolution_result_recorded": True,
                    "compiled_claims": list(result.claims),
                    "compiled_actions": list(result.actions),
                    "compiled_identity_relations": list(result.identity_relations),
                    "lifecycle_transitions": list(result.transitions),
                    "graph_nodes": list(result.graph_nodes),
                    "graph_edges": list(result.graph_edges),
                    "graph_validation_errors": list(result.graph_validation_errors),
                    "graph_delta": graph_delta,
                }
            )
            self._graph_nodes = current_nodes
            self._graph_edges = current_edges

    def record_operation_outcomes(
        self,
        outcomes: list[ProviderEvolutionOutcome],
    ) -> None:
        """Attach synchronous durable outcomes to their just-recorded extractions."""

        if not outcomes:
            return
        if len(outcomes) > len(self.recorded_runs):
            raise RuntimeError("operation outcomes exceed recorded extraction runs")
        target_indexes = range(
            len(self.recorded_runs) - len(outcomes),
            len(self.recorded_runs),
        )
        for index, outcome in zip(target_indexes, outcomes, strict=True):
            run = self.recorded_runs[index]
            if run.operation_status is not None:
                raise RuntimeError("recorded extraction already has an operation outcome")
            self.recorded_runs[index] = run.model_copy(
                update={
                    "operation_id": outcome.operation_id,
                    "operation_status": EvolutionOperationStatus(outcome.status),
                    "operation_failure_code": (
                        EvolutionFailureCategory(outcome.failure_code) if outcome.failure_code is not None else None
                    ),
                    "operation_retryable": outcome.retryable,
                }
            )


def build_runtime_extractor(
    *,
    scenario: LatentGraphScenario,
    effective_mode: str,
    dry_run: bool,
    runtime_config: LLMRuntimeConfig,
    prompt_root: Path,
    live_client_factory: Callable[[LLMRuntimeConfig], LLMStructuredClient] = LLMClientFactory.from_config,
) -> RecordingMemoryExtractor:
    if effective_mode == "rule":
        delegate: MemoryExtractor = EnglishRuleMemoryExtractor()
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
            raise ValueError(f"Unsupported runtime extractor mode: {effective_mode}")
    return RecordingMemoryExtractor(delegate=delegate)


def recorded_extraction_runs(extractor: RecordingMemoryExtractor) -> list[RecordedExtractionRun]:
    return list(extractor.recorded_runs)


def extractor_fallback_count(extractor: RecordingMemoryExtractor) -> int:
    return sum(run.fallback_outcome != FallbackOutcome.NOT_USED for run in extractor.recorded_runs)
