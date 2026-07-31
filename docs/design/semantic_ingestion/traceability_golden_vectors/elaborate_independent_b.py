"""Independent standard-library elaborator B for the frozen C2 recipe."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def _canonical(document: object, final_lf: bool = True) -> bytes:
    result = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return result + (b"\n" if final_lf else b"")


def build(recipe_file: Path, design_file: Path, registry_file: Path) -> bytes:
    authority = json.loads(recipe_file.read_text(encoding="ascii"))
    records = []
    for specification in authority["fixture_recipes"]:
        representation = specification["body_value"]
        if specification["body_encoding"] == "raw_bytes":
            if representation.get("$type") != "bytes" or len(representation) != 2:
                raise ValueError("malformed raw recipe value")
            body_bytes = base64.b64decode(representation["value"], validate=True)
        elif specification["body_encoding"] == "canonical_typed_value_v1":
            body_bytes = _canonical(representation, final_lf=False)
            binding = specification["inner_binding"]
            if binding["binding_id"] != binding["schema_id"]:
                body_bytes += b"\n"
        else:
            raise ValueError("unsupported recipe encoding")

        artifact_kind = specification["target_artifact_kind"]
        if artifact_kind == "design_document":
            if body_bytes != design_file.read_bytes():
                raise ValueError("explicit design input differs from recipe")
        elif artifact_kind == "registry_source":
            if body_bytes != registry_file.read_bytes():
                raise ValueError("explicit registry input differs from recipe")

        ib = specification["inner_binding"]
        ob = specification["outer_binding"]
        record = {
            "depends_on_coordinates": specification["depends_on_coordinates"],
            "exact_reference_coordinates": specification[
                "exact_reference_coordinates"
            ],
            "expected_artifact_coordinate": specification[
                "expected_artifact_coordinate"
            ],
            "expected_artifact_digest": specification["expected_artifact_digest"],
            "expected_body_bytes_base64": base64.b64encode(body_bytes).decode(),
            "expected_body_digest": specification["expected_body_digest"],
            "expected_envelope_bytes_base64": specification[
                "expected_envelope_bytes_base64"
            ],
            "expected_historical_manifest_loads": specification[
                "expected_historical_manifest_loads"
            ],
            "expected_ordinary_historical_member_traversals": specification[
                "expected_ordinary_historical_member_traversals"
            ],
            "expected_signature_preimage_bytes_base64": specification[
                "expected_signature_preimage_bytes_base64"
            ],
            "expected_signatures_base64": specification[
                "expected_signatures_base64"
            ],
            "expected_total_manifest_loads": specification[
                "expected_total_manifest_loads"
            ],
            "fixture_id": specification["fixture_id"],
            "inner_body_binding_digest": ib["binding_digest"],
            "inner_body_binding_id": ib["binding_id"],
            "inner_body_schema_id": ib["schema_id"],
            "inner_body_schema_version": ib["schema_version"],
            "outer_envelope_binding_digest": ob["binding_digest"],
            "outer_envelope_binding_id": ob["binding_id"],
            "outer_envelope_schema_id": ob["schema_id"],
            "outer_envelope_schema_version": ob["schema_version"],
            "signer_coordinate_references": specification[
                "signer_coordinate_references"
            ],
            "target_artifact_kind": artifact_kind,
            "typed_input_bytes_base64": base64.b64encode(body_bytes).decode(),
        }
        records.append(record)

    result = {
        "format": "memorii-sia-traceability-golden-vector-source-v1",
        "manifest_id": "memorii-sia-traceability-golden-vectors-v1",
        "manifest_version": 1,
        "owner": "acceptance_independent_vector_author",
        "source_path": "docs/design/semantic_ingestion/traceability_golden_vectors/v1.json",
        "fixtures": records,
        "vectors": authority["vector_cases"],
    }
    return _canonical(result)


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("recipe", type=Path)
    cli.add_argument("design", type=Path)
    cli.add_argument("registry", type=Path)
    cli.add_argument("output", type=Path)
    options = cli.parse_args()
    options.output.write_bytes(
        build(options.recipe, options.design, options.registry)
    )


if __name__ == "__main__":
    main()
