"""Read-only inspection of a Hermes development profile's Memorii graph."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService

from memorii_hermes_development import _load_development_factory


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("summary", "graph"),
        nargs="?",
        default="summary",
        help="show operational counts or export the complete canonical graph",
    )
    parser.add_argument(
        "--hermes-home",
        type=Path,
        default=Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")),
        help="Hermes profile root (defaults to HERMES_HOME or ~/.hermes)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON to this path instead of standard output",
    )
    return parser


def _load_snapshot(hermes_home: Path):
    memory_plane_root = hermes_home.expanduser().resolve() / "memorii" / "memory-plane"
    records_path = memory_plane_root / "memory_records.jsonl"
    if not records_path.is_file():
        raise FileNotFoundError(
            f"Memorii data was not found at {records_path}; check --hermes-home and run a Hermes turn first"
        )

    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(memory_plane_root))
    build_service, _ = _load_development_factory(
        memory_plane_root.parent / ".development-authority"
    )
    service = build_service(plane)
    runtime = service._composed_semantic_runtime
    if runtime is None or runtime.atomic_store is None:
        raise RuntimeError("the development provider has no semantic graph runtime")
    write_revision, records = plane.read_write_snapshot()
    authority = runtime.atomic_store.read_detached_observation_authority(
        write_revision=write_revision,
        records=records,
        snapshot_created_at=datetime.now(UTC),
    )
    return memory_plane_root, authority


def _summary(memory_plane_root: Path, authority: Any) -> dict[str, object]:
    graph = authority.graph
    source_kinds = Counter(record.source_kind for record in authority.records)
    graph_counts = {kind: count for kind, count in graph.exact_record_counts_by_kind if count}
    return {
        "storage_root": str(memory_plane_root),
        "write_revision": authority.write_revision,
        "memory_plane_record_count": len(authority.records),
        "captured_source_count": source_kinds["semantic_ingestion_source"],
        "observation_ledger_entry_count": source_kinds[
            "semantic_ingestion_observation_ledger_entry"
        ],
        "retrieval_visible_record_count": sum(
            record.visibility.value == "runtime_context" for record in authority.records
        ),
        "graph_revision": graph.graph_revision,
        "graph_snapshot_digest": graph.snapshot_digest,
        "graph_record_count": len(graph.records),
        "graph_record_counts_by_kind": graph_counts,
    }


def _render(command: str, memory_plane_root: Path, authority: Any) -> dict[str, object]:
    if command == "summary":
        return _summary(memory_plane_root, authority)
    return authority.graph.model_dump(mode="json")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    memory_plane_root, authority = _load_snapshot(args.hermes_home)
    rendered = json.dumps(
        _render(args.command, memory_plane_root, authority),
        indent=2,
        sort_keys=True,
    ) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.expanduser().resolve().write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"inspection failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
