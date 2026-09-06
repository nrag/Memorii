"""cProfile attribution for one enabled delivery.

Runs the same deterministic corpus delivery as the wall-clock harness with
cProfile enabled only around the delivery, saves the raw pstats dump, and
prints a focused JSON summary: top exclusive/cumulative functions plus
time/call-count rollups for the canonical-encode pipeline, pydantic
validation, and digest work.
"""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
sys.path.insert(0, str(VECTORS))

from memorii.core.memory_plane.service import MemoryPlaneService
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_coordinator_v3 import (
    _delivery,
    _production_recovery_service,
)

EVIDENCE = ROOT / "docs/work/semantic-ingestion-canonical-member-reuse-2026-09-01/evidence"

ROLLUPS = {
    "canonical_json_emission": ("_json", "_json_string", "_scalar"),
    "normalization": ("_normalized_typed_json", "canonical_contract_value"),
    "span_walk": ("walk",),
    "with_spans_encode": ("encode_typed_value_with_spans",),
    "plain_encode": ("encode_typed_value",),
    "codec_revalidate": ("_build_validated_semantic_contract_result",),
    "contract_digest": ("contract_digest",),
    "content_digest_validator": ("validate_content_digest",),
    "member_evidence_build": ("_member_evidence",),
}


def main() -> None:
    service = _production_recovery_service(plane=MemoryPlaneService())
    assert service._canonical_evidence_enabled is True
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    result = _delivery(service, "delivery-profile")
    profiler.disable()
    elapsed = time.perf_counter() - started

    dump_path = EVIDENCE / "cmr-exp-007-profile-current-v1.pstats"
    profiler.dump_stats(str(dump_path))

    stats = pstats.Stats(profiler)
    rows: dict[str, dict[str, object]] = {}
    total_tt: dict[str, float] = {}
    total_cc: dict[str, int] = {}
    for (filename, _lineno, name), (_cc, _nc, tt, _ct, _callers) in stats.stats.items():
        total_tt[name] = total_tt.get(name, 0.0) + tt
        total_cc[name] = total_cc.get(name, 0) + _nc

    top_exclusive = sorted(total_tt.items(), key=lambda item: -item[1])[:30]
    summary = {
        "elapsed_seconds": elapsed,
        "total_functions": len(total_tt),
        "top_exclusive_functions_seconds": [
            {"function": name, "exclusive_seconds": round(value, 3), "calls": total_cc[name]}
            for name, value in top_exclusive
        ],
        "rollup_totals_seconds": {
            label: {
                "functions": {
                    name: {
                        "exclusive_seconds": round(total_tt.get(name, 0.0), 3),
                        "calls": total_cc.get(name, 0),
                    }
                    for name in names
                }
            }
            for label, names in ROLLUPS.items()
        },
    }
    out = io.StringIO()
    stats_stream = pstats.Stats(profiler, stream=out)
    stats_stream.sort_stats("cumulative").print_stats(45)
    stats_stream.sort_stats("tottime").print_stats(45)
    stats_stream.print_callers("validate_python")
    (EVIDENCE / "cmr-exp-007-profile-current-v1.txt").write_text(out.getvalue(), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
