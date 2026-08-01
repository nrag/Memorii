"""Unicode-safe token boundaries used by extraction language capabilities."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from icu import BreakIterator, Locale  # pyright: ignore[reportAttributeAccessIssue]


@dataclass(frozen=True, order=True)
class TokenSpan:
    start: int
    end: int

    def overlaps(self, other: TokenSpan) -> bool:
        return self.start < other.end and other.start < self.end

def normalize_text(value: str) -> str:
    """Return the canonical identity/evidence comparison form."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.replace("’", "'").split())


def word_tokens(value: str, language: str) -> tuple[str, ...]:
    """Tokenize with ICU word boundaries and retain letters/numbers only."""

    normalized = normalize_text(value)
    iterator = BreakIterator.createWordInstance(Locale(language or "und"))
    iterator.setText(normalized)
    tokens: list[str] = []
    start = iterator.first()
    for end in iterator:
        token = normalized[start:end].strip()
        start = end
        if token and any(unicodedata.category(character)[0] in {"L", "N"} for character in token):
            tokens.append(token)
    return tuple(tokens)


def phrase_spans(tokens: Sequence[str], phrase: str, language: str) -> tuple[TokenSpan, ...]:
    phrase_tokens = word_tokens(phrase, language)
    if not phrase_tokens or len(phrase_tokens) > len(tokens):
        return ()
    width = len(phrase_tokens)
    return tuple(
        TokenSpan(start=index, end=index + width)
        for index in range(len(tokens) - width + 1)
        if tuple(tokens[index : index + width]) == phrase_tokens
    )


def interval_contains_any(
    tokens: Sequence[str],
    *,
    start: int,
    end: int,
    phrases: frozenset[tuple[str, ...]],
) -> bool:
    window = tuple(tokens[start:end])
    return any(
        width <= len(window)
        and any(window[index : index + width] == phrase for index in range(len(window) - width + 1))
        for phrase in phrases
        for width in (len(phrase),)
    )


def has_intervening_entity(
    *,
    tokens: Sequence[str],
    language: str,
    interval: TokenSpan,
    selected: tuple[TokenSpan, ...],
    known_entity_names: Sequence[str],
) -> bool:
    for name in known_entity_names:
        for span in phrase_spans(tokens, name, language):
            if span.start < interval.start or span.end > interval.end:
                continue
            if any(span.overlaps(chosen) for chosen in selected):
                continue
            return True
    return False
