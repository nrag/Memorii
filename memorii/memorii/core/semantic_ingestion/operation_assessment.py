"""Deterministic operation sealing after independent semantic ingestion assessments."""

from __future__ import annotations

from memorii.core.semantic_ingestion.contracts import (
    IndependentSourceAnalysis,
    OperationTemporalAttachmentBinding,
    OperationTemporalDecisionBinding,
    SealedSemanticOperation,
    SemanticCandidate,
    TemporalEvidenceDecisionClosure,
    TemporalRole,
    contract_digest,
)


def seal_semantic_operation(
    *,
    source_id: str,
    source_digest: str,
    candidate: SemanticCandidate,
    source_analysis: IndependentSourceAnalysis,
    role_closures: tuple[tuple[TemporalRole, TemporalEvidenceDecisionClosure], ...],
) -> SealedSemanticOperation | None:
    """Seal a complete role-specific operation without importing orchestration."""
    consensus = source_analysis.parser_consensus
    if (
        source_analysis.candidate_id != candidate.candidate_id
        or source_analysis.predicate_id != candidate.predicate_id
        or source_analysis.operation_kind != candidate.operation_kind
        or source_analysis.source_id != source_id
        or source_analysis.source_digest != source_digest
        or consensus.status != "stable"
        or consensus.primary_interpretation.predicate_head_span.source_id != source_id
        or consensus.corroborating_interpretation.predicate_head_span.source_id != source_id
        or any(item.canonical_entity_id is None for item in source_analysis.identity_evidence)
        or any(item.source_id != source_id for item in source_analysis.identity_evidence)
        or any(closure.outcome != "pass" for _, closure in role_closures)
    ):
        return None
    expected_roles = tuple(role for role, _ in source_analysis.temporal_roles())
    actual_roles = tuple(role for role, _ in role_closures)
    if actual_roles != expected_roles or len(set(actual_roles)) != len(actual_roles):
        raise ValueError("resolved temporal roles do not match the typed candidate")
    operation_id = contract_digest(
        b"memorii.semantic-ingestion.operation-coordinate.v1",
        {
            "source_id": source_id,
            "source_digest": source_digest,
            "provider_local_id": candidate.candidate_id,
            "operation_kind": candidate.operation_kind,
        },
    )
    bindings: list[OperationTemporalDecisionBinding] = []
    for role, closure in role_closures:
        source_temporal = next(value for value in source_analysis.temporal_evidence if value.temporal_role == role)
        attachment = OperationTemporalAttachmentBinding.create(
            operation_id=operation_id,
            temporal_role=role,
            stable_attachment_consensus_digest=source_temporal.attachment_consensus_digest,
            candidate_ids=tuple(value.candidate_id for value in closure.candidates),
            candidate_spans=source_temporal.attachment_spans,
        )
        scope = contract_digest(
            b"memorii.semantic-ingestion.scope-assessment.v1",
            {
                "operation_id": operation_id,
                "candidate_id": candidate.candidate_id,
                "temporal_role": role,
                "attachment": attachment,
                "parser_consensus_digest": consensus.assessment_digest,
                "source_analysis_digest": source_analysis.analysis_digest,
            },
        )
        semantic = contract_digest(
            b"memorii.semantic-ingestion.semantic-assessment.v1",
            {
                "operation_id": operation_id,
                "scope_assessment_digest": scope,
                "predicate_id": candidate.predicate_id,
                "operation_kind": candidate.operation_kind,
                "temporal_role": role,
            },
        )
        bindings.append(
            OperationTemporalDecisionBinding.create(
                operation_id=operation_id,
                temporal_role=role,
                scope_assessment_digest=scope,
                semantic_assessment_digest=semantic,
                temporal_attachment=attachment,
                reference_evidence=source_temporal.reference_evidence,
                decision_closure=closure,
            )
        )
    ordered = tuple(sorted(bindings, key=lambda value: (value.operation_id, value.temporal_role, value.binding_digest)))
    scope_digest = contract_digest(
        b"memorii.semantic-ingestion.operation-scope-assessments.v1",
        tuple(value.scope_assessment_digest for value in ordered),
    )
    semantic_digest = contract_digest(
        b"memorii.semantic-ingestion.operation-semantic-assessments.v1",
        tuple(value.semantic_assessment_digest for value in ordered),
    )
    body: dict[str, object] = {
        "operation_id": operation_id,
        "candidate_id": candidate.candidate_id,
        "kind": candidate.operation_kind,
        "scope_assessment_digest": scope_digest,
        "semantic_assessment_digest": semantic_digest,
        "temporal_bindings": ordered,
    }
    if source_analysis.claim_identity is not None:
        body.update(
            {
                "claim_identity": source_analysis.claim_identity,
                "source_authority_evidence": source_analysis.source_authority_evidence,
            }
        )
    return SealedSemanticOperation.model_validate(
        body
        | {
            "sealed_operation_digest": contract_digest(
                b"memorii.semantic-ingestion.sealed-operation.v1", body
            )
        }
    )


def seal_assertion_operation(
    *, source_id: str, source_digest: str, candidate: SemanticCandidate,
    source_analysis: IndependentSourceAnalysis,
    closure: TemporalEvidenceDecisionClosure,
) -> SealedSemanticOperation | None:
    """Compatibility wrapper for the original fact-only semantic ingestion API."""
    if candidate.operation_kind not in {"fact", "action"}:
        raise ValueError("assertion sealing is valid only for fact or action candidates")
    return seal_semantic_operation(
        source_id=source_id,
        source_digest=source_digest,
        candidate=candidate,
        source_analysis=source_analysis,
        role_closures=(("assertion", closure),),
    )


__all__ = ["SealedSemanticOperation", "seal_assertion_operation", "seal_semantic_operation"]
