"""Strict v1 codec and copied-span closure checks for consensus artifacts."""

from __future__ import annotations

import pytest
from memorii.core.memory_evolution.semantic_analysis.policies import ConstructionFamily
from memorii.core.semantic_ingestion.contracts import (
    AnalyzerRoleInterpretation,
    AnalyzerScopeInterpretation,
    AnalyzerScopeObservation,
    AnalyzerTemporalAttachment,
    AnalyzerTemporalAttachmentObservation,
    CanonicalRoleAssignment,
    CheckResult,
    CoveredPredicateEvent,
    OperationAlignment,
    OperationTemporalAttachmentConsensusSet,
    ParserConsensusAssessment,
    ProposalCoverageAudit,
    SegmentLanguageRouteSet,
    SemanticContractCodecError,
    SemanticScopeConsensus,
    SourceDependencyGroup,
    SourceLocalIdentityClusterDecision,
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
    scope_primary_observation = AnalyzerScopeObservation.create(
        **{key: value for key, value in coordinates.items() if key not in {"analysis_bundle_fingerprint", "consensus_policy_fingerprint"}},
        analyzer_role="primary", interpretation=scope_primary,
    )
    scope_corroborating_observation = AnalyzerScopeObservation.create(
        **{key: value for key, value in coordinates.items() if key not in {"analysis_bundle_fingerprint", "consensus_policy_fingerprint"}},
        analyzer_role="corroborating", interpretation=scope_corroborating,
    )
    scope = SemanticScopeConsensus.create(
        **coordinates,
        primary_observation=scope_primary_observation,
        corroborating_observation=scope_corroborating_observation,
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
    attachment_primary_observation = AnalyzerTemporalAttachmentObservation.create(
        **{key: value for key, value in coordinates.items() if key not in {"analysis_bundle_fingerprint", "consensus_policy_fingerprint"}},
        temporal_role="assertion", analyzer_role="primary", attachment=attachment_primary,
    )
    attachment_corroborating_observation = AnalyzerTemporalAttachmentObservation.create(
        **{key: value for key, value in coordinates.items() if key not in {"analysis_bundle_fingerprint", "consensus_policy_fingerprint"}},
        temporal_role="assertion", analyzer_role="corroborating", attachment=attachment_corroborating,
    )
    temporal = TemporalAttachmentConsensus.create(
        **{key: value for key, value in coordinates.items() if key != "analysis_bundle_fingerprint"},
        temporal_resolution_fingerprint="5" * 64,
        temporal_role="assertion",
        primary_attachment=attachment_primary_observation,
        corroborating_attachment=attachment_corroborating_observation,
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
    temporal_set = OperationTemporalAttachmentConsensusSet.create(
        operation_id="operation-1", proposal_id="proposal-1", segment_id=request.segment_id,
        segment_language_route_digest=request.language_route.route_digest,
        role_consensus_digests=(("assertion", temporal.consensus_digest),),
    )
    operation = OperationAlignment.create(
        operation_id="operation-1", proposal_id="proposal-1", segment_id=request.segment_id,
        segment_language_route_digest=request.language_route.route_digest,
        parser_consensus_digest=parser.assessment_digest, scope_consensus_digest=scope.consensus_digest,
        temporal_attachment_consensus_set_digest=temporal_set.consensus_set_digest,
    )
    mention = "mention-1"
    identity = SourceLocalIdentityResolution.create(
        source_id=request.source_id, grounded_mention_refs=(mention,),
        clusters=(SourceLocalIdentityClusterDecision.create(
            cluster_id="6" * 64, decision="singleton_distinct",
            proof_kind="explicit_alias", mention_digests=(mention,), source_evidence=(), segment_route_policy_closure=(),
        ),), unresolved_mention_refs=(),
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
    return SourceProposalAlignment.create(
        source_id=request.source_id, segment_language_routes=route_set, operation_alignments=(operation,),
        parser_consensus=(parser,), scope_consensus=(scope,), temporal_attachment_consensus=(temporal,),
        source_local_identity=identity, source_dependency_groups=(group,), proposal_coverage=coverage,
        predicate_event_inventory_fingerprint="8" * 64, temporal_resolution_fingerprint="a" * 64,
        status="complete", reason_codes=(),
    )


def test_source_alignment_requires_exact_canonical_consensus_rows_and_spans() -> None:
    alignment = _alignment()
    assert decode_semantic_contract(encode_semantic_contract(alignment), SourceProposalAlignment) == alignment
    changed = alignment.model_dump(mode="python")
    changed["parser_consensus"][0]["operation_id"] = "other-operation"
    with pytest.raises(ValueError, match="consensus"):
        SourceProposalAlignment.model_validate(changed)
    changed = alignment.model_dump(mode="python")
    changed["scope_consensus"][0]["primary_observation"]["interpretation"]["predicate_head_span"]["projection_segment_id"] = "sibling-parent"
    with pytest.raises(ValueError):
        SourceProposalAlignment.model_validate(changed)


def test_source_alignment_rejects_retired_singular_temporal_and_unversioned_shapes() -> None:
    alignment = _alignment()
    old_shape = alignment.model_dump(mode="python")
    old_shape.pop("schema_version")
    with pytest.raises(ValueError, match="schema_version"):
        SourceProposalAlignment.model_validate(old_shape)

    old_operation = alignment.operation_alignments[0].model_dump(mode="python")
    old_operation.pop("schema_version")
    old_operation["temporal_attachment_consensus_digest"] = alignment.temporal_attachment_consensus[0].consensus_digest
    old_operation.pop("temporal_attachment_consensus_set_digest")
    with pytest.raises(ValueError):
        OperationAlignment.model_validate(old_operation)
