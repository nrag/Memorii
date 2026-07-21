from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    LatentGraphScenario,
    expected_sim_output_for_checkpoint,
    judge_sim_checkpoint,
    sim_checkpoint_diagnostics,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    claim_by_role,
    generate_scenario_by_family,
)


def _action_claim(scenario: LatentGraphScenario, state: str, subject: str):
    return next(
        claim
        for claim in scenario.claims
        if "action_state" in claim.evaluation_roles
        and claim.object.normalized_value == state
        and claim.subject.canonical_name == subject
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
    progress = _action_claim(scenario, "in_progress", "Atlas Cleanup Branch B")
    current_owner = claim_by_role(scenario, "current_truth")

    assert checkpoint.expected_claim_ids == []
    assert checkpoint.expected_entity_ids == []
    assert checkpoint.expected_citation_event_ids == []
    assert checkpoint.expected_execution_claim_ids == [progress.claim_id]
    assert checkpoint.expected_execution_entity_ids == [progress.subject.entity_id]
    assert checkpoint.expected_execution_citation_event_ids == progress.evidence.source_event_ids
    assert current_owner.claim_id not in output.selected_claim_ids
    assert current_owner.subject.entity_id not in output.selected_entity_ids
    assert not set(current_owner.evidence.source_event_ids) & set(output.supporting_citation_event_ids)

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
    assert diagnostics.answer_match_type == "diagnostic_only"


def test_memory_evolution_sim_execution_continuation_keeps_owner_facts_context_only() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    current_owner = claim_by_role(scenario, "current_truth")
    project_type = claim_by_role(scenario, "entity_type_missing")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_claim_ids": [
                *checkpoint.expected_execution_claim_ids,
                current_owner.claim_id,
                project_type.claim_id,
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
    assert "execution_context_claim_used_as_support" in diagnostics.precision_failure_classification
    assert diagnostics.supporting_role_violations["execution_context_support"] == sorted(
        [current_owner.claim_id, project_type.claim_id]
    )


def test_memory_evolution_sim_execution_continuation_rejects_truth_fact_without_active_branch() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    current_owner = claim_by_role(scenario, "current_truth")
    progress = _action_claim(scenario, "in_progress", "Atlas Cleanup Branch B")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": [current_owner.subject.entity_id],
            "selected_claim_ids": [current_owner.claim_id],
            "supporting_claim_ids": [current_owner.claim_id],
            "supporting_citation_event_ids": current_owner.evidence.source_event_ids,
            "context_entity_ids": [progress.subject.entity_id],
            "context_claim_ids": [progress.claim_id],
            "context_citation_event_ids": progress.evidence.source_event_ids,
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
    blocked_claim_id = _action_claim(scenario, "blocked", "Atlas Cleanup Branch A").claim_id
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
    assert diagnostics.channel_overlap.critical_ids["selected_rejected_claim_ids"] == [blocked_claim_id]
    assert diagnostics.channel_overlap.critical_ids["supporting_rejected_claim_ids"] == [blocked_claim_id]
    assert "selected_rejected_channel_overlap" in diagnostics.precision_failure_classification
    assert "supporting_rejected_channel_overlap" in diagnostics.precision_failure_classification
    assert "execution_text_mismatch_only" not in diagnostics.failure_classification


def test_memory_evolution_sim_execution_continuation_requires_active_action_support_and_citation() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    current_owner = claim_by_role(scenario, "current_truth")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_claim_ids": [current_owner.claim_id],
            "supporting_citation_event_ids": current_owner.evidence.source_event_ids,
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
    assert diagnostics.selected_claim_ids_missing_support == checkpoint.expected_execution_claim_ids
    assert (
        diagnostics.selected_action_state_event_ids_missing_support == checkpoint.expected_execution_citation_event_ids
    )
    assert "execution_state_support_missing" in diagnostics.failure_classification
    assert "active_action_provenance_missing" in diagnostics.failure_classification
    assert "unclassified_failure" not in diagnostics.failure_classification
