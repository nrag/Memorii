"""Recoverable provider ingestion composed with default-on memory evolution."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService, PreparedSourceAdmission
from memorii.core.memory_evolution.atomic_store import (
    PreplanningOperationControl,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.bootstrap_profile import VerifiedBootstrapProfile, classify_bootstrap_input
from memorii.core.memory_evolution.conflict_attention import AgentClarificationProposal
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    OperationFenceBinding,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.prompts.runtime_manifest import PromptOwner
from memorii.core.provider.models import ProviderEvent, ProviderEvolutionOutcome, ProviderSyncResult
from memorii.core.semantic_ingestion.authorization import (
    SemanticAuthorizationAuthorityError,
    SemanticAuthorizationAuthorityRepository,
)
from memorii.core.semantic_ingestion.capability import (
    AuthorizedSemanticIngestionRuntime,
    ConflictClarificationSemanticContext,
)
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    AuthorizationStageSnapshot,
    AuthorizationUsePoint,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SemanticEgressAuthorizationBinding,
    SemanticExecutionRetryPlan,
    SemanticRecoveryAuthorityBinding,
    SourceAuthority,
    SourceAuthorityEvidence,
    TimeInterval,
)
from memorii.core.semantic_ingestion.egress import (
    EgressPolicyProvider,
    ProviderEgressBinding,
    verify_current_egress,
)
from memorii.core.semantic_ingestion.persistence import (
    SemanticAuthorizationReadSetError,
    SemanticIngestionLeaseSession,
    SemanticTerminalPersistenceService,
)
from memorii.core.semantic_ingestion.pipeline import (
    SemanticAnalysisOutage,
    SemanticCandidateAssessor,
    SemanticIngestionPipeline,
    SemanticPipelinePolicyProvider,
    SemanticTerminalOutcome,
)
from memorii.core.semantic_ingestion.prompt_authority import SemanticPromptAuthority
from memorii.domain.enums import (
    ExtractionRunStatus,
    FinalExtractionSource,
    MemoryRecordVisibility,
    ProviderAttemptStatus,
)


class _SemanticPolicyReadOutage(OSError):
    """A mutable semantic ingestion authorization owner is retryably unavailable."""


class _ProviderAuthorizationReadSet:
    """Re-read all mutable authorization owners for one admitted source."""

    def __init__(
        self,
        *,
        runtime: AuthorizedSemanticIngestionRuntime,
        profile: VerifiedBootstrapProfile,
        policy_provider: SemanticPipelinePolicyProvider,
        egress_policy_provider: EgressPolicyProvider | None,
        egress_binding: ProviderEgressBinding | None,
        source_id: str,
        source_digest: str,
        now_provider: Callable[[], datetime],
        authority_repository: SemanticAuthorizationAuthorityRepository,
        policy_bundle: SemanticArbitrationPolicyBundle | None = None,
    ) -> None:
        self._runtime = runtime
        self._profile = profile
        self._policy_provider = policy_provider
        self._egress_policy_provider = egress_policy_provider
        self._egress_binding = egress_binding
        self._source_id = source_id
        self._source_digest = source_digest
        self._now_provider = now_provider
        self._authority_repository = authority_repository
        self._policy_bundle = policy_bundle
        self._authority_scope_id = authority_repository.scope_id(
            source_id=source_id, source_digest=source_digest
        )

    def current_snapshot(
        self,
        *,
        policy_bundle: SemanticArbitrationPolicyBundle,
        use_point: AuthorizationUsePoint,
    ) -> AuthorizationStageSnapshot | None:
        server_now = self._now_provider()
        try:
            current_policy = self._policy_provider.current_policy(
                source_id=self._source_id, source_digest=self._source_digest
            )
        except OSError as exc:
            raise _SemanticPolicyReadOutage("semantic policy is unavailable") from exc
        if current_policy is None or current_policy.arbitration_bundle != policy_bundle:
            return None
        self._policy_bundle = policy_bundle
        deployment_use_point: Literal[
            "stage_start", "post_response", "pre_seal", "pre_commit"
        ]
        if use_point in {"pre_request", "pre_analysis", "recovery_activation"}:
            deployment_use_point = "stage_start"
        elif use_point == "post_response":
            deployment_use_point = "post_response"
        elif use_point == "pre_seal":
            deployment_use_point = "pre_seal"
        else:
            deployment_use_point = "pre_commit"
        try:
            deployment = self._runtime.verify_authorization(
                profile=self._profile,
                use_point=deployment_use_point,
                server_time=server_now,
            )
        except OSError as exc:
            raise _SemanticPolicyReadOutage("deployment authorization is unavailable") from exc
        if deployment is None:
            return None
        current_egress = None
        if self._egress_binding is not None:
            current_egress = verify_current_egress(
                self._egress_policy_provider,
                binding=self._egress_binding,
                at=server_now,
            )
            if current_egress is None:
                return None
        read_set = SemanticAuthorizationReadSet.create(
            policy_bundle=policy_bundle,
            egress_policy_revision=(
                current_egress.policy_revision if current_egress is not None else None
            ),
            egress_decision_digest=(
                current_egress.decision_digest if current_egress is not None else None
            ),
            egress_binding=(
                SemanticEgressAuthorizationBinding.model_validate(
                    self._egress_binding.model_dump(mode="python")
                )
                if self._egress_binding is not None else None
            ),
            deployment_authorization_digest=deployment.authorization_digest,
            deployment_active_epoch=deployment.active_epoch,
            deployment_decision_digest=deployment.decision_digest,
        )
        valid_until = deployment.expires_at
        if current_egress is not None and current_egress.expires_at < valid_until:
            valid_until = current_egress.expires_at
        try:
            precondition = self._authority_repository.observe_verified(
                authority_scope_id=self._authority_scope_id,
                read_set=read_set,
                valid_until=valid_until,
                server_now=server_now,
            )
        except SemanticAuthorizationAuthorityError:
            return None
        return AuthorizationStageSnapshot.create(
            use_point=use_point,
            server_now=server_now,
            read_set=read_set,
            egress_policy_id=(
                current_egress.policy_id if current_egress is not None else None
            ),
            egress_policy_fingerprint=(
                current_egress.policy_fingerprint if current_egress is not None else None
            ),
            egress_expires_at=(
                current_egress.expires_at if current_egress is not None else None
            ),
            deployment_expires_at=deployment.expires_at,
            authority_record_id=precondition.authority_record_id,
            authority_revision=precondition.expected_authority_revision,
            authority_coordinates_digest=precondition.expected_coordinates_digest,
            authority_record_digest=precondition.expected_record_digest,
        )

    def verify_current(self, read_set: SemanticAuthorizationReadSet, *, use_point: str) -> bool:
        if use_point != "pre_commit":
            return False
        policy_bundle = getattr(self, "_policy_bundle", None)
        snapshot = self.current_snapshot(
            policy_bundle=policy_bundle,
            use_point="pre_commit",
        ) if policy_bundle is not None else None
        self._precommit_snapshot = snapshot
        return snapshot is not None and snapshot.read_set == read_set

    def take_precommit_snapshot(
        self, read_set: SemanticAuthorizationReadSet,
    ) -> AuthorizationStageSnapshot | None:
        snapshot = getattr(self, "_precommit_snapshot", None)
        self._precommit_snapshot = None
        return snapshot if snapshot is not None and snapshot.read_set == read_set else None


class ProviderIngestionCoordinator:
    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        admission_service: GovernedSourceAdmissionService,
        bootstrap_profile: VerifiedBootstrapProfile | None,
        bootstrap_unavailable_reason: str,
        atomic_store: SemanticIngestionAtomicStore,
        writer_admission: SemanticWriterAdmissionStore,
        semantic_pipeline: SemanticIngestionPipeline | None = None,
        semantic_policy_provider: SemanticPipelinePolicyProvider | None = None,
        semantic_egress_policy_provider: EgressPolicyProvider | None = None,
        semantic_candidate_assessor: SemanticCandidateAssessor | None = None,
        semantic_runtime: AuthorizedSemanticIngestionRuntime | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._memory_plane = memory_plane
        self._admission_service = admission_service
        self._bootstrap_profile = bootstrap_profile
        self._bootstrap_unavailable_reason = bootstrap_unavailable_reason
        self._atomic_store = atomic_store
        self._writer_admission = writer_admission
        self._semantic_pipeline = semantic_pipeline
        self._semantic_policy_provider = semantic_policy_provider
        self._semantic_egress_policy_provider = semantic_egress_policy_provider
        self._semantic_candidate_assessor = semantic_candidate_assessor
        self._semantic_runtime = semantic_runtime
        self._semantic_local_proposal_producer = (
            semantic_runtime.local_proposal_producer if semantic_runtime is not None else None
        )
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._authorization_repository = SemanticAuthorizationAuthorityRepository(
            atomic_store=atomic_store,
            writer_binding_provider=self._current_writer_binding,
            now_provider=self._now_provider,
        )
        self._semantic_terminal_persistence = SemanticTerminalPersistenceService(
            atomic_store=atomic_store,
            writer_binding_provider=self._current_writer_binding,
            authorization_repository=self._authorization_repository,
        )

    def resolve_context(
        self, proposal: AgentClarificationProposal
    ) -> ConflictClarificationSemanticContext | None:
        """Rebuild ordinary local semantic inputs from the retained user event."""

        from memorii.core.memory_evolution.conflict_attention import (
            RetainedConflictClarificationContext,
        )

        try:
            validated = AgentClarificationProposal.model_validate(
                proposal.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            return None
        retained_value = self._atomic_store.resolve_conflict_clarification_context(
            validated
        )
        if retained_value is None:
            return None
        try:
            retained = RetainedConflictClarificationContext.model_validate(
                retained_value.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            return None
        ingress = retained.authenticated_ingress
        if (
            ingress.delivery_principal_binding.principal_subject_id
            != validated.agent_principal_id
            or self._semantic_policy_provider is None
            or self._semantic_runtime is None
            or self._bootstrap_profile is None
            or self._semantic_candidate_assessor is None
            or self._semantic_local_proposal_producer is None
        ):
            return None
        policy = self._semantic_policy_provider.current_policy(
            source_id=retained.source_user_event_id,
            source_digest=retained.source_user_event_digest,
        )
        if policy is None:
            return None
        evidence = self._authenticated_source_evidence(
            source_id=retained.source_user_event_id,
            source_digest=retained.source_user_event_digest,
            authenticated_ingress=ingress,
        )
        if evidence is None:
            return None
        authority, interval = evidence
        local_proposals = self._semantic_local_proposal_producer.propose(
            source_id=retained.source_user_event_id,
            source_digest=retained.source_user_event_digest,
            source_text=retained.source_text,
        )
        authorization_guard = _ProviderAuthorizationReadSet(
            runtime=self._semantic_runtime,
            profile=self._bootstrap_profile,
            policy_provider=self._semantic_policy_provider,
            egress_policy_provider=self._semantic_egress_policy_provider,
            egress_binding=None,
            source_id=retained.source_user_event_id,
            source_digest=retained.source_user_event_digest,
            now_provider=self._now_provider,
            authority_repository=self._authorization_repository,
        )
        return ConflictClarificationSemanticContext(
            source_id=retained.source_user_event_id,
            source_digest=retained.source_user_event_digest,
            source_text=retained.source_text,
            policy_bundle=policy.arbitration_bundle,
            source_authority_evidence=authority,
            source_interval_evidence=interval,
            authorization_read_set_provider=authorization_guard,
            independent_assessor=self._semantic_candidate_assessor,
            local_proposals=local_proposals,
            current_time_provider=self._now_provider,
        )

    def ingest(
        self,
        event: ProviderEvent,
        *,
        defer_assertions: bool = False,
        authenticated_ingress: AuthenticatedIngressContext | None = None,
    ) -> tuple[ProviderSyncResult, None, None]:
        result, source_records = self._memory_plane.prepare_provider_event(event)
        metadata_poor = event.operation.value in {"session_end", "pre_compress"}
        if metadata_poor:
            # Metadata-poor events are evidence-only, but still require the
            # same authenticated governed-admission boundary as every governed-source admission input.
            if authenticated_ingress is None:
                return (
                    result.model_copy(update={"transcript_ids": [], "candidate_ids": [], "allowed_candidate_domains": [], "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "ingress_unavailable"}}),
                    None,
                    None,
                )
            raw_sources = tuple(record for record in source_records if record.is_raw_event)
            if len(raw_sources) != 1:
                raise RuntimeError("governed provider admission requires one raw source")
            identity = DeliveryIdentity.create(authenticated_ingress.delivery_principal_binding, event.event_id)
            outcome = "unavailable"
            reason = self._bootstrap_unavailable_reason
            if self._bootstrap_profile is not None:
                if self._bootstrap_profile.enabled:
                    outcome = "abstained"
                    reason = "extractor_abstained"
                else:
                    outcome = "disabled"
                    reason = "operator_disabled"
            def prepare() -> PreparedSourceAdmission:
                return self._admission_service.prepare_atomic(
                source=_governed_source(raw_sources[0], identity, metadata_poor=True),
                delivery_identity=identity,
                ingress=authenticated_ingress,
                operation_id=event.event_id,
                outcome_kind=outcome,
                outcome_reason=reason,
                normalized_input=(event.content or "").encode("utf-8"),
                evidence_only=True,
                selection_digest=(self._bootstrap_profile.selection_digest if self._bootstrap_profile else None),
                verification_digest=(self._bootstrap_profile.verification_digest if self._bootstrap_profile else None),
                )
            self._admit_with_writer_retry(prepare)
            return (
                result.model_copy(update={"transcript_ids": [f"semantic_ingestion:source:{identity.delivery_key_digest}"], "candidate_ids": [], "allowed_candidate_domains": [], "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "source_only"}}),
                None,
                None,
            )
        if authenticated_ingress is None:
            return (
                result.model_copy(
                    update={
                        "transcript_ids": [],
                        "candidate_ids": [],
                        "allowed_candidate_domains": [],
                        "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "ingress_unavailable"},
                    }
                ),
                None,
                None,
            )
        raw_sources = tuple(record for record in source_records if record.is_raw_event)
        if len(raw_sources) != 1:
            raise RuntimeError("governed provider admission requires one raw source")
        identity = DeliveryIdentity.create(authenticated_ingress.delivery_principal_binding, event.event_id)
        governed_source = _governed_source(raw_sources[0], identity)
        outcome = "unavailable"
        reason = self._bootstrap_unavailable_reason
        matched_case_id = None
        if self._bootstrap_profile is not None:
            outcome, reason, matched_case_id = classify_bootstrap_input(
                profile=self._bootstrap_profile,
                ingress=authenticated_ingress,
                normalized_segment=(event.content or "").encode("utf-8"),
            )
        def prepare() -> PreparedSourceAdmission:
            return self._admission_service.prepare_atomic(
                source=governed_source,
            delivery_identity=identity,
            ingress=authenticated_ingress,
            operation_id=event.event_id,
            outcome_kind=outcome,
            outcome_reason=reason,
            normalized_input=(event.content or "").encode("utf-8"),
            matched_corpus_case_id=matched_case_id,
            selection_digest=(self._bootstrap_profile.selection_digest if self._bootstrap_profile else None),
            verification_digest=(self._bootstrap_profile.verification_digest if self._bootstrap_profile else None),
            )
        publication = self._admit_with_writer_retry(prepare)
        if outcome == "selected_pipeline_pending":
            fence = publication.operation.operation_fence
            execution_plan = self._semantic_terminal_persistence.recover_execution_plan(
                fence=fence
            )
            if execution_plan is not None:
                self._validate_execution_plan_source(
                    plan=execution_plan,
                    fence=fence,
                    expected_source_utf8=governed_source.text.encode("utf-8"),
                )
            lease_session = self._semantic_terminal_persistence.open_lease_session(
                fence=fence
            )
            if lease_session.closed:
                return (result.model_copy(update={"transcript_ids": [governed_source.memory_id], "candidate_ids": [], "allowed_candidate_domains": [], "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "source_only"}}), None, None)
            if self._semantic_pipeline is not None:
                if execution_plan is None:
                    execution_plan, deployment_state = self._build_execution_plan(
                        fence=fence,
                        source_text=governed_source.text,
                        authenticated_ingress=authenticated_ingress,
                    )
                    lease_session.checkpoint_execution_plan(execution_plan)
                    if deployment_state == "outage":
                        lease_session.checkpoint_retryable(
                            stage="policy_read", failure_kind="policy_outage",
                        )
                        return (result.model_copy(update={
                            "transcript_ids": [governed_source.memory_id], "candidate_ids": [],
                            "allowed_candidate_domains": [], "blocked_reasons": {
                                **result.blocked_reasons, "semantic_ingestion": "retryable_outage",
                            },
                        }), None, None)
                    if deployment_state == "denied":
                        denied_terminal = SemanticTerminalOutcome.create(
                            operation_id=event.event_id, status="evidence_only",
                            reason_codes=("deployment_authorization_unavailable",), candidates=(),
                            temporal_closures=(), attempt_count=0,
                        )
                        self._semantic_terminal_persistence.persist(
                            fence=fence, terminal=denied_terminal,
                        )
                        return (result.model_copy(update={
                            "transcript_ids": [governed_source.memory_id], "candidate_ids": [],
                            "allowed_candidate_domains": [], "blocked_reasons": {
                                **result.blocked_reasons, "semantic_ingestion": "source_only",
                            },
                        }), None, None)
                else:
                    try:
                        authority_prepared = self._prepare_recovery_authority(
                            plan=execution_plan,
                            fence=fence,
                            lease_session=lease_session,
                        )
                    except _SemanticPolicyReadOutage:
                        authority_prepared = False
                    if not authority_prepared:
                        return (result.model_copy(update={
                            "transcript_ids": [governed_source.memory_id], "candidate_ids": [],
                            "allowed_candidate_domains": [], "blocked_reasons": {
                                **result.blocked_reasons, "semantic_ingestion": "retryable_outage",
                            },
                        }), None, None)
            recovered_terminal = self._semantic_terminal_persistence.recover_terminal_artifact(
                fence=fence
            )
            try:
                terminal_with_guard = (
                    (
                        recovered_terminal,
                        self._authorization_guard_for_terminal(
                            recovered_terminal, fence
                        ),
                    )
                    if recovered_terminal is not None
                    else self._run_semantic_ingestion(
                        operation_id=execution_plan.operation_id,
                        source_id=execution_plan.source_id,
                        source_digest=execution_plan.source_digest,
                        source_text=execution_plan.source_utf8_bytes.decode("utf-8"),
                        authenticated_ingress=execution_plan.authenticated_ingress,
                        lease_session=lease_session,
                        operation_fence=fence,
                    )
                    if self._semantic_pipeline is not None and execution_plan is not None
                    else (
                        SemanticTerminalOutcome.create(
                            operation_id=event.event_id, status="evidence_only",
                            reason_codes=("semantic_runtime_unauthorized",), candidates=(),
                            temporal_closures=(), attempt_count=0,
                        ),
                        None,
                    )
                )
            except _SemanticPolicyReadOutage:
                lease_session.checkpoint_retryable(
                    stage="policy_read", failure_kind="policy_outage",
                )
                return (
                    result.model_copy(update={
                        "transcript_ids": [governed_source.memory_id],
                        "candidate_ids": [], "allowed_candidate_domains": [],
                        "blocked_reasons": {
                            **result.blocked_reasons,
                            "semantic_ingestion": "retryable_outage",
                        },
                    }),
                    None, None,
                )
            except SemanticAnalysisOutage:
                lease_session.checkpoint_retryable(
                    stage="analysis", failure_kind="transport_outage",
                )
                return (
                    result.model_copy(update={
                        "transcript_ids": [governed_source.memory_id],
                        "candidate_ids": [], "allowed_candidate_domains": [],
                        "blocked_reasons": {
                            **result.blocked_reasons,
                            "semantic_ingestion": "retryable_outage",
                        },
                    }),
                    None, None,
                )
            except OSError:
                lease_session.checkpoint_retryable(
                    stage="proposal",
                    failure_kind="transport_outage",
                )
                return (
                    result.model_copy(update={
                        "transcript_ids": [governed_source.memory_id],
                        "candidate_ids": [],
                        "allowed_candidate_domains": [],
                        "blocked_reasons": {
                            **result.blocked_reasons,
                            "semantic_ingestion": "retryable_outage",
                        },
                    }),
                    None,
                    None,
                )
            terminal, authorization_guard = terminal_with_guard
            try:
                self._persist_semantic_terminal(
                    fence,
                    terminal,
                    authorization_guard=authorization_guard,
                )
            except SemanticAuthorizationReadSetError:
                lease_session.checkpoint_retryable(
                    stage="group",
                    failure_kind="policy_outage",
                    terminal=terminal,
                )
            except _SemanticPolicyReadOutage:
                lease_session.checkpoint_retryable(
                    stage="group",
                    failure_kind="policy_outage",
                    terminal=terminal,
                )
            except OSError:
                control = self._atomic_store.get_operation(
                    fence
                )
                lease_session.checkpoint_retryable(
                    stage=("finalization" if control.group_result_digests else "planning"),
                    failure_kind="store_outage",
                    terminal=terminal,
                )
        return (result.model_copy(update={"transcript_ids": [governed_source.memory_id], "candidate_ids": [], "allowed_candidate_domains": [], "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "source_only"}}), None, None)

    def reconcile(self) -> list[ProviderEvolutionOutcome]:
        outcomes: list[ProviderEvolutionOutcome] = []
        for record in self._memory_plane.list_records():
            if record.source_kind != "semantic_ingestion_preplanning_control":
                continue
            try:
                control = PreplanningOperationControl.model_validate(record.content["control"])
            except (KeyError, ValueError, TypeError):
                continue
            if control.state in {"terminal", "lease_recovery_exhausted"}:
                continue
            terminal = self._semantic_terminal_persistence.recover_terminal_artifact(
                fence=control.operation_fence
            )
            if terminal is None:
                plan = self._semantic_terminal_persistence.recover_execution_plan(
                    fence=control.operation_fence
                )
                if plan is None:
                    continue
                self._validate_execution_plan_source(
                    plan=plan,
                    fence=control.operation_fence,
                )
                lease_session = self._semantic_terminal_persistence.open_lease_session(
                    fence=control.operation_fence
                )
                if lease_session.closed:
                    continue
                try:
                    authority_prepared = self._prepare_recovery_authority(
                        plan=plan,
                        fence=control.operation_fence,
                        lease_session=lease_session,
                    )
                except _SemanticPolicyReadOutage:
                    lease_session.checkpoint_retryable(
                        stage="policy_read", failure_kind="policy_outage"
                    )
                    outcomes.append(self._retryable_outcome(control))
                    continue
                if not authority_prepared:
                    outcomes.append(self._retryable_outcome(control))
                    continue
                try:
                    terminal, guard = self._run_semantic_ingestion(
                        operation_id=plan.operation_id,
                        source_id=plan.source_id,
                        source_digest=plan.source_digest,
                        source_text=plan.source_utf8_bytes.decode("utf-8"),
                        authenticated_ingress=plan.authenticated_ingress,
                        lease_session=lease_session,
                        operation_fence=control.operation_fence,
                    )
                except _SemanticPolicyReadOutage:
                    lease_session.checkpoint_retryable(
                        stage="policy_read", failure_kind="policy_outage"
                    )
                    outcomes.append(self._retryable_outcome(control))
                    continue
                except SemanticAnalysisOutage:
                    lease_session.checkpoint_retryable(
                        stage="analysis", failure_kind="transport_outage"
                    )
                    outcomes.append(self._retryable_outcome(control))
                    continue
                except OSError:
                    lease_session.checkpoint_retryable(
                        stage="proposal", failure_kind="transport_outage"
                    )
                    outcomes.append(self._retryable_outcome(control))
                    continue
                try:
                    self._semantic_terminal_persistence.persist(
                        fence=control.operation_fence,
                        terminal=terminal,
                        authorization_verifier=guard,
                    )
                except (SemanticAuthorizationReadSetError, OSError):
                    lease_session.checkpoint_retryable(
                        stage="group", failure_kind="policy_outage", terminal=terminal
                    )
                    outcomes.append(self._retryable_outcome(control))
                    continue
                outcomes.append(self._committed_outcome(control, terminal))
                continue
            guard = self._authorization_guard_for_terminal(terminal, control.operation_fence)
            try:
                self._semantic_terminal_persistence.persist(
                    fence=control.operation_fence,
                    terminal=terminal,
                    authorization_verifier=guard,
                )
            except (SemanticAuthorizationReadSetError, OSError):
                outcomes.append(self._retryable_outcome(control))
                continue
            outcomes.append(self._committed_outcome(control, terminal))
        return outcomes

    @staticmethod
    def _retryable_outcome(control: PreplanningOperationControl) -> ProviderEvolutionOutcome:
        return ProviderEvolutionOutcome(
            operation_id=control.operation_fence.operation_id,
            status="evolution_pending",
            attempt_count=max(control.attempt_count, 1),
            failure_code="semantic_ingestion_reconciliation_retryable",
            retryable=True,
        )

    @staticmethod
    def _committed_outcome(
        control: PreplanningOperationControl,
        terminal: SemanticTerminalOutcome,
    ) -> ProviderEvolutionOutcome:
        return ProviderEvolutionOutcome(
                operation_id=control.operation_fence.operation_id,
                status="evolution_committed",
                attempt_count=max(control.attempt_count, 1),
                extraction_status=(
                    ExtractionRunStatus.SUCCEEDED
                    if terminal.status == "accepted"
                    else ExtractionRunStatus.ABSTAINED
                ),
                provider_attempt_status=(
                    ProviderAttemptStatus.SUCCEEDED
                    if terminal.status == "accepted"
                    else ProviderAttemptStatus.NOT_ATTEMPTED
                ),
                final_extraction_source=(
                    FinalExtractionSource.PRIMARY
                    if terminal.status == "accepted"
                    else FinalExtractionSource.NONE
                ),
            )

    def _build_execution_plan(
        self,
        *,
        fence: OperationFenceBinding,
        source_text: str,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> tuple[SemanticExecutionRetryPlan, Literal["verified", "outage", "denied"]]:
        runtime = self._semantic_runtime
        profile = self._bootstrap_profile
        if runtime is None or profile is None:
            raise ValueError("authorized semantic ingestion runtime is unavailable for retry planning")
        state: Literal["verified", "outage", "denied"]
        try:
            deployment = runtime.verify_authorization(
                profile=profile, use_point="stage_start", server_time=self._now_provider()
            )
        except OSError:
            deployment = None
            state = "outage"
        else:
            state = "verified" if deployment is not None else "denied"
        authority_scope_id = self._authorization_repository.scope_id(
            source_id=fence.source_id, source_digest=fence.source_digest
        )
        current_authority = self._atomic_store.authorization_authority(authority_scope_id)
        plan = SemanticExecutionRetryPlan.create(
            operation_id=fence.operation_id,
            operation_fence_binding_digest=fence.binding_digest,
            source_id=fence.source_id,
            source_digest=fence.source_digest,
            source_utf8_bytes=source_text.encode("utf-8"),
            authenticated_ingress=authenticated_ingress,
            prompt_reference="semantic_ingestion_proposal:v1",
            policy_source_id=fence.source_id,
            policy_source_digest=fence.source_digest,
            bootstrap_selection_digest=profile.selection_digest,
            bootstrap_verification_digest=profile.verification_digest,
            deployment_authorization_state="verified" if deployment is not None else "unavailable",
            deployment_authorization_digest=(
                deployment.authorization_digest
                if deployment is not None else sha256(runtime.authorization_bytes).hexdigest()
            ),
            deployment_active_epoch=deployment.active_epoch if deployment is not None else None,
            deployment_decision_digest=deployment.decision_digest if deployment is not None else None,
            authorization_authority_scope_id=authority_scope_id,
            expected_authority_revision=(
                current_authority[0].authority_revision if current_authority is not None else 0
            ),
            expected_authority_coordinates_digest=(
                current_authority[0].coordinates_digest if current_authority is not None else None
            ),
            authorization_secret_reference=(
                "semantic-deployment-authorization:"
                + sha256(runtime.authorization_bytes).hexdigest()
            ),
            attempt_budget=3,
        )
        plan.validate_for_fence(fence)
        return plan, state

    def _validate_execution_plan_source(
        self,
        *,
        plan: SemanticExecutionRetryPlan,
        fence: OperationFenceBinding,
        expected_source_utf8: bytes | None = None,
    ) -> None:
        """Validate durable plan identity before lease, policy, or learned work."""
        plan.validate_for_fence(fence)
        source = self._memory_plane.get_record(plan.admitted_source_id)
        if source is None or source.text.encode("utf-8") != plan.source_utf8_bytes:
            raise ValueError("semantic ingestion execution retry plan source bytes are unavailable")
        if expected_source_utf8 is not None and expected_source_utf8 != plan.source_utf8_bytes:
            raise ValueError("semantic ingestion redelivery source bytes differ from persisted plan")

    def _authorization_guard_for_terminal(
        self,
        terminal: SemanticTerminalOutcome,
        fence,
    ) -> _ProviderAuthorizationReadSet | None:
        read_set = terminal.authorization_read_set
        if (
            read_set is None
            or terminal.arbitration_policy_bundle is None
            or self._semantic_runtime is None
            or self._bootstrap_profile is None
            or self._semantic_policy_provider is None
        ):
            return None
        binding = (
            ProviderEgressBinding.model_validate(read_set.egress_binding.model_dump(mode="python"))
            if read_set.egress_binding is not None else None
        )
        return _ProviderAuthorizationReadSet(
            runtime=self._semantic_runtime,
            profile=self._bootstrap_profile,
            policy_provider=self._semantic_policy_provider,
            egress_policy_provider=self._semantic_egress_policy_provider,
            egress_binding=binding,
            source_id=fence.source_id,
            source_digest=fence.source_digest,
            now_provider=self._now_provider,
            authority_repository=self._authorization_repository,
            policy_bundle=terminal.arbitration_policy_bundle,
        )

    def _current_writer_binding(self):
        return self._writer_admission.commit_binding(self._writer_admission.current())

    def _admit_with_writer_retry(self, prepare: Callable[[], PreparedSourceAdmission]):
        for attempt in range(2):
            prepared = prepare()
            try:
                return self._atomic_store.admit_source(
                    prepared=prepared,
                    writer_binding=self._current_writer_binding(),
                )
            except SemanticWriterAdmissionError as exc:
                if attempt or "atomic admission index binding is mismatched" not in str(exc):
                    raise
        raise AssertionError("unreachable writer retry loop")

    def _run_semantic_ingestion(
        self, *, operation_id: str, source_id: str, source_digest: str, source_text: str,
        authenticated_ingress: AuthenticatedIngressContext,
        lease_session: SemanticIngestionLeaseSession,
        operation_fence: OperationFenceBinding,
    ) -> tuple[SemanticTerminalOutcome, _ProviderAuthorizationReadSet | None]:
        """Invoke semantic ingestion only with a current server-owned policy snapshot.

        Missing control-plane policy is terminal evidence, never permission to
        serialize a source to a remote transport.
        """
        if self._semantic_policy_provider is None:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("semantic_policy_unapproved",),
                candidates=(), temporal_closures=(), attempt_count=0,
            ), None
        try:
            policy = self._semantic_policy_provider.current_policy(
                source_id=source_id, source_digest=source_digest
            )
        except OSError as exc:
            raise _SemanticPolicyReadOutage("semantic policy is unavailable") from exc
        if policy is None:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("semantic_policy_unavailable",),
                candidates=(), temporal_closures=(), attempt_count=0,
            ), None
        pipeline = self._semantic_pipeline
        if pipeline is None:
            raise RuntimeError("semantic ingestion pipeline was removed during execution")
        source_evidence = self._authenticated_source_evidence(
            source_id=source_id,
            source_digest=source_digest,
            authenticated_ingress=authenticated_ingress,
        )
        if source_evidence is None or self._semantic_runtime is None or self._bootstrap_profile is None:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("authenticated_source_or_deployment_authority_unavailable",),
                candidates=(),
                temporal_closures=(),
                attempt_count=0,
            ), None
        authority, interval = source_evidence
        local_proposals = None
        binding = None
        registered_prompt = None
        if self._semantic_local_proposal_producer is not None:
            local_proposals = self._semantic_local_proposal_producer.propose(
                source_id=source_id,
                source_digest=source_digest,
                source_text=source_text,
            )
        else:
            binding = self._egress_binding_for(
                source_id=source_id,
                source_digest=source_digest,
                authenticated_ingress=authenticated_ingress,
            )
            if binding is None:
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id, status="evidence_only",
                    reason_codes=("semantic_egress_governance_unavailable",), candidates=(), temporal_closures=(), attempt_count=0,
                ), None
            try:
                registered_prompt = SemanticPromptAuthority.build(
                    registry=PromptRegistry(), prompt_ref="semantic_ingestion_proposal:v1",
                    owner=PromptOwner.SEMANTIC_INGESTION_PROPOSER, variables={}, source_text=source_text,
                    metadata={"operation_id": operation_id, "segment_id": binding.segment_id},
                )
            except (TypeError, ValueError):
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id, status="evidence_only",
                    reason_codes=("registered_semantic_prompt_unavailable",), candidates=(), temporal_closures=(), attempt_count=0,
                ), None
        authorization_guard = _ProviderAuthorizationReadSet(
            runtime=self._semantic_runtime,
            profile=self._bootstrap_profile,
            policy_provider=self._semantic_policy_provider,
            egress_policy_provider=self._semantic_egress_policy_provider,
            egress_binding=binding,
            source_id=source_id,
            source_digest=source_digest,
            now_provider=self._now_provider,
            authority_repository=self._authorization_repository,
        )
        return pipeline.run(
            operation_id=operation_id,
            source_id=source_id,
            source_digest=source_digest,
            source_text=source_text,
            policy_bundle=policy.arbitration_bundle,
            source_authority_evidence=authority,
            source_interval_evidence=interval,
            authorization_read_set_provider=authorization_guard,
            independent_assessor=self._semantic_candidate_assessor,
            local_proposals=local_proposals,
            registered_prompt=registered_prompt,
            egress_binding=binding,
            egress_policy_provider=self._semantic_egress_policy_provider,
            current_time_provider=self._now_provider,
            lease_heartbeat=lease_session.heartbeat,
            stage_observer=lease_session.checkpoint,
            operation_fence=operation_fence,
        ), authorization_guard

    def _prepare_recovery_authority(
        self, *, plan: SemanticExecutionRetryPlan, fence: OperationFenceBinding,
        lease_session: SemanticIngestionLeaseSession,
    ) -> bool:
        """Bind exact same-store authority before recovered learned execution."""
        current = self._atomic_store.authorization_authority(
            plan.authorization_authority_scope_id
        )
        existing = self._semantic_terminal_persistence.recover_recovery_authority_binding(
            fence=fence
        )
        if existing is not None:
            if current is None:
                return False
            authority, precondition = current
            return (
                existing.plan_digest == plan.plan_digest
                and existing.authority_record_id == plan.authorization_authority_record_id
                and existing.authority_revision == authority.authority_revision
                and existing.authority_coordinates_digest == authority.coordinates_digest
                and existing.authority_record_digest == precondition.expected_record_digest
                and existing.read_set_digest == authority.read_set_digest
                and authority.state == "active"
                and authority.valid_until > self._now_provider()
            )
        if current is not None:
            authority, precondition = current
            if (
                authority.authority_record_id != plan.authorization_authority_record_id
                or authority.state != "active"
                or authority.valid_until <= self._now_provider()
                or authority.deployment_authorization_digest
                != plan.deployment_authorization_digest
                or authority.deployment_active_epoch != plan.deployment_active_epoch
                or authority.deployment_decision_digest != plan.deployment_decision_digest
                or (
                    plan.expected_authority_revision == 0
                    and authority.authority_revision != 1
                )
                or (
                    plan.expected_authority_revision > 0
                    and (
                        authority.authority_revision != plan.expected_authority_revision
                        or authority.coordinates_digest
                        != plan.expected_authority_coordinates_digest
                    )
                )
            ):
                return False
            binding = SemanticRecoveryAuthorityBinding.create(
                operation_id=plan.operation_id,
                plan_digest=plan.plan_digest,
                authority_scope_id=plan.authorization_authority_scope_id,
                authority_record_id=authority.authority_record_id,
                authority_revision=authority.authority_revision,
                authority_coordinates_digest=authority.coordinates_digest,
                authority_record_digest=precondition.expected_record_digest,
                read_set_digest=authority.read_set_digest,
            )
            lease_session.checkpoint_recovery_authority_binding(binding)
            return True
        if plan.expected_authority_revision != 0:
            return False
        if (
            self._semantic_policy_provider is None
            or self._semantic_runtime is None
            or self._bootstrap_profile is None
        ):
            return False
        try:
            policy = self._semantic_policy_provider.current_policy(
                source_id=plan.source_id, source_digest=plan.source_digest
            )
        except OSError as exc:
            raise _SemanticPolicyReadOutage("semantic policy is unavailable") from exc
        if policy is None:
            return False
        egress_binding = (
            None
            if self._semantic_local_proposal_producer is not None
            else self._egress_binding_for(
                source_id=plan.source_id,
                source_digest=plan.source_digest,
                authenticated_ingress=plan.authenticated_ingress,
            )
        )
        guard = _ProviderAuthorizationReadSet(
            runtime=self._semantic_runtime,
            profile=self._bootstrap_profile,
            policy_provider=self._semantic_policy_provider,
            egress_policy_provider=self._semantic_egress_policy_provider,
            egress_binding=egress_binding,
            source_id=plan.source_id,
            source_digest=plan.source_digest,
            now_provider=self._now_provider,
            authority_repository=self._authorization_repository,
        )
        snapshot = guard.current_snapshot(
            policy_bundle=policy.arbitration_bundle,
            use_point="recovery_activation",
        )
        if snapshot is None:
            return False
        lease_session.checkpoint_recovery_authority_binding(
            SemanticRecoveryAuthorityBinding.create(
                operation_id=plan.operation_id,
                plan_digest=plan.plan_digest,
                authority_scope_id=plan.authorization_authority_scope_id,
                authority_record_id=snapshot.authority_record_id,
                authority_revision=snapshot.authority_revision,
                authority_coordinates_digest=snapshot.authority_coordinates_digest,
                authority_record_digest=snapshot.authority_record_digest,
                read_set_digest=snapshot.read_set.read_set_digest,
            )
        )
        return True

    @staticmethod
    def _egress_binding_for(
        *, source_id: str, source_digest: str,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> ProviderEgressBinding | None:
        governance = authenticated_ingress.semantic_egress_governance
        if governance is None:
            return None
        return ProviderEgressBinding(
            tenant_id=authenticated_ingress.delivery_principal_binding.tenant_partition_id,
            source_id=source_id,
            source_digest=source_digest,
            segment_id=sha256(
                ("memorii.semantic-ingestion.segment.v1:" + source_digest).encode()
            ).hexdigest(),
            classification=governance.classification,
            provider=governance.provider,
            model=governance.model,
            region=governance.region,
            retention_mode=governance.retention_mode,
            training_use=governance.training_use,
        )

    def _persist_semantic_terminal(
        self,
        fence,
        terminal: SemanticTerminalOutcome,
        *,
        authorization_guard: _ProviderAuthorizationReadSet | None,
    ) -> None:
        """Publish the closed terminal through semantic ingestion's sole writer-safe preplanning persistence owner."""
        self._semantic_terminal_persistence.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=authorization_guard,
        )

    @staticmethod
    def _authenticated_source_evidence(
        *,
        source_id: str,
        source_digest: str,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> tuple[SourceAuthorityEvidence, AuthenticatedSourceIntervalEvidence | None] | None:
        metadata = authenticated_ingress.semantic_source_authority
        if metadata is None:
            return None
        authority = SourceAuthorityEvidence.create(
            source_id=source_id,
            source_digest=source_digest,
            authority=SourceAuthority(
                authority_class=metadata.authority_class,
                authenticated_provenance_class=metadata.authenticated_provenance_class,
                governing_principal_id=metadata.governing_principal_id,
                policy_revision=metadata.policy_revision,
            ),
            provenance_digest=metadata.provenance_digest,
        )
        interval_metadata = authenticated_ingress.semantic_source_interval
        if interval_metadata is None:
            return authority, None
        if interval_metadata.policy_revision != metadata.policy_revision:
            return None
        interval = AuthenticatedSourceIntervalEvidence.create(
            source_id=source_id,
            source_digest=source_digest,
            interval=TimeInterval(start=interval_metadata.start, end=interval_metadata.end),
            authority_basis=interval_metadata.authority_basis,
            provenance_digest=interval_metadata.provenance_digest,
            policy_revision=interval_metadata.policy_revision,
            source_authority_evidence_digest=authority.evidence_digest,
        )
        return authority, interval


def _governed_source(
    source: CanonicalMemoryRecord,
    identity: DeliveryIdentity,
    *,
    metadata_poor: bool = False,
) -> CanonicalMemoryRecord:
    update: dict[str, object] = {
        "memory_id": f"semantic_ingestion:source:{identity.delivery_key_digest}",
        "source_kind": "semantic_ingestion_source",
        "visibility": MemoryRecordVisibility.INTERNAL_CONTROL,
    }
    if metadata_poor:
        update.update(
            {
                "source_kind": "semantic_ingestion_metadata_poor_snapshot",
                "text": "",
                "content": {
                    "schema_version": 1,
                    "source_kind": "conversation_snapshot",
                    "snapshot_utf8_bytes": source.text.encode("utf-8"),
                    "hook_kind": source.content.get("operation"),
                    "reason": "missing_message_governance",
                },
                "role": None,
                "session_id": None,
                "task_id": None,
                "user_id": None,
                "language": "und",
            }
        )
    return source.model_copy(update=update)
