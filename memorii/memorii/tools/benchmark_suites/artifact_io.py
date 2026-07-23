from __future__ import annotations

from pathlib import Path

from memorii.core.benchmark.artifact_validation import write_jsonl_atomic


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    write_jsonl_atomic(path, rows)
