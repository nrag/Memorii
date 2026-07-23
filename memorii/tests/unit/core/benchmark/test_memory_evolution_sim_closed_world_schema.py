from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator
from memorii.core.benchmark.llm_adapters import (
    LLMMemoryEvolutionSimReconstructionAdapter,
)
from memorii.core.benchmark.memory_evolution_sim import (
    expected_sim_semantic_decision_for_checkpoint,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_sim.closed_world_schema import (
    constrain_string_array_fields,
    sim_output_id_constraints,
)
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from memorii.core.prompts.runtime_manifest import PromptOwner
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
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
    return sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )


def test_closed_world_schema_uses_field_specific_visible_namespaces() -> None:
    context = _context()
    constrained = constrain_string_array_fields(
        contract=_contract(),
        allowed_values_by_field=sim_output_id_constraints(context),
    )
    properties = constrained.output_schema["properties"]

    assert properties["selected_claim_ids"]["items"]["enum"] == sorted(context.visible_claim_ids)
    assert properties["considered_claim_ids"]["items"]["enum"] == sorted(context.visible_claim_ids)
    assert properties["relevant_relation_ids"]["items"]["enum"] == sorted(context.visible_relation_ids)


def test_closed_world_schema_rejects_fabricated_and_cross_namespace_ids() -> None:
    context = _context()
    constrained = constrain_string_array_fields(
        contract=_contract(),
        allowed_values_by_field=sim_output_id_constraints(context),
    )
    output = {
        field_name: []
        for field_name, field_schema in constrained.output_schema["properties"].items()
        if field_schema.get("type") == "array"
    }
    output.update(
        {
            "operation": "answer",
            "answer": "test answer",
            "next_action": None,
            "confidence": 0.5,
            "rationale": "test",
        }
    )
    output["selected_claim_ids"] = ["fabricated-composite-id"]
    errors = list(Draft202012Validator(constrained.output_schema).iter_errors(output))
    assert errors

    output["selected_claim_ids"] = [context.visible_relation_ids[0]]
    errors = list(Draft202012Validator(constrained.output_schema).iter_errors(output))
    assert errors


def test_closed_world_schema_constrains_uncertain_ids_to_visible_union() -> None:
    context = _context()
    constraints = sim_output_id_constraints(context)
    visible_union = sorted(
        {
            *context.visible_entity_ids,
            *context.visible_claim_ids,
            *context.visible_relation_ids,
            *(event.event_id for event in context.visible_events),
        }
    )

    assert list(constraints["uncertain_ids"]) == visible_union
    assert "fabricated-id" not in constraints["uncertain_ids"]


def test_closed_world_schema_empty_namespace_requires_empty_array() -> None:
    context = _context().model_copy(
        update={
            "visible_claim_ids": [],
            "visible_claims": [],
        }
    )
    constrained = constrain_string_array_fields(
        contract=_contract(),
        allowed_values_by_field=sim_output_id_constraints(context),
    )

    assert constrained.output_schema["properties"]["selected_claim_ids"]["maxItems"] == 0
    assert "enum" not in constrained.output_schema["properties"]["selected_claim_ids"]["items"]


def test_closed_world_schema_digest_is_order_invariant_and_content_sensitive() -> None:
    contract = _contract()
    first = constrain_string_array_fields(
        contract=contract,
        allowed_values_by_field={"selected_claim_ids": ("b", "a", "a")},
    )
    reordered = constrain_string_array_fields(
        contract=contract,
        allowed_values_by_field={"selected_claim_ids": ("a", "b")},
    )
    changed = constrain_string_array_fields(
        contract=contract,
        allowed_values_by_field={"selected_claim_ids": ("a", "c")},
    )

    assert first.registration_digest == reordered.registration_digest
    assert first.output_schema == reordered.output_schema
    assert first.registration_digest != changed.registration_digest


def test_closed_world_schema_rejects_unknown_or_non_array_fields() -> None:
    with pytest.raises(ValueError, match="not a top-level array"):
        constrain_string_array_fields(
            contract=_contract(),
            allowed_values_by_field={"answer": ("x",)},
        )
    with pytest.raises(ValueError, match="not a top-level array"):
        constrain_string_array_fields(
            contract=_contract(),
            allowed_values_by_field={"missing_ids": ("x",)},
        )


def test_sim_adapter_sends_request_specific_closed_world_schema() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_split",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    response = expected_sim_semantic_decision_for_checkpoint(checkpoint).model_dump(mode="json")
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
    selected_claim_schema = client.last_request.output_schema["properties"]["selected_claim_ids"]
    assert selected_claim_schema["items"]["enum"] == sorted(context.visible_claim_ids)
    assert client.last_request.prompt_hash == client.last_request.metadata["prompt_hash"]
