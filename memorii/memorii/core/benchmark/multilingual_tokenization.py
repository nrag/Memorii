"""Deterministic multilingual tokenization and lexical helpers."""

from __future__ import annotations

import string
import unicodedata
from collections import Counter
from math import sqrt

try:
    from icu import BreakIterator, Locale

    _ICU_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised indirectly in CI environments without PyICU
    BreakIterator = None  # type: ignore[assignment]
    Locale = None  # type: ignore[assignment]
    _ICU_AVAILABLE = False

from memorii.core.benchmark.text_normalization import normalize_text

_PUNCT_CHARS = set(string.punctuation)


def icu_tokens(text: str, language: str) -> list[str]:
    """Tokenize text with ICU word boundaries for multilingual safety."""
    normalized = normalize_text(text)
    if not _ICU_AVAILABLE:
        return _fallback_tokens(normalized)

    locale = Locale(language or "und")
    iterator = BreakIterator.createWordInstance(locale)
    iterator.setText(normalized)

    tokens: list[str] = []
    start = iterator.first()
    for end in iterator:
        token = normalized[start:end].strip()
        start = end
        if not token:
            continue
        if _is_punctuation(token):
            continue
        tokens.append(token)
    return tokens


def _fallback_tokens(normalized: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isspace() or category.startswith(("P", "S")):
            token = "".join(current).strip()
            if token and not _is_punctuation(token):
                tokens.append(token)
            current = []
            continue
        current.append(character)
    token = "".join(current).strip()
    if token and not _is_punctuation(token):
        tokens.append(token)
    return tokens


def mixed_char_ngrams(text: str, n_values: tuple[int, ...] = (3, 4, 5)) -> set[str]:
    """Extract deterministic mixed-size character n-grams from normalized text."""
    normalized = normalize_text(text)
    compact = " ".join(normalized.split())
    ngrams: set[str] = set()
    for n in n_values:
        if n <= 0:
            continue
        if len(compact) < n:
            continue
        for index in range(len(compact) - n + 1):
            ngrams.add(compact[index : index + n])
    return ngrams


def tfidf_char_ngram_similarity(
    source: str,
    target: str,
    *,
    ngram_range: tuple[int, int] = (3, 5),
) -> float:
    """Compute deterministic character n-gram cosine similarity."""
    source_vec = _char_ngram_tf(normalize_text(source), ngram_range=ngram_range)
    target_vec = _char_ngram_tf(normalize_text(target), ngram_range=ngram_range)
    if not source_vec or not target_vec:
        return 0.0
    shared = set(source_vec) & set(target_vec)
    numerator = float(sum(source_vec[key] * target_vec[key] for key in shared))
    source_norm = sqrt(sum(value * value for value in source_vec.values()))
    target_norm = sqrt(sum(value * value for value in target_vec.values()))
    if source_norm == 0.0 or target_norm == 0.0:
        return 0.0
    return numerator / (source_norm * target_norm)


def _char_ngram_tf(text: str, *, ngram_range: tuple[int, int]) -> Counter[str]:
    minimum, maximum = ngram_range
    compact = " ".join(text.split())
    counts: Counter[str] = Counter()
    for n in range(max(1, minimum), maximum + 1):
        if len(compact) < n:
            continue
        for index in range(len(compact) - n + 1):
            counts[compact[index : index + n]] += 1
    return counts


def _is_punctuation(token: str) -> bool:
    return all(
        (character in _PUNCT_CHARS) or unicodedata.category(character).startswith("P")
        for character in token
    )
