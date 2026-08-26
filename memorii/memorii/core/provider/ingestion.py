"""Recoverable provider ingestion composed with default-on memory evolution."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService, PreparedSourceAdmission
from memorii.core.memory_evolution.atomic_store import (
    BootstrapHandoffAccessDenied,
    BootstrapRetainedPendingAuthorityUnavailable,
    BootstrapWriterHandoffRequest,
    BootstrapWriterHandoffResult,
    PreplanningOperationControl,
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapAdmissionPin,
    VerifiedBootstrapProfile,
)
from memorii.core.memory_evolution.conflict_attention import AgentClarificationProposal
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    OperationFenceBinding,
)
from memorii.core.memory_evolution.models import SourceObservation
from memorii.core.memory_evolution.record_projection import source_observation_from_record
from memorii.core.memory_evolution.source_admission import (
    DeliveryAuthorizationRequest,
    ProviderEventNormalizer,
    build_admitted_source_record,
    build_step_one_material_from_governance,
    build_structured_step_one_material_from_governance,
    step_one_source_digest,
)
from memorii.core.memory_evolution.source_governance import derive_source_governance_material
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
from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphAuthorityRequestV3
from memorii.core.semantic_ingestion.canonical_evidence_arena import (
    CANONICAL_CODEC_REVISION,
    CANONICAL_PROFILE_REVISION,
    CanonicalEvidenceArena,
    CanonicalEvidenceLease,
    CanonicalValidationScope,
)
from memorii.core.semantic_ingestion.capability import (
    AuthorizedSemanticIngestionRuntime,
    ConflictClarificationSemanticContext,
)
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    AuthorizationStageSnapshot,
    AuthorizationUsePoint,
    BootstrapGraphDependentCoordinatorSucceededV3,
    BootstrapGraphDependentPreGraphNonCommitV3,
    BootstrapGraphDurableRetryProgressV3,
    BootstrapGraphFinalizedFailureV3,
    BootstrapRecoveryClaimedV3,
    BootstrapRecoveryFoundV3,
    BootstrapRecoveryKeyV3,
    BootstrapRecoveryProbeV3,
    BootstrapSourceNormalizationResultV3,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SemanticEgressAuthorizationBinding,
    SemanticExecutionRetryPlan,
    SemanticRecoveryAuthorityBinding,
    SourceAuthority,
    SourceAuthorityEvidence,
    TextPreparationRequest,
    TimeInterval,
    contract_digest,
    encode_semantic_contract_result,
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
from memorii.core.semantic_ingestion.source_normalization_execution import (
    SourceNormalizationNonCommit,
)
from memorii.core.semantic_ingestion.source_normalization_stage import (
    GraphFreeSourceNormalizationInvocation,
    validate_reloaded_bootstrap_v3_source_normalization_result,
    validate_reloaded_source_normalization_result,
)
from memorii.core.semantic_ingestion.source_preparation import (
    BootstrapTextPreparationProducer,
)
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
        canonical_evidence_arena_factory: Callable[[], CanonicalEvidenceArena] | None = None,
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
        self._canonical_evidence_arena_factory = canonical_evidence_arena_factory
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
        canonical_evidence_arena: CanonicalEvidenceArena,
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
        if event.content == "":
            # An empty turn has no nonzero verbatim span to govern or prepare.
            # It remains evidence-only at the provider boundary: do not derive
            # a source identity, admit a semantic source, or invoke preparation.
            return (
                result.model_copy(
                    update={
                        "transcript_ids": [],
                        "candidate_ids": [],
                        "allowed_candidate_domains": [],
                        "blocked_reasons": {
                            **result.blocked_reasons,
                            "semantic_ingestion": "source_only",
                        },
                    }
                ),
                None,
                None,
            )
        try:
            request = ProviderEventNormalizer(authenticated_ingress).normalize(event)
        except ValueError as exc:
            # A snapshot/delegation event without its host-authenticated
            # envelope is retained only as provider evidence, never guessed
            # into a semantic source.
            return (
                result.model_copy(update={
                    "transcript_ids": [], "candidate_ids": [], "allowed_candidate_domains": [],
                    "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": str(exc)},
                }), None, None,
            )
        identity = request.delivery_identity
        source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
        # Exact redelivery must reconstruct identical admission evidence. The
        # caller-owned event timestamp is immutable delivery identity; local
        # processing time is not.
        retained_at = event.timestamp
        source_digest = step_one_source_digest(
            source_id=source_id,
            delivery_key_digest=identity.delivery_key_digest,
            original_text=request.original_text,
        )
        governance_result = derive_source_governance_material(
            ingress=authenticated_ingress,
            event=event,
            source_id=source_id,
            source_digest=source_digest,
            received_at=retained_at,
            retained_at=retained_at,
        )
        if governance_result.kind == "nonpromoting":
            return (
                result.model_copy(
                    update={
                        "transcript_ids": [],
                        "candidate_ids": [],
                        "allowed_candidate_domains": [],
                        "blocked_reasons": {
                            **result.blocked_reasons,
                            "semantic_ingestion": governance_result.reason_codes[0],
                        },
                    }
                ),
                None,
                None,
            )
        assert governance_result.material is not None
        request = request.bind_bootstrap_language_evidence(
            ingress=authenticated_ingress,
            source_id=source_id,
            source_digest=source_digest,
            segment_governance_set_digest=(
                governance_result.material.segment_governance_carriers.carrier_set_digest
            ),
            governance_carrier_artifact_digest=(
                governance_result.material.governance_carrier_artifact.artifact_digest
            ),
            segment_governance_carriers_digest=(
                governance_result.material.segment_governance_carriers.carrier_set_digest
            ),
            message_admission_carriers_digest=(
                governance_result.material.message_admission_carriers.carrier_set_digest
            ),
        )
        step_one_material = (
            build_structured_step_one_material_from_governance(
                source_id=source_id, source_digest=source_digest, original_text=request.original_text,
                envelope=request.structured_source_envelope, governance=governance_result.material,
            )
            if request.structured_source_envelope is not None
            else build_step_one_material_from_governance(
                source_id=source_id, source_digest=source_digest, original_text=request.original_text,
                source_reference=event.event_id, governance=governance_result.material,
            )
        )
        governed_source = build_admitted_source_record(
            request=request,
            source_id=source_id,
            retained_at=retained_at,
            material=step_one_material,
            session_id=event.session_id,
            task_id=event.task_id,
            user_id=event.user_id,
        )
        outcome = "unavailable"
        reason = self._bootstrap_unavailable_reason
        matched_case_id = None
        if self._bootstrap_profile is not None:
            outcome, reason, matched_case_id = (
                BootstrapTextPreparationProducer.classify_projection_eligibility(
                    profile=self._bootstrap_profile,
                    ingress=authenticated_ingress,
                    projection=step_one_material.semantic_text_projection,
                )
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
            bootstrap_language_evidence=request.bootstrap_language_evidence,
            )
        prepared_admission = self._admit_with_writer_retry(prepare)
        if outcome == "selected_pipeline_pending":
            handoff_with_lease = self._bootstrap_prepare_and_handoff(
                prepared_admission=prepared_admission,
                authenticated_ingress=authenticated_ingress,
                canonical_evidence_arena=canonical_evidence_arena,
            )
            if handoff_with_lease is None:
                return (
                    result.model_copy(
                        update={
                            "transcript_ids": [governed_source.memory_id],
                            "candidate_ids": [],
                            "allowed_candidate_domains": [],
                            "blocked_reasons": {
                                **result.blocked_reasons,
                                "semantic_ingestion": "source_only",
                            },
                        }
                    ),
                    None,
                    None,
                )
            handoff, canonical_evidence_lease = handoff_with_lease
            fence = prepared_admission.operation_fence_binding
            # V3 binds the handoff's exact generation-one predecessor into its
            # recovery probe.  Acquiring the ordinary pipeline lease here
            # would advance that control before the probe can linearize its
            # ready control and claim.  Run the V3 normalization boundary
            # first; it creates the ordinary session only after publication.
            if (
                handoff.marker is not None
                and hasattr(handoff.marker, "recovery_key_digest")
            ):
                try:
                    terminal, authorization_guard = self._run_semantic_ingestion(
                        operation_id=fence.operation_id,
                        observation=self._load_admitted_observation(fence),
                        authenticated_ingress=authenticated_ingress,
                        lease_session=None,
                        operation_fence=fence,
                        bootstrap_handoff=handoff,
                        canonical_evidence_arena=canonical_evidence_arena,
                        canonical_evidence_lease=canonical_evidence_lease,
                    )
                except PreplanningStoreError:
                    terminal = SemanticTerminalOutcome.create(
                        operation_id=fence.operation_id,
                        status="evidence_only",
                        reason_codes=("graph_transaction_authority_unavailable",),
                        candidates=(),
                        temporal_closures=(),
                        attempt_count=0,
                    )
                    authorization_guard = None
                except (OSError, SemanticAnalysisOutage):
                    terminal = None
                    authorization_guard = None
                finally:
                    if canonical_evidence_lease is not None:
                        canonical_evidence_lease.release()
                if (
                    terminal is None
                    or "source_alignment_authority_unavailable" in terminal.reason_codes
                ):
                    return (
                        result.model_copy(update={
                            "transcript_ids": [governed_source.memory_id],
                            "candidate_ids": [],
                            "allowed_candidate_domains": [],
                            "blocked_reasons": {
                                **result.blocked_reasons,
                                "semantic_ingestion": "source_alignment_authority_unavailable",
                            },
                        }),
                        None,
                        None,
                    )
                if "graph_transaction_authority_unavailable" in terminal.reason_codes:
                    return (
                        result.model_copy(update={
                            "transcript_ids": [governed_source.memory_id],
                            "candidate_ids": [],
                            "allowed_candidate_domains": [],
                            "blocked_reasons": {
                                **result.blocked_reasons,
                                "semantic_ingestion": "graph_transaction_authority_unavailable",
                            },
                        }),
                        None,
                        None,
                    )
                if "bootstrap_graph_terminal_persisted" in terminal.reason_codes:
                    return (
                        result.model_copy(update={
                            "transcript_ids": [governed_source.memory_id],
                            "candidate_ids": [],
                            "allowed_candidate_domains": [],
                            "blocked_reasons": {
                                **result.blocked_reasons,
                                "semantic_ingestion": "source_only",
                            },
                        }),
                        None,
                        None,
                    )
                if "bootstrap_graph_retry_persisted" in terminal.reason_codes:
                    return (
                        result.model_copy(update={
                            "transcript_ids": [governed_source.memory_id],
                            "candidate_ids": [],
                            "allowed_candidate_domains": [],
                            "blocked_reasons": {
                                **result.blocked_reasons,
                                "semantic_ingestion": "source_only",
                            },
                        }),
                        None,
                        None,
                    )
                try:
                    self._persist_semantic_terminal(
                        fence,
                        terminal,
                        authorization_guard=authorization_guard,
                    )
                except (OSError, SemanticAuthorizationReadSetError):
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
                return (
                    result.model_copy(update={
                        "transcript_ids": [governed_source.memory_id],
                        "candidate_ids": [],
                        "allowed_candidate_domains": [],
                        "blocked_reasons": {
                            **result.blocked_reasons,
                            "semantic_ingestion": "source_only",
                        },
                    }),
                    None,
                    None,
                )
            elif canonical_evidence_lease is not None:
                # A non-V3 handoff cannot reach the recovery reload consumer;
                # release the writer-boundary lease before the ordinary path.
                canonical_evidence_lease.release()
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
                        observation=self._load_admitted_observation(fence),
                        authenticated_ingress=execution_plan.authenticated_ingress,
                        lease_session=lease_session,
                        operation_fence=fence,
                        bootstrap_handoff=handoff,
                        canonical_evidence_arena=canonical_evidence_arena,
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
            if "source_alignment_authority_unavailable" in terminal.reason_codes:
                # A graph-free normalization non-commit is intentionally not a
                # semantic terminal.  Persisting it would create a terminal
                # bypass around the mandatory source-alignment checkpoint.
                return (
                    result.model_copy(
                        update={
                            "transcript_ids": [governed_source.memory_id],
                            "candidate_ids": [],
                            "allowed_candidate_domains": [],
                            "blocked_reasons": {
                                **result.blocked_reasons,
                                "semantic_ingestion": "source_alignment_authority_unavailable",
                            },
                        }
                    ),
                    None,
                    None,
                )
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
                handoff = self._atomic_store.load_bootstrap_writer_handoff_marker_v3(
                    operation_fence_binding=control.operation_fence
                )
                arena_factory = self._canonical_evidence_arena_factory
                if arena_factory is None:
                    outcomes.append(self._retryable_outcome(control))
                    continue
                try:
                    with arena_factory() as canonical_evidence_arena:
                        lease = None
                        bootstrap_handoff = None
                        if handoff is not None:
                            current = self._writer_admission.current()
                            if (
                                handoff.writer_commit_binding.admission_digest
                                != current.admission_digest
                                or handoff.writer_commit_binding.expected_writer_epoch
                                != current.writer_epoch
                            ):
                                lease_session.checkpoint_retryable(
                                    stage="writer", failure_kind="writer_unavailable"
                                )
                                outcomes.append(self._retryable_outcome(control))
                                continue
                            lease = self._stage_recovery_prepared_source(
                                observation=self._load_admitted_observation(
                                    control.operation_fence
                                ),
                                authenticated_ingress=plan.authenticated_ingress,
                                handoff_marker=handoff,
                                canonical_evidence_arena=canonical_evidence_arena,
                            )
                            if canonical_evidence_arena.enabled and lease is None:
                                outcomes.append(self._retryable_outcome(control))
                                continue
                            bootstrap_handoff = BootstrapWriterHandoffResult.create(
                                kind="already_started", marker=handoff
                            )
                        try:
                            terminal, guard = self._run_semantic_ingestion(
                                operation_id=plan.operation_id,
                                observation=self._load_admitted_observation(control.operation_fence),
                                authenticated_ingress=plan.authenticated_ingress,
                                lease_session=lease_session,
                                operation_fence=control.operation_fence,
                                bootstrap_handoff=bootstrap_handoff,
                                canonical_evidence_arena=canonical_evidence_arena,
                                canonical_evidence_lease=lease,
                            )
                        finally:
                            if lease is not None:
                                lease.release()
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
                if "source_alignment_authority_unavailable" in terminal.reason_codes:
                    # Do not turn an unavailable source-normalization authority
                    # into a persisted terminal during replay.
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
                return self._atomic_store.publish_admitted_source(
                    prepared=prepared,
                    writer_binding=self._current_writer_binding(),
                )
            except SemanticWriterAdmissionError as exc:
                if attempt or "atomic admission index binding is mismatched" not in str(exc):
                    raise
        raise AssertionError("unreachable writer retry loop")

    def _bootstrap_prepare_and_handoff(
        self,
        *,
        prepared_admission,
        authenticated_ingress: AuthenticatedIngressContext,
        canonical_evidence_arena: CanonicalEvidenceArena,
    ) -> tuple[BootstrapWriterHandoffResult, CanonicalEvidenceLease | None] | None:
        """Bridge admitted Step-1 authority to the only writer-start boundary.

        On success the sealed lease stays open for the caller's semantic
        ingestion pass, mirroring the recovery loop's lease lifetime; every
        failure path releases it exactly once.
        """
        profile = self._bootstrap_profile
        runtime = self._semantic_runtime
        if profile is None or runtime is None:
            return None
        preparation = runtime.text_preparation_service
        policy = runtime.text_preparation_policy
        if preparation is None or policy is None:
            return None
        admission = prepared_admission
        observation = self._load_admitted_observation(admission.operation_fence_binding)
        language_evidence = observation.bootstrap_language_evidence
        if language_evidence is None:
            return None
        authorization = DeliveryAuthorizationRequest(
            delivery_identity=admission.delivery_identity,
            ingress=authenticated_ingress,
        )
        publication_assertion = self._atomic_store.assert_current_bootstrap_release(
            authorization=authorization,
            release_evidence=profile.release_evidence,
            assertion_phase="prepared_publication",
        )
        if publication_assertion is None:
            return None
        try:
            prepared = preparation.prepare(
                TextPreparationRequest(observation=observation, policy=policy)
            )
        except ValueError:
            return None
        pin = BootstrapAdmissionPin.create(
            coordinate=profile.coordinate,
            profile_digest=profile.artifacts.profile_manifest.profile_digest,
            release_evidence_digest=profile.release_evidence.evidence_digest,
            bootstrap_language_evidence_digest=language_evidence.evidence_digest,
            source_id=admission.source_id,
            source_digest=admission.source_digest,
            operation_fence_binding_digest=admission.operation_fence_binding.binding_digest,
        )
        try:
            published, prepared_generation = (
                self._atomic_store.publish_bootstrap_prepared_source_if_absent(
                    prepared_source=prepared,
                    authority_pin=pin,
                    release_evidence=profile.release_evidence,
                    language_evidence=language_evidence,
                    grammar_proofs=prepared.grammar_proofs,
                    operation_fence_binding=admission.operation_fence_binding,
                    authorization=authorization,
                    release_assertion=publication_assertion,
                )
            )
        except (PreplanningStoreError, ValueError):
            return None
        if isinstance(published, BootstrapRetainedPendingAuthorityUnavailable):
            return None
        try:
            published_prepared = type(prepared).model_validate(
                published.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            return None
        retry_assertion = self._atomic_store.assert_current_bootstrap_release(
            authorization=authorization,
            release_evidence=profile.release_evidence,
            assertion_phase="pre_handoff_retry",
        )
        if retry_assertion is None:
            return None
        current = self._writer_admission.current()
        staged = encode_semantic_contract_result(
            published_prepared,
            canonical_staging=canonical_evidence_arena if canonical_evidence_arena.enabled else None,
        )
        lease = None
        if canonical_evidence_arena.enabled:
            binding = canonical_evidence_arena.bind_and_seal(CanonicalValidationScope(
                tenant=authenticated_ingress.delivery_principal_binding.tenant_partition_id,
                operation=admission.operation_fence_binding.operation_id,
                generation=prepared_generation,
                fence=admission.operation_fence_binding.operation_fence_id,
                writer=f"{current.admission_digest}:{current.writer_epoch}",
            ))
            lease = canonical_evidence_arena.lookup_sealed(
                binding=binding,
                scope=canonical_evidence_arena.scope,
                canonical_contract_bytes=staged.canonical_contract_bytes,
                concrete_contract_type=type(published_prepared),
                profile_revision=CANONICAL_PROFILE_REVISION,
                codec_revision=CANONICAL_CODEC_REVISION,
                domain=staged.domain,
            )
            if lease is None:
                return None
        try:
            handoff = self._atomic_store.bootstrap_writer_handoff(
            BootstrapWriterHandoffRequest.create(
                source_id=admission.source_id,
                source_digest=admission.source_digest,
                prepared_generation=prepared_generation,
                prepared_source_digest=sha256(staged.canonical_contract_bytes).hexdigest(),
                authority_pin=pin,
                release_evidence=profile.release_evidence,
                bootstrap_language_evidence=language_evidence,
                delivery_identity=admission.delivery_identity,
                operation_fence_binding=admission.operation_fence_binding,
                current_delivery_authorization=authorization,
                current_release_assertion=retry_assertion,
                expected_writer_admission_digest=current.admission_digest,
                expected_writer_epoch=current.writer_epoch,
            ),
                canonical_evidence_lease=lease,
            )
        except BaseException:
            if lease is not None:
                lease.release()
            raise
        if isinstance(handoff, BootstrapHandoffAccessDenied) or handoff.kind not in {
            "started",
            "already_started",
        }:
            if lease is not None:
                lease.release()
            return None
        marker = handoff.marker
        if marker is None or marker.operation_fence_binding != admission.operation_fence_binding:
            if lease is not None:
                lease.release()
            return None
        current = self._writer_admission.current()
        if (
            marker.writer_commit_binding.admission_digest != current.admission_digest
            or marker.writer_commit_binding.expected_writer_epoch != current.writer_epoch
        ):
            if lease is not None:
                lease.release()
            return None
        return handoff, lease

    def _stage_recovery_prepared_source(
        self,
        *,
        observation: SourceObservation,
        authenticated_ingress: AuthenticatedIngressContext,
        handoff_marker,
        canonical_evidence_arena: CanonicalEvidenceArena,
    ) -> CanonicalEvidenceLease | None:
        """Stage one revalidated retained PreparedSource for one recovery owner."""
        runtime = self._semantic_runtime
        if runtime is None or runtime.prepared_source_repository is None:
            return None
        try:
            prepared = runtime.prepared_source_repository.load(
                source_id=observation.source_id,
                source_digest=observation.source_digest or "",
            )
            if prepared is None:
                return None
            prepared = type(prepared).model_validate(prepared.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError):
            return None
        if (
            prepared.source_id != handoff_marker.source_id
            or prepared.source_digest != handoff_marker.source_digest
            or handoff_marker.operation_fence_binding.source_id != observation.source_id
            or handoff_marker.operation_fence_binding.source_digest != observation.source_digest
        ):
            return None
        current = self._writer_admission.current()
        if (
            handoff_marker.writer_commit_binding.admission_digest != current.admission_digest
            or handoff_marker.writer_commit_binding.expected_writer_epoch != current.writer_epoch
        ):
            return None
        staged = encode_semantic_contract_result(
            prepared,
            canonical_staging=canonical_evidence_arena if canonical_evidence_arena.enabled else None,
        )
        if not canonical_evidence_arena.enabled:
            return None
        binding = canonical_evidence_arena.bind_and_seal(
            CanonicalValidationScope(
                tenant=authenticated_ingress.delivery_principal_binding.tenant_partition_id,
                operation=handoff_marker.operation_fence_binding.operation_id,
                generation=handoff_marker.prepared_generation,
                fence=handoff_marker.operation_fence_binding.operation_fence_id,
                writer=f"{current.admission_digest}:{current.writer_epoch}",
            )
        )
        return canonical_evidence_arena.lookup_sealed(
            binding=binding,
            scope=canonical_evidence_arena.scope,
            canonical_contract_bytes=staged.canonical_contract_bytes,
            concrete_contract_type=type(prepared),
            profile_revision=CANONICAL_PROFILE_REVISION,
            codec_revision=CANONICAL_CODEC_REVISION,
            domain=staged.domain,
        )

    def _run_semantic_ingestion(
        self, *, operation_id: str, observation: SourceObservation,
        authenticated_ingress: AuthenticatedIngressContext,
        lease_session: SemanticIngestionLeaseSession | None,
        operation_fence: OperationFenceBinding,
        bootstrap_handoff: BootstrapWriterHandoffResult | None = None,
        canonical_evidence_arena: CanonicalEvidenceArena | None,
        canonical_evidence_lease: CanonicalEvidenceLease | None = None,
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
                source_id=observation.source_id, source_digest=observation.source_digest or ""
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
        if self._semantic_runtime is None:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("semantic_runtime_unauthorized",),
                candidates=(), temporal_closures=(), attempt_count=0,
            ), None
        preparation = self._semantic_runtime.text_preparation_service
        prepared_repository = self._semantic_runtime.prepared_source_repository
        preparation_policy = self._semantic_runtime.text_preparation_policy
        if preparation is None or prepared_repository is None or preparation_policy is None:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("prepared_source_authority_unavailable",),
                candidates=(), temporal_closures=(), attempt_count=0,
            ), None
        try:
            preparation.prepare_and_publish(
                TextPreparationRequest(observation=observation, policy=preparation_policy)
            )
        except ValueError:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("prepared_source_authority_unavailable",),
                candidates=(), temporal_closures=(), attempt_count=0,
            ), None
        source_evidence = self._authenticated_source_evidence(
            source_id=observation.source_id,
            source_digest=observation.source_digest or "",
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
                source_id=observation.source_id,
                source_digest=observation.source_digest or "",
                source_text=observation.text,
            )
        else:
            binding = self._egress_binding_for(
                source_id=observation.source_id,
                source_digest=observation.source_digest or "",
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
                    owner=PromptOwner.SEMANTIC_INGESTION_PROPOSER, variables={}, source_text=observation.text,
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
            source_id=observation.source_id,
            source_digest=observation.source_digest or "",
            now_provider=self._now_provider,
            authority_repository=self._authorization_repository,
        )
        host_bundle = self._semantic_runtime.source_normalization_host_bundle
        if (
            bootstrap_handoff is None
            or host_bundle is None
        ):
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("source_alignment_authority_unavailable",),
                candidates=(),
                temporal_closures=(),
                attempt_count=0,
            ), None
        try:
            prepared_source = prepared_repository.load(
                source_id=observation.source_id,
                source_digest=observation.source_digest or "",
            )
        except ValueError:
            prepared_source = None
        if (
            prepared_source is None
            or prepared_source.status != "complete"
            or prepared_source.source_id != observation.source_id
            or prepared_source.source_digest != observation.source_digest
            or prepared_source.semantic_text != observation.text
        ):
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("source_alignment_authority_unavailable",),
                candidates=(),
                temporal_closures=(),
                attempt_count=0,
            ), None
        invocation = GraphFreeSourceNormalizationInvocation(
            operation_id=operation_id,
            source=prepared_source,
            source_authority_evidence=authority,
            source_interval_evidence=interval,
            policy_bundle=policy.arbitration_bundle,
            authorization_read_set_provider=authorization_guard,
            operation_fence_binding=operation_fence,
        )
        # Recovery precedes transient authority construction.  A found record
        # is a retained publication, not permission to rebuild analyzer state.
        marker = bootstrap_handoff.marker
        try:
            if marker is None or not hasattr(marker, "recovery_key_digest"):
                raise ValueError("V3 bootstrap handoff marker is required")
            key_body = {
                "source_id": prepared_source.source_id,
                "source_digest": prepared_source.source_digest,
                "preparation_fingerprint": prepared_source.preparation_fingerprint,
                "operation_id": operation_id,
                "operation_fence_digest": operation_fence.binding_digest,
                "bootstrap_profile_manifest_digest": marker.release_evidence_digest,
                "handoff_request_digest": marker.handoff_request_digest,
            }
            recovery_key = BootstrapRecoveryKeyV3(
                **key_body,
                recovery_key_digest=contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-recovery-key.v3", key_body
                ),
            )
            if recovery_key.recovery_key_digest != marker.recovery_key_digest:
                raise ValueError("bootstrap recovery key is substituted")
            probe_body = {
                "recovery_key": recovery_key,
                "handoff_marker_digest": marker.marker_digest,
                "expected_predecessor_operation_generation": marker.expected_predecessor_operation_generation,
                "expected_predecessor_artifact_generation": marker.expected_predecessor_artifact_generation,
                "expected_predecessor_control_digest": marker.expected_predecessor_control_digest,
            }
            probe = BootstrapRecoveryProbeV3(
                **probe_body,
                probe_digest=contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-recovery-probe.v3", probe_body
                ),
            )
            recovery = host_bundle.recovery_repository.probe(
                probe=probe,
                server_time=host_bundle.trusted_time.server_time(),
                monotonic_tick=host_bundle.trusted_time.monotonic_tick(),
            )
        except (AttributeError, TypeError, ValueError):
            recovery = None
        if isinstance(recovery, BootstrapRecoveryFoundV3):
            normalized = host_bundle.recovery_repository.reload_found(
                recovery_key_digest=recovery.recovery_key_digest
            )
            if normalized is None:
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id, status="evidence_only",
                    reason_codes=("source_alignment_authority_unavailable",), candidates=(), temporal_closures=(), attempt_count=0,
                ), None
            graph_bundle = self._semantic_runtime.bootstrap_graph_host_bundle
            if (
                type(normalized) is BootstrapSourceNormalizationResultV3
                and graph_bundle is None
            ):
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id,
                    status="evidence_only",
                    reason_codes=("graph_transaction_authority_unavailable",),
                    candidates=(),
                    temporal_closures=(),
                    attempt_count=0,
                ), None
            if graph_bundle is not None:
                try:
                    replay = self._atomic_store.reload_bootstrap_recovery_replay_v3(
                        recovery_key_digest=recovery.recovery_key_digest,
                        canonical_evidence_lease=canonical_evidence_lease,
                        handoff_marker=marker,
                        authenticated_ingress=authenticated_ingress,
                    )
                    graph_reload = graph_bundle.reload_terminal(
                        normalization_replay=replay,
                        authenticated_ingress=authenticated_ingress,
                        required_outcome_scopes=(
                            prepared_source.governance_carrier_artifact.required_outcome_scopes
                        ),
                        operation_fence_binding=operation_fence,
                    )
                except (AttributeError, TypeError, ValueError, PreplanningStoreError):
                    graph_reload = None
                if graph_reload is not None:
                    canonical = graph_reload.canonical_source_result.canonical_source_result
                    return SemanticTerminalOutcome.create(
                        operation_id=operation_id, status="evidence_only",
                        reason_codes=(
                            "bootstrap_graph_terminal_persisted", canonical.final_status,
                        ),
                        candidates=(), temporal_closures=(), attempt_count=0,
                    ), authorization_guard
                try:
                    graph_retry = graph_bundle.reload_retry(
                        normalization_replay=replay,
                        authenticated_ingress=authenticated_ingress,
                        required_outcome_scopes=(
                            prepared_source.governance_carrier_artifact.required_outcome_scopes
                        ),
                        operation_fence_binding=operation_fence,
                    )
                except (AttributeError, TypeError, ValueError, PreplanningStoreError):
                    return SemanticTerminalOutcome.create(
                        operation_id=operation_id,
                        status="evidence_only",
                        reason_codes=("graph_transaction_authority_unavailable",),
                        candidates=(), temporal_closures=(), attempt_count=0,
                    ), None
                if graph_retry is not None:
                    return self._bootstrap_graph_durable_retry_terminal(
                        operation_id=operation_id,
                        retry=graph_retry,
                    ), None
                if lease_session is None:
                    lease_session = self._semantic_terminal_persistence.open_lease_session(
                        fence=operation_fence
                    )
                if lease_session.closed:
                    return SemanticTerminalOutcome.create(
                        operation_id=operation_id, status="evidence_only",
                        reason_codes=("graph_transaction_authority_unavailable",),
                        candidates=(), temporal_closures=(), attempt_count=0,
                    ), None
                try:
                    control = self._atomic_store.get_operation(operation_fence)
                    graph_result = graph_bundle.execute(
                        request=BootstrapGraphAuthorityRequestV3(
                            normalization_replay=replay,
                            prepared_source=prepared_source,
                            authenticated_ingress=authenticated_ingress,
                            required_outcome_scopes=(
                                prepared_source.governance_carrier_artifact.required_outcome_scopes
                            ),
                            operation_fence_binding=operation_fence,
                            operation_lease_binding=self._atomic_store.lease_binding(control),
                            writer_commit_binding=control.writer_binding,
                        )
                    )
                except (AttributeError, TypeError, ValueError, PreplanningStoreError):
                    graph_result = None
                if isinstance(
                    graph_result,
                    (BootstrapGraphDependentCoordinatorSucceededV3, BootstrapGraphFinalizedFailureV3),
                ):
                    canonical = graph_result.terminal_reload.canonical_source_result.canonical_source_result
                    return SemanticTerminalOutcome.create(
                        operation_id=operation_id, status="evidence_only",
                        reason_codes=(
                            "bootstrap_graph_terminal_persisted", canonical.final_status,
                        ),
                        candidates=(), temporal_closures=(), attempt_count=0,
                    ), authorization_guard
                if graph_result is not None and graph_result.kind == "durable_retry":
                    return self._bootstrap_graph_durable_retry_terminal(
                        operation_id=operation_id,
                        retry=graph_result,
                    ), None
                if isinstance(graph_result, BootstrapGraphDependentPreGraphNonCommitV3):
                    if graph_result.reason == "authority_unavailable":
                        return SemanticTerminalOutcome.create(
                            operation_id=operation_id,
                            status="evidence_only",
                            reason_codes=("graph_transaction_authority_unavailable",),
                            candidates=(), temporal_closures=(), attempt_count=0,
                        ), None
                    return SemanticTerminalOutcome.create(
                        operation_id=operation_id,
                        status="evidence_only",
                        reason_codes=("source_only",),
                        candidates=(), temporal_closures=(), attempt_count=0,
                    ), None
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id, status="evidence_only",
                    reason_codes=("graph_transaction_authority_unavailable",),
                    candidates=(), temporal_closures=(), attempt_count=0,
                ), None
            # A lost acknowledgement after finalization must return the sealed
            # terminal before attempting a lease, pipeline, or terminal write.
            recovered_terminal = self._semantic_terminal_persistence.recover_terminal_artifact(
                fence=operation_fence
            )
            if recovered_terminal is not None:
                return recovered_terminal, self._authorization_guard_for_terminal(
                    recovered_terminal, operation_fence
                )
            # A fresh process has no retained in-memory lease session.  Found
            # reuses only the sealed normalization closure, then opens the
            # ordinary terminal-persistence lease for its distinct phase.
            if lease_session is None:
                lease_session = self._semantic_terminal_persistence.open_lease_session(
                    fence=operation_fence
                )
                if lease_session.closed:
                    return SemanticTerminalOutcome.create(
                        operation_id=operation_id, status="evidence_only",
                        reason_codes=("source_alignment_authority_unavailable",), candidates=(), temporal_closures=(), attempt_count=0,
                    ), None
            return pipeline.run(
                operation_id=operation_id, source_id=observation.source_id,
                source_digest=observation.source_digest or "", source_text=observation.text,
                prepared_source_repository=prepared_repository, policy_bundle=policy.arbitration_bundle,
                source_authority_evidence=authority, source_interval_evidence=interval,
                authorization_read_set_provider=authorization_guard,
                independent_assessor=self._semantic_candidate_assessor,
                local_proposals=local_proposals, registered_prompt=registered_prompt,
                egress_binding=binding, egress_policy_provider=self._semantic_egress_policy_provider,
                current_time_provider=self._now_provider, lease_heartbeat=lease_session.heartbeat,
                stage_observer=lease_session.checkpoint, operation_fence=operation_fence,
                source_normalization_result=normalized,
                source_normalization_publication_coordinate=None,
            ), authorization_guard
        if not isinstance(recovery, BootstrapRecoveryClaimedV3):
            return SemanticTerminalOutcome.create(
                operation_id=operation_id, status="evidence_only",
                reason_codes=("source_alignment_authority_unavailable",), candidates=(), temporal_closures=(), attempt_count=0,
            ), None
        source_normalization_authority = host_bundle.authority_provider.build(
            invocation=invocation,
            handoff=bootstrap_handoff,
            recovery_claim=recovery.claim,
        )
        if source_normalization_authority is None:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("source_alignment_authority_unavailable",),
                candidates=(),
                temporal_closures=(),
                attempt_count=0,
            ), None
        normalized = host_bundle.execution_owner.normalize_after_recovery_claim(
            invocation=invocation,
            handoff=bootstrap_handoff,
            recovery_claim=recovery.claim,
            authority=source_normalization_authority,
        )
        if isinstance(normalized, SourceNormalizationNonCommit):
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("source_alignment_authority_unavailable",),
                candidates=(),
                temporal_closures=(),
                attempt_count=0,
            ), None
        if type(normalized) is BootstrapSourceNormalizationResultV3:
            normalized = validate_reloaded_bootstrap_v3_source_normalization_result(
                result=normalized, source=prepared_source
            )
        else:
            normalized = validate_reloaded_source_normalization_result(
                result=normalized,
                source=prepared_source,
                operation_fence_binding=operation_fence,
                publication_coordinate=getattr(
                    getattr(source_normalization_authority, "publication", None),
                    "publication_coordinate",
                    None,
                ),
            )
        if normalized is None:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("source_alignment_authority_unavailable",),
                candidates=(),
                temporal_closures=(),
                attempt_count=0,
            ), None
        graph_bundle = self._semantic_runtime.bootstrap_graph_host_bundle
        if type(normalized) is BootstrapSourceNormalizationResultV3:
            if graph_bundle is None:
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id, status="evidence_only",
                    reason_codes=("graph_transaction_authority_unavailable",),
                    candidates=(), temporal_closures=(), attempt_count=0,
                ), None
            if lease_session is None:
                lease_session = self._semantic_terminal_persistence.open_lease_session(
                    fence=operation_fence
                )
                if lease_session.closed:
                    return SemanticTerminalOutcome.create(
                        operation_id=operation_id, status="evidence_only",
                        reason_codes=("graph_transaction_authority_unavailable",),
                        candidates=(), temporal_closures=(), attempt_count=0,
                    ), None
            try:
                replay = self._atomic_store.reload_bootstrap_recovery_replay_v3(
                    recovery_key_digest=recovery_key.recovery_key_digest,
                    canonical_evidence_lease=canonical_evidence_lease,
                    handoff_marker=marker,
                    authenticated_ingress=authenticated_ingress,
                )
                control = self._atomic_store.get_operation(operation_fence)
                graph_result = graph_bundle.execute(
                    request=BootstrapGraphAuthorityRequestV3(
                        normalization_replay=replay,
                        prepared_source=prepared_source,
                        authenticated_ingress=authenticated_ingress,
                        required_outcome_scopes=(
                            prepared_source.governance_carrier_artifact.required_outcome_scopes
                        ),
                        operation_fence_binding=operation_fence,
                        operation_lease_binding=self._atomic_store.lease_binding(control),
                        writer_commit_binding=control.writer_binding,
                    )
                )
            except (AttributeError, TypeError, ValueError, PreplanningStoreError):
                graph_result = None
            if isinstance(
                graph_result,
                (BootstrapGraphDependentCoordinatorSucceededV3, BootstrapGraphFinalizedFailureV3),
            ):
                canonical = graph_result.terminal_reload.canonical_source_result.canonical_source_result
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id,
                    status="evidence_only",
                    reason_codes=("bootstrap_graph_terminal_persisted", canonical.final_status),
                    candidates=(), temporal_closures=(), attempt_count=0,
                ), authorization_guard
            if graph_result is not None and graph_result.kind == "durable_retry":
                return self._bootstrap_graph_durable_retry_terminal(
                    operation_id=operation_id,
                    retry=graph_result,
                ), None
            if isinstance(graph_result, BootstrapGraphDependentPreGraphNonCommitV3):
                reason = (
                    "graph_transaction_authority_unavailable"
                    if graph_result.reason == "authority_unavailable"
                    else "source_only"
                )
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id,
                    status="evidence_only",
                    reason_codes=(reason,),
                    candidates=(), temporal_closures=(), attempt_count=0,
                ), None
            return SemanticTerminalOutcome.create(
                operation_id=operation_id, status="evidence_only",
                reason_codes=("graph_transaction_authority_unavailable",),
                candidates=(), temporal_closures=(), attempt_count=0,
            ), None
        if lease_session is None:
            # Deliberately after V3 probe/claim, authority construction, and
            # atomic source-normalization publication.  The claim snapshot is
            # the only control authority for those effects.
            lease_session = self._semantic_terminal_persistence.open_lease_session(
                fence=operation_fence
            )
            if lease_session.closed:
                return SemanticTerminalOutcome.create(
                    operation_id=operation_id,
                    status="evidence_only",
                    reason_codes=("source_alignment_authority_unavailable",),
                    candidates=(),
                    temporal_closures=(),
                    attempt_count=0,
                ), None
        return pipeline.run(
            operation_id=operation_id,
            source_id=observation.source_id,
            source_digest=observation.source_digest or "",
            source_text=observation.text,
            prepared_source_repository=prepared_repository,
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
            source_normalization_result=normalized,
            source_normalization_publication_coordinate=getattr(
                getattr(source_normalization_authority, "publication", None),
                "publication_coordinate",
                None,
            ),
        ), authorization_guard

    def _load_admitted_observation(self, fence: OperationFenceBinding) -> SourceObservation:
        """Reload the immutable source record before a learned stage or replay."""

        record = self._memory_plane.get_record(fence.source_id)
        if record is None:
            raise RuntimeError("admitted source record is unavailable")
        observation = source_observation_from_record(record)
        if (
            not observation.is_governed_admission
            or observation.source_id != fence.source_id
            or observation.source_digest != fence.source_digest
        ):
            raise RuntimeError("admitted source observation is substituted")
        return observation

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
    def _bootstrap_graph_durable_retry_terminal(
        *,
        operation_id: str,
        retry: BootstrapGraphDurableRetryProgressV3,
    ) -> SemanticTerminalOutcome:
        """Keep V3 retry provenance internal until the outer public mapping."""
        return SemanticTerminalOutcome.create(
            operation_id=operation_id,
            status="evidence_only",
            reason_codes=("bootstrap_graph_retry_persisted", retry.reason),
            candidates=(),
            temporal_closures=(),
            attempt_count=0,
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
