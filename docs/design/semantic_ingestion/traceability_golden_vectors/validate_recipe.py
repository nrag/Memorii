"""Design-side validation for the oracle-free scenario-first closure primitive recipe."""

from __future__ import annotations

import argparse
import ast
import base64
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


HEX64 = re.compile(r"[0-9a-f]{64}")
ROOT_KEYS = {
    "acceptance_baselines",
    "authority_use",
    "direct_negative_cases",
    "expanded_typed_values",
    "expanded_leaf_denominator",
    "raw_leaf_count",
    "typed_expansion_leaf_count",
    "field_coverage_ledger",
    "fixed_signers",
    "format",
    "mutation_target_grammar",
    "nested_substitution_cases",
    "primitive_authority",
    "primitive_fixtures",
    "vector_cases",
}
CURRENT_ROOT_KEYS = {
    "authority_use",
    "checked_fixture_outputs",
    "fixed_signers",
    "format",
    "nested_substitution_cases",
    "primitive_authority",
    "primitive_fixtures",
    "vector_cases",
}
CURRENT_AUTHORITY_KEYS = {
    "authority_id",
    "body_leaf_classification",
    "bootstrap_anchors",
    "channel_id",
    "derivation_program",
    "fences",
    "generations",
    "indexes",
    "lifecycle_records",
    "lifecycle_roots",
    "load_counts",
    "pointer_histories",
    "pointers",
    "primitive_body_inputs",
    "recovery_policy",
    "recovery_roots",
    "release",
    "runner",
}
FIXTURE_KEYS = {
    "body_input",
    "body_input_kind",
    "dependency_fixture_ids",
    "fixture_id",
    "inner_schema_id",
    "inner_schema_version",
    "signer_ids",
    "target_artifact_kind",
}
ENUM_REGISTRY_BEGIN = "[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]"
ENUM_REGISTRY_END = "[SIA-CTV-ENUM-REGISTRY-V1-END]"
ENUM_REGISTRY: dict[str, tuple[Any, ...]] = {}


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )


def exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} has incomplete or unknown fields")
    return value


def walk_leaves(value: Any, path: str = "$.body_input") -> list[str]:
    if isinstance(value, dict) and "$derive" in value:
        return [path]
    if isinstance(value, dict) and value.get("$type") == "map":
        return [
            leaf
            for key, item in value["entries"]
            for leaf in walk_leaves(item, f"{path}.{key}")
        ]
    if isinstance(value, dict):
        return [
            leaf
            for key, item in value.items()
            for leaf in walk_leaves(item, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            leaf
            for index, item in enumerate(value)
            for leaf in walk_leaves(item, f"{path}[{index}]")
        ]
    return [path]


def current_leaf_paths(value: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Return the stable CTV-field paths used by the primitive ownership ledger."""
    if isinstance(value, dict) and value.get("$type") == "map":
        return [
            leaf
            for key, item in value["entries"]
            for leaf in current_leaf_paths(item, (*path, f"field:{key}"))
        ]
    if isinstance(value, dict):
        return [
            leaf
            for key, item in value.items()
            for leaf in current_leaf_paths(item, (*path, f"key:{key}"))
        ]
    if isinstance(value, list):
        return [
            leaf
            for index, item in enumerate(value)
            for leaf in current_leaf_paths(item, (*path, f"index:{index}"))
        ]
    return [path]


def current_has_path(value: Any, path: tuple[str, ...]) -> bool:
    current = value
    for segment in path:
        try:
            kind, token = segment.split(":", 1)
            if kind == "field":
                if not isinstance(current, dict) or current.get("$type") != "map":
                    return False
                matches = [item for key, item in current["entries"] if key == token]
                if len(matches) != 1:
                    return False
                current = matches[0]
            elif kind == "key":
                if not isinstance(current, dict):
                    return False
                current = current[token]
            elif kind == "index":
                if not isinstance(current, list):
                    return False
                current = current[int(token)]
            else:
                return False
        except (IndexError, KeyError, ValueError):
            return False
    return True


def validate_current_primitive_ownership(authority: dict[str, Any]) -> None:
    """Require an exhaustive, non-heuristic source classification for scenario-first closure bodies."""
    exact_keys(authority, CURRENT_AUTHORITY_KEYS, "current primitive authority")
    bodies = authority["primitive_body_inputs"]
    ledger = authority["body_leaf_classification"]
    program = authority["derivation_program"]
    if not isinstance(program, dict) or not program:
        raise ValueError("current derivation program is missing")
    for rule_id, rule in program.items():
        exact_keys(rule, {"depends_on", "formula"}, f"derivation rule {rule_id}")
        if not isinstance(rule["formula"], str) or not isinstance(rule["depends_on"], list):
            raise ValueError(f"derivation rule {rule_id} is malformed")
    if not isinstance(bodies, dict) or not isinstance(ledger, dict) or set(bodies) != set(ledger):
        raise ValueError("current primitive body/classification fixture set mismatch")
    if len(bodies) != 49:
        raise ValueError("current primitive authority must contain 49 typed bodies")
    for fixture_id, body in bodies.items():
        exact_keys(body, {"inner_schema_id", "inner_schema_version", "value"}, f"{fixture_id} primitive body")
        if body["inner_schema_version"] != 1:
            raise ValueError(f"{fixture_id}: primitive body schema version mismatch")
        entries = ledger[fixture_id]
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{fixture_id}: missing primitive ownership classification")
        paths: list[tuple[str, ...]] = []
        primitive_paths: set[tuple[str, ...]] = set()
        for entry in entries:
            source = entry.get("source") if isinstance(entry, dict) else None
            expected = {"path", "source"} if source == "primitive" else {
                "depends_on", "derivation_rule_id", "path", "source"
            }
            exact_keys(entry, expected, f"{fixture_id} ownership entry")
            if entry["source"] not in {"primitive", "deterministic_derivation"}:
                raise ValueError(f"{fixture_id}: invalid ownership source")
            if not isinstance(entry["path"], list) or not all(isinstance(part, str) for part in entry["path"]):
                raise ValueError(f"{fixture_id}: invalid ownership path")
            path = tuple(entry["path"])
            paths.append(path)
            if entry["source"] == "primitive":
                primitive_paths.add(path)
                if not current_has_path(body["value"], path):
                    raise ValueError(f"{fixture_id}: primitive leaf is absent from authority")
            else:
                rule_id = entry["derivation_rule_id"]
                if rule_id not in program or entry["depends_on"] != program[rule_id]["depends_on"]:
                    raise ValueError(f"{fixture_id}: derived leaf has unknown or mismatched formula")
                if current_has_path(body["value"], path):
                    raise ValueError(f"{fixture_id}: derived leaf leaked into primitive authority")
        if len(paths) != len(set(paths)):
            raise ValueError(f"{fixture_id}: duplicate ownership path")
        observed = set(current_leaf_paths(body["value"]))
        if observed != primitive_paths:
            raise ValueError(f"{fixture_id}: primitive leaves do not exactly match ownership ledger")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--expected-recipe-sha256", required=True)
    parser.add_argument("--expected-design-sha256", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    design_bytes = args.design.read_bytes()
    registry_bytes = args.registry.read_bytes()
    if not design_bytes or not registry_bytes:
        raise ValueError("design and registry inputs must be non-empty")
    if hashlib.sha256(design_bytes).hexdigest() != args.expected_design_sha256:
        raise ValueError("incompatible design hash")
    if hashlib.sha256(registry_bytes).hexdigest() != args.expected_registry_sha256:
        raise ValueError("incompatible registry hash")
    raw = args.recipe.read_bytes()
    candidate = json.loads(raw)
    if candidate.get("format") == "memorii-sia-c2-normative-fixture-recipe-v1":
        recipe = exact_keys(candidate, CURRENT_ROOT_KEYS, "current recipe root")
        if raw != canonical(recipe):
            raise ValueError("recipe must be canonical compact ASCII JSON plus one LF")
        if hashlib.sha256(raw).hexdigest() != args.expected_recipe_sha256:
            raise ValueError("recipe SHA-256 mismatch")
        if recipe["authority_use"] != "nonoperational_design_fixture_authority_only":
            raise ValueError("invalid fixture authority use")
        if len(recipe["primitive_fixtures"]) != 57 or len(recipe["fixed_signers"]) != 4:
            raise ValueError("closed fixture/signer denominator mismatch")
        if len(recipe["vector_cases"]) != 25 or len(recipe["nested_substitution_cases"]) != 29:
            raise ValueError("closed mutation denominator mismatch")
        if recipe["checked_fixture_outputs"]:
            raise ValueError("derived fixture outputs are not recipe authority")
        validate_current_primitive_ownership(recipe["primitive_authority"])
        print(json.dumps({"fixtures": 57, "format": recipe["format"], "signers": 4}, sort_keys=True))
        return
    global ENUM_REGISTRY
    ENUM_REGISTRY = parse_enum_registry(design_bytes.decode("utf-8"))
    validate_enum_registry_authority(design_bytes.decode("utf-8"), ENUM_REGISTRY)
    recipe = exact_keys(json.loads(raw), ROOT_KEYS, "recipe root")
    if raw != canonical(recipe):
        raise ValueError("recipe must be canonical compact ASCII JSON plus one LF")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != args.expected_recipe_sha256 or not HEX64.fullmatch(digest):
        raise ValueError("recipe SHA-256 mismatch")
    if recipe["format"] != "memorii-sia-c2-oracle-free-elaboration-input-v9":
        raise ValueError("unexpected recipe format")

    fixtures = recipe["primitive_fixtures"]
    ledger = recipe["field_coverage_ledger"]
    signers = recipe["fixed_signers"]
    vectors = recipe["vector_cases"]
    nested = recipe["nested_substitution_cases"]
    negatives = recipe["direct_negative_cases"]
    if tuple(map(len, (fixtures, ledger, signers, vectors, nested, negatives))) != (
        57,
        57,
        4,
        25,
        29,
        12,
    ):
        raise ValueError("closed denominator must be 57/57/4/25/29/12")
    validate_fixed_signers(signers)

    fixture_ids = []
    fixture_by_id = {}
    for raw_fixture in fixtures:
        fixture = exact_keys(raw_fixture, FIXTURE_KEYS, "primitive fixture")
        fixture_id = fixture["fixture_id"]
        fixture_ids.append(fixture_id)
        fixture_by_id[fixture_id] = fixture
        if fixture["inner_schema_version"] != 1:
            raise ValueError(f"{fixture_id}: schema version must be 1")
        if any(":" in value for value in walk_string_values(fixture["body_input"]) if "fixture-" in value):
            raise ValueError(f"{fixture_id}: fixture-id-plus-field placeholder remains")
    if fixture_ids != sorted(set(fixture_ids)):
        raise ValueError("fixture IDs must be sorted and unique")
    for fixture in fixtures:
        if not set(fixture["dependency_fixture_ids"]) <= set(fixture_ids):
            raise ValueError(f"{fixture['fixture_id']}: dangling primitive dependency")

    state = recipe["primitive_authority"]
    coverage = {row["fixture_id"]: row["fields"] for row in ledger}
    expanded = recipe["expanded_typed_values"]
    typed_fixture_ids = {
        fixture["fixture_id"]
        for fixture in fixtures
        if fixture["body_input_kind"] == "typed_template"
    }
    if set(expanded) != typed_fixture_ids or len(expanded) != 49:
        raise ValueError("expanded typed authority must cover exactly 49 fixtures")
    if (
        recipe["typed_expansion_leaf_count"],
        recipe["raw_leaf_count"],
        recipe["expanded_leaf_denominator"],
    ) != (2686, 14, 2700):
        raise ValueError("expanded leaf denominator mismatch")
    design_fields = declared_class_fields(design_bytes.decode("utf-8"))
    schema_classes, schema_aliases = declared_schema_graph(
        design_bytes.decode("utf-8")
    )
    if set(coverage) != set(fixture_ids):
        raise ValueError("coverage ledger fixture set mismatch")
    observed_typed_leaves = 0
    observed_raw_leaves = 0
    for fixture_id, fixture in fixture_by_id.items():
        leaves = (
            walk_leaves(expanded[fixture_id]["typed_ctv"], "$.expanded_typed_value")
            if fixture_id in expanded
            else walk_leaves(fixture["body_input"])
        )
        paths = [entry["path"] for entry in coverage[fixture_id]]
        if set(paths) != set(leaves) or len(paths) != len(set(paths)):
            raise ValueError(f"{fixture_id}: field coverage is not exact")
        if any(entry["source"] not in {"primitive", "deterministic_derivation"} for entry in coverage[fixture_id]):
            raise ValueError(f"{fixture_id}: invalid field coverage source")
        if fixture_id in expanded:
            observed_typed_leaves += len(leaves)
            record = expanded[fixture_id]
            if (
                record["inner_schema_id"] != fixture["inner_schema_id"]
                or record["inner_schema_version"] != fixture["inner_schema_version"]
            ):
                raise ValueError(f"{fixture_id}: expanded schema mismatch")
            if "$derive" in walk_string_values(record["typed_ctv"]):
                raise ValueError(f"{fixture_id}: opaque derivation remains in expansion")
            validate_ctv(record["typed_ctv"], f"{fixture_id}.expanded")
            validate_content_boundaries(record["typed_ctv"], f"{fixture_id}.expanded")
            validate_declared_ctv(
                record["typed_ctv"],
                ast.Name(id=fixture["inner_schema_id"].removesuffix(".v1")),
                schema_classes,
                schema_aliases,
                f"{fixture_id}.expanded",
            )
            class_name = fixture["inner_schema_id"].removesuffix(".v1")
            declared = design_fields.get(class_name)
            if declared is None:
                raise ValueError(f"{fixture_id}: schema is absent from marked design")
            actual = (
                {entry[0] for entry in record["typed_ctv"]["entries"]}
                if record["typed_ctv"].get("$type") == "map"
                else set()
            )
            if actual != declared:
                raise ValueError(
                    f"{fixture_id}: top-level schema fields mismatch "
                    f"missing={sorted(declared - actual)} extra={sorted(actual - declared)}"
                )
            authority_value = authority_selection(state, fixture["body_input"])
            if isinstance(authority_value, dict):
                for field, expected_value in authority_value.items():
                    if isinstance(expected_value, (dict, list)) or field not in actual:
                        continue
                    actual_value = ctv_scalar(ctv_field(record["typed_ctv"], field))
                    if actual_value != expected_value:
                        raise ValueError(
                            f"{fixture_id}.{field}: expansion/authority scalar mismatch"
                        )
        else:
            observed_raw_leaves += len(leaves)
    if (observed_typed_leaves, observed_raw_leaves, observed_typed_leaves + observed_raw_leaves) != (
        recipe["typed_expansion_leaf_count"],
        recipe["raw_leaf_count"],
        recipe["expanded_leaf_denominator"],
    ):
        raise ValueError(
            "observed leaf counts do not match typed/raw/total metadata: "
            f"{observed_typed_leaves}/{observed_raw_leaves}/"
            f"{observed_typed_leaves + observed_raw_leaves}"
        )
    validate_boundary_siblings(expanded)

    records = state["lifecycle_records"]
    if [row["action"] for row in records] != ["activate", "activate", "activate", "recover"]:
        raise ValueError("lifecycle actions must be activate/activate/activate/recover")
    if [row["sequence"] for row in records] != [1, 2, 3, 4]:
        raise ValueError("lifecycle sequence mismatch")
    if any(records[index]["predecessor_record_id"] != records[index - 1]["record_id"] for index in range(1, 4)):
        raise ValueError("lifecycle immediate predecessor mismatch")
    if any(records[index][field] is not None for index in range(3) for field in ("policy_id", "replacement_target_id")):
        raise ValueError("activation records must not carry policy or replacement")
    if records[3]["policy_id"] is None or records[3]["replacement_target_id"] is None:
        raise ValueError("recovery record must carry policy and replacement")
    if [row["terminal_sequence"] for row in state["lifecycle_roots"]] != [1, 2, 3, 3, 4]:
        raise ValueError("lifecycle root terminal sequences mismatch")
    for family, field in (
        ("generations", "generation_sequence"),
        ("pointers", "pointer_sequence"),
        ("indexes", "index_generation"),
        ("fences", "index_generation"),
    ):
        if [row[field] for row in state[family]] != [1, 2, 3]:
            raise ValueError(f"{family} sequence must be exactly 1/2/3")
    for family, predecessor in (
        ("generations", "predecessor_generation_id"),
        ("pointers", "predecessor_pointer_id"),
        ("indexes", "predecessor_index_id"),
        ("fences", "predecessor_fence_id"),
    ):
        rows = state[family]
        if rows[0][predecessor] is not None:
            raise ValueError(f"{family} genesis predecessor must be null")
        for index in (1, 2):
            expected = {
                "generations": f"fixture-generation-{index}",
                "pointers": f"fixture-pointer-{index}",
                "indexes": f"fixture-pointer-index-{index}",
                "fences": f"fixture-pointer-fence-{index}",
            }[family]
            if rows[index][predecessor] != expected:
                raise ValueError(f"{family} immediate predecessor mismatch")
    validate_atomic_generation_state(state)
    if any(
        row["member_fixture_ids"] != sorted(set(row["member_fixture_ids"]))
        or not set(row["member_fixture_ids"]) <= set(fixture_ids)
        for row in state["generations"]
    ):
        raise ValueError("generation member tuples must be sorted, unique, and closed")
    authority_bodies = state["authority_bodies"]
    if "selector_materializations" in state:
        raise ValueError("stored selector materialization witness is forbidden")
    for fixture in fixtures:
        if fixture["body_input_kind"] != "typed_template":
            continue
        body_input = fixture["body_input"]
        if body_input.get("$derive") != "exact_body_from_primitive_authority":
            raise ValueError(f"{fixture['fixture_id']}: parallel typed template remains")
        if body_input["section"] == "authority_bodies":
            selector = body_input["selector"]
            if selector != fixture["fixture_id"] or selector not in authority_bodies:
                raise ValueError(f"{fixture['fixture_id']}: unresolved authority body selector")
            record = authority_bodies[selector]
            if (
                record["inner_schema_id"] != fixture["inner_schema_id"]
                or record["inner_schema_version"] != fixture["inner_schema_version"]
            ):
                raise ValueError(f"{fixture['fixture_id']}: authority body schema mismatch")
            expected_expansion = {
                "inner_schema_id": record["inner_schema_id"],
                "inner_schema_version": record["inner_schema_version"],
                "typed_ctv": record["value"],
            }
            if expected_expansion != expanded[fixture["fixture_id"]]:
                raise ValueError(
                    f"{fixture['fixture_id']}: independently materialized CTV tree mismatch"
                )
    history_zero = authority_bodies["fixture-06-recovery_policy_history"]["value"]
    history_one = authority_bodies["fixture-41-recovery_policy_history_1"]["value"]
    history_zero_policies = ctv_field(history_zero, "policies")
    history_one_policies = ctv_field(history_one, "policies")
    if (
        ctv_field(history_zero, "history_id") != "fixture-recovery-policy-history-0"
        or history_zero_policies != {"$type": "tuple", "items": []}
        or fixture_by_id["fixture-06-recovery_policy_history"]["dependency_fixture_ids"] != []
    ):
        raise ValueError("fixture-06 recovery policy history-0 is not empty and unique")
    embedded_policy = history_one_policies["items"][0]
    if (
        ctv_field(history_one, "history_id") != "fixture-recovery-policy-history-1"
        or len(history_one_policies["items"]) != 1
        or ctv_scalar(ctv_field(embedded_policy, "minimum_distinct_signatures")) != 2
        or len(ctv_field(embedded_policy, "eligible_recovery_root_digests")["items"]) != 2
        or "fixture-05-recovery_policy"
        not in fixture_by_id["fixture-41-recovery_policy_history_1"]["dependency_fixture_ids"]
    ):
        raise ValueError("fixture-41 recovery policy history-1 contents mismatch")

    required_negative_reasons = {
        "signer_not_authorized",
        "purpose_mismatch",
        "public_key_mismatch",
        "dangling_reference",
        "dependency_cycle",
        "sequence_mismatch",
        "predecessor_mismatch",
        "member_set_mismatch",
        "member_kind_mismatch",
    }
    if not required_negative_reasons <= {case["expected_reason"] for case in negatives}:
        raise ValueError("direct-negative matrix is incomplete")
    if len({case["case_id"] for case in negatives}) != 12:
        raise ValueError("direct-negative IDs must be unique")
    all_cases = [*vectors, *nested, *negatives]
    grammar = recipe["mutation_target_grammar"]
    signer_by_id = {signer["signer_id"]: signer for signer in signers}
    if len(all_cases) != 66 or any(case["mutation_kind"] == "none" for case in all_cases):
        raise ValueError("mutation denominator must contain exactly 66 concrete mutations")
    for case in all_cases:
        target = exact_keys(case["target"], {"owner_id", "path", "scope"}, "mutation target")
        if target["scope"] not in grammar["allowed_scopes"]:
            raise ValueError(f"{case['case_id']}: unknown mutation scope")
        if case["propagation"] != grammar["propagation"]:
            raise ValueError(f"{case['case_id']}: propagation mismatch")
        if case["expected_verdict"] != "reject":
            raise ValueError(f"{case['case_id']}: mutation must have explicit reject verdict")
        if not isinstance(case.get("expected_terminal_type"), str) or not isinstance(
            case.get("expected_terminal_category"), str
        ):
            raise ValueError(f"{case['case_id']}: terminal type/category missing")
        if not target["path"] or target["path"][0] != {"kind": "root"}:
            raise ValueError(f"{case['case_id']}: path must begin at the typed scope root")
        if any(segment == {"kind": "field", "name": "$"} for segment in target["path"]):
            raise ValueError(f"{case['case_id']}: '$' is not a field")
        for segment in target["path"]:
            kind = segment.get("kind")
            if kind not in grammar["path_segment_variants"]:
                raise ValueError(f"{case['case_id']}: unknown typed path segment")
            expected = (
                {"kind"}
                if kind == "root"
                else {"kind", "index"}
                if kind == "index"
                else {"kind", "name"}
            )
            exact_keys(segment, expected, "mutation path segment")
        if len(target["path"]) > 1 and target["scope"] not in {"derived_body", "preimage"}:
            first = target["path"][1]
            if first.get("kind") != "field" or first.get("name") not in grammar[
                "scope_root_schemas"
            ][target["scope"]]:
                raise ValueError(f"{case['case_id']}: target does not resolve in scope root")
        replacement = case["replacement"]
        if replacement["kind"] == "generation_reference" and replacement["value"] not in {
            "fixture-generation-1",
            "fixture-generation-2",
            "fixture-generation-3",
        }:
            raise ValueError(f"{case['case_id']}: unresolved generation reference")
        owner_id = target["owner_id"]
        if target["scope"] == "fixed_signer":
            root = signer_by_id.get(owner_id)
        else:
            fixture = fixture_by_id.get(owner_id)
            if fixture is None:
                raise ValueError(f"{case['case_id']}: mutation owner does not exist")
            if target["scope"] == "primitive_input":
                root = dict(fixture)
                if isinstance(fixture["body_input"], dict) and "section" in fixture["body_input"]:
                    root["authority_projection"] = authority_selection(
                        state, fixture["body_input"]
                    )
                chain_state = declared_chain_state(state, owner_id)
                if chain_state is not None:
                    root["declared_chain_state"] = chain_state
            elif target["scope"] == "derived_body":
                root = expanded[owner_id]["typed_ctv"]
            elif target["scope"] == "preimage":
                root = {"issuance_purpose": ctv_field(expanded[owner_id]["typed_ctv"], "issuance_purpose")}
            else:
                root = {
                    "dependencies": fixture["dependency_fixture_ids"],
                    "members": next(
                        (
                            row["member_fixture_ids"]
                            for row in state["generations"]
                            if row["manifest_fixture_id"] == owner_id
                        ),
                        [],
                    ),
                }
                if owner_id in expanded:
                    for field in grammar["scope_root_schemas"]["graph"]:
                        if field in root:
                            continue
                        try:
                            root[field] = ctv_field(expanded[owner_id]["typed_ctv"], field)
                        except ValueError:
                            pass
        if root is None:
            raise ValueError(f"{case['case_id']}: mutation scope/owner mismatch")
        current = resolve_segments(root, target["path"], case["case_id"])
        if replacement.get("value") == current:
            raise ValueError(f"{case['case_id']}: replacement is a no-op")
    validate_descriptor_matrix(all_cases)
    validate_cycle_case_authority(negatives, fixture_by_id)
    observed_mutations = [
        execute_mutation_case(
            case, fixture_by_id, signer_by_id, state, expanded
        )
        for case in all_cases
    ]
    for case, observed in zip(all_cases, observed_mutations):
        expected = (
            case["expected_boundary"],
            case["expected_reason"],
            case["expected_verdict"],
        )
        if observed != expected:
            raise ValueError(
                f"{case['case_id']}: executed mutation outcome mismatch "
                f"observed={observed!r} expected={expected!r}"
            )
    if len(observed_mutations) != 66:
        raise ValueError("executed mutation denominator mismatch")
    baselines = recipe["acceptance_baselines"]
    if len(baselines) != 1 or baselines[0]["expected_verdict"] != "accept":
        raise ValueError("idempotent acceptance baseline must be separate and explicit")
    if any(value.startswith("sia-traceability/v1/") for value in walk_string_values(recipe)):
        raise ValueError("oracle-free recipe contains a derived artifact coordinate")
    if args.self_test:
        run_adversarial_self_tests(
            raw,
            design_bytes,
            registry_bytes,
            args.expected_design_sha256,
            args.expected_registry_sha256,
        )

    raise ValueError(
        "ROUND20_INCOMPLETE_AUTHORITY: all-56 profile/binding recomputation, "
        "enum/profile grammar consistency, common mutation re-elaboration, "
        "non-fixture root evidence, and exhaustive registry-negative coverage "
        "remain unproved"
    )

    print(
        json.dumps(
            {
                "expanded_leaf_denominator": recipe["expanded_leaf_denominator"],
                "fixtures": len(fixtures),
                "mutation_cases": len(all_cases),
                "raw_leaf_count": recipe["raw_leaf_count"],
                "recipe_sha256": digest,
                "typed_expansion_leaf_count": recipe[
                    "typed_expansion_leaf_count"
                ],
            },
            sort_keys=True,
        )
    )


def walk_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in walk_string_values(child)]
    if isinstance(value, list):
        return [item for child in value for item in walk_string_values(child)]
    return []


def validate_fixed_signers(signers: list[dict[str, Any]]) -> None:
    keys = {
        "allowed_signature_purposes",
        "coordinate",
        "key_digest",
        "private_seed_hex",
        "public_key_hex",
        "reference_message_hex",
        "reference_signature_hex",
        "signature_profile_id",
        "signer_id",
    }
    expected_purposes = {
        "fixture-bootstrap-1": (
            "semantic_ingestion_traceability_trust_lifecycle",
            "semantic_ingestion_traceability_coverage",
            "semantic_ingestion_normative_evidence",
            "semantic_ingestion_traceability_release",
            "semantic_ingestion_traceability_release_history",
            "semantic_ingestion_traceability_active_pointer",
            "semantic_ingestion_traceability_reader_lease",
            "semantic_ingestion_traceability_retention_watermark",
            "semantic_ingestion_traceability_pointer_history",
            "semantic_ingestion_traceability_monotonic_time_witness",
            "semantic_ingestion_traceability_approval_generation",
        ),
        "fixture-bootstrap-2": ("semantic_ingestion_traceability_trust_lifecycle",),
        "fixture-recovery-1": ("semantic_ingestion_traceability_trust_lifecycle",),
        "fixture-recovery-2": ("semantic_ingestion_traceability_trust_lifecycle",),
    }
    if [item["signer_id"] for item in signers] != list(expected_purposes):
        raise ValueError("fixed signer order/identity mismatch")
    for signer in signers:
        exact_keys(signer, keys, "fixed signer")
        signer_id = signer["signer_id"]
        if tuple(signer["allowed_signature_purposes"]) != expected_purposes[signer_id]:
            raise ValueError(f"{signer_id}: exact purpose tuple mismatch")
        if signer["signature_profile_id"] != "memorii.test.ed25519.rfc8032.v1":
            raise ValueError(f"{signer_id}: signature profile mismatch")
        seed = bytes.fromhex(signer["private_seed_hex"])
        public, signature = rfc8032_sign(
            seed, bytes.fromhex(signer["reference_message_hex"])
        )
        if public.hex() != signer["public_key_hex"]:
            raise ValueError(f"{signer_id}: seed/public-key mismatch")
        if signature.hex() != signer["reference_signature_hex"]:
            raise ValueError(f"{signer_id}: RFC8032 reference signature mismatch")
        key_digest = hashlib.sha256(
            b"memorii:sia-test-ed25519-public-key:v1\0" + public
        ).hexdigest()
        if key_digest != signer["key_digest"]:
            raise ValueError(f"{signer_id}: public-key digest mismatch")
        expected_coordinate = f"sia-test-signer/v1/{signer_id}/{public.hex()}"
        if signer["coordinate"] != expected_coordinate:
            raise ValueError(f"{signer_id}: signer coordinate mismatch")


def rfc8032_sign(seed: bytes, message: bytes) -> tuple[bytes, bytes]:
    if len(seed) != 32:
        raise ValueError("RFC8032 seed must be 32 bytes")
    field = 2**255 - 19
    order = 2**252 + 27742317777372353535851937790883648493
    curve = -121665 * pow(121666, field - 2, field) % field
    sqrt_minus_one = pow(2, (field - 1) // 4, field)

    def recover_x(y: int, sign: int) -> int:
        xx = (y * y - 1) * pow(curve * y * y + 1, field - 2, field) % field
        x = pow(xx, (field + 3) // 8, field)
        if (x * x - xx) % field:
            x = x * sqrt_minus_one % field
        if (x * x - xx) % field:
            raise ValueError("invalid Ed25519 point")
        return field - x if x & 1 != sign else x

    def plus(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
        x1, y1 = left
        x2, y2 = right
        product = curve * x1 * x2 * y1 * y2
        return (
            (x1 * y2 + x2 * y1) * pow(1 + product, field - 2, field) % field,
            (y1 * y2 + x1 * x2) * pow(1 - product, field - 2, field) % field,
        )

    def multiply(point: tuple[int, int], scalar: int) -> tuple[int, int]:
        result = (0, 1)
        while scalar:
            if scalar & 1:
                result = plus(result, point)
            point = plus(point, point)
            scalar >>= 1
        return result

    def encode(point: tuple[int, int]) -> bytes:
        x, y = point
        return (y | ((x & 1) << 255)).to_bytes(32, "little")

    hashed = hashlib.sha512(seed).digest()
    secret = (int.from_bytes(hashed[:32], "little") & ((1 << 254) - 8)) | (
        1 << 254
    )
    y = 4 * pow(5, field - 2, field) % field
    base = (recover_x(y, 0), y)
    public = encode(multiply(base, secret))
    nonce = int.from_bytes(
        hashlib.sha512(hashed[32:] + message).digest(), "little"
    ) % order
    encoded_r = encode(multiply(base, nonce))
    challenge = int.from_bytes(
        hashlib.sha512(encoded_r + public + message).digest(), "little"
    ) % order
    signature = encoded_r + (
        (nonce + challenge * secret) % order
    ).to_bytes(32, "little")
    return public, signature


def validate_atomic_generation_state(state: dict[str, Any]) -> None:
    expected = {
        "generations": [
            ("fixture-generation-1", 1, None, "fixture-37-approval_generation_manifest"),
            ("fixture-generation-2", 2, "fixture-generation-1", "fixture-49-approval_generation_manifest_G2"),
            ("fixture-generation-3", 3, "fixture-generation-2", "fixture-50-approval_generation_manifest_G3"),
        ],
        "pointers": [
            ("fixture-pointer-1", 1, None, "fixture-generation-1"),
            ("fixture-pointer-2", 2, "fixture-pointer-1", "fixture-generation-2"),
            ("fixture-pointer-3", 3, "fixture-pointer-2", "fixture-generation-3"),
        ],
        "indexes": [
            ("fixture-pointer-index-1", 1, None, "fixture-pointer-1"),
            ("fixture-pointer-index-2", 2, "fixture-pointer-index-1", "fixture-pointer-2"),
            ("fixture-pointer-index-3", 3, "fixture-pointer-index-2", "fixture-pointer-3"),
        ],
        "fences": [
            ("fixture-pointer-fence-1", 1, None, "fixture-pointer-index-1"),
            ("fixture-pointer-fence-2", 2, "fixture-pointer-fence-1", "fixture-pointer-index-2"),
            ("fixture-pointer-fence-3", 3, "fixture-pointer-fence-2", "fixture-pointer-index-3"),
        ],
    }
    observed = {
        "generations": [
            (x["generation_id"], x["generation_sequence"], x["predecessor_generation_id"], x["manifest_fixture_id"])
            for x in state["generations"]
        ],
        "pointers": [
            (x["pointer_id"], x["pointer_sequence"], x["predecessor_pointer_id"], x["generation_id"])
            for x in state["pointers"]
        ],
        "indexes": [
            (x["index_id"], x["index_generation"], x["predecessor_index_id"], x["pointer_id"])
            for x in state["indexes"]
        ],
        "fences": [
            (x["fence_id"], x["index_generation"], x["predecessor_fence_id"], x["index_id"])
            for x in state["fences"]
        ],
    }
    if observed != expected:
        raise ValueError("atomic G1/G2/G3 identity table mismatch")


def validate_descriptor_matrix(cases: list[dict[str, Any]]) -> None:
    projection = [
        {
            key: case[key]
            for key in (
                "case_id",
                "target",
                "expected_terminal_type",
                "expected_terminal_category",
                "mutation_kind",
                "replacement",
                "expected_boundary",
                "expected_reason",
                "expected_verdict",
            )
        }
        for case in cases
    ]
    digest = hashlib.sha256(canonical(projection)).hexdigest()
    if digest != "b09e25b63f3e48856e59d08f2717345ddd512a5d6aa53ceb640a96ddcc1d5abf":
        raise ValueError("closed 66-case descriptor/outcome matrix mismatch")


def validate_cycle_case_authority(
    cases: list[dict[str, Any]], fixtures: dict[str, dict[str, Any]]
) -> None:
    by_id = {case["case_id"]: case for case in cases}

    def distance(start: str, target: str) -> int | None:
        queue = [(start, 0)]
        visited = {start}
        while queue:
            node, depth = queue.pop(0)
            if node == target:
                return depth
            for child in fixtures[node]["dependency_fixture_ids"]:
                if child not in visited:
                    visited.add(child)
                    queue.append((child, depth + 1))
        return None

    owner = "fixture-19-release"
    two_node = by_id["negative-two-node-cycle"]["replacement"]["value"]
    descendant = by_id["negative-descendant-cycle"]["replacement"]["value"]
    if distance(two_node, owner) != 1:
        raise ValueError("two-node cycle replacement lacks exact one-edge return path")
    descendant_distance = distance(descendant, owner)
    if descendant_distance is None or descendant_distance < 2:
        raise ValueError(
            "descendant cycle replacement lacks distinct multi-edge return path"
        )
    if two_node == descendant:
        raise ValueError("two-node and descendant cycle replacements must differ")


def walk_ctv_maps(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("$type") == "map":
            result.append(value)
        for child in value.values():
            result.extend(walk_ctv_maps(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(walk_ctv_maps(child))
    return result


def validate_content_boundaries(value: Any, path: str) -> None:
    required = {
        "canonical_profile_id",
        "content_bytes",
        "content_digest",
        "content_schema_id",
        "content_schema_version",
        "content_size",
        "media_type",
    }
    for candidate in walk_ctv_maps(value):
        entries = {key: item for key, item in candidate["entries"]}
        if not required <= set(entries):
            continue
        if set(entries) != required:
            raise ValueError(f"{path}: canonical content boundary has unknown fields")
        encoded = entries["content_bytes"]
        if not isinstance(encoded, dict) or encoded.get("$type") != "bytes":
            raise ValueError(f"{path}: canonical content bytes are not tagged bytes")
        content = base64.b64decode(encoded["value"], validate=True)
        version = ctv_scalar(entries["content_schema_version"])
        size = ctv_scalar(entries["content_size"])
        if (
            not isinstance(version, int)
            or version < 1
            or size != len(content)
            or size < 1
        ):
            raise ValueError(f"{path}: canonical content boundary size/version mismatch")
        identity = (
            entries["content_schema_id"],
            entries["media_type"],
            entries["canonical_profile_id"],
        )
        if not all(isinstance(item, str) and item for item in identity):
            raise ValueError(f"{path}: canonical content identity is incomplete")
        pieces = [identity[0], str(version), identity[1], identity[2]]
        preimage = b"memorii:sia-canonical-content:v1\0"
        for piece in pieces:
            raw = piece.encode("ascii")
            preimage += len(raw).to_bytes(8, "big") + raw
        preimage += len(content).to_bytes(8, "big") + content
        if hashlib.sha256(preimage).hexdigest() != entries["content_digest"]:
            raise ValueError(f"{path}: canonical content digest mismatch")


def validate_ctv(value: Any, path: str) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError(f"{path}: string contains a non-scalar surrogate")
        return
    if not isinstance(value, dict) or "$type" not in value:
        raise ValueError(f"{path}: invalid CTV node")
    tag = value["$type"]
    if tag == "integer":
        exact_keys(value, {"$type", "value"}, path)
        if not re.fullmatch(r"0|-?[1-9][0-9]*", value["value"]):
            raise ValueError(f"{path}: noncanonical integer")
    elif tag == "datetime":
        exact_keys(value, {"$type", "value"}, path)
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value["value"]):
            raise ValueError(f"{path}: noncanonical datetime")
        dt.datetime.strptime(value["value"], "%Y-%m-%dT%H:%M:%S.%fZ")
    elif tag in {"tuple", "list"}:
        exact_keys(value, {"$type", "items"}, path)
        for index, item in enumerate(value["items"]):
            validate_ctv(item, f"{path}.items[{index}]")
    elif tag in {"set", "frozenset"}:
        exact_keys(value, {"$type", "items"}, path)
        encoded = [canonical(item)[:-1] for item in value["items"]]
        if encoded != sorted(set(encoded)):
            raise ValueError(f"{path}: set members must be canonical and unique")
        for index, item in enumerate(value["items"]):
            validate_ctv(item, f"{path}.items[{index}]")
    elif tag == "map":
        exact_keys(value, {"$type", "entries"}, path)
        keys = [entry[0] for entry in value["entries"]]
        if not all(
            isinstance(key, str)
            and not any(0xD800 <= ord(char) <= 0xDFFF for char in key)
            for key in keys
        ):
            raise ValueError(f"{path}: map key must be a Unicode scalar string")
        if keys != sorted(set(keys)):
            raise ValueError(f"{path}: map keys must be sorted and unique")
        for key, item in value["entries"]:
            validate_ctv(item, f"{path}.{key}")
    elif tag == "bytes":
        exact_keys(value, {"$type", "value"}, path)
        decoded = base64.b64decode(value["value"], validate=True)
        if base64.b64encode(decoded).decode("ascii") != value["value"]:
            raise ValueError(f"{path}: noncanonical padded RFC4648 base64")
    elif tag == "duration_microseconds":
        exact_keys(value, {"$type", "value"}, path)
        microseconds = value["value"]
        if not isinstance(microseconds, str) or not re.fullmatch(
            r"0|-?[1-9][0-9]*", microseconds
        ):
            raise ValueError(f"{path}: noncanonical duration")
        if not -(2**63) <= int(microseconds) < 2**63:
            raise ValueError(f"{path}: duration outside signed int64")
    elif tag == "enum":
        exact_keys(value, {"$type", "schema", "member"}, path)
        if not isinstance(value["schema"], str) or not value["schema"]:
            raise ValueError(f"{path}: invalid enum identity")
        if value["schema"] not in ENUM_REGISTRY:
            raise ValueError(f"{path}: unknown enum schema {value['schema']!r}")
        member = canonical_literal_member(value["member"])
        registered = {
            canonical_literal_member(item) for item in ENUM_REGISTRY[value["schema"]]
        }
        if member not in registered:
            raise ValueError(f"{path}: unregistered enum member {value['member']!r}")
    else:
        raise ValueError(f"{path}: unknown CTV tag {tag!r}")


def declared_schema_graph(
    design: str,
) -> tuple[dict[str, ast.ClassDef], dict[str, ast.expr]]:
    classes: dict[str, ast.ClassDef] = {}
    aliases: dict[str, ast.expr] = {}
    for block in re.findall(r"```python\n(.*?)```", design, re.DOTALL):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes[node.name] = node
            elif (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                aliases[node.targets[0].id] = node.value
    return classes, aliases


def model_fields(
    name: str, classes: dict[str, ast.ClassDef]
) -> dict[str, tuple[str, ast.AnnAssign]]:
    node = classes[name]
    result: dict[str, tuple[str, ast.AnnAssign]] = {}
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in classes:
            result.update(model_fields(base.id, classes))
    for child in node.body:
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            result[child.target.id] = (name, child)
    return result


def validate_declared_constraints(value: Any, field: ast.AnnAssign, path: str) -> None:
    if not isinstance(field.value, ast.Call):
        return
    callable_name = (
        field.value.func.id if isinstance(field.value.func, ast.Name) else ""
    )
    if callable_name != "Field":
        return
    constraints = {
        keyword.arg: ast.literal_eval(keyword.value)
        for keyword in field.value.keywords
        if keyword.arg in {"ge", "gt", "le", "lt", "min_length", "max_length", "pattern"}
    }
    scalar = ctv_scalar(value)
    if "ge" in constraints and not scalar >= constraints["ge"]:
        raise ValueError(f"{path}: value violates declared ge constraint")
    if "gt" in constraints and not scalar > constraints["gt"]:
        raise ValueError(f"{path}: value violates declared gt constraint")
    if "le" in constraints and not scalar <= constraints["le"]:
        raise ValueError(f"{path}: value violates declared le constraint")
    if "lt" in constraints and not scalar < constraints["lt"]:
        raise ValueError(f"{path}: value violates declared lt constraint")
    if "min_length" in constraints and len(scalar) < constraints["min_length"]:
        raise ValueError(f"{path}: value violates declared min_length constraint")
    if "max_length" in constraints and len(scalar) > constraints["max_length"]:
        raise ValueError(f"{path}: value violates declared max_length constraint")
    if "pattern" in constraints and re.fullmatch(constraints["pattern"], scalar) is None:
        raise ValueError(f"{path}: value violates declared pattern constraint")


def validate_declared_ctv(
    value: Any,
    annotation: ast.expr,
    classes: dict[str, ast.ClassDef],
    aliases: dict[str, ast.expr],
    path: str,
    enum_schema: str | None = None,
) -> None:
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        validate_declared_ctv(
            value,
            ast.parse(annotation.value, mode="eval").body,
            classes,
            aliases,
            path,
            enum_schema,
        )
        return
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        errors = []
        for option in (annotation.left, annotation.right):
            try:
                validate_declared_ctv(value, option, classes, aliases, path, enum_schema)
                return
            except ValueError as error:
                errors.append(str(error))
        raise ValueError(f"{path}: value matches no declared union member: {errors}")
    if isinstance(annotation, ast.Subscript):
        container = annotation.value.id if isinstance(annotation.value, ast.Name) else ""
        if container in {"Union", "Optional"}:
            options = (
                list(annotation.slice.elts)
                if isinstance(annotation.slice, ast.Tuple)
                else [annotation.slice]
            )
            if container == "Optional":
                options.append(ast.Constant(value=None))
            errors = []
            for option in options:
                try:
                    validate_declared_ctv(
                        value, option, classes, aliases, path, enum_schema
                    )
                    return
                except ValueError as error:
                    errors.append(str(error))
            raise ValueError(
                f"{path}: value matches no declared {container} member: {errors}"
            )
        if container == "Literal":
            options = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
            allowed = {ast.literal_eval(option) for option in options}
            if (
                not isinstance(value, dict)
                or value.get("$type") != "enum"
                or value.get("schema") != enum_schema
            ):
                raise ValueError(f"{path}: expected declared enum schema {enum_schema}")
            scalar = value["member"]
            normalized = {
                canonical_literal_member(option) for option in allowed
            }
            if canonical(scalar) not in normalized:
                raise ValueError(f"{path}: value is outside declared Literal")
            return
        if container == "Annotated":
            inner = annotation.slice.elts[0] if isinstance(annotation.slice, ast.Tuple) else annotation.slice
            validate_declared_ctv(value, inner, classes, aliases, path, enum_schema)
            return
        if container in {"tuple", "list", "set", "frozenset"}:
            expected_tag = container
            if not isinstance(value, dict) or value.get("$type") != expected_tag:
                raise ValueError(f"{path}: expected declared {expected_tag} CTV node")
            inner = annotation.slice.elts[0] if isinstance(annotation.slice, ast.Tuple) else annotation.slice
            for index, item in enumerate(value["items"]):
                validate_declared_ctv(item, inner, classes, aliases, f"{path}[{index}]", enum_schema)
            return
        if container == "dict":
            if not isinstance(value, dict) or value.get("$type") != "map":
                raise ValueError(f"{path}: expected declared map CTV node")
            args = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
            child = args[-1]
            for key, item in value["entries"]:
                validate_declared_ctv(item, child, classes, aliases, f"{path}.{key}", enum_schema)
            return
    if isinstance(annotation, ast.Name):
        name = annotation.id
        if name in aliases:
            validate_declared_ctv(
                value,
                aliases[name],
                classes,
                aliases,
                path,
                enum_schema if enum_schema in aliases else name,
            )
            return
        if name in classes:
            if not isinstance(value, dict) or value.get("$type") != "map":
                raise ValueError(f"{path}: expected declared model {name}")
            actual = {key: item for key, item in value["entries"]}
            expected = model_fields(name, classes)
            if set(actual) != set(expected):
                raise ValueError(f"{path}: declared model fields mismatch for {name}")
            for field_name, (declaring_owner, field) in expected.items():
                validate_declared_ctv(
                    actual[field_name],
                    field.annotation,
                    classes,
                    aliases,
                    f"{path}.{field_name}",
                    f"{declaring_owner}.{field_name}",
                )
                validate_declared_constraints(
                    actual[field_name], field, f"{path}.{field_name}"
                )
            return
        if name in {"None"}:
            if value is not None:
                raise ValueError(f"{path}: expected null")
            return
        if name == "str" and not isinstance(value, str):
            raise ValueError(f"{path}: expected string")
        if name == "bool" and not isinstance(value, bool):
            raise ValueError(f"{path}: expected boolean")
        if name == "int" and not (
            isinstance(value, dict) and value.get("$type") == "integer"
        ):
            raise ValueError(f"{path}: expected integer")
        if name == "bytes" and not (
            isinstance(value, dict) and value.get("$type") == "bytes"
        ):
            raise ValueError(f"{path}: expected bytes")
        if name == "datetime" and not (
            isinstance(value, dict) and value.get("$type") == "datetime"
        ):
            raise ValueError(f"{path}: expected datetime")
        if name in {"Any", "object"}:
            return
        if name not in {
            "None",
            "str",
            "bool",
            "int",
            "bytes",
            "datetime",
            "Any",
            "object",
        }:
            raise ValueError(f"{path}: unsupported declared annotation {name}")
        return
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        if value is not None:
            raise ValueError(f"{path}: expected null")
        return
    raise ValueError(
        f"{path}: unsupported declared annotation {ast.unparse(annotation)}"
    )


def declared_class_fields(design: str) -> dict[str, set[str]]:
    fields: dict[str, set[str]] = {}
    for block in re.findall(r"```python\n(.*?)```", design, re.DOTALL):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                fields[node.name] = {
                    child.target.id
                    for child in node.body
                    if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
                }
    return fields


def canonical_literal_member(value: Any) -> bytes:
    if value is None or isinstance(value, (str, bool)):
        return canonical(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return canonical({"$type": "integer", "value": str(value)})
    if (
        isinstance(value, dict)
        and value.get("$type") == "integer"
        and set(value) == {"$type", "value"}
    ):
        return canonical(value)
    raise ValueError("enum member is not a CanonicalLiteralScalar")


def parse_enum_registry(design: str) -> dict[str, tuple[Any, ...]]:
    start = design.find(ENUM_REGISTRY_BEGIN)
    end = design.find(ENUM_REGISTRY_END)
    if start < 0 or end < 0 or end <= start:
        raise ValueError("marked CTV enum registry is absent or malformed")
    block = design[start + len(ENUM_REGISTRY_BEGIN) : end]
    match = re.search(r"```json\n(.*?)```", block, re.DOTALL)
    if match is None:
        raise ValueError("marked CTV enum registry JSON is absent")
    parsed = json.loads(match.group(1))
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("CTV enum registry must be a non-empty object")
    result: dict[str, tuple[Any, ...]] = {}
    for schema, members in parsed.items():
        if (
            not isinstance(schema, str)
            or not schema
            or not isinstance(members, list)
            or not members
        ):
            raise ValueError(f"invalid closed enum registry row {schema!r}")
        identities = [canonical_literal_member(member) for member in members]
        if len(identities) != len(set(identities)):
            raise ValueError(f"duplicate typed enum member in {schema!r}")
        result[schema] = tuple(members)
    return result


def validate_enum_registry_authority(
    design: str, registry: dict[str, tuple[Any, ...]]
) -> None:
    classes, aliases = declared_schema_graph(design)
    inventory_match = re.search(
        r"`\[SIA-TRACEABILITY-SCHEMA-INVENTORY-V1-BEGIN\]`\n```text\n"
        r"(.*?)```\n`\[SIA-TRACEABILITY-SCHEMA-INVENTORY-V1-END\]`",
        design,
        re.DOTALL,
    )
    if inventory_match is None:
        raise ValueError("marked schema inventory is absent")
    roots = inventory_match.group(1).splitlines()
    expected: dict[str, tuple[Any, ...]] = {}
    visited: set[tuple[str, str | None]] = set()

    def resolved_literals(node: ast.expr, stack: frozenset[str]) -> list[ast.expr]:
        if isinstance(node, ast.Name) and node.id in aliases:
            if node.id in stack:
                raise ValueError(f"recursive enum alias {node.id}")
            return resolved_literals(aliases[node.id], stack | {node.id})
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Literal"
        ):
            return (
                list(node.slice.elts)
                if isinstance(node.slice, ast.Tuple)
                else [node.slice]
            )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return resolved_literals(node.left, stack) + resolved_literals(
                node.right, stack
            )
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Annotated"
        ):
            inner = (
                node.slice.elts[0]
                if isinstance(node.slice, ast.Tuple)
                else node.slice
            )
            return resolved_literals(inner, stack)
        return []

    def direct_literals(node: ast.expr) -> list[ast.expr]:
        if isinstance(node, ast.Name):
            return []
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Literal"
        ):
            return (
                list(node.slice.elts)
                if isinstance(node.slice, ast.Tuple)
                else [node.slice]
            )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return direct_literals(node.left) + direct_literals(node.right)
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Annotated"
        ):
            inner = (
                node.slice.elts[0]
                if isinstance(node.slice, ast.Tuple)
                else node.slice
            )
            return direct_literals(inner)
        return []

    def register(schema: str, nodes: list[ast.expr]) -> None:
        values = []
        identities = set()
        for node in nodes:
            literal = ast.literal_eval(node)
            member: Any = (
                {"$type": "integer", "value": str(literal)}
                if isinstance(literal, int) and not isinstance(literal, bool)
                else literal
            )
            identity = canonical_literal_member(member)
            if identity in identities:
                raise ValueError(f"type-sensitive duplicate enum member in {schema}")
            identities.add(identity)
            values.append(member)
        previous = expected.setdefault(schema, tuple(values))
        if previous != tuple(values):
            raise ValueError(f"conflicting enum declaration {schema}")

    def visit(node: ast.expr, owner: str | None = None, field: str | None = None) -> None:
        key = (ast.dump(node), f"{owner}.{field}" if owner and field else None)
        if key in visited:
            return
        visited.add(key)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            visit(ast.parse(node.value, mode="eval").body, owner, field)
            return
        if isinstance(node, ast.Name):
            if node.id in aliases:
                values = resolved_literals(aliases[node.id], frozenset({node.id}))
                if values:
                    register(node.id, values)
                else:
                    visit(aliases[node.id])
            elif node.id in classes:
                for field_name, (declaring_owner, declared) in model_fields(
                    node.id, classes
                ).items():
                    visit(declared.annotation, declaring_owner, field_name)
            return
        values = direct_literals(node)
        if values:
            if owner is None or field is None:
                raise ValueError("anonymous reachable Literal")
            register(f"{owner}.{field}", values)
            return
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            visit(node.left, owner, field)
            visit(node.right, owner, field)
        elif isinstance(node, ast.Subscript):
            children = (
                list(node.slice.elts)
                if isinstance(node.slice, ast.Tuple)
                else [node.slice]
            )
            for child in children:
                if not (
                    isinstance(child, ast.Constant) and child.value is Ellipsis
                ):
                    visit(child, owner, field)

    for coordinate in roots:
        root = coordinate.removesuffix(".v1")
        if root.startswith("TraceabilityRegistryRoot."):
            continue
        if root not in classes and root not in aliases:
            raise ValueError(f"inventory root is undeclared: {root}")
        visit(ast.Name(id=root))
    if canonical(expected) != canonical(registry):
        raise ValueError("reachable enum registry schema/member mapping mismatch")


def validate_boundary_siblings(expanded: dict[str, Any]) -> None:
    fixture35 = expanded["fixture-35-golden_typed_input_fixture"]["typed_ctv"]
    boundary35 = ctv_field(fixture35, "typed_input_value")
    binding35 = ctv_field(fixture35, "target_body_binding")
    if (
        ctv_field(boundary35, "content_schema_id")
        != ctv_field(fixture35, "target_schema_id")
        or ctv_scalar(ctv_field(boundary35, "content_schema_version"))
        != ctv_scalar(ctv_field(fixture35, "target_schema_version"))
        or ctv_scalar(ctv_field(boundary35, "canonical_profile_id"))
        != ctv_scalar(ctv_field(binding35, "profile_id"))
    ):
        raise ValueError("fixture-35 canonical boundary sibling mismatch")
    manifest = expanded["fixture-36-golden_vector_manifest"]["typed_ctv"]
    nested = ctv_field(manifest, "fixtures")["items"][0]
    boundary36 = ctv_field(nested, "typed_input_value")
    binding36 = ctv_field(nested, "target_body_binding")
    if (
        ctv_field(boundary36, "content_schema_id")
        != ctv_field(nested, "target_schema_id")
        or ctv_scalar(ctv_field(boundary36, "content_schema_version"))
        != ctv_scalar(ctv_field(nested, "target_schema_version"))
        or ctv_scalar(ctv_field(boundary36, "canonical_profile_id"))
        != ctv_scalar(ctv_field(binding36, "profile_id"))
    ):
        raise ValueError("fixture-36 canonical boundary sibling mismatch")


def authority_selection(state: dict[str, Any], reference: dict[str, Any]) -> Any:
    section = reference["section"]
    selector = reference["selector"]
    value = state[section]
    if section == "authority_bodies":
        return value[selector]["value"]
    if section == "runner":
        return (
            {"observation_id": value["observation_id"]}
            if selector == "observation"
            else value
        )
    return value[selector] if isinstance(selector, int) else value


def declared_chain_state(state: dict[str, Any], fixture_id: str) -> Any:
    mapping = {
        "fixture-37-approval_generation_manifest": ("generations", 0),
        "fixture-49-approval_generation_manifest_G2": ("generations", 1),
        "fixture-50-approval_generation_manifest_G3": ("generations", 2),
        "fixture-21-active_release_pointer": ("pointers", 0),
        "fixture-51-active_release_pointer_G2": ("pointers", 1),
        "fixture-52-active_release_pointer_G3": ("pointers", 2),
        "fixture-22-current_pointer_index": ("indexes", 0),
        "fixture-53-current_pointer_index_G2": ("indexes", 1),
        "fixture-54-current_pointer_index_G3": ("indexes", 2),
    }
    selected = mapping.get(fixture_id)
    return None if selected is None else state[selected[0]][selected[1]]


def ctv_field(value: dict[str, Any], name: str) -> Any:
    if value.get("$type") != "map":
        raise ValueError(f"CTV value is not a map while resolving {name!r}")
    matches = [item for key, item in value["entries"] if key == name]
    if len(matches) != 1:
        raise ValueError(f"CTV field {name!r} does not resolve uniquely")
    return matches[0]


def ctv_scalar(value: Any) -> Any:
    if isinstance(value, dict) and value.get("$type") == "integer":
        return int(value["value"])
    if isinstance(value, dict) and value.get("$type") == "datetime":
        return value["value"]
    if isinstance(value, dict) and value.get("$type") == "enum":
        member = value["member"]
        if isinstance(member, dict) and member.get("$type") == "integer":
            return int(member["value"])
        return member
    return value


def resolve_segments(root: Any, path: list[dict[str, Any]], case_id: str) -> Any:
    value = root
    for segment in path[1:]:
        kind = segment["kind"]
        if kind == "field":
            name = segment["name"]
            if not isinstance(value, dict):
                raise ValueError(f"{case_id}: field {name!r} applied to non-object")
            value = value[name] if name in value else ctv_field(value, name)
        elif kind == "index":
            if not isinstance(value, list) or not 0 <= segment["index"] < len(value):
                raise ValueError(f"{case_id}: index does not resolve")
            value = value[segment["index"]]
        elif kind == "map_key":
            value = ctv_field(value, segment["name"])
        else:
            raise ValueError(f"{case_id}: unsupported path segment")
    return value


def replace_segments(
    root: Any, path: list[dict[str, Any]], replacement: Any, case_id: str
) -> Any:
    if len(path) == 1:
        return deepcopy(replacement)
    parent = root
    for segment in path[1:-1]:
        kind = segment["kind"]
        if kind == "field":
            name = segment["name"]
            parent = parent[name] if name in parent else ctv_field(parent, name)
        elif kind == "index":
            parent = parent[segment["index"]]
        elif kind == "map_key":
            parent = ctv_field(parent, segment["name"])
        else:
            raise ValueError(f"{case_id}: unsupported mutation path")
    terminal = path[-1]
    if terminal["kind"] == "field":
        name = terminal["name"]
        if name in parent:
            parent[name] = deepcopy(replacement)
        else:
            for entry in parent["entries"]:
                if entry[0] == name:
                    entry[1] = deepcopy(replacement)
                    break
            else:
                raise ValueError(f"{case_id}: mutation field does not resolve")
    elif terminal["kind"] == "index":
        parent[terminal["index"]] = deepcopy(replacement)
    elif terminal["kind"] == "map_key":
        for entry in parent["entries"]:
            if entry[0] == terminal["name"]:
                entry[1] = deepcopy(replacement)
                break
        else:
            raise ValueError(f"{case_id}: mutation map key does not resolve")
    else:
        raise ValueError(f"{case_id}: unsupported terminal mutation path")
    return root


def execute_mutation_case(
    case: dict[str, Any],
    fixtures: dict[str, dict[str, Any]],
    signers: dict[str, dict[str, Any]],
    state: dict[str, Any],
    expanded: dict[str, Any],
) -> tuple[str, str, str]:
    target = case["target"]
    owner_id = target["owner_id"]
    scope = target["scope"]
    fixture = fixtures.get(owner_id)
    if scope == "fixed_signer":
        original = signers[owner_id]
        root = deepcopy(original)
    elif scope == "derived_body":
        original = expanded[owner_id]["typed_ctv"]
        root = deepcopy(original)
    elif scope == "preimage":
        original = {
            "issuance_purpose": ctv_field(
                expanded[owner_id]["typed_ctv"], "issuance_purpose"
            )
        }
        root = deepcopy(original)
    elif scope == "primitive_input":
        if fixture is None:
            raise ValueError(f"{case['case_id']}: unknown primitive owner")
        original = dict(fixture)
        if isinstance(fixture["body_input"], dict) and "section" in fixture["body_input"]:
            original["authority_projection"] = authority_selection(
                state, fixture["body_input"]
            )
        chain = declared_chain_state(state, owner_id)
        if chain is not None:
            original["declared_chain_state"] = chain
        root = deepcopy(original)
    else:
        if fixture is None:
            raise ValueError(f"{case['case_id']}: unknown graph owner")
        original = {
            "dependencies": fixture["dependency_fixture_ids"],
            "members": next(
                (
                    row["member_fixture_ids"]
                    for row in state["generations"]
                    if row["manifest_fixture_id"] == owner_id
                ),
                [],
            ),
        }
        if owner_id in expanded:
            for name in (
                "active_pointer_intent",
                "generation_id",
                "generation_sequence",
                "index_generation",
                "pointer_id",
                "predecessor_fence_id",
                "predecessor_generation_id",
                "predecessor_index_id",
                "predecessor_pointer_id",
                "stderr_artifact_coordinate",
                "stdout_artifact_coordinate",
            ):
                try:
                    original[name] = ctv_field(expanded[owner_id]["typed_ctv"], name)
                except ValueError:
                    pass
        root = deepcopy(original)
    mutated = replace_segments(
        root, target["path"], case["replacement"]["value"], case["case_id"]
    )

    if scope == "derived_body":
        try:
            validate_ctv(mutated, f"{case['case_id']}.mutated")
        except ValueError as error:
            reason = (
                "schema_invalid_type_tag"
                if "unknown CTV tag" in str(error)
                else "schema_invalid"
            )
            return "typed_domain_semantic_validation", reason, "reject"
    if scope == "fixed_signer":
        seed = bytes.fromhex(mutated["private_seed_hex"])
        public, _ = rfc8032_sign(seed, bytes.fromhex(mutated["reference_message_hex"]))
        if public.hex() != mutated["public_key_hex"]:
            return "provenance_signature_validation", "public_key_mismatch", "reject"
    if scope == "preimage":
        if mutated["issuance_purpose"] != original["issuance_purpose"]:
            return "provenance_signature_validation", "purpose_mismatch", "reject"
    if scope == "primitive_input":
        if not isinstance(mutated, dict) or not set(FIXTURE_KEYS) <= set(mutated):
            return "typed_domain_semantic_validation", "schema_invalid", "reject"
        if mutated.get("signer_ids") != original.get("signer_ids"):
            return "provenance_signature_validation", "signer_not_authorized", "reject"
        path_names = [
            segment.get("name")
            for segment in target["path"]
            if segment["kind"] in {"field", "map_key"}
        ]
        chain_before = original.get("declared_chain_state")
        chain_after = mutated.get("declared_chain_state")
        if (
            isinstance(chain_before, dict)
            and isinstance(chain_after, dict)
            and chain_after != chain_before
        ):
            changed = {
                key
                for key in chain_before
                if chain_before.get(key) != chain_after.get(key)
            }
            if changed == {"generation_id"}:
                return (
                    "lifecycle_policy",
                    "active_pointer_monotonicity",
                    "reject",
                )
            if changed == {"predecessor_generation_id"}:
                return (
                    "lifecycle_policy",
                    "historical_predecessor_mismatch",
                    "reject",
                )
            if any("sequence" in name for name in changed):
                return "lifecycle_policy", "sequence_mismatch", "reject"
            if any("predecessor" in name for name in changed):
                return "lifecycle_policy", "predecessor_mismatch", "reject"
        if any("sequence" in (name or "") for name in path_names):
            return "lifecycle_policy", "sequence_mismatch", "reject"
        if any("predecessor" in (name or "") for name in path_names):
            return (
                "lifecycle_policy", "predecessor_mismatch",
                "reject",
            )
    if scope == "graph":
        dependencies = mutated.get("dependencies", [])
        known = set(fixtures)
        if any(item not in known for item in dependencies):
            return "dependency_closure", "dangling_reference", "reject"
        if owner_id == "fixture-14-runner_report" and dependencies != original[
            "dependencies"
        ]:
            changed_index = next(
                index
                for index, (before, after) in enumerate(
                    zip(original["dependencies"], dependencies)
                )
                if before != after
            )
            reason = (
                "stream_kind_mismatch"
                if changed_index == 2
                else "stream_alias_forbidden"
            )
            return "typed_domain_semantic_validation", reason, "reject"
        graph = {
            fixture_id: list(fixture["dependency_fixture_ids"])
            for fixture_id, fixture in fixtures.items()
        }
        graph[owner_id] = dependencies
        colors: dict[str, int] = {}

        def visit(node: str) -> bool:
            if colors.get(node) == 1:
                return True
            if colors.get(node) == 2:
                return False
            colors[node] = 1
            if any(visit(child) for child in graph[node]):
                return True
            colors[node] = 2
            return False

        if any(visit(node) for node in graph):
            return "dependency_closure", "dependency_cycle", "reject"
        members = mutated.get("members", [])
        if any(member not in fixtures for member in members):
            return "generation_closure", "member_kind_mismatch", "reject"
        if members != original["members"]:
            return "generation_closure", "member_set_mismatch", "reject"
    raise ValueError(f"{case['case_id']}: mutation produced no validation failure")


def validate_candidate(
    recipe_bytes: bytes,
    design_bytes: bytes,
    registry_bytes: bytes,
    *,
    expected_recipe_sha256: str | None = None,
    expected_design_sha256: str | None = None,
    expected_registry_sha256: str | None = None,
) -> dict[str, Any]:
    """Run the ordinary validator over caller-supplied bytes and return diagnostics."""
    with tempfile.TemporaryDirectory(prefix="sia-c2-validator-") as directory:
        root = Path(directory)
        paths = {
            "recipe": root / "recipe.json",
            "design": root / "design.md",
            "registry": root / "registry.json",
        }
        paths["recipe"].write_bytes(recipe_bytes)
        paths["design"].write_bytes(design_bytes)
        paths["registry"].write_bytes(registry_bytes)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--recipe",
            str(paths["recipe"]),
            "--design",
            str(paths["design"]),
            "--registry",
            str(paths["registry"]),
            "--expected-recipe-sha256",
            expected_recipe_sha256 or hashlib.sha256(recipe_bytes).hexdigest(),
            "--expected-design-sha256",
            expected_design_sha256 or hashlib.sha256(design_bytes).hexdigest(),
            "--expected-registry-sha256",
            expected_registry_sha256 or hashlib.sha256(registry_bytes).hexdigest(),
        ]
        completed = subprocess.run(command, capture_output=True, check=False, text=True)
    return {
        "accepted": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_adversarial_self_tests(
    recipe_bytes: bytes,
    design_bytes: bytes,
    registry_bytes: bytes,
    design_sha256: str,
    registry_sha256: str,
) -> None:
    failures = [
        lambda: validate_ctv({"$type": "integer", "value": "01"}, "bad.integer"),
        lambda: validate_ctv(
            {"$type": "datetime", "value": "2024-02-30T00:00:00.000000Z"},
            "bad.datetime",
        ),
        lambda: validate_ctv(
            {"$type": "map", "entries": [["b", None], ["a", None]]},
            "bad.map",
        ),
        lambda: validate_ctv({"$type": "bytes", "value": "YQ"}, "bad.bytes"),
        lambda: validate_ctv(
            {"$type": "duration_microseconds", "value": str(2**63)}, "bad.duration"
        ),
        lambda: validate_ctv(
            {"$type": "duration", "microseconds": "0"}, "bad.legacy_duration"
        ),
        lambda: validate_ctv(
            {"$type": "set", "items": ["b", "a"]}, "bad.set"
        ),
        lambda: validate_ctv(
            {"$type": "enum", "schema": "", "member": "x"}, "bad.enum"
        ),
        lambda: validate_ctv("\ud800", "bad.unicode"),
        lambda: resolve_segments(
            {"present": 1},
            [{"kind": "root"}, {"kind": "field", "name": "missing"}],
            "bad.field",
        ),
        lambda: resolve_segments(
            {"items": []},
            [
                {"kind": "root"},
                {"kind": "field", "name": "items"},
                {"kind": "index", "index": 0},
            ],
            "bad.index",
        ),
    ]
    for index, operation in enumerate(failures):
        try:
            operation()
        except (KeyError, ValueError):
            continue
        raise AssertionError(f"adversarial self-test {index} did not fail closed")

    recipe = json.loads(recipe_bytes)
    full_candidate_mutations: list[tuple[str, Any, str]] = [
        (
            "leaf denominator drift",
            lambda candidate: candidate.__setitem__(
                "typed_expansion_leaf_count",
                candidate["typed_expansion_leaf_count"] + 1,
            ),
            "expanded leaf denominator mismatch",
        ),
        (
            "missing mutation owner",
            lambda candidate: candidate["vector_cases"][0]["target"].__setitem__(
                "owner_id", "fixture-does-not-exist"
            ),
            "mutation owner does not exist",
        ),
        (
            "no-op replacement",
            lambda candidate: candidate["vector_cases"][13].__setitem__(
                "replacement",
                {
                    "kind": candidate["vector_cases"][13]["replacement"]["kind"],
                    "value": resolve_case_current_value(candidate, candidate["vector_cases"][13]),
                },
            ),
            "replacement is a no-op",
        ),
        (
            "signer public key drift",
            lambda candidate: candidate["fixed_signers"][0].__setitem__(
                "public_key_hex", "00" * 32
            ),
            "seed/public-key mismatch",
        ),
        (
            "atomic generation identity drift",
            lambda candidate: candidate["primitive_authority"]["generations"][0].__setitem__(
                "generation_id", "fixture-generation-invalid"
            ),
            "atomic G1/G2/G3 identity table mismatch",
        ),
        (
            "descriptor outcome drift",
            lambda candidate: candidate["vector_cases"][0].__setitem__(
                "expected_reason", "purpose_mismatch"
            ),
            "closed 66-case descriptor/outcome matrix mismatch",
        ),
        (
            "wrong nested CTV tag",
            lambda candidate: replace_expanded_field(
                candidate,
                "fixture-01-bootstrap_anchor",
                ("canonical_profile_binding", "profile_version"),
                {
                    "$type": "datetime",
                    "value": "2024-01-01T00:00:00.000000Z",
                },
            ),
            "expected integer",
        ),
        (
            "wrong declared scalar type",
            lambda candidate: replace_expanded_field(
                candidate,
                "fixture-01-bootstrap_anchor",
                ("rotation_sequence",),
                {
                    "$type": "datetime",
                    "value": "2024-01-01T00:00:00.000000Z",
                },
            ),
            "expected integer",
        ),
        (
            "non-nullable field changed to null",
            lambda candidate: replace_expanded_field(
                candidate,
                "fixture-01-bootstrap_anchor",
                ("anchor_id",),
                None,
            ),
            "expected string",
        ),
        (
            "wrong declared collection type",
            lambda candidate: replace_expanded_field(
                candidate,
                "fixture-01-bootstrap_anchor",
                ("authorized_signature_purposes",),
                {
                    "$type": "list",
                    "items": [
                        {
                            "$type": "enum",
                            "schema": "TraceabilitySignaturePurpose",
                            "member": "semantic_ingestion_traceability_release",
                        }
                    ],
                },
            ),
            "expected declared tuple CTV node",
        ),
        (
            "wrong collection element value",
            lambda candidate: replace_expanded_collection_item(
                candidate,
                "fixture-01-bootstrap_anchor",
                ("authorized_signature_purposes",),
                0,
                {
                    "$type": "enum",
                    "schema": "TraceabilitySignaturePurpose",
                    "member": "not-a-declared-signature-purpose",
                },
            ),
            "unregistered enum member",
        ),
        (
            "constrained scalar violation",
            lambda candidate: replace_expanded_field(
                candidate,
                "fixture-01-bootstrap_anchor",
                ("rotation_sequence",),
                {"$type": "integer", "value": "0"},
            ),
            "violates declared ge constraint",
        ),
        (
            "nullable union mismatch",
            lambda candidate: replace_expanded_field(
                candidate,
                "fixture-01-bootstrap_anchor",
                ("expires_at",),
                False,
            ),
            "value matches no declared union member",
        ),
    ]
    for label, mutate, expected_diagnostic in full_candidate_mutations:
        candidate = deepcopy(recipe)
        mutate(candidate)
        candidate_bytes = canonical(candidate)
        diagnostic = validate_candidate(
            candidate_bytes,
            design_bytes,
            registry_bytes,
            expected_design_sha256=design_sha256,
            expected_registry_sha256=registry_sha256,
        )
        combined = diagnostic["stdout"] + diagnostic["stderr"]
        if diagnostic["accepted"] or expected_diagnostic not in combined:
            raise AssertionError(
                f"full-candidate self-test {label!r} did not fail at "
                f"{expected_diagnostic!r}: {combined}"
            )

    incompatible_design = validate_candidate(
        recipe_bytes,
        design_bytes + b"\n",
        registry_bytes,
        expected_design_sha256=design_sha256,
        expected_registry_sha256=registry_sha256,
    )
    if incompatible_design["accepted"] or "incompatible design hash" not in (
        incompatible_design["stdout"] + incompatible_design["stderr"]
    ):
        raise AssertionError("full-candidate design-hash self-test did not fail closed")


def resolve_case_current_value(recipe: dict[str, Any], case: dict[str, Any]) -> Any:
    """Resolve the common primitive-input case used by the no-op full-input test."""
    target = case["target"]
    fixture = next(
        fixture
        for fixture in recipe["primitive_fixtures"]
        if fixture["fixture_id"] == target["owner_id"]
    )
    if target["scope"] == "primitive_input":
        root: Any = dict(fixture)
    elif target["scope"] == "graph":
        root = {"dependencies": fixture["dependency_fixture_ids"], "members": []}
    else:
        raise ValueError("unsupported self-test no-op seed scope")
    return resolve_segments(root, target["path"], case["case_id"])


def replace_expanded_field(
    candidate: dict[str, Any],
    fixture_id: str,
    field_path: tuple[str, ...],
    replacement: Any,
) -> None:
    value = candidate["expanded_typed_values"][fixture_id]["typed_ctv"]
    for field_name in field_path[:-1]:
        value = ctv_field(value, field_name)
    entries = value["entries"]
    target = field_path[-1]
    for index, (field_name, _) in enumerate(entries):
        if field_name == target:
            entries[index][1] = replacement
            return
    raise AssertionError(f"self-test field {target!r} does not exist")


def replace_expanded_collection_item(
    candidate: dict[str, Any],
    fixture_id: str,
    field_path: tuple[str, ...],
    index: int,
    replacement: Any,
) -> None:
    value = candidate["expanded_typed_values"][fixture_id]["typed_ctv"]
    for field_name in field_path:
        value = ctv_field(value, field_name)
    value["items"][index] = replacement


if __name__ == "__main__":
    main()
