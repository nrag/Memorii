from memorii.core.benchmark.memory_evolution_oracle import build_oracle_execution_expectation
from tests.unit.core.benchmark.memory_evolution_runtime_test_helpers import long_horizon_execution_scenario


def test_oracle_execution_expectation_selects_active_branch() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()

    states = build_oracle_execution_expectation(scenario, checkpoint)

    active = [state for state in states if state.active]
    assert active
    assert any(state.branch_id in checkpoint.expected_execution_entity_ids for state in active)
    assert all(state.supporting_claim_ids for state in active)
