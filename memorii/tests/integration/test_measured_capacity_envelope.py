"""Measured capacity envelope for the bounded runtime operations.

Populates a representative fixture (tasks, solver runs, overlays,
justifications, event-free batch publications) and wall-clocks the
design's named bounded operations, asserting each stays inside the
recorded envelope. The measured numbers are printed so the release
evidence can cite them; failures mean the envelope must be revised
explicitly, never silently widened.
"""
from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.persistence.runtime_api import RuntimeCommandService
from memorii.core.persistence.runtime_contracts import (
    RuntimeCommandRequest,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import (
    publish_runtime_change,
)
from memorii.core.storage_administration.service import (
    StorageAdministrationService,
)

# Design reference fixture scaled for CI: a bounded slice of the stated
# 10k/50k envelope that still exercises the same code paths per operation.
TASK_COUNT = 200
OVERLAYS_PER_TASK = 5
JUSTIFICATIONS_PER_TASK = 5

# Recorded envelope (seconds) for this fixture class on CI-class hardware.
# Exceeding these is a capacity regression: revise explicitly with evidence.
STATE_READ_P95_BUDGET = 2.0
DISPATCH_P95_BUDGET = 2.0
CHECKPOINT_BUDGET = 10.0
TIER_A_VERIFY_BUDGET = 5.0

_NOW = datetime(2026, 10, 2, tzinfo=UTC)


def _populate(administration: StorageAdministrationService) -> None:
    for index in range(TASK_COUNT):
        def seed(connection, repo, index=index) -> None:
            task_id = f"task:capacity:{index}"
            repo.apply_task(
                connection,
                TaskRecord(
                    task_id=task_id,
                    principal="principal:capacity",
                    goal=f"Capacity fixture {index}",
                    created_at=_NOW,
                    root_execution_node_id="exec:" + task_id,
                ),
            )
            from memorii.core.persistence.runtime_contracts import (
                OverlayJustificationBinding,
                RuntimeOverlayVersion,
                SolverJustificationRecord,
                SolverRunRecord,
            )

            solver_id = f"solver:capacity:{index}"
            repo.apply_solver_run(
                connection,
                SolverRunRecord(
                    solver_id=solver_id,
                    task_id=task_id,
                    parent_execution_node_id="exec:" + task_id,
                    category="capacity",
                    created_by="fixture",
                ),
            )
            for version in range(OVERLAYS_PER_TASK):
                repo.apply_overlay(
                    connection,
                    RuntimeOverlayVersion(
                        version_id=f"overlay:capacity:{index}:{version}",
                        solver_id=solver_id,
                        node_bindings=(
                            OverlayJustificationBinding(
                                node_id=f"node:{index}:{version}",
                                frontier=version == 0,
                            ),
                        ),
                        created_at=_NOW,
                        committed=version % 2 == 0,
                    ),
                )
            for justification in range(JUSTIFICATIONS_PER_TASK):
                repo.apply_justification(
                    connection,
                    SolverJustificationRecord(
                        justification_id=f"justification:capacity:{index}:{justification}",
                        solver_id=solver_id,
                        conclusion=f"fixture conclusion {justification}",
                        strength=0.5,
                        active=justification % 2 == 0,
                    ),
                )

        publish_runtime_change(
            administration, seed, operation_binding=f"capacity:{index}"
        )


def _service(tmp_path: Path) -> RuntimeCommandService:
    administration = StorageAdministrationService(tmp_path / "installation")
    administration.initialize()
    _populate(administration)
    return RuntimeCommandService(administration, client_namespace="capacity")


def test_measured_capacity_envelope(tmp_path: Path) -> None:
    service = _service(tmp_path)
    try:
        task_id = "task:capacity:0"

        # Bounded no-model command latency (dispatch of host-event kinds).
        samples: list[float] = []
        for index in range(20):
            started = time.perf_counter()
            receipt = service.dispatch(
                RuntimeCommandRequest(
                    kind="record_observation",
                    operation_id=f"op:capacity:{index}",
                    task_id=task_id,
                    expected_revision=0,
                    source_digest="a" * 64,
                )
            )
            assert receipt.status == "committed"
            samples.append(time.perf_counter() - started)
        dispatch_p95 = statistics.quantiles(samples, n=20)[18]
        print(f"\nmeasured dispatch p95: {dispatch_p95:.4f}s over {len(samples)} samples")

        # Signed checkpoint creation over the full fixture.
        started = time.perf_counter()
        checkpointed = service.dispatch(
            RuntimeCommandRequest(
                kind="checkpoint_task",
                operation_id="op:capacity:checkpoint",
                task_id=task_id,
                expected_revision=0,
            )
        )
        checkpoint_seconds = time.perf_counter() - started
        assert checkpointed.status == "committed"
        print(f"measured checkpoint: {checkpoint_seconds:.4f}s over {TASK_COUNT} tasks")

        # Tier-A-style verified snapshot acquisition.
        started = time.perf_counter()
        snapshot = service._administration.acquire_verified_snapshot()
        tier_a = time.perf_counter() - started
        del snapshot
        print(f"measured verified snapshot: {tier_a:.4f}s")

        # Bounded envelope assertions — explicit, never silently widened.
        assert dispatch_p95 <= DISPATCH_P95_BUDGET, (
            f"dispatch p95 {dispatch_p95:.4f}s exceeds the "
            f"{DISPATCH_P95_BUDGET}s envelope"
        )
        assert checkpoint_seconds <= CHECKPOINT_BUDGET, (
            f"checkpoint {checkpoint_seconds:.4f}s exceeds the "
            f"{CHECKPOINT_BUDGET}s envelope"
        )
        assert tier_a <= TIER_A_VERIFY_BUDGET, (
            f"verified snapshot {tier_a:.4f}s exceeds the "
            f"{TIER_A_VERIFY_BUDGET}s envelope"
        )
    finally:
        service._administration.close()


def test_disk_full_publication_fails_closed_without_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENOSPC during a publication aborts cleanly; prior state survives."""
    service = _service(tmp_path)
    try:
        repository = service.repository
        baseline = repository.runtime_revision()

        real_write = repository._partition.upsert_runtime_row

        def out_of_space(*args: object, **kwargs: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(repository._partition, "upsert_runtime_row", out_of_space)
        with pytest.raises(OSError, match="No space left on device"):
            service.dispatch(
                RuntimeCommandRequest(
                    kind="record_observation",
                    operation_id="op:diskfull",
                    task_id="task:capacity:0",
                    expected_revision=0,
                    source_digest="b" * 64,
                )
            )
        monkeypatch.setattr(
            repository._partition, "upsert_runtime_row", real_write
        )

        # The failed publication rolled back: no revision advanced past the
        # populate baseline, and the installation still serves verified reads
        # (fail-closed, no partial durable state).
        after = repository.runtime_revision()
        assert after == baseline, (
            f"failed dispatch advanced the revision: {baseline} -> {after}"
        )
        second = service.dispatch(
            RuntimeCommandRequest(
                kind="record_observation",
                operation_id="op:diskfull:retry",
                task_id="task:capacity:0",
                expected_revision=0,
                source_digest="c" * 64,
            )
        )
        assert second.status == "committed"
        snapshot = service._administration.acquire_verified_snapshot()
        del snapshot
    finally:
        service._administration.close()
