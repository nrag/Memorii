"""Memory-plane storage contracts and in-memory/JSONL implementations."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain


class MemoryPlaneRevisionConflictError(RuntimeError):
    """Raised when a unit of work commits against a stale store revision."""


class _PersistedBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int
    records: tuple[CanonicalMemoryRecord, ...]


class MemoryPlaneStore(Protocol):
    def stage_record(self, record: CanonicalMemoryRecord) -> None: ...

    def upsert_record(self, record: CanonicalMemoryRecord) -> None: ...

    def revision(self) -> int: ...

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int,
    ) -> int: ...

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]: ...

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None: ...

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]: ...


class InMemoryMemoryPlaneStore:
    def __init__(self) -> None:
        self._records: dict[str, CanonicalMemoryRecord] = {}
        self._revision = 0
        self._lock = RLock()

    def stage_record(self, record: CanonicalMemoryRecord) -> None:
        self.apply_batch((record,), expected_revision=self.revision())

    def upsert_record(self, record: CanonicalMemoryRecord) -> None:
        self.apply_batch((record,), expected_revision=self.revision())

    def revision(self) -> int:
        with self._lock:
            return self._revision

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int,
    ) -> int:
        with self._lock:
            if expected_revision != self._revision:
                raise MemoryPlaneRevisionConflictError(
                    f"memory-plane revision changed: expected {expected_revision}, actual {self._revision}"
                )
            updated = dict(self._records)
            for record in records:
                updated[record.memory_id] = record
            self._records = updated
            self._revision += 1
            return self._revision

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._lock:
            return self._revision, tuple(self._records.values())

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        with self._lock:
            return self._records.get(memory_id)

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        domain_set = set(domains) if domains is not None else None
        with self._lock:
            return [
                item
                for item in self._records.values()
                if (status is None or item.status == status)
                and (domain_set is None or item.domain in domain_set)
                and (source_kind is None or item.source_kind == source_kind)
            ]


class JsonlMemoryPlaneStore:
    def __init__(self, path: str | Path) -> None:
        self._base_path = Path(path)
        self._records_path = self._base_path / "memory_records.jsonl"
        self._lock_path = self._base_path / "memory_records.lock"
        self._base_path.mkdir(parents=True, exist_ok=True)

    def stage_record(self, record: CanonicalMemoryRecord) -> None:
        self.apply_batch((record,), expected_revision=self.revision())

    def upsert_record(self, record: CanonicalMemoryRecord) -> None:
        self.apply_batch((record,), expected_revision=self.revision())

    def revision(self) -> int:
        batches = self._read_batches()
        return batches[-1].revision if batches else 0

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int,
    ) -> int:
        with self._lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                batches = self._read_batches()
                actual_revision = batches[-1].revision if batches else 0
                if expected_revision != actual_revision:
                    raise MemoryPlaneRevisionConflictError(
                        f"memory-plane revision changed: expected {expected_revision}, actual {actual_revision}"
                    )
                next_revision = actual_revision + 1
                payload = _PersistedBatch(revision=next_revision, records=records).model_dump_json()
                self._append_jsonl(payload)
                return next_revision
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_SH)
            try:
                batches = self._read_batches()
                latest_by_id: dict[str, CanonicalMemoryRecord] = {}
                for batch in batches:
                    for record in batch.records:
                        latest_by_id[record.memory_id] = record
                revision = batches[-1].revision if batches else 0
                return revision, tuple(latest_by_id.values())
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        return self._replay_latest().get(memory_id)

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        domain_set = set(domains) if domains is not None else None
        return [
            item
            for item in self._replay_latest().values()
            if (status is None or item.status == status)
            and (domain_set is None or item.domain in domain_set)
            and (source_kind is None or item.source_kind == source_kind)
        ]

    def _replay_latest(self) -> dict[str, CanonicalMemoryRecord]:
        latest_by_id: dict[str, CanonicalMemoryRecord] = {}
        for batch in self._read_batches():
            for record in batch.records:
                latest_by_id[record.memory_id] = record
        return latest_by_id

    def _read_batches(self) -> list[_PersistedBatch]:
        batches: list[_PersistedBatch] = []
        expected_revision = 1
        for line in self._iter_jsonl_lines():
            try:
                batch = _PersistedBatch.model_validate_json(line)
            except ValueError:
                break
            if batch.revision != expected_revision:
                raise ValueError(
                    f"non-contiguous memory-plane revision: expected {expected_revision}, got {batch.revision}"
                )
            batches.append(batch)
            expected_revision += 1
        return batches

    def _iter_jsonl_lines(self) -> list[str]:
        if not self._records_path.exists():
            return []
        with self._records_path.open("r", encoding="utf-8") as handle:
            return [line for line in handle if line.strip()]

    def _append_jsonl(self, payload: str) -> None:
        with self._records_path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
