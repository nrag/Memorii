"""Transient authorized lexical index for one captured snapshot."""

from __future__ import annotations

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.bm25 import BM25Scorer


class ScopedContextIndex:
    def __init__(self, records: tuple[CanonicalMemoryRecord, ...], scorer: BM25Scorer | None = None) -> None:
        self._records = records
        self._scorer = scorer or BM25Scorer()

    def rank(self, query: str) -> list[CanonicalMemoryRecord]:
        scores = self._scorer.score(query=query, documents={record.memory_id: record.text for record in self._records})
        channel_order = {"semantic": 0, "episodic": 1}
        return sorted(
            (record for record in self._records if scores.get(record.memory_id, 0.0) > 0),
            key=lambda record: (channel_order[record.domain.value], -scores[record.memory_id], record.memory_id),
        )
