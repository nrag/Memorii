
from memorii.core.benchmark.execution_graph_decision import (
    execution_graph_assertion_passed,
    expected_execution_graph_decision_for_scenario,
    rule_execution_graph_decision_for_scenario,
)
from memorii.core.benchmark.fixture_sets.execution_graph_v1 import load_execution_graph_v1_fixture_set


def test_execution_graph_v1_has_compact_contract_and_discriminative_cases() -> None:
    scenarios = load_execution_graph_v1_fixture_set()

    assert len(scenarios) == 9
    assert sum(1 for scenario in scenarios if scenario.expectation.discriminative) == 5


def test_rule_execution_graph_provider_fails_discriminative_traps() -> None:
    scenarios = [
        scenario
        for scenario in load_execution_graph_v1_fixture_set()
        if scenario.expectation.discriminative
    ]

    assert all(
        execution_graph_assertion_passed(
            scenario=scenario,
            decision=rule_execution_graph_decision_for_scenario(scenario).model_dump(mode="json"),
        )
        is False
        for scenario in scenarios
    )


def test_rule_execution_graph_provider_passes_stable_contract_cases() -> None:
    scenarios = [
        scenario
        for scenario in load_execution_graph_v1_fixture_set()
        if not scenario.expectation.discriminative
    ]

    assert all(
        execution_graph_assertion_passed(
            scenario=scenario,
            decision=rule_execution_graph_decision_for_scenario(scenario).model_dump(mode="json"),
        )
        is True
        for scenario in scenarios
    )


def test_expected_execution_graph_decision_passes_all_cases() -> None:
    assert all(
        execution_graph_assertion_passed(
            scenario=scenario,
            decision=expected_execution_graph_decision_for_scenario(scenario).model_dump(mode="json"),
        )
        is True
        for scenario in load_execution_graph_v1_fixture_set()
    )


def test_execution_graph_assertion_rejects_retrieval_style_node_only_output() -> None:
    scenario = next(
        item
        for item in load_execution_graph_v1_fixture_set()
        if item.scenario_id == "execution_wrong_dependency_direction"
    )
    output = expected_execution_graph_decision_for_scenario(scenario).model_dump(mode="json")
    output["blocked_node_ids"] = []

    assert execution_graph_assertion_passed(scenario=scenario, decision=output) is False


def test_execution_graph_assertion_requires_next_action_tokens() -> None:
    scenario = next(
        item
        for item in load_execution_graph_v1_fixture_set()
        if item.scenario_id == "execution_handoff_continuity"
    )
    scenario = scenario.model_copy(
        update={
            "expectation": scenario.expectation.model_copy(
                update={"require_next_action_tokens": True}
            )
        }
    )
    output = expected_execution_graph_decision_for_scenario(scenario).model_dump(mode="json")
    output["next_action"] = "continue handoff"

    assert execution_graph_assertion_passed(scenario=scenario, decision=output) is False


def test_execution_graph_assertion_allows_suppression_bucket_variation() -> None:
    scenario = next(
        item
        for item in load_execution_graph_v1_fixture_set()
        if item.scenario_id == "execution_handoff_continuity"
    )
    output = expected_execution_graph_decision_for_scenario(scenario).model_dump(mode="json")
    output["stale_node_ids"] = []
    output["blocked_node_ids"] = ["exec:search:triage"]

    assert execution_graph_assertion_passed(scenario=scenario, decision=output) is True


def test_execution_graph_assertion_requires_suppressed_nodes_out_of_frontier() -> None:
    scenario = next(
        item
        for item in load_execution_graph_v1_fixture_set()
        if item.scenario_id == "execution_stale_branch_avoidance"
    )
    output = expected_execution_graph_decision_for_scenario(scenario).model_dump(mode="json")
    output["selected_node_ids"] = ["exec:notify:v1-polling"]
    output["active_frontier_node_ids"] = ["exec:notify:v1-polling"]
    output["stale_node_ids"] = ["exec:notify:v1-polling"]

    assert execution_graph_assertion_passed(scenario=scenario, decision=output) is False
