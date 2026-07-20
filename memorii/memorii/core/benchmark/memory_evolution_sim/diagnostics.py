"""Simulator diagnostics and failure-classification helpers."""

from __future__ import annotations

import re
from typing import TypedDict

from memorii.core.benchmark.memory_evolution_sim import judge_features
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    JudgeAggregate,
    JudgeVerdict,
    LatentGraphScenario,
    ObservabilityLabel,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    bad_supporting_event_ids,
    claim_by_id,
    hidden_answer_leaks,
    is_visible_entity,
    normalize_sim_text,
    ordered_unique,
    role_claim_ids,
    role_entity_ids,
    role_relation_ids,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    context_only_noise_event_ids as find_context_only_noise_event_ids,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    selected_noncurrent_claim_ids as find_selected_noncurrent_claim_ids,
)


class ChannelOverlapDiagnostics(TypedDict):
    critical: list[str]
    warning: list[str]
    critical_ids: dict[str, list[str]]
    warning_ids: dict[str, list[str]]


class SelectedClaimSupportClosureDiagnostics(TypedDict):
    claim_id: str
    missing_supporting_claim: bool
    expected_event_ids: list[str]
    present_event_ids: list[str]
    missing_event_ids: list[str]
    is_action_state: bool


def sim_output_allowed_id_errors(*, scenario: LatentGraphScenario, output: SimSystemOutput) -> list[str]:
    visible_entities = {item for obs in scenario.observations for item in obs.exposed_entity_ids}
    visible_claims = {item for obs in scenario.observations for item in obs.exposed_claim_ids}
    visible_relations = {item for obs in scenario.observations for item in obs.exposed_relation_ids}
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
    event_ids = {obs.event_id for obs in scenario.observations}
    for field_name, actual in [
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
    asserted = set(role_entity_ids(output)) | set(role_claim_ids(output)) | set(role_relation_ids(output))
    hallucinated = sorted(asserted & hidden_ids)
    if hallucinated:
        errors.append(f"hidden_ids_asserted:{','.join(hallucinated)}")
    answer_leaks = hidden_answer_leaks(scenario, output)
    if answer_leaks:
        errors.append(f"hidden_answer_leak:{','.join(answer_leaks)}")
    return errors


def _diagnostic_expected_entity_ids(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_entity_ids)
    return list(checkpoint.expected_entity_ids)


def _diagnostic_expected_claim_ids(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_claim_ids)
    return list(checkpoint.expected_claim_ids)


def _diagnostic_expected_citation_event_ids(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_citation_event_ids)
    return list(checkpoint.expected_citation_event_ids)


def sim_checkpoint_diagnostics(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
) -> dict[str, object]:
    required_definition_claim_ids = judge_features.required_definition_claim_ids_for_checkpoint(
        scenario,
        checkpoint,
        output,
    )
    allowed_definition_citation_event_ids = ordered_unique([
        event_id
        for claim_id in required_definition_claim_ids
        if (claim := claim_by_id(scenario, claim_id)) is not None
        for event_id in claim.evidence.source_event_ids
    ])
    expected_by_type = {
        "entity_ids": _diagnostic_expected_entity_ids(checkpoint),
        "claim_ids": _diagnostic_expected_claim_ids(checkpoint),
        "relation_ids": checkpoint.expected_relation_ids,
        "citation_event_ids": _diagnostic_expected_citation_event_ids(checkpoint),
    }
    actual_coverage_by_type = {
        "entity_ids": output.selected_entity_ids,
        "claim_ids": output.selected_claim_ids,
        "relation_ids": ordered_unique([
            *output.selected_relation_ids,
            *output.supporting_relation_ids,
            *output.context_relation_ids,
            *output.rejected_relation_ids,
        ]),
        "citation_event_ids": output.supporting_citation_event_ids,
    }
    selected_by_type = {
        "entity_ids": output.selected_entity_ids,
        "claim_ids": output.selected_claim_ids,
        "relation_ids": output.selected_relation_ids,
        "citation_event_ids": output.supporting_citation_event_ids,
    }
    allowed_extra_by_type = {
        "entity_ids": [],
        "claim_ids": required_definition_claim_ids,
        "relation_ids": [],
        "citation_event_ids": allowed_definition_citation_event_ids,
    }
    missing = {
        key: [item for item in expected if item not in actual_coverage_by_type[key]]
        for key, expected in expected_by_type.items()
        if [item for item in expected if item not in actual_coverage_by_type[key]]
    }
    extra = {
        key: [
            item
            for item in selected_by_type[key]
            if item not in expected_by_type[key] and item not in allowed_extra_by_type[key]
        ]
        for key in selected_by_type
        if [
            item
            for item in selected_by_type[key]
            if item not in expected_by_type[key] and item not in allowed_extra_by_type[key]
        ]
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
            for item in ordered_unique([
                *checkpoint.expected_excluded_entity_ids,
                *judge_features.expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
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
            for item in ordered_unique([
                *checkpoint.expected_excluded_entity_ids,
                *judge_features.expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
            ])
            if item not in output.rejected_entity_ids and item not in output.context_entity_ids
        ],
    }
    if not checkpoint.checkpoint_contract.excluded_ids_must_be_rejected_or_contextualized:
        missing_rejected_ids = {"claim_ids": [], "entity_ids": []}
    missing_rejected_claim_subject_entity_ids = [
        item
        for item in judge_features.expected_rejected_claim_subject_entity_ids(scenario, checkpoint)
        if item not in output.rejected_entity_ids and item not in output.context_entity_ids
    ]
    supporting_wrong_entity_claim_ids = [
        item for item in checkpoint.expected_excluded_claim_ids if item in output.supporting_claim_ids
    ]
    supporting_wrong_subject_claim_ids = judge_features.supporting_wrong_subject_claim_ids(
        scenario,
        checkpoint,
        output,
    )
    supporting_wrong_subject_entity_ids = judge_features.supporting_wrong_subject_entity_ids(
        scenario,
        checkpoint,
        output,
    )
    supporting_disambiguation_claim_ids = judge_features.supporting_disambiguation_claim_ids(
        scenario,
        checkpoint,
        output,
    )
    selected_noncurrent_claim_ids = find_selected_noncurrent_claim_ids(scenario, checkpoint, output)
    missing_definition_claim_ids = [
        claim_id for claim_id in required_definition_claim_ids if claim_id not in output.selected_claim_ids
    ]
    missing_definition_support_claim_ids = [
        claim_id for claim_id in required_definition_claim_ids if claim_id not in output.supporting_claim_ids
    ]
    rejected_required_definition_claim_ids = [
        claim_id for claim_id in required_definition_claim_ids if claim_id in output.rejected_claim_ids
    ]
    required_selected_entity_ids = judge_features.required_selected_entity_ids_for_policy(
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
    selected_rejected_or_context_entity_ids = ordered_unique([
        *[entity_id for entity_id in output.selected_entity_ids if entity_id in output.rejected_entity_ids],
        *selected_context_only_entity_ids,
    ])
    missing_selected_subject_entity_ids = []
    if checkpoint.checkpoint_contract.selected_entity_role_policy in {
        "subject",
        "subject_and_object",
        "active_graph_subjects",
    }:
        missing_selected_subject_entity_ids = missing_selected_entity_role_ids
    supporting_noisy_citation_event_ids = bad_supporting_event_ids(
        scenario,
        checkpoint,
        output.supporting_citation_event_ids,
    )
    support_closure_errors = judge_features.selected_claim_support_closure_errors(scenario, output)
    selected_claim_support_closure_error_rows: list[SelectedClaimSupportClosureDiagnostics] = [
        {
            "claim_id": error.claim_id,
            "missing_supporting_claim": error.missing_supporting_claim,
            "expected_event_ids": error.expected_event_ids,
            "present_event_ids": error.present_event_ids,
            "missing_event_ids": error.missing_event_ids,
            "is_action_state": error.is_action_state,
        }
        for error in support_closure_errors
    ]
    selected_claim_ids_missing_support = judge_features.selected_claim_ids_missing_support(support_closure_errors)
    selected_claim_evidence_event_ids_missing_support = judge_features.selected_claim_evidence_event_ids_missing_support(
        support_closure_errors,
    )
    selected_action_state_event_ids_missing_support = judge_features.selected_action_state_event_ids_missing_support(
        support_closure_errors,
    )
    context_only_noise_event_ids = find_context_only_noise_event_ids(scenario, output)
    supporting_role_violations = judge_features.supporting_claim_role_violations(scenario, checkpoint, output)
    channel_overlap = _channel_overlap_diagnostics(scenario, checkpoint, output)
    precision_failure_classification = _precision_failure_classifications(
        selected_excluded_ids=selected_excluded_ids,
        supporting_excluded_ids=supporting_excluded_ids,
        missing_rejected_ids=missing_rejected_ids,
        missing_rejected_claim_subject_entity_ids=missing_rejected_claim_subject_entity_ids,
        selected_noncurrent_claim_ids=selected_noncurrent_claim_ids,
        supporting_noisy_citation_event_ids=supporting_noisy_citation_event_ids,
        selected_entity_role_mismatches=missing_selected_entity_role_ids,
        selected_claim_ids_missing_support=selected_claim_ids_missing_support,
        selected_claim_evidence_event_ids_missing_support=selected_claim_evidence_event_ids_missing_support,
        selected_action_state_event_ids_missing_support=selected_action_state_event_ids_missing_support,
        supporting_role_violations=supporting_role_violations,
        supporting_wrong_subject_claim_ids=supporting_wrong_subject_claim_ids,
        supporting_disambiguation_claim_ids=supporting_disambiguation_claim_ids,
        channel_overlap=channel_overlap,
    )
    return {
        "missing_expected_ids": missing,
        "extra_selected_ids": extra,
        "allowed_definition_selected_ids": {
            "claim_ids": [
                claim_id for claim_id in output.selected_claim_ids if claim_id in required_definition_claim_ids
            ],
            "citation_event_ids": [
                event_id
                for event_id in output.supporting_citation_event_ids
                if event_id in allowed_definition_citation_event_ids
            ],
        },
        "allowed_context_selected_ids": {},
        "forbidden_selected_ids": {},
        "answer_match_type": answer_match_type,
        "failure_classification": classifications,
        "selected_excluded_ids": {key: value for key, value in selected_excluded_ids.items() if value},
        "supporting_excluded_ids": {key: value for key, value in supporting_excluded_ids.items() if value},
        "rejected_expected_ids": {key: value for key, value in rejected_expected_ids.items() if value},
        "missing_rejected_ids": {key: value for key, value in missing_rejected_ids.items() if value},
        "missing_rejected_claim_subject_entity_ids": missing_rejected_claim_subject_entity_ids,
        "supporting_wrong_entity_claim_ids": supporting_wrong_entity_claim_ids,
        "supporting_wrong_subject_claim_ids": supporting_wrong_subject_claim_ids,
        "supporting_wrong_subject_entity_ids": supporting_wrong_subject_entity_ids,
        "supporting_disambiguation_claim_ids": supporting_disambiguation_claim_ids,
        "missing_wrong_entity_rejection_claim_ids": missing_rejected_ids["claim_ids"],
        "missing_wrong_entity_rejection_subject_ids": missing_rejected_claim_subject_entity_ids,
        "selected_noncurrent_claim_ids": selected_noncurrent_claim_ids,
        "required_definition_claim_ids": required_definition_claim_ids,
        "missing_definition_claim_ids": missing_definition_claim_ids,
        "missing_definition_support_claim_ids": missing_definition_support_claim_ids,
        "rejected_required_definition_claim_ids": rejected_required_definition_claim_ids,
        "selected_entity_role_mismatches": missing_selected_entity_role_ids,
        "missing_selected_subject_entity_ids": missing_selected_subject_entity_ids,
        "selected_object_entity_instead_of_subject_ids": selected_object_entity_instead_of_subject_ids,
        "selected_graph_entity_overbreadth": selected_nonrequired_graph_entity_ids,
        "selected_nonrequired_graph_entity_ids": selected_nonrequired_graph_entity_ids,
        "selected_context_only_entity_ids": selected_context_only_entity_ids,
        "selected_rejected_or_context_entity_ids": selected_rejected_or_context_entity_ids,
        "supporting_noisy_citation_event_ids": supporting_noisy_citation_event_ids,
        "selected_claim_support_closure_errors": selected_claim_support_closure_error_rows,
        "selected_claim_ids_missing_support": selected_claim_ids_missing_support,
        "selected_claim_evidence_event_ids_missing_support": selected_claim_evidence_event_ids_missing_support,
        "selected_action_state_event_ids_missing_support": selected_action_state_event_ids_missing_support,
        "context_only_noise_event_ids": context_only_noise_event_ids,
        "supporting_role_violations": supporting_role_violations,
        "supporting_rejection_provenance_overlap": {
            "citation_event_ids": judge_features.supporting_rejection_provenance_overlap_ids(
                scenario,
                checkpoint,
                output,
            )
        },
        "channel_overlap": channel_overlap,
        "role_misclassification": bool(
            selected_noncurrent_claim_ids
            or missing_selected_entity_role_ids
            or supporting_noisy_citation_event_ids
            or any(selected_excluded_ids.values())
            or any(supporting_excluded_ids.values())
            or any(supporting_role_violations.values())
            or supporting_wrong_subject_claim_ids
            or selected_claim_ids_missing_support
            or selected_claim_evidence_event_ids_missing_support
            or channel_overlap["critical"]
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
    selected_claim_ids_missing_support: list[str],
    selected_claim_evidence_event_ids_missing_support: list[str],
    selected_action_state_event_ids_missing_support: list[str],
    supporting_role_violations: dict[str, list[str]],
    supporting_wrong_subject_claim_ids: list[str],
    supporting_disambiguation_claim_ids: list[str],
    channel_overlap: ChannelOverlapDiagnostics,
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
        classifications.add("missing_wrong_entity_rejection")
    if selected_noncurrent_claim_ids:
        classifications.add("selected_noncurrent_claim")
    if selected_entity_role_mismatches:
        classifications.add("entity_role_mismatch")
    if supporting_noisy_citation_event_ids:
        classifications.add("supporting_noisy_or_stale_provenance")
    if selected_claim_ids_missing_support:
        classifications.add("selected_claim_support_missing")
    if selected_claim_evidence_event_ids_missing_support:
        classifications.add("selected_claim_provenance_missing")
    if selected_action_state_event_ids_missing_support:
        classifications.add("active_action_provenance_missing")
    if any(supporting_role_violations.values()):
        classifications.add("supporting_role_violation")
    if supporting_role_violations.get("execution_context_support"):
        classifications.add("execution_context_claim_used_as_support")
    if supporting_wrong_subject_claim_ids:
        classifications.add("wrong_entity_support_used")
    if supporting_disambiguation_claim_ids:
        classifications.add("disambiguation_evidence_used_as_support")
    for bucket in channel_overlap["critical"]:
        classifications.add(str(bucket))
    return sorted(classifications)


def _channel_overlap_diagnostics(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> ChannelOverlapDiagnostics:
    required_definition_claim_ids = judge_features.required_definition_claim_ids_for_checkpoint(
        scenario,
        checkpoint,
        output,
    )
    rejected_required_definition_claim_ids = [
        claim_id for claim_id in required_definition_claim_ids if claim_id in output.rejected_claim_ids
    ]
    critical_supporting_rejection_events = judge_features.supporting_rejection_provenance_overlap_ids(
        scenario,
        checkpoint,
        output,
    )
    warning_supporting_rejection_events = judge_features.supporting_rejection_provenance_warning_ids(
        scenario,
        checkpoint,
        output,
    )
    critical = {
        "selected_rejected_claim_ids": [
            claim_id for claim_id in output.selected_claim_ids if claim_id in output.rejected_claim_ids
        ],
        "supporting_rejected_claim_ids": [
            claim_id for claim_id in output.supporting_claim_ids if claim_id in output.rejected_claim_ids
        ],
        "rejected_required_definition_claim_ids": rejected_required_definition_claim_ids,
        "supporting_rejection_citation_event_ids": critical_supporting_rejection_events,
    }
    warning = {
        "selected_context_claim_ids": [
            claim_id for claim_id in output.selected_claim_ids if claim_id in output.context_claim_ids
        ],
        "supporting_context_claim_ids": [
            claim_id for claim_id in output.supporting_claim_ids if claim_id in output.context_claim_ids
        ],
        "selected_context_entity_ids": [
            entity_id for entity_id in output.selected_entity_ids if entity_id in output.context_entity_ids
        ],
        "supporting_context_citation_event_ids": [
            event_id
            for event_id in output.supporting_citation_event_ids
            if event_id in output.context_citation_event_ids
        ],
        "supporting_rejection_definition_citation_event_ids": warning_supporting_rejection_events,
    }
    critical_buckets = []
    if critical["selected_rejected_claim_ids"]:
        critical_buckets.append("selected_rejected_channel_overlap")
    if critical["supporting_rejected_claim_ids"]:
        critical_buckets.append("supporting_rejected_channel_overlap")
    if critical["rejected_required_definition_claim_ids"]:
        critical_buckets.append("definition_claim_rejected")
    if critical["supporting_rejection_citation_event_ids"]:
        critical_buckets.append("supporting_rejection_provenance_overlap")
    warning_buckets = []
    if any(warning.values()):
        warning_buckets.append("role_channel_context_overlap")
    return {
        "critical": critical_buckets,
        "warning": warning_buckets,
        "critical_ids": {key: value for key, value in critical.items() if value},
        "warning_ids": {key: value for key, value in warning.items() if value},
    }

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
        claim = claim_by_id(scenario, claim_id)
        if claim is None or claim.object.entity_id is None:
            continue
        if claim.subject.entity_id in missing_subject_entity_ids and claim.object.entity_id in output.selected_entity_ids:
            object_ids.append(claim.object.entity_id)
    return ordered_unique(object_ids)

def _selected_nonrequired_graph_entity_ids(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    required_selected_entity_ids: list[str],
) -> list[str]:
    policy = checkpoint.checkpoint_contract.selected_entity_role_policy
    if policy != "active_graph_subjects":
        return []
    required = set(required_selected_entity_ids)
    return [
        entity_id
        for entity_id in output.selected_entity_ids
        if entity_id not in required and is_visible_entity(scenario, entity_id)
    ]

def _answer_match_type(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> str:
    if not checkpoint.checkpoint_contract.answer_required:
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
    actual_norm = normalize_sim_text(actual)
    expected_norm = normalize_sim_text(expected)
    if actual_norm == expected_norm:
        return "exact"
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return "substring"
    expected_entity_ids = set(checkpoint.expected_entity_ids)
    for entity in scenario.entities:
        if entity.entity_id not in expected_entity_ids:
            continue
        names = {entity.canonical_name, *[alias.alias_text for alias in entity.aliases]}
        if any(normalize_sim_text(name) and normalize_sim_text(name) in actual_norm for name in names):
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
        required_entity_ids = judge_features.required_selected_entity_ids_for_policy(
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
    if any("supporting_role_violation" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("supporting_role_violation")
    if any("disambiguation_evidence_used_as_support" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("disambiguation_evidence_used_as_support")
    if any("supporting_rejected_channel_overlap" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("supporting_rejected_channel_overlap")
    if any("selected_rejected_channel_overlap" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("selected_rejected_channel_overlap")
    if any("definition_claim_rejected" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("definition_claim_rejected")
    if any("supporting_rejection_provenance_overlap" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("supporting_rejection_provenance_overlap")
    if any("selected_claim_support_missing" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("selected_claim_support_missing")
    if any("selected_claim_provenance_missing" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("selected_claim_provenance_missing")
    if any("execution_state_support_missing" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("execution_state_support_missing")
    if any("active_action_provenance_missing" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("active_action_provenance_missing")
    if (
        checkpoint.checkpoint_type == "execution_continuation"
        and answer_match_type in {"mismatch", "missing"}
        and any(vote.judge_id == "answer_judge" and vote.verdict == JudgeVerdict.FAIL for vote in aggregate.votes)
    ):
        classifications.add("execution_text_mismatch_only")
    if any(
        vote.judge_id == "definition_coverage_judge" and vote.verdict == JudgeVerdict.FAIL
        for vote in aggregate.votes
    ):
        classifications.add("missing_definition_claim")
    for item in [*role_entity_ids(output), *role_claim_ids(output), *role_relation_ids(output)]:
        if re.search(r"_(alice|bob|carol)(_|$)", item):
            classifications.add("fixture_name_id_mismatch")
    if not classifications:
        classifications.add("unclassified_failure")
    return sorted(classifications)
