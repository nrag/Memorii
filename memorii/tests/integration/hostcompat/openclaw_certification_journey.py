"""In-container OpenClaw certification journey: the real gateway end to end.

Runs inside memorii-openclaw-validation:pr from clean image state. Installs
the Memorii plugin into the extensions home (OpenClaw's ownership and
allowlist gates satisfied in-container as root), configures the stub model
provider and gateway token auth, boots the stub provider and the loopback
sidecar with an intake binding, seeds the provisioned task, drives real
gateway agent turns (fresh session, then same-session continuation), drains
the spool through memorii-consume --drain, and asserts committed runtime
state.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/opt/memorii-src/memorii")
sys.path.insert(0, "/opt/memorii-src/memorii/tests/integration/hostcompat")

from memorii.core.harness_state.consumer import LocalDurableSpool
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.sidecar import (
    HostIntakeBinding,
    RuntimeSidecar,
    serve_loopback,
)
from memorii.core.persistence.runtime_contracts import TaskRecord
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from stub_openai_provider import serve_stub_provider

PRODUCER = "host:principal:a"
GATEWAY_TOKEN = "cert-token-1"
root = Path("/tmp/memorii-journey")
administration = StorageAdministrationService(root / "installation")
administration.initialize()
task_id = "task:openclaw-session"

def seed(connection, repo) -> None:
    repo.apply_task(
        connection,
        TaskRecord(
            task_id=task_id,
            principal="principal:a",
            goal="OpenClaw certification journey",
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
            root_execution_node_id="exec:root",
        ),
    )

publish_runtime_change(administration, seed, operation_binding="openclaw_seed")

def grant_for(principal: str) -> RuntimeReadGrant:
    return RuntimeReadGrant(
        grant_id=f"openclaw:{principal}",
        principal=principal,
        allowed_task_ids=(task_id,),
        epoch=1,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

spool_directory = root / "spool"
repository = RuntimeStateRepository(administration.partition())
sidecar = RuntimeSidecar(
    repository=repository,
    credentials={"credential:one": "principal:a"},
    grant_factory=grant_for,
    intake_factory=lambda principal: HostIntakeBinding(
        spool=LocalDurableSpool(spool_directory),
        producer_binding=f"host:{principal}",
        allowlisted_producers=(f"host:{principal}",),
    ),
)

credential_path = Path("/run/memorii/openclaw-plugin.credential")
credential_path.parent.mkdir(parents=True, exist_ok=True)
os.chmod(credential_path.parent, 0o700)
credential_path.write_text("credential:one")
os.chmod(credential_path, 0o600)

# Plugin into the extensions home: root-owned (OpenClaw blocks foreign-uid
# plugin files), with openclaw resolvable for the plugin-sdk import.
extensions_home = Path("/root/.openclaw/extensions/memorii")
if extensions_home.exists():
    shutil.rmtree(extensions_home)
extensions_home.mkdir(parents=True)
for name in ("index.js", "openclaw.plugin.json", "package.json"):
    shutil.copy(f"/opt/memorii-openclaw/plugin/{name}", extensions_home / name)
subprocess.run(
    ["npm", "install", "--no-save", "--ignore-scripts", "openclaw@2026.9.7"],
    cwd=extensions_home, capture_output=True, text=True, timeout=900, check=False,
)

stub_url, stub_server = serve_stub_provider()
sidecar_url, sidecar_server = serve_loopback(sidecar, port=8762)
print("stub:", stub_url, "sidecar:", sidecar_url, flush=True)

def config_set(path: str, value: str) -> None:
    result = subprocess.run(
        ["openclaw", "config", "set", path, value],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if result.returncode != 0:
        print(f"config set {path} failed: {result.stdout} {result.stderr}")

config_set("models.providers.stub", json.dumps({
    "baseUrl": f"{stub_url}/v1",
    "apiKey": "stub-key",
    "api": "openai-completions",
    "authHeader": True,
    "models": [{"id": "stub-model", "name": "Stub Model", "api": "openai-completions"}],
}))
config_set("plugins.entries.memorii", json.dumps({"enabled": True, "config": {}}))
config_set("plugins.allow", json.dumps(["memorii"]))
config_set("gateway.mode", "local")
config_set("gateway.auth.mode", "token")
config_set("gateway.auth.token", GATEWAY_TOKEN)

subprocess.run(["pkill", "-f", "openclaw-gateway"], capture_output=True, check=False)
time.sleep(3)
gateway_log = open("/tmp/gateway-journey.log", "w")  # noqa: SIM115 - inherited by the gateway child
gateway = subprocess.Popen(
    ["openclaw", "gateway", "--bind", "loopback"],
    stdout=gateway_log, stderr=subprocess.STDOUT,
    start_new_session=True,
)


def wait_for_loopback_port(port: int, timeout_seconds: int = 180) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except OSError:
            if gateway.poll() is not None:
                return False
            time.sleep(2)
    return False

gateway_up = wait_for_loopback_port(18789)
print("gateway listening:", gateway_up, flush=True)
if not gateway_up:
    gateway_log.flush()
    print(Path("/tmp/gateway-journey.log").read_text()[-600:])

base_env = dict(
    os.environ,
    MEMORII_SIDECAR_URL=sidecar_url,
    MEMORII_CREDENTIAL_PATH=str(credential_path),
    MEMORII_TASK_ID=task_id,
    OPENCLAW_GATEWAY_TOKEN=GATEWAY_TOKEN,
)

def run_agent(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["openclaw", "agent", "--json", "--model", "stub/stub-model", *args],
        capture_output=True, text=True, env=base_env, timeout=240,
    )

def drain() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "/opt/memorii-venv/bin/memorii-consume",
            "--installation-root", str(root / "installation"),
            "--spool-directory", str(spool_directory),
            "--drain",
            "--allowlisted-producers", PRODUCER,
        ],
        capture_output=True, text=True, timeout=300,
    )

failures: list[str] = []
try:
    first = run_agent("--session-id", "cert-session", "-m", "record this certification turn")
    print("turn1 rc:", first.returncode, (first.stdout or first.stderr)[:200].replace("\n", " "))
    drain1 = drain()
    print("drain1 rc:", drain1.returncode, drain1.stdout.strip().replace("\n", " | ")[:400])

    # Restart the gateway between turns: the new process adopts the SAME
    # session, proving continuation survives a host restart.
    gateway.terminate()
    try:
        gateway.wait(timeout=30)
    except subprocess.TimeoutExpired:
        gateway.kill()
    gateway = subprocess.Popen(
        ["openclaw", "gateway", "--bind", "loopback"],
        stdout=gateway_log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print("gateway restarted:", wait_for_loopback_port(18789), flush=True)

    second = run_agent("--session-id", "cert-session", "-m", "continue the same session")
    print("turn2 rc:", second.returncode, (second.stdout or second.stderr)[:200].replace("\n", " "))
    drain2 = drain()
    print("drain2 rc:", drain2.returncode, drain2.stdout.strip().replace("\n", " | ")[:400])
finally:
    gateway.terminate()
    try:
        gateway.wait(timeout=30)
    except subprocess.TimeoutExpired:
        gateway.kill()
    stub_server.shutdown()
    stub_server.server_close()
    sidecar_server.shutdown()
    sidecar_server.server_close()

records = [json.loads(line) for line in (spool_directory / "intake.jsonl").read_text().splitlines()]
kinds = [record["operation_id"].split(":")[1] for record in records]
committed = [r for r in records if r["state"] == "committed"]
print("SPOOL:", kinds, "committed:", len(committed), "of", len(records))

status, payload = sidecar.handle_state_request(
    bearer_token="credential:one",
    origin=None,
    body=json.dumps({"protocol_version": 1, "task_id": task_id, "view": "summary"}).encode(),
)
envelope = json.loads(payload)
print("task status:", status, envelope.get("status"), "revision", envelope.get("revision"))

checks = {
    "both turns ran": first.returncode == 0 and second.returncode == 0,
    "user messages captured": kinds.count("observe") >= 2,
    "sessions resumed the provisioned task": kinds.count("resume") >= 2,
    "drain committed everything": len(committed) == len(records) and len(records) > 0,
    "runtime serves the task": status == 200,
}
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)

print("JOURNEY:", "PASS" if not failures else "FAIL", failures)
sys.exit(0 if not failures else 1)
