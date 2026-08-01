"""Rebind the round-17 oracle-free recipe after the exhaustive enum correction."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        .encode("ascii")
        + b"\n"
    )


def digest(domain: str, value: bytes) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\0" + value).hexdigest()


def lp(value: str | bytes) -> bytes:
    raw = value if isinstance(value, bytes) else value.encode("ascii")
    return len(raw).to_bytes(8, "big") + raw


def marked(document: bytes, name: str, language: str) -> bytes:
    text = document.decode("utf-8")
    match = re.search(
        rf"^`\[{re.escape(name)}-BEGIN\]`\n```{language}\n(.*?)```\n"
        rf"`\[{re.escape(name)}-END\]`$",
        text,
        re.DOTALL | re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"missing marked {name}")
    return match.group(1).encode("ascii")


def bindings(document: bytes) -> tuple[str, dict[str, str]]:
    grammar = marked(document, "SIA-CTV-GRAMMAR-V1", "text")
    inventory = marked(document, "SIA-TRACEABILITY-SCHEMA-INVENTORY-V1", "text")
    enum_payload = marked(document, "SIA-CTV-ENUM-REGISTRY-V1", "json")
    schemas = inventory.decode("ascii").splitlines()
    if len(schemas) != 56 or schemas != sorted(set(schemas)):
        raise ValueError("schema inventory is not the closed sorted 56-root set")
    design_digest = digest("semantic-ingestion-traceability", document)
    grammar_digest = digest("memorii:sia-ctv-grammar:v1", grammar)
    inventory_digest = digest(
        "memorii:sia-traceability-schema-inventory:v1", inventory
    )
    enum_digest = digest("memorii:sia-ctv-enum-registry:v1", enum_payload)
    profile = digest(
        "memorii:sia-ctv-profile:v1",
        b"".join(
            lp(value)
            for value in (
                "semantic_ingestion_typed_value",
                "1",
                "sia-ctv-grammar-v1",
                grammar_digest,
                grammar,
                "sia-ctv-enum-registry-v1",
                enum_digest,
                enum_payload,
            )
        ),
    )
    domains = (
        (
            "schema_fingerprint",
            "memorii:sia-ctv-schema-fingerprint:v1",
            "closed_declared_schema_and_transitive_types",
        ),
        (
            "enum_registry",
            "memorii:sia-ctv-enum-registry:v1",
            "exact_literal_and_enum_members_in_registered_schema",
        ),
        (
            "optional_field_policy",
            "memorii:sia-ctv-optional-field-policy:v1",
            "exact_required_omittable_nullable_state_in_registered_schema",
        ),
        (
            "numeric_encoding_spec_registry",
            "memorii:sia-ctv-numeric-spec-registry:v1",
            "exact_field_constraints_and_no_ambient_numeric_default",
        ),
        (
            "digest_signature_field_policy",
            "memorii:sia-ctv-digest-signature-field-policy:v1",
            "exclude_only_the_named_outer_digest_and_signature_fields",
        ),
    )
    result = {}
    for schema in schemas:
        components = {}
        for name, domain, policy in domains:
            source = canonical(
                {
                    "component": name,
                    "design_document_digest": design_digest,
                    "policy": policy,
                    "profile_id": "semantic_ingestion_typed_value",
                    "profile_version": 1,
                    "schema_id": schema,
                    "schema_inventory_digest": inventory_digest,
                    "schema_version": 1,
                }
            )
            components[name] = digest(domain, source)
        result[schema] = digest(
            "memorii:sia-ctv-binding:v1",
            b"".join(
                lp(value)
                for value in (
                    "semantic_ingestion_typed_value",
                    "1",
                    profile,
                    schema,
                    "1",
                    components["schema_fingerprint"],
                    components["enum_registry"],
                    components["optional_field_policy"],
                    components["numeric_encoding_spec_registry"],
                    components["digest_signature_field_policy"],
                )
            ),
        )
    return profile, result


def ctv_fields(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value["entries"]}


def replace_ctv_fields(value: dict[str, Any], replacements: dict[str, Any]) -> None:
    value["entries"] = [
        [key, replacements.get(key, item)] for key, item in value["entries"]
    ]


def rebind(value: Any, profile: str, binding_by_schema: dict[str, str]) -> None:
    if isinstance(value, dict):
        if value.get("$type") == "map":
            fields = ctv_fields(value)
            binding_keys = {
                "binding_digest",
                "profile_digest",
                "profile_id",
                "profile_version",
                "schema_id",
                "schema_version",
            }
            if set(fields) == binding_keys:
                schema = fields["schema_id"]
                if schema not in binding_by_schema:
                    raise ValueError(f"unknown embedded binding schema {schema!r}")
                replace_ctv_fields(
                    value,
                    {
                        "binding_digest": binding_by_schema[schema],
                        "profile_digest": profile,
                    },
                )
            for _, child in value["entries"]:
                rebind(child, profile, binding_by_schema)
            fields = ctv_fields(value)
            boundary_keys = {
                "canonical_profile_id",
                "content_bytes",
                "content_digest",
                "content_schema_id",
                "content_schema_version",
                "content_size",
                "media_type",
            }
            if set(fields) == boundary_keys and fields["canonical_profile_id"] == (
                "semantic_ingestion_typed_value"
            ):
                raw = base64.b64decode(fields["content_bytes"]["value"], validate=True)
                trailing_lf = raw.endswith(b"\n")
                payload = json.loads(raw)
                rebind(payload, profile, binding_by_schema)
                raw = canonical(payload)
                if not trailing_lf:
                    raw = raw[:-1]
                schema = fields["content_schema_id"]
                version = fields["content_schema_version"]["value"]
                media = fields["media_type"]
                profile_id = fields["canonical_profile_id"]
                preimage = (
                    b"memorii:sia-canonical-content:v1\0"
                    + lp(schema)
                    + lp(version)
                    + lp(media)
                    + lp(profile_id)
                    + lp(raw)
                )
                replace_ctv_fields(
                    value,
                    {
                        "content_bytes": {
                            "$type": "bytes",
                            "value": base64.b64encode(raw).decode("ascii"),
                        },
                        "content_digest": hashlib.sha256(preimage).hexdigest(),
                        "content_size": {"$type": "integer", "value": str(len(raw))},
                    },
                )
        else:
            for child in value.values():
                rebind(child, profile, binding_by_schema)
    elif isinstance(value, list):
        for child in value:
            rebind(child, profile, binding_by_schema)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.registry.read_bytes()).hexdigest() != (
        "38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692"
    ):
        raise ValueError("registry identity mismatch")
    recipe = json.loads(args.recipe.read_bytes())
    profile, binding_by_schema = bindings(args.design.read_bytes())
    rebind(recipe, profile, binding_by_schema)
    args.output.write_bytes(canonical(recipe))


if __name__ == "__main__":
    main()
