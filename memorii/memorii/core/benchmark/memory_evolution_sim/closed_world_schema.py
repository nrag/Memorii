"""Request-local schema constraints for simulator semantic assessments."""

from __future__ import annotations

from copy import deepcopy

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
)
from memorii.core.benchmark.task_conditioned_fields import allowed_task_operations
from memorii.core.prompts.registry import (
    RegisteredPromptContract,
    prompt_registration_digest,
)


def constrain_sim_semantic_contract(
    *,
    contract: RegisteredPromptContract,
    context: MemoryEvolutionSimReconstructionContext,
) -> RegisteredPromptContract:
    """Bind assessment IDs and task-conditioned ranks to visible context."""

    schema = deepcopy(contract.output_schema)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("output schema must define object properties")
    operation = properties.get("operation")
    if not isinstance(operation, dict):
        raise ValueError("operation must define a scalar field")
    operation["enum"] = list(
        allowed_task_operations(context.checkpoint.task_contract.allowed_operations)
    )
    assessments = properties.get("claim_assessments")
    if not isinstance(assessments, dict) or assessments.get("type") != "array":
        raise ValueError("claim_assessments must be an array")
    items = assessments.get("items")
    if not isinstance(items, dict):
        raise ValueError("claim_assessments must define object items")
    item_properties = items.get("properties")
    if not isinstance(item_properties, dict):
        raise ValueError("claim assessments must define properties")
    claim_id = item_properties.get("claim_id")
    belief_rank = item_properties.get("belief_rank")
    if not isinstance(claim_id, dict) or not isinstance(belief_rank, dict):
        raise ValueError("claim assessment schema is incomplete")

    visible_claim_ids = sorted(set(context.visible_claim_ids))
    assessments["minItems"] = len(visible_claim_ids)
    assessments["maxItems"] = len(visible_claim_ids)
    claim_id["enum"] = visible_claim_ids
    if context.checkpoint.task_contract.belief_ranking_policy == "forbidden":
        item_properties["belief_rank"] = {"type": "null"}

    uncertain = properties.get("uncertain_ids")
    if not isinstance(uncertain, dict):
        raise ValueError("uncertain_ids must define an array")
    uncertain_items = uncertain.get("items")
    if not isinstance(uncertain_items, dict):
        raise ValueError("uncertain_ids must define string items")
    all_visible_ids = sorted(
        {
            *context.visible_entity_ids,
            *context.visible_claim_ids,
            *context.visible_relation_ids,
            *(event.event_id for event in context.visible_events),
        }
    )
    uncertain_items["enum"] = all_visible_ids

    narrowed = contract.model_copy(update={"output_schema": schema})
    return narrowed.model_copy(
        update={
            "registration_digest": prompt_registration_digest(
                narrowed,
                narrowed.runtime_registration,
            )
        }
    )
