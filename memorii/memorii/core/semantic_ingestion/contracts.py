"""Closed, content-addressed contracts shared by the semantic ingestion ingestion pipeline.

This module is deliberately a dependency leaf.  Candidate validation,
operation sealing, durable carrier compilation, provider orchestration, and
writer-safe preplanning persistence all consume these types; none of the types imports those
services back.  That makes the accepted/non-accepted boundary auditable and
keeps replay execution outside semantic ingestion.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from hashlib import sha256
from itertools import groupby
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal, Protocol, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationRequest,
    OperationLeaseBinding,
    generation_request_digest,
)
from memorii.core.memory_evolution.bootstrap_profile import BootstrapSegmentGrammarProof
from memorii.core.memory_evolution.graph_records import (
    GraphReadSet,
    GraphRecordKind,
    GraphStateSnapshot,
    NonOwningGraphRecord,
    SourceAuthority,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
    SemanticWriterCommitBinding,
    decode_typed_value,
    encode_typed_value,
    encode_typed_value_with_spans,
)
from memorii.core.memory_evolution.models import ClaimValueType, ExtractionTriggerMode, MemoryScope, SourceObservation
from memorii.core.memory_evolution.semantic_analysis.policies import (
    ConstructionFamily,
    PredicateSemanticPolicy,
    QuotationBoundaryPolicy,
    SemanticScopePolicy,
    UdPathPattern,
    UdPathStep,
    UdRoleSchema,
)
from memorii.core.memory_evolution.semantic_state import (
    AcceptedClaimIdentity,
    CompiledIdentityLineageTransition,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.domain.enums import SourceModality

if TYPE_CHECKING:
    from memorii.core.memory_evolution.graph_effect_contracts import (
        CanonicalSourceTerminalOutcomeCore,
        CanonicalSourceTerminalOutcomeRecord,
        GraphRevisionDelta,
        IngestionObservationDelta,
    )
    from memorii.core.memory_evolution.graph_planning import (
        CanonicalPlanningRecordPayload,
        GraphPlanningState,
        NonPublishingIdentityPlanningResultV3,
        PlanningActionRevision,
        PlanningAliasRevision,
        PlanningCitation,
        PlanningClaimAssertion,
        PlanningClaimProjection,
        PlanningEntityRevision,
        PlanningProvenance,
        PlanningRecordPrecondition,
        PlanningRelationRevision,
        PlanningTemporalTransition,
        PlanningTypeEvidence,
    )
    from memorii.core.memory_evolution.graph_records import (
        AcceptedIdentityOperationArtifact,
        PlannedIdentityReservation,
        TrustedAcceptedIdentityOperationDecision,
        VerifiedIdentityDecisionAuthority,
    )
    from memorii.core.memory_evolution.transaction_coordinator import (
        GraphReadSetToken,
        SealedGraphStateSnapshot,
    )
    from memorii.core.semantic_ingestion.canonical_evidence_arena import CanonicalEvidenceArena
    from memorii.core.semantic_ingestion.event_replay import SemanticMemoryEventBatch

from memorii.core.semantic_ingestion.canonical_evidence_arena import (
    CANONICAL_CODEC_REVISION,
    CANONICAL_PROFILE_REVISION,
    CanonicalMemberEvidence,
    CanonicalMemberIndex,
    ValidatedCanonicalEvidenceResult,
    current_digest_verification_scope,
)

Commitment = Literal[
    "asserted",
    "believed",
    "reported",
    "quoted",
    "questioned",
    "instructed",
    "hypothetical",
]


class _CanonicalContractMap(dict[str, object]):
    """Map-shaped, hashable CTV member for nested model frozensets."""

    def __hash__(self) -> int:
        return hash(encode_typed_value(dict(self)))


def canonical_contract_value(value: object) -> object:
    """Lower nested Pydantic values before entering the closed CTV codec."""
    if isinstance(value, BaseModel):
        reuse_scope = current_digest_verification_scope()
        if reuse_scope is not None:
            lowered = reuse_scope.lookup_lowered_value(value)
            if lowered is not None:
                return lowered
        lowered = _CanonicalContractMap(
            {name: canonical_contract_value(getattr(value, name)) for name in type(value).model_fields}
        )
        if reuse_scope is not None:
            reuse_scope.record_lowered_value(value, lowered)
        return lowered
    if isinstance(value, dict):
        return {key: canonical_contract_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(canonical_contract_value(item) for item in value)
    if isinstance(value, list):
        return [canonical_contract_value(item) for item in value]
    if isinstance(value, frozenset):
        return frozenset(canonical_contract_value(item) for item in value)
    return value


def _revalidated_contract_instance(value: BaseModel, canonical_payload: object) -> BaseModel:
    """Re-derive validation from the lowered payload; forgeries fail closed.

    ``model_copy``/``model_construct`` instances never inherit validation:
    the payload is re-validated as freshly parsed content on every codec
    admission.
    """
    try:
        return type(value).model_validate(
            restore_closed_wire_enums(canonical_payload),
            context=None,
        )
    except (TypeError, ValueError) as exc:
        raise SemanticContractCodecError("semantic ingestion contract validation failed") from exc


def _build_validated_semantic_contract_result(
    *,
    value: BaseModel,
    canonical_contract_bytes: bytes,
    canonical_payload: object,
    member_spans: tuple[object, ...],
    domain: bytes,
) -> ValidatedCanonicalEvidenceResult:
    validated = _revalidated_contract_instance(value, canonical_payload)

    return ValidatedCanonicalEvidenceResult(
        contract=validated,
        canonical_contract_bytes=canonical_contract_bytes,
        canonical_member_index=CanonicalMemberIndex(
            contract_type=f"{type(validated).__module__}.{type(validated).__qualname__}",
            member_paths=len(member_spans),
            canonical_digest=sha256(canonical_contract_bytes).hexdigest(),
        ),
        validation_provenance=("transport", "domain", "content_digest"),
        member_evidence=tuple(
            CanonicalMemberEvidence(
                path=span.path,
                begin=span.begin,
                end=span.end,
                member_digest=sha256(canonical_contract_bytes[span.begin : span.end]).hexdigest(),
                member_type=span.value_type,
                domain=_CANONICAL_CONTRACT_ENVELOPE.encode("ascii"),
                profile_revision=CANONICAL_PROFILE_REVISION,
                codec_revision=CANONICAL_CODEC_REVISION,
                schema=_CANONICAL_CONTRACT_ENVELOPE,
                provenance=("transport", "domain", "content_digest"),
            )
            for span in member_spans
        ),
        domain=domain,
    )


def contract_digest(domain: bytes, value: object) -> str:
    return sha256(domain + b"\0" + encode_typed_value(canonical_contract_value(value))).hexdigest()


def _digest_verification_hit(instance: object, declared: str) -> bool:
    """True when an operation-proven verification covers this exact content.

    Reuse requires the same concrete type and declared digest plus full
    structural equality with the certified instance, so a forged declaration
    can never inherit an entry and always falls through to the full
    computation.  Identity short-circuits the equality walk for the common
    same-instance repeat; it proves strictly more than equality.
    """

    scope = current_digest_verification_scope()
    if scope is None:
        return False
    certified = scope.lookup_verified(type(instance), declared)
    return certified is not None and (
        certified is instance or (type(certified) is type(instance) and certified == instance)
    )


def _record_digest_verification(instance: object, declared: str) -> None:
    scope = current_digest_verification_scope()
    if scope is not None:
        scope.record_verified(type(instance), declared, instance)


def certified_roundtrip(value: BaseModel) -> BaseModel:
    """Round-trip validation of a typed value, reusing proven work by identity.

    Internal composition boundaries re-derive validation from content by
    dumping and re-validating a value that is already a typed instance of
    the same contract.  Within one enabled operation, an instance whose
    complete round-trip already succeeded is served that proven result; any
    other instance — a fresh construction, a copy, or a forgery — pays the
    full existing path, so this never validates untrusted input and never
    weakens a first admission.  Writer admissions and decode boundaries do
    not use this helper.
    """
    scope = current_digest_verification_scope()
    if scope is not None:
        cached = scope.lookup_roundtrip(value)
        if cached is not None:
            return cached  # type: ignore[return-value]
    validated = type(value).model_validate(value.model_dump(mode="python"))
    if scope is not None:
        scope.record_roundtrip(value, validated)
    return validated


class CandidateTransportError(ValueError):
    """The proposer returned bytes outside the closed candidate schema."""


class SemanticContractCodecError(ValueError):
    """Serialized semantic ingestion bytes do not match the active closed contract."""


class SourceAuthorityEvidence(BaseModel):
    """Host-authenticated source authority, never reconstructed by an analyzer."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata_field: Literal["source_authority"] = "source_authority"
    authority: SourceAuthority
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_evidence(self) -> SourceAuthorityEvidence:
        body = self.model_dump(mode="python", exclude={"evidence_digest"})
        if self.evidence_digest != contract_digest(b"memorii.semantic-ingestion.source-authority-evidence.v1", body):
            raise ValueError("source authority evidence digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        source_digest: str,
        authority: SourceAuthority,
        provenance_digest: str,
    ) -> SourceAuthorityEvidence:
        body = {
            "source_id": source_id,
            "source_digest": source_digest,
            "metadata_field": "source_authority",
            "authority": authority,
            "provenance_digest": provenance_digest,
        }
        return cls(
            **body,
            evidence_digest=contract_digest(b"memorii.semantic-ingestion.source-authority-evidence.v1", body),
        )


class AuthenticatedEventTimeReference(BaseModel):
    kind: Literal["authenticated_event_time"] = "authenticated_event_time"
    source_field: Literal["event_time"] = "event_time"
    reference_instant: datetime
    authority_basis: Literal["server_event_metadata", "authenticated_external_time"]
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> AuthenticatedEventTimeReference:
        body = self.model_dump(mode="python", exclude={"reference_digest"})
        if self.reference_digest != contract_digest(b"memorii.semantic-ingestion.temporal-reference.v1", body):
            raise ValueError("temporal reference digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> AuthenticatedEventTimeReference:
        body = {"kind": "authenticated_event_time", "source_field": "event_time", **values}
        return cls(
            **body,
            reference_digest=contract_digest(b"memorii.semantic-ingestion.temporal-reference.v1", body),
        )


class AuthenticatedDocumentTimeReference(BaseModel):
    kind: Literal["authenticated_document_time"] = "authenticated_document_time"
    source_field: Literal["authenticated_document_time"] = "authenticated_document_time"
    reference_instant: datetime
    authority_basis: Literal["authenticated_document_metadata", "authenticated_external_time"]
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> AuthenticatedDocumentTimeReference:
        body = self.model_dump(mode="python", exclude={"reference_digest"})
        if self.reference_digest != contract_digest(b"memorii.semantic-ingestion.temporal-reference.v1", body):
            raise ValueError("temporal reference digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> AuthenticatedDocumentTimeReference:
        body = {
            "kind": "authenticated_document_time",
            "source_field": "authenticated_document_time",
            **values,
        }
        return cls(
            **body,
            reference_digest=contract_digest(b"memorii.semantic-ingestion.temporal-reference.v1", body),
        )


TemporalReferenceEvidence = Annotated[
    AuthenticatedEventTimeReference | AuthenticatedDocumentTimeReference,
    Field(discriminator="kind"),
]


class SourceSemanticContext(BaseModel):
    """Source-wide coordinates; segment governance is deliberately excluded."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trigger_mode: ExtractionTriggerMode
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_references: tuple[TemporalReferenceEvidence, ...]
    received_at: datetime
    retained_at: datetime
    source_effective_interval_evidence: AuthenticatedSourceIntervalEvidence | None
    provider_egress_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    governance_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_context(self) -> SourceSemanticContext:
        references = tuple(reference.reference_digest for reference in self.temporal_references)
        if references != tuple(sorted(references)) or len(set(references)) != len(references):
            raise ValueError("source semantic temporal references must be canonical")
        interval_digest = (
            None
            if self.source_effective_interval_evidence is None
            else self.source_effective_interval_evidence.evidence_digest
        )
        body = {
            "version": 1,
            "source_id": self.source_id,
            "source_digest": self.source_digest,
            "trigger_mode": self.trigger_mode,
            "provenance_digest": self.provenance_digest,
            "temporal_reference_digests": references,
            "received_at": self.received_at,
            "retained_at": self.retained_at,
            "source_effective_interval_evidence_digest": interval_digest,
            "provider_egress_policy_fingerprint": self.provider_egress_policy_fingerprint,
            "governance_policy_fingerprint": self.governance_policy_fingerprint,
            "trust_policy_fingerprint": self.trust_policy_fingerprint,
        }
        if self.context_digest != contract_digest(b"memorii.semantic-ingestion.source-semantic-context", body):
            raise ValueError("source semantic context digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SourceSemanticContext:
        references = values["temporal_references"]
        interval = values["source_effective_interval_evidence"]
        assert isinstance(references, tuple)
        body = {
            "version": 1,
            "source_id": values["source_id"],
            "source_digest": values["source_digest"],
            "trigger_mode": values["trigger_mode"],
            "provenance_digest": values["provenance_digest"],
            "temporal_reference_digests": tuple(reference.reference_digest for reference in references),
            "received_at": values["received_at"],
            "retained_at": values["retained_at"],
            "source_effective_interval_evidence_digest": None if interval is None else interval.evidence_digest,
            "provider_egress_policy_fingerprint": values["provider_egress_policy_fingerprint"],
            "governance_policy_fingerprint": values["governance_policy_fingerprint"],
            "trust_policy_fingerprint": values["trust_policy_fingerprint"],
        }
        return cls(
            **values, context_digest=contract_digest(b"memorii.semantic-ingestion.source-semantic-context", body)
        )


class TrustDecayStep(BaseModel):
    minimum_age: timedelta
    authority_loss: int = Field(ge=0)
    eligibility: Literal["eligible", "ineligible"] = "eligible"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_step(self) -> TrustDecayStep:
        if self.minimum_age < timedelta(0):
            raise ValueError("trust decay minimum age must be non-negative")
        return self


class PredicateTrustRule(BaseModel):
    predicate_id: str = Field(min_length=1)
    eligible_authority_classes: frozenset[str]
    authority_rank_by_class: Mapping[str, int]
    incomparable_class_pairs: tuple[tuple[str, str], ...] = ()
    decay_age_basis: Literal[
        "assertion_system_start",
        "authenticated_event_time",
    ] = "assertion_system_start"
    decay_schedule_by_class: Mapping[str, tuple[TrustDecayStep, ...]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_rule(self) -> PredicateTrustRule:
        if not self.authority_rank_by_class or any(
            not authority_class for authority_class in self.authority_rank_by_class
        ):
            raise ValueError("trust authority classes must be nonempty")
        if not self.eligible_authority_classes.issubset(self.authority_rank_by_class):
            raise ValueError("each eligible authority class requires a rank")
        pairs = tuple(tuple(sorted(pair)) for pair in self.incomparable_class_pairs)
        if any(len(pair) != 2 or pair[0] == pair[1] for pair in pairs):
            raise ValueError("incomparable authority pair must contain two distinct classes")
        if self.incomparable_class_pairs != pairs or tuple(sorted(set(pairs))) != pairs:
            raise ValueError("incomparable authority pairs must be canonical")
        if any(not set(pair).issubset(self.eligible_authority_classes) for pair in pairs):
            raise ValueError("incomparable authority pair references an ineligible class")
        if not set(self.decay_schedule_by_class).issubset(self.authority_rank_by_class):
            raise ValueError("trust decay schedule references an unknown authority class")
        for authority_class, steps in self.decay_schedule_by_class.items():
            if not authority_class:
                raise ValueError("trust decay authority class is empty")
            ages = tuple(step.minimum_age for step in steps)
            losses = tuple(step.authority_loss for step in steps)
            if ages != tuple(sorted(set(ages))):
                raise ValueError("trust decay thresholds must be strictly increasing")
            if losses != tuple(sorted(losses)):
                raise ValueError("trust decay authority loss must be non-decreasing")
            ineligible = False
            for step in steps:
                if ineligible and step.eligibility == "eligible":
                    raise ValueError("trust decay eligibility cannot re-enter")
                ineligible = ineligible or step.eligibility == "ineligible"
        return self

    @model_serializer(mode="wrap")
    def serialize_rule(self, handler):
        values = handler(self)
        # Preserve the shipped no-decay policy bytes.  Decay-bearing policies
        # include both fields, so the age basis can never be detached from its
        # schedule.
        if not self.decay_schedule_by_class:
            values.pop("decay_age_basis", None)
            values.pop("decay_schedule_by_class", None)
        return values


class TrustPolicySnapshot(BaseModel):
    schema_id: Literal["memorii.semantic_ingestion.trust_policy"] = "memorii.semantic_ingestion.trust_policy"
    schema_version: Literal[1] = 1
    policy_revision: str = Field(min_length=1)
    system_effective_interval: TimeInterval
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    rules: tuple[PredicateTrustRule, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_rules(self) -> TrustPolicySnapshot:
        ids = tuple(rule.predicate_id for rule in self.rules)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("trust rules must be ordered and unique")
        fingerprint = contract_digest(b"memorii.semantic-ingestion.trust-policy-rules.v1", self.rules)
        if self.fingerprint != fingerprint:
            raise ValueError("trust policy fingerprint mismatch")
        body = {name: getattr(self, name) for name in type(self).model_fields if name != "snapshot_digest"}
        if self.snapshot_digest != contract_digest(b"memorii.semantic-ingestion.trust-policy-snapshot.v1", body):
            raise ValueError("trust policy snapshot digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        policy_revision: str,
        system_effective_interval: TimeInterval,
        rules: tuple[PredicateTrustRule, ...],
    ) -> TrustPolicySnapshot:
        fingerprint = contract_digest(b"memorii.semantic-ingestion.trust-policy-rules.v1", rules)
        body = {
            "schema_id": "memorii.semantic_ingestion.trust_policy",
            "schema_version": 1,
            "policy_revision": policy_revision,
            "system_effective_interval": system_effective_interval,
            "fingerprint": fingerprint,
            "rules": rules,
        }
        return cls(
            **body, snapshot_digest=contract_digest(b"memorii.semantic-ingestion.trust-policy-snapshot.v1", body)
        )

    def active_at(self, coordinate: datetime) -> bool:
        return self.system_effective_interval.start <= coordinate and (
            self.system_effective_interval.end is None or coordinate < self.system_effective_interval.end
        )

    def rule_for(self, predicate_id: str) -> PredicateTrustRule:
        for rule in self.rules:
            if rule.predicate_id == predicate_id:
                return rule
        raise ValueError("predicate has no trust rule")


class PredicateTemporalRule(BaseModel):
    predicate_id: str = Field(min_length=1)
    valid_time_requirement: Literal["required", "optional", "atemporal"]
    allow_open_end: bool
    allow_reference_as_effective_start: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class TemporalPolicySnapshot(BaseModel):
    schema_id: Literal["memorii.semantic_ingestion.temporal_policy"] = "memorii.semantic_ingestion.temporal_policy"
    schema_version: Literal[1] = 1
    policy_revision: str = Field(min_length=1)
    system_effective_interval: TimeInterval
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    rules: tuple[PredicateTemporalRule, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_rules(self) -> TemporalPolicySnapshot:
        ids = tuple(rule.predicate_id for rule in self.rules)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("temporal rules must be ordered and unique")
        fingerprint = contract_digest(b"memorii.semantic-ingestion.temporal-policy-rules.v1", self.rules)
        if self.fingerprint != fingerprint:
            raise ValueError("temporal policy fingerprint mismatch")
        body = {name: getattr(self, name) for name in type(self).model_fields if name != "snapshot_digest"}
        if self.snapshot_digest != contract_digest(b"memorii.semantic-ingestion.temporal-policy-snapshot.v1", body):
            raise ValueError("temporal policy snapshot digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        policy_revision: str,
        system_effective_interval: TimeInterval,
        rules: tuple[PredicateTemporalRule, ...],
    ) -> TemporalPolicySnapshot:
        fingerprint = contract_digest(b"memorii.semantic-ingestion.temporal-policy-rules.v1", rules)
        body = {
            "schema_id": "memorii.semantic_ingestion.temporal_policy",
            "schema_version": 1,
            "policy_revision": policy_revision,
            "system_effective_interval": system_effective_interval,
            "fingerprint": fingerprint,
            "rules": rules,
        }
        return cls(
            **body, snapshot_digest=contract_digest(b"memorii.semantic-ingestion.temporal-policy-snapshot.v1", body)
        )

    def active_at(self, coordinate: datetime) -> bool:
        return self.system_effective_interval.start <= coordinate and (
            self.system_effective_interval.end is None or coordinate < self.system_effective_interval.end
        )

    def rule_for(self, predicate_id: str) -> PredicateTemporalRule:
        for rule in self.rules:
            if rule.predicate_id == predicate_id:
                return rule
        raise ValueError("predicate has no temporal rule")


class SemanticArbitrationPolicyBundle(BaseModel):
    """The unique immutable trust/temporal pair used by one semantic ingestion operation."""

    trust_policy: TrustPolicySnapshot
    temporal_policy: TemporalPolicySnapshot
    arbitration_as_of: datetime
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_bundle(self) -> SemanticArbitrationPolicyBundle:
        if not self.trust_policy.active_at(self.arbitration_as_of):
            raise ValueError("trust policy is not active at arbitration coordinate")
        if not self.temporal_policy.active_at(self.arbitration_as_of):
            raise ValueError("temporal policy is not active at arbitration coordinate")
        body = {name: getattr(self, name) for name in type(self).model_fields if name != "bundle_digest"}
        if self.bundle_digest != contract_digest(b"memorii.semantic-ingestion.arbitration-policy-bundle.v1", body):
            raise ValueError("arbitration policy bundle digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        trust_policy: TrustPolicySnapshot,
        temporal_policy: TemporalPolicySnapshot,
        arbitration_as_of: datetime,
    ) -> SemanticArbitrationPolicyBundle:
        body = {
            "trust_policy": trust_policy,
            "temporal_policy": temporal_policy,
            "arbitration_as_of": arbitration_as_of,
        }
        return cls(
            **body, bundle_digest=contract_digest(b"memorii.semantic-ingestion.arbitration-policy-bundle.v1", body)
        )


class SemanticEgressAuthorizationBinding(BaseModel):
    tenant_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    classification: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    region: str = Field(min_length=1)
    retention_mode: str = Field(min_length=1)
    training_use: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticAuthorizationReadSet(BaseModel):
    """Immutable policy, egress, and deployment authority observed by one run."""

    policy_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_revision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_policy_revision: int | None = Field(default=None, ge=1)
    egress_decision_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    egress_binding: SemanticEgressAuthorizationBinding | None = None
    deployment_authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_active_epoch: int = Field(ge=1)
    deployment_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_read_set(self) -> SemanticAuthorizationReadSet:
        if (
            len(
                {
                    self.egress_policy_revision is None,
                    self.egress_decision_digest is None,
                    self.egress_binding is None,
                }
            )
            != 1
        ):
            raise ValueError("egress authorization coordinates must be present together")
        body = self.model_dump(mode="python", exclude={"read_set_digest"})
        if self.read_set_digest != contract_digest(b"memorii.semantic-ingestion.authorization-read-set.v1", body):
            raise ValueError("semantic authorization read-set digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        policy_bundle: SemanticArbitrationPolicyBundle,
        deployment_authorization_digest: str,
        deployment_active_epoch: int,
        deployment_decision_digest: str,
        egress_policy_revision: int | None = None,
        egress_decision_digest: str | None = None,
        egress_binding: SemanticEgressAuthorizationBinding | None = None,
    ) -> SemanticAuthorizationReadSet:
        body = {
            "policy_bundle_digest": policy_bundle.bundle_digest,
            "policy_revision_digest": contract_digest(
                b"memorii.semantic-ingestion.policy-revision-pair.v1",
                {
                    "trust": policy_bundle.trust_policy.snapshot_digest,
                    "temporal": policy_bundle.temporal_policy.snapshot_digest,
                },
            ),
            "egress_policy_revision": egress_policy_revision,
            "egress_decision_digest": egress_decision_digest,
            "egress_binding": egress_binding,
            "deployment_authorization_digest": deployment_authorization_digest,
            "deployment_active_epoch": deployment_active_epoch,
            "deployment_decision_digest": deployment_decision_digest,
        }
        return cls(
            **body,
            read_set_digest=contract_digest(b"memorii.semantic-ingestion.authorization-read-set.v1", body),
        )


AuthorizationUsePoint = Literal[
    "pre_request",
    "post_response",
    "pre_analysis",
    "pre_seal",
    "pre_commit",
    "recovery_activation",
]


class AuthorizationStageSnapshot(BaseModel):
    """One immutable read of every mutable authorization owner at a use point."""

    use_point: AuthorizationUsePoint
    server_now: datetime
    read_set: SemanticAuthorizationReadSet
    egress_policy_id: str | None = None
    egress_policy_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    egress_expires_at: datetime | None = None
    deployment_expires_at: datetime
    authority_record_id: str = Field(min_length=1)
    authority_revision: int = Field(ge=1)
    authority_coordinates_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_snapshot(self) -> AuthorizationStageSnapshot:
        if self.server_now.utcoffset() is None:
            raise ValueError("authorization snapshot server time must be timezone-aware")
        egress_values = (
            self.egress_policy_id,
            self.egress_policy_fingerprint,
            self.egress_expires_at,
        )
        if any(value is None for value in egress_values) != all(value is None for value in egress_values):
            raise ValueError("authorization snapshot egress coordinates must be complete")
        if (self.read_set.egress_policy_revision is None) != (self.egress_policy_id is None):
            raise ValueError("authorization snapshot egress decision differs from its read set")
        if self.egress_policy_id is not None:
            assert self.egress_policy_fingerprint is not None
            assert self.egress_expires_at is not None
            assert self.read_set.egress_policy_revision is not None
            assert self.read_set.egress_decision_digest is not None
            assert self.read_set.egress_binding is not None
            egress_decision = {
                "binding": self.read_set.egress_binding,
                "policy_id": self.egress_policy_id,
                "policy_revision": self.read_set.egress_policy_revision,
                "policy_fingerprint": self.egress_policy_fingerprint,
                "expires_at": self.egress_expires_at,
            }
            if self.read_set.egress_decision_digest != contract_digest(
                b"memorii.semantic-ingestion.egress-decision.v1", egress_decision
            ):
                raise ValueError("authorization snapshot egress decision coordinates are invalid")
        if self.deployment_expires_at <= self.server_now or (
            self.egress_expires_at is not None and self.egress_expires_at <= self.server_now
        ):
            raise ValueError("authorization snapshot contains expired authority")
        body = self.model_dump(mode="python", exclude={"snapshot_digest"})
        if self.snapshot_digest != contract_digest(b"memorii.semantic-ingestion.authorization-stage-snapshot.v1", body):
            raise ValueError("authorization stage snapshot digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> AuthorizationStageSnapshot:
        return cls(
            **values,
            snapshot_digest=contract_digest(b"memorii.semantic-ingestion.authorization-stage-snapshot.v1", values),
        )


class SemanticAuthorizationReadSetProvider(Protocol):
    def current_snapshot(
        self,
        *,
        policy_bundle: SemanticArbitrationPolicyBundle,
        use_point: AuthorizationUsePoint,
    ) -> AuthorizationStageSnapshot | None: ...


class SemanticAuthorizationReadSetVerifier(Protocol):
    def verify_current(
        self,
        read_set: SemanticAuthorizationReadSet,
        *,
        use_point: Literal["pre_commit"],
    ) -> bool: ...


class AuthenticatedSourceIntervalEvidence(BaseModel):
    kind: Literal["authenticated_source_interval"] = "authenticated_source_interval"
    source_field: Literal["source_effective_interval"] = "source_effective_interval"
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    interval: TimeInterval
    authority_basis: Literal["server_source_metadata", "authenticated_external_interval"]
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_revision: str = Field(min_length=1)
    source_authority_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_evidence(self) -> AuthenticatedSourceIntervalEvidence:
        body = self.model_dump(mode="python", exclude={"evidence_digest"})
        if self.evidence_digest != contract_digest(b"memorii.semantic-ingestion.source-interval-evidence.v1", body):
            raise ValueError("authenticated source interval evidence digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        source_digest: str,
        interval: TimeInterval,
        authority_basis: Literal["server_source_metadata", "authenticated_external_interval"],
        provenance_digest: str,
        policy_revision: str,
        source_authority_evidence_digest: str,
    ) -> AuthenticatedSourceIntervalEvidence:
        body = {
            "kind": "authenticated_source_interval",
            "source_field": "source_effective_interval",
            "source_id": source_id,
            "source_digest": source_digest,
            "interval": interval,
            "authority_basis": authority_basis,
            "provenance_digest": provenance_digest,
            "policy_revision": policy_revision,
            "source_authority_evidence_digest": source_authority_evidence_digest,
        }
        return cls(
            **body,
            evidence_digest=contract_digest(b"memorii.semantic-ingestion.source-interval-evidence.v1", body),
        )


class TemporalEvidenceCandidate(BaseModel):
    candidate_id: str = Field(min_length=1)
    kind: Literal["authenticated_source_interval", "certified_text_interval"]
    interval: TimeInterval
    source_authority: SourceAuthority
    authenticated_source_interval_evidence: AuthenticatedSourceIntervalEvidence | None = None
    certified_text_candidate_id: str | None = None
    evidence_spans: tuple[SourceSpan, ...] = ()
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> TemporalEvidenceCandidate:
        if self.kind == "authenticated_source_interval":
            evidence = self.authenticated_source_interval_evidence
            if evidence is None or self.certified_text_candidate_id is not None or self.evidence_spans:
                raise ValueError("authenticated interval candidate has an invalid evidence shape")
            if evidence.interval != self.interval:
                raise ValueError("authenticated interval candidate changed its source evidence")
        elif (
            self.authenticated_source_interval_evidence is not None
            or self.certified_text_candidate_id is None
            or not self.evidence_spans
        ):
            raise ValueError("certified text candidate requires its exact nonempty source spans")
        body = self.model_dump(mode="python", exclude={"candidate_digest"})
        if self.candidate_digest != contract_digest(b"memorii.semantic-ingestion.temporal-candidate.v1", body):
            raise ValueError("temporal candidate digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        candidate_id: str,
        kind: Literal["authenticated_source_interval", "certified_text_interval"],
        interval: TimeInterval,
        source_authority: SourceAuthority,
        authenticated_source_interval_evidence: AuthenticatedSourceIntervalEvidence | None = None,
        certified_text_candidate_id: str | None = None,
        evidence_spans: tuple[SourceSpan, ...] = (),
    ) -> TemporalEvidenceCandidate:
        body = {
            "candidate_id": candidate_id,
            "kind": kind,
            "interval": interval,
            "source_authority": source_authority,
            "authenticated_source_interval_evidence": authenticated_source_interval_evidence,
            "certified_text_candidate_id": certified_text_candidate_id,
            "evidence_spans": evidence_spans,
        }
        return cls(**body, candidate_digest=contract_digest(b"memorii.semantic-ingestion.temporal-candidate.v1", body))


class TemporalEvidenceDecisionClosure(BaseModel):
    outcome: Literal["pass", "unknown", "contested"]
    candidates: tuple[TemporalEvidenceCandidate, ...]
    selected_candidate_ids: tuple[str, ...] = ()
    contested_candidate_ids: tuple[str, ...] = ()
    resolved_interval: TimeInterval | None = None
    resolution_rule: Literal[
        "trust_selected_text_interval",
        "trust_selected_source_interval",
        "trust_co_supported_equal_interval",
        "trust_contested_nonidentical_top_evidence",
        "authenticated_reference_open_start",
        "atemporal",
        "unresolved",
    ]
    temporal_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_policy_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_policy_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    arbitration_as_of: datetime
    closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_closure(self) -> TemporalEvidenceDecisionClosure:
        for candidate in self.candidates:
            TemporalEvidenceCandidate.model_validate(candidate.model_dump(mode="python"))
        ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("temporal candidates must be ordered by candidate ID")
        selected = self.selected_candidate_ids
        contested = self.contested_candidate_ids
        if selected != tuple(sorted(set(selected))) or contested != tuple(sorted(set(contested))):
            raise ValueError("decision IDs must be canonical")
        if not set(selected).issubset(ids) or not set(contested).issubset(ids) or set(selected) & set(contested):
            raise ValueError("decision IDs must be disjoint candidate subsets")
        by_id = {candidate.candidate_id: candidate for candidate in self.candidates}
        if self.outcome == "pass":
            if contested or self.resolution_rule == "unresolved":
                raise ValueError("pass closure cannot be unresolved or contested")
            if self.resolution_rule == "atemporal":
                if self.candidates or selected or self.resolved_interval is not None:
                    raise ValueError("atemporal closure has no candidates or valid interval")
            elif self.resolution_rule == "authenticated_reference_open_start":
                if (
                    self.candidates
                    or selected
                    or self.resolved_interval is None
                    or self.resolved_interval.end is not None
                ):
                    raise ValueError("reference-open-start closure requires only an open resolved interval")
            else:
                if not selected or self.resolved_interval is None:
                    raise ValueError("trust-selected pass closure requires selected asserted interval")
                if any(by_id[candidate_id].interval != self.resolved_interval for candidate_id in selected):
                    raise ValueError("selected temporal candidates must equal the resolved interval")
        elif self.outcome == "contested":
            if (
                not contested
                or selected
                or self.resolved_interval is not None
                or self.resolution_rule != "trust_contested_nonidentical_top_evidence"
            ):
                raise ValueError("contested closure must retain top alternatives")
        elif selected or contested or self.resolved_interval is not None or self.resolution_rule != "unresolved":
            raise ValueError("unknown closure must be non-promoting")
        body = self.model_dump(mode="python", exclude={"closure_digest"})
        if self.closure_digest != contract_digest(b"memorii.semantic-ingestion.temporal-decision-closure.v1", body):
            raise ValueError("temporal decision closure digest mismatch")
        return self


class SourceSpan(BaseModel):
    source_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_span(self) -> SourceSpan:
        if self.end <= self.start:
            raise ValueError("source span must be nonempty")
        return self


class SourceLocalIdentityEvidence(BaseModel):
    source_id: str = Field(min_length=1)
    mention_span: SourceSpan
    cluster_id: str = Field(min_length=1)
    canonical_entity_id: str | None = None
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_source(self) -> SourceLocalIdentityEvidence:
        if self.source_id != self.mention_span.source_id:
            raise ValueError("identity evidence span must belong to its source")
        return self


TemporalRole = Literal["assertion", "replacement", "transition"]
OperationKind = Literal["fact", "action", "correction", "retraction", "identity"]


class OperationTemporalAttachmentBinding(BaseModel):
    operation_id: str = Field(min_length=1)
    temporal_role: TemporalRole
    stable_attachment_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_ids: tuple[str, ...]
    candidate_spans: tuple[SourceSpan, ...]
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_binding(self) -> OperationTemporalAttachmentBinding:
        if self.candidate_ids != tuple(sorted(set(self.candidate_ids))):
            raise ValueError("temporal attachment IDs must be ordered and unique")
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != contract_digest(b"memorii.semantic-ingestion.temporal_attachment_binding.v1", body):
            raise ValueError("temporal attachment binding digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        temporal_role: TemporalRole,
        stable_attachment_consensus_digest: str,
        candidate_ids: tuple[str, ...],
        candidate_spans: tuple[SourceSpan, ...],
    ) -> OperationTemporalAttachmentBinding:
        body = {
            "operation_id": operation_id,
            "temporal_role": temporal_role,
            "stable_attachment_consensus_digest": stable_attachment_consensus_digest,
            "candidate_ids": candidate_ids,
            "candidate_spans": candidate_spans,
        }
        return cls(
            **body, binding_digest=contract_digest(b"memorii.semantic-ingestion.temporal_attachment_binding.v1", body)
        )


class OperationTemporalDecisionBinding(BaseModel):
    operation_id: str = Field(min_length=1)
    temporal_role: TemporalRole
    scope_assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_attachment: OperationTemporalAttachmentBinding
    reference_evidence: TemporalReferenceEvidence | None = None
    decision_closure: TemporalEvidenceDecisionClosure
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_binding(self) -> OperationTemporalDecisionBinding:
        attachment = self.temporal_attachment
        if attachment.operation_id != self.operation_id or attachment.temporal_role != self.temporal_role:
            raise ValueError("temporal attachment does not bind this operation role")
        if attachment.candidate_ids != tuple(candidate.candidate_id for candidate in self.decision_closure.candidates):
            raise ValueError("temporal attachment candidates do not equal the decision closure")
        if self.decision_closure.resolution_rule == "authenticated_reference_open_start":
            if self.reference_evidence is None or self.decision_closure.resolved_interval is None:
                raise ValueError("reference-open-start closure requires exact reference evidence")
            if self.reference_evidence.reference_instant != self.decision_closure.resolved_interval.start:
                raise ValueError("reference evidence does not equal the resolved interval start")
        elif self.reference_evidence is not None and self.decision_closure.resolution_rule != "atemporal":
            raise ValueError("unselected reference evidence cannot be attached to an interval")
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != contract_digest(b"memorii.semantic-ingestion.temporal_decision_binding.v1", body):
            raise ValueError("temporal decision binding digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        temporal_role: TemporalRole,
        scope_assessment_digest: str,
        semantic_assessment_digest: str,
        temporal_attachment: OperationTemporalAttachmentBinding,
        decision_closure: TemporalEvidenceDecisionClosure,
        reference_evidence: TemporalReferenceEvidence | None = None,
    ) -> OperationTemporalDecisionBinding:
        body = {
            "operation_id": operation_id,
            "temporal_role": temporal_role,
            "scope_assessment_digest": scope_assessment_digest,
            "semantic_assessment_digest": semantic_assessment_digest,
            "temporal_attachment": temporal_attachment,
            "reference_evidence": reference_evidence,
            "decision_closure": decision_closure,
        }
        return cls(
            **body, binding_digest=contract_digest(b"memorii.semantic-ingestion.temporal_decision_binding.v1", body)
        )


class ProposalAlignmentReference(BaseModel):
    """Untrusted proposer hint used only to align against source analysis."""

    role_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticCandidate(BaseModel):
    """Closed remote proposal. It intentionally contains no evidence authority."""

    candidate_id: str = Field(min_length=1)
    operation_kind: OperationKind
    predicate_id: str = Field(min_length=1)
    assertion_quote: str = Field(min_length=1)
    alignment_refs: tuple[ProposalAlignmentReference, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_candidate(self) -> SemanticCandidate:
        role_ids = tuple(value.role_id for value in self.alignment_refs)
        if role_ids != tuple(sorted(set(role_ids))):
            raise ValueError("proposal alignment references must be canonical")
        return self

    @property
    def candidate_digest(self) -> str:
        return contract_digest(b"memorii.semantic-ingestion.semantic-candidate.v1", self)


class SourceTemporalEvidenceSet(BaseModel):
    temporal_role: TemporalRole
    candidates: tuple[TemporalEvidenceCandidate, ...]
    reference_evidence: TemporalReferenceEvidence | None = None
    attachment_spans: tuple[SourceSpan, ...]
    attachment_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_set(self) -> SourceTemporalEvidenceSet:
        ids = tuple(value.candidate_id for value in self.candidates)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("source temporal candidates must be canonical")
        if any(value.kind == "certified_text_interval" for value in self.candidates) and not self.attachment_spans:
            raise ValueError("textual temporal evidence requires attachment spans")
        return self


class IndependentSourceAnalysis(BaseModel):
    """Source-only analysis; proposer bytes cannot populate this artifact."""

    candidate_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_id: str = Field(min_length=1)
    operation_kind: OperationKind
    source_authority_evidence: SourceAuthorityEvidence | None = None
    claim_identity: AcceptedClaimIdentity | None = None
    assertion_span: SourceSpan
    parser_consensus: ParserConsensusAssessment
    identity_evidence: tuple[SourceLocalIdentityEvidence, ...]
    temporal_evidence: tuple[SourceTemporalEvidenceSet, ...]
    analysis_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_analysis(self) -> IndependentSourceAnalysis:
        if self.assertion_span.source_id != self.source_id:
            raise ValueError("assertion span does not belong to source analysis")
        if self.source_authority_evidence is not None and (
            self.source_authority_evidence.source_id != self.source_id
            or self.source_authority_evidence.source_digest != self.source_digest
        ):
            raise ValueError("source authority evidence does not bind this analysis")
        if self.claim_identity is not None and (
            self.operation_kind not in {"fact", "correction"}
            or self.claim_identity.assertion_key_at_recording.slot.predicate_id != self.predicate_id
        ):
            raise ValueError("claim identity does not bind this source analysis")
        if (
            self.parser_consensus.source_id != self.source_id
            or (self.parser_consensus.source_digest != self.source_digest)
            or self.parser_consensus.primary_interpretation.predicate_head_span.source_id != self.source_id
            or (self.parser_consensus.corroborating_interpretation.predicate_head_span.source_id != self.source_id)
        ):
            raise ValueError("parser consensus does not belong to source analysis")
        if any(value.source_id != self.source_id for value in self.identity_evidence):
            raise ValueError("identity evidence does not belong to source analysis")
        roles = tuple(value.temporal_role for value in self.temporal_evidence)
        expected = {
            "fact": ("assertion",),
            "action": ("assertion",),
            "correction": ("replacement", "transition"),
            "retraction": ("transition",),
            "identity": ("transition",),
        }[self.operation_kind]
        if roles != expected:
            raise ValueError("source temporal roles do not match operation kind")
        if any(span.source_id != self.source_id for value in self.temporal_evidence for span in value.attachment_spans):
            raise ValueError("temporal attachment span does not belong to source analysis")
        body = self.model_dump(mode="python", exclude={"analysis_digest"})
        if self.analysis_digest != contract_digest(b"memorii.semantic-ingestion.independent-source-analysis.v1", body):
            raise ValueError("independent source analysis digest mismatch")
        return self

    @model_serializer(mode="wrap")
    def serialize_analysis(self, handler):
        values = handler(self)
        if self.claim_identity is None:
            values.pop("claim_identity", None)
        return values

    @classmethod
    def create(cls, **values: object) -> IndependentSourceAnalysis:
        return cls.model_validate(
            {
                **values,
                "analysis_digest": contract_digest(
                    b"memorii.semantic-ingestion.independent-source-analysis.v1", values
                ),
            }
        )

    def temporal_roles(self) -> tuple[tuple[TemporalRole, tuple[TemporalEvidenceCandidate, ...]], ...]:
        return tuple((value.temporal_role, value.candidates) for value in self.temporal_evidence)


class SealedSemanticOperation(BaseModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(min_length=1)
    kind: OperationKind
    scope_assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_identity: AcceptedClaimIdentity | None = None
    source_authority_evidence: SourceAuthorityEvidence | None = None
    temporal_bindings: tuple[OperationTemporalDecisionBinding, ...]
    sealed_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_seal(self) -> SealedSemanticOperation:
        ordered = tuple(
            sorted(
                self.temporal_bindings,
                key=lambda value: (value.operation_id, value.temporal_role, value.binding_digest),
            )
        )
        if ordered != self.temporal_bindings or any(value.operation_id != self.operation_id for value in ordered):
            raise ValueError("sealed operation temporal bindings must be local and canonical")
        expected_roles = {
            "fact": {"assertion"},
            "action": {"assertion"},
            "correction": {"replacement", "transition"},
            "retraction": {"transition"},
            "identity": {"transition"},
        }[self.kind]
        if {value.temporal_role for value in ordered} != expected_roles or len(ordered) != len(expected_roles):
            raise ValueError("sealed operation has an invalid temporal role set")
        if (self.claim_identity is None) != (self.source_authority_evidence is None):
            raise ValueError("sealed claim identity and source authority must be present together")
        if self.claim_identity is not None and self.kind not in {"fact", "correction"}:
            raise ValueError("only claim-producing operations may carry claim identity")
        expected_scope_digest = contract_digest(
            b"memorii.semantic-ingestion.operation-scope-assessments.v1",
            tuple(value.scope_assessment_digest for value in ordered),
        )
        expected_semantic_digest = contract_digest(
            b"memorii.semantic-ingestion.operation-semantic-assessments.v1",
            tuple(value.semantic_assessment_digest for value in ordered),
        )
        if (
            self.scope_assessment_digest != expected_scope_digest
            or self.semantic_assessment_digest != expected_semantic_digest
        ):
            raise ValueError("sealed operation assessment closure mismatch")
        body = self.model_dump(mode="python", exclude={"sealed_operation_digest"})
        if self.sealed_operation_digest != contract_digest(b"memorii.semantic-ingestion.sealed-operation.v1", body):
            raise ValueError("sealed operation digest mismatch")
        return self

    @model_serializer(mode="wrap")
    def serialize_operation(self, handler):
        values = handler(self)
        if self.claim_identity is None:
            values.pop("claim_identity", None)
            values.pop("source_authority_evidence", None)
        return values


class AcceptedTemporalEvidence(BaseModel):
    reference_evidence: TemporalReferenceEvidence | None = None
    decision_closure: TemporalEvidenceDecisionClosure

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_accepted(self) -> AcceptedTemporalEvidence:
        if self.decision_closure.outcome != "pass":
            raise ValueError("accepted temporal evidence requires a pass closure")
        if self.decision_closure.resolution_rule == "authenticated_reference_open_start":
            if self.reference_evidence is None or self.decision_closure.resolved_interval is None:
                raise ValueError("accepted reference interval requires exact reference evidence")
            if self.reference_evidence.reference_instant != self.decision_closure.resolved_interval.start:
                raise ValueError("accepted reference evidence does not equal interval start")
        elif self.reference_evidence is not None and self.decision_closure.resolution_rule != "atemporal":
            raise ValueError("accepted evidence contains an unselected reference")
        return self

    @property
    def valid_interval(self) -> TimeInterval | None:
        return self.decision_closure.resolved_interval


class _TemporalCarrier(BaseModel):
    operation_id: str = Field(min_length=1)
    valid_interval: TimeInterval | None
    temporal_evidence: AcceptedTemporalEvidence
    temporal_decision_binding: OperationTemporalDecisionBinding
    record_version: int = Field(default=1, ge=1)
    codec_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_binding(self) -> _TemporalCarrier:
        closure = self.temporal_evidence.decision_closure
        if self.temporal_decision_binding.operation_id != self.operation_id:
            raise ValueError("temporal carrier operation binding mismatch")
        if self.temporal_decision_binding.decision_closure != closure:
            raise ValueError("temporal carrier closure binding mismatch")
        if self.valid_interval != closure.resolved_interval:
            raise ValueError("temporal carrier valid interval mismatch")
        body = self.model_dump(mode="python", exclude={"record_digest"})
        if self.record_digest != contract_digest(b"memorii.semantic-ingestion.temporal-carrier.v1", body):
            raise ValueError("temporal carrier digest mismatch")
        return self


class ClaimAssertion(_TemporalCarrier):
    record_kind: Literal["claim_assertion"] = "claim_assertion"
    claim_assertion_id: str = Field(min_length=1)
    statement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_identity: AcceptedClaimIdentity | None = None
    source_authority_evidence: SourceAuthorityEvidence | None = None
    predicate_trust_rule: PredicateTrustRule | None = None

    @model_validator(mode="after")
    def validate_claim_authority(self) -> ClaimAssertion:
        typed = (
            self.claim_identity,
            self.source_authority_evidence,
            self.predicate_trust_rule,
        )
        if any(value is None for value in typed) != all(value is None for value in typed):
            raise ValueError("typed claim identity and authority closure must be complete")
        if self.claim_identity is None:
            return self
        assert self.source_authority_evidence is not None
        assert self.predicate_trust_rule is not None
        slot = self.claim_identity.assertion_key_at_recording.slot
        if self.predicate_trust_rule.predicate_id != slot.predicate_id:
            raise ValueError("claim trust rule does not bind its canonical slot")
        if any(
            candidate.source_authority != self.source_authority_evidence.authority
            for candidate in self.temporal_evidence.decision_closure.candidates
        ):
            raise ValueError("claim temporal evidence differs from source authority evidence")
        return self

    @model_serializer(mode="wrap")
    def serialize_claim(self, handler):
        values = handler(self)
        if self.claim_identity is None:
            values.pop("claim_identity", None)
            values.pop("source_authority_evidence", None)
            values.pop("predicate_trust_rule", None)
        return values


class ActionRevision(_TemporalCarrier):
    record_kind: Literal["action_revision"] = "action_revision"
    action_revision_id: str = Field(min_length=1)
    statement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdentityLineageRecord(_TemporalCarrier):
    record_kind: Literal["identity_lineage"] = "identity_lineage"
    identity_lineage_id: str = Field(min_length=1)
    statement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transition: CompiledIdentityLineageTransition

    @model_validator(mode="after")
    def validate_lineage_transition(self) -> IdentityLineageRecord:
        binding = self.temporal_decision_binding
        if (
            self.operation_id != self.transition.operation_id
            or self.statement_digest != self.transition.transition_digest
            or self.valid_interval != self.temporal_evidence.decision_closure.resolved_interval
            or binding.temporal_role != "transition"
        ):
            raise ValueError("identity_lineage_carrier_binding_mismatch")
        return self


class TemporalTransitionRecord(_TemporalCarrier):
    record_kind: Literal["temporal_transition"] = "temporal_transition"
    transition_kind: Literal["correction", "retraction"]
    transition_id: str = Field(min_length=1)
    statement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_interval: TimeInterval | None


SemanticDurableCarrier = Annotated[
    ClaimAssertion | ActionRevision | IdentityLineageRecord | TemporalTransitionRecord,
    Field(discriminator="record_kind"),
]


class SemanticTerminalBindingSet(BaseModel):
    operation_id: str = Field(min_length=1)
    bindings: tuple[OperationTemporalDecisionBinding, ...]
    binding_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_set(self) -> SemanticTerminalBindingSet:
        ordered = tuple(
            sorted(self.bindings, key=lambda value: (value.operation_id, value.temporal_role, value.binding_digest))
        )
        if ordered != self.bindings or any(value.operation_id != self.operation_id for value in ordered):
            raise ValueError("terminal bindings must be operation-local and canonical")
        if len({value.temporal_role for value in self.bindings}) != len(self.bindings):
            raise ValueError("terminal temporal roles must be unique")
        body = self.model_dump(mode="python", exclude={"binding_set_digest"})
        if self.binding_set_digest != contract_digest(b"memorii.semantic-ingestion.terminal-binding-set.v1", body):
            raise ValueError("terminal binding-set digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, operation_id: str, bindings: tuple[OperationTemporalDecisionBinding, ...]
    ) -> SemanticTerminalBindingSet:
        body = {"operation_id": operation_id, "bindings": bindings}
        return cls(
            **body, binding_set_digest=contract_digest(b"memorii.semantic-ingestion.terminal-binding-set.v1", body)
        )


class SemanticExecutionLineage(BaseModel):
    operation_id: str = Field(min_length=1)
    proposal_attempt_digests: tuple[str, ...]
    source_analysis_digests: tuple[str, ...]
    sealed_operation_digests: tuple[str, ...]
    prompt_authority_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    egress_decision_digests: tuple[str, ...] = ()
    arbitration_policy_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_lineage(self) -> SemanticExecutionLineage:
        for values in (
            self.proposal_attempt_digests,
            self.source_analysis_digests,
            self.sealed_operation_digests,
            self.egress_decision_digests,
        ):
            if any(len(value) != 64 for value in values):
                raise ValueError("semantic ingestion lineage contains a non-digest coordinate")
        body = self.model_dump(mode="python", exclude={"lineage_digest"})
        if self.lineage_digest != contract_digest(b"memorii.semantic-ingestion.execution-lineage.v1", body):
            raise ValueError("semantic ingestion execution lineage digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SemanticExecutionLineage:
        return cls.model_validate(
            {
                **values,
                "lineage_digest": contract_digest(b"memorii.semantic-ingestion.execution-lineage.v1", values),
            }
        )


class SemanticTerminalOutcome(BaseModel):
    operation_id: str = Field(min_length=1)
    status: Literal["accepted", "unresolved", "rejected", "evidence_only"]
    reason_codes: tuple[str, ...]
    candidates: tuple[SemanticCandidate, ...]
    source_analyses: tuple[IndependentSourceAnalysis, ...] = ()
    arbitration_policy_bundle: SemanticArbitrationPolicyBundle | None = None
    authorization_read_set: SemanticAuthorizationReadSet | None = None
    execution_lineage: SemanticExecutionLineage | None = None
    temporal_closures: tuple[TemporalEvidenceDecisionClosure, ...]
    carrier_artifact_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    sealed_operations: tuple[SealedSemanticOperation, ...] = ()
    accepted_carriers: tuple[SemanticDurableCarrier, ...] = ()
    terminal_binding_sets: tuple[SemanticTerminalBindingSet, ...] = ()
    attempt_count: int = Field(ge=0, le=2)
    terminal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def candidate_set_digest(self) -> str:
        return contract_digest(b"memorii.semantic-ingestion.semantic-candidate-set.v1", self.candidates)

    @model_validator(mode="after")
    def validate_terminal(self) -> SemanticTerminalOutcome:
        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if candidate_ids != tuple(sorted(set(candidate_ids))):
            raise ValueError("terminal candidates must be canonical")
        sealed_ids = tuple(value.candidate_id for value in self.sealed_operations)
        if sealed_ids != tuple(sorted(set(sealed_ids))) or not set(sealed_ids).issubset(candidate_ids):
            raise ValueError("terminal sealed operations must be canonical candidate members")
        binding_operation_ids = tuple(value.operation_id for value in self.terminal_binding_sets)
        if binding_operation_ids != tuple(sorted(set(binding_operation_ids))):
            raise ValueError("terminal binding sets must be canonical and unique")
        if self.status == "accepted":
            if self.arbitration_policy_bundle is None:
                raise ValueError("accepted terminal requires its immutable arbitration policy bundle")
            if self.authorization_read_set is None:
                raise ValueError("accepted terminal requires its immutable authorization read set")
            if self.authorization_read_set.policy_bundle_digest != self.arbitration_policy_bundle.bundle_digest:
                raise ValueError("accepted terminal authorization does not bind its policy bundle")
            if self.execution_lineage is None:
                raise ValueError("accepted terminal requires complete execution lineage")
            if tuple(value.candidate_id for value in self.source_analyses) != candidate_ids:
                raise ValueError("accepted terminal requires one source analysis per proposal")
            if self.execution_lineage.operation_id != self.operation_id or (
                self.execution_lineage.arbitration_policy_bundle_digest != self.arbitration_policy_bundle.bundle_digest
            ):
                raise ValueError("accepted terminal lineage does not bind its policy or operation")
            if (
                self.authorization_read_set is None
                or self.execution_lineage.authorization_read_set_digest != self.authorization_read_set.read_set_digest
            ):
                raise ValueError("accepted terminal lineage does not bind its authorization read set")
            if not self.candidates or len(self.sealed_operations) != len(self.candidates) or not self.accepted_carriers:
                raise ValueError("accepted terminal requires every sealed operation and canonical carrier")
            if set(binding_operation_ids) != {value.operation_id for value in self.sealed_operations}:
                raise ValueError("accepted terminal binding sets do not close every sealed operation")
            carrier_operations = {value.operation_id for value in self.accepted_carriers}
            if carrier_operations != set(binding_operation_ids):
                raise ValueError("accepted terminal carriers do not close every sealed operation")
            expected_kinds = {
                "fact": ("claim_assertion",),
                "action": ("action_revision",),
                "correction": ("claim_assertion", "temporal_transition"),
                "retraction": ("temporal_transition",),
                "identity": ("identity_lineage",),
            }
            analysis_by_candidate = {value.candidate_id: value for value in self.source_analyses}
            for operation in self.sealed_operations:
                operation_carriers = tuple(
                    value.record_kind
                    for value in self.accepted_carriers
                    if value.operation_id == operation.operation_id
                )
                if operation_carriers != expected_kinds[operation.kind]:
                    raise ValueError("accepted terminal has the wrong carrier family for an operation")
                analysis = analysis_by_candidate[operation.candidate_id]
                if (
                    analysis.claim_identity != operation.claim_identity
                    or (analysis.source_authority_evidence if operation.claim_identity is not None else None)
                    != operation.source_authority_evidence
                ):
                    raise ValueError("sealed claim identity differs from source analysis")
                for carrier in self.accepted_carriers:
                    if not isinstance(carrier, ClaimAssertion) or carrier.operation_id != operation.operation_id:
                        continue
                    expected_trust_rule = (
                        self.arbitration_policy_bundle.trust_policy.rule_for(
                            carrier.claim_identity.assertion_key_at_recording.slot.predicate_id
                        )
                        if carrier.claim_identity is not None
                        else None
                    )
                    if (
                        carrier.claim_identity != operation.claim_identity
                        or carrier.source_authority_evidence != operation.source_authority_evidence
                        or carrier.predicate_trust_rule != expected_trust_rule
                    ):
                        raise ValueError("claim carrier differs from its sealed authority closure")
            bound_closures = tuple(
                binding.decision_closure
                for operation in self.sealed_operations
                for binding in operation.temporal_bindings
            )
            if bound_closures != self.temporal_closures:
                raise ValueError("accepted terminal closures do not equal sealed role bindings")
            expected_carrier_digest = contract_digest(
                b"memorii.semantic-ingestion.terminal-carrier-artifact.v1",
                {
                    "operation_id": self.operation_id,
                    "sealed_operations": self.sealed_operations,
                    "accepted_carriers": self.accepted_carriers,
                    "terminal_binding_sets": self.terminal_binding_sets,
                },
            )
            if self.carrier_artifact_digest != expected_carrier_digest:
                raise ValueError("accepted terminal carrier artifact digest mismatch")
        else:
            if self.accepted_carriers or self.carrier_artifact_digest is not None:
                raise ValueError("non-accepted terminal cannot carry accepted durable records")
            if set(binding_operation_ids) != {value.operation_id for value in self.sealed_operations}:
                raise ValueError("non-accepted terminal binding sets do not close its sealed operations")
            for operation, binding_set in zip(
                sorted(self.sealed_operations, key=lambda value: value.operation_id),
                self.terminal_binding_sets,
                strict=True,
            ):
                if (
                    operation.operation_id != binding_set.operation_id
                    or operation.temporal_bindings != binding_set.bindings
                ):
                    raise ValueError("non-accepted terminal binding set differs from its sealed operation")
            if any(
                binding.decision_closure not in self.temporal_closures
                for operation in self.sealed_operations
                for binding in operation.temporal_bindings
            ):
                raise ValueError("non-accepted terminal omitted a sealed temporal closure")
        body = {name: getattr(self, name) for name in type(self).model_fields if name != "terminal_digest"}
        if self.terminal_digest != contract_digest(b"memorii.semantic-ingestion.semantic-terminal.v1", body):
            raise ValueError("semantic terminal digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        status: Literal["accepted", "unresolved", "rejected", "evidence_only"],
        reason_codes: tuple[str, ...],
        candidates: tuple[SemanticCandidate, ...],
        source_analyses: tuple[IndependentSourceAnalysis, ...] = (),
        arbitration_policy_bundle: SemanticArbitrationPolicyBundle | None = None,
        authorization_read_set: SemanticAuthorizationReadSet | None = None,
        execution_lineage: SemanticExecutionLineage | None = None,
        temporal_closures: tuple[TemporalEvidenceDecisionClosure, ...],
        carrier_artifact_digest: str | None = None,
        sealed_operations: tuple[SealedSemanticOperation, ...] = (),
        accepted_carriers: tuple[SemanticDurableCarrier, ...] = (),
        terminal_binding_sets: tuple[SemanticTerminalBindingSet, ...] = (),
        attempt_count: int,
    ) -> SemanticTerminalOutcome:
        values = {
            "operation_id": operation_id,
            "status": status,
            "reason_codes": reason_codes,
            "candidates": candidates,
            "source_analyses": source_analyses,
            "arbitration_policy_bundle": arbitration_policy_bundle,
            "authorization_read_set": authorization_read_set,
            "execution_lineage": execution_lineage,
            "temporal_closures": temporal_closures,
            "carrier_artifact_digest": carrier_artifact_digest,
            "sealed_operations": sealed_operations,
            "accepted_carriers": accepted_carriers,
            "terminal_binding_sets": terminal_binding_sets,
            "attempt_count": attempt_count,
        }
        return cls(
            **values, terminal_digest=contract_digest(b"memorii.semantic-ingestion.semantic-terminal.v1", values)
        )


class SemanticLifecycleTransition(BaseModel):
    """Append-only persisted transition for the protected provider lifecycle."""

    operation_id: str = Field(min_length=1)
    from_kind: Literal["selected_pipeline_pending", "accepted_candidate"]
    to_kind: Literal["accepted_candidate", "committed_terminal", "unsupported_input", "abstained"]
    candidate_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    terminal_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason_code: (
        Literal[
            "missing_language_declaration",
            "untrusted_language",
            "language_mismatch",
            "non_english_language",
            "mixed_residue",
            "unsupported_grammar",
            "extractor_abstained",
            "retry_budget_exhausted",
        ]
        | None
    ) = None
    predecessor_transition_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    transition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_transition(self) -> SemanticLifecycleTransition:
        if self.to_kind == "accepted_candidate":
            if (
                self.from_kind != "selected_pipeline_pending"
                or self.candidate_digest is None
                or self.terminal_digest is not None
                or self.reason_code is not None
                or self.predecessor_transition_digest is not None
            ):
                raise ValueError("accepted-candidate lifecycle transition is invalid")
        elif self.to_kind == "committed_terminal":
            if (
                self.from_kind != "accepted_candidate"
                or self.terminal_digest is None
                or self.candidate_digest is not None
                or self.reason_code is not None
                or self.predecessor_transition_digest is None
            ):
                raise ValueError("committed-terminal lifecycle transition is invalid")
        elif (
            self.terminal_digest is None
            or self.candidate_digest is not None
            or self.reason_code is None
            or (self.from_kind == "accepted_candidate") != (self.predecessor_transition_digest is not None)
        ):
            raise ValueError("nonpromoting terminal lifecycle transition is invalid")
        body = self.model_dump(mode="python", exclude={"transition_digest"})
        if self.transition_digest != contract_digest(b"memorii.semantic-ingestion.lifecycle-transition.v1", body):
            raise ValueError("semantic ingestion lifecycle transition digest mismatch")
        return self

    @classmethod
    def accepted_candidate(
        cls,
        *,
        operation_id: str,
        candidate_digest: str,
    ) -> SemanticLifecycleTransition:
        body = {
            "operation_id": operation_id,
            "from_kind": "selected_pipeline_pending",
            "to_kind": "accepted_candidate",
            "candidate_digest": candidate_digest,
            "terminal_digest": None,
            "reason_code": None,
            "predecessor_transition_digest": None,
        }
        return cls(
            **body,
            transition_digest=contract_digest(b"memorii.semantic-ingestion.lifecycle-transition.v1", body),
        )

    @classmethod
    def committed_terminal(
        cls,
        *,
        terminal: SemanticTerminalOutcome,
        accepted_transition: SemanticLifecycleTransition,
    ) -> SemanticLifecycleTransition:
        body = {
            "operation_id": terminal.operation_id,
            "from_kind": "accepted_candidate",
            "to_kind": "committed_terminal",
            "candidate_digest": None,
            "terminal_digest": terminal.terminal_digest,
            "reason_code": None,
            "predecessor_transition_digest": accepted_transition.transition_digest,
        }
        return cls(
            **body,
            transition_digest=contract_digest(b"memorii.semantic-ingestion.lifecycle-transition.v1", body),
        )

    @classmethod
    def nonpromoting_terminal(
        cls,
        *,
        terminal: SemanticTerminalOutcome,
        to_kind: Literal["unsupported_input", "abstained"],
        reason_code: Literal[
            "missing_language_declaration",
            "untrusted_language",
            "language_mismatch",
            "non_english_language",
            "mixed_residue",
            "unsupported_grammar",
            "extractor_abstained",
            "retry_budget_exhausted",
        ],
        accepted_transition: SemanticLifecycleTransition | None = None,
    ) -> SemanticLifecycleTransition:
        body = {
            "operation_id": terminal.operation_id,
            "from_kind": "accepted_candidate" if accepted_transition is not None else "selected_pipeline_pending",
            "to_kind": to_kind,
            "candidate_digest": None,
            "terminal_digest": terminal.terminal_digest,
            "reason_code": reason_code,
            "predecessor_transition_digest": (
                accepted_transition.transition_digest if accepted_transition is not None else None
            ),
        }
        return cls(
            **body,
            transition_digest=contract_digest(b"memorii.semantic-ingestion.lifecycle-transition.v1", body),
        )


class SemanticRetryableProgress(BaseModel):
    operation_id: str = Field(min_length=1)
    stage: Literal["policy_read", "proposal", "analysis", "planning", "group", "finalization"]
    failure_kind: Literal["policy_outage", "transport_outage", "store_outage"]
    attempt_count: int = Field(ge=1, le=3)
    terminal_artifact_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    progress_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_progress(self) -> SemanticRetryableProgress:
        body = self.model_dump(mode="python", exclude={"progress_digest"})
        if self.progress_digest != contract_digest(b"memorii.semantic-ingestion.retryable-progress.v1", body):
            raise ValueError("semantic ingestion retryable progress digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        stage: Literal["policy_read", "proposal", "analysis", "planning", "group", "finalization"],
        failure_kind: Literal["policy_outage", "transport_outage", "store_outage"],
        attempt_count: int,
        terminal_artifact_digest: str | None = None,
    ) -> SemanticRetryableProgress:
        body = {
            "operation_id": operation_id,
            "stage": stage,
            "failure_kind": failure_kind,
            "attempt_count": attempt_count,
            "terminal_artifact_digest": terminal_artifact_digest,
        }
        return cls(
            **body,
            progress_digest=contract_digest(b"memorii.semantic-ingestion.retryable-progress.v1", body),
        )


class SemanticRecoveryAuthorityBinding(BaseModel):
    """First authoritative coordinates appended before recovered learned work."""

    operation_id: str = Field(min_length=1)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_scope_id: str = Field(min_length=1)
    authority_record_id: str = Field(min_length=1)
    authority_revision: int = Field(ge=1)
    authority_coordinates_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_binding(self) -> SemanticRecoveryAuthorityBinding:
        expected_id = "semantic_ingestion:authorization:" + sha256(self.authority_scope_id.encode("utf-8")).hexdigest()
        if self.authority_record_id != expected_id:
            raise ValueError("recovery authority record does not bind its scope")
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != contract_digest(b"memorii.semantic-ingestion.recovery-authority-binding.v1", body):
            raise ValueError("recovery authority binding digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SemanticRecoveryAuthorityBinding:
        return cls(
            **values,
            binding_digest=contract_digest(b"memorii.semantic-ingestion.recovery-authority-binding.v1", values),
        )


class SemanticTransport(Protocol):
    def propose(self, request_bytes: bytes) -> bytes: ...


class SemanticPipelinePolicy(BaseModel):
    arbitration_bundle: SemanticArbitrationPolicyBundle

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticPipelinePolicyProvider(Protocol):
    def current_policy(self, *, source_id: str, source_digest: str) -> SemanticPipelinePolicy | None: ...


class SemanticCandidateAssessor(Protocol):
    """Independent source-analysis boundary; never implemented by the proposer."""

    def analyze(
        self,
        *,
        proposal: SemanticCandidate,
        source_id: str,
        source_digest: str,
        source_text: str,
        prepared_source: PreparedSource,
        source_authority_evidence: SourceAuthorityEvidence,
        source_interval_evidence: AuthenticatedSourceIntervalEvidence | None,
    ) -> IndependentSourceAnalysis | None: ...


class SemanticArtifactClosure(BaseModel):
    operation_id: str
    terminal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_operation_digests: tuple[str, ...]
    accepted_carrier_digests: tuple[str, ...]
    terminal_binding_set_digests: tuple[str, ...]
    execution_lineage_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    arbitration_policy_bundle_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    authorization_read_set_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_closure(self) -> SemanticArtifactClosure:
        for values in (self.sealed_operation_digests, self.accepted_carrier_digests, self.terminal_binding_set_digests):
            if values != tuple(sorted(set(values))):
                raise ValueError("artifact closure digests must be canonical")
        body = self.model_dump(mode="python", exclude={"closure_digest"})
        if self.closure_digest != contract_digest(b"memorii.semantic-ingestion.artifact-closure.v1", body):
            raise ValueError("semantic ingestion artifact closure digest mismatch")
        return self

    @classmethod
    def create(cls, terminal: SemanticTerminalOutcome) -> SemanticArtifactClosure:
        body = {
            "operation_id": terminal.operation_id,
            "terminal_digest": terminal.terminal_digest,
            "sealed_operation_digests": tuple(
                sorted(value.sealed_operation_digest for value in terminal.sealed_operations)
            ),
            "accepted_carrier_digests": tuple(sorted(value.record_digest for value in terminal.accepted_carriers)),
            "terminal_binding_set_digests": tuple(
                sorted(value.binding_set_digest for value in terminal.terminal_binding_sets)
            ),
            "execution_lineage_digest": (
                terminal.execution_lineage.lineage_digest if terminal.execution_lineage is not None else None
            ),
            "arbitration_policy_bundle_digest": (
                terminal.arbitration_policy_bundle.bundle_digest
                if terminal.arbitration_policy_bundle is not None
                else None
            ),
            "authorization_read_set_digest": (
                terminal.authorization_read_set.read_set_digest if terminal.authorization_read_set is not None else None
            ),
        }
        return cls(**body, closure_digest=contract_digest(b"memorii.semantic-ingestion.artifact-closure.v1", body))


class SemanticGraphDelta(BaseModel):
    kind: Literal["semantic_graph_delta"] = "semantic_graph_delta"
    operation_id: str
    carriers: tuple[SemanticDurableCarrier, ...]
    graph_records: tuple[NonOwningGraphRecord, ...] = ()
    terminal_binding_sets: tuple[SemanticTerminalBindingSet, ...]
    delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_delta(self) -> SemanticGraphDelta:
        body = self.model_dump(mode="python", exclude={"delta_digest"})
        graph_keys = tuple((value.record_kind, value.record_digest) for value in self.graph_records)
        if graph_keys != tuple(sorted(set(graph_keys))):
            raise ValueError("semantic ingestion companion graph records are not canonical")
        if (not self.carriers and not self.graph_records) or self.delta_digest != contract_digest(
            b"memorii.semantic-ingestion.graph-delta.v1", body
        ):
            raise ValueError("semantic ingestion graph delta is incomplete or has an invalid digest")
        return self

    @model_serializer(mode="wrap")
    def serialize_delta(self, handler):
        values = handler(self)
        if not self.graph_records:
            values.pop("graph_records", None)
        return values

    @classmethod
    def create(cls, terminal: SemanticTerminalOutcome) -> SemanticGraphDelta:
        if terminal.status != "accepted":
            raise ValueError("only accepted terminals produce graph deltas")
        body = {
            "kind": "semantic_graph_delta",
            "operation_id": terminal.operation_id,
            "carriers": terminal.accepted_carriers,
            "graph_records": (),
            "terminal_binding_sets": terminal.terminal_binding_sets,
        }
        # The discriminated carrier union serializes to its persisted mapping;
        # derive the digest from that exact model representation.
        persisted_body = cls.model_construct(**body, delta_digest="0" * 64).model_dump(
            mode="python", exclude={"delta_digest"}
        )
        return cls(
            **body,
            delta_digest=contract_digest(b"memorii.semantic-ingestion.graph-delta.v1", persisted_body),
        )


class SemanticEventInputBatch(BaseModel):
    kind: Literal["semantic_event_input_batch"] = "semantic_event_input_batch"
    operation_id: str
    graph_delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    carrier_digests: tuple[str, ...]
    event_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_batch(self) -> SemanticEventInputBatch:
        if self.carrier_digests != tuple(sorted(set(self.carrier_digests))):
            raise ValueError("event carrier digests must be canonical")
        body = self.model_dump(mode="python", exclude={"event_input_digest"})
        if self.event_input_digest != contract_digest(b"memorii.semantic-ingestion.event-input-batch.v1", body):
            raise ValueError("semantic ingestion event input digest mismatch")
        return self

    @classmethod
    def create(cls, *, terminal: SemanticTerminalOutcome, graph_delta: SemanticGraphDelta) -> SemanticEventInputBatch:
        if terminal.status != "accepted" or graph_delta.operation_id != terminal.operation_id:
            raise ValueError("event input requires one accepted terminal graph delta")
        body = {
            "kind": "semantic_event_input_batch",
            "operation_id": terminal.operation_id,
            "graph_delta_digest": graph_delta.delta_digest,
            "terminal_digest": terminal.terminal_digest,
            "carrier_digests": tuple(sorted(value.record_digest for value in terminal.accepted_carriers)),
        }
        return cls(**body, event_input_digest=contract_digest(b"memorii.semantic-ingestion.event-input-batch.v1", body))


class SemanticObservationDelta(BaseModel):
    operation_id: str
    graph_effect: Literal["committed", "none"]
    terminal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_delta_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason_codes: tuple[str, ...]
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_delta(self) -> SemanticObservationDelta:
        if (self.graph_effect == "committed") != (self.graph_delta_digest is not None):
            raise ValueError("observation graph effect and delta must agree")
        body = self.model_dump(mode="python", exclude={"observation_digest"})
        if self.observation_digest != contract_digest(b"memorii.semantic-ingestion.observation-delta.v1", body):
            raise ValueError("semantic ingestion observation digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, terminal: SemanticTerminalOutcome, graph_delta: SemanticGraphDelta | None
    ) -> SemanticObservationDelta:
        if (terminal.status == "accepted") != (graph_delta is not None):
            raise ValueError("accepted status and graph delta must agree")
        body = {
            "operation_id": terminal.operation_id,
            "graph_effect": "committed" if graph_delta is not None else "none",
            "terminal_digest": terminal.terminal_digest,
            "graph_delta_digest": graph_delta.delta_digest if graph_delta is not None else None,
            "reason_codes": terminal.reason_codes,
        }
        return cls(**body, observation_digest=contract_digest(b"memorii.semantic-ingestion.observation-delta.v1", body))


class SemanticEffectGroupResult(BaseModel):
    operation_id: str
    status: Literal["accepted", "unresolved", "rejected", "evidence_only"]
    terminal: SemanticTerminalOutcome
    artifact_closure: SemanticArtifactClosure
    group_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_result(self) -> SemanticEffectGroupResult:
        if self.operation_id != self.terminal.operation_id or self.status != self.terminal.status:
            raise ValueError("group result does not bind its terminal")
        if self.artifact_closure.terminal_digest != self.terminal.terminal_digest:
            raise ValueError("group result artifact closure does not bind its terminal")
        body = self.model_dump(mode="python", exclude={"group_result_digest"})
        if self.group_result_digest != contract_digest(b"memorii.semantic-ingestion.group-result.v1", body):
            raise ValueError("semantic ingestion group result digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, terminal: SemanticTerminalOutcome, artifact_closure: SemanticArtifactClosure
    ) -> SemanticEffectGroupResult:
        body = {
            "operation_id": terminal.operation_id,
            "status": terminal.status,
            "terminal": terminal,
            "artifact_closure": artifact_closure,
        }
        persisted_body = cls.model_construct(**body, group_result_digest="0" * 64).model_dump(
            mode="python", exclude={"group_result_digest"}
        )
        return cls(
            **body,
            group_result_digest=contract_digest(b"memorii.semantic-ingestion.group-result.v1", persisted_body),
        )


class TransactionSemanticGroupPlanReference(BaseModel):
    """Content-addressed pointer to a repository-owned group plan."""

    plan_id: str = Field(min_length=1)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_id: str = Field(min_length=1)
    repository_contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PlanningArtifactReference(BaseModel):
    """Content-addressed pointer to a repository-owned planning artifact."""

    artifact_id: str = Field(min_length=1)
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_id: str = Field(min_length=1)
    repository_contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _canonical_values(values: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(sorted(values, key=lambda value: encode_typed_value(canonical_contract_value(value))))


class SegmentGovernanceBinding(BaseModel):
    """The admission-derived governance values for one source segment."""

    source_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    message_semantic_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_classification: str = Field(min_length=1)
    modality: SourceModality
    provider_egress_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_disposition: Literal["allow_verbatim", "deny"]
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_binding(self) -> SegmentGovernanceBinding:
        if _digest_verification_hit(self, self.binding_digest):
            return self
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != contract_digest(b"memorii.semantic-ingestion.segment-governance-binding.v1", body):
            raise ValueError("segment governance binding digest mismatch")
        _record_digest_verification(self, self.binding_digest)
        return self

    @classmethod
    def create(cls, **values: object) -> SegmentGovernanceBinding:
        return cls(
            **values,
            binding_digest=contract_digest(b"memorii.semantic-ingestion.segment-governance-binding.v1", values),
        )


class SegmentGovernanceCarrierSet(BaseModel):
    source_id: str = Field(min_length=1)
    bindings: tuple[SegmentGovernanceBinding, ...]
    carrier_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_carrier_set(self) -> SegmentGovernanceCarrierSet:
        if not self.bindings or any(binding.source_id != self.source_id for binding in self.bindings):
            raise ValueError("segment governance carrier set must contain source-local bindings")
        if self.bindings != _canonical_values(self.bindings):
            raise ValueError("segment governance bindings must be canonical")
        if len({binding.segment_id for binding in self.bindings}) != len(self.bindings):
            raise ValueError("segment governance bindings must name each segment once")
        if _digest_verification_hit(self, self.carrier_set_digest):
            return self
        body = self.model_dump(mode="python", exclude={"carrier_set_digest"})
        if self.carrier_set_digest != contract_digest(
            b"memorii.semantic-ingestion.segment-governance-carrier-set.v1", body
        ):
            raise ValueError("segment governance carrier set digest mismatch")
        _record_digest_verification(self, self.carrier_set_digest)
        return self

    @classmethod
    def create(cls, *, source_id: str, bindings: tuple[SegmentGovernanceBinding, ...]) -> SegmentGovernanceCarrierSet:
        body = {"source_id": source_id, "bindings": bindings}
        return cls(
            **body,
            carrier_set_digest=contract_digest(b"memorii.semantic-ingestion.segment-governance-carrier-set.v1", body),
        )


class RequiredOutcomeScopeSet(BaseModel):
    tenant_partition_id: str = Field(min_length=1)
    scopes: tuple[MemoryScope, ...]
    canonical_scope_digests: tuple[str, ...]
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_scope_set(self) -> RequiredOutcomeScopeSet:
        expected_scope_digests = tuple(
            contract_digest(b"memorii.semantic-ingestion.required-outcome-scope.v1", scope) for scope in self.scopes
        )
        if (
            not self.scopes
            or self.scopes != _canonical_values(self.scopes)
            or len(set(expected_scope_digests)) != len(expected_scope_digests)
            or self.canonical_scope_digests != expected_scope_digests
        ):
            raise ValueError("required outcome scopes must be canonical and complete")
        body = self.model_dump(mode="python", exclude={"required_scope_set_digest"})
        if self.required_scope_set_digest != contract_digest(
            b"memorii.semantic-ingestion.required-outcome-scope-set.v1", body
        ):
            raise ValueError("required outcome scope set digest mismatch")
        return self

    @classmethod
    def create(cls, *, tenant_partition_id: str, scopes: tuple[MemoryScope, ...]) -> RequiredOutcomeScopeSet:
        canonical_scopes = _canonical_values(scopes)
        body = {
            "tenant_partition_id": tenant_partition_id,
            "scopes": canonical_scopes,
            "canonical_scope_digests": tuple(
                contract_digest(b"memorii.semantic-ingestion.required-outcome-scope.v1", scope)
                for scope in canonical_scopes
            ),
        }
        return cls(
            **body,
            required_scope_set_digest=contract_digest(
                b"memorii.semantic-ingestion.required-outcome-scope-set.v1", body
            ),
        )


class MessageAdmissionIdentity(BaseModel):
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authenticated_source_reference: str = Field(min_length=1)
    authenticated_source_reference_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    message_bytes_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_governance_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    message_admission_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_identity(self) -> MessageAdmissionIdentity:
        if _digest_verification_hit(self, self.message_admission_key_digest):
            return self
        body = self.model_dump(mode="python", exclude={"message_admission_key_digest"})
        if self.message_admission_key_digest != contract_digest(
            b"memorii.semantic-ingestion.message-admission-identity.v1", body
        ):
            raise ValueError("message admission identity digest mismatch")
        _record_digest_verification(self, self.message_admission_key_digest)
        return self

    @classmethod
    def create(cls, **values: object) -> MessageAdmissionIdentity:
        return cls(
            **values,
            message_admission_key_digest=contract_digest(
                b"memorii.semantic-ingestion.message-admission-identity.v1", values
            ),
        )


class MessageAdmissionCarrierSet(BaseModel):
    source_id: str = Field(min_length=1)
    identities: tuple[MessageAdmissionIdentity, ...]
    carrier_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_carrier_set(self) -> MessageAdmissionCarrierSet:
        if self.identities != _canonical_values(self.identities):
            raise ValueError("message admission identities must be canonical")
        if len({identity.segment_governance_binding_digest for identity in self.identities}) != len(self.identities):
            raise ValueError("message admissions must name each governance binding once")
        body = self.model_dump(mode="python", exclude={"carrier_set_digest"})
        if self.carrier_set_digest != contract_digest(
            b"memorii.semantic-ingestion.message-admission-carrier-set.v1", body
        ):
            raise ValueError("message admission carrier set digest mismatch")
        return self

    @classmethod
    def create(cls, *, source_id: str, identities: tuple[MessageAdmissionIdentity, ...]) -> MessageAdmissionCarrierSet:
        body = {"source_id": source_id, "identities": identities}
        return cls(
            **body,
            carrier_set_digest=contract_digest(b"memorii.semantic-ingestion.message-admission-carrier-set.v1", body),
        )


class GovernanceCarrierArtifact(BaseModel):
    artifact_id: str = Field(min_length=1)
    atomic_generation: int = Field(ge=1)
    segment_governance: SegmentGovernanceCarrierSet
    message_admissions: MessageAdmissionCarrierSet
    required_outcome_scopes: RequiredOutcomeScopeSet
    canonical_payload: bytes
    canonical_payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_artifact(self) -> GovernanceCarrierArtifact:
        if self.segment_governance.source_id != self.message_admissions.source_id:
            raise ValueError("governance carrier artifact source mismatch")
        binding_digests = tuple(binding.binding_digest for binding in self.segment_governance.bindings)
        admission_binding_digests = tuple(
            identity.segment_governance_binding_digest for identity in self.message_admissions.identities
        )
        if not set(admission_binding_digests).issubset(binding_digests):
            raise ValueError("governance carrier artifact admission bindings mismatch")
        expected_payload = encode_typed_value(
            canonical_contract_value(
                {
                    "segment_governance": self.segment_governance,
                    "message_admissions": self.message_admissions,
                    "required_outcome_scopes": self.required_outcome_scopes,
                }
            )
        )
        if (
            self.canonical_payload != expected_payload
            or self.canonical_payload_digest != sha256(expected_payload).hexdigest()
        ):
            raise ValueError("governance carrier artifact payload mismatch")
        body = self.model_dump(mode="python", exclude={"artifact_digest"})
        if self.artifact_digest != contract_digest(b"memorii.semantic-ingestion.governance-carrier-artifact.v1", body):
            raise ValueError("governance carrier artifact digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        atomic_generation: int,
        segment_governance: SegmentGovernanceCarrierSet,
        message_admissions: MessageAdmissionCarrierSet,
        required_outcome_scopes: RequiredOutcomeScopeSet,
    ) -> GovernanceCarrierArtifact:
        payload = encode_typed_value(
            canonical_contract_value(
                {
                    "segment_governance": segment_governance,
                    "message_admissions": message_admissions,
                    "required_outcome_scopes": required_outcome_scopes,
                }
            )
        )
        body = {
            "artifact_id": artifact_id,
            "atomic_generation": atomic_generation,
            "segment_governance": segment_governance,
            "message_admissions": message_admissions,
            "required_outcome_scopes": required_outcome_scopes,
            "canonical_payload": payload,
            "canonical_payload_digest": sha256(payload).hexdigest(),
        }
        return cls(
            **body, artifact_digest=contract_digest(b"memorii.semantic-ingestion.governance-carrier-artifact.v1", body)
        )


class LanguageCandidate(BaseModel):
    language: str = Field(min_length=1)
    probability_ppm: int = Field(ge=0, le=1_000_000)
    model_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SegmentLanguageResourceBinding(BaseModel):
    selected_language: str = Field(min_length=1)
    proposal_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    stanza_analyzer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    spacy_analyzer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_resolver_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_binding(self) -> SegmentLanguageResourceBinding:
        body = self.model_dump(mode="python", exclude={"resource_binding_digest"})
        if self.resource_binding_digest != contract_digest(
            b"memorii.semantic-ingestion.segment-language-resource-binding.v1", body
        ):
            raise ValueError("segment language resource binding digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SegmentLanguageResourceBinding:
        return cls(
            **values,
            resource_binding_digest=contract_digest(
                b"memorii.semantic-ingestion.segment-language-resource-binding.v1", values
            ),
        )


class SegmentLanguageRoute(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    parent_projection_segment_id: str = Field(min_length=1)
    segment_text_artifact_id: str = Field(min_length=1)
    segment_text_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_text_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    declared_language: str | None = None
    candidates: tuple[LanguageCandidate, ...]
    code_switch_spans: tuple[SegmentLocalTextSpan, ...]
    selected_language: str | None = None
    decision: Literal["selected", "uncertain", "unsupported", "conflict", "unresolved_code_switch", "missing_resource"]
    minimum_probability_ppm: int = Field(ge=0, le=1_000_000)
    minimum_margin_ppm: int = Field(ge=0, le=1_000_000)
    routing_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    router_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_binding: SegmentLanguageResourceBinding | None = None
    route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_route(self) -> SegmentLanguageRoute:
        def canonical_tag(tag: str) -> str:
            # BCP-47's common language[-Script][-REGION][-variant...] shape is
            # sufficient for the persisted router boundary.  We reject rather
            # than silently case-normalizing received evidence.
            if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", tag):
                raise ValueError("language tag must be canonical BCP-47")
            parts = tag.split("-")
            normalized = [parts[0].lower()]
            for part in parts[1:]:
                normalized.append(
                    part.title()
                    if len(part) == 4 and part.isalpha()
                    else part.upper()
                    if len(part) == 2 and part.isalpha() or len(part) == 3 and part.isdigit()
                    else part.lower()
                )
            return "-".join(normalized)

        candidates = self.candidates
        if any(candidate.language != canonical_tag(candidate.language) for candidate in candidates):
            raise ValueError("segment language candidates must use canonical BCP-47 tags")
        if self.declared_language is not None and self.declared_language != canonical_tag(self.declared_language):
            raise ValueError("declared language must use canonical BCP-47 tag")
        if candidates != tuple(
            sorted(candidates, key=lambda candidate: (-candidate.probability_ppm, candidate.language))
        ) or len({candidate.language for candidate in self.candidates}) != len(self.candidates):
            raise ValueError("segment language candidates must be unique and score ordered")
        if any(
            span.artifact.artifact_id != self.segment_text_artifact_id
            or span.artifact.artifact_digest != self.segment_text_artifact_digest
            or span.artifact.content_digest != self.segment_text_content_digest
            or span.artifact.projection_segment_id != self.parent_projection_segment_id
            for span in self.code_switch_spans
        ):
            raise ValueError("segment language code switch spans must bind exact segment text")
        selected = self.decision == "selected"
        if selected != (self.selected_language is not None and self.resource_binding is not None):
            raise ValueError("segment language route selection and resource binding must agree")
        if (
            selected
            and self.resource_binding is not None
            and self.resource_binding.selected_language != self.selected_language
        ):
            raise ValueError("segment language route resource binding language mismatch")
        if selected:
            assert self.selected_language is not None
            if self.selected_language != canonical_tag(self.selected_language) or not candidates:
                raise ValueError("selected route requires one canonical top candidate")
            top = candidates[0]
            runner_up = candidates[1] if len(candidates) > 1 else None
            if (
                top.language != self.selected_language
                or top.probability_ppm < self.minimum_probability_ppm
                or runner_up is not None
                and top.probability_ppm - runner_up.probability_ppm < self.minimum_margin_ppm
                or self.declared_language is not None
                and self.declared_language != self.selected_language
            ):
                raise ValueError("selected route must be threshold-certified and declaration-consistent")
        elif self.selected_language is not None or self.resource_binding is not None:
            raise ValueError("blocked route cannot retain selected language or resource")
        body = self.model_dump(mode="python", exclude={"route_digest"})
        if self.route_digest != contract_digest(b"memorii.semantic-ingestion.segment-language-route.v1", body):
            raise ValueError("segment language route digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SegmentLanguageRoute:
        return cls(
            **values, route_digest=contract_digest(b"memorii.semantic-ingestion.segment-language-route.v1", values)
        )


class BootstrapDeclaredSegmentLanguageRoute(BaseModel):
    """Closed V1 local-English route; it is intentionally not a classifier route."""

    schema_id: Literal["memorii.semantic_ingestion.bootstrap_declared_segment_language_route"]
    schema_version: Literal[1]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    parent_projection_segment_id: str = Field(min_length=1)
    segment_text_artifact_id: str = Field(min_length=1)
    segment_text_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_text_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    declared_language: Literal["en"]
    language_evidence_kind: Literal["authenticated_host_declaration"]
    language_evidence_trust: Literal["trusted"]
    governance_agreement: Literal["agrees"]
    bootstrap_language_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_profile_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    component_root_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_case_id: str = Field(min_length=1)
    normalized_segment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    grammar_proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["selected"]
    route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_route(self) -> BootstrapDeclaredSegmentLanguageRoute:
        body = self.model_dump(mode="python", exclude={"route_digest"})
        if self.route_digest != contract_digest(
            b"memorii.semantic_ingestion.bootstrap_declared_segment_language_route.v1", body
        ):
            raise ValueError("bootstrap declared segment language route digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapDeclaredSegmentLanguageRoute:
        return cls(
            **values,
            route_digest=contract_digest(
                b"memorii.semantic_ingestion.bootstrap_declared_segment_language_route.v1", values
            ),
        )


LanguageRoute = SegmentLanguageRoute | BootstrapDeclaredSegmentLanguageRoute


class SegmentLanguageRouteSet(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    routes: tuple[LanguageRoute, ...]
    route_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_routes(self) -> SegmentLanguageRouteSet:
        if not self.routes or any(
            route.source_id != self.source_id or route.source_digest != self.source_digest for route in self.routes
        ):
            raise ValueError("segment language routes must belong to source")
        if len({route.segment_id for route in self.routes}) != len(self.routes):
            raise ValueError("segment language route execution children must be unique")
        body = self.model_dump(mode="python", exclude={"route_set_digest"})
        if self.route_set_digest != contract_digest(b"memorii.semantic-ingestion.segment-language-route-set.v1", body):
            raise ValueError("segment language route set digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SegmentLanguageRouteSet:
        return cls(
            **values,
            route_set_digest=contract_digest(b"memorii.semantic-ingestion.segment-language-route-set.v1", values),
        )


class SourcePrePartitionMention(BaseModel):
    """A route-bound source mention before identity partitioning."""

    schema_version: Literal[2]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    mention_span: SourceSpanReference
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @classmethod
    def create(cls, **values: object):
        return cls(
            **values,
            schema_version=2,
            mention_digest=contract_digest(
                b"memorii.semantic-ingestion.source-pre-partition-mention.v2", {"schema_version": 2, **values}
            ),
        )


class SourceLocalIdentityAssertion(BaseModel):
    schema_version: Literal[2]
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    mention_digests: tuple[str, ...]
    proof_kind: Literal[
        "explicit_alias",
        "explicit_apposition",
        "authenticated_external_id",
        "certified_unambiguous_repetition",
        "insufficient_evidence",
        "conflicting_evidence",
    ]
    source_evidence: tuple[SourceSpanReference, ...]
    assertion_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_assertion(self):
        if self.mention_digests != tuple(sorted(set(self.mention_digests))) or not self.mention_digests:
            raise ValueError("identity assertion mentions must be nonempty, unique, and canonical")
        affirmative = self.proof_kind not in {"insufficient_evidence", "conflicting_evidence"}
        if (affirmative and len(self.mention_digests) < 2) or not self.source_evidence:
            raise ValueError("identity assertion proof closure is invalid")
        if self.source_evidence != tuple(sorted(self.source_evidence, key=lambda span: span.reference_digest)):
            raise ValueError("identity assertion evidence must be canonical")
        return self

    @classmethod
    def create(cls, **values: object):
        return cls(
            **values,
            schema_version=2,
            assertion_digest=contract_digest(
                b"memorii.semantic-ingestion.source-local-identity-assertion.v2", {"schema_version": 2, **values}
            ),
        )


class SourceLocalIdentityPartitionEvidence(BaseModel):
    schema_version: Literal[2]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mentions: tuple[SourcePrePartitionMention, ...]
    assertions: tuple[SourceLocalIdentityAssertion, ...]
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_evidence(self):
        if not self.mentions or self.mentions != tuple(sorted(self.mentions, key=lambda item: item.mention_digest)):
            raise ValueError("identity evidence mentions must be nonempty and canonical")
        ids = {item.mention_digest for item in self.mentions}
        if len(ids) != len(self.mentions) or any(
            item.source_id != self.source_id or item.source_digest != self.source_digest for item in self.mentions
        ):
            raise ValueError("identity evidence mentions must bind one source")
        if self.assertions != tuple(sorted(self.assertions, key=lambda item: item.assertion_digest)) or any(
            set(item.mention_digests) - ids for item in self.assertions
        ):
            raise ValueError("identity assertions must be canonical and refer to known mentions")
        return self

    @classmethod
    def create(cls, **values: object):
        return cls(
            **values,
            schema_version=2,
            evidence_digest=contract_digest(
                b"memorii.semantic-ingestion.source-local-identity-partition-evidence.v2",
                {"schema_version": 2, **values},
            ),
        )


class SourceLocalIdentityClusterDecision(BaseModel):
    schema_version: Literal[2]
    cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["same_source_entity", "singleton_distinct", "unresolved"]
    proof_kind: Literal[
        "explicit_alias",
        "explicit_apposition",
        "authenticated_external_id",
        "certified_unambiguous_repetition",
        "insufficient_evidence",
        "conflicting_evidence",
    ]
    mention_digests: tuple[str, ...]
    source_evidence: tuple[SourceSpanReference, ...]
    segment_route_policy_closure: tuple[tuple[str, str, str], ...]
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_cluster(self) -> SourceLocalEntityClusterDecision:
        if not self.mention_digests or self.mention_digests != tuple(sorted(set(self.mention_digests))):
            raise ValueError("source local identity cluster mentions must be nonempty and canonical")
        if self.decision == "unresolved" and self.proof_kind not in {"insufficient_evidence", "conflicting_evidence"}:
            raise ValueError("unresolved source local identity cluster requires unresolved proof")
        if self.decision != "unresolved" and self.proof_kind in {"insufficient_evidence", "conflicting_evidence"}:
            raise ValueError("resolved source local identity cluster requires affirmative proof")
        return self

    @classmethod
    def create(cls, **values: object):
        return cls(
            **values,
            schema_version=2,
            decision_digest=contract_digest(
                b"memorii.semantic-ingestion.source-local-identity-cluster-decision.v2", {"schema_version": 2, **values}
            ),
        )


SourceLocalEntityClusterDecision = SourceLocalIdentityClusterDecision


class SourceLocalIdentityResolution(BaseModel):
    schema_version: Literal[2]
    source_id: str = Field(min_length=1)
    grounded_mention_refs: tuple[str, ...]
    clusters: tuple[SourceLocalIdentityClusterDecision, ...]
    unresolved_mention_refs: tuple[str, ...]
    resolution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_resolution(self) -> SourceLocalIdentityResolution:
        mentions = self.grounded_mention_refs
        if mentions != tuple(sorted(set(mentions))) or not mentions:
            raise ValueError("source local identity mentions must be source-local and canonical")
        if self.clusters != tuple(sorted(self.clusters, key=lambda cluster: cluster.cluster_id)) or len(
            {cluster.cluster_id for cluster in self.clusters}
        ) != len(self.clusters):
            raise ValueError("source local identity clusters must be canonical")
        clustered = tuple(mention for cluster in self.clusters for mention in cluster.mention_digests)
        if set(clustered) != set(mentions) or len(clustered) != len(set(clustered)):
            raise ValueError("source local identity clusters must be a total partition")
        unresolved = tuple(
            mention
            for cluster in self.clusters
            if cluster.decision == "unresolved"
            for mention in cluster.mention_digests
        )
        if self.unresolved_mention_refs != tuple(sorted(unresolved)):
            raise ValueError("source local identity unresolved mentions must equal unresolved clusters")
        body = self.model_dump(mode="python", exclude={"resolution_digest"})
        if self.resolution_digest != contract_digest(
            b"memorii.semantic-ingestion.source-local-identity-resolution.v2", body
        ):
            raise ValueError("source local identity resolution digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SourceLocalIdentityResolution:
        values = {"schema_version": 2, **values}
        return cls(
            **values,
            resolution_digest=contract_digest(
                b"memorii.semantic-ingestion.source-local-identity-resolution.v2", values
            ),
        )










class OperationAlignment(BaseModel):
    schema_version: Literal[2]
    operation_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_attachment_consensus_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_alignment(self) -> OperationAlignment:
        body = self.model_dump(mode="python", exclude={"alignment_digest"})
        if self.alignment_digest != contract_digest(b"memorii.semantic-ingestion.operation-alignment.v2", body):
            raise ValueError("operation alignment digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> OperationAlignment:
        values = {"schema_version": 2, **values}
        return cls(
            **values, alignment_digest=contract_digest(b"memorii.semantic-ingestion.operation-alignment.v2", values)
        )


class SourceDependencyGroup(BaseModel):
    schema_version: Literal[2]
    group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_ids: tuple[str, ...]
    segment_ids: tuple[str, ...]
    kind: Literal["independent_fact", "correction", "retraction", "identity", "action_state"]
    source_dependency_kinds: tuple[str, ...]
    atomic: Literal[True]
    status: Literal["complete", "unresolved", "failed"]
    reason_codes: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_group(self) -> SourceDependencyGroup:
        for values, label in (
            (self.operation_ids, "operation ids"),
            (self.segment_ids, "segment ids"),
            (self.source_dependency_kinds, "source dependency kinds"),
            (self.reason_codes, "reason codes"),
        ):
            if values != tuple(sorted(set(values))) or any(not value for value in values):
                raise ValueError(f"source dependency group {label} must be canonical")
        if not self.operation_ids or not self.segment_ids:
            raise ValueError("source dependency group membership must be nonempty")
        if self.status == "complete" and self.reason_codes:
            raise ValueError("complete source dependency groups cannot have reason codes")
        if self.status != "complete" and not self.reason_codes:
            raise ValueError("non-complete source dependency groups require reason codes")
        body = self.model_dump(mode="python", exclude={"group_id"})
        if self.group_id != contract_digest(b"memorii.semantic-ingestion.source-dependency-group.v2", body):
            raise ValueError("source dependency group id mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SourceDependencyGroup:
        values = {"schema_version": 2, **values}
        return cls(**values, group_id=contract_digest(b"memorii.semantic-ingestion.source-dependency-group.v2", values))




class OperationCarrierMembership(BaseModel):
    """The admitted carriers consumed by one operation in a transaction group."""

    operation_id: str = Field(min_length=1)
    segment_governance_binding_digests: tuple[str, ...]
    message_admission_key_digests: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_membership(self) -> OperationCarrierMembership:
        for values, label in (
            (self.segment_governance_binding_digests, "governance binding digests"),
            (self.message_admission_key_digests, "message admission key digests"),
        ):
            if not values or values != tuple(sorted(set(values))):
                raise ValueError(f"operation carrier membership {label} must be nonempty and canonical")
        return self


class TransactionSemanticGroup(BaseModel):
    transaction_group_id: str = Field(min_length=1)
    source_dependency_group_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    segment_governance_bindings: tuple[SegmentGovernanceBinding, ...]
    message_admission_identities: tuple[MessageAdmissionIdentity, ...]
    operation_carrier_memberships: tuple[OperationCarrierMembership, ...]
    governance_carrier_artifact: GovernanceCarrierArtifact
    member_decisions: tuple[tuple[str, Literal["accepted", "rejected", "unresolved"]], ...]
    graph_dependency_record_keys: tuple[str, ...]
    dependency_kinds: tuple[str, ...]
    atomic: Literal[True]
    status: Literal["commit_eligible", "rejected", "unresolved"]
    group_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_group(self) -> TransactionSemanticGroup:
        for values, label, required in (
            (self.source_dependency_group_ids, "source group ids", True),
            (self.operation_ids, "operation ids", True),
            (self.graph_dependency_record_keys, "graph dependency record keys", False),
            (self.dependency_kinds, "dependency kinds", False),
        ):
            if (required and not values) or values != tuple(sorted(set(values))):
                raise ValueError(f"transaction semantic group {label} must be canonical")
            if any(not value for value in values):
                raise ValueError(f"transaction semantic group {label} cannot contain empty values")
        if self.segment_governance_bindings != _canonical_values(self.segment_governance_bindings):
            raise ValueError("transaction semantic group governance bindings must be canonical")
        if self.message_admission_identities != _canonical_values(self.message_admission_identities):
            raise ValueError("transaction semantic group message admissions must be canonical")
        if (
            self.operation_carrier_memberships != _canonical_values(self.operation_carrier_memberships)
            or tuple(membership.operation_id for membership in self.operation_carrier_memberships) != self.operation_ids
        ):
            raise ValueError("transaction semantic group operation carrier memberships must exactly cover operations")
        if tuple(operation_id for operation_id, _ in self.member_decisions) != self.operation_ids:
            raise ValueError("transaction semantic group member decisions must exactly cover operations")
        decisions = tuple(decision for _, decision in self.member_decisions)
        expected_status = (
            "unresolved" if "unresolved" in decisions else "rejected" if "rejected" in decisions else "commit_eligible"
        )
        if self.status != expected_status:
            raise ValueError("transaction semantic group status does not match member decisions")
        artifact_bindings = {
            binding.binding_digest for binding in self.governance_carrier_artifact.segment_governance.bindings
        }
        artifact_admissions = {
            identity.message_admission_key_digest
            for identity in self.governance_carrier_artifact.message_admissions.identities
        }
        group_binding_digests = tuple(binding.binding_digest for binding in self.segment_governance_bindings)
        group_admission_digests = tuple(
            identity.message_admission_key_digest for identity in self.message_admission_identities
        )
        if not set(group_binding_digests).issubset(artifact_bindings) or not set(group_admission_digests).issubset(
            artifact_admissions
        ):
            raise ValueError("transaction semantic group carriers must belong to its artifact")
        membership_bindings = tuple(
            digest
            for membership in self.operation_carrier_memberships
            for digest in membership.segment_governance_binding_digests
        )
        membership_admissions = tuple(
            digest
            for membership in self.operation_carrier_memberships
            for digest in membership.message_admission_key_digests
        )
        if (
            tuple(sorted(set(membership_bindings))) != group_binding_digests
            or tuple(sorted(set(membership_admissions))) != group_admission_digests
        ):
            raise ValueError("transaction semantic group carriers must equal the operation-derived union")
        body = self.model_dump(mode="python", exclude={"group_digest"})
        if self.group_digest != contract_digest(b"memorii.semantic-ingestion.transaction-semantic-group.v1", body):
            raise ValueError("transaction semantic group digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> TransactionSemanticGroup:
        return cls(
            **values, group_digest=contract_digest(b"memorii.semantic-ingestion.transaction-semantic-group.v1", values)
        )


class PlannedTransactionGroupExecution(BaseModel):
    transaction_group_id: str = Field(min_length=1)
    planning_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prefix_state_digest_before: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_artifact: PlanningArtifactReference
    semantic_effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prefix_state_digest_after: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_execution(self) -> PlannedTransactionGroupExecution:
        body = self.model_dump(mode="python", exclude={"execution_digest"})
        if self.execution_digest != contract_digest(
            b"memorii.semantic-ingestion.planned-transaction-group-execution.v1", body
        ):
            raise ValueError("planned transaction group execution digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> PlannedTransactionGroupExecution:
        return cls(
            **values,
            execution_digest=contract_digest(
                b"memorii.semantic-ingestion.planned-transaction-group-execution.v1", values
            ),
        )


class GroupIndependenceCertificate(BaseModel):
    transaction_group_id: str = Field(min_length=1)
    preceding_group_ids: tuple[str, ...]
    preceding_execution_digests: tuple[str, ...]
    baseline_artifact: PlanningArtifactReference
    after_prefix_artifact: PlanningArtifactReference
    prefix_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    certificate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_certificate(self) -> GroupIndependenceCertificate:
        for values, label in (
            (self.preceding_group_ids, "preceding group ids"),
            (self.preceding_execution_digests, "preceding execution digests"),
        ):
            if values != tuple(sorted(set(values))) or any(not value for value in values):
                raise ValueError(f"group independence certificate {label} must be canonical")
        if len(self.preceding_group_ids) != len(self.preceding_execution_digests):
            raise ValueError("group independence certificate preceding groups and executions must pair")
        body = self.model_dump(mode="python", exclude={"certificate_digest"})
        if self.certificate_digest != contract_digest(
            b"memorii.semantic-ingestion.group-independence-certificate.v1", body
        ):
            raise ValueError("group independence certificate digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> GroupIndependenceCertificate:
        return cls(
            **values,
            certificate_digest=contract_digest(b"memorii.semantic-ingestion.group-independence-certificate.v1", values),
        )


class TransactionSemanticGroupPlan(BaseModel):
    plan_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    snapshot_token: str = Field(min_length=1)
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    groups: tuple[TransactionSemanticGroup, ...]
    planned_executions: tuple[PlannedTransactionGroupExecution, ...]
    independence_certificates: tuple[GroupIndependenceCertificate, ...]
    effective_read_set: GraphReadSet
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_plan(self) -> TransactionSemanticGroupPlan:
        if (
            self.segment_governance_carriers.source_id != self.source_id
            or self.message_admission_carriers.source_id != self.source_id
        ):
            raise ValueError("transaction group plan carrier source mismatch")
        artifact = self.governance_carrier_artifact
        if (
            artifact.segment_governance != self.segment_governance_carriers
            or artifact.message_admissions != self.message_admission_carriers
        ):
            raise ValueError("transaction group plan carriers must equal its governance artifact")
        if not self.groups or self.groups != _canonical_values(self.groups):
            raise ValueError("transaction group plan groups must be nonempty and canonical")
        group_ids = tuple(group.transaction_group_id for group in self.groups)
        execution_ids = tuple(execution.transaction_group_id for execution in self.planned_executions)
        certificate_ids = tuple(certificate.transaction_group_id for certificate in self.independence_certificates)
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("transaction group plan group ids must be unique")
        if execution_ids != group_ids or len(set(execution_ids)) != len(execution_ids):
            raise ValueError("transaction group plan executions must exactly cover groups")
        if self.independence_certificates != _canonical_values(self.independence_certificates):
            raise ValueError("transaction group plan independence certificates must be canonical")
        if certificate_ids != group_ids or len(set(certificate_ids)) != len(certificate_ids):
            raise ValueError("transaction group plan certificates must exactly cover groups")
        body = self.model_dump(mode="python", exclude={"plan_digest"})
        if self.plan_digest != contract_digest(b"memorii.semantic-ingestion.transaction-semantic-group-plan.v1", body):
            raise ValueError("transaction semantic group plan digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> TransactionSemanticGroupPlan:
        return cls(
            **values,
            plan_digest=contract_digest(b"memorii.semantic-ingestion.transaction-semantic-group-plan.v1", values),
        )


class GroupPlanningAuthorization(BaseModel):
    """The immutable planning authority for one transaction group."""

    transaction_group_id: str = Field(min_length=1)
    group_plan: TransactionSemanticGroupPlanReference
    planned_execution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_artifact: PlanningArtifactReference
    independence_certificate_digests: tuple[str, ...]
    authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_authorization(self) -> GroupPlanningAuthorization:
        if self.independence_certificate_digests != tuple(sorted(set(self.independence_certificate_digests))) or any(
            len(value) != 64 for value in self.independence_certificate_digests
        ):
            raise ValueError("planning authorization certificate digests must be canonical")
        body = self.model_dump(mode="python", exclude={"authorization_digest"})
        if self.authorization_digest != contract_digest(
            b"memorii.semantic-ingestion.group-planning-authorization.v1", body
        ):
            raise ValueError("group planning authorization digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        transaction_group_id: str,
        group_plan: TransactionSemanticGroupPlanReference,
        planned_execution_digest: str,
        planning_artifact: PlanningArtifactReference,
        independence_certificate_digests: tuple[str, ...],
    ) -> GroupPlanningAuthorization:
        body = {
            "transaction_group_id": transaction_group_id,
            "group_plan": group_plan,
            "planned_execution_digest": planned_execution_digest,
            "planning_artifact": planning_artifact,
            "independence_certificate_digests": independence_certificate_digests,
        }
        return cls(
            **body,
            authorization_digest=contract_digest(b"memorii.semantic-ingestion.group-planning-authorization.v1", body),
        )


IngestionStage = Literal[
    "source_ingestion",
    "source_governance",
    "text_preparation",
    "language_routing",
    "provider_egress_authorization",
    "llm_proposal",
    "proposal_validation",
    "proposal_run_sealing",
    "primary_linguistic_analysis",
    "corroborating_linguistic_analysis",
    "linguistic_consensus",
    "semantic_scope_consensus",
    "temporal_attachment_consensus",
    "predicate_event_detection",
    "temporal_resolution",
    "source_proposal_alignment",
    "proposal_coverage",
    "semantic_scope",
    "source_local_identity",
    "capability_selection",
    "canonical_identity_resolution",
    "planned_identity_reservation",
    "graph_proposal_alignment",
    "capability_status_binding_validation",
    "type_evidence_resolution",
    "claim_slot_construction",
    "nli_corroboration",
    "semantic_reconciliation",
    "transaction_group_expansion",
    "graph_compilation",
    "temporal_projection",
    "trust_arbitration",
    "reference_closure",
    "identity_lineage",
    "source_trace_persistence",
    "transaction_group_persistence",
    "source_summary_persistence",
]
IngestionStageScope = Literal[
    "source", "segment", "source_plan_attempt", "transaction_group_attempt", "transaction_group"
]


class IngestionStageDependencySpec(BaseModel):
    stage: IngestionStage
    mode: Literal["required", "capability_conditional", "diagnostic"]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class IngestionStageSpec(BaseModel):
    stage: IngestionStage
    allowed_scopes: frozenset[IngestionStageScope]
    dependencies: tuple[IngestionStageDependencySpec, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_spec(self) -> IngestionStageSpec:
        if not self.allowed_scopes:
            raise ValueError("ingestion stage must have a permitted scope")
        if self.dependencies != _canonical_values(self.dependencies):
            raise ValueError("ingestion stage dependencies must be canonical")
        if len({dependency.stage for dependency in self.dependencies}) != len(self.dependencies):
            raise ValueError("ingestion stage dependencies must be unique")
        if self.stage in {dependency.stage for dependency in self.dependencies}:
            raise ValueError("ingestion stage cannot depend on itself")
        return self


_INGESTION_STAGE_TEMPLATE: tuple[
    tuple[IngestionStage, IngestionStageScope, tuple[tuple[IngestionStage, str], ...]], ...
] = (
    ("source_ingestion", "source", ()),
    ("source_governance", "source", (("source_ingestion", "required"),)),
    ("text_preparation", "source", (("source_governance", "required"),)),
    ("language_routing", "segment", (("text_preparation", "required"),)),
    ("provider_egress_authorization", "segment", (("source_governance", "required"),)),
    ("llm_proposal", "segment", (("language_routing", "required"), ("provider_egress_authorization", "required"))),
    ("proposal_validation", "segment", (("llm_proposal", "required"),)),
    ("proposal_run_sealing", "source", (("proposal_validation", "required"),)),
    ("primary_linguistic_analysis", "segment", (("language_routing", "required"),)),
    ("corroborating_linguistic_analysis", "segment", (("language_routing", "required"),)),
    (
        "linguistic_consensus",
        "segment",
        (("primary_linguistic_analysis", "required"), ("corroborating_linguistic_analysis", "required")),
    ),
    ("semantic_scope_consensus", "segment", (("linguistic_consensus", "required"),)),
    ("temporal_attachment_consensus", "segment", (("linguistic_consensus", "required"),)),
    ("predicate_event_detection", "segment", (("language_routing", "required"),)),
    ("temporal_resolution", "segment", (("language_routing", "required"),)),
    (
        "source_proposal_alignment",
        "source",
        (
            ("proposal_run_sealing", "required"),
            ("linguistic_consensus", "required"),
            ("predicate_event_detection", "required"),
            ("temporal_resolution", "required"),
        ),
    ),
    ("proposal_coverage", "source", (("source_proposal_alignment", "required"),)),
    ("semantic_scope", "segment", (("semantic_scope_consensus", "required"),)),
    ("source_local_identity", "source", (("source_proposal_alignment", "required"),)),
    ("capability_selection", "source_plan_attempt", (("source_proposal_alignment", "required"),)),
    ("nli_corroboration", "source_plan_attempt", (("capability_selection", "capability_conditional"),)),
    (
        "graph_proposal_alignment",
        "source_plan_attempt",
        (("source_proposal_alignment", "required"), ("capability_selection", "required")),
    ),
    ("canonical_identity_resolution", "source_plan_attempt", (("graph_proposal_alignment", "required"),)),
    ("planned_identity_reservation", "source_plan_attempt", (("canonical_identity_resolution", "required"),)),
    ("capability_status_binding_validation", "source_plan_attempt", (("capability_selection", "required"),)),
    ("type_evidence_resolution", "source_plan_attempt", (("canonical_identity_resolution", "required"),)),
    ("claim_slot_construction", "source_plan_attempt", (("type_evidence_resolution", "required"),)),
    (
        "semantic_reconciliation",
        "source_plan_attempt",
        (("claim_slot_construction", "required"), ("nli_corroboration", "capability_conditional")),
    ),
    (
        "reference_closure",
        "source_plan_attempt",
        (("semantic_reconciliation", "required"), ("planned_identity_reservation", "required")),
    ),
    ("transaction_group_expansion", "source_plan_attempt", (("reference_closure", "required"),)),
    ("graph_compilation", "transaction_group", (("transaction_group_expansion", "required"),)),
    ("temporal_projection", "transaction_group", (("graph_compilation", "required"),)),
    ("trust_arbitration", "transaction_group", (("temporal_projection", "required"),)),
    ("identity_lineage", "transaction_group", (("trust_arbitration", "required"),)),
    ("transaction_group_persistence", "transaction_group", (("identity_lineage", "required"),)),
    ("source_trace_persistence", "source", (("source_proposal_alignment", "diagnostic"),)),
    ("source_summary_persistence", "source", (("transaction_group_persistence", "required"),)),
)


_ATTEMPT_SHARED_STAGES: frozenset[IngestionStage] = frozenset(
    {
        "graph_proposal_alignment",
        "canonical_identity_resolution",
        "planned_identity_reservation",
        "capability_status_binding_validation",
        "type_evidence_resolution",
        "claim_slot_construction",
        "semantic_reconciliation",
        "reference_closure",
    }
)


def _ingestion_stage_specs() -> tuple[IngestionStageSpec, ...]:
    return tuple(
        IngestionStageSpec(
            stage=stage,
            allowed_scopes=frozenset((scope, "transaction_group_attempt"))
            if stage in _ATTEMPT_SHARED_STAGES
            else frozenset((scope,)),
            dependencies=_canonical_values(
                tuple(IngestionStageDependencySpec(stage=dependency, mode=mode) for dependency, mode in dependencies)
            ),
        )
        for stage, scope, dependencies in _INGESTION_STAGE_TEMPLATE
    )


class IngestionExecutionGraph(BaseModel):
    stages: tuple[IngestionStageSpec, ...]
    topological_order: tuple[IngestionStage, ...]
    graph_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_graph(self) -> IngestionExecutionGraph:
        expected = _ingestion_stage_specs()
        if self.stages != expected or self.topological_order != tuple(stage.stage for stage in expected):
            raise ValueError("ingestion execution graph must equal the canonical stage template")
        body = self.model_dump(mode="python", exclude={"graph_fingerprint"})
        if self.graph_fingerprint != contract_digest(b"memorii.semantic-ingestion.execution-graph.v1", body):
            raise ValueError("ingestion execution graph fingerprint mismatch")
        return self

    @classmethod
    def create(cls) -> IngestionExecutionGraph:
        stages = _ingestion_stage_specs()
        body = {"stages": stages, "topological_order": tuple(stage.stage for stage in stages)}
        return cls(**body, graph_fingerprint=contract_digest(b"memorii.semantic-ingestion.execution-graph.v1", body))


CANONICAL_INGESTION_EXECUTION_GRAPH = IngestionExecutionGraph.create()


class IngestionStageInstanceRef(BaseModel):
    stage: IngestionStage
    scope: IngestionStageScope
    segment_id: str | None = Field(default=None, min_length=1)
    segment_language_route_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str | None = Field(default=None, min_length=1)
    attempt_id: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_coordinates(self) -> IngestionStageInstanceRef:
        expected_scope = next(
            spec.allowed_scopes for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages if spec.stage == self.stage
        )
        if self.scope not in expected_scope:
            raise ValueError("ingestion stage instance uses an invalid scope")
        values = (self.segment_id, self.segment_language_route_digest, self.transaction_group_id, self.attempt_id)
        required = {
            "source": (False, False, False, False),
            "segment": (True, True, False, False),
            "source_plan_attempt": (False, False, False, True),
            "transaction_group_attempt": (False, False, True, True),
            "transaction_group": (False, False, True, False),
        }[self.scope]
        if any((value is not None) != required_value for value, required_value in zip(values, required, strict=True)):
            raise ValueError("ingestion stage instance scope coordinates are invalid")
        return self


class IngestionStageOutcome(BaseModel):
    instance: IngestionStageInstanceRef
    status: Literal["not_started", "complete", "committed", "evidence_only", "rejected", "unresolved", "failed"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    blocking_stages: tuple[IngestionStageInstanceRef, ...] = ()
    reason_codes: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_outcome(self) -> IngestionStageOutcome:
        if self.blocking_stages != _canonical_values(self.blocking_stages) or len(set(self.blocking_stages)) != len(
            self.blocking_stages
        ):
            raise ValueError("stage outcome blockers must be canonical and unique")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))) or any(not code for code in self.reason_codes):
            raise ValueError("stage outcome reason codes must be canonical and nonempty")
        if self.status == "not_started":
            if (
                self.started_at is not None
                or self.completed_at is not None
                or self.artifact_digest is not None
                or self.reason_codes
            ):
                raise ValueError("not-started stage outcomes cannot have completion data")
        else:
            if (
                self.started_at is None
                or self.completed_at is None
                or self.started_at > self.completed_at
                or self.blocking_stages
            ):
                raise ValueError("terminal stage outcome times and blockers are invalid")
            if self.status in {"rejected", "unresolved", "failed"} and not self.reason_codes:
                raise ValueError("non-success stage outcome requires reason codes")
        return self


class OperationCapabilityExecutionBinding(BaseModel):
    """One sealed, graph-payload-free capability projection for an operation."""

    operation_id: str = Field(min_length=1)
    source_dependency_group_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_registry_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_status_revision: str = Field(min_length=1)
    capability_status_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    monitoring_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_freshness_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nli_mode: Literal["required", "optional", "shadow", "disabled"]
    verifier_manifest_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    temporal_policy_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_policy_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    arbitration_as_of: datetime
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_binding(self) -> OperationCapabilityExecutionBinding:
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != contract_digest(
            b"memorii.semantic-ingestion.operation-capability-execution-binding.v1", body
        ):
            raise ValueError("operation capability execution binding digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> OperationCapabilityExecutionBinding:
        return cls(
            **values,
            binding_digest=contract_digest(
                b"memorii.semantic-ingestion.operation-capability-execution-binding.v1", values
            ),
        )


class GraphDependentValidationAttempt(BaseModel):
    attempt_id: str = Field(min_length=1)
    scope: Literal["source_plan_attempt", "transaction_group_attempt"]
    trigger: Literal["initial_plan", "prior_group_commit", "related_version_conflict"]
    transaction_group_id: str | None = Field(default=None, min_length=1)
    segment_governance_bindings: tuple[SegmentGovernanceBinding, ...]
    message_admission_identities: tuple[MessageAdmissionIdentity, ...]
    governance_carrier_artifact: GovernanceCarrierArtifact
    attempt_index: int = Field(ge=1)
    operation_lease_binding: OperationLeaseBinding
    supersedes_attempt_id: str | None = Field(default=None, min_length=1)
    base_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_snapshot_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_proposal_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planned_identity_reservation_digests: tuple[str, ...]
    planned_action_reservation_digests: tuple[str, ...]
    reservation_use_authorization_digests: tuple[str, ...]
    capability_selection_digests: tuple[str, ...]
    capability_binding_digests: tuple[str, ...]
    canonical_entity_decision_digests: tuple[str, ...]
    reconciliation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_plan: TransactionSemanticGroupPlanReference
    planning_authorizations: tuple[GroupPlanningAuthorization, ...]
    stage_outcomes: tuple[IngestionStageOutcome, ...]
    status: Literal["eligible", "superseded", "rejected", "unresolved", "failed"]
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_attempt(self) -> GraphDependentValidationAttempt:
        is_initial = self.scope == "source_plan_attempt"
        if is_initial != (self.transaction_group_id is None) or (self.trigger == "initial_plan") != is_initial:
            raise ValueError("graph validation attempt scope, group, and trigger must agree")
        if is_initial != (self.attempt_index == 1 and self.supersedes_attempt_id is None):
            raise ValueError("initial graph validation attempt ancestry is invalid")
        if not is_initial and self.supersedes_attempt_id is None:
            raise ValueError("transaction-group graph validation attempt must supersede an attempt")
        if self.segment_governance_bindings != _canonical_values(
            self.segment_governance_bindings
        ) or self.message_admission_identities != _canonical_values(self.message_admission_identities):
            raise ValueError("graph validation attempt carrier bindings must be canonical")
        if tuple(binding.binding_digest for binding in self.segment_governance_bindings) != tuple(
            binding.binding_digest for binding in self.governance_carrier_artifact.segment_governance.bindings
        ):
            raise ValueError("graph validation attempt governance bindings must equal governance artifact")
        if tuple(identity.message_admission_key_digest for identity in self.message_admission_identities) != tuple(
            identity.message_admission_key_digest
            for identity in self.governance_carrier_artifact.message_admissions.identities
        ):
            raise ValueError("graph validation attempt admission identities must equal governance artifact")
        for values in (
            self.planned_identity_reservation_digests,
            self.planned_action_reservation_digests,
            self.reservation_use_authorization_digests,
            self.capability_selection_digests,
            self.capability_binding_digests,
            self.canonical_entity_decision_digests,
        ):
            if values != tuple(sorted(set(values))) or any(len(value) != 64 for value in values):
                raise ValueError("graph validation attempt digest tuples must be canonical")
        authorizations = self.planning_authorizations
        if (
            not authorizations
            or authorizations != _canonical_values(authorizations)
            or len({item.transaction_group_id for item in authorizations}) != len(authorizations)
        ):
            raise ValueError("graph validation attempt planning authorizations must be complete and canonical")
        if any(item.group_plan != self.transaction_group_plan for item in authorizations):
            raise ValueError("graph validation attempt authorization plan mismatch")
        if not is_initial and tuple(item.transaction_group_id for item in authorizations) != (
            self.transaction_group_id,
        ):
            raise ValueError("transaction-group attempt must carry exactly its group authorization")
        expected_scopes = {"source_plan_attempt"} if is_initial else {"transaction_group_attempt"}
        if not self.stage_outcomes or any(
            outcome.instance.scope not in expected_scopes
            or outcome.instance.attempt_id != self.attempt_id
            or outcome.instance.transaction_group_id != self.transaction_group_id
            for outcome in self.stage_outcomes
        ):
            raise ValueError("graph validation attempt stage outcomes have invalid scope coordinates")
        if self.stage_outcomes != _canonical_values(self.stage_outcomes) or len(
            {outcome.instance for outcome in self.stage_outcomes}
        ) != len(self.stage_outcomes):
            raise ValueError("graph validation attempt stage outcomes must be canonical and unique")
        expected_stages = {
            spec.stage for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages if self.scope in spec.allowed_scopes
        }
        if {outcome.instance.stage for outcome in self.stage_outcomes} != expected_stages:
            raise ValueError("graph validation attempt must retain every applicable stage outcome")
        body = self.model_dump(mode="python", exclude={"attempt_digest"})
        if self.attempt_digest != contract_digest(
            b"memorii.semantic-ingestion.graph-dependent-validation-attempt.v1", body
        ):
            raise ValueError("graph validation attempt digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> GraphDependentValidationAttempt:
        return cls(
            **values,
            attempt_digest=contract_digest(b"memorii.semantic-ingestion.graph-dependent-validation-attempt.v1", values),
        )


class TransactionGroupPlanLineageEntry(BaseModel):
    """One append-only plan/attempt binding for a transaction group."""

    transaction_group_id: str = Field(min_length=1)
    operation_ids: tuple[str, ...]
    attempt_id: str = Field(min_length=1)
    authorizing_attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorizing_group_plan: TransactionSemanticGroupPlanReference
    planning_authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_authorization: GroupPlanningAuthorization
    supersedes_entry_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_entry(self) -> TransactionGroupPlanLineageEntry:
        if (
            not self.operation_ids
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            or any(not operation_id for operation_id in self.operation_ids)
        ):
            raise ValueError("plan lineage entry operation ids must be nonempty and canonical")
        if self.supersedes_entry_digest == self.entry_digest:
            raise ValueError("plan lineage entry cannot supersede itself")
        if (
            self.planning_authorization.authorization_digest != self.planning_authorization_digest
            or self.planning_authorization.transaction_group_id != self.transaction_group_id
            or self.planning_authorization.group_plan != self.authorizing_group_plan
        ):
            raise ValueError("plan lineage entry planning authorization must exactly authorize its group plan")
        body = self.model_dump(mode="python", exclude={"entry_digest"})
        if self.entry_digest != contract_digest(
            b"memorii.semantic-ingestion.transaction-group-plan-lineage-entry.v1", body
        ):
            raise ValueError("transaction group plan lineage entry digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        transaction_group_id: str,
        operation_ids: tuple[str, ...],
        attempt_id: str,
        authorizing_attempt_digest: str,
        authorizing_group_plan: TransactionSemanticGroupPlanReference,
        planning_authorization_digest: str,
        planning_authorization: GroupPlanningAuthorization,
        supersedes_entry_digest: str | None,
    ) -> TransactionGroupPlanLineageEntry:
        body = {
            "transaction_group_id": transaction_group_id,
            "operation_ids": operation_ids,
            "attempt_id": attempt_id,
            "authorizing_attempt_digest": authorizing_attempt_digest,
            "authorizing_group_plan": authorizing_group_plan,
            "planning_authorization_digest": planning_authorization_digest,
            "planning_authorization": planning_authorization,
            "supersedes_entry_digest": supersedes_entry_digest,
        }
        return cls(
            **body,
            entry_digest=contract_digest(b"memorii.semantic-ingestion.transaction-group-plan-lineage-entry.v1", body),
        )


class IngestionExecutionManifest(BaseModel):
    pre_execution_manifests: BootstrapGraphPreExecutionManifestIdentityClosureV3
    pre_execution_manifest_identity_closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_graph_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_routes: SegmentLanguageRouteSet
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    capability_bindings: tuple[OperationCapabilityExecutionBinding, ...]
    source_outcomes: tuple[IngestionStageOutcome, ...]
    graph_validation_attempts: tuple[GraphDependentValidationAttempt, ...]
    transaction_group_outcomes: tuple[tuple[str, tuple[IngestionStageOutcome, ...]], ...]
    causal_blockers: tuple[IngestionStageInstanceRef, ...]
    terminal_before_planning_proof_digests: tuple[str, ...]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_manifest(self) -> IngestionExecutionManifest:
        if (
            self.pre_execution_manifest_identity_closure_digest
            != self.pre_execution_manifests.closure_digest
        ):
            raise ValueError("execution manifest pre-execution identity closure is substituted")
        if self.execution_graph_fingerprint != CANONICAL_INGESTION_EXECUTION_GRAPH.graph_fingerprint:
            raise ValueError("execution manifest graph fingerprint is not canonical")
        source_id = self.segment_language_routes.source_id
        if (
            self.segment_governance_carriers.source_id != source_id
            or self.message_admission_carriers.source_id != source_id
        ):
            raise ValueError("execution manifest carrier source mismatch")
        artifact = self.governance_carrier_artifact
        if (
            artifact.segment_governance != self.segment_governance_carriers
            or artifact.message_admissions != self.message_admission_carriers
        ):
            raise ValueError("execution manifest carriers must equal governance artifact")
        route_digests = {route.route_digest for route in self.segment_language_routes.routes}
        if self.capability_bindings != _canonical_values(self.capability_bindings) or len(
            {binding.operation_id for binding in self.capability_bindings}
        ) != len(self.capability_bindings):
            raise ValueError("execution manifest capability bindings must be canonical and unique")
        if any(binding.segment_language_route_digest not in route_digests for binding in self.capability_bindings):
            raise ValueError("execution manifest capability binding route is unknown")
        if self.source_outcomes != _canonical_values(self.source_outcomes) or any(
            outcome.instance.scope not in {"source", "segment"} for outcome in self.source_outcomes
        ):
            raise ValueError("execution manifest source outcomes must be canonical and source-or-segment scoped")
        if len({outcome.instance for outcome in self.source_outcomes}) != len(self.source_outcomes):
            raise ValueError("execution manifest source outcomes must be unique")
        expected_source_instances = {
            IngestionStageInstanceRef(stage=spec.stage, scope="source")
            for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages
            if "source" in spec.allowed_scopes
        }
        expected_segment_instances = {
            IngestionStageInstanceRef(
                stage=spec.stage,
                scope="segment",
                segment_id=route.segment_id,
                segment_language_route_digest=route.route_digest,
            )
            for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages
            if "segment" in spec.allowed_scopes
            for route in self.segment_language_routes.routes
        }
        if {
            outcome.instance for outcome in self.source_outcomes
        } != expected_source_instances | expected_segment_instances:
            raise ValueError("execution manifest must retain every source and segment stage outcome")
        if self.graph_validation_attempts != _canonical_values(self.graph_validation_attempts) or len(
            {attempt.attempt_id for attempt in self.graph_validation_attempts}
        ) != len(self.graph_validation_attempts):
            raise ValueError("execution manifest graph attempts must be canonical and unique")
        attempt_ids = {attempt.attempt_id for attempt in self.graph_validation_attempts}
        if any(
            attempt.supersedes_attempt_id is not None and attempt.supersedes_attempt_id not in attempt_ids
            for attempt in self.graph_validation_attempts
        ):
            raise ValueError("execution manifest graph attempt ancestry is orphaned")
        groups = tuple(group_id for group_id, _ in self.transaction_group_outcomes)
        if (
            groups != tuple(sorted(groups))
            or len(set(groups)) != len(groups)
            or any(not group_id for group_id in groups)
        ):
            raise ValueError("execution manifest group outcomes must be canonical and unique")
        for group_id, outcomes in self.transaction_group_outcomes:
            if (
                not outcomes
                or outcomes != _canonical_values(outcomes)
                or any(
                    outcome.instance.scope != "transaction_group" or outcome.instance.transaction_group_id != group_id
                    for outcome in outcomes
                )
            ):
                raise ValueError("execution manifest group stage outcomes are invalid")
            expected_group_stages = {
                spec.stage
                for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages
                if "transaction_group" in spec.allowed_scopes
            }
            if {outcome.instance.stage for outcome in outcomes} != expected_group_stages:
                raise ValueError("execution manifest group must retain every terminal stage outcome")
        if self.causal_blockers != _canonical_values(self.causal_blockers) or len(set(self.causal_blockers)) != len(
            self.causal_blockers
        ):
            raise ValueError("execution manifest causal blockers must be canonical and unique")
        all_outcomes = (
            *self.source_outcomes,
            *(outcome for attempt in self.graph_validation_attempts for outcome in attempt.stage_outcomes),
            *(outcome for _, outcomes in self.transaction_group_outcomes for outcome in outcomes),
        )
        outcome_by_instance = {outcome.instance: outcome for outcome in all_outcomes}
        stage_specs = {spec.stage: spec for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages}
        successful = {"complete", "committed", "evidence_only"}

        def dependency_instances(instance: IngestionStageInstanceRef) -> tuple[IngestionStageInstanceRef, ...]:
            dependencies: list[IngestionStageInstanceRef] = []
            for dependency in stage_specs[instance.stage].dependencies:
                if dependency.mode != "required":
                    continue
                allowed = stage_specs[dependency.stage].allowed_scopes
                if instance.scope == "segment":
                    if "segment" in allowed:
                        dependencies.append(
                            IngestionStageInstanceRef(
                                stage=dependency.stage,
                                scope="segment",
                                segment_id=instance.segment_id,
                                segment_language_route_digest=instance.segment_language_route_digest,
                            )
                        )
                    elif "source" in allowed:
                        dependencies.append(IngestionStageInstanceRef(stage=dependency.stage, scope="source"))
                elif instance.scope == "source":
                    if "source" in allowed:
                        dependencies.append(IngestionStageInstanceRef(stage=dependency.stage, scope="source"))
                    elif "segment" in allowed:
                        dependencies.extend(
                            IngestionStageInstanceRef(
                                stage=dependency.stage,
                                scope="segment",
                                segment_id=route.segment_id,
                                segment_language_route_digest=route.route_digest,
                            )
                            for route in self.segment_language_routes.routes
                        )
                    elif "transaction_group" in allowed:
                        dependencies.extend(
                            IngestionStageInstanceRef(
                                stage=dependency.stage, scope="transaction_group", transaction_group_id=group_id
                            )
                            for group_id, _ in self.transaction_group_outcomes
                        )
                elif instance.scope in {"source_plan_attempt", "transaction_group_attempt"}:
                    if instance.scope in allowed:
                        dependencies.append(
                            IngestionStageInstanceRef(
                                stage=dependency.stage,
                                scope=instance.scope,
                                transaction_group_id=instance.transaction_group_id,
                                attempt_id=instance.attempt_id,
                            )
                        )
                    elif "source" in allowed:
                        dependencies.append(IngestionStageInstanceRef(stage=dependency.stage, scope="source"))
                elif instance.scope == "transaction_group" and "transaction_group" in allowed:
                    dependencies.append(
                        IngestionStageInstanceRef(
                            stage=dependency.stage,
                            scope="transaction_group",
                            transaction_group_id=instance.transaction_group_id,
                        )
                    )
            return _canonical_values(tuple(set(dependencies)))  # type: ignore[return-value]

        for outcome in all_outcomes:
            dependencies = dependency_instances(outcome.instance)
            blocked = tuple(
                dependency
                for dependency in dependencies
                if outcome_by_instance.get(dependency) is None
                or outcome_by_instance[dependency].status not in successful
            )
            if outcome.status == "not_started":
                if outcome.blocking_stages != blocked:
                    raise ValueError("not-started stage blockers must exactly name unsatisfied required dependencies")
            elif blocked:
                raise ValueError("started stage has an unsatisfied required dependency")
        manifest_blockers = tuple(
            outcome.instance for outcome in all_outcomes if outcome.status == "not_started" and outcome.blocking_stages
        )
        if self.causal_blockers != _canonical_values(tuple(set(manifest_blockers))):
            raise ValueError("execution manifest causal blockers must exactly equal blocked stages")
        body = self.model_dump(mode="python", exclude={"manifest_digest"})
        if self.manifest_digest != contract_digest(b"memorii.semantic-ingestion.execution-manifest.v1", body):
            raise ValueError("execution manifest digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> IngestionExecutionManifest:
        return cls(
            **values, manifest_digest=contract_digest(b"memorii.semantic-ingestion.execution-manifest.v1", values)
        )


class SourceTransactionPlanLineage(BaseModel):
    lineage_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    required_outcome_scopes: RequiredOutcomeScopeSet
    initial_group_plan: TransactionSemanticGroupPlanReference
    entries: tuple[TransactionGroupPlanLineageEntry, ...]
    final_entry_digests: tuple[str, ...]
    lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_lineage(self) -> SourceTransactionPlanLineage:
        if self.initial_group_plan.repository_id != self.repository_id:
            raise ValueError("plan lineage initial plan repository mismatch")
        if (
            self.segment_governance_carriers.source_id != self.source_id
            or self.message_admission_carriers.source_id != self.source_id
        ):
            raise ValueError("plan lineage carrier source mismatch")
        artifact = self.governance_carrier_artifact
        if (
            artifact.segment_governance != self.segment_governance_carriers
            or artifact.message_admissions != self.message_admission_carriers
            or artifact.required_outcome_scopes != self.required_outcome_scopes
        ):
            raise ValueError("plan lineage carriers must equal governance artifact")
        if not self.entries or self.entries != _canonical_values(self.entries):
            raise ValueError("plan lineage entries must be nonempty and canonical")
        by_digest = {entry.entry_digest: entry for entry in self.entries}
        if len(by_digest) != len(self.entries):
            raise ValueError("plan lineage entries must have unique digests")
        successors: dict[str, str] = {}
        for entry in self.entries:
            if entry.authorizing_group_plan.repository_id != self.repository_id:
                raise ValueError("plan lineage entry authorization plan repository mismatch")
            predecessor = entry.supersedes_entry_digest
            if predecessor is not None:
                prior = by_digest.get(predecessor)
                if prior is None or prior.transaction_group_id != entry.transaction_group_id:
                    raise ValueError("plan lineage entry supersedes an unknown or cross-group entry")
                if predecessor in successors:
                    raise ValueError("plan lineage group chain cannot fork")
                successors[predecessor] = entry.entry_digest
        for entry in self.entries:
            seen: set[str] = set()
            current = entry
            while current.supersedes_entry_digest is not None:
                if current.entry_digest in seen:
                    raise ValueError("plan lineage group chain cannot cycle")
                seen.add(current.entry_digest)
                current = by_digest[current.supersedes_entry_digest]
        finals = tuple(entry.entry_digest for entry in self.entries if entry.entry_digest not in successors)
        if self.final_entry_digests != finals:
            raise ValueError("plan lineage final entries must be the exact canonical group-chain tails")
        final_entries = tuple(by_digest[digest] for digest in finals)
        if len({entry.transaction_group_id for entry in final_entries}) != len(final_entries):
            raise ValueError("plan lineage must have exactly one final entry per group")
        final_operation_ids = tuple(operation_id for entry in final_entries for operation_id in entry.operation_ids)
        if len(set(final_operation_ids)) != len(final_operation_ids):
            raise ValueError("plan lineage final entries must cover each operation exactly once")
        body = self.model_dump(mode="python", exclude={"lineage_digest"})
        if self.lineage_digest != contract_digest(
            b"memorii.semantic-ingestion.source-transaction-plan-lineage.v1", body
        ):
            raise ValueError("source transaction plan lineage digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SourceTransactionPlanLineage:
        return cls(
            **values,
            lineage_digest=contract_digest(b"memorii.semantic-ingestion.source-transaction-plan-lineage.v1", values),
        )


class SourceTransactionPlanLineageReference(BaseModel):
    """The stable source-level handle carried by progress and terminal results."""

    lineage_id: str = Field(min_length=1)
    lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PrePlanningSourceIngestionProgress(BaseModel):
    kind: Literal["pre_planning"] = "pre_planning"
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    execution_manifest: IngestionExecutionManifest
    completed_source_stage_instances: tuple[IngestionStageInstanceRef, ...]
    next_eligible_source_stage_instances: tuple[IngestionStageInstanceRef, ...]
    replay_artifact_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reusable_artifact_digests: tuple[str, ...]
    retry_attempt_count: int = Field(ge=1)
    retry_reason_codes: tuple[str, ...]
    operation_lease_binding: OperationLeaseBinding
    progress_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_progress(self) -> PrePlanningSourceIngestionProgress:
        for instances, label in (
            (self.completed_source_stage_instances, "completed"),
            (self.next_eligible_source_stage_instances, "next eligible"),
        ):
            if (
                instances != _canonical_values(instances)
                or len(set(instances)) != len(instances)
                or any(instance.scope != "source" for instance in instances)
            ):
                raise ValueError(f"pre-planning {label} stage instances must be canonical source instances")
        if set(self.completed_source_stage_instances) & set(self.next_eligible_source_stage_instances):
            raise ValueError("pre-planning complete and next-eligible stages cannot overlap")
        if self.reusable_artifact_digests != tuple(sorted(set(self.reusable_artifact_digests))) or any(
            len(value) != 64 for value in self.reusable_artifact_digests
        ):
            raise ValueError("pre-planning reusable artifact digests must be canonical")
        if self.retry_reason_codes != tuple(sorted(set(self.retry_reason_codes))) or any(
            not code for code in self.retry_reason_codes
        ):
            raise ValueError("pre-planning retry reason codes must be canonical")
        if self.operation_lease_binding.operation_id != self.operation_id:
            raise ValueError("pre-planning progress operation lease mismatch")
        manifest = self.execution_manifest
        if (
            manifest.segment_language_routes.source_id != self.source_id
            or manifest.segment_language_routes.source_digest != self.source_digest
        ):
            raise ValueError("pre-planning progress manifest source mismatch")
        successful = {"complete", "committed", "evidence_only"}
        source_outcomes = tuple(outcome for outcome in manifest.source_outcomes if outcome.instance.scope == "source")
        expected_completed = _canonical_values(
            tuple(outcome.instance for outcome in source_outcomes if outcome.status in successful)
        )
        if self.completed_source_stage_instances != expected_completed:
            raise ValueError("pre-planning completed stages must equal manifest-derived closure")
        expected_next = _canonical_values(
            tuple(
                outcome.instance
                for outcome in source_outcomes
                if outcome.status == "not_started" and set(outcome.blocking_stages).issubset(set(expected_completed))
            )
        )
        if self.next_eligible_source_stage_instances != expected_next:
            raise ValueError("pre-planning next eligible stages must equal manifest-derived eligibility")
        expected_reusable = tuple(
            sorted(
                outcome.artifact_digest
                for outcome in source_outcomes
                if outcome.status in successful and outcome.artifact_digest is not None
            )
        )
        if self.reusable_artifact_digests != expected_reusable:
            raise ValueError("pre-planning reusable artifacts must equal manifest-derived artifacts")
        body = self.model_dump(mode="python", exclude={"progress_digest"})
        if self.progress_digest != contract_digest(b"memorii.semantic-ingestion.pre-planning-source-progress.v1", body):
            raise ValueError("pre-planning source progress digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> PrePlanningSourceIngestionProgress:
        body = {"kind": "pre_planning", **values}
        return cls(
            **body, progress_digest=contract_digest(b"memorii.semantic-ingestion.pre-planning-source-progress.v1", body)
        )


class PlannedSourceIngestionProgress(BaseModel):
    kind: Literal["planned"] = "planned"
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    plan_lineage: SourceTransactionPlanLineageReference
    replay_artifact_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_group_result_digests: tuple[str, ...]
    unfinished_transaction_group_ids: tuple[str, ...]
    latest_retryable_attempt_digests: tuple[str, ...]
    operation_lease_binding: OperationLeaseBinding
    progress_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_progress(self) -> PlannedSourceIngestionProgress:
        for values, label in (
            (self.terminal_group_result_digests, "terminal result digests"),
            (self.latest_retryable_attempt_digests, "retryable attempt digests"),
        ):
            if values != tuple(sorted(set(values))) or any(
                len(value) != 64 or any(character not in "0123456789abcdef" for character in value) for value in values
            ):
                raise ValueError(f"planned progress {label} must be canonical")
        if self.unfinished_transaction_group_ids != tuple(sorted(set(self.unfinished_transaction_group_ids))) or any(
            not value for value in self.unfinished_transaction_group_ids
        ):
            raise ValueError("planned progress unfinished groups must be canonical")
        if self.operation_lease_binding.operation_id != self.operation_id:
            raise ValueError("planned progress operation lease mismatch")
        body = self.model_dump(mode="python", exclude={"progress_digest"})
        if self.progress_digest != contract_digest(b"memorii.semantic-ingestion.planned-source-progress.v1", body):
            raise ValueError("planned source progress digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> PlannedSourceIngestionProgress:
        body = {"kind": "planned", **values}
        return cls(
            **body, progress_digest=contract_digest(b"memorii.semantic-ingestion.planned-source-progress.v1", body)
        )


SourceIngestionProgress = Annotated[
    PrePlanningSourceIngestionProgress | PlannedSourceIngestionProgress,
    Field(discriminator="kind"),
]


# Normalized proposal contracts intentionally live beside the strict semantic
# codec. Provider-local identifiers exist only on the Provider* wires below;
# every persisted proposal coordinate is a source span or a content digest.
class _ContentAddressedContract(BaseModel):
    _digest_domain: ClassVar[bytes]
    _digest_field: ClassVar[str]
    _create_static_values: ClassVar[Mapping[str, object]] = {}
    _digest_excluded_fields: ClassVar[frozenset[str]] = frozenset()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_content_digest(self) -> _ContentAddressedContract:
        declared = getattr(self, self._digest_field)
        if _digest_verification_hit(self, declared):
            return self
        body = {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name != self._digest_field and name not in self._digest_excluded_fields
        }
        if declared != contract_digest(self._digest_domain, body):
            raise ValueError(f"{self._digest_field} mismatch")
        _record_digest_verification(self, declared)
        return self

    @classmethod
    def create(cls, **values: object):  # type: ignore[no-untyped-def]
        body: dict[str, object] = {}
        for base in reversed(cls.__mro__):
            body.update(base.__dict__.get("_create_static_values", {}))
        if "schema_version" in cls.model_fields:
            body["schema_version"] = 2
        body.update(values)
        digest_body = {
            name: value
            for name, value in body.items()
            if name not in cls._digest_excluded_fields
        }
        return cls(
            **body,
            **{cls._digest_field: contract_digest(cls._digest_domain, digest_body)},
        )


class _TextArtifact(_ContentAddressedContract):
    artifact_id: str = Field(min_length=1)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    unicode_scalar_length: int = Field(ge=0)
    offset_unit: Literal["unicode_scalar"]
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_field = "artifact_digest"
    _create_static_values = {"offset_unit": "unicode_scalar"}


class RetainedSourceTextArtifact(_TextArtifact):
    artifact_kind: Literal["retained_source_text"]
    _digest_domain = b"memorii.semantic-ingestion.retained-source-text-artifact.v1"
    _create_static_values = {"artifact_kind": "retained_source_text"}


class SemanticProjectionTextArtifact(_TextArtifact):
    artifact_kind: Literal["semantic_projection_text"]
    _digest_domain = b"memorii.semantic-ingestion.semantic-projection-text-artifact.v1"
    _create_static_values = {"artifact_kind": "semantic_projection_text"}


class SegmentLocalTextArtifact(_TextArtifact):
    artifact_kind: Literal["segment_local_text"]
    projection_segment_id: str = Field(min_length=1)
    _digest_domain = b"memorii.semantic-ingestion.segment-local-text-artifact.v1"
    _create_static_values = {"artifact_kind": "segment_local_text"}


class _TextSpan(_ContentAddressedContract):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    substring_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    span_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_field = "span_digest"

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.end <= self.start or self.end > self.artifact.unicode_scalar_length:  # type: ignore[attr-defined]
            raise ValueError("text span must be nonempty and within its artifact")
        return self


class RetainedSourceTextSpan(_TextSpan):
    artifact_kind: Literal["retained_source_text"]
    artifact: RetainedSourceTextArtifact
    _digest_domain = b"memorii.semantic-ingestion.retained-source-text-span.v1"
    _create_static_values = {"artifact_kind": "retained_source_text"}


class ProjectionTextSpan(_TextSpan):
    artifact_kind: Literal["semantic_projection_text"]
    artifact: SemanticProjectionTextArtifact
    _digest_domain = b"memorii.semantic-ingestion.projection-text-span.v1"
    _create_static_values = {"artifact_kind": "semantic_projection_text"}


class SegmentLocalTextSpan(_TextSpan):
    artifact_kind: Literal["segment_local_text"]
    artifact: SegmentLocalTextArtifact
    _digest_domain = b"memorii.semantic-ingestion.segment-local-text-span.v1"
    _create_static_values = {"artifact_kind": "segment_local_text"}


class VerbatimTextArtifactMappingProof(_ContentAddressedContract):
    kind: Literal["verbatim_identity"]
    retained_span: RetainedSourceTextSpan
    projection_span: ProjectionTextSpan
    segment_span: SegmentLocalTextSpan
    proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.verbatim-text-artifact-mapping-proof.v1"
    _digest_field = "proof_digest"
    _create_static_values = {"kind": "verbatim_identity"}

    @model_validator(mode="after")
    def validate_mapping(self):
        retained = self.retained_span
        projection = self.projection_span
        segment = self.segment_span
        if (
            retained.start != 0
            or retained.end != retained.artifact.unicode_scalar_length
            or segment.start != 0
            or segment.end != segment.artifact.unicode_scalar_length
            or retained.substring_digest != retained.artifact.content_digest
            or segment.substring_digest != segment.artifact.content_digest
            or retained.artifact.content_digest != segment.artifact.content_digest
            or retained.artifact.unicode_scalar_length != segment.artifact.unicode_scalar_length
            or projection.end - projection.start != segment.artifact.unicode_scalar_length
            or projection.substring_digest != segment.artifact.content_digest
        ):
            raise ValueError(
                "verbatim mapping proof must bind one exact retained/local text into its projection subspan"
            )
        return self


class EnvelopeFieldTextArtifactMappingProof(_ContentAddressedContract):
    kind: Literal["envelope_field"]
    retained_artifact: RetainedSourceTextArtifact
    canonical_json_pointer: str = Field(min_length=1)
    canonical_encoded_field_value_bytes: bytes
    canonical_encoded_field_value_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decoded_content_bytes: bytes
    decoded_content_text_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_segment_id: str = Field(min_length=1)
    projection_span: ProjectionTextSpan
    segment_artifact: SegmentLocalTextArtifact
    segment_span: SegmentLocalTextSpan
    proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.envelope-field-text-artifact-mapping-proof.v1"
    _digest_field = "proof_digest"
    _create_static_values = {"kind": "envelope_field"}

    @model_validator(mode="after")
    def validate_mapping(self):
        try:
            decoded_text = self.decoded_content_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("envelope mapping proof decoded content must be strict UTF-8") from exc
        if (
            self.canonical_encoded_field_value_digest != sha256(self.canonical_encoded_field_value_bytes).hexdigest()
            or self.decoded_content_text_digest != sha256(self.decoded_content_bytes).hexdigest()
            or self.projection_segment_id != self.segment_artifact.projection_segment_id
            or self.segment_span.artifact != self.segment_artifact
            or self.segment_span.start != 0
            or self.segment_span.end != self.segment_artifact.unicode_scalar_length
            or self.projection_span.end - self.projection_span.start != self.segment_artifact.unicode_scalar_length
            or len(decoded_text) != self.segment_artifact.unicode_scalar_length
            or self.segment_artifact.content_digest != self.decoded_content_text_digest
            or self.projection_span.substring_digest != self.segment_artifact.content_digest
            or self.segment_span.substring_digest != self.segment_artifact.content_digest
        ):
            raise ValueError("envelope mapping proof does not bind the exact projection segment")
        return self


TextArtifactMappingProof = Annotated[
    VerbatimTextArtifactMappingProof | EnvelopeFieldTextArtifactMappingProof, Field(discriminator="kind")
]


class SourceSpanReference(_ContentAddressedContract):
    source_id: str = Field(min_length=1)
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_segment_id: str = Field(min_length=1)
    retained_text_artifact: RetainedSourceTextArtifact
    projection_span: ProjectionTextSpan
    segment_local_span: SegmentLocalTextSpan
    text_mapping_proof: TextArtifactMappingProof
    source_reference: str | None
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.source-span-reference.v1"
    _digest_field = "reference_digest"

    @model_validator(mode="after")
    def validate_reference(self):
        if self.projection_digest != self.projection_span.artifact.artifact_digest:
            raise ValueError("source span reference projection digest must bind its projection artifact")
        if (
            self.segment_local_span.artifact.projection_segment_id != self.projection_segment_id
            or self.projection_span.end - self.projection_span.start
            != self.segment_local_span.end - self.segment_local_span.start
            or self.projection_span.substring_digest != self.segment_local_span.substring_digest
        ):
            raise ValueError("source span reference must bind matching projection and local coordinates")
        proof = self.text_mapping_proof
        if isinstance(proof, VerbatimTextArtifactMappingProof):
            proof_retained = proof.retained_span
            proof_projection = proof.projection_span
            proof_segment = proof.segment_span
            if proof_retained.artifact != self.retained_text_artifact:
                raise ValueError("verbatim proof does not match source reference")
        else:
            if (
                proof.retained_artifact != self.retained_text_artifact
                or proof.projection_segment_id != self.projection_segment_id
            ):
                raise ValueError("envelope proof does not match source reference")
            proof_projection = proof.projection_span
            proof_segment = proof.segment_span
        if (
            proof_projection.artifact != self.projection_span.artifact
            or proof_segment.artifact != self.segment_local_span.artifact
            or not _contained_text_span(proof_projection, self.projection_span)
            or not _contained_text_span(proof_segment, self.segment_local_span)
            or self.projection_span.start - proof_projection.start
            != self.segment_local_span.start - proof_segment.start
            or self.projection_span.end - proof_projection.start != self.segment_local_span.end - proof_segment.start
        ):
            raise ValueError("source span reference must be a relative subspan of its complete mapping proof")
        return self


class CanonicalRoleAssignment(_ContentAddressedContract):
    role_id: str = Field(min_length=1)
    argument_span: SourceSpanReference
    endpoint_kind: Literal["subject", "object", "actor", "other"]
    assignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.canonical-role-assignment.v1"
    _digest_field = "assignment_digest"


class AnalyzerRoleInterpretation(_ContentAddressedContract):
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_head_span: SourceSpanReference
    construction_family: ConstructionFamily
    assignments: tuple[CanonicalRoleAssignment, ...]
    interpretation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.analyzer-role-interpretation.v1"
    _digest_field = "interpretation_digest"

    @model_validator(mode="after")
    def validate_interpretation(self) -> AnalyzerRoleInterpretation:
        if (
            not self.assignments
            or self.assignments != tuple(sorted(self.assignments, key=lambda item: item.role_id))
            or len({item.role_id for item in self.assignments}) != len(self.assignments)
        ):
            raise ValueError("role assignments must be nonempty, ordered, and unique")
        source_id = self.predicate_head_span.source_id
        if any(item.argument_span.source_id != source_id for item in self.assignments):
            raise ValueError("role interpretation spans must belong to one source")
        return self


class CheckResult(BaseModel):
    status: Literal["pass", "fail", "unknown"]
    reason_code: str = Field(min_length=1)
    evidence_spans: tuple[SourceSpanReference, ...]
    diagnostics: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_result(self) -> CheckResult:
        if self.evidence_spans != tuple(sorted(self.evidence_spans, key=lambda item: item.reference_digest)) or len(
            {item.reference_digest for item in self.evidence_spans}
        ) != len(self.evidence_spans):
            raise ValueError("check result evidence spans must be canonical and duplicate-free")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))):
            raise ValueError("check result diagnostics must be canonical and duplicate-free")
        return self


class AnalyzerScopeInterpretation(_ContentAddressedContract):
    schema_version: Literal[2]
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    predicate_head_span: SourceSpanReference
    governing_clause_spans: tuple[SourceSpanReference, ...]
    polarity: CheckResult
    commitment: CheckResult
    attribution: CheckResult
    attribution_bearer_span: SourceSpanReference | None
    interpretation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.analyzer-scope-interpretation.v2"
    _digest_field = "interpretation_digest"

    @model_validator(mode="after")
    def validate_interpretation(self) -> AnalyzerScopeInterpretation:
        spans = self.governing_clause_spans
        if (
            not spans
            or spans != tuple(sorted(spans, key=lambda item: item.reference_digest))
            or len({item.reference_digest for item in spans}) != len(spans)
        ):
            raise ValueError("governing clause spans must be nonempty and canonical")
        source_id = self.predicate_head_span.source_id
        if any(span.source_id != source_id for span in spans) or (
            self.attribution_bearer_span is not None and self.attribution_bearer_span.source_id != source_id
        ):
            raise ValueError("scope interpretation spans must belong to one source")
        return self


class AnalyzerScopeObservation(_ContentAddressedContract):
    schema_version: Literal[2]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    analyzer_role: Literal["primary", "corroborating"]
    interpretation: AnalyzerScopeInterpretation
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.analyzer-scope-observation.v2"
    _digest_field = "observation_digest"


class StableSemanticScope(_ContentAddressedContract):
    schema_version: Literal[2]
    polarity: Literal["positive", "negative"]
    commitment: Commitment
    attribution: Literal["speaker", "quoted_or_reported_source"]
    attribution_bearer_span: SourceSpanReference | None
    governing_clause_spans: tuple[SourceSpanReference, ...]
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.stable-semantic-scope.v2"
    _digest_field = "scope_digest"

    @model_validator(mode="after")
    def validate_scope(self) -> StableSemanticScope:
        if (
            not self.governing_clause_spans
            or self.governing_clause_spans
            != tuple(sorted(self.governing_clause_spans, key=lambda item: item.reference_digest))
            or len({item.reference_digest for item in self.governing_clause_spans}) != len(self.governing_clause_spans)
        ):
            raise ValueError("stable scope governing clause spans must be nonempty and canonical")
        if self.attribution == "speaker" and self.attribution_bearer_span is not None:
            raise ValueError("speaker scope cannot retain an attribution bearer")
        if self.attribution == "quoted_or_reported_source" and self.attribution_bearer_span is None:
            raise ValueError("reported scope requires an attribution bearer")
        return self


class AnalyzerTemporalAttachment(_ContentAddressedContract):
    schema_version: Literal[2]
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    predicate_head_span: SourceSpanReference
    candidate_ids: tuple[str, ...]
    attachment_spans: tuple[SourceSpanReference, ...]
    attachment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.analyzer-temporal-attachment.v2"
    _digest_field = "attachment_digest"

    @model_validator(mode="after")
    def validate_attachment(self) -> AnalyzerTemporalAttachment:
        if (
            self.candidate_ids != tuple(sorted(set(self.candidate_ids)))
            or self.attachment_spans != tuple(sorted(self.attachment_spans, key=lambda item: item.reference_digest))
            or len({item.reference_digest for item in self.attachment_spans}) != len(self.attachment_spans)
        ):
            raise ValueError("temporal attachment values must be canonical and duplicate-free")
        if any(span.source_id != self.predicate_head_span.source_id for span in self.attachment_spans):
            raise ValueError("temporal attachment spans must belong to one source")
        return self


class AnalyzerTemporalAttachmentObservation(_ContentAddressedContract):
    schema_version: Literal[2]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    temporal_role: TemporalRole
    analyzer_role: Literal["primary", "corroborating"]
    attachment: AnalyzerTemporalAttachment
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.analyzer-temporal-attachment-observation.v2"
    _digest_field = "observation_digest"


class ParserConsensusAssessment(_ContentAddressedContract):
    schema_version: Literal[2]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_bundle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_interpretation: AnalyzerRoleInterpretation
    corroborating_interpretation: AnalyzerRoleInterpretation
    stable_assignment: tuple[CanonicalRoleAssignment, ...] | None
    status: Literal["stable", "disagreement", "ambiguous", "unsupported"]
    consensus_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.parser-consensus-assessment.v2"
    _digest_field = "assessment_digest"

    @model_validator(mode="after")
    def validate_assessment(self) -> ParserConsensusAssessment:
        primary, corroborating = self.primary_interpretation, self.corroborating_interpretation
        if primary.analyzer_fingerprint == corroborating.analyzer_fingerprint:
            raise ValueError("parser consensus requires distinct analyzer fingerprints")
        for interpretation in (primary, corroborating):
            if interpretation.predicate_head_span.source_id != self.source_id or any(
                assignment.argument_span.source_id != self.source_id
                or assignment.argument_span.projection_segment_id
                != interpretation.predicate_head_span.projection_segment_id
                for assignment in interpretation.assignments
            ):
                raise ValueError("role assignments must share the predicate parent")
        equal = primary.assignments == corroborating.assignments
        if self.status == "stable":
            if self.stable_assignment is None or self.stable_assignment != primary.assignments or not equal:
                raise ValueError("stable parser consensus requires one exact shared assignment")
        elif self.stable_assignment is not None or (self.status == "disagreement" and equal):
            raise ValueError("nonstable parser consensus cannot retain stable assignment")
        return self


class SemanticScopeConsensus(_ContentAddressedContract):
    schema_version: Literal[2]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_bundle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_observation: AnalyzerScopeObservation
    corroborating_observation: AnalyzerScopeObservation
    stable_scope: StableSemanticScope | None
    status: Literal["stable", "disagreement", "ambiguous", "unsupported"]
    consensus_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-scope-consensus.v2"
    _digest_field = "consensus_digest"

    @model_validator(mode="after")
    def validate_consensus(self) -> SemanticScopeConsensus:
        primary, corroborating = self.primary_observation, self.corroborating_observation
        if (
            primary.analyzer_role != "primary"
            or corroborating.analyzer_role != "corroborating"
            or primary.interpretation.analyzer_fingerprint == corroborating.interpretation.analyzer_fingerprint
            or primary.proposal_id != self.proposal_id
            or corroborating.proposal_id != self.proposal_id
        ):
            raise ValueError("scope consensus requires distinct analyzers for its exact proposal")
        equal = (
            primary.interpretation.proposal_id == corroborating.interpretation.proposal_id
            and primary.interpretation.predicate_head_span == corroborating.interpretation.predicate_head_span
            and primary.interpretation.governing_clause_spans == corroborating.interpretation.governing_clause_spans
            and primary.interpretation.polarity == corroborating.interpretation.polarity
            and primary.interpretation.commitment == corroborating.interpretation.commitment
            and primary.interpretation.attribution == corroborating.interpretation.attribution
            and primary.interpretation.attribution_bearer_span == corroborating.interpretation.attribution_bearer_span
        )
        if self.status == "stable":
            if (
                self.stable_scope is None
                or not equal
                or any(
                    check.status != "pass"
                    for check in (
                        primary.interpretation.polarity,
                        primary.interpretation.commitment,
                        primary.interpretation.attribution,
                    )
                )
            ):
                raise ValueError("stable scope consensus requires equal passing interpretations")
        elif self.stable_scope is not None or (self.status == "disagreement" and equal):
            raise ValueError("nonstable scope consensus cannot retain stable scope")
        return self


class TemporalAttachmentConsensus(_ContentAddressedContract):
    schema_version: Literal[2]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    temporal_role: TemporalRole
    temporal_resolution_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_attachment: AnalyzerTemporalAttachmentObservation
    corroborating_attachment: AnalyzerTemporalAttachmentObservation
    stable_candidate_ids: tuple[str, ...] | None
    status: Literal["stable", "disagreement", "ambiguous", "unsupported"]
    consensus_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.temporal-attachment-consensus.v2"
    _digest_field = "consensus_digest"

    @model_validator(mode="after")
    def validate_consensus(self) -> TemporalAttachmentConsensus:
        primary, corroborating = self.primary_attachment, self.corroborating_attachment
        if (
            primary.analyzer_role != "primary"
            or corroborating.analyzer_role != "corroborating"
            or primary.attachment.analyzer_fingerprint == corroborating.attachment.analyzer_fingerprint
            or primary.proposal_id != self.proposal_id
            or corroborating.proposal_id != self.proposal_id
        ):
            raise ValueError("temporal consensus requires distinct analyzers for its exact proposal")
        equal = (
            primary.attachment.candidate_ids == corroborating.attachment.candidate_ids
            and primary.attachment.attachment_spans == corroborating.attachment.attachment_spans
        )
        if self.status == "stable":
            if (
                self.stable_candidate_ids is None
                or self.stable_candidate_ids != primary.attachment.candidate_ids
                or not equal
            ):
                raise ValueError("stable temporal consensus requires exact shared candidates")
        elif self.stable_candidate_ids is not None or (self.status == "disagreement" and equal):
            raise ValueError("nonstable temporal consensus cannot retain candidates")
        return self


class OperationTemporalAttachmentConsensusSet(_ContentAddressedContract):
    """The complete role-keyed temporal consensus closure for one operation."""

    schema_version: Literal[2]
    operation_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    role_consensus_digests: tuple[tuple[TemporalRole, str], ...]
    consensus_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.operation-temporal-attachment-consensus-set.v2"
    _digest_field = "consensus_set_digest"

    @model_validator(mode="after")
    def validate_roles(self) -> OperationTemporalAttachmentConsensusSet:
        roles = tuple(role for role, _ in self.role_consensus_digests)
        if (
            not roles
            or roles != tuple(sorted(roles))
            or len(roles) != len(set(roles))
            or any(not digest for _, digest in self.role_consensus_digests)
        ):
            raise ValueError("temporal consensus roles must be complete and canonical")
        return self


def _contained_text_span(outer: _TextSpan, inner: _TextSpan) -> bool:
    return outer.artifact == inner.artifact and outer.start <= inner.start and inner.end <= outer.end


def _validate_route_span(span: SourceSpanReference, route: SegmentLanguageRoute, source_id: str) -> None:
    """Close a semantic evidence span over the exact selected child route."""
    artifact = span.segment_local_span.artifact
    if (
        span.source_id != source_id
        or span.projection_segment_id != route.parent_projection_segment_id
        or artifact.artifact_id != route.segment_text_artifact_id
        or artifact.artifact_digest != route.segment_text_artifact_digest
        or artifact.content_digest != route.segment_text_content_digest
    ):
        raise ValueError("source span must bind its exact route parent and local artifact")


class SemanticProjectionSegment(_ContentAddressedContract):
    segment_id: str = Field(min_length=1)
    projection_span: ProjectionTextSpan
    segment_text_artifact: SegmentLocalTextArtifact
    text_mapping_proof: TextArtifactMappingProof
    semantic_text: str
    source_variant: Literal["verbatim_text", "conversation_message", "delegation_result_content"]
    source_reference: str | None
    message_semantic_context_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    segment_governance: SegmentGovernanceBinding
    message_admission_identity: MessageAdmissionIdentity | None
    segment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-projection-segment.v1"
    _digest_field = "segment_digest"

    @model_validator(mode="after")
    def validate_segment(self) -> SemanticProjectionSegment:
        text_digest = sha256(self.semantic_text.encode("utf-8")).hexdigest()
        proof = self.text_mapping_proof
        proof_projection = proof.projection_span
        proof_segment = proof.segment_span
        if (
            self.segment_text_artifact.projection_segment_id != self.segment_id
            or self.projection_span.substring_digest != text_digest
            or self.projection_span.end - self.projection_span.start != len(self.semantic_text)
            or self.segment_text_artifact.content_digest != text_digest
            or self.segment_text_artifact.unicode_scalar_length != len(self.semantic_text)
            or proof_projection != self.projection_span
            or proof_segment.artifact != self.segment_text_artifact
            or proof_segment.start != 0
            or proof_segment.end != len(self.semantic_text)
            or proof_segment.substring_digest != text_digest
            or self.segment_governance.segment_id != self.segment_id
        ):
            raise ValueError("semantic projection segment does not bind its exact text and governance")
        if self.message_admission_identity is not None and (
            self.message_admission_identity.segment_governance_binding_digest != self.segment_governance.binding_digest
        ):
            raise ValueError("projection segment admission identity must bind its governance")
        if (self.message_semantic_context_digest is None) != (self.message_admission_identity is None):
            raise ValueError("projection segment message context and admission identity must agree")
        return self


class SourceSemanticTextProjection(BaseModel):
    schema_version: Literal[1]
    retained_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    retained_text_artifact: RetainedSourceTextArtifact
    required_outcome_scopes: RequiredOutcomeScopeSet
    projection_text_artifact: SemanticProjectionTextArtifact
    projection_text: str
    separator: Literal["\n"]
    segments: tuple[SemanticProjectionSegment, ...]
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    envelope_manifest_digest: str | None
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_projection(self) -> SourceSemanticTextProjection:
        segment_ids = tuple(segment.segment_id for segment in self.segments)
        if not self.segments or len(set(segment_ids)) != len(segment_ids):
            raise ValueError("semantic projection must contain unique segments")
        if self.projection_text_artifact.content_digest != sha256(self.projection_text.encode("utf-8")).hexdigest() or (
            self.projection_text_artifact.unicode_scalar_length != len(self.projection_text)
        ):
            raise ValueError("semantic projection text artifact mismatch")
        if self.projection_digest != self.projection_text_artifact.artifact_digest:
            raise ValueError("semantic projection digest must bind its projection artifact")
        if self.segment_governance_carriers.source_id != self.message_admission_carriers.source_id:
            raise ValueError("semantic projection carrier sources differ")
        bindings = self.segment_governance_carriers.bindings
        if (
            tuple(binding.segment_id for binding in bindings) != segment_ids
            or tuple(segment.segment_governance for segment in self.segments) != bindings
        ):
            raise ValueError("semantic projection governance carriers must be an ordered segment bijection")
        admissions = tuple(
            segment.message_admission_identity
            for segment in self.segments
            if segment.message_admission_identity is not None
        )
        if admissions != self.message_admission_carriers.identities:
            raise ValueError("semantic projection admissions must be an ordered segment bijection")
        if self.projection_text != self.separator.join(segment.semantic_text for segment in self.segments):
            raise ValueError("semantic projection text must equal its ordered segment text")
        offset = 0
        for index, segment in enumerate(self.segments):
            span = segment.projection_span
            if (
                span.artifact != self.projection_text_artifact
                or span.start != offset
                or span.end != offset + len(segment.semantic_text)
                or self.projection_text[span.start : span.end] != segment.semantic_text
                or span.substring_digest != sha256(segment.semantic_text.encode("utf-8")).hexdigest()
            ):
                raise ValueError("semantic projection segments must bind source-wide ordered text offsets")
            offset = span.end + (len(self.separator) if index + 1 < len(self.segments) else 0)
        return self


class PreparedSegment(BaseModel):
    segment_id: str = Field(min_length=1)
    parent_projection_segment_id: str = Field(min_length=1)
    owned_projection_span: ProjectionTextSpan
    context_projection_span: ProjectionTextSpan
    owned_segment_span: SegmentLocalTextSpan
    context_segment_span: SegmentLocalTextSpan
    text_mapping_proof: TextArtifactMappingProof
    segment_governance: SegmentGovernanceBinding
    message_admission_identity: MessageAdmissionIdentity | None
    language_route: LanguageRoute
    code_switch_spans: tuple[SegmentLocalTextSpan, ...]
    boundary_flags: frozenset[str]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_segment(self) -> PreparedSegment:
        if self.segment_governance.segment_id != self.parent_projection_segment_id:
            raise ValueError("prepared segment governance must bind its parent projection segment")
        if self.message_admission_identity is not None and (
            self.message_admission_identity.segment_governance_binding_digest != self.segment_governance.binding_digest
        ):
            raise ValueError("prepared segment admission identity must bind its governance")
        if (
            self.owned_projection_span.artifact != self.context_projection_span.artifact
            or self.owned_segment_span.artifact != self.context_segment_span.artifact
            or not _contained_text_span(self.context_projection_span, self.owned_projection_span)
            or not _contained_text_span(self.context_segment_span, self.owned_segment_span)
            or self.owned_projection_span.end - self.owned_projection_span.start
            != self.owned_segment_span.end - self.owned_segment_span.start
            or self.context_projection_span.end - self.context_projection_span.start
            != self.context_segment_span.end - self.context_segment_span.start
            or self.owned_projection_span.start - self.context_projection_span.start
            != self.owned_segment_span.start - self.context_segment_span.start
            or self.owned_projection_span.end - self.context_projection_span.start
            != self.owned_segment_span.end - self.context_segment_span.start
        ):
            raise ValueError("prepared segment owned and context spans must preserve coordinates")
        route = self.language_route
        artifact = self.context_segment_span.artifact
        if (
            route.segment_id != self.segment_id
            or route.parent_projection_segment_id != self.parent_projection_segment_id
            or route.segment_text_artifact_id != artifact.artifact_id
            or route.segment_text_artifact_digest != artifact.artifact_digest
            or route.segment_text_content_digest != artifact.content_digest
            or (
                isinstance(route, SegmentLanguageRoute)
                and tuple(self.code_switch_spans) != tuple(route.code_switch_spans)
            )
        ):
            raise ValueError("prepared segment language route must bind exact segment text")
        return self


class TextPreparationPolicy(_ContentAddressedContract):
    """Pinned deterministic preparation behavior; never reconstructed from a registry."""

    max_segment_characters: int = Field(gt=0)
    supported_languages: tuple[str, ...]
    segmentation_algorithm: Literal["memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1"]
    context_window_algorithm: Literal["memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1"]
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.text-preparation-policy.v1"
    _digest_field = "policy_fingerprint"

    @model_validator(mode="after")
    def validate_policy(self) -> TextPreparationPolicy:
        if (
            not self.supported_languages
            or self.supported_languages != tuple(sorted(self.supported_languages))
            or len(set(self.supported_languages)) != len(self.supported_languages)
            or any(
                not language
                or language != language.strip()
                or not re.fullmatch(r"[a-z]{2,8}(?:-(?:[A-Z][a-z]{3}|[A-Z]{2}|[0-9]{3}|[a-z0-9]{1,8}))*", language)
                for language in self.supported_languages
            )
        ):
            raise ValueError("preparation policy languages must be nonempty and canonical")
        return self


class TextPreparationRequest(BaseModel):
    """Preparation input retains the original host observation and exact policy bytes."""

    observation: SourceObservation
    policy: TextPreparationPolicy

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_request(self) -> TextPreparationRequest:
        # Model validation re-runs the content-addressed policy check before any output exists.
        TextPreparationPolicy.model_validate(self.policy.model_dump(mode="python"))
        if not self.observation.is_governed_admission:
            raise ValueError("text preparation requires a governed admitted observation")
        return self


class ActionProposalRoleContract(BaseModel):
    role_id: str = Field(min_length=1)
    endpoint_kind: Literal["actor", "object"]
    description: str = Field(min_length=1)
    grounding_requirement: Literal["verbatim_source_mention"]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ActionProposalStateContract(BaseModel):
    state_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    allowed_role_ids: tuple[str, ...]
    required_state_anchor: Literal[True]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_state(self) -> ActionProposalStateContract:
        if (
            not self.allowed_role_ids
            or self.allowed_role_ids != tuple(sorted(self.allowed_role_ids))
            or len(set(self.allowed_role_ids)) != len(self.allowed_role_ids)
        ):
            raise ValueError("action proposal state roles must be canonical and nonempty")
        return self


class ActionProposalCatalog(_ContentAddressedContract):
    vocabulary_namespace: str = Field(min_length=1)
    proposal_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    roles: tuple[ActionProposalRoleContract, ...]
    states: tuple[ActionProposalStateContract, ...]
    catalog_schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.action-proposal-catalog.v1"
    _digest_field = "catalog_fingerprint"
    _schema_fingerprint = "0fb700ec5d56481e582f70d89a66627708cd95ad2393e9df78559e0f1f0b16fe"

    @model_validator(mode="after")
    def validate_catalog(self) -> ActionProposalCatalog:
        if self.catalog_schema_fingerprint != self._schema_fingerprint:
            raise ValueError("action catalog schema fingerprint does not match pinned manifest")
        if self.roles != tuple(sorted(self.roles, key=lambda item: item.role_id)) or len(
            {item.role_id for item in self.roles}
        ) != len(self.roles):
            raise ValueError("action catalog roles must be canonical and unique")
        if self.states != tuple(sorted(self.states, key=lambda item: item.state_id)) or len(
            {item.state_id for item in self.states}
        ) != len(self.states):
            raise ValueError("action catalog states must be canonical and unique")
        role_ids = {item.role_id for item in self.roles}
        if (
            not self.roles
            or not self.states
            or any(set(item.allowed_role_ids) - role_ids for item in self.states)
            or role_ids != set().union(*(set(item.allowed_role_ids) for item in self.states))
        ):
            raise ValueError("action catalog states must exactly cover catalog roles")
        return self


class PredicatePromptContract(_ContentAddressedContract):
    predicate_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    subject_value_kind: Literal["entity"]
    object_value_kind: Literal["entity", "literal"]
    object_literal_type: ClaimValueType | None
    supported_commitments: tuple[
        Literal["asserted", "believed", "reported", "quoted", "questioned", "instructed", "hypothetical"], ...
    ]
    contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-prompt-contract.v1"
    _digest_field = "contract_digest"

    @model_validator(mode="after")
    def validate_predicate(self) -> PredicatePromptContract:
        commitment_order = ("asserted", "believed", "reported", "quoted", "questioned", "instructed", "hypothetical")
        if (self.object_value_kind == "entity") != (self.object_literal_type is None):
            raise ValueError("predicate literal type must match object kind")
        if (
            not self.supported_commitments
            or self.supported_commitments != tuple(sorted(self.supported_commitments, key=commitment_order.index))
            or len(set(self.supported_commitments)) != len(self.supported_commitments)
        ):
            raise ValueError("predicate commitments must be canonical and nonempty")
        return self


class PredicateProposalCatalog(_ContentAddressedContract):
    vocabulary_namespace: str = Field(min_length=1)
    proposal_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicates: tuple[PredicatePromptContract, ...]
    catalog_schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-proposal-catalog.v1"
    _digest_field = "catalog_fingerprint"
    _schema_fingerprint = "7c2fef7072d3996b93949eab7db1701d5458379a6b65d96f5851415d748fb0e0"

    @model_validator(mode="after")
    def validate_catalog(self) -> PredicateProposalCatalog:
        if self.catalog_schema_fingerprint != self._schema_fingerprint:
            raise ValueError("predicate catalog schema fingerprint does not match pinned manifest")
        if (
            not self.predicates
            or self.predicates != tuple(sorted(self.predicates, key=lambda item: item.predicate_id))
            or len({item.predicate_id for item in self.predicates}) != len(self.predicates)
        ):
            raise ValueError("predicate catalog entries must be canonical and unique")
        return self


class RegisteredSemanticPromptBinding(BaseModel):
    prompt_ref: str = Field(min_length=1)
    prompt_registration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    visibility_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    redaction_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SemanticProposerManifest(_ContentAddressedContract):
    proposer_id: str = Field(min_length=1)
    proposer_kind: Literal["local", "remote"]
    runtime_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    tokenizer_or_template_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    structured_output_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-proposer-manifest.v1"
    _digest_field = "manifest_digest"


class PreparedSource(BaseModel):
    source_id: str = Field(min_length=1)
    semantic_text: str
    semantic_text_projection: SourceSemanticTextProjection
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_context: SourceSemanticContext
    segment_language_routes: SegmentLanguageRouteSet
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    sentence_spans: tuple[SourceSpanReference, ...]
    segments: tuple[PreparedSegment, ...]
    token_spans: tuple[SourceSpanReference, ...]
    grammar_proofs: tuple[BootstrapSegmentGrammarProof, ...]
    preparation_policy: TextPreparationPolicy
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["complete", "unsupported", "failed"]
    diagnostics: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_prepared_source(self) -> PreparedSource:
        if (
            self.semantic_text != self.semantic_text_projection.projection_text
            or self.semantic_text_projection.retained_source_digest != self.source_digest
            or self.semantic_context.source_id != self.source_id
            or self.semantic_context.source_digest != self.source_digest
            or self.segment_language_routes.source_id != self.source_id
            or self.segment_language_routes.source_digest != self.source_digest
            or self.segment_governance_carriers != self.semantic_text_projection.segment_governance_carriers
            or self.message_admission_carriers != self.semantic_text_projection.message_admission_carriers
        ):
            raise ValueError("prepared source must preserve exact source projection authorities")
        if (
            self.governance_carrier_artifact.segment_governance != self.segment_governance_carriers
            or self.governance_carrier_artifact.message_admissions != self.message_admission_carriers
            or self.governance_carrier_artifact.required_outcome_scopes
            != self.semantic_text_projection.required_outcome_scopes
        ):
            raise ValueError("prepared source governance artifact must contain its exact carriers")
        ids = tuple(segment.segment_id for segment in self.segments)
        parents = tuple(segment.parent_projection_segment_id for segment in self.segments)
        if (
            not ids
            or len(set(ids)) != len(ids)
            or tuple(route.segment_id for route in self.segment_language_routes.routes) != ids
        ):
            raise ValueError("prepared source routes must be an ordered segment bijection")
        if tuple(route.parent_projection_segment_id for route in self.segment_language_routes.routes) != parents:
            raise ValueError("prepared source routes must copy child parent coordinates")
        bootstrap_routes = tuple(
            route
            for route in self.segment_language_routes.routes
            if isinstance(route, BootstrapDeclaredSegmentLanguageRoute)
        )
        if bootstrap_routes:
            if (
                tuple(proof.segment_id for proof in self.grammar_proofs)
                != tuple(route.segment_id for route in bootstrap_routes)
                or len(bootstrap_routes) != len(self.segment_language_routes.routes)
                or any(
                    proof.source_id != self.source_id
                    or proof.normalized_segment_digest != route.normalized_segment_digest
                    or proof.proof_digest != route.grammar_proof_digest
                    or proof.bootstrap_language_evidence_digest != route.bootstrap_language_evidence_digest
                    for proof, route in zip(self.grammar_proofs, bootstrap_routes, strict=True)
                )
            ):
                raise ValueError("prepared source bootstrap grammar proofs must be ordered route bijection")
        elif self.grammar_proofs:
            raise ValueError("non-bootstrap prepared source cannot carry grammar proofs")
        route_by_artifact = {route.segment_text_artifact_digest: route for route in self.segment_language_routes.routes}
        for span in (*self.sentence_spans, *self.token_spans):
            route = route_by_artifact.get(span.segment_local_span.artifact.artifact_digest)
            if route is None:
                raise ValueError("prepared source annotation span must name one route artifact")
            _validate_route_span(span, route, self.source_id)
        carrier_by_parent = {binding.segment_id: binding for binding in self.segment_governance_carriers.bindings}
        if set(parents) != set(carrier_by_parent) or any(
            segment.segment_governance != carrier_by_parent.get(segment.parent_projection_segment_id)
            for segment in self.segments
        ):
            raise ValueError("prepared source children must totally and surjectively bind parent governance")
        admissions_by_parent = {
            identity.segment_governance_binding_digest: identity
            for identity in self.message_admission_carriers.identities
        }
        if any(
            segment.message_admission_identity is not None
            and admissions_by_parent.get(segment.segment_governance.binding_digest)
            != segment.message_admission_identity
            for segment in self.segments
        ):
            raise ValueError("prepared source child admission must bind its parent governance")
        if any(segment.language_route.source_id != self.source_id for segment in self.segments):
            raise ValueError("prepared source segments must belong to source")
        parent_by_id = {segment.segment_id: segment for segment in self.semantic_text_projection.segments}
        expected_parent_ids = tuple(parent_by_id)
        if (
            tuple(
                parent
                for parent, _children in groupby(self.segments, key=lambda item: item.parent_projection_segment_id)
            )
            != expected_parent_ids
        ):
            raise ValueError("prepared source children must be grouped in source parent order")
        for parent_id in expected_parent_ids:
            parent = parent_by_id[parent_id]
            children = tuple(item for item in self.segments if item.parent_projection_segment_id == parent_id)
            if not children:
                raise ValueError("prepared source must retain children for every projection parent")
            cursor = parent.projection_span.start
            for child in children:
                if (
                    child.text_mapping_proof != parent.text_mapping_proof
                    or not _contained_text_span(parent.projection_span, child.context_projection_span)
                    or not _contained_text_span(parent.text_mapping_proof.segment_span, child.context_segment_span)
                    or child.context_projection_span.start - parent.projection_span.start
                    != child.context_segment_span.start - parent.text_mapping_proof.segment_span.start
                    or child.context_projection_span.end - parent.projection_span.start
                    != child.context_segment_span.end - parent.text_mapping_proof.segment_span.start
                    or child.owned_projection_span.artifact != self.semantic_text_projection.projection_text_artifact
                    or child.owned_projection_span.start != cursor
                    or child.owned_projection_span.substring_digest != child.owned_segment_span.substring_digest
                    or self.semantic_text[child.owned_projection_span.start : child.owned_projection_span.end]
                    != parent.semantic_text[child.owned_segment_span.start : child.owned_segment_span.end]
                ):
                    raise ValueError("prepared source children must partition exact parent projection coordinates")
                cursor = child.owned_projection_span.end
            if cursor != parent.projection_span.end:
                raise ValueError("prepared source children must completely partition their parent projection span")
        body = self.model_dump(mode="python", exclude={"preparation_fingerprint"})
        if self.preparation_fingerprint != contract_digest(b"memorii.semantic-ingestion.prepared-source.v1", body):
            raise ValueError("prepared source fingerprint mismatch")
        return self


class TypedLiteral(_ContentAddressedContract):
    literal_type: str = Field(min_length=1)
    canonical_value: str = Field(min_length=1)
    unit: str | None
    literal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.typed-literal.v1"
    _digest_field = "literal_digest"


class ProviderEntityObject(BaseModel):
    kind: Literal["entity"] = "entity"
    entity_ref: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderLiteralObject(BaseModel):
    kind: Literal["literal"] = "literal"
    literal_type: str = Field(min_length=1)
    canonical_value: str = Field(min_length=1)
    unit: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


ProviderObject = Annotated[ProviderEntityObject | ProviderLiteralObject, Field(discriminator="kind")]


class ProviderMention(BaseModel):
    local_id: str = Field(min_length=1)
    mention_quote: str = Field(min_length=1)
    mention_context_quote: str = Field(min_length=1)
    proposed_type: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderFact(BaseModel):
    kind: Literal["fact"] = "fact"
    local_id: str = Field(min_length=1)
    predicate_id: str = Field(min_length=1)
    subject_entity_ref: str = Field(min_length=1)
    object: ProviderObject
    assertion_quote: str = Field(min_length=1)
    predicate_anchor_quote: str = Field(min_length=1)
    polarity: Literal["positive", "negative"]
    commitment: Literal["asserted", "believed", "reported", "quoted", "questioned", "instructed", "hypothetical"]
    attributed_to_entity_ref: str | None = None
    temporal_qualifier_quotes: tuple[str, ...] = ()
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderCorrection(BaseModel):
    kind: Literal["correction"] = "correction"
    local_id: str = Field(min_length=1)
    corrected_fact: ProviderFact
    replacement_fact: ProviderFact
    assertion_quote: str = Field(min_length=1)
    correction_anchor_quote: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderRetraction(BaseModel):
    kind: Literal["retraction"] = "retraction"
    local_id: str = Field(min_length=1)
    retracted_fact: ProviderFact
    assertion_quote: str = Field(min_length=1)
    retraction_anchor_quote: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderClaimRecordSelector(BaseModel):
    kind: Literal["claim"] = "claim"
    fact_local_id: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderActionRecordSelector(BaseModel):
    kind: Literal["action"] = "action"
    logical_action_local_id: str = Field(min_length=1)
    action_anchor_quote: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderAliasRecordSelector(BaseModel):
    kind: Literal["alias"] = "alias"
    alias_namespace: str = Field(min_length=1)
    alias_anchor_quote: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


ProviderRecordSelector = Annotated[
    ProviderClaimRecordSelector | ProviderActionRecordSelector | ProviderAliasRecordSelector,
    Field(discriminator="kind"),
]


class ProviderActionRoleBinding(BaseModel):
    role_id: str = Field(min_length=1)
    endpoint_kind: Literal["actor", "object"]
    entity_refs: tuple[str, ...]
    grounding_quotes: tuple[str, ...]
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderActionState(BaseModel):
    kind: Literal["action_state"] = "action_state"
    local_id: str = Field(min_length=1)
    logical_action_local_id: str = Field(min_length=1)
    action_anchor_quote: str = Field(min_length=1)
    role_bindings: tuple[ProviderActionRoleBinding, ...]
    state_id: str = Field(min_length=1)
    state_anchor_quote: str = Field(min_length=1)
    execution_branch_local_id: str | None = Field(default=None, min_length=1)
    execution_branch_anchor_quote: str | None = Field(default=None, min_length=1)
    assertion_quote: str = Field(min_length=1)
    temporal_qualifier_quotes: tuple[str, ...] = ()
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_branch_pair(self):
        if (self.execution_branch_local_id is None) != (self.execution_branch_anchor_quote is None):
            raise ValueError("provider branch id and anchor quote must be paired")
        return self


class ProviderReferenceAssignment(BaseModel):
    record_selector: ProviderRecordSelector
    successor_entity_refs: tuple[str, ...]
    disposition: Literal["migrate_current", "share_by_explicit_evidence", "preserve_historical"]
    assertion_quote: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderIdentityOperation(BaseModel):
    kind: Literal["identity"] = "identity"
    local_id: str = Field(min_length=1)
    operation: Literal["alias", "rekey", "merge", "split"]
    predecessor_entity_refs: tuple[str, ...]
    successor_entity_refs: tuple[str, ...]
    reference_assignments: tuple[ProviderReferenceAssignment, ...] = ()
    assertion_quote: str = Field(min_length=1)
    identity_anchor_quote: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderSemanticProposal(BaseModel):
    mentions: tuple[ProviderMention, ...] = ()
    facts: tuple[ProviderFact, ...] = ()
    corrections: tuple[ProviderCorrection, ...] = ()
    retractions: tuple[ProviderRetraction, ...] = ()
    action_states: tuple[ProviderActionState, ...] = ()
    identity_operations: tuple[ProviderIdentityOperation, ...] = ()
    abstained: bool
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_abstention(self) -> ProviderSemanticProposal:
        if self.abstained and (
            self.facts or self.corrections or self.retractions or self.action_states or self.identity_operations
        ):
            raise ValueError("abstained provider proposal cannot contain operations")
        all_ids = (
            self.mentions
            + self.facts
            + self.corrections
            + self.retractions
            + self.action_states
            + self.identity_operations
        )
        if len({item.local_id for item in all_ids}) != len(all_ids):
            raise ValueError("provider local ids must be proposal-wide unique")
        return self


class ProposedMention(_ContentAddressedContract):
    mention_span: SourceSpanReference
    proposed_type: str | None
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-mention.v1"
    _digest_field = "mention_digest"


class ProposedEntityObject(_ContentAddressedContract):
    kind: Literal["entity"]
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-entity-object.v1"
    _digest_field = "object_digest"
    _create_static_values = {"kind": "entity"}


class ProposedLiteralObject(_ContentAddressedContract):
    kind: Literal["literal"]
    value: TypedLiteral
    object_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-literal-object.v1"
    _digest_field = "object_digest"
    _create_static_values = {"kind": "literal"}


ProposedObject = Annotated[ProposedEntityObject | ProposedLiteralObject, Field(discriminator="kind")]


class ProposedFact(_ContentAddressedContract):
    kind: Literal["fact"]
    predicate_id: str = Field(min_length=1)
    subject_mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    object: ProposedObject
    assertion_span: SourceSpanReference
    predicate_anchor_span: SourceSpanReference
    polarity: Literal["positive", "negative"]
    commitment: Literal["asserted", "believed", "reported", "quoted", "questioned", "instructed", "hypothetical"]
    attributed_to_mention_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_qualifier_spans: tuple[SourceSpanReference, ...]
    fact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-fact.v1"
    _digest_field = "fact_digest"
    _create_static_values = {"kind": "fact"}

    @model_validator(mode="after")
    def validate_fact_order(self) -> ProposedFact:
        keys = tuple(span.reference_digest for span in self.temporal_qualifier_spans)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("fact temporal qualifiers must be canonical")
        return self


class ProposedCorrection(_ContentAddressedContract):
    kind: Literal["correction"]
    corrected_fact: ProposedFact
    replacement_fact: ProposedFact
    assertion_span: SourceSpanReference
    correction_anchor_span: SourceSpanReference
    correction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-correction.v1"
    _digest_field = "correction_digest"
    _create_static_values = {"kind": "correction"}


class ProposedRetraction(_ContentAddressedContract):
    kind: Literal["retraction"]
    retracted_fact: ProposedFact
    assertion_span: SourceSpanReference
    retraction_anchor_span: SourceSpanReference
    retraction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-retraction.v1"
    _digest_field = "retraction_digest"
    _create_static_values = {"kind": "retraction"}


class ProposedActionRoleParticipant(_ContentAddressedContract):
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    grounding_spans: tuple[SourceSpanReference, ...]
    participant_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-action-role-participant.v1"
    _digest_field = "participant_digest"

    @model_validator(mode="after")
    def validate_grounding(self):
        keys = tuple(span.reference_digest for span in self.grounding_spans)
        if not keys or keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("participant grounding spans must be canonical and unique")
        return self


class ProposedActionRoleBinding(_ContentAddressedContract):
    role_id: str = Field(min_length=1)
    endpoint_kind: Literal["actor", "object"]
    participants: tuple[ProposedActionRoleParticipant, ...]
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-action-role-binding.v1"
    _digest_field = "binding_digest"

    @model_validator(mode="after")
    def validate_participants(self):
        keys = tuple((member.mention_digest, member.participant_digest) for member in self.participants)
        if (
            not keys
            or keys != tuple(sorted(keys))
            or len({member.participant_digest for member in self.participants}) != len(self.participants)
        ):
            raise ValueError("role participants must be canonical and unique")
        return self


class ProposedActionState(_ContentAddressedContract):
    kind: Literal["action_state"]
    action_anchor_span: SourceSpanReference
    logical_action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    role_bindings: tuple[ProposedActionRoleBinding, ...]
    state_id: str = Field(min_length=1)
    state_anchor_span: SourceSpanReference
    execution_branch_span: SourceSpanReference | None
    execution_branch_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    assertion_span: SourceSpanReference
    temporal_qualifier_spans: tuple[SourceSpanReference, ...]
    action_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-action-state.v1"
    _digest_field = "action_state_digest"
    _create_static_values = {"kind": "action_state"}

    @model_validator(mode="after")
    def validate_action(self):
        if (self.execution_branch_span is None) != (self.execution_branch_digest is None):
            raise ValueError("execution branch span and digest must be paired")
        if self.execution_branch_span is not None and self.execution_branch_digest != contract_digest(
            b"memorii.semantic-ingestion.proposed-execution-branch.v1",
            {"execution_branch_span": self.execution_branch_span},
        ):
            raise ValueError("execution branch digest mismatch")
        binding_keys = tuple((item.role_id, item.endpoint_kind, item.binding_digest) for item in self.role_bindings)
        span_keys = tuple(item.reference_digest for item in self.temporal_qualifier_spans)
        if (
            binding_keys != tuple(sorted(binding_keys))
            or len({item.binding_digest for item in self.role_bindings}) != len(self.role_bindings)
            or span_keys != tuple(sorted(span_keys))
            or len(set(span_keys)) != len(span_keys)
        ):
            raise ValueError("action nested members must be canonical and unique")
        expected = contract_digest(
            b"memorii.semantic-ingestion.proposed-logical-action.v1",
            {"action_anchor_span": self.action_anchor_span, "role_bindings": self.role_bindings},
        )
        if self.logical_action_digest != expected:
            raise ValueError("logical action digest mismatch")
        return self


class ProposedClaimRecordSelector(_ContentAddressedContract):
    kind: Literal["claim"]
    fact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selector_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-claim-record-selector.v1"
    _digest_field = "selector_digest"
    _create_static_values = {"kind": "claim"}


class ProposedActionRecordSelector(_ContentAddressedContract):
    kind: Literal["action"]
    logical_action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_anchor_span: SourceSpanReference
    selector_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-action-record-selector.v1"
    _digest_field = "selector_digest"
    _create_static_values = {"kind": "action"}


class ProposedAliasRecordSelector(_ContentAddressedContract):
    kind: Literal["alias"]
    alias_namespace: str = Field(min_length=1)
    alias_anchor_span: SourceSpanReference
    selector_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-alias-record-selector.v1"
    _digest_field = "selector_digest"
    _create_static_values = {"kind": "alias"}


ProposedRecordSelector = Annotated[
    ProposedClaimRecordSelector | ProposedActionRecordSelector | ProposedAliasRecordSelector,
    Field(discriminator="kind"),
]


class ProposedReferenceAssignment(_ContentAddressedContract):
    record_selector: ProposedRecordSelector
    successor_mention_digests: tuple[str, ...]
    disposition: Literal["migrate_current", "share_by_explicit_evidence", "preserve_historical"]
    assertion_span: SourceSpanReference
    assignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-reference-assignment.v1"
    _digest_field = "assignment_digest"

    @model_validator(mode="after")
    def validate_successors(self):
        if (
            not self.successor_mention_digests
            or self.successor_mention_digests != tuple(sorted(self.successor_mention_digests))
            or len(set(self.successor_mention_digests)) != len(self.successor_mention_digests)
        ):
            raise ValueError("assignment successors must be canonical and nonempty")
        return self


class ProposedIdentityOperation(_ContentAddressedContract):
    kind: Literal["identity"]
    operation: Literal["alias", "rekey", "merge", "split"]
    predecessor_mention_digests: tuple[str, ...]
    successor_mention_digests: tuple[str, ...]
    reference_assignments: tuple[ProposedReferenceAssignment, ...]
    assertion_span: SourceSpanReference
    identity_anchor_span: SourceSpanReference
    identity_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.proposed-identity-operation.v1"
    _digest_field = "identity_operation_digest"
    _create_static_values = {"kind": "identity"}

    @model_validator(mode="after")
    def validate_identity(self):
        for values in (self.predecessor_mention_digests, self.successor_mention_digests):
            if not values or values != tuple(sorted(values)) or len(set(values)) != len(values):
                raise ValueError("identity members must be canonical and nonempty")
        assignments = tuple(
            (item.record_selector.selector_digest, item.assignment_digest) for item in self.reference_assignments
        )
        if (
            assignments != tuple(sorted(assignments))
            or len({item.assignment_digest for item in self.reference_assignments}) != len(self.reference_assignments)
            or len({item.record_selector.selector_digest for item in self.reference_assignments})
            != len(self.reference_assignments)
        ):
            raise ValueError("reference assignments must be canonical and unique")
        if self.operation != "split" and self.reference_assignments:
            raise ValueError("only splits may contain reference assignments")
        return self


class SemanticProposal(_ContentAddressedContract):
    proposal_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_governance: SegmentGovernanceBinding
    message_admission_identity: MessageAdmissionIdentity | None
    governance_carrier_artifact: GovernanceCarrierArtifact
    owned_text: SourceSpanReference
    context_text: SourceSpanReference
    language_route: SegmentLanguageRoute
    proposer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_registration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_proposal_catalog_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_payload_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    originating_attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mentions: tuple[ProposedMention, ...]
    facts: tuple[ProposedFact, ...]
    corrections: tuple[ProposedCorrection, ...]
    retractions: tuple[ProposedRetraction, ...]
    action_states: tuple[ProposedActionState, ...]
    identity_operations: tuple[ProposedIdentityOperation, ...]
    status: Literal["complete", "abstained"]
    diagnostics: tuple[str, ...]
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-proposal.v1"
    _digest_field = "proposal_digest"

    @model_validator(mode="after")
    def validate_proposal(self) -> SemanticProposal:
        if (
            self.segment_governance.source_id != self.source_id
            or self.segment_governance.segment_id != self.language_route.parent_projection_segment_id
            or self.language_route.source_id != self.source_id
            or self.language_route.source_digest != self.source_digest
            or self.language_route.segment_id != self.segment_id
        ):
            raise ValueError("proposal authorities must bind the exact source and segment")
        if self.message_admission_identity is not None and (
            self.message_admission_identity.segment_governance_binding_digest != self.segment_governance.binding_digest
        ):
            raise ValueError("proposal message admission must bind segment governance")
        artifact = self.governance_carrier_artifact
        if (
            artifact.segment_governance.source_id != self.source_id
            or self.segment_governance not in artifact.segment_governance.bindings
            or (
                self.message_admission_identity is not None
                and self.message_admission_identity not in artifact.message_admissions.identities
            )
        ):
            raise ValueError("proposal governance carrier does not contain its authorities")
        for span in (self.owned_text, self.context_text):
            if span.source_id != self.source_id:
                raise ValueError("proposal text spans must belong to source")
            if span.projection_segment_id != self.language_route.parent_projection_segment_id:
                raise ValueError("proposal text spans must bind the exact segment")
        if (
            self.owned_text.projection_digest != self.context_text.projection_digest
            or self.owned_text.retained_text_artifact != self.context_text.retained_text_artifact
            or self.owned_text.segment_local_span.artifact != self.context_text.segment_local_span.artifact
            or self.owned_text.projection_span.start < self.context_text.projection_span.start
            or self.owned_text.projection_span.end > self.context_text.projection_span.end
            or self.owned_text.segment_local_span.start < self.context_text.segment_local_span.start
            or self.owned_text.segment_local_span.end > self.context_text.segment_local_span.end
        ):
            raise ValueError("proposal owned and context text must share one projection")
        segment_artifact = self.context_text.segment_local_span.artifact
        if (
            self.language_route.segment_text_artifact_id != segment_artifact.artifact_id
            or self.language_route.segment_text_artifact_digest != segment_artifact.artifact_digest
            or self.language_route.segment_text_content_digest != segment_artifact.content_digest
        ):
            raise ValueError("proposal language route must bind the exact segment text artifact")
        operations = (self.facts, self.corrections, self.retractions, self.action_states, self.identity_operations)
        if (self.status == "abstained") != (not any(operations)):
            raise ValueError("proposal status must match operation membership")
        for members, field, key in (
            (self.mentions, "mention_digest", lambda x: (x.mention_span.reference_digest, x.mention_digest)),
            (
                self.facts,
                "fact_digest",
                lambda x: (x.predicate_anchor_span.reference_digest, x.assertion_span.reference_digest, x.fact_digest),
            ),
            (
                self.corrections,
                "correction_digest",
                lambda x: (
                    x.correction_anchor_span.reference_digest,
                    x.assertion_span.reference_digest,
                    x.correction_digest,
                ),
            ),
            (
                self.retractions,
                "retraction_digest",
                lambda x: (
                    x.retraction_anchor_span.reference_digest,
                    x.assertion_span.reference_digest,
                    x.retraction_digest,
                ),
            ),
            (
                self.action_states,
                "action_state_digest",
                lambda x: (
                    x.action_anchor_span.reference_digest,
                    x.assertion_span.reference_digest,
                    x.action_state_digest,
                ),
            ),
            (
                self.identity_operations,
                "identity_operation_digest",
                lambda x: (
                    x.identity_anchor_span.reference_digest,
                    x.assertion_span.reference_digest,
                    x.identity_operation_digest,
                ),
            ),
        ):
            digests = tuple(getattr(member, field) for member in members)
            if tuple(members) != tuple(sorted(members, key=key)) or len(set(digests)) != len(digests):
                raise ValueError("proposal members must be canonical and unique")
        self._validate_member_closure()
        return self

    def _validate_member_closure(self) -> None:
        """Close every persisted member over this proposal's exact source authority."""
        mention_digests = tuple(member.mention_digest for member in self.mentions)
        if len(set(mention_digests)) != len(mention_digests):
            raise ValueError("proposal mentions must have unique digests")
        mention_set = set(mention_digests)

        def require_mention(digest: str, label: str) -> None:
            if digest not in mention_set:
                raise ValueError(f"proposal {label} must resolve exactly one mention")

        def require_span(span: SourceSpanReference, label: str, *, owned: bool = False) -> None:
            if (
                span.source_id != self.source_id
                or span.projection_segment_id != self.language_route.parent_projection_segment_id
                or span.projection_digest != self.context_text.projection_digest
                or span.retained_text_artifact != self.context_text.retained_text_artifact
                or span.projection_span.artifact != self.context_text.projection_span.artifact
                or span.segment_local_span.artifact != self.context_text.segment_local_span.artifact
            ):
                raise ValueError(f"proposal {label} span must bind its exact source, segment, and artifacts")
            if not _reference_contains(self.context_text, span):
                raise ValueError(f"proposal {label} span must lie within proposal context")
            if owned and not _reference_contains(self.owned_text, span):
                raise ValueError(f"proposal {label} anchor must lie within proposal owned text")

        def require_fact(fact: ProposedFact, label: str) -> None:
            require_mention(fact.subject_mention_digest, f"{label} subject")
            if isinstance(fact.object, ProposedEntityObject):
                require_mention(fact.object.mention_digest, f"{label} object")
            if fact.attributed_to_mention_digest is not None:
                require_mention(fact.attributed_to_mention_digest, f"{label} attribution")
            require_span(fact.assertion_span, f"{label} assertion")
            require_span(fact.predicate_anchor_span, f"{label} predicate", owned=True)
            if not _reference_contains(fact.assertion_span, fact.predicate_anchor_span):
                raise ValueError(f"proposal {label} predicate must lie within its assertion")
            for index, span in enumerate(fact.temporal_qualifier_spans):
                require_span(span, f"{label} temporal qualifier {index}")
                if not _reference_contains(fact.assertion_span, span):
                    raise ValueError(f"proposal {label} temporal qualifier must lie within its assertion")

        for index, mention in enumerate(self.mentions):
            require_span(mention.mention_span, f"mention {index}")
        for index, fact in enumerate(self.facts):
            require_fact(fact, f"fact {index}")
        for index, correction in enumerate(self.corrections):
            require_fact(correction.corrected_fact, f"correction {index} corrected fact")
            require_fact(correction.replacement_fact, f"correction {index} replacement fact")
            require_span(correction.assertion_span, f"correction {index} assertion")
            require_span(correction.correction_anchor_span, f"correction {index}", owned=True)
            if not _reference_contains(correction.assertion_span, correction.correction_anchor_span):
                raise ValueError(f"proposal correction {index} anchor must lie within its assertion")
        for index, retraction in enumerate(self.retractions):
            require_fact(retraction.retracted_fact, f"retraction {index} fact")
            require_span(retraction.assertion_span, f"retraction {index} assertion")
            require_span(retraction.retraction_anchor_span, f"retraction {index}", owned=True)
            if not _reference_contains(retraction.assertion_span, retraction.retraction_anchor_span):
                raise ValueError(f"proposal retraction {index} anchor must lie within its assertion")
        for index, action in enumerate(self.action_states):
            require_span(action.assertion_span, f"action {index} assertion")
            require_span(action.action_anchor_span, f"action {index}", owned=True)
            require_span(action.state_anchor_span, f"action {index} state", owned=True)
            for span, label in ((action.action_anchor_span, "anchor"), (action.state_anchor_span, "state")):
                if not _reference_contains(action.assertion_span, span):
                    raise ValueError(f"proposal action {index} {label} must lie within its assertion")
            if action.execution_branch_span is not None:
                require_span(action.execution_branch_span, f"action {index} execution branch")
                if not _reference_contains(action.assertion_span, action.execution_branch_span):
                    raise ValueError(f"proposal action {index} execution branch must lie within its assertion")
            for temporal_index, span in enumerate(action.temporal_qualifier_spans):
                require_span(span, f"action {index} temporal qualifier {temporal_index}")
                if not _reference_contains(action.assertion_span, span):
                    raise ValueError(f"proposal action {index} temporal qualifier must lie within its assertion")
            for binding_index, binding in enumerate(action.role_bindings):
                for participant_index, participant in enumerate(binding.participants):
                    require_mention(
                        participant.mention_digest,
                        f"action {index} role {binding_index} participant {participant_index}",
                    )
                    for grounding_index, span in enumerate(participant.grounding_spans):
                        require_span(
                            span,
                            f"action {index} role {binding_index} participant {participant_index} grounding {grounding_index}",
                        )
                        if not _reference_contains(action.assertion_span, span):
                            raise ValueError(
                                f"proposal action {index} participant grounding must lie within its assertion"
                            )

        facts_by_digest = {fact.fact_digest for fact in self.facts}
        action_coordinates = tuple(
            (action.logical_action_digest, action.action_anchor_span.reference_digest) for action in self.action_states
        )
        for index, identity in enumerate(self.identity_operations):
            for digest in identity.predecessor_mention_digests:
                require_mention(digest, f"identity {index} predecessor")
            for digest in identity.successor_mention_digests:
                require_mention(digest, f"identity {index} successor")
            require_span(identity.assertion_span, f"identity {index} assertion")
            require_span(identity.identity_anchor_span, f"identity {index}", owned=True)
            if not _reference_contains(identity.assertion_span, identity.identity_anchor_span):
                raise ValueError(f"proposal identity {index} anchor must lie within its assertion")
            for assignment_index, assignment in enumerate(identity.reference_assignments):
                for digest in assignment.successor_mention_digests:
                    require_mention(digest, f"identity {index} assignment {assignment_index} successor")
                require_span(assignment.assertion_span, f"identity {index} assignment {assignment_index} assertion")
                if not _reference_contains(identity.assertion_span, assignment.assertion_span):
                    raise ValueError(
                        f"proposal identity {index} assignment {assignment_index} must lie within its assertion"
                    )
                selector = assignment.record_selector
                if isinstance(selector, ProposedClaimRecordSelector):
                    if selector.fact_digest not in facts_by_digest:
                        raise ValueError(f"identity {index} claim selector must resolve exactly one top-level fact")
                elif isinstance(selector, ProposedActionRecordSelector):
                    require_span(selector.action_anchor_span, f"identity {index} action selector")
                    if not _reference_contains(assignment.assertion_span, selector.action_anchor_span):
                        raise ValueError(
                            f"proposal identity {index} action selector must lie within its assignment assertion"
                        )
                    if (
                        action_coordinates.count(
                            (selector.logical_action_digest, selector.action_anchor_span.reference_digest)
                        )
                        != 1
                    ):
                        raise ValueError(f"identity {index} action selector must resolve exactly one action")
                else:
                    require_span(selector.alias_anchor_span, f"identity {index} alias selector")
                    if not _reference_contains(assignment.assertion_span, selector.alias_anchor_span):
                        raise ValueError(
                            f"proposal identity {index} alias selector must lie within its assignment assertion"
                        )

    @property
    def segment_language_route_digest(self) -> str:
        """Compatibility read view; the route object is the persisted authority."""
        return self.language_route.route_digest





class SemanticProposalResponseArtifact(_ContentAddressedContract):
    raw_output_bytes: bytes
    raw_output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-proposal-response-artifact.v1"
    _digest_field = "artifact_digest"

    @model_validator(mode="after")
    def validate_response(self) -> SemanticProposalResponseArtifact:
        if self.raw_output_digest != sha256(self.raw_output_bytes).hexdigest():
            raise ValueError("proposal response artifact bytes digest mismatch")
        return self

    @classmethod
    def create(cls, *, raw_output_bytes: bytes) -> SemanticProposalResponseArtifact:
        return super().create(raw_output_bytes=raw_output_bytes, raw_output_digest=sha256(raw_output_bytes).hexdigest())


class SemanticProposalAttemptIdentity(_ContentAddressedContract):
    source_id: str = Field(min_length=1)
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_governance: SegmentGovernanceBinding
    message_admission_identity: MessageAdmissionIdentity | None
    governance_carrier_artifact: GovernanceCarrierArtifact
    owned_text: SourceSpanReference
    context_text: SourceSpanReference
    language_route: SegmentLanguageRoute
    proposer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_registration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_payload_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_number: int = Field(ge=0)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-proposal-attempt-identity.v1"
    _digest_field = "attempt_identity_digest"

    @model_validator(mode="after")
    def validate_identity(self) -> SemanticProposalAttemptIdentity:
        if (
            self.segment_governance.source_id != self.source_id
            or self.segment_governance.segment_id != self.language_route.parent_projection_segment_id
            or self.language_route.source_id != self.source_id
            or self.language_route.segment_id != self.segment_id
        ):
            raise ValueError("proposal attempt identity authorities must bind exact source and segment")
        if self.message_admission_identity is not None and (
            self.message_admission_identity.segment_governance_binding_digest != self.segment_governance.binding_digest
        ):
            raise ValueError("proposal attempt identity message admission must bind segment governance")
        artifact = self.governance_carrier_artifact
        if (
            artifact.segment_governance.source_id != self.source_id
            or self.segment_governance not in artifact.segment_governance.bindings
            or (
                self.message_admission_identity is not None
                and self.message_admission_identity not in artifact.message_admissions.identities
            )
        ):
            raise ValueError("proposal attempt identity governance artifact does not contain its authorities")
        for span in (self.owned_text, self.context_text):
            if (
                span.source_id != self.source_id
                or span.projection_segment_id != self.language_route.parent_projection_segment_id
            ):
                raise ValueError("proposal attempt identity text spans must bind exact source and segment")
        if (
            self.owned_text.projection_digest != self.context_text.projection_digest
            or self.owned_text.retained_text_artifact != self.context_text.retained_text_artifact
            or self.owned_text.segment_local_span.artifact != self.context_text.segment_local_span.artifact
            or self.owned_text.projection_span.start < self.context_text.projection_span.start
            or self.owned_text.projection_span.end > self.context_text.projection_span.end
        ):
            raise ValueError("proposal attempt identity owned text must be contained by context text")
        artifact = self.context_text.segment_local_span.artifact
        if (
            self.language_route.segment_text_artifact_id != artifact.artifact_id
            or self.language_route.segment_text_artifact_digest != artifact.artifact_digest
            or self.language_route.segment_text_content_digest != artifact.content_digest
        ):
            raise ValueError("proposal attempt identity route must bind exact segment text")
        return self


class SemanticProposalAttempt(_ContentAddressedContract):
    identity: SemanticProposalAttemptIdentity
    raw_output_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    response_artifact_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["complete", "partial", "abstained", "evidence_only", "failed"]
    diagnostics: tuple[str, ...]
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-proposal-attempt.v1"
    _digest_field = "attempt_digest"

    @model_validator(mode="after")
    def validate_attempt(self) -> SemanticProposalAttempt:
        has_response = self.raw_output_digest is not None and self.response_artifact_digest is not None
        if (self.raw_output_digest is None) != (self.response_artifact_digest is None):
            raise ValueError("proposal attempt response digest and artifact must agree")
        if self.status in {"complete", "partial", "abstained"} and not has_response:
            raise ValueError("proposal attempt terminal provider status requires response artifact")
        if self.status == "evidence_only" and has_response:
            raise ValueError("evidence-only proposal attempt forbids response artifact")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))) or any(not item for item in self.diagnostics):
            raise ValueError("proposal attempt diagnostics must be canonical")
        return self


class SegmentProposalOutcome(_ContentAddressedContract):
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["complete", "abstained", "evidence_only", "failed"]
    proposal_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    reason_codes: tuple[str, ...]
    outcome_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.segment-proposal-outcome.v1"
    _digest_field = "outcome_digest"

    @model_validator(mode="after")
    def validate_outcome(self) -> SegmentProposalOutcome:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))) or any(not value for value in self.reason_codes):
            raise ValueError("segment proposal outcome reason codes must be canonical")
        if (self.status in {"complete", "abstained"}) != (self.proposal_digest is not None):
            raise ValueError("segment proposal outcome proposal digest must match promotable status")
        if self.status in {"complete", "abstained", "failed"} and self.attempt_digest is None:
            raise ValueError("route-selected terminal proposal outcome requires attempt digest")
        if self.status == "evidence_only" and self.proposal_digest is not None:
            raise ValueError("evidence-only proposal outcome forbids proposal digest")
        return self




def _reference_contains(outer: SourceSpanReference, inner: SourceSpanReference) -> bool:
    return (
        outer.projection_span.artifact == inner.projection_span.artifact
        and outer.segment_local_span.artifact == inner.segment_local_span.artifact
        and outer.projection_span.start <= inner.projection_span.start
        and inner.projection_span.end <= outer.projection_span.end
        and outer.segment_local_span.start <= inner.segment_local_span.start
        and inner.segment_local_span.end <= outer.segment_local_span.end
    )


# The member closure is intentionally shared with the normalized proposal after
# the attempt/run contracts; assigning it here keeps its source-span helper
# available without creating a second closure implementation.


class ParserConsensusPolicy(_ContentAddressedContract):
    kind: Literal["parser"]
    algorithm: Literal["memorii.semantic-ingestion.parser-consensus.exact-two-analyzer.v1"]
    required_independent_analyzers: Literal[2]
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.parser-consensus-rule.v1"
    _digest_field = "policy_fingerprint"
    _create_static_values = {
        "kind": "parser",
        "algorithm": "memorii.semantic-ingestion.parser-consensus.exact-two-analyzer.v1",
        "required_independent_analyzers": 2,
    }


class ScopeConsensusPolicy(_ContentAddressedContract):
    kind: Literal["scope"]
    algorithm: Literal["memorii.semantic-ingestion.scope-consensus.exact-two-analyzer.v1"]
    required_independent_analyzers: Literal[2]
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.scope-consensus-rule.v1"
    _digest_field = "policy_fingerprint"
    _create_static_values = {
        "kind": "scope",
        "algorithm": "memorii.semantic-ingestion.scope-consensus.exact-two-analyzer.v1",
        "required_independent_analyzers": 2,
    }


class TemporalAttachmentConsensusPolicy(_ContentAddressedContract):
    kind: Literal["temporal_attachment"]
    algorithm: Literal["memorii.semantic-ingestion.temporal-attachment-consensus.exact-two-analyzer.v1"]
    required_independent_analyzers: Literal[2]
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.temporal-attachment-consensus-rule.v1"
    _digest_field = "policy_fingerprint"
    _create_static_values = {
        "kind": "temporal_attachment",
        "algorithm": "memorii.semantic-ingestion.temporal-attachment-consensus.exact-two-analyzer.v1",
        "required_independent_analyzers": 2,
    }


ConsensusPolicy = Annotated[
    ParserConsensusPolicy | ScopeConsensusPolicy | TemporalAttachmentConsensusPolicy, Field(discriminator="kind")
]


class ConsensusPolicySelection(_ContentAddressedContract):
    schema_version: Literal[2]
    kind: Literal["parser", "scope", "temporal_attachment"]
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_role: TemporalRole | None
    request_dependency_kind: Literal["analyses", "temporal_resolution"]
    request_dependency_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_policy: ConsensusPolicy
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.consensus-policy-selection.v2"
    _digest_field = "selection_digest"

    @model_validator(mode="after")
    def validate_selection(self):
        if (
            self.kind != self.selected_policy.kind
            or self.selected_policy_fingerprint != self.selected_policy.policy_fingerprint
        ):
            raise ValueError("consensus policy selection must bind exact policy kind and fingerprint")
        if (self.kind == "temporal_attachment") != (self.request_dependency_kind == "temporal_resolution"):
            raise ValueError("consensus policy selection dependency kind mismatches rule kind")
        if self.kind == "temporal_attachment":
            if self.temporal_role is None:
                raise ValueError("temporal consensus policy selection requires a temporal role")
        elif self.temporal_role is not None:
            raise ValueError("parser and scope consensus policy selections cannot have a temporal role")
        return self


class FactOperationSemanticPolicyKey(BaseModel):
    kind: Literal["fact"]
    predicate_id: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CorrectionOperationSemanticPolicyKey(BaseModel):
    kind: Literal["correction"]
    corrected_predicate_id: str = Field(min_length=1)
    replacement_predicate_id: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RetractionOperationSemanticPolicyKey(BaseModel):
    kind: Literal["retraction"]
    retracted_predicate_id: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ActionStateOperationSemanticPolicyKey(BaseModel):
    kind: Literal["action_state"]
    logical_action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_id: str = Field(min_length=1)
    role_ids: tuple[str, ...]
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_roles(self):
        if not self.role_ids or len(set(self.role_ids)) != len(self.role_ids):
            raise ValueError("action policy key role ids must be nonempty and unique")
        return self


class IdentityOperationSemanticPolicyKey(BaseModel):
    kind: Literal["identity"]
    identity_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation: Literal["alias", "rekey", "merge", "split"]
    predecessor_mention_digests: tuple[str, ...]
    successor_mention_digests: tuple[str, ...]
    reference_assignment_digests: tuple[str, ...]
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_identity_key(self):
        for values in (
            self.predecessor_mention_digests,
            self.successor_mention_digests,
            self.reference_assignment_digests,
        ):
            if values != tuple(sorted(values)) or len(set(values)) != len(values):
                raise ValueError("identity policy key tuples must be canonical and unique")
        return self


OperationSemanticPolicyKey = Annotated[
    FactOperationSemanticPolicyKey
    | CorrectionOperationSemanticPolicyKey
    | RetractionOperationSemanticPolicyKey
    | ActionStateOperationSemanticPolicyKey
    | IdentityOperationSemanticPolicyKey,
    Field(discriminator="kind"),
]


class PredicateSemanticPolicyBinding(_ContentAddressedContract):
    role: Literal["fact", "corrected", "replacement", "retracted"]
    predicate_id: str = Field(min_length=1)
    policy: PredicateSemanticPolicy
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-semantic-policy-binding.v1"
    _digest_field = "binding_digest"

    @model_validator(mode="after")
    def validate_binding(self):
        if self.predicate_id != self.policy.predicate_id:
            raise ValueError("predicate policy binding predicate must match embedded policy")
        return self


class PreAlignmentSemanticOperationSubject(_ContentAddressedContract):
    kind: Literal["fact", "correction", "retraction", "action_state", "identity"]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_member_index: int = Field(ge=0)
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.pre-alignment-semantic-operation-subject.v1"
    _digest_field = "operation_id"


def expand_pre_alignment_subjects(proposal: SemanticProposal) -> tuple[PreAlignmentSemanticOperationSubject, ...]:
    if proposal.status == "abstained":
        return ()
    subjects: list[PreAlignmentSemanticOperationSubject] = []
    for kind, members in (
        ("fact", proposal.facts),
        ("correction", proposal.corrections),
        ("retraction", proposal.retractions),
        ("action_state", proposal.action_states),
        ("identity", proposal.identity_operations),
    ):
        for index, _member in enumerate(members):
            subjects.append(
                PreAlignmentSemanticOperationSubject.create(
                    kind=kind,
                    source_id=proposal.source_id,
                    source_digest=proposal.source_digest,
                    proposal_id=proposal.proposal_id,
                    proposal_digest=proposal.proposal_digest,
                    segment_id=proposal.segment_id,
                    segment_language_route_digest=proposal.language_route.route_digest,
                    proposal_member_index=index,
                )
            )
    if len({subject.operation_id for subject in subjects}) != len(subjects):
        raise ValueError("pre-alignment subjects must have unique operation ids")
    return tuple(subjects)


class PreAlignmentSemanticOperationSubjectSet(_ContentAddressedContract):
    """The only replayable authority for pre-alignment operation subjects."""

    proposal: SemanticProposal
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    subjects: tuple[PreAlignmentSemanticOperationSubject, ...]
    subject_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.pre-alignment-semantic-operation-subject-set.v1"
    _digest_field = "subject_set_digest"

    @model_validator(mode="after")
    def validate_subject_set(self) -> PreAlignmentSemanticOperationSubjectSet:
        expected = expand_pre_alignment_subjects(self.proposal)
        if (
            self.proposal_digest != self.proposal.proposal_digest
            or len({subject.operation_id for subject in self.subjects}) != len(self.subjects)
            or self.subjects != expected
        ):
            raise ValueError("pre-alignment subject set must be the exact proposal expansion")
        return self

    @classmethod
    def create(cls, *, proposal: SemanticProposal) -> PreAlignmentSemanticOperationSubjectSet:
        return super().create(
            proposal=proposal,
            proposal_digest=proposal.proposal_digest,
            subjects=expand_pre_alignment_subjects(proposal),
        )


class ParserOperationPolicyAuthority(_ContentAddressedContract):
    kind: Literal["parser_operation"]
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_consensus_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_policy_key: OperationSemanticPolicyKey
    predicate_policy_bindings: tuple[PredicateSemanticPolicyBinding, ...]
    construction_families: tuple[ConstructionFamily, ...]
    role_schemas: tuple[UdRoleSchema, ...]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.parser-operation-policy-authority.v1"
    _digest_field = "authority_digest"
    _create_static_values = {"kind": "parser_operation"}

    @model_validator(mode="after")
    def validate_authority(self):
        bindings = self.predicate_policy_bindings
        if isinstance(self.semantic_policy_key, FactOperationSemanticPolicyKey):
            expected = (("fact", self.semantic_policy_key.predicate_id),)
        elif isinstance(self.semantic_policy_key, CorrectionOperationSemanticPolicyKey):
            expected = (
                ("corrected", self.semantic_policy_key.corrected_predicate_id),
                ("replacement", self.semantic_policy_key.replacement_predicate_id),
            )
        elif isinstance(self.semantic_policy_key, RetractionOperationSemanticPolicyKey):
            expected = (("retracted", self.semantic_policy_key.retracted_predicate_id),)
        else:
            expected = ()
        actual = tuple((v.role, v.predicate_id) for v in bindings)
        if actual != expected:
            raise ValueError("parser authority predicate bindings must exactly match policy key roles")
        family_keys = tuple((v.family_id, v.family_digest) for v in self.construction_families)
        if family_keys != tuple(sorted(family_keys)) or len(set(family_keys)) != len(family_keys):
            raise ValueError("parser authority construction families must be canonical and unique")
        if isinstance(self.semantic_policy_key, ActionStateOperationSemanticPolicyKey):
            if tuple(v.role_id for v in self.role_schemas) != self.semantic_policy_key.role_ids:
                raise ValueError("action parser authority role schemas must exactly match role ids")
        else:
            role_keys = tuple((v.role_id, v.schema_digest) for v in self.role_schemas)
            if role_keys != tuple(sorted(role_keys)) or len({v.role_id for v in self.role_schemas}) != len(role_keys):
                raise ValueError("parser authority role schemas must be canonical and role-id unique")
        return self


class ScopeOperationPolicyAuthority(_ContentAddressedContract):
    kind: Literal["scope_operation"]
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_consensus_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_attachment_consensus_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_policy_key: OperationSemanticPolicyKey
    scope_policy: SemanticScopePolicy
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.scope-operation-policy-authority.v1"
    _digest_field = "authority_digest"
    _create_static_values = {"kind": "scope_operation"}


LanguageConstructionPolicyAuthority = Annotated[
    ParserOperationPolicyAuthority | ScopeOperationPolicyAuthority, Field(discriminator="kind")
]


class LanguageConstructionPolicyAuthorityBundle(_ContentAddressedContract):
    policies: tuple[LanguageConstructionPolicyAuthority, ...]
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.language-construction-policy-authority-bundle.v1"
    _digest_field = "bundle_digest"

    @model_validator(mode="after")
    def validate_bundle(self):
        groups: dict[tuple[str, str, str, str], tuple[LanguageConstructionPolicyAuthority, ...]] = {}
        for policy in self.policies:
            coordinate = (
                policy.operation_id,
                policy.proposal_id,
                policy.segment_id,
                policy.segment_language_route_digest,
            )
            groups[coordinate] = groups.get(coordinate, ()) + (policy,)
        coordinates = tuple(groups)
        if coordinates != tuple(sorted(coordinates)):
            raise ValueError("language construction authority groups must be canonical")
        for policies in groups.values():
            if (
                len(policies) != 2
                or not isinstance(policies[0], ParserOperationPolicyAuthority)
                or not isinstance(policies[1], ScopeOperationPolicyAuthority)
            ):
                raise ValueError("each language construction authority group requires parser then scope policy")
            parser, scope = policies
            if parser.semantic_policy_key != scope.semantic_policy_key:
                raise ValueError("parser and scope authorities must bind the same semantic policy key")
            if scope.scope_policy.construction_family not in parser.construction_families:
                raise ValueError("scope construction family must be present in parser authority")
            if any(
                binding.policy.language != scope.scope_policy.language for binding in parser.predicate_policy_bindings
            ):
                raise ValueError("predicate policy languages must match scope policy language")
        return self


class LinguisticFeature(_ContentAddressedContract):
    name: str = Field(min_length=1)
    value: str
    feature_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.linguistic-feature.v1"
    _digest_field = "feature_digest"


class SegmentAnalysisInput(_ContentAddressedContract):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_projection_segment_id: str
    segment_governance: SegmentGovernanceBinding
    message_admission_identity: MessageAdmissionIdentity | None
    governance_carrier_artifact: GovernanceCarrierArtifact
    context_text: SourceSpanReference
    segment_text: str
    language_route: SegmentLanguageRoute
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.segment-analysis-input.v1"
    _digest_field = "input_digest"

    @model_validator(mode="after")
    def validate_input(self) -> SegmentAnalysisInput:
        if (self.segment_governance.source_id, self.segment_governance.segment_id) != (
            self.source_id,
            self.parent_projection_segment_id,
        ) or (
            self.language_route.source_id,
            self.language_route.source_digest,
            self.language_route.segment_id,
            self.language_route.parent_projection_segment_id,
        ) != (self.source_id, self.source_digest, self.segment_id, self.parent_projection_segment_id):
            raise ValueError("analysis input must bind exact segment governance and route")
        if (
            self.context_text.source_id != self.source_id
            or self.context_text.projection_segment_id != self.parent_projection_segment_id
        ):
            raise ValueError("analysis input context must bind exact source segment")
        artifact = self.governance_carrier_artifact
        if (
            artifact.segment_governance.source_id != self.source_id
            or self.segment_governance not in artifact.segment_governance.bindings
            or (
                self.message_admission_identity is not None
                and self.message_admission_identity not in artifact.message_admissions.identities
            )
            or (
                self.message_admission_identity is not None
                and self.message_admission_identity.segment_governance_binding_digest
                != self.segment_governance.binding_digest
            )
        ):
            raise ValueError("analysis input governance artifact must contain its exact authorities")
        segment_artifact = self.context_text.segment_local_span.artifact
        if (
            self.language_route.segment_text_artifact_id != segment_artifact.artifact_id
            or self.language_route.segment_text_artifact_digest != segment_artifact.artifact_digest
            or self.language_route.segment_text_content_digest != segment_artifact.content_digest
        ):
            raise ValueError("analysis input context must bind the route segment artifact")
        return self


class AnalyzerManifest(_ContentAddressedContract):
    analyzer_id: str
    analyzer_kind: Literal["stanza", "spacy"]
    library_version: str
    resource_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_file_hashes: tuple[str, ...]
    processor_configuration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_version: str
    supported_languages: tuple[str, ...]
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.analyzer-manifest.v1"
    _digest_field = "manifest_digest"


class PredicateEventManifest(_ContentAddressedContract):
    language: str
    predicate_lemmas: tuple[str, ...]
    inflection_table_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    multi_token_forms: tuple[str, ...]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-event-manifest.v1"
    _digest_field = "manifest_digest"


class TemporalResolverManifest(_ContentAddressedContract):
    binary_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ruleset_version: str
    locale_map_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    timezone_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    supported_construction_families: tuple[str, ...]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.temporal-resolver-manifest.v1"
    _digest_field = "manifest_digest"


class LinguisticAnalysisRequest(_ContentAddressedContract):
    segment: SegmentAnalysisInput
    analyzer_manifest: AnalyzerManifest
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.linguistic-analysis-request.v1"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> LinguisticAnalysisRequest:
        binding = self.segment.language_route.resource_binding
        if (
            binding is None
            or self.segment.language_route.decision != "selected"
            or self.analyzer_manifest.manifest_digest
            != (
                binding.stanza_analyzer_manifest_digest
                if self.analyzer_manifest.analyzer_kind == "stanza"
                else binding.spacy_analyzer_manifest_digest
            )
            or self.segment.language_route.selected_language not in self.analyzer_manifest.supported_languages
        ):
            raise ValueError("linguistic request manifest must match selected route")
        return self


class PredicateEventDetectionRequest(_ContentAddressedContract):
    segment: SegmentAnalysisInput
    predicate_event_manifest: PredicateEventManifest
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-event-detection-request.v1"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> PredicateEventDetectionRequest:
        binding = self.segment.language_route.resource_binding
        if (
            binding is None
            or self.segment.language_route.decision != "selected"
            or self.predicate_event_manifest.manifest_digest != binding.predicate_event_manifest_digest
            or self.predicate_event_manifest.language != self.segment.language_route.selected_language
        ):
            raise ValueError("predicate request manifest must match selected route")
        return self


class TemporalResolutionRequest(_ContentAddressedContract):
    segment: SegmentAnalysisInput
    resolver_manifest: TemporalResolverManifest
    reference_evidence: TemporalReferenceEvidence | None
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.temporal-resolution-request.v1"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> TemporalResolutionRequest:
        binding = self.segment.language_route.resource_binding
        if (
            binding is None
            or self.segment.language_route.decision != "selected"
            or self.resolver_manifest.manifest_digest != binding.temporal_resolver_manifest_digest
        ):
            raise ValueError("temporal request manifest must match selected route")
        return self


class LinguisticToken(_ContentAddressedContract):
    source_span: SourceSpanReference
    surface_text: str
    lemma: str
    upos: str
    xpos: str | None
    morphological_features: tuple[LinguisticFeature, ...]
    sentence_index: int = Field(ge=0)
    word_index: int = Field(ge=0)
    syntactic_word_index: int | None
    multi_word_token_span: SourceSpanReference | None
    token_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.linguistic-token.v1"
    _digest_field = "token_id"

    @model_validator(mode="after")
    def validate_token(self) -> LinguisticToken:
        if self.morphological_features != tuple(
            sorted(self.morphological_features, key=lambda item: (item.name, item.value, item.feature_digest))
        ) or len({item.name for item in self.morphological_features}) != len(self.morphological_features):
            raise ValueError("token features must be canonical and unique")
        if self.syntactic_word_index is None and self.multi_word_token_span is None:
            raise ValueError("non-syntactic token requires multi-word span")
        if self.multi_word_token_span is not None and (
            self.multi_word_token_span.source_id != self.source_span.source_id
            or self.multi_word_token_span.projection_digest != self.source_span.projection_digest
            or not _reference_contains(self.multi_word_token_span, self.source_span)
        ):
            raise ValueError("token multi-word span must contain its token coordinate")
        if self.syntactic_word_index is None and self.multi_word_token_span != self.source_span:
            raise ValueError("multi-word surface token must name its exact token span")
        return self


class DependencyArc(_ContentAddressedContract):
    dependent_token_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    governor_token_id: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    relation: str = Field(min_length=1)
    enhanced: bool
    arc_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.dependency-arc.v1"
    _digest_field = "arc_id"


class SourceMention(_ContentAddressedContract):
    kind: Literal["named_entity", "noun_phrase", "pronoun", "predicate_argument", "coordinated_argument"]
    source_span: SourceSpanReference
    token_ids: tuple[str, ...]
    head_token_id: str
    entity_label: str | None
    coordination_group_id: str | None
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.source-mention.v1"
    _digest_field = "mention_digest"

    @model_validator(mode="after")
    def validate_mention(self) -> SourceMention:
        if (
            not self.token_ids
            or len(set(self.token_ids)) != len(self.token_ids)
            or self.head_token_id not in self.token_ids
        ):
            raise ValueError("source mention tokens must be unique and include head")
        if (self.kind == "named_entity") != (self.entity_label is not None) or (
            self.kind == "coordinated_argument"
        ) != (self.coordination_group_id is not None):
            raise ValueError("source mention optional fields must match kind")
        return self


class ClauseArgument(_ContentAddressedContract):
    grammatical_role: str = Field(min_length=1)
    head_token_id: str
    source_span: SourceSpanReference
    mention_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    argument_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.clause-argument.v1"
    _digest_field = "argument_digest"


class ClauseQuotationEvidence(_ContentAddressedContract):
    opening_token_id: str | None
    closing_token_id: str | None
    reporting_head_token_id: str | None
    complement_clause_id: str | None
    attribution_argument_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.clause-quotation-evidence.v1"
    _digest_field = "evidence_digest"

    @model_validator(mode="after")
    def validate_evidence(self) -> ClauseQuotationEvidence:
        if not any(
            (
                self.opening_token_id,
                self.closing_token_id,
                self.reporting_head_token_id,
                self.complement_clause_id,
                self.attribution_argument_digest,
            )
        ):
            raise ValueError("quotation evidence requires one cue")
        return self


class ClauseAnalysis(_ContentAddressedContract):
    source_span: SourceSpanReference
    parent_clause_id: str | None
    predicate_head_token_id: str
    predicate_span: SourceSpanReference
    arguments: tuple[ClauseArgument, ...]
    voice: Literal["active", "passive", "unknown"]
    negation_token_ids: tuple[str, ...]
    dependency_arc_ids: tuple[str, ...]
    morphological_polarity_features: tuple[LinguisticFeature, ...]
    mood_features: tuple[LinguisticFeature, ...]
    modality_features: tuple[LinguisticFeature, ...]
    quotation_evidence: ClauseQuotationEvidence | None
    coordination_group_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    clause_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.clause-analysis.v1"
    _digest_field = "clause_id"


_AnalysisStatus = Literal["complete", "partial", "evidence_only", "unsupported", "failed"]


class SegmentLanguageLaneOutcome(_ContentAddressedContract):
    lane: Literal["stanza", "spacy", "predicate_event_detection", "temporal_resolution"]
    segment_id: str = Field(min_length=1)
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_binding_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    selected_manifest_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    status: _AnalysisStatus
    artifact_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    reason_codes: tuple[str, ...]
    outcome_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.segment-language-lane-outcome.v1"
    _digest_field = "outcome_digest"

    @model_validator(mode="after")
    def validate_outcome(self) -> SegmentLanguageLaneOutcome:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))) or any(not item for item in self.reason_codes):
            raise ValueError("analysis lane reason codes must be canonical")
        if self.status in {"complete", "partial"} and self.artifact_digest is None:
            raise ValueError("artifact-bearing analysis status requires artifact")
        if self.status in {"failed", "unsupported"} and self.artifact_digest is not None:
            raise ValueError("failed or unsupported analysis forbids artifact")
        if self.status == "evidence_only" and any(
            value is not None
            for value in (self.resource_binding_digest, self.selected_manifest_digest, self.artifact_digest)
        ):
            raise ValueError("evidence-only analysis outcome has no selected resource")
        return self


def _validate_selected_lane_outcomes(
    routes: tuple[SegmentLanguageRoute, ...], outcomes: tuple[SegmentLanguageLaneOutcome, ...]
) -> None:
    """Bind every lane result to the immutable route-selected resource tuple."""
    expected_manifest_field = {
        "stanza": "stanza_analyzer_manifest_digest",
        "spacy": "spacy_analyzer_manifest_digest",
        "predicate_event_detection": "predicate_event_manifest_digest",
        "temporal_resolution": "temporal_resolver_manifest_digest",
    }
    route_by_segment = {route.segment_id: route for route in routes}
    for outcome in outcomes:
        route = route_by_segment.get(outcome.segment_id)
        if route is None or outcome.segment_language_route_digest != route.route_digest:
            raise ValueError("analysis lane outcome must bind an exact route")
        if route.decision != "selected":
            if outcome.status != "evidence_only":
                raise ValueError("blocked route lane outcome must be evidence-only")
            continue
        binding = route.resource_binding
        assert binding is not None  # guaranteed by SegmentLanguageRoute validation
        if (
            outcome.status == "evidence_only"
            or outcome.resource_binding_digest != binding.resource_binding_digest
            or outcome.selected_manifest_digest != getattr(binding, expected_manifest_field[outcome.lane])
        ):
            raise ValueError("selected route lane outcome must bind selected resource and manifest")


def _aggregate_status(outcomes: tuple[object, ...]) -> str:
    statuses = tuple(item.status for item in outcomes)  # type: ignore[attr-defined]
    if all(status == "evidence_only" for status in statuses):
        return "evidence_only"
    if "failed" in statuses:
        return "failed"
    if all(status in {"complete", "evidence_only"} for status in statuses) and "complete" in statuses:
        return "complete"
    if all(status in {"unsupported", "evidence_only"} for status in statuses) and "unsupported" in statuses:
        return "unsupported"
    return "partial"


def _segment_parser_status(outcomes: tuple[SegmentLanguageLaneOutcome, ...]) -> str:
    statuses = tuple(item.status for item in outcomes)
    if all(status == "evidence_only" for status in statuses):
        return "evidence_only"
    if all(status == "complete" for status in statuses):
        return "complete"
    if any(status in {"complete", "partial"} for status in statuses):
        return "partial"
    if "failed" in statuses:
        return "failed"
    if "unsupported" in statuses:
        return "unsupported"
    return "partial"


class LinguisticAnalysis(_ContentAddressedContract):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    analyzer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    language: str | None
    tokens: tuple[LinguisticToken, ...]
    mentions: tuple[SourceMention, ...]
    clauses: tuple[ClauseAnalysis, ...]
    dependencies: tuple[DependencyArc, ...]
    status: Literal["complete", "partial", "unsupported", "failed"]
    diagnostics: tuple[str, ...]
    analysis_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.linguistic-analysis.v1"
    _digest_field = "analysis_digest"

    @model_validator(mode="after")
    def validate_analysis(self) -> LinguisticAnalysis:
        token_ids = tuple(token.token_id for token in self.tokens)

        def token_key(token: LinguisticToken) -> tuple[int, int, int, str, str]:
            return (
                token.sentence_index,
                token.word_index,
                token.syntactic_word_index if token.syntactic_word_index is not None else -1,
                token.source_span.reference_digest,
                token.token_id,
            )

        if token_ids != tuple(token.token_id for token in sorted(self.tokens, key=token_key)) or len(
            set(token_ids)
        ) != len(token_ids):
            raise ValueError("analysis tokens must be uniquely source ordered")
        if len({(token.sentence_index, token.word_index, token.syntactic_word_index) for token in self.tokens}) != len(
            self.tokens
        ):
            raise ValueError("analysis token coordinates must be unique")
        if any(token.source_span.source_id != self.source_id for token in self.tokens):
            raise ValueError("analysis token spans must bind exact source and segment")
        token_set = set(token_ids)
        if any(
            arc.dependent_token_id not in token_set
            or arc.governor_token_id is not None
            and arc.governor_token_id not in token_set
            for arc in self.dependencies
        ):
            raise ValueError("dependency endpoints must resolve to analysis tokens")
        basic = tuple(arc for arc in self.dependencies if not arc.enhanced)
        syntactic = tuple(token for token in self.tokens if token.syntactic_word_index is not None)
        token_by_id = {token.token_id: token for token in self.tokens}

        def arc_key(
            arc: DependencyArc,
        ) -> tuple[tuple[int, int, int, str, str], bool, str, tuple[int, int, int, str, str], str]:
            return (
                token_key(token_by_id[arc.dependent_token_id]),
                arc.enhanced,
                arc.relation,
                (-1, -1, -1, "", "")
                if arc.governor_token_id is None
                else token_key(token_by_id[arc.governor_token_id]),
                arc.arc_id,
            )

        if (
            self.dependencies != tuple(sorted(self.dependencies, key=arc_key))
            or len({arc.arc_id for arc in self.dependencies}) != len(self.dependencies)
            or len(
                {
                    (arc.dependent_token_id, arc.governor_token_id, arc.relation, arc.enhanced)
                    for arc in self.dependencies
                }
            )
            != len(self.dependencies)
            or {arc.dependent_token_id for arc in basic} != {token.token_id for token in syntactic}
            or len(basic) != len(syntactic)
            or sum(arc.governor_token_id is None and arc.relation == "root" for arc in basic) != 1
            or any((arc.governor_token_id is None) != (arc.relation == "root") for arc in basic)
        ):
            raise ValueError("analysis basic dependencies must form one rooted tree")
        if any(
            set(mention.token_ids) - token_set
            or mention.source_span.source_id != self.source_id
            or any(
                not _reference_contains(mention.source_span, token_by_id[token_id].source_span)
                for token_id in mention.token_ids
            )
            or tuple(mention.token_ids)
            != tuple(sorted(mention.token_ids, key=lambda item: token_key(token_by_id[item])))
            for mention in self.mentions
        ):
            raise ValueError("source mentions must reference analysis tokens")
        if self.mentions != tuple(
            sorted(self.mentions, key=lambda item: (item.source_span.reference_digest, item.kind, item.mention_digest))
        ):
            raise ValueError("source mentions must be canonical")
        arc_ids = {arc.arc_id for arc in self.dependencies}
        arc_by_id = {arc.arc_id: arc for arc in self.dependencies}
        mention_ids = {mention.mention_digest for mention in self.mentions}
        clause_ids = {clause.clause_id for clause in self.clauses}
        if len(clause_ids) != len(self.clauses):
            raise ValueError("analysis clauses must be unique")
        clause_by_id = {clause.clause_id: clause for clause in self.clauses}
        for clause in self.clauses:
            if clause.parent_clause_id is not None and clause.parent_clause_id not in clause_ids:
                raise ValueError("clause parent must resolve in analysis")
            if (
                clause.source_span.source_id != self.source_id
                or clause.predicate_span.source_id != self.source_id
                or clause.predicate_head_token_id not in token_set
                or not _reference_contains(
                    clause.predicate_span, token_by_id[clause.predicate_head_token_id].source_span
                )
                or set(clause.dependency_arc_ids) - arc_ids
                or len(set(clause.dependency_arc_ids)) != len(clause.dependency_arc_ids)
                or len(set(clause.negation_token_ids)) != len(clause.negation_token_ids)
                or set(clause.negation_token_ids) - token_set
                or len(set(clause.coordination_group_ids)) != len(clause.coordination_group_ids)
                or len(set(clause.limitations)) != len(clause.limitations)
                or clause.limitations != tuple(sorted(clause.limitations))
            ):
                raise ValueError("clause token and arc references must resolve")
            if any(
                argument.head_token_id not in token_set
                or argument.mention_digest is not None
                and argument.mention_digest not in mention_ids
                or argument.source_span.source_id != self.source_id
                or not _reference_contains(clause.source_span, argument.source_span)
                for argument in clause.arguments
            ):
                raise ValueError("clause argument references must resolve")
            if (
                clause.arguments
                != tuple(
                    sorted(
                        clause.arguments,
                        key=lambda item: (
                            item.source_span.reference_digest,
                            item.grammatical_role,
                            item.argument_digest,
                        ),
                    )
                )
                or len({argument.argument_digest for argument in clause.arguments}) != len(clause.arguments)
                or clause.negation_token_ids
                != tuple(sorted(clause.negation_token_ids, key=lambda item: token_key(token_by_id[item])))
                or clause.dependency_arc_ids
                != tuple(sorted(clause.dependency_arc_ids, key=lambda item: arc_key(arc_by_id[item])))
                or any(
                    features != tuple(sorted(features, key=lambda item: (item.name, item.value, item.feature_digest)))
                    or len({item.name for item in features}) != len(features)
                    for features in (
                        clause.morphological_polarity_features,
                        clause.mood_features,
                        clause.modality_features,
                    )
                )
                or clause.coordination_group_ids != tuple(sorted(clause.coordination_group_ids))
            ):
                raise ValueError("clause members must be canonical")
            if not _reference_contains(clause.source_span, clause.predicate_span):
                raise ValueError("clause predicate span must be contained")
            quotation = clause.quotation_evidence
            if quotation is not None and (
                any(
                    token_id is not None and token_id not in token_set
                    for token_id in (
                        quotation.opening_token_id,
                        quotation.closing_token_id,
                        quotation.reporting_head_token_id,
                    )
                )
                or quotation.complement_clause_id is not None
                and quotation.complement_clause_id not in clause_ids
                or quotation.attribution_argument_digest is not None
                and quotation.attribution_argument_digest
                not in {argument.argument_digest for argument in clause.arguments}
                or quotation.opening_token_id is not None
                and quotation.closing_token_id is not None
                and token_key(token_by_id[quotation.opening_token_id])
                >= token_key(token_by_id[quotation.closing_token_id])
            ):
                raise ValueError("quotation evidence references must resolve in clause")
        for clause in self.clauses:
            parent_id = clause.parent_clause_id
            visited = {clause.clause_id}
            while parent_id is not None:
                if (
                    parent_id in visited
                    or not _reference_contains(clause_by_id[parent_id].source_span, clause.source_span)
                    or clause_by_id[parent_id].source_span == clause.source_span
                ):
                    raise ValueError("clause parents must be acyclic and strictly containing")
                visited.add(parent_id)
                parent_id = clause_by_id[parent_id].parent_clause_id
        # Exact token surface and temporal text slicing is deliberately checked
        # at SourceNormalizationRequest against retained PreparedSource bytes.
        return self


class PredicateEventCandidate(_ContentAddressedContract):
    event_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_family: str
    lexical_anchor_span: SourceSpanReference
    morphology_evidence_spans: tuple[SourceSpanReference, ...]
    detection_rule_id: str
    detection_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-event-candidate.v1"
    _digest_field = "candidate_digest"

    @model_validator(mode="after")
    def validate_candidate(self) -> PredicateEventCandidate:
        identity = {
            name: getattr(self, name)
            for name in (
                "segment_id",
                "preparation_fingerprint",
                "segment_language_route_digest",
                "predicate_family",
                "lexical_anchor_span",
                "detection_rule_id",
                "detection_manifest_fingerprint",
            )
        }
        if self.event_id != contract_digest(b"memorii.semantic-ingestion.predicate-event-identity.v1", identity):
            raise ValueError("predicate event identity mismatch")
        return self


class PredicateEventInventory(_ContentAddressedContract):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_routes: SegmentLanguageRouteSet
    segment_outcomes: tuple[SegmentLanguageLaneOutcome, ...]
    candidates: tuple[PredicateEventCandidate, ...]
    status: _AnalysisStatus
    inventory_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-event-inventory.v1"
    _digest_field = "inventory_fingerprint"

    @model_validator(mode="after")
    def validate_inventory(self) -> PredicateEventInventory:
        routes = self.segment_language_routes.routes
        if (
            self.source_id != self.segment_language_routes.source_id
            or self.source_digest != self.segment_language_routes.source_digest
        ):
            raise ValueError("predicate inventory source must match route set")
        if tuple((item.lane, item.segment_id) for item in self.segment_outcomes) != tuple(
            ("predicate_event_detection", route.segment_id) for route in routes
        ):
            raise ValueError("predicate inventory outcomes must be exact route bijection")
        if self.status != _aggregate_status(self.segment_outcomes):
            raise ValueError("predicate inventory status must be derived")
        if any(item.preparation_fingerprint != self.preparation_fingerprint for item in self.segment_outcomes):
            raise ValueError("predicate inventory preparation fingerprint must join every lane outcome")
        route_order = {route.segment_id: index for index, route in enumerate(routes)}
        if self.candidates != tuple(
            sorted(
                self.candidates,
                key=lambda item: (
                    route_order.get(item.segment_id, -1),
                    item.lexical_anchor_span.reference_digest,
                    item.predicate_family,
                    item.candidate_digest,
                ),
            )
        ):
            raise ValueError("predicate candidates must be canonical")
        outcomes = {item.segment_id: item for item in self.segment_outcomes}
        _validate_selected_lane_outcomes(routes, self.segment_outcomes)
        if any(
            candidate.preparation_fingerprint != self.preparation_fingerprint
            or candidate.segment_id not in outcomes
            or candidate.segment_language_route_digest
            != next(route.route_digest for route in routes if route.segment_id == candidate.segment_id)
            or outcomes[candidate.segment_id].preparation_fingerprint != self.preparation_fingerprint
            or outcomes[candidate.segment_id].artifact_digest is None
            or candidate.detection_manifest_fingerprint != outcomes[candidate.segment_id].selected_manifest_digest
            for candidate in self.candidates
        ):
            raise ValueError("predicate candidates must join their artifact-bearing route outcome")
        for candidate in self.candidates:
            route = next(route for route in routes if route.segment_id == candidate.segment_id)
            _validate_route_span(candidate.lexical_anchor_span, route, self.source_id)
            for span in candidate.morphology_evidence_spans:
                _validate_route_span(span, route, self.source_id)
        if any(
            candidate.morphology_evidence_spans
            != tuple(sorted(candidate.morphology_evidence_spans, key=lambda span: span.reference_digest))
            or len(set(candidate.morphology_evidence_spans)) != len(candidate.morphology_evidence_spans)
            for candidate in self.candidates
        ):
            raise ValueError("predicate candidate morphology spans must be canonical")
        return self


class ResolvedTemporalCandidate(_ContentAddressedContract):
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_span: SourceSpanReference
    exact_text: str
    value_kind: Literal["instant", "interval", "duration"]
    normalized_interval: TimeInterval | None
    normalized_duration: timedelta | None
    grain: str
    locale: str
    timezone: str
    reference_evidence: TemporalReferenceEvidence | None
    resolver_rule_id: str
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.resolved-temporal-candidate.v1"
    _digest_field = "candidate_digest"

    @model_validator(mode="after")
    def validate_candidate(self) -> ResolvedTemporalCandidate:
        if self.value_kind == "duration":
            if self.normalized_duration is None or self.normalized_interval is not None:
                raise ValueError("duration requires only duration value")
        elif self.normalized_interval is None or self.normalized_duration is not None:
            raise ValueError("instant or interval requires only interval value")
        elif (self.value_kind == "instant") != (self.normalized_interval.end is None):
            raise ValueError("temporal interval end must match value kind")
        identity = {
            name: getattr(self, name)
            for name in (
                "segment_id",
                "preparation_fingerprint",
                "segment_language_route_digest",
                "source_span",
                "value_kind",
                "normalized_interval",
                "normalized_duration",
                "grain",
                "locale",
                "timezone",
                "reference_evidence",
                "resolver_rule_id",
            )
        }
        if self.candidate_id != contract_digest(
            b"memorii.semantic-ingestion.resolved-temporal-candidate-identity.v1", identity
        ):
            raise ValueError("temporal candidate identity mismatch")
        return self


class TemporalResolution(_ContentAddressedContract):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_routes: SegmentLanguageRouteSet
    segment_outcomes: tuple[SegmentLanguageLaneOutcome, ...]
    candidates: tuple[ResolvedTemporalCandidate, ...]
    ambiguous_spans: tuple[SourceSpanReference, ...]
    status: _AnalysisStatus
    resolver_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostics: tuple[str, ...]
    _digest_domain = b"memorii.semantic-ingestion.temporal-resolution.v1"
    _digest_field = "resolver_fingerprint"

    @model_validator(mode="after")
    def validate_resolution(self) -> TemporalResolution:
        routes = self.segment_language_routes.routes
        if (
            self.source_id != self.segment_language_routes.source_id
            or self.source_digest != self.segment_language_routes.source_digest
        ):
            raise ValueError("temporal resolution source must match route set")
        if tuple((item.lane, item.segment_id) for item in self.segment_outcomes) != tuple(
            ("temporal_resolution", route.segment_id) for route in routes
        ):
            raise ValueError("temporal resolution outcomes must be exact route bijection")
        if self.status != _aggregate_status(self.segment_outcomes):
            raise ValueError("temporal resolution status must be derived")
        if any(item.preparation_fingerprint != self.preparation_fingerprint for item in self.segment_outcomes):
            raise ValueError("temporal resolution preparation fingerprint must join every lane outcome")
        _validate_selected_lane_outcomes(routes, self.segment_outcomes)
        route_by_segment = {route.segment_id: route for route in routes}
        outcomes_by_segment = {outcome.segment_id: outcome for outcome in self.segment_outcomes}
        if any(
            candidate.preparation_fingerprint != self.preparation_fingerprint
            or candidate.segment_id not in route_by_segment
            or candidate.segment_language_route_digest != route_by_segment[candidate.segment_id].route_digest
            or outcomes_by_segment[candidate.segment_id].preparation_fingerprint != self.preparation_fingerprint
            or outcomes_by_segment[candidate.segment_id].artifact_digest is None
            for candidate in self.candidates
        ):
            raise ValueError("temporal candidates must join an artifact-bearing exact route outcome")
        for candidate in self.candidates:
            _validate_route_span(candidate.source_span, route_by_segment[candidate.segment_id], self.source_id)
            if (
                len(candidate.exact_text)
                != candidate.source_span.segment_local_span.end - candidate.source_span.segment_local_span.start
                or sha256(candidate.exact_text.encode("utf-8")).hexdigest()
                != candidate.source_span.segment_local_span.substring_digest
            ):
                raise ValueError("temporal candidate text must equal its exact source span")
        keys = [
            (
                candidate.source_span.reference_digest
                if hasattr(candidate.source_span, "reference_digest")
                else candidate.source_span.span_digest,
                candidate.value_kind,
                candidate.normalized_interval,
                candidate.normalized_duration,
                candidate.grain,
                candidate.locale,
                candidate.timezone,
                candidate.reference_evidence,
            )
            for candidate in self.candidates
        ]
        if len(set(map(repr, keys))) != len(keys):
            raise ValueError("temporal resolution candidates must have unique value and basis")
        route_order = {route.segment_id: index for index, route in enumerate(routes)}
        if self.candidates != tuple(
            sorted(
                self.candidates,
                key=lambda item: (
                    route_order.get(item.segment_id, -1),
                    item.source_span.reference_digest,
                    item.candidate_digest,
                ),
            )
        ):
            raise ValueError("temporal candidates must be canonical")
        expected_ambiguous = tuple(
            sorted(
                {
                    candidate.source_span
                    for candidate in self.candidates
                    if sum(other.source_span == candidate.source_span for other in self.candidates) > 1
                },
                key=lambda item: item.reference_digest,
            )
        )
        if self.ambiguous_spans != expected_ambiguous:
            raise ValueError("temporal ambiguous spans must be derived from retained candidates")
        return self


SourceSemanticContext.model_rebuild()
SegmentLanguageRoute.model_rebuild()
BootstrapDeclaredSegmentLanguageRoute.model_rebuild()




# V3 recovery is intentionally independent of the retired request/context
# shape above.  The immutable key names work; the short lived claim authorizes
# exactly one publication attempt.
class BootstrapRecoveryKeyV3(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    operation_fence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_profile_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    handoff_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_key(self) -> BootstrapRecoveryKeyV3:
        if self.recovery_key_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-key.v3",
            self.model_dump(mode="python", exclude={"recovery_key_digest"}),
        ):
            raise ValueError("bootstrap recovery key digest mismatch")
        return self


class BootstrapNormalizationReadyControlRecordV3(BaseModel):
    """The store-owned, generation-two recovery authority.

    It deliberately contains neither provider output nor a claim.  Those are
    derived after this record has been sealed, preventing a recovery retry from
    smuggling caller-selected publication state into the durable control plane.
    """

    schema_version: Literal[3]
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    handoff_marker_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    operation_fence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_operation_generation: int = Field(ge=1)
    predecessor_artifact_generation: int = Field(ge=1)
    predecessor_control_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_generation: int = Field(ge=1)
    artifact_generation: int = Field(ge=1)
    transition: Literal["post_handoff_normalization_ready"]
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    progress_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_control_record(self) -> BootstrapNormalizationReadyControlRecordV3:
        if (
            self.operation_generation != self.predecessor_operation_generation + 1
            or self.artifact_generation != self.predecessor_artifact_generation + 1
            or self.operation_lease_binding.operation_fence_binding.binding_digest != self.operation_fence_digest
            or self.control_record_digest != contract_digest(
                b"memorii.semantic-ingestion.bootstrap-normalization-ready-control-record.v3",
                self.model_dump(mode="python", exclude={"control_record_digest"}),
            )
        ):
            raise ValueError("bootstrap normalization-ready control record is invalid")
        return self


class BootstrapRecoveryControlSnapshotV3(BaseModel):
    control_record: BootstrapNormalizationReadyControlRecordV3
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_snapshot(self) -> BootstrapRecoveryControlSnapshotV3:
        if self.snapshot_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-control-snapshot.v3",
            {"control_record": self.control_record},
        ):
            raise ValueError("bootstrap recovery control snapshot digest mismatch")
        return self


class BootstrapRecoveryClaimV3(BaseModel):
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    handoff_marker_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_snapshot: BootstrapRecoveryControlSnapshotV3
    claim_nonce: str = Field(min_length=1)
    issued_server_time: datetime
    expires_server_time: datetime
    issued_monotonic_tick: int = Field(ge=0)
    expires_monotonic_tick: int = Field(ge=1)
    renewal_count: int = Field(ge=0)
    max_claim_renewals: int = Field(ge=0)
    max_claim_total_duration_ticks: int = Field(ge=1)
    claim_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_claim(self) -> BootstrapRecoveryClaimV3:
        if (
            self.expires_server_time <= self.issued_server_time
            or self.expires_monotonic_tick <= self.issued_monotonic_tick
            or self.renewal_count > self.max_claim_renewals
            or self.expires_monotonic_tick - self.issued_monotonic_tick > self.max_claim_total_duration_ticks
        ):
            raise ValueError("bootstrap recovery claim lifetime is invalid")
        if self.claim_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-claim.v3",
            self.model_dump(mode="python", exclude={"claim_digest"}),
        ):
            raise ValueError("bootstrap recovery claim digest mismatch")
        return self

    @property
    def expected_operation_generation(self) -> int:
        """Compatibility accessor; authority is always the sealed snapshot."""
        return self.control_snapshot.control_record.operation_generation

    @property
    def expected_artifact_generation(self) -> int:
        return self.control_snapshot.control_record.artifact_generation


class BootstrapRecoveryProbeV3(BaseModel):
    recovery_key: BootstrapRecoveryKeyV3
    handoff_marker_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_predecessor_operation_generation: int = Field(ge=1)
    expected_predecessor_artifact_generation: int = Field(ge=1)
    expected_predecessor_control_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    probe_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_probe(self) -> BootstrapRecoveryProbeV3:
        if self.probe_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-probe.v3",
            self.model_dump(mode="python", exclude={"probe_digest"}),
        ):
            raise ValueError("bootstrap recovery probe digest mismatch")
        return self


class BootstrapRecoveryFoundV3(BaseModel):
    kind: Literal["found"]
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    consumed_claim_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    recovery_control_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_operation_generation: int = Field(ge=1)
    predecessor_artifact_generation: int = Field(ge=1)
    publication_operation_generation: int = Field(ge=1)
    publication_artifact_generation: int = Field(ge=1)
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class BootstrapRecoveryClaimedV3(BaseModel):
    kind: Literal["claimed"]
    claim: BootstrapRecoveryClaimV3
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class BootstrapRecoveryUnavailableV3(BaseModel):
    kind: Literal["unavailable"]
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal["invalid_probe", "stale_predecessor", "invalid_control_transition", "stale_control_snapshot", "lease_unavailable", "writer_unavailable", "foreign_live_claim", "storage_unavailable", "index_corrupt"]
    reason_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


BootstrapRecoveryProbeResultV3: TypeAlias = Annotated[
    BootstrapRecoveryFoundV3 | BootstrapRecoveryClaimedV3 | BootstrapRecoveryUnavailableV3,
    Field(discriminator="kind"),
]


class BootstrapRecoveryRenewedV3(BaseModel):
    kind: Literal["renewed"]
    claim: BootstrapRecoveryClaimV3
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class BootstrapRecoveryAbortedV3(BaseModel):
    kind: Literal["aborted"]
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal["expired", "foreign", "consumed", "snapshot_substituted", "control_advanced", "lease_expired", "writer_superseded", "clock_regressed", "renewal_bound"]
    reason_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


BootstrapRecoveryRenewalResultV3: TypeAlias = Annotated[
    BootstrapRecoveryRenewedV3 | BootstrapRecoveryAbortedV3,
    Field(discriminator="kind"),
]


class BootstrapAnalysisRouteBinding(BaseModel):
    """Host-certified resource authority for one persisted bootstrap route."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    parent_projection_segment_id: str = Field(min_length=1)
    bootstrap_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_text_artifact_id: str = Field(min_length=1)
    segment_text_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_text_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_language: str = Field(min_length=1)
    resource_binding: SegmentLanguageResourceBinding
    proposal_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    stanza_analyzer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    spacy_analyzer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_resolver_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_binding(self) -> BootstrapAnalysisRouteBinding:
        if (
            self.resource_binding.selected_language != self.selected_language
            or self.resource_binding.resource_binding_digest != self.resource_binding_digest
            or self.resource_binding.proposal_capability_fingerprint != self.proposal_capability_fingerprint
            or self.resource_binding.stanza_analyzer_manifest_digest != self.stanza_analyzer_manifest_digest
            or self.resource_binding.spacy_analyzer_manifest_digest != self.spacy_analyzer_manifest_digest
            or self.resource_binding.predicate_event_manifest_digest != self.predicate_event_manifest_digest
            or self.resource_binding.temporal_resolver_manifest_digest != self.temporal_resolver_manifest_digest
        ):
            raise ValueError("bootstrap analysis binding resource authority is substituted")
        if self.binding_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-analysis-route-binding.v1",
            self.model_dump(mode="python", exclude={"binding_digest"}),
        ):
            raise ValueError("bootstrap analysis route binding digest mismatch")
        return self

    @property
    def resource_binding_digest(self) -> str:
        return self.resource_binding.resource_binding_digest


class BootstrapAnalysisRouteBindingSet(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bindings: tuple[BootstrapAnalysisRouteBinding, ...]
    binding_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_set(self) -> BootstrapAnalysisRouteBindingSet:
        # An empty set is the exact authority for a wholly generic source.  A
        # bootstrap source is required to supply a total, source-ordered set by
        # the derivation-authority join; this value itself has no PreparedSource
        # to use as an ambient ordering oracle.
        if len({item.segment_id for item in self.bindings}) != len(self.bindings) or any(
            (item.source_id, item.source_digest, item.preparation_fingerprint)
            != (self.source_id, self.source_digest, self.preparation_fingerprint)
            for item in self.bindings
        ):
            raise ValueError("bootstrap analysis bindings must be source ordered")
        if self.binding_set_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-analysis-route-binding-set.v1",
            self.model_dump(mode="python", exclude={"binding_set_digest"}),
        ):
            raise ValueError("bootstrap analysis route binding set digest mismatch")
        return self


class BootstrapAnalysisProvenanceV1(BaseModel):
    """Flattened bootstrap-only durable route provenance."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    stanza_analyzer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    spacy_analyzer_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_resolver_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_provenance(self) -> BootstrapAnalysisProvenanceV1:
        if _digest_verification_hit(self, self.provenance_digest):
            return self
        if self.provenance_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-analysis-provenance.v1",
            self.model_dump(mode="python", exclude={"provenance_digest"}),
        ):
            raise ValueError("bootstrap analysis provenance digest mismatch")
        _record_digest_verification(self, self.provenance_digest)
        return self

    @classmethod
    def from_binding(cls, binding: BootstrapAnalysisRouteBinding) -> BootstrapAnalysisProvenanceV1:
        """Flatten one host-issued binding without consulting ambient state."""
        body = {
            "source_id": binding.source_id,
            "source_digest": binding.source_digest,
            "preparation_fingerprint": binding.preparation_fingerprint,
            "segment_id": binding.segment_id,
            "bootstrap_route_digest": binding.bootstrap_route_digest,
            "binding_digest": binding.binding_digest,
            "resource_binding_digest": binding.resource_binding_digest,
            "proposal_capability_fingerprint": binding.proposal_capability_fingerprint,
            "stanza_analyzer_manifest_digest": binding.stanza_analyzer_manifest_digest,
            "spacy_analyzer_manifest_digest": binding.spacy_analyzer_manifest_digest,
            "predicate_event_manifest_digest": binding.predicate_event_manifest_digest,
            "temporal_resolver_manifest_digest": binding.temporal_resolver_manifest_digest,
        }
        return cls(
            **body,
            provenance_digest=contract_digest(b"memorii.semantic-ingestion.bootstrap-analysis-provenance.v1", body),
        )


class BootstrapAnalysisRouteProjection(_ContentAddressedContract):
    """Ephemeral join of a declared bootstrap route and host lane authority.

    This is deliberately not a ``SegmentLanguageRoute``.  It exists only while
    materializing proposal and local-analysis requests; durable artifacts carry
    the flattened provenance below instead.
    """

    bootstrap_route: BootstrapDeclaredSegmentLanguageRoute
    binding: BootstrapAnalysisRouteBinding
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analysis-route-projection.v1"
    _digest_field = "projection_digest"

    @model_validator(mode="after")
    def validate_projection(self) -> BootstrapAnalysisRouteProjection:
        route, binding, provenance = (
            self.bootstrap_route,
            self.binding,
            self.bootstrap_analysis_provenance,
        )
        if (
            (
                binding.source_id,
                binding.source_digest,
                binding.segment_id,
                binding.parent_projection_segment_id,
                binding.bootstrap_route_digest,
            )
            != (
                route.source_id,
                route.source_digest,
                route.segment_id,
                route.parent_projection_segment_id,
                route.route_digest,
            )
            or binding.selected_language != route.declared_language
            or (
                provenance.source_id,
                provenance.source_digest,
                provenance.preparation_fingerprint,
                provenance.segment_id,
                provenance.bootstrap_route_digest,
                provenance.binding_digest,
                provenance.resource_binding_digest,
                provenance.proposal_capability_fingerprint,
                provenance.stanza_analyzer_manifest_digest,
                provenance.spacy_analyzer_manifest_digest,
                provenance.predicate_event_manifest_digest,
                provenance.temporal_resolver_manifest_digest,
            )
            != (
                binding.source_id,
                binding.source_digest,
                binding.preparation_fingerprint,
                binding.segment_id,
                binding.bootstrap_route_digest,
                binding.binding_digest,
                binding.resource_binding_digest,
                binding.proposal_capability_fingerprint,
                binding.stanza_analyzer_manifest_digest,
                binding.spacy_analyzer_manifest_digest,
                binding.predicate_event_manifest_digest,
                binding.temporal_resolver_manifest_digest,
            )
        ):
            raise ValueError("bootstrap analysis projection authority is substituted")
        return self


class BootstrapSegmentAnalysisInputV3(_ContentAddressedContract):
    """V3 request-local input for one declared bootstrap segment.

    It intentionally has no generic route field.  The sole route authority is
    the transient projection and the retained scalar provenance.
    """

    schema_version: Literal[3]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    parent_projection_segment_id: str = Field(min_length=1)
    segment_governance: SegmentGovernanceBinding
    message_admission_identity: MessageAdmissionIdentity | None
    governance_carrier_artifact: GovernanceCarrierArtifact
    context_text: SourceSpanReference
    segment_text: str
    bootstrap_projection: BootstrapAnalysisRouteProjection
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-segment-analysis-input.v3"
    _digest_field = "input_digest"

    @model_validator(mode="after")
    def validate_input(self) -> BootstrapSegmentAnalysisInputV3:
        projection = self.bootstrap_projection
        route = projection.bootstrap_route
        provenance = self.bootstrap_analysis_provenance
        if (
            projection.bootstrap_analysis_provenance != provenance
            or (
                self.source_id,
                self.source_digest,
                self.preparation_fingerprint,
                self.segment_id,
                self.parent_projection_segment_id,
            )
            != (
                route.source_id,
                route.source_digest,
                provenance.preparation_fingerprint,
                route.segment_id,
                route.parent_projection_segment_id,
            )
            or self.segment_governance.segment_id != route.parent_projection_segment_id
            or self.context_text.projection_segment_id != route.parent_projection_segment_id
            or self.context_text.segment_local_span.artifact.artifact_id != route.segment_text_artifact_id
            or self.context_text.segment_local_span.artifact.artifact_digest != route.segment_text_artifact_digest
            or self.context_text.segment_local_span.artifact.content_digest != route.segment_text_content_digest
        ):
            raise ValueError("bootstrap V3 analysis input authority is substituted")
        return self


class BootstrapSemanticProposalRequestV3(_ContentAddressedContract):
    """V3 bootstrap proposal request; generic request bytes are never reused."""

    schema_version: Literal[3]
    segment: BootstrapSegmentAnalysisInputV3
    semantic_context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_egress_decision_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_catalog: PredicateProposalCatalog
    action_proposal_catalog: ActionProposalCatalog
    registered_prompt: RegisteredSemanticPromptBinding
    proposer_manifest: SemanticProposerManifest
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-semantic-proposal-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> BootstrapSemanticProposalRequestV3:
        if (
            self.bootstrap_analysis_provenance != self.segment.bootstrap_analysis_provenance
            or self.proposal_capability_fingerprint
            != self.bootstrap_analysis_provenance.proposal_capability_fingerprint
            or self.predicate_catalog.proposal_capability_fingerprint != self.proposal_capability_fingerprint
            or self.action_proposal_catalog.proposal_capability_fingerprint != self.proposal_capability_fingerprint
            or self.proposer_manifest.structured_output_capability_fingerprint != self.proposal_capability_fingerprint
            or self.semantic_context_fingerprint != self.segment.segment_governance.message_semantic_context_digest
        ):
            raise ValueError("bootstrap V3 proposal request authority is substituted")
        return self


class BootstrapLinguisticAnalysisRequestV3(_ContentAddressedContract):
    schema_version: Literal[3]
    segment: BootstrapSegmentAnalysisInputV3
    analyzer_manifest: AnalyzerManifest
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-linguistic-analysis-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> BootstrapLinguisticAnalysisRequestV3:
        provenance = self.bootstrap_analysis_provenance
        if (
            self.segment.bootstrap_analysis_provenance != provenance
            or self.analyzer_manifest.manifest_digest
            != (
                provenance.stanza_analyzer_manifest_digest
                if self.analyzer_manifest.analyzer_kind == "stanza"
                else provenance.spacy_analyzer_manifest_digest
            )
            or self.segment.bootstrap_projection.bootstrap_route.declared_language
            not in self.analyzer_manifest.supported_languages
        ):
            raise ValueError("bootstrap V3 linguistic manifest is substituted")
        return self


class BootstrapPredicateEventDetectionRequestV3(_ContentAddressedContract):
    schema_version: Literal[3]
    segment: BootstrapSegmentAnalysisInputV3
    predicate_event_manifest: PredicateEventManifest
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-predicate-event-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> BootstrapPredicateEventDetectionRequestV3:
        if (
            self.segment.bootstrap_analysis_provenance != self.bootstrap_analysis_provenance
            or self.predicate_event_manifest.manifest_digest
            != self.bootstrap_analysis_provenance.predicate_event_manifest_digest
            or self.predicate_event_manifest.language
            != self.segment.bootstrap_projection.bootstrap_route.declared_language
        ):
            raise ValueError("bootstrap V3 predicate manifest is substituted")
        return self


class BootstrapTemporalResolutionRequestV3(_ContentAddressedContract):
    schema_version: Literal[3]
    segment: BootstrapSegmentAnalysisInputV3
    resolver_manifest: TemporalResolverManifest
    reference_evidence: TemporalReferenceEvidence | None
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-temporal-resolution-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> BootstrapTemporalResolutionRequestV3:
        if (
            self.segment.bootstrap_analysis_provenance != self.bootstrap_analysis_provenance
            or self.resolver_manifest.manifest_digest
            != self.bootstrap_analysis_provenance.temporal_resolver_manifest_digest
        ):
            raise ValueError("bootstrap V3 temporal manifest is substituted")
        return self


# Bootstrap V3 deliberately has its own proposal algebra.  These contracts do
# not wrap the generic proposal objects: doing so would make a bootstrap route
# look like a generic classifier route during recovery.
class _BootstrapV3Contract(_ContentAddressedContract):
    schema_version: Literal[3]

    @classmethod
    def create(cls, **values: object):  # type: ignore[no-untyped-def]
        if not cls.__pydantic_complete__:
            # Resolve this class from its module globals first — the same
            # resolution pydantic applies lazily at first construction.  Only
            # the cross-module effect payloads need the full namespace
            # cascade, so the expensive family-wide rebuild stays a fallback.
            cls.model_rebuild(raise_errors=False)
            if not cls.__pydantic_complete__:
                rebuild_bootstrap_graph_effect_contracts()
        return super().create(schema_version=3, **values)


class BootstrapV3PayloadLimitPolicy(_BootstrapV3Contract):
    max_proposal_attempts: int = Field(ge=0)
    max_normalized_proposals: int = Field(ge=0)
    max_stanza_bytes: int = Field(ge=0)
    max_spacy_bytes: int = Field(ge=0)
    max_predicate_event_detection_bytes: int = Field(ge=0)
    max_temporal_resolution_bytes: int = Field(ge=0)
    max_lane_items: int = Field(ge=0)
    max_aggregate_bytes: int = Field(ge=0)
    max_mentions_per_proposal: int = Field(ge=0)
    max_fact_members_per_proposal: int = Field(ge=0)
    max_correction_members_per_proposal: int = Field(ge=0)
    max_retraction_members_per_proposal: int = Field(ge=0)
    max_action_state_members_per_proposal: int = Field(ge=0)
    max_identity_members_per_proposal: int = Field(ge=0)
    max_action_role_bindings_per_member: int = Field(ge=0)
    max_action_participants_per_binding: int = Field(ge=0)
    max_temporal_qualifiers_per_member: int = Field(ge=0)
    max_identity_predecessors_per_member: int = Field(ge=0)
    max_identity_successors_per_member: int = Field(ge=0)
    max_reference_assignments_per_identity: int = Field(ge=0)
    max_evidence_items_per_proposal: int = Field(ge=0)
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-v3-payload-limit-policy.v3"
    _digest_field = "policy_digest"


class BootstrapV3PayloadLimitAuthority(_BootstrapV3Contract):
    policy: BootstrapV3PayloadLimitPolicy
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-v3-payload-limit-authority.v3"
    _digest_field = "authority_digest"


class BootstrapProposalEvidenceItemV3(_BootstrapV3Contract):
    span: SourceSpanReference
    quote: str = Field(min_length=1)
    item_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-evidence-item.v3"
    _digest_field = "item_digest"


class BootstrapProposalMentionV3(_BootstrapV3Contract):
    mention_span: SourceSpanReference
    mention_quote: str = Field(min_length=1)
    mention_context_span: SourceSpanReference
    mention_context_quote: str = Field(min_length=1)
    proposed_type: str | None
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-mention.v3"
    _digest_field = "mention_digest"


class BootstrapProposalTypedLiteralV3(_BootstrapV3Contract):
    literal_type: ClaimValueType
    canonical_value: str = Field(min_length=1)
    unit: str | None
    literal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-typed-literal.v3"
    _digest_field = "literal_digest"


class BootstrapProposalEntityObjectV3(_BootstrapV3Contract):
    kind: Literal["entity"]
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-entity-object.v3"
    _digest_field = "object_digest"
    _create_static_values = {"kind": "entity"}


class BootstrapProposalLiteralObjectV3(_BootstrapV3Contract):
    kind: Literal["literal"]
    value: BootstrapProposalTypedLiteralV3
    object_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-literal-object.v3"
    _digest_field = "object_digest"
    _create_static_values = {"kind": "literal"}


BootstrapProposalObjectV3 = Annotated[
    BootstrapProposalEntityObjectV3 | BootstrapProposalLiteralObjectV3,
    Field(discriminator="kind"),
]


class BootstrapProposalFactV3(_BootstrapV3Contract):
    kind: Literal["fact"]
    predicate_id: str = Field(min_length=1)
    subject_mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    object: BootstrapProposalObjectV3
    assertion: BootstrapProposalEvidenceItemV3
    predicate_anchor: BootstrapProposalEvidenceItemV3
    polarity: Literal["positive", "negative"]
    commitment: Commitment
    attributed_to_mention_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    temporal_qualifiers: tuple[BootstrapProposalEvidenceItemV3, ...]
    fact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-fact.v3"
    _digest_field = "fact_digest"
    _create_static_values = {"kind": "fact"}

    @model_validator(mode="after")
    def validate_qualifiers(self) -> BootstrapProposalFactV3:
        if self.temporal_qualifiers != tuple(
            sorted(self.temporal_qualifiers, key=lambda item: item.item_digest)
        ) or len({item.item_digest for item in self.temporal_qualifiers}) != len(self.temporal_qualifiers):
            raise ValueError("bootstrap fact temporal qualifiers must be canonical")
        return self


class BootstrapProposalCorrectionV3(_BootstrapV3Contract):
    kind: Literal["correction"]
    corrected_fact: BootstrapProposalFactV3
    replacement_fact: BootstrapProposalFactV3
    assertion: BootstrapProposalEvidenceItemV3
    correction_anchor: BootstrapProposalEvidenceItemV3
    correction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-correction.v3"
    _digest_field = "correction_digest"
    _create_static_values = {"kind": "correction"}


class BootstrapProposalRetractionV3(_BootstrapV3Contract):
    kind: Literal["retraction"]
    retracted_fact: BootstrapProposalFactV3
    assertion: BootstrapProposalEvidenceItemV3
    retraction_anchor: BootstrapProposalEvidenceItemV3
    retraction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-retraction.v3"
    _digest_field = "retraction_digest"
    _create_static_values = {"kind": "retraction"}


class BootstrapProposalActionRoleParticipantV3(_BootstrapV3Contract):
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    grounding: tuple[BootstrapProposalEvidenceItemV3, ...]
    participant_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-action-role-participant.v3"
    _digest_field = "participant_digest"


class BootstrapProposalActionRoleBindingV3(_BootstrapV3Contract):
    role_id: str = Field(min_length=1)
    endpoint_kind: Literal["actor", "object"]
    participants: tuple[BootstrapProposalActionRoleParticipantV3, ...]
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-action-role-binding.v3"
    _digest_field = "binding_digest"


class BootstrapProposalActionStateV3(_BootstrapV3Contract):
    kind: Literal["action_state"]
    action_anchor: BootstrapProposalEvidenceItemV3
    logical_action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    role_bindings: tuple[BootstrapProposalActionRoleBindingV3, ...]
    state_id: str = Field(min_length=1)
    state_anchor: BootstrapProposalEvidenceItemV3
    execution_branch: BootstrapProposalEvidenceItemV3 | None
    execution_branch_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    assertion: BootstrapProposalEvidenceItemV3
    temporal_qualifiers: tuple[BootstrapProposalEvidenceItemV3, ...]
    action_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-action-state.v3"
    _digest_field = "action_state_digest"
    _create_static_values = {"kind": "action_state"}

    @model_validator(mode="after")
    def validate_action(self) -> BootstrapProposalActionStateV3:
        if (self.execution_branch is None) != (self.execution_branch_digest is None):
            raise ValueError("bootstrap execution branch must be paired")
        expected = contract_digest(
            b"memorii.semantic-ingestion.bootstrap-proposal-logical-action.v3",
            {"action_anchor": self.action_anchor, "role_bindings": self.role_bindings},
        )
        if self.logical_action_digest != expected:
            raise ValueError("bootstrap logical action digest mismatch")
        if self.execution_branch is not None and self.execution_branch_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-proposal-execution-branch.v3",
            {"execution_branch": self.execution_branch},
        ):
            raise ValueError("bootstrap execution branch digest mismatch")
        return self


class BootstrapProposalClaimRecordSelectorV3(_BootstrapV3Contract):
    kind: Literal["claim"]
    fact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selector_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-claim-record-selector.v3"
    _digest_field = "selector_digest"
    _create_static_values = {"kind": "claim"}


class BootstrapProposalActionRecordSelectorV3(_BootstrapV3Contract):
    kind: Literal["action"]
    logical_action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_anchor: BootstrapProposalEvidenceItemV3
    selector_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-action-record-selector.v3"
    _digest_field = "selector_digest"
    _create_static_values = {"kind": "action"}


class BootstrapProposalAliasRecordSelectorV3(_BootstrapV3Contract):
    kind: Literal["alias"]
    alias_namespace: str = Field(min_length=1)
    alias_anchor: BootstrapProposalEvidenceItemV3
    selector_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-alias-record-selector.v3"
    _digest_field = "selector_digest"
    _create_static_values = {"kind": "alias"}


BootstrapProposalRecordSelectorV3 = Annotated[
    BootstrapProposalClaimRecordSelectorV3
    | BootstrapProposalActionRecordSelectorV3
    | BootstrapProposalAliasRecordSelectorV3,
    Field(discriminator="kind"),
]


class BootstrapProposalReferenceAssignmentV3(_BootstrapV3Contract):
    record_selector: BootstrapProposalRecordSelectorV3
    successor_mention_digests: tuple[str, ...]
    disposition: Literal["migrate_current", "share_by_explicit_evidence", "preserve_historical"]
    assertion: BootstrapProposalEvidenceItemV3
    assignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-reference-assignment.v3"
    _digest_field = "assignment_digest"

    @model_validator(mode="after")
    def validate_successors(self) -> BootstrapProposalReferenceAssignmentV3:
        if not self.successor_mention_digests or self.successor_mention_digests != tuple(
            sorted(set(self.successor_mention_digests))
        ):
            raise ValueError("bootstrap reference assignment successors must be canonical")
        return self


class BootstrapProposalIdentityOperationV3(_BootstrapV3Contract):
    kind: Literal["identity"]
    operation: Literal["alias", "rekey", "merge", "split"]
    predecessor_mention_digests: tuple[str, ...]
    successor_mention_digests: tuple[str, ...]
    reference_assignments: tuple[BootstrapProposalReferenceAssignmentV3, ...]
    assertion: BootstrapProposalEvidenceItemV3
    identity_anchor: BootstrapProposalEvidenceItemV3
    identity_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-identity-operation.v3"
    _digest_field = "identity_operation_digest"
    _create_static_values = {"kind": "identity"}

    @model_validator(mode="after")
    def validate_identity(self) -> BootstrapProposalIdentityOperationV3:
        for values in (self.predecessor_mention_digests, self.successor_mention_digests):
            if not values or values != tuple(sorted(set(values))):
                raise ValueError("bootstrap identity members must be canonical")
        if self.operation != "split" and self.reference_assignments:
            raise ValueError("only bootstrap identity splits may assign references")
        return self


BootstrapProposalOperationMemberV3 = Annotated[
    BootstrapProposalFactV3
    | BootstrapProposalCorrectionV3
    | BootstrapProposalRetractionV3
    | BootstrapProposalActionStateV3
    | BootstrapProposalIdentityOperationV3,
    Field(discriminator="kind"),
]


class BootstrapProposalTransportRequestV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_keys: tuple[str, ...]
    prompt_registration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_bytes_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-transport-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_keys(self) -> BootstrapProposalTransportRequestV3:
        if not self.provenance_keys or self.provenance_keys != tuple(sorted(set(self.provenance_keys))):
            raise ValueError("bootstrap transport request provenance keys must be canonical")
        return self


class BootstrapProposalAttemptV3(_BootstrapV3Contract):
    attempt_ordinal: int = Field(ge=0)
    transport_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transport_status: Literal["succeeded", "rejected", "failed"]
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-attempt.v3"
    _digest_field = "attempt_digest"


class BootstrapNormalizedProposalV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    mentions: tuple[BootstrapProposalMentionV3, ...]
    operation_members: tuple[BootstrapProposalOperationMemberV3, ...]
    status: Literal["complete", "abstained"]
    originating_attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-normalized.v3"
    _digest_field = "proposal_digest"

    @model_validator(mode="after")
    def validate_proposal(self) -> BootstrapNormalizedProposalV3:
        if (self.source_id, self.source_digest, self.preparation_fingerprint, self.segment_id) != (
            self.bootstrap_analysis_provenance.source_id,
            self.bootstrap_analysis_provenance.source_digest,
            self.bootstrap_analysis_provenance.preparation_fingerprint,
            self.bootstrap_analysis_provenance.segment_id,
        ):
            raise ValueError("bootstrap proposal provenance is foreign")
        if self.mentions != tuple(
            sorted(self.mentions, key=lambda item: (item.mention_span.reference_digest, item.mention_digest))
        ) or len({item.mention_digest for item in self.mentions}) != len(self.mentions):
            raise ValueError("bootstrap proposal mentions must be canonical")
        if (self.status == "complete" and not self.operation_members) or (
            self.status == "abstained" and self.operation_members
        ):
            raise ValueError("bootstrap proposal status/member closure is invalid")
        ranks = {"fact": 0, "correction": 1, "retraction": 2, "action_state": 3, "identity": 4}

        def member_key(item: BootstrapProposalOperationMemberV3) -> tuple[int, str, str]:
            anchor = (
                getattr(item, "predicate_anchor", None)
                or getattr(item, "correction_anchor", None)
                or getattr(item, "retraction_anchor", None)
                or getattr(item, "action_anchor", None)
                or getattr(item, "identity_anchor", None)
            )
            digest = next(
                getattr(item, name)
                for name in type(item).model_fields
                if name.endswith("_digest") and name not in {"logical_action_digest", "execution_branch_digest"}
            )
            return ranks[item.kind], anchor.item_digest, digest

        if self.operation_members != tuple(sorted(self.operation_members, key=member_key)):
            raise ValueError("bootstrap proposal operation members must be canonical")
        return self


class BootstrapProposalRunPayloadV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenances: tuple[BootstrapAnalysisProvenanceV1, ...]
    transport_requests: tuple[BootstrapProposalTransportRequestV3, ...]
    proposal_attempts: tuple[BootstrapProposalAttemptV3, ...]
    normalized_proposals: tuple[BootstrapNormalizedProposalV3, ...]
    payload_limit_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-run-payload.v3"
    _digest_field = "payload_digest"

    @model_validator(mode="after")
    def validate_payload(self) -> BootstrapProposalRunPayloadV3:
        provenances = self.bootstrap_analysis_provenances
        if (
            not provenances
            or provenances != tuple(sorted(provenances, key=lambda item: item.segment_id))
            or len({item.segment_id for item in provenances}) != len(provenances)
        ):
            raise ValueError("bootstrap proposal provenance set must be source ordered")
        if tuple(item.attempt_ordinal for item in self.proposal_attempts) != tuple(range(len(self.proposal_attempts))):
            raise ValueError("bootstrap proposal attempt ordinals must be contiguous")
        request_digests = tuple(item.request_digest for item in self.transport_requests)
        if (
            len(set(request_digests)) != len(request_digests)
            or tuple(sorted({item.transport_request_digest for item in self.proposal_attempts})) != tuple(sorted(request_digests))
        ):
            raise ValueError("bootstrap proposal request closure is invalid")
        attempt_digests = {item.attempt_digest for item in self.proposal_attempts}
        if any(item.originating_attempt_digest not in attempt_digests for item in self.normalized_proposals):
            raise ValueError("bootstrap normalized proposal attempt is absent")
        closure = {
            "transport_request_digests": request_digests,
            "attempt_digests": tuple(item.attempt_digest for item in self.proposal_attempts),
            "normalized_proposal_digests": tuple(item.proposal_digest for item in self.normalized_proposals),
        }
        if self.attempt_closure_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-proposal-attempt-closure.v3", closure
        ):
            raise ValueError("bootstrap proposal attempt closure digest mismatch")
        return self


class BootstrapStanzaLanePayloadV3(_BootstrapV3Contract):
    kind: Literal["stanza"]
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis: LinguisticAnalysis
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analysis-lane-payload.v3"
    _digest_field = "payload_digest"
    _create_static_values = {"kind": "stanza"}


class BootstrapSpacyLanePayloadV3(_BootstrapV3Contract):
    kind: Literal["spacy"]
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis: LinguisticAnalysis
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analysis-lane-payload.v3"
    _digest_field = "payload_digest"
    _create_static_values = {"kind": "spacy"}


class BootstrapAnalysisSourceEvidenceV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    span: SourceSpanReference
    exact_text: str = Field(min_length=1)
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analysis-source-evidence.v3"
    _digest_field = "evidence_digest"

    @model_validator(mode="after")
    def validate_evidence(self) -> BootstrapAnalysisSourceEvidenceV3:
        if ((self.source_id, self.source_digest, self.preparation_fingerprint, self.segment_id) !=
                (self.bootstrap_analysis_provenance.source_id, self.bootstrap_analysis_provenance.source_digest,
                 self.bootstrap_analysis_provenance.preparation_fingerprint, self.bootstrap_analysis_provenance.segment_id)
                or self.span.source_id != self.source_id
                or len(self.exact_text) != self.span.segment_local_span.end - self.span.segment_local_span.start
                or sha256(self.exact_text.encode("utf-8")).hexdigest() != self.span.segment_local_span.substring_digest):
            raise ValueError("bootstrap V3 source evidence is substituted")
        return self


class BootstrapPredicateEventCandidateV3(_BootstrapV3Contract):
    event_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    predicate_family: str = Field(min_length=1)
    lexical_anchor: BootstrapAnalysisSourceEvidenceV3
    morphology_evidence: tuple[BootstrapAnalysisSourceEvidenceV3, ...]
    detection_rule_id: str = Field(min_length=1)
    detector_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-predicate-event-candidate.v3"
    _digest_field = "candidate_digest"

    @model_validator(mode="after")
    def validate_candidate(self) -> BootstrapPredicateEventCandidateV3:
        coordinate = (self.source_id, self.source_digest, self.preparation_fingerprint, self.segment_id,
                      self.bootstrap_analysis_provenance)
        evidence = (self.lexical_anchor,) + self.morphology_evidence
        identity = {"provenance_digest": self.bootstrap_analysis_provenance.provenance_digest,
                    "predicate_family": self.predicate_family, "lexical_anchor": self.lexical_anchor,
                    "detection_rule_id": self.detection_rule_id, "detector_fingerprint": self.detector_manifest_digest}
        if (not self.morphology_evidence or any((item.source_id, item.source_digest, item.preparation_fingerprint,
                item.segment_id, item.bootstrap_analysis_provenance) != coordinate for item in evidence)
                or self.morphology_evidence != tuple(sorted(self.morphology_evidence, key=lambda item: item.evidence_digest))
                or len({item.evidence_digest for item in self.morphology_evidence}) != len(self.morphology_evidence)
                or self.event_id != contract_digest(b"memorii.semantic-ingestion.bootstrap-predicate-event-identity.v3", identity)):
            raise ValueError("bootstrap V3 predicate candidate is invalid")
        return self


class BootstrapPredicateLanePayloadV3(_BootstrapV3Contract):
    kind: Literal["predicate_event_detection"]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    detector_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    detector_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[BootstrapPredicateEventCandidateV3, ...]
    status: Literal["complete", "partial", "unsupported", "failed"]
    reason_codes: tuple[str, ...]
    inventory_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-predicate-lane-payload.v3"
    _digest_field = "inventory_digest"
    _create_static_values = {"kind": "predicate_event_detection"}

    @property
    def payload_digest(self) -> str: return self.inventory_digest

    @model_validator(mode="after")
    def validate_payload(self) -> BootstrapPredicateLanePayloadV3:
        coordinate = (self.source_id, self.source_digest, self.preparation_fingerprint, self.segment_id,
                      self.bootstrap_analysis_provenance)
        if (self.detector_manifest_digest != self.bootstrap_analysis_provenance.predicate_event_manifest_digest
                or any((item.source_id, item.source_digest, item.preparation_fingerprint, item.segment_id,
                        item.bootstrap_analysis_provenance) != coordinate or item.detector_manifest_digest != self.detector_manifest_digest for item in self.candidates)
                or self.candidates != tuple(sorted(self.candidates, key=lambda item: (item.lexical_anchor.evidence_digest, item.event_id, item.candidate_digest)))
                or len({item.event_id for item in self.candidates}) != len(self.candidates)
                or self.reason_codes != tuple(sorted(set(self.reason_codes)))
                or (self.status not in {"complete", "unsupported", "failed"} and not self.reason_codes)):
            raise ValueError("bootstrap V3 predicate payload is invalid")
        return self


class BootstrapTemporalReferenceV3(_BootstrapV3Contract):
    kind: Literal["authenticated_event_time", "authenticated_document_time"]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_field: Literal["event_time", "authenticated_document_time"]
    reference_instant: datetime
    authority_basis: Literal["server_event_metadata", "authenticated_document_metadata", "authenticated_external_time"]
    authority_provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_semantic_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-temporal-reference.v3"
    _digest_field = "reference_digest"

    @model_validator(mode="after")
    def validate_reference(self) -> BootstrapTemporalReferenceV3:
        if ((self.kind == "authenticated_event_time" and (self.source_field != "event_time" or self.authority_basis not in {"server_event_metadata", "authenticated_external_time"}))
                or (self.kind == "authenticated_document_time" and (self.source_field != "authenticated_document_time" or self.authority_basis not in {"authenticated_document_metadata", "authenticated_external_time"}))
                or (self.source_id, self.source_digest, self.preparation_fingerprint) != (self.bootstrap_analysis_provenance.source_id, self.bootstrap_analysis_provenance.source_digest, self.bootstrap_analysis_provenance.preparation_fingerprint)):
            raise ValueError("bootstrap V3 temporal reference is invalid")
        return self


class BootstrapResolvedTemporalCandidateV3(_BootstrapV3Contract):
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    source_evidence: BootstrapAnalysisSourceEvidenceV3
    value_kind: Literal["instant", "interval", "duration"]
    normalized_start: datetime | None
    normalized_end: datetime | None
    normalized_duration_seconds: int | None
    grain: str = Field(min_length=1)
    locale: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    reference: BootstrapTemporalReferenceV3 | None
    resolver_rule_id: str = Field(min_length=1)
    resolver_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-resolved-temporal-candidate.v3"
    _digest_field = "candidate_digest"

    @model_validator(mode="after")
    def validate_candidate(self) -> BootstrapResolvedTemporalCandidateV3:
        shape = ((self.normalized_start is not None and self.normalized_end is not None and self.normalized_start == self.normalized_end and self.normalized_duration_seconds is None) if self.value_kind == "instant" else
                 (self.normalized_start is not None and self.normalized_end is not None and self.normalized_start <= self.normalized_end and self.normalized_duration_seconds is None) if self.value_kind == "interval" else
                 (self.normalized_start is None and self.normalized_end is None and self.normalized_duration_seconds is not None and self.normalized_duration_seconds > 0))
        identity = {name: getattr(self, name) for name in ("source_id", "source_digest", "preparation_fingerprint", "segment_id", "bootstrap_analysis_provenance", "source_evidence", "value_kind", "normalized_start", "normalized_end", "normalized_duration_seconds", "grain", "locale", "timezone", "reference", "resolver_rule_id", "resolver_fingerprint")}
        if (not shape or (self.source_id, self.source_digest, self.preparation_fingerprint, self.segment_id, self.bootstrap_analysis_provenance) !=
                (self.source_evidence.source_id, self.source_evidence.source_digest, self.source_evidence.preparation_fingerprint, self.source_evidence.segment_id, self.source_evidence.bootstrap_analysis_provenance)
                or self.candidate_id != contract_digest(b"memorii.semantic-ingestion.bootstrap-resolved-temporal-candidate-identity.v3", identity)):
            raise ValueError("bootstrap V3 temporal candidate is invalid")
        return self


class BootstrapTemporalAmbiguityMemberV3(_BootstrapV3Contract):
    candidate: BootstrapResolvedTemporalCandidateV3
    value_basis_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-temporal-ambiguity-member.v3"
    _digest_field = "member_digest"


class BootstrapTemporalAmbiguitySetV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    source_evidence: BootstrapAnalysisSourceEvidenceV3
    alternatives: tuple[BootstrapTemporalAmbiguityMemberV3, ...]
    ambiguity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-temporal-ambiguity-set.v3"
    _digest_field = "ambiguity_digest"

    @model_validator(mode="after")
    def validate_ambiguity(self) -> BootstrapTemporalAmbiguitySetV3:
        if (len(self.alternatives) < 2 or self.alternatives != tuple(sorted(self.alternatives, key=lambda item: (item.value_basis_key, item.candidate.candidate_id, item.member_digest)))
                or len({item.value_basis_key for item in self.alternatives}) != len(self.alternatives)
                or any(item.candidate.source_evidence != self.source_evidence for item in self.alternatives)):
            raise ValueError("bootstrap V3 temporal ambiguity is invalid")
        return self


class BootstrapTemporalLanePayloadV3(_BootstrapV3Contract):
    kind: Literal["temporal_resolution"]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    resolver_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolver_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[BootstrapResolvedTemporalCandidateV3, ...]
    ambiguities: tuple[BootstrapTemporalAmbiguitySetV3, ...]
    status: Literal["complete", "partial", "unsupported", "failed"]
    reason_codes: tuple[str, ...]
    resolution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-temporal-lane-payload.v3"
    _digest_field = "resolution_digest"
    _create_static_values = {"kind": "temporal_resolution"}

    @property
    def payload_digest(self) -> str: return self.resolution_digest

    @model_validator(mode="after")
    def validate_payload(self) -> BootstrapTemporalLanePayloadV3:
        coordinate = (self.source_id, self.source_digest, self.preparation_fingerprint, self.segment_id, self.bootstrap_analysis_provenance)
        candidate_ids = {item.candidate_id for item in self.candidates}
        if (self.resolver_manifest_digest != self.bootstrap_analysis_provenance.temporal_resolver_manifest_digest
                or self.candidates != tuple(sorted(self.candidates, key=lambda item: (item.source_evidence.evidence_digest, item.candidate_id, item.candidate_digest)))
                or len(candidate_ids) != len(self.candidates)
                or any((item.source_id, item.source_digest, item.preparation_fingerprint, item.segment_id, item.bootstrap_analysis_provenance) != coordinate or item.resolver_fingerprint != self.resolver_fingerprint for item in self.candidates)
                or self.ambiguities != tuple(sorted(self.ambiguities, key=lambda item: (item.source_evidence.evidence_digest, item.ambiguity_digest)))
                or any(item.candidate.candidate_id not in candidate_ids for group in self.ambiguities for item in group.alternatives)
                or self.reason_codes != tuple(sorted(set(self.reason_codes))) or (self.status not in {"complete", "unsupported", "failed"} and not self.reason_codes)):
            raise ValueError("bootstrap V3 temporal payload is invalid")
        return self


BootstrapAnalysisLanePayloadV3 = Annotated[
    BootstrapStanzaLanePayloadV3
    | BootstrapSpacyLanePayloadV3
    | BootstrapPredicateLanePayloadV3
    | BootstrapTemporalLanePayloadV3,
    Field(discriminator="kind"),
]


class BootstrapAnalysisLaneResultV3(_BootstrapV3Contract):
    """Closed V3 durable receipt for one bootstrap-only local lane."""

    lane: Literal["stanza", "spacy", "predicate_event_detection", "temporal_resolution"]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    lane_payload: BootstrapAnalysisLanePayloadV3
    payload_limit_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analysis-lane-result.v3"
    _digest_field = "result_digest"

    @model_validator(mode="after")
    def validate_result(self) -> BootstrapAnalysisLaneResultV3:
        if (
            (self.source_id, self.source_digest, self.preparation_fingerprint, self.segment_id)
            != (
                self.bootstrap_analysis_provenance.source_id,
                self.bootstrap_analysis_provenance.source_digest,
                self.bootstrap_analysis_provenance.preparation_fingerprint,
                self.bootstrap_analysis_provenance.segment_id,
            )
            or self.lane_payload.kind != self.lane
            or self.payload_digest != self.lane_payload.payload_digest
        ):
            raise ValueError("bootstrap V3 lane result authority is substituted")
        return self


class BootstrapPreAlignmentOperationSubjectV3(_BootstrapV3Contract):
    kind: Literal["fact", "correction", "retraction", "action_state", "identity"]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_ordinal: int = Field(ge=0)
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-pre-alignment-operation-subject.v3"
    _digest_field = "operation_id"


class BootstrapPreAlignmentOperationSubjectSetV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    subjects: tuple[BootstrapPreAlignmentOperationSubjectV3, ...]
    payload_limit_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    subject_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-pre-alignment-operation-subject-set.v3"
    _digest_field = "subject_set_digest"


class BootstrapCanonicalRoleAssignmentV3(_BootstrapV3Contract):
    role_id: str = Field(min_length=1)
    argument: BootstrapProposalEvidenceItemV3
    assignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-canonical-role-assignment.v3"
    _digest_field = "assignment_digest"


class BootstrapAnalyzerRoleInterpretationV3(_BootstrapV3Contract):
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_anchor: BootstrapProposalEvidenceItemV3
    assignments: tuple[BootstrapCanonicalRoleAssignmentV3, ...]
    interpretation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analyzer-role-interpretation.v3"
    _digest_field = "interpretation_digest"


class BootstrapAnalyzerScopeInterpretationV3(_BootstrapV3Contract):
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_anchor: BootstrapProposalEvidenceItemV3
    governing_clauses: tuple[BootstrapProposalEvidenceItemV3, ...]
    polarity: Literal["positive", "negative"]
    commitment: Commitment
    attribution: Literal["speaker", "quoted_or_reported_source"]
    attribution_bearer: BootstrapProposalEvidenceItemV3 | None
    interpretation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analyzer-scope-interpretation.v3"
    _digest_field = "interpretation_digest"


class BootstrapStableSemanticScopeV3(_BootstrapV3Contract):
    polarity: Literal["positive", "negative"]
    commitment: Commitment
    attribution: Literal["speaker", "quoted_or_reported_source"]
    attribution_bearer: BootstrapProposalEvidenceItemV3 | None
    governing_clauses: tuple[BootstrapProposalEvidenceItemV3, ...]
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-stable-semantic-scope.v3"
    _digest_field = "scope_digest"


class BootstrapAnalyzerTemporalAttachmentV3(_BootstrapV3Contract):
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_anchor: BootstrapProposalEvidenceItemV3
    candidate_ids: tuple[str, ...]
    attachment_spans: tuple[BootstrapProposalEvidenceItemV3, ...]
    attachment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analyzer-temporal-attachment.v3"
    _digest_field = "attachment_digest"


class _BootstrapOperationObservationV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class BootstrapAnalyzerScopeObservationV3(_BootstrapOperationObservationV3):
    analyzer_role: Literal["primary", "corroborating"]
    interpretation: BootstrapAnalyzerScopeInterpretationV3
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analyzer-scope-observation.v3"
    _digest_field = "observation_digest"


class BootstrapAnalyzerTemporalAttachmentObservationV3(_BootstrapOperationObservationV3):
    temporal_role: Literal["assertion", "corrected", "replacement", "retracted", "action_state", "identity"]
    analyzer_role: Literal["primary", "corroborating"]
    attachment: BootstrapAnalyzerTemporalAttachmentV3
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-analyzer-temporal-attachment-observation.v3"
    _digest_field = "observation_digest"


class BootstrapParserConsensusAssessmentV3(_BootstrapOperationObservationV3):
    analysis_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_analyzer_role: Literal["stanza"]
    primary_lane_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_interpretation: BootstrapAnalyzerRoleInterpretationV3
    corroborating_analyzer_role: Literal["spacy"]
    corroborating_lane_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    corroborating_interpretation: BootstrapAnalyzerRoleInterpretationV3
    stable_assignment: tuple[BootstrapCanonicalRoleAssignmentV3, ...] | None
    status: Literal["stable", "disagreement", "ambiguous", "unsupported"]
    consensus_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-parser-consensus-assessment.v3"
    _digest_field = "assessment_digest"


class BootstrapSemanticScopeConsensusV3(_BootstrapOperationObservationV3):
    analysis_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_observation: BootstrapAnalyzerScopeObservationV3
    corroborating_observation: BootstrapAnalyzerScopeObservationV3
    stable_scope: BootstrapStableSemanticScopeV3 | None
    status: Literal["stable", "disagreement", "ambiguous", "unsupported"]
    consensus_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-semantic-scope-consensus.v3"
    _digest_field = "consensus_digest"


class BootstrapTemporalAttachmentConsensusV3(_BootstrapOperationObservationV3):
    temporal_role: Literal["assertion", "corrected", "replacement", "retracted", "action_state", "identity"]
    temporal_resolution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_attachment: BootstrapAnalyzerTemporalAttachmentObservationV3
    corroborating_attachment: BootstrapAnalyzerTemporalAttachmentObservationV3
    stable_candidate_ids: tuple[str, ...] | None
    status: Literal["stable", "disagreement", "ambiguous", "unsupported"]
    consensus_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-temporal-attachment-consensus.v3"
    _digest_field = "consensus_digest"


class BootstrapOperationTemporalAttachmentConsensusSetV3(_BootstrapV3Contract):
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    role_consensus_digests: tuple[
        tuple[Literal["assertion", "corrected", "replacement", "retracted", "action_state", "identity"], str], ...
    ]
    consensus_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-operation-temporal-attachment-consensus-set.v3"
    _digest_field = "consensus_set_digest"


class BootstrapOperationAlignmentV3(_BootstrapV3Contract):
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    parser_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_attachment_consensus_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-operation-alignment.v3"
    _digest_field = "alignment_digest"


class BootstrapSourceDependencyGroupV3(_BootstrapV3Contract):
    operation_ids: tuple[str, ...]
    proposal_digests: tuple[str, ...]
    member_digests: tuple[str, ...]
    segment_ids: tuple[str, ...]
    kind: Literal["independent_fact", "correction", "retraction", "identity", "action_state"]
    source_dependency_kinds: tuple[str, ...]
    atomic: Literal[True]
    status: Literal["complete", "unresolved", "failed"]
    reason_codes: tuple[str, ...]
    group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-dependency-group.v3"
    _digest_field = "group_id"

    @model_validator(mode="after")
    def validate_group(self) -> BootstrapSourceDependencyGroupV3:
        for values in (self.operation_ids, self.proposal_digests, self.member_digests, self.segment_ids):
            if not values or values != tuple(sorted(set(values))):
                raise ValueError("bootstrap dependency group members must be nonempty and canonical")
        if (self.status == "complete") != (not self.reason_codes):
            raise ValueError("bootstrap dependency group reason closure is invalid")
        return self


class BootstrapSourcePrePartitionMentionV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mention: BootstrapProposalMentionV3
    partition_mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-pre-partition-mention.v3"
    _digest_field = "partition_mention_digest"


class BootstrapSourceLocalIdentityAssertionV3(_BootstrapV3Contract):
    proof_kind: Literal[
        "explicit_alias",
        "explicit_apposition",
        "authenticated_external_id",
        "certified_unambiguous_repetition",
        "insufficient_evidence",
        "conflicting_evidence",
    ]
    mention_digests: tuple[str, ...]
    source_evidence: tuple[BootstrapProposalEvidenceItemV3, ...]
    assertion_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-local-identity-assertion.v3"
    _digest_field = "assertion_digest"


class BootstrapSourceLocalIdentityPartitionEvidenceV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenances: tuple[BootstrapAnalysisProvenanceV1, ...]
    mentions: tuple[BootstrapSourcePrePartitionMentionV3, ...]
    assertions: tuple[BootstrapSourceLocalIdentityAssertionV3, ...]
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-local-identity-partition-evidence.v3"
    _digest_field = "evidence_digest"


class BootstrapSourceLocalIdentityResolutionV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    grounded_mention_digests: tuple[str, ...]
    clusters: tuple[BootstrapSourceLocalIdentityClusterDecisionV3, ...]
    unresolved_mention_digests: tuple[str, ...]
    resolution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-local-identity-resolution.v3"
    _digest_field = "resolution_digest"


class BootstrapSourceLocalIdentityClusterDecisionV3(_BootstrapV3Contract):
    """A V3-native source-local identity decision.

    Bootstrap recovery must never deserialize the generic route-bearing
    cluster record.  The provenance closure is the complete replacement for
    its historic route/policy coordinate.
    """

    decision: Literal["same_source_entity", "singleton_distinct", "unresolved"]
    proof_kind: Literal[
        "explicit_alias",
        "explicit_apposition",
        "authenticated_external_id",
        "certified_unambiguous_repetition",
        "insufficient_evidence",
        "conflicting_evidence",
    ]
    mention_digests: tuple[str, ...]
    source_evidence: tuple[BootstrapProposalEvidenceItemV3, ...]
    provenance_closure: tuple[tuple[str, str, str], ...]
    cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-local-identity-cluster-decision.v3"
    _digest_field = "decision_digest"

    @model_validator(mode="after")
    def validate_cluster(self) -> BootstrapSourceLocalIdentityClusterDecisionV3:
        if (
            not self.mention_digests
            or self.mention_digests != tuple(sorted(set(self.mention_digests)))
            or self.provenance_closure != tuple(sorted(set(self.provenance_closure)))
            or (self.decision == "unresolved") != (
                self.proof_kind in {"insufficient_evidence", "conflicting_evidence"}
            )
        ):
            raise ValueError("bootstrap V3 identity cluster closure is invalid")
        cluster_preimage = self.model_dump(
            mode="python", exclude={"cluster_id", "decision_digest"}
        )
        expected_cluster_id = contract_digest(
            b"memorii.semantic-ingestion.bootstrap-source-local-identity-cluster-id.v3",
            cluster_preimage,
        )
        if self.cluster_id != expected_cluster_id:
            raise ValueError("bootstrap V3 identity cluster id mismatch")
        return self


class BootstrapCoveredPredicateEventV3(_BootstrapV3Contract):
    kind: Literal["covered"]
    event_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digests: tuple[str, ...]
    operation_ids: tuple[str, ...]
    alignment_digests: tuple[str, ...]
    disposition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-covered-predicate-event.v3"
    _digest_field = "disposition_digest"


class BootstrapUnresolvedPredicateEventV3(_BootstrapV3Contract):
    kind: Literal["unresolved"]
    event_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal[
        "proposal_omitted", "proposal_abstained", "alignment_failed",
        "parser_disagreement", "scope_disagreement",
        "temporal_attachment_disagreement", "unsupported_construction",
    ]
    related_proposal_digests: tuple[str, ...]
    evidence: tuple[BootstrapProposalEvidenceItemV3, ...]
    disposition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-unresolved-predicate-event.v3"
    _digest_field = "disposition_digest"


BootstrapPredicateEventDispositionV3 = Annotated[
    BootstrapCoveredPredicateEventV3 | BootstrapUnresolvedPredicateEventV3,
    Field(discriminator="kind"),
]


class BootstrapProposalCoverageAuditV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenances: tuple[BootstrapAnalysisProvenanceV1, ...]
    proposal_payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_inventory_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_ids: tuple[str, ...]
    dispositions: tuple[BootstrapPredicateEventDispositionV3, ...]
    covered_event_ids: tuple[str, ...]
    unresolved_event_ids: tuple[str, ...]
    status: Literal["complete", "unresolved", "failed"]
    coverage_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-proposal-coverage-audit.v3"
    _digest_field = "audit_digest"


class BootstrapGraphFreeInterpretationBundleV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    lane_result_digests: tuple[str, ...]
    subject_sets: tuple[BootstrapPreAlignmentOperationSubjectSetV3, ...]
    scope_observations: tuple[BootstrapAnalyzerScopeObservationV3, ...]
    temporal_attachment_observations: tuple[BootstrapAnalyzerTemporalAttachmentObservationV3, ...]
    identity_partition_evidence: BootstrapSourceLocalIdentityPartitionEvidenceV3
    payload_limit_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-free-interpretation-bundle.v3"
    _digest_field = "bundle_digest"


class BootstrapGraphFreeIdentityPlanningInputV3(_BootstrapV3Contract):
    """Retained graph-free identity input; never a generic identity adapter."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_member: BootstrapProposalIdentityOperationV3
    operation_subject: BootstrapPreAlignmentOperationSubjectV3
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    identity_partition_evidence: BootstrapSourceLocalIdentityPartitionEvidenceV3
    source_local_identity: BootstrapSourceLocalIdentityResolutionV3
    operation_alignment: BootstrapOperationAlignmentV3
    dependency_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.graph-free-identity-planning-input.v3"
    _digest_field = "input_digest"

    @model_validator(mode="after")
    def validate_native_identity_join(self) -> BootstrapGraphFreeIdentityPlanningInputV3:
        subject = self.operation_subject
        alignment = self.operation_alignment
        provenance = self.bootstrap_analysis_provenance
        if (
            subject.kind != "identity"
            or (subject.source_id, subject.source_digest, subject.preparation_fingerprint)
            != (self.source_id, self.source_digest, self.preparation_fingerprint)
            or subject.operation_id != self.operation_id
            or subject.proposal_digest != self.proposal_digest
            or subject.bootstrap_analysis_provenance != provenance
            or (alignment.operation_id, alignment.proposal_digest, alignment.member_digest)
            != (self.operation_id, self.proposal_digest, subject.member_digest)
            or alignment.bootstrap_analysis_provenance != provenance
            or self.identity_partition_evidence.source_id != self.source_id
            or self.source_local_identity.source_id != self.source_id
        ):
            raise ValueError("bootstrap native identity input is substituted")
        return self


class BootstrapOperationCoverageBindingV3(_BootstrapV3Contract):
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenance: BootstrapAnalysisProvenanceV1
    operation_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: BootstrapPredicateEventDispositionV3
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.operation-coverage-binding.v3"
    _digest_field = "binding_digest"

    @model_validator(mode="after")
    def validate_disposition_membership(self) -> BootstrapOperationCoverageBindingV3:
        if self.disposition.event_id != self.predicate_event_id:
            raise ValueError("bootstrap operation coverage event is substituted")
        if self.disposition.kind == "covered":
            if (
                self.operation_id not in self.disposition.operation_ids
                or self.proposal_digest not in self.disposition.proposal_digests
                or self.operation_alignment_digest not in self.disposition.alignment_digests
            ):
                raise ValueError("bootstrap covered operation binding is foreign")
        elif self.proposal_digest not in self.disposition.related_proposal_digests:
            raise ValueError("bootstrap unresolved operation binding is foreign")
        return self


class BootstrapNativeOperationReductionInputV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_proposal: BootstrapNormalizedProposalV3
    operation_member: BootstrapProposalOperationMemberV3
    operation_subject: BootstrapPreAlignmentOperationSubjectV3
    lane_results: tuple[BootstrapAnalysisLaneResultV3, ...]
    parser_consensus: BootstrapParserConsensusAssessmentV3
    scope_consensus: BootstrapSemanticScopeConsensusV3
    temporal_consensus_set: BootstrapOperationTemporalAttachmentConsensusSetV3
    operation_alignment: BootstrapOperationAlignmentV3
    identity_partition_evidence: BootstrapSourceLocalIdentityPartitionEvidenceV3
    source_local_identity: BootstrapSourceLocalIdentityResolutionV3
    dependency_group: BootstrapSourceDependencyGroupV3
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    coverage_bindings: tuple[BootstrapOperationCoverageBindingV3, ...]
    graph_free_identity_input: BootstrapGraphFreeIdentityPlanningInputV3 | None
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-operation-reduction-input.v3"
    _digest_field = "input_digest"

    @model_validator(mode="after")
    def validate_retained_native_closure(self) -> BootstrapNativeOperationReductionInputV3:
        subject, alignment = self.operation_subject, self.operation_alignment
        coordinate = (self.source_id, self.source_digest, self.preparation_fingerprint)
        checks = {
            # A source with no detected predicate event has no accepted arm;
            # it remains a sealed evidence-only reduction instead of inventing
            # an unresolved event binding.
            "coverage": bool(self.coverage_bindings) or self.normalized_proposal.status == "complete",
            "binding_order": self.coverage_bindings == tuple(sorted(self.coverage_bindings, key=lambda item: (item.predicate_event_id, item.binding_digest))),
            "binding_unique": len({(item.operation_execution_id, item.predicate_event_id) for item in self.coverage_bindings}) == len(self.coverage_bindings),
            "proposal_coordinate": (self.normalized_proposal.source_id, self.normalized_proposal.source_digest, self.normalized_proposal.preparation_fingerprint) == coordinate,
            "subject_coordinate": (subject.source_id, subject.source_digest, subject.preparation_fingerprint) == coordinate,
            "subject_operation": subject.operation_id == self.operation_id,
            "subject_proposal": subject.proposal_digest == self.normalized_proposal.proposal_digest,
            "member": self.operation_member in self.normalized_proposal.operation_members,
            "alignment": (alignment.operation_id, alignment.proposal_digest, alignment.member_digest) == (self.operation_id, subject.proposal_digest, subject.member_digest),
            "parser": self.parser_consensus.assessment_digest == alignment.parser_consensus_digest,
            "scope": self.scope_consensus.consensus_digest == alignment.scope_consensus_digest,
            "temporal": self.temporal_consensus_set.consensus_set_digest == alignment.temporal_attachment_consensus_set_digest,
            "group": self.operation_id in self.dependency_group.operation_ids,
            "bindings": not any(item.operation_execution_id != self.operation_execution_id or item.operation_id != self.operation_id or item.proposal_digest != subject.proposal_digest or item.member_digest != subject.member_digest or item.bootstrap_analysis_provenance != subject.bootstrap_analysis_provenance or item.operation_alignment_digest != alignment.alignment_digest for item in self.coverage_bindings),
            "identity": (self.operation_member.kind == "identity") == (self.graph_free_identity_input is not None),
        }
        failed = tuple(name for name, valid in checks.items() if not valid)
        if failed:
            raise ValueError("bootstrap native operation reduction input is incomplete: " + ",".join(failed))
        return self


class BootstrapSourceProposalAlignmentV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenances: tuple[BootstrapAnalysisProvenanceV1, ...]
    operation_alignments: tuple[BootstrapOperationAlignmentV3, ...]
    parser_consensus: tuple[BootstrapParserConsensusAssessmentV3, ...]
    scope_consensus: tuple[BootstrapSemanticScopeConsensusV3, ...]
    temporal_attachment_consensus: tuple[BootstrapTemporalAttachmentConsensusV3, ...]
    temporal_attachment_consensus_sets: tuple[BootstrapOperationTemporalAttachmentConsensusSetV3, ...]
    source_local_identity: BootstrapSourceLocalIdentityResolutionV3
    proposal_coverage: BootstrapProposalCoverageAuditV3
    source_dependency_groups: tuple[BootstrapSourceDependencyGroupV3, ...]
    interpretation_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_inventory_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_resolution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["complete", "unsupported", "failed"]
    reason_codes: tuple[str, ...]
    payload_limit_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-proposal-alignment.v3"
    _digest_field = "alignment_digest"


class BootstrapSemanticProposalRunV3(_ContentAddressedContract):
    """Closed bootstrap proposal aggregate; payload bytes never require read-back."""

    schema_version: Literal[3]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_payload: BootstrapProposalRunPayloadV3
    bootstrap_analysis_provenance: tuple[BootstrapAnalysisProvenanceV1, ...]
    run_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-semantic-proposal-run.v3"
    _digest_field = "run_digest"

    @model_validator(mode="after")
    def validate_run(self) -> BootstrapSemanticProposalRunV3:
        if (
            not self.bootstrap_analysis_provenance
            or self.bootstrap_analysis_provenance != self.proposal_payload.bootstrap_analysis_provenances
            or (self.source_id, self.source_digest, self.preparation_fingerprint)
            != (
                self.proposal_payload.source_id,
                self.proposal_payload.source_digest,
                self.proposal_payload.preparation_fingerprint,
            )
        ):
            raise ValueError("bootstrap V3 proposal run closure is invalid")
        return self


class BootstrapSourceNormalizationRequestV3(_ContentAddressedContract):
    """Flattened V3 bootstrap normalization request, separate from V2."""

    schema_version: Literal[3]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_run: BootstrapSemanticProposalRunV3
    lane_results: tuple[BootstrapAnalysisLaneResultV3, ...]
    interpretation_bundle: BootstrapGraphFreeInterpretationBundleV3
    source_alignment: BootstrapSourceProposalAlignmentV3
    bootstrap_analysis_provenance: tuple[BootstrapAnalysisProvenanceV1, ...]
    payload_limit_authority: BootstrapV3PayloadLimitAuthority
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-normalization-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> BootstrapSourceNormalizationRequestV3:
        expected = self.bootstrap_analysis_provenance
        if (
            not expected
            or self.proposal_run.bootstrap_analysis_provenance != expected
            or any(
                (item.source_id, item.source_digest, item.preparation_fingerprint)
                != (self.source_id, self.source_digest, self.preparation_fingerprint)
                for item in (*self.lane_results, *expected)
            )
            or {(item.segment_id, item.lane) for item in self.lane_results}
            != {
                (item.segment_id, lane)
                for item in expected
                for lane in ("stanza", "spacy", "predicate_event_detection", "temporal_resolution")
            }
            or any(item.bootstrap_analysis_provenance not in expected for item in self.lane_results)
            or self.proposal_run.proposal_payload.payload_limit_authority_digest
            != self.payload_limit_authority.authority_digest
            or self.interpretation_bundle.proposal_payload_digest
            != self.proposal_run.proposal_payload.payload_digest
            or self.source_alignment.interpretation_bundle_digest
            != self.interpretation_bundle.bundle_digest
            or self.source_alignment.bootstrap_analysis_provenances != expected
        ):
            raise ValueError("bootstrap V3 normalization request closure is incomplete")
        return self


class BootstrapSourceNormalizationEvidenceManifestV3(_ContentAddressedContract):
    schema_version: Literal[3]
    source_normalization_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenance: tuple[BootstrapAnalysisProvenanceV1, ...]
    lane_result_digests: tuple[str, ...]
    payload_limit_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-normalization-evidence-manifest.v3"
    _digest_field = "manifest_digest"

    @model_validator(mode="after")
    def validate_manifest(self) -> BootstrapSourceNormalizationEvidenceManifestV3:
        if (
            not self.bootstrap_analysis_provenance
            or self.lane_result_digests != tuple(sorted(set(self.lane_result_digests)))
            or len(self.lane_result_digests) != 4 * len(self.bootstrap_analysis_provenance)
        ):
            raise ValueError("bootstrap V3 evidence manifest closure is incomplete")
        return self


class BootstrapSourceNormalizationResultV3(_ContentAddressedContract):
    schema_version: Literal[3]
    source_normalization_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_manifest: BootstrapSourceNormalizationEvidenceManifestV3
    interpretation_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_analysis_provenance: tuple[BootstrapAnalysisProvenanceV1, ...]
    payload_limit_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_limit_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-normalization-result.v3"
    _digest_field = "result_digest"

    @model_validator(mode="after")
    def validate_result(self) -> BootstrapSourceNormalizationResultV3:
        if (
            self.evidence_manifest.source_normalization_request_digest != self.source_normalization_request_digest
            or self.evidence_manifest.interpretation_bundle_digest != self.interpretation_bundle_digest
            or self.evidence_manifest.source_alignment_digest != self.source_alignment_digest
            or self.evidence_manifest.bootstrap_analysis_provenance != self.bootstrap_analysis_provenance
            or self.evidence_manifest.payload_limit_policy_digest != self.payload_limit_policy_digest
            or self.evidence_manifest.payload_limit_authority_digest != self.payload_limit_authority_digest
        ):
            raise ValueError("bootstrap V3 normalization result closure is substituted")
        return self


class BootstrapNormalizationRequestCoreV3(_BootstrapV3Contract):
    """The complete graph-free V3 preimage retained before any authority write.

    This is deliberately a value object rather than a digest alias.  Recovery
    must authenticate the exact bytes that were used to derive both the
    semantic-reduction member and the outer normalization checkpoint.
    """

    proposal_payload: BootstrapProposalRunPayloadV3
    lane_results: tuple[BootstrapAnalysisLaneResultV3, ...]
    interpretation_bundle: BootstrapGraphFreeInterpretationBundleV3
    source_alignment: BootstrapSourceProposalAlignmentV3
    payload_limit_authority: BootstrapV3PayloadLimitAuthority
    recovery_key: BootstrapRecoveryKeyV3
    core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-normalization-request-core.v3"
    _digest_field = "core_digest"

    @model_validator(mode="after")
    def validate_core_closure(self) -> BootstrapNormalizationRequestCoreV3:
        provenance = self.proposal_payload.bootstrap_analysis_provenances
        if (
            not provenance
            or self.proposal_payload.payload_limit_authority_digest
            != self.payload_limit_authority.authority_digest
            or self.interpretation_bundle.proposal_payload_digest
            != self.proposal_payload.payload_digest
            or self.source_alignment.interpretation_bundle_digest
            != self.interpretation_bundle.bundle_digest
            or (
                self.recovery_key.source_id,
                self.recovery_key.source_digest,
                self.recovery_key.preparation_fingerprint,
            )
            != (
                self.proposal_payload.source_id,
                self.proposal_payload.source_digest,
                self.proposal_payload.preparation_fingerprint,
            )
            or tuple((item.segment_id, item.lane) for item in self.lane_results)
            != tuple(
                (item.segment_id, lane)
                for item in provenance
                for lane in ("stanza", "spacy", "predicate_event_detection", "temporal_resolution")
            )
        ):
            raise ValueError("bootstrap normalization request core is incomplete")
        return self


class BootstrapSemanticReductionAuthorityMemberV3(_BootstrapV3Contract):
    """Reloadable native reduction authority built solely from retained input."""

    normalization_request_core: BootstrapNormalizationRequestCoreV3
    normalization_request_core_canonical_bytes: bytes
    operation_inputs: tuple[BootstrapNativeOperationReductionInputV3, ...]
    execution_policy: GraphDependentExecutionPolicy
    execution_policy_canonical_bytes: bytes
    capability_registry: CapabilityRegistrySnapshot
    capability_registry_canonical_bytes: bytes
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-semantic-reduction-authority-member.v3"
    _digest_field = "member_digest"

    @model_validator(mode="after")
    def validate_reduction_bytes(self) -> BootstrapSemanticReductionAuthorityMemberV3:
        core_bytes = encode_typed_value(
            canonical_contract_value(self.normalization_request_core)
        )
        policy_bytes = encode_typed_value(canonical_contract_value(self.execution_policy))
        registry_bytes = encode_typed_value(canonical_contract_value(self.capability_registry))
        core = self.normalization_request_core
        if (
            not self.operation_inputs
            or tuple(
                (item.dependency_group.group_id, item.operation_id)
                for item in self.operation_inputs
            )
            != tuple(sorted(
                (item.dependency_group.group_id, item.operation_id)
                for item in self.operation_inputs
            ))
            or len({item.operation_id for item in self.operation_inputs})
            != len(self.operation_inputs)
            or {
                item.operation_id for item in self.operation_inputs
            }
            != {
                operation_id
                for group in core.source_alignment.source_dependency_groups
                if group.status == "complete"
                for operation_id in group.operation_ids
            }
            or self.normalization_request_core_canonical_bytes != core_bytes
            or self.execution_policy_canonical_bytes != policy_bytes
            or self.capability_registry_canonical_bytes != registry_bytes
        ):
            raise ValueError("bootstrap semantic reduction authority bytes are not canonical")
        return self


class BootstrapSemanticReductionAuthorityReloadV3(_BootstrapV3Contract):
    normalization_replay: BootstrapRecoveryReplayRecordV3
    normalization_atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_operation_generation: int = Field(ge=0)
    normalization_artifact_generation: int = Field(ge=0)
    authority_member: BootstrapSemanticReductionAuthorityMemberV3
    reload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-semantic-reduction-authority-reload.v3"
    _digest_field = "reload_digest"

    @model_validator(mode="after")
    def validate_reload_join(self) -> BootstrapSemanticReductionAuthorityReloadV3:
        core = self.authority_member.normalization_request_core
        replay = self.normalization_replay
        if (
            core.recovery_key.recovery_key_digest != replay.recovery_key_digest
            or core.source_alignment.alignment_digest
            != replay.source_normalization_request.source_alignment.alignment_digest
            or core.proposal_payload != replay.source_normalization_request.proposal_run.proposal_payload
        ):
            raise ValueError("bootstrap semantic reduction authority reload is substituted")
        return self


class GraphDependentExecutionPolicyReferenceV3(_BootstrapV3Contract):
    """Immutable persisted reference to the graph-execution policy selected by a host."""

    repository_id: str = Field(min_length=1)
    repository_contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-execution-policy-reference.v3"
    _digest_field = "reference_digest"


class GraphSemanticSnapshotBundleV3(_BootstrapV3Contract):
    """The single graph snapshot/read-set pair admitted to a V3 graph run."""

    graph_snapshot: GraphStateSnapshot
    base_read_set: GraphReadSet
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-semantic-snapshot-bundle.v3"
    _digest_field = "snapshot_digest"

    @model_validator(mode="after")
    def validate_snapshot_join(self) -> GraphSemanticSnapshotBundleV3:
        if self.graph_snapshot.read_set != self.base_read_set:
            raise ValueError("bootstrap graph snapshot/read-set mismatch")
        return self


class BootstrapRecoveryReplayRecordV3(_BootstrapV3Contract):
    """Closed persisted V3 normalization replay input for graph coordination."""

    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    found_response: BootstrapRecoveryFoundV3
    source_normalization_request: BootstrapSourceNormalizationRequestV3
    source_normalization_result: BootstrapSourceNormalizationResultV3
    replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-recovery-replay-record.v3"
    _digest_field = "replay_digest"

    @model_validator(mode="after")
    def validate_replay_closure(self) -> BootstrapRecoveryReplayRecordV3:
        request, result, found = (
            self.source_normalization_request,
            self.source_normalization_result,
            self.found_response,
        )
        if (
            found.recovery_key_digest != self.recovery_key_digest
            or found.result_digest != result.result_digest
            or result.source_normalization_request_digest != request.request_digest
            or result.source_alignment_digest != request.source_alignment.alignment_digest
            or result.bootstrap_analysis_provenance != request.bootstrap_analysis_provenance
        ):
            raise ValueError("bootstrap graph replay closure is substituted")
        return self


class BootstrapGraphSnapshotAuthorityV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot: GraphSemanticSnapshotBundleV3
    base_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_policy: GraphDependentExecutionPolicyReferenceV3
    capability_registry_snapshot: CapabilityRegistrySnapshot
    operation_lease_binding: OperationLeaseBinding
    operation_fence_binding: OperationFenceBinding
    writer_commit_binding: SemanticWriterCommitBinding
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-snapshot-authority.v3"
    _digest_field = "authority_digest"

    @model_validator(mode="after")
    def validate_authority_join(self) -> BootstrapGraphSnapshotAuthorityV3:
        if (
            self.base_read_set_digest != self.snapshot.base_read_set.read_set_digest
            or self.operation_fence_binding.source_id != self.source_id
            or self.operation_fence_binding.source_digest != self.source_digest
            or self.operation_lease_binding.operation_id != self.operation_fence_binding.operation_id
        ):
            raise ValueError("bootstrap graph authority join is invalid")
        return self


class BootstrapGraphNormalizationAuthorityMemberV3(_BootstrapV3Contract):
    """The exact policy and capability bytes sealed with normalization."""

    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_policy: GraphDependentExecutionPolicy
    execution_policy_canonical_bytes: bytes
    capability_registry: CapabilityRegistrySnapshot
    capability_registry_canonical_bytes: bytes
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-normalization-authority-member.v3"
    _digest_field = "member_digest"

    @model_validator(mode="after")
    def validate_canonical_bytes(self) -> BootstrapGraphNormalizationAuthorityMemberV3:
        policy = encode_typed_value(canonical_contract_value(self.execution_policy))
        registry = encode_typed_value(canonical_contract_value(self.capability_registry))
        if (
            self.execution_policy_canonical_bytes != policy
            or self.capability_registry_canonical_bytes != registry
        ):
            raise ValueError("bootstrap graph normalization authority bytes are not canonical")
        return self


class BootstrapGraphNormalizationAuthorityReloadV3(_BootstrapV3Contract):
    normalization_replay: BootstrapRecoveryReplayRecordV3
    normalization_atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_operation_generation: int = Field(ge=0)
    normalization_artifact_generation: int = Field(ge=0)
    authority_member: BootstrapGraphNormalizationAuthorityMemberV3
    reload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-normalization-authority-reload.v3"
    _digest_field = "reload_digest"

    @model_validator(mode="after")
    def validate_replay_member_join(self) -> BootstrapGraphNormalizationAuthorityReloadV3:
        replay = self.normalization_replay
        member = self.authority_member
        if (
            member.recovery_key_digest != replay.recovery_key_digest
            or member.normalization_request_digest != replay.source_normalization_request.request_digest
            or member.normalization_result_digest != replay.source_normalization_result.result_digest
        ):
            raise ValueError("bootstrap graph normalization authority reload is substituted")
        return self


class BootstrapGraphPreparedSourceTerminalAuthorityV3(_BootstrapV3Contract):
    prepared_source: PreparedSource
    execution_graph: IngestionExecutionGraph
    terminal_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-prepared-source-terminal-authority.v3"
    _digest_field = "terminal_authority_digest"

    @model_validator(mode="after")
    def validate_execution_graph(self) -> BootstrapGraphPreparedSourceTerminalAuthorityV3:
        if self.execution_graph != CANONICAL_INGESTION_EXECUTION_GRAPH:
            raise ValueError("bootstrap graph terminal authority uses a noncanonical execution graph")
        return self


class BootstrapGraphTransactionAuthorityProjectionV3(_BootstrapV3Contract):
    normalization_authority: BootstrapGraphNormalizationAuthorityReloadV3
    graph_authority: BootstrapGraphSnapshotAuthorityV3
    prepared_source_terminal: BootstrapGraphPreparedSourceTerminalAuthorityV3
    authority_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-transaction-authority-projection.v3"
    _digest_field = "authority_projection_digest"

    @model_validator(mode="after")
    def validate_projection_join(self) -> BootstrapGraphTransactionAuthorityProjectionV3:
        normalization = self.normalization_authority
        graph = self.graph_authority
        prepared = self.prepared_source_terminal.prepared_source
        if (
            graph.normalization_replay_digest != normalization.normalization_replay.replay_digest
            or graph.normalization_result_digest != normalization.authority_member.normalization_result_digest
            or graph.source_id != prepared.source_id
            or graph.source_digest != prepared.source_digest
            or graph.preparation_fingerprint != prepared.preparation_fingerprint
            or graph.capability_registry_snapshot != normalization.authority_member.capability_registry
            or graph.execution_policy.policy_digest != normalization.authority_member.execution_policy.policy_digest
        ):
            raise ValueError("bootstrap graph authority projection join is invalid")
        return self


class BootstrapGraphAuthorityGenerationV3(_BootstrapV3Contract):
    store_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_generation: int = Field(ge=0)
    artifact_generation: int = Field(ge=0)
    generation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-authority-generation.v3"
    _digest_field = "generation_digest"


class BootstrapGraphTransactionAuthorityWriteRequestV3(_BootstrapV3Contract):
    authority_projection: BootstrapGraphTransactionAuthorityProjectionV3
    delivery_principal_binding_digest: str
    required_outcome_scopes: RequiredOutcomeScopeSet
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    expected_normalization_operation_generation: int = Field(ge=0)
    expected_normalization_artifact_generation: int = Field(ge=0)
    write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-transaction-authority-write.v3"
    _digest_field = "write_digest"

    @model_validator(mode="after")
    def validate_write_join(self) -> BootstrapGraphTransactionAuthorityWriteRequestV3:
        graph = self.authority_projection.graph_authority
        if (
            graph.operation_fence_binding != self.operation_fence_binding
            or graph.operation_lease_binding != self.operation_lease_binding
            or graph.writer_commit_binding != self.writer_commit_binding
            or graph.required_scope_set_digest != self.required_outcome_scopes.required_scope_set_digest
            or graph.delivery_principal_binding_digest != self.delivery_principal_binding_digest
            or self.expected_normalization_operation_generation != self.authority_projection.normalization_authority.normalization_operation_generation
            or self.expected_normalization_artifact_generation != self.authority_projection.normalization_authority.normalization_artifact_generation
        ):
            raise ValueError("bootstrap graph authority write join is invalid")
        return self


class BootstrapGraphAuthorityPublicationCoreV3(_BootstrapV3Contract):
    write_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_projection: BootstrapGraphTransactionAuthorityProjectionV3
    publication_operation_generation: int = Field(ge=0)
    publication_artifact_generation: int = Field(ge=0)
    core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-authority-publication-core.v3"
    _digest_field = "core_digest"


class BootstrapGraphAuthorityPublicationReceiptV3(_BootstrapV3Contract):
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    write_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    successor_generation: BootstrapGraphAuthorityGenerationV3
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-authority-publication-receipt.v3"
    _digest_field = "receipt_digest"


class BootstrapGraphTransactionAuthorityReloadV3(_BootstrapV3Contract):
    publication_core: BootstrapGraphAuthorityPublicationCoreV3
    publication_receipt: BootstrapGraphAuthorityPublicationReceiptV3
    reload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-transaction-authority-reload.v3"
    _digest_field = "reload_digest"

    @model_validator(mode="after")
    def validate_publication_join(self) -> BootstrapGraphTransactionAuthorityReloadV3:
        core = self.publication_core
        receipt = self.publication_receipt
        projection = core.authority_projection
        if (
            receipt.write_request_digest != core.write_request_digest
            or receipt.authority_projection_digest != projection.authority_projection_digest
            or receipt.publication_core_digest != core.core_digest
            or receipt.recovery_key_digest != projection.normalization_authority.normalization_replay.recovery_key_digest
            or receipt.successor_generation.authority_projection_digest != projection.authority_projection_digest
        ):
            raise ValueError("bootstrap graph authority publication reload is substituted")
        return self


class BootstrapGraphControlEpochV3(_BootstrapV3Contract):
    request_core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    epoch: int = Field(ge=0)
    predecessor_epoch_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    transition: Literal["initial", "lease_renewed", "lease_reclaimed"]
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    issued_server_time: datetime
    issued_monotonic_tick: int = Field(ge=0)
    epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-control-epoch.v3"
    _digest_field = "epoch_digest"

    @model_validator(mode="after")
    def validate_epoch_shape(self) -> BootstrapGraphControlEpochV3:
        if self.issued_server_time.tzinfo is None or self.issued_server_time.utcoffset() != timedelta(0):
            raise ValueError("bootstrap graph epoch time must be utc")
        if (self.epoch == 0) != (self.transition == "initial") or (self.epoch == 0) != (self.predecessor_epoch_digest is None):
            raise ValueError("bootstrap graph epoch predecessor shape is invalid")
        if self.operation_fence_binding.source_id != self.source_id or self.operation_fence_binding.source_digest != self.source_digest:
            raise ValueError("bootstrap graph epoch fence is foreign")
        return self


class BootstrapGraphControlEpochTransitionRequestV3(_BootstrapV3Contract):
    request_core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_epoch_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    transition: Literal["initial", "lease_renewed", "lease_reclaimed"]
    normalization_replay: BootstrapRecoveryReplayRecordV3
    graph_authority: BootstrapGraphSnapshotAuthorityV3
    delivery_principal_binding_digest: str
    required_outcome_scopes: RequiredOutcomeScopeSet
    operation_fence: OperationFenceBinding
    operation_lease: OperationLeaseBinding
    writer_commit: SemanticWriterCommitBinding
    transition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-control-epoch-transition.v3"
    _digest_field = "transition_digest"

    @model_validator(mode="after")
    def validate_transition_join(self) -> BootstrapGraphControlEpochTransitionRequestV3:
        authority = self.graph_authority
        replay = self.normalization_replay
        if (
            authority.normalization_replay_digest != replay.replay_digest
            or authority.normalization_result_digest != replay.source_normalization_result.result_digest
            or authority.source_alignment_digest != replay.source_normalization_request.source_alignment.alignment_digest
            or self.operation_fence != authority.operation_fence_binding
            or (
                self.transition == "initial"
                and self.operation_lease != authority.operation_lease_binding
            )
            or self.writer_commit != authority.writer_commit_binding
            or self.required_outcome_scopes.required_scope_set_digest
            != authority.required_scope_set_digest
            or self.delivery_principal_binding_digest != authority.delivery_principal_binding_digest
            or (self.transition == "initial") != (self.expected_epoch_digest is None)
        ):
            raise ValueError("bootstrap graph epoch transition authority is invalid")
        return self


class BootstrapGraphControlEpochFoundV3(_BootstrapV3Contract):
    kind: Literal["found"]
    epoch: BootstrapGraphControlEpochV3
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-control-epoch-found.v3"
    _digest_field = "response_digest"


class BootstrapGraphControlEpochAdvancedV3(_BootstrapV3Contract):
    kind: Literal["advanced"]
    epoch: BootstrapGraphControlEpochV3
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-control-epoch-advanced.v3"
    _digest_field = "response_digest"


class BootstrapGraphControlEpochUnavailableV3(_BootstrapV3Contract):
    kind: Literal["unavailable"]
    request_core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal["invalid_transition", "stale_epoch", "ingress_unavailable", "scope_unavailable", "fence_superseded", "lease_unavailable", "writer_changed", "writer_unavailable", "storage_unavailable"]
    reason_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-control-epoch-unavailable.v3"
    _digest_field = "response_digest"

    @model_validator(mode="after")
    def validate_reason_digest(self) -> BootstrapGraphControlEpochUnavailableV3:
        if self.reason_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-control-epoch-unavailable-reason.v3", {"reason": self.reason}
        ):
            raise ValueError("bootstrap graph unavailable reason digest is invalid")
        return self


BootstrapGraphControlEpochTransitionResultV3: TypeAlias = Annotated[
    BootstrapGraphControlEpochFoundV3 | BootstrapGraphControlEpochAdvancedV3 | BootstrapGraphControlEpochUnavailableV3,
    Field(discriminator="kind"),
]


class BootstrapGraphDependentCoordinatorRequestV3(_BootstrapV3Contract):
    normalization_replay: BootstrapRecoveryReplayRecordV3
    source_alignment: BootstrapSourceProposalAlignmentV3
    source_dependency_groups: tuple[BootstrapSourceDependencyGroupV3, ...]
    delivery_principal_binding_digest: str
    required_outcome_scopes: RequiredOutcomeScopeSet
    graph_authority: BootstrapGraphSnapshotAuthorityV3
    request_core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_control_epoch: BootstrapGraphControlEpochV3
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-dependent-coordinator-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request_closure(self) -> BootstrapGraphDependentCoordinatorRequestV3:
        replay = self.normalization_replay
        alignment = replay.source_normalization_request.source_alignment
        if (
            self.source_alignment != alignment
            or self.source_dependency_groups != alignment.source_dependency_groups
            or self.source_dependency_groups != tuple(sorted(self.source_dependency_groups, key=lambda item: item.group_id))
            or any(item.status != "complete" for item in self.source_dependency_groups)
            or alignment.status != "complete"
            or self.graph_authority.normalization_replay_digest != replay.replay_digest
            or self.initial_control_epoch.request_core_digest != self.request_core_digest
            or self.initial_control_epoch.epoch != 0
        ):
            raise ValueError("bootstrap graph request closure is invalid")
        core = {
            "schema_version": self.schema_version,
            "normalization_replay": self.normalization_replay,
            "source_alignment": self.source_alignment,
            "source_dependency_groups": self.source_dependency_groups,
            "delivery_principal_binding_digest": self.delivery_principal_binding_digest,
            "required_outcome_scopes": self.required_outcome_scopes,
            "graph_authority": self.graph_authority,
        }
        if self.request_core_digest != contract_digest(b"memorii.semantic-ingestion.bootstrap-graph-request-core.v3", core):
            raise ValueError("bootstrap graph request core digest is invalid")
        return self


class BootstrapReservationUseAuthorizationV3(_BootstrapV3Contract):
    """A store-verifiable use grant for one reservation, not a digest alias."""

    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    reservation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-reservation-use-authorization.v3"
    _digest_field = "authorization_digest"


class BootstrapNoReservationUseV3(_BootstrapV3Contract):
    kind: Literal["none"]
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    planned_identity_reservation_digests: tuple[()] = ()
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-no-reservation-use.v3"
    _digest_field = "authority_digest"


class BootstrapIdentityReservationUseSetV3(_BootstrapV3Contract):
    kind: Literal["identity_reservations"]
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    reservation_use_authorizations: tuple[BootstrapReservationUseAuthorizationV3, ...]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-identity-reservation-use-set.v3"
    _digest_field = "authority_digest"

    @model_validator(mode="after")
    def validate_reservation_set(self) -> BootstrapIdentityReservationUseSetV3:
        values = self.reservation_use_authorizations
        if not values or any(item.transaction_group_id != self.transaction_group_id for item in values):
            raise ValueError("bootstrap graph reservation use set is invalid")
        digests = tuple(item.reservation_digest for item in values)
        if digests != tuple(sorted(set(digests))):
            raise ValueError("bootstrap graph reservation use order is invalid")
        return self


BootstrapReservationUseAuthorityV3: TypeAlias = Annotated[
    BootstrapNoReservationUseV3 | BootstrapIdentityReservationUseSetV3,
    Field(discriminator="kind"),
]


class BootstrapTransactionGroupOperationPlanV3(_BootstrapV3Contract):
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_digests: tuple[str, ...]
    segment_ids: tuple[str, ...]
    dependency_group_ids: tuple[str, ...]
    planning_result: NonPublishingIdentityPlanningResultV3 | None
    operation_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-transaction-group-operation-plan.v3"
    _digest_field = "operation_plan_digest"

    @model_validator(mode="after")
    def validate_operation_plan(self) -> BootstrapTransactionGroupOperationPlanV3:
        for values in (self.member_digests, self.segment_ids, self.dependency_group_ids):
            if not values or values != tuple(sorted(set(values))) or len(values) > 4096:
                raise ValueError("bootstrap graph operation plan vectors are invalid")
        if self.planning_result is not None and self.planning_result.frozen_artifact.operation.operation_id != self.operation_id:
            raise ValueError("bootstrap graph operation plan planning result is foreign")
        return self


class BootstrapTransactionGroupPlanMemberV3(_BootstrapV3Contract):
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_dependency_group_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_read_set: GraphReadSetToken
    reference_integrity_ledger_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_state_before: GraphPlanningState
    operation_plans: tuple[BootstrapTransactionGroupOperationPlanV3, ...]
    planning_state_after: GraphPlanningState
    required_reservation_digests: tuple[str, ...]
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-transaction-group-plan-member.v3"
    _digest_field = "member_digest"

    @property
    def operation_ids(self) -> tuple[str, ...]:
        return tuple(item.operation_id for item in self.operation_plans)

    @model_validator(mode="after")
    def validate_member_vectors(self) -> BootstrapTransactionGroupPlanMemberV3:
        if not 1 <= len(self.operation_plans) <= 256:
            raise ValueError("bootstrap graph plan member operation cardinality is invalid")
        if self.operation_ids != tuple(sorted(set(self.operation_ids))):
            raise ValueError("bootstrap graph plan member operation order is invalid")
        if self.required_reservation_digests != tuple(sorted(set(self.required_reservation_digests))):
            raise ValueError("bootstrap graph plan member reservation projection is invalid")
        state = self.planning_state_before
        for operation_plan in self.operation_plans:
            result = operation_plan.planning_result
            if result is not None:
                if result.transaction_group_id != self.transaction_group_id or result.planning_state_before_digest != state.state_digest:
                    raise ValueError("bootstrap graph plan member planning fold is discontinuous")
                state = result.planning_state_after
        if state != self.planning_state_after:
            raise ValueError("bootstrap graph plan member planning state is invalid")
        return self


class BootstrapTransactionGroupPlanV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixed_point_rounds: int = Field(ge=1)
    group_members: tuple[BootstrapTransactionGroupPlanMemberV3, ...]
    canonical_group_order: tuple[str, ...]
    execution_policy_reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_commit_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-transaction-group-plan.v3"
    _digest_field = "plan_digest"

    @model_validator(mode="after")
    def validate_plan_members(self) -> BootstrapTransactionGroupPlanV3:
        ids = tuple(member.transaction_group_id for member in self.group_members)
        if not ids or self.canonical_group_order != ids or ids != tuple(sorted(set(ids))):
            raise ValueError("bootstrap graph plan membership is invalid")
        return self


class BootstrapGroupPlanningAuthorizationV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_plan_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_ids: tuple[str, ...]
    operation_plan_digests: tuple[str, ...]
    admission_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_binding_digests: tuple[str, ...]
    reservation_use_authority: BootstrapReservationUseAuthorityV3
    graph_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_commit_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-group-planning-authorization.v3"
    _digest_field = "authorization_digest"

    @model_validator(mode="after")
    def validate_reservations(self) -> BootstrapGroupPlanningAuthorizationV3:
        if (
            not self.operation_ids
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            or len(self.operation_ids) != len(self.operation_plan_digests)
            or self.capability_binding_digests != tuple(sorted(set(self.capability_binding_digests)))
            or self.reservation_use_authority.transaction_group_id != self.transaction_group_id
        ):
            raise ValueError("bootstrap graph authorization reservations are invalid")
        return self


class BootstrapSourcePlanLineageEntryReferenceV3(_BootstrapV3Contract):
    repository_id: Literal["semantic_ingestion.bootstrap_source_plan_lineage.v3"]
    entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-plan-lineage-entry-reference.v3"
    _digest_field = "reference_digest"


class BootstrapFinalGroupResultReferenceV3(_BootstrapV3Contract):
    repository_id: Literal["semantic_ingestion.bootstrap_group_result.v3"]
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-final-group-result-reference.v3"
    _digest_field = "reference_digest"


class BootstrapGraphReplanPartitionV3(_BootstrapV3Contract):
    predecessor_attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_group_ids: tuple[str, ...]
    unfinished_group_ids: tuple[str, ...]
    replanned_group_ids: tuple[str, ...]
    partition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-replan-partition.v3"
    _digest_field = "partition_digest"

    @model_validator(mode="after")
    def validate_partition(self) -> BootstrapGraphReplanPartitionV3:
        final, unfinished, replanned = self.final_group_ids, self.unfinished_group_ids, self.replanned_group_ids
        if any(values != tuple(sorted(set(values))) for values in (final, unfinished, replanned)) or set(final) & set(unfinished) or not replanned or not set(replanned).issubset(unfinished):
            raise ValueError("bootstrap graph replan partition is invalid")
        return self


class BootstrapInitialAttemptAuthorityV3(_BootstrapV3Contract):
    kind: Literal["initial"]
    planning_authorizations: tuple[BootstrapGroupPlanningAuthorizationV3, ...]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-initial-attempt-authority.v3"
    _digest_field = "authority_digest"

    @model_validator(mode="after")
    def validate_authorizations(self) -> BootstrapInitialAttemptAuthorityV3:
        group_ids = tuple(item.transaction_group_id for item in self.planning_authorizations)
        authorization_digests = tuple(
            item.authorization_digest for item in self.planning_authorizations
        )
        if (
            not group_ids
            or group_ids != tuple(sorted(set(group_ids)))
            or len(set(authorization_digests)) != len(authorization_digests)
        ):
            raise ValueError("bootstrap initial authorizations are invalid")
        return self


class _BootstrapSuccessorGroupAuthorityV3(_BootstrapV3Contract):
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_lineage_entry: BootstrapSourcePlanLineageEntryReferenceV3
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class BootstrapReusedCommittedGroupAuthorityV3(_BootstrapSuccessorGroupAuthorityV3):
    kind: Literal["reused_committed"]
    predecessor_final_result: BootstrapFinalGroupResultReferenceV3
    predecessor_group_plan_member: BootstrapTransactionGroupPlanMemberV3
    predecessor_planning_authorization: BootstrapGroupPlanningAuthorizationV3
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-reused-committed-group-authority.v3"
    _digest_field = "authority_digest"


class BootstrapReusedFinalGroupAuthorityV3(_BootstrapSuccessorGroupAuthorityV3):
    kind: Literal["reused_final"]
    predecessor_final_result: BootstrapFinalGroupResultReferenceV3
    predecessor_group_plan_member: BootstrapTransactionGroupPlanMemberV3
    terminal_disposition: Literal["noncommitting", "failed"]
    planning_authorization: BootstrapGroupPlanningAuthorizationV3 | None
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-reused-final-group-authority.v3"
    _digest_field = "authority_digest"


class BootstrapReusedUnfinishedGroupAuthorityV3(_BootstrapSuccessorGroupAuthorityV3):
    kind: Literal["reused_unfinished"]
    predecessor_group_plan_member: BootstrapTransactionGroupPlanMemberV3
    predecessor_planning_authorization: BootstrapGroupPlanningAuthorizationV3
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-reused-unfinished-group-authority.v3"
    _digest_field = "authority_digest"


class BootstrapReplacementGroupAuthorityV3(_BootstrapSuccessorGroupAuthorityV3):
    kind: Literal["replacement"]
    replacement_group_plan_member: BootstrapTransactionGroupPlanMemberV3
    replacement_planning_authorization: BootstrapGroupPlanningAuthorizationV3
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-replacement-group-authority.v3"
    _digest_field = "authority_digest"


BootstrapSuccessorGroupAuthorityV3: TypeAlias = Annotated[
    BootstrapReusedCommittedGroupAuthorityV3 | BootstrapReusedFinalGroupAuthorityV3 |
    BootstrapReusedUnfinishedGroupAuthorityV3 | BootstrapReplacementGroupAuthorityV3,
    Field(discriminator="kind"),
]


class BootstrapSuccessorAttemptAuthorityV3(_BootstrapV3Contract):
    kind: Literal["successor"]
    predecessor_attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    replan_partition: BootstrapGraphReplanPartitionV3
    group_member_authorities: tuple[BootstrapSuccessorGroupAuthorityV3, ...]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-successor-attempt-authority.v3"
    _digest_field = "authority_digest"

    @model_validator(mode="after")
    def validate_successor_authorities(self) -> BootstrapSuccessorAttemptAuthorityV3:
        authorities = self.group_member_authorities
        ids = tuple(value.transaction_group_id for value in authorities)
        if (
            not ids or ids != tuple(sorted(set(ids)))
            or self.predecessor_attempt_digest != self.replan_partition.predecessor_attempt_digest
            or self.predecessor_lineage_digest != self.replan_partition.predecessor_lineage_digest
        ):
            raise ValueError("bootstrap successor authority closure is invalid")
        final_ids, unfinished, replanned = (
            set(self.replan_partition.final_group_ids),
            set(self.replan_partition.unfinished_group_ids),
            set(self.replan_partition.replanned_group_ids),
        )
        expected = final_ids | unfinished
        if set(ids) != expected:
            raise ValueError("bootstrap successor authority partition is incomplete")
        for authority in authorities:
            if authority.transaction_group_id in replanned and authority.kind != "replacement":
                raise ValueError("bootstrap replanned group must be replacement")
            if authority.transaction_group_id in unfinished - replanned and authority.kind != "reused_unfinished":
                raise ValueError("bootstrap unreplanned unfinished group must be reused")
            if authority.transaction_group_id in final_ids and authority.kind not in {"reused_committed", "reused_final"}:
                raise ValueError("bootstrap final group authority is invalid")
        return self


BootstrapGraphAttemptAuthorityV3: TypeAlias = Annotated[
    BootstrapInitialAttemptAuthorityV3 | BootstrapSuccessorAttemptAuthorityV3,
    Field(discriminator="kind"),
]


class BootstrapGraphDependentAttemptV3(_BootstrapV3Contract):
    attempt_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_index: int = Field(ge=0)
    trigger: Literal["initial_plan", "prior_group_commit", "related_version_conflict"]
    attempt_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_dependency_group_digests: tuple[str, ...]
    graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_set_extension_digests: tuple[str, ...]
    reconciliation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_binding_digests: tuple[str, ...]
    reservation_use_authorization_digests: tuple[str, ...]
    transaction_group_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_authority: BootstrapGraphAttemptAuthorityV3
    execution_policy_reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_commit_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_counters_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["eligible", "superseded", "rejected", "unresolved", "failed"]
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-dependent-attempt.v3"
    _digest_field = "attempt_digest"

    @model_validator(mode="after")
    def validate_attempt_authority(self) -> BootstrapGraphDependentAttemptV3:
        if (self.attempt_index == 0) != (self.trigger == "initial_plan") or (self.attempt_index == 0) != (self.attempt_authority.kind == "initial"):
            raise ValueError("bootstrap graph attempt authority is invalid")
        for values in (self.source_dependency_group_digests, self.read_set_extension_digests, self.capability_binding_digests, self.reservation_use_authorization_digests):
            if values != tuple(sorted(set(values))):
                raise ValueError("bootstrap graph attempt vector is invalid")
        return self


class BootstrapSourcePlanLineageEntryV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_ordinal: int = Field(ge=0)
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_entry_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_dependency_group_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_plan_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_group_result_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    disposition: Literal["planned", "committed", "noncommitting", "superseded"]
    operation_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_commit_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-plan-lineage-entry.v3"
    _digest_field = "entry_digest"


class BootstrapSourcePlanLineageV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: tuple[BootstrapSourcePlanLineageEntryV3, ...]
    latest_entry_by_group: tuple[tuple[str, str], ...]
    lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-source-plan-lineage.v3"
    _digest_field = "lineage_digest"

    @model_validator(mode="after")
    def validate_lineage(self) -> BootstrapSourcePlanLineageV3:
        if not self.entries or tuple(item.lineage_ordinal for item in self.entries) != tuple(range(len(self.entries))):
            raise ValueError("bootstrap graph lineage order is invalid")
        latest_by_group: dict[str, str] = {}
        for entry in self.entries:
            predecessor = latest_by_group.get(entry.transaction_group_id)
            if predecessor is None:
                if entry.predecessor_entry_digest is not None:
                    raise ValueError("bootstrap graph initial lineage predecessor is invalid")
            elif entry.predecessor_entry_digest != predecessor:
                raise ValueError("bootstrap graph successor lineage predecessor is invalid")
            latest_by_group[entry.transaction_group_id] = entry.entry_digest
        latest = tuple(sorted(latest_by_group.items()))
        if self.latest_entry_by_group != latest:
            raise ValueError("bootstrap graph lineage latest projection is invalid")
        return self


class BootstrapGraphGroupResultV3(_BootstrapV3Contract):
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_plan_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: Literal["committed", "noncommitting", "failed"]
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-result.v3"
    _digest_field = "result_digest"


class BootstrapSourceOperationMembershipV3(_BootstrapV3Contract):
    """Pre-compilation source order; it deliberately has no plan reference."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_dependency_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_group_ordinal: int = Field(ge=0)
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_ordinal: int = Field(ge=0)
    operation_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    membership_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.source-operation-membership.v3"
    _digest_field = "membership_digest"


class BootstrapCanonicalClusterReferenceOccurrenceV3(_BootstrapV3Contract):
    membership: BootstrapSourceOperationMembershipV3
    source_local_cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurrence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.canonical-cluster-reference-occurrence.v3"
    _digest_field = "occurrence_digest"


class BootstrapCanonicalFirstUseConsumerV3(_BootstrapV3Contract):
    occurrence: BootstrapCanonicalClusterReferenceOccurrenceV3
    consumer_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.canonical-first-use-consumer.v3"
    _digest_field = "consumer_digest"


class BootstrapCanonicalFirstUseDependencyV3(_BootstrapV3Contract):
    source_local_cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_identity_proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_membership: BootstrapSourceOperationMembershipV3
    producer_occurrences: tuple[BootstrapCanonicalClusterReferenceOccurrenceV3, ...]
    consumers: tuple[BootstrapCanonicalFirstUseConsumerV3, ...]
    dependency_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.canonical-first-use-dependency.v3"
    _digest_field = "dependency_digest"

    @model_validator(mode="after")
    def validate_occurrences(self) -> BootstrapCanonicalFirstUseDependencyV3:
        producer_keys = tuple(item.source_coordinate_digest for item in self.producer_occurrences)
        consumer_keys = tuple(item.occurrence.source_coordinate_digest for item in self.consumers)
        if (
            not producer_keys
            or producer_keys != tuple(sorted(set(producer_keys)))
            or len(set(consumer_keys)) != len(consumer_keys)
            or any(item.source_local_cluster_id != self.source_local_cluster_id for item in self.producer_occurrences)
            or any(item.occurrence.source_local_cluster_id != self.source_local_cluster_id for item in self.consumers)
        ):
            raise ValueError("canonical first-use occurrences are invalid")
        return self


class BootstrapCanonicalPlanningPrefixProofV3(_BootstrapV3Contract):
    authority_base_planning_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    membership: BootstrapSourceOperationMembershipV3
    preceding_memberships: tuple[BootstrapSourceOperationMembershipV3, ...]
    prefix_planning_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_producer_record_digests: tuple[str, ...]
    prefix_proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.canonical-planning-prefix-proof.v3"
    _digest_field = "prefix_proof_digest"


class BootstrapGraphTargetReferenceV3(_BootstrapV3Contract):
    """A snapshot-bound graph target; no ambient resolver may supply one."""

    record_kind: GraphRecordKind
    record_id: str = Field(min_length=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-target-reference.v3"
    _digest_field = "target_digest"


class BootstrapNativeTargetPlanningRequestV3(_BootstrapV3Contract):
    """Closed input to the pure V3 target/materialization boundary."""

    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_input: BootstrapNativeOperationReductionInputV3
    sealed_snapshot: SealedGraphStateSnapshot
    effective_read_set: GraphReadSet
    current_planning_state: GraphPlanningState
    target_resolution_authority: BootstrapNativeTargetResolutionAuthorityV3
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-target-planning-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_request(self) -> BootstrapNativeTargetPlanningRequestV3:
        if (
            self.effective_read_set.read_set_digest != self.sealed_snapshot.read_set.read_set_digest
            or self.current_planning_state.base_snapshot_digest != self.sealed_snapshot.snapshot_digest
        ):
            raise ValueError("native target planning authority is substituted")
        return self


class BootstrapSnapshotTargetAuthorityV3(_BootstrapV3Contract):
    kind: Literal["snapshot"]
    target: BootstrapGraphTargetReferenceV3
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-snapshot-target-authority.v3"
    _digest_field = "authority_digest"

    @model_validator(mode="after")
    def validate_snapshot_target(self) -> BootstrapSnapshotTargetAuthorityV3:
        if self.target.record_digest != self.snapshot_record_digest:
            raise ValueError("native snapshot target record is substituted")
        return self


class BootstrapPendingTargetAuthorityV3(_BootstrapV3Contract):
    kind: Literal["pending"]
    target: BootstrapGraphTargetReferenceV3
    source_local_cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    producing_transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_membership_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_prefix_proof: BootstrapCanonicalPlanningPrefixProofV3
    planning_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-pending-target-authority.v3"
    _digest_field = "authority_digest"

    @model_validator(mode="after")
    def validate_pending_target(self) -> BootstrapPendingTargetAuthorityV3:
        if self.target.record_digest != self.planning_record_digest:
            raise ValueError("native pending target record is substituted")
        return self


class BootstrapNewFirstUseTargetAuthorityV3(_BootstrapV3Contract):
    kind: Literal["new_first_use"]
    target: BootstrapGraphTargetReferenceV3
    source_local_cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_identity_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planned_identity_reservation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_producer_operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_producer_source_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_producer_transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_producer_membership_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_prefix_proof: BootstrapCanonicalPlanningPrefixProofV3
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.new-first-use-target-authority.v3"
    _digest_field = "authority_digest"

    @model_validator(mode="after")
    def validate_seed_coordinate(self) -> BootstrapNewFirstUseTargetAuthorityV3:
        if self.source_coordinate_digest != self.seed_producer_source_coordinate_digest:
            raise ValueError("new first-use target coordinate is substituted")
        return self


BootstrapNativeTargetAuthorityV3 = Annotated[
    BootstrapSnapshotTargetAuthorityV3
    | BootstrapPendingTargetAuthorityV3
    | BootstrapNewFirstUseTargetAuthorityV3,
    Field(discriminator="kind"),
]


class BootstrapNativeTargetBindingV3(_BootstrapV3Contract):
    role: Literal[
        "fact_subject", "fact_object", "corrected_target", "retracted_target",
        "action_participant", "identity_predecessor", "identity_successor",
        "identity_reference_target",
    ]
    source_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority: BootstrapNativeTargetAuthorityV3
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-target-binding.v3"
    _digest_field = "binding_digest"


class BootstrapCanonicalIdentityDecisionProofV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_local_cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    mention_digests: tuple[str, ...]
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized_scope_identity: str = Field(min_length=1)
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_base_planning_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_partition_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_local_resolution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    alias_proof_digests: tuple[str, ...]
    type_proof_digests: tuple[str, ...]
    proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.canonical-identity-decision-proof.v3"
    _digest_field = "proof_digest"


class BootstrapExistingCanonicalIdentityDecisionV3(_BootstrapV3Contract):
    kind: Literal["existing"]
    proof: BootstrapCanonicalIdentityDecisionProofV3
    target: BootstrapGraphTargetReferenceV3
    snapshot_or_pending_authority: BootstrapNativeTargetAuthorityV3
    alias_record_ids: tuple[str, ...]
    type_evidence_record_ids: tuple[str, ...]
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.existing-canonical-identity-decision.v3"
    _digest_field = "decision_digest"


class BootstrapNewCanonicalIdentityAllocationV3(_BootstrapV3Contract):
    kind: Literal["new"]
    proof: BootstrapCanonicalIdentityDecisionProofV3
    allocation_namespace_id: str = Field(min_length=1)
    allocation_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    allocation_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    logical_entity_id: str = Field(min_length=1)
    entity_revision_id: str = Field(min_length=1)
    alias_proofs: tuple[BootstrapProposalEvidenceItemV3, ...]
    type_proofs: tuple[BootstrapProposalEvidenceItemV3, ...]
    planned_identity_reservation: PlannedIdentityReservation
    seed_producer_operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_producer_source_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    allocation_proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.new-canonical-identity-allocation.v3"
    _digest_field = "decision_digest"


class BootstrapAbsentCanonicalIdentityDecisionV3(_BootstrapV3Contract):
    kind: Literal["absent"]
    proof: BootstrapCanonicalIdentityDecisionProofV3
    reason: Literal[
        "no_binding_proof", "ambiguous_existing", "allocation_forbidden",
        "incomplete_alias_type_proof", "scope_unavailable",
    ]
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.absent-canonical-identity-decision.v3"
    _digest_field = "decision_digest"


BootstrapCanonicalIdentityClusterDecisionV3 = Annotated[
    BootstrapExistingCanonicalIdentityDecisionV3
    | BootstrapNewCanonicalIdentityAllocationV3
    | BootstrapAbsentCanonicalIdentityDecisionV3,
    Field(discriminator="kind"),
]


class BootstrapCanonicalIdentityBindingAllocationAuthorityV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    recovery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_base_planning_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized_scope_identity: str = Field(min_length=1)
    allocation_namespace_id: str = Field(min_length=1)
    source_operation_memberships: tuple[BootstrapSourceOperationMembershipV3, ...]
    referenced_cluster_ids: tuple[str, ...]
    cluster_decisions: tuple[BootstrapCanonicalIdentityClusterDecisionV3, ...]
    first_use_dependencies: tuple[BootstrapCanonicalFirstUseDependencyV3, ...]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.canonical-identity-binding-allocation-authority.v3"
    _digest_field = "authority_digest"


class BootstrapCanonicalIdentityBindingAllocationReloadV3(_BootstrapV3Contract):
    authority: BootstrapCanonicalIdentityBindingAllocationAuthorityV3
    source_plan_checkpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_generation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.canonical-identity-binding-allocation-reload.v3"
    _digest_field = "reload_digest"


class BootstrapCanonicalIdentityAuthorityWriteRequestV3(_BootstrapV3Contract):
    """Separate pre-plan persistence request for the v69 authority reload."""

    authority_reload: BootstrapCanonicalIdentityBindingAllocationReloadV3
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    delivery_principal_binding_digest: str
    required_outcome_scopes: RequiredOutcomeScopeSet
    write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.canonical-identity-authority-write.v3"
    _digest_field = "write_digest"

    @model_validator(mode="after")
    def validate_write(self) -> BootstrapCanonicalIdentityAuthorityWriteRequestV3:
        authority = self.authority_reload.authority
        if (
            authority.required_scope_set_digest != self.required_outcome_scopes.required_scope_set_digest
            or authority.source_id != self.operation_fence_binding.source_id
            or authority.source_digest != self.operation_fence_binding.source_digest
        ):
            raise ValueError("canonical identity authority write binding is substituted")
        return self


class BootstrapNativeMentionTargetCandidateV3(_BootstrapV3Contract):
    mention_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_local_cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_identity_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_identity_proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_authority: BootstrapNativeTargetAuthorityV3
    logical_entity_id: str = Field(min_length=1)
    entity_revision_id: str = Field(min_length=1)
    alias_record_ids: tuple[str, ...]
    type_evidence_record_ids: tuple[str, ...]
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-mention-target-candidate.v3"
    _digest_field = "candidate_digest"


class BootstrapNativeSelectorTargetV3(_BootstrapV3Contract):
    selector_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selector_kind: Literal["claim", "action", "alias"]
    target_authority: BootstrapNativeTargetAuthorityV3
    target_record_kind: Literal["claim_assertion", "action_revision", "alias_revision"]
    target_record_id: str = Field(min_length=1)
    target_record_planning_or_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selector_target_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-selector-target.v3"
    _digest_field = "selector_target_digest"


class BootstrapNativeTargetResolutionAuthorityV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_prefix_proof: BootstrapCanonicalPlanningPrefixProofV3
    canonical_identity_authority: BootstrapCanonicalIdentityBindingAllocationReloadV3
    mention_candidates: tuple[BootstrapNativeMentionTargetCandidateV3, ...]
    selector_targets: tuple[BootstrapNativeSelectorTargetV3, ...]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-target-resolution-authority.v3"
    _digest_field = "authority_digest"


class BootstrapNativePlanningRecordV3(_BootstrapV3Contract):
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_kind: GraphRecordKind
    record_id: str = Field(min_length=1)
    precondition: PlanningRecordPrecondition
    planning_payload: CanonicalPlanningRecordPayload
    source_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-planning-record.v3"
    _digest_field = "record_digest"

    @model_validator(mode="after")
    def validate_planning_record(self) -> BootstrapNativePlanningRecordV3:
        if self.planning_payload.record_kind != self.record_kind:
            raise ValueError("native planning record kind is substituted")
        return self


class BootstrapNativeTemporalTerminalBindingV3(_BootstrapV3Contract):
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_role: str = Field(min_length=1)
    temporal_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-temporal-terminal-binding.v3"
    _digest_field = "binding_digest"


class BootstrapNativeEvidenceProjectionV3(_BootstrapV3Contract):
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_item_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    citation_record: BootstrapNativePlanningRecordV3
    provenance_record: BootstrapNativePlanningRecordV3
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-evidence-projection.v3"
    _digest_field = "projection_digest"


class BootstrapNativeEntitySeedV3(_BootstrapV3Contract):
    """The one permitted source-wide entity creation seed for a new cluster."""

    kind: Literal["entity"]
    source_local_cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    mention_digests: tuple[str, ...]
    canonical_identity_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_identity_proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_producer_operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_producer_source_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    logical_entity_id: str = Field(min_length=1)
    entity_revision_id: str = Field(min_length=1)
    entity_revision: PlanningEntityRevision
    aliases: tuple[PlanningAliasRevision, ...]
    type_evidence: tuple[PlanningTypeEvidence, ...]
    alias_type_proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-entity-seed.v3"
    _digest_field = "seed_digest"


class BootstrapNativeFactPlanningSeedV3(_BootstrapV3Contract):
    kind: Literal["fact"]
    fact: BootstrapProposalFactV3
    subject_target: BootstrapNativeTargetBindingV3
    object_target: BootstrapNativeTargetBindingV3 | None
    created_entities: tuple[BootstrapNativeEntitySeedV3, ...]
    claim_assertion: PlanningClaimAssertion
    claim_projection: PlanningClaimProjection
    relation_revision: PlanningRelationRevision | None
    citations: tuple[PlanningCitation, ...]
    provenances: tuple[PlanningProvenance, ...]
    terminal_bindings: tuple[BootstrapNativeTemporalTerminalBindingV3, ...]
    seed_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-fact-planning-seed.v3"
    _digest_field = "seed_digest"


class BootstrapNativeCorrectionPlanningSeedV3(_BootstrapV3Contract):
    kind: Literal["correction"]
    selector_targets: tuple[BootstrapNativeSelectorTargetV3, ...]
    transitions: tuple[PlanningTemporalTransition, ...]
    replacement_fact: BootstrapNativeFactPlanningSeedV3
    seed_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-correction-planning-seed.v3"
    _digest_field = "seed_digest"


class BootstrapNativeRetractionPlanningSeedV3(_BootstrapV3Contract):
    kind: Literal["retraction"]
    selector_targets: tuple[BootstrapNativeSelectorTargetV3, ...]
    transitions: tuple[PlanningTemporalTransition, ...]
    citations: tuple[PlanningCitation, ...]
    provenances: tuple[PlanningProvenance, ...]
    seed_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-retraction-planning-seed.v3"
    _digest_field = "seed_digest"


class BootstrapNativeActionPlanningSeedV3(_BootstrapV3Contract):
    kind: Literal["action_state"]
    participant_targets: tuple[BootstrapNativeTargetBindingV3, ...]
    created_entities: tuple[BootstrapNativeEntitySeedV3, ...]
    action_revision: PlanningActionRevision
    citations: tuple[PlanningCitation, ...]
    provenances: tuple[PlanningProvenance, ...]
    terminal_bindings: tuple[BootstrapNativeTemporalTerminalBindingV3, ...]
    seed_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-action-planning-seed.v3"
    _digest_field = "seed_digest"


class BootstrapNativeIdentityMaterializationV3(_BootstrapV3Contract):
    canonical_identity_authority: BootstrapCanonicalIdentityBindingAllocationReloadV3
    graph_free_identity_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    fresh_planning_result: NonPublishingIdentityPlanningResultV3
    revision_and_alias_records: tuple[BootstrapNativePlanningRecordV3, ...]
    lineage_record: BootstrapNativePlanningRecordV3
    reference_disposition_records: tuple[BootstrapNativePlanningRecordV3, ...]
    identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-identity-materialization.v3"
    _digest_field = "identity_digest"


class BootstrapNativeIdentityPlanningSeedV3(_BootstrapV3Contract):
    kind: Literal["identity"]
    predecessor_targets: tuple[BootstrapNativeTargetBindingV3, ...]
    successor_targets: tuple[BootstrapNativeTargetBindingV3, ...]
    selector_targets: tuple[BootstrapNativeSelectorTargetV3, ...]
    admission: BootstrapNativeIdentityAdmissionV3
    materialization: BootstrapNativeIdentityMaterializationV3
    citations: tuple[PlanningCitation, ...]
    provenances: tuple[PlanningProvenance, ...]
    seed_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-identity-planning-seed.v3"
    _digest_field = "seed_digest"


BootstrapNativeOperationPlanningSeedV3 = Annotated[
    BootstrapNativeFactPlanningSeedV3
    | BootstrapNativeCorrectionPlanningSeedV3
    | BootstrapNativeRetractionPlanningSeedV3
    | BootstrapNativeActionPlanningSeedV3
    | BootstrapNativeIdentityPlanningSeedV3,
    Field(discriminator="kind"),
]


class BootstrapGraphTargetMaterializationPlanV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_kind: Literal["fact", "correction", "retraction", "action_state", "identity"]
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_state_before_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_bindings: tuple[BootstrapNativeTargetBindingV3, ...]
    operation_seed: BootstrapNativeOperationPlanningSeedV3
    planning_records: tuple[BootstrapNativePlanningRecordV3, ...]
    terminal_bindings: tuple[BootstrapNativeTemporalTerminalBindingV3, ...]
    evidence_projections: tuple[BootstrapNativeEvidenceProjectionV3, ...]
    identity_materialization: BootstrapNativeIdentityMaterializationV3 | None
    planning_state_after: GraphPlanningState
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.target-materialization-plan.v3"
    _digest_field = "plan_digest"

    @model_validator(mode="after")
    def validate_plan_order(self) -> BootstrapGraphTargetMaterializationPlanV3:
        record_keys = tuple((item.record_kind, item.record_id, item.record_digest) for item in self.planning_records)
        if record_keys != tuple(sorted(set(record_keys))):
            raise ValueError("native target plan records are not canonical")
        if self.planning_state_after.base_snapshot_digest != self.sealed_snapshot_digest:
            raise ValueError("native target plan state authority is substituted")
        return self


class BootstrapNativePlanningUnavailableV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["unresolved", "rejected", "evidence_only"]
    reason_codes: tuple[BootstrapNativeTerminalReasonV3, ...]
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_state_before_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    unavailable_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-planning-unavailable.v3"
    _digest_field = "unavailable_digest"

    @model_validator(mode="after")
    def validate_unavailable(self) -> BootstrapNativePlanningUnavailableV3:
        if not self.reason_codes or self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("native planning unavailable reasons are invalid")
        return self


class BootstrapNativeRecordMaterializationIntentV3(_BootstrapV3Contract):
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_kind: GraphRecordKind
    record_id: str = Field(min_length=1)
    mutation_kind: Literal["create", "update"]
    expected_prior_record_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    canonical_after_record: CanonicalPlanningRecordPayload
    source_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    intent_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-record-intent.v3"
    _digest_field = "intent_digest"

    @model_validator(mode="after")
    def validate_intent(self) -> BootstrapNativeRecordMaterializationIntentV3:
        if self.canonical_after_record.record_kind != self.record_kind:
            raise ValueError("native record intent kind is substituted")
        return self


class BootstrapNativeFactEffectV3(_BootstrapV3Contract):
    kind: Literal["fact"]
    fact: BootstrapProposalFactV3
    target_bindings: tuple[BootstrapNativeTargetBindingV3, ...]
    planning_records: tuple[BootstrapNativePlanningRecordV3, ...]
    terminal_bindings: tuple[BootstrapNativeTemporalTerminalBindingV3, ...]
    evidence_projections: tuple[BootstrapNativeEvidenceProjectionV3, ...]
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-fact-effect.v3"
    _digest_field = "effect_digest"


class BootstrapNativeCorrectionEffectV3(_BootstrapV3Contract):
    kind: Literal["correction"]
    correction: BootstrapProposalCorrectionV3
    corrected_targets: tuple[BootstrapNativeTargetBindingV3, ...]
    replacement_effect: BootstrapNativeFactEffectV3
    transition_records: tuple[BootstrapNativePlanningRecordV3, ...]
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-correction-effect.v3"
    _digest_field = "effect_digest"

    @model_validator(mode="after")
    def validate_replacement(self) -> BootstrapNativeCorrectionEffectV3:
        if self.replacement_effect.fact != self.correction.replacement_fact:
            raise ValueError("native correction replacement fact is substituted")
        return self


class BootstrapNativeRetractionEffectV3(_BootstrapV3Contract):
    kind: Literal["retraction"]
    retraction: BootstrapProposalRetractionV3
    retracted_targets: tuple[BootstrapNativeTargetBindingV3, ...]
    transition_records: tuple[BootstrapNativePlanningRecordV3, ...]
    evidence_projections: tuple[BootstrapNativeEvidenceProjectionV3, ...]
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-retraction-effect.v3"
    _digest_field = "effect_digest"


class BootstrapNativeActionStateEffectV3(_BootstrapV3Contract):
    kind: Literal["action_state"]
    action_state: BootstrapProposalActionStateV3
    resolved_participants: tuple[BootstrapNativeTargetBindingV3, ...]
    planning_records: tuple[BootstrapNativePlanningRecordV3, ...]
    terminal_bindings: tuple[BootstrapNativeTemporalTerminalBindingV3, ...]
    evidence_projections: tuple[BootstrapNativeEvidenceProjectionV3, ...]
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-action-state-effect.v3"
    _digest_field = "effect_digest"


class BootstrapNativeIdentityEffectV3(_BootstrapV3Contract):
    kind: Literal["identity"]
    identity_operation: BootstrapProposalIdentityOperationV3
    materialization: BootstrapNativeIdentityMaterializationV3
    target_bindings: tuple[BootstrapNativeTargetBindingV3, ...]
    terminal_bindings: tuple[BootstrapNativeTemporalTerminalBindingV3, ...]
    evidence_projections: tuple[BootstrapNativeEvidenceProjectionV3, ...]
    effect_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-identity-effect.v3"
    _digest_field = "effect_digest"


BootstrapNativeAcceptedOperationEffectV3 = Annotated[
    BootstrapNativeFactEffectV3
    | BootstrapNativeCorrectionEffectV3
    | BootstrapNativeRetractionEffectV3
    | BootstrapNativeActionStateEffectV3
    | BootstrapNativeIdentityEffectV3,
    Field(discriminator="kind"),
]

BootstrapNativeTerminalReasonV3 = Literal[
    "coverage_unresolved", "parser_disagreement", "scope_disagreement",
    "temporal_disagreement", "graph_target_missing", "graph_target_ambiguous",
    "stale_reference", "forbidden_domain", "policy_denied",
    "identity_plan_unavailable", "reference_closure_incomplete",
    "supported_evidence_not_promotable",
]


class BootstrapNativeIdentityAdmissionRequestV3(_BootstrapV3Contract):
    """Request-bound identity admission; it never carries a live store handle."""

    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_free_input: BootstrapGraphFreeIdentityPlanningInputV3
    sealed_snapshot: SealedGraphStateSnapshot
    effective_read_set: GraphReadSet
    current_planning_state: GraphPlanningState
    predecessor_identity_materialization: BootstrapNativeIdentityMaterializationV3 | None
    mode: Literal["initial", "replacement", "reuse"]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-identity-admission-request.v3"
    _digest_field = "request_digest"

    @model_validator(mode="after")
    def validate_admission_request(self) -> BootstrapNativeIdentityAdmissionRequestV3:
        predecessor = self.predecessor_identity_materialization
        if self.effective_read_set.read_set_digest != self.sealed_snapshot.read_set.read_set_digest:
            raise ValueError("native identity admission read set is substituted")
        if (self.mode == "initial") != (predecessor is None):
            raise ValueError("native identity admission mode/nullability is invalid")
        if predecessor is not None:
            result = predecessor.fresh_planning_result
            records = (
                *predecessor.revision_and_alias_records,
                predecessor.lineage_record,
                *predecessor.reference_disposition_records,
            )
            if (
                result.transaction_group_id != self.transaction_group_id
                or predecessor.graph_free_identity_input_digest != self.graph_free_input.input_digest
                or any(item.operation_execution_id != self.operation_execution_id for item in records)
            ):
                raise ValueError("native identity admission predecessor is substituted")
        return self


class BootstrapNativeIdentityAdmissionV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_operation_artifact: AcceptedIdentityOperationArtifact
    trusted_decision: TrustedAcceptedIdentityOperationDecision
    authority_verification: VerifiedIdentityDecisionAuthority
    planning_result: NonPublishingIdentityPlanningResultV3
    admission_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-identity-admission.v3"
    _digest_field = "admission_digest"


class BootstrapGraphTargetMaterializationPlannerV3(Protocol):
    def plan(
        self, *, request: BootstrapNativeTargetPlanningRequestV3
    ) -> BootstrapGraphTargetMaterializationPlanV3 | BootstrapNativePlanningUnavailableV3: ...


class BootstrapNativeIdentityAdmissionPortV3(Protocol):
    def admit_and_plan(
        self, *, request: BootstrapNativeIdentityAdmissionRequestV3
    ) -> BootstrapNativeIdentityAdmissionV3 | BootstrapNativePlanningUnavailableV3: ...


class SemanticSealedOperation(_BootstrapV3Contract):
    """The native, snapshot-bound sealed operation carrier used by V3 only."""

    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_kind: Literal["fact", "correction", "retraction", "action_state", "identity"]
    source_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-sealed-operation.v3"
    _digest_field = "sealed_operation_digest"


class BootstrapNativeOperationCompilationV3(_BootstrapV3Contract):
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_input: BootstrapNativeOperationReductionInputV3
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_member: BootstrapProposalOperationMemberV3
    resolved_graph_targets: tuple[BootstrapGraphTargetReferenceV3, ...]
    sealed_operations: tuple[SemanticSealedOperation, ...]
    accepted_carriers: tuple[SemanticDurableCarrier, ...]
    terminal_binding_sets: tuple[SemanticTerminalBindingSet, ...]
    terminal_status: Literal["accepted", "unresolved", "rejected", "evidence_only"]
    reason_codes: tuple[BootstrapNativeTerminalReasonV3, ...]
    compilation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-operation-compilation.v3"
    _digest_field = "compilation_digest"

    @model_validator(mode="after")
    def validate_native_compilation(self) -> BootstrapNativeOperationCompilationV3:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("native compilation reasons are not canonical")
        if (
            self.operation_input.operation_id != self.operation_id
            or self.operation_input.operation_execution_id != self.operation_execution_id
            or self.operation_input.operation_member != self.operation_member
            or (self.terminal_status == "accepted") != (not self.reason_codes)
        ):
            raise ValueError("native compilation input/status closure is invalid")
        if (self.terminal_status == "accepted") != (not self.reason_codes):
            raise ValueError("native compilation status/reason partition is invalid")
        return self


class BootstrapNativeOperationEffectMaterializationV3(_BootstrapV3Contract):
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_status: Literal["accepted", "unresolved", "rejected", "evidence_only"]
    accepted_effect: BootstrapNativeAcceptedOperationEffectV3 | None
    record_intents: tuple[BootstrapNativeRecordMaterializationIntentV3, ...]
    observation_disposition: Literal["committed", "unresolved", "rejected", "evidence_only"]
    observation_reason_codes: tuple[BootstrapNativeTerminalReasonV3, ...]
    materialization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-operation-effect-materialization.v3"
    _digest_field = "materialization_digest"

    @model_validator(mode="after")
    def validate_materialization(self) -> BootstrapNativeOperationEffectMaterializationV3:
        if self.observation_reason_codes != tuple(sorted(set(self.observation_reason_codes))):
            raise ValueError("native observation reasons are not canonical")
        if self.terminal_status == "accepted":
            if self.accepted_effect is None or not self.record_intents or self.observation_disposition != "committed" or self.observation_reason_codes:
                raise ValueError("accepted native materialization is incomplete")
        elif self.accepted_effect is not None or self.record_intents or self.observation_disposition != self.terminal_status:
            raise ValueError("nonaccepting native materialization has effects")
        return self


class BootstrapNativeOperationTerminalV3(_BootstrapV3Contract):
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_kind: Literal["fact", "correction", "retraction", "action_state", "identity"]
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    native_compilation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["accepted", "unresolved", "rejected", "evidence_only"]
    reason_codes: tuple[BootstrapNativeTerminalReasonV3, ...]
    coverage_binding_digests: tuple[str, ...]
    accepted_effect_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    record_intent_digests: tuple[str, ...]
    terminal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-operation-terminal.v3"
    _digest_field = "terminal_digest"


class BootstrapNativeOperationArtifactClosureV3(_BootstrapV3Contract):
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    native_compilation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_effect_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    record_intent_digests: tuple[str, ...]
    coverage_binding_digests: tuple[str, ...]
    graph_target_digests: tuple[str, ...]
    planning_result_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-operation-artifact-closure.v3"
    _digest_field = "closure_digest"


class BootstrapGraphOperationReductionV3(_BootstrapV3Contract):
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    native_compilation: BootstrapNativeOperationCompilationV3
    native_terminal: BootstrapNativeOperationTerminalV3
    native_artifact_closure: BootstrapNativeOperationArtifactClosureV3
    effect_materialization: BootstrapNativeOperationEffectMaterializationV3
    reduction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.graph-operation-reduction.v3"
    _digest_field = "reduction_digest"

    @model_validator(mode="after")
    def validate_reduction(self) -> BootstrapGraphOperationReductionV3:
        terminal = self.native_terminal
        materialization = self.effect_materialization
        if (
            self.native_compilation.transaction_group_id != self.transaction_group_id
            or self.native_compilation.operation_id != self.operation_id
            or self.native_compilation.operation_execution_id != self.operation_execution_id
            or terminal.operation_id != self.operation_id
            or terminal.operation_execution_id != self.operation_execution_id
            or terminal.proposal_digest != self.proposal_digest
            or terminal.sealed_snapshot_digest != self.sealed_snapshot_digest
            or terminal.effective_read_set_digest != self.effective_read_set_digest
            or terminal.native_compilation_digest != self.native_compilation.compilation_digest
            or terminal.status != self.native_compilation.terminal_status
            or terminal.reason_codes != self.native_compilation.reason_codes
            or materialization.operation_id != self.operation_id
            or materialization.operation_execution_id != self.operation_execution_id
            or materialization.terminal_status != terminal.status
            or materialization.observation_reason_codes != terminal.reason_codes
            or self.native_artifact_closure.terminal_digest != terminal.terminal_digest
            or self.native_artifact_closure.native_compilation_digest != self.native_compilation.compilation_digest
            or self.native_artifact_closure.accepted_effect_digest != terminal.accepted_effect_digest
            or self.native_artifact_closure.record_intent_digests != terminal.record_intent_digests
        ):
            raise ValueError("native bootstrap graph reduction is incompatible")
        return self


def validate_bootstrap_native_operation_reduction_v3(
    reduction: BootstrapGraphOperationReductionV3,
    *,
    sealed_snapshot_digest: str,
    effective_read_set_digest: str,
) -> BootstrapGraphOperationReductionV3:
    """Store-independent V3 reduction admission before group CAS."""
    validated = BootstrapGraphOperationReductionV3.model_validate(
        reduction.model_dump(mode="python")
    )
    if (
        validated.sealed_snapshot_digest != sealed_snapshot_digest
        or validated.effective_read_set_digest != effective_read_set_digest
        or validated.native_compilation.operation_input.operation_execution_id
        != validated.operation_execution_id
    ):
        raise ValueError("native bootstrap graph reduction authority is substituted")
    return validated


class BootstrapGraphOperationStoreMaterializationInputV3(_BootstrapV3Contract):
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_plan: BootstrapTransactionGroupOperationPlanV3
    reduction: BootstrapGraphOperationReductionV3
    planning_result: NonPublishingIdentityPlanningResultV3 | None
    reservation_use_authority: BootstrapReservationUseAuthorityV3
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-operation-store-materialization-input.v3"
    _digest_field = "input_digest"

    @model_validator(mode="after")
    def validate_materialization_input(self) -> BootstrapGraphOperationStoreMaterializationInputV3:
        if (
            self.operation_plan.operation_id != self.operation_id
            or self.reduction.transaction_group_id != self.transaction_group_id
            or self.reduction.operation_id != self.operation_id
            or self.reduction.operation_execution_id != self.operation_execution_id
            or self.reduction.proposal_digest != self.operation_plan.proposal_digest
            or self.planning_result != self.operation_plan.planning_result
            or self.reservation_use_authority.transaction_group_id != self.transaction_group_id
        ):
            raise ValueError("graph_group_materialization_input_incompatible")
        return self


class BootstrapGraphOperationCommitResultV3(_BootstrapV3Contract):
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_execution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reduction: BootstrapGraphOperationReductionV3
    final_status: Literal["accepted", "unresolved", "rejected", "evidence_only"]
    graph_delta_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    event_batch_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observation_delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-operation-commit-result.v3"
    _digest_field = "result_digest"

    @model_validator(mode="after")
    def validate_operation_result(self) -> BootstrapGraphOperationCommitResultV3:
        accepted = self.final_status == "accepted"
        if (
            self.reduction.transaction_group_id != self.transaction_group_id
            or self.reduction.operation_id != self.operation_id
            or self.reduction.operation_execution_id != self.operation_execution_id
            or self.reduction.native_terminal.status != self.final_status
            or accepted != (self.graph_delta_digest is not None and self.event_batch_digest is not None)
        ):
            raise ValueError("bootstrap graph operation result disposition is invalid")
        return self


class BootstrapGraphGroupCommitResultCoreV3(_BootstrapV3Contract):
    request_ctv_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: Literal["committed", "noncommitting"]
    ordered_operation_results: tuple[BootstrapGraphOperationCommitResultV3, ...]
    graph_revision_before: str = Field(min_length=1)
    graph_revision_after: str = Field(min_length=1)
    event_revision_before: str = Field(min_length=1)
    event_revision_after: str = Field(min_length=1)
    observation_revision_before: str = Field(min_length=1)
    observation_revision_after: str = Field(min_length=1)
    publication_operation_generation: int = Field(ge=1)
    publication_artifact_generation: int = Field(ge=1)
    atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-commit-result-core.v3"
    _digest_field = "core_digest"

    @model_validator(mode="after")
    def validate_core(self) -> BootstrapGraphGroupCommitResultCoreV3:
        ids = tuple(item.operation_id for item in self.ordered_operation_results)
        committed = any(item.final_status == "accepted" for item in self.ordered_operation_results)
        if not ids or ids != tuple(sorted(set(ids))) or (self.disposition == "committed") != committed:
            raise ValueError("bootstrap graph group commit result core is invalid")
        return self


class BootstrapGraphAtomicEffectReceiptV3(_BootstrapV3Contract):
    request_ctv_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_operation_result_digests: tuple[str, ...]
    graph_revision_before: str = Field(min_length=1)
    graph_revision_after: str = Field(min_length=1)
    event_revision_before: str = Field(min_length=1)
    event_revision_after: str = Field(min_length=1)
    observation_revision_before: str = Field(min_length=1)
    observation_revision_after: str = Field(min_length=1)
    atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-atomic-effect-receipt.v3"
    _digest_field = "receipt_digest"


class BootstrapGraphGroupCommitResultV3(_BootstrapV3Contract):
    core: BootstrapGraphGroupCommitResultCoreV3
    receipt: BootstrapGraphAtomicEffectReceiptV3
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-commit-result.v3"
    _digest_field = "result_digest"

    @model_validator(mode="after")
    def validate_result(self) -> BootstrapGraphGroupCommitResultV3:
        core, receipt = self.core, self.receipt
        if (
            receipt.request_ctv_digest != core.request_ctv_digest
            or receipt.result_core_digest != core.core_digest
            or receipt.atomic_write_digest != core.atomic_write_digest
            or receipt.ordered_operation_result_digests != tuple(item.result_digest for item in core.ordered_operation_results)
        ):
            raise ValueError("bootstrap graph group commit receipt is substituted")
        return self


class BootstrapGraphGroupEffectReceiptV3(_BootstrapV3Contract):
    effect_kind: Literal["observation_delta", "graph_delta", "event_batch"]
    effect_id: str = Field(min_length=1)
    effect_carrier_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    commit_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["applied", "not_applicable"]
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-effect-receipt.v3"
    _digest_field = "receipt_digest"


class BootstrapGraphObservationDeltaEffectV3(_BootstrapV3Contract):
    """The compulsory terminal observation effect for one group CAS."""

    kind: Literal["observation_delta"]
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    commit_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: IngestionObservationDelta
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    carrier_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-observation-delta-effect.v3"
    _digest_field = "carrier_digest"

    @model_validator(mode="after")
    def validate_payload(self) -> BootstrapGraphObservationDeltaEffectV3:
        if self.payload_digest != self.payload.delta_digest:
            raise ValueError("bootstrap graph observation effect payload is substituted")
        return self


class BootstrapGraphDeltaEffectV3(_BootstrapV3Contract):
    kind: Literal["graph_delta"]
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    commit_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: GraphRevisionDelta
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    carrier_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-delta-effect.v3"
    _digest_field = "carrier_digest"

    @model_validator(mode="after")
    def validate_payload(self) -> BootstrapGraphDeltaEffectV3:
        if self.payload_digest != self.payload.delta_digest:
            raise ValueError("bootstrap graph delta effect payload is substituted")
        return self


class BootstrapGraphEventBatchEffectV3(_BootstrapV3Contract):
    kind: Literal["event_batch"]
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    commit_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: SemanticMemoryEventBatch
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    carrier_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-event-batch-effect.v3"
    _digest_field = "carrier_digest"

    @model_validator(mode="after")
    def validate_payload(self) -> BootstrapGraphEventBatchEffectV3:
        if self.payload_digest != self.payload.event_batch_digest:
            raise ValueError("bootstrap graph event effect payload is substituted")
        return self


class BootstrapGraphEffectNotApplicableV3(_BootstrapV3Contract):
    kind: Literal["not_applicable"]
    effect_kind: Literal["graph_delta", "event_batch"]
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    commit_coordinate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal["noncommitting", "failed"]
    carrier_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-effect-not-applicable.v3"
    _digest_field = "carrier_digest"


BootstrapGraphGroupEffectCarrierV3: TypeAlias = Annotated[
    BootstrapGraphObservationDeltaEffectV3
    | BootstrapGraphDeltaEffectV3
    | BootstrapGraphEventBatchEffectV3
    | BootstrapGraphEffectNotApplicableV3,
    Field(discriminator="kind"),
]


class BootstrapGraphGroupCasRequestV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_plan_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    pre_execution_manifest_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_batch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    cas_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-cas-request.v3"
    _digest_field = "cas_digest"


class BootstrapGraphGroupCasOutcomeV3(_BootstrapV3Contract):
    cas_request: BootstrapGraphGroupCasRequestV3
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: Literal["committed", "noncommitting", "failed"]
    terminal_observation_status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"]
    observed_graph_revision: str = Field(min_length=1)
    observed_event_revision: str = Field(min_length=1)
    observed_observation_revision: str = Field(min_length=1)
    publication_graph_revision: str | None = None
    publication_event_revision: str | None = None
    publication_observation_revision: str = Field(min_length=1)
    effect_carriers: tuple[BootstrapGraphGroupEffectCarrierV3, ...]
    outcome_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-cas-outcome.v3"
    _digest_field = "outcome_digest"

    @model_validator(mode="after")
    def validate_effect_algebra(self) -> BootstrapGraphGroupCasOutcomeV3:
        if (
            self.transaction_group_id != self.cas_request.transaction_group_id
            or tuple(item.carrier_digest for item in self.effect_carriers)
            != tuple(sorted(item.carrier_digest for item in self.effect_carriers))
            or (self.disposition == "committed") != (
                self.terminal_observation_status == "committed"
                and self.publication_graph_revision is not None
                and self.publication_event_revision is not None
            )
            or (self.disposition != "committed") != (
                self.publication_graph_revision is None and self.publication_event_revision is None
            )
        ):
            raise ValueError("bootstrap graph CAS effect algebra is invalid")
        return self


class BootstrapGraphGroupExecutionResultV3(_BootstrapV3Contract):
    """Closed result of one graph CAS; callers cannot split its effect proof."""

    cas_request: BootstrapGraphGroupCasRequestV3
    cas_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    cas_outcome: BootstrapGraphGroupCasOutcomeV3
    effect_carriers: tuple[BootstrapGraphGroupEffectCarrierV3, ...]
    effect_receipts: tuple[BootstrapGraphGroupEffectReceiptV3, ...]
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-execution-result.v3"
    _digest_field = "result_digest"

    @model_validator(mode="after")
    def validate_execution_result(self) -> BootstrapGraphGroupExecutionResultV3:
        if (
            self.cas_request_digest != self.cas_request.cas_digest
            or self.transaction_group_id != self.cas_request.transaction_group_id
            or self.attempt_digest != self.cas_request.attempt_digest
            or self.control_epoch_digest != self.cas_request.control_epoch_digest
            or self.cas_outcome.cas_request != self.cas_request
            or self.cas_outcome.transaction_group_id != self.transaction_group_id
            or self.effect_carriers != self.cas_outcome.effect_carriers
            or tuple(item.effect_kind for item in self.effect_receipts)
            != ("observation_delta", "graph_delta", "event_batch")
        ):
            raise ValueError("bootstrap graph execution result closure is invalid")
        return self


class BootstrapGraphGroupResultConstructionV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_entry: BootstrapSourcePlanLineageEntryV3
    group_plan_member: BootstrapTransactionGroupPlanMemberV3
    planning_authorization: BootstrapGroupPlanningAuthorizationV3
    disposition: Literal["committed", "noncommitting", "failed"]
    terminal_observation_status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"]
    execution_result: BootstrapGraphGroupExecutionResultV3
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    construction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-result-construction.v3"
    _digest_field = "construction_digest"

    @model_validator(mode="after")
    def validate_result_closure(self) -> BootstrapGraphGroupResultConstructionV3:
        if (
            self.transaction_group_id != self.group_plan_member.transaction_group_id
            or self.transaction_group_id != self.source_plan_lineage_entry.transaction_group_id
            or self.transaction_group_id != self.execution_result.transaction_group_id
            or self.attempt_digest != self.execution_result.attempt_digest
            or self.control_epoch_digest != self.execution_result.control_epoch_digest
            or self.disposition != self.execution_result.cas_outcome.disposition
            or self.terminal_observation_status != self.execution_result.cas_outcome.terminal_observation_status
        ):
            raise ValueError("bootstrap graph group result closure is invalid")
        return self


class BootstrapGraphCanonicalSourceResultV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_group_result_digests: tuple[str, ...]
    canonical_source_result: CanonicalSourceTerminalOutcomeRecord
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-canonical-source-result.v3"
    _digest_field = "result_digest"

    @model_validator(mode="after")
    def validate_source_result(self) -> BootstrapGraphCanonicalSourceResultV3:
        if self.ordered_group_result_digests != self.canonical_source_result.group_result_digests:
            raise ValueError("bootstrap graph canonical source result groups are substituted")
        return self


class BootstrapGraphTerminalHandoffCoreV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_group_result_digests: tuple[str, ...]
    final_source_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_lease_binding: OperationLeaseBinding
    operation_fence_binding: OperationFenceBinding
    writer_commit_binding: SemanticWriterCommitBinding
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-handoff-core.v3"
    _digest_field = "core_digest"


class BootstrapGraphTerminalMemberIntentV3(_BootstrapV3Contract):
    kind: Literal["bootstrap_graph_coordinator_request", "bootstrap_graph_control_epoch", "bootstrap_graph_dependent_attempt", "bootstrap_transaction_group_plan", "bootstrap_source_plan_lineage_entry", "ingestion_execution_manifest", "transaction_group_result", "bootstrap_graph_terminal_handoff", "bootstrap_graph_canonical_source_result"]
    member_id: str = Field(min_length=1)
    construction_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    intent_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-member-intent.v3"
    _digest_field = "intent_member_digest"


class BootstrapGraphTerminalPublicationIntentV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_commit_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_operation_generation: int = Field(ge=1)
    expected_artifact_generation: int = Field(ge=1)
    canonical_source_result_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_intents: tuple[BootstrapGraphTerminalMemberIntentV3, ...]
    intent_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-publication-intent.v3"
    _digest_field = "intent_digest"
    _digest_excluded_fields = frozenset({"locator_digest"})

    @classmethod
    def create(cls, **values: object):  # type: ignore[no-untyped-def]
        body = {"schema_version": 3, **values}
        intent_digest = contract_digest(cls._digest_domain, body)
        locator_digest = contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-terminal-publication-locator.v3",
            {"intent_digest": intent_digest},
        )
        return cls(
            **body,
            intent_digest=intent_digest,
            locator_digest=locator_digest,
        )

    @model_validator(mode="after")
    def validate_terminal_intent(self) -> BootstrapGraphTerminalPublicationIntentV3:
        order = {
            "bootstrap_graph_coordinator_request": 0, "bootstrap_graph_control_epoch": 1,
            "bootstrap_graph_dependent_attempt": 2, "bootstrap_transaction_group_plan": 3,
            "bootstrap_source_plan_lineage_entry": 4, "ingestion_execution_manifest": 5,
            "transaction_group_result": 6, "bootstrap_graph_terminal_handoff": 7,
            "bootstrap_graph_canonical_source_result": 8,
        }
        kinds = tuple(item.kind for item in self.member_intents)
        ids = tuple(item.member_id for item in self.member_intents)
        required = set(order)
        repeated = {"bootstrap_source_plan_lineage_entry", "transaction_group_result"}
        if (
            not kinds or tuple(sorted(kinds, key=order.__getitem__)) != kinds
            or len(ids) != len(set(ids)) or set(kinds) != required
            or any(kinds.count(kind) != 1 for kind in required - repeated)
            or self.expected_operation_generation != self.expected_artifact_generation
            or self.locator_digest != contract_digest(
                b"memorii.semantic-ingestion.bootstrap-graph-terminal-publication-locator.v3",
                {"intent_digest": self.intent_digest},
            )
        ):
            raise ValueError("bootstrap graph terminal publication intent is invalid")
        return self


class BootstrapGraphTerminalPersistenceHandoffV3(_BootstrapV3Contract):
    core: BootstrapGraphTerminalHandoffCoreV3
    publication_intent: BootstrapGraphTerminalPublicationIntentV3
    handoff_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-persistence-handoff.v3"
    _digest_field = "handoff_digest"


class BootstrapGraphPlanAtomicWriteIdentityV3(_BootstrapV3Contract):
    checkpoint_kind: Literal["bootstrap_graph_terminal_checkpoint"]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    publication_intent_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_operation_generation: int = Field(ge=1)
    expected_artifact_generation: int = Field(ge=1)
    publication_operation_generation: int = Field(ge=1)
    publication_artifact_generation: int = Field(ge=1)
    member_manifest_id: str = Field(min_length=1)
    member_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_member_digests: tuple[str, ...]
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_control_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-plan-atomic-write-identity.v3"
    _digest_field = "identity_digest"


class BootstrapGraphTerminalControlV3(_BootstrapV3Contract):
    state: Literal["terminal_published"]
    operation_id: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_operation_generation: int = Field(ge=1)
    publication_artifact_generation: int = Field(ge=1)
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_commit_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_control_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-control.v3"
    _digest_field = "terminal_control_digest"


class BootstrapGraphTerminalReloadV3(_BootstrapV3Contract):
    handoff_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    atomic_write_locator_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_write_identity: BootstrapGraphPlanAtomicWriteIdentityV3
    terminal_control: BootstrapGraphTerminalControlV3
    canonical_source_result: BootstrapGraphCanonicalSourceResultV3
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_receipt: BootstrapGraphCheckpointReceiptV3
    reload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-reload.v3"
    _digest_field = "reload_digest"

    @model_validator(mode="after")
    def validate_terminal_receipt(self) -> BootstrapGraphTerminalReloadV3:
        receipt = self.checkpoint_receipt
        if (
            receipt.checkpoint_kind != "bootstrap_graph_terminal_checkpoint"
            or receipt.atomic_write_digest != self.final_write_identity.atomic_write_digest
            or receipt.publication_operation_generation
            != self.final_write_identity.publication_operation_generation
            or receipt.publication_artifact_generation
            != self.final_write_identity.publication_artifact_generation
            or receipt.reload_core_digest != self.terminal_control.terminal_control_digest
        ):
            raise ValueError("bootstrap graph terminal reload receipt is substituted")
        return self


class BootstrapGraphCanonicalSourceResultInputV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_group_result_constructions: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...]
    ordered_group_commit_reload_digests: tuple[str, ...]
    source_status: Literal["fully_committed", "partially_committed", "evidence_only", "rejected", "unresolved", "failed"]
    canonical_outcome_core: CanonicalSourceTerminalOutcomeCore
    completed_canonical_source_result: CanonicalSourceTerminalOutcomeRecord
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-canonical-source-result-input.v3"
    _digest_field = "input_digest"

    @model_validator(mode="after")
    def validate_canonical_outcome(self) -> BootstrapGraphCanonicalSourceResultInputV3:
        record = self.completed_canonical_source_result
        if (
            record.core != self.canonical_outcome_core
            or record.final_status != self.source_status
            or record.group_result_digests
            != tuple(item.result_digest for item in self.ordered_group_result_constructions)
            or self.ordered_group_commit_reload_digests
            != tuple(
                item.group_commit_reload.reload_digest
                for item in self.ordered_group_result_constructions
            )
        ):
            raise ValueError("bootstrap graph canonical source outcome is substituted")
        return self


class BootstrapGraphTerminalPublicationRequestV3(_BootstrapV3Contract):
    coordinator_request: BootstrapGraphDependentCoordinatorRequestV3
    control_epoch: BootstrapGraphControlEpochV3
    final_attempt: BootstrapGraphDependentAttemptV3
    final_plan: BootstrapTransactionGroupPlanV3
    complete_lineage: BootstrapSourcePlanLineageV3
    execution_manifest: IngestionExecutionManifest
    ordered_group_result_constructions: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...]
    ordered_group_commit_reload_digests: tuple[str, ...]
    canonical_source_result_input: BootstrapGraphCanonicalSourceResultInputV3
    handoff_core: BootstrapGraphTerminalHandoffCoreV3
    publication_intent: BootstrapGraphTerminalPublicationIntentV3
    handoff: BootstrapGraphTerminalPersistenceHandoffV3
    predecessor_generation: BootstrapGraphCurrentGenerationV3
    delivery_principal_binding_digest: str
    required_outcome_scopes: RequiredOutcomeScopeSet
    operation_lease_binding: OperationLeaseBinding
    operation_fence_binding: OperationFenceBinding
    writer_commit_binding: SemanticWriterCommitBinding
    publication_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-publication-request.v3"
    _digest_field = "publication_request_digest"

    @model_validator(mode="after")
    def validate_terminal_request(self) -> BootstrapGraphTerminalPublicationRequestV3:
        if (
            self.control_epoch.epoch_digest != self.publication_intent.control_epoch_digest
            or self.operation_fence_binding != self.handoff_core.operation_fence_binding
            or self.operation_lease_binding != self.handoff_core.operation_lease_binding
            or self.writer_commit_binding != self.handoff_core.writer_commit_binding
            or self.handoff.core != self.handoff_core
            or self.handoff.publication_intent != self.publication_intent
            or self.complete_lineage.lineage_digest != self.handoff_core.source_plan_lineage_digest
            or self.final_plan.plan_digest != self.handoff_core.transaction_group_plan_digest
            or self.canonical_source_result_input.control_epoch_digest != self.control_epoch.epoch_digest
            or self.canonical_source_result_input.request_digest != self.coordinator_request.request_digest
            or self.canonical_source_result_input.normalization_replay_digest
            != self.coordinator_request.normalization_replay.replay_digest
            or self.ordered_group_commit_reload_digests
            != tuple(
                item.group_commit_reload.reload_digest
                for item in self.ordered_group_result_constructions
            )
            or self.predecessor_generation.operation_id != self.operation_fence_binding.operation_id
            or self.predecessor_generation.request_digest != self.coordinator_request.request_digest
            or self.predecessor_generation.control_epoch_digest != self.control_epoch.epoch_digest
        ):
            raise ValueError("bootstrap graph terminal publication request is invalid")
        return self


class BootstrapGraphTerminalHostAuthorityV3(_BootstrapV3Contract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_graph_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_routes: SegmentLanguageRouteSet
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    capability_bindings: tuple[OperationCapabilityExecutionBinding, ...]
    required_outcome_scopes: RequiredOutcomeScopeSet
    operation_fence_binding: OperationFenceBinding
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-host-authority.v3"
    _digest_field = "authority_digest"


class BootstrapGraphFinalStageEvidenceV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_transaction_group_ids: tuple[str, ...]
    ordered_group_commit_reload_digests: tuple[str, ...]
    source_outcomes: tuple[IngestionStageOutcome, ...]
    graph_validation_attempts: tuple[GraphDependentValidationAttempt, ...]
    causal_blockers: tuple[IngestionStageInstanceRef, ...]
    terminal_before_planning_proof_digests: tuple[str, ...]
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-final-stage-evidence.v3"
    _digest_field = "evidence_digest"

    @model_validator(mode="after")
    def validate_order(self) -> BootstrapGraphFinalStageEvidenceV3:
        if self.ordered_transaction_group_ids != tuple(sorted(set(self.ordered_transaction_group_ids))):
            raise ValueError("bootstrap graph final stage evidence group order is invalid")
        return self


class BootstrapGraphTerminalPreparationV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    host_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_generation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_request: BootstrapGraphTerminalPublicationRequestV3
    preparation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-terminal-preparation.v3"
    _digest_field = "preparation_digest"


BootstrapGraphPlanAtomicMemberKindV3: TypeAlias = Literal[
    "bootstrap_graph_coordinator_request", "bootstrap_graph_snapshot_authority",
    "bootstrap_graph_control_epoch", "graph_base_read_set",
    "graph_read_set_extension", "graph_reconciliation", "reference_closure",
    "group_compilation_request", "group_compilation_artifact",
    "group_independence_certificate", "bootstrap_graph_pre_execution_group_evidence",
    "bootstrap_transaction_group_plan", "bootstrap_group_planning_authorization",
    "bootstrap_graph_dependent_attempt", "bootstrap_source_plan_lineage_entry",
    "bootstrap_graph_retry_progress", "bootstrap_graph_final_stage_evidence",
    "ingestion_execution_manifest", "transaction_group_result",
    "bootstrap_graph_terminal_handoff", "bootstrap_graph_canonical_source_result",
]


# This is intentionally the sole V3 atomic-member vocabulary.  Checkpoint
# classes describe publication lifecycle, not additional persisted member kinds.
BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS: dict[str, str] = {
    "bootstrap_graph_coordinator_request": "bootstrap_graph_v3/bootstrap_graph_coordinator_request/native",
    "bootstrap_graph_snapshot_authority": "bootstrap_graph_v3/bootstrap_graph_snapshot_authority/native",
    "bootstrap_graph_control_epoch": "bootstrap_graph_v3/bootstrap_graph_control_epoch/native",
    "graph_base_read_set": "bootstrap_graph_v3/graph_base_read_set/native",
    "graph_read_set_extension": "bootstrap_graph_v3/graph_read_set_extension/native",
    "graph_reconciliation": "bootstrap_graph_v3/graph_reconciliation/native",
    "reference_closure": "bootstrap_graph_v3/reference_closure/native",
    "group_compilation_request": "bootstrap_graph_v3/group_compilation_request/native",
    "group_compilation_artifact": "bootstrap_graph_v3/group_compilation_artifact/native",
    "group_independence_certificate": "bootstrap_graph_v3/group_independence_certificate/native",
    "bootstrap_graph_pre_execution_group_evidence": "bootstrap_graph_v3/bootstrap_graph_pre_execution_group_evidence/native",
    "bootstrap_transaction_group_plan": "bootstrap_graph_v3/bootstrap_transaction_group_plan/native",
    "bootstrap_group_planning_authorization": "bootstrap_graph_v3/bootstrap_group_planning_authorization/native",
    "bootstrap_graph_dependent_attempt": "bootstrap_graph_v3/bootstrap_graph_dependent_attempt/native",
    "bootstrap_source_plan_lineage_entry": "bootstrap_graph_v3/bootstrap_source_plan_lineage_entry/native",
    "bootstrap_graph_retry_progress": "bootstrap_graph_v3/bootstrap_graph_retry_progress/native",
    "bootstrap_graph_final_stage_evidence": "bootstrap_graph_v3/bootstrap_graph_final_stage_evidence/native",
    "ingestion_execution_manifest": "bootstrap_graph_v3/ingestion_execution_manifest/native",
    "transaction_group_result": "bootstrap_graph_v3/transaction_group_result/native",
    "bootstrap_graph_terminal_handoff": "bootstrap_graph_v3/bootstrap_graph_terminal_handoff/native",
    "bootstrap_graph_canonical_source_result": "bootstrap_graph_v3/bootstrap_graph_canonical_source_result/native",
}

_BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_ENVELOPE = (
    "memorii.bootstrap-graph.atomic-member-envelope.v3"
)
_BOOTSTRAP_GRAPH_V3_RETIRED_GENERIC_REDUCTION_FIELDS = frozenset({
    "semantic_compilation", "terminal_outcome", "artifact_closure",
})


def _contains_retired_bootstrap_graph_v3_reduction(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            key in _BOOTSTRAP_GRAPH_V3_RETIRED_GENERIC_REDUCTION_FIELDS
            or _contains_retired_bootstrap_graph_v3_reduction(item)
            for key, item in value.items()
        )
    if isinstance(value, (tuple, list)):
        return any(_contains_retired_bootstrap_graph_v3_reduction(item) for item in value)
    return False


def encode_bootstrap_graph_atomic_member_payload_v3(
    *, kind: BootstrapGraphPlanAtomicMemberKindV3, artifact: BaseModel,
) -> bytes:
    """Encode one qualified native V3 atomic-member payload.

    The member kind selects the codec before the payload is serialized.  The
    retired generic-reduction grammar is prohibited at this boundary, so an old
    graph payload cannot be relabelled as a native checkpoint member.
    """
    codec_key = BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS.get(kind)
    if codec_key is None:
        raise SemanticContractCodecError("unknown bootstrap graph V3 atomic member kind")
    if (
        kind == "transaction_group_result"
        and not isinstance(artifact, BootstrapNativeGroupCommitTerminalConstructionV3)
    ):
        raise SemanticContractCodecError("native transaction group result has an incompatible type")
    payload = canonical_contract_value(artifact)
    if _contains_retired_bootstrap_graph_v3_reduction(payload):
        raise SemanticContractCodecError("retired generic bootstrap graph reduction")
    return encode_typed_value({
        "schema": _BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_ENVELOPE,
        "codec_key": codec_key,
        "payload": payload,
    })


def decode_bootstrap_graph_atomic_member_payload_v3(
    *, kind: BootstrapGraphPlanAtomicMemberKindV3, raw: bytes,
) -> object:
    """Fail closed before a V3 member payload can be interpreted or referenced."""
    codec_key = BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS.get(kind)
    if codec_key is None:
        raise SemanticContractCodecError("unknown bootstrap graph V3 atomic member kind")
    try:
        decoded = decode_typed_value(raw)
    except (TypeError, ValueError) as exc:
        raise SemanticContractCodecError("invalid bootstrap graph V3 member bytes") from exc
    if (
        not isinstance(decoded, dict)
        or set(decoded) != {"schema", "codec_key", "payload"}
        or decoded["schema"] != _BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_ENVELOPE
        or decoded["codec_key"] != codec_key
        or _contains_retired_bootstrap_graph_v3_reduction(decoded["payload"])
    ):
        raise SemanticContractCodecError("bootstrap graph V3 member payload is not native")
    payload = decoded["payload"]
    if kind == "transaction_group_result":
        try:
            return canonical_contract_value(
                BootstrapNativeGroupCommitTerminalConstructionV3.model_validate(payload)
            )
        except (TypeError, ValueError) as exc:
            raise SemanticContractCodecError(
                "native transaction group result is incompatible"
            ) from exc
    return payload


def validate_bootstrap_graph_plan_atomic_members_v3(
    members: tuple[BootstrapGraphPlanAtomicMemberV3, ...],
) -> None:
    """Validate every member by its literal codec before persistence or reload."""
    for member in members:
        decode_bootstrap_graph_atomic_member_payload_v3(
            kind=member.kind, raw=member.canonical_payload,
        )


class BootstrapGraphPlanAtomicMemberV3(_BootstrapV3Contract):
    member_id: str = Field(min_length=1)
    kind: BootstrapGraphPlanAtomicMemberKindV3
    canonical_payload: bytes
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-plan-atomic-member.v3"
    _digest_field = "member_digest"

    @model_validator(mode="after")
    def validate_payload_digest(self) -> BootstrapGraphPlanAtomicMemberV3:
        if self.payload_digest != sha256(self.canonical_payload).hexdigest():
            raise ValueError("bootstrap graph atomic member payload digest is invalid")
        return self


class BootstrapGraphCurrentGenerationV3(_BootstrapV3Contract):
    store_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_generation: int = Field(ge=1)
    artifact_generation: int = Field(ge=1)
    latest_atomic_write_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-current-generation.v3"
    _digest_field = "snapshot_digest"

    @model_validator(mode="after")
    def validate_generations(self) -> BootstrapGraphCurrentGenerationV3:
        if self.operation_generation != self.artifact_generation:
            raise ValueError("bootstrap graph generation snapshot is invalid")
        return self


class BootstrapGraphGroupCommitRequestV3(_BootstrapV3Contract):
    source_operation_id: str = Field(min_length=1)
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_ids: tuple[str, ...]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: BootstrapGraphDependentAttemptV3
    group_plan_member: BootstrapTransactionGroupPlanMemberV3
    planning_authorization: BootstrapGroupPlanningAuthorizationV3
    source_plan_lineage_entry: BootstrapSourcePlanLineageEntryV3
    pre_execution_manifest_identity: BootstrapGraphPreExecutionManifestIdentityV3
    control_epoch: BootstrapGraphControlEpochV3
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    delivery_principal_binding_digest: str
    required_outcome_scopes: RequiredOutcomeScopeSet
    expected_generation: BootstrapGraphCurrentGenerationV3
    ordered_operation_inputs: tuple[BootstrapGraphOperationStoreMaterializationInputV3, ...]
    request_ctv_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.group-commit-request.v3"
    _digest_field = "request_ctv_digest"

    @property
    def control_epoch_digest(self) -> str:
        return self.control_epoch.epoch_digest

    @property
    def write_digest(self) -> str:
        """Compatibility view for the store's current-authority verifier."""
        return self.request_ctv_digest

    @model_validator(mode="after")
    def validate_group_commit_request(self) -> BootstrapGraphGroupCommitRequestV3:
        inputs = self.ordered_operation_inputs
        if (
            not self.operation_ids
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            or self.group_plan_member.transaction_group_id != self.transaction_group_id
            or self.group_plan_member.operation_ids != self.operation_ids
            or tuple(item.operation_id for item in inputs) != self.operation_ids
            or any(item.transaction_group_id != self.transaction_group_id for item in inputs)
            or self.planning_authorization.transaction_group_id != self.transaction_group_id
            or self.planning_authorization.operation_ids != self.operation_ids
            or self.source_plan_lineage_entry.transaction_group_id != self.transaction_group_id
            or self.source_plan_lineage_entry.attempt_digest != self.attempt.attempt_digest
            or self.planning_authorization.group_plan_member_digest != self.group_plan_member.member_digest
            or self.operation_fence_binding != self.control_epoch.operation_fence_binding
            or self.operation_lease_binding != self.control_epoch.operation_lease_binding
            or self.writer_commit_binding != self.control_epoch.writer_commit_binding
            or self.expected_generation.operation_id != self.source_operation_id
        ):
            raise ValueError("graph_group_materialization_input_incompatible")
        return self


class BootstrapGraphGroupCommitReloadV3(_BootstrapV3Contract):
    source_operation_id: str = Field(min_length=1)
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_ids: tuple[str, ...]
    request_ctv_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    persisted_result: BootstrapGraphGroupCommitResultV3
    successor_generation: BootstrapGraphCurrentGenerationV3
    reload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-group-commit-reload.v3"
    _digest_field = "reload_digest"

    @model_validator(mode="after")
    def validate_reload(self) -> BootstrapGraphGroupCommitReloadV3:
        if (
            not self.operation_ids
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            or self.persisted_result.core.request_ctv_digest != self.request_ctv_digest
            or tuple(item.operation_id for item in self.persisted_result.core.ordered_operation_results) != self.operation_ids
            or self.successor_generation.operation_id != self.source_operation_id
        ):
            raise ValueError("bootstrap graph group commit reload is invalid")
        return self


class BootstrapNativeGroupCommitTerminalConstructionV3(_BootstrapV3Contract):
    """The one persisted native terminal projection of a group-commit reload.

    Store-owned reload bytes are the sole authority for the group effect.  The
    surrounding fields only prove the exact request/attempt/lineage tuple that
    caused that reload; they never reconstruct an effect or outcome.
    """

    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: BootstrapGraphDependentAttemptV3
    source_plan_lineage_entry: BootstrapSourcePlanLineageEntryV3
    group_plan_member: BootstrapTransactionGroupPlanMemberV3
    planning_authorization: BootstrapGroupPlanningAuthorizationV3
    group_commit_reload: BootstrapGraphGroupCommitReloadV3
    operation_fence_binding: OperationFenceBinding
    control_epoch: BootstrapGraphControlEpochV3
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.bootstrap-graph.native-group-commit-terminal-construction.v3"
    _digest_field = "result_digest"

    @property
    def transaction_group_id(self) -> str:
        return self.group_plan_member.transaction_group_id

    @property
    def disposition(self) -> Literal["committed", "noncommitting"]:
        return self.group_commit_reload.persisted_result.core.disposition

    @property
    def terminal_observation_status(self) -> Literal["committed", "rejected", "unresolved", "evidence_only"]:
        if self.disposition == "committed":
            return "committed"
        statuses = tuple(
            item.final_status
            for item in self.group_commit_reload.persisted_result.core.ordered_operation_results
        )
        if statuses and all(status == "rejected" for status in statuses):
            return "rejected"
        if "unresolved" in statuses:
            return "unresolved"
        return "evidence_only"

    @model_validator(mode="after")
    def validate_terminal_construction(self) -> BootstrapNativeGroupCommitTerminalConstructionV3:
        reload = self.group_commit_reload
        if (
            self.request_digest != self.attempt.request_digest
            or self.normalization_replay_digest != self.attempt.normalization_replay_digest
            or self.source_plan_lineage_entry.attempt_digest != self.attempt.attempt_digest
            or self.source_plan_lineage_entry.transaction_group_id != self.transaction_group_id
            or self.group_plan_member.operation_ids != reload.operation_ids
            or self.planning_authorization.transaction_group_id != self.transaction_group_id
            or self.planning_authorization.operation_ids != reload.operation_ids
            or reload.transaction_group_id != self.transaction_group_id
            or self.operation_fence_binding.binding_digest
            != self.attempt.operation_fence_binding_digest
            or self.operation_fence_binding != self.control_epoch.operation_fence_binding
            or self.control_epoch.epoch_digest != self.attempt.control_epoch_digest
            or reload.successor_generation.control_epoch_digest != self.control_epoch.epoch_digest
            or reload.successor_generation.request_digest != self.request_digest
        ):
            raise ValueError("bootstrap native group commit terminal construction is substituted")
        return self


class BootstrapGraphPlanAtomicWriteRequestV3(_BootstrapV3Contract):
    kind: Literal["bootstrap_graph_plan_checkpoint", "bootstrap_graph_attempt_checkpoint", "bootstrap_graph_lineage_checkpoint", "bootstrap_graph_group_result_checkpoint", "bootstrap_graph_retry_checkpoint", "bootstrap_graph_final_stage_evidence_checkpoint", "bootstrap_graph_terminal_checkpoint"]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_generation: BootstrapGraphCurrentGenerationV3
    operation_lease_binding: OperationLeaseBinding
    operation_fence_binding: OperationFenceBinding
    writer_commit_binding: SemanticWriterCommitBinding
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    members: tuple[BootstrapGraphPlanAtomicMemberV3, ...]
    required_member_digests: tuple[str, ...]
    write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-plan-atomic-write-request.v3"
    _digest_field = "write_digest"

    @property
    def predecessor_operation_generation(self) -> int:
        return self.predecessor_generation.operation_generation

    @property
    def predecessor_artifact_generation(self) -> int:
        return self.predecessor_generation.artifact_generation

    @property
    def publication_operation_generation(self) -> int:
        return self.predecessor_generation.operation_generation + 1

    @property
    def publication_artifact_generation(self) -> int:
        return self.predecessor_generation.artifact_generation + 1

    @model_validator(mode="after")
    def validate_atomic_order(self) -> BootstrapGraphPlanAtomicWriteRequestV3:
        ids = tuple(item.member_id for item in self.members)
        digests = tuple(item.member_digest for item in self.members)
        if not ids or ids != tuple(sorted(set(ids))) or self.required_member_digests != tuple(sorted(digests)):
            raise ValueError("bootstrap graph atomic write closure is invalid")
        return self


class BootstrapGraphPlanAtomicReloadV3(_BootstrapV3Contract):
    """Store-reloaded, authority-bound receipt for one V3 graph checkpoint."""

    core: BootstrapGraphPlanAtomicReloadCoreV3
    checkpoint_receipt: BootstrapGraphCheckpointReceiptV3
    reload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-plan-atomic-reload.v3"
    _digest_field = "reload_digest"

    @model_validator(mode="after")
    def validate_reload(self) -> BootstrapGraphPlanAtomicReloadV3:
        if self.checkpoint_receipt.reload_core_digest != self.core.core_digest:
            raise ValueError("bootstrap graph checkpoint reload is substituted")
        return self


class BootstrapGraphPlanAtomicReloadCoreV3(_BootstrapV3Contract):
    write_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_operation_generation: int = Field(ge=1)
    publication_artifact_generation: int = Field(ge=1)
    members: tuple[BootstrapGraphPlanAtomicMemberV3, ...]
    required_member_digests: tuple[str, ...]
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_lease_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-plan-atomic-reload-core.v3"
    _digest_field = "core_digest"

    @model_validator(mode="after")
    def validate_atomic_reload(self) -> BootstrapGraphPlanAtomicReloadCoreV3:
        ids = tuple(item.member_id for item in self.members)
        digests = tuple(item.member_digest for item in self.members)
        if (
            not ids
            or ids != tuple(sorted(set(ids)))
            or self.required_member_digests != tuple(sorted(digests))
            or self.publication_operation_generation
            != self.publication_artifact_generation
        ):
            raise ValueError("bootstrap graph atomic reload closure is invalid")
        return self


class BootstrapGraphCheckpointReceiptV3(_BootstrapV3Contract):
    checkpoint_kind: Literal["bootstrap_graph_plan_checkpoint", "bootstrap_graph_attempt_checkpoint", "bootstrap_graph_lineage_checkpoint", "bootstrap_graph_group_result_checkpoint", "bootstrap_graph_retry_checkpoint", "bootstrap_graph_final_stage_evidence_checkpoint", "bootstrap_graph_terminal_checkpoint"]
    predecessor_generation: BootstrapGraphCurrentGenerationV3
    write_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    atomic_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reload_core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_operation_generation: int = Field(ge=1)
    publication_artifact_generation: int = Field(ge=1)
    successor_generation: BootstrapGraphCurrentGenerationV3
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-checkpoint-receipt.v3"
    _digest_field = "receipt_digest"

    @model_validator(mode="after")
    def validate_receipt(self) -> BootstrapGraphCheckpointReceiptV3:
        if (
            self.publication_operation_generation != self.predecessor_generation.operation_generation + 1
            or self.publication_artifact_generation != self.predecessor_generation.artifact_generation + 1
            or self.successor_generation.operation_generation != self.publication_operation_generation
            or self.successor_generation.artifact_generation != self.publication_artifact_generation
            or self.successor_generation.latest_atomic_write_digest != self.atomic_write_digest
        ):
            raise ValueError("bootstrap graph checkpoint receipt is invalid")
        return self


class BootstrapGraphExecutionManifestGroupInputV3(_BootstrapV3Contract):
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_plan_member: BootstrapTransactionGroupPlanMemberV3
    compilation_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    compilation_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    independence_certificate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_operation_ids: tuple[str, ...]
    proposed_delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_batch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-execution-manifest-group-input.v3"
    _digest_field = "input_digest"


class BootstrapGraphPreExecutionGroupEvidenceV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    group_plan_member_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconciliation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_validation_attempts: tuple[GraphDependentValidationAttempt, ...]
    causal_blockers: tuple[IngestionStageInstanceRef, ...]
    terminal_before_planning_proof_digests: tuple[str, ...]
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-pre-execution-group-evidence.v3"
    _digest_field = "evidence_digest"


class BootstrapGraphPreExecutionManifestCoreV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    producing_attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    producing_transaction_group_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    producing_lineage_entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_graph_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_routes: SegmentLanguageRouteSet
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    capability_bindings: tuple[OperationCapabilityExecutionBinding, ...]
    graph_validation_attempts: tuple[GraphDependentValidationAttempt, ...]
    causal_blockers: tuple[IngestionStageInstanceRef, ...]
    terminal_before_planning_proof_digests: tuple[str, ...]
    manifest_group_inputs: tuple[BootstrapGraphExecutionManifestGroupInputV3, ...]
    core_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-pre-execution-manifest-core.v3"
    _digest_field = "core_digest"


class BootstrapGraphPreExecutionManifestIdentityV3(_BootstrapV3Contract):
    core: BootstrapGraphPreExecutionManifestCoreV3
    manifest_identity_id: str = Field(min_length=1)
    identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-pre-execution-manifest-identity.v3"
    _digest_field = "identity_digest"


class BootstrapGraphPreExecutionManifestIdentityClosureV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    identities: tuple[BootstrapGraphPreExecutionManifestIdentityV3, ...]
    identity_by_group: tuple[tuple[str, str], ...]
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_commit_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-pre-execution-manifest-identity-closure.v3"
    _digest_field = "closure_digest"


class BootstrapGraphExecutionManifestConstructionV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    pre_execution_manifests: BootstrapGraphPreExecutionManifestIdentityClosureV3
    pre_execution_manifest_identity_closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_graph_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_routes: SegmentLanguageRouteSet
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    capability_bindings: tuple[OperationCapabilityExecutionBinding, ...]
    source_outcomes: tuple[IngestionStageOutcome, ...]
    graph_validation_attempts: tuple[GraphDependentValidationAttempt, ...]
    transaction_group_outcomes: tuple[tuple[str, tuple[IngestionStageOutcome, ...]], ...]
    causal_blockers: tuple[IngestionStageInstanceRef, ...]
    terminal_before_planning_proof_digests: tuple[str, ...]
    manifest_group_inputs: tuple[BootstrapGraphExecutionManifestGroupInputV3, ...]
    ordered_group_commit_reload_digests: tuple[str, ...]
    construction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-execution-manifest-construction.v3"
    _digest_field = "construction_digest"


class BootstrapGraphPlanCompilationV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_group_plan: BootstrapTransactionGroupPlanV3
    operation_reductions: tuple[BootstrapGraphOperationReductionV3, ...]
    pre_execution_evidence: tuple[BootstrapGraphPreExecutionGroupEvidenceV3, ...]
    attempt_construction_inputs: BootstrapGraphAttemptConstructionInputsV3
    compilation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-plan-compilation.v3"
    _digest_field = "compilation_digest"

    @model_validator(mode="after")
    def validate_compilation(self) -> BootstrapGraphPlanCompilationV3:
        groups = self.transaction_group_plan.group_members
        operations = tuple(
            (operation.operation_id, operation.operation_execution_id)
            for group in groups
            for operation in group.operation_plans
        )
        reductions = tuple(
            (item.operation_id, item.operation_execution_id)
            for item in self.operation_reductions
        )
        evidence_groups = tuple(item.transaction_group_id for item in self.pre_execution_evidence)
        if operations != reductions or evidence_groups != tuple(item.transaction_group_id for item in groups):
            raise ValueError("bootstrap graph plan compilation closure is invalid")
        return self


class BootstrapGraphAttemptConstructionInputsV3(_BootstrapV3Contract):
    """Pre-attempt immutable inputs retained with a graph plan checkpoint."""

    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconciliation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_policy_reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_pre_execution_evidence_digests: tuple[str, ...]
    inputs_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-attempt-construction-inputs.v3"
    _digest_field = "inputs_digest"

    @model_validator(mode="after")
    def validate_evidence_projection(self) -> BootstrapGraphAttemptConstructionInputsV3:
        if len(set(self.ordered_pre_execution_evidence_digests)) != len(
            self.ordered_pre_execution_evidence_digests
        ):
            raise ValueError("bootstrap graph pre-execution evidence projection is invalid")
        return self


class BootstrapGraphPlanAuthorizationSetV3(_BootstrapV3Contract):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorizations: tuple[BootstrapGroupPlanningAuthorizationV3, ...]
    authorization_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-plan-authorization-set.v3"
    _digest_field = "authorization_set_digest"


class BootstrapGraphV3ProducerUnavailable(_BootstrapV3Contract):
    phase: Literal["compile", "authorize", "group_execute"]
    reason: Literal["authority_unavailable", "scope_revoked", "lease_unavailable", "writer_unavailable", "stale_epoch", "invalid_input", "read_conflict", "storage_unavailable"]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    unavailable_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-producer-unavailable.v3"
    _digest_field = "unavailable_digest"


class BootstrapGraphDependentCoordinatorSucceededV3(_BootstrapV3Contract):
    kind: Literal["succeeded"]
    terminal_reload: BootstrapGraphTerminalReloadV3
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-dependent-coordinator-succeeded.v3"
    _digest_field = "response_digest"

    @model_validator(mode="after")
    def validate_epoch(self) -> BootstrapGraphDependentCoordinatorSucceededV3:
        if self.control_epoch_digest != self.terminal_reload.control_epoch_digest:
            raise ValueError("bootstrap graph succeeded epoch is substituted")
        return self


class BootstrapGraphDependentPreGraphNonCommitV3(_BootstrapV3Contract):
    kind: Literal["pre_graph_noncommit"]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal["authority_unavailable", "normalization_incompatible", "snapshot_unavailable", "planning_unavailable", "authorization_unavailable"]
    reason_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-dependent-coordinator-pre-graph-noncommit.v3"
    _digest_field = "response_digest"


class BootstrapGraphDurableRetryProgressV3(_BootstrapV3Contract):
    kind: Literal["durable_retry"]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_group_result_digests: tuple[str, ...]
    retry_group_ids: tuple[str, ...]
    reason: Literal["related_conflict", "lease_renewal_required", "lease_reclaim_required", "publication_retry", "storage_retry"]
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_commit_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    progress_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-durable-retry-progress.v3"
    _digest_field = "response_digest"


class BootstrapGraphRetryRecoveryLocatorV3(_BootstrapV3Contract):
    kind: Literal["bootstrap_graph_retry_recovery_locator"]
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_replay_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_write_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_manifest_id: str = Field(min_length=1)
    checkpoint_request: BootstrapGraphPlanAtomicWriteRequestV3
    progress: BootstrapGraphDurableRetryProgressV3
    locator_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-retry-recovery-locator.v3"
    _digest_field = "locator_digest"

    @model_validator(mode="after")
    def validate_retry_recovery_locator(self) -> BootstrapGraphRetryRecoveryLocatorV3:
        request = self.checkpoint_request
        if (
            request.kind != "bootstrap_graph_retry_checkpoint"
            or request.request_digest != self.request_digest
            or request.write_digest != self.checkpoint_write_digest
            or request.normalization_replay_digest != self.normalization_replay_digest
            or request.normalization_result_digest != self.normalization_result_digest
            or request.operation_fence_binding.binding_digest
            != self.operation_fence_binding_digest
            or self.progress.request_digest != self.request_digest
            or self.progress.normalization_replay_digest
            != self.normalization_replay_digest
            or self.progress.operation_fence_binding_digest
            != self.operation_fence_binding_digest
            or self.progress.writer_commit_binding_digest
            != request.writer_commit_binding.binding_digest
            or self.progress.control_epoch_digest != request.control_epoch_digest
        ):
            raise ValueError("bootstrap graph retry recovery locator is substituted")
        progress_members = tuple(
            member
            for member in request.members
            if member.kind == "bootstrap_graph_retry_progress"
        )
        if len(progress_members) != 1:
            raise ValueError("bootstrap graph retry recovery progress is ambiguous")
        decoded = decode_bootstrap_graph_atomic_member_payload_v3(
            kind=progress_members[0].kind,
            raw=progress_members[0].canonical_payload,
        )
        if BootstrapGraphDurableRetryProgressV3.model_validate(decoded) != self.progress:
            raise ValueError("bootstrap graph retry recovery progress is substituted")
        return self


class BootstrapGraphFinalizedFailureV3(_BootstrapV3Contract):
    kind: Literal["finalized_failure"]
    terminal_reload: BootstrapGraphTerminalReloadV3
    control_epoch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal["related_conflict_exhausted", "lease_expired", "fence_superseded", "writer_superseded", "publication_conflict", "storage_unavailable"]
    response_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.bootstrap-graph-finalized-failure.v3"
    _digest_field = "response_digest"


BootstrapGraphDependentCoordinatorResultV3: TypeAlias = Annotated[
    BootstrapGraphDependentCoordinatorSucceededV3 | BootstrapGraphDependentPreGraphNonCommitV3 |
    BootstrapGraphDurableRetryProgressV3 | BootstrapGraphFinalizedFailureV3,
    Field(discriminator="kind"),
]


class BootstrapSourceNormalizationAtomicWriteRequestV3(AtomicGenerationRequest):
    """Closed bootstrap publication wire; deliberately not a V2 checkpoint.

    Bootstrap analysis has a different persisted algebra from generic source
    normalization.  Inheriting the V2 request made its graph-route and V2
    result fields silently part of the V3 wire.  This standalone discriminator
    is the only accepted bootstrap atomic request.
    """

    schema_version: Literal[3]
    kind: Literal["bootstrap_source_normalization_checkpoint"]
    progress_state: Literal["preplanning"]
    publication_generation: int = Field(ge=1)
    source_normalization_request: BootstrapSourceNormalizationRequestV3
    source_normalization_result: BootstrapSourceNormalizationResultV3
    evidence_manifest: BootstrapSourceNormalizationEvidenceManifestV3
    bootstrap_v3_payload_limit_authority: BootstrapV3PayloadLimitAuthority
    normalization_request_core: BootstrapNormalizationRequestCoreV3
    semantic_reduction_authority: BootstrapSemanticReductionAuthorityMemberV3
    bootstrap_graph_normalization_authority: BootstrapGraphNormalizationAuthorityMemberV3
    bootstrap_proposal_run_payload: BootstrapProposalRunPayloadV3
    bootstrap_analysis_lane_results: tuple[BootstrapAnalysisLaneResultV3, ...]
    bootstrap_recovery_key: BootstrapRecoveryKeyV3
    bootstrap_recovery_claim: BootstrapRecoveryClaimV3

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_bootstrap_v3_closure(self) -> BootstrapSourceNormalizationAtomicWriteRequestV3:
        provenance = self.source_normalization_request.bootstrap_analysis_provenance
        if not provenance:
            raise ValueError("bootstrap V3 atomic request has no provenance")
        if (
            self.bootstrap_recovery_key.operation_fence_digest != self.operation_fence_binding.binding_digest
            or self.bootstrap_recovery_claim.recovery_key_digest != self.bootstrap_recovery_key.recovery_key_digest
            or self.bootstrap_recovery_claim.operation_fence_digest != self.operation_fence_binding.binding_digest
            or self.bootstrap_recovery_claim.expected_operation_generation != self.expected_operation_generation
            or self.bootstrap_recovery_claim.expected_artifact_generation != self.expected_artifact_generation
        ):
            raise ValueError("bootstrap V3 recovery closure is substituted")
        if any(
            (item.source_id, item.source_digest, item.preparation_fingerprint)
            != (
                self.bootstrap_recovery_key.source_id,
                self.bootstrap_recovery_key.source_digest,
                self.bootstrap_recovery_key.preparation_fingerprint,
            )
            for item in provenance
        ):
            raise ValueError("bootstrap V3 provenance is foreign")
        authority = self.bootstrap_v3_payload_limit_authority
        payload = self.bootstrap_proposal_run_payload
        core = self.normalization_request_core
        reduction = self.semantic_reduction_authority
        if (
            (authority.source_id, authority.source_digest, authority.preparation_fingerprint)
            != (
                self.bootstrap_recovery_key.source_id,
                self.bootstrap_recovery_key.source_digest,
                self.bootstrap_recovery_key.preparation_fingerprint,
            )
            or payload.bootstrap_analysis_provenances != provenance
            or payload.payload_limit_authority_digest != authority.authority_digest
            or self.source_normalization_request.proposal_run.proposal_payload != payload
            or self.source_normalization_request.payload_limit_authority != authority
            or self.source_normalization_result.source_normalization_request_digest
            != self.source_normalization_request.request_digest
            or self.evidence_manifest.source_normalization_request_digest
            != self.source_normalization_request.request_digest
            or self.source_normalization_result.evidence_manifest != self.evidence_manifest
            or self.bootstrap_graph_normalization_authority.recovery_key_digest
            != self.bootstrap_recovery_key.recovery_key_digest
            or self.bootstrap_graph_normalization_authority.normalization_request_digest
            != self.source_normalization_request.request_digest
            or self.bootstrap_graph_normalization_authority.normalization_result_digest
            != self.source_normalization_result.result_digest
            or core.proposal_payload != payload
            or core.lane_results != self.bootstrap_analysis_lane_results
            or core.payload_limit_authority != authority
            or core.recovery_key != self.bootstrap_recovery_key
            or core.source_alignment != self.source_normalization_request.source_alignment
            or reduction.normalization_request_core != core
            or reduction.execution_policy != self.bootstrap_graph_normalization_authority.execution_policy
            or reduction.capability_registry != self.bootstrap_graph_normalization_authority.capability_registry
        ):
            raise ValueError("bootstrap V3 atomic payload closure is substituted")
        lane_order = ("stanza", "spacy", "predicate_event_detection", "temporal_resolution")
        if tuple((item.segment_id, item.lane) for item in self.bootstrap_analysis_lane_results) != tuple(
            (item.segment_id, lane) for item in provenance for lane in lane_order
        ):
            raise ValueError("bootstrap V3 atomic lanes are not the exact four-lane closure")
        if any(
            item.payload_limit_authority_digest != authority.authority_digest
            or item.payload_limit_policy_digest != authority.policy.policy_digest
            for item in self.bootstrap_analysis_lane_results
        ):
            raise ValueError("bootstrap V3 atomic lane limit authority is substituted")
        # The retained carriers are the recovery boundary.  The V3 registry is
        # intentionally separate from V2: no generic route, V2 result, or V2
        # checkpoint member can be smuggled into a bootstrap generation.
        expected_payloads = (
            ("bootstrap_proposal_run_payload", encode_semantic_contract(payload)),
            *(("bootstrap_analysis_lane_result", encode_semantic_contract(item))
              for item in self.bootstrap_analysis_lane_results),
        )
        actual = tuple((member.kind, member.canonical_payload) for member in self.members)
        if actual[: len(expected_payloads)] != expected_payloads:
            raise ValueError("bootstrap V3 atomic retained member bytes are incomplete or substituted")
        authority_payload = encode_semantic_contract(
            self.bootstrap_graph_normalization_authority
        )
        reduction_payload = encode_semantic_contract(reduction)
        core_payload = encode_semantic_contract(core)
        if actual[-3:] != (
            ("bootstrap_normalization_request_core", core_payload),
            ("bootstrap_semantic_reduction_authority", reduction_payload),
            ("bootstrap_graph_normalization_authority", authority_payload),
        ):
            raise ValueError("bootstrap V3 normalization authority member is absent or substituted")
        allowed = {
            "bootstrap_proposal_run_payload", "bootstrap_analysis_lane_result",
            "bootstrap_pre_alignment_operation_subject_set", "bootstrap_analyzer_scope_observation",
            "bootstrap_analyzer_temporal_attachment_observation", "bootstrap_parser_consensus_assessment",
            "bootstrap_semantic_scope_consensus", "bootstrap_temporal_attachment_consensus",
            "bootstrap_operation_temporal_attachment_consensus_set",
            "bootstrap_source_local_identity_partition_evidence",
            "bootstrap_source_local_identity_resolution", "bootstrap_proposal_coverage_audit",
            "bootstrap_operation_alignment", "bootstrap_source_dependency_group",
            "bootstrap_graph_free_interpretation_bundle", "bootstrap_source_proposal_alignment",
            "bootstrap_source_normalization_request",
            "bootstrap_source_normalization_evidence_manifest",
            "bootstrap_source_normalization_result",
            "bootstrap_normalization_request_core",
            "bootstrap_semantic_reduction_authority",
            "bootstrap_graph_normalization_authority",
        }
        kinds = tuple(member.kind for member in self.members)
        ordered_categories = (
            "bootstrap_proposal_run_payload", "bootstrap_analysis_lane_result",
            "bootstrap_pre_alignment_operation_subject_set", "bootstrap_analyzer_scope_observation",
            "bootstrap_analyzer_temporal_attachment_observation", "bootstrap_parser_consensus_assessment",
            "bootstrap_semantic_scope_consensus", "bootstrap_temporal_attachment_consensus",
            "bootstrap_operation_temporal_attachment_consensus_set",
            "bootstrap_source_local_identity_partition_evidence",
            "bootstrap_source_local_identity_resolution", "bootstrap_proposal_coverage_audit",
            "bootstrap_operation_alignment", "bootstrap_source_dependency_group",
            "bootstrap_graph_free_interpretation_bundle", "bootstrap_source_proposal_alignment",
            "bootstrap_source_normalization_request",
            "bootstrap_source_normalization_evidence_manifest",
            "bootstrap_source_normalization_result",
            "bootstrap_normalization_request_core",
            "bootstrap_semantic_reduction_authority",
            "bootstrap_graph_normalization_authority",
        )
        positions = {kind: index for index, kind in enumerate(ordered_categories)}
        singleton_categories = {
            "bootstrap_proposal_run_payload", "bootstrap_graph_free_interpretation_bundle",
            "bootstrap_source_proposal_alignment", "bootstrap_source_local_identity_partition_evidence",
            "bootstrap_source_local_identity_resolution", "bootstrap_proposal_coverage_audit",
            "bootstrap_source_normalization_request",
            "bootstrap_source_normalization_evidence_manifest",
            "bootstrap_source_normalization_result",
            "bootstrap_normalization_request_core",
            "bootstrap_semantic_reduction_authority",
            "bootstrap_graph_normalization_authority",
        }
        if (
            any(kind not in allowed for kind in kinds)
            or len({member.member_id for member in self.members}) != len(self.members)
            or tuple(sorted(kinds, key=positions.__getitem__)) != kinds
            or any(kinds.count(kind) != 1 for kind in singleton_categories)
        ):
            raise ValueError("bootstrap V3 atomic member registry is invalid")
        if self.required_artifact_digests != tuple(member.payload_digest for member in self.members):
            raise ValueError("bootstrap V3 required artifact closure is not exact")
        if self.request_digest != generation_request_digest(self):
            raise ValueError("bootstrap V3 atomic request digest is invalid")
        return self


# These host-owned leaves import policy contracts from this module.  Resolve the
# persisted closure only after those policy classes have been declared, rather
# than weakening its fields to BaseModel and losing their closed wire schema.
from memorii.core.semantic_ingestion.source_normalization_authority import (  # noqa: E402
    CapabilityRegistrySnapshot,
    GraphDependentExecutionPolicy,
)

_SOURCE_NORMALIZATION_TYPES = {
    "CapabilityRegistrySnapshot": CapabilityRegistrySnapshot,
    "GraphDependentExecutionPolicy": GraphDependentExecutionPolicy,
}


def rebuild_bootstrap_graph_effect_contracts() -> None:
    """Resolve terminal effect payload owners after replay has initialized."""
    from memorii.core.memory_evolution.graph_effect_contracts import (
        CanonicalSourceTerminalOutcomeCore,
        CanonicalSourceTerminalOutcomeRecord,
        GraphRevisionDelta,
        IngestionObservationDelta,
        rebuild_graph_effect_contracts,
    )
    from memorii.core.memory_evolution.graph_planning import (
        CanonicalPlanningRecordPayload,
        GraphPlanningState,
        NonPublishingIdentityPlanningResultV3,
        PlanningActionRevision,
        PlanningAliasRevision,
        PlanningCitation,
        PlanningClaimAssertion,
        PlanningClaimProjection,
        PlanningEntityRevision,
        PlanningProvenance,
        PlanningRecordPrecondition,
        PlanningReferenceDisposition,
        PlanningRelationRevision,
        PlanningTemporalTransition,
        PlanningTypeEvidence,
    )
    from memorii.core.memory_evolution.graph_records import (
        AcceptedIdentityOperationArtifact,
        PlannedIdentityReservation,
        TrustedAcceptedIdentityOperationDecision,
        VerifiedIdentityDecisionAuthority,
    )
    from memorii.core.memory_evolution.semantic_compilation import SemanticCompilationResult
    from memorii.core.memory_evolution.transaction_coordinator import (
        GraphReadSetToken,
        SealedGraphStateSnapshot,
    )
    from memorii.core.semantic_ingestion.event_replay import SemanticMemoryEventBatch

    rebuild_graph_effect_contracts()
    namespace = {
        **_SOURCE_NORMALIZATION_TYPES,
        "CanonicalSourceTerminalOutcomeRecord": CanonicalSourceTerminalOutcomeRecord,
        "CanonicalSourceTerminalOutcomeCore": CanonicalSourceTerminalOutcomeCore,
        "GraphRevisionDelta": GraphRevisionDelta,
        "IngestionObservationDelta": IngestionObservationDelta,
        "SemanticMemoryEventBatch": SemanticMemoryEventBatch,
        "GraphPlanningState": GraphPlanningState,
        "CanonicalPlanningRecordPayload": CanonicalPlanningRecordPayload,
        "NonPublishingIdentityPlanningResultV3": NonPublishingIdentityPlanningResultV3,
        "PlanningRecordPrecondition": PlanningRecordPrecondition,
        "PlanningActionRevision": PlanningActionRevision,
        "PlanningAliasRevision": PlanningAliasRevision,
        "PlanningCitation": PlanningCitation,
        "PlanningClaimAssertion": PlanningClaimAssertion,
        "PlanningClaimProjection": PlanningClaimProjection,
        "PlanningEntityRevision": PlanningEntityRevision,
        "PlanningProvenance": PlanningProvenance,
        "PlanningReferenceDisposition": PlanningReferenceDisposition,
        "PlanningRelationRevision": PlanningRelationRevision,
        "PlanningTemporalTransition": PlanningTemporalTransition,
        "PlanningTypeEvidence": PlanningTypeEvidence,
        "SealedGraphStateSnapshot": SealedGraphStateSnapshot,
        "BootstrapNativeTargetResolutionAuthorityV3": BootstrapNativeTargetResolutionAuthorityV3,
        "AcceptedIdentityOperationArtifact": AcceptedIdentityOperationArtifact,
        "PlannedIdentityReservation": PlannedIdentityReservation,
        "TrustedAcceptedIdentityOperationDecision": TrustedAcceptedIdentityOperationDecision,
        "VerifiedIdentityDecisionAuthority": VerifiedIdentityDecisionAuthority,
        "SemanticCompilationResult": SemanticCompilationResult,
        "GraphReadSetToken": GraphReadSetToken,
        "BootstrapGraphCheckpointReceiptV3": BootstrapGraphCheckpointReceiptV3,
        "BootstrapGraphPlanAtomicReloadCoreV3": BootstrapGraphPlanAtomicReloadCoreV3,
        "BootstrapNativeGroupCommitTerminalConstructionV3": BootstrapNativeGroupCommitTerminalConstructionV3,
    }
    for model in (
        BootstrapGraphObservationDeltaEffectV3,
        BootstrapGraphDeltaEffectV3,
        BootstrapGraphEventBatchEffectV3,
        BootstrapGraphEffectNotApplicableV3,
        BootstrapGraphGroupCasRequestV3,
        BootstrapGraphGroupCasOutcomeV3,
        BootstrapNativeGroupCommitTerminalConstructionV3,
        BootstrapGraphCanonicalSourceResultV3,
        BootstrapGraphCanonicalSourceResultInputV3,
        BootstrapGraphTerminalPublicationRequestV3,
        BootstrapGraphTerminalReloadV3,
        BootstrapGraphPlanAtomicWriteRequestV3,
        BootstrapGraphPlanAtomicReloadV3,
        BootstrapTransactionGroupOperationPlanV3,
        BootstrapTransactionGroupPlanMemberV3,
        BootstrapNativeTargetPlanningRequestV3,
        BootstrapNativeTargetResolutionAuthorityV3,
        BootstrapNativeEntitySeedV3,
        BootstrapNativeFactPlanningSeedV3,
        BootstrapNativeCorrectionPlanningSeedV3,
        BootstrapNativeRetractionPlanningSeedV3,
        BootstrapNativeActionPlanningSeedV3,
        BootstrapNativeIdentityPlanningSeedV3,
        BootstrapNativePlanningRecordV3,
        BootstrapNativeIdentityMaterializationV3,
        BootstrapGraphTargetMaterializationPlanV3,
        BootstrapNativePlanningUnavailableV3,
        BootstrapNewCanonicalIdentityAllocationV3,
        BootstrapCanonicalIdentityBindingAllocationAuthorityV3,
        BootstrapCanonicalIdentityBindingAllocationReloadV3,
        BootstrapNativeIdentityAdmissionRequestV3,
        BootstrapNativeIdentityAdmissionV3,
        BootstrapNativeRecordMaterializationIntentV3,
        BootstrapNativeIdentityEffectV3,
        BootstrapGraphOperationReductionV3,
        BootstrapGraphOperationStoreMaterializationInputV3,
        BootstrapGraphGroupCommitRequestV3,
        BootstrapGraphGroupCommitReloadV3,
    ):
        model.model_rebuild(_types_namespace=namespace)

for _source_normalization_model in (
    BootstrapSegmentAnalysisInputV3,
    BootstrapSemanticProposalRequestV3,
    BootstrapLinguisticAnalysisRequestV3,
    BootstrapPredicateEventDetectionRequestV3,
    BootstrapTemporalResolutionRequestV3,
    BootstrapAnalysisLaneResultV3,
    BootstrapStanzaLanePayloadV3,
    BootstrapSpacyLanePayloadV3,
    BootstrapPredicateLanePayloadV3,
    BootstrapTemporalLanePayloadV3,
    BootstrapPreAlignmentOperationSubjectV3,
    BootstrapPreAlignmentOperationSubjectSetV3,
    BootstrapOperationAlignmentV3,
    BootstrapSourceDependencyGroupV3,
    BootstrapGraphFreeInterpretationBundleV3,
    BootstrapGraphFreeIdentityPlanningInputV3,
    BootstrapOperationCoverageBindingV3,
    BootstrapNativeOperationReductionInputV3,
    BootstrapSourceProposalAlignmentV3,
    BootstrapCanonicalRoleAssignmentV3,
    BootstrapAnalyzerRoleInterpretationV3,
    BootstrapAnalyzerScopeInterpretationV3,
    BootstrapStableSemanticScopeV3,
    BootstrapAnalyzerTemporalAttachmentV3,
    BootstrapAnalyzerScopeObservationV3,
    BootstrapAnalyzerTemporalAttachmentObservationV3,
    BootstrapParserConsensusAssessmentV3,
    BootstrapSemanticScopeConsensusV3,
    BootstrapTemporalAttachmentConsensusV3,
    BootstrapOperationTemporalAttachmentConsensusSetV3,
    BootstrapSourceLocalIdentityClusterDecisionV3,
    BootstrapCoveredPredicateEventV3,
    BootstrapUnresolvedPredicateEventV3,
    BootstrapSemanticProposalRunV3,
    BootstrapSourceNormalizationRequestV3,
    BootstrapSourceNormalizationEvidenceManifestV3,
    BootstrapSourceNormalizationResultV3,
    BootstrapNormalizationRequestCoreV3,
    BootstrapSemanticReductionAuthorityMemberV3,
    BootstrapSemanticReductionAuthorityReloadV3,
    GraphDependentExecutionPolicyReferenceV3,
    GraphSemanticSnapshotBundleV3,
    BootstrapRecoveryReplayRecordV3,
    BootstrapGraphSnapshotAuthorityV3,
    BootstrapGraphNormalizationAuthorityMemberV3,
    BootstrapGraphNormalizationAuthorityReloadV3,
    BootstrapGraphPreparedSourceTerminalAuthorityV3,
    BootstrapGraphTransactionAuthorityProjectionV3,
    BootstrapGraphAuthorityGenerationV3,
    BootstrapGraphTransactionAuthorityWriteRequestV3,
    BootstrapGraphAuthorityPublicationCoreV3,
    BootstrapGraphAuthorityPublicationReceiptV3,
    BootstrapGraphTransactionAuthorityReloadV3,
    BootstrapGraphControlEpochV3,
    BootstrapGraphControlEpochTransitionRequestV3,
    BootstrapGraphControlEpochFoundV3,
    BootstrapGraphControlEpochAdvancedV3,
    BootstrapGraphControlEpochUnavailableV3,
    BootstrapGraphDependentCoordinatorRequestV3,
    BootstrapGraphTerminalHandoffCoreV3,
    BootstrapGraphTerminalMemberIntentV3,
    BootstrapGraphTerminalPublicationIntentV3,
    BootstrapGraphPlanAtomicWriteIdentityV3,
    BootstrapGraphTerminalControlV3,
    BootstrapGraphTerminalPersistenceHandoffV3,
    BootstrapGraphPlanAtomicMemberV3,
    BootstrapGraphCurrentGenerationV3,
    BootstrapGraphCheckpointReceiptV3,
    BootstrapGraphPlanAtomicWriteRequestV3,
    BootstrapGraphPlanAtomicReloadCoreV3,
    BootstrapGraphPlanAtomicReloadV3,
):
    _source_normalization_model.model_rebuild(
        _types_namespace=_SOURCE_NORMALIZATION_TYPES,
    )

_ContractModel = TypeVar("_ContractModel", bound=BaseModel)
_CONTRACT_KINDS: dict[type[BaseModel], str] = {
    SemanticTerminalOutcome: "semantic_terminal",
    SemanticAuthorizationReadSet: "authorization_read_set",
    SemanticLifecycleTransition: "lifecycle_transition",
    SemanticRetryableProgress: "retryable_progress",
    SemanticRecoveryAuthorityBinding: "recovery_authority_binding",
    SemanticArtifactClosure: "artifact_closure",
    SemanticGraphDelta: "graph_delta",
    SemanticEventInputBatch: "event_batch",
    SemanticObservationDelta: "observation_delta",
    SemanticEffectGroupResult: "group_result",
    SegmentGovernanceBinding: "segment_governance_binding",
    SegmentGovernanceCarrierSet: "segment_governance_carrier_set",
    RequiredOutcomeScopeSet: "required_outcome_scope_set",
    MessageAdmissionIdentity: "message_admission_identity",
    MessageAdmissionCarrierSet: "message_admission_carrier_set",
    GovernanceCarrierArtifact: "governance_carrier_artifact",
    SegmentLanguageResourceBinding: "segment_language_resource_binding",
    SegmentLanguageRoute: "segment_language_route",
    BootstrapDeclaredSegmentLanguageRoute: "bootstrap_declared_segment_language_route",
    SegmentLanguageRouteSet: "segment_language_route_set",
    TextPreparationPolicy: "text_preparation_policy",
    TextPreparationRequest: "text_preparation_request",
    ActionProposalRoleContract: "action_proposal_role_contract",
    ActionProposalStateContract: "action_proposal_state_contract",
    ActionProposalCatalog: "action_proposal_catalog",
    PredicatePromptContract: "predicate_prompt_contract",
    PredicateProposalCatalog: "predicate_proposal_catalog",
    RegisteredSemanticPromptBinding: "registered_semantic_prompt_binding",
    SemanticProposerManifest: "semantic_proposer_manifest",
    SourceSemanticContext: "source_semantic_context",
    SemanticProjectionSegment: "semantic_projection_segment",
    SourceSemanticTextProjection: "source_semantic_text_projection",
    PreparedSegment: "prepared_segment",
    PreparedSource: "prepared_source",
    CanonicalRoleAssignment: "canonical_role_assignment",
    AnalyzerRoleInterpretation: "analyzer_role_interpretation",
    CheckResult: "check_result",
    AnalyzerScopeInterpretation: "analyzer_scope_interpretation",
    StableSemanticScope: "stable_semantic_scope",
    AnalyzerTemporalAttachment: "analyzer_temporal_attachment",
    ParserConsensusAssessment: "parser_consensus_assessment",
    SemanticScopeConsensus: "semantic_scope_consensus",
    TemporalAttachmentConsensus: "temporal_attachment_consensus",
    SourceLocalIdentityResolution: "source_local_identity_resolution",
    OperationAlignment: "operation_alignment",
    OperationTemporalAttachmentConsensusSet: "operation_temporal_attachment_consensus_set",
    BootstrapSourceNormalizationAtomicWriteRequestV3: "bootstrap_source_normalization_atomic_write_request_v3",
    BootstrapSegmentAnalysisInputV3: "bootstrap_segment_analysis_input_v3",
    BootstrapSemanticProposalRequestV3: "bootstrap_semantic_proposal_request_v3",
    BootstrapLinguisticAnalysisRequestV3: "bootstrap_linguistic_analysis_request_v3",
    BootstrapPredicateEventDetectionRequestV3: "bootstrap_predicate_event_detection_request_v3",
    BootstrapTemporalResolutionRequestV3: "bootstrap_temporal_resolution_request_v3",
    BootstrapAnalysisLaneResultV3: "bootstrap_analysis_lane_result_v3",
    BootstrapSemanticProposalRunV3: "bootstrap_semantic_proposal_run_v3",
    BootstrapSourceNormalizationRequestV3: "bootstrap_source_normalization_request_v3",
    BootstrapSourceNormalizationEvidenceManifestV3: "bootstrap_source_normalization_evidence_manifest_v3",
    BootstrapSourceNormalizationResultV3: "bootstrap_source_normalization_result_v3",
    BootstrapNormalizationRequestCoreV3: "bootstrap_normalization_request_core_v3",
    BootstrapSemanticReductionAuthorityMemberV3: "bootstrap_semantic_reduction_authority_member_v3",
    BootstrapSemanticReductionAuthorityReloadV3: "bootstrap_semantic_reduction_authority_reload_v3",
    GraphDependentExecutionPolicyReferenceV3: "bootstrap_graph_execution_policy_reference_v3",
    GraphSemanticSnapshotBundleV3: "bootstrap_graph_semantic_snapshot_bundle_v3",
    BootstrapRecoveryReplayRecordV3: "bootstrap_recovery_replay_record_v3",
    BootstrapGraphSnapshotAuthorityV3: "bootstrap_graph_snapshot_authority_v3",
    BootstrapGraphNormalizationAuthorityMemberV3: "bootstrap_graph_normalization_authority_member_v3",
    BootstrapGraphNormalizationAuthorityReloadV3: "bootstrap_graph_normalization_authority_reload_v3",
    BootstrapGraphPreparedSourceTerminalAuthorityV3: "bootstrap_graph_prepared_source_terminal_authority_v3",
    BootstrapGraphTransactionAuthorityProjectionV3: "bootstrap_graph_transaction_authority_projection_v3",
    BootstrapGraphAuthorityGenerationV3: "bootstrap_graph_authority_generation_v3",
    BootstrapGraphTransactionAuthorityWriteRequestV3: "bootstrap_graph_transaction_authority_write_request_v3",
    BootstrapGraphAuthorityPublicationCoreV3: "bootstrap_graph_authority_publication_core_v3",
    BootstrapGraphAuthorityPublicationReceiptV3: "bootstrap_graph_authority_publication_receipt_v3",
    BootstrapGraphTransactionAuthorityReloadV3: "bootstrap_graph_transaction_authority_reload_v3",
    BootstrapGraphControlEpochV3: "bootstrap_graph_control_epoch_v3",
    BootstrapGraphControlEpochTransitionRequestV3: "bootstrap_graph_control_epoch_transition_v3",
    BootstrapGraphControlEpochFoundV3: "bootstrap_graph_control_epoch_found_v3",
    BootstrapGraphControlEpochAdvancedV3: "bootstrap_graph_control_epoch_advanced_v3",
    BootstrapGraphControlEpochUnavailableV3: "bootstrap_graph_control_epoch_unavailable_v3",
    BootstrapGraphDependentCoordinatorRequestV3: "bootstrap_graph_dependent_coordinator_request_v3",
    BootstrapReservationUseAuthorizationV3: "bootstrap_reservation_use_authorization_v3",
    BootstrapNoReservationUseV3: "bootstrap_no_reservation_use_v3",
    BootstrapIdentityReservationUseSetV3: "bootstrap_identity_reservation_use_set_v3",
    BootstrapTransactionGroupOperationPlanV3: "bootstrap_transaction_group_operation_plan_v3",
    BootstrapGraphTargetReferenceV3: "bootstrap_graph_target_reference_v3_native",
    BootstrapSourceOperationMembershipV3: "bootstrap_source_operation_membership_v3",
    BootstrapCanonicalClusterReferenceOccurrenceV3: "bootstrap_canonical_cluster_reference_occurrence_v3",
    BootstrapCanonicalFirstUseConsumerV3: "bootstrap_canonical_first_use_consumer_v3",
    BootstrapCanonicalFirstUseDependencyV3: "bootstrap_canonical_first_use_dependency_v3",
    BootstrapCanonicalPlanningPrefixProofV3: "bootstrap_canonical_planning_prefix_proof_v3",
    BootstrapCanonicalIdentityDecisionProofV3: "bootstrap_canonical_identity_decision_proof_v3",
    BootstrapExistingCanonicalIdentityDecisionV3: "bootstrap_existing_canonical_identity_decision_v3",
    BootstrapNewCanonicalIdentityAllocationV3: "bootstrap_new_canonical_identity_allocation_v3",
    BootstrapAbsentCanonicalIdentityDecisionV3: "bootstrap_absent_canonical_identity_decision_v3",
    BootstrapNativeMentionTargetCandidateV3: "bootstrap_native_mention_target_candidate_v3",
    BootstrapNativeSelectorTargetV3: "bootstrap_native_selector_target_v3",
    BootstrapNativeTargetResolutionAuthorityV3: "bootstrap_native_target_resolution_authority_v3",
    BootstrapNativeEntitySeedV3: "bootstrap_native_entity_seed_v3",
    BootstrapNativeFactPlanningSeedV3: "bootstrap_native_fact_planning_seed_v3",
    BootstrapNativeCorrectionPlanningSeedV3: "bootstrap_native_correction_planning_seed_v3",
    BootstrapNativeRetractionPlanningSeedV3: "bootstrap_native_retraction_planning_seed_v3",
    BootstrapNativeActionPlanningSeedV3: "bootstrap_native_action_planning_seed_v3",
    BootstrapNativeIdentityPlanningSeedV3: "bootstrap_native_identity_planning_seed_v3",
    BootstrapCanonicalIdentityAuthorityWriteRequestV3: "bootstrap_canonical_identity_authority_write_request_v3",
    BootstrapNativeTargetPlanningRequestV3: "bootstrap_native_target_planning_request_v3",
    BootstrapSnapshotTargetAuthorityV3: "bootstrap_snapshot_target_authority_v3",
    BootstrapPendingTargetAuthorityV3: "bootstrap_pending_target_authority_v3",
    BootstrapNativeTargetBindingV3: "bootstrap_native_target_binding_v3",
    BootstrapNativePlanningRecordV3: "bootstrap_native_planning_record_v3",
    BootstrapNativeTemporalTerminalBindingV3: "bootstrap_native_temporal_terminal_binding_v3",
    BootstrapNativeEvidenceProjectionV3: "bootstrap_native_evidence_projection_v3",
    BootstrapNativeIdentityMaterializationV3: "bootstrap_native_identity_materialization_v3",
    BootstrapGraphTargetMaterializationPlanV3: "bootstrap_graph_target_materialization_plan_v3",
    BootstrapNativePlanningUnavailableV3: "bootstrap_native_planning_unavailable_v3",
    BootstrapNativeIdentityAdmissionRequestV3: "bootstrap_native_identity_admission_request_v3",
    BootstrapNativeIdentityAdmissionV3: "bootstrap_native_identity_admission_v3",
    BootstrapNativeRecordMaterializationIntentV3: "bootstrap_native_record_materialization_intent_v3",
    BootstrapNativeFactEffectV3: "bootstrap_native_fact_effect_v3",
    BootstrapNativeCorrectionEffectV3: "bootstrap_native_correction_effect_v3",
    BootstrapNativeRetractionEffectV3: "bootstrap_native_retraction_effect_v3",
    BootstrapNativeActionStateEffectV3: "bootstrap_native_action_state_effect_v3",
    BootstrapNativeIdentityEffectV3: "bootstrap_native_identity_effect_v3",
    SemanticSealedOperation: "bootstrap_native_sealed_operation_v3",
    BootstrapNativeOperationCompilationV3: "bootstrap_native_operation_compilation_v3",
    BootstrapNativeOperationEffectMaterializationV3: "bootstrap_native_operation_effect_materialization_v3",
    BootstrapNativeOperationTerminalV3: "bootstrap_native_operation_terminal_v3",
    BootstrapNativeOperationArtifactClosureV3: "bootstrap_native_operation_artifact_closure_v3",
    BootstrapGraphOperationReductionV3: "bootstrap_graph_operation_reduction_v3",
    BootstrapGraphOperationStoreMaterializationInputV3: "bootstrap_graph_operation_store_materialization_input_v3",
    BootstrapGraphOperationCommitResultV3: "bootstrap_graph_operation_commit_result_v3",
    BootstrapGraphGroupCommitResultCoreV3: "bootstrap_graph_group_commit_result_core_v3",
    BootstrapGraphAtomicEffectReceiptV3: "bootstrap_graph_atomic_effect_receipt_v3",
    BootstrapGraphGroupCommitResultV3: "bootstrap_graph_group_commit_result_v3",
    BootstrapGraphGroupCommitRequestV3: "bootstrap_graph_group_commit_request_v3",
    BootstrapGraphGroupCommitReloadV3: "bootstrap_graph_group_commit_reload_v3",
    BootstrapNativeGroupCommitTerminalConstructionV3: "bootstrap_native_group_commit_terminal_construction_v3",
    BootstrapGraphObservationDeltaEffectV3: "bootstrap_graph_observation_delta_effect_v3",
    BootstrapGraphDeltaEffectV3: "bootstrap_graph_delta_effect_v3",
    BootstrapGraphEventBatchEffectV3: "bootstrap_graph_event_batch_effect_v3",
    BootstrapGraphEffectNotApplicableV3: "bootstrap_graph_effect_not_applicable_v3",
    BootstrapGraphGroupCasRequestV3: "bootstrap_graph_group_cas_request_v3",
    BootstrapGraphGroupCasOutcomeV3: "bootstrap_graph_group_cas_outcome_v3",
    BootstrapGraphGroupExecutionResultV3: "bootstrap_graph_group_execution_result_v3",
    BootstrapGraphGroupResultConstructionV3: "bootstrap_graph_group_result_construction_v3",
    BootstrapGraphCanonicalSourceResultV3: "bootstrap_graph_canonical_source_result_v3",
    BootstrapGraphCanonicalSourceResultInputV3: "bootstrap_graph_canonical_source_result_input_v3",
    BootstrapGraphTerminalPublicationRequestV3: "bootstrap_graph_terminal_publication_request_v3",
    BootstrapGraphTerminalHostAuthorityV3: "bootstrap_graph_terminal_host_authority_v3",
    BootstrapGraphTerminalPreparationV3: "bootstrap_graph_terminal_preparation_v3",
    BootstrapGraphFinalStageEvidenceV3: "bootstrap_graph_final_stage_evidence_v3",
    BootstrapGraphTerminalHandoffCoreV3: "bootstrap_graph_terminal_handoff_core_v3",
    BootstrapGraphTerminalMemberIntentV3: "bootstrap_graph_terminal_member_intent_v3",
    BootstrapGraphTerminalPublicationIntentV3: "bootstrap_graph_terminal_publication_intent_v3",
    BootstrapGraphPlanAtomicWriteIdentityV3: "bootstrap_graph_plan_atomic_write_identity_v3",
    BootstrapGraphTerminalControlV3: "bootstrap_graph_terminal_control_v3",
    BootstrapGraphTerminalPersistenceHandoffV3: "bootstrap_graph_terminal_persistence_handoff_v3",
    BootstrapGraphTerminalReloadV3: "bootstrap_graph_terminal_reload_v3",
    BootstrapGraphPlanAtomicMemberV3: "bootstrap_graph_plan_atomic_member_v3",
    BootstrapGraphCurrentGenerationV3: "bootstrap_graph_current_generation_v3",
    BootstrapGraphCheckpointReceiptV3: "bootstrap_graph_checkpoint_receipt_v3",
    BootstrapGraphPlanAtomicWriteRequestV3: "bootstrap_graph_plan_atomic_write_request_v3",
    BootstrapGraphAttemptConstructionInputsV3: "bootstrap_graph_attempt_construction_inputs_v3",
    BootstrapGraphPreExecutionManifestCoreV3: "bootstrap_graph_pre_execution_manifest_core_v3",
    BootstrapGraphPreExecutionManifestIdentityV3: "bootstrap_graph_pre_execution_manifest_identity_v3",
    BootstrapGraphPreExecutionManifestIdentityClosureV3: "bootstrap_graph_pre_execution_manifest_identity_closure_v3",
    BootstrapGraphExecutionManifestConstructionV3: "bootstrap_graph_execution_manifest_construction_v3",
    BootstrapGraphPreExecutionGroupEvidenceV3: "bootstrap_graph_pre_execution_group_evidence_v3",
    BootstrapGraphPlanAtomicReloadV3: "bootstrap_graph_plan_atomic_reload_v3",
    BootstrapGraphPlanAtomicReloadCoreV3: "bootstrap_graph_plan_atomic_reload_core_v3",
    BootstrapTransactionGroupPlanMemberV3: "bootstrap_transaction_group_plan_member_v3",
    BootstrapTransactionGroupPlanV3: "bootstrap_transaction_group_plan_v3",
    BootstrapGroupPlanningAuthorizationV3: "bootstrap_group_planning_authorization_v3",
    BootstrapSourcePlanLineageEntryReferenceV3: "bootstrap_source_plan_lineage_entry_reference_v3",
    BootstrapFinalGroupResultReferenceV3: "bootstrap_final_group_result_reference_v3",
    BootstrapGraphReplanPartitionV3: "bootstrap_graph_replan_partition_v3",
    BootstrapInitialAttemptAuthorityV3: "bootstrap_initial_attempt_authority_v3",
    BootstrapGraphDependentAttemptV3: "bootstrap_graph_dependent_attempt_v3",
    BootstrapSourcePlanLineageEntryV3: "bootstrap_source_plan_lineage_entry_v3",
    BootstrapSourcePlanLineageV3: "bootstrap_source_plan_lineage_v3",
    BootstrapGraphGroupResultV3: "bootstrap_graph_group_result_v3",
    BootstrapReusedCommittedGroupAuthorityV3: "bootstrap_reused_committed_group_authority_v3",
    BootstrapReusedFinalGroupAuthorityV3: "bootstrap_reused_final_group_authority_v3",
    BootstrapReusedUnfinishedGroupAuthorityV3: "bootstrap_reused_unfinished_group_authority_v3",
    BootstrapReplacementGroupAuthorityV3: "bootstrap_replacement_group_authority_v3",
    BootstrapSuccessorAttemptAuthorityV3: "bootstrap_successor_attempt_authority_v3",
    BootstrapGraphDurableRetryProgressV3: "bootstrap_graph_durable_retry_progress_v3",
    BootstrapV3PayloadLimitPolicy: "bootstrap_v3_payload_limit_policy",
    BootstrapV3PayloadLimitAuthority: "bootstrap_v3_payload_limit_authority",
    BootstrapProposalEvidenceItemV3: "bootstrap_proposal_evidence_item_v3",
    BootstrapProposalMentionV3: "bootstrap_proposal_mention_v3",
    BootstrapProposalTypedLiteralV3: "bootstrap_proposal_typed_literal_v3",
    BootstrapProposalEntityObjectV3: "bootstrap_proposal_entity_object_v3",
    BootstrapProposalLiteralObjectV3: "bootstrap_proposal_literal_object_v3",
    BootstrapProposalFactV3: "bootstrap_proposal_fact_v3",
    BootstrapProposalCorrectionV3: "bootstrap_proposal_correction_v3",
    BootstrapProposalRetractionV3: "bootstrap_proposal_retraction_v3",
    BootstrapProposalActionRoleParticipantV3: "bootstrap_proposal_action_role_participant_v3",
    BootstrapProposalActionRoleBindingV3: "bootstrap_proposal_action_role_binding_v3",
    BootstrapProposalActionStateV3: "bootstrap_proposal_action_state_v3",
    BootstrapProposalClaimRecordSelectorV3: "bootstrap_proposal_claim_record_selector_v3",
    BootstrapProposalActionRecordSelectorV3: "bootstrap_proposal_action_record_selector_v3",
    BootstrapProposalAliasRecordSelectorV3: "bootstrap_proposal_alias_record_selector_v3",
    BootstrapProposalReferenceAssignmentV3: "bootstrap_proposal_reference_assignment_v3",
    BootstrapProposalIdentityOperationV3: "bootstrap_proposal_identity_operation_v3",
    BootstrapProposalTransportRequestV3: "bootstrap_proposal_transport_request_v3",
    BootstrapProposalAttemptV3: "bootstrap_proposal_attempt_v3",
    BootstrapNormalizedProposalV3: "bootstrap_normalized_proposal_v3",
    BootstrapProposalRunPayloadV3: "bootstrap_proposal_run_payload_v3",
    BootstrapStanzaLanePayloadV3: "bootstrap_stanza_lane_payload_v3",
    BootstrapSpacyLanePayloadV3: "bootstrap_spacy_lane_payload_v3",
    BootstrapAnalysisSourceEvidenceV3: "bootstrap_analysis_source_evidence_v3",
    BootstrapPredicateEventCandidateV3: "bootstrap_predicate_event_candidate_v3",
    BootstrapPredicateLanePayloadV3: "bootstrap_predicate_lane_payload_v3",
    BootstrapTemporalReferenceV3: "bootstrap_temporal_reference_v3",
    BootstrapResolvedTemporalCandidateV3: "bootstrap_resolved_temporal_candidate_v3",
    BootstrapTemporalAmbiguityMemberV3: "bootstrap_temporal_ambiguity_member_v3",
    BootstrapTemporalAmbiguitySetV3: "bootstrap_temporal_ambiguity_set_v3",
    BootstrapTemporalLanePayloadV3: "bootstrap_temporal_lane_payload_v3",
    BootstrapPreAlignmentOperationSubjectV3: "bootstrap_pre_alignment_operation_subject_v3",
    BootstrapPreAlignmentOperationSubjectSetV3: "bootstrap_pre_alignment_operation_subject_set_v3",
    BootstrapOperationAlignmentV3: "bootstrap_operation_alignment_v3",
    BootstrapSourceDependencyGroupV3: "bootstrap_source_dependency_group_v3",
    BootstrapGraphFreeInterpretationBundleV3: "bootstrap_graph_free_interpretation_bundle_v3",
    BootstrapSourceProposalAlignmentV3: "bootstrap_source_proposal_alignment_v3",
    BootstrapCanonicalRoleAssignmentV3: "bootstrap_canonical_role_assignment_v3",
    BootstrapAnalyzerRoleInterpretationV3: "bootstrap_analyzer_role_interpretation_v3",
    BootstrapAnalyzerScopeInterpretationV3: "bootstrap_analyzer_scope_interpretation_v3",
    BootstrapStableSemanticScopeV3: "bootstrap_stable_semantic_scope_v3",
    BootstrapAnalyzerTemporalAttachmentV3: "bootstrap_analyzer_temporal_attachment_v3",
    BootstrapAnalyzerScopeObservationV3: "bootstrap_analyzer_scope_observation_v3",
    BootstrapAnalyzerTemporalAttachmentObservationV3: "bootstrap_analyzer_temporal_attachment_observation_v3",
    BootstrapParserConsensusAssessmentV3: "bootstrap_parser_consensus_assessment_v3",
    BootstrapSemanticScopeConsensusV3: "bootstrap_semantic_scope_consensus_v3",
    BootstrapTemporalAttachmentConsensusV3: "bootstrap_temporal_attachment_consensus_v3",
    BootstrapOperationTemporalAttachmentConsensusSetV3: "bootstrap_operation_temporal_attachment_consensus_set_v3",
    BootstrapSourcePrePartitionMentionV3: "bootstrap_source_pre_partition_mention_v3",
    BootstrapSourceLocalIdentityAssertionV3: "bootstrap_source_local_identity_assertion_v3",
    BootstrapSourceLocalIdentityPartitionEvidenceV3: "bootstrap_source_local_identity_partition_evidence_v3",
    BootstrapSourceLocalIdentityClusterDecisionV3: "bootstrap_source_local_identity_cluster_decision_v3",
    BootstrapSourceLocalIdentityResolutionV3: "bootstrap_source_local_identity_resolution_v3",
    BootstrapCoveredPredicateEventV3: "bootstrap_covered_predicate_event_v3",
    BootstrapUnresolvedPredicateEventV3: "bootstrap_unresolved_predicate_event_v3",
    BootstrapProposalCoverageAuditV3: "bootstrap_proposal_coverage_audit_v3",
    SourceDependencyGroup: "source_dependency_group",
    TransactionSemanticGroup: "transaction_semantic_group",
    PlannedTransactionGroupExecution: "planned_transaction_group_execution",
    GroupIndependenceCertificate: "group_independence_certificate",
    TransactionSemanticGroupPlan: "transaction_semantic_group_plan",
    GroupPlanningAuthorization: "group_planning_authorization",
    IngestionExecutionGraph: "ingestion_execution_graph",
    IngestionStageInstanceRef: "ingestion_stage_instance_ref",
    IngestionStageOutcome: "ingestion_stage_outcome",
    OperationCapabilityExecutionBinding: "operation_capability_execution_binding",
    GraphDependentValidationAttempt: "graph_dependent_validation_attempt",
    IngestionExecutionManifest: "ingestion_execution_manifest",
    TransactionGroupPlanLineageEntry: "transaction_group_plan_lineage_entry",
    SourceTransactionPlanLineage: "source_transaction_plan_lineage",
    SourceTransactionPlanLineageReference: "source_transaction_plan_lineage_reference",
    PrePlanningSourceIngestionProgress: "pre_planning_source_ingestion_progress",
    PlannedSourceIngestionProgress: "planned_source_ingestion_progress",
    TypedLiteral: "typed_literal",
    ConstructionFamily: "construction_family",
    UdPathStep: "ud_path_step",
    UdPathPattern: "ud_path_pattern",
    QuotationBoundaryPolicy: "quotation_boundary_policy",
    SemanticScopePolicy: "semantic_scope_policy",
    UdRoleSchema: "ud_role_schema",
    PredicateSemanticPolicy: "predicate_semantic_policy",
    RetainedSourceTextArtifact: "retained_source_text_artifact",
    SemanticProjectionTextArtifact: "semantic_projection_text_artifact",
    SegmentLocalTextArtifact: "segment_local_text_artifact",
    RetainedSourceTextSpan: "retained_source_text_span",
    ProjectionTextSpan: "projection_text_span",
    SegmentLocalTextSpan: "segment_local_text_span",
    VerbatimTextArtifactMappingProof: "verbatim_text_artifact_mapping_proof",
    EnvelopeFieldTextArtifactMappingProof: "envelope_field_text_artifact_mapping_proof",
    SourceSpanReference: "source_span_reference",
    ProposedMention: "proposed_mention",
    ProposedEntityObject: "proposed_entity_object",
    ProposedLiteralObject: "proposed_literal_object",
    ProposedFact: "proposed_fact",
    ProposedCorrection: "proposed_correction",
    ProposedRetraction: "proposed_retraction",
    ProposedActionRoleParticipant: "proposed_action_role_participant",
    ProposedActionRoleBinding: "proposed_action_role_binding",
    ProposedActionState: "proposed_action_state",
    ProposedClaimRecordSelector: "proposed_claim_record_selector",
    ProposedActionRecordSelector: "proposed_action_record_selector",
    ProposedAliasRecordSelector: "proposed_alias_record_selector",
    ProposedReferenceAssignment: "proposed_reference_assignment",
    ProposedIdentityOperation: "proposed_identity_operation",
    SemanticProposal: "semantic_proposal",
    SemanticProposalResponseArtifact: "semantic_proposal_response_artifact",
    SemanticProposalAttemptIdentity: "semantic_proposal_attempt_identity",
    SemanticProposalAttempt: "semantic_proposal_attempt",
    SegmentProposalOutcome: "segment_proposal_outcome",
    LinguisticFeature: "linguistic_feature",
    LinguisticToken: "linguistic_token",
    DependencyArc: "dependency_arc",
    SourceMention: "source_mention",
    ClauseArgument: "clause_argument",
    ClauseQuotationEvidence: "clause_quotation_evidence",
    ClauseAnalysis: "clause_analysis",
    SegmentLanguageLaneOutcome: "segment_language_lane_outcome",
    LinguisticAnalysis: "linguistic_analysis",
    PredicateEventCandidate: "predicate_event_candidate",
    PredicateEventInventory: "predicate_event_inventory",
    ResolvedTemporalCandidate: "resolved_temporal_candidate",
    TemporalResolution: "temporal_resolution",
    SegmentAnalysisInput: "segment_analysis_input",
    AnalyzerManifest: "analyzer_manifest",
    PredicateEventManifest: "predicate_event_manifest",
    TemporalResolverManifest: "temporal_resolver_manifest",
    LinguisticAnalysisRequest: "linguistic_analysis_request",
    PredicateEventDetectionRequest: "predicate_event_detection_request",
    TemporalResolutionRequest: "temporal_resolution_request",
    PreAlignmentSemanticOperationSubjectSet: "pre_alignment_semantic_operation_subject_set",
    ParserConsensusPolicy: "parser_consensus_policy",
    ScopeConsensusPolicy: "scope_consensus_policy",
    TemporalAttachmentConsensusPolicy: "temporal_attachment_consensus_policy",
    ConsensusPolicySelection: "consensus_policy_selection",
    PredicateSemanticPolicyBinding: "predicate_semantic_policy_binding",
    FactOperationSemanticPolicyKey: "fact_operation_semantic_policy_key",
    CorrectionOperationSemanticPolicyKey: "correction_operation_semantic_policy_key",
    RetractionOperationSemanticPolicyKey: "retraction_operation_semantic_policy_key",
    ActionStateOperationSemanticPolicyKey: "action_state_operation_semantic_policy_key",
    IdentityOperationSemanticPolicyKey: "identity_operation_semantic_policy_key",
    ParserOperationPolicyAuthority: "parser_operation_policy_authority",
    ScopeOperationPolicyAuthority: "scope_operation_policy_authority",
    LanguageConstructionPolicyAuthorityBundle: "language_construction_policy_authority_bundle",
    ClaimAssertion: "claim_assertion",
    ActionRevision: "action_revision",
    IdentityLineageRecord: "identity_lineage",
    TemporalTransitionRecord: "temporal_transition",
}


_CANONICAL_CONTRACT_ENVELOPE = "memorii.semantic-ingestion.contract-envelope.v1"


def encode_semantic_contract_result(
    value: BaseModel,
    *,
    canonical_staging: CanonicalEvidenceArena | None = None,
) -> ValidatedCanonicalEvidenceResult:
    """Build a validated result and stage it only through an explicit owner."""
    """Encode one active semantic ingestion contract with no legacy/upcast fallback."""
    kind = _CONTRACT_KINDS.get(type(value))
    if kind is None:
        raise SemanticContractCodecError(f"unsupported semantic ingestion contract type: {type(value).__name__}")
    reuse_scope = current_digest_verification_scope()
    if reuse_scope is not None:
        certified = reuse_scope.lookup_encoded_result(value)
        if certified is not None:
            # Object continuity within one operation: this exact instance
            # already passed the complete codec pipeline.  A staging owner
            # still receives its admission so sealed lookup behavior is
            # unchanged (duplicate keys are refused by the arena itself).
            if canonical_staging is not None:
                canonical_staging.admit_success(
                    canonical_contract_bytes=certified.canonical_contract_bytes,
                    concrete_contract_type=type(value),
                    profile_revision=CANONICAL_PROFILE_REVISION,
                    codec_revision=CANONICAL_CODEC_REVISION,
                    domain=certified.domain,
                    result=certified,
                )
            return certified
    payload = canonical_contract_value(value)
    domain = _CANONICAL_CONTRACT_ENVELOPE.encode("ascii") + b"\0" + kind.encode("ascii")
    canonical_bytes, member_spans = encode_typed_value_with_spans(
        {
            "schema": _CANONICAL_CONTRACT_ENVELOPE,
            "kind": kind,
            "payload": payload,
        }
    )
    # Revalidation makes forged model_copy/model_construct instances fail closed.
    result = _build_validated_semantic_contract_result(
        value=value,
        canonical_contract_bytes=canonical_bytes,
        canonical_payload=payload,
        member_spans=member_spans,
        domain=domain,
    )
    if canonical_staging is not None:
        canonical_staging.admit_success(
            canonical_contract_bytes=canonical_bytes,
            concrete_contract_type=type(value),
            profile_revision=CANONICAL_PROFILE_REVISION,
            codec_revision=CANONICAL_CODEC_REVISION,
            domain=domain,
            result=result,
        )
    if reuse_scope is not None:
        reuse_scope.record_encoded_result(value, result)
    return result


def encode_semantic_contract(value: BaseModel) -> bytes:
    """Encode with full validation; ordinary callers receive no cache authority.

    The bytes-only path emits through the single canonical writer without
    span issuance or member-evidence minting (those belong to the staged
    result pipeline) and still re-derives validation from the lowered
    payload, so forged copies fail closed exactly as the result path does.
    Within one enabled operation, an instance the codec already certified is
    served its proven bytes by object identity.
    """
    kind = _CONTRACT_KINDS.get(type(value))
    if kind is None:
        raise SemanticContractCodecError(f"unsupported semantic ingestion contract type: {type(value).__name__}")
    reuse_scope = current_digest_verification_scope()
    if reuse_scope is not None:
        certified_bytes = reuse_scope.lookup_encoded_bytes(value)
        if certified_bytes is not None:
            return certified_bytes
    payload = canonical_contract_value(value)
    canonical_bytes = encode_typed_value(
        {
            "schema": _CANONICAL_CONTRACT_ENVELOPE,
            "kind": kind,
            "payload": payload,
        }
    )
    _revalidated_contract_instance(value, payload)
    if reuse_scope is not None:
        reuse_scope.record_encoded_bytes(value, canonical_bytes)
    return canonical_bytes


def decode_semantic_contract(
    raw: bytes,
    expected_type: type[_ContractModel],
    *,
    max_nodes: int | None = None,
    max_depth: int | None = None,
) -> _ContractModel:
    """Decode only exact active bytes; pre-closure and unknown variants reject."""
    expected_kind = _CONTRACT_KINDS.get(expected_type)
    if expected_kind is None:
        raise SemanticContractCodecError(f"unsupported semantic ingestion contract type: {expected_type.__name__}")
    try:
        decoded = decode_typed_value(raw, max_nodes=max_nodes, max_depth=max_depth)
        if not isinstance(decoded, dict) or set(decoded) != {"schema", "kind", "payload"}:
            raise SemanticContractCodecError("semantic ingestion contract envelope is not closed")
        if decoded["schema"] != _CANONICAL_CONTRACT_ENVELOPE or decoded["kind"] != expected_kind:
            raise SemanticContractCodecError("legacy or mismatched semantic ingestion contract variant")
        return expected_type.model_validate(restore_closed_wire_enums(decoded["payload"]))
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SemanticContractCodecError):
            raise
        raise SemanticContractCodecError("semantic ingestion contract validation failed") from exc


def restore_closed_wire_enums(value: object) -> object:
    """Restore the one strict enum lowered by the generic CTV codec."""
    if isinstance(value, dict):
        return {
            key: SourceModality(item)
            if key == "modality" and isinstance(item, str)
            else ClaimValueType(item)
            if key == "object_literal_type" and isinstance(item, str)
            else ExtractionTriggerMode(item)
            if key == "trigger_mode" and isinstance(item, str)
            else restore_closed_wire_enums(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(restore_closed_wire_enums(item) for item in value)
    if isinstance(value, list):
        return [restore_closed_wire_enums(item) for item in value]
    return value


__all__ = [
    "AcceptedTemporalEvidence",
    "ActionRevision",
    "AnalyzerScopeInterpretation",
    "AnalyzerScopeObservation",
    "AnalyzerTemporalAttachment",
    "AnalyzerTemporalAttachmentObservation",
    "AnalyzerRoleInterpretation",
    "CanonicalRoleAssignment",
    "CandidateTransportError",
    "ClaimAssertion",
    "IdentityLineageRecord",
    "SemanticArtifactClosure",
    "SemanticDurableCarrier",
    "SemanticEventInputBatch",
    "SemanticGraphDelta",
    "SemanticEffectGroupResult",
    "SemanticObservationDelta",
    "OperationKind",
    "GroupPlanningAuthorization",
    "IngestionStage",
    "IngestionStageDependencySpec",
    "IngestionStageSpec",
    "IngestionExecutionGraph",
    "CANONICAL_INGESTION_EXECUTION_GRAPH",
    "IngestionStageInstanceRef",
    "IngestionStageOutcome",
    "OperationCapabilityExecutionBinding",
    "GraphDependentValidationAttempt",
    "IngestionExecutionManifest",
    "TransactionGroupPlanLineageEntry",
    "SourceTransactionPlanLineage",
    "PlanningArtifactReference",
    "TransactionSemanticGroupPlanReference",
    "SourceTransactionPlanLineageReference",
    "PrePlanningSourceIngestionProgress",
    "PlannedSourceIngestionProgress",
    "SourceIngestionProgress",
    "SegmentGovernanceBinding",
    "SegmentGovernanceCarrierSet",
    "RequiredOutcomeScopeSet",
    "MessageAdmissionIdentity",
    "MessageAdmissionCarrierSet",
    "GovernanceCarrierArtifact",
    "SourceDependencyGroup",
    "TransactionSemanticGroup",
    "LanguageCandidate",
    "SegmentLanguageResourceBinding",
    "SegmentLanguageRoute",
    "BootstrapDeclaredSegmentLanguageRoute",
    "SegmentLanguageRouteSet",
    "SourceSemanticContext",
    "SemanticProjectionSegment",
    "SourceSemanticTextProjection",
    "PreparedSegment",
    "PreparedSource",
    "TextPreparationPolicy",
    "TextPreparationRequest",
    "ActionProposalRoleContract",
    "ActionProposalStateContract",
    "ActionProposalCatalog",
    "PredicatePromptContract",
    "PredicateProposalCatalog",
    "RegisteredSemanticPromptBinding",
    "SemanticProposerManifest",
    "SemanticScopeConsensus",
    "StableSemanticScope",
    "TemporalAttachmentConsensus",
    "SourceLocalEntityClusterDecision",
    "SourceLocalIdentityClusterDecision",
    "SourcePrePartitionMention",
    "SourceLocalIdentityAssertion",
    "SourceLocalIdentityPartitionEvidence",
    "SourceLocalIdentityResolution",
    "OperationAlignment",
    "OperationTemporalAttachmentConsensusSet",
    "BootstrapAnalysisProvenanceV1",
    "BootstrapAnalysisRouteProjection",
    "BootstrapSegmentAnalysisInputV3",
    "BootstrapSemanticProposalRequestV3",
    "BootstrapLinguisticAnalysisRequestV3",
    "BootstrapPredicateEventDetectionRequestV3",
    "BootstrapTemporalResolutionRequestV3",
    "BootstrapAnalysisLaneResultV3",
    "BootstrapSemanticProposalRunV3",
    "BootstrapSourceNormalizationRequestV3",
    "BootstrapSourceNormalizationEvidenceManifestV3",
    "BootstrapSourceNormalizationResultV3",
    "BootstrapNormalizationRequestCoreV3",
    "BootstrapSemanticReductionAuthorityMemberV3",
    "BootstrapSemanticReductionAuthorityReloadV3",
    "BootstrapSourceNormalizationAtomicWriteRequestV3",
    "BootstrapV3PayloadLimitPolicy",
    "BootstrapV3PayloadLimitAuthority",
    "BootstrapProposalEvidenceItemV3",
    "BootstrapProposalMentionV3",
    "BootstrapProposalTypedLiteralV3",
    "BootstrapProposalEntityObjectV3",
    "BootstrapProposalLiteralObjectV3",
    "BootstrapProposalObjectV3",
    "BootstrapProposalFactV3",
    "BootstrapProposalCorrectionV3",
    "BootstrapProposalRetractionV3",
    "BootstrapProposalActionRoleParticipantV3",
    "BootstrapProposalActionRoleBindingV3",
    "BootstrapProposalActionStateV3",
    "BootstrapProposalClaimRecordSelectorV3",
    "BootstrapProposalActionRecordSelectorV3",
    "BootstrapProposalAliasRecordSelectorV3",
    "BootstrapProposalRecordSelectorV3",
    "BootstrapProposalReferenceAssignmentV3",
    "BootstrapProposalIdentityOperationV3",
    "BootstrapProposalOperationMemberV3",
    "BootstrapProposalTransportRequestV3",
    "BootstrapProposalAttemptV3",
    "BootstrapNormalizedProposalV3",
    "BootstrapProposalRunPayloadV3",
    "BootstrapStanzaLanePayloadV3",
    "BootstrapSpacyLanePayloadV3",
    "BootstrapAnalysisSourceEvidenceV3",
    "BootstrapPredicateEventCandidateV3",
    "BootstrapPredicateLanePayloadV3",
    "BootstrapTemporalReferenceV3",
    "BootstrapResolvedTemporalCandidateV3",
    "BootstrapTemporalAmbiguityMemberV3",
    "BootstrapTemporalAmbiguitySetV3",
    "BootstrapTemporalLanePayloadV3",
    "BootstrapAnalysisLanePayloadV3",
    "BootstrapPreAlignmentOperationSubjectV3",
    "BootstrapPreAlignmentOperationSubjectSetV3",
    "BootstrapOperationAlignmentV3",
    "BootstrapSourceDependencyGroupV3",
    "BootstrapGraphFreeInterpretationBundleV3",
    "BootstrapGraphFreeIdentityPlanningInputV3",
    "BootstrapOperationCoverageBindingV3",
    "BootstrapNativeOperationReductionInputV3",
    "BootstrapSourceProposalAlignmentV3",
    "BootstrapAnalysisRouteBinding",
    "BootstrapAnalysisRouteBindingSet",
    "BootstrapRecoveryKeyV3",
    "BootstrapRecoveryClaimV3",
    "BootstrapRecoveryProbeV3",
    "BootstrapRecoveryFoundV3",
    "BootstrapRecoveryClaimedV3",
    "BootstrapRecoveryUnavailableV3",
    "BootstrapRecoveryProbeResultV3",
    "BootstrapRecoveryRenewedV3",
    "BootstrapRecoveryAbortedV3",
    "BootstrapRecoveryRenewalResultV3",
    "GraphDependentExecutionPolicyReferenceV3",
    "GraphSemanticSnapshotBundleV3",
    "BootstrapRecoveryReplayRecordV3",
    "BootstrapGraphSnapshotAuthorityV3",
    "BootstrapGraphNormalizationAuthorityMemberV3",
    "BootstrapGraphNormalizationAuthorityReloadV3",
    "BootstrapGraphPreparedSourceTerminalAuthorityV3",
    "BootstrapGraphTransactionAuthorityProjectionV3",
    "BootstrapGraphAuthorityGenerationV3",
    "BootstrapGraphTransactionAuthorityWriteRequestV3",
    "BootstrapGraphAuthorityPublicationCoreV3",
    "BootstrapGraphAuthorityPublicationReceiptV3",
    "BootstrapGraphTransactionAuthorityReloadV3",
    "BootstrapGraphControlEpochV3",
    "BootstrapGraphControlEpochTransitionRequestV3",
    "BootstrapGraphControlEpochFoundV3",
    "BootstrapGraphControlEpochAdvancedV3",
    "BootstrapGraphControlEpochUnavailableV3",
    "BootstrapGraphControlEpochTransitionResultV3",
    "BootstrapGraphDependentCoordinatorRequestV3",
    "BootstrapReservationUseAuthorizationV3",
    "BootstrapNoReservationUseV3",
    "BootstrapIdentityReservationUseSetV3",
    "BootstrapReservationUseAuthorityV3",
    "BootstrapTransactionGroupOperationPlanV3",
    "BootstrapGraphTargetReferenceV3",
    "BootstrapSourceOperationMembershipV3",
    "BootstrapCanonicalClusterReferenceOccurrenceV3",
    "BootstrapCanonicalFirstUseConsumerV3",
    "BootstrapCanonicalFirstUseDependencyV3",
    "BootstrapCanonicalPlanningPrefixProofV3",
    "BootstrapCanonicalIdentityDecisionProofV3",
    "BootstrapExistingCanonicalIdentityDecisionV3",
    "BootstrapNewCanonicalIdentityAllocationV3",
    "BootstrapAbsentCanonicalIdentityDecisionV3",
    "BootstrapCanonicalIdentityClusterDecisionV3",
    "BootstrapCanonicalIdentityBindingAllocationAuthorityV3",
    "BootstrapCanonicalIdentityBindingAllocationReloadV3",
    "BootstrapCanonicalIdentityAuthorityWriteRequestV3",
    "BootstrapNativeMentionTargetCandidateV3",
    "BootstrapNativeSelectorTargetV3",
    "BootstrapNativeTargetResolutionAuthorityV3",
    "BootstrapNativeEntitySeedV3",
    "BootstrapNativeFactPlanningSeedV3",
    "BootstrapNativeCorrectionPlanningSeedV3",
    "BootstrapNativeRetractionPlanningSeedV3",
    "BootstrapNativeActionPlanningSeedV3",
    "BootstrapNativeIdentityPlanningSeedV3",
    "BootstrapNativeOperationPlanningSeedV3",
    "BootstrapNewFirstUseTargetAuthorityV3",
    "BootstrapNativeTargetPlanningRequestV3",
    "BootstrapSnapshotTargetAuthorityV3",
    "BootstrapPendingTargetAuthorityV3",
    "BootstrapNativeTargetAuthorityV3",
    "BootstrapNativeTargetBindingV3",
    "BootstrapNativePlanningRecordV3",
    "BootstrapNativeTemporalTerminalBindingV3",
    "BootstrapNativeEvidenceProjectionV3",
    "BootstrapNativeIdentityMaterializationV3",
    "BootstrapGraphTargetMaterializationPlanV3",
    "BootstrapNativePlanningUnavailableV3",
    "BootstrapNativeIdentityAdmissionRequestV3",
    "BootstrapNativeIdentityAdmissionV3",
    "BootstrapGraphTargetMaterializationPlannerV3",
    "BootstrapNativeIdentityAdmissionPortV3",
    "BootstrapNativeRecordMaterializationIntentV3",
    "BootstrapNativeFactEffectV3",
    "BootstrapNativeCorrectionEffectV3",
    "BootstrapNativeRetractionEffectV3",
    "BootstrapNativeActionStateEffectV3",
    "BootstrapNativeIdentityEffectV3",
    "BootstrapNativeAcceptedOperationEffectV3",
    "BootstrapNativeTerminalReasonV3",
    "SemanticSealedOperation",
    "BootstrapNativeOperationCompilationV3",
    "BootstrapNativeOperationEffectMaterializationV3",
    "BootstrapNativeOperationTerminalV3",
    "BootstrapNativeOperationArtifactClosureV3",
    "BootstrapGraphOperationReductionV3",
    "validate_bootstrap_native_operation_reduction_v3",
    "BootstrapGraphOperationStoreMaterializationInputV3",
    "BootstrapGraphOperationCommitResultV3",
    "BootstrapGraphGroupCommitResultCoreV3",
    "BootstrapGraphAtomicEffectReceiptV3",
    "BootstrapGraphGroupCommitResultV3",
    "BootstrapGraphGroupCommitRequestV3",
    "BootstrapGraphGroupCommitReloadV3",
    "BootstrapNativeGroupCommitTerminalConstructionV3",
    "BootstrapGraphObservationDeltaEffectV3",
    "BootstrapGraphDeltaEffectV3",
    "BootstrapGraphEventBatchEffectV3",
    "BootstrapGraphEffectNotApplicableV3",
    "BootstrapGraphGroupEffectCarrierV3",
    "BootstrapGraphGroupCasRequestV3",
    "BootstrapGraphGroupCasOutcomeV3",
    "BootstrapGraphGroupExecutionResultV3",
    "BootstrapGraphGroupResultConstructionV3",
    "BootstrapGraphCanonicalSourceResultV3",
    "BootstrapGraphCanonicalSourceResultInputV3",
    "BootstrapGraphTerminalPublicationRequestV3",
    "BootstrapGraphTerminalHostAuthorityV3",
    "BootstrapGraphTerminalPreparationV3",
    "BootstrapGraphFinalStageEvidenceV3",
    "BootstrapGraphTerminalHandoffCoreV3",
    "BootstrapGraphTerminalMemberIntentV3",
    "BootstrapGraphTerminalPublicationIntentV3",
    "BootstrapGraphPlanAtomicWriteIdentityV3",
    "BootstrapGraphTerminalControlV3",
    "BootstrapGraphTerminalPersistenceHandoffV3",
    "BootstrapGraphTerminalReloadV3",
    "BootstrapGraphPlanAtomicMemberKindV3",
    "BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS",
    "encode_bootstrap_graph_atomic_member_payload_v3",
    "decode_bootstrap_graph_atomic_member_payload_v3",
    "validate_bootstrap_graph_plan_atomic_members_v3",
    "BootstrapGraphPlanAtomicMemberV3",
    "BootstrapGraphCurrentGenerationV3",
    "BootstrapGraphCheckpointReceiptV3",
    "BootstrapGraphPlanAtomicWriteRequestV3",
    "BootstrapGraphPlanAtomicReloadCoreV3",
    "BootstrapGraphAttemptConstructionInputsV3",
    "BootstrapGraphPreExecutionManifestCoreV3",
    "BootstrapGraphPreExecutionManifestIdentityV3",
    "BootstrapGraphPreExecutionManifestIdentityClosureV3",
    "BootstrapGraphExecutionManifestConstructionV3",
    "BootstrapGraphPreExecutionGroupEvidenceV3",
    "BootstrapGraphPlanAtomicReloadV3",
    "TypedLiteral",
    "ConstructionFamily",
    "Commitment",
    "CheckResult",
    "UdPathStep",
    "UdPathPattern",
    "QuotationBoundaryPolicy",
    "SemanticScopePolicy",
    "UdRoleSchema",
    "PredicateSemanticPolicy",
    "RetainedSourceTextArtifact",
    "SemanticProjectionTextArtifact",
    "SegmentLocalTextArtifact",
    "RetainedSourceTextSpan",
    "ProjectionTextSpan",
    "SegmentLocalTextSpan",
    "VerbatimTextArtifactMappingProof",
    "EnvelopeFieldTextArtifactMappingProof",
    "TextArtifactMappingProof",
    "SourceSpanReference",
    "ProviderEntityObject",
    "ProviderLiteralObject",
    "ProviderObject",
    "ProviderMention",
    "ProviderFact",
    "ProviderCorrection",
    "ProviderRetraction",
    "ProviderSemanticProposal",
    "ProposedMention",
    "ProposedEntityObject",
    "ProposedLiteralObject",
    "ProposedObject",
    "ProposedFact",
    "ProposedCorrection",
    "ProposedRetraction",
    "ProposedActionRoleParticipant",
    "ProposedActionRoleBinding",
    "ProposedActionState",
    "ProposedClaimRecordSelector",
    "ProposedActionRecordSelector",
    "ProposedAliasRecordSelector",
    "ProposedRecordSelector",
    "ProposedReferenceAssignment",
    "ProposedIdentityOperation",
    "SemanticProposal",
    "SemanticProposalResponseArtifact",
    "SemanticProposalAttemptIdentity",
    "SemanticProposalAttempt",
    "SegmentProposalOutcome",
    "LinguisticFeature",
    "LinguisticToken",
    "DependencyArc",
    "SourceMention",
    "ClauseArgument",
    "ClauseQuotationEvidence",
    "ClauseAnalysis",
    "SegmentLanguageLaneOutcome",
    "LinguisticAnalysis",
    "PredicateEventCandidate",
    "PredicateEventInventory",
    "ResolvedTemporalCandidate",
    "TemporalResolution",
    "SegmentAnalysisInput",
    "AnalyzerManifest",
    "PredicateEventManifest",
    "TemporalResolverManifest",
    "LinguisticAnalysisRequest",
    "PredicateEventDetectionRequest",
    "TemporalResolutionRequest",
    "PreAlignmentSemanticOperationSubject",
    "PreAlignmentSemanticOperationSubjectSet",
    "ParserConsensusPolicy",
    "ScopeConsensusPolicy",
    "TemporalAttachmentConsensusPolicy",
    "ConsensusPolicy",
    "ConsensusPolicySelection",
    "FactOperationSemanticPolicyKey",
    "CorrectionOperationSemanticPolicyKey",
    "RetractionOperationSemanticPolicyKey",
    "ActionStateOperationSemanticPolicyKey",
    "IdentityOperationSemanticPolicyKey",
    "OperationSemanticPolicyKey",
    "PredicateSemanticPolicyBinding",
    "ParserOperationPolicyAuthority",
    "ScopeOperationPolicyAuthority",
    "LanguageConstructionPolicyAuthority",
    "LanguageConstructionPolicyAuthorityBundle",
    "expand_pre_alignment_subjects",
    "PlannedTransactionGroupExecution",
    "GroupIndependenceCertificate",
    "TransactionSemanticGroupPlan",
    "OperationTemporalAttachmentBinding",
    "OperationTemporalDecisionBinding",
    "ParserConsensusAssessment",
    "PredicateTemporalRule",
    "PredicateTrustRule",
    "SealedSemanticOperation",
    "SemanticCandidate",
    "SemanticContractCodecError",
    "SemanticCandidateAssessor",
    "SemanticPipelinePolicy",
    "SemanticPipelinePolicyProvider",
    "SemanticTerminalBindingSet",
    "SemanticTerminalOutcome",
    "SemanticTransport",
    "SourceAuthority",
    "SourceLocalIdentityEvidence",
    "SourceSpan",
    "TemporalEvidenceCandidate",
    "TemporalEvidenceDecisionClosure",
    "TemporalPolicySnapshot",
    "TemporalRole",
    "TemporalTransitionRecord",
    "TimeInterval",
    "TrustPolicySnapshot",
    "canonical_contract_value",
    "contract_digest",
    "rebuild_bootstrap_graph_effect_contracts",
    "decode_semantic_contract",
    "encode_semantic_contract",
]
