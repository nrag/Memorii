"""Runtime ingestion helpers for benchmark surface observations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from memorii.core.benchmark.memory_evolution_sim import LatentGraphScenario, SurfaceObservation
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService


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


def ingest_scenario_surface_observations(
    *,
    provider: ProviderMemoryService,
    memory_plane: MemoryPlaneService,
    scenario: LatentGraphScenario,
    context: IngestionContext | None = None,
) -> dict[str, str]:
    before_ids: set[str] = set()
    source_id_to_event_id: dict[str, str] = {}
    context = context or IngestionContext()
    for observation in sorted(scenario.observations, key=lambda item: (item.timestamp, item.event_id)):
        source_id_to_event_id.update(
            ingest_surface_observation(
                provider=provider,
                memory_plane=memory_plane,
                observation=observation,
                context=context,
                before_ids=before_ids,
            )
        )
        before_ids = {record.memory_id for record in memory_plane.list_records()}
    return source_id_to_event_id


def ingest_surface_observation(
    *,
    provider: ProviderMemoryService,
    memory_plane: MemoryPlaneService,
    observation: SurfaceObservation,
    context: IngestionContext | None = None,
    before_ids: set[str] | None = None,
) -> dict[str, str]:
    """Ingest exactly one surface observation and return new evidence links."""
    before = set(before_ids or {record.memory_id for record in memory_plane.list_records()})
    context = _context_for_observation(observation, fallback=context or IngestionContext())
    operation = _provider_operation_for_surface(observation)
    if operation in {ProviderOperation.MEMORY_WRITE_LONGTERM, ProviderOperation.MEMORY_WRITE_USER}:
        provider.apply_memory_write(
            operation=operation,
            content=observation.text,
            session_id=context.session_id,
            task_id=context.task_id,
            user_id=context.user_id,
            action="write",
            target="memory",
            operation_id=f"benchmark:runtime:{observation.event_id}",
        )
    else:
        provider.sync_event(
            operation=operation,
            content=observation.text,
            role="user" if observation.source_type in {"user", "transcript"} else observation.source_type,
            session_id=context.session_id,
            task_id=context.task_id,
            user_id=context.user_id,
            operation_id=f"benchmark:runtime:{observation.event_id}",
        )
    return {
        record.memory_id: observation.event_id
        for record in memory_plane.list_records()
        if record.memory_id not in before and record.is_raw_event and record.text == observation.text
    }


def _context_for_observation(
    observation: SurfaceObservation,
    *,
    fallback: IngestionContext,
) -> IngestionContext:
    return IngestionContext(
        task_id=observation.task_id if observation.task_id is not None else fallback.task_id,
        session_id=(
            observation.session_id
            if observation.session_id is not None
            else fallback.session_id
        ),
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
