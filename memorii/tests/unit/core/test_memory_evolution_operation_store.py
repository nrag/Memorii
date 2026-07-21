from __future__ import annotations

import json
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
    InMemoryEvolutionOperationRepository,
    JsonEvolutionOperationRepository,
)


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
            "execution_token": token,
            "lease_expires_at": operation.updated_at + timedelta(minutes=1),
        }
    )


def _claim_from_process(path: str, operation_payload: dict[str, object], token: str) -> bool:
    operation = EvolutionOperation.model_validate(operation_payload)
    repository = JsonEvolutionOperationRepository(path)
    return repository.compare_and_set(
        expected_state_revision=operation.state_revision,
        operation=_running_candidate(operation, token=token),
    )


@pytest.mark.parametrize(
    "repository_factory",
    [
        lambda _path: InMemoryEvolutionOperationRepository(),
        lambda path: JsonEvolutionOperationRepository(path),
    ],
)
def test_operation_repository_compare_and_set_has_one_winner(
    tmp_path: Path,
    repository_factory,
) -> None:
    repository = repository_factory(tmp_path / "operations")
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


def test_json_operation_repository_serializes_process_claims(tmp_path: Path) -> None:
    path = tmp_path / "operations"
    repository = JsonEvolutionOperationRepository(path)
    pending = repository.create(_pending_operation("operation:process-contention"))
    payload = pending.model_dump(mode="python")

    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as pool:
        outcomes = list(
            pool.map(
                _claim_from_process,
                [str(path), str(path)],
                [payload, payload],
                ["first", "second"],
            )
        )

    assert sorted(outcomes) == [False, True]
    stored = JsonEvolutionOperationRepository(path).get(pending.operation_id)
    assert stored is not None
    assert stored.execution_token in {"first", "second"}


def test_json_operation_repository_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "operations"
    pending = JsonEvolutionOperationRepository(path).create(_pending_operation("operation:reopen"))
    running = _running_candidate(pending, token="owner")
    assert JsonEvolutionOperationRepository(path).compare_and_set(
        expected_state_revision=pending.state_revision,
        operation=running,
    )

    reopened = JsonEvolutionOperationRepository(path).get(pending.operation_id)

    assert reopened == running


def test_json_operation_repository_rejects_incomplete_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "operations"
    repository = JsonEvolutionOperationRepository(path)
    repository.create(_pending_operation())
    snapshot_path = path / "evolution_operations.json"
    snapshot_path.write_text(snapshot_path.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")

    with pytest.raises(EvolutionOperationStoreCorruptionError, match="incomplete"):
        repository.list()


def test_json_operation_repository_rejects_checksum_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "operations"
    repository = JsonEvolutionOperationRepository(path)
    repository.create(_pending_operation())
    snapshot_path = path / "evolution_operations.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["operations"][0]["defer_assertions"] = True
    snapshot_path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")

    with pytest.raises(EvolutionOperationStoreCorruptionError, match="checksum"):
        repository.list()
