"""semantic ingestion fail-closed candidate-to-terminal semantic pipeline."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256
from threading import Event, Thread
from typing import Literal, Protocol, TypeVar

from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.semantic_state import CompiledIdentityLineageTransition
from memorii.core.semantic_ingestion.carriers import compile_accepted_carriers
from memorii.core.semantic_ingestion.contracts import (
    BootstrapSourceNormalizationResultV3,
    AnalyzerRoleInterpretation,
    AuthenticatedSourceIntervalEvidence,
    AuthorizationStageSnapshot,
    AuthorizationUsePoint,
    CandidateTransportError,
    GraphFreeInterpretationBundle,
    IndependentSourceAnalysis,
    OperationTemporalAttachmentBinding,
    OperationTemporalDecisionBinding,
    ParserConsensusAssessment,
    PredicateTemporalRule,
    PredicateTrustRule,
    PreparedSource,
    ResolvedTemporalCandidate,
    SealedSemanticOperation,
    SegmentLanguageRouteSet,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SemanticAuthorizationReadSetProvider,
    SemanticCandidate,
    SemanticCandidateAssessor,
    SemanticExecutionLineage,
    SemanticPipelinePolicy,
    SemanticPipelinePolicyProvider,
    SemanticTerminalBindingSet,
    SemanticTerminalOutcome,
    SemanticTransport,
    SourceAuthority,
    SourceAuthorityEvidence,
    SourceLocalIdentityEvidence,
    SourceProposalAlignment,
    SourceSpan,
    SourceTemporalEvidenceSet,
    TemporalEvidenceCandidate,
    TemporalEvidenceDecisionClosure,
    TemporalPolicySnapshot,
    TemporalReferenceEvidence,
    TemporalRole,
    TimeInterval,
    TrustPolicySnapshot,
    contract_digest,
)
from memorii.core.semantic_ingestion.egress import EgressPolicyProvider, ProviderEgressBinding
from memorii.core.semantic_ingestion.local_analyzer import GraphFreeAnalyzerOutput
from memorii.core.semantic_ingestion.operation_assessment import seal_semantic_operation
from memorii.core.semantic_ingestion.prompt_authority import SemanticPromptAuthority
from memorii.core.semantic_ingestion.source_alignment import build_source_proposal_alignment
from memorii.core.semantic_ingestion.source_normalization_stage import (
    validate_reloaded_bootstrap_v3_source_normalization_result,
    validate_reloaded_source_normalization_result,
)
from memorii.core.semantic_ingestion.source_preparation import PreparedSourceRepository

_StageResult = TypeVar("_StageResult")


def require_complete_graph_free_analysis(
    output: GraphFreeAnalyzerOutput, *, source_id: str, source_digest: str, operation_ids: tuple[str, ...]
) -> GraphFreeAnalyzerOutput | None:
    """Expose only a complete two-analyzer source-only intermediate."""
    if output.source_id != source_id or output.source_digest != source_digest:
        return None
    if not output.complete_for(operation_ids) or any(item.status != "stable" for item in output.observations):
        return None
    return output


def build_graph_free_source_alignment(
    *,
    bundle: GraphFreeInterpretationBundle,
    parser_consensus: tuple[ParserConsensusAssessment, ...],
    segment_language_routes: SegmentLanguageRouteSet,
    predicate_event_ids: tuple[str, ...],
    predicate_event_inventory_fingerprint: str,
    coverage_policy_fingerprint: str,
    temporal_candidates: tuple[ResolvedTemporalCandidate, ...],
) -> SourceProposalAlignment | None:
    """Canonical graph-free intermediate, deliberately before terminalization."""
    return build_source_proposal_alignment(
        bundle=bundle,
        parser_consensus=parser_consensus,
        segment_language_routes=segment_language_routes,
        predicate_event_ids=predicate_event_ids,
        predicate_event_inventory_fingerprint=predicate_event_inventory_fingerprint,
        coverage_policy_fingerprint=coverage_policy_fingerprint,
        temporal_candidates=temporal_candidates,
    )


class SemanticAnalysisOutage(OSError):
    """The independent analysis boundary is retryably unavailable."""


class LearnedStageRenewalScheduler(Protocol):
    """Run one blocking learned stage while renewing its lease ownership."""

    def run(
        self,
        *,
        call: Callable[[], _StageResult],
        heartbeat: Callable[[], None],
    ) -> _StageResult: ...


class IdentityLineageCompiler(Protocol):
    """Graph-owned compiler for already grounded identity operations."""

    def compile_transition(
        self,
        *,
        operation: SealedSemanticOperation,
        candidate: SemanticCandidate,
        source_analysis: IndependentSourceAnalysis,
    ) -> CompiledIdentityLineageTransition: ...


class AcceptedIdentityOperationPlanner(Protocol):
    def prepare_accepted_identity_operation(
        self,
        *,
        operation: SealedSemanticOperation,
        candidate: SemanticCandidate,
        source_analysis: IndependentSourceAnalysis,
        operation_fence: OperationFenceBinding,
        authorization_read_set: SemanticAuthorizationReadSet,
    ) -> None: ...


class _ThreadedLearnedStageRenewalScheduler:
    """Production renewal scheduler for blocking provider boundaries."""

    def __init__(self, *, interval_seconds: float) -> None:
        self._interval_seconds = interval_seconds

    def run(
        self,
        *,
        call: Callable[[], _StageResult],
        heartbeat: Callable[[], None],
    ) -> _StageResult:
        heartbeat()
        stopped = Event()
        lease_errors: list[BaseException] = []

        def renew() -> None:
            while not stopped.wait(self._interval_seconds):
                try:
                    heartbeat()
                except BaseException as exc:
                    lease_errors.append(exc)
                    stopped.set()

        thread = Thread(target=renew, name="memorii-semantic-ingestion-lease-heartbeat", daemon=True)
        thread.start()
        call_error: BaseException | None = None
        results: list[_StageResult] = []
        try:
            results.append(call())
        except BaseException as exc:
            call_error = exc
        finally:
            stopped.set()
            thread.join()
        if lease_errors:
            raise lease_errors[0]
        heartbeat()
        if call_error is not None:
            raise call_error
        if len(results) != 1:
            raise AssertionError("learned stage completed without one result")
        return results[0]


class TemporalEvidenceResolver:
    """Resolve certified complete intervals by policy rank; never combine bounds."""

    def resolve(
        self,
        *,
        predicate_id: str,
        candidates: tuple[TemporalEvidenceCandidate, ...],
        reference_evidence: TemporalReferenceEvidence | None = None,
        source_present_attachment: bool = False,
        trust_policy: TrustPolicySnapshot,
        temporal_policy: TemporalPolicySnapshot,
        arbitration_as_of: datetime,
    ) -> TemporalEvidenceDecisionClosure:
        # Revalidate model-copy/replay inputs and both complete policy snapshots
        # before any authority value can influence selection.
        TrustPolicySnapshot.model_validate(trust_policy.model_dump(mode="python"))
        TemporalPolicySnapshot.model_validate(temporal_policy.model_dump(mode="python"))
        rule = trust_policy.rule_for(predicate_id)
        temporal_rule = temporal_policy.rule_for(predicate_id)
        ordered = tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id))
        if len({candidate.candidate_id for candidate in ordered}) != len(ordered):
            return self._closure("unknown", ordered, (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
        if temporal_rule.valid_time_requirement == "atemporal":
            if ordered or source_present_attachment:
                return self._closure("unknown", ordered, (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
            return self._closure("pass", (), (), (), None, "atemporal", trust_policy, temporal_policy, arbitration_as_of)
        if not ordered:
            if reference_evidence is not None and (
                temporal_rule.allow_reference_as_effective_start and temporal_rule.allow_open_end
            ):
                return self._closure(
                    "pass", (), (), (), TimeInterval(start=reference_evidence.reference_instant),
                    "authenticated_reference_open_start", trust_policy, temporal_policy,
                    arbitration_as_of,
                )
            if temporal_rule.valid_time_requirement == "optional" and not source_present_attachment:
                return self._closure("pass", (), (), (), None, "atemporal", trust_policy, temporal_policy, arbitration_as_of)
            return self._closure("unknown", (), (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
        try:
            for candidate in ordered:
                TemporalEvidenceCandidate.model_validate(candidate.model_dump(mode="python"))
                if candidate.interval.end is None and not temporal_rule.allow_open_end:
                    raise ValueError("open interval is disallowed")
                if candidate.source_authority.authority_class not in rule.authority_rank_by_class:
                    raise ValueError("unknown source authority class")
        except ValueError:
            return self._closure("unknown", ordered, (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
        eligible = tuple(
            item for item in ordered
            if item.source_authority.authority_class in rule.eligible_authority_classes
        )
        if not eligible:
            return self._closure("unknown", ordered, (), (), None, "unresolved", trust_policy, temporal_policy, arbitration_as_of)
        top = tuple(
            item for item in eligible
            if not any(self._dominates(other, item, rule) for other in eligible)
        )
        if len({(item.interval.start, item.interval.end) for item in top}) != 1:
            return self._closure(
                "contested", ordered, (), tuple(sorted(item.candidate_id for item in top)), None,
                "trust_contested_nonidentical_top_evidence", trust_policy, temporal_policy, arbitration_as_of,
            )
        interval = top[0].interval
        supporters = tuple(sorted(item.candidate_id for item in eligible if item.interval == interval))
        kinds = {item.kind for item in eligible if item.interval == interval}
        resolution = "trust_co_supported_equal_interval" if len(supporters) > 1 else (
            "trust_selected_text_interval" if kinds == {"certified_text_interval"}
            else "trust_selected_source_interval"
        )
        return self._closure(
            "pass", ordered, supporters, (), interval, resolution,
            trust_policy, temporal_policy, arbitration_as_of,
        )

    @staticmethod
    def _dominates(
        left: TemporalEvidenceCandidate,
        right: TemporalEvidenceCandidate,
        rule: PredicateTrustRule,
    ) -> bool:
        pair = tuple(sorted((left.source_authority.authority_class, right.source_authority.authority_class)))
        if left.source_authority.authority_class != right.source_authority.authority_class and pair in rule.incomparable_class_pairs:
            return False
        return rule.authority_rank_by_class[left.source_authority.authority_class] > rule.authority_rank_by_class[right.source_authority.authority_class]

    @staticmethod
    def _closure(
        outcome: Literal["pass", "unknown", "contested"],
        candidates: tuple[TemporalEvidenceCandidate, ...],
        selected: tuple[str, ...],
        contested: tuple[str, ...],
        interval: TimeInterval | None,
        resolution: str,
        trust: TrustPolicySnapshot,
        temporal: TemporalPolicySnapshot,
        coordinate: datetime,
    ) -> TemporalEvidenceDecisionClosure:
        body = {
            "outcome": outcome,
            "candidates": candidates,
            "selected_candidate_ids": selected,
            "contested_candidate_ids": contested,
            "resolved_interval": interval,
            "resolution_rule": resolution,
            "temporal_policy_fingerprint": temporal.fingerprint,
            "temporal_policy_snapshot_digest": temporal.snapshot_digest,
            "trust_policy_fingerprint": trust.fingerprint,
            "trust_policy_snapshot_digest": trust.snapshot_digest,
            "arbitration_as_of": coordinate,
        }
        return TemporalEvidenceDecisionClosure(
            **body,
            closure_digest=contract_digest(b"memorii.semantic-ingestion.temporal-decision-closure.v1", body),
        )


class SemanticIngestionPipeline:
    """One bounded proposal repair followed by deterministic semantic ingestion reconciliation."""

    _HEARTBEAT_INTERVAL_SECONDS = 10.0

    def __init__(
        self,
        *,
        transport: SemanticTransport | None,
        resolver: TemporalEvidenceResolver | None = None,
        renewal_scheduler: LearnedStageRenewalScheduler | None = None,
        identity_lineage_compiler: IdentityLineageCompiler | None = None,
        identity_operation_planner: AcceptedIdentityOperationPlanner | None = None,
    ) -> None:
        self._transport = transport
        self._resolver = resolver or TemporalEvidenceResolver()
        self._renewal_scheduler = renewal_scheduler or _ThreadedLearnedStageRenewalScheduler(
            interval_seconds=self._HEARTBEAT_INTERVAL_SECONDS
        )
        self._identity_lineage_compiler = identity_lineage_compiler
        self._identity_operation_planner = identity_operation_planner

    def run(
        self,
        *,
        operation_id: str,
        source_id: str,
        source_digest: str,
        source_text: str,
        prepared_source_repository: PreparedSourceRepository | None = None,
        policy_bundle: SemanticArbitrationPolicyBundle | None,
        source_authority_evidence: SourceAuthorityEvidence | None = None,
        source_interval_evidence: AuthenticatedSourceIntervalEvidence | None = None,
        authorization_read_set_provider: SemanticAuthorizationReadSetProvider | None = None,
        independent_assessor: SemanticCandidateAssessor | None = None,
        local_proposals: tuple[SemanticCandidate, ...] | None = None,
        registered_prompt: SemanticPromptAuthority | None = None,
        egress_binding: ProviderEgressBinding | None = None,
        egress_policy_provider: EgressPolicyProvider | None = None,
        current_time_provider: Callable[[], datetime] | None = None,
        lease_heartbeat: Callable[[], None] | None = None,
        stage_observer: Callable[[str, str, bytes], None] | None = None,
        operation_fence: OperationFenceBinding | None = None,
        source_normalization_result: object | None = None,
        source_normalization_publication_coordinate: object | None = None,
    ) -> SemanticTerminalOutcome:
        if not source_id or len(source_digest) != 64 or not source_text:
            return self._terminal(operation_id, "evidence_only", ("source_binding_unavailable",), (), (), 0)
        prepared_source = self._load_prepared_source(
            repository=prepared_source_repository,
            source_id=source_id,
            source_digest=source_digest,
            source_text=source_text,
        )
        if prepared_source is None:
            return self._terminal(operation_id, "evidence_only", ("prepared_source_authority_unavailable",), (), (), 0)
        validated_normalization = (
            validate_reloaded_bootstrap_v3_source_normalization_result(
                result=source_normalization_result, source=prepared_source
            )
            if type(source_normalization_result) is BootstrapSourceNormalizationResultV3
            else validate_reloaded_source_normalization_result(
                result=source_normalization_result,
                source=prepared_source,
                operation_fence_binding=operation_fence,
                publication_coordinate=source_normalization_publication_coordinate,
            )
            if operation_fence is not None
            else None
        )
        if operation_fence is not None and validated_normalization is None:
            return self._terminal(
                operation_id, "evidence_only", ("source_alignment_authority_unavailable",), (), (), 0
            )
        if policy_bundle is None:
            return self._terminal(operation_id, "evidence_only", ("policy_unavailable",), (), (), 0)
        try:
            validated_policy_bundle = SemanticArbitrationPolicyBundle.model_validate(
                policy_bundle.model_dump(mode="python")
            )
        except ValueError:
            return self._terminal(operation_id, "evidence_only", ("policy_bundle_invalid",), (), (), 0)
        trust_policy = validated_policy_bundle.trust_policy
        temporal_policy = validated_policy_bundle.temporal_policy
        arbitration_as_of = validated_policy_bundle.arbitration_as_of
        server_now = current_time_provider or (lambda: datetime.now().astimezone())
        if source_authority_evidence is None:
            return self._terminal(
                operation_id, "evidence_only", ("authenticated_source_authority_unavailable",),
                (), (), 0,
            )
        try:
            validated_authority = SourceAuthorityEvidence.model_validate(
                source_authority_evidence.model_dump(mode="python")
            )
            validated_interval = (
                AuthenticatedSourceIntervalEvidence.model_validate(
                    source_interval_evidence.model_dump(mode="python")
                )
                if source_interval_evidence is not None else None
            )
        except ValueError:
            return self._terminal(
                operation_id, "rejected", ("authenticated_source_evidence_invalid",), (), (), 0,
            )
        if (
            validated_authority.source_id != source_id
            or validated_authority.source_digest != source_digest
            or (
                validated_interval is not None
                and (
                    validated_interval.source_id != source_id
                    or validated_interval.source_digest != source_digest
                    or validated_interval.source_authority_evidence_digest
                    != validated_authority.evidence_digest
                    or validated_interval.policy_revision
                    != validated_authority.authority.policy_revision
                )
            )
        ):
            return self._terminal(
                operation_id, "rejected", ("authenticated_source_evidence_substitution",),
                (), (), 0,
            )
        proposal_attempt_digests: list[str] = []
        egress_decision_digests: list[str] = []
        authorization_read_set: SemanticAuthorizationReadSet | None = None
        if local_proposals is not None:
            if self._transport is not None or registered_prompt is not None or egress_binding is not None:
                return self._terminal(operation_id, "rejected", ("mixed_local_remote_proposal_path",), (), (), 0)
            parsed = self._canonical_candidates(
                tuple(
                    SemanticCandidate.model_validate(value.model_dump(mode="python"))
                    for value in local_proposals
                )
            )
            initial_snapshot = self._current_authorization_snapshot(
                authorization_read_set_provider,
                policy_bundle=validated_policy_bundle,
                use_point="pre_request",
                egress_policy_provider=None,
                egress_binding=None,
                now_provider=server_now,
            )
            if initial_snapshot is None:
                return self._terminal(
                    operation_id, "evidence_only", ("deployment_authorization_unavailable",),
                    parsed, (), 0,
                )
            authorization_read_set = initial_snapshot.read_set
            proposal_attempt_digests.append(
                contract_digest(b"memorii.semantic-ingestion.local-proposal-attempt.v1", parsed)
            )
            self._observe_stage(
                stage_observer,
                "proposal_complete",
                proposal_attempt_digests[-1],
                encode_typed_value(
                    {
                        "kind": "local_proposal_attempt",
                        "candidates": tuple(
                            value.model_dump(mode="python") for value in parsed
                        ),
                    }
                ),
            )
            attempt = 0
        else:
            if self._transport is None or registered_prompt is None or egress_binding is None:
                return self._terminal(operation_id, "evidence_only", ("remote_proposal_authority_unavailable",), (), (), 0)
            transport = self._transport
            try:
                original_request = registered_prompt.serialized_request(source_text=source_text)
            except (TypeError, ValueError):
                return self._terminal(operation_id, "evidence_only", ("registered_prompt_invalid",), (), (), 0)
            request_bytes = original_request
            parsed = None
            attempt = 0
            initial_snapshot = None
            for attempt in range(1, 3):
                request_snapshot = self._current_authorization_snapshot(
                    authorization_read_set_provider,
                    policy_bundle=validated_policy_bundle,
                    use_point="pre_request",
                    egress_policy_provider=egress_policy_provider,
                    egress_binding=egress_binding,
                    now_provider=server_now,
                )
                if (
                    request_snapshot is None
                    or request_snapshot.read_set.egress_policy_revision is None
                    or request_snapshot.read_set.egress_binding is None
                    or request_snapshot.read_set.egress_binding.model_dump(mode="python")
                    != egress_binding.model_dump(mode="python")
                ):
                    return self._terminal(
                        operation_id, "evidence_only", ("remote_egress_policy_unavailable_or_denied",),
                        (), (), attempt - 1,
                    )
                observed_read_set = request_snapshot.read_set
                if authorization_read_set is None:
                    authorization_read_set = observed_read_set
                    initial_snapshot = request_snapshot
                elif observed_read_set != authorization_read_set:
                    return self._terminal(
                        operation_id, "evidence_only", ("authorization_read_set_changed",),
                        (), (), attempt - 1,
                    )
                try:
                    raw = self._run_learned_stage(
                        lambda request=request_bytes: transport.propose(request),
                        lease_heartbeat,
                    )
                    proposal_attempt_digests.append(contract_digest(
                        b"memorii.semantic-ingestion.remote-proposal-attempt.v1",
                        {"request_digest": sha256(request_bytes).hexdigest(), "response_digest": sha256(raw).hexdigest()},
                    ))
                    self._observe_stage(
                        stage_observer,
                        f"proposal_attempt_{attempt}",
                        proposal_attempt_digests[-1],
                        encode_typed_value(
                            {
                                "kind": "remote_proposal_attempt",
                                "request_digest": sha256(request_bytes).hexdigest(),
                                "response_digest": sha256(raw).hexdigest(),
                            }
                        ),
                    )
                    assert request_snapshot.read_set.egress_decision_digest is not None
                    egress_decision_digests.append(
                        request_snapshot.read_set.egress_decision_digest
                    )
                    post_response = self._current_authorization_snapshot(
                        authorization_read_set_provider,
                        policy_bundle=validated_policy_bundle,
                        use_point="post_response",
                        egress_policy_provider=egress_policy_provider,
                        egress_binding=egress_binding,
                        now_provider=server_now,
                    )
                    if (
                        initial_snapshot is None
                        or not self._snapshot_unchanged(initial_snapshot, post_response)
                    ):
                        return self._terminal(
                            operation_id, "evidence_only", ("authorization_changed_after_response",),
                            (), (), attempt,
                        )
                    parsed = self._parse_transport(raw)
                    break
                except CandidateTransportError:
                    if attempt == 2:
                        return self._terminal(operation_id, "rejected", ("candidate_transport_invalid",), (), (), attempt)
                    request_bytes = encode_typed_value({
                        "repair_of": sha256(original_request).hexdigest(),
                        "registered_prompt_authority_digest": registered_prompt.authority_digest,
                        "validation_failure": "candidate_transport_invalid",
                    })
            if parsed is None:
                raise AssertionError("bounded proposal loop ended without a terminal result")
        if authorization_read_set is None:
            return self._terminal(
                operation_id, "evidence_only", ("authorization_read_set_unavailable",),
                parsed, (), attempt,
            )
        analyses = []
        for candidate in parsed:
            if not self._snapshot_unchanged(
                initial_snapshot,
                self._current_authorization_snapshot(
                authorization_read_set_provider,
                policy_bundle=validated_policy_bundle,
                use_point="pre_analysis",
                egress_policy_provider=egress_policy_provider,
                egress_binding=egress_binding,
                now_provider=server_now,
                ),
            ):
                return self._terminal(
                    operation_id, "evidence_only", ("authorization_changed_before_analysis",),
                    parsed, (), attempt,
                )
            try:
                analysis = self._run_learned_stage(
                    lambda proposal=candidate: independent_assessor.analyze(
                        proposal=proposal,
                        source_id=source_id,
                        source_digest=source_digest,
                        source_text=source_text,
                        prepared_source=prepared_source,
                        source_authority_evidence=validated_authority,
                        source_interval_evidence=validated_interval,
                    ),
                    lease_heartbeat,
                ) if independent_assessor is not None else None
            except OSError as exc:
                raise SemanticAnalysisOutage("independent semantic analysis is unavailable") from exc
            if analysis is None:
                return self._terminal(
                    operation_id, "unresolved", ("independent_source_analysis_unavailable",),
                    parsed, (), attempt, arbitration_policy_bundle=validated_policy_bundle,
                )
            try:
                analysis = type(analysis).model_validate(analysis.model_dump(mode="python"))
            except ValueError:
                return self._terminal(operation_id, "rejected", ("independent_source_analysis_invalid",), parsed, (), attempt)
            if (
                analysis.candidate_id != candidate.candidate_id
                or analysis.predicate_id != candidate.predicate_id
                or analysis.operation_kind != candidate.operation_kind
                or analysis.source_id != source_id
                or analysis.source_digest != source_digest
                or source_text[analysis.assertion_span.start:analysis.assertion_span.end] != candidate.assertion_quote
                or analysis.source_authority_evidence != validated_authority
                or not self._analysis_spans_are_valid(
                    analysis=analysis,
                    source_id=source_id,
                    source_text=source_text,
                    prepared_source=prepared_source,
                    source_authority_evidence=validated_authority,
                    source_interval_evidence=validated_interval,
                )
            ):
                return self._terminal(operation_id, "rejected", ("independent_source_analysis_substitution",), parsed, (), attempt)
            analyses.append(analysis)
            self._observe_stage(
                stage_observer,
                f"source_analysis:{candidate.candidate_id}",
                analysis.analysis_digest,
                encode_typed_value(
                    {
                        "kind": "source_analysis",
                        "analysis": analysis.model_dump(mode="python"),
                    }
                ),
            )
        source_analyses = tuple(analyses)
        # The closed V1 scenario pair is evidence of a contested single-valued
        # owner relation, never authority to choose or publish either value.
        if self._is_protected_scenario_owner_pair(parsed, source_analyses):
            return self._terminal(
                operation_id,
                "unresolved",
                ("protected_multi_segment_owner_ambiguity",),
                parsed,
                (),
                attempt,
                source_analyses=source_analyses,
                arbitration_policy_bundle=validated_policy_bundle,
                authorization_read_set=authorization_read_set,
            )
        if not self._snapshot_unchanged(
            initial_snapshot,
            self._current_authorization_snapshot(
            authorization_read_set_provider,
            policy_bundle=validated_policy_bundle,
            use_point="pre_seal",
            egress_policy_provider=egress_policy_provider,
            egress_binding=egress_binding,
            now_provider=server_now,
            ),
        ):
            return self._terminal(
                operation_id, "evidence_only", ("authorization_changed_before_sealing",),
                parsed, (), attempt,
            )

        role_closures_by_candidate: list[tuple[tuple[TemporalRole, TemporalEvidenceDecisionClosure], ...]] = []
        closure_list: list[TemporalEvidenceDecisionClosure] = []
        try:
            for candidate, analysis in zip(parsed, source_analyses, strict=True):
                resolved_roles: list[tuple[TemporalRole, TemporalEvidenceDecisionClosure]] = []
                for source_temporal in analysis.temporal_evidence:
                    role = source_temporal.temporal_role
                    resolved_roles.append(
                        (
                            role,
                            self._resolver.resolve(
                                predicate_id=candidate.predicate_id,
                                candidates=source_temporal.candidates,
                                reference_evidence=source_temporal.reference_evidence,
                                source_present_attachment=bool(source_temporal.attachment_spans),
                                trust_policy=trust_policy,
                                temporal_policy=temporal_policy,
                                arbitration_as_of=arbitration_as_of,
                            ),
                        )
                    )
                role_closures = tuple(resolved_roles)
                role_closures_by_candidate.append(role_closures)
                closure_list.extend(closure for _, closure in role_closures)
        except ValueError:
            return self._terminal(
                operation_id, "unresolved", ("policy_or_temporal_contract_invalid",), parsed, (), attempt,
            )

        sealed_values: list[SealedSemanticOperation] = []
        for candidate, analysis, role_closures in zip(parsed, source_analyses, role_closures_by_candidate, strict=True):
            sealed = seal_semantic_operation(
                source_id=source_id,
                source_digest=source_digest,
                candidate=candidate,
                source_analysis=analysis,
                role_closures=role_closures,
            )
            if sealed is not None:
                sealed_values.append(sealed)
        sealed_operations = tuple(sorted(sealed_values, key=lambda value: value.candidate_id))
        execution_lineage = SemanticExecutionLineage.create(
            operation_id=operation_id,
            proposal_attempt_digests=tuple(proposal_attempt_digests),
            source_analysis_digests=tuple(value.analysis_digest for value in source_analyses),
            sealed_operation_digests=tuple(value.sealed_operation_digest for value in sealed_operations),
            prompt_authority_digest=(
                registered_prompt.authority_digest if registered_prompt is not None else None
            ),
            egress_decision_digests=tuple(egress_decision_digests),
            arbitration_policy_bundle_digest=validated_policy_bundle.bundle_digest,
            authorization_read_set_digest=authorization_read_set.read_set_digest,
        )
        self._observe_stage(
            stage_observer,
            "semantic_sealing_complete",
            execution_lineage.lineage_digest,
            encode_typed_value(
                {
                    "kind": "execution_lineage",
                    "lineage": execution_lineage.model_dump(mode="python"),
                }
            ),
        )

        promotable = (
            bool(parsed)
            and len(sealed_operations) == len(parsed)
            and all(value.parser_consensus.status == "stable" for value in source_analyses)
        )
        identity_transitions: dict[str, CompiledIdentityLineageTransition] = {}
        identity_failure: str | None = None
        if promotable:
            analysis_by_candidate = {
                value.candidate_id: value for value in source_analyses
            }
            candidate_by_id = {candidate.candidate_id: candidate for candidate in parsed}
            for operation in sealed_operations:
                if operation.kind != "identity":
                    continue
                if self._identity_lineage_compiler is None:
                    identity_failure = "identity_lineage_compiler_required"
                    break
                try:
                    if self._identity_operation_planner is not None:
                        if operation_fence is None:
                            raise ValueError("identity operation fence is unavailable")
                        self._identity_operation_planner.prepare_accepted_identity_operation(
                            operation=operation,
                            candidate=candidate_by_id[operation.candidate_id],
                            source_analysis=analysis_by_candidate[operation.candidate_id],
                            operation_fence=operation_fence,
                            authorization_read_set=authorization_read_set,
                        )
                    transition = self._identity_lineage_compiler.compile_transition(
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
        if not promotable:
            binding_sets = tuple(
                SemanticTerminalBindingSet.create(
                    operation_id=operation.operation_id,
                    bindings=operation.temporal_bindings,
                )
                for operation in sorted(sealed_operations, key=lambda value: value.operation_id)
            )
            return self._terminal(
                operation_id,
                "unresolved",
                (
                    identity_failure
                    or "independent_consensus_or_temporal_resolution_failed",
                ),
                parsed,
                tuple(closure_list),
                attempt,
                source_analyses=source_analyses,
                arbitration_policy_bundle=validated_policy_bundle,
                authorization_read_set=authorization_read_set,
                execution_lineage=execution_lineage,
                sealed_operations=sealed_operations,
                terminal_binding_sets=binding_sets,
            )
        candidate_by_id = {candidate.candidate_id: candidate for candidate in parsed}
        carriers = tuple(
            carrier
            for operation in sealed_operations
            for carrier in compile_accepted_carriers(
                operation=operation,
                candidate=candidate_by_id[operation.candidate_id],
                predicate_trust_rule=(
                    validated_policy_bundle.trust_policy.rule_for(
                        candidate_by_id[operation.candidate_id].predicate_id
                    )
                    if operation.claim_identity is not None
                    else None
                ),
                identity_transition=identity_transitions.get(operation.operation_id),
                committed_at=None,
            )
        )
        carriers = tuple(sorted(carriers, key=lambda value: (value.operation_id, value.record_kind, value.record_digest)))
        binding_sets = tuple(
            SemanticTerminalBindingSet.create(
                operation_id=operation.operation_id,
                bindings=operation.temporal_bindings,
            )
            for operation in sorted(sealed_operations, key=lambda value: value.operation_id)
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
            candidates=parsed,
            source_analyses=source_analyses,
            arbitration_policy_bundle=validated_policy_bundle,
            authorization_read_set=authorization_read_set,
            execution_lineage=execution_lineage,
            temporal_closures=tuple(closure_list),
            carrier_artifact_digest=carrier_artifact_digest,
            sealed_operations=sealed_operations,
            accepted_carriers=carriers,
            terminal_binding_sets=binding_sets,
            attempt_count=attempt,
        )

    @staticmethod
    def _current_authorization_snapshot(
        provider: SemanticAuthorizationReadSetProvider | None,
        *,
        policy_bundle: SemanticArbitrationPolicyBundle,
        use_point: AuthorizationUsePoint,
        egress_policy_provider: EgressPolicyProvider | None,
        egress_binding: ProviderEgressBinding | None,
        now_provider: Callable[[], datetime],
    ) -> AuthorizationStageSnapshot | None:
        if provider is None:
            return None
        snapshot_reader = getattr(provider, "current_snapshot", None)
        if callable(snapshot_reader):
            return snapshot_reader(policy_bundle=policy_bundle, use_point=use_point)
        server_now = now_provider()
        decision = None
        if egress_binding is not None:
            if egress_policy_provider is None:
                return None
            decision = egress_policy_provider.current(binding=egress_binding, at=server_now)
            if decision is None:
                return None
        read_set = provider.current_read_set(
            policy_bundle=policy_bundle,
            egress_policy_revision=(decision.policy_revision if decision is not None else None),
            egress_decision_digest=(decision.decision_digest if decision is not None else None),
            use_point={"pre_request": "stage_start", "pre_analysis": "stage_start"}.get(
                use_point, use_point
            ),
        )
        if read_set is None:
            return None
        synthetic = contract_digest(
            b"memorii.semantic-ingestion.test-authorization-authority.v1", read_set
        )
        return AuthorizationStageSnapshot.create(
            use_point=use_point,
            server_now=server_now,
            read_set=read_set,
            egress_policy_id=(decision.policy_id if decision is not None else None),
            egress_policy_fingerprint=(
                decision.policy_fingerprint if decision is not None else None
            ),
            egress_expires_at=(decision.expires_at if decision is not None else None),
            deployment_expires_at=server_now + timedelta(days=3650),
            authority_record_id=f"test-authorization:{synthetic}",
            authority_revision=1,
            authority_coordinates_digest=synthetic,
            authority_record_digest=synthetic,
        )

    @staticmethod
    def _snapshot_unchanged(
        expected: AuthorizationStageSnapshot | None,
        observed: AuthorizationStageSnapshot | None,
    ) -> bool:
        return (
            expected is not None
            and observed is not None
            and observed.read_set == expected.read_set
            and observed.authority_record_id == expected.authority_record_id
            and observed.authority_revision == expected.authority_revision
            and observed.authority_coordinates_digest
            == expected.authority_coordinates_digest
            and observed.authority_record_digest == expected.authority_record_digest
        )

    @staticmethod
    def _is_protected_scenario_owner_pair(
        candidates: tuple[SemanticCandidate, ...],
        analyses: tuple[IndependentSourceAnalysis, ...],
    ) -> bool:
        """Recognize only the closed, two-segment V1 owner ambiguity form."""
        if len(candidates) != 2 or len(analyses) != 2:
            return False
        if any(candidate.predicate_id != "owner" for candidate in candidates):
            return False
        if tuple(analysis.candidate_id for analysis in analyses) != tuple(
            candidate.candidate_id for candidate in candidates
        ):
            return False
        ordered_pairs = tuple(
            pair
            for _, pair in sorted(
                zip(
                    analyses,
                    zip(candidates, analyses, strict=True),
                    strict=True,
                ),
                key=lambda item: (
                    item[0].assertion_span.start,
                    item[0].assertion_span.end,
                    item[0].parser_consensus.segment_id,
                ),
            )
        )
        expected_quotes = ("Atlas owner is Alice.", "Atlas owner is Bob.")
        if tuple(candidate.assertion_quote for candidate, _ in ordered_pairs) != expected_quotes:
            return False
        source_coordinates = {
            (analysis.source_id, analysis.source_digest) for analysis in analyses
        }
        route_coordinates = {
            (
                analysis.parser_consensus.segment_id,
                analysis.parser_consensus.segment_language_route_digest,
            )
            for analysis in analyses
        }
        return len(source_coordinates) == 1 and len(route_coordinates) == 2

    @staticmethod
    def _analysis_spans_are_valid(
        *,
        analysis: IndependentSourceAnalysis,
        source_id: str,
        source_text: str,
        prepared_source: PreparedSource,
        source_authority_evidence: SourceAuthorityEvidence,
        source_interval_evidence: AuthenticatedSourceIntervalEvidence | None,
    ) -> bool:
        # The retired local analyzer has no canonical analysis to supply. A
        # caller that does supply the strict assessment must at least retain the
        # exact source coordinates; deeper route/proof closure is validated by
        # the consensus and source-alignment contracts before normalization.
        consensus = analysis.parser_consensus
        selected = tuple(
            (segment, route)
            for segment, route in zip(
                prepared_source.segments,
                prepared_source.segment_language_routes.routes,
                strict=True,
            )
            if segment.segment_id == consensus.segment_id
        )
        if len(selected) != 1:
            return False
        segment, route = selected[0]

        def binds_selected_route(span) -> bool:
            artifact = span.segment_local_span.artifact
            return (
                span.source_id == source_id
                and span.projection_segment_id == segment.parent_projection_segment_id
                and artifact.artifact_id == route.segment_text_artifact_id
                and artifact.artifact_digest == route.segment_text_artifact_digest
                and artifact.content_digest == route.segment_text_content_digest
            )

        copied_spans = tuple(
            span
            for interpretation in (
                consensus.primary_interpretation,
                consensus.corroborating_interpretation,
            )
            for span in (
                interpretation.predicate_head_span,
                *(assignment.argument_span for assignment in interpretation.assignments),
            )
        )
        return (
            consensus.source_id == source_id
            and consensus.source_digest == analysis.source_digest
            and analysis.source_id == source_id
            and analysis.source_digest == source_authority_evidence.source_digest
            and consensus.preparation_fingerprint == prepared_source.preparation_fingerprint
            and consensus.segment_language_route_digest == route.route_digest
            # The admitted source digest identifies the immutable source record,
            # not necessarily the raw text bytes. Exact text binding is instead
            # carried by the prepared SourceSpanReference artifacts.
            and consensus.primary_interpretation.predicate_head_span.source_id == source_id
            and consensus.corroborating_interpretation.predicate_head_span.source_id == source_id
            and all(binds_selected_route(span) for span in copied_spans)
        )

    @staticmethod
    def _load_prepared_source(
        *, repository: PreparedSourceRepository | None, source_id: str, source_digest: str, source_text: str
    ) -> PreparedSource | None:
        if repository is None:
            return None
        try:
            prepared = repository.load(source_id=source_id, source_digest=source_digest)
            if prepared is None:
                return None
            prepared = PreparedSource.model_validate(prepared.model_dump(mode="python"))
        except ValueError:
            return None
        if (
            prepared.status == "complete"
            and prepared.source_id == source_id
            and prepared.source_digest == source_digest
            and prepared.semantic_text == source_text
            and prepared.segments
        ):
            return prepared
        return None

    def _run_learned_stage(
        self,
        call: Callable[[], _StageResult],
        heartbeat: Callable[[], None] | None,
    ) -> _StageResult:
        """Renew ownership while a blocking proposer or analyzer call runs."""
        if heartbeat is None:
            return call()
        return self._renewal_scheduler.run(call=call, heartbeat=heartbeat)

    @staticmethod
    def _observe_stage(
        observer: Callable[[str, str, bytes], None] | None,
        stage: str,
        artifact_digest: str,
        canonical_artifact_payload: bytes,
    ) -> None:
        if observer is not None:
            observer(stage, artifact_digest, canonical_artifact_payload)

    @staticmethod
    def _terminal(
        operation_id: str,
        status: Literal["accepted", "unresolved", "rejected", "evidence_only"],
        reason_codes: tuple[str, ...],
        candidates: tuple[SemanticCandidate, ...],
        temporal_closures: tuple[TemporalEvidenceDecisionClosure, ...],
        attempt_count: int,
        *,
        source_analyses: tuple[IndependentSourceAnalysis, ...] = (),
        arbitration_policy_bundle: SemanticArbitrationPolicyBundle | None = None,
        authorization_read_set: SemanticAuthorizationReadSet | None = None,
        execution_lineage: SemanticExecutionLineage | None = None,
        sealed_operations: tuple[SealedSemanticOperation, ...] = (),
        terminal_binding_sets: tuple[SemanticTerminalBindingSet, ...] = (),
    ) -> SemanticTerminalOutcome:
        return SemanticTerminalOutcome.create(
            operation_id=operation_id,
            status=status,
            reason_codes=reason_codes,
            candidates=candidates,
            source_analyses=source_analyses,
            arbitration_policy_bundle=arbitration_policy_bundle,
            authorization_read_set=authorization_read_set,
            execution_lineage=execution_lineage,
            temporal_closures=temporal_closures,
            sealed_operations=sealed_operations,
            terminal_binding_sets=terminal_binding_sets,
            attempt_count=attempt_count,
        )

    @staticmethod
    def _canonical_candidates(
        candidates: tuple[SemanticCandidate, ...],
    ) -> tuple[SemanticCandidate, ...]:
        return tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id))

    @staticmethod
    def _parse_transport(raw: bytes) -> tuple[SemanticCandidate, ...]:
        try:
            decoded = decode_typed_value(raw)
            if not isinstance(decoded, dict) or set(decoded) != {"candidates"} or not isinstance(decoded["candidates"], list):
                raise CandidateTransportError("candidate transport envelope is invalid")
            candidates = SemanticIngestionPipeline._canonical_candidates(
                tuple(
                    SemanticCandidate.model_validate(value)
                    for value in decoded["candidates"]
                )
            )
            ids = tuple(item.candidate_id for item in candidates)
            if ids != tuple(sorted(set(ids))):
                raise CandidateTransportError("candidate IDs must be canonical and unique")
            return candidates
        except (TypeError, ValueError) as exc:
            if isinstance(exc, CandidateTransportError):
                raise
            raise CandidateTransportError("candidate transport validation failed") from exc


__all__ = [
    "AnalyzerRoleInterpretation", "AuthenticatedSourceIntervalEvidence", "CandidateTransportError", "OperationTemporalAttachmentBinding",
    "OperationTemporalDecisionBinding", "ParserConsensusAssessment", "PredicateTemporalRule", "IdentityLineageCompiler",
    "PredicateTrustRule", "SemanticArbitrationPolicyBundle", "SemanticCandidate", "SemanticIngestionPipeline", "SemanticPipelinePolicy",
    "SemanticCandidateAssessor", "SemanticPipelinePolicyProvider", "SemanticTerminalBindingSet", "SemanticTerminalOutcome",
    "IndependentSourceAnalysis", "SourceAuthority", "SourceLocalIdentityEvidence", "SourceSpan", "SourceTemporalEvidenceSet", "TemporalEvidenceCandidate",
    "TemporalEvidenceDecisionClosure", "TemporalEvidenceResolver", "TemporalPolicySnapshot",
    "SemanticAnalysisOutage", "TimeInterval", "TrustPolicySnapshot",
]
