from __future__ import annotations

import json

from jsonschema import Draft202012Validator
from memorii.core.benchmark.llm_adapters import (
    LLMMemoryEvolutionSimReconstructionAdapter,
)
from memorii.core.benchmark.memory_evolution_sim import (
    sim_reconstruction_context_for_checkpoint,
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


def test_closed_world_schema_requires_exactly_one_assessment_per_visible_claim() -> None:
    _scenario, _checkpoint, context = _context()
    constrained = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context,
    )
    assessments = constrained.output_schema["properties"]["claim_assessments"]
    claim_id = assessments["items"]["properties"]["claim_id"]

    assert assessments["minItems"] == len(context.visible_claim_ids)
    assert assessments["maxItems"] == len(context.visible_claim_ids)
    assert claim_id["enum"] == sorted(context.visible_claim_ids)


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

    rank_schema = constrained.output_schema["properties"]["claim_assessments"]["items"][
        "properties"
    ]["belief_rank"]

    assert rank_schema == {"type": "null"}


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
    changed = constrain_sim_semantic_contract(
        contract=_contract(),
        context=context.model_copy(
            update={"visible_claim_ids": [*context.visible_claim_ids, "new-visible-claim"]}
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
    assessments = client.last_request.output_schema["properties"]["claim_assessments"]
    assert assessments["items"]["properties"]["claim_id"]["enum"] == sorted(
        context.visible_claim_ids
    )
    assert client.last_request.prompt_hash == client.last_request.metadata["prompt_hash"]
