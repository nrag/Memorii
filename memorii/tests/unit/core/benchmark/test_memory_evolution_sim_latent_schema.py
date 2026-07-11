from __future__ import annotations

import pytest
from pydantic import ValidationError

from memorii.core.benchmark.memory_evolution_sim import (
    LatentGraphScenario,
    ObservabilityLabel,
    SimSystemOutput,
    generate_memory_evolution_sim_scenarios,
    sim_reconstruction_context_for_checkpoint,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    claim_by_role,
    generate_scenario_by_family,
)


def test_memory_evolution_sim_adversarial_profile_creates_hidden_latent_items() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=10, seed=7, noise_rate=0.35
    )

    for scenario in scenarios:
        hidden_entities = [item for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN]
        hidden_claims = [item for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN]
        hidden_relations = [item for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN]
        assert len(hidden_entities) >= 1
        assert len(hidden_claims) >= 1
        assert len(hidden_relations) >= 1
        assert all(not claim.evidence.spans for claim in hidden_claims)
        assert all(not claim.evidence.source_event_ids for claim in hidden_claims)
        expected_ids = {hidden_entities[0].entity_id, hidden_claims[0].claim_id, hidden_relations[0].relation_id}
        exposed_ids = {
            item
            for observation in scenario.observations
            for item in [
                *observation.exposed_entity_ids,
                *observation.exposed_claim_ids,
                *observation.exposed_relation_ids,
            ]
        }
        assert not expected_ids & exposed_ids


def test_memory_evolution_sim_smoke_profile_does_not_create_hidden_latent_items() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)

    hidden_ids = {
        item.entity_id for scenario in scenarios for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.claim_id for scenario in scenarios for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.relation_id
        for scenario in scenarios
        for item in scenario.relations
        if item.observability == ObservabilityLabel.HIDDEN
    }

    assert hidden_ids == set()


def test_memory_evolution_sim_visible_claim_relation_evidence_matches_exposing_observation() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=10, seed=19, noise_rate=0.35
    )
    for scenario in scenarios:
        exposed_claim_events: dict[str, set[str]] = {}
        exposed_relation_events: dict[str, set[str]] = {}
        for observation in scenario.observations:
            for claim_id in observation.exposed_claim_ids:
                exposed_claim_events.setdefault(claim_id, set()).add(observation.event_id)
            for relation_id in observation.exposed_relation_ids:
                exposed_relation_events.setdefault(relation_id, set()).add(observation.event_id)
        for claim in scenario.claims:
            if claim.claim_id not in exposed_claim_events or claim.observability == ObservabilityLabel.HIDDEN:
                continue
            assert set(claim.evidence.source_event_ids) & exposed_claim_events[claim.claim_id], claim.claim_id
        for relation in scenario.relations:
            if relation.relation_id not in exposed_relation_events or relation.observability == ObservabilityLabel.HIDDEN:
                continue
            assert set(relation.provenance.source_event_ids) & exposed_relation_events[relation.relation_id], relation.relation_id


def test_memory_evolution_sim_seed_19_conflict_evidence_uses_ambiguity_event_not_noise() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="source_trust_conflict",
        scenario_count=10,
        seed=19,
        noise_rate=0.35,
    )
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint_by_type(scenario, "source_trust_conflict"),
    )
    ambiguous_claim = next(claim for claim in context.visible_claims if claim.claim_id == "claim_03_ambiguous_service_owner_atlas")
    conflict_relation = next(relation for relation in context.visible_relations if relation.relation_id == "rel_03_owner_conflict")

    assert ambiguous_claim.evidence_event_ids == ["event_03_006"]
    assert conflict_relation.evidence_event_ids == ["event_03_006"]
    assert "standup" in ambiguous_claim.evidence_quote
    assert "standup" in conflict_relation.evidence_quote
    assert all("_noise_" not in event_id for event_id in ambiguous_claim.evidence_event_ids)
    assert all("_noise_" not in event_id for event_id in conflict_relation.evidence_event_ids)


def test_memory_evolution_sim_uses_role_stable_ids_not_seeded_names() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=19)
    all_ids = [
        item_id
        for scenario in scenarios
        for item_id in [
            *[entity.entity_id for entity in scenario.entities],
            *[claim.claim_id for claim in scenario.claims],
            *[relation.relation_id for relation in scenario.relations],
        ]
    ]

    assert not any("_alice" in item_id or "_bob" in item_id or "_carol" in item_id for item_id in all_ids)
    assert any("_current_owner" in item_id for item_id in all_ids)
    assert any("_service_owner" in item_id for item_id in all_ids)


def test_memory_evolution_sim_legacy_fields_are_derived_from_role_channels() -> None:
    output = SimSystemOutput(
        operation="answer",
        entity_ids=["legacy_entity"],
        claim_ids=["legacy_claim"],
        relation_ids=["legacy_relation"],
        citation_event_ids=["legacy_event"],
        selected_entity_ids=["ent_current"],
        selected_claim_ids=["claim_current"],
        selected_relation_ids=["rel_current"],
        supporting_claim_ids=["claim_support"],
        supporting_relation_ids=["rel_support"],
        supporting_citation_event_ids=["event_support"],
        rejected_entity_ids=["ent_rejected"],
        rejected_claim_ids=["claim_rejected"],
        rejected_relation_ids=["rel_rejected"],
        rejection_citation_event_ids=["event_rejected"],
        context_entity_ids=["ent_context"],
        context_claim_ids=["claim_context"],
        context_relation_ids=["rel_context"],
        context_citation_event_ids=["event_context"],
        answer="Nadia",
        next_action=None,
        uncertain_ids=[],
        confidence=0.8,
        rationale="role-aware fields are canonical",
    )

    assert output.entity_ids == ["ent_current", "ent_context", "ent_rejected"]
    assert output.claim_ids == ["claim_current", "claim_support", "claim_context", "claim_rejected"]
    assert output.relation_ids == ["rel_current", "rel_support", "rel_context", "rel_rejected"]
    assert output.citation_event_ids == ["event_support", "event_context", "event_rejected"]


def test_memory_evolution_sim_hidden_items_cannot_be_expected() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    claim = claim_by_role(scenario, "entity_reconstruction")
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    payload = scenario.model_dump(mode="json")
    payload_claim = next(item for item in payload["claims"] if item["claim_id"] == claim.claim_id)
    payload_checkpoint = next(item for item in payload["checkpoints"] if item["checkpoint_id"] == checkpoint.checkpoint_id)
    payload_claim["observability"] = ObservabilityLabel.HIDDEN.value
    payload_claim["evidence"]["spans"] = []
    payload_checkpoint["expected_claim_ids"] = [payload_claim["claim_id"]]

    with pytest.raises(ValidationError, match="requires hidden ids"):
        LatentGraphScenario.model_validate(payload)


def test_memory_evolution_sim_oracle_checkpoints_do_not_require_hidden_ids() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=10, seed=7, noise_rate=0.35
    )

    for scenario in scenarios:
        hidden_ids = {
            item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
        } | {
            item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
        } | {
            item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
        }
        for checkpoint in scenario.checkpoints:
            expected_ids = {
                *checkpoint.expected_entity_ids,
                *checkpoint.expected_claim_ids,
                *checkpoint.expected_relation_ids,
                *checkpoint.expected_excluded_entity_ids,
                *checkpoint.expected_excluded_claim_ids,
                *checkpoint.expected_uncertain_ids,
            }
            assert not expected_ids & hidden_ids


def test_memory_evolution_sim_observed_claims_require_spo_evidence() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    claim = claim_by_role(scenario, "entity_reconstruction")
    payload = scenario.model_dump(mode="json")
    payload_claim = next(item for item in payload["claims"] if item["claim_id"] == claim.claim_id)
    payload_claim["evidence"]["spans"] = [payload_claim["evidence"]["spans"][0]]

    with pytest.raises(ValidationError, match="subject, predicate, and object evidence"):
        LatentGraphScenario.model_validate(payload)
