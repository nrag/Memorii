from __future__ import annotations

import ast
import inspect
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
PACKAGE = ROOT / "memorii/memorii"
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
sys.path.insert(0, str(VECTORS))

import run_scenario_ingress as runner
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion import contracts
from memorii.core.semantic_ingestion.canonical_evidence_arena import CanonicalEvidenceArena
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_scenario_test_provider_service,
)


RELEVANT_CALLS = {
    "model_validate",
    "model_construct",
    "model_copy",
    "encode_semantic_contract",
    "decode_semantic_contract",
    "encode_typed_value",
    "decode_typed_value",
}


def _category(path: str, symbol: str, operation: str) -> tuple[str, str]:
    lowered = f"{path}:{symbol}".lower()
    if operation in {"decode_semantic_contract", "decode_typed_value"}:
        return "mandatory_decode", "closed bytes must be decoded and revalidated"
    if operation == "model_construct":
        return "mandatory_constructed", "construction bypass has no validation authority"
    if any(value in lowered for value in ("recover", "reload", "replay", "from_record", "load_", "read_")):
        return "mandatory_reload_recovery", "persisted or recovered state requires fresh validation"
    if "atomic_store.py" in path or "persistence.py" in path or "repository.py" in path:
        return "mandatory_persistence_transaction", "storage and transaction boundaries require validation"
    if "/provider/" in path or "/integrations/" in path:
        return "mandatory_provider", "provider and integration boundaries require validation"
    if operation == "model_copy":
        return "mandatory_copy_or_candidate_unknown", "copy authority depends on the subsequent owner and mutation path"
    if operation in {"encode_semantic_contract", "encode_typed_value"}:
        return "mandatory_codec_or_candidate_repeat", "canonical output is mandatory but repeated internal requests may be reusable"
    if any(
        value in path
        for value in (
            "source_preparation.py",
            "source_admission.py",
            "record_projection.py",
            "linguistic_adapters.py",
            "/semantic_analysis/",
        )
    ):
        return "candidate_internal_composition", "internal typed composition with no observed persistence crossing"
    return "unknown", "owner and input authority require manual classification"


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _enclosing_symbol(parents: dict[ast.AST, ast.AST], node: ast.AST) -> str:
    current = parents.get(node)
    names: list[str] = []
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(current.name)
        current = parents.get(current)
    return ".".join(reversed(names)) or "<module>"


def _is_dump_revalidate(node: ast.Call) -> bool:
    if _call_name(node) != "model_validate" or not node.args:
        return False
    argument = node.args[0]
    return (
        isinstance(argument, ast.Call)
        and isinstance(argument.func, ast.Attribute)
        and argument.func.attr == "model_dump"
    )


def _static_census() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            operation = _call_name(node)
            if operation not in RELEVANT_CALLS:
                continue
            symbol = _enclosing_symbol(parents, node)
            category, reason = _category(relative, symbol, operation)
            dump_revalidate = _is_dump_revalidate(node)
            if dump_revalidate and category == "unknown":
                category = "candidate_dump_revalidate"
                reason = "same-expression model dump followed by typed validation"
            rows.append(
                {
                    "path": relative,
                    "line": node.lineno,
                    "symbol": symbol,
                    "operation": operation,
                    "category": category,
                    "reason": reason,
                    "has_context": any(keyword.arg == "context" for keyword in node.keywords),
                    "dump_revalidate": dump_revalidate,
                }
            )
    rows.sort(key=lambda row: (row["path"], row["line"], row["operation"]))
    counts = Counter(row["category"] for row in rows)
    operation_counts = Counter(row["operation"] for row in rows)
    return {
        "callsite_count": len(rows),
        "category_counts": dict(sorted(counts.items())),
        "operation_counts": dict(sorted(operation_counts.items())),
        "context_bearing_callsites": sum(bool(row["has_context"]) for row in rows),
        "dump_revalidate_callsites": sum(bool(row["dump_revalidate"]) for row in rows),
        "callsites": rows,
    }


def _runtime_census() -> dict[str, object]:
    world = json.loads((VECTORS / "scenario-first-v1.json").read_text(encoding="utf-8"))
    scenario = runner.validate(world)[0]
    observation = runner.render(scenario)[0]
    operation_id = runner._opaque_event_id(ordinal=0, source_bytes=observation.text.encode("utf-8"))
    service = build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: datetime(2026, 7, 30, tzinfo=UTC),
    )
    reservations = [CanonicalEvidenceArena() for _ in range(64)]
    original = contracts.contract_digest
    calls = 0
    origins: Counter[tuple[str, str, int, str, str, str]] = Counter()

    def observed(domain: bytes, value: object) -> str:
        nonlocal calls
        result = original(domain, value)
        caller = inspect.currentframe()
        caller = caller.f_back if caller is not None else None
        contract = caller.f_locals.get("self") if caller is not None else None
        if not isinstance(contract, contracts._ContentAddressedContract):
            return result
        calls += 1
        frame = caller.f_back
        origin = None
        while frame is not None:
            filename = Path(frame.f_code.co_filename).resolve()
            try:
                relative = filename.relative_to(PACKAGE.resolve()).as_posix()
            except ValueError:
                relative = None
            if relative is not None and relative != "core/semantic_ingestion/contracts.py":
                origin = (relative, frame.f_lineno, frame.f_code.co_name)
                break
            frame = frame.f_back
        if origin is None:
            origin = ("core/semantic_ingestion/contracts.py", 0, "nested_validation")
        category, reason = _category(origin[0], origin[2], "model_validate")
        origins[(type(contract).__name__, origin[0], origin[1], origin[2], category, reason)] += 1
        return result

    contracts.contract_digest = observed
    try:
        service.sync_event(
            operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
            content=observation.text,
            operation_id=operation_id,
            session_id=runner._PUBLIC_SCOPE[1],
            task_id=runner._PUBLIC_SCOPE[2],
            user_id=runner._PUBLIC_SCOPE[0],
            language="en",
            speaker_id="scenario-speaker",
            timestamp=observation.timestamp,
            authenticated_host_ingress=runner._host_ingress(ordinal=0),
        )
    finally:
        contracts.contract_digest = original
        for arena in reservations:
            arena.close()
    rows = [
        {
            "contract_type": key[0],
            "path": key[1],
            "line": key[2],
            "symbol": key[3],
            "category": key[4],
            "reason": key[5],
            "calls": count,
        }
        for key, count in origins.items()
    ]
    rows.sort(key=lambda row: (-row["calls"], row["path"], row["line"], row["contract_type"]))
    category_counts: Counter[str] = Counter()
    for row in rows:
        category_counts[row["category"]] += row["calls"]
    return {
        "content_validation_calls": calls,
        "origin_count": len(rows),
        "category_call_counts": dict(sorted(category_counts.items())),
        "origins": rows,
    }


def main() -> None:
    static = _static_census()
    runtime = _runtime_census()
    result = {
        "schema": "memorii.semantic-ingestion.validation-boundary.census.v1",
        "experiment": "VBP-EXP-001",
        "evidence_stage": "reference_only_feasibility",
        "certifies_m3_1": False,
        "candidate_lock_sha256": "24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3",
        "classification_rule": "heuristic classifications select experiments only; unknown and mandatory classes cannot be optimized without manual owner proof",
        "static": static,
        "runtime": runtime,
    }
    output = Path(__file__).with_name("evidence") / "vbp-exp-001-boundary-census-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "static_callsite_count": static["callsite_count"],
                "static_category_counts": static["category_counts"],
                "static_context_bearing": static["context_bearing_callsites"],
                "static_dump_revalidate": static["dump_revalidate_callsites"],
                "runtime_content_validation_calls": runtime["content_validation_calls"],
                "runtime_origin_count": runtime["origin_count"],
                "runtime_category_call_counts": runtime["category_call_counts"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
