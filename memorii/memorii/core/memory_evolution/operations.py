"""Durable orchestration state for source-to-memory evolution."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionRunError
from memorii.core.memory_evolution.models import FallbackOutcome, MemoryEvolutionResult
from memorii.core.memory_evolution.mutations import MemoryEvolutionMutationValidationError
from memorii.core.memory_evolution.operation_lease import EvolutionLeaseHeartbeat
from memorii.core.memory_evolution.operation_models import (
    EvolutionFailure,
    EvolutionFailureCategory,
    EvolutionOperation,
    EvolutionOperationStatus,
)
from memorii.core.memory_evolution.operation_store import (
    operation_fence_precondition,
    operation_memory_id,
    record_from_operation,
)
from memorii.core.memory_evolution.service import MemoryEvolutionService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneCorruptionError,
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.operation_store import EvolutionOperationRepository

logger = logging.getLogger(__name__)


class LeaseHeartbeatFactory(Protocol):
    def __call__(
        self,
        *,
        renew: Callable[[], bool],
        interval: timedelta,
    ) -> EvolutionLeaseHeartbeat: ...


class EvolutionCoordinator:
    """Coordinates durable operation state around deterministic projection commits."""

    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        evolution_service: MemoryEvolutionService,
        now_provider: Callable[[], datetime] | None = None,
        max_attempts: int = 3,
        lease_duration: timedelta = timedelta(minutes=5),
        heartbeat_interval: timedelta | None = None,
        heartbeat_factory: LeaseHeartbeatFactory = EvolutionLeaseHeartbeat,
        max_lease_recoveries: int = 3,
        operation_repository: EvolutionOperationRepository,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if max_lease_recoveries < 0:
            raise ValueError("max_lease_recoveries must not be negative")
        resolved_heartbeat_interval = heartbeat_interval or lease_duration / 3
        if resolved_heartbeat_interval <= timedelta(0):
            raise ValueError("heartbeat_interval must be positive")
        if resolved_heartbeat_interval >= lease_duration:
            raise ValueError("heartbeat_interval must be shorter than lease_duration")
        self._memory_plane = memory_plane
        self._evolution_service = evolution_service
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._max_attempts = max_attempts
        self._lease_duration = lease_duration
        self._heartbeat_interval = resolved_heartbeat_interval
        self._heartbeat_factory = heartbeat_factory
        self._max_lease_recoveries = max_lease_recoveries
        self._operations = operation_repository

    def begin(
        self,
        *,
        operation_id: str,
        source_record_ids: list[str],
        source_records: tuple[CanonicalMemoryRecord, ...],
        defer_assertions: bool,
    ) -> EvolutionOperation:
        source_fingerprint = _source_fingerprint(source_records)
        existing = self._read(operation_id)
        if existing is not None:
            _assert_same_operation_definition(
                existing,
                source_record_ids=source_record_ids,
                source_fingerprint=source_fingerprint,
                defer_assertions=defer_assertions,
            )
            return existing
        for attempt in range(self._max_attempts):
            try:
                with self._memory_plane.unit_of_work() as unit_of_work:
                    durable = self._read(operation_id)
                    if durable is not None:
                        _assert_same_operation_definition(
                            durable,
                            source_record_ids=source_record_ids,
                            source_fingerprint=source_fingerprint,
                            defer_assertions=defer_assertions,
                        )
                        return durable
                    now = self._now_provider()
                    operation = EvolutionOperation(
                        operation_id=operation_id,
                        source_record_ids=source_record_ids,
                        source_fingerprint=source_fingerprint,
                        defer_assertions=defer_assertions,
                        status=EvolutionOperationStatus.PENDING,
                        created_at=now,
                        updated_at=now,
                    )
                    self._memory_plane.write_records((*source_records, record_from_operation(operation)))
                    unit_of_work.commit(
                        preconditions=(
                            RecordAbsentPrecondition(memory_id=operation_memory_id(operation_id)),
                        ),
                    )
                    created = self._read(operation_id)
                    if created is None:
                        raise RuntimeError(f"evolution operation was not committed: {operation_id}")
                    _assert_same_operation_definition(
                        created,
                        source_record_ids=source_record_ids,
                        source_fingerprint=source_fingerprint,
                        defer_assertions=defer_assertions,
                    )
                    return created
            except MemoryPlaneRevisionConflictError:
                if attempt + 1 == self._max_attempts:
                    raise
        raise AssertionError("bounded operation creation loop exited unexpectedly")

    def execute(
        self,
        operation: EvolutionOperation,
    ) -> tuple[EvolutionOperation, MemoryEvolutionResult | None]:
        running, acquired = self._claim(operation)
        if not acquired:
            return running, None
        execution_token = running.execution_token
        if execution_token is None:
            raise AssertionError("acquired evolution operation has no execution token")
        heartbeat = self._heartbeat_factory(
            renew=lambda: self._renew_claim(
                operation_id=running.operation_id,
                execution_token=execution_token,
            ),
            interval=self._heartbeat_interval,
        )
        heartbeat.start()
        try:
            result = self._evolution_service.evolve_source_ids(
                running.source_record_ids,
                defer_assertions=running.defer_assertions,
                completion_record_factory=lambda evolution_result: (
                    record_from_operation(
                        self._completion_marker_if_claimed(
                            operation_id=running.operation_id,
                            execution_token=execution_token,
                            result=evolution_result,
                        )
                    ),
                ),
                commit_preconditions=(operation_fence_precondition(running),),
            )
        except Exception as exc:  # orchestration boundary records every projection failure
            heartbeat.stop()
            logger.warning(
                "memory_evolution_projection_failed operation_id=%s error_type=%s",
                running.operation_id,
                type(exc).__name__,
                exc_info=True,
            )
            durable = self._synchronize_completion_marker(running.operation_id)
            if durable is not None and durable.status == EvolutionOperationStatus.COMMITTED:
                return durable, None
            if durable is not None and durable.execution_token != execution_token:
                return durable, None
            failed = self._persist_failure_if_claimed(
                operation_id=running.operation_id,
                execution_token=execution_token,
                exc=exc,
            )
            return failed, None
        heartbeat.stop()
        committed = self._synchronize_completion_marker(running.operation_id)
        if committed is None or committed.status != EvolutionOperationStatus.COMMITTED:
            raise RuntimeError("evolution projection committed without its operation completion record")
        return committed, result

    def reconcile(self) -> list[EvolutionOperation]:
        reconciled: list[EvolutionOperation] = []
        for operation in self._operations.list():
            if operation.status == EvolutionOperationStatus.COMMITTED:
                continue
            if operation.status == EvolutionOperationStatus.FAILED and (
                operation.failure is None or not operation.failure.retryable
            ):
                continue
            updated, _ = self.execute(operation)
            if updated != operation:
                reconciled.append(updated)
        return reconciled

    def _claim(self, operation: EvolutionOperation) -> tuple[EvolutionOperation, bool]:
        for _attempt in range(self._max_attempts):
            current = self._read(operation.operation_id)
            if current is None:
                raise RuntimeError(f"evolution operation disappeared: {operation.operation_id}")
            if current.status == EvolutionOperationStatus.COMMITTED:
                return current, False
            now = self._now_provider()
            if (
                current.status == EvolutionOperationStatus.RUNNING
                and current.lease_expires_at is not None
                and current.lease_expires_at > now
            ):
                return current, False
            if current.status == EvolutionOperationStatus.FAILED and (
                current.failure is None or not current.failure.retryable
            ):
                return current, False
            recovering_expired_lease = current.status == EvolutionOperationStatus.RUNNING
            if recovering_expired_lease and current.lease_recovery_count >= self._max_lease_recoveries:
                exhausted = _lease_recovery_exhausted_operation(
                    current,
                    max_lease_recoveries=self._max_lease_recoveries,
                    updated_at=now,
                )
                if self._compare_and_set(current=current, updated=exhausted):
                    return exhausted, False
                continue
            if current.attempt_count >= self._max_attempts:
                exhausted = _exhausted_operation(
                    current,
                    max_attempts=self._max_attempts,
                    updated_at=now,
                )
                if self._compare_and_set(current=current, updated=exhausted):
                    return exhausted, False
                continue
            running = _advance_operation(
                current,
                status=EvolutionOperationStatus.RUNNING,
                attempt_count=current.attempt_count + 1,
                lease_recovery_count=current.lease_recovery_count + int(recovering_expired_lease),
                ownership_epoch=current.ownership_epoch + 1,
                execution_token=str(uuid4()),
                lease_expires_at=now + self._lease_duration,
                failure=None,
                updated_at=now,
            )
            if self._compare_and_set(current=current, updated=running):
                return running, True
        raise AssertionError("bounded operation claim loop exited unexpectedly")

    def _renew_claim(self, *, operation_id: str, execution_token: str) -> bool:
        for _attempt in range(self._max_attempts):
            current = self._read(operation_id)
            if (
                current is None
                or current.status != EvolutionOperationStatus.RUNNING
                or current.execution_token != execution_token
            ):
                return False
            now = self._now_provider()
            renewed = _advance_operation(
                current,
                lease_expires_at=now + self._lease_duration,
                updated_at=now,
            )
            if self._compare_and_set(current=current, updated=renewed):
                return True
        raise AssertionError("bounded lease-renewal loop exited unexpectedly")

    def _completion_marker_if_claimed(
        self,
        *,
        operation_id: str,
        execution_token: str,
        result: MemoryEvolutionResult,
    ) -> EvolutionOperation:
        durable = self._read(operation_id)
        if (
            durable is None
            or durable.status != EvolutionOperationStatus.RUNNING
            or durable.execution_token != execution_token
        ):
            raise MemoryPlaneRevisionConflictError("evolution operation claim was lost before projection commit")
        return _committed_operation(durable, result, self._now_provider())

    def _persist_failure_if_claimed(
        self,
        *,
        operation_id: str,
        execution_token: str,
        exc: Exception,
    ) -> EvolutionOperation:
        failure = _classify_failure(exc)
        extraction_run = exc.run if isinstance(exc, MemoryExtractionRunError) else None
        for _attempt in range(self._max_attempts):
            current = self._read(operation_id)
            if current is None:
                raise RuntimeError(f"evolution operation disappeared: {operation_id}")
            if current.status == EvolutionOperationStatus.COMMITTED:
                return current
            if current.execution_token != execution_token:
                return current
            failed = _advance_operation(
                current,
                status=EvolutionOperationStatus.FAILED,
                failure=failure,
                extraction_run_id=(
                    extraction_run.extraction_run_id if extraction_run is not None else None
                ),
                extraction_status=extraction_run.status if extraction_run is not None else None,
                provider_attempt_status=(
                    extraction_run.provider_attempt_status if extraction_run is not None else None
                ),
                fallback_outcome=(
                    extraction_run.fallback_outcome
                    if extraction_run is not None
                    else FallbackOutcome.NOT_USED
                ),
                final_extraction_source=(
                    extraction_run.final_output_source if extraction_run is not None else None
                ),
                extraction_failure_code=(
                    extraction_run.failure_code if extraction_run is not None else None
                ),
                primary_failure_code=(
                    extraction_run.primary_failure_code if extraction_run is not None else None
                ),
                fallback_provider=(
                    extraction_run.fallback_provider if extraction_run is not None else None
                ),
                execution_token=None,
                lease_expires_at=None,
                updated_at=self._now_provider(),
            )
            if self._compare_and_set(current=current, updated=failed):
                return failed
        raise AssertionError("bounded claimed-operation persistence loop exited unexpectedly")

    def _read(self, operation_id: str) -> EvolutionOperation | None:
        return self._operations.get(operation_id)

    def _compare_and_set(
        self,
        *,
        current: EvolutionOperation,
        updated: EvolutionOperation,
    ) -> bool:
        return self._operations.compare_and_set(
            expected_state_revision=current.state_revision,
            operation=updated,
        )

    def _synchronize_completion_marker(
        self,
        operation_id: str,
    ) -> EvolutionOperation | None:
        return self._read(operation_id)


def _source_fingerprint(records: tuple[CanonicalMemoryRecord, ...]) -> str:
    payloads: list[dict[str, object]] = []
    for record in records:
        payload = record.model_dump(mode="json")
        payload.pop("timestamp", None)
        payloads.append(payload)
    canonical = json.dumps(payloads, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_same_operation_definition(
    operation: EvolutionOperation,
    *,
    source_record_ids: list[str],
    source_fingerprint: str,
    defer_assertions: bool,
) -> None:
    if (
        operation.source_record_ids != source_record_ids
        or operation.source_fingerprint != source_fingerprint
        or operation.defer_assertions != defer_assertions
    ):
        raise ValueError(f"operation id {operation.operation_id!r} is already bound to different source records")


def _validated_operation_update(
    operation: EvolutionOperation,
    **updates: object,
) -> EvolutionOperation:
    return EvolutionOperation.model_validate({**operation.model_dump(mode="python"), **updates})


def _advance_operation(
    operation: EvolutionOperation,
    **updates: object,
) -> EvolutionOperation:
    return _validated_operation_update(
        operation,
        state_revision=operation.state_revision + 1,
        **updates,
    )


def _committed_operation(
    operation: EvolutionOperation,
    result: MemoryEvolutionResult,
    committed_at: datetime,
) -> EvolutionOperation:
    return _advance_operation(
        operation,
        status=EvolutionOperationStatus.COMMITTED,
        extraction_run_id=result.extraction_run.extraction_run_id,
        extraction_status=result.extraction_run.status,
        provider_attempt_status=result.extraction_run.provider_attempt_status,
        fallback_outcome=result.extraction_run.fallback_outcome,
        final_extraction_source=result.extraction_run.final_output_source,
        extraction_failure_code=result.extraction_run.failure_code,
        primary_failure_code=result.extraction_run.primary_failure_code,
        fallback_provider=result.extraction_run.fallback_provider,
        projection_record_ids=list(result.written_record_ids),
        completed_fence_epoch=operation.ownership_epoch,
        execution_token=None,
        lease_expires_at=None,
        updated_at=committed_at,
    )


def _exhausted_operation(
    operation: EvolutionOperation,
    *,
    max_attempts: int,
    updated_at: datetime,
) -> EvolutionOperation:
    return _advance_operation(
        operation,
        status=EvolutionOperationStatus.FAILED,
        failure=EvolutionFailure(
            category=EvolutionFailureCategory.RETRY_EXHAUSTED,
            error_type="EvolutionRetryExhausted",
            message=f"memory evolution exhausted {max_attempts} attempts",
            retryable=False,
        ),
        execution_token=None,
        lease_expires_at=None,
        updated_at=updated_at,
    )


def _lease_recovery_exhausted_operation(
    operation: EvolutionOperation,
    *,
    max_lease_recoveries: int,
    updated_at: datetime,
) -> EvolutionOperation:
    return _advance_operation(
        operation,
        status=EvolutionOperationStatus.FAILED,
        failure=EvolutionFailure(
            category=EvolutionFailureCategory.LEASE_RECOVERY_EXHAUSTED,
            error_type="EvolutionLeaseRecoveryExhausted",
            message=f"memory evolution exhausted {max_lease_recoveries} stale-lease recoveries",
            retryable=False,
        ),
        execution_token=None,
        lease_expires_at=None,
        updated_at=updated_at,
    )


def _classify_failure(exc: Exception) -> EvolutionFailure:
    if isinstance(exc, MemoryExtractionRunError):
        if exc.run.failure_code is None:
            raise AssertionError("failed extraction is missing its failure code")
        category = (
            EvolutionFailureCategory.PROVIDER_ERROR
            if exc.run.failure_code.value == "provider_error"
            else EvolutionFailureCategory.EXTRACTION_OUTPUT_ERROR
        )
        retryable = exc.retryable
        message = f"memory extraction failed with {exc.run.failure_code.value}"
    elif isinstance(exc, MemoryPlaneRevisionConflictError):
        category = EvolutionFailureCategory.REVISION_CONFLICT
        retryable = True
        message = "memory evolution encountered a concurrent update"
    elif isinstance(exc, MemoryPlaneCorruptionError):
        category = EvolutionFailureCategory.CORRUPTION_ERROR
        retryable = False
        message = "memory evolution storage is corrupted"
    elif isinstance(exc, OSError):
        category = EvolutionFailureCategory.STORE_ERROR
        retryable = True
        message = "memory evolution encountered an operational storage or provider failure"
    elif isinstance(exc, MemoryEvolutionMutationValidationError):
        category = EvolutionFailureCategory.VALIDATION_ERROR
        retryable = False
        message = "memory evolution projection validation failed"
    else:
        category = EvolutionFailureCategory.UNEXPECTED_ERROR
        retryable = False
        message = "memory evolution failed unexpectedly"
    return EvolutionFailure(
        category=category,
        error_type=type(exc).__name__,
        message=message,
        retryable=retryable,
    )
