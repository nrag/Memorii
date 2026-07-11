from __future__ import annotations

import pytest

from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    claim_by_role,
    entity_by_role,
    generate_scenario_by_family,
    relation_by_role,
)


def test_generate_scenario_by_family_selects_named_family() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )

    assert scenario.family == "entity_split"


def test_generate_scenario_by_family_reports_available_families() -> None:
    with pytest.raises(AssertionError, match="Available"):
        generate_scenario_by_family(
            profile="smoke",
            family="missing_family",
            seed=7,
        )


def test_checkpoint_by_type_selects_named_checkpoint_type() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )

    assert checkpoint_by_type(scenario, "current_truth").checkpoint_type == "current_truth"
    assert checkpoint_by_type(scenario, "historical_truth").checkpoint_type == "historical_truth"


def test_checkpoint_by_type_reports_available_checkpoint_types() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )

    with pytest.raises(AssertionError, match="Available"):
        checkpoint_by_type(scenario, "execution_continuation")


def test_checkpoint_by_type_rejects_negative_index() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )

    with pytest.raises(AssertionError, match="index -1"):
        checkpoint_by_type(scenario, "current_truth", index=-1)


def test_role_helpers_select_items_by_evaluation_role() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )

    assert "entity_reconstruction" in entity_by_role(scenario, "entity_reconstruction").evaluation_roles
    assert "entity_disambiguation" in claim_by_role(scenario, "entity_disambiguation").evaluation_roles
    assert "entity_split" in relation_by_role(scenario, "entity_split").evaluation_roles


def test_role_helpers_report_available_roles() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )

    with pytest.raises(AssertionError, match="Available"):
        claim_by_role(scenario, "missing_role")
