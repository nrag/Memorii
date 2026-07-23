"""Request-local closed-world constraints for simulator output identifiers."""

from __future__ import annotations

from copy import deepcopy

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
)
from memorii.core.prompts.registry import (
    RegisteredPromptContract,
    prompt_registration_digest,
)

_ENTITY_ID_FIELDS = (
    "selected_entity_ids",
    "rejected_entity_ids",
    "context_entity_ids",
)
_CLAIM_ID_FIELDS = (
    "belief_ranking_ids",
    "selected_claim_ids",
    "supporting_claim_ids",
    "rejected_claim_ids",
    "context_claim_ids",
)
_RELATION_ID_FIELDS = (
    "selected_relation_ids",
    "supporting_relation_ids",
    "rejected_relation_ids",
    "context_relation_ids",
)
_EVENT_ID_FIELDS = (
    "supporting_citation_event_ids",
    "rejection_citation_event_ids",
    "context_citation_event_ids",
)


def sim_output_id_constraints(
    context: MemoryEvolutionSimReconstructionContext,
) -> dict[str, tuple[str, ...]]:
    """Return deterministic per-field ID namespaces from model-visible context."""

    entity_ids = tuple(sorted(set(context.visible_entity_ids)))
    claim_ids = tuple(sorted(set(context.visible_claim_ids)))
    relation_ids = tuple(sorted(set(context.visible_relation_ids)))
    event_ids = tuple(sorted({event.event_id for event in context.visible_events}))
    all_visible_ids = tuple(sorted({*entity_ids, *claim_ids, *relation_ids, *event_ids}))
    return {
        **{field_name: entity_ids for field_name in _ENTITY_ID_FIELDS},
        **{field_name: claim_ids for field_name in _CLAIM_ID_FIELDS},
        **{field_name: relation_ids for field_name in _RELATION_ID_FIELDS},
        **{field_name: event_ids for field_name in _EVENT_ID_FIELDS},
        "uncertain_ids": all_visible_ids,
    }


def constrain_string_array_fields(
    *,
    contract: RegisteredPromptContract,
    allowed_values_by_field: dict[str, tuple[str, ...]],
) -> RegisteredPromptContract:
    """Narrow top-level string-array fields and bind the result to prompt identity."""

    schema = deepcopy(contract.output_schema)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("output schema must define an object properties mapping")

    for field_name, raw_values in sorted(allowed_values_by_field.items()):
        field_schema = properties.get(field_name)
        if not isinstance(field_schema, dict) or field_schema.get("type") != "array":
            raise ValueError(f"closed-world field is not a top-level array: {field_name}")
        item_schema = field_schema.get("items")
        if not isinstance(item_schema, dict) or item_schema.get("type") != "string":
            raise ValueError(f"closed-world field does not contain string items: {field_name}")
        values = sorted(set(raw_values))
        field_schema.pop("maxItems", None)
        item_schema.pop("enum", None)
        if values:
            item_schema["enum"] = values
        else:
            field_schema["maxItems"] = 0

    narrowed = contract.model_copy(update={"output_schema": schema})
    return narrowed.model_copy(
        update={
            "registration_digest": prompt_registration_digest(
                narrowed,
                narrowed.runtime_registration,
            )
        }
    )
