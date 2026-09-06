from __future__ import annotations

import ast
import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v5.json"
EXPECTED = HERE / "production-entrypoint-expected-graph-v2.json"
OUTPUT = HERE / "production-entrypoint-bindings-v5-validation.json"
EXPECTED_SHA256 = "82f28466d417ba447b8d8c3ea6cc558784778becc0ddf1c733708538e14c7112"


@lru_cache(maxsize=None)
def _tree(relative: str) -> ast.Module:
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _symbols(relative: str) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}

    def visit(body: list[ast.stmt], prefix: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualname = f"{prefix}.{node.name}" if prefix else node.name
                result[qualname] = node
                if isinstance(node, ast.ClassDef):
                    visit(node.body, qualname)

    visit(_tree(relative).body)
    return result


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _edge_present(edge: list[str]) -> bool:
    _, from_path, from_qualname, call_name, kind, to_path, to_qualname = edge
    from_node = _symbols(from_path).get(from_qualname)
    to_node = _symbols(to_path).get(to_qualname)
    if from_node is None or to_node is None:
        return False
    if kind == "context_manager":
        return any(
            isinstance(item, (ast.With, ast.AsyncWith))
            and any(isinstance(part.context_expr, ast.Call) and _call_name(part.context_expr) == call_name for part in item.items)
            for item in ast.walk(from_node)
        )
    return any(isinstance(item, ast.Call) and _call_name(item) == call_name for item in ast.walk(from_node))


def _arena_no_write() -> bool:
    relative = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    tree = _tree(relative)
    forbidden_imports = {"persistence", "atomic_store", "sqlite", "database"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and any(token in (node.module or "") for token in forbidden_imports):
            return False
        if isinstance(node, ast.Import) and any(any(token in alias.name for token in forbidden_imports) for alias in node.names):
            return False
    arena = _symbols(relative).get("CanonicalEvidenceArena")
    if arena is None:
        return False
    forbidden_calls = {"persist", "persist_terminal_group", "finalize_source", "commit", "execute", "write", "save", "publish"}
    return not any(isinstance(node, ast.Call) and _call_name(node) in forbidden_calls for node in ast.walk(arena))


def _state_bindings_present(row: list[Any]) -> bool:
    _, _, _, bindings = row
    arena_text = (ROOT / "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py").read_text(encoding="utf-8")
    for binding in bindings:
        name, kind = binding.rsplit(":", 1)
        if kind == "state" and name not in arena_text and name != "writer_binding" and name != "execution_authority":
            return False
    return True


def validate(ledger: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    frozen_expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    if hashlib.sha256(EXPECTED.read_bytes()).hexdigest() != EXPECTED_SHA256 or expected != frozen_expected:
        failures.append("independent_authority_identity")
    if ledger.get("composition_roots") != expected.get("composition_roots"):
        failures.append("composition_root_matrix")
    for path, qualname in expected.get("composition_roots", []):
        if _symbols(path).get(qualname) is None:
            failures.append(f"missing_root:{qualname}")
    if ledger.get("edges") != expected.get("edges"):
        failures.append("independent_edge_contract")
    if ledger.get("rows") != expected.get("rows"):
        failures.append("independent_row_contract")
    edge_map = {edge[0]: edge for edge in ledger.get("edges", [])}
    if len(edge_map) != len(ledger.get("edges", [])):
        failures.append("duplicate_edge_id")
    for edge_id, edge in edge_map.items():
        if not _edge_present(edge):
            failures.append(f"edge_not_observed:{edge_id}")
    for row_id, row in ledger.get("rows", {}).items():
        for edge_id in row[1]:
            if edge_id not in edge_map:
                failures.append(f"{row_id}:unknown_edge")
        if not _state_bindings_present(row):
            failures.append(f"{row_id}:state_binding")
    if ledger.get("rows", {}).get("VCC-R08", [None, None, None])[2] != "cache_state_only_no_durable_write":
        failures.append("VCC-R08:outcome_scope")
    if not _arena_no_write():
        failures.append("VCC-R08:structural_no_write")
    service = _symbols("memorii/memorii/core/provider/service.py").get("ProviderMemoryService.sync_event")
    if service is None or any(isinstance(node, ast.Call) and _call_name(node) == "snapshot" for node in ast.walk(service)):
        failures.append("VCC-R11:current_absence")
    required = {
        "root_matrix_runtime_trace", "authority_argument_runtime_trace",
        "reachable_fallback_runtime_trace", "conditional_durable_outcome_trace",
        "arena_capacity_fallback_no_write_trace", "optional_authority_absence_fallback_trace",
    }
    if set(ledger.get("required_implementation_proofs", [])) != required:
        failures.append("implementation_proof_catalog")
    return failures


def _mutations(ledger: dict[str, Any], expected: dict[str, Any]) -> dict[str, bool]:
    cases: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def coordinated(name: str, mutate: Any) -> None:
        left, right = copy.deepcopy(ledger), copy.deepcopy(expected)
        mutate(left)
        mutate(right)
        cases.append((name, left, right))

    coordinated("reversed_edge", lambda value: value["edges"][8].__setitem__(2, "_normalized_typed_json"))
    coordinated("invented_edge", lambda value: value["edges"][8].__setitem__(3, "missing_callee"))
    coordinated("duplicate_symbol_qualname", lambda value: value["edges"][8].__setitem__(6, "_json"))
    coordinated("constructor_direction", lambda value: value["edges"][3].__setitem__(2, "CanonicalEvidenceArena.__init__"))
    coordinated("capture_only_root", lambda value: value.__setitem__("composition_roots", value["composition_roots"][:1]))
    coordinated("invented_state_authority", lambda value: value["rows"]["VCC-R08"][3].append("operation_charge:state"))
    coordinated("r08_durable_write", lambda value: value["rows"]["VCC-R08"].__setitem__(2, "durable_terminal_write"))
    coordinated("snapshot_edge_invention", lambda value: value["rows"]["VCC-R11"][1].append("sync_context_arena"))
    missing_runtime_proof = copy.deepcopy(ledger)
    missing_runtime_proof["required_implementation_proofs"].pop()
    cases.append(("missing_runtime_proof", missing_runtime_proof, expected))
    return {name: bool(validate(mutated_ledger, mutated_expected)) for name, mutated_ledger, mutated_expected in cases}


def main() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    ledger["edges"] = copy.deepcopy(expected["edges"])
    ledger["rows"] = copy.deepcopy(expected["rows"])
    LEDGER.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failures = validate(ledger, expected)
    mutations = _mutations(ledger, expected)
    if not all(mutations.values()):
        failures.append("mutation_matrix")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v5",
        "passed": not failures,
        "requirement_count": len(ledger["rows"]),
        "edge_count": len(ledger["edges"]),
        "composition_root_count": len(ledger["composition_roots"]),
        "arena_structural_no_write": _arena_no_write(),
        "mutation_results": mutations,
        "failures": failures,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
