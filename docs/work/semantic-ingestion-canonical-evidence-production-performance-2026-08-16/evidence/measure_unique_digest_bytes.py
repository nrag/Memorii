from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
sys.path.insert(0, str(VECTORS))

import run_scenario_ingress as runner
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
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
sizes: dict[str, int] = {}

def measured_contract_digest(domain: bytes, value: object) -> str:
    digest = original(domain, value)
    counts[digest] += 1
    if digest not in sizes:
        canonical = encode_typed_value(contracts.canonical_contract_value(value))
        sizes[digest] = len(domain) + 1 + len(canonical)
    return digest

contracts.contract_digest = measured_contract_digest
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
ordered = sorted(sizes.values())
print(json.dumps({
    "unique_identity_count": len(ordered),
    "unique_canonical_bytes": sum(ordered),
    "maximum_entry_bytes": max(ordered),
    "median_entry_bytes": ordered[(len(ordered) - 1) // 2],
    "p95_entry_bytes": ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)],
    "total_digest_calls": sum(counts.values()),
}, sort_keys=True))
