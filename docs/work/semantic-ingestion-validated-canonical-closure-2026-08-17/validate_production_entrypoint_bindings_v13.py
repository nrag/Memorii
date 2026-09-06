"""Validate v13 construction-safe writer-admission bindings."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v13.json"
OUTPUT = HERE / "production-entrypoint-bindings-v13-validation.json"
def main() -> None:
    ledger = json.loads(LEDGER.read_text())
    failures = []
    for name, path, marker in ledger["edges"]:
        source = (ROOT / path).read_text()
        if marker not in source:
            failures.append(name)
        if sha256(source.encode()).hexdigest() != ledger["source_hashes"][path]:
            failures.append("hash:" + path)
    if any(count < 1 for count in ledger["caller_counts"].values()):
        failures.append("caller_count")
    result = {"passed": not failures, "failures": failures, "validated_edges": len(ledger["edges"]), "caller_counts": ledger["caller_counts"]}
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)
if __name__ == "__main__":
    main()
