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


TARGETS = {
    contracts.SemanticProjectionTextArtifact,
    contracts.ProjectionTextSpan,
    contracts.SegmentLocalTextArtifact,
    contracts.SegmentLocalTextSpan,
    contracts.RetainedSourceTextArtifact,
}
TARGET_NAMES = {target.__name__ for target in TARGETS}


def _runtime_inventory() -> tuple[int, list[dict[str, object]]]:
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
    all_target_calls = 0
    origins: Counter[tuple[str, str, int, str, bool]] = Counter()

    def observed(domain: bytes, value: object) -> str:
        nonlocal all_target_calls
        result = original(domain, value)
        caller = inspect.currentframe()
        caller = caller.f_back if caller is not None else None
        contract = caller.f_locals.get("self") if caller is not None else None
        if type(contract) not in TARGETS:
            return result
        all_target_calls += 1
        frame = caller.f_back
        encode_boundary = False
        origin = None
        while frame is not None:
            filename = Path(frame.f_code.co_filename).resolve()
            if frame.f_code.co_name == "encode_semantic_contract":
                encode_boundary = True
            try:
                relative = filename.relative_to(PACKAGE.resolve()).as_posix()
            except ValueError:
                relative = None
            if relative is not None and relative != "core/semantic_ingestion/contracts.py":
                origin = (relative, frame.f_lineno, frame.f_code.co_name)
                break
            frame = frame.f_back
        if origin is None:
            origin = ("<contracts-owner>", 0, "nested_validation")
        origins[(type(contract).__name__, origin[0], origin[1], origin[2], encode_boundary)] += 1
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
            "origin_path": key[1],
            "origin_line": key[2],
            "origin_symbol": key[3],
            "under_encode_semantic_contract": key[4],
            "calls": count,
        }
        for key, count in origins.items()
    ]
    rows.sort(key=lambda row: (-row["calls"], row["contract_type"], row["origin_path"], row["origin_line"]))
    return all_target_calls, rows


def _static_inventory() -> dict[str, object]:
    direct_calls: list[dict[str, object]] = []
    validation_calls = 0
    context_validation_calls = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(PACKAGE).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "model_validate":
                validation_calls += 1
                if any(keyword.arg == "context" for keyword in node.keywords):
                    context_validation_calls += 1
            owner = node.func.value
            if (
                node.func.attr in {"create", "model_validate", "model_construct"}
                and isinstance(owner, ast.Name)
                and owner.id in TARGET_NAMES
            ):
                direct_calls.append(
                    {
                        "contract_type": owner.id,
                        "operation": node.func.attr,
                        "path": relative,
                        "line": node.lineno,
                        "has_context": any(keyword.arg == "context" for keyword in node.keywords),
                    }
                )
    direct_calls.sort(key=lambda row: (row["contract_type"], row["path"], row["line"]))
    return {
        "all_model_validate_callsites": validation_calls,
        "context_bearing_model_validate_callsites": context_validation_calls,
        "context_free_model_validate_callsites": validation_calls - context_validation_calls,
        "direct_target_callsites": direct_calls,
        "direct_target_callsite_count": len(direct_calls),
    }


def main() -> None:
    target_calls, runtime_origins = _runtime_inventory()
    static = _static_inventory()
    runtime_origin_calls = sum(row["calls"] for row in runtime_origins)
    if target_calls == 0 or runtime_origin_calls != target_calls:
        raise RuntimeError("runtime origin inventory is incomplete")
    encode_calls = sum(
        row["calls"] for row in runtime_origins if row["under_encode_semantic_contract"]
    )
    result = {
        "schema": "memorii.semantic-ingestion.codec-attestation.propagation-inventory.v1",
        "experiment": "COA-EXP-002B",
        "evidence_stage": "read_only_feasibility",
        "certifies_m3_1": False,
        "target_contract_types": sorted(TARGET_NAMES),
        "runtime_target_validation_calls": target_calls,
        "runtime_origin_count": len(runtime_origins),
        "runtime_calls_under_encode_semantic_contract": encode_calls,
        "runtime_calls_outside_encode_semantic_contract": target_calls - encode_calls,
        "runtime_origins": runtime_origins,
        "static_inventory": static,
    }
    output = Path(__file__).with_name("evidence") / "coa-exp-002b-propagation-inventory-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runtime_origins" and key != "static_inventory"} | {"static_summary": {key: value for key, value in static.items() if key != "direct_target_callsites"}}, sort_keys=True))


if __name__ == "__main__":
    main()
