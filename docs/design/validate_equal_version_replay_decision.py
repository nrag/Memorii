"""Validate the frozen equal-version replay decision and bound design bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

_FORMAT = "memorii.equal-version-replay-decision.v1"
_DOMAIN = b"memorii.equal-version-replay-decision.v1\0"
_EXPECTED_KEYS = {
    "approved_on",
    "approved_owner",
    "bound_documents",
    "checkpoint_rule",
    "decision",
    "decision_digest",
    "duplicate_rule",
    "format",
    "ordering_authority",
    "recovery_rule",
    "required_evidence_families",
    "visibility_rule",
}
_EXPECTED_DOCUMENTS = {
    "docs/design/conflict_attention.md",
    "docs/design/event_model.md",
    "docs/design/semantic_ingestion_architecture.md",
}
_EXPECTED_EVIDENCE = [
    "arrival_order",
    "checkpoint_tail",
    "event_id_order",
    "genesis",
    "mixed_schema",
    "timestamp_order",
    "upcast",
]
_EXPECTED_RULES = {
    "approved_on": "2026-08-02",
    "approved_owner": "product_and_event_model_owner",
    "checkpoint_rule": (
        "validate_complete_batch_position_and_binding_indexes_then_apply_the_same_"
        "fail_closed_algebra_as_genesis"
    ),
    "decision": "reject_non_identical_equal_version_envelopes",
    "duplicate_rule": "only_a_byte_identical_canonical_envelope_is_an_idempotent_duplicate",
    "format": _FORMAT,
    "ordering_authority": "repository_batch_position",
    "recovery_rule": (
        "freeze_the_smallest_proven_isolated_scope_preserve_both_envelopes_and_"
        "require_append_only_operator_repair"
    ),
    "visibility_rule": "reject_before_winner_processed_marker_position_or_partial_projection_visibility",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decision_digest(value: dict[str, object]) -> str:
    body = {key: item for key, item in value.items() if key != "decision_digest"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(_DOMAIN + encoded).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"replay decision JSON contains duplicate key: {key}")
        value[key] = item
    return value


def validate(*, artifact_path: Path, repository_root: Path) -> None:
    try:
        value = json.loads(artifact_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("replay decision is not valid JSON") from exc
    if not isinstance(value, dict) or set(value) != _EXPECTED_KEYS:
        raise ValueError("replay decision keys do not match the closed schema")
    for field, expected in _EXPECTED_RULES.items():
        if value[field] != expected:
            raise ValueError(f"replay decision field has an unsupported value: {field}")
    if value["required_evidence_families"] != _EXPECTED_EVIDENCE:
        raise ValueError("replay decision evidence families are incomplete or unordered")
    documents = value["bound_documents"]
    if not isinstance(documents, dict) or set(documents) != _EXPECTED_DOCUMENTS:
        raise ValueError("replay decision document bindings are incomplete")
    for relative_path, expected_digest in documents.items():
        if not isinstance(relative_path, str) or not isinstance(expected_digest, str):
            raise ValueError("replay decision document binding is malformed")
        if _sha256(repository_root / relative_path) != expected_digest:
            raise ValueError(f"replay decision document digest mismatch: {relative_path}")
    if value["decision_digest"] != _decision_digest(value):
        raise ValueError("replay decision digest mismatch")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    validate(artifact_path=args.artifact, repository_root=args.repository_root)


if __name__ == "__main__":
    main()
