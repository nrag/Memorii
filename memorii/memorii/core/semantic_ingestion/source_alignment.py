"""Graph-free source normalization derivations.

This module intentionally consumes only sealed source artifacts.  It neither
looks up graph identity nor attempts to turn an incomplete row into a terminal
result.
"""

from __future__ import annotations

from collections import defaultdict

from memorii.core.semantic_ingestion.contracts import (
    CoveredPredicateEvent,
    GraphFreeInterpretationBundle,
    OperationAlignment,
    OperationTemporalAttachmentConsensusSet,
    ParserConsensusAssessment,
    ProposalCoverageAudit,
    ResolvedTemporalCandidate,
    SegmentLanguageRouteSet,
    SemanticScopeConsensus,
    SourceDependencyGroup,
    SourceLocalIdentityClusterDecision,
    SourceLocalIdentityPartitionEvidence,
    SourceLocalIdentityResolution,
    SourceProposalAlignment,
    StableSemanticScope,
    TemporalAttachmentConsensus,
    contract_digest,
)

_ROLES = {
    "fact": ("assertion",), "action_state": ("assertion",),
    "correction": ("replacement", "transition"), "retraction": ("transition",),
    "identity": ("transition",),
}
_GROUPS = {
    "fact": ("independent_fact", ("assertion",)),
    "action_state": ("action_state", ("assertion",)),
    "correction": ("correction", ("replacement", "transition")),
    "retraction": ("retraction", ("transition",)),
    "identity": ("identity", ("transition",)),
}


def resolve_source_local_identity(evidence: SourceLocalIdentityPartitionEvidence) -> SourceLocalIdentityResolution:
    """Build a total partition; unresolved hyperedges taint their component."""
    mentions = {item.mention_digest: item for item in evidence.mentions}
    parent = {key: key for key in mentions}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[max(left, right)] = min(left, right)

    for assertion in evidence.assertions:
        for item in assertion.mention_digests[1:]:
            union(assertion.mention_digests[0], item)
    assertion_by_root: dict[str, list] = defaultdict(list)
    for assertion in evidence.assertions:
        assertion_by_root[find(assertion.mention_digests[0])].append(assertion)
    clusters = []
    for root in sorted({find(key) for key in mentions}):
        members = tuple(sorted(key for key in mentions if find(key) == root))
        assertions = sorted(assertion_by_root.get(root, ()), key=lambda item: item.assertion_digest)
        unresolved = [item for item in assertions if item.proof_kind in {"insufficient_evidence", "conflicting_evidence"}]
        affirmative_kinds = {item.proof_kind for item in assertions if item not in unresolved}
        if unresolved:
            decision = "unresolved"
            proof = "conflicting_evidence" if any(item.proof_kind == "conflicting_evidence" for item in unresolved) else "insufficient_evidence"
        elif not assertions:
            decision, proof = "singleton_distinct", "certified_unambiguous_repetition"
        elif len(affirmative_kinds) == 1:
            decision, proof = "same_source_entity", next(iter(affirmative_kinds))
        else:
            decision, proof = "unresolved", "conflicting_evidence"
        spans = tuple(sorted({span for item in assertions for span in item.source_evidence}, key=lambda span: span.reference_digest))
        closure = tuple(sorted({(mentions[key].segment_id, mentions[key].segment_language_route_digest, mentions[key].language_policy_fingerprint) for key in members}))
        cluster_id = contract_digest(b"memorii.semantic-ingestion.source-local-identity-cluster-id.v2", {"source_id": evidence.source_id, "mentions": members})
        clusters.append(SourceLocalIdentityClusterDecision.create(cluster_id=cluster_id, decision=decision, proof_kind=proof, mention_digests=members, source_evidence=spans, segment_route_policy_closure=closure))
    clusters = tuple(sorted(clusters, key=lambda item: item.cluster_id))
    unresolved = tuple(sorted(item for cluster in clusters if cluster.decision == "unresolved" for item in cluster.mention_digests))
    return SourceLocalIdentityResolution.create(source_id=evidence.source_id, grounded_mention_refs=tuple(sorted(mentions)), clusters=clusters, unresolved_mention_refs=unresolved)


def build_source_proposal_alignment(*, bundle: GraphFreeInterpretationBundle, parser_consensus: tuple[ParserConsensusAssessment, ...], segment_language_routes: SegmentLanguageRouteSet, predicate_event_ids: tuple[str, ...], predicate_event_inventory_fingerprint: str, coverage_policy_fingerprint: str, temporal_candidates: tuple[ResolvedTemporalCandidate, ...]) -> SourceProposalAlignment | None:
    """Derive exact joins and singleton groups, or fail closed on any gap."""
    subjects = tuple(subject for item in bundle.subject_sets for subject in item.subjects)
    parser_by_key = {(item.operation_id, item.proposal_id, item.segment_id, item.segment_language_route_digest): item for item in parser_consensus}
    if len(parser_by_key) != len(parser_consensus):
        return None
    scope_rows, temporal_rows = [], []
    scope_by_key = defaultdict(list)
    temporal_by_key = defaultdict(list)
    for item in bundle.scope_observations:
        scope_by_key[(item.operation_id, item.proposal_id, item.segment_id, item.segment_language_route_digest)].append(item)
    for item in bundle.temporal_attachment_observations:
        temporal_by_key[(item.operation_id, item.proposal_id, item.segment_id, item.segment_language_route_digest, item.temporal_role)].append(item)
    alignments = []
    for subject in subjects:
        key = (subject.operation_id, subject.proposal_id, subject.segment_id, subject.segment_language_route_digest)
        parser = parser_by_key.get(key)
        observations = scope_by_key.get(key, [])
        if parser is None or parser.status != "stable" or {item.analyzer_role for item in observations} != {"primary", "corroborating"} or len(observations) != 2:
            return None
        primary, corroborating = sorted(
            observations,
            key=lambda item: {"primary": 0, "corroborating": 1}[item.analyzer_role],
        )
        equal = primary.interpretation.model_dump(exclude={"analyzer_fingerprint", "interpretation_digest"}) == corroborating.interpretation.model_dump(exclude={"analyzer_fingerprint", "interpretation_digest"})
        checks = (primary.interpretation.polarity, primary.interpretation.commitment, primary.interpretation.attribution)
        if equal and all(item.status == "pass" for item in checks):
            scope_status = "stable"
            scope = StableSemanticScope.create(polarity="positive", commitment="asserted", attribution="speaker", attribution_bearer_span=None, governing_clause_spans=primary.interpretation.governing_clause_spans)
        elif equal and any(item.status == "unknown" for item in checks):
            scope_status, scope = "ambiguous", None
        elif equal and any(item.status == "fail" for item in checks):
            scope_status, scope = "unsupported", None
        else:
            scope_status, scope = "disagreement", None
        scope_row = SemanticScopeConsensus.create(source_id=bundle.source_id, source_digest=bundle.source_digest, preparation_fingerprint=bundle.preparation_fingerprint, segment_id=subject.segment_id, segment_language_route_digest=subject.segment_language_route_digest, proposal_id=subject.proposal_id, operation_id=subject.operation_id, analysis_bundle_fingerprint=bundle.analysis_bundle_fingerprint, primary_observation=primary, corroborating_observation=corroborating, stable_scope=scope, status=scope_status, consensus_policy_fingerprint=contract_digest(b"memorii.semantic-ingestion.scope-policy.v2", {"rule": "exact"}))
        scope_rows.append(scope_row)
        role_rows = []
        for role in _ROLES[subject.kind]:
            observations = temporal_by_key.get((*key, role), [])
            if len(observations) != 2 or {item.analyzer_role for item in observations} != {"primary", "corroborating"}:
                return None
            primary_t, corroborating_t = sorted(
                observations,
                key=lambda item: {"primary": 0, "corroborating": 1}[item.analyzer_role],
            )
            candidate_ids = primary_t.attachment.candidate_ids
            resolved = {item.candidate_id for item in temporal_candidates if item.segment_id == subject.segment_id}
            equal_attachment = primary_t.attachment.model_dump(exclude={"analyzer_fingerprint", "attachment_digest"}) == corroborating_t.attachment.model_dump(exclude={"analyzer_fingerprint", "attachment_digest"})
            if equal_attachment and set(candidate_ids).issubset(resolved) and candidate_ids:
                status, stable = "stable", candidate_ids
            elif equal_attachment:
                status, stable = "ambiguous", None
            else:
                status, stable = "disagreement", None
            row = TemporalAttachmentConsensus.create(source_id=bundle.source_id, source_digest=bundle.source_digest, preparation_fingerprint=bundle.preparation_fingerprint, segment_id=subject.segment_id, segment_language_route_digest=subject.segment_language_route_digest, proposal_id=subject.proposal_id, operation_id=subject.operation_id, temporal_role=role, temporal_resolution_fingerprint=bundle.temporal_resolution_fingerprint, primary_attachment=primary_t, corroborating_attachment=corroborating_t, stable_candidate_ids=stable, status=status, consensus_policy_fingerprint=contract_digest(b"memorii.semantic-ingestion.temporal-policy.v2", {"rule": "exact"}))
            temporal_rows.append(row)
            role_rows.append(row)
        if scope_row.status != "stable" or any(item.status != "stable" for item in role_rows):
            return None
        temporal_set = OperationTemporalAttachmentConsensusSet.create(operation_id=subject.operation_id, proposal_id=subject.proposal_id, segment_id=subject.segment_id, segment_language_route_digest=subject.segment_language_route_digest, role_consensus_digests=tuple((item.temporal_role, item.consensus_digest) for item in sorted(role_rows, key=lambda item: item.temporal_role)))
        alignments.append(OperationAlignment.create(operation_id=subject.operation_id, proposal_id=subject.proposal_id, segment_id=subject.segment_id, segment_language_route_digest=subject.segment_language_route_digest, parser_consensus_digest=parser.assessment_digest, scope_consensus_digest=scope_row.consensus_digest, temporal_attachment_consensus_set_digest=temporal_set.consensus_set_digest))
    alignments = tuple(sorted(alignments, key=lambda item: item.operation_id))
    if len(predicate_event_ids) != len(alignments):
        return None
    dispositions = tuple(CoveredPredicateEvent.create(event_id=event_id, proposal_ids=(alignment.proposal_id,), operation_ids=(alignment.operation_id,), alignment_digests=(alignment.alignment_digest,)) for event_id, alignment in zip(sorted(predicate_event_ids), alignments, strict=True))
    coverage = ProposalCoverageAudit.create(source_id=bundle.source_id, source_digest=bundle.source_digest, segment_language_routes=segment_language_routes, proposal_run_fingerprint=bundle.proposal_run_fingerprint, predicate_event_inventory_fingerprint=predicate_event_inventory_fingerprint, predicate_event_ids=tuple(sorted(predicate_event_ids)), dispositions=dispositions, covered_event_ids=tuple(item.event_id for item in dispositions), unresolved_event_ids=(), status="complete", coverage_policy_fingerprint=coverage_policy_fingerprint)
    groups = []
    for subject, alignment in zip(sorted(subjects, key=lambda item: item.operation_id), alignments, strict=True):
        kind, dependencies = _GROUPS[subject.kind]
        groups.append(SourceDependencyGroup.create(operation_ids=(alignment.operation_id,), segment_ids=(alignment.segment_id,), kind=kind, source_dependency_kinds=dependencies, atomic=True, status="complete", reason_codes=()))
    return SourceProposalAlignment.create(source_id=bundle.source_id, segment_language_routes=segment_language_routes, operation_alignments=alignments, parser_consensus=tuple(sorted(parser_consensus, key=lambda item: item.operation_id)), scope_consensus=tuple(sorted(scope_rows, key=lambda item: item.operation_id)), temporal_attachment_consensus=tuple(sorted(temporal_rows, key=lambda item: item.operation_id)), source_local_identity=resolve_source_local_identity(bundle.identity_partition_evidence), source_dependency_groups=tuple(sorted(groups, key=lambda item: item.group_id)), proposal_coverage=coverage, predicate_event_inventory_fingerprint=predicate_event_inventory_fingerprint, temporal_resolution_fingerprint=bundle.temporal_resolution_fingerprint, status="complete", reason_codes=())
