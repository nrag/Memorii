"""Scenario generation for the memory evolution simulator."""

from __future__ import annotations

from typing import Literal

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    ReconstructionTaskContract,
)


def truth_contract(
    *,
    historical: bool = False,
    answer_projection_policy: Literal["claim_object", "claim_subject", "none"] = "claim_object",
) -> ReconstructionTaskContract:
    return ReconstructionTaskContract(
        answer_projection_policy=answer_projection_policy,
        allow_stale_selected_claims=historical,
        supporting_citations_must_be_direct_current_evidence=not historical,
    )


def graph_contract(
    *,
    selected_entity_role_policy: Literal["active_graph_subjects", "audit_graph_entities"] = "active_graph_subjects",
    definition_claim_placement: Literal[
        "selected_and_supporting_required",
        "context_or_support",
    ] = "context_or_support",
    belief_ranking_policy: Literal["required", "forbidden"] = "forbidden",
) -> ReconstructionTaskContract:
    return ReconstructionTaskContract(
        allowed_operations=["graph_reconstruction"],
        answer_required=False,
        answer_projection_policy="graph_channels_only",
        selected_entity_role_policy=selected_entity_role_policy,
        definition_claim_placement=definition_claim_placement,
        belief_ranking_policy=belief_ranking_policy,
    )


def source_trust_contract() -> ReconstructionTaskContract:
    return ReconstructionTaskContract(
        conflict_relation_ids_belong_in=["context_relation_ids", "supporting_relation_ids"],
    )


def modality_suppression_contract() -> ReconstructionTaskContract:
    return ReconstructionTaskContract(answer_required=False, answer_projection_policy="none")


def entity_split_contract(
    *,
    answer_projection_policy: Literal["claim_object", "claim_subject"] = "claim_object",
) -> ReconstructionTaskContract:
    return ReconstructionTaskContract(
        answer_projection_policy=answer_projection_policy,
        wrong_entity_claims_belong_in=["rejected", "context"],
    )


def execution_contract() -> ReconstructionTaskContract:
    return ReconstructionTaskContract(
        allowed_operations=["next_action"],
        answer_required=False,
        answer_projection_policy="next_action",
        requires_next_action=True,
    )
