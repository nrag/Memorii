"""Exercise the installed numeric evaluator against the frozen signed V2 corpus."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from acceptance.numeric_context_authority import FixedNumericManifestAuthority
from acceptance.statistical_certification import (
    TransportLimits,
    evaluate_certificate,
    verify_certificate,
)


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _policy_and_evidence(frame: dict[str, object], gates: dict[str, object]) -> tuple[bytes, bytes]:
    fingerprint = frame["capability_fingerprint"]
    gate_values = gates["metric_gates"]
    memberships = frame["memberships"]
    assert isinstance(fingerprint, str) and isinstance(gate_values, list) and isinstance(memberships, list)

    def locator(value: dict[str, object]) -> dict[str, str]:
        return {
            "capability_fingerprint": fingerprint,
            "cell_id": str(value["coverage_cell_id"]),
            "metric_id": str(value["metric_id"]),
        }

    policy_gates = []
    for value in gate_values:
        assert isinstance(value, dict)
        policy_gates.append({
            "locator": locator(value),
            "method": value["test_method"],
            "direction": value["bound"],
            "estimand": value["estimand"],
            "threshold": value["threshold"],
            "nominal_alpha": value["nominal_alpha"],
            "minimum_clusters": value["minimum_clusters"],
            "threshold_spec_id": value["threshold_spec_id"],
            "nominal_alpha_spec_id": value["nominal_alpha_spec_id"],
            "lower_spec_id": value["lower_spec_id"],
            "upper_spec_id": value["upper_spec_id"],
            "weight_spec_id": value["weight_spec_id"],
            "event_value_spec_id": value["event_value_spec_id"],
            "iid_declared": value["iid_declared"],
        })
    policy_memberships = []
    events = []
    gate_by_locator = {
        (value["coverage_cell_id"], value["metric_id"]): value
        for value in gate_values if isinstance(value, dict)
    }
    for value in memberships:
        assert isinstance(value, dict)
        policy_memberships.append({
            "cluster_id": value["cluster_id"],
            "locator": locator(value),
            "provenance_ids": value["provenance_ids"],
            "expected_event_ids": value["expected_event_ids"],
            "weight": value["weight"],
            "lower": value["lower"],
            "upper": value["upper"],
        })
        gate = gate_by_locator[(value["coverage_cell_id"], value["metric_id"])]
        assert isinstance(gate, dict)
        event_value = value["upper"] if gate["bound"] == "lower" else value["lower"]
        provenance = value["provenance_ids"]
        expected = value["expected_event_ids"]
        assert isinstance(provenance, list) and provenance and isinstance(expected, list)
        for event_id in expected:
            events.append({
                "event_id": event_id,
                "provenance_id": provenance[0],
                "locator": locator(value),
                "value": event_value,
            })
    policy = {
        "schema": "statistical_acceptance_policy.v2",
        "arithmetic_bits": 1024,
        "arithmetic_operations": 40000,
        "precision": 8,
        "output_cap": 40000,
        "family_alpha": frame["family_alpha"],
        "family_alpha_spec_id": frame["family_alpha_spec_id"],
        "specs": frame["encoding_specs"],
        "gates": policy_gates,
        "memberships": policy_memberships,
    }
    evidence = {"schema": "statistical_acceptance_evidence.v2", "events": events}
    return _json(policy), _json(evidence)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parsed = parser.parse_args()
    import acceptance

    assert Path(acceptance.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    value = json.loads(parsed.fixture.read_bytes())
    artifacts = value["artifacts"]

    def raw(name: str) -> bytes:
        return base64.b64decode(artifacts[name]["canonical_bytes_base64"])

    baseline = raw("capability_baseline")
    release = raw("capability_release")
    successor_release = raw("capability_release_successor")
    coverage = raw("capability_coverage_manifest")
    coverage_value = json.loads(coverage)
    gate_bytes = raw("capability_statistical_gate_manifest")
    frame_bytes = raw("capability_sampling_frame_manifest")
    frame = json.loads(frame_bytes)
    gates = json.loads(gate_bytes)
    policy = base64.b64decode(value["policy_base64"])
    evidence = base64.b64decode(value["evidence_base64"])
    assert (policy, evidence) == _policy_and_evidence(frame, gates)
    policy_value = json.loads(policy)
    coverage_cells = {
        cell["coverage_cell_id"] for cell in coverage_value["cells"]
    }
    gate_cells = {
        gate["coverage_cell_id"] for gate in gates["metric_gates"]
    }
    frame_cells = {
        membership["coverage_cell_id"] for membership in frame["memberships"]
    }
    policy_cells = {
        gate["locator"]["cell_id"] for gate in policy_value["gates"]
    }
    if (
        len(coverage_cells) != 4
        or gate_cells != coverage_cells
        or frame_cells != coverage_cells
        or policy_cells != coverage_cells
        or "explicitly_unsupported"
        not in {cell["disposition"] for cell in coverage_value["cells"]}
        or {gate["test_method"] for gate in gates["metric_gates"]}
        != {"exact_binomial", "weighted_hoeffding"}
        or len(
            {
                membership["weight"]["fixed_scale_value"]
                for membership in frame["memberships"]
            }
        )
        < 2
    ):
        raise AssertionError("frozen_numeric_vector_topology")
    authority = FixedNumericManifestAuthority(
        coverage_bytes=coverage,
        gate_bytes=gate_bytes,
        sampling_frame_bytes=frame_bytes,
        signing_keys={"fixture-key": base64.b64decode(value["public_key_base64"])},
        expected_signing_key_id="fixture-key",
        expected_trust_policy_digest="a" * 64,
    )
    binding = authority.resolve(
        baseline_bytes=baseline,
        release_bytes=release,
        policy_bytes=policy,
        evidence_bytes=evidence,
    )
    successor_binding = authority.resolve(
        baseline_bytes=baseline,
        release_bytes=successor_release,
        policy_bytes=policy,
        evidence_bytes=evidence,
    )
    if (
        successor_binding.context is binding.context
        or successor_binding.expected_authority.verified_baseline_approval_release_digest
        == binding.expected_authority.verified_baseline_approval_release_digest
    ):
        raise AssertionError("frozen_numeric_successor_selection")
    limits = TransportLimits(200000, 200000, 200000, 4096, 200000, 20, 200000, 32, 128, 20000, 2000)
    certificate = evaluate_certificate(BytesIO(policy), BytesIO(evidence), binding, limits)
    verified = verify_certificate(BytesIO(certificate), BytesIO(policy), BytesIO(evidence), binding, limits)
    if not verified.accepted or len(verified.results) != 5:
        raise AssertionError(
            "frozen_numeric_vector_result:"
            + repr([(result.locator.cell_id, result.outcome) for result in verified.results])
        )
    print(json.dumps({
        "certificate_sha256": sha256(certificate).hexdigest(),
        "gate_count": len(verified.results),
        "membership_count": len(binding.context.expected_clusters),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
