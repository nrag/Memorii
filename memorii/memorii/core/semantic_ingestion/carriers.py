"""Compile sealed semantic ingestion operations into canonical durable carrier inputs."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Any

from memorii.core.memory_evolution.semantic_state import CompiledIdentityLineageTransition
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.semantic_ingestion.canonical_evidence_arena import (
    record_certified_instance,
)
from memorii.core.semantic_ingestion.contracts import (
    AcceptedTemporalEvidence,
    ActionRevision,
    ClaimAssertion,
    IdentityLineageRecord,
    PredicateTrustRule,
    SealedSemanticOperation,
    SemanticCandidate,
    SemanticDurableCarrier,
    TemporalTransitionRecord,
    contract_digest,
)


def _record_and_certify(kind, body):
    validated = kind.model_validate(
        body | {"record_digest": _record_digest(kind, body)}
    )
    record_certified_instance(validated)
    return validated


SEMANTIC_INGESTION_CODEC_FINGERPRINT = sha256(b"memorii.semantic-ingestion.closed-codec.v1").hexdigest()


def _record_digest(record_type: type[Any], body: dict[str, object]) -> str:
    """Hash the exact persisted carrier shape, including subclass serialization."""
    record = record_type.model_construct(**body, record_digest="0" * 64)
    return contract_digest(
        b"memorii.semantic-ingestion.temporal-carrier.v1",
        record.model_dump(mode="python", exclude={"record_digest"}),
    )


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
        "codec_fingerprint": SEMANTIC_INGESTION_CODEC_FINGERPRINT,
        "statement_digest": contract_digest(b"memorii.semantic-ingestion.statement.v1", candidate.assertion_quote),
    }


def _claim(
    operation: SealedSemanticOperation,
    candidate: SemanticCandidate,
    role: str,
    predicate_trust_rule: PredicateTrustRule | None,
) -> ClaimAssertion:
    body = _base(operation, candidate, role) | {
        "record_kind": "claim_assertion",
        "claim_assertion_id": contract_digest(
            b"memorii.semantic-ingestion.claim-assertion-id.v1",
            {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id, "role": role},
        ),
    }
    if operation.claim_identity is not None:
        body.update(
            {
                "claim_identity": operation.claim_identity,
                "source_authority_evidence": operation.source_authority_evidence,
                "predicate_trust_rule": predicate_trust_rule,
            }
        )
    return _record_and_certify(ClaimAssertion, body)


def compile_accepted_carriers(
    *,
    operation: SealedSemanticOperation,
    candidate: SemanticCandidate,
    predicate_trust_rule: PredicateTrustRule | None = None,
    identity_transition: CompiledIdentityLineageTransition | None = None,
    committed_at: datetime | None,
) -> tuple[SemanticDurableCarrier, ...]:
    """Produce only the durable record family authorized by the typed candidate."""
    if operation.candidate_id != candidate.candidate_id or operation.kind != candidate.operation_kind:
        raise ValueError("sealed operation and candidate do not match")
    if operation.kind == "fact":
        carriers: tuple[SemanticDurableCarrier, ...] = (
            _claim(operation, candidate, "assertion", predicate_trust_rule),
        )
    elif operation.kind == "action":
        body = _base(operation, candidate, "assertion") | {
            "record_kind": "action_revision",
            "action_revision_id": contract_digest(
                b"memorii.semantic-ingestion.action-revision-id.v1",
                {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id},
            ),
        }
        carriers = (
            _record_and_certify(ActionRevision, body),
        )
    elif operation.kind == "correction":
        transition_body = _base(operation, candidate, "transition") | {
            "record_kind": "temporal_transition",
            "transition_kind": "correction",
            "transition_id": contract_digest(
                b"memorii.semantic-ingestion.correction-transition-id.v1",
                {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id},
            ),
            "system_interval": (
                TimeInterval(start=committed_at)
                if committed_at is not None
                else None
            ),
        }
        carriers = (
            _claim(operation, candidate, "replacement", predicate_trust_rule),
            _record_and_certify(TemporalTransitionRecord, transition_body),
        )
    elif operation.kind == "retraction":
        body = _base(operation, candidate, "transition") | {
            "record_kind": "temporal_transition",
            "transition_kind": "retraction",
            "transition_id": contract_digest(
                b"memorii.semantic-ingestion.retraction-transition-id.v1",
                {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id},
            ),
            "system_interval": (
                TimeInterval(start=committed_at)
                if committed_at is not None
                else None
            ),
        }
        carriers = (
            _record_and_certify(TemporalTransitionRecord, body),
        )
    else:
        if identity_transition is None:
            raise ValueError("identity_lineage_compiler_required")
        if identity_transition.operation_id != operation.operation_id:
            raise ValueError("identity_lineage_operation_binding_mismatch")
        body = _base(operation, candidate, "transition") | {
            "record_kind": "identity_lineage",
            "identity_lineage_id": contract_digest(
                b"memorii.semantic-ingestion.identity-lineage-id.v1",
                {"operation_id": operation.operation_id, "candidate_id": candidate.candidate_id},
            ),
            "statement_digest": identity_transition.transition_digest,
            "transition": identity_transition,
        }
        carriers = (
            _record_and_certify(IdentityLineageRecord, body),
        )
    return tuple(sorted(carriers, key=lambda value: (value.operation_id, value.record_kind, value.record_digest)))


__all__ = [
    "AcceptedTemporalEvidence",
    "ActionRevision",
    "ClaimAssertion",
    "IdentityLineageRecord",
    "SemanticDurableCarrier",
    "SEMANTIC_INGESTION_CODEC_FINGERPRINT",
    "TemporalTransitionRecord",
    "compile_accepted_carriers",
]
