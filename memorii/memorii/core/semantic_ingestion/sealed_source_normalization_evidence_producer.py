"""Sealed, host-injected graph-free source-normalization evidence production.

The production owner deliberately has no discovery or fallback behaviour.  It
only combines the four explicitly injected lane results with the consumed
reservation and the source-normalization authority already checked by the
execution owner.
"""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from memorii.core.semantic_ingestion.contracts import (
    AnalyzerRoleInterpretation,
    AnalyzerScopeInterpretation,
    AnalyzerScopeObservation,
    AnalyzerTemporalAttachment,
    AnalyzerTemporalAttachmentObservation,
    CanonicalRoleAssignment,
    CheckResult,
    ConsensusPolicySelection,
    ConsensusPolicySelectionBundle,
    GraphFreeInterpretationBundle,
    LinguisticAnalysis,
    LinguisticAnalysisBundle,
    LinguisticAnalysisRequest,
    ParserConsensusAssessment,
    ParserOperationPolicyAuthority,
    PreAlignmentSemanticOperationSubject,
    PreAlignmentSemanticOperationSubjectSet,
    PredicateEventCandidate,
    PredicateEventDetectionRequest,
    PredicateEventInventory,
    ScopeOperationPolicyAuthority,
    SegmentAnalysisInput,
    SegmentLanguageLaneOutcome,
    SegmentLinguisticAnalysisBundle,
    SemanticProposalRun,
    SourceLocalIdentityPartitionEvidence,
    SourceNormalizationEvidenceEntry,
    SourcePrePartitionMention,
    SourceSpanReference,
    TemporalResolution,
    TemporalResolutionRequest,
)
from memorii.core.semantic_ingestion.source_normalization_execution import (
    BootstrapRecoveryClaimV3,
    ConsumedSourceNormalizationResourceReservation,
    SourceNormalizationAuthorityBundle,
    SourceNormalizationNonCommit,
)
from memorii.core.semantic_ingestion.source_normalization_stage import (
    GraphFreeSourceNormalizationInputs,
    GraphFreeSourceNormalizationInvocation,
)


class ParserLane(Protocol):
    """One independently configured, exact-resource parser lane."""

    def analyze(self, request: LinguisticAnalysisRequest) -> LinguisticAnalysis | None: ...


class PredicateEventDetector(Protocol):
    def detect(self, request: PredicateEventDetectionRequest) -> tuple[PredicateEventCandidate, ...] | None: ...


class TemporalLane(Protocol):
    def resolve(self, request: TemporalResolutionRequest, *, locale: str, timezone: str) -> TemporalResolution | None: ...


class InterpretationEvidenceProducer(Protocol):
    """Produces only typed source-local observations from sealed lane output.

    It intentionally receives no graph, terminal, provider, clock, or current
    policy lookup.  The return type is a concrete contract bundle rather than
    an untyped adapter dictionary.
    """

    def produce(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        proposal_run: SemanticProposalRun,
        analyses: LinguisticAnalysisBundle,
        temporal_resolution: TemporalResolution,
        authority: SourceNormalizationAuthorityBundle,
    ) -> GraphFreeInterpretationEvidence | None: ...


class GraphFreeInterpretationEvidence(BaseModel):
    """Strict typed intermediate supplied by the source-only interpreter.

    This small non-persisted carrier closes the previously absent raw analyzer
    output boundary without allowing provider proposal bytes to masquerade as
    parser/scope/temporal/identity evidence.
    """

    parser_consensus: tuple[ParserConsensusAssessment, ...]
    scope_observations: tuple[AnalyzerScopeObservation, ...]
    temporal_observations: tuple[AnalyzerTemporalAttachmentObservation, ...]
    identity_partition_evidence: SourceLocalIdentityPartitionEvidence

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


_TEMPORAL_ROLES = {
    "fact": ("assertion",), "action_state": ("assertion",),
    "correction": ("replacement", "transition"), "retraction": ("transition",),
    "identity": ("transition",),
}


class TypedSourceInterpretationEvidenceProducer:
    """The graph-free, policy-bound interpreter for sealed local analyses.

    This is deliberately a small closed interpreter, rather than an adapter to
    a model or a terminal result.  Every result is reconstructed from both
    retained parser graphs, Duckling candidates, proposal subjects, and the
    per-operation language policy packet.  A missing or ambiguous coordinate
    returns ``None`` so the outer producer emits its one typed noncommit.
    """

    def produce(
        self, *, invocation: GraphFreeSourceNormalizationInvocation,
        proposal_run: SemanticProposalRun, analyses: LinguisticAnalysisBundle,
        temporal_resolution: TemporalResolution, authority: SourceNormalizationAuthorityBundle,
    ) -> GraphFreeInterpretationEvidence | None:
        subjects = tuple(
            (subject, proposal) for proposal in proposal_run.validated_segments
            for subject in PreAlignmentSemanticOperationSubjectSet.create(proposal=proposal).subjects
        )
        if not subjects:
            return None
        by_segment = {item.segment_id: item for item in analyses.segment_bundles}
        if len(by_segment) != len(analyses.segment_bundles):
            return None
        scopes: list[AnalyzerScopeObservation] = []
        temporal: list[AnalyzerTemporalAttachmentObservation] = []
        consensus: list[ParserConsensusAssessment] = []
        mentions: dict[str, SourcePrePartitionMention] = {}
        for subject, proposal in subjects:
            policy = self._policy(subject.operation_id, subject.proposal_id, subject.segment_id,
                                  subject.segment_language_route_digest, authority)
            bundle = by_segment.get(subject.segment_id)
            if policy is None or bundle is None or bundle.primary is None or bundle.corroborating is None:
                return None
            primary = self._interpret(subject, proposal, bundle.primary, policy[0], policy[1], temporal_resolution)
            corroborating = self._interpret(subject, proposal, bundle.corroborating, policy[0], policy[1], temporal_resolution)
            if primary is None or corroborating is None:
                return None
            primary_role, primary_scope, primary_temporal, primary_mentions = primary
            corroborating_role, corroborating_scope, corroborating_temporal, corroborating_mentions = corroborating
            if set(primary_mentions) != set(corroborating_mentions):
                return None
            for mention in primary_mentions.values():
                previous = mentions.setdefault(mention.mention_digest, mention)
                if previous != mention:
                    return None
            for role in ("primary", "corroborating"):
                value = primary_scope if role == "primary" else corroborating_scope
                scopes.append(AnalyzerScopeObservation.create(
                    source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
                    preparation_fingerprint=invocation.source.preparation_fingerprint,
                    segment_id=subject.segment_id, segment_language_route_digest=subject.segment_language_route_digest,
                    proposal_id=subject.proposal_id, operation_id=subject.operation_id,
                    analyzer_role=role, interpretation=value,
                ))
            stable = primary_role.assignments if primary_role.assignments == corroborating_role.assignments else None
            consensus.append(ParserConsensusAssessment.create(
                schema_version=2, source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
                preparation_fingerprint=invocation.source.preparation_fingerprint, segment_id=subject.segment_id,
                proposal_id=subject.proposal_id, operation_id=subject.operation_id,
                segment_language_route_digest=subject.segment_language_route_digest,
                analysis_bundle_fingerprint=analyses.bundle_fingerprint, primary_interpretation=primary_role,
                corroborating_interpretation=corroborating_role, stable_assignment=stable,
                status="stable" if stable is not None else "disagreement",
                consensus_policy_fingerprint=authority.derivation.consensus_policy_authority.parser_policy.policy_fingerprint,
            ))
            for temporal_role in _TEMPORAL_ROLES[subject.kind]:
                for role, values in (("primary", primary_temporal), ("corroborating", corroborating_temporal)):
                    attachment = values[temporal_role]
                    temporal.append(AnalyzerTemporalAttachmentObservation.create(
                        schema_version=2, source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
                        preparation_fingerprint=invocation.source.preparation_fingerprint,
                        segment_id=subject.segment_id, segment_language_route_digest=subject.segment_language_route_digest,
                        proposal_id=subject.proposal_id, operation_id=subject.operation_id, temporal_role=temporal_role,
                        analyzer_role=role, attachment=attachment,
                    ))
        if not mentions:
            return None
        identity = SourceLocalIdentityPartitionEvidence.create(
            source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
            mentions=tuple(sorted(mentions.values(), key=lambda item: item.mention_digest)), assertions=(),
        )
        return GraphFreeInterpretationEvidence(
            parser_consensus=tuple(sorted(consensus, key=lambda item: item.operation_id)),
            scope_observations=tuple(sorted(scopes, key=lambda item: (item.operation_id, item.analyzer_role))),
            temporal_observations=tuple(sorted(temporal, key=lambda item: (item.operation_id, item.temporal_role, item.analyzer_role))),
            identity_partition_evidence=identity,
        )

    @staticmethod
    def _policy(operation_id: str, proposal_id: str, segment_id: str, route: str,
                authority: SourceNormalizationAuthorityBundle) -> tuple[ParserOperationPolicyAuthority, ScopeOperationPolicyAuthority] | None:
        values = tuple(item for item in authority.derivation.language_construction_policies.policies if (
            item.operation_id, item.proposal_id, item.segment_id, item.segment_language_route_digest
        ) == (operation_id, proposal_id, segment_id, route))
        if len(values) != 2 or not isinstance(values[0], ParserOperationPolicyAuthority) or not isinstance(values[1], ScopeOperationPolicyAuthority):
            return None
        return values[0], values[1]

    @staticmethod
    def _interpret(subject: PreAlignmentSemanticOperationSubject, proposal: object, analysis: LinguisticAnalysis, parser: ParserOperationPolicyAuthority,
                   scope_policy: ScopeOperationPolicyAuthority, temporal: TemporalResolution):
        # The policy packet already selected the legal construction/roles.  A
        # clause is usable only when it has exactly those roles; never guess.
        anchor = TypedSourceInterpretationEvidenceProducer._anchor(subject, proposal)
        if anchor is None:
            return None
        matches = [clause for clause in analysis.clauses if clause.predicate_span == anchor]
        if len(matches) != 1:
            return None
        clause = matches[0]
        arguments = {item.grammatical_role: item for item in clause.arguments}
        if set(arguments) != {item.role_id for item in parser.role_schemas}:
            return None
        assignments = tuple(CanonicalRoleAssignment.create(
            role_id=schema.role_id, argument_span=arguments[schema.role_id].source_span,
            endpoint_kind="actor" if schema.role_id == "actor" else ("subject" if schema.role_id == "subject" else ("object" if schema.role_id == "object" else "other")),
        ) for schema in parser.role_schemas)
        role = AnalyzerRoleInterpretation.create(analyzer_fingerprint=analysis.analyzer_fingerprint,
            predicate_head_span=clause.predicate_span, construction_family=scope_policy.scope_policy.construction_family,
            assignments=assignments)
        check = CheckResult(status="pass", reason_code="policy_exact", evidence_spans=(clause.source_span,), diagnostics=())
        scope = AnalyzerScopeInterpretation.create(analyzer_fingerprint=analysis.analyzer_fingerprint,
            proposal_id=subject.proposal_id, predicate_head_span=clause.predicate_span,
            governing_clause_spans=(clause.source_span,), polarity=check, commitment=check, attribution=check,
            attribution_bearer_span=None)
        candidates = tuple(item for item in temporal.candidates if item.segment_id == subject.segment_id and item.source_span.projection_segment_id == clause.source_span.projection_segment_id)
        attachment = AnalyzerTemporalAttachment.create(analyzer_fingerprint=analysis.analyzer_fingerprint,
            proposal_id=subject.proposal_id, predicate_head_span=clause.predicate_span,
            candidate_ids=tuple(sorted(item.candidate_id for item in candidates)),
            attachment_spans=tuple(sorted((item.source_span for item in candidates), key=lambda item: item.reference_digest)))
        attachments = {role: attachment for role in _TEMPORAL_ROLES[subject.kind]}
        mentions = {item.mention_digest: SourcePrePartitionMention.create(source_id=analysis.source_id,
            source_digest=analysis.source_digest, segment_id=subject.segment_id,
            segment_language_route_digest=subject.segment_language_route_digest,
            language_policy_fingerprint=scope_policy.scope_policy.policy_fingerprint,
            mention_span=item.source_span) for item in analysis.mentions}
        return role, scope, attachments, mentions

    @staticmethod
    def _anchor(subject: PreAlignmentSemanticOperationSubject, proposal: object) -> SourceSpanReference | None:
        members = getattr(proposal, {
            "fact": "facts", "correction": "corrections", "retraction": "retractions",
            "action_state": "action_states", "identity": "identity_operations",
        }[subject.kind], ())
        if subject.proposal_member_index >= len(members):
            return None
        member = members[subject.proposal_member_index]
        for name in ("predicate_anchor_span", "correction_anchor_span", "retraction_anchor_span", "action_anchor_span", "identity_anchor_span"):
            value = getattr(member, name, None)
            if isinstance(value, SourceSpanReference):
                return value
        return None


class SealedSourceNormalizationEvidenceProducer:
    """Build complete graph-free inputs from four sealed local lanes."""

    def __init__(
        self, *,
        stanza: ParserLane,
        spacy: ParserLane,
        predicate_detector: PredicateEventDetector,
        duckling: TemporalLane,
        interpretation_producer: InterpretationEvidenceProducer,
        locale_by_language: dict[str, str],
        timezone: str,
    ) -> None:
        # Copy the mapping so a host mutation cannot change a later call.
        self._stanza = stanza
        self._spacy = spacy
        self._predicate_detector = predicate_detector
        self._duckling = duckling
        self._interpretation_producer = interpretation_producer
        self._locale_by_language = dict(locale_by_language)
        self._timezone = timezone

    @classmethod
    def with_typed_interpreter(
        cls, *, stanza: ParserLane, spacy: ParserLane,
        predicate_detector: PredicateEventDetector, duckling: TemporalLane,
        locale_by_language: dict[str, str], timezone: str,
    ) -> SealedSourceNormalizationEvidenceProducer:
        """Construct the sealed producer with the only in-core interpreter.

        Composition still supplies every resource-backed lane explicitly; this
        helper merely prevents a host from replacing source interpretation with
        a model-shaped or terminal-shaped adapter.
        """
        return cls(
            stanza=stanza, spacy=spacy, predicate_detector=predicate_detector,
            duckling=duckling, interpretation_producer=TypedSourceInterpretationEvidenceProducer(),
            locale_by_language=locale_by_language, timezone=timezone,
        )

    def produce(self, *, invocation: GraphFreeSourceNormalizationInvocation,
                proposal_run: SemanticProposalRun, authority: SourceNormalizationAuthorityBundle,
                resources: ConsumedSourceNormalizationResourceReservation,
                renew_claim: Callable[[], BootstrapRecoveryClaimV3 | None] | None = None,
    ) -> GraphFreeSourceNormalizationInputs | SourceNormalizationNonCommit:
        try:
            self._validate(invocation=invocation, proposal_run=proposal_run, authority=authority, resources=resources)
            analyses = self._analyses(invocation=invocation, authority=authority, renew_claim=renew_claim)
            predicate_events = self._predicate_events(invocation=invocation, authority=authority, renew_claim=renew_claim)
            temporal = self._temporal(invocation=invocation, authority=authority, renew_claim=renew_claim)
            if analyses is None or predicate_events is None or temporal is None:
                return self._unavailable(invocation)
            raw = self._interpretation_producer.produce(
                invocation=invocation, proposal_run=proposal_run, analyses=analyses,
                temporal_resolution=temporal, authority=authority,
            )
            if raw is None:
                return self._unavailable(invocation)
            return self._inputs(
                invocation=invocation, proposal_run=proposal_run, authority=authority,
                analyses=analyses, predicate_events=predicate_events, temporal=temporal, raw=raw,
            )
        except (ValueError, TypeError):
            return self._unavailable(invocation)

    @staticmethod
    def _unavailable(invocation: GraphFreeSourceNormalizationInvocation) -> SourceNormalizationNonCommit:
        return SourceNormalizationNonCommit.create(
            phase="evidence_sealed", reason="analysis_unavailable", invocation=invocation
        )

    def _validate(self, *, invocation: GraphFreeSourceNormalizationInvocation,
                  proposal_run: SemanticProposalRun, authority: SourceNormalizationAuthorityBundle,
                  resources: ConsumedSourceNormalizationResourceReservation) -> None:
        source = invocation.source
        if proposal_run.status != "complete" or (
            proposal_run.source_id, proposal_run.source_digest, proposal_run.preparation_fingerprint
        ) != (source.source_id, source.source_digest, source.preparation_fingerprint):
            raise ValueError("proposal run does not join source")
        bindings = tuple(item.resource_binding_digest for item in authority.derivation.analyzer_resource_bindings)
        expected = tuple(route.resource_binding.resource_binding_digest for route in source.segment_language_routes.routes if route.resource_binding is not None)
        if bindings != expected or tuple(sorted(resources.required_lane_manifest_digests)) != resources.required_lane_manifest_digests:
            raise ValueError("analyzer reservation does not bind selected lanes")
        if (resources.source_id, resources.source_digest, resources.preparation_fingerprint,
            resources.operation_id, resources.operation_fence_digest) != (
                source.source_id, source.source_digest, source.preparation_fingerprint,
                invocation.operation_id, invocation.operation_fence_binding.binding_digest,
            ):
            raise ValueError("consumed reservation does not join invocation")

    def _analyses(self, *, invocation: GraphFreeSourceNormalizationInvocation,
                  authority: SourceNormalizationAuthorityBundle,
                  renew_claim: Callable[[], BootstrapRecoveryClaimV3 | None] | None = None) -> LinguisticAnalysisBundle | None:
        bundles: list[SegmentLinguisticAnalysisBundle] = []
        for segment, route in zip(invocation.source.segments, invocation.source.segment_language_routes.routes, strict=True):
            binding = route.resource_binding
            if route.decision != "selected" or binding is None:
                return None
            analysis_input = self._analysis_input(invocation=invocation, segment=segment)
            request = LinguisticAnalysisRequest.create(segment=analysis_input, analyzer_manifest=self._stanza.manifest)
            if renew_claim is not None and renew_claim() is None:
                return None
            primary = self._stanza.analyze(request)
            request = LinguisticAnalysisRequest.create(segment=analysis_input, analyzer_manifest=self._spacy.manifest)
            if renew_claim is not None and renew_claim() is None:
                return None
            corroborating = self._spacy.analyze(request)
            if primary is None or corroborating is None:
                return None
            if (primary.analyzer_manifest_digest, corroborating.analyzer_manifest_digest) != (
                binding.stanza_analyzer_manifest_digest, binding.spacy_analyzer_manifest_digest,
            ):
                return None
            outcomes = tuple(SegmentLanguageLaneOutcome.create(
                lane=lane, segment_id=segment.segment_id,
                preparation_fingerprint=invocation.source.preparation_fingerprint,
                segment_language_route_digest=route.route_digest,
                resource_binding_digest=binding.resource_binding_digest,
                selected_manifest_digest=manifest, status="complete", artifact_digest=analysis.analysis_digest,
                reason_codes=(),
            ) for lane, manifest, analysis in (("stanza", binding.stanza_analyzer_manifest_digest, primary), ("spacy", binding.spacy_analyzer_manifest_digest, corroborating)))
            bundles.append(SegmentLinguisticAnalysisBundle.create(
                source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
                preparation_fingerprint=invocation.source.preparation_fingerprint, segment_id=segment.segment_id,
                segment_language_route_digest=route.route_digest, primary=primary, corroborating=corroborating,
                lane_outcomes=outcomes, status="complete", diagnostics=(),
            ))
        return LinguisticAnalysisBundle.create(
            source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
            preparation_fingerprint=invocation.source.preparation_fingerprint,
            segment_language_routes=invocation.source.segment_language_routes, segment_bundles=tuple(bundles),
            segment_outcomes=tuple(outcome for bundle in bundles for outcome in bundle.lane_outcomes),
            status="complete", diagnostics=(),
        )

    def _predicate_events(self, *, invocation: GraphFreeSourceNormalizationInvocation,
                          authority: SourceNormalizationAuthorityBundle,
                          renew_claim: Callable[[], BootstrapRecoveryClaimV3 | None] | None = None) -> PredicateEventInventory | None:
        candidates: list[PredicateEventCandidate] = []
        outcomes: list[SegmentLanguageLaneOutcome] = []
        for segment, route in zip(invocation.source.segments, invocation.source.segment_language_routes.routes, strict=True):
            binding = route.resource_binding
            if binding is None:
                return None
            manifest = getattr(self._predicate_detector, "manifest", None)
            request = PredicateEventDetectionRequest.create(
                segment=self._analysis_input(invocation=invocation, segment=segment), predicate_event_manifest=manifest
            )
            if renew_claim is not None and renew_claim() is None:
                return None
            detected = self._predicate_detector.detect(request)
            if detected is None or any(item.segment_id != segment.segment_id for item in detected):
                return None
            candidates.extend(detected)
            artifact = sha256("".join(item.candidate_digest for item in detected).encode()).hexdigest()
            outcomes.append(SegmentLanguageLaneOutcome.create(lane="predicate_event_detection", segment_id=segment.segment_id,
                preparation_fingerprint=invocation.source.preparation_fingerprint, segment_language_route_digest=route.route_digest,
                resource_binding_digest=binding.resource_binding_digest, selected_manifest_digest=binding.predicate_event_manifest_digest,
                status="complete", artifact_digest=artifact, reason_codes=()))
        return PredicateEventInventory.create(source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
            preparation_fingerprint=invocation.source.preparation_fingerprint, segment_language_routes=invocation.source.segment_language_routes,
            segment_outcomes=tuple(outcomes), candidates=tuple(sorted(candidates, key=lambda item: (item.segment_id, item.lexical_anchor_span.reference_digest, item.predicate_family, item.candidate_digest))), status="complete")

    def _temporal(self, *, invocation: GraphFreeSourceNormalizationInvocation,
                  authority: SourceNormalizationAuthorityBundle,
                  renew_claim: Callable[[], BootstrapRecoveryClaimV3 | None] | None = None) -> TemporalResolution | None:
        resolutions: list[TemporalResolution] = []
        for segment, route in zip(invocation.source.segments, invocation.source.segment_language_routes.routes, strict=True):
            locale = self._locale_by_language.get(route.selected_language or "")
            if locale is None:
                return None
            request = TemporalResolutionRequest.create(
                segment=self._analysis_input(invocation=invocation, segment=segment),
                resolver_manifest=self._duckling.manifest, reference_evidence=None,
            )
            if renew_claim is not None and renew_claim() is None:
                return None
            value = self._duckling.resolve(request, locale=locale, timezone=self._timezone)
            if value is None or value.status != "complete":
                return None
            resolutions.append(value)
        outcomes = tuple(item.segment_outcomes[0] for item in resolutions)
        candidates = tuple(sorted((candidate for item in resolutions for candidate in item.candidates), key=lambda item: (item.segment_id, item.source_span.reference_digest, item.candidate_digest)))
        return TemporalResolution.create(source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
            preparation_fingerprint=invocation.source.preparation_fingerprint, segment_language_routes=invocation.source.segment_language_routes,
            segment_outcomes=outcomes, candidates=candidates, ambiguous_spans=tuple(sorted({span for item in resolutions for span in item.ambiguous_spans}, key=lambda item: item.reference_digest)), status="complete", diagnostics=())

    @staticmethod
    def _analysis_input(*, invocation: GraphFreeSourceNormalizationInvocation, segment: object) -> SegmentAnalysisInput:
        """Derive the sole segment request from sealed prepared-source bytes."""
        source = invocation.source
        context = SourceSpanReference.create(
            source_id=source.source_id,
            projection_digest=segment.context_projection_span.artifact.artifact_digest,
            projection_segment_id=segment.parent_projection_segment_id,
            retained_text_artifact=source.semantic_text_projection.retained_text_artifact,
            projection_span=segment.context_projection_span,
            segment_local_span=segment.context_segment_span,
            text_mapping_proof=segment.text_mapping_proof,
            source_reference=None,
        )
        start, end = segment.context_projection_span.start, segment.context_projection_span.end
        return SegmentAnalysisInput.create(
            source_id=source.source_id, source_digest=source.source_digest,
            segment_id=segment.segment_id, preparation_fingerprint=source.preparation_fingerprint,
            parent_projection_segment_id=segment.parent_projection_segment_id,
            segment_governance=segment.segment_governance,
            message_admission_identity=segment.message_admission_identity,
            governance_carrier_artifact=source.governance_carrier_artifact,
            context_text=context, segment_text=source.semantic_text[start:end], language_route=segment.language_route,
        )

    def _inputs(self, *, invocation: GraphFreeSourceNormalizationInvocation, proposal_run: SemanticProposalRun,
                authority: SourceNormalizationAuthorityBundle, analyses: LinguisticAnalysisBundle,
                predicate_events: PredicateEventInventory, temporal: TemporalResolution,
                raw: GraphFreeInterpretationEvidence) -> GraphFreeSourceNormalizationInputs:
        subject_sets = tuple(PreAlignmentSemanticOperationSubjectSet.create(proposal=proposal)
            for proposal in proposal_run.validated_segments)
        bundle = GraphFreeInterpretationBundle.create(schema_version=2, source_id=invocation.source.source_id,
            source_digest=invocation.source.source_digest, preparation_fingerprint=invocation.source.preparation_fingerprint,
            proposal_run_fingerprint=proposal_run.run_fingerprint, analysis_bundle_fingerprint=analyses.bundle_fingerprint,
            temporal_resolution_fingerprint=temporal.resolver_fingerprint, subject_sets=subject_sets,
            scope_observations=raw.scope_observations, temporal_attachment_observations=raw.temporal_observations,
            identity_partition_evidence=raw.identity_partition_evidence)
        policies = authority.derivation.consensus_policy_authority
        selections = []
        for row in raw.parser_consensus:
            for kind, policy, fingerprint, dependency, role in (
                ("parser", policies.parser_policy, policies.parser_policy.policy_fingerprint, analyses.bundle_fingerprint, None),
                ("scope", policies.scope_policy, policies.scope_policy.policy_fingerprint, analyses.bundle_fingerprint, None),
            ):
                selections.append(ConsensusPolicySelection.create(schema_version=2, kind=kind, operation_id=row.operation_id, proposal_id=row.proposal_id, segment_id=row.segment_id, segment_language_route_digest=row.segment_language_route_digest, temporal_role=role, request_dependency_kind="analyses", request_dependency_fingerprint=dependency, selected_policy_fingerprint=fingerprint, selected_policy=policy))
            for role in {"fact": ("assertion",), "action_state": ("assertion",), "correction": ("replacement", "transition"), "retraction": ("transition",), "identity": ("transition",)}[next(subject.kind for group in subject_sets for subject in group.subjects if subject.operation_id == row.operation_id)]:
                selections.append(ConsensusPolicySelection.create(schema_version=2, kind="temporal_attachment", operation_id=row.operation_id, proposal_id=row.proposal_id, segment_id=row.segment_id, segment_language_route_digest=row.segment_language_route_digest, temporal_role=role, request_dependency_kind="temporal_resolution", request_dependency_fingerprint=temporal.resolver_fingerprint, selected_policy_fingerprint=policies.temporal_attachment_policy.policy_fingerprint, selected_policy=policies.temporal_attachment_policy))
        selection_bundle = ConsensusPolicySelectionBundle.create(schema_version=2, selections=tuple(sorted(selections, key=lambda item: (item.kind, item.operation_id, item.proposal_id, item.segment_id, item.segment_language_route_digest, item.temporal_role or ""))))
        selection_by_key = {(item.kind, item.operation_id, item.temporal_role): item for item in selection_bundle.selections}
        entries = []
        for row in raw.parser_consensus:
            values = (("parser", None, row.assessment_digest), ("scope", None, next(x.observation_digest for x in raw.scope_observations if x.operation_id == row.operation_id and x.analyzer_role == "primary")))
            values += tuple(("temporal_attachment", role, next(x.observation_digest for x in raw.temporal_observations if x.operation_id == row.operation_id and x.temporal_role == role and x.analyzer_role == "primary")) for role in {"fact": ("assertion",), "action_state": ("assertion",), "correction": ("replacement", "transition"), "retraction": ("transition",), "identity": ("transition",)}[next(subject.kind for group in subject_sets for subject in group.subjects if subject.operation_id == row.operation_id)])
            for kind, role, digest in values:
                selected = selection_by_key[(kind, row.operation_id, role)]
                entries.append(SourceNormalizationEvidenceEntry.create(schema_version=2, kind=kind, operation_id=row.operation_id, proposal_id=row.proposal_id, segment_id=row.segment_id, segment_language_route_digest=row.segment_language_route_digest, temporal_role=role, artifact_digest=digest, selection_digest=selected.selection_digest, retention="aligned"))
        return GraphFreeSourceNormalizationInputs(source=invocation.source, proposal_run=proposal_run, analyses=analyses, interpretation_bundle=bundle, predicate_events=predicate_events, temporal_resolution=temporal, consensus_policy_selections=selection_bundle, language_construction_policies=authority.derivation.language_construction_policies, publication_coordinate=authority.publication.publication_coordinate, temporal_policy=authority.derivation.temporal_policy, trust_policy=authority.derivation.trust_policy, arbitration_as_of=authority.derivation.arbitration_as_of, capability_registry=authority.derivation.capability_registry, parser_consensus=raw.parser_consensus, evidence_entries=tuple(entries), capability_selections=(authority.derivation.capability_registry,), graph_dependent_execution_policy=authority.derivation.graph_dependent_execution_policy, graph_dependent_execution_policy_digest=authority.derivation.graph_dependent_execution_policy.policy_digest, progress=authority.publication.progress, operation_fence_binding=authority.publication.operation_fence_binding, operation_lease_binding=authority.publication.operation_lease_binding, writer_commit_binding=authority.publication.writer_commit_binding, expected_operation_generation=authority.publication.expected_operation_generation, expected_artifact_generation=authority.publication.expected_artifact_generation)


__all__ = [
    "GraphFreeInterpretationEvidence",
    "SealedSourceNormalizationEvidenceProducer",
    "TypedSourceInterpretationEvidenceProducer",
]
