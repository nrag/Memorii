from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v9.json"
ORACLE = HERE / "production-owner-oracle-v6.json"
OUTPUT = HERE / "production-entrypoint-bindings-v9-validation.json"
V8 = HERE / "validate_production_entrypoint_bindings_v8.py"

spec = importlib.util.spec_from_file_location("vcc_binding_v8", V8)
if spec is None or spec.loader is None:
    raise RuntimeError("v8 binding validator unavailable")
v8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v8)
BASE_VALIDATE = v8.validate
v6 = v8.v6


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _owner(tree: ast.Module, qualname: str) -> ast.AST:
    node = v6._owner(tree, qualname)
    if node is None:
        raise ValueError(f"missing_owner:{qualname}")
    return node


def _targets(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.Assign):
        return node.targets
    if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
        return [node.target]
    if isinstance(node, ast.Delete):
        return node.targets
    return []


def _service_write(target: ast.AST) -> bool:
    if isinstance(target, ast.Attribute):
        return (
            isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "_service"
        )
    if isinstance(target, ast.Subscript):
        text = ast.unparse(target)
        return "_service" in text or "self.__dict__" in text or "vars(self)" in text
    return False


def _reflective_service_write(node: ast.Call) -> bool:
    function = ast.unparse(node.func)
    if function not in {"setattr", "object.__setattr__", "self.__setattr__"}:
        return False
    if len(node.args) < 2 or ast.unparse(node.args[0]) != "self":
        return False
    field = node.args[1]
    return not isinstance(field, ast.Constant) or field.value == "_service"


def _exact_source_contracts(
    ledger: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str]
) -> list[str]:
    failures: list[str] = []
    if ledger["semantic_source_contracts"] != oracle["semantic_source_contracts"]:
        failures.append("semantic_source_contract")
    if ledger["instance_bridges"] != oracle["instance_bridges"]:
        failures.append("instance_bridge_contract")
    contract = oracle["semantic_source_contracts"]

    hermes_path = "memorii/memorii/integrations/hermes_provider.py"
    hermes_tree = ast.parse(sources[hermes_path])
    hermes_class = _owner(hermes_tree, "HermesMemoryProvider")
    hermes_init = _owner(hermes_tree, "HermesMemoryProvider.__init__")
    assert isinstance(hermes_class, ast.ClassDef)
    assert isinstance(hermes_init, ast.FunctionDef)
    if ast.dump(hermes_init, annotate_fields=True, include_attributes=False) != contract["hermes_init_ast"]:
        failures.append("hermes_init_ast")
    service_arg = next(
        (item for item in hermes_init.args.args + hermes_init.args.kwonlyargs if item.arg == "service"),
        None,
    )
    if service_arg is None or service_arg.annotation is None or ast.unparse(service_arg.annotation) != contract["hermes_service_annotation"]:
        failures.append("hermes_service_annotation")
    service_if = next(
        (
            item
            for item in hermes_init.body
            if isinstance(item, ast.If)
            and any(
                isinstance(node, ast.Attribute) and node.attr == "_service"
                for node in ast.walk(item)
            )
        ),
        None,
    )
    predicates: list[str] = []
    if isinstance(service_if, ast.If):
        predicates.append(ast.unparse(service_if.test))
        nested = service_if.orelse[0] if len(service_if.orelse) == 1 else None
        if isinstance(nested, ast.If):
            predicates.extend((ast.unparse(nested.test), "else"))
    if predicates != contract["hermes_branch_predicates"]:
        failures.append("hermes_branch_predicates")
    for method in hermes_class.body:
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) or method.name == "__init__":
            continue
        for node in ast.walk(method):
            if any(_service_write(target) for target in _targets(node)):
                failures.append("hermes_service_write_outside_constructor")
            if isinstance(node, ast.Call) and _reflective_service_write(node):
                failures.append("hermes_reflective_service_write")

    bundle_path = "memorii/memorii/core/filesystem_storage/bundle.py"
    bundle_tree = ast.parse(sources[bundle_path])
    function = _owner(bundle_tree, "build_filesystem_provider")
    assert isinstance(function, ast.FunctionDef)
    returns = [item for item in function.body if isinstance(item, ast.Return)]
    if len(returns) != 1 or ast.dump(returns[0], annotate_fields=True, include_attributes=False) != contract["filesystem_provider_return_ast"]:
        failures.append("filesystem_provider_instance_dataflow")
    for path in ledger["composition_root_trigger_paths"]["filesystem_factory"]:
        if "instance:filesystem_provider_chain" not in path:
            failures.append("filesystem_instance_bridge_path")

    arena_path = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    arena_tree = ast.parse(sources[arena_path])
    arena_class = _owner(arena_tree, "CanonicalEvidenceArena")
    assert isinstance(arena_class, ast.ClassDef)
    calls = sorted(ast.unparse(node.func) for node in ast.walk(arena_class) if isinstance(node, ast.Call))
    if sorted(set(calls)) != contract["arena_call_allowlist"]:
        failures.append("R08_arena_call_allowlist")
    if calls != contract["arena_call_multiset"]:
        failures.append("R08_arena_call_multiset")
    return sorted(set(failures))


def validate(
    ledger: dict[str, Any],
    oracle: dict[str, Any],
    sources: dict[str, str],
    *,
    enforce_hashes: bool,
) -> list[str]:
    failures = BASE_VALIDATE(ledger, oracle, sources, enforce_hashes=enforce_hashes)
    failures.extend(_exact_source_contracts(ledger, oracle, sources))
    return sorted(set(failures))


class _AppendReflectiveWrite(ast.NodeTransformer):
    def __init__(self, function: str) -> None:
        self.function = function

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        if node.name == "__init__":
            func: ast.expr
            if self.function == "setattr":
                func = ast.Name(id="setattr", ctx=ast.Load())
            else:
                func = ast.Attribute(value=ast.Name(id="object", ctx=ast.Load()), attr="__setattr__", ctx=ast.Load())
            node.body.append(
                ast.Expr(
                    value=ast.Call(
                        func=func,
                        args=[ast.Name(id="self", ctx=ast.Load()), ast.Constant("_service"), ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[])],
                        keywords=[],
                    )
                )
            )
        return node


class _AppendDictWrite(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        if node.name == "__init__":
            node.body.append(
                ast.Assign(
                    targets=[ast.Subscript(value=ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="__dict__", ctx=ast.Load()), slice=ast.Constant("_service"), ctx=ast.Store())],
                    value=ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[]),
                )
            )
        return node


class _DetachFilesystemReturn(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        if node.name == "build_filesystem_provider":
            node.body = [
                ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id="FilesystemStorageBundle", ctx=ast.Load()), attr="from_root", ctx=ast.Load()), args=[], keywords=[])),
                ast.Return(value=ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[])),
            ]
        return node


def _mutate(source: str, transformer: ast.NodeTransformer) -> str:
    tree = transformer.visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _mutations(
    ledger: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str]
) -> dict[str, bool]:
    original = v8.validate
    v8.validate = validate
    try:
        cases = v8._mutations(ledger, oracle, sources)
    finally:
        v8.validate = original
    hermes = "memorii/memorii/integrations/hermes_provider.py"
    bundle = "memorii/memorii/core/filesystem_storage/bundle.py"
    arena = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    shadows = {
        "widened_service_annotation": sources[hermes].replace("service: ProviderMemoryService | None", "service: ProviderMemoryService | object | None"),
        "container_service_annotation": sources[hermes].replace("service: ProviderMemoryService | None", "service: list[ProviderMemoryService] | None"),
        "service_guard_bypass": sources[hermes].replace("if service is not None:", "if True:", 1),
        "setattr_service_write": _mutate(sources[hermes], _AppendReflectiveWrite("setattr")),
        "object_setattr_service_write": _mutate(sources[hermes], _AppendReflectiveWrite("object.__setattr__")),
        "dict_service_write": _mutate(sources[hermes], _AppendDictWrite()),
        "detached_filesystem_instance": _mutate(sources[bundle], _DetachFilesystemReturn()),
        "dispatch_table_durable_sink": sources[arena].replace("    def close(self) -> None:", "    def injected_dispatch_sink(self) -> None:\n        dispatch = {\"persist\": self.persist}\n        dispatch[\"persist\"]()\n\n    def close(self) -> None:"),
    }
    for name, shadow in shadows.items():
        path = bundle if name == "detached_filesystem_instance" else arena if name == "dispatch_table_durable_sink" else hermes
        cases[name] = shadow != sources[path] and bool(
            validate(ledger, oracle, {**sources, path: shadow}, enforce_hashes=False)
        )
    return cases


def main() -> None:
    ledger_before = LEDGER.read_bytes()
    oracle_before = ORACLE.read_bytes()
    ledger = json.loads(ledger_before)
    oracle = json.loads(oracle_before)
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for path in oracle["source_hashes"]}
    failures = validate(ledger, oracle, sources, enforce_hashes=True)
    mutations = _mutations(ledger, oracle, sources)
    failures.extend(f"mutation_survived:{name}" for name, detected in mutations.items() if not detected)
    if LEDGER.read_bytes() != ledger_before or ORACLE.read_bytes() != oracle_before:
        failures.append("input_mutation")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v9",
        "passed": not failures,
        "failures": failures,
        "read_only_inputs": True,
        "trigger_count": len(ledger["triggers"]),
        "composition_root_count": len(ledger["composition_roots"]),
        "composition_branch_count": len(ledger["composition_branches"]),
        "root_path_count": sum(len(paths) for paths in ledger["composition_root_trigger_paths"].values()),
        "edge_count": len(ledger["edges"]),
        "row_count": len(ledger["rows"]),
        "source_hash_count": len(oracle["source_hashes"]),
        "arena_allowed_call_count": len(oracle["semantic_source_contracts"]["arena_call_allowlist"]),
        "mutation_results": mutations,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
