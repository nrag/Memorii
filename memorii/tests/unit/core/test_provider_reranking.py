from datetime import UTC, datetime

from memorii.core.provider.bm25 import BM25Scorer
from memorii.core.provider.models import ProviderQueryClass, ProviderStoredRecord
from memorii.core.provider.reranking import ProviderReranker
from memorii.domain.enums import MemoryDomain


def test_bm25_rewards_repeated_important_terms() -> None:
    scorer = BM25Scorer()
    scores = scorer.score(
        query="timeout default config",
        documents={
            "strong": "timeout default timeout default config",
            "weak": "timeout default value",
        },
    )
    assert scores["strong"] > scores["weak"]


def test_bm25_normalization_is_deterministic_and_zero_safe() -> None:
    reranker = ProviderReranker()
    now = datetime(2026, 1, 15, tzinfo=UTC)
    candidates = [
        ProviderStoredRecord(
            memory_id="sem:1",
            domain=MemoryDomain.SEMANTIC,
            text="完全不相关的内容",
            status="committed",
            timestamp=now,
        ),
        ProviderStoredRecord(
            memory_id="tx:1",
            domain=MemoryDomain.TRANSCRIPT,
            text="nada coincide aquí",
            status="committed",
            timestamp=now,
        ),
    ]

    first = reranker.rerank(
        query="timeout default config",
        query_class=ProviderQueryClass.FACT_CONFIG,
        candidates=candidates,
        session_id=None,
        task_id=None,
        user_id=None,
    )
    second = reranker.rerank(
        query="timeout default config",
        query_class=ProviderQueryClass.FACT_CONFIG,
        candidates=list(reversed(candidates)),
        session_id=None,
        task_id=None,
        user_id=None,
    )

    assert all(item.signals.lexical_score == 0.0 for item in first)
    assert [item.record.memory_id for item in first] == [item.record.memory_id for item in second]
