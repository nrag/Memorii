"""Run pinned OpenClaw gateway turns against installed managed v8 intake and drain."""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, "/opt/memorii-src/memorii")
sys.path.insert(0, "/opt/memorii-src/memorii/tests/integration/hostcompat")

from managed_host_journey import ManagedHostJourney
from stub_openai_provider import serve_stub_provider

GATEWAY_TOKEN = "cert-token-1"
journey = ManagedHostJourney(Path("/tmp/memorii-journey"), "openclaw")
session_key = "agent:main:cert-session"
base_env = dict(
    os.environ, **journey.environment, OPENCLAW_GATEWAY_TOKEN=GATEWAY_TOKEN,
    MEMORII_OPENCLAW_SESSION_KEY=session_key,
)

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
def start_gateway() -> subprocess.Popen:
    return subprocess.Popen(
        ["openclaw", "gateway", "--bind", "loopback"],
        stdout=gateway_log, stderr=subprocess.STDOUT, start_new_session=True, env=base_env,
    )


gateway = start_gateway()


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

def run_agent(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["openclaw", "agent", "--json", "--model", "stub/stub-model", *args],
        capture_output=True, text=True, env=base_env, timeout=240,
    )

def stop_gateway() -> None:
    with suppress(ProcessLookupError):
        os.killpg(gateway.pid, signal.SIGTERM)
    try:
        gateway.wait(timeout=30)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(gateway.pid, signal.SIGKILL)
        gateway.wait(timeout=30)


try:
    assert wait_for_loopback_port(18789), Path("/tmp/gateway-journey.log").read_text()[-2000:]
    baseline = journey.read()
    first_prompt = "record this certification turn"
    first = run_agent("--session-key", session_key, "-m", first_prompt)
    assert first.returncode == 0, first.stderr
    first_receipt = journey.prove_turn(first_prompt)

    stop_gateway()
    with suppress(ConnectionRefusedError), socket.create_connection(("127.0.0.1", 18789), timeout=2):
        raise AssertionError("the old gateway is still listening")
    journey.stop()
    journey.start()
    gateway = start_gateway()
    assert wait_for_loopback_port(18789), Path("/tmp/gateway-journey.log").read_text()[-2000:]
    reopened = journey.read()
    assert reopened.goal == journey.goal and reopened.revision > baseline.revision
    assert reopened.task_version == baseline.task_version
    assert reopened.revision != reopened.task_version
    print("Reopened gateway and sidecar recalled the provisioned task and committed runtime revision", flush=True)

    second_prompt = "continue the same session"
    second = run_agent("--session-key", session_key, "-m", second_prompt)
    assert second.returncode == 0, second.stderr
    second_receipt = journey.prove_turn(second_prompt)
    assert second_receipt.operation_id != first_receipt.operation_id
    assert journey.read().revision > reopened.revision

    observations_before_other_session = list(journey.sidecar.observations)
    other = run_agent("--session-key", "agent:main:unbound-session", "-m", "unbound session")
    assert other.returncode == 0, other.stderr
    assert journey.sidecar.observations == observations_before_other_session
    retry = journey.drain()
    assert retry.returncode == 0 and retry.stdout == ""
    print("An unbound OpenClaw session could not submit to the Memorii task", flush=True)
    print("JOURNEY: PASS (managed resume and runtime state read)")
except Exception:
    gateway_log.flush()
    print(Path("/tmp/gateway-journey.log").read_text()[-6000:], file=sys.stderr)
    raise
finally:
    stop_gateway()
    gateway_log.close()
    stub_server.shutdown()
    stub_server.server_close()
    journey.stop()
