"""Run pinned OpenClaw gateway turns against installed managed v8 intake and drain."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

from managed_host_journey import ManagedHostJourney
from stub_openai_provider import serve_stub_provider

GATEWAY_TOKEN = "cert-token-1"
session_key = "agent:main:cert-session"
journey = ManagedHostJourney(Path("/tmp/memorii-journey"), "openclaw", session_key)
base_env = dict(
    os.environ, **journey.environment, OPENCLAW_GATEWAY_TOKEN=GATEWAY_TOKEN,
    MEMORII_OPENCLAW_SESSION_KEY=session_key,
)

# Load the packaged plugin in place, so it resolves the same OpenClaw
# installation as the gateway and never installs dependencies at runtime.
plugin_directory = "/opt/memorii-openclaw/plugin"

stub_url, stub_server = serve_stub_provider(observe=journey.model_requests.append)

def config_set(path: str, value: str) -> None:
    result = subprocess.run(
        ["openclaw", "config", "set", path, value],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, f"config set {path} failed: {result.stdout} {result.stderr}"

config_set("models.providers.stub", json.dumps({
    "baseUrl": f"{stub_url}/v1",
    "apiKey": "stub-key",
    "api": "openai-completions",
    "authHeader": True,
    "models": [{"id": "stub-model", "name": "Stub Model", "api": "openai-completions"}],
}))
config_set("plugins.load.paths", json.dumps([plugin_directory]))
config_set("plugins.entries.memorii", json.dumps({
    "enabled": True, "config": {},
    "hooks": {"allowConversationAccess": True},
}))
config_set("plugins.allow", json.dumps(["memorii"]))
config_set("plugins.slots.contextEngine", "memorii")
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
    if gateway.poll() is not None:
        return
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
    assert reopened.task_version == baseline.task_version + 1
    assert reopened.revision != reopened.task_version
    print("Reopened gateway and sidecar recalled the provisioned task and committed runtime revision", flush=True)

    journey.prove_recall(first_prompt)
    second_prompt = "continue the same session"
    second = run_agent("--session-key", session_key, "-m", second_prompt)
    assert second.returncode == 0, second.stderr
    journey.prove_model_recall(first_prompt)
    second_receipt = journey.prove_turn(second_prompt)
    assert second_receipt.operation_id != first_receipt.operation_id
    assert journey.read().revision > reopened.revision

    observations_before_other_session = list(journey.observations)
    other = run_agent("--session-key", "agent:main:unbound-session", "-m", "unbound session")
    assert other.returncode == 0, other.stderr
    assert journey.observations == observations_before_other_session
    retry = journey.drain()
    assert retry.returncode == 0 and retry.stdout == ""
    print("An unbound OpenClaw session could not submit to the Memorii task", flush=True)

    journey.stop()
    try:
        for turn in range(17):
            unavailable = run_agent("--session-key", session_key, "-m", f"sidecar outage turn {turn}")
            assert unavailable.returncode == 0, unavailable.stderr
    finally:
        journey.start()
    recovered_prompt = "continue when Memorii returns"
    recovered = run_agent("--session-key", session_key, "-m", recovered_prompt)
    assert recovered.returncode == 0, recovered.stderr
    journey.prove_model_recall(second_prompt)
    journey.prove_turn(recovered_prompt)
    print("OpenClaw capture and recall recovered without restarting the gateway after 17 unavailable turns", flush=True)

    journey.revoke()
    prior_model_requests = len(journey.model_requests)
    revoked_prompt = "continue after revocation"
    revoked_turn = run_agent("--session-key", session_key, "-m", revoked_prompt)
    assert revoked_turn.returncode == 0, revoked_turn.stderr
    assert len(journey.model_requests) > prior_model_requests
    assert any(revoked_prompt in message for message in journey.last_model_messages())
    journey.prove_model_without_recall()
    recall_marker = "Memorii historical user data"
    assert all(recall_marker not in json.dumps(request) for request in journey.model_requests[prior_model_requests:])
    assert any(second_prompt in message for message in journey.last_model_messages())

    stop_gateway()
    gateway = start_gateway()
    assert wait_for_loopback_port(18789), Path("/tmp/gateway-journey.log").read_text()[-2000:]
    prior_model_requests = len(journey.model_requests)
    after_restart = "continue after revoked gateway restart"
    restarted_turn = run_agent("--session-key", session_key, "-m", after_restart)
    assert restarted_turn.returncode == 0, restarted_turn.stderr
    assert len(journey.model_requests) > prior_model_requests
    assert any(after_restart in message for message in journey.last_model_messages())
    assert all(recall_marker not in json.dumps(request) for request in journey.model_requests[prior_model_requests:])
    assert any(second_prompt in message for message in journey.last_model_messages())

    stop_gateway()
    native_state = Path.home() / ".openclaw"
    native_history = [
        path for path in native_state.rglob("*")
        if path.is_file()
        and path.suffix in {".sqlite", ".sqlite-wal", ".db", ".db-wal", ".jsonl", ".json"}
    ]
    assert any(first_prompt.encode() in path.read_bytes() for path in native_history)
    assert all(recall_marker.encode() not in path.read_bytes() for path in native_history)
    print("OpenClaw retained its original transcript and omitted the recall projection after revocation and restart")
    print("JOURNEY: PASS (signed capture, restart recall, and revocation)")
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
