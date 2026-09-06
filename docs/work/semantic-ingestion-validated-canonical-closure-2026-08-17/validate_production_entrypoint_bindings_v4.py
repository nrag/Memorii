from __future__ import annotations

import ast
import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v4.json"
EXPECTED = HERE / "production-entrypoint-expected-rows-v1.json"
OUTPUT = HERE / "production-entrypoint-bindings-v4-validation.json"
ROW_FIELDS = (
    "status", "production_trigger", "current_production_anchor", "target_callsite",
    "authority_bindings", "ordered_owner_chain", "call_edges", "validation_boundary",
    "durable_outcome", "fallback_branch", "planned_proof_ids",
)


def _text(relative: str) -> str:
    path = ROOT / relative
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _definition_name(symbol: str) -> str:
    if symbol.startswith("def "):
        return symbol[4:].split("(", 1)[0]
    if symbol.startswith("class "):
        return symbol[6:].split("(", 1)[0].split(":", 1)[0]
    return symbol.split(".")[-1]


def _find_definition(relative: str, symbol: str) -> ast.AST | None:
    text = _text(relative)
    if not text:
        return None
    name = _definition_name(symbol)
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return node
    return None


def _attribute_calls(node: ast.AST, attribute: str) -> int:
    return sum(
        1 for item in ast.walk(node)
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == attribute
    )


def _owner_paths(row: dict[str, object]) -> set[str]:
    paths = set()
    for owner in row["ordered_owner_chain"]:
        relative = owner.split("::", 1)[0]
        paths.add(f"memorii/memorii/core/{relative}")
    anchor = row["current_production_anchor"]
    paths.update((anchor["from_path"], anchor["to_path"]))
    return paths


def validate(ledger: dict[str, object], expected: dict[str, object]) -> list[str]:
    failures: list[str] = []
    rows = ledger.get("requirements", [])
    expected_rows = expected.get("rows", {})
    if {row.get("id") for row in rows} != set(expected_rows) or len(rows) != 12:
        failures.append("requirement_set")
    proof_catalog = expected.get("proof_catalog", {})
    for row in rows:
        rid = row["id"]
        projection = {field: row.get(field) for field in ROW_FIELDS}
        if projection != expected_rows.get(rid):
            failures.append(f"{rid}:expected_row_contract")
        anchor = row["current_production_anchor"]
        from_node = _find_definition(anchor["from_path"], anchor["from_symbol"])
        to_node = _find_definition(anchor["to_path"], anchor["to_symbol"])
        scoped_count = _attribute_calls(from_node, "sync_event") if from_node is not None else 0
        if to_node is None or scoped_count != anchor["captured_non_test_callers"]:
            failures.append(f"{rid}:symbol_scoped_anchor")
        parameters = row["target_callsite"]["parameters"]
        if [item["parameter"] for item in row["authority_bindings"]] != parameters:
            failures.append(f"{rid}:authority_binding")
        chain = row["ordered_owner_chain"]
        if [(edge["from_owner"], edge["to_owner"]) for edge in row["call_edges"]] != list(zip(chain, chain[1:])):
            failures.append(f"{rid}:ordered_edges")
        connected = _owner_paths(row)
        validation = row["validation_boundary"]
        if validation["path"] not in connected or _find_definition(validation["path"], validation["symbol"]) is None:
            failures.append(f"{rid}:connected_validation")
        durable = row["durable_outcome"]
        if durable["path"] not in connected or _find_definition(durable["path"], durable["symbol"]) is None:
            failures.append(f"{rid}:connected_durable")
        fallback = row["fallback_branch"]
        if fallback["path"] not in connected or fallback["token"] not in _text(fallback["path"]):
            failures.append(f"{rid}:connected_fallback")
        for proof_id in row["planned_proof_ids"]:
            entry = proof_catalog.get(proof_id)
            if entry != {"phase": "implementation", "gate": proof_id.lower().replace("-", "_"), "required": True}:
                failures.append(f"{rid}:proof_catalog")
        if rid == "VCC-R08":
            if durable["mode"] != "no_durable_write" or "persistence.py" in durable["path"]:
                failures.append("VCC-R08:no_durable_write")
    return failures


def _mutations(ledger: dict[str, object], expected: dict[str, object]) -> dict[str, bool]:
    cases: list[tuple[str, dict[str, object], dict[str, object]]] = []
    coordinated_parameters = copy.deepcopy(ledger)
    row = coordinated_parameters["requirements"][0]
    row["target_callsite"]["parameters"][0] = "coordinated_wrong"
    row["authority_bindings"][0]["parameter"] = "coordinated_wrong"
    cases.append(("coordinated_parameter_binding", coordinated_parameters, expected))
    coordinated_chain = copy.deepcopy(ledger)
    row = coordinated_chain["requirements"][1]
    row["ordered_owner_chain"][1] = "semantic_ingestion/missing.py::missing"
    row["call_edges"][0]["to_owner"] = row["ordered_owner_chain"][1]
    row["call_edges"][1]["from_owner"] = row["ordered_owner_chain"][1]
    cases.append(("coordinated_chain_edges", coordinated_chain, expected))
    unrelated_fallback = copy.deepcopy(ledger)
    unrelated_fallback["requirements"][2]["fallback_branch"]["token"] = "encode_typed_value"
    cases.append(("unrelated_fallback_token", unrelated_fallback, expected))
    outside_anchor = copy.deepcopy(ledger)
    outside_anchor["requirements"][3]["current_production_anchor"]["captured_non_test_callers"] = 5
    cases.append(("repository_wide_instead_of_scoped_count", outside_anchor, expected))
    wrong_durable = copy.deepcopy(ledger)
    wrong_durable["requirements"][4]["durable_outcome"]["mode"] = "wrong_semantics"
    cases.append(("wrong_durable_semantics", wrong_durable, expected))
    no_write = copy.deepcopy(ledger)
    no_write["requirements"][7]["durable_outcome"].update({
        "mode": "unchanged_persistence",
        "path": "memorii/memorii/core/semantic_ingestion/persistence.py",
        "symbol": "def persist(",
    })
    cases.append(("no_durable_write_violation", no_write, expected))
    missing_proof = copy.deepcopy(expected)
    proof_id = ledger["requirements"][8]["planned_proof_ids"][0]
    del missing_proof["proof_catalog"][proof_id]
    cases.append(("missing_proof_catalog_entry", ledger, missing_proof))
    return {name: bool(validate(mutated_ledger, mutated_expected)) for name, mutated_ledger, mutated_expected in cases}


def main() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    failures = validate(ledger, expected)
    mutations = _mutations(ledger, expected)
    if not all(mutations.values()):
        failures.append("mutation_self_test")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v4",
        "passed": not failures,
        "requirement_count": len(ledger["requirements"]),
        "symbol_scoped_capture_cell_call_count": 1,
        "mutation_results": mutations,
        "failures": failures,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
