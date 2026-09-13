from __future__ import annotations

import ast
import inspect
from pathlib import Path

from acceptance.host_runtime import InstalledAcceptanceRuntime, runtime_config_path

ROOT = Path(__file__).parents[4]


def _cross_package_imports(path: Path, forbidden_root: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append(node.module)
    return [name for name in imports if name == forbidden_root or name.startswith(f"{forbidden_root}.")]


def _production_isolation_sources(root: Path) -> tuple[Path, ...]:
    package = root / "memorii" / "memorii"
    sources = list((package / "core" / "memory_evolution").rglob("*.py"))
    sources.extend((package / "core" / "semantic_ingestion").rglob("*.py"))
    sources.extend((package / "tools").glob("semantic_ingestion*.py"))
    integrations = package / "integrations"
    if integrations.is_dir():
        sources.extend(integrations.rglob("*.py"))
    return tuple(sorted(set(sources)))


def test_installed_provider_uses_fixed_platform_data_config_and_cli_has_no_injection() -> None:
    assert runtime_config_path().is_absolute()
    assert runtime_config_path().parts[-4:] == ("etc", "memorii", "acceptance", "runtime-v2.json")
    assert "evaluator" not in inspect.signature(__import__("acceptance.cli", fromlist=["main"]).main).parameters
    assert InstalledAcceptanceRuntime.__module__ == "acceptance.host_runtime"


def test_packaging_and_pr_gate_require_installed_acceptance_runtime() -> None:
    pyproject = (ROOT / "memorii" / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "pr-gates.yml").read_text(encoding="utf-8")
    assert 'installed = "acceptance.host_runtime:InstalledAcceptanceRuntime"' in pyproject
    assert "acceptance-authority-runtime:" in workflow
    assert "acceptance-authority-runtime" in workflow.split("semantic-ingestion:", 1)[1]


def test_acceptance_and_production_keep_a_serialized_import_boundary() -> None:
    acceptance_sources = tuple((ROOT / "acceptance").rglob("*.py"))
    production_sources = _production_isolation_sources(ROOT)
    assert acceptance_sources and production_sources
    assert not {
        path: _cross_package_imports(path, "memorii")
        for path in acceptance_sources
        if _cross_package_imports(path, "memorii")
    }
    assert not {
        path: _cross_package_imports(path, "acceptance")
        for path in production_sources
        if _cross_package_imports(path, "acceptance")
    }


def test_serialized_import_boundary_detects_nested_import_forms(tmp_path: Path) -> None:
    acceptance_nested = tmp_path / "acceptance" / "nested.py"
    production_nested = tmp_path / "memorii" / "core" / "semantic_ingestion" / "nested.py"
    acceptance_nested.parent.mkdir(parents=True)
    production_nested.parent.mkdir(parents=True)
    acceptance_nested.write_text("from memorii.core.memory_evolution import deployment_authorization\n")
    production_nested.write_text("import acceptance.production_revocation\n")
    assert _cross_package_imports(acceptance_nested, "memorii") == ["memorii.core.memory_evolution"]
    assert _cross_package_imports(production_nested, "acceptance") == ["acceptance.production_revocation"]
