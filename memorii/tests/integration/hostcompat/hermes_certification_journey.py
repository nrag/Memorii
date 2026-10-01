"""In-container Hermes certification journey: the real ACP agent end to end.

Runs inside the pinned Hermes memorii image. Boots the stub provider, writes
a minimal current-form Hermes config (custom OpenAI-compatible provider +
the Memorii memory provider), then drives the REAL ``hermes-acp`` stdio
server through the Agent Client Protocol: initialize, session/new, a first
turn, a server RESTART, session/load of the same session, and a second
turn. Asserts the in-process write path: the Memorii plane under the
profile's memorii root captures authentic transcript records and the
continuation turn reopens the same root.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/memorii-src/memorii")
sys.path.insert(0, "/opt/memorii-src/memorii/tests/integration/hostcompat")

from hermes_acp_client import AcpClient
from stub_openai_provider import serve_stub_provider

HERMES_HOME = Path("/root/.hermes")
MEMORII_ROOT = HERMES_HOME / "memorii"

HERMES_HOME.mkdir(parents=True, exist_ok=True)
(HERMES_HOME / "config.yaml").write_text(
    "\n".join(
        [
            "_config_version: 12",
            "model:",
            '  default: "stub-model"',
            '  provider: "custom"',
            '  base_url: "http://127.0.0.1:9911/v1"',
            '  api_key: "stub-key"',
            "memory:",
            "  memory_enabled: true",
            '  provider: "memorii"',
            "",
        ]
    )
)

stub_url, stub_server = serve_stub_provider(port=9911)
print("stub:", stub_url, flush=True)

# The image bakes HERMES_HOME=/opt/data; the journey's profile overrides it
# so the written config is the one the agent reads.
environment = dict(os.environ, HOME="/root", HERMES_HOME=str(HERMES_HOME))
ACP_COMMAND = ["/opt/hermes/.venv/bin/hermes-acp"]
WORKDIR = "/tmp/hermes-journey-work"
os.makedirs(WORKDIR, exist_ok=True)

def plane_record_count() -> int:
    if not MEMORII_ROOT.exists():
        return 0
    total = 0
    for path in MEMORII_ROOT.rglob("memory_records.jsonl"):
        total += len([line for line in path.read_text().splitlines() if line.strip()])
    return total

failures: list[str] = []

client = AcpClient(ACP_COMMAND, environment)
hello = client.initialize()
print("initialized:", hello.get("agentInfo", {}).get("name"), flush=True)
session_id = client.new_session(WORKDIR)
print("session:", session_id, flush=True)
turn1 = client.prompt(session_id, "remember this certification turn")
print("turn1 stop:", turn1.get("stopReason"), flush=True)
records_after_turn1 = plane_record_count()
print("plane records after turn1:", records_after_turn1, flush=True)

# Server restart: a brand-new agent process must continue the same session.
client.stop()
client = AcpClient(ACP_COMMAND, environment)
client.initialize()
loaded = client.load_session(session_id, WORKDIR)
print("loaded session:", loaded.get("sessionId") == session_id, flush=True)
turn2 = client.prompt(session_id, "continue the same session")
print("turn2 stop:", turn2.get("stopReason"), flush=True)
client.stop()

stub_server.shutdown()
stub_server.server_close()

records_after_turn2 = plane_record_count()
print("plane records after turn2:", records_after_turn2)
plane_files = list(MEMORII_ROOT.rglob("memory_records.jsonl")) if MEMORII_ROOT.exists() else []
print("plane files:", [str(p.relative_to(MEMORII_ROOT)) for p in plane_files][:4])

checks = {
    "turn1 completed": turn1.get("stopReason") == "end_turn",
    "memorii plane captured records": records_after_turn1 > 0,
    "restart continuation reopened the same root": records_after_turn2 > records_after_turn1
    and len(plane_files) == 1,
}
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)

print("JOURNEY:", "PASS" if not failures else "FAIL", failures)
sys.exit(0 if not failures else 1)
