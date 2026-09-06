from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "production-entrypoint-bindings-v7.json"
ORACLE = HERE / "production-owner-oracle-v4.json"
OUTPUT = HERE / "production-entrypoint-bindings-v7-validation.json"
V6 = HERE / "validate_production_entrypoint_bindings_v6.py"

spec = importlib.util.spec_from_file_location("vcc_binding_v6", V6)
if spec is None or spec.loader is None:
    raise RuntimeError("v6 binding validator unavailable")
v6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v6)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _split_owner(value: str) -> tuple[str, str]:
    path, separator, qualname = value.partition("::")
    if not separator or not path or not qualname:
        raise ValueError("invalid_owner_coordinate")
    return path, qualname


def _assigned_fields(class_node: ast.ClassDef) -> set[str]:
    init = next(
        (
            item
            for item in class_node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "__init__"
        ),
        None,
    )
    if init is None:
        return set()
    fields: set[str] = set()
    for node in ast.walk(init):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        for target in targets:
            for candidate in ast.walk(target):
                if (
                    isinstance(candidate, ast.Attribute)
                    and isinstance(candidate.value, ast.Name)
                    and candidate.value.id == "self"
                ):
                    fields.add(candidate.attr)
    return fields


def _production_census(trees: dict[str, ast.Module]) -> tuple[set[str], set[str]]:
    hermes_path = "memorii/memorii/integrations/hermes_provider.py"
    service_path = "memorii/memorii/core/provider/service.py"
    hermes = v6._owner(trees[hermes_path], "HermesMemoryProvider")
    service = v6._owner(trees[service_path], "ProviderMemoryService")
    if not isinstance(hermes, ast.ClassDef) or not isinstance(service, ast.ClassDef):
        return set(), set()
    hermes_calls = {
        "self._service.sync_event",
        "self._service._sync_composite_event",
        "self._service.apply_memory_write",
    }
    hermes_owners = {
        f"{hermes_path}::HermesMemoryProvider.{method.name}"
        for method in hermes.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(node, ast.Call) and ast.unparse(node.func) in hermes_calls
            for node in ast.walk(method)
        )
    }
    service_owners = {
        f"{service_path}::ProviderMemoryService.{method.name}"
        for method in service.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(node, ast.Call)
            and ast.unparse(node.func) == "CanonicalEvidenceArena"
            for node in ast.walk(method)
        )
        and any(
            isinstance(node, ast.Call)
            and ast.unparse(node.func)
            in {"self._ingest_event", "self._provider_ingestion.ingest"}
            for node in ast.walk(method)
        )
    }
    return hermes_owners, service_owners


def _dynamic_durable_dispatch(source: str) -> bool:
    durable_methods = {
        "persist",
        "persist_terminal_group",
        "finalize_source",
        "commit",
        "write",
    }
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
            return True
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in durable_methods
        ):
            return True
    return False


def validate(
    ledger: dict[str, Any],
    oracle: dict[str, Any],
    sources: dict[str, str],
    *,
    enforce_hashes: bool,
) -> list[str]:
    failures = v6.validate(ledger, oracle, sources, enforce_hashes=enforce_hashes)
    trees = {path: ast.parse(text) for path, text in sources.items()}
    edges = {edge[0]: edge for edge in ledger["edges"]}

    if ledger["triggers"] != oracle["trigger_mappings"]:
        failures.append("trigger_mapping")
    if ledger["composition_roots"] != oracle["composition_root_mappings"]:
        failures.append("composition_root_mapping")
    if ledger.get("trigger_edge_anchors") != oracle["trigger_edge_anchors"]:
        failures.append("trigger_anchor_contract")
    if ledger.get("composition_root_edge_anchors") != oracle["composition_root_edge_anchors"]:
        failures.append("composition_anchor_contract")
    if ledger.get("composition_root_trigger_bridges") != oracle["composition_root_trigger_bridges"]:
        failures.append("root_trigger_bridge_contract")
    if ledger.get("trigger_required_rows") != oracle["trigger_required_rows"]:
        failures.append("trigger_row_contract")

    all_row_edges = {
        row_id: {
            edge_id
            for segment in row["segments"]
            for edge_id in segment
        }
        for row_id, row in ledger["rows"].items()
    }
    for trigger_id, owner_value in ledger["triggers"].items():
        try:
            path, qualname = _split_owner(owner_value)
        except ValueError:
            failures.append(f"trigger_owner:{trigger_id}")
            continue
        if path not in trees or v6._owner(trees[path], qualname) is None:
            failures.append(f"trigger_owner:{trigger_id}")
        anchors = ledger["trigger_edge_anchors"].get(trigger_id, [])
        for edge_id in anchors:
            edge = edges.get(edge_id)
            if edge is None or (edge[1], edge[2]) != (path, qualname):
                failures.append(f"trigger_anchor:{trigger_id}")
        for row_id in ledger["trigger_required_rows"].get(trigger_id, []):
            if not set(anchors).intersection(all_row_edges.get(row_id, set())):
                failures.append(f"trigger_row:{trigger_id}:{row_id}")

    for root_id, owner_value in ledger["composition_roots"].items():
        try:
            path, qualname = _split_owner(owner_value)
        except ValueError:
            failures.append(f"composition_owner:{root_id}")
            continue
        if path not in trees or v6._owner(trees[path], qualname) is None:
            failures.append(f"composition_owner:{root_id}")
        anchors = ledger["composition_root_edge_anchors"].get(root_id, [])
        if not anchors or any(edge_id not in edges for edge_id in anchors):
            failures.append(f"composition_anchor:{root_id}")
        if not ledger["composition_root_trigger_bridges"].get(root_id):
            failures.append(f"composition_bridge:{root_id}")
        for trigger_id in ledger["composition_root_trigger_bridges"].get(root_id, []):
            if trigger_id not in ledger["triggers"]:
                failures.append(f"composition_trigger:{root_id}")

    expected_hermes = {
        value for key, value in oracle["trigger_mappings"].items() if key.startswith("hermes_")
    }
    expected_service = {
        value for key, value in oracle["trigger_mappings"].items() if key.startswith("direct_")
    }
    actual_hermes, actual_service = _production_census(trees)
    if actual_hermes != expected_hermes:
        failures.append("hermes_trigger_census")
    if actual_service != expected_service:
        failures.append("service_trigger_census")

    for edge_id, edge in edges.items():
        binding = edge[7]
        if not binding.startswith("field:"):
            continue
        class_name = edge[2].split(".")[0]
        class_node = v6._owner(trees[edge[1]], class_name)
        field = edge[3].split(".")[1]
        if not isinstance(class_node, ast.ClassDef) or field not in _assigned_fields(class_node):
            failures.append(f"field_assignment:{edge_id}")

    arena_path = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    if _dynamic_durable_dispatch(sources[arena_path]):
        failures.append("R08_dynamic_durable_dispatch")
    return sorted(set(failures))


class _RebindService(ast.NodeTransformer):
    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        self.generic_visit(node)
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr == "_service"
            ):
                target.attr = "_detached_service"
                return node
        return node


def _mutations(
    ledger: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str]
) -> dict[str, bool]:
    cases = v6._mutations(ledger, oracle, sources)

    def ledger_case(name: str, mutate: Any) -> None:
        candidate = copy.deepcopy(ledger)
        mutate(candidate)
        cases[name] = bool(validate(candidate, oracle, sources, enforce_hashes=False))

    ledger_case(
        "forged_trigger_mapping",
        lambda value: value["triggers"].__setitem__("direct_sync", "forged"),
    )
    ledger_case(
        "forged_composition_root_mapping",
        lambda value: value["composition_roots"].__setitem__("provider_factory", "forged"),
    )
    ledger_case(
        "removed_composite_trigger",
        lambda value: value["triggers"].pop("direct_composite_sync"),
    )
    ledger_case(
        "removed_memory_write_trigger",
        lambda value: value["triggers"].pop("direct_memory_write"),
    )
    ledger_case(
        "detached_trigger_row",
        lambda value: value["rows"]["VCC-R01"]["segments"].__setitem__(
            slice(None),
            [
                segment
                for segment in value["rows"]["VCC-R01"]["segments"]
                if "hermes_memory_edge" not in segment and "write_ingest" not in segment
            ],
        ),
    )

    hermes_path = "memorii/memorii/integrations/hermes_provider.py"
    shadow = dict(sources)
    changed = shadow[hermes_path].replace(
        "authenticated_host_ingress=authenticated_host_ingress,",
        "authenticated_host_ingress=None,",
        1,
    )
    cases["none_hermes_authority"] = changed != shadow[hermes_path] and bool(
        validate(ledger, oracle, {**shadow, hermes_path: changed}, enforce_hashes=False)
    )

    tree = _RebindService().visit(ast.parse(sources[hermes_path]))
    ast.fix_missing_locations(tree)
    rebound = ast.unparse(tree) + "\n"
    cases["receiver_field_reassignment"] = bool(
        validate(ledger, oracle, {**sources, hermes_path: rebound}, enforce_hashes=False)
    )

    arena_path = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    dynamic = sources[arena_path].replace(
        "    def close(self) -> None:",
        "    def injected_dynamic_sink(self) -> None:\n"
        "        getattr(__import__(\"memorii.core.semantic_ingestion.persistence\"), \"persist\")(self)\n\n"
        "    def close(self) -> None:",
    )
    cases["dynamic_durable_sink_source"] = dynamic != sources[arena_path] and bool(
        validate(ledger, oracle, {**sources, arena_path: dynamic}, enforce_hashes=False)
    )
    return cases


def main() -> None:
    ledger_before = LEDGER.read_bytes()
    oracle_before = ORACLE.read_bytes()
    ledger = json.loads(ledger_before)
    oracle = json.loads(oracle_before)
    sources = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in oracle["source_hashes"]
    }
    failures = validate(ledger, oracle, sources, enforce_hashes=True)
    mutations = _mutations(ledger, oracle, sources)
    failed_mutations = sorted(name for name, detected in mutations.items() if not detected)
    if failed_mutations:
        failures.extend(f"mutation_survived:{name}" for name in failed_mutations)
    if LEDGER.read_bytes() != ledger_before or ORACLE.read_bytes() != oracle_before:
        failures.append("input_mutation")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v7",
        "passed": not failures,
        "failures": failures,
        "read_only_inputs": True,
        "trigger_count": len(ledger["triggers"]),
        "composition_root_count": len(ledger["composition_roots"]),
        "edge_count": len(ledger["edges"]),
        "row_count": len(ledger["rows"]),
        "source_hash_count": len(oracle["source_hashes"]),
        "mutation_results": mutations,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
