"""Deterministic multilingual tokenization and lexical helpers."""

from __future__ import annotations

import string

from icu import BreakIterator, Locale
from sklearn.feature_extraction.text import TfidfVectorizer

from memorii.core.benchmark.text_normalization import normalize_text

_PUNCT_CHARS = set(string.punctuation)


def icu_tokens(text: str, language: str) -> list[str]:
    """Tokenize text with ICU word boundaries for multilingual safety."""
    normalized = normalize_text(text)
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
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=ngram_range, lowercase=False, norm="l2")
    matrix = vectorizer.fit_transform([normalize_text(source), normalize_text(target)])
    return float((matrix[0] @ matrix[1].T).toarray()[0][0])


def _is_punctuation(token: str) -> bool:
    return all((character in _PUNCT_CHARS) for character in token)
