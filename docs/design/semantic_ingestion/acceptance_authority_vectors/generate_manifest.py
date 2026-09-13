"""Deterministically promote the acceptance authority registry into its manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REGISTRY = ROOT / "acceptance/resources/authority-schema-registry-v1.json"
MANIFEST = ROOT / "acceptance/generated/authority-schema-manifest-v1.json"


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


if __name__ == "__main__":
    main()
