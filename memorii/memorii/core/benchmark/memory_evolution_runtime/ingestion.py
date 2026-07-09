"""Runtime ingestion helpers for benchmark surface observations."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import LatentGraphScenario, SurfaceObservation
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService


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
