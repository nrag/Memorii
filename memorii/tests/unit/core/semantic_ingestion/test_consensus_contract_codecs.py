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
    ParserConsensusAssessment,
    SemanticContractCodecError,
    SemanticScopeConsensus,
    StableSemanticScope,
    TemporalAttachmentConsensus,
    decode_semantic_contract,
    encode_semantic_contract,
)
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
    build_clean_room_proposal_catalogs,
)


def _contracts():
    request = build_clean_room_proposal_catalogs()
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






