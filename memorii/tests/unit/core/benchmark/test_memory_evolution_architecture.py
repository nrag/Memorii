import ast
import importlib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[4] / "memorii" / "core"
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
        if module == "memorii.core.prompts.manifest"
    ]

    assert violations == []


def test_production_runtime_does_not_import_conformance_or_test_support() -> None:
    forbidden = (
        "tests",
        "memorii.core.llm_eval.fake_client",
        "memorii.core.prompts.manifest",
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
        "memorii.core.prompts.manifest",
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


def test_benchmark_packages_do_not_import_cross_module_private_symbols() -> None:
    violations = [
        f"{path}:{module}:{name}"
        for root in INDEPENDENT_EVALUATORS
        for path in root.rglob("*.py")
        for module, names in _imports(path)
        if module.startswith("memorii.core.benchmark")
        for name in names
        if name.startswith("_")
    ]

    assert violations == []


def test_public_hardening_packages_export_real_symbols() -> None:
    for module_name in (
        "memorii.core.benchmark.artifact_rows",
        "memorii.core.memory_evolution",
        "memorii.core.calibration",
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


def test_typed_artifact_construction_does_not_round_trip_through_dicts() -> None:
    violations = []
    for path in PACKAGE_ROOT.parent.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "from_flat_row(vote.model_dump" in source:
            violations.append(path.relative_to(PACKAGE_ROOT.parent).as_posix())

    assert violations == []
