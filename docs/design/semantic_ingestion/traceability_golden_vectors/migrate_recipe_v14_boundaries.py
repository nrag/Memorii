"""Migrate the frozen v14 C2 recipe to explicit canonical-content boundaries."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any


DESIGN_SHA256 = "bff1640cd6feff8561972ca30785a88e3d64503c4b72ec23826000f6fb55f90b"
RECIPE_SHA256 = "92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07"
REGISTRY_SHA256 = "38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692"
CTV_MEDIA_TYPE = "application/vnd.memorii.ctv+json;version=1"


def canonical(value: Any, final_lf: bool = True) -> bytes:
    result = json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    return result + (b"\n" if final_lf else b"")


def lp(value: str | bytes) -> bytes:
    raw = value if isinstance(value, bytes) else value.encode("ascii")
    return len(raw).to_bytes(8, "big") + raw


def field(value: dict[str, Any], name: str) -> Any:
    if value.get("$type") != "map":
        raise ValueError(f"expected CTV map while resolving {name}")
    matches = [item for key, item in value["entries"] if key == name]
    if len(matches) != 1:
        raise ValueError(f"field {name!r} does not resolve exactly once")
    return matches[0]


def set_field(value: dict[str, Any], name: str, replacement: Any) -> None:
    matches = [index for index, item in enumerate(value["entries"]) if item[0] == name]
    if len(matches) != 1:
        raise ValueError(f"field {name!r} does not resolve exactly once")
    value["entries"][matches[0]][1] = replacement


def integer(value: int) -> dict[str, str]:
    return {"$type": "integer", "value": str(value)}


def ctv_map(entries: dict[str, Any]) -> dict[str, Any]:
    return {"$type": "map", "entries": [[key, entries[key]] for key in sorted(entries)]}


def boundary(
    content: bytes,
    *,
    schema_id: str,
    schema_version: int,
    media_type: str,
    profile_id: str,
) -> dict[str, Any]:
    preimage = (
        b"memorii:sia-canonical-content:v1\0"
        + lp(schema_id)
        + lp(str(schema_version))
        + lp(media_type)
        + lp(profile_id)
        + lp(content)
    )
    return ctv_map(
        {
            "canonical_profile_id": profile_id,
            "content_bytes": {
                "$type": "bytes",
                "value": base64.b64encode(content).decode("ascii"),
            },
            "content_digest": hashlib.sha256(preimage).hexdigest(),
            "content_schema_id": schema_id,
            "content_schema_version": integer(schema_version),
            "content_size": integer(len(content)),
            "media_type": media_type,
        }
    )


def walk_leaves(value: Any, path: str) -> list[str]:
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


def migrate(recipe: dict[str, Any]) -> dict[str, Any]:
    authority = recipe["primitive_authority"]["authority_bodies"]
    expanded = recipe["expanded_typed_values"]
    bootstrap = expanded["fixture-01-bootstrap_anchor"]["typed_ctv"]
    runner = expanded["fixture-14-runner_report"]["typed_ctv"]

    structural = authority["fixture-10-structural_manifest"]["value"]
    report = field(structural, "report_schemas")["items"][0]
    if field(report, "schema_document") != {"$type": "map", "entries": []}:
        raise ValueError("unexpected legacy schema_document")
    set_field(
        report,
        "schema_document",
        boundary(
            b"{}",
            schema_id="memorii.semantic_ingestion.pytest_report",
            schema_version=1,
            media_type="application/schema+json",
            profile_id="memorii-sia-canonical-json-v1",
        ),
    )

    fixture35 = authority["fixture-35-golden_typed_input_fixture"]["value"]
    if field(fixture35, "typed_input_value") != (
        "memorii-c2-golden-typed-input-fixture-typed-input-value-v1"
    ):
        raise ValueError("unexpected fixture-35 legacy typed input")
    bootstrap_binding = field(bootstrap, "canonical_profile_binding")
    set_field(fixture35, "target_schema_id", "TraceabilityBootstrapTrustAnchorBody.v1")
    set_field(fixture35, "target_schema_version", integer(1))
    set_field(fixture35, "target_body_binding", bootstrap_binding)
    set_field(
        fixture35,
        "typed_input_value",
        boundary(
            canonical(bootstrap, final_lf=False),
            schema_id="TraceabilityBootstrapTrustAnchorBody.v1",
            schema_version=1,
            media_type=CTV_MEDIA_TYPE,
            profile_id="semantic_ingestion_typed_value",
        ),
    )

    manifest = authority["fixture-36-golden_vector_manifest"]["value"]
    fixture36 = field(manifest, "fixtures")["items"][0]
    if field(fixture36, "typed_input_value") != (
        "memorii-c2-golden-vector-manifest-typed-input-value-v1"
    ):
        raise ValueError("unexpected fixture-36 legacy typed input")
    runner_binding = field(runner, "canonical_profile_binding")
    set_field(fixture36, "target_schema_id", "TraceabilityRunnerReportBody.v1")
    set_field(fixture36, "target_schema_version", integer(1))
    set_field(fixture36, "target_body_binding", runner_binding)
    set_field(
        fixture36,
        "typed_input_value",
        boundary(
            canonical(runner, final_lf=False),
            schema_id="TraceabilityRunnerReportBody.v1",
            schema_version=1,
            media_type=CTV_MEDIA_TYPE,
            profile_id="semantic_ingestion_typed_value",
        ),
    )

    for fixture_id, record in expanded.items():
        authored = authority.get(fixture_id)
        if authored is not None:
            record["typed_ctv"] = authored["value"]

    fixture_by_id = {item["fixture_id"]: item for item in recipe["primitive_fixtures"]}
    ledgers = []
    typed_count = 0
    raw_count = 0
    for fixture_id in sorted(fixture_by_id):
        if fixture_id in expanded:
            paths = walk_leaves(
                expanded[fixture_id]["typed_ctv"], "$.expanded_typed_value"
            )
            typed_count += len(paths)
            rule, source = "expanded_authority_ctv", "deterministic_derivation"
        else:
            paths = walk_leaves(fixture_by_id[fixture_id]["body_input"], "$.body_input")
            raw_count += len(paths)
            rule, source = "explicit_raw_input", "primitive"
        ledgers.append(
            {
                "fields": [
                    {"path": path, "rule": rule, "source": source} for path in paths
                ],
                "fixture_id": fixture_id,
            }
        )
    recipe["field_coverage_ledger"] = ledgers
    recipe["typed_expansion_leaf_count"] = typed_count
    recipe["raw_leaf_count"] = raw_count
    recipe["expanded_leaf_denominator"] = typed_count + raw_count
    return recipe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    inputs = (
        (args.recipe, RECIPE_SHA256),
        (args.design, DESIGN_SHA256),
        (args.registry, REGISTRY_SHA256),
    )
    for path, expected in inputs:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"pinned input mismatch for {path}: {actual}")
    recipe = json.loads(args.recipe.read_bytes())
    args.output.write_bytes(canonical(migrate(recipe)))


if __name__ == "__main__":
    main()
