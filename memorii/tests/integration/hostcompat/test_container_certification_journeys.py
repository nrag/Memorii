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

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = __file__.rsplit("/memorii/", 1)[0]
JOURNEY_DIRECTORY = "/opt/memorii-journey"

JOURNEYS = {
    "pi": {
        "image": "memorii-pi-validation",
        "dockerfile": "Dockerfile.pi",
        "script": "pi_certification_journey.py",
        "venv": "/opt/memorii-venv/bin/python",
        "asset_root": "/opt/memorii-pi/.pi/extensions",
    },
    "openclaw": {
        "image": "memorii-openclaw-validation",
        "dockerfile": "Dockerfile.openclaw",
        "script": "openclaw_certification_journey.py",
        "venv": "/opt/memorii-venv/bin/python",
        "asset_root": "/opt/memorii-openclaw/plugin",
    },
    "hermes": {
        "image": "hermes-memorii-pr",
        "dockerfile": "Dockerfile.memorii",
        "script": "hermes_certification_journey.py",
        "venv": "/opt/hermes/.venv/bin/python",
    },
}


def _docker_available() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "info", "--format", "ok"],
        capture_output=True, text=True, timeout=30,
    ).returncode == 0


@dataclass(frozen=True)
class NativeArtifacts:
    wheel_directory: Path
    wheel_digest: str
    asset_members: dict[str, dict[str, str]]


@pytest.fixture(scope="session")
def native_candidate_wheel(tmp_path_factory: pytest.TempPathFactory) -> NativeArtifacts:
    """Build one wheel and both installable asset archives for certification."""
    configured_output = os.environ.get("MEMORII_NATIVE_ASSET_OUTPUT")
    output = Path(configured_output) if configured_output else tmp_path_factory.mktemp("memorii-native-candidate")
    wheel_directory = output / "wheel"
    wheel_directory.mkdir(parents=True)
    revision = subprocess.check_output(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"], text=True, timeout=30).strip()
    if configured_output:
        status = subprocess.check_output(
            ["git", "-C", REPO_ROOT, "status", "--porcelain=v1", "--untracked-files=all"], text=True, timeout=30,
        )
        if status:
            pytest.fail("release candidate assets require a clean checkout")
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-build-isolation", "--no-deps",
         "--wheel-dir", str(wheel_directory), str(Path(REPO_ROOT) / "memorii")],
        env={**os.environ, "SOURCE_DATE_EPOCH": subprocess.check_output(
            ["git", "-C", REPO_ROOT, "show", "-s", "--format=%ct", revision], text=True, timeout=30,
        ).strip()},
        check=True, timeout=300,
    )
    [wheel] = wheel_directory.glob("memorii-*.whl")
    with wheel.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    assets = output / "host-assets"
    subprocess.run(
        [sys.executable, str(Path(REPO_ROOT) / "tools/build_native_host_assets.py"),
         "--wheel", str(wheel), "--output", str(assets), "--revision", revision],
        check=True, timeout=60,
    )
    manifest = json.loads((assets / "native-host-assets.json").read_bytes())
    assert manifest["wheel"] == {"filename": wheel.name, "sha256": digest}
    return NativeArtifacts(wheel_directory, digest, {
        host["host"]: {row["filename"]: row["sha256"] for row in host["members"]} for host in manifest["hosts"]
    })


def _build(image: str, dockerfile: str, artifacts: NativeArtifacts | None) -> None:
    # Absolute Dockerfile path: CI runs pytest from memorii/, so a bare
    # relative name cannot resolve. Build logs stream to the console so a
    # failed build is diagnosable instead of a bare CalledProcessError.
    tag = f"{image}:ci-{_commit()}"
    command = ["docker", "build", "-f", str(Path(REPO_ROOT) / dockerfile), "-t", tag]
    if artifacts is not None:
        command += [
            "--build-context", f"memorii-wheel={artifacts.wheel_directory}",
            "--build-arg", f"MEMORII_WHEEL_SHA256={artifacts.wheel_digest}",
        ]
    subprocess.run([*command, REPO_ROOT], timeout=3600, check=True)
    subprocess.run(
        ["docker", "tag", tag, f"{image}:ci"], check=True, timeout=120
    )


def _commit() -> str:
    result = subprocess.run(
        ["git", "-C", REPO_ROOT, "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip() or "unknown"


def _run_journey(host: str, artifacts: NativeArtifacts | None) -> None:
    spec = JOURNEYS[host]
    image = f"{spec['image']}:ci"
    container = f"memorii-journey-{host}-{_commit()}"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
    subprocess.run(
        ["docker", "run", "-d", "--name", container, "--entrypoint", "bash", image, "-lc", "sleep 3600"],
        capture_output=True, check=True, timeout=120,
    )
    try:
        if artifacts is not None:
            subprocess.run(
                ["docker", "exec", container, spec["venv"], "-I", "-c",
                 "import hashlib, json, sys, sysconfig; from importlib.metadata import distribution; "
                 "from pathlib import Path; import memorii; "
                 "source = json.loads(distribution('memorii').read_text('direct_url.json')); "
                 "assert source['archive_info']['hashes']['sha256'] == sys.argv[1]; "
                 "assert Path(memorii.__file__).resolve().is_relative_to(sysconfig.get_path('purelib')); "
                 "assets = Path(sys.argv[2]); "
                 "assert all(hashlib.sha256((assets / path).read_bytes()).hexdigest() == digest "
                 "for path, digest in json.loads(sys.argv[3]).items())",
                 artifacts.wheel_digest, spec["asset_root"], json.dumps(artifacts.asset_members[host])],
                check=True, timeout=120,
            )
        subprocess.run(
            ["docker", "exec", container, "mkdir", "-p", JOURNEY_DIRECTORY],
            capture_output=True, check=True, timeout=120,
        )
        for name in (spec["script"], "stub_openai_provider.py", "hermes_chat_pty.py", "managed_host_journey.py"):
            subprocess.run(
                ["docker", "cp", f"{REPO_ROOT}/memorii/tests/integration/hostcompat/{name}",
                 f"{container}:{JOURNEY_DIRECTORY}/{name}"],
                capture_output=True, check=True, timeout=120,
            )
        result = subprocess.run(
            ["docker", "exec", container, spec["venv"],
             f"{JOURNEY_DIRECTORY}/{spec['script']}"],
            capture_output=True, text=True, timeout=2400,
        )
        output = result.stdout + result.stderr
        print(output[-6000:])
        assert result.returncode == 0, f"{host} journey failed"
        assert "JOURNEY: PASS" in output, f"{host} journey did not pass"
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)


@pytest.mark.parametrize("host", sorted(JOURNEYS))
def test_container_certification_journey(host: str, request: pytest.FixtureRequest) -> None:
    if not _docker_available():
        if os.environ.get("MEMORII_RUN_DOCKER_TESTS") == "1":
            pytest.fail("container certification requires a Docker daemon")
        pytest.skip("docker daemon unavailable")
    spec = JOURNEYS[host]
    artifacts = request.getfixturevalue("native_candidate_wheel") if host in {"openclaw", "pi"} else None
    subprocess.run(
        ["docker", "image", "rm", "-f", f"{spec['image']}:ci"], capture_output=True
    )
    _build(spec["image"], spec["dockerfile"], artifacts)
    _run_journey(host, artifacts)
