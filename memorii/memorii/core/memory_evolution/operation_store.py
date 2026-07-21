"""Process-safe persistence for mutable memory-evolution operation state."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.operation_models import EvolutionOperation
from memorii.core.memory_plane.file_lock import locked_file


class EvolutionOperationStoreCorruptionError(RuntimeError):
    """Persisted operation state cannot be read without losing truth."""


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


class InMemoryEvolutionOperationRepository:
    def __init__(self) -> None:
        self._operations: dict[str, EvolutionOperation] = {}
        self._lock = RLock()

    def create(self, operation: EvolutionOperation) -> EvolutionOperation:
        with self._lock:
            existing = self._operations.get(operation.operation_id)
            if existing is not None:
                return existing.model_copy(deep=True)
            self._operations[operation.operation_id] = operation.model_copy(deep=True)
            return operation.model_copy(deep=True)

    def get(self, operation_id: str) -> EvolutionOperation | None:
        with self._lock:
            operation = self._operations.get(operation_id)
            return operation.model_copy(deep=True) if operation is not None else None

    def list(self) -> list[EvolutionOperation]:
        with self._lock:
            return [
                operation.model_copy(deep=True)
                for operation in sorted(
                    self._operations.values(),
                    key=lambda item: item.operation_id,
                )
            ]

    def compare_and_set(
        self,
        *,
        expected_state_revision: int,
        operation: EvolutionOperation,
    ) -> bool:
        with self._lock:
            current = self._operations.get(operation.operation_id)
            if current is None or current.state_revision != expected_state_revision:
                return False
            if operation.state_revision != expected_state_revision + 1:
                raise ValueError("operation CAS must advance state_revision by exactly one")
            self._operations[operation.operation_id] = operation.model_copy(deep=True)
            return True


class _OperationSnapshot(BaseModel):
    operations: tuple[EvolutionOperation, ...]
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def create(cls, operations: tuple[EvolutionOperation, ...]) -> _OperationSnapshot:
        ordered = tuple(sorted(operations, key=lambda item: item.operation_id))
        return cls(operations=ordered, checksum=_snapshot_checksum(ordered))

    @model_validator(mode="after")
    def validate_checksum(self) -> _OperationSnapshot:
        if self.checksum != _snapshot_checksum(self.operations):
            raise ValueError("evolution-operation snapshot checksum mismatch")
        return self


class JsonEvolutionOperationRepository:
    """Crash-atomic operation snapshot guarded by a process-level lock."""

    def __init__(self, path: str | Path) -> None:
        self._base_path = Path(path)
        self._snapshot_path = self._base_path / "evolution_operations.json"
        self._lock_path = self._base_path / "evolution_operations.lock"
        self._base_path.mkdir(parents=True, exist_ok=True)

    def create(self, operation: EvolutionOperation) -> EvolutionOperation:
        with locked_file(self._lock_path, exclusive=True):
            operations = self._read_unlocked()
            existing = operations.get(operation.operation_id)
            if existing is not None:
                return existing.model_copy(deep=True)
            operations[operation.operation_id] = operation.model_copy(deep=True)
            self._write_unlocked(operations)
            return operation.model_copy(deep=True)

    def get(self, operation_id: str) -> EvolutionOperation | None:
        with locked_file(self._lock_path, exclusive=False):
            operation = self._read_unlocked().get(operation_id)
            return operation.model_copy(deep=True) if operation is not None else None

    def list(self) -> list[EvolutionOperation]:
        with locked_file(self._lock_path, exclusive=False):
            return [
                operation.model_copy(deep=True)
                for operation in sorted(
                    self._read_unlocked().values(),
                    key=lambda item: item.operation_id,
                )
            ]

    def compare_and_set(
        self,
        *,
        expected_state_revision: int,
        operation: EvolutionOperation,
    ) -> bool:
        with locked_file(self._lock_path, exclusive=True):
            operations = self._read_unlocked()
            current = operations.get(operation.operation_id)
            if current is None or current.state_revision != expected_state_revision:
                return False
            if operation.state_revision != expected_state_revision + 1:
                raise ValueError("operation CAS must advance state_revision by exactly one")
            operations[operation.operation_id] = operation.model_copy(deep=True)
            self._write_unlocked(operations)
            return True

    def _read_unlocked(self) -> dict[str, EvolutionOperation]:
        if not self._snapshot_path.exists():
            return {}
        try:
            content = self._snapshot_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise EvolutionOperationStoreCorruptionError(f"cannot read evolution-operation snapshot: {exc}") from exc
        if content and not content.endswith("\n"):
            raise EvolutionOperationStoreCorruptionError("evolution-operation snapshot is incomplete")
        try:
            snapshot = _OperationSnapshot.model_validate_json(content)
        except ValueError as exc:
            raise EvolutionOperationStoreCorruptionError(f"invalid evolution-operation snapshot: {exc}") from exc
        operations = {operation.operation_id: operation for operation in snapshot.operations}
        if len(operations) != len(snapshot.operations):
            raise EvolutionOperationStoreCorruptionError(
                "evolution-operation snapshot contains duplicate operation IDs"
            )
        return operations

    def _write_unlocked(self, operations: dict[str, EvolutionOperation]) -> None:
        snapshot = _OperationSnapshot.create(tuple(operations.values()))
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._base_path,
            prefix=f".{self._snapshot_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(snapshot.model_dump_json())
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._snapshot_path)
            _fsync_directory(self._base_path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise


def _snapshot_checksum(operations: tuple[EvolutionOperation, ...]) -> str:
    payload = json.dumps(
        [operation.model_dump(mode="json") for operation in operations],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
