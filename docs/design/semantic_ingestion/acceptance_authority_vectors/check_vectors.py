"""Independent authority-vector checker; it intentionally does not import acceptance."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[4]
REGISTRY = ROOT / "acceptance/resources/authority-schema-registry-v1.json"
MANIFEST = ROOT / "acceptance/generated/authority-schema-manifest-v1.json"
VECTORS = Path(__file__).with_name("v1.json")
VECTOR_MANIFEST = Path(__file__).with_name("manifest-v1.json")


def _string(value: str) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _encode(value: Any) -> bytes:
    if value is None:
        return b"null"
    if type(value) is bool:
        return b"true" if value else b"false"
    if type(value) is int:
        return b'{"$type":"integer","value":"' + str(value).encode("ascii") + b'"}'
    if type(value) is str:
        return _string(value)
    if type(value) is list:
        return b'{"$type":"list","items":[' + b",".join(_encode(item) for item in value) + b"]}"
    if type(value) is dict and all(type(key) is str for key in value):
        rows = sorted((_string(key), item) for key, item in value.items())
        return b'{"$type":"map","entries":[' + b",".join(
            b"[" + key + b"," + _encode(item) + b"]" for key, item in rows
        ) + b"]}"
    raise ValueError("vector_type")


def _lp(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def _unsigned(value: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    excluded = {schema["digest_field"], "signature"}
    return {name: item for name, item in value.items() if name not in excluded}


def _digest(domain: str, profile: dict[str, Any], value: object) -> str:
    return hashlib.sha256(
        _lp(domain.encode("ascii")) + _lp(_encode(profile)) + _lp(_encode(value))
    ).hexdigest()


def _preimage(value: dict[str, Any], schema: dict[str, Any], registry: dict[str, Any]) -> bytes:
    signer = value[schema["signer_coordinate_field"]]
    return _lp(schema["signature_domain"].encode("ascii")) + _lp(_encode({
        "purpose": schema["purpose"],
        "profile_binding": registry["profile"],
        "signer_coordinate": signer,
        "body_digest": value[schema["digest_field"]],
        "unsigned_content": _unsigned(value, schema),
    }))


def _descriptor(value: object, descriptor: dict[str, Any], types: dict[str, Any]) -> None:
    if value is None:
        if descriptor.get("nullable"):
            return
        raise ValueError("null")
    kind = descriptor["type"]
    if kind == "integer":
        if type(value) is not int or not descriptor.get("minimum", -(2**63)) <= value <= descriptor.get("maximum", 2**63 - 1):
            raise ValueError("integer")
    elif kind == "boolean":
        if type(value) is not bool:
            raise ValueError("boolean")
    elif kind == "digest":
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("digest")
    elif kind == "hex":
        if (
            not isinstance(value, str)
            or len(value) < descriptor.get("minimum_length", 0)
            or len(value) > descriptor.get("maximum_length", 16384)
            or re.fullmatch(r"[0-9a-f]*", value) is None
        ):
            raise ValueError("hex")
    elif kind == "timestamp":
        if not isinstance(value, str):
            raise ValueError("timestamp")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError("timestamp")
    elif kind == "string":
        if (
            not isinstance(value, str)
            or len(value) < descriptor.get("minimum_length", 1)
            or len(value) > descriptor.get("maximum_length", 16384)
            or ("enum" in descriptor and value not in descriptor["enum"])
        ):
            raise ValueError("string")
    elif kind == "array":
        if (
            type(value) is not list
            or len(value) < descriptor.get("minimum_items", 0)
            or len(value) > descriptor.get("maximum_items", 1024)
        ):
            raise ValueError("array")
        encoded = [_encode(item) for item in value]
        if descriptor.get("unique") and len(set(encoded)) != len(encoded):
            raise ValueError("array_unique")
        if descriptor.get("sorted") and encoded != sorted(encoded):
            raise ValueError("array_order")
        for item in value:
            _descriptor(item, descriptor["item"], types)
    elif kind == "named":
        named = types[descriptor.get("type_name", descriptor["name"])]
        if named["type"] == "pair":
            if type(value) is not list or len(value) != 2:
                raise ValueError("pair")
            for item, child in zip(value, named["items"], strict=True):
                _descriptor(item, child, types)
        else:
            if type(value) is not dict or set(value) != {field["name"] for field in named["fields"]}:
                raise ValueError("map")
            for field in named["fields"]:
                _descriptor(value[field["name"]], field, types)
    else:
        raise ValueError("descriptor")


def _registered(value: dict[str, Any], schema: dict[str, Any], registry: dict[str, Any]) -> None:
    if set(value) != {field["name"] for field in schema["fields"]}:
        raise ValueError("shape")
    if value["purpose"] != schema["purpose"] or value["schema_version"] != schema["schema_version"]:
        raise ValueError("purpose_or_version")
    for field in schema["fields"]:
        _descriptor(value[field["name"]], field, registry["types"])


def main() -> None:
    registry_raw = REGISTRY.read_bytes()
    registry = json.loads(registry_raw)
    manifest = json.loads(MANIFEST.read_bytes())
    vectors = json.loads(VECTORS.read_bytes())
    vector_manifest = json.loads(VECTOR_MANIFEST.read_bytes())
    if manifest["registry_sha256"] != hashlib.sha256(registry_raw).hexdigest():
        raise SystemExit("stale authority manifest")
    if vector_manifest != {
        "format": "memorii.acceptance.authority-vector-manifest.v1",
        "registry_sha256": hashlib.sha256(registry_raw).hexdigest(),
        "generated_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "vectors_sha256": hashlib.sha256(VECTORS.read_bytes()).hexdigest(),
        "schema_count": 13,
        "profile_count": 1,
        "digest_domain_count": 13,
    }:
        raise SystemExit("authority vector manifest")
    if len(registry["schemas"]) != len(manifest["schemas"]) or len(registry["schemas"]) != 13:
        raise SystemExit("authority schema cardinality")
    if [vector["name"] for vector in vectors["vectors"][:13]] != [row["id"] for row in registry["schemas"]]:
        raise SystemExit("authority vector inventory")
    if vectors.get("signing_key_id") != "fixture-authority-key":
        raise SystemExit("authority vector signer")
    verifier = Ed25519PublicKey.from_public_bytes(bytes.fromhex(vectors["public_key_hex"]))
    for vector, schema in zip(vectors["vectors"][:13], registry["schemas"], strict=True):
        if set(vector["value"]) != {field["name"] for field in schema["fields"]}:
            raise SystemExit(f"authority vector shape: {vector['name']}")
        value = vector["value"]
        _registered(value, schema, registry)
        for name, changed in (
            ("purpose", {**value, "purpose": str(value["purpose"]) + ".tampered"}),
            ("version", {**value, "schema_version": 0}),
            ("type", {**value, schema["fields"][0]["name"]: object()}),
        ):
            try:
                _registered(changed, schema, registry)
            except ValueError:
                pass
            else:
                raise SystemExit(f"authority vector {name} mutation admitted: {vector['name']}")
        digest = _digest(schema["digest_domain"], registry["profile"], _unsigned(value, schema))
        if value[schema["digest_field"]] != digest:
            raise SystemExit(f"authority vector digest: {vector['name']}")
        signer_field = schema["signer_coordinate_field"]
        if signer_field is not None:
            try:
                verifier.verify(bytes.fromhex(value["signature"]), _preimage(value, schema, registry))
            except (InvalidSignature, ValueError) as exc:
                raise SystemExit(f"authority vector signature: {vector['name']}") from exc
            tampered = dict(value)
            tampered["purpose"] = value["purpose"] + ".tampered"
            try:
                verifier.verify(bytes.fromhex(value["signature"]), _preimage(tampered, schema, registry))
            except InvalidSignature:
                pass
            else:
                raise SystemExit(f"authority vector mutation admitted: {vector['name']}")
    for vector in vectors["vectors"]:
        if _encode(vector["value"]).decode("utf-8") != vector["expected_ctv"]:
            raise SystemExit(f"authority vector mismatch: {vector['name']}")


if __name__ == "__main__":
    main()
