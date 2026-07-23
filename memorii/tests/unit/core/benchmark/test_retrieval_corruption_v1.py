from memorii.core.benchmark.fixture_sets.retrieval_corruption_v1 import load_retrieval_corruption_v1_fixture_set
from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.metrics import aggregate_metrics, compute_metrics
from memorii.core.benchmark.models import BenchmarkSystem
from memorii.core.benchmark.retrieval_relevance_decision import (
    expected_retrieval_relevance_decision_for_fixture,
    retrieval_relevance_assertion_passed,
    rule_retrieval_relevance_decision_for_fixture,
)
from memorii.core.benchmark.scenarios import ScenarioExecutor


def test_retrieval_corruption_v1_has_focused_hard_distractor_cases() -> None:
    fixtures = normalize_fixtures(load_retrieval_corruption_v1_fixture_set())

    assert len(fixtures) == 11
    assert all(fixture.retrieval is not None for fixture in fixtures)
    assert all(fixture.retrieval.expected_hard_distractor_ids for fixture in fixtures if fixture.retrieval)


def test_retrieval_corruption_v1_memorii_passes_rank_sensitive_contract() -> None:
    fixtures = normalize_fixtures(load_retrieval_corruption_v1_fixture_set())
    executor = ScenarioExecutor()

    observations = [
        executor.run(fixture=fixture, system=BenchmarkSystem.MEMORII)
        for fixture in fixtures
    ]

    assert all(observation.scenario_success is True for observation in observations)
    positive_observations = [observation for observation in observations if observation.relevant_ids]
    assert all(observation.precision_at_1 == 1.0 for observation in positive_observations)
    assert all(observation.hard_distractor_outrank_rate == 0.0 for observation in positive_observations)
    assert all(compute_metrics(observation).scenario_success_rate == 1.0 for observation in observations)


def test_retrieval_corruption_v1_aggregate_metrics_include_corruption_axes() -> None:
    fixtures = normalize_fixtures(load_retrieval_corruption_v1_fixture_set())
    executor = ScenarioExecutor()
    observations = [
        executor.run(fixture=fixture, system=BenchmarkSystem.MEMORII)
        for fixture in fixtures
    ]

    aggregate = aggregate_metrics(observations)

    assert aggregate.scenario_success_rate == 1.0
    assert aggregate.precision_at_1 == 1.0
    assert aggregate.hard_distractor_outrank_rate == 0.0
    assert aggregate.false_positive_retrieval_rate is not None


def test_retrieval_corruption_v1_discriminates_memorii_from_baselines() -> None:
    report = BenchmarkHarness().run(fixtures=load_retrieval_corruption_v1_fixture_set())

    success_by_system = {
        system: metrics.scenario_success_rate
        for system, metrics in report.aggregate_by_system.items()
    }
    hard_distractor_by_system = {
        system: metrics.hard_distractor_outrank_rate
        for system, metrics in report.aggregate_by_system.items()
    }

    assert success_by_system[BenchmarkSystem.MEMORII] == 1.0
    assert 0.0 < success_by_system[BenchmarkSystem.FLAT_RETRIEVAL_BASELINE] < 1.0
    assert 0.0 < success_by_system[BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE] < 1.0
    assert success_by_system[BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE] < 0.2
    assert hard_distractor_by_system[BenchmarkSystem.MEMORII] == 0.0
    assert hard_distractor_by_system[BenchmarkSystem.FLAT_RETRIEVAL_BASELINE] > 0.0
    assert hard_distractor_by_system[BenchmarkSystem.NO_SOLVER_GRAPH_BASELINE] > 0.0
    assert hard_distractor_by_system[BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE] > 0.8


def test_rule_retrieval_relevance_decision_fails_semantic_traps() -> None:
    fixtures = normalize_fixtures(load_retrieval_corruption_v1_fixture_set())

    failed = [
        fixture.scenario_id
        for fixture in fixtures
        if not retrieval_relevance_assertion_passed(
            fixture=fixture,
            decision=rule_retrieval_relevance_decision_for_fixture(fixture).model_dump(mode="json"),
        )
    ]

    assert set(failed) == {
        "retrieval_corruption_candidate_suppression",
        "retrieval_corruption_current_beats_invalidated",
        "retrieval_corruption_no_reliable_current_answer",
        "retrieval_corruption_solver_frontier_beats_old_fix",
        "retrieval_corruption_task_scope_boundary",
    }


def test_expected_retrieval_relevance_decision_passes_all_cases() -> None:
    fixtures = normalize_fixtures(load_retrieval_corruption_v1_fixture_set())

    assert all(
        retrieval_relevance_assertion_passed(
            fixture=fixture,
            decision=expected_retrieval_relevance_decision_for_fixture(fixture).model_dump(mode="json"),
        )
        for fixture in fixtures
    )
