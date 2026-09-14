from __future__ import annotations

import importlib.util
import json
import subprocess
import tomllib
from pathlib import Path

_ROOT = Path(__file__).parents[4]
_SCRIPT = _ROOT / "tools" / "setup_hermes_development.py"


def _module():
    specification = importlib.util.spec_from_file_location(
        "setup_hermes_development", _SCRIPT
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_development_connector_declares_exactly_one_service_factory() -> None:
    project = tomllib.loads(
        (_ROOT / "tools" / "hermes_development_connector" / "pyproject.toml").read_text()
    )

    assert project["project"]["entry-points"]["memorii.hermes.provider_service"] == {
        "development": "memorii_hermes_development:build_runtime_binding"
    }


def test_setup_installs_both_editable_packages_and_can_skip_config(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    module = _module()
    python = tmp_path / "python"
    python.touch()
    calls: list[list[str]] = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        if arguments[-2:] == ["pip", "--version"]:
            return subprocess.CompletedProcess(arguments, 0, stdout="pip 25", stderr="")
        if "capture_output" in kwargs:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=json.dumps(
                    {
                        "development_factory_count": 1,
                        "hermes_abc_installed": True,
                        "memorii_provider_installed": True,
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(module.subprocess, "run", run)

    assert module.main(["--hermes-python", str(python), "--skip-config"]) == 0
    assert calls[1][:6] == [
        str(python.absolute()),
        "-m",
        "pip",
        "install",
        "--no-build-isolation",
        "--editable",
    ]
    assert str(_ROOT / "memorii") in calls[1]
    assert str(_ROOT / "tools" / "hermes_development_connector") in calls[1]
    assert len(calls) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
