"""In-container Pi certification journey: the real pi CLI end to end.

Runs inside memorii-pi-validation:pr with the current source. Boots the
stub provider and the loopback sidecar with an intake binding, then drives
the real pi CLI (pinned 0.99.2) through three sessions — a first turn, a
restart resume of the same session, and a denied fork — drains the spool
through memorii-consume --drain, and asserts committed runtime state.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
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
root = Path("/tmp/memorii-journey")
administration = StorageAdministrationService(root / "installation")
administration.initialize()
repository = RuntimeStateRepository(administration.partition())
task_id = "task:pi-session"

# Operator provisioning: the task exists before the host session starts;
# hosts continue provisioned tasks, they never mint their own.
def seed(connection, repo) -> None:
    repo.apply_task(
        connection,
        TaskRecord(
            task_id=task_id,
            principal="principal:a",
            goal="Pi certification journey",
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
            root_execution_node_id="exec:root",
        ),
    )

publish_runtime_change(administration, seed, operation_binding="pi_seed")

def grant_for(principal: str) -> RuntimeReadGrant:
    return RuntimeReadGrant(
        grant_id=f"pi:{principal}",
        principal=principal,
        allowed_task_ids=(task_id,),
        epoch=1,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

spool_directory = root / "spool"
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

credential_path = Path("/run/memorii/pi-extension.credential")
credential_path.parent.mkdir(parents=True, exist_ok=True)
os.chmod(credential_path.parent, 0o700)
credential_path.write_text("credential:one")
os.chmod(credential_path, 0o600)

stub_url, stub_server = serve_stub_provider()
sidecar_url, sidecar_server = serve_loopback(sidecar, port=8762)
print("stub:", stub_url, "sidecar:", sidecar_url, flush=True)

agent_dir = Path("/root/.pi/agent")
agent_dir.mkdir(parents=True, exist_ok=True)
(agent_dir / "models.json").write_text(json.dumps({
    "providers": {
        "stub": {
            "name": "Stub",
            "baseUrl": f"{stub_url}/v1",
            "apiKey": "stub-key",
            "api": "openai",
            "authHeader": True,
            "models": [{
                "id": "stub-model",
                "name": "Stub Model",
                "contextWindow": 128000,
                "maxTokens": 4096,
            }],
        }
    }
}))

session_dir = root / "pi-sessions"
session_dir.mkdir(parents=True)

base_env = dict(
    os.environ,
    MEMORII_SIDECAR_URL=sidecar_url,
    MEMORII_CREDENTIAL_PATH=str(credential_path),
    MEMORII_TASK_ID=task_id,
)

def run_pi(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "pi", "--mode", "json", "-p",
            "-e", "/opt/memorii-pi/.pi/extensions/memorii-extension.ts",
            "--provider", "stub", "--model", "stub-model",
            "--session-dir", str(session_dir),
            "--offline",
            *args,
        ],
        capture_output=True,
        text=True,
        env=dict(base_env, **(env_extra or {})),
        timeout=180,
    )

failures: list[str] = []

def drain() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "/opt/memorii-venv/bin/memorii-consume",
            "--installation-root", str(root / "installation"),
            "--spool-directory", str(spool_directory),
            "--drain",
            "--allowlisted-producers", PRODUCER,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

# Turn 1: fresh session, one user message, then the consumer commits it.
first = run_pi("--session-id", "cert-session", "record this certification turn")
print("turn1 rc:", first.returncode, (first.stdout or first.stderr)[:200].replace("\n", " "))
if first.returncode != 0:
    failures.append("turn1 failed")
drain1 = drain()
print("drain1 rc:", drain1.returncode, drain1.stdout.strip().replace("\n", " | ")[:400])
if drain1.returncode != 0:
    failures.append("drain1 failed")

# Restart: continue the SAME session in a new process; the extension sees
# the committed task and resumes it.
second = run_pi("--continue", "continue after restart")
print("turn2 rc:", second.returncode, (second.stdout or second.stderr)[:200].replace("\n", " "))
if second.returncode != 0:
    failures.append("turn2 failed")

# Fork attempt WITHOUT authorization must be cancelled by the extension.
fork = run_pi("--fork", str(session_dir / "cert-session.json"), "fork attempt")
fork_denied = fork.returncode != 0 or "cancel" in (fork.stderr + fork.stdout).lower()
print("fork rc:", fork.returncode, "denied:", fork_denied)

stub_server.shutdown()
stub_server.server_close()
sidecar_server.shutdown()
sidecar_server.server_close()

records = [json.loads(line) for line in (spool_directory / "intake.jsonl").read_text().splitlines()]
kinds = [record["operation_id"].split(":")[1] for record in records]
print("SPOOL:", kinds)

# Final drain commits the restart's commands.
drain = drain()
print("drain rc:", drain.returncode)
print(drain.stdout.strip()[:800])
if drain.returncode != 0:
    failures.append("drain failed: " + drain.stderr.strip()[:300])

after = [json.loads(line) for line in (spool_directory / "intake.jsonl").read_text().splitlines()]
committed = [r for r in after if r["state"] == "committed"]
print("COMMITTED:", len(committed), "of", len(after))

# Runtime state survived and advanced: query through the read service.
status, payload = sidecar.handle_state_request(
    bearer_token="credential:one",
    origin=None,
    body=json.dumps({"protocol_version": 1, "task_id": task_id, "view": "summary"}).encode(),
)
envelope = json.loads(payload)
print("task status:", status, envelope.get("status"), "revision", envelope.get("revision"))

checks = {
    "user messages captured": kinds.count("observe") >= 2,
    "both sessions resumed the provisioned task": kinds.count("resume") >= 2,
    "fork denied without authorization": fork_denied,
    "drain committed everything": len(committed) == len(after) and len(after) > 0,
    "runtime serves the task": status == 200,
}
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)

print("JOURNEY:", "PASS" if not failures else "FAIL", failures)
sys.exit(0 if not failures else 1)
