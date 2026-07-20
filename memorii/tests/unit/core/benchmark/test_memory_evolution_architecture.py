import ast
import importlib
import importlib.util
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[4] / "memorii" / "core"
SOURCE_ROOT = PACKAGE_ROOT.parent
TEST_ROOT = SOURCE_ROOT.parent / "tests"
PRODUCTION_ROOT = PACKAGE_ROOT / "memory_evolution"
PRODUCTION_LLM_DECISION_ROOT = PACKAGE_ROOT / "llm_decision"
PROMPT_ROOT = PACKAGE_ROOT / "prompts"
PRODUCTION_RUNTIME_ROOTS = tuple(
    PACKAGE_ROOT / name
    for name in (
        "belief",
        "llm_decision",
        "memory_evolution",
        "promotion",
        "provider",
        "solver",
    )
)
INDEPENDENT_EVALUATORS = (
    PACKAGE_ROOT / "benchmark" / "memory_evolution_decision",
    PACKAGE_ROOT / "benchmark" / "memory_evolution_sim",
)
DOMAIN_NAMING_PATTERN = re.compile(r"(?:phase\d+|wave\d+|legacy|compat)", re.IGNORECASE)
MODULE_LINE_BUDGETS = {
    PACKAGE_ROOT / "benchmark" / "memory_evolution_runtime" / "runner.py": 400,
    PACKAGE_ROOT / "benchmark" / "memory_evolution_runtime" / "checkpoint_projection.py": 500,
    PACKAGE_ROOT / "benchmark" / "memory_evolution_runtime" / "checkpoint_evaluation.py": 200,
    PACKAGE_ROOT / "benchmark" / "memory_evolution_sim" / "generation.py": 100,
    PACKAGE_ROOT / "benchmark" / "memory_evolution_sim" / "family_scenarios.py": 700,
    PACKAGE_ROOT / "benchmark" / "memory_evolution_sim" / "family_observations.py": 350,
    PACKAGE_ROOT / "benchmark" / "memory_evolution_sim" / "checkpoints.py": 450,
    PACKAGE_ROOT / "benchmark" / "memory_evolution_sim" / "schema_builders.py": 350,
}
PRODUCTION_SHAPED_TESTS = (
    TEST_ROOT / "unit" / "core" / "test_llm_eval_runner.py",
    TEST_ROOT / "unit" / "core" / "test_runtime_step_service.py",
    TEST_ROOT / "integration" / "test_harness_runtime_integration.py",
)


def _imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append((node.module, tuple(alias.name for alias in node.names)))
        elif isinstance(node, ast.Import):
            imports.extend((alias.name, ()) for alias in node.names)
    return imports


def _dynamic_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first_argument = node.args[0]
        if not isinstance(first_argument, ast.Constant) or not isinstance(first_argument.value, str):
            continue
        is_builtin_import = isinstance(node.func, ast.Name) and node.func.id == "__import__"
        is_importlib_import = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "importlib"
            and node.func.attr == "import_module"
        )
        if is_builtin_import or is_importlib_import:
            modules.append(first_argument.value)
    return modules


def _module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(("memorii", *parts))


def _resolved_import_module(path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    current_module = _module_name(path)
    package = current_module if path.name == "__init__.py" else current_module.rpartition(".")[0]
    relative_name = "." * node.level + (node.module or "")
    try:
        return importlib.util.resolve_name(relative_name, package)
    except ImportError:
        return None


def _defined_identifiers(tree: ast.AST) -> list[tuple[int, str]]:
    identifiers: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identifiers.append((node.lineno, node.name))
        elif isinstance(node, ast.Name):
            identifiers.append((node.lineno, node.id))
        elif isinstance(node, ast.arg):
            identifiers.append((node.lineno, node.arg))
        elif isinstance(node, ast.alias) and node.asname is not None:
            identifiers.append((node.lineno, node.asname))
    return identifiers


def _call_attribute(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def test_production_memory_evolution_never_imports_benchmark_code() -> None:
    violations = [
        f"{path}:{module}"
        for path in PRODUCTION_ROOT.rglob("*.py")
        for module, _names in _imports(path)
        if module.startswith("memorii.core.benchmark")
    ]

    assert violations == []


def test_production_memory_evolution_never_dynamically_imports_benchmark_code() -> None:
    violations = [
        f"{path}:{module}"
        for path in PRODUCTION_ROOT.rglob("*.py")
        for module in _dynamic_imports(path)
        if module.startswith("memorii.core.benchmark")
    ]

    assert violations == []


def test_production_llm_decision_layer_never_imports_benchmark_contracts() -> None:
    violations = [
        f"{path}:{module}"
        for path in PRODUCTION_LLM_DECISION_ROOT.rglob("*.py")
        for module, _names in _imports(path)
        if module.startswith("memorii.core.benchmark")
    ]

    assert violations == []


def test_runtime_prompt_registry_does_not_import_conformance_fixtures() -> None:
    runtime_paths = (
        PROMPT_ROOT / "__init__.py",
        PROMPT_ROOT / "registry.py",
        PROMPT_ROOT / "render.py",
        PROMPT_ROOT / "runtime_manifest.py",
    )
    violations = [
        f"{path}:{module}"
        for path in runtime_paths
        for module, _names in _imports(path)
        if module == "tests.prompt_contract_manifest"
    ]

    assert violations == []


def test_prompt_conformance_fixtures_do_not_ship_in_installable_source() -> None:
    assert not (PROMPT_ROOT / "manifest.py").exists()
    forbidden_names = {"fake_valid_output", "representative_variables"}
    violations: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        violations.extend(
            f"{path}:{line}:{name}"
            for line, name in _defined_identifiers(tree)
            if name in forbidden_names
        )

    assert violations == []


def test_production_runtime_does_not_import_conformance_or_test_support() -> None:
    forbidden = (
        "tests",
        "memorii.core.llm_eval.fake_client",
        "tests.prompt_contract_manifest",
    )
    violations = [
        f"{path}:{module}"
        for root in PRODUCTION_RUNTIME_ROOTS
        for path in root.rglob("*.py")
        for module, _names in _imports(path)
        if module == forbidden[0] or module.startswith(f"{forbidden[0]}.") or module in forbidden[1:]
    ]

    assert violations == []


def test_production_runtime_does_not_dynamically_import_test_support() -> None:
    forbidden = (
        "tests",
        "memorii.core.llm_eval.fake_client",
        "tests.prompt_contract_manifest",
    )
    violations = [
        f"{path}:{module}"
        for root in PRODUCTION_RUNTIME_ROOTS
        for path in root.rglob("*.py")
        for module in _dynamic_imports(path)
        if module == forbidden[0] or module.startswith(f"{forbidden[0]}.") or module in forbidden[1:]
    ]

    assert violations == []


def test_benchmark_prompt_adapters_use_explicit_context_annotations() -> None:
    adapter_paths = (
        PACKAGE_ROOT / "benchmark" / "llm_adapters.py",
        PACKAGE_ROOT.parent / "tools" / "benchmark_suites" / "fake_adapters.py",
    )
    decide_methods: list[ast.FunctionDef] = []
    for adapter_path in adapter_paths:
        tree = ast.parse(adapter_path.read_text(), filename=str(adapter_path))
        decide_methods.extend(
            node
            for class_node in tree.body
            if isinstance(class_node, ast.ClassDef)
            for node in class_node.body
            if isinstance(node, ast.FunctionDef) and node.name == "decide"
        )

    assert decide_methods
    for method in decide_methods:
        context = next(argument for argument in method.args.args if argument.arg == "context")
        assert isinstance(context.annotation, ast.Name)
        assert context.annotation.id not in {"Any", "object"}


def test_oracle_and_sim_evaluators_do_not_reuse_production_semantic_pipeline() -> None:
    forbidden = (
        "memorii.core.memory_evolution.graph_constraint_resolution",
        "memorii.core.memory_evolution.query_analysis",
        "memorii.core.memory_evolution.retrieval",
        "memorii.core.memory_evolution.retrieval_runtime",
    )
    violations = [
        f"{path}:{module}"
        for root in INDEPENDENT_EVALUATORS
        for path in root.rglob("*.py")
        for module, _names in _imports(path)
        if module.startswith(forbidden)
    ]

    assert violations == []


def test_oracle_and_sim_evaluators_do_not_dynamically_import_production_pipeline() -> None:
    forbidden = (
        "memorii.core.memory_evolution.graph_constraint_resolution",
        "memorii.core.memory_evolution.query_analysis",
        "memorii.core.memory_evolution.retrieval",
        "memorii.core.memory_evolution.retrieval_runtime",
    )
    violations = [
        f"{path}:{module}"
        for root in INDEPENDENT_EVALUATORS
        for path in root.rglob("*.py")
        for module in _dynamic_imports(path)
        if module.startswith(forbidden)
    ]

    assert violations == []


def test_source_does_not_import_cross_module_private_symbols() -> None:
    violations = [
        f"{path}:{module}:{name}"
        for path in SOURCE_ROOT.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
        if isinstance(node, ast.ImportFrom)
        if (module := _resolved_import_module(path, node)) is not None
        if module.startswith("memorii.") and module != _module_name(path)
        for name in (alias.name for alias in node.names)
        if name.startswith("_") and name != "__future__"
    ]

    assert violations == []


def test_public_hardening_packages_export_real_symbols() -> None:
    for module_name in (
        "memorii.core.benchmark.artifact_rows",
        "memorii.core.memory_evolution",
    ):
        module = importlib.import_module(module_name)
        missing = [name for name in module.__all__ if not hasattr(module, name)]
        assert missing == [], f"{module_name} has invalid __all__ entries: {missing}"


def test_owned_packages_replace_the_removed_monolith_modules() -> None:
    benchmark_root = PACKAGE_ROOT / "benchmark"

    assert (benchmark_root / "artifact_rows").is_dir()
    assert not (benchmark_root / "artifact_rows.py").exists()
    assert (PRODUCTION_ROOT / "query_analysis").is_dir()
    assert not (PRODUCTION_ROOT / "query_analysis.py").exists()
    assert not (PRODUCTION_ROOT / "query_runtime_factory.py").exists()


def test_active_python_identifiers_and_paths_use_domain_names() -> None:
    architecture_test = Path(__file__).resolve()
    violations: list[str] = []
    for root in (SOURCE_ROOT, TEST_ROOT):
        for path in root.rglob("*.py"):
            if path.resolve() == architecture_test:
                continue
            relative_path = path.relative_to(root).as_posix()
            if DOMAIN_NAMING_PATTERN.search(relative_path):
                violations.append(relative_path)
            tree = ast.parse(path.read_text(), filename=str(path))
            violations.extend(
                f"{relative_path}:{line}:{name}"
                for line, name in _defined_identifiers(tree)
                if DOMAIN_NAMING_PATTERN.search(name)
            )

    assert violations == []


def test_domain_constructors_do_not_load_environment_configuration() -> None:
    violations: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            for method in (
                node
                for node in class_node.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__"
            ):
                for call in (node for node in ast.walk(method) if isinstance(node, ast.Call)):
                    if _call_attribute(call) in {"from_env", "load_memorii_environment"}:
                        violations.append(f"{path}:{call.lineno}:{class_node.name}")

    assert violations == []


def test_installable_source_does_not_import_test_packages() -> None:
    violations = [
        f"{path}:{module}"
        for path in SOURCE_ROOT.rglob("*.py")
        for module, _names in _imports(path)
        if module == "tests" or module.startswith("tests.")
    ]

    assert violations == []


def test_schema_only_package_initializers_remain_side_effect_free() -> None:
    for path in (PACKAGE_ROOT / "calibration" / "__init__.py", PACKAGE_ROOT / "solver" / "__init__.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        executable_statements = [
            node
            for node in tree.body
            if not isinstance(node, (ast.Expr, ast.Import, ast.ImportFrom))
        ]
        assert imports == [], f"{path} must not eagerly import its component graph"
        assert executable_statements == [], f"{path} must contain documentation only"


def test_production_shaped_test_doubles_use_runtime_contracts() -> None:
    violations: list[str] = []
    for path in PRODUCTION_SHAPED_TESTS:
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        if any(isinstance(node, ast.Name) and node.id == "SimpleNamespace" for node in ast.walk(tree)):
            violations.append(f"{path}:SimpleNamespace")
        if "SLF001" in source:
            violations.append(f"{path}:SLF001")
        if "type: ignore" in source:
            violations.append(f"{path}:type-ignore")

    assert violations == []


def test_typed_artifact_models_do_not_emulate_mappings() -> None:
    path = PACKAGE_ROOT / "benchmark" / "artifact_rows" / "common.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    model = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FlatArtifactModel")
    prohibited_methods = {"__getitem__", "__iter__", "__len__", "__eq__", "from_flat_row"}
    defined_methods = {
        node.name for node in model.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert defined_methods.isdisjoint(prohibited_methods)


def test_typed_artifact_construction_does_not_round_trip_through_dicts() -> None:
    violations: list[str] = []
    artifact_root = PACKAGE_ROOT / "benchmark" / "artifact_rows"
    for path in artifact_root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            if _call_attribute(call) not in {"model_validate", "from_flat_row"}:
                continue
            if any(
                isinstance(nested, ast.Call) and _call_attribute(nested) == "model_dump"
                for argument in (*call.args, *(keyword.value for keyword in call.keywords))
                for nested in ast.walk(argument)
            ):
                violations.append(f"{path}:{call.lineno}")

    assert violations == []


def test_calibration_models_remain_typed_until_artifact_writers() -> None:
    violations: list[str] = []
    for path in (
        PACKAGE_ROOT / "calibration" / "reports.py",
        PACKAGE_ROOT / "calibration" / "gates.py",
    ):
        tree = ast.parse(path.read_text(), filename=str(path))
        violations.extend(
            f"{path}:{call.lineno}"
            for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call))
            if _call_attribute(call) == "model_dump"
        )

    assert violations == []


def test_default_provider_composition_has_no_memory_evolution_feature_flag() -> None:
    path = PACKAGE_ROOT / "provider" / "service.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    provider_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ProviderMemoryService"
    )
    constructor = next(
        node for node in provider_class.body if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    argument_names = {argument.arg for argument in (*constructor.args.args, *constructor.args.kwonlyargs)}

    assert "memory_evolution_enabled" not in argument_names


def test_runtime_benchmark_uses_production_prefetch_composition() -> None:
    path = PACKAGE_ROOT / "benchmark" / "memory_evolution_runtime" / "runner.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    calls = {
        attribute
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call))
        if (attribute := _call_attribute(call)) is not None
    }

    assert "prefetch_result" in calls
    assert "retrieve_evolution_decision" not in calls


def test_documentation_does_not_advertise_removed_memory_evolution_feature_flag() -> None:
    repository_root = SOURCE_ROOT.parents[1]
    documented_paths = (
        repository_root / "docs" / "plans" / "agent_integration_readiness.md",
        repository_root / "docs" / "design" / "belief_state_management.md",
        repository_root / "docs" / "design" / "memory_evolution_runtime_benchmark.md",
        repository_root / "docs" / "design" / "memory_evolution_runtime.md",
    )

    stale_paths = [str(path) for path in documented_paths if "memory_evolution_enabled" in path.read_text()]

    assert stale_paths == []


def test_promotion_contract_modules_have_single_domain_ownership() -> None:
    promotion_root = PACKAGE_ROOT / "promotion"
    assert (promotion_root / "assessment.py").exists()
    assert (promotion_root / "execution_contracts.py").exists()
    assert not (promotion_root / "models.py").exists()
    assert not (promotion_root / "lifecycle_models.py").exists()


def test_checkpoint_diagnostics_aggregator_copies_every_typed_field() -> None:
    module = importlib.import_module("memorii.core.benchmark.artifact_rows.checkpoints")
    path = PACKAGE_ROOT / "benchmark" / "artifact_rows" / "checkpoints.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    payload_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CheckpointDiagnosticsPayload"
    )
    method = next(
        node
        for node in payload_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "from_sections"
    )
    constructor = next(
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "cls"
    )
    copied_fields = {keyword.arg for keyword in constructor.keywords if keyword.arg is not None}
    expected_fields = set(module.CheckpointDiagnosticsPayload.model_fields)

    assert copied_fields == expected_fields


def test_split_modules_remain_within_ownership_budgets() -> None:
    violations = [
        f"{path}:{line_count}>{budget}"
        for path, budget in MODULE_LINE_BUDGETS.items()
        if (line_count := len(path.read_text().splitlines())) > budget
    ]

    assert violations == []
