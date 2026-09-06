"""Run and reopen the public clarification-winner race in separate interpreters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_process_runner import (
    _persisted_progress_evidence,
)
from tests.unit.core.test_conflict_clarification import (
    _exercise_public_accepted_clarification_race,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("storage_root", type=Path)
    parser.add_argument("phase", choices=("first", "reopen"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.phase == "first":
        monkeypatch = pytest.MonkeyPatch()
        try:
            result = _exercise_public_accepted_clarification_race(
                args.storage_root, monkeypatch, "jsonl"
            )
        finally:
            monkeypatch.undo()
    else:
        service = MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(args.storage_root / "plane")
        )
        result = {
            "progress": _persisted_progress_evidence(
                service, operation_id="clarification-race-source"
            )
        }
    args.output.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
