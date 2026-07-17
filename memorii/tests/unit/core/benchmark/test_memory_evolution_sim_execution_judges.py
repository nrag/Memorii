from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    expected_sim_output_for_checkpoint,
    judge_sim_checkpoint,
    sim_checkpoint_diagnostics,
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
            "context_entity_ids": checkpoint.expected_execution_entity_ids,
            "context_claim_ids": checkpoint.expected_execution_claim_ids,
            "context_citation_event_ids": checkpoint.expected_execution_citation_event_ids,
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "execution_state_support_missing" in aggregate.critical_failure_buckets
    assert "active_action_provenance_missing" in aggregate.critical_failure_buckets
    assert "missing_provenance" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_execution_continuation_oracle_uses_execution_expectations_only() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    output = expected_sim_output_for_checkpoint(checkpoint)

    assert checkpoint.expected_claim_ids == []
    assert checkpoint.expected_entity_ids == []
    assert checkpoint.expected_citation_event_ids == []
    assert checkpoint.expected_execution_claim_ids == ["claim_09_branch_b_progress"]
    assert checkpoint.expected_execution_entity_ids == ["ent_09_branch_b"]
    assert checkpoint.expected_execution_citation_event_ids == ["event_09_branch_b_progress"]
    assert "claim_09_current_owner" not in output.selected_claim_ids
    assert "ent_09_atlas_migration" not in output.selected_entity_ids
    assert "event_09_005" not in output.supporting_citation_event_ids

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.PASS


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


def test_memory_evolution_sim_execution_continuation_keeps_owner_facts_context_only() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_claim_ids": [
                *checkpoint.expected_execution_claim_ids,
                "claim_09_current_owner",
                "claim_09_project_type",
            ],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "execution_context_claim_used_as_support" in aggregate.critical_failure_buckets
    assert "execution_context_claim_used_as_support" in diagnostics["precision_failure_classification"]
    assert diagnostics["supporting_role_violations"]["execution_context_support"] == [
        "claim_09_current_owner",
        "claim_09_project_type",
    ]


def test_memory_evolution_sim_execution_continuation_rejects_truth_fact_without_active_branch() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": ["ent_09_atlas_migration"],
            "selected_claim_ids": ["claim_09_current_owner"],
            "supporting_claim_ids": ["claim_09_current_owner"],
            "supporting_citation_event_ids": ["event_09_005"],
            "context_entity_ids": ["ent_09_branch_b"],
            "context_claim_ids": ["claim_09_branch_b_progress"],
            "context_citation_event_ids": ["event_09_branch_b_progress"],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "execution_state_support_missing" in aggregate.critical_failure_buckets
    assert "execution_state_entity_missing" in aggregate.critical_failure_buckets
    assert "active_action_provenance_missing" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_execution_continuation_fails_when_blocked_branch_is_selected_or_supporting() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    blocked_claim_id = "claim_09_branch_a_blocked"
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [*checkpoint.expected_execution_claim_ids, blocked_claim_id],
            "supporting_claim_ids": [*checkpoint.expected_execution_claim_ids, blocked_claim_id],
            "rejected_claim_ids": [blocked_claim_id],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "selected_rejected_channel_overlap" in aggregate.critical_failure_buckets
    assert "supporting_rejected_channel_overlap" in aggregate.critical_failure_buckets
    vote_buckets = {bucket for vote in aggregate.votes for bucket in vote.failure_buckets}
    assert "selected_rejected_channel_overlap" in vote_buckets
    assert "supporting_rejected_channel_overlap" in vote_buckets
    assert diagnostics["channel_overlap"]["critical_ids"]["selected_rejected_claim_ids"] == [blocked_claim_id]
    assert diagnostics["channel_overlap"]["critical_ids"]["supporting_rejected_claim_ids"] == [blocked_claim_id]
    assert "selected_rejected_channel_overlap" in diagnostics["precision_failure_classification"]
    assert "supporting_rejected_channel_overlap" in diagnostics["precision_failure_classification"]
    assert "execution_text_mismatch_only" not in diagnostics["failure_classification"]


def test_memory_evolution_sim_execution_continuation_requires_active_action_support_and_citation() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_claim_ids": ["claim_09_current_owner"],
            "supporting_citation_event_ids": ["event_09_005"],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "execution_state_support_missing" in aggregate.critical_failure_buckets
    assert "active_action_provenance_missing" in aggregate.critical_failure_buckets
    assert diagnostics["selected_claim_ids_missing_support"] == ["claim_09_branch_b_progress"]
    assert diagnostics["selected_action_state_event_ids_missing_support"] == ["event_09_branch_b_progress"]
    assert "execution_state_support_missing" in diagnostics["failure_classification"]
    assert "active_action_provenance_missing" in diagnostics["failure_classification"]
    assert "unclassified_failure" not in diagnostics["failure_classification"]
