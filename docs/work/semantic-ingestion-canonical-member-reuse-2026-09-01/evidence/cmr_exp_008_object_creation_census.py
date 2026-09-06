"""Object-creation and live-set census for one enabled delivery.

Counts, for the same deterministic corpus delivery as the wall-clock
harness:

- GC activity: collections and wall time per generation (gc.callbacks),
  plus generation counters before/after;
- live tracked objects by type inside the arena at close (before the
  operation memos purge) and after close, to separate the operation's
  working set from the memo contribution;
- explicit ``model_validate`` and ``model_dump`` calls by class (pydantic's
  C-level nested construction is invisible to Python patches; these count
  the explicit re-materialization boundaries);
- decode calls with the container-node count of each freshly built typed
  tree, split unique/repeat raw bytes;
- lowering visits (fresh vs memo-served);
- tracemalloc top allocation sites and peak traced memory.

Counting only; no production behavior is changed.  Output is one JSON
object on stdout.
"""

from __future__ import annotations

import gc
import json
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
sys.path.insert(0, str(ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"))

import pydantic
from memorii.core.memory_plane.service import MemoryPlaneService
import memorii.core.memory_evolution.ingestion_contracts as ic
import memorii.core.memory_evolution.record_projection as rp
import memorii.core.semantic_ingestion.contracts as C
from memorii.core.provider.service import CanonicalEvidenceArena
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_coordinator_v3 import (
    _delivery,
    _production_recovery_service,
)

_EVIDENCE = ROOT / "docs/work/semantic-ingestion-canonical-member-reuse-2026-09-01/evidence"

_CONTAINER_TYPES = (dict, list, tuple, set, frozenset)


def _count_nodes(value: object, seen: set[int], depth: int = 0) -> int:
    if depth > 60 or id(value) in seen:
        return 0
    if isinstance(value, pydantic.BaseModel):
        seen.add(id(value))
        return 1 + sum(
            _count_nodes(item, seen, depth + 1) for item in value.__dict__.values()
        )
    if isinstance(value, _CONTAINER_TYPES):
        seen.add(id(value))
        if isinstance(value, dict):
            items = list(value.keys()) + list(value.values())
        else:
            items = list(value)
        return 1 + sum(_count_nodes(item, seen, depth + 1) for item in items)
    return 0


def _live_type_census() -> Counter:
    census: Counter[str] = Counter()
    for obj in gc.get_objects():
        census[type(obj).__name__] += 1
    return census


def main() -> None:
    gc.collect()
    stats_before = [dict(entry) for entry in gc.get_stats()]

    gc_times: Counter[str] = Counter()
    gc_collections: Counter[str] = Counter()
    pending: dict[int, float] = {}

    def gc_callback(phase: str, info: dict) -> None:
        if phase == "start":
            pending[info["generation"]] = time.perf_counter()
        else:
            started = pending.pop(info["generation"], None)
            if started is not None:
                gc_times[f"gen{info['generation']}"] += time.perf_counter() - started
                gc_collections[f"gen{info['generation']}"] += 1

    gc.callbacks.append(gc_callback)

    validate_calls: Counter[str] = Counter()
    original_validate = pydantic.BaseModel.model_validate.__func__

    def counting_validate(cls, *args, **kwargs):  # type: ignore[no-untyped-def]
        validate_calls[cls.__name__] += 1
        return original_validate(cls, *args, **kwargs)

    pydantic.BaseModel.model_validate = classmethod(counting_validate)

    dump_calls: Counter[str] = Counter()
    original_dump = pydantic.BaseModel.model_dump

    def counting_dump(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        dump_calls[type(self).__name__] += 1
        return original_dump(self, *args, **kwargs)

    pydantic.BaseModel.model_dump = counting_dump

    decode_stats = {"calls": 0, "nodes": 0, "unique_raws": set(), "nodes_unique": 0}
    original_decode = ic.decode_typed_value

    def counting_decode(raw: bytes, **kwargs):  # type: ignore[no-untyped-def]
        decode_stats["calls"] += 1
        result = original_decode(raw, **kwargs)
        nodes = _count_nodes(result, set())
        decode_stats["nodes"] += nodes
        if raw not in decode_stats["unique_raws"]:
            decode_stats["unique_raws"].add(raw)
            decode_stats["nodes_unique"] += nodes
        return result

    for module in (ic, C, rp):
        if hasattr(module, "decode_typed_value"):
            module.decode_typed_value = counting_decode

    lower_stats = {"calls": 0, "fresh": 0, "memo_hits": 0}
    original_lower = C.canonical_contract_value

    def counting_lower(value: object) -> object:
        lower_stats["calls"] += 1
        if isinstance(value, pydantic.BaseModel):
            from memorii.core.semantic_ingestion.canonical_evidence_arena import (
                current_digest_verification_scope,
            )

            scope = current_digest_verification_scope()
            if scope is not None and scope.lookup_lowered_value(value) is not None:
                lower_stats["memo_hits"] += 1
            else:
                lower_stats["fresh"] += 1
        return original_lower(value)

    C.canonical_contract_value = counting_lower

    live_inside: Counter[str] | None = None
    memo_sizes: dict[str, int] = {}
    original_exit = CanonicalEvidenceArena.__exit__

    def census_exit(self, *args):  # type: ignore[no-untyped-def]
        nonlocal live_inside
        if live_inside is None:
            live_inside = _live_type_census()
            emission = getattr(self, "_emission_scope", None)
            if emission is not None:
                memo_sizes["emitted_entries"] = emission.emitted_entries
                memo_sizes["emitted_retained_bytes"] = emission.retained_bytes
                memo_sizes["string_entries"] = emission.string_entries
            digest_scope = getattr(self, "_digest_verification_scope", None)
            if digest_scope is not None:
                memo_sizes["lowered_entries"] = len(digest_scope._lowered_values)
                memo_sizes["roundtrip_entries"] = len(digest_scope._roundtrips)
                memo_sizes["encoded_results"] = len(digest_scope._encoded_results)
                memo_sizes["encoded_bytes"] = len(digest_scope._encoded_bytes)
                memo_sizes["digest_verified"] = len(digest_scope._verified)
        return original_exit(self, *args)

    CanonicalEvidenceArena.__exit__ = census_exit

    tracemalloc.start(25)
    try:
        service = _production_recovery_service(plane=MemoryPlaneService())
        started = time.perf_counter()
        _delivery(service, "object-creation-census")
        elapsed = time.perf_counter() - started
        peak_traced = tracemalloc.get_traced_memory()[1]
        snapshot = tracemalloc.take_snapshot()
    finally:
        tracemalloc.stop()
        CanonicalEvidenceArena.__exit__ = original_exit
        C.canonical_contract_value = original_lower
        for module in (ic, C, rp):
            if hasattr(module, "decode_typed_value"):
                module.decode_typed_value = original_decode
        pydantic.BaseModel.model_dump = original_dump
        pydantic.BaseModel.model_validate = classmethod(original_validate)
        gc.callbacks.remove(gc_callback)

    gc.collect()
    stats_after = [dict(entry) for entry in gc.get_stats()]
    live_after = _live_type_census()

    top_sites = [
        {
            "site": f"{Path(stat.traceback[0].filename).name}:{stat.traceback[0].lineno}"
            if stat.traceback
            else "<unknown>",
            "blocks": stat.count,
            "bytes": stat.size,
        }
        for stat in sorted(
            snapshot.statistics("lineno"), key=lambda item: -item.size
        )[:20]
    ]

    result = {
        "elapsed_seconds": elapsed,
        "tracemalloc_peak_bytes": peak_traced,
        "tracemalloc_top_sites": top_sites,
        "gc": {
            "collections": dict(gc_collections),
            "time_seconds": {key: round(value, 3) for key, value in gc_times.items()},
            "collections_before": [entry["collections"] for entry in stats_before],
            "collections_after": [entry["collections"] for entry in stats_after],
        },
        "live_inside_arena": dict(live_inside.most_common(25)) if live_inside else {},
        "live_inside_total": sum(live_inside.values()) if live_inside else 0,
        "live_after_close": dict(live_after.most_common(25)),
        "live_after_total": sum(live_after.values()),
        "memo_sizes": memo_sizes,
        "model_validate_calls": dict(validate_calls.most_common(20)),
        "model_validate_total": sum(validate_calls.values()),
        "model_dump_calls": dict(dump_calls.most_common(20)),
        "model_dump_total": sum(dump_calls.values()),
        "decode": {
            "calls": decode_stats["calls"],
            "unique_raws": len(decode_stats["unique_raws"]),
            "tree_nodes_total": decode_stats["nodes"],
            "tree_nodes_unique": decode_stats["nodes_unique"],
        },
        "lowering": lower_stats,
    }
    (_EVIDENCE / "cmr-exp-008-object-creation-census-v1.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
