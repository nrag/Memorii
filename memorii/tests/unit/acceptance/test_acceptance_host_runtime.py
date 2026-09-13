from __future__ import annotations

import ast
import inspect
from pathlib import Path

from acceptance.host_runtime import InstalledAcceptanceRuntime, runtime_config_path

ROOT = Path(__file__).parents[4]


def test_installed_provider_uses_fixed_platform_data_config_and_cli_has_no_injection() -> None:
    assert runtime_config_path().is_absolute()
    assert runtime_config_path().parts[-4:] == ("etc", "memorii", "acceptance", "runtime-v1.json")
    assert "evaluator" not in inspect.signature(__import__("acceptance.cli", fromlist=["main"]).main).parameters
    assert InstalledAcceptanceRuntime.__module__ == "acceptance.host_runtime"


def test_packaging_and_pr_gate_require_installed_acceptance_runtime() -> None:
    pyproject = (ROOT / "memorii" / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "pr-gates.yml").read_text(encoding="utf-8")
    assert 'installed = "acceptance.host_runtime:InstalledAcceptanceRuntime"' in pyproject
    assert "acceptance-authority-runtime:" in workflow
    assert "acceptance-authority-runtime" in workflow.split("semantic-ingestion:", 1)[1]


def test_acceptance_and_production_keep_a_serialized_import_boundary() -> None:
    acceptance_sources = (ROOT / "acceptance").glob("*.py")
    for path in acceptance_sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports.extend(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
        assert not any(name == "memorii" or name.startswith("memorii.") for name in imports)
    production = ROOT / "memorii" / "memorii" / "core" / "memory_evolution" / "deployment_authorization.py"
    tree = ast.parse(production.read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports.extend(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not any(name == "acceptance" or name.startswith("acceptance.") for name in imports)
