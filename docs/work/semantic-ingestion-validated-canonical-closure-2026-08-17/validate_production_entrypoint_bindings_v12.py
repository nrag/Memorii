"""Validate the generated v12 ingress-gated writer-admission binding map."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v12.json"
OUTPUT = HERE / "production-entrypoint-bindings-v12-validation.json"


def main() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    failures: list[str] = []
    for edge_id, path, marker in ledger["edges"]:
        source = (ROOT / path).read_text(encoding="utf-8")
        if marker not in source:
            failures.append(f"missing_edge:{edge_id}")
        if sha256(source.encode()).hexdigest() != ledger["source_hashes"].get(path):
            failures.append(f"hash_drift:{path}")
    for root, details in ledger["production_roots"].items():
        if details["caller_count"] < 1:
            failures.append(f"zero_production_callers:{root}")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v12",
        "passed": not failures,
        "failures": failures,
        "validated_edges": len(ledger["edges"]),
        "production_roots": ledger["production_roots"],
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
