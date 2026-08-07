from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from itertools import combinations
from pathlib import Path

import yaml
from memorii.tools.test_shards import collect_nodeids, load_config
from tools.extract_provider_compatibility_fixture import BASELINE_REVISION

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
    required_includes = {
        "memorii/core/belief",
        "memorii/core/benchmark/artifact_rows",
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
    }
    includes = pyright["include"]
    assert isinstance(includes, list)
    assert required_includes <= set(includes)


def test_prompt_contracts_are_owned_by_the_installable_package() -> None:
    package_prompt_root = PROJECT_ROOT / "memorii" / "prompts"

    assert package_prompt_root.is_dir()
    assert list(package_prompt_root.glob("**/*.yaml"))
    assert not (PROJECT_ROOT / "prompts").exists()
    package_data = _tool_config("setuptools")["package-data"]
    assert isinstance(package_data, dict)
    assert "prompts/**/*.yaml" in package_data["memorii"]


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
    assert set(jobs) == {
        "live-certification-policy",
        "fake-oracle-plumbing",
        "live-runtime-smoke",
        "live-runtime-gate",
    }
    policy_job = jobs["live-certification-policy"]
    assert isinstance(policy_job, dict)
    assert policy_job["name"] == "Resolve Live Certification Policy"
    assert policy_job["outputs"]["matrix"] == "${{ steps.policy.outputs.matrix }}"
    live_smoke = jobs["live-runtime-smoke"]
    assert isinstance(live_smoke, dict)
    assert live_smoke["needs"] == "live-certification-policy"
    assert live_smoke["timeout-minutes"] == "180"
    live_environment = live_smoke["env"]
    assert isinstance(live_environment, dict)
    assert live_environment["MEMORII_LLM_PROVIDER"] == "openai"
    assert live_environment["MEMORII_LLM_MODEL"] == "${{ vars.MEMORII_LLM_MODEL }}"
    assert live_environment["MEMORII_ENABLE_LIVE_LLM_TESTS"] == "true"
    assert live_environment["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    live_gate = jobs["live-runtime-gate"]
    assert isinstance(live_gate, dict)
    assert live_gate["name"] == "Live Runtime Statistical Gate"
    assert live_gate["needs"] == ["live-certification-policy", "live-runtime-smoke"]
    assert live_gate["timeout-minutes"] == "180"

    assert "MEMORII_RUN_LIVE_GATES" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "github.event_name == 'workflow_dispatch' ||" in workflow
    assert "live_certification_policy github-matrix" in workflow
    assert "live_certification_policy preflight" in workflow
    assert "live_certification_policy run-replicate" in workflow
    assert "--minimum-seed-count" not in workflow
    assert "--minimum-scenarios-per-replicate" not in workflow
    assert "--minimum-replicates-per-seed" not in workflow
    assert "Verify live provider configuration" in workflow
    assert "runtime.has_live_provider()" in workflow
    assert "assert runtime.model" in workflow
    assert "live.should_run_live_llm_tests(runtime)" in workflow
    assert "LLMDecisionRuntimeConfig(mode='hybrid').resolve(runtime) == 'hybrid'" in workflow
    assert "ref: ${{ env.MEMORII_SOURCE_REVISION }}" in workflow
    assert 'test "$(git rev-parse HEAD)" = "$MEMORII_SOURCE_REVISION"' in workflow
    assert "Verify source-bound gate certificate" in workflow
    assert "summary.interval_coverage_certificate.configuration.source_revision" in workflow
    assert "from memorii.core.benchmark.calibration.gates import LiveGateSummary" in workflow


def test_pr_and_live_workflows_bind_reports_to_checked_out_revision() -> None:
    pr_workflow = (REPO_ROOT / ".github" / "workflows" / "pr-gates.yml").read_text(encoding="utf-8")
    live_workflow = (REPO_ROOT / ".github" / "workflows" / "benchmark-scheduled.yml").read_text(encoding="utf-8")

    assert "MEMORII_SOURCE_REVISION: ${{ github.sha }}" in pr_workflow
    assert "MEMORII_SOURCE_REVISION: ${{ github.sha }}" in live_workflow
    assert "benchmark-certification-${{ github.sha }}" in live_workflow
    assert "source_revision:" not in live_workflow
    assert "github.event.inputs.source_revision" not in live_workflow


def test_candidate_live_gate_is_not_an_automatic_pr_or_merge_trigger() -> None:
    live_config = _workflow_config("benchmark-scheduled.yml")
    pr_config = _workflow_config("pr-gates.yml")

    assert set(live_config["on"]) == {"schedule", "workflow_dispatch"}
    assert set(pr_config["on"]) == {"pull_request", "merge_group"}


def test_pr_unit_gate_is_complete_duration_balanced_and_timeout_bounded() -> None:
    config = _workflow_config("pr-gates.yml")
    jobs = config["jobs"]
    shards = jobs["unit-test-shards"]
    compatibility = jobs["provider-compatibility"]
    umbrella = jobs["unit-tests"]
    timing = jobs["unit-timing-inventory"]

    assert shards["timeout-minutes"] == "15"
    assert shards["strategy"]["fail-fast"] == "false"
    shard_config = json.loads(
        (PROJECT_ROOT / "tests" / "ci" / "unit-shards.json").read_text(
            encoding="utf-8"
        )
    )
    assert shards["strategy"]["matrix"]["shard"] == [
        str(index) for index in range(shard_config["shard_count"])
    ]
    shard_run = next(step for step in shards["steps"] if step["name"] == "Run deterministic unit shard")
    assert "memorii.tools.test_shards run" in shard_run["run"]
    shard_timing_path = '${RUNNER_TEMP}/unit-shard-${{ matrix.shard }}-timings.json'
    assert f'--timing-output "{shard_timing_path}"' in shard_run["run"]
    shard_upload = next(step for step in shards["steps"] if step["name"] == "Upload shard timing evidence")
    assert shard_upload["with"]["name"] == "unit-shard-${{ matrix.shard }}-timings"
    assert shard_upload["with"]["path"] == "${{ runner.temp }}/unit-shard-${{ matrix.shard }}-timings.json"
    assert umbrella["name"] == "Unit Tests"
    assert umbrella["if"] == "always()"
    assert umbrella["needs"] == [
        "equal-version-replay-decision",
        "static-analysis",
        "package-smoke",
        "provider-compatibility",
        "unit-test-shards",
        "unit-timing-inventory",
        "semantic-terminal-persistence",
        "semantic-terminal-persistence-timing-inventory",
    ]
    umbrella_run = umbrella["steps"][0]
    expected_results = {
        "REPLAY_DECISION_RESULT": "equal-version-replay-decision",
        "STATIC_RESULT": "static-analysis",
        "PACKAGE_RESULT": "package-smoke",
        "COMPATIBILITY_RESULT": "provider-compatibility",
        "SHARD_RESULT": "unit-test-shards",
        "TIMING_RESULT": "unit-timing-inventory",
        "TERMINAL_RESULT": "semantic-terminal-persistence",
        "TERMINAL_TIMING_RESULT": "semantic-terminal-persistence-timing-inventory",
    }
    for variable, dependency in expected_results.items():
        assert umbrella_run["env"][variable] == f"${{{{ needs.{dependency}.result }}}}"
        assert f'test "${variable}" = success' in umbrella_run["run"]

    assert timing["needs"] == ["unit-test-shards"]
    timing_download = next(
        step for step in timing["steps"] if step["name"] == "Download shard timing evidence"
    )
    assert timing_download["uses"] == "actions/download-artifact@v4"
    assert timing_download["with"]["pattern"] == "unit-shard-*-timings"
    assert timing_download["with"]["path"] == "${{ runner.temp }}/unit-shard-timings"
    assert timing_download["with"]["merge-multiple"] == "true"
    timing_merge = next(step for step in timing["steps"] if step["name"] == "Merge timing inventory")
    assert "memorii.tools.test_shards merge" in timing_merge["run"]
    assert "--config tests/ci/unit-shards.json" in timing_merge["run"]
    assert '--input-dir "${RUNNER_TEMP}/unit-shard-timings"' in timing_merge["run"]
    assert '--output "${RUNNER_TEMP}/unit-test-durations.json"' in timing_merge["run"]
    timing_upload = next(
        step for step in timing["steps"] if step["name"] == "Upload complete timing inventory"
    )
    assert timing_upload["uses"] == "actions/upload-artifact@v4"
    assert timing_upload["with"]["name"] == "unit-test-timing-inventory"
    assert timing_upload["with"]["path"] == "${{ runner.temp }}/unit-test-durations.json"
    assert timing_upload["with"]["if-no-files-found"] == "error"
    assert compatibility["name"] == "Provider Compatibility Recapture"
    compatibility_checkout = compatibility["steps"][0]
    assert compatibility_checkout["name"] == "Checkout"
    assert compatibility_checkout["uses"] == "actions/checkout@v4"
    compatibility_fetch_index, compatibility_fetch = next(
        (index, step)
        for index, step in enumerate(compatibility["steps"])
        if step["name"] == "Fetch pinned provider compatibility baseline"
    )
    assert compatibility_fetch["working-directory"] == "memorii"
    assignments = re.findall(
        r"BASELINE_REVISION=\"\$\(python -c '([^']+)'\)\"",
        compatibility_fetch["run"],
    )
    assert len(assignments) == 1
    completed = subprocess.run(
        [sys.executable, "-c", assignments[0]],
        cwd=REPO_ROOT / compatibility_fetch["working-directory"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == BASELINE_REVISION
    assert 'git fetch --no-tags --depth=1 origin "$BASELINE_REVISION"' in compatibility_fetch["run"]
    assert 'git cat-file -e "$BASELINE_REVISION^{commit}"' in compatibility_fetch["run"]
    compatibility_run = next(
        step for step in compatibility["steps"]
        if step["name"] == "Verify deterministic historical provider recapture"
    )
    assert compatibility_fetch_index < compatibility["steps"].index(compatibility_run)
    assert "tests/integration/semantic_ingestion/test_provider_compatibility_recapture.py" in compatibility_run["run"]

    bounded_jobs = [
        "static-analysis",
        "package-smoke",
        "provider-compatibility",
        "unit-test-shards",
        "unit-timing-inventory",
        "unit-tests",
        "semantic-ingestion-generation",
        "semantic-projection-history",
        "semantic-ingestion",
        "semantic-ingestion-scenario",
        "semantic-ingestion-acceptance",
        "benchmark-contract-tests",
        "benchmark-artifacts",
        "benchmark-contracts",
    ]
    assert all(int(jobs[name]["timeout-minutes"]) <= 15 for name in bounded_jobs)
    assert jobs["benchmark-contracts"]["name"] == "Benchmark Contracts"
    assert jobs["benchmark-contracts"]["needs"] == ["benchmark-contract-tests", "benchmark-artifacts"]


def test_terminal_persistence_job_is_exact_node_balanced_and_disjoint() -> None:
    config = _workflow_config("pr-gates.yml")
    job = config["jobs"]["semantic-terminal-persistence"]
    timing = config["jobs"]["semantic-terminal-persistence-timing-inventory"]
    terminal_path = "tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py"
    shard_config_path = "tests/ci/semantic-terminal-persistence-shards.json"
    shard_config = json.loads(
        (PROJECT_ROOT / shard_config_path).read_text(encoding="utf-8")
    )

    assert shard_config["assignment_scope"] == "node"
    assert shard_config["pytest_args"] == [terminal_path]
    assert shard_config["shard_count"] == 7
    assert shard_config["target_seconds"] == 600
    assert job["timeout-minutes"] == "15"
    assert job["strategy"]["matrix"]["shard"] == ["0", "1", "2", "3", "4", "5", "6"]
    count_command = next(
        step["run"]
        for step in job["steps"]
        if step["name"] == "Verify exact terminal-persistence collection count"
    )
    assert count_command.count(terminal_path) == 1
    assert '"156 tests collected in "*' in count_command
    run_command = next(
        step["run"]
        for step in job["steps"]
        if step["name"] == "Run exact terminal-persistence shard"
    )
    assert f"--config {shard_config_path}" in run_command
    assert "--index ${{ matrix.shard }}" in run_command
    assert timing["needs"] == ["semantic-terminal-persistence"]
    merge_command = next(
        step["run"]
        for step in timing["steps"]
        if step["name"] == "Merge terminal-persistence timing inventory"
    )
    assert f"--config {shard_config_path}" in merge_command

    broad_config = json.loads(
        (PROJECT_ROOT / "tests" / "ci" / "unit-shards.json").read_text(
            encoding="utf-8"
        )
    )
    assert broad_config["assignment_scope"] == "file"
    assert f"--ignore={terminal_path}" in broad_config["pytest_args"]
    assert (
        "--ignore=tests/unit/core/semantic_ingestion/test_provider_compatibility.py"
        in broad_config["pytest_args"]
    )


def test_unit_pytest_owners_partition_the_live_unit_corpus_exactly_once() -> None:
    broad_config = load_config(PROJECT_ROOT / "tests" / "ci" / "unit-shards.json")
    full = set(collect_nodeids(("tests/unit",), cwd=PROJECT_ROOT))
    broad = set(collect_nodeids(broad_config.pytest_args, cwd=PROJECT_ROOT))
    owner_paths = {
        "generation-closure-exactness": (
            "tests/unit/tools/test_generation_closure_exactness.py",
        ),
        "scenario-fixture-authority": (
            "tests/unit/tools/test_scenario_fixture_authority.py",
        ),
        "projection-history": (
            "tests/unit/core/test_projection_history.py",
            "tests/unit/core/semantic_ingestion/test_projection_scheduler.py",
            "tests/unit/core/semantic_ingestion/test_policy_migration.py",
            "tests/unit/core/semantic_ingestion/test_identity_lineage.py",
            "tests/unit/core/semantic_ingestion/test_graph_planning.py",
            "tests/unit/core/semantic_ingestion/test_identity_lineage_prerequisites.py",
        ),
        "terminal-persistence": (
            "tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py",
        ),
        "provider-compatibility": (
            "tests/unit/core/semantic_ingestion/test_provider_compatibility.py",
        ),
    }
    owners = {"broad": broad}
    for owner, paths in owner_paths.items():
        owners[owner] = {
            nodeid
            for nodeid in full
            if any(nodeid.startswith(f"{path}::") for path in paths)
        }

    assert all(nodes for nodes in owners.values())
    for (left_name, left), (right_name, right) in combinations(owners.items(), 2):
        assert left.isdisjoint(right), f"overlap between {left_name} and {right_name}"
    assert set().union(*owners.values()) == full

    terminal = owners["terminal-persistence"]
    terminal_manifest = json.loads(
        (
            PROJECT_ROOT
            / "tests"
            / "ci"
            / "semantic-terminal-persistence-test-durations.json"
        ).read_text(encoding="utf-8")
    )
    assert len(terminal) == 156
    assert set(terminal_manifest["tests"]) == terminal


def test_repository_workflow_skills_share_fail_closed_closure_contract() -> None:
    root_names = {path.name for path in REPO_ROOT.iterdir()}
    assert "AGENTS.md" in root_names
    assert "agents.md" not in root_names

    plans = (REPO_ROOT / ".agents" / "PLANS.md").read_text(encoding="utf-8")
    required_common_fields = {
        "remaining_validated_p1_p2: []",
        "remaining_blocks_approval: []",
        "remaining_changes_required: []",
        "ci_executed_sha:",
        "ci_executed_ref:",
        "acceptance_gate_inventory: []",
    }
    assert required_common_fields <= set(plans.splitlines())

    required_skill_tokens = {
        "implement-design": ["remaining_validated_p1_p2: []", "merge-group SHAs"],
        "debug-problem": ["remaining_validated_p1_p2: []", "external acceptance gates"],
        "design-tests": ["remaining_validated_p1_p2: []", "owner-or-exemption ledger"],
        "review-pr": ["merge_group", "acceptance-gate inventory", "cannot be retrieved authoritatively"],
    }
    for skill_name, tokens in required_skill_tokens.items():
        skill_path = REPO_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        assert all(token in content for token in tokens), skill_name

    review_skill = (
        REPO_ROOT / ".agents" / "skills" / "review-pr" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "passes on its actual\n  current executed ref" in review_skill
    assert "required checks pass on the head" not in review_skill
    for decision_token in (
        "decision table as normative precedence",
        "Do not downgrade `blocked`",
        "unavailable or forbidden | `blocked`",
        "stale or mismatched executed SHA/ref | `blocked`",
        "skipped, neutral, or incomplete | `changes_required`",
        "thread remains unresolved | `changes_required`",
    ):
        assert decision_token in review_skill
    plans_template = re.search(r"For every milestone or final closure.*?```yaml\n(.*?)\n```", plans, re.DOTALL)
    review_template = re.search(r"Record:\n\n```yaml\n(.*?)\n```", review_skill, re.DOTALL)
    assert plans_template is not None
    assert review_template is not None
    common_keys = set(yaml.load(plans_template.group(1), Loader=yaml.BaseLoader))
    review_keys = set(yaml.load(review_template.group(1), Loader=yaml.BaseLoader))
    assert common_keys <= review_keys
    assert {"unresolved_review_threads", "decision"} <= review_keys


def test_dedicated_deterministic_pytest_jobs_have_timing_owners_or_exemptions() -> None:
    config = _workflow_config("pr-gates.yml")
    jobs = config["jobs"]
    observed_jobs = {
        job_name
        for job_name, job in jobs.items()
        if job_name != "unit-test-shards"
        if any(
            "pytest" in step.get("run", "")
            and "pip install" not in step.get("run", "")
            for step in job.get("steps", [])
        )
    }
    ledger = json.loads(
        (PROJECT_ROOT / "tests" / "ci" / "deterministic-job-owners.json").read_text(
            encoding="utf-8"
        )
    )["dedicated_pytest_jobs"]

    assert set(ledger) == observed_jobs
    for job_name, entry in ledger.items():
        timeout_seconds = int(jobs[job_name]["timeout-minutes"]) * 60
        assert entry["timeout_minutes"] * 60 == timeout_seconds
        assert entry["runtime_budget_seconds"] > 0
        assert entry["timeout_headroom_seconds"] > 0
        assert entry["runtime_budget_seconds"] + entry["timeout_headroom_seconds"] <= timeout_seconds
        assert entry["timing_exemption_reason"].strip()


def test_exact_semantic_ingestion_workflow_argv_is_pinned() -> None:
    config = _workflow_config("pr-gates.yml")
    steps = config["jobs"]["semantic-ingestion-generation"]["steps"]
    command = next(
        step["run"]
        for step in steps
        if step["name"] == "Run exact semantic ingestion integration and process closure"
    )
    assert command.split() == [
        "pytest",
        "-W",
        "error",
        "tests/integration/test_semantic_ingestion_pipeline.py",
        "tests/integration/test_semantic_ingestion_process_safety.py",
        "tests/integration/test_conflict_attention_persistence.py",
        "tests/integration/test_semantic_ingestion_replay.py",
        "-p",
        "no:cacheprovider",
    ]
    count_command = next(
        step["run"]
        for step in steps
        if step["name"] == "Verify exact semantic ingestion collection count"
    )
    assert '"34 tests collected in "*' in count_command
    assert count_command.count("tests/integration/test_semantic_ingestion_pipeline.py") == 1
    assert count_command.count("tests/integration/test_semantic_ingestion_process_safety.py") == 1
    assert count_command.count("tests/integration/test_conflict_attention_persistence.py") == 1
    assert count_command.count("tests/integration/test_semantic_ingestion_replay.py") == 1


def test_projection_history_job_is_exact_and_disjoint_from_broad_unit_shards() -> None:
    config = _workflow_config("pr-gates.yml")
    steps = config["jobs"]["semantic-projection-history"]["steps"]
    command = next(step["run"] for step in steps if step["name"] == "Run exact projection-history closure")
    expected_files = [
        "tests/unit/core/test_projection_history.py",
        "tests/unit/core/semantic_ingestion/test_projection_scheduler.py",
        "tests/unit/core/semantic_ingestion/test_policy_migration.py",
        "tests/unit/core/semantic_ingestion/test_identity_lineage.py",
        "tests/unit/core/semantic_ingestion/test_graph_planning.py",
        "tests/unit/core/semantic_ingestion/test_identity_lineage_prerequisites.py",
    ]
    assert command.split() == ["pytest", "-W", "error", *expected_files, "-p", "no:cacheprovider"]
    count_command = next(
        step["run"] for step in steps if step["name"] == "Verify exact projection-history collection count"
    )
    assert '"84 tests collected in "*' in count_command
    assert all(count_command.count(path) == 1 for path in expected_files)

    shard_config = json.loads((PROJECT_ROOT / "tests" / "ci" / "unit-shards.json").read_text())
    shard_args = set(shard_config["pytest_args"])
    assert {f"--ignore={path}" for path in expected_files} <= shard_args

    generation_command = next(
        step["run"]
        for step in config["jobs"]["semantic-ingestion-generation"]["steps"]
        if step["name"] == "Run exact semantic ingestion integration and process closure"
    )
    assert all(path not in generation_command for path in expected_files)

    semantic_umbrella = config["jobs"]["semantic-ingestion"]
    assert semantic_umbrella["name"] == "Semantic Ingestion"
    assert semantic_umbrella["if"] == "always()"
    expected_dependencies = {
        "GENERATION_RESULT": "semantic-ingestion-generation",
        "SCENARIO_RESULT": "semantic-ingestion-scenario",
        "ACCEPTANCE_RESULT": "semantic-ingestion-acceptance",
        "PROJECTION_HISTORY_RESULT": "semantic-projection-history",
    }
    assert set(semantic_umbrella["needs"]) == set(expected_dependencies.values())
    umbrella_step = semantic_umbrella["steps"][0]
    for variable, dependency in expected_dependencies.items():
        assert umbrella_step["env"][variable] == f"${{{{ needs.{dependency}.result }}}}"
        assert f'test "${variable}" = success' in umbrella_step["run"]


def test_test_symbols_use_behavioral_names() -> None:
    identifier_name = re.compile(
        r"^(?:async )?def test_(?:.*_(?:r|m|t|c|p)\d+(?:_|\()|sia_[a-z]\d+(?:_|\())",
        re.IGNORECASE,
    )
    violations: list[str] = []
    for path in sorted((PROJECT_ROOT / "tests").rglob("*.py")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if identifier_name.match(line):
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{line_number}:{line.strip()}")
    assert violations == []


def test_static_analysis_owns_exact_behavioral_identity_command() -> None:
    config = _workflow_config("pr-gates.yml")
    steps = config["jobs"]["static-analysis"]["steps"]
    step = next(item for item in steps if item["name"] == "Verify behavioral identity hygiene")
    assert step["working-directory"] == "memorii"
    assert step["run"].split() == [
        "python",
        "-m",
        "memorii.tools.identity_hygiene",
        "--root",
        "..",
        "--allowlist",
        "../.agents/identity_hygiene_allowlist.json",
    ]


def test_provider_recapture_documentation_matches_exact_pinned_fetch_contract() -> None:
    documentation = (REPO_ROOT / "docs" / "development" / "static_tooling.md").read_text(encoding="utf-8")
    assert "fetch the tool-owned baseline SHA" in documentation
    assert "`--depth=1`" in documentation
    assert "verify that the fetched object is a commit" in documentation
    assert "fetch-depth: 0" not in documentation
    assert "provider compatibility\nrecapture" in documentation
    assert "both merged timing inventories" in documentation
    assert "seven exact-node\nterminal-persistence shards" in documentation


def _workflow_steps(path: Path) -> list[tuple[str, str]]:
    workflow = path.read_text(encoding="utf-8")
    return re.findall(
        r"(?ms)^      - name: (?P<name>[^\n]+)\n(?P<body>.*?)(?=^      - name:|\Z)",
        workflow,
    )


def test_runtime_dry_runs_separate_plumbing_from_semantic_quality_gates() -> None:
    pr_config = _workflow_config("pr-gates.yml")
    scheduled_steps = _workflow_steps(REPO_ROOT / ".github" / "workflows" / "benchmark-scheduled.yml")
    scheduled_semantic_runtime_steps = [body for name, body in scheduled_steps if "runtime semantic artifact" in name]
    artifact_job = pr_config["jobs"]["benchmark-artifacts"]
    matrix = artifact_job["strategy"]["matrix"]["include"]
    runtime_rows = [row for row in matrix if row["suite"] == "memory_evolution_runtime_v1"]
    simulator_rows = [row for row in matrix if row["suite"] == "memory_evolution_sim_v1"]
    artifact_step = next(step for step in artifact_job["steps"] if step["name"] == "Build deterministic benchmark artifact")

    assert len(runtime_rows) == 4
    assert len(simulator_rows) == 4
    assert {row["profile"] for row in runtime_rows} == {"long_horizon", "adversarial"}
    assert {row["mode"] for row in runtime_rows} == {"llm", "hybrid"}
    assert "tests.support.run_memory_evolution_runtime_benchmark" in artifact_step["run"]
    assert "--fail-on-benchmark-failure" in artifact_step["run"]
    assert len(scheduled_semantic_runtime_steps) == 0
