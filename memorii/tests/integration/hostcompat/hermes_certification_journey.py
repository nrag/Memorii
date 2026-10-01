"""In-container Hermes certification journey: the real CLI end to end.

Runs inside the pinned Hermes memorii image (bash entrypoint). Boots the
stub provider, writes a minimal current-form Hermes config (custom
OpenAI-compatible provider + the Memorii memory provider), drives two real
``hermes -z`` one-shot turns (the second continuing the same session), and
asserts the in-process write path: the Memorii plane under the profile's
memorii root captures authentic transcript records and the continuation
turn reopens the same root without a second installation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/memorii-src/memorii")
sys.path.insert(0, "/opt/memorii-src/memorii/tests/integration/hostcompat")

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
# so the written config is the one the CLI reads.
environment = dict(os.environ, HOME="/root", HERMES_HOME=str(HERMES_HOME))

def run_hermes(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/opt/hermes/.venv/bin/hermes", "-z", *args],
        capture_output=True, text=True, env=environment, timeout=300,
    )

failures: list[str] = []
# NOTE (open): -z one-shot turns reach the stub (model replies observed)
# but exit 2 after the replies and do not yet drive the memory provider;
# the activation path (memory.provider: memorii, entry-point load verified
# manually) and the turn shape that syncs memory remain to be pinned —
# candidates: interactive `hermes chat` under a pty, or the ACP adapter.
first = run_hermes("remember this certification turn")
print("turn1 rc:", first.returncode, (first.stdout or first.stderr)[:240].replace("\n", " "))

second = run_hermes("--continue", "continue the same session")
print("turn2 rc:", second.returncode, (second.stdout or second.stderr)[:240].replace("\n", " "))

stub_server.shutdown()
stub_server.server_close()

print("memorii root exists:", MEMORII_ROOT.exists())
for path in sorted(MEMORII_ROOT.rglob("*"))[:12]:
    if path.is_file():
        print("  ", path.relative_to(MEMORII_ROOT))

records_files = [p for p in MEMORII_ROOT.rglob("memory_records.jsonl")]
plane_records = 0
for path in records_files:
    plane_records += len([line for line in path.read_text().splitlines() if line.strip()])
print("plane records:", plane_records, "across", len(records_files), "file(s)")

checks = {
    "both turns ran": first.returncode == 0 and second.returncode == 0,
    "memorii plane captured records": plane_records > 0,
    "single plane root (continuation reopened)": len(records_files) == 1,
}
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)

print("JOURNEY:", "PASS" if not failures else "FAIL", failures)
sys.exit(0 if not failures else 1)
