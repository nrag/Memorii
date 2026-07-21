from __future__ import annotations

from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution import (
    MemoryEvolutionMutationValidationError,
    MemoryEvolutionService,
    MemoryGraphValidator,
)
from memorii.core.memory_evolution.models import MemoryGraphSnapshot
from memorii.core.memory_plane import (
    MemoryPlaneRevisionConflictError,
    MemoryPlaneService,
    MemoryPlaneUnitOfWork,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    MemoryPlanePrecondition,
    RecordAbsentPrecondition,
)
from memorii.domain.enums import CommitStatus, MemoryDomain


def _record(memory_id: str, text: str, *, domain: MemoryDomain = MemoryDomain.TRANSCRIPT) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=domain,
        text=text,
        content={"text": text},
        status=CommitStatus.COMMITTED,
        source_kind="test_source",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        task_id="task:atomicity",
        is_raw_event=domain == MemoryDomain.TRANSCRIPT,
    )


class _RejectingGraphValidator(MemoryGraphValidator):
    def validate_snapshot(self, snapshot: MemoryGraphSnapshot) -> list[str]:
        assert snapshot.nodes
        return ["injected_graph_failure"]


class _FailingBatchStore(InMemoryMemoryPlaneStore):
    def __init__(self) -> None:
        super().__init__()
        self.fail_batch = False

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
    ) -> int:
        if self.fail_batch:
            raise OSError("injected batch failure")
        return super().apply_batch(
            records,
            expected_revision=expected_revision,
            preconditions=preconditions,
        )


def test_graph_validation_failure_leaves_memory_plane_unchanged() -> None:
    plane = MemoryPlaneService()
    marker = _record("mem:marker", "existing", domain=MemoryDomain.SEMANTIC)
    plane.stage_record(marker)
    before = plane.list_records()
    service = MemoryEvolutionService(
        memory_plane=plane,
        graph_validator=_RejectingGraphValidator(),
    )

    with pytest.raises(MemoryEvolutionMutationValidationError, match="injected_graph_failure"):
        service.evolve_records([_record("tx:owner", "Atlas owner is Bob.")])

    assert plane.list_records() == before


def test_store_failure_cannot_publish_a_partial_evolution() -> None:
    store = _FailingBatchStore()
    plane = MemoryPlaneService(record_store=store)
    marker = _record("mem:marker", "existing", domain=MemoryDomain.SEMANTIC)
    plane.stage_record(marker)
    before = plane.list_records()
    store.fail_batch = True

    with pytest.raises(OSError, match="injected batch failure"):
        MemoryEvolutionService(memory_plane=plane).evolve_records(
            [_record("tx:owner", "Atlas owner is Bob.")]
        )

    assert plane.list_records() == before


def test_stale_unit_of_work_is_rejected_without_overwriting_newer_state() -> None:
    store = InMemoryMemoryPlaneStore()
    unit_of_work = MemoryPlaneUnitOfWork(store)
    unit_of_work.stage_record(_record("mem:stale", "stale", domain=MemoryDomain.SEMANTIC))
    newer = _record("mem:newer", "newer", domain=MemoryDomain.SEMANTIC)
    store.stage_record(newer)

    with pytest.raises(MemoryPlaneRevisionConflictError):
        unit_of_work.commit()

    assert store.get_record("mem:newer") == newer
    assert store.get_record("mem:stale") is None


def test_unit_of_work_preserves_staged_preconditions_until_commit() -> None:
    store = InMemoryMemoryPlaneStore()
    existing = _record("mem:existing", "existing", domain=MemoryDomain.SEMANTIC)
    store.stage_record(existing)
    unit_of_work = MemoryPlaneUnitOfWork(store)
    staged = _record("mem:staged", "staged", domain=MemoryDomain.SEMANTIC)
    unit_of_work.apply_batch(
        (staged,),
        expected_revision=unit_of_work.base_revision,
        preconditions=(RecordAbsentPrecondition(memory_id=existing.memory_id),),
    )

    with pytest.raises(MemoryPlaneRevisionConflictError, match="precondition failed"):
        unit_of_work.commit()

    assert store.get_record(existing.memory_id) == existing
    assert store.get_record(staged.memory_id) is None
