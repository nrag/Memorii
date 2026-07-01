from memorii.core.benchmark.memory_evolution_decision import (
    expected_memory_evolution_decision_for_checkpoint,
    memory_evolution_assertion_passed,
    rule_memory_evolution_decision_for_checkpoint,
)
from tests.fixtures.benchmarks.memory_evolution_v1 import load_memory_evolution_v1_fixture_set


def test_memory_evolution_v1_has_ten_episode_chain_scenarios() -> None:
    scenarios = load_memory_evolution_v1_fixture_set()

    assert len(scenarios) == 10
    assert sum(1 for scenario in scenarios if scenario.discriminative) >= 5
    assert all(len(scenario.events) >= 2 for scenario in scenarios)
    assert all(scenario.checkpoints for scenario in scenarios)


def test_memory_evolution_v1_checkpoint_references_are_event_derived() -> None:
    for scenario in load_memory_evolution_v1_fixture_set():
        event_ids = {event.event_id for event in scenario.events}
        for checkpoint in scenario.checkpoints:
            referenced = {
                *checkpoint.expected_retrieval_ids,
                *checkpoint.expected_citation_ids,
                *checkpoint.expected_excluded_memory_ids,
                *checkpoint.expected_active_memory_ids,
                *checkpoint.expected_inactive_memory_ids,
                *checkpoint.expected_archived_memory_ids,
                *checkpoint.expected_belief_ranking,
                *checkpoint.expected_belief_scores.keys(),
            }
            assert referenced.issubset(event_ids)


def test_expected_memory_evolution_decisions_pass_all_checkpoints() -> None:
    for scenario in load_memory_evolution_v1_fixture_set():
        for checkpoint in scenario.checkpoints:
            assert memory_evolution_assertion_passed(
                scenario=scenario,
                checkpoint=checkpoint,
                decision=expected_memory_evolution_decision_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                ).model_dump(mode="json"),
            )


def test_rule_memory_evolution_provider_fails_semantic_traps() -> None:
    failures = 0
    for scenario in load_memory_evolution_v1_fixture_set():
        if not scenario.discriminative:
            continue
        scenario_passed = all(
            memory_evolution_assertion_passed(
                scenario=scenario,
                checkpoint=checkpoint,
                decision=rule_memory_evolution_decision_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                ).model_dump(mode="json"),
            )
            for checkpoint in scenario.checkpoints
        )
        if not scenario_passed:
            failures += 1

    assert failures >= 5


def test_memory_evolution_assertion_requires_current_and_historical_truth() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_current_vs_historical_truth"
    )
    historical = next(
        checkpoint
        for checkpoint in scenario.checkpoints
        if checkpoint.checkpoint_id == "checkpoint:atlas-owner-january"
    )
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=historical,
    ).model_dump(mode="json")
    output["selected_memory_ids"] = ["mem:atlas-owner-bob-current"]
    output["citation_memory_ids"] = ["mem:atlas-owner-bob-current"]
    output["answer"] = "Bob"

    assert memory_evolution_assertion_passed(
        scenario=scenario,
        checkpoint=historical,
        decision=output,
    ) is False


def test_memory_evolution_assertion_requires_wrong_entity_precision() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_wrong_entity_high_similarity"
    )
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["selected_memory_ids"] = ["mem:orion-billing-approver-nikhil"]
    output["citation_memory_ids"] = ["mem:orion-billing-approver-nikhil"]
    output["answer"] = "Nikhil"

    assert memory_evolution_assertion_passed(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    ) is False


def test_memory_evolution_assertion_requires_belief_degradation() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_belief_dependency_degradation"
    )
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["belief_scores"] = [
        {"memory_id": "belief:a-cache-miss-root", "belief": 0.8},
        {"memory_id": "belief:b-worker-retry-backed-by-a", "belief": 0.7},
        {"memory_id": "belief:c-customer-latency-backed-by-b", "belief": 0.6},
    ]

    assert memory_evolution_assertion_passed(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    ) is False


def test_memory_evolution_assertion_suppresses_abandoned_branch() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_abandoned_then_resumed_work"
    )
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["selected_memory_ids"] = ["exec:approach-a-started"]
    output["citation_memory_ids"] = ["exec:approach-a-started"]
    output["next_action"] = "continue approach A"

    assert memory_evolution_assertion_passed(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    ) is False
