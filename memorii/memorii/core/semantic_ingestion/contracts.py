"""Closed, content-addressed contracts shared by the semantic ingestion ingestion pipeline.

This module is deliberately a dependency leaf.  Candidate validation,
operation sealing, durable carrier compilation, provider orchestration, and
writer-safe preplanning persistence all consume these types; none of the types imports those
services back.  That makes the accepted/non-accepted boundary auditable and
keeps replay execution outside semantic ingestion.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Annotated, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    OperationFenceBinding,
    decode_typed_value,
    encode_typed_value,
)


def canonical_contract_value(value: object) -> object:
    """Lower nested Pydantic values before entering the closed CTV codec."""
    if isinstance(value, BaseModel):
        return canonical_contract_value(value.model_dump(mode="python"))
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


class TimeInterval(BaseModel):
    start: datetime
    end: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_interval(self) -> TimeInterval:
        if self.end is not None and self.end <= self.start:
            raise ValueError("interval end must be later than start")
        return self


class SourceAuthority(BaseModel):
    authority_class: str = Field(min_length=1)
    authenticated_provenance_class: str = Field(min_length=1)
    governing_principal_id: str | None = None
    policy_revision: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


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


class PredicateTrustRule(BaseModel):
    predicate_id: str = Field(min_length=1)
    eligible_authority_classes: frozenset[str]
    authority_rank_by_class: Mapping[str, int]
    incomparable_class_pairs: tuple[tuple[str, str], ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_rule(self) -> PredicateTrustRule:
        if not self.eligible_authority_classes.issubset(self.authority_rank_by_class):
            raise ValueError("each eligible authority class requires a rank")
        pairs = tuple(tuple(sorted(pair)) for pair in self.incomparable_class_pairs)
        if any(len(pair) != 2 or pair[0] == pair[1] for pair in pairs):
            raise ValueError("incomparable authority pair must contain two distinct classes")
        if self.incomparable_class_pairs != pairs or tuple(sorted(set(pairs))) != pairs:
            raise ValueError("incomparable authority pairs must be canonical")
        if any(not set(pair).issubset(self.eligible_authority_classes) for pair in pairs):
            raise ValueError("incomparable authority pair references an ineligible class")
        return self


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
        body = self.model_dump(mode="python", exclude={"snapshot_digest"})
        if self.snapshot_digest != contract_digest(b"memorii.semantic-ingestion.trust-policy-snapshot.v1", body):
            raise ValueError("trust policy snapshot digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, policy_revision: str, system_effective_interval: TimeInterval,
        rules: tuple[PredicateTrustRule, ...],
    ) -> TrustPolicySnapshot:
        fingerprint = contract_digest(b"memorii.semantic-ingestion.trust-policy-rules.v1", rules)
        body = {
            "schema_id": "memorii.semantic_ingestion.trust_policy", "schema_version": 1,
            "policy_revision": policy_revision, "system_effective_interval": system_effective_interval,
            "fingerprint": fingerprint, "rules": rules,
        }
        return cls(**body, snapshot_digest=contract_digest(b"memorii.semantic-ingestion.trust-policy-snapshot.v1", body))

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
        body = self.model_dump(mode="python", exclude={"snapshot_digest"})
        if self.snapshot_digest != contract_digest(b"memorii.semantic-ingestion.temporal-policy-snapshot.v1", body):
            raise ValueError("temporal policy snapshot digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, policy_revision: str, system_effective_interval: TimeInterval,
        rules: tuple[PredicateTemporalRule, ...],
    ) -> TemporalPolicySnapshot:
        fingerprint = contract_digest(b"memorii.semantic-ingestion.temporal-policy-rules.v1", rules)
        body = {
            "schema_id": "memorii.semantic_ingestion.temporal_policy", "schema_version": 1,
            "policy_revision": policy_revision, "system_effective_interval": system_effective_interval,
            "fingerprint": fingerprint, "rules": rules,
        }
        return cls(**body, snapshot_digest=contract_digest(b"memorii.semantic-ingestion.temporal-policy-snapshot.v1", body))

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
        body = self.model_dump(mode="python", exclude={"bundle_digest"})
        if self.bundle_digest != contract_digest(b"memorii.semantic-ingestion.arbitration-policy-bundle.v1", body):
            raise ValueError("arbitration policy bundle digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, trust_policy: TrustPolicySnapshot, temporal_policy: TemporalPolicySnapshot,
        arbitration_as_of: datetime,
    ) -> SemanticArbitrationPolicyBundle:
        body = {
            "trust_policy": trust_policy, "temporal_policy": temporal_policy,
            "arbitration_as_of": arbitration_as_of,
        }
        return cls(**body, bundle_digest=contract_digest(b"memorii.semantic-ingestion.arbitration-policy-bundle.v1", body))


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
        if len({
            self.egress_policy_revision is None,
            self.egress_decision_digest is None,
            self.egress_binding is None,
        }) != 1:
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
    "pre_request", "post_response", "pre_analysis", "pre_seal", "pre_commit",
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
        if any(value is None for value in egress_values) != all(
            value is None for value in egress_values
        ):
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
                raise ValueError(
                    "authorization snapshot egress decision coordinates are invalid"
                )
        if self.deployment_expires_at <= self.server_now or (
            self.egress_expires_at is not None and self.egress_expires_at <= self.server_now
        ):
            raise ValueError("authorization snapshot contains expired authority")
        body = self.model_dump(mode="python", exclude={"snapshot_digest"})
        if self.snapshot_digest != contract_digest(
            b"memorii.semantic-ingestion.authorization-stage-snapshot.v1", body
        ):
            raise ValueError("authorization stage snapshot digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> AuthorizationStageSnapshot:
        return cls(
            **values,
            snapshot_digest=contract_digest(
                b"memorii.semantic-ingestion.authorization-stage-snapshot.v1", values
            ),
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
                if self.candidates or selected or self.resolved_interval is None or self.resolved_interval.end is not None:
                    raise ValueError("reference-open-start closure requires only an open resolved interval")
            else:
                if not selected or self.resolved_interval is None:
                    raise ValueError("trust-selected pass closure requires selected asserted interval")
                if any(by_id[candidate_id].interval != self.resolved_interval for candidate_id in selected):
                    raise ValueError("selected temporal candidates must equal the resolved interval")
        elif self.outcome == "contested":
            if not contested or selected or self.resolved_interval is not None or self.resolution_rule != "trust_contested_nonidentical_top_evidence":
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


class AnalyzerRoleInterpretation(BaseModel):
    analyzer_id: str = Field(min_length=1)
    analyzer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_span: SourceSpan
    construction_family: str = Field(min_length=1)
    role_spans: tuple[tuple[str, SourceSpan], ...]
    semantic_scope: Literal["asserted", "negated", "question", "instruction"]
    attribution_kind: Literal["speaker", "quoted_or_reported_source"]
    attribution_bearer_span: SourceSpan | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_interpretation(self) -> AnalyzerRoleInterpretation:
        ids = tuple(role_id for role_id, _ in self.role_spans)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("role IDs must be ordered and unique")
        spans = (self.predicate_span, *(span for _, span in self.role_spans))
        if len({span.source_id for span in spans}) != 1:
            raise ValueError("analyzer spans must belong to one source")
        if self.attribution_kind == "speaker" and self.attribution_bearer_span is not None:
            raise ValueError("speaker attribution has no source bearer span")
        if self.attribution_kind == "quoted_or_reported_source" and self.attribution_bearer_span is None:
            raise ValueError("reported attribution requires a source bearer span")
        if self.attribution_bearer_span is not None and self.attribution_bearer_span.source_id != self.predicate_span.source_id:
            raise ValueError("attribution bearer must belong to the analyzed source")
        return self


class ParserConsensusAssessment(BaseModel):
    primary: AnalyzerRoleInterpretation
    corroborating: AnalyzerRoleInterpretation
    status: Literal["stable", "unresolved"]
    assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_assessment(self) -> ParserConsensusAssessment:
        if self.primary.analyzer_id == self.corroborating.analyzer_id or self.primary.analyzer_fingerprint == self.corroborating.analyzer_fingerprint:
            raise ValueError("consensus requires independently identified analyzers")
        expected_status = "stable" if self._equivalent(self.primary, self.corroborating) else "unresolved"
        if self.status != expected_status:
            raise ValueError("parser consensus status is not reproducible")
        body = self.model_dump(mode="python", exclude={"assessment_digest"})
        if self.assessment_digest != contract_digest(b"memorii.semantic-ingestion.parser-consensus.v1", body):
            raise ValueError("parser consensus digest mismatch")
        return self

    @classmethod
    def create(cls, *, primary: AnalyzerRoleInterpretation, corroborating: AnalyzerRoleInterpretation) -> ParserConsensusAssessment:
        stable = cls._equivalent(primary, corroborating)
        body = {"primary": primary, "corroborating": corroborating, "status": "stable" if stable else "unresolved"}
        return cls(**body, assessment_digest=contract_digest(b"memorii.semantic-ingestion.parser-consensus.v1", body))

    @staticmethod
    def _equivalent(left: AnalyzerRoleInterpretation, right: AnalyzerRoleInterpretation) -> bool:
        return (
            left.predicate_span == right.predicate_span
            and left.construction_family == right.construction_family
            and left.role_spans == right.role_spans
            and left.semantic_scope == right.semantic_scope
            and left.attribution_kind == right.attribution_kind
            and left.attribution_bearer_span == right.attribution_bearer_span
        )


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
        cls, *, operation_id: str, temporal_role: TemporalRole,
        stable_attachment_consensus_digest: str, candidate_ids: tuple[str, ...],
        candidate_spans: tuple[SourceSpan, ...],
    ) -> OperationTemporalAttachmentBinding:
        body = {
            "operation_id": operation_id,
            "temporal_role": temporal_role,
            "stable_attachment_consensus_digest": stable_attachment_consensus_digest,
            "candidate_ids": candidate_ids,
            "candidate_spans": candidate_spans,
        }
        return cls(**body, binding_digest=contract_digest(b"memorii.semantic-ingestion.temporal_attachment_binding.v1", body))


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
        cls, *, operation_id: str, temporal_role: TemporalRole,
        scope_assessment_digest: str, semantic_assessment_digest: str,
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
        return cls(**body, binding_digest=contract_digest(b"memorii.semantic-ingestion.temporal_decision_binding.v1", body))


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
        if self.parser_consensus.primary.predicate_span.source_id != self.source_id or (
            self.parser_consensus.corroborating.predicate_span.source_id != self.source_id
        ):
            raise ValueError("parser consensus does not belong to source analysis")
        if any(value.source_id != self.source_id for value in self.identity_evidence):
            raise ValueError("identity evidence does not belong to source analysis")
        roles = tuple(value.temporal_role for value in self.temporal_evidence)
        expected = {
            "fact": ("assertion",), "action": ("assertion",),
            "correction": ("replacement", "transition"),
            "retraction": ("transition",), "identity": ("transition",),
        }[self.operation_kind]
        if roles != expected:
            raise ValueError("source temporal roles do not match operation kind")
        if any(span.source_id != self.source_id for value in self.temporal_evidence for span in value.attachment_spans):
            raise ValueError("temporal attachment span does not belong to source analysis")
        body = self.model_dump(mode="python", exclude={"analysis_digest"})
        if self.analysis_digest != contract_digest(b"memorii.semantic-ingestion.independent-source-analysis.v1", body):
            raise ValueError("independent source analysis digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> IndependentSourceAnalysis:
        return cls.model_validate({
            **values,
            "analysis_digest": contract_digest(
                b"memorii.semantic-ingestion.independent-source-analysis.v1", values
            ),
        })

    def temporal_roles(self) -> tuple[tuple[TemporalRole, tuple[TemporalEvidenceCandidate, ...]], ...]:
        return tuple((value.temporal_role, value.candidates) for value in self.temporal_evidence)


class SealedSemanticOperation(BaseModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(min_length=1)
    kind: OperationKind
    scope_assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_bindings: tuple[OperationTemporalDecisionBinding, ...]
    sealed_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_seal(self) -> SealedSemanticOperation:
        ordered = tuple(sorted(self.temporal_bindings, key=lambda value: (value.operation_id, value.temporal_role, value.binding_digest)))
        if ordered != self.temporal_bindings or any(value.operation_id != self.operation_id for value in ordered):
            raise ValueError("sealed operation temporal bindings must be local and canonical")
        expected_roles = {
            "fact": {"assertion"}, "action": {"assertion"},
            "correction": {"replacement", "transition"},
            "retraction": {"transition"}, "identity": {"transition"},
        }[self.kind]
        if {value.temporal_role for value in ordered} != expected_roles or len(ordered) != len(expected_roles):
            raise ValueError("sealed operation has an invalid temporal role set")
        expected_scope_digest = contract_digest(
            b"memorii.semantic-ingestion.operation-scope-assessments.v1",
            tuple(value.scope_assessment_digest for value in ordered),
        )
        expected_semantic_digest = contract_digest(
            b"memorii.semantic-ingestion.operation-semantic-assessments.v1",
            tuple(value.semantic_assessment_digest for value in ordered),
        )
        if self.scope_assessment_digest != expected_scope_digest or self.semantic_assessment_digest != expected_semantic_digest:
            raise ValueError("sealed operation assessment closure mismatch")
        body = self.model_dump(mode="python", exclude={"sealed_operation_digest"})
        if self.sealed_operation_digest != contract_digest(b"memorii.semantic-ingestion.sealed-operation.v1", body):
            raise ValueError("sealed operation digest mismatch")
        return self


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
    record_version: Literal[1] = 1
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


class ActionRevision(_TemporalCarrier):
    record_kind: Literal["action_revision"] = "action_revision"
    action_revision_id: str = Field(min_length=1)
    statement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdentityLineageRecord(_TemporalCarrier):
    record_kind: Literal["identity_lineage"] = "identity_lineage"
    identity_lineage_id: str = Field(min_length=1)
    statement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class TemporalTransitionRecord(_TemporalCarrier):
    record_kind: Literal["temporal_transition"] = "temporal_transition"
    transition_kind: Literal["correction", "retraction"]
    transition_id: str = Field(min_length=1)
    statement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


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
        ordered = tuple(sorted(self.bindings, key=lambda value: (value.operation_id, value.temporal_role, value.binding_digest)))
        if ordered != self.bindings or any(value.operation_id != self.operation_id for value in ordered):
            raise ValueError("terminal bindings must be operation-local and canonical")
        if len({value.temporal_role for value in self.bindings}) != len(self.bindings):
            raise ValueError("terminal temporal roles must be unique")
        body = self.model_dump(mode="python", exclude={"binding_set_digest"})
        if self.binding_set_digest != contract_digest(b"memorii.semantic-ingestion.terminal-binding-set.v1", body):
            raise ValueError("terminal binding-set digest mismatch")
        return self

    @classmethod
    def create(cls, *, operation_id: str, bindings: tuple[OperationTemporalDecisionBinding, ...]) -> SemanticTerminalBindingSet:
        body = {"operation_id": operation_id, "bindings": bindings}
        return cls(**body, binding_set_digest=contract_digest(b"memorii.semantic-ingestion.terminal-binding-set.v1", body))


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
            self.proposal_attempt_digests, self.source_analysis_digests,
            self.sealed_operation_digests, self.egress_decision_digests,
        ):
            if any(len(value) != 64 for value in values):
                raise ValueError("semantic ingestion lineage contains a non-digest coordinate")
        body = self.model_dump(mode="python", exclude={"lineage_digest"})
        if self.lineage_digest != contract_digest(b"memorii.semantic-ingestion.execution-lineage.v1", body):
            raise ValueError("semantic ingestion execution lineage digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SemanticExecutionLineage:
        return cls.model_validate({
            **values,
            "lineage_digest": contract_digest(b"memorii.semantic-ingestion.execution-lineage.v1", values),
        })


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
                self.execution_lineage.arbitration_policy_bundle_digest
                != self.arbitration_policy_bundle.bundle_digest
            ):
                raise ValueError("accepted terminal lineage does not bind its policy or operation")
            if (
                self.authorization_read_set is None
                or self.execution_lineage.authorization_read_set_digest
                != self.authorization_read_set.read_set_digest
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
            for operation in self.sealed_operations:
                operation_carriers = tuple(
                    value.record_kind for value in self.accepted_carriers if value.operation_id == operation.operation_id
                )
                if operation_carriers != expected_kinds[operation.kind]:
                    raise ValueError("accepted terminal has the wrong carrier family for an operation")
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
                if operation.operation_id != binding_set.operation_id or operation.temporal_bindings != binding_set.bindings:
                    raise ValueError("non-accepted terminal binding set differs from its sealed operation")
            if any(
                binding.decision_closure not in self.temporal_closures
                for operation in self.sealed_operations
                for binding in operation.temporal_bindings
            ):
                raise ValueError("non-accepted terminal omitted a sealed temporal closure")
        body = self.model_dump(mode="python", exclude={"terminal_digest"})
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
        return cls(**values, terminal_digest=contract_digest(b"memorii.semantic-ingestion.semantic-terminal.v1", values))


class SemanticLifecycleTransition(BaseModel):
    """Append-only persisted transition for the protected provider lifecycle."""

    operation_id: str = Field(min_length=1)
    from_kind: Literal["selected_pipeline_pending", "accepted_candidate"]
    to_kind: Literal["accepted_candidate", "committed_terminal", "unsupported_input", "abstained"]
    candidate_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    terminal_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason_code: Literal[
        "missing_language_declaration", "untrusted_language", "language_mismatch",
        "non_english_language", "mixed_residue", "unsupported_grammar",
        "extractor_abstained", "retry_budget_exhausted",
    ] | None = None
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
            or (self.from_kind == "accepted_candidate")
            != (self.predecessor_transition_digest is not None)
        ):
            raise ValueError("nonpromoting terminal lifecycle transition is invalid")
        body = self.model_dump(mode="python", exclude={"transition_digest"})
        if self.transition_digest != contract_digest(b"memorii.semantic-ingestion.lifecycle-transition.v1", body):
            raise ValueError("semantic ingestion lifecycle transition digest mismatch")
        return self

    @classmethod
    def accepted_candidate(
        cls, *, operation_id: str, candidate_digest: str,
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
            "missing_language_declaration", "untrusted_language", "language_mismatch",
            "non_english_language", "mixed_residue", "unsupported_grammar",
            "extractor_abstained", "retry_budget_exhausted",
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
    expected_authority_coordinates_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
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
                "semantic_ingestion:authorization:"
                + sha256(scope_id.encode("utf-8")).hexdigest()
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
        expected_id = (
            "semantic_ingestion:authorization:"
            + sha256(self.authority_scope_id.encode("utf-8")).hexdigest()
        )
        if self.authority_record_id != expected_id:
            raise ValueError("recovery authority record does not bind its scope")
        body = self.model_dump(mode="python", exclude={"binding_digest"})
        if self.binding_digest != contract_digest(
            b"memorii.semantic-ingestion.recovery-authority-binding.v1", body
        ):
            raise ValueError("recovery authority binding digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SemanticRecoveryAuthorityBinding:
        return cls(
            **values,
            binding_digest=contract_digest(
                b"memorii.semantic-ingestion.recovery-authority-binding.v1", values
            ),
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
        self, *, proposal: SemanticCandidate, source_id: str, source_digest: str,
        source_text: str, source_authority_evidence: SourceAuthorityEvidence,
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
            "sealed_operation_digests": tuple(sorted(value.sealed_operation_digest for value in terminal.sealed_operations)),
            "accepted_carrier_digests": tuple(sorted(value.record_digest for value in terminal.accepted_carriers)),
            "terminal_binding_set_digests": tuple(sorted(value.binding_set_digest for value in terminal.terminal_binding_sets)),
            "execution_lineage_digest": (
                terminal.execution_lineage.lineage_digest if terminal.execution_lineage is not None else None
            ),
            "arbitration_policy_bundle_digest": (
                terminal.arbitration_policy_bundle.bundle_digest
                if terminal.arbitration_policy_bundle is not None else None
            ),
            "authorization_read_set_digest": (
                terminal.authorization_read_set.read_set_digest
                if terminal.authorization_read_set is not None else None
            ),
        }
        return cls(**body, closure_digest=contract_digest(b"memorii.semantic-ingestion.artifact-closure.v1", body))


class SemanticGraphDelta(BaseModel):
    kind: Literal["semantic_graph_delta"] = "semantic_graph_delta"
    operation_id: str
    carriers: tuple[SemanticDurableCarrier, ...]
    terminal_binding_sets: tuple[SemanticTerminalBindingSet, ...]
    delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_delta(self) -> SemanticGraphDelta:
        body = self.model_dump(mode="python", exclude={"delta_digest"})
        if not self.carriers or self.delta_digest != contract_digest(b"memorii.semantic-ingestion.graph-delta.v1", body):
            raise ValueError("semantic ingestion graph delta is incomplete or has an invalid digest")
        return self

    @classmethod
    def create(cls, terminal: SemanticTerminalOutcome) -> SemanticGraphDelta:
        if terminal.status != "accepted":
            raise ValueError("only accepted terminals produce graph deltas")
        body = {"kind": "semantic_graph_delta", "operation_id": terminal.operation_id, "carriers": terminal.accepted_carriers, "terminal_binding_sets": terminal.terminal_binding_sets}
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
    payload = canonical_contract_value(value)
    return encode_typed_value({"schema": "memorii.semantic-ingestion.contract-envelope.v1", "kind": kind, "payload": payload})


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
        return expected_type.model_validate(decoded["payload"])
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SemanticContractCodecError):
            raise
        raise SemanticContractCodecError("semantic ingestion contract validation failed") from exc


__all__ = [
    "AcceptedTemporalEvidence", "ActionRevision", "AnalyzerRoleInterpretation",
    "CandidateTransportError", "ClaimAssertion", "IdentityLineageRecord",
    "SemanticArtifactClosure", "SemanticDurableCarrier", "SemanticEventInputBatch", "SemanticGraphDelta",
    "SemanticEffectGroupResult", "SemanticObservationDelta", "OperationKind",
    "OperationTemporalAttachmentBinding", "OperationTemporalDecisionBinding",
    "ParserConsensusAssessment", "PredicateTemporalRule", "PredicateTrustRule",
    "SealedSemanticOperation", "SemanticCandidate", "SemanticContractCodecError",
    "SemanticCandidateAssessor", "SemanticPipelinePolicy", "SemanticPipelinePolicyProvider", "SemanticTerminalBindingSet",
    "SemanticTerminalOutcome", "SemanticTransport", "SourceAuthority",
    "SourceLocalIdentityEvidence", "SourceSpan", "TemporalEvidenceCandidate",
    "TemporalEvidenceDecisionClosure", "TemporalPolicySnapshot", "TemporalRole",
    "TemporalTransitionRecord", "TimeInterval", "TrustPolicySnapshot",
    "canonical_contract_value", "contract_digest", "decode_semantic_contract",
    "encode_semantic_contract",
]
