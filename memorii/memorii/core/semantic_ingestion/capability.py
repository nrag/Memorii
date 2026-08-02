"""Host-owned semantic ingestion runtime capability and externally verified deployment authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.bootstrap_profile import VerifiedBootstrapProfile
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionStore
from memorii.core.semantic_ingestion.contracts import (
    SemanticCandidateAssessor,
    SemanticPipelinePolicyProvider,
    contract_digest,
)
from memorii.core.semantic_ingestion.egress import EgressPolicyProvider
from memorii.core.semantic_ingestion.local_analyzer import (
    LocalSemanticProposalProducer,
    ProductionLocalSemanticAnalyzer,
)
from memorii.core.semantic_ingestion.pipeline import SemanticIngestionPipeline


class SemanticDeploymentAuthorizationUse(BaseModel):
    profile_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_bootstrap_release_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    use_point: Literal["activation", "stage_start", "post_response", "pre_seal", "pre_commit"]
    use_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_use(self) -> SemanticDeploymentAuthorizationUse:
        body = self.model_dump(mode="python", exclude={"use_digest"})
        if self.use_digest != contract_digest(b"memorii.semantic-ingestion.deployment-authorization-use.v1", body):
            raise ValueError("semantic deployment authorization use digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        profile: VerifiedBootstrapProfile,
        use_point: Literal["activation", "stage_start", "post_response", "pre_seal", "pre_commit"],
    ) -> SemanticDeploymentAuthorizationUse:
        body = {
            "profile_manifest_digest": profile.artifacts.profile_manifest.profile_digest,
            "verified_bootstrap_release_digest": profile.verification_digest,
            "use_point": use_point,
        }
        return cls(
            **body,
            use_digest=contract_digest(b"memorii.semantic-ingestion.deployment-authorization-use.v1", body),
        )


class SemanticIngestionRuntimeAuthorization(BaseModel):
    """Verifier output; callers cannot manufacture activation from builder strings."""

    authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_profile_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_bootstrap_release_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_epoch: int = Field(ge=1)
    expires_at: datetime
    signer_id: str = Field(min_length=1)
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_decision(self) -> SemanticIngestionRuntimeAuthorization:
        if self.expires_at.utcoffset() is None:
            raise ValueError("semantic deployment authorization expiry must be timezone-aware")
        body = self.model_dump(mode="python", exclude={"decision_digest"})
        if self.decision_digest != contract_digest(b"memorii.semantic-ingestion.verified-deployment-authorization.v1", body):
            raise ValueError("verified semantic deployment authorization digest mismatch")
        return self


class SemanticDeploymentAuthorizationVerifier(Protocol):
    """External signature, signer lifecycle, epoch, expiry, and revocation port."""

    def verify(
        self,
        *,
        authorization_bytes: bytes,
        use: SemanticDeploymentAuthorizationUse,
        server_time: datetime,
    ) -> SemanticIngestionRuntimeAuthorization | None: ...


@dataclass(frozen=True)
class AuthorizedSemanticIngestionRuntime:
    authorization_bytes: bytes
    authorization_verifier: SemanticDeploymentAuthorizationVerifier
    pipeline: SemanticIngestionPipeline
    policy_provider: SemanticPipelinePolicyProvider
    egress_policy_provider: EgressPolicyProvider | None
    candidate_assessor: SemanticCandidateAssessor
    local_proposal_producer: LocalSemanticProposalProducer | None = None
    writer_admission: SemanticWriterAdmissionStore | None = None
    atomic_store: SemanticIngestionAtomicStore | None = None

    def verify_authorization(
        self,
        *,
        profile: VerifiedBootstrapProfile,
        use_point: Literal["activation", "stage_start", "post_response", "pre_seal", "pre_commit"],
        server_time: datetime,
    ) -> SemanticIngestionRuntimeAuthorization | None:
        if not self.authorization_bytes or server_time.utcoffset() is None:
            return None
        decision = self.authorization_verifier.verify(
            authorization_bytes=bytes(self.authorization_bytes),
            use=SemanticDeploymentAuthorizationUse.create(profile=profile, use_point=use_point),
            server_time=server_time,
        )
        if decision is None:
            return None
        try:
            verified = SemanticIngestionRuntimeAuthorization.model_validate(
                decision.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            return None
        if (
            verified.authorization_digest != sha256(self.authorization_bytes).hexdigest()
            or
            verified.target_profile_manifest_digest
            != profile.artifacts.profile_manifest.profile_digest
            or verified.verified_bootstrap_release_digest != profile.verification_digest
            or verified.expires_at <= server_time
        ):
            return None
        return verified

    def validate(self, *, profile: VerifiedBootstrapProfile, server_time: datetime) -> None:
        if self.verify_authorization(
            profile=profile, use_point="activation", server_time=server_time
        ) is None:
            raise ValueError("semantic runtime deployment authorization is unavailable")
        if (self.writer_admission is None) != (self.atomic_store is None):
            raise ValueError("semantic runtime writer and atomic store must be supplied together")


class HostSemanticIngestionRuntimeBuilder(Protocol):
    """Structural protocol implemented only by the installed host capability."""

    def build_semantic_ingestion_runtime(
        self, *, memory_plane: object, now_provider: Callable[[], datetime],
    ) -> AuthorizedSemanticIngestionRuntime | None:
        ...


def build_authorized_local_semantic_runtime(
    *,
    authorization_bytes: bytes,
    authorization_verifier: SemanticDeploymentAuthorizationVerifier,
    policy_provider: SemanticPipelinePolicyProvider,
    writer_admission: SemanticWriterAdmissionStore | None = None,
    atomic_store: SemanticIngestionAtomicStore | None = None,
) -> AuthorizedSemanticIngestionRuntime:
    """Build the ordinary zero-egress production semantic ingestion composition."""

    analyzer = ProductionLocalSemanticAnalyzer()
    return AuthorizedSemanticIngestionRuntime(
        authorization_bytes=authorization_bytes,
        authorization_verifier=authorization_verifier,
        pipeline=SemanticIngestionPipeline(transport=None),
        policy_provider=policy_provider,
        egress_policy_provider=None,
        candidate_assessor=analyzer,
        local_proposal_producer=analyzer,
        writer_admission=writer_admission,
        atomic_store=atomic_store,
    )


__all__ = [
    "AuthorizedSemanticIngestionRuntime",
    "HostSemanticIngestionRuntimeBuilder",
    "SemanticDeploymentAuthorizationUse",
    "SemanticDeploymentAuthorizationVerifier",
    "SemanticIngestionRuntimeAuthorization",
    "build_authorized_local_semantic_runtime",
]
