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
LEDGER = HERE / "production-entrypoint-bindings-v8.json"
ORACLE = HERE / "production-owner-oracle-v5.json"
OUTPUT = HERE / "production-entrypoint-bindings-v8-validation.json"
V7 = HERE / "validate_production_entrypoint_bindings_v7.py"

spec = importlib.util.spec_from_file_location("vcc_binding_v7", V7)
if spec is None or spec.loader is None:
    raise RuntimeError("v7 binding validator unavailable")
v7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v7)
v6 = v7.v6


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _split_owner(value: str) -> tuple[str, str]:
    path, separator, qualname = value.partition("::")
    if not separator or not path or not qualname:
        raise ValueError("invalid_owner_coordinate")
    return path, qualname


def _self_field(target: ast.AST, field: str) -> bool:
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
        and target.attr == field
    )


def _field_assignments(class_node: ast.ClassDef, field: str) -> list[tuple[str, ast.AST]]:
    result: list[tuple[str, ast.AST]] = []
    for method in class_node.body:
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(method):
            if isinstance(node, ast.Assign) and any(
                _self_field(target, field) for target in node.targets
            ):
                result.append((method.name, node.value))
            elif isinstance(node, ast.AnnAssign) and _self_field(node.target, field):
                result.append((method.name, node.value))
    return result


def _leaves(node: ast.AST) -> list[tuple[str, str, ast.Call | None]]:
    if isinstance(node, ast.Name):
        return [("typed_parameter", node.id, None)]
    if isinstance(node, ast.Call):
        return [("factory_call", ast.unparse(node.func), node)]
    if isinstance(node, ast.IfExp):
        return _leaves(node.body) + _leaves(node.orelse)
    if isinstance(node, ast.BoolOp):
        return [leaf for value in node.values for leaf in _leaves(value)]
    raise ValueError(f"unsupported_assignment_source:{type(node).__name__}")


def _hermes_composition_valid(
    ledger: dict[str, Any], trees: dict[str, ast.Module]
) -> list[str]:
    failures: list[str] = []
    hermes_path = "memorii/memorii/integrations/hermes_provider.py"
    class_node = v6._owner(trees[hermes_path], "HermesMemoryProvider")
    init = v6._owner(trees[hermes_path], "HermesMemoryProvider.__init__")
    if not isinstance(class_node, ast.ClassDef) or not isinstance(
        init, (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        return ["hermes_constructor_owner"]
    assignments = _field_assignments(class_node, "_service")
    if len(assignments) != 3 or any(method != "__init__" for method, _ in assignments):
        return ["hermes_service_assignment_cardinality"]
    try:
        leaves = [leaf for _, value in assignments for leaf in _leaves(value)]
    except ValueError:
        return ["hermes_service_assignment_grammar"]
    actual = {(kind, expression) for kind, expression, _ in leaves}
    branches = ledger["composition_branches"]
    expected = {
        (branch["kind"], branch["source_expression"])
        for branch in branches.values()
        if branch["root_id"] == "hermes_constructor"
    }
    if actual != expected or len(leaves) != len(expected):
        failures.append("hermes_service_assignment_sources")
    parameters = {
        argument.arg: ast.unparse(argument.annotation)
        for argument in init.args.args + init.args.kwonlyargs
        if argument.annotation is not None
    }
    for branch in branches.values():
        if branch["root_id"] != "hermes_constructor":
            continue
        if branch["owner"] != ledger["composition_roots"]["hermes_constructor"]:
            failures.append("hermes_branch_owner")
        matching = [
            item for item in leaves if item[0] == branch["kind"] and item[1] == branch["source_expression"]
        ]
        if len(matching) != 1:
            failures.append(f"hermes_branch_source:{branch['source_expression']}")
            continue
        if branch["kind"] == "typed_parameter":
            if "ProviderMemoryService" not in parameters.get(branch["source_expression"], ""):
                failures.append("hermes_injected_service_type")
            continue
        call = matching[0][2]
        assert call is not None
        keywords = {
            item.arg: ast.unparse(item.value)
            for item in call.keywords
            if item.arg is not None
        }
        if any(
            keywords.get(name) != value
            for name, value in branch["required_keywords"].items()
        ):
            failures.append(f"hermes_branch_authority:{branch['source_expression']}")
    return failures


def _validate_root_paths(
    ledger: dict[str, Any], oracle: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    edges = {edge[0]: edge for edge in ledger["edges"]}
    branches = ledger["composition_branches"]
    if ledger["composition_root_anchors"] != oracle["composition_root_anchors"]:
        failures.append("composition_root_anchor_contract")
    if ledger["composition_root_trigger_paths"] != oracle["composition_root_trigger_paths"]:
        failures.append("composition_root_path_contract")
    if ledger["composition_branches"] != oracle["composition_branches"]:
        failures.append("composition_branch_contract")
    for root_id, paths in ledger["composition_root_trigger_paths"].items():
        root_owner = ledger["composition_roots"][root_id]
        anchors = set(ledger["composition_root_anchors"][root_id])
        for path in paths:
            if not path or path[0] not in anchors or not path[-1].startswith("trigger:"):
                failures.append(f"composition_path_shape:{root_id}")
                continue
            first_kind, first_id = path[0].split(":", 1)
            if first_kind == "edge":
                edge = edges.get(first_id)
                if edge is None or f"{edge[1]}::{edge[2]}" != root_owner:
                    failures.append(f"composition_anchor_owner:{root_id}")
            elif first_kind == "branch":
                branch = branches.get(first_id)
                if branch is None or branch["owner"] != root_owner:
                    failures.append(f"composition_anchor_owner:{root_id}")
            else:
                failures.append(f"composition_anchor_kind:{root_id}")
            trigger_id = path[-1].split(":", 1)[1]
            if trigger_id not in ledger["composition_root_trigger_bridges"].get(root_id, []):
                failures.append(f"composition_trigger_bridge:{root_id}")
            trigger_anchors = ledger["trigger_edge_anchors"].get(trigger_id, [])
            required_rows = ledger["trigger_required_rows"].get(trigger_id, [])
            if not trigger_anchors or not any(
                set(trigger_anchors).intersection(
                    edge_id
                    for segment in ledger["rows"][row_id]["segments"]
                    for edge_id in segment
                )
                for row_id in required_rows
            ):
                failures.append(f"composition_trigger_row:{root_id}:{trigger_id}")
            if first_kind == "branch":
                field_tokens = [token for token in path if token.startswith("field:")]
                edge = edges[trigger_anchors[0]]
                if field_tokens != [f"field:{branches[first_id]['field']}"] or not edge[3].startswith(
                    f"self.{branches[first_id]['field']}."
                ):
                    failures.append(f"composition_field_bridge:{root_id}:{trigger_id}")
    return failures


def validate(
    ledger: dict[str, Any],
    oracle: dict[str, Any],
    sources: dict[str, str],
    *,
    enforce_hashes: bool,
) -> list[str]:
    failures = v6.validate(ledger, oracle, sources, enforce_hashes=enforce_hashes)
    trees = {path: ast.parse(text) for path, text in sources.items()}
    if ledger["triggers"] != oracle["trigger_mappings"]:
        failures.append("trigger_mapping")
    if ledger["composition_roots"] != oracle["composition_root_mappings"]:
        failures.append("composition_root_mapping")
    if ledger["trigger_edge_anchors"] != oracle["trigger_edge_anchors"]:
        failures.append("trigger_anchor_contract")
    if ledger["composition_root_trigger_bridges"] != oracle["composition_root_trigger_bridges"]:
        failures.append("root_trigger_bridge_contract")
    if ledger["trigger_required_rows"] != oracle["trigger_required_rows"]:
        failures.append("trigger_row_contract")
    actual_hermes, actual_service = v7._production_census(trees)
    expected_hermes = {
        value for key, value in oracle["trigger_mappings"].items() if key.startswith("hermes_")
    }
    expected_service = {
        value for key, value in oracle["trigger_mappings"].items() if key.startswith("direct_")
    }
    if actual_hermes != expected_hermes:
        failures.append("hermes_trigger_census")
    if actual_service != expected_service:
        failures.append("service_trigger_census")
    failures.extend(_hermes_composition_valid(ledger, trees))
    failures.extend(_validate_root_paths(ledger, oracle))
    arena_path = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    if v7._dynamic_durable_dispatch(sources[arena_path]):
        failures.append("R08_dynamic_durable_dispatch")
    return sorted(set(failures))


class _ReplaceServiceValue(ast.NodeTransformer):
    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        self.generic_visit(node)
        if any(_self_field(target, "_service") for target in node.targets):
            node.value = ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[])
        return node


class _ReplaceServiceAnnotation(ast.NodeTransformer):
    def visit_arg(self, node: ast.arg) -> ast.AST:
        if node.arg == "service":
            node.annotation = ast.Name(id="object", ctx=ast.Load())
        return node


class _AddServiceReassignment(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        if node.name == "__init__":
            node.body.append(
                ast.Assign(
                    targets=[ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="_service", ctx=ast.Store())],
                    value=ast.Call(func=ast.Name(id="object", ctx=ast.Load()), args=[], keywords=[]),
                )
            )
        return node


def _mutate_source(source: str, transformer: ast.NodeTransformer) -> str:
    tree = transformer.visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _mutations(
    ledger: dict[str, Any], oracle: dict[str, Any], sources: dict[str, str]
) -> dict[str, bool]:
    cases: dict[str, bool] = {}

    def ledger_case(name: str, mutate: Any) -> None:
        candidate = copy.deepcopy(ledger)
        mutate(candidate)
        cases[name] = bool(validate(candidate, oracle, sources, enforce_hashes=False))

    ledger_case("forged_trigger_mapping", lambda value: value["triggers"].__setitem__("direct_sync", "forged"))
    ledger_case("forged_root_mapping", lambda value: value["composition_roots"].__setitem__("provider_factory", "forged"))
    ledger_case("root_anchor_swap", lambda value: value["composition_root_anchors"]["hermes_constructor"].__setitem__(0, "edge:factory_service"))
    ledger_case("detached_root_bridge", lambda value: value["composition_root_trigger_paths"]["hermes_constructor"].pop())
    ledger_case("detached_trigger_row", lambda value: value["rows"]["VCC-R01"]["segments"].clear())
    ledger_case("removed_composite_trigger", lambda value: value["triggers"].pop("direct_composite_sync"))
    ledger_case("removed_memory_trigger", lambda value: value["triggers"].pop("direct_memory_write"))
    ledger_case("wrong_target_same_name", lambda value: value["edges"][0].__setitem__(6, "ProviderMemoryService._sync_composite_event"))
    ledger_case("disconnected_row", lambda value: value["rows"]["VCC-R01"]["segments"][0].insert(1, "semantic_encode"))
    ledger_case("missing_authority_keyword", lambda value: value["edges"][5][4].append("missing_authority"))
    ledger_case("R08_relabelled_durable", lambda value: value["rows"]["VCC-R08"].__setitem__("outcome", "durable_terminal_write"))

    hermes_path = "memorii/memorii/integrations/hermes_provider.py"
    constructor_none = sources[hermes_path].replace(
        "verified_production_host_authority=verified_production_host_authority,",
        "verified_production_host_authority=None,",
    )
    cases["constructor_none_authority"] = constructor_none != sources[hermes_path] and bool(
        validate(ledger, oracle, {**sources, hermes_path: constructor_none}, enforce_hashes=False)
    )
    for name, transformer in (
        ("receiver_value_substitution", _ReplaceServiceValue()),
        ("injected_service_type_substitution", _ReplaceServiceAnnotation()),
        ("later_receiver_reassignment", _AddServiceReassignment()),
    ):
        shadow = _mutate_source(sources[hermes_path], transformer)
        cases[name] = bool(validate(ledger, oracle, {**sources, hermes_path: shadow}, enforce_hashes=False))

    hook_none = sources[hermes_path].replace(
        "authenticated_host_ingress=authenticated_host_ingress,",
        "authenticated_host_ingress=None,",
        1,
    )
    cases["hook_none_authority"] = hook_none != sources[hermes_path] and bool(
        validate(ledger, oracle, {**sources, hermes_path: hook_none}, enforce_hashes=False)
    )

    arena_path = "memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py"
    for name, body in (
        ("direct_durable_sink", "        self.persist()\n"),
        ("aliased_durable_sink", "        writer.persist(self)\n"),
        ("dynamic_durable_sink", "        getattr(__import__(\"memorii.core.semantic_ingestion.persistence\"), \"persist\")(self)\n"),
    ):
        shadow = sources[arena_path].replace(
            "    def close(self) -> None:",
            f"    def injected_sink(self) -> None:\n{body}\n    def close(self) -> None:",
        )
        cases[name] = bool(validate(ledger, oracle, {**sources, arena_path: shadow}, enforce_hashes=False))
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
    failures.extend(
        f"mutation_survived:{name}" for name, detected in mutations.items() if not detected
    )
    if LEDGER.read_bytes() != ledger_before or ORACLE.read_bytes() != oracle_before:
        failures.append("input_mutation")
    result = {
        "schema": "memorii.production-entrypoint-bindings-validation.v8",
        "passed": not failures,
        "failures": failures,
        "read_only_inputs": True,
        "trigger_count": len(ledger["triggers"]),
        "composition_root_count": len(ledger["composition_roots"]),
        "composition_branch_count": len(ledger["composition_branches"]),
        "root_path_count": sum(len(paths) for paths in ledger["composition_root_trigger_paths"].values()),
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
