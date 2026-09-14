"""One-shot deterministic promotion of registry field names to closed descriptors."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).with_name("authority-schema-registry-v1.json")
NULLABLE = {"predecessor_snapshot_digest", "predecessor_event_digest", "predecessor_commit_digest", "supersedes_release_digest", "revoked_at", "compromise_effective_at", "predecessor_checkpoint_digest", "active_release_digest", "active_release_epoch", "active_release_sequence", "issuance_snapshot_digest", "approval_release_digest"}
INTEGER = {"schema_version", "snapshot_sequence", "global_sequence", "key_history_head_sequence", "acceptance_release_epoch", "acceptance_release_sequence", "checkpoint_generation", "release_history_head_sequence", "active_epoch", "active_sequence", "prior_production_epoch", "advanced_production_epoch", "active_production_epoch", "transaction_sequence", "active_release_epoch", "active_release_sequence"}
TIMESTAMP = {"issued_at", "effective_at", "expires_at", "observed_at", "withdrawal_requested_at", "completed_at", "revoked_at", "compromise_effective_at"}
ENUMS = {"state": ["active", "retired", "revoked", "compromised"], "lifecycle_state": ["active", "retired", "revoked", "compromised"]}


def field(name: str, kind: str, *, nullable: bool = False, **extra: object) -> dict[str, object]:
    """Make one closed descriptor; V2 nested records are explicit below."""
    return {"name": name, "type": kind, "nullable": nullable, **extra}


def named(name: str, *, nullable: bool = False) -> dict[str, object]:
    return field(name, "named", nullable=nullable, type_name="CanonicalQuantity")


def v2_schema(
    identifier: str, purpose: str, digest_domain: str, signature_domain: str,
    digest_field: str, signer_field: str, fields: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "id": identifier, "purpose": purpose, "digest_domain": digest_domain,
        "signature_domain": signature_domain, "fields": fields,
        "schema_version": 2, "profile_binding_id": "memorii.acceptance.canonical-map.v1",
        "digest_field": digest_field, "signature_field": "signature",
        "signer_coordinate_field": signer_field,
    }


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
        "CanonicalQuantity": {"type": "map", "fields": [
            field("encoding_spec_id", "string", minimum_length=1, maximum_length=256),
            field("fixed_scale_value", "string", minimum_length=1, maximum_length=256),
        ]},
        "CoverageCell": {"type": "map", "fields": [
            field("behavior_lane", "string", minimum_length=1, maximum_length=256), field("cell_digest", "digest", digest_algorithm="sha256"),
            field("construction", "string", minimum_length=1, maximum_length=256), field("coverage_cell_id", "string", minimum_length=1, maximum_length=256),
            field("disposition", "string", enum=["enabled", "explicitly_unsupported"]), field("language", "string", minimum_length=1, maximum_length=256),
            field("predicate_family", "string", minimum_length=1, maximum_length=256),
            field("required_metric_ids", "array", item={"type": "string"}, minimum_items=0, maximum_items=1024, unique=True, sorted=True),
            field("unsupported_abstention_metric_id", "string", nullable=True, minimum_length=1, maximum_length=256),
        ]},
        "MetricGate": {"type": "map", "fields": [
            field("bound", "string", enum=["upper", "lower"]), named("cluster_value_lower_bound"), named("cluster_value_upper_bound"),
            field("coverage_cell_id", "string", minimum_length=1, maximum_length=256), field("estimand", "string", enum=["cluster_any_failure", "cluster_macro_mean"]),
            field("event_value_spec_id", "string", minimum_length=1, maximum_length=256), field("iid_declared", "boolean"), field("lower_spec_id", "string", minimum_length=1, maximum_length=256),
            field("metric_id", "string", minimum_length=1, maximum_length=256), field("minimum_clusters", "integer", minimum=1, maximum=9223372036854775807),
            named("nominal_alpha"), field("nominal_alpha_spec_id", "string", minimum_length=1, maximum_length=256), field("test_method", "string", enum=["exact_binomial", "weighted_hoeffding"]),
            named("threshold"), field("threshold_spec_id", "string", minimum_length=1, maximum_length=256), field("upper_spec_id", "string", minimum_length=1, maximum_length=256), field("weight_spec_id", "string", minimum_length=1, maximum_length=256),
        ]},
        "EncodingSpec": {"type": "map", "fields": [
            field("encoding_spec_id", "string", minimum_length=1, maximum_length=256), field("lower", "string", minimum_length=1, maximum_length=256),
            field("lower_inclusive", "boolean"), field("reject_inexact", "boolean"), field("scale", "integer", minimum=0, maximum=1024),
            field("unit", "string", minimum_length=1, maximum_length=256), field("upper", "string", minimum_length=1, maximum_length=256), field("upper_inclusive", "boolean"),
        ]},
        "GateIidProof": {"type": "map", "fields": [field("coverage_cell_id", "string", minimum_length=1, maximum_length=256), field("metric_id", "string", minimum_length=1, maximum_length=256), field("iid_bernoulli_clusters_proven", "boolean"), field("proof_digest", "digest", digest_algorithm="sha256")]},
        "SamplingMembership": {"type": "map", "fields": [
            field("coverage_cell_id", "string", minimum_length=1, maximum_length=256), field("metric_id", "string", minimum_length=1, maximum_length=256), field("cluster_id", "string", minimum_length=1, maximum_length=256),
            field("provenance_ids", "array", item={"type": "string"}, minimum_items=1, maximum_items=1024, unique=True, sorted=True), field("expected_event_ids", "array", item={"type": "string"}, minimum_items=1, maximum_items=1024, unique=True, sorted=True),
            named("weight"), named("lower"), named("upper"),
        ]},
    }
    for schema in registry["schemas"]:
        if schema["id"] in {"CapabilityBaselineApprovalRelease", "ApprovedCapabilityBaseline", "CapabilityCoverageManifest", "CapabilityStatisticalGateManifest", "CapabilitySamplingFrameManifest"}:
            continue
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
    # V2 replaces the legacy release as the only current authorization route.
    registry["schemas"] = [row for row in registry["schemas"] if row["id"] not in {"CapabilityBaselineApprovalRelease", "ApprovedCapabilityBaseline", "CapabilityCoverageManifest", "CapabilityStatisticalGateManifest", "CapabilitySamplingFrameManifest"}]
    common = [
        field("schema_version", "integer", minimum=2, maximum=2), field("purpose", "string", minimum_length=1, maximum_length=256),
        field("capability_fingerprint", "string", minimum_length=1, maximum_length=256), field("capability_contract_digest", "digest", digest_algorithm="sha256"),
        field("coverage_manifest_digest", "digest", digest_algorithm="sha256"), field("coverage_release_id", "string", minimum_length=1, maximum_length=256),
        field("statistical_gate_manifest_digest", "digest", digest_algorithm="sha256"), field("sampling_frame_manifest_digest", "digest", digest_algorithm="sha256"),
        field("sampling_frame_digest", "digest", digest_algorithm="sha256"), field("independent_cluster_definition_digest", "digest", digest_algorithm="sha256"), field("strata_definition_digest", "digest", digest_algorithm="sha256"), field("cluster_weighting_digest", "digest", digest_algorithm="sha256"), field("numeric_encoding_registry_digest", "digest", digest_algorithm="sha256"), field("unsupported_cells_digest", "digest", digest_algorithm="sha256"),
    ]
    release_fields = [field("schema_version", "integer", minimum=2, maximum=2), field("purpose", "string", minimum_length=1, maximum_length=256), field("approver_subject_id", "string", minimum_length=1, maximum_length=256), field("approved_baseline_artifact_digest", "digest", digest_algorithm="sha256"), *common[2:], field("acceptance_authority_snapshot_digest", "digest", digest_algorithm="sha256"), field("acceptance_release_epoch", "integer", minimum=1, maximum=9223372036854775807), field("acceptance_release_sequence", "integer", minimum=1, maximum=9223372036854775807), field("supersedes_release_digest", "digest", nullable=True, digest_algorithm="sha256"), field("issued_at", "timestamp"), field("expires_at", "timestamp"), field("lifecycle_state", "string", enum=ENUMS["lifecycle_state"]), field("revoked_at", "timestamp", nullable=True), field("compromise_effective_at", "timestamp", nullable=True), field("acceptance_signing_key_reference", "string", minimum_length=1, maximum_length=256), field("release_digest", "digest", digest_algorithm="sha256"), field("signature", "hex", minimum_length=128, maximum_length=128)]
    registry["schemas"].insert(3, v2_schema("CapabilityBaselineApprovalRelease", "semantic_ingestion_capability_baseline_approval.v2", "memorii.acceptance.capability-baseline-approval.v2", "memorii.acceptance.capability-baseline-approval.signature.v2", "release_digest", "acceptance_signing_key_reference", release_fields))
    registry["schemas"].extend([
        v2_schema("ApprovedCapabilityBaseline", "capability_baseline", "memorii.acceptance.capability_baseline.v2", "memorii.acceptance.capability_baseline.signature.v2", "manifest_digest", "signing_key_id", [*common, field("trust_policy_digest", "digest", digest_algorithm="sha256"), field("signing_key_id", "string", minimum_length=1, maximum_length=256), field("manifest_digest", "digest", digest_algorithm="sha256"), field("signature", "hex", minimum_length=128, maximum_length=128)]),
        v2_schema("CapabilityCoverageManifest", "capability_coverage_manifest", "memorii.acceptance.capability_coverage_manifest.v2", "memorii.acceptance.capability_coverage_manifest.signature.v2", "manifest_digest", "signing_key_id", [field("schema_version", "integer", minimum=2, maximum=2), field("purpose", "string", minimum_length=1, maximum_length=256), field("capability_fingerprint", "string", minimum_length=1, maximum_length=256), field("capability_contract_digest", "digest", digest_algorithm="sha256"), field("cells", "array", item={"type":"named","name":"CoverageCell"}, minimum_items=1, maximum_items=1024, unique=True, sorted=True), field("release_id", "string", minimum_length=1, maximum_length=256), field("trust_policy_digest", "digest", digest_algorithm="sha256"), field("signing_key_id", "string", minimum_length=1, maximum_length=256), field("manifest_digest", "digest", digest_algorithm="sha256"), field("signature", "hex", minimum_length=128, maximum_length=128)]),
        v2_schema("CapabilityStatisticalGateManifest", "capability_statistical_gate_manifest", "memorii.acceptance.capability_statistical_gate_manifest.v2", "memorii.acceptance.capability_statistical_gate_manifest.signature.v2", "manifest_digest", "signing_key_id", [field("schema_version", "integer", minimum=2, maximum=2), field("purpose", "string", minimum_length=1, maximum_length=256), field("capability_fingerprint", "string", minimum_length=1, maximum_length=256), field("capability_coverage_manifest_digest", "digest", digest_algorithm="sha256"), field("capability_coverage_release_id", "string", minimum_length=1, maximum_length=256), field("sampling_frame_manifest_digest", "digest", digest_algorithm="sha256"), field("numeric_encoding_registry_digest", "digest", digest_algorithm="sha256"), field("metric_gates", "array", item={"type":"named","name":"MetricGate"}, minimum_items=1, maximum_items=4096, unique=True, sorted=True), field("trust_policy_digest", "digest", digest_algorithm="sha256"), field("signing_key_id", "string", minimum_length=1, maximum_length=256), field("manifest_digest", "digest", digest_algorithm="sha256"), field("signature", "hex", minimum_length=128, maximum_length=128)]),
        v2_schema("CapabilitySamplingFrameManifest", "capability_sampling_frame_manifest", "memorii.acceptance.capability_sampling_frame_manifest.v2", "memorii.acceptance.capability_sampling_frame_manifest.signature.v2", "manifest_digest", "signing_key_id", [*common[:6], field("sampling_frame_digest", "digest", digest_algorithm="sha256"), field("independent_cluster_definition_digest", "digest", digest_algorithm="sha256"), field("strata_definition_digest", "digest", digest_algorithm="sha256"), field("cluster_weighting_digest", "digest", digest_algorithm="sha256"), field("numeric_encoding_registry_digest", "digest", digest_algorithm="sha256"), field("encoding_specs", "array", item={"type":"named","name":"EncodingSpec"}, minimum_items=1, maximum_items=256, unique=True, sorted=True), named("family_alpha"), field("family_alpha_spec_id", "string", minimum_length=1, maximum_length=256), field("gate_iid_proofs", "array", item={"type":"named","name":"GateIidProof"}, minimum_items=1, maximum_items=4096, unique=True, sorted=True), field("memberships", "array", item={"type":"named","name":"SamplingMembership"}, minimum_items=1, maximum_items=8192, unique=True, sorted=True), field("trust_policy_digest", "digest", digest_algorithm="sha256"), field("signing_key_id", "string", minimum_length=1, maximum_length=256), field("manifest_digest", "digest", digest_algorithm="sha256"), field("signature", "hex", minimum_length=128, maximum_length=128)]),
    ])
    PATH.write_bytes(json.dumps(registry, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n")


if __name__ == "__main__":
    main()
