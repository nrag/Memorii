"""M3 fail-closed candidate-to-terminal semantic pipeline."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256
from threading import Event, Thread
from typing import Literal, Protocol, TypeVar

from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value, encode_typed_value
from memorii.core.semantic_ingestion.carriers import compile_accepted_carriers
from memorii.core.semantic_ingestion.contracts import (
    AnalyzerRoleInterpretation,
    AuthenticatedSourceIntervalEvidence,
    AuthorizationStageSnapshot,
    AuthorizationUsePoint,
    CandidateTransportError,
    IndependentSourceAnalysis,
    M3ExecutionLineage,
    OperationTemporalAttachmentBinding,
    OperationTemporalDecisionBinding,
    ParserConsensusAssessment,
    PredicateTemporalRule,
    PredicateTrustRule,
    SealedSemanticOperation,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SemanticAuthorizationReadSetProvider,
    SemanticCandidate,
    SemanticCandidateAssessor,
    SemanticPipelinePolicy,
    SemanticPipelinePolicyProvider,
    SemanticTerminalBindingSet,
    SemanticTerminalOutcome,
    SemanticTransport,
    SourceAuthority,
    SourceAuthorityEvidence,
    SourceLocalIdentityEvidence,
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
from memorii.core.semantic_ingestion.operation_assessment import seal_semantic_operation
from memorii.core.semantic_ingestion.prompt_authority import SemanticPromptAuthority

_StageResult = TypeVar("_StageResult")


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

        thread = Thread(target=renew, name="memorii-m3-lease-heartbeat", daemon=True)
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
            closure_digest=contract_digest(b"memorii.m3.temporal-decision-closure.v1", body),
        )


class SemanticIngestionPipeline:
    """One bounded proposal repair followed by deterministic M3 reconciliation."""

    _HEARTBEAT_INTERVAL_SECONDS = 10.0

    def __init__(
        self,
        *,
        transport: SemanticTransport | None,
        resolver: TemporalEvidenceResolver | None = None,
        renewal_scheduler: LearnedStageRenewalScheduler | None = None,
    ) -> None:
        self._transport = transport
        self._resolver = resolver or TemporalEvidenceResolver()
        self._renewal_scheduler = renewal_scheduler or _ThreadedLearnedStageRenewalScheduler(
            interval_seconds=self._HEARTBEAT_INTERVAL_SECONDS
        )

    def run(
        self,
        *,
        operation_id: str,
        source_id: str,
        source_digest: str,
        source_text: str,
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
        stage_observer: Callable[[str, str], None] | None = None,
    ) -> SemanticTerminalOutcome:
        if not source_id or len(source_digest) != 64 or not source_text:
            return self._terminal(operation_id, "evidence_only", ("source_binding_unavailable",), (), (), 0)
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
            parsed = tuple(SemanticCandidate.model_validate(value.model_dump(mode="python")) for value in local_proposals)
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
                contract_digest(b"memorii.m3.local-proposal-attempt.v1", parsed)
            )
            self._observe_stage(stage_observer, "proposal_complete", proposal_attempt_digests[-1])
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
                        b"memorii.m3.remote-proposal-attempt.v1",
                        {"request_digest": sha256(request_bytes).hexdigest(), "response_digest": sha256(raw).hexdigest()},
                    ))
                    self._observe_stage(
                        stage_observer,
                        f"proposal_attempt_{attempt}",
                        proposal_attempt_digests[-1],
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
            )
        source_analyses = tuple(analyses)
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
        execution_lineage = M3ExecutionLineage.create(
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
            stage_observer, "semantic_sealing_complete", execution_lineage.lineage_digest
        )
        promotable = (
            bool(parsed)
            and len(sealed_operations) == len(parsed)
            and all(value.parser_consensus.status == "stable" for value in source_analyses)
        )
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
                ("independent_consensus_or_temporal_resolution_failed",),
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
            b"memorii.m3.terminal-carrier-artifact.v1",
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
            b"memorii.m3.test-authorization-authority.v1", read_set
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
    def _analysis_spans_are_valid(
        *,
        analysis: IndependentSourceAnalysis,
        source_id: str,
        source_text: str,
        source_authority_evidence: SourceAuthorityEvidence,
        source_interval_evidence: AuthenticatedSourceIntervalEvidence | None,
    ) -> bool:
        parser_spans = (
            analysis.parser_consensus.primary.predicate_span,
            *(span for _, span in analysis.parser_consensus.primary.role_spans),
            *(
                (analysis.parser_consensus.primary.attribution_bearer_span,)
                if analysis.parser_consensus.primary.attribution_bearer_span is not None else ()
            ),
            analysis.parser_consensus.corroborating.predicate_span,
            *(span for _, span in analysis.parser_consensus.corroborating.role_spans),
            *(
                (analysis.parser_consensus.corroborating.attribution_bearer_span,)
                if analysis.parser_consensus.corroborating.attribution_bearer_span is not None else ()
            ),
        )
        spans = [
            analysis.assertion_span,
            *parser_spans,
            *(value.mention_span for value in analysis.identity_evidence),
            *(
                span
                for temporal in analysis.temporal_evidence
                for span in temporal.attachment_spans
            ),
            *(
                span
                for temporal in analysis.temporal_evidence
                for candidate in temporal.candidates
                for span in candidate.evidence_spans
            ),
        ]
        if any(
            span.source_id != source_id
            or span.start < 0
            or span.start >= span.end
            or span.end > len(source_text)
            for span in spans
        ):
            return False
        def span_key(value: SourceSpan) -> tuple[str, int, int]:
            return (value.source_id, value.start, value.end)
        for temporal in analysis.temporal_evidence:
            if tuple(sorted(temporal.attachment_spans, key=span_key)) != temporal.attachment_spans or (
                len(set(span_key(value) for value in temporal.attachment_spans))
                != len(temporal.attachment_spans)
            ):
                return False
            textual_spans = tuple(sorted(
                (
                    span
                    for candidate in temporal.candidates
                    if candidate.kind == "certified_text_interval"
                    for span in candidate.evidence_spans
                ),
                key=span_key,
            ))
            if textual_spans != temporal.attachment_spans:
                return False
            for candidate in temporal.candidates:
                if candidate.source_authority != source_authority_evidence.authority:
                    return False
                if candidate.kind == "authenticated_source_interval" and (
                    source_interval_evidence is None
                    or candidate.authenticated_source_interval_evidence != source_interval_evidence
                ):
                    return False
        return True

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
        observer: Callable[[str, str], None] | None,
        stage: str,
        artifact_digest: str,
    ) -> None:
        if observer is not None:
            observer(stage, artifact_digest)

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
        execution_lineage: M3ExecutionLineage | None = None,
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
    def _parse_transport(raw: bytes) -> tuple[SemanticCandidate, ...]:
        try:
            decoded = decode_typed_value(raw)
            if not isinstance(decoded, dict) or set(decoded) != {"candidates"} or not isinstance(decoded["candidates"], list):
                raise CandidateTransportError("candidate transport envelope is invalid")
            candidates = tuple(SemanticCandidate.model_validate(value) for value in decoded["candidates"])
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
    "OperationTemporalDecisionBinding", "ParserConsensusAssessment", "PredicateTemporalRule",
    "PredicateTrustRule", "SemanticArbitrationPolicyBundle", "SemanticCandidate", "SemanticIngestionPipeline", "SemanticPipelinePolicy",
    "SemanticCandidateAssessor", "SemanticPipelinePolicyProvider", "SemanticTerminalBindingSet", "SemanticTerminalOutcome",
    "IndependentSourceAnalysis", "SourceAuthority", "SourceLocalIdentityEvidence", "SourceSpan", "SourceTemporalEvidenceSet", "TemporalEvidenceCandidate",
    "TemporalEvidenceDecisionClosure", "TemporalEvidenceResolver", "TemporalPolicySnapshot",
    "SemanticAnalysisOutage", "TimeInterval", "TrustPolicySnapshot",
]
