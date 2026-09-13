from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal

from acceptance.ctv import encode_typed_value
from acceptance.numeric_context_authority import CoverageDisposition, unsupported_cells_digest, verify_numeric_context
from acceptance.schema_registry import canonical_digest, schema_for, signing_preimage, unsigned_artifact
from acceptance.statistical_certification import HeldBinding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _raw(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sorted(values: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(values, key=encode_typed_value)


def _signed(schema: str, key: Ed25519PrivateKey, coordinate: str, fields: dict[str, object]) -> tuple[str, bytes]:
    registered = schema_for(schema)
    digest_field = registered["digest_field"]
    value = {**fields, digest_field: "0" * 64, "signature": "0" * 128}
    value[digest_field] = canonical_digest(
        registered["digest_domain"], "registered", unsigned_artifact(value, schema)
    )
    value["signature"] = key.sign(signing_preimage(schema, value, coordinate)).hex()
    return value[digest_field], _raw(value)


@dataclass(frozen=True)
class V2AuthorityFixture:
    policy: bytes
    baseline: bytes
    release: bytes
    coverage: bytes
    gates: bytes
    sampling_frame: bytes
    release_digest: str
    binding: HeldBinding


def build_v2_authority(
    *, policy: bytes, evidence: bytes, key: Ed25519PrivateKey, coordinate: str,
    authority_snapshot_digest: str, now: datetime, issued_at: datetime | None = None,
    lifecycle_state: Literal["active", "retired", "revoked", "compromised"] = "active",
) -> V2AuthorityFixture:
    policy_value = json.loads(policy)
    policy_value["specs"] = _sorted(policy_value["specs"])
    policy_value["gates"] = _sorted(policy_value["gates"])
    policy_value["memberships"] = _sorted(policy_value["memberships"])
    policy = _raw(policy_value)
    capability = policy_value["gates"][0]["locator"]["capability_fingerprint"]
    cell = policy_value["gates"][0]["locator"]["cell_id"]
    metrics = sorted({gate["locator"]["metric_id"] for gate in policy_value["gates"]})
    contract_digest = "d" * 64
    trust_digest = "9" * 64
    release_id = "test-release"
    common_digests = {
        "sampling_frame_digest": "0" * 64,
        "independent_cluster_definition_digest": "1" * 64,
        "strata_definition_digest": "2" * 64,
        "cluster_weighting_digest": "3" * 64,
        "numeric_encoding_registry_digest": "4" * 64,
    }
    coverage_digest, coverage = _signed("CapabilityCoverageManifest", key, coordinate, {
        "schema_version": 2, "purpose": "capability_coverage_manifest",
        "capability_fingerprint": capability, "capability_contract_digest": contract_digest,
        "cells": [{
            "behavior_lane": "semantic_ingestion", "cell_digest": "5" * 64,
            "construction": "test", "coverage_cell_id": cell, "disposition": "enabled",
            "language": "und", "predicate_family": "test", "required_metric_ids": metrics,
            "unsupported_abstention_metric_id": None,
        }],
        "release_id": release_id, "trust_policy_digest": trust_digest, "signing_key_id": coordinate,
    })
    memberships = _sorted([{**{k: value for k, value in member.items() if k != "locator"},
        "coverage_cell_id": member["locator"]["cell_id"], "metric_id": member["locator"]["metric_id"]}
        for member in policy_value["memberships"]])
    iid = _sorted([{
        "coverage_cell_id": gate["locator"]["cell_id"], "metric_id": gate["locator"]["metric_id"],
        "iid_bernoulli_clusters_proven": gate["iid_declared"], "proof_digest": "6" * 64,
    } for gate in policy_value["gates"]])
    frame_digest, frame = _signed("CapabilitySamplingFrameManifest", key, coordinate, {
        "schema_version": 2, "purpose": "capability_sampling_frame_manifest",
        "capability_fingerprint": capability, "capability_contract_digest": contract_digest,
        "coverage_manifest_digest": coverage_digest, "coverage_release_id": release_id,
        **common_digests, "encoding_specs": _sorted(policy_value["specs"]),
        "family_alpha": policy_value["family_alpha"],
        "family_alpha_spec_id": policy_value["family_alpha_spec_id"],
        "gate_iid_proofs": iid, "memberships": memberships,
        "trust_policy_digest": trust_digest, "signing_key_id": coordinate,
    })
    metric_gates = _sorted([{
        "bound": gate["direction"], "cluster_value_lower_bound": next(member["lower"] for member in policy_value["memberships"] if member["locator"] == gate["locator"]),
        "cluster_value_upper_bound": next(member["upper"] for member in policy_value["memberships"] if member["locator"] == gate["locator"]),
        "coverage_cell_id": gate["locator"]["cell_id"], "estimand": gate["estimand"],
        "event_value_spec_id": gate["event_value_spec_id"], "iid_declared": gate["iid_declared"],
        "lower_spec_id": gate["lower_spec_id"], "metric_id": gate["locator"]["metric_id"],
        "minimum_clusters": gate["minimum_clusters"], "nominal_alpha": gate["nominal_alpha"],
        "nominal_alpha_spec_id": gate["nominal_alpha_spec_id"], "test_method": gate["method"],
        "threshold": gate["threshold"], "threshold_spec_id": gate["threshold_spec_id"],
        "upper_spec_id": gate["upper_spec_id"], "weight_spec_id": gate["weight_spec_id"],
    } for gate in policy_value["gates"]])
    gate_digest, gates = _signed("CapabilityStatisticalGateManifest", key, coordinate, {
        "schema_version": 2, "purpose": "capability_statistical_gate_manifest",
        "capability_fingerprint": capability, "capability_coverage_manifest_digest": coverage_digest,
        "capability_coverage_release_id": release_id, "sampling_frame_manifest_digest": frame_digest,
        "numeric_encoding_registry_digest": common_digests["numeric_encoding_registry_digest"],
        "metric_gates": metric_gates, "trust_policy_digest": trust_digest, "signing_key_id": coordinate,
    })
    disposition_digest = unsupported_cells_digest(tuple(
        CoverageDisposition(capability, cell, metric, "enabled") for metric in metrics
    ))
    baseline_fields = {
        "schema_version": 2, "purpose": "capability_baseline", "capability_fingerprint": capability,
        "capability_contract_digest": contract_digest, "coverage_manifest_digest": coverage_digest,
        "coverage_release_id": release_id, "statistical_gate_manifest_digest": gate_digest,
        "sampling_frame_manifest_digest": frame_digest, **common_digests,
        "unsupported_cells_digest": disposition_digest, "trust_policy_digest": trust_digest,
        "signing_key_id": coordinate,
    }
    _, baseline = _signed("ApprovedCapabilityBaseline", key, coordinate, baseline_fields)
    baseline_digest = sha256(baseline).hexdigest()
    release_fields = {
        "schema_version": 2, "purpose": "semantic_ingestion_capability_baseline_approval.v2",
        "approver_subject_id": "test-approver", "approved_baseline_artifact_digest": baseline_digest,
        **{name: baseline_fields[name] for name in (
            "capability_fingerprint", "capability_contract_digest", "coverage_manifest_digest", "coverage_release_id",
            "statistical_gate_manifest_digest", "sampling_frame_manifest_digest", "sampling_frame_digest",
            "independent_cluster_definition_digest", "strata_definition_digest", "cluster_weighting_digest",
            "numeric_encoding_registry_digest", "unsupported_cells_digest")},
        "acceptance_authority_snapshot_digest": authority_snapshot_digest,
        "acceptance_release_epoch": 1, "acceptance_release_sequence": 1,
        "supersedes_release_digest": None, "issued_at": (issued_at or now - timedelta(minutes=1)).isoformat(),
        "expires_at": ((now + timedelta(minutes=5)) if issued_at is None else issued_at + timedelta(days=2)).isoformat(),
        "lifecycle_state": lifecycle_state,
        "revoked_at": now.isoformat() if lifecycle_state == "revoked" else None,
        "compromise_effective_at": now.isoformat() if lifecycle_state == "compromised" else None,
        "acceptance_signing_key_reference": coordinate,
    }
    release_digest, release = _signed("CapabilityBaselineApprovalRelease", key, coordinate, release_fields)
    verified = verify_numeric_context(
        baseline_bytes=baseline, release_bytes=release, coverage_bytes=coverage, gate_bytes=gates,
        sampling_frame_bytes=frame, signing_keys={coordinate: key.public_key().public_bytes_raw()},
    )
    binding = HeldBinding(sha256(policy).hexdigest(), sha256(evidence).hexdigest(), verified.certification_context.authority, verified.certification_context)
    return V2AuthorityFixture(policy, baseline, release, coverage, gates, frame, release_digest, binding)
