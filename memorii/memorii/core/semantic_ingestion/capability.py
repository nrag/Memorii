"""Host-owned semantic ingestion runtime capability and externally verified deployment authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.atomic_store import (
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.bootstrap_profile import VerifiedBootstrapProfile
from memorii.core.memory_evolution.conflict_attention import (
    AgentClarificationProposal,
    ClarificationFailureClass,
    ConflictClarificationAttemptResult,
    ConflictClarificationClaim,
    ConflictClarificationProcessingReceipt,
    ConflictClarificationSemanticPipeline,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    ClarificationPipelineError,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticConflictAuthorityAdministrationGrant,
    SemanticWriterAdmissionStore,
)
from memorii.core.memory_plane.store import MemoryPlaneRevisionConflictError
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSetProvider,
    SemanticCandidate,
    SemanticCandidateAssessor,
    SemanticPipelinePolicyProvider,
    SourceAuthorityEvidence,
    contract_digest,
)
from memorii.core.semantic_ingestion.egress import EgressPolicyProvider
from memorii.core.semantic_ingestion.local_analyzer import (
    LocalSemanticProposalProducer,
    ProductionLocalSemanticAnalyzer,
)
from memorii.core.semantic_ingestion.pipeline import SemanticIngestionPipeline


@dataclass(frozen=True)
class ConflictClarificationSemanticContext:
    """Host-resolved ordinary semantic-ingestion inputs for one clarification."""

    source_id: str
    source_digest: str
    source_text: str
    policy_bundle: SemanticArbitrationPolicyBundle
    source_authority_evidence: SourceAuthorityEvidence
    authorization_read_set_provider: SemanticAuthorizationReadSetProvider
    independent_assessor: SemanticCandidateAssessor
    local_proposals: tuple[SemanticCandidate, ...]
    source_interval_evidence: AuthenticatedSourceIntervalEvidence | None = None
    current_time_provider: Callable[[], datetime] | None = None


class ConflictClarificationSemanticContextProvider(Protocol):
    def resolve_context(
        self, proposal: AgentClarificationProposal
    ) -> ConflictClarificationSemanticContext | None: ...


class ConflictClarificationSemanticPipelineAdapter:
    """Production adapter to the atomic semantic transaction/receipt owner."""

    def __init__(
        self,
        atomic_store: SemanticIngestionAtomicStore,
        semantic_pipeline: SemanticIngestionPipeline | None = None,
        context_provider: ConflictClarificationSemanticContextProvider | None = None,
    ) -> None:
        self._store = atomic_store
        self._semantic_pipeline = semantic_pipeline or SemanticIngestionPipeline(
            transport=None
        )
        self._context_provider = context_provider

    def resolve_processing_receipt(
        self, processing_operation_id: str
    ) -> ConflictClarificationProcessingReceipt | None:
        return self._store.resolve_conflict_clarification_receipt(processing_operation_id)

    def process_clarification(
        self,
        proposal: AgentClarificationProposal,
        *,
        processing_operation_id: str,
        policy_fingerprint: str,
        current_claim: Callable[[], ConflictClarificationClaim],
    ) -> ConflictClarificationProcessingReceipt | ConflictClarificationAttemptResult:
        def commit(
            *,
            committed_outcome: Literal["accepted", "rejected", "insufficient"],
            semantic_result_digest: str,
            semantic_terminal=None,
        ) -> ConflictClarificationProcessingReceipt | ConflictClarificationAttemptResult:
            # Do this at the commit boundary, not at pipeline invocation: a
            # heartbeat may have advanced the fenced work revision meanwhile.
            claim = current_claim()
            if claim.proposal != proposal or claim.work.processing_operation_id != processing_operation_id:
                raise ClarificationPipelineError(ClarificationFailureClass.TERMINAL)
            clarification_cas = self._store.build_conflict_clarification_cas_input(claim)
            resulting_conflict_revision = contract_digest(
                b"memorii.conflict-clarification-semantic-result.v1",
                {
                    "submitted_pointer_revision": clarification_cas.expected_pointer_revision,
                    "submitted_conflict_revision": clarification_cas.expected_conflict_revision,
                    "proposal_digest": proposal.proposal_digest,
                    "processing_operation_id": processing_operation_id,
                    "committed_outcome": committed_outcome,
                    "semantic_result_digest": semantic_result_digest,
                },
            )
            return self._store.commit_conflict_clarification_transaction(
                proposal=proposal,
                processing_operation_id=processing_operation_id,
                resulting_conflict_revision=resulting_conflict_revision,
                policy_fingerprint=policy_fingerprint,
                committed_outcome=committed_outcome,
                semantic_result_digest=semantic_result_digest,
                semantic_terminal=semantic_terminal,
                clarification_cas=clarification_cas,
            )
        try:
            context = (
                self._context_provider.resolve_context(proposal)
                if self._context_provider is not None
                else None
            )
            if context is None:
                return commit(
                    committed_outcome="insufficient",
                    semantic_result_digest=contract_digest(
                        b"memorii.conflict-clarification-insufficient.v1",
                        {
                            "proposal_digest": proposal.proposal_digest,
                            "source_user_event_digest": proposal.source_user_event_digest,
                        },
                    ),
                )
            if (
                context.source_id != proposal.source_user_event_id
                or context.source_digest != proposal.source_user_event_digest
            ):
                raise ClarificationPipelineError(ClarificationFailureClass.TERMINAL)
            terminal = self._semantic_pipeline.run(
                operation_id=processing_operation_id,
                source_id=context.source_id,
                source_digest=context.source_digest,
                source_text=context.source_text,
                policy_bundle=context.policy_bundle,
                source_authority_evidence=context.source_authority_evidence,
                source_interval_evidence=context.source_interval_evidence,
                authorization_read_set_provider=(
                    context.authorization_read_set_provider
                ),
                independent_assessor=context.independent_assessor,
                local_proposals=context.local_proposals,
                current_time_provider=context.current_time_provider,
            )
            committed_outcome: Literal["accepted", "rejected", "insufficient"]
            if terminal.status == "accepted":
                committed_outcome = "accepted"
            elif terminal.status == "rejected":
                committed_outcome = "rejected"
            else:
                committed_outcome = "insufficient"
            return commit(
                committed_outcome=committed_outcome,
                semantic_result_digest=terminal.terminal_digest,
                semantic_terminal=terminal,
            )
        except ClarificationPipelineError:
            raise
        except (MemoryPlaneRevisionConflictError, OSError, TimeoutError) as exc:
            raise ClarificationPipelineError(
                ClarificationFailureClass.RETRYABLE
            ) from exc
        except PreplanningStoreError as exc:
            reason = str(exc)
            failure_class = (
                ClarificationFailureClass.RETRYABLE
                if (
                    "contention" in reason
                    or "race" in reason
                    or "stale" in reason
                )
                else ClarificationFailureClass.TERMINAL
            )
            raise ClarificationPipelineError(failure_class) from exc


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
            profile_manifest_digest=body["profile_manifest_digest"],
            verified_bootstrap_release_digest=body[
                "verified_bootstrap_release_digest"
            ],
            use_point=use_point,
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
    conflict_clarification_context_provider: (
        ConflictClarificationSemanticContextProvider | None
    ) = None
    conflict_clarification_pipeline: ConflictClarificationSemanticPipeline | None = None
    _conflict_authority_administration_grant: (
        SemanticConflictAuthorityAdministrationGrant | None
    ) = field(default=None, init=False, repr=False, compare=False)

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
        if (
            self.atomic_store is not None
            and not self.atomic_store.has_replay_integrity_composition
        ):
            raise ValueError("semantic runtime atomic store has no replay integrity authority")
        if self.atomic_store is not None and self.writer_admission is not None:
            grant = self.writer_admission._claim_conflict_authority_administration(
                owner=self
            )
            object.__setattr__(
                self, "_conflict_authority_administration_grant", grant
            )
            binding = self.writer_admission.commit_binding(
                self.writer_admission.current()
            )
            self.atomic_store.bootstrap_reference_integrity(writer_binding=binding)

    def conflict_authority_administration_grant(
        self,
    ) -> SemanticConflictAuthorityAdministrationGrant:
        grant = self._conflict_authority_administration_grant
        if grant is None:
            raise ValueError(
                "semantic runtime is not verified for conflict authority administration"
            )
        return grant


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
    conflict_clarification_context_provider: (
        ConflictClarificationSemanticContextProvider | None
    ) = None,
    identity_operation_resolver: object | None = None,
    identity_decision_authority_verifier: object | None = None,
) -> AuthorizedSemanticIngestionRuntime:
    """Build the ordinary zero-egress production semantic ingestion composition."""

    analyzer = ProductionLocalSemanticAnalyzer()
    identity_lineage_compiler = None
    identity_operation_planner = None
    if atomic_store is not None:
        from memorii.core.memory_evolution.identity_lineage import (
            AtomicStoreAcceptedIdentityOperationPlanner,
            ProductionIdentityLineageCompiler,
            TrustedAcceptedIdentityOperationResolver,
            TrustedIdentityDecisionAuthorityVerifier,
        )
        from memorii.core.memory_evolution.transaction_coordinator import (
            SemanticIngestionTransactionCoordinator,
        )

        coordinator = SemanticIngestionTransactionCoordinator(atomic_store)
        identity_lineage_compiler = ProductionIdentityLineageCompiler(
            coordinator,
            atomic_store,
        )
        identity_capabilities = (
            identity_operation_resolver,
            identity_decision_authority_verifier,
        )
        if any(value is not None for value in identity_capabilities) and not all(
            value is not None for value in identity_capabilities
        ):
            raise ValueError("identity operation authority composition is incomplete")
        if identity_operation_resolver is not None:
            if writer_admission is None:
                raise ValueError("identity operation planner requires writer authority")
            if not callable(
                getattr(
                    identity_operation_resolver,
                    "resolve_accepted_identity_operation",
                    None,
                )
            ) or not callable(
                getattr(
                    identity_decision_authority_verifier,
                    "verify_identity_decision_authority",
                    None,
                )
            ):
                raise ValueError("identity operation authority capability is invalid")
            if (
                atomic_store.identity_decision_authority_verifier
                is not identity_decision_authority_verifier
            ):
                raise ValueError(
                    "identity operation authority verifier is not store-owned"
                )
            identity_operation_planner = AtomicStoreAcceptedIdentityOperationPlanner(
                coordinator,
                atomic_store,
                writer_admission,
                cast(TrustedAcceptedIdentityOperationResolver, identity_operation_resolver),
                cast(
                    TrustedIdentityDecisionAuthorityVerifier,
                    atomic_store.identity_decision_authority_verifier,
                ),
            )
    pipeline = SemanticIngestionPipeline(
        transport=None,
        identity_lineage_compiler=identity_lineage_compiler,
        identity_operation_planner=identity_operation_planner,
    )
    return AuthorizedSemanticIngestionRuntime(
        authorization_bytes=authorization_bytes,
        authorization_verifier=authorization_verifier,
        pipeline=pipeline,
        policy_provider=policy_provider,
        egress_policy_provider=None,
        candidate_assessor=analyzer,
        local_proposal_producer=analyzer,
        writer_admission=writer_admission,
        atomic_store=atomic_store,
        conflict_clarification_context_provider=(
            conflict_clarification_context_provider
        ),
        conflict_clarification_pipeline=(
            ConflictClarificationSemanticPipelineAdapter(
                atomic_store,
                semantic_pipeline=pipeline,
                context_provider=conflict_clarification_context_provider,
            )
            if atomic_store is not None
            and conflict_clarification_context_provider is not None
            else None
        ),
    )


__all__ = [
    "AuthorizedSemanticIngestionRuntime",
    "ConflictClarificationSemanticContext",
    "ConflictClarificationSemanticContextProvider",
    "ConflictClarificationSemanticPipelineAdapter",
    "HostSemanticIngestionRuntimeBuilder",
    "SemanticDeploymentAuthorizationUse",
    "SemanticDeploymentAuthorizationVerifier",
    "SemanticIngestionRuntimeAuthorization",
    "build_authorized_local_semantic_runtime",
]
