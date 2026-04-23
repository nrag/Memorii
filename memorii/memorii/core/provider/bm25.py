"""Deterministic in-repo Okapi BM25 scoring for provider reranking."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import log
import string
import unicodedata

try:
    from icu import BreakIterator, Locale

    _ICU_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without PyICU
    BreakIterator = None  # type: ignore[assignment]
    Locale = None  # type: ignore[assignment]
    _ICU_AVAILABLE = False

_PUNCT_CHARS = set(string.punctuation)


@dataclass(frozen=True)
class BM25Config:
    k1: float = 1.2
    b: float = 0.75
    language: str = "und"


class BM25Scorer:
    """Compute deterministic BM25 scores over a candidate pool."""

    def __init__(self, *, config: BM25Config | None = None) -> None:
        self._config = config or BM25Config()

    def score(self, *, query: str, documents: dict[str, str]) -> dict[str, float]:
        if not documents:
            return {}

        tokenized_docs = {
            doc_id: _tokens(text, language=self._config.language)
            for doc_id, text in documents.items()
        }
        doc_lengths = {doc_id: len(tokens) for doc_id, tokens in tokenized_docs.items()}
        total_documents = len(tokenized_docs)
        avg_doc_len = sum(doc_lengths.values()) / total_documents if total_documents else 0.0

        doc_frequencies = _document_frequencies(tokenized_docs)
        query_term_frequencies = Counter(_tokens(query, language=self._config.language))
        if not query_term_frequencies:
            return {doc_id: 0.0 for doc_id in documents}

        idf_by_term = {
            term: log(1.0 + ((total_documents - frequency + 0.5) / (frequency + 0.5)))
            for term, frequency in doc_frequencies.items()
        }

        scores: dict[str, float] = {}
        for doc_id, tokens in tokenized_docs.items():
            term_frequencies = Counter(tokens)
            scores[doc_id] = _bm25_score(
                query_terms=query_term_frequencies,
                term_frequencies=term_frequencies,
                idf_by_term=idf_by_term,
                doc_length=doc_lengths[doc_id],
                avg_doc_length=avg_doc_len,
                k1=self._config.k1,
                b=self._config.b,
            )
        return scores


def _document_frequencies(tokenized_docs: dict[str, list[str]]) -> Counter[str]:
    frequencies: Counter[str] = Counter()
    for tokens in tokenized_docs.values():
        frequencies.update(set(tokens))
    return frequencies


def _bm25_score(
    *,
    query_terms: Counter[str],
    term_frequencies: Counter[str],
    idf_by_term: dict[str, float],
    doc_length: int,
    avg_doc_length: float,
    k1: float,
    b: float,
) -> float:
    if avg_doc_length <= 0:
        return 0.0

    score = 0.0
    length_norm = 1.0 - b + b * (doc_length / avg_doc_length)
    for term, query_tf in query_terms.items():
        frequency = term_frequencies.get(term, 0)
        if frequency == 0:
            continue
        idf = idf_by_term.get(term)
        if idf is None:
            continue
        numerator = frequency * (k1 + 1.0)
        denominator = frequency + (k1 * length_norm)
        if denominator == 0.0:
            continue
        score += float(query_tf) * idf * (numerator / denominator)
    return score


def _tokens(text: str, *, language: str) -> list[str]:
    normalized = _normalize_text(text)
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


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


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


def _is_punctuation(token: str) -> bool:
    return all(
        (character in _PUNCT_CHARS) or unicodedata.category(character).startswith("P")
        for character in token
    )
