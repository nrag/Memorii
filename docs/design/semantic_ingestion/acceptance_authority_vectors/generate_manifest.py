"""Deterministically promote the acceptance authority registry into its manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[4]
REGISTRY = ROOT / "acceptance/resources/authority-schema-registry-v1.json"
MANIFEST = ROOT / "acceptance/generated/authority-schema-manifest-v1.json"
VECTORS = Path(__file__).with_name("v1.json")
VECTOR_MANIFEST = Path(__file__).with_name("manifest-v1.json")


def _encoded(value: Any) -> bytes:
    if value is None:
        return b"null"
    if type(value) is bool:
        return b"true" if value else b"false"
    if type(value) is int:
        return b'{"$type":"integer","value":"' + str(value).encode("ascii") + b'"}'
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if type(value) is list:
        return b'{"$type":"list","items":[' + b",".join(_encoded(item) for item in value) + b"]}"
    if type(value) is dict:
        rows = sorted((json.dumps(key, ensure_ascii=False).encode("utf-8"), item) for key, item in value.items())
        return b'{"$type":"map","entries":[' + b",".join(b"[" + key + b"," + _encoded(item) + b"]" for key, item in rows) + b"]}"
    raise TypeError("authority_vector_value")


def _sample(descriptor: dict[str, Any], types: dict[str, Any], field_name: str) -> Any:
    if descriptor.get("nullable"):
        return None
    kind = descriptor["type"]
    if kind == "integer":
        return max(1, descriptor.get("minimum", 1))
    if kind == "boolean":
        return True
    if kind == "digest":
        return "0" * 64
    if kind == "hex":
        return "0" * descriptor.get("minimum_length", 2)
    if kind == "timestamp":
        return "2026-01-01T00:00:00Z"
    if kind == "string":
        return descriptor.get("enum", [field_name])[0]
    if kind == "array":
        count = descriptor.get("minimum_items", 0)
        return [_sample(descriptor["item"], types, field_name) for _ in range(count)]
    if kind == "named":
        return _sample(types[descriptor.get("type_name", descriptor["name"])], types, field_name)
    if kind == "map":
        return {item["name"]: _sample(item, types, item["name"]) for item in descriptor["fields"]}
    if kind == "pair":
        return [_sample(item, types, field_name) for item in descriptor["items"]]
    raise TypeError(f"authority_vector_descriptor:{kind}")


def _lp(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def _digest(domain: str, profile: dict[str, Any], value: object) -> str:
    return hashlib.sha256(
        _lp(domain.encode("ascii")) + _lp(_encoded(profile)) + _lp(_encoded(value))
    ).hexdigest()


def _unsigned(value: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    excluded = {schema["digest_field"], "signature"}
    return {name: item for name, item in value.items() if name not in excluded}


def main() -> None:
    raw = REGISTRY.read_bytes()
    registry = json.loads(raw)
    manifest = {
        "format": "memorii.acceptance.authority-schema-manifest.v1",
        "registry_resource": REGISTRY.name,
        "registry_sha256": hashlib.sha256(raw).hexdigest(),
        "schemas": [
            {"id": row["id"], "purpose": row["purpose"], "digest_domain": row["digest_domain"]}
            for row in registry["schemas"]
        ],
    }
    MANIFEST.write_bytes(json.dumps(manifest, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n")
    signing_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("1f" * 32))
    signer = "fixture-authority-key"
    vectors = []
    for schema in registry["schemas"]:
        value = {item["name"]: _sample(item, registry["types"], item["name"]) for item in schema["fields"]}
        value["schema_version"] = schema["schema_version"]
        value["purpose"] = schema["purpose"]
        signer_field = schema["signer_coordinate_field"]
        if signer_field is not None:
            value[signer_field] = signer
        if schema["id"] == "AcceptanceTrustSnapshot":
            value["key_declarations"][0]["key_reference"] = signer
            value["key_declarations"][0]["public_key"] = signing_key.public_key().public_bytes_raw().hex()
        value[schema["digest_field"]] = _digest(
            schema["digest_domain"], registry["profile"], _unsigned(value, schema)
        )
        if signer_field is not None:
            preimage = _lp(schema["signature_domain"].encode("ascii")) + _lp(_encoded({
                "purpose": schema["purpose"],
                "profile_binding": registry["profile"],
                "signer_coordinate": signer,
                "body_digest": value[schema["digest_field"]],
                "unsigned_content": _unsigned(value, schema),
            }))
            value["signature"] = signing_key.sign(preimage).hex()
        vectors.append({"name": schema["id"], "value": value, "expected_ctv": _encoded(value).decode("utf-8")})
    boundary = {"z": -1, "ä": 9223372036854775807}
    vectors.append({"name": "unicode_integer_boundary", "value": boundary, "expected_ctv": _encoded(boundary).decode("utf-8")})
    VECTORS.write_bytes(json.dumps({
        "format": "memorii.acceptance.authority-vectors.v1",
        "signing_key_id": signer,
        "public_key_hex": signing_key.public_key().public_bytes_raw().hex(),
        "vectors": vectors,
    }, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n")
    vector_manifest = {
        "format": "memorii.acceptance.authority-vector-manifest.v1",
        "registry_sha256": hashlib.sha256(raw).hexdigest(),
        "generated_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "vectors_sha256": hashlib.sha256(VECTORS.read_bytes()).hexdigest(),
        "schema_count": len(registry["schemas"]),
        "profile_count": 1,
        "digest_domain_count": len({row["digest_domain"] for row in registry["schemas"]}),
    }
    VECTOR_MANIFEST.write_bytes(json.dumps(vector_manifest, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n")


if __name__ == "__main__":
    main()
