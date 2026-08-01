from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.memory_evolution.operation_models import (
    EvolutionOperation,
    EvolutionOperationStatus,
)
from memorii.core.memory_evolution.operation_store import (
    EvolutionOperationStoreCorruptionError,
    MemoryPlaneEvolutionOperationRepository,
    operation_from_record,
    record_from_operation,
)
from memorii.core.memory_plane.models import MemoryRecordFence
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore, JsonlMemoryPlaneStore
from memorii.domain.enums import MemoryRecordVisibility


def _pending_operation(operation_id: str = "operation:test") -> EvolutionOperation:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return EvolutionOperation(
        operation_id=operation_id,
        source_record_ids=[f"tx:{operation_id}"],
        source_fingerprint="0" * 64,
        defer_assertions=False,
        status=EvolutionOperationStatus.PENDING,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _running_candidate(operation: EvolutionOperation, *, token: str) -> EvolutionOperation:
    return EvolutionOperation.model_validate(
        {
            **operation.model_dump(mode="python"),
            "state_revision": operation.state_revision + 1,
            "status": EvolutionOperationStatus.RUNNING,
            "attempt_count": 1,
            "ownership_epoch": operation.ownership_epoch + 1,
            "execution_token": token,
            "lease_expires_at": operation.updated_at + timedelta(minutes=1),
        }
    )


def _repository(store: InMemoryMemoryPlaneStore | JsonlMemoryPlaneStore) -> MemoryPlaneEvolutionOperationRepository:
    return MemoryPlaneEvolutionOperationRepository(MemoryPlaneService(record_store=store))


def _claim_from_process(path: str, operation_payload: dict[str, object], token: str) -> bool:
    operation = EvolutionOperation.model_validate(operation_payload)
    repository = _repository(JsonlMemoryPlaneStore(path))
    return repository.compare_and_set(
        expected_state_revision=operation.state_revision,
        operation=_running_candidate(operation, token=token),
    )


@pytest.mark.parametrize(
    "repository_factory",
    [
        lambda _path: _repository(InMemoryMemoryPlaneStore()),
        lambda path: _repository(JsonlMemoryPlaneStore(path)),
    ],
)
def test_operation_repository_compare_and_set_has_one_winner(
    tmp_path: Path,
    repository_factory,
) -> None:
    repository = repository_factory(tmp_path / "memory-plane")
    pending = repository.create(_pending_operation())

    first = repository.compare_and_set(
        expected_state_revision=pending.state_revision,
        operation=_running_candidate(pending, token="first"),
    )
    second = repository.compare_and_set(
        expected_state_revision=pending.state_revision,
        operation=_running_candidate(pending, token="second"),
    )

    assert first is True
    assert second is False
    stored = repository.get(pending.operation_id)
    assert stored is not None
    assert stored.execution_token == "first"
    assert stored.ownership_epoch == 1


def test_filesystem_operation_repository_serializes_process_claims(tmp_path: Path) -> None:
    path = tmp_path / "memory-plane"
    repository = _repository(JsonlMemoryPlaneStore(path))
    pending = repository.create(_pending_operation("operation:process-contention"))
    payload = pending.model_dump(mode="python")

    try:
        pool = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn"))
    except (NotImplementedError, PermissionError) as exc:
        pytest.skip(f"process semaphore capability is unavailable: {exc}")
    with pool:
        outcomes = list(
            pool.map(
                _claim_from_process,
                [str(path), str(path)],
                [payload, payload],
                ["first", "second"],
            )
        )

    assert sorted(outcomes) == [False, True]
    stored = _repository(JsonlMemoryPlaneStore(path)).get(pending.operation_id)
    assert stored is not None
    assert stored.execution_token in {"first", "second"}


def test_filesystem_operation_repository_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "memory-plane"
    repository = _repository(JsonlMemoryPlaneStore(path))
    pending = repository.create(_pending_operation("operation:reopen"))
    running = _running_candidate(pending, token="owner")
    assert repository.compare_and_set(
        expected_state_revision=pending.state_revision,
        operation=running,
    )

    reopened = _repository(JsonlMemoryPlaneStore(path)).get(pending.operation_id)

    assert reopened == running


def test_operation_repository_fails_closed_on_malformed_internal_record() -> None:
    plane = MemoryPlaneService()
    repository = MemoryPlaneEvolutionOperationRepository(plane)
    operation = _pending_operation("operation:malformed")
    malformed = record_from_operation(operation).model_copy(
        update={"content": {"memory_evolution_kind": "operation", "operation": {"operation_id": "bad"}}}
    )
    plane.write_records((malformed,))

    with pytest.raises(EvolutionOperationStoreCorruptionError, match="invalid memory-evolution operation"):
        repository.get(operation.operation_id)


@pytest.mark.parametrize(
    "update",
    [
        {"visibility": MemoryRecordVisibility.RUNTIME_CONTEXT},
        {"mutation_fence": MemoryRecordFence(execution_token="wrong-owner", ownership_epoch=1)},
        {"memory_id": "mem:evolution:operation:wrong-id"},
    ],
)
def test_operation_repository_fails_closed_on_malformed_control_envelope(
    update: dict[str, object],
) -> None:
    operation = _pending_operation("operation:malformed-envelope")
    record = record_from_operation(operation).model_copy(update=update)

    with pytest.raises(EvolutionOperationStoreCorruptionError, match="invalid memory-evolution operation envelope"):
        operation_from_record(record)
