"""Deterministic provider-side retrieval reranking."""

from __future__ import annotations

from dataclasses import dataclass

from memorii.core.provider.bm25 import BM25Scorer
from memorii.core.provider.models import ProviderQueryClass, ProviderStoredRecord
from memorii.domain.enums import MemoryDomain


@dataclass(frozen=True)
class ProviderRerankWeights:
    domain: float
    lexical: float
    recency: float
    scope: float


@dataclass(frozen=True)
class ProviderRerankSignals:
    domain_prior_score: float
    lexical_score: float
    recency_score: float
    scope_score: float


@dataclass(frozen=True)
class ProviderRerankResult:
    record: ProviderStoredRecord
    final_score: float
    signals: ProviderRerankSignals


QUERY_CLASS_WEIGHTS: dict[ProviderQueryClass, ProviderRerankWeights] = {
    ProviderQueryClass.PREFERENCE_PROFILE: ProviderRerankWeights(domain=0.45, lexical=0.2, recency=0.1, scope=0.25),
    ProviderQueryClass.FACT_CONFIG: ProviderRerankWeights(domain=0.35, lexical=0.35, recency=0.1, scope=0.2),
    ProviderQueryClass.EVENT_HISTORY: ProviderRerankWeights(domain=0.6, lexical=0.2, recency=0.1, scope=0.1),
    ProviderQueryClass.GENERAL_CONTINUITY: ProviderRerankWeights(domain=0.25, lexical=0.2, recency=0.4, scope=0.15),
}

_DOMAIN_PRIORS: dict[ProviderQueryClass, dict[MemoryDomain, float]] = {
    ProviderQueryClass.PREFERENCE_PROFILE: {
        MemoryDomain.USER: 1.0,
        MemoryDomain.SEMANTIC: 0.75,
        MemoryDomain.EPISODIC: 0.55,
        MemoryDomain.TRANSCRIPT: 0.45,
    },
    ProviderQueryClass.FACT_CONFIG: {
        MemoryDomain.SEMANTIC: 1.0,
        MemoryDomain.USER: 0.7,
        MemoryDomain.EPISODIC: 0.5,
        MemoryDomain.TRANSCRIPT: 0.35,
    },
    ProviderQueryClass.EVENT_HISTORY: {
        MemoryDomain.EPISODIC: 1.0,
        MemoryDomain.TRANSCRIPT: 0.75,
        MemoryDomain.SEMANTIC: 0.45,
        MemoryDomain.USER: 0.35,
    },
    ProviderQueryClass.GENERAL_CONTINUITY: {
        MemoryDomain.TRANSCRIPT: 1.0,
        MemoryDomain.EPISODIC: 0.8,
        MemoryDomain.SEMANTIC: 0.6,
        MemoryDomain.USER: 0.55,
    },
}


class ProviderReranker:
    def __init__(self) -> None:
        self._bm25 = BM25Scorer()

    def rerank(
        self,
        *,
        query: str,
        query_class: ProviderQueryClass,
        candidates: list[ProviderStoredRecord],
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
    ) -> list[ProviderRerankResult]:
        if not candidates:
            return []

        recency_scores = _relative_recency_scores(candidates)
        lexical_scores = self._normalized_lexical_scores(query=query, candidates=candidates)
        weights = QUERY_CLASS_WEIGHTS[query_class]

        scored: list[ProviderRerankResult] = []
        for candidate in candidates:
            signals = ProviderRerankSignals(
                domain_prior_score=_domain_prior(query_class=query_class, domain=candidate.domain),
                lexical_score=lexical_scores[candidate.memory_id],
                recency_score=recency_scores[candidate.memory_id],
                scope_score=_scope_closeness(
                    record=candidate,
                    session_id=session_id,
                    task_id=task_id,
                    user_id=user_id,
                ),
            )
            final_score = (
                weights.domain * signals.domain_prior_score
                + weights.lexical * signals.lexical_score
                + weights.recency * signals.recency_score
                + weights.scope * signals.scope_score
            )
            scored.append(ProviderRerankResult(record=candidate, final_score=final_score, signals=signals))

        return sorted(scored, key=lambda item: (-item.final_score, item.record.memory_id))

    def _normalized_lexical_scores(self, *, query: str, candidates: list[ProviderStoredRecord]) -> dict[str, float]:
        raw_scores = self._bm25.score(
            query=query,
            documents={candidate.memory_id: candidate.text for candidate in candidates},
        )
        max_score = max(raw_scores.values()) if raw_scores else 0.0
        if max_score == 0.0:
            return {candidate.memory_id: 0.0 for candidate in candidates}
        return {
            candidate.memory_id: raw_scores.get(candidate.memory_id, 0.0) / max_score
            for candidate in candidates
        }


def _domain_prior(*, query_class: ProviderQueryClass, domain: MemoryDomain) -> float:
    return _DOMAIN_PRIORS[query_class].get(domain, 0.0)


def _relative_recency_scores(candidates: list[ProviderStoredRecord]) -> dict[str, float]:
    ordered = sorted(candidates, key=lambda item: (item.timestamp, item.memory_id))
    if len(ordered) == 1:
        return {ordered[0].memory_id: 1.0}
    denominator = len(ordered) - 1
    scores: dict[str, float] = {}
    for idx, item in enumerate(ordered):
        scores[item.memory_id] = idx / denominator
    return scores


def _scope_closeness(
    *,
    record: ProviderStoredRecord,
    session_id: str | None,
    task_id: str | None,
    user_id: str | None,
) -> float:
    requested_values = {"session_id": session_id, "task_id": task_id, "user_id": user_id}
    weights = {"session_id": 0.2, "task_id": 0.5, "user_id": 0.3}

    requested_total = sum(weight for key, weight in weights.items() if requested_values[key] is not None)
    if requested_total == 0:
        return 0.5

    matched = 0.0
    for key, weight in weights.items():
        requested = requested_values[key]
        if requested is None:
            continue
        if getattr(record, key) == requested:
            matched += weight

    if requested_total == 0:
        return 0.5
    normalized = matched / requested_total
    return max(0.0, min(1.0, normalized))
