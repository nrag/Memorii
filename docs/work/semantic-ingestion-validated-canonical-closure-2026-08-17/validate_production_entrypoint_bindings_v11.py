"""Validate the generated v11 sealed-authority production binding contract."""

from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v11.json"
ORACLE = HERE / "production-owner-oracle-v8.json"
EXPECTED = HERE / "production-entrypoint-expected-graph-v11.json"
OUTPUT = HERE / "production-entrypoint-bindings-v11-validation.json"

def validate(contract: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str]) -> list[str]:
    failures = []
    for key in ("schema", "family", "edges", "forbidden_ambient_tokens", "expected_mutation_names", "source_hashes"):
        if contract.get(key) != oracle.get(key):
            failures.append(f"contract:{key}")
    for edge_id, path, marker in oracle["edges"]:
        if marker not in sources[path]:
            failures.append(f"missing_edge:{edge_id}")
    for path, token in oracle["forbidden_ambient_tokens"]:
        if token in sources[path]:
            failures.append(f"ambient_token:{path}:{token}")
    for path, expected in oracle["source_hashes"].items():
        if sha256(sources[path].encode()).hexdigest() != expected:
            failures.append(f"source_hash:{path}")
    return sorted(set(failures))

def _mutations(contract: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str]) -> dict[str, bool]:
    results = {}
    for name in oracle["expected_mutation_names"]:
        candidate, shadow = copy.deepcopy(contract), dict(sources)
        if name.startswith("remove_"):
            edge_id = name.removeprefix("remove_")
            _, path, marker = next(item for item in oracle["edges"] if item[0] == edge_id)
            shadow[path] = shadow[path].replace(marker, "removed_marker", 1)
        elif name.startswith("forbidden_"):
            path, token = oracle["forbidden_ambient_tokens"][int(name.removeprefix("forbidden_"))]
            shadow[path] += "\n" + token + "\n"
        elif name.startswith("disconnect_"):
            edge_id = name.removeprefix("disconnect_")
            candidate["edges"] = [item for item in candidate["edges"] if item[0] != edge_id]
        else:
            shadow["memorii/memorii/core/memory_evolution/atomic_store.py"] = shadow["memorii/memorii/core/memory_evolution/atomic_store.py"].replace(
                "scope." + name.removeprefix("scope_"), "missing_scope_coordinate", 1
            )
        results[name] = bool(validate(candidate, oracle, shadow))
    return results

def main() -> None:
    before_ledger, before_oracle, before_expected = LEDGER.read_bytes(), ORACLE.read_bytes(), EXPECTED.read_bytes()
    contract, oracle, expected_graph = json.loads(before_ledger), json.loads(before_oracle), json.loads(before_expected)
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for path in oracle["source_hashes"]}
    failures = validate(contract, oracle, sources)
    if expected_graph != oracle:
        failures.append("expected_graph")
    mutations = _mutations(contract, oracle, sources) if not failures else {}
    expected = oracle["expected_mutation_names"]
    failures.extend(name for name in expected if not mutations.get(name, False))
    if len(mutations) != 32 or len(expected) != 32:
        failures.append("mutation_count")
    if LEDGER.read_bytes() != before_ledger or ORACLE.read_bytes() != before_oracle or EXPECTED.read_bytes() != before_expected:
        failures.append("input_mutation")
    result = {"schema": "memorii.production-entrypoint-bindings-validation.v11", "passed": not failures, "failures": sorted(set(failures)), "read_only_inputs": True, "mutation_results": mutations, "mutation_count": len(mutations), "expected_mutation_count": len(expected)}
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
