import re
import sys as _sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

# The sibling support module resolves as a top-level import under pytest's
# prepend mode, but the bootstrap-graph process runner imports this module
# in a fresh interpreter without that path entry.
if (support_dir := str(Path(__file__).parent)) not in _sys.path:
    _sys.path.insert(0, support_dir)

import pytest
from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    BootstrapWriterHandoffMarkerV3,
    PreplanningOperationControl,
    PreplanningStoreError,
    SemanticAuthorizationAuthorityRecord,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapGrammarCorpusCase,
    BootstrapProfileReleaseMetadata,
    CurrentBootstrapReleaseAssertion,
    HostVerifiedBootstrapMaterial,
    build_bootstrap_profile_artifacts,
    build_bootstrap_trust_anchor,
    serialize_bootstrap_profile_artifacts,
    verify_bootstrap_profile,
    verify_bootstrap_release,
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
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    AuthenticatedSemanticSourceInterval,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
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
    JsonlMemoryPlaneStore,
    _PersistedBatch,
)
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
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
from memorii.core.semantic_ingestion.contracts import (
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
from memorii.core.semantic_ingestion.egress import (
    ProviderEgressDecision,
)
from memorii.core.semantic_ingestion.event_replay import (
    decode_semantic_memory_event_batch,
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


def _bootstrap_cases() -> tuple[BootstrapGrammarCorpusCase, ...]:
    values = (
        (
            "01-supported-atlas",
            "en",
            "authenticated_host_declaration",
            "trusted",
            "agrees",
            b"Atlas owner is Bob.",
            "supported_form",
            None,
        ),
        (
            "02-supported-receipt",
            "en",
            "authenticated_host_declaration",
            "trusted",
            "agrees",
            b"Receipt is confirmed.",
            "supported_form",
            None,
        ),
        (
            "03-unsupported-mixed",
            "en",
            "authenticated_host_declaration",
            "trusted",
            "agrees",
            b"Atlas is Bob. trailing",
            "unsupported_form",
            "mixed_residue",
        ),
        (
            "04-unsupported-grammar",
            "en",
            "authenticated_host_declaration",
            "trusted",
            "agrees",
            b"unstructured",
            "unsupported_form",
            "unsupported_grammar",
        ),
        (
            "05-abstain-extractor",
            "en",
            "authenticated_host_declaration",
            "trusted",
            "agrees",
            b"",
            "abstain_form",
            "extractor_abstained",
        ),
        (
            "06-abstain-mismatch",
            "en",
            "mismatched",
            "mismatched",
            "disagrees",
            b"mismatch",
            "abstain_form",
            "language_mismatch",
        ),
        (
            "07-abstain-missing",
            None,
            "missing",
            "missing",
            "missing",
            b"missing",
            "abstain_form",
            "missing_language_declaration",
        ),
        (
            "08-abstain-non-english",
            "fr",
            "authenticated_host_declaration",
            "trusted",
            "agrees",
            b"bonjour",
            "abstain_form",
            "non_english_language",
        ),
        (
            "09-abstain-untrusted",
            None,
            "untrusted",
            "untrusted",
            "missing",
            b"untrusted",
            "abstain_form",
            "untrusted_language",
        ),
    )
    return tuple(
        BootstrapGrammarCorpusCase.model_validate(
            {
                "case_id": case_id,
                "declared_language": language,
                "language_evidence_kind": evidence_kind,
                "language_evidence_trust": trust,
                "governance_agreement": agreement,
                "normalized_segment_bytes": source,
                "disposition": disposition,
                "expected_reason": reason,
            }
        )
        for case_id, language, evidence_kind, trust, agreement, source, disposition, reason in values
    )


class _TrustRoot:
    def __init__(self, digest: str) -> None:
        self.digest = digest

    def verify_active_release(self, metadata: BootstrapProfileReleaseMetadata) -> bool:
        return metadata.bootstrap_profile_trust_anchor_digest == self.digest


class _TestHostBootstrapCapability:
    def __init__(self, *, resolver=None, trust_domain="production") -> None:
        artifacts = build_bootstrap_profile_artifacts(_bootstrap_cases())
        self._anchor = build_bootstrap_trust_anchor(artifacts)
        self._metadata = BootstrapProfileReleaseMetadata(
            coordinate=BOOTSTRAP_COORDINATE,
            bootstrap_profile_trust_anchor_digest=self._anchor.trust_anchor_digest,
            signed_release_digest="1" * 64,
        )
        self._payloads = serialize_bootstrap_profile_artifacts(artifacts)
        self._resolver = resolver or _Resolver()
        self._root = _TrustRoot(self._anchor.trust_anchor_digest)
        self._trust_domain = trust_domain

    def load_verified_bootstrap_material(self):
        if not verify_bootstrap_release(provider=self._root, metadata=self._metadata, anchor=self._anchor):
            return None
        return HostVerifiedBootstrapMaterial(
            release_metadata=self._metadata,
            trust_anchor=self._anchor,
            artifact_payloads=self._payloads,
            release_evidence=build_test_host_verified_bootstrap_release_evidence(
                metadata=self._metadata,
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


def _bundle(predicate_id: str = "works_for") -> SemanticArbitrationPolicyBundle:
    effective = TimeInterval(start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC))
    trust = TrustPolicySnapshot.create(
        policy_revision="trust-r1",
        system_effective_interval=effective,
        rules=(
            PredicateTrustRule(
                predicate_id=predicate_id,
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 10},
            ),
        ),
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="temporal-r1",
        system_effective_interval=effective,
        rules=(
            PredicateTemporalRule(
                predicate_id=predicate_id,
                valid_time_requirement="required",
                allow_open_end=True,
            ),
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


class _SwitchingIngressResolver:
    """Exercise accepted and rejected ingress through one service composition."""

    def __init__(self) -> None:
        self.reject = False
        self._accepted = _Resolver()

    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime):
        if self.reject:
            raise AuthenticatedIngressResolutionError("rejected")
        return self._accepted.resolve(host_ingress, server_time)


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
    def __init__(self, predicate_id: str = "works_for", *, outage: bool = False) -> None:
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
) -> tuple[SourceNormalizationHostBundleBuilder, dict[str, int]]:
    """Build a complete V3-only host bundle for the ordinary provider root."""
    proposal_value = proposal or ProviderSemanticProposal(abstained=True)
    quotes = _UnusedNormalizationQuoteAuthority() if proposal is None else _SingleTextQuoteAuthority()
    calls = {"proposal": 0, "stanza": 0, "spacy": 0, "predicate": 0, "temporal": 0}

    authority_provider = DynamicSourceNormalizationAuthorityProvider(
        proposal_factory=lambda _source, _request: proposal_value,
        retry_policy_fingerprint="a" * 64,
    )

    def proposal(_request):
        calls["proposal"] += 1
        value = proposal_value
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
        server_time=lambda: TEST_NOW, monotonic_tick=lambda: 1,
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
    *, verifier=None, normalization_builder=None, resolver=None, scenario_test=False,
):
    material = _TestHostBootstrapCapability(
        resolver=resolver or _Resolver(),
        trust_domain="scenario_test" if scenario_test else "production",
    ).load_verified_bootstrap_material()
    assert material is not None
    return BuiltInLocalHostSemanticIngestionCapability(
        bootstrap_material_presentation=present_authenticated_host_bootstrap_material(material),
        authorization_bytes=b"signed-test-authorization",
        authorization_verifier=_AuthorizationVerifier(),
        policy_provider=_PolicyProvider("owner_is"),
        current_bootstrap_release_verifier=(
            _CurrentBootstrapReleaseVerifier() if verifier is None else verifier
        ),
        source_normalization_host_bundle_builder=normalization_builder,
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
    # A lost acknowledgement retries the same public operation.  Found must
    # reload the V3 closure before authority or any of the five learned lanes.
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
    original = scenario.bootstrap_material_presentation.material.release_evidence
    rebuilt_evidence = build_test_host_verified_bootstrap_release_evidence(
        metadata=scenario.bootstrap_material_presentation.material.release_metadata,
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
    assert verify_bootstrap_profile(
        scenario.bootstrap_material_presentation.material
    ).release_evidence == rebuilt_evidence

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
        capability._root = _TrustRoot("0" * 64)
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


def _bob_owner_proposal():
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
                predicate_id="owner_is",
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
