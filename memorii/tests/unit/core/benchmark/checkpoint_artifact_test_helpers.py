"""Typed checkpoint artifact fixtures for benchmark unit tests."""

from __future__ import annotations

from memorii.core.benchmark.artifact_rows import (
    ChannelOverlapSection,
    CheckpointDiagnosticsPayload,
)


def checkpoint_diagnostics_payload(**overrides: object) -> CheckpointDiagnosticsPayload:
    return CheckpointDiagnosticsPayload.model_validate(
        {
            "missing_expected_ids": {},
            "extra_selected_ids": {},
            "allowed_definition_selected_ids": {},
            "allowed_context_selected_ids": {},
            "forbidden_selected_ids": {},
            "answer_match_type": "unknown",
            "failure_classification": [],
            "selected_excluded_ids": {},
            "supporting_excluded_ids": {},
            "rejected_expected_ids": {},
            "missing_rejected_ids": {},
            "missing_rejected_claim_subject_entity_ids": [],
            "supporting_wrong_entity_claim_ids": [],
            "supporting_wrong_subject_claim_ids": [],
            "supporting_wrong_subject_entity_ids": [],
            "supporting_disambiguation_claim_ids": [],
            "missing_wrong_entity_rejection_claim_ids": [],
            "missing_wrong_entity_rejection_subject_ids": [],
            "selected_noncurrent_claim_ids": [],
            "required_definition_claim_ids": [],
            "missing_definition_claim_ids": [],
            "missing_definition_support_claim_ids": [],
            "rejected_required_definition_claim_ids": [],
            "selected_entity_role_mismatches": [],
            "missing_selected_subject_entity_ids": [],
            "selected_object_entity_instead_of_subject_ids": [],
            "selected_graph_entity_overbreadth": [],
            "selected_nonrequired_graph_entity_ids": [],
            "selected_context_only_entity_ids": [],
            "selected_rejected_or_context_entity_ids": [],
            "supporting_noisy_citation_event_ids": [],
            "selected_claim_support_closure_errors": [],
            "selected_claim_ids_missing_support": [],
            "selected_claim_evidence_event_ids_missing_support": [],
            "selected_action_state_event_ids_missing_support": [],
            "context_only_noise_event_ids": [],
            "supporting_role_violations": {},
            "supporting_rejection_provenance_overlap": {},
            "channel_overlap": ChannelOverlapSection(),
            "role_misclassification": False,
            "precision_failure_classification": [],
            "required_judge_ids": [],
            **overrides,
        }
    )
