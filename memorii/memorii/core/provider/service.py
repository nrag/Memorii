"""Provider-oriented memory service for Hermes-style hooks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

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
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapProfileVerificationError,
    InstalledHostBootstrapCapabilityProvider,
    VerifiedBootstrapProfile,
    verify_bootstrap_profile,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContextResolver,
    AuthenticatedIngressResolutionError,
)
from memorii.core.memory_evolution.operation_store import (
    EvolutionOperationRepository,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.next_step import NextStepEngine
from memorii.core.promotion.provider import PromotionAssessmentProvider
from memorii.core.promotion.rule_provider import RuleBasedPromotionAssessmentProvider
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
from memorii.core.provider.tool_schemas import provider_tool_schemas
from memorii.core.provider.tools import ProviderToolCallResult
from memorii.core.provider.work_state_projection import WorkStateMemoryProjector
from memorii.core.recall import RecallStateBundle, WorkStateSummary, summarize_work_states
from memorii.core.solver.frontier import SolverFrontierPlanner
from memorii.core.work_state.models import WorkStateKind, WorkStateRecord, WorkStateStatus
from memorii.core.work_state.selector import WorkStateSelector
from memorii.core.work_state.service import WorkStateService
from memorii.domain.enums import SourceModality
from memorii.stores.base.interfaces import OverlayStore, SolverGraphStore


class ProviderMemoryService:
    """Thin provider adapter over the canonical MemoryPlaneService."""

    _DEFAULT_DECISION_STATE_SERVICE = object()
    _DEFAULT_PROMOTION_DECISION_PROVIDER = object()

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
    ) -> None:
        self._memory_plane = memory_plane or MemoryPlaneService()
        capability_provider = InstalledHostBootstrapCapabilityProvider()
        try:
            host_bootstrap_capability = capability_provider.load()
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            host_bootstrap_capability = None
        verified_material = None
        if host_bootstrap_capability is not None:
            try:
                verified_material = host_bootstrap_capability.load_verified_bootstrap_material()
            except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                verified_material = None
        self._authenticated_ingress_resolver = None
        self._bootstrap_profile: VerifiedBootstrapProfile | None = None
        self._bootstrap_unavailable_reason = "invalid_config"
        if verified_material is not None:
            self._authenticated_ingress_resolver = cast(
                AuthenticatedIngressContextResolver,
                verified_material.authenticated_ingress_resolver,
            )
            try:
                self._bootstrap_profile = verify_bootstrap_profile(verified_material)
            except BootstrapProfileVerificationError as exc:
                self._bootstrap_profile = None
                self._bootstrap_unavailable_reason = exc.reason.value
            except ValueError:
                self._bootstrap_profile = None
                self._bootstrap_unavailable_reason = "invalid_manifest"
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
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
        self._provider_ingestion = ProviderIngestionCoordinator(
            memory_plane=self._memory_plane,
            admission_service=self._semantic_ingestion_admission,
            bootstrap_profile=self._bootstrap_profile,
            bootstrap_unavailable_reason=self._bootstrap_unavailable_reason,
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
        return self._ingest_event(event, authenticated_host_ingress=authenticated_host_ingress)

    def _ingest_event(
        self,
        event: ProviderEvent,
        *,
        authenticated_host_ingress: AuthenticatedHostIngress | None,
    ) -> ProviderSyncResult:
        ingress = self._resolve_ingress(authenticated_host_ingress)
        result, _, evolution_result = self._provider_ingestion.ingest(
            event,
            defer_assertions=event.operation
            in {
                ProviderOperation.CHAT_USER_TURN,
                ProviderOperation.CHAT_ASSISTANT_TURN,
            },
            authenticated_ingress=ingress,
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
            raise RuntimeError("memory evolution is unavailable in the M1 source-only composition")
        return self._memory_evolution_service

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
        sync_result, _, evolution_result = self._provider_ingestion.ingest(
            event,
            authenticated_ingress=self._resolve_ingress(authenticated_host_ingress),
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

    def handle_tool_call(self, tool_name: str, arguments: dict[str, object]) -> ProviderToolCallResult:
        return self._tool_dispatcher.handle(tool_name, arguments)

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

        return []

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
