"""Runtime ingestion helpers for benchmark surface observations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from memorii.core.benchmark.memory_evolution_sim import LatentGraphScenario, SurfaceObservation
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderEvolutionOutcome, ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import SourceModality


class IngestionContext(BaseModel):
    """Caller-owned context transported alongside benchmark observations.

    This deliberately contains no latent graph IDs or expected outputs.  The
    runtime must receive scope from the caller, never infer it from oracle
    labels embedded in a simulator object.
    """

    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class SurfaceIngestionResult(BaseModel):
    """Observable evidence and durable evolution outcome for ingested surfaces."""

    source_id_to_event_id: dict[str, str]
    evolution_outcomes: list[ProviderEvolutionOutcome]

    model_config = ConfigDict(extra="forbid")


def ingest_scenario_surface_observations(
    *,
    provider: ProviderMemoryService,
    memory_plane: MemoryPlaneService,
    scenario: LatentGraphScenario,
    context: IngestionContext | None = None,
) -> SurfaceIngestionResult:
    before_ids: set[str] = set()
    source_id_to_event_id: dict[str, str] = {}
    evolution_outcomes: list[ProviderEvolutionOutcome] = []
    context = context or IngestionContext()
    for observation in sorted(scenario.observations, key=lambda item: (item.timestamp, item.event_id)):
        result = ingest_surface_observation(
            provider=provider,
            memory_plane=memory_plane,
            observation=observation,
            context=context,
            before_ids=before_ids,
        )
        source_id_to_event_id.update(result.source_id_to_event_id)
        evolution_outcomes.extend(result.evolution_outcomes)
        before_ids = {record.memory_id for record in memory_plane.list_records()}
    return SurfaceIngestionResult(
        source_id_to_event_id=source_id_to_event_id,
        evolution_outcomes=evolution_outcomes,
    )


def ingest_surface_observation(
    *,
    provider: ProviderMemoryService,
    memory_plane: MemoryPlaneService,
    observation: SurfaceObservation,
    context: IngestionContext | None = None,
    before_ids: set[str] | None = None,
) -> SurfaceIngestionResult:
    """Ingest exactly one surface observation and return new evidence links."""
    before = set(before_ids or {record.memory_id for record in memory_plane.list_records()})
    context = _context_for_observation(observation, fallback=context or IngestionContext())
    operation = _provider_operation_for_surface(observation)
    if operation in {ProviderOperation.MEMORY_WRITE_LONGTERM, ProviderOperation.MEMORY_WRITE_USER}:
        provider_result = provider.apply_memory_write(
            operation=operation,
            content=observation.text,
            session_id=context.session_id,
            task_id=context.task_id,
            user_id=context.user_id,
            action="write",
            target="memory",
            operation_id=f"benchmark:runtime:{observation.event_id}",
            timestamp=observation.timestamp,
            source_modality=SourceModality(observation.modality),
        )
    else:
        provider_result = provider.sync_event(
            operation=operation,
            content=observation.text,
            role="user" if observation.source_type in {"user", "transcript"} else observation.source_type,
            session_id=context.session_id,
            task_id=context.task_id,
            user_id=context.user_id,
            operation_id=f"benchmark:runtime:{observation.event_id}",
            timestamp=observation.timestamp,
            source_modality=SourceModality(observation.modality),
        )
    return SurfaceIngestionResult(
        source_id_to_event_id={
            record.memory_id: observation.event_id
            for record in memory_plane.list_records()
            if record.memory_id not in before and record.is_raw_event and record.text == observation.text
        },
        evolution_outcomes=list(provider_result.evolution_outcomes),
    )


def _context_for_observation(
    observation: SurfaceObservation,
    *,
    fallback: IngestionContext,
) -> IngestionContext:
    return IngestionContext(
        task_id=observation.task_id if observation.task_id is not None else fallback.task_id,
        session_id=(observation.session_id if observation.session_id is not None else fallback.session_id),
        user_id=observation.user_id if observation.user_id is not None else fallback.user_id,
    )


def _provider_operation_for_surface(observation: SurfaceObservation) -> ProviderOperation:
    if observation.source_type == "tool" or observation.modality == "tool_result":
        return ProviderOperation.DELEGATION_RESULT
    if observation.modality in {"assertion", "correction"} and observation.trust_level >= 3:
        return ProviderOperation.MEMORY_WRITE_LONGTERM
    if observation.modality == "instruction":
        return ProviderOperation.CHAT_USER_TURN
    return ProviderOperation.CHAT_USER_TURN
