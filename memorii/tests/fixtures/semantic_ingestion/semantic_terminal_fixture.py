"""Self-contained semantic terminal persistence fixtures shared without importing test modules."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Literal

from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
    SourceAdmissionAccepted,
    source_admission_source_digest,
)
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapGrammarCorpusCase,
    BootstrapProfileReleaseMetadata,
    HostVerifiedBootstrapMaterial,
    build_bootstrap_profile_artifacts,
    build_bootstrap_trust_anchor,
    serialize_bootstrap_profile_artifacts,
    verify_bootstrap_profile,
)
from memorii.core.memory_evolution.conflict_attention import (
    ActiveSemanticConflictResolverAuthority,
    ConflictResolutionOption,
    SemanticConflictAuthorityResolution,
    SemanticConflictAuthorityResolutionRequest,
    SemanticConflictDisplayBinding,
    SemanticConflictResolverAuthority,
    semantic_conflict_rendered_item_utf8_bytes,
)
from memorii.core.memory_evolution.delivery_coordinate_migration import (
    DeliveryCoordinateMigrationCheckpoint,
    activate_migration,
    build_migration_plan,
    certify_migration,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import SourceObservation, SourceType
from memorii.core.memory_evolution.projection_history import (
    SemanticConflictResolverAuthorityRepository,
)
from memorii.core.memory_evolution.semantic_state import (
    AcceptedClaimIdentity,
    ImmutableAssertionEntityRef,
    PredicateStateRule,
    SemanticAssertionKey,
    SemanticClaimSlotKey,
    SemanticClaimValueKey,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    SemanticWriterCommitBinding,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.semantic_ingestion.authorization import (
    SemanticAuthorizationAuthorityRepository,
)
from memorii.core.semantic_ingestion.capability import (
    AuthorizedSemanticIngestionRuntime,
    SemanticIngestionRuntimeAuthorization,
)
from memorii.core.semantic_ingestion.carriers import compile_accepted_carriers
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedEventTimeReference,
    AuthenticatedSourceIntervalEvidence,
    IndependentSourceAnalysis,
    PredicateTemporalRule,
    PredicateTrustRule,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SemanticExecutionLineage,
    SemanticTerminalBindingSet,
    SemanticTerminalOutcome,
    SourceAuthority,
    SourceAuthorityEvidence,
    TemporalPolicySnapshot,
    TextPreparationPolicy,
    TextPreparationRequest,
    TimeInterval,
    TrustDecayStep,
    TrustPolicySnapshot,
    contract_digest,
)
from memorii.core.semantic_ingestion.local_analyzer import ProductionLocalSemanticAnalyzer
from memorii.core.semantic_ingestion.operation_assessment import seal_semantic_operation
from memorii.core.semantic_ingestion.persistence import SemanticTerminalPersistenceService
from memorii.core.semantic_ingestion.source_preparation import (
    InMemoryPreparedSourceRepository,
    TextPreparationService,
)
from memorii.core.semantic_ingestion.temporal_evidence_resolution import TemporalEvidenceResolver
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from pydantic import BaseModel
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import (
    build_prepared_source_authority,
)
from tests.fixtures.semantic_ingestion.host_bootstrap_authority import (
    build_test_host_verified_bootstrap_release_evidence,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = "Atlas works for Memorii."
SOURCE_ID = "source"
SOURCE_DIGEST = sha256(SOURCE.encode()).hexdigest()


class _CurrentAuthorization:
    def verify_current(self, read_set, *, use_point: str) -> bool:
        return use_point == "pre_commit"


@dataclass(frozen=True)
class TerminalPersistenceHarness:
    plane: MemoryPlaneService
    store: SemanticIngestionAtomicStore
    service: SemanticTerminalPersistenceService
    authorization_repository: SemanticAuthorizationAuthorityRepository
    accepted_fence: OperationFenceBinding
    zero_effect_fence: OperationFenceBinding


def build_terminal_persistence_harness(root: Path) -> TerminalPersistenceHarness:
    """Build a durable verified-writer harness through public admission owners."""

    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root))
    writers = SemanticWriterAdmissionStore(
        plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="semantic-ingestion",
            writer_implementation_fingerprint="writer",
            graph_schema_fingerprint="schema",
        )
    )
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
    certificate = certify_migration(
        plan,
        checkpoint,
        independent_verifier_fingerprint="semantic-ingestion-verifier",
    )
    binding = writers.commit_binding(
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
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    _, accepted_fence = handoff(
        plane,
        coordinate="accepted-observation",
        atomic_store=store,
        writer_binding=binding,
    )
    _, zero_effect_fence = handoff(
        plane,
        coordinate="zero-effect-observation",
        atomic_store=store,
        writer_binding=binding,
    )
    authorization_repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        now_provider=lambda: NOW,
    )
    service = SemanticTerminalPersistenceService(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        authorization_repository=authorization_repository,
    )
    return TerminalPersistenceHarness(
        plane=plane,
        store=store,
        service=service,
        authorization_repository=authorization_repository,
        accepted_fence=accepted_fence,
        zero_effect_fence=zero_effect_fence,
    )


def persist_harness_terminal(
    harness: TerminalPersistenceHarness,
    *,
    fence: OperationFenceBinding,
    terminal: SemanticTerminalOutcome,
) -> None:
    if terminal.authorization_read_set is not None:
        harness.authorization_repository.observe_verified(
            authority_scope_id=harness.authorization_repository.scope_id(
                source_id=fence.source_id,
                source_digest=fence.source_digest,
            ),
            read_set=terminal.authorization_read_set,
            valid_until=datetime(2030, 1, 1, tzinfo=UTC),
        )
    harness.service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=_CurrentAuthorization(),
    )


def reopen_terminal_persistence_store(root: Path) -> SemanticIngestionAtomicStore:
    """Reconstruct the durable replay owner from a fresh store composition."""

    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root))
    writers = SemanticWriterAdmissionStore(
        plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    return SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)


@cache
def _prepared_source_authority(
    source_id: str, source_digest: str, source_text: str
):
    """Build one immutable Step-2 authority for identical fixture inputs."""
    policy = TextPreparationPolicy.create(
        max_segment_characters=max(1, len(source_text)),
        supported_languages=("en",),
        segmentation_algorithm=(
            "memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1"
        ),
        context_window_algorithm=(
            "memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1"
        ),
    )
    return build_prepared_source_authority(
        source_id=source_id,
        source_digest=source_digest,
        source_text=source_text,
        preparation_policy=policy,
    )


def _prepared_source_repository(
    *, source_id: str, source_digest: str, source_text: str
) -> InMemoryPreparedSourceRepository:
    # Each terminal receives a fresh repository.  The cached value is frozen
    # and the repository validates/clones on publication and load, so tests
    # cannot share mutable state while avoiding repeated fixture construction.
    repository = InMemoryPreparedSourceRepository()
    observation = SourceObservation(
        source_id=source_id,
        text=source_text,
        source_type=SourceType.USER,
        source_digest=source_digest,
        delivery_key_digest=sha256(f"terminal:{source_id}".encode()).hexdigest(),
    )
    prepared = _prepared_source_authority(source_id, source_digest, source_text)
    TextPreparationService(
        producer=lambda _request: prepared,
        repository=repository,
    ).prepare_and_publish(
        TextPreparationRequest(
            observation=observation,
            policy=prepared.preparation_policy,
        )
    )
    return repository


def _conflict_digest(domain: bytes, value: object) -> str:
    def normalize(item: object) -> object:
        if isinstance(item, BaseModel):
            return normalize(item.model_dump(mode="python"))
        if isinstance(item, dict):
            return {key: normalize(member) for key, member in item.items()}
        if isinstance(item, tuple):
            return tuple(normalize(member) for member in item)
        return item

    return sha256(domain + encode_typed_value(normalize(value))).hexdigest()


def _bootstrap_profile_for_test_runtime():
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

    artifacts = build_bootstrap_profile_artifacts(
        (
            case("01-supported", b"Atlas owner is Bob.", "supported_form", None),
            case("02-mixed", b"Atlas is Bob. trailing", "unsupported_form", "mixed_residue"),
            case("03-grammar", b"unstructured", "unsupported_form", "unsupported_grammar"),
            case("04-extractor", b"", "abstain_form", "extractor_abstained"),
            case("05-language", b"mismatch", "abstain_form", "language_mismatch", evidence_kind="mismatched", evidence_trust="mismatched", agreement="disagrees"),
            case("06-missing", b"missing", "abstain_form", "missing_language_declaration", language=None, evidence_kind="missing", evidence_trust="missing", agreement="missing"),
            case("07-untrusted", b"untrusted", "abstain_form", "untrusted_language", language=None, evidence_kind="untrusted", evidence_trust="untrusted", agreement="missing"),
            case("08-non-english", b"bonjour", "abstain_form", "non_english_language", language="fr"),
        )
    )
    anchor = build_bootstrap_trust_anchor(artifacts)

    class _TrustRoot:
        def verify_active_release(self, metadata: BootstrapProfileReleaseMetadata) -> bool:
            return metadata.bootstrap_profile_trust_anchor_digest == anchor.trust_anchor_digest

    return verify_bootstrap_profile(
        HostVerifiedBootstrapMaterial(
            release_metadata=BootstrapProfileReleaseMetadata(
                coordinate=BOOTSTRAP_COORDINATE,
                bootstrap_profile_trust_anchor_digest=anchor.trust_anchor_digest,
                signed_release_digest="1" * 64,
            ),
            trust_anchor=anchor,
            artifact_payloads=serialize_bootstrap_profile_artifacts(artifacts),
            release_evidence=build_test_host_verified_bootstrap_release_evidence(
                metadata=BootstrapProfileReleaseMetadata(
                    coordinate=BOOTSTRAP_COORDINATE,
                    bootstrap_profile_trust_anchor_digest=anchor.trust_anchor_digest,
                    signed_release_digest="1" * 64,
                ),
                external_root_digest="2" * 64,
                active_lifecycle_snapshot_digest="3" * 64,
                verified_at=NOW,
            ),
            authenticated_ingress_resolver=object(),
            profile_enabled=True,
        )
    )


def _validated_test_runtime(
    *,
    admissions,
    atomic_store: SemanticIngestionAtomicStore,
) -> AuthorizedSemanticIngestionRuntime:
    profile = _bootstrap_profile_for_test_runtime()

    class _DeploymentVerifier:
        def verify(self, *, authorization_bytes, use, server_time):
            body = {
                "authorization_digest": sha256(authorization_bytes).hexdigest(),
                "target_profile_manifest_digest": use.profile_manifest_digest,
                "verified_bootstrap_release_digest": use.verified_bootstrap_release_digest,
                "deployment_artifact_digest": sha256(b"test-deployment").hexdigest(),
                "authority_snapshot_digest": sha256(b"test-authority").hexdigest(),
                "active_epoch": 1,
                "expires_at": NOW + timedelta(days=1),
                "signer_id": "test-signer",
            }
            return SemanticIngestionRuntimeAuthorization(
                **body,
                decision_digest=_conflict_digest(
                    b"memorii.semantic-ingestion.verified-deployment-authorization.v1\0",
                    body,
                ),
            )

    runtime = AuthorizedSemanticIngestionRuntime(
        authorization_bytes=b"terminal-test-deployment-authorization",
        authorization_verifier=_DeploymentVerifier(),
        policy_provider=object(),
        writer_admission=admissions,
        atomic_store=atomic_store,
    )
    runtime.validate(profile=profile, server_time=NOW)
    return runtime


class TestSemanticConflictAuthorityResolver:
    """Typed host seam used by core persistence tests, not production composition."""

    def __init__(self, plane: MemoryPlaneService, *, now: datetime = NOW) -> None:
        self._plane = plane
        self._now = now
        authority_body = {
            "authority_record_id": "test-semantic-conflict-authority",
            "tenant_partition_id": "tenant:a",
            "renderer_schema": "test-semantic-conflict-renderer",
            "renderer_policy_fingerprint": sha256(b"test-renderer-policy").hexdigest(),
            "owner_capability_digest": sha256(b"test-host-capability").hexdigest(),
            "status": "active",
            "authority_revision": 1,
            "valid_from": NOW - timedelta(days=1),
            "valid_until": NOW + timedelta(days=365),
            "predecessor_authority_record_digest": None,
        }
        self.authority = SemanticConflictResolverAuthority(
            **authority_body,
            authority_record_digest=_conflict_digest(
                b"memorii.semantic-conflict-resolver-authority.v1\0",
                authority_body,
            ),
        )
        pointer_body = {
            "tenant_partition_id": self.authority.tenant_partition_id,
            "renderer_schema": self.authority.renderer_schema,
            "authority_record_id": self.authority.authority_record_id,
            "authority_record_digest": self.authority.authority_record_digest,
            "pointer_revision": 1,
            "predecessor_pointer_digest": None,
        }
        self.pointer = ActiveSemanticConflictResolverAuthority(
            **pointer_body,
            pointer_digest=_conflict_digest(
                b"memorii.semantic-conflict-resolver-pointer.v1\0", pointer_body
            ),
        )

    def install(self, admissions, administration_grant) -> None:
        SemanticConflictResolverAuthorityRepository(
            self._plane,
            admissions,
            administration_capability=administration_grant,
            now_provider=lambda: self._now,
        ).install(
            authority=self.authority,
            pointer=self.pointer,
            capability=administration_grant,
        )

    def resolve_semantic_conflicts(
        self,
        requests: tuple[SemanticConflictAuthorityResolutionRequest, ...],
    ) -> tuple[SemanticConflictAuthorityResolution, ...]:
        resolutions = []
        for request in requests:
            options = tuple(
                ConflictResolutionOption(
                    candidate_id=candidate_id,
                    label=f"Candidate {candidate_id}",
                    statement=f"Choose {candidate_id}",
                    candidate_digest=candidate_digest,
                )
                for candidate_id, candidate_digest in request.contest_key.candidate_set
            )
            display_body = {
                "renderer_schema": self.authority.renderer_schema,
                "renderer_policy_fingerprint": self.authority.renderer_policy_fingerprint,
                "authority_record_id": self.authority.authority_record_id,
                "authority_revision": self.authority.authority_revision,
                "authority_record_digest": self.authority.authority_record_digest,
                "authority_pointer_digest": self.pointer.pointer_digest,
                "authority_valid_until": self.authority.valid_until,
                "question": "Which candidate should be retained?",
                "options": options,
                "rendered_item_utf8_bytes": semantic_conflict_rendered_item_utf8_bytes(
                    conflict_id="a" * 64,
                    question="Which candidate should be retained?",
                    options=options,
                ),
                "embedded_page_budget_utf8_bytes": 8192,
            }
            display = SemanticConflictDisplayBinding(
                **display_body,
                display_digest=_conflict_digest(
                    b"memorii.semantic-conflict-display.v1\0", display_body
                ),
            )
            resolution_body = {
                "contest_key": request.contest_key,
                "scope": request.scope,
                "display": display,
                "resolver_authority_record": self.authority,
                "resolver_authority_pointer": self.pointer,
            }
            resolutions.append(
                SemanticConflictAuthorityResolution(
                    **resolution_body,
                    resolution_digest=_conflict_digest(
                        b"memorii.semantic-conflict-authority-resolution.v1\0",
                        resolution_body,
                    ),
                )
            )
        return tuple(resolutions)


def install_test_semantic_conflict_authority_resolver(
    plane: MemoryPlaneService,
    admissions,
    atomic_store: SemanticIngestionAtomicStore,
    *,
    resolver: TestSemanticConflictAuthorityResolver | None = None,
) -> TestSemanticConflictAuthorityResolver:
    resolver = resolver or TestSemanticConflictAuthorityResolver(plane)
    runtime = _validated_test_runtime(admissions=admissions, atomic_store=atomic_store)
    resolver.install(admissions, runtime.conflict_authority_administration_grant())
    return resolver


def handoff(
    plane: MemoryPlaneService,
    *,
    coordinate: str = "one",
    scope_ids: frozenset[str] = frozenset(),
    atomic_store: SemanticIngestionAtomicStore | None = None,
    writer_binding: SemanticWriterCommitBinding | None = None,
) -> tuple[SourceAdmissionAccepted, OperationFenceBinding]:
    if (atomic_store is None) != (writer_binding is None):
        raise ValueError("atomic store and writer binding must be supplied together")
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:a",
        tenant_partition_id="tenant:a",
        provider_identity="provider:test",
    )
    identity = DeliveryIdentity.create(principal, f"delivery:{coordinate}")
    source = CanonicalMemoryRecord(
        memory_id=f"tx:{coordinate}",
        domain=MemoryDomain.TRANSCRIPT,
        text="source",
        content={"text": "source"},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_source",
        timestamp=NOW,
        is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    scopes = RequiredOutcomeScopeSet.create(
        tenant_partition_id="tenant:a", scopes=scope_ids
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=scopes,
        current_authorized_scopes=scopes,
    )
    admission_service = GovernedSourceAdmissionService(plane)
    if atomic_store is None or writer_binding is None:
        admission = admission_service.admit(
            source=source,
            delivery_identity=identity,
            ingress=ingress,
            operation_id=f"op:{coordinate}",
            evidence_only=True,
        )
    else:
        prepared = admission_service.prepare_atomic(
            source=source,
            delivery_identity=identity,
            ingress=ingress,
            operation_id=f"op:{coordinate}",
            evidence_only=True,
        )
        atomic_store.admit_source(
            prepared=prepared,
            writer_binding=writer_binding,
        )
        admission = prepared.accepted
    return admission, OperationFenceBinding.create(
        operation_id=f"op:{coordinate}",
        source_id=admission.source_id,
        source_digest=admission.source_digest,
        delivery_identity=identity,
    )


def accepted_terminal(
    *,
    operation_id: str,
    source_text: str = SOURCE,
    source_id: str | None = None,
    source_digest: str | None = None,
    subject_logical_entity_id: str = "entity:atlas",
    subject_entity_revision_id: str = "entity-revision:atlas:v1",
    object_logical_entity_id: str = "entity:memorii",
    object_entity_revision_id: str = "entity-revision:memorii:v1",
    authority_class: str = "official",
    eligible_authority_classes: frozenset[str] | None = None,
    authority_rank_by_class: Mapping[str, int] | None = None,
    decay_schedule_by_class: Mapping[str, tuple[TrustDecayStep, ...]] | None = None,
    valid_start: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    valid_end: datetime | None = datetime(2026, 2, 1, tzinfo=UTC),
    atemporal: bool = False,
    temporal_requirement: Literal["required", "optional", "atemporal"] | None = None,
    allow_reference_as_effective_start: bool = False,
    reference_instant: datetime | None = None,
    state_cardinality: Literal["single", "multi"] = "single",
    operation_kind: Literal[
        "fact", "correction", "retraction", "identity"
    ] = "fact",
    identity_lineage_compiler=None,
    identity_operation_planner=None,
    operation_fence: OperationFenceBinding | None = None,
):
    if source_id is None:
        if operation_id.startswith("op:"):
            coordinate = operation_id.removeprefix("op:")
            source_record = CanonicalMemoryRecord(
                memory_id=f"tx:{coordinate}",
                domain=MemoryDomain.TRANSCRIPT,
                text="source",
                content={"text": "source"},
                status=CommitStatus.COMMITTED,
                source_kind="semantic_ingestion_source",
                timestamp=NOW,
                is_raw_event=True,
                visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
            )
            source_id = source_record.memory_id
            source_digest = source_digest or source_admission_source_digest(source_record)
        else:
            source_id = SOURCE_ID
    source_digest = source_digest or sha256(source_text.encode()).hexdigest()
    eligible_authority_classes = eligible_authority_classes or frozenset({authority_class})
    authority_rank_by_class = authority_rank_by_class or {authority_class: 10}
    temporal_requirement = temporal_requirement or (
        "atemporal" if atemporal else "required"
    )
    interval = (
        None
        if atemporal or reference_instant is not None
        else TimeInterval(start=valid_start, end=valid_end)
    )
    effective = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2027, 1, 1, tzinfo=UTC),
    )
    authority = SourceAuthorityEvidence.create(
        source_id=source_id,
        source_digest=source_digest,
        authority=SourceAuthority(
            authority_class=authority_class,
            authenticated_provenance_class="host",
            policy_revision="trust-r1",
        ),
        provenance_digest=sha256(f"source-authority:{source_id}:{authority_class}".encode()).hexdigest(),
    )
    interval_evidence = (
        AuthenticatedSourceIntervalEvidence.create(
            source_id=source_id,
            source_digest=source_digest,
            interval=interval,
            authority_basis="server_source_metadata",
            provenance_digest=sha256(f"source-interval:{source_id}".encode()).hexdigest(),
            policy_revision="trust-r1",
            source_authority_evidence_digest=authority.evidence_digest,
        )
        if interval is not None
        else None
    )
    policy = SemanticArbitrationPolicyBundle.create(
        trust_policy=TrustPolicySnapshot.create(
            policy_revision="trust-r1",
            system_effective_interval=effective,
            rules=(
                PredicateTrustRule(
                    predicate_id="works_for",
                    eligible_authority_classes=eligible_authority_classes,
                    authority_rank_by_class=authority_rank_by_class,
                    decay_schedule_by_class=decay_schedule_by_class or {},
                ),
            ),
        ),
        temporal_policy=TemporalPolicySnapshot.create(
            policy_revision="temporal-r1",
            system_effective_interval=effective,
            rules=(
                PredicateTemporalRule(
                    predicate_id="works_for",
                    valid_time_requirement=temporal_requirement,
                    allow_open_end=temporal_requirement != "atemporal",
                    allow_reference_as_effective_start=(
                        allow_reference_as_effective_start
                    ),
                ),
            ),
        ),
        arbitration_as_of=datetime(2026, 3, 1, tzinfo=UTC),
    )

    class Authorization:
        def current_read_set(self, *, policy_bundle, egress_policy_revision, egress_decision_digest, use_point):
            del egress_policy_revision, egress_decision_digest, use_point
            return SemanticAuthorizationReadSet.create(
                policy_bundle=policy_bundle,
                deployment_authorization_digest="d" * 64,
                deployment_active_epoch=1,
                deployment_decision_digest="e" * 64,
            )

    base_analyzer = ProductionLocalSemanticAnalyzer()
    claim_identity = AcceptedClaimIdentity(
        subject_assertion_ref=ImmutableAssertionEntityRef(
            entity_revision_id=subject_entity_revision_id,
            logical_entity_id_at_assertion=subject_logical_entity_id,
        ),
        object_assertion_ref=ImmutableAssertionEntityRef(
            entity_revision_id=object_entity_revision_id,
            logical_entity_id_at_assertion=object_logical_entity_id,
        ),
        assertion_key_at_recording=SemanticAssertionKey(
            slot=SemanticClaimSlotKey(
                subject_logical_entity_id=subject_logical_entity_id,
                predicate_id="works_for",
                scope_identity="asserted:speaker",
                qualifier_partition=(),
            ),
            value=SemanticClaimValueKey(
                object_kind="entity",
                object_logical_entity_id=object_logical_entity_id,
                value_policy_fingerprint=sha256(b"memorii.test.entity-value-policy.v1").hexdigest(),
            ),
        ),
        predicate_state_rule=PredicateStateRule(
            predicate_id="works_for",
            cardinality=state_cardinality,
            conflict_behavior=(
                "compete_within_slot" if state_cardinality == "single" else "accumulate_distinct_values"
            ),
            qualifier_partition_fields=(),
            value_identity_policy_id="memorii.test.entity-identity.v1",
            policy_fingerprint=sha256(
                (f"memorii.test.works-for-state-policy.v1:{state_cardinality}").encode()
            ).hexdigest(),
        ),
        identity_lineage_snapshot_digest=sha256(b"memorii.test.identity-lineage-snapshot.v1").hexdigest(),
    )

    class TypedAnalyzer:
        def propose(self, **values):
            proposals = base_analyzer.propose(**values)
            if operation_kind == "fact":
                return proposals
            return tuple(
                proposal.model_copy(update={"operation_kind": operation_kind})
                for proposal in proposals
            )

        def analyze(self, **values):
            # The pipeline supplies the current prepared source after its exact
            # repository lookup.  Delegate with that authority rather than
            # reconstructing an independent analysis fixture per terminal.
            analysis_values = dict(values)
            if operation_kind != "fact":
                analysis_values["proposal"] = values["proposal"].model_copy(
                    update={"operation_kind": "fact"}
                )
            analysis = base_analyzer.analyze(**analysis_values)
            assert analysis is not None
            temporal_evidence = analysis.temporal_evidence
            if operation_kind in {"identity", "retraction"}:
                temporal_evidence = tuple(
                    item.model_copy(update={"temporal_role": "transition"})
                    for item in temporal_evidence
                )
            elif operation_kind == "correction":
                temporal_evidence = tuple(
                    item.model_copy(update={"temporal_role": role})
                    for role in ("replacement", "transition")
                    for item in temporal_evidence
                )
            if reference_instant is not None:
                reference = AuthenticatedEventTimeReference.create(
                    reference_instant=reference_instant,
                    authority_basis="server_event_metadata",
                    provenance_digest=sha256(
                        f"event-reference:{reference_instant.isoformat()}".encode()
                    ).hexdigest(),
                )
                temporal_evidence = tuple(
                    item.model_copy(update={"reference_evidence": reference})
                    for item in temporal_evidence
                )
            body = analysis.model_dump(mode="python", exclude={"analysis_digest"}) | {
                "operation_kind": operation_kind,
                "temporal_evidence": temporal_evidence,
            }
            if operation_kind in {"fact", "correction"}:
                body["claim_identity"] = claim_identity
            return IndependentSourceAnalysis.create(**body)

    analyzer = TypedAnalyzer()
    # Direct terminal construction mirroring the retired pipeline's
    # local-proposal path: propose, analyze, resolve temporal evidence by
    # policy rank, seal, compile carriers, and close one terminal outcome.
    read_set = Authorization().current_read_set(
        policy_bundle=policy,
        egress_policy_revision=None,
        egress_decision_digest=None,
        use_point="pre_request",
    )
    prepared_source = _prepared_source_repository(
        source_id=source_id, source_digest=source_digest, source_text=source_text
    ).load(source_id=source_id, source_digest=source_digest)
    assert prepared_source is not None
    candidates = tuple(
        sorted(
            analyzer.propose(
                source_id=source_id, source_digest=source_digest, source_text=source_text
            ),
            key=lambda value: value.candidate_id,
        )
    )
    analyses = []
    for candidate in candidates:
        analysis = analyzer.analyze(
            proposal=candidate,
            source_id=source_id,
            source_digest=source_digest,
            source_text=source_text,
            prepared_source=prepared_source,
            source_authority_evidence=authority,
            source_interval_evidence=interval_evidence,
        )
        assert analysis is not None
        analyses.append(analysis)
    source_analyses = tuple(analyses)
    resolver = TemporalEvidenceResolver()
    role_closures_by_candidate = []
    closure_list = []
    for candidate, analysis in zip(candidates, source_analyses, strict=True):
        resolved_roles = []
        for source_temporal in analysis.temporal_evidence:
            resolved_roles.append(
                (
                    source_temporal.temporal_role,
                    resolver.resolve(
                        predicate_id=candidate.predicate_id,
                        candidates=source_temporal.candidates,
                        reference_evidence=source_temporal.reference_evidence,
                        source_present_attachment=bool(source_temporal.attachment_spans),
                        trust_policy=policy.trust_policy,
                        temporal_policy=policy.temporal_policy,
                        arbitration_as_of=policy.arbitration_as_of,
                    ),
                )
            )
        role_closures = tuple(resolved_roles)
        role_closures_by_candidate.append(role_closures)
        closure_list.extend(closure for _, closure in role_closures)
    closures = tuple(closure_list)
    sealed_values = []
    for candidate, analysis, role_closures in zip(
        candidates, source_analyses, role_closures_by_candidate, strict=True
    ):
        sealed = seal_semantic_operation(
            source_id=source_id,
            source_digest=source_digest,
            candidate=candidate,
            source_analysis=analysis,
            role_closures=role_closures,
        )
        if sealed is not None:
            sealed_values.append(sealed)
    sealed_operations = tuple(
        sorted(sealed_values, key=lambda value: value.candidate_id)
    )
    execution_lineage = SemanticExecutionLineage.create(
        operation_id=operation_id,
        proposal_attempt_digests=(
            contract_digest(
                b"memorii.semantic-ingestion.local-proposal-attempt.v1", candidates
            ),
        ),
        source_analysis_digests=tuple(
            value.analysis_digest for value in source_analyses
        ),
        sealed_operation_digests=tuple(
            value.sealed_operation_digest for value in sealed_operations
        ),
        prompt_authority_digest=None,
        egress_decision_digests=(),
        arbitration_policy_bundle_digest=policy.bundle_digest,
        authorization_read_set_digest=read_set.read_set_digest,
    )
    promotable = bool(candidates) and len(sealed_operations) == len(candidates)
    identity_transitions = {}
    identity_failure = None
    if promotable:
        analysis_by_candidate = {
            value.candidate_id: value for value in source_analyses
        }
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        for operation in sealed_operations:
            if operation.kind != "identity":
                continue
            if identity_lineage_compiler is None:
                identity_failure = "identity_lineage_compiler_required"
                break
            try:
                if identity_operation_planner is not None:
                    if operation_fence is None:
                        raise ValueError("identity operation fence is unavailable")
                    identity_operation_planner.prepare_accepted_identity_operation(
                        operation=operation,
                        candidate=candidate_by_id[operation.candidate_id],
                        source_analysis=analysis_by_candidate[operation.candidate_id],
                        operation_fence=operation_fence,
                        authorization_read_set=read_set,
                    )
                transition = identity_lineage_compiler.compile_transition(
                    operation=operation,
                    candidate=candidate_by_id[operation.candidate_id],
                    source_analysis=analysis_by_candidate[operation.candidate_id],
                )
            except ValueError:
                identity_failure = "identity_lineage_compilation_failed"
                break
            if transition.operation_id != operation.operation_id:
                identity_failure = "identity_lineage_operation_binding_mismatch"
                break
            identity_transitions[operation.operation_id] = transition
        promotable = identity_failure is None
    binding_sets = tuple(
        SemanticTerminalBindingSet.create(
            operation_id=operation.operation_id,
            bindings=operation.temporal_bindings,
        )
        for operation in sorted(sealed_operations, key=lambda value: value.operation_id)
    )
    if not promotable:
        return SemanticTerminalOutcome.create(
            operation_id=operation_id,
            status="unresolved",
            reason_codes=(
                identity_failure or "independent_consensus_or_temporal_resolution_failed",
            ),
            candidates=candidates,
            temporal_closures=closures,
            attempt_count=0,
            source_analyses=source_analyses,
            arbitration_policy_bundle=policy,
            authorization_read_set=read_set,
            execution_lineage=execution_lineage,
            sealed_operations=sealed_operations,
            terminal_binding_sets=binding_sets,
        )
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    carriers = tuple(
        carrier
        for operation in sealed_operations
        for carrier in compile_accepted_carriers(
            operation=operation,
            candidate=candidate_by_id[operation.candidate_id],
            predicate_trust_rule=(
                policy.trust_policy.rule_for(
                    candidate_by_id[operation.candidate_id].predicate_id
                )
                if operation.claim_identity is not None
                else None
            ),
            identity_transition=identity_transitions.get(operation.operation_id),
            committed_at=None,
        )
    )
    carriers = tuple(
        sorted(
            carriers,
            key=lambda value: (value.operation_id, value.record_kind, value.record_digest),
        )
    )
    carrier_artifact_digest = contract_digest(
        b"memorii.semantic-ingestion.terminal-carrier-artifact.v1",
        {
            "operation_id": operation_id,
            "sealed_operations": sealed_operations,
            "accepted_carriers": carriers,
            "terminal_binding_sets": binding_sets,
        },
    )
    return SemanticTerminalOutcome.create(
        operation_id=operation_id,
        status="accepted",
        reason_codes=(),
        candidates=candidates,
        source_analyses=source_analyses,
        arbitration_policy_bundle=policy,
        authorization_read_set=read_set,
        execution_lineage=execution_lineage,
        temporal_closures=closures,
        carrier_artifact_digest=carrier_artifact_digest,
        sealed_operations=sealed_operations,
        accepted_carriers=carriers,
        terminal_binding_sets=binding_sets,
        attempt_count=0,
    )


def zero_effect_terminal(
    *,
    operation_id: str,
    status: Literal["unresolved", "rejected", "evidence_only"] = "unresolved",
    reason_codes: tuple[str, ...] = ("consensus_unresolved",),
) -> SemanticTerminalOutcome:
    """Build a canonical non-committing terminal without graph carriers."""
    accepted = accepted_terminal(operation_id=operation_id)
    return SemanticTerminalOutcome.create(
        operation_id=accepted.operation_id,
        status=status,
        reason_codes=reason_codes,
        candidates=accepted.candidates,
        source_analyses=accepted.source_analyses,
        temporal_closures=(),
        attempt_count=accepted.attempt_count,
    )
