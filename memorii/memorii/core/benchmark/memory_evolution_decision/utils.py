"""Small deterministic utilities for benchmark decision evaluation."""

from __future__ import annotations

import re
from typing import TypeVar

from memorii.core.benchmark.memory_evolution_decision.contracts import MemoryEvolutionCheckpoint

BucketT = TypeVar("BucketT", bound=str)


def dedupe_string_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result



def extract_shallow_answer(content: str) -> str:
    for separator in [" is ", " = ", ":"]:
        if separator in content:
            return content.split(separator, 1)[1].strip().rstrip(".")
    return content.strip().rstrip(".")


def normalize_decision_text(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())


def ordered_missing(expected_ids: list[str], actual_ids: set[str]) -> list[str]:
    return [memory_id for memory_id in expected_ids if memory_id not in actual_ids]


def ordered_extra(actual_ids: list[str], expected_ids: set[str]) -> list[str]:
    return [memory_id for memory_id in actual_ids if memory_id not in expected_ids]


def is_belief_memory_id(memory_id: str, *, checkpoint: MemoryEvolutionCheckpoint) -> bool:
    return (
        memory_id.startswith("belief:")
        or memory_id in checkpoint.expected_belief_ranking
        or memory_id in checkpoint.expected_belief_scores
    )


def dedupe_preserving_order(values: list[BucketT]) -> list[BucketT]:
    seen: set[BucketT] = set()
    result: list[BucketT] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def answer_matches_expected(*, actual: str | None, expected: str, aliases: list[str] | None = None) -> bool:
    actual_norm = normalize_decision_text(actual)
    candidates = [expected, *(aliases or [])]
    for candidate in candidates:
        expected_norm = normalize_decision_text(candidate)
        if actual_norm == expected_norm:
            return True
        actual_tokens = set(actual_norm.split())
        expected_tokens = set(expected_norm.split())
        if not expected_tokens:
            return True
        expected_negated = bool({"not", "never"} & expected_tokens)
        if expected_negated and not _contains_negation(actual_norm):
            continue
        if not expected_negated and _contains_local_negation(
            actual_norm=actual_norm,
            expected_tokens=expected_tokens,
        ):
            continue
        if expected_tokens.issubset(actual_tokens):
            return True
        if _answer_token_stems(expected_tokens).issubset(_answer_token_stems(actual_tokens)):
            return True
        if "no" in expected_tokens and ({"no", "none", "neither", "zero"} & actual_tokens):
            return (expected_tokens - {"no"}).issubset(actual_tokens)
    return False


def _contains_negation(text: str) -> bool:
    return bool({"not", "never"} & set(text.split()))


def _contains_local_negation(*, actual_norm: str, expected_tokens: set[str]) -> bool:
    """Reject a match only when negation is near a required concept.

    Explanatory answers can contain a separate negative fact, such as
    "Nikhil is not included in the active Atlas facts", after stating the
    positive answer. Document-wide negation detection incorrectly rejects
    those answers. A short token window still catches direct contradictions
    such as "Alice is not the owner".
    """
    tokens = actual_norm.split()
    required_tokens = expected_tokens - {"not", "never", "no"}
    for index, token in enumerate(tokens):
        if token not in required_tokens:
            continue
        window = tokens[max(0, index - 3) : index + 1]
        if {"not", "never"} & set(window):
            return True
    return False


def _answer_token_stems(tokens: set[str]) -> set[str]:
    stems: set[str] = set()
    for token in tokens:
        if len(token) > 5 and token.endswith("ing"):
            stems.add(token[:-3])
        elif len(token) > 4 and (token.endswith("ed") or token.endswith("es")):
            stems.add(token[:-2])
        elif len(token) > 3 and token.endswith("s"):
            stems.add(token[:-1])
        else:
            stems.add(token)
    return stems
