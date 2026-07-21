"""Memory-plane storage contracts and in-memory/JSONL implementations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import AbstractContextManager
from pathlib import Path
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain


class MemoryPlaneRevisionConflictError(RuntimeError):
    """Raised when a unit of work commits against a stale store revision."""


class MemoryPlaneCorruptionError(RuntimeError):
    """Raised when persisted memory cannot be replayed without data loss."""


class _PersistedBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int
    records: tuple[CanonicalMemoryRecord, ...]
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def create(cls, *, revision: int, records: tuple[CanonicalMemoryRecord, ...]) -> _PersistedBatch:
        return cls(revision=revision, records=records, checksum=_batch_checksum(revision, records))

    @model_validator(mode="after")
    def validate_checksum(self) -> _PersistedBatch:
        if self.checksum != _batch_checksum(self.revision, self.records):
            raise ValueError("memory-plane batch checksum mismatch")
        return self


class MemoryPlaneStore(Protocol):
    def write_records(self, records: tuple[CanonicalMemoryRecord, ...]) -> int: ...

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
        self.write_records((record,))

    def upsert_record(self, record: CanonicalMemoryRecord) -> None:
        self.write_records((record,))

    def write_records(self, records: tuple[CanonicalMemoryRecord, ...]) -> int:
        with self._lock:
            return self._apply_locked(records)

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
            return self._apply_locked(records)

    def _apply_locked(self, records: tuple[CanonicalMemoryRecord, ...]) -> int:
        updated = dict(self._records)
        for record in records:
            updated[record.memory_id] = _clone_record(record)
        self._records = updated
        self._revision += 1
        return self._revision

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._lock:
            return self._revision, tuple(_clone_record(record) for record in self._records.values())

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        with self._lock:
            record = self._records.get(memory_id)
            return _clone_record(record) if record is not None else None

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
                _clone_record(item)
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
        self.write_records((record,))

    def upsert_record(self, record: CanonicalMemoryRecord) -> None:
        self.write_records((record,))

    def write_records(self, records: tuple[CanonicalMemoryRecord, ...]) -> int:
        with self._locked(exclusive=True):
            batches = self._read_batches_unlocked()
            next_revision = batches[-1].revision + 1 if batches else 1
            self._replace_batches(
                [*batches, _PersistedBatch.create(revision=next_revision, records=records)]
            )
            return next_revision

    def revision(self) -> int:
        with self._locked(exclusive=False):
            batches = self._read_batches_unlocked()
            return batches[-1].revision if batches else 0

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int,
    ) -> int:
        with self._locked(exclusive=True):
            batches = self._read_batches_unlocked()
            actual_revision = batches[-1].revision if batches else 0
            if expected_revision != actual_revision:
                raise MemoryPlaneRevisionConflictError(
                    f"memory-plane revision changed: expected {expected_revision}, actual {actual_revision}"
                )
            next_revision = actual_revision + 1
            self._replace_batches(
                [*batches, _PersistedBatch.create(revision=next_revision, records=records)]
            )
            return next_revision

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._locked(exclusive=False):
            batches = self._read_batches_unlocked()
            latest_by_id: dict[str, CanonicalMemoryRecord] = {}
            for batch in batches:
                for record in batch.records:
                    latest_by_id[record.memory_id] = record
            revision = batches[-1].revision if batches else 0
            return revision, tuple(_clone_record(record) for record in latest_by_id.values())

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        _, records = self.read_snapshot()
        return next((record for record in records if record.memory_id == memory_id), None)

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        domain_set = set(domains) if domains is not None else None
        _, records = self.read_snapshot()
        return [
            item
            for item in records
            if (status is None or item.status == status)
            and (domain_set is None or item.domain in domain_set)
            and (source_kind is None or item.source_kind == source_kind)
        ]

    def _read_batches_unlocked(self) -> list[_PersistedBatch]:
        batches: list[_PersistedBatch] = []
        expected_revision = 1
        for line_number, line in enumerate(self._iter_jsonl_lines_unlocked(), start=1):
            try:
                batch = _PersistedBatch.model_validate_json(line)
            except ValueError as exc:
                raise MemoryPlaneCorruptionError(f"invalid memory-plane batch at line {line_number}: {exc}") from exc
            if batch.revision != expected_revision:
                raise MemoryPlaneCorruptionError(
                    f"non-contiguous memory-plane revision: expected {expected_revision}, got {batch.revision}"
                )
            batches.append(batch)
            expected_revision += 1
        return batches

    def _iter_jsonl_lines_unlocked(self) -> list[str]:
        if not self._records_path.exists():
            return []
        try:
            content = self._records_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise MemoryPlaneCorruptionError(f"cannot read memory-plane log: {exc}") from exc
        if content and not content.endswith("\n"):
            raise MemoryPlaneCorruptionError("memory-plane log ends with an incomplete batch")
        return [line for line in content.splitlines() if line.strip()]

    def _replace_batches(self, batches: list[_PersistedBatch]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._base_path,
            prefix=f".{self._records_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for batch in batches:
                    handle.write(batch.model_dump_json())
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._records_path)
            _fsync_directory(self._base_path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    def _locked(self, *, exclusive: bool) -> AbstractContextManager[None]:
        return locked_file(self._lock_path, exclusive=exclusive)


def _clone_record(record: CanonicalMemoryRecord) -> CanonicalMemoryRecord:
    return record.model_copy(deep=True)


def _batch_checksum(revision: int, records: tuple[CanonicalMemoryRecord, ...]) -> str:
    payload = json.dumps(
        {
            "revision": revision,
            "records": [record.model_dump(mode="json") for record in records],
        },
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
