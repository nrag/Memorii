"""Validate the revision-bound Hermes Level 2 production entrypoint map."""

from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[3]
PREFLIGHT = Path(__file__).with_name("production-entrypoint-preflight.json")
LEDGER = ROOT / "docs/design/semantic_ingestion_canonical_evidence/production-entrypoint-bindings-v1.json"
REQUIREMENT = "hermes_level2_completed_turn_memory"


def _method_calls(path: Path, class_name: str, method_name: str, call_name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
    )
    return sum(
        isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == call_name
            or isinstance(node.func, ast.Name)
            and node.func.id == call_name
        )
        for node in ast.walk(method)
    )


def _method_string_literals(path: Path, class_name: str, method_name: str, value: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
    )
    return sum(
        isinstance(node, ast.Constant) and node.value == value for node in ast.walk(method)
    )


def main() -> None:
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = [
        row
        for row in ledger["production_entrypoint_bindings"]
        if row.get("requirement") == REQUIREMENT
    ]
    if len(rows) != 1:
        raise SystemExit("Hermes Level 2 binding ledger row is missing or duplicated")
    row = rows[0]
    if row["mapper_preflight"]["artifact"] != str(PREFLIGHT.relative_to(ROOT)):
        raise SystemExit("Hermes Level 2 binding ledger does not name the preflight artifact")
    if preflight["mapped_revision"] != row["mapper_preflight"]["baseline_revision"]:
        raise SystemExit("Hermes Level 2 binding revision is mismatched")
    for relative, expected in preflight["source_sha256"].items():
        actual = sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"Hermes Level 2 mapped source changed: {relative}")

    project = tomllib.loads((ROOT / "memorii/pyproject.toml").read_text(encoding="utf-8"))
    if project["project"]["entry-points"]["hermes_agent.memory_providers"] != {
        "memorii": "memorii.integrations.hermes_memory_provider:MemoriiHermesMemoryProvider"
    }:
        raise SystemExit("installed Hermes memory-provider entry point is not singular")
    if project["project"]["entry-points"]["memorii.hermes.provider_service"] != {
        "installed": "memorii.integrations.hermes_factory:build_local_level2_runtime_binding"
    }:
        raise SystemExit("installed Hermes service factory entry point is not singular")

    bridge = ROOT / "memorii/memorii/integrations/hermes_memory_provider.py"
    repository = ROOT / "memorii/memorii/core/semantic_ingestion/source_normalization_repository.py"
    observed = {
        "installed_hermes_provider_entrypoint": 1,
        "installed_hermes_service_factory_entrypoint": 1,
        "bridge_to_completed_turn_sync": _method_string_literals(
            bridge, "MemoriiHermesMemoryProvider", "sync_turn", "sync_completed_turn"
        ),
        "bridge_to_completed_turn_prefetch": _method_calls(
            bridge, "MemoriiHermesMemoryProvider", "prefetch", "prefetch"
        ) - 1,
        "recovery_repository_to_atomic_renewal": repository.read_text(
            encoding="utf-8"
        ).count("self._atomic_store.renew_or_abort_bootstrap_v3_recovery("),
    }
    if observed != preflight["production_caller_counts"]:
        raise SystemExit(
            "Hermes Level 2 production caller census changed: "
            f"expected={preflight['production_caller_counts']!r} actual={observed!r}"
        )

    required_symbols = {
        "memorii/memorii/integrations/hermes_factory.py": (
            "service.reconcile_memory_evolution()",
            "service.activate_observation_ledger()",
        ),
        "memorii/memorii/core/memory_evolution/atomic_store.py": (
            "def renew_or_abort_bootstrap_v3_recovery(",
        ),
        "memorii/memorii/core/memory_evolution/writer_admission.py": (
            "class SemanticGovernedWritePolicy:",
        ),
        "memorii/memorii/core/semantic_ingestion/hermes_completed_turn_runtime.py": (
            "def sync_completed_turn(",
            "def _process(",
            "def prefetch(",
            "def close(",
        ),
    }
    for relative, symbols in required_symbols.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        missing = [symbol for symbol in symbols if symbol not in source]
        if missing:
            raise SystemExit(f"Hermes Level 2 owner chain changed in {relative}: {missing}")

    print(json.dumps({
        "mapping_id": preflight["mapping_id"],
        "mapped_revision": preflight["mapped_revision"],
        "production_caller_counts": observed,
        "result": "valid",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
