"""Closed acceptance authority schema inventory and canonical LP/CTV helpers."""
from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from importlib.resources import files
from typing import Any

from acceptance.ctv import encode_typed_value

_REGISTRY_FORMAT = "memorii.acceptance.authority-schema-registry.v1"
_MANIFEST_FORMAT = "memorii.acceptance.authority-schema-manifest.v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_REGISTRY_SHA256 = "11b23375581852ed5df51deb3c3d104c12e1d1f48bb845423264aabdef45b2ff"
_EXPECTED_IDS = ("AcceptanceTrustSnapshot", "KeyLifecycleEvent", "AcceptanceApprovalIssuanceSnapshot", "CapabilityBaselineApprovalRelease", "AcceptanceCurrentCheckpoint", "ProductionRevocationReceipt", "ProductionEpochCheckpoint", "AcceptanceEvaluationReceipt", "AcceptanceAuthorityCommit")

def registry_bytes() -> bytes:
    return files("acceptance").joinpath("resources/authority-schema-registry-v1.json").read_bytes()

def load_registry() -> dict[str, Any]:
    raw = registry_bytes()
    value = json.loads(raw)
    if type(value) is not dict or set(value) != {"format", "profile", "schemas", "types"} or value["format"] != _REGISTRY_FORMAT:
        raise ValueError("acceptance_authority_schema_registry")
    if sha256(raw).hexdigest() != _EXPECTED_REGISTRY_SHA256:
        raise ValueError("acceptance_authority_schema_registry_pin")
    schemas = value["schemas"]
    if type(schemas) is not list or len(schemas) != 9:
        raise ValueError("acceptance_authority_schema_registry")
    identifiers: set[str] = set()
    domains: set[str] = set()
    for row in schemas:
        required = {"id", "purpose", "digest_domain", "signature_domain", "fields", "schema_version", "profile_binding_id", "digest_field", "signature_field", "signer_coordinate_field"}
        if type(row) is not dict or set(row) != required:
            raise ValueError("acceptance_authority_schema_registry")
        if not all(isinstance(row[name], str) and row[name] for name in ("id", "purpose", "digest_domain")):
            raise ValueError("acceptance_authority_schema_registry")
        if not isinstance(row["signature_domain"], str) or (
            not row["signature_domain"] and row["id"] != "AcceptanceAuthorityCommit"
        ):
            raise ValueError("acceptance_authority_schema_registry")
        fields = row["fields"]
        if type(fields) is not list or not fields or any(type(field) is not dict for field in fields):
            raise ValueError("acceptance_authority_schema_registry")
        names = [field.get("name") for field in fields]
        if any(type(name) is not str or not name or field.get("type") not in {"string", "integer", "timestamp", "digest", "hex", "array"} for name, field in zip(names, fields, strict=True)):
            raise ValueError("acceptance_authority_schema_registry")
        if len(set(names)) != len(names) or row["id"] in identifiers or row["digest_domain"] in domains:
            raise ValueError("acceptance_authority_schema_registry")
        identifiers.add(row["id"])
        domains.add(row["digest_domain"])
    if tuple(row["id"] for row in schemas) != _EXPECTED_IDS:
        raise ValueError("acceptance_authority_schema_registry_ids")
    types = value["types"]
    if type(types) is not dict or set(types) != {"AcceptanceStaticKeyDeclaration", "ProductionRevocationEvidencePair"}:
        raise ValueError("acceptance_authority_schema_registry_types")
    return value


def manifest_bytes() -> bytes:
    return files("acceptance").joinpath("generated/authority-schema-manifest-v1.json").read_bytes()


def load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("acceptance_authority_schema_manifest") from exc
    registry = load_registry()
    if type(manifest) is not dict or manifest.get("format") != _MANIFEST_FORMAT:
        raise ValueError("acceptance_authority_schema_manifest")
    if manifest.get("registry_sha256") != sha256(registry_bytes()).hexdigest():
        raise ValueError("acceptance_authority_schema_manifest")
    schemas = manifest.get("schemas")
    if schemas != [{"id": row["id"], "purpose": row["purpose"], "digest_domain": row["digest_domain"]} for row in registry["schemas"]]:
        raise ValueError("acceptance_authority_schema_manifest")
    return manifest


def canonical_profile_binding_bytes() -> bytes:
    """Return the complete registered profile binding, never its identifier alone."""
    profile = load_registry()["profile"]
    if type(profile) is not dict or set(profile) not in ({"id", "decimal_encoding_policy_id"}, {"id", "decimal_encoding_policy_id", "parser_ceilings"}):
        raise ValueError("acceptance_profile_binding")
    ceilings = profile.get("parser_ceilings", {"maximum_bytes": 131072, "maximum_depth": 32, "maximum_nodes": 4096, "maximum_string_bytes": 16384, "maximum_integer_digits": 128})
    if type(ceilings) is not dict or not ceilings or any(type(value) is not int or value < 1 for value in ceilings.values()):
        raise ValueError("acceptance_profile_binding")
    return encode_typed_value({"id": profile["id"], "decimal_encoding_policy_id": profile["decimal_encoding_policy_id"], "parser_ceilings": ceilings})


def schema_for(schema_id: str) -> dict[str, Any]:
    for schema in load_registry()["schemas"]:
        if schema["id"] == schema_id:
            return schema
    raise ValueError("acceptance_schema_unknown")


def unsigned_artifact(value: dict[str, Any], schema_id: str) -> dict[str, Any]:
    schema = schema_for(schema_id)
    digest_name = schema["digest_field"]
    excluded = {name for name in (digest_name, "signature") if name is not None}
    return {key: item for key, item in value.items() if key not in excluded}


def validate_artifact(value: object, schema_id: str) -> dict[str, Any]:
    """Fail closed on field, purpose, digest, and basic registered type drift."""
    if type(value) is not dict:
        raise ValueError("acceptance_schema_value")
    schema = schema_for(schema_id)
    fields = schema["fields"]
    names = [field["name"] for field in fields]
    if set(value) != set(names):
        raise ValueError("acceptance_schema_fields")
    purpose_name = "approval_purpose" if schema_id == "CapabilityBaselineApprovalRelease" else "purpose"
    if value.get(purpose_name) != schema["purpose"]:
        raise ValueError("acceptance_schema_purpose")
    if value.get("schema_version") != schema["schema_version"]:
        raise ValueError("acceptance_schema_version")
    for field in fields:
        item = value[field["name"]]
        if item is None:
            if not field["nullable"]:
                raise ValueError("acceptance_schema_null")
            continue
        _validate_descriptor(item, field)
    if schema_id == "AcceptanceAuthorityCommit":
        active = (value["active_release_digest"], value["active_release_epoch"], value["active_release_sequence"])
        if any(part is None for part in active) and any(part is not None for part in active):
            raise ValueError("acceptance_schema_active_pointer")
        issuance = (value["issuance_snapshot_digest"], value["approval_release_digest"])
        if any(part is None for part in issuance) and any(part is not None for part in issuance):
            raise ValueError("acceptance_schema_issuance_pair")
    return value


def _validate_descriptor(value: object, descriptor: dict[str, Any]) -> None:
    kind = descriptor["type"]
    if kind == "integer" and (
        type(value) is not int
        or value < descriptor.get("minimum", -(2**63))
        or value > descriptor.get("maximum", 2**63 - 1)
    ):
        raise ValueError("acceptance_schema_integer")
    if kind == "digest" and (not isinstance(value, str) or not _DIGEST.fullmatch(value)):
        raise ValueError("acceptance_schema_nested_digest")
    if kind == "string" and (
        not isinstance(value, str)
        or len(value) < descriptor.get("minimum_length", 1)
        or len(value) > descriptor.get("maximum_length", 16384)
        or ("enum" in descriptor and value not in descriptor["enum"])
    ):
        raise ValueError("acceptance_schema_string")
    if kind == "hex" and (
        not isinstance(value, str)
        or len(value) < descriptor.get("minimum_length", 0)
        or len(value) > descriptor.get("maximum_length", 16384)
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("acceptance_schema_hex")
    if kind == "timestamp":
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
        except ValueError as exc:
            raise ValueError("acceptance_schema_timestamp") from exc
        if parsed is None or parsed.utcoffset() is None:
            raise ValueError("acceptance_schema_timestamp")
    if kind == "array":
        if (
            type(value) is not list
            or len(value) < descriptor.get("minimum_items", 0)
            or len(value) > descriptor.get("maximum_items", 1024)
        ):
            raise ValueError("acceptance_schema_array")
        encoded = [encode_typed_value(item) for item in value]
        if descriptor.get("unique", False) and len(set(encoded)) != len(encoded):
            raise ValueError("acceptance_schema_array_unique")
        if descriptor.get("sorted", False) and encoded != sorted(encoded):
            raise ValueError("acceptance_schema_array_order")
        for item in value:
            _validate_descriptor(item, descriptor["item"])
    if kind == "named":
        named = load_registry()["types"][descriptor["name"]]
        if named["type"] == "pair":
            if type(value) is not list or len(value) != 2:
                raise ValueError("acceptance_schema_pair")
            for item, child in zip(value, named["items"], strict=True):
                _validate_descriptor(item, child)
        elif named["type"] == "map":
            if type(value) is not dict or set(value) != {field["name"] for field in named["fields"]}:
                raise ValueError("acceptance_schema_named_map")
            for field in named["fields"]:
                item = value[field["name"]]
                if item is None:
                    if field["nullable"]:
                        continue
                    raise ValueError("acceptance_schema_nested_null")
                _validate_descriptor(item, field)


def decode_artifact(raw: bytes, schema_id: str) -> dict[str, Any]:
    """Bounded duplicate-free canonical JSON entry for one registered artifact."""
    ceilings = load_registry()["profile"].get(
        "parser_ceilings",
        {"maximum_bytes": 131072, "maximum_depth": 32, "maximum_nodes": 4096, "maximum_string_bytes": 16384, "maximum_integer_digits": 128},
    )
    if not isinstance(raw, bytes) or not raw or len(raw) > ceilings["maximum_bytes"]:
        raise ValueError("acceptance_schema_bytes")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("acceptance_schema_duplicate")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("acceptance_schema_json") from exc
    if json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") != raw:
        raise ValueError("acceptance_schema_noncanonical")
    _validate_json_ceiling(value, ceilings)
    validated = validate_artifact(value, schema_id)
    schema = schema_for(schema_id)
    unsigned = unsigned_artifact(validated, schema_id)
    expected = canonical_digest(schema["digest_domain"], "registered", unsigned)
    if validated[schema["digest_field"]] != expected:
        raise ValueError("acceptance_schema_digest_recomputed")
    return validated


def _validate_json_ceiling(value: object, ceilings: dict[str, Any], *, depth: int = 0) -> int:
    if depth > ceilings["maximum_depth"]:
        raise ValueError("acceptance_schema_depth")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > ceilings["maximum_string_bytes"]:
            raise ValueError("acceptance_schema_string_bytes")
        return 1
    if type(value) is int:
        if len(str(abs(value))) > ceilings["maximum_integer_digits"]:
            raise ValueError("acceptance_schema_integer_digits")
        return 1
    if type(value) in {type(None), bool}:
        return 1
    if type(value) is list:
        count = 1 + sum(_validate_json_ceiling(item, ceilings, depth=depth + 1) for item in value)
    elif type(value) is dict:
        count = 1 + sum(_validate_json_ceiling(key, ceilings, depth=depth + 1) + _validate_json_ceiling(item, ceilings, depth=depth + 1) for key, item in value.items())
    else:
        raise ValueError("acceptance_schema_native_type")
    if count > ceilings["maximum_nodes"]:
        raise ValueError("acceptance_schema_nodes")
    return count


def signing_preimage(schema_id: str, value: dict[str, Any], signer_coordinate: str) -> bytes:
    schema = schema_for(schema_id)
    registered_signer = schema["signer_coordinate_field"]
    if not schema["signature_domain"] or not isinstance(signer_coordinate, str) or not signer_coordinate or registered_signer is None:
        raise ValueError("acceptance_signing_preimage")
    validated = validate_artifact(value, schema_id)
    if validated[registered_signer] != signer_coordinate:
        raise ValueError("acceptance_signing_coordinate")
    body = unsigned_artifact(validated, schema_id)
    digest = canonical_digest(schema["digest_domain"], "registered", body)
    return lp(schema["signature_domain"].encode("ascii")) + lp(encode_typed_value({"purpose": schema["purpose"], "profile_binding": load_registry()["profile"], "signer_coordinate": signer_coordinate, "body_digest": digest, "unsigned_content": body}))

def lp(value: bytes) -> bytes:
    if not isinstance(value, bytes):
        raise ValueError("acceptance_lp")
    return len(value).to_bytes(8, "big") + value

def canonical_digest(domain: str, profile: str, value: object) -> str:
    if not isinstance(domain, str) or not isinstance(profile, str):
        raise ValueError("acceptance_digest")
    profile_bytes = canonical_profile_binding_bytes() if profile == "registered" else profile.encode("ascii")
    return sha256(lp(domain.encode("ascii")) + lp(profile_bytes) + lp(encode_typed_value(value))).hexdigest()
