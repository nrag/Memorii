"""Validate v14 writer-admission production binding evidence and mutation coverage."""

from __future__ import annotations

import ast
import copy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v14.json"
OUTPUT = HERE / "production-entrypoint-bindings-v14-validation.json"
EXPECTED_ROWS = {
    "direct_sync_event",
    "direct_apply_memory_write",
    "repository_factory",
    "configured_hermes_sync_turn",
    "configured_hermes_memory_write",
    "filesystem_root",
}
REQUIRED_ROW_KEYS = {
    "row_id", "requirement_ids", "trigger", "composition_root",
    "authority_and_authenticated_ingress_arguments", "ordered_validation_chain",
    "durable_or_no_write_outcome", "fallback_or_fail_closed_behavior",
    "production_caller_census", "behavioral_test_node_ids",
}
CHAIN = [
    "ProviderMemoryService._resolve_ingress(authenticated_host_ingress)",
    "ProviderMemoryService._ensure_writer_admission_record()",
    "SemanticWriterAdmissionStore.current() or create_initial_evidence_only()",
    "ProviderMemoryService._validate_semantic_runtime_after_ingress()",
    "ProviderIngestionCoordinator.ingest()",
]


def _calls_named(name: str, sources: dict[str, str]) -> int:
    return sum(
        sum(
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == name)
                or (isinstance(node.func, ast.Name) and node.func.id == name)
            )
            for node in ast.walk(ast.parse(source, filename=path))
        )
        for path, source in sources.items()
        if path.startswith("memorii/memorii/")
    )


def _method_source(source: str, class_name: str, method_name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return "".join(lines[item.lineno - 1:item.end_lineno])
    return ""


def validate(ledger: dict[str, Any], sources: dict[str, str]) -> list[str]:
    failures: list[str] = []
    if ledger.get("schema") != "memorii.production-entrypoint-bindings.v14":
        failures.append("schema")
    if ledger.get("supersedes") != "production-entrypoint-bindings-v13.json":
        failures.append("supersedes")
    rows = ledger.get("rows")
    if not isinstance(rows, list):
        return [*failures, "rows"]
    row_ids = {row.get("row_id") for row in rows if isinstance(row, dict)}
    if row_ids != EXPECTED_ROWS or len(rows) != len(EXPECTED_ROWS):
        failures.append("root_trigger_set")
    service = sources["memorii/memorii/core/provider/service.py"]
    preflight = _method_source(service, "ProviderMemoryService", "_preflight_ingress")
    if preflight.find("ingress = self._resolve_ingress(authenticated_host_ingress)") > preflight.find("self._ensure_writer_admission_record()"):
        failures.append("pre_resolution_order")
    if "if ingress is not None:\n            self._ensure_writer_admission_record()" not in preflight:
        failures.append("writer_gate")
    for row in rows:
        if not isinstance(row, dict):
            failures.append("row_type")
            continue
        row_id = row.get("row_id", "unknown")
        if set(row) != REQUIRED_ROW_KEYS:
            failures.append(f"row_schema:{row_id}")
            continue
        if row.get("requirement_ids") != ["VCC-R02", "VCC-R03", "VCC-R10"]:
            failures.append(f"requirements:{row_id}")
        if row.get("ordered_validation_chain") != CHAIN:
            failures.append(f"chain:{row_id}")
        trigger = row.get("trigger")
        if not isinstance(trigger, dict) or set(trigger) != {"path", "symbol"}:
            failures.append(f"trigger_schema:{row_id}")
        elif trigger["symbol"].split(".")[-1] not in sources[trigger["path"]]:
            failures.append(f"trigger:{row_id}")
        authority = row.get("authority_and_authenticated_ingress_arguments")
        if not isinstance(authority, list) or not any("authenticated" in item for item in authority):
            failures.append(f"authority_arguments:{row_id}")
        census = row.get("production_caller_census")
        if not isinstance(census, dict) or set(census) != {"symbol", "count", "query"}:
            failures.append(f"census_schema:{row_id}")
        elif census["count"] != _calls_named(census["symbol"], sources) or census["count"] < 1:
            failures.append(f"caller_count:{row_id}")
    for path, expected in ledger.get("source_hashes", {}).items():
        if path not in sources or sha256(sources[path].encode("utf-8")).hexdigest() != expected:
            failures.append(f"source_hash:{path}")
    hermes = sources["memorii/memorii/integrations/hermes_provider.py"]
    if any(
        "authenticated_host_ingress=authenticated_host_ingress"
        not in _method_source(hermes, "HermesMemoryProvider", method)
        for method in ("sync_event", "sync_turn", "on_memory_write")
    ):
        failures.append("authority_forwarding")
    return sorted(set(failures))


def _mutations(ledger: dict[str, Any], sources: dict[str, str]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    candidate = copy.deepcopy(ledger)
    candidate["rows"] = candidate["rows"][1:]
    results["omitted_root"] = bool(validate(candidate, sources))
    candidate = copy.deepcopy(ledger)
    candidate["rows"][0]["trigger"]["symbol"] = "ProviderMemoryService.missing_sync_event"
    results["omitted_trigger"] = bool(validate(candidate, sources))
    shadow = dict(sources)
    path = "memorii/memorii/integrations/hermes_provider.py"
    old = "return self._service.apply_memory_write("
    start = shadow[path].index(old)
    offset = shadow[path][start:].index("authenticated_host_ingress=authenticated_host_ingress")
    position = start + offset
    shadow[path] = (
        shadow[path][:position]
        + "authenticated_host_ingress=None"
        + shadow[path][position + len("authenticated_host_ingress=authenticated_host_ingress"):]
    )
    results["authority_forwarding"] = bool(validate(ledger, shadow))
    shadow = dict(sources)
    path = "memorii/memorii/core/provider/service.py"
    shadow[path] = shadow[path].replace(
        "ingress = self._resolve_ingress(authenticated_host_ingress)",
        "ingress = None\n        self._ensure_writer_admission_record()\n        ingress = self._resolve_ingress(authenticated_host_ingress)",
        1,
    )
    results["pre_resolution_order"] = bool(validate(ledger, shadow))
    candidate = copy.deepcopy(ledger)
    candidate["rows"][0]["production_caller_census"]["count"] += 1
    results["unrelated_fake_count"] = bool(validate(candidate, sources))
    return results


def main() -> None:
    original = LEDGER.read_bytes()
    ledger = json.loads(original)
    sources = {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in (ROOT / "memorii/memorii").rglob("*.py")
    }
    sources.update({
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in ledger["source_hashes"]
        if path not in sources
    })
    failures = validate(ledger, sources)
    mutations = _mutations(ledger, sources) if not failures else {}
    expected = {"omitted_root", "omitted_trigger", "authority_forwarding", "pre_resolution_order", "unrelated_fake_count"}
    failures.extend(name for name in expected if not mutations.get(name, False))
    if LEDGER.read_bytes() != original:
        failures.append("input_mutation")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v14",
        "passed": not failures,
        "failures": sorted(set(failures)),
        "mutation_results": mutations,
        "mutation_count": len(mutations),
        "expected_mutation_count": len(expected),
        "read_only_input": True,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
