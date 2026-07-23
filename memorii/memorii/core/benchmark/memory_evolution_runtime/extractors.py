"""Runtime extractor construction and benchmark telemetry."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.benchmark.calibration.alignment import normalize_alignment_value
from memorii.core.benchmark.memory_evolution_runtime.graph_items import (
    claim_quote,
    entity_quote,
    runtime_entity_type,
    runtime_span_for_item,
)
from memorii.core.benchmark.memory_evolution_runtime.utils import (
    claim_by_id,
    entity_by_id,
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
    EntityMention,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionRun,
    HybridMemoryExtractor,
    LLMMemoryExtractor,
    MemoryExtractor,
    SourceObservation,
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


class RecordedExtractionRun(BaseModel):
    """Validated telemetry for one runtime extraction call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_source_ids: list[str]
    provider: str
    model: str | None
    prompt_hash: str | None
    extraction_status: ExtractionRunStatus
    provider_attempt_status: ProviderAttemptStatus
    fallback_outcome: FallbackOutcome
    final_output_source: FinalExtractionSource
    failure_code: ExtractionFailureCode | None
    primary_failure_code: ExtractionFailureCode | None
    fallback_provider: str | None
    errors: list[str]
    entity_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    action_count: int = Field(ge=0)
    entity_ids: list[str]
    claim_ids: list[str]
    action_ids: list[str]
    validation_summary: dict[str, int]


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

    def extract(
        self, observations: list[SourceObservation]
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        self.calls += 1
        run_id = stable_id("runtime-fake-extraction", "|".join(obs.source_id for obs in observations))
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
                    mention_text=entity.canonical_name,
                    normalized_name=normalize_alignment_value(entity.canonical_name),
                    aliases=[alias.alias_text for alias in entity.aliases],
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
                claim_scope = runtime_scope_for_claim(claim)
                for entity_id in (claim.subject.entity_id, claim.object.entity_id):
                    entity = entity_by_id(self._scenario, entity_id) if entity_id else None
                    if entity is None or entity.observability == ObservabilityLabel.HIDDEN:
                        continue
                    entity_by_scope.setdefault(
                        (entity.entity_id, claim_scope.scope_key),
                        EntityMention(
                            entity_id=entity.entity_id,
                            mention_text=entity.canonical_name,
                            normalized_name=normalize_alignment_value(entity.canonical_name),
                            aliases=[alias.alias_text for alias in entity.aliases],
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
            status=ExtractionRunStatus.PARTIAL if errors else ExtractionRunStatus.SUCCEEDED,
            failure_code=ExtractionFailureCode.OUTPUT_VALIDATION if errors else None,
            errors=errors,
        )
        return run, list(entity_by_scope.values()), claims, actions

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

    @property
    def provider(self) -> str:
        return self._delegate.provider

    @property
    def model(self) -> str | None:
        return self._delegate.model

    @property
    def prompt_hash(self) -> str | None:
        return self._delegate.prompt_hash

    def extract(
        self, observations: list[SourceObservation]
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        run, entities, claims, actions = self._delegate.extract(observations)
        self.recorded_runs.append(
            RecordedExtractionRun(
                input_source_ids=list(run.input_source_ids),
                provider=run.provider,
                model=run.model,
                prompt_hash=run.prompt_hash,
                extraction_status=run.status,
                provider_attempt_status=run.provider_attempt_status,
                fallback_outcome=run.fallback_outcome,
                final_output_source=run.final_output_source,
                failure_code=run.failure_code,
                primary_failure_code=run.primary_failure_code,
                fallback_provider=run.fallback_provider,
                errors=list(run.errors),
                entity_count=len(entities),
                claim_count=len(claims),
                action_count=len(actions),
                entity_ids=[entity.entity_id for entity in entities],
                claim_ids=[claim.claim_id for claim in claims],
                action_ids=[action.action_id for action in actions],
                validation_summary=dict(run.validation_summary),
            )
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
