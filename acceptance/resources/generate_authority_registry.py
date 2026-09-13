"""One-shot deterministic promotion of registry field names to closed descriptors."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).with_name("authority-schema-registry-v1.json")
NULLABLE = {"predecessor_snapshot_digest", "predecessor_event_digest", "predecessor_commit_digest", "supersedes_release_digest", "revoked_at", "compromise_effective_at", "predecessor_checkpoint_digest", "active_release_digest", "active_release_epoch", "active_release_sequence", "issuance_snapshot_digest", "approval_release_digest"}
INTEGER = {"schema_version", "snapshot_sequence", "global_sequence", "key_history_head_sequence", "acceptance_release_epoch", "acceptance_release_sequence", "checkpoint_generation", "release_history_head_sequence", "active_epoch", "active_sequence", "prior_production_epoch", "advanced_production_epoch", "active_production_epoch", "transaction_sequence", "active_release_epoch", "active_release_sequence"}
TIMESTAMP = {"issued_at", "effective_at", "expires_at", "observed_at", "withdrawal_requested_at", "completed_at", "revoked_at", "compromise_effective_at"}
ENUMS = {"state": ["active", "retired", "revoked", "compromised"], "lifecycle_state": ["active", "retired", "revoked", "compromised"]}


def descriptor(name: str) -> dict[str, object]:
    result: dict[str, object] = {"name": name, "nullable": name in NULLABLE}
    if name in INTEGER:
        result.update({"type": "integer", "minimum": 1, "maximum": 9_223_372_036_854_775_807})
    elif name in TIMESTAMP:
        result["type"] = "timestamp"
    elif name in ENUMS:
        result.update({"type": "string", "enum": ENUMS[name]})
    elif name.endswith("_digest"):
        result.update({"type": "digest", "digest_algorithm": "sha256"})
    elif name == "signature":
        result.update({"type": "hex", "minimum_length": 128, "maximum_length": 128})
    elif name in {"key_event_digests", "active_authorization_digests", "revocation_receipt_digests"}:
        result.update({"type": "array", "item": {"type": "digest"}, "minimum_items": 1, "unique": True, "ordered": True})
    elif name == "production_revocation_evidence":
        result.update({"type": "array", "item": {"type": "named", "name": "ProductionRevocationEvidencePair"}, "minimum_items": 0, "maximum_items": 1024, "unique": True, "ordered": True})
    elif name == "key_declarations":
        result.update({"type": "array", "item": {"type": "named", "name": "AcceptanceStaticKeyDeclaration"}, "minimum_items": 1, "maximum_items": 1024, "unique": True, "ordered": True})
    else:
        result.update({"type": "string", "minimum_length": 1, "maximum_length": 16384})
    return result


def main() -> None:
    registry = json.loads(PATH.read_bytes())
    registry["profile"] = {
        "id": "memorii.acceptance.canonical-map.v1",
        "decimal_encoding_policy_id": "memorii.decimal.fixed-scale.v1",
        "parser_ceilings": {"maximum_bytes": 131072, "maximum_depth": 32, "maximum_nodes": 4096, "maximum_string_bytes": 16384, "maximum_integer_digits": 128},
    }
    registry["types"] = {
        "AcceptanceStaticKeyDeclaration": {"type": "map", "fields": [
            {"name": "key_reference", "type": "string", "nullable": False, "minimum_length": 1, "maximum_length": 256},
            {"name": "public_key", "type": "hex", "nullable": False, "minimum_length": 64, "maximum_length": 64},
            {"name": "valid_from", "type": "timestamp", "nullable": False},
            {"name": "valid_until", "type": "timestamp", "nullable": True},
            {"name": "allowed_purposes", "type": "array", "nullable": False, "item": {"type": "string"}, "minimum_items": 1, "maximum_items": 32, "unique": True, "ordered": True},
        ]},
        "ProductionRevocationEvidencePair": {"type": "pair", "items": [{"type": "digest"}, {"type": "digest"}]},
    }
    for schema in registry["schemas"]:
        schema["fields"] = [descriptor(item if isinstance(item, str) else item["name"]) for item in schema["fields"]]
        schema["schema_version"] = 1
        schema["profile_binding_id"] = registry["profile"]["id"]
        schema["digest_field"] = next(item["name"] for item in schema["fields"] if item["name"] in {"snapshot_digest", "event_digest", "release_digest", "checkpoint_digest", "receipt_digest", "commit_digest"})
        schema["signature_field"] = None if schema["id"] == "AcceptanceAuthorityCommit" else "signature"
        schema["signer_coordinate_field"] = (
            None
            if schema["id"] == "AcceptanceAuthorityCommit"
            else "acceptance_signing_key_reference"
            if schema["id"] == "CapabilityBaselineApprovalRelease"
            else "signing_key_coordinate"
        )
    PATH.write_bytes(json.dumps(registry, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n")


if __name__ == "__main__":
    main()
