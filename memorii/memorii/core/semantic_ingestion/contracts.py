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
from typing import Annotated, ClassVar, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from memorii.core.memory_evolution.atomic_store import OperationLeaseBinding
from memorii.core.memory_evolution.graph_records import (
    GraphReadSet,
    GroundedMentionRef,
    NonOwningGraphRecord,
    SourceAuthority,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    OperationFenceBinding,
    decode_typed_value,
    encode_typed_value,
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
        return _CanonicalContractMap({
            name: canonical_contract_value(getattr(value, name))
            for name in type(value).model_fields
        })
    if isinstance(value, dict):
        return {key: canonical_contract_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(canonical_contract_value(item) for item in value)
    if isinstance(value, list):
        return [canonical_contract_value(item) for item in value]
    if isinstance(value, frozenset):
        return frozenset(canonical_contract_value(item) for item in value)
    return value


def contract_digest(domain: bytes, value: object) -> str:
    return sha256(domain + b"\0" + encode_typed_value(canonical_contract_value(value))).hexdigest()


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
        return cls(**values, context_digest=contract_digest(b"memorii.semantic-ingestion.source-semantic-context", body))


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
        body = {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name != "snapshot_digest"
        }
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
        body = {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name != "snapshot_digest"
        }
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
        body = {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name != "bundle_digest"
        }
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
        if self.parser_consensus.source_id != self.source_id or (
            self.parser_consensus.source_digest != self.source_digest
        ) or self.parser_consensus.primary_interpretation.predicate_head_span.source_id != self.source_id or (
            self.parser_consensus.corroborating_interpretation.predicate_head_span.source_id != self.source_id
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
    plan_lineage: SourceTransactionPlanLineage | None = None
    execution_manifest: IngestionExecutionManifest | None = None,
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
        body = {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name != "terminal_digest"
        }
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
        execution_manifest: IngestionExecutionManifest | None = None,
        plan_lineage: SourceTransactionPlanLineage | None = None
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
            "plan_lineage": plan_lineage,
            "execution_manifest": execution_manifest,
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


class SemanticExecutionRetryPlan(BaseModel):
    """Authenticated, secret-free inputs needed to resume before learned stages."""

    operation_id: str = Field(min_length=1)
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_utf8_bytes: bytes
    admitted_source_id: str = Field(min_length=1)
    admitted_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admitted_source_bytes_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admitted_source_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authenticated_ingress: AuthenticatedIngressContext
    prompt_reference: str = Field(min_length=1)
    policy_source_id: str = Field(min_length=1)
    policy_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_verification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_authorization_state: Literal["verified", "unavailable"]
    deployment_authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_active_epoch: int | None = Field(default=None, ge=1)
    deployment_decision_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    authorization_authority_scope_id: str = Field(min_length=1)
    authorization_authority_record_id: str = Field(min_length=1)
    expected_authority_revision: int = Field(ge=0)
    expected_authority_coordinates_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    authority_reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_secret_reference: str = Field(min_length=1)
    attempt_budget: int = Field(ge=1, le=10)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_plan(self) -> SemanticExecutionRetryPlan:
        if (
            self.admitted_source_id != self.source_id
            or self.admitted_source_digest != self.source_digest
            or self.admitted_source_bytes_digest != sha256(self.source_utf8_bytes).hexdigest()
        ):
            raise ValueError("semantic ingestion retry plan admitted source binding is invalid")
        admitted_source = {
            "operation_fence_binding_digest": self.operation_fence_binding_digest,
            "admitted_source_id": self.admitted_source_id,
            "admitted_source_digest": self.admitted_source_digest,
            "admitted_source_bytes_digest": self.admitted_source_bytes_digest,
        }
        if self.admitted_source_binding_digest != contract_digest(
            b"memorii.semantic-ingestion.admitted-source-binding.v1", admitted_source
        ):
            raise ValueError("semantic ingestion retry plan admitted source digest mismatch")
        if self.policy_source_id != self.source_id or self.policy_source_digest != self.source_digest:
            raise ValueError("semantic ingestion retry plan policy coordinates do not bind its source")
        if self.deployment_authorization_state == "verified":
            if self.deployment_active_epoch is None or self.deployment_decision_digest is None:
                raise ValueError("verified semantic ingestion retry plan lacks deployment coordinates")
        elif self.deployment_active_epoch is not None or self.deployment_decision_digest is not None:
            raise ValueError("unavailable semantic ingestion retry plan invents deployment coordinates")
        expected_record_id = (
            "semantic_ingestion:authorization:"
            + sha256(self.authorization_authority_scope_id.encode("utf-8")).hexdigest()
        )
        if self.authorization_authority_record_id != expected_record_id:
            raise ValueError("semantic ingestion retry plan authority record does not bind its scope")
        reference = {
            "authorization_authority_scope_id": self.authorization_authority_scope_id,
            "authorization_authority_record_id": self.authorization_authority_record_id,
            "expected_authority_revision": self.expected_authority_revision,
            "expected_authority_coordinates_digest": self.expected_authority_coordinates_digest,
        }
        if self.authority_reference_digest != contract_digest(
            b"memorii.semantic-ingestion.authorization-authority-reference.v1", reference
        ):
            raise ValueError("semantic ingestion retry plan authority reference digest mismatch")
        body = self.model_dump(mode="python", exclude={"plan_digest"})
        if self.plan_digest != contract_digest(b"memorii.semantic-ingestion.execution-retry-plan.v1", body):
            raise ValueError("semantic ingestion execution retry plan digest mismatch")
        return self

    def validate_for_fence(self, fence: OperationFenceBinding) -> None:
        """Reject a foreign operation, principal, allocation, or source fence."""
        if (
            self.operation_id != fence.operation_id
            or self.operation_fence_binding_digest != fence.binding_digest
            or self.authenticated_ingress.delivery_principal_binding.binding_digest
            != fence.delivery_principal_binding_digest
            or self.admitted_source_id != fence.source_id
            or self.admitted_source_digest != fence.source_digest
            or self.source_id != fence.source_id
            or self.source_digest != fence.source_digest
        ):
            raise ValueError("semantic ingestion execution retry plan fence/source binding is invalid")

    @classmethod
    def create(cls, **values: object) -> SemanticExecutionRetryPlan:
        scope_id = values["authorization_authority_scope_id"]
        if not isinstance(scope_id, str):
            raise TypeError("authorization authority scope must be a string")
        values = {
            **values,
            "authorization_authority_record_id": (
                "semantic_ingestion:authorization:" + sha256(scope_id.encode("utf-8")).hexdigest()
            ),
        }
        reference = {
            key: values.get(key)
            for key in (
                "authorization_authority_scope_id",
                "authorization_authority_record_id",
                "expected_authority_revision",
                "expected_authority_coordinates_digest",
            )
        }
        values["authority_reference_digest"] = contract_digest(
            b"memorii.semantic-ingestion.authorization-authority-reference.v1", reference
        )
        source_id = values.get("source_id")
        source_digest = values.get("source_digest")
        source_bytes = values.get("source_utf8_bytes")
        fence_digest = values.get("operation_fence_binding_digest")
        if (
            not isinstance(source_id, str)
            or not isinstance(source_digest, str)
            or not isinstance(source_bytes, bytes)
            or not isinstance(fence_digest, str)
        ):
            raise TypeError("semantic ingestion retry plan source/fence inputs are invalid")
        admitted_source = {
            "operation_fence_binding_digest": fence_digest,
            "admitted_source_id": source_id,
            "admitted_source_digest": source_digest,
            "admitted_source_bytes_digest": sha256(source_bytes).hexdigest(),
        }
        values.update(admitted_source)
        values["admitted_source_binding_digest"] = contract_digest(
            b"memorii.semantic-ingestion.admitted-source-binding.v1", admitted_source
        )
        return cls(
            **values,
            plan_digest=contract_digest(b"memorii.semantic-ingestion.execution-retry-plan.v1", values),
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
        if not self.carriers or self.delta_digest != contract_digest(
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
            "terminal_binding_sets": terminal.terminal_binding_sets,
        }
        return cls(**body, delta_digest=contract_digest(b"memorii.semantic-ingestion.graph-delta.v1", body))


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
        return cls(**body, group_result_digest=contract_digest(b"memorii.semantic-ingestion.group-result.v1", body))


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
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != contract_digest(b"memorii.semantic-ingestion.segment-governance-binding.v1", body):
            raise ValueError("segment governance binding digest mismatch")
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
        body = self.model_dump(mode="python", exclude={"carrier_set_digest"})
        if self.carrier_set_digest != contract_digest(
            b"memorii.semantic-ingestion.segment-governance-carrier-set.v1", body
        ):
            raise ValueError("segment governance carrier set digest mismatch")
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
        body = self.model_dump(mode="python", exclude={"message_admission_key_digest"})
        if self.message_admission_key_digest != contract_digest(
            b"memorii.semantic-ingestion.message-admission-identity.v1", body
        ):
            raise ValueError("message admission identity digest mismatch")
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
        if not self.identities or self.identities != _canonical_values(self.identities):
            raise ValueError("message admission identities must be nonempty and canonical")
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
        if tuple(sorted(binding_digests)) != tuple(sorted(admission_binding_digests)):
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
                normalized.append(part.title() if len(part) == 4 and part.isalpha() else part.upper() if len(part) == 2 and part.isalpha() or len(part) == 3 and part.isdigit() else part.lower())
            return "-".join(normalized)

        candidates = self.candidates
        if any(candidate.language != canonical_tag(candidate.language) for candidate in candidates):
            raise ValueError("segment language candidates must use canonical BCP-47 tags")
        if self.declared_language is not None and self.declared_language != canonical_tag(self.declared_language):
            raise ValueError("declared language must use canonical BCP-47 tag")
        if candidates != tuple(sorted(candidates, key=lambda candidate: (-candidate.probability_ppm, candidate.language))) or len(
            {candidate.language for candidate in self.candidates}
        ) != len(self.candidates):
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
                or self.declared_language is not None and self.declared_language != self.selected_language
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


class SegmentLanguageRouteSet(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    routes: tuple[SegmentLanguageRoute, ...]
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


class SourceLocalEntityClusterDecision(BaseModel):
    cluster_id: str = Field(min_length=1)
    mention_refs: tuple[GroundedMentionRef, ...]
    decision: Literal["same_source_entity", "singleton_distinct", "unresolved"]
    proof_kind: Literal[
        "explicit_alias",
        "explicit_apposition",
        "authenticated_external_id",
        "certified_unambiguous_repetition",
        "insufficient_evidence",
        "conflicting_evidence",
    ]
    source_evidence: tuple[SourceSpan, ...]
    language_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason_codes: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_cluster(self) -> SourceLocalEntityClusterDecision:
        if not self.mention_refs or self.mention_refs != tuple(
            sorted(
                self.mention_refs,
                key=lambda mention: (mention.source_id, mention.start, mention.end, mention.cluster_id),
            )
        ):
            raise ValueError("source local identity cluster mentions must be nonempty and canonical")
        if self.decision == "unresolved" and self.proof_kind not in {"insufficient_evidence", "conflicting_evidence"}:
            raise ValueError("unresolved source local identity cluster requires unresolved proof")
        if self.decision != "unresolved" and self.proof_kind in {"insufficient_evidence", "conflicting_evidence"}:
            raise ValueError("resolved source local identity cluster requires affirmative proof")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))) or any(not code for code in self.reason_codes):
            raise ValueError("source local identity cluster reason codes must be canonical")
        return self


class SourceLocalIdentityResolution(BaseModel):
    source_id: str = Field(min_length=1)
    grounded_mention_refs: tuple[GroundedMentionRef, ...]
    clusters: tuple[SourceLocalEntityClusterDecision, ...]
    unresolved_mention_refs: tuple[GroundedMentionRef, ...]
    language_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_resolution(self) -> SourceLocalIdentityResolution:
        mentions = self.grounded_mention_refs
        if (
            mentions != tuple(sorted(mentions, key=lambda mention: (mention.start, mention.end, mention.cluster_id)))
            or len(set(mentions)) != len(mentions)
            or any(mention.source_id != self.source_id for mention in mentions)
        ):
            raise ValueError("source local identity mentions must be source-local and canonical")
        if self.clusters != tuple(sorted(self.clusters, key=lambda cluster: cluster.cluster_id)) or len(
            {cluster.cluster_id for cluster in self.clusters}
        ) != len(self.clusters):
            raise ValueError("source local identity clusters must be canonical")
        clustered = tuple(mention for cluster in self.clusters for mention in cluster.mention_refs)
        if set(clustered) != set(mentions) or len(clustered) != len(set(clustered)):
            raise ValueError("source local identity clusters must be a total partition")
        unresolved = tuple(
            mention for cluster in self.clusters if cluster.decision == "unresolved" for mention in cluster.mention_refs
        )
        if self.unresolved_mention_refs != tuple(
            sorted(unresolved, key=lambda mention: (mention.start, mention.end, mention.cluster_id))
        ):
            raise ValueError("source local identity unresolved mentions must equal unresolved clusters")
        body = self.model_dump(mode="python", exclude={"resolution_digest"})
        if self.resolution_digest != contract_digest(
            b"memorii.semantic-ingestion.source-local-identity-resolution.v1", body
        ):
            raise ValueError("source local identity resolution digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SourceLocalIdentityResolution:
        return cls(
            **values,
            resolution_digest=contract_digest(
                b"memorii.semantic-ingestion.source-local-identity-resolution.v1", values
            ),
        )


class CoveredPredicateEvent(BaseModel):
    kind: Literal["covered"] = "covered"
    event_id: str = Field(min_length=1)
    proposal_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    alignment_digests: tuple[str, ...]
    disposition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_disposition(self) -> CoveredPredicateEvent:
        for values, label in (
            (self.proposal_ids, "proposal ids"),
            (self.operation_ids, "operation ids"),
            (self.alignment_digests, "alignment digests"),
        ):
            if not values or values != tuple(sorted(set(values))) or any(not value for value in values):
                raise ValueError(f"covered predicate event {label} must be nonempty and canonical")
        body = self.model_dump(mode="python", exclude={"disposition_digest"})
        if self.disposition_digest != contract_digest(b"memorii.semantic-ingestion.covered-predicate-event.v1", body):
            raise ValueError("covered predicate event digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> CoveredPredicateEvent:
        body = {"kind": "covered", **values}
        return cls(
            **body,
            disposition_digest=contract_digest(b"memorii.semantic-ingestion.covered-predicate-event.v1", body),
        )


class UnresolvedPredicateEvent(BaseModel):
    kind: Literal["unresolved"] = "unresolved"
    event_id: str = Field(min_length=1)
    reason: Literal[
        "proposal_omitted",
        "proposal_abstained",
        "alignment_failed",
        "parser_disagreement",
        "scope_disagreement",
        "temporal_attachment_disagreement",
        "unsupported_construction",
    ]
    related_proposal_ids: tuple[str, ...]
    evidence_spans: tuple[SourceSpan, ...]
    disposition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_disposition(self) -> UnresolvedPredicateEvent:
        if self.related_proposal_ids != tuple(sorted(set(self.related_proposal_ids))) or any(
            not value for value in self.related_proposal_ids
        ):
            raise ValueError("unresolved predicate event proposal ids must be canonical")
        if self.evidence_spans != _canonical_values(self.evidence_spans) or len(set(self.evidence_spans)) != len(
            self.evidence_spans
        ):
            raise ValueError("unresolved predicate event evidence spans must be canonical")
        body = self.model_dump(mode="python", exclude={"disposition_digest"})
        if self.disposition_digest != contract_digest(b"memorii.semantic-ingestion.unresolved-predicate-event.v1", body):
            raise ValueError("unresolved predicate event digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> UnresolvedPredicateEvent:
        body = {"kind": "unresolved", **values}
        return cls(
            **body,
            disposition_digest=contract_digest(b"memorii.semantic-ingestion.unresolved-predicate-event.v1", body),
        )


PredicateEventDisposition = Annotated[CoveredPredicateEvent | UnresolvedPredicateEvent, Field(discriminator="kind")]


class ProposalCoverageAudit(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_routes: SegmentLanguageRouteSet
    proposal_run_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_inventory_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_event_ids: tuple[str, ...]
    dispositions: tuple[PredicateEventDisposition, ...]
    covered_event_ids: tuple[str, ...]
    unresolved_event_ids: tuple[str, ...]
    status: Literal["complete", "unresolved", "failed"]
    coverage_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_audit(self) -> ProposalCoverageAudit:
        if (
            self.source_id != self.segment_language_routes.source_id
            or self.source_digest != self.segment_language_routes.source_digest
        ):
            raise ValueError("proposal coverage route source mismatch")
        if not self.predicate_event_ids or self.predicate_event_ids != tuple(sorted(set(self.predicate_event_ids))) or any(
            not event_id for event_id in self.predicate_event_ids
        ):
            raise ValueError("predicate event inventory membership must be nonempty and canonical")
        ids = tuple(disposition.event_id for disposition in self.dispositions)
        if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids) or ids != self.predicate_event_ids:
            raise ValueError("proposal coverage dispositions must be canonical")
        covered = tuple(disposition.event_id for disposition in self.dispositions if disposition.kind == "covered")
        unresolved = tuple(
            disposition.event_id for disposition in self.dispositions if disposition.kind == "unresolved"
        )
        if self.covered_event_ids != covered or self.unresolved_event_ids != unresolved:
            raise ValueError("proposal coverage event ids must exactly cover dispositions")
        expected_status = "failed" if not self.dispositions else "unresolved" if unresolved else "complete"
        if self.status != expected_status:
            raise ValueError("proposal coverage status must match dispositions")
        body = self.model_dump(mode="python", exclude={"audit_digest"})
        if self.audit_digest != contract_digest(b"memorii.semantic-ingestion.proposal-coverage-audit.v1", body):
            raise ValueError("proposal coverage audit digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> ProposalCoverageAudit:
        return cls(
            **values, audit_digest=contract_digest(b"memorii.semantic-ingestion.proposal-coverage-audit.v1", values)
        )


class OperationAlignment(BaseModel):
    operation_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_attachment_consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    alignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_alignment(self) -> OperationAlignment:
        body = self.model_dump(mode="python", exclude={"alignment_digest"})
        if self.alignment_digest != contract_digest(b"memorii.semantic-ingestion.operation-alignment.v1", body):
            raise ValueError("operation alignment digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> OperationAlignment:
        return cls(
            **values, alignment_digest=contract_digest(b"memorii.semantic-ingestion.operation-alignment.v1", values)
        )


class SourceDependencyGroup(BaseModel):
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
        if self.group_id != contract_digest(b"memorii.semantic-ingestion.source-dependency-group.v1", body):
            raise ValueError("source dependency group id mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SourceDependencyGroup:
        return cls(**values, group_id=contract_digest(b"memorii.semantic-ingestion.source-dependency-group.v1", values))


class SourceProposalAlignment(BaseModel):
    source_id: str = Field(min_length=1)
    segment_language_routes: SegmentLanguageRouteSet
    operation_alignments: tuple[OperationAlignment, ...]
    parser_consensus: tuple[ParserConsensusAssessment, ...]
    scope_consensus: tuple[SemanticScopeConsensus, ...]
    temporal_attachment_consensus: tuple[TemporalAttachmentConsensus, ...]
    source_local_identity: SourceLocalIdentityResolution
    source_dependency_groups: tuple[SourceDependencyGroup, ...]
    proposal_coverage: ProposalCoverageAudit
    predicate_event_inventory_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_resolution_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["complete", "unsupported", "failed"]
    reason_codes: tuple[str, ...]
    source_alignment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_alignment(self) -> SourceProposalAlignment:
        routes = self.segment_language_routes
        if self.source_id != routes.source_id or self.source_local_identity.source_id != self.source_id:
            raise ValueError("source proposal alignment source mismatch")
        if (
            self.proposal_coverage.segment_language_routes != routes
            or self.proposal_coverage.source_id != self.source_id
        ):
            raise ValueError("source proposal alignment coverage mismatch")
        if self.predicate_event_inventory_fingerprint != self.proposal_coverage.predicate_event_inventory_fingerprint:
            raise ValueError("source proposal alignment predicate inventory fingerprint mismatch")
        if self.operation_alignments != tuple(
            sorted(self.operation_alignments, key=lambda alignment: alignment.operation_id)
        ) or len({alignment.operation_id for alignment in self.operation_alignments}) != len(self.operation_alignments):
            raise ValueError("source proposal operation alignments must be canonical")
        route_by_segment = {route.segment_id: route.route_digest for route in routes.routes}
        parser_by_digest = {item.assessment_digest: item for item in self.parser_consensus}
        scope_by_digest = {item.consensus_digest: item for item in self.scope_consensus}
        temporal_by_digest = {item.consensus_digest: item for item in self.temporal_attachment_consensus}
        if (
            self.parser_consensus != tuple(sorted(self.parser_consensus, key=lambda item: item.operation_id))
            or self.scope_consensus != tuple(sorted(self.scope_consensus, key=lambda item: item.operation_id))
            or self.temporal_attachment_consensus
            != tuple(sorted(self.temporal_attachment_consensus, key=lambda item: item.operation_id))
            or len({item.operation_id for item in self.parser_consensus}) != len(self.parser_consensus)
            or len({item.operation_id for item in self.scope_consensus}) != len(self.scope_consensus)
            or len({item.operation_id for item in self.temporal_attachment_consensus})
            != len(self.temporal_attachment_consensus)
            or len(parser_by_digest) != len(self.parser_consensus)
            or len(scope_by_digest) != len(self.scope_consensus)
            or len(temporal_by_digest) != len(self.temporal_attachment_consensus)
        ):
            raise ValueError("source proposal consensus digests must be unique")
        for alignment in self.operation_alignments:
            if route_by_segment.get(alignment.segment_id) != alignment.segment_language_route_digest:
                raise ValueError("operation alignment route mismatch")
            route = next(route for route in routes.routes if route.segment_id == alignment.segment_id)
            parser = parser_by_digest.get(alignment.parser_consensus_digest)
            if parser is None:
                raise ValueError("operation alignment parser consensus is absent")
            scope = scope_by_digest.get(alignment.scope_consensus_digest)
            temporal = temporal_by_digest.get(alignment.temporal_attachment_consensus_digest)
            if (
                parser.source_id != self.source_id
                or parser.source_digest != routes.source_digest
                or parser.segment_id != alignment.segment_id
                or parser.proposal_id != alignment.proposal_id
                or parser.operation_id != alignment.operation_id
                or parser.segment_language_route_digest != alignment.segment_language_route_digest
                or scope is None
                or temporal is None
                or scope.source_id != self.source_id
                or scope.source_digest != routes.source_digest
                or temporal.source_id != self.source_id
                or temporal.source_digest != routes.source_digest
                or scope.segment_id != alignment.segment_id
                or temporal.segment_id != alignment.segment_id
                or scope.proposal_id != alignment.proposal_id
                or temporal.proposal_id != alignment.proposal_id
                or scope.operation_id != alignment.operation_id
                or temporal.operation_id != alignment.operation_id
                or scope.segment_language_route_digest != alignment.segment_language_route_digest
                or temporal.segment_language_route_digest != alignment.segment_language_route_digest
                or parser.preparation_fingerprint != scope.preparation_fingerprint
                or parser.preparation_fingerprint != temporal.preparation_fingerprint
            ):
                raise ValueError("operation alignment consensus mismatch")
            parser_spans = tuple(
                span
                for interpretation in (parser.primary_interpretation, parser.corroborating_interpretation)
                for span in (interpretation.predicate_head_span, *(item.argument_span for item in interpretation.assignments))
            )
            scope_spans = tuple(
                span
                for interpretation in (scope.primary_interpretation, scope.corroborating_interpretation)
                for span in (
                    interpretation.predicate_head_span,
                    *interpretation.governing_clause_spans,
                    *((interpretation.attribution_bearer_span,) if interpretation.attribution_bearer_span is not None else ()),
                    *(item for check in (interpretation.polarity, interpretation.commitment, interpretation.attribution) for item in check.evidence_spans),
                )
            ) + tuple(
                span
                for stable in (scope.stable_scope,)
                if stable is not None
                for span in (*stable.governing_clause_spans, *((stable.attribution_bearer_span,) if stable.attribution_bearer_span is not None else ()))
            )
            temporal_spans = tuple(
                span
                for attachment in (temporal.primary_attachment, temporal.corroborating_attachment)
                for span in (attachment.predicate_head_span, *attachment.attachment_spans)
            )
            try:
                for span in (*parser_spans, *scope_spans, *temporal_spans):
                    _validate_route_span(span, route, self.source_id)
            except ValueError as exc:
                raise ValueError("operation alignment consensus span closure mismatch") from exc
        alignment_by_digest = {alignment.alignment_digest: alignment for alignment in self.operation_alignments}
        for disposition in self.proposal_coverage.dispositions:
            if disposition.kind != "covered":
                continue
            referenced = tuple(alignment_by_digest.get(digest) for digest in disposition.alignment_digests)
            if any(item is None for item in referenced):
                raise ValueError("covered predicate event references an unknown operation alignment")
            assert all(item is not None for item in referenced)
            if (
                tuple(sorted(item.proposal_id for item in referenced)) != disposition.proposal_ids
                or tuple(sorted(item.operation_id for item in referenced)) != disposition.operation_ids
            ):
                raise ValueError("covered predicate event references must exactly match operation alignments")
        if self.source_dependency_groups != tuple(
            sorted(self.source_dependency_groups, key=lambda group: group.group_id)
        ):
            raise ValueError("source proposal dependency groups must be canonical")
        grouped_operations = tuple(
            operation_id for group in self.source_dependency_groups for operation_id in group.operation_ids
        )
        operation_ids = tuple(alignment.operation_id for alignment in self.operation_alignments)
        if tuple(sorted(grouped_operations)) != operation_ids or len(grouped_operations) != len(
            set(grouped_operations)
        ):
            raise ValueError("source proposal dependency groups must exactly cover operations")
        if any(not set(group.segment_ids).issubset(route_by_segment) for group in self.source_dependency_groups):
            raise ValueError("source proposal dependency group segment is absent")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))) or any(not code for code in self.reason_codes):
            raise ValueError("source proposal alignment reason codes must be canonical")
        all_complete = self.proposal_coverage.status == "complete" and all(
            group.status == "complete" for group in self.source_dependency_groups
        )
        expected_status = (
            "complete"
            if all_complete and not self.reason_codes
            else "failed"
            if self.proposal_coverage.status == "failed"
            else "unsupported"
        )
        if self.status != expected_status:
            raise ValueError("source proposal alignment status is not reproducible")
        return self


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
        if self.operation_carrier_memberships != _canonical_values(self.operation_carrier_memberships) or tuple(
            membership.operation_id for membership in self.operation_carrier_memberships
        ) != self.operation_ids:
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
        group_admission_digests = tuple(identity.message_admission_key_digest for identity in self.message_admission_identities)
        if not set(group_binding_digests).issubset(artifact_bindings) or not set(group_admission_digests).issubset(artifact_admissions):
            raise ValueError("transaction semantic group carriers must belong to its artifact")
        membership_bindings = tuple(
            digest for membership in self.operation_carrier_memberships for digest in membership.segment_governance_binding_digests
        )
        membership_admissions = tuple(
            digest for membership in self.operation_carrier_memberships for digest in membership.message_admission_key_digests
        )
        if tuple(sorted(set(membership_bindings))) != group_binding_digests or tuple(
            sorted(set(membership_admissions))
        ) != group_admission_digests:
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
    "source_ingestion", "source_governance", "text_preparation", "language_routing",
    "provider_egress_authorization", "llm_proposal", "proposal_validation", "proposal_run_sealing",
    "primary_linguistic_analysis", "corroborating_linguistic_analysis", "linguistic_consensus",
    "semantic_scope_consensus", "temporal_attachment_consensus", "predicate_event_detection",
    "temporal_resolution", "source_proposal_alignment", "proposal_coverage", "semantic_scope",
    "source_local_identity", "capability_selection", "canonical_identity_resolution",
    "planned_identity_reservation", "graph_proposal_alignment", "capability_status_binding_validation",
    "type_evidence_resolution", "claim_slot_construction", "nli_corroboration",
    "semantic_reconciliation", "transaction_group_expansion", "graph_compilation",
    "temporal_projection", "trust_arbitration", "reference_closure", "identity_lineage",
    "source_trace_persistence", "transaction_group_persistence", "source_summary_persistence",
]
IngestionStageScope = Literal["source", "segment", "source_plan_attempt", "transaction_group_attempt", "transaction_group"]


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


_INGESTION_STAGE_TEMPLATE: tuple[tuple[IngestionStage, IngestionStageScope, tuple[tuple[IngestionStage, str], ...]], ...] = (
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
    ("linguistic_consensus", "segment", (("primary_linguistic_analysis", "required"), ("corroborating_linguistic_analysis", "required"))),
    ("semantic_scope_consensus", "segment", (("linguistic_consensus", "required"),)),
    ("temporal_attachment_consensus", "segment", (("linguistic_consensus", "required"),)),
    ("predicate_event_detection", "segment", (("language_routing", "required"),)),
    ("temporal_resolution", "segment", (("language_routing", "required"),)),
    ("source_proposal_alignment", "source", (("proposal_run_sealing", "required"), ("linguistic_consensus", "required"), ("predicate_event_detection", "required"), ("temporal_resolution", "required"))),
    ("proposal_coverage", "source", (("source_proposal_alignment", "required"),)),
    ("semantic_scope", "segment", (("semantic_scope_consensus", "required"),)),
    ("source_local_identity", "source", (("source_proposal_alignment", "required"),)),
    ("capability_selection", "source_plan_attempt", (("source_proposal_alignment", "required"),)),
    ("nli_corroboration", "source_plan_attempt", (("capability_selection", "capability_conditional"),)),
    ("graph_proposal_alignment", "source_plan_attempt", (("source_proposal_alignment", "required"), ("capability_selection", "required"))),
    ("canonical_identity_resolution", "source_plan_attempt", (("graph_proposal_alignment", "required"),)),
    ("planned_identity_reservation", "source_plan_attempt", (("canonical_identity_resolution", "required"),)),
    ("capability_status_binding_validation", "source_plan_attempt", (("capability_selection", "required"),)),
    ("type_evidence_resolution", "source_plan_attempt", (("canonical_identity_resolution", "required"),)),
    ("claim_slot_construction", "source_plan_attempt", (("type_evidence_resolution", "required"),)),
    ("semantic_reconciliation", "source_plan_attempt", (("claim_slot_construction", "required"), ("nli_corroboration", "capability_conditional"))),
    ("reference_closure", "source_plan_attempt", (("semantic_reconciliation", "required"), ("planned_identity_reservation", "required"))),
    ("transaction_group_expansion", "source_plan_attempt", (("reference_closure", "required"),)),
    ("graph_compilation", "transaction_group", (("transaction_group_expansion", "required"),)),
    ("temporal_projection", "transaction_group", (("graph_compilation", "required"),)),
    ("trust_arbitration", "transaction_group", (("temporal_projection", "required"),)),
    ("identity_lineage", "transaction_group", (("trust_arbitration", "required"),)),
    ("transaction_group_persistence", "transaction_group", (("identity_lineage", "required"),)),
    ("source_trace_persistence", "source", (("source_proposal_alignment", "diagnostic"),)),
    ("source_summary_persistence", "source", (("transaction_group_persistence", "required"),)),
)


_ATTEMPT_SHARED_STAGES: frozenset[IngestionStage] = frozenset({
    "graph_proposal_alignment", "canonical_identity_resolution", "planned_identity_reservation",
    "capability_status_binding_validation", "type_evidence_resolution", "claim_slot_construction",
    "semantic_reconciliation", "reference_closure",
})


def _ingestion_stage_specs() -> tuple[IngestionStageSpec, ...]:
    return tuple(
        IngestionStageSpec(
            stage=stage,
            allowed_scopes=frozenset((scope, "transaction_group_attempt")) if stage in _ATTEMPT_SHARED_STAGES else frozenset((scope,)),
            dependencies=_canonical_values(tuple(
                IngestionStageDependencySpec(stage=dependency, mode=mode) for dependency, mode in dependencies
            )),
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
        expected_scope = next(spec.allowed_scopes for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages if spec.stage == self.stage)
        if self.scope not in expected_scope:
            raise ValueError("ingestion stage instance uses an invalid scope")
        values = (self.segment_id, self.segment_language_route_digest, self.transaction_group_id, self.attempt_id)
        required = {
            "source": (False, False, False, False), "segment": (True, True, False, False),
            "source_plan_attempt": (False, False, False, True), "transaction_group_attempt": (False, False, True, True),
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
        if self.blocking_stages != _canonical_values(self.blocking_stages) or len(set(self.blocking_stages)) != len(self.blocking_stages):
            raise ValueError("stage outcome blockers must be canonical and unique")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))) or any(not code for code in self.reason_codes):
            raise ValueError("stage outcome reason codes must be canonical and nonempty")
        if self.status == "not_started":
            if self.started_at is not None or self.completed_at is not None or self.artifact_digest is not None or self.reason_codes:
                raise ValueError("not-started stage outcomes cannot have completion data")
        else:
            if self.started_at is None or self.completed_at is None or self.started_at > self.completed_at or self.blocking_stages:
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
        if self.binding_digest != contract_digest(b"memorii.semantic-ingestion.operation-capability-execution-binding.v1", body):
            raise ValueError("operation capability execution binding digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> OperationCapabilityExecutionBinding:
        return cls(
            **values,
            binding_digest=contract_digest(b"memorii.semantic-ingestion.operation-capability-execution-binding.v1", values),
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
        if self.segment_governance_bindings != _canonical_values(self.segment_governance_bindings) or self.message_admission_identities != _canonical_values(self.message_admission_identities):
            raise ValueError("graph validation attempt carrier bindings must be canonical")
        if tuple(binding.binding_digest for binding in self.segment_governance_bindings) != tuple(binding.binding_digest for binding in self.governance_carrier_artifact.segment_governance.bindings):
            raise ValueError("graph validation attempt governance bindings must equal governance artifact")
        if tuple(identity.message_admission_key_digest for identity in self.message_admission_identities) != tuple(identity.message_admission_key_digest for identity in self.governance_carrier_artifact.message_admissions.identities):
            raise ValueError("graph validation attempt admission identities must equal governance artifact")
        for values in (self.planned_identity_reservation_digests, self.planned_action_reservation_digests, self.reservation_use_authorization_digests, self.capability_selection_digests, self.capability_binding_digests, self.canonical_entity_decision_digests):
            if values != tuple(sorted(set(values))) or any(len(value) != 64 for value in values):
                raise ValueError("graph validation attempt digest tuples must be canonical")
        authorizations = self.planning_authorizations
        if not authorizations or authorizations != _canonical_values(authorizations) or len({item.transaction_group_id for item in authorizations}) != len(authorizations):
            raise ValueError("graph validation attempt planning authorizations must be complete and canonical")
        if any(item.group_plan != self.transaction_group_plan for item in authorizations):
            raise ValueError("graph validation attempt authorization plan mismatch")
        if not is_initial and tuple(item.transaction_group_id for item in authorizations) != (self.transaction_group_id,):
            raise ValueError("transaction-group attempt must carry exactly its group authorization")
        expected_scopes = {"source_plan_attempt"} if is_initial else {"transaction_group_attempt"}
        if not self.stage_outcomes or any(outcome.instance.scope not in expected_scopes or outcome.instance.attempt_id != self.attempt_id or outcome.instance.transaction_group_id != self.transaction_group_id for outcome in self.stage_outcomes):
            raise ValueError("graph validation attempt stage outcomes have invalid scope coordinates")
        if self.stage_outcomes != _canonical_values(self.stage_outcomes) or len({outcome.instance for outcome in self.stage_outcomes}) != len(self.stage_outcomes):
            raise ValueError("graph validation attempt stage outcomes must be canonical and unique")
        expected_stages = {
            spec.stage
            for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages
            if self.scope in spec.allowed_scopes
        }
        if {outcome.instance.stage for outcome in self.stage_outcomes} != expected_stages:
            raise ValueError("graph validation attempt must retain every applicable stage outcome")
        body = self.model_dump(mode="python", exclude={"attempt_digest"})
        if self.attempt_digest != contract_digest(b"memorii.semantic-ingestion.graph-dependent-validation-attempt.v1", body):
            raise ValueError("graph validation attempt digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> GraphDependentValidationAttempt:
        return cls(**values, attempt_digest=contract_digest(b"memorii.semantic-ingestion.graph-dependent-validation-attempt.v1", values))

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
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_manifest(self) -> IngestionExecutionManifest:
        if self.execution_graph_fingerprint != CANONICAL_INGESTION_EXECUTION_GRAPH.graph_fingerprint:
            raise ValueError("execution manifest graph fingerprint is not canonical")
        source_id = self.segment_language_routes.source_id
        if self.segment_governance_carriers.source_id != source_id or self.message_admission_carriers.source_id != source_id:
            raise ValueError("execution manifest carrier source mismatch")
        artifact = self.governance_carrier_artifact
        if artifact.segment_governance != self.segment_governance_carriers or artifact.message_admissions != self.message_admission_carriers:
            raise ValueError("execution manifest carriers must equal governance artifact")
        route_digests = {route.route_digest for route in self.segment_language_routes.routes}
        if self.capability_bindings != _canonical_values(self.capability_bindings) or len({binding.operation_id for binding in self.capability_bindings}) != len(self.capability_bindings):
            raise ValueError("execution manifest capability bindings must be canonical and unique")
        if any(binding.segment_language_route_digest not in route_digests for binding in self.capability_bindings):
            raise ValueError("execution manifest capability binding route is unknown")
        if self.source_outcomes != _canonical_values(self.source_outcomes) or any(outcome.instance.scope not in {"source", "segment"} for outcome in self.source_outcomes):
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
        if {outcome.instance for outcome in self.source_outcomes} != expected_source_instances | expected_segment_instances:
            raise ValueError("execution manifest must retain every source and segment stage outcome")
        if self.graph_validation_attempts != _canonical_values(self.graph_validation_attempts) or len({attempt.attempt_id for attempt in self.graph_validation_attempts}) != len(self.graph_validation_attempts):
            raise ValueError("execution manifest graph attempts must be canonical and unique")
        attempt_ids = {attempt.attempt_id for attempt in self.graph_validation_attempts}
        if any(attempt.supersedes_attempt_id is not None and attempt.supersedes_attempt_id not in attempt_ids for attempt in self.graph_validation_attempts):
            raise ValueError("execution manifest graph attempt ancestry is orphaned")
        groups = tuple(group_id for group_id, _ in self.transaction_group_outcomes)
        if groups != tuple(sorted(groups)) or len(set(groups)) != len(groups) or any(not group_id for group_id in groups):
            raise ValueError("execution manifest group outcomes must be canonical and unique")
        for group_id, outcomes in self.transaction_group_outcomes:
            if not outcomes or outcomes != _canonical_values(outcomes) or any(outcome.instance.scope != "transaction_group" or outcome.instance.transaction_group_id != group_id for outcome in outcomes):
                raise ValueError("execution manifest group stage outcomes are invalid")
            expected_group_stages = {
                spec.stage for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages if "transaction_group" in spec.allowed_scopes
            }
            if {outcome.instance.stage for outcome in outcomes} != expected_group_stages:
                raise ValueError("execution manifest group must retain every terminal stage outcome")
        if self.causal_blockers != _canonical_values(self.causal_blockers) or len(set(self.causal_blockers)) != len(self.causal_blockers):
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
                        dependencies.append(IngestionStageInstanceRef(
                            stage=dependency.stage, scope="segment", segment_id=instance.segment_id,
                            segment_language_route_digest=instance.segment_language_route_digest,
                        ))
                    elif "source" in allowed:
                        dependencies.append(IngestionStageInstanceRef(stage=dependency.stage, scope="source"))
                elif instance.scope == "source":
                    if "source" in allowed:
                        dependencies.append(IngestionStageInstanceRef(stage=dependency.stage, scope="source"))
                    elif "segment" in allowed:
                        dependencies.extend(
                            IngestionStageInstanceRef(
                                stage=dependency.stage, scope="segment", segment_id=route.segment_id,
                                segment_language_route_digest=route.route_digest,
                            ) for route in self.segment_language_routes.routes
                        )
                    elif "transaction_group" in allowed:
                        dependencies.extend(
                            IngestionStageInstanceRef(stage=dependency.stage, scope="transaction_group", transaction_group_id=group_id)
                            for group_id, _ in self.transaction_group_outcomes
                        )
                elif instance.scope in {"source_plan_attempt", "transaction_group_attempt"}:
                    if instance.scope in allowed:
                        dependencies.append(IngestionStageInstanceRef(
                            stage=dependency.stage, scope=instance.scope,
                            transaction_group_id=instance.transaction_group_id, attempt_id=instance.attempt_id,
                        ))
                    elif "source" in allowed:
                        dependencies.append(IngestionStageInstanceRef(stage=dependency.stage, scope="source"))
                elif instance.scope == "transaction_group" and "transaction_group" in allowed:
                    dependencies.append(IngestionStageInstanceRef(
                        stage=dependency.stage, scope="transaction_group", transaction_group_id=instance.transaction_group_id,
                    ))
            return _canonical_values(tuple(set(dependencies)))  # type: ignore[return-value]

        for outcome in all_outcomes:
            dependencies = dependency_instances(outcome.instance)
            blocked = tuple(
                dependency for dependency in dependencies
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
        return cls(**values, manifest_digest=contract_digest(b"memorii.semantic-ingestion.execution-manifest.v1", values))


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
        if self.segment_governance_carriers.source_id != self.source_id or self.message_admission_carriers.source_id != self.source_id:
            raise ValueError("plan lineage carrier source mismatch")
        artifact = self.governance_carrier_artifact
        if artifact.segment_governance != self.segment_governance_carriers or artifact.message_admissions != self.message_admission_carriers or artifact.required_outcome_scopes != self.required_outcome_scopes:
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
        if self.lineage_digest != contract_digest(b"memorii.semantic-ingestion.source-transaction-plan-lineage.v1", body):
            raise ValueError("source transaction plan lineage digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SourceTransactionPlanLineage:
        return cls(**values, lineage_digest=contract_digest(b"memorii.semantic-ingestion.source-transaction-plan-lineage.v1", values))


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
        for instances, label in ((self.completed_source_stage_instances, "completed"), (self.next_eligible_source_stage_instances, "next eligible")):
            if instances != _canonical_values(instances) or len(set(instances)) != len(instances) or any(instance.scope != "source" for instance in instances):
                raise ValueError(f"pre-planning {label} stage instances must be canonical source instances")
        if set(self.completed_source_stage_instances) & set(self.next_eligible_source_stage_instances):
            raise ValueError("pre-planning complete and next-eligible stages cannot overlap")
        if self.reusable_artifact_digests != tuple(sorted(set(self.reusable_artifact_digests))) or any(len(value) != 64 for value in self.reusable_artifact_digests):
            raise ValueError("pre-planning reusable artifact digests must be canonical")
        if self.retry_reason_codes != tuple(sorted(set(self.retry_reason_codes))) or any(not code for code in self.retry_reason_codes):
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
        source_outcomes = tuple(
            outcome for outcome in manifest.source_outcomes if outcome.instance.scope == "source"
        )
        expected_completed = _canonical_values(tuple(
            outcome.instance for outcome in source_outcomes if outcome.status in successful
        ))
        if self.completed_source_stage_instances != expected_completed:
            raise ValueError("pre-planning completed stages must equal manifest-derived closure")
        expected_next = _canonical_values(tuple(
            outcome.instance
            for outcome in source_outcomes
            if outcome.status == "not_started" and set(outcome.blocking_stages).issubset(set(expected_completed))
        ))
        if self.next_eligible_source_stage_instances != expected_next:
            raise ValueError("pre-planning next eligible stages must equal manifest-derived eligibility")
        expected_reusable = tuple(sorted(
            outcome.artifact_digest for outcome in source_outcomes
            if outcome.status in successful and outcome.artifact_digest is not None
        ))
        if self.reusable_artifact_digests != expected_reusable:
            raise ValueError("pre-planning reusable artifacts must equal manifest-derived artifacts")
        body = self.model_dump(mode="python", exclude={"progress_digest"})
        if self.progress_digest != contract_digest(b"memorii.semantic-ingestion.pre-planning-source-progress.v1", body):
            raise ValueError("pre-planning source progress digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> PrePlanningSourceIngestionProgress:
        body = {"kind": "pre_planning", **values}
        return cls(**body, progress_digest=contract_digest(b"memorii.semantic-ingestion.pre-planning-source-progress.v1", body))


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
                len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
                for value in values
            ):
                raise ValueError(f"planned progress {label} must be canonical")
        if self.unfinished_transaction_group_ids != tuple(sorted(set(self.unfinished_transaction_group_ids))) or any(not value for value in self.unfinished_transaction_group_ids):
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
        return cls(**body, progress_digest=contract_digest(b"memorii.semantic-ingestion.planned-source-progress.v1", body))


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

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_content_digest(self) -> _ContentAddressedContract:
        body = {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name != self._digest_field
        }
        if getattr(self, self._digest_field) != contract_digest(self._digest_domain, body):
            raise ValueError(f"{self._digest_field} mismatch")
        return self

    @classmethod
    def create(cls, **values: object):  # type: ignore[no-untyped-def]
        body: dict[str, object] = {}
        for base in reversed(cls.__mro__):
            body.update(base.__dict__.get("_create_static_values", {}))
        body.update(values)
        return cls(**body, **{cls._digest_field: contract_digest(cls._digest_domain, body)})


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
            raise ValueError("verbatim mapping proof must bind one exact retained/local text into its projection subspan")
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


TextArtifactMappingProof = Annotated[VerbatimTextArtifactMappingProof | EnvelopeFieldTextArtifactMappingProof, Field(discriminator="kind")]


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
        if (
            self.projection_digest != self.projection_span.artifact.artifact_digest
        ):
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
            or self.projection_span.end - proof_projection.start
            != self.segment_local_span.end - proof_segment.start
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
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    predicate_head_span: SourceSpanReference
    governing_clause_spans: tuple[SourceSpanReference, ...]
    polarity: CheckResult
    commitment: CheckResult
    attribution: CheckResult
    attribution_bearer_span: SourceSpanReference | None
    interpretation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.analyzer-scope-interpretation.v1"
    _digest_field = "interpretation_digest"

    @model_validator(mode="after")
    def validate_interpretation(self) -> AnalyzerScopeInterpretation:
        spans = self.governing_clause_spans
        if not spans or spans != tuple(sorted(spans, key=lambda item: item.reference_digest)) or len(
            {item.reference_digest for item in spans}
        ) != len(spans):
            raise ValueError("governing clause spans must be nonempty and canonical")
        source_id = self.predicate_head_span.source_id
        if any(span.source_id != source_id for span in spans) or (
            self.attribution_bearer_span is not None and self.attribution_bearer_span.source_id != source_id
        ):
            raise ValueError("scope interpretation spans must belong to one source")
        return self


class StableSemanticScope(_ContentAddressedContract):
    polarity: Literal["positive", "negative"]
    commitment: Commitment
    attribution: Literal["speaker", "quoted_or_reported_source"]
    attribution_bearer_span: SourceSpanReference | None
    governing_clause_spans: tuple[SourceSpanReference, ...]
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.stable-semantic-scope.v1"
    _digest_field = "scope_digest"

    @model_validator(mode="after")
    def validate_scope(self) -> StableSemanticScope:
        if not self.governing_clause_spans or self.governing_clause_spans != tuple(
            sorted(self.governing_clause_spans, key=lambda item: item.reference_digest)
        ) or len({item.reference_digest for item in self.governing_clause_spans}) != len(self.governing_clause_spans):
            raise ValueError("stable scope governing clause spans must be nonempty and canonical")
        if self.attribution == "speaker" and self.attribution_bearer_span is not None:
            raise ValueError("speaker scope cannot retain an attribution bearer")
        if self.attribution == "quoted_or_reported_source" and self.attribution_bearer_span is None:
            raise ValueError("reported scope requires an attribution bearer")
        return self


class AnalyzerTemporalAttachment(_ContentAddressedContract):
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    predicate_head_span: SourceSpanReference
    candidate_ids: tuple[str, ...]
    attachment_spans: tuple[SourceSpanReference, ...]
    attachment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.analyzer-temporal-attachment.v1"
    _digest_field = "attachment_digest"

    @model_validator(mode="after")
    def validate_attachment(self) -> AnalyzerTemporalAttachment:
        if self.candidate_ids != tuple(sorted(set(self.candidate_ids))) or self.attachment_spans != tuple(
            sorted(self.attachment_spans, key=lambda item: item.reference_digest)
        ) or len({item.reference_digest for item in self.attachment_spans}) != len(self.attachment_spans):
            raise ValueError("temporal attachment values must be canonical and duplicate-free")
        if any(span.source_id != self.predicate_head_span.source_id for span in self.attachment_spans):
            raise ValueError("temporal attachment spans must belong to one source")
        return self


class ParserConsensusAssessment(_ContentAddressedContract):
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
    _digest_domain = b"memorii.semantic-ingestion.parser-consensus.v1"
    _digest_field = "assessment_digest"

    @model_validator(mode="after")
    def validate_assessment(self) -> ParserConsensusAssessment:
        primary, corroborating = self.primary_interpretation, self.corroborating_interpretation
        if primary.analyzer_fingerprint == corroborating.analyzer_fingerprint:
            raise ValueError("parser consensus requires distinct analyzer fingerprints")
        for interpretation in (primary, corroborating):
            if interpretation.predicate_head_span.source_id != self.source_id or any(
                assignment.argument_span.source_id != self.source_id
                or assignment.argument_span.projection_segment_id != interpretation.predicate_head_span.projection_segment_id
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
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_bundle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_interpretation: AnalyzerScopeInterpretation
    corroborating_interpretation: AnalyzerScopeInterpretation
    stable_scope: StableSemanticScope | None
    status: Literal["stable", "disagreement", "ambiguous", "unsupported"]
    consensus_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-scope-consensus.v1"
    _digest_field = "consensus_digest"

    @model_validator(mode="after")
    def validate_consensus(self) -> SemanticScopeConsensus:
        primary, corroborating = self.primary_interpretation, self.corroborating_interpretation
        if primary.analyzer_fingerprint == corroborating.analyzer_fingerprint or primary.proposal_id != self.proposal_id or corroborating.proposal_id != self.proposal_id:
            raise ValueError("scope consensus requires distinct analyzers for its exact proposal")
        equal = (
            primary.proposal_id == corroborating.proposal_id
            and primary.predicate_head_span == corroborating.predicate_head_span
            and primary.governing_clause_spans == corroborating.governing_clause_spans
            and primary.polarity == corroborating.polarity
            and primary.commitment == corroborating.commitment
            and primary.attribution == corroborating.attribution
            and primary.attribution_bearer_span == corroborating.attribution_bearer_span
        )
        if self.status == "stable":
            if self.stable_scope is None or not equal or any(
                check.status != "pass" for check in (primary.polarity, primary.commitment, primary.attribution)
            ):
                raise ValueError("stable scope consensus requires equal passing interpretations")
        elif self.stable_scope is not None or (self.status == "disagreement" and equal):
            raise ValueError("nonstable scope consensus cannot retain stable scope")
        return self


class TemporalAttachmentConsensus(_ContentAddressedContract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    temporal_resolution_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_attachment: AnalyzerTemporalAttachment
    corroborating_attachment: AnalyzerTemporalAttachment
    stable_candidate_ids: tuple[str, ...] | None
    status: Literal["stable", "disagreement", "ambiguous", "unsupported"]
    consensus_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.temporal-attachment-consensus.v1"
    _digest_field = "consensus_digest"

    @model_validator(mode="after")
    def validate_consensus(self) -> TemporalAttachmentConsensus:
        primary, corroborating = self.primary_attachment, self.corroborating_attachment
        if primary.analyzer_fingerprint == corroborating.analyzer_fingerprint or primary.proposal_id != self.proposal_id or corroborating.proposal_id != self.proposal_id:
            raise ValueError("temporal consensus requires distinct analyzers for its exact proposal")
        equal = primary.candidate_ids == corroborating.candidate_ids and primary.attachment_spans == corroborating.attachment_spans
        if self.status == "stable":
            if self.stable_candidate_ids is None or self.stable_candidate_ids != primary.candidate_ids or not equal:
                raise ValueError("stable temporal consensus requires exact shared candidates")
        elif self.stable_candidate_ids is not None or (self.status == "disagreement" and equal):
            raise ValueError("nonstable temporal consensus cannot retain candidates")
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
        if tuple(binding.segment_id for binding in bindings) != segment_ids or tuple(
            segment.segment_governance for segment in self.segments
        ) != bindings:
            raise ValueError("semantic projection governance carriers must be an ordered segment bijection")
        admissions = tuple(segment.message_admission_identity for segment in self.segments if segment.message_admission_identity is not None)
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
                or self.projection_text[span.start:span.end] != segment.semantic_text
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
    language_route: SegmentLanguageRoute
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
            or tuple(self.code_switch_spans) != tuple(route.code_switch_spans)
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
            or any(not language or language != language.strip() or not re.fullmatch(r"[a-z]{2,8}(?:-(?:[A-Z][a-z]{3}|[A-Z]{2}|[0-9]{3}|[a-z0-9]{1,8}))*", language) for language in self.supported_languages)
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
        if not self.allowed_role_ids or self.allowed_role_ids != tuple(sorted(self.allowed_role_ids)) or len(set(self.allowed_role_ids)) != len(self.allowed_role_ids):
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
        if self.roles != tuple(sorted(self.roles, key=lambda item: item.role_id)) or len({item.role_id for item in self.roles}) != len(self.roles):
            raise ValueError("action catalog roles must be canonical and unique")
        if self.states != tuple(sorted(self.states, key=lambda item: item.state_id)) or len({item.state_id for item in self.states}) != len(self.states):
            raise ValueError("action catalog states must be canonical and unique")
        role_ids = {item.role_id for item in self.roles}
        if not self.roles or not self.states or any(set(item.allowed_role_ids) - role_ids for item in self.states) or role_ids != set().union(*(set(item.allowed_role_ids) for item in self.states)):
            raise ValueError("action catalog states must exactly cover catalog roles")
        return self


class PredicatePromptContract(_ContentAddressedContract):
    predicate_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    subject_value_kind: Literal["entity"]
    object_value_kind: Literal["entity", "literal"]
    object_literal_type: ClaimValueType | None
    supported_commitments: tuple[Literal["asserted", "believed", "reported", "quoted", "questioned", "instructed", "hypothetical"], ...]
    contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.predicate-prompt-contract.v1"
    _digest_field = "contract_digest"

    @model_validator(mode="after")
    def validate_predicate(self) -> PredicatePromptContract:
        commitment_order = ("asserted", "believed", "reported", "quoted", "questioned", "instructed", "hypothetical")
        if (self.object_value_kind == "entity") != (self.object_literal_type is None):
            raise ValueError("predicate literal type must match object kind")
        if not self.supported_commitments or self.supported_commitments != tuple(sorted(self.supported_commitments, key=commitment_order.index)) or len(set(self.supported_commitments)) != len(self.supported_commitments):
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
        if not self.predicates or self.predicates != tuple(sorted(self.predicates, key=lambda item: item.predicate_id)) or len({item.predicate_id for item in self.predicates}) != len(self.predicates):
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
            or self.governance_carrier_artifact.required_outcome_scopes != self.semantic_text_projection.required_outcome_scopes
        ):
            raise ValueError("prepared source governance artifact must contain its exact carriers")
        ids = tuple(segment.segment_id for segment in self.segments)
        parents = tuple(segment.parent_projection_segment_id for segment in self.segments)
        if not ids or len(set(ids)) != len(ids) or tuple(route.segment_id for route in self.segment_language_routes.routes) != ids:
            raise ValueError("prepared source routes must be an ordered segment bijection")
        if tuple(route.parent_projection_segment_id for route in self.segment_language_routes.routes) != parents:
            raise ValueError("prepared source routes must copy child parent coordinates")
        route_by_artifact = {
            route.segment_text_artifact_digest: route
            for route in self.segment_language_routes.routes
        }
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
        if tuple(parent for parent, _children in groupby(
            self.segments, key=lambda item: item.parent_projection_segment_id
        )) != expected_parent_ids:
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
                    or self.semantic_text[child.owned_projection_span.start:child.owned_projection_span.end]
                    != parent.semantic_text[child.owned_segment_span.start:child.owned_segment_span.end]
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


ProviderRecordSelector = Annotated[ProviderClaimRecordSelector | ProviderActionRecordSelector | ProviderAliasRecordSelector, Field(discriminator="kind")]


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
        if self.abstained and (self.facts or self.corrections or self.retractions or self.action_states or self.identity_operations):
            raise ValueError("abstained provider proposal cannot contain operations")
        all_ids = self.mentions + self.facts + self.corrections + self.retractions + self.action_states + self.identity_operations
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
        if not keys or keys != tuple(sorted(keys)) or len({member.participant_digest for member in self.participants}) != len(self.participants):
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
        if self.execution_branch_span is not None and self.execution_branch_digest != contract_digest(b"memorii.semantic-ingestion.proposed-execution-branch.v1", {"execution_branch_span": self.execution_branch_span}):
            raise ValueError("execution branch digest mismatch")
        binding_keys = tuple((item.role_id, item.endpoint_kind, item.binding_digest) for item in self.role_bindings)
        span_keys = tuple(item.reference_digest for item in self.temporal_qualifier_spans)
        if binding_keys != tuple(sorted(binding_keys)) or len({item.binding_digest for item in self.role_bindings}) != len(self.role_bindings) or span_keys != tuple(sorted(span_keys)) or len(set(span_keys)) != len(span_keys):
            raise ValueError("action nested members must be canonical and unique")
        expected = contract_digest(b"memorii.semantic-ingestion.proposed-logical-action.v1", {"action_anchor_span": self.action_anchor_span, "role_bindings": self.role_bindings})
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


ProposedRecordSelector = Annotated[ProposedClaimRecordSelector | ProposedActionRecordSelector | ProposedAliasRecordSelector, Field(discriminator="kind")]


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
        if not self.successor_mention_digests or self.successor_mention_digests != tuple(sorted(self.successor_mention_digests)) or len(set(self.successor_mention_digests)) != len(self.successor_mention_digests):
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
        assignments = tuple((item.record_selector.selector_digest, item.assignment_digest) for item in self.reference_assignments)
        if assignments != tuple(sorted(assignments)) or len({item.assignment_digest for item in self.reference_assignments}) != len(self.reference_assignments) or len({item.record_selector.selector_digest for item in self.reference_assignments}) != len(self.reference_assignments):
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
            self.message_admission_identity.segment_governance_binding_digest
            != self.segment_governance.binding_digest
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
        for members, field, key in ((self.mentions, "mention_digest", lambda x: (x.mention_span.reference_digest, x.mention_digest)), (self.facts, "fact_digest", lambda x: (x.predicate_anchor_span.reference_digest, x.assertion_span.reference_digest, x.fact_digest)), (self.corrections, "correction_digest", lambda x: (x.correction_anchor_span.reference_digest, x.assertion_span.reference_digest, x.correction_digest)), (self.retractions, "retraction_digest", lambda x: (x.retraction_anchor_span.reference_digest, x.assertion_span.reference_digest, x.retraction_digest)), (self.action_states, "action_state_digest", lambda x: (x.action_anchor_span.reference_digest, x.assertion_span.reference_digest, x.action_state_digest)), (self.identity_operations, "identity_operation_digest", lambda x: (x.identity_anchor_span.reference_digest, x.assertion_span.reference_digest, x.identity_operation_digest))):
            digests = tuple(getattr(member, field) for member in members)
            if tuple(members) != tuple(sorted(members, key=key)) or len(set(digests)) != len(digests):
                raise ValueError("proposal members must be canonical and unique")
        self._validate_member_closure()
        return self


class SemanticProposalRequest(_ContentAddressedContract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str = Field(min_length=1)
    segment_governance: SegmentGovernanceBinding
    message_admission_identity: MessageAdmissionIdentity | None
    governance_carrier_artifact: GovernanceCarrierArtifact
    owned_text: SourceSpanReference
    context_text: SourceSpanReference
    segment_text: str
    language_route: SegmentLanguageRoute
    provider_egress_decision_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_catalog: PredicateProposalCatalog
    action_proposal_catalog: ActionProposalCatalog
    registered_prompt: RegisteredSemanticPromptBinding
    proposer_manifest: SemanticProposerManifest
    semantic_request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-proposal-request.v1"
    _digest_field = "semantic_request_fingerprint"

    @model_validator(mode="after")
    def validate_request(self) -> SemanticProposalRequest:
        route = self.language_route
        if (
            route.decision != "selected"
            or (self.source_id, self.source_digest, self.segment_id)
            != (route.source_id, route.source_digest, route.segment_id)
            or self.segment_governance.segment_id != route.parent_projection_segment_id
            or self.owned_text.projection_segment_id != route.parent_projection_segment_id
            or self.context_text.projection_segment_id != route.parent_projection_segment_id
            or self.predicate_catalog.proposal_capability_fingerprint != self.proposal_capability_fingerprint
            or self.action_proposal_catalog.proposal_capability_fingerprint != self.proposal_capability_fingerprint
            or self.proposer_manifest.structured_output_capability_fingerprint != self.proposal_capability_fingerprint
            or (self.proposer_manifest.proposer_kind == "local") != (self.provider_egress_decision_digest is None)
        ):
            raise ValueError("semantic proposal request authorities must be exact and selected")
        if (
            self.semantic_context_fingerprint != self.segment_governance.message_semantic_context_digest
            or self.message_admission_identity is not None
            and self.message_admission_identity.segment_governance_binding_digest
            != self.segment_governance.binding_digest
            or self.segment_governance not in self.governance_carrier_artifact.segment_governance.bindings
            or self.message_admission_identity is not None
            and self.message_admission_identity not in self.governance_carrier_artifact.message_admissions.identities
        ):
            raise ValueError("semantic proposal request context and governance closure mismatch")
        for span in (self.owned_text, self.context_text):
            if (
                span.source_id != self.source_id
                or span.projection_segment_id != route.parent_projection_segment_id
                or span.segment_local_span.artifact.artifact_id != route.segment_text_artifact_id
                or span.segment_local_span.artifact.artifact_digest != route.segment_text_artifact_digest
                or span.segment_local_span.artifact.content_digest != route.segment_text_content_digest
            ):
                raise ValueError("semantic proposal request text must bind its exact route parent and artifact")
        if (
            not _reference_contains(self.context_text, self.owned_text)
            or self.owned_text.projection_digest != self.context_text.projection_digest
            or self.owned_text.retained_text_artifact != self.context_text.retained_text_artifact
            or self.owned_text.text_mapping_proof != self.context_text.text_mapping_proof
            or len(self.segment_text) != self.context_text.segment_local_span.end - self.context_text.segment_local_span.start
            or sha256(self.segment_text.encode("utf-8")).hexdigest()
            != self.context_text.segment_local_span.substring_digest
        ):
            raise ValueError("semantic proposal request text must be the exact context slice")
        return self


class SemanticProposalRequestArtifact(_ContentAddressedContract):
    request_bytes: bytes
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.semantic-proposal-request-artifact.v1"
    _digest_field = "artifact_digest"

    @model_validator(mode="after")
    def validate_request(self) -> SemanticProposalRequestArtifact:
        try:
            request = decode_semantic_contract(self.request_bytes, SemanticProposalRequest)
        except SemanticContractCodecError as exc:
            raise ValueError("proposal request artifact must contain one strict request") from exc
        if (
            encode_semantic_contract(request) != self.request_bytes
            or self.request_digest != sha256(self.request_bytes).hexdigest()
        ):
            raise ValueError("proposal request artifact bytes digest mismatch")
        return self

    @classmethod
    def create(cls, *, request_bytes: bytes) -> SemanticProposalRequestArtifact:
        return super().create(request_bytes=request_bytes, request_digest=sha256(request_bytes).hexdigest())


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
            or (self.message_admission_identity is not None and self.message_admission_identity not in artifact.message_admissions.identities)
        ):
            raise ValueError("proposal attempt identity governance artifact does not contain its authorities")
        for span in (self.owned_text, self.context_text):
            if span.source_id != self.source_id or span.projection_segment_id != self.language_route.parent_projection_segment_id:
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


class SemanticProposalRun(_ContentAddressedContract):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    segment_language_routes: SegmentLanguageRouteSet
    expected_segment_ids: tuple[str, ...]
    segment_attempts: tuple[SemanticProposalAttempt, ...]
    validated_segments: tuple[SemanticProposal, ...]
    segment_outcomes: tuple[SegmentProposalOutcome, ...]
    status: Literal["complete", "evidence_only", "abstained", "incomplete", "failed"]
    run_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostics: tuple[str, ...]
    _digest_domain = b"memorii.semantic-ingestion.semantic-proposal-run.v1"
    _digest_field = "run_fingerprint"

    @model_validator(mode="after")
    def validate_run(self) -> SemanticProposalRun:
        expected = self.expected_segment_ids
        if not expected or len(set(expected)) != len(expected):
            raise ValueError("proposal run expected segments must be nonempty and unique")
        if (
            self.segment_governance_carriers.source_id != self.source_id
            or self.message_admission_carriers.source_id != self.source_id
            or self.segment_language_routes.source_id != self.source_id
            or self.segment_language_routes.source_digest != self.source_digest
            or self.governance_carrier_artifact.segment_governance != self.segment_governance_carriers
            or self.governance_carrier_artifact.message_admissions != self.message_admission_carriers
        ):
            raise ValueError("proposal run source authorities must agree")
        routes = self.segment_language_routes.routes
        if tuple(route.segment_id for route in routes) != expected:
            raise ValueError("proposal run routes must be an ordered expected-segment bijection")
        parent_order = tuple(dict.fromkeys(route.parent_projection_segment_id for route in routes))
        governance_by_parent = {
            binding.segment_id: binding for binding in self.segment_governance_carriers.bindings
        }
        if (
            tuple(binding.segment_id for binding in self.segment_governance_carriers.bindings)
            != parent_order
            or set(governance_by_parent) != set(parent_order)
        ):
            raise ValueError("proposal run governance carriers must be unique route parents")
        attempts = self.segment_attempts
        if tuple(attempt.identity.segment_id for attempt in attempts) != tuple(
            sorted((attempt.identity.segment_id for attempt in attempts), key=expected.index)
        ):
            raise ValueError("proposal run attempts must be grouped in expected-segment order")
        if tuple(outcome.segment_id for outcome in self.segment_outcomes) != expected:
            raise ValueError("proposal run outcomes must be an ordered expected-segment bijection")
        route_by_segment = dict(zip(expected, routes, strict=True))
        attempts_by_segment: dict[str, tuple[SemanticProposalAttempt, ...]] = {
            segment_id: tuple(item for item in attempts if item.identity.segment_id == segment_id)
            for segment_id in expected
        }
        if any(item.identity.segment_id not in route_by_segment for item in attempts):
            raise ValueError("proposal run attempt names an unexpected segment")
        for segment_id, history in attempts_by_segment.items():
            route = route_by_segment[segment_id]
            if route.decision == "selected":
                if not history:
                    raise ValueError("selected proposal route requires final attempt history")
                if tuple(item.identity.attempt_number for item in history) != tuple(range(len(history))):
                    raise ValueError("proposal attempts must have contiguous numbers")
                if len({item.identity.attempt_identity_digest for item in history}) != len(history):
                    raise ValueError("proposal attempt identities must be unique")
                if any(item.identity.language_route != route for item in history):
                    raise ValueError("proposal attempts must copy their exact selected route")
                if any(
                    item.identity.source_id != self.source_id
                    or item.identity.preparation_fingerprint != self.preparation_fingerprint
                    or item.identity.segment_governance
                    != governance_by_parent[route.parent_projection_segment_id]
                    or item.identity.governance_carrier_artifact != self.governance_carrier_artifact
                    for item in history
                ):
                    raise ValueError("proposal attempts must copy exact run governance")
                for previous, current in zip(history, history[1:], strict=False):
                    if (
                        previous.status in {"partial", "failed"}
                        and previous.raw_output_digest is not None
                        and current.identity.attempt_payload_fingerprint == previous.identity.attempt_payload_fingerprint
                    ):
                        raise ValueError("repair after artifact-bearing partial or failure needs new payload fingerprint")
            elif history:
                raise ValueError("blocked proposal route cannot have attempts")
        proposal_by_segment: dict[str, SemanticProposal] = {}
        for proposal in self.validated_segments:
            if proposal.segment_id in proposal_by_segment or proposal.segment_id not in attempts_by_segment:
                raise ValueError("proposal run validated proposals must name unique expected segments")
            history = attempts_by_segment[proposal.segment_id]
            attempt = history[-1] if history else None
            route = route_by_segment[proposal.segment_id]
            if (
                proposal.source_id != self.source_id
                or proposal.source_digest != self.source_digest
                or proposal.language_route != route
                or proposal.preparation_fingerprint != self.preparation_fingerprint
                or proposal.segment_governance
                != governance_by_parent[route.parent_projection_segment_id]
            or proposal.message_admission_identity
            != next(
                (
                    identity
                    for identity in self.message_admission_carriers.identities
                    if attempt is not None and identity.segment_governance_binding_digest == attempt.identity.segment_governance.binding_digest
                ),
                None,
            )
                or attempt is None
                or attempt.status != proposal.status
                or attempt.status not in {"complete", "abstained"}
                or proposal.originating_attempt_digest != attempt.attempt_digest
                or proposal.owned_text != attempt.identity.owned_text
                or proposal.context_text != attempt.identity.context_text
                or proposal.proposer_fingerprint != attempt.identity.proposer_fingerprint
                or proposal.proposer_manifest_digest != attempt.identity.proposer_manifest_digest
                or proposal.prompt_registration_digest != attempt.identity.prompt_registration_digest
                or proposal.semantic_request_fingerprint != attempt.identity.semantic_request_fingerprint
                or proposal.attempt_payload_fingerprint != attempt.identity.attempt_payload_fingerprint
            ):
                raise ValueError("proposal run validated proposal must exactly match its attempt coordinate")
            proposal_by_segment[proposal.segment_id] = proposal
        for outcome in self.segment_outcomes:
            history = attempts_by_segment[outcome.segment_id]
            attempt = history[-1] if history else None
            route = route_by_segment[outcome.segment_id]
            proposal = proposal_by_segment.get(outcome.segment_id)
            if outcome.attempt_digest != (None if attempt is None else attempt.attempt_digest) or outcome.segment_language_route_digest != route.route_digest:
                raise ValueError("proposal outcome must copy its exact attempt and route")
            if proposal is None:
                if outcome.proposal_digest is not None:
                    raise ValueError("proposal outcome cannot reference an unvalidated proposal")
                expected_status = (
                    "evidence_only"
                    if attempt is None or attempt.status in {"partial", "evidence_only"}
                    else "failed"
                    if attempt.status == "failed"
                    else None
                )
                if outcome.status != expected_status:
                    raise ValueError("proposal outcome status must derive from its final attempt")
            elif outcome.proposal_digest != proposal.proposal_digest or outcome.status != proposal.status:
                raise ValueError("proposal outcome must copy its exact validated proposal status and digest")
            if route.decision != "selected" and (outcome.status != "evidence_only" or proposal is not None):
                raise ValueError("non-selected route must remain evidence-only")
        outcome_statuses = tuple(outcome.status for outcome in self.segment_outcomes)
        if self.status == "abstained" and any(
            route.decision == "selected" and proposal_by_segment.get(route.segment_id) is None
            or route.decision == "selected" and proposal_by_segment[route.segment_id].status != "abstained"
            for route in routes
        ):
            raise ValueError("abstained proposal run requires abstained validated selected routes")
        if all(status == "evidence_only" for status in outcome_statuses):
            derived_status = "evidence_only"
        elif any(status == "failed" for status in outcome_statuses):
            derived_status = "failed"
        elif all(
            route.decision != "selected" or proposal_by_segment.get(route.segment_id) is not None
            and proposal_by_segment[route.segment_id].status == "abstained"
            for route in routes
        ):
            derived_status = "abstained"
        elif all(status in {"complete", "abstained", "evidence_only"} for status in outcome_statuses):
            derived_status = "complete"
        else:
            derived_status = "incomplete"
        if self.status != derived_status:
            raise ValueError("proposal run status must be derived from exact outcomes")
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
                            raise ValueError(f"proposal action {index} participant grounding must lie within its assertion")

        facts_by_digest = {fact.fact_digest for fact in self.facts}
        action_coordinates = tuple(
            (action.logical_action_digest, action.action_anchor_span.reference_digest)
            for action in self.action_states
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
                    raise ValueError(f"proposal identity {index} assignment {assignment_index} must lie within its assertion")
                selector = assignment.record_selector
                if isinstance(selector, ProposedClaimRecordSelector):
                    if selector.fact_digest not in facts_by_digest:
                        raise ValueError(f"identity {index} claim selector must resolve exactly one top-level fact")
                elif isinstance(selector, ProposedActionRecordSelector):
                    require_span(selector.action_anchor_span, f"identity {index} action selector")
                    if not _reference_contains(assignment.assertion_span, selector.action_anchor_span):
                        raise ValueError(f"proposal identity {index} action selector must lie within its assignment assertion")
                    if action_coordinates.count(
                        (selector.logical_action_digest, selector.action_anchor_span.reference_digest)
                    ) != 1:
                        raise ValueError(f"identity {index} action selector must resolve exactly one action")
                else:
                    require_span(selector.alias_anchor_span, f"identity {index} alias selector")
                    if not _reference_contains(assignment.assertion_span, selector.alias_anchor_span):
                        raise ValueError(f"proposal identity {index} alias selector must lie within its assignment assertion")

    @property
    def segment_language_route_digest(self) -> str:
        """Compatibility read view; the route object is the persisted authority."""
        return self.language_route.route_digest


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
SemanticProposal._validate_member_closure = SemanticProposalRun._validate_member_closure
SemanticProposal.segment_language_route_digest = SemanticProposalRun.segment_language_route_digest


class ParserConsensusPolicy(_ContentAddressedContract):
    kind: Literal["parser"]
    algorithm: Literal["memorii.semantic-ingestion.parser-consensus.exact-two-analyzer.v1"]
    required_independent_analyzers: Literal[2]
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.parser-consensus-rule.v1"
    _digest_field = "policy_fingerprint"
    _create_static_values = {
        "kind": "parser", "algorithm": "memorii.semantic-ingestion.parser-consensus.exact-two-analyzer.v1",
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
        "kind": "scope", "algorithm": "memorii.semantic-ingestion.scope-consensus.exact-two-analyzer.v1",
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


ConsensusPolicy = Annotated[ParserConsensusPolicy | ScopeConsensusPolicy | TemporalAttachmentConsensusPolicy, Field(discriminator="kind")]


class ConsensusPolicySelection(_ContentAddressedContract):
    kind: Literal["parser", "scope", "temporal_attachment"]
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_dependency_kind: Literal["analyses", "temporal_resolution"]
    request_dependency_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_policy: ConsensusPolicy
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.consensus-policy-selection.v1"
    _digest_field = "selection_digest"

    @model_validator(mode="after")
    def validate_selection(self):
        if self.kind != self.selected_policy.kind or self.selected_policy_fingerprint != self.selected_policy.policy_fingerprint:
            raise ValueError("consensus policy selection must bind exact policy kind and fingerprint")
        if (self.kind == "temporal_attachment") != (self.request_dependency_kind == "temporal_resolution"):
            raise ValueError("consensus policy selection dependency kind mismatches rule kind")
        return self


class ConsensusPolicySelectionBundle(_ContentAddressedContract):
    selections: tuple[ConsensusPolicySelection, ...]
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    _digest_domain = b"memorii.semantic-ingestion.consensus-policy-selection-bundle.v1"
    _digest_field = "bundle_digest"

    @model_validator(mode="after")
    def validate_bundle(self):
        keys = tuple((v.kind, v.operation_id, v.proposal_id, v.segment_id, v.segment_language_route_digest) for v in self.selections)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("consensus policy selections must be canonical and coordinate-unique")
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
        for values in (self.predecessor_mention_digests, self.successor_mention_digests, self.reference_assignment_digests):
            if values != tuple(sorted(values)) or len(set(values)) != len(values):
                raise ValueError("identity policy key tuples must be canonical and unique")
        return self


OperationSemanticPolicyKey = Annotated[FactOperationSemanticPolicyKey | CorrectionOperationSemanticPolicyKey | RetractionOperationSemanticPolicyKey | ActionStateOperationSemanticPolicyKey | IdentityOperationSemanticPolicyKey, Field(discriminator="kind")]


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
    for kind, members in (("fact", proposal.facts), ("correction", proposal.corrections), ("retraction", proposal.retractions), ("action_state", proposal.action_states), ("identity", proposal.identity_operations)):
        for index, _member in enumerate(members):
            subjects.append(PreAlignmentSemanticOperationSubject.create(
                kind=kind, source_id=proposal.source_id, source_digest=proposal.source_digest,
                proposal_id=proposal.proposal_id, proposal_digest=proposal.proposal_digest,
                segment_id=proposal.segment_id, segment_language_route_digest=proposal.language_route.route_digest,
                proposal_member_index=index,
            ))
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
            expected = (("corrected", self.semantic_policy_key.corrected_predicate_id), ("replacement", self.semantic_policy_key.replacement_predicate_id))
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


LanguageConstructionPolicyAuthority = Annotated[ParserOperationPolicyAuthority | ScopeOperationPolicyAuthority, Field(discriminator="kind")]


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
            if len(policies) != 2 or not isinstance(policies[0], ParserOperationPolicyAuthority) or not isinstance(policies[1], ScopeOperationPolicyAuthority):
                raise ValueError("each language construction authority group requires parser then scope policy")
            parser, scope = policies
            if parser.semantic_policy_key != scope.semantic_policy_key:
                raise ValueError("parser and scope authorities must bind the same semantic policy key")
            if scope.scope_policy.construction_family not in parser.construction_families:
                raise ValueError("scope construction family must be present in parser authority")
            if any(binding.policy.language != scope.scope_policy.language for binding in parser.predicate_policy_bindings):
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
        if (self.segment_governance.source_id, self.segment_governance.segment_id) != (self.source_id, self.parent_projection_segment_id) or (self.language_route.source_id, self.language_route.source_digest, self.language_route.segment_id, self.language_route.parent_projection_segment_id) != (self.source_id, self.source_digest, self.segment_id, self.parent_projection_segment_id):
            raise ValueError("analysis input must bind exact segment governance and route")
        if self.context_text.source_id != self.source_id or self.context_text.projection_segment_id != self.parent_projection_segment_id:
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
        if binding is None or self.segment.language_route.decision != "selected" or self.analyzer_manifest.manifest_digest != (binding.stanza_analyzer_manifest_digest if self.analyzer_manifest.analyzer_kind == "stanza" else binding.spacy_analyzer_manifest_digest) or self.segment.language_route.selected_language not in self.analyzer_manifest.supported_languages:
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
        if binding is None or self.segment.language_route.decision != "selected" or self.predicate_event_manifest.manifest_digest != binding.predicate_event_manifest_digest or self.predicate_event_manifest.language != self.segment.language_route.selected_language:
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
        if binding is None or self.segment.language_route.decision != "selected" or self.resolver_manifest.manifest_digest != binding.temporal_resolver_manifest_digest:
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
        if self.morphological_features != tuple(sorted(self.morphological_features, key=lambda item: (item.name, item.value, item.feature_digest))) or len({item.name for item in self.morphological_features}) != len(self.morphological_features):
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
        if not self.token_ids or len(set(self.token_ids)) != len(self.token_ids) or self.head_token_id not in self.token_ids:
            raise ValueError("source mention tokens must be unique and include head")
        if (self.kind == "named_entity") != (self.entity_label is not None) or (self.kind == "coordinated_argument") != (self.coordination_group_id is not None):
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
        if not any((self.opening_token_id, self.closing_token_id, self.reporting_head_token_id, self.complement_clause_id, self.attribution_argument_digest)):
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
        if self.status == "evidence_only" and any(value is not None for value in (self.resource_binding_digest, self.selected_manifest_digest, self.artifact_digest)):
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
        if token_ids != tuple(token.token_id for token in sorted(self.tokens, key=token_key)) or len(set(token_ids)) != len(token_ids):
            raise ValueError("analysis tokens must be uniquely source ordered")
        if len({(token.sentence_index, token.word_index, token.syntactic_word_index) for token in self.tokens}) != len(self.tokens):
            raise ValueError("analysis token coordinates must be unique")
        if any(
            token.source_span.source_id != self.source_id
            for token in self.tokens
        ):
            raise ValueError("analysis token spans must bind exact source and segment")
        token_set = set(token_ids)
        if any(arc.dependent_token_id not in token_set or arc.governor_token_id is not None and arc.governor_token_id not in token_set for arc in self.dependencies):
            raise ValueError("dependency endpoints must resolve to analysis tokens")
        basic = tuple(arc for arc in self.dependencies if not arc.enhanced)
        syntactic = tuple(token for token in self.tokens if token.syntactic_word_index is not None)
        token_by_id = {token.token_id: token for token in self.tokens}
        def arc_key(arc: DependencyArc) -> tuple[tuple[int, int, int, str, str], bool, str, tuple[int, int, int, str, str], str]:
            return (
                token_key(token_by_id[arc.dependent_token_id]),
                arc.enhanced,
                arc.relation,
                (-1, -1, -1, "", "") if arc.governor_token_id is None else token_key(token_by_id[arc.governor_token_id]),
                arc.arc_id,
            )
        if (
            self.dependencies != tuple(sorted(self.dependencies, key=arc_key))
            or len({arc.arc_id for arc in self.dependencies}) != len(self.dependencies)
            or len({(arc.dependent_token_id, arc.governor_token_id, arc.relation, arc.enhanced) for arc in self.dependencies}) != len(self.dependencies)
            or {arc.dependent_token_id for arc in basic} != {token.token_id for token in syntactic}
            or len(basic) != len(syntactic)
            or sum(arc.governor_token_id is None and arc.relation == "root" for arc in basic) != 1
            or any((arc.governor_token_id is None) != (arc.relation == "root") for arc in basic)
        ):
            raise ValueError("analysis basic dependencies must form one rooted tree")
        if any(
            set(mention.token_ids) - token_set
            or mention.source_span.source_id != self.source_id
            or any(not _reference_contains(mention.source_span, token_by_id[token_id].source_span) for token_id in mention.token_ids)
            or tuple(mention.token_ids) != tuple(sorted(mention.token_ids, key=lambda item: token_key(token_by_id[item])))
            for mention in self.mentions
        ):
            raise ValueError("source mentions must reference analysis tokens")
        if self.mentions != tuple(sorted(self.mentions, key=lambda item: (item.source_span.reference_digest, item.kind, item.mention_digest))):
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
                or not _reference_contains(clause.predicate_span, token_by_id[clause.predicate_head_token_id].source_span)
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
                or argument.mention_digest is not None and argument.mention_digest not in mention_ids
                or argument.source_span.source_id != self.source_id
                or not _reference_contains(clause.source_span, argument.source_span)
                for argument in clause.arguments
            ):
                raise ValueError("clause argument references must resolve")
            if (
                clause.arguments
                != tuple(sorted(clause.arguments, key=lambda item: (item.source_span.reference_digest, item.grammatical_role, item.argument_digest)))
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
                    for token_id in (quotation.opening_token_id, quotation.closing_token_id, quotation.reporting_head_token_id)
                )
                or quotation.complement_clause_id is not None and quotation.complement_clause_id not in clause_ids
                or quotation.attribution_argument_digest is not None
                and quotation.attribution_argument_digest not in {argument.argument_digest for argument in clause.arguments}
                or quotation.opening_token_id is not None
                and quotation.closing_token_id is not None
                and token_key(token_by_id[quotation.opening_token_id]) >= token_key(token_by_id[quotation.closing_token_id])
            ):
                raise ValueError("quotation evidence references must resolve in clause")
        for clause in self.clauses:
            parent_id = clause.parent_clause_id
            visited = {clause.clause_id}
            while parent_id is not None:
                if parent_id in visited or not _reference_contains(clause_by_id[parent_id].source_span, clause.source_span) or clause_by_id[parent_id].source_span == clause.source_span:
                    raise ValueError("clause parents must be acyclic and strictly containing")
                visited.add(parent_id)
                parent_id = clause_by_id[parent_id].parent_clause_id
        # Exact token surface and temporal text slicing is deliberately checked
        # at SourceNormalizationRequest against retained PreparedSource bytes.
        return self


class SegmentLinguisticAnalysisBundle(_ContentAddressedContract):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_id: str
    segment_language_route_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary: LinguisticAnalysis | None
    corroborating: LinguisticAnalysis | None
    lane_outcomes: tuple[SegmentLanguageLaneOutcome, ...]
    status: _AnalysisStatus
    bundle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostics: tuple[str, ...]
    _digest_domain = b"memorii.semantic-ingestion.segment-linguistic-analysis-bundle.v1"
    _digest_field = "bundle_fingerprint"

    @model_validator(mode="after")
    def validate_bundle(self) -> SegmentLinguisticAnalysisBundle:
        if tuple(item.lane for item in self.lane_outcomes) != ("stanza", "spacy") or self.status != _segment_parser_status(self.lane_outcomes):
            raise ValueError("segment linguistic bundle lanes and status must be derived")
        if any(item.preparation_fingerprint != self.preparation_fingerprint for item in self.lane_outcomes):
            raise ValueError("segment linguistic bundle preparation fingerprint must join both lanes")
        for analysis, lane in ((self.primary, "stanza"), (self.corroborating, "spacy")):
            outcome = next(item for item in self.lane_outcomes if item.lane == lane)
            if (outcome.segment_id, outcome.segment_language_route_digest) != (self.segment_id, self.segment_language_route_digest):
                raise ValueError("parser lane outcome must bind exact segment route")
            if analysis is None:
                if outcome.artifact_digest is not None:
                    raise ValueError("missing parser analysis cannot retain artifact digest")
            elif (
                analysis.status not in {"complete", "partial"}
                or (analysis.source_id, analysis.source_digest, analysis.segment_id, analysis.segment_language_route_digest, analysis.analysis_digest)
                != (self.source_id, self.source_digest, self.segment_id, self.segment_language_route_digest, outcome.artifact_digest)
                or analysis.preparation_fingerprint != self.preparation_fingerprint
                or outcome.preparation_fingerprint != self.preparation_fingerprint
            ):
                raise ValueError("parser analysis must exactly match its lane outcome")
        if self.status == "complete" and (
            self.primary is None
            or self.corroborating is None
            or self.primary.status != "complete"
            or self.corroborating.status != "complete"
            or self.primary.analyzer_fingerprint == self.corroborating.analyzer_fingerprint
        ):
            raise ValueError("complete parser bundle requires distinct complete analyses")
        return self


class LinguisticAnalysisBundle(_ContentAddressedContract):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_language_routes: SegmentLanguageRouteSet
    segment_bundles: tuple[SegmentLinguisticAnalysisBundle, ...]
    segment_outcomes: tuple[SegmentLanguageLaneOutcome, ...]
    status: _AnalysisStatus
    bundle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostics: tuple[str, ...]
    _digest_domain = b"memorii.semantic-ingestion.linguistic-analysis-bundle.v1"
    _digest_field = "bundle_fingerprint"

    @model_validator(mode="after")
    def validate_bundle(self) -> LinguisticAnalysisBundle:
        routes = self.segment_language_routes.routes
        if (
            self.source_id != self.segment_language_routes.source_id
            or self.source_digest != self.segment_language_routes.source_digest
            or tuple(item.segment_id for item in self.segment_bundles) != tuple(route.segment_id for route in routes)
            or self.segment_outcomes != tuple(outcome for bundle in self.segment_bundles for outcome in bundle.lane_outcomes)
        ):
            raise ValueError("linguistic bundle must be exact route and outcome bijection")
        if self.status != _aggregate_status(self.segment_bundles):
            raise ValueError("linguistic bundle status must be derived")
        for route, bundle in zip(routes, self.segment_bundles, strict=True):
            if (bundle.source_id, bundle.source_digest, bundle.segment_id, bundle.segment_language_route_digest) != (
                self.source_id,
                self.source_digest,
                route.segment_id,
                route.route_digest,
            ):
                raise ValueError("linguistic bundle segment coordinate must match route")
            if bundle.preparation_fingerprint != self.preparation_fingerprint or any(
                outcome.preparation_fingerprint != self.preparation_fingerprint
                for outcome in bundle.lane_outcomes
            ):
                raise ValueError("linguistic bundle preparation fingerprint must join every segment outcome")
            _validate_selected_lane_outcomes((route,), bundle.lane_outcomes)
            for analysis, lane in ((bundle.primary, "stanza"), (bundle.corroborating, "spacy")):
                if analysis is None:
                    continue
                binding = route.resource_binding
                if binding is None or analysis.language != route.selected_language or analysis.analyzer_manifest_digest != (
                    binding.stanza_analyzer_manifest_digest if lane == "stanza" else binding.spacy_analyzer_manifest_digest
                ):
                    raise ValueError("parser analysis manifest and language must match route")
                if analysis.preparation_fingerprint != self.preparation_fingerprint:
                    raise ValueError("parser analysis preparation fingerprint must match its aggregate")
                spans = [token.source_span for token in analysis.tokens]
                spans.extend(token.multi_word_token_span for token in analysis.tokens if token.multi_word_token_span is not None)
                spans.extend(mention.source_span for mention in analysis.mentions)
                for clause in analysis.clauses:
                    spans.extend((clause.source_span, clause.predicate_span))
                    spans.extend(argument.source_span for argument in clause.arguments)
                for span in spans:
                    _validate_route_span(span, route, self.source_id)
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
        identity = {name: getattr(self, name) for name in ("segment_id", "preparation_fingerprint", "segment_language_route_digest", "predicate_family", "lexical_anchor_span", "detection_rule_id", "detection_manifest_fingerprint")}
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
        if self.source_id != self.segment_language_routes.source_id or self.source_digest != self.segment_language_routes.source_digest:
            raise ValueError("predicate inventory source must match route set")
        if tuple((item.lane, item.segment_id) for item in self.segment_outcomes) != tuple(("predicate_event_detection", route.segment_id) for route in routes):
            raise ValueError("predicate inventory outcomes must be exact route bijection")
        if self.status != _aggregate_status(self.segment_outcomes):
            raise ValueError("predicate inventory status must be derived")
        if any(item.preparation_fingerprint != self.preparation_fingerprint for item in self.segment_outcomes):
            raise ValueError("predicate inventory preparation fingerprint must join every lane outcome")
        route_order = {route.segment_id: index for index, route in enumerate(routes)}
        if self.candidates != tuple(sorted(self.candidates, key=lambda item: (route_order.get(item.segment_id, -1), item.lexical_anchor_span.reference_digest, item.predicate_family, item.candidate_digest))):
            raise ValueError("predicate candidates must be canonical")
        outcomes = {item.segment_id: item for item in self.segment_outcomes}
        _validate_selected_lane_outcomes(routes, self.segment_outcomes)
        if any(candidate.preparation_fingerprint != self.preparation_fingerprint or candidate.segment_id not in outcomes or candidate.segment_language_route_digest != next(route.route_digest for route in routes if route.segment_id == candidate.segment_id) or outcomes[candidate.segment_id].preparation_fingerprint != self.preparation_fingerprint or outcomes[candidate.segment_id].artifact_digest is None or candidate.detection_manifest_fingerprint != outcomes[candidate.segment_id].selected_manifest_digest for candidate in self.candidates):
            raise ValueError("predicate candidates must join their artifact-bearing route outcome")
        for candidate in self.candidates:
            route = next(route for route in routes if route.segment_id == candidate.segment_id)
            _validate_route_span(candidate.lexical_anchor_span, route, self.source_id)
            for span in candidate.morphology_evidence_spans:
                _validate_route_span(span, route, self.source_id)
        if any(
            candidate.morphology_evidence_spans != tuple(sorted(candidate.morphology_evidence_spans, key=lambda span: span.reference_digest))
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
        identity = {name: getattr(self, name) for name in ("segment_id", "preparation_fingerprint", "segment_language_route_digest", "source_span", "value_kind", "normalized_interval", "normalized_duration", "grain", "locale", "timezone", "reference_evidence", "resolver_rule_id")}
        if self.candidate_id != contract_digest(b"memorii.semantic-ingestion.resolved-temporal-candidate-identity.v1", identity):
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
        if self.source_id != self.segment_language_routes.source_id or self.source_digest != self.segment_language_routes.source_digest:
            raise ValueError("temporal resolution source must match route set")
        if tuple((item.lane, item.segment_id) for item in self.segment_outcomes) != tuple(("temporal_resolution", route.segment_id) for route in routes):
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
            or candidate.segment_language_route_digest
            != route_by_segment[candidate.segment_id].route_digest
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
        keys = [(candidate.source_span.reference_digest if hasattr(candidate.source_span, "reference_digest") else candidate.source_span.span_digest, candidate.value_kind, candidate.normalized_interval, candidate.normalized_duration, candidate.grain, candidate.locale, candidate.timezone, candidate.reference_evidence) for candidate in self.candidates]
        if len(set(map(repr, keys))) != len(keys):
            raise ValueError("temporal resolution candidates must have unique value and basis")
        route_order = {route.segment_id: index for index, route in enumerate(routes)}
        if self.candidates != tuple(sorted(self.candidates, key=lambda item: (route_order.get(item.segment_id, -1), item.source_span.reference_digest, item.candidate_digest))):
            raise ValueError("temporal candidates must be canonical")
        expected_ambiguous = tuple(sorted({candidate.source_span for candidate in self.candidates if sum(other.source_span == candidate.source_span for other in self.candidates) > 1}, key=lambda item: item.reference_digest))
        if self.ambiguous_spans != expected_ambiguous:
            raise ValueError("temporal ambiguous spans must be derived from retained candidates")
        return self
SourceSemanticContext.model_rebuild()
SegmentLanguageRoute.model_rebuild()
_ContractModel = TypeVar("_ContractModel", bound=BaseModel)
_CONTRACT_KINDS: dict[type[BaseModel], str] = {
    SemanticTerminalOutcome: "semantic_terminal",
    SemanticAuthorizationReadSet: "authorization_read_set",
    SemanticLifecycleTransition: "lifecycle_transition",
    SemanticRetryableProgress: "retryable_progress",
    SemanticExecutionRetryPlan: "execution_retry_plan",
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
    ProposalCoverageAudit: "proposal_coverage_audit",
    OperationAlignment: "operation_alignment",
    SourceProposalAlignment: "source_proposal_alignment",
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
    SemanticProposalRequest: "semantic_proposal_request",
    SemanticProposalRequestArtifact: "semantic_proposal_request_artifact",
    SemanticProposalResponseArtifact: "semantic_proposal_response_artifact",
    SemanticProposalAttemptIdentity: "semantic_proposal_attempt_identity",
    SemanticProposalAttempt: "semantic_proposal_attempt",
    SegmentProposalOutcome: "segment_proposal_outcome",
    SemanticProposalRun: "semantic_proposal_run",
    LinguisticFeature: "linguistic_feature",
    LinguisticToken: "linguistic_token",
    DependencyArc: "dependency_arc",
    SourceMention: "source_mention",
    ClauseArgument: "clause_argument",
    ClauseQuotationEvidence: "clause_quotation_evidence",
    ClauseAnalysis: "clause_analysis",
    SegmentLanguageLaneOutcome: "segment_language_lane_outcome",
    LinguisticAnalysis: "linguistic_analysis",
    SegmentLinguisticAnalysisBundle: "segment_linguistic_analysis_bundle",
    LinguisticAnalysisBundle: "linguistic_analysis_bundle",
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
    ConsensusPolicySelectionBundle: "consensus_policy_selection_bundle",
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


def encode_semantic_contract(value: BaseModel) -> bytes:
    """Encode one active semantic ingestion contract with no legacy/upcast fallback."""
    kind = _CONTRACT_KINDS.get(type(value))
    if kind is None:
        raise SemanticContractCodecError(f"unsupported semantic ingestion contract type: {type(value).__name__}")
    # Revalidation makes forged model_copy/model_construct instances fail closed.
    try:
        validated = type(value).model_validate(_restore_closed_wire_enums(canonical_contract_value(value)))
    except (TypeError, ValueError) as exc:
        raise SemanticContractCodecError("semantic ingestion contract validation failed") from exc
    payload = canonical_contract_value(validated)
    return encode_typed_value(
        {"schema": "memorii.semantic-ingestion.contract-envelope.v1", "kind": kind, "payload": payload}
    )


def decode_semantic_contract(raw: bytes, expected_type: type[_ContractModel]) -> _ContractModel:
    """Decode only exact active bytes; pre-closure and unknown variants reject."""
    expected_kind = _CONTRACT_KINDS.get(expected_type)
    if expected_kind is None:
        raise SemanticContractCodecError(f"unsupported semantic ingestion contract type: {expected_type.__name__}")
    try:
        decoded = decode_typed_value(raw)
        if not isinstance(decoded, dict) or set(decoded) != {"schema", "kind", "payload"}:
            raise SemanticContractCodecError("semantic ingestion contract envelope is not closed")
        if decoded["schema"] != "memorii.semantic-ingestion.contract-envelope.v1" or decoded["kind"] != expected_kind:
            raise SemanticContractCodecError("legacy or mismatched semantic ingestion contract variant")
        return expected_type.model_validate(_restore_closed_wire_enums(decoded["payload"]))
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SemanticContractCodecError):
            raise
        raise SemanticContractCodecError("semantic ingestion contract validation failed") from exc


def _restore_closed_wire_enums(value: object) -> object:
    """Restore the one strict enum lowered by the generic CTV codec."""
    if isinstance(value, dict):
        return {
            key: SourceModality(item)
            if key == "modality" and isinstance(item, str)
            else ClaimValueType(item)
            if key == "object_literal_type" and isinstance(item, str)
            else ExtractionTriggerMode(item)
            if key == "trigger_mode" and isinstance(item, str)
            else _restore_closed_wire_enums(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_restore_closed_wire_enums(item) for item in value)
    if isinstance(value, list):
        return [_restore_closed_wire_enums(item) for item in value]
    return value


__all__ = [
    "AcceptedTemporalEvidence",
    "ActionRevision",
    "AnalyzerScopeInterpretation",
    "AnalyzerTemporalAttachment",
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
    "SourceLocalIdentityResolution",
    "CoveredPredicateEvent",
    "UnresolvedPredicateEvent",
    "PredicateEventDisposition",
    "ProposalCoverageAudit",
    "OperationAlignment",
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
    "SemanticProposalRequest",
    "SemanticProposalRequestArtifact",
    "SemanticProposalResponseArtifact",
    "SemanticProposalAttemptIdentity",
    "SemanticProposalAttempt",
    "SegmentProposalOutcome",
    "SemanticProposalRun",
    "LinguisticFeature",
    "LinguisticToken",
    "DependencyArc",
    "SourceMention",
    "ClauseArgument",
    "ClauseQuotationEvidence",
    "ClauseAnalysis",
    "SegmentLanguageLaneOutcome",
    "LinguisticAnalysis",
    "SegmentLinguisticAnalysisBundle",
    "LinguisticAnalysisBundle",
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
    "ConsensusPolicySelectionBundle",
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
    "SourceProposalAlignment",
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
    "decode_semantic_contract",
    "encode_semantic_contract",
]


