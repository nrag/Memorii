"""Test-only provider harness for memory-evolution verification."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from _pytest.monkeypatch import MonkeyPatch
from memorii.core.memory_evolution.extraction_contracts import MemoryExtractor
from memorii.core.memory_evolution.models import MemoryEvolutionResult
from memorii.core.memory_evolution.operation_models import EvolutionOperation
from memorii.core.memory_evolution.operation_store import (
    EvolutionOperationRepository,
    MemoryPlaneEvolutionOperationRepository,
)
from memorii.core.memory_evolution.operations import EvolutionCoordinator
from memorii.core.memory_evolution.query_analysis import QueryAnalyzer
from memorii.core.memory_evolution.service import MemoryEvolutionService
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.models import ProviderEvent, ProviderEvolutionOutcome, ProviderSyncResult
from memorii.core.provider.service import ProviderMemoryService


class _EvolutionIngestionHarness:
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
        authenticated_ingress: object | None = None,
    ) -> tuple[ProviderSyncResult, EvolutionOperation | None, MemoryEvolutionResult | None]:
        del authenticated_ingress
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


class MemoryEvolutionProviderHarness(ProviderMemoryService):
    """Retain M2 verification without making it a production composition option."""

    def __init__(
        self,
        *args: object,
        memory_plane: MemoryPlaneService | None = None,
        memory_evolution_extractor: MemoryExtractor | None = None,
        memory_evolution_query_analyzer: QueryAnalyzer | None = None,
        memory_evolution_operation_repository: EvolutionOperationRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
        **kwargs: object,
    ) -> None:
        resolved_plane = memory_plane or MemoryPlaneService()
        super().__init__(
            *args,
            memory_plane=resolved_plane,
            now_provider=now_provider,
            **kwargs,
        )
        resolved_now = now_provider or (lambda: datetime.now(UTC))
        self._memory_evolution_service = MemoryEvolutionService(
            memory_plane=resolved_plane,
            extractor=memory_evolution_extractor,
            query_analyzer=memory_evolution_query_analyzer,
            now_provider=resolved_now,
        )
        repository = memory_evolution_operation_repository or MemoryPlaneEvolutionOperationRepository(
            resolved_plane
        )
        self._evolution_coordinator = EvolutionCoordinator(
            memory_plane=resolved_plane,
            evolution_service=self._memory_evolution_service,
            now_provider=resolved_now,
            operation_repository=repository,
        )
        self._provider_ingestion = _EvolutionIngestionHarness(
            memory_plane=resolved_plane,
            evolution_coordinator=self._evolution_coordinator,
        )

    def _ingest_event(
        self,
        event: ProviderEvent,
        *,
        authenticated_host_ingress: object | None,
    ) -> ProviderSyncResult:
        del authenticated_host_ingress
        result, _, evolution_result = self._provider_ingestion.ingest(
            event,
            defer_assertions=event.operation.value in {"chat_user_turn", "chat_assistant_turn"},
        )
        self._last_memory_evolution_result = evolution_result
        self._work_state_memory_projector.ingest_provider_event(event)
        return result

    def reconcile_memory_evolution(self) -> list[ProviderEvolutionOutcome]:
        return self._provider_ingestion.reconcile()


def enable_test_runtime_benchmark_harness(monkeypatch: MonkeyPatch) -> None:
    """Explicitly compose the M2 benchmark for a test that exercises its CLI."""
    from memorii.core.benchmark.memory_evolution_runtime.runner import run_runtime_scenarios
    from memorii.tools.benchmark_suites import memory_evolution_runtime as runtime_suite

    def run_with_test_composition(**kwargs: Any):
        kwargs["provider_factory"] = MemoryEvolutionProviderHarness
        return run_runtime_scenarios(**kwargs)

    monkeypatch.setattr(runtime_suite, "run_runtime_scenarios", run_with_test_composition)


def _provider_outcome(operation: EvolutionOperation) -> ProviderEvolutionOutcome:
    return ProviderEvolutionOutcome(
        operation_id=operation.operation_id,
        status=operation.status.value,
        attempt_count=operation.attempt_count,
        failure_code=operation.failure.category.value if operation.failure is not None else None,
        retryable=operation.failure.retryable if operation.failure is not None else False,
        extraction_status=operation.extraction_status,
        provider_attempt_status=operation.provider_attempt_status,
        fallback_outcome=operation.fallback_outcome,
        final_extraction_source=operation.final_extraction_source,
        extraction_failure_code=operation.extraction_failure_code,
        primary_failure_code=operation.primary_failure_code,
        fallback_provider=operation.fallback_provider,
    )
