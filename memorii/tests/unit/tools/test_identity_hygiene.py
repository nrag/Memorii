from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.tools.identity_hygiene import scan_repository

REPO_ROOT = Path(__file__).parents[4]
_COORDINATE_CASES = (
    ("M1", "M1Owner", "m1-owner", "m1_owner"),
    ("M2", "M2Owner", "m2-owner", "m2_owner"),
    ("M3", "M3Owner", "m3-owner", "m3_owner"),
    ("C2", "ScenarioC2Owner", "scenario-c2-owner", "scenario_c2_owner"),
    ("R22", "R22Owner", "r22-owner", "r22_owner"),
    ("SIA-R22", "SIA_R22_OWNER", "sia-r22-owner", "sia_r22_owner"),
)
_MUTATION_SURFACES = (
    "production_identifier",
    "test_identifier",
    "identity_fstring",
    "import_path",
    "imported_symbol",
    "import_alias",
    "runtime_diagnostic",
    "diagnostic_keyword",
    "assertion_diagnostic",
    "design_generator",
    "nested_repository_path",
    "structured_fixture",
    "bare_python_id",
    "bare_json_id",
    "bare_yaml_id",
    "yaml_config",
    "workflow_step_name",
    "workflow_job_key",
)


def _root(tmp_path: Path) -> tuple[Path, Path]:
    for relative in (
        "memorii/memorii",
        "memorii/tests",
        "docs/design",
        ".github/workflows",
        ".agents",
    ):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    allowlist = tmp_path / ".agents/identity_hygiene_allowlist.json"
    allowlist.write_text('{"exceptions":[],"version":1}\n', encoding="utf-8")
    return tmp_path, allowlist


def _write_mutation(
    root: Path,
    *,
    surface: str,
    identifier: str,
    value: str,
    module: str,
) -> str:
    if surface == "production_identifier":
        relative, content = "memorii/memorii/example.py", f"class {identifier}:\n    pass\n"
    elif surface == "test_identifier":
        relative, content = "memorii/tests/test_example.py", f"def test_{module}():\n    pass\n"
    elif surface == "identity_fstring":
        relative, content = "memorii/memorii/example.py", f'SCHEMA = f"{value}-{{suffix}}"\n'
    elif surface == "import_path":
        relative, content = "memorii/memorii/example.py", f"import memorii.{module}\n"
    elif surface == "imported_symbol":
        relative, content = "memorii/memorii/example.py", f"from memorii.clean import {identifier}\n"
    elif surface == "import_alias":
        relative, content = "memorii/memorii/example.py", f"import memorii.clean as {identifier}\n"
    elif surface == "runtime_diagnostic":
        relative, content = "memorii/memorii/example.py", f'raise ValueError("failed {value}")\n'
    elif surface == "diagnostic_keyword":
        relative, content = "memorii/memorii/example.py", f'logger.error(message="failed {value}")\n'
    elif surface == "assertion_diagnostic":
        relative, content = "memorii/memorii/example.py", f'assert ready, "failed {value}"\n'
    elif surface == "design_generator":
        relative, content = "docs/design/generate_example.py", f"class {identifier}:\n    pass\n"
    elif surface == "nested_repository_path":
        relative, content = f"memorii/tests/{value}/test_behavior.py", "pass\n"
    elif surface == "structured_fixture":
        relative, content = "memorii/tests/example.json", json.dumps({"release_id": value})
    elif surface == "bare_python_id":
        relative, content = "docs/design/generate_example.py", f'id = "{value}"\n'
    elif surface == "bare_json_id":
        relative, content = "docs/design/generated.json", json.dumps({"id": value})
    elif surface == "bare_yaml_id":
        relative, content = "docs/design/generated.yaml", f"id: {value}\n"
    elif surface == "yaml_config":
        relative, content = "memorii/tests/example.yaml", f"owner_id: {value}\n"
    elif surface == "workflow_step_name":
        relative = ".github/workflows/check.yml"
        content = f"jobs:\n  check:\n    steps:\n      - name: Verify {value}\n        run: true\n"
    elif surface == "workflow_job_key":
        relative, content = ".github/workflows/check.yml", f"jobs:\n  {value}:\n    runs-on: ubuntu-latest\n"
    else:  # pragma: no cover - the fixed matrix owns this closed set
        raise AssertionError(f"unknown surface: {surface}")
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return relative


def _write_allowlist(path: Path, entries: list[dict[str, str]]) -> None:
    path.write_text(
        json.dumps({"exceptions": entries, "version": 1}, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )


def test_repository_identity_hygiene_is_clean() -> None:
    assert scan_repository(
        REPO_ROOT,
        allowlist_path=REPO_ROOT / ".agents/identity_hygiene_allowlist.json",
    ) == ()


@pytest.mark.parametrize("surface", _MUTATION_SURFACES)
@pytest.mark.parametrize(("coordinate", "identifier", "value", "module"), _COORDINATE_CASES)
def test_fixed_coordinate_corpus_is_rejected_on_every_owned_surface(
    tmp_path: Path,
    surface: str,
    coordinate: str,
    identifier: str,
    value: str,
    module: str,
) -> None:
    del coordinate
    root, allowlist = _root(tmp_path)
    relative = _write_mutation(
        root,
        surface=surface,
        identifier=identifier,
        value=value,
        module=module,
    )

    violations = scan_repository(root, allowlist_path=allowlist)

    assert violations, f"{surface} accepted {identifier!r}/{value!r}"
    assert all(item.path == relative for item in violations)
    assert all("planning/evidence coordinate" in item.reason for item in violations)


def test_static_concatenation_cannot_hide_a_planning_coordinate(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    (root / "memorii/memorii/example.py").write_text(
        'SCHEMA = "memorii." + "m3." + "contract.v1"\n', encoding="utf-8"
    )

    violations = scan_repository(root, allowlist_path=allowlist)

    assert len(violations) == 1
    assert violations[0].value == "memorii.m3.contract.v1"


@pytest.mark.parametrize(
    "content",
    [
        'stage = "m3"\nSCHEMA = f"memorii.{stage}.contract.v1"\n',
        'from enum import StrEnum\nclass ContractKind(StrEnum):\n    CURRENT = "m3"\n',
        'message = "M3"\nraise DomainFailure(message)\n',
    ],
)
def test_alias_enum_and_custom_raise_cannot_hide_a_planning_coordinate(
    tmp_path: Path, content: str
) -> None:
    root, allowlist = _root(tmp_path)
    (root / "memorii/memorii/example.py").write_text(content, encoding="utf-8")

    violations = scan_repository(root, allowlist_path=allowlist)

    assert violations
    assert any("planning/evidence coordinate" in item.reason for item in violations)


@pytest.mark.parametrize(
    ("relative", "content"),
    [
        ("docs/design/generate_example.py", 'document = {"milestone": 2}\n'),
        ("docs/design/generated.json", '{"milestone":2}\n'),
        ("docs/design/generated.yaml", "milestone: 2\n"),
        ("docs/design/generate_example.py", 'document = {"phase": 2}\n'),
        ("docs/design/generated.json", '{"phase":2}\n'),
        ("docs/design/generated.yaml", "phase: 2\n"),
        ("docs/design/generate_example.py", 'document = {"review_round": 3}\n'),
        ("docs/design/generated.json", '{"review_round":3}\n'),
        ("docs/design/generated.yaml", "review_round: 3\n"),
        (
            "docs/design/generate_example.py",
            'milestone_number = 2\ndocument = {"milestone": milestone_number}\n',
        ),
        (
            "docs/design/generate_example.py",
            'phase_number = 2\ndocument = {"phase": phase_number}\n',
        ),
        (
            "docs/design/generate_example.py",
            'round_number = 3\ndocument = {"review_round": round_number}\n',
        ),
    ],
)
def test_numeric_planning_field_is_rejected(
    tmp_path: Path, relative: str, content: str
) -> None:
    root, allowlist = _root(tmp_path)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    violations = scan_repository(root, allowlist_path=allowlist)

    assert len(violations) == 1
    assert violations[0].path == relative
    assert "planning/evidence coordinate" in violations[0].reason


def test_behavioral_protocol_and_algorithm_names_pass(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    (root / "memorii/memorii/example.py").write_text(
        "from enum import StrEnum\n\n"
        "class DeliveryCoordinate:\n"
        "    pass\n\n"
        "class BM25Scorer:\n"
        "    pass\n\n"
        "class ExecutionNodeType(StrEnum):\n"
        '    MILESTONE = "MILESTONE"\n\n'
        'SCHEMA = "memorii.semantic-ingestion.contract-envelope.v1"\n',
        encoding="utf-8",
    )
    (root / "memorii/tests/example.json").write_text(
        json.dumps(
            {
                "format": "memorii.provider-envelope-capture.v4",
                "id": "external-source-123",
            }
        ),
        encoding="utf-8",
    )
    (root / ".github/workflows/check.yml").write_text(
        "jobs:\n  bm25-contracts:\n    name: Verify contract envelope v1\n",
        encoding="utf-8",
    )

    assert scan_repository(root, allowlist_path=allowlist) == ()


def test_retired_requirement_coordinates_are_rejected_in_durable_markdown_identities(
    tmp_path: Path,
) -> None:
    root, allowlist = _root(tmp_path)
    (root / "docs/design/identity_examples.md").write_text(
        "\n".join(
            (
                "| retired | replacement |",
                "| --- | --- |",
                "| `semantic-ingestion-r03` | `current-contract` |",
                "| `semantic-ingestion-r13` | `current-contract` |",
                "| `pytest-sia-r03-v1` | `current-test` |",
                "| `pytest-sia-r13-v1` | `current-test` |",
                "| `bm25-contract-v1` | `current-algorithm` |",
                "| `memorii.semantic-ingestion.contract-envelope.v1` | `current-protocol` |",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    violations = scan_repository(root, allowlist_path=allowlist)

    assert {item.value for item in violations} == {
        "semantic-ingestion-r03",
        "semantic-ingestion-r13",
        "pytest-sia-r03-v1",
        "pytest-sia-r13-v1",
    }
    assert all("durable Markdown identity" in item.reason for item in violations)


def test_positive_compatibility_identity_is_backed_by_a_real_retained_fixture() -> None:
    manifest_path = (
        REPO_ROOT
        / "memorii/tests/fixtures/semantic_ingestion/provider_compatibility/capture_manifest.json"
    )
    proof_test = REPO_ROOT / "memorii/tests/unit/core/semantic_ingestion/test_provider_compatibility.py"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["format"] == "memorii.provider-envelope-capture.v4"
    assert proof_test.is_file()
    assert 'manifest["format"] == "memorii.provider-envelope-capture.v4"' in proof_test.read_text(
        encoding="utf-8"
    )


def test_requirement_coordinate_is_allowed_only_in_exact_registry_metadata(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    requirement = "SIA-" + "R22"
    registry = root / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps(
            {
                "heading_defaults": [{"require" + "ments": [requirement]}],
                "requirement_bindings": [{"requirement_" + "id": requirement}],
                "structural_rules": [{"selector_" + "values": [requirement]}],
                "test_evidence_groups": [
                    {"selected_tests": [{"test_" + "id": "SIA-T-" + "R22-ACCEPTANCE"}]}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert scan_repository(root, allowlist_path=allowlist) == ()

    registry.write_text(json.dumps({"fixture_" + "id": requirement}), encoding="utf-8")
    violations = scan_repository(root, allowlist_path=allowlist)
    assert len(violations) == 1
    assert violations[0].value == requirement


def test_graph_selector_requirements_are_allowed_only_in_exact_traceability_field(
    tmp_path: Path,
) -> None:
    root, allowlist = _root(tmp_path)
    manifest = root / "memorii/tests/ci/bootstrap-graph-transaction-boundary.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    requirement = "GTC-" + "R19"
    manifest.write_text(
        json.dumps({"rows": [{"requirement_" + "ids": [requirement]}]}),
        encoding="utf-8",
    )
    assert scan_repository(root, allowlist_path=allowlist) == ()

    manifest.write_text(
        json.dumps({"rows": [{"node_" + "id": requirement}]}),
        encoding="utf-8",
    )
    violations = scan_repository(root, allowlist_path=allowlist)
    assert len(violations) == 1
    assert violations[0].value == requirement


def test_python_traceability_exception_requires_exact_registry_proof(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    registry = root / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    source = root / "memorii/tests/test_traceability.py"
    source.write_text(
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        'UnitRequirementMapping(requirement_id="SIA-'
        + 'R22")\n',
        encoding="utf-8",
    )
    violation = scan_repository(root, allowlist_path=allowlist)[0]
    entry = {
        "classification": "typed_traceability_metadata",
        "location": violation.location,
        "path": violation.path,
        "proof": "docs/design/semantic_ingestion/traceability_registry/registry-v1.json",
        "rationale": "The value populates an exact typed requirement-binding field.",
        "value": violation.value,
    }
    _write_allowlist(allowlist, [entry])
    for invalid_proof in (
        {},
        {"fixture_" + "id": "SIA-" + "R22"},
        {"requirement_bindings": [{"requirement_" + "id": "SIA-" + "R21"}]},
    ):
        registry.write_text(json.dumps(invalid_proof), encoding="utf-8")
        with pytest.raises(ValueError, match="does not bind the exact permitted field and value"):
            scan_repository(root, allowlist_path=allowlist)

    registry.write_text(
        json.dumps({"requirement_bindings": [{"requirement_" + "id": "SIA-" + "R22"}]}),
        encoding="utf-8",
    )
    assert scan_repository(root, allowlist_path=allowlist) == ()

    entry["proof"] = "docs/design/missing-registry.json"
    _write_allowlist(allowlist, [entry])
    with pytest.raises(ValueError, match="existing repository artifact"):
        scan_repository(root, allowlist_path=allowlist)


@pytest.mark.parametrize(
    "source_text",
    [
        'requirement_id = "SIA-' + 'R22"\n',
        'helper(requirement_id="SIA-' + 'R22")\n',
        'def fake_mapping(*, requirement_id: str):\n    return requirement_id\n\n'
        'fake_mapping(requirement_id="SIA-' + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        "def UnitRequirementMapping(*, requirement_id: str):\n    return requirement_id\n\n"
        'UnitRequirementMapping(requirement_id="SIA-' + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        "UnitRequirementMapping = lambda **values: values\n"
        'UnitRequirementMapping(requirement_id="SIA-' + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        "def wrapper(UnitRequirementMapping):\n"
        '    return UnitRequirementMapping(requirement_id="SIA-'
        + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        "def wrapper():\n"
        "    from fake_module import UnitRequirementMapping\n"
        '    return UnitRequirementMapping(requirement_id="SIA-'
        + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        "def wrapper():\n"
        "    import fake_module as UnitRequirementMapping\n"
        '    return UnitRequirementMapping(requirement_id="SIA-'
        + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        "def wrapper():\n"
        "    from fake_module import *\n"
        '    return UnitRequirementMapping(requirement_id="SIA-'
        + 'R22")\n',
        "import memorii.tools.semantic_ingestion_traceability as trace\n"
        "trace.UnitRequirementMapping = lambda **values: values\n"
        'trace.UnitRequirementMapping(requirement_id="SIA-' + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        'globals()["UnitRequirementMapping"] = lambda **values: values\n'
        'UnitRequirementMapping(requirement_id="SIA-' + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        "match object():\n"
        "    case UnitRequirementMapping:\n"
        "        pass\n"
        'UnitRequirementMapping(requirement_id="SIA-' + 'R22")\n',
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        "import builtins\n"
        'builtins.globals()["UnitRequirementMapping"] = lambda **values: values\n'
        'UnitRequirementMapping(requirement_id="SIA-' + 'R22")\n',
    ],
)
def test_traceability_exception_requires_a_typed_keyword_call(
    tmp_path: Path, source_text: str
) -> None:
    root, allowlist = _root(tmp_path)
    registry = root / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"requirement_bindings": [{"requirement_" + "id": "SIA-" + "R22"}]}),
        encoding="utf-8",
    )
    source = root / "memorii/tests/test_traceability.py"
    source.write_text(source_text, encoding="utf-8")
    violation = scan_repository(root, allowlist_path=allowlist)[0]
    _write_allowlist(
        allowlist,
        [
            {
                "classification": "typed_traceability_metadata",
                "location": violation.location,
                "path": violation.path,
                "proof": "docs/design/semantic_ingestion/traceability_registry/registry-v1.json",
                "rationale": "Attempted typed traceability exception.",
                "value": violation.value,
            }
        ],
    )

    with pytest.raises(ValueError, match="not an exact typed call field"):
        scan_repository(root, allowlist_path=allowlist)


def test_traceability_exception_requires_the_exact_keyword_column(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    registry = root / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"requirement_bindings": [{"requirement_" + "id": "SIA-" + "R22"}]}),
        encoding="utf-8",
    )
    source = root / "memorii/tests/test_traceability.py"
    source.write_text(
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        'UnitRequirementMapping(requirement_id="SIA-R22"); helper(requirement_id="SIA-R22")\n',
        encoding="utf-8",
    )
    violations = scan_repository(root, allowlist_path=allowlist)
    helper_violation = max(violations, key=lambda item: int(item.location.rsplit(":", 1)[1]))
    _write_allowlist(
        allowlist,
        [
            {
                "classification": "typed_traceability_metadata",
                "location": helper_violation.location,
                "path": helper_violation.path,
                "proof": "docs/design/semantic_ingestion/traceability_registry/registry-v1.json",
                "rationale": "Attempted same-line traceability exception.",
                "value": helper_violation.value,
            }
        ],
    )

    with pytest.raises(ValueError, match="not an exact typed call field"):
        scan_repository(root, allowlist_path=allowlist)


def test_positional_traceability_coordinate_is_rejected(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    (root / "memorii/tests/test_traceability.py").write_text(
        'binding("SIA-' + 'R22")\n', encoding="utf-8"
    )

    violations = scan_repository(root, allowlist_path=allowlist)

    assert len(violations) == 1
    assert "explicit typed field" in violations[0].reason


def test_traceability_exception_rejects_field_and_value_type_mismatch(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    registry = root / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"requirement_bindings": [{"requirement_" + "id": "SIA-" + "R22"}]}),
        encoding="utf-8",
    )
    source = root / "memorii/tests/test_traceability.py"
    source.write_text(
        "from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping\n"
        'UnitRequirementMapping(test_id="SIA-'
        + 'R22")\n',
        encoding="utf-8",
    )
    violation = scan_repository(root, allowlist_path=allowlist)[0]
    _write_allowlist(
        allowlist,
        [
            {
                "classification": "typed_traceability_metadata",
                "location": violation.location,
                "path": violation.path,
                "proof": "docs/design/semantic_ingestion/traceability_registry/registry-v1.json",
                "rationale": "Attempted mismatched traceability exception.",
                "value": violation.value,
            }
        ],
    )

    with pytest.raises(ValueError, match="test traceability field must contain an SIA-T value"):
        scan_repository(root, allowlist_path=allowlist)


def test_shipped_compatibility_exception_is_exact_and_stale_entries_fail(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    proof = root / ".agents/compatibility_proof.json"
    proof_test = root / "memorii/tests/test_compatibility_reader.py"
    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        'def test_compatibility_reader():\n    assert read_outcome("unrelated-format-v1")\n',
        encoding="utf-8",
    )
    source = root / "memorii/memorii/example.py"
    source.write_text('SCHEMA = "memorii.' + 'm2.legacy.v1"\n', encoding="utf-8")
    violation = scan_repository(root, allowlist_path=allowlist)[0]
    _write_allowlist(
        allowlist,
        [
            {
                "classification": "shipped_migration_identity",
                "location": violation.location,
                "path": violation.path,
                "proof": ".agents/compatibility_proof.json",
                "rationale": "A shipped reader must retain this exact source format.",
                "value": violation.value,
            }
        ],
    )
    proof.write_text(
        json.dumps(
            {
                    "proof_test": "memorii/tests/test_compatibility_reader.py::test_compatibility_reader",
                    "source_" + "format": "unrelated-format-v1",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not contain the exact retained identity"):
        scan_repository(root, allowlist_path=allowlist)

    proof.write_text(
        json.dumps(
            {
                "proof_test": "memorii/tests/test_compatibility_reader.py",
                "source_" + "format": "memorii." + "m2.legacy.v1",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must name its exact reader or fixture test"):
        scan_repository(root, allowlist_path=allowlist)

    proof.write_text(
        json.dumps(
            {
                    "proof_test": "memorii/tests/test_compatibility_reader.py::test_compatibility_reader",
                    "source_" + "format": "memorii." + "m2.legacy.v1",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        'def test_compatibility_reader():\n'
        '    retained = "memorii.'
        + 'm2.legacy.v1"\n'
        "    assert True\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "def read(value):\n    return value\n\n"
        'def test_compatibility_reader():\n    assert read("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "import tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader as legacy_reader\n\n"
        "legacy_reader.read_outcome = lambda value: value\n\n"
        "def test_compatibility_reader():\n"
        '    assert legacy_reader.read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n"
        "import builtins\n\n"
        'builtins.globals()["read_outcome"] = lambda value: value\n\n'
        "def test_compatibility_reader():\n"
        '    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        "def test_compatibility_reader():\n"
        "    match object():\n"
        "        case read_outcome:\n"
        "            pass\n"
        '    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        'globals()["read_outcome"] = lambda value: value\n\n'
        "def test_compatibility_reader():\n"
        '    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        "def test_compatibility_reader():\n"
        "    from fake_module import *\n"
        '    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        "def test_compatibility_reader():\n"
        "    import fake_module as read_outcome\n"
        '    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        "def test_compatibility_reader():\n"
        "    from fake_module import read_outcome\n"
        '    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        "def test_compatibility_reader(read_outcome=lambda value: value):\n"
        '    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        "def read_outcome(value):\n    return value\n\n"
        'def test_compatibility_reader():\n    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="proof test does not bind"):
        scan_repository(root, allowlist_path=allowlist)

    proof_test.write_text(
        "from tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader import read_outcome\n\n"
        'def test_compatibility_reader():\n    assert read_outcome("memorii.'
        + 'm2.legacy.v1")\n',
        encoding="utf-8",
    )
    assert scan_repository(root, allowlist_path=allowlist) == ()

    source.write_text('SCHEMA = "memorii.semantic.current.v1"\n', encoding="utf-8")
    stale = scan_repository(root, allowlist_path=allowlist)
    assert len(stale) == 1
    assert stale[0].reason == "stale identity allowlist entry"


def test_legacy_exception_requires_a_named_test_with_rejection_assertion(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    source = root / "memorii/tests/test_legacy_codec.py"
    source.write_text(
        "import pytest\n\n"
        "def decode(*, schema):\n"
        "    raise ValueError(schema)\n\n"
        "def test_legacy_schema_is_rejected():\n"
        "    with pytest.raises(ValueError):\n"
        '        decode(schema="memorii.m2.legacy.v1")\n',
        encoding="utf-8",
    )
    violation = scan_repository(root, allowlist_path=allowlist)[0]
    entry = {
        "classification": "legacy_rejection_vector",
        "location": violation.location,
        "path": violation.path,
        "proof": "memorii/tests/test_legacy_codec.py::test_legacy_schema_is_rejected",
        "rationale": "The bytes exist only to prove fail-closed rejection.",
        "value": violation.value,
    }
    _write_allowlist(allowlist, [entry])
    assert scan_repository(root, allowlist_path=allowlist) == ()

    source.write_text(
        "import pytest\n\n"
        "def decode(*, schema):\n"
        "    raise ValueError(schema)\n\n"
        "def test_legacy_schema_is_rejected():\n"
        "    with pytest.raises(ValueError):\n"
        '        decode(schema="current-schema-v1")\n'
        '        schema = "memorii.m2.legacy.v1"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exact rejecting test proof"):
        scan_repository(root, allowlist_path=allowlist)


def test_allowlist_rejects_broad_or_untyped_exceptions(tmp_path: Path) -> None:
    root, allowlist = _root(tmp_path)
    _write_allowlist(
        allowlist,
        [
            {
                "classification": "temporary_debt",
                "location": "*",
                "path": "memorii/tests/*",
                "proof": "docs/design/none.md",
                "rationale": "broad exception",
                "value": "M3",
            }
        ],
    )

    with pytest.raises(ValueError, match="invalid classification"):
        scan_repository(root, allowlist_path=allowlist)
