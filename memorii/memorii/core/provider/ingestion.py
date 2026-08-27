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
    SemanticPipelinePolicyProvider,
    SemanticTerminalOutcome,
    SourceAuthority,
    SourceAuthorityEvidence,
    TextPreparationRequest,
    TimeInterval,
    contract_digest,
    encode_semantic_contract_result,
)
from memorii.core.semantic_ingestion.persistence import (
    SemanticAuthorizationReadSetError,
    SemanticIngestionLeaseSession,
    SemanticTerminalPersistenceService,
)
from memorii.core.semantic_ingestion.source_normalization_execution import (
    SourceNormalizationNonCommit,
)
from memorii.core.semantic_ingestion.source_normalization_stage import (
    GraphFreeSourceNormalizationInvocation,
    validate_reloaded_bootstrap_v3_source_normalization_result,
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
        source_id: str,
        source_digest: str,
        now_provider: Callable[[], datetime],
        authority_repository: SemanticAuthorizationAuthorityRepository,
        policy_bundle: SemanticArbitrationPolicyBundle | None = None,
    ) -> None:
        self._runtime = runtime
        self._profile = profile
        self._policy_provider = policy_provider
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
        read_set = SemanticAuthorizationReadSet.create(
            policy_bundle=policy_bundle,
            deployment_authorization_digest=deployment.authorization_digest,
            deployment_active_epoch=deployment.active_epoch,
            deployment_decision_digest=deployment.decision_digest,
        )
        valid_until = deployment.expires_at
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
        semantic_policy_provider: SemanticPipelinePolicyProvider | None = None,
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
        self._semantic_policy_provider = semantic_policy_provider
        self._semantic_runtime = semantic_runtime
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
            # Every handoff marker is the V3 marker: the atomic store mints
            # and reloads only that type.  The V3 normalization boundary runs
            # before any lease session so the recovery probe can linearize
            # its ready control and claim first.
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
            except OSError:
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
        return (result.model_copy(update={"transcript_ids": [governed_source.memory_id], "candidate_ids": [], "allowed_candidate_domains": [], "blocked_reasons": {**result.blocked_reasons, "semantic_ingestion": "source_only"}}), None, None)

    def reconcile(self) -> list[ProviderEvolutionOutcome]:
        """Complete retained found publications from retained durable records.

        Admission is marker-keyed: a retained V3 handoff marker, its recovery
        index, the loadable prepared source, and the current writer binding.
        No authenticated ingress is reconstructed, so an unpublished
        normalization is never completed here; exact redelivery remains its
        recovery door.
        """
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
            if terminal is not None:
                guard = self._authorization_guard_for_terminal(
                    terminal, control.operation_fence
                )
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
                continue
            handoff = self._atomic_store.load_bootstrap_writer_handoff_marker_v3(
                operation_fence_binding=control.operation_fence
            )
            if handoff is None:
                continue
            current = self._writer_admission.current()
            if (
                handoff.writer_commit_binding.admission_digest != current.admission_digest
                or handoff.writer_commit_binding.expected_writer_epoch != current.writer_epoch
            ):
                outcomes.append(self._retryable_outcome(control))
                continue
            arena_factory = self._canonical_evidence_arena_factory
            if arena_factory is None:
                outcomes.append(self._retryable_outcome(control))
                continue
            try:
                observation = self._load_admitted_observation(control.operation_fence)
            except RuntimeError:
                outcomes.append(self._retryable_outcome(control))
                continue
            try:
                with arena_factory() as canonical_evidence_arena:
                    lease = self._stage_recovery_prepared_source(
                        observation=observation,
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
                            operation_id=control.operation_fence.operation_id,
                            observation=observation,
                            authenticated_ingress=None,
                            lease_session=None,
                            operation_fence=control.operation_fence,
                            bootstrap_handoff=bootstrap_handoff,
                            canonical_evidence_arena=canonical_evidence_arena,
                            canonical_evidence_lease=lease,
                        )
                    finally:
                        if lease is not None:
                            lease.release()
            except OSError:
                outcomes.append(self._retryable_outcome(control))
                continue
            if "source_alignment_authority_unavailable" in terminal.reason_codes:
                # An unpublished normalization is not completable from
                # retained state; do not persist this as a terminal.
                outcomes.append(self._retryable_outcome(control))
                continue
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
        return _ProviderAuthorizationReadSet(
            runtime=self._semantic_runtime,
            profile=self._bootstrap_profile,
            policy_provider=self._semantic_policy_provider,
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
                tenant=(
                    prepared.governance_carrier_artifact
                    .required_outcome_scopes.tenant_partition_id
                ),
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
        authenticated_ingress: AuthenticatedIngressContext | None,
        lease_session: SemanticIngestionLeaseSession | None,
        operation_fence: OperationFenceBinding,
        bootstrap_handoff: BootstrapWriterHandoffResult | None = None,
        canonical_evidence_arena: CanonicalEvidenceArena | None,
        canonical_evidence_lease: CanonicalEvidenceLease | None = None,
    ) -> tuple[SemanticTerminalOutcome, _ProviderAuthorizationReadSet | None]:
        """Invoke semantic ingestion only with a current server-owned policy snapshot.

        Missing control-plane policy is terminal evidence, never permission to
        serialize a source to a remote transport.  ``authenticated_ingress`` is
        supplied by the live delivery path; the retained-state reconcile door
        passes ``None`` and may complete only an already published (found)
        normalization closure.
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
        authority = None
        interval = None
        if authenticated_ingress is not None:
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
        elif self._semantic_runtime is None or self._bootstrap_profile is None:
            return SemanticTerminalOutcome.create(
                operation_id=operation_id,
                status="evidence_only",
                reason_codes=("authenticated_source_or_deployment_authority_unavailable",),
                candidates=(),
                temporal_closures=(),
                attempt_count=0,
            ), None
        authorization_guard = _ProviderAuthorizationReadSet(
            runtime=self._semantic_runtime,
            profile=self._bootstrap_profile,
            policy_provider=self._semantic_policy_provider,
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
        invocation = (
            GraphFreeSourceNormalizationInvocation(
                operation_id=operation_id,
                source=prepared_source,
                source_authority_evidence=authority,
                source_interval_evidence=interval,
                policy_bundle=policy.arbitration_bundle,
                authorization_read_set_provider=authorization_guard,
                operation_fence_binding=operation_fence,
            )
            if authority is not None
            else None
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
                        tenant_partition_id=(
                            prepared_source.governance_carrier_artifact
                            .required_outcome_scopes.tenant_partition_id
                        ),
                    )
                    graph_reload = graph_bundle.reload_terminal(
                        normalization_replay=replay,
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
            # The recovery repository reloads only native V3 closures, and a
            # V3 closure without a graph host was rejected above.  A foreign
            # result type is rejected as foreign rather than pipelined.
            return SemanticTerminalOutcome.create(
                operation_id=operation_id, status="evidence_only",
                reason_codes=("source_alignment_authority_unavailable",), candidates=(), temporal_closures=(), attempt_count=0,
            ), None
        if invocation is None or not isinstance(recovery, BootstrapRecoveryClaimedV3):
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
            # The legacy source-normalization result type is foreign to the
            # retained runtime and is rejected rather than pipelined.
            normalized = None
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
                    tenant_partition_id=(
                        prepared_source.governance_carrier_artifact
                        .required_outcome_scopes.tenant_partition_id
                    ),
                )
                control = self._atomic_store.get_operation(operation_fence)
                graph_result = graph_bundle.execute(
                    request=BootstrapGraphAuthorityRequestV3(
                        normalization_replay=replay,
                        prepared_source=prepared_source,
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
