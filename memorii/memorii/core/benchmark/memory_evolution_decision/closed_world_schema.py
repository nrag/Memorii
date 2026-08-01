"""Request-local schema constraints for curated memory-evolution decisions."""

from __future__ import annotations

from copy import deepcopy

from memorii.core.benchmark.memory_evolution_decision.contracts import (
    MemoryEvolutionBeliefScorePolicy,
    MemoryEvolutionDecisionContext,
)
from memorii.core.prompts.registry import (
    RegisteredPromptContract,
    prompt_registration_digest,
)


def constrain_memory_evolution_semantic_contract(
    *,
    contract: RegisteredPromptContract,
    context: MemoryEvolutionDecisionContext,
) -> RegisteredPromptContract:
    """Bind belief-score presence to the visible checkpoint contract."""

    schema = deepcopy(contract.output_schema)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("output schema must define object properties")
    belief_scores = properties.get("belief_scores")
    if not isinstance(belief_scores, dict) or belief_scores.get("type") != "array":
        raise ValueError("belief_scores must define an array")
    if context.decision_contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.NONE:
        belief_scores["maxItems"] = 0
    else:
        belief_scores["minItems"] = 1

    narrowed = contract.model_copy(update={"output_schema": schema})
    return narrowed.model_copy(
        update={
            "registration_digest": prompt_registration_digest(
                narrowed,
                narrowed.runtime_registration,
            )
        }
    )
