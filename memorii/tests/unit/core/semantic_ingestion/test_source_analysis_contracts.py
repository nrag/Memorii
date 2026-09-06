"""Strict-wire regression proof for independent source-analysis contracts."""

from __future__ import annotations

import base64
import json
import zlib
from pathlib import Path

import pytest
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    AnalyzerManifest,
    ClauseAnalysis,
    ClauseArgument,
    DependencyArc,
    LanguageCandidate,
    LinguisticAnalysis,
    LinguisticAnalysisRequest,
    LinguisticFeature,
    LinguisticToken,
    PredicateEventDetectionRequest,
    PredicateEventManifest,
    SegmentAnalysisInput,
    SegmentLanguageLaneOutcome,
    SegmentLanguageResourceBinding,
    SegmentLanguageRoute,
    SemanticProposal,
    SourceMention,
    TemporalResolutionRequest,
    TemporalResolverManifest,
    decode_semantic_contract,
    encode_semantic_contract,
    restore_closed_wire_enums,
)

_FIXTURE = (
    Path(__file__).parents[3]
    / "fixtures"
    / "semantic_ingestion"
    / "normalization_contracts"
    / "semantic_proposal_literal_v1.json"
)


def _proposal() -> SemanticProposal:
    vector = json.loads(_FIXTURE.read_text(encoding="ascii"))
    body = decode_typed_value(zlib.decompress(base64.b64decode(vector["expected_ctv_preimage_zlib_base64"])))
    payload = json.loads(zlib.decompress(base64.b64decode(vector["semantic_proposal_zlib_base64"])))
    body["proposal_digest"] = payload["proposal_digest"]
    body = restore_closed_wire_enums(body)
    body["preparation_fingerprint"] = "1" * 64
    route = body["language_route"]
    assert isinstance(route, dict)
    body["language_route"] = SegmentLanguageRoute.create(
        **({key: value for key, value in route.items() if key != "route_digest"} | {"parent_projection_segment_id": body["segment_id"], "candidates": (LanguageCandidate(language="en", probability_ppm=1_000_000, model_fingerprint="1" * 64),)})
    )
    return SemanticProposal.create(
        **({key: value for key, value in body.items() if key != "proposal_digest"} | {"originating_attempt_digest": "0" * 64})
    )


def _analysis_fixture() -> tuple[SemanticProposal, LinguisticAnalysis, LinguisticAnalysis, SegmentLanguageLaneOutcome, SegmentLanguageLaneOutcome]:
    proposal = _proposal()
    route = proposal.language_route
    assert route.decision == "selected" and route.resource_binding is not None and route.selected_language is not None
    span = proposal.owned_text
    token = LinguisticToken.create(source_span=span, surface_text="Alice", lemma="alice", upos="PROPN", xpos=None, morphological_features=(), sentence_index=0, word_index=0, syntactic_word_index=0, multi_word_token_span=None)
    arc = DependencyArc.create(dependent_token_id=token.token_id, governor_token_id=None, relation="root", enhanced=False)
    mention = SourceMention.create(kind="noun_phrase", source_span=span, token_ids=(token.token_id,), head_token_id=token.token_id, entity_label=None, coordination_group_id=None)
    argument = ClauseArgument.create(grammatical_role="root", head_token_id=token.token_id, source_span=span, mention_digest=mention.mention_digest)
    clause = ClauseAnalysis.create(source_span=span, parent_clause_id=None, predicate_head_token_id=token.token_id, predicate_span=span, arguments=(argument,), voice="active", negation_token_ids=(), dependency_arc_ids=(arc.arc_id,), morphological_polarity_features=(), mood_features=(), modality_features=(), quotation_evidence=None, coordination_group_ids=(), limitations=())

    def build(manifest_digest: str, fingerprint: str) -> LinguisticAnalysis:
        return LinguisticAnalysis.create(source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_id=proposal.segment_id, segment_language_route_digest=route.route_digest, analyzer_manifest_digest=manifest_digest, analyzer_fingerprint=fingerprint, language=route.selected_language, tokens=(token,), mentions=(mention,), clauses=(clause,), dependencies=(arc,), status="complete", diagnostics=())

    binding = route.resource_binding
    primary = build(binding.stanza_analyzer_manifest_digest, "1" * 64)
    corroborating = build(binding.spacy_analyzer_manifest_digest, "2" * 64)
    primary_outcome = SegmentLanguageLaneOutcome.create(lane="stanza", segment_id=proposal.segment_id, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_route_digest=route.route_digest, resource_binding_digest=binding.resource_binding_digest, selected_manifest_digest=binding.stanza_analyzer_manifest_digest, status="complete", artifact_digest=primary.analysis_digest, reason_codes=())
    corroborating_outcome = SegmentLanguageLaneOutcome.create(lane="spacy", segment_id=proposal.segment_id, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_route_digest=route.route_digest, resource_binding_digest=binding.resource_binding_digest, selected_manifest_digest=binding.spacy_analyzer_manifest_digest, status="complete", artifact_digest=corroborating.analysis_digest, reason_codes=())
    return proposal, primary, corroborating, primary_outcome, corroborating_outcome


def test_step_four_leaf_codecs_round_trip_and_reject_digest_substitution() -> None:
    feature = LinguisticFeature.create(name="Number", value="Sing")
    assert decode_semantic_contract(encode_semantic_contract(feature), LinguisticFeature) == feature
    with pytest.raises(ValueError, match="feature_digest mismatch"):
        LinguisticFeature.model_validate(feature.model_dump() | {"feature_digest": "f" * 64})

    manifest = AnalyzerManifest.create(
        analyzer_id="stanza-en",
        analyzer_kind="stanza",
        library_version="1",
        resource_manifest_digest="1" * 64,
        model_file_hashes=("2" * 64,),
        processor_configuration_digest="3" * 64,
        adapter_version="1",
        supported_languages=("en",),
        analyzer_fingerprint="4" * 64,
    )
    assert decode_semantic_contract(encode_semantic_contract(manifest), AnalyzerManifest) == manifest

    resolver = TemporalResolverManifest.create(
        binary_digest="5" * 64,
        ruleset_version="1",
        locale_map_digest="6" * 64,
        timezone_policy_digest="7" * 64,
        adapter_schema_digest="8" * 64,
        supported_construction_families=("absolute",),
    )
    assert decode_semantic_contract(encode_semantic_contract(resolver), TemporalResolverManifest) == resolver


def test_lane_status_algebra_rejects_missing_or_forbidden_artifacts() -> None:
    with pytest.raises(ValueError, match="requires artifact"):
        SegmentLanguageLaneOutcome.create(
            lane="stanza",
            segment_id="segment",
            preparation_fingerprint="a" * 64,
            segment_language_route_digest="a" * 64,
            resource_binding_digest="b" * 64,
            selected_manifest_digest="c" * 64,
            status="complete",
            artifact_digest=None,
            reason_codes=(),
        )






def test_segment_analysis_input_and_requests_bind_selected_route_authority() -> None:
    proposal = _proposal()
    route = proposal.language_route
    assert route.resource_binding is not None and route.selected_language is not None
    segment = SegmentAnalysisInput.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, segment_id=proposal.segment_id,
        preparation_fingerprint=proposal.preparation_fingerprint, parent_projection_segment_id=route.parent_projection_segment_id,
        segment_governance=proposal.segment_governance,
        message_admission_identity=proposal.message_admission_identity,
        governance_carrier_artifact=proposal.governance_carrier_artifact,
        context_text=proposal.context_text, segment_text="source fixture text", language_route=route,
    )
    assert decode_semantic_contract(encode_semantic_contract(segment), SegmentAnalysisInput) == segment

    analyzer = AnalyzerManifest.create(analyzer_id="stanza-en", analyzer_kind="stanza", library_version="1", resource_manifest_digest="1" * 64, model_file_hashes=("2" * 64,), processor_configuration_digest="3" * 64, adapter_version="1", supported_languages=(route.selected_language,), analyzer_fingerprint="4" * 64)
    spacy = AnalyzerManifest.create(analyzer_id="spacy-en", analyzer_kind="spacy", library_version="1", resource_manifest_digest="5" * 64, model_file_hashes=("6" * 64,), processor_configuration_digest="7" * 64, adapter_version="1", supported_languages=(route.selected_language,), analyzer_fingerprint="8" * 64)
    predicate = PredicateEventManifest.create(language=route.selected_language, predicate_lemmas=("employ",), inflection_table_digest="9" * 64, multi_token_forms=())
    resolver = TemporalResolverManifest.create(binary_digest="a" * 64, ruleset_version="1", locale_map_digest="b" * 64, timezone_policy_digest="c" * 64, adapter_schema_digest="d" * 64, supported_construction_families=("absolute",))
    binding = SegmentLanguageResourceBinding.create(
        selected_language=route.selected_language, proposal_capability_fingerprint=route.resource_binding.proposal_capability_fingerprint,
        stanza_analyzer_manifest_digest=analyzer.manifest_digest, spacy_analyzer_manifest_digest=spacy.manifest_digest,
        predicate_event_manifest_digest=predicate.manifest_digest, temporal_resolver_manifest_digest=resolver.manifest_digest,
    )
    selected_route = SegmentLanguageRoute.create(
        **(route.model_dump(mode="python", exclude={"route_digest"}) | {"resource_binding": binding})
    )
    selected_segment = SegmentAnalysisInput.create(
        **(segment.model_dump(mode="python", exclude={"input_digest"}) | {"language_route": selected_route})
    )
    assert LinguisticAnalysisRequest.create(segment=selected_segment, analyzer_manifest=analyzer).segment == selected_segment
    assert PredicateEventDetectionRequest.create(segment=selected_segment, predicate_event_manifest=predicate).segment == selected_segment
    assert TemporalResolutionRequest.create(segment=selected_segment, resolver_manifest=resolver, reference_evidence=None).segment == selected_segment

    altered_context_artifact = proposal.context_text.segment_local_span.artifact.model_copy(
        update={"artifact_id": "other"}
    )
    mutations = (
        {"segment_governance": proposal.governance_carrier_artifact.segment_governance.bindings[0].model_copy(update={"segment_id": "other"})},
        {"message_admission_identity": proposal.message_admission_identity.model_copy(update={"segment_governance_binding_digest": "0" * 64})},
        {"governance_carrier_artifact": proposal.governance_carrier_artifact.model_copy(update={"segment_governance": proposal.governance_carrier_artifact.segment_governance.model_copy(update={"source_id": "other"})})},
        {"context_text": proposal.context_text.model_copy(update={"segment_local_span": proposal.context_text.segment_local_span.model_copy(update={"artifact": altered_context_artifact})})},
        {"language_route": route.model_copy(update={"segment_text_artifact_id": "other"})},
    )
    for mutation in mutations:
        with pytest.raises(ValueError):
            SegmentAnalysisInput.create(**(segment.model_dump(mode="python", exclude={"input_digest"}) | mutation))

    wrong_analyzer = AnalyzerManifest.create(analyzer_id="stanza-other", analyzer_kind="stanza", library_version="1", resource_manifest_digest="0" * 64, model_file_hashes=("1" * 64,), processor_configuration_digest="2" * 64, adapter_version="1", supported_languages=(route.selected_language,), analyzer_fingerprint="3" * 64)
    with pytest.raises(ValueError, match="manifest must match selected route"):
        LinguisticAnalysisRequest.create(segment=selected_segment, analyzer_manifest=wrong_analyzer)
    with pytest.raises(ValueError, match="manifest must match selected route"):
        PredicateEventDetectionRequest.create(segment=selected_segment, predicate_event_manifest=PredicateEventManifest.create(language="other", predicate_lemmas=("employ",), inflection_table_digest="9" * 64, multi_token_forms=()))
    with pytest.raises(ValueError, match="manifest must match selected route"):
        TemporalResolutionRequest.create(segment=selected_segment, resolver_manifest=TemporalResolverManifest.create(binary_digest="e" * 64, ruleset_version="1", locale_map_digest="b" * 64, timezone_policy_digest="c" * 64, adapter_schema_digest="d" * 64, supported_construction_families=("absolute",)), reference_evidence=None)






