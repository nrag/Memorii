"""Clean-room standard-library elaborator A for the normative scenario-first closure recipe."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any


def _json_bytes(value: Any, newline: bool = True) -> bytes:
    encoded = json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    return encoded + (b"\n" if newline else b"")


def _body(item: dict[str, Any]) -> bytes:
    value = item["body_value"]
    if item["body_encoding"] == "raw_bytes":
        if set(value) != {"$type", "value"} or value["$type"] != "bytes":
            raise ValueError(f"{item['fixture_id']}: invalid raw body")
        return base64.b64decode(value["value"], validate=True)
    if item["body_encoding"] != "canonical_typed_value_v1":
        raise ValueError(f"{item['fixture_id']}: unknown body encoding")
    raw = _json_bytes(value, newline=False)
    # Raw canonical-JSON bodies retain their specified trailing LF.
    if item["inner_binding"]["binding_id"] != item["inner_binding"]["schema_id"]:
        raw += b"\n"
    return raw


def elaborate(recipe_path: Path, design_path: Path, registry_path: Path) -> bytes:
    recipe = json.loads(recipe_path.read_bytes())
    fixtures: list[dict[str, Any]] = []
    for item in recipe["fixture_recipes"]:
        body = _body(item)
        kind = item["target_artifact_kind"]
        if kind == "design_document" and body != design_path.read_bytes():
            raise ValueError("recipe design bytes do not match explicit design input")
        if kind == "registry_source" and body != registry_path.read_bytes():
            raise ValueError("recipe registry bytes do not match explicit registry input")
        inner, outer = item["inner_binding"], item["outer_binding"]
        fixtures.append(
            {
                "depends_on_coordinates": item["depends_on_coordinates"],
                "exact_reference_coordinates": item["exact_reference_coordinates"],
                "expected_artifact_coordinate": item["expected_artifact_coordinate"],
                "expected_artifact_digest": item["expected_artifact_digest"],
                "expected_body_bytes_base64": base64.b64encode(body).decode("ascii"),
                "expected_body_digest": item["expected_body_digest"],
                "expected_envelope_bytes_base64": item[
                    "expected_envelope_bytes_base64"
                ],
                "expected_historical_manifest_loads": item[
                    "expected_historical_manifest_loads"
                ],
                "expected_ordinary_historical_member_traversals": item[
                    "expected_ordinary_historical_member_traversals"
                ],
                "expected_signature_preimage_bytes_base64": item[
                    "expected_signature_preimage_bytes_base64"
                ],
                "expected_signatures_base64": item["expected_signatures_base64"],
                "expected_total_manifest_loads": item[
                    "expected_total_manifest_loads"
                ],
                "fixture_id": item["fixture_id"],
                "inner_body_binding_digest": inner["binding_digest"],
                "inner_body_binding_id": inner["binding_id"],
                "inner_body_schema_id": inner["schema_id"],
                "inner_body_schema_version": inner["schema_version"],
                "outer_envelope_binding_digest": outer["binding_digest"],
                "outer_envelope_binding_id": outer["binding_id"],
                "outer_envelope_schema_id": outer["schema_id"],
                "outer_envelope_schema_version": outer["schema_version"],
                "signer_coordinate_references": item[
                    "signer_coordinate_references"
                ],
                "target_artifact_kind": kind,
                "typed_input_bytes_base64": base64.b64encode(body).decode("ascii"),
            }
        )
    package = {
        "fixtures": fixtures,
        "format": "memorii-sia-traceability-golden-vector-source-v1",
        "manifest_id": "memorii-sia-traceability-golden-vectors-v1",
        "manifest_version": 1,
        "owner": "acceptance_independent_vector_author",
        "source_path": "docs/design/semantic_ingestion/traceability_golden_vectors/v1.json",
        "vectors": recipe["vector_cases"],
    }
    return _json_bytes(package)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", type=Path)
    parser.add_argument("design", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(elaborate(args.recipe, args.design, args.registry))


if __name__ == "__main__":
    main()
