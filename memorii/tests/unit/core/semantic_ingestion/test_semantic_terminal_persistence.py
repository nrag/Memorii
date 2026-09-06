from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from shutil import copytree
from threading import Barrier, Event
from typing import Literal

import pytest
from memorii.core.memory_evolution import graph_planning as graph_planning_module
from memorii.core.memory_evolution.admission import source_admission_source_digest
from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    CommittedGroupAtomicWriteRequest,
    IdentityPlanningMigrationRequiredError,
    NonCommittingGroupAtomicWriteRequest,
    PreplanningStoreError,
    SemanticAuthorizationAuthorityRecord,
    SemanticIngestionAtomicStore,
    SourceCheckpointAtomicWriteRequest,
    _authorization_authority_record,
    _control_from_record,
    generation_request_digest,
)
from memorii.core.memory_evolution.conflict_attention import (
    ActiveSemanticConflict,
    AgentClarificationProposal,
    ClarificationAttemptOutcome,
    ClarificationSubmissionOutcome,
    ConflictAttention,
    ConflictAudience,
    ConflictClarificationAttemptResult,
    ConflictClarificationOperationReceipt,
    ConflictClarificationProcessingReceipt,
    ConflictClarificationWork,
    ConflictKind,
    ConflictResolutionAction,
    ConflictResolutionRequest,
    ConflictStatus,
    SemanticConflictClarificationNonceConsumption,
    SemanticConflictClarificationSubmissionGeneration,
    SemanticConflictClarificationSubmissionOperation,
    SemanticConflictClarificationTransition,
    SemanticConflictClarificationTransitionReason,
    SemanticConflictClarificationWorkGeneration,
    SemanticConflictIntroduction,
    SemanticConflictLedgerHead,
    VerifiedUserConfirmation,
    build_agent_clarification_proposal,
    conflict_clarification_processing_operation_id,
    decode_persisted_conflict_generation,
    verified_user_confirmation_digest,
    verified_user_confirmation_nonce_digest,
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
from memorii.core.memory_evolution.graph_planning import (
    PlanningCommitValues,
    materialize_frozen_identity_graph_plan,
)
from memorii.core.memory_evolution.graph_records import (
    AcceptedIdentityOperationArtifact,
    GraphReadSetExtension,
    GraphWriteIntent,
    PlannedEntityIdentity,
    PlannedIdentityReservation,
    SourceGroundedAliasPayload,
    TrustedAcceptedIdentityOperationDecision,
    VerifiedIdentityDecisionAuthority,
    canonical_graph_codec_manifest,
)
from memorii.core.memory_evolution.identity_lineage import (
    AtomicStoreAcceptedIdentityOperationPlanner,
    AtomicStoreScopedIdentityLineageAuditReader,
    GrantBackedIdentityLineageAuditAuthorizer,
    IdentityLineageAuditGrant,
    ProductionIdentityLineageCompiler,
    derive_total_reverse_reference_closure,
    replay_identity_lineage,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.projection_history import (
    ProjectionCommitRequest,
    ProjectionHistoryError,
    ProjectionHistoryRepository,
    projection_records_from_replay_state,
)
from memorii.core.memory_evolution.reference_integrity import (
    ReferenceTarget,
    validate_reference_integrity_converse,
)
from memorii.core.memory_evolution.retrieval_contracts import (
    GraphAuditRequest,
    RetrievalPurpose,
)
from memorii.core.memory_evolution.semantic_state import (
    AcceptedIdentityOperation,
    ActiveTemporalProjectionPointer,
    GroundedLineageReferenceAssignment,
    LineageEntityIdentity,
    LineageEvidenceReference,
    TemporalProjectionGeneration,
    TemporalProjectionHistoryEntry,
    TemporalProjectionRecord,
    TrustProjectionGeneration,
    projection_contract_digest,
)
from memorii.core.memory_evolution.transaction_coordinator import (
    SealedGraphStateSnapshot,
    SemanticIngestionTransactionCoordinator,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    JsonlMemoryPlaneStore,
    MemoryPlaneRevisionConflictError,
    MemoryPlaneStore,
    _PersistedBatch,
    record_digest,
)
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion import event_replay
from memorii.core.semantic_ingestion.authorization import (
    SemanticAuthorizationAuthorityRepository,
    VerifiedSemanticAuthorizationControlPlane,
    VerifiedSemanticAuthorizationTransition,
)
from memorii.core.semantic_ingestion.contracts import (
    ClaimAssertion,
    SemanticArtifactClosure,
    SemanticEffectGroupResult,
    SemanticGraphDelta,
    SemanticObservationDelta,
    SemanticTerminalOutcome,
    TemporalTransitionRecord,
    TimeInterval,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.core.semantic_ingestion.event_replay import (
    SemanticEventReplayError,
    SemanticReplayCheckpointBundle,
    build_semantic_memory_event_batch,
    decode_semantic_memory_event_batch,
    encode_semantic_memory_event_batch,
    replay_semantic_event_batches,
)
from memorii.core.semantic_ingestion.persistence import SemanticTerminalPersistenceService
from memorii.integrations.hermes_provider import HermesMemoryProvider
from planning_serialized_oracle import materialize_serialized
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import (
    SOURCE_DIGEST,
    SOURCE_ID,
    accepted_terminal,
    handoff,
    install_test_semantic_conflict_authority_resolver,
)
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import (
    TestSemanticConflictAuthorityResolver as _TestSemanticConflictAuthorityResolver,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _assert_live_conflict_replay_binding(store: SemanticIngestionAtomicStore) -> None:
    """The persisted aggregate/checkpoint must bind exactly the live ledger."""

    live = store.projection_history.semantic_conflict_replay_binding()
    aggregate = store.semantic_replay_authority()
    assert aggregate.semantic_conflict_replay_binding == live
    assert aggregate.latest_checkpoint is not None
    assert aggregate.latest_checkpoint.checkpoint.semantic_conflict_replay_binding == live


def _replay_binding_records(plane: MemoryPlaneService) -> tuple[CanonicalMemoryRecord, ...]:
    """Return the immutable replay records whose bytes must not change for queue work."""

    return tuple(
        record
        for record in plane.list_records()
        if record.source_kind
        in {
            "semantic_ingestion_replay_authority",
            "semantic_ingestion_checkpoint_lifecycle",
        }
    )


class _CurrentAuthorization:
    def verify_current(self, read_set, *, use_point: str) -> bool:
        return use_point == "pre_commit"


AUTHORIZATION = _CurrentAuthorization()


class _StoreIdentityDecisionAuthorityVerifier:
    def verify_identity_decision_authority(self, decision):
        return VerifiedIdentityDecisionAuthority.create(
            decision_digest=decision.decision_digest,
            sealed_operation_digest=decision.sealed_operation_digest,
            candidate_digest=decision.candidate_digest,
            source_analysis_digest=decision.source_analysis_digest,
            operation_fence_binding_digest=decision.operation_fence_binding_digest,
            graph_snapshot_digest=decision.graph_snapshot_digest,
            graph_read_set_digest=decision.graph_read_set_digest,
            authority_record_id="identity-authority:test",
            authority_record_digest="b" * 64,
            verifier_id="test-verifier",
        )


IDENTITY_AUTHORITY_VERIFIER = _StoreIdentityDecisionAuthorityVerifier()


class _StaleAuthorization:
    def verify_current(self, read_set, *, use_point: str) -> bool:
        return False


class _RotateInsideStoreAuthorization:
    def __init__(self) -> None:
        self.reads = 0

    def verify_current(self, read_set, *, use_point: str) -> bool:
        self.reads += 1
        return use_point == "pre_commit" and self.reads < 3


def _setup(
    *,
    verified: bool,
    backend: MemoryPlaneStore | None = None,
    now_provider=lambda: NOW,
    scope_ids: frozenset[str] = frozenset(),
    with_test_conflict_authority: bool = False,
    conflict_resolver_factory: Callable[[MemoryPlaneService], _TestSemanticConflictAuthorityResolver] | None = None,
    semantic_integrity_lifecycle: PrivilegedSemanticIntegrityLifecycle | None = None,
):
    plane = MemoryPlaneService(record_store=backend) if backend is not None else MemoryPlaneService()
    admission, fence = handoff(plane, scope_ids=scope_ids)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=now_provider)
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="semantic-ingestion",
            writer_implementation_fingerprint="writer",
            graph_schema_fingerprint="schema",
        )
    )
    if verified:
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
            plan, checkpoint, independent_verifier_fingerprint="semantic-ingestion-verifier"
        )
        activation = activate_migration(plan, certificate)
        binding = writers.commit_binding(
            writers.transition(
                expected=binding,
                admission_id="semantic-ingestion:verified",
                runtime_mode="verified_semantic",
                writer_implementation_fingerprint="writer:verified",
                graph_schema_fingerprint="schema",
                migration_activation=activation,
                migration_plan=plan,
                migration_checkpoint=checkpoint,
                migration_certificate=certificate,
                target_records=(),
            )
        )
    conflict_resolver = (
        (conflict_resolver_factory(plane) if conflict_resolver_factory is not None else _TestSemanticConflictAuthorityResolver(plane))
        if with_test_conflict_authority
        else None
    )
    store = SemanticIngestionAtomicStore(
        plane,
        writers,
        now_provider=now_provider,
        semantic_freeze_guard=(
            semantic_integrity_lifecycle.freeze_guard if semantic_integrity_lifecycle is not None else None
        ),
        semantic_integrity_incident_reporter=(
            semantic_integrity_lifecycle.incident_reporter if semantic_integrity_lifecycle is not None else None
        ),
        semantic_integrity_linearization=(
            semantic_integrity_lifecycle.linearization if semantic_integrity_lifecycle is not None else None
        ),
        identity_decision_authority_verifier=IDENTITY_AUTHORITY_VERIFIER,
        semantic_conflict_authority_resolver=conflict_resolver,
    )
    if conflict_resolver is not None:
        install_test_semantic_conflict_authority_resolver(
            plane,
            writers,
            store,
            resolver=conflict_resolver,
        )
    store._publish_preplanning(admission=admission, writer_binding=binding)
    repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        now_provider=now_provider,
    )
    service = SemanticTerminalPersistenceService(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        authorization_repository=repository,
    )
    return plane, writers, store, binding, fence, service, repository


def _activate(repository, fence, terminal, *, valid_until=None) -> None:
    assert terminal.authorization_read_set is not None
    repository.observe_verified(
        authority_scope_id=repository.scope_id(source_id=fence.source_id, source_digest=fence.source_digest),
        read_set=terminal.authorization_read_set,
        valid_until=valid_until or datetime(2030, 1, 1, tzinfo=UTC),
    )


def _nonaccepted(
    operation_id: str,
    *,
    status: Literal["unresolved", "rejected", "evidence_only"] = "unresolved",
    reason_codes: tuple[str, ...] = ("consensus_unresolved",),
) -> SemanticTerminalOutcome:
    return SemanticTerminalOutcome.create(
        operation_id=operation_id,
        status=status,
        reason_codes=reason_codes,
        candidates=(),
        temporal_closures=(),
        attempt_count=1,
    )


def _direct_terminal_checkpoint_request(
    *,
    store: SemanticIngestionAtomicStore,
    binding,
    fence,
    terminal: SemanticTerminalOutcome,
) -> SourceCheckpointAtomicWriteRequest:
    control = store.acquire_lease(
        operation_fence=fence,
        writer_binding=binding,
        execution_token=f"semantic-ingestion:{fence.operation_fence_id}",
        owner_id="semantic-ingestion-pipeline",
        duration=timedelta(minutes=5),
    )
    closure = SemanticArtifactClosure.create(terminal)
    checkpoint = SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=fence,
        operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding,
        expected_operation_generation=control.generation,
        expected_artifact_generation=control.generation,
        members=SemanticTerminalPersistenceService._checkpoint_members(
            terminal,
            closure,
            binding,
        ),
        required_artifact_digests=(),
        request_digest="0" * 64,
        progress_state="planned",
    )
    checkpoint = checkpoint.model_copy(
        update={"request_digest": generation_request_digest(checkpoint)}
    )
    return checkpoint


def _direct_noncommitting_group_request(
    *,
    store: SemanticIngestionAtomicStore,
    binding,
    fence,
    terminal: SemanticTerminalOutcome,
) -> NonCommittingGroupAtomicWriteRequest:
    control = store.get_operation(fence)
    closure = SemanticArtifactClosure.create(terminal)
    group_result = SemanticEffectGroupResult.create(
        terminal=terminal,
        artifact_closure=closure,
    )
    observation = SemanticObservationDelta.create(
        terminal=terminal,
        graph_delta=None,
    )
    request = NonCommittingGroupAtomicWriteRequest(
        operation_fence_binding=fence,
        operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding,
        expected_operation_generation=control.generation,
        expected_artifact_generation=control.generation,
        members=SemanticTerminalPersistenceService._noncommitting_group_members(
            terminal,
            closure,
            group_result,
            observation,
        ),
        required_artifact_digests=(),
        request_digest="0" * 64,
        expected_observation_revision=control.observation_revision,
        observation_revision_after=SemanticTerminalPersistenceService._next_revision(
            b"memorii.semantic-ingestion.observation-revision.v1",
            control.observation_revision,
            terminal.terminal_digest,
        ),
    )
    return request.model_copy(
        update={"request_digest": generation_request_digest(request)}
    )


def _direct_noncommitting_request(
    *,
    store: SemanticIngestionAtomicStore,
    binding,
    fence,
    terminal: SemanticTerminalOutcome,
) -> NonCommittingGroupAtomicWriteRequest:
    checkpoint = _direct_terminal_checkpoint_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    )
    store.checkpoint_source_progress(checkpoint)
    return _direct_noncommitting_group_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    )


def _direct_committed_request(
    *,
    store: SemanticIngestionAtomicStore,
    binding,
    fence,
    terminal: SemanticTerminalOutcome,
    authorization_repository,
) -> CommittedGroupAtomicWriteRequest:
    checkpoint = _direct_terminal_checkpoint_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    )
    store.checkpoint_source_progress(checkpoint)
    control = store.get_operation(fence)
    closure = SemanticArtifactClosure.create(terminal)
    group_result = SemanticEffectGroupResult.create(
        terminal=terminal,
        artifact_closure=closure,
    )
    graph_delta = SemanticGraphDelta.create(terminal)
    observation = SemanticObservationDelta.create(
        terminal=terminal,
        graph_delta=graph_delta,
    )
    graph_revision_after = SemanticTerminalPersistenceService._next_revision(
        b"memorii.semantic-ingestion.graph-revision.v1",
        control.graph_revision,
        graph_delta.delta_digest,
    )
    event_batch = store.prepare_semantic_event_batch(
        graph_delta=graph_delta,
        operation_fence=fence,
        writer_binding=binding,
        graph_revision_before=control.graph_revision,
        graph_revision_after=graph_revision_after,
    )
    assert terminal.authorization_read_set is not None
    authorization_precondition = authorization_repository.require_current(
        authority_scope_id=authorization_repository.scope_id(
            source_id=fence.source_id,
            source_digest=fence.source_digest,
        ),
        read_set=terminal.authorization_read_set,
    )
    request = CommittedGroupAtomicWriteRequest(
        operation_fence_binding=fence,
        operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding,
        expected_operation_generation=control.generation,
        expected_artifact_generation=control.generation,
        members=SemanticTerminalPersistenceService._committed_group_members(
            terminal,
            closure,
            group_result,
            graph_delta,
            event_batch,
            observation,
        ),
        required_artifact_digests=(),
        request_digest="0" * 64,
        expected_observation_revision=control.observation_revision,
        observation_revision_after=SemanticTerminalPersistenceService._next_revision(
            b"memorii.semantic-ingestion.observation-revision.v1",
            control.observation_revision,
            terminal.terminal_digest,
        ),
        expected_graph_revision=control.graph_revision,
        expected_effective_read_set_digest=control.effective_read_set_digest,
        graph_revision_after=graph_revision_after,
        authorization_precondition=authorization_precondition,
    )
    return request.model_copy(
        update={"request_digest": generation_request_digest(request)}
    )


def _with_claim_record_version(
    terminal: SemanticTerminalOutcome,
    *,
    record_version: int,
) -> SemanticTerminalOutcome:
    assert len(terminal.accepted_carriers) == 1
    carrier = terminal.accepted_carriers[0]
    assert isinstance(carrier, ClaimAssertion)
    carrier_body = carrier.model_dump(
        mode="python",
        exclude={"record_digest"},
    ) | {"record_version": record_version}
    revised_carrier = ClaimAssertion(
        **carrier_body,
        record_digest=contract_digest(
            b"memorii.semantic-ingestion.temporal-carrier.v1",
            carrier_body,
        ),
    )
    carrier_artifact_digest = contract_digest(
        b"memorii.semantic-ingestion.terminal-carrier-artifact.v1",
        {
            "operation_id": terminal.operation_id,
            "sealed_operations": terminal.sealed_operations,
            "accepted_carriers": (revised_carrier,),
            "terminal_binding_sets": terminal.terminal_binding_sets,
        },
    )
    return SemanticTerminalOutcome.create(
        operation_id=terminal.operation_id,
        status=terminal.status,
        reason_codes=terminal.reason_codes,
        candidates=terminal.candidates,
        source_analyses=terminal.source_analyses,
        arbitration_policy_bundle=terminal.arbitration_policy_bundle,
        authorization_read_set=terminal.authorization_read_set,
        execution_lineage=terminal.execution_lineage,
        temporal_closures=terminal.temporal_closures,
        carrier_artifact_digest=carrier_artifact_digest,
        sealed_operations=terminal.sealed_operations,
        accepted_carriers=(revised_carrier,),
        terminal_binding_sets=terminal.terminal_binding_sets,
        attempt_count=terminal.attempt_count,
    )


def _accepted_clarification_inputs(
    processing_operation_id: str,
    *,
    record_version: int = 1,
):
    request = ConflictResolutionRequest(
        conflict_id="conflict",
        expected_conflict_revision=sha256(b"conflict-revision").hexdigest(),
        operation_id="user-resolution-operation",
        action=ConflictResolutionAction.SELECT,
        selected_candidate_ids=("globex",),
        validity_intervals=(),
        source_user_event_id=SOURCE_ID,
    )
    proposal = build_agent_clarification_proposal(
        request,
        source_user_event_digest=SOURCE_DIGEST,
        agent_principal_id="principal",
        scope_digest=sha256(b"scope").hexdigest(),
    )
    terminal = accepted_terminal(operation_id=processing_operation_id)
    if record_version != 1:
        terminal = _with_claim_record_version(
            terminal,
            record_version=record_version,
        )
    return (
        proposal,
        terminal,
        sha256(b"resolved-conflict-revision").hexdigest(),
        sha256(b"clarification-policy").hexdigest(),
    )


def _json_round_tripped(
    records: tuple[CanonicalMemoryRecord, ...],
) -> tuple[CanonicalMemoryRecord, ...]:
    """Normalize records through one JSON round trip before equality.

    Durable stores return JSON-parsed content (lists); in-memory records keep
    Python tuples.  Record equality across a reopen must compare the durable
    representation, not the in-memory container types.
    """
    import json as _json

    return tuple(
        CanonicalMemoryRecord.model_validate(
            _json.loads(_json.dumps(record.model_dump(mode="json")))
        )
        for record in records
    )


def _assert_retry_returns_committed_receipt(
    result: ConflictClarificationProcessingReceipt | ConflictClarificationAttemptResult,
    receipt: ConflictClarificationProcessingReceipt,
) -> None:
    """A lost-ack retry returns the receipt or its terminal attempt result.

    The declared commit return is the union: the idempotent replay returns the
    persisted receipt itself, while a retry over a superseded claimed image
    returns the terminal attempt result, which binds the same committed
    receipt through its downstream receipt digest.
    """
    if isinstance(result, ConflictClarificationProcessingReceipt):
        assert result == receipt
    else:
        assert result.downstream_receipt_digest == receipt.receipt_digest


def _conflict_pointer_sits_at_introduction(
    plane: MemoryPlaneService, introduction: SemanticConflictIntroduction
) -> bool:
    """The conflict is still open at its introduction record."""

    pointer_record = plane.get_record(
        f"semantic_ingestion:conflict-authority:pointer:{introduction.conflict_id}"
    )
    if pointer_record is None:
        return False
    pointer = ActiveSemanticConflict.model_validate(
        decode_typed_value(bytes.fromhex(str(pointer_record.content["canonical_hex"])))
    )
    return (
        pointer.current_record_digest == introduction.introduction_digest
        and pointer.current_conflict_revision == introduction.conflict_revision
    )


def _claim_canonical_clarification(
    store: SemanticIngestionAtomicStore,
    processing_operation_id: str,
    *,
    plane: MemoryPlaneService,
    service,
    authorization_repository,
    owner_token: str = "canonical-clarification-owner",
    terminal_kwargs: dict | None = None,
):
    """Introduce one real contest and return its claimed work and CAS input.

    Persists two contested terminals, submits the canonical clarification for
    the introduction they create, claims it, and builds the canonical CAS
    input.  The claim derives its own processing operation id; the caller's
    identifier only seeds the durable handoff coordinates.
    """
    binding = store._writers.commit_binding(store._writers.current())
    _, contested_fence = handoff(
        plane,
        coordinate=f"canonical-clarification-{processing_operation_id[:12]}",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=binding,
    )
    # Isolate the contest on its own subject slot and keep both claims on the
    # default valid window: the contest then materializes exactly ONE
    # head-adjacent introduction whose partition is that whole window, and the
    # accepted answer's projection lands on the same partition.  Sharing the
    # default subject slot with unrelated retained claims lets their
    # corroboration tilt the arbitration, resolving the clarified conflict by
    # projection and colliding with the lifecycle closure's own pointer.
    first = accepted_terminal(
        operation_id=contested_fence.operation_id,
        subject_logical_entity_id="entity:clarification",
        subject_entity_revision_id="entity-revision:clarification:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
        **(terminal_kwargs or {}),
    )
    _activate(authorization_repository, contested_fence, first)
    service.persist(fence=contested_fence, terminal=first, authorization_verifier=AUTHORIZATION)
    _, second_fence = handoff(
        plane,
        coordinate=f"canonical-clarification-contest-{processing_operation_id[:12]}",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=binding,
    )
    contested = accepted_terminal(
        operation_id=second_fence.operation_id,
        subject_logical_entity_id="entity:clarification",
        subject_entity_revision_id="entity-revision:clarification:v1",
        object_logical_entity_id="entity:initech",
        object_entity_revision_id="entity-revision:initech:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
        **(terminal_kwargs or {}),
    )
    _activate(authorization_repository, second_fence, contested)
    service.persist(fence=second_fence, terminal=contested, authorization_verifier=AUTHORIZATION)
    # A contest materializes one introduction per contested partition and may
    # resolve earlier ones by projection in the same persist.  Select the
    # conflict whose active pointer still sits at its introduction; deriving
    # coordinates from any other (already closed) introduction is stale.
    introduction = next(
        candidate
        for candidate in (
            SemanticConflictIntroduction.model_validate(
                decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"])))
            )
            for record in plane.list_records(
                source_kind="semantic_ingestion_conflict_authority"
            )
            if record.memory_id.startswith(
                "semantic_ingestion:conflict-authority:introduction:"
            )
        )
        if _conflict_pointer_sits_at_introduction(plane, candidate)
    )
    # The clarification must bind the CONTESTED handoff's admitted source: the
    # accepted answer supersedes that side's contested claim (same source) and
    # materializes a fresh introduction, leaving one active pointer per
    # conflict.  Binding the first handoff's source instead supersedes the
    # first claim, which resolves the clarified conflict by projection and
    # collides with the lifecycle closure's own pointer in one batch.
    clarification_source = plane.get_record(
        f"tx:canonical-clarification-contest-{processing_operation_id[:12]}"
    )
    assert clarification_source is not None
    submission_operation_id = f"canonical-clarification-{processing_operation_id[:12]}"
    submission_request = ConflictResolutionRequest(
        conflict_id=introduction.conflict_id,
        expected_conflict_revision=introduction.conflict_revision,
        operation_id=submission_operation_id,
        action=ConflictResolutionAction.NEITHER,
        selected_candidate_ids=(),
        validity_intervals=(),
        source_user_event_id=clarification_source.memory_id,
    )
    submission_proposal = build_agent_clarification_proposal(
        submission_request,
        source_user_event_digest=source_admission_source_digest(clarification_source),
        agent_principal_id="clarification-principal",
        scope_digest=introduction.scope.scope_digest,
    )
    # Submit through the canonical door: it derives the submitted transition's
    # immutable coordinate and pointer successor from the live ledger state,
    # which sibling contests in the same plane may already have advanced.
    submitted_result = store.submit_canonical_conflict_clarification(
        request=submission_request,
        request_digest=submission_proposal.request_digest,
        proposal=submission_proposal,
        verified_confirmation=None,
    )
    assert submitted_result.outcome is ClarificationSubmissionOutcome.SUBMITTED
    assert submitted_result.operation_receipt is not None
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token=owner_token
    )
    assert claim is not None
    return claim, store.build_conflict_clarification_cas_input(claim)


def _commit_claimed_accepted_clarification(
    store: SemanticIngestionAtomicStore,
    claim,
    cas,
    *,
    record_version: int = 1,
    terminal_kwargs: dict | None = None,
):
    """Commit the accepted answer for an already-claimed canonical work."""
    terminal_values = dict(terminal_kwargs or {})
    terminal_values.setdefault(
        "subject_logical_entity_id", "entity:clarification"
    )
    terminal_values.setdefault(
        "subject_entity_revision_id", "entity-revision:clarification:v1"
    )
    terminal = accepted_terminal(
        operation_id=claim.work.processing_operation_id,
        source_id=claim.proposal.source_user_event_id,
        source_digest=claim.proposal.source_user_event_digest,
        **terminal_values,
    )
    terminal = _with_claim_record_version(
        terminal, record_version=max(record_version, 2)
    )
    receipt = store.commit_conflict_clarification_transaction(
        proposal=claim.proposal,
        processing_operation_id=claim.work.processing_operation_id,
        resulting_conflict_revision=sha256(b"resolved-conflict-revision").hexdigest(),
        policy_fingerprint=claim.work.policy_fingerprint,
        committed_outcome="accepted",
        semantic_result_digest=terminal.terminal_digest,
        semantic_terminal=terminal,
        clarification_cas=cas,
    )
    return receipt, terminal, claim.work.processing_operation_id


def _commit_accepted_clarification(
    store: SemanticIngestionAtomicStore,
    processing_operation_id: str,
    *,
    plane: MemoryPlaneService,
    service,
    authorization_repository,
    record_version: int = 1,
    owner_token: str = "canonical-clarification-owner",
    terminal_kwargs: dict | None = None,
):
    """Drive one accepted clarification commit through the real claim lifecycle.

    Introduces a real contest, submits the canonical clarification, claims it,
    and commits through the canonical CAS.  Returns the receipt/attempt
    result, the committed terminal, and the canonical processing operation id
    (which the claim derives, not the caller).
    """
    claim, cas = _claim_canonical_clarification(
        store,
        processing_operation_id,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
        owner_token=owner_token,
    )
    return _commit_claimed_accepted_clarification(
        store,
        claim,
        cas,
        record_version=record_version,
        terminal_kwargs=terminal_kwargs,
    )






def _projection_generations(
    plane: MemoryPlaneService,
    *,
    kind: str,
):
    model = TemporalProjectionGeneration if kind == "temporal" else TrustProjectionGeneration
    return tuple(
        model.model_validate(decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))))
        for record in plane.list_records(source_kind=f"semantic_projection_{kind}_generation")
    )


def _projection_authority_value(record: CanonicalMemoryRecord, model):
    return model.model_validate(decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))))


def _projection_authority_record(
    record: CanonicalMemoryRecord,
    value,
) -> CanonicalMemoryRecord:
    raw = encode_typed_value(value.model_dump(mode="python"))
    return record.model_copy(
        update={
            "content": {
                "projection_authority_kind": record.content["projection_authority_kind"],
                "canonical_hex": raw.hex(),
                "authority_digest": sha256(raw).hexdigest(),
            }
        }
    )


def _rewrite_jsonl_snapshot(
    backend: JsonlMemoryPlaneStore,
    plane: MemoryPlaneService,
    *,
    replacements: tuple[CanonicalMemoryRecord, ...] = (),
    deleted_ids: tuple[str, ...] = (),
) -> None:
    records = {record.memory_id: record for record in plane.list_records()}
    for memory_id in deleted_ids:
        del records[memory_id]
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


def _clarification_transition(
    *,
    introduction: SemanticConflictIntroduction,
    predecessor_digest: str,
    predecessor_revision: str,
    predecessor_status: ConflictStatus,
    status: ConflictStatus,
    reason: SemanticConflictClarificationTransitionReason,
    record_coordinate: int,
    transition_coordinate: int | None = None,
    successor_conflict_revision: str | None = None,
    proposal_digest: str | None = None,
    processing_operation_id: str | None = None,
) -> SemanticConflictClarificationTransition:
    """Build a closed lifecycle edge without bypassing its typed contract."""

    attention = ConflictAttention(
        conflict_id=introduction.conflict_id,
        conflict_revision=sha256(
            f"clarification:{reason.value}:{record_coordinate}".encode()
        ).hexdigest(),
        kind=ConflictKind.SEMANTIC_DISAGREEMENT,
        audience=ConflictAudience.USER,
        status=status,
        question=introduction.display.question,
        options=introduction.display.options,
        created_at=NOW,
        creation_coordinate=record_coordinate,
        scope_digest=introduction.scope.scope_digest,
    )
    body = {
        "conflict_id": introduction.conflict_id,
        "predecessor_conflict_revision": predecessor_revision,
        "predecessor_record_digest": predecessor_digest,
        "predecessor_status": predecessor_status,
        "resulting_attention": attention,
        "reason": reason,
        "proposal_digest": proposal_digest or sha256(b"clarification-reconstruction-proposal").hexdigest(),
        "processing_operation_id": processing_operation_id or (
            conflict_clarification_processing_operation_id(
                repository_id="semantic_ingestion",
                conflict_revision=attention.conflict_revision,
                proposal_digest=proposal_digest or sha256(b"clarification-reconstruction-proposal").hexdigest(),
                policy_fingerprint=sha256(b"clarification-policy").hexdigest(),
            )
            if reason == SemanticConflictClarificationTransitionReason.SUBMITTED
            else sha256(b"clarification-reconstruction-operation").hexdigest()
        ),
        "successor_conflict_revision": successor_conflict_revision,
        "record_coordinate": record_coordinate,
        "transition_coordinate": transition_coordinate or record_coordinate,
        "transitioned_at": NOW,
    }
    return SemanticConflictClarificationTransition(
        **body, transition_digest=_clarification_transition_digest(body)
    )


def _coerced_transition_body(body: dict) -> dict:
    """Coerce a dumped transition body's nested shapes back to models.

    ``model_dump`` flattens nested models to dicts; reconstructing from that
    body with ``model_construct`` leaves dict-valued model fields whose
    serialization warns under ``-W error``. Coerce the enum and model fields
    back before digesting or constructing.
    """
    coerced = dict(body)
    coerced["predecessor_status"] = ConflictStatus(coerced["predecessor_status"])
    coerced["reason"] = SemanticConflictClarificationTransitionReason(coerced["reason"])
    attention = coerced["resulting_attention"]
    if isinstance(attention, dict):
        attention = ConflictAttention.model_validate(attention)
    coerced["resulting_attention"] = attention.model_copy(
        update={
            "status": ConflictStatus(attention.status),
            "kind": ConflictKind(attention.kind),
            "audience": ConflictAudience(attention.audience),
        }
    )
    return coerced


def _clarification_transition_digest(body: dict[str, object]) -> str:
    """Match the model-validator's canonical primitive representation exactly."""

    provisional = SemanticConflictClarificationTransition.model_construct(
        **body, transition_digest="0" * 64
    )
    canonical_body = provisional.model_dump(mode="python", exclude={"transition_digest"})
    return sha256(
        b"memorii.semantic-conflict-clarification-transition.v1\0"
        + encode_typed_value(canonical_body)
    ).hexdigest()


def _clarification_submission_generation(
    introduction: SemanticConflictIntroduction,
    transition: SemanticConflictClarificationTransition,
    *,
    expected_conflict_revision: str | None = None,
    operation_id: str = "clarification-reconstruction",
    source_user_event_id: str = "clarification-source",
    source_user_event_digest: str | None = None,
    verified_confirmation: VerifiedUserConfirmation | None = None,
) -> SemanticConflictClarificationSubmissionGeneration:
    request = ConflictResolutionRequest(
        conflict_id=introduction.conflict_id,
        expected_conflict_revision=expected_conflict_revision or introduction.conflict_revision,
        operation_id=operation_id,
        action=ConflictResolutionAction.NEITHER,
        selected_candidate_ids=(),
        validity_intervals=(),
        source_user_event_id=source_user_event_id,
    )
    proposal = build_agent_clarification_proposal(
        request,
        source_user_event_digest=(
            source_user_event_digest
            if source_user_event_digest is not None
            else sha256(source_user_event_id.encode()).hexdigest()
        ),
        agent_principal_id="clarification-principal",
        scope_digest=introduction.scope.scope_digest,
    )
    assert proposal.proposal_digest == transition.proposal_digest
    receipt_body = {
        "operation_id": proposal.operation_id,
        "conflict_id": proposal.conflict_id,
        "conflict_revision": proposal.conflict_revision,
        "request_digest": proposal.request_digest,
        "proposal_digest": proposal.proposal_digest,
        "verified_confirmation_digest": (
            None
            if verified_confirmation is None
            else verified_user_confirmation_digest(verified_confirmation)
        ),
    }
    receipt = ConflictClarificationOperationReceipt(
        **receipt_body,
        receipt_digest=sha256(
            b"memorii.conflict-clarification-operation-receipt.v1\0"
            + encode_typed_value(receipt_body)
        ).hexdigest(),
    )
    work_body = {
        "conflict_id": proposal.conflict_id,
        "conflict_revision": transition.resulting_attention.conflict_revision,
        "proposal_digest": proposal.proposal_digest,
        "attempt_count": 0,
        "max_attempts": 3,
        "owner_token": None,
        "ownership_epoch": 0,
        "lease_expires_at": None,
        "last_failure_class": None,
        "policy_fingerprint": sha256(b"clarification-policy").hexdigest(),
        "processing_operation_id": transition.processing_operation_id,
        "downstream_receipt_digest": None,
        "work_revision": 1,
        "predecessor_work_digest": None,
    }
    work = ConflictClarificationWork(
        **work_body,
        work_digest=sha256(
            b"memorii.conflict-clarification-work.v1\0" + encode_typed_value(work_body)
        ).hexdigest(),
    )
    return SemanticConflictClarificationSubmissionGeneration.create(
        operation_receipt=receipt,
        proposal=proposal,
        verified_confirmation=verified_confirmation,
        work=work,
        transition=transition,
    )


def _clarification_pointer(
    *,
    conflict_id: str,
    record_id: str,
    record_digest_value: str,
    conflict_revision: str,
    pointer_revision: int,
    predecessor_pointer_digest: str | None,
) -> ActiveSemanticConflict:
    body = {
        "conflict_id": conflict_id,
        "current_conflict_revision": conflict_revision,
        "current_record_id": record_id,
        "current_record_digest": record_digest_value,
        "pointer_revision": pointer_revision,
        "predecessor_pointer_digest": predecessor_pointer_digest,
    }
    return ActiveSemanticConflict(
        **body,
        pointer_digest=sha256(
            b"memorii.semantic-conflict-active-pointer.v1\0" + encode_typed_value(body)
        ).hexdigest(),
    )


def _verified_confirmation_for(
    proposal,
    *,
    nonce: str,
) -> VerifiedUserConfirmation:
    return VerifiedUserConfirmation(
        issuer_id="clarification-confirmation-issuer",
        key_id="clarification-confirmation-key",
        trust_snapshot_digest=sha256(b"clarification-confirmation-trust").hexdigest(),
        revocation_snapshot_digest=sha256(b"clarification-confirmation-revocation").hexdigest(),
        principal_id=proposal.agent_principal_id,
        scope_digest=proposal.scope_digest,
        conflict_id=proposal.conflict_id,
        conflict_revision=proposal.conflict_revision,
        action=proposal.action,
        request_digest=proposal.request_digest,
        source_user_event_id=proposal.answering_user_event_id,
        source_user_event_digest=proposal.answering_user_event_digest,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        nonce=nonce,
    )


def _persist_reconstructible_clarification_history(
    tmp_path,
    *,
    backend=None,
    semantic_integrity_lifecycle: PrivilegedSemanticIntegrityLifecycle | None = None,
    complete: bool = True,
    verified_confirmation_nonce: str | None = None,
    return_runtime: bool = False,
    before_submission: Callable[[MemoryPlaneService], None] | None = None,
):
    """Persist real introduction authority followed by submitted and accepted edges."""

    storage = tmp_path / "memory-plane"
    plane, _, store, _, fence, service, repository = _setup(
        verified=True,
        backend=backend or JsonlMemoryPlaneStore(storage),
        scope_ids=frozenset({"scope:a"}),
        with_test_conflict_authority=True,
        semantic_integrity_lifecycle=semantic_integrity_lifecycle,
    )
    first = accepted_terminal(
        operation_id=fence.operation_id,
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, fence, first)
    service.persist(fence=fence, terminal=first, authorization_verifier=AUTHORIZATION)
    _, contested_fence = handoff(
        plane,
        coordinate="clarification-reconstruction",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=store._writers.commit_binding(store._writers.current()),
    )
    contested = accepted_terminal(
        operation_id=contested_fence.operation_id,
        object_logical_entity_id="entity:initech",
        object_entity_revision_id="entity-revision:initech:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, contested_fence, contested)
    service.persist(
        fence=contested_fence,
        terminal=contested,
        authorization_verifier=AUTHORIZATION,
    )
    introduction_record = next(
        record
        for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
        if record.memory_id.startswith("semantic_ingestion:conflict-authority:introduction:")
    )
    introduction = SemanticConflictIntroduction.model_validate(
        decode_typed_value(bytes.fromhex(str(introduction_record.content["canonical_hex"])))
    )
    pointer_id = f"semantic_ingestion:conflict-authority:pointer:{introduction.conflict_id}"
    pointer_record = plane.get_record(pointer_id)
    assert pointer_record is not None
    head_record = plane.get_record("semantic_ingestion:conflict-authority:ledger-head")
    assert head_record is not None
    clarification_source = plane.get_record("tx:clarification-reconstruction")
    assert clarification_source is not None
    submission_request = ConflictResolutionRequest(
        conflict_id=introduction.conflict_id,
        expected_conflict_revision=introduction.conflict_revision,
        operation_id="clarification-reconstruction",
        action=ConflictResolutionAction.NEITHER,
        selected_candidate_ids=(),
        validity_intervals=(),
        # The proposal must bind an admitted user event.  The canonical
        # completion guard rejects a terminal that substitutes an arbitrary
        # conversation identifier for an ingress-controlled source.
        source_user_event_id=clarification_source.memory_id,
    )
    submission_proposal = build_agent_clarification_proposal(
        submission_request,
        source_user_event_digest=source_admission_source_digest(clarification_source),
        agent_principal_id="clarification-principal",
        scope_digest=introduction.scope.scope_digest,
    )
    submitted = _clarification_transition(
        introduction=introduction,
        predecessor_digest=introduction.introduction_digest,
        predecessor_revision=introduction.conflict_revision,
        predecessor_status=ConflictStatus.OPEN,
        status=ConflictStatus.CLARIFICATION_SUBMITTED,
        reason=SemanticConflictClarificationTransitionReason.SUBMITTED,
        record_coordinate=2,
        proposal_digest=submission_proposal.proposal_digest,
    )
    generation = _clarification_submission_generation(
        introduction,
        submitted,
        source_user_event_id=clarification_source.memory_id,
        source_user_event_digest=source_admission_source_digest(clarification_source),
        verified_confirmation=(
            None
            if verified_confirmation_nonce is None
            else _verified_confirmation_for(
                submission_proposal, nonce=verified_confirmation_nonce
            )
        ),
    )
    if before_submission is not None:
        before_submission(plane)
    pointer_two = store.submit_conflict_clarification_generation(generation)
    assert generation.work.conflict_revision == submitted.resulting_attention.conflict_revision
    operation_index = plane.get_record(
        "semantic_ingestion:conflict-authority:clarification-submission-operation:"
        f"{generation.operation_receipt.operation_id}"
    )
    assert operation_index is not None
    nonce_consumptions = tuple(
        record
        for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
        if record.memory_id.startswith(
            "semantic_ingestion:conflict-authority:clarification-nonce-consumption:"
        )
    )
    if verified_confirmation_nonce is None:
        assert generation.verified_confirmation is None
        assert generation.operation_receipt.verified_confirmation_digest is None
        assert not nonce_consumptions
        assert not tuple(
            record
            for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
            if record.memory_id.startswith(
                "semantic_ingestion:conflict-authority:clarification-confirmation-proof:"
            )
        )
    else:
        assert generation.verified_confirmation is not None
        assert generation.verified_confirmation.nonce == verified_confirmation_nonce
        assert len(nonce_consumptions) == 1
    submitted_records = tuple(plane.list_records())
    assert store.submit_conflict_clarification_generation(generation) == pointer_two
    assert tuple(plane.list_records()) == submitted_records
    divergent = generation.model_copy(
        update={
            "proposal": generation.proposal.model_copy(
                update={"operation_id": "divergent-operation"}
            )
        }
    )
    with pytest.raises(PreplanningStoreError):
        store.submit_conflict_clarification_generation(divergent)
    assert tuple(plane.list_records()) == submitted_records
    if not complete:
        if return_runtime:
            return (
                storage,
                introduction,
                submitted,
                None,
                pointer_two,
                None,
                plane,
                store,
                service,
                repository,
            )
        return storage, introduction, submitted, None, pointer_two, None
    # The accepted edge is a composite completion write, never a loose
    # pointer transition: claim the durable submitted work and commit the
    # real transaction (receipt, work successor, result member, event batch).
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5),
        owner_token="clarification-reconstruction-owner",
    )
    assert claim is not None
    _receipt, _terminal, _processing = _commit_claimed_accepted_clarification(
        store,
        claim,
        store.build_conflict_clarification_cas_input(claim),
    )
    completed = next(
        transition
        for transition in (
            decode_persisted_conflict_generation(
                decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
                SemanticConflictClarificationTransition,
            )
            for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
            if record.memory_id.startswith(
                "semantic_ingestion:conflict-authority:clarification-transition:"
            )
        )
        if transition.reason is SemanticConflictClarificationTransitionReason.ACCEPTED
    )
    pointer_record = plane.get_record(
        f"semantic_ingestion:conflict-authority:pointer:{introduction.conflict_id}"
    )
    assert pointer_record is not None
    pointer_three = ActiveSemanticConflict.model_validate(
        decode_typed_value(bytes.fromhex(str(pointer_record.content["canonical_hex"])))
    )
    return storage, introduction, submitted, completed, pointer_two, pointer_three


def _submitted_clarification_generation(
    plane: MemoryPlaneService,
) -> SemanticConflictClarificationSubmissionGeneration:
    records = tuple(
        record
        for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
        if record.memory_id.startswith(
            "semantic_ingestion:conflict-authority:clarification-submission:"
        )
    )
    assert len(records) == 1
    return decode_persisted_conflict_generation(
        decode_typed_value(bytes.fromhex(str(records[0].content["canonical_hex"]))),
        SemanticConflictClarificationSubmissionGeneration,
    )


def _open_conflict_for_canonical_submission(tmp_path):
    """Create one real OPEN conflict without manufacturing a submission edge."""

    plane, _, store, binding, fence, service, repository = _setup(
        verified=True,
        backend=InMemoryMemoryPlaneStore(),
        scope_ids=frozenset({"scope:a"}),
        with_test_conflict_authority=True,
    )
    first = accepted_terminal(
        operation_id=fence.operation_id,
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, fence, first)
    service.persist(fence=fence, terminal=first, authorization_verifier=AUTHORIZATION)
    _, contested_fence = handoff(
        plane,
        coordinate="canonical-submission-race-conflict",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=binding,
    )
    contested = accepted_terminal(
        operation_id=contested_fence.operation_id,
        object_logical_entity_id="entity:initech",
        object_entity_revision_id="entity-revision:initech:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, contested_fence, contested)
    service.persist(
        fence=contested_fence,
        terminal=contested,
        authorization_verifier=AUTHORIZATION,
    )
    introduction_record = next(
        record
        for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
        if record.memory_id.startswith("semantic_ingestion:conflict-authority:introduction:")
    )
    introduction = SemanticConflictIntroduction.model_validate(
        decode_typed_value(bytes.fromhex(str(introduction_record.content["canonical_hex"])))
    )
    source = plane.get_record("tx:canonical-submission-race-conflict")
    assert source is not None
    return plane, store, binding, service, repository, introduction, source


def _canonical_submission_request(
    introduction: SemanticConflictIntroduction,
    source: CanonicalMemoryRecord,
    *,
    operation_id: str,
) -> tuple[ConflictResolutionRequest, AgentClarificationProposal]:
    request = ConflictResolutionRequest(
        conflict_id=introduction.conflict_id,
        expected_conflict_revision=introduction.conflict_revision,
        operation_id=operation_id,
        action=ConflictResolutionAction.NEITHER,
        selected_candidate_ids=(),
        validity_intervals=(),
        source_user_event_id=source.memory_id,
    )
    proposal = build_agent_clarification_proposal(
        request,
        source_user_event_digest=source_admission_source_digest(source),
        agent_principal_id="clarification-principal",
        scope_digest=introduction.scope.scope_digest,
    )
    return request, proposal


def _publish_natural_conflict_projection(
    *,
    plane: MemoryPlaneService,
    store: SemanticIngestionAtomicStore,
    binding,
    service: SemanticTerminalPersistenceService,
    repository: SemanticAuthorizationAuthorityRepository,
    coordinate: str,
) -> None:
    """Use the normal publisher so projection supersession owns its full closure."""

    _, fence = handoff(
        plane,
        coordinate=coordinate,
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=binding,
    )
    terminal = accepted_terminal(
        operation_id=fence.operation_id,
        object_logical_entity_id="entity:initech",
        object_entity_revision_id="entity-revision:initech:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, fence, terminal)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)


def test_canonical_submission_projection_first_race_returns_stale_without_submission_records(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A projection winner turns a lost first-submission CAS into STALE_REVISION."""

    plane, store, binding, service, repository, introduction, source = (
        _open_conflict_for_canonical_submission(tmp_path)
    )
    request, proposal = _canonical_submission_request(
        introduction,
        source,
        operation_id="canonical-submission-projection-first",
    )
    original_submit = store.submit_conflict_clarification_generation
    published = False

    def projection_wins(generation):
        nonlocal published
        if not published:
            published = True
            _publish_natural_conflict_projection(
                plane=plane,
                store=store,
                binding=binding,
                service=service,
                repository=repository,
                coordinate="canonical-submission-projection-first",
            )
        return original_submit(generation)

    monkeypatch.setattr(store, "submit_conflict_clarification_generation", projection_wins)
    result = store.submit_canonical_conflict_clarification(
        request=request,
        request_digest=proposal.request_digest,
        proposal=proposal,
        verified_confirmation=None,
    )
    assert published is True
    assert result.outcome is ClarificationSubmissionOutcome.STALE_REVISION
    assert result.attention is not None
    assert result.attention.conflict_revision != request.expected_conflict_revision
    forbidden_prefixes = (
        "semantic_ingestion:conflict-authority:clarification-submission:",
        "semantic_ingestion:conflict-authority:clarification-submission-operation:",
        "semantic_ingestion:conflict-authority:clarification-confirmation-proof:",
        "semantic_ingestion:conflict-authority:clarification-nonce-consumption:",
        "semantic_ingestion:conflict-authority:clarification-work-member:",
    )
    assert not any(
        record.memory_id.startswith(forbidden_prefixes)
        for record in plane.list_records()
    )


def test_canonical_submission_first_is_idempotent_after_natural_projection_supersedes_unclaimed_work(
    tmp_path,
) -> None:
    """A natural projection supersedes submitted unclaimed work in one closure."""

    plane, store, binding, service, repository, introduction, source = (
        _open_conflict_for_canonical_submission(tmp_path)
    )
    request, proposal = _canonical_submission_request(
        introduction,
        source,
        operation_id="canonical-submission-first",
    )
    submitted = store.submit_canonical_conflict_clarification(
        request=request,
        request_digest=proposal.request_digest,
        proposal=proposal,
        verified_confirmation=None,
    )
    assert submitted.outcome is ClarificationSubmissionOutcome.SUBMITTED
    assert submitted.operation_receipt is not None
    generation = _submitted_clarification_generation(plane)
    _publish_natural_conflict_projection(
        plane=plane,
        store=store,
        binding=binding,
        service=service,
        repository=repository,
        coordinate="canonical-submission-first-projection",
    )
    terminal_work = next(
        decode_persisted_conflict_generation(
            decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
            ConflictClarificationWork,
        )
        for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
        if record.memory_id.startswith(
            "semantic_ingestion:conflict-authority:clarification-work-member:"
        )
        and decode_persisted_conflict_generation(
            decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
            ConflictClarificationWork,
        ).processing_operation_id == generation.work.processing_operation_id
        and decode_persisted_conflict_generation(
            decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
            ConflictClarificationWork,
        ).work_revision > generation.work.work_revision
    )
    assert terminal_work.owner_token is None
    assert terminal_work.work_revision == 2
    assert not any(
        record.memory_id.startswith(
            "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
        )
        for record in plane.list_records()
    )
    before_retry = tuple(plane.list_records())
    retried = store.submit_canonical_conflict_clarification(
        request=request,
        request_digest=proposal.request_digest,
        proposal=proposal,
        verified_confirmation=None,
    )
    assert retried.outcome is ClarificationSubmissionOutcome.IDEMPOTENT
    assert retried.operation_receipt == submitted.operation_receipt
    assert tuple(plane.list_records()) == before_retry


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_verified_clarification_submission_binds_operation_proof_and_nonce_once(
    tmp_path,
    backend_kind: str,
) -> None:
    """A verified user answer is one replayable, exactly-once submission closure."""
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, introduction, _, _, pointer, _ = _persist_reconstructible_clarification_history(
        tmp_path,
        backend=backend,
        complete=False,
        verified_confirmation_nonce="verified-submission-nonce",
    )
    plane = MemoryPlaneService(
        record_store=backend if backend is not None else JsonlMemoryPlaneStore(storage)
    )
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
        ),
        now_provider=lambda: NOW,
    )
    generation = _submitted_clarification_generation(plane)
    assert generation.verified_confirmation is not None
    confirmation = generation.verified_confirmation
    operation = SemanticConflictClarificationSubmissionOperation.create(
        operation_id=generation.operation_receipt.operation_id,
        request_digest=generation.operation_receipt.request_digest,
        proposal_digest=generation.operation_receipt.proposal_digest,
        operation_receipt_digest=generation.operation_receipt.receipt_digest,
        generation_digest=generation.generation_digest,
        verified_confirmation_digest=verified_user_confirmation_digest(confirmation),
    )
    consumption = SemanticConflictClarificationNonceConsumption.create(
        nonce_digest=verified_user_confirmation_nonce_digest(confirmation),
        verified_confirmation_digest=verified_user_confirmation_digest(confirmation),
        operation_id=generation.operation_receipt.operation_id,
    )
    by_id = {record.memory_id: record for record in plane.list_records()}
    operation_id = (
        "semantic_ingestion:conflict-authority:clarification-submission-operation:"
        f"{operation.operation_id}"
    )
    proof_id = (
        "semantic_ingestion:conflict-authority:clarification-confirmation-proof:"
        f"{verified_user_confirmation_digest(confirmation)}"
    )
    nonce_id = (
        "semantic_ingestion:conflict-authority:clarification-nonce-consumption:"
        f"{consumption.nonce_digest}"
    )
    assert decode_persisted_conflict_generation(
        decode_typed_value(bytes.fromhex(str(by_id[operation_id].content["canonical_hex"]))),
        SemanticConflictClarificationSubmissionOperation,
    ) == operation
    assert decode_persisted_conflict_generation(
        decode_typed_value(bytes.fromhex(str(by_id[proof_id].content["canonical_hex"]))),
        VerifiedUserConfirmation,
    ) == confirmation
    assert decode_persisted_conflict_generation(
        decode_typed_value(bytes.fromhex(str(by_id[nonce_id].content["canonical_hex"]))),
        SemanticConflictClarificationNonceConsumption,
    ) == consumption
    current = next(iter(store._projection_history.current_clarification_work().values()))
    assert current.work == generation.work
    assert current.work.conflict_revision == generation.transition.resulting_attention.conflict_revision
    assert current.work.processing_operation_id == conflict_clarification_processing_operation_id(
        repository_id="semantic_ingestion",
        conflict_revision=generation.transition.resulting_attention.conflict_revision,
        proposal_digest=generation.proposal.proposal_digest,
        policy_fingerprint=generation.work.policy_fingerprint,
    )
    before_retry = tuple(plane.list_records())
    assert store.submit_conflict_clarification_generation(generation) == pointer
    assert tuple(plane.list_records()) == before_retry

    # An acknowledgement retry may repeat the entire immutable closure, but a
    # changed proof for the same operation must never consume another nonce.
    replacement_confirmation = _verified_confirmation_for(
        generation.proposal, nonce="different-verified-submission-nonce"
    )
    receipt_values = generation.operation_receipt.model_dump(
        mode="python", exclude={"receipt_digest"}
    )
    receipt_values["verified_confirmation_digest"] = verified_user_confirmation_digest(
        replacement_confirmation
    )
    changed_receipt = ConflictClarificationOperationReceipt(
        **receipt_values,
        receipt_digest=sha256(
            b"memorii.conflict-clarification-operation-receipt.v1\0"
            + encode_typed_value(receipt_values)
        ).hexdigest(),
    )
    changed_proof = SemanticConflictClarificationSubmissionGeneration.create(
        operation_receipt=changed_receipt,
        proposal=generation.proposal,
        verified_confirmation=replacement_confirmation,
        work=generation.work,
        transition=generation.transition,
    )
    with pytest.raises(PreplanningStoreError):
        store.submit_conflict_clarification_generation(changed_proof)
    assert tuple(plane.list_records()) == before_retry

    # A second operation with the retained nonce cannot publish another
    # closure, even when it uses a distinct proposal and processing identity.
    request = ConflictResolutionRequest(
        conflict_id=introduction.conflict_id,
        expected_conflict_revision=introduction.conflict_revision,
        operation_id="different-operation-same-nonce",
        action=ConflictResolutionAction.NEITHER,
        selected_candidate_ids=(),
        validity_intervals=(),
        source_user_event_id=generation.proposal.source_user_event_id,
    )
    other_proposal = build_agent_clarification_proposal(
        request,
        source_user_event_digest=generation.proposal.source_user_event_digest,
        agent_principal_id=generation.proposal.agent_principal_id,
        scope_digest=generation.proposal.scope_digest,
    )
    other_transition = _clarification_transition(
        introduction=introduction,
        predecessor_digest=introduction.introduction_digest,
        predecessor_revision=introduction.conflict_revision,
        predecessor_status=ConflictStatus.OPEN,
        status=ConflictStatus.CLARIFICATION_SUBMITTED,
        reason=SemanticConflictClarificationTransitionReason.SUBMITTED,
        record_coordinate=2,
        proposal_digest=other_proposal.proposal_digest,
        processing_operation_id=conflict_clarification_processing_operation_id(
            repository_id="semantic_ingestion",
            conflict_revision=sha256(b"clarification:submitted:2").hexdigest(),
            proposal_digest=other_proposal.proposal_digest,
            policy_fingerprint=generation.work.policy_fingerprint,
        ),
    )
    other = _clarification_submission_generation(
        introduction,
        other_transition,
        operation_id=request.operation_id,
        source_user_event_id=request.source_user_event_id,
        source_user_event_digest=other_proposal.source_user_event_digest,
        verified_confirmation=_verified_confirmation_for(other_proposal, nonce=confirmation.nonce),
    )
    with pytest.raises(PreplanningStoreError):
        store.submit_conflict_clarification_generation(other)
    assert tuple(plane.list_records()) == before_retry
    _assert_live_conflict_replay_binding(store)

    if backend_kind == "jsonl":
        reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        reopened = SemanticIngestionAtomicStore(
            reopened_plane,
            SemanticWriterAdmissionStore(
                reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
            ),
            now_provider=lambda: NOW,
        )
        assert reopened.submit_conflict_clarification_generation(generation) == pointer
        assert reopened._projection_history.current_clarification_work() == {
            generation.work.conflict_id: current
        }
        _assert_live_conflict_replay_binding(reopened)


def test_jsonl_submission_lost_ack_reopens_for_exact_canonical_retry(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed submission closure survives a lost write acknowledgement unchanged."""

    lost_ack = False

    def inject_lost_ack(plane: MemoryPlaneService) -> None:
        original_write = plane.conditionally_write_records

        def publish_then_lose_ack(records, **kwargs):
            nonlocal lost_ack
            result = original_write(records, **kwargs)
            if not lost_ack and any(
                record.memory_id.startswith(
                    "semantic_ingestion:conflict-authority:clarification-submission:"
                )
                for record in records
            ):
                lost_ack = True
                raise OSError("simulated clarification submission lost acknowledgement")
            return result

        monkeypatch.setattr(plane, "conditionally_write_records", publish_then_lose_ack)

    with pytest.raises(OSError, match="submission lost acknowledgement"):
        _persist_reconstructible_clarification_history(
            tmp_path,
            complete=False,
            before_submission=inject_lost_ack,
        )
    assert lost_ack

    storage = tmp_path / "memory-plane"
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        SemanticWriterAdmissionStore(
            reopened_plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: NOW,
        ),
        now_provider=lambda: NOW,
    )
    generation = _submitted_clarification_generation(reopened_plane)
    retained = tuple(reopened_plane.list_records())

    assert reopened_store.submit_conflict_clarification_generation(generation).conflict_id == (
        generation.transition.conflict_id
    )
    assert tuple(reopened_plane.list_records()) == retained
    _assert_live_conflict_replay_binding(reopened_store)


def test_jsonl_accepted_completion_lost_ack_reopens_for_exact_cas_retry(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepted completion retries its committed closure without duplicate durable effects."""

    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path,
        complete=False,
    )
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: NOW,
        ),
        now_provider=lambda: NOW,
        semantic_conflict_authority_resolver=_TestSemanticConflictAuthorityResolver(plane),
    )
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="lost-ack-completion-owner"
    )
    assert claim is not None
    cas = store.build_conflict_clarification_cas_input(claim)
    terminal = _with_claim_record_version(
        accepted_terminal(
            operation_id=claim.work.processing_operation_id,
            source_id=claim.proposal.source_user_event_id,
            source_digest=claim.proposal.source_user_event_digest,
            object_logical_entity_id="entity:lost-ack-clarified",
            object_entity_revision_id="entity-revision:lost-ack-clarified:v1",
        ),
        record_version=2,
    )
    resulting_revision = sha256(b"lost-ack-accepted-clarification").hexdigest()
    original_write = plane.conditionally_write_records
    lost_ack = False

    def publish_then_lose_ack(records, **kwargs):
        nonlocal lost_ack
        result = original_write(records, **kwargs)
        if not lost_ack and any(
            record.source_kind == "semantic_ingestion_conflict_clarification_transaction"
            for record in records
        ):
            lost_ack = True
            raise OSError("simulated clarification completion lost acknowledgement")
        return result

    monkeypatch.setattr(plane, "conditionally_write_records", publish_then_lose_ack)
    with pytest.raises(OSError, match="completion lost acknowledgement"):
        store.commit_conflict_clarification_transaction(
            proposal=claim.proposal,
            processing_operation_id=claim.work.processing_operation_id,
            resulting_conflict_revision=resulting_revision,
            policy_fingerprint=claim.work.policy_fingerprint,
            committed_outcome="accepted",
            semantic_result_digest=terminal.terminal_digest,
            semantic_terminal=terminal,
            clarification_cas=cas,
        )
    assert lost_ack
    committed = tuple(plane.list_records())

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        SemanticWriterAdmissionStore(
            reopened_plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: NOW,
        ),
        now_provider=lambda: NOW,
        semantic_conflict_authority_resolver=_TestSemanticConflictAuthorityResolver(
            reopened_plane
        ),
    )
    recovered = reopened_store.commit_conflict_clarification_transaction(
        proposal=claim.proposal,
        processing_operation_id=claim.work.processing_operation_id,
        resulting_conflict_revision=resulting_revision,
        policy_fingerprint=claim.work.policy_fingerprint,
        committed_outcome="accepted",
        semantic_result_digest=terminal.terminal_digest,
        semantic_terminal=terminal,
        clarification_cas=cas,
    )
    receipt = reopened_store.resolve_conflict_clarification_receipt(
        claim.work.processing_operation_id
    )
    assert receipt is not None
    assert isinstance(recovered, ConflictClarificationAttemptResult)
    assert recovered.downstream_receipt_digest == receipt.receipt_digest
    assert tuple(reopened_plane.list_records()) == committed
    assert len(reopened_plane.list_records(source_kind="semantic_ingestion_event_batch")) == 3
    assert len(
        reopened_plane.list_records(
            source_kind="semantic_ingestion_conflict_clarification_transaction"
        )
    ) == 1
    assert len(
        reopened_plane.list_records(
            source_kind="semantic_ingestion_conflict_clarification_receipt"
        )
    ) == 1
    _assert_live_conflict_replay_binding(reopened_store)


def test_second_live_conflict_fences_reused_nonce_and_operation_index(tmp_path) -> None:
    """Neither fence may be hidden behind the first conflict's stale pointer."""
    (
        _,
        first_introduction,
        _,
        _,
        _,
        _,
        plane,
        store,
        service,
        repository,
    ) = _persist_reconstructible_clarification_history(
        tmp_path,
        backend=InMemoryMemoryPlaneStore(),
        complete=False,
        verified_confirmation_nonce="shared-cross-conflict-nonce",
        return_runtime=True,
    )
    _, base_fence = handoff(
        plane,
        coordinate="second-live-conflict-base",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=store._writers.commit_binding(store._writers.current()),
    )
    base = accepted_terminal(
        operation_id=base_fence.operation_id,
        subject_logical_entity_id="entity:zephyr",
        subject_entity_revision_id="entity-revision:zephyr:v1",
        object_logical_entity_id="entity:second-live-a",
        object_entity_revision_id="entity-revision:second-live-a:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, base_fence, base)
    service.persist(fence=base_fence, terminal=base, authorization_verifier=AUTHORIZATION)
    _, contested_fence = handoff(
        plane,
        coordinate="second-live-conflict-contested",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=store._writers.commit_binding(store._writers.current()),
    )
    contested = accepted_terminal(
        operation_id=contested_fence.operation_id,
        subject_logical_entity_id="entity:zephyr",
        subject_entity_revision_id="entity-revision:zephyr:v1",
        object_logical_entity_id="entity:second-live-b",
        object_entity_revision_id="entity-revision:second-live-b:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, contested_fence, contested)
    service.persist(fence=contested_fence, terminal=contested, authorization_verifier=AUTHORIZATION)

    introductions = tuple(
        SemanticConflictIntroduction.model_validate(
            decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"])))
        )
        for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
        if record.memory_id.startswith("semantic_ingestion:conflict-authority:introduction:")
    )
    second_introduction = next(
        introduction
        for introduction in introductions
        if introduction.conflict_id != first_introduction.conflict_id
    )
    second_pointer_record = plane.get_record(
        f"semantic_ingestion:conflict-authority:pointer:{second_introduction.conflict_id}"
    )
    head_record = plane.get_record("semantic_ingestion:conflict-authority:ledger-head")
    source = plane.get_record("tx:second-live-conflict-contested")
    assert second_pointer_record is not None and head_record is not None and source is not None
    second_pointer = ActiveSemanticConflict.model_validate(
        decode_typed_value(bytes.fromhex(str(second_pointer_record.content["canonical_hex"])))
    )
    head = SemanticConflictLedgerHead.model_validate(
        decode_typed_value(bytes.fromhex(str(head_record.content["canonical_hex"])))
    )

    def candidate_generation(*, operation_id: str, nonce: str | None):
        request = ConflictResolutionRequest(
            conflict_id=second_introduction.conflict_id,
            expected_conflict_revision=second_introduction.conflict_revision,
            operation_id=operation_id,
            action=ConflictResolutionAction.NEITHER,
            selected_candidate_ids=(),
            validity_intervals=(),
            source_user_event_id=source.memory_id,
        )
        proposal = build_agent_clarification_proposal(
            request,
            source_user_event_digest=source_admission_source_digest(source),
            agent_principal_id="clarification-principal",
            scope_digest=second_introduction.scope.scope_digest,
        )
        transition = _clarification_transition(
            introduction=second_introduction,
            predecessor_digest=second_introduction.introduction_digest,
            predecessor_revision=second_introduction.conflict_revision,
            predecessor_status=ConflictStatus.OPEN,
            status=ConflictStatus.CLARIFICATION_SUBMITTED,
            reason=SemanticConflictClarificationTransitionReason.SUBMITTED,
            record_coordinate=head.last_record_coordinate + 1,
            transition_coordinate=second_pointer.pointer_revision + 1,
            proposal_digest=proposal.proposal_digest,
            processing_operation_id=conflict_clarification_processing_operation_id(
                repository_id="semantic_ingestion",
                conflict_revision=sha256(
                    f"clarification:submitted:{head.last_record_coordinate + 1}".encode()
                ).hexdigest(),
                proposal_digest=proposal.proposal_digest,
                policy_fingerprint=sha256(b"clarification-policy").hexdigest(),
            ),
        )
        return _clarification_submission_generation(
            second_introduction,
            transition,
            operation_id=operation_id,
            source_user_event_id=source.memory_id,
            source_user_event_digest=source_admission_source_digest(source),
            verified_confirmation=(
                None if nonce is None else _verified_confirmation_for(proposal, nonce=nonce)
            ),
        )

    before = tuple(plane.list_records())
    reused_nonce = candidate_generation(
        operation_id="second-live-conflict-new-operation",
        nonce="shared-cross-conflict-nonce",
    )
    with pytest.raises(PreplanningStoreError):
        store.submit_conflict_clarification_generation(reused_nonce)
    assert tuple(plane.list_records()) == before
    assert store._projection_history._current_semantic_conflicts()[
        second_introduction.conflict_id
    ][1].status == ConflictStatus.OPEN.value

    # The second pointer remains live, so this rejection can only be the
    # retained operation index rather than a stale predecessor image.
    reused_operation = candidate_generation(
        operation_id="clarification-reconstruction",
        nonce=None,
    )
    with pytest.raises(PreplanningStoreError):
        store.submit_conflict_clarification_generation(reused_operation)
    assert tuple(plane.list_records()) == before


@pytest.mark.parametrize(
    "field,value",
    (
        ("source_user_event_id", "substituted-source"),
        ("source_user_event_digest", "0" * 64),
        ("request_digest", "1" * 64),
        ("action", ConflictResolutionAction.SELECT),
        ("principal_id", "substituted-proposal-principal"),
    ),
)
def test_submission_rejects_mismatched_verified_confirmation_before_write(
    tmp_path,
    field: str,
    value: object,
) -> None:
    """A host proof is bound to every proposal-bearing user-answer field."""
    storage, _, submitted, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path,
        complete=False,
        verified_confirmation_nonce="binding-negative-nonce",
    )
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    generation = _submitted_clarification_generation(plane)
    assert generation.verified_confirmation is not None
    mutated_confirmation = generation.verified_confirmation.model_copy(
        update={field: value}
    )
    receipt_values = generation.operation_receipt.model_dump(
        mode="python", exclude={"receipt_digest"}
    )
    receipt_values["verified_confirmation_digest"] = verified_user_confirmation_digest(
        mutated_confirmation
    )
    mutated_receipt = ConflictClarificationOperationReceipt(
        **receipt_values,
        receipt_digest=sha256(
            b"memorii.conflict-clarification-operation-receipt.v1\0"
            + encode_typed_value(receipt_values)
        ).hexdigest(),
    )
    before = tuple(plane.list_records())
    with pytest.raises(ValueError, match="clarification confirmation proof binding is invalid"):
        SemanticConflictClarificationSubmissionGeneration.create(
            operation_receipt=mutated_receipt,
            proposal=generation.proposal,
            verified_confirmation=mutated_confirmation,
            work=generation.work,
            transition=submitted,
        )
    assert tuple(plane.list_records()) == before


@pytest.mark.parametrize("member", ("operation", "proof", "nonce"))
@pytest.mark.parametrize("mutation", ("missing", "substituted"))
def test_verified_submission_auxiliary_members_fail_replay_and_retry_closed(
    tmp_path,
    member: str,
    mutation: str,
) -> None:
    """The operation, proof, and nonce records are all required closure members."""
    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path,
        complete=False,
        verified_confirmation_nonce="verified-corruption-nonce",
    )
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    generation = _submitted_clarification_generation(plane)
    assert generation.verified_confirmation is not None
    confirmation = generation.verified_confirmation
    member_ids = {
        "operation": (
            "semantic_ingestion:conflict-authority:clarification-submission-operation:"
            f"{generation.operation_receipt.operation_id}"
        ),
        "proof": (
            "semantic_ingestion:conflict-authority:clarification-confirmation-proof:"
            f"{verified_user_confirmation_digest(confirmation)}"
        ),
        "nonce": (
            "semantic_ingestion:conflict-authority:clarification-nonce-consumption:"
            f"{verified_user_confirmation_nonce_digest(confirmation)}"
        ),
    }
    target_id = member_ids[member]
    target = plane.get_record(target_id)
    assert target is not None
    backend = JsonlMemoryPlaneStore(storage)
    if mutation == "missing":
        _rewrite_jsonl_snapshot(backend, plane, deleted_ids=(target_id,))
    else:
        substitute_id = next(
            value for key, value in member_ids.items() if key != member
        )
        substitute = plane.get_record(substitute_id)
        assert substitute is not None
        _rewrite_jsonl_snapshot(
            backend,
            plane,
            replacements=(
                target.model_copy(
                    update={
                        "content": {
                            **target.content,
                            "canonical_hex": substitute.content["canonical_hex"],
                            "authority_digest": substitute.content["authority_digest"],
                        }
                    }
                ),
            ),
        )
    corrupt_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    corrupt_store = SemanticIngestionAtomicStore(
        corrupt_plane,
        SemanticWriterAdmissionStore(
            corrupt_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
        ),
        now_provider=lambda: NOW,
    )
    corrupt_before = tuple(corrupt_plane.list_records())
    with pytest.raises(ProjectionHistoryError, match="projection_history_integrity_error"):
        corrupt_store._projection_history._current_semantic_conflicts()
    with pytest.raises(ProjectionHistoryError, match="projection_history_integrity_error"):
        corrupt_store._projection_history.current_clarification_work()
    with pytest.raises(PreplanningStoreError):
        corrupt_store.submit_conflict_clarification_generation(generation)
    assert tuple(corrupt_plane.list_records()) == corrupt_before


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_canonical_clarification_claim_and_renew_are_fenced_and_replayable(
    tmp_path,
    backend_kind: str,
) -> None:
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, introduction, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path,
        backend=backend,
        complete=False,
    )
    now = [NOW]
    if backend_kind == "jsonl":
        plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        writers = SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
        )
        store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now[0])
    else:
        # Reopen the same in-memory records through the public constructor so
        # both backends exercise the identical lifecycle API.
        plane = MemoryPlaneService(record_store=backend)
        writers = SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
        )
        store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now[0])
    _assert_live_conflict_replay_binding(store)
    replay_records_after_submission = _replay_binding_records(plane)
    state = next(iter(store._projection_history.current_clarification_work().values()))
    work = store._claimed_clarification_work(
        state.work,
        owner_token="claim-owner",
        ownership_epoch=state.work.ownership_epoch + 1,
        lease_expires_at=now[0] + timedelta(minutes=5),
    )
    attempt = store._clarification_attempt(
        previous=state.work,
        work=work,
        owner_token="claim-owner",
        claimed_at=now[0],
        lease_expires_at=work.lease_expires_at,
        predecessor_attempt_digest=None,
    )
    generation = SemanticConflictClarificationWorkGeneration.create(
        predecessor_work_digest=state.work.work_digest,
        work=work,
        attempt=attempt,
    )

    def authorization_record(scope_id: str) -> CanonicalMemoryRecord:
        authority_body = {
            "authority_record_id": (
                "semantic_ingestion:authorization:"
                f"{sha256(scope_id.encode()).hexdigest()}"
            ),
            "authority_scope_id": scope_id,
            "authority_revision": 1,
            "state": "active",
            "policy_bundle_digest": "1" * 64,
            "policy_revision_digest": "2" * 64,
            "egress_policy_revision": None,
            "egress_decision_digest": None,
            "deployment_authorization_digest": "3" * 64,
            "deployment_active_epoch": 1,
            "deployment_decision_digest": "4" * 64,
            "valid_until": datetime(2030, 1, 1, tzinfo=UTC),
            "read_set_digest": "5" * 64,
        }
        authority = SemanticAuthorizationAuthorityRecord(
            **authority_body,
            coordinates_digest=sha256(encode_typed_value(authority_body)).hexdigest(),
        )
        return _authorization_authority_record(authority, now[0])

    assert store.append_conflict_clarification_work_generation(generation) == generation
    binding = writers.commit_binding(writers.current())
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="claim-owner"
    )
    assert claim is not None and claim.work.conflict_id == introduction.conflict_id
    assert claim.work == work and claim.attempt == attempt
    _assert_live_conflict_replay_binding(store)
    assert _replay_binding_records(plane) == replay_records_after_submission
    cas = store.build_conflict_clarification_cas_input(claim)
    assert cas.work_record_id.endswith(claim.work.work_digest)
    assert cas.attempt_record_id.endswith(claim.attempt.attempt_digest)
    # Pointer and work fence the submitted successor; the proposal separately
    # retains the OPEN revision the user answered.
    assert cas.expected_conflict_revision == claim.work.conflict_revision
    assert claim.work.conflict_revision != claim.proposal.conflict_revision
    assert cas.ownership_epoch == claim.work.ownership_epoch
    records_after_claim = tuple(plane.list_records())
    assert store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="claim-owner"
    ) == claim
    assert tuple(plane.list_records()) == records_after_claim

    malformed_generation = SemanticConflictClarificationWorkGeneration.create(
        predecessor_work_digest=work.work_digest,
        work=store._claimed_clarification_work(
            work,
            owner_token="claim-owner",
            ownership_epoch=work.ownership_epoch,
            lease_expires_at=now[0] + timedelta(minutes=10),
        ),
    )
    malformed_work_record = store._projection_history._conflict_authority_record(
        "semantic_ingestion:conflict-authority:clarification-work:"
        f"{malformed_generation.predecessor_work_digest}",
        malformed_generation,
        now[0],
    )
    malformed_work_member = store._projection_history._conflict_authority_record(
        "semantic_ingestion:conflict-authority:clarification-work-member:"
        f"{malformed_generation.work.work_digest}",
        malformed_generation.work,
        now[0],
    )
    with pytest.raises(
        SemanticWriterAdmissionError,
        match="authorization authority transition is not isolated",
    ):
        plane.conditionally_write_records(
            (
                malformed_work_record,
                malformed_work_member,
                authorization_record("clarification-claim-extra-authorization-a"),
                authorization_record("clarification-claim-extra-authorization-b"),
            ),
            preconditions=(),
            authorization=writers._authorize_atomic(
                binding, capability=store._write_capability
            ),
        )
    assert tuple(plane.list_records()) == records_after_claim

    renewed = store.renew_conflict_clarification_claim(
        claim, lease_duration=timedelta(minutes=5)
    )
    assert renewed.attempt == claim.attempt
    assert renewed.work.ownership_epoch == claim.work.ownership_epoch
    assert renewed.work.work_revision == claim.work.work_revision + 1
    _assert_live_conflict_replay_binding(store)
    assert _replay_binding_records(plane) == replay_records_after_submission
    records_after_renew = tuple(plane.list_records())
    assert store.renew_conflict_clarification_claim(
        claim, lease_duration=timedelta(minutes=5)
    ) == renewed
    assert tuple(plane.list_records()) == records_after_renew

    wrong_owner = claim.model_copy(
        update={"work": claim.work.model_copy(update={"owner_token": "other-owner"})}
    )
    wrong_epoch = renewed.model_copy(
        update={
            "work": renewed.work.model_copy(
                update={"ownership_epoch": renewed.work.ownership_epoch + 1}
            )
        }
    )
    for stale in (wrong_owner, wrong_epoch):
        with pytest.raises(PreplanningStoreError):
            store.renew_conflict_clarification_claim(stale, lease_duration=timedelta(minutes=5))
        with pytest.raises(PreplanningStoreError):
            store.build_conflict_clarification_cas_input(stale)
    with pytest.raises(PreplanningStoreError):
        store.build_conflict_clarification_cas_input(claim)
    renewed_cas = store.build_conflict_clarification_cas_input(renewed)
    assert renewed_cas.work_record_id.endswith(renewed.work.work_digest)
    now[0] += timedelta(minutes=6)
    with pytest.raises(PreplanningStoreError):
        store.renew_conflict_clarification_claim(renewed, lease_duration=timedelta(minutes=5))
    with pytest.raises(PreplanningStoreError):
        store.build_conflict_clarification_cas_input(renewed)
    assert tuple(plane.list_records()) == records_after_renew
    # A lost acknowledgement is reusable only while the lease is live.  Once
    # it expires, the same token must traverse the fenced reclaim path rather
    # than receive the stale owned image back.
    reclaimed_same_token = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="claim-owner"
    )
    assert reclaimed_same_token is not None
    assert reclaimed_same_token.work.ownership_epoch == renewed.work.ownership_epoch + 1
    assert reclaimed_same_token.work.lease_expires_at > now[0]
    assert reclaimed_same_token.attempt.predecessor_attempt_digest == claim.attempt.attempt_digest
    if backend_kind == "jsonl":
        attempt_record = next(
            record
            for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
            if record.memory_id
            == "semantic_ingestion:conflict-authority:clarification-attempt-member:"
            f"{reclaimed_same_token.attempt.attempt_digest}"
        )
        backend = JsonlMemoryPlaneStore(storage)
        _rewrite_jsonl_snapshot(backend, plane, deleted_ids=(attempt_record.memory_id,))
        missing_attempt_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        missing_attempt_store = SemanticIngestionAtomicStore(
            missing_attempt_plane,
            SemanticWriterAdmissionStore(
                missing_attempt_plane,
                bounded_preplanning_ownership_manifest(),
                now_provider=lambda: now[0],
            ),
            now_provider=lambda: now[0],
        )
        missing_attempt_before = tuple(missing_attempt_plane.list_records())
        with pytest.raises(PreplanningStoreError):
            missing_attempt_store.build_conflict_clarification_cas_input(
                reclaimed_same_token
            )
        assert tuple(missing_attempt_plane.list_records()) == missing_attempt_before
        corrupt_attempt = attempt_record.model_copy(
            update={
                "content": {
                    **attempt_record.content,
                    "canonical_hex": "00",
                    "authority_digest": sha256(b"\0").hexdigest(),
                }
            }
        )
        _rewrite_jsonl_snapshot(backend, plane, replacements=(corrupt_attempt,))
        corrupt_attempt_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        corrupt_attempt_store = SemanticIngestionAtomicStore(
            corrupt_attempt_plane,
            SemanticWriterAdmissionStore(
                corrupt_attempt_plane,
                bounded_preplanning_ownership_manifest(),
                now_provider=lambda: now[0],
            ),
            now_provider=lambda: now[0],
        )
        corrupt_attempt_before = tuple(corrupt_attempt_plane.list_records())
        with pytest.raises(PreplanningStoreError):
            corrupt_attempt_store.build_conflict_clarification_cas_input(
                reclaimed_same_token
            )
        assert tuple(corrupt_attempt_plane.list_records()) == corrupt_attempt_before
        work_record = next(
            record
            for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
            if record.memory_id.startswith("semantic_ingestion:conflict-authority:clarification-work-member:")
        )
        backend = JsonlMemoryPlaneStore(storage)
        _rewrite_jsonl_snapshot(backend, plane, deleted_ids=(work_record.memory_id,))
        missing_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        missing_store = SemanticIngestionAtomicStore(
            missing_plane,
            SemanticWriterAdmissionStore(
                missing_plane,
                bounded_preplanning_ownership_manifest(),
                now_provider=lambda: now[0],
            ),
            now_provider=lambda: now[0],
        )
        with pytest.raises(PreplanningStoreError):
            missing_store.claim_next_conflict_clarification(
                lease_duration=timedelta(minutes=5), owner_token="different-owner"
            )
        corrupt = work_record.model_copy(
            update={
                "content": {
                    **work_record.content,
                    "canonical_hex": "00",
                    "authority_digest": sha256(b"\0").hexdigest(),
                }
            }
        )
        _rewrite_jsonl_snapshot(backend, plane, replacements=(corrupt,))
        reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        reopened_writers = SemanticWriterAdmissionStore(
            reopened, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
        )
        reopened_store = SemanticIngestionAtomicStore(
            reopened, reopened_writers, now_provider=lambda: now[0]
        )
        corrupt_records = tuple(reopened.list_records())
        with pytest.raises(PreplanningStoreError):
            reopened_store.claim_next_conflict_clarification(
                lease_duration=timedelta(minutes=5), owner_token="different-owner"
            )
        assert tuple(reopened.list_records()) == corrupt_records


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_claimed_clarification_insufficient_completion_is_one_canonical_closure(
    tmp_path, backend_kind: str, monkeypatch
) -> None:
    """A non-graph outcome still closes receipt, attempt, work, and pointer together."""
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path, backend=backend, complete=False
    )
    now = [NOW]
    plane = MemoryPlaneService(
        record_store=backend if backend is not None else JsonlMemoryPlaneStore(storage)
    )
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now[0])
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="completion-owner"
    )
    assert claim is not None
    cas = store.build_conflict_clarification_cas_input(claim)
    successor_revision = sha256(b"clarification-insufficient-successor").hexdigest()
    prior_event_batches = tuple(
        plane.list_records(source_kind="semantic_ingestion_event_batch")
    )
    writes = []
    original_write = plane.conditionally_write_records

    def capture_completion_write(records, *, preconditions=(), authorization=None):
        writes.append(tuple(records))
        return original_write(
            records, preconditions=preconditions, authorization=authorization
        )

    monkeypatch.setattr(plane, "conditionally_write_records", capture_completion_write)
    receipt = store.commit_conflict_clarification_transaction(
        proposal=claim.proposal,
        processing_operation_id=claim.work.processing_operation_id,
        resulting_conflict_revision=successor_revision,
        policy_fingerprint=claim.work.policy_fingerprint,
        committed_outcome="insufficient",
        semantic_result_digest=sha256(b"insufficient-result").hexdigest(),
        clarification_cas=cas,
    )
    after = tuple(plane.list_records())
    assert len(writes) == 1
    assert tuple(plane.list_records(source_kind="semantic_ingestion_event_batch")) == prior_event_batches
    _assert_retry_returns_committed_receipt(
        store.commit_conflict_clarification_transaction(
            proposal=claim.proposal,
            processing_operation_id=claim.work.processing_operation_id,
            resulting_conflict_revision=successor_revision,
            policy_fingerprint=claim.work.policy_fingerprint,
            committed_outcome="insufficient",
            semantic_result_digest=sha256(b"insufficient-result").hexdigest(),
            clarification_cas=cas,
        ),
        receipt,
    )
    assert tuple(plane.list_records()) == after
    assert store._projection_history.current_clarification_work() == {}


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
@pytest.mark.parametrize("outcome", ("accepted", "rejected", "insufficient"))
def test_claimed_clarification_terminal_completion_is_one_real_store_closure(
    tmp_path, backend_kind: str, outcome: str, monkeypatch
) -> None:
    """The claimed queue, conflict pointer, and semantic effect commit together."""
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path, backend=backend, complete=False
    )
    plane = MemoryPlaneService(
        record_store=backend if backend is not None else JsonlMemoryPlaneStore(storage)
    )
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
        ),
        now_provider=lambda: NOW,
        semantic_conflict_authority_resolver=_TestSemanticConflictAuthorityResolver(plane),
    )
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token=f"completion-{outcome}"
    )
    assert claim is not None
    cas = store.build_conflict_clarification_cas_input(claim)
    terminal = (
        _with_claim_record_version(
            accepted_terminal(
                operation_id=claim.work.processing_operation_id,
                source_id=claim.proposal.source_user_event_id,
                source_digest=claim.proposal.source_user_event_digest,
                object_logical_entity_id="entity:clarified",
                object_entity_revision_id="entity-revision:clarified:v1",
            ),
            record_version=2,
        )
        if outcome == "accepted"
        else (
            _nonaccepted(
                claim.work.processing_operation_id,
                status="rejected",
                reason_codes=("policy_rejected",),
            )
            if outcome == "rejected"
            else None
        )
    )
    semantic_result_digest = (
        terminal.terminal_digest
        if terminal is not None
        else sha256(b"clarification-insufficient-result").hexdigest()
    )
    successor_revision = sha256(f"completion:{backend_kind}:{outcome}".encode()).hexdigest()
    prior_event_batches = store.semantic_event_batches()
    writes: list[tuple[CanonicalMemoryRecord, ...]] = []
    original_write = plane.conditionally_write_records

    def capture_completion_write(records, *, preconditions=(), authorization=None):
        writes.append(tuple(records))
        return original_write(records, preconditions=preconditions, authorization=authorization)

    monkeypatch.setattr(plane, "conditionally_write_records", capture_completion_write)
    receipt = store.commit_conflict_clarification_transaction(
        proposal=claim.proposal,
        processing_operation_id=claim.work.processing_operation_id,
        resulting_conflict_revision=successor_revision,
        policy_fingerprint=claim.work.policy_fingerprint,
        committed_outcome=outcome,
        semantic_result_digest=semantic_result_digest,
        semantic_terminal=terminal,
        clarification_cas=cas,
    )
    assert len(writes) == 1
    completion_kinds = {record.source_kind for record in writes[0]}
    assert {
        "semantic_ingestion_conflict_clarification_transaction",
        "semantic_ingestion_conflict_clarification_receipt",
        "semantic_ingestion_conflict_authority",
    } <= completion_kinds
    if outcome == "accepted":
        assert {
            "semantic_ingestion_event_batch",
            "semantic_ingestion_replay_state",
            "semantic_ingestion_replay_authority",
            "semantic_ingestion_checkpoint_lifecycle",
            "semantic_ingestion_event_schema_registry_history",
        } <= completion_kinds
        assert any("projection" in kind for kind in completion_kinds)
        assert store.semantic_event_batches()
    else:
        assert "semantic_ingestion_event_batch" not in completion_kinds
        assert store.semantic_event_batches() == prior_event_batches
    records_after = tuple(plane.list_records())
    assert store.resolve_conflict_clarification_receipt(claim.work.processing_operation_id) == receipt
    assert store._projection_history.current_clarification_work() == {}
    current = store._projection_history._current_semantic_conflicts()[claim.work.conflict_id][1]
    assert isinstance(current, SemanticConflictClarificationTransition)
    assert current.reason.value == outcome
    assert current.resulting_attention.status is (
        ConflictStatus.RESOLVED if outcome == "accepted" else ConflictStatus.OPEN
    )
    _assert_retry_returns_committed_receipt(
        store.commit_conflict_clarification_transaction(
            proposal=claim.proposal,
            processing_operation_id=claim.work.processing_operation_id,
            resulting_conflict_revision=successor_revision,
            policy_fingerprint=claim.work.policy_fingerprint,
            committed_outcome=outcome,
            semantic_result_digest=semantic_result_digest,
            semantic_terminal=terminal,
            clarification_cas=cas,
        ),
        receipt,
    )
    assert tuple(plane.list_records()) == records_after
    _assert_live_conflict_replay_binding(store)
    if backend_kind == "jsonl":
        reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        reopened = SemanticIngestionAtomicStore(
            reopened_plane,
            SemanticWriterAdmissionStore(
                reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
            ),
            now_provider=lambda: NOW,
            semantic_conflict_authority_resolver=_TestSemanticConflictAuthorityResolver(
                reopened_plane
            ),
        )
        assert reopened.resolve_conflict_clarification_receipt(claim.work.processing_operation_id) == receipt
        assert reopened._projection_history.current_clarification_work() == {}
        _assert_live_conflict_replay_binding(reopened)


def _completed_rejected_clarification(tmp_path, *, backend_kind: str):
    """Return one real terminal closure and the exact lost-ack retry inputs."""

    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path, backend=backend, complete=False
    )
    plane = MemoryPlaneService(
        record_store=backend if backend is not None else JsonlMemoryPlaneStore(storage)
    )
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
        ),
        now_provider=lambda: NOW,
    )
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="retained-corruption-owner"
    )
    assert claim is not None
    cas = store.build_conflict_clarification_cas_input(claim)
    terminal = _nonaccepted(
        claim.work.processing_operation_id,
        status="rejected",
        reason_codes=("policy_rejected",),
    )
    receipt = store.commit_conflict_clarification_transaction(
        proposal=claim.proposal,
        processing_operation_id=claim.work.processing_operation_id,
        resulting_conflict_revision=sha256(
            f"retained-corruption:{backend_kind}".encode()
        ).hexdigest(),
        policy_fingerprint=claim.work.policy_fingerprint,
        committed_outcome="rejected",
        semantic_result_digest=terminal.terminal_digest,
        semantic_terminal=terminal,
        clarification_cas=cas,
    )
    return storage, backend, plane, store, claim, cas, terminal, receipt


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
@pytest.mark.parametrize(
    "mutation",
    (
        "missing_receipt",
        "missing_terminal_generation",
        "missing_terminal_pointer",
        "divergent_replay_aggregate",
    ),
)
def test_completed_clarification_retained_authority_corruption_fails_closed(
    tmp_path,
    backend_kind: str,
    mutation: str,
) -> None:
    """No retained completion component may be silently repaired or replayed."""

    storage, backend, plane, store, claim, cas, terminal, _ = _completed_rejected_clarification(
        tmp_path, backend_kind=backend_kind
    )
    records = {record.memory_id: record for record in plane.list_records()}
    deleted_ids: tuple[str, ...] = ()
    operation_id = claim.work.processing_operation_id
    if mutation == "missing_receipt":
        deleted_ids = (f"semantic_ingestion:clarification:receipt:{operation_id}",)
        del records[deleted_ids[0]]
    elif mutation == "missing_terminal_generation":
        generation_id = next(
            memory_id
            for memory_id, record in records.items()
            if memory_id.startswith("semantic_ingestion:conflict-authority:clarification-work:")
            and not memory_id.startswith(
                "semantic_ingestion:conflict-authority:clarification-work-member:"
            )
            and (
                decode_persisted_conflict_generation(
                    decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
                    SemanticConflictClarificationWorkGeneration,
                ).attempt_result is not None
            )
        )
        deleted_ids = (generation_id,)
        del records[generation_id]
    elif mutation == "missing_terminal_pointer":
        deleted_ids = (
            f"semantic_ingestion:conflict-authority:pointer:{claim.work.conflict_id}",
        )
        del records[deleted_ids[0]]
    else:
        aggregate_id = "semantic_ingestion:event-authority:aggregate"
        aggregate = records[aggregate_id]
        records[aggregate_id] = aggregate.model_copy(
            update={
                "content": aggregate.content
                | {"canonical_hex": "00", "aggregate_digest": "0" * 64}
            }
        )

    if backend_kind == "memory":
        assert isinstance(backend, InMemoryMemoryPlaneStore)
        # Model an out-of-band durable-store corruption without invoking the
        # governed write path.  The test must mutate the backend the service
        # actually reads, not a stale snapshot or an adapter cache.
        with backend._lock:
            backend._records = dict(records)
        corrupt_plane = plane
        corrupt_store = store
    else:
        jsonl = JsonlMemoryPlaneStore(storage)
        _rewrite_jsonl_snapshot(
            jsonl,
            plane,
            replacements=tuple(records.values()),
            deleted_ids=deleted_ids,
        )
        corrupt_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        corrupt_store = SemanticIngestionAtomicStore(
            corrupt_plane,
            SemanticWriterAdmissionStore(
                corrupt_plane,
                bounded_preplanning_ownership_manifest(),
                now_provider=lambda: NOW,
            ),
            now_provider=lambda: NOW,
        )
    for memory_id in deleted_ids:
        assert corrupt_plane.get_record(memory_id) is None
    if mutation == "divergent_replay_aggregate":
        aggregate = corrupt_plane.get_record("semantic_ingestion:event-authority:aggregate")
        assert aggregate is not None
        assert aggregate.content["canonical_hex"] == "00"
        assert aggregate.content["aggregate_digest"] == "0" * 64
    corrupt_before = tuple(corrupt_plane.list_records())
    with pytest.raises(PreplanningStoreError):
        corrupt_store.commit_conflict_clarification_transaction(
            proposal=claim.proposal,
            processing_operation_id=operation_id,
            resulting_conflict_revision=sha256(
                f"retained-corruption:{backend_kind}".encode()
            ).hexdigest(),
            policy_fingerprint=claim.work.policy_fingerprint,
            committed_outcome="rejected",
            semantic_result_digest=terminal.terminal_digest,
            semantic_terminal=terminal,
            clarification_cas=cas,
        )
    assert tuple(corrupt_plane.list_records()) == corrupt_before
    if mutation == "divergent_replay_aggregate":
        with pytest.raises(
            SemanticEventReplayError,
            match="semantic replay authority validation failed",
        ):
            corrupt_store.semantic_replay_authority()
    else:
        with pytest.raises(PreplanningStoreError):
            corrupt_store.semantic_replay_authority()
    assert tuple(corrupt_plane.list_records()) == corrupt_before
    # Queue authority is independent from the replay aggregate, so only the
    # two queue mutations are expected to fail the projection-history reader.
    if mutation in {"missing_terminal_generation", "missing_terminal_pointer"}:
        with pytest.raises(ProjectionHistoryError):
            corrupt_store._projection_history.current_clarification_work()
        assert tuple(corrupt_plane.list_records()) == corrupt_before


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_clarification_completion_rejects_stale_claim_fences_without_writes(
    tmp_path, backend_kind: str, monkeypatch
) -> None:
    """Every retained claim fence is checked before the completion transaction exists."""
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path, backend=backend, complete=False
    )
    now = [NOW]
    plane = MemoryPlaneService(
        record_store=(backend if backend is not None else JsonlMemoryPlaneStore(storage))
    )
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
        ),
        now_provider=lambda: now[0],
        semantic_conflict_authority_resolver=_TestSemanticConflictAuthorityResolver(plane),
    )
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="stale-completion-owner"
    )
    assert claim is not None
    cas = store.build_conflict_clarification_cas_input(claim)
    terminal = _with_claim_record_version(
        accepted_terminal(
            operation_id=claim.work.processing_operation_id,
            source_id=claim.proposal.source_user_event_id,
            source_digest=claim.proposal.source_user_event_digest,
            object_logical_entity_id="entity:stale-fence",
            object_entity_revision_id="entity-revision:stale-fence:v1",
        ),
        record_version=2,
    )
    writes = []
    original_write = plane.conditionally_write_records

    def capture_write(records, *, preconditions=(), authorization=None):
        writes.append(tuple(records))
        return original_write(records, preconditions=preconditions, authorization=authorization)

    monkeypatch.setattr(plane, "conditionally_write_records", capture_write)
    for mutation, expired in (
        (("expected_pointer_digest", "0" * 64), False),
        (("expected_pointer_revision", 3), False),
        (("work_record_id", "semantic_ingestion:conflict-authority:clarification-work-member:missing"), False),
        (("work_record_digest", "0" * 64), False),
        (("attempt_record_id", "semantic_ingestion:conflict-authority:clarification-attempt-member:missing"), False),
        (("attempt_record_digest", "0" * 64), False),
        (("owner_token_digest", "0" * 64), False),
        (("ownership_epoch", 2), False),
        ((None, None), True),
    ):
        candidate = cas
        if mutation[0] is not None:
            values = cas.model_dump(mode="python", exclude={"input_digest"})
            values[mutation[0]] = mutation[1]
            candidate = type(cas).create(**values)
        if expired:
            now[0] += timedelta(minutes=6)
        before = tuple(plane.list_records())
        with pytest.raises(PreplanningStoreError):
            store.commit_conflict_clarification_transaction(
                proposal=claim.proposal,
                processing_operation_id=claim.work.processing_operation_id,
                resulting_conflict_revision=sha256(b"stale-clarification-completion").hexdigest(),
                policy_fingerprint=claim.work.policy_fingerprint,
                committed_outcome="accepted",
                semantic_result_digest=terminal.terminal_digest,
                semantic_terminal=terminal,
                clarification_cas=candidate,
            )
        assert not writes
        assert tuple(plane.list_records()) == before


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_queue_only_clarification_work_rejects_semantic_or_superseded_closures(
    tmp_path, backend_kind: str
) -> None:
    """Queue-only writes cannot invent terminal semantic/audit results."""
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path, backend=backend, complete=False
    )
    plane = MemoryPlaneService(
        record_store=(backend if backend_kind == "memory" else JsonlMemoryPlaneStore(storage))
    )
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
        ),
        now_provider=lambda: NOW,
    )
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="forbidden-outcome-owner"
    )
    assert claim is not None
    released_values = claim.work.model_dump(mode="python", exclude={"work_digest"})
    released_values.update(
        owner_token=None,
        lease_expires_at=None,
        work_revision=claim.work.work_revision + 1,
        predecessor_work_digest=claim.work.work_digest,
    )
    released = store._clarification_work_from_values(released_values)
    for outcome in (
        ClarificationAttemptOutcome.ACCEPTED,
        ClarificationAttemptOutcome.REJECTED,
        ClarificationAttemptOutcome.INSUFFICIENT,
        ClarificationAttemptOutcome.SUPERSEDED,
    ):
        values = {
            "attempt_id": claim.attempt.attempt_id,
            "attempt_digest": claim.attempt.attempt_digest,
            "processing_operation_id": claim.attempt.processing_operation_id,
            "ownership_epoch": claim.attempt.ownership_epoch,
            "owner_token_digest": claim.attempt.owner_token_digest,
            "outcome": outcome,
            "attempt_count_after": claim.work.attempt_count,
            "downstream_receipt_digest": (
                sha256(b"semantic-completion-receipt").hexdigest()
                if outcome is not ClarificationAttemptOutcome.SUPERSEDED
                else None
            ),
            "superseded_by_conflict_revision": (
                sha256(b"superseding-projection").hexdigest()
                if outcome is ClarificationAttemptOutcome.SUPERSEDED
                else None
            ),
            "completed_at": NOW,
        }
        provisional = ConflictClarificationAttemptResult.model_construct(
            **values, result_digest="0" * 64
        )
        result = ConflictClarificationAttemptResult(
            **values,
            result_digest=sha256(
                b"memorii.conflict-clarification-attempt-result.v1\0"
                + encode_typed_value(
                    provisional.model_dump(mode="json", exclude={"result_digest"})
                )
            ).hexdigest(),
        )
        forbidden = SemanticConflictClarificationWorkGeneration.create(
            predecessor_work_digest=claim.work.work_digest,
            work=released,
            attempt_result=result,
        )
        before = tuple(plane.list_records())
        with pytest.raises(PreplanningStoreError):
            store.append_conflict_clarification_work_generation(forbidden)
        assert tuple(plane.list_records()) == before


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_canonical_clarification_failure_reclaim_and_exhaustion_are_fenced(
    tmp_path, backend_kind: str, monkeypatch
) -> None:
    """Retry, expiry, and exhaustion remain one immutable predecessor chain."""
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path, backend=backend, complete=False
    )
    now = [NOW]
    plane = MemoryPlaneService(
        record_store=(backend if backend_kind == "memory" else JsonlMemoryPlaneStore(storage))
    )
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: now[0])
    _assert_live_conflict_replay_binding(store)
    replay_records_after_submission = _replay_binding_records(plane)

    first = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="retry-owner-one"
    )
    assert first is not None
    first_failure = store.fail_conflict_clarification_claim(
        first, retryable=True, completed_at=now[0]
    )
    assert first_failure.work.owner_token is None
    assert first_failure.work.attempt_count == 1
    assert first_failure.attempt_result is not None
    assert first_failure.attempt_result.outcome.value == "retryable_failure"
    _assert_live_conflict_replay_binding(store)
    assert _replay_binding_records(plane) == replay_records_after_submission
    retained_records = tuple(plane.list_records())
    assert store.fail_conflict_clarification_claim(
        first, retryable=True, completed_at=now[0]
    ) == first_failure
    assert tuple(plane.list_records()) == retained_records

    second = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="retry-owner-two"
    )
    assert second is not None and second.work.attempt_count == 1
    now[0] += timedelta(minutes=6)
    reclaimed = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="reclaim-owner"
    )
    assert reclaimed is not None
    assert reclaimed.work.attempt_count == 1
    assert reclaimed.attempt.predecessor_attempt_digest == second.attempt.attempt_digest
    before_stale_failure = tuple(plane.list_records())
    with pytest.raises(PreplanningStoreError):
        store.fail_conflict_clarification_claim(second, retryable=True, completed_at=now[0])
    assert tuple(plane.list_records()) == before_stale_failure

    second_failure = store.fail_conflict_clarification_claim(
        reclaimed, retryable=True, completed_at=now[0]
    )
    assert second_failure.work.attempt_count == 2
    third = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="retry-owner-three"
    )
    assert third is not None and third.work.attempt_count == 2
    # Capture the canonical exhaustion closure before storage sees it.  A work
    # generation with a processing-exhausted transition must never be accepted
    # as a detached queue update or with a substituted pointer-history member.
    original_write = plane.conditionally_write_records
    captured: dict[str, object] = {}

    def capture_exhaustion_write(records, *, preconditions, authorization):
        captured["records"] = records
        captured["authorization"] = authorization
        raise MemoryPlaneRevisionConflictError("capture exhaustion closure")

    monkeypatch.setattr(plane, "conditionally_write_records", capture_exhaustion_write)
    with pytest.raises(PreplanningStoreError):
        store.fail_conflict_clarification_claim(
            third, retryable=True, completed_at=now[0]
        )
    monkeypatch.setattr(plane, "conditionally_write_records", original_write)
    exhaustion_records = tuple(captured["records"])
    exhaustion_authorization = captured["authorization"]
    before_malformed = tuple(plane.list_records())
    detached_records = tuple(
        record
        for record in exhaustion_records
        if record.content.get("authority_record_type")
        in {
            "clarification_work",
            "clarification_work_member",
            "clarification_attempt_result_member",
        }
    )
    with pytest.raises(SemanticWriterAdmissionError):
        original_write(
            detached_records,
            preconditions=(),
            authorization=exhaustion_authorization,
        )
    assert tuple(plane.list_records()) == before_malformed
    pointer_history = next(
        record
        for record in exhaustion_records
        if record.content.get("authority_record_type") == "pointer_history"
    )
    active_pointer = next(
        record
        for record in exhaustion_records
        if record.content.get("authority_record_type") == "active_pointer"
    )
    mismatched_records = tuple(
        record.model_copy(update={"content": active_pointer.content})
        if record == pointer_history
        else record
        for record in exhaustion_records
    )
    with pytest.raises(SemanticWriterAdmissionError):
        original_write(
            mismatched_records,
            preconditions=(),
            authorization=exhaustion_authorization,
        )
    assert tuple(plane.list_records()) == before_malformed
    exhausted = store.fail_conflict_clarification_claim(
        third, retryable=True, completed_at=now[0]
    )
    assert exhausted.transition is not None
    assert exhausted.transition.reason.value == "processing_exhausted"
    _assert_live_conflict_replay_binding(store)
    assert store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="after-exhaustion"
    ) is None
    if backend_kind == "jsonl":
        reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        reopened_store = SemanticIngestionAtomicStore(
            reopened,
            SemanticWriterAdmissionStore(
                reopened, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
            ),
            now_provider=lambda: now[0],
        )
        assert reopened_store.claim_next_conflict_clarification(
            lease_duration=timedelta(minutes=5), owner_token="after-reopen"
        ) is None
        result_record = next(
            record
            for record in reopened.list_records(source_kind="semantic_ingestion_conflict_authority")
            if record.memory_id.startswith(
                "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
            )
        )
        malformed = decode_typed_value(
            bytes.fromhex(str(result_record.content["canonical_hex"]))
        )
        assert isinstance(malformed, dict)
        malformed["outcome"] = "unknown_attempt_outcome"
        malformed_bytes = encode_typed_value(malformed)
        corrupt_result_record = result_record.model_copy(
            update={
                "content": result_record.content
                | {
                    "canonical_hex": malformed_bytes.hex(),
                    "authority_digest": sha256(malformed_bytes).hexdigest(),
                }
            }
        )
        _rewrite_jsonl_snapshot(
            JsonlMemoryPlaneStore(storage),
            reopened,
            replacements=(corrupt_result_record,),
        )
        corrupt_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        corrupt_store = SemanticIngestionAtomicStore(
            corrupt_plane,
            SemanticWriterAdmissionStore(
                corrupt_plane,
                bounded_preplanning_ownership_manifest(),
                now_provider=lambda: now[0],
            ),
            now_provider=lambda: now[0],
        )
        corrupt_before = tuple(corrupt_plane.list_records())
        with pytest.raises(PreplanningStoreError):
            corrupt_store.claim_next_conflict_clarification(
                lease_duration=timedelta(minutes=5), owner_token="corrupt-result"
            )
        assert tuple(corrupt_plane.list_records()) == corrupt_before


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_terminal_clarification_failure_ceases_claimability_without_pointer_edge(
    tmp_path, backend_kind: str
) -> None:
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path, backend=backend, complete=False
    )
    now = [NOW]
    plane = MemoryPlaneService(
        record_store=(backend if backend_kind == "memory" else JsonlMemoryPlaneStore(storage))
    )
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
        ),
        now_provider=lambda: now[0],
    )
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="terminal-owner"
    )
    assert claim is not None
    terminal = store.fail_conflict_clarification_claim(
        claim, retryable=False, completed_at=now[0]
    )
    assert terminal.transition is None
    assert terminal.work.last_failure_class is not None
    assert terminal.work.last_failure_class.value == "terminal"
    assert store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="terminal-retry"
    ) is None


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_exhausted_generation_cannot_extend_after_fresh_resubmission(
    tmp_path, backend_kind: str
) -> None:
    """A new user answer fences stale work from the exhausted answer chain."""
    backend = InMemoryMemoryPlaneStore() if backend_kind == "memory" else None
    storage, introduction, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path, backend=backend, complete=False
    )
    now = [NOW]
    plane = MemoryPlaneService(
        record_store=(backend if backend_kind == "memory" else JsonlMemoryPlaneStore(storage))
    )
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: now[0]
        ),
        now_provider=lambda: now[0],
    )
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="exhaustion-owner"
    )
    assert claim is not None
    store.fail_conflict_clarification_claim(claim, retryable=True, completed_at=now[0])
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="exhaustion-owner-two"
    )
    assert claim is not None
    store.fail_conflict_clarification_claim(claim, retryable=True, completed_at=now[0])
    stale_claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="exhaustion-owner-three"
    )
    assert stale_claim is not None
    exhausted = store.fail_conflict_clarification_claim(
        stale_claim, retryable=True, completed_at=now[0]
    )
    assert exhausted.transition is not None
    operation_id = "clarification-resubmission"
    source_user_event_id = "clarification-resubmission-source"
    request = ConflictResolutionRequest(
        conflict_id=introduction.conflict_id,
        expected_conflict_revision=exhausted.transition.resulting_attention.conflict_revision,
        operation_id=operation_id,
        action=ConflictResolutionAction.NEITHER,
        selected_candidate_ids=(),
        validity_intervals=(),
        source_user_event_id=source_user_event_id,
    )
    proposal = build_agent_clarification_proposal(
        request,
        source_user_event_digest=sha256(source_user_event_id.encode()).hexdigest(),
        agent_principal_id="clarification-principal",
        scope_digest=introduction.scope.scope_digest,
    )
    resubmitted = _clarification_transition(
        introduction=introduction,
        predecessor_digest=exhausted.transition.transition_digest,
        predecessor_revision=exhausted.transition.resulting_attention.conflict_revision,
        predecessor_status=ConflictStatus.OPEN,
        status=ConflictStatus.CLARIFICATION_SUBMITTED,
        reason=SemanticConflictClarificationTransitionReason.SUBMITTED,
        record_coordinate=store.projection_history.semantic_conflict_replay_binding().immutable_record_count + 1,
        proposal_digest=proposal.proposal_digest,
    )
    store.submit_conflict_clarification_generation(
        _clarification_submission_generation(
            introduction,
            resubmitted,
            expected_conflict_revision=exhausted.transition.resulting_attention.conflict_revision,
            operation_id=operation_id,
            source_user_event_id=source_user_event_id,
        )
    )
    stale_successor = SemanticConflictClarificationWorkGeneration.create(
        predecessor_work_digest=stale_claim.work.work_digest,
        work=store._claimed_clarification_work(
            stale_claim.work,
            owner_token="stale-owner",
            ownership_epoch=stale_claim.work.ownership_epoch,
            lease_expires_at=now[0] + timedelta(minutes=5),
        ),
    )
    before = tuple(plane.list_records())
    with pytest.raises(PreplanningStoreError):
        store.append_conflict_clarification_work_generation(stale_successor)
    assert tuple(plane.list_records()) == before
    assert store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="fresh-owner"
    ) is not None


def _retained_authority_batches(
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
    for record in plane.list_records(source_kind=("semantic_ingestion_conflict_clarification_recovery_authority")):
        canonical_bytes = bytes.fromhex(record.content["event_batch_canonical_hex"])
        batch = decode_semantic_memory_event_batch(
            canonical_bytes,
            registry=store.event_schema_registry,
        )
        retained.append(
            (
                batch.log_position.sequence,
                SemanticEventCleanAuthorityBatch(
                    source_id=(f"semantic_ingestion:event-authority:batch:{batch.log_position.sequence:020d}"),
                    canonical_batch_bytes=canonical_bytes,
                    source_digest=sha256(canonical_bytes).hexdigest(),
                ),
            )
        )
    retained.sort(key=lambda item: item[0])
    assert tuple(sequence for sequence, _ in retained) == tuple(range(1, len(retained) + 1))
    return tuple(authority for _, authority in retained)


def test_store_commits_only_accepted_exact_effect_closure() -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    group = store.generation_members(fence, 3)
    assert {value.kind for value in group} == {
        "artifact_closure",
        "artifact_index",
        "event_batch",
        "graph_delta",
        "group_result",
        "observation_delta",
    }
    control = store.get_operation(fence)
    assert control.state == "terminal"
    assert control.graph_revision != "genesis" and control.observation_revision != "genesis"
    event_member = next(value for value in group if value.kind == "event_batch")
    event_batch = decode_semantic_memory_event_batch(
        event_member.canonical_payload, registry=store.event_schema_registry
    )
    assert store.semantic_event_batches() == (event_batch,)
    replay_state = store.semantic_replay_state()
    assert replay_state.graph_revision == control.graph_revision
    assert replay_state.last_event_batch_digest == event_batch.event_batch_digest
    assert len(replay_state.materialized_records) == len(event_batch.events)
    authority = store.semantic_replay_authority()
    assert authority.graph_state == replay_state
    assert authority.latest_checkpoint is not None
    assert authority.observation_bindings
    assert authority.artifact_bindings
    assert authority.aggregate_revision == 3
    assert authority.projection_history_bindings == (store.projection_history.replay_bindings())
    assert terminal.arbitration_policy_bundle is not None
    assert (
        store.projection_history.current_temporal(
            policy_fingerprint=(terminal.arbitration_policy_bundle.temporal_policy.fingerprint),
        ).generation.base_graph_revision
        == replay_state.graph_revision
    )
    assert (
        store.projection_history.current_trust(
            policy_fingerprint=(terminal.arbitration_policy_bundle.trust_policy.fingerprint),
        ).generation.base_graph_revision
        == replay_state.graph_revision
    )


def test_reference_ledger_advances_in_the_same_committed_event_transaction() -> None:
    _, _, store, binding, fence, service, repository = _setup(verified=True)
    bootstrap = store.bootstrap_reference_integrity(writer_binding=binding)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)

    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)

    advanced = store.reference_integrity_snapshot()
    assert advanced.ledger_digest != bootstrap.ledger_digest
    assert advanced.audit_certificate is not None
    assert advanced.audit_certificate.graph_revision == store.semantic_replay_state().graph_revision
    assert {entry.target.kind for entry in advanced.entries} == {
        "entity_revision",
        "logical_entity",
    }


def test_reference_ledger_uses_the_atomic_store_commit_clock() -> None:
    current = [NOW]
    plane, _, store, binding, fence, service, repository = _setup(
        verified=True,
        now_provider=lambda: current[0],
    )
    bootstrap = store.bootstrap_reference_integrity(writer_binding=binding)
    assert bootstrap.audit_certificate is not None
    assert bootstrap.audit_certificate.completed_at == NOW
    ledger_id = "semantic_ingestion:reference-integrity:ledger"
    assert plane.get_record(ledger_id).timestamp == NOW

    current[0] = NOW + timedelta(minutes=7)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )

    advanced = store.reference_integrity_snapshot()
    assert advanced.audit_certificate is not None
    assert advanced.audit_certificate.completed_at == current[0]
    assert (
        plane.get_record(ledger_id).timestamp == current[0]
    )


def test_populated_reference_bootstrap_survives_jsonl_reopen(tmp_path) -> None:
    storage = tmp_path / "populated-reference-bootstrap"
    plane, _, store, binding, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )

    activated = store.bootstrap_reference_integrity(writer_binding=binding)
    replay_state = store.semantic_replay_state()
    assert activated.audit_certificate is not None
    assert activated.audit_certificate.graph_revision == replay_state.graph_revision
    assert activated.audit_certificate.base_record_count == len(
        replay_state.materialized_records
    )
    assert activated.entries
    validate_reference_integrity_converse(activated, replay_state)

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    reopened = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    assert reopened.reference_integrity_snapshot() == activated
    assert (
        reopened.bootstrap_reference_integrity(writer_binding=reopened_binding)
        == activated
    )
    validate_reference_integrity_converse(
        reopened.reference_integrity_snapshot(), reopened.semantic_replay_state()
    )


def test_reference_bootstrap_catches_up_racing_terminal_and_reopens(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = tmp_path / "racing-reference-bootstrap"
    plane, _, store, binding, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original_write = plane.conditionally_write_records
    committed_during_audit = False

    def race_terminal_before_ledger(records, **kwargs):
        nonlocal committed_during_audit
        if (
            not committed_during_audit
            and records
            and records[0].source_kind
            == "semantic_ingestion_reference_integrity"
        ):
            committed_during_audit = True
            service.persist(
                fence=fence,
                terminal=terminal,
                authorization_verifier=AUTHORIZATION,
            )
        return original_write(records, **kwargs)

    monkeypatch.setattr(
        plane, "conditionally_write_records", race_terminal_before_ledger
    )
    activated = store.bootstrap_reference_integrity(writer_binding=binding)

    assert committed_during_audit
    replay_state = store.semantic_replay_state()
    assert replay_state.graph_revision != "genesis"
    assert activated.audit_certificate is not None
    assert activated.audit_certificate.graph_revision == replay_state.graph_revision
    assert activated.entries
    validate_reference_integrity_converse(activated, replay_state)

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    assert reopened_store.reference_integrity_snapshot() == activated
    validate_reference_integrity_converse(
        reopened_store.reference_integrity_snapshot(),
        reopened_store.semantic_replay_state(),
    )


def test_reference_ledger_failure_leaves_no_partial_event_or_graph_state(monkeypatch) -> None:
    plane, _, store, binding, fence, service, repository = _setup(verified=True)
    store.bootstrap_reference_integrity(writer_binding=binding)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    before_state = store.semantic_replay_state()
    before_ledger = store.reference_integrity_snapshot()

    def fail_ledger(*args, **kwargs):
        raise ValueError("injected ledger failure")

    monkeypatch.setattr(
        "memorii.core.memory_evolution.reference_integrity.advance_reference_integrity",
        fail_ledger,
    )
    with pytest.raises(ValueError, match="terminal-group retry budget exhausted"):
        service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)

    assert store.semantic_replay_state() == before_state
    assert store.reference_integrity_snapshot() == before_ledger
    assert store.semantic_event_batches() == ()


class _AcceptedIdentityArtifactRepository:
    def __init__(self, factory, *, fence, graph_revision: str) -> None:
        self._factory = factory
        self._fence = fence
        self._graph_revision = graph_revision
        self.artifact: AcceptedIdentityOperationArtifact | None = None

    def get_accepted_identity_operation(self, **bindings):
        accepted = self._factory(bindings["operation_id"])
        reservations = []
        for successor in accepted.successors:
            keys = tuple(sorted((
                f"entity_revision:{successor.entity_revision_id}",
                f"logical_entity:{successor.logical_entity_id}",
            )))
            extension = GraphReadSetExtension.create(
                snapshot_token="test-snapshot",
                graph_revision=self._graph_revision,
                segment_governance_binding_digests=(),
                operation_fence_id=self._fence.operation_fence_id,
                issuer_repository_id="semantic_ingestion",
                issuer_contract_fingerprint="4" * 64,
                dependency_kind="identity_allocation",
                record_keys=keys,
                partition_versions=(),
                manifest_fingerprints=(canonical_graph_codec_manifest().manifest_fingerprint,),
            )
            reservations.append(PlannedIdentityReservation.create(
                planned_identity=PlannedEntityIdentity(
                    allocation_key=successor.entity_revision_id,
                    entity_revision_id=successor.entity_revision_id,
                    logical_entity_id=successor.logical_entity_id,
                    allocation_namespace_id="test",
                    allocation_policy_fingerprint="5" * 64,
                ),
                collision_read_set_extension=extension,
                expected_absent_write_intents=tuple(
                    GraphWriteIntent(record_key=key, expected_before_digest=None)
                    for key in keys
                ),
            ))
        alias_payload = None
        if accepted.operation == "alias":
            alias_payload = SourceGroundedAliasPayload.create(
                alias_namespace="test",
                normalized_alias_key="alias",
                entity_revision_id="alias-target:v1",
                logical_entity_id="alias-target",
                source_evidence=accepted.source_evidence,
            )
        self.artifact = AcceptedIdentityOperationArtifact.create(
            operation=accepted,
            operation_fence_id=self._fence.operation_fence_id,
            sealed_operation_digest=bindings["sealed_operation_digest"],
            candidate_digest=bindings["candidate_digest"],
            source_analysis_digest=bindings["source_analysis_digest"],
            source_evidence_digests=tuple(
                sorted(item.evidence_digest for item in accepted.source_evidence)
            ),
            semantic_authorization_read_set_digest="6" * 64,
            authority_digest="7" * 64,
            verified_decision_digest="8" * 64,
            authority_record_id="authority:test",
            authority_record_digest="9" * 64,
            authority_verification_digest="7" * 64,
            successor_reservations=tuple(reservations),
            alias_payload=alias_payload,
        )
        return self.artifact


def _trusted_identity_terminal(
    *,
    store,
    writers,
    fence,
    operation_kind: str,
    predecessors: tuple[LineageEntityIdentity, ...],
    successors: tuple[LineageEntityIdentity, ...],
    reference_assignment_builder: Callable[
        [SealedGraphStateSnapshot, LineageEvidenceReference],
        tuple[GroundedLineageReferenceAssignment, ...],
    ]
    | None = None,
    expect_accepted: bool = True,
):
    class Resolver:
        def resolve_accepted_identity_operation(
            self,
            *,
            operation,
            candidate,
            source_analysis,
            operation_fence,
            graph_snapshot,
        ):
            evidence = LineageEvidenceReference(
                source_id=source_analysis.source_id,
                start=source_analysis.assertion_span.start,
                end=source_analysis.assertion_span.end,
                evidence_digest=sha256(
                    (source_analysis.source_id + source_analysis.analysis_digest).encode()
                ).hexdigest(),
            )
            accepted = AcceptedIdentityOperation.create(
                operation_id=operation.operation_id,
                operation=operation_kind,
                predecessors=predecessors,
                successors=successors,
                source_evidence=(evidence,),
                reference_assignments=(
                    reference_assignment_builder(graph_snapshot, evidence)
                    if reference_assignment_builder is not None
                    else ()
                ),
            )
            return TrustedAcceptedIdentityOperationDecision.create(
                operation=accepted,
                alias_payload=None,
                sealed_operation_digest=operation.sealed_operation_digest,
                candidate_digest=candidate.candidate_digest,
                source_analysis_digest=source_analysis.analysis_digest,
                operation_fence_binding_digest=operation_fence.binding_digest,
                graph_snapshot_digest=graph_snapshot.snapshot_digest,
                graph_read_set_digest=graph_snapshot.read_set.read_set_digest,
                authority_digest="a" * 64,
            )

    class Verifier:
        def verify_identity_decision_authority(self, decision):
            return VerifiedIdentityDecisionAuthority.create(
                decision_digest=decision.decision_digest,
                sealed_operation_digest=decision.sealed_operation_digest,
                candidate_digest=decision.candidate_digest,
                source_analysis_digest=decision.source_analysis_digest,
                operation_fence_binding_digest=decision.operation_fence_binding_digest,
                graph_snapshot_digest=decision.graph_snapshot_digest,
                graph_read_set_digest=decision.graph_read_set_digest,
                authority_record_id="identity-authority:test",
                authority_record_digest="b" * 64,
                verifier_id="test-verifier",
            )

    coordinator = SemanticIngestionTransactionCoordinator(store, now_provider=lambda: NOW)
    terminal = accepted_terminal(
        operation_id=fence.operation_id,
        operation_kind="identity",
        identity_lineage_compiler=ProductionIdentityLineageCompiler(coordinator, store),
        identity_operation_planner=AtomicStoreAcceptedIdentityOperationPlanner(
            coordinator, store, writers, Resolver(), Verifier()
        ),
        operation_fence=fence,
    )
    if expect_accepted:
        assert terminal.status == "accepted", terminal.reason_codes
    return terminal


@pytest.mark.parametrize("operation_kind", ("alias", "rekey", "merge", "split"))
def test_normal_identity_planner_freezes_outputs_before_compilation(
    operation_kind: str,
) -> None:
    plane, writers, store, binding, fence, service, repository = _setup(verified=True)
    store.bootstrap_reference_integrity(writer_binding=binding)
    alice = LineageEntityIdentity(
        entity_revision_id="entity:alice:v1", logical_entity_id="entity:alice"
    )
    bob = LineageEntityIdentity(
        entity_revision_id="entity:bob:v1", logical_entity_id="entity:bob"
    )
    shapes = {
        "alias": ((), ()),
        "rekey": (
            (alice,),
            (LineageEntityIdentity(
                entity_revision_id="entity:alice:v2",
                logical_entity_id="entity:alice",
            ),),
        ),
        "merge": (
            tuple(sorted((alice, bob), key=lambda item: item.entity_revision_id)),
            (LineageEntityIdentity(
                entity_revision_id="entity:people:v1",
                logical_entity_id="entity:people",
            ),),
        ),
        "split": (
            (alice,),
            tuple(sorted((
                LineageEntityIdentity(
                    entity_revision_id="entity:alice-a:v1",
                    logical_entity_id="entity:alice-a",
                ),
                LineageEntityIdentity(
                    entity_revision_id="entity:alice-b:v1",
                    logical_entity_id="entity:alice-b",
                ),
            ), key=lambda item: item.entity_revision_id)),
        ),
    }
    predecessors, successors = shapes[operation_kind]

    class Resolver:
        def resolve_accepted_identity_operation(
            self,
            *,
            operation,
            candidate,
            source_analysis,
            operation_fence,
            graph_snapshot,
        ):
            evidence = LineageEvidenceReference(
                source_id=source_analysis.source_id,
                start=source_analysis.assertion_span.start,
                end=source_analysis.assertion_span.end,
                evidence_digest=sha256(
                    (
                        source_analysis.source_id
                        + source_analysis.analysis_digest
                    ).encode()
                ).hexdigest(),
            )
            accepted = AcceptedIdentityOperation.create(
                operation_id=operation.operation_id,
                operation=operation_kind,
                predecessors=predecessors,
                successors=successors,
                source_evidence=(evidence,),
                reference_assignments=(),
            )
            alias_payload = (
                SourceGroundedAliasPayload.create(
                    alias_namespace="people",
                    normalized_alias_key="alice",
                    entity_revision_id=alice.entity_revision_id,
                    logical_entity_id=alice.logical_entity_id,
                    source_evidence=(evidence,),
                )
                if operation_kind == "alias"
                else None
            )
            return TrustedAcceptedIdentityOperationDecision.create(
                operation=accepted,
                alias_payload=alias_payload,
                sealed_operation_digest=operation.sealed_operation_digest,
                candidate_digest=candidate.candidate_digest,
                source_analysis_digest=source_analysis.analysis_digest,
                operation_fence_binding_digest=operation_fence.binding_digest,
                graph_snapshot_digest=graph_snapshot.snapshot_digest,
                graph_read_set_digest=graph_snapshot.read_set.read_set_digest,
                authority_digest="a" * 64,
            )

    class Verifier:
        def verify_identity_decision_authority(self, decision):
            return VerifiedIdentityDecisionAuthority.create(
                decision_digest=decision.decision_digest,
                sealed_operation_digest=decision.sealed_operation_digest,
                candidate_digest=decision.candidate_digest,
                source_analysis_digest=decision.source_analysis_digest,
                operation_fence_binding_digest=decision.operation_fence_binding_digest,
                graph_snapshot_digest=decision.graph_snapshot_digest,
                graph_read_set_digest=decision.graph_read_set_digest,
                authority_record_id="identity-authority:test",
                authority_record_digest="b" * 64,
                verifier_id="test-verifier",
            )

    coordinator = SemanticIngestionTransactionCoordinator(store, now_provider=lambda: NOW)
    planner = AtomicStoreAcceptedIdentityOperationPlanner(
        coordinator, store, writers, Resolver(), Verifier()
    )
    compiler = ProductionIdentityLineageCompiler(coordinator, store)
    terminal = accepted_terminal(
        operation_id=fence.operation_id,
        operation_kind="identity",
        identity_lineage_compiler=compiler,
        identity_operation_planner=planner,
        operation_fence=fence,
    )

    assert terminal.status == "accepted", terminal.reason_codes
    sealed = terminal.sealed_operations[0]
    candidate = terminal.candidates[0]
    analysis = terminal.source_analyses[0]
    planned = store.get_identity_graph_planning_artifact(
        operation_id=sealed.operation_id,
        sealed_operation_digest=sealed.sealed_operation_digest,
        candidate_digest=candidate.candidate_digest,
        source_analysis_digest=analysis.analysis_digest,
    )
    assert planned is not None
    assert planned.compiled_transition == terminal.accepted_carriers[0].transition
    identity_plan = next(
        item.after_planning_record.payload.planning_record
        for item in planned.planning_delta.mutations
        if item.record_kind == "identity_lineage"
    )
    assert "record_digest" not in identity_plan
    assert identity_plan["transition"]["recorded_at"] == {
        "kind": "transaction_commit_coordinate",
        "transaction_group_id": fence.operation_id,
        "coordinate": "committed_at",
    }
    before_direct_publish = tuple(plane.list_records())
    assert (
        store.publish_accepted_identity_operation(
            planned, writer_binding=binding
        )
        == planned
    )
    with pytest.raises(TypeError, match="unexpected keyword"):
        store.publish_accepted_identity_operation(
            planned,
            writer_binding=binding,
            authority_verifier=Verifier(),  # type: ignore[call-arg]
        )
    assert tuple(plane.list_records()) == before_direct_publish
    _activate(repository, fence, terminal)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    materialized = {
        (item.record_kind, item.record_id): item.record
        for item in store.semantic_replay_state().materialized_records
        if item.transaction_group_id == fence.operation_id
    }
    event_batch = store.semantic_event_batches()[0]
    expected_records, _ = materialize_frozen_identity_graph_plan(
        planned,
        commit_values=PlanningCommitValues(
            transaction_group_id=fence.operation_id,
            graph_revision_before=(
                event_batch.events[0].payload.graph_revision_before
            ),
            graph_revision_after=(
                event_batch.events[-1].payload.graph_revision_after
            ),
            committed_at=event_batch.events[0].timestamp,
        ),
    )
    assert {
        (item.payload_record_kind, item.record_id): item.payload
        for item in expected_records
    } == materialized
    lineage = next(
        item
        for item in materialized.values()
        if item.record_kind == "identity_lineage"
    )
    assert lineage.transition.recorded_at == event_batch.events[0].timestamp


def test_identity_plan_lost_ack_reopens_jsonl_without_duplicate_effects(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = tmp_path / "identity-plan-lost-ack"
    planning_time = NOW
    commit_time = NOW + timedelta(hours=2)
    current_time = [planning_time]
    plane, writers, store, binding, fence, _, _ = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: current_time[0],
    )
    store.bootstrap_reference_integrity(writer_binding=binding)
    predecessor = LineageEntityIdentity(
        entity_revision_id="entity:alice:v1",
        logical_entity_id="entity:alice",
    )
    successor = LineageEntityIdentity(
        entity_revision_id="entity:alice:v2",
        logical_entity_id="entity:alice",
    )
    original_write = plane.conditionally_write_records
    lost_ack = False

    def publish_then_lose_ack(records, **kwargs):
        nonlocal lost_ack
        result = original_write(records, **kwargs)
        if (
            not lost_ack
            and records
            and records[0].source_kind
            == "semantic_ingestion_accepted_identity_operation"
        ):
            lost_ack = True
            raise OSError("simulated identity plan lost acknowledgement")
        return result

    monkeypatch.setattr(
        plane, "conditionally_write_records", publish_then_lose_ack
    )
    with pytest.raises(OSError, match="identity plan lost acknowledgement"):
        _trusted_identity_terminal(
            store=store,
            writers=writers,
            fence=fence,
            operation_kind="rekey",
            predecessors=(predecessor,),
            successors=(successor,),
            expect_accepted=False,
        )
    assert lost_ack

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: current_time[0],
    )
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: current_time[0],
        identity_decision_authority_verifier=IDENTITY_AUTHORITY_VERIFIER,
    )
    persisted_plan = decode_typed_value(
        bytes.fromhex(
            str(
                reopened_plane.list_records(
                    source_kind="semantic_ingestion_accepted_identity_operation"
                )[0].content["canonical_hex"]
            )
        )
    )
    persisted_accepted = persisted_plan["accepted_operation_artifact"]
    persisted_operation = persisted_accepted["operation"]
    assert reopened_store.get_identity_graph_planning_artifact(
        operation_id=persisted_operation["operation_id"],
        sealed_operation_digest=persisted_accepted["sealed_operation_digest"],
        candidate_digest=persisted_accepted["candidate_digest"],
        source_analysis_digest=persisted_accepted["source_analysis_digest"],
    ) is not None
    terminal = _trusted_identity_terminal(
        store=reopened_store,
        writers=reopened_writers,
        fence=fence,
        operation_kind="rekey",
        predecessors=(predecessor,),
        successors=(successor,),
    )
    sealed = terminal.sealed_operations[0]
    candidate = terminal.candidates[0]
    analysis = terminal.source_analyses[0]
    planned = reopened_store.get_identity_graph_planning_artifact(
        operation_id=sealed.operation_id,
        sealed_operation_digest=sealed.sealed_operation_digest,
        candidate_digest=candidate.candidate_digest,
        source_analysis_digest=analysis.analysis_digest,
    )
    assert planned is not None
    assert planned.compiled_transition == terminal.accepted_carriers[0].transition
    assert planned.compiled_transition.recorded_at is None
    assert len(
        reopened_plane.list_records(
            source_kind="semantic_ingestion_accepted_identity_operation"
        )
    ) == 1

    repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=reopened_store,
        writer_binding_provider=lambda: reopened_binding,
        now_provider=lambda: current_time[0],
    )
    service = SemanticTerminalPersistenceService(
        atomic_store=reopened_store,
        writer_binding_provider=lambda: reopened_binding,
        authorization_repository=repository,
    )
    _activate(repository, fence, terminal)
    current_time[0] = commit_time
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    assert reopened_store.get_operation(fence).state == "terminal"
    event_batch = reopened_store.semantic_event_batches()[0]
    assert event_batch.events[0].timestamp == commit_time
    graph_revision_before = event_batch.events[0].payload.graph_revision_before
    graph_revision_after = event_batch.events[-1].payload.graph_revision_after
    assert graph_revision_after != graph_revision_before
    committed_records, committed_state = materialize_frozen_identity_graph_plan(
        planned,
        commit_values=PlanningCommitValues(
            transaction_group_id=fence.operation_id,
            graph_revision_before=graph_revision_before,
            graph_revision_after=graph_revision_after,
            committed_at=commit_time,
        ),
    )
    oracle_state = materialize_serialized(
        planned.planning_state_after.model_dump(mode="python"),
        authorizing_group=fence.operation_id,
        commit_values={
            "transaction_group_id": fence.operation_id,
            "graph_revision_before": graph_revision_before,
            "graph_revision_after": graph_revision_after,
            "committed_at": commit_time,
        },
        durable_records=tuple(
            item.model_dump(mode="python") for item in committed_records
        ),
    )
    assert oracle_state == committed_state.model_dump(mode="python")
    expected_ledger = (
        graph_planning_module.materialize_frozen_identity_reference_mutations(
            planned,
            commit_values=PlanningCommitValues(
                transaction_group_id=fence.operation_id,
                graph_revision_before=graph_revision_before,
                graph_revision_after=graph_revision_after,
                committed_at=commit_time,
            ),
            durable_records=committed_records,
        )
    )
    durable_ledger = reopened_store.reference_integrity_snapshot().entries
    assert tuple(sorted(
        (
            item.graph_revision,
            item.operation_id,
            item.change,
            item.record_kind,
            item.record_id,
            item.reference_path,
            item.target.kind,
            item.target.target_id,
            item.base_record_digest,
        )
        for item in durable_ledger
    )) == tuple(sorted(
        (
            item.graph_revision,
            item.operation_id,
            item.change,
            item.record_kind,
            item.record_id,
            item.reference_path,
            item.target.kind,
            item.target.target_id,
            item.base_record_digest,
        )
        for item in expected_ledger
    ))
    lineage_event = next(
        event
        for event in event_batch.events
        if event.payload.record_kind == "identity_lineage"
    )
    assert lineage_event.payload.entity.record.transition.recorded_at == commit_time
    assert b"transaction_commit_coordinate" not in encode_semantic_memory_event_batch(
        event_batch
    )


@pytest.mark.parametrize(
    "mutation",
    ("omit", "path", "target", "revision", "base_digest"),
)
def test_planned_reference_ledger_substitution_rejects_before_any_effect(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    plane, writers, store, binding, fence, service, repository = _setup(
        verified=True
    )
    store.bootstrap_reference_integrity(writer_binding=binding)
    terminal = _trusted_identity_terminal(
        store=store,
        writers=writers,
        fence=fence,
        operation_kind="rekey",
        predecessors=(
            LineageEntityIdentity(
                entity_revision_id="ledger:alice:v1",
                logical_entity_id="ledger:alice",
            ),
        ),
        successors=(
            LineageEntityIdentity(
                entity_revision_id="ledger:alice:v2",
                logical_entity_id="ledger:alice",
            ),
        ),
    )
    _activate(repository, fence, terminal)
    replay_before = store.semantic_replay_state()
    ledger_before = store.reference_integrity_snapshot()
    original = (
        graph_planning_module.materialize_frozen_identity_reference_mutations
    )

    def substitute(*args, **kwargs):
        values = list(original(*args, **kwargs))
        assert values
        if mutation == "omit":
            return tuple(values[1:])
        first = values[0]
        if mutation == "path":
            values[0] = first.model_copy(
                update={"reference_path": first.reference_path + ".substituted"}
            )
        elif mutation == "target":
            values[0] = first.model_copy(
                update={
                    "target": ReferenceTarget(
                        kind=first.target.kind,
                        target_id=first.target.target_id + ":substituted",
                    )
                }
            )
        elif mutation == "revision":
            values[0] = first.model_copy(
                update={"graph_revision": "substituted-revision"}
            )
        else:
            values[0] = first.model_copy(
                update={"base_record_digest": "f" * 64}
            )
        return tuple(values)

    monkeypatch.setattr(
        graph_planning_module,
        "materialize_frozen_identity_reference_mutations",
        substitute,
    )
    with pytest.raises(
        PreplanningStoreError,
        match="terminal-group retry budget exhausted",
    ):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )
    assert store.semantic_event_batches() == ()
    assert store.semantic_replay_state() == replay_before
    assert store.reference_integrity_snapshot() == ledger_before


def test_identity_plan_jsonl_barrier_rechecks_freeze_before_publication(
    tmp_path,
) -> None:
    storage = tmp_path / "identity-plan-freeze-barrier"
    _, writers, store, binding, fence, _, _ = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    store.bootstrap_reference_integrity(writer_binding=binding)
    guard_calls = 0

    def freeze_at_transaction_barrier(_graph_delta) -> None:
        nonlocal guard_calls
        guard_calls += 1
        if guard_calls == 2:
            raise SemanticEventReplayError("semantic_repository_scope_frozen")

    store._semantic_freeze_guard = freeze_at_transaction_barrier
    store._uses_default_semantic_freeze_guard = False
    terminal = _trusted_identity_terminal(
        store=store,
        writers=writers,
        fence=fence,
        operation_kind="rekey",
        predecessors=(
            LineageEntityIdentity(
                entity_revision_id="entity:alice:v1",
                logical_entity_id="entity:alice",
            ),
        ),
        successors=(
            LineageEntityIdentity(
                entity_revision_id="entity:alice:v2",
                logical_entity_id="entity:alice",
            ),
        ),
        expect_accepted=False,
    )

    assert terminal.status == "unresolved"
    assert guard_calls == 2
    observer = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    assert not observer.list_records(
        source_kind="semantic_ingestion_accepted_identity_operation"
    )


def test_hermes_real_store_audit_views_do_not_leak_disjoint_scope_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane, _, store, binding, _, service, repository = _setup(verified=True)
    store.bootstrap_reference_integrity(writer_binding=binding)
    for coordinate, scope_id, subject in (
        ("audit-alice", "user:alice", "entity:alice"),
        ("audit-bob", "user:bob", "entity:bob"),
    ):
        admission, fence = handoff(
            plane,
            coordinate=coordinate,
            scope_ids=frozenset({scope_id}),
            atomic_store=store,
            writer_binding=binding,
        )
        terminal = accepted_terminal(
            operation_id=fence.operation_id,
            source_id=admission.source_id,
            source_digest=admission.source_digest,
            subject_logical_entity_id=subject,
            subject_entity_revision_id=f"{subject}:v1",
        )
        _activate(repository, fence, terminal)
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )

    principals = {
        name: DeliveryPrincipalBinding.create(
            principal_subject_id=f"principal:{name}",
            tenant_partition_id="tenant:a",
            provider_identity="hermes",
        )
        for name in ("alice", "bob")
    }
    contexts = {
        name: AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            required_outcome_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id="tenant:a", scopes={f"user:{name}"}
            ),
            current_authorized_scopes=RequiredOutcomeScopeSet.create(
                tenant_partition_id="tenant:a",
                scopes=(
                    {"user:alice", "user:bob"}
                    if name == "alice"
                    else {"user:bob"}
                ),
            ),
        )
        for name, principal in principals.items()
    }
    grants = {
        principal.binding_digest: IdentityLineageAuditGrant(
            tenant_partition_id="tenant:a",
            principal_binding_digest=principal.binding_digest,
            authorized_scope_ids=(
                ("user:alice", "user:bob")
                if name == "alice"
                else ("user:bob",)
            ),
            issued_at=NOW,
            expires_at=NOW + timedelta(days=30),
        )
        for name, principal in principals.items()
    }

    class Resolver:
        shrink_alice_on_final = False
        alice_reads = 0

        def resolve(self, host_ingress, server_time):
            del server_time
            if self.shrink_alice_on_final and host_ingress.principal_handle == "alice":
                self.alice_reads += 1
                if self.alice_reads == 2:
                    self.shrink_alice_on_final = False
                    self.alice_reads = 0
                    return contexts["alice"].model_copy(
                        update={
                            "current_authorized_scopes": RequiredOutcomeScopeSet.create(
                                tenant_partition_id="tenant:a", scopes={"user:bob"}
                            )
                        }
                    )
            return contexts[host_ingress.principal_handle]

    audit_authorizer = GrantBackedIdentityLineageAuditAuthorizer(grants.get)
    disclosure_reads = 0
    original_scope_event_ids = store.lineage_audit_scope_event_ids

    def count_scope_event_ids(**kwargs):
        nonlocal disclosure_reads
        disclosure_reads += 1
        return original_scope_event_ids(**kwargs)

    monkeypatch.setattr(store, "lineage_audit_scope_event_ids", count_scope_event_ids)
    resolver = Resolver()
    provider = HermesMemoryProvider(
        service=ProviderMemoryService(
            identity_lineage_audit_reader=AtomicStoreScopedIdentityLineageAuditReader(
                store,
                tenant_partition_id="tenant:a",
                scope_revalidator=lambda scope, server_time: (
                    audit_authorizer.revalidate_identity_lineage_audit_scope(
                        scope, server_time=server_time
                    )
                ),
                now_provider=lambda: NOW,
            ),
            identity_lineage_audit_authorizer=audit_authorizer,
            authenticated_ingress_resolver=resolver,
            now_provider=lambda: NOW,
        )
    )

    views = {}
    for name in ("alice", "bob"):
        views[name] = provider.read_identity_lineage(
            GraphAuditRequest(
                query=f"{name} lineage",
                purpose=RetrievalPurpose.GRAPH_AUDIT,
                scope=MemoryScope(user_id=f"user:{name}"),
                scope_mode="scoped",
            ),
            authenticated_host_ingress=AuthenticatedHostIngress(
                provider_identity="hermes",
                principal_handle=name,
                session_handle=f"session:{name}",
                received_at=NOW,
            ),
        )

    assert views["alice"].view_digest != views["bob"].view_digest
    assert {item.claim_assertion_id for item in views["alice"].resolved_claims}.isdisjoint(
        item.claim_assertion_id for item in views["bob"].resolved_claims
    )
    assert disclosure_reads == 2

    alice_digest = principals["alice"].binding_digest
    grants[alice_digest] = grants[alice_digest].model_copy(update={"revoked": True})
    with pytest.raises(ValueError, match="identity_lineage_audit_denied"):
        provider.read_identity_lineage(
            GraphAuditRequest(
                query="revoked",
                purpose=RetrievalPurpose.GRAPH_AUDIT,
                scope=MemoryScope(user_id="user:alice"),
                scope_mode="scoped",
            ),
            authenticated_host_ingress=AuthenticatedHostIngress(
                provider_identity="hermes",
                principal_handle="alice",
                session_handle="session:revoked",
                received_at=NOW,
            ),
        )
    assert disclosure_reads == 2

    grants[alice_digest] = grants[alice_digest].model_copy(
        update={"revoked": False, "allow_full_scope": True}
    )
    full = provider.read_identity_lineage(
        GraphAuditRequest(
            query="full",
            purpose=RetrievalPurpose.GRAPH_AUDIT,
            scope_mode="full",
        ),
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="hermes",
            principal_handle="alice",
            session_handle="session:full",
            received_at=NOW,
        ),
    )
    assert disclosure_reads == 3
    assert {
        item.claim_assertion_id for item in full.resolved_claims
    } == {
        item.claim_assertion_id
        for name in ("alice", "bob")
        for item in views[name].resolved_claims
    }

    grants[alice_digest] = grants[alice_digest].model_copy(
        update={"allow_full_scope": False}
    )
    with pytest.raises(ValueError, match="identity_lineage_audit_denied"):
        provider.read_identity_lineage(
            GraphAuditRequest(
                query="full denied",
                purpose=RetrievalPurpose.GRAPH_AUDIT,
                scope_mode="full",
            ),
            authenticated_host_ingress=AuthenticatedHostIngress(
                provider_identity="hermes",
                principal_handle="alice",
                session_handle="session:full-denied",
                received_at=NOW,
            ),
        )
    assert disclosure_reads == 3

    resolver.shrink_alice_on_final = True
    with pytest.raises(ValueError, match="identity_lineage_audit_denied"):
        provider.read_identity_lineage(
            GraphAuditRequest(
                query="scope removed",
                purpose=RetrievalPurpose.GRAPH_AUDIT,
                scope=MemoryScope(user_id="user:alice"),
                scope_mode="scoped",
            ),
            authenticated_host_ingress=AuthenticatedHostIngress(
                provider_identity="hermes",
                principal_handle="alice",
                session_handle="session:scope-removed",
                received_at=NOW,
            ),
        )
    assert disclosure_reads == 3


@pytest.mark.parametrize("operation_kind", ("alias", "rekey", "merge", "split"))
def test_accepted_only_identity_artifacts_require_explicit_migration_without_effects(
    operation_kind: str,
) -> None:
    plane, _, store, binding, fence, _, _ = _setup(verified=True)
    store.bootstrap_reference_integrity(writer_binding=binding)
    alice = LineageEntityIdentity(entity_revision_id="alice:v1", logical_entity_id="alice")
    bob = LineageEntityIdentity(entity_revision_id="bob:v1", logical_entity_id="bob")
    shapes = {
        "alias": ((), ()),
        "rekey": ((alice,), (LineageEntityIdentity(entity_revision_id="alice:v2", logical_entity_id="alice"),)),
        "merge": (tuple(sorted((alice, bob), key=lambda item: item.entity_revision_id)), (LineageEntityIdentity(entity_revision_id="people:v1", logical_entity_id="people"),)),
        "split": ((alice,), tuple(sorted((
            LineageEntityIdentity(entity_revision_id="alice-a:v1", logical_entity_id="alice-a"),
            LineageEntityIdentity(entity_revision_id="alice-b:v1", logical_entity_id="alice-b"),
        ), key=lambda item: item.entity_revision_id))),
    }
    predecessors, successors = shapes[operation_kind]

    def accepted_provider(operation_id: str):
        return AcceptedIdentityOperation.create(
            operation_id=operation_id,
            operation=operation_kind,
            predecessors=predecessors,
            successors=successors,
            source_evidence=(LineageEvidenceReference(
                source_id=fence.source_id,
                start=0,
                end=5,
                evidence_digest=sha256(operation_kind.encode()).hexdigest(),
            ),),
            reference_assignments=(),
        )

    artifact_repository = _AcceptedIdentityArtifactRepository(
        accepted_provider,
        fence=fence,
        graph_revision=store.semantic_replay_state().graph_revision,
    )
    compiler = ProductionIdentityLineageCompiler(
        SemanticIngestionTransactionCoordinator(store, now_provider=lambda: NOW),
        artifact_repository,
    )
    terminal = accepted_terminal(
        operation_id=fence.operation_id,
        operation_kind="identity",
        identity_lineage_compiler=compiler,
    )
    assert terminal.status == "accepted"
    assert artifact_repository.artifact is not None
    before_records = tuple(plane.list_records())
    before_state = store.semantic_replay_state()
    before_ledger = store.reference_integrity_snapshot()

    with pytest.raises(
        IdentityPlanningMigrationRequiredError,
        match="requires explicit migration",
    ):
        store.publish_accepted_identity_operation(
            artifact_repository.artifact, writer_binding=binding
        )

    assert tuple(plane.list_records()) == before_records
    assert store.semantic_replay_state() == before_state
    assert store.reference_integrity_snapshot() == before_ledger


def test_two_identity_writers_on_one_predecessor_leave_no_partial_second_commit() -> None:
    plane, writers, store, binding, first_fence, service, repository = _setup(
        verified=True
    )
    store.bootstrap_reference_integrity(writer_binding=binding)
    _, second_fence = handoff(
        plane,
        coordinate="two",
        atomic_store=store,
        writer_binding=binding,
    )
    predecessor = LineageEntityIdentity(
        entity_revision_id="alice:v1", logical_entity_id="alice"
    )

    def terminal_for(fence, successor_revision: str):
        return _trusted_identity_terminal(
            store=store,
            writers=writers,
            fence=fence,
            operation_kind="rekey",
            predecessors=(predecessor,),
            successors=(
                LineageEntityIdentity(
                    entity_revision_id=successor_revision,
                    logical_entity_id="alice",
                ),
            ),
        )

    # Both writers seal against the same predecessor and genesis snapshot.
    first = terminal_for(first_fence, "alice:v2")
    second = terminal_for(second_fence, "alice:v3")
    _activate(repository, first_fence, first)
    _activate(repository, second_fence, second)
    service.persist(fence=first_fence, terminal=first, authorization_verifier=AUTHORIZATION)
    state_after_first = store.semantic_replay_state()
    ledger_after_first = store.reference_integrity_snapshot()

    with pytest.raises(ValueError):
        service.persist(
            fence=second_fence,
            terminal=second,
            authorization_verifier=AUTHORIZATION,
        )

    assert store.semantic_replay_state() == state_after_first
    assert store.reference_integrity_snapshot() == ledger_after_first
    assert len(replay_identity_lineage(state_after_first).transitions) == 1


def test_two_jsonl_identity_planners_racing_same_successor_leave_one_winner(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = tmp_path / "same-successor-planning-race"
    plane_a, writers_a, store_a, binding_a, fence_a, service_a, repository_a = (
        _setup(verified=True, backend=JsonlMemoryPlaneStore(storage))
    )
    store_a.bootstrap_reference_integrity(writer_binding=binding_a)
    plane_b = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    writers_b = SemanticWriterAdmissionStore(
        plane_b,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    binding_b = writers_b.commit_binding(writers_b.current())
    store_b = SemanticIngestionAtomicStore(
        plane_b,
        writers_b,
        now_provider=lambda: NOW,
        identity_decision_authority_verifier=IDENTITY_AUTHORITY_VERIFIER,
    )
    repository_b = SemanticAuthorizationAuthorityRepository(
        atomic_store=store_b,
        writer_binding_provider=lambda: binding_b,
        now_provider=lambda: NOW,
    )
    service_b = SemanticTerminalPersistenceService(
        atomic_store=store_b,
        writer_binding_provider=lambda: binding_b,
        authorization_repository=repository_b,
    )
    _, fence_b = handoff(
        plane_b,
        coordinate="same-successor-b",
        atomic_store=store_b,
        writer_binding=binding_b,
    )
    barrier = Barrier(2)

    def install_barrier(plane):
        original = plane.conditionally_write_records
        entered = False

        def write(records, **kwargs):
            nonlocal entered
            if any(
                item.source_kind
                == "semantic_ingestion_accepted_identity_operation"
                for item in records
            ) and not entered:
                entered = True
                barrier.wait(timeout=10)
            return original(records, **kwargs)

        monkeypatch.setattr(plane, "conditionally_write_records", write)

    install_barrier(plane_a)
    install_barrier(plane_b)
    predecessor = LineageEntityIdentity(
        entity_revision_id="race:alice:v1", logical_entity_id="race:alice"
    )
    successor = LineageEntityIdentity(
        entity_revision_id="race:alice:v2", logical_entity_id="race:alice"
    )

    def plan(store, writers, fence):
        return _trusted_identity_terminal(
            store=store,
            writers=writers,
            fence=fence,
            operation_kind="rekey",
            predecessors=(predecessor,),
            successors=(successor,),
            expect_accepted=False,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(plan, store_a, writers_a, fence_a),
            executor.submit(plan, store_b, writers_b, fence_b),
        )
        outcomes = []
        for index, future in enumerate(futures):
            try:
                outcomes.append((index, future.result()))
            except Exception as exc:
                outcomes.append((index, exc))

    winners = tuple(
        item
        for item in outcomes
        if isinstance(item[1], SemanticTerminalOutcome)
        and item[1].status == "accepted"
    )
    assert len(winners) == 1, (
        outcomes,
        plane_a.list_records(
            source_kind="semantic_ingestion_accepted_identity_operation"
        ),
    )
    winner_index, winner = winners[0]
    assert isinstance(winner, SemanticTerminalOutcome)
    winner_fence, winner_service, winner_repository = (
        (fence_a, service_a, repository_a)
        if winner_index == 0
        else (fence_b, service_b, repository_b)
    )
    _activate(winner_repository, winner_fence, winner)
    winner_service.persist(
        fence=winner_fence,
        terminal=winner,
        authorization_verifier=AUTHORIZATION,
    )

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
        identity_decision_authority_verifier=IDENTITY_AUTHORITY_VERIFIER,
    )
    assert len(
        reopened_plane.list_records(
            source_kind="semantic_ingestion_accepted_identity_operation"
        )
    ) == 1
    assert len(
        reopened_plane.list_records(
            source_kind="semantic_ingestion_graph_identity_reservation"
        )
    ) == 1
    assert len(reopened_store.semantic_event_batches()) == 1
    assert len(replay_identity_lineage(reopened_store.semantic_replay_state()).transitions) == 1


def test_recomputed_persisted_identity_plan_authority_tamper_rejects_on_reopen(
    tmp_path,
) -> None:
    storage = tmp_path / "identity-plan-authority-tamper"
    backend = JsonlMemoryPlaneStore(storage)
    plane, writers, store, binding, fence, _, _ = _setup(
        verified=True,
        backend=backend,
    )
    store.bootstrap_reference_integrity(writer_binding=binding)
    terminal = _trusted_identity_terminal(
        store=store,
        writers=writers,
        fence=fence,
        operation_kind="rekey",
        predecessors=(
            LineageEntityIdentity(
                entity_revision_id="tamper:alice:v1",
                logical_entity_id="tamper:alice",
            ),
        ),
        successors=(
            LineageEntityIdentity(
                entity_revision_id="tamper:alice:v2",
                logical_entity_id="tamper:alice",
            ),
        ),
    )
    sealed = terminal.sealed_operations[0]
    candidate = terminal.candidates[0]
    analysis = terminal.source_analyses[0]
    planned = store.get_identity_graph_planning_artifact(
        operation_id=sealed.operation_id,
        sealed_operation_digest=sealed.sealed_operation_digest,
        candidate_digest=candidate.candidate_digest,
        source_analysis_digest=analysis.analysis_digest,
    )
    assert planned is not None

    verification_values = planned.authority_verification.model_dump(
        mode="python", exclude={"verification_digest"}
    )
    verification_values["verifier_id"] = "forged-verifier"
    forged_verification = VerifiedIdentityDecisionAuthority.create(
        **verification_values
    )
    accepted_values = planned.accepted_operation_artifact.model_dump(
        mode="python", exclude={"artifact_digest"}
    )
    accepted_values.update(
        authority_digest=forged_verification.verification_digest,
        authority_verification_digest=forged_verification.verification_digest,
    )
    forged_accepted = AcceptedIdentityOperationArtifact.create(**accepted_values)
    frozen_values = planned.model_dump(mode="python", exclude={"artifact_digest"})
    frozen_values.update(
        accepted_operation_artifact=forged_accepted,
        authority_verification=forged_verification,
    )
    forged_plan = type(planned).create(**frozen_values)
    plan_record = plane.list_records(
        source_kind="semantic_ingestion_accepted_identity_operation"
    )[0]
    forged_record = plan_record.model_copy(
        update={
            "content": {
                **plan_record.content,
                "canonical_hex": encode_typed_value(
                    forged_plan.model_dump(mode="python")
                ).hex(),
                "artifact_digest": forged_plan.artifact_digest,
            }
        }
    )
    _rewrite_jsonl_snapshot(backend, plane, replacements=(forged_record,))

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
        identity_decision_authority_verifier=IDENTITY_AUTHORITY_VERIFIER,
    )
    exposed = None
    with pytest.raises(PreplanningStoreError, match="authority binding mismatch"):
        exposed = reopened_store.get_identity_graph_planning_artifact(
            operation_id=sealed.operation_id,
            sealed_operation_digest=sealed.sealed_operation_digest,
            candidate_digest=candidate.candidate_digest,
            source_analysis_digest=analysis.analysis_digest,
        )
    assert exposed is None
    assert reopened_store.semantic_event_batches() == ()
    assert replay_identity_lineage(
        reopened_store.semantic_replay_state()
    ).transitions == ()


@pytest.mark.parametrize("operation_kind", ("correction", "retraction"))
def test_temporal_transition_system_time_materializes_only_at_commit_and_reopens_exactly(
    tmp_path,
    operation_kind: str,
) -> None:
    planning_time = NOW
    commit_time = NOW + timedelta(hours=3)
    current_time = [planning_time]
    storage = tmp_path / f"commit-time-{operation_kind}"
    plane, _, store, _, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: current_time[0],
    )
    terminal = accepted_terminal(
        operation_id=fence.operation_id,
        operation_kind=operation_kind,
        operation_fence=fence,
    )
    planned_transition = next(
        item
        for item in terminal.accepted_carriers
        if isinstance(item, TemporalTransitionRecord)
    )
    assert planned_transition.system_interval is None
    _activate(repository, fence, terminal)
    current_time[0] = commit_time
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    committed_batch = store.semantic_event_batches()[0]
    committed_transition = next(
        event.payload.entity.record
        for event in committed_batch.events
        if isinstance(event.payload.entity.record, TemporalTransitionRecord)
    )
    assert committed_transition.system_interval is not None
    assert committed_transition.system_interval.start == commit_time
    assert committed_batch.events[0].timestamp == commit_time
    committed_bytes = encode_semantic_memory_event_batch(committed_batch)

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopen_clock_reads = [0]

    def reopen_now() -> datetime:
        reopen_clock_reads[0] += 1
        return commit_time + timedelta(days=1)

    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=reopen_now,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=reopen_now,
    )
    reopened_service = SemanticTerminalPersistenceService(
        atomic_store=reopened_store,
        writer_binding_provider=lambda: reopened_writers.commit_binding(
            reopened_writers.current()
        ),
    )
    reads_before_retry = reopen_clock_reads[0]
    reopened_service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    assert reopen_clock_reads[0] == reads_before_retry
    assert encode_semantic_memory_event_batch(
        reopened_store.semantic_event_batches()[0]
    ) == committed_bytes


def test_identity_plan_recompiles_when_graph_commits_at_publication_barrier(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = tmp_path / "identity-plan-publication-cas"
    plane, writers, store, binding, identity_fence, _, _ = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    store.bootstrap_reference_integrity(writer_binding=binding)

    graph_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    graph_writers = SemanticWriterAdmissionStore(
        graph_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    graph_binding = graph_writers.commit_binding(graph_writers.current())
    graph_store = SemanticIngestionAtomicStore(
        graph_plane,
        graph_writers,
        now_provider=lambda: NOW,
    )
    graph_repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=graph_store,
        writer_binding_provider=lambda: graph_binding,
        now_provider=lambda: NOW,
    )
    graph_service = SemanticTerminalPersistenceService(
        atomic_store=graph_store,
        writer_binding_provider=lambda: graph_binding,
        authorization_repository=graph_repository,
    )
    _, graph_fence = handoff(
        graph_plane,
        coordinate="publication-barrier",
        atomic_store=graph_store,
        writer_binding=graph_binding,
    )
    graph_terminal = accepted_terminal(
        operation_id=graph_fence.operation_id,
        operation_fence=graph_fence,
    )
    _activate(graph_repository, graph_fence, graph_terminal)
    original_write = plane.conditionally_write_records
    graph_committed = False

    def commit_graph_before_plan(
        records,
        *,
        preconditions,
        authorization=None,
        transaction_precondition=None,
    ):
        nonlocal graph_committed
        if not graph_committed and any(
            record.source_kind == "semantic_ingestion_accepted_identity_operation"
            for record in records
        ):
            graph_committed = True
            graph_service.persist(
                fence=graph_fence,
                terminal=graph_terminal,
                authorization_verifier=AUTHORIZATION,
            )
        return original_write(
            records,
            preconditions=preconditions,
            authorization=authorization,
            transaction_precondition=transaction_precondition,
        )

    monkeypatch.setattr(
        plane, "conditionally_write_records", commit_graph_before_plan
    )
    terminal = _trusted_identity_terminal(
        store=store,
        writers=writers,
        fence=identity_fence,
        operation_kind="rekey",
        predecessors=(
            LineageEntityIdentity(
                entity_revision_id="barrier:alice:v1",
                logical_entity_id="barrier:alice",
            ),
        ),
        successors=(
            LineageEntityIdentity(
                entity_revision_id="barrier:alice:v2",
                logical_entity_id="barrier:alice",
            ),
        ),
    )

    assert graph_committed is True
    assert terminal.status == "accepted"
    sealed = terminal.sealed_operations[0]
    candidate = terminal.candidates[0]
    analysis = terminal.source_analyses[0]
    planned = store.get_identity_graph_planning_artifact(
        operation_id=sealed.operation_id,
        sealed_operation_digest=sealed.sealed_operation_digest,
        candidate_digest=candidate.candidate_digest,
        source_analysis_digest=analysis.analysis_digest,
    )
    assert planned is not None
    assert planned.graph_replay_state_digest == store.semantic_replay_state().state_digest
    observer = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    assert sum(
        record.source_kind == "semantic_ingestion_accepted_identity_operation"
        for record in observer.list_records()
    ) == 1


def test_sequential_rekeys_reuse_logical_identity_without_reservation_collision() -> None:
    plane, writers, store, binding, first_fence, service, repository = _setup(
        verified=True
    )
    store.bootstrap_reference_integrity(writer_binding=binding)
    first_predecessor = LineageEntityIdentity(
        entity_revision_id="alice:v1", logical_entity_id="alice"
    )
    first_successor = LineageEntityIdentity(
        entity_revision_id="alice:v2", logical_entity_id="alice"
    )
    first = _trusted_identity_terminal(
        store=store,
        writers=writers,
        fence=first_fence,
        operation_kind="rekey",
        predecessors=(first_predecessor,),
        successors=(first_successor,),
    )
    _activate(repository, first_fence, first)
    service.persist(
        fence=first_fence,
        terminal=first,
        authorization_verifier=AUTHORIZATION,
    )
    _, second_fence = handoff(
        plane,
        coordinate="sequential-rekey-two",
        atomic_store=store,
        writer_binding=binding,
    )
    second_successor = LineageEntityIdentity(
        entity_revision_id="alice:v3", logical_entity_id="alice"
    )
    second = _trusted_identity_terminal(
        store=store,
        writers=writers,
        fence=second_fence,
        operation_kind="rekey",
        predecessors=(first_successor,),
        successors=(second_successor,),
    )
    _activate(repository, second_fence, second)
    service.persist(
        fence=second_fence,
        terminal=second,
        authorization_verifier=AUTHORIZATION,
    )

    lineage = replay_identity_lineage(store.semantic_replay_state())
    assert tuple(
        (
            item.predecessors[0].entity_revision_id,
            item.predecessors[0].logical_entity_id,
            item.successors[0].entity_revision_id,
            item.successors[0].logical_entity_id,
        )
        for item, _ in lineage.transitions
    ) == (
        ("alice:v1", "alice", "alice:v2", "alice"),
        ("alice:v2", "alice", "alice:v3", "alice"),
    )
    reservations = tuple(
        item.content["record_key"]
        for item in plane.list_records()
        if item.source_kind == "semantic_ingestion_graph_identity_reservation"
    )
    assert "entity_revision:alice:v2" in reservations
    assert "entity_revision:alice:v3" in reservations
    assert "logical_entity:alice" not in reservations


@pytest.mark.parametrize("operation_kind", ("merge", "split"))
def test_populated_merge_and_split_reopen_with_historical_lineage_and_current_projection(
    tmp_path,
    operation_kind: str,
) -> None:
    storage = tmp_path / f"populated-{operation_kind}-reopen"
    plane, writers, store, binding, first_fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    store.bootstrap_reference_integrity(writer_binding=binding)
    initial = LineageEntityIdentity(
        entity_revision_id="entity-revision:atlas:v1",
        logical_entity_id="entity:atlas",
    )
    predecessor = LineageEntityIdentity(
        entity_revision_id="entity-revision:atlas:v2",
        logical_entity_id="entity:atlas",
    )
    first = _trusted_identity_terminal(
        store=store,
        writers=writers,
        fence=first_fence,
        operation_kind="rekey",
        predecessors=(initial,),
        successors=(predecessor,),
    )
    _activate(repository, first_fence, first)
    service.persist(
        fence=first_fence,
        terminal=first,
        authorization_verifier=AUTHORIZATION,
    )
    if operation_kind == "merge":
        predecessors = tuple(
            sorted(
                (
                    predecessor,
                    LineageEntityIdentity(
                        entity_revision_id="entity-revision:bob:v1",
                        logical_entity_id="entity:bob",
                    ),
                ),
                key=lambda item: item.entity_revision_id,
            )
        )
        successors = (
            LineageEntityIdentity(
                entity_revision_id="entity-revision:people:v1",
                logical_entity_id="entity:people",
            ),
        )
    else:
        predecessors = (predecessor,)
        successors = tuple(
            sorted(
                (
                    LineageEntityIdentity(
                        entity_revision_id="entity-revision:atlas-a:v1",
                        logical_entity_id="entity:atlas-a",
                    ),
                    LineageEntityIdentity(
                        entity_revision_id="entity-revision:atlas-b:v1",
                        logical_entity_id="entity:atlas-b",
                    ),
                ),
                key=lambda item: item.entity_revision_id,
            )
        )

    def assignments(
        snapshot: SealedGraphStateSnapshot,
        evidence: LineageEvidenceReference,
    ) -> tuple[GroundedLineageReferenceAssignment, ...]:
        if operation_kind == "merge":
            return ()
        closure = derive_total_reverse_reference_closure(
            materialized_records=snapshot.graph_state.materialized_records,
            predecessors=predecessors,
            recorded_before=snapshot.system_as_of,
        )
        return tuple(
            GroundedLineageReferenceAssignment(
                reference_digest=reference.reference_digest,
                successors=(successors[0],),
                disposition="redirect_current",
                source_evidence=(evidence,),
            )
            for reference in closure
            if reference.lifecycle == "current"
        )

    _, identity_fence = handoff(
        plane,
        coordinate=f"populated-{operation_kind}",
        atomic_store=store,
        writer_binding=binding,
    )
    identity = _trusted_identity_terminal(
        store=store,
        writers=writers,
        fence=identity_fence,
        operation_kind=operation_kind,
        predecessors=predecessors,
        successors=successors,
        reference_assignment_builder=assignments,
    )
    _activate(repository, identity_fence, identity)
    service.persist(
        fence=identity_fence,
        terminal=identity,
        authorization_verifier=AUTHORIZATION,
    )
    committed_state = store.semantic_replay_state()

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
        identity_decision_authority_verifier=IDENTITY_AUTHORITY_VERIFIER,
    )
    reopened_state = reopened_store.semantic_replay_state()
    assert reopened_state == committed_state
    validate_reference_integrity_converse(
        reopened_store.reference_integrity_snapshot(), reopened_state
    )
    lineage = replay_identity_lineage(reopened_state)
    assert len(lineage.transitions) == 2
    first_transition = lineage.transitions[0][0]
    transition = lineage.transitions[1][0]
    assert first_transition.predecessors == (initial,)
    assert first_transition.successors == (predecessor,)
    assert transition.predecessors == predecessors
    assert transition.successors == successors
    projections = tuple(
        item.record
        for item in reopened_state.materialized_records
        if item.record_kind == "entity_revision"
        and item.record_id == predecessor.entity_revision_id
    )
    assert len(projections) == 1
    assert projections[0].record_version == 2
    assert projections[0].logical_entity_id == successors[0].logical_entity_id


def test_split_with_incomplete_reference_closure_is_noncommitting() -> None:
    plane, _, store, binding, fact_fence, service, repository = _setup(verified=True)
    store.bootstrap_reference_integrity(writer_binding=binding)
    fact = accepted_terminal(operation_id=fact_fence.operation_id)
    _activate(repository, fact_fence, fact)
    service.persist(fence=fact_fence, terminal=fact, authorization_verifier=AUTHORIZATION)
    state_after_fact = store.semantic_replay_state()
    ledger_after_fact = store.reference_integrity_snapshot()
    _, split_fence = handoff(
        plane,
        coordinate="split-incomplete",
        atomic_store=store,
        writer_binding=binding,
    )

    def accepted_provider(operation_id: str):
        return AcceptedIdentityOperation.create(
            operation_id=operation_id,
            operation="split",
            predecessors=(LineageEntityIdentity(
                entity_revision_id="entity-revision:atlas:v1",
                logical_entity_id="entity:atlas",
            ),),
            successors=tuple(sorted((
                LineageEntityIdentity(entity_revision_id="atlas-a:v1", logical_entity_id="atlas-a"),
                LineageEntityIdentity(entity_revision_id="atlas-b:v1", logical_entity_id="atlas-b"),
            ), key=lambda item: item.entity_revision_id)),
            source_evidence=(LineageEvidenceReference(
                source_id=split_fence.source_id,
                start=0,
                end=5,
                evidence_digest=sha256(b"incomplete split").hexdigest(),
            ),),
            reference_assignments=(),
        )

    artifact_repository = _AcceptedIdentityArtifactRepository(
        accepted_provider,
        fence=split_fence,
        graph_revision=store.semantic_replay_state().graph_revision,
    )
    compiler = ProductionIdentityLineageCompiler(
        SemanticIngestionTransactionCoordinator(store, now_provider=lambda: NOW),
        artifact_repository,
    )
    split = accepted_terminal(
        operation_id=split_fence.operation_id,
        operation_kind="identity",
        identity_lineage_compiler=compiler,
    )
    assert split.status == "unresolved"
    assert split.reason_codes == ("identity_lineage_compilation_failed",)
    _activate(repository, split_fence, split)
    service.persist(
        fence=split_fence,
        terminal=split,
        authorization_verifier=AUTHORIZATION,
    )
    assert store.semantic_replay_state() == state_after_fact
    assert store.reference_integrity_snapshot() == ledger_after_fact


def test_source_swapped_terminal_is_rejected_before_any_record_is_written() -> None:
    plane, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(
        operation_id=fence.operation_id,
        source_id="tx:foreign-source",
        source_digest="f" * 64,
    )
    _activate(repository, fence, terminal)
    before = tuple(plane.list_records())
    before_control = store.get_operation(fence)

    with pytest.raises(
        ValueError,
        match="semantic analysis does not bind the admitted source",
    ):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )

    assert tuple(plane.list_records()) == before
    assert store.get_operation(fence) == before_control


@pytest.mark.parametrize(
    ("status", "reason_codes"),
    (
        ("unresolved", ("consensus_unresolved",)),
        ("rejected", ("policy_rejected",)),
        ("evidence_only", ("insufficient_commit_authority",)),
        # Analyzer failure is represented by an unresolved terminal; there is no
        # separate persisted "failed" terminal status.
        ("unresolved", ("analyzer_failed",)),
    ),
    ids=("unresolved", "rejected", "evidence-only", "failed"),
)
def test_nonaccepted_foreign_analysis_is_rejected_before_any_effect(
    status: Literal["unresolved", "rejected", "evidence_only"],
    reason_codes: tuple[str, ...],
) -> None:
    plane, _, store, _, fence, service, _ = _setup(verified=True)
    foreign = accepted_terminal(
        operation_id=fence.operation_id,
        source_id="tx:foreign-source",
        source_digest="f" * 64,
    )
    terminal = SemanticTerminalOutcome.create(
        operation_id=fence.operation_id,
        status=status,
        reason_codes=reason_codes,
        candidates=foreign.candidates,
        source_analyses=foreign.source_analyses,
        temporal_closures=(),
        attempt_count=1,
    )
    before_records = tuple(plane.list_records())
    before_control = store.get_operation(fence)
    before_replay = store.semantic_replay_authority()

    with pytest.raises(
        ValueError,
        match="semantic analysis does not bind the admitted source",
    ):
        service.persist(fence=fence, terminal=terminal)

    assert tuple(plane.list_records()) == before_records
    assert store.get_operation(fence) == before_control
    assert store.semantic_replay_authority() == before_replay


@pytest.mark.parametrize(
    ("status", "reason_codes"),
    (
        ("unresolved", ("consensus_unresolved",)),
        ("rejected", ("policy_rejected",)),
        ("evidence_only", ("insufficient_commit_authority",)),
        ("unresolved", ("analyzer_failed",)),
    ),
    ids=("unresolved", "rejected", "evidence-only", "failed"),
)
def test_nonaccepted_foreign_typed_source_authority_is_rejected_before_any_effect(
    status: Literal["unresolved", "rejected", "evidence_only"],
    reason_codes: tuple[str, ...],
) -> None:
    plane, _, store, _, fence, service, _ = _setup(verified=True)
    foreign = accepted_terminal(
        operation_id=fence.operation_id,
        source_id="tx:foreign-source",
        source_digest="f" * 64,
    )
    terminal = SemanticTerminalOutcome.create(
        operation_id=fence.operation_id,
        status=status,
        reason_codes=reason_codes,
        candidates=foreign.candidates,
        source_analyses=(),
        temporal_closures=foreign.temporal_closures,
        sealed_operations=foreign.sealed_operations,
        terminal_binding_sets=foreign.terminal_binding_sets,
        attempt_count=1,
    )
    before_records = tuple(plane.list_records())
    before_control = store.get_operation(fence)
    before_state = store.semantic_replay_state()
    before_replay = store.semantic_replay_authority()
    before_batches = store.semantic_event_batches()
    before_projection_bindings = store.projection_history.replay_bindings()

    with pytest.raises(
        ValueError,
        match="semantic source authority does not bind the admitted source",
    ):
        service.persist(fence=fence, terminal=terminal)

    assert tuple(plane.list_records()) == before_records
    assert store.get_operation(fence) == before_control
    assert store.semantic_replay_state() == before_state
    assert store.semantic_replay_authority() == before_replay
    assert store.semantic_event_batches() == before_batches
    assert (
        store.projection_history.replay_bindings()
        == before_projection_bindings
    )


@pytest.mark.parametrize(
    ("status", "reason_codes"),
    (
        ("unresolved", ("consensus_unresolved",)),
        ("rejected", ("policy_rejected",)),
        ("evidence_only", ("insufficient_commit_authority",)),
        ("unresolved", ("analyzer_failed",)),
    ),
    ids=("unresolved", "rejected", "evidence-only", "failed"),
)
def test_nonaccepted_zero_analysis_terminal_remains_valid(
    status: Literal["unresolved", "rejected", "evidence_only"],
    reason_codes: tuple[str, ...],
) -> None:
    plane, _, store, _, fence, service, _ = _setup(verified=True)
    terminal = _nonaccepted(
        fence.operation_id,
        status=status,
        reason_codes=reason_codes,
    )

    service.persist(fence=fence, terminal=terminal)

    control = store.get_operation(fence)
    assert control.state == "terminal"
    assert control.graph_revision == "genesis"
    assert control.observation_revision != "genesis"
    assert store.semantic_event_batches() == ()
    assert store.semantic_replay_authority().latest_checkpoint is None
    assert plane.list_records()


@pytest.mark.parametrize("foreign_kind", ("analysis", "typed-authority"))
@pytest.mark.parametrize(
    ("status", "reason_codes"),
    (
        ("unresolved", ("consensus_unresolved",)),
        ("rejected", ("policy_rejected",)),
        ("evidence_only", ("insufficient_commit_authority",)),
        ("unresolved", ("analyzer_failed",)),
    ),
    ids=("unresolved", "rejected", "evidence-only", "failed"),
)
def test_direct_terminal_checkpoint_foreign_source_closure_has_zero_effects_across_reopen(
    foreign_kind: str,
    status: Literal["unresolved", "rejected", "evidence_only"],
    reason_codes: tuple[str, ...],
    tmp_path,
) -> None:
    storage = tmp_path / f"direct-{foreign_kind}-{status}-{reason_codes[0]}"
    plane, _, store, binding, fence, _, _ = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    foreign = accepted_terminal(
        operation_id=fence.operation_id,
        source_id="tx:foreign-source",
        source_digest="f" * 64,
    )
    terminal = SemanticTerminalOutcome.create(
        operation_id=fence.operation_id,
        status=status,
        reason_codes=reason_codes,
        candidates=foreign.candidates,
        source_analyses=(
            foreign.source_analyses if foreign_kind == "analysis" else ()
        ),
        temporal_closures=(
            foreign.temporal_closures
            if foreign_kind == "typed-authority"
            else ()
        ),
        sealed_operations=(
            foreign.sealed_operations
            if foreign_kind == "typed-authority"
            else ()
        ),
        terminal_binding_sets=(
            foreign.terminal_binding_sets
            if foreign_kind == "typed-authority"
            else ()
        ),
        attempt_count=1,
    )
    request = _direct_terminal_checkpoint_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    )
    before_records = tuple(plane.list_records())
    before_control = store.get_operation(fence)
    before_state = store.semantic_replay_state()
    before_authority = store.semantic_replay_authority()
    before_batches = store.semantic_event_batches()
    before_projection_bindings = store.projection_history.replay_bindings()

    for _ in range(4):
        with pytest.raises(
            PreplanningStoreError,
            match="terminal does not bind its admitted operation source",
        ):
            store.checkpoint_source_progress(request)
        assert tuple(plane.list_records()) == before_records
        assert store.get_operation(fence) == before_control
        assert store.get_operation(fence).observation_revision == (
            before_control.observation_revision
        )
        assert store.semantic_replay_state() == before_state
        assert store.semantic_replay_authority() == before_authority
        assert (
            store.semantic_replay_authority().artifact_bindings
            == before_authority.artifact_bindings
        )
        assert store.semantic_event_batches() == before_batches
        assert (
            store.projection_history.replay_bindings()
            == before_projection_bindings
        )

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    assert _json_round_tripped(tuple(reopened_plane.list_records())) == _json_round_tripped(before_records)
    assert reopened_store.get_operation(fence) == before_control
    assert reopened_store.semantic_replay_state() == before_state
    assert reopened_store.semantic_replay_authority() == before_authority
    assert reopened_store.semantic_event_batches() == before_batches
    assert (
        reopened_store.projection_history.replay_bindings()
        == before_projection_bindings
    )


@pytest.mark.parametrize("foreign_source", (False, True), ids=("same-source", "foreign-source"))
def test_preplanning_terminal_checkpoint_is_illegal_and_cannot_authorize_a_group(
    foreign_source: bool,
    tmp_path,
) -> None:
    storage = tmp_path / f"preplanning-terminal-{foreign_source}"
    plane, _, store, binding, fence, _, _ = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    if foreign_source:
        foreign = accepted_terminal(
            operation_id=fence.operation_id,
            source_id="tx:foreign-source",
            source_digest="f" * 64,
        )
        terminal = SemanticTerminalOutcome.create(
            operation_id=fence.operation_id,
            status="unresolved",
            reason_codes=("consensus_unresolved",),
            candidates=foreign.candidates,
            source_analyses=foreign.source_analyses,
            temporal_closures=(),
            attempt_count=1,
        )
    else:
        terminal = _nonaccepted(fence.operation_id)
    checkpoint = _direct_terminal_checkpoint_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    ).model_copy(update={"progress_state": "preplanning", "request_digest": "0" * 64})
    checkpoint = checkpoint.model_copy(
        update={"request_digest": generation_request_digest(checkpoint)}
    )
    before_records = tuple(plane.list_records())
    before_control = store.get_operation(fence)
    before_state = store.semantic_replay_state()
    before_authority = store.semantic_replay_authority()
    before_batches = store.semantic_event_batches()
    before_projection_bindings = store.projection_history.replay_bindings()

    for _ in range(4):
        with pytest.raises(
            PreplanningStoreError,
            match="terminal artifacts are legal only in the canonical planned checkpoint",
        ):
            store.checkpoint_source_progress(checkpoint)
        assert tuple(plane.list_records()) == before_records
        assert store.get_operation(fence) == before_control
        assert store.semantic_replay_state() == before_state
        assert store.semantic_replay_authority() == before_authority
        assert store.semantic_event_batches() == before_batches
        assert (
            store.projection_history.replay_bindings()
            == before_projection_bindings
        )

    group = _direct_noncommitting_group_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    )
    with pytest.raises(
        PreplanningStoreError,
        match="terminal group requires planned source progress",
    ):
        store.persist_terminal_group(group)
    assert tuple(plane.list_records()) == before_records
    assert store.get_operation(fence) == before_control

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    assert _json_round_tripped(tuple(reopened_plane.list_records())) == _json_round_tripped(before_records)
    assert reopened_store.get_operation(fence) == before_control
    assert reopened_store.semantic_replay_state() == before_state
    assert reopened_store.semantic_replay_authority() == before_authority
    assert reopened_store.semantic_event_batches() == before_batches
    assert (
        reopened_store.projection_history.replay_bindings()
        == before_projection_bindings
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "artifact-closure",
        "artifact-index",
        "planning-artifact",
        "planning-authorization",
    ),
)
def test_direct_terminal_checkpoint_rejects_substituted_planning_closure(
    mutation: str,
) -> None:
    plane, _, store, binding, fence, _, _ = _setup(verified=True)
    terminal = _nonaccepted(fence.operation_id)
    request = _direct_terminal_checkpoint_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    )
    if mutation == "artifact-closure":
        substituted_terminal = _nonaccepted(
            fence.operation_id,
            status="rejected",
            reason_codes=("policy_rejected",),
        )
        payload = encode_semantic_contract(
            SemanticArtifactClosure.create(substituted_terminal)
        )
        target_kind = "artifact_closure"
    elif mutation == "artifact-index":
        payload = encode_typed_value(
            {"terminal": "f" * 64, "closure": "e" * 64}
        )
        target_kind = "artifact_index"
    elif mutation == "planning-artifact":
        payload = encode_typed_value(
            {
                "operation_id": fence.operation_id,
                "terminal_digest": "f" * 64,
                "execution_lineage": None,
            }
        )
        target_kind = "planning_artifact"
    else:
        payload = encode_typed_value(
            {
                "writer_admission_digest": "f" * 64,
                "policy_bundle_digest": None,
                "execution_lineage_digest": None,
            }
        )
        target_kind = "planning_authorization"
    members = tuple(
        member.model_copy(
            update={
                "canonical_payload": payload,
                "payload_digest": sha256(payload).hexdigest(),
            }
        )
        if member.kind == target_kind
        else member
        for member in request.members
    )
    mutant = request.model_copy(
        update={"members": members, "request_digest": "0" * 64}
    )
    mutant = mutant.model_copy(
        update={"request_digest": generation_request_digest(mutant)}
    )
    before_records = tuple(plane.list_records())
    before_control = store.get_operation(fence)
    before_authority = store.semantic_replay_authority()

    with pytest.raises(
        PreplanningStoreError,
        match="terminal artifact closure|planned terminal checkpoint",
    ):
        store.checkpoint_source_progress(mutant)

    assert tuple(plane.list_records()) == before_records
    assert store.get_operation(fence) == before_control
    assert store.semantic_replay_authority() == before_authority
    assert store.semantic_event_batches() == ()
    assert store.projection_history.replay_bindings() == ()


def test_direct_checkpoint_rejects_missing_retained_planned_terminal() -> None:
    plane, _, store, binding, fence, _, _ = _setup(verified=True)
    terminal = _nonaccepted(fence.operation_id)
    checkpoint = _direct_terminal_checkpoint_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    )
    members = tuple(
        member for member in checkpoint.members if member.kind != "terminal_artifact"
    )
    checkpoint = checkpoint.model_copy(
        update={"members": members, "request_digest": "0" * 64}
    )
    checkpoint = checkpoint.model_copy(
        update={"request_digest": generation_request_digest(checkpoint)}
    )
    before_records = tuple(plane.list_records())
    before_control = store.get_operation(fence)
    before_authority = store.semantic_replay_authority()

    with pytest.raises(
        SemanticEventReplayError,
        match="semantic replay member has an unresolved cross-generation reference",
    ):
        store.checkpoint_source_progress(checkpoint)

    assert tuple(plane.list_records()) == before_records
    assert store.get_operation(fence) == before_control
    assert before_control.group_result_digests == ()
    assert store.semantic_replay_authority() == before_authority
    assert store.semantic_event_batches() == ()
    assert store.projection_history.replay_bindings() == ()


@pytest.mark.parametrize(
    ("status", "reason_codes"),
    (
        ("unresolved", ("consensus_unresolved",)),
        ("rejected", ("policy_rejected",)),
        ("evidence_only", ("insufficient_commit_authority",)),
        ("unresolved", ("analyzer_failed",)),
    ),
    ids=("unresolved", "rejected", "evidence-only", "failed"),
)
def test_valid_direct_noncommitting_terminal_group_succeeds_exactly_once(
    status: Literal["unresolved", "rejected", "evidence_only"],
    reason_codes: tuple[str, ...],
) -> None:
    plane, _, store, binding, fence, _, _ = _setup(verified=True)
    terminal = _nonaccepted(
        fence.operation_id,
        status=status,
        reason_codes=reason_codes,
    )
    request = _direct_noncommitting_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
    )
    before_authority = store.semantic_replay_authority()

    first = store.persist_terminal_group(request)
    after_first_records = tuple(plane.list_records())
    after_first_control = store.get_operation(fence)
    after_first_authority = store.semantic_replay_authority()
    second = store.persist_terminal_group(request)

    assert first == second == request.members
    assert tuple(plane.list_records()) == after_first_records
    assert store.get_operation(fence) == after_first_control
    assert after_first_control.graph_revision == "genesis"
    assert (
        after_first_control.observation_revision
        == request.observation_revision_after
    )
    assert store.semantic_replay_state().graph_revision == "genesis"
    assert store.semantic_event_batches() == ()
    assert after_first_authority.latest_checkpoint is None
    assert len(after_first_authority.observation_bindings) == 1
    assert len(after_first_authority.artifact_bindings) > len(
        before_authority.artifact_bindings
    )
    assert store.semantic_replay_authority() == after_first_authority
    assert store.projection_history.replay_bindings() == ()


def test_direct_group_cannot_substitute_the_retained_planned_terminal(
    tmp_path,
) -> None:
    storage = tmp_path / "direct-planned-terminal-substitution"
    plane, _, store, binding, fence, _, _ = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    planned_terminal = _nonaccepted(
        fence.operation_id,
        status="unresolved",
        reason_codes=("consensus_unresolved",),
    )
    substituted_terminal = _nonaccepted(
        fence.operation_id,
        status="rejected",
        reason_codes=("policy_rejected",),
    )
    checkpoint = _direct_terminal_checkpoint_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=planned_terminal,
    )
    store.checkpoint_source_progress(checkpoint)
    request = _direct_noncommitting_group_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=substituted_terminal,
    )
    before_records = tuple(plane.list_records())
    before_control = store.get_operation(fence)
    before_state = store.semantic_replay_state()
    before_authority = store.semantic_replay_authority()
    before_batches = store.semantic_event_batches()
    before_projection_bindings = store.projection_history.replay_bindings()

    for _ in range(4):
        with pytest.raises(
            PreplanningStoreError,
            match="terminal group differs from its retained planned terminal closure",
        ):
            store.persist_terminal_group(request)
        assert tuple(plane.list_records()) == before_records
        assert store.get_operation(fence) == before_control
        assert store.semantic_replay_state() == before_state
        assert store.semantic_replay_authority() == before_authority
        assert store.semantic_event_batches() == before_batches
        assert (
            store.projection_history.replay_bindings()
            == before_projection_bindings
        )

    assert before_control.state == "planned"
    assert before_control.group_result_digests == ()
    assert not any(
        isinstance(member := record.content.get("member"), dict)
        and member.get("kind") == "source_result"
        for record in plane.list_records()
    )
    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    assert _json_round_tripped(tuple(reopened_plane.list_records())) == _json_round_tripped(before_records)
    assert reopened_store.get_operation(fence) == before_control
    assert reopened_store.semantic_replay_state() == before_state
    assert reopened_store.semantic_replay_authority() == before_authority
    assert reopened_store.semantic_event_batches() == before_batches
    assert (
        reopened_store.projection_history.replay_bindings()
        == before_projection_bindings
    )


@pytest.mark.parametrize("group_kind", ("committed", "noncommitting"))
@pytest.mark.parametrize(
    "mutation",
    (
        "omission",
        "duplicate",
        "alternate-terminal",
        "foreign-closure",
        "field",
        "type",
        "order",
    ),
)
def test_direct_terminal_group_rejects_artifact_index_mutation_without_any_effect(
    group_kind: str,
    mutation: str,
    tmp_path,
) -> None:
    storage = tmp_path / f"artifact-index-{group_kind}-{mutation}"
    plane, _, store, binding, fence, _, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    if group_kind == "committed":
        terminal = accepted_terminal(operation_id=fence.operation_id)
        _activate(repository, fence, terminal)
        request = _direct_committed_request(
            store=store,
            binding=binding,
            fence=fence,
            terminal=terminal,
            authorization_repository=repository,
        )
    else:
        terminal = _nonaccepted(fence.operation_id)
        request = _direct_noncommitting_request(
            store=store,
            binding=binding,
            fence=fence,
            terminal=terminal,
        )
    index = next(member for member in request.members if member.kind == "artifact_index")
    closure = SemanticArtifactClosure.create(terminal)
    alternate = _nonaccepted(
        fence.operation_id,
        status="rejected",
        reason_codes=("policy_rejected",),
    )
    if mutation == "omission":
        members = tuple(
            member for member in request.members if member.kind != "artifact_index"
        )
    elif mutation == "duplicate":
        duplicate = index.model_copy(
            update={"member_id": "semantic-ingestion-99-artifact-index-duplicate"}
        )
        members = tuple(sorted((*request.members, duplicate), key=lambda member: member.member_id))
    else:
        if mutation == "alternate-terminal":
            payload = encode_typed_value(
                {
                    "terminal": alternate.terminal_digest,
                    "closure": closure.closure_digest,
                }
            )
        elif mutation == "foreign-closure":
            payload = encode_typed_value(
                {
                    "terminal": terminal.terminal_digest,
                    "closure": SemanticArtifactClosure.create(alternate).closure_digest,
                }
            )
        elif mutation == "field":
            payload = encode_typed_value(
                {
                    "terminal": terminal.terminal_digest,
                    "closure": closure.closure_digest,
                    "extra": "substituted",
                }
            )
        elif mutation == "type":
            payload = encode_typed_value(
                {
                    "terminal": 1,
                    "closure": closure.closure_digest,
                }
            )
        else:
            payload = (
                '{"$type":"map","entries":[["terminal","'
                + terminal.terminal_digest
                + '"],["closure","'
                + closure.closure_digest
                + '"]]}'
            ).encode()
        members = tuple(
            member.model_copy(
                update={
                    "canonical_payload": payload,
                    "payload_digest": sha256(payload).hexdigest(),
                }
            )
            if member.kind == "artifact_index"
            else member
            for member in request.members
        )
    mutant = request.model_copy(
        update={"members": members, "request_digest": "0" * 64}
    )
    mutant = mutant.model_copy(
        update={"request_digest": generation_request_digest(mutant)}
    )
    before_records = tuple(plane.list_records())
    before_control = store.get_operation(fence)
    before_state = store.semantic_replay_state()
    before_authority = store.semantic_replay_authority()
    before_batches = store.semantic_event_batches()
    before_projection_bindings = store.projection_history.replay_bindings()

    for _ in range(4):
        with pytest.raises(
            PreplanningStoreError,
            match=(
                "terminal group generation is incomplete"
                if mutation in {"omission", "duplicate"}
                else "terminal group artifact index is not canonical"
            ),
        ):
            store.persist_terminal_group(mutant)
        assert tuple(plane.list_records()) == before_records
        assert store.get_operation(fence) == before_control
        assert store.get_operation(fence).observation_revision == (
            before_control.observation_revision
        )
        assert store.semantic_replay_state() == before_state
        assert store.semantic_replay_authority() == before_authority
        assert (
            store.semantic_replay_authority().artifact_bindings
            == before_authority.artifact_bindings
        )
        assert store.semantic_event_batches() == before_batches
        assert (
            store.projection_history.replay_bindings()
            == before_projection_bindings
        )

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    assert _json_round_tripped(tuple(reopened_plane.list_records())) == _json_round_tripped(before_records)
    assert reopened_store.get_operation(fence) == before_control
    assert reopened_store.semantic_replay_state() == before_state
    assert reopened_store.semantic_replay_authority() == before_authority
    assert reopened_store.semantic_event_batches() == before_batches
    assert (
        reopened_store.projection_history.replay_bindings()
        == before_projection_bindings
    )


def test_valid_direct_committed_terminal_group_remains_idempotent() -> None:
    plane, _, store, binding, fence, _, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    request = _direct_committed_request(
        store=store,
        binding=binding,
        fence=fence,
        terminal=terminal,
        authorization_repository=repository,
    )

    first = store.persist_terminal_group(request)
    after_records = tuple(plane.list_records())
    after_control = store.get_operation(fence)
    after_authority = store.semantic_replay_authority()
    second = store.persist_terminal_group(request)

    assert first == second == request.members
    assert tuple(plane.list_records()) == after_records
    assert store.get_operation(fence) == after_control
    assert store.semantic_replay_authority() == after_authority
    assert len(store.semantic_event_batches()) == 1
    assert after_authority.latest_checkpoint is not None
    assert store.projection_history.replay_bindings()


def test_cross_group_graph_delta_substitution_has_zero_atomic_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane, _, store, _, fence, service, repository = _setup(verified=True)
    terminal_a = accepted_terminal(operation_id=fence.operation_id)
    terminal_b = accepted_terminal(
        operation_id=fence.operation_id,
        source_id=fence.source_id,
        source_digest=fence.source_digest,
        object_logical_entity_id="entity:foreign-employer",
        object_entity_revision_id="entity-revision:foreign-employer:v1",
    )
    delta_b_bytes = encode_semantic_contract(SemanticGraphDelta.create(terminal_b))
    _activate(repository, fence, terminal_a)
    original = store.persist_terminal_group
    attempts = 0

    def substitute_graph_delta(request):
        nonlocal attempts
        attempts += 1
        members = tuple(
            member.model_copy(
                update={
                    "canonical_payload": delta_b_bytes,
                    "payload_digest": sha256(delta_b_bytes).hexdigest(),
                }
            )
            if member.kind == "graph_delta"
            else member
            for member in request.members
        )
        mutant = request.model_copy(update={"members": members, "request_digest": "0" * 64})
        mutant = mutant.model_copy(update={"request_digest": generation_request_digest(mutant)})
        before = tuple(plane.list_records())
        with pytest.raises(
            PreplanningStoreError,
            match="canonical semantic event batch is invalid",
        ):
            original(mutant)
        assert tuple(plane.list_records()) == before
        raise PreplanningStoreError("injected cross-group delta substitution")

    monkeypatch.setattr(store, "persist_terminal_group", substitute_graph_delta)
    with pytest.raises(
        PreplanningStoreError,
        match="terminal-group retry budget exhausted",
    ):
        service.persist(
            fence=fence,
            terminal=terminal_a,
            authorization_verifier=AUTHORIZATION,
        )

    assert attempts == 4
    control = store.get_operation(fence)
    assert control.state == "planned"
    assert control.graph_revision == "genesis"
    assert control.group_result_digests == ()
    assert store.semantic_event_batches() == ()


@pytest.mark.parametrize(
    ("event_payload", "error_message"),
    (
        (b"opaque historical event input", "semantic event batch validation failed"),
        (
            encode_typed_value(
                {
                    "schema": "memorii.semantic-memory-event-batch-envelope.v999",
                    "payload": {},
                }
            ),
            "semantic event batch envelope is not closed",
        ),
    ),
    ids=("opaque", "wrong-envelope-schema"),
)
def test_committed_event_batch_rejects_noncurrent_bytes_without_any_effect(
    monkeypatch: pytest.MonkeyPatch,
    event_payload: bytes,
    error_message: str,
) -> None:
    plane, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = store.persist_terminal_group
    attempts = 0

    def substitute_event_batch(request):
        nonlocal attempts
        attempts += 1
        members = tuple(
            member.model_copy(
                update={
                    "canonical_payload": event_payload,
                    "payload_digest": sha256(event_payload).hexdigest(),
                }
            )
            if member.kind == "event_batch"
            else member
            for member in request.members
        )
        mutant = request.model_copy(
            update={"members": members, "request_digest": "0" * 64}
        )
        mutant = mutant.model_copy(
            update={"request_digest": generation_request_digest(mutant)}
        )
        before_records = tuple(plane.list_records())
        before_control = store.get_operation(fence)
        before_state = store.semantic_replay_state()
        before_authority = store.semantic_replay_authority()
        before_batches = store.semantic_event_batches()
        before_projection_bindings = store.projection_history.replay_bindings()

        with pytest.raises(
            SemanticEventReplayError,
            match=error_message,
        ):
            original(mutant)

        assert tuple(plane.list_records()) == before_records
        assert store.get_operation(fence) == before_control
        assert store.semantic_replay_state() == before_state
        assert store.semantic_replay_authority() == before_authority
        assert store.semantic_event_batches() == before_batches
        assert (
            store.projection_history.replay_bindings()
            == before_projection_bindings
        )
        raise PreplanningStoreError("injected noncurrent event bytes")

    monkeypatch.setattr(
        store,
        "persist_terminal_group",
        substitute_event_batch,
    )
    with pytest.raises(
        PreplanningStoreError,
        match="terminal-group retry budget exhausted",
    ):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )

    assert attempts == 4
    control = store.get_operation(fence)
    assert control.state == "planned"
    assert control.graph_revision == "genesis"
    assert control.observation_revision == "genesis"
    assert control.group_result_digests == ()
    assert store.semantic_event_batches() == ()
    assert store.semantic_replay_authority().latest_checkpoint is None
    assert store.projection_history.replay_bindings() == ()


def test_committed_event_batch_rejects_canonical_foreign_transaction_group_without_any_effect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    storage = tmp_path / "foreign-event-transaction-group"
    plane, _, store, _, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = store.persist_terminal_group
    attempts = 0

    def substitute_transaction_group(request):
        nonlocal attempts
        attempts += 1
        event_member = next(
            member for member in request.members if member.kind == "event_batch"
        )
        graph_member = next(
            member for member in request.members if member.kind == "graph_delta"
        )
        admitted_batch = decode_semantic_memory_event_batch(
            event_member.canonical_payload,
            registry_history=store.event_schema_registry_history,
        )
        graph_delta = decode_semantic_contract(
            graph_member.canonical_payload,
            SemanticGraphDelta,
        )
        foreign_batch = build_semantic_memory_event_batch(
            graph_delta=graph_delta,
            prior_state=store.semantic_replay_state(),
            repository_id=admitted_batch.repository_id,
            source_id=admitted_batch.source_id,
            transaction_group_id="op:foreign-transaction-group",
            operation_fence_id=admitted_batch.operation_fence_id,
            writer_epoch=admitted_batch.writer_epoch,
            graph_revision_before=(
                admitted_batch.events[0].payload.graph_revision_before
            ),
            graph_revision_after=(
                admitted_batch.events[-1].payload.graph_revision_after
            ),
            timestamp=admitted_batch.events[0].timestamp,
            registry=store.event_schema_registry,
        )
        foreign_bytes = encode_semantic_memory_event_batch(foreign_batch)
        members = tuple(
            member.model_copy(
                update={
                    "canonical_payload": foreign_bytes,
                    "payload_digest": sha256(foreign_bytes).hexdigest(),
                }
            )
            if member.kind == "event_batch"
            else member
            for member in request.members
        )
        mutant = request.model_copy(
            update={"members": members, "request_digest": "0" * 64}
        )
        mutant = mutant.model_copy(
            update={"request_digest": generation_request_digest(mutant)}
        )
        before_records = tuple(plane.list_records())
        before_control = store.get_operation(fence)
        before_state = store.semantic_replay_state()
        before_authority = store.semantic_replay_authority()
        before_batches = store.semantic_event_batches()
        before_projection_bindings = store.projection_history.replay_bindings()

        with pytest.raises(
            PreplanningStoreError,
            match="canonical semantic event batch is invalid",
        ):
            original(mutant)

        assert tuple(plane.list_records()) == before_records
        assert store.get_operation(fence) == before_control
        assert store.semantic_replay_state() == before_state
        assert store.semantic_replay_authority() == before_authority
        assert store.semantic_event_batches() == before_batches
        assert (
            store.projection_history.replay_bindings()
            == before_projection_bindings
        )
        raise PreplanningStoreError("injected foreign transaction group")

    monkeypatch.setattr(
        store,
        "persist_terminal_group",
        substitute_transaction_group,
    )
    with pytest.raises(
        PreplanningStoreError,
        match="terminal-group retry budget exhausted",
    ):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )

    assert attempts == 4
    final_records = tuple(plane.list_records())
    final_control = store.get_operation(fence)
    final_state = store.semantic_replay_state()
    final_authority = store.semantic_replay_authority()
    final_batches = store.semantic_event_batches()
    final_projection_bindings = store.projection_history.replay_bindings()
    assert final_control.state == "planned"
    assert final_control.graph_revision == "genesis"
    assert final_control.observation_revision == "genesis"
    assert final_control.group_result_digests == ()
    assert final_batches == ()
    assert final_authority.latest_checkpoint is None
    assert final_projection_bindings == ()

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    assert _json_round_tripped(tuple(reopened_plane.list_records())) == (
        _json_round_tripped(final_records)
    )
    assert reopened_store.get_operation(fence) == final_control
    assert reopened_store.semantic_replay_state() == final_state
    assert reopened_store.semantic_replay_authority() == final_authority
    assert reopened_store.semantic_event_batches() == final_batches
    assert (
        reopened_store.projection_history.replay_bindings()
        == final_projection_bindings
    )


def test_real_terminal_updates_publish_immutable_projection_generations_after_reopen(
    tmp_path,
) -> None:
    storage = tmp_path / "projection-generation-reopen"
    clock = [NOW]
    plane, _, store, binding, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: clock[0],
        with_test_conflict_authority=True,
    )
    first_terminal = accepted_terminal(
        operation_id=fence.operation_id,
        valid_start=NOW,
        valid_end=NOW + timedelta(days=15),
        temporal_requirement="optional",
    )
    _activate(repository, fence, first_terminal)
    service.persist(
        fence=fence,
        terminal=first_terminal,
        authorization_verifier=AUTHORIZATION,
    )
    first_temporal = _projection_generations(plane, kind="temporal")
    first_trust = _projection_generations(plane, kind="trust")
    assert len(first_temporal) == len(first_trust) == 1
    first_generation_bytes = tuple(
        record.content["canonical_hex"]
        for record in plane.list_records(source_kind="semantic_projection_temporal_generation")
    )

    clock[0] = NOW + timedelta(hours=1)
    _, second_fence = handoff(
        plane,
        coordinate="projection-successor",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=binding,
    )
    second_terminal = accepted_terminal(
        operation_id=second_fence.operation_id,
        object_logical_entity_id="entity:initech",
        object_entity_revision_id="entity-revision:initech:v1",
        valid_start=NOW + timedelta(days=10),
        valid_end=NOW + timedelta(days=20),
        temporal_requirement="optional",
    )
    _activate(repository, second_fence, second_terminal)
    service.persist(
        fence=second_fence,
        terminal=second_terminal,
        authorization_verifier=AUTHORIZATION,
    )

    temporal = _projection_generations(plane, kind="temporal")
    trust = _projection_generations(plane, kind="trust")
    assert len(temporal) == len(trust) == 2
    assert temporal[1].predecessor_generation_digest == temporal[0].generation_digest
    assert trust[1].predecessor_generation_digest == trust[0].generation_digest
    assert (
        tuple(
            record.content["canonical_hex"]
            for record in plane.list_records(source_kind="semantic_projection_temporal_generation")
            if record.content["canonical_hex"] in first_generation_bytes
        )
        == first_generation_bytes
    )
    assert first_terminal.arbitration_policy_bundle is not None
    historical_first = store.projection_history.historical_temporal(
        system_as_of=NOW
    ).projections
    assert len(historical_first) == 1
    assert historical_first[0].source_record_version == 1
    assert historical_first[0].valid_interval == TimeInterval(
        start=NOW,
        end=NOW + timedelta(days=15),
    )

    def required_interval(projection: TemporalProjectionRecord) -> TimeInterval:
        assert projection.valid_interval is not None
        return projection.valid_interval

    finite_temporal = store.projection_history.current_temporal(
        policy_fingerprint=(first_terminal.arbitration_policy_bundle.temporal_policy.fingerprint)
    ).projections
    assert all(projection.valid_interval is not None for projection in finite_temporal)
    finite_temporal = tuple(
        sorted(
            finite_temporal,
            key=lambda projection: required_interval(projection).start,
        )
    )
    assert tuple(projection.outcome for projection in finite_temporal) == (
        "pass",
        "contested",
        "pass",
    )
    assert tuple(
        (
            required_interval(projection).start,
            required_interval(projection).end,
        )
        for projection in finite_temporal
    ) == (
        (NOW, NOW + timedelta(days=10)),
        (NOW + timedelta(days=10), NOW + timedelta(days=15)),
        (NOW + timedelta(days=15), NOW + timedelta(days=20)),
    )
    historical_overlap = store.projection_history.historical_temporal(
        system_as_of=NOW + timedelta(hours=1)
    ).projections
    assert all(
        projection.valid_interval is not None
        for projection in historical_overlap
    )
    assert tuple(
        sorted(
            historical_overlap,
            key=lambda projection: required_interval(projection).start,
        )
    ) == finite_temporal

    clock[0] = NOW + timedelta(hours=2)
    _, third_fence = handoff(
        plane,
        coordinate="projection-atemporal-successor",
        atomic_store=store,
        writer_binding=binding,
    )
    atemporal_terminal = accepted_terminal(
        operation_id=third_fence.operation_id,
        object_logical_entity_id="entity:umbrella",
        object_entity_revision_id="entity-revision:umbrella:v1",
        atemporal=True,
        temporal_requirement="optional",
    )
    _activate(repository, third_fence, atemporal_terminal)
    service.persist(
        fence=third_fence,
        terminal=atemporal_terminal,
        authorization_verifier=AUTHORIZATION,
    )
    temporal = _projection_generations(plane, kind="temporal")
    trust = _projection_generations(plane, kind="trust")
    assert len(temporal) == len(trust) == 3
    current_temporal = store.projection_history.current_temporal(
        policy_fingerprint=(first_terminal.arbitration_policy_bundle.temporal_policy.fingerprint)
    ).projections
    assert {
        projection.projection_digest
        for projection in current_temporal
        if projection.valid_interval is not None
    } == {projection.projection_digest for projection in finite_temporal}
    atemporal = tuple(
        projection for projection in current_temporal if projection.valid_interval is None
    )
    assert len(atemporal) == 1
    assert atemporal[0].outcome == "pass"
    atemporal_claim = atemporal_terminal.accepted_carriers[0]
    assert isinstance(atemporal_claim, ClaimAssertion)
    assert atemporal[0].selected_assertion_ids == (
        atemporal_claim.claim_assertion_id,
    )
    replay_authority = store.semantic_replay_authority()
    assert replay_authority.latest_checkpoint is not None
    checkpoint_state = store.validate_semantic_replay_checkpoint(replay_authority.latest_checkpoint)
    genesis_state = replay_semantic_event_batches(
        repository_id="semantic_ingestion",
        batches=store.semantic_event_batches(),
        registry_history=store.event_schema_registry_history,
    )
    assert encode_typed_value(
        {
            "graph_state": checkpoint_state.model_dump(mode="python"),
            "projection_history_bindings": tuple(
                binding.model_dump(mode="python")
                for binding in replay_authority.latest_checkpoint.checkpoint.projection_history_bindings
            ),
        }
    ) == encode_typed_value(
        {
            "graph_state": genesis_state.model_dump(mode="python"),
            "projection_history_bindings": tuple(
                binding.model_dump(mode="python") for binding in store.projection_history.replay_bindings()
            ),
        }
    )

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: clock[0],
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: clock[0],
    )
    reopened_checkpoint_state = reopened_store.validate_semantic_replay_checkpoint(
        replay_authority.latest_checkpoint
    )
    assert reopened_checkpoint_state == checkpoint_state
    assert (
        reopened_store.resume_semantic_replay_checkpoint_tail(
            replay_authority.latest_checkpoint,
            (),
        )
        == checkpoint_state
    )
    reopened_current = reopened_store.projection_history.current_temporal(
        policy_fingerprint=(first_terminal.arbitration_policy_bundle.temporal_policy.fingerprint)
    ).projections
    assert reopened_current == current_temporal

    detached = ProjectionHistoryRepository(
        reopened_plane,
        repository_id="semantic_ingestion",
        now_provider=lambda: clock[0],
    )
    with pytest.raises(
        ProjectionHistoryError,
        match="projection_history_unavailable",
    ):
        detached.current_temporal(
            policy_fingerprint=(first_terminal.arbitration_policy_bundle.temporal_policy.fingerprint)
        )


@pytest.fixture(scope="module")
def persisted_three_pointer_projection_authority(tmp_path_factory):
    base_storage = tmp_path_factory.mktemp("three-pointer-authority")
    clock = [NOW]
    plane, _, store, binding, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(base_storage),
        now_provider=lambda: clock[0],
    )
    first_terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, first_terminal)
    service.persist(
        fence=fence,
        terminal=first_terminal,
        authorization_verifier=AUTHORIZATION,
    )
    for version in (2, 3):
        clock[0] = NOW + timedelta(hours=version - 1)
        _, successor_fence = handoff(
            plane,
            coordinate=f"projection-pointer-{version}",
            atomic_store=store,
            writer_binding=binding,
        )
        terminal = accepted_terminal(operation_id=successor_fence.operation_id)
        _activate(repository, successor_fence, terminal)
        service.persist(
            fence=successor_fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )
    assert first_terminal.arbitration_policy_bundle is not None
    return (
        base_storage,
        first_terminal.arbitration_policy_bundle.temporal_policy.fingerprint,
        clock[0],
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "delete",
        "reorder",
        "duplicate",
        "predecessor_substitute",
        "cycle",
        "valid_prior_substitute",
    ),
)
def test_three_pointer_jsonl_corruption_fails_before_current_projection_view(
    tmp_path,
    mutation: str,
    persisted_three_pointer_projection_authority,
) -> None:
    base_storage, policy_fingerprint, now = persisted_three_pointer_projection_authority

    corrupted_storage = tmp_path / f"three-pointer-{mutation}"
    copytree(base_storage, corrupted_storage)
    backend = JsonlMemoryPlaneStore(corrupted_storage)
    corrupted_plane = MemoryPlaneService(record_store=backend)
    history_records = sorted(
        corrupted_plane.list_records(source_kind="semantic_projection_temporal_history_entry"),
        key=lambda record: record.memory_id,
    )
    assert len(history_records) == 3
    entries = tuple(_projection_authority_value(record, TemporalProjectionHistoryEntry) for record in history_records)
    active_record = corrupted_plane.list_records(source_kind="semantic_projection_temporal_active_pointer")[0]

    def changed_entry(
        index: int,
        *,
        predecessor: str,
    ) -> tuple[TemporalProjectionHistoryEntry, ActiveTemporalProjectionPointer]:
        pointer_values = entries[index].pointer.model_dump(
            mode="python",
            exclude={"pointer_digest"},
        )
        pointer_values["predecessor_pointer_digest"] = predecessor
        pointer = ActiveTemporalProjectionPointer.model_validate(
            {
                **pointer_values,
                "pointer_digest": projection_contract_digest(
                    "temporal_pointer",
                    pointer_values,
                ),
            }
        )
        entry_values = entries[index].model_dump(
            mode="python",
            exclude={"entry_digest", "pointer"},
        )
        entry_values["pointer"] = pointer
        entry = TemporalProjectionHistoryEntry.model_validate(
            {
                **entry_values,
                "entry_digest": projection_contract_digest(
                    "history_entry",
                    entry_values,
                ),
            }
        )
        return entry, pointer

    replacements: tuple[CanonicalMemoryRecord, ...] = ()
    deleted_ids: tuple[str, ...] = ()
    if mutation == "delete":
        deleted_ids = (history_records[1].memory_id,)
    elif mutation == "reorder":
        replacements = (
            history_records[1].model_copy(update={"memory_id": history_records[2].memory_id}),
            history_records[2].model_copy(update={"memory_id": history_records[1].memory_id}),
        )
    elif mutation == "duplicate":
        replacements = (
            history_records[1].model_copy(
                update={"memory_id": history_records[1].memory_id[:-20] + "00000000000000000004"}
            ),
        )
    else:
        predecessor = {
            "predecessor_substitute": sha256(b"foreign-pointer").hexdigest(),
            "cycle": entries[2].pointer.pointer_digest,
            "valid_prior_substitute": entries[0].pointer.pointer_digest,
        }[mutation]
        index = 1 if mutation in {"predecessor_substitute", "cycle"} else 2
        entry, pointer = changed_entry(index, predecessor=predecessor)
        replacements = (
            _projection_authority_record(history_records[index], entry),
            *((_projection_authority_record(active_record, pointer),) if index == 2 else ()),
        )
    _rewrite_jsonl_snapshot(
        backend,
        corrupted_plane,
        replacements=replacements,
        deleted_ids=deleted_ids,
    )

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(corrupted_storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: now,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: now,
    )
    current_view = None
    with pytest.raises(ProjectionHistoryError):
        current_view = reopened_store.projection_history.current_temporal(policy_fingerprint=policy_fingerprint)
    assert current_view is None


@pytest.mark.parametrize(
    "mutation",
    (
        "history_omission",
        "active_substitution",
        "generation_omission",
        "generation_base_graph_revision",
    ),
)
def test_persisted_projection_checkpoint_mutation_rejects_before_replay_exposure(
    tmp_path,
    mutation: str,
    persisted_three_pointer_projection_authority,
) -> None:
    base_storage, _, now = persisted_three_pointer_projection_authority
    corrupted_storage = tmp_path / f"checkpoint-projection-{mutation}"
    copytree(base_storage, corrupted_storage)
    backend = JsonlMemoryPlaneStore(corrupted_storage)
    plane = MemoryPlaneService(record_store=backend)
    temporal_history = sorted(
        plane.list_records(source_kind="semantic_projection_temporal_history_entry"),
        key=lambda record: record.memory_id,
    )
    temporal_active = plane.list_records(source_kind="semantic_projection_temporal_active_pointer")[0]
    trust_active = plane.list_records(source_kind="semantic_projection_trust_active_pointer")[0]
    active_pointer = _projection_authority_value(
        temporal_active,
        ActiveTemporalProjectionPointer,
    )
    temporal_generations = plane.list_records(source_kind="semantic_projection_temporal_generation")
    active_generation_record = next(
        record for record in temporal_generations if record.memory_id.endswith(active_pointer.generation_digest)
    )
    replacements: tuple[CanonicalMemoryRecord, ...] = ()
    deleted_ids: tuple[str, ...] = ()
    if mutation == "history_omission":
        deleted_ids = (temporal_history[-1].memory_id,)
    elif mutation == "active_substitution":
        replacements = (temporal_active.model_copy(update={"content": trust_active.content}),)
    elif mutation == "generation_omission":
        deleted_ids = (active_generation_record.memory_id,)
    else:
        generation = _projection_authority_value(
            active_generation_record,
            TemporalProjectionGeneration,
        ).model_copy(update={"base_graph_revision": "substituted-graph"})
        replacements = (_projection_authority_record(active_generation_record, generation),)
    _rewrite_jsonl_snapshot(
        backend,
        plane,
        replacements=replacements,
        deleted_ids=deleted_ids,
    )

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(corrupted_storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: now,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: now,
    )
    exposed = None
    with pytest.raises(PreplanningStoreError):
        exposed = reopened_store.semantic_replay_authority()
    assert exposed is None


@pytest.mark.parametrize(
    "recovery_mutation",
    (
        "none",
        "registry_history",
        "checkpoint_lifecycle",
        "forged_activated_status",
        "empty",
        "prefix",
        "duplicate",
        "reordered",
        "substituted_full_set",
    ),
)
def test_atomic_integrity_clean_recovery_activates_same_authority_after_restart(
    tmp_path,
    recovery_mutation: str,
) -> None:
    storage = tmp_path / "memory-plane"
    backend = JsonlMemoryPlaneStore(storage)
    integrity_path = tmp_path / "semantic-integrity" / "integrity.jsonl"
    linearization = ReplayIntegrityLinearization(tmp_path / "semantic-integrity" / "linearization.lock")
    holder: list[SemanticIngestionAtomicStore] = []
    repository = FileConflictIntegrityRepository(
        integrity_path,
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    crash_after_release = [True]

    def activate_or_crash(request: SemanticEventCleanRecoveryRequest) -> None:
        if crash_after_release[0]:
            crash_after_release[0] = False
            raise SystemExit("simulated crash after release")
        holder[0].activate_semantic_clean_recovery(request)

    lifecycle = PrivilegedSemanticIntegrityLifecycle(
        repository,
        clean_recovery_request_retainer=lambda request: holder[0].retain_semantic_clean_recovery_request(request),
        clean_recovery_activator=activate_or_crash,
        clean_recovery_reconciler=lambda released: holder[0].reconcile_semantic_clean_recovery(released),
    )
    plane, _, store, binding, fence, service, authorization_repository = _setup(
        verified=True,
        backend=backend,
        semantic_integrity_lifecycle=lifecycle,
    )
    holder.append(store)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, terminal)
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    first_event_member = next(member for member in store.generation_members(fence, 3) if member.kind == "event_batch")
    _, second_fence = handoff(
        plane,
        coordinate="two",
        atomic_store=store,
        writer_binding=binding,
    )
    second_terminal = accepted_terminal(operation_id=second_fence.operation_id)
    _activate(authorization_repository, second_fence, second_terminal)
    service.persist(
        fence=second_fence,
        terminal=second_terminal,
        authorization_verifier=AUTHORIZATION,
    )
    second_event_member = next(
        member for member in store.generation_members(second_fence, 3) if member.kind == "event_batch"
    )
    authority_batches = tuple(
        SemanticEventCleanAuthorityBatch(
            source_id=(f"semantic_ingestion:event-authority:batch:{batch.log_position.sequence:020d}"),
            canonical_batch_bytes=member.canonical_payload,
            source_digest=member.payload_digest,
        )
        for batch, member in sorted(
            (
                (
                    decode_semantic_memory_event_batch(
                        member.canonical_payload,
                        registry=store.event_schema_registry,
                    ),
                    member,
                )
                for member in (first_event_member, second_event_member)
            ),
            key=lambda item: item[0].log_position.sequence,
        )
    )
    active = sorted(
        plane.list_records(source_kind="semantic_ingestion_event_batch"),
        key=lambda record: record.memory_id,
    )[0]
    corrupted = active.model_copy(update={"content": active.content | {"canonical_hex": "00"}})
    _rewrite_jsonl_snapshot(backend, plane, replacements=(corrupted,))
    conflicting_digest = sha256(encode_typed_value(corrupted.content)).hexdigest()
    with pytest.raises(PreplanningStoreError, match="authority is corrupt"):
        store.semantic_event_batches()
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
    if recovery_mutation in {
        "empty",
        "prefix",
        "duplicate",
        "reordered",
        "substituted_full_set",
    }:
        if recovery_mutation == "empty":
            mutated_batches = ()
        elif recovery_mutation == "prefix":
            mutated_batches = authority_batches[:1]
        elif recovery_mutation == "duplicate":
            mutated_batches = (
                authority_batches[0],
                SemanticEventCleanAuthorityBatch(
                    source_id=authority_batches[1].source_id,
                    canonical_batch_bytes=(authority_batches[0].canonical_batch_bytes),
                    source_digest=authority_batches[0].source_digest,
                ),
            )
        elif recovery_mutation == "reordered":
            mutated_batches = tuple(reversed(authority_batches))
        else:
            mutated_batches = (
                SemanticEventCleanAuthorityBatch(
                    source_id=authority_batches[0].source_id,
                    canonical_batch_bytes=(authority_batches[1].canonical_batch_bytes),
                    source_digest=authority_batches[1].source_digest,
                ),
                SemanticEventCleanAuthorityBatch(
                    source_id=authority_batches[1].source_id,
                    canonical_batch_bytes=(authority_batches[0].canonical_batch_bytes),
                    source_digest=authority_batches[0].source_digest,
                ),
            )
        if recovery_mutation in {"empty", "duplicate", "reordered"}:
            mutated = SemanticEventCleanRecoveryRequest.model_construct(
                repository_id=request.repository_id,
                repaired_partition_ids=request.repaired_partition_ids,
                authority_batches=mutated_batches,
                retained_conflicting_byte_digests=(request.retained_conflicting_byte_digests),
                retained_corrupt_generation_digest=(request.retained_corrupt_generation_digest),
                request_digest=request.request_digest,
            )
        else:
            mutated = SemanticEventCleanRecoveryRequest.create(
                repository_id=request.repository_id,
                repaired_partition_ids=request.repaired_partition_ids,
                authority_batches=mutated_batches,
                retained_conflicting_byte_digests=(request.retained_conflicting_byte_digests),
                retained_corrupt_generation_digest=(request.retained_corrupt_generation_digest),
            )
        expected_error = (
            "clean_recovery_request_invalid"
            if recovery_mutation in {"empty", "duplicate", "reordered"}
            else "clean_replay_verification_failed"
        )
        with pytest.raises(
            ConflictIntegrityError,
            match=f"^{expected_error}$",
        ):
            lifecycle.recover_and_release(
                mutated,
                supplied_snapshot=snapshot,
                expected_control_digest=frozen.control_digest,
            )
        unchanged = lifecycle.current_control()
        assert unchanged == frozen
        assert not plane.list_records(source_kind="semantic_ingestion_clean_generation")
        assert not plane.list_records(source_kind="semantic_ingestion_clean_generation_status")
        return
    with pytest.raises(SystemExit, match="simulated crash after release"):
        lifecycle.recover_and_release(
            request,
            supplied_snapshot=snapshot,
            expected_control_digest=frozen.control_digest,
        )
    released = lifecycle.current_control()
    assert released is not None and released.frozen_partition_ids == ()
    assert (
        plane.list_records(source_kind="semantic_ingestion_clean_generation_status")[0].content["status"] == "prepared"
    )
    if recovery_mutation == "forged_activated_status":
        status_record = plane.list_records(
            source_kind="semantic_ingestion_clean_generation_status"
        )[0]
        substituted = status_record.model_copy(
            update={
                "content": status_record.content | {"status": "activated"}
            }
        )
        _rewrite_jsonl_snapshot(backend, plane, replacements=(substituted,))
    elif recovery_mutation != "none":
        source_kind = {
            "registry_history": ("semantic_ingestion_event_schema_registry_history"),
            "checkpoint_lifecycle": "semantic_ingestion_checkpoint_lifecycle",
        }[recovery_mutation]
        authority_record = plane.list_records(source_kind=source_kind)[0]
        digest_field = {
            "registry_history": "history_digest",
            "checkpoint_lifecycle": "authority_digest",
        }[recovery_mutation]
        substituted = authority_record.model_copy(
            update={
                "content": authority_record.content | {digest_field: sha256(recovery_mutation.encode()).hexdigest()}
            }
        )
        _rewrite_jsonl_snapshot(backend, plane, replacements=(substituted,))

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_holder: list[SemanticIngestionAtomicStore] = []
    reopened_repository = FileConflictIntegrityRepository(
        integrity_path,
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: reopened_holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: reopened_holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    reopened_lifecycle = PrivilegedSemanticIntegrityLifecycle(
        reopened_repository,
        clean_recovery_request_retainer=lambda retained_request: reopened_holder[
            0
        ].retain_semantic_clean_recovery_request(retained_request),
        clean_recovery_activator=lambda retained_request: reopened_holder[0].activate_semantic_clean_recovery(
            retained_request
        ),
        clean_recovery_reconciler=lambda is_released: reopened_holder[0].reconcile_semantic_clean_recovery(is_released),
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
        semantic_freeze_guard=reopened_lifecycle.freeze_guard,
        semantic_integrity_incident_reporter=(reopened_lifecycle.incident_reporter),
        semantic_integrity_linearization=reopened_lifecycle.linearization,
    )
    reopened_holder.append(reopened_store)
    if recovery_mutation == "none":
        reopened_lifecycle.reconcile_pending_recovery()
        assert len(reopened_store.semantic_event_batches()) == 2
        activated_authority = reopened_store.semantic_replay_authority()
        assert activated_authority.graph_state.graph_revision != "genesis"
        reopened_store.activate_semantic_clean_recovery(request)
        assert reopened_store.semantic_replay_authority() == activated_authority
        assert (
            reopened_plane.list_records(source_kind="semantic_ingestion_clean_generation_status")[0].content["status"]
            == "activated"
        )
    else:
        with pytest.raises(
            (PreplanningStoreError, ConflictIntegrityError),
            match="authority|substituted|recovery",
        ):
            reopened_lifecycle.reconcile_pending_recovery()
        refrozen = reopened_lifecycle.current_control()
        assert refrozen is not None
        assert refrozen.frozen_partition_ids == ("global",)
        exposed = None
        with pytest.raises(PreplanningStoreError, match="authority is corrupt"):
            exposed = reopened_store.semantic_event_batches()
        assert exposed is None
        assert (
            reopened_plane.list_records(source_kind="semantic_ingestion_clean_generation_status")[0].content["status"]
            == (
                "activated"
                if recovery_mutation == "forged_activated_status"
                else "prepared"
            )
        )


def test_accepted_clarification_atomically_binds_receipt_to_canonical_replay_effect(
    tmp_path,
) -> None:
    # The accepted completion is a canonical CAS transaction: build one real
    # OPEN conflict, submit, and claim the durable work.
    plane, store, _binding, _service, _repository, introduction, source = (
        _open_conflict_for_canonical_submission(tmp_path)
    )
    request, proposal = _canonical_submission_request(
        introduction, source, operation_id="user-resolution-operation"
    )
    submitted_generation = _clarification_submission_generation(
        introduction,
        _clarification_transition(
            introduction=introduction,
            predecessor_digest=introduction.introduction_digest,
            predecessor_revision=introduction.conflict_revision,
            predecessor_status=ConflictStatus.OPEN,
            status=ConflictStatus.CLARIFICATION_SUBMITTED,
            reason=SemanticConflictClarificationTransitionReason.SUBMITTED,
            record_coordinate=store.projection_history.semantic_conflict_replay_binding().immutable_record_count + 1,
            proposal_digest=proposal.proposal_digest,
        ),
        expected_conflict_revision=introduction.conflict_revision,
        operation_id="user-resolution-operation",
        source_user_event_id=source.memory_id,
        source_user_event_digest=source_admission_source_digest(source),
    )
    store.submit_conflict_clarification_generation(submitted_generation)
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token="atomic-bind-owner"
    )
    assert claim is not None
    clarification_cas = store.build_conflict_clarification_cas_input(claim)
    processing_operation_id = claim.work.processing_operation_id
    proposal = claim.proposal
    terminal = _with_claim_record_version(
        accepted_terminal(
            operation_id=processing_operation_id,
            source_id=proposal.source_user_event_id,
            source_digest=proposal.source_user_event_digest,
        ),
        record_version=2,
    )
    resulting_revision = sha256(b"resolved-conflict-revision").hexdigest()
    policy_fingerprint = claim.work.policy_fingerprint

    def commit():
        return store.commit_conflict_clarification_transaction(
            proposal=proposal,
            processing_operation_id=processing_operation_id,
            resulting_conflict_revision=resulting_revision,
            policy_fingerprint=policy_fingerprint,
            committed_outcome="accepted",
            semantic_result_digest=terminal.terminal_digest,
            semantic_terminal=terminal,
            clarification_cas=clarification_cas,
        )

    # The same CAS image presented again is the lost-ack retry, not a
    # concurrent race (one claim has one owner; the pointer race is covered
    # by its own test).  The retry returns the union binding: the retained
    # attempt result binds the same committed receipt digest.
    prior_materialized_count = len(
        store.semantic_replay_state().materialized_records
    )
    prior_aggregate_revision = store.semantic_replay_authority().aggregate_revision
    _bundle = accepted_terminal(operation_id=processing_operation_id).arbitration_policy_bundle
    assert _bundle is not None
    prior_temporal_sequence = store.projection_history.current_temporal(
        policy_fingerprint=_bundle.temporal_policy.fingerprint,
    ).pointer.publication_sequence
    prior_trust_sequence = store.projection_history.current_trust(
        policy_fingerprint=_bundle.trust_policy.fingerprint,
    ).pointer.publication_sequence
    receipt = commit()
    retried = commit()

    _assert_retry_returns_committed_receipt(retried, receipt)
    assert store.resolve_conflict_clarification_receipt(processing_operation_id) == receipt
    assert receipt.committed_outcome == "accepted"
    batches = store.semantic_event_batches()
    # The fixture's contest pair already advanced the graph; the accepted
    # clarification appends exactly one batch under its own transaction group.
    clarification_batches = tuple(
        batch for batch in batches if batch.transaction_group_id == processing_operation_id
    )
    assert len(clarification_batches) == 1
    assert (
        clarification_batches[0].graph_delta_digest
        == SemanticGraphDelta.create(terminal).delta_digest
    )
    replay_state = store.semantic_replay_state()
    assert (
        replay_state.graph_revision
        == clarification_batches[0].events[-1].payload.graph_revision_after
    )
    # The accepted answer supersedes the predecessor's version-1 carrier in
    # place (record version 2 over the same identity): the materialized
    # universe does not grow.
    assert len(replay_state.materialized_records) == prior_materialized_count
    assert any(
        record.record_version == 2 for record in replay_state.materialized_records
    )
    authority = store.semantic_replay_authority()
    assert authority.graph_state == replay_state
    assert authority.latest_checkpoint is not None
    assert authority.aggregate_revision == prior_aggregate_revision + 1
    assert authority.projection_history_bindings == (store.projection_history.replay_bindings())
    assert terminal.arbitration_policy_bundle is not None
    temporal = store.projection_history.current_temporal(
        policy_fingerprint=(terminal.arbitration_policy_bundle.temporal_policy.fingerprint),
    )
    trust = store.projection_history.current_trust(
        policy_fingerprint=(terminal.arbitration_policy_bundle.trust_policy.fingerprint),
    )
    assert temporal.pointer.publication_sequence == prior_temporal_sequence + 1
    assert trust.pointer.publication_sequence == prior_trust_sequence + 1
    replay_record_digests = {item.record_digest for item in replay_state.materialized_records}
    assert {
        evidence.candidate_digest for projection in temporal.projections for evidence in projection.evidence
    } == replay_record_digests
    assert {
        evidence.candidate_digest for projection in trust.projections for evidence in projection.evidence
    } == replay_record_digests
    assert len(clarification_batches) == 1
    recovery_authorities = plane.list_records(
        source_kind=("semantic_ingestion_conflict_clarification_recovery_authority")
    )
    assert any(
        processing_operation_id in record.memory_id for record in recovery_authorities
    )
    assert any(
        processing_operation_id in str(batch)
        for batch in _retained_authority_batches(plane, store)
    )

    event_id = "semantic_ingestion:event-authority:batch:00000000000000000001"
    backend = plane._records
    with backend._lock:
        del backend._records[event_id]
    with pytest.raises(
        PreplanningStoreError,
        match="clarification semantic transaction integrity failure",
    ):
        store.resolve_conflict_clarification_receipt(processing_operation_id)


def test_ordinary_and_clarification_batches_recover_exactly_after_filesystem_reopen(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = tmp_path / "memory-plane"
    backend = JsonlMemoryPlaneStore(storage)
    integrity_path = tmp_path / "integrity" / "ledger.jsonl"
    linearization = ReplayIntegrityLinearization(tmp_path / "integrity" / "linearization.lock")
    holder: list[SemanticIngestionAtomicStore] = []
    integrity_repository = FileConflictIntegrityRepository(
        integrity_path,
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    lifecycle = PrivilegedSemanticIntegrityLifecycle(
        integrity_repository,
        clean_recovery_request_retainer=lambda request: holder[0].retain_semantic_clean_recovery_request(request),
        clean_recovery_activator=lambda request: holder[0].activate_semantic_clean_recovery(request),
        clean_recovery_reconciler=lambda released: holder[0].reconcile_semantic_clean_recovery(released),
    )
    (
        plane,
        _,
        store,
        _,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=backend,
        with_test_conflict_authority=True,
        semantic_integrity_lifecycle=lifecycle,
    )
    holder.append(store)
    ordinary_terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, ordinary_terminal)
    service.persist(
        fence=fence,
        terminal=ordinary_terminal,
        authorization_verifier=AUTHORIZATION,
    )
    processing_operation_id = sha256(b"filesystem-clarification-processing").hexdigest()
    receipt, _, _ = _commit_accepted_clarification(
        store,
        processing_operation_id,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
    )
    authority_batches = _retained_authority_batches(plane, store)
    # One retained authority batch per graph-advancing write: the ordinary
    # terminal, the two contested claims, and the clarification commit.
    assert len(authority_batches) == 4

    active = plane.list_records(source_kind="semantic_ingestion_event_batch")[0]
    corrupted = active.model_copy(update={"content": active.content | {"canonical_hex": "00"}})
    _rewrite_jsonl_snapshot(backend, plane, replacements=(corrupted,))
    conflicting_digest = sha256(encode_typed_value(corrupted.content)).hexdigest()
    with pytest.raises(PreplanningStoreError, match="authority is corrupt"):
        store.semantic_event_batches()
    frozen = lifecycle.current_control()
    assert frozen is not None and frozen.frozen_partition_ids == ("global",)
    request = SemanticEventCleanRecoveryRequest.create(
        repository_id="semantic_ingestion",
        repaired_partition_ids=("global",),
        authority_batches=authority_batches,
        retained_conflicting_byte_digests=(conflicting_digest,),
        retained_corrupt_generation_digest=(store.semantic_integrity_generation_digest()),
    )
    snapshot = store.semantic_integrity_snapshot()
    with monkeypatch.context() as recovery_guard:
        recovery_guard.setattr(
            store,
            "enrich_identity_graph_delta",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("clean recovery called live graph enrichment")
            ),
        )
        recovery_guard.setattr(
            store,
            "semantic_replay_authority",
            lambda: (_ for _ in ()).throw(
                AssertionError("clean recovery called active replay authority")
            ),
        )
        repair, released = lifecycle.recover_and_release(
            request,
            supplied_snapshot=snapshot,
            expected_control_digest=frozen.control_digest,
        )
    assert repair.authority_source_digests == request.authority_source_digests
    assert released.frozen_partition_ids == ()
    assert len(store.semantic_event_batches()) == 4
    assert store.resolve_conflict_clarification_receipt(receipt.processing_operation_id) == receipt

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_holder: list[SemanticIngestionAtomicStore] = []
    reopened_repository = FileConflictIntegrityRepository(
        integrity_path,
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: reopened_holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: reopened_holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    reopened_lifecycle = PrivilegedSemanticIntegrityLifecycle(
        reopened_repository,
        clean_recovery_request_retainer=lambda retained: reopened_holder[0].retain_semantic_clean_recovery_request(
            retained
        ),
        clean_recovery_activator=lambda retained: reopened_holder[0].activate_semantic_clean_recovery(retained),
        clean_recovery_reconciler=lambda is_released: reopened_holder[0].reconcile_semantic_clean_recovery(is_released),
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
        semantic_freeze_guard=reopened_lifecycle.freeze_guard,
        semantic_integrity_incident_reporter=(reopened_lifecycle.incident_reporter),
        semantic_integrity_linearization=reopened_lifecycle.linearization,
    )
    reopened_holder.append(reopened_store)
    assert len(reopened_store.semantic_event_batches()) == 4
    assert (
        reopened_store.semantic_replay_authority().graph_state.graph_revision
        == store.semantic_replay_authority().graph_state.graph_revision
    )
    assert reopened_store.projection_history.replay_bindings() == (store.projection_history.replay_bindings())
    assert tuple(
        binding.active_pointer_digest
        for binding in reopened_store.semantic_replay_authority().projection_history_bindings
    ) == tuple(
        binding.active_pointer_digest for binding in store.semantic_replay_authority().projection_history_bindings
    )
    assert reopened_store.resolve_conflict_clarification_receipt(receipt.processing_operation_id) == receipt


def test_projection_and_claimed_clarification_races_have_one_pointer_winner(
    tmp_path,
) -> None:
    backend = JsonlMemoryPlaneStore(tmp_path / "memory-plane")
    integrity_path = tmp_path / "integrity" / "ledger.jsonl"
    linearization = ReplayIntegrityLinearization(tmp_path / "integrity" / "linearization.lock")
    holder: list[SemanticIngestionAtomicStore] = []
    integrity_repository = FileConflictIntegrityRepository(
        integrity_path,
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    lifecycle = PrivilegedSemanticIntegrityLifecycle(
        integrity_repository,
        clean_recovery_request_retainer=lambda request: holder[0].retain_semantic_clean_recovery_request(request),
        clean_recovery_activator=lambda request: holder[0].activate_semantic_clean_recovery(request),
        clean_recovery_reconciler=lambda released: holder[0].reconcile_semantic_clean_recovery(released),
    )
    (
        _,
        introduction,
        _,
        _,
        _,
        _,
        plane,
        store,
        _,
        _,
    ) = _persist_reconstructible_clarification_history(
        tmp_path,
        backend=backend,
        complete=False,
        return_runtime=True,
        semantic_integrity_lifecycle=lifecycle,
    )
    holder.append(store)
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5),
        owner_token="clean-recovery-race-owner",
    )
    assert claim is not None and claim.work.conflict_id == introduction.conflict_id
    clarification_cas = store.build_conflict_clarification_cas_input(claim)
    processing_operation_id = claim.work.processing_operation_id
    terminal = _with_claim_record_version(
        accepted_terminal(
            operation_id=processing_operation_id,
            source_id=claim.proposal.source_user_event_id,
            source_digest=claim.proposal.source_user_event_digest,
            object_logical_entity_id="entity:clean-recovery-clarified",
            object_entity_revision_id="entity-revision:clean-recovery-clarified:v1",
        ),
        record_version=2,
    )
    resulting_revision = sha256(b"clean-recovery-race-successor").hexdigest()
    authority_batches = _retained_authority_batches(plane, store)
    active = plane.list_records(source_kind="semantic_ingestion_event_batch")[0]
    corrupted = active.model_copy(update={"content": active.content | {"canonical_hex": "00"}})
    _rewrite_jsonl_snapshot(backend, plane, replacements=(corrupted,))
    conflicting_digest = sha256(encode_typed_value(corrupted.content)).hexdigest()
    with pytest.raises(PreplanningStoreError, match="authority is corrupt"):
        store.semantic_event_batches()
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

    def commit():
        barrier.wait(timeout=5)
        try:
            return store.commit_conflict_clarification_transaction(
                proposal=claim.proposal,
                processing_operation_id=processing_operation_id,
                resulting_conflict_revision=resulting_revision,
                policy_fingerprint=claim.work.policy_fingerprint,
                committed_outcome="accepted",
                semantic_result_digest=terminal.terminal_digest,
                semantic_terminal=terminal,
                clarification_cas=clarification_cas,
            )
        except (PreplanningStoreError, SemanticEventReplayError):
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        release_future = executor.submit(release)
        commit_future = executor.submit(commit)
        _, released = release_future.result(timeout=180)
        raced_receipt = commit_future.result(timeout=180)

    assert released.frozen_partition_ids == ()
    assert lifecycle.current_control() == released
    if raced_receipt is None:
        assert len(store.semantic_event_batches()) == 2
        raced_receipt = store.commit_conflict_clarification_transaction(
            proposal=claim.proposal,
            processing_operation_id=processing_operation_id,
            resulting_conflict_revision=resulting_revision,
            policy_fingerprint=claim.work.policy_fingerprint,
            committed_outcome="accepted",
            semantic_result_digest=terminal.terminal_digest,
            semantic_terminal=terminal,
            clarification_cas=clarification_cas,
        )
    assert len(store.semantic_event_batches()) == 3
    assert store.resolve_conflict_clarification_receipt(processing_operation_id) == raced_receipt
    retried = store.commit_conflict_clarification_transaction(
        proposal=claim.proposal,
        processing_operation_id=processing_operation_id,
        resulting_conflict_revision=resulting_revision,
        policy_fingerprint=claim.work.policy_fingerprint,
        committed_outcome="accepted",
        semantic_result_digest=terminal.terminal_digest,
        semantic_terminal=terminal,
        clarification_cas=clarification_cas,
    )
    # The retry raced a projection winner: the union return binds the same
    # committed receipt through the retained attempt result's digest.
    _assert_retry_returns_committed_receipt(retried, raced_receipt)
    assert len(plane.list_records(source_kind=("semantic_ingestion_conflict_clarification_recovery_authority"))) == 1


@pytest.mark.parametrize("winner", ("projection", "clarification"))
def test_prepared_projection_and_claimed_clarification_completion_have_one_cas_winner(
    tmp_path,
    winner: Literal["projection", "clarification"],
) -> None:
    """A stale prepared projection or clarification completion appends nothing.

    This intentionally builds the projection request from the real next
    admitted terminal and replay state.  A hand-written authority closure
    would miss the pointer/work CAS members that make this race meaningful.
    """
    (
        _,
        introduction,
        _,
        _,
        _,
        _,
        plane,
        store,
        service,
        authorization_repository,
    ) = _persist_reconstructible_clarification_history(
        tmp_path / winner,
        backend=InMemoryMemoryPlaneStore(),
        complete=False,
        return_runtime=True,
    )
    binding = store._writers.commit_binding(store._writers.current())
    claim = store.claim_next_conflict_clarification(
        lease_duration=timedelta(minutes=5), owner_token=f"race-owner-{winner}"
    )
    assert claim is not None
    clarification_cas = store.build_conflict_clarification_cas_input(claim)

    # Produce the natural successor through the ordinary admitted terminal
    # path, keeping its scope equal to the submitted clarification scope.
    _, projection_fence = handoff(
        plane,
        coordinate=f"natural-projection-{winner}",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=binding,
    )
    projection_terminal = accepted_terminal(
        operation_id=projection_fence.operation_id,
        object_logical_entity_id="entity:initech",
        object_entity_revision_id="entity-revision:initech:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(authorization_repository, projection_fence, projection_terminal)
    request = _direct_committed_request(
        store=store,
        binding=binding,
        fence=projection_fence,
        terminal=projection_terminal,
        authorization_repository=authorization_repository,
    )
    batch_member = next(member for member in request.members if member.kind == "event_batch")
    batch = decode_semantic_memory_event_batch(
        batch_member.canonical_payload, registry=store.event_schema_registry
    )
    prior_state = store.semantic_replay_state()
    next_state = replay_semantic_event_batches(
        repository_id="semantic_ingestion",
        batches=(batch,),
        registry_history=store._event_schema_registry_history,
        initial_state=prior_state,
    )
    bindings = store.projection_history.replay_bindings()
    (
        temporal_projections,
        trust_projections,
        temporal_policy_fingerprint,
        trust_policy_fingerprint,
        arbitration_as_of,
    ) = projection_records_from_replay_state(
        next_state,
        active_temporal=(store.projection_history.active_temporal_authority() if bindings else None),
        active_trust=(store.projection_history.active_trust_authority() if bindings else None),
        active_temporal_policy=(
            projection_terminal.arbitration_policy_bundle.temporal_policy if bindings else None
        ),
        active_trust_policy=(
            projection_terminal.arbitration_policy_bundle.trust_policy if bindings else None
        ),
    )
    authority = store.projection_history.resolve_semantic_conflict_authority(
        temporal_projections=temporal_projections,
        trust_projections=trust_projections,
    )
    projection = store.projection_history.prepare(
        ProjectionCommitRequest(
            repository_id="semantic_ingestion",
            operation_id=batch.transaction_group_id,
            graph_revision=next_state.graph_revision,
            event_batch_sequence=batch.log_position.sequence,
            event_batch_digest=batch.source_event_batch_digest,
            complete_read_set_digest=request.expected_effective_read_set_digest,
            writer_epoch=binding.expected_writer_epoch,
            base_snapshot_token=prior_state.state_digest,
            temporal_policy_fingerprint=temporal_policy_fingerprint,
            trust_policy_fingerprint=trust_policy_fingerprint,
            arbitration_as_of=arbitration_as_of,
            temporal_projections=temporal_projections,
            trust_projections=trust_projections,
            semantic_conflict_authority=authority,
        ),
        capability=store._write_capability,
        authorization=store._writers._authorize_atomic(
            binding, capability=store._write_capability
        ),
    )
    assert any(
        record.memory_id == f"semantic_ingestion:conflict-authority:pointer:{introduction.conflict_id}"
        for record in projection.records
    )

    clarification_terminal = _with_claim_record_version(
        accepted_terminal(
            operation_id=claim.work.processing_operation_id,
            source_id=claim.proposal.source_user_event_id,
            source_digest=claim.proposal.source_user_event_digest,
            object_logical_entity_id="entity:clarified",
            object_entity_revision_id="entity-revision:clarified:v1",
        ),
        record_version=2,
    )
    successor_revision = sha256(f"clarification-successor:{winner}".encode()).hexdigest()
    start = Barrier(2)
    projection_published = Event()
    clarification_committed = Event()

    def publish_projection() -> None:
        start.wait(timeout=30)
        if winner == "clarification":
            assert clarification_committed.wait(timeout=300)
            plane.conditionally_write_records(
                projection.records,
                preconditions=projection.preconditions,
                authorization=store._writers._authorize_atomic(
                    binding, capability=store._write_capability
                ),
            )
            return
        # The prepared closure above proves the exact pointer CAS image.
        # Publish through the normal group owner so a winning projection also
        # carries its event/replay/checkpoint closure in the same write.
        store.persist_terminal_group(request)
        if winner == "projection":
            projection_published.set()

    def complete_clarification():
        start.wait(timeout=30)
        if winner == "projection":
            assert projection_published.wait(timeout=300)
        receipt = store.commit_conflict_clarification_transaction(
            proposal=claim.proposal,
            processing_operation_id=claim.work.processing_operation_id,
            resulting_conflict_revision=successor_revision,
            policy_fingerprint=claim.work.policy_fingerprint,
            committed_outcome="accepted",
            semantic_result_digest=clarification_terminal.terminal_digest,
            semantic_terminal=clarification_terminal,
            clarification_cas=clarification_cas,
        )
        if winner == "clarification":
            clarification_committed.set()
        return receipt

    with ThreadPoolExecutor(max_workers=2) as executor:
        projection_future = executor.submit(publish_projection)
        clarification_future = executor.submit(complete_clarification)
        if winner == "clarification":
            receipt = clarification_future.result(timeout=300)
            with pytest.raises(MemoryPlaneRevisionConflictError):
                projection_future.result(timeout=300)
        else:
            projection_future.result(timeout=300)
            receipt = clarification_future.result(timeout=300)

    current = store.canonical_conflict_attention(introduction.conflict_id)
    assert current is not None
    if winner == "projection":
        assert current.conflict_revision != successor_revision
        assert store.resolve_conflict_clarification_receipt(claim.work.processing_operation_id) is None
        assert not plane.list_records(source_kind="semantic_ingestion_conflict_clarification_transaction")
        assert len(store.semantic_event_batches()) == 3
        terminal_work = next(
            decode_persisted_conflict_generation(
                decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
                ConflictClarificationWork,
            )
            for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
            if record.memory_id.startswith(
                "semantic_ingestion:conflict-authority:clarification-work-member:"
            )
            and decode_persisted_conflict_generation(
                decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
                ConflictClarificationWork,
            ).processing_operation_id == claim.work.processing_operation_id
            and decode_persisted_conflict_generation(
                decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
                ConflictClarificationWork,
            ).work_revision > claim.work.work_revision
        )
        assert terminal_work.owner_token is None
        assert terminal_work.attempt_count == claim.work.attempt_count
        superseded = next(
            decode_persisted_conflict_generation(
                decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
                ConflictClarificationAttemptResult,
            )
            for record in plane.list_records(source_kind="semantic_ingestion_conflict_authority")
            if record.memory_id.startswith(
                "semantic_ingestion:conflict-authority:clarification-attempt-result-member:"
            )
            and decode_persisted_conflict_generation(
                decode_typed_value(bytes.fromhex(str(record.content["canonical_hex"]))),
                ConflictClarificationAttemptResult,
            ).processing_operation_id == claim.work.processing_operation_id
        )
        assert superseded.outcome is ClarificationAttemptOutcome.SUPERSEDED
        assert superseded.superseded_by_conflict_revision == current.conflict_revision
        assert superseded.downstream_receipt_digest is None
        # The stale worker replays the retained terminal audit result.  It
        # does not adopt the already-prepared semantic outcome or append a
        # second closure.
        assert receipt == superseded
        before_retry = tuple(plane.list_records())
        assert store.commit_conflict_clarification_transaction(
            proposal=claim.proposal,
            processing_operation_id=claim.work.processing_operation_id,
            resulting_conflict_revision=successor_revision,
            policy_fingerprint=claim.work.policy_fingerprint,
            committed_outcome="accepted",
            semantic_result_digest=clarification_terminal.terminal_digest,
            semantic_terminal=clarification_terminal,
            clarification_cas=clarification_cas,
        ) == superseded
        assert tuple(plane.list_records()) == before_retry
    else:
        assert receipt is not None
        assert receipt.committed_outcome == "accepted"
        assert current.conflict_revision == successor_revision
        # The losing prepared request and its old graph fence are rejected
        # without a detached write.  Replanning starts from a fresh handoff
        # against the clarification winner's graph revision.
        before_stale_retry = tuple(plane.list_records())
        with pytest.raises(SemanticEventReplayError):
            service.persist(
                fence=projection_fence,
                terminal=projection_terminal,
                authorization_verifier=AUTHORIZATION,
            )
        assert tuple(plane.list_records()) == before_stale_retry
        _, replanned_fence = handoff(
            plane,
            coordinate="natural-projection-replanned",
            scope_ids=frozenset({"scope:a"}),
            atomic_store=store,
            writer_binding=store._writers.commit_binding(store._writers.current()),
        )
        replanned_terminal = accepted_terminal(
            operation_id=replanned_fence.operation_id,
            object_logical_entity_id="entity:initech",
            object_entity_revision_id="entity-revision:initech:v1",
            valid_start=NOW,
            valid_end=NOW + timedelta(days=2),
        )
        _activate(authorization_repository, replanned_fence, replanned_terminal)
        service.persist(
            fence=replanned_fence,
            terminal=replanned_terminal,
            authorization_verifier=AUTHORIZATION,
        )
        assert store.get_operation(replanned_fence).state == "terminal"


@pytest.mark.parametrize(
    "mutation",
    (
        "provenance",
        "transaction",
        "receipt",
        "event_payload",
        "generation_order",
    ),
)
def test_clarification_recovery_authority_rejects_bound_record_mutations(
    tmp_path,
    mutation: str,
) -> None:
    backend = JsonlMemoryPlaneStore(tmp_path / "memory-plane")
    plane, _, store, _, _, service, authorization_repository = _setup(
        verified=True,
        backend=backend,
        with_test_conflict_authority=True,
    )
    processing_operation_id = sha256(b"clarification-authority-mutation").hexdigest()
    _commit_accepted_clarification(
        store,
        processing_operation_id,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
    )
    authority = plane.list_records(source_kind=("semantic_ingestion_conflict_clarification_recovery_authority"))[0]
    if mutation in {"provenance", "event_payload", "generation_order"}:
        content = dict(authority.content)
        if mutation == "event_payload":
            content["event_batch_canonical_hex"] = "00"
        else:
            binding = dict(content["binding"])
            if mutation == "provenance":
                binding["binding_digest"] = "0" * 64
            else:
                binding["generation"] += 1
                binding_body = {key: value for key, value in binding.items() if key != "binding_digest"}
                binding["binding_digest"] = sha256(
                    b"memorii.semantic-ingestion.clarification-recovery-binding.v1\0" + encode_typed_value(binding_body)
                ).hexdigest()
            content["binding"] = binding
        target = authority
    elif mutation == "transaction":
        target = plane.list_records(source_kind=("semantic_ingestion_conflict_clarification_transaction"))[0]
        transaction = dict(target.content["transaction"])
        transaction["conflict_id"] = "substituted-conflict"
        content = target.content | {"transaction": transaction}
    else:
        target = plane.list_records(source_kind="semantic_ingestion_conflict_clarification_receipt")[0]
        receipt = dict(target.content["receipt"])
        receipt["conflict_id"] = "substituted-conflict"
        content = target.content | {"receipt": receipt}
    substituted = target.model_copy(update={"content": content})
    _rewrite_jsonl_snapshot(backend, plane, replacements=(substituted,))
    with pytest.raises(
        ConflictIntegrityError,
        match="^clean_recovery_authority_invalid$",
    ):
        store.prepare_semantic_clean_recovery(
            ("global",),
            (sha256(mutation.encode()).hexdigest(),),
            (sha256(b"untrusted-authority").hexdigest(),),
        )


def test_clarification_recovery_rejects_cross_bound_transaction_delta_and_batch(
    tmp_path,
) -> None:
    backend = JsonlMemoryPlaneStore(tmp_path / "memory-plane")
    plane, _, store, _, _, service, authorization_repository = _setup(
        verified=True,
        backend=backend,
        with_test_conflict_authority=True,
    )
    processing_operation_id = sha256(b"clarification-delta-cross-bind").hexdigest()
    _commit_accepted_clarification(
        store,
        processing_operation_id,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
    )
    transaction = plane.list_records(
        source_kind="semantic_ingestion_conflict_clarification_transaction"
    )[0]
    receipt_record = plane.list_records(
        source_kind="semantic_ingestion_conflict_clarification_receipt"
    )[0]
    authority = plane.list_records(
        source_kind="semantic_ingestion_conflict_clarification_recovery_authority"
    )[0]

    alternate_delta = SemanticGraphDelta.create(
        accepted_terminal(
            operation_id=processing_operation_id,
            object_logical_entity_id="entity:substituted",
            object_entity_revision_id="entity-revision:substituted:v1",
        )
    )
    transaction_body = dict(transaction.content["transaction"])
    transaction_body["graph_delta_hex"] = encode_semantic_contract(
        alternate_delta
    ).hex()
    transaction_body["graph_delta_digest"] = alternate_delta.delta_digest
    transaction_digest = sha256(encode_typed_value(transaction_body)).hexdigest()
    substituted_transaction = transaction.model_copy(
        update={
            "content": transaction.content
            | {
                "semantic_transaction_digest": transaction_digest,
                "transaction": transaction_body,
            }
        }
    )
    prior_receipt = dict(receipt_record.content["receipt"])
    substituted_receipt_value = ConflictClarificationProcessingReceipt.create(
        processing_operation_id=prior_receipt["processing_operation_id"],
        conflict_id=prior_receipt["conflict_id"],
        conflict_revision=prior_receipt["conflict_revision"],
        proposal_digest=prior_receipt["proposal_digest"],
        policy_fingerprint=prior_receipt["policy_fingerprint"],
        semantic_transaction_id=prior_receipt["semantic_transaction_id"],
        semantic_transaction_digest=transaction_digest,
        semantic_result_digest=prior_receipt["semantic_result_digest"],
        committed_outcome=prior_receipt["committed_outcome"],
        committed_at=NOW,
    )
    substituted_receipt = receipt_record.model_copy(
        update={
            "content": receipt_record.content
            | {"receipt": substituted_receipt_value.model_dump(mode="json")}
        }
    )
    authority_content = dict(authority.content)
    authority_binding = dict(authority_content["binding"])
    authority_binding["transaction_record_digest"] = record_digest(
        substituted_transaction
    )
    authority_binding["receipt_record_digest"] = record_digest(substituted_receipt)
    binding_body = {
        key: value
        for key, value in authority_binding.items()
        if key != "binding_digest"
    }
    authority_binding["binding_digest"] = sha256(
        b"memorii.semantic-ingestion.clarification-recovery-binding.v1\0"
        + encode_typed_value(binding_body)
    ).hexdigest()
    authority_content["binding"] = authority_binding
    substituted_authority = authority.model_copy(update={"content": authority_content})
    _rewrite_jsonl_snapshot(
        backend,
        plane,
        replacements=(
            substituted_transaction,
            substituted_receipt,
            substituted_authority,
        ),
    )

    with pytest.raises(
        ConflictIntegrityError,
        match="^clean_recovery_authority_invalid$",
    ):
        store.prepare_semantic_clean_recovery(
            ("global",),
            (sha256(b"delta-cross-bind").hexdigest(),),
            (sha256(b"untrusted-authority").hexdigest(),),
        )


@pytest.mark.parametrize(
    "mutation",
    ("omitted_binding", "swapped_bindings", "checkpoint_revision"),
)
def test_clarification_recovery_rejects_rehashed_retained_authority_mutations(
    tmp_path,
    mutation: str,
) -> None:
    backend = JsonlMemoryPlaneStore(tmp_path / "memory-plane")
    plane, _, store, binding, fence, service, authorization_repository = _setup(
        verified=True,
        backend=backend,
        with_test_conflict_authority=True,
    )
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, terminal)
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    _, second_fence = handoff(
        plane,
        coordinate="retained-authority-two",
        atomic_store=store,
        writer_binding=binding,
    )
    second_terminal = accepted_terminal(operation_id=second_fence.operation_id)
    _activate(authorization_repository, second_fence, second_terminal)
    service.persist(
        fence=second_fence,
        terminal=second_terminal,
        authorization_verifier=AUTHORIZATION,
    )
    processing_operation_id = sha256(
        b"clarification-retained-authority-mutation"
    ).hexdigest()
    _commit_accepted_clarification(
        store,
        processing_operation_id,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
    )
    authority = plane.list_records(
        source_kind="semantic_ingestion_conflict_clarification_recovery_authority"
    )[0]
    aggregate = event_replay.decode_semantic_replay_authority(
        bytes.fromhex(authority.content["replay_aggregate_canonical_hex"])
    )
    aggregate_body = aggregate.model_dump(
        mode="python",
        exclude={"aggregate_digest"},
    )
    if mutation == "omitted_binding":
        assert aggregate.observation_bindings
        aggregate_body["observation_bindings"] = aggregate.observation_bindings[1:]
    elif mutation == "swapped_bindings":
        assert len(aggregate.observation_bindings) >= 2
        first, second, *remaining = aggregate.observation_bindings
        aggregate_body["observation_bindings"] = (
            event_replay.SemanticReplayAuthorityMemberBinding.create(
                operation_fence_id=first.operation_fence_id,
                generation=first.generation,
                member_id=first.member_id,
                member_kind=first.member_kind,
                payload_digest=second.payload_digest,
            ),
            event_replay.SemanticReplayAuthorityMemberBinding.create(
                operation_fence_id=second.operation_fence_id,
                generation=second.generation,
                member_id=second.member_id,
                member_kind=second.member_kind,
                payload_digest=first.payload_digest,
            ),
            *remaining,
        )
    else:
        bundle = aggregate.latest_checkpoint
        assert bundle is not None
        checkpoint = bundle.checkpoint
        checkpoint_body = checkpoint.model_dump(
            mode="python",
            exclude={"checkpoint_digest", "signature"},
        )
        checkpoint_body["graph_revision"] = "substituted-graph-revision"
        substituted_checkpoint = type(checkpoint)(
            **checkpoint_body,
            checkpoint_digest=event_replay._digest(
                event_replay._CHECKPOINT_POSITION_DOMAIN,
                checkpoint_body,
            ),
            signature=checkpoint.signature,
        )
        bundle_body = {
            "checkpoint": substituted_checkpoint,
            "materialized_snapshot": bundle.materialized_snapshot,
            "watermark_batch": bundle.watermark_batch,
        }
        aggregate_body["latest_checkpoint"] = type(bundle)(
            **bundle_body,
            bundle_digest=event_replay._digest(
                event_replay._CHECKPOINT_BUNDLE_DOMAIN,
                bundle_body,
            ),
        )
    substituted_aggregate = type(aggregate)(
        **aggregate_body,
        aggregate_digest=event_replay._digest(
            (
                event_replay._REPLAY_AUTHORITY_AGGREGATE_DOMAIN
                if aggregate.aggregate_schema_version
                == "memorii.semantic-replay-authority-aggregate.v1"
                else event_replay._REPLAY_AUTHORITY_AGGREGATE_V2_DOMAIN
            ),
            aggregate_body,
        ),
    )
    replay_payload = event_replay.encode_semantic_replay_authority(
        substituted_aggregate
    )
    authority_content = dict(authority.content)
    authority_binding = dict(authority_content["binding"])
    authority_binding["replay_aggregate_payload_digest"] = sha256(
        replay_payload
    ).hexdigest()
    authority_binding["replay_aggregate_digest"] = (
        substituted_aggregate.aggregate_digest
    )
    binding_body = {
        key: value
        for key, value in authority_binding.items()
        if key != "binding_digest"
    }
    authority_binding["binding_digest"] = sha256(
        b"memorii.semantic-ingestion.clarification-recovery-binding.v1\0"
        + encode_typed_value(binding_body)
    ).hexdigest()
    authority_content["binding"] = authority_binding
    authority_content["replay_aggregate_canonical_hex"] = replay_payload.hex()
    substituted_authority = authority.model_copy(update={"content": authority_content})
    _rewrite_jsonl_snapshot(
        backend,
        plane,
        replacements=(substituted_authority,),
    )

    with pytest.raises(
        ConflictIntegrityError,
        match="^clean_recovery_authority_invalid$",
    ):
        store.prepare_semantic_clean_recovery(
            ("global",),
            (sha256(mutation.encode()).hexdigest(),),
            (sha256(b"untrusted-authority").hexdigest(),),
        )


@pytest.mark.parametrize(
    "closure_mutation",
    (
        "missing_authority",
        "missing_transaction",
        "missing_receipt",
        "extra_authority",
        "duplicate_transaction",
        "duplicate_receipt",
        "duplicate_event",
        "cross_transaction",
        "cross_receipt",
        "cross_event",
        "sequence_substitution",
        "generation_substitution",
    ),
)
def test_filesystem_reopen_rejects_nonbijective_clarification_recovery_closure(
    tmp_path,
    closure_mutation: str,
) -> None:
    root = tmp_path / f"clarification-closure-{closure_mutation}"
    storage = root / "memory-plane"
    backend = JsonlMemoryPlaneStore(storage)
    integrity_path = root / "integrity" / "ledger.jsonl"
    linearization = ReplayIntegrityLinearization(root / "integrity" / "linearization.lock")
    holder: list[SemanticIngestionAtomicStore] = []
    repository = FileConflictIntegrityRepository(
        integrity_path,
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    lifecycle = PrivilegedSemanticIntegrityLifecycle(
        repository,
        clean_recovery_request_retainer=lambda request: holder[0].retain_semantic_clean_recovery_request(request),
        clean_recovery_activator=lambda request: holder[0].activate_semantic_clean_recovery(request),
        clean_recovery_reconciler=lambda released: holder[0].reconcile_semantic_clean_recovery(released),
    )
    (
        plane,
        _,
        store,
        _,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=backend,
        with_test_conflict_authority=True,
        semantic_integrity_lifecycle=lifecycle,
    )
    holder.append(store)
    ordinary_terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, ordinary_terminal)
    service.persist(
        fence=fence,
        terminal=ordinary_terminal,
        authorization_verifier=AUTHORIZATION,
    )
    processing_operation_id = sha256(b"filesystem-clarification-closure").hexdigest()
    _commit_accepted_clarification(
        store,
        processing_operation_id,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
    )
    authority_batches = _retained_authority_batches(plane, store)
    # One retained authority batch per graph-advancing write: the ordinary
    # terminal, the two contested claims, and the clarification commit.
    assert len(authority_batches) == 4
    active_records = sorted(
        plane.list_records(source_kind="semantic_ingestion_event_batch"),
        key=lambda record: record.memory_id,
    )
    ordinary_event, *_, clarification_event = active_records
    valid_clarification_content = clarification_event.content
    corrupted_ordinary = ordinary_event.model_copy(update={"content": ordinary_event.content | {"canonical_hex": "00"}})
    _rewrite_jsonl_snapshot(
        backend,
        plane,
        replacements=(corrupted_ordinary,),
    )
    conflicting_digest = sha256(encode_typed_value(corrupted_ordinary.content)).hexdigest()
    with pytest.raises(PreplanningStoreError, match="authority is corrupt"):
        store.semantic_event_batches()
    frozen = lifecycle.current_control()
    assert frozen is not None and frozen.frozen_partition_ids == ("global",)
    request = SemanticEventCleanRecoveryRequest.create(
        repository_id="semantic_ingestion",
        repaired_partition_ids=("global",),
        authority_batches=authority_batches,
        retained_conflicting_byte_digests=(conflicting_digest,),
        retained_corrupt_generation_digest=(store.semantic_integrity_generation_digest()),
    )
    current = {record.memory_id: record for record in plane.list_records()}
    transaction = next(
        record
        for record in current.values()
        if record.source_kind == "semantic_ingestion_conflict_clarification_transaction"
    )
    receipt = next(
        record
        for record in current.values()
        if record.source_kind == "semantic_ingestion_conflict_clarification_receipt"
    )
    authority = next(
        record
        for record in current.values()
        if record.source_kind == "semantic_ingestion_conflict_clarification_recovery_authority"
    )

    delete_id = None
    replacement = None
    extra = None
    if closure_mutation == "missing_authority":
        delete_id = authority.memory_id
    elif closure_mutation == "missing_transaction":
        delete_id = transaction.memory_id
    elif closure_mutation == "missing_receipt":
        delete_id = receipt.memory_id
    elif closure_mutation == "extra_authority":
        extra = authority.model_copy(update={"memory_id": f"{authority.memory_id}:extra"})
    elif closure_mutation == "duplicate_transaction":
        extra = transaction.model_copy(update={"memory_id": f"{transaction.memory_id}:duplicate"})
    elif closure_mutation == "duplicate_receipt":
        extra = receipt.model_copy(update={"memory_id": f"{receipt.memory_id}:duplicate"})
    elif closure_mutation == "duplicate_event":
        extra = clarification_event.model_copy(update={"memory_id": f"{clarification_event.memory_id}:duplicate"})
    else:
        authority_content = dict(authority.content)
        binding = dict(authority_content["binding"])
        if closure_mutation == "cross_transaction":
            binding["transaction_record_id"] = receipt.memory_id
        elif closure_mutation == "cross_receipt":
            binding["receipt_record_id"] = transaction.memory_id
        elif closure_mutation == "cross_event":
            binding["event_batch_record_id"] = ordinary_event.memory_id
        elif closure_mutation == "sequence_substitution":
            binding["event_batch_sequence"] += 1
            binding["generation"] += 1
            binding["event_batch_record_id"] = (
                f"semantic_ingestion:event-authority:batch:{binding['event_batch_sequence']:020d}"
            )
        else:
            binding["generation"] += 1
        binding_body = {key: value for key, value in binding.items() if key != "binding_digest"}
        binding["binding_digest"] = sha256(
            b"memorii.semantic-ingestion.clarification-recovery-binding.v1\0" + encode_typed_value(binding_body)
        ).hexdigest()
        authority_content["binding"] = binding
        replacement = authority.model_copy(update={"content": authority_content})

    backend = plane._records
    assert isinstance(backend, JsonlMemoryPlaneStore)
    rewritten = []
    changed = False
    for batch in backend._read_batches_unlocked():
        records = []
        for record in batch.records:
            if record.memory_id == delete_id:
                changed = True
                continue
            if replacement is not None and record.memory_id == replacement.memory_id:
                records.append(replacement)
                changed = True
            else:
                records.append(record)
        rewritten.append(
            _PersistedBatch.create(
                revision=batch.revision,
                data_revision=batch.data_revision,
                records=tuple(records),
            )
        )
    if extra is not None:
        last = rewritten[-1]
        rewritten[-1] = _PersistedBatch.create(
            revision=last.revision,
            data_revision=last.data_revision,
            records=(*last.records, extra),
        )
        changed = True
    assert changed
    backend._replace_batches(rewritten)

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_holder: list[SemanticIngestionAtomicStore] = []
    reopened_repository = FileConflictIntegrityRepository(
        integrity_path,
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: reopened_holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: reopened_holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    reopened_lifecycle = PrivilegedSemanticIntegrityLifecycle(
        reopened_repository,
        clean_recovery_request_retainer=lambda retained: reopened_holder[0].retain_semantic_clean_recovery_request(
            retained
        ),
        clean_recovery_activator=lambda retained: reopened_holder[0].activate_semantic_clean_recovery(retained),
        clean_recovery_reconciler=lambda released: reopened_holder[0].reconcile_semantic_clean_recovery(released),
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
        semantic_freeze_guard=reopened_lifecycle.freeze_guard,
        semantic_integrity_incident_reporter=(reopened_lifecycle.incident_reporter),
        semantic_integrity_linearization=reopened_lifecycle.linearization,
    )
    reopened_holder.append(reopened_store)
    reopened_frozen = reopened_lifecycle.current_control()
    assert reopened_frozen == frozen
    with pytest.raises(
        ConflictIntegrityError,
        match="clean_replay_verification_failed",
    ):
        reopened_lifecycle.recover_and_release(
            request,
            supplied_snapshot=reopened_store.semantic_integrity_snapshot(),
            expected_control_digest=frozen.control_digest,
        )
    assert reopened_lifecycle.current_control() == frozen
    assert not reopened_plane.list_records(source_kind="semantic_ingestion_clean_generation")
    assert not reopened_plane.list_records(source_kind="semantic_ingestion_clean_generation_status")
    retained_clarification = reopened_plane.get_record(clarification_event.memory_id)
    assert retained_clarification is not None
    assert retained_clarification.content == valid_clarification_content

    final_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    final_writers = SemanticWriterAdmissionStore(
        final_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    final_holder: list[SemanticIngestionAtomicStore] = []
    final_repository = FileConflictIntegrityRepository(
        integrity_path,
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: final_holder[0].semantic_integrity_snapshot(),
        clean_replay_verifier=lambda repaired, retained, authority: final_holder[0].prepare_semantic_clean_recovery(
            repaired, retained, authority
        ),
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    final_lifecycle = PrivilegedSemanticIntegrityLifecycle(
        final_repository,
        clean_recovery_request_retainer=lambda retained: final_holder[0].retain_semantic_clean_recovery_request(
            retained
        ),
        clean_recovery_activator=lambda retained: final_holder[0].activate_semantic_clean_recovery(retained),
        clean_recovery_reconciler=lambda released: final_holder[0].reconcile_semantic_clean_recovery(released),
    )
    final_store = SemanticIngestionAtomicStore(
        final_plane,
        final_writers,
        now_provider=lambda: NOW,
        semantic_freeze_guard=final_lifecycle.freeze_guard,
        semantic_integrity_incident_reporter=final_lifecycle.incident_reporter,
        semantic_integrity_linearization=final_lifecycle.linearization,
    )
    final_holder.append(final_store)
    assert final_lifecycle.current_control() == frozen
    final_clarification = final_plane.get_record(clarification_event.memory_id)
    assert final_clarification is not None
    assert final_clarification.content == valid_clarification_content


def test_replay_authority_rejects_deleted_bound_generation_member_before_exposure() -> None:
    plane, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    authority = store.semantic_replay_authority()
    binding = authority.observation_bindings[0]
    member_id = f"semantic_ingestion:generation:{binding.operation_fence_id}:{binding.generation}:{binding.member_id}"
    backend = plane._records
    with backend._lock:
        del backend._records[member_id]

    with pytest.raises(
        PreplanningStoreError,
        match="committed generation is incomplete",
    ):
        store.semantic_replay_authority()


def test_replay_authority_carries_only_verified_same_or_earlier_generation_dependencies() -> None:
    _, _, store, binding, fence, service, repository = _setup(verified=True)
    control = store.acquire_lease(
        operation_fence=fence,
        writer_binding=binding,
        execution_token=f"semantic-ingestion:{fence.operation_fence_id}",
        owner_id="semantic-ingestion-pipeline",
        duration=timedelta(minutes=5),
    )
    artifact_payload = encode_typed_value({"artifact": "verified-prior"})
    artifact_digest = sha256(artifact_payload).hexdigest()
    closure_payload = encode_typed_value({"closure": "verified-prior"})
    closure_digest = sha256(closure_payload).hexdigest()

    def checkpoint(
        members: tuple[AtomicGenerationMember, ...],
        *,
        required_artifact_digests: tuple[str, ...] = (),
    ) -> None:
        nonlocal control
        request = SourceCheckpointAtomicWriteRequest(
            operation_fence_binding=fence,
            operation_lease_binding=store.lease_binding(control),
            writer_commit_binding=binding,
            expected_operation_generation=control.generation,
            expected_artifact_generation=control.generation,
            members=members,
            required_artifact_digests=required_artifact_digests,
            request_digest="0" * 64,
            progress_state="preplanning",
        )
        request = request.model_copy(update={"request_digest": generation_request_digest(request)})
        store.checkpoint_source_progress(request)
        control = store.get_operation(fence)

    first_progress_payload = encode_typed_value({"stage": "artifact_created", "artifact_digest": artifact_digest})
    checkpoint(
        (
            AtomicGenerationMember(
                member_id="semantic-ingestion-00-progress",
                kind="progress",
                canonical_payload=first_progress_payload,
                payload_digest=sha256(first_progress_payload).hexdigest(),
            ),
            AtomicGenerationMember(
                member_id="semantic-ingestion-01-replay-artifact",
                kind="replay_artifact",
                canonical_payload=artifact_payload,
                payload_digest=artifact_digest,
            ),
            AtomicGenerationMember(
                member_id="semantic-ingestion-02-replay-closure",
                kind="replay_artifact",
                canonical_payload=closure_payload,
                payload_digest=closure_digest,
            ),
        )
    )
    later_progress_payload = encode_typed_value({"stage": "artifact_consumed", "artifact_digest": artifact_digest})
    later_index_payload = encode_typed_value({"terminal": artifact_digest, "closure": closure_digest})
    checkpoint(
        (
            AtomicGenerationMember(
                member_id="semantic-ingestion-00-progress",
                kind="progress",
                canonical_payload=later_progress_payload,
                payload_digest=sha256(later_progress_payload).hexdigest(),
            ),
            AtomicGenerationMember(
                member_id="semantic-ingestion-01-artifact-index",
                kind="artifact_index",
                canonical_payload=later_index_payload,
                payload_digest=sha256(later_index_payload).hexdigest(),
            ),
        ),
        required_artifact_digests=(artifact_digest, closure_digest),
    )

    before_terminal = store.reconstructed_semantic_replay_authority()
    consumed = tuple(
        projection for projection in before_terminal.member_projections if projection.binding.generation == 3
    )
    index_projection = next(
        projection for projection in consumed if projection.semantic_object_kind == "artifact_index"
    )
    assert index_projection.referenced_digests == tuple(sorted((artifact_digest, closure_digest)))

    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    authority = store.semantic_replay_authority()
    assert authority.latest_checkpoint is not None
    assert (
        authority.latest_checkpoint.checkpoint.reconstructed_replay_authority_digest
        == store.reconstructed_semantic_replay_authority().authority_digest
    )


def test_replay_authority_rejects_absent_or_later_dependency() -> None:
    _, _, store, binding, fence, _, _ = _setup(verified=False)
    control = store.acquire_lease(
        operation_fence=fence,
        writer_binding=binding,
        execution_token="unresolved-dependency",
        owner_id="semantic-ingestion-pipeline",
        duration=timedelta(minutes=5),
    )
    future_artifact_digest = sha256(b"future-artifact").hexdigest()
    progress_payload = encode_typed_value({"stage": "future_consumer", "artifact_digest": future_artifact_digest})
    index_payload = encode_typed_value(
        {"terminal": future_artifact_digest, "closure": sha256(b"future-closure").hexdigest()}
    )
    request = SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=fence,
        operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding,
        expected_operation_generation=control.generation,
        expected_artifact_generation=control.generation,
        members=(
            AtomicGenerationMember(
                member_id="semantic-ingestion-00-progress",
                kind="progress",
                canonical_payload=progress_payload,
                payload_digest=sha256(progress_payload).hexdigest(),
            ),
            AtomicGenerationMember(
                member_id="semantic-ingestion-01-artifact-index",
                kind="artifact_index",
                canonical_payload=index_payload,
                payload_digest=sha256(index_payload).hexdigest(),
            ),
        ),
        required_artifact_digests=(),
        request_digest="0" * 64,
        progress_state="preplanning",
    )
    request = request.model_copy(update={"request_digest": generation_request_digest(request)})

    with pytest.raises(
        SemanticEventReplayError,
        match="semantic replay member has an unresolved cross-generation reference",
    ):
        store.checkpoint_source_progress(request)
    assert store.get_operation(fence).generation == 1


def test_replay_authority_rejects_peer_only_digest_advertisement() -> None:
    _, _, store, binding, fence, _, _ = _setup(verified=False)
    control = store.acquire_lease(
        operation_fence=fence,
        writer_binding=binding,
        execution_token="peer-advertisement",
        owner_id="semantic-ingestion-pipeline",
        duration=timedelta(minutes=5),
    )
    advertised_digest = sha256(b"not-a-member-payload").hexdigest()
    progress_payload = encode_typed_value({"stage": "peer_consumer", "artifact_digest": advertised_digest})
    advertisement_payload = encode_typed_value({"metadata": {"advertised_digest": advertised_digest}})
    request = SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=fence,
        operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding,
        expected_operation_generation=control.generation,
        expected_artifact_generation=control.generation,
        members=(
            AtomicGenerationMember(
                member_id="semantic-ingestion-00-progress",
                kind="progress",
                canonical_payload=progress_payload,
                payload_digest=sha256(progress_payload).hexdigest(),
            ),
            AtomicGenerationMember(
                member_id="semantic-ingestion-01-replay-artifact",
                kind="replay_artifact",
                canonical_payload=advertisement_payload,
                payload_digest=sha256(advertisement_payload).hexdigest(),
            ),
        ),
        required_artifact_digests=(),
        request_digest="0" * 64,
        progress_state="preplanning",
    )
    request = request.model_copy(update={"request_digest": generation_request_digest(request)})

    with pytest.raises(
        SemanticEventReplayError,
        match="semantic replay member has an unresolved cross-generation reference",
    ):
        store.checkpoint_source_progress(request)
    assert store.get_operation(fence).generation == 1


def test_store_nonaccepted_terminal_has_no_graph_or_event_effect() -> None:
    _, _, store, _, fence, service, _ = _setup(verified=False)
    service.persist(fence=fence, terminal=_nonaccepted(fence.operation_id))
    group = store.generation_members(fence, 3)
    assert {value.kind for value in group} == {
        "artifact_closure",
        "artifact_index",
        "group_result",
        "observation_delta",
    }
    control = store.get_operation(fence)
    assert control.state == "terminal" and control.graph_revision == "genesis"
    authority = store.semantic_replay_authority()
    assert authority.graph_state == store.semantic_replay_state()
    assert authority.latest_checkpoint is None
    assert authority.observation_bindings


def test_accepted_terminal_rechecks_authorization_before_any_planned_generation() -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    with pytest.raises(ValueError, match="authorization read set is stale"):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=_StaleAuthorization(),
        )
    assert store.get_operation(fence).generation == 1


def test_same_store_authority_rotation_rejects_before_graph_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane, _, store, binding, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = store.persist_terminal_group
    rotated = False

    def rotate_before_cas(request):
        nonlocal rotated
        if not rotated:
            rotated = True
            expected = request.authorization_precondition
            assert expected is not None
            record = plane.get_record(expected.authority_record_id)
            assert record is not None
            current = SemanticAuthorizationAuthorityRecord.model_validate(record.content["authority"])
            body = current.model_dump(mode="python", exclude={"coordinates_digest"})
            body.update({"authority_revision": 2, "state": "revoked"})
            replacement = SemanticAuthorizationAuthorityRecord(
                **body, coordinates_digest=sha256(encode_typed_value(body)).hexdigest()
            )
            store.replace_authorization_authority(
                writer_binding=binding,
                expected=expected,
                authority=replacement,
            )
        return original(request)

    monkeypatch.setattr(store, "persist_terminal_group", rotate_before_cas)
    with pytest.raises(MemoryPlaneRevisionConflictError, match="authorization"):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )
    control = store.get_operation(fence)
    assert control.generation == 2
    assert control.graph_revision == "genesis"
    assert control.group_result_digests == ()


def test_verified_revocation_rejects_policy_bearing_noncommit_before_any_effect() -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    accepted = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, accepted)
    scope_id = repository.scope_id(source_id=fence.source_id, source_digest=fence.source_digest)

    class _Verifier:
        def verify(self, *, command_bytes: bytes, server_time: datetime):
            assert command_bytes == b"signed-revoke"
            assert server_time == NOW
            return VerifiedSemanticAuthorizationTransition.create(
                authority_scope_id=scope_id,
                action="revoke",
                expected_revision=1,
            )

    VerifiedSemanticAuthorizationControlPlane(
        verifier=_Verifier(), repository=repository, now_provider=lambda: NOW
    ).apply(b"signed-revoke")
    terminal = SemanticTerminalOutcome.create(
        operation_id=fence.operation_id,
        status="unresolved",
        reason_codes=("consensus_unresolved",),
        candidates=(),
        arbitration_policy_bundle=accepted.arbitration_policy_bundle,
        authorization_read_set=accepted.authorization_read_set,
        temporal_closures=(),
        attempt_count=1,
    )
    with pytest.raises(ValueError, match="authorization authority is stale"):
        service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    control = store.get_operation(fence)
    assert control.generation == 1
    assert control.group_result_digests == ()
    assert control.graph_revision == "genesis"


def test_same_store_authority_expiry_at_precommit_has_zero_effects() -> None:
    clock = [NOW]
    _, _, store, _, fence, service, repository = _setup(verified=True, now_provider=lambda: clock[0])
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal, valid_until=NOW + timedelta(minutes=1))
    clock[0] = NOW + timedelta(minutes=2)
    with pytest.raises(ValueError, match="authorization authority is stale"):
        service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    control = store.get_operation(fence)
    assert control.generation == 1
    assert control.group_result_digests == ()
    assert control.graph_revision == "genesis"


@pytest.mark.parametrize("method_name", ["checkpoint_source_progress", "persist_terminal_group", "finalize_source"])
def test_retry_and_lost_ack_are_byte_idempotent(monkeypatch: pytest.MonkeyPatch, method_name: str) -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = getattr(store, method_name)
    failed = False

    def lost_ack(request, **kwargs):
        nonlocal failed
        result = original(request, **kwargs)
        if not failed:
            failed = True
            raise OSError("simulated lost acknowledgement")
        return result

    monkeypatch.setattr(store, method_name, lost_ack)
    with pytest.raises(OSError, match="lost acknowledgement"):
        service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    assert failed is True
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    assert store.get_operation(fence).state == "terminal"
    with pytest.raises(ValueError, match="differs from retry terminal"):
        service.persist(fence=fence, terminal=_nonaccepted(fence.operation_id))


def test_filesystem_reopen_recovers_exact_terminal_without_duplicate_effects(tmp_path) -> None:
    backend = JsonlMemoryPlaneStore(tmp_path / "semantic-terminal-store")
    _, _, store, _, fence, service, repository = _setup(verified=True, backend=backend)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    original_projection_bindings = store.projection_history.replay_bindings()

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "semantic-terminal-store"))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    reopened_store = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: NOW)
    reopened = SemanticTerminalPersistenceService(
        atomic_store=reopened_store, writer_binding_provider=lambda: reopened_binding
    )
    reopened.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    assert reopened_store.get_operation(fence).generation == 4
    assert reopened_store.projection_history.replay_bindings() == (original_projection_bindings)
    assert len(reopened_plane.list_records(source_kind="semantic_projection_temporal_history_entry")) == 1
    assert len(reopened_plane.list_records(source_kind="semantic_projection_trust_history_entry")) == 1


def test_jsonl_terminal_wire_remains_legacy_and_excludes_semantic_transaction_members_after_lost_ack(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The M3 store path preserves the legacy terminal wire through recovery."""

    storage = tmp_path / "legacy-terminal-wire"
    _, _, store, _, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
    )
    terminal = accepted_terminal(operation_id=fence.operation_id)
    terminal_wire = encode_semantic_contract(terminal)
    # The golden moved with the M4 terminal carrier contract; the wire shape
    # assertions below still pin the legacy exclusion boundary.
    assert terminal.terminal_digest == "d708ae30ed670efde8e915c4e1df9eebf6fea96db5132bf15a53b23e2cefa68f"
    assert sha256(terminal_wire).hexdigest() == "1e49afc814884d703346237de95686a17c4d60925e25363e12042b5707ffc25e"
    assert decode_semantic_contract(terminal_wire, SemanticTerminalOutcome) == terminal
    for forbidden in ("plan_lineage", "execution_manifest"):
        with pytest.raises(ValueError):
            SemanticTerminalOutcome.model_validate(
                terminal.model_dump(mode="python") | {forbidden: {}}
            )

    _activate(repository, fence, terminal)
    original_finalize = store.finalize_source
    lost_ack = False

    def finalize_then_lose_ack(request):
        nonlocal lost_ack
        result = original_finalize(request)
        if not lost_ack:
            lost_ack = True
            raise OSError("simulated finalization lost acknowledgement")
        return result

    monkeypatch.setattr(store, "finalize_source", finalize_then_lose_ack)
    with pytest.raises(OSError, match="finalization lost acknowledgement"):
        service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    assert lost_ack

    expected_kinds = {
        2: (
            "artifact_closure", "artifact_index", "authorization_read_set",
            "independence_certificate", "lifecycle", "plan", "planning_artifact",
            "planning_authorization", "progress", "terminal_artifact",
        ),
        3: ("artifact_closure", "artifact_index", "event_batch", "graph_delta", "group_result", "observation_delta"),
        4: ("artifact_closure", "lifecycle", "observation_delta", "source_result", "source_summary", "terminal_operation"),
    }
    for generation, kinds in expected_kinds.items():
        members = store.generation_members(fence, generation)
        assert tuple(member.kind for member in members) == kinds
        assert {member.kind for member in members}.isdisjoint({"plan_lineage", "execution_manifest"})
    checkpoint_terminal = next(
        member for member in store.generation_members(fence, 2) if member.kind == "terminal_artifact"
    )
    assert checkpoint_terminal.canonical_payload == terminal_wire

    records_after_lost_ack = tuple(store._memory_plane.list_records())
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    reopened_store = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: NOW)
    reopened = SemanticTerminalPersistenceService(
        atomic_store=reopened_store,
        writer_binding_provider=lambda: reopened_writers.commit_binding(reopened_writers.current()),
    )
    reopened.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    # Compare the durable representation: the reopened store returns
    # JSON-parsed content (lists) while the captured snapshot keeps tuples.
    assert _json_round_tripped(tuple(reopened_plane.list_records())) == (
        _json_round_tripped(records_after_lost_ack)
    )
    assert reopened_store.get_operation(fence).generation == 4


def test_terminal_group_jsonl_failure_keeps_old_complete_authority_then_retries(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = tmp_path / "terminal-projection-atomic-failure"
    backend = JsonlMemoryPlaneStore(storage)
    _, _, store, _, fence, service, repository = _setup(
        verified=True,
        backend=backend,
    )
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = store.persist_terminal_group

    def fail_terminal_group(request):
        def fail_replace(_source, _destination) -> None:
            raise OSError("injected terminal projection CAS failure")

        with monkeypatch.context() as context:
            context.setattr(
                "memorii.core.memory_plane.store.os.replace",
                fail_replace,
            )
            return original(request)

    monkeypatch.setattr(store, "persist_terminal_group", fail_terminal_group)
    with pytest.raises(OSError, match="terminal projection CAS failure"):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    assert reopened_store.semantic_replay_state().graph_revision == "genesis"
    assert reopened_store.projection_history.replay_bindings() == ()

    reopened_authorization_repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=reopened_store,
        writer_binding_provider=lambda: reopened_binding,
        now_provider=lambda: NOW,
    )
    reopened_service = SemanticTerminalPersistenceService(
        atomic_store=reopened_store,
        writer_binding_provider=lambda: reopened_binding,
        authorization_repository=reopened_authorization_repository,
    )
    reopened_service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    assert reopened_store.semantic_replay_state().graph_revision != "genesis"
    assert len(reopened_plane.list_records(source_kind="semantic_projection_temporal_history_entry")) == 1
    assert len(reopened_plane.list_records(source_kind="semantic_projection_trust_history_entry")) == 1


def test_public_checkpoint_api_exposes_validation_without_signing_material() -> None:
    plane, _, store, _, _, _, _ = _setup(verified=False)

    assert not hasattr(event_replay, "ReplayCheckpointKeyMaterial")
    assert not hasattr(store, "checkpoint_resume_authority")
    assert not hasattr(store, "checkpoint_signature_authority")
    assert not hasattr(plane, "claim_semantic_checkpoint_signature_authority")
    assert callable(store.validate_semantic_replay_checkpoint)
    assert callable(store.resume_semantic_replay_checkpoint_tail)


@pytest.mark.parametrize("backend_kind", ("memory", "jsonl"))
def test_checkpoint_secret_cannot_be_retrieved_through_public_storage_api(
    backend_kind: str,
    tmp_path,
) -> None:
    backend = (
        InMemoryMemoryPlaneStore()
        if backend_kind == "memory"
        else JsonlMemoryPlaneStore(tmp_path / "checkpoint-secret-api")
    )
    plane = MemoryPlaneService(record_store=backend)
    checkpoint_purpose = "semantic-ingestion-replay-checkpoint-signing"

    with pytest.raises(
        PermissionError,
        match="checkpoint signing material is backend-private",
    ):
        backend.load_or_create_protected_secret(
            purpose=checkpoint_purpose,
            length=32,
        )
    with pytest.raises(
        PermissionError,
        match="checkpoint signing material is backend-private",
    ):
        plane.load_or_create_protected_secret(
            purpose=checkpoint_purpose,
            length=32,
        )

    first = plane.load_or_create_protected_secret(
        purpose="test-general-protected-secret",
        length=32,
    )
    second = plane.load_or_create_protected_secret(
        purpose="test-general-protected-secret",
        length=32,
    )
    assert len(first) == 32
    assert second == first


def test_external_checkpoint_signature_forgery_is_rejected() -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    authoritative = store.semantic_replay_authority().latest_checkpoint
    assert authoritative is not None
    forged_checkpoint = authoritative.checkpoint.model_copy(
        update={"signature": "f" * 64}
    )
    forged_body = {
        "checkpoint": forged_checkpoint,
        "materialized_snapshot": authoritative.materialized_snapshot,
        "watermark_batch": authoritative.watermark_batch,
    }
    forged_digest_body = {
        key: value.model_dump(mode="python") for key, value in forged_body.items()
    }
    forged = SemanticReplayCheckpointBundle(
        checkpoint=forged_checkpoint,
        materialized_snapshot=authoritative.materialized_snapshot,
        watermark_batch=authoritative.watermark_batch,
        bundle_digest=sha256(
            b"memorii.semantic-replay-checkpoint-bundle.v1\0"
            + encode_typed_value(forged_digest_body)
        ).hexdigest(),
    )

    with pytest.raises(
        SemanticEventReplayError,
        match="checkpoint signature is invalid",
    ):
        store.validate_semantic_replay_checkpoint(forged)


@pytest.mark.parametrize("mutation", ("pointer", "immutable_member"))
def test_signed_nonempty_conflict_checkpoint_reopens_and_rejects_authority_mutation(
    tmp_path,
    mutation: Literal["pointer", "immutable_member"],
) -> None:
    """Checkpoint resume consults the reopened live conflict authority, not its bytes alone."""

    storage, _, _, _, _, _ = _persist_reconstructible_clarification_history(
        tmp_path,
        complete=False,
    )
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    store = SemanticIngestionAtomicStore(
        plane,
        SemanticWriterAdmissionStore(
            plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: NOW,
        ),
        now_provider=lambda: NOW,
    )
    authoritative = store.semantic_replay_authority().latest_checkpoint
    assert authoritative is not None
    assert authoritative.checkpoint.semantic_conflict_replay_binding is not None
    assert authoritative.checkpoint.semantic_conflict_replay_binding.immutable_record_count > 0
    assert store.validate_semantic_replay_checkpoint(authoritative) == store.semantic_replay_state()
    assert store.resume_semantic_replay_checkpoint_tail(authoritative, ()) == store.semantic_replay_state()

    root = tmp_path / f"checkpoint-conflict-{mutation}"
    copytree(storage, root)
    mutable_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root))
    if mutation == "pointer":
        target = next(
            record
            for record in mutable_plane.list_records(
                source_kind="semantic_ingestion_conflict_authority"
            )
            if record.memory_id.startswith("semantic_ingestion:conflict-authority:pointer:")
        )
        pointer = ActiveSemanticConflict.model_validate(
            decode_typed_value(bytes.fromhex(str(target.content["canonical_hex"])))
        )
        pointer_body = pointer.model_dump(mode="python", exclude={"pointer_digest"})
        pointer_body["current_record_digest"] = sha256(b"syntactically-valid-pointer-mutation").hexdigest()
        replacement_payload = ActiveSemanticConflict(
            **pointer_body,
            pointer_digest=sha256(
                b"memorii.semantic-conflict-active-pointer.v1\0"
                + encode_typed_value(pointer_body)
            ).hexdigest(),
        )
    else:
        target = next(
            record
            for record in mutable_plane.list_records(
                source_kind="semantic_ingestion_conflict_authority"
            )
            if record.memory_id.startswith(
                "semantic_ingestion:conflict-authority:clarification-transition:"
            )
        )
        transition = decode_persisted_conflict_generation(
            decode_typed_value(bytes.fromhex(str(target.content["canonical_hex"]))),
            SemanticConflictClarificationTransition,
        )
        transition_body = transition.model_dump(mode="python", exclude={"transition_digest"})
        transition_body["transitioned_at"] = transition.transitioned_at + timedelta(seconds=1)
        replacement_payload = SemanticConflictClarificationTransition(
            **transition_body,
            transition_digest=sha256(
                b"memorii.semantic-conflict-clarification-transition.v1\0"
                + encode_typed_value(transition_body)
            ).hexdigest(),
        )
    raw = encode_typed_value(replacement_payload.model_dump(mode="python"))
    replacement = target.model_copy(
        update={
            "content": {
                **target.content,
                "canonical_hex": raw.hex(),
                "authority_digest": sha256(raw).hexdigest(),
            }
        }
    )
    _rewrite_jsonl_snapshot(
        JsonlMemoryPlaneStore(root), mutable_plane, replacements=(replacement,)
    )

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root))
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        SemanticWriterAdmissionStore(
            reopened_plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: NOW,
        ),
        now_provider=lambda: NOW,
    )
    exposed = None
    with pytest.raises((PreplanningStoreError, SemanticEventReplayError, ValueError)):
        exposed = reopened_store.validate_semantic_replay_checkpoint(authoritative)
    assert exposed is None


def test_filesystem_reopen_rejects_malformed_terminal_artifact_batch(tmp_path) -> None:
    backend = JsonlMemoryPlaneStore(tmp_path / "semantic-malformed-terminal")
    _, _, _, _, fence, service, repository = _setup(verified=True, backend=backend)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)

    batches = backend._read_batches_unlocked()
    rewritten = []
    changed = False
    for batch in batches:
        records = []
        for record in batch.records:
            member = record.content.get("member")
            if isinstance(member, dict) and member.get("kind") in {
                "terminal_artifact",
                "source_result",
            }:
                malformed = dict(member)
                malformed["canonical_payload"] = b"{malformed-terminal"
                malformed["payload_digest"] = sha256(malformed["canonical_payload"]).hexdigest()
                content = dict(record.content)
                content["member"] = malformed
                record = record.model_copy(update={"content": content})
                changed = True
            records.append(record)
        rewritten.append(
            _PersistedBatch.create(
                revision=batch.revision,
                data_revision=batch.data_revision,
                records=tuple(records),
            )
        )
    assert changed is True
    backend._replace_batches(rewritten)

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "semantic-malformed-terminal"))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    reopened_store = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: NOW)
    reopened = SemanticTerminalPersistenceService(
        atomic_store=reopened_store,
        writer_binding_provider=lambda: reopened_writers.commit_binding(reopened_writers.current()),
    )
    with pytest.raises((PreplanningStoreError, ValueError)):
        reopened.recover_terminal_artifact(fence=fence)


@pytest.mark.parametrize("target", ("aggregate", "member", "index"))
@pytest.mark.parametrize("mutation", ("delete", "substitute"))
def test_jsonl_reopen_rejects_replay_authority_deletion_and_substitution(
    tmp_path,
    target: str,
    mutation: str,
) -> None:
    root = tmp_path / f"replay-{target}-{mutation}"
    backend = JsonlMemoryPlaneStore(root)
    plane, _, _, _, fence, service, repository = _setup(
        verified=True,
        backend=backend,
    )
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(
        fence=fence,
        terminal=terminal,
        authorization_verifier=AUTHORIZATION,
    )
    current = {record.memory_id: record for record in plane.list_records()}
    if target == "aggregate":
        target_id = next(
            memory_id
            for memory_id, record in current.items()
            if record.source_kind == "semantic_ingestion_replay_authority"
        )
    else:
        expected_kind = "artifact_index" if target == "index" else "observation_delta"
        target_id = next(
            memory_id
            for memory_id, record in current.items()
            if record.source_kind == "semantic_ingestion_generation_member"
            and record.content.get("member", {}).get("kind") == expected_kind
        )
    rewritten = []
    changed = False
    for batch in backend._read_batches_unlocked():
        records = []
        for record in batch.records:
            if record.memory_id != target_id:
                records.append(record)
                continue
            changed = True
            if mutation == "delete":
                continue
            content = dict(record.content)
            if target == "aggregate":
                content["canonical_hex"] = "00"
            else:
                member = dict(content["member"])
                member["canonical_payload"] = encode_typed_value({"substituted": target})
                member["payload_digest"] = sha256(member["canonical_payload"]).hexdigest()
                content["member"] = member
            records.append(record.model_copy(update={"content": content}))
        rewritten.append(
            _PersistedBatch.create(
                revision=batch.revision,
                data_revision=batch.data_revision,
                records=tuple(records),
            )
        )
    assert changed
    backend._replace_batches(rewritten)

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    exposed = None
    with pytest.raises((PreplanningStoreError, ValueError)):
        exposed = reopened_store.semantic_replay_authority()
    assert exposed is None


def test_durable_retry_checkpoint_resumes_after_group_lost_ack_without_learned_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = store.persist_terminal_group
    failed = False

    def lost_ack(request, **kwargs):
        nonlocal failed
        result = original(request, **kwargs)
        if not failed:
            failed = True
            raise OSError("simulated group lost acknowledgement")
        return result

    monkeypatch.setattr(store, "persist_terminal_group", lost_ack)
    with pytest.raises(OSError, match="lost acknowledgement"):
        service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    session = service.open_lease_session(fence=fence)
    session.checkpoint_retryable(stage="finalization", failure_kind="store_outage", terminal=terminal)
    monkeypatch.setattr(store, "persist_terminal_group", original)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    assert store.get_operation(fence).state == "terminal"


def test_cross_operation_terminal_swap_fails_before_generation_write() -> None:
    _, _, store, _, fence, service, _ = _setup(verified=True)
    with pytest.raises(ValueError, match="does not bind"):
        service.persist(fence=fence, terminal=accepted_terminal(operation_id="other-operation"))
    assert store.get_operation(fence).generation == 1


def test_legacy_retry_exhausted_control_requires_explicit_terminal_migration() -> None:
    plane, _, _, _, fence, _, _ = _setup(verified=True)
    record = plane.get_record(f"semantic_ingestion:operation:{fence.operation_fence_id}")
    assert record is not None
    content = dict(record.content)
    control = dict(content["control"])
    control["state"] = "retry_exhausted"
    content["control"] = control
    legacy = record.model_copy(update={"content": content})
    with pytest.raises(
        PreplanningStoreError,
        match="legacy retry_exhausted control requires explicit terminal migration",
    ):
        _control_from_record(legacy)


def test_conflict_publication_is_atomic_at_every_durable_boundary(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slot-bearing contest cannot leave a partial durable closure behind."""

    for boundary in ("before_write", "lost_acknowledgement"):
        storage = tmp_path / boundary
        plane, writers, store, binding, fence, service, repository = _setup(
            verified=True,
            backend=JsonlMemoryPlaneStore(storage),
            scope_ids=frozenset({"scope:a"}),
            with_test_conflict_authority=True,
        )
        first = accepted_terminal(
            operation_id=fence.operation_id,
            valid_start=NOW,
            valid_end=NOW + timedelta(days=2),
        )
        _activate(repository, fence, first)
        service.persist(
            fence=fence,
            terminal=first,
            authorization_verifier=AUTHORIZATION,
        )
        _, contested_fence = handoff(
            plane,
            coordinate=f"atomic-{boundary}",
            scope_ids=frozenset({"scope:a"}),
            atomic_store=store,
            writer_binding=binding,
        )
        contested = accepted_terminal(
            operation_id=contested_fence.operation_id,
            object_logical_entity_id="entity:initech",
            object_entity_revision_id="entity-revision:initech:v1",
            valid_start=NOW,
            valid_end=NOW + timedelta(days=2),
        )
        _activate(repository, contested_fence, contested)
        before = tuple(plane.list_records())
        before_final_write: tuple[CanonicalMemoryRecord, ...] | None = None
        original_write = plane.conditionally_write_records
        captured: list[tuple[CanonicalMemoryRecord, ...]] = []
        fired = False

        def interrupt(
            records,
            *,
            captured=captured,
            boundary=boundary,
            original_write=original_write,
            plane=plane,
            **kwargs,
        ):
            nonlocal fired, before_final_write
            captured.append(tuple(records))
            has_conflict = any(
                record.source_kind == "semantic_ingestion_conflict_authority"
                for record in records
            )
            if has_conflict and not fired:
                fired = True
                if boundary == "before_write":
                    # The planned checkpoint is a legitimate predecessor
                    # generation.  This is the exact state at the final
                    # semantic CAS boundary, which must remain untouched.
                    before_final_write = tuple(plane.list_records())
                    raise OSError("injected conflict publication failure")
                original_write(records, **kwargs)
                raise OSError("injected conflict publication lost acknowledgement")
            return original_write(records, **kwargs)

        monkeypatch.setattr(plane, "conditionally_write_records", interrupt)
        with pytest.raises(OSError, match="conflict publication"):
            service.persist(
                fence=contested_fence,
                terminal=contested,
                authorization_verifier=AUTHORIZATION,
            )
        assert fired
        if boundary == "before_write":
            assert before_final_write is not None
            assert tuple(plane.list_records()) == before_final_write
            assert tuple(plane.list_records()) != before
        monkeypatch.setattr(plane, "conditionally_write_records", original_write)
        reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
        reopened_writers = SemanticWriterAdmissionStore(
            reopened_plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: NOW,
        )
        reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
        reopened_store = SemanticIngestionAtomicStore(
            reopened_plane,
            reopened_writers,
            now_provider=lambda: NOW,
            semantic_conflict_authority_resolver=_TestSemanticConflictAuthorityResolver(reopened_plane),
        )
        reopened_repository = SemanticAuthorizationAuthorityRepository(
            atomic_store=reopened_store,
            writer_binding_provider=lambda binding=reopened_binding: binding,
            now_provider=lambda: NOW,
        )
        reopened_service = SemanticTerminalPersistenceService(
            atomic_store=reopened_store,
            writer_binding_provider=lambda binding=reopened_binding: binding,
            authorization_repository=reopened_repository,
        )
        reopened_before_retry = tuple(reopened_plane.list_records())
        retained_group_authority: tuple[CanonicalMemoryRecord, ...] | None = None
        if boundary == "before_write":
            # The reopened store returns JSON-parsed content (lists) while
            # the captured in-memory snapshot keeps tuples; compare the
            # durable representation, not the in-memory container types.
            assert _json_round_tripped(reopened_before_retry) == _json_round_tripped(
                before_final_write
            )
        else:
            replay_binding = reopened_store.projection_history.semantic_conflict_replay_binding()
            assert replay_binding.immutable_record_count == 1
            assert replay_binding.pointer_history_count == 1
            retained_control = reopened_store.get_operation(contested_fence)
            assert retained_control.state == "planned"
            assert len(retained_control.group_result_digests) == 1
            assert reopened_store.projection_history.current_temporal(
                policy_fingerprint=first.arbitration_policy_bundle.temporal_policy.fingerprint
            ).pointer.publication_sequence == 2
            assert reopened_store.projection_history.current_trust(
                policy_fingerprint=first.arbitration_policy_bundle.trust_policy.fingerprint
            ).pointer.publication_sequence == 2
            retained_group_authority = tuple(
                record
                for record in reopened_before_retry
                if record.source_kind
                in {
                    "semantic_ingestion_conflict_authority",
                    "semantic_ingestion_event_batch",
                    "semantic_ingestion_reference_integrity",
                    "semantic_ingestion_replay_state",
                }
                or record.source_kind.startswith("semantic_projection_")
            )
        reopened_service.persist(
            fence=contested_fence,
            terminal=contested,
            authorization_verifier=AUTHORIZATION,
        )
        reopened_after_retry = tuple(reopened_plane.list_records())
        assert reopened_after_retry != reopened_before_retry
        assert reopened_store.get_operation(contested_fence).state == "terminal"
        if retained_group_authority is not None:
            # The committed group landed before its acknowledgement was lost;
            # retry may add source finalization but cannot rewrite that group.
            assert tuple(
                record
                for record in reopened_after_retry
                if record.source_kind
                in {
                    "semantic_ingestion_conflict_authority",
                    "semantic_ingestion_event_batch",
                    "semantic_ingestion_reference_integrity",
                    "semantic_ingestion_replay_state",
                }
                or record.source_kind.startswith("semantic_projection_")
            ) == retained_group_authority
        conflict_records = tuple(
            record
            for record in reopened_plane.list_records()
            if record.source_kind == "semantic_ingestion_conflict_authority"
        )
        assert {
            record.content.get("authority_record_type") for record in conflict_records
        } >= {
            "introduction",
            "active_pointer",
            "pointer_history",
            "resolver_authority",
            "resolver_pointer",
        }
        assert any(
            "semantic_ingestion_conflict_authority" in {
                record.source_kind for record in records
            }
            and any(
                record.source_kind.startswith("semantic_ingestion_generation_")
                for record in records
            )
            and any(
                record.source_kind.startswith("semantic_projection_")
                for record in records
            )
            for records in captured
        )
        assert (
            reopened_store.projection_history.semantic_conflict_replay_binding().immutable_record_count
            == 1
        )
        completed_records = tuple(reopened_plane.list_records())
        reopened_service.persist(
            fence=contested_fence,
            terminal=contested,
            authorization_verifier=AUTHORIZATION,
        )
        assert tuple(reopened_plane.list_records()) == completed_records


def _reopened_conflict_history(storage):
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    return plane, SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)


def test_clarification_history_reconstructs_completed_and_audit_only_superseded_edges(
    tmp_path,
) -> None:
    storage, introduction, submitted, completed, pointer_two, _ = (
        _persist_reconstructible_clarification_history(tmp_path)
    )
    _, reopened = _reopened_conflict_history(storage)
    completed_binding = reopened.projection_history.semantic_conflict_replay_binding()
    assert completed_binding.immutable_record_count == 3
    assert reopened.projection_history._current_semantic_conflicts()[
        introduction.conflict_id
    ][1].transition_digest == completed.transition_digest

    # A superseded edge remains immutable audit history; it cannot advance the
    # active pointer, so the submitted edge remains the live conflict state.
    plane, _ = _reopened_conflict_history(storage)
    superseded = _clarification_transition(
        introduction=introduction,
        predecessor_digest=submitted.transition_digest,
        predecessor_revision=submitted.resulting_attention.conflict_revision,
        predecessor_status=ConflictStatus.CLARIFICATION_SUBMITTED,
        status=ConflictStatus.CLARIFICATION_SUBMITTED,
        reason=SemanticConflictClarificationTransitionReason.SUPERSEDED,
        record_coordinate=3,
        successor_conflict_revision=sha256(b"natural-successor").hexdigest(),
    )
    superseded_id = (
        "semantic_ingestion:conflict-authority:clarification-transition:"
        f"{superseded.transition_digest}"
    )
    completed_id = (
        "semantic_ingestion:conflict-authority:clarification-transition:"
        f"{completed.transition_digest}"
    )
    history = reopened.projection_history
    completed_record = plane.get_record(completed_id)
    assert completed_record is not None
    pointer_id = f"semantic_ingestion:conflict-authority:pointer:{introduction.conflict_id}"
    pointer_record = plane.get_record(pointer_id)
    assert pointer_record is not None
    _rewrite_jsonl_snapshot(
        plane._records,
        plane,
        replacements=(
            history._conflict_authority_record(superseded_id, superseded, NOW),
            history._conflict_authority_record(pointer_id, pointer_two, NOW),
        ),
        deleted_ids=(
            completed_id,
            f"semantic_ingestion:conflict-authority:pointer-history:{introduction.conflict_id}:3",
        ),
    )
    _, superseded_reopened = _reopened_conflict_history(storage)
    assert superseded_reopened.projection_history._current_semantic_conflicts()[
        introduction.conflict_id
    ][1].transition_digest == submitted.transition_digest


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_predecessor",
        "noncontiguous_coordinate",
        "reordered_transition_coordinate",
        "predecessor_digest_mismatch",
        "predecessor_revision_mismatch",
        "predecessor_status_mismatch",
        "inconsistent_active_pointer",
        "unknown_clarification_type",
        "future_clarification_payload",
        "superseded_pointer_target",
    ),
)
def test_clarification_history_reconstruction_rejects_corrupt_authority(
    tmp_path,
    mutation: str,
) -> None:
    storage, introduction, submitted, completed, pointer_two, _ = (
        _persist_reconstructible_clarification_history(tmp_path)
    )
    plane, reopened = _reopened_conflict_history(storage)
    history = reopened.projection_history
    submitted_id = (
        "semantic_ingestion:conflict-authority:clarification-transition:"
        f"{submitted.transition_digest}"
    )
    completed_id = (
        "semantic_ingestion:conflict-authority:clarification-transition:"
        f"{completed.transition_digest}"
    )
    pointer_id = f"semantic_ingestion:conflict-authority:pointer:{introduction.conflict_id}"
    replacements: list[CanonicalMemoryRecord] = []
    deleted_ids: tuple[str, ...] = ()
    if mutation == "missing_predecessor":
        # Keep the immutable prefix closed after removing the submitted edge,
        # so reconstruction reaches the missing-predecessor check itself.
        body = _coerced_transition_body(
            completed.model_dump(mode="python", exclude={"transition_digest"})
        )
        body.update({"record_coordinate": 2, "transition_coordinate": 2})
        # Corrupt records are planted without lifecycle validation; the
        # coerced body keeps serialization warning-free under -W error.
        orphaned = SemanticConflictClarificationTransition.model_construct(
            **body,
            transition_digest=_clarification_transition_digest(body),
        )
        orphaned_pointer = _clarification_pointer(
            conflict_id=introduction.conflict_id,
            record_id=completed_id,
            record_digest_value=orphaned.transition_digest,
            conflict_revision=orphaned.resulting_attention.conflict_revision,
            pointer_revision=2,
            predecessor_pointer_digest=pointer_two.predecessor_pointer_digest,
        )
        head_record = plane.get_record("semantic_ingestion:conflict-authority:ledger-head")
        assert head_record is not None
        head = SemanticConflictLedgerHead.model_validate(
            decode_typed_value(bytes.fromhex(str(head_record.content["canonical_hex"])))
        )
        replacements.extend(
            (
                history._conflict_authority_record(completed_id, orphaned, NOW),
                history._conflict_authority_record(pointer_id, orphaned_pointer, NOW),
                history._conflict_authority_record(
                    head_record.memory_id,
                    SemanticConflictLedgerHead.create(
                        repository_id=head.repository_id,
                        last_record_coordinate=2,
                        head_revision=head.head_revision,
                        predecessor_head_digest=head.predecessor_head_digest,
                    ),
                    NOW,
                ),
            )
        )
        deleted_ids = (
            submitted_id,
            f"semantic_ingestion:conflict-authority:pointer-history:{introduction.conflict_id}:2",
            f"semantic_ingestion:conflict-authority:pointer-history:{introduction.conflict_id}:3",
        )
    elif mutation == "inconsistent_active_pointer":
        stale_pointer = _clarification_pointer(
            conflict_id=introduction.conflict_id,
            record_id=completed_id,
            record_digest_value=completed.transition_digest,
            conflict_revision=completed.resulting_attention.conflict_revision,
            pointer_revision=2,
            predecessor_pointer_digest=pointer_two.predecessor_pointer_digest,
        )
        replacements.append(
            history._conflict_authority_record(pointer_id, stale_pointer, NOW)
        )
    elif mutation in {"unknown_clarification_type", "future_clarification_payload"}:
        unknown = plane.get_record(completed_id)
        assert unknown is not None
        if mutation == "unknown_clarification_type":
            replacements.append(
                unknown.model_copy(
                    update={
                        "memory_id": "semantic_ingestion:conflict-authority:clarification-future:1"
                    }
                )
            )
        else:
            raw = decode_typed_value(bytes.fromhex(str(unknown.content["canonical_hex"])))
            assert isinstance(raw, dict)
            raw["future_lifecycle_field"] = "unsupported"
            canonical = encode_typed_value(raw)
            replacements.append(
                unknown.model_copy(
                    update={
                        "content": unknown.content
                        | {
                            "canonical_hex": canonical.hex(),
                            "authority_digest": sha256(canonical).hexdigest(),
                        }
                    }
                )
            )
    elif mutation == "superseded_pointer_target":
        superseded = _clarification_transition(
            introduction=introduction,
            predecessor_digest=submitted.transition_digest,
            predecessor_revision=submitted.resulting_attention.conflict_revision,
            predecessor_status=ConflictStatus.CLARIFICATION_SUBMITTED,
            status=ConflictStatus.CLARIFICATION_SUBMITTED,
            reason=SemanticConflictClarificationTransitionReason.SUPERSEDED,
            record_coordinate=3,
            successor_conflict_revision=sha256(b"natural-successor").hexdigest(),
        )
        superseded_id = (
            "semantic_ingestion:conflict-authority:clarification-transition:"
            f"{superseded.transition_digest}"
        )
        superseded_pointer = _clarification_pointer(
            conflict_id=introduction.conflict_id,
            record_id=superseded_id,
            record_digest_value=superseded.transition_digest,
            conflict_revision=superseded.resulting_attention.conflict_revision,
            pointer_revision=3,
            predecessor_pointer_digest=pointer_two.pointer_digest,
        )
        replacements.extend(
            (
                history._conflict_authority_record(superseded_id, superseded, NOW),
                history._conflict_authority_record(pointer_id, superseded_pointer, NOW),
            )
        )
        deleted_ids = (completed_id,)
    else:
        body = _coerced_transition_body(
            completed.model_dump(mode="python", exclude={"transition_digest"})
        )
        if mutation == "noncontiguous_coordinate":
            body.update({"record_coordinate": 4, "transition_coordinate": 4})
        elif mutation == "reordered_transition_coordinate":
            body["transition_coordinate"] = 2
        elif mutation == "predecessor_digest_mismatch":
            body["predecessor_record_digest"] = sha256(b"wrong-predecessor").hexdigest()
        elif mutation == "predecessor_revision_mismatch":
            body["predecessor_conflict_revision"] = sha256(b"wrong-revision").hexdigest()
        else:
            body["predecessor_status"] = ConflictStatus.OPEN
        mutated = SemanticConflictClarificationTransition.model_construct(
            **body,
            transition_digest=_clarification_transition_digest(body),
        )
        replacements.append(history._conflict_authority_record(completed_id, mutated, NOW))
    _rewrite_jsonl_snapshot(plane._records, plane, replacements=tuple(replacements), deleted_ids=deleted_ids)
    _, corrupt_reopened = _reopened_conflict_history(storage)
    with pytest.raises(ProjectionHistoryError, match="projection_history_integrity_error"):
        corrupt_reopened.projection_history._current_semantic_conflicts()


@pytest.mark.parametrize("mutation", ("missing", "extra", "pointer", "display", "revoked"))
def test_conflict_authority_bijection_scope_display_and_revocation_fail_before_write(
    tmp_path,
    mutation: str,
) -> None:
    """Resolver output is a total, current authority closure, not advisory display data."""

    class _HostResolver(_TestSemanticConflictAuthorityResolver):
        def resolve_semantic_conflicts(self, requests):
            resolutions = super().resolve_semantic_conflicts(requests)
            if mutation == "missing":
                return ()
            if mutation == "extra":
                return (*resolutions, resolutions[0])
            resolution = resolutions[0]
            if mutation == "pointer":
                return (
                    resolution.model_copy(
                        update={
                            "resolver_authority_pointer": resolution.resolver_authority_pointer.model_copy(
                                update={"pointer_digest": "0" * 64}
                            )
                        }
                    ),
                )
            if mutation == "display":
                return (
                    resolution.model_copy(
                        update={
                            "display": resolution.display.model_copy(
                                update={"renderer_schema": "cross-tenant-renderer"}
                            )
                        }
                    ),
                )
            return (
                resolution.model_copy(
                    update={
                        "resolver_authority_record": resolution.resolver_authority_record.model_copy(
                            update={"status": "revoked"}
                        )
                    }
                ),
            )

    plane, _, store, binding, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(tmp_path / mutation),
        scope_ids=frozenset({"scope:a"}),
        with_test_conflict_authority=True,
        conflict_resolver_factory=_HostResolver,
    )
    first = accepted_terminal(
        operation_id=fence.operation_id,
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, fence, first)
    service.persist(fence=fence, terminal=first, authorization_verifier=AUTHORIZATION)
    _, contender_fence = handoff(
        plane,
        coordinate=f"authority-{mutation}",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=binding,
    )
    contender = accepted_terminal(
        operation_id=contender_fence.operation_id,
        object_logical_entity_id="entity:initech",
        object_entity_revision_id="entity-revision:initech:v1",
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, contender_fence, contender)
    before = tuple(plane.list_records())

    with pytest.raises((PreplanningStoreError, ProjectionHistoryError, ValueError)):
        service.persist(
            fence=contender_fence,
            terminal=contender,
            authorization_verifier=AUTHORIZATION,
        )

    assert tuple(plane.list_records()) == before
