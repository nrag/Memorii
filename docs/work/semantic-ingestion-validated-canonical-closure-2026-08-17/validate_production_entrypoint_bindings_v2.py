from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LEDGER = Path(__file__).with_name("production-entrypoint-bindings-v2.json")
OUTPUT = Path(__file__).with_name("production-entrypoint-bindings-v2-validation.json")


def _owner_path(owner: str) -> Path:
    relative = owner.split("::", 1)[0]
    return ROOT / "memorii" / "memorii" / "core" / relative


def main() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    expected = {f"VCC-R{index:02d}" for index in range(1, 13)}
    rows = ledger["requirements"]
    ids = {row["id"] for row in rows}
    failures: list[str] = []
    if ledger.get("candidate_manifest") != "candidate-manifest-v2.json":
        failures.append("missing_candidate_manifest_binding")
    if ids != expected or len(rows) != 12:
        failures.append("missing_requirement")

    roots = [ROOT / item for item in ledger["production_trigger_census"]["roots"]]
    pattern = re.compile(ledger["production_trigger_census"]["pattern"])
    callers: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            if any(part in {"test", "tests", "benchmark", "tools"} for part in path.parts):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and not line.lstrip().startswith("def "):
                    callers.append(f"{path.relative_to(ROOT)}:{number}")
    if len(callers) < ledger["production_trigger_census"]["minimum_non_test_callers"]:
        failures.append("zero_production_caller")

    checked_owners: set[str] = set()
    for row in rows:
        for field in ("trigger", "production_caller_count_source", "composition_root", "authority_arguments", "owner_chain", "mapping_tokens", "fallback", "behavioral_proof"):
            if not row.get(field):
                failures.append(f"{row['id']}:missing_{field}")
        for owner in row["owner_chain"]:
            path = _owner_path(owner)
            checked_owners.add(str(path.relative_to(ROOT)))
            if not path.is_file():
                failures.append(f"{row['id']}:missing_owner:{owner}")
        corpus = "\n".join(
            _owner_path(owner).read_text(encoding="utf-8")
            for owner in row["owner_chain"]
            if _owner_path(owner).is_file()
        )
        for token in row["mapping_tokens"]:
            if token not in corpus:
                failures.append(f"{row['id']}:missing_token:{token}")

    writer_results: list[dict[str, object]] = []
    for writer in ledger["durable_writers"]:
        path = ROOT / writer["path"]
        present = path.is_file() and writer["symbol"] in path.read_text(encoding="utf-8")
        writer_results.append({**writer, "present": present})
        if not present:
            failures.append(f"missing_durable_writer:{writer['path']}::{writer['symbol']}")

    global_guards = {
        "removed_handoff": (ROOT / "memorii/memorii/core/provider/ingestion.py", "_bootstrap_prepare_and_handoff"),
        "omitted_authority_argument": (ROOT / "memorii/memorii/core/provider/service.py", "verified_production_host_authority"),
        "bypass_fallback": (ROOT / "memorii/memorii/core/provider/ingestion.py", "source_only"),
    }
    guard_results: dict[str, bool] = {}
    for name, (path, token) in global_guards.items():
        present = path.is_file() and token in path.read_text(encoding="utf-8")
        guard_results[name] = present
        if not present:
            failures.append(name)

    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v2",
        "passed": not failures,
        "requirement_count": len(rows),
        "production_non_test_caller_count": len(callers),
        "production_non_test_callers": callers,
        "checked_owner_count": len(checked_owners),
        "durable_writers": writer_results,
        "global_guards": guard_results,
        "failures": failures,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
