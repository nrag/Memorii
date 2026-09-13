"""Independent authority-vector checker; it intentionally does not import acceptance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

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
    for vector, schema in zip(vectors["vectors"][:13], registry["schemas"], strict=True):
        if set(vector["value"]) != {field["name"] for field in schema["fields"]}:
            raise SystemExit(f"authority vector shape: {vector['name']}")
    for vector in vectors["vectors"]:
        if _encode(vector["value"]).decode("utf-8") != vector["expected_ctv"]:
            raise SystemExit(f"authority vector mismatch: {vector['name']}")


if __name__ == "__main__":
    main()
