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

import run_scenario_ingress as runner
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion import contracts
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_scenario_test_provider_service,
)

world = json.loads((VECTORS / "scenario-first-v1.json").read_text(encoding="utf-8"))
scenario = runner.validate(world)[0]
observation = runner.render(scenario)[0]
rendered = observation.text.encode("utf-8")
operation_id = runner._opaque_event_id(ordinal=0, source_bytes=rendered)
service = build_scenario_test_provider_service(
    memory_plane=MemoryPlaneService(),
    now_provider=lambda: datetime(2026, 7, 30, tzinfo=UTC),
)

original = contracts.contract_digest
counts: Counter[str] = Counter()

def counted_contract_digest(*args, **kwargs):
    digest = original(*args, **kwargs)
    counts[digest] += 1
    return digest

contracts.contract_digest = counted_contract_digest
started = time.perf_counter()
try:
    service.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content=observation.text,
        operation_id=operation_id,
        session_id=runner._PUBLIC_SCOPE[1],
        task_id=runner._PUBLIC_SCOPE[2],
        user_id=runner._PUBLIC_SCOPE[0],
        language="en",
        speaker_id="scenario-speaker",
        timestamp=observation.timestamp,
        authenticated_host_ingress=runner._host_ingress(ordinal=0),
    )
finally:
    contracts.contract_digest = original
elapsed = time.perf_counter() - started
repeated = sorted((count, digest) for digest, count in counts.items() if count > 1)
print(json.dumps({
    "elapsed_seconds": elapsed,
    "total_digest_calls": sum(counts.values()),
    "unique_digest_outputs": len(counts),
    "redundant_digest_calls": sum(count - 1 for count in counts.values()),
    "repeated_identity_count": len(repeated),
    "maximum_repetition": repeated[-1][0] if repeated else 1,
    "top_repetitions": [
        {"count": count, "digest": digest}
        for count, digest in reversed(repeated[-12:])
    ],
}, sort_keys=True))
