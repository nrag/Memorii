"""Production-bound digest census through the real provider roots.

Methodology follows the frozen reference census: every
``memorii.core.semantic_ingestion.contracts.contract_digest`` call is one
full digest computation. The census records totals, unique identities,
repetition, and a callsite attribution sample for enabled and disabled
canonical-evidence modes over the same scenario vector.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
sys.path.insert(0, str(VECTORS))
sys.path.insert(0, str(ROOT / "memorii"))

import run_scenario_ingress as runner  # noqa: E402
from memorii.core.memory_plane import MemoryPlaneService  # noqa: E402
from memorii.core.provider.models import ProviderOperation  # noqa: E402
from memorii.core.semantic_ingestion import contracts  # noqa: E402
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (  # noqa: E402
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _v3_normalization_host_builder,
    _host_ingress as scenario_ingress,
)
from tests.unit.core.test_provider_service import (  # noqa: E402
    _build_production_scoped_provider_service,
)


def census(mode: str) -> dict[str, object]:
    from memorii.core.provider.service import ProviderMemoryService
    from tests.unit.core.semantic_ingestion.test_bootstrap_graph_coordinator_v3 import (
        _recovery_proposal,
    )

    now = datetime(2026, 3, 1, tzinfo=UTC)
    content = "Atlas owner is Bob."
    operation_id = f"digest-census-{mode}"
    builder, _calls = _v3_normalization_host_builder(proposal=_recovery_proposal())
    if mode == "enabled":
        service = _build_production_scoped_provider_service(
            source_normalization_host_bundle_builder=builder,
            now_provider=lambda: now,
        )
        arena = service._canonical_closure_dispatcher
    else:
        service = ProviderMemoryService._from_scenario_test_host(
            memory_plane=MemoryPlaneService(),
            now_provider=lambda: now,
            host_bootstrap_capability=_built_in_local_capability(
                normalization_builder=builder, scenario_test=True,
            ),
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )
    counts: Counter[str] = Counter()
    callsites: Counter[str] = Counter()
    original = contracts.contract_digest

    def counted(domain, value):
        digest = original(domain, value)
        counts[digest] += 1
        if sum(callsites.values()) < 200_000:
            frame = sys._getframe(1)
            site = f"{frame.f_code.co_filename.rsplit('/', 1)[-1]}:{frame.f_lineno}"
            callsites[site] += 1
        return digest

    contracts.contract_digest = counted
    started = time.perf_counter()
    try:
        result = service.sync_event(
            operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
            content=content,
            operation_id=operation_id,
            session_id="session:census",
            task_id="task:census",
            user_id="user:census",
            language="en",
            timestamp=now,
            authenticated_host_ingress=scenario_ingress().model_copy(
                update={"provider_identity": "scenario-test-host"}
            ),
        )
    finally:
        contracts.contract_digest = original
    elapsed = time.perf_counter() - started
    repeated = sum(count - 1 for count in counts.values())
    return {
        "mode": mode,
        "elapsed_seconds": round(elapsed, 3),
        "blocked_semantic": result.blocked_reasons.get("semantic_ingestion"),
        "total_digest_calls": sum(counts.values()),
        "unique_digest_outputs": len(counts),
        "repeated_digest_calls": repeated,
        "repeated_fraction": round(repeated / max(1, sum(counts.values())), 6),
        "top_callsites": callsites.most_common(12),
        "top_repetitions": [
            {"count": count, "digest": digest[:16]}
            for digest, count in counts.most_common(8)
        ],
    }


if __name__ == "__main__":
    modes = sys.argv[1:] or ["enabled", "disabled"]
    report = {"started": datetime.now(UTC).isoformat(), "censuses": []}
    for mode in modes:
        report["censuses"].append(census(mode))
    out = Path(__file__).with_name("production-digest-census-v1.json")
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["censuses"], indent=1, sort_keys=True))
