"""Step-1 governance invariants shared by source admission and preparation.

This module deliberately contains no provider or NLP dependency.  It is the
single place that decides whether a complete derived scope set is usable for
semantic work.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import ExtractionTriggerMode, MemoryScope
from memorii.core.provider.models import ProviderEvent
from memorii.domain.enums import SourceModality

if TYPE_CHECKING:
    # Annotation-only contract import: a runtime import here would close a
    # semantic_ingestion -> memory_evolution import cycle through atomic_store.
    from memorii.core.semantic_ingestion.contracts import (
        RequiredOutcomeScopeSet as SemanticRequiredOutcomeScopeSet,
    )


class SourceGovernanceError(ValueError):
    """A source cannot cross from retention into semantic processing."""


class DerivedSourceGovernanceMaterial(BaseModel):
    """Complete server-owned governance material for one verbatim source."""

    # The contract payloads are typed as object at runtime: resolving their
    # concrete semantic_ingestion classes here would close an import cycle.
    # ``derive_source_governance_material`` is their sole constructor and
    # stores exactly those types.
    semantic_context: object
    required_outcome_scopes: object
    segment_governance_carriers: object
    message_admission_carriers: object
    governance_carrier_artifact: object
    admission_scope_authorization_proof: AdmissionScopeAuthorizationProof

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceGovernanceMaterialResult(BaseModel):
    """Closed result of governance derivation; denial never manufactures authority."""

    kind: Literal["governed", "nonpromoting"]
    material: DerivedSourceGovernanceMaterial | None = None
    reason_codes: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_result(self) -> SourceGovernanceMaterialResult:
        if (self.kind == "governed") != (self.material is not None):
            raise ValueError("governance material result kind and material must agree")
        if self.kind == "governed" and self.reason_codes:
            raise ValueError("governed material result cannot carry denial reasons")
        if self.kind == "nonpromoting" and (self.material is not None or not self.reason_codes):
            raise ValueError("nonpromoting governance result requires explicit reasons")
        return self


class AdmissionScopeAuthorizationProof(BaseModel):
    """Audit-only proof that the exact derived scope set was authorized."""

    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_outcome_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_authorized_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_authorization_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["authorized"]
    authorized_at: datetime
    proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_proof(self) -> AdmissionScopeAuthorizationProof:
        if self.authorized_at.utcoffset() is None:
            raise ValueError("admission authorization proof time must be timezone-aware")
        body = self.model_dump(mode="python", exclude={"proof_digest"})
        expected = sha256(
            b"memorii.semantic_ingestion.admission_scope_authorization_proof.v1\0"
            + encode_typed_value(body)
        ).hexdigest()
        if self.proof_digest != expected:
            raise ValueError("admission scope authorization proof digest mismatch")
        return self

    @classmethod
    def create(cls, **body: Any) -> AdmissionScopeAuthorizationProof:
        return cls(
            **body,
            proof_digest=sha256(
                b"memorii.semantic_ingestion.admission_scope_authorization_proof.v1\0"
                + encode_typed_value(body)
            ).hexdigest(),
        )


def require_complete_scope_authorization(
    *,
    ingress: AuthenticatedIngressContext,
    required_outcome_scopes: RequiredOutcomeScopeSet,
) -> None:
    """Fail closed unless the current authenticated set covers every scope.

    Callers must pass the complete, server-derived set.  A representative
    source-level scope is intentionally not accepted here.
    """

    if required_outcome_scopes != ingress.required_outcome_scopes:
        raise SourceGovernanceError("source required scopes differ from authenticated ingress")
    if not set(required_outcome_scopes.scopes).issubset(
        ingress.current_authorized_scopes.scopes
    ):
        raise SourceGovernanceError("authenticated scope coverage is incomplete")


def derive_source_governance_material(
    *,
    ingress: AuthenticatedIngressContext,
    event: ProviderEvent,
    source_id: str,
    source_digest: str,
    received_at: datetime,
    retained_at: datetime,
) -> SourceGovernanceMaterialResult:
    """Build every Step-1 semantic authority from authenticated ingress only.

    This is deliberately a one-segment, verbatim-source builder.  Structured
    snapshots and delegation envelopes require their own authenticated envelope
    authorities and must not be approximated here.
    """
    if received_at.utcoffset() is None or retained_at.utcoffset() is None:
        raise ValueError("server receive and retain times must be timezone-aware")
    if retained_at < received_at:
        raise ValueError("retained time cannot precede server receive time")
    missing: list[str] = []
    if ingress.semantic_egress_governance is None:
        missing.append("semantic_egress_governance_unavailable")
    if ingress.semantic_source_authority is None:
        missing.append("semantic_source_authority_unavailable")
    if event.content is None:
        missing.append("content_unavailable")
    if missing:
        return SourceGovernanceMaterialResult(kind="nonpromoting", reason_codes=tuple(missing))
    if event.operation.value in {"delegation_result", "session_end", "pre_compress"} and ingress.structured_source_envelope is None:
        # Structured content is semantic only after its distinct authenticated
        # envelope is available; a verbatim public event is not a substitute.
        return SourceGovernanceMaterialResult(
            kind="nonpromoting", reason_codes=("structured_envelope_authority_unavailable",)
        )
    try:
        require_complete_scope_authorization(
            ingress=ingress, required_outcome_scopes=ingress.required_outcome_scopes
        )
    except SourceGovernanceError:
        return SourceGovernanceMaterialResult(
            kind="nonpromoting", reason_codes=("authenticated_scope_coverage_incomplete",)
        )

    from memorii.core.semantic_ingestion.contracts import (
        AuthenticatedSourceIntervalEvidence,
        GovernanceCarrierArtifact,
        MessageAdmissionCarrierSet,
        MessageAdmissionIdentity,
        SegmentGovernanceBinding,
        SegmentGovernanceCarrierSet,
        SourceSemanticContext,
        TimeInterval,
        contract_digest,
    )

    egress = ingress.semantic_egress_governance
    authority = ingress.semantic_source_authority
    assert egress is not None and authority is not None
    if (
        ingress.semantic_source_interval is not None
        and ingress.semantic_source_interval.policy_revision != authority.policy_revision
    ):
        return SourceGovernanceMaterialResult(
            kind="nonpromoting", reason_codes=("semantic_source_interval_policy_mismatch",)
        )
    scopes = _semantic_required_scopes(ingress.required_outcome_scopes)
    if scopes is None:
        return SourceGovernanceMaterialResult(
            kind="nonpromoting", reason_codes=("required_scope_projection_unavailable",)
        )
    authority_digest = contract_digest(
        b"memorii.semantic-ingestion.authenticated-source-authority.v1",
        authority.model_dump(mode="python"),
    )
    egress_policy_fingerprint = contract_digest(
        b"memorii.semantic-ingestion.authenticated-egress-governance.v1",
        egress.model_dump(mode="python"),
    )
    governance_policy_fingerprint = contract_digest(
        b"memorii.semantic-ingestion.source-governance-policy.v1",
        {
            "operation": event.operation.value,
            "required_scope_set_digest": scopes.required_scope_set_digest,
            "classification": egress.classification,
            "authority_digest": authority_digest,
        },
    )
    trust_policy_fingerprint = contract_digest(
        b"memorii.semantic-ingestion.source-trust-policy.v1",
        {
            "policy_revision": authority.policy_revision,
            "provenance_digest": authority.provenance_digest,
            "authority_digest": authority_digest,
        },
    )
    interval = None
    if ingress.semantic_source_interval is not None:
        interval_metadata = ingress.semantic_source_interval
        interval = AuthenticatedSourceIntervalEvidence.create(
            source_id=source_id,
            source_digest=source_digest,
            interval=TimeInterval(start=interval_metadata.start, end=interval_metadata.end),
            authority_basis=interval_metadata.authority_basis,
            provenance_digest=interval_metadata.provenance_digest,
            policy_revision=interval_metadata.policy_revision,
            source_authority_evidence_digest=contract_digest(
                b"memorii.semantic-ingestion.source-authority-evidence.v1",
                {
                    "source_id": source_id,
                    "source_digest": source_digest,
                    "authority": {
                        "authority_class": authority.authority_class,
                        "authenticated_provenance_class": authority.authenticated_provenance_class,
                        "governing_principal_id": authority.governing_principal_id,
                        "policy_revision": authority.policy_revision,
                    },
                    "provenance_digest": authority.provenance_digest,
                },
            ),
        )
    context = SourceSemanticContext.create(
        source_id=source_id,
        source_digest=source_digest,
        trigger_mode=ExtractionTriggerMode.IMMEDIATE,
        provenance_digest=authority.provenance_digest,
        temporal_references=(),
        received_at=received_at,
        retained_at=retained_at,
        source_effective_interval_evidence=interval,
        provider_egress_policy_fingerprint=egress_policy_fingerprint,
        governance_policy_fingerprint=governance_policy_fingerprint,
        trust_policy_fingerprint=trust_policy_fingerprint,
    )
    binding = SegmentGovernanceBinding.create(
        source_id=source_id,
        segment_id="segment-0",
        message_semantic_context_digest=context.context_digest,
        effective_scope_digest=scopes.required_scope_set_digest,
        authority_digest=authority_digest,
        data_classification=egress.classification,
        modality=_server_modality(event),
        provider_egress_decision_digest=contract_digest(
            b"memorii.semantic-ingestion.source-egress-decision.v1",
            {
                "source_id": source_id,
                "source_digest": source_digest,
                "egress_governance": egress.model_dump(mode="python"),
                "policy_fingerprint": egress_policy_fingerprint,
            },
        ),
        egress_disposition="allow_verbatim",
    )
    carriers = SegmentGovernanceCarrierSet.create(source_id=source_id, bindings=(binding,))
    # The nonpromoting guard above already rejected missing content.
    assert event.content is not None
    admission = MessageAdmissionIdentity.create(
        delivery_principal_binding_digest=ingress.delivery_principal_binding.binding_digest,
        authenticated_source_reference=event.event_id,
        authenticated_source_reference_key_digest=contract_digest(
            b"memorii.semantic-ingestion.authenticated-source-reference.v1", event.event_id
        ),
        message_bytes_digest=sha256(event.content.encode("utf-8")).hexdigest(),
        segment_governance_binding_digest=binding.binding_digest,
    )
    admissions = MessageAdmissionCarrierSet.create(source_id=source_id, identities=(admission,))
    artifact = GovernanceCarrierArtifact.create(
        artifact_id=f"semantic_ingestion:governance:{source_digest}",
        atomic_generation=1,
        segment_governance=carriers,
        message_admissions=admissions,
        required_outcome_scopes=scopes,
    )
    proof = AdmissionScopeAuthorizationProof.create(
        delivery_principal_binding_digest=ingress.delivery_principal_binding.binding_digest,
        required_outcome_scope_set_digest=ingress.required_outcome_scopes.required_scope_set_digest,
        current_authorized_scope_set_digest=ingress.current_authorized_scopes.required_scope_set_digest,
        session_authorization_evidence_digest=contract_digest(
            b"memorii.semantic-ingestion.authenticated-session-authorization.v1",
            ingress.model_dump(mode="python"),
        ),
        decision="authorized",
        authorized_at=retained_at,
    )
    return SourceGovernanceMaterialResult(
        kind="governed",
        material=DerivedSourceGovernanceMaterial(
            semantic_context=context,
            required_outcome_scopes=scopes,
            segment_governance_carriers=carriers,
            message_admission_carriers=admissions,
            governance_carrier_artifact=artifact,
            admission_scope_authorization_proof=proof,
        ),
    )


def _semantic_required_scopes(
    scopes: RequiredOutcomeScopeSet,
) -> SemanticRequiredOutcomeScopeSet | None:
    from memorii.core.semantic_ingestion.contracts import (
        RequiredOutcomeScopeSet as SemanticRequiredOutcomeScopeSet,
    )

    projected: list[MemoryScope] = []
    for scope in scopes.scopes:
        kind, separator, value = scope.partition(":")
        if not separator or not value:
            return None
        if kind == "task":
            projected.append(MemoryScope(task_id=value))
        elif kind == "session":
            projected.append(MemoryScope(session_id=value))
        elif kind == "user":
            projected.append(MemoryScope(user_id=value))
        else:
            return None
    return SemanticRequiredOutcomeScopeSet.create(
        tenant_partition_id=scopes.tenant_partition_id, scopes=tuple(projected)
    )


def _server_modality(event: ProviderEvent) -> SourceModality:
    """Closed operation policy; public event metadata cannot choose modality."""
    return {
        "chat_user_turn": SourceModality.ASSERTION,
        "chat_assistant_turn": SourceModality.ASSISTANT_CLAIM,
        "memory_write_longterm": SourceModality.ASSERTION,
        "memory_write_user": SourceModality.ASSERTION,
        "memory_write_dailylog": SourceModality.ASSERTION,
        "delegation_result": SourceModality.TOOL_RESULT,
    }.get(event.operation.value, SourceModality.NOISE)


__all__ = [
    "AdmissionScopeAuthorizationProof",
    "DerivedSourceGovernanceMaterial",
    "SourceGovernanceError",
    "SourceGovernanceMaterialResult",
    "derive_source_governance_material",
    "require_complete_scope_authorization",
]
