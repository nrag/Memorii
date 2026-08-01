"""Authoritative algebra for compiled simulator output channels."""

from __future__ import annotations

from enum import StrEnum

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    SimSystemOutput,
    VisibleClaimCandidate,
)


class ChannelAlgebraViolation(StrEnum):
    DUPLICATE_CHANNEL_ID = "duplicate_channel_id"
    SELECTED_SUPPORTING_CLAIMS_DIFFER = "selected_supporting_claims_differ"
    SELECTED_RELATIONS_NOT_SUPPORTING = "selected_relations_not_supporting"
    CLAIM_CHANNEL_OVERLAP = "claim_channel_overlap"
    ENTITY_CHANNEL_OVERLAP = "entity_channel_overlap"
    RELATION_CHANNEL_OVERLAP = "relation_channel_overlap"
    CITATION_CHANNEL_OVERLAP = "citation_channel_overlap"


def selected_entity_ids_for_claims(
    *,
    selected_claims: list[VisibleClaimCandidate],
    role_policy: str,
) -> list[str]:
    """Project selected entities according to the visible task contract."""

    if role_policy == "audit_graph_entities":
        return []
    entity_ids: list[str] = []
    for claim in selected_claims:
        if role_policy in {"subject", "subject_and_object", "active_graph_subjects"}:
            entity_ids.append(claim.subject_entity_id)
        if role_policy in {"object", "subject_and_object"} and claim.object_entity_id:
            entity_ids.append(claim.object_entity_id)
    if role_policy not in {
        "subject",
        "object",
        "subject_and_object",
        "active_graph_subjects",
    }:
        raise ValueError(f"unsupported selected entity role policy: {role_policy}")
    return list(dict.fromkeys(entity_ids))


def channel_algebra_violations(output: SimSystemOutput) -> tuple[ChannelAlgebraViolation, ...]:
    """Return every equality, subset, uniqueness, or disjointness violation."""

    violations: list[ChannelAlgebraViolation] = []
    channel_values = (
        output.selected_entity_ids,
        output.selected_claim_ids,
        output.selected_relation_ids,
        output.supporting_claim_ids,
        output.supporting_relation_ids,
        output.supporting_citation_event_ids,
        output.rejected_entity_ids,
        output.rejected_claim_ids,
        output.rejected_relation_ids,
        output.rejection_citation_event_ids,
        output.context_entity_ids,
        output.context_claim_ids,
        output.context_relation_ids,
        output.context_citation_event_ids,
    )
    if any(len(values) != len(set(values)) for values in channel_values):
        violations.append(ChannelAlgebraViolation.DUPLICATE_CHANNEL_ID)

    selected_claims = set(output.selected_claim_ids)
    supporting_claims = set(output.supporting_claim_ids)
    context_claims = set(output.context_claim_ids)
    rejected_claims = set(output.rejected_claim_ids)
    if selected_claims != supporting_claims:
        violations.append(ChannelAlgebraViolation.SELECTED_SUPPORTING_CLAIMS_DIFFER)
    if _overlap_exists(selected_claims, context_claims, rejected_claims):
        violations.append(ChannelAlgebraViolation.CLAIM_CHANNEL_OVERLAP)

    selected_entities = set(output.selected_entity_ids)
    context_entities = set(output.context_entity_ids)
    rejected_entities = set(output.rejected_entity_ids)
    if _overlap_exists(selected_entities, context_entities, rejected_entities):
        violations.append(ChannelAlgebraViolation.ENTITY_CHANNEL_OVERLAP)

    selected_relations = set(output.selected_relation_ids)
    supporting_relations = set(output.supporting_relation_ids)
    context_relations = set(output.context_relation_ids)
    rejected_relations = set(output.rejected_relation_ids)
    if not selected_relations.issubset(supporting_relations):
        violations.append(ChannelAlgebraViolation.SELECTED_RELATIONS_NOT_SUPPORTING)
    if _overlap_exists(supporting_relations, context_relations, rejected_relations):
        violations.append(ChannelAlgebraViolation.RELATION_CHANNEL_OVERLAP)

    if _overlap_exists(
        set(output.supporting_citation_event_ids),
        set(output.context_citation_event_ids),
        set(output.rejection_citation_event_ids),
    ):
        violations.append(ChannelAlgebraViolation.CITATION_CHANNEL_OVERLAP)
    return tuple(dict.fromkeys(violations))


def require_valid_channel_algebra(output: SimSystemOutput) -> None:
    """Fail compilation when output channels are not mutually consistent."""

    violations = channel_algebra_violations(output)
    if violations:
        codes = ",".join(item.value for item in violations)
        raise ValueError(f"compiled simulator channel algebra failed: {codes}")


def _overlap_exists(*values: set[str]) -> bool:
    return any(left & right for index, left in enumerate(values) for right in values[index + 1 :])
