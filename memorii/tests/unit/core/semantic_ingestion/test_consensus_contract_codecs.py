"""Strict v1 codec and copied-span closure checks for consensus artifacts."""

from __future__ import annotations

import pytest
from memorii.core.memory_evolution.graph_records import GroundedMentionRef
from memorii.core.memory_evolution.semantic_analysis.policies import ConstructionFamily
from memorii.core.semantic_ingestion.contracts import (
    AnalyzerRoleInterpretation,
    AnalyzerScopeInterpretation,
    AnalyzerTemporalAttachment,
    CanonicalRoleAssignment,
    CheckResult,
    CoveredPredicateEvent,
    OperationAlignment,
    ParserConsensusAssessment,
    ProposalCoverageAudit,
    SegmentLanguageRouteSet,
    SemanticContractCodecError,
    SemanticScopeConsensus,
    SourceDependencyGroup,
    SourceLocalEntityClusterDecision,
    SourceLocalIdentityResolution,
    SourceProposalAlignment,
    StableSemanticScope,
    TemporalAttachmentConsensus,
    decode_semantic_contract,
    encode_semantic_contract,
)
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
    build_clean_room_semantic_proposal_request,
)


def _contracts():
    request = build_clean_room_semantic_proposal_request()
    span, route = request.owned_text, request.language_route
    assignment = CanonicalRoleAssignment.create(
        role_id="subject", argument_span=span, endpoint_kind="subject"
    )
    construction = ConstructionFamily.create(family_id="transitive")
    primary = AnalyzerRoleInterpretation.create(
        analyzer_fingerprint="1" * 64,
        predicate_head_span=span,
        construction_family=construction,
        assignments=(assignment,),
    )
    corroborating = AnalyzerRoleInterpretation.create(
        analyzer_fingerprint="2" * 64,
        predicate_head_span=span,
        construction_family=construction,
        assignments=(assignment,),
    )
    coordinates = {
        "source_id": request.source_id,
        "source_digest": request.source_digest,
        "preparation_fingerprint": request.preparation_fingerprint,
        "segment_id": request.segment_id,
        "proposal_id": "proposal-1",
        "operation_id": "operation-1",
        "segment_language_route_digest": route.route_digest,
        "analysis_bundle_fingerprint": "3" * 64,
        "consensus_policy_fingerprint": "4" * 64,
    }
    parser = ParserConsensusAssessment.create(
        **coordinates,
        primary_interpretation=primary,
        corroborating_interpretation=corroborating,
        stable_assignment=(assignment,),
        status="stable",
    )
    result = CheckResult(status="pass", reason_code="certified", evidence_spans=(span,), diagnostics=())
    scope_primary = AnalyzerScopeInterpretation.create(
        analyzer_fingerprint="1" * 64,
        proposal_id="proposal-1",
        predicate_head_span=span,
        governing_clause_spans=(span,),
        polarity=result,
        commitment=result,
        attribution=result,
        attribution_bearer_span=None,
    )
    scope_corroborating = AnalyzerScopeInterpretation.create(
        analyzer_fingerprint="2" * 64,
        proposal_id="proposal-1",
        predicate_head_span=span,
        governing_clause_spans=(span,),
        polarity=result,
        commitment=result,
        attribution=result,
        attribution_bearer_span=None,
    )
    stable_scope = StableSemanticScope.create(
        polarity="positive",
        commitment="asserted",
        attribution="speaker",
        attribution_bearer_span=None,
        governing_clause_spans=(span,),
    )
    scope = SemanticScopeConsensus.create(
        **coordinates,
        primary_interpretation=scope_primary,
        corroborating_interpretation=scope_corroborating,
        stable_scope=stable_scope,
        status="stable",
    )
    attachment_primary = AnalyzerTemporalAttachment.create(
        analyzer_fingerprint="1" * 64,
        proposal_id="proposal-1",
        predicate_head_span=span,
        candidate_ids=("candidate-1",),
        attachment_spans=(span,),
    )
    attachment_corroborating = AnalyzerTemporalAttachment.create(
        analyzer_fingerprint="2" * 64,
        proposal_id="proposal-1",
        predicate_head_span=span,
        candidate_ids=("candidate-1",),
        attachment_spans=(span,),
    )
    temporal = TemporalAttachmentConsensus.create(
        **{key: value for key, value in coordinates.items() if key != "analysis_bundle_fingerprint"},
        temporal_resolution_fingerprint="5" * 64,
        primary_attachment=attachment_primary,
        corroborating_attachment=attachment_corroborating,
        stable_candidate_ids=("candidate-1",),
        status="stable",
    )
    return parser, scope, temporal


def test_consensus_contracts_round_trip_only_as_closed_v1_bytes() -> None:
    for value in _contracts():
        assert decode_semantic_contract(encode_semantic_contract(value), type(value)) == value
    parser, _, _ = _contracts()
    legacy = parser.model_dump(mode="python")
    legacy.pop("operation_id")
    legacy["primary"] = legacy.pop("primary_interpretation")
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_semantic_contract(parser).replace(b"parser_consensus_assessment", b"parser-consensus-legacy"), type(parser))
    with pytest.raises(ValueError):
        ParserConsensusAssessment.model_validate(legacy)


@pytest.mark.parametrize("field", ("source_id", "segment_id", "proposal_id", "operation_id", "segment_language_route_digest"))
def test_parser_consensus_coordinate_substitutions_fail_closed(field: str) -> None:
    parser, _, _ = _contracts()
    changed = parser.model_dump(mode="python")
    changed[field] = "other" if field in {"source_id", "segment_id", "proposal_id", "operation_id"} else "a" * 64
    with pytest.raises(ValueError):
        ParserConsensusAssessment.model_validate(changed)


def _alignment() -> SourceProposalAlignment:
    parser, scope, temporal = _contracts()
    request = build_clean_room_semantic_proposal_request()
    route_set = SegmentLanguageRouteSet.create(
        source_id=request.source_id, source_digest=request.source_digest, routes=(request.language_route,)
    )
    operation = OperationAlignment.create(
        operation_id="operation-1", proposal_id="proposal-1", segment_id=request.segment_id,
        segment_language_route_digest=request.language_route.route_digest,
        parser_consensus_digest=parser.assessment_digest, scope_consensus_digest=scope.consensus_digest,
        temporal_attachment_consensus_digest=temporal.consensus_digest,
    )
    mention = GroundedMentionRef(source_id=request.source_id, start=0, end=1, cluster_id="cluster-1")
    identity = SourceLocalIdentityResolution.create(
        source_id=request.source_id, grounded_mention_refs=(mention,),
        clusters=(SourceLocalEntityClusterDecision(
            cluster_id="cluster-1", mention_refs=(mention,), decision="singleton_distinct",
            proof_kind="explicit_alias", source_evidence=(), language_policy_fingerprint="6" * 64, reason_codes=(),
        ),), unresolved_mention_refs=(), language_policy_fingerprint="6" * 64,
    )
    coverage = ProposalCoverageAudit.create(
        source_id=request.source_id, source_digest=request.source_digest, segment_language_routes=route_set,
        proposal_run_fingerprint="7" * 64, predicate_event_inventory_fingerprint="8" * 64,
        predicate_event_ids=("event-1",), dispositions=(CoveredPredicateEvent.create(
            event_id="event-1", proposal_ids=("proposal-1",), operation_ids=("operation-1",),
            alignment_digests=(operation.alignment_digest,),
        ),), covered_event_ids=("event-1",), unresolved_event_ids=(), status="complete",
        coverage_policy_fingerprint="9" * 64,
    )
    group = SourceDependencyGroup.create(
        operation_ids=("operation-1",), segment_ids=(request.segment_id,), kind="independent_fact",
        source_dependency_kinds=("assertion",), atomic=True, status="complete", reason_codes=(),
    )
    return SourceProposalAlignment(
        source_id=request.source_id, segment_language_routes=route_set, operation_alignments=(operation,),
        parser_consensus=(parser,), scope_consensus=(scope,), temporal_attachment_consensus=(temporal,),
        source_local_identity=identity, source_dependency_groups=(group,), proposal_coverage=coverage,
        predicate_event_inventory_fingerprint="8" * 64, temporal_resolution_fingerprint="a" * 64,
        status="complete", reason_codes=(), source_alignment_fingerprint="b" * 64,
    )


def test_source_alignment_requires_exact_canonical_consensus_rows_and_spans() -> None:
    alignment = _alignment()
    assert decode_semantic_contract(encode_semantic_contract(alignment), SourceProposalAlignment) == alignment
    changed = alignment.model_dump(mode="python")
    changed["parser_consensus"][0]["operation_id"] = "other-operation"
    with pytest.raises(ValueError, match="consensus"):
        SourceProposalAlignment.model_validate(changed)
    changed = alignment.model_dump(mode="python")
    changed["scope_consensus"][0]["primary_interpretation"]["predicate_head_span"]["projection_segment_id"] = "sibling-parent"
    with pytest.raises(ValueError):
        SourceProposalAlignment.model_validate(changed)
