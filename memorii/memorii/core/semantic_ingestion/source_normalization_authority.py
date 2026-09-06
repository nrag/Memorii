"""Strict host-owned leaves for one source-normalization execution."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.semantic_state import PredicateStateRule
from memorii.core.semantic_ingestion.contracts import (
    BootstrapSemanticProposalRequestV3,
    BootstrapV3PayloadLimitAuthority,
    ParserConsensusPolicy,
    ScopeConsensusPolicy,
    TemporalAttachmentConsensusPolicy,
    contract_digest,
)

_DIGEST = r"^[0-9a-f]{64}$"


class ProposalRunProductionAuthority(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    preparation_fingerprint: str = Field(pattern=_DIGEST)
    route_set_digest: str = Field(pattern=_DIGEST)
    proposer_fingerprint: str = Field(pattern=_DIGEST)
    proposer_manifest_digest: str = Field(pattern=_DIGEST)
    prompt_registration_digest: str = Field(pattern=_DIGEST)
    semantic_request_fingerprint: str = Field(pattern=_DIGEST)
    action_proposal_catalog_fingerprint: str = Field(pattern=_DIGEST)
    retry_policy_fingerprint: str = Field(pattern=_DIGEST)
    authority_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> ProposalRunProductionAuthority:
        if self.authority_digest != contract_digest(
            b"memorii.semantic-ingestion.proposal-run-production-authority.v1",
            self.model_dump(mode="python", exclude={"authority_digest"}),
        ):
            raise ValueError("proposal-run production authority digest mismatch")
        return self


class BootstrapPlanningPolicyAuthority(BaseModel):
    """Host-owned graph-planning policy identity sealed before normalization."""

    predicate_registry_fingerprint: str = Field(pattern=_DIGEST)
    predicate_state_rule: PredicateStateRule
    action_policy_fingerprint: str = Field(pattern=_DIGEST)
    authority_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> BootstrapPlanningPolicyAuthority:
        if self.predicate_state_rule.predicate_id == "":
            raise ValueError("bootstrap planning predicate state rule is invalid")
        if self.authority_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-planning-policy-authority.v3",
            self.model_dump(mode="python", exclude={"authority_digest"}),
        ):
            raise ValueError("bootstrap planning policy authority digest mismatch")
        return self


class BootstrapV3RuntimeAuthority(BaseModel):
    """Transient bootstrap-only inputs required before V3 sealing.

    These values are authoritative while the call is live; persisted V3
    records retain only their closed proposal/lane payloads.
    """

    proposal_requests: tuple[BootstrapSemanticProposalRequestV3, ...]
    payload_limit_authority: BootstrapV3PayloadLimitAuthority
    authority_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> BootstrapV3RuntimeAuthority:
        requests = self.proposal_requests
        if (
            not requests
            or tuple(item.segment.segment_id for item in requests)
            != tuple(sorted(item.segment.segment_id for item in requests))
            or len({item.segment.segment_id for item in requests}) != len(requests)
            or any(
                (item.segment.source_id, item.segment.source_digest, item.segment.preparation_fingerprint)
                != (
                    self.payload_limit_authority.source_id,
                    self.payload_limit_authority.source_digest,
                    self.payload_limit_authority.preparation_fingerprint,
                )
                or item.bootstrap_analysis_provenance.proposal_capability_fingerprint
                != item.proposal_capability_fingerprint
                for item in requests
            )
        ):
            raise ValueError("bootstrap V3 runtime authority request closure is invalid")
        if self.authority_digest != contract_digest(
            b"memorii.semantic-ingestion.bootstrap-v3-runtime-authority.v3",
            self.model_dump(mode="python", exclude={"authority_digest"}),
        ):
            raise ValueError("bootstrap V3 runtime authority digest mismatch")
        return self


class ConsensusPolicyAuthority(BaseModel):
    parser_policy: ParserConsensusPolicy
    scope_policy: ScopeConsensusPolicy
    temporal_attachment_policy: TemporalAttachmentConsensusPolicy
    authority_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> ConsensusPolicyAuthority:
        if self.authority_digest != contract_digest(
            b"memorii.semantic-ingestion.consensus-policy-authority.v1",
            self.model_dump(mode="python", exclude={"authority_digest"}),
        ):
            raise ValueError("consensus policy authority digest mismatch")
        return self


class CapabilityRegistryEntry(BaseModel):
    capability_id: str = Field(min_length=1)
    capability_fingerprint: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CapabilityRegistrySnapshot(BaseModel):
    registry_revision: str = Field(min_length=1)
    capabilities: tuple[CapabilityRegistryEntry, ...]
    snapshot_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> CapabilityRegistrySnapshot:
        keys = tuple((entry.capability_id, entry.capability_fingerprint) for entry in self.capabilities)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("capability registry entries must be canonical and unique")
        if self.snapshot_digest != contract_digest(
            b"memorii.semantic-ingestion.capability-registry-snapshot.v2",
            self.model_dump(mode="python", exclude={"snapshot_digest"}),
        ):
            raise ValueError("capability registry snapshot digest mismatch")
        return self


class GraphDependentExecutionPolicy(BaseModel):
    policy_version: int = Field(ge=1, le=1)
    maximum_operations_per_source: int = Field(ge=1)
    maximum_groups_per_source: int = Field(ge=1)
    maximum_fixed_point_rounds: int = Field(ge=1)
    maximum_records_per_snapshot: int = Field(ge=1)
    maximum_partitions_per_snapshot: int = Field(ge=1)
    maximum_related_conflicts_per_group: int = Field(ge=1, le=1)
    maximum_attempts_per_group: int = Field(ge=1)
    maximum_read_set_extensions: int = Field(ge=1)
    maximum_reservations: int = Field(ge=1)
    maximum_lineage_entries: int = Field(ge=1)
    maximum_replay_artifacts: int = Field(ge=1)
    maximum_replay_bundle_bytes: int = Field(ge=1)
    replay_artifact_schema_registry_fingerprint: str = Field(pattern=_DIGEST)
    maximum_decode_depth: int = Field(ge=1)
    policy_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> GraphDependentExecutionPolicy:
        if self.policy_digest != contract_digest(
            b"memorii.semantic-ingestion.graph-dependent-execution-policy.v1",
            self.model_dump(mode="python", exclude={"policy_digest"}),
        ):
            raise ValueError("graph-dependent execution policy digest mismatch")
        return self


__all__ = [
    "CapabilityRegistryEntry",
    "CapabilityRegistrySnapshot",
    "ConsensusPolicyAuthority",
    "GraphDependentExecutionPolicy",
    "ProposalRunProductionAuthority",
    "BootstrapV3RuntimeAuthority",
    "BootstrapPlanningPolicyAuthority",
]
