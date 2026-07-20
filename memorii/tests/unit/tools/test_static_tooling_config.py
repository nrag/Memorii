from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = PROJECT_ROOT.parent


def _pyproject() -> dict[str, object]:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _tool_config(name: str) -> dict[str, object]:
    data = _pyproject()
    tool = data["tool"]
    assert isinstance(tool, dict)
    config = tool[name]
    assert isinstance(config, dict)
    return config


def test_dev_extra_installs_static_tooling() -> None:
    data = _pyproject()
    project = data["project"]
    assert isinstance(project, dict)
    optional = project["optional-dependencies"]
    assert isinstance(optional, dict)
    dev = optional["dev"]
    assert isinstance(dev, list)

    assert "pytest>=8.0" in dev
    assert "openai>=1.0" in dev
    assert any(isinstance(dep, str) and dep.startswith("ruff>=") for dep in dev)
    assert any(isinstance(dep, str) and dep.startswith("pyright>=") for dep in dev)


def test_ruff_config_is_correctness_oriented() -> None:
    ruff = _tool_config("ruff")
    lint = ruff["lint"]
    assert isinstance(lint, dict)

    assert ruff["target-version"] == "py311"
    assert ruff["src"] == ["memorii", "tests"]
    assert lint["select"] == ["E", "F", "I", "B", "UP", "SIM"]
    assert "E501" in lint["ignore"]
    per_file_ignores = lint["per-file-ignores"]
    assert isinstance(per_file_ignores, dict)
    assert "memorii/core/benchmark/memory_evolution_sim/*.py" not in per_file_ignores
    assert per_file_ignores["tests/**/*.py"] == ["B011"]


def test_pyright_config_is_scoped_to_hardening_surfaces() -> None:
    pyright = _tool_config("pyright")

    assert pyright["pythonVersion"] == "3.11"
    assert "venvPath" not in pyright
    assert "venv" not in pyright
    assert pyright["typeCheckingMode"] == "basic"
    assert pyright["reportMissingTypeStubs"] is False
    assert pyright["reportArgumentType"] == "error"
    assert pyright["reportAssignmentType"] == "error"
    assert pyright["reportAttributeAccessIssue"] == "error"
    assert pyright["reportCallIssue"] == "error"
    assert pyright["reportGeneralTypeIssues"] == "error"
    assert pyright["reportOperatorIssue"] == "error"
    assert pyright["reportOptionalMemberAccess"] == "error"
    assert pyright["reportReturnType"] == "error"
    assert pyright["include"] == [
        "memorii/core/belief",
        "memorii/core/benchmark/artifact_rows",
        "memorii/core/benchmark/artifact_validation.py",
        "memorii/core/benchmark/reproducibility.py",
        "memorii/core/memory_evolution",
        "memorii/core/benchmark/memory_evolution_sim",
        "memorii/core/benchmark/memory_evolution_runtime",
        "memorii/core/calibration",
        "memorii/core/prompts",
        "memorii/core/llm_decision",
        "memorii/tools/benchmark_suites",
    ]


def test_static_tooling_workflow_doc_lists_supported_commands() -> None:
    doc = (REPO_ROOT / "docs" / "development" / "static_tooling.md").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "pr-gates.yml").read_text(encoding="utf-8")

    assert "python -m pip install -e '.[dev]'" in doc
    assert "python -W error -m pytest tests/unit -p no:cacheprovider" in doc
    assert "python -m ruff check memorii tests" in doc
    assert "--select F" not in doc
    assert "pyright --pythonpath" in doc
    assert "PromptRegistry().load('memory_extraction:v1', owner=PromptOwner.LLM_MEMORY_EXTRACTOR)" in doc
    assert "from memorii.core.prompts.runtime_manifest import PromptOwner" in doc
    assert "Run Ruff" in workflow
    assert "ruff check memorii tests" in workflow
    assert "pyright --pythonpath" in workflow
    assert "Build and smoke-test wheel" in workflow
    assert "pytest -W error tests/unit" in workflow
    assert "pytest -W error" in workflow
    assert "pip wheel . --no-deps" in workflow
    assert "PromptRegistry().load('memory_extraction:v1', owner=PromptOwner.LLM_MEMORY_EXTRACTOR)" in workflow
    assert "from memorii.core.prompts.runtime_manifest import PromptOwner" in workflow
    assert "is_relative_to(root)" in workflow
    assert "Do not mass-format unrelated files." in doc
    assert "Pyright is error-mode" in doc


def test_prompt_contracts_are_owned_by_the_installable_package() -> None:
    package_prompt_root = PROJECT_ROOT / "memorii" / "prompts"

    assert package_prompt_root.is_dir()
    assert list(package_prompt_root.glob("**/*.yaml"))
    assert not (PROJECT_ROOT / "prompts").exists()
    package_data = _tool_config("setuptools")["package-data"]
    assert isinstance(package_data, dict)
    assert "prompts/**/*.yaml" in package_data["memorii"]


def test_scheduled_workflow_separates_opt_in_live_gate_from_pr_gates() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "benchmark-scheduled.yml").read_text(encoding="utf-8")

    assert "MEMORII_RUN_LIVE_GATES" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "replicate: [0, 1]" in workflow
    assert "--minimum-seed-count" in workflow
    assert "--minimum-scenarios-per-replicate" in workflow
    assert "--minimum-replicates-per-seed" in workflow
    assert "--allow-live" in workflow
