"""Recoverable provider ingestion composed with default-on memory evolution."""

from __future__ import annotations

from memorii.core.memory_evolution.models import ExtractionRunStatus, MemoryEvolutionResult
from memorii.core.memory_evolution.operation_models import EvolutionOperation
from memorii.core.memory_evolution.operations import EvolutionCoordinator
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.models import ProviderEvent, ProviderEvolutionOutcome, ProviderSyncResult


class ProviderIngestionCoordinator:
    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        evolution_coordinator: EvolutionCoordinator,
    ) -> None:
        self._memory_plane = memory_plane
        self._evolution_coordinator = evolution_coordinator

    def ingest(
        self,
        event: ProviderEvent,
        *,
        defer_assertions: bool = False,
    ) -> tuple[ProviderSyncResult, EvolutionOperation | None, MemoryEvolutionResult | None]:
        result, source_records = self._memory_plane.prepare_provider_event(event)
        if not result.transcript_ids:
            if source_records:
                self._memory_plane.write_records(source_records)
            return result, None, None
        operation = self._evolution_coordinator.begin(
            operation_id=event.event_id,
            source_record_ids=result.transcript_ids,
            source_records=source_records,
            defer_assertions=defer_assertions,
        )
        operation, evolution_result = self._evolution_coordinator.execute(operation)
        return (
            result.model_copy(update={"evolution_outcomes": [_provider_outcome(operation)]}),
            operation,
            evolution_result,
        )

    def reconcile(self) -> list[ProviderEvolutionOutcome]:
        return [_provider_outcome(operation) for operation in self._evolution_coordinator.reconcile()]


def _provider_outcome(operation: EvolutionOperation) -> ProviderEvolutionOutcome:
    live_success = (
        operation.status.value == "evolution_committed" and operation.extraction_status == ExtractionRunStatus.SUCCEEDED
    )
    fallback_used = operation.extraction_status == ExtractionRunStatus.FALLBACK_SUCCEEDED
    return ProviderEvolutionOutcome(
        operation_id=operation.operation_id,
        status=operation.status.value,
        attempt_count=operation.attempt_count,
        failure_code=operation.failure.category.value if operation.failure is not None else None,
        retryable=operation.failure.retryable if operation.failure is not None else False,
        extraction_status=(operation.extraction_status.value if operation.extraction_status is not None else None),
        live_success=live_success,
        fallback_used=fallback_used,
        fallback_provider=operation.fallback_provider,
    )
