from __future__ import annotations

import copy
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LEDGER = Path(__file__).with_name("production-entrypoint-bindings-v3.json")
OUTPUT = Path(__file__).with_name("production-entrypoint-bindings-v3-validation.json")


def _text(relative: str) -> str:
    path = ROOT / relative
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _caller_count(anchor: dict[str, object]) -> int:
    pattern = re.compile(str(anchor["caller_query_pattern"]))
    excluded = set(anchor["excluded_path_parts"])
    count = 0
    for relative in anchor["caller_query_roots"]:
        for path in (ROOT / str(relative)).rglob("*.py"):
            if excluded.intersection(path.parts):
                continue
            count += sum(
                1
                for line in path.read_text(encoding="utf-8").splitlines()
                if pattern.search(line) and not line.lstrip().startswith("def ")
            )
    return count


def validate(ledger: dict[str, object]) -> list[str]:
    failures: list[str] = []
    rows = ledger.get("requirements", [])
    expected = {f"VCC-R{index:02d}" for index in range(1, 13)}
    if {row.get("id") for row in rows} != expected or len(rows) != 12:
        failures.append("requirements")
    for row in rows:
        rid = row["id"]
        if row.get("status") != "planned":
            failures.append(f"{rid}:status")
        anchor = row["current_production_anchor"]
        from_text = _text(anchor["from_path"])
        to_text = _text(anchor["to_path"])
        if anchor["from_symbol"] not in from_text or anchor["edge_token"] not in from_text or anchor["to_symbol"] not in to_text:
            failures.append(f"{rid}:production_anchor_edge")
        if _caller_count(anchor) != anchor["captured_non_test_callers"]:
            failures.append(f"{rid}:caller_count")
        target = row["target_callsite"]
        parameters = target.get("parameters", [])
        bindings = row.get("authority_bindings", [])
        if [item.get("parameter") for item in bindings] != parameters or not parameters:
            failures.append(f"{rid}:authority_parameters")
        if any(item.get("status") != "planned" or not item.get("proof_id") for item in bindings):
            failures.append(f"{rid}:authority_proofs")
        chain = row.get("ordered_owner_chain", [])
        edges = row.get("call_edges", [])
        expected_edges = list(zip(chain, chain[1:]))
        actual_edges = [(edge.get("from_owner"), edge.get("to_owner")) for edge in edges]
        if actual_edges != expected_edges or any(edge.get("status") != "planned" or not edge.get("proof_id") for edge in edges):
            failures.append(f"{rid}:ordered_edges")
        boundary = row["validation_boundary"]
        if boundary["status"] != "existing" or boundary["symbol"] not in _text(boundary["path"]):
            failures.append(f"{rid}:validation_boundary")
        durable = row["durable_outcome"]
        if durable["status"] != "existing" or durable["symbol"] not in _text(durable["path"]) or not durable.get("mode"):
            failures.append(f"{rid}:durable_outcome")
        fallback = row["fallback_branch"]
        if fallback["status"] != "existing" or fallback["token"] not in _text(fallback["path"]):
            failures.append(f"{rid}:fallback")
        proofs = row.get("planned_proof_ids", [])
        if len(proofs) < 3 or any(not str(item).startswith(rid) for item in proofs):
            failures.append(f"{rid}:planned_proofs")
    return failures


def _mutation_results(ledger: dict[str, object]) -> dict[str, bool]:
    mutations = {}
    cases = []
    wrong_authority = copy.deepcopy(ledger)
    wrong_authority["requirements"][0]["authority_bindings"][0]["parameter"] = "wrong_parameter"
    cases.append(("wrong_authority_parameter", wrong_authority))
    disconnected = copy.deepcopy(ledger)
    disconnected["requirements"][1]["call_edges"][0]["to_owner"] = "disconnected.py::missing"
    cases.append(("disconnected_owner_edge", disconnected))
    wrong_count = copy.deepcopy(ledger)
    wrong_count["requirements"][2]["current_production_anchor"]["captured_non_test_callers"] += 1
    cases.append(("wrong_row_caller_count", wrong_count))
    missing_writer = copy.deepcopy(ledger)
    missing_writer["requirements"][3]["durable_outcome"]["symbol"] = "missing_writer_symbol"
    cases.append(("missing_durable_writer", missing_writer))
    missing_fallback = copy.deepcopy(ledger)
    missing_fallback["requirements"][4]["fallback_branch"]["token"] = "missing_fallback_token"
    missing_fallback["requirements"][4]["planned_proof_ids"] = []
    cases.append(("missing_fallback_and_proof", missing_fallback))
    for name, mutated in cases:
        mutations[name] = bool(validate(mutated))
    return mutations


def main() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    failures = validate(ledger)
    mutations = _mutation_results(ledger)
    if not all(mutations.values()):
        failures.append("mutation_self_test")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v3",
        "passed": not failures,
        "requirement_count": len(ledger["requirements"]),
        "row_local_caller_count": ledger["requirements"][0]["current_production_anchor"]["captured_non_test_callers"],
        "mutation_results": mutations,
        "failures": failures,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
