from hashlib import sha256

import pytest
from memorii.core.memory_evolution.bootstrap_profile import BootstrapSegmentGrammarProof
from memorii.core.semantic_ingestion.contracts import (
    AnalyzerManifest,
    BootstrapAnalysisProvenanceV1,
    BootstrapAnalysisRouteBinding,
    BootstrapAnalysisRouteBindingSet,
    BootstrapAnalysisRouteProjection,
    BootstrapDeclaredSegmentLanguageRoute,
    BootstrapLinguisticAnalysisRequestV3,
    BootstrapSegmentAnalysisInputV3,
    PreparedSegment,
    PreparedSource,
    SegmentLanguageRouteSet,
    SourceSpanReference,
    contract_digest,
)
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import build_prepared_source_authority


def _hex(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _bootstrap_prepared() -> PreparedSource:
    prepared = build_prepared_source_authority(
        source_id="source:bootstrap", source_digest=_hex("source"), source_text="Atlas owner is Bob."
    )
    old = prepared.segment_language_routes.routes[0]
    proof = BootstrapSegmentGrammarProof.create(
        source_id=prepared.source_id,
        segment_id=old.segment_id,
        language_evidence_tuple=("en", "authenticated_host_declaration", "trusted", "agrees"),
        bootstrap_language_evidence_digest=_hex("language-evidence"),
        normalized_segment_digest=old.segment_text_content_digest,
        corpus_case_id="supported-atlas",
    )
    route = BootstrapDeclaredSegmentLanguageRoute.create(
        schema_id="memorii.semantic_ingestion.bootstrap_declared_segment_language_route",
        schema_version=1,
        source_id=prepared.source_id,
        source_digest=prepared.source_digest,
        segment_id=old.segment_id,
        parent_projection_segment_id=old.parent_projection_segment_id,
        segment_text_artifact_id=old.segment_text_artifact_id,
        segment_text_artifact_digest=old.segment_text_artifact_digest,
        segment_text_content_digest=old.segment_text_content_digest,
        declared_language="en",
        language_evidence_kind="authenticated_host_declaration",
        language_evidence_trust="trusted",
        governance_agreement="agrees",
        bootstrap_language_evidence_digest=proof.bootstrap_language_evidence_digest,
        bootstrap_profile_manifest_digest=_hex("profile"),
        preparation_policy_fingerprint=prepared.preparation_policy.policy_fingerprint,
        component_root_digest=_hex("components"),
        corpus_case_id=proof.corpus_case_id,
        normalized_segment_digest=proof.normalized_segment_digest,
        grammar_proof_digest=proof.proof_digest,
        decision="selected",
    )
    segment = prepared.segments[0].model_copy(update={"language_route": route})
    body = {
        name: getattr(prepared, name)
        for name in PreparedSource.model_fields
        if name != "preparation_fingerprint"
    }
    body.update(
        segments=(PreparedSegment.model_validate(segment.model_dump(mode="python")),),
        segment_language_routes=SegmentLanguageRouteSet.create(
            source_id=prepared.source_id, source_digest=prepared.source_digest, routes=(route,)
        ),
        grammar_proofs=(proof,),
    )
    return PreparedSource(
        **body,
        preparation_fingerprint=contract_digest(
            b"memorii.semantic-ingestion.prepared-source.v1", body
        ),
    )


def test_bootstrap_route_and_proof_are_an_exact_ordered_prepared_source_bijection() -> None:
    prepared = _bootstrap_prepared()
    assert prepared.grammar_proofs[0].proof_digest == prepared.segment_language_routes.routes[0].grammar_proof_digest


def test_bootstrap_analysis_projection_requires_the_declared_route_and_host_binding() -> None:
    prepared = _bootstrap_prepared()
    route = prepared.segment_language_routes.routes[0]
    resource_values = {
        "selected_language": "en",
        "proposal_capability_fingerprint": _hex("proposal"),
        "stanza_analyzer_manifest_digest": _hex("stanza"),
        "spacy_analyzer_manifest_digest": _hex("spacy"),
        "predicate_event_manifest_digest": _hex("predicate"),
        "temporal_resolver_manifest_digest": _hex("temporal"),
    }
    from memorii.core.semantic_ingestion.contracts import SegmentLanguageResourceBinding

    resource = SegmentLanguageResourceBinding.create(**resource_values)
    body = {
        "source_id": prepared.source_id,
        "source_digest": prepared.source_digest,
        "preparation_fingerprint": prepared.preparation_fingerprint,
        "segment_id": route.segment_id,
        "parent_projection_segment_id": route.parent_projection_segment_id,
        "bootstrap_route_digest": route.route_digest,
        "segment_text_artifact_id": route.segment_text_artifact_id,
        "segment_text_artifact_digest": route.segment_text_artifact_digest,
        "segment_text_content_digest": route.segment_text_content_digest,
        "selected_language": "en",
        "resource_binding": resource,
        "proposal_capability_fingerprint": resource.proposal_capability_fingerprint,
        "stanza_analyzer_manifest_digest": resource.stanza_analyzer_manifest_digest,
        "spacy_analyzer_manifest_digest": resource.spacy_analyzer_manifest_digest,
        "predicate_event_manifest_digest": resource.predicate_event_manifest_digest,
        "temporal_resolver_manifest_digest": resource.temporal_resolver_manifest_digest,
    }
    binding = BootstrapAnalysisRouteBinding(
        **body,
        binding_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-analysis-route-binding.v1", body
        ),
    )
    binding_set_body = {
        "source_id": prepared.source_id,
        "source_digest": prepared.source_digest,
        "preparation_fingerprint": prepared.preparation_fingerprint,
        "bindings": (binding,),
    }
    binding_set = BootstrapAnalysisRouteBindingSet(
        **binding_set_body,
        binding_set_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-analysis-route-binding-set.v1", binding_set_body
        ),
    )
    assert binding_set.bindings == (binding,)
    provenance = BootstrapAnalysisProvenanceV1.from_binding(binding)
    projection = BootstrapAnalysisRouteProjection.create(
        bootstrap_route=route, binding=binding, bootstrap_analysis_provenance=provenance
    )
    assert projection.bootstrap_analysis_provenance == provenance
    with pytest.raises(ValueError, match="(projection authority|binding resource authority)"):
        BootstrapAnalysisRouteProjection.create(
            bootstrap_route=route,
            binding=binding.model_copy(update={"selected_language": "fr"}),
            bootstrap_analysis_provenance=provenance,
        )


def test_bootstrap_v3_lane_requests_reject_a_swapped_host_manifest() -> None:
    prepared = _bootstrap_prepared()
    route = prepared.segment_language_routes.routes[0]
    resource = __import__(
        "memorii.core.semantic_ingestion.contracts", fromlist=["SegmentLanguageResourceBinding"]
    ).SegmentLanguageResourceBinding.create(
        selected_language="en", proposal_capability_fingerprint=_hex("proposal"),
        stanza_analyzer_manifest_digest=_hex("stanza"), spacy_analyzer_manifest_digest=_hex("spacy"),
        predicate_event_manifest_digest=_hex("predicate"), temporal_resolver_manifest_digest=_hex("temporal"),
    )
    binding_body = {
        "source_id": prepared.source_id, "source_digest": prepared.source_digest,
        "preparation_fingerprint": prepared.preparation_fingerprint,
        "segment_id": route.segment_id, "parent_projection_segment_id": route.parent_projection_segment_id,
        "bootstrap_route_digest": route.route_digest,
        "segment_text_artifact_id": route.segment_text_artifact_id,
        "segment_text_artifact_digest": route.segment_text_artifact_digest,
        "segment_text_content_digest": route.segment_text_content_digest,
        "selected_language": "en", "resource_binding": resource,
        "proposal_capability_fingerprint": resource.proposal_capability_fingerprint,
        "stanza_analyzer_manifest_digest": resource.stanza_analyzer_manifest_digest,
        "spacy_analyzer_manifest_digest": resource.spacy_analyzer_manifest_digest,
        "predicate_event_manifest_digest": resource.predicate_event_manifest_digest,
        "temporal_resolver_manifest_digest": resource.temporal_resolver_manifest_digest,
    }
    binding = BootstrapAnalysisRouteBinding(
        **binding_body,
        binding_digest=contract_digest(b"memorii.semantic-ingestion.bootstrap-analysis-route-binding.v1", binding_body),
    )
    provenance = BootstrapAnalysisProvenanceV1.from_binding(binding)
    projection = BootstrapAnalysisRouteProjection.create(
        bootstrap_route=route, binding=binding, bootstrap_analysis_provenance=provenance
    )
    segment = prepared.segments[0]
    context = SourceSpanReference.create(
        source_id=prepared.source_id,
        projection_digest=segment.context_projection_span.artifact.artifact_digest,
        projection_segment_id=segment.parent_projection_segment_id,
        retained_text_artifact=prepared.semantic_text_projection.retained_text_artifact,
        projection_span=segment.context_projection_span,
        segment_local_span=segment.context_segment_span,
        text_mapping_proof=segment.text_mapping_proof,
        source_reference=None,
    )
    input_value = BootstrapSegmentAnalysisInputV3.create(
        schema_version=3, source_id=prepared.source_id, source_digest=prepared.source_digest,
        preparation_fingerprint=prepared.preparation_fingerprint, segment_id=segment.segment_id,
        parent_projection_segment_id=segment.parent_projection_segment_id,
        segment_governance=segment.segment_governance,
        message_admission_identity=segment.message_admission_identity,
        governance_carrier_artifact=prepared.governance_carrier_artifact,
        context_text=context, segment_text=prepared.semantic_text, bootstrap_projection=projection,
        bootstrap_analysis_provenance=provenance,
    )
    stanza = AnalyzerManifest.create(
        analyzer_id="stanza", analyzer_kind="stanza", library_version="1",
        resource_manifest_digest=_hex("resource"), model_file_hashes=(_hex("model"),),
        processor_configuration_digest=_hex("processors"), adapter_version="1", supported_languages=("en",),
        analyzer_fingerprint=_hex("fingerprint"),
    ).model_copy(update={"manifest_digest": provenance.stanza_analyzer_manifest_digest})
    # The strict constructor refuses a digest-only substituted manifest before
    # a lane can execute.
    with pytest.raises(ValueError, match="manifest_digest mismatch"):
        BootstrapLinguisticAnalysisRequestV3.create(
            schema_version=3, segment=input_value, analyzer_manifest=stanza,
            bootstrap_analysis_provenance=provenance,
        )


@pytest.mark.parametrize("field", ("segment_id", "normalized_segment_digest", "proof_digest"))
def test_bootstrap_route_proof_mutations_reject_prepared_source(field: str) -> None:
    prepared = _bootstrap_prepared()
    proof = prepared.grammar_proofs[0]
    changed = "other-segment" if field == "segment_id" else _hex("mutated-" + field)
    mutated = proof.model_copy(update={field: changed})
    body = {
        name: getattr(prepared, name)
        for name in PreparedSource.model_fields
        if name != "preparation_fingerprint"
    }
    body["grammar_proofs"] = (mutated,)
    with pytest.raises(ValueError, match="(grammar proof|grammar proofs)"):
        PreparedSource(
            **body,
            preparation_fingerprint=contract_digest(
                b"memorii.semantic-ingestion.prepared-source.v1", body
            ),
        )
