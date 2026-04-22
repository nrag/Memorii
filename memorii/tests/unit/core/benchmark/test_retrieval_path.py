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
from memorii.core.benchmark.multilingual_tokenization import icu_tokens, mixed_char_ngrams
from memorii.core.benchmark.scenarios import ScenarioExecutor, _retrieval_score
from memorii.core.benchmark.text_normalization import normalize_text
from memorii.domain.enums import CommitStatus, MemoryDomain, TemporalValidityStatus
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope


def test_unicode_normalization_is_deterministic() -> None:
    assert normalize_text("ＡＴＬＡＳ Café") == "atlas café"
    assert normalize_text("ℌ𝔢𝔯𝔪𝔢𝔰") == normalize_text("Hermes")


def test_icu_tokenization_handles_en_es_fr() -> None:
    assert "atlas" in icu_tokens("Atlas uses Postgres now.", "en")
    assert "ahora" in icu_tokens("Atlas ahora usa Postgres.", "es")
    assert "maintenant" in icu_tokens("Atlas utilise maintenant Postgres.", "fr")


def test_char_ngrams_are_deterministic() -> None:
    source = "Atlas-now uses Postgres"
    first = mixed_char_ngrams(source)
    second = mixed_char_ngrams(source)
    assert first == second
    assert any(len(item) in {3, 4, 5} for item in first)


def test_retrieval_score_prefers_multilingual_phrase_and_overlap() -> None:
    query = "¿Qué base de datos usa Atlas ahora?"
    phrase_match = "Atlas ahora usa Postgres para base de datos."
    weak_match = "Atlas ahora usa Redis para caché."
    assert _retrieval_score(query, phrase_match, language="es") > _retrieval_score(query, weak_match, language="es")


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
    reference = datetime(2026, 1, 1, tzinfo=UTC)
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
                    valid_to=reference - timedelta(days=2),
                ),
                RetrievalFixtureMemoryItem(
                    item_id="active",
                    domain=MemoryDomain.EXECUTION,
                    text="deploy policy active prod only",
                    task_id="task-2",
                    validity_status=TemporalValidityStatus.ACTIVE,
                    valid_from=reference - timedelta(days=3),
                    valid_to=reference + timedelta(days=1),
                ),
            ],
            expected_relevant_ids=["active"],
            expected_excluded_ids=["expired"],
        ),
    )

    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.retrieved_ids == ["active"]
    assert observation.scenario_success is True


def test_long_horizon_rank_sensitive_metrics_and_success() -> None:
    corpus = [
        RetrievalFixtureMemoryItem(
            item_id="mem:atlas:db:current",
            domain=MemoryDomain.SEMANTIC,
            language="en",
            text="Atlas now uses Postgres for database.",
            task_id="task-lh",
            role="gold",
        ),
        RetrievalFixtureMemoryItem(
            item_id="tx:atlas:db:old",
            domain=MemoryDomain.TRANSCRIPT,
            language="en",
            text="Previously, Atlas used Redis for database.",
            task_id="task-lh",
            role="hard_distractor",
        ),
        RetrievalFixtureMemoryItem(
            item_id="tx:atlas:cache:redis",
            domain=MemoryDomain.TRANSCRIPT,
            language="en",
            text="Atlas uses Redis for cache.",
            task_id="task-lh",
            role="hard_distractor",
        ),
        *[
            RetrievalFixtureMemoryItem(
                item_id=f"noise-{index}",
                domain=MemoryDomain.TRANSCRIPT,
                text=f"irrelevant chatter {index}",
                task_id="task-lh",
                role="soft_noise",
            )
            for index in range(1, 60)
        ],
    ]
    fixture = BenchmarkScenarioFixture(
        scenario_id="long_horizon_rank_sensitive",
        category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
        long_horizon_degradation=LongHorizonDegradationFixture(
            early_retrieval=RetrievalFixture(
                    query="what database does atlas use now",
                    language="en",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(task_id="task-lh"),
                top_k=3,
                corpus=corpus,
                expected_relevant_ids=["mem:atlas:db:current"],
            ),
            delayed_retrieval=RetrievalFixture(
                    query="what database does atlas use now",
                    language="en",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(task_id="task-lh"),
                top_k=3,
                corpus=corpus,
                expected_relevant_ids=["mem:atlas:db:current"],
                expected_hard_distractor_ids=["tx:atlas:db:old", "tx:atlas:cache:redis"],
                expected_domain_priority=["semantic", "episodic", "transcript"],
            ),
            noise_ids=[f"noise-{index}" for index in range(1, 60)],
        ),
    )

    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.execution_level == ScenarioExecutionLevel.COMPONENT_LEVEL
    assert observation.precision_at_1 == 1.0
    assert observation.gold_rank == 1
    assert observation.hard_distractor_outrank_rate == 0.0
    assert observation.top_k_contamination_rate >= 0.0
    assert observation.scenario_success is True


def test_long_horizon_fails_when_hard_distractor_outranks_gold() -> None:
    corpus = [
        RetrievalFixtureMemoryItem(
            item_id="mem:atlas:db:current",
            domain=MemoryDomain.SEMANTIC,
            language="en",
            text="Atlas now uses Postgres.",
            task_id="task-lh-fail",
        ),
        RetrievalFixtureMemoryItem(
            item_id="tx:atlas:db:old",
            domain=MemoryDomain.TRANSCRIPT,
            language="en",
            text="Atlas now uses Postgres for database and previously Redis.",
            task_id="task-lh-fail",
        ),
        *[
            RetrievalFixtureMemoryItem(
                item_id=f"noise-fail-{index}",
                domain=MemoryDomain.TRANSCRIPT,
                text=f"irrelevant {index}",
                task_id="task-lh-fail",
            )
            for index in range(1, 55)
        ],
    ]

    fixture = BenchmarkScenarioFixture(
        scenario_id="long_horizon_distractor_outranks",
        category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
        long_horizon_degradation=LongHorizonDegradationFixture(
            early_retrieval=RetrievalFixture(
                    query="what database atlas now",
                    language="en",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(task_id="task-lh-fail"),
                top_k=3,
                corpus=corpus,
                expected_relevant_ids=["mem:atlas:db:current"],
            ),
            delayed_retrieval=RetrievalFixture(
                    query="what database atlas now",
                    language="en",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(task_id="task-lh-fail"),
                top_k=2,
                corpus=corpus,
                expected_relevant_ids=["mem:atlas:db:current"],
                expected_hard_distractor_ids=["tx:atlas:db:old"],
            ),
            noise_ids=[f"noise-fail-{index}" for index in range(1, 55)],
        ),
    )
    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.gold_rank is not None
    assert observation.hard_distractor_outrank_rate == 1.0
    assert observation.scenario_success is False
