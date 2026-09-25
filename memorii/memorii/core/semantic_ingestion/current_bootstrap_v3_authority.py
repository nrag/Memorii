"""Current-release Bootstrap V3 host material for a local Level 2 installation.

This module deliberately constructs one Bootstrap V3 release family.  The
``local_level2`` value is an installation authorization mode; it is never a
second semantic profile, a test authority, or a production certificate.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapProfileReleaseBuilder,
    BootstrapProfileReleaseVerifier,
    CurrentBootstrapReleaseAssertion,
    HostBootstrapMaterialPresentation,
    HostVerifiedBootstrapMaterial,
    HostVerifiedBootstrapReleaseEvidence,
    VerifiedBootstrapProfile,
    verify_bootstrap_profile,
)
from memorii.core.memory_evolution.capability_monitoring import (
    CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT,
    CapabilityAuthorizationCheckpoint,
    CapabilityEvidenceWindow,
    CapabilityMonitor,
    CapabilityMonitoringPolicy,
    SequentialTestManifest,
)
from memorii.core.memory_evolution.observation_activation_configuration import (
    LocalLevel2ObservationActivationTargetConfiguration,
    local_level2_package_root_digest,
    resolve_verified_observation_activation_target,
)
from memorii.core.memory_evolution.typed_value_declarations import (
    ProtectedDeclarationParseLimits,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    ProtectedDecoderSourceManifestLimits,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationLimits,
    ProtectedTypedValuePublicationPins,
    parse_typed_value_publication_manifest,
)
from memorii.core.memory_evolution.typed_value_registry_configuration import (
    ProtectedTypedValueRegistryConfiguration,
    ProtectedTypedValueRegistryPublicationConfiguration,
    verify_configured_typed_value_registry_history,
)
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionStore
from memorii.core.semantic_ingestion.capability import (
    AuthorizedSemanticIngestionRuntime,
    BuiltInLocalHostSemanticIngestionCapability,
    SemanticDeploymentAuthorizationUse,
    SemanticIngestionRuntimeAuthorization,
)
from memorii.core.semantic_ingestion.contracts import (
    PredicateTemporalRule,
    PredicateTrustRule,
    SemanticArbitrationPolicyBundle,
    SemanticPipelinePolicy,
    TemporalPolicySnapshot,
    TimeInterval,
    TrustPolicySnapshot,
    contract_digest,
)
from memorii.core.semantic_ingestion.current_bootstrap_v3_lanes import (
    CurrentBootstrapV3InstalledLanes,
)
from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
    BootstrapV3OpenAIProjectAssertionsTransport,
)
from memorii.core.semantic_ingestion.project_assertions import (
    ProjectAssertionProviderProposalAdapter,
)
from memorii.core.semantic_ingestion.project_assertions_profile import (
    ProjectAssertionsProfileBundle,
    load_project_assertions_bundle,
)
from memorii.core.semantic_ingestion.source_normalization_host import (
    SourceNormalizationHostBundleBuilder,
)

_DIGEST = r"^[0-9a-f]{64}$"
_PREDICATES = ("project_deadline", "project_owner", "project_status")
_LOCAL_LEVEL2_REGISTRY_HISTORY_CACHE: dict[
    tuple[str, str, str, str], ProtectedTypedValueRegistryHistory
] = {}


class CurrentBootstrapV3AuthorityError(ValueError):
    """Installed material or its local authorization failed closed validation."""


class LocalLevel2BootstrapV3Authorization(BaseModel):
    """Closed, installation-bound authorization for the one Bootstrap V3 release."""

    schema_id: Literal["memorii.semantic_ingestion.local_level2_bootstrap_v3_authorization"]
    schema_version: Literal[1]
    authority_kind: Literal["local_level2_operator"]
    execution_class: Literal["local_level2"]
    installation_id: str = Field(min_length=1)
    hermes_home_digest: str = Field(pattern=_DIGEST)
    bootstrap_profile_verification_digest: str = Field(pattern=_DIGEST)
    bootstrap_manifest_digest: str = Field(pattern=_DIGEST)
    component_root_digest: str = Field(pattern=_DIGEST)
    project_assertions_catalog_digest: str = Field(pattern=_DIGEST)
    project_assertions_prompt_digest: str = Field(pattern=_DIGEST)
    project_assertions_output_schema_digest: str = Field(pattern=_DIGEST)
    project_assertions_provider_binding_digest: str = Field(pattern=_DIGEST)
    project_assertions_egress_policy_digest: str = Field(pattern=_DIGEST)
    issued_at: datetime
    expires_at: datetime
    authorization_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _validate_digest_and_expiry(self) -> LocalLevel2BootstrapV3Authorization:
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None or self.expires_at <= self.issued_at:
            raise ValueError("local Bootstrap V3 authorization lifetime is invalid")
        body = self.model_dump(mode="python", exclude={"authorization_digest"})
        if self.authorization_digest != contract_digest(
            b"memorii.semantic-ingestion.local-level2-bootstrap-v3-authorization.v1", body
        ):
            raise ValueError("local Bootstrap V3 authorization digest mismatch")
        return self

    @classmethod
    def create(cls, **body: object) -> LocalLevel2BootstrapV3Authorization:
        return cls(
            **body,
            authorization_digest=contract_digest(
                b"memorii.semantic-ingestion.local-level2-bootstrap-v3-authorization.v1", body
            ),
        )


@dataclass(frozen=True)
class VerifiedBootstrapV3ResourcePolicy:
    """Verified package resources used by the fixed project-assertion adapter."""

    catalog_digest: str
    prompt_schema_digest: str
    provider_binding_digest: str
    egress_policy_digest: str
    component_fingerprint_digest: str
    policy_digest: str

    @classmethod
    def from_bundle(cls, bundle: ProjectAssertionsProfileBundle) -> VerifiedBootstrapV3ResourcePolicy:
        digests = dict(bundle.profile_digests)
        required = {
            "semantic_contract_digest",
            "prompt_schema_digest",
            "profile_manifest_digest",
            "egress_policy_digest",
            "component_fingerprint_digest",
        }
        if set(digests) != {
            "profile_manifest_digest", "semantic_contract_digest", "component_fingerprint_digest",
            "prompt_schema_digest", "predicate_catalog_digest", "egress_policy_digest",
        } or any(not isinstance(digests[key], str) for key in required):
            raise CurrentBootstrapV3AuthorityError("installed Bootstrap V3 resource policy is invalid")
        body = {
            "catalog_digest": digests["predicate_catalog_digest"],
            "prompt_schema_digest": digests["prompt_schema_digest"],
            "provider_binding_digest": digests["profile_manifest_digest"],
            "egress_policy_digest": digests["egress_policy_digest"],
            "component_fingerprint_digest": digests["component_fingerprint_digest"],
        }
        return cls(
            **body,
            policy_digest=contract_digest(b"memorii.semantic-ingestion.bootstrap-v3-resource-policy.v1", body),
        )


class LocalLevel2BootstrapV3DeploymentVerifier:
    """Host-owned verifier for exact local authorization bytes and revalidation."""

    def __init__(self, *, authorization: LocalLevel2BootstrapV3Authorization, profile: VerifiedBootstrapProfile) -> None:
        self._authorization = authorization
        self._profile = profile

    def verify(
        self,
        *,
        authorization_bytes: bytes,
        use: SemanticDeploymentAuthorizationUse,
        server_time: datetime,
    ) -> SemanticIngestionRuntimeAuthorization | None:
        if not _is_live(self._authorization, server_time) or authorization_bytes != _authorization_bytes(self._authorization):
            return None
        if (
            use.profile_manifest_digest != self._profile.artifacts.profile_manifest.profile_digest
            or use.verified_bootstrap_release_digest != self._profile.verification_digest
        ):
            return None
        body = {
            "authorization_digest": sha256(authorization_bytes).hexdigest(),
            "target_profile_manifest_digest": use.profile_manifest_digest,
            "verified_bootstrap_release_digest": use.verified_bootstrap_release_digest,
            "deployment_artifact_digest": self._authorization.bootstrap_manifest_digest,
            "authority_snapshot_digest": self._authorization.authorization_digest,
            "active_epoch": 1,
            "expires_at": self._authorization.expires_at,
            "signer_id": "local_level2_operator",
        }
        return SemanticIngestionRuntimeAuthorization(
            **body,
            decision_digest=contract_digest(b"memorii.semantic-ingestion.verified-deployment-authorization.v1", body),
        )


@dataclass(frozen=True)
class LocalLevel2MonitoredCapabilityActivation:
    """Initialize the local V3 capability from verified installation evidence.

    This is a Level 2 installation attestation, not a traffic canary or a
    production certification.  The monitor remains the only writer of the
    persisted capability status.
    """

    authorization: LocalLevel2BootstrapV3Authorization
    resource_policy: VerifiedBootstrapV3ResourcePolicy

    def initialize_capability_status(
        self, *, writers: SemanticWriterAdmissionStore, now_provider: Callable[[], datetime]
    ) -> None:
        now = now_provider()
        if not _is_live(self.authorization, now):
            raise CurrentBootstrapV3AuthorityError("local Bootstrap V3 authorization is unavailable")
        capability_fingerprint = CurrentBootstrapV3InstalledLanes(
            resource_policy=self.resource_policy
        ).proposal_capability_fingerprint
        implementation = CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT
        policy = CapabilityMonitoringPolicy.create(
            capability_fingerprint=capability_fingerprint,
            monitoring_policy_revision="bootstrap-v3-local-level2-installation-v1",
            maximum_independent_label_age=timedelta(days=1),
            maximum_canary_success_age=timedelta(days=1),
            minimum_labeled_clusters_per_window=1,
            label_window=timedelta(days=1),
            paused_traffic_grace_period=timedelta(hours=1),
            label_pipeline_outage_grace_period=timedelta(hours=1),
            stale_evidence_action="evidence_only",
            metric_gates=(),
            family_wise_alpha_budget="0.1",
            sequential_test_manifest=SequentialTestManifest.create(
                method="time_uniform_confidence_sequence",
                bounded_value_lower="0",
                bounded_value_upper="1",
                spending_rule_id="inverse_quadratic_union_bound_v1",
                implementation_fingerprint=implementation,
            ),
            breach_action="evidence_only",
            activation_mode="verified_installation",
        )
        evidence = CapabilityEvidenceWindow.create(
            capability_fingerprint=capability_fingerprint,
            monitoring_policy_digest=policy.policy_digest,
            sequential_implementation_fingerprint=implementation,
            observations=(),
            latest_independent_label_at=None,
            latest_canary_success_at=None,
            traffic_state="active",
            # This is installation evidence.  Its identity must survive a
            # service reopen while the sidecar authorization remains current;
            # startup time is not a new traffic-state transition.
            traffic_state_changed_at=self.authorization.issued_at,
            label_pipeline_state="healthy",
            label_pipeline_state_changed_at=self.authorization.issued_at,
        )
        checkpoint_body = {
            "capability_fingerprint": capability_fingerprint,
            "monitoring_policy_digest": policy.policy_digest,
            "deployment_authorization_digest": self.authorization.authorization_digest,
            "deployment_artifact_raw_digest": self.authorization.bootstrap_manifest_digest,
            "target_artifact_digest": self.resource_policy.component_fingerprint_digest,
            "approval_release_digest": self.authorization.bootstrap_profile_verification_digest,
            "expires_at": self.authorization.expires_at,
            "signer_subject_id": "local_level2_operator",
            "signing_key_reference": "hermes-sidecar:" + self.authorization.hermes_home_digest,
            "authority_snapshot_digest": self.authorization.authorization_digest,
            "active_epoch": 1,
        }
        checkpoint = CapabilityAuthorizationCheckpoint(
            **checkpoint_body,
            checkpoint_digest=contract_digest(
                b"memorii.semantic-ingestion.capability-authorization-checkpoint.v1",
                checkpoint_body,
            ),
        )
        CapabilityMonitor(
            writers=writers,
            now=now_provider,
            policies=(policy,),
            authorization_checkpoints=(checkpoint,),
        ).initialize_active_from_verified_evidence(
            evidence=evidence
        )


class LocalLevel2CurrentBootstrapReleaseVerifier:
    """Revalidates the exact local authorization at each existing V3 write phase."""

    def __init__(
        self, *, authorization: LocalLevel2BootstrapV3Authorization,
        now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._authorization = authorization
        self._now = now_provider

    def assert_current(self, *, authorization: object, release_evidence: object, assertion_phase: str) -> CurrentBootstrapReleaseAssertion:
        del authorization
        if assertion_phase not in {"prepared_publication", "pre_handoff_retry", "writer_handoff"}:
            raise CurrentBootstrapV3AuthorityError("Bootstrap V3 release assertion phase is invalid")
        if not isinstance(release_evidence, HostVerifiedBootstrapReleaseEvidence) or not _is_live(
            self._authorization, self._now()
        ):
            raise CurrentBootstrapV3AuthorityError("local Bootstrap V3 authorization is unavailable")
        body = {
            "coordinate": release_evidence.coordinate.model_dump(mode="python"),
            "signed_release_digest": release_evidence.signed_release_digest,
            "bootstrap_anchor_digest": release_evidence.bootstrap_anchor_digest,
            "active_lifecycle_snapshot_digest": release_evidence.active_lifecycle_snapshot_digest,
            "assertion_phase": assertion_phase,
            "assertion_nonce": contract_digest(
                b"memorii.semantic-ingestion.local-level2-bootstrap-v3-release-use.v1",
                {"authorization": self._authorization.authorization_digest, "phase": assertion_phase},
            ),
        }
        return CurrentBootstrapReleaseAssertion(
            **body,
            assertion_digest=contract_digest(b"memorii.semantic_ingestion.current_bootstrap_release_assertion.v1", body),
        )


@dataclass(frozen=True)
class BootstrapV3HostInputEnvelope:
    """Opaque current-release material supplied by a host composition root.

    Dynamic ingress, source-normalization, graph, writer, and read capability
    issuance remains outside this immutable installed-material boundary.
    """

    bootstrap_profile: VerifiedBootstrapProfile
    resource_policy: VerifiedBootstrapV3ResourcePolicy
    authorization_bytes: bytes
    deployment_authorization_verifier: LocalLevel2BootstrapV3DeploymentVerifier
    current_release_verifier: LocalLevel2CurrentBootstrapReleaseVerifier
    execution_class: Literal["local_level2"]
    envelope_digest: str


@dataclass(frozen=True)
class LocalLevel2BootstrapV3HostCapability:
    """The one installed host capability for a locally authorized Bootstrap V3 run.

    The capability owns no new profile selection.  It presents the already
    verified current Bootstrap release and delegates all store composition to
    the canonical Bootstrap runtime builder.
    """

    envelope: BootstrapV3HostInputEnvelope
    material: HostVerifiedBootstrapMaterial
    authentication_proof: bytes
    runtime_capability: BuiltInLocalHostSemanticIngestionCapability
    execution_class: Literal["local_level2"] = "local_level2"

    def load_bootstrap_material_presentation(self) -> HostBootstrapMaterialPresentation:
        return HostBootstrapMaterialPresentation(
            material=self.material, authentication_proof=self.authentication_proof
        )

    def build_semantic_ingestion_runtime(
        self, *, memory_plane: object, now_provider: Callable[[], datetime],
        bootstrap_profile: VerifiedBootstrapProfile,
    ) -> AuthorizedSemanticIngestionRuntime | None:
        return self.runtime_capability.build_semantic_ingestion_runtime(
            memory_plane=memory_plane,
            now_provider=now_provider,
            bootstrap_profile=bootstrap_profile,
            verified_material=self.material,
        )


class LocalLevel2BootstrapV3MaterialVerifier:
    """Accept only the exact material presentation minted with one sidecar."""

    def __init__(self, *, capability: LocalLevel2BootstrapV3HostCapability) -> None:
        self._capability = capability

    def verify(
        self, *, presentation: HostBootstrapMaterialPresentation,
        required_trust_domain: Literal["production", "local_level2", "scenario_test"],
        server_time: datetime,
    ) -> HostVerifiedBootstrapMaterial | None:
        envelope = self._capability.envelope
        if (
            required_trust_domain != "local_level2"
            or presentation.material != self._capability.material
            or presentation.authentication_proof != self._capability.authentication_proof
            or not _is_live_authorization_bytes(envelope.authorization_bytes, server_time)
        ):
            return None
        return self._capability.material


def _local_level2_observation_activation_configuration(
    *, authorization: LocalLevel2BootstrapV3Authorization,
    resource_policy: VerifiedBootstrapV3ResourcePolicy,
) -> tuple[ProtectedTypedValueRegistryConfiguration, LocalLevel2ObservationActivationTargetConfiguration]:
    """Bind the installed registry publication to the exact local Bootstrap release.

    The signed-wheel target remains the production arm.  This local arm uses
    the installation sidecar and package bytes that the Level 2 operator has
    already authorized, then rechecks both on every writer admission.
    """
    import memorii

    # ``memorii.__file__`` names the installed package itself.  The previous
    # parent directory is the editable-project root during development and can
    # contain a virtual environment, test artifacts, and unrelated files.  It
    # is not the installed package whose bytes this local authority binds.
    package_root = Path(memorii.__file__).resolve().parent
    # Decoder manifests are rooted at the import root and retain paths such as
    # ``memorii/core/...``.  Keep that verification root separate from the
    # package-byte root bound by local activation.
    import_root = package_root.parent
    source_root = package_root / "core" / "memory_evolution" / "observation_registry_sources"
    try:
        role_sources = tuple(
            path.read_bytes()
            for path in sorted(
                (
                    path for path in source_root.rglob("*.json")
                    if path.name not in {"decoder-source-manifest.json", "publication-manifest.json"}
                ),
                key=lambda path: path.relative_to(source_root).as_posix().encode("utf-8"),
            )
        )
        decoder_manifest = (source_root / "decoder-source-manifest.json").read_bytes()
        publication_manifest = (source_root / "publication-manifest.json").read_bytes()
    except OSError as exc:
        raise CurrentBootstrapV3AuthorityError("installed observation registry is unavailable") from exc
    limits = ProtectedTypedValuePublicationLimits(
        ProtectedDeclarationParseLimits(2_000_000, 300_000, 64),
        ProtectedDecoderSourceManifestLimits(8_000_000, 300_000, 64, 10_000, 2_000_000),
        2_000_000,
    )
    try:
        manifest = parse_typed_value_publication_manifest(
            publication_manifest, maximum_bytes=limits.maximum_publication_manifest_bytes
        )
    except ValueError as exc:
        raise CurrentBootstrapV3AuthorityError("installed observation registry manifest is invalid") from exc
    # The generated publication is the immutable local verification vector.
    # It is a package resource, so this runtime has no dependency on work-plan
    # evidence or test fixtures.
    pins = ProtectedTypedValuePublicationPins(
        publication_digest=manifest.publication_digest,
        registry_digest=manifest.registry_digest,
        decoder_source_snapshots=tuple(
            DecoderSourceSnapshotPin(row.decoder_id, row.source_snapshot_digest)
            for row in manifest.decoder_source_snapshots
        ),
        independent_vector_manifest_digest=sha256(publication_manifest).hexdigest(),
    )
    registry_configuration = ProtectedTypedValueRegistryConfiguration((
        ProtectedTypedValueRegistryPublicationConfiguration(
            raw_role_sources=role_sources,
            raw_decoder_source_manifest=decoder_manifest,
            raw_publication_manifest=publication_manifest,
            raw_independent_vector_manifest=publication_manifest,
            source_package_root=import_root,
            limits=limits,
            pins=pins,
        ),
    ))
    target_configuration = LocalLevel2ObservationActivationTargetConfiguration(
        sidecar_authorization_digest=authorization.authorization_digest,
        bootstrap_profile_verification_digest=authorization.bootstrap_profile_verification_digest,
        component_root_digest=authorization.component_root_digest,
        resource_policy_digest=resource_policy.policy_digest,
        package_root=package_root,
        package_root_digest=local_level2_package_root_digest(package_root),
        typed_value_publication_digest=manifest.publication_digest,
        typed_value_registry_digest=manifest.registry_digest,
        decoder_source_manifest_digest=manifest.decoder_source_manifest_digest,
        expires_at=authorization.expires_at,
        now_provider=lambda: datetime.now(UTC),
    )
    return registry_configuration, target_configuration


def _verified_local_level2_registry_history(
    *,
    registry_configuration: ProtectedTypedValueRegistryConfiguration,
    target_configuration: LocalLevel2ObservationActivationTargetConfiguration,
) -> ProtectedTypedValueRegistryHistory:
    """Reuse one fully verified immutable local registry generation per process."""
    key = (
        target_configuration.package_root_digest,
        target_configuration.typed_value_publication_digest,
        target_configuration.typed_value_registry_digest,
        target_configuration.decoder_source_manifest_digest,
    )
    history = _LOCAL_LEVEL2_REGISTRY_HISTORY_CACHE.get(key)
    if history is not None:
        return history
    history = verify_configured_typed_value_registry_history(registry_configuration)
    target = resolve_verified_observation_activation_target(target_configuration, history)
    if target.publication.publication_manifest.publication_digest != key[1]:
        raise CurrentBootstrapV3AuthorityError("local observation registry cache is substituted")
    _LOCAL_LEVEL2_REGISTRY_HISTORY_CACHE[key] = history
    return history


class CurrentReleaseBootstrapV3HostMaterialBuilder:
    """Verify installed current-release bytes and build the complete static host material."""

    @classmethod
    def build(
        cls, *, authorization: LocalLevel2BootstrapV3Authorization, now: datetime
    ) -> BootstrapV3HostInputEnvelope:
        if not _is_live(authorization, now):
            raise CurrentBootstrapV3AuthorityError("local Bootstrap V3 authorization is unavailable")
        release = BootstrapProfileReleaseBuilder.build(enabled=True)
        verified_release = BootstrapProfileReleaseVerifier.verify(payloads=release.payloads, enabled=True)
        evidence = _release_evidence(profile=verified_release)
        material = HostVerifiedBootstrapMaterial(
            artifact_payloads=release.payloads, release_evidence=evidence,
            authenticated_ingress_resolver=object(), profile_enabled=True, trust_domain="local_level2",
        )
        profile = verify_bootstrap_profile(material)
        policy = VerifiedBootstrapV3ResourcePolicy.from_bundle(load_project_assertions_bundle())
        _verify_authorization(authorization=authorization, profile=profile, policy=policy)
        authorization_bytes = _authorization_bytes(authorization)
        body = {
            "bootstrap_profile_verification_digest": profile.verification_digest,
            "resource_policy_digest": policy.policy_digest,
            "authorization_digest": authorization.authorization_digest,
            "execution_class": "local_level2",
        }
        return BootstrapV3HostInputEnvelope(
            bootstrap_profile=profile,
            resource_policy=policy,
            authorization_bytes=authorization_bytes,
            deployment_authorization_verifier=LocalLevel2BootstrapV3DeploymentVerifier(
                authorization=authorization, profile=profile
            ),
            current_release_verifier=LocalLevel2CurrentBootstrapReleaseVerifier(authorization=authorization),
            execution_class="local_level2",
            envelope_digest=contract_digest(b"memorii.semantic-ingestion.bootstrap-v3-host-input-envelope.v1", body),
        )

    @classmethod
    def build_capability(
        cls,
        *,
        authorization: LocalLevel2BootstrapV3Authorization,
        now: datetime,
        authenticated_ingress_resolver: object,
        authorization_is_current: Callable[[], bool] | None = None,
    ) -> tuple[LocalLevel2BootstrapV3HostCapability, LocalLevel2BootstrapV3MaterialVerifier]:
        """Build the sole local host presentation after sidecar verification.

        The resolver is supplied by the Hermes factory, where authenticated
        callback evidence is available.  It is retained verbatim in the host
        material and is never rebuilt from a public provider event.
        """
        envelope = cls.build(authorization=authorization, now=now)
        release = BootstrapProfileReleaseBuilder.build(enabled=True)
        profile = BootstrapProfileReleaseVerifier.verify(payloads=release.payloads, enabled=True)
        material = HostVerifiedBootstrapMaterial(
            artifact_payloads=release.payloads,
            release_evidence=_release_evidence(profile=profile),
            authenticated_ingress_resolver=authenticated_ingress_resolver,
            profile_enabled=True,
            trust_domain="local_level2",
        )
        presentation = HostBootstrapMaterialPresentation(
            material=material,
            authentication_proof=envelope.authorization_bytes,
        )
        normalization_builder = _normalization_builder(
            authorization=authorization,
            resource_policy=envelope.resource_policy,
            authorization_is_current=authorization_is_current,
        )
        registry_configuration, observation_activation_target_configuration = (
            _local_level2_observation_activation_configuration(
                authorization=authorization, resource_policy=envelope.resource_policy
            )
        )
        verified_registry_history = _verified_local_level2_registry_history(
            registry_configuration=registry_configuration,
            target_configuration=observation_activation_target_configuration,
        )
        runtime = BuiltInLocalHostSemanticIngestionCapability(
            bootstrap_material_presentation=presentation,
            authorization_bytes=envelope.authorization_bytes,
            authorization_verifier=envelope.deployment_authorization_verifier,
            policy_provider=_FixedBootstrapV3PolicyProvider(at=now),
            current_bootstrap_release_verifier=envelope.current_release_verifier,
            source_normalization_host_bundle_builder=normalization_builder,
            typed_value_registry_configuration=registry_configuration,
            verified_typed_value_registry_history=verified_registry_history,
            observation_activation_target_configuration=observation_activation_target_configuration,
            bootstrap_recovery_operation_lease_duration=timedelta(minutes=10),
            capability_status_activation=LocalLevel2MonitoredCapabilityActivation(
                authorization=authorization, resource_policy=envelope.resource_policy
            ),
        )
        capability = LocalLevel2BootstrapV3HostCapability(
            envelope=envelope,
            material=material,
            authentication_proof=envelope.authorization_bytes,
            runtime_capability=runtime,
        )
        return capability, LocalLevel2BootstrapV3MaterialVerifier(capability=capability)


def _normalization_builder(
    *, authorization: LocalLevel2BootstrapV3Authorization,
    resource_policy: VerifiedBootstrapV3ResourcePolicy,
    authorization_is_current: Callable[[], bool] | None = None,
) -> SourceNormalizationHostBundleBuilder:
    """Compose current installed lanes and the only remote proposal boundary."""
    from memorii.core.semantic_ingestion.current_bootstrap_v3_dynamic_authority import (
        CurrentBootstrapV3DynamicAuthorityProvider,
    )

    is_current = authorization_is_current or (
        lambda: _is_live(authorization, datetime.now(UTC))
    )
    dynamic = CurrentBootstrapV3DynamicAuthorityProvider(
        resource_policy=resource_policy,
        authorization_is_current=is_current,
        now=lambda: datetime.now(UTC),
    )
    lanes = CurrentBootstrapV3InstalledLanes(resource_policy=resource_policy)
    adapter = ProjectAssertionProviderProposalAdapter(
        semantic_contract_digest=resource_policy.catalog_digest,
        resolve_quote=dynamic.quote_authority.resolve,
        projection_quote_verifier=dynamic.quote_authority,
    )
    transport = BootstrapV3OpenAIProjectAssertionsTransport(
        adapter=adapter,
        egress_authorized=lambda request: (
            is_current()
            and request.proposal_capability_fingerprint == lanes.proposal_capability_fingerprint
            and request.proposer_manifest.runtime_fingerprint
            == resource_policy.component_fingerprint_digest
        ),
        credential_resolver=lambda: os.getenv("OPENAI_API_KEY"),
    )
    return SourceNormalizationHostBundleBuilder(
        authority_provider=dynamic,
        resolve_quote=dynamic.quote_authority.resolve,
        projection_quote_verifier=dynamic.quote_authority,
        server_time=lambda: datetime.now(UTC),
        # Recovery contracts express their ten-tick lifetime in coarse
        # monotonic ticks.  Nanoseconds would expire a claim between adjacent
        # in-process stages before the proposal transport is reached.
        monotonic_tick=lambda: int(time.monotonic()),
        bootstrap_v3_proposal_transport=transport,
        bootstrap_v3_stanza=lanes.stanza,
        bootstrap_v3_spacy=lanes.spacy,
        bootstrap_v3_predicate_event_detection=lanes.predicate,
        bootstrap_v3_temporal_resolution=lanes.temporal,
        bootstrap_v3_linguistic_request=dynamic.linguistic_request,
        bootstrap_v3_predicate_request=dynamic.predicate_request,
        bootstrap_v3_temporal_request=dynamic.temporal_request,
        authorization_is_current=is_current,
    )


def local_level2_bootstrap_authorization_from_sidecar(
    sidecar: Mapping[str, object], *, now: datetime
) -> LocalLevel2BootstrapV3Authorization:
    """Translate the already validated CLI sidecar into the V3 runtime wire."""
    raw = sidecar.get("authorization")
    if not isinstance(raw, Mapping):
        raise CurrentBootstrapV3AuthorityError("local Bootstrap V3 sidecar is invalid")
    installation_id = sidecar.get("installation_id")
    home_digest = sidecar.get("hermes_home_digest")
    if not isinstance(installation_id, str) or not isinstance(home_digest, str):
        raise CurrentBootstrapV3AuthorityError("local Bootstrap V3 sidecar is invalid")
    release = BootstrapProfileReleaseBuilder.build(enabled=True)
    profile = BootstrapProfileReleaseVerifier.verify(payloads=release.payloads, enabled=True)
    policy = VerifiedBootstrapV3ResourcePolicy.from_bundle(load_project_assertions_bundle())
    values = {
        "schema_id": "memorii.semantic_ingestion.local_level2_bootstrap_v3_authorization",
        "schema_version": 1,
        "authority_kind": "local_level2_operator",
        "execution_class": "local_level2",
        "installation_id": installation_id,
        "hermes_home_digest": home_digest,
        "bootstrap_profile_verification_digest": profile.verification_digest,
        "bootstrap_manifest_digest": profile.artifacts.profile_manifest.profile_digest,
        "component_root_digest": profile.artifacts.profile_manifest.component_root_digest,
        "project_assertions_catalog_digest": policy.catalog_digest,
        "project_assertions_prompt_digest": policy.prompt_schema_digest,
        "project_assertions_output_schema_digest": policy.prompt_schema_digest,
        "project_assertions_provider_binding_digest": policy.provider_binding_digest,
        "project_assertions_egress_policy_digest": policy.egress_policy_digest,
        "issued_at": _sidecar_time(raw.get("issued_at")),
        "expires_at": _sidecar_time(raw.get("expires_at")),
    }
    try:
        authorization = LocalLevel2BootstrapV3Authorization.create(**values)
    except (TypeError, ValueError) as error:
        raise CurrentBootstrapV3AuthorityError("local Bootstrap V3 sidecar is invalid") from error
    if not _is_live(authorization, now):
        raise CurrentBootstrapV3AuthorityError("local Bootstrap V3 authorization is unavailable")
    return authorization


class _FixedBootstrapV3PolicyProvider:
    """Installed fixed trial policy, re-issued at each canonical policy read."""

    def __init__(self, *, at: datetime) -> None:
        self._policy = SemanticPipelinePolicy(
            arbitration_bundle=build_project_assertions_arbitration_policy(at=at)
        )

    def current_policy(self, *, source_id: str, source_digest: str) -> SemanticPipelinePolicy | None:
        if not source_id or len(source_digest) != 64:
            return None
        return self._policy


def build_project_assertions_arbitration_policy(*, at: datetime) -> SemanticArbitrationPolicyBundle:
    """Return the fixed three-predicate policy for this current-release trial."""
    if at.tzinfo is None:
        raise CurrentBootstrapV3AuthorityError("Bootstrap V3 policy clock must be timezone-aware")
    interval = TimeInterval(start=datetime(2020, 1, 1, tzinfo=UTC), end=None)
    trust = TrustPolicySnapshot.create(
        policy_revision="bootstrap-v3-project-assertions-trust-v1", system_effective_interval=interval,
        rules=tuple(PredicateTrustRule(
            predicate_id=predicate, eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 10},
        ) for predicate in _PREDICATES),
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="bootstrap-v3-project-assertions-temporal-v1", system_effective_interval=interval,
        rules=tuple(PredicateTemporalRule(
            predicate_id=predicate, valid_time_requirement="optional", allow_open_end=True,
        ) for predicate in _PREDICATES),
    )
    return SemanticArbitrationPolicyBundle.create(
        trust_policy=trust, temporal_policy=temporal, arbitration_as_of=at,
    )


def _release_evidence(*, profile: VerifiedBootstrapProfile) -> HostVerifiedBootstrapReleaseEvidence:
    body = {
        "coordinate": BOOTSTRAP_COORDINATE,
        "signed_release_digest": profile.verification_digest,
        "bootstrap_anchor_digest": sha256(b"memorii.bootstrap-v3.local-level2.anchor.v1").hexdigest(),
        "external_root_digest": sha256(b"memorii.bootstrap-v3.local-level2.root.v1").hexdigest(),
        "active_lifecycle_snapshot_digest": sha256(b"memorii.bootstrap-v3.local-level2.lifecycle.v1").hexdigest(),
        "lifecycle_state": "active", "trust_domain": "local_level2", "verified_at": datetime.now(UTC),
    }
    return HostVerifiedBootstrapReleaseEvidence(
        **body,
        evidence_digest=contract_digest(b"memorii.semantic_ingestion.host_verified_bootstrap_release_evidence.v1", body),
    )


def _verify_authorization(*, authorization: LocalLevel2BootstrapV3Authorization, profile: VerifiedBootstrapProfile, policy: VerifiedBootstrapV3ResourcePolicy) -> None:
    if (
        authorization.bootstrap_profile_verification_digest != profile.verification_digest
        or authorization.bootstrap_manifest_digest != profile.artifacts.profile_manifest.profile_digest
        or authorization.component_root_digest != profile.artifacts.profile_manifest.component_root_digest
        or authorization.project_assertions_catalog_digest != policy.catalog_digest
        or authorization.project_assertions_prompt_digest != policy.prompt_schema_digest
        or authorization.project_assertions_output_schema_digest != policy.prompt_schema_digest
        or authorization.project_assertions_provider_binding_digest != policy.provider_binding_digest
        or authorization.project_assertions_egress_policy_digest != policy.egress_policy_digest
    ):
        raise CurrentBootstrapV3AuthorityError("local Bootstrap V3 authorization is substituted")


def _authorization_bytes(authorization: LocalLevel2BootstrapV3Authorization) -> bytes:
    return authorization.model_dump_json().encode("utf-8")


def _is_live(authorization: LocalLevel2BootstrapV3Authorization, now: datetime) -> bool:
    return now.tzinfo is not None and authorization.issued_at <= now < authorization.expires_at


def _is_live_authorization_bytes(value: bytes, now: datetime) -> bool:
    try:
        authorization = LocalLevel2BootstrapV3Authorization.model_validate_json(value)
    except ValueError:
        return False
    return _is_live(authorization, now)


def _sidecar_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("sidecar timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("sidecar timestamp is invalid")
    return parsed


__all__ = [
    "BootstrapV3HostInputEnvelope", "CurrentBootstrapV3AuthorityError",
    "CurrentReleaseBootstrapV3HostMaterialBuilder", "LocalLevel2BootstrapV3Authorization",
    "LocalLevel2BootstrapV3DeploymentVerifier", "LocalLevel2CurrentBootstrapReleaseVerifier",
    "LocalLevel2BootstrapV3HostCapability", "LocalLevel2BootstrapV3MaterialVerifier",
    "LocalLevel2MonitoredCapabilityActivation",
    "VerifiedBootstrapV3ResourcePolicy", "build_project_assertions_arbitration_policy",
]
