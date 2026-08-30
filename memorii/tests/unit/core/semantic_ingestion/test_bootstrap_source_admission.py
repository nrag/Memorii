from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import patch

import pytest
from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
    SemanticIngestionOutcomeLookupRequest,
    source_admission_source_digest,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapGrammarCorpusCase,
    BootstrapLocalProfileManifest,
    BootstrapProfileArtifacts,
    BootstrapProfileReleaseMetadata,
    BootstrapProfileVerificationError,
    ComponentSymbolFingerprint,
    HostVerifiedBootstrapMaterial,
    ProfileSelectedPipelinePending,
    _component_fingerprint_digest,
    _component_root,
    build_bootstrap_profile_artifacts,
    build_bootstrap_trust_anchor,
    disposition_outcome,
    serialize_bootstrap_profile_artifacts,
    verify_bootstrap_profile,
    verify_bootstrap_release,
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
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    derive_composite_child_delivery_id,
    encode_typed_value,
    normalize_delivery_id,
)
from memorii.core.memory_evolution.source_admission import (
    ProviderEventNormalizer,
    derive_bootstrap_authenticated_language_evidence,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    MemoryPlaneRevisionConflictError,
)
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderEvent, ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from memorii.integrations.hermes_provider import HermesMemoryProvider
from tests.fixtures.semantic_ingestion.host_bootstrap_authority import (
    DeterministicTestHostBootstrapMaterialVerifier,
    build_test_host_verified_bootstrap_release_evidence,
    present_authenticated_host_bootstrap_material,
)


def _binding() -> DeliveryPrincipalBinding:
    return DeliveryPrincipalBinding.create(
        principal_subject_id="principal:alice", tenant_partition_id="tenant:one", provider_identity="provider:test"
    )


def _ingress(*scopes: str, required_scopes: tuple[str, ...] | None = None) -> AuthenticatedIngressContext:
    binding = _binding()
    required = scopes if required_scopes is None else required_scopes
    return AuthenticatedIngressContext(
        delivery_principal_binding=binding,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id=binding.tenant_partition_id, scopes=set(required)
        ),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id=binding.tenant_partition_id, scopes=set(scopes)
        ),
        language_declaration="en",
        language_evidence_kind="authenticated_host_declaration",
        language_evidence_trust="trusted",
        language_governance_agreement="agrees",
        # The governed semantic boundary requires the host-authenticated
        # egress and source-authority metadata; without them the resolved
        # ingress is not a semantic-ingress ingress at all.
        semantic_egress_governance=AuthenticatedSemanticEgressGovernance(
            classification="internal",
            provider="provider:test",
            model="fixture",
            region="local",
            retention_mode="none",
            training_use=False,
        ),
        semantic_source_authority=AuthenticatedSemanticSourceAuthority(
            authority_class="official",
            authenticated_provenance_class="host",
            governing_principal_id="user:user:alice",
            policy_revision="trust-r1",
            provenance_digest="ab" * 32,
        ),
        semantic_source_interval=AuthenticatedSemanticSourceInterval(
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 2, 1, tzinfo=UTC),
            authority_basis="server_source_metadata",
            provenance_digest="cd" * 32,
            policy_revision="trust-r1",
        ),
    )


def test_provider_event_normalizer_rejects_empty_semantic_source_text() -> None:
    with pytest.raises(ValueError, match="String should have at least 1 character"):
        ProviderEventNormalizer(_ingress("semantic:read")).normalize(
            ProviderEvent(
                event_id="empty-semantic-source",
                operation=ProviderOperation.CHAT_ASSISTANT_TURN,
                content="",
            )
        )


def _source() -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id="tx:exact-id",
        domain=MemoryDomain.TRANSCRIPT,
        text="Atlas owner is Bob.",
        content={"text": "Atlas owner is Bob."},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_source",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        task_id="task:one",
        user_id="user:alice",
        is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


class _TestHostBootstrapCapability:
    def __init__(self, *, enabled: bool = True, resolver=None) -> None:
        self._artifacts = build_bootstrap_profile_artifacts(_complete_corpus_cases())
        self._trust_anchor = build_bootstrap_trust_anchor(self._artifacts)
        self._trust_root_provider = DeterministicTestTrustRootProvider(self._trust_anchor.trust_anchor_digest)
        self._release_metadata = BootstrapProfileReleaseMetadata(
            coordinate=BOOTSTRAP_COORDINATE,
            bootstrap_profile_trust_anchor_digest=self._trust_anchor.trust_anchor_digest,
            signed_release_digest="1" * 64,
        )
        self._resolver = resolver or _TrustedResolver()
        self._enabled = enabled

    @property
    def trust_root_provider(self):
        return self._trust_root_provider

    @property
    def release_metadata(self):
        return self._release_metadata

    @property
    def trust_anchor(self):
        return self._trust_anchor

    @property
    def artifact_payloads(self):
        from memorii.core.memory_evolution.bootstrap_profile import serialize_bootstrap_profile_artifacts

        return serialize_bootstrap_profile_artifacts(self._artifacts)

    @property
    def profile_enabled(self):
        return self._enabled

    @property
    def authenticated_ingress_resolver(self):
        return self._resolver

    def load_verified_bootstrap_material(self):
        if not verify_bootstrap_release(
            provider=self.trust_root_provider,
            metadata=self.release_metadata,
            anchor=self.trust_anchor,
        ):
            return None
        return HostVerifiedBootstrapMaterial(
            release_metadata=self.release_metadata,
            trust_anchor=self.trust_anchor,
            artifact_payloads=self.artifact_payloads,
            release_evidence=build_test_host_verified_bootstrap_release_evidence(
                metadata=self.release_metadata,
                external_root_digest="2" * 64,
                active_lifecycle_snapshot_digest="3" * 64,
                verified_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            authenticated_ingress_resolver=self.authenticated_ingress_resolver,
            profile_enabled=self.profile_enabled,
        )

    def load_bootstrap_material_presentation(self):
        material = self.load_verified_bootstrap_material()
        return (
            present_authenticated_host_bootstrap_material(material)
            if material is not None
            else None
        )


class DeterministicTestTrustRootProvider:
    def __init__(self, accepted_anchor_digest: str) -> None:
        self._accepted_anchor_digest = accepted_anchor_digest

    def verify_active_release(self, metadata: BootstrapProfileReleaseMetadata) -> bool:
        return (
            metadata.coordinate == BOOTSTRAP_COORDINATE
            and metadata.bootstrap_profile_trust_anchor_digest == self._accepted_anchor_digest
        )


def _complete_corpus_cases() -> tuple[BootstrapGrammarCorpusCase, ...]:
    def case(
        case_id: str,
        content: bytes,
        disposition: str,
        reason: str | None,
        *,
        language: str | None = "en",
        evidence_kind: str = "authenticated_host_declaration",
        evidence_trust: str = "trusted",
        agreement: str = "agrees",
    ) -> BootstrapGrammarCorpusCase:
        return BootstrapGrammarCorpusCase.model_validate(
            {
                "case_id": case_id,
                "declared_language": language,
                "language_evidence_kind": evidence_kind,
                "language_evidence_trust": evidence_trust,
                "governance_agreement": agreement,
                "normalized_segment_bytes": content,
                "disposition": disposition,
                "expected_reason": reason,
            }
        )

    return (
        case("01-supported-atlas", b"Atlas owner is Bob.", "supported_form", None),
        case("02-supported-receipt", b"Receipt is confirmed.", "supported_form", None),
        case("03-unsupported-mixed", b"Atlas is Bob. trailing", "unsupported_form", "mixed_residue"),
        case("04-unsupported-grammar", b"unstructured", "unsupported_form", "unsupported_grammar"),
        case("05-abstain-extractor", b"", "abstain_form", "extractor_abstained"),
        case(
            "06-abstain-mismatch", b"mismatch", "abstain_form", "language_mismatch",
            evidence_kind="mismatched", evidence_trust="mismatched", agreement="disagrees",
        ),
        case(
            "07-abstain-missing", b"missing", "abstain_form", "missing_language_declaration",
            language=None, evidence_kind="missing", evidence_trust="missing", agreement="missing",
        ),
        case("08-abstain-non-english", b"bonjour", "abstain_form", "non_english_language", language="fr"),
        case(
            "09-abstain-untrusted", b"untrusted", "abstain_form", "untrusted_language",
            language=None, evidence_kind="untrusted", evidence_trust="untrusted", agreement="missing",
        ),
    )


def _runtime_mutated_bootstrap_material(
    mutation: dict[str, object],
) -> HostVerifiedBootstrapMaterial:
    artifacts = build_bootstrap_profile_artifacts(_complete_corpus_cases())
    original = artifacts.profile_manifest.component_fingerprints[0]
    fingerprint_fields = original.model_dump(mode="python", exclude={"fingerprint_digest"})
    fingerprint_fields.update(mutation)
    fingerprint = ComponentSymbolFingerprint(
        **fingerprint_fields,
        fingerprint_digest=_component_fingerprint_digest(
            ComponentSymbolFingerprint.model_construct(**fingerprint_fields, fingerprint_digest="0" * 64)
        ),
    )
    fingerprints = (fingerprint, *artifacts.profile_manifest.component_fingerprints[1:])
    profile_fields = artifacts.profile_manifest.model_dump(mode="python", exclude={"profile_digest"})
    profile_fields["component_fingerprints"] = tuple(item.model_dump(mode="python") for item in fingerprints)
    profile_fields["component_root_digest"] = _component_root(BOOTSTRAP_COORDINATE, fingerprints)
    profile = BootstrapLocalProfileManifest(
        **profile_fields,
        profile_digest=sha256(encode_typed_value(profile_fields)).hexdigest(),
    )
    mutated = BootstrapProfileArtifacts(
        profile_manifest=profile,
        grammar_capability_manifest=artifacts.grammar_capability_manifest,
        grammar_corpus=artifacts.grammar_corpus,
    )
    anchor = build_bootstrap_trust_anchor(mutated)
    return HostVerifiedBootstrapMaterial(
        release_metadata=BootstrapProfileReleaseMetadata(
            coordinate=BOOTSTRAP_COORDINATE,
            bootstrap_profile_trust_anchor_digest=anchor.trust_anchor_digest,
            signed_release_digest="1" * 64,
        ),
        trust_anchor=anchor,
        artifact_payloads=serialize_bootstrap_profile_artifacts(mutated),
        release_evidence=build_test_host_verified_bootstrap_release_evidence(
            metadata=BootstrapProfileReleaseMetadata(
                coordinate=BOOTSTRAP_COORDINATE,
                bootstrap_profile_trust_anchor_digest=anchor.trust_anchor_digest,
                signed_release_digest="1" * 64,
            ),
            external_root_digest="2" * 64,
            active_lifecycle_snapshot_digest="3" * 64,
            verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        authenticated_ingress_resolver=_TrustedResolver(),
        profile_enabled=True,
    )


def test_delivery_id_is_exact_and_rejects_unsafe_forms() -> None:
    value = "  delivery:naive-cafe  "
    assert normalize_delivery_id(value) == value
    assert DeliveryIdentity.create(_binding(), value).normalized_delivery_id.strict_utf8_bytes == value.encode("utf-8")
    with pytest.raises(ValueError, match="nonblank"):
        normalize_delivery_id(" \t\n")
    with pytest.raises(ValueError, match="Unicode scalar"):
        normalize_delivery_id("bad\ud800")
    assert derive_composite_child_delivery_id("parent:one", "user") != derive_composite_child_delivery_id(
        "parent", "one:user"
    )


def test_component_fingerprint_requires_paired_distribution_or_repository_identity() -> None:
    with pytest.raises(ValueError, match="distribution name and version"):
        ComponentSymbolFingerprint(
            module_path="example.module",
            qualified_symbol="Example",
            distribution_name="example",
            distribution_version=None,
            repository_blob_identity=None,
            source_or_package_content_digest="0" * 64,
            fingerprint_digest="0" * 64,
        )


def test_runtime_bootstrap_component_identity_mutations_fail_closed() -> None:
    original = build_bootstrap_profile_artifacts(_complete_corpus_cases()).profile_manifest.component_fingerprints[0]
    if original.distribution_name is not None:
        missing_version = original.model_dump(mode="python")
        missing_version["distribution_version"] = None
        with pytest.raises(ValueError, match="distribution name and version"):
            ComponentSymbolFingerprint.model_validate(missing_version)
        mutation = {"distribution_version": "9999.0.0"}
    else:
        mutation = {"source_or_package_content_digest": "0" * 64}
    with pytest.raises(BootstrapProfileVerificationError):
        verify_bootstrap_profile(_runtime_mutated_bootstrap_material(mutation))
    with pytest.raises(ValueError, match="inventory"):
        _runtime_mutated_bootstrap_material({"qualified_symbol": "MissingBootstrapSymbol"})
    with pytest.raises(ValueError, match="repository blob identity"):
        ComponentSymbolFingerprint(
            module_path="example.module",
            qualified_symbol="Example",
            distribution_name=None,
            distribution_version=None,
            repository_blob_identity=None,
            source_or_package_content_digest="0" * 64,
            fingerprint_digest="0" * 64,
        )


def test_bootstrap_release_evidence_rejects_before_artifact_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = _TestHostBootstrapCapability().load_verified_bootstrap_material()
    assert material is not None
    invalid = HostVerifiedBootstrapMaterial(
        release_metadata=material.release_metadata,
        trust_anchor=material.trust_anchor,
        artifact_payloads=material.artifact_payloads,
        release_evidence=material.release_evidence.model_copy(
            update={"signed_release_digest": "f" * 64}
        ),
        authenticated_ingress_resolver=material.authenticated_ingress_resolver,
        profile_enabled=material.profile_enabled,
    )

    def decoded_too_early(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("artifact decoding preceded release-evidence validation")

    monkeypatch.setattr(
        "memorii.core.memory_evolution.bootstrap_profile.decode_artifact",
        decoded_too_early,
    )
    with pytest.raises(BootstrapProfileVerificationError) as exc_info:
        verify_bootstrap_profile(invalid)
    assert exc_info.value.reason.value == "invalid_manifest"


def test_admission_rejects_partial_scope_before_any_retention() -> None:
    memory_plane = MemoryPlaneService()
    admission = GovernedSourceAdmissionService(memory_plane)
    identity = DeliveryIdentity.create(_binding(), "delivery-1")
    with pytest.raises(ValueError, match="scope coverage"):
        admission.admit(
            source=_source(),
            delivery_identity=identity,
            ingress=_ingress(
                "task:task:one", required_scopes=("task:task:one", "user:user:alice")
            ),
            operation_id="operation-1",
        )
    assert memory_plane.list_records() == []


def test_admission_uses_host_required_scopes_not_public_source_metadata() -> None:
    memory_plane = MemoryPlaneService()
    admission = GovernedSourceAdmissionService(memory_plane)
    identity = DeliveryIdentity.create(_binding(), "delivery:host-scopes")
    ingress = _ingress("host:classification", "host:task")
    accepted = admission.admit(
        source=_source().model_copy(update={"session_id": "attacker-session", "task_id": "attacker-task"}),
        delivery_identity=identity,
        ingress=ingress,
        operation_id="operation:host-scopes",
    )
    assert accepted.required_outcome_scopes == ingress.required_outcome_scopes
    index = memory_plane.get_record(f"semantic_ingestion:admission:{identity.delivery_key_digest}")
    assert index is not None
    assert index.content["required_scopes"] == ["host:classification", "host:task"]


def test_bootstrap_language_evidence_is_derived_and_retained_with_the_observation() -> None:
    source = _source()
    ingress = _ingress("task:task:one", "user:user:alice")
    evidence = derive_bootstrap_authenticated_language_evidence(
        ingress=ingress,
        source_id=source.memory_id,
        source_digest=source_admission_source_digest(source),
        original_text=source.text,
        segment_governance_set_digest="1" * 64,
        governance_carrier_artifact_digest="2" * 64,
        segment_governance_carriers_digest="3" * 64,
        message_admission_carriers_digest="4" * 64,
    )
    accepted = GovernedSourceAdmissionService(MemoryPlaneService()).admit(
        source=source,
        delivery_identity=DeliveryIdentity.create(_binding(), "delivery:bootstrap-evidence"),
        ingress=ingress,
        operation_id="operation:bootstrap-evidence",
        bootstrap_language_evidence=evidence,
    )
    assert accepted.observation.bootstrap_language_evidence == evidence
    mutated = evidence.model_dump(mode="python")
    mutated["language_declaration"] = "fr"
    with pytest.raises(ValueError, match="language evidence digest"):
        type(evidence).model_validate(mutated)


def test_host_required_scopes_are_retained_for_evidence_only_admission() -> None:
    memory_plane = MemoryPlaneService()
    admission = GovernedSourceAdmissionService(memory_plane)
    identity = DeliveryIdentity.create(_binding(), "delivery:evidence-scopes")
    accepted = admission.admit(
        source=_source(),
        delivery_identity=identity,
        ingress=_ingress("host:session"),
        operation_id="operation:evidence-scopes",
        evidence_only=True,
    )
    assert accepted.required_outcome_scopes.scopes == ("host:session",)


def test_admission_identity_is_stable_and_lookup_is_non_disclosing() -> None:
    memory_plane = MemoryPlaneService()
    admission = GovernedSourceAdmissionService(memory_plane)
    identity = DeliveryIdentity.create(_binding(), "delivery-1")
    accepted = admission.admit(
        source=_source(),
        delivery_identity=identity,
        ingress=_ingress("task:task:one", "user:user:alice"),
        operation_id="operation-1",
    )
    recovered = admission.admit(
        source=_source(),
        delivery_identity=identity,
        ingress=_ingress(
            "task:task:one",
            "user:user:alice",
            "session:rotated",
            required_scopes=("task:task:one", "user:user:alice"),
        ),
        operation_id="operation-1",
    )
    assert (
        accepted.delivery_identity.delivery_key_digest
        == DeliveryIdentity.create(_binding(), "delivery-1").delivery_key_digest
    )
    assert recovered == accepted
    response = admission.lookup(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=identity,
        ),
        authenticated_ingress=_ingress("task:task:one", "user:user:alice", "session:rotated"),
    )
    denied = admission.lookup(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=identity,
        ),
        authenticated_ingress=_ingress("task:task:one"),
    )
    assert response.available is True
    assert isinstance(response.outcome, ProfileSelectedPipelinePending)
    assert denied.available is False and denied.outcome is None
    assert accepted.admission_index_digest == recovered.admission_index_digest


def test_cross_principal_same_source_cannot_overwrite_retained_evidence() -> None:
    memory_plane = MemoryPlaneService()
    admission = GovernedSourceAdmissionService(memory_plane)
    first_binding = _binding()
    first_identity = DeliveryIdentity.create(first_binding, "delivery-1")
    admission.admit(
        source=_source(), delivery_identity=first_identity,
        ingress=_ingress("task:task:one", "user:user:alice"), operation_id="operation-1",
    )
    second_binding = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:bob", tenant_partition_id="tenant:one", provider_identity="provider:test"
    )
    second_identity = DeliveryIdentity.create(second_binding, "delivery-1")
    second_ingress = AuthenticatedIngressContext(
        delivery_principal_binding=second_binding,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:one", scopes={"task:task:one", "user:user:alice"}
        ),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:one", scopes={"task:task:one", "user:user:alice"}
        ),
    )
    with pytest.raises(MemoryPlaneRevisionConflictError):
        admission.admit(source=_source(), delivery_identity=second_identity, ingress=second_ingress, operation_id="operation-1")
    assert memory_plane.get_record("tx:exact-id") == _source()


class _TrustedResolver:
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        assert host_ingress.provider_identity == "provider:test"
        return _ingress("task:task:one", "user:user:alice")


class _FrenchResolver:
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        base = _ingress("task:task:one")
        return base.model_copy(
            update={
                "language_declaration": "fr",
                "language_evidence_kind": "authenticated_host_declaration",
                "language_evidence_trust": "trusted",
                "language_governance_agreement": "agrees",
            }
        )


class _CorpusResolver:
    def __init__(self, case: BootstrapGrammarCorpusCase) -> None:
        self._case = case

    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        base = _ingress("task:task:one")
        return base.model_copy(
            update={
                "language_declaration": self._case.declared_language,
                "language_evidence_kind": self._case.language_evidence_kind,
                "language_evidence_trust": self._case.language_evidence_trust,
                "language_governance_agreement": self._case.governance_agreement,
            }
        )


class _PartialScopeResolver:
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        return _ingress("task:task:one")


class _HostGovernanceScopeResolver:
    def __init__(self, *current_scopes: str) -> None:
        self._current_scopes = current_scopes

    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        return _ingress(
            *self._current_scopes,
            required_scopes=("host:classification", "host:retention"),
        )


class _DeniedResolver:
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        raise AuthenticatedIngressResolutionError("expired host ingress")


class _CapabilityLoader:
    def __init__(self, capability: object) -> None:
        self._capability = capability

    def load(self):
        return self._capability


class _InstalledCapabilityEntryPoint:
    def __init__(self, capability: object) -> None:
        self._capability = capability

    def load(self):
        return _CapabilityLoader(self._capability)


class _UnavailableHostBoundary:
    def load_bootstrap_material_presentation(self):
        return None


def _service_with_capability(
    capability: _TestHostBootstrapCapability,
    *,
    memory_plane: MemoryPlaneService | None = None,
) -> ProviderMemoryService:
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        return ProviderMemoryService(
            memory_plane=memory_plane,
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )


def test_default_provider_root_is_profile_unapproved_evidence_only() -> None:
    memory_plane = MemoryPlaneService()
    service = ProviderMemoryService(memory_plane=memory_plane)
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=" exact-delivery-id ",
        task_id="task:one",
    )
    assert result.transcript_ids == []
    assert result.candidate_ids == []
    assert result.blocked_reasons["semantic_ingestion"] == "ingress_unavailable"
    assert tuple(memory_plane.list_records()) == ()
    with pytest.raises(ValueError, match="reserved composite"):
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN, content="ignored", operation_id="composite:v1:" + "0" * 64
        )


def test_trusted_provider_path_admits_evidence_before_profile_gate() -> None:
    memory_plane = MemoryPlaneService()
    service = _service_with_capability(_TestHostBootstrapCapability(), memory_plane=memory_plane)
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="exact-delivery-id",
        task_id="task:one",
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="provider:test", principal_handle=object(), session_handle=object(), received_at=datetime.now(UTC)
        ),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(memory_plane.list_records()) == 35


def test_provider_sync_event_uses_host_required_scopes_not_public_event_metadata() -> None:
    ingress = AuthenticatedHostIngress(
        provider_identity="provider:test", principal_handle=object(), session_handle=object(), received_at=datetime.now(UTC)
    )
    insufficient_plane = MemoryPlaneService()
    insufficient = _service_with_capability(
        _TestHostBootstrapCapability(resolver=_HostGovernanceScopeResolver("host:classification")),
        memory_plane=insufficient_plane,
    )
    before = insufficient_plane.list_records()
    with pytest.raises(ValueError, match="scope coverage"):
        insufficient.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id="host-governance-denied",
            task_id="caller-task",
            user_id="caller-user",
            authenticated_host_ingress=ingress,
        )
    assert insufficient_plane.list_records() == before

    plane = MemoryPlaneService()
    service = _service_with_capability(
        _TestHostBootstrapCapability(
            resolver=_HostGovernanceScopeResolver("host:classification", "host:retention")
        ),
        memory_plane=plane,
    )
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="host-governance-accepted",
        task_id="caller-task",
        user_id="caller-user",
        authenticated_host_ingress=ingress,
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    index = next(record for record in plane.list_records() if record.source_kind == "semantic_ingestion_admission_index")
    assert index.content["required_scopes"] == ["host:classification", "host:retention"]


def test_provider_reprepares_atomic_admission_when_writer_cutover_wins_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory_plane = MemoryPlaneService()
    service = _service_with_capability(_TestHostBootstrapCapability(), memory_plane=memory_plane)
    original_admit = service._semantic_atomic_store.admit_source
    raced = [False]

    def cutover_then_admit(*, prepared, writer_binding):
        if not raced[0]:
            raced[0] = True
            plan = build_migration_plan(
                migration_plan_id="provider-race", source_writer_epoch=1,
                legacy_snapshot_token=sha256(encode_typed_value(())).hexdigest(), entries=(),
            )
            values = {
                "migration_plan_id": plan.migration_plan_id, "plan_digest": plan.plan_digest,
                "completed_entry_digests": (), "target_generation": 1,
            }
            checkpoint = DeliveryCoordinateMigrationCheckpoint(
                **values, checkpoint_digest=sha256(encode_typed_value(values)).hexdigest()
            )
            certificate = certify_migration(plan, checkpoint, independent_verifier_fingerprint="verifier")
            service._semantic_writer_admission.transition(
                expected=writer_binding, admission_id="provider:2", runtime_mode="evidence_only",
                writer_implementation_fingerprint="provider:2", graph_schema_fingerprint="schema:2",
                migration_activation=activate_migration(plan, certificate), migration_plan=plan,
                migration_checkpoint=checkpoint, migration_certificate=certificate, target_records=(),
            )
        return original_admit(prepared=prepared, writer_binding=service._provider_ingestion._current_writer_binding())

    monkeypatch.setattr(service._semantic_atomic_store, "admit_source", cutover_then_admit)
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="cutover-race", task_id="task:one",
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="provider:test", principal_handle=object(), session_handle=object(),
            received_at=datetime.now(UTC),
        ),
    )
    assert raced[0] and result.blocked_reasons["semantic_ingestion"] == "source_only"
    index = next(record for record in memory_plane.list_records() if record.source_kind == "semantic_ingestion_admission_index")
    assert index.content["admitted_writer_epoch"] == 2


def test_hermes_trusted_ingress_uses_internal_composite_coordinates() -> None:
    memory_plane = MemoryPlaneService()
    provider = HermesMemoryProvider(
        _service_with_capability(_TestHostBootstrapCapability(), memory_plane=memory_plane)
    )
    result = provider.sync_turn(
        "Atlas owner is Bob.", "Receipt is confirmed.", operation_id="turn-1", task_id="task:one",
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="provider:test", principal_handle=object(), session_handle=object(), received_at=datetime.now(UTC)
        ),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(memory_plane.list_records()) == 66


def test_authenticated_metadata_poor_snapshot_is_governed_evidence_only() -> None:
    memory_plane = MemoryPlaneService()
    service = _service_with_capability(_TestHostBootstrapCapability(), memory_plane=memory_plane)
    result = service.sync_event(
        operation=ProviderOperation.SESSION_END,
        content="user: Atlas owner is Bob.",
        operation_id="session-end-1",
        task_id="task:one",
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="provider:test",
            principal_handle=object(),
            session_handle=object(),
            received_at=datetime.now(UTC),
        ),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    records = memory_plane.list_records()
    assert {record.source_kind for record in records} == {
        "semantic_ingestion_metadata_poor_snapshot",
        "semantic_ingestion_admission_index",
        "semantic_ingestion_profile_selection",
        "semantic_ingestion_profile_verification",
        "semantic_ingestion_profile_outcome",
        "semantic_ingestion_writer_admission",
        "semantic_ingestion_preplanning_control",
        "semantic_ingestion_preplanning_artifact",
    }
    snapshot = next(
        record for record in records if record.source_kind == "semantic_ingestion_metadata_poor_snapshot"
    )
    assert snapshot.content["snapshot_utf8_bytes"] == b"user: Atlas owner is Bob."
    assert snapshot.session_id is None and snapshot.task_id is None and snapshot.user_id is None


def test_hermes_metadata_poor_payload_preserves_structural_shape() -> None:
    memory_plane = MemoryPlaneService()
    provider = HermesMemoryProvider(
        _service_with_capability(_TestHostBootstrapCapability(), memory_plane=memory_plane)
    )
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    provider.on_session_end(
        ["user: a"], operation_id="shape-string", authenticated_host_ingress=host_ingress
    )
    provider.on_pre_compress(
        [{"role": "user", "content": "a", "metadata": None}],
        operation_id="shape-map",
        authenticated_host_ingress=host_ingress,
    )
    snapshots = memory_plane.list_records(source_kind="semantic_ingestion_metadata_poor_snapshot")
    payloads = {record.content["snapshot_utf8_bytes"] for record in snapshots}
    assert payloads == {
        b'["user: a"]',
        b'[{"content":"a","metadata":null,"role":"user"}]',
    }
    assert all(record.language == "und" for record in snapshots)


def test_disabled_profile_is_exact_only_through_protected_lookup() -> None:
    memory_plane = MemoryPlaneService()
    capability = _TestHostBootstrapCapability(enabled=False)
    service = _service_with_capability(capability, memory_plane=memory_plane)
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="disabled-delivery",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    response = service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), "disabled-delivery")
        ),
        authenticated_host_ingress=host_ingress,
    )
    assert response.available is True
    assert response.outcome is not None and response.outcome.kind == "disabled"


def test_factory_loads_installed_host_capability_and_ignores_public_language_label() -> None:
    capability = _TestHostBootstrapCapability()
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = build_provider_memory_service_from_env(
            memory_plane=MemoryPlaneService(),
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        language="fr",
        operation_id="factory-delivery",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    outcome = service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), "factory-delivery")
        ),
        authenticated_host_ingress=host_ingress,
    ).outcome
    assert outcome is not None and outcome.kind == "abstained"


def test_authenticated_non_english_declaration_abstains_even_when_public_label_is_en() -> None:
    capability = _TestHostBootstrapCapability(resolver=_FrenchResolver())
    service = _service_with_capability(capability, memory_plane=MemoryPlaneService())
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        language="en",
        operation_id="french-delivery",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    outcome = service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), "french-delivery")
        ),
        authenticated_host_ingress=host_ingress,
    ).outcome
    assert outcome is not None and outcome.kind == "abstained"
    assert outcome.reason == "non_english_language"


@pytest.mark.parametrize("case", _complete_corpus_cases(), ids=lambda case: case.case_id)
def test_every_bootstrap_corpus_case_has_exact_protected_source_admission_outcome(
    case: BootstrapGrammarCorpusCase,
) -> None:
    capability = _TestHostBootstrapCapability(resolver=_CorpusResolver(case))
    plane = MemoryPlaneService()
    service = _service_with_capability(capability, memory_plane=plane)
    ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    delivery_id = f"corpus-{case.case_id}"
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content=case.normalized_segment_bytes.decode("utf-8"),
        operation_id=delivery_id,
        task_id="task:one",
        authenticated_host_ingress=ingress,
    )
    outcome = service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), delivery_id)
        ),
        authenticated_host_ingress=ingress,
    ).outcome
    expected_kind = {
        "supported_form": "abstained",
        "unsupported_form": "unsupported_input",
        "abstain_form": "abstained",
    }[case.disposition]
    assert outcome is not None and outcome.kind == expected_kind
    if outcome.kind in {"unsupported_input", "abstained"}:
        assert outcome.reason == (
            "extractor_abstained" if case.disposition == "supported_form" else case.expected_reason
        )
        assert outcome.matched_corpus_case_id == (
            None if case.disposition == "supported_form" else case.case_id
        )
        assert outcome.input_normalized_digest == sha256(case.normalized_segment_bytes).hexdigest()
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(plane.list_records()) == (35 if case.disposition == "supported_form" else 10)
    assert result.candidate_ids == []


def test_bootstrap_artifact_payloads_require_canonical_envelope_and_exact_binding() -> None:
    from memorii.core.memory_evolution.bootstrap_profile import (
        BootstrapProfileArtifactPayloads,
        bootstrap_artifact_binding,
        serialize_bootstrap_profile_artifacts,
    )
    from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value, serialize_artifact

    baseline = _TestHostBootstrapCapability()
    valid = serialize_bootstrap_profile_artifacts(baseline._artifacts)
    invalid_payloads = (
        valid.model_copy(
            update={
                "profile_manifest": encode_typed_value(
                    baseline._artifacts.profile_manifest.model_dump(mode="python")
                )
            }
        ),
        valid.model_copy(
            update={
                "profile_manifest": serialize_artifact(
                    baseline._artifacts.profile_manifest.model_dump(mode="python"),
                    bootstrap_artifact_binding(
                        "memorii.semantic_ingestion.bootstrap_grammar_capability_manifest"
                    ),
                )
            }
        ),
        BootstrapProfileArtifactPayloads(
            profile_manifest=valid.profile_manifest[:-1] + bytes([valid.profile_manifest[-1] ^ 1]),
            grammar_capability_manifest=valid.grammar_capability_manifest,
            grammar_corpus=valid.grammar_corpus,
        ),
    )
    class InvalidCapability(_TestHostBootstrapCapability):
        def __init__(self, payloads):
            super().__init__()
            self._invalid_payloads = payloads

        @property
        def artifact_payloads(self):
            return self._invalid_payloads

    for index, payloads in enumerate(invalid_payloads):
        plane = MemoryPlaneService()
        service = _service_with_capability(InvalidCapability(payloads), memory_plane=plane)
        ingress = AuthenticatedHostIngress(
            provider_identity="provider:test",
            principal_handle=object(),
            session_handle=object(),
            received_at=datetime.now(UTC),
        )
        delivery_id = f"invalid-envelope-{index}"
        service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id=delivery_id,
            task_id="task:one",
            authenticated_host_ingress=ingress,
        )
        outcome = service.lookup_semantic_ingestion_outcome(
            SemanticIngestionOutcomeLookupRequest(
                delivery_identity=DeliveryIdentity.create(_binding(), delivery_id)
            ),
            authenticated_host_ingress=ingress,
        ).outcome
        assert outcome is not None and outcome.kind == "unavailable"
        assert outcome.reason == "invalid_manifest"
        assert len(plane.list_records()) == 10


def test_invalid_installed_capability_inventory_fails_closed_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = _TestHostBootstrapCapability()
    monkeypatch.setattr(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        lambda **kwargs: (
            _InstalledCapabilityEntryPoint(capability),
            _InstalledCapabilityEntryPoint(capability),
        ),
    )
    service = ProviderMemoryService(memory_plane=MemoryPlaneService())
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="invalid-installed-inventory",
        task_id="task:one",
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="provider:test",
            principal_handle=object(),
            session_handle=object(),
            received_at=datetime.now(UTC),
        ),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "ingress_unavailable"


def test_altered_component_fails_closed_with_truthful_unavailable_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = _TestHostBootstrapCapability()
    monkeypatch.setattr(
        "memorii.core.memory_evolution.bootstrap_profile.Path.read_bytes",
        lambda path: b"altered-installed-component",
    )
    memory_plane = MemoryPlaneService()
    service = _service_with_capability(capability, memory_plane=memory_plane)
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="altered-component",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    records = {record.source_kind: record for record in memory_plane.list_records()}
    assert records["semantic_ingestion_profile_selection"].content == {"status": "unavailable"}
    assert records["semantic_ingestion_profile_verification"].content == {"status": "unavailable"}
    outcome = service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), "altered-component")
        ),
        authenticated_host_ingress=host_ingress,
    ).outcome
    assert outcome is not None and outcome.kind == "unavailable"
    assert outcome.reason == "altered_component"


def test_unreadable_component_fails_closed_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = _TestHostBootstrapCapability()
    monkeypatch.setattr(
        "memorii.core.memory_evolution.bootstrap_profile.Path.read_bytes",
        lambda path: (_ for _ in ()).throw(OSError("component unavailable")),
    )
    plane = MemoryPlaneService()
    service = _service_with_capability(capability, memory_plane=plane)
    ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="unreadable-component",
        task_id="task:one",
        authenticated_host_ingress=ingress,
    )
    outcome = service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), "unreadable-component")
        ),
        authenticated_host_ingress=ingress,
    ).outcome
    assert outcome is not None and outcome.kind == "unavailable"
    assert outcome.reason == "missing_component"


def test_incomplete_component_inventory_fails_closed_before_classification() -> None:
    capability = _TestHostBootstrapCapability()
    profile = capability._artifacts.profile_manifest
    capability._artifacts = capability._artifacts.model_copy(
        update={
            "profile_manifest": profile.model_copy(
                update={"component_fingerprints": profile.component_fingerprints[1:]}
            )
        }
    )
    memory_plane = MemoryPlaneService()
    service = _service_with_capability(capability, memory_plane=memory_plane)
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="incomplete-components",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    outcome = service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), "incomplete-components")
        ),
        authenticated_host_ingress=host_ingress,
    ).outcome
    assert outcome is not None and outcome.kind == "unavailable"
    assert outcome.reason == "invalid_manifest"


def test_jsonl_reopen_and_lost_ack_retry_preserve_one_bootstrap_generation(tmp_path: Path) -> None:
    capability = _TestHostBootstrapCapability()
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    store_path = tmp_path / "memory-plane"
    first = _service_with_capability(
        capability,
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path)),
    )
    first.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="retry-delivery",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    reopened = _service_with_capability(capability, memory_plane=reopened_plane)
    reopened.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="retry-delivery",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    assert len(reopened_plane.list_records()) == 35
    assert len((store_path / "memory_records.jsonl").read_text(encoding="utf-8").splitlines()) == 6


@pytest.mark.parametrize("persistent", [False, True], ids=["memory", "jsonl"])
def test_concurrent_exact_delivery_is_idempotent(
    persistent: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = (
        JsonlMemoryPlaneStore(tmp_path / "concurrent")
        if persistent
        else InMemoryMemoryPlaneStore()
    )
    plane = MemoryPlaneService(record_store=store)
    service = _service_with_capability(_TestHostBootstrapCapability(), memory_plane=plane)
    ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    original_apply = store.apply_batch
    rendezvous = Barrier(2)
    synchronization_lock = Lock()
    synchronized_calls = 0

    def synchronized_apply(*args, **kwargs):
        nonlocal synchronized_calls
        with synchronization_lock:
            synchronized_calls += 1
            synchronize = synchronized_calls <= 2
        if synchronize:
            rendezvous.wait(timeout=5)
        return original_apply(*args, **kwargs)

    monkeypatch.setattr(store, "apply_batch", synchronized_apply)

    def deliver():
        return service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id="concurrent-exact-delivery",
            task_id="task:one",
            authenticated_host_ingress=ingress,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: deliver(), range(2)))
    assert all(result.blocked_reasons["semantic_ingestion"] == "source_only" for result in results)
    assert len({tuple(result.transcript_ids) for result in results}) == 1
    assert len(plane.list_records()) == 35


def test_installed_capability_loader_works_through_hermes_and_filesystem_roots(tmp_path: Path) -> None:
    capability = _TestHostBootstrapCapability()
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        hermes = HermesMemoryProvider()
    hermes_result = hermes.sync_turn(
        "Atlas owner is Bob.",
        "Receipt is confirmed.",
        operation_id="hermes-loader",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    assert hermes_result.blocked_reasons["semantic_ingestion"] == "source_only"

    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        filesystem = build_filesystem_provider(
            tmp_path / "filesystem-root",
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )
    filesystem_result = filesystem.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="filesystem-loader",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    assert filesystem_result.blocked_reasons["semantic_ingestion"] == "source_only"


def test_normal_roots_discover_installed_host_capability_without_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capability = _TestHostBootstrapCapability()
    monkeypatch.setattr(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        lambda **kwargs: (_InstalledCapabilityEntryPoint(capability),),
    )
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    direct = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    direct_result = direct.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="installed-direct",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    assert direct_result.transcript_ids[0].startswith("semantic_ingestion:source:")
    assert direct_result.blocked_reasons["semantic_ingestion"] == "source_only"

    factory = build_provider_memory_service_from_env(
        memory_plane=MemoryPlaneService(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    factory_result = factory.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="installed-factory",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    assert factory_result.blocked_reasons["semantic_ingestion"] == "source_only"

    hermes = HermesMemoryProvider(
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier()
    )
    assert hermes.sync_turn(
        "Atlas owner is Bob.", "Receipt is confirmed.", operation_id="installed-hermes",
        task_id="task:one", authenticated_host_ingress=host_ingress,
    ).blocked_reasons["semantic_ingestion"] == "source_only"
    filesystem = build_filesystem_provider(
        tmp_path / "installed-filesystem",
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
    )
    assert filesystem.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="installed-filesystem",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    ).blocked_reasons["semantic_ingestion"] == "source_only"


def test_jsonl_replace_failure_is_atomic_and_lost_ack_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capability = _TestHostBootstrapCapability()
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    failed_path = tmp_path / "failed-replace"
    failed_store = JsonlMemoryPlaneStore(failed_path)
    failed_service = _service_with_capability(
        capability,
        memory_plane=MemoryPlaneService(record_store=failed_store),
    )
    monkeypatch.setattr(
        "memorii.core.memory_plane.store.os.replace",
        lambda source, target: (_ for _ in ()).throw(OSError("injected replace failure")),
    )
    with pytest.raises(OSError, match="injected replace failure"):
        failed_service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id="failed-replace",
            task_id="task:one",
            authenticated_host_ingress=host_ingress,
        )
    monkeypatch.undo()
    assert {
        record.source_kind
        for record in MemoryPlaneService(record_store=JsonlMemoryPlaneStore(failed_path)).list_records()
    } == {"semantic_ingestion_writer_admission"}

    lost_ack_path = tmp_path / "lost-ack"
    lost_ack_store = JsonlMemoryPlaneStore(lost_ack_path)
    lost_ack_service = _service_with_capability(
        capability,
        memory_plane=MemoryPlaneService(record_store=lost_ack_store),
    )
    original_apply = lost_ack_store.apply_batch

    def apply_then_fail(*args, **kwargs):
        original_apply(*args, **kwargs)
        raise OSError("injected lost acknowledgement")

    monkeypatch.setattr(lost_ack_store, "apply_batch", apply_then_fail)
    with pytest.raises(OSError, match="lost acknowledgement"):
        lost_ack_service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id="lost-ack",
            task_id="task:one",
            authenticated_host_ingress=host_ingress,
        )
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(lost_ack_path))
    expected_kinds = {
        "semantic_ingestion_source",
        "semantic_ingestion_admission_index",
        "semantic_ingestion_profile_selection",
        "semantic_ingestion_profile_verification",
        "semantic_ingestion_profile_outcome",
        "semantic_ingestion_writer_admission",
        "semantic_ingestion_preplanning_control",
        "semantic_ingestion_preplanning_artifact",
    }
    assert {record.source_kind for record in reopened_plane.list_records()} == expected_kinds
    retry = _service_with_capability(capability, memory_plane=reopened_plane)
    retry.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="lost-ack",
        task_id="task:one",
        authenticated_host_ingress=host_ingress,
    )
    assert {record.source_kind for record in reopened_plane.list_records()} == expected_kinds | {
        "semantic_ingestion_generation_member",
        "semantic_ingestion_generation_manifest",
        "semantic_ingestion_checkpoint_lifecycle",
        "semantic_ingestion_event_schema_registry_history",
        "semantic_ingestion_replay_authority",
    }


def test_unavailable_host_boundary_exposes_no_partial_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary = _UnavailableHostBoundary()
    monkeypatch.setattr(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        lambda **kwargs: (_InstalledCapabilityEntryPoint(boundary),),
    )
    service = ProviderMemoryService(memory_plane=MemoryPlaneService())
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="unavailable-host-boundary",
        task_id="task:one",
    )
    assert result.blocked_reasons["semantic_ingestion"] == "ingress_unavailable"


def test_bootstrap_construction_and_ingestion_attempt_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    capability = _TestHostBootstrapCapability()
    monkeypatch.setattr(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        lambda **kwargs: (_InstalledCapabilityEntryPoint(capability),),
    )

    def network_forbidden(*args, **kwargs):
        raise AssertionError("governed source admission attempted network access")

    monkeypatch.setattr("socket.getaddrinfo", network_forbidden)
    monkeypatch.setattr("socket.create_connection", network_forbidden)
    monkeypatch.setattr("socket.socket.connect", network_forbidden)
    monkeypatch.setattr("socket.socket.connect_ex", network_forbidden)
    monkeypatch.setattr("socket.socket.bind", network_forbidden)
    monkeypatch.setattr("socket.socket.listen", network_forbidden)
    service = build_provider_memory_service_from_env(memory_plane=MemoryPlaneService())
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="no-network",
        task_id="task:one",
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="provider:test",
            principal_handle=object(),
            session_handle=object(),
            received_at=datetime.now(UTC),
        ),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"


def test_denied_lookup_never_reads_protected_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    memory_plane = MemoryPlaneService()
    capability = _TestHostBootstrapCapability()
    service = _service_with_capability(capability, memory_plane=memory_plane)
    host_ingress = AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="protected-lookup",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=host_ingress,
    )
    denied_service = _service_with_capability(
        _TestHostBootstrapCapability(resolver=_PartialScopeResolver()),
        memory_plane=memory_plane,
    )
    reads: list[str] = []
    original_get = memory_plane.get_record

    def recording_get(memory_id: str):
        reads.append(memory_id)
        return original_get(memory_id)

    monkeypatch.setattr(memory_plane, "get_record", recording_get)
    response = denied_service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), "protected-lookup")
        ),
        authenticated_host_ingress=host_ingress,
    )
    assert response.available is False
    assert not any(memory_id.endswith(":outcome") for memory_id in reads)


def test_expected_host_ingress_denial_uses_non_disclosing_lookup_shape() -> None:
    plane = MemoryPlaneService()
    service = _service_with_capability(
        _TestHostBootstrapCapability(resolver=_DeniedResolver()),
        memory_plane=plane,
    )
    response = service.lookup_semantic_ingestion_outcome(
        SemanticIngestionOutcomeLookupRequest(
            delivery_identity=DeliveryIdentity.create(_binding(), "unknown-delivery")
        ),
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="provider:test",
            principal_handle=object(),
            session_handle=object(),
            received_at=datetime.now(UTC),
        ),
    )
    assert response.available is False and response.outcome is None
    assert {record.source_kind for record in plane.list_records()} == {
        "semantic_ingestion_writer_admission"
    }


def test_bootstrap_release_and_corpus_fail_closed_without_runtime_state() -> None:
    artifacts = build_bootstrap_profile_artifacts(_complete_corpus_cases())
    anchor = build_bootstrap_trust_anchor(artifacts)
    metadata = BootstrapProfileReleaseMetadata(
        coordinate=BOOTSTRAP_COORDINATE, bootstrap_profile_trust_anchor_digest=anchor.trust_anchor_digest,
        signed_release_digest="1" * 64,
    )
    assert verify_bootstrap_release(provider=DeterministicTestTrustRootProvider(anchor.trust_anchor_digest), metadata=metadata, anchor=anchor)
    assert not verify_bootstrap_release(provider=None, metadata=metadata, anchor=anchor)
    case = BootstrapGrammarCorpusCase(case_id="supported", declared_language="en", language_evidence_kind="authenticated_host_declaration", language_evidence_trust="trusted", governance_agreement="agrees", normalized_segment_bytes=b"x", disposition="supported_form", expected_reason=None)
    assert disposition_outcome(case) == "selected_pipeline_pending"
