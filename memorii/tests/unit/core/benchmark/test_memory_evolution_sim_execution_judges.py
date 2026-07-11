from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    ObservabilityLabel,
    SimSystemOutput,
    expected_sim_output_for_checkpoint,
    judge_sim_checkpoint,
    normalize_sim_system_output_for_checkpoint,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
    sim_reconstruction_context_for_checkpoint,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)


def test_memory_evolution_sim_execution_continuation_requires_selected_state() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="abandoned_then_resumed_work",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": [],
            "selected_claim_ids": [],
            "supporting_claim_ids": [],
            "supporting_citation_event_ids": [],
            "context_entity_ids": checkpoint.expected_entity_ids,
            "context_claim_ids": checkpoint.expected_claim_ids,
            "context_citation_event_ids": checkpoint.expected_citation_event_ids,
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "abandoned_branch_selected" in aggregate.critical_failure_buckets
    assert "missing_provenance" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_execution_continuation_allows_different_next_action_wording() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="abandoned_then_resumed_work",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "next_action": "Verify the current owner in the directory and continue the active cleanup branch.",
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics["answer_match_type"] == "diagnostic_only"


