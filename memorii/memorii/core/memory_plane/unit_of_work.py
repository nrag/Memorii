"""Revisioned memory-plane unit of work."""

from __future__ import annotations

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import MemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain


class MemoryPlaneUnitOfWork:
    """Isolated read/write view committed with one optimistic batch."""

    def __init__(self, store: MemoryPlaneStore) -> None:
        self._store = store
        self._base_revision, records = store.read_snapshot()
        self._records = {record.memory_id: record for record in records}
        self._pending: dict[str, CanonicalMemoryRecord] = {}
        self._committed_revision: int | None = None

    @property
    def base_revision(self) -> int:
        return self._base_revision

    @property
    def pending_records(self) -> tuple[CanonicalMemoryRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._pending.values())

    @property
    def committed(self) -> bool:
        return self._committed_revision is not None

    def stage_record(self, record: CanonicalMemoryRecord) -> None:
        self._ensure_open()
        self._pending[record.memory_id] = record.model_copy(deep=True)

    def write_records(self, records: tuple[CanonicalMemoryRecord, ...]) -> int:
        self._ensure_open()
        for record in records:
            self.stage_record(record)
        return self._base_revision

    def upsert_record(self, record: CanonicalMemoryRecord) -> None:
        self.stage_record(record)

    def revision(self) -> int:
        return self._base_revision

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int,
    ) -> int:
        self._ensure_open()
        if expected_revision != self._base_revision:
            raise ValueError(
                f"unit-of-work revision mismatch: expected {expected_revision}, base {self._base_revision}"
            )
        for record in records:
            self._pending[record.memory_id] = record.model_copy(deep=True)
        return self._base_revision

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        return self._base_revision, tuple(record.model_copy(deep=True) for record in self._current_records().values())

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        record = self._pending.get(memory_id, self._records.get(memory_id))
        return record.model_copy(deep=True) if record is not None else None

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        domain_set = set(domains) if domains is not None else None
        return [
            record.model_copy(deep=True)
            for record in self._current_records().values()
            if (status is None or record.status == status)
            and (domain_set is None or record.domain in domain_set)
            and (source_kind is None or record.source_kind == source_kind)
        ]

    def commit(
        self,
        *,
        records: tuple[CanonicalMemoryRecord, ...] | None = None,
        expected_revision: int | None = None,
    ) -> int:
        self._ensure_open()
        records = self.pending_records if records is None else records
        expected_revision = self._base_revision if expected_revision is None else expected_revision
        if records != self.pending_records:
            raise ValueError("commit records do not match the staged unit-of-work records")
        if expected_revision != self._base_revision:
            raise ValueError("commit revision does not match the unit-of-work base revision")
        if not self._pending:
            self._committed_revision = self._base_revision
            return self._base_revision
        self._committed_revision = self._store.apply_batch(
            records,
            expected_revision=expected_revision,
        )
        return self._committed_revision

    def _current_records(self) -> dict[str, CanonicalMemoryRecord]:
        return {**self._records, **self._pending}

    def _ensure_open(self) -> None:
        if self.committed:
            raise RuntimeError("memory-plane unit of work is already committed")
