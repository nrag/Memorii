"""Strict-wire regression proof for independent source-analysis contracts."""

from __future__ import annotations

import base64
import json
import zlib
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import pytest
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value, encode_typed_value
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.semantic_ingestion.contracts import (
    AnalyzerManifest,
    ClauseAnalysis,
    ClauseArgument,
    ClauseQuotationEvidence,
    DependencyArc,
    LanguageCandidate,
    LinguisticAnalysis,
    LinguisticAnalysisBundle,
    LinguisticAnalysisRequest,
    LinguisticFeature,
    LinguisticToken,
    PredicateEventCandidate,
    PredicateEventDetectionRequest,
    PredicateEventInventory,
    PredicateEventManifest,
    ResolvedTemporalCandidate,
    SegmentAnalysisInput,
    SegmentLanguageLaneOutcome,
    SegmentLanguageResourceBinding,
    SegmentLanguageRoute,
    SegmentLanguageRouteSet,
    SegmentLinguisticAnalysisBundle,
    SemanticContractCodecError,
    SemanticProposal,
    SourceMention,
    TemporalResolution,
    TemporalResolutionRequest,
    TemporalResolverManifest,
    _restore_closed_wire_enums,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
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
    body = _restore_closed_wire_enums(body)
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


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("complete", "complete", "complete"),
        ("complete", "partial", "partial"),
        ("complete", "failed", "partial"),
        ("partial", "failed", "partial"),
        ("failed", "failed", "failed"),
        ("unsupported", "unsupported", "unsupported"),
        ("evidence_only", "evidence_only", "evidence_only"),
        ("failed", "unsupported", "failed"),
    ],
)
def test_two_lane_parser_status_table_is_exhaustive_for_terminal_precedence(
    left: str, right: str, expected: str
) -> None:
    proposal, primary, corroborating, stanza, spacy = _analysis_fixture()
    route = proposal.language_route
    assert route.resource_binding is not None

    def lane(base: SegmentLanguageLaneOutcome, status: str, analysis: LinguisticAnalysis) -> SegmentLanguageLaneOutcome:
        resource_values = (
            {"resource_binding_digest": None, "selected_manifest_digest": None}
            if status == "evidence_only"
            else {}
        )
        return SegmentLanguageLaneOutcome.create(
            **(
                base.model_dump(mode="python", exclude={"outcome_digest"})
                | resource_values
                | {"status": status, "artifact_digest": analysis.analysis_digest if status in {"complete", "partial"} else None}
            )
        )

    left_outcome = lane(stanza, left, primary)
    right_outcome = lane(spacy, right, corroborating)
    left_analysis = primary if left in {"complete", "partial"} else None
    right_analysis = corroborating if right in {"complete", "partial"} else None
    bundle = SegmentLinguisticAnalysisBundle.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_id=proposal.segment_id,
        segment_language_route_digest=route.route_digest, primary=left_analysis, corroborating=right_analysis,
        lane_outcomes=(left_outcome, right_outcome), status=expected, diagnostics=(),
    )
    assert bundle.status == expected


@pytest.mark.parametrize("statuses", tuple(product(("complete", "partial", "evidence_only", "unsupported", "failed"), repeat=2)))
def test_all_valid_ordered_lane_status_pairs_derive_parser_predicate_and_temporal_statuses(
    statuses: tuple[str, str],
) -> None:
    proposal, primary, corroborating, stanza, spacy = _analysis_fixture()
    route = proposal.language_route
    assert route.resource_binding is not None
    second_route = SegmentLanguageRoute.create(
        **(route.model_dump(mode="python", exclude={"route_digest"}) | {"segment_id": "segment-z"})
    )

    def aggregate_route(route_item: SegmentLanguageRoute, status: str) -> SegmentLanguageRoute:
        if status != "evidence_only":
            return route_item
        return SegmentLanguageRoute.create(
            **(
                route_item.model_dump(mode="python", exclude={"route_digest"})
                | {"decision": "unsupported", "selected_language": None, "resource_binding": None}
            )
        )

    def expected_parser(pair: tuple[str, str]) -> str:
        if pair == ("evidence_only", "evidence_only"):
            return "evidence_only"
        if pair == ("complete", "complete"):
            return "complete"
        if any(status in {"complete", "partial"} for status in pair):
            return "partial"
        if "failed" in pair:
            return "failed"
        if "unsupported" in pair:
            return "unsupported"
        return "partial"

    def expected_aggregate(pair: tuple[str, str]) -> str:
        if all(status == "evidence_only" for status in pair):
            return "evidence_only"
        if "failed" in pair:
            return "failed"
        if all(status in {"complete", "evidence_only"} for status in pair) and "complete" in pair:
            return "complete"
        if all(status in {"unsupported", "evidence_only"} for status in pair) and "unsupported" in pair:
            return "unsupported"
        return "partial"

    def outcome(route_item: SegmentLanguageRoute, lane: str, status: str) -> SegmentLanguageLaneOutcome:
        fields = {
            "stanza": "stanza_analyzer_manifest_digest",
            "spacy": "spacy_analyzer_manifest_digest",
            "predicate_event_detection": "predicate_event_manifest_digest",
            "temporal_resolution": "temporal_resolver_manifest_digest",
        }
        return SegmentLanguageLaneOutcome.create(
            lane=lane, segment_id=route_item.segment_id, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_route_digest=route_item.route_digest,
            resource_binding_digest=None if status == "evidence_only" else route_item.resource_binding.resource_binding_digest,  # type: ignore[union-attr]
            selected_manifest_digest=None if status == "evidence_only" else getattr(route_item.resource_binding, fields[lane]),  # type: ignore[arg-type]
            status=status, artifact_digest="a" * 64 if status in {"complete", "partial"} else None,
            reason_codes=(),
        )

    def parser_outcome(
        base: SegmentLanguageLaneOutcome, status: str, analysis: LinguisticAnalysis
    ) -> SegmentLanguageLaneOutcome:
        return SegmentLanguageLaneOutcome.create(
            **(
                base.model_dump(mode="python", exclude={"outcome_digest"})
                | (
                    {"resource_binding_digest": None, "selected_manifest_digest": None}
                    if status == "evidence_only"
                    else {}
                )
                | {"status": status, "artifact_digest": analysis.analysis_digest if status in {"complete", "partial"} else None}
            )
        )

    parser_outcomes = (
        parser_outcome(stanza, statuses[0], primary),
        parser_outcome(spacy, statuses[1], corroborating),
    )
    parser_expected = expected_parser(statuses)
    parser_bundle = SegmentLinguisticAnalysisBundle.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_id=proposal.segment_id,
        segment_language_route_digest=route.route_digest,
        primary=primary if statuses[0] in {"complete", "partial"} else None,
        corroborating=corroborating if statuses[1] in {"complete", "partial"} else None,
        lane_outcomes=parser_outcomes, status=parser_expected, diagnostics=(),
    )
    assert parser_bundle.status == parser_expected
    wrong_parser = "failed" if parser_expected != "failed" else "complete"
    with pytest.raises(ValueError, match="lanes and status must be derived"):
        SegmentLinguisticAnalysisBundle.create(
            **(parser_bundle.model_dump(mode="python", exclude={"bundle_fingerprint"}) | {"status": wrong_parser})
        )

    aggregate_expected = expected_aggregate(statuses)
    aggregate_routes = SegmentLanguageRouteSet.create(
        source_id=proposal.source_id,
        source_digest=proposal.source_digest,
        routes=(aggregate_route(route, statuses[0]), aggregate_route(second_route, statuses[1])),
    )
    for lane, aggregate_type, digest_field in (
        ("predicate_event_detection", PredicateEventInventory, "inventory_fingerprint"),
        ("temporal_resolution", TemporalResolution, "resolver_fingerprint"),
    ):
        outcomes = tuple(
            outcome(route_item, lane, status)
            for route_item, status in zip(aggregate_routes.routes, statuses, strict=True)
        )
        values: dict[str, object] = {
            "source_id": proposal.source_id,
            "source_digest": proposal.source_digest,
            "preparation_fingerprint": proposal.preparation_fingerprint,
            "segment_language_routes": aggregate_routes,
            "segment_outcomes": outcomes,
            "candidates": (),
            "status": aggregate_expected,
        }
        if aggregate_type is TemporalResolution:
            values.update({"ambiguous_spans": (), "diagnostics": ()})
        aggregate = aggregate_type.create(**values)
        assert aggregate.status == aggregate_expected
        wrong_aggregate = "failed" if aggregate_expected != "failed" else "complete"
        with pytest.raises(ValueError, match="status must be derived"):
            aggregate_type.create(
                **(aggregate.model_dump(mode="python", exclude={digest_field}) | {"status": wrong_aggregate})
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


def test_analysis_contract_codecs_reject_closed_envelope_swaps() -> None:
    proposal, primary, corroborating, stanza, spacy = _analysis_fixture()
    route_set = SegmentLanguageRouteSet.create(source_id=proposal.source_id, source_digest=proposal.source_digest, routes=(proposal.language_route,))
    bundle = SegmentLinguisticAnalysisBundle.create(source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_id=proposal.segment_id, segment_language_route_digest=proposal.language_route.route_digest, primary=primary, corroborating=corroborating, lane_outcomes=(stanza, spacy), status="complete", diagnostics=())
    values = (stanza, primary, bundle, LinguisticAnalysisBundle.create(source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_routes=route_set, segment_bundles=(bundle,), segment_outcomes=(stanza, spacy), status="complete", diagnostics=()))
    for value in values:
        encoded = encode_semantic_contract(value)
        envelope = decode_typed_value(encoded)
        assert isinstance(envelope, dict)
        assert decode_semantic_contract(encoded, type(value)) == value
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value({**envelope, "kind": "future_contract"}), type(value))


def test_analysis_bundle_and_leaf_mutation_matrix_rejects_cross_route_and_internal_closure() -> None:
    proposal, primary, corroborating, stanza, spacy = _analysis_fixture()
    route = proposal.language_route
    assert route.resource_binding is not None
    segment_bundle = SegmentLinguisticAnalysisBundle.create(source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_id=proposal.segment_id, segment_language_route_digest=route.route_digest, primary=primary, corroborating=corroborating, lane_outcomes=(stanza, spacy), status="complete", diagnostics=())
    bundle = LinguisticAnalysisBundle.create(source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_routes=SegmentLanguageRouteSet.create(source_id=proposal.source_id, source_digest=proposal.source_digest, routes=(route,)), segment_bundles=(segment_bundle,), segment_outcomes=(stanza, spacy), status="complete", diagnostics=())
    assert bundle.segment_bundles == (segment_bundle,)

    bad_lane = SegmentLanguageLaneOutcome.create(**(stanza.model_dump(mode="python", exclude={"outcome_digest"}) | {"selected_manifest_digest": "f" * 64}))
    with pytest.raises(ValueError, match="selected resource and manifest"):
        LinguisticAnalysisBundle.create(**(bundle.model_dump(mode="python", exclude={"bundle_fingerprint"}) | {"segment_bundles": (SegmentLinguisticAnalysisBundle.create(**(segment_bundle.model_dump(mode="python", exclude={"bundle_fingerprint"}) | {"lane_outcomes": (bad_lane, spacy)})),), "segment_outcomes": (bad_lane, spacy)}))

    token = primary.tokens[0]
    duplicate_coordinate = LinguisticToken.create(**(token.model_dump(mode="python", exclude={"token_id"}) | {"lemma": "other"}))
    duplicate_arc = DependencyArc.create(dependent_token_id=duplicate_coordinate.token_id, governor_token_id=None, relation="root", enhanced=False)
    with pytest.raises(ValueError, match="token coordinates"):
        LinguisticAnalysis.create(**(primary.model_dump(mode="python", exclude={"analysis_digest"}) | {"tokens": (token, duplicate_coordinate), "dependencies": (primary.dependencies[0], duplicate_arc)}))

    child_clause = ClauseAnalysis.create(**(primary.clauses[0].model_dump(mode="python", exclude={"clause_id"}) | {"parent_clause_id": "0" * 64}))
    parent_clause = ClauseAnalysis.create(**(primary.clauses[0].model_dump(mode="python", exclude={"clause_id"}) | {"parent_clause_id": child_clause.clause_id}))
    child_clause = ClauseAnalysis.create(**(child_clause.model_dump(mode="python", exclude={"clause_id"}) | {"parent_clause_id": parent_clause.clause_id}))
    with pytest.raises(ValueError, match="clause parent"):
        LinguisticAnalysis.create(**(primary.model_dump(mode="python", exclude={"analysis_digest"}) | {"clauses": (parent_clause, child_clause)}))

    lexical = proposal.owned_text
    event_identity = {"segment_id": proposal.segment_id, "preparation_fingerprint": proposal.preparation_fingerprint, "segment_language_route_digest": route.route_digest, "predicate_family": "employment", "lexical_anchor_span": lexical, "detection_rule_id": "rule", "detection_manifest_fingerprint": route.resource_binding.predicate_event_manifest_digest}
    event = PredicateEventCandidate.create(**event_identity, event_id=contract_digest(b"memorii.semantic-ingestion.predicate-event-identity.v1", event_identity), morphology_evidence_spans=())
    event_lane = SegmentLanguageLaneOutcome.create(lane="predicate_event_detection", segment_id=proposal.segment_id, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_route_digest=route.route_digest, resource_binding_digest=route.resource_binding.resource_binding_digest, selected_manifest_digest=route.resource_binding.predicate_event_manifest_digest, status="complete", artifact_digest="3" * 64, reason_codes=())
    inventory = PredicateEventInventory.create(source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_routes=bundle.segment_language_routes, segment_outcomes=(event_lane,), candidates=(event,), status="complete")
    assert inventory.candidates == (event,)
    with pytest.raises(ValueError, match="artifact-bearing route outcome"):
        PredicateEventInventory.create(**(inventory.model_dump(mode="python", exclude={"inventory_fingerprint"}) | {"segment_outcomes": (SegmentLanguageLaneOutcome.create(**(event_lane.model_dump(mode="python", exclude={"outcome_digest"}) | {"artifact_digest": None, "status": "failed"})),), "status": "failed"}))

    interval = TimeInterval(start=datetime(2026, 1, 1, tzinfo=UTC))
    temporal_identity = {"segment_id": proposal.segment_id, "preparation_fingerprint": proposal.preparation_fingerprint, "segment_language_route_digest": route.route_digest, "source_span": lexical, "value_kind": "instant", "normalized_interval": interval, "normalized_duration": None, "grain": "day", "locale": "en", "timezone": "UTC", "reference_evidence": None, "resolver_rule_id": "absolute"}
    temporal = ResolvedTemporalCandidate.create(**temporal_identity, candidate_id=contract_digest(b"memorii.semantic-ingestion.resolved-temporal-candidate-identity.v1", temporal_identity), exact_text="2026-01-01")
    temporal_lane = SegmentLanguageLaneOutcome.create(lane="temporal_resolution", segment_id=proposal.segment_id, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_route_digest=route.route_digest, resource_binding_digest=route.resource_binding.resource_binding_digest, selected_manifest_digest=route.resource_binding.temporal_resolver_manifest_digest, status="complete", artifact_digest="4" * 64, reason_codes=())
    resolution = TemporalResolution.create(source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_routes=bundle.segment_language_routes, segment_outcomes=(temporal_lane,), candidates=(temporal,), ambiguous_spans=(), status="complete", diagnostics=())
    assert resolution.candidates == (temporal,)
    for mutation in (
        {"segment_id": "foreign"},
        {"segment_language_route_digest": "f" * 64},
    ):
        foreign_identity = temporal.model_dump(mode="python", exclude={"candidate_digest", "candidate_id"}) | mutation
        foreign = ResolvedTemporalCandidate.create(
            **foreign_identity,
            candidate_id=contract_digest(
                b"memorii.semantic-ingestion.resolved-temporal-candidate-identity.v1",
                {name: foreign_identity[name] for name in (
                        "segment_id", "preparation_fingerprint", "segment_language_route_digest", "source_span", "value_kind",
                    "normalized_interval", "normalized_duration", "grain", "locale", "timezone",
                    "reference_evidence", "resolver_rule_id",
                )},
            ),
        )
        with pytest.raises(ValueError, match="temporal candidates must join"):
            TemporalResolution.create(
                **(resolution.model_dump(mode="python", exclude={"resolver_fingerprint"}) | {"candidates": (foreign,)})
            )
    failed_lane = SegmentLanguageLaneOutcome.create(
        **(temporal_lane.model_dump(mode="python", exclude={"outcome_digest"}) | {"status": "failed", "artifact_digest": None})
    )
    with pytest.raises(ValueError, match="temporal candidates must join"):
        TemporalResolution.create(
            **(
                resolution.model_dump(mode="python", exclude={"resolver_fingerprint"})
                | {"segment_outcomes": (failed_lane,), "status": "failed"}
            )
        )
    with pytest.raises(ValueError, match="identity mismatch"):
        ResolvedTemporalCandidate.create(**(temporal.model_dump(mode="python", exclude={"candidate_digest", "candidate_id"}) | {"candidate_id": temporal.candidate_id, "resolver_rule_id": "other"}))
    with pytest.raises(ValueError, match="no selected resource"):
        SegmentLanguageLaneOutcome.create(
            lane="stanza",
            segment_id="segment",
            preparation_fingerprint="a" * 64,
            segment_language_route_digest="a" * 64,
            resource_binding_digest="b" * 64,
            selected_manifest_digest="c" * 64,
            status="evidence_only",
            artifact_digest=None,
            reason_codes=(),
        )


def test_every_step_four_contract_uses_the_same_closed_strict_envelope() -> None:
    proposal, primary, corroborating, stanza, spacy = _analysis_fixture()
    route = proposal.language_route
    assert route.resource_binding is not None and route.selected_language is not None
    route_set = SegmentLanguageRouteSet.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, routes=(route,)
    )
    segment_bundle = SegmentLinguisticAnalysisBundle.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_id=proposal.segment_id,
        segment_language_route_digest=route.route_digest, primary=primary, corroborating=corroborating,
        lane_outcomes=(stanza, spacy), status="complete", diagnostics=(),
    )
    analysis_bundle = LinguisticAnalysisBundle.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_routes=route_set,
        segment_bundles=(segment_bundle,), segment_outcomes=(stanza, spacy), status="complete", diagnostics=(),
    )
    feature = LinguisticFeature.create(name="Number", value="Sing")
    quotation = ClauseQuotationEvidence.create(
        opening_token_id=primary.tokens[0].token_id, closing_token_id=None, reporting_head_token_id=None,
        complement_clause_id=None, attribution_argument_digest=None,
    )
    predicate_manifest = PredicateEventManifest.create(
        language=route.selected_language, predicate_lemmas=("employ",), inflection_table_digest="1" * 64,
        multi_token_forms=(),
    )
    resolver = TemporalResolverManifest.create(
        binary_digest="2" * 64, ruleset_version="1", locale_map_digest="3" * 64,
        timezone_policy_digest="4" * 64, adapter_schema_digest="5" * 64,
        supported_construction_families=("absolute",),
    )
    stanza_manifest = AnalyzerManifest.create(
        analyzer_id="stanza", analyzer_kind="stanza", library_version="1", resource_manifest_digest="6" * 64,
        model_file_hashes=("7" * 64,), processor_configuration_digest="8" * 64, adapter_version="1",
        supported_languages=(route.selected_language,), analyzer_fingerprint="9" * 64,
    )
    spacy_manifest = AnalyzerManifest.create(
        analyzer_id="spacy", analyzer_kind="spacy", library_version="1", resource_manifest_digest="a" * 64,
        model_file_hashes=("b" * 64,), processor_configuration_digest="c" * 64, adapter_version="1",
        supported_languages=(route.selected_language,), analyzer_fingerprint="d" * 64,
    )
    binding = SegmentLanguageResourceBinding.create(
        selected_language=route.selected_language,
        proposal_capability_fingerprint=route.resource_binding.proposal_capability_fingerprint,
        stanza_analyzer_manifest_digest=stanza_manifest.manifest_digest,
        spacy_analyzer_manifest_digest=spacy_manifest.manifest_digest,
        predicate_event_manifest_digest=predicate_manifest.manifest_digest,
        temporal_resolver_manifest_digest=resolver.manifest_digest,
    )
    request_route = SegmentLanguageRoute.create(
        **(route.model_dump(mode="python", exclude={"route_digest"}) | {"resource_binding": binding})
    )
    segment = SegmentAnalysisInput.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, segment_id=proposal.segment_id,
        preparation_fingerprint=proposal.preparation_fingerprint, parent_projection_segment_id=request_route.parent_projection_segment_id,
        segment_governance=proposal.segment_governance,
        message_admission_identity=proposal.message_admission_identity,
        governance_carrier_artifact=proposal.governance_carrier_artifact, context_text=proposal.context_text,
        segment_text="fixture", language_route=request_route,
    )
    event_identity = {
        "segment_id": proposal.segment_id, "preparation_fingerprint": proposal.preparation_fingerprint, "segment_language_route_digest": route.route_digest,
            "predicate_family": "employment", "lexical_anchor_span": proposal.owned_text,
        "detection_rule_id": "rule", "detection_manifest_fingerprint": route.resource_binding.predicate_event_manifest_digest,
    }
    event = PredicateEventCandidate.create(
        **event_identity,
        event_id=contract_digest(b"memorii.semantic-ingestion.predicate-event-identity.v1", event_identity),
        morphology_evidence_spans=(),
    )
    event_outcome = SegmentLanguageLaneOutcome.create(
        lane="predicate_event_detection", segment_id=proposal.segment_id, preparation_fingerprint=proposal.preparation_fingerprint,
        segment_language_route_digest=route.route_digest,
        resource_binding_digest=route.resource_binding.resource_binding_digest,
        selected_manifest_digest=route.resource_binding.predicate_event_manifest_digest,
        status="complete", artifact_digest="e" * 64, reason_codes=(),
    )
    inventory = PredicateEventInventory.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_routes=route_set,
        segment_outcomes=(event_outcome,), candidates=(event,), status="complete",
    )
    temporal_identity = {
        "segment_id": proposal.segment_id, "preparation_fingerprint": proposal.preparation_fingerprint, "segment_language_route_digest": route.route_digest,
            "source_span": proposal.owned_text, "value_kind": "instant",
        "normalized_interval": TimeInterval(start=datetime(2026, 1, 1, tzinfo=UTC)),
        "normalized_duration": None, "grain": "day", "locale": "en", "timezone": "UTC",
        "reference_evidence": None, "resolver_rule_id": "absolute",
    }
    temporal = ResolvedTemporalCandidate.create(
        **temporal_identity,
        candidate_id=contract_digest(b"memorii.semantic-ingestion.resolved-temporal-candidate-identity.v1", temporal_identity),
        exact_text="2026-01-01",
    )
    temporal_outcome = SegmentLanguageLaneOutcome.create(
        lane="temporal_resolution", segment_id=proposal.segment_id, preparation_fingerprint=proposal.preparation_fingerprint,
        segment_language_route_digest=route.route_digest,
        resource_binding_digest=route.resource_binding.resource_binding_digest,
        selected_manifest_digest=route.resource_binding.temporal_resolver_manifest_digest,
        status="complete", artifact_digest="f" * 64, reason_codes=(),
    )
    resolution = TemporalResolution.create(
        source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint=proposal.preparation_fingerprint, segment_language_routes=route_set,
        segment_outcomes=(temporal_outcome,), candidates=(temporal,), ambiguous_spans=(), status="complete", diagnostics=(),
    )
    values = (
        feature, primary.tokens[0], primary.dependencies[0], primary.mentions[0], primary.clauses[0].arguments[0],
        quotation, primary.clauses[0], stanza, primary, segment_bundle, analysis_bundle, event, inventory,
        temporal, resolution, segment, stanza_manifest, predicate_manifest, resolver,
        LinguisticAnalysisRequest.create(segment=segment, analyzer_manifest=stanza_manifest),
        PredicateEventDetectionRequest.create(segment=segment, predicate_event_manifest=predicate_manifest),
        TemporalResolutionRequest.create(segment=segment, resolver_manifest=resolver, reference_evidence=None),
    )
    for value in values:
        encoded = encode_semantic_contract(value)
        envelope = decode_typed_value(encoded)
        assert isinstance(envelope, dict)
        assert decode_semantic_contract(encoded, type(value)) == value
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        required_field = next(
            name for name, field in type(value).model_fields.items() if field.is_required()
        )
        digest_field = next(
            name
            for name in type(value).model_fields
            if name.endswith(("_digest", "_fingerprint", "_id"))
        )
        malformed = (
            {key: value for key, value in envelope.items() if key != "payload"},
            {**envelope, "unexpected": True},
            {**envelope, "kind": f"alias_{envelope['kind']}"},
            {**envelope, "schema": "foreign.domain.v1"},
            {**envelope, "kind": "future_contract"},
            {**envelope, "payload": "scalar"},
            {**envelope, "payload": {**payload, "unexpected": True}},
            {**envelope, "payload": {**payload, digest_field: "0" * 64}},
            {**envelope, "payload": {key: item for key, item in payload.items() if key != required_field}},
            {
                **envelope,
                "payload": {
                    **{key: item for key, item in payload.items() if key != required_field},
                    f"alias_{required_field}": payload[required_field],
                },
            },
        )
        for candidate in malformed:
            with pytest.raises(SemanticContractCodecError):
                decode_semantic_contract(encode_typed_value(candidate), type(value))
        if "preparation_fingerprint" in payload:
            with pytest.raises(SemanticContractCodecError):
                decode_semantic_contract(
                    encode_typed_value({**envelope, "payload": {key: item for key, item in payload.items() if key != "preparation_fingerprint"}}),
                    type(value),
                )
    for aggregate, digest_field in (
        (segment_bundle, "bundle_fingerprint"),
        (analysis_bundle, "bundle_fingerprint"),
        (inventory, "inventory_fingerprint"),
        (resolution, "resolver_fingerprint"),
    ):
        with pytest.raises(ValueError, match="preparation fingerprint"):
            type(aggregate).create(
                **(aggregate.model_dump(mode="python", exclude={digest_field}) | {"preparation_fingerprint": "2" * 64})
            )
