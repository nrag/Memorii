"""Shared judge feature extraction for memory evolution simulator checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    LatentClaim,
    LatentGraphScenario,
    ObservabilityLabel,
    OracleCheckpoint,
    SimLifecycleState,
    SimSystemOutput,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    claim_by_id,
    is_visible_entity,
    ordered_unique,
    required_definition_claim_ids_for_selected_claims,
)


class SupportRole(StrEnum):
    """Semantic role an emitted support item plays for a checkpoint."""

    ANSWER_SUPPORT = "answer_support"
    DEFINITION_SUPPORT = "definition_support"
    REJECTION_SUPPORT = "rejection_support"
    CONTEXT_ONLY = "context_only"
    FORBIDDEN_SUPPORT = "forbidden_support"


@dataclass(frozen=True)
class SelectedClaimSupportClosureError:
    """Claim-local support closure failure for selected simulator claims."""

    claim_id: str
    missing_supporting_claim: bool
    expected_event_ids: list[str]
    present_event_ids: list[str]
    missing_event_ids: list[str]
    is_action_state: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "missing_supporting_claim": self.missing_supporting_claim,
            "expected_event_ids": self.expected_event_ids,
            "present_event_ids": self.present_event_ids,
            "missing_event_ids": self.missing_event_ids,
            "is_action_state": self.is_action_state,
        }


def required_selected_entity_ids_for_policy(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    policy: str | None = None,
) -> list[str]:
    selected_policy = policy or checkpoint.task_contract.selected_entity_role_policy
    if selected_policy == "audit_graph_entities":
        return []
    required: list[str] = []
    for claim_id in output.selected_claim_ids:
        claim = claim_by_id(scenario, claim_id)
        if claim is None:
            continue
        if selected_policy in {"subject", "subject_and_object", "active_graph_subjects"}:
            required.append(claim.subject.entity_id)
        if selected_policy in {"object", "subject_and_object"} and claim.object.entity_id:
            required.append(claim.object.entity_id)
    return ordered_unique(required)


def rejected_required_definition_claim_ids(
    scenario: LatentGraphScenario,
    output: SimSystemOutput,
) -> list[str]:
    required_ids = required_definition_claim_ids_for_selected_claims(scenario, output)
    return [claim_id for claim_id in required_ids if claim_id in output.rejected_claim_ids]


def expected_rejected_claim_subject_entity_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
) -> list[str]:
    expected_entities = set(checkpoint.expected_entity_ids)
    required: list[str] = []
    for claim_id in checkpoint.expected_excluded_claim_ids:
        claim = claim_by_id(scenario, claim_id)
        if claim is None:
            continue
        subject_entity_id = claim.subject.entity_id
        if subject_entity_id in expected_entities:
            continue
        if is_visible_entity(scenario, subject_entity_id):
            required.append(subject_entity_id)
    return ordered_unique(required)


def required_definition_claim_ids_for_checkpoint(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> list[str]:
    """Return visible definition/type claims required by selected graph state.

    Definition claims are not ordinary answer facts. They are sometimes required
    to make graph state well-formed, and their evidence can legitimately appear
    in support even when nearby stale/wrong-entity evidence is rejected.
    """

    if (
        checkpoint.task_contract.definition_claim_placement
        == "selected_and_supporting_required"
    ):
        return required_definition_claim_ids_for_selected_claims(scenario, output)
    if checkpoint.checkpoint_type in {"entity_reconstruction", "claim_rekey"}:
        return required_definition_claim_ids_for_selected_claims(scenario, output)
    return [
        claim_id
        for claim_id in output.selected_claim_ids
        if (claim := claim_by_id(scenario, claim_id)) is not None and claim.predicate.predicate_id == "entity_type"
    ]


def claim_support_role_for_checkpoint(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    claim_id: str,
) -> SupportRole:
    """Classify a claim's support role without using hidden oracle channels."""

    if claim_id in required_definition_claim_ids_for_checkpoint(scenario, checkpoint, output):
        return SupportRole.DEFINITION_SUPPORT
    if checkpoint.checkpoint_type == "execution_continuation":
        expected_claim_ids = set(checkpoint.expected_execution_claim_ids)
    else:
        expected_claim_ids = set(checkpoint.expected_claim_ids)
    if claim_id in expected_claim_ids:
        claim = claim_by_id(scenario, claim_id)
        if claim is not None and claim.predicate.predicate_id == "entity_type":
            return SupportRole.DEFINITION_SUPPORT
        return SupportRole.ANSWER_SUPPORT
    if claim_id in checkpoint.expected_excluded_claim_ids:
        return SupportRole.REJECTION_SUPPORT
    claim = claim_by_id(scenario, claim_id)
    if claim is None:
        return SupportRole.CONTEXT_ONLY
    if _claim_is_forbidden_support(checkpoint, claim):
        return SupportRole.FORBIDDEN_SUPPORT
    return SupportRole.CONTEXT_ONLY


def supporting_claim_role_violations(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> dict[str, list[str]]:
    """Return supporting claims that are semantically invalid answer support."""

    violations: dict[str, list[str]] = {}
    for claim_id in output.supporting_claim_ids:
        role = claim_support_role_for_checkpoint(scenario, checkpoint, output, claim_id)
        if role not in {SupportRole.REJECTION_SUPPORT, SupportRole.FORBIDDEN_SUPPORT}:
            continue
        violations.setdefault(role.value, []).append(claim_id)
    if checkpoint.checkpoint_type == "execution_continuation":
        execution_context_support = [
            claim_id
            for claim_id in output.supporting_claim_ids
            if (claim := claim_by_id(scenario, claim_id)) is not None and claim.claim_kind != "action_state"
        ]
        if execution_context_support:
            violations["execution_context_support"] = execution_context_support
    wrong_subject_claims = supporting_wrong_subject_claim_ids(scenario, checkpoint, output)
    if wrong_subject_claims:
        violations["wrong_subject_support"] = wrong_subject_claims
    return {key: sorted(set(value)) for key, value in violations.items()}


def supporting_wrong_subject_claim_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> list[str]:
    """Return supporting claims whose subject is not the selected target subject."""

    if checkpoint.checkpoint_type != "entity_split_repair":
        return []
    selected_subject_ids = set(
        required_selected_entity_ids_for_policy(
            scenario=scenario,
            checkpoint=checkpoint,
            output=output,
        )
    )
    if not selected_subject_ids:
        return []
    wrong: list[str] = []
    for claim_id in output.supporting_claim_ids:
        claim = claim_by_id(scenario, claim_id)
        if claim is None:
            continue
        if claim.subject.entity_id not in selected_subject_ids:
            wrong.append(claim_id)
    return ordered_unique(wrong)


def supporting_wrong_subject_entity_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> list[str]:
    wrong_entities: list[str] = []
    for claim_id in supporting_wrong_subject_claim_ids(scenario, checkpoint, output):
        claim = claim_by_id(scenario, claim_id)
        if claim is not None:
            wrong_entities.append(claim.subject.entity_id)
    return ordered_unique(wrong_entities)


def supporting_disambiguation_claim_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> list[str]:
    if checkpoint.checkpoint_type != "entity_split_repair":
        return []
    return supporting_wrong_subject_claim_ids(scenario, checkpoint, output)


def event_support_roles_for_checkpoint(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    event_id: str,
) -> list[SupportRole]:
    """Classify why an event appears relevant to a checkpoint.

    The same surface event may define the entity and mention stale/rejected
    material. Judges should only fail support/rejection citation overlap when
    the overlapped event is actually serving rejected or forbidden support.
    """

    roles: list[SupportRole] = []
    expected_citations = (
        checkpoint.expected_execution_citation_event_ids
        if checkpoint.checkpoint_type == "execution_continuation"
        else checkpoint.expected_citation_event_ids
    )
    if event_id in expected_citations:
        roles.append(SupportRole.ANSWER_SUPPORT)
    for claim in scenario.claims:
        if event_id not in claim.evidence.source_event_ids:
            continue
        role = claim_support_role_for_checkpoint(scenario, checkpoint, output, claim.claim_id)
        roles.append(role)
    if not roles:
        roles.append(SupportRole.CONTEXT_ONLY)
    return list(dict.fromkeys(roles))


def supporting_rejection_provenance_overlap_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> list[str]:
    """Return support/rejection citation overlaps that are semantically fatal."""

    overlapped = [
        event_id for event_id in output.supporting_citation_event_ids if event_id in output.rejection_citation_event_ids
    ]
    bad_roles = {SupportRole.REJECTION_SUPPORT, SupportRole.FORBIDDEN_SUPPORT}
    safe_roles = {SupportRole.ANSWER_SUPPORT, SupportRole.DEFINITION_SUPPORT}
    bad: list[str] = []
    for event_id in overlapped:
        roles = set(event_support_roles_for_checkpoint(scenario, checkpoint, output, event_id))
        if roles & bad_roles and not roles & safe_roles:
            bad.append(event_id)
    return ordered_unique(bad)


def supporting_rejection_provenance_warning_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> list[str]:
    overlapped = [
        event_id for event_id in output.supporting_citation_event_ids if event_id in output.rejection_citation_event_ids
    ]
    critical = set(supporting_rejection_provenance_overlap_ids(scenario, checkpoint, output))
    return [event_id for event_id in overlapped if event_id not in critical]


def _claim_is_forbidden_support(checkpoint: OracleCheckpoint, claim: LatentClaim) -> bool:
    if checkpoint.checkpoint_type == "historical_truth":
        return False
    bad_states = {
        SimLifecycleState.SUPERSEDED,
        SimLifecycleState.INVALIDATED,
        SimLifecycleState.EXPIRED,
        SimLifecycleState.EVIDENCE_ONLY,
        SimLifecycleState.ARCHIVED,
    }
    return claim.lifecycle.state in bad_states or claim.observability == ObservabilityLabel.AMBIGUOUS


def selected_claim_support_closure_errors(
    scenario: LatentGraphScenario,
    output: SimSystemOutput,
) -> list[SelectedClaimSupportClosureError]:
    supporting_claims = set(output.supporting_claim_ids)
    supporting_events = set(output.supporting_citation_event_ids)
    errors: list[SelectedClaimSupportClosureError] = []
    for claim_id in output.selected_claim_ids:
        claim = claim_by_id(scenario, claim_id)
        if claim is None:
            continue
        expected_event_ids = ordered_unique([event_id for event_id in claim.evidence.source_event_ids if event_id])
        present_event_ids = [event_id for event_id in expected_event_ids if event_id in supporting_events]
        missing_event_ids = [event_id for event_id in expected_event_ids if event_id not in supporting_events]
        missing_supporting_claim = claim_id not in supporting_claims
        if not missing_supporting_claim and not missing_event_ids:
            continue
        errors.append(
            SelectedClaimSupportClosureError(
                claim_id=claim_id,
                missing_supporting_claim=missing_supporting_claim,
                expected_event_ids=expected_event_ids,
                present_event_ids=present_event_ids,
                missing_event_ids=missing_event_ids,
                is_action_state=claim.claim_kind == "action_state",
            )
        )
    return errors


def selected_claim_ids_missing_support(
    errors: list[SelectedClaimSupportClosureError],
) -> list[str]:
    return ordered_unique([error.claim_id for error in errors if error.missing_supporting_claim])


def selected_claim_evidence_event_ids_missing_support(
    errors: list[SelectedClaimSupportClosureError],
) -> list[str]:
    return ordered_unique([event_id for error in errors for event_id in error.missing_event_ids])


def selected_action_state_event_ids_missing_support(
    errors: list[SelectedClaimSupportClosureError],
) -> list[str]:
    return ordered_unique(
        [event_id for error in errors if error.is_action_state for event_id in error.missing_event_ids]
    )
