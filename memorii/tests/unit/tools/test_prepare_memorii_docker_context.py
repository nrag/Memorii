from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[4]
_SCRIPT = _ROOT / "tools" / "prepare_memorii_docker_context.py"
_RESOURCE_DIRECTORY = Path("memorii/core/semantic_ingestion/resources")
_DECODER_MANIFEST = Path("memorii/core/memory_evolution/observation_registry_sources/decoder-source-manifest.json")


def _module():
    specification = importlib.util.spec_from_file_location("prepare_memorii_docker_context", _SCRIPT)
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


def _decoder_paths(source_root: Path) -> list[Path]:
    manifest = json.loads((source_root / _DECODER_MANIFEST).read_text())
    return list(
        dict.fromkeys(source_root / Path(*Path(row["relative_path"]).parts) for row in manifest["files"])
    )


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


def test_crlf_decoder_replicas_normalize_the_full_declared_set(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    paths = _decoder_paths(source_root)
    assert len(paths) == 36
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


def test_decoder_source_semantic_drift_fails_after_crlf_normalization(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    decoder = _decoder_paths(source_root)[0]
    _as_crlf(decoder)
    decoder.write_bytes(decoder.read_bytes() + b"\n# decoder semantic drift\n")

    with pytest.raises(module.PreparationError, match="decoder source digest is invalid"):
        module.prepare(source_root)


def test_lone_carriage_return_fails_closed(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    prompt = source_root / _RESOURCE_DIRECTORY / "project_assertions.prompt.v1.json"
    prompt.write_bytes(prompt.read_bytes() + b"\r")

    with pytest.raises(module.PreparationError, match="lone carriage return"):
        module.prepare(source_root)


def test_decoder_lone_carriage_return_fails_closed(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    decoder = _decoder_paths(source_root)[0]
    decoder.write_bytes(decoder.read_bytes() + b"\r")

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


def test_unsafe_decoder_source_coordinate_fails_closed(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    manifest_path = source_root / _DECODER_MANIFEST
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][0]["relative_path"] = "../../outside.py"
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")))

    with pytest.raises(module.PreparationError, match="decoder source coordinate is unsafe"):
        module.prepare(source_root)


def test_conflicting_decoder_source_rows_fail_closed(tmp_path: Path) -> None:
    module = _module()
    source_root = _replica(tmp_path)
    manifest_path = source_root / _DECODER_MANIFEST
    manifest = json.loads(manifest_path.read_text())
    first = manifest["files"][0]
    duplicate = next(row for row in manifest["files"][1:] if row["relative_path"] == first["relative_path"])
    duplicate["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")))

    with pytest.raises(module.PreparationError, match="decoder source manifest duplicates conflict"):
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
def test_docker_build_normalizes_windows_crlf_bootstrap_context(tmp_path: Path) -> None:
    if not _docker_available():
        pytest.skip("Docker daemon is unavailable")
    context = _docker_context(tmp_path)
    source_root = context / "memorii"
    resources = source_root / _RESOURCE_DIRECTORY
    manifest = json.loads((resources / "project_assertions.manifest.v1.json").read_text())
    decoder_paths = _decoder_paths(source_root)
    for path in decoder_paths:
        _as_crlf(path)
    preflight_environment = dict(os.environ)
    preflight_environment["PYTHONPATH"] = str(source_root)
    preflight_environment["MEMORII_TEST_HOME"] = str(tmp_path / "preparation-required-home")
    preflight = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import os",
                    "from pathlib import Path",
                    "from types import SimpleNamespace",
                    "from memorii.core.memory_evolution.typed_value_registry_configuration import TypedValueRegistryConfigurationError",
                    "from memorii.integrations.hermes_factory import build_local_level2_runtime_binding",
                    "from memorii.integrations.hermes_local_authority import authorize_local_level2",
                    "home = Path(os.environ['MEMORII_TEST_HOME'])",
                    "authorize_local_level2(hermes_home=home)",
                    "context = SimpleNamespace(storage_root=home / 'memorii', hermes_home=home, session_id='session:one', user_id='user:ada', agent_identity='profile:primary', platform='cli', agent_context='primary', agent_workspace='hermes', parent_session_id=None)",
                    "try:",
                    "    build_local_level2_runtime_binding(context)",
                    "except TypedValueRegistryConfigurationError as error:",
                    "    raise SystemExit(0 if 'typed_value_registry_configuration_verification_failed' in str(error) else 1)",
                    "raise SystemExit(1)",
                )
            ),
        ],
        cwd=source_root,
        env=preflight_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr

    profile_paths = _profile_paths(source_root)
    for path in profile_paths:
        _as_crlf(path)
    schema_name = "project_assertions.output_schema.v1.json"
    assert hashlib.sha256((resources / schema_name).read_bytes()).hexdigest() != manifest["member_digests"][schema_name]
    decoder_manifest = json.loads((source_root / _DECODER_MANIFEST).read_text())
    first_decoder = decoder_manifest["files"][0]
    assert hashlib.sha256((source_root / first_decoder["relative_path"]).read_bytes()).hexdigest() != first_decoder["sha256"]

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
                "\n".join(
                    (
                        "from pathlib import Path",
                        "from types import SimpleNamespace",
                        "from memorii.integrations.hermes_factory import build_local_level2_runtime_binding",
                        "from memorii.integrations.hermes_local_authority import authorize_local_level2",
                        "home = Path('/tmp/memorii-hermes')",
                        "authorize_local_level2(hermes_home=home)",
                        "context = SimpleNamespace(storage_root=home / 'memorii', hermes_home=home, session_id='session:one', user_id='user:ada', agent_identity='profile:primary', platform='cli', agent_context='primary', agent_workspace='hermes', parent_session_id=None)",
                        "assert build_local_level2_runtime_binding(context).completed_turn_runtime is not None",
                    )
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert probe.returncode == 0, probe.stdout + probe.stderr
    finally:
        subprocess.run(["docker", "image", "rm", "--force", image_id], capture_output=True, text=True, check=False)
