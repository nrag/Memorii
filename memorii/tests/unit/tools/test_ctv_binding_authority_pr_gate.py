"""Black-box coverage for the pinned Layer-1 CTV PR gate."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[4]
PROJECT = ROOT / "memorii"
VECTORS = ROOT / "docs" / "design" / "semantic_ingestion" / "traceability_golden_vectors"
DESIGN = ROOT / "docs" / "design" / "semantic_ingestion_architecture.md"
REGISTRY = ROOT / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"
AUTHORITY = VECTORS / "ctv-binding-authority-v2.json"
VALIDATOR = VECTORS / "validate_ctv_binding_authority_v2.py"
CHECKER = VECTORS / "check_ctv_binding_authority_v2.py"
STATIC_TOOLING = ROOT / "docs" / "development" / "static_tooling.md"
WORKFLOW = ROOT / ".github" / "workflows" / "pr-gates.yml"
SEMANTIC_FIXTURE = VECTORS / "lifecycle-root-signer-provenance-witness-v1.json"
SEMANTIC_VALIDATOR = VECTORS / "validate_lifecycle_root_signer_provenance_v1.py"
SEMANTIC_CHECKER = VECTORS / "check_lifecycle_root_signer_provenance_v1.py"
STRUCTURAL_CHECKER = VECTORS / "check_cgs_structural_contract_v1.py"
SEMANTIC_EXPECTED = {
    "fixture": "d3c1dce10624365647cbb00926f63b6deabe681e51a138bc3de88d7c60faef69",
    "validator": "46bbda1afb6ccbec5a49ea668752c19a7b1354b94515a33365191cee01745edb",
    "checker": "1d618a7e8072cf2a5c95258538bee4ad0fe2646000e0ac4127fc380c9444ab22",
}
STRUCTURAL_CHECKER_SHA256 = "3f5ba86e4cc26b7c6b0d518fb8a073ebf7db68a2858afada78dd242b699c826e"
EXPECTED = {
    "design": "2923340bc6417d516983714e5fe69b7bab0f2257652d28a043cfb273b53aaed3",
    "registry": "8c5ad6e6260c793472ddbc2df8637230fbb5d5b28405b0b558ac4491c945d37e",
    "authority": "c4fbd524c6b7c20795f42977aed458248754c04a0b9635ef0dd3e366bd829b0e",
    "validator": "826541e7864583bbe3c32e3f153c008f07a881f33d38861237dfac80d9f3657e",
    "checker": "e2c35870a99e587f34cbffc701f42587520ee015009cd51647367da56716c732",
}


def _command(
    design: Path = DESIGN,
    registry: Path = REGISTRY,
    authority: Path = AUTHORITY,
    validator: Path = VALIDATOR,
    checker: Path = CHECKER,
    *,
    expected_authority_sha256: str = EXPECTED["authority"],
) -> list[str]:
    return [
        "python3.12",
        "-I",
        str(checker),
        "--design",
        str(design),
        "--registry",
        str(registry),
        "--authority",
        str(authority),
        "--validator",
        str(validator),
        "--expected-design-sha256",
        EXPECTED["design"],
        "--expected-registry-sha256",
        EXPECTED["registry"],
        "--expected-authority-sha256",
        expected_authority_sha256,
        "--expected-validator-sha256",
        EXPECTED["validator"],
        "--expected-checker-sha256",
        EXPECTED["checker"],
    ]


def _first_bash_command(document: str) -> list[str]:
    begin = "```bash\n"
    start = document.find(begin)
    assert start >= 0
    end = document.find("```", start + len(begin))
    assert end >= 0
    command = document[start + len(begin) : end].replace("\\\n", " ")
    return shlex.split(command)


def _bash_commands(document: str) -> list[list[str]]:
    return [
        shlex.split(match.group(1).replace("\\\n", " "))
        for match in re.finditer(r"```bash\n(.*?)```", document, flags=re.DOTALL)
    ]


def _contains_token_sequence(commands: list[list[str]], expected: list[str]) -> bool:
    return any(
        command[start : start + len(expected)] == expected
        for command in commands
        for start in range(len(command) - len(expected) + 1)
    )


def _mutate_first_bash_command(document: str, fragment: str) -> str:
    begin = "```bash\n"
    start = document.find(begin)
    end = document.find("```", start + len(begin))
    command = document[start + len(begin) : end]
    assert command.count(fragment) == 1
    return document[: start + len(begin)] + command.replace(fragment, fragment + "-drift", 1) + document[end:]


def test_pinned_gate_command_is_hermetic_and_identity_complete() -> None:
    assert _command()[:2] == ["python3.12", "-I"]
    assert hashlib.sha256(AUTHORITY.read_bytes()).hexdigest() == EXPECTED["authority"]


def test_lifecycle_root_semantic_gate_pins_checker_and_isolation() -> None:
    assert hashlib.sha256(SEMANTIC_FIXTURE.read_bytes()).hexdigest() == SEMANTIC_EXPECTED["fixture"]
    assert hashlib.sha256(SEMANTIC_VALIDATOR.read_bytes()).hexdigest() == SEMANTIC_EXPECTED["validator"]
    assert hashlib.sha256(SEMANTIC_CHECKER.read_bytes()).hexdigest() == SEMANTIC_EXPECTED["checker"]
    required = (
        "python3.12 -I",
        "--expected-checker-sha256 " + SEMANTIC_EXPECTED["checker"],
        str(SEMANTIC_FIXTURE.relative_to(ROOT)),
        str(SEMANTIC_VALIDATOR.relative_to(ROOT)),
    )
    for path in (STATIC_TOOLING, WORKFLOW):
        document = path.read_text(encoding="utf-8")
        assert all(token in document for token in required)


def test_structural_checker_rejects_source_drift_and_nonisolated_startup(tmp_path: Path) -> None:
    assert hashlib.sha256(STRUCTURAL_CHECKER.read_bytes()).hexdigest() == STRUCTURAL_CHECKER_SHA256
    arguments = [
        "--design",
        str(DESIGN),
        "--registry",
        str(REGISTRY),
        "--ledger",
        str(VECTORS / "structural_manifest_derivation_ledger-v1.json"),
        "--matrix",
        str(VECTORS / "cgs_verification_attack_matrix-v1.json"),
        "--prototype",
        str(VECTORS / "cgs_structural_manifest_prototype.py"),
        "--vector",
        str(VECTORS / "cgs-structural-manifest-prototype-v1.json"),
        "--expected-checker-sha256",
        STRUCTURAL_CHECKER_SHA256,
    ]
    nonisolated = subprocess.run(
        ["python3.12", str(STRUCTURAL_CHECKER), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert nonisolated.returncode != 0
    assert "requires isolated Python" in nonisolated.stderr + nonisolated.stdout

    changed_checker = tmp_path / STRUCTURAL_CHECKER.name
    changed_checker.write_bytes(STRUCTURAL_CHECKER.read_bytes() + b"\n")
    drifted = subprocess.run(
        ["python3.12", "-I", str(changed_checker), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert drifted.returncode != 0
    assert "checker SHA-256 mismatch" in drifted.stderr + drifted.stdout


@pytest.mark.parametrize(
    "fragment",
    (
        "--expected-design-sha256 " + EXPECTED["design"],
        "--expected-registry-sha256 " + EXPECTED["registry"],
        "--expected-authority-sha256 " + EXPECTED["authority"],
        "--expected-validator-sha256 " + EXPECTED["validator"],
        "--expected-checker-sha256 " + EXPECTED["checker"],
        "--design docs/design/semantic_ingestion_architecture.md",
        "--registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json",
        "--authority docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json",
        "--validator docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py",
        "python3.12 -I",
    ),
)
def test_static_tooling_checker_command_rejects_each_required_token_mutation(fragment: str) -> None:
    document = STATIC_TOOLING.read_text(encoding="utf-8")
    mutated = _mutate_first_bash_command(document, fragment)
    assert _first_bash_command(mutated) != _command()


@pytest.mark.parametrize("target", ["design", "registry", "authority", "validator", "checker"])
def test_pinned_gate_fails_closed_when_a_source_identity_drifts(tmp_path: Path, target: str) -> None:
    sources = {
        "design": DESIGN,
        "registry": REGISTRY,
        "authority": AUTHORITY,
        "validator": VALIDATOR,
        "checker": CHECKER,
    }
    copies = {name: tmp_path / path.name for name, path in sources.items()}
    for name, source in sources.items():
        shutil.copyfile(source, copies[name])
    copies[target].write_bytes(copies[target].read_bytes() + b" ")
    completed = subprocess.run(
        _command(
            copies["design"],
            copies["registry"],
            copies["authority"],
            copies["validator"],
            copies["checker"],
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "SHA-256 mismatch" in completed.stderr


def test_pinned_gate_rejects_semantic_authority_tampering_after_identity_check(
    tmp_path: Path,
) -> None:
    authority = json.loads(AUTHORITY.read_bytes())
    authority["schemas"][0]["binding_digest"] = "0" * 64
    changed = tmp_path / "authority.json"
    changed.write_text(
        json.dumps(authority, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    expected_authority_sha256 = hashlib.sha256(changed.read_bytes()).hexdigest()
    completed = subprocess.run(
        _command(
            authority=changed,
            expected_authority_sha256=expected_authority_sha256,
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "authority SHA-256 mismatch" not in completed.stderr


def test_pr_workflow_structurally_runs_complete_matrix_and_exact_pinned_checker() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "pr-gates.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    trigger = workflow[True] if True in workflow else workflow["on"]
    assert trigger == {"pull_request": {"branches": ["main"]}, "merge_group": {"branches": ["main"]}}
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    compiler_job = jobs["ctv-binding-authority-compiler-parity"]
    gate_job = jobs["ctv-binding-authority-pr-gate"]
    exact_job = jobs["ctv-binding-authority-exact"]
    unit_job = jobs["unit-tests"]
    acceptance_job = jobs["semantic-ingestion-acceptance"]
    generation_job = jobs["semantic-ingestion-generation"]
    scenario_job = jobs["semantic-ingestion-scenario"]
    assert isinstance(compiler_job, dict)
    assert isinstance(gate_job, dict)
    assert isinstance(exact_job, dict)
    assert isinstance(unit_job, dict)
    assert isinstance(acceptance_job, dict)
    assert compiler_job["name"] == "CTV Binding Authority Compiler Parity"
    assert gate_job["name"] == "CTV Binding Authority PR Gate"
    assert exact_job["name"] == "CTV Binding Authority Exact"
    assert acceptance_job["name"] == "Semantic Ingestion Acceptance"
    assert acceptance_job["runs-on"] == "ubuntu-latest"
    assert acceptance_job["timeout-minutes"] == "15"
    assert generation_job["timeout-minutes"] == "15"
    assert scenario_job["timeout-minutes"] == "15"
    assert unit_job["name"] == "Unit Tests"
    assert unit_job["needs"] == [
        "static-analysis",
        "package-smoke",
        "provider-compatibility",
        "unit-test-shards",
        "unit-timing-inventory",
    ]
    for job in (compiler_job, gate_job, exact_job):
        assert job["runs-on"] == "ubuntu-latest"
        assert job["timeout-minutes"] == "5"

    compiler_steps = compiler_job["steps"]
    assert [step.get("name") for step in compiler_steps] == [
        "Checkout",
        "Set up Python",
        "Install compiler parity dependencies",
        "Run independent CTV compiler parity",
    ]
    assert compiler_steps[1]["with"]["python-version"] == "3.12"
    assert compiler_steps[2]["run"] == "python3.12 -m pip install 'pytest>=8,<10'"
    compiler_run = compiler_steps[3]
    assert compiler_run["working-directory"] == "memorii"
    assert shlex.split(compiler_run["run"]) == [
        "python3.12",
        "-m",
        "pytest",
        "-W",
        "error",
        "tests/unit/tools/test_semantic_ingestion_ctv_reference_compiler.py",
        "-p",
        "no:cacheprovider",
    ]

    gate_steps = gate_job["steps"]
    assert [step.get("name") for step in gate_steps] == [
        "Checkout",
        "Set up Python",
        "Install PR-gate test dependencies",
        "Run CTV PR-gate tamper tests",
    ]
    assert gate_steps[1]["with"]["python-version"] == "3.12"
    assert gate_steps[2]["run"] == (
        "python3.12 -m pip install 'pytest>=8,<10' 'PyYAML>=6,<7'"
    )
    gate_run = gate_steps[3]
    assert gate_run["working-directory"] == "memorii"
    assert shlex.split(gate_run["run"]) == [
        "python3.12",
        "-m",
        "pytest",
        "-W",
        "error",
        "tests/unit/tools/test_ctv_binding_authority_pr_gate.py",
        "-p",
        "no:cacheprovider",
    ]
    forbidden_selectors = {"-k", "--deselect", "--ignore", "--ignore-glob", "-m"}
    assert not forbidden_selectors.intersection(shlex.split(compiler_run["run"])[3:])
    assert not forbidden_selectors.intersection(shlex.split(gate_run["run"])[3:])
    acceptance_steps = [
        step
        for step in acceptance_job["steps"]
        if step.get("name") == "Run semantic ingestion public acceptance"
    ]
    assert len(acceptance_steps) == 1
    acceptance_run = acceptance_steps[0]
    assert acceptance_run["working-directory"] == "memorii"
    acceptance_tokens = shlex.split(acceptance_run["run"])
    assert acceptance_tokens == [
        "pytest",
        "-W",
        "error",
        "tests/acceptance/semantic_ingestion/test_sia_requirements.py",
        "-p",
        "no:cacheprovider",
    ]
    assert not forbidden_selectors.intersection(acceptance_tokens)
    generation_run = next(
        step for step in generation_job["steps"] if step.get("name") == "Run generation closure acceptance"
    )
    scenario_run = next(
        step for step in scenario_job["steps"] if step.get("name") == "Run scenario authority acceptance"
    )
    assert "tests/unit/tools/test_generation_closure_exactness.py" in shlex.split(generation_run["run"])
    assert "tests/unit/tools/test_scenario_fixture_authority.py" in shlex.split(scenario_run["run"])
    exact_steps = exact_job["steps"]
    assert [step.get("name") for step in exact_steps] == [
        "Checkout",
        "Set up Python",
        "Verify pinned CTV binding authority",
        "Verify lifecycle-root signer provenance semantics",
        "Verify structural manifest contract",
    ]
    assert exact_steps[1]["with"]["python-version"] == "3.12"
    checker_command = exact_steps[2]["run"]
    expected_arguments = {
        "--design": "docs/design/semantic_ingestion_architecture.md",
        "--registry": "docs/design/semantic_ingestion/traceability_registry/registry-v1.json",
        "--authority": "docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json",
        "--validator": "docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py",
        "--expected-design-sha256": EXPECTED["design"],
        "--expected-registry-sha256": EXPECTED["registry"],
        "--expected-authority-sha256": EXPECTED["authority"],
        "--expected-validator-sha256": EXPECTED["validator"],
        "--expected-checker-sha256": EXPECTED["checker"],
    }
    tokens = shlex.split(checker_command)
    assert tokens[:3] == [
        "python3.12",
        "-I",
        "docs/design/semantic_ingestion/traceability_golden_vectors/check_ctv_binding_authority_v2.py",
    ]
    assert len(tokens) == 3 + 2 * len(expected_arguments)
    for option, value in expected_arguments.items():
        index = tokens.index(option)
        assert tokens[index + 1] == value
    assert _first_bash_command(STATIC_TOOLING.read_text(encoding="utf-8")) == tokens
    semantic_tokens = shlex.split(exact_steps[3]["run"])
    assert semantic_tokens == [
        "python3.12",
        "-I",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "check_lifecycle_root_signer_provenance_v1.py",
        "--design",
        "docs/design/semantic_ingestion_architecture.md",
        "--matrix",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "cgs_verification_attack_matrix-v1.json",
        "--fixture",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "lifecycle-root-signer-provenance-witness-v1.json",
        "--validator",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "validate_lifecycle_root_signer_provenance_v1.py",
        "--expected-checker-sha256",
        SEMANTIC_EXPECTED["checker"],
        "--self-test",
    ]
    assert semantic_tokens in _bash_commands(STATIC_TOOLING.read_text(encoding="utf-8"))
    structural_tokens = shlex.split(exact_steps[4]["run"])
    assert structural_tokens == [
        "python3.12",
        "-I",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "check_cgs_structural_contract_v1.py",
        "--design",
        "docs/design/semantic_ingestion_architecture.md",
        "--registry",
        "docs/design/semantic_ingestion/traceability_registry/registry-v1.json",
        "--ledger",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "structural_manifest_derivation_ledger-v1.json",
        "--matrix",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "cgs_verification_attack_matrix-v1.json",
        "--prototype",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "cgs_structural_manifest_prototype.py",
        "--vector",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "cgs-structural-manifest-prototype-v1.json",
        "--expected-checker-sha256",
        STRUCTURAL_CHECKER_SHA256,
        "--self-test",
    ]
    assert _contains_token_sequence(
        _bash_commands(STATIC_TOOLING.read_text(encoding="utf-8")), structural_tokens
    )
    prototype_tokens = [
        "python3.12",
        "-I",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "cgs_structural_manifest_prototype.py",
        "docs/design/semantic_ingestion_architecture.md",
        "docs/design/semantic_ingestion/traceability_registry/registry-v1.json",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "structural_manifest_derivation_ledger-v1.json",
        "docs/design/semantic_ingestion/traceability_golden_vectors/"
        "cgs-structural-manifest-prototype-v1.json",
        "--verify",
    ]
    assert _contains_token_sequence(
        _bash_commands(STATIC_TOOLING.read_text(encoding="utf-8")), prototype_tokens
    )
