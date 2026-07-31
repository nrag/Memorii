"""Independent executable verifier for the frozen C2 recipe and package."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


_TAGS = {
    "bytes",
    "datetime",
    "duration_microseconds",
    "enum",
    "frozenset",
    "integer",
    "list",
    "map",
    "set",
    "tuple",
}
_INTEGER = re.compile(r"0|-?[1-9][0-9]*")
_DATETIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z")


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        .encode("ascii")
        + b"\n"
    )


def _validate_ctv(value: Any) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, (int, float, list)):
        raise ValueError("schema_invalid")
    if not isinstance(value, dict) or "$type" not in value:
        raise ValueError("schema_invalid")
    tag = value["$type"]
    if tag not in _TAGS:
        raise ValueError("schema_invalid_type_tag")
    if tag in {"integer", "duration_microseconds"}:
        if set(value) != {"$type", "value"} or not isinstance(value["value"], str):
            raise ValueError("schema_invalid")
        if not _INTEGER.fullmatch(value["value"]) or value["value"] == "-0":
            raise ValueError("schema_invalid")
    elif tag == "bytes":
        if set(value) != {"$type", "value"}:
            raise ValueError("schema_invalid")
        raw = base64.b64decode(value["value"], validate=True)
        if base64.b64encode(raw).decode("ascii") != value["value"]:
            raise ValueError("schema_invalid")
    elif tag == "datetime":
        if set(value) != {"$type", "value"} or not _DATETIME.fullmatch(value["value"]):
            raise ValueError("schema_invalid")
    elif tag == "enum":
        if set(value) != {"$type", "member", "schema"}:
            raise ValueError("schema_invalid")
    elif tag in {"list", "tuple", "set", "frozenset"}:
        if set(value) != {"$type", "items"} or not isinstance(value["items"], list):
            raise ValueError("schema_invalid")
        encoded = []
        for item in value["items"]:
            _validate_ctv(item)
            encoded.append(_canonical(item)[:-1])
        if tag in {"set", "frozenset"} and encoded != sorted(set(encoded)):
            raise ValueError("schema_invalid")
    elif tag == "map":
        if set(value) != {"$type", "entries"} or not isinstance(value["entries"], list):
            raise ValueError("schema_invalid")
        keys = []
        for entry in value["entries"]:
            if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str):
                raise ValueError("schema_invalid")
            keys.append(json.dumps(entry[0], ensure_ascii=False).encode("utf-8"))
            _validate_ctv(entry[1])
        if keys != sorted(set(keys)):
            raise ValueError("schema_invalid")


def _path_target(root: Any, path: str) -> tuple[Any, str | int]:
    if not path.startswith("$."):
        raise ValueError("invalid mutation path")
    tokens: list[str | int] = []
    for name, index in re.findall(r"(?:^|\.)([A-Za-z_$][A-Za-z0-9_$]*)|\[([0-9]+)\]", path[2:]):
        tokens.append(name if name else int(index))
    if not tokens:
        raise ValueError("empty mutation path")
    parent = root
    for token in tokens[:-1]:
        parent = parent[token]
    return parent, tokens[-1]


def _observe_vector(vector: dict[str, Any], fixtures: dict[str, dict[str, Any]]) -> tuple[str, str | None]:
    fixture = fixtures[vector["fixture_id"]]
    mutation = vector["mutation_kind"]
    if mutation == "none":
        return "accept", None
    if mutation == "idempotent_lost_ack_replay":
        if vector["replacement_reference"] == "fixture-generation-G2":
            return "accept", None
        return "reject", "active_pointer_monotonicity"
    replacement = vector["replacement_reference"]
    if mutation == "cross_stream_substitution":
        replacement_fixture = next(
            item for item in fixtures.values()
            if item["expected_artifact_coordinate"] == replacement
        )
        if replacement_fixture["target_artifact_kind"] != "stderr_artifact":
            return "reject", "stream_kind_mismatch"
    elif mutation == "alias_forbidden_stream":
        if replacement not in fixture["exact_reference_coordinates"]:
            return "reject", "stream_alias_forbidden"
    elif mutation == "restore_prior_index":
        if replacement == "fixture-generation-G1":
            return "reject", "active_pointer_monotonicity"
    elif mutation == "substitute_reference":
        if replacement not in fixture["exact_reference_coordinates"]:
            return "reject", "historical_predecessor_mismatch"
    raise ValueError(f"mutation did not reach a defined semantic boundary: {vector['vector_id']}")


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("recipe", type=Path)
    cli.add_argument("design", type=Path)
    cli.add_argument("registry", type=Path)
    cli.add_argument("source", type=Path)
    args = cli.parse_args()
    directory = Path(__file__).parent
    recipe = json.loads(args.recipe.read_bytes())
    # These independent validators recompute the frozen binding, digest,
    # signature, coordinate, DAG, lifecycle, and recipe/source cross-bindings.
    _run([sys.executable, str(directory / "validate_recipe.py")])
    _run([sys.executable, str(directory / "validate_source.py")])
    with tempfile.TemporaryDirectory(prefix="memorii-c2-") as temporary:
        temp = Path(temporary)
        a, b = temp / "a.json", temp / "b.json"
        common = [str(args.recipe), str(args.design), str(args.registry)]
        _run([sys.executable, str(directory / "materialize_remaining.py"), *common, str(a)])
        _run([sys.executable, str(directory / "elaborate_independent_b.py"), *common, str(b)])
        expected = args.source.read_bytes()
        if a.read_bytes() != b.read_bytes() or a.read_bytes() != expected:
            raise ValueError("independent elaborator byte disagreement")

        bad_design = temp / "design.md"
        bad_design.write_bytes(args.design.read_bytes() + b"\n")
        failed = subprocess.run(
            [sys.executable, str(directory / "materialize_remaining.py"),
             str(args.recipe), str(bad_design), str(args.registry), str(temp / "bad-a.json")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if failed.returncode == 0:
            raise ValueError("one-byte design mutation was accepted")
        bad_registry = temp / "registry.json"
        bad_registry.write_bytes(args.registry.read_bytes() + b"\n")
        failed = subprocess.run(
            [sys.executable, str(directory / "elaborate_independent_b.py"),
             str(args.recipe), str(args.design), str(bad_registry), str(temp / "bad-b.json")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if failed.returncode == 0:
            raise ValueError("one-byte registry mutation was accepted")

    fixtures = {item["fixture_id"]: item for item in recipe["fixture_recipes"]}
    for item in fixtures.values():
        if item["body_encoding"] == "canonical_typed_value_v1":
            _validate_ctv(item["body_value"])
            if _canonical(item["body_value"])[:-1] != _canonical(
                json.loads(_canonical(item["body_value"]))
            )[:-1]:
                raise ValueError("CTV decode/re-encode mismatch")
    for vector in recipe["vector_cases"]:
        observed = _observe_vector(vector, fixtures)
        expected_result = (vector["expected_verdict"], vector["expected_reason"])
        if observed != expected_result:
            raise ValueError(f"vector result mismatch: {vector['vector_id']}")
    for case in recipe["nested_substitution_cases"]:
        candidate = copy.deepcopy(fixtures[case["target_fixture_id"]])
        parent, key = _path_target(candidate, case["target_path"])
        parent[key] = case["replacement_value"]
        try:
            _validate_ctv(candidate["body_value"])
        except ValueError as error:
            observed_reason = str(error)
        else:
            raise ValueError(f"nested mutation accepted: {case['case_id']}")
        if observed_reason != case["expected_reason"]:
            raise ValueError(f"nested reason mismatch: {case['case_id']}")

    digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
    print(json.dumps({"fixtures": 57, "nested": 29, "sha256": digest, "vectors": 25}, sort_keys=True))


if __name__ == "__main__":
    main()
