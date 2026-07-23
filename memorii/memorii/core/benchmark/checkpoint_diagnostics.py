"""Typed simulator and runtime checkpoint diagnostics."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChannelOverlapSection(BaseModel):
    """Role-channel overlap diagnostics for selected/support/rejected/context views."""

    critical: list[str] = Field(default_factory=list)
    warning: list[str] = Field(default_factory=list)
    critical_ids: dict[str, list[str]] = Field(default_factory=dict)
    warning_ids: dict[str, list[str]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class SelectedClaimSupportClosureErrorSection(BaseModel):
    """Claim-local selected/supporting/citation closure diagnostics."""

    claim_id: str
    missing_supporting_claim: bool
    expected_event_ids: list[str] = Field(default_factory=list)
    present_event_ids: list[str] = Field(default_factory=list)
    missing_event_ids: list[str] = Field(default_factory=list)
    is_action_state: bool

    model_config = ConfigDict(extra="forbid")


class CheckpointDiagnosticsSection(BaseModel):
    """Complete diagnostics emitted by simulator and runtime checkpoint judges."""

    missing_expected_ids: dict[str, list[str]]
    extra_selected_ids: dict[str, list[str]]
    allowed_definition_selected_ids: dict[str, list[str]]
    allowed_context_selected_ids: dict[str, list[str]]
    forbidden_selected_ids: dict[str, list[str]]
    answer_match_type: str
    failure_classification: list[str]
    selected_excluded_ids: dict[str, list[str]]
    supporting_excluded_ids: dict[str, list[str]]
    rejected_expected_ids: dict[str, list[str]]
    missing_rejected_ids: dict[str, list[str]]
    missing_rejected_claim_subject_entity_ids: list[str]
    supporting_wrong_entity_claim_ids: list[str]
    supporting_wrong_subject_claim_ids: list[str]
    supporting_wrong_subject_entity_ids: list[str]
    supporting_disambiguation_claim_ids: list[str]
    missing_wrong_entity_rejection_claim_ids: list[str]
    missing_wrong_entity_rejection_subject_ids: list[str]
    selected_noncurrent_claim_ids: list[str]
    required_definition_claim_ids: list[str]
    missing_definition_claim_ids: list[str]
    missing_definition_support_claim_ids: list[str]
    rejected_required_definition_claim_ids: list[str]
    selected_entity_role_mismatches: list[str]
    missing_selected_subject_entity_ids: list[str]
    selected_object_entity_instead_of_subject_ids: list[str]
    selected_graph_entity_overbreadth: list[str]
    selected_nonrequired_graph_entity_ids: list[str]
    selected_context_only_entity_ids: list[str]
    selected_rejected_or_context_entity_ids: list[str]
    supporting_noisy_citation_event_ids: list[str]
    selected_claim_support_closure_errors: list[SelectedClaimSupportClosureErrorSection]
    selected_claim_ids_missing_support: list[str]
    selected_claim_evidence_event_ids_missing_support: list[str]
    selected_action_state_event_ids_missing_support: list[str]
    context_only_noise_event_ids: list[str]
    supporting_role_violations: dict[str, list[str]]
    supporting_rejection_provenance_overlap: dict[str, list[str]]
    channel_overlap: ChannelOverlapSection
    role_misclassification: bool
    precision_failure_classification: list[str]
    required_judge_ids: list[str]

    model_config = ConfigDict(extra="forbid")

    def to_flat_fields(self) -> dict[str, object]:
        serialized = self.model_dump(mode="json")
        return {
            field_name: serialized[field_name]
            for field_name in CheckpointDiagnosticsSection.model_fields
        }
