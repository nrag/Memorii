import pytest

from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.models import (
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    ConflictCandidate,
    ConflictResolutionFixture,
    ImplicitRecallFixture,
    LongHorizonDegradationFixture,
    RetrievalFixture,
    RetrievalFixtureMemoryItem,
)
from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope


def _retrieval_fixture(*, corpus_size: int, relevant_ids: list[str]) -> RetrievalFixture:
    corpus = [
        RetrievalFixtureMemoryItem(
            item_id=f"item:{idx}",
            domain=MemoryDomain.TRANSCRIPT,
            text=f"memory text {idx}",
            task_id="task:validator",
        )
        for idx in range(corpus_size)
    ]
    return RetrievalFixture(
        query="query",
        intent=RetrievalIntent.RESUME_TASK,
        scope=RetrievalScope(task_id="task:validator"),
        top_k=3,
        corpus=corpus,
        expected_relevant_ids=relevant_ids,
    )


def test_fixture_validation_fails_on_invalid_category_subtype_combination() -> None:
    with pytest.raises(ValueError):
        BenchmarkScenarioFixture(
            scenario_id="invalid_combo",
            category=BenchmarkScenarioType.ROUTING_CORRECTNESS,
            retrieval=_retrieval_fixture(corpus_size=2, relevant_ids=["item:0"]),
        )


def test_long_horizon_fixture_validation_rejects_undersized_fixture() -> None:
    fixture = BenchmarkScenarioFixture(
        scenario_id="too_small_long_horizon",
        category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
        long_horizon_degradation=LongHorizonDegradationFixture(
            early_retrieval=_retrieval_fixture(corpus_size=4, relevant_ids=["item:0"]),
            delayed_retrieval=_retrieval_fixture(corpus_size=10, relevant_ids=["item:0"]),
            noise_ids=["item:1"],
            delayed_depends_on_early_context=True,
        ),
    )
    with pytest.raises(ValueError):
        normalize_fixtures([fixture])


def test_implicit_recall_fixture_validation_rejects_excessive_lexical_overlap() -> None:
    with pytest.raises(ValueError):
        ImplicitRecallFixture(
            query="hello world",
            top_k=1,
            corpus=[
                RetrievalFixtureMemoryItem(
                    item_id="i:1",
                    domain=MemoryDomain.EPISODIC,
                    text="hello world memory",
                    task_id="task:validator",
                )
            ],
            relevant_ids=["i:1"],
            relevant_memory_texts=["hello world memory"],
            lexical_overlap_score=0.9,
            max_lexical_overlap=0.25,
            expected_domains=[MemoryDomain.EPISODIC],
        )


def test_conflict_fixture_requires_temporal_or_validity_window() -> None:
    with pytest.raises(ValueError):
        ConflictResolutionFixture(
            candidates=[
                ConflictCandidate(
                    candidate_id="c:1",
                    recency_rank=1,
                    validity_status="active",
                )
            ],
            expected_winner_candidate_id="c:1",
        )
