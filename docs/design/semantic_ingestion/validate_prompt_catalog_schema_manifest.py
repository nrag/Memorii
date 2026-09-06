"""Validate and reproduce the closed prompt-catalog schema manifest."""

from __future__ import annotations

import hashlib
import json
import base64
import argparse
from pathlib import Path


ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "docs/design/semantic_ingestion/prompt-catalog-schema-manifest-v1.json"
ARTIFACT_DOMAIN = "memorii.semantic-ingestion.prompt-catalog-schema-manifest.v1"
SCHEMA_DOMAIN = "memorii.semantic-ingestion.prompt-catalog-schema.v1"
SEMANTIC_LITERAL_TOKENS = (
    "endpoint_kind_actor_object",
    "grounding_requirement_verbatim_source_mention",
    "subject_value_kind_entity",
    "object_value_kind_entity_literal",
)
EXPECTED_RECORD_FIELDS = {
    "memorii.semantic-ingestion.action-proposal-role-contract": [
        ["role_id", "identifier"],
        ["endpoint_kind", "endpoint_kind_actor_object"],
        ["description", "text"],
        ["grounding_requirement", "grounding_requirement_verbatim_source_mention"],
    ],
    "memorii.semantic-ingestion.action-proposal-state-contract": [
        ["state_id", "identifier"],
        ["description", "text"],
        ["allowed_role_ids", "action_role_id_tuple"],
        ["required_state_anchor", "literal_true"],
    ],
    "memorii.semantic-ingestion.predicate-prompt-contract": [
        ["predicate_id", "identifier"],
        ["description", "text"],
        ["subject_value_kind", "subject_value_kind_entity"],
        ["object_value_kind", "object_value_kind_entity_literal"],
        ["object_literal_type", "claim_value_type_or_null"],
        ["supported_commitments", "commitment_tuple"],
        ["contract_digest", "digest_lowercase_64hex"],
    ],
    "memorii.semantic-ingestion.action-proposal-catalog": [
        ["vocabulary_namespace", "identifier"],
        ["proposal_capability_fingerprint", "digest_lowercase_64hex"],
        ["roles", "action_role_contract_tuple"],
        ["states", "action_state_contract_tuple"],
        ["catalog_schema_fingerprint", "digest_lowercase_64hex"],
        ["catalog_fingerprint", "digest_lowercase_64hex"],
    ],
    "memorii.semantic-ingestion.predicate-proposal-catalog": [
        ["vocabulary_namespace", "identifier"],
        ["proposal_capability_fingerprint", "digest_lowercase_64hex"],
        ["predicates", "predicate_prompt_contract_tuple"],
        ["catalog_schema_fingerprint", "digest_lowercase_64hex"],
        ["catalog_fingerprint", "digest_lowercase_64hex"],
    ],
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"


def _ctv(value: object) -> object:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, bytes):
        return {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [_ctv(item) for item in value]}
    if isinstance(value, dict):
        return {"$type": "map", "entries": [[key, _ctv(value[key])] for key in sorted(value)]}
    raise TypeError(f"unsupported CTV value: {type(value)!r}")


def _digest(domain: str, payload: bytes) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\0" + payload).hexdigest()


def _entry_bytes(entry: dict[str, object]) -> bytes:
    return _canonical_json(entry)


def validate(manifest: dict[str, object]) -> tuple[str, dict[str, str]]:
    required = {"schema_manifest_version", "closed_wire_type_tokens", "record_schemas", "catalog_schemas"}
    if set(manifest) != required or manifest["schema_manifest_version"] != "v1":
        raise ValueError("manifest shape/version is not closed v1")
    tokens = manifest["closed_wire_type_tokens"]
    records = manifest["record_schemas"]
    catalogs = manifest["catalog_schemas"]
    if not isinstance(tokens, list) or not tokens or len(tokens) != len(set(tokens)):
        raise ValueError("closed type tokens must be unique and nonempty")
    if not isinstance(records, list) or not isinstance(catalogs, list):
        raise ValueError("schema entries must be lists")
    record_by_id: dict[str, dict[str, object]] = {}
    for entry in records:
        if not isinstance(entry, dict) or set(entry) != {"schema_id", "schema_version", "fields"}:
            raise ValueError("record schema shape is not closed")
        schema_id = entry["schema_id"]
        fields = entry["fields"]
        if not isinstance(schema_id, str) or entry["schema_version"] != "v1" or not isinstance(fields, list):
            raise ValueError("invalid record schema")
        names: list[str] = []
        for field in fields:
            if not isinstance(field, list) or len(field) != 2 or not all(isinstance(item, str) for item in field):
                raise ValueError("field declaration is not an exact pair")
            names.append(field[0])
            if field[1] not in tokens:
                raise ValueError("unknown closed wire type token")
        if len(names) != len(set(names)) or schema_id in record_by_id:
            raise ValueError("duplicate field or schema ID")
        if fields != EXPECTED_RECORD_FIELDS.get(schema_id):
            raise ValueError("record schema fields do not match the exact closed grammar")
        record_by_id[schema_id] = entry
    fingerprints: dict[str, str] = {}
    for entry in catalogs:
        if not isinstance(entry, dict) or set(entry) != {"schema_id", "schema_version", "embedded_schema_ids"}:
            raise ValueError("catalog schema shape is not closed")
        schema_id = entry["schema_id"]
        embedded = entry["embedded_schema_ids"]
        if not isinstance(schema_id, str) or entry["schema_version"] != "v1" or not isinstance(embedded, list):
            raise ValueError("invalid catalog schema")
        if schema_id not in record_by_id or not embedded or len(embedded) != len(set(embedded)):
            raise ValueError("catalog embedding is invalid")
        if any(item not in record_by_id for item in embedded):
            raise ValueError("unknown embedded schema")
        preimage = ("v1", _entry_bytes(entry), *(_entry_bytes(record_by_id[item]) for item in embedded), _entry_bytes(record_by_id[schema_id]))
        fingerprints[schema_id] = _digest(SCHEMA_DOMAIN, _canonical_json(_ctv(preimage)))
    if set(fingerprints) != {"memorii.semantic-ingestion.action-proposal-catalog", "memorii.semantic-ingestion.predicate-proposal-catalog"}:
        raise ValueError("catalog set is not exact")
    return _digest(ARTIFACT_DOMAIN, _canonical_json(manifest)), fingerprints


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    artifact = json.loads(MANIFEST.read_text(encoding="ascii"))
    digest, fingerprints = validate(artifact)
    if args.self_test:
        for schema_id, field_name, replacement in (
            ("memorii.semantic-ingestion.action-proposal-role-contract", "endpoint_kind", "grounding_requirement_verbatim_source_mention"),
            ("memorii.semantic-ingestion.action-proposal-role-contract", "grounding_requirement", "endpoint_kind_actor_object"),
            ("memorii.semantic-ingestion.predicate-prompt-contract", "subject_value_kind", "object_value_kind_entity_literal"),
            ("memorii.semantic-ingestion.predicate-prompt-contract", "object_value_kind", "subject_value_kind_entity"),
        ):
            malformed = json.loads(json.dumps(artifact))
            entry = next(item for item in malformed["record_schemas"] if item["schema_id"] == schema_id)
            field = next(item for item in entry["fields"] if item[0] == field_name)
            field[1] = replacement
            try:
                validate(malformed)
            except ValueError:
                pass
            else:
                raise AssertionError(f"self-test accepted changed {field_name} token")
        malformed = json.loads(json.dumps(artifact))
        malformed["closed_wire_type_tokens"].remove(SEMANTIC_LITERAL_TOKENS[0])
        try:
            validate(malformed)
        except ValueError:
            pass
        else:
            raise AssertionError("self-test accepted removed semantic token")
    print(json.dumps({"artifact_digest": digest, "schema_fingerprints": fingerprints}, sort_keys=True))
