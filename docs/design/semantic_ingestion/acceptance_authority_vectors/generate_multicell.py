"""Generate the frozen signed multi-cell V2 vector from the reviewed corpus."""

from __future__ import annotations

import base64
from hashlib import sha256
import json
from pathlib import Path

from acceptance.ctv import encode_typed_value
from acceptance.numeric_context_authority import CoverageDisposition, unsupported_cells_digest
from acceptance.schema_registry import canonical_digest, schema_for, signing_preimage, unsigned_artifact
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "docs/work/semantic_ingestion/statistical-unsupported-cell-binding/manifest-fixtures-v1.json"
OUTPUT = Path(__file__).with_name("multicell-v2.json")
KEY = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("1f" * 32))
COORDINATE = "fixture-key"
FINGERPRINT = "c" * 64


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _decode(source: dict[str, object], name: str) -> dict[str, object]:
    artifacts = source["artifacts"]
    assert isinstance(artifacts, dict)
    artifact = artifacts[name]
    assert isinstance(artifact, dict)
    encoded = artifact["canonical_bytes_base64"]
    assert isinstance(encoded, str)
    value = json.loads(base64.b64decode(encoded))
    assert isinstance(value, dict)
    return value


def _signed(schema_id: str, value: dict[str, object]) -> tuple[str, bytes]:
    schema = schema_for(schema_id)
    digest_field = schema["digest_field"]
    signer_field = schema["signer_coordinate_field"]
    value[digest_field] = "0" * 64
    value["signature"] = "0" * 128
    assert isinstance(signer_field, str)
    value[signer_field] = COORDINATE
    value[digest_field] = canonical_digest(
        schema["digest_domain"], "registered", unsigned_artifact(value, schema_id)
    )
    value["signature"] = KEY.sign(signing_preimage(schema_id, value, COORDINATE)).hex()
    return str(value[digest_field]), _json(value)


def _candidate_inputs(frame: dict[str, object], gates: dict[str, object]) -> tuple[bytes, bytes]:
    fingerprint = str(frame["capability_fingerprint"])
    gate_values = gates["metric_gates"]
    memberships = frame["memberships"]
    assert isinstance(gate_values, list) and isinstance(memberships, list)

    def locator(value: dict[str, object]) -> dict[str, str]:
        return {
            "capability_fingerprint": fingerprint,
            "cell_id": str(value["coverage_cell_id"]),
            "metric_id": str(value["metric_id"]),
        }

    policy_gates = []
    gate_by_locator = {}
    for value in gate_values:
        assert isinstance(value, dict)
        gate_by_locator[(value["coverage_cell_id"], value["metric_id"])] = value
        policy_gates.append({
            "locator": locator(value), "method": value["test_method"], "direction": value["bound"],
            "estimand": value["estimand"], "threshold": value["threshold"],
            "nominal_alpha": value["nominal_alpha"], "minimum_clusters": value["minimum_clusters"],
            **{name: value[name] for name in (
                "threshold_spec_id", "nominal_alpha_spec_id", "lower_spec_id", "upper_spec_id",
                "weight_spec_id", "event_value_spec_id", "iid_declared",
            )},
        })
    policy_memberships = []
    events = []
    for value in memberships:
        assert isinstance(value, dict)
        policy_memberships.append({
            "cluster_id": value["cluster_id"], "locator": locator(value),
            **{name: value[name] for name in (
                "provenance_ids", "expected_event_ids", "weight", "lower", "upper",
            )},
        })
        gate = gate_by_locator[(value["coverage_cell_id"], value["metric_id"])]
        provenance, event_ids = value["provenance_ids"], value["expected_event_ids"]
        assert isinstance(provenance, list) and provenance and isinstance(event_ids, list)
        for event_id in event_ids:
            events.append({
                "event_id": event_id, "provenance_id": provenance[0], "locator": locator(value),
                "value": value["upper"] if gate["bound"] == "lower" else value["lower"],
            })
    policy = {
        "schema": "statistical_acceptance_policy.v2", "arithmetic_bits": 1024,
        "arithmetic_operations": 40000, "precision": 8, "output_cap": 40000,
        "family_alpha": frame["family_alpha"], "family_alpha_spec_id": frame["family_alpha_spec_id"],
        "specs": frame["encoding_specs"], "gates": policy_gates, "memberships": policy_memberships,
    }
    return _json(policy), _json({"schema": "statistical_acceptance_evidence.v2", "events": events})


def main() -> None:
    source = json.loads(SOURCE.read_bytes())
    coverage = _decode(source, "capability_coverage_manifest")
    coverage["capability_fingerprint"] = FINGERPRINT
    coverage_digest, coverage_raw = _signed("CapabilityCoverageManifest", coverage)

    frame = _decode(source, "capability_sampling_frame_manifest")
    frame["capability_fingerprint"] = FINGERPRINT
    frame["coverage_manifest_digest"] = coverage_digest
    original_specs = frame["encoding_specs"]
    assert isinstance(original_specs, list)
    expanded_specs = []
    for spec in original_specs:
        assert isinstance(spec, dict)
        for suffix, unit in (("probability", "probability"), ("weight", "weight"), ("metric", "score")):
            expanded_specs.append({**spec, "encoding_spec_id": f"{spec['encoding_spec_id']}-{suffix}", "unit": unit})
    frame["encoding_specs"] = sorted(expanded_specs, key=encode_typed_value)
    family_alpha = frame["family_alpha"]
    assert isinstance(family_alpha, dict)
    family_alpha["encoding_spec_id"] = f"{family_alpha['encoding_spec_id']}-probability"
    family_alpha["fixed_scale_value"] = "1.00"
    frame["family_alpha_spec_id"] = f"{frame['family_alpha_spec_id']}-probability"
    memberships = frame["memberships"]
    assert isinstance(memberships, list)
    for membership in memberships:
        assert isinstance(membership, dict)
        for name, suffix in (("weight", "weight"), ("lower", "metric"), ("upper", "metric")):
            quantity = membership[name]
            assert isinstance(quantity, dict)
            quantity["encoding_spec_id"] = f"{quantity['encoding_spec_id']}-{suffix}"
        if membership["coverage_cell_id"] == "action":
            weight = membership["weight"]
            assert isinstance(weight, dict)
            weight["fixed_scale_value"] = "0.500"
    frame["memberships"] = sorted(memberships, key=encode_typed_value)
    frame_digest, frame_raw = _signed("CapabilitySamplingFrameManifest", frame)

    gates = _decode(source, "capability_statistical_gate_manifest")
    gates["capability_fingerprint"] = FINGERPRINT
    gates["capability_coverage_manifest_digest"] = coverage_digest
    gates["sampling_frame_manifest_digest"] = frame_digest
    metric_gates = gates["metric_gates"]
    assert isinstance(metric_gates, list)
    for gate in metric_gates:
        assert isinstance(gate, dict)
        for name in ("threshold", "cluster_value_lower_bound", "cluster_value_upper_bound"):
            quantity = gate[name]
            assert isinstance(quantity, dict)
            quantity["encoding_spec_id"] = f"{quantity['encoding_spec_id']}-metric"
        threshold = gate["threshold"]
        assert isinstance(threshold, dict)
        scale = 3 if str(threshold["fixed_scale_value"]).count("0") >= 3 else 2
        threshold["fixed_scale_value"] = ("0." if gate["bound"] == "lower" else "1.") + ("0" * scale)
        alpha = gate["nominal_alpha"]
        assert isinstance(alpha, dict)
        alpha["encoding_spec_id"] = f"{alpha['encoding_spec_id']}-probability"
        alpha_scale = 3 if str(alpha["fixed_scale_value"]).count("0") >= 3 else 2
        alpha["fixed_scale_value"] = "1." + ("0" * alpha_scale)
        for name, suffix in (
            ("threshold_spec_id", "metric"), ("nominal_alpha_spec_id", "probability"),
            ("lower_spec_id", "metric"), ("upper_spec_id", "metric"),
            ("weight_spec_id", "weight"), ("event_value_spec_id", "metric"),
        ):
            gate[name] = f"{gate[name]}-{suffix}"
    gates["metric_gates"] = sorted(metric_gates, key=encode_typed_value)
    gate_digest, gate_raw = _signed("CapabilityStatisticalGateManifest", gates)

    dispositions = []
    cells = coverage["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        assert isinstance(cell, dict)
        if cell["disposition"] == "enabled":
            metrics = cell["required_metric_ids"]
            assert isinstance(metrics, list)
            dispositions.extend(
                CoverageDisposition(FINGERPRINT, str(cell["coverage_cell_id"]), str(metric), "enabled")
                for metric in metrics
            )
        else:
            dispositions.append(CoverageDisposition(
                FINGERPRINT,
                str(cell["coverage_cell_id"]),
                str(cell["unsupported_abstention_metric_id"]),
                "explicitly_unsupported",
            ))
    baseline = _decode(source, "capability_baseline")
    baseline.update({
        "capability_fingerprint": FINGERPRINT,
        "coverage_manifest_digest": coverage_digest,
        "statistical_gate_manifest_digest": gate_digest,
        "sampling_frame_manifest_digest": frame_digest,
        "unsupported_cells_digest": unsupported_cells_digest(tuple(sorted(dispositions))),
    })
    _, baseline_raw = _signed("ApprovedCapabilityBaseline", baseline)

    release = _decode(source, "capability_release")
    release["approved_baseline_artifact_digest"] = sha256(baseline_raw).hexdigest()
    for name in (
        "capability_fingerprint", "capability_contract_digest", "coverage_manifest_digest",
        "coverage_release_id", "statistical_gate_manifest_digest", "sampling_frame_manifest_digest",
        "sampling_frame_digest", "independent_cluster_definition_digest", "strata_definition_digest",
        "cluster_weighting_digest", "numeric_encoding_registry_digest", "unsupported_cells_digest",
    ):
        release[name] = baseline[name]
    release_digest, release_raw = _signed("CapabilityBaselineApprovalRelease", release)
    successor = dict(release)
    successor.update({
        "acceptance_release_sequence": 2,
        "supersedes_release_digest": release_digest,
        "issued_at": "2026-01-02T00:00:00Z",
    })
    _, successor_raw = _signed("CapabilityBaselineApprovalRelease", successor)

    raws = {
        "capability_baseline": baseline_raw,
        "capability_release": release_raw,
        "capability_release_successor": successor_raw,
        "capability_coverage_manifest": coverage_raw,
        "capability_statistical_gate_manifest": gate_raw,
        "capability_sampling_frame_manifest": frame_raw,
    }
    policy, evidence = _candidate_inputs(frame, gates)
    result = {
        "format": "memorii.acceptance.installed-multicell-vector.v2",
        "public_key_base64": base64.b64encode(KEY.public_key().public_bytes_raw()).decode("ascii"),
        "policy_base64": base64.b64encode(policy).decode("ascii"),
        "evidence_base64": base64.b64encode(evidence).decode("ascii"),
        "artifacts": {
            name: {
                "canonical_bytes_base64": base64.b64encode(raw).decode("ascii"),
                "sha256": sha256(raw).hexdigest(),
            }
            for name, raw in raws.items()
        },
    }
    OUTPUT.write_bytes(_json(result) + b"\n")


if __name__ == "__main__":
    main()
