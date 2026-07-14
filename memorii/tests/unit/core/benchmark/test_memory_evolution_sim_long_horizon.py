from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    generate_memory_evolution_sim_scenarios,
    sim_reconstruction_context_for_checkpoint,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)


def test_memory_evolution_sim_long_horizon_profile_has_phase_pressure() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="long_horizon",
        scenario_count=10,
        seed=7,
        min_events=25,
        max_events=60,
        noise_rate=0.35,
    )

    assert all(len(scenario.observations) >= 25 for scenario in scenarios)
    for scenario in scenarios:
        phases = {observation.phase for observation in scenario.observations}
        assert {"setup", "interference", "evolution", "dormancy"} <= phases
        assert any("late_stale_resurface" in observation.event_id for observation in scenario.observations)
        assert all(checkpoint.horizon_distance >= 10 for checkpoint in scenario.checkpoints)
        assert all(checkpoint.interference_count >= 10 for checkpoint in scenario.checkpoints)
        assert all(checkpoint.source_event_age_days > 0 for checkpoint in scenario.checkpoints)
        assert all(checkpoint.expected_stage_path for checkpoint in scenario.checkpoints)


def test_memory_evolution_sim_long_horizon_execution_has_action_state_pressure() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        scenario_count=10,
        min_events=25,
        max_events=60,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    action_claims = [claim for claim in scenario.claims if claim.claim_kind == "action_state"]

    assert checkpoint.expected_action_ids
    assert checkpoint.expected_claim_ids == []
    assert checkpoint.expected_entity_ids == []
    assert checkpoint.expected_citation_event_ids == []
    assert checkpoint.expected_execution_claim_ids == ["claim_09_branch_b_progress"]
    assert checkpoint.expected_execution_entity_ids == ["ent_09_branch_b"]
    assert checkpoint.expected_execution_citation_event_ids == ["event_09_branch_b_progress"]
    assert any(claim.claim_id.endswith("branch_b_progress") for claim in action_claims)
    assert any(claim.claim_id.endswith("branch_a_blocked") for claim in action_claims)
    assert any(
        claim.claim_id.endswith("branch_b_progress")
        for claim in scenario.claims
        if claim.claim_id in checkpoint.expected_execution_claim_ids
    )
    assert any(claim_id.endswith("branch_a_blocked") for claim_id in checkpoint.expected_excluded_claim_ids)
    assert any(
        observation.event_id.endswith("branch_b_progress") and observation.phase == "evolution"
        for observation in scenario.observations
    )


def test_memory_evolution_sim_long_horizon_context_has_sanitized_stage_metadata() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="entity_definition_before_role_claims",
        seed=7,
        scenario_count=10,
        min_events=25,
        max_events=60,
        noise_rate=0.35,
    )
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint_by_type(scenario, "entity_reconstruction"),
    )
    payload = context.model_dump(mode="json")

    assert {event["phase"] for event in payload["visible_events"]} >= {"setup", "interference", "evolution", "dormancy"}
    assert payload["checkpoint"]["horizon_distance"] >= 10
    assert payload["checkpoint"]["stage_path"]
    assert not any(key.startswith("expected_") for key in payload["checkpoint"])
    assert "stage_path" in payload["metadata"]["long_horizon"]
    assert "expected_stage_path" not in payload["metadata"]["long_horizon"]
