"""Oracle-aware audit of final simulator output identifiers."""

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    LatentGraphScenario,
    ObservabilityLabel,
    SimSystemOutput,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    hidden_answer_leaks,
    role_claim_ids,
    role_entity_ids,
    role_relation_ids,
)


def sim_output_allowed_id_errors(
    *,
    scenario: LatentGraphScenario,
    output: SimSystemOutput,
) -> list[str]:
    visible_entities = {item for observation in scenario.observations for item in observation.exposed_entity_ids}
    visible_claims = {item for observation in scenario.observations for item in observation.exposed_claim_ids}
    visible_relations = {item for observation in scenario.observations for item in observation.exposed_relation_ids}
    errors: list[str] = []
    for field_name, actual, allowed in [
        ("selected_entity_ids", output.selected_entity_ids, visible_entities),
        ("rejected_entity_ids", output.rejected_entity_ids, visible_entities),
        ("context_entity_ids", output.context_entity_ids, visible_entities),
        ("selected_claim_ids", output.selected_claim_ids, visible_claims),
        ("supporting_claim_ids", output.supporting_claim_ids, visible_claims),
        ("rejected_claim_ids", output.rejected_claim_ids, visible_claims),
        ("context_claim_ids", output.context_claim_ids, visible_claims),
        ("selected_relation_ids", output.selected_relation_ids, visible_relations),
        ("supporting_relation_ids", output.supporting_relation_ids, visible_relations),
        ("rejected_relation_ids", output.rejected_relation_ids, visible_relations),
        ("context_relation_ids", output.context_relation_ids, visible_relations),
        ("belief_ranking_ids", output.belief_ranking_ids, visible_claims),
    ]:
        unknown = sorted(set(actual) - allowed)
        if unknown:
            errors.append(f"invalid_{field_name}:{','.join(unknown)}")
    event_ids = {observation.event_id for observation in scenario.observations}
    for field_name, actual in [
        ("supporting_citation_event_ids", output.supporting_citation_event_ids),
        ("rejection_citation_event_ids", output.rejection_citation_event_ids),
        ("context_citation_event_ids", output.context_citation_event_ids),
    ]:
        unknown_events = sorted(set(actual) - event_ids)
        if unknown_events:
            errors.append(f"invalid_{field_name}:{','.join(unknown_events)}")
    all_visible_ids = visible_entities | visible_claims | visible_relations | event_ids
    unknown_uncertain = sorted(set(output.uncertain_ids) - all_visible_ids)
    if unknown_uncertain:
        errors.append(f"invalid_uncertain_ids:{','.join(unknown_uncertain)}")
    hidden_ids = (
        {item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN}
        | {item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN}
        | {item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN}
    )
    asserted = set(role_entity_ids(output)) | set(role_claim_ids(output)) | set(role_relation_ids(output))
    hallucinated = sorted(asserted & hidden_ids)
    if hallucinated:
        errors.append(f"hidden_ids_asserted:{','.join(hallucinated)}")
    answer_leaks = hidden_answer_leaks(scenario, output)
    if answer_leaks:
        errors.append(f"hidden_answer_leak:{','.join(answer_leaks)}")
    return errors
