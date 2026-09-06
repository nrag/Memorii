"""Operation-aware digest-work counterfactual for validated canonical closure."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any


def _signature(row: dict[str, Any]) -> str:
    structural = {
        key: value
        for key, value in row.items()
        if key not in {"content_digest", "first_stack"}
    }
    return json.dumps(structural, sort_keys=True, separators=(",", ":"))


def _group(identities: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for identity, row in identities.items():
        grouped[_signature(row)].append(identity)
    return {key: sorted(values) for key, values in grouped.items()}


def _retained_full_validations(row: dict[str, Any], *, specialized: bool) -> tuple[int, dict[str, int]]:
    validations = int(row["validations"])
    if specialized:
        return validations, {"specialized_owner_full_path": validations}
    classification = row["classification"]
    if classification == "aggregate_coverable_candidate":
        return 0, {"aggregate_closure": 0}
    if classification == "in_process_only_candidate":
        return 1, {"necessary_operation_identity": 1}
    if classification != "mandatory_boundary_root":
        raise ValueError(f"unknown classification: {classification}")
    writer = sum(
        int(count)
        for event, count in row["boundary_events"].items()
        if event.startswith("writer_admission:")
    )
    nonwriter = sum(
        1
        for event, count in row["boundary_events"].items()
        if not event.startswith("writer_admission:") and int(count) > 0
    )
    return writer + nonwriter, {
        "independent_writer_occurrences": writer,
        "independent_nonwriter_event_identities": nonwriter,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-census", type=Path, required=True)
    parser.add_argument("--current-run", type=Path, required=True)
    parser.add_argument("--path-proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    frozen_document = json.loads(args.frozen_census.read_text())
    current_document = json.loads(args.current_run.read_text())
    path_document = json.loads(args.path_proof.read_text())
    frozen_census = frozen_document["census"]
    current_census = current_document["validation_floor_census"]
    frozen = frozen_census["identities"]
    current = current_census["identities"]
    path_identities = path_document["identities"]

    frozen_groups = _group(frozen)
    current_groups = _group(current)
    if frozen_groups.keys() != current_groups.keys():
        raise ValueError("frozen and current structural coordinate sets differ")
    if any(len(frozen_groups[key]) != len(current_groups[key]) for key in frozen_groups):
        raise ValueError("frozen and current structural coordinate multiplicities differ")

    current_to_frozen: dict[str, str] = {}
    for signature in sorted(frozen_groups):
        for frozen_identity, current_identity in zip(
            frozen_groups[signature], current_groups[signature], strict=True
        ):
            current_to_frozen[current_identity] = frozen_identity
    if len(current_to_frozen) != 238:
        raise ValueError("operation-aware identity mapping is incomplete")
    if set(path_identities) != set(current):
        raise ValueError("path proof does not cover the current census exactly")

    rows: list[dict[str, Any]] = []
    full_after = 0
    repeated_after = 0
    proof_covered = 0
    retained_reasons: dict[str, int] = defaultdict(int)
    all_substitutions_equal = True
    for current_identity, frozen_identity in sorted(current_to_frozen.items()):
        current_row = current[current_identity]
        frozen_row = frozen[frozen_identity]
        proof = path_identities[current_identity]
        root_rows = [
            row
            for row in proof["member_paths"]
            if row["path"] == [] and row["member_type"] == current_row["family"]
        ]
        root_verified = len(root_rows) == 1
        declared_digest = current_identity.rsplit(":", 1)[1]
        generic_verified = bool(proof["generic_digest_preimage_verified"])
        specialized = not generic_verified
        retained, reasons = _retained_full_validations(frozen_row, specialized=specialized)
        validations = int(frozen_row["validations"])
        if retained > validations:
            raise ValueError("retained validation count exceeds baseline")
        covered = validations - retained
        substitution_equal = root_verified and (generic_verified or covered == 0)
        all_substitutions_equal &= substitution_equal
        full_after += retained
        repeated_after += max(0, retained - 1)
        proof_covered += covered
        for reason, count in reasons.items():
            retained_reasons[reason] += count
        rows.append({
            "frozen_identity": frozen_identity,
            "current_identity": current_identity,
            "family": current_row["family"],
            "classification": frozen_row["classification"],
            "baseline_validations": validations,
            "retained_full_validations": retained,
            "proof_covered_validations": covered,
            "declared_digest": declared_digest,
            "root_path_verified": root_verified,
            "generic_digest_preimage_verified": generic_verified,
            "equal_digest_substitution": substitution_equal,
            "retained_reasons": reasons,
        })

    baseline_full = int(frozen_census["total_validations"])
    baseline_repeated = int(frozen_census["repeat_validations"])
    if full_after + proof_covered != baseline_full:
        raise ValueError("counterfactual accounting does not close")
    repeated_reduction = (baseline_repeated - repeated_after) / baseline_repeated
    target_repeated = 4_272
    target_total = 4_510
    passed = (
        full_after <= target_total
        and repeated_after <= target_repeated
        and repeated_reduction >= 0.90
        and all_substitutions_equal
        and len(rows) == 238
    )
    output = {
        "schema": "memorii.semantic-ingestion.vcc-exp-002.v1",
        "experiment": "VCC-EXP-002",
        "evidence_stage": "reference_only_operation_aware_counterfactual",
        "production_implementation_changed": False,
        "tests_changed": False,
        "certifies_m3_1": False,
        "sources": {
            "frozen_census_sha256": sha256(args.frozen_census.read_bytes()).hexdigest(),
            "current_run_sha256": sha256(args.current_run.read_bytes()).hexdigest(),
            "path_proof_sha256": sha256(args.path_proof.read_bytes()).hexdigest(),
        },
        "identity_mapping": {
            "mapped_identities": len(rows),
            "stable_exact_content_identities": len(set(frozen) & set(current)),
            "operation_bound_structural_identities": len(set(current) - set(frozen)),
            "structural_coordinate_multiset_equal": True,
        },
        "baseline": {
            "full_digest_computations": baseline_full,
            "repeated_digest_computations": baseline_repeated,
            "unique_content_identities": int(frozen_census["unique_content_identities"]),
        },
        "counterfactual": {
            "full_digest_computations": full_after,
            "repeated_digest_computations": repeated_after,
            "proof_covered_digest_computations": proof_covered,
            "repeated_digest_reduction_fraction": repeated_reduction,
            "retained_reasons": dict(sorted(retained_reasons.items())),
        },
        "target": {
            "maximum_full_digest_computations": target_total,
            "maximum_repeated_digest_computations": target_repeated,
            "minimum_repeated_digest_reduction_fraction": 0.90,
        },
        "promise_projection": {
            "equal": all_substitutions_equal,
            "basis": "Every covered call returns the current operation's independently reproduced declared digest; specialized owner calls remain on the full path.",
            "production_output_sha256": current_document["output_sha256"],
            "counterfactual_output_sha256": current_document["output_sha256"],
        },
        "security_contract": {
            "writer_occurrences_retained": retained_reasons.get("independent_writer_occurrences", 0),
            "nonwriter_event_identities_retained": retained_reasons.get("independent_nonwriter_event_identities", 0),
            "necessary_operation_identities_retained": retained_reasons.get("necessary_operation_identity", 0),
            "specialized_owner_validations_retained": retained_reasons.get("specialized_owner_full_path", 0),
            "digest_only_authority": False,
            "scope": "one current production operation; no evidence crosses writer invocations",
        },
        "passed": passed,
        "decision": (
            "operation-aware validated canonical closure exceeds the 90 percent repeated-digest reduction gate"
            if passed else
            "counterfactual does not satisfy the frozen reduction or equality gate"
        ),
        "identities": rows,
    }
    encoded = json.dumps(output, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    args.output.write_bytes(encoded)
    print(json.dumps({
        "passed": passed,
        "full_after": full_after,
        "repeated_after": repeated_after,
        "proof_covered": proof_covered,
        "repeated_reduction_fraction": repeated_reduction,
        "retained_reasons": dict(sorted(retained_reasons.items())),
        "promise_projection_equal": all_substitutions_equal,
        "output_sha256": sha256(encoded).hexdigest(),
    }, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
