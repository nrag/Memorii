"""Run pinned Pi turns against installed managed v8 intake and drain."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from managed_host_journey import ManagedHostJourney
from stub_openai_provider import serve_stub_provider

root = Path("/tmp/memorii-journey")
session_id = "cert-session"
journey = ManagedHostJourney(root, "pi", session_id)
stub_url, stub_server = serve_stub_provider(observe=journey.model_requests.append)

agent_dir = Path("/root/.pi/agent")
agent_dir.mkdir(parents=True, exist_ok=True)
(agent_dir / "models.json").write_text(json.dumps({
    "providers": {
        "stub": {
            "name": "Stub",
            "baseUrl": f"{stub_url}/v1",
            "apiKey": "stub-key",
            "api": "openai-completions",
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

base_env = dict(os.environ, **journey.environment, MEMORII_PI_SESSION_ID=session_id)


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

try:
    baseline = journey.read()
    first_prompt = "record this certification turn"
    first = run_pi("--session-id", session_id, first_prompt)
    assert first.returncode == 0, first.stderr
    first_receipt = journey.prove_turn(first_prompt)
    journey.stop()
    journey.start()

    reopened = journey.read()
    assert reopened.goal == journey.goal and reopened.revision > baseline.revision
    assert reopened.task_version == baseline.task_version + 1
    assert reopened.revision != reopened.task_version
    print("Reopened sidecar recalled the provisioned task and committed runtime revision", flush=True)

    journey.prove_recall(first_prompt)
    second_prompt = "continue after restart"
    second = run_pi("--continue", second_prompt)
    assert second.returncode == 0, second.stderr
    assert journey.model_requests, second.stderr + "\n" + second.stdout[-4500:]
    journey.prove_model_recall(first_prompt)
    second_receipt = journey.prove_turn(second_prompt)
    assert second_receipt.operation_id != first_receipt.operation_id
    assert journey.read().revision > reopened.revision

    [session_file] = list(session_dir.rglob("*.jsonl"))
    observations_before_fork = list(journey.sidecar.observations)
    fork = run_pi("--fork", str(session_file), "fork attempt")
    assert "memorii denied an unbound Pi session" in fork.stderr, fork.stderr
    assert journey.sidecar.observations == observations_before_fork
    retry = journey.drain()
    assert retry.returncode == 0 and retry.stdout == ""
    print("The actual Pi startup fork could not submit to the bound Memorii task", flush=True)
    journey.revoke()
    revoked_turn = run_pi("--session-id", session_id, "continue after revocation")
    assert revoked_turn.returncode == 0, revoked_turn.stderr
    journey.prove_model_without_recall()
    print("JOURNEY: PASS (signed capture, restart recall, and revocation)")
finally:
    stub_server.shutdown()
    stub_server.server_close()
    journey.stop()
