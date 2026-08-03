from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import patch

import pytest
from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_evolution.atomic_store import (
    PreplanningOperationControl,
    SemanticAuthorizationAuthorityRecord,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapGrammarCorpusCase,
    BootstrapProfileReleaseMetadata,
    HostVerifiedBootstrapMaterial,
    build_bootstrap_profile_artifacts,
    build_bootstrap_trust_anchor,
    serialize_bootstrap_profile_artifacts,
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
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    AuthenticatedSemanticSourceInterval,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.capability import (
    AuthorizedSemanticIngestionRuntime,
    SemanticIngestionRuntimeAuthorization,
    build_authorized_local_semantic_runtime,
)
from memorii.core.semantic_ingestion.contracts import (
    IndependentSourceAnalysis,
    ParserConsensusAssessment,
    PredicateTemporalRule,
    PredicateTrustRule,
    SemanticArbitrationPolicyBundle,
    SemanticCandidate,
    SemanticPipelinePolicy,
    SemanticTerminalOutcome,
    SourceLocalIdentityEvidence,
    SourceSpan,
    SourceTemporalEvidenceSet,
    TemporalEvidenceCandidate,
    TemporalPolicySnapshot,
    TimeInterval,
    TrustPolicySnapshot,
    contract_digest,
    decode_semantic_contract,
)
from memorii.core.semantic_ingestion.egress import (
    InMemoryEgressPolicyRepository,
    ProviderEgressDecision,
    SignedEgressPolicyCommand,
)
from memorii.core.semantic_ingestion.pipeline import AnalyzerRoleInterpretation, SemanticIngestionPipeline
from memorii.integrations.hermes_provider import HermesMemoryProvider

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
        ("01-supported-atlas", "en", "authenticated_host_declaration", "trusted", "agrees", b"Atlas owner is Bob.", "supported_form", None),
        ("02-supported-receipt", "en", "authenticated_host_declaration", "trusted", "agrees", b"Receipt is confirmed.", "supported_form", None),
        ("03-unsupported-mixed", "en", "authenticated_host_declaration", "trusted", "agrees", b"Atlas is Bob. trailing", "unsupported_form", "mixed_residue"),
        ("04-unsupported-grammar", "en", "authenticated_host_declaration", "trusted", "agrees", b"unstructured", "unsupported_form", "unsupported_grammar"),
        ("05-abstain-extractor", "en", "authenticated_host_declaration", "trusted", "agrees", b"", "abstain_form", "extractor_abstained"),
        ("06-abstain-mismatch", "en", "mismatched", "mismatched", "disagrees", b"mismatch", "abstain_form", "language_mismatch"),
        ("07-abstain-missing", None, "missing", "missing", "missing", b"missing", "abstain_form", "missing_language_declaration"),
        ("08-abstain-non-english", "fr", "authenticated_host_declaration", "trusted", "agrees", b"bonjour", "abstain_form", "non_english_language"),
        ("09-abstain-untrusted", None, "untrusted", "untrusted", "missing", b"untrusted", "abstain_form", "untrusted_language"),
    )
    return tuple(
        BootstrapGrammarCorpusCase.model_validate({
            "case_id": case_id,
            "declared_language": language,
            "language_evidence_kind": evidence_kind,
            "language_evidence_trust": trust,
            "governance_agreement": agreement,
            "normalized_segment_bytes": source,
            "disposition": disposition,
            "expected_reason": reason,
        })
        for case_id, language, evidence_kind, trust, agreement, source, disposition, reason in values
    )


class _TrustRoot:
    def __init__(self, digest: str) -> None:
        self.digest = digest

    def verify_active_release(self, metadata: BootstrapProfileReleaseMetadata) -> bool:
        return metadata.bootstrap_profile_trust_anchor_digest == self.digest


class _TestHostBootstrapCapability:
    def __init__(self, *, resolver=None) -> None:
        artifacts = build_bootstrap_profile_artifacts(_bootstrap_cases())
        self._anchor = build_bootstrap_trust_anchor(artifacts)
        self._metadata = BootstrapProfileReleaseMetadata(
            coordinate=BOOTSTRAP_COORDINATE,
            bootstrap_profile_trust_anchor_digest=self._anchor.trust_anchor_digest,
        )
        self._payloads = serialize_bootstrap_profile_artifacts(artifacts)
        self._resolver = resolver or _Resolver()
        self._root = _TrustRoot(self._anchor.trust_anchor_digest)

    def load_verified_bootstrap_material(self):
        if not verify_bootstrap_release(
            provider=self._root, metadata=self._metadata, anchor=self._anchor
        ):
            return None
        return HostVerifiedBootstrapMaterial(
            release_metadata=self._metadata,
            trust_anchor=self._anchor,
            artifact_payloads=self._payloads,
            authenticated_ingress_resolver=self._resolver,
            profile_enabled=True,
        )


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


def _verified_runtime_store(plane: MemoryPlaneService | None = None):
    plane = plane or MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: TEST_NOW
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
        return plane, writers, SemanticIngestionAtomicStore(
            plane, writers, now_provider=lambda: TEST_NOW
        )
    binding = writers.commit_binding(current)
    plan = build_migration_plan(
        migration_plan_id="semantic-ingestion:verified", source_writer_epoch=1,
        legacy_snapshot_token=sha256(encode_typed_value(())).hexdigest(), entries=(),
    )
    checkpoint_values = {
        "migration_plan_id": plan.migration_plan_id, "plan_digest": plan.plan_digest,
        "completed_entry_digests": (), "target_generation": 1,
    }
    checkpoint = DeliveryCoordinateMigrationCheckpoint(
        **checkpoint_values,
        checkpoint_digest=sha256(encode_typed_value(checkpoint_values)).hexdigest(),
    )
    certificate = certify_migration(
        plan, checkpoint, independent_verifier_fingerprint="semantic-ingestion-verifier"
    )
    writers.transition(
        expected=binding, admission_id="semantic-ingestion:verified", runtime_mode="verified_semantic",
        writer_implementation_fingerprint="writer:verified", graph_schema_fingerprint="schema",
        migration_activation=activate_migration(plan, certificate), migration_plan=plan,
        migration_checkpoint=checkpoint, migration_certificate=certificate, target_records=(),
    )
    return plane, writers, SemanticIngestionAtomicStore(
        plane, writers, now_provider=lambda: TEST_NOW
    )


def _hex(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _bundle(predicate_id: str = "works_for") -> SemanticArbitrationPolicyBundle:
    effective = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC)
    )
    trust = TrustPolicySnapshot.create(
        policy_revision="trust-r1", system_effective_interval=effective,
        rules=(PredicateTrustRule(
            predicate_id=predicate_id, eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 10},
        ),),
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="temporal-r1", system_effective_interval=effective,
        rules=(PredicateTemporalRule(
            predicate_id=predicate_id, valid_time_requirement="required", allow_open_end=True,
        ),),
    )
    return SemanticArbitrationPolicyBundle.create(
        trust_policy=trust, temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 3, 1, tzinfo=UTC),
    )


def _analysis(
    proposal: SemanticCandidate, *, source_id: str, source_digest: str, source_text: str,
    source_authority_evidence, source_interval_evidence,
) -> IndependentSourceAnalysis:
    first = AnalyzerRoleInterpretation(
        analyzer_id="stanza", analyzer_fingerprint="a" * 64,
        predicate_span=SourceSpan(source_id=source_id, start=6, end=11), construction_family="active",
        role_spans=(("subject", SourceSpan(source_id=source_id, start=0, end=5)),),
        semantic_scope="asserted", attribution_kind="speaker",
    )
    second = first.model_copy(update={"analyzer_id": "spacy", "analyzer_fingerprint": "b" * 64})
    return IndependentSourceAnalysis.create(
        candidate_id=proposal.candidate_id, source_id=source_id, source_digest=source_digest,
        predicate_id=proposal.predicate_id, operation_kind=proposal.operation_kind,
        source_authority_evidence=source_authority_evidence,
        assertion_span=SourceSpan(source_id=source_id, start=0, end=len(source_text)),
        parser_consensus=ParserConsensusAssessment.create(primary=first, corroborating=second),
        identity_evidence=(SourceLocalIdentityEvidence(
            source_id=source_id, mention_span=SourceSpan(source_id=source_id, start=0, end=5),
            cluster_id="atlas", canonical_entity_id="entity:atlas", evidence_digest=_hex("identity"),
        ),),
        temporal_evidence=(SourceTemporalEvidenceSet(
            temporal_role="assertion", candidates=(TemporalEvidenceCandidate.create(
                candidate_id="assertion-time", kind="authenticated_source_interval",
                interval=source_interval_evidence.interval,
                source_authority=source_authority_evidence.authority,
                authenticated_source_interval_evidence=source_interval_evidence,
            ),), attachment_spans=(),
            attachment_consensus_digest=_hex("attachment"),
        ),),
    )


class _Resolver:
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime):
        return _base_ingress().model_copy(update={
            "semantic_egress_governance": AuthenticatedSemanticEgressGovernance(
                classification="internal", provider="capture", model="capture-v1", region="local",
                retention_mode="none", training_use=False,
            ),
            "semantic_source_authority": AuthenticatedSemanticSourceAuthority(
                authority_class="official", authenticated_provenance_class="host",
                governing_principal_id="user:user:alice", policy_revision="trust-r1",
                provenance_digest=_hex("source-authority"),
            ),
            "semantic_source_interval": AuthenticatedSemanticSourceInterval(
                start=datetime(2026, 1, 1, tzinfo=UTC),
                end=datetime(2026, 2, 1, tzinfo=UTC),
                authority_basis="server_source_metadata",
                provenance_digest=_hex("source-interval"), policy_revision="trust-r1",
            ),
        })


class _AuthorizedCapability(_TestHostBootstrapCapability):
    def __init__(self, *, runtime: AuthorizedSemanticIngestionRuntime) -> None:
        super().__init__(resolver=_Resolver())
        self._runtime = runtime

    def build_semantic_ingestion_runtime(self, *, memory_plane, now_provider):
        return self._runtime


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
            binding=binding, policy_id="capture-policy", policy_revision=1,
            policy_fingerprint="f" * 64, expires_at=at + timedelta(minutes=1),
        )


class _AdversarialEgressProvider:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def current(self, *, binding, at: datetime):
        if self.mode == "outage":
            raise OSError("egress authority unavailable")
        mutations = {
            "tenant_id": "tenant:other",
            "source_id": "source:other",
            "source_digest": "0" * 64,
            "segment_id": "segment:other",
            "classification": "public",
            "provider": "other-provider",
            "model": "other-model",
            "region": "other-region",
            "retention_mode": "retained",
            "training_use": True,
        }
        decision_binding = (
            binding.model_copy(update={self.mode: mutations[self.mode]})
            if self.mode in mutations else binding
        )
        decision = ProviderEgressDecision.create(
            binding=decision_binding,
            policy_id="capture-policy",
            policy_revision=1,
            policy_fingerprint="f" * 64,
            expires_at=(at if self.mode == "expiry" else at + timedelta(minutes=1)),
        )
        stale_decision_mutations = {
            "policy_id": "other-policy",
            "policy_revision": 2,
            "policy_fingerprint": "e" * 64,
            "decision_digest": "0" * 64,
        }
        if self.mode in stale_decision_mutations:
            return decision.model_copy(
                update={self.mode: stale_decision_mutations[self.mode]}
            )
        if self.mode not in {"signature", "signer"}:
            return decision

        class SignatureVerifier:
            def verify(self, *, signer_id, payload, signature):
                return signature == sha256(signer_id.encode() + payload).digest()

        class LifecycleVerifier:
            def is_eligible(self, *, signer_id, at):
                return signer_id == "egress-root"

        repository = InMemoryEgressPolicyRepository(
            signature_verifier=SignatureVerifier(), lifecycle_verifier=LifecycleVerifier()
        )
        signer_id = "ineligible-root" if self.mode == "signer" else "egress-root"
        provisional = SignedEgressPolicyCommand(
            command_id="adversarial-command",
            action="install",
            policy_id="capture-policy",
            expected_revision=0,
            issued_at=at,
            signer_id=signer_id,
            decision=decision,
            signature=b"invalid",
        )
        command = provisional.model_copy(
            update={
                "signature": (
                    sha256(signer_id.encode() + provisional.signed_payload()).digest()
                    if self.mode == "signer" else b"invalid"
                )
            }
        )
        repository.apply(command, control_plane_principal="admin")
        return repository.current(binding=binding, at=at)


class _CaptureTransport:
    def __init__(self) -> None:
        candidate = SemanticCandidate(
            candidate_id="candidate", operation_kind="fact", predicate_id="works_for",
            assertion_quote="Atlas owner is Bob.", alignment_refs=(),
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
        self, *, proposal: SemanticCandidate, source_id: str, source_digest: str, source_text: str,
        source_authority_evidence, source_interval_evidence,
    ):
        return _analysis(
            proposal, source_id=source_id, source_digest=source_digest, source_text=source_text,
            source_authority_evidence=source_authority_evidence,
            source_interval_evidence=source_interval_evidence,
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
            "authorization_digest": (
                "0" * 64 if self.mode == "mutated" else sha256(authorization_bytes).hexdigest()
            ),
            "target_profile_manifest_digest": use.profile_manifest_digest,
            "verified_bootstrap_release_digest": use.verified_bootstrap_release_digest,
            "deployment_artifact_digest": "d" * 64,
            "authority_snapshot_digest": "a" * 64,
            "active_epoch": 1,
            "expires_at": (
                datetime(2020, 1, 1, tzinfo=UTC)
                if self.mode == "expired"
                else datetime(2030, 1, 1, tzinfo=UTC)
            ),
            "signer_id": "test-signer",
        }
        return SemanticIngestionRuntimeAuthorization(
            **body,
            decision_digest=contract_digest(
                b"memorii.semantic-ingestion.verified-deployment-authorization.v1", body
            ),
        )


def _host_ingress() -> AuthenticatedHostIngress:
    return AuthenticatedHostIngress(
        provider_identity="provider:test", principal_handle=object(), session_handle=object(),
        received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )


def _dependencies(
    *, writer_admission=None, atomic_store=None, authorization_mode="valid", assessor=None,
):
    transport = _CaptureTransport()
    runtime = AuthorizedSemanticIngestionRuntime(
        authorization_bytes=b"signed-test-authorization",
        authorization_verifier=_AuthorizationVerifier(authorization_mode),
        pipeline=SemanticIngestionPipeline(transport=transport), policy_provider=_PolicyProvider(),
        egress_policy_provider=_EgressProvider(),
        candidate_assessor=(
            assessor
            if assessor is not None
            else (_Assessor() if writer_admission is not None else _AbstainAssessor())
        ),
        writer_admission=writer_admission, atomic_store=atomic_store,
    )
    return transport, _AuthorizedCapability(runtime=runtime)


def _runtime_for_outage(*, writers, store, stage: str) -> AuthorizedSemanticIngestionRuntime:
    transport = _OutageTransport() if stage == "proposal" else _CaptureTransport()
    return AuthorizedSemanticIngestionRuntime(
        authorization_bytes=b"signed-test-authorization",
        authorization_verifier=_AuthorizationVerifier(),
        pipeline=SemanticIngestionPipeline(transport=transport),
        policy_provider=_PolicyProvider(outage=stage == "policy_read"),
        egress_policy_provider=_EgressProvider(),
        candidate_assessor=_OutageAssessor() if stage == "analysis" else _Assessor(),
        writer_admission=writers,
        atomic_store=store,
    )


def test_normal_provider_root_reaches_allowed_transport_once_and_terminalizes() -> None:
    transport, capability = _dependencies()
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=MemoryPlaneService())
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-normal", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(transport.requests) == 1
    terminal_controls = [
        value for value in service._memory_plane.list_records()
        if value.source_kind == "semantic_ingestion_preplanning_control" and value.content["control"]["state"] == "terminal"
    ]
    assert len(terminal_controls) == 1


@pytest.mark.parametrize("mode", ["expired", "revoked", "outage", "mutated"])
def test_external_deployment_authorization_failure_is_zero_wire(mode: str) -> None:
    transport, capability = _dependencies(authorization_mode=mode)
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=MemoryPlaneService())
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=f"semantic-ingestion-authorization-{mode}",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert transport.requests == []
    members = [
        record.content["member"]
        for record in service._memory_plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    ]
    assert not any(member["kind"] in {"graph_delta", "event_batch"} for member in members)
    group_results = [
        decode_semantic_contract(
            member["canonical_payload"].encode("utf-8"), SemanticTerminalOutcome
        )
        for member in members
        if member["kind"] == "source_result"
    ]
    assert all(terminal.status == "evidence_only" for terminal in group_results)
    assert not any(terminal.status == "accepted" for terminal in group_results)


@pytest.mark.parametrize(
    "mode",
    [
        "tenant_id", "source_id", "source_digest", "segment_id", "classification",
        "provider", "model", "region", "retention_mode", "training_use", "signature",
        "signer", "expiry", "outage", "policy_id", "policy_revision",
        "policy_fingerprint", "decision_digest",
    ],
)
def test_public_coordinator_rejects_every_egress_authority_mutation_without_wire(
    mode: str,
) -> None:
    plane, writers, store = _verified_runtime_store(MemoryPlaneService())
    transport = _CaptureTransport()
    runtime = AuthorizedSemanticIngestionRuntime(
        authorization_bytes=b"signed-test-authorization",
        authorization_verifier=_AuthorizationVerifier(),
        pipeline=SemanticIngestionPipeline(transport=transport),
        policy_provider=_PolicyProvider(),
        egress_policy_provider=_AdversarialEgressProvider(mode),
        candidate_assessor=_Assessor(),
        writer_admission=writers,
        atomic_store=store,
    )
    capability = _AuthorizedCapability(runtime=runtime)
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(
            memory_plane=plane, now_provider=lambda: TEST_NOW
        )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=f"semantic-ingestion-egress-{mode}",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert transport.requests == []
    members = [
        record.content["member"]
        for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    ]
    assert not any(member["kind"] in {"graph_delta", "event_batch"} for member in members)
    control = PreplanningOperationControl.model_validate(next(
        record.content["control"]
        for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_preplanning_control"
    ))
    terminals = [
        decode_semantic_contract(member.canonical_payload, SemanticTerminalOutcome)
        for generation in range(2, control.generation + 1)
        for member in store.generation_members(control.operation_fence, generation)
        if member.kind == "source_result"
    ]
    assert terminals and all(terminal.status == "evidence_only" for terminal in terminals)
    assert not any(terminal.status == "accepted" for terminal in terminals)


def test_hermes_and_filesystem_roots_use_the_same_semantic_pipeline(tmp_path) -> None:
    direct_transport, capability = _dependencies()
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        hermes = HermesMemoryProvider(ProviderMemoryService())
    hermes.sync_turn(
        "Atlas owner is Bob.", "Receipt is confirmed.", operation_id="semantic-ingestion-hermes",
        task_id="task:one", user_id="user:alice", authenticated_host_ingress=_host_ingress(),
    )
    assert len(direct_transport.requests) == 2

    fs_transport, fs_capability = _dependencies()
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(fs_capability),),
    ):
        filesystem = build_filesystem_provider(tmp_path / "semantic-ingestion-filesystem")
    filesystem.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-filesystem", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert len(fs_transport.requests) == 1


def test_normal_provider_accepted_control_commits_complete_effect_group() -> None:
    plane, writers, store = _verified_runtime_store()
    delivery_id = "semantic-ingestion-accepted"
    transport, capability = _dependencies(writer_admission=writers, atomic_store=store)
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW)
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id=delivery_id, task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    effect_kinds = {
        value.content["member"]["kind"]
        for value in plane.list_records()
        if value.source_kind == "semantic_ingestion_generation_member"
    }
    assert {"graph_delta", "event_batch", "group_result", "observation_delta"}.issubset(effect_kinds)


def test_ordinary_provider_root_uses_production_local_analyzer_without_wire() -> None:
    plane, writers, store = _verified_runtime_store()
    runtime = build_authorized_local_semantic_runtime(
        authorization_bytes=b"signed-test-authorization",
        authorization_verifier=_AuthorizationVerifier(),
        policy_provider=_PolicyProvider("owner_is"),
        writer_admission=writers,
        atomic_store=store,
    )
    capability = _AuthorizedCapability(runtime=runtime)
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW)
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-local-production",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    effect_kinds = {
        value.content["member"]["kind"]
        for value in plane.list_records()
        if value.source_kind == "semantic_ingestion_generation_member"
    }
    assert {"graph_delta", "event_batch", "group_result", "observation_delta"}.issubset(
        effect_kinds
    )


@pytest.mark.parametrize("stage", ["policy_read", "proposal", "analysis"])
def test_public_jsonl_reconcile_resumes_preplanning_outage_without_redelivery(
    tmp_path, stage: str
) -> None:
    storage = tmp_path / stage
    plane, writers, store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    failed_capability = _AuthorizedCapability(
        runtime=_runtime_for_outage(writers=writers, store=store, stage=stage)
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(failed_capability),),
    ):
        failed_service = ProviderMemoryService(
            memory_plane=plane, now_provider=lambda: TEST_NOW
        )
    failed_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=f"semantic-ingestion-reconcile-{stage}",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    member_kinds = {
        record.content["member"]["kind"]
        for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    }
    assert "execution_plan" in member_kinds
    assert "source_result" not in member_kinds

    reopened_plane, reopened_writers, reopened_store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    recovered_transport, recovered_capability = _dependencies(
        writer_admission=reopened_writers, atomic_store=reopened_store
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(recovered_capability),),
    ):
        reopened_service = ProviderMemoryService(
            memory_plane=reopened_plane, now_provider=lambda: TEST_NOW
        )
    outcomes = reopened_service.reconcile_memory_evolution()
    assert [outcome.status for outcome in outcomes] == ["evolution_committed"]
    assert len(recovered_transport.requests) == 1
    final_kinds = [
        record.content["member"]["kind"]
        for record in reopened_plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    ]
    assert final_kinds.count("execution_plan") == 1
    assert final_kinds.count("recovery_authority_binding") == 1
    assert final_kinds.count("source_result") == 1


@pytest.mark.parametrize("mutation", ["rotate", "revoke", "coordinate"])
def test_jsonl_recovery_authority_change_is_zero_learned_calls(
    tmp_path, mutation: str,
) -> None:
    storage = tmp_path / mutation
    plane, writers, store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    failed_capability = _AuthorizedCapability(
        runtime=_runtime_for_outage(writers=writers, store=store, stage="proposal")
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(failed_capability),),
    ):
        failed_service = ProviderMemoryService(
            memory_plane=plane, now_provider=lambda: TEST_NOW
        )
    failed_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=f"semantic-ingestion-recovery-{mutation}",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    control_record = next(
        record for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_preplanning_control"
    )
    control = PreplanningOperationControl.model_validate(control_record.content["control"])
    plan = failed_service._provider_ingestion._semantic_terminal_persistence.recover_execution_plan(
        fence=control.operation_fence
    )
    assert plan is not None
    assert plan.operation_fence_binding_digest == control.operation_fence.binding_digest
    assert plan.admitted_source_id == control.operation_fence.source_id
    assert plan.admitted_source_digest == control.operation_fence.source_digest
    assert plan.admitted_source_bytes_digest == sha256(plan.source_utf8_bytes).hexdigest()
    current = store.authorization_authority(plan.authorization_authority_scope_id)
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
        reopened = ProviderMemoryService(
            memory_plane=reopened_plane, now_provider=lambda: TEST_NOW
        )
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
        runtime=_runtime_for_outage(
            writers=foreign_writers, store=foreign_store, stage="proposal"
        )
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(foreign_capability),),
    ):
        foreign_service = ProviderMemoryService(
            memory_plane=foreign_plane, now_provider=lambda: TEST_NOW
        )
    foreign_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-foreign-plan-source",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    foreign_control = PreplanningOperationControl.model_validate(next(
        record.content["control"]
        for record in foreign_plane.list_records()
        if record.source_kind == "semantic_ingestion_preplanning_control"
    ))
    foreign_plan = (
        foreign_service._provider_ingestion._semantic_terminal_persistence
        .recover_execution_plan(fence=foreign_control.operation_fence)
    )
    assert foreign_plan is not None

    storage = tmp_path / "foreign-plan-target"
    target_plane, target_writers, target_store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    target_capability = _AuthorizedCapability(
        runtime=_runtime_for_outage(
            writers=target_writers, store=target_store, stage="proposal"
        )
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(target_capability),),
    ):
        target_service = ProviderMemoryService(
            memory_plane=target_plane, now_provider=lambda: TEST_NOW
        )
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
        reopened = ProviderMemoryService(
            memory_plane=reopened_plane, now_provider=lambda: TEST_NOW
        )
    with patch.object(
        reopened._provider_ingestion._semantic_terminal_persistence,
        "recover_execution_plan",
        return_value=foreign_plan,
    ), pytest.raises(ValueError, match="fence/source"):
        reopened.reconcile_memory_evolution()
    assert transport.requests == []
    assert assessor.calls == 0


def test_identical_redelivery_after_authority_rotation_reuses_plan_without_calls(
    tmp_path,
) -> None:
    storage = tmp_path / "redelivery-rotation"
    plane, writers, store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    capability = _AuthorizedCapability(
        runtime=_runtime_for_outage(writers=writers, store=store, stage="proposal")
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW)
    event_kwargs = {
        "operation": ProviderOperation.CHAT_USER_TURN,
        "content": "Atlas owner is Bob.",
        "operation_id": "semantic-ingestion-identical-redelivery-rotation",
        "task_id": "task:one",
        "user_id": "user:alice",
        "authenticated_host_ingress": _host_ingress(),
    }
    service.sync_event(**event_kwargs)
    control = PreplanningOperationControl.model_validate(next(
        record.content["control"]
        for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_preplanning_control"
    ))
    plan = service._provider_ingestion._semantic_terminal_persistence.recover_execution_plan(
        fence=control.operation_fence
    )
    assert plan is not None
    current = store.authorization_authority(plan.authorization_authority_scope_id)
    assert current is not None
    authority, precondition = current
    body = authority.model_dump(mode="python", exclude={"coordinates_digest"})
    body.update({
        "authority_revision": 2,
        "deployment_authorization_digest": "9" * 64,
    })
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
    assessor = _CountingAssessor()
    transport, recovered_capability = _dependencies(
        writer_admission=reopened_writers,
        atomic_store=reopened_store,
        assessor=assessor,
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(recovered_capability),),
    ):
        reopened = ProviderMemoryService(
            memory_plane=reopened_plane, now_provider=lambda: TEST_NOW
        )
    result = reopened.sync_event(**event_kwargs)
    assert result.blocked_reasons["semantic_ingestion"] == "retryable_outage"
    assert transport.requests == []
    assert assessor.calls == 0
    kinds = [
        record.content["member"]["kind"]
        for record in reopened_plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    ]
    assert kinds.count("execution_plan") == 1
    assert "source_result" not in kinds


def test_public_reconcile_persists_retry_exhaustion_within_attempt_budget(tmp_path) -> None:
    storage = tmp_path / "exhaustion"
    plane, writers, store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    capability = _AuthorizedCapability(
        runtime=_runtime_for_outage(writers=writers, store=store, stage="policy_read")
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW)
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-retry-exhaustion",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    service.reconcile_memory_evolution()
    service.reconcile_memory_evolution()
    service.reconcile_memory_evolution()
    controls = [
        record.content["control"]
        for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_preplanning_control"
    ]
    assert len(controls) == 1
    assert controls[0]["state"] == "terminal"
    source_results = [
        member
        for generation in range(2, controls[0]["generation"] + 1)
        for member in store.generation_members(
            PreplanningOperationControl.model_validate(controls[0]).operation_fence,
            generation,
        )
        if member.kind == "source_result"
    ]
    assert len(source_results) == 1
    terminal = decode_semantic_contract(source_results[0].canonical_payload, SemanticTerminalOutcome)
    assert terminal.status == "evidence_only"
    assert terminal.reason_codes == ("retry_budget_exhausted",)
    assert service.reconcile_memory_evolution() == []


@pytest.mark.parametrize(
    "boundary", ["checkpoint_source_progress", "persist_terminal_group", "finalize_source"]
)
def test_public_jsonl_lost_ack_reopens_without_duplicate_effects(
    tmp_path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    storage = tmp_path / boundary
    plane, writers, store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    _, capability = _dependencies(writer_admission=writers, atomic_store=store)
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW)
    original = getattr(store, boundary)
    failed = False

    def apply_then_fail(request, **kwargs):
        nonlocal failed
        result = original(request, **kwargs)
        selected_checkpoint = boundary != "checkpoint_source_progress" or any(
            member.kind == "terminal_artifact" for member in request.members
        )
        if not failed and selected_checkpoint:
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

    reopened_plane, reopened_writers, reopened_store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    reopened_assessor = _CountingAssessor()
    reopened_transport, reopened_capability = _dependencies(
        writer_admission=reopened_writers,
        atomic_store=reopened_store,
        assessor=reopened_assessor,
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(reopened_capability),),
    ):
        reopened = ProviderMemoryService(
            memory_plane=reopened_plane, now_provider=lambda: TEST_NOW
        )
    reopened.reconcile_memory_evolution()
    assert failed is True
    assert reopened_transport.requests == []
    assert reopened_assessor.calls == 0
    controls = [
        record.content["control"]
        for record in reopened_plane.list_records()
        if record.source_kind == "semantic_ingestion_preplanning_control"
    ]
    assert len(controls) == 1 and controls[0]["state"] == "terminal"
    kinds = [
        record.content["member"]["kind"]
        for record in reopened_plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    ]
    assert kinds.count("execution_plan") == 1
    assert kinds.count("group_result") == 1
    assert kinds.count("source_result") == 1


def test_public_jsonl_service_matches_frozen_wire_and_member_bytes_across_reopen(
    tmp_path,
) -> None:
    storage = tmp_path / "frozen-public-integration"
    plane, writers, store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    transport, capability = _dependencies(writer_admission=writers, atomic_store=store)
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(capability),),
    ):
        service = ProviderMemoryService(memory_plane=plane, now_provider=lambda: TEST_NOW)
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="semantic-ingestion-frozen-public-integration",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    observed = {
        "wire": sha256(transport.requests[0]).hexdigest(),
        **{
            record.content["member"]["kind"]: record.content["member"]["payload_digest"]
            for record in plane.list_records()
            if record.source_kind == "semantic_ingestion_generation_member"
            and record.content["member"]["kind"]
            in {"terminal_artifact", "graph_delta", "event_batch", "source_result"}
        },
    }
    assert observed == {
        "wire": "8e03752bbf05c9e9e148a28f1dd2b7d61a69719d9c9022c59cdeda516bee04cc",
        "terminal_artifact": "9da9ff3ff76bf677cee67b8ee00d0dd3d0eddb1b9a70711c6498284f2c430af4",
        "graph_delta": "20f7fb17c59267e24b09ea910a40edfaf2d57748a399c6e2f253e92f8b47445e",
        "event_batch": "26df9ffe1713caa5e05a58dbab51fa92fd2a5b98ed22126e479161390bb303c4",
        "source_result": "9da9ff3ff76bf677cee67b8ee00d0dd3d0eddb1b9a70711c6498284f2c430af4",
    }
    before = (storage / "memory_records.jsonl").read_bytes()
    assert sha256(before).hexdigest() == "dd49f76cb43b13f905576300265e9eeac6bb292e2e858ef8e468a49a8e8ce66e"
    member_map = tuple(sorted(
        (
            int(record.memory_id.rsplit(":", 2)[1]),
            record.memory_id.rsplit(":", 2)[2],
            record.content["member"]["kind"],
            record.content["member"]["payload_digest"],
        )
        for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_generation_member"
    ))
    assert member_map == (
        (2, "semantic-ingestion-00-execution-plan", "execution_plan", "a2ed8ca9803b8afae911a11095d584e3554dd16b0283b4cabef8f0d3ee987104"),
        (2, "semantic-ingestion-01-progress", "progress", "4c95242d0caaee421ba7178d667cbb803c391dee1e6dc6ad29ea0e3aa3eb848f"),
        (3, "semantic-ingestion-00-progress", "progress", "0f477604f49db7f105a449f045598c3f42f7bec117daf58d81cb03505ea4d190"),
        (4, "semantic-ingestion-00-progress", "progress", "8da79dc10c9e6df74d4d5c413264ac280d3ad1133728145f29c71a37ddf38c44"),
        (5, "semantic-ingestion-00-progress", "progress", "2133a5f69794d65b86f288402e6766b397300c354cd8d791d7486261c562e2cb"),
        (6, "semantic-ingestion-00-artifact_closure", "artifact_closure", "e34c1f606798ec0201fd9f488280f6b354a0132b2174b5ed1cfb66f81b5c0952"),
        (6, "semantic-ingestion-01-artifact_index", "artifact_index", "031f23edf34997cd120d1891256541ae46c68a37ef3b3e4b48ffa36fcfdd24ce"),
        (6, "semantic-ingestion-02-authorization_read_set", "authorization_read_set", "5d202114c60a3289be781407eca3cc02e36e4b9c31e5ceffcb3e1dcb01d4ec85"),
        (6, "semantic-ingestion-03-independence_certificate", "independence_certificate", "97046c95bdfa978d1f2534ab7b432ec78755d2833a96313bb783a7484ced2b7c"),
        (6, "semantic-ingestion-04-lifecycle", "lifecycle", "4117cef643ccd43a83e1cd11c674f940f09d8fda9692a0343c895cc3548a3276"),
        (6, "semantic-ingestion-05-plan", "plan", "ff80ca93dbc36259d0db85937357940567919fe39050f2fb5e25fbf82b15b157"),
        (6, "semantic-ingestion-06-planning_artifact", "planning_artifact", "4b1042b420ceb8bb55760f4daa1d271bada8cc54208c7f22644d23ac75232e75"),
        (6, "semantic-ingestion-07-planning_authorization", "planning_authorization", "0634307e12a27b67290b2e6d5e4b7197880153042711ad676485946cdd8e5499"),
        (6, "semantic-ingestion-08-progress", "progress", "d4fd5b7f43987ffddaf3394fa48b234f78e87cba5784b0301d4a839a900de867"),
        (6, "semantic-ingestion-09-terminal_artifact", "terminal_artifact", "9da9ff3ff76bf677cee67b8ee00d0dd3d0eddb1b9a70711c6498284f2c430af4"),
        (7, "semantic-ingestion-00-artifact_closure", "artifact_closure", "e34c1f606798ec0201fd9f488280f6b354a0132b2174b5ed1cfb66f81b5c0952"),
        (7, "semantic-ingestion-01-artifact_index", "artifact_index", "031f23edf34997cd120d1891256541ae46c68a37ef3b3e4b48ffa36fcfdd24ce"),
        (7, "semantic-ingestion-02-event_batch", "event_batch", "26df9ffe1713caa5e05a58dbab51fa92fd2a5b98ed22126e479161390bb303c4"),
        (7, "semantic-ingestion-03-graph_delta", "graph_delta", "20f7fb17c59267e24b09ea910a40edfaf2d57748a399c6e2f253e92f8b47445e"),
        (7, "semantic-ingestion-04-group_result", "group_result", "1a3b7cbf9fa75831597a577efa4b86319832a9ec79cd948ad115464930a32fd7"),
        (7, "semantic-ingestion-05-observation_delta", "observation_delta", "e1ea5be8b31968d36c23fb8017c7a9a522b11c9fea57028e4d803455705f6cce"),
        (8, "semantic-ingestion-00-artifact_closure", "artifact_closure", "e34c1f606798ec0201fd9f488280f6b354a0132b2174b5ed1cfb66f81b5c0952"),
        (8, "semantic-ingestion-01-lifecycle", "lifecycle", "223a0207d584e5e57bb4474182d159da91e125688a19ef3b380db837a011d401"),
        (8, "semantic-ingestion-02-observation_delta", "observation_delta", "e1ea5be8b31968d36c23fb8017c7a9a522b11c9fea57028e4d803455705f6cce"),
        (8, "semantic-ingestion-03-source_result", "source_result", "9da9ff3ff76bf677cee67b8ee00d0dd3d0eddb1b9a70711c6498284f2c430af4"),
        (8, "semantic-ingestion-04-source_summary", "source_summary", "06395ef84dd81a90b215285746bdf381cb6599b444c5d638eb339743e3077b83"),
        (8, "semantic-ingestion-05-terminal_operation", "terminal_operation", "0417f12b936b2ecc1c8796acd71c99b9b3d21391b075128ba6e87e97cc226496"),
    )

    reopened_plane, reopened_writers, reopened_store = _verified_runtime_store(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    )
    _, reopened_capability = _dependencies(
        writer_admission=reopened_writers, atomic_store=reopened_store
    )
    with patch(
        "memorii.core.memory_evolution.bootstrap_profile.entry_points",
        return_value=(_InstalledCapabilityEntryPoint(reopened_capability),),
    ):
        reopened = ProviderMemoryService(
            memory_plane=reopened_plane, now_provider=lambda: TEST_NOW
        )
    assert reopened.reconcile_memory_evolution() == []
    assert (storage / "memory_records.jsonl").read_bytes() == before
