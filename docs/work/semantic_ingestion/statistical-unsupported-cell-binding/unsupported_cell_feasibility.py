"""Independent signed numeric-context authority feasibility proof.

It reimplements acceptance CTV-v1 locally and uses cryptography only for the
Ed25519 primitive; it imports no acceptance code.
"""

from __future__ import annotations

import base64
import copy
import json
import re
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

KEY = bytes.fromhex("1f" * 32)
PUBLIC_KEY_B64 = "QwRr/kCSs+lJlOraFdzCDYqqB7ZY/TlU644O+4vcpd4="
PROFILE = {
    "id": "memorii.acceptance.canonical-map.v1",
    "decimal_encoding_policy_id": "memorii.decimal.fixed-scale.v1",
    "parser_ceilings": {
        "maximum_bytes": 131072,
        "maximum_depth": 32,
        "maximum_nodes": 4096,
        "maximum_string_bytes": 16384,
        "maximum_integer_digits": 128,
    },
}
EXPECTED_PROJECTION_HEX = (
    "retired; canonical bytes are frozen in EXPECTED_PROJECTION_B64"
)
EXPECTED_PROJECTION_DIGEST = (
    "1ef7d14c49e98eed2a9de0c93cf99d895d0c97d2f33316431232478e9c445e6f"
)
EXPECTED_PROJECTION_B64 = "eyIkdHlwZSI6InR1cGxlIiwiaXRlbXMiOlt7IiR0eXBlIjoibWFwIiwiZW50cmllcyI6W1siY2FwYWJpbGl0eV9maW5nZXJwcmludCIsImNhcCJdLFsiY292ZXJhZ2VfY2VsbF9pZCIsImFjdGlvbiJdLFsiZGlzcG9zaXRpb24iLCJleHBsaWNpdGx5X3Vuc3VwcG9ydGVkIl0sWyJtZXRyaWNfaWQiLCJhYnN0YWluLmFjdGlvbiJdXX0seyIkdHlwZSI6Im1hcCIsImVudHJpZXMiOltbImNhcGFiaWxpdHlfZmluZ2VycHJpbnQiLCJjYXAiXSxbImNvdmVyYWdlX2NlbGxfaWQiLCJpZGVudGl0eSJdLFsiZGlzcG9zaXRpb24iLCJleHBsaWNpdGx5X3Vuc3VwcG9ydGVkIl0sWyJtZXRyaWNfaWQiLCJhYnN0YWluLmlkZW50aXR5Il1dfSx7IiR0eXBlIjoibWFwIiwiZW50cmllcyI6W1siY2FwYWJpbGl0eV9maW5nZXJwcmludCIsImNhcCJdLFsiY292ZXJhZ2VfY2VsbF9pZCIsImxhbmd1YWdlIl0sWyJkaXNwb3NpdGlvbiIsImVuYWJsZWQiXSxbIm1ldHJpY19pZCIsInByZWNpc2lvbiJdXX0seyIkdHlwZSI6Im1hcCIsImVudHJpZXMiOltbImNhcGFiaWxpdHlfZmluZ2VycHJpbnQiLCJjYXAiXSxbImNvdmVyYWdlX2NlbGxfaWQiLCJsYW5ndWFnZSJdLFsiZGlzcG9zaXRpb24iLCJlbmFibGVkIl0sWyJtZXRyaWNfaWQiLCJyZWNhbGwiXV19LHsiJHR5cGUiOiJtYXAiLCJlbnRyaWVzIjpbWyJjYXBhYmlsaXR5X2ZpbmdlcnByaW50IiwiY2FwIl0sWyJjb3ZlcmFnZV9jZWxsX2lkIiwidGVtcG9yYWwiXSxbImRpc3Bvc2l0aW9uIiwiZW5hYmxlZCJdLFsibWV0cmljX2lkIiwiYXR0YWNobWVudCJdXX1dfQ=="
AUTHORITY_FIELDS = (
    "approved_baseline_artifact_digest",
    "verified_baseline_approval_release_digest",
    "capability_fingerprint",
    "capability_contract_digest",
    "coverage_manifest_digest",
    "coverage_release_id",
    "statistical_gate_manifest_digest",
    "sampling_frame_manifest_digest",
    "sampling_frame_digest",
    "independent_cluster_definition_digest",
    "strata_definition_digest",
    "cluster_weighting_digest",
    "numeric_encoding_registry_digest",
    "unsupported_cells_digest",
)
MANIFEST_FIELDS = {
    "capability_baseline": frozenset(
        "capability_contract_digest capability_fingerprint cluster_weighting_digest coverage_manifest_digest coverage_release_id independent_cluster_definition_digest manifest_digest numeric_encoding_registry_digest purpose sampling_frame_digest sampling_frame_manifest_digest schema_version signature signing_key_id statistical_gate_manifest_digest strata_definition_digest trust_policy_digest unsupported_cells_digest".split()
    ),
    "capability_release": frozenset(
        "acceptance_authority_snapshot_digest acceptance_release_epoch acceptance_release_sequence acceptance_signing_key_reference approved_baseline_artifact_digest approver_subject_id capability_contract_digest capability_fingerprint cluster_weighting_digest compromise_effective_at coverage_manifest_digest coverage_release_id expires_at independent_cluster_definition_digest issued_at lifecycle_state numeric_encoding_registry_digest purpose release_digest revoked_at sampling_frame_digest sampling_frame_manifest_digest schema_version signature statistical_gate_manifest_digest strata_definition_digest supersedes_release_digest unsupported_cells_digest".split()
    ),
    "capability_coverage_manifest": frozenset(
        "capability_contract_digest capability_fingerprint cells manifest_digest purpose release_id schema_version signature signing_key_id trust_policy_digest".split()
    ),
    "capability_statistical_gate_manifest": frozenset(
        "capability_coverage_manifest_digest capability_coverage_release_id capability_fingerprint manifest_digest metric_gates numeric_encoding_registry_digest purpose sampling_frame_manifest_digest schema_version signature signing_key_id trust_policy_digest".split()
    ),
    "capability_sampling_frame_manifest": frozenset(
        "capability_contract_digest capability_fingerprint cluster_weighting_digest coverage_manifest_digest coverage_release_id encoding_specs family_alpha family_alpha_spec_id gate_iid_proofs independent_cluster_definition_digest manifest_digest memberships numeric_encoding_registry_digest purpose sampling_frame_digest schema_version signature signing_key_id strata_definition_digest trust_policy_digest".split()
    ),
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_QUANTITY = re.compile(r"^(?:0|1)\.[0-9]+$")


def ctv(value: object) -> bytes:
    """Exact acceptance CTV-v1 grammar, independently implemented."""
    if value is None:
        return b"null"
    if type(value) is bool:
        return b"true" if value else b"false"
    if type(value) is int:
        return b'{"$type":"integer","value":"' + str(value).encode("ascii") + b'"}'
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    if type(value) is bytes:
        return (
            b'{"$type":"bytes","base64":'
            + ctv(base64.b64encode(value).decode("ascii"))
            + b"}"
        )
    if type(value) is tuple:
        return b'{"$type":"tuple","items":[' + b",".join(ctv(x) for x in value) + b"]}"
    if type(value) is list:
        return b'{"$type":"list","items":[' + b",".join(ctv(x) for x in value) + b"]}"
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("map_key")
        return (
            b'{"$type":"map","entries":['
            + b",".join(
                b"[" + ctv(key) + b"," + ctv(item) + b"]"
                for key, item in sorted(value.items())
            )
            + b"]}"
        )
    raise TypeError(type(value).__name__)


def lp(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def digest(domain: str, body: dict[str, object]) -> str:
    return sha256(lp(domain.encode()) + lp(ctv(PROFILE)) + lp(ctv(body))).hexdigest()


def preimage(
    domain: str, purpose: str, signer: str, body_digest: str, body: dict[str, object]
) -> bytes:
    return lp(domain.encode()) + lp(
        ctv(
            {
                "purpose": purpose,
                "profile_binding": PROFILE,
                "signer_coordinate": signer,
                "body_digest": body_digest,
                "unsigned_content": body,
            }
        )
    )


def signed(kind: str, body: dict[str, object]) -> bytes:
    if kind == "capability_release":
        domain = "memorii.acceptance.capability-baseline-approval.v2"
        signature_domain = "memorii.acceptance.capability-baseline-approval.signature.v2"
        purpose = "semantic_ingestion_capability_baseline_approval.v2"
        signer_field, digest_field = "acceptance_signing_key_reference", "release_digest"
        value = dict(body, schema_version=2, purpose=purpose, **{signer_field: "fixture-key"})
    else:
        domain, signature_domain = (
            f"memorii.acceptance.{kind}.v2",
            f"memorii.acceptance.{kind}.signature.v2",
        )
        purpose = kind
        signer_field, digest_field = "signing_key_id", "manifest_digest"
        value = dict(body, schema_version=2, purpose=purpose, signing_key_id="fixture-key", trust_policy_digest="a" * 64)
    value[digest_field] = digest(domain, value)
    value["signature"] = (
        Ed25519PrivateKey.from_private_bytes(KEY)
        .sign(
            preimage(
                signature_domain,
                purpose,
                "fixture-key",
                value[digest_field],
                {
                    k: v
                    for k, v in value.items()
                    if k not in {digest_field, "signature"}
                },
            )
        )
        .hex()
    )
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def verify(raw: bytes, kind: str) -> dict[str, object]:
    value = json.loads(raw)
    is_release = kind == "capability_release"
    purpose = "semantic_ingestion_capability_baseline_approval.v2" if is_release else kind
    signer_field = "acceptance_signing_key_reference" if is_release else "signing_key_id"
    digest_field = "release_digest" if is_release else "manifest_digest"
    if (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        != raw
    ):
        raise ValueError("canonical_bytes")
    if (
        type(value) is not dict
        or set(value) != MANIFEST_FIELDS[kind]
        or value.get("schema_version") != 2
        or value.get("purpose") != purpose
        or value.get(signer_field) != "fixture-key"
        or (not is_release and value.get("trust_policy_digest") != "a" * 64)
        or any(
            type(value[name]) is not str
            for name in ("capability_fingerprint", digest_field, "signature")
        )
    ):
        raise ValueError("manifest_fields")
    arrays = {
        "capability_baseline": (),
        "capability_release": (),
        "capability_coverage_manifest": ("cells",),
        "capability_statistical_gate_manifest": ("metric_gates",),
        "capability_sampling_frame_manifest": (
            "encoding_specs",
            "gate_iid_proofs",
            "memberships",
        ),
    }[kind]
    if any(type(value[name]) is not list for name in arrays):
        raise ValueError("manifest_types")
    unsigned = {
        k: v for k, v in value.items() if k not in {digest_field, "signature"}
    }
    domain = "memorii.acceptance.capability-baseline-approval.v2" if is_release else f"memorii.acceptance.{kind}.v2"
    signature_domain = "memorii.acceptance.capability-baseline-approval.signature.v2" if is_release else f"memorii.acceptance.{kind}.signature.v2"
    if value.get(digest_field) != digest(domain, dict(unsigned)):
        raise ValueError("manifest_digest")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64)).verify(
            bytes.fromhex(value["signature"]),
            preimage(
                signature_domain,
                purpose,
                "fixture-key",
                value[digest_field],
                unsigned,
            ),
        )
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise ValueError("manifest_signature") from exc
    _validate_nested(kind, value)
    return value


def _closed_map(value: object, fields: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(label)
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(label)
    return value


def _digest_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(label)
    return value


def _quantity(value: object, label: str) -> dict[str, object]:
    answer = _closed_map(value, {"encoding_spec_id", "fixed_scale_value"}, label)
    _identifier(answer["encoding_spec_id"], label)
    if not isinstance(answer["fixed_scale_value"], str) or not _QUANTITY.fullmatch(
        answer["fixed_scale_value"]
    ):
        raise ValueError(label)
    return answer


def _canonical_array(value: object, label: str, identity: callable) -> list[object]:
    if type(value) is not list or not value or value != sorted(value, key=ctv):
        raise ValueError(label)
    keys = [identity(item) for item in value]
    if len(keys) != len(set(keys)):
        raise ValueError(label)
    return value


def _locator(value: dict[str, object], label: str) -> tuple[str, str]:
    return _identifier(value["coverage_cell_id"], label), _identifier(
        value["metric_id"], label
    )


def _validate_nested(kind: str, value: dict[str, object]) -> None:
    for name in (("release_digest",) if kind == "capability_release" else ("manifest_digest", "trust_policy_digest")):
        _digest_value(value[name], f"{kind}_{name}")
    _identifier(value["capability_fingerprint"], f"{kind}_capability")
    if kind in {
        "capability_baseline",
        "capability_release",
        "capability_sampling_frame_manifest",
    }:
        for name in (
            "capability_contract_digest",
            "coverage_manifest_digest",
            "numeric_encoding_registry_digest",
            "sampling_frame_digest",
            "independent_cluster_definition_digest",
            "strata_definition_digest",
            "cluster_weighting_digest",
        ):
            _digest_value(value[name], f"{kind}_{name}")
        _identifier(value["coverage_release_id"], f"{kind}_release")
    if kind == "capability_release":
        _digest_value(value["approved_baseline_artifact_digest"], "release_baseline")
    if kind == "capability_coverage_manifest":
        cells = _canonical_array(
            value["cells"],
            "coverage_cells",
            lambda item: _identifier(item["coverage_cell_id"], "coverage_cell"),
        )
        for cell in cells:
            row = _closed_map(
                cell,
                {
                    "behavior_lane",
                    "cell_digest",
                    "construction",
                    "coverage_cell_id",
                    "disposition",
                    "language",
                    "predicate_family",
                    "required_metric_ids",
                    "unsupported_abstention_metric_id",
                },
                "coverage_cell",
            )
            for name in (
                "behavior_lane",
                "construction",
                "coverage_cell_id",
                "language",
                "predicate_family",
            ):
                _identifier(row[name], "coverage_cell")
            _digest_value(row["cell_digest"], "coverage_cell")
            metrics = (
                _canonical_array(
                    row["required_metric_ids"],
                    "coverage_metrics",
                    lambda item: _identifier(item, "coverage_metric"),
                )
                if row["required_metric_ids"]
                else []
            )
            if row["disposition"] == "enabled":
                if not metrics or row["unsupported_abstention_metric_id"] is not None:
                    raise ValueError("coverage_enabled")
            elif row["disposition"] == "explicitly_unsupported":
                if metrics or not isinstance(
                    row["unsupported_abstention_metric_id"], str
                ):
                    raise ValueError("coverage_unsupported")
                _identifier(
                    row["unsupported_abstention_metric_id"], "coverage_unsupported"
                )
            else:
                raise ValueError("coverage_disposition")
    if kind == "capability_statistical_gate_manifest":
        for name in (
            "capability_coverage_manifest_digest",
            "sampling_frame_manifest_digest",
            "numeric_encoding_registry_digest",
        ):
            _digest_value(value[name], "gate_chain")
        _identifier(value["capability_coverage_release_id"], "gate_release")
        gates = _canonical_array(
            value["metric_gates"], "metric_gates", lambda item: _locator(item, "gate")
        )
        fields = {
            "bound",
            "cluster_value_lower_bound",
            "cluster_value_upper_bound",
            "coverage_cell_id",
            "estimand",
            "event_value_spec_id",
            "iid_declared",
            "lower_spec_id",
            "metric_id",
            "minimum_clusters",
            "nominal_alpha",
            "nominal_alpha_spec_id",
            "test_method",
            "threshold",
            "threshold_spec_id",
            "upper_spec_id",
            "weight_spec_id",
        }
        for gate in gates:
            row = _closed_map(gate, fields, "metric_gate")
            _locator(row, "metric_gate")
            if (
                row["bound"] not in {"upper", "lower"}
                or row["estimand"] not in {"cluster_any_failure", "cluster_macro_mean"}
                or row["test_method"] not in {"exact_binomial", "weighted_hoeffding"}
                or type(row["iid_declared"]) is not bool
                or type(row["minimum_clusters"]) is not int
                or row["minimum_clusters"] < 1
            ):
                raise ValueError("metric_gate")
            for name in (
                "event_value_spec_id",
                "lower_spec_id",
                "nominal_alpha_spec_id",
                "threshold_spec_id",
                "upper_spec_id",
                "weight_spec_id",
            ):
                _identifier(row[name], "metric_gate")
            for name in (
                "cluster_value_lower_bound",
                "cluster_value_upper_bound",
                "nominal_alpha",
                "threshold",
            ):
                _quantity(row[name], "metric_gate")
    if kind == "capability_sampling_frame_manifest":
        specs = _canonical_array(
            value["encoding_specs"],
            "encoding_specs",
            lambda item: _identifier(item["encoding_spec_id"], "encoding_spec"),
        )
        for spec in specs:
            row = _closed_map(
                spec,
                {
                    "encoding_spec_id",
                    "lower",
                    "lower_inclusive",
                    "reject_inexact",
                    "scale",
                    "unit",
                    "upper",
                    "upper_inclusive",
                },
                "encoding_spec",
            )
            _identifier(row["encoding_spec_id"], "encoding_spec")
            if (
                not isinstance(row["unit"], str)
                or type(row["scale"]) is not int
                or row["scale"] < 0
                or type(row["lower_inclusive"]) is not bool
                or type(row["upper_inclusive"]) is not bool
                or row["reject_inexact"] is not True
                or not isinstance(row["lower"], str)
                or not isinstance(row["upper"], str)
            ):
                raise ValueError("encoding_spec")
        _quantity(value["family_alpha"], "family_alpha")
        _identifier(value["family_alpha_spec_id"], "family_alpha")
        proofs = _canonical_array(
            value["gate_iid_proofs"],
            "iid_proofs",
            lambda item: _locator(item, "iid_proof"),
        )
        for proof in proofs:
            row = _closed_map(
                proof,
                {
                    "coverage_cell_id",
                    "metric_id",
                    "iid_bernoulli_clusters_proven",
                    "proof_digest",
                },
                "iid_proof",
            )
            _locator(row, "iid_proof")
            if type(row["iid_bernoulli_clusters_proven"]) is not bool:
                raise ValueError("iid_proof")
            _digest_value(row["proof_digest"], "iid_proof")
        memberships = _canonical_array(
            value["memberships"],
            "memberships",
            lambda item: (
                *_locator(item, "membership"),
                _identifier(item["cluster_id"], "membership"),
            ),
        )
        for member in memberships:
            row = _closed_map(
                member,
                {
                    "coverage_cell_id",
                    "metric_id",
                    "cluster_id",
                    "provenance_ids",
                    "expected_event_ids",
                    "weight",
                    "lower",
                    "upper",
                },
                "membership",
            )
            _locator(row, "membership")
            _identifier(row["cluster_id"], "membership")
            for name in ("provenance_ids", "expected_event_ids"):
                _canonical_array(
                    row[name],
                    "membership_ids",
                    lambda item: _identifier(item, "membership_id"),
                )
            for name in ("weight", "lower", "upper"):
                _quantity(row[name], "membership")


def projection(coverage: dict[str, object]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for cell in coverage["cells"]:
        if cell["disposition"] == "enabled":
            if (
                not cell["required_metric_ids"]
                or cell["unsupported_abstention_metric_id"] is not None
            ):
                raise ValueError("enabled_cell")
            for metric in cell["required_metric_ids"]:
                rows.append(
                    {
                        "capability_fingerprint": coverage["capability_fingerprint"],
                        "coverage_cell_id": cell["coverage_cell_id"],
                        "metric_id": metric,
                        "disposition": "enabled",
                    }
                )
        elif cell["disposition"] == "explicitly_unsupported":
            if (
                cell["required_metric_ids"]
                or not cell["unsupported_abstention_metric_id"]
            ):
                raise ValueError("unsupported_cell")
            rows.append(
                {
                    "capability_fingerprint": coverage["capability_fingerprint"],
                    "coverage_cell_id": cell["coverage_cell_id"],
                    "metric_id": cell["unsupported_abstention_metric_id"],
                    "disposition": "explicitly_unsupported",
                }
            )
        else:
            raise ValueError("disposition")
    if len({ctv(row) for row in rows}) != len(rows):
        raise ValueError("duplicate_disposition")
    return tuple(sorted(rows, key=ctv))


def unsupported_digest(rows: tuple[dict[str, str], ...]) -> str:
    return sha256(b"memorii.acceptance.unsupported-cells.v2\0" + ctv(rows)).hexdigest()


def signed_artifact_digest(raw: bytes) -> str:
    """The complete canonical signed artifact hash has no self-reference."""
    return sha256(raw).hexdigest()


def metadata_fields(kind: str) -> set[str]:
    if kind == "capability_release":
        return {"schema_version", "purpose", "acceptance_signing_key_reference", "release_digest", "signature"}
    return {"schema_version", "purpose", "signing_key_id", "trust_policy_digest", "manifest_digest", "signature"}


def reissue_chain(
    bodies: dict[str, dict[str, object]],
    *,
    retain_unsupported: bool = False,
) -> tuple[tuple[bytes, bytes, bytes, bytes, bytes], dict[str, str]]:
    """Re-sign a coherent manifest chain for value-level negative vectors."""
    coverage_raw = signed(
        "capability_coverage_manifest", bodies["capability_coverage_manifest"]
    )
    coverage = json.loads(coverage_raw)
    frame_body = bodies["capability_sampling_frame_manifest"]
    frame_body.update(
        coverage_manifest_digest=coverage["manifest_digest"],
        coverage_release_id=coverage["release_id"],
    )
    frame_raw = signed("capability_sampling_frame_manifest", frame_body)
    frame = json.loads(frame_raw)
    gate_body = bodies["capability_statistical_gate_manifest"]
    gate_body.update(
        capability_coverage_manifest_digest=coverage["manifest_digest"],
        capability_coverage_release_id=coverage["release_id"],
        sampling_frame_manifest_digest=frame["manifest_digest"],
        numeric_encoding_registry_digest=frame["numeric_encoding_registry_digest"],
    )
    gate_raw = signed("capability_statistical_gate_manifest", gate_body)
    gate = json.loads(gate_raw)
    baseline_body = bodies["capability_baseline"]
    baseline_body.update(
        coverage_manifest_digest=coverage["manifest_digest"],
        coverage_release_id=coverage["release_id"],
        statistical_gate_manifest_digest=gate["manifest_digest"],
        sampling_frame_manifest_digest=frame["manifest_digest"],
    )
    if not retain_unsupported:
        baseline_body["unsupported_cells_digest"] = unsupported_digest(
            projection(coverage)
        )
    baseline_raw = signed("capability_baseline", baseline_body)
    baseline = json.loads(baseline_raw)
    release_body = bodies["capability_release"]
    release_body.update(
        {
            name: baseline[name]
            for name in (
                "capability_contract_digest",
                "capability_fingerprint",
                "cluster_weighting_digest",
                "coverage_manifest_digest",
                "coverage_release_id",
                "independent_cluster_definition_digest",
                "numeric_encoding_registry_digest",
                "sampling_frame_digest",
                "sampling_frame_manifest_digest",
                "statistical_gate_manifest_digest",
                "strata_definition_digest",
                "unsupported_cells_digest",
            )
        }
    )
    release_body["approved_baseline_artifact_digest"] = signed_artifact_digest(
        baseline_raw
    )
    release_raw = signed("capability_release", release_body)
    parsed = tuple(
        verify(raw, name)
        for raw, name in zip(
            (baseline_raw, release_raw, coverage_raw, gate_raw, frame_raw),
            (
                "capability_baseline",
                "capability_release",
                "capability_coverage_manifest",
                "capability_statistical_gate_manifest",
                "capability_sampling_frame_manifest",
            ),
            strict=True,
        )
    )
    return (
        baseline_raw,
        release_raw,
        coverage_raw,
        gate_raw,
        frame_raw,
    ), derived_authority(baseline_raw, release_raw, *parsed, projection(parsed[2]))


def _within_spec(
    quantity: dict[str, object], specs: dict[str, dict[str, object]], label: str
) -> None:
    spec = specs.get(quantity["encoding_spec_id"])
    if spec is None:
        raise ValueError(label)
    value = quantity["fixed_scale_value"]
    if not isinstance(value, str) or len(value.split(".")[-1]) != spec["scale"]:
        raise ValueError(label)
    numeric, lower, upper = (
        Fraction(value),
        Fraction(spec["lower"]),
        Fraction(spec["upper"]),
    )
    if numeric < lower or numeric > upper:
        raise ValueError(label)


def derived_authority(
    baseline_raw: bytes,
    release_raw: bytes,
    baseline: dict[str, object],
    release: dict[str, object],
    coverage: dict[str, object],
    gates: dict[str, object],
    frame: dict[str, object],
    rows: tuple[dict[str, str], ...],
) -> dict[str, str]:
    return {
        "approved_baseline_artifact_digest": signed_artifact_digest(baseline_raw),
        "verified_baseline_approval_release_digest": release["release_digest"],
        "capability_fingerprint": coverage["capability_fingerprint"],
        "capability_contract_digest": coverage["capability_contract_digest"],
        "coverage_manifest_digest": coverage["manifest_digest"],
        "coverage_release_id": coverage["release_id"],
        "statistical_gate_manifest_digest": gates["manifest_digest"],
        "sampling_frame_manifest_digest": frame["manifest_digest"],
        "sampling_frame_digest": frame["sampling_frame_digest"],
        "independent_cluster_definition_digest": frame[
            "independent_cluster_definition_digest"
        ],
        "strata_definition_digest": frame["strata_definition_digest"],
        "cluster_weighting_digest": frame["cluster_weighting_digest"],
        "numeric_encoding_registry_digest": frame["numeric_encoding_registry_digest"],
        "unsupported_cells_digest": unsupported_digest(rows),
    }


def validate(
    baseline_raw: bytes,
    release_raw: bytes,
    coverage_raw: bytes,
    gates_raw: bytes,
    frame_raw: bytes,
    authority: dict[str, str],
    marker: str = "statistical_acceptance_certificate.v2",
    candidate: dict[str, object] | None = None,
    parser_sentinel: list[bool] | None = None,
) -> tuple[dict[str, str], ...]:
    if marker != "statistical_acceptance_certificate.v2":
        raise ValueError("v1_rejected")
    baseline, release, coverage, gates, frame = (
        verify(baseline_raw, "capability_baseline"),
        verify(release_raw, "capability_release"),
        verify(coverage_raw, "capability_coverage_manifest"),
        verify(gates_raw, "capability_statistical_gate_manifest"),
        verify(frame_raw, "capability_sampling_frame_manifest"),
    )
    if release["approved_baseline_artifact_digest"] != signed_artifact_digest(
        baseline_raw
    ):
        raise ValueError("baseline_release_join")
    for name in (
        "capability_fingerprint",
        "capability_contract_digest",
        "coverage_manifest_digest",
        "coverage_release_id",
        "statistical_gate_manifest_digest",
        "sampling_frame_manifest_digest",
        "sampling_frame_digest",
        "independent_cluster_definition_digest",
        "strata_definition_digest",
        "cluster_weighting_digest",
        "numeric_encoding_registry_digest",
        "unsupported_cells_digest",
    ):
        if baseline[name] != release[name]:
            raise ValueError("baseline_release_coordinate")
    if (baseline["capability_fingerprint"], baseline["capability_contract_digest"]) != (
        coverage["capability_fingerprint"],
        coverage["capability_contract_digest"],
    ) or (release["capability_fingerprint"], release["capability_contract_digest"]) != (
        coverage["capability_fingerprint"],
        coverage["capability_contract_digest"],
    ):
        raise ValueError("baseline_release_coverage_join")
    for name in (
        "sampling_frame_digest",
        "independent_cluster_definition_digest",
        "strata_definition_digest",
        "cluster_weighting_digest",
        "numeric_encoding_registry_digest",
    ):
        if baseline[name] != frame[name] or release[name] != frame[name]:
            raise ValueError("baseline_release_frame_join")
    rows = projection(coverage)
    if (
        base64.b64encode(ctv(rows)).decode() != EXPECTED_PROJECTION_B64
        or unsupported_digest(rows) != EXPECTED_PROJECTION_DIGEST
    ):
        raise ValueError("frozen_projection")
    if baseline["unsupported_cells_digest"] != unsupported_digest(rows) or release[
        "unsupported_cells_digest"
    ] != unsupported_digest(rows):
        raise ValueError("unsupported_projection_join")
    expected = {(row["coverage_cell_id"], row["metric_id"]) for row in rows}
    actual = {
        (gate["coverage_cell_id"], gate["metric_id"]) for gate in gates["metric_gates"]
    }
    if len(actual) != len(gates["metric_gates"]) or actual != expected:
        raise ValueError("gate_bijection")
    if (
        gates["capability_fingerprint"],
        gates["capability_coverage_manifest_digest"],
        gates["capability_coverage_release_id"],
        gates["sampling_frame_manifest_digest"],
        gates["numeric_encoding_registry_digest"],
    ) != (
        coverage["capability_fingerprint"],
        coverage["manifest_digest"],
        coverage["release_id"],
        frame["manifest_digest"],
        frame["numeric_encoding_registry_digest"],
    ):
        raise ValueError("gate_chain")
    if (
        frame["capability_fingerprint"],
        frame["coverage_manifest_digest"],
        frame["coverage_release_id"],
        frame["numeric_encoding_registry_digest"],
    ) != (
        coverage["capability_fingerprint"],
        coverage["manifest_digest"],
        coverage["release_id"],
        gates["numeric_encoding_registry_digest"],
    ):
        raise ValueError("frame_chain")
    if (
        baseline["coverage_manifest_digest"],
        baseline["statistical_gate_manifest_digest"],
        baseline["sampling_frame_manifest_digest"],
    ) != (
        coverage["manifest_digest"],
        gates["manifest_digest"],
        frame["manifest_digest"],
    ):
        raise ValueError("baseline_manifest_join")
    if set(authority) != set(AUTHORITY_FIELDS) or authority != derived_authority(
        baseline_raw, release_raw, baseline, release, coverage, gates, frame, rows
    ):
        raise ValueError("authority")
    specs = {entry["encoding_spec_id"]: entry for entry in frame["encoding_specs"]}
    _within_spec(frame["family_alpha"], specs, "family_alpha_spec")
    if frame["family_alpha"]["encoding_spec_id"] != frame["family_alpha_spec_id"]:
        raise ValueError("family_alpha_spec")
    for gate in gates["metric_gates"]:
        for name in (
            "cluster_value_lower_bound",
            "cluster_value_upper_bound",
            "nominal_alpha",
            "threshold",
        ):
            _within_spec(gate[name], specs, "gate_spec")
        if (
            gate["cluster_value_lower_bound"]["encoding_spec_id"]
            != gate["lower_spec_id"]
            or gate["cluster_value_upper_bound"]["encoding_spec_id"]
            != gate["upper_spec_id"]
            or gate["nominal_alpha"]["encoding_spec_id"]
            != gate["nominal_alpha_spec_id"]
            or gate["threshold"]["encoding_spec_id"] != gate["threshold_spec_id"]
        ):
            raise ValueError("gate_quantity_spec")
    iid_rows = frame["gate_iid_proofs"]
    if any(
        type(item) is not dict
        or set(item)
        != {
            "coverage_cell_id",
            "metric_id",
            "iid_bernoulli_clusters_proven",
            "proof_digest",
        }
        or type(item["iid_bernoulli_clusters_proven"]) is not bool
        or not isinstance(item["proof_digest"], str)
        or len(item["proof_digest"]) != 64
        for item in iid_rows
    ):
        raise ValueError("iid_shape")
    iid = {
        (item["coverage_cell_id"], item["metric_id"]): item[
            "iid_bernoulli_clusters_proven"
        ]
        for item in iid_rows
    }
    memberships = frame["memberships"]
    if set(iid) != expected or len(iid) != len(iid_rows) or not memberships:
        raise ValueError("iid_proof")
    by_gate = {
        (item["coverage_cell_id"], item["metric_id"]): [] for item in memberships
    }
    membership_identity: set[tuple[str, str, str]] = set()
    event_identity: set[tuple[str, str, str, str]] = set()
    provenance_identity: set[tuple[str, str, str]] = set()
    declared_event_identity: set[tuple[str, str, str]] = set()
    for item in memberships:
        if type(item) is not dict or set(item) != {
            "coverage_cell_id",
            "metric_id",
            "cluster_id",
            "provenance_ids",
            "expected_event_ids",
            "weight",
            "lower",
            "upper",
        }:
            raise ValueError("membership")
        key = (item["coverage_cell_id"], item["metric_id"])
        if (
            key not in expected
            or not isinstance(item["cluster_id"], str)
            or not item["provenance_ids"]
            or not item["expected_event_ids"]
            or type(item["weight"]) is not dict
            or set(item["weight"]) != {"encoding_spec_id", "fixed_scale_value"}
            or not isinstance(item["weight"].get("fixed_scale_value"), str)
        ):
            raise ValueError("membership")
        identity = (*key, item["cluster_id"])
        if (
            identity in membership_identity
            or len(set(item["provenance_ids"])) != len(item["provenance_ids"])
            or len(set(item["expected_event_ids"])) != len(item["expected_event_ids"])
        ):
            raise ValueError("membership_identity")
        membership_identity.add(identity)
        for provenance in item["provenance_ids"]:
            provenance_key = (*key, provenance)
            if provenance_key in provenance_identity:
                raise ValueError("cross_member_provenance")
            provenance_identity.add(provenance_key)
            for event in item["expected_event_ids"]:
                declared_event_key = (*key, event)
                if declared_event_key in declared_event_identity:
                    raise ValueError("cross_member_event")
                declared_event_identity.add(declared_event_key)
                event_key = (*key, provenance + "\0" + event)
                if event_key in event_identity:
                    raise ValueError("event_identity")
                event_identity.add(event_key)
        if not re.fullmatch(r"0\.[0-9]+", item["weight"]["fixed_scale_value"]):
            raise ValueError("weight_encoding")
        for name in ("weight", "lower", "upper"):
            _within_spec(item[name], specs, "membership_spec")
        if Fraction(item["lower"]["fixed_scale_value"]) >= Fraction(
            item["upper"]["fixed_scale_value"]
        ):
            raise ValueError("membership_range")
        by_gate.setdefault(key, []).append(item)
    if set(by_gate) != expected or any(not value for value in by_gate.values()):
        raise ValueError("coverage_evidence")
    gate_by_locator = {
        (gate["coverage_cell_id"], gate["metric_id"]): gate
        for gate in gates["metric_gates"]
    }
    if any(
        len(members) < gate_by_locator[locator]["minimum_clusters"]
        for locator, members in by_gate.items()
    ):
        raise ValueError("minimum_denominator")
    if any(
        sum(
            (Fraction(item["weight"]["fixed_scale_value"]) for item in values),
            Fraction(),
        )
        != 1
        for values in by_gate.values()
    ):
        raise ValueError("weights")
    for locator, proof in iid.items():
        gate = gate_by_locator[locator]
        if (
            proof is not (gate["test_method"] == "exact_binomial")
            or proof is not gate["iid_declared"]
        ):
            raise ValueError("iid_gate_agreement")
    for locator, members in by_gate.items():
        gate = gate_by_locator[locator]
        if any(
            member["weight"]["encoding_spec_id"] != gate["weight_spec_id"]
            or member["lower"]["encoding_spec_id"] != gate["lower_spec_id"]
            or member["upper"]["encoding_spec_id"] != gate["upper_spec_id"]
            for member in members
        ):
            raise ValueError("membership_gate_spec")
        if any(
            Fraction(member["lower"]["fixed_scale_value"])
            < Fraction(gate["cluster_value_lower_bound"]["fixed_scale_value"])
            or Fraction(member["upper"]["fixed_scale_value"])
            > Fraction(gate["cluster_value_upper_bound"]["fixed_scale_value"])
            for member in members
        ):
            raise ValueError("membership_gate_bounds")
    derived = {
        "authority": authority,
        "encoding_specs": frame["encoding_specs"],
        "family_alpha": frame["family_alpha"],
        "family_alpha_spec_id": frame["family_alpha_spec_id"],
        "gates": gates["metric_gates"],
        "iid_proofs": frame["gate_iid_proofs"],
        "memberships": memberships,
    }
    if candidate is not None and candidate != derived:
        raise ValueError("candidate_context")
    if parser_sentinel is not None:
        parser_sentinel.append(True)
    return rows


def _literal_self_test() -> None:
    fixture = json.loads(
        (Path(__file__).with_name("manifest-fixtures-v1.json")).read_text()
    )
    names = (
        "capability_baseline",
        "capability_release",
        "capability_coverage_manifest",
        "capability_statistical_gate_manifest",
        "capability_sampling_frame_manifest",
    )
    if fixture.get("public_key_base64") != PUBLIC_KEY_B64 or set(
        fixture.get("artifacts", {})
    ) != set(names):
        raise AssertionError("fixture_shape")
    rows = fixture["artifacts"]
    raws = tuple(
        base64.b64decode(rows[name]["canonical_bytes_base64"]) for name in names
    )
    parsed = tuple(verify(raw, name) for raw, name in zip(raws, names, strict=True))
    for name, value in rows.items():
        kind = name
        is_release = kind == "capability_release"
        digest_field = "release_digest" if is_release else "manifest_digest"
        purpose = "semantic_ingestion_capability_baseline_approval.v2" if is_release else kind
        signature_domain = "memorii.acceptance.capability-baseline-approval.signature.v2" if is_release else f"memorii.acceptance.{kind}.signature.v2"
        body = {
            key: item
            for key, item in json.loads(
                base64.b64decode(value["canonical_bytes_base64"])
            ).items()
            if key not in {digest_field, "signature"}
        }
        if (
            value["digest"]
            != json.loads(base64.b64decode(value["canonical_bytes_base64"]))[
                digest_field
            ]
            or value["signature"]
            != json.loads(base64.b64decode(value["canonical_bytes_base64"]))[
                "signature"
            ]
            or value["signing_preimage_base64"]
            != base64.b64encode(
                preimage(
                    signature_domain,
                    purpose,
                    "fixture-key",
                    value["digest"],
                    body,
                )
            ).decode()
        ):
            raise AssertionError("fixture_literal")
    projected = projection(parsed[2])
    authority = derived_authority(raws[0], raws[1], *parsed, projected)
    sentinel: list[bool] = []
    validate(*raws, authority, parser_sentinel=sentinel)
    if sentinel != [True]:
        raise AssertionError("parser_reachability")
    for field in AUTHORITY_FIELDS:
        mutated = dict(
            authority,
            **{field: "0" * 64 if field != "coverage_release_id" else "wrong"},
        )
        sentinel.clear()
        try:
            validate(*raws, mutated, parser_sentinel=sentinel)
        except ValueError:
            if sentinel:
                raise AssertionError("authority_reached_parser")
        else:
            raise AssertionError(field)

    def resigned(index: int, mutate) -> bytes:
        value = json.loads(raws[index])
        for name in metadata_fields(names[index]):
            value.pop(name, None)
        mutate(value)
        return signed(names[index], value)

    def rejects_before_parser(
        changed: tuple[bytes, bytes, bytes, bytes, bytes],
        label: str,
        expected: str | None = None,
    ) -> None:
        reached: list[bool] = []
        try:
            validate(*changed, authority, parser_sentinel=reached)
        except ValueError as exc:
            if reached:
                raise AssertionError(f"{label}_parser")
            if expected is not None and str(exc) != expected:
                raise AssertionError(f"{label}:{exc}") from exc
            return
        raise AssertionError(label)

    original_bodies = {
        name: {
            key: value
            for key, value in json.loads(raw).items()
            if key not in metadata_fields(name)
        }
        for name, raw in zip(names, raws, strict=True)
    }

    def reissued_rejects(
        name: str, mutate, expected: str, *, retain_unsupported: bool = False
    ) -> None:
        bodies = copy.deepcopy(original_bodies)
        mutate(bodies[name])
        changed, changed_authority = reissue_chain(
            bodies, retain_unsupported=retain_unsupported
        )
        reached: list[bool] = []
        try:
            validate(*changed, changed_authority, parser_sentinel=reached)
        except ValueError as exc:
            if reached or str(exc) != expected:
                raise AssertionError(f"reissued:{expected}:{exc}") from exc
            return
        raise AssertionError(f"reissued:{expected}")

    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["gate_iid_proofs"][0].update(
            iid_bernoulli_clusters_proven=False
        ),
        "iid_gate_agreement",
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["memberships"][0]["weight"].update(fixed_scale_value="0.300"),
        "weights",
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["memberships"][0]["weight"].update(fixed_scale_value="0.500"),
        "weights",
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["memberships"][0]["weight"].update(
            encoding_spec_id="q", fixed_scale_value="0.40"
        ),
        "membership_gate_spec",
    )
    reissued_rejects(
        "capability_statistical_gate_manifest",
        lambda body: body["metric_gates"][0]["threshold"].update(
            fixed_scale_value="1.100"
        ),
        "gate_spec",
    )
    reissued_rejects(
        "capability_statistical_gate_manifest",
        lambda body: body["metric_gates"][0]["cluster_value_upper_bound"].update(
            fixed_scale_value="0.50"
        ),
        "membership_gate_bounds",
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["memberships"][5].update(
            provenance_ids=body["memberships"][0]["provenance_ids"]
        ),
        "cross_member_provenance",
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["memberships"][5].update(
            expected_event_ids=body["memberships"][0]["expected_event_ids"]
        ),
        "cross_member_event",
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["memberships"].pop(5),
        "minimum_denominator",
    )
    reissued_rejects(
        "capability_baseline",
        lambda body: body.update(unsupported_cells_digest="0" * 64),
        "unsupported_projection_join",
        retain_unsupported=True,
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["family_alpha"].update(
            encoding_spec_id="r", fixed_scale_value="0.050"
        ),
        "family_alpha_spec",
    )
    reissued_rejects(
        "capability_statistical_gate_manifest",
        lambda body: body["metric_gates"][0]["threshold"].update(
            encoding_spec_id="r", fixed_scale_value="0.900"
        ),
        "gate_quantity_spec",
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["memberships"][0]["lower"].update(
            encoding_spec_id="q", fixed_scale_value="0.00"
        ),
        "membership_gate_spec",
    )
    reissued_rejects(
        "capability_sampling_frame_manifest",
        lambda body: body["memberships"][0]["upper"].update(
            encoding_spec_id="q", fixed_scale_value="1.00"
        ),
        "membership_gate_spec",
    )

    # Every mutation is validly re-signed, so these prove semantic validation
    # rather than only the outer artifact signature.
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            raws[3],
            resigned(
                4,
                lambda body: body["gate_iid_proofs"].__setitem__(
                    0,
                    {
                        **body["gate_iid_proofs"][0],
                        "iid_bernoulli_clusters_proven": False,
                    },
                ),
            ),
        ),
        "false_iid",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            raws[3],
            resigned(
                4,
                lambda body: body["gate_iid_proofs"].append(
                    dict(body["gate_iid_proofs"][0])
                ),
            ),
        ),
        "duplicate_iid",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            raws[3],
            resigned(
                4, lambda body: body["memberships"].append(dict(body["memberships"][0]))
            ),
        ),
        "duplicate_membership",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            raws[3],
            resigned(
                4,
                lambda body: body["memberships"][0].update(
                    expected_event_ids=["e1", "e1"]
                ),
            ),
        ),
        "duplicate_event",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            resigned(3, lambda body: body["metric_gates"][0].pop("threshold")),
            raws[4],
        ),
        "missing_gate_field",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            resigned(
                3, lambda body: body["metric_gates"][0].update(minimum_clusters="2")
            ),
            raws[4],
        ),
        "wrong_gate_type",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            raws[3],
            resigned(
                4,
                lambda body: body["memberships"][0]["weight"].update(
                    fixed_scale_value="0.50"
                ),
            ),
        ),
        "nonnormalized_weight",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            raws[3],
            resigned(
                4, lambda body: body["memberships"][0].update(expected_event_ids=[])
            ),
        ),
        "empty_denominator",
    )
    rejects_before_parser(
        (
            raws[0],
            resigned(
                1, lambda body: body.update(approved_baseline_artifact_digest="0" * 64)
            ),
            raws[2],
            raws[3],
            raws[4],
        ),
        "baseline_release_join",
    )
    rejects_before_parser(
        (
            resigned(0, lambda body: body.update(coverage_manifest_digest="0" * 64)),
            raws[1],
            raws[2],
            raws[3],
            raws[4],
        ),
        "baseline_coverage_join",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            resigned(
                3,
                lambda body: body.update(capability_coverage_manifest_digest="0" * 64),
            ),
            raws[4],
        ),
        "gate_coverage_join",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            resigned(
                3, lambda body: body.update(sampling_frame_manifest_digest="0" * 64)
            ),
            raws[4],
        ),
        "gate_frame_join",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            raws[3],
            resigned(4, lambda body: body.update(coverage_manifest_digest="0" * 64)),
        ),
        "frame_coverage_join",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            raws[3],
            resigned(
                4,
                lambda body: body["memberships"][0]["lower"].update(
                    encoding_spec_id="wrong"
                ),
            ),
        ),
        "wrong_membership_spec",
    )
    rejects_before_parser(
        (
            raws[0],
            raws[1],
            raws[2],
            resigned(
                3,
                lambda body: body["metric_gates"][0][
                    "cluster_value_upper_bound"
                ].update(fixed_scale_value="0.50"),
            ),
            raws[4],
        ),
        "changed_gate_bound",
    )
    # Content is changed while retaining the old literal digest/signature.
    old = json.loads(raws[3])
    old["metric_gates"][0]["threshold"]["fixed_scale_value"] = "0.80"
    try:
        validate(
            raws[0],
            raws[1],
            raws[2],
            json.dumps(old, sort_keys=True, separators=(",", ":")).encode(),
            raws[4],
            authority,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("old_signature_content_mutation")
    # A valid new signature cannot repair an inconsistent authority join.
    gate_body = {
        key: item
        for key, item in json.loads(raws[3]).items()
        if key
        not in {
            "schema_version",
            "purpose",
            "signing_key_id",
            "trust_policy_digest",
            "manifest_digest",
            "signature",
        }
    }
    gate_body["capability_coverage_manifest_digest"] = "0" * 64
    resigned = signed("capability_statistical_gate_manifest", gate_body)
    try:
        validate(raws[0], raws[1], raws[2], resigned, raws[4], authority)
    except ValueError:
        pass
    else:
        raise AssertionError("resigned_inconsistent_join")
    for index in range(len(names)):
        changed = json.loads(raws[index])
        changed["unknown"] = True
        try:
            verify(
                json.dumps(changed, sort_keys=True, separators=(",", ":")).encode(),
                names[index],
            )
        except ValueError:
            continue
        raise AssertionError("unknown_field")


if __name__ == "__main__":
    _literal_self_test()
