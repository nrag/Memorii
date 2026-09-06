from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v6.json"
ORACLE = HERE / "production-owner-oracle-v3.json"
OUTPUT = HERE / "production-entrypoint-bindings-v6-validation.json"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _owner(tree: ast.Module, qualname: str) -> ast.AST | None:
    parts = qualname.split(".")
    body: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for part in parts:
        node = next((item for item in body if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == part), None)
        if node is None:
            return None
        body = node.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else []
    return node


def _imports(tree: ast.Module) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                result[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split('.')[0]] = alias.name
    return result


def _call(owner: ast.AST, expression: str, required_keywords: list[str]) -> ast.Call | None:
    for node in ast.walk(owner):
        if not isinstance(node, ast.Call) or ast.unparse(node.func) != expression:
            continue
        keywords = {item.arg for item in node.keywords if item.arg is not None}
        if set(required_keywords).issubset(keywords):
            return node
    return None


def _binding_valid(edge: list[Any], trees: dict[str, ast.Module]) -> bool:
    _, from_path, from_qualname, expression, keywords, to_path, to_qualname, binding, *rest = edge
    tree = trees[from_path]
    node = _owner(tree, from_qualname)
    call = None if node is None else _call(node, expression, keywords)
    if node is None or _owner(trees[to_path], to_qualname) is None or call is None:
        return False
    target_class = to_qualname.split(".")[0]
    target_terminal = to_qualname.split(".")[-1]
    expression_terminal = expression.split(".")[-1]
    expected_terminal = target_class if target_terminal == "__init__" else target_terminal
    if expression_terminal != expected_terminal:
        return False
    expected_keywords = rest[0] if rest else {}
    actual_keywords = {
        item.arg: ast.unparse(item.value)
        for item in call.keywords
        if item.arg is not None
    }
    if any(actual_keywords.get(name) != value for name, value in expected_keywords.items()):
        return False
    if binding == "self_method":
        return from_qualname.split(".")[0] == target_class
    if binding == "same_module" or binding == "same_class":
        return from_path == to_path
    if binding.startswith("import:"):
        name = binding.split(":", 1)[1]
        imported = _imports(tree).get(name, "")
        expected = "memorii." + to_path.removeprefix("memorii/memorii/").removesuffix(".py").replace("/", ".")
        return imported.startswith(expected) and imported.endswith(name)
    if binding.startswith("parameter:"):
        receiver = expression.split(".", 1)[0]
        args = node.args.args + node.args.kwonlyargs if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else []
        arg = next((item for item in args if item.arg == receiver), None)
        return arg is not None and arg.annotation is not None and binding.split(":", 1)[1] in ast.unparse(arg.annotation)
    if binding.startswith("field:"):
        class_name = from_qualname.split(".")[0]
        class_node = _owner(tree, class_name)
        if not isinstance(class_node, ast.ClassDef):
            return False
        init = next((item for item in class_node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
        field = expression.split(".")[1]
        expected = binding.split(":", 1)[1]
        if init is None:
            return False
        text = ast.unparse(init)
        return f"self.{field}" in text and expected in text
    return False


def _arena_no_write(source: str, durable_modules: list[str]) -> bool:
    tree = ast.parse(source)
    imports = _imports(tree)
    if any(any(module == durable or module.startswith(durable + ".") for durable in durable_modules) for module in imports.values()):
        return False
    arena = _owner(tree, "CanonicalEvidenceArena")
    if arena is None:
        return False
    return not any(
        isinstance(node, ast.Call)
        and ((isinstance(node.func, ast.Attribute) and node.func.attr in {"persist", "persist_terminal_group", "finalize_source", "commit", "write"})
             or (isinstance(node.func, ast.Name) and node.func.id in {"persist", "commit", "write"}))
        for node in ast.walk(arena)
    )


def validate(ledger: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str], *, enforce_hashes: bool) -> list[str]:
    failures: list[str] = []
    if enforce_hashes:
        for path, expected in oracle["source_hashes"].items():
            if _sha(sources[path].encode()) != expected:
                failures.append(f"source_hash:{path}")
    if set(ledger["triggers"]) != set(oracle["allowed_trigger_ids"]):
        failures.append("trigger_inventory")
    if set(ledger["composition_roots"]) != set(oracle["composition_root_ids"]):
        failures.append("composition_inventory")
    if ledger["excluded_roots"] != {"capture_child": "memorii/memorii/core/semantic_ingestion/production_capture.py::_capture_child"}:
        failures.append("capture_exclusion")
    if set(ledger["rows"]) != set(oracle["required_rows"]):
        failures.append("row_inventory")
    trees = {path: ast.parse(text) for path, text in sources.items()}
    edge_map = {edge[0]: edge for edge in ledger["edges"]}
    if len(edge_map) != len(ledger["edges"]):
        failures.append("edge_identity")
    for edge_id, edge in edge_map.items():
        if not _binding_valid(edge, trees):
            failures.append(f"edge_binding:{edge_id}")
    for row_id, row in ledger["rows"].items():
        for segment in row["segments"]:
            if any(edge_id not in edge_map for edge_id in segment):
                failures.append(f"row_edge:{row_id}")
                continue
            for left, right in zip(segment, segment[1:]):
                if edge_map[left][6] != edge_map[right][2] or edge_map[left][5] != edge_map[right][1]:
                    failures.append(f"row_connectivity:{row_id}")
    if ledger["rows"]["VCC-R08"]["outcome"] != "cache_state_only_no_durable_write":
        failures.append("R08_outcome")
    arena_path = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    if not _arena_no_write(sources[arena_path], oracle["durable_modules"]):
        failures.append("R08_durable_sink")
    service = _owner(trees["memorii/memorii/core/provider/service.py"], "ProviderMemoryService._resolve_ingress")
    if service is None or "return None" not in ast.unparse(service):
        failures.append("authority_fallback")
    return failures


def _mutations(ledger: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str]) -> dict[str, bool]:
    cases: dict[str, bool] = {}
    def ledger_case(name: str, mutate: Any) -> None:
        candidate = copy.deepcopy(ledger); mutate(candidate)
        cases[name] = bool(validate(candidate, oracle, sources, enforce_hashes=False))
    ledger_case("wrong_target_same_name", lambda value: value["edges"][0].__setitem__(6, "ProviderMemoryService._sync_composite_event"))
    ledger_case("reversed_constructor", lambda value: value["edges"][4].__setitem__(2, "CanonicalEvidenceArena.__init__"))
    ledger_case("disconnected_row", lambda value: value["rows"]["VCC-R01"]["segments"][0].insert(1, "semantic_encode"))
    ledger_case("capture_root", lambda value: value["triggers"].__setitem__("capture_child", value["excluded_roots"]["capture_child"]))
    ledger_case("missing_authority_keyword", lambda value: value["edges"][5][4].append("missing_authority"))
    ledger_case("R08_relabelled_durable", lambda value: value["rows"]["VCC-R08"].__setitem__("outcome", "durable_terminal_write"))
    hermes = "memorii/memorii/integrations/hermes_provider.py"
    shadow = dict(sources); shadow[hermes] = shadow[hermes].replace("self._service.sync_event(", "other.sync_event(", 1)
    cases["wrong_receiver_source"] = bool(validate(ledger, oracle, shadow, enforce_hashes=False))
    service_path = "memorii/memorii/core/provider/service.py"
    shadow = dict(sources); shadow[service_path] = shadow[service_path].replace("arena_nonce=canonical_evidence_arena.nonce,", "arena_nonce=None,", 1)
    cases["substituted_authority_source"] = bool(validate(ledger, oracle, shadow, enforce_hashes=False))
    arena = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    shadow = dict(sources); shadow[arena] = "from memorii.core.semantic_ingestion.persistence import SemanticTerminalPersistenceService\n" + shadow[arena].replace("    def close(self) -> None:", "    def injected(self):\n        SemanticTerminalPersistenceService.persist(self)\n\n    def close(self) -> None:")
    cases["direct_durable_sink_source"] = bool(validate(ledger, oracle, shadow, enforce_hashes=False))
    shadow = dict(sources); shadow[arena] = "import memorii.core.semantic_ingestion.persistence as durable_alias\n" + shadow[arena].replace("    def close(self) -> None:", "    def injected(self):\n        durable_alias.SemanticTerminalPersistenceService.persist(self)\n\n    def close(self) -> None:")
    cases["aliased_durable_sink_source"] = bool(validate(ledger, oracle, shadow, enforce_hashes=False))
    return cases


def main() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for path in oracle["source_hashes"]}
    ledger_before, oracle_before = LEDGER.read_bytes(), ORACLE.read_bytes()
    failures = validate(ledger, oracle, sources, enforce_hashes=True)
    mutations = _mutations(ledger, oracle, sources)
    if not all(mutations.values()):
        failures.append("mutation_matrix")
    if LEDGER.read_bytes() != ledger_before or ORACLE.read_bytes() != oracle_before:
        failures.append("validator_not_read_only")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v6",
        "passed": not failures,
        "source_hash_count": len(sources),
        "trigger_count": len(ledger["triggers"]),
        "composition_root_count": len(ledger["composition_roots"]),
        "edge_count": len(ledger["edges"]),
        "row_count": len(ledger["rows"]),
        "read_only_inputs": True,
        "arena_no_write": _arena_no_write(sources["memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"], oracle["durable_modules"]),
        "mutation_results": mutations,
        "failures": failures,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
