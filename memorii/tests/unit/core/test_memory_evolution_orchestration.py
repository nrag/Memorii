from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock
from time import sleep

from memorii.core.memory_evolution import (
    EnglishRuleMemoryExtractor,
    ExtractionFailureCode,
    ExtractionRun,
    ExtractionRunStatus,
    HybridMemoryExtractor,
    MemoryEvolutionResult,
    MemoryEvolutionService,
    MemoryGraphProjector,
    MemoryGraphSnapshot,
    RetrievalView,
)
from memorii.core.memory_evolution.models import SourceObservation
from memorii.core.memory_evolution.operation_models import EvolutionOperationStatus
from memorii.core.memory_evolution.operation_store import (
    MemoryPlaneEvolutionOperationRepository,
)
from memorii.core.memory_evolution.operations import EvolutionCoordinator
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    MemoryPlanePrecondition,
    MemoryPlaneRevisionConflictError,
)
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import CommitStatus, MemoryDomain


class _CountingExtractor(EnglishRuleMemoryExtractor):
    def __init__(self, *, failures: int = 0) -> None:
        self.calls = 0
        self._failures = failures

    def extract(self, observations: list[SourceObservation]):
        self.calls += 1
        if self.calls <= self._failures:
            raise OSError("injected retryable extraction failure")
        return super().extract(observations)


class _BlockingCountingExtractor(EnglishRuleMemoryExtractor):
    def __init__(self) -> None:
        self.calls = 0
        self.entered = Barrier(2)
        self.release = Barrier(2)
        self.lock = Lock()

    def extract(self, observations: list[SourceObservation]):
        with self.lock:
            self.calls += 1
        self.entered.wait(timeout=5)
        self.release.wait(timeout=5)
        return super().extract(observations)


class _FailedExtractionProvider:
    provider = "test_llm"
    model = "test-model"
    prompt_hash = "test-prompt"

    def extract(self, observations: list[SourceObservation]):
        return (
            ExtractionRun(
                extraction_run_id="extraction:failed",
                provider=self.provider,
                model=self.model,
                prompt_hash=self.prompt_hash,
                input_source_ids=[observation.source_id for observation in observations],
                status=ExtractionRunStatus.FAILED,
                failure_code=ExtractionFailureCode.PROVIDER_ERROR,
                errors=["provider_error"],
            ),
            [],
            [],
            [],
        )


class _OneConflictStore(InMemoryMemoryPlaneStore):
    def __init__(self) -> None:
        super().__init__()
        self.conflict_next_batch = False

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
    ) -> int:
        if self.conflict_next_batch:
            self.conflict_next_batch = False
            raise MemoryPlaneRevisionConflictError("injected conflict")
        return super().apply_batch(
            records,
            expected_revision=expected_revision,
            preconditions=preconditions,
        )


class _LostAcknowledgementStore(InMemoryMemoryPlaneStore):
    def __init__(self) -> None:
        super().__init__()
        self.lose_completion_acknowledgement = False

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
    ) -> int:
        revision = super().apply_batch(
            records,
            expected_revision=expected_revision,
            preconditions=preconditions,
        )
        if self.lose_completion_acknowledgement and any(_is_committed_operation(record) for record in records):
            self.lose_completion_acknowledgement = False
            raise OSError("injected lost commit acknowledgement")
        return revision


class _BlockingCompletionStore(InMemoryMemoryPlaneStore):
    def __init__(self) -> None:
        super().__init__()
        self.completion_started = Barrier(2)
        self.completion_release = Barrier(2)

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
    ) -> int:
        if any(_is_committed_operation(record) for record in records):
            self.completion_started.wait(timeout=5)
            self.completion_release.wait(timeout=5)
        return super().apply_batch(
            records,
            expected_revision=expected_revision,
            preconditions=preconditions,
        )


class _OwnershipTransferStore(InMemoryMemoryPlaneStore):
    def __init__(self) -> None:
        super().__init__()
        self.stale_commit_started = Barrier(2)
        self.stale_commit_release = Barrier(2)
        self._blocked_once = False

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
    ) -> int:
        if not self._blocked_once and any(_is_committed_operation(record) for record in records):
            self._blocked_once = True
            self.stale_commit_started.wait(timeout=5)
            self.stale_commit_release.wait(timeout=5)
        return super().apply_batch(
            records,
            expected_revision=expected_revision,
            preconditions=preconditions,
        )


class _BlockingGraphProjector(MemoryGraphProjector):
    def __init__(self) -> None:
        self.entered = Barrier(2)
        self.release = Barrier(2)

    def project_evolution_result(
        self,
        *,
        result: MemoryEvolutionResult,
        existing_snapshot: MemoryGraphSnapshot | None = None,
    ) -> MemoryGraphSnapshot:
        self.entered.wait(timeout=5)
        self.release.wait(timeout=5)
        return super().project_evolution_result(result=result, existing_snapshot=existing_snapshot)


def _is_committed_operation(record: CanonicalMemoryRecord) -> bool:
    operation = record.content.get("operation")
    return isinstance(operation, dict) and operation.get("status") == "evolution_committed"


def _source(memory_id: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text="Atlas migration owner is Alice.",
        content={"text": "Atlas migration owner is Alice."},
        status=CommitStatus.COMMITTED,
        source_kind="user",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        task_id="task:atlas",
        user_id="user:alice",
        is_raw_event=True,
    )


def test_revision_retry_does_not_repeat_extraction() -> None:
    store = _OneConflictStore()
    plane = MemoryPlaneService(record_store=store)
    source = _source("tx:one")
    plane.stage_record(source)
    extractor = _CountingExtractor()
    store.conflict_next_batch = True

    result = MemoryEvolutionService(memory_plane=plane, extractor=extractor).evolve_records([source])

    assert result.claim_states
    assert extractor.calls == 1


def test_provider_failure_is_durable_truthful_and_reconcilable() -> None:
    plane = MemoryPlaneService()
    failing_extractor = _CountingExtractor(failures=1)
    first = ProviderMemoryService(
        memory_plane=plane,
        memory_evolution_extractor=failing_extractor,
    )

    result = first.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        task_id="task:atlas",
        user_id="user:alice",
        operation_id="operation:atlas-owner",
    )

    assert len(result.evolution_outcomes) == 1
    outcome = result.evolution_outcomes[0]
    assert outcome.status == "evolution_failed"
    assert outcome.failure_code == "store_error"
    assert outcome.retryable is True
    assert plane.get_record("tx:operation:atlas-owner") is not None

    restarted = ProviderMemoryService(
        memory_plane=plane,
        memory_evolution_extractor=failing_extractor,
    )
    reconciled = restarted.reconcile_memory_evolution()

    assert [outcome.status for outcome in reconciled] == ["evolution_committed"]
    states = restarted.memory_evolution_service.retrieve_claim_states(view=RetrievalView.CURRENT)
    assert [state.object_value for state in states] == ["Alice"]
    assert failing_extractor.calls == 2


def test_failed_extraction_is_not_reported_as_live_success() -> None:
    provider = ProviderMemoryService(memory_evolution_extractor=_FailedExtractionProvider())

    result = provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        operation_id="operation:provider-failure",
    )

    assert len(result.evolution_outcomes) == 1
    outcome = result.evolution_outcomes[0]
    assert outcome.status == "evolution_failed"
    assert outcome.failure_code == "provider_error"
    assert outcome.retryable is True
    assert outcome.extraction_status == ExtractionRunStatus.FAILED
    assert outcome.live_success is False
    assert outcome.fallback_used is False
    assert provider.memory_evolution_service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS) == []


def test_hybrid_fallback_is_committed_but_not_reported_as_live_success() -> None:
    provider = ProviderMemoryService(
        memory_evolution_extractor=HybridMemoryExtractor(
            llm_extractor=_FailedExtractionProvider(),
        )
    )

    result = provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        operation_id="operation:fallback",
    )

    outcome = result.evolution_outcomes[0]
    assert outcome.status == "evolution_committed"
    assert outcome.failure_code is None
    assert outcome.extraction_status == ExtractionRunStatus.FALLBACK_SUCCEEDED
    assert outcome.live_success is False
    assert outcome.fallback_used is True
    assert outcome.fallback_provider == "english_rule"


def test_hybrid_does_not_report_an_abstaining_fallback_as_success() -> None:
    provider = ProviderMemoryService(
        memory_evolution_extractor=HybridMemoryExtractor(
            llm_extractor=_FailedExtractionProvider(),
        )
    )

    result = provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="La propietaria de Atlas es Alice.",
        language="es",
        operation_id="operation:unsupported-fallback",
    )

    outcome = result.evolution_outcomes[0]
    assert outcome.status == "evolution_failed"
    assert outcome.failure_code == "provider_error"
    assert outcome.live_success is False
    assert outcome.fallback_used is False


def test_failed_evolution_reconciles_after_persistent_store_reopen(tmp_path: Path) -> None:
    store_path = tmp_path / "memory-plane"
    first_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    first_provider = ProviderMemoryService(
        memory_plane=first_plane,
        memory_evolution_extractor=_CountingExtractor(failures=1),
    )

    initial = first_provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        task_id="task:atlas",
        user_id="user:alice",
        operation_id="operation:persistent-recovery",
    )

    assert [outcome.status for outcome in initial.evolution_outcomes] == ["evolution_failed"]

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    restarted_provider = ProviderMemoryService(
        memory_plane=reopened_plane,
        memory_evolution_extractor=_CountingExtractor(),
    )
    reconciled = restarted_provider.reconcile_memory_evolution()

    assert [outcome.status for outcome in reconciled] == ["evolution_committed"]
    assert [
        state.object_value
        for state in restarted_provider.memory_evolution_service.retrieve_claim_states(view=RetrievalView.CURRENT)
    ] == ["Alice"]

    verified_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    operation_record = verified_plane.get_record("mem:evolution:operation:operation:persistent-recovery")
    assert operation_record is not None
    assert operation_record.content["operation"]["status"] == "evolution_committed"


def test_production_composition_recovers_retryable_operation_on_startup(tmp_path: Path) -> None:
    store_path = tmp_path / "memory-plane"
    first_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    first_provider = ProviderMemoryService(
        memory_plane=first_plane,
        memory_evolution_extractor=_CountingExtractor(failures=1),
    )
    first_provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        task_id="task:atlas",
        operation_id="operation:startup-recovery",
    )

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    restarted = build_provider_memory_service_from_env(
        memory_plane=reopened_plane,
        env={"MEMORII_SECRET_SOURCE": "process", "MEMORII_LLM_PROVIDER": "none"},
    )

    states = restarted.memory_evolution_service.retrieve_claim_states(view=RetrievalView.CURRENT)
    assert [state.object_value for state in states] == ["Alice"]
    operation = reopened_plane.get_record("mem:evolution:operation:operation:startup-recovery")
    assert operation is not None
    assert operation.content["operation"]["status"] == "evolution_committed"


def test_durable_failure_message_does_not_persist_exception_text() -> None:
    plane = MemoryPlaneService()
    secret = "customer-secret-that-must-not-be-persisted"

    class _SensitiveFailureExtractor(EnglishRuleMemoryExtractor):
        def extract(self, observations: list[SourceObservation]):
            raise OSError(secret)

    provider = ProviderMemoryService(
        memory_plane=plane,
        memory_evolution_extractor=_SensitiveFailureExtractor(),
    )
    provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        operation_id="operation:sanitized-failure",
    )

    operation = plane.get_record("mem:evolution:operation:operation:sanitized-failure")
    assert operation is not None
    serialized = operation.model_dump_json()
    assert secret not in serialized
    assert operation.content["operation"]["failure"]["message"] == (
        "memory evolution encountered an operational storage or provider failure"
    )


def test_reconciliation_preserves_deferred_assertion_policy() -> None:
    plane = MemoryPlaneService()
    extractor = _CountingExtractor(failures=1)
    provider = ProviderMemoryService(memory_plane=plane, memory_evolution_extractor=extractor)

    result = provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas migration owner is Alice.",
        operation_id="operation:deferred-owner",
    )
    reconciled = provider.reconcile_memory_evolution()

    assert len(result.evolution_outcomes) == 1
    assert result.evolution_outcomes[0].status == "evolution_failed"
    assert [outcome.status for outcome in reconciled] == ["evolution_committed"]
    assert provider.memory_evolution_service.retrieve_claim_states(view=RetrievalView.CURRENT) == []
    all_states = provider.memory_evolution_service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    assert len(all_states) == 1
    assert all_states[0].lifecycle_state.value == "invalidated"


def test_retry_exhaustion_becomes_terminal() -> None:
    plane = MemoryPlaneService()
    extractor = _CountingExtractor(failures=10)
    provider = ProviderMemoryService(memory_plane=plane, memory_evolution_extractor=extractor)

    provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        operation_id="operation:exhaustion",
    )
    provider.reconcile_memory_evolution()
    provider.reconcile_memory_evolution()
    exhausted = provider.reconcile_memory_evolution()

    assert len(exhausted) == 1
    assert exhausted[0].failure_code == "retry_exhausted"
    assert exhausted[0].retryable is False
    assert provider.reconcile_memory_evolution() == []


def test_stable_operation_id_is_idempotent() -> None:
    plane = MemoryPlaneService()
    extractor = _CountingExtractor()
    provider = ProviderMemoryService(memory_plane=plane, memory_evolution_extractor=extractor)
    arguments = {
        "operation": ProviderOperation.MEMORY_WRITE_LONGTERM,
        "content": "Atlas migration owner is Alice.",
        "task_id": "task:atlas",
        "user_id": "user:alice",
        "operation_id": "operation:idempotent",
    }

    first = provider.sync_event(**arguments)
    second = provider.sync_event(**arguments)

    assert first.evolution_outcomes == second.evolution_outcomes
    assert extractor.calls == 1
    assert [record.memory_id for record in plane.provider_transcript_records()] == ["tx:operation:idempotent"]
    assert len(provider.memory_evolution_service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)) == 1


def test_distinct_delivery_ids_remain_distinct_after_provider_restart() -> None:
    plane = MemoryPlaneService()
    first = ProviderMemoryService(memory_plane=plane)
    first_result = first.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        operation_id="operation:restart:alice",
        task_id="task:atlas",
    )

    restarted = ProviderMemoryService(memory_plane=plane)
    second_result = restarted.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Bob.",
        operation_id="operation:restart:bob",
        task_id="task:atlas",
    )

    assert first_result.evolution_outcomes[0].operation_id != second_result.evolution_outcomes[0].operation_id
    assert second_result.evolution_outcomes[0].status == "evolution_committed"
    assert len(plane.provider_transcript_records()) == 2


def test_concurrent_delivery_claims_one_evolution_execution() -> None:
    plane = MemoryPlaneService()
    extractor = _BlockingCountingExtractor()
    operations = MemoryPlaneEvolutionOperationRepository(plane)
    providers = [
        ProviderMemoryService(
            memory_plane=plane,
            memory_evolution_extractor=extractor,
            memory_evolution_operation_repository=operations,
        )
        for _ in range(2)
    ]

    def ingest(provider: ProviderMemoryService):
        return provider.sync_event(
            operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
            content="Atlas migration owner is Alice.",
            task_id="task:atlas",
            operation_id="operation:concurrent-delivery",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(ingest, providers[0])
        extractor.entered.wait(timeout=5)
        second_result = pool.submit(ingest, providers[1]).result(timeout=5)
        extractor.release.wait(timeout=5)
        first_result = first_future.result(timeout=5)

    assert extractor.calls == 1
    assert {first_result.evolution_outcomes[0].status, second_result.evolution_outcomes[0].status} == {
        "evolution_committed",
        "evolution_running",
    }
    states = providers[0].memory_evolution_service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    assert len(states) == 1
    assert len(states[0].evidence_spans) == 1
    assert states[0].confidence_history == []


def test_active_lease_is_renewed_during_slow_extraction() -> None:
    plane = MemoryPlaneService()
    extractor = _BlockingCountingExtractor()
    evolution_service = MemoryEvolutionService(memory_plane=plane, extractor=extractor)
    operations = MemoryPlaneEvolutionOperationRepository(plane)
    coordinator = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=evolution_service,
        lease_duration=timedelta(milliseconds=120),
        heartbeat_interval=timedelta(milliseconds=20),
        operation_repository=operations,
    )
    contender = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=evolution_service,
        lease_duration=timedelta(milliseconds=120),
        heartbeat_interval=timedelta(milliseconds=20),
        operation_repository=operations,
    )
    source = _source("tx:renewed-lease")
    operation = coordinator.begin(
        operation_id="operation:renewed-lease",
        source_record_ids=[source.memory_id],
        source_records=(source,),
        defer_assertions=False,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(coordinator.execute, operation)
        extractor.entered.wait(timeout=5)
        sleep(0.25)
        observed, result = contender.execute(operation)
        extractor.release.wait(timeout=5)
        committed, _ = future.result(timeout=5)

    assert observed.status.value == "evolution_running"
    assert result is None
    assert committed.status.value == "evolution_committed"
    assert committed.lease_recovery_count == 0
    assert extractor.calls == 1


def test_active_lease_is_renewed_during_slow_projection() -> None:
    plane = MemoryPlaneService()
    projector = _BlockingGraphProjector()
    evolution_service = MemoryEvolutionService(memory_plane=plane, graph_projector=projector)
    operations = MemoryPlaneEvolutionOperationRepository(plane)
    coordinator = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=evolution_service,
        lease_duration=timedelta(milliseconds=120),
        heartbeat_interval=timedelta(milliseconds=20),
        operation_repository=operations,
    )
    contender = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=evolution_service,
        lease_duration=timedelta(milliseconds=120),
        heartbeat_interval=timedelta(milliseconds=20),
        operation_repository=operations,
    )
    source = _source("tx:slow-projection")
    operation = coordinator.begin(
        operation_id="operation:slow-projection",
        source_record_ids=[source.memory_id],
        source_records=(source,),
        defer_assertions=False,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(coordinator.execute, operation)
        projector.entered.wait(timeout=5)
        sleep(0.25)
        observed, result = contender.execute(operation)
        projector.release.wait(timeout=5)
        committed, _ = future.result(timeout=5)

    assert observed.status.value == "evolution_running"
    assert result is None
    assert committed.status.value == "evolution_committed"
    assert committed.lease_recovery_count == 0


def test_active_lease_is_renewed_during_slow_commit() -> None:
    store = _BlockingCompletionStore()
    plane = MemoryPlaneService(record_store=store)
    evolution_service = MemoryEvolutionService(memory_plane=plane)
    operations = MemoryPlaneEvolutionOperationRepository(plane)
    coordinator = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=evolution_service,
        lease_duration=timedelta(milliseconds=120),
        heartbeat_interval=timedelta(milliseconds=20),
        operation_repository=operations,
    )
    contender = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=evolution_service,
        lease_duration=timedelta(milliseconds=120),
        heartbeat_interval=timedelta(milliseconds=20),
        operation_repository=operations,
    )
    source = _source("tx:slow-commit")
    operation = coordinator.begin(
        operation_id="operation:slow-commit",
        source_record_ids=[source.memory_id],
        source_records=(source,),
        defer_assertions=False,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(coordinator.execute, operation)
        store.completion_started.wait(timeout=5)
        sleep(0.25)
        observed, result = contender.execute(operation)
        store.completion_release.wait(timeout=5)
        committed, _ = future.result(timeout=5)

    assert observed.status.value == "evolution_running"
    assert result is None
    assert committed.status.value == "evolution_committed"
    assert committed.lease_recovery_count == 0


def test_stale_lease_recovery_has_an_independent_bound() -> None:
    plane = MemoryPlaneService()
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    operations = MemoryPlaneEvolutionOperationRepository(plane)
    coordinator = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=MemoryEvolutionService(memory_plane=plane),
        now_provider=lambda: now[0],
        max_attempts=10,
        max_lease_recoveries=1,
        lease_duration=timedelta(seconds=3),
        heartbeat_interval=timedelta(seconds=1),
        operation_repository=operations,
    )
    source = _source("tx:stale-lease")
    operation = coordinator.begin(
        operation_id="operation:stale-lease",
        source_record_ids=[source.memory_id],
        source_records=(source,),
        defer_assertions=False,
    )

    first_claim, acquired = coordinator._claim(operation)
    assert acquired is True
    now[0] += timedelta(seconds=4)
    recovered, acquired = coordinator._claim(first_claim)
    assert acquired is True
    assert recovered.attempt_count == 2
    assert recovered.lease_recovery_count == 1

    now[0] += timedelta(seconds=4)
    exhausted, acquired = coordinator._claim(recovered)

    assert acquired is False
    assert exhausted.status.value == "evolution_failed"
    assert exhausted.failure is not None
    assert exhausted.failure.category.value == "lease_recovery_exhausted"
    assert exhausted.attempt_count == 2
    assert exhausted.lease_recovery_count == 1


def test_stale_worker_cannot_commit_after_lease_ownership_transfers() -> None:
    store = _OwnershipTransferStore()
    plane = MemoryPlaneService(record_store=store)
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    operations = MemoryPlaneEvolutionOperationRepository(plane)
    evolution_service = MemoryEvolutionService(memory_plane=plane)
    owner = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=evolution_service,
        now_provider=lambda: now[0],
        lease_duration=timedelta(seconds=10),
        heartbeat_interval=timedelta(seconds=5),
        operation_repository=operations,
    )
    contender = EvolutionCoordinator(
        memory_plane=plane,
        evolution_service=evolution_service,
        now_provider=lambda: now[0],
        lease_duration=timedelta(seconds=10),
        heartbeat_interval=timedelta(seconds=5),
        operation_repository=operations,
    )
    source = _source("tx:fenced-transfer")
    operation = owner.begin(
        operation_id="operation:fenced-transfer",
        source_record_ids=[source.memory_id],
        source_records=(source,),
        defer_assertions=False,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        stale_future = pool.submit(owner.execute, operation)
        store.stale_commit_started.wait(timeout=5)
        running = operations.get(operation.operation_id)
        assert running is not None
        now[0] += timedelta(seconds=11)
        replacement, acquired = contender._claim(running)
        assert acquired is True
        assert replacement.ownership_epoch == running.ownership_epoch + 1
        assert evolution_service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS) == []
        store.stale_commit_release.wait(timeout=5)
        stale_observation, stale_result = stale_future.result(timeout=5)

    assert stale_result is None
    assert stale_observation.execution_token == replacement.execution_token
    assert evolution_service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS) == []

    now[0] += timedelta(seconds=11)
    committed, result = contender.execute(replacement)

    assert result is not None
    assert committed.status == EvolutionOperationStatus.COMMITTED
    assert committed.completed_fence_epoch == replacement.ownership_epoch + 1
    assert len(evolution_service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)) == 1


def test_projection_and_committed_operation_are_one_atomic_batch() -> None:
    store = _LostAcknowledgementStore()
    plane = MemoryPlaneService(record_store=store)
    extractor = _CountingExtractor()
    operations = MemoryPlaneEvolutionOperationRepository(plane)
    provider = ProviderMemoryService(
        memory_plane=plane,
        memory_evolution_extractor=extractor,
        memory_evolution_operation_repository=operations,
    )
    store.lose_completion_acknowledgement = True

    result = provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        task_id="task:atlas",
        user_id="user:alice",
        operation_id="operation:lost-ack",
    )

    assert len(result.evolution_outcomes) == 1
    assert result.evolution_outcomes[0].status == "evolution_committed"
    assert extractor.calls == 1
    assert provider.reconcile_memory_evolution() == []
    assert len(provider.memory_evolution_service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)) == 1
    operation = operations.get("operation:lost-ack")
    assert operation is not None
    assert operation.status.value == "evolution_committed"


def test_operation_id_cannot_be_reused_for_different_sources() -> None:
    plane = MemoryPlaneService()
    provider = ProviderMemoryService(memory_plane=plane)
    provider.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas migration owner is Alice.",
        operation_id="operation:collision",
    )

    try:
        provider.sync_event(
            operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
            content="Atlas migration owner is Bob.",
            operation_id="operation:collision",
        )
    except ValueError as exc:
        assert "already bound to different source records" in str(exc)
    else:
        raise AssertionError("operation id collision must fail closed")
