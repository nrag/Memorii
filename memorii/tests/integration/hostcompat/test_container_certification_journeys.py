"""Container-driven certification journeys: Pi, OpenClaw, Hermes.

Each journey runs the REAL host (pinned image, offline stub model provider)
end to end against a live Memorii sidecar and asserts its verdict. The
suite skips cleanly when Docker is unavailable so it can live in the
ordinary integration tier; the CI job provides the daemon.

Journey scripts and images:
- Pi:        Dockerfile.pi           -> memorii-pi-validation,        pi_certification_journey.py
- OpenClaw:  Dockerfile.openclaw     -> memorii-openclaw-validation,  openclaw_certification_journey.py
- Hermes:    Dockerfile.memorii      -> hermes-memorii-pr,            hermes_certification_journey.py
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

REPO_ROOT = __file__.rsplit("/memorii/", 1)[0]

JOURNEYS = {
    "pi": {
        "image": "memorii-pi-validation",
        "dockerfile": "Dockerfile.pi",
        "script": "pi_certification_journey.py",
        "venv": "/opt/memorii-venv/bin/python",
        "refresh": (
            "memorii/core/harness_state/sidecar.py",
            "memorii/core/harness_state/consumer.py",
            "memorii/tools/runtime_consume.py",
            "memorii/core/persistence/runtime_api.py",
        ),
    },
    "openclaw": {
        "image": "memorii-openclaw-validation",
        "dockerfile": "Dockerfile.openclaw",
        "script": "openclaw_certification_journey.py",
        "venv": "/opt/memorii-venv/bin/python",
        "refresh": (
            "memorii/core/harness_state/sidecar.py",
            "memorii/core/harness_state/consumer.py",
            "memorii/tools/runtime_consume.py",
            "memorii/core/persistence/runtime_api.py",
        ),
    },
    "hermes": {
        "image": "hermes-memorii-pr",
        "dockerfile": "Dockerfile.memorii",
        "script": "hermes_certification_journey.py",
        "venv": "/opt/hermes/.venv/bin/python",
        # The Hermes journey drives the in-process provider through Hermes
        # itself; its image ships the pinned integration sources it needs,
        # so no source refresh applies.
        "refresh": (),
    },
}


def _docker_available() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "info", "--format", "ok"],
        capture_output=True, text=True, timeout=30,
    ).returncode == 0


def _build(image: str, dockerfile: str) -> None:
    subprocess.run(
        ["docker", "build", "-f", dockerfile, "-t", f"{image}:ci", REPO_ROOT],
        capture_output=True, text=True, timeout=3600, check=True,
    )


def _run_journey(host: str) -> None:
    spec = JOURNEYS[host]
    image = f"{spec['image']}:ci"
    container = f"memorii-journey-{host}-{subprocess.run(['git', '-C', REPO_ROOT, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip() or 'x'}"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
    subprocess.run(
        ["docker", "run", "-d", "--name", container, "--entrypoint", "bash", image, "-lc", "sleep 3600"],
        capture_output=True, check=True, timeout=120,
    )
    try:
        for source in spec["refresh"]:
            subprocess.run(
                ["docker", "cp", f"{REPO_ROOT}/memorii/{source}", f"{container}:/opt/memorii-src/memorii/{source}"],
                capture_output=True, check=True, timeout=120,
            )
        subprocess.run(
            ["docker", "exec", container, "mkdir", "-p",
             "/opt/memorii-src/memorii/tests/integration/hostcompat"],
            capture_output=True, check=True, timeout=120,
        )
        for name in (spec["script"], "stub_openai_provider.py", "hermes_chat_pty.py"):
            subprocess.run(
                ["docker", "cp", f"{REPO_ROOT}/memorii/tests/integration/hostcompat/{name}",
                 f"{container}:/opt/memorii-src/memorii/tests/integration/hostcompat/{name}"],
                capture_output=True, check=True, timeout=120,
            )
        if host == "openclaw":
            for name in ("index.js", "openclaw.plugin.json", "package.json"):
                subprocess.run(
                    ["docker", "cp", f"{REPO_ROOT}/memorii/memorii/integrations/openclaw/plugin/{name}",
                     f"{container}:/opt/memorii-openclaw/plugin/{name}"],
                    capture_output=True, check=True, timeout=120,
                )
        if host == "pi":
            subprocess.run(
                ["docker", "cp", f"{REPO_ROOT}/memorii/memorii/integrations/pi/extension/memorii-extension.ts",
                 f"{container}:/opt/memorii-pi/.pi/extensions/memorii-extension.ts"],
                capture_output=True, check=True, timeout=120,
            )
        result = subprocess.run(
            ["docker", "exec", container, spec["venv"],
             f"/opt/memorii-src/memorii/tests/integration/hostcompat/{spec['script']}"],
            capture_output=True, text=True, timeout=2400,
        )
        output = result.stdout + result.stderr
        print(output[-2000:])
        assert result.returncode == 0, f"{host} journey failed"
        assert "JOURNEY: PASS" in output, f"{host} journey did not pass"
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)


@pytest.mark.skipif(not _docker_available(), reason="docker daemon unavailable")
@pytest.mark.parametrize("host", sorted(JOURNEYS))
def test_container_certification_journey(host: str) -> None:
    spec = JOURNEYS[host]
    image = f"{spec['image']}:ci"
    probe = subprocess.run(
        ["docker", "image", "inspect", image], capture_output=True, timeout=60,
    )
    if probe.returncode != 0:
        _build(spec["image"], spec["dockerfile"])
    _run_journey(host)
