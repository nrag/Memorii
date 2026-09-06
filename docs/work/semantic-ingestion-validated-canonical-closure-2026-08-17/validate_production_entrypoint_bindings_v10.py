from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v10.json"
ORACLE = HERE / "production-owner-oracle-v7.json"
OUTPUT = HERE / "production-entrypoint-bindings-v10-validation.json"
V9 = HERE / "validate_production_entrypoint_bindings_v9.py"

spec = importlib.util.spec_from_file_location("vcc_binding_v9", V9)
if spec is None or spec.loader is None:
    raise RuntimeError("v9 binding validator unavailable")
v9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v9)
BASE_VALIDATE = v9.validate


def _runtime_identity() -> dict[str, Any]:
    return {
        "implementation": sys.implementation.name,
        "major": sys.version_info.major,
        "minor": sys.version_info.minor,
    }


def _class_dump(source: str, name: str) -> str:
    tree = ast.parse(source)
    owner = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name),
        None,
    )
    if owner is None:
        return ""
    return ast.dump(owner, annotate_fields=True, include_attributes=False)


def validate(
    ledger: dict[str, Any],
    oracle: dict[str, Any],
    sources: dict[str, str],
    *,
    enforce_hashes: bool,
) -> list[str]:
    contract = oracle["semantic_source_contracts"]
    if _runtime_identity() != contract["python_ast_runtime"]:
        return ["unsupported_ast_runtime"]
    failures = BASE_VALIDATE(ledger, oracle, sources, enforce_hashes=enforce_hashes)
    if ledger["semantic_source_contracts"] != contract:
        failures.append("semantic_source_contract")
    hermes = "memorii/memorii/integrations/hermes_provider.py"
    arena = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    if _class_dump(sources[hermes], "HermesMemoryProvider") != contract["hermes_class_ast"]:
        failures.append("hermes_owner_class_ast")
    if _class_dump(sources[arena], "CanonicalEvidenceArena") != contract["arena_class_ast"]:
        failures.append("R08_arena_owner_class_ast")
    return sorted(set(failures))


class _AliasServiceWrite(ast.NodeTransformer):
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        if node.name != "sync_event":
            return node
        alias = ast.Assign(
            targets=[ast.Name(id="receiver", ctx=ast.Store())],
            value=ast.Name(id="self", ctx=ast.Load()),
        )
        if self.mode == "attribute":
            write: ast.stmt = ast.Assign(
                targets=[ast.Attribute(value=ast.Name(id="receiver", ctx=ast.Load()), attr="_service", ctx=ast.Store())],
                value=ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[]),
            )
        else:
            write = ast.Expr(
                value=ast.Call(
                    func=ast.Name(id="setattr", ctx=ast.Load()),
                    args=[ast.Name(id="receiver", ctx=ast.Load()), ast.Constant("_service"), ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[])],
                    keywords=[],
                )
            )
        node.body[0:0] = [alias, write]
        return node


class _MappingServiceWrite(ast.NodeTransformer):
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        if node.name != "sync_event":
            return node
        if self.mode == "update":
            write: ast.stmt = ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="__dict__", ctx=ast.Load()), attr="update", ctx=ast.Load()),
                    args=[],
                    keywords=[ast.keyword(arg="_service", value=ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[]))],
                )
            )
        else:
            write = ast.Assign(
                targets=[ast.Subscript(value=ast.Call(func=ast.Name(id="vars", ctx=ast.Load()), args=[ast.Name(id="self", ctx=ast.Load())], keywords=[]), slice=ast.Constant("_service"), ctx=ast.Store())],
                value=ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[]),
            )
        node.body.insert(0, write)
        return node


class _ArenaReceiverProxy(ast.NodeTransformer):
    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.generic_visit(node)
        if node.name == "CanonicalEvidenceArena":
            node.body.append(
                ast.FunctionDef(
                    name="injected_receiver_proxy",
                    args=ast.arguments(posonlyargs=[], args=[ast.arg(arg="self")], kwonlyargs=[], kw_defaults=[], defaults=[]),
                    body=[ast.Assign(targets=[ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="_entries", ctx=ast.Store())], value=ast.Call(func=ast.Name(id="DurableProxy", ctx=ast.Load()), args=[], keywords=[]))],
                    decorator_list=[],
                )
            )
        return node


def _mutate(source: str, transformer: ast.NodeTransformer) -> str:
    tree = transformer.visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _mutations(
    ledger: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str]
) -> dict[str, bool]:
    original = v9.validate
    v9.validate = validate
    try:
        cases = v9._mutations(ledger, oracle, sources)
    finally:
        v9.validate = original
    hermes = "memorii/memorii/integrations/hermes_provider.py"
    arena = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    attacks = {
        "alias_attribute_service_write": (hermes, _mutate(sources[hermes], _AliasServiceWrite("attribute"))),
        "alias_setattr_service_write": (hermes, _mutate(sources[hermes], _AliasServiceWrite("setattr"))),
        "dict_update_service_write": (hermes, _mutate(sources[hermes], _MappingServiceWrite("update"))),
        "vars_service_write": (hermes, _mutate(sources[hermes], _MappingServiceWrite("vars"))),
        "arena_receiver_proxy": (arena, _mutate(sources[arena], _ArenaReceiverProxy())),
    }
    for name, (path, shadow) in attacks.items():
        cases[name] = bool(
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
    mutations = _mutations(ledger, oracle, sources) if not failures else {}
    failures.extend(f"mutation_survived:{name}" for name, detected in mutations.items() if not detected)
    if LEDGER.read_bytes() != ledger_before or ORACLE.read_bytes() != oracle_before:
        failures.append("input_mutation")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v10",
        "passed": not failures,
        "failures": failures,
        "read_only_inputs": True,
        "python_ast_runtime": _runtime_identity(),
        "mutation_results": mutations,
        "mutation_count": len(mutations),
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
