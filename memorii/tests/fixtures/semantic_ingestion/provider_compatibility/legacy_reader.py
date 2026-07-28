"""Frozen R22 legacy reader; intentionally imports no Memorii code."""
from __future__ import annotations

import json
from collections.abc import Container
from typing import Any

OUTCOME_FIELDS = ("operation_id", "status", "attempt_count", "failure_code", "retryable", "extraction_status", "provider_attempt_status", "fallback_outcome", "final_extraction_source", "extraction_failure_code", "primary_failure_code", "fallback_provider")
SYNC_FIELDS = ("transcript_ids", "candidate_ids", "blocked_domains", "blocked_reasons", "allowed_candidate_domains", "raw_append_domains", "blocked_commit_domains", "evolution_outcomes")
_STATUS = {"evolution_pending", "evolution_running", "evolution_committed", "evolution_failed"}
_EXTRACTION = {None, "succeeded", "partial", "abstained", "failed"}
_ATTEMPT = {None, "not_attempted", "succeeded", "provider_error", "invalid_json", "schema_error"}
_FALLBACK = {"not_used", "succeeded", "failed"}
_FINAL = {None, "primary", "fallback", "none"}
_FAILURE = {None, "provider_error", "invalid_json", "schema_validation", "output_validation", "unsupported_language"}
_DOMAINS = {"transcript", "semantic", "episodic", "user", "execution", "solver"}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate legacy object key: {key}")
        value[key] = item
    return value


def _object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError, TypeError) as error:
        raise ValueError("legacy payload is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("legacy payload must be an object")
    return value


def _enum(value: Any, allowed: Container[str | None], name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"legacy {name} type changed")
    if value not in allowed:
        raise ValueError(f"legacy {name} changed")


def read_outcome(raw: bytes) -> dict[str, object]:
    value = _object(raw)
    if tuple(value) != OUTCOME_FIELDS:
        raise ValueError("legacy outcome field order changed")
    if not isinstance(value["operation_id"], str) or not isinstance(value["attempt_count"], int) or isinstance(value["attempt_count"], bool) or value["attempt_count"] < 0:
        raise ValueError("legacy outcome required type changed")
    if not isinstance(value["retryable"], bool):
        raise ValueError("legacy retryable type changed")
    for name in ("failure_code", "fallback_provider"):
        if value[name] is not None and not isinstance(value[name], str):
            raise ValueError(f"legacy {name} type changed")
    _enum(value["status"], _STATUS, "outcome status")
    _enum(value["extraction_status"], _EXTRACTION, "extraction status")
    _enum(value["provider_attempt_status"], _ATTEMPT, "attempt status")
    _enum(value["fallback_outcome"], _FALLBACK, "fallback outcome")
    _enum(value["final_extraction_source"], _FINAL, "final source")
    _enum(value["extraction_failure_code"], _FAILURE, "extraction failure")
    _enum(value["primary_failure_code"], _FAILURE, "primary failure")
    committed = value["status"] == "evolution_committed"
    deterministic_abstention = (
        value["extraction_status"] == "abstained"
        and value["provider_attempt_status"] == "not_attempted"
        and value["fallback_outcome"] == "not_used"
        and value["final_extraction_source"] == "none"
        and value["extraction_failure_code"] is None
        and value["primary_failure_code"] is None
    )
    if committed and (
        value["extraction_status"] not in {"succeeded", "abstained"}
        or value["final_extraction_source"] is None
        or (value["final_extraction_source"] == "none" and not deterministic_abstention)
    ):
        raise ValueError("legacy committed lifecycle invariant changed")
    if value["fallback_outcome"] == "succeeded":
        if not value["fallback_provider"] or value["final_extraction_source"] != "fallback":
            raise ValueError("legacy successful fallback invariant changed")
    elif value["fallback_outcome"] == "failed":
        if not value["fallback_provider"] or value["final_extraction_source"] != "none":
            raise ValueError("legacy failed fallback invariant changed")
    elif value["fallback_provider"] is not None:
        raise ValueError("legacy unused fallback invariant changed")
    if committed and value["failure_code"] is not None:
        raise ValueError("legacy committed failure invariant changed")
    if value["status"] == "evolution_failed" and value["failure_code"] is None:
        raise ValueError("legacy failed lifecycle invariant changed")
    return value


def read_sync(raw: bytes) -> dict[str, object]:
    value = _object(raw)
    if tuple(value) != SYNC_FIELDS:
        raise ValueError("legacy sync field order changed")
    for name in ("transcript_ids", "candidate_ids"):
        if not isinstance(value[name], list) or not all(isinstance(item, str) for item in value[name]):
            raise ValueError(f"legacy {name} changed")
    for name in ("blocked_domains", "allowed_candidate_domains", "raw_append_domains", "blocked_commit_domains"):
        if not isinstance(value[name], list) or not all(
            isinstance(item, str) and item in _DOMAINS for item in value[name]
        ):
            raise ValueError(f"legacy {name} changed")
    if not isinstance(value["blocked_reasons"], dict) or not all(isinstance(key, str) and isinstance(reason, str) for key, reason in value["blocked_reasons"].items()):
        raise ValueError("legacy blocked_reasons changed")
    if not isinstance(value["evolution_outcomes"], list):
        raise ValueError("legacy outcome list changed")
    for outcome in value["evolution_outcomes"]:
        if not isinstance(outcome, dict):
            raise ValueError("legacy nested outcome changed")
        read_outcome(json.dumps(outcome, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return value
