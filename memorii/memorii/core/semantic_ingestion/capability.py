"""Host-owned semantic ingestion runtime capability and externally verified deployment authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.atomic_store import (
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    CurrentBootstrapReleaseVerifier,
    HostBootstrapMaterialPresentation,
    HostVerifiedBootstrapMaterial,
    VerifiedBootstrapProfile,
    verify_bootstrap_profile,
)
from memorii.core.memory_evolution.conflict_integrity import (
    PrivilegedSemanticIntegrityLifecycle,
)
from memorii.core.memory_evolution.ingestion_contracts import SemanticWriterCommitBinding
from memorii.core.memory_evolution.observation_activation_configuration import (
    ObservationActivationTargetConfiguration,
    ObservationActivationTargetConfigurationError,
    VerifiedObservationActivationTarget,
    resolve_verified_observation_activation_target,
)
from memorii.core.memory_evolution.typed_value_registry_configuration import (
    ProtectedTypedValueRegistryConfiguration,
    TypedValueRegistryConfigurationError,
    verify_configured_typed_value_registry_history,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticConflictAuthorityAdministrationGrant,
    SemanticWriterAdmissionStore,
)
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphHostBundle,
    BootstrapGraphHostBundleBuilder,
)
from memorii.core.semantic_ingestion.contracts import (
    SemanticPipelinePolicyProvider,
    TextPreparationPolicy,
    contract_digest,
)
from memorii.core.semantic_ingestion.source_normalization_host import (
    SourceNormalizationHostBundle,
    SourceNormalizationHostBundleBuilder,
)
from memorii.core.semantic_ingestion.source_preparation import (
    AtomicStorePreparedSourceRepository,
    PreparedSourceRepository,
    TextPreparationService,
)


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
    policy_provider: SemanticPipelinePolicyProvider
    text_preparation_service: TextPreparationService | None = None
    prepared_source_repository: PreparedSourceRepository | None = None
    text_preparation_policy: TextPreparationPolicy | None = None
    source_normalization_host_bundle: SourceNormalizationHostBundle | None = None
    bootstrap_graph_host_bundle: BootstrapGraphHostBundle | None = None
    writer_admission: SemanticWriterAdmissionStore | None = None
    atomic_store: SemanticIngestionAtomicStore | None = None
    typed_value_registry_history: ProtectedTypedValueRegistryHistory | None = None
    observation_activation_target: VerifiedObservationActivationTarget | None = None
    bootstrap_profile: VerifiedBootstrapProfile | None = None
    now_provider: Callable[[], datetime] | None = None
    _conflict_authority_administration_grant: (
        SemanticConflictAuthorityAdministrationGrant | None
    ) = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        writer_history = (
            self.writer_admission._typed_value_registry_history
            if self.writer_admission is not None
            else None
        )
        store_history = (
            self.atomic_store._typed_value_registry_history
            if self.atomic_store is not None
            else None
        )
        if any(history is not None for history in (self.typed_value_registry_history, writer_history, store_history)):
            if self.typed_value_registry_history is not None and type(self.typed_value_registry_history) is not ProtectedTypedValueRegistryHistory:
                raise TypedValueRegistryConfigurationError("semantic runtime typed value registry history is invalid")
            if self.writer_admission is None or self.atomic_store is None:
                raise TypedValueRegistryConfigurationError("semantic runtime typed value registry requires writer and atomic store")
            assert self.atomic_store is not None
            if self.typed_value_registry_history is not writer_history:
                raise TypedValueRegistryConfigurationError("semantic runtime writer registry history differs")
            if self.typed_value_registry_history is not store_history:
                raise TypedValueRegistryConfigurationError("semantic runtime atomic store registry history differs")

        writer_target = self.writer_admission._observation_activation_target if self.writer_admission is not None else None
        store_target = self.atomic_store._observation_activation_target if self.atomic_store is not None else None
        if self.observation_activation_target is not writer_target or self.observation_activation_target is not store_target:
            raise ObservationActivationTargetConfigurationError("semantic runtime activation targets differ")

    def activate_observation_ledger(self) -> SemanticWriterCommitBinding:
        if self.observation_activation_target is None or self.writer_admission is None or self.atomic_store is None:
            raise PreplanningStoreError("observation ledger activation target authority is not configured")
        if self.bootstrap_profile is None or self.now_provider is None:
            raise PreplanningStoreError("observation ledger activation deployment authority is unavailable")
        if self.verify_authorization(
            profile=self.bootstrap_profile, use_point="activation", server_time=self.now_provider()
        ) is None:
            raise PreplanningStoreError("observation ledger activation deployment authorization is unavailable")
        return self.atomic_store.activate_observation_ledger(
            writer_binding=self.writer_admission.commit_binding(self.writer_admission.current())
        )

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
        if self.source_normalization_host_bundle is not None and self.atomic_store is None:
            raise ValueError(
                "source normalization requires atomic-store authority"
            )
        if self.bootstrap_graph_host_bundle is not None and self.atomic_store is None:
            raise ValueError("bootstrap graph execution requires atomic-store authority")
        if (self.text_preparation_service is None) != (
            self.prepared_source_repository is None
        ):
            raise ValueError("semantic runtime preparation producer and repository must be supplied together")
        if (self.text_preparation_service is None) != (
            self.text_preparation_policy is None
        ):
            raise ValueError("semantic runtime preparation producer and policy must be supplied together")
        if self.atomic_store is not None and self.prepared_source_repository is not None and not isinstance(
            self.prepared_source_repository, AtomicStorePreparedSourceRepository
        ):
            raise ValueError("production semantic runtime must use atomic prepared-source storage")
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
        self,
        *,
        memory_plane: object,
        now_provider: Callable[[], datetime],
        bootstrap_profile: VerifiedBootstrapProfile,
    ) -> AuthorizedSemanticIngestionRuntime | None:
        ...


class HostSemanticWriterActivation(Protocol):
    """Host-held authority for an explicit initial semantic writer activation."""

    def activate_initial_writer(
        self,
        *,
        writers: object,
        now_provider: Callable[[], datetime],
    ) -> None: ...


@dataclass(frozen=True)
class BuiltInLocalHostSemanticIngestionCapability:
    """Deterministic local host composition over externally verified V1 authority.

    This capability intentionally owns no trust root, release bytes, or policy
    decision.  A host must supply those verified authorities before the
    ordinary composition root can construct the local runtime.
    """

    bootstrap_material_presentation: HostBootstrapMaterialPresentation
    authorization_bytes: bytes
    authorization_verifier: SemanticDeploymentAuthorizationVerifier
    policy_provider: SemanticPipelinePolicyProvider
    current_bootstrap_release_verifier: CurrentBootstrapReleaseVerifier | None
    initial_writer_activation: HostSemanticWriterActivation | None = None
    source_normalization_host_bundle_builder: SourceNormalizationHostBundleBuilder | None = None
    bootstrap_graph_host_bundle_builder: BootstrapGraphHostBundleBuilder | None = None
    typed_value_registry_configuration: ProtectedTypedValueRegistryConfiguration | None = None
    observation_activation_target_configuration: ObservationActivationTargetConfiguration | None = None

    def load_bootstrap_material_presentation(self) -> HostBootstrapMaterialPresentation:
        return self.bootstrap_material_presentation

    def build_semantic_ingestion_runtime(
        self,
        *,
        memory_plane: object,
        now_provider: Callable[[], datetime],
        bootstrap_profile: VerifiedBootstrapProfile,
        verified_material: HostVerifiedBootstrapMaterial,
        semantic_integrity_lifecycle: PrivilegedSemanticIntegrityLifecycle | None = None,
    ) -> AuthorizedSemanticIngestionRuntime | None:
        """Build only the complete local path, otherwise leave the source evidence-only."""
        if (
            self.current_bootstrap_release_verifier is None
            or not self.authorization_bytes
            or verified_material != self.bootstrap_material_presentation.material
        ):
            return None
        try:
            material_profile = verify_bootstrap_profile(verified_material)
        except ValueError:
            return None
        if material_profile != bootstrap_profile or not material_profile.enabled:
            return None
        from memorii.core.memory_evolution.writer_admission import (
            SemanticWriterAdmissionStore,
            bounded_preplanning_ownership_manifest,
            writer_admission_memory_id,
        )
        from memorii.core.memory_plane.service import MemoryPlaneService

        if not isinstance(memory_plane, MemoryPlaneService):
            raise TypeError("built-in semantic runtime requires a memory plane service")
        typed_value_registry_history = (
            verify_configured_typed_value_registry_history(
                self.typed_value_registry_configuration
            )
            if self.typed_value_registry_configuration is not None
            else None
        )
        observation_activation_target = None
        if self.observation_activation_target_configuration is not None:
            if typed_value_registry_history is None:
                raise ObservationActivationTargetConfigurationError("activation target requires configured registry history")
            observation_activation_target = resolve_verified_observation_activation_target(
                self.observation_activation_target_configuration, typed_value_registry_history
            )
        writers = SemanticWriterAdmissionStore(
            memory_plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=now_provider,
            typed_value_registry_history=typed_value_registry_history,
            observation_activation_target=observation_activation_target,
        )
        if (
            verified_material.trust_domain == "scenario_test"
            and verified_material.release_evidence.trust_domain == "scenario_test"
            and memory_plane.get_record(writer_admission_memory_id()) is None
        ):
            # The no-auto-create writer contract leaves a fresh store unbound;
            # the scenario test domain owns creating the evidence-only epoch
            # that its runtime builds either upgrade or retain.
            writers.create_initial_evidence_only(
                admission_id="scenario-semantic-writer",
                writer_implementation_fingerprint="scenario-local-semantic-runtime",
                graph_schema_fingerprint="memorii-semantic-graph-v1",
            )
        if self.initial_writer_activation is not None:
            if (
                verified_material.trust_domain != "scenario_test"
                or verified_material.release_evidence.trust_domain != "scenario_test"
            ):
                return None
            self.initial_writer_activation.activate_initial_writer(
                writers=writers, now_provider=now_provider
            )
        store = SemanticIngestionAtomicStore(
            memory_plane,
            writers,
            now_provider=now_provider,
            semantic_freeze_guard=(
                semantic_integrity_lifecycle.freeze_guard
                if semantic_integrity_lifecycle is not None
                else None
            ),
            semantic_integrity_incident_reporter=(
                semantic_integrity_lifecycle.incident_reporter
                if semantic_integrity_lifecycle is not None
                else None
            ),
            semantic_integrity_linearization=(
                semantic_integrity_lifecycle.linearization
                if semantic_integrity_lifecycle is not None
                else None
            ),
            current_bootstrap_release_verifier=self.current_bootstrap_release_verifier,
            typed_value_registry_history=typed_value_registry_history,
            observation_activation_target=observation_activation_target,
        )
        host_bundle = (
            None
            if self.source_normalization_host_bundle_builder is None
            else self.source_normalization_host_bundle_builder.build(atomic_store=store)
        )
        # Graph execution is part of the ordinary local runtime.  Hosts may
        # replace the authority provider explicitly, but absence of a fixture
        # builder must not silently downgrade an accepted source to source-only.
        if self.bootstrap_graph_host_bundle_builder is None:
            graph_bundle = BootstrapGraphHostBundle(atomic_store=store)
        else:
            graph_bundle = self.bootstrap_graph_host_bundle_builder.build(atomic_store=store)
        runtime = build_authorized_local_semantic_runtime(
            authorization_bytes=self.authorization_bytes,
            authorization_verifier=self.authorization_verifier,
            policy_provider=self.policy_provider,
            writer_admission=writers,
            atomic_store=store,
            bootstrap_profile=bootstrap_profile,
            now_provider=now_provider,
            source_normalization_host_bundle=host_bundle,
            bootstrap_graph_host_bundle=graph_bundle,
            typed_value_registry_history=typed_value_registry_history,
            observation_activation_target=observation_activation_target,
        )
        return runtime


def build_authorized_local_semantic_runtime(
    *,
    authorization_bytes: bytes,
    authorization_verifier: SemanticDeploymentAuthorizationVerifier,
    policy_provider: SemanticPipelinePolicyProvider,
    writer_admission: SemanticWriterAdmissionStore | None = None,
    atomic_store: SemanticIngestionAtomicStore | None = None,
    bootstrap_profile: VerifiedBootstrapProfile | None = None,
    now_provider: Callable[[], datetime] | None = None,
    source_normalization_host_bundle: SourceNormalizationHostBundle | None = None,
    bootstrap_graph_host_bundle: BootstrapGraphHostBundle | None = None,
    typed_value_registry_history: ProtectedTypedValueRegistryHistory | None = None,
    observation_activation_target: VerifiedObservationActivationTarget | None = None,
) -> AuthorizedSemanticIngestionRuntime:
    """Build the ordinary zero-egress production semantic ingestion composition."""

    if (writer_admission is None) != (atomic_store is None):
        raise ValueError("local semantic runtime writer and atomic store must be supplied together")
    if writer_admission is not None and typed_value_registry_history is not writer_admission._typed_value_registry_history:
        raise TypedValueRegistryConfigurationError("local semantic runtime writer registry history differs")
    if atomic_store is not None and typed_value_registry_history is not atomic_store._typed_value_registry_history:
        raise TypedValueRegistryConfigurationError("local semantic runtime atomic store registry history differs")
    prepared_source_repository = None
    text_preparation_service = None
    text_preparation_policy = None
    if atomic_store is not None and bootstrap_profile is not None:
        assert writer_admission is not None
        prepared_source_repository = AtomicStorePreparedSourceRepository(
            atomic_store=atomic_store,
            writer_binding=lambda: writer_admission.commit_binding(
                writer_admission.current()
            ),
        )
        text_preparation_service = TextPreparationService.for_verified_bootstrap_profile(
            profile=bootstrap_profile,
            repository=prepared_source_repository,
        )
        text_preparation_policy = (
            bootstrap_profile.artifacts.profile_manifest.preparation_policy
        )
    if source_normalization_host_bundle is not None and atomic_store is None:
        raise ValueError(
            "source normalization requires atomic-store authority"
        )
    if bootstrap_graph_host_bundle is not None and atomic_store is None:
        raise ValueError("bootstrap graph execution requires atomic-store authority")
    return AuthorizedSemanticIngestionRuntime(
        authorization_bytes=authorization_bytes,
        authorization_verifier=authorization_verifier,
        policy_provider=policy_provider,
        text_preparation_service=text_preparation_service,
        prepared_source_repository=prepared_source_repository,
        text_preparation_policy=text_preparation_policy,
        source_normalization_host_bundle=source_normalization_host_bundle,
        bootstrap_graph_host_bundle=bootstrap_graph_host_bundle,
        writer_admission=writer_admission,
        atomic_store=atomic_store,
        typed_value_registry_history=typed_value_registry_history,
        observation_activation_target=observation_activation_target,
        bootstrap_profile=bootstrap_profile,
        now_provider=now_provider,
    )


__all__ = [
    "AuthorizedSemanticIngestionRuntime",
    "BuiltInLocalHostSemanticIngestionCapability",
    "HostSemanticIngestionRuntimeBuilder",
    "HostSemanticWriterActivation",
    "SemanticDeploymentAuthorizationUse",
    "SemanticDeploymentAuthorizationVerifier",
    "SemanticIngestionRuntimeAuthorization",
    "build_authorized_local_semantic_runtime",
]
