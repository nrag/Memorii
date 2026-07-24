from __future__ import annotations

import json

from jsonschema import Draft202012Validator
from memorii.core.benchmark.llm_adapters import (
    LLMMemoryEvolutionSimReconstructionAdapter,
)
from memorii.core.benchmark.memory_evolution_sim import (
    SimDecisionContractViolationCode,
    SimSemanticDecision,
    sim_reconstruction_context_for_checkpoint,
    validate_sim_decision_contract,
)
from memorii.core.benchmark.memory_evolution_sim.closed_world_schema import (
    constrain_sim_semantic_contract,
)
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from memorii.core.prompts.runtime_manifest import PromptOwner
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
    oracle_shaped_sim_semantic_decision,
)


def _contract():
    return PromptRegistry(prompt_root=default_prompt_root()).load(
        "memory_evolution_sim_reconstruction:v1",
        owner=PromptOwner.LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER,
        output_model=LLMMemoryEvolutionSimReconstructionAdapter.output_model,
    )


def _context():
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_split",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    return (
        scenario,
        checkpoint,
        sim_reconstruction_context_for_checkpoint(
            scenario=scenario,
            checkpoint=checkpoint,
        ),
    )


def _assessment_variants(schema: dict[str, object]) -> list[dict[str, object]]:
    assessments = schema["properties"]["claim_assessments"]  # type: ignore[index]
    return assessments["items"]["anyOf"]  # type: ignore[index]


def _variant_by_claim_id(
    schema: dict[str, object],
    claim_id: str,
) -> dict[str, object]:
    return next(
        variant
        for variant in _assessment_variants(schema)
        if variant["properties"]["claim_id"]["const"] == claim_id  # type: ignore[index]
    )


def test_closed_world_schema_requires_exactly_one_assessment_per_visible_claim() -> None:
    _scenario, _checkpoint, context = _context()
    constrained = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )
    assessments = constrained.output_schema["properties"]["claim_assessments"]

    assert assessments["minItems"] == len(context.visible_claim_ids)
    assert assessments["maxItems"] == len(context.visible_claim_ids)
    assert sorted(
        variant["properties"]["claim_id"]["const"]  # type: ignore[index]
        for variant in assessments["items"]["anyOf"]
    ) == sorted(context.visible_claim_ids)


def test_closed_world_schema_uses_task_operation_domain_with_abstention() -> None:
    _scenario, _checkpoint, context = _context()
    constrained = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )

    assert constrained.output_schema["properties"]["operation"]["enum"] == [
        "abstain",
        *sorted(context.checkpoint.task_contract.allowed_operations),
    ]


def test_closed_world_schema_rejects_fabricated_and_cross_namespace_ids() -> None:
    _scenario, checkpoint, context = _context()
    constrained = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )
    payload = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    ).model_dump(mode="json")

    payload["claim_assessments"][0]["claim_id"] = "fabricated-composite-id"
    assert list(Draft202012Validator(constrained.output_schema).iter_errors(payload))

    payload["claim_assessments"][0]["claim_id"] = context.visible_relation_ids[0]
    assert list(Draft202012Validator(constrained.output_schema).iter_errors(payload))


def test_closed_world_schema_constrains_uncertain_ids_to_visible_union() -> None:
    _scenario, _checkpoint, context = _context()
    constrained = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )
    uncertain_items = constrained.output_schema["properties"]["uncertain_ids"]["items"]
    visible_union = sorted(
        {
            *context.visible_entity_ids,
            *context.visible_claim_ids,
            *context.visible_relation_ids,
            *(event.event_id for event in context.visible_events),
        }
    )

    assert uncertain_items["enum"] == visible_union
    assert "fabricated-id" not in uncertain_items["enum"]


def test_closed_world_schema_forbids_ranks_for_non_ranking_tasks() -> None:
    _scenario, _checkpoint, context = _context()
    constrained = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )

    assert all(
        variant["properties"]["belief_rank"] == {"type": "null"}  # type: ignore[index]
        for variant in _assessment_variants(constrained.output_schema)
    )


def test_closed_world_schema_digest_is_order_invariant_and_content_sensitive() -> None:
    _scenario, _checkpoint, context = _context()
    first = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )
    reordered = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context.model_copy(
            update={"visible_claim_ids": list(reversed(context.visible_claim_ids))}
        ),
    )
    new_claim = context.visible_claims[0].model_copy(
        update={"claim_id": "new-visible-claim"}
    )
    changed = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context.model_copy(
            update={
                "visible_claim_ids": [
                    *context.visible_claim_ids,
                    "new-visible-claim",
                ],
                "visible_claims": [*context.visible_claims, new_claim],
            }
        ),
    )

    assert first.registration_digest == reordered.registration_digest
    assert first.output_schema == reordered.output_schema
    assert first.registration_digest != changed.registration_digest


def test_sim_adapter_sends_request_specific_closed_world_schema() -> None:
    _scenario, checkpoint, context = _context()
    response = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    client = FakeLLMStructuredClient(default_response=json.dumps(response))
    adapter = LLMMemoryEvolutionSimReconstructionAdapter(
        runner=PromptLLMRunner(
            client=client,
            config=LLMRuntimeConfig(provider="none"),
        ),
        registry=PromptRegistry(prompt_root=default_prompt_root()),
    )

    result = adapter.decide(context, request_id="closed-world-test")

    assert result.success is True
    assert client.last_request is not None
    assert sorted(
        variant["properties"]["claim_id"]["const"]  # type: ignore[index]
        for variant in _assessment_variants(client.last_request.output_schema)
    ) == sorted(context.visible_claim_ids)
    assert client.last_request.prompt_hash == client.last_request.metadata["prompt_hash"]


def test_execution_schema_prevents_ineligible_primary_roles() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    constrained = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )
    eligible = next(
        claim
        for claim in context.visible_claims
        if claim.predicate_id == "action_state"
        and claim.lifecycle_state == "active"
        and claim.object_value == "in_progress"
    )
    owner = next(
        claim for claim in context.visible_claims if claim.predicate_id == "owner"
    )
    blocked = next(
        claim
        for claim in context.visible_claims
        if claim.predicate_id == "action_state"
        and claim.object_value == "blocked"
    )

    assert _variant_by_claim_id(
        constrained.output_schema,
        eligible.claim_id,
    )["properties"]["role"]["enum"] == ["primary", "relevant", "irrelevant"]  # type: ignore[index]
    for claim in (owner, blocked):
        assert _variant_by_claim_id(
            constrained.output_schema,
            claim.claim_id,
        )["properties"]["role"]["enum"] == ["relevant", "irrelevant"]  # type: ignore[index]


def test_execution_schema_and_validator_agree_on_primary_eligibility() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    constrained = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )
    semantic = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    )
    owner = next(
        claim for claim in context.visible_claims if claim.predicate_id == "owner"
    )
    payload = semantic.model_dump(mode="json")
    for assessment in payload["claim_assessments"]:
        assessment["role"] = (
            "primary" if assessment["claim_id"] == owner.claim_id else "irrelevant"
        )

    errors = list(
        Draft202012Validator(constrained.output_schema).iter_errors(payload)
    )
    validation = validate_sim_decision_contract(
        context=context,
        semantic=SimSemanticDecision.model_validate(payload),
    )

    assert errors
    assert SimDecisionContractViolationCode.NON_ACTION_SELECTED_FOR_EXECUTION in {
        issue.code for issue in validation.issues
    }
