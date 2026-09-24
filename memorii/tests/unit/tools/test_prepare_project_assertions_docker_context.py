from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[4]
_SCRIPT = _ROOT / "tools" / "prepare_project_assertions_docker_context.py"
_RESOURCE_DIRECTORY = Path("memorii/core/semantic_ingestion/resources")


def _module():
    specification = importlib.util.spec_from_file_location("prepare_project_assertions_docker_context", _SCRIPT)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _replica(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    shutil.copytree(_ROOT / "memorii" / "memorii", source_root / "memorii")
    return source_root


def _profile_paths(source_root: Path) -> list[Path]:
    resources = source_root / _RESOURCE_DIRECTORY
    manifest = json.loads((resources / "project_assertions.manifest.v1.json").read_text())
    paths = [resources / "project_assertions.manifest.v1.json"]
    paths.extend(resources / name for name in manifest["member_digests"])
    fingerprints = json.loads((resources / "project_assertions.component_fingerprints.v1.json").read_text())
    paths.extend(
        source_root / (Path(*component["module"].split("."))).with_suffix(".py")
        for component in fingerprints["components"]
    )
    return list(dict.fromkeys(paths))


def _as_crlf(path: Path) -> None:
    payload = path.read_bytes()
    assert b"\r" not in payload
    path.write_bytes(payload.replace(b"\n", b"\r\n"))


def test_crlf_profile_replicas_normalize_to_signed_bytes(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    paths = _profile_paths(source_root)
    expected = {path.relative_to(source_root): path.read_bytes() for path in paths}
    for path in paths:
        _as_crlf(path)

    module.prepare(source_root)

    assert {path.relative_to(source_root): path.read_bytes() for path in paths} == expected


def test_semantic_resource_drift_fails_after_crlf_normalization(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    prompt = source_root / _RESOURCE_DIRECTORY / "project_assertions.prompt.v1.json"
    _as_crlf(prompt)
    prompt.write_bytes(prompt.read_bytes() + b" ")

    with pytest.raises(module.PreparationError, match="resource digest is invalid"):
        module.prepare(source_root)


def test_component_source_semantic_drift_fails_after_crlf_normalization(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    component = source_root / "memorii" / "core" / "semantic_ingestion" / "project_assertions.py"
    _as_crlf(component)
    component.write_bytes(
        component.read_bytes().replace(
            b"PROJECT_ASSERTIONS_ADAPTER_SEMANTIC_REVISION = 1",
            b"PROJECT_ASSERTIONS_ADAPTER_SEMANTIC_REVISION = 2",
        )
    )

    with pytest.raises(module.PreparationError, match="component source digest is invalid"):
        module.prepare(source_root)


def test_lone_carriage_return_fails_closed(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    prompt = source_root / _RESOURCE_DIRECTORY / "project_assertions.prompt.v1.json"
    prompt.write_bytes(prompt.read_bytes() + b"\r")

    with pytest.raises(module.PreparationError, match="lone carriage return"):
        module.prepare(source_root)


def test_unsafe_component_module_coordinate_fails_closed(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    resources = source_root / _RESOURCE_DIRECTORY
    fingerprints_path = resources / "project_assertions.component_fingerprints.v1.json"
    fingerprints = json.loads(fingerprints_path.read_text())
    fingerprints["components"][0]["module"] = "memorii.core.semantic_ingestion.invalid-module"
    fingerprints_path.write_text(json.dumps(fingerprints, separators=(",", ":")))
    manifest_path = resources / "project_assertions.manifest.v1.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["member_digests"][fingerprints_path.name] = hashlib.sha256(fingerprints_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")))

    with pytest.raises(module.PreparationError, match="component module coordinate is unsafe"):
        module.prepare(source_root)


def _docker_available() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True, check=False
    ).returncode == 0


def _docker_context(tmp_path: Path) -> Path:
    context = tmp_path / "docker-context"
    context.mkdir()
    shutil.copy2(_ROOT / "Dockerfile.memorii", context / "Dockerfile.memorii")
    (context / "tools").mkdir()
    shutil.copy2(_SCRIPT, context / "tools" / _SCRIPT.name)
    (context / "memorii").mkdir()
    shutil.copy2(_ROOT / "memorii" / "pyproject.toml", context / "memorii" / "pyproject.toml")
    shutil.copytree(_ROOT / "memorii" / "memorii", context / "memorii" / "memorii", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(_ROOT / "acceptance", context / "acceptance", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return context


@pytest.mark.skipif(
    os.environ.get("MEMORII_RUN_DOCKER_TESTS") != "1",
    reason="set MEMORII_RUN_DOCKER_TESTS=1 to run the Docker integration regression",
)
def test_docker_build_normalizes_windows_crlf_profile_context(tmp_path: Path) -> None:
    if not _docker_available():
        pytest.skip("Docker daemon is unavailable")
    context = _docker_context(tmp_path)
    source_root = context / "memorii"
    resources = source_root / _RESOURCE_DIRECTORY
    manifest = json.loads((resources / "project_assertions.manifest.v1.json").read_text())
    paths = _profile_paths(source_root)
    for path in paths:
        _as_crlf(path)
    schema_name = "project_assertions.output_schema.v1.json"
    assert hashlib.sha256((resources / schema_name).read_bytes()).hexdigest() != manifest["member_digests"][schema_name]

    image_id_path = tmp_path / "image-id"
    build = subprocess.run(
        ["docker", "build", "--iidfile", str(image_id_path), "-f", "Dockerfile.memorii", "."],
        cwd=context,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    image_id = image_id_path.read_text().strip()
    try:
        probe = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/opt/hermes/.venv/bin/python",
                image_id,
                "-c",
                "from memorii.core.semantic_ingestion.project_assertions_profile import load_project_assertions_bundle; load_project_assertions_bundle()",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert probe.returncode == 0, probe.stdout + probe.stderr
    finally:
        subprocess.run(["docker", "image", "rm", "--force", image_id], capture_output=True, text=True, check=False)
