from __future__ import annotations

import json

import pytest
from memorii.core.benchmark.llm_adapters import (
    LLMMemoryEvolutionSimReconstructionAdapter,
)
from memorii.core.benchmark.memory_evolution_sim import (
    expected_sim_output_for_checkpoint,
    generate_memory_evolution_sim_scenarios,
    memory_evolution_sim_engine_result_from_llm,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_sim.visible_output_validation import (
    validate_visible_sim_output,
)
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionStatus
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)


def _case(*, family: str, checkpoint_type: str, index: int = 0):
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family=family,
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, checkpoint_type, index=index)
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    output = expected_sim_output_for_checkpoint(checkpoint)
    return context, output


def test_visible_contract_accepts_expected_inverse_relationship_output() -> None:
    context, output = _case(
        family="entity_split",
        checkpoint_type="entity_split_repair",
        index=1,
    )

    assert validate_visible_sim_output(context=context, output=output) == ()


def test_visible_contract_accepts_all_generated_expected_outputs() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )

    for scenario in scenarios:
        for checkpoint in scenario.checkpoints:
            context = sim_reconstruction_context_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            output = expected_sim_output_for_checkpoint(checkpoint)
            assert validate_visible_sim_output(context=context, output=output) == ()


def test_visible_contract_is_invariant_to_candidate_card_and_observation_order() -> None:
    context, output = _case(
        family="entity_split",
        checkpoint_type="entity_split_repair",
        index=1,
    )
    reordered = context.model_copy(
        update={
            "surface_observations": list(reversed(context.surface_observations)),
            "visible_events": list(reversed(context.visible_events)),
            "visible_entities": list(reversed(context.visible_entities)),
            "visible_claims": list(reversed(context.visible_claims)),
            "visible_relations": list(reversed(context.visible_relations)),
        }
    )

    assert validate_visible_sim_output(context=context, output=output) == ()
    assert validate_visible_sim_output(context=reordered, output=output) == ()


def test_visible_contract_rejects_object_substitution_for_required_subject() -> None:
    context, output = _case(
        family="entity_split",
        checkpoint_type="entity_split_repair",
        index=1,
    )
    selected_claim = next(
        claim
        for claim in context.visible_claims
        if claim.claim_id == output.selected_claim_ids[0]
    )
    assert selected_claim.object_entity_id is not None
    invalid = output.model_copy(
        update={"selected_entity_ids": [selected_claim.object_entity_id]}
    )

    issues = validate_visible_sim_output(context=context, output=invalid)

    assert [issue.code for issue in issues] == ["selected_entity_role_mismatch"]
    assert issues[0].location == ("selected_entity_ids",)


def test_visible_contract_forbids_belief_ranking_outside_belief_tasks() -> None:
    context, output = _case(
        family="entity_split",
        checkpoint_type="entity_split_repair",
    )
    invalid = output.model_copy(
        update={"belief_ranking_ids": [output.selected_claim_ids[0]]}
    )

    issues = validate_visible_sim_output(context=context, output=invalid)

    assert [issue.code for issue in issues] == ["belief_ranking_forbidden"]


def test_visible_contract_requires_belief_ranking_for_belief_tasks() -> None:
    context, output = _case(
        family="belief_dependency_and_reranking",
        checkpoint_type="belief_ranking",
    )
    invalid = output.model_copy(update={"belief_ranking_ids": []})

    issues = validate_visible_sim_output(context=context, output=invalid)

    assert [issue.code for issue in issues] == ["belief_ranking_required"]


def test_visible_contract_rejects_active_selected_subject_definition() -> None:
    context, output = _case(
        family="current_vs_historical_truth",
        checkpoint_type="current_truth",
    )
    selected_subjects = {
        claim.subject_entity_id
        for claim in context.visible_claims
        if claim.claim_id in output.selected_claim_ids
    }
    definition = next(
        claim
        for claim in context.visible_claims
        if claim.subject_entity_id in selected_subjects
        and claim.predicate_id == "entity_type"
        and claim.lifecycle_state == "active"
    )
    invalid = output.model_copy(
        update={
            "context_claim_ids": [definition.claim_id],
            "rejected_claim_ids": [
                *output.rejected_claim_ids,
                definition.claim_id,
            ],
        }
    )

    issues = validate_visible_sim_output(context=context, output=invalid)

    assert "selected_subject_definition_rejected" in {
        issue.code for issue in issues
    }


@pytest.mark.parametrize(
    ("family", "checkpoint_type", "include_definition_in_support", "expected_codes"),
    [
        (
            "current_vs_historical_truth",
            "current_truth",
            False,
            {
                "belief_ranking_forbidden",
                "selected_subject_definition_rejected",
            },
        ),
        (
            "entity_split",
            "entity_split_repair",
            True,
            {
                "belief_ranking_forbidden",
                "selected_subject_definition_rejected",
                "supporting_rejected_claim_overlap",
            },
        ),
    ],
)
def test_normalized_live_failure_replays_preserve_visible_semantic_failures(
    family: str,
    checkpoint_type: str,
    include_definition_in_support: bool,
    expected_codes: set[str],
) -> None:
    context, output = _case(
        family=family,
        checkpoint_type=checkpoint_type,
        index=1 if family == "entity_split" else 0,
    )
    selected_subjects = {
        claim.subject_entity_id
        for claim in context.visible_claims
        if claim.claim_id in output.selected_claim_ids
    }
    definition = next(
        claim
        for claim in context.visible_claims
        if claim.subject_entity_id in selected_subjects
        and claim.predicate_id == "entity_type"
        and claim.lifecycle_state == "active"
    )
    updates: dict[str, object] = {
        "belief_ranking_ids": [output.selected_claim_ids[0]],
        "context_claim_ids": list(
            dict.fromkeys([*output.context_claim_ids, definition.claim_id])
        ),
        "rejected_claim_ids": list(
            dict.fromkeys([*output.rejected_claim_ids, definition.claim_id])
        ),
    }
    if include_definition_in_support:
        updates["supporting_claim_ids"] = list(
            dict.fromkeys([*output.supporting_claim_ids, definition.claim_id])
        )
    replay = output.model_copy(update=updates)

    issues = validate_visible_sim_output(context=context, output=replay)

    assert {issue.code for issue in issues} == expected_codes
    assert all(issue.stage.value == "semantic" for issue in issues)


def test_normalized_live_inverse_query_replay_rejects_forbidden_belief_channel() -> None:
    context, output = _case(
        family="entity_split",
        checkpoint_type="entity_split_repair",
        index=1,
    )
    replay = output.model_copy(
        update={"belief_ranking_ids": [output.selected_claim_ids[0]]}
    )

    issues = validate_visible_sim_output(context=context, output=replay)

    assert [issue.code for issue in issues] == ["belief_ranking_forbidden"]


def test_visible_contract_requires_definition_when_policy_requires_selection() -> None:
    context, output = _case(
        family="entity_definition_before_role_claims",
        checkpoint_type="entity_reconstruction",
    )
    selected_subjects = {
        claim.subject_entity_id
        for claim in context.visible_claims
        if claim.claim_id in output.selected_claim_ids
    }
    definition_ids = {
        claim.claim_id
        for claim in context.visible_claims
        if claim.subject_entity_id in selected_subjects
        and claim.predicate_id == "entity_type"
        and claim.lifecycle_state == "active"
    }
    invalid = output.model_copy(
        update={
            "selected_claim_ids": [
                claim_id
                for claim_id in output.selected_claim_ids
                if claim_id not in definition_ids
            ],
            "supporting_claim_ids": [
                claim_id
                for claim_id in output.supporting_claim_ids
                if claim_id not in definition_ids
            ],
        }
    )

    issue_codes = {
        issue.code
        for issue in validate_visible_sim_output(context=context, output=invalid)
    }

    assert "required_definition_not_selected" in issue_codes
    assert "required_definition_not_supporting" in issue_codes


def test_sim_adapter_preserves_visible_semantic_rejection_without_fallback() -> None:
    context, output = _case(
        family="entity_split",
        checkpoint_type="entity_split_repair",
        index=1,
    )
    selected_claim = next(
        claim
        for claim in context.visible_claims
        if claim.claim_id == output.selected_claim_ids[0]
    )
    assert selected_claim.object_entity_id is not None
    invalid = output.model_copy(
        update={"selected_entity_ids": [selected_claim.object_entity_id]}
    )
    adapter = LLMMemoryEvolutionSimReconstructionAdapter(
        runner=PromptLLMRunner(
            client=FakeLLMStructuredClient(
                default_response=json.dumps(invalid.model_dump(mode="json"))
            ),
            config=LLMRuntimeConfig(provider="none"),
        ),
        registry=PromptRegistry(prompt_root=default_prompt_root()),
    )

    result = adapter.decide(context, request_id="visible-semantic-rejection")

    assert result.success is False
    assert result.failure_mode == "semantic_validation"
    assert result.output is None
    assert result.rejected_output == invalid.model_dump(mode="json")
    assert [issue.code for issue in result.validation_issues] == [
        "selected_entity_role_mismatch"
    ]
    assert result.response.schema_valid is True
    assert result.response.semantic_valid is False

    final_output, trace, accepted, failure_mode = (
        memory_evolution_sim_engine_result_from_llm(
            result=result,
            mode=LLMDecisionMode.HYBRID,
            scenario=generate_scenario_by_family(
                profile="adversarial",
                family="entity_split",
                seed=7,
                noise_rate=0.35,
            ),
            rule_output=output.model_dump(mode="json"),
        )
    )
    assert final_output == invalid.model_dump(mode="json")
    assert accepted is False
    assert failure_mode == "semantic_validation"
    assert trace.status == LLMDecisionStatus.VALIDATION_FAILED
    assert trace.fallback_used is False
