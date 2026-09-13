"""Registered V2 numeric authority reconstruction.

Candidate policy and evidence never select numeric semantics.  This module
accepts only the five signed, registered V2 manifests and projects their
closed content into the certification context consumed by the evaluator.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from acceptance.ctv import encode_typed_value
from acceptance.schema_registry import decode_artifact, signing_preimage
from acceptance.statistical_certification import (
    CanonicalDecimalQuantity, EncodingSpec, Gate, GateLocator, Membership,
    NumericAuthority,
    HeldBinding, PreverifiedNumericCertificationContext, PreverifiedNumericGate,
)


class NumericContextAuthorityRejected(ValueError):
    """The signed numeric authority chain is not a single closed V2 context."""


@dataclass(frozen=True, order=True)
class CoverageDisposition:
    capability_fingerprint: str
    coverage_cell_id: str
    metric_id: str
    disposition: str


@dataclass(frozen=True)
class VerifiedNumericAuthority:
    approved_baseline_artifact_digest: str
    verified_baseline_approval_release_digest: str
    capability_fingerprint: str
    capability_contract_digest: str
    coverage_manifest_digest: str
    coverage_release_id: str
    statistical_gate_manifest_digest: str
    sampling_frame_manifest_digest: str
    sampling_frame_digest: str
    independent_cluster_definition_digest: str
    strata_definition_digest: str
    cluster_weighting_digest: str
    numeric_encoding_registry_digest: str
    unsupported_cells_digest: str


@dataclass(frozen=True)
class VerifiedNumericContext:
    authority: VerifiedNumericAuthority
    dispositions: tuple[CoverageDisposition, ...]
    certification_context: PreverifiedNumericCertificationContext


_SCHEMAS = (
    "ApprovedCapabilityBaseline", "CapabilityBaselineApprovalRelease",
    "CapabilityCoverageManifest", "CapabilityStatisticalGateManifest",
    "CapabilitySamplingFrameManifest",
)


def _signed(raw: bytes, schema: str, keys: Mapping[str, bytes]) -> dict[str, Any]:
    try:
        value = cast(dict[str, Any], decode_artifact(raw, schema))
        coordinate = value["acceptance_signing_key_reference"] if schema == "CapabilityBaselineApprovalRelease" else value["signing_key_id"]
        if not isinstance(coordinate, str) or coordinate not in keys:
            raise NumericContextAuthorityRejected("numeric_context_signer")
        signature = value["signature"]
        if not isinstance(signature, str):
            raise NumericContextAuthorityRejected("numeric_context_signature")
        Ed25519PublicKey.from_public_bytes(keys[coordinate]).verify(
            bytes.fromhex(signature), signing_preimage(schema, value, coordinate)
        )
        return value
    except (InvalidSignature, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, NumericContextAuthorityRejected):
            raise
        raise NumericContextAuthorityRejected("numeric_context_signature") from exc


def _dispositions(coverage: dict[str, Any]) -> tuple[CoverageDisposition, ...]:
    fingerprint = str(coverage["capability_fingerprint"])
    rows: list[CoverageDisposition] = []
    for value in coverage["cells"]:  # schema already closed and typed
        assert isinstance(value, dict)
        disposition, cell = value["disposition"], value["coverage_cell_id"]
        if disposition == "enabled":
            for metric in value["required_metric_ids"]:
                rows.append(CoverageDisposition(fingerprint, str(cell), str(metric), "enabled"))
        elif disposition == "explicitly_unsupported":
            rows.append(CoverageDisposition(fingerprint, str(cell), str(value["unsupported_abstention_metric_id"]), "explicitly_unsupported"))
        else:
            raise NumericContextAuthorityRejected("numeric_context_disposition")
    answer = tuple(sorted(rows, key=lambda row: encode_typed_value(row.__dict__)))
    if len(set(answer)) != len(answer):
        raise NumericContextAuthorityRejected("numeric_context_disposition_duplicate")
    return answer


def unsupported_cells_digest(rows: tuple[CoverageDisposition, ...]) -> str:
    return sha256(
        b"memorii.acceptance.unsupported-cells.v2\0"
        + encode_typed_value(tuple(row.__dict__ for row in rows))
    ).hexdigest()


def verify_numeric_context(
    *, baseline_bytes: bytes, release_bytes: bytes, coverage_bytes: bytes,
    gate_bytes: bytes, sampling_frame_bytes: bytes, signing_keys: Mapping[str, bytes],
    expected_signing_key_id: str, expected_trust_policy_digest: str,
) -> VerifiedNumericContext:
    """Verify all signed manifests and project one complete certification context."""
    baseline, release, coverage, gates, frame = (
        _signed(raw, schema, signing_keys)
        for raw, schema in zip((baseline_bytes, release_bytes, coverage_bytes, gate_bytes, sampling_frame_bytes), _SCHEMAS, strict=True)
    )
    assert all(isinstance(item, dict) for item in (baseline, release, coverage, gates, frame))
    if any(
        item["signing_key_id"] != expected_signing_key_id
        or item["trust_policy_digest"] != expected_trust_policy_digest
        for item in (baseline, coverage, gates, frame)
    ) or release["acceptance_signing_key_reference"] != expected_signing_key_id:
        raise NumericContextAuthorityRejected("numeric_context_trust_policy")
    baseline_digest = sha256(baseline_bytes).hexdigest()
    if release["approved_baseline_artifact_digest"] != baseline_digest:
        raise NumericContextAuthorityRejected("numeric_context_baseline_release_join")
    shared = (
        "capability_fingerprint", "capability_contract_digest", "coverage_manifest_digest", "coverage_release_id",
        "statistical_gate_manifest_digest", "sampling_frame_manifest_digest", "sampling_frame_digest",
        "independent_cluster_definition_digest", "strata_definition_digest", "cluster_weighting_digest",
        "numeric_encoding_registry_digest", "unsupported_cells_digest",
    )
    if any(baseline[name] != release[name] for name in shared):
        raise NumericContextAuthorityRejected("numeric_context_release_coordinate")
    if (
        baseline["capability_fingerprint"], baseline["capability_contract_digest"], baseline["coverage_manifest_digest"], baseline["coverage_release_id"]
    ) != (coverage["capability_fingerprint"], coverage["capability_contract_digest"], coverage["manifest_digest"], coverage["release_id"]):
        raise NumericContextAuthorityRejected("numeric_context_coverage_join")
    if (baseline["statistical_gate_manifest_digest"], baseline["sampling_frame_manifest_digest"]) != (gates["manifest_digest"], frame["manifest_digest"]):
        raise NumericContextAuthorityRejected("numeric_context_manifest_join")
    for name in ("sampling_frame_digest", "independent_cluster_definition_digest", "strata_definition_digest", "cluster_weighting_digest", "numeric_encoding_registry_digest"):
        if baseline[name] != frame[name]:
            raise NumericContextAuthorityRejected("numeric_context_frame_join")
    rows = _dispositions(coverage)
    if unsupported_cells_digest(rows) != baseline["unsupported_cells_digest"]:
        raise NumericContextAuthorityRejected("numeric_context_unsupported_digest")
    expected = {(row.coverage_cell_id, row.metric_id) for row in rows}
    gate_rows = gates["metric_gates"]
    actual = {(item["coverage_cell_id"], item["metric_id"]) for item in gate_rows}
    if len(actual) != len(gate_rows) or actual != expected:
        raise NumericContextAuthorityRejected("numeric_context_gate_bijection")
    if (gates["capability_coverage_manifest_digest"], gates["capability_coverage_release_id"], gates["sampling_frame_manifest_digest"], gates["numeric_encoding_registry_digest"]) != (coverage["manifest_digest"], coverage["release_id"], frame["manifest_digest"], frame["numeric_encoding_registry_digest"]):
        raise NumericContextAuthorityRejected("numeric_context_gate_join")
    specs = tuple(EncodingSpec(**item) for item in frame["encoding_specs"])
    proofs = {(item["coverage_cell_id"], item["metric_id"]): item["iid_bernoulli_clusters_proven"] for item in frame["gate_iid_proofs"]}
    if set(proofs) != actual:
        raise NumericContextAuthorityRejected("numeric_context_iid_bijection")
    converted_gates = tuple(PreverifiedNumericGate(Gate(
        GateLocator(str(coverage["capability_fingerprint"]), item["coverage_cell_id"], item["metric_id"]),
        item["test_method"], item["bound"], item["estimand"], CanonicalDecimalQuantity(**item["threshold"]),
        CanonicalDecimalQuantity(**item["nominal_alpha"]), item["minimum_clusters"], item["threshold_spec_id"],
        item["nominal_alpha_spec_id"], item["lower_spec_id"], item["upper_spec_id"], item["weight_spec_id"],
        item["event_value_spec_id"], item["iid_declared"],
    ), bool(proofs[(item["coverage_cell_id"], item["metric_id"])])) for item in gate_rows)
    members = tuple(Membership(item["cluster_id"], GateLocator(str(coverage["capability_fingerprint"]), item["coverage_cell_id"], item["metric_id"]), tuple(item["provenance_ids"]), tuple(item["expected_event_ids"]), CanonicalDecimalQuantity(**item["weight"]), CanonicalDecimalQuantity(**item["lower"]), CanonicalDecimalQuantity(**item["upper"])) for item in frame["memberships"])
    authority = VerifiedNumericAuthority(baseline_digest, str(release["release_digest"]), *(str(baseline[name]) for name in shared[0:]))
    # The legacy arithmetic owner remains the certificate executor; it receives
    # the V2 coordinates through the complete preverified context on cutover.
    legacy_authority = NumericAuthority(
        approved_baseline_artifact_digest=authority.approved_baseline_artifact_digest,
        verified_baseline_approval_release_digest=authority.verified_baseline_approval_release_digest,
        capability_fingerprint=authority.capability_fingerprint,
        capability_contract_digest=authority.capability_contract_digest,
        coverage_manifest_digest=authority.coverage_manifest_digest,
        coverage_release_id=authority.coverage_release_id,
        statistical_gate_manifest_digest=authority.statistical_gate_manifest_digest,
        sampling_frame_manifest_digest=authority.sampling_frame_manifest_digest,
        sampling_frame_digest=authority.sampling_frame_digest,
        independent_cluster_definition_digest=authority.independent_cluster_definition_digest,
        strata_definition_digest=authority.strata_definition_digest,
        cluster_weighting_digest=authority.cluster_weighting_digest,
        numeric_encoding_registry_digest=authority.numeric_encoding_registry_digest,
        unsupported_cells_digest=authority.unsupported_cells_digest,
    )
    context = PreverifiedNumericCertificationContext(legacy_authority, specs, CanonicalDecimalQuantity(**frame["family_alpha"]), str(frame["family_alpha_spec_id"]), converted_gates, members)
    return VerifiedNumericContext(authority, rows, context)


@dataclass(frozen=True)
class FixedNumericManifestAuthority:
    """Fixed trust and manifests; the fenced candidate selects release bytes."""

    coverage_bytes: bytes
    gate_bytes: bytes
    sampling_frame_bytes: bytes
    signing_keys: Mapping[str, bytes]
    expected_signing_key_id: str
    expected_trust_policy_digest: str

    def __post_init__(self) -> None:
        coverage = _signed(
            self.coverage_bytes, "CapabilityCoverageManifest", self.signing_keys
        )
        gates = _signed(
            self.gate_bytes, "CapabilityStatisticalGateManifest", self.signing_keys
        )
        frame = _signed(
            self.sampling_frame_bytes,
            "CapabilitySamplingFrameManifest",
            self.signing_keys,
        )
        if any(
            value["signing_key_id"] != self.expected_signing_key_id
            or value["trust_policy_digest"] != self.expected_trust_policy_digest
            for value in (coverage, gates, frame)
        ):
            raise NumericContextAuthorityRejected("numeric_context_trust_policy")
        if (
            gates["capability_coverage_manifest_digest"] != coverage["manifest_digest"]
            or gates["capability_coverage_release_id"] != coverage["release_id"]
            or gates["sampling_frame_manifest_digest"] != frame["manifest_digest"]
            or frame["coverage_manifest_digest"] != coverage["manifest_digest"]
            or frame["coverage_release_id"] != coverage["release_id"]
        ):
            raise NumericContextAuthorityRejected("numeric_context_fixed_manifest_join")

    def resolve(
        self, *, baseline_bytes: bytes, release_bytes: bytes,
        policy_bytes: bytes, evidence_bytes: bytes,
    ) -> HeldBinding:
        verified = verify_numeric_context(
            baseline_bytes=baseline_bytes, release_bytes=release_bytes,
            coverage_bytes=self.coverage_bytes, gate_bytes=self.gate_bytes,
            sampling_frame_bytes=self.sampling_frame_bytes,
            signing_keys=self.signing_keys,
            expected_signing_key_id=self.expected_signing_key_id,
            expected_trust_policy_digest=self.expected_trust_policy_digest,
        )
        return HeldBinding(
            sha256(policy_bytes).hexdigest(), sha256(evidence_bytes).hexdigest(),
            verified.certification_context.authority, verified.certification_context,
        )
