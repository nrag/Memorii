"""Canonical prompt-field visibility policy.

Model-visible payload types should exclude oracle and secret fields by
construction. These normalized key sets are the defense-in-depth boundary for
arbitrary nested mappings supplied by integrations.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from math import isfinite
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonInput: TypeAlias = JsonScalar | Mapping[str, "JsonInput"] | list["JsonInput"] | tuple["JsonInput", ...]


def normalize_sensitive_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


ORACLE_INPUT_FIELDS = frozenset(
    normalize_sensitive_key(value)
    for value in {
        "expected_answer",
        "expected_action_ids",
        "expected_active_memory_ids",
        "expected_inactive_memory_ids",
        "expected_archived_memory_ids",
        "expected_checkpoint_active_record_ids",
        "expected_checkpoint_retained_record_ids",
        "expected_checkpoint_superseded_record_ids",
        "expected_belief_ranking",
        "expected_belief_scores",
        "expected_citation_ids",
        "expected_claim_ids",
        "expected_execution_citation_event_ids",
        "expected_execution_claim_ids",
        "expected_execution_entity_ids",
        "expected_entity_ids",
        "expected_excluded_claim_ids",
        "expected_excluded_entity_ids",
        "expected_excluded_memory_ids",
        "expected_excluded_relation_ids",
        "expected_next_action",
        "expected_retrieval_ids",
        "expected_relation_ids",
        "expected_stage_path",
        "expected_uncertain_ids",
        "excluded_ids",
        "hidden_distractor_ids",
        "hidden_graph_items",
        "hidden_ids",
        "judge_outputs",
        "judge_votes",
        "oracle_checkpoint",
        "oracle_ids",
        "required_judge_ids",
    }
)

SECRET_KEYS = frozenset(
    normalize_sensitive_key(value)
    for value in {"api_key", "apikey", "token", "password", "secret", "authorization", "cookie"}
)


def sanitize_json_value(
    value: object,
    *,
    remove_fields: frozenset[str] = frozenset(),
    redact_fields: frozenset[str] = frozenset(),
    _path: str = "$",
    _ancestors: frozenset[int] = frozenset(),
) -> JsonValue:
    """Return a detached JSON value under one canonical visibility policy."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError(f"{_path} contains a non-finite JSON number")
        return value
    if isinstance(value, (Mapping, list, tuple)):
        identity = id(value)
        if identity in _ancestors:
            raise ValueError(f"{_path} contains a cyclic JSON value")
        ancestors = _ancestors | {identity}
        if isinstance(value, Mapping):
            sanitized: dict[str, JsonValue] = {}
            for key, nested in value.items():
                if not isinstance(key, str):
                    raise TypeError(f"{_path} contains a non-string JSON object key")
                normalized_key = normalize_sensitive_key(key)
                if normalized_key in remove_fields:
                    continue
                sanitized[key] = (
                    "[REDACTED]"
                    if normalized_key in redact_fields
                    else sanitize_json_value(
                        nested,
                        remove_fields=remove_fields,
                        redact_fields=redact_fields,
                        _path=f"{_path}.{key}",
                        _ancestors=ancestors,
                    )
                )
            return sanitized
        return [
            sanitize_json_value(
                item,
                remove_fields=remove_fields,
                redact_fields=redact_fields,
                _path=f"{_path}[{index}]",
                _ancestors=ancestors,
            )
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{_path} contains unsupported non-JSON value {type(value).__name__}")


def redact_sensitive_value(value: object) -> JsonValue:
    """Sanitize audit data using the same boundary as model-visible prompts."""

    return sanitize_json_value(value, redact_fields=SECRET_KEYS | ORACLE_INPUT_FIELDS)
