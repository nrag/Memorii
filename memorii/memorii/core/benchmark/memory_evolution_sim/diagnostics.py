"""Simulator diagnostics and failure-classification helpers."""

from __future__ import annotations

import re

from memorii.core.benchmark.memory_evolution_sim.schemas import *  # noqa: F403
from memorii.core.benchmark.memory_evolution_sim.utils import (
    _answer_bucket,
    _bad_supporting_event_ids,
    _claim_bucket,
    _claim_by_id,
    _claim_is_bad_support,
    _context_only_noise_event_ids,
    _extract_rule_answer,
    _hidden_answer_leaks,
    _is_visible_claim,
    _is_visible_entity,
    _norm,
    _observation_by_id,
    _ordered_unique,
    _relation_bucket,
    _required_definition_claim_ids_for_selected_claims,
    _role_relation_ids,
    _selected_noncurrent_claim_ids,
)
from memorii.core.benchmark.memory_evolution_sim.candidate_cards import _checkpoint_contract_for_type
from memorii.core.benchmark.memory_evolution_sim.judges import (
    _expected_rejected_claim_subject_entity_ids,
    _required_selected_entity_ids_for_policy,
)


def sim_output_allowed_id_errors(*, scenario: LatentGraphScenario, output: SimSystemOutput) -> list[str]:
    visible_entities = {item for obs in scenario.observations for item in obs.exposed_entity_ids}
    visible_claims = {item for obs in scenario.observations for item in obs.exposed_claim_ids}
    visible_relations = {item for obs in scenario.observations for item in obs.exposed_relation_ids}
    errors: list[str] = []
    for field_name, actual, allowed in [
        ("entity_ids", output.entity_ids, visible_entities),
        ("selected_entity_ids", output.selected_entity_ids, visible_entities),
        ("rejected_entity_ids", output.rejected_entity_ids, visible_entities),
        ("context_entity_ids", output.context_entity_ids, visible_entities),
        ("claim_ids", output.claim_ids, visible_claims),
        ("selected_claim_ids", output.selected_claim_ids, visible_claims),
        ("supporting_claim_ids", output.supporting_claim_ids, visible_claims),
        ("rejected_claim_ids", output.rejected_claim_ids, visible_claims),
        ("context_claim_ids", output.context_claim_ids, visible_claims),
        ("relation_ids", output.relation_ids, visible_relations),
        ("selected_relation_ids", output.selected_relation_ids, visible_relations),
        ("supporting_relation_ids", output.supporting_relation_ids, visible_relations),
        ("rejected_relation_ids", output.rejected_relation_ids, visible_relations),
        ("context_relation_ids", output.context_relation_ids, visible_relations),
        ("belief_ranking_ids", output.belief_ranking_ids, visible_claims),
    ]:
        unknown = sorted(set(actual) - allowed)
        if unknown:
            errors.append(f"invalid_{field_name}:{','.join(unknown)}")
    event_ids = {obs.event_id for obs in scenario.observations}
    for field_name, actual in [
        ("citation_event_ids", output.citation_event_ids),
        ("supporting_citation_event_ids", output.supporting_citation_event_ids),
        ("rejection_citation_event_ids", output.rejection_citation_event_ids),
        ("context_citation_event_ids", output.context_citation_event_ids),
    ]:
        unknown_events = sorted(set(actual) - event_ids)
        if unknown_events:
            errors.append(f"invalid_{field_name}:{','.join(unknown_events)}")
    hidden_ids = {
        item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
    }
    asserted = (
        set(output.entity_ids)
        | set(output.selected_entity_ids)
        | set(output.rejected_entity_ids)
        | set(output.context_entity_ids)
        | set(output.claim_ids)
        | set(output.selected_claim_ids)
        | set(output.supporting_claim_ids)
        | set(output.rejected_claim_ids)
        | set(output.context_claim_ids)
        | set(output.relation_ids)
        | set(output.selected_relation_ids)
        | set(output.supporting_relation_ids)
        | set(output.rejected_relation_ids)
        | set(output.context_relation_ids)
    )
    hallucinated = sorted(asserted & hidden_ids)
    if hallucinated:
        errors.append(f"hidden_ids_asserted:{','.join(hallucinated)}")
    answer_leaks = _hidden_answer_leaks(scenario, output)
    if answer_leaks:
        errors.append(f"hidden_answer_leak:{','.join(answer_leaks)}")
    return errors

def sim_checkpoint_diagnostics(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
) -> dict[str, object]:
    expected_by_type = {
        "entity_ids": checkpoint.expected_entity_ids,
        "claim_ids": checkpoint.expected_claim_ids,
        "relation_ids": checkpoint.expected_relation_ids,
        "citation_event_ids": checkpoint.expected_citation_event_ids,
    }
    actual_by_type = {
        "entity_ids": output.entity_ids,
        "claim_ids": output.claim_ids,
        "relation_ids": output.relation_ids,
        "citation_event_ids": output.citation_event_ids,
    }
    missing = {
        key: [item for item in expected if item not in actual_by_type[key]]
        for key, expected in expected_by_type.items()
        if [item for item in expected if item not in actual_by_type[key]]
    }
    extra = {
        key: [item for item in actual_by_type[key] if item not in expected_by_type[key]]
        for key in actual_by_type
        if [item for item in actual_by_type[key] if item not in expected_by_type[key]]
    }
    answer_match_type = _answer_match_type(scenario, checkpoint, output)
    classifications = _failure_classifications(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
        missing=missing,
        answer_match_type=answer_match_type,
    )
    selected_excluded_ids = {
        "claim_ids": [item for item in checkpoint.expected_excluded_claim_ids if item in output.selected_claim_ids],
        "entity_ids": [item for item in checkpoint.expected_excluded_entity_ids if item in output.selected_entity_ids],
    }
    supporting_excluded_ids = {
        "claim_ids": [item for item in checkpoint.expected_excluded_claim_ids if item in output.supporting_claim_ids],
        "entity_ids": [item for item in checkpoint.expected_excluded_entity_ids if item in output.selected_entity_ids],
    }
    rejected_expected_ids = {
        "claim_ids": [item for item in checkpoint.expected_excluded_claim_ids if item in output.rejected_claim_ids or item in output.context_claim_ids],
        "entity_ids": [
            item
            for item in _ordered_unique([
                *checkpoint.expected_excluded_entity_ids,
                *_expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
            ])
            if item in output.rejected_entity_ids or item in output.context_entity_ids
        ],
    }
    missing_rejected_ids = {
        "claim_ids": [
            item
            for item in checkpoint.expected_excluded_claim_ids
            if item not in output.rejected_claim_ids and item not in output.context_claim_ids
        ],
        "entity_ids": [
            item
            for item in _ordered_unique([
                *checkpoint.expected_excluded_entity_ids,
                *_expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
            ])
            if item not in output.rejected_entity_ids and item not in output.context_entity_ids
        ],
    }
    missing_rejected_claim_subject_entity_ids = [
        item
        for item in _expected_rejected_claim_subject_entity_ids(scenario, checkpoint)
        if item not in output.rejected_entity_ids and item not in output.context_entity_ids
    ]
    supporting_wrong_entity_claim_ids = [
        item for item in checkpoint.expected_excluded_claim_ids if item in output.supporting_claim_ids
    ]
    selected_noncurrent_claim_ids = _selected_noncurrent_claim_ids(scenario, checkpoint, output)
    required_definition_claim_ids = _required_definition_claim_ids_for_selected_claims(scenario, output)
    missing_definition_claim_ids = [
        claim_id for claim_id in required_definition_claim_ids if claim_id not in output.selected_claim_ids
    ]
    missing_definition_support_claim_ids = [
        claim_id for claim_id in required_definition_claim_ids if claim_id not in output.supporting_claim_ids
    ]
    required_selected_entity_ids = _required_selected_entity_ids_for_policy(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
    )
    missing_selected_entity_role_ids = [
        entity_id for entity_id in required_selected_entity_ids if entity_id not in output.selected_entity_ids
    ]
    selected_object_entity_instead_of_subject_ids = _selected_object_entity_instead_of_subject_ids(
        scenario=scenario,
        output=output,
        missing_subject_entity_ids=missing_selected_entity_role_ids,
    )
    selected_nonrequired_graph_entity_ids = _selected_nonrequired_graph_entity_ids(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        required_selected_entity_ids=required_selected_entity_ids,
    )
    selected_context_only_entity_ids = [
        entity_id for entity_id in output.selected_entity_ids if entity_id in output.context_entity_ids
    ]
    selected_rejected_or_context_entity_ids = _ordered_unique([
        *[entity_id for entity_id in output.selected_entity_ids if entity_id in output.rejected_entity_ids],
        *selected_context_only_entity_ids,
    ])
    missing_selected_subject_entity_ids = []
    if str(_checkpoint_contract_for_type(checkpoint.checkpoint_type).get("selected_entity_role_policy")) in {
        "subject",
        "subject_and_object",
        "active_graph_subjects",
    }:
        missing_selected_subject_entity_ids = missing_selected_entity_role_ids
    supporting_noisy_citation_event_ids = _bad_supporting_event_ids(
        scenario,
        checkpoint,
        output.supporting_citation_event_ids,
    )
    context_only_noise_event_ids = _context_only_noise_event_ids(scenario, output)
    precision_failure_classification = _precision_failure_classifications(
        selected_excluded_ids=selected_excluded_ids,
        supporting_excluded_ids=supporting_excluded_ids,
        missing_rejected_ids=missing_rejected_ids,
        missing_rejected_claim_subject_entity_ids=missing_rejected_claim_subject_entity_ids,
        selected_noncurrent_claim_ids=selected_noncurrent_claim_ids,
        supporting_noisy_citation_event_ids=supporting_noisy_citation_event_ids,
        selected_entity_role_mismatches=missing_selected_entity_role_ids,
    )
    return {
        "missing_expected_ids": missing,
        "extra_selected_ids": extra,
        "answer_match_type": answer_match_type,
        "failure_classification": classifications,
        "selected_excluded_ids": {key: value for key, value in selected_excluded_ids.items() if value},
        "supporting_excluded_ids": {key: value for key, value in supporting_excluded_ids.items() if value},
        "rejected_expected_ids": {key: value for key, value in rejected_expected_ids.items() if value},
        "missing_rejected_ids": {key: value for key, value in missing_rejected_ids.items() if value},
        "missing_rejected_claim_subject_entity_ids": missing_rejected_claim_subject_entity_ids,
        "supporting_wrong_entity_claim_ids": supporting_wrong_entity_claim_ids,
        "selected_noncurrent_claim_ids": selected_noncurrent_claim_ids,
        "required_definition_claim_ids": required_definition_claim_ids,
        "missing_definition_claim_ids": missing_definition_claim_ids,
        "missing_definition_support_claim_ids": missing_definition_support_claim_ids,
        "selected_entity_role_mismatches": missing_selected_entity_role_ids,
        "missing_selected_subject_entity_ids": missing_selected_subject_entity_ids,
        "selected_object_entity_instead_of_subject_ids": selected_object_entity_instead_of_subject_ids,
        "selected_graph_entity_overbreadth": selected_nonrequired_graph_entity_ids,
        "selected_nonrequired_graph_entity_ids": selected_nonrequired_graph_entity_ids,
        "selected_context_only_entity_ids": selected_context_only_entity_ids,
        "selected_rejected_or_context_entity_ids": selected_rejected_or_context_entity_ids,
        "supporting_noisy_citation_event_ids": supporting_noisy_citation_event_ids,
        "context_only_noise_event_ids": context_only_noise_event_ids,
        "role_misclassification": bool(
            selected_noncurrent_claim_ids
            or missing_selected_entity_role_ids
            or supporting_noisy_citation_event_ids
            or any(selected_excluded_ids.values())
            or any(supporting_excluded_ids.values())
        ),
        "precision_failure_classification": precision_failure_classification,
        "required_judge_ids": aggregate.required_judge_ids,
    }

def _precision_failure_classifications(
    *,
    selected_excluded_ids: dict[str, list[str]],
    supporting_excluded_ids: dict[str, list[str]],
    missing_rejected_ids: dict[str, list[str]],
    missing_rejected_claim_subject_entity_ids: list[str],
    selected_noncurrent_claim_ids: list[str],
    supporting_noisy_citation_event_ids: list[str],
    selected_entity_role_mismatches: list[str],
) -> list[str]:
    classifications: set[str] = set()
    if any(selected_excluded_ids.values()):
        classifications.add("selected_excluded_id")
    if any(supporting_excluded_ids.values()):
        classifications.add("supporting_excluded_id")
    if any(missing_rejected_ids.values()):
        classifications.add("missing_rejected_id")
    if missing_rejected_claim_subject_entity_ids:
        classifications.add("missing_rejected_claim_subject_entity")
    if selected_noncurrent_claim_ids:
        classifications.add("selected_noncurrent_claim")
    if selected_entity_role_mismatches:
        classifications.add("entity_role_mismatch")
    if supporting_noisy_citation_event_ids:
        classifications.add("supporting_noisy_or_stale_provenance")
    return sorted(classifications)

def _selected_object_entity_instead_of_subject_ids(
    *,
    scenario: LatentGraphScenario,
    output: SimSystemOutput,
    missing_subject_entity_ids: list[str],
) -> list[str]:
    if not missing_subject_entity_ids:
        return []
    object_ids: list[str] = []
    for claim_id in output.selected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.object.entity_id is None:
            continue
        if claim.subject.entity_id in missing_subject_entity_ids and claim.object.entity_id in output.selected_entity_ids:
            object_ids.append(claim.object.entity_id)
    return _ordered_unique(object_ids)

def _selected_nonrequired_graph_entity_ids(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    required_selected_entity_ids: list[str],
) -> list[str]:
    policy = str(_checkpoint_contract_for_type(checkpoint.checkpoint_type).get("selected_entity_role_policy"))
    if policy != "active_graph_subjects":
        return []
    required = set(required_selected_entity_ids)
    return [
        entity_id
        for entity_id in output.selected_entity_ids
        if entity_id not in required and _is_visible_entity(scenario, entity_id)
    ]

def _answer_match_type(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> str:
    if not bool(_checkpoint_contract_for_type(checkpoint.checkpoint_type).get("answer_required", True)):
        expected = checkpoint.expected_next_action if checkpoint.expected_next_action is not None else checkpoint.expected_answer
        actual = output.next_action if checkpoint.expected_next_action is not None else output.answer
        if expected and not actual:
            return "optional_missing"
        return "diagnostic_only"
    expected = checkpoint.expected_next_action if checkpoint.expected_next_action is not None else checkpoint.expected_answer
    if expected is None:
        return "not_applicable"
    actual = output.next_action if checkpoint.expected_next_action is not None else output.answer
    if not actual:
        return "missing"
    actual_norm = _norm(actual)
    expected_norm = _norm(expected)
    if actual_norm == expected_norm:
        return "exact"
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return "substring"
    expected_entity_ids = set(checkpoint.expected_entity_ids)
    for entity in scenario.entities:
        if entity.entity_id not in expected_entity_ids:
            continue
        names = {entity.canonical_name, *[alias.alias_text for alias in entity.aliases]}
        if any(_norm(name) and _norm(name) in actual_norm for name in names):
            return "semantic_entity"
    return "mismatch"

def _failure_classifications(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
    missing: dict[str, list[str]],
    answer_match_type: str,
) -> list[str]:
    if aggregate.verdict == JudgeVerdict.PASS:
        return []
    classifications: set[str] = set()
    if sim_output_allowed_id_errors(scenario=scenario, output=output):
        classifications.add("hidden_or_expected_leakage")
    if checkpoint.checkpoint_type == "execution_continuation" and (
        output.operation != "next_action" or not output.next_action
    ):
        classifications.add("wrong_output_shape")
    if missing.get("relation_ids"):
        visible_relations = {item for obs in scenario.observations for item in obs.exposed_relation_ids}
        if checkpoint.checkpoint_type == "source_trust_conflict":
            classifications.add("missing_conflict_relation")
        if all(item in visible_relations for item in missing["relation_ids"]):
            classifications.add("missing_visible_relation")
        else:
            classifications.add("relation_context_under_specified")
    if answer_match_type in {"mismatch", "missing"}:
        classifications.add("model_wrong_fact")
    if answer_match_type == "optional_missing":
        classifications.add("graph_answer_optional_missing")
    if answer_match_type == "semantic_entity":
        classifications.add("judge_brittle_answer_match")
    if any("entity_role_mismatch" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("entity_role_mismatch")
        required_entity_ids = _required_selected_entity_ids_for_policy(
            scenario=scenario,
            checkpoint=checkpoint,
            output=output,
        )
        missing_entity_ids = [
            entity_id for entity_id in required_entity_ids if entity_id not in output.selected_entity_ids
        ]
        if _selected_object_entity_instead_of_subject_ids(
            scenario=scenario,
            output=output,
            missing_subject_entity_ids=missing_entity_ids,
        ):
            classifications.add("object_subject_confusion")
    if checkpoint.checkpoint_type == "claim_rekey":
        if any("claim_rekey_error" in vote.failure_buckets for vote in aggregate.votes):
            classifications.add("missing_required_defining_claim")
        if any("missing_provenance" in vote.failure_buckets for vote in aggregate.votes):
            classifications.add("missing_required_defining_provenance")
    if any("supporting_excluded_id" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("wrong_entity_support_used")
    if any("supporting_noncurrent_claim_selected" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("wrong_entity_support_used")
    if checkpoint.checkpoint_type == "execution_continuation" and answer_match_type in {
        "diagnostic_only",
        "optional_missing",
    }:
        classifications.add("execution_text_mismatch_only")
    if any(
        vote.judge_id == "definition_coverage_judge" and vote.verdict == JudgeVerdict.FAIL
        for vote in aggregate.votes
    ):
        classifications.add("missing_definition_claim")
    for item in [*output.entity_ids, *output.claim_ids, *output.relation_ids]:
        if re.search(r"_(alice|bob|carol)(_|$)", item):
            classifications.add("fixture_name_id_mismatch")
    if not classifications:
        classifications.add("unclassified_failure")
    return sorted(classifications)
