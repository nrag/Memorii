from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

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


def _workflow_config(name: str) -> dict[str, object]:
    data = yaml.load(
        (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert isinstance(data, dict)
    return data


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
        "memorii/core/memory_plane",
        "memorii/core/provider",
        "memorii/core/promotion",
        "memorii/core/benchmark/memory_evolution_sim",
        "memorii/core/benchmark/memory_evolution_runtime",
        "memorii/core/benchmark/calibration",
        "memorii/core/prompts",
        "memorii/core/llm_decision",
        "memorii/integrations",
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
    load_command = (
        "PromptRegistry().load('memory_extraction:v1', "
        "owner=PromptOwner.LLM_MEMORY_EXTRACTOR, output_model=MemoryExtractionOutput)"
    )
    assert load_command in doc
    assert "from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionOutput" in doc
    assert "from memorii.core.prompts.runtime_manifest import PromptOwner" in doc
    assert "Run Ruff" in workflow
    assert "ruff check memorii tests" in workflow
    assert "pyright --pythonpath" in workflow
    assert "Build and smoke-test wheel" in workflow
    assert "pytest -W error tests/unit" in workflow
    assert "pytest -W error" in workflow
    assert "pip wheel . --no-deps" in workflow
    assert load_command in workflow
    assert "from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionOutput" in workflow
    assert "from memorii.core.prompts.runtime_manifest import PromptOwner" in workflow
    assert "is_relative_to(root)" in workflow
    assert "memorii.core.promotion.legacy_models" in doc
    assert "memorii.core.promotion.legacy_models" in workflow
    assert "assert all(find_spec(module) is None for module in removed)" in doc
    assert "assert all(find_spec(module) is None for module in removed)" in workflow
    assert "ignored in-tree `build/` directory" in doc
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


def test_hardening_closure_matrix_covers_every_declared_contract() -> None:
    matrix = (REPO_ROOT / "docs" / "plans" / "engineering_hardening_closure_matrix.md").read_text(
        encoding="utf-8"
    )
    contract_ids = re.findall(r"^\| (C\d+) \|", matrix, flags=re.MULTILINE)

    assert contract_ids == [f"C{index}" for index in range(1, 15)]
    for required_outcome in (
        "Extraction outcomes distinguish live success",
        "caller delivery ID",
        "process-safe and crash-atomic",
        "bounded stale recovery",
        "tool dispatch",
    ):
        assert required_outcome in matrix


def test_scheduled_workflow_requires_manual_live_certification_and_opt_in_scheduled_runs() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "benchmark-scheduled.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    config = _workflow_config("benchmark-scheduled.yml")
    triggers = config["on"]
    environment = config["env"]
    concurrency = config["concurrency"]
    jobs = config["jobs"]

    assert isinstance(triggers, dict)
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert isinstance(environment, dict)
    assert environment["MEMORII_SOURCE_REVISION"] == "${{ github.sha }}"
    assert isinstance(concurrency, dict)
    assert concurrency["group"] == "benchmark-certification-${{ github.sha }}"
    assert concurrency["cancel-in-progress"] == "false"
    assert isinstance(jobs, dict)
    assert set(jobs) == {"fake-oracle-plumbing", "live-runtime-smoke", "live-runtime-gate"}
    live_smoke = jobs["live-runtime-smoke"]
    assert isinstance(live_smoke, dict)
    assert live_smoke["timeout-minutes"] == "180"
    live_environment = live_smoke["env"]
    assert isinstance(live_environment, dict)
    assert live_environment["MEMORII_LLM_PROVIDER"] == "openai"
    assert live_environment["MEMORII_ENABLE_LIVE_LLM_TESTS"] == "true"
    assert live_environment["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    live_gate = jobs["live-runtime-gate"]
    assert isinstance(live_gate, dict)
    assert live_gate["name"] == "Live Runtime Statistical Gate"
    assert live_gate["needs"] == "live-runtime-smoke"

    assert "MEMORII_RUN_LIVE_GATES" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "github.event_name == 'workflow_dispatch' ||" in workflow
    assert "replicate: [0, 1]" in workflow
    assert "--minimum-seed-count" in workflow
    assert "--minimum-scenarios-per-replicate" in workflow
    assert "--minimum-replicates-per-seed" in workflow
    assert "--allow-live" in workflow
    assert "Verify live provider configuration" in workflow
    assert "runtime.has_live_provider()" in workflow
    assert "live.should_run_live_llm_tests(runtime)" in workflow
    assert "LLMDecisionRuntimeConfig(mode='hybrid').resolve(runtime) == 'hybrid'" in workflow
    assert "ref: ${{ env.MEMORII_SOURCE_REVISION }}" in workflow
    assert 'test "$(git rev-parse HEAD)" = "$MEMORII_SOURCE_REVISION"' in workflow
    assert "Verify source-bound gate certificate" in workflow
    assert "summary.interval_coverage_certificate.configuration.source_revision" in workflow
    assert "from memorii.core.benchmark.calibration.gates import LiveGateSummary" in workflow


def test_live_certification_documentation_requires_default_branch_bootstrap() -> None:
    certification_doc = (
        REPO_ROOT / "docs" / "development" / "benchmark_certification.md"
    ).read_text(encoding="utf-8")

    assert "default branch" in certification_doc
    assert "credential-free bootstrap PR" in certification_doc
    assert "`.github/workflows/benchmark-scheduled.yml`" in certification_doc
    assert re.search(r"must not\s+contain provider secrets", certification_doc)


def test_pr_and_live_workflows_bind_reports_to_checked_out_revision() -> None:
    pr_workflow = (REPO_ROOT / ".github" / "workflows" / "pr-gates.yml").read_text(encoding="utf-8")
    live_workflow = (REPO_ROOT / ".github" / "workflows" / "benchmark-scheduled.yml").read_text(encoding="utf-8")
    certification_doc = (REPO_ROOT / "docs" / "development" / "benchmark_certification.md").read_text(encoding="utf-8")

    assert "MEMORII_SOURCE_REVISION: ${{ github.sha }}" in pr_workflow
    assert "MEMORII_SOURCE_REVISION: ${{ github.sha }}" in live_workflow
    assert "benchmark-certification-${{ github.sha }}" in live_workflow
    assert "source_revision:" not in live_workflow
    assert "github.event.inputs.source_revision" not in live_workflow
    assert "full commit SHA" in certification_doc
    assert "dirty working tree" in certification_doc
    assert "required branch protection" in certification_doc
    assert "pre-merge check" in certification_doc
    assert "gh workflow run benchmark-scheduled.yml --ref <pr-branch>" in certification_doc


def _workflow_steps(path: Path) -> list[tuple[str, str]]:
    workflow = path.read_text(encoding="utf-8")
    return re.findall(
        r"(?ms)^      - name: (?P<name>[^\n]+)\n(?P<body>.*?)(?=^      - name:|\Z)",
        workflow,
    )


def test_runtime_dry_runs_are_plumbing_gates_not_semantic_quality_gates() -> None:
    pr_steps = _workflow_steps(REPO_ROOT / ".github" / "workflows" / "pr-gates.yml")
    scheduled_steps = _workflow_steps(REPO_ROOT / ".github" / "workflows" / "benchmark-scheduled.yml")
    runtime_steps = [body for name, body in pr_steps if "runtime plumbing artifact" in name]
    simulator_steps = [body for name, body in pr_steps if "simulator plumbing artifact" in name]
    scheduled_runtime_steps = [
        body for name, body in scheduled_steps if "runtime plumbing artifact" in name
    ]

    assert len(runtime_steps) == 4
    assert len(simulator_steps) == 4
    assert len(scheduled_runtime_steps) == 1
    assert all("--fail-on-benchmark-failure" not in body for body in runtime_steps)
    assert all("--fail-on-benchmark-failure" not in body for body in scheduled_runtime_steps)
    assert all("--fail-on-benchmark-failure" in body for body in simulator_steps)
