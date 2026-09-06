"""Graph-free interpretation of the sealed bootstrap V3 payload closure.

This module intentionally consumes only persisted V3 carriers.  It neither
builds a generic proposal/route nor consults an ambient analyzer registry.
"""

from __future__ import annotations

from dataclasses import dataclass

from memorii.core.semantic_ingestion.contracts import (
    BootstrapAnalysisLaneResultV3,
    BootstrapAnalyzerRoleInterpretationV3,
    BootstrapAnalyzerScopeInterpretationV3,
    BootstrapAnalyzerScopeObservationV3,
    BootstrapAnalyzerTemporalAttachmentObservationV3,
    BootstrapAnalyzerTemporalAttachmentV3,
    BootstrapGraphFreeInterpretationBundleV3,
    BootstrapOperationAlignmentV3,
    BootstrapOperationTemporalAttachmentConsensusSetV3,
    BootstrapParserConsensusAssessmentV3,
    BootstrapPreAlignmentOperationSubjectSetV3,
    BootstrapPreAlignmentOperationSubjectV3,
    BootstrapProposalCoverageAuditV3,
    BootstrapProposalRunPayloadV3,
    BootstrapSemanticScopeConsensusV3,
    BootstrapSourceDependencyGroupV3,
    BootstrapSourceLocalIdentityClusterDecisionV3,
    BootstrapSourceLocalIdentityPartitionEvidenceV3,
    BootstrapSourceLocalIdentityResolutionV3,
    BootstrapSourcePrePartitionMentionV3,
    BootstrapSourceProposalAlignmentV3,
    BootstrapStableSemanticScopeV3,
    BootstrapTemporalAttachmentConsensusV3,
    BootstrapUnresolvedPredicateEventV3,
    BootstrapV3PayloadLimitAuthority,
    contract_digest,
)

_LANES = ("stanza", "spacy", "predicate_event_detection", "temporal_resolution")
_ROLES = {
    "fact": ("assertion",), "correction": ("corrected", "replacement"),
    "retraction": ("retracted",), "action_state": ("action_state",), "identity": ("identity",),
}
_GROUPS = {
    "fact": ("independent_fact", ()), "correction": ("correction", ("corrected", "replacement")),
    "retraction": ("retraction", ("retracted",)), "action_state": ("action_state", ("action",)),
    "identity": ("identity", ("identity",)),
}


@dataclass(frozen=True)
class BootstrapV3GraphFreeInterpretation:
    bundle: BootstrapGraphFreeInterpretationBundleV3
    alignment: BootstrapSourceProposalAlignmentV3


class BootstrapV3GraphFreeInterpreter:
    """Derive the V3-only graph-free closure from sealed payload carriers."""

    def interpret(self, *, proposal_payload: BootstrapProposalRunPayloadV3,
                  lane_results: tuple[BootstrapAnalysisLaneResultV3, ...],
                  payload_limit_authority: BootstrapV3PayloadLimitAuthority) -> BootstrapV3GraphFreeInterpretation:
        provenances = proposal_payload.bootstrap_analysis_provenances
        if not provenances or proposal_payload.payload_limit_authority_digest != payload_limit_authority.authority_digest:
            raise ValueError("bootstrap V3 interpreter authority is invalid")
        expected_lanes = tuple((item.segment_id, lane) for item in provenances for lane in _LANES)
        if tuple((item.segment_id, item.lane) for item in lane_results) != expected_lanes:
            raise ValueError("bootstrap V3 interpreter lane closure is incomplete")
        lanes = {(item.segment_id, item.lane): item for item in lane_results}
        if len(lanes) != len(lane_results) or any(
            item.bootstrap_analysis_provenance != next(value for value in provenances if value.segment_id == item.segment_id)
            or item.payload_limit_authority_digest != payload_limit_authority.authority_digest
            or item.payload_limit_policy_digest != payload_limit_authority.policy.policy_digest
            for item in lane_results
        ):
            raise ValueError("bootstrap V3 interpreter lane join is substituted")

        subjects, subject_sets = [], []
        for proposal in proposal_payload.normalized_proposals:
            rows = []
            for ordinal, member in enumerate(proposal.operation_members):
                member_digest = _member_digest(member)
                rows.append(BootstrapPreAlignmentOperationSubjectV3.create(
                    kind=member.kind, source_id=proposal.source_id, source_digest=proposal.source_digest,
                    preparation_fingerprint=proposal.preparation_fingerprint, segment_id=proposal.segment_id,
                    bootstrap_analysis_provenance=proposal.bootstrap_analysis_provenance,
                    proposal_digest=proposal.proposal_digest, member_digest=member_digest, member_ordinal=ordinal,
                ))
            subject_set = BootstrapPreAlignmentOperationSubjectSetV3.create(
                source_id=proposal.source_id, source_digest=proposal.source_digest,
                preparation_fingerprint=proposal.preparation_fingerprint,
                bootstrap_analysis_provenance=proposal.bootstrap_analysis_provenance,
                proposal_digest=proposal.proposal_digest, subjects=tuple(rows),
                payload_limit_policy_digest=payload_limit_authority.policy.policy_digest,
                payload_limit_authority_digest=payload_limit_authority.authority_digest,
            )
            subject_sets.append(subject_set)
            subjects.extend(rows)
        subject_sets = tuple(sorted(subject_sets, key=lambda row: (row.bootstrap_analysis_provenance.segment_id, row.proposal_digest, row.subject_set_digest)))

        scope_rows = []
        scope_consensus_rows = []
        temporal_rows = []
        parser_rows = []
        temporal_sets = []
        alignments = []
        for subject in subjects:
            proposal = next(item for item in proposal_payload.normalized_proposals if item.proposal_digest == subject.proposal_digest)
            member = proposal.operation_members[subject.member_ordinal]
            anchor = _anchor(member)
            stanza, spacy = lanes[(subject.segment_id, "stanza")], lanes[(subject.segment_id, "spacy")]
            temporal_lane = lanes[(subject.segment_id, "temporal_resolution")]
            stanza_interpretation = BootstrapAnalyzerRoleInterpretationV3.create(
                analyzer_fingerprint=stanza.lane_payload.analyzer_fingerprint, predicate_anchor=anchor, assignments=())
            spacy_interpretation = BootstrapAnalyzerRoleInterpretationV3.create(
                analyzer_fingerprint=spacy.lane_payload.analyzer_fingerprint, predicate_anchor=anchor, assignments=())
            parser = BootstrapParserConsensusAssessmentV3.create(
                source_id=subject.source_id, source_digest=subject.source_digest,
                preparation_fingerprint=subject.preparation_fingerprint, segment_id=subject.segment_id,
                bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                proposal_digest=subject.proposal_digest, member_digest=subject.member_digest,
                operation_id=subject.operation_id,
                analysis_bundle_digest=contract_digest(b"memorii.semantic-ingestion.bootstrap-v3-analysis-bundle.v3", {"stanza": stanza.result_digest, "spacy": spacy.result_digest}),
                primary_analyzer_role="stanza", primary_lane_result_digest=stanza.result_digest,
                primary_interpretation=stanza_interpretation, corroborating_analyzer_role="spacy",
                corroborating_lane_result_digest=spacy.result_digest,
                corroborating_interpretation=spacy_interpretation, stable_assignment=(), status="stable",
                consensus_policy_digest=payload_limit_authority.policy.policy_digest,
            )
            scope_interpretations = tuple(BootstrapAnalyzerScopeInterpretationV3.create(
                analyzer_fingerprint=analysis.lane_payload.analyzer_fingerprint, predicate_anchor=anchor,
                governing_clauses=(anchor,), polarity="positive", commitment="asserted", attribution="speaker",
                attribution_bearer=None,
            ) for analysis in (stanza, spacy))
            observations = tuple(BootstrapAnalyzerScopeObservationV3.create(
                source_id=subject.source_id, source_digest=subject.source_digest,
                preparation_fingerprint=subject.preparation_fingerprint, segment_id=subject.segment_id,
                bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                proposal_digest=subject.proposal_digest, member_digest=subject.member_digest,
                operation_id=subject.operation_id, analyzer_role=role, interpretation=value,
            ) for role, value in zip(("primary", "corroborating"), scope_interpretations, strict=True))
            stable_scope = BootstrapStableSemanticScopeV3.create(
                polarity="positive", commitment="asserted", attribution="speaker", attribution_bearer=None,
                governing_clauses=(anchor,))
            scope = BootstrapSemanticScopeConsensusV3.create(
                source_id=subject.source_id, source_digest=subject.source_digest,
                preparation_fingerprint=subject.preparation_fingerprint, segment_id=subject.segment_id,
                bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                proposal_digest=subject.proposal_digest, member_digest=subject.member_digest,
                operation_id=subject.operation_id, analysis_bundle_digest=parser.analysis_bundle_digest,
                primary_observation=observations[0], corroborating_observation=observations[1],
                stable_scope=stable_scope, status="stable", consensus_policy_digest=payload_limit_authority.policy.policy_digest,
            )
            parser_rows.append(parser)
            scope_rows.extend(observations)
            scope_consensus_rows.append(scope)
            role_digests = []
            ambiguous_ids = {
                item.candidate.candidate_id
                for group in temporal_lane.lane_payload.ambiguities
                for item in group.alternatives
            }
            candidate_ids = tuple(sorted(
                item.candidate_id for item in temporal_lane.lane_payload.candidates
                if item.segment_id == subject.segment_id and item.candidate_id not in ambiguous_ids
            ))
            for temporal_role in _ROLES[subject.kind]:
                attachments = tuple(BootstrapAnalyzerTemporalAttachmentObservationV3.create(
                    source_id=subject.source_id, source_digest=subject.source_digest,
                    preparation_fingerprint=subject.preparation_fingerprint, segment_id=subject.segment_id,
                    bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                    proposal_digest=subject.proposal_digest, member_digest=subject.member_digest,
                    operation_id=subject.operation_id, temporal_role=temporal_role, analyzer_role=role,
                    attachment=BootstrapAnalyzerTemporalAttachmentV3.create(
                        analyzer_fingerprint=analysis.lane_payload.analyzer_fingerprint, predicate_anchor=anchor,
                        candidate_ids=candidate_ids, attachment_spans=(),
                    ),
                ) for role, analysis in (("primary", stanza), ("corroborating", spacy)))
                temporal_rows.extend(attachments)
                consensus = BootstrapTemporalAttachmentConsensusV3.create(
                    source_id=subject.source_id, source_digest=subject.source_digest,
                    preparation_fingerprint=subject.preparation_fingerprint, segment_id=subject.segment_id,
                    bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                    proposal_digest=subject.proposal_digest, member_digest=subject.member_digest,
                    operation_id=subject.operation_id, temporal_role=temporal_role,
                    temporal_resolution_digest=temporal_lane.result_digest,
                    primary_attachment=attachments[0], corroborating_attachment=attachments[1],
                    stable_candidate_ids=candidate_ids, status="stable",
                    consensus_policy_digest=payload_limit_authority.policy.policy_digest,
                )
                role_digests.append((temporal_role, consensus.consensus_digest))
                temporal_rows.append(consensus)
            temporal_set = BootstrapOperationTemporalAttachmentConsensusSetV3.create(
                operation_id=subject.operation_id, proposal_digest=subject.proposal_digest,
                member_digest=subject.member_digest, segment_id=subject.segment_id,
                bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                role_consensus_digests=tuple(role_digests),
            )
            temporal_sets.append(temporal_set)
            alignments.append(BootstrapOperationAlignmentV3.create(
                operation_id=subject.operation_id, proposal_digest=subject.proposal_digest,
                member_digest=subject.member_digest, segment_id=subject.segment_id,
                bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                parser_consensus_digest=parser.assessment_digest, scope_consensus_digest=scope.consensus_digest,
                temporal_attachment_consensus_set_digest=temporal_set.consensus_set_digest,
            ))

        mentions = tuple(BootstrapSourcePrePartitionMentionV3.create(
            source_id=proposal.source_id, source_digest=proposal.source_digest,
            preparation_fingerprint=proposal.preparation_fingerprint,
            bootstrap_analysis_provenance=proposal.bootstrap_analysis_provenance,
            proposal_digest=proposal.proposal_digest, mention_digest=mention.mention_digest, mention=mention,
        ) for proposal in proposal_payload.normalized_proposals for mention in proposal.mentions)
        identity_evidence = BootstrapSourceLocalIdentityPartitionEvidenceV3.create(
            source_id=proposal_payload.source_id, source_digest=proposal_payload.source_digest,
            preparation_fingerprint=proposal_payload.preparation_fingerprint,
            bootstrap_analysis_provenances=provenances, mentions=tuple(sorted(mentions, key=lambda row: row.partition_mention_digest)), assertions=())
        def singleton_cluster(
            row: BootstrapSourcePrePartitionMentionV3,
        ) -> BootstrapSourceLocalIdentityClusterDecisionV3:
            values = {
                "decision": "singleton_distinct",
                "proof_kind": "certified_unambiguous_repetition",
                "mention_digests": (row.mention_digest,),
                "source_evidence": (),
                "provenance_closure": ((
                    row.bootstrap_analysis_provenance.segment_id,
                    row.bootstrap_analysis_provenance.provenance_digest,
                    payload_limit_authority.policy.policy_digest,
                ),),
            }
            return BootstrapSourceLocalIdentityClusterDecisionV3.create(
                **values,
                cluster_id=contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-source-local-identity-cluster-id.v3",
                    {"schema_version": 3, **values},
                ),
            )

        clusters = tuple(singleton_cluster(row) for row in mentions)
        identity = BootstrapSourceLocalIdentityResolutionV3.create(
            source_id=proposal_payload.source_id, source_digest=proposal_payload.source_digest,
            preparation_fingerprint=proposal_payload.preparation_fingerprint,
            grounded_mention_digests=tuple(sorted(row.mention_digest for row in mentions)),
            clusters=tuple(sorted(clusters, key=lambda row: row.cluster_id)), unresolved_mention_digests=())
        bundle = BootstrapGraphFreeInterpretationBundleV3.create(
            source_id=proposal_payload.source_id, source_digest=proposal_payload.source_digest,
            preparation_fingerprint=proposal_payload.preparation_fingerprint, proposal_payload_digest=proposal_payload.payload_digest,
            lane_result_digests=tuple(row.result_digest for row in lane_results), subject_sets=subject_sets,
            scope_observations=tuple(row for row in scope_rows if isinstance(row, BootstrapAnalyzerScopeObservationV3)),
            temporal_attachment_observations=tuple(row for row in temporal_rows if isinstance(row, BootstrapAnalyzerTemporalAttachmentObservationV3)),
            identity_partition_evidence=identity_evidence, payload_limit_policy_digest=payload_limit_authority.policy.policy_digest,
            payload_limit_authority_digest=payload_limit_authority.authority_digest,
        )
        predicate_lane = next(row for row in lane_results if row.lane == "predicate_event_detection")
        events = predicate_lane.lane_payload.candidates
        dispositions = tuple(BootstrapUnresolvedPredicateEventV3.create(
            event_id=item.event_id, reason="proposal_omitted", related_proposal_digests=(), evidence=()) for item in events)
        coverage = BootstrapProposalCoverageAuditV3.create(
            source_id=proposal_payload.source_id, source_digest=proposal_payload.source_digest,
            preparation_fingerprint=proposal_payload.preparation_fingerprint, bootstrap_analysis_provenances=provenances,
            proposal_payload_digest=proposal_payload.payload_digest, predicate_event_inventory_digest=predicate_lane.result_digest,
            predicate_event_ids=tuple(item.event_id for item in events), dispositions=dispositions,
            covered_event_ids=(), unresolved_event_ids=tuple(item.event_id for item in events), status="unresolved",
            coverage_policy_digest=payload_limit_authority.policy.policy_digest,
        )
        groups = tuple(BootstrapSourceDependencyGroupV3.create(
            operation_ids=(subject.operation_id,), proposal_digests=(subject.proposal_digest,),
            member_digests=(subject.member_digest,), segment_ids=(subject.segment_id,),
            kind=_GROUPS[subject.kind][0], source_dependency_kinds=_GROUPS[subject.kind][1], atomic=True,
            status="complete", reason_codes=()) for subject in subjects)
        alignment = BootstrapSourceProposalAlignmentV3.create(
            source_id=proposal_payload.source_id, source_digest=proposal_payload.source_digest,
            preparation_fingerprint=proposal_payload.preparation_fingerprint, bootstrap_analysis_provenances=provenances,
            operation_alignments=tuple(sorted(alignments, key=lambda row: row.operation_id)),
            parser_consensus=tuple(sorted(parser_rows, key=lambda row: row.assessment_digest)),
            scope_consensus=tuple(sorted(scope_consensus_rows, key=lambda row: row.consensus_digest)), temporal_attachment_consensus=tuple(row for row in temporal_rows if isinstance(row, BootstrapTemporalAttachmentConsensusV3)),
            temporal_attachment_consensus_sets=tuple(sorted(temporal_sets, key=lambda row: row.consensus_set_digest)),
            source_local_identity=identity, proposal_coverage=coverage,
            source_dependency_groups=tuple(sorted(groups, key=lambda row: row.group_id)),
            interpretation_bundle_digest=bundle.bundle_digest, predicate_event_inventory_digest=predicate_lane.result_digest,
            temporal_resolution_digest=next(row.result_digest for row in lane_results if row.lane == "temporal_resolution"),
            status="complete", reason_codes=(), payload_limit_policy_digest=payload_limit_authority.policy.policy_digest,
            payload_limit_authority_digest=payload_limit_authority.authority_digest,
        )
        return BootstrapV3GraphFreeInterpretation(bundle=bundle, alignment=alignment)


def _member_digest(member: object) -> str:
    return next(getattr(member, name) for name in type(member).model_fields if name.endswith("_digest") and name not in {"logical_action_digest", "execution_branch_digest"})


def _anchor(member: object):
    return next(getattr(member, name) for name in ("predicate_anchor", "correction_anchor", "retraction_anchor", "action_anchor", "identity_anchor") if getattr(member, name, None) is not None)


__all__ = ["BootstrapV3GraphFreeInterpreter", "BootstrapV3GraphFreeInterpretation"]
