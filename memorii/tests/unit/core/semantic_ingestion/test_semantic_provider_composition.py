import base64
import json
import re
import socket
import sys as _sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

# The sibling support module resolves as a top-level import under pytest's
# prepend mode, but the bootstrap-graph process runner imports this module
# in a fresh interpreter without that path entry.
if (support_dir := str(Path(__file__).parent)) not in _sys.path:
    _sys.path.insert(0, support_dir)

import pytest
from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
    RetainedSourceOperationRequest,
    source_admission_source_digest,
)
from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    BootstrapWriterHandoffMarkerV3,
    PreplanningLease,
    PreplanningOperationControl,
    PreplanningStoreError,
    SemanticAuthorizationAuthorityRecord,
    SemanticIngestionAtomicStore,
    StructuredSubmissionGrantRevokedError,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapProfileReleaseBuilder,
    BootstrapProfileReleaseVerifier,
    CurrentBootstrapReleaseAssertion,
    HostVerifiedBootstrapMaterial,
    verify_bootstrap_profile,
)
from memorii.core.memory_evolution.conflict_integrity import (
    ConflictIntegrityError,
    FileConflictIntegrityRepository,
    PrivilegedSemanticIntegrityLifecycle,
    ReplayIntegrityLinearization,
    SemanticEventCleanAuthorityBatch,
    SemanticEventCleanRecoveryRequest,
)
from memorii.core.memory_evolution.delivery_coordinate_migration import (
    DeliveryCoordinateMigrationCheckpoint,
    activate_migration,
    build_migration_plan,
    certify_migration,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    AuthenticatedIngressResolutionError,
    AuthenticatedOriginLineageEvidence,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    AuthenticatedSemanticSourceInterval,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.typed_value_declarations import (
    ProtectedDeclarationParseLimits,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifest,
    DecoderSourceSelection,
    DecoderSourceSnapshot,
    ProtectedDecoderSourceManifestLimits,
    VerifiedDecoderSourceManifest,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationLimits,
    ProtectedTypedValuePublicationPins,
    PublicationDecoderSourceSnapshot,
    TypedValuePublicationManifest,
    VerifiedTypedValuePublication,
    parse_typed_value_publication_manifest,
)
from memorii.core.memory_evolution.typed_value_publication_authoring import (
    author_typed_value_publication_package,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledPolicyDigests,
    CompiledProfile,
    CompiledRegistryEntry,
    CompiledTypedValueRegistry,
)
from memorii.core.memory_evolution.typed_value_registry_configuration import (
    ProtectedTypedValueRegistryConfiguration,
    ProtectedTypedValueRegistryPublicationConfiguration,
    TypedValueRegistryConfigurationError,
    verify_configured_typed_value_registry_history,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
    writer_admission_memory_id,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    _PersistedBatch,
    record_digest,
)
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.ingestion import (
    ProviderIngestionCoordinator,
    RetainedStructuredSubmission,
    StructuredFactSubmissionRequest,
    StructuredFactSubmissionStatusRequest,
)
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.scoped_context.authority import (
    InProcessScopedReadAuthority,
    ScopedNamespaceGrantRow,
)
from memorii.core.scoped_context.contracts import (
    ScopedContextBudget,
    ScopedContextRequest,
    ScopedContextStatus,
)
from memorii.core.semantic_ingestion.authorization import (
    SemanticAuthorizationAuthorityRepository,
    SemanticAuthorizationReadSet,
)
from memorii.core.semantic_ingestion.capability import (
    AuthorizedSemanticIngestionRuntime,
    BuiltInLocalHostSemanticIngestionCapability,
    SemanticIngestionRuntimeAuthorization,
    build_authorized_local_semantic_runtime,
)
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    ResolvedCatalogAuthority,
    ResolvedStructuredSubmissionAuthority,
    SourceScopeGrant,
    StructuredFactReadAuthority,
    StructuredGrantState,
    StructuredSubmissionAuthorityRequest,
    ThreePredicateSeedCatalogAuthorityRepository,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphDurableRetryProgressV3,
    BootstrapGraphGroupCommitRequestV3,
    BootstrapPredicateLanePayloadV3,
    BootstrapRecoveryKeyV3,
    BootstrapRecoveryProbeV3,
    BootstrapTemporalLanePayloadV3,
    DependencyArc,
    LinguisticAnalysis,
    LinguisticToken,
    PredicateTemporalRule,
    PredicateTrustRule,
    ProviderSemanticProposal,
    SemanticArbitrationPolicyBundle,
    SemanticCandidate,
    SemanticPipelinePolicy,
    TemporalPolicySnapshot,
    TextPreparationPolicy,
    TimeInterval,
    TrustPolicySnapshot,
    contract_digest,
)
from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageObservationRepository,
    CoverageSemanticOutcome,
    CoverageSourceSpan,
    DiscoveryProcessingState,
    ObserverBindingIdentity,
)
from memorii.core.semantic_ingestion.coverage_observer import (
    OntologyObservationResult,
)
from memorii.core.semantic_ingestion.coverage_recurrence import (
    CoverageRecurrenceGroup,
    CoverageRecurrenceRepository,
    RelationGapSignature,
)
from memorii.core.semantic_ingestion.egress import (
    ProviderEgressDecision,
)
from memorii.core.semantic_ingestion.event_replay import (
    decode_semantic_memory_event_batch,
)
from memorii.core.semantic_ingestion.production_authority import (
    build_verified_production_host_authority,
)
from memorii.core.semantic_ingestion.source_normalization_execution import (
    SourceNormalizationExecutionOwner,
)
from memorii.core.semantic_ingestion.source_normalization_host import (
    SourceNormalizationHostBundle,
    SourceNormalizationHostBundleBuilder,
)
from memorii.core.semantic_ingestion.source_preparation import (
    AtomicStorePreparedSourceRepository,
    InMemoryPreparedSourceRepository,
    TextPreparationService,
)
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
)
from memorii.integrations.authenticated_source import (
    AuthenticatedSourceAdapter,
    AuthenticatedSourceRuntime,
    AuthenticatedSourceSubmission,
)
from memorii.integrations.hermes_provider import HermesMemoryProvider
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import (
    build_prepared_independent_source_analysis,
    build_prepared_source_authority,
)
from tests.fixtures.semantic_ingestion.host_bootstrap_authority import (
    DeterministicTestHostBootstrapMaterialVerifier,
    build_test_host_verified_bootstrap_release_evidence,
    present_authenticated_host_bootstrap_material,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_scenario_test_host_capability,
)
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import accepted_terminal
from tests.fixtures.semantic_ingestion.source_normalization_fixture_builder import (
    DynamicSourceNormalizationAuthorityProvider,
)

TEST_NOW = datetime(2026, 3, 1, tzinfo=UTC)


def _principal() -> DeliveryPrincipalBinding:
    return DeliveryPrincipalBinding.create(
        principal_subject_id="principal:alice",
        tenant_partition_id="tenant:one",
        provider_identity="provider:test",
    )


def _base_ingress() -> AuthenticatedIngressContext:
    principal = _principal()
    scopes = {"task:task:one", "user:user:alice"}
    return AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id=principal.tenant_partition_id, scopes=scopes
        ),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id=principal.tenant_partition_id, scopes=scopes
        ),
        language_declaration="en",
        language_evidence_kind="authenticated_host_declaration",
        language_evidence_trust="trusted",
        language_governance_agreement="agrees",
    )


class _TestHostBootstrapCapability:
    def __init__(self, *, resolver=None, trust_domain="production") -> None:
        release = BootstrapProfileReleaseBuilder.build(enabled=True)
        self._payloads = release.payloads
        self._profile = BootstrapProfileReleaseVerifier.verify(
            payloads=release.payloads, enabled=True
        )
        self._resolver = resolver or _Resolver()
        self._trust_domain = trust_domain

    def load_verified_bootstrap_material(self):
        return HostVerifiedBootstrapMaterial(
            artifact_payloads=self._payloads,
            release_evidence=build_test_host_verified_bootstrap_release_evidence(
                profile=self._profile,
                external_root_digest="2" * 64,
                active_lifecycle_snapshot_digest="3" * 64,
                verified_at=datetime(2026, 1, 1, tzinfo=UTC),
                trust_domain=self._trust_domain,
            ),
            authenticated_ingress_resolver=self._resolver,
            profile_enabled=True,
            trust_domain=self._trust_domain,
        )

    def load_bootstrap_material_presentation(self):
        material = self.load_verified_bootstrap_material()
        return (
            present_authenticated_host_bootstrap_material(material)
            if material is not None
            else None
        )


def _verified_profile():
    material = _TestHostBootstrapCapability().load_verified_bootstrap_material()
    assert material is not None
    return verify_bootstrap_profile(material)


class _CapabilityLoader:
    def __init__(self, capability: object) -> None:
        self.capability = capability

    def load(self):
        return self.capability


class _InstalledCapabilityEntryPoint:
    def __init__(self, capability: object) -> None:
        self.capability = capability

    def load(self):
        return _CapabilityLoader(self.capability)


class _CurrentBootstrapReleaseVerifier:
    """Host fixture authority for the three bootstrap CAS use points."""

    def assert_current(self, *, authorization, release_evidence, assertion_phase):
        body = {
            "coordinate": release_evidence.coordinate.model_dump(mode="python"),
            "signed_release_digest": release_evidence.signed_release_digest,
            "bootstrap_anchor_digest": release_evidence.bootstrap_anchor_digest,
            "active_lifecycle_snapshot_digest": release_evidence.active_lifecycle_snapshot_digest,
            "assertion_phase": assertion_phase,
            "assertion_nonce": f"host-current:{assertion_phase}",
        }
        del authorization
        return CurrentBootstrapReleaseAssertion(
            **body,
            assertion_digest=sha256(
                b"memorii.semantic_ingestion.current_bootstrap_release_assertion.v1\0"
                + encode_typed_value(body)
            ).hexdigest(),
        )


def _verified_runtime_store(
    plane: MemoryPlaneService | None = None,
    *,
    semantic_integrity_lifecycle: PrivilegedSemanticIntegrityLifecycle | None = None,
    semantic_conflict_authority_resolver=None,
):
    plane = plane or MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: TEST_NOW
    )

    def atomic_store() -> SemanticIngestionAtomicStore:
        with patch(
            "memorii.core.memory_plane.store.token_bytes",
            return_value=b"provider-composition-test-key!!!",
        ):
            return SemanticIngestionAtomicStore(
                plane,
                writers,
                now_provider=lambda: TEST_NOW,
                semantic_freeze_guard=(
                    semantic_integrity_lifecycle.freeze_guard if semantic_integrity_lifecycle is not None else None
                ),
                semantic_integrity_incident_reporter=(
                    semantic_integrity_lifecycle.incident_reporter if semantic_integrity_lifecycle is not None else None
                ),
                semantic_integrity_linearization=(
                    semantic_integrity_lifecycle.linearization if semantic_integrity_lifecycle is not None else None
                ),
                current_bootstrap_release_verifier=_CurrentBootstrapReleaseVerifier(),
                semantic_conflict_authority_resolver=semantic_conflict_authority_resolver,
            )

    try:
        current = writers.current()
    except ValueError:
        current = writers.create_initial_evidence_only(
            admission_id="semantic-ingestion",
            writer_implementation_fingerprint="writer",
            graph_schema_fingerprint="schema",
        )
    if current.active_runtime_mode == "verified_semantic":
        return plane, writers, atomic_store()
    binding = writers.commit_binding(current)
    plan = build_migration_plan(
        migration_plan_id="semantic-ingestion:verified",
        source_writer_epoch=1,
        legacy_snapshot_token=sha256(encode_typed_value(())).hexdigest(),
        entries=(),
    )
    checkpoint_values = {
        "migration_plan_id": plan.migration_plan_id,
        "plan_digest": plan.plan_digest,
        "completed_entry_digests": (),
        "target_generation": 1,
    }
    checkpoint = DeliveryCoordinateMigrationCheckpoint(
        **checkpoint_values,
        checkpoint_digest=sha256(encode_typed_value(checkpoint_values)).hexdigest(),
    )
    certificate = certify_migration(plan, checkpoint, independent_verifier_fingerprint="semantic-ingestion-verifier")
    writers.transition(
        expected=binding,
        admission_id="semantic-ingestion:verified",
        runtime_mode="verified_semantic",
        writer_implementation_fingerprint="writer:verified",
        graph_schema_fingerprint="schema",
        migration_activation=activate_migration(plan, certificate),
        migration_plan=plan,
        migration_checkpoint=checkpoint,
        migration_certificate=certificate,
        target_records=(),
    )
    return plane, writers, atomic_store()


def _hex(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _bundle(predicate_id: str | tuple[str, ...] = "works_for") -> SemanticArbitrationPolicyBundle:
    predicate_ids = (predicate_id,) if isinstance(predicate_id, str) else predicate_id
    effective = TimeInterval(start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC))
    trust = TrustPolicySnapshot.create(
        policy_revision="trust-r1",
        system_effective_interval=effective,
        rules=tuple(
            PredicateTrustRule(
                predicate_id=current_predicate_id,
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 10},
            )
            for current_predicate_id in predicate_ids
        ),
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="temporal-r1",
        system_effective_interval=effective,
        rules=tuple(
            PredicateTemporalRule(
                predicate_id=current_predicate_id,
                valid_time_requirement="required",
                allow_open_end=True,
            )
            for current_predicate_id in predicate_ids
        ),
    )
    return SemanticArbitrationPolicyBundle.create(
        trust_policy=trust,
        temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 3, 1, tzinfo=UTC),
    )


def _analysis(
    proposal: SemanticCandidate,
    *,
    source_id: str,
    source_digest: str,
    source_text: str,
    source_authority_evidence,
    source_interval_evidence,
    preparation_fingerprint: str | None = None,
):
    if source_authority_evidence is None:
        return None
    return build_prepared_independent_source_analysis(
        proposal=proposal,
        operation_id=f"prepared-analysis:{proposal.candidate_id}",
        source_id=source_id,
        source_digest=source_digest,
        source_text=source_text,
        source_authority_evidence=source_authority_evidence,
        source_interval_evidence=source_interval_evidence,
        require_text_digest=False,
        preparation_fingerprint=preparation_fingerprint,
    )

class _Resolver:
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime):
        return _base_ingress().model_copy(
            update={
                "semantic_egress_governance": AuthenticatedSemanticEgressGovernance(
                    classification="internal",
                    provider="capture",
                    model="capture-v1",
                    region="local",
                    retention_mode="none",
                    training_use=False,
                ),
                "semantic_source_authority": AuthenticatedSemanticSourceAuthority(
                    authority_class="official",
                    authenticated_provenance_class="host",
                    governing_principal_id="user:user:alice",
                    policy_revision="trust-r1",
                    provenance_digest=_hex("source-authority"),
                ),
                "semantic_source_interval": AuthenticatedSemanticSourceInterval(
                    start=datetime(2026, 1, 1, tzinfo=UTC),
                    end=datetime(2026, 2, 1, tzinfo=UTC),
                    authority_basis="server_source_metadata",
                    provenance_digest=_hex("source-interval"),
                    policy_revision="trust-r1",
                ),
            }
        )


class _AgentBoundResolver(_Resolver):
    """Test host binding an agent identity through authenticated ingress."""

    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime):
        return super().resolve(host_ingress, server_time).model_copy(
            update={"authenticated_agent_id": "agent:alice"}
        )


class _SharedOriginLineageResolver(_Resolver):
    def __init__(self) -> None:
        self.evidence = AuthenticatedOriginLineageEvidence.create(
            authority_digest=_hex("trusted-origin-authority"),
            origin_receipt_digest=_hex("upstream-message-one"),
        )

    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime):
        return super().resolve(host_ingress, server_time).model_copy(
            update={"origin_lineage_evidence": self.evidence}
        )


class _SwitchingIngressResolver:
    """Exercise accepted and rejected ingress through one service composition."""

    def __init__(self) -> None:
        self.reject = False
        self._accepted = _Resolver()

    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime):
        if self.reject:
            raise AuthenticatedIngressResolutionError("rejected")
        return self._accepted.resolve(host_ingress, server_time)


class _CoverageStatusResolver(_Resolver):
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime):
        if host_ingress.provider_identity == "invalid":
            raise AuthenticatedIngressResolutionError("rejected")
        ingress = super().resolve(host_ingress, server_time)
        if host_ingress.provider_identity == "other-agent":
            return ingress.model_copy(
                update={"authenticated_agent_id": "agent:other"}
            )
        if host_ingress.provider_identity == "other-principal":
            return ingress.model_copy(
                update={
                    "delivery_principal_binding": DeliveryPrincipalBinding.create(
                        principal_subject_id="principal:bob",
                        tenant_partition_id="tenant:one",
                        provider_identity="provider:test",
                    )
                }
            )
        if host_ingress.provider_identity == "other-scope":
            scopes = RequiredOutcomeScopeSet.create(
                tenant_partition_id="tenant:one",
                scopes={"task:task:other", "user:user:alice"},
            )
            return ingress.model_copy(
                update={
                    "required_outcome_scopes": scopes,
                    "current_authorized_scopes": scopes,
                }
            )
        return ingress


class _AuthorizedCapability(_TestHostBootstrapCapability):
    def __init__(self, *, runtime: AuthorizedSemanticIngestionRuntime | None = None, runtime_factory=None) -> None:
        super().__init__(resolver=_Resolver())
        self._runtime = runtime
        self._runtime_factory = runtime_factory

    def build_semantic_ingestion_runtime(
        self, *, memory_plane, now_provider, bootstrap_profile
    ):
        del memory_plane, now_provider
        if self._runtime_factory is not None:
            return self._runtime_factory(bootstrap_profile=bootstrap_profile)
        del bootstrap_profile
        return self._runtime


class _LocalRuntimeCapability(_TestHostBootstrapCapability):
    """Host capability whose only semantic construction is the production root."""

    def __init__(self, *, source_normalization_authority_provider=None, source_normalization_execution_owner=None) -> None:
        super().__init__(resolver=_Resolver())
        self.stores: list[SemanticIngestionAtomicStore] = []
        self._source_normalization_authority_provider = source_normalization_authority_provider
        self._source_normalization_execution_owner = source_normalization_execution_owner

    def build_semantic_ingestion_runtime(
        self, *, memory_plane, now_provider, bootstrap_profile
    ):
        del now_provider
        _, writers, store = _verified_runtime_store(memory_plane)
        self.stores.append(store)
        runtime = build_authorized_local_semantic_runtime(
            authorization_bytes=b"signed-test-authorization",
            authorization_verifier=_AuthorizationVerifier(),
            policy_provider=_PolicyProvider("owner_is"),
            writer_admission=writers,
            atomic_store=store,
            bootstrap_profile=bootstrap_profile,
        )
        return replace(
            runtime,
            source_normalization_host_bundle=(
                None
                if self._source_normalization_authority_provider is None
                else SourceNormalizationHostBundle(
                    authority_provider=self._source_normalization_authority_provider,
                    execution_owner=self._source_normalization_execution_owner,
                )
            ),
        )


class _RecordingSourceNormalizationAuthorityProvider:
    """Explicit host authority provider used to prove the coordinator boundary."""

    def __init__(self, *, available: bool = True) -> None:
        self.invocations = []
        self._available = available

    def build(self, *, invocation, handoff):
        self.invocations.append((invocation, handoff))
        return object() if self._available else None


class _RecordingSourceNormalizationExecutionOwner:
    """Real coordinator boundary spy; execution-owner internals have dedicated tests."""

    def __init__(self, *, result=None) -> None:
        self.calls = []
        self._result = result

    def normalize_after_bootstrap_handoff(self, *, invocation, handoff, authority):
        self.calls.append((invocation, handoff, authority))
        return self._result


class _PolicyProvider:
    def __init__(self, predicate_id: str | tuple[str, ...] = "works_for", *, outage: bool = False) -> None:
        self.predicate_id = predicate_id
        self.outage = outage

    def current_policy(self, *, source_id: str, source_digest: str):
        if self.outage:
            raise OSError("policy unavailable")
        return SemanticPipelinePolicy(arbitration_bundle=_bundle(self.predicate_id))


class _EgressProvider:
    def current(self, *, binding, at: datetime):
        return ProviderEgressDecision.create(
            binding=binding,
            policy_id="capture-policy",
            policy_revision=1,
            policy_fingerprint="f" * 64,
            expires_at=at + timedelta(minutes=1),
        )


class _StableEgressProvider:
    def current(self, *, binding, at: datetime):
        del at
        return ProviderEgressDecision.create(
            binding=binding,
            policy_id="capture-policy",
            policy_revision=1,
            policy_fingerprint="f" * 64,
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )




class _CaptureTransport:
    def __init__(self) -> None:
        candidate = SemanticCandidate(
            candidate_id="candidate",
            operation_kind="fact",
            predicate_id="works_for",
            assertion_quote="Atlas owner is Bob.",
            alignment_refs=(),
        )
        self.response = encode_typed_value({"candidates": [candidate.model_dump(mode="python")]})
        self.requests: list[bytes] = []

    def propose(self, request_bytes: bytes) -> bytes:
        self.requests.append(request_bytes)
        return self.response


class _OutageTransport(_CaptureTransport):
    def propose(self, request_bytes: bytes) -> bytes:
        self.requests.append(request_bytes)
        raise OSError("proposal transport unavailable")


class _Assessor:
    def analyze(
        self,
        *,
        proposal: SemanticCandidate,
        source_id: str,
        source_digest: str,
        source_text: str,
        prepared_source,
        source_authority_evidence,
        source_interval_evidence,
    ):
        return _analysis(
            proposal,
            source_id=source_id,
            source_digest=source_digest,
            source_text=source_text,
            source_authority_evidence=source_authority_evidence,
            source_interval_evidence=source_interval_evidence,
            preparation_fingerprint=prepared_source.preparation_fingerprint,
        )


class _CountingAssessor(_Assessor):
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, **kwargs):
        self.calls += 1
        return super().analyze(**kwargs)


class _OutageAssessor:
    def analyze(self, **_: object):
        raise OSError("analysis transport unavailable")


class _AbstainAssessor:
    def analyze(self, **_: object):
        return None


class _AuthorizationVerifier:
    def __init__(self, mode: str = "valid") -> None:
        self.mode = mode

    def verify(self, *, authorization_bytes, use, server_time):
        if self.mode == "outage":
            raise OSError("deployment authorization unavailable")
        if self.mode == "revoked":
            return None
        body = {
            "authorization_digest": ("0" * 64 if self.mode == "mutated" else sha256(authorization_bytes).hexdigest()),
            "target_profile_manifest_digest": use.profile_manifest_digest,
            "verified_bootstrap_release_digest": use.verified_bootstrap_release_digest,
            "deployment_artifact_digest": "d" * 64,
            "authority_snapshot_digest": "a" * 64,
            "active_epoch": 1,
            "expires_at": (
                datetime(2020, 1, 1, tzinfo=UTC) if self.mode == "expired" else datetime(2030, 1, 1, tzinfo=UTC)
            ),
            "signer_id": "test-signer",
        }
        return SemanticIngestionRuntimeAuthorization(
            **body,
            decision_digest=contract_digest(b"memorii.semantic-ingestion.verified-deployment-authorization.v1", body),
        )


def _host_ingress() -> AuthenticatedHostIngress:
    return AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )


def _dependencies(
    *,
    writer_admission=None,
    atomic_store=None,
    authorization_mode="valid",
    assessor=None,
):
    transport = _CaptureTransport()
    prepared_sources = (
        AtomicStorePreparedSourceRepository(
            atomic_store=atomic_store,
            writer_binding=lambda: writer_admission.commit_binding(writer_admission.current()),
        )
        if atomic_store is not None and writer_admission is not None
        else InMemoryPreparedSourceRepository()
    )
    preparation_policy = TextPreparationPolicy.create(
        max_segment_characters=4096,
        supported_languages=("en",),
        segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1",
        context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1",
    )
    runtime = AuthorizedSemanticIngestionRuntime(
        authorization_bytes=b"signed-test-authorization",
        authorization_verifier=_AuthorizationVerifier(authorization_mode),
        policy_provider=_PolicyProvider(),
        text_preparation_service=TextPreparationService(
            producer=lambda request: build_prepared_source_authority(
                source_id=request.observation.source_id,
                source_digest=request.observation.source_digest or "",
                source_text=request.observation.text,
                preparation_policy=request.policy,
            ),
            repository=prepared_sources,
        ),
        prepared_source_repository=prepared_sources,
        text_preparation_policy=preparation_policy,
        writer_admission=writer_admission,
        atomic_store=atomic_store,
    )
    return transport, _AuthorizedCapability(runtime=runtime)


def _runtime_factory_for_outage(*, writers, store, stage: str):
    """Build the failed-ingestion runtime with the profile's own corpus.

    The failed sync must first hand off (durable prepared source, control,
    and marker) before its semantic pass fails closed at the absent
    normalization bundle, so the recovery tests have a retained operation
    to reconcile.  The grammar-proof-bound preparation seam comes from the
    runtime builder with the verified bootstrap profile.
    """
    def factory(*, bootstrap_profile) -> AuthorizedSemanticIngestionRuntime:
        return build_authorized_local_semantic_runtime(
            authorization_bytes=b"signed-test-authorization",
            authorization_verifier=_AuthorizationVerifier(),
            policy_provider=_PolicyProvider(outage=stage == "policy_read"),
            writer_admission=writers,
            atomic_store=store,
            bootstrap_profile=bootstrap_profile,
        )
    return factory








class _UnusedNormalizationQuoteAuthority:
    def resolve(self, quote, context, owned):
        raise AssertionError("construction proof must not resolve quotes")

    def verify_quote(self, **kwargs):
        raise AssertionError("construction proof must not verify quotes")


class _SingleTextQuoteAuthority:
    def resolve(self, quote, context, owned):
        del owned
        text = "Atlas owner is Bob."
        start = text.find(quote, context.projection_span.start, context.projection_span.end)
        if start < 0 or text.find(quote, start + 1, context.projection_span.end) >= 0:
            raise ValueError("fixture quote must resolve exactly once")
        projection, local = context.projection_span, context.segment_local_span
        return type(context).create(
            source_id=context.source_id, projection_digest=context.projection_digest,
            projection_segment_id=context.projection_segment_id,
            retained_text_artifact=context.retained_text_artifact,
            projection_span=type(projection).create(artifact=projection.artifact, start=start, end=start + len(quote), substring_digest=sha256(quote.encode()).hexdigest()),
            segment_local_span=type(local).create(artifact=local.artifact, start=start, end=start + len(quote), substring_digest=sha256(quote.encode()).hexdigest()),
            text_mapping_proof=context.text_mapping_proof, source_reference=quote,
        )

    def verify_quote(self, *, projection_digest, quote, span):
        if projection_digest != span.projection_digest or "Atlas owner is Bob."[span.projection_span.start:span.projection_span.end] != quote:
            raise ValueError("fixture quote is not exact")


def _v3_normalization_host_builder(
    *,
    proposal: ProviderSemanticProposal | None = None,
    proposal_ref: list[ProviderSemanticProposal] | None = None,
) -> tuple[SourceNormalizationHostBundleBuilder, dict[str, int]]:
    """Build a complete V3-only host bundle for the ordinary provider root."""
    proposal_value = proposal or ProviderSemanticProposal(abstained=True)
    quotes = _UnusedNormalizationQuoteAuthority() if proposal is None else _SingleTextQuoteAuthority()
    calls = {"proposal": 0, "stanza": 0, "spacy": 0, "predicate": 0, "temporal": 0}

    def selected_proposal() -> ProviderSemanticProposal:
        return proposal_value if proposal_ref is None else proposal_ref[0]

    authority_provider = DynamicSourceNormalizationAuthorityProvider(
        proposal_factory=lambda _source, _request: selected_proposal(),
        retry_policy_fingerprint="a" * 64,
    )
    monotonic_ticks = iter(range(1, 10_000))

    def proposal(_request):
        calls["proposal"] += 1
        value = selected_proposal()
        return value, encode_typed_value(value.model_dump(mode="python"))

    def linguistic(request, name: str) -> LinguisticAnalysis:
        calls[name] += 1
        token = LinguisticToken.create(
            source_span=request.segment.context_text,
            surface_text="fixture",
            lemma="fixture",
            upos="NOUN",
            xpos=None,
            morphological_features=(),
            sentence_index=0,
            word_index=0,
            syntactic_word_index=0,
            multi_word_token_span=None,
        )
        dependency = DependencyArc.create(
            dependent_token_id=token.token_id,
            governor_token_id=None,
            relation="root",
            enhanced=False,
        )
        return LinguisticAnalysis.create(
            source_id=request.segment.source_id,
            source_digest=request.segment.source_digest,
            preparation_fingerprint=request.segment.preparation_fingerprint,
            segment_id=request.segment.segment_id,
            segment_language_route_digest=request.segment.bootstrap_projection.bootstrap_route.route_digest,
            analyzer_manifest_digest=request.analyzer_manifest.manifest_digest,
            analyzer_fingerprint=request.analyzer_manifest.analyzer_fingerprint,
            language="en",
            tokens=(token,), mentions=(), clauses=(), dependencies=(dependency,), status="complete", diagnostics=(),
        )

    def predicate(request):
        calls["predicate"] += 1
        segment, provenance = request.segment, request.bootstrap_analysis_provenance
        return BootstrapPredicateLanePayloadV3.create(
            source_id=segment.source_id, source_digest=segment.source_digest,
            preparation_fingerprint=segment.preparation_fingerprint, segment_id=segment.segment_id,
            bootstrap_analysis_provenance=provenance,
            detector_manifest_digest=request.predicate_event_manifest.manifest_digest,
            detector_fingerprint=request.predicate_event_manifest.manifest_digest,
            candidates=(), status="complete", reason_codes=(),
        )

    def temporal(request):
        calls["temporal"] += 1
        segment, provenance = request.segment, request.bootstrap_analysis_provenance
        return BootstrapTemporalLanePayloadV3.create(
            source_id=segment.source_id, source_digest=segment.source_digest,
            preparation_fingerprint=segment.preparation_fingerprint, segment_id=segment.segment_id,
            bootstrap_analysis_provenance=provenance,
            resolver_manifest_digest=request.resolver_manifest.manifest_digest,
            resolver_fingerprint=request.resolver_manifest.manifest_digest,
            candidates=(), ambiguities=(), status="complete", reason_codes=(),
        )

    return SourceNormalizationHostBundleBuilder(
        authority_provider=authority_provider,
        resolve_quote=quotes.resolve, projection_quote_verifier=quotes,
        server_time=lambda: TEST_NOW, monotonic_tick=lambda: next(monotonic_ticks),
        bootstrap_v3_proposal_transport=proposal,
        bootstrap_v3_stanza=lambda request: linguistic(request, "stanza"),
        bootstrap_v3_spacy=lambda request: linguistic(request, "spacy"),
        bootstrap_v3_predicate_event_detection=predicate,
        bootstrap_v3_temporal_resolution=temporal,
        bootstrap_v3_linguistic_request=lambda request, lane_name: authority_provider
        .bootstrap_v3_authority_for(request).linguistic_request(request, lane_name),
        bootstrap_v3_predicate_request=lambda request: authority_provider
        .bootstrap_v3_authority_for(request).predicate_request(request),
        bootstrap_v3_temporal_request=lambda request: authority_provider
        .bootstrap_v3_authority_for(request).temporal_request(request),
    ), calls


def _built_in_local_capability(
    *, verifier=None, normalization_builder=None, resolver=None,
    structured_submission_authority_resolver=None, scenario_test=False,
    predicate_id="owner_is",
):
    material = _TestHostBootstrapCapability(
        resolver=resolver or _Resolver(),
        trust_domain="scenario_test" if scenario_test else "production",
    ).load_verified_bootstrap_material()
    assert material is not None
    if structured_submission_authority_resolver is not None:
        material = replace(
            material,
            structured_submission_authority_resolver=structured_submission_authority_resolver,
            structured_submission_authority_resolver_binding_digest=(
                structured_submission_authority_resolver.resolver_binding_digest
            ),
        )
    return BuiltInLocalHostSemanticIngestionCapability(
        bootstrap_material_presentation=present_authenticated_host_bootstrap_material(material),
        authorization_bytes=b"signed-test-authorization",
        authorization_verifier=_AuthorizationVerifier(),
        policy_provider=_PolicyProvider(predicate_id),
        current_bootstrap_release_verifier=(
            _CurrentBootstrapReleaseVerifier() if verifier is None else verifier
        ),
        source_normalization_host_bundle_builder=normalization_builder,
    )


def _configured_registry_history() -> ProtectedTypedValueRegistryHistory:
    profile = CompiledProfile(
        "semantic_ingestion_typed_value", "3", "operational-3", "a" * 64, "b" * 64
    )
    entry = CompiledRegistryEntry(
        profile, "MemoryScope", "1", "c" * 64,
        CompiledPolicyDigests("d" * 64, "e" * 64, "f" * 64, "0" * 64),
        "1" * 64, "memorii.semantic_ingestion.observation.MemoryScope.v1",
        "2" * 64, "3" * 64, "4" * 64, "active",
    )
    registry = CompiledTypedValueRegistry(profile, (entry,), "5" * 64, ())
    snapshot = DecoderSourceSnapshot(entry.decoder_id, entry.implementation_source_digest, ())
    sources = VerifiedDecoderSourceManifest(
        DecoderSourceManifest(b"{}", "6" * 64, profile.profile_id, profile.profile_version, ()),
        (), (snapshot,),
    )
    manifest = TypedValuePublicationManifest(
        b"{}", "7" * 64, profile.profile_id, profile.profile_version, (), "6" * 64,
        (PublicationDecoderSourceSnapshot(entry.decoder_id, snapshot.source_snapshot_digest),), registry.registry_digest,
    )
    pins = ProtectedTypedValuePublicationPins(
        manifest.publication_digest, registry.registry_digest,
        (DecoderSourceSnapshotPin(entry.decoder_id, snapshot.source_snapshot_digest),), "8" * 64,
    )
    return ProtectedTypedValueRegistryHistory((VerifiedTypedValuePublication(registry, sources, manifest, pins, "8" * 64),))


def _small_real_configured_registry_material(tmp_path: Path) -> ProtectedTypedValueRegistryConfiguration:
    def raw(value: object) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    grammar = {
        "role": "grammar", "profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "grammar_revision": "operational-3",
        "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"},
        "envelope": {"binding_fields": ["profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"], "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"], "permitted_value_kinds": ["bytes", "integer", "map", "scalar"]},
        "tags": {"bytes": "rfc4648_standard_padded", "datetime": "utc_six_fractional_digits", "duration_microseconds": "signed_i64", "enum": "registered_qualified_member", "frozenset": "canonical_member_byte_order", "integer": "canonical_decimal_string", "list": "declared_order", "map": "encoded_json_string_key_order", "set": "canonical_member_byte_order", "tuple": "declared_order"},
        "type_rules": {"bool_as_integer": False, "defaults_before_verification": False, "float_decimal": False, "map_keys": "string_only", "model_fields": "registered_exact", "optional": "registered_policy", "union": "one_registered_discriminator"},
    }
    common = {"schema_id": "MemoryScope", "schema_version": "1"}
    fields = [{"name": name, "type": {"kind": "string", "lexical_rule": "unicode_scalar"}, "integrity_role": "ordinary"} for name in ("session_id", "task_id", "user_id")]
    roles = (
        raw(grammar), raw({"role": "schema", **common, "root_kind": "model", "fields": fields}),
        raw({"role": "enum", **common, "enums": []}), raw({"role": "optional", **common, "fields": [{"field_name": name, "policy": "required_nullable"} for name in ("session_id", "task_id", "user_id")]}),
        raw({"role": "numeric", **common, "fields": []}), raw({"role": "digest-signature", **common, "policy": {"kind": "ordinary"}}), raw({"role": "upcast", **common, "target_binding": None, "upcaster_id": None, "implementation_source_digest": None}),
    )
    (tmp_path / "decoder").mkdir()
    (tmp_path / "decoder" / "native.py").write_bytes(b"def decode(value):\n    return value\n")
    limits = ProtectedTypedValuePublicationLimits(
        ProtectedDeclarationParseLimits(20_000, 300, 30),
        ProtectedDecoderSourceManifestLimits(20_000, 300, 30, 10, 20_000), 20_000,
    )
    package = author_typed_value_publication_package(
        roles, (DecoderSourceSelection("memorii.semantic_ingestion.observation.MemoryScope.v1", "native", "decoder/native.py"),), source_package_root=tmp_path, limits=limits,
    )
    raw_vector = b'{"independent":"configured-registry"}'
    manifest = parse_typed_value_publication_manifest(package.raw_publication_manifest, maximum_bytes=20_000)
    pins = ProtectedTypedValuePublicationPins(
        manifest.publication_digest,
        manifest.registry_digest,
        tuple(
            DecoderSourceSnapshotPin(item.decoder_id, item.source_snapshot_digest)
            for item in manifest.decoder_source_snapshots
        ),
        sha256(raw_vector).hexdigest(),
    )
    return ProtectedTypedValueRegistryConfiguration((
        ProtectedTypedValueRegistryPublicationConfiguration(
            package.raw_role_sources, package.raw_decoder_source_manifest,
            package.raw_publication_manifest, raw_vector, tmp_path, limits, pins,
        ),
    ))


def test_configured_registry_verifies_real_package_and_rejects_wrong_pin(tmp_path: Path) -> None:
    configuration = _small_real_configured_registry_material(tmp_path)
    history = verify_configured_typed_value_registry_history(configuration)
    assert len(history.publications[0].compiled_registry.entries) == 1
    publication = configuration.publications[0]
    bad = replace(
        publication,
        pins=replace(publication.pins, publication_digest="0" * 64),
    )
    with pytest.raises(TypedValueRegistryConfigurationError):
        verify_configured_typed_value_registry_history(
            ProtectedTypedValueRegistryConfiguration((bad,))
        )
    with pytest.raises(TypedValueRegistryConfigurationError):
        verify_configured_typed_value_registry_history(
            ProtectedTypedValueRegistryConfiguration((
                replace(publication, source_package_root=Path("/missing-configured-source-root")),
            ))
        )
    with pytest.raises(TypedValueRegistryConfigurationError):
        ProtectedTypedValueRegistryPublicationConfiguration(
            cast(tuple[bytes, ...], [b"mutable"]), publication.raw_decoder_source_manifest,
            publication.raw_publication_manifest,
            publication.raw_independent_vector_manifest,
            publication.source_package_root, publication.limits, publication.pins,
        )


def test_builtin_provider_composition_verifies_configured_registry_once_and_preserves_identity(tmp_path: Path) -> None:
    configuration = _small_real_configured_registry_material(tmp_path)
    verifier = patch(
        "memorii.core.semantic_ingestion.capability.verify_configured_typed_value_registry_history",
        wraps=verify_configured_typed_value_registry_history,
    )
    with verifier as verify:
        service = ProviderMemoryService(
            memory_plane=MemoryPlaneService(), now_provider=lambda: TEST_NOW,
            host_bootstrap_capability=replace(
                _built_in_local_capability(),
                typed_value_registry_configuration=configuration,
            ),
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )
    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None
    verify.assert_called_once()
    history = runtime.typed_value_registry_history
    assert history is not None
    assert service._semantic_writer_admission._typed_value_registry_history is history
    assert service._semantic_atomic_store._typed_value_registry_history is history


def test_invalid_configured_registry_fails_before_built_in_runtime_owners(tmp_path: Path) -> None:
    configuration = _small_real_configured_registry_material(tmp_path)
    publication = configuration.publications[0]
    plane = MemoryPlaneService()
    capability = replace(
        _built_in_local_capability(),
        typed_value_registry_configuration=ProtectedTypedValueRegistryConfiguration((
            replace(publication, pins=replace(publication.pins, publication_digest="0" * 64)),
        )),
    )
    with patch(
        "memorii.core.memory_evolution.writer_admission.SemanticWriterAdmissionStore"
    ) as writers, pytest.raises(TypedValueRegistryConfigurationError):
        ProviderMemoryService(
            memory_plane=plane, now_provider=lambda: TEST_NOW,
            host_bootstrap_capability=capability,
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )
    writers.assert_not_called()
    assert plane.get_record(writer_admission_memory_id()) is None


def test_direct_runtime_rejects_substituted_configured_registry_history() -> None:
    plane = MemoryPlaneService()
    history = _configured_registry_history()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(),
        typed_value_registry_history=history,
    )
    store = SemanticIngestionAtomicStore(
        plane, writers, typed_value_registry_history=history,
    )
    with pytest.raises(TypedValueRegistryConfigurationError, match="writer registry history differs"):
        AuthorizedSemanticIngestionRuntime(
            authorization_bytes=b"signed-test-authorization",
            authorization_verifier=_AuthorizationVerifier(),
            policy_provider=_PolicyProvider("owner_is"),
            writer_admission=writers,
            atomic_store=store,
            typed_value_registry_history=_configured_registry_history(),
        )
    with pytest.raises(TypedValueRegistryConfigurationError, match="requires writer and atomic store"):
        AuthorizedSemanticIngestionRuntime(
            authorization_bytes=b"signed-test-authorization",
            authorization_verifier=_AuthorizationVerifier(),
            policy_provider=_PolicyProvider("owner_is"),
            typed_value_registry_history=history,
        )
    with pytest.raises(TypedValueRegistryConfigurationError, match="writer registry history differs"):
        AuthorizedSemanticIngestionRuntime(
            authorization_bytes=b"signed-test-authorization",
            authorization_verifier=_AuthorizationVerifier(),
            policy_provider=_PolicyProvider("owner_is"),
            writer_admission=writers,
            atomic_store=store,
        )


def test_custom_runtime_builder_cannot_downgrade_a_registry_substitution_to_fallback() -> None:
    plane = MemoryPlaneService()
    history = _configured_registry_history()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(),
        typed_value_registry_history=history,
    )
    store = SemanticIngestionAtomicStore(
        plane, writers, typed_value_registry_history=history,
    )

    def substituted_runtime(*, bootstrap_profile):
        del bootstrap_profile
        return AuthorizedSemanticIngestionRuntime(
            authorization_bytes=b"signed-test-authorization",
            authorization_verifier=_AuthorizationVerifier(),
            policy_provider=_PolicyProvider("owner_is"),
            writer_admission=writers,
            atomic_store=store,
            typed_value_registry_history=_configured_registry_history(),
        )

    with pytest.raises(TypedValueRegistryConfigurationError):
        ProviderMemoryService(
            memory_plane=plane,
            host_bootstrap_capability=_AuthorizedCapability(
                runtime_factory=substituted_runtime
            ),
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )


def test_builtin_local_capability_wires_provider_hermes_and_filesystem_without_entrypoint_patch(
    tmp_path,
) -> None:
    provider = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    hermes = HermesMemoryProvider(
        ProviderMemoryService(
            now_provider=lambda: TEST_NOW,
            host_bootstrap_capability=_built_in_local_capability(),
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )
    )
    filesystem = build_filesystem_provider(
        tmp_path / "builtin-local",
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    factory = build_provider_memory_service_from_env(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )

    for service in (provider, factory, hermes._service, filesystem):
        assert service._bootstrap_profile is not None
        assert service._provider_ingestion._semantic_runtime is not None
        runtime = service._provider_ingestion._semantic_runtime
        assert runtime.atomic_store is service._semantic_atomic_store
        assert runtime.writer_admission is service._semantic_writer_admission
        assert isinstance(runtime.prepared_source_repository, AtomicStorePreparedSourceRepository)
        assert runtime.text_preparation_service is not None
        assert service._semantic_atomic_store._current_bootstrap_release_verifier is not None
        assert service._memory_plane.get_record(writer_admission_memory_id()) is None

    for service, operation_id in ((provider, "builtin-direct"), (factory, "builtin-factory"), (filesystem, "builtin-filesystem")):
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id=operation_id,
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
        assert service._memory_plane.get_record(writer_admission_memory_id()) is not None
    hermes.sync_turn(
        "Atlas owner is Bob.",
        "Noted.",
        operation_id="builtin-hermes",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert hermes._service._memory_plane.get_record(writer_admission_memory_id()) is not None


def test_configured_public_roots_construct_the_real_normalization_execution_owner(tmp_path) -> None:
    """Every public root reaches the one concrete host-bundle construction call."""
    # One fresh builder per root: the dynamic authority provider binds its
    # publication-lease lookup to one store per bundle.
    verifier = DeterministicTestHostBootstrapMaterialVerifier()
    direct = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=verifier,
        source_normalization_host_bundle_builder=_v3_normalization_host_builder()[0],
    )
    factory = build_provider_memory_service_from_env(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=verifier,
        source_normalization_host_bundle_builder=_v3_normalization_host_builder()[0],
    )
    filesystem = build_filesystem_provider(
        tmp_path / "configured-normalization-root",
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=verifier,
        source_normalization_host_bundle_builder=_v3_normalization_host_builder()[0],
    )
    hermes = HermesMemoryProvider(
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=verifier,
        source_normalization_host_bundle_builder=_v3_normalization_host_builder()[0],
    )

    for service in (direct, factory, filesystem, hermes._service):
        runtime = service._provider_ingestion._semantic_runtime
        assert runtime is not None
        assert runtime.source_normalization_host_bundle is not None
        assert isinstance(
            runtime.source_normalization_host_bundle.execution_owner,
            SourceNormalizationExecutionOwner,
        )


def _direct_v3_recovery_probe(service: ProviderMemoryService) -> object:
    marker_record = service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_handoff_marker"
    )[0]
    marker = marker_record.content["marker"]
    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None and runtime.prepared_source_repository is not None
    prepared = runtime.prepared_source_repository.load(
        source_id=marker["source_id"], source_digest=marker["source_digest"]
    )
    assert prepared is not None
    key_body = {
        "source_id": prepared.source_id,
        "source_digest": prepared.source_digest,
        "preparation_fingerprint": prepared.preparation_fingerprint,
        "operation_id": marker["operation_fence_binding"]["operation_id"],
        "operation_fence_digest": marker["operation_fence_binding"]["binding_digest"],
        "bootstrap_profile_manifest_digest": marker["release_evidence_digest"],
        "handoff_request_digest": marker["handoff_request_digest"],
    }
    key = BootstrapRecoveryKeyV3(
        **key_body,
        recovery_key_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-key.v3", key_body
        ),
    )
    probe_body = {
        "recovery_key": key,
        "handoff_marker_digest": marker["marker_digest"],
        "expected_predecessor_operation_generation": marker["expected_predecessor_operation_generation"],
        "expected_predecessor_artifact_generation": marker["expected_predecessor_artifact_generation"],
        "expected_predecessor_control_digest": marker["expected_predecessor_control_digest"],
    }
    probe = BootstrapRecoveryProbeV3(
        **probe_body,
        probe_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-probe.v3", probe_body
        ),
    )
    assert runtime.source_normalization_host_bundle is not None
    bundle = runtime.source_normalization_host_bundle
    result = bundle.recovery_repository.probe(
        probe=probe, server_time=TEST_NOW, monotonic_tick=1
    )
    return type(result).__name__, getattr(result, "reason", None)


def test_direct_provider_root_publishes_and_reloads_bootstrap_v3_normalization() -> None:
    """The public provider root reaches the V3 owner and its atomic reload."""
    builder, calls = _v3_normalization_host_builder(
        proposal=_bob_owner_proposal()
    )
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
    )
    selection_repository = service._provider_ingestion._catalog_selection_repository
    assert selection_repository is not None
    # Simulate a source retained by a pre-observation revision. Its exact retry
    # must preserve the admission tuple and backfill the current observation.
    service._provider_ingestion._catalog_selection_repository = None
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="provider-v3-normalization",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.blocked_reasons.get("semantic_ingestion") != "source_alignment_authority_unavailable", (
        _direct_v3_recovery_probe(service),
        calls,
        tuple(
            record.source_kind
            for record in service._memory_plane.list_records()
            if "bootstrap" in record.source_kind or "prepared" in record.source_kind
        ),
        tuple(
            (
                record.content["state"], record.content.get("claim_digest"),
                record.content.get("claim_nonce"), record.content.get("renewal_count"),
                record.content.get("expires_monotonic_tick"),
            )
            for record in service._memory_plane.list_records(
                source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
            )
        ),
        tuple(
            (
                record.content["marker"]["recovery_key_digest"],
                    record.content["marker"]["expected_predecessor_operation_generation"],
                    record.content["marker"]["expected_predecessor_artifact_generation"],
            )
            for record in service._memory_plane.list_records(
                source_kind="semantic_ingestion_bootstrap_handoff_marker"
            )
        ),
    )
    assert calls == {"proposal": 1, "stanza": 1, "spacy": 1, "predicate": 1, "temporal": 1}
    store = service._semantic_atomic_store
    assert store.bootstrap_v3_recovery_snapshot()
    coverage_records = service._memory_plane.list_records(
        source_kind="learned_ontology_coverage_observation_v1"
    )
    assert coverage_records == []
    assert not [
        record
        for record in service._memory_plane.list_records()
        if record.source_kind in {
            "learned_ontology_change_proposal_v1",
            "learned_ontology_gap_fact_v1",
        }
    ]
    # A lost acknowledgement retries the same public operation.  Found must
    # reload the V3 closure before authority or any of the five learned lanes.
    service._provider_ingestion._catalog_selection_repository = selection_repository
    retry = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="provider-v3-normalization",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert retry.blocked_reasons.get("semantic_ingestion") != "source_alignment_authority_unavailable"
    assert calls == {"proposal": 1, "stanza": 1, "spacy": 1, "predicate": 1, "temporal": 1}
    coverage_records = service._memory_plane.list_records(
        source_kind="learned_ontology_coverage_observation_v1"
    )
    assert len(coverage_records) == 1
    coverage = CoverageObservationRepository(service._memory_plane).load(
        coverage_records[0].memory_id
    )
    assert coverage is not None
    assert coverage.processing_state == DiscoveryProcessingState.PENDING_NO_CAPABILITY
    assert coverage.semantic_outcome == CoverageSemanticOutcome.NOT_EVALUATED
    status = service.list_ontology_coverage_statuses(
        authenticated_host_ingress=_host_ingress()
    )
    assert status.status == "ok"
    assert len(status.observations) == 1
    assert (
        status.observations[0].processing_state
        == DiscoveryProcessingState.PENDING_NO_CAPABILITY
    )
    assert status.observations[0].semantic_outcome == CoverageSemanticOutcome.NOT_EVALUATED
    assert "Atlas owner is Bob" not in status.model_dump_json()
    assert coverage.source_id not in status.model_dump_json()

    class _RotatedCatalog:
        def resolve_selected_base(self):
            selected = selection_repository.resolve_selected_base()
            return selected.model_copy(update={"catalog_digest": "f" * 64})

        def resolve_selected_bundle(self):
            selected = self.resolve_selected_base()
            return SimpleNamespace(
                catalog=selected,
                version=SimpleNamespace(version_digest="f" * 64),
            )

    service._provider_ingestion._catalog_selection_repository = _RotatedCatalog()
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="provider-v3-normalization",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    rotated_records = service._memory_plane.list_records(
        source_kind="learned_ontology_coverage_observation_v1"
    )
    assert len(rotated_records) == 2
    assert coverage.observation_id in {record.memory_id for record in rotated_records}

    # A crash after the first admission CAS cannot lose the initial pending
    # member. The separate reobservation write is only a retry/backfill path.
    service._provider_ingestion._catalog_selection_repository = selection_repository
    with (
        patch.object(
            CoverageObservationRepository,
            "create",
            side_effect=OSError("injected post-admission failure"),
        ),
        pytest.raises(OSError, match="post-admission failure"),
    ):
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id="provider-v3-normalization-crash",
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
    assert len(
        service._memory_plane.list_records(
            source_kind="learned_ontology_coverage_observation_v1"
        )
    ) == 3


def test_concurrent_first_admission_recovers_across_catalog_rotation() -> None:
    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
    )
    selection_repository = service._provider_ingestion._catalog_selection_repository
    assert selection_repository is not None
    selected = selection_repository.resolve_selected_base()
    selected_bundle = selection_repository.resolve_selected_bundle()
    catalog_digests = (selected_bundle.version.version_digest, "f" * 64)
    selection_lock = Lock()
    selection_count = 0

    class _RotatingCatalog:
        def resolve_selected_base(self):
            return selected

        def resolve_selected_bundle(self):
            nonlocal selection_count
            with selection_lock:
                digest = catalog_digests[min(selection_count, 1)]
                selection_count += 1
            return selected_bundle.model_copy(
                update={
                    "version": selected_bundle.version.model_copy(
                        update={"version_digest": digest}
                    )
                }
            )

    service._provider_ingestion._catalog_selection_repository = _RotatingCatalog()
    replay_barrier = Barrier(2)
    replay_lock = Lock()
    replay_count = 0
    original_replay = service._provider_ingestion._admission_service.replay_retained_source

    def replay_together(*args, **kwargs):
        nonlocal replay_count
        retained = original_replay(*args, **kwargs)
        with replay_lock:
            replay_count += 1
            ordinal = replay_count
        if retained is None and ordinal <= 2:
            replay_barrier.wait(timeout=10)
        return retained

    first_catalog_published = Event()
    original_publish = service._semantic_atomic_store.publish_admitted_source

    def publish_in_catalog_order(*, prepared, writer_binding):
        coverage = next(
            (
                record
                for record in prepared.records
                if record.source_kind == "learned_ontology_coverage_observation_v1"
            ),
            None,
        )
        digest = (
            None
            if coverage is None
            else coverage.content["observation"]["catalog_digest"]
        )
        if digest == catalog_digests[1]:
            assert first_catalog_published.wait(timeout=30)
        try:
            return original_publish(prepared=prepared, writer_binding=writer_binding)
        finally:
            if digest == catalog_digests[0]:
                first_catalog_published.set()

    with (
        patch.object(
            service._provider_ingestion._admission_service,
            "replay_retained_source",
            side_effect=replay_together,
        ),
        patch.object(
            service._semantic_atomic_store,
            "publish_admitted_source",
            side_effect=publish_in_catalog_order,
        ),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        futures = tuple(
            executor.submit(
                service.sync_event,
                operation=ProviderOperation.CHAT_USER_TURN,
                content="Atlas owner is Bob.",
                operation_id="provider-concurrent-catalog-rotation",
                task_id="task:one",
                user_id="user:alice",
                authenticated_host_ingress=_host_ingress(),
            )
            for _ in range(2)
        )
        results = tuple(future.result(timeout=180) for future in futures)

    assert all(result.transcript_ids for result in results)
    observations = tuple(
        CoverageObservationRepository(service._memory_plane).load(record.memory_id)
        for record in service._memory_plane.list_records(
            source_kind="learned_ontology_coverage_observation_v1"
        )
    )
    assert len(observations) == 2
    assert {observation.catalog_digest for observation in observations if observation} == set(
        catalog_digests
    )


def test_authenticated_origin_coalesces_direct_and_forwarded_deliveries() -> None:
    resolver = _SharedOriginLineageResolver()
    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(
            resolver=resolver, scenario_test=True
        ),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
    )

    for provider_identity, content, operation_id in (
        ("adapter:direct", "Atlas owner is Bob.", "direct-origin-delivery"),
        (
            "adapter:forwarded",
            "Bob is the owner of Atlas.",
            "forwarded-origin-delivery",
        ),
    ):
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content=content,
            operation_id=operation_id,
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=AuthenticatedHostIngress(
                provider_identity=provider_identity,
                principal_handle=object(),
                session_handle=object(),
                received_at=TEST_NOW,
            ),
        )

    observations = tuple(
        observation
        for record in service._memory_plane.list_records(
            source_kind="learned_ontology_coverage_observation_v1"
        )
        if (
            observation := CoverageObservationRepository(service._memory_plane).load(
                record.memory_id
            )
        )
        is not None
    )
    assert len(observations) == 2
    assert len({observation.source_id for observation in observations}) == 2
    assert {observation.origin_lineage_digest for observation in observations} == {
        resolver.evidence.lineage_digest
    }


def test_configured_ontology_observer_runs_after_source_admission_and_retries_once() -> None:
    binding = ObserverBindingIdentity(
        binding_version="observer:v1",
        provider="host",
        model="fixture-model",
        prompt_version="ontology-observe:v1",
        transport="in_process",
        egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )
    signature = RelationGapSignature.create(
        normalized_relation_meaning="mentors",
        subject_type_id="Person",
        object_type_id="Person",
        domain_id="organization",
        evidence_rule_id="direct_assertion:v1",
    )

    class Observer:
        calls = 0

        @property
        def binding(self):
            return binding

        def observe(self, _request):
            self.calls += 1
            return OntologyObservationResult.create(
                semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
                source_span=CoverageSourceSpan(start=0, end=17),
                source_quote="Alice mentors Bob",
                signature=signature,
            )

    observer = Observer()
    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
        ontology_observer_capability=observer,
        ontology_observer_authorizer=lambda _ingress, candidate: candidate == binding,
    )

    for _ in range(2):
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Alice mentors Bob.",
            operation_id="provider-ontology-observer",
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )

    observation_record = service._memory_plane.list_records(
        source_kind="learned_ontology_coverage_observation_v1"
    )[0]
    observation = CoverageObservationRepository(service._memory_plane).load(
        observation_record.memory_id
    )
    assert observation is not None
    assert observation.processing_state == DiscoveryProcessingState.CLASSIFIED
    assert observation.semantic_outcome == CoverageSemanticOutcome.UNSUPPORTED_RELATION
    recurrence_record = service._memory_plane.list_records(
        source_kind="learned_ontology_coverage_recurrence_group_v1"
    )[0]
    recurrence = CoverageRecurrenceRepository(service._memory_plane).load(
        recurrence_record.memory_id
    )
    assert isinstance(recurrence, CoverageRecurrenceGroup)
    assert recurrence.independent_lineage_count == 1
    assert recurrence.proposal_eligible is False
    assert observer.calls == 1


def test_observer_report_of_registered_relation_alias_becomes_uncertain() -> None:
    binding = ObserverBindingIdentity(
        binding_version="observer:v1",
        provider="host",
        model="fixture-model",
        prompt_version="ontology-observe:v1",
        transport="in_process",
        egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )
    covered = RelationGapSignature.create(
        normalized_relation_meaning="asset owner",
        subject_type_id="Asset",
        object_type_id="Person",
        domain_id="organization",
        evidence_rule_id="direct_assertion:v1",
    )

    class Observer:
        @property
        def binding(self):
            return binding

        def observe(self, _request):
            return OntologyObservationResult.create(
                semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
                source_span=CoverageSourceSpan(start=0, end=18),
                source_quote="Truck owner is Bob",
                signature=covered,
            )

    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
        ontology_observer_capability=Observer(),
        ontology_observer_authorizer=lambda _ingress, candidate: candidate == binding,
    )
    repository = service._provider_ingestion._catalog_selection_repository
    assert repository is not None
    repository.install_default_catalog_release()

    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Truck owner is Bob.",
        operation_id="covered-ontology-alias",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    observation = CoverageObservationRepository(service._memory_plane).all()[0]
    assert observation.processing_state == DiscoveryProcessingState.CLASSIFIED
    assert observation.semantic_outcome == CoverageSemanticOutcome.UNCERTAIN
    assert service._memory_plane.list_records(
        source_kind="learned_ontology_verified_coverage_gap_v1"
    ) == []
    assert service._memory_plane.list_records(
        source_kind="learned_ontology_coverage_recurrence_group_v1"
    ) == []


def test_observer_retry_after_catalog_rotation_uses_pinned_seed_version() -> None:
    binding = ObserverBindingIdentity(
        binding_version="observer:v1",
        provider="host",
        model="recovering-model",
        prompt_version="ontology-observe:v1",
        transport="in_process",
        egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )
    reports_to = RelationGapSignature.create(
        normalized_relation_meaning="reports to",
        subject_type_id="Person",
        object_type_id="Person",
        domain_id="organization",
        evidence_rule_id="direct_assertion:v1",
    )

    class Observer:
        unavailable = True

        @property
        def binding(self):
            return binding

        def observe(self, _request):
            if self.unavailable:
                raise OSError("observer unavailable")
            return OntologyObservationResult.create(
                semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
                source_span=CoverageSourceSpan(start=0, end=20),
                source_quote="Alice reports to Bob",
                signature=reports_to,
            )

    observer = Observer()
    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
        ontology_observer_capability=observer,
        ontology_observer_authorizer=lambda _ingress, candidate: candidate == binding,
    )
    ingress = _host_ingress()

    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Alice reports to Bob.",
        operation_id="pinned-catalog-observation",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=ingress,
    )
    unavailable = CoverageObservationRepository(service._memory_plane).all()[0]
    assert unavailable.processing_state == DiscoveryProcessingState.UNAVAILABLE
    repository = service._provider_ingestion._catalog_selection_repository
    assert repository is not None
    repository.install_default_catalog_release()
    assert repository.resolve_selected_bundle().version.version_digest != (
        unavailable.catalog_digest
    )

    observer.unavailable = False
    reopened = ProviderMemoryService._from_scenario_test_host(
        memory_plane=service._memory_plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
        ontology_observer_capability=observer,
        ontology_observer_authorizer=lambda _ingress, candidate: candidate == binding,
    )

    recovered = CoverageObservationRepository(reopened._memory_plane).load(
        unavailable.observation_id
    )
    assert recovered is not None
    assert recovered.semantic_outcome == CoverageSemanticOutcome.UNSUPPORTED_RELATION
    assert len(reopened._memory_plane.list_records(
        source_kind="learned_ontology_verified_coverage_gap_v1"
    )) == 1


def test_observer_outage_retries_live_and_during_service_jsonl_reopen(
    tmp_path: Path,
) -> None:
    binding = ObserverBindingIdentity(
        binding_version="observer:v1",
        provider="host",
        model="recovering-model",
        prompt_version="ontology-observe:v1",
        transport="in_process",
        egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )
    signature = RelationGapSignature.create(
        normalized_relation_meaning="mentors",
        subject_type_id="Person",
        object_type_id="Person",
        domain_id="organization",
        evidence_rule_id="direct_assertion:v1",
    )

    class Observer:
        def __init__(self, *, unavailable: bool) -> None:
            self.unavailable = unavailable
            self.calls = 0

        @property
        def binding(self):
            return binding

        def observe(self, _request):
            self.calls += 1
            if self.unavailable:
                raise OSError("observer transport unavailable")
            return OntologyObservationResult.create(
                semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
                source_span=CoverageSourceSpan(start=0, end=17),
                source_quote="Alice mentors Bob",
                signature=signature,
            )

    storage_path = tmp_path / "memory-plane"
    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())

    def build_service(observer: Observer) -> ProviderMemoryService:
        return ProviderMemoryService._from_scenario_test_host(
            memory_plane=MemoryPlaneService(
                record_store=JsonlMemoryPlaneStore(storage_path)
            ),
            now_provider=lambda: TEST_NOW,
            host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
            source_normalization_host_bundle_builder=builder,
            bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
            ontology_observer_capability=observer,
            ontology_observer_authorizer=lambda _ingress, candidate: candidate == binding,
        )

    observer = Observer(unavailable=True)
    service = build_service(observer)

    def sync(operation_id: str) -> None:
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Alice mentors Bob.",
            operation_id=operation_id,
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )

    sync("observer-live-retry")
    first = CoverageObservationRepository(service._memory_plane).all()[0]
    assert first.processing_state == DiscoveryProcessingState.UNAVAILABLE
    assert first.attempt_count == 1

    observer.unavailable = False
    sync("observer-live-retry")
    live_recovered = CoverageObservationRepository(service._memory_plane).load(
        first.observation_id
    )
    assert live_recovered is not None
    assert live_recovered.processing_state == DiscoveryProcessingState.CLASSIFIED
    assert live_recovered.attempt_count == 2
    assert observer.calls == 2

    observer.unavailable = True
    sync("observer-restart-retry")
    before_reopen = CoverageObservationRepository(service._memory_plane).all()
    unavailable = next(
        item
        for item in before_reopen
        if item.processing_state == DiscoveryProcessingState.UNAVAILABLE
    )
    source_ids = {item.source_id for item in before_reopen}

    reopened_observer = Observer(unavailable=False)
    reopened = build_service(reopened_observer)
    after_reopen = CoverageObservationRepository(reopened._memory_plane).all()
    recovered = next(
        item for item in after_reopen if item.observation_id == unavailable.observation_id
    )
    assert recovered.processing_state == DiscoveryProcessingState.CLASSIFIED
    assert recovered.attempt_count == 2
    assert reopened_observer.calls == 1
    assert {item.source_id for item in after_reopen} == source_ids
    assert len(after_reopen) == 2
    assert len(
        reopened._memory_plane.list_records(
            source_kind="learned_ontology_verified_coverage_gap_v1"
        )
    ) == 2
    assert len(
        reopened._memory_plane.list_records(
            source_kind="learned_ontology_coverage_recurrence_group_v1"
        )
    ) == 1


def test_framework_neutral_and_hermes_adapters_share_coverage_contract() -> None:
    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
    )
    generic = AuthenticatedSourceRuntime(
        adapter=AuthenticatedSourceAdapter(service),
        issue_ingress=lambda _submission: _host_ingress(),
    )
    hermes = HermesMemoryProvider(service)
    ingress = _host_ingress()

    generic.submit(
        AuthenticatedSourceSubmission(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id="generic-coverage-source",
            task_id="task:one",
            user_id="user:alice",
        )
    )
    hermes.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="hermes-coverage-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=ingress,
    )

    observations = CoverageObservationRepository(service._memory_plane).all()
    assert len(observations) == 2
    assert len({item.source_id for item in observations}) == 2
    assert {
        (
            item.principal_id,
            item.agent_id,
            item.source_scope_digest,
            item.catalog_scope,
            item.catalog_digest,
            item.processing_state,
            item.semantic_outcome,
        )
        for item in observations
    } == {
        (
            observations[0].principal_id,
            observations[0].agent_id,
            observations[0].source_scope_digest,
            observations[0].catalog_scope,
            observations[0].catalog_digest,
            DiscoveryProcessingState.PENDING_NO_CAPABILITY,
            CoverageSemanticOutcome.NOT_EVALUATED,
        )
    }


def test_coverage_status_isolated_by_principal_agent_and_scope() -> None:
    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
        authenticated_ingress_resolver=_CoverageStatusResolver(),
    )

    def host(kind: str) -> AuthenticatedHostIngress:
        return AuthenticatedHostIngress(
            provider_identity=kind,
            principal_handle=object(),
            session_handle=object(),
            received_at=TEST_NOW,
        )

    owner = host("owner")
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="coverage-status-owner",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=owner,
    )

    owner_status = service.list_ontology_coverage_statuses(
        authenticated_host_ingress=owner
    )
    assert owner_status.status == "ok"
    assert len(owner_status.observations) == 1
    assert "Atlas owner is Bob" not in owner_status.model_dump_json()
    for kind in ("other-agent", "other-principal", "other-scope"):
        status = service.list_ontology_coverage_statuses(
            authenticated_host_ingress=host(kind)
        )
        assert status.status == "ok"
        assert status.observations == ()
    denied = service.list_ontology_coverage_statuses(
        authenticated_host_ingress=host("invalid")
    )
    assert denied.status == "denied"
    assert denied.observations == ()


def test_ontology_observer_denied_egress_remains_pending_without_call() -> None:
    binding = ObserverBindingIdentity(
        binding_version="observer:v1",
        provider="remote",
        model="fixture-model",
        prompt_version="ontology-observe:v1",
        transport="https",
        egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )

    class Observer:
        calls = 0

        @property
        def binding(self):
            return binding

        def observe(self, _request):
            self.calls += 1
            raise AssertionError("denied source reached ontology observer")

    observer = Observer()
    builder, _ = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
        ontology_observer_capability=observer,
        ontology_observer_authorizer=lambda _ingress, _binding: False,
    )

    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="provider-ontology-observer-denied",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    record = service._memory_plane.list_records(
        source_kind="learned_ontology_coverage_observation_v1"
    )[0]
    observation = CoverageObservationRepository(service._memory_plane).load(
        record.memory_id
    )
    assert observation is not None
    assert (
        observation.processing_state
        == DiscoveryProcessingState.PENDING_NO_CAPABILITY
    )
    assert observation.semantic_outcome == CoverageSemanticOutcome.NOT_EVALUATED
    assert observer.calls == 0


def _retained_structured_submission(
    service: ProviderMemoryService,
    *,
    authority: ResolvedStructuredSubmissionAuthority | None = None,
    activate_authority: bool = True,
    source_id: str | None = None,
    proposal: ProviderSemanticProposal | None = None,
):
    """Build a direct proposal only after the ordinary root retained its source."""
    source = next(
        record
        for record in service._memory_plane.list_records(
            source_kind="semantic_ingestion_source"
        )
        if record.text == "Atlas owner is Bob."
        and (source_id is None or record.memory_id == source_id)
    )
    source_digest = source_admission_source_digest(source)
    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None and runtime.prepared_source_repository is not None
    prepared = runtime.prepared_source_repository.load(
        source_id=source.memory_id, source_digest=source_digest
    )
    assert prepared is not None and prepared.sentence_spans
    proposal = proposal or _bob_owner_proposal()
    proposal_bytes = encode_typed_value(proposal.model_dump(mode="python"))
    raw_artifact = b'{"structured":"Atlas owner is Bob."}'
    submission = RetainedStructuredSubmission(
        source_id=source.memory_id,
        source_digest=source_digest,
        authority=authority or ResolvedStructuredSubmissionAuthority(
            authenticated=AuthenticatedPrincipalAgent(
                principal_id="principal:alice", agent_id="agent:alice"
            ),
            source_grant=SourceScopeGrant(
                grant_id="source-grant:fixture", grant_version=1,
                source_scope="task:task:one",
                authenticated=AuthenticatedPrincipalAgent(
                    principal_id="principal:alice", agent_id="agent:alice"
                ),
            ),
            fact_grant=FactScopeGrant(
                grant_id="fact-grant:fixture", grant_version=1,
                fact_scope="user:user:alice",
                authenticated=AuthenticatedPrincipalAgent(
                    principal_id="principal:alice", agent_id="agent:alice"
                ),
            ),
            catalog_visibility_grant=CatalogOwnerVisibilityGrant(
                grant_id="catalog-grant:fixture", grant_version=1,
                catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
                authenticated=AuthenticatedPrincipalAgent(
                    principal_id="principal:alice", agent_id="agent:alice"
                ),
                purpose="visibility_status",
            ),
            catalog=ResolvedCatalogAuthority(
                catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
                catalog_digest=sha256(b"base-catalog").hexdigest(),
                genesis_selection_digest=sha256(b"fixture-base-genesis").hexdigest(),
            ),
        ),
        exact_source_spans=(prepared.sentence_spans[0],),
        raw_proposal_artifact=raw_artifact,
        raw_proposal_artifact_digest=sha256(raw_artifact).hexdigest(),
        protocol_version="structured-fact-v1",
        parser_version="fixture-parser-v1",
        proposal=proposal,
        proposal_bytes=proposal_bytes,
    )
    ingress = service._resolve_ingress(_host_ingress())
    assert ingress is not None
    writer_binding = service._provider_ingestion._current_writer_binding()
    accepted = GovernedSourceAdmissionService(
        service._memory_plane
    ).allocate_retained_source_operation(
        request=RetainedSourceOperationRequest(
            source_id=submission.source_id,
            source_digest=submission.source_digest,
            canonical_envelope=submission.canonical_envelope(),
        ),
        authenticated_ingress=ingress,
    )
    if activate_authority:
        service._activate_structured_submission_authority(
            accepted=accepted, authority=submission.authority,
            writer_binding=writer_binding,
        )
    return accepted, submission, ingress, writer_binding


def _execute_retained_structured_submission(
    service: ProviderMemoryService, *, accepted, submission, ingress, writer_binding,
):
    with service._new_canonical_evidence_arena() as arena:
        return service._provider_ingestion.execute_retained_structured_proposal(
            accepted=accepted,
            submission=submission,
            authenticated_ingress=ingress,
            canonical_evidence_arena=arena,
            writer_binding=writer_binding,
        )


class _StructuredSubmissionAuthorityResolver:
    """Host fixture that issues only the core-selected base coordinate."""

    resolver_binding_digest = sha256(b"structured-submission-resolver:fixture").hexdigest()

    def resolve_submission_authority(self, *, authenticated_ingress, request):
        if (
            authenticated_ingress.delivery_principal_binding.principal_subject_id
            != request.authenticated.principal_id
        ):
            return None
        try:
            catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base(
                expected_catalog_digest=request.expected_catalog_digest
            )
        except ValueError:
            return None
        return ResolvedStructuredSubmissionAuthority(
            authenticated=request.authenticated,
            source_grant=request.source_grant,
            fact_grant=request.fact_grant,
            catalog_visibility_grant=request.catalog_visibility_grant,
            catalog=catalog,
            provider_model_prompt_provenance_digest=(
                request.provider_model_prompt_provenance_digest
            ),
        )


class _FixedStructuredSubmissionAuthorityResolver(_StructuredSubmissionAuthorityResolver):
    """Return the host's fixed authority rather than echoing request fields."""

    expected: ResolvedStructuredSubmissionAuthority | None = None

    def resolve_submission_authority(self, *, authenticated_ingress, request):
        del authenticated_ingress, request
        return self.expected


def test_public_structured_fact_rejects_substituted_authority_and_source_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.integration.test_observation_ledger_activation import _signed_monitoring_authority

    resolver = _FixedStructuredSubmissionAuthorityResolver()
    normalization, calls = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    capability = _built_in_local_capability(
        resolver=_AgentBoundResolver(),
        normalization_builder=normalization,
        structured_submission_authority_resolver=resolver,
    )
    verified_authority = build_verified_production_host_authority(
        host_bootstrap_capability=capability,
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        server_time=TEST_NOW,
    )
    assert verified_authority is not None
    service = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        verified_production_host_authority=verified_authority,
        verified_capability_monitoring_authorities=(_signed_monitoring_authority(),),
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="substituted-structured-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    _, submission, _, _ = _retained_structured_submission(service)
    seed = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    resolver.expected = submission.authority.model_copy(update={"catalog": seed})
    authority_request = StructuredSubmissionAuthorityRequest(
        authenticated=resolver.expected.authenticated,
        source_grant=resolver.expected.source_grant,
        fact_grant=resolver.expected.fact_grant,
        catalog_visibility_grant=resolver.expected.catalog_visibility_grant,
        expected_catalog_digest=seed.catalog_digest,
    )
    request = StructuredFactSubmissionRequest(
        source_id=submission.source_id,
        source_digest=submission.source_digest,
        authority_request=authority_request,
        exact_source_spans=submission.exact_source_spans,
        raw_proposal_artifact=submission.raw_proposal_artifact,
        raw_proposal_artifact_digest=submission.raw_proposal_artifact_digest,
        protocol_version=submission.protocol_version,
        parser_version=submission.parser_version,
        proposal=submission.proposal,
        proposal_bytes=submission.proposal_bytes,
    )

    def network_forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("substituted structured request attempted network access")

    monkeypatch.setattr(socket, "getaddrinfo", network_forbidden)
    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", network_forbidden)
    baseline = tuple(service._memory_plane.list_records())
    proposal_calls_before = calls["proposal"]
    variants = (
        authority_request.model_copy(update={"authenticated": authority_request.authenticated.model_copy(update={"principal_id": "principal:other"})}),
        authority_request.model_copy(update={"authenticated": authority_request.authenticated.model_copy(update={"agent_id": "agent:other"})}),
        authority_request.model_copy(update={"source_grant": authority_request.source_grant.model_copy(update={"grant_id": "source-grant:other"})}),
        authority_request.model_copy(update={"fact_grant": authority_request.fact_grant.model_copy(update={"grant_id": "fact-grant:other"})}),
        authority_request.model_copy(update={"catalog_visibility_grant": authority_request.catalog_visibility_grant.model_copy(update={"grant_id": "catalog-grant:other"})}),
        authority_request.model_copy(update={"expected_catalog_digest": "0" * 64}),
    )
    for altered_authority in variants:
        response = service.submit_structured_fact(
            request.model_copy(update={"authority_request": altered_authority}),
            authenticated_host_ingress=_host_ingress(),
        )
        assert response.status == "denied"
        assert response.operation_id is None
        assert tuple(service._memory_plane.list_records()) == baseline
        assert calls["proposal"] == proposal_calls_before
    for changed in (
        {"source_id": "source:other"},
        {"source_digest": "0" * 64},
        {"exact_source_spans": ()},
    ):
        response = service.submit_structured_fact(
            request.model_copy(update=changed),
            authenticated_host_ingress=_host_ingress(),
        )
        assert response.status == "denied"
        assert response.operation_id is None
        assert tuple(service._memory_plane.list_records()) == baseline
        assert calls["proposal"] == proposal_calls_before


def test_verified_production_authority_seals_structured_submission_resolver() -> None:
    resolver = _StructuredSubmissionAuthorityResolver()
    capability = _built_in_local_capability()
    presentation = capability.bootstrap_material_presentation
    unbound_authority = build_verified_production_host_authority(
        host_bootstrap_capability=capability,
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        server_time=TEST_NOW,
    )
    assert unbound_authority is not None
    legacy_material_digest = sha256(
        encode_typed_value(
            {
                "artifact_payloads": presentation.material.artifact_payloads.model_dump(
                    mode="python"
                ),
                "release_evidence": presentation.material.release_evidence.model_dump(
                    mode="python"
                ),
                "profile_enabled": presentation.material.profile_enabled,
                "trust_domain": presentation.material.trust_domain,
            }
        )
    ).hexdigest()
    assert unbound_authority.receipt.verified_material_digest == legacy_material_digest
    material = replace(
        presentation.material,
        structured_submission_authority_resolver=resolver,
        structured_submission_authority_resolver_binding_digest=(
            resolver.resolver_binding_digest
        ),
    )
    capability = replace(
        capability,
        bootstrap_material_presentation=present_authenticated_host_bootstrap_material(
            material
        ),
    )
    authority = build_verified_production_host_authority(
        host_bootstrap_capability=capability,
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        server_time=TEST_NOW,
    )

    assert authority is not None
    service = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        verified_production_host_authority=authority,
    )
    assert service._structured_submission_authority_resolver is resolver

    substituted = replace(
        material,
        structured_submission_authority_resolver=_StructuredSubmissionAuthorityResolver(),
        structured_submission_authority_resolver_binding_digest="0" * 64,
    )
    substituted_capability = replace(
        capability,
        bootstrap_material_presentation=replace(presentation, material=substituted),
    )
    assert build_verified_production_host_authority(
        host_bootstrap_capability=substituted_capability,
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        server_time=TEST_NOW,
    ) is None


def test_public_structured_fact_submission_requires_current_grant_fence() -> None:
    """The generic root returns only a persisted V3 terminal under current grants."""

    normalization, calls = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
        structured_submission_authority_resolver=_StructuredSubmissionAuthorityResolver(),
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="public-structured-submission-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    _, submission, _, _ = _retained_structured_submission(service)
    seed = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    authority_request = StructuredSubmissionAuthorityRequest(
        authenticated=submission.authority.authenticated,
        source_grant=submission.authority.source_grant,
        fact_grant=submission.authority.fact_grant,
        catalog_visibility_grant=submission.authority.catalog_visibility_grant,
        expected_catalog_digest=seed.catalog_digest,
    )
    request = StructuredFactSubmissionRequest(
        source_id=submission.source_id,
        source_digest=submission.source_digest,
        authority_request=authority_request,
        exact_source_spans=submission.exact_source_spans,
        raw_proposal_artifact=submission.raw_proposal_artifact,
        raw_proposal_artifact_digest=submission.raw_proposal_artifact_digest,
        protocol_version=submission.protocol_version,
        parser_version=submission.parser_version,
        proposal=submission.proposal,
        proposal_bytes=submission.proposal_bytes,
    )

    result = service.submit_structured_fact(
        request, authenticated_host_ingress=_host_ingress()
    )
    assert result.status == "abstained"
    assert result.operation_id is not None
    status = service.lookup_structured_fact_status(
        StructuredFactSubmissionStatusRequest(
            operation_id=result.operation_id, authority_request=authority_request,
        ),
        authenticated_host_ingress=_host_ingress(),
    )
    assert status.status == "abstained"
    assert status.operation_id == result.operation_id
    assert calls["proposal"] == 1
    retry = service.submit_structured_fact(
        request, authenticated_host_ingress=_host_ingress()
    )
    assert retry == result
    assert calls["proposal"] == 1
    service._semantic_atomic_store.revoke_structured_submission_grant(
        grant_kind="fact",
        grant_id=submission.authority.fact_grant.grant_id,
        writer_binding=service._provider_ingestion._current_writer_binding(),
    )
    revoked_status = service.lookup_structured_fact_status(
        StructuredFactSubmissionStatusRequest(
            operation_id=result.operation_id, authority_request=authority_request,
        ),
        authenticated_host_ingress=_host_ingress(),
    )
    assert revoked_status.status == "denied"
    assert revoked_status.denial_reason == "authorization_revoked"
    assert tuple(
        service._memory_plane.list_records(
            source_kind="semantic_ingestion_retained_structured_submission"
        )
    )


def test_public_structured_fact_submission_commits_before_protected_read_composition() -> None:
    """The public no-key path persists an accepted claim for the read composition owner."""
    from tests.integration.test_observation_ledger_activation import _signed_monitoring_authority

    proposal_ref = [ProviderSemanticProposal(abstained=True)]
    normalization, calls = _v3_normalization_host_builder(
        proposal=_bob_owner_proposal(), proposal_ref=proposal_ref,
    )
    scoped_authority = InProcessScopedReadAuthority(now_provider=lambda: TEST_NOW)
    resolver = _StructuredSubmissionAuthorityResolver()
    capability = _built_in_local_capability(
        resolver=_AgentBoundResolver(),
        normalization_builder=normalization,
        structured_submission_authority_resolver=resolver,
    )
    verified_authority = build_verified_production_host_authority(
        host_bootstrap_capability=capability,
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        server_time=TEST_NOW,
    )
    assert verified_authority is not None
    service = ProviderMemoryService(
        memory_plane=MemoryPlaneService(), now_provider=lambda: TEST_NOW,
        verified_production_host_authority=verified_authority,
        verified_capability_monitoring_authorities=(_signed_monitoring_authority(),),
        scoped_read_authority=scoped_authority,
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="public-structured-commit-source", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    proposal_ref[0] = _bob_owner_proposal()
    authenticated = AuthenticatedPrincipalAgent(principal_id="principal:alice", agent_id="agent:alice")
    seed = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    authority = ResolvedStructuredSubmissionAuthority(
        authenticated=authenticated,
        source_grant=SourceScopeGrant(grant_id="source-grant:public-commit", grant_version=1, source_scope="task:task:one", authenticated=authenticated),
        fact_grant=FactScopeGrant(grant_id="fact-grant:public-commit", grant_version=1, fact_scope="user:user:alice", authenticated=authenticated),
        catalog_visibility_grant=CatalogOwnerVisibilityGrant(grant_id="catalog-grant:public-commit", grant_version=1, catalog_scope=seed.catalog_scope, authenticated=authenticated, purpose="visibility_status"),
        catalog=seed,
    )
    _, submission, _, _ = _retained_structured_submission(
        service, authority=authority, activate_authority=False,
    )
    authority_request = StructuredSubmissionAuthorityRequest(
        authenticated=authenticated, source_grant=authority.source_grant,
        fact_grant=authority.fact_grant, catalog_visibility_grant=authority.catalog_visibility_grant,
        expected_catalog_digest=seed.catalog_digest,
    )
    request = StructuredFactSubmissionRequest(
        source_id=submission.source_id, source_digest=submission.source_digest,
        authority_request=authority_request, exact_source_spans=submission.exact_source_spans,
        raw_proposal_artifact=submission.raw_proposal_artifact,
        raw_proposal_artifact_digest=submission.raw_proposal_artifact_digest,
        protocol_version=submission.protocol_version, parser_version=submission.parser_version,
        proposal=submission.proposal, proposal_bytes=submission.proposal_bytes,
    )
    result = service.submit_structured_fact(request, authenticated_host_ingress=_host_ingress())
    assert result.status == "committed", result
    assert result.operation_id is not None
    assert calls["proposal"] == 1
    # The generic public root, not the fixture resolver, selects and persists
    # the catalog authority before it executes the structured proposal.
    assert len(service._memory_plane.list_records(
        source_kind="semantic_ingestion_catalog_version"
    )) == 1
    assert len(service._memory_plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )) == 1
    projections = tuple(record for record in service._memory_plane.list_records()
                        if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion")
    bindings = tuple(service._memory_plane.list_records(
        source_kind="semantic_ingestion_structured_claim_catalog_binding"
    ))
    assert len(bindings) == 1
    projection = next(record for record in projections if record.content["claim_assertion_id"] == bindings[0].content["binding"]["claim_assertion_id"])
    handle = scoped_authority.provision(
        host_task_id="task:one", host_state_id="state:one",
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task:one", user_id="user:alice", agent_id="agent:alice"),),
        expires_at=TEST_NOW + timedelta(minutes=1),
        structured_fact_read_authorities=(StructuredFactReadAuthority(
            authenticated=authenticated, fact_grant=authority.fact_grant,
            catalog_visibility_grant=authority.catalog_visibility_grant,
        ),),
    )
    response = service.retrieve_context(ScopedContextRequest(
        host_task_id="task:one", host_state_id="state:one",
        declared_complete_mandatory_set=True, mandatory_record_references=(), optional_query="Atlas owner",
        optional_domains=(MemoryDomain.SEMANTIC,),
        budget=ScopedContextBudget(max_mandatory_items=2, max_optional_items=2, max_optional_omission_ids=2, max_rendered_utf8_bytes=4096),
        reference_time=datetime(2026, 1, 15, tzinfo=UTC),
    ), opaque_host_ingress=handle)
    assert tuple(item.record_id for item in response.optional_items) == (projection.memory_id,), response

    retry = service.submit_structured_fact(request, authenticated_host_ingress=_host_ingress())
    assert retry.status == "committed"
    assert retry.operation_id == result.operation_id
    assert calls["proposal"] == 1

    pointer = service._memory_plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )[0]
    corrupt_pointer = pointer.model_copy(update={"content": {
        **pointer.content,
        "catalog_selection_pointer": {
            **pointer.content["catalog_selection_pointer"],
            "pointer_digest": "0" * 64,
        },
    }})
    # Model a damaged durable image below the normal governed write boundary.
    # The generic public root must deny it before it can reuse the old seed.
    backend = service._memory_plane._records
    assert isinstance(backend, InMemoryMemoryPlaneStore)
    backend._records[pointer.memory_id] = corrupt_pointer
    unavailable = service.submit_structured_fact(
        request, authenticated_host_ingress=_host_ingress()
    )
    assert unavailable.status == "denied"
    assert unavailable.denial_reason == "base_catalog_unavailable"
    assert calls["proposal"] == 1

    # This test's source-only fixture is schema 1 and remains outside the
    # projection-era reader.  The schema-2 compatibility fixture is covered
    # through the normal production root.
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="public-structured-pre-catalog-legacy",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    mixed = service.retrieve_context(
        ScopedContextRequest(
            host_task_id="task:one", host_state_id="state:one",
            declared_complete_mandatory_set=True,
            mandatory_record_references=(), optional_query="Atlas owner",
            optional_domains=(MemoryDomain.SEMANTIC,),
            budget=ScopedContextBudget(
                max_mandatory_items=2, max_optional_items=2,
                max_optional_omission_ids=2, max_rendered_utf8_bytes=4096,
            ),
            reference_time=datetime(2026, 1, 15, tzinfo=UTC),
        ),
        opaque_host_ingress=handle,
    )
    assert mixed.status is ScopedContextStatus.UNAVAILABLE


def test_verified_production_public_structured_fact_jsonl_recovery_denies_revoked_retry_and_corruption_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public terminal survives JSONL reopen and never needs a network provider."""
    from tests.integration.test_observation_ledger_activation import _signed_monitoring_authority

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def network_forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("structured public path attempted network access")

    monkeypatch.setattr(socket, "getaddrinfo", network_forbidden)
    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", network_forbidden)

    proposal_ref = [ProviderSemanticProposal(abstained=True)]
    resolver = _StructuredSubmissionAuthorityResolver()
    call_sets: list[dict[str, int]] = []

    def build_service(
        plane: MemoryPlaneService, *, with_monitoring_authority: bool = True,
    ) -> ProviderMemoryService:
        normalization, local_calls = _v3_normalization_host_builder(
            proposal=_bob_owner_proposal(), proposal_ref=proposal_ref,
        )
        # A host builder is per-process composition state. Reusing the test
        # fixture would itself deny the second construction before recovery.
        call_sets.append(local_calls)
        capability = _built_in_local_capability(
            resolver=_AgentBoundResolver(),
            normalization_builder=normalization,
            structured_submission_authority_resolver=resolver,
        )
        verified_authority = build_verified_production_host_authority(
            host_bootstrap_capability=capability,
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
            server_time=TEST_NOW,
        )
        assert verified_authority is not None
        return ProviderMemoryService(
            memory_plane=plane,
            now_provider=lambda: TEST_NOW,
            verified_production_host_authority=verified_authority,
            verified_capability_monitoring_authorities=(
                (_signed_monitoring_authority(),)
                if with_monitoring_authority
                else ()
            ),
        )

    path = tmp_path / "verified-production-structured-recovery"
    service = build_service(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="verified-production-structured-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    proposal_ref[0] = _bob_owner_proposal()
    seed = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    authenticated = AuthenticatedPrincipalAgent(
        principal_id="principal:alice", agent_id="agent:alice",
    )
    authority = ResolvedStructuredSubmissionAuthority(
        authenticated=authenticated,
        source_grant=SourceScopeGrant(
            grant_id="source-grant:verified-production-recovery", grant_version=1,
            source_scope="task:task:one", authenticated=authenticated,
        ),
        fact_grant=FactScopeGrant(
            grant_id="fact-grant:verified-production-recovery", grant_version=1,
            fact_scope="user:user:alice", authenticated=authenticated,
        ),
        catalog_visibility_grant=CatalogOwnerVisibilityGrant(
            grant_id="catalog-grant:verified-production-recovery", grant_version=1,
            catalog_scope=seed.catalog_scope, authenticated=authenticated,
            purpose="visibility_status",
        ),
        catalog=seed,
    )
    _, submission, _, _ = _retained_structured_submission(
        service, authority=authority, activate_authority=False,
    )
    authority_request = StructuredSubmissionAuthorityRequest(
        authenticated=authenticated, source_grant=authority.source_grant,
        fact_grant=authority.fact_grant,
        catalog_visibility_grant=authority.catalog_visibility_grant,
        expected_catalog_digest=seed.catalog_digest,
    )
    request = StructuredFactSubmissionRequest(
        source_id=submission.source_id, source_digest=submission.source_digest,
        authority_request=authority_request, exact_source_spans=submission.exact_source_spans,
        raw_proposal_artifact=submission.raw_proposal_artifact,
        raw_proposal_artifact_digest=submission.raw_proposal_artifact_digest,
        protocol_version=submission.protocol_version, parser_version=submission.parser_version,
        proposal=submission.proposal, proposal_bytes=submission.proposal_bytes,
    )
    event_batches_before = len(service._semantic_atomic_store.semantic_event_batches())

    first = service.submit_structured_fact(request, authenticated_host_ingress=_host_ingress())
    assert first.status == "committed"
    assert first.operation_id is not None
    first_status = service.lookup_structured_fact_status(
        StructuredFactSubmissionStatusRequest(
            operation_id=first.operation_id, authority_request=authority_request,
        ), authenticated_host_ingress=_host_ingress(),
    )
    assert first_status.status == "committed"
    assert first_status.operation_id == first.operation_id
    assert len(service._semantic_atomic_store.semantic_event_batches()) == event_batches_before + 1
    committed_record_digests = {
        record.memory_id: record_digest(record)
        for record in service._memory_plane.list_records()
    }

    reopened = build_service(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    runtime = reopened._provider_ingestion._semantic_runtime
    assert runtime is not None and runtime.prepared_source_repository is not None, {
        "writer_record": reopened._memory_plane.get_record(
            writer_admission_memory_id()
        ).content if reopened._memory_plane.get_record(writer_admission_memory_id()) else None,
    }
    base_loaded = runtime.prepared_source_repository.load(
        source_id=request.source_id, source_digest=request.source_digest,
    )
    prepared_records = tuple(
        (record.memory_id, record.content.get("source_id"), record.content.get("source_digest"))
        for record in reopened._memory_plane.list_records(
            source_kind="semantic_ingestion_prepared_source"
        )
    )
    reopened_status = reopened.lookup_structured_fact_status(
        StructuredFactSubmissionStatusRequest(
            operation_id=first.operation_id, authority_request=authority_request,
        ), authenticated_host_ingress=_host_ingress(),
    )
    assert reopened_status.status == "committed"
    assert reopened_status.operation_id == first.operation_id
    retry = reopened.submit_structured_fact(
        request, authenticated_host_ingress=_host_ingress(),
    )
    assert retry == first, {
        "prepared_records": prepared_records,
        "source": (request.source_id, request.source_digest),
        "repository_type": type(runtime.prepared_source_repository).__qualname__,
        "base_load": None if base_loaded is None else (
            base_loaded.source_id, base_loaded.source_digest,
        ),
    }
    assert sum(item["proposal"] for item in call_sets) == 1
    assert {
        record.memory_id: record_digest(record)
        for record in reopened._memory_plane.list_records()
    } == committed_record_digests
    assert len(reopened._semantic_atomic_store.semantic_event_batches()) == event_batches_before + 1
    assert reopened._semantic_atomic_store.recover_retained_structured_terminal_by_operation(
        operation_id=first.operation_id, authority=authority,
    ) is not None
    assert len(tuple(reopened._memory_plane.list_records(
        source_kind="semantic_ingestion_structured_claim_catalog_binding"
    ))) == 1
    assert len(tuple(record for record in reopened._memory_plane.list_records()
                     if record.content.get("runtime_context_projection_kind")
                     == "bootstrap_v3_claim_assertion")) == 1

    reopened._semantic_atomic_store.revoke_structured_submission_grant(
        grant_kind="fact", grant_id=authority.fact_grant.grant_id,
        writer_binding=reopened._provider_ingestion._current_writer_binding(),
    )
    denied_status = reopened.lookup_structured_fact_status(
        StructuredFactSubmissionStatusRequest(
            operation_id=first.operation_id, authority_request=authority_request,
        ), authenticated_host_ingress=_host_ingress(),
    )
    denied_retry = reopened.submit_structured_fact(
        request, authenticated_host_ingress=_host_ingress(),
    )
    assert denied_status.status == "denied"
    assert denied_status.denial_reason == "authorization_revoked"
    assert denied_retry.status == "denied"
    assert denied_retry.denial_reason == "authorization_revoked"
    assert sum(item["proposal"] for item in call_sets) == 1

    # Corrupt the real JSONL log after a completed public submission.  The
    # subsequent public submission must fail closed before catalog selection,
    # operation allocation, writes, or proposal execution.
    records_path = path / "memory_records.jsonl"
    records_before = records_path.read_bytes()
    records_path.write_bytes(records_before + b"{corrupt-jsonl-batch}\n")

    # Recompose the verified public root after damage. Its first authenticated
    # ingress reads writer admission before catalog selection, so this catches
    # the cold-service recovery path rather than reusing warm state.
    corrupted_service = build_service(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)),
        with_monitoring_authority=False,
    )
    corrupted = corrupted_service.submit_structured_fact(
        request, authenticated_host_ingress=_host_ingress(),
    )

    assert corrupted.status == "denied"
    assert corrupted.denial_reason == "base_catalog_unavailable"
    assert records_path.read_bytes() == records_before + b"{corrupt-jsonl-batch}\n"
    assert sum(item["proposal"] for item in call_sets) == 1


def test_public_structured_fact_submission_denies_missing_authority_resolver() -> None:
    service = ProviderMemoryService(memory_plane=MemoryPlaneService())
    result = service.submit_structured_fact(
        cast(StructuredFactSubmissionRequest, object()),
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.status == "denied"
    assert result.denial_reason == "ingress_unavailable"


def test_unverified_constructor_cannot_install_structured_submission_authority() -> None:
    with pytest.raises(ValueError, match="restricted to a verified host authority"):
        ProviderMemoryService(
            memory_plane=MemoryPlaneService(),
            structured_submission_authority_resolver=_StructuredSubmissionAuthorityResolver(),
        )


def test_retained_structured_proposal_retries_through_v3_terminal() -> None:
    builder, calls = _v3_normalization_host_builder(proposal=_bob_owner_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="retained-structured-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    accepted, submission, ingress, writer_binding = _retained_structured_submission(service)

    calls_before_direct = dict(calls)
    first = _execute_retained_structured_submission(
        service, accepted=accepted, submission=submission, ingress=ingress, writer_binding=writer_binding
    )
    calls_before_retry = dict(calls)
    second = _execute_retained_structured_submission(
        service, accepted=accepted, submission=submission, ingress=ingress, writer_binding=writer_binding
    )

    assert first is not None
    assert second == first
    assert "bootstrap_graph_terminal_persisted" in first.reason_codes
    recovered = service._semantic_atomic_store.recover_retained_structured_terminal(
        accepted=accepted, authority=submission.authority,
    )
    assert recovered is not None
    assert recovered.canonical_source_result.canonical_source_result.final_status == "unresolved"
    assert service._semantic_atomic_store.load_retained_structured_submission(
        accepted=accepted
    ) == (submission.canonical_envelope(), submission.proposal_bytes, submission.raw_proposal_artifact)
    assert calls["proposal"] == calls_before_direct["proposal"]


    assert calls == calls_before_retry

    swapped_proposal = submission.model_copy(
        update={
            "proposal": ProviderSemanticProposal(abstained=True),
            "proposal_bytes": encode_typed_value(
                ProviderSemanticProposal(abstained=True).model_dump(mode="python")
            ),
        }
    )
    swapped_artifact = submission.model_copy(
        update={
            "raw_proposal_artifact": b'{"structured":"substituted"}',
            "raw_proposal_artifact_digest": sha256(b'{"structured":"substituted"}').hexdigest(),
        }
    )
    swapped_fence = GovernedSourceAdmissionService(
        service._memory_plane
    ).allocate_retained_source_operation(
        request=RetainedSourceOperationRequest(
            source_id=swapped_artifact.source_id,
            source_digest=swapped_artifact.source_digest,
            canonical_envelope=swapped_artifact.canonical_envelope(),
        ),
        authenticated_ingress=ingress,
    )
    assert _execute_retained_structured_submission(
        service, accepted=accepted, submission=swapped_proposal, ingress=ingress, writer_binding=writer_binding
    ) is None
    assert _execute_retained_structured_submission(
        service, accepted=accepted, submission=swapped_artifact, ingress=ingress, writer_binding=writer_binding
    ) is None
    assert _execute_retained_structured_submission(
        service, accepted=swapped_fence, submission=submission, ingress=ingress, writer_binding=writer_binding
    ) is None


@pytest.mark.parametrize("revoked_kind", ("fact", "catalog_visibility"))
def test_normal_root_structured_claim_is_readable_only_under_current_fact_and_catalog_grants(
    revoked_kind: str,
) -> None:
    """A retained no-key proposal uses the normal V3 graph planner and read gate."""
    from tests.integration.test_observation_ledger_activation import (
        _signed_monitoring_authority,
    )

    proposal_ref = [ProviderSemanticProposal(abstained=True)]
    normalization, calls = _v3_normalization_host_builder(
        proposal=_bob_owner_proposal("employs"), proposal_ref=proposal_ref,
    )
    scoped_authority = InProcessScopedReadAuthority(now_provider=lambda: TEST_NOW)
    service = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(
            resolver=_AgentBoundResolver(),
            predicate_id="employs",
        ),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        verified_capability_monitoring_authorities=(_signed_monitoring_authority(),),
        scoped_read_authority=scoped_authority,
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=f"normal-root-structured-{revoked_kind}",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    proposal_ref[0] = _bob_owner_proposal("employs")
    authenticated = AuthenticatedPrincipalAgent(
        principal_id="principal:alice", agent_id="agent:alice",
    )
    seed = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    authority = ResolvedStructuredSubmissionAuthority(
        authenticated=authenticated,
        source_grant=SourceScopeGrant(
            grant_id=f"source-grant:normal-root:{revoked_kind}",
            grant_version=1,
            source_scope="task:task:one",
            authenticated=authenticated,
        ),
        fact_grant=FactScopeGrant(
            grant_id=f"fact-grant:normal-root:{revoked_kind}",
            grant_version=1,
            fact_scope="user:user:alice",
            authenticated=authenticated,
        ),
        catalog_visibility_grant=CatalogOwnerVisibilityGrant(
            grant_id=f"catalog-grant:normal-root:{revoked_kind}",
            grant_version=1,
            catalog_scope=seed.catalog_scope,
            authenticated=authenticated,
            purpose="visibility_status",
        ),
        catalog=seed,
    )
    accepted, submission, ingress, writer_binding = _retained_structured_submission(
        service, authority=authority, proposal=_bob_owner_proposal("employs"),
    )
    outcome = _execute_retained_structured_submission(
        service, accepted=accepted, submission=submission, ingress=ingress, writer_binding=writer_binding,
    )
    assert outcome is not None
    assert "bootstrap_graph_terminal_persisted" in outcome.reason_codes
    assert calls["proposal"] == 1

    projections = tuple(
        record
        for record in service._memory_plane.list_records()
        if record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
    )
    bindings = tuple(service._memory_plane.list_records(
        source_kind="semantic_ingestion_structured_claim_catalog_binding"
    ))
    assert len(projections) == len(bindings) == 1
    assert bindings[0].content["binding"]["claim_assertion_id"] == (
        projections[0].content["claim_assertion_id"]
    )
    assert bindings[0].content["binding"]["claim_record_digest"] == (
        projections[0].content["claim_assertion_record_digest"]
    )

    handle = scoped_authority.provision(
        host_task_id="task:one",
        host_state_id="state:one",
        rows=(ScopedNamespaceGrantRow(
            domain=MemoryDomain.SEMANTIC,
            task_id="task:one",
            user_id="user:alice",
            agent_id="agent:alice",
        ),),
        expires_at=TEST_NOW + timedelta(minutes=1),
        structured_fact_read_authorities=(StructuredFactReadAuthority(
            authenticated=authenticated,
            fact_grant=authority.fact_grant,
            catalog_visibility_grant=authority.catalog_visibility_grant,
        ),),
    )
    request = ScopedContextRequest(
        host_task_id="task:one",
        host_state_id="state:one",
        declared_complete_mandatory_set=True,
        mandatory_record_references=(),
        optional_query="Atlas owner",
        optional_domains=(MemoryDomain.SEMANTIC,),
        budget=ScopedContextBudget(
            max_mandatory_items=2,
            max_optional_items=2,
            max_optional_omission_ids=2,
            max_rendered_utf8_bytes=4096,
        ),
        reference_time=datetime(2026, 1, 15, tzinfo=UTC),
    )
    readable = service.retrieve_context(request, opaque_host_ingress=handle)
    assert tuple(item.record_id for item in readable.optional_items) == (
        projections[0].memory_id,
    )

    grant = (
        authority.fact_grant if revoked_kind == "fact"
        else authority.catalog_visibility_grant
    )
    service._semantic_atomic_store.revoke_structured_submission_grant(
        grant_kind=revoked_kind,
        grant_id=grant.grant_id,
        writer_binding=service._provider_ingestion._current_writer_binding(),
    )
    denied = service.retrieve_context(request, opaque_host_ingress=handle)
    assert denied.status.value == "denied"
    assert denied.optional_items == ()
    assert denied.omissions == ()
    assert denied.memory_snapshot_revision is None


def test_retained_structured_proposal_revocation_between_pin_and_v3_cas_seals_source_only_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final V3 CAS must reject a grant revoked after planning begins."""
    path = tmp_path / "revoked-before-v3-cas.jsonl"
    service = _full_v3_service(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="retained-structured-revoked-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    accepted, submission, ingress, writer_binding = _retained_structured_submission(service)
    store = service._semantic_atomic_store
    original = store.commit_or_reload_bootstrap_graph_group_v3
    graph_before = store.semantic_replay_state().graph_revision
    revoked = False

    def revoke_before_cas(*args, **kwargs):
        nonlocal revoked
        if not revoked:
            revoked = True
            store.revoke_structured_submission_grant(
                grant_kind="fact",
                grant_id=submission.authority.fact_grant.grant_id,
                writer_binding=service._provider_ingestion._current_writer_binding(),
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "commit_or_reload_bootstrap_graph_group_v3", revoke_before_cas)
    outcome = _execute_retained_structured_submission(
        service, accepted=accepted, submission=submission, ingress=ingress, writer_binding=writer_binding
    )

    assert revoked is True
    assert outcome is not None
    assert outcome.reason_codes == (
        "bootstrap_graph_terminal_persisted",
        "failed",
    )
    assert store.semantic_replay_state().graph_revision == graph_before
    assert not any(
        record.source_kind == "semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
        and record.content.get("request", {}).get("operation_fence_binding", {}).get("operation_id")
        == accepted.operation_fence_binding.operation_id
        for record in service._memory_plane.list_records()
    )
    retry = _execute_retained_structured_submission(
        service, accepted=accepted, submission=submission, ingress=ingress, writer_binding=writer_binding
    )
    assert retry == outcome
    terminal = next(
        record.content["reload"]
        for record in service._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
        )
        if record.content["reload"]["terminal_member_schema_version"] == 4
    )
    assert terminal["pre_group_noncommit"]["reason"] == (
        "authorization_revoked_before_commit"
    )
    # Status recovery must re-read the current grant state before it even
    # validates the cached native terminal.  The revoked caller therefore
    # receives no terminal payload through the structured status owner.
    with pytest.raises(StructuredSubmissionGrantRevokedError):
        store.recover_retained_structured_terminal(
            accepted=accepted, authority=submission.authority,
        )

    before_reopen_retry_values = {
        record.memory_id: record.model_dump(mode="json")
        for record in service._memory_plane.list_records()
    }
    before_reopen_retry = {
        record_id: sha256(encode_typed_value(value)).hexdigest()
        for record_id, value in before_reopen_retry_values.items()
    }
    reopened = _full_v3_service(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    )
    reopened_retry = _execute_retained_structured_submission(
        reopened, accepted=accepted, submission=submission, ingress=ingress, writer_binding=writer_binding
    )
    assert reopened_retry == outcome
    with pytest.raises(StructuredSubmissionGrantRevokedError):
        reopened._semantic_atomic_store.recover_retained_structured_terminal(
            accepted=accepted, authority=submission.authority,
        )
    with pytest.raises(StructuredSubmissionGrantRevokedError):
        reopened._semantic_atomic_store.recover_retained_structured_terminal_by_operation(
            operation_id=accepted.operation_fence_binding.operation_id,
            authority=submission.authority,
        )
    after_reopen_retry_values = {
        record.memory_id: record.model_dump(mode="json")
        for record in reopened._memory_plane.list_records()
    }
    after_reopen_retry = {
        record_id: sha256(encode_typed_value(value)).hexdigest()
        for record_id, value in after_reopen_retry_values.items()
    }
    assert len(after_reopen_retry) == len(before_reopen_retry)
    assert set(after_reopen_retry) == set(before_reopen_retry)
    changed_records = tuple(
        (
            record_id,
            tuple(
                field
                for field in before_reopen_retry_values[record_id]
                if before_reopen_retry_values[record_id][field]
                != after_reopen_retry_values[record_id][field]
            ),
        )
        for record_id in sorted(before_reopen_retry)
        if after_reopen_retry[record_id] != before_reopen_retry[record_id]
    )
    assert not changed_records


@pytest.mark.parametrize("revoked_kind", ("source", "fact", "catalog_visibility"))
def test_structured_commit_fence_rejects_each_revoked_grant_before_returning_preconditions(
    revoked_kind: str,
) -> None:
    """The native final-CAS fence fails as a unit for every authority grant."""
    authenticated = AuthenticatedPrincipalAgent(
        principal_id="principal:alice", agent_id="agent:alice"
    )
    authority = ResolvedStructuredSubmissionAuthority(
        authenticated=authenticated,
        source_grant=SourceScopeGrant(
            grant_id="source-grant:fence", grant_version=1,
            source_scope="task:task:one", authenticated=authenticated,
        ),
        fact_grant=FactScopeGrant(
            grant_id="fact-grant:fence", grant_version=1,
            fact_scope="user:user:alice", authenticated=authenticated,
        ),
        catalog_visibility_grant=CatalogOwnerVisibilityGrant(
            grant_id="catalog-grant:fence", grant_version=1,
            catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
            authenticated=authenticated, purpose="visibility_status",
        ),
        catalog=ResolvedCatalogAuthority(
            catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
            catalog_digest=sha256(b"fence-catalog").hexdigest(),
            genesis_selection_digest=sha256(b"fence-genesis").hexdigest(),
        ),
    )

    class _Fence:
        operation_fence_id = "fence:structured-grant"
        source_id = "source:structured-grant"
        source_digest = sha256(b"source:structured-grant").hexdigest()

        def model_dump(self, *, mode: str) -> dict[str, str]:
            assert mode == "json"
            return {
                "operation_fence_id": self.operation_fence_id,
                "source_id": self.source_id,
                "source_digest": self.source_digest,
            }

    fence = _Fence()
    request = BootstrapGraphGroupCommitRequestV3.model_construct(
        operation_fence_binding=fence
    )
    envelope = encode_typed_value({
        "source_id": fence.source_id,
        "source_digest": fence.source_digest,
        "authority": authority.model_dump(mode="python"),
    })
    records: dict[str, object] = {
        "semantic_ingestion:retained-structured-submission:" + fence.operation_fence_id:
            SimpleNamespace(
                source_kind="semantic_ingestion_retained_structured_submission",
                content={
                    "canonical_envelope": base64.b64encode(envelope).decode("ascii"),
                    "operation_fence_binding": fence.model_dump(mode="json"),
                },
            ),
    }
    for kind, grant in (
        ("source", authority.source_grant),
        ("fact", authority.fact_grant),
        ("catalog_visibility", authority.catalog_visibility_grant),
    ):
        state = StructuredGrantState(
            schema_version=1, grant_kind=kind, grant=grant,
            active=kind != revoked_kind,
        )
        record_id = SemanticIngestionAtomicStore._structured_grant_state_record_id(
            kind, grant.grant_id
        )
        records[record_id] = CanonicalMemoryRecord(
            memory_id=record_id,
            domain=MemoryDomain.EXECUTION,
            text="",
            content={"state": state.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_structured_grant_state",
            timestamp=TEST_NOW,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )

    store = object.__new__(SemanticIngestionAtomicStore)
    store._memory_plane = SimpleNamespace(get_record=records.get)
    with pytest.raises(StructuredSubmissionGrantRevokedError):
        store._structured_submission_commit_fence_preconditions(request)


def test_retained_structured_proposal_reopens_from_jsonl_terminal(tmp_path: Path) -> None:
    path = tmp_path / "retained-structured-proposal.jsonl"
    service = _full_v3_service(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="retained-structured-restart-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    accepted, submission, ingress, writer_binding = _retained_structured_submission(service)
    first = _execute_retained_structured_submission(
        service, accepted=accepted, submission=submission, ingress=ingress, writer_binding=writer_binding
    )
    assert first is not None and "bootstrap_graph_terminal_persisted" in first.reason_codes

    reopened = _full_v3_service(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    retried, reopened_submission, reopened_ingress, reopened_binding = _retained_structured_submission(reopened)
    second = _execute_retained_structured_submission(
        reopened,
        accepted=retried,
        submission=reopened_submission,
        ingress=reopened_ingress,
        writer_binding=reopened_binding,
    )

    assert retried == accepted
    assert reopened_submission == submission
    assert second == first


def test_builtin_local_capability_missing_current_release_verifier_is_evidence_only() -> None:
    service = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=BuiltInLocalHostSemanticIngestionCapability(
            bootstrap_material_presentation=(
                _built_in_local_capability().bootstrap_material_presentation
            ),
            authorization_bytes=b"signed-test-authorization",
            authorization_verifier=_AuthorizationVerifier(),
            policy_provider=_PolicyProvider("owner_is"),
            current_bootstrap_release_verifier=None,
        ),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )

    assert service._bootstrap_profile is not None
    assert service._provider_ingestion._semantic_runtime is None
    assert service._semantic_atomic_store._current_bootstrap_release_verifier is None


def test_builtin_local_capability_has_no_caller_controlled_trust_domain() -> None:
    """The verifier result, not a runtime constructor label, selects the domain."""
    capability = _built_in_local_capability()
    assert "trust_domain" not in capability.__dataclass_fields__

    with pytest.raises(TypeError, match="unexpected keyword argument 'trust_domain'"):
        BuiltInLocalHostSemanticIngestionCapability(
            bootstrap_material_presentation=capability.bootstrap_material_presentation,
            authorization_bytes=capability.authorization_bytes,
            authorization_verifier=capability.authorization_verifier,
            policy_provider=capability.policy_provider,
            current_bootstrap_release_verifier=capability.current_bootstrap_release_verifier,
            trust_domain="scenario_test",
        )


def test_builtin_capability_cannot_authenticate_its_own_rebuilt_material() -> None:
    """A capability presentation without host verification never builds a runtime."""
    plane = MemoryPlaneService()
    service = ProviderMemoryService(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
    )

    assert service._bootstrap_profile is None
    assert service._provider_ingestion._semantic_runtime is None
    assert service._semantic_atomic_store._current_bootstrap_release_verifier is None
    assert tuple(plane.list_records()) == ()


def test_builtin_capability_trust_domains_cannot_cross_any_default_root(tmp_path) -> None:
    """A validly rebuilt scenario release is still never production authority."""

    scenario = build_scenario_test_host_capability()
    material = scenario.bootstrap_material_presentation.material
    original = material.release_evidence
    profile = BootstrapProfileReleaseVerifier.verify(
        payloads=material.artifact_payloads, enabled=material.profile_enabled
    )
    rebuilt_evidence = build_test_host_verified_bootstrap_release_evidence(
        profile=profile,
        external_root_digest=original.external_root_digest,
        active_lifecycle_snapshot_digest=original.active_lifecycle_snapshot_digest,
        verified_at=original.verified_at + timedelta(seconds=1),
        trust_domain="scenario_test",
    )
    scenario = replace(
        scenario,
        bootstrap_material_presentation=present_authenticated_host_bootstrap_material(
            replace(
                scenario.bootstrap_material_presentation.material,
                release_evidence=rebuilt_evidence,
            )
        ),
    )
    assert scenario.bootstrap_material_presentation.material.release_evidence == rebuilt_evidence

    roots = (
        ProviderMemoryService(
            memory_plane=MemoryPlaneService(), host_bootstrap_capability=scenario
        ),
        HermesMemoryProvider(host_bootstrap_capability=scenario)._service,
        build_filesystem_provider(
            tmp_path / "scenario-domain-default-filesystem",
            host_bootstrap_capability=scenario,
        ),
    )
    for root in roots:
        assert root._bootstrap_profile is None
        assert root._provider_ingestion._semantic_runtime is None

    # A supplied verifier does not turn a scenario proof into production
    # authority, nor production authority into a scenario fixture authority.
    cross_production = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        host_bootstrap_capability=scenario,
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    assert cross_production._bootstrap_profile is None
    assert cross_production._provider_ingestion._semantic_runtime is None
    cross_scenario = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    assert cross_scenario._bootstrap_profile is None
    assert cross_scenario._provider_ingestion._semantic_runtime is None

    # The sole fixture-private construction root is intentionally the only
    # caller allowed to consume this valid scenario-domain material.
    scenario_root = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        host_bootstrap_capability=scenario,
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    assert scenario_root._bootstrap_profile is not None
    assert scenario_root._provider_ingestion._semantic_runtime is not None


@pytest.mark.parametrize("failure", ["missing_profile", "swapped_root", "missing_ingress"])
def test_normal_provider_root_missing_bootstrap_authority_is_evidence_only(
    failure: str,
) -> None:
    capability = _LocalRuntimeCapability()
    entry_points = ()
    ingress = _host_ingress()
    if failure == "swapped_root":
        capability._payloads = capability._payloads.model_copy(
            update={"profile_manifest": b"substituted"}
        )
        entry_points = (_InstalledCapabilityEntryPoint(capability),)
    elif failure == "missing_ingress":
        entry_points = (_InstalledCapabilityEntryPoint(capability),)
        ingress = None
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=entry_points,
    ):
        service = ProviderMemoryService(memory_plane=MemoryPlaneService())
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=f"semantic-ingestion-bootstrap-authority-{failure}",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=ingress,
    )
    assert result.blocked_reasons["semantic_ingestion"] == "ingress_unavailable"
    if failure != "missing_ingress":
        assert capability.stores == []
    assert not any(
        record.source_kind.startswith("semantic_ingestion_generation")
        for record in service._memory_plane.list_records()
    )








@pytest.mark.parametrize(
    ("user_content", "assistant_content", "expected_source_texts", "expected_reason"),
    [
        # The empty child's source_only outcome wins the fan-out merge; a
        # non-empty child carrying pending corpus content fails closed at
        # this host's absent normalization bundle.
        ("Atlas owner is Bob.", "", ("Atlas owner is Bob.",), "source_only"),
        ("", "Receipt is confirmed.", ("Receipt is confirmed.",), "source_alignment_authority_unavailable"),
        ("", "", (), "source_only"),
    ],
)
def test_hermes_empty_turn_content_is_evidence_only_without_semantic_preparation(
    user_content: str,
    assistant_content: str,
    expected_source_texts: tuple[str, ...],
    expected_reason: str,
) -> None:
    capability = _LocalRuntimeCapability()
    plane = MemoryPlaneService()
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        hermes = HermesMemoryProvider(
            ProviderMemoryService(
                memory_plane=plane,
                now_provider=lambda: TEST_NOW,
                host_bootstrap_material_verifier=(
                    DeterministicTestHostBootstrapMaterialVerifier()
                ),
            )
        )

    result = hermes.sync_turn(
        user_content,
        assistant_content,
        operation_id=f"empty-turn:{len(user_content)}:{len(assistant_content)}",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    assert result.blocked_reasons["semantic_ingestion"] == expected_reason
    source_texts = tuple(
        record.text
        for record in plane.list_records(source_kind="semantic_ingestion_source")
    )
    assert source_texts == expected_source_texts
    assert all(source_texts)


class _FilesystemIntegrityCapability(_TestHostBootstrapCapability):
    def __init__(
        self,
        *,
        lifecycle: PrivilegedSemanticIntegrityLifecycle,
        holder: list[SemanticIngestionAtomicStore],
    ) -> None:
        # The composition rides the scenario-test host so it may carry the
        # full host bundles over the real filesystem store.
        super().__init__(resolver=_Resolver(), trust_domain="scenario_test")
        self._lifecycle = lifecycle
        self._holder = holder
        self.transports: list[_CaptureTransport] = []

    def build_semantic_ingestion_runtime(
        self, *, memory_plane, now_provider, bootstrap_profile
    ):
        del now_provider
        from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import (
            TestSemanticConflictAuthorityResolver,
        )

        conflict_resolver = TestSemanticConflictAuthorityResolver(memory_plane)
        _, writers, store = _verified_runtime_store(
            memory_plane,
            semantic_integrity_lifecycle=self._lifecycle,
            semantic_conflict_authority_resolver=conflict_resolver,
        )
        self._holder.append(store)
        runtime = replace(
            build_authorized_local_semantic_runtime(
                authorization_bytes=b"signed-test-authorization",
                authorization_verifier=_AuthorizationVerifier(),
                policy_provider=_PolicyProvider("owner_is"),
                writer_admission=writers,
                atomic_store=store,
                bootstrap_profile=bootstrap_profile,
            ),
            source_normalization_host_bundle=(
                _bob_owner_proposal_bundle_builder().build(atomic_store=store)
            ),
            bootstrap_graph_host_bundle=(
                _deterministic_graph_bundle_builder().build(atomic_store=store)
            ),
        )
        # Install the resolver authority through THIS runtime's
        # administration grant; the claim is lazy, so the runtime validates
        # first, and a reopened plane already carries the durable authority.
        if (
            memory_plane.get_record(
                "semantic_ingestion:conflict-authority:resolver:"
                "test-semantic-conflict-authority"
            )
            is None
        ):
            runtime.validate(profile=bootstrap_profile, server_time=TEST_NOW)
            conflict_resolver.install(
                writers, runtime.conflict_authority_administration_grant()
            )
        self.transports.append(_CaptureTransport())
        return runtime


def _filesystem_hermes_integrity_composition(root):
    holder: list[SemanticIngestionAtomicStore] = []
    linearization = ReplayIntegrityLinearization(root / "semantic_integrity" / "linearization.lock")
    integrity_repository = FileConflictIntegrityRepository(
        root / "semantic_integrity" / "integrity.jsonl",
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: TEST_NOW,
        linearization=linearization,
    )
    lifecycle = PrivilegedSemanticIntegrityLifecycle(
        integrity_repository,
        clean_recovery_request_retainer=lambda request: holder[0].retain_semantic_clean_recovery_request(request),
        clean_recovery_activator=lambda request: holder[0].activate_semantic_clean_recovery(request),
        clean_recovery_reconciler=lambda released: holder[0].reconcile_semantic_clean_recovery(released),
    )
    capability = _FilesystemIntegrityCapability(
        lifecycle=lifecycle,
        holder=holder,
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        # The scenario-test composition carries the full host bundles over
        # the real JSONL filesystem store; the graph bundle is restricted
        # to scenario construction by production contract.
        service = ProviderMemoryService._from_scenario_test_host(
            memory_plane=MemoryPlaneService(
                record_store=JsonlMemoryPlaneStore(root / "memory-plane")
            ),
            now_provider=lambda: TEST_NOW,
            host_bootstrap_capability=capability,
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
            semantic_integrity_lifecycle=lifecycle,
        )
    assert len(holder) == 1 and len(capability.transports) == 1
    return (
        service,
        HermesMemoryProvider(service),
        service._memory_plane,
        holder[0],
        lifecycle,
        capability.transports[0],
    )


def _rewrite_jsonl_snapshot(
    backend: JsonlMemoryPlaneStore,
    plane: MemoryPlaneService,
    *,
    replacements: tuple[CanonicalMemoryRecord, ...],
) -> None:
    records = {record.memory_id: record for record in plane.list_records()}
    records.update({record.memory_id: record for record in replacements})
    data_revision = int(any(record.visibility.value == "runtime_context" for record in records.values()))
    backend._replace_batches(
        [
            _PersistedBatch.create(
                revision=1,
                data_revision=data_revision,
                records=tuple(records.values()),
            )
        ]
    )


def _retained_clean_authority_batches(
    plane: MemoryPlaneService,
    store: SemanticIngestionAtomicStore,
) -> tuple[SemanticEventCleanAuthorityBatch, ...]:
    retained: list[tuple[int, SemanticEventCleanAuthorityBatch]] = []
    for record in plane.list_records(source_kind="semantic_ingestion_generation_member"):
        member = AtomicGenerationMember.model_validate(record.content["member"])
        if member.kind != "event_batch":
            continue
        batch = decode_semantic_memory_event_batch(
            member.canonical_payload,
            registry=store.event_schema_registry,
        )
        retained.append(
            (
                batch.log_position.sequence,
                SemanticEventCleanAuthorityBatch(
                    source_id=(f"semantic_ingestion:event-authority:batch:{batch.log_position.sequence:020d}"),
                    canonical_batch_bytes=member.canonical_payload,
                    source_digest=member.payload_digest,
                ),
            )
        )
    retained.sort(key=lambda item: item[0])
    assert tuple(sequence for sequence, _ in retained) == tuple(range(1, len(retained) + 1))
    return tuple(authority for _, authority in retained)


def test_real_filesystem_hermes_corruption_recovery_restart_and_racing_write(
    tmp_path,
) -> None:
    root = tmp_path / "semantic-integrity-filesystem-hermes"
    service, hermes, plane, store, lifecycle, transport = _filesystem_hermes_integrity_composition(root)
    initial = hermes.sync_turn(
        "Atlas owner is Bob.",
        "",
        operation_id="filesystem-hermes-initial",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert initial.blocked_reasons["semantic_ingestion"] == "source_only"
    # The V3 graph plane records its terminal in its own grammar; the
    # semantic event batches the integrity door recovers come from one
    # canonical clarification lifecycle through the same store.
    from memorii.core.semantic_ingestion.authorization import (
        SemanticAuthorizationAuthorityRepository as _IntegrityAuthorizationRepository,
    )
    from memorii.core.semantic_ingestion.persistence import (
        SemanticTerminalPersistenceService as _IntegrityPersistenceService,
    )
    from tests.unit.core.semantic_ingestion.test_semantic_terminal_persistence import (
        _commit_accepted_clarification,
    )

    integrity_binding = store._writers.commit_binding(store._writers.current())
    integrity_repository = _IntegrityAuthorizationRepository(
        atomic_store=store,
        writer_binding_provider=lambda: integrity_binding,
        now_provider=lambda: TEST_NOW,
    )
    integrity_persistence = _IntegrityPersistenceService(
        atomic_store=store,
        writer_binding_provider=lambda: integrity_binding,
        authorization_repository=integrity_repository,
    )
    _commit_accepted_clarification(
        store,
        sha256(b"filesystem-hermes-integrity-clarification").hexdigest(),
        plane=plane,
        service=integrity_persistence,
        authorization_repository=integrity_repository,
    )
    retained_batch_count = len(store.semantic_event_batches())
    assert retained_batch_count >= 1
    # This filesystem composition uses the deterministic local runtime.  Its
    # retained capture transport is intentionally unattached; remote transport
    # behavior is covered by the explicit-remote composition tests.
    assert transport.requests == []
    # The recovery request must carry the store's own retained view:
    # generation-member effect batches plus the clarification recovery
    # authority batch (whose digest the generation-member helper misses).
    retained_sources, _retained_bindings = store._retained_semantic_clean_authority()
    authority_batches = tuple(retained_sources)
    assert authority_batches == tuple(_retained_clean_authority_batches(plane, store)) + (
        authority_batches[-1],
    )

    active = plane.list_records(source_kind="semantic_ingestion_event_batch")[0]
    corrupted = active.model_copy(update={"content": active.content | {"canonical_hex": "00"}})
    backend = plane._records
    assert isinstance(backend, JsonlMemoryPlaneStore)
    _rewrite_jsonl_snapshot(backend, plane, replacements=(corrupted,))
    conflicting_digest = sha256(encode_typed_value(corrupted.content)).hexdigest()

    with pytest.raises(PreplanningStoreError, match="authority is corrupt"):
        hermes.sync_turn(
            "Atlas owner is Bob.",
            "",
            operation_id="filesystem-hermes-detect-corruption",
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
    frozen = lifecycle.current_control()
    assert frozen is not None and frozen.frozen_partition_ids == ("global",)
    snapshot = store.semantic_integrity_snapshot()
    request = SemanticEventCleanRecoveryRequest.create(
        repository_id="semantic_ingestion",
        repaired_partition_ids=("global",),
        authority_batches=authority_batches,
        retained_conflicting_byte_digests=(conflicting_digest,),
        retained_corrupt_generation_digest=(store.semantic_integrity_generation_digest()),
    )

    barrier = Barrier(2)

    def release():
        barrier.wait(timeout=5)
        return lifecycle.recover_and_release(
            request,
            supplied_snapshot=snapshot,
            expected_control_digest=frozen.control_digest,
        )

    def racing_write() -> str:
        barrier.wait(timeout=5)
        try:
            service.sync_event(
                operation=ProviderOperation.CHAT_USER_TURN,
                content="",
                operation_id="filesystem-provider-racing-write",
                task_id="task:one",
                user_id="user:alice",
                authenticated_host_ingress=_host_ingress(),
            )
        except (ConflictIntegrityError, PreplanningStoreError):
            return "rejected"
        return "accepted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        release_future = executor.submit(release)
        write_future = executor.submit(racing_write)
        repair, released = release_future.result(timeout=180)
        write_outcome = write_future.result(timeout=180)

    assert repair.authority_source_digests == request.authority_source_digests
    assert released.frozen_partition_ids == ()
    assert lifecycle.current_control() == released
    assert write_outcome in {"accepted", "rejected"}
    assert len(store.semantic_event_batches()) == retained_batch_count

    (
        reopened_service,
        reopened_hermes,
        _,
        reopened_store,
        reopened_lifecycle,
        reopened_transport,
    ) = _filesystem_hermes_integrity_composition(root)
    assert reopened_lifecycle.current_control() == released
    assert len(reopened_store.semantic_event_batches()) == retained_batch_count
    assert isinstance(
        reopened_hermes.prefetch(
            "Who owns Atlas?",
            task_id="task:one",
            user_id="user:alice",
        ),
        str,
    )
    assert reopened_transport.requests == []
    assert reopened_service.semantic_integrity_lifecycle.current_control() == released








@pytest.mark.parametrize("durable", (False, True))
def test_profileless_service_preserves_existing_durable_writer_at_ingress_and_reconcile(
    tmp_path, durable: bool,
) -> None:
    """Fallback ownership validates an existing admission instead of rebinding it."""
    plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "preserve") if durable else None
    )
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: TEST_NOW
    )
    existing = writers.create_initial_evidence_only(
        admission_id="existing-writer",
        writer_implementation_fingerprint="existing-implementation",
        graph_schema_fingerprint="existing-schema",
    )
    before = plane.get_record(writer_admission_memory_id())
    assert before is not None

    resolver = _SwitchingIngressResolver()
    service = ProviderMemoryService(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        authenticated_ingress_resolver=resolver,
    )
    assert service._bootstrap_profile is None
    assert plane.get_record(writer_admission_memory_id()) == before

    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="profileless-existing-writer", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert service.reconcile_memory_evolution() == []
    assert writers.current() == existing
    assert plane.get_record(writer_admission_memory_id()) == before


@pytest.mark.parametrize("durable", (False, True))
def test_profileless_service_waits_for_resolved_ingress_then_creates_default_once(
    tmp_path, durable: bool,
) -> None:
    """Construction is write-free; first authenticated ingress creates one default record."""
    plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "wait") if durable else None
    )
    resolver = _SwitchingIngressResolver()
    service = ProviderMemoryService(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        authenticated_ingress_resolver=resolver,
    )
    assert plane.get_record(writer_admission_memory_id()) is None

    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="profileless-missing-ingress", task_id="task:one", user_id="user:alice",
    )
    assert plane.get_record(writer_admission_memory_id()) is None
    resolver.reject = True
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="profileless-rejected-ingress", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert plane.get_record(writer_admission_memory_id()) is None
    resolver.reject = False

    for operation_id in ("profileless-new-writer-one", "profileless-new-writer-two"):
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
            operation_id=operation_id, task_id="task:one", user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
    records = [
        record for record in plane.list_records()
        if record.memory_id == writer_admission_memory_id()
    ]
    assert len(records) == 1
    current = service._semantic_writer_admission.current()
    assert current.admission_id == "memorii-provider-semantic-writer-v1"
    assert current.active_runtime_mode == "evidence_only"


@pytest.mark.parametrize("hermes", (False, True))
def test_memory_write_preflights_ingress_before_writer_creation(hermes: bool) -> None:
    plane = MemoryPlaneService()
    resolver = _SwitchingIngressResolver()
    service = ProviderMemoryService(
        memory_plane=plane, now_provider=lambda: TEST_NOW,
        authenticated_ingress_resolver=resolver,
    )
    root = HermesMemoryProvider(service) if hermes else service
    if hermes:
        def invoke(ingress):
            return root.on_memory_write("write", "memory", "Atlas", operation_id="write", task_id="task:one", user_id="user:alice", authenticated_host_ingress=ingress)
    else:
        def invoke(ingress):
            return root.apply_memory_write(operation=ProviderOperation.MEMORY_WRITE_USER, content="Atlas", action="write", target="memory", operation_id="write", session_id=None, task_id="task:one", user_id="user:alice", authenticated_host_ingress=ingress)
    invoke(None)
    resolver.reject = True
    invoke(_host_ingress())
    assert plane.get_record(writer_admission_memory_id()) is None
    resolver.reject = False
    invoke(_host_ingress())
    invoke(_host_ingress())
    assert len([r for r in plane.list_records() if r.memory_id == writer_admission_memory_id()]) == 1


def test_configured_hermes_constructs_write_free_then_creates_once_after_authenticated_turn() -> None:
    """The service-free Hermes root forwards its verified host composition unchanged."""
    plane = MemoryPlaneService()
    resolver = _SwitchingIngressResolver()
    hermes = HermesMemoryProvider(
        service=None,
        memory_plane=plane,
        host_bootstrap_capability=_built_in_local_capability(resolver=resolver),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    assert plane.get_record(writer_admission_memory_id()) is None

    resolver.reject = True
    hermes.sync_turn(
        "Atlas owner is Bob.", "Noted.", operation_id="configured-hermes-rejected",
        task_id="task:one", user_id="user:alice", authenticated_host_ingress=_host_ingress(),
    )
    assert plane.get_record(writer_admission_memory_id()) is None

    resolver.reject = False
    hermes.sync_turn(
        "Atlas owner is Bob.", "Noted.", operation_id="configured-hermes-resolved",
        task_id="task:one", user_id="user:alice", authenticated_host_ingress=_host_ingress(),
    )
    writer_records = [
        record for record in plane.list_records()
        if record.memory_id == writer_admission_memory_id()
    ]
    assert len(writer_records) == 1


def _writer_failure_snapshot(
    backend: JsonlMemoryPlaneStore,
    plane: MemoryPlaneService,
) -> tuple[bytes, tuple[CanonicalMemoryRecord, ...]]:
    return (
        backend._records_path.read_bytes(),
        tuple(sorted(plane.list_records(), key=lambda record: record.memory_id)),
    )


@pytest.mark.parametrize("writer_state", ("corrupt", "foreign_manifest"))
def test_profileless_service_rejects_invalid_or_foreign_durable_writer_without_writes(
    tmp_path, writer_state: str,
) -> None:
    """Writer validation fails before source ingestion can change the durable JSONL state."""
    storage = tmp_path / writer_state
    backend = JsonlMemoryPlaneStore(storage)
    plane = MemoryPlaneService(record_store=backend)
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: TEST_NOW
    )
    writers.create_initial_evidence_only(
        admission_id="valid-writer",
        writer_implementation_fingerprint="valid-implementation",
        graph_schema_fingerprint="valid-schema",
    )
    original = plane.get_record(writer_admission_memory_id())
    assert original is not None
    if writer_state == "corrupt":
        replacement = original.model_copy(update={"content": {"corrupt": True}})
    else:
        manifest = dict(original.content["manifest"])
        manifest["manifest_revision"] = "foreign-semantic-generation-v2"
        manifest["manifest_digest"] = sha256(
            encode_typed_value(
                {
                    "manifest_revision": manifest["manifest_revision"],
                    "governed_record_kinds": frozenset(manifest["governed_record_kinds"]),
                    "semantic_store_methods": frozenset(manifest["semantic_store_methods"]),
                }
            )
        ).hexdigest()
        replacement = original.model_copy(
            update={"content": original.content | {"manifest": manifest}}
        )
    _rewrite_jsonl_snapshot(backend, plane, replacements=(replacement,))
    reopened = ProviderMemoryService(
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage)),
        now_provider=lambda: TEST_NOW,
        authenticated_ingress_resolver=_Resolver(),
    )
    before = _writer_failure_snapshot(backend, reopened._memory_plane)
    with pytest.raises(SemanticWriterAdmissionError):
        reopened.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
            operation_id=f"profileless-{writer_state}-writer", task_id="task:one", user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
    assert _writer_failure_snapshot(backend, reopened._memory_plane) == before
    writer_records = [
        record for record in reopened._memory_plane.list_records()
        if record.memory_id == writer_admission_memory_id()
    ]
    assert writer_records == [replacement]
    assert not [
        record for record in reopened._memory_plane.list_records()
        if record.source_kind != "semantic_ingestion_writer_admission"
    ]


@pytest.mark.parametrize("mutation", ["rotate", "revoke", "coordinate"])
def test_jsonl_recovery_authority_change_is_zero_learned_calls(
    tmp_path,
    mutation: str,
) -> None:
    storage = tmp_path / mutation
    plane, writers, store = _verified_runtime_store(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage)))
    failed_capability = _AuthorizedCapability(
        runtime_factory=_runtime_factory_for_outage(writers=writers, store=store, stage="proposal")
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(failed_capability),),
    ):
        failed_service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW, host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier())
    failed_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=f"semantic-ingestion-recovery-{mutation}",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    control_record = next(
        record for record in plane.list_records() if record.source_kind == "semantic_ingestion_preplanning_control"
    )
    control = PreplanningOperationControl.model_validate(control_record.content["control"])
    # The retained control is the reconcilable authority for the failed
    # operation; its authorization scope derives from the admitted source.
    scope_id = SemanticAuthorizationAuthorityRepository.scope_id(
        source_id=control.operation_fence.source_id,
        source_digest=control.operation_fence.source_digest,
    )
    # The failed pass stops before publishing any authorization read set;
    # install the retained authority explicitly so each rotation mutation
    # operates on durable state, as the reconciling host would find it.
    authority_bundle = accepted_terminal(
        operation_id=control.operation_fence.operation_id
    ).arbitration_policy_bundle
    assert authority_bundle is not None
    SemanticAuthorizationAuthorityRepository(
        atomic_store=store,
        writer_binding_provider=lambda: writers.commit_binding(writers.current()),
        now_provider=lambda: TEST_NOW,
    ).observe_verified(
        authority_scope_id=scope_id,
        read_set=SemanticAuthorizationReadSet.create(
            policy_bundle=authority_bundle,
            deployment_authorization_digest="d" * 64,
            deployment_active_epoch=1,
            deployment_decision_digest="e" * 64,
        ),
        valid_until=TEST_NOW + timedelta(days=1),
    )
    current = store.authorization_authority(scope_id)
    assert current is not None
    authority, precondition = current
    body = authority.model_dump(mode="python", exclude={"coordinates_digest"})
    body.update({"authority_revision": 2, "state": mutation == "revoke" and "revoked" or "active"})
    if mutation == "rotate":
        body["deployment_authorization_digest"] = "9" * 64
    if mutation == "coordinate":
        body["policy_bundle_digest"] = "8" * 64
        body["read_set_digest"] = "7" * 64
    replacement = SemanticAuthorizationAuthorityRecord(
        **body,
        coordinates_digest=sha256(encode_typed_value(body)).hexdigest(),
    )
    store.replace_authorization_authority(
        writer_binding=writers.commit_binding(writers.current()),
        expected=precondition,
        authority=replacement,
    )

    reopened_plane, reopened_writers, reopened_store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    assessor = _CountingAssessor()
    transport, capability = _dependencies(
        writer_admission=reopened_writers,
        atomic_store=reopened_store,
        assessor=assessor,
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        reopened = ProviderMemoryService(memory_plane=reopened_plane, now_provider=lambda: TEST_NOW, host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier())
    outcomes = reopened.reconcile_memory_evolution()
    assert [outcome.status for outcome in outcomes] == ["evolution_pending"]
    assert transport.requests == []
    assert assessor.calls == 0
    kinds = {
        record.content["member"]["kind"]
        for record in reopened_plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    }
    assert "graph_delta" not in kinds
    assert "event_batch" not in kinds
    assert "source_result" not in kinds


def test_foreign_recovery_plan_is_rejected_before_lease_or_learned_calls(tmp_path) -> None:
    foreign_plane, foreign_writers, foreign_store = _verified_runtime_store()
    foreign_capability = _AuthorizedCapability(
        runtime_factory=_runtime_factory_for_outage(writers=foreign_writers, store=foreign_store, stage="proposal")
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(foreign_capability),),
    ):
        foreign_service = ProviderMemoryService(memory_plane=foreign_plane, now_provider=lambda: TEST_NOW, host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier())
    foreign_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-foreign-plan-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    foreign_control = PreplanningOperationControl.model_validate(
        next(
            record.content["control"]
            for record in foreign_plane.list_records()
            if record.source_kind == "semantic_ingestion_preplanning_control"
        )
    )
    # The retained control itself is the foreign operation's recoverable
    # authority; execution plans were pipeline-era machinery.
    assert foreign_control.operation_fence is not None

    storage = tmp_path / "foreign-plan-target"
    target_plane, target_writers, target_store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    target_capability = _AuthorizedCapability(
        runtime_factory=_runtime_factory_for_outage(writers=target_writers, store=target_store, stage="proposal")
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(target_capability),),
    ):
        target_service = ProviderMemoryService(memory_plane=target_plane, now_provider=lambda: TEST_NOW, host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier())
    target_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-foreign-plan-target",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    reopened_plane, reopened_writers, reopened_store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    assessor = _CountingAssessor()
    transport, capability = _dependencies(
        writer_admission=reopened_writers,
        atomic_store=reopened_store,
        assessor=assessor,
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        reopened = ProviderMemoryService(memory_plane=reopened_plane, now_provider=lambda: TEST_NOW, host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier())
    # A foreign retained marker cannot complete the reconciled control:
    # admission is marker-keyed by fence, so the substituted marker fails
    # closed before any model call, exactly as a foreign plan once did.
    foreign_marker = BootstrapWriterHandoffMarkerV3.model_validate(
        foreign_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_handoff_marker"
        )[0].content["marker"]
    )
    with patch.object(
        reopened_store,
        "load_bootstrap_writer_handoff_marker_v3",
        return_value=foreign_marker,
    ):
        outcomes = reopened.reconcile_memory_evolution()
    assert [outcome.status for outcome in outcomes] == ["evolution_pending"]
    assert transport.requests == []
    assert assessor.calls == 0


def test_identical_redelivery_after_authority_rotation_reuses_plan_without_calls(
    tmp_path,
) -> None:
    storage = tmp_path / "redelivery-rotation"
    plane, writers, store = _verified_runtime_store(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage)))
    capability = _AuthorizedCapability(runtime_factory=_runtime_factory_for_outage(writers=writers, store=store, stage="proposal"))
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW, host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier())
    event_kwargs = {
        "operation": ProviderOperation.CHAT_USER_TURN,
        "content": "Atlas owner is Bob.",
        "operation_id": "semantic-ingestion-identical-redelivery-rotation",
        "task_id": "task:one",
        "user_id": "user:alice",
        "authenticated_host_ingress": _host_ingress(),
    }
    service.sync_event(**event_kwargs)
    control = PreplanningOperationControl.model_validate(
        next(
            record.content["control"]
            for record in plane.list_records()
            if record.source_kind == "semantic_ingestion_preplanning_control"
        )
    )
    scope_id = SemanticAuthorizationAuthorityRepository.scope_id(
        source_id=control.operation_fence.source_id,
        source_digest=control.operation_fence.source_digest,
    )
    authority_bundle = accepted_terminal(
        operation_id=control.operation_fence.operation_id
    ).arbitration_policy_bundle
    assert authority_bundle is not None
    SemanticAuthorizationAuthorityRepository(
        atomic_store=store,
        writer_binding_provider=lambda: writers.commit_binding(writers.current()),
        now_provider=lambda: TEST_NOW,
    ).observe_verified(
        authority_scope_id=scope_id,
        read_set=SemanticAuthorizationReadSet.create(
            policy_bundle=authority_bundle,
            deployment_authorization_digest="d" * 64,
            deployment_active_epoch=1,
            deployment_decision_digest="e" * 64,
        ),
        valid_until=TEST_NOW + timedelta(days=1),
    )
    current = store.authorization_authority(scope_id)
    assert current is not None
    authority, precondition = current
    body = authority.model_dump(mode="python", exclude={"coordinates_digest"})
    body.update(
        {
            "authority_revision": 2,
            "deployment_authorization_digest": "9" * 64,
        }
    )
    store.replace_authorization_authority(
        writer_binding=writers.commit_binding(writers.current()),
        expected=precondition,
        authority=SemanticAuthorizationAuthorityRecord(
            **body,
            coordinates_digest=sha256(encode_typed_value(body)).hexdigest(),
        ),
    )

    reopened_plane, reopened_writers, reopened_store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    # The redelivery service must carry the same profile-aware preparation
    # seam as the original pass: the retained prepared source's grammar
    # proofs bind its routes, and a minimal producer cannot re-publish it.
    recovered_capability = _AuthorizedCapability(
        runtime_factory=_runtime_factory_for_outage(
            writers=reopened_writers, store=reopened_store, stage="proposal"
        )
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(recovered_capability),),
    ):
        reopened = ProviderMemoryService(memory_plane=reopened_plane, now_provider=lambda: TEST_NOW, host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier())
    result = reopened.sync_event(**event_kwargs)
    # The identical redelivery re-enters the retained marker and fails
    # closed at the absent normalization authority: no model round runs,
    # and no terminal or source-result effect is duplicated.
    assert result.blocked_reasons["semantic_ingestion"] == "source_alignment_authority_unavailable"
    kinds = [
        record.content["member"]["kind"]
        for record in reopened_plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    ]
    assert "source_result" not in kinds


def test_public_reconcile_leaves_unpublished_normalization_pending(tmp_path) -> None:
    storage = tmp_path / "exhaustion"
    plane, writers, store = _verified_runtime_store(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage)))
    capability = _AuthorizedCapability(runtime_factory=_runtime_factory_for_outage(writers=writers, store=store, stage="policy_read"))
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW, host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier())
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-retry-exhaustion",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    # An unpublished normalization is never exhausted or completed by
    # reconcile: it stays retryable forever, exact redelivery remains its
    # only recovery door, and no terminal/source-result effect is written.
    for _ in range(3):
        outcomes = service.reconcile_memory_evolution()
        assert [outcome.status for outcome in outcomes] == ["evolution_pending"]
        assert all(outcome.retryable for outcome in outcomes)
    controls = [
        record.content["control"]
        for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_preplanning_control"
    ]
    assert len(controls) == 1
    assert controls[0]["state"] == "preplanning"
    source_results = [
        member
        for generation in range(2, controls[0]["generation"] + 1)
        for member in store.generation_members(
            PreplanningOperationControl.model_validate(controls[0]).operation_fence,
            generation,
        )
        if member.kind == "source_result"
    ]
    assert source_results == []


def _bob_owner_proposal_bundle_builder():
    """Normalization host builder carrying the corpus owner-is proposal."""

    builder, _calls = _v3_normalization_host_builder(
        proposal=_bob_owner_proposal()
    )
    return builder


def _bob_owner_proposal(predicate_id: str = "owner_is"):
    from memorii.core.semantic_ingestion.contracts import (
        ProviderEntityObject,
        ProviderFact,
        ProviderMention,
        ProviderSemanticProposal,
    )

    return ProviderSemanticProposal(
        mentions=(
            ProviderMention(local_id="atlas", mention_quote="Atlas", mention_context_quote="Atlas owner is Bob."),
            ProviderMention(local_id="bob", mention_quote="Bob", mention_context_quote="Atlas owner is Bob."),
        ),
        facts=(
            ProviderFact(
                local_id="owner",
                predicate_id=predicate_id,
                subject_entity_ref="atlas",
                object=ProviderEntityObject(entity_ref="bob"),
                assertion_quote="Atlas owner is Bob.",
                predicate_anchor_quote="owner",
                polarity="positive",
                commitment="asserted",
            ),
        ),
        abstained=False,
    )


def _deterministic_graph_bundle_builder():
    from memorii.core.semantic_ingestion.bootstrap_graph_host import (
        BootstrapGraphHostBundleBuilder,
    )
    from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
        DeterministicBootstrapGraphAuthorityProviderV3,
    )

    return BootstrapGraphHostBundleBuilder(
        authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
            successful_calls=[]
        )
    )


def _full_v3_service(plane, *, storage_unused=None):
    """Compose the complete V3 scenario flow: normalization and graph host."""

    return ProviderMemoryService._from_scenario_test_host(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=_bob_owner_proposal_bundle_builder(),
        bootstrap_graph_host_bundle_builder=_deterministic_graph_bundle_builder(),
    )


@pytest.mark.parametrize(
    "boundary",
    [
        "checkpoint_source_progress",
        "commit_or_reload_bootstrap_graph_group_v3",
        "persist_bootstrap_graph_terminal_v3",
    ],
)
def test_public_jsonl_lost_ack_reopens_without_duplicate_effects(
    tmp_path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    storage = tmp_path / boundary
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    service = _full_v3_service(plane)
    store = service._semantic_atomic_store
    original = getattr(store, boundary)
    failed = False

    def apply_then_fail(*args, **kwargs):
        nonlocal failed
        result = original(*args, **kwargs)
        if not failed:
            failed = True
            raise OSError(f"{boundary} lost acknowledgement")
        return result

    monkeypatch.setattr(store, boundary, apply_then_fail)

    def call():
        return service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id=f"semantic-ingestion-lost-ack-{boundary}",
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )

    call()

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened = _full_v3_service(reopened_plane)
    outcomes = reopened.reconcile_memory_evolution()
    assert failed is True
    controls = [
        record.content["control"]
        for record in reopened_plane.list_records()
        if record.source_kind == "semantic_ingestion_preplanning_control"
    ]
    assert len(controls) == 1 and controls[0]["state"] == "terminal"
    # Exactly one graph terminal identity survives the lost
    # acknowledgement; the recovery door never duplicates it.
    terminal_identities = reopened_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_identity"
    )
    assert len(terminal_identities) == 1
    assert [outcome.status for outcome in outcomes] in ([], ["evolution_committed"])
    assert reopened.reconcile_memory_evolution() == []


def test_public_flow_prepared_source_contract_is_frozen_across_runs(
    tmp_path,
) -> None:
    """The V3 public flow's prepared-source contract is frozen across runs.

    The graph plane's epoch locators and request digests are per-run
    nonces by construction, so raw JSONL bytes are deliberately not the
    frozen witness.  Deterministic reconstruction lives in the sealed
    prepared source the whole flow derives from: its source digest and
    preparation fingerprint must be identical for the same public input
    on every run.
    """

    def run_public_flow(storage):
        plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        service = _full_v3_service(plane)
        result = service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id="semantic-ingestion-frozen-public-integration",
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
        assert result.blocked_reasons.get("semantic_ingestion") == "source_only"
        identities = plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_identity"
        )
        assert len(identities) == 1
        inner = identities[0].content["identity"]
        return inner["source_digest"], inner["preparation_fingerprint"]

    prepared_contract = run_public_flow(tmp_path / "frozen-public-integration-one")
    assert run_public_flow(tmp_path / "frozen-public-integration-two") == prepared_contract
    # Only the source digest is a stable cross-environment witness: the
    # preparation fingerprint transitively covers the bootstrap profile's
    # verified component digests, which pin the live environment's component
    # source bytes and installed package versions by design
    # (verify_bootstrap_profile). Its absolute value therefore moves with the
    # environment and cannot be a hex-pinned constant; cross-run equality for
    # identical code and inputs is the frozen-witness contract.
    source_digest, preparation_fingerprint = prepared_contract
    assert source_digest == (
        "546b01c202f669fb5cca9933bfc509a5ba2c3718ab25ba54f1ba5eb0fc4983cf"
    )
    assert re.fullmatch(r"[0-9a-f]{64}", preparation_fingerprint)

def test_hermes_root_preserves_existing_durable_writer_and_skips_writes_without_ingress(
    tmp_path,
) -> None:
    """The Hermes fan-out root keeps the fallback writer-admission contract."""
    plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "hermes-family")
    )
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: TEST_NOW
    )
    existing = writers.create_initial_evidence_only(
        admission_id="existing-writer",
        writer_implementation_fingerprint="existing-implementation",
        graph_schema_fingerprint="existing-schema",
    )
    before = plane.get_record(writer_admission_memory_id())
    assert before is not None

    resolver = _SwitchingIngressResolver()
    service = ProviderMemoryService(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        authenticated_ingress_resolver=resolver,
    )
    hermes = HermesMemoryProvider(service=service)

    # Absent ingress through the Hermes root writes nothing.
    hermes.sync_turn(
        "Atlas owner is Bob.", "Atlas owner is Bob.",
        operation_id="hermes-family-absent", task_id="task:one", user_id="user:alice",
    )
    assert plane.get_record(writer_admission_memory_id()) == before
    hermes.on_memory_write(
        content="Atlas owner is Bob.", action="upsert", target="memory",
        operation_id="hermes-family-absent-write",
        session_id=None, task_id="task:one", user_id="user:alice",
    )
    assert plane.get_record(writer_admission_memory_id()) == before

    # A resolved authenticated turn preserves the existing record exactly.
    hermes.sync_turn(
        "Atlas owner is Bob.", "Atlas owner is Bob.",
        operation_id="hermes-family-resolved", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert service.reconcile_memory_evolution() == []
    assert writers.current() == existing
    assert plane.get_record(writer_admission_memory_id()) == before


@pytest.mark.parametrize("root", ("factory", "filesystem"))
def test_composed_roots_write_nothing_without_resolved_ingress(root, tmp_path) -> None:
    """Factory and filesystem roots stay write-free at absent ingress."""
    plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / root)
    )
    if root == "factory":
        service = build_provider_memory_service_from_env(
            memory_plane=plane, now_provider=lambda: TEST_NOW
        )
    else:
        service = build_filesystem_provider(
            tmp_path / "storage", memory_plane=plane, now_provider=lambda: TEST_NOW
        )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id=f"{root}-absent-ingress", task_id="task:one", user_id="user:alice",
    )
    assert plane.get_record(writer_admission_memory_id()) is None


def test_provider_preserves_verified_activation_target_and_revalidates_before_cutover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.memory_evolution.observation_activation_configuration import (
        ObservationActivationTargetConfigurationError,
    )
    from tests.unit.core.memory_evolution.test_observation_activation_configuration import _signed_package

    registry = _small_real_configured_registry_material(tmp_path)
    target, _, _ = _signed_package(tmp_path, monkeypatch, verify_configured_typed_value_registry_history(registry))
    plane = MemoryPlaneService()
    service = ProviderMemoryService(
        memory_plane=plane, now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=replace(
            _built_in_local_capability(), typed_value_registry_configuration=registry,
            observation_activation_target_configuration=target,
        ),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    runtime = service._composed_semantic_runtime
    assert runtime is not None and runtime.observation_activation_target is not None
    assert runtime.writer_admission is not None and runtime.atomic_store is not None
    assert runtime.observation_activation_target is runtime.writer_admission._observation_activation_target
    assert runtime.observation_activation_target is runtime.atomic_store._observation_activation_target
    runtime.writer_admission.create_initial_evidence_only(
        admission_id="configured-host-writer",
        writer_implementation_fingerprint="configured-host-legacy-writer",
        graph_schema_fingerprint="memorii-semantic-graph-v1",
    )
    before = plane.read_write_snapshot()
    with pytest.raises(PreplanningStoreError, match="registered schemas are unavailable"):
        service.activate_observation_ledger()
    after = plane.read_write_snapshot()
    assert after[0] == before[0] + 1
    assert tuple(record for record in after[1] if record.source_kind != "semantic_ingestion_reference_integrity") == before[1]
    assert [record.source_kind for record in after[1]].count(
        "semantic_ingestion_reference_integrity"
    ) == 1
    (target.deployment_configuration.installation_root / "memorii/empty.py").write_bytes(b"changed")
    with pytest.raises(ObservationActivationTargetConfigurationError):
        service.activate_observation_ledger()
    assert plane.read_write_snapshot() == after


def test_invalid_activation_target_never_falls_back_to_legacy_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.memory_evolution.observation_activation_configuration import (
        ObservationActivationTargetConfigurationError,
    )
    from tests.unit.core.memory_evolution.test_observation_activation_configuration import _signed_package

    registry = _small_real_configured_registry_material(tmp_path)
    target, _, _ = _signed_package(tmp_path, monkeypatch, verify_configured_typed_value_registry_history(registry))
    target = replace(target, selected_manifest_sha256="0" * 64)
    plane = MemoryPlaneService()
    before = plane.read_write_snapshot()
    with pytest.raises(ObservationActivationTargetConfigurationError):
        ProviderMemoryService(
            memory_plane=plane, now_provider=lambda: TEST_NOW,
            host_bootstrap_capability=replace(
                _built_in_local_capability(), typed_value_registry_configuration=registry,
                observation_activation_target_configuration=target,
            ),
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )
    assert plane.read_write_snapshot() == before


def test_unconfigured_provider_activation_is_explicitly_unavailable() -> None:
    plane = MemoryPlaneService()
    service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW)
    before = plane.read_write_snapshot()
    with pytest.raises(PreplanningStoreError, match="target authority is not configured"):
        service.activate_observation_ledger()
    assert plane.read_write_snapshot() == before


def test_explicit_activation_checks_current_deployment_authorization_before_atomic_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.core.memory_evolution.test_observation_activation_configuration import _signed_package

    registry = _small_real_configured_registry_material(tmp_path)
    target, _, _ = _signed_package(tmp_path, monkeypatch, verify_configured_typed_value_registry_history(registry))
    verifier = _AuthorizationVerifier()
    plane = MemoryPlaneService()
    service = ProviderMemoryService(
        memory_plane=plane, now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=replace(
            _built_in_local_capability(), typed_value_registry_configuration=registry,
            observation_activation_target_configuration=target, authorization_verifier=verifier,
        ),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    runtime = service._composed_semantic_runtime
    assert runtime is not None and runtime.atomic_store is not None
    before = plane.read_write_snapshot()
    with patch.object(
        runtime.atomic_store, "activate_observation_ledger", wraps=runtime.atomic_store.activate_observation_ledger
    ) as activate:
        for mode in ("revoked", "expired", "mutated", "outage"):
            verifier.mode = mode
            for trigger in (service.activate_observation_ledger, runtime.activate_observation_ledger):
                error = OSError if mode == "outage" else ValueError
                with pytest.raises(error, match="authorization.*unavailable"):
                    trigger()
                activate.assert_not_called()
                assert plane.read_write_snapshot() == before


def test_bootstrap_graph_execution_preserves_live_lease_identity() -> None:
    now = TEST_NOW
    fence = SimpleNamespace(operation_fence_id="fence", operation_id="operation")
    writer = SimpleNamespace(binding_digest="writer")
    near_expiry = PreplanningLease(
        owner_id="bootstrap-v3-recovery",
        execution_token="original-execution",
        ownership_epoch=1,
        acquired_at=now - timedelta(minutes=14),
        expires_at=now + timedelta(minutes=1),
        renewal_interval=timedelta(minutes=15),
    )
    control = SimpleNamespace(state="planned", lease=near_expiry, writer_binding=writer)
    coordinator = object.__new__(ProviderIngestionCoordinator)
    coordinator._atomic_store = object()
    coordinator._now_provider = lambda: now
    executed: list[object] = []

    assert coordinator._execute_bootstrap_graph_with_expired_lease_retry(
        operation_fence=fence,
        initial_control=control,
        replay=object(),
        execute=lambda current: executed.append(current) or "terminal",
    ) == "terminal"
    assert executed == [control]

    fresh = near_expiry.model_copy(update={"expires_at": now + timedelta(minutes=9)})
    control.lease = fresh
    executed.clear()
    assert coordinator._execute_bootstrap_graph_with_expired_lease_retry(
        operation_fence=fence,
        initial_control=control,
        replay=object(),
        execute=lambda current: executed.append(current) or "terminal",
    ) == "terminal"
    assert executed == [control]

    control.lease = near_expiry.model_copy(update={"owner_id": "foreign-owner"})
    executed.clear()
    assert coordinator._execute_bootstrap_graph_with_expired_lease_retry(
        operation_fence=fence,
        initial_control=control,
        replay=object(),
        execute=lambda current: executed.append(current) or "terminal",
    ) is None
    assert executed == []

    control.lease = near_expiry.model_copy(update={"expires_at": now})
    assert coordinator._execute_bootstrap_graph_with_expired_lease_retry(
        operation_fence=fence,
        initial_control=control,
        replay=object(),
        execute=lambda current: executed.append(current) or "terminal",
    ) is None
    assert executed == []


def test_expired_bootstrap_graph_execution_error_reclaims_once() -> None:
    now = TEST_NOW
    fence = SimpleNamespace(operation_fence_id="fence", operation_id="operation")
    writer = SimpleNamespace(binding_digest="writer")
    fresh = PreplanningLease(
        owner_id="bootstrap-v3-recovery", execution_token="first", ownership_epoch=1,
        acquired_at=now - timedelta(minutes=6), expires_at=now + timedelta(minutes=9),
        renewal_interval=timedelta(minutes=7, seconds=30),
    )
    expired = fresh.model_copy(update={"expires_at": now - timedelta(seconds=1)})
    control = SimpleNamespace(state="planned", lease=fresh, writer_binding=writer)
    reclaimed = SimpleNamespace(
        state="planned",
        lease=expired.model_copy(update={"execution_token": "reclaimed", "ownership_epoch": 2}),
        writer_binding=writer,
    )

    class AtomicStore:
        def __init__(self) -> None:
            self.reclaims: list[dict[str, object]] = []

        def renew_lease(self, **_kwargs: object) -> object:
            return control

        def get_operation(self, observed_fence: object) -> object:
            assert observed_fence is fence
            return control

        def acquire_lease(self, **kwargs: object) -> object:
            self.reclaims.append(kwargs)
            return reclaimed

    atomic = AtomicStore()
    coordinator = object.__new__(ProviderIngestionCoordinator)
    coordinator._atomic_store = atomic
    coordinator._now_provider = lambda: now
    executed: list[object] = []

    def stale_then_succeed(current: object) -> object:
        executed.append(current)
        if current is control:
            control.lease = expired
            raise PreplanningStoreError("graph authority expired")
        return "terminal"

    assert coordinator._execute_bootstrap_graph_with_expired_lease_retry(
        operation_fence=fence, initial_control=control, replay=object(), execute=stale_then_succeed,
    ) == "terminal"
    assert executed == [control, reclaimed]
    assert atomic.reclaims == [{
        "operation_fence": fence, "writer_binding": writer,
        "execution_token": "bootstrap-v3-graph-retry:fence",
        "owner_id": "bootstrap-v3-recovery", "duration": timedelta(minutes=15),
    }]

    control.lease = fresh
    assert coordinator._reclaim_expired_bootstrap_graph_lease(operation_fence=fence) is None
    assert len(atomic.reclaims) == 1
    with pytest.raises(StructuredSubmissionGrantRevokedError):
        coordinator._execute_bootstrap_graph_with_expired_lease_retry(
            operation_fence=fence, initial_control=control, replay=object(),
            execute=lambda _current: (_ for _ in ()).throw(
                StructuredSubmissionGrantRevokedError("structured submission grant is revoked")
            ),
        )
    assert len(atomic.reclaims) == 1


def test_provider_root_uses_preflight_renewed_lease_for_native_graph_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary provider root constructs the native request from renewed control."""
    from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphHostBundle

    clock = [TEST_NOW]
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: clock[0],
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=_bob_owner_proposal_bundle_builder(),
    )
    atomic = service._semantic_atomic_store
    original_reload = atomic.reload_bootstrap_recovery_replay_v3
    observed_lease_bindings: list[object] = []
    observed_controls: list[object] = []

    def reload_then_near_expire(**kwargs):
        replay = original_reload(**kwargs)
        control = atomic.get_operation(kwargs["handoff_marker"].operation_fence_binding)
        assert control.lease is not None
        clock[0] = control.lease.expires_at - control.lease.renewal_interval
        return replay

    def observe_request(_bundle, *, request):
        observed_lease_bindings.append(request.operation_lease_binding)
        observed_controls.append(atomic.get_operation(request.operation_fence_binding))
        return None

    monkeypatch.setattr(atomic, "reload_bootstrap_recovery_replay_v3", reload_then_near_expire)
    monkeypatch.setattr(BootstrapGraphHostBundle, "execute", observe_request)
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="provider-preflight-lease-renewal",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert len(observed_lease_bindings) == 1
    control = observed_controls[0]
    assert control.lease is not None
    assert observed_lease_bindings[0] == atomic.lease_binding(control)


def test_provider_root_returns_durable_graph_retry_without_reclaim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persisted graph retry is terminal progress, not a second graph attempt."""
    from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphHostBundle

    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=_bob_owner_proposal_bundle_builder(),
    )
    atomic = service._semantic_atomic_store
    retry = BootstrapGraphDurableRetryProgressV3.create(
        kind="durable_retry", request_digest="0" * 64,
        normalization_replay_digest="1" * 64, attempt_digest="2" * 64,
        source_plan_lineage_digest="3" * 64, completed_group_result_digests=(),
        retry_group_ids=(), reason="storage_retry", operation_fence_binding_digest="4" * 64,
        writer_commit_binding_digest="5" * 64, control_epoch_digest="6" * 64,
        progress_digest="7" * 64,
    )
    original_reload = atomic.reload_bootstrap_recovery_replay_v3
    original_acquire = atomic.acquire_lease
    acquires: list[object] = []
    executions: list[object] = []
    terminal_attempts: list[object] = []

    def reload_then_reset(**kwargs):
        replay = original_reload(**kwargs)
        acquires.clear()
        return replay

    def observe_acquire(**kwargs):
        acquires.append(kwargs)
        return original_acquire(**kwargs)

    def return_retry(_bundle, *, request):
        executions.append(request)
        return retry

    def terminal_attempt(**kwargs):
        terminal_attempts.append(kwargs)
        raise AssertionError("durable retry must not attempt graph terminal persistence")

    monkeypatch.setattr(atomic, "reload_bootstrap_recovery_replay_v3", reload_then_reset)
    monkeypatch.setattr(atomic, "acquire_lease", observe_acquire)
    monkeypatch.setattr(BootstrapGraphHostBundle, "execute", return_retry)
    monkeypatch.setattr(atomic, "persist_bootstrap_graph_terminal_v3", terminal_attempt)
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="provider-durable-graph-retry",
        task_id="task:one", user_id="user:alice", authenticated_host_ingress=_host_ingress(),
    )

    assert len(executions) == 1
    assert acquires == []
    assert terminal_attempts == []
    assert result.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
