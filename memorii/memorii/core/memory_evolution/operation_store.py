"""Authoritative memory-plane repository for evolution operation state."""

from __future__ import annotations

from typing import Protocol

from memorii.core.memory_evolution.operation_models import (
    EvolutionOperation,
    EvolutionOperationStatus,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord, MemoryRecordFence
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    RecordFencePrecondition,
    record_digest,
)
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
    TemporalValidityStatus,
)


class EvolutionOperationStoreCorruptionError(RuntimeError):
    """An internal operation record cannot be decoded without losing truth."""


class EvolutionOperationRepository(Protocol):
    def create(self, operation: EvolutionOperation) -> EvolutionOperation: ...

    def get(self, operation_id: str) -> EvolutionOperation | None: ...

    def list(self) -> list[EvolutionOperation]: ...

    def compare_and_set(
        self,
        *,
        expected_state_revision: int,
        operation: EvolutionOperation,
    ) -> bool: ...


class MemoryPlaneEvolutionOperationRepository:
    """Stores ownership and completion state in the projection commit authority."""

    def __init__(self, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane

    def create(self, operation: EvolutionOperation) -> EvolutionOperation:
        existing = self.get(operation.operation_id)
        if existing is not None:
            return existing
        try:
            self._memory_plane.conditionally_write_records(
                (record_from_operation(operation),),
                preconditions=(RecordAbsentPrecondition(memory_id=operation_memory_id(operation.operation_id)),),
            )
        except MemoryPlaneRevisionConflictError:
            existing = self.get(operation.operation_id)
            if existing is None:
                raise
            return existing
        return operation.model_copy(deep=True)

    def get(self, operation_id: str) -> EvolutionOperation | None:
        return operation_from_record(self._memory_plane.get_record(operation_memory_id(operation_id)))

    def list(self) -> list[EvolutionOperation]:
        operations = [
            operation
            for record in self._memory_plane.list_records(source_kind="memory_evolution:operation")
            if (operation := operation_from_record(record)) is not None
        ]
        return sorted(operations, key=lambda item: item.operation_id)

    def compare_and_set(
        self,
        *,
        expected_state_revision: int,
        operation: EvolutionOperation,
    ) -> bool:
        current_record = self._memory_plane.get_record(operation_memory_id(operation.operation_id))
        current = operation_from_record(current_record)
        if current is None or current_record is None or current.state_revision != expected_state_revision:
            return False
        if operation.state_revision != expected_state_revision + 1:
            raise ValueError("operation CAS must advance state_revision by exactly one")
        try:
            self._memory_plane.conditionally_write_records(
                (record_from_operation(operation),),
                preconditions=(
                    RecordDigestPrecondition(
                        memory_id=current_record.memory_id,
                        expected_digest=record_digest(current_record),
                    ),
                ),
            )
        except MemoryPlaneRevisionConflictError:
            return False
        return True


def operation_memory_id(operation_id: str) -> str:
    return f"mem:evolution:operation:{operation_id}"


def operation_fence_precondition(operation: EvolutionOperation) -> RecordFencePrecondition:
    if operation.status != EvolutionOperationStatus.RUNNING or operation.execution_token is None:
        raise ValueError("only a running operation can provide a projection fence")
    return RecordFencePrecondition(
        memory_id=operation_memory_id(operation.operation_id),
        expected_fence=MemoryRecordFence(
            execution_token=operation.execution_token,
            ownership_epoch=operation.ownership_epoch,
        ),
    )


def record_from_operation(operation: EvolutionOperation) -> CanonicalMemoryRecord:
    fence = None
    if operation.status == EvolutionOperationStatus.RUNNING:
        if operation.execution_token is None:
            raise ValueError("running operation is missing its execution token")
        fence = MemoryRecordFence(
            execution_token=operation.execution_token,
            ownership_epoch=operation.ownership_epoch,
        )
    return CanonicalMemoryRecord(
        memory_id=operation_memory_id(operation.operation_id),
        domain=MemoryDomain.EXECUTION,
        text=f"Memory evolution {operation.status.value}",
        content={
            "memory_evolution_kind": "operation",
            "operation": operation.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="memory_evolution:operation",
        timestamp=operation.updated_at,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        mutation_fence=fence,
    )


def operation_from_record(record: CanonicalMemoryRecord | None) -> EvolutionOperation | None:
    if record is None:
        return None
    if (
        record.domain != MemoryDomain.EXECUTION
        or record.status != CommitStatus.COMMITTED
        or record.source_kind != "memory_evolution:operation"
        or record.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
        or record.content.get("memory_evolution_kind") != "operation"
    ):
        raise EvolutionOperationStoreCorruptionError(
            f"invalid memory-evolution operation envelope: {record.memory_id}"
        )
    try:
        operation = EvolutionOperation.model_validate(record.content.get("operation"))
    except ValueError as exc:
        raise EvolutionOperationStoreCorruptionError(
            f"invalid memory-evolution operation record {record.memory_id}: {exc}"
        ) from exc
    expected_record = record_from_operation(operation)
    if (
        record.memory_id != expected_record.memory_id
        or record.mutation_fence != expected_record.mutation_fence
    ):
        raise EvolutionOperationStoreCorruptionError(
            f"invalid memory-evolution operation envelope: {record.memory_id}"
        )
    return operation
