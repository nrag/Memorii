"""Load the terminal fixture captured from the current Bootstrap V3 contract."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, _PersistedBatch

_FIXTURE_ROOT = Path(__file__).with_name("current_terminal")


def current_terminal_fixture_bytes(filename: str) -> bytes:
    return gzip.decompress((_FIXTURE_ROOT / f"{filename}.gz").read_bytes())


def rehydrated_current_terminal_plane(tmp_path: Path) -> MemoryPlaneService:
    records = tuple(
        CanonicalMemoryRecord.model_validate(item)
        for item in json.loads(current_terminal_fixture_bytes("memory-records.json").decode())
    )
    backend = JsonlMemoryPlaneStore(tmp_path / "current-terminal")
    backend._replace_batches([
        _PersistedBatch.create(revision=1, data_revision=0, records=records),
    ])
    return MemoryPlaneService(record_store=backend)
