"""Memory-plane storage contracts and in-memory/JSONL implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain


class MemoryPlaneStore(Protocol):
    def stage_record(self, record: CanonicalMemoryRecord) -> None: ...

    def upsert_record(self, record: CanonicalMemoryRecord) -> None: ...

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
        self._records: list[CanonicalMemoryRecord] = []

    def stage_record(self, record: CanonicalMemoryRecord) -> None:
        self._records.append(record)

    def upsert_record(self, record: CanonicalMemoryRecord) -> None:
        for idx, existing in enumerate(self._records):
            if existing.memory_id == record.memory_id:
                self._records[idx] = record
                return
        self._records.append(record)

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        for item in self._records:
            if item.memory_id == memory_id:
                return item
        return None

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
            for item in self._records
            if (status is None or item.status == status)
            and (domain_set is None or item.domain in domain_set)
            and (source_kind is None or item.source_kind == source_kind)
        ]


class JsonlMemoryPlaneStore:
    def __init__(self, path: str | Path) -> None:
        self._base_path = Path(path)
        self._records_path = self._base_path / "memory_records.jsonl"
        self._base_path.mkdir(parents=True, exist_ok=True)

    def stage_record(self, record: CanonicalMemoryRecord) -> None:
        self._append_jsonl(record.model_dump_json())

    def upsert_record(self, record: CanonicalMemoryRecord) -> None:
        self._append_jsonl(record.model_dump_json())

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
        for line in self._iter_jsonl_lines():
            record = CanonicalMemoryRecord.model_validate_json(line)
            latest_by_id[record.memory_id] = record
        return latest_by_id

    def _iter_jsonl_lines(self) -> list[str]:
        if not self._records_path.exists():
            return []
        with self._records_path.open("r", encoding="utf-8") as handle:
            return [line for line in handle if line.strip()]

    def _append_jsonl(self, payload: str) -> None:
        with self._records_path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
