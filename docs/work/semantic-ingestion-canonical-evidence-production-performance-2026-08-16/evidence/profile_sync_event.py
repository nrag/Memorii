from __future__ import annotations

import cProfile
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
sys.path.insert(0, str(VECTORS))

import run_scenario_ingress as runner
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_scenario_test_provider_service,
)

world = json.loads(
    (VECTORS / "scenario-first-v1.json").read_text(encoding="utf-8")
)
scenario = runner.validate(world)[0]
observation = runner.render(scenario)[0]
rendered = observation.text.encode("utf-8")
operation_id = runner._opaque_event_id(ordinal=0, source_bytes=rendered)
service = build_scenario_test_provider_service(
    memory_plane=MemoryPlaneService(),
    now_provider=lambda: datetime(2026, 7, 30, tzinfo=UTC),
)
profile = cProfile.Profile()
started = time.perf_counter()
profile.enable()
result = service.sync_event(
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
profile.disable()
elapsed = time.perf_counter() - started
profile.dump_stats("/private/tmp/memorii-sync-event-only.prof")
print(json.dumps({
    "elapsed_seconds": elapsed,
    "operation_id": operation_id,
    "result_type": type(result).__name__,
    "record_count": len(service._memory_plane.list_records()),
}, sort_keys=True))
