from datetime import UTC, datetime, timedelta

from memorii.core.benchmark.models import (
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    BenchmarkSystem,
    LongHorizonDegradationFixture,
    RetrievalFixture,
    RetrievalFixtureMemoryItem,
    ScenarioExecutionLevel,
)
from memorii.core.benchmark.scenarios import ScenarioExecutor, _normalize_tokens, _retrieval_score
from memorii.domain.enums import CommitStatus, MemoryDomain, TemporalValidityStatus
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope


def test_token_normalization_handles_punctuation_consistently() -> None:
    assert _normalize_tokens("Error: timeout, retry!") == ["error", "timeout", "retry"]
    assert _normalize_tokens("kernel-panics...again?") == ["kernel", "panics", "again"]


def test_retrieval_score_prefers_phrase_and_normalized_match() -> None:
    query = "cache invalidation strategy"
    phrase_match = "We need a cache invalidation strategy for stale entries."
    weak_match = "cache entries can be stale from many causes"
    assert _retrieval_score(query, phrase_match) > _retrieval_score(query, weak_match)


def test_benchmark_retrieval_excludes_candidate_items_by_default() -> None:
    fixture = BenchmarkScenarioFixture(
        scenario_id="retrieval_exclude_candidate",
        category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
        retrieval=RetrievalFixture(
            query="connection timeout investigation",
            intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
            scope=RetrievalScope(task_id="task-1"),
            top_k=3,
            corpus=[
                RetrievalFixtureMemoryItem(
                    item_id="candidate-1",
                    domain=MemoryDomain.SEMANTIC,
                    text="connection timeout root cause",
                    task_id="task-1",
                    status=CommitStatus.CANDIDATE,
                ),
                RetrievalFixtureMemoryItem(
                    item_id="committed-1",
                    domain=MemoryDomain.SEMANTIC,
                    text="connection timeout root cause",
                    task_id="task-1",
                    status=CommitStatus.COMMITTED,
                ),
            ],
            expected_relevant_ids=["committed-1"],
            expected_excluded_ids=["candidate-1"],
        ),
    )

    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.retrieved_ids == ["committed-1"]
    assert observation.scenario_success is True


def test_benchmark_retrieval_excludes_invalid_or_expired_for_active_intents() -> None:
    now = datetime.now(UTC)
    fixture = BenchmarkScenarioFixture(
        scenario_id="retrieval_exclude_invalid",
        category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
        retrieval=RetrievalFixture(
            query="deploy policy",
            intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
            scope=RetrievalScope(task_id="task-2"),
            top_k=3,
            corpus=[
                RetrievalFixtureMemoryItem(
                    item_id="expired",
                    domain=MemoryDomain.EXECUTION,
                    text="deploy policy active prod only",
                    task_id="task-2",
                    validity_status=TemporalValidityStatus.EXPIRED,
                    valid_to=now - timedelta(days=2),
                ),
                RetrievalFixtureMemoryItem(
                    item_id="active",
                    domain=MemoryDomain.EXECUTION,
                    text="deploy policy active prod only",
                    task_id="task-2",
                    validity_status=TemporalValidityStatus.ACTIVE,
                    valid_from=now - timedelta(days=3),
                    valid_to=now + timedelta(days=1),
                ),
            ],
            expected_relevant_ids=["active"],
            expected_excluded_ids=["expired"],
        ),
    )

    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.retrieved_ids == ["active"]
    assert observation.scenario_success is True


def test_long_horizon_success_tracks_recall_independently_from_noise() -> None:
    low_noise = [f"noise-{i}" for i in range(30)]
    corpus = [
        RetrievalFixtureMemoryItem(
            item_id="relevant-delayed",
            domain=MemoryDomain.EXECUTION,
            text="critical resume token",
            task_id="task-lh",
        ),
        *[
                RetrievalFixtureMemoryItem(
                    item_id=item_id,
                    domain=MemoryDomain.EXECUTION,
                text="noise token",
                task_id="task-lh",
            )
            for item_id in low_noise
        ],
    ]
    fixture = BenchmarkScenarioFixture(
        scenario_id="long_horizon_recall_first",
        category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
        long_horizon_degradation=LongHorizonDegradationFixture(
            early_retrieval=RetrievalFixture(
                query="critical resume token",
                intent=RetrievalIntent.RESUME_TASK,
                scope=RetrievalScope(task_id="task-lh"),
                top_k=1,
                corpus=corpus,
                expected_relevant_ids=["relevant-delayed"],
            ),
            delayed_retrieval=RetrievalFixture(
                query="critical resume token",
                intent=RetrievalIntent.RESUME_TASK,
                scope=RetrievalScope(task_id="task-lh"),
                top_k=1,
                corpus=corpus,
                expected_relevant_ids=["relevant-delayed"],
            ),
            noise_ids=low_noise,
        ),
    )

    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.execution_level == ScenarioExecutionLevel.COMPONENT_LEVEL
    assert observation.resume_correctness_under_scale is True
    assert observation.noise_resilience is not None
    assert observation.scenario_success is True
