"""Dependency-free semantic validator for lifecycle-root signer provenance."""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

FORMAT = "memorii-sia-lifecycle-root-signer-provenance-witness-v1"
PURPOSE = "semantic_ingestion_traceability_lifecycle_root"
GENESIS = "independently_provisioned_bootstrap_anchor"
SUCCESSOR = "prior_verified_lifecycle_root"
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
ANCHOR_FIELDS = (
    "authority_id",
    "provisioned_channel_id",
    "bootstrap_anchor_id",
    "bootstrap_anchor_digest",
    "issuer_id",
    "key_or_certificate_digest",
    "signature_profile_id",
    "signature_purpose",
    "eligible_not_before",
    "eligible_not_after",
)
GENESIS_FIELDS = {"source_kind", *ANCHOR_FIELDS}
SUCCESSOR_FIELDS = {
    "source_kind",
    "signature_purpose",
    "issuer_id",
    "key_or_certificate_digest",
    "signature_profile_id",
    "trust_lifecycle_root_digest",
    "lifecycle_record_digest",
    "eligible_not_before",
    "eligible_not_after",
}
ROOT_FIELDS = {
    "witness_id",
    "owner",
    "authority_id",
    "sequence",
    "issued_at",
    "lifecycle_root_digest",
    "terminal_record_digest",
    "signer_coordinates",
    "preimage_signer_coordinates",
}
HISTORY_FIELDS = {
    "authority_id",
    "sequence",
    "lifecycle_root_digest",
    "terminal_record_digest",
    "final_action_authorized_signer_coordinates",
}
CASE_FIELDS = {"case_id", "base", "operation", "path", "value", "expected_reason"}
BOUNDARY_FIELDS = {
    "case_id",
    "base",
    "issued_at",
    "expected_verdict",
    "expected_reason",
}
EXPECTED_BOUNDARY_CASES = {
    "lifecycle-root-genesis-issued-at-not-before",
    "lifecycle-root-genesis-issued-at-not-after",
    "lifecycle-root-genesis-issued-before-not-before",
    "lifecycle-root-genesis-issued-after-not-after",
    "lifecycle-root-successor-issued-at-not-before",
    "lifecycle-root-successor-issued-at-not-after",
    "lifecycle-root-successor-issued-before-not-before",
    "lifecycle-root-successor-issued-after-not-after",
}
EXPECTED_HISTORY_CASES = {
    "lifecycle-root-history-issuer-malformed",
    "lifecycle-root-history-key-malformed",
    "lifecycle-root-history-profile-malformed",
    "lifecycle-root-history-interval-order-malformed",
}
EXPECTED_CASES = {
    "lifecycle-root-genesis-authority-substitution",
    "lifecycle-root-genesis-channel-substitution",
    "lifecycle-root-genesis-anchor-id-substitution",
    "lifecycle-root-genesis-anchor-digest-substitution",
    "lifecycle-root-genesis-issuer-substitution",
    "lifecycle-root-genesis-key-substitution",
    "lifecycle-root-genesis-profile-substitution",
    "lifecycle-root-genesis-purpose-substitution",
    "lifecycle-root-genesis-not-before-substitution",
    "lifecycle-root-genesis-not-after-substitution",
    "lifecycle-root-genesis-mixed-union-fields",
    "lifecycle-root-sequence-one-successor",
    "lifecycle-root-successor-genesis-downgrade",
    "lifecycle-root-successor-authority-substitution",
    "lifecycle-root-successor-issuer-substitution",
    "lifecycle-root-successor-key-substitution",
    "lifecycle-root-successor-profile-substitution",
    "lifecycle-root-successor-purpose-substitution",
    "lifecycle-root-successor-not-before-substitution",
    "lifecycle-root-successor-not-after-substitution",
    "lifecycle-root-successor-issuer-malformed",
    "lifecycle-root-successor-key-malformed",
    "lifecycle-root-successor-profile-malformed",
    "lifecycle-root-successor-interval-order-malformed",
    "lifecycle-root-rp-owner-cross-substitution",
    "lifecycle-root-ba-owner-cross-substitution",
    "lifecycle-root-rr-owner-cross-substitution",
    "lifecycle-root-record-owner-cross-substitution",
    "lifecycle-root-envelope-preimage-mismatch",
    "lifecycle-root-successor-self-root-reference",
    "lifecycle-root-successor-self-record-reference",
    "lifecycle-root-successor-forward-root-reference",
    "lifecycle-root-successor-forward-record-reference",
}


class Rejected(ValueError):
    pass


def strict_json(raw: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    return json.loads(raw, object_pairs_hook=object_pairs)


def require_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise Rejected(f"{label}_invalid")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise Rejected(f"{label}_invalid") from error


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX_64.fullmatch(value) is None:
        raise Rejected(f"{label}_invalid")
    return value


def validate_successor_coordinate_structure(
    coordinate: Any,
    *,
    prefix: str,
) -> tuple[datetime, datetime]:
    if not isinstance(coordinate, dict) or set(coordinate) != SUCCESSOR_FIELDS:
        raise Rejected(f"{prefix}_fields_invalid")
    if coordinate["source_kind"] != SUCCESSOR:
        raise Rejected(f"{prefix}_source_invalid")
    if coordinate["signature_purpose"] != PURPOSE:
        raise Rejected("purpose_mismatch" if prefix == "successor" else f"{prefix}_purpose_invalid")
    for field, reason in (
        ("issuer_id", f"{prefix}_issuer_invalid"),
        ("signature_profile_id", f"{prefix}_profile_invalid"),
    ):
        if not isinstance(coordinate[field], str) or not coordinate[field]:
            raise Rejected(reason)
    require_digest(coordinate["key_or_certificate_digest"], f"{prefix}_key")
    require_digest(coordinate["trust_lifecycle_root_digest"], f"{prefix}_root_digest")
    require_digest(coordinate["lifecycle_record_digest"], f"{prefix}_record_digest")
    not_before = require_time(
        coordinate["eligible_not_before"], f"{prefix}_eligible_not_before"
    )
    not_after = require_time(
        coordinate["eligible_not_after"], f"{prefix}_eligible_not_after"
    )
    if not_before >= not_after:
        raise Rejected(f"{prefix}_interval_invalid")
    return not_before, not_after


def validate_anchor(anchor: Any) -> dict[str, Any]:
    if not isinstance(anchor, dict) or set(anchor) != set(ANCHOR_FIELDS):
        raise ValueError("authority anchor shape invalid")
    for name in ANCHOR_FIELDS:
        if not isinstance(anchor[name], str):
            raise ValueError(f"authority anchor {name} invalid")
    require_digest(anchor["bootstrap_anchor_digest"], "anchor_digest")
    require_digest(anchor["key_or_certificate_digest"], "anchor_key")
    if anchor["signature_purpose"] != PURPOSE:
        raise ValueError("authority anchor purpose invalid")
    if require_time(anchor["eligible_not_before"], "anchor_not_before") >= require_time(
        anchor["eligible_not_after"], "anchor_not_after"
    ):
        raise ValueError("authority anchor interval invalid")
    return anchor


def validate_genesis(coordinate: Any, anchor: dict[str, Any]) -> None:
    if not isinstance(coordinate, dict) or set(coordinate) != GENESIS_FIELDS:
        raise Rejected("genesis_fields_invalid")
    if coordinate["source_kind"] != GENESIS:
        raise Rejected("genesis_source_invalid")
    if coordinate["signature_purpose"] != PURPOSE:
        raise Rejected("purpose_mismatch")
    reason_by_field = {
        "authority_id": "anchor_authority_mismatch",
        "provisioned_channel_id": "anchor_channel_mismatch",
        "bootstrap_anchor_id": "anchor_id_mismatch",
        "bootstrap_anchor_digest": "anchor_digest_mismatch",
        "issuer_id": "anchor_issuer_mismatch",
        "key_or_certificate_digest": "anchor_key_mismatch",
        "signature_profile_id": "anchor_profile_mismatch",
        "eligible_not_before": "anchor_not_before_mismatch",
        "eligible_not_after": "anchor_not_after_mismatch",
    }
    for field, reason in reason_by_field.items():
        if coordinate[field] != anchor[field]:
            raise Rejected(reason)
    if require_time(coordinate["eligible_not_before"], "eligible_not_before") >= require_time(
        coordinate["eligible_not_after"], "eligible_not_after"
    ):
        raise Rejected("anchor_interval_invalid")


def validate_successor(
    coordinate: Any,
    root: dict[str, Any],
    history: list[dict[str, Any]],
) -> None:
    not_before, not_after = validate_successor_coordinate_structure(
        coordinate, prefix="successor"
    )
    if (
        coordinate["trust_lifecycle_root_digest"] == root["lifecycle_root_digest"]
        or coordinate["lifecycle_record_digest"] == root["terminal_record_digest"]
    ):
        raise Rejected("successor_self_reference")
    matching = [
        item
        for item in history
        if item["lifecycle_root_digest"] == coordinate["trust_lifecycle_root_digest"]
        and item["terminal_record_digest"] == coordinate["lifecycle_record_digest"]
    ]
    if len(matching) != 1:
        raise Rejected("successor_reference_unverified")
    prior = matching[0]
    if prior["sequence"] != root["sequence"] - 1:
        raise Rejected("successor_reference_not_immediate")
    if prior["authority_id"] != root["authority_id"]:
        raise Rejected("successor_authority_mismatch")
    authorized = prior["final_action_authorized_signer_coordinates"]
    if not isinstance(authorized, list) or len(authorized) != 1:
        raise Rejected("successor_authorization_ambiguous")
    expected = authorized[0]
    validate_successor_coordinate_structure(expected, prefix="history")
    reason_by_field = {
        "source_kind": "successor_source_invalid",
        "signature_purpose": "purpose_mismatch",
        "issuer_id": "successor_issuer_mismatch",
        "key_or_certificate_digest": "successor_key_mismatch",
        "signature_profile_id": "successor_profile_mismatch",
        "trust_lifecycle_root_digest": "successor_root_mismatch",
        "lifecycle_record_digest": "successor_record_mismatch",
        "eligible_not_before": "successor_not_before_mismatch",
        "eligible_not_after": "successor_not_after_mismatch",
    }
    for field, reason in reason_by_field.items():
        if coordinate[field] != expected[field]:
            raise Rejected(reason)
    issued_at = require_time(root["issued_at"], "issued_at")
    if issued_at < not_before or issued_at > not_after:
        raise Rejected("successor_issued_at_ineligible")


def validate_history(history: Any, roots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(history, list) or len(history) != 1:
        raise ValueError("successor history must contain exactly one verified root")
    item = history[0]
    if not isinstance(item, dict) or set(item) != HISTORY_FIELDS:
        raise ValueError("successor history shape invalid")
    if not isinstance(item["authority_id"], str) or not item["authority_id"]:
        raise Rejected("history_authority_invalid")
    if isinstance(item["sequence"], bool) or item["sequence"] != 1:
        raise ValueError("successor history sequence invalid")
    require_digest(item["lifecycle_root_digest"], "history_root_digest")
    require_digest(item["terminal_record_digest"], "history_record_digest")
    genesis = roots[0]
    for field in (
        "authority_id",
        "sequence",
        "lifecycle_root_digest",
        "terminal_record_digest",
    ):
        if item[field] != genesis[field]:
            raise ValueError(f"successor history {field} mismatch")
    authorized = item["final_action_authorized_signer_coordinates"]
    if not isinstance(authorized, list) or len(authorized) != 1:
        raise ValueError("successor history signer authorization invalid")
    coordinate = authorized[0]
    validate_successor_coordinate_structure(coordinate, prefix="history")
    if (
        coordinate["trust_lifecycle_root_digest"] != item["lifecycle_root_digest"]
        or coordinate["lifecycle_record_digest"] != item["terminal_record_digest"]
    ):
        raise ValueError("successor history signer reference mismatch")
    return history


def validate_root(
    root: Any,
    anchor: dict[str, Any],
    history: list[dict[str, Any]],
) -> None:
    if not isinstance(root, dict) or set(root) != ROOT_FIELDS:
        raise Rejected("root_shape_invalid")
    if root["owner"] != "lifecycle_root":
        raise Rejected("wrong_owner")
    if not isinstance(root["authority_id"], str) or not root["authority_id"]:
        raise Rejected("authority_invalid")
    if isinstance(root["sequence"], bool) or not isinstance(root["sequence"], int) or root["sequence"] < 1:
        raise Rejected("sequence_invalid")
    require_digest(root["lifecycle_root_digest"], "root_digest")
    require_digest(root["terminal_record_digest"], "terminal_record_digest")
    issued_at = require_time(root["issued_at"], "issued_at")
    envelope = root["signer_coordinates"]
    preimage = root["preimage_signer_coordinates"]
    if not isinstance(envelope, list) or len(envelope) != 1:
        raise Rejected("envelope_cardinality_invalid")
    if not isinstance(preimage, list) or len(preimage) != 1:
        raise Rejected("preimage_cardinality_invalid")
    coordinate = envelope[0]
    source = coordinate.get("source_kind") if isinstance(coordinate, dict) else None
    if root["sequence"] == 1:
        if source != GENESIS:
            raise Rejected("sequence_one_requires_genesis")
        if history:
            raise Rejected("sequence_one_history_invalid")
        validate_genesis(coordinate, anchor)
        if root["authority_id"] != anchor["authority_id"]:
            raise Rejected("anchor_authority_mismatch")
        not_before = require_time(coordinate["eligible_not_before"], "eligible_not_before")
        not_after = require_time(coordinate["eligible_not_after"], "eligible_not_after")
        if issued_at < not_before or issued_at > not_after:
            raise Rejected("genesis_issued_at_ineligible")
    else:
        if source != SUCCESSOR:
            raise Rejected("successor_requires_prior_root")
        validate_successor(coordinate, root, history)
    if envelope != preimage:
        raise Rejected("envelope_preimage_mismatch")


def mutate(root: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(root)
    cursor: Any = candidate
    path = case["path"]
    if not isinstance(path, list) or not path:
        raise ValueError(f"{case['case_id']}: mutation path invalid")
    for component in path[:-1]:
        cursor = cursor[component]
    operation = case["operation"]
    if operation not in {"replace", "add", "replace_coordinate"}:
        raise ValueError(f"{case['case_id']}: mutation operation invalid")
    cursor[path[-1]] = copy.deepcopy(case["value"])
    return candidate


def validate_fixture(value: Any, *, self_test: bool) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != {
        "format",
        "authority_anchor",
        "accepted_roots",
        "successor_history",
        "boundary_witnesses",
        "history_negative_cases",
        "negative_cases",
    }:
        raise ValueError("witness fixture shape invalid")
    if value["format"] != FORMAT:
        raise ValueError("witness format invalid")
    anchor = validate_anchor(value["authority_anchor"])
    roots = value["accepted_roots"]
    if not isinstance(roots, list) or len(roots) != 2:
        raise ValueError("witness must contain exactly two accepted roots")
    by_id: dict[str, dict[str, Any]] = {}
    validate_root(roots[0], anchor, [])
    history = validate_history(value["successor_history"], roots)
    validate_root(roots[1], anchor, history)
    for root in roots:
        if root["witness_id"] in by_id:
            raise ValueError("duplicate witness ID")
        by_id[root["witness_id"]] = root
    if [item["sequence"] for item in roots] != [1, 2]:
        raise ValueError("accepted witness sequence invalid")
    boundary_cases = value["boundary_witnesses"]
    if not isinstance(boundary_cases, list):
        raise ValueError("boundary witnesses invalid")
    boundary_seen: set[str] = set()
    boundary_accepted = 0
    boundary_rejected = 0
    for case in boundary_cases:
        if not isinstance(case, dict) or set(case) != BOUNDARY_FIELDS:
            raise ValueError("boundary witness shape invalid")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or case_id in boundary_seen:
            raise ValueError("boundary witness ID invalid")
        boundary_seen.add(case_id)
        if case["base"] not in by_id:
            raise ValueError(f"{case_id}: boundary base invalid")
        if case["expected_verdict"] not in {"accept", "reject"}:
            raise ValueError(f"{case_id}: boundary verdict invalid")
        expected_reason = case["expected_reason"]
        if (case["expected_verdict"] == "accept" and expected_reason is not None) or (
            case["expected_verdict"] == "reject" and not isinstance(expected_reason, str)
        ):
            raise ValueError(f"{case_id}: boundary reason invalid")
        candidate = copy.deepcopy(by_id[case["base"]])
        candidate["issued_at"] = case["issued_at"]
        case_history = [] if candidate["sequence"] == 1 else history
        try:
            validate_root(candidate, anchor, case_history)
        except Rejected as error:
            if case["expected_verdict"] != "reject" or str(error) != expected_reason:
                raise AssertionError(
                    f"{case_id}: expected {case['expected_verdict']} "
                    f"{expected_reason}, got {error}"
                ) from error
            boundary_rejected += 1
        else:
            if case["expected_verdict"] != "accept":
                raise AssertionError(f"{case_id}: rejected boundary was accepted")
            boundary_accepted += 1
    if boundary_seen != EXPECTED_BOUNDARY_CASES:
        raise ValueError(
            "boundary witness inventory mismatch: "
            f"missing={sorted(EXPECTED_BOUNDARY_CASES - boundary_seen)} "
            f"extra={sorted(boundary_seen - EXPECTED_BOUNDARY_CASES)}"
        )
    history_cases = value["history_negative_cases"]
    if not isinstance(history_cases, list):
        raise ValueError("history negative cases invalid")
    history_seen: set[str] = set()
    for case in history_cases:
        if not isinstance(case, dict) or set(case) != CASE_FIELDS:
            raise ValueError("history negative case shape invalid")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or case_id in history_seen:
            raise ValueError("history negative case ID invalid")
        history_seen.add(case_id)
        if case["base"] != "successor-history" or not isinstance(
            case["expected_reason"], str
        ):
            raise ValueError(f"{case_id}: history base/reason invalid")
    if history_seen != EXPECTED_HISTORY_CASES:
        raise ValueError(
            "history negative inventory mismatch: "
            f"missing={sorted(EXPECTED_HISTORY_CASES - history_seen)} "
            f"extra={sorted(history_seen - EXPECTED_HISTORY_CASES)}"
        )
    cases = value["negative_cases"]
    if not isinstance(cases, list):
        raise ValueError("negative cases invalid")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != CASE_FIELDS:
            raise ValueError("negative case shape invalid")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or case_id in seen:
            raise ValueError("negative case ID invalid")
        seen.add(case_id)
        if case["base"] not in by_id or not isinstance(case["expected_reason"], str):
            raise ValueError(f"{case_id}: base/reason invalid")
    if seen != EXPECTED_CASES:
        raise ValueError(
            f"negative case inventory mismatch: missing={sorted(EXPECTED_CASES - seen)} "
            f"extra={sorted(seen - EXPECTED_CASES)}"
        )
    if self_test:
        for case in cases:
            candidate = mutate(by_id[case["base"]], case)
            case_history = [] if candidate["sequence"] == 1 else history
            try:
                validate_root(candidate, anchor, case_history)
            except Rejected as error:
                if str(error) != case["expected_reason"]:
                    raise AssertionError(
                        f"{case['case_id']}: expected {case['expected_reason']}, got {error}"
                    ) from error
            else:
                raise AssertionError(f"{case['case_id']}: mutation accepted")
        for case in history_cases:
            candidate_history = copy.deepcopy(history)
            candidate_history[0] = mutate(candidate_history[0], case)
            try:
                validate_history(candidate_history, roots)
            except Rejected as error:
                if str(error) != case["expected_reason"]:
                    raise AssertionError(
                        f"{case['case_id']}: expected {case['expected_reason']}, "
                        f"got {error}"
                    ) from error
            else:
                raise AssertionError(f"{case['case_id']}: history mutation accepted")
    return {
        "accepted": len(roots) + boundary_accepted,
        "rejected": boundary_rejected
        + (len(cases) + len(history_cases) if self_test else 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    result = validate_fixture(strict_json(args.fixture.read_bytes()), self_test=args.self_test)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
