"""Provider-oriented memory service for Hermes-style hooks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast

from memorii.core.decision_state.service import DecisionStateService
from memorii.core.decision_state.summary import DecisionStateSummary
from memorii.core.llm_decision.trace import LLMDecisionTraceStore
from memorii.core.memory_evolution import (
    GraphAuditRequest,
    MemoryEvolutionResult,
    MemoryEvolutionService,
    MemoryExtractor,
    MemoryQueryRequest,
    MemoryScope,
    ProductionRetrievalDecision,
    QueryAnalyzer,
    QueryTemporalKind,
    RetrievalPurpose,
    RetrievalView,
)
from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
    SemanticIngestionOutcomeLookupRequest,
    SemanticIngestionOutcomeLookupResponse,
    source_admission_source_bytes,
)
from memorii.core.memory_evolution.atomic_store import (
    PreplanningOperationMismatchError,
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapProfileVerificationError,
    HostBootstrapCapability,
    HostBootstrapMaterialVerifier,
    InstalledHostBootstrapCapabilityProvider,
    VerifiedBootstrapProfile,
    verify_bootstrap_profile,
)
from memorii.core.memory_evolution.conflict_attention import (
    AuthorizedUserEventProof,
    ClarificationSubmissionOutcome,
    ConflictAccessContext,
    ConflictAttentionObservabilityEvent,
    ConflictAttentionObservabilitySink,
    ConflictAttentionPage,
    ConflictClarificationSemanticPipeline,
    ConflictClarificationSubmissionResult,
    ConflictKind,
    ConflictListRequest,
    ConflictListRequestError,
    ConflictResolutionRequest,
    ConflictResolutionRequestError,
    ConflictStatus,
    SourceUserEventVerifier,
    UserConfirmationReceiptVerifier,
    UserConfirmationVerificationContext,
    VerifiedUserConfirmation,
    build_agent_clarification_proposal,
    conflict_resolution_request_digest,
    parse_conflict_list_request,
    parse_conflict_resolution_request,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    AtomicStoreConflictClarificationProcessingRepository,
    ConflictAttentionReadError,
    ConflictAttentionRepository,
    ConflictClarificationError,
    ConflictClarificationProcessor,
    FileConflictAttentionRepository,
)
from memorii.core.memory_evolution.conflict_integrity import (
    FileConflictIntegrityRepository,
    PrivilegedSemanticIntegrityLifecycle,
)
from memorii.core.memory_evolution.identity_lineage import (
    IdentityLineageAuditScopeSnapshot,
    IdentityLineageAuditView,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    AuthenticatedIngressContextResolver,
    AuthenticatedIngressResolutionError,
    DeliveryIdentity,
)
from memorii.core.memory_evolution.operation_store import (
    EvolutionOperationRepository,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
    writer_admission_memory_id,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.next_step import NextStepEngine
from memorii.core.promotion.provider import PromotionAssessmentProvider
from memorii.core.promotion.rule_provider import RuleBasedPromotionAssessmentProvider
from memorii.core.provider.attention_models import (
    ProviderPrefetchAttentionEnvelope,
    ProviderToolAttentionEnvelope,
)
from memorii.core.provider.classifier import make_event
from memorii.core.provider.ingestion import ProviderIngestionCoordinator
from memorii.core.provider.models import (
    ProviderEvent,
    ProviderEvolutionOutcome,
    ProviderOperation,
    ProviderPrefetchResult,
    ProviderStoredRecord,
    ProviderSyncResult,
    ProviderWriteDecision,
    RetrievalChannelAuthority,
    RetrievalChannelResult,
    RetrievalChannelStatus,
)
from memorii.core.provider.retrieval_composition import (
    arbitrate_retrieval_channels,
    build_evolution_channel_result,
    format_evolution_claim_decision,
    format_evolution_execution_decision,
)
from memorii.core.provider.tool_dispatch import ProviderToolDispatcher
from memorii.core.provider.tool_schemas import provider_tool_schemas, provider_tool_schemas_with_attention
from memorii.core.provider.tools import ProviderToolCallResult
from memorii.core.provider.work_state_projection import WorkStateMemoryProjector
from memorii.core.recall import RecallStateBundle, WorkStateSummary, summarize_work_states
from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphHostBundleBuilder
from memorii.core.semantic_ingestion.canonical_evidence_arena import (
    CanonicalEvidenceArena,
    RetainingCanonicalClosureObservabilityDispatcher,
)
from memorii.core.semantic_ingestion.capability import (
    AuthorizedSemanticIngestionRuntime,
    BuiltInLocalHostSemanticIngestionCapability,
    HostSemanticIngestionRuntimeBuilder,
)
from memorii.core.semantic_ingestion.production_authority import (
    VerifiedProductionHostAuthority,
    verified_production_authority_inputs,
)
from memorii.core.semantic_ingestion.source_normalization_host import (
    SourceNormalizationHostBundleBuilder,
)
from memorii.core.solver.frontier import SolverFrontierPlanner
from memorii.core.work_state.models import WorkStateKind, WorkStateRecord, WorkStateStatus
from memorii.core.work_state.selector import WorkStateSelector
from memorii.core.work_state.service import WorkStateService
from memorii.domain.enums import SourceModality
from memorii.stores.base.interfaces import OverlayStore, SolverGraphStore


class ScopedIdentityLineageAuditReader(Protocol):
    def read_identity_lineage(
        self,
        *,
        request: GraphAuditRequest,
        scope: IdentityLineageAuditScopeSnapshot,
        system_time: datetime | None = None,
    ) -> IdentityLineageAuditView: ...


class IdentityLineageAuditAuthorizer(Protocol):
    def authorize_identity_lineage_audit(
        self,
        *,
        ingress: AuthenticatedIngressContext,
        request: GraphAuditRequest,
        server_time: datetime,
    ) -> IdentityLineageAuditScopeSnapshot | None: ...


class ProviderMemoryService:
    """Thin provider adapter over the canonical MemoryPlaneService."""

    _DEFAULT_DECISION_STATE_SERVICE = object()
    _DEFAULT_PROMOTION_DECISION_PROVIDER = object()
    _SCENARIO_TEST_CONSTRUCTION = object()

    @classmethod
    def _from_scenario_test_host(
        cls,
        *,
        host_bootstrap_capability: HostBootstrapCapability,
        host_bootstrap_material_verifier: HostBootstrapMaterialVerifier,
        bootstrap_graph_host_bundle_builder: BootstrapGraphHostBundleBuilder | None = None,
        **kwargs: object,
    ) -> ProviderMemoryService:
        """Private fixture composition path; ordinary construction is production-only."""
        if bootstrap_graph_host_bundle_builder is not None:
            if not isinstance(
                host_bootstrap_capability,
                BuiltInLocalHostSemanticIngestionCapability,
            ):
                raise ValueError(
                    "scenario graph host bundle requires the built-in local capability"
                )
            host_bootstrap_capability = replace(
                host_bootstrap_capability,
                bootstrap_graph_host_bundle_builder=(
                    bootstrap_graph_host_bundle_builder
                ),
            )
        return cls(
            host_bootstrap_capability=host_bootstrap_capability,
            host_bootstrap_material_verifier=host_bootstrap_material_verifier,
            _host_construction=cls._SCENARIO_TEST_CONSTRUCTION,
            **kwargs,
        )

    def __init__(
        self,
        memory_plane: MemoryPlaneService | None = None,
        work_state_service: WorkStateService | None = None,
        decision_state_service: DecisionStateService | None | object = _DEFAULT_DECISION_STATE_SERVICE,
        promotion_decision_provider: PromotionAssessmentProvider | None | object = _DEFAULT_PROMOTION_DECISION_PROVIDER,
        llm_decision_trace_store: LLMDecisionTraceStore | None = None,
        solver_frontier_planner: SolverFrontierPlanner | None = None,
        solver_store: SolverGraphStore | None = None,
        overlay_store: OverlayStore | None = None,
        emit_work_state_event_candidates: bool = True,
        memory_evolution_extractor: MemoryExtractor | None = None,
        memory_evolution_query_analyzer: QueryAnalyzer | None = None,
        memory_evolution_operation_repository: EvolutionOperationRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
        conflict_attention_repository: ConflictAttentionRepository | None = None,
        conflict_attention_enabled: bool = False,
        conflict_attention_observability_sink: ConflictAttentionObservabilitySink
        | None = None,
        authenticated_ingress_resolver: AuthenticatedIngressContextResolver | None = None,
        source_user_event_verifier: SourceUserEventVerifier | None = None,
        user_confirmation_receipt_verifier: UserConfirmationReceiptVerifier | None = None,
        conflict_clarification_pipeline: ConflictClarificationSemanticPipeline | None = None,
        semantic_integrity_lifecycle: PrivilegedSemanticIntegrityLifecycle
        | None = None,
        semantic_integrity_root: Path | None = None,
        identity_lineage_audit_reader: ScopedIdentityLineageAuditReader | None = None,
        identity_lineage_audit_authorizer: IdentityLineageAuditAuthorizer | None = None,
        host_bootstrap_capability: HostBootstrapCapability | None = None,
        host_bootstrap_material_verifier: HostBootstrapMaterialVerifier | None = None,
        source_normalization_host_bundle_builder: SourceNormalizationHostBundleBuilder | None = None,
        verified_production_host_authority: VerifiedProductionHostAuthority | None = None,
        canonical_evidence_enabled: bool | None = None,
        _host_construction: object | None = None,
    ) -> None:
        self._memory_plane = memory_plane or MemoryPlaneService()
        self._canonical_evidence_requested = canonical_evidence_enabled
        verified_material = None
        verified_ingress_resolver = None
        if verified_production_host_authority is not None:
            if any(
                value is not None
                for value in (
                    authenticated_ingress_resolver,
                    host_bootstrap_capability,
                    host_bootstrap_material_verifier,
                    source_normalization_host_bundle_builder,
                )
            ) or _host_construction is not None:
                raise ValueError(
                    "verified production host authority rejects legacy authority injection"
                )
            (
                host_bootstrap_capability,
                verified_material,
                verified_ingress_resolver,
            ) = verified_production_authority_inputs(
                verified_production_host_authority
            )
        elif host_bootstrap_capability is None:
            capability_provider = InstalledHostBootstrapCapabilityProvider()
            try:
                host_bootstrap_capability = capability_provider.load()
            except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                host_bootstrap_capability = None
        if source_normalization_host_bundle_builder is not None:
            if not isinstance(host_bootstrap_capability, BuiltInLocalHostSemanticIngestionCapability):
                raise ValueError("source normalization host bundle requires the built-in local host capability")
            if host_bootstrap_capability.source_normalization_host_bundle_builder is not None:
                raise ValueError("source normalization host bundle is already configured")
            host_bootstrap_capability = replace(
                host_bootstrap_capability,
                source_normalization_host_bundle_builder=source_normalization_host_bundle_builder,
            )
        if (
            isinstance(
                host_bootstrap_capability,
                BuiltInLocalHostSemanticIngestionCapability,
            )
            and host_bootstrap_capability.bootstrap_graph_host_bundle_builder
            is not None
            and _host_construction is not self._SCENARIO_TEST_CONSTRUCTION
        ):
            raise ValueError(
                "bootstrap graph host injection is restricted to the scenario-test harness"
            )
        if (
            verified_production_host_authority is None
            and (
            host_bootstrap_capability is not None
            and host_bootstrap_material_verifier is not None
            )
        ):
            try:
                presentation = host_bootstrap_capability.load_bootstrap_material_presentation()
                verified_material = (
                    host_bootstrap_material_verifier.verify(
                        presentation=presentation,
                        required_trust_domain=(
                            "scenario_test"
                            if _host_construction is self._SCENARIO_TEST_CONSTRUCTION
                            else "production"
                        ),
                        server_time=(now_provider or (lambda: datetime.now(UTC)))(),
                    )
                    if presentation is not None
                    else None
                )
            except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                verified_material = None
        required_domain = (
            "scenario_test"
            if _host_construction is self._SCENARIO_TEST_CONSTRUCTION
            else "production"
        )
        if (
            verified_material is not None
            and (
                verified_material.trust_domain != required_domain
                or verified_material.release_evidence.trust_domain != required_domain
            )
        ):
            verified_material = None
        self._canonical_evidence_enabled = False
        self._canonical_closure_dispatcher = RetainingCanonicalClosureObservabilityDispatcher()
        self._authenticated_ingress_resolver = None
        self._bootstrap_profile: VerifiedBootstrapProfile | None = None
        self._bootstrap_unavailable_reason = "invalid_config"
        if verified_material is not None:
            self._authenticated_ingress_resolver = (
                verified_ingress_resolver
                if verified_ingress_resolver is not None
                else cast(
                    AuthenticatedIngressContextResolver,
                    verified_material.authenticated_ingress_resolver,
                )
            )
            try:
                self._bootstrap_profile = verify_bootstrap_profile(verified_material)
                # The canonical-evidence substitution is the default for every
                # verified runtime; an explicit request is the only way off
                # (parity proofs and rollback).
                self._canonical_evidence_enabled = (
                    True
                    if self._canonical_evidence_requested is None
                    else self._canonical_evidence_requested
                )
            except BootstrapProfileVerificationError as exc:
                self._bootstrap_profile = None
                self._bootstrap_unavailable_reason = exc.reason.value
            except ValueError:
                self._bootstrap_profile = None
                self._bootstrap_unavailable_reason = "invalid_manifest"
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        if conflict_attention_enabled and conflict_attention_repository is None:
            raise ValueError("conflict attention is enabled without a repository")
        self._conflict_attention_repository = conflict_attention_repository
        self._conflict_attention_enabled = conflict_attention_enabled
        self._conflict_attention_observability_sink = (
            conflict_attention_observability_sink
        )
        self._identity_lineage_audit_reader = identity_lineage_audit_reader
        self._identity_lineage_audit_authorizer = identity_lineage_audit_authorizer
        self._source_user_event_verifier = source_user_event_verifier
        self._user_confirmation_receipt_verifier = user_confirmation_receipt_verifier
        if semantic_integrity_lifecycle is not None and semantic_integrity_root is not None:
            raise ValueError("semantic integrity lifecycle and root are mutually exclusive")
        if (
            semantic_integrity_lifecycle is not None
            and semantic_integrity_lifecycle.repository_id != "semantic_ingestion"
        ):
            raise ValueError(
                "semantic integrity lifecycle does not bind the provider event authority"
            )
        if authenticated_ingress_resolver is not None:
            self._authenticated_ingress_resolver = authenticated_ingress_resolver
        if semantic_integrity_lifecycle is None and semantic_integrity_root is not None:
            integrity_repository = FileConflictIntegrityRepository(
                semantic_integrity_root / "integrity.jsonl",
                repository_id="semantic_ingestion",
                snapshot_provider=lambda: self._semantic_atomic_store.semantic_integrity_snapshot(),
                clean_replay_verifier=(
                    lambda repaired, retained, authority: self._semantic_atomic_store.prepare_semantic_clean_recovery(
                        repaired,
                        retained,
                        authority,
                    )
                ),
                now_provider=self._now_provider,
            )
            semantic_integrity_lifecycle = PrivilegedSemanticIntegrityLifecycle(
                integrity_repository,
                attention_repository=(
                    conflict_attention_repository
                    if isinstance(conflict_attention_repository, FileConflictAttentionRepository)
                    else None
                ),
                clean_recovery_request_retainer=(
                    lambda request: self._semantic_atomic_store.retain_semantic_clean_recovery_request(request)
                ),
                clean_recovery_activator=(
                    lambda request: self._semantic_atomic_store.activate_semantic_clean_recovery(request)
                ),
                clean_recovery_reconciler=(
                    lambda released: self._semantic_atomic_store.reconcile_semantic_clean_recovery(released)
                ),
            )
        semantic_runtime: AuthorizedSemanticIngestionRuntime | None = None
        runtime_builder = cast(
            HostSemanticIngestionRuntimeBuilder | None, host_bootstrap_capability
        )
        if (
            self._bootstrap_profile is not None
            and runtime_builder is not None
            and hasattr(runtime_builder, "build_semantic_ingestion_runtime")
        ):
            try:
                if isinstance(
                    host_bootstrap_capability,
                    BuiltInLocalHostSemanticIngestionCapability,
                ) and verified_material is not None:
                    semantic_runtime = (
                        host_bootstrap_capability.build_semantic_ingestion_runtime(
                        memory_plane=self._memory_plane,
                        now_provider=self._now_provider,
                        bootstrap_profile=self._bootstrap_profile,
                        verified_material=verified_material,
                        semantic_integrity_lifecycle=semantic_integrity_lifecycle,
                        )
                    )
                else:
                    semantic_runtime = runtime_builder.build_semantic_ingestion_runtime(
                        memory_plane=self._memory_plane,
                        now_provider=self._now_provider,
                        bootstrap_profile=self._bootstrap_profile,
                    )
            except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                semantic_runtime = None
        # Post-ingress runtime validation reads this stored composition
        # reference instead of reaching into the coordinator's privates.
        self._composed_semantic_runtime = semantic_runtime
        self._work_state_service = work_state_service
        self._work_state_selector = WorkStateSelector(work_state_service)
        self._solver_frontier_planner = solver_frontier_planner
        self._solver_store = solver_store
        self._overlay_store = overlay_store
        if decision_state_service is self._DEFAULT_DECISION_STATE_SERVICE:
            self._decision_state_service: DecisionStateService | None = DecisionStateService()
        else:
            self._decision_state_service = cast(DecisionStateService | None, decision_state_service)
        if promotion_decision_provider is self._DEFAULT_PROMOTION_DECISION_PROVIDER:
            self._promotion_decision_provider: PromotionAssessmentProvider | None = (
                RuleBasedPromotionAssessmentProvider()
            )
        else:
            self._promotion_decision_provider = cast(PromotionAssessmentProvider | None, promotion_decision_provider)
        self._llm_decision_trace_store = llm_decision_trace_store
        self._next_step_engine = NextStepEngine(
            work_state_service=work_state_service,
            decision_state_service=self._decision_state_service,
            solver_frontier_planner=solver_frontier_planner,
            solver_store=solver_store,
            overlay_store=overlay_store,
        )
        self._emit_work_state_event_candidates = emit_work_state_event_candidates
        self._memory_evolution_service: MemoryEvolutionService | None = None
        self._semantic_ingestion_admission = GovernedSourceAdmissionService(self._memory_plane)
        runtime_writer = semantic_runtime.writer_admission if semantic_runtime is not None else None
        runtime_store = semantic_runtime.atomic_store if semantic_runtime is not None else None
        # Runtime composition may provide the canonical store, but durable
        # admission initialization is always deferred to resolved ingress.
        self._owns_writer_admission_record = True
        self._writer_admission_record_initialized = False
        if runtime_writer is None:
            self._semantic_writer_admission = SemanticWriterAdmissionStore(
                self._memory_plane, bounded_preplanning_ownership_manifest(), now_provider=self._now_provider
            )
        else:
            # Active semantic composition is explicit: the host supplies the
            # canonical writer owner. Its durable admission is validated only
            # after authenticated ingress, never during construction.
            self._semantic_writer_admission = runtime_writer
        self._semantic_integrity_lifecycle = semantic_integrity_lifecycle
        integrity_attention_publisher: Callable[[str, datetime], None] | None = None
        if isinstance(conflict_attention_repository, FileConflictAttentionRepository):
            def publish_integrity_attention(digest: str, recorded_at: datetime) -> None:
                conflict_attention_repository.append_sanitized_storage_integrity_incident(
                    repository_id="semantic_ingestion",
                    incident_evidence_digest=digest,
                    frozen_scope_ids=("global",),
                    recorded_at=recorded_at,
                )

            integrity_attention_publisher = publish_integrity_attention
        self._semantic_atomic_store = runtime_store or SemanticIngestionAtomicStore(
            self._memory_plane,
            self._semantic_writer_admission,
            now_provider=self._now_provider,
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
            semantic_integrity_attention_publisher=integrity_attention_publisher,
            semantic_integrity_linearization=(
                semantic_integrity_lifecycle.linearization
                if semantic_integrity_lifecycle is not None
                else None
            ),
        )
        if (
            runtime_store is not None
            and semantic_integrity_lifecycle is not None
            and runtime_store.semantic_integrity_linearization
            is not semantic_integrity_lifecycle.linearization
        ):
            raise ValueError(
                "semantic runtime store and integrity lifecycle are not linearized together"
            )
        if semantic_integrity_lifecycle is not None:
            semantic_integrity_lifecycle.reconcile_pending_recovery()
        self._provider_ingestion = ProviderIngestionCoordinator(
            memory_plane=self._memory_plane,
            admission_service=self._semantic_ingestion_admission,
            bootstrap_profile=self._bootstrap_profile,
            bootstrap_unavailable_reason=self._bootstrap_unavailable_reason,
            atomic_store=self._semantic_atomic_store,
            writer_admission=self._semantic_writer_admission,
            semantic_policy_provider=semantic_runtime.policy_provider if semantic_runtime is not None else None,
            semantic_runtime=semantic_runtime,
            now_provider=self._now_provider,
            canonical_evidence_arena_factory=self._new_canonical_evidence_arena,
        )
        self._semantic_runtime_validated_after_ingress = False
        self._conflict_clarification_processor: ConflictClarificationProcessor | None = None
        if self._conflict_attention_enabled and conflict_clarification_pipeline is not None:
            # Clarification processing requires an explicitly supplied host
            # pipeline; without one, submitted clarifications stay pending.
            self._conflict_clarification_processor = ConflictClarificationProcessor(
                AtomicStoreConflictClarificationProcessingRepository(
                    self._semantic_atomic_store
                ),
                conflict_clarification_pipeline,
            )
        self._work_state_memory_projector = WorkStateMemoryProjector(
            memory_plane=self._memory_plane,
            work_state_service=self._work_state_service,
            promotion_provider=self._promotion_decision_provider,
            trace_store=self._llm_decision_trace_store,
            emit_candidates=self._emit_work_state_event_candidates,
        )
        self._tool_dispatcher = ProviderToolDispatcher(
            decision_state_service=self._decision_state_service,
            work_state_service=self._work_state_service,
            work_state_selector=self._work_state_selector,
            next_step_engine=self._next_step_engine,
            work_state_memory_projector=self._work_state_memory_projector,
        )
        self._last_memory_evolution_result: MemoryEvolutionResult | None = None
        self._last_recall_bundle: RecallStateBundle | None = None
        self._last_prefetch_result: ProviderPrefetchResult[ProductionRetrievalDecision] | None = None

    def _ensure_writer_admission_record(self) -> None:
        if not self._owns_writer_admission_record:
            return
        if self._writer_admission_record_initialized:
            return
        # A profile-less reopened service owns no replacement identity.  An
        # existing durable record is authoritative only after `current()`
        # revalidates its closed admission and ownership manifest.
        if self._memory_plane.get_record(writer_admission_memory_id()) is not None:
            self._semantic_writer_admission.current()
            self._writer_admission_record_initialized = True
            return
        self._semantic_writer_admission.create_initial_evidence_only(
            admission_id="memorii-provider-semantic-writer-v1",
            writer_implementation_fingerprint="memorii-provider-semantic-evidence-only-v1",
            graph_schema_fingerprint="memorii-semantic-graph-preactivation-v1",
        )
        self._writer_admission_record_initialized = True

    def _new_canonical_evidence_arena(self) -> CanonicalEvidenceArena:
        """Create one private owner per provider invocation or recovery item."""
        return CanonicalEvidenceArena(
            enabled=self._canonical_evidence_enabled,
            observability_dispatcher=self._canonical_closure_dispatcher,
        )

    def sync_event(
        self,
        *,
        operation: ProviderOperation,
        content: str,
        operation_id: str,
        role: str | None = None,
        target: str | None = None,
        action: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        language: str = "en",
        speaker_id: str | None = None,
        timestamp: datetime | None = None,
        source_modality: SourceModality | None = None,
        authenticated_host_ingress: AuthenticatedHostIngress | None = None,
    ) -> ProviderSyncResult:
        with CanonicalEvidenceArena(enabled=self._canonical_evidence_enabled, observability_dispatcher=self._canonical_closure_dispatcher) as canonical_evidence_arena:
            event = make_event(
                event_id=operation_id,
                operation=operation,
                content=content,
                role=role,
                target=target,
                action=action,
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
                language=language,
                speaker_id=speaker_id,
                timestamp=timestamp or self._now_provider(),
                source_modality=source_modality,
            )
            return self._ingest_event(
                event,
                authenticated_host_ingress=authenticated_host_ingress,
                canonical_evidence_arena=canonical_evidence_arena,
            )

    def _sync_composite_event(
        self,
        *,
        operation: ProviderOperation,
        content: str,
        composite_operation_id: str,
        role: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        authenticated_host_ingress: AuthenticatedHostIngress | None = None,
    ) -> ProviderSyncResult:
        """Internal-only typed composite coordinate path used by Hermes fan-out."""

        if not composite_operation_id.startswith("composite:v1:"):
            raise ValueError("internal composite event requires a composite coordinate")
        # This path is not exposed through ProviderEvent validation or any
        # caller-selectable API.  The adapter obtains the value only from the
        # canonical domain-separated coordinate constructor.
        event = ProviderEvent.model_construct(
            event_id=composite_operation_id,
            operation=operation,
            content=content,
            role=role,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            language="en",
            timestamp=self._now_provider(),
        )
        with CanonicalEvidenceArena(enabled=self._canonical_evidence_enabled, observability_dispatcher=self._canonical_closure_dispatcher) as canonical_evidence_arena:
            return self._ingest_event(
                event,
                authenticated_host_ingress=authenticated_host_ingress,
                canonical_evidence_arena=canonical_evidence_arena,
            )

    def _ingest_event(
        self,
        event: ProviderEvent,
        *,
        authenticated_host_ingress: AuthenticatedHostIngress | None,
        canonical_evidence_arena: CanonicalEvidenceArena,
    ) -> ProviderSyncResult:
        ingress = self._preflight_ingress(authenticated_host_ingress)
        result, _, evolution_result = self._provider_ingestion.ingest(
            event,
            defer_assertions=event.operation
            in {
                ProviderOperation.CHAT_USER_TURN,
                ProviderOperation.CHAT_ASSISTANT_TURN,
            },
            authenticated_ingress=ingress,
            canonical_evidence_arena=canonical_evidence_arena,
        )
        self._last_memory_evolution_result = evolution_result
        return result

    def _resolve_ingress(self, host_ingress: AuthenticatedHostIngress | None):
        if host_ingress is None or self._authenticated_ingress_resolver is None:
            return None
        try:
            return self._authenticated_ingress_resolver.resolve(host_ingress, self._now_provider())
        except AuthenticatedIngressResolutionError:
            return None

    def _preflight_ingress(self, host_ingress: AuthenticatedHostIngress | None):
        """Resolve ingress before the sole durable writer-admission boundary."""
        ingress = self._resolve_ingress(host_ingress)
        if ingress is not None:
            self._ensure_writer_admission_record()
            self._validate_semantic_runtime_after_ingress()
        return ingress

    def _validate_semantic_runtime_after_ingress(self) -> None:
        if self._semantic_runtime_validated_after_ingress:
            return
        runtime = self._composed_semantic_runtime
        if runtime is None or self._bootstrap_profile is None:
            return
        runtime.validate(profile=self._bootstrap_profile, server_time=self._now_provider())
        self._semantic_runtime_validated_after_ingress = True

    def lookup_semantic_ingestion_outcome(
        self,
        request: SemanticIngestionOutcomeLookupRequest,
        *,
        authenticated_host_ingress: AuthenticatedHostIngress,
    ) -> SemanticIngestionOutcomeLookupResponse:
        """Use the sole authenticated, intentionally non-disclosing result path."""

        ingress = self._resolve_ingress(authenticated_host_ingress)
        if ingress is None:
            return SemanticIngestionOutcomeLookupResponse()
        return self._semantic_ingestion_admission.lookup(request, authenticated_ingress=ingress)

    @property
    def memory_evolution_service(self) -> MemoryEvolutionService:
        """Return the runtime evolution service used by provider operations."""
        if self._memory_evolution_service is None:
            raise RuntimeError(
                "memory evolution is unavailable in the governed-source admission source-only configuration"
            )
        return self._memory_evolution_service

    @property
    def semantic_integrity_lifecycle(self) -> PrivilegedSemanticIntegrityLifecycle:
        """Return the host-owned privileged repair/release boundary."""

        if self._semantic_integrity_lifecycle is None:
            raise RuntimeError("semantic integrity recovery is unavailable")
        return self._semantic_integrity_lifecycle

    def retrieve_evolution_decision(
        self,
        request: MemoryQueryRequest,
    ) -> ProductionRetrievalDecision:
        """Return the structured evolution decision without rendering it.

        Provider integrations that need machine-readable retrieval context can
        consume this typed decision directly.  Text rendering remains an
        adapter concern in :meth:`prefetch`.
        """

        return self.memory_evolution_service.retrieve(request)

    def read_identity_lineage(
        self,
        request: GraphAuditRequest,
        *,
        authenticated_host_ingress: AuthenticatedHostIngress,
        system_time: datetime | None = None,
    ) -> IdentityLineageAuditView:
        """Return typed lineage only through the explicit graph-audit surface."""

        # Resolve and authorize before consulting the lineage reader. Every
        # denial intentionally has the same non-disclosing result.
        ingress = self._resolve_ingress(authenticated_host_ingress)
        authorizer = self._identity_lineage_audit_authorizer
        now = self._now_provider()
        scope = (
            authorizer.authorize_identity_lineage_audit(
                ingress=ingress,
                request=request,
                server_time=now,
            )
            if request.purpose == RetrievalPurpose.GRAPH_AUDIT
            and ingress is not None
            and authorizer is not None
            else None
        )
        if scope is None or self._identity_lineage_audit_reader is None:
            raise ValueError("identity_lineage_audit_denied")
        scope.require_current(now)
        final_ingress = self._resolve_ingress(authenticated_host_ingress)
        final_now = self._now_provider()
        final_scope = (
            authorizer.authorize_identity_lineage_audit(
                ingress=final_ingress,
                request=request,
                server_time=final_now,
            )
            if final_ingress is not None and authorizer is not None
            else None
        )
        if (
            final_scope is None
            or final_scope.tenant_partition_id != scope.tenant_partition_id
            or final_scope.principal_binding_digest
            != scope.principal_binding_digest
            or final_scope.authorized_scope_ids != scope.authorized_scope_ids
            or final_scope.scope_mode != scope.scope_mode
        ):
            raise ValueError("identity_lineage_audit_denied")
        final_scope.require_current(final_now)
        return self._identity_lineage_audit_reader.read_identity_lineage(
            request=request,
            scope=final_scope,
            system_time=system_time,
        )

    def apply_memory_write(
        self,
        *,
        operation: ProviderOperation,
        content: str,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        action: str,
        target: str,
        operation_id: str,
        language: str = "en",
        timestamp: datetime | None = None,
        source_modality: SourceModality | None = None,
        authenticated_host_ingress: AuthenticatedHostIngress | None = None,
    ) -> ProviderWriteDecision:
        event = make_event(
            event_id=operation_id,
            operation=operation,
            content=content,
            action=action,
            target=target,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            language=language,
            timestamp=timestamp or self._now_provider(),
            source_modality=source_modality,
        )
        with CanonicalEvidenceArena(enabled=self._canonical_evidence_enabled, observability_dispatcher=self._canonical_closure_dispatcher) as canonical_evidence_arena:
            sync_result, _, evolution_result = self._provider_ingestion.ingest(
                event,
                authenticated_ingress=self._preflight_ingress(authenticated_host_ingress),
                canonical_evidence_arena=canonical_evidence_arena,
            )
        self._last_memory_evolution_result = evolution_result
        decision = ProviderWriteDecision(
            blocked_domains=sync_result.blocked_domains,
            allowed_candidate_domains=sync_result.allowed_candidate_domains,
            committed_domains=[],
            blocked_reasons=sync_result.blocked_reasons,
            candidate_ids=sync_result.candidate_ids,
            raw_append_domains=sync_result.raw_append_domains,
            blocked_commit_domains=sync_result.blocked_commit_domains,
            evolution_outcomes=list(sync_result.evolution_outcomes),
        )
        return decision

    def prefetch(
        self,
        query: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        top_k: int = 6,
        query_language: str = "en",
        reference_time: datetime | None = None,
        purpose: RetrievalPurpose = RetrievalPurpose.ANSWER,
        include_context: bool = False,
        include_conflicts: bool = False,
    ) -> str:
        return self.prefetch_result(
            query,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            top_k=top_k,
            query_language=query_language,
            reference_time=reference_time,
            purpose=purpose,
            include_context=include_context,
            include_conflicts=include_conflicts,
        ).context

    def prefetch_result(
        self,
        query: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        top_k: int = 6,
        query_language: str = "en",
        reference_time: datetime | None = None,
        purpose: RetrievalPurpose = RetrievalPurpose.ANSWER,
        include_context: bool = False,
        include_conflicts: bool = False,
    ) -> ProviderPrefetchResult[ProductionRetrievalDecision]:
        """Return final context together with inspectable channel arbitration."""

        memory_context = self._memory_plane.prefetch_provider_context(
            query,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            top_k=top_k,
        )
        evolution_context, evolution_decision = self._format_evolution_retrieval(
            query=query,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            top_k=top_k,
            query_language=query_language,
            reference_time=reference_time or self._now_provider(),
            purpose=purpose,
            include_context=include_context,
            include_conflicts=include_conflicts,
        )
        canonical_trace = self._memory_plane.last_provider_prefetch_trace()
        canonical_ids = (
            [item.memory_id for item in canonical_trace.ranked_items[:top_k]] if canonical_trace is not None else []
        )
        canonical_records = [
            record for record_id in canonical_ids if (record := self._memory_plane.get_record(record_id)) is not None
        ]
        canonical_is_authoritative = any(not record.is_raw_event for record in canonical_records)
        canonical_channel = RetrievalChannelResult(
            channel="canonical",
            status=(RetrievalChannelStatus.ANSWER if canonical_ids else RetrievalChannelStatus.NO_MATCH),
            authority=(
                RetrievalChannelAuthority.AUTHORITATIVE
                if canonical_is_authoritative
                else RetrievalChannelAuthority.SUPPLEMENTAL
                if canonical_ids
                else RetrievalChannelAuthority.NONE
            ),
            context=memory_context,
            selected_record_ids=canonical_ids,
            reason=None if canonical_ids else "no_canonical_records_matched",
        )
        evolution_channel = build_evolution_channel_result(
            context=evolution_context,
            decision=evolution_decision,
        )
        selected_channel, memory_context = arbitrate_retrieval_channels(
            canonical=canonical_channel,
            evolution=evolution_channel,
        )
        has_execution_selection = (
            evolution_decision is not None
            and evolution_decision.temporal_frame.temporal_kind == QueryTemporalKind.EXECUTION
            and not evolution_decision.abstained
            and bool(evolution_decision.selected_record_ids)
        )
        selected_work_states = (
            []
            if has_execution_selection
            else self._work_state_selector.select_recall_work_states(
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
            )
        )
        work_state_summaries = summarize_work_states(
            selected_work_states,
            events_by_state_id=self._tool_dispatcher.list_events_by_work_state_id(selected_work_states),
            decision_summary_by_state_id=self._tool_dispatcher.decision_summary_by_work_state_id(selected_work_states),
        )
        bundle = RecallStateBundle(
            query=query,
            memory_context=memory_context,
            work_states=work_state_summaries,
            trace={
                "work_state_count": len(work_state_summaries),
                "work_state_ids": [state.work_state_id for state in work_state_summaries],
                "included_statuses": sorted({state.status.value for state in work_state_summaries}),
                "evolution_retrieval": (
                    evolution_decision.model_dump(mode="json") if evolution_decision is not None else None
                ),
                "retrieval_channels": {
                    "canonical": canonical_channel.model_dump(mode="json"),
                    "evolution": evolution_channel.model_dump(mode="json"),
                    "selected": selected_channel,
                },
            },
        )
        self._last_recall_bundle = bundle
        final_context = (
            memory_context
            if not work_state_summaries
            else f"{memory_context}\n\n{self._format_work_state_section(work_state_summaries[:3])}"
        )
        result = ProviderPrefetchResult[ProductionRetrievalDecision](
            context=final_context,
            selected_channel=selected_channel,
            canonical=canonical_channel,
            evolution=evolution_channel,
            evolution_decision=evolution_decision,
        )
        self._last_prefetch_result = result
        return result

    def _format_evolution_retrieval(
        self,
        *,
        query: str,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        top_k: int,
        query_language: str,
        reference_time: datetime,
        purpose: RetrievalPurpose,
        include_context: bool,
        include_conflicts: bool,
    ) -> tuple[str, ProductionRetrievalDecision | None]:
        """Render only the production evolution decision into provider context."""

        if self._memory_evolution_service is None:
            return "", None

        scope = MemoryScope(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
        )
        request: MemoryQueryRequest
        if purpose == RetrievalPurpose.GRAPH_AUDIT:
            request = GraphAuditRequest(
                query=query,
                query_language=query_language,
                reference_time=reference_time,
                scope=scope,
                top_k=top_k,
                include_context=include_context,
                include_conflicts=include_conflicts,
                purpose=purpose,
            )
        else:
            request = MemoryQueryRequest(
                query=query,
                query_language=query_language,
                reference_time=reference_time,
                scope=scope,
                top_k=top_k,
                include_context=include_context,
                include_conflicts=include_conflicts,
                purpose=purpose,
            )
        decision = self.retrieve_evolution_decision(request)
        if decision.abstained or not decision.selected_record_ids:
            if decision.temporal_frame.temporal_kind == QueryTemporalKind.EXECUTION:
                return (
                    "Evolution execution (production retrieval):\n"
                    f"- No active continuation branch selected ({decision.abstention_reason or 'abstained'}).",
                    decision,
                )
            return (
                "Evolution memory (production retrieval):\n"
                f"- No lifecycle-valid memory selected ({decision.abstention_reason or 'no_match'}).",
                decision,
            )
        if decision.temporal_frame.temporal_kind == QueryTemporalKind.EXECUTION:
            return format_evolution_execution_decision(decision), decision
        states = {
            state.claim_id: state
            for state in self.memory_evolution_service.retrieve_claim_states(
                view=RetrievalView.ALL_VERSIONS,
            )
        }
        return format_evolution_claim_decision(decision, states=states, top_k=top_k), decision

    def get_tool_schemas(self) -> list[dict[str, object]]:
        return provider_tool_schemas()

    def get_tool_schemas_with_attention(self) -> list[dict[str, object]]:
        return provider_tool_schemas_with_attention()

    def handle_tool_call(self, tool_name: str, arguments: dict[str, object]) -> ProviderToolCallResult:
        return self._tool_dispatcher.handle(tool_name, arguments)

    def prefetch_with_attention(
        self,
        query: str,
        *,
        authenticated_host_ingress: AuthenticatedHostIngress,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        query_language: str = "en",
        reference_time: datetime | None = None,
        defer_observability: bool = False,
    ) -> ProviderPrefetchAttentionEnvelope[ProductionRetrievalDecision]:
        legacy = self.prefetch_result(
            query,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            query_language=query_language,
            reference_time=reference_time,
        )
        access = self._conflict_access(authenticated_host_ingress)
        page = self._attention_page(access, ConflictListRequest(page_size=3))
        envelope = ProviderPrefetchAttentionEnvelope(
            legacy_result=legacy, attention_required=page
        )
        if not defer_observability:
            self.publish_conflict_attention_observability(page)
        return envelope

    def handle_tool_call_with_attention(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        authenticated_host_ingress: AuthenticatedHostIngress,
    ) -> ProviderToolAttentionEnvelope:
        ingress = self._resolve_ingress(authenticated_host_ingress)
        access = self._conflict_access_from_ingress(ingress)
        if tool_name == "memorii_list_conflicts":
            try:
                request = parse_conflict_list_request(arguments)
                page = self._attention_page(access, request, explicit=True)
                legacy = ProviderToolCallResult(tool_name=tool_name, ok=True, result=page.model_dump(mode="json"))
                self.publish_conflict_attention_observability(page)
            except (ConflictAttentionReadError, ConflictListRequestError) as exc:
                legacy = ProviderToolCallResult(tool_name=tool_name, ok=False, error=str(exc))
            # The complete page is the tool result. The embedded side channel remains capped at three.
            attention = ConflictAttentionPage(total_pending=0)
        elif tool_name == "memorii_resolve_conflict":
            try:
                request = parse_conflict_resolution_request(arguments)
                result = self._resolve_conflict(
                    access,
                    request,
                    authenticated_ingress=ingress,
                )
                legacy = ProviderToolCallResult(tool_name=tool_name, ok=True, result=result.model_dump(mode="json"))
            except (ConflictClarificationError, ConflictResolutionRequestError) as exc:
                legacy = ProviderToolCallResult(tool_name=tool_name, ok=False, error=str(exc))
            attention = ConflictAttentionPage(total_pending=0)
        else:
            legacy = self.handle_tool_call(tool_name, arguments)
            attention = self._attention_page(access, ConflictListRequest(page_size=3))
        envelope = ProviderToolAttentionEnvelope(
            legacy_result=legacy, attention_required=attention
        )
        if tool_name not in {
            "memorii_list_conflicts",
            "memorii_resolve_conflict",
        }:
            self.publish_conflict_attention_observability(attention)
        return envelope

    def publish_conflict_attention_observability(
        self, page: ConflictAttentionPage
    ) -> None:
        """Emit only safe dimensions after a page or render succeeds."""

        sink = self._conflict_attention_observability_sink
        if sink is None:
            return
        for item in page.items:
            sink.emit_conflict_attention_event(
                ConflictAttentionObservabilityEvent(
                    conflict_id=item.conflict_id,
                    kind=item.kind,
                    status=item.status,
                    scope_digest=item.scope_digest,
                )
            )

    def _resolve_conflict(
        self,
        access: ConflictAccessContext | None,
        request: ConflictResolutionRequest,
        *,
        authenticated_ingress: AuthenticatedIngressContext | None,
    ) -> ConflictClarificationSubmissionResult:
        if not self._conflict_attention_enabled:
            raise ConflictClarificationError("conflict_attention_unavailable")
        if access is None:
            raise ConflictClarificationError("conflict_attention_authorization_required")
        # An integrity-kind attention may exist precisely because canonical
        # conflict state is corrupt or absent, so the attention repository is
        # consulted before any canonical lookup: operator action is the only
        # resolution path for detected storage corruption.  The file target is
        # kept: a conflict absent from canonical state resolves through the
        # attention ledger's display projection instead.
        file_target = None
        if self._conflict_attention_repository is not None:
            try:
                file_target = (
                    self._conflict_attention_repository.get_resolution_target(
                        access, request.conflict_id
                    )
                )
            except ConflictClarificationError:
                file_target = None
            if (
                file_target is not None
                and file_target.kind == ConflictKind.STORAGE_INTEGRITY
            ):
                raise ConflictClarificationError("operator_action_required")
        request_digest = conflict_resolution_request_digest(request)
        try:
            retained = self._semantic_atomic_store.canonical_clarification_operation_receipt(
                operation_id=request.operation_id, request_digest=request_digest
            )
            if retained is not None:
                self._semantic_atomic_store.authorize_canonical_conflict_scopes(
                    conflict_id=retained.conflict_id,
                    authorized_scope_ids=access.authorized_scope_ids,
                )
                return ConflictClarificationSubmissionResult(
                    outcome=ClarificationSubmissionOutcome.IDEMPOTENT,
                    operation_receipt=retained,
                )
            target = self._semantic_atomic_store.canonical_conflict_attention(request.conflict_id)
            if target is not None:
                self._semantic_atomic_store.authorize_canonical_conflict_scopes(
                    conflict_id=request.conflict_id,
                    authorized_scope_ids=access.authorized_scope_ids,
                )
        except PreplanningOperationMismatchError:
            raise ConflictClarificationError("conflict_operation_mismatch") from None
        except PreplanningStoreError:
            raise ConflictClarificationError("conflict_resolution_unavailable") from None
        if target is None:
            # Without canonical conflict state the attention ledger is the
            # only resolution authority; its submission is a display
            # projection that must never become canonical work.
            if file_target is None:
                raise ConflictClarificationError("conflict_resolution_unavailable")
        else:
            if target.kind == ConflictKind.STORAGE_INTEGRITY:
                raise ConflictClarificationError("operator_action_required")
            if target.status != ConflictStatus.OPEN or target.conflict_revision != request.expected_conflict_revision:
                return ConflictClarificationSubmissionResult(
                    outcome=ClarificationSubmissionOutcome.STALE_REVISION,
                    attention=target,
                )
            candidates = {option.candidate_id for option in target.options}
            if not set(request.selected_candidate_ids) <= candidates:
                raise ConflictClarificationError("invalid_conflict_resolution")
        verifier = self._source_user_event_verifier
        if verifier is None:
            raise ConflictClarificationError("source_user_event_verification_unavailable")
        if authenticated_ingress is None:
            raise ConflictClarificationError("invalid_source_user_event")
        source_record = self._memory_plane.get_record(
            f"tx:{request.source_user_event_id}"
        )
        if source_record is None:
            identity = DeliveryIdentity.create(
                authenticated_ingress.delivery_principal_binding,
                request.source_user_event_id,
            )
            source_record = self._memory_plane.get_record(
                f"semantic_ingestion:source:{identity.delivery_key_digest}"
            )
        if source_record is None:
            raise ConflictClarificationError("invalid_source_user_event")
        resolution_scope_digest = (
            target.scope_digest if target is not None else file_target.scope_digest
        )
        canonical_source_bytes = source_admission_source_bytes(source_record)
        try:
            source = verifier.verify_user_event(
                tenant_id=access.tenant_id,
                principal_id=access.principal_id,
                scope_digest=resolution_scope_digest,
                source_user_event_id=request.source_user_event_id,
            )
            source = AuthorizedUserEventProof.model_validate(
                source.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            raise ConflictClarificationError("invalid_source_user_event") from None
        if not isinstance(source, AuthorizedUserEventProof) or (
            source.tenant_id != access.tenant_id
            or source.principal_id != access.principal_id
            or source.scope_digest != resolution_scope_digest
            or source.source_user_event_id != request.source_user_event_id
            or source.source_user_event_digest
            != sha256(canonical_source_bytes).hexdigest()
            or source.canonical_source_bytes != canonical_source_bytes
        ):
            raise ConflictClarificationError("invalid_source_user_event")
        predecessor_record = None
        if target is not None:
            # The user event is the ANSWER's evidence; the canonical commit's
            # supersession discipline keys on the contested assertion's
            # source.  Bind the proposal to that predecessor so the accepted
            # answer commits at record version 2 over the predecessor's
            # version-1 assertion instead of fabricating a new record from a
            # non-asserting transcript event.
            try:
                (
                    predecessor_source_id,
                    predecessor_source_digest,
                ) = self._semantic_atomic_store.canonical_conflict_predecessor(
                    request.conflict_id
                )
            except PreplanningStoreError:
                raise ConflictClarificationError("conflict_resolution_unavailable") from None
            # The binding is already a full record id: candidate sources come
            # from admitted evidence, never the bare request vocabulary.
            predecessor_record = self._memory_plane.get_record(predecessor_source_id)
            if predecessor_record is None:
                raise ConflictClarificationError("conflict_resolution_unavailable")
            proposal = build_agent_clarification_proposal(
                request,
                source_user_event_digest=predecessor_source_digest,
                agent_principal_id=access.principal_id,
                scope_digest=target.scope_digest,
                predecessor_source_user_event_id=predecessor_source_id,
                answering_user_event_digest=source.source_user_event_digest,
            )
        else:
            proposal = build_agent_clarification_proposal(
                request,
                source_user_event_digest=source.source_user_event_digest,
                agent_principal_id=access.principal_id,
                scope_digest=file_target.scope_digest,
            )
        verified = None
        if request.user_confirmation_receipt is not None:
            receipt_verifier = self._user_confirmation_receipt_verifier
            if receipt_verifier is None:
                raise ConflictClarificationError("user_confirmation_verification_unavailable")
            expected = UserConfirmationVerificationContext(
                principal_id=access.principal_id,
                scope_digest=resolution_scope_digest,
                conflict_id=request.conflict_id,
                conflict_revision=request.expected_conflict_revision,
                action=request.action,
                request_digest=request_digest,
                source_user_event_id=request.source_user_event_id,
                source_user_event_digest=source.source_user_event_digest,
            )
            try:
                verification_time = self._now_provider()
                verified = receipt_verifier.verify(
                    request.user_confirmation_receipt,
                    expected=expected,
                    server_time=verification_time,
                )
                verified = VerifiedUserConfirmation.model_validate(
                    verified.model_dump(mode="python")
                )
                if (
                    verified.principal_id != expected.principal_id
                    or verified.scope_digest != expected.scope_digest
                    or verified.conflict_id != expected.conflict_id
                    or verified.conflict_revision != expected.conflict_revision
                    or verified.action != expected.action
                    or verified.request_digest != expected.request_digest
                    or verified.source_user_event_id
                    != expected.source_user_event_id
                    or verified.source_user_event_digest
                    != expected.source_user_event_digest
                    or verified.issued_at > verification_time
                    or verified.expires_at <= verification_time
                ):
                    raise ValueError("confirmation receipt binding mismatch")
            except (AttributeError, TypeError, ValueError):
                raise ConflictClarificationError("invalid_user_confirmation_receipt") from None
        if target is None:
            # File-only conflicts terminate at the display projection: no
            # retained context, no canonical generation, no claim work.
            return self._conflict_attention_repository.submit_clarification(
                access,
                request,
                request_digest,
                proposal,
                verified,
            )
        if self._conflict_clarification_processor is None:
            raise ConflictClarificationError("conflict_resolution_processing_unavailable")
        try:
            retained_context = (
                self._semantic_atomic_store.retain_conflict_clarification_context(
                    proposal=proposal,
                    authorized_source=source,
                    source_record=predecessor_record
                    if predecessor_record is not None
                    else source_record,
                    authenticated_ingress=authenticated_ingress,
                )
            )
        except (OSError, PreplanningStoreError):
            raise ConflictClarificationError(
                "conflict_resolution_processing_unavailable"
            ) from None
        if not retained_context:
            raise ConflictClarificationError("invalid_source_user_event")
        try:
            submitted = self._semantic_atomic_store.submit_canonical_conflict_clarification(
                request=request,
                request_digest=request_digest,
                proposal=proposal,
                verified_confirmation=verified,
            )
        except PreplanningOperationMismatchError:
            raise ConflictClarificationError("conflict_operation_mismatch") from None
        except PreplanningStoreError:
            raise ConflictClarificationError("conflict_resolution_unavailable") from None
        if submitted.outcome == ClarificationSubmissionOutcome.SUBMITTED:
            self.process_pending_conflict_clarifications(max_items=1)
        return submitted

    def _conflict_access(self, host_ingress: AuthenticatedHostIngress) -> ConflictAccessContext | None:
        return self._conflict_access_from_ingress(self._resolve_ingress(host_ingress))

    @staticmethod
    def _conflict_access_from_ingress(
        ingress: AuthenticatedIngressContext | None,
    ) -> ConflictAccessContext | None:
        if ingress is None:
            return None
        binding = ingress.delivery_principal_binding
        scopes = ingress.current_authorized_scopes
        if not scopes.scopes:
            return None
        return ConflictAccessContext(
            tenant_id=binding.tenant_partition_id,
            principal_id=binding.principal_subject_id,
            principal_binding_digest=binding.binding_digest,
            authorized_scope_ids=scopes.scopes,
            scope_digest=scopes.required_scope_set_digest,
            authorization_snapshot_digest=scopes.required_scope_set_digest,
        )

    def _attention_page(
        self, access: ConflictAccessContext | None, request: ConflictListRequest, *, explicit: bool = False
    ) -> ConflictAttentionPage:
        if not self._conflict_attention_enabled:
            if explicit:
                raise ConflictAttentionReadError("conflict_attention_unavailable")
            return ConflictAttentionPage(total_pending=0)
        if access is None:
            if explicit:
                raise ConflictAttentionReadError("conflict_attention_authorization_required")
            return ConflictAttentionPage(total_pending=0)
        if self._conflict_attention_repository is None:
            raise RuntimeError("conflict attention repository configuration is unavailable")
        if request.cursor is None and request.scope_ids is not None and not set(request.scope_ids) <= set(
            access.authorized_scope_ids
        ):
            raise ConflictAttentionReadError("invalid_conflict_scope")
        return self._conflict_attention_repository.list_conflicts(access, request)

    def seed_committed_record(self, record: ProviderStoredRecord) -> None:
        self._memory_plane.seed_provider_committed_record(record)

    def candidate_records(self) -> list[ProviderStoredRecord]:
        return self._memory_plane.provider_candidate_records()

    def transcript_records(self) -> list[ProviderStoredRecord]:
        return self._memory_plane.provider_transcript_records()

    def last_prefetch_trace(self):
        return self._memory_plane.last_provider_prefetch_trace()

    def last_recall_bundle(self) -> RecallStateBundle | None:
        return self._last_recall_bundle

    def last_memory_evolution_result(self) -> MemoryEvolutionResult | None:
        return self._last_memory_evolution_result

    def list_work_states(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        kinds: list[WorkStateKind] | None = None,
        statuses: list[WorkStateStatus] | None = None,
    ) -> list[WorkStateRecord]:
        if self._work_state_service is None:
            return []
        return self._work_state_service.list_states(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            kinds=kinds,
            statuses=statuses,
        )

    def reconcile_memory_evolution(self) -> list[ProviderEvolutionOutcome]:
        """Retry pending and retryable failed evolution operations."""

        self.process_pending_conflict_clarifications(max_items=16)
        return self._provider_ingestion.reconcile()

    def process_pending_conflict_clarifications(self, *, max_items: int = 1) -> int:
        """Run a bounded scheduler tick over durable clarification work."""

        if max_items < 1 or max_items > 256:
            raise ValueError("max_items must be between 1 and 256")
        processor = self._conflict_clarification_processor
        if processor is None:
            return 0
        completed = 0
        while completed < max_items and processor.process_next():
            completed += 1
        return completed

    @staticmethod
    def _format_work_state_section(work_states: list[WorkStateSummary]) -> str:
        lines = ["Current work state:"]
        for state in work_states:
            lines.append(f"- [{state.kind.value}:{state.status.value}] {state.title}")
            lines.append(f"  Summary: {state.summary}")
            if state.latest_progress:
                lines.append(f"  Latest progress: {state.latest_progress}")
            if state.latest_outcome:
                lines.append(f"  Latest outcome: {state.latest_outcome}")
            if state.decision_state is not None:
                lines.extend(ProviderMemoryService._format_decision_state_section(state.decision_state))
            lines.append(f"  Confidence: {state.confidence:.2f}")
        return "\n".join(lines)

    @staticmethod
    def _format_decision_state_section(decision_summary: DecisionStateSummary) -> list[str]:
        lines = [
            "  Decision state:",
            f"  Question: {decision_summary.question}",
            f"  Status: {decision_summary.status}",
        ]
        if decision_summary.option_labels:
            lines.append("  Options:")
            lines.extend([f"  - {option_label}" for option_label in decision_summary.option_labels])
        if decision_summary.criteria_labels:
            lines.append("  Criteria:")
            lines.extend([f"  - {criteria_label}" for criteria_label in decision_summary.criteria_labels])
        if decision_summary.recommendation is not None:
            lines.extend(["  Current recommendation:", f"  {decision_summary.recommendation}"])
        if decision_summary.unresolved_questions:
            lines.append("  Unresolved questions:")
            lines.extend([f"  - {question}" for question in decision_summary.unresolved_questions])
        if decision_summary.final_decision is not None:
            lines.extend(["  Final decision:", f"  {decision_summary.final_decision}"])
        return lines
