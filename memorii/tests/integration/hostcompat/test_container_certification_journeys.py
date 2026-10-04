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
from pathlib import Path

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
            "memorii/core/persistence/runtime_contracts.py",
            "memorii/core/storage_administration/service.py",
            "memorii/core/storage_administration/writer_enrollment.py",
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
            "memorii/core/persistence/runtime_contracts.py",
            "memorii/core/storage_administration/service.py",
            "memorii/core/storage_administration/writer_enrollment.py",
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
    # Absolute Dockerfile path: CI runs pytest from memorii/, so a bare
    # relative name cannot resolve. Build logs stream to the console so a
    # failed build is diagnosable instead of a bare CalledProcessError.
    tag = f"{image}:ci-{_commit()}"
    subprocess.run(
        ["docker", "build", "-f", str(Path(REPO_ROOT) / dockerfile), "-t", tag, REPO_ROOT],
        timeout=3600, check=True,
    )
    subprocess.run(
        ["docker", "tag", tag, f"{image}:ci"], check=True, timeout=120
    )


def _commit() -> str:
    result = subprocess.run(
        ["git", "-C", REPO_ROOT, "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip() or "unknown"


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
        print(output[-6000:])
        assert result.returncode == 0, f"{host} journey failed"
        assert "JOURNEY: PASS" in output, f"{host} journey did not pass"
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)


@pytest.mark.skipif(not _docker_available(), reason="docker daemon unavailable")
@pytest.mark.parametrize("host", sorted(JOURNEYS))
def test_container_certification_journey(host: str) -> None:
    spec = JOURNEYS[host]
    subprocess.run(
        ["docker", "image", "rm", "-f", f"{spec['image']}:ci"], capture_output=True
    )
    _build(spec["image"], spec["dockerfile"])
    _run_journey(host)
