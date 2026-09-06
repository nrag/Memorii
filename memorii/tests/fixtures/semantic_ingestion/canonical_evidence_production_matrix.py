"""Closed structural proof for the thin canonical-evidence capture fixture."""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

MATRIX = (("direct", "memory"), ("direct", "jsonl"), ("factory", "memory"), ("factory", "jsonl"), ("filesystem", "memory"), ("filesystem", "jsonl"), ("hermes", "memory"), ("hermes", "jsonl"))


class MatrixError(RuntimeError):
    pass


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _grammar() -> dict[str, object]:
    value = json.loads((repository_root() / "docs/design/semantic_ingestion_canonical_evidence/thin-fixture-ast-grammar-v1.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "memorii.semantic-ingestion.canonical-evidence.thin-fixture-grammar.v3":
        raise MatrixError("thin fixture grammar is invalid")
    return value


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _exact_imports(tree: ast.Module, expected: set[str]) -> None:
    actual: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    raise MatrixError("import aliases are forbidden")
                actual.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                raise MatrixError("relative imports are forbidden")
            for alias in node.names:
                if alias.asname is not None:
                    raise MatrixError("import aliases are forbidden")
                actual.add(f"{node.module}.{alias.name}")
    if actual != expected:
        raise MatrixError("fixture imports are not exact")


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_cell_value(node: ast.AST, key: str) -> bool:
    return isinstance(node, ast.Subscript) and _is_name(node.value, "cell") and isinstance(node.slice, ast.Constant) and node.slice.value == key


def _require_call(statement: ast.stmt, target: str, target_name: str, keywords: tuple[str, ...]) -> ast.Call:
    if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 or not _is_name(statement.targets[0], target_name):
        raise MatrixError(f"expected assignment to {target_name}")
    if not isinstance(statement.value, ast.Call) or _dotted(statement.value.func) != target:
        raise MatrixError(f"expected exact {target} call")
    if tuple(keyword.arg for keyword in statement.value.keywords) != keywords or any(keyword.arg is None for keyword in statement.value.keywords):
        raise MatrixError(f"{target} keyword contract differs")
    return statement.value


def _validate_straight_line(function: ast.FunctionDef) -> None:
    arguments = function.args
    if (
        function.decorator_list
        or function.returns is not None
        or function.type_comment is not None
        or getattr(function, "type_params", ())
        or arguments.posonlyargs
        or [argument.arg for argument in arguments.args] != ["cell", "factory", "root_constructor", "operation"]
        or any(argument.annotation is not None or argument.type_comment is not None for argument in arguments.args)
        or arguments.vararg is not None
        or arguments.kwonlyargs
        or arguments.kw_defaults
        or arguments.kwarg is not None
        or arguments.defaults
    ):
        raise MatrixError("cell executor arguments are not exact")
    prohibited = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.AsyncFor, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Yield, ast.YieldFrom)
    if len(function.body) != 4 or any(isinstance(node, prohibited) for node in ast.walk(function)):
        raise MatrixError("cell executor must be straight-line")
    authority_call = _require_call(function.body[0], "factory", "authority", ("host_bootstrap_capability", "host_bootstrap_material_verifier", "server_time"))
    if not all(_is_cell_value(keyword.value, key) for keyword, key in zip(authority_call.keywords, ("host_bootstrap_capability", "host_bootstrap_material_verifier", "server_time"), strict=True)):
        raise MatrixError("factory inputs must come directly from declared cell")
    root_call = _require_call(function.body[1], "root_constructor", "service", ("verified_production_host_authority",))
    if not _is_name(root_call.keywords[0].value, "authority"):
        raise MatrixError("authority may flow only to the root authority argument")
    sync_call = _require_call(function.body[2], "service.sync_event", "result", ("operation", "content", "operation_id", "authenticated_host_ingress"))
    if not (_is_name(sync_call.keywords[0].value, "operation") and _is_cell_value(sync_call.keywords[1].value, "content") and _is_cell_value(sync_call.keywords[2].value, "operation_identity") and _is_cell_value(sync_call.keywords[3].value, "authenticated_host_ingress")):
        raise MatrixError("sync_event inputs must come directly from declared cell")
    if not isinstance(function.body[3], ast.Return) or not _is_name(function.body[3].value, "result"):
        raise MatrixError("only production result may leave cell executor")


def _validate_runner(source: str) -> ast.Module:
    grammar = _grammar()["modules"]["canonical_evidence_performance_runner.py"]
    assert isinstance(grammar, dict)
    tree = ast.parse(
        source,
        filename="canonical_evidence_performance_runner.py",
        type_comments=True,
    )
    if tree.type_ignores:
        raise MatrixError("runner type ignores are forbidden")
    _exact_imports(tree, set(grammar["top_level_imports"]))
    if len(tree.body) != 4 or not (isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str)):
        raise MatrixError("runner module body is not exact")
    definitions = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
    if [node.name for node in definitions] != grammar["top_level_definitions"]:
        raise MatrixError("fixture top-level definitions are not exact")
    executor = next((node for node in definitions if isinstance(node, ast.FunctionDef) and node.name == "_execute_declared_cell"), None)
    if executor is None:
        raise MatrixError("cell executor is absent")
    _validate_straight_line(executor)
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)]
    if len(assignments) != 1 or len(assignments[0].targets) != 1 or not _is_name(assignments[0].targets[0], "CAPTURE_ENTRYPOINT") or not isinstance(assignments[0].value, ast.Constant) or assignments[0].value.value != "_execute_declared_cell":
        raise MatrixError("runner declarative entrypoint is not exact")
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            raise MatrixError("async function definitions are forbidden")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.type_comment is not None:
            raise MatrixError("function type comments are forbidden")
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and getattr(node, "type_comment", None) is not None:
            raise MatrixError("assignment type comments are forbidden")
        if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.AsyncFor, ast.Match, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            raise MatrixError("runner control flow or deferred expression is forbidden")
        if isinstance(node, ast.Assign) and any(isinstance(target, (ast.Attribute, ast.Subscript, ast.Tuple, ast.List)) for target in node.targets):
            raise MatrixError("attribute, subscript, and destructuring assignment are forbidden")
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, (ast.Attribute, ast.Subscript, ast.Tuple, ast.List)):
            raise MatrixError("attribute, subscript, and destructuring assignment are forbidden")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"getattr", "setattr"}:
            raise MatrixError("dynamic attribute access is forbidden")
        if isinstance(node, ast.Call) and node is not executor.body[0].value and node is not executor.body[1].value and node is not executor.body[2].value:
            raise MatrixError("runner has a call outside the exact production dataflow")
    return tree


def _parser_supports_type_parameters() -> bool:
    try:
        ast.parse("def probe[T]():\n    pass\n")
    except SyntaxError:
        return False
    return True


def verify_static_matrix(*, binding_map: dict[str, object], runner_source: str, recipe_source: str) -> dict[str, object]:
    tree = _validate_runner(runner_source)
    if "Closed structural proof" not in recipe_source:
        raise MatrixError("locked static validator identity is invalid")
    entries = binding_map.get("production_entrypoint_bindings")
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        raise MatrixError("binding map omits public matrix entry")
    entry = entries[0]
    if tuple(tuple(item.split("/")) for item in entry.get("matrix_order", [])) != MATRIX:
        raise MatrixError("binding matrix order is not exact")
    if entry.get("fixture_ast_grammar") != "thin-fixture-ast-grammar-v1.json":
        raise MatrixError("binding map does not bind the positive AST grammar")
    return {"matrix": [f"{root}/{backend}" for root, backend in MATRIX], "ast_nodes": len(list(ast.walk(tree))), "status": entry.get("status")}


def self_test(*, binding_map: dict[str, object], runner_source: str, recipe_source: str) -> None:
    verify_static_matrix(binding_map=binding_map, runner_source=runner_source, recipe_source=recipe_source)
    mutations = {
        "factory_omission": runner_source.replace("authority = factory", "authority = root_constructor", 1),
        "factory_replacement": runner_source.replace("authority = factory", "authority = replacement", 1),
        "cell_sourced_authority": runner_source.replace("verified_production_host_authority=authority", "verified_production_host_authority=cell['authority']", 1),
        "authority_alias": runner_source.replace("service = root_constructor", "authority_alias = authority\n    service = root_constructor", 1),
        "if_false": runner_source.replace("result = service.sync_event", "if False:\n        pass\n    result = service.sync_event", 1),
        "loop": runner_source.replace("result = service.sync_event", "for ignored in ():\n        pass\n    result = service.sync_event", 1),
        "two_sync": runner_source.replace("return result", "service.sync_event(operation=operation, content=cell['content'], operation_id=cell['operation_identity'], authenticated_host_ingress=cell['authenticated_host_ingress'])\n    return result", 1),
        "direct_terminal": runner_source.replace("service.sync_event", "service._run_semantic_ingestion", 1),
        "fabricated_function": runner_source + "\ndef forged_receipt():\n    return None\n",
        "subscript_assignment": runner_source.replace("return result", "cell['result'] = result\n    return result", 1),
        "unknown_expression": runner_source.replace("return result", "return (result for result in ())", 1),
        "main_control_flow": runner_source + "\nif __name__ == '__main__':\n    pass\n",
        "import_side_effect": runner_source.replace("from __future__ import annotations", "from __future__ import annotations\nimport os", 1),
        "fabricated_receipt": runner_source.replace("return result", "forged_receipt = {}\n    return result", 1),
        "decorator": runner_source.replace("def _execute_declared_cell", "@print\ndef _execute_declared_cell", 1),
        "parameter_annotation": runner_source.replace("cell, factory", "cell: object, factory", 1),
        "return_annotation": runner_source.replace("operation):", "operation) -> object:", 1),
        "function_type_comment": runner_source.replace("operation):", "operation):  # type: (object, object, object, object) -> object", 1),
        "assignment_type_comment": runner_source.replace('server_time=cell["server_time"])', 'server_time=cell["server_time"])  # type: object', 1),
        "type_ignore": runner_source.replace("CAPTURE_ENTRYPOINT = \"_execute_declared_cell\"", "CAPTURE_ENTRYPOINT = \"_execute_declared_cell\"  # type: ignore", 1),
        "default_argument": runner_source.replace("operation):", "operation=None):", 1),
        "kwonly_default": runner_source.replace("operation):", "operation, *, forged=None):", 1),
        "async_function": runner_source.replace("def _execute_declared_cell", "async def _execute_declared_cell", 1),
        "generator": runner_source.replace("return result", "yield result", 1),
    }
    if _parser_supports_type_parameters():
        mutations["type_parameters"] = runner_source.replace("def _execute_declared_cell", "def _execute_declared_cell[T]", 1)
    for name, candidate in mutations.items():
        try:
            _validate_runner(candidate)
        except MatrixError:
            continue
        raise MatrixError(f"static self-test mutation accepted: {name}")


def _isolated_locked_runner(*, runner_path: Path, binding_map_path: Path) -> None:
    """Validate the externally lock-verified runner without importing it."""
    try:
        binding_map = json.loads(binding_map_path.read_text(encoding="utf-8"))
        runner_source = runner_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as error:
        raise MatrixError("isolated locked grammar inputs are unreadable") from error
    if not isinstance(binding_map, dict):
        raise MatrixError("isolated locked binding map must be an object")
    verify_static_matrix(
        binding_map=binding_map,
        runner_source=runner_source,
        recipe_source=Path(__file__).read_text(encoding="utf-8"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isolated-locked-runner", type=Path)
    parser.add_argument("--binding-map", type=Path)
    args = parser.parse_args()
    if args.isolated_locked_runner is None or args.binding_map is None:
        parser.error("--isolated-locked-runner and --binding-map are required")
    try:
        _isolated_locked_runner(
            runner_path=args.isolated_locked_runner,
            binding_map_path=args.binding_map,
        )
    except MatrixError as error:
        print(f"static AST grammar rejected locked runner: {error}", file=sys.stderr)
        return 64
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
