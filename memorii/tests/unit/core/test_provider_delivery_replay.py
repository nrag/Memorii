from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

from memorii.core.memory_evolution.ingestion_contracts import derive_composite_child_delivery_id
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore

_PROCESS_SCRIPT = """
import json
import sys
from pathlib import Path

from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.memory_evolution.ingestion_contracts import derive_composite_child_delivery_id
from tests.support.memory_evolution_provider_harness import (
    MemoryEvolutionProviderHarness as ProviderMemoryService,
)
from memorii.integrations.hermes_provider import HermesMemoryProvider

store_path = Path(sys.argv[1])
action = sys.argv[2]
plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
service = ProviderMemoryService(memory_plane=plane)
provider = HermesMemoryProvider(service)

if action == "turn":
    result = provider.sync_turn(
        "Atlas migration owner is Alice.",
        "Acknowledged.",
        operation_id="delivery:durable-turn",
        task_id="task:atlas",
    )
elif action == "user_only":
    result = service._sync_composite_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas migration owner is Alice.",
        role="user",
        composite_operation_id=derive_composite_child_delivery_id("delivery:durable-turn", "user"),
        task_id="task:atlas",
        session_id=None,
        user_id=None,
        authenticated_host_ingress=None,
    )
else:
    raise AssertionError(action)

print(json.dumps({
    "transcript_ids": result.transcript_ids,
    "operation_ids": [outcome.operation_id for outcome in result.evolution_outcomes],
}))
"""


def _run_provider_process(store_path: Path, action: str) -> dict[str, list[str]]:
    completed = subprocess.run(
        [sys.executable, "-c", _PROCESS_SCRIPT, str(store_path), action],
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, list[str]], json.loads(completed.stdout))


def test_delivery_replay_is_idempotent_after_process_restart(tmp_path: Path) -> None:
    store_path = tmp_path / "memory-plane"

    first = _run_provider_process(store_path, "turn")
    replay = _run_provider_process(store_path, "turn")

    reopened = JsonlMemoryPlaneStore(store_path)
    transcript_records = [record for record in reopened.list_records() if record.is_raw_event]
    assert replay == first
    assert len(transcript_records) == 2
    assert {record.memory_id for record in transcript_records} == set(first["transcript_ids"])


def test_partial_turn_recovers_after_process_restart(tmp_path: Path) -> None:
    store_path = tmp_path / "memory-plane"

    first = _run_provider_process(store_path, "user_only")
    recovered = _run_provider_process(store_path, "turn")

    reopened = JsonlMemoryPlaneStore(store_path)
    transcript_records = [record for record in reopened.list_records() if record.is_raw_event]
    assert first["operation_ids"] == [
        derive_composite_child_delivery_id("delivery:durable-turn", "user")
    ]
    assert recovered["operation_ids"] == [
        derive_composite_child_delivery_id("delivery:durable-turn", "user"),
        derive_composite_child_delivery_id("delivery:durable-turn", "assistant"),
    ]
    assert len(transcript_records) == 2
