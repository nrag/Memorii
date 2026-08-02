"""Compile sealed M3 operations into canonical durable carrier inputs."""

from __future__ import annotations

from hashlib import sha256

from memorii.core.semantic_ingestion.contracts import (
    AcceptedTemporalEvidence,
    ActionRevision,
    ClaimAssertion,
    IdentityLineageRecord,
    M3DurableCarrier,
    SealedSemanticOperation,
    SemanticCandidate,
    TemporalTransitionRecord,
    contract_digest,
)

M3_CODEC_FINGERPRINT = sha256(b"memorii.semantic-ingestion.m3.closed-codec.v1").hexdigest()


def _binding(operation: SealedSemanticOperation, role: str):
    matches = tuple(value for value in operation.temporal_bindings if value.temporal_role == role)
    if len(matches) != 1:
        raise ValueError(f"sealed operation requires exactly one {role} temporal binding")
    return matches[0]


def _base(operation: SealedSemanticOperation, candidate: SemanticCandidate, role: str) -> dict[str, object]:
    binding = _binding(operation, role)
    evidence = AcceptedTemporalEvidence(
        reference_evidence=binding.reference_evidence,
        decision_closure=binding.decision_closure,
    )
    return {
        "operation_id": operation.operation_id,
        "valid_interval": evidence.valid_interval,
        "temporal_evidence": evidence,
        "temporal_decision_binding": binding,
        "record_version": 1,
        "codec_fingerprint": M3_CODEC_FINGERPRINT,
        "statement_digest": contract_digest(b"memorii.m3.statement.v1", candidate.assertion_quote),
    }


def _claim(operation: SealedSemanticOperation, candidate: SemanticCandidate, role: str) -> ClaimAssertion:
    body = _base(operation, candidate, role) | {
        "record_kind": "claim_assertion",
        "claim_assertion_id": contract_digest(
            b"memorii.m3.claim-assertion-id.v1",
            {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id, "role": role},
        ),
    }
    return ClaimAssertion.model_validate(
        body | {"record_digest": contract_digest(b"memorii.m3.temporal-carrier.v1", body)}
    )


def compile_accepted_carriers(
    *, operation: SealedSemanticOperation, candidate: SemanticCandidate
) -> tuple[M3DurableCarrier, ...]:
    """Produce only the durable record family authorized by the typed candidate."""
    if operation.candidate_id != candidate.candidate_id or operation.kind != candidate.operation_kind:
        raise ValueError("sealed operation and candidate do not match")
    if operation.kind == "fact":
        carriers: tuple[M3DurableCarrier, ...] = (_claim(operation, candidate, "assertion"),)
    elif operation.kind == "action":
        body = _base(operation, candidate, "assertion") | {
            "record_kind": "action_revision",
            "action_revision_id": contract_digest(
                b"memorii.m3.action-revision-id.v1",
                {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id},
            ),
        }
        carriers = (
            ActionRevision.model_validate(
                body | {"record_digest": contract_digest(b"memorii.m3.temporal-carrier.v1", body)}
            ),
        )
    elif operation.kind == "correction":
        transition_body = _base(operation, candidate, "transition") | {
            "record_kind": "temporal_transition",
            "transition_kind": "correction",
            "transition_id": contract_digest(
                b"memorii.m3.correction-transition-id.v1",
                {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id},
            ),
        }
        carriers = (
            _claim(operation, candidate, "replacement"),
            TemporalTransitionRecord.model_validate(
                transition_body
                | {"record_digest": contract_digest(b"memorii.m3.temporal-carrier.v1", transition_body)}
            ),
        )
    elif operation.kind == "retraction":
        body = _base(operation, candidate, "transition") | {
            "record_kind": "temporal_transition",
            "transition_kind": "retraction",
            "transition_id": contract_digest(
                b"memorii.m3.retraction-transition-id.v1",
                {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id},
            ),
        }
        carriers = (
            TemporalTransitionRecord.model_validate(
                body | {"record_digest": contract_digest(b"memorii.m3.temporal-carrier.v1", body)}
            ),
        )
    else:
        body = _base(operation, candidate, "transition") | {
            "record_kind": "identity_lineage",
            "identity_lineage_id": contract_digest(
                b"memorii.m3.identity-lineage-id.v1",
                {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id},
            ),
        }
        carriers = (
            IdentityLineageRecord.model_validate(
                body | {"record_digest": contract_digest(b"memorii.m3.temporal-carrier.v1", body)}
            ),
        )
    return tuple(sorted(carriers, key=lambda value: (value.operation_id, value.record_kind, value.record_digest)))


__all__ = [
    "AcceptedTemporalEvidence",
    "ActionRevision",
    "ClaimAssertion",
    "IdentityLineageRecord",
    "M3DurableCarrier",
    "M3_CODEC_FINGERPRINT",
    "TemporalTransitionRecord",
    "compile_accepted_carriers",
]
