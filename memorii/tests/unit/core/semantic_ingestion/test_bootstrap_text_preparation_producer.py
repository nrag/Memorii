"""Focused proof for the verified-profile owned V1 prepared-source producer."""

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapAuthenticatedLanguageEvidence,
    BootstrapGrammarCorpusCase,
    BootstrapProfileReleaseMetadata,
    VerifiedBootstrapProfile,
    build_bootstrap_profile_artifacts,
)
from tests.fixtures.semantic_ingestion.host_bootstrap_authority import (
    build_test_host_verified_bootstrap_release_evidence,
)
from memorii.core.memory_evolution.models import SourceObservation, SourceType
from memorii.core.semantic_ingestion.contracts import (
    SourceAuthority,
    SourceAuthorityEvidence,
    TextPreparationPolicy,
    TextPreparationRequest,
)
from memorii.core.semantic_ingestion.local_analyzer import ProductionLocalSemanticAnalyzer
from memorii.core.semantic_ingestion.pipeline import SemanticIngestionPipeline
from memorii.core.semantic_ingestion.source_preparation import (
    BootstrapTextPreparationProducer,
    InMemoryPreparedSourceRepository,
    TextPreparationService,
)
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
    build_prepared_source_authority,
)


def _case(case_id: str, content: bytes, disposition: str, reason: str | None, *, language: str | None = "en", kind: str = "authenticated_host_declaration", trust: str = "trusted", agreement: str = "agrees") -> BootstrapGrammarCorpusCase:
    return BootstrapGrammarCorpusCase.model_validate({
        "case_id": case_id, "declared_language": language,
        "language_evidence_kind": kind, "language_evidence_trust": trust,
        "governance_agreement": agreement, "normalized_segment_bytes": content,
        "disposition": disposition, "expected_reason": reason,
    })


def _profile(*supported: bytes) -> VerifiedBootstrapProfile:
    cases = (
        *(_case(f"supported-{index:02d}", value, "supported_form", None) for index, value in enumerate(supported)),
        _case("unsupported-mixed", b"mixed", "unsupported_form", "mixed_residue"),
        _case("unsupported-grammar", b"unstructured", "unsupported_form", "unsupported_grammar"),
        _case("abstain-empty", b"", "abstain_form", "extractor_abstained"),
        _case("abstain-mismatch", b"mismatch", "abstain_form", "language_mismatch", kind="mismatched", trust="mismatched", agreement="disagrees"),
        _case("abstain-missing", b"missing", "abstain_form", "missing_language_declaration", language=None, kind="missing", trust="missing", agreement="missing"),
        _case("abstain-non-english", b"bonjour", "abstain_form", "non_english_language", language="fr"),
        _case("abstain-untrusted", b"untrusted", "abstain_form", "untrusted_language", language=None, kind="untrusted", trust="untrusted", agreement="missing"),
    )
    artifacts = build_bootstrap_profile_artifacts(tuple(sorted(cases, key=lambda item: item.case_id)))
    evidence = build_test_host_verified_bootstrap_release_evidence(
        metadata=BootstrapProfileReleaseMetadata(
            coordinate=BOOTSTRAP_COORDINATE,
            signed_release_digest="1" * 64,
            bootstrap_profile_trust_anchor_digest="2" * 64,
        ),
        external_root_digest="3" * 64,
        active_lifecycle_snapshot_digest="4" * 64,
        verified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return VerifiedBootstrapProfile(
        coordinate=BOOTSTRAP_COORDINATE, enabled=True, artifacts=artifacts,
        release_evidence=evidence, selection_digest="5" * 64, verification_digest="6" * 64,
    )


def _request(text: str, profile: VerifiedBootstrapProfile) -> TextPreparationRequest:
    source_id = "bootstrap-source"
    source_digest = sha256(("source:" + text).encode()).hexdigest()
    base = build_prepared_source_authority(source_id=source_id, source_digest=source_digest, source_text=text)
    carriers = base.segment_governance_carriers
    admissions = base.message_admission_carriers
    artifact = base.governance_carrier_artifact
    evidence = BootstrapAuthenticatedLanguageEvidence.create(
        source_id=source_id, source_digest=source_digest,
        original_text_digest=sha256(text.encode()).hexdigest(),
        delivery_principal_binding_digest=admissions.identities[0].delivery_principal_binding_digest,
        segment_governance_set_digest=carriers.carrier_set_digest,
        governance_carrier_artifact_digest=artifact.artifact_digest,
        segment_governance_carriers_digest=carriers.carrier_set_digest,
        message_admission_carriers_digest=admissions.carrier_set_digest,
        language_declaration="en", language_evidence_kind="authenticated_host_declaration",
        language_evidence_trust="trusted", language_governance_agreement="agrees",
    )
    observation = SourceObservation(
        source_id=source_id, source_digest=source_digest, delivery_key_digest="7" * 64,
        text=text, source_type=SourceType.USER, timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        bootstrap_language_evidence=evidence, retained_text_artifact=base.semantic_text_projection.retained_text_artifact,
        required_outcome_scopes=base.semantic_text_projection.required_outcome_scopes,
        semantic_context=base.semantic_context, semantic_text_projection=base.semantic_text_projection,
        segment_governance_carriers=carriers, message_admission_carriers=admissions,
        governance_carrier_artifact=artifact, admission_scope_authorization_proof=object(),
    )
    return TextPreparationRequest(observation=observation, policy=profile.artifacts.profile_manifest.preparation_policy)


def test_verified_producer_builds_repeatable_multi_child_route_proofs_and_spans() -> None:
    text = "Atlas owner is Bob. Atlas owner is Bob."
    profile = _profile(b"Atlas owner is Bob.")
    request = _request(text, profile)
    service = TextPreparationService.for_verified_bootstrap_profile(
        profile=profile, repository=InMemoryPreparedSourceRepository(),
    )

    prepared = service.prepare_and_publish(request)
    assert prepared.status == "complete"
    assert len(prepared.segments) == 2
    assert len(set(segment.segment_id for segment in prepared.segments)) == 2
    assert tuple(proof.segment_id for proof in prepared.grammar_proofs) == tuple(segment.segment_id for segment in prepared.segments)
    assert all(route.decision == "selected" for route in prepared.segment_language_routes.routes)
    assert [route.normalized_segment_digest for route in prepared.segment_language_routes.routes] == [
        proof.normalized_segment_digest for proof in prepared.grammar_proofs
    ]
    assert [prepared.semantic_text[span.projection_span.start:span.projection_span.end] for span in prepared.sentence_spans] == ["Atlas owner is Bob.", " Atlas owner is Bob."]
    assert [proof.normalized_segment_digest for proof in prepared.grammar_proofs] == [
        sha256(b"Atlas owner is Bob.").hexdigest(),
        sha256(b"Atlas owner is Bob.").hexdigest(),
    ]
    assert prepared.token_spans
    assert service.prepare_and_publish(request) == prepared


def test_local_analyzer_exposes_only_the_closed_scenario_predicates() -> None:
    analyzer = ProductionLocalSemanticAnalyzer()

    owners = analyzer.propose(
        source_id="scenario-source",
        source_digest="a" * 64,
        source_text="Atlas owner is Alice. Atlas owner is Bob.",
    )
    assert [candidate.predicate_id for candidate in owners] == ["owner", "owner"]
    assert [candidate.assertion_quote for candidate in owners] == [
        "Atlas owner is Alice.",
        "Atlas owner is Bob.",
    ]
    status = analyzer.propose(
        source_id="scenario-source",
        source_digest="b" * 64,
        source_text="Orion status is running.",
    )
    assert len(status) == 1
    assert status[0].predicate_id == "status"
    assert analyzer.propose(
        source_id="scenario-source",
        source_digest="c" * 64,
        source_text="No source-grounded assertion is available.",
    ) == ()


def test_local_analyzer_binds_assertion_span_to_matched_quote_within_second_segment() -> None:
    text = "Atlas owner is Alice. Atlas owner is Bob."
    profile = _profile(b"Atlas owner is Alice.", b"Atlas owner is Bob.")
    request = _request(text, profile)
    prepared = TextPreparationService.for_verified_bootstrap_profile(
        profile=profile,
        repository=InMemoryPreparedSourceRepository(),
    ).prepare_and_publish(request)
    analyzer = ProductionLocalSemanticAnalyzer()
    proposals = analyzer.propose(
        source_id=prepared.source_id,
        source_digest=prepared.source_digest,
        source_text=text,
    )

    analysis = analyzer.analyze(
        proposal=proposals[1],
        source_id=prepared.source_id,
        source_digest=prepared.source_digest,
        source_text=text,
        prepared_source=prepared,
        source_authority_evidence=SourceAuthorityEvidence.create(
            source_id=prepared.source_id,
            source_digest=prepared.source_digest,
            authority=SourceAuthority(
                authority_class="official",
                authenticated_provenance_class="host",
                policy_revision="trust-r1",
            ),
            provenance_digest=sha256(b"bootstrap-local-analyzer-authority").hexdigest(),
        ),
        source_interval_evidence=None,
    )

    assert analysis is not None
    assert text[analysis.assertion_span.start : analysis.assertion_span.end] == proposals[1].assertion_quote


def test_protected_owner_pair_uses_source_order_not_candidate_id_order() -> None:
    def authority_for(*, source_id: str, source_digest: str) -> SourceAuthorityEvidence:
        return SourceAuthorityEvidence.create(
            source_id=source_id,
            source_digest=source_digest,
            authority=SourceAuthority(
                authority_class="official",
                authenticated_provenance_class="host",
                policy_revision="trust-r1",
            ),
            provenance_digest=sha256(f"{source_id}:{source_digest}:authority".encode("utf-8")).hexdigest(),
        )

    def analyses_for(text: str) -> tuple:
        profile = _profile(b"Atlas owner is Alice.", b"Atlas owner is Bob.")
        prepared = TextPreparationService.for_verified_bootstrap_profile(
            profile=profile,
            repository=InMemoryPreparedSourceRepository(),
        ).prepare_and_publish(_request(text, profile))
        analyzer = ProductionLocalSemanticAnalyzer()
        proposals = analyzer.propose(
            source_id=prepared.source_id,
            source_digest=prepared.source_digest,
            source_text=text,
        )
        authority = authority_for(
            source_id=prepared.source_id,
            source_digest=prepared.source_digest,
        )
        analyses = tuple(
            analyzer.analyze(
                proposal=proposal,
                source_id=prepared.source_id,
                source_digest=prepared.source_digest,
                source_text=text,
                prepared_source=prepared,
                source_authority_evidence=authority,
                source_interval_evidence=None,
            )
            for proposal in proposals
        )
        assert all(analysis is not None for analysis in analyses)
        return proposals, tuple(analyses)

    forward_candidates, forward_analyses = analyses_for(
        "Atlas owner is Alice. Atlas owner is Bob."
    )
    assert SemanticIngestionPipeline._is_protected_scenario_owner_pair(
        tuple(reversed(forward_candidates)),
        tuple(reversed(forward_analyses)),
    )

    swapped_candidates = tuple(reversed(forward_candidates))
    swapped_analyses = (
        forward_analyses[1].model_copy(
            update={"assertion_span": forward_analyses[0].assertion_span}
        ),
        forward_analyses[0].model_copy(
            update={"assertion_span": forward_analyses[1].assertion_span}
        ),
    )
    assert not SemanticIngestionPipeline._is_protected_scenario_owner_pair(
        swapped_candidates,
        swapped_analyses,
    )


@pytest.mark.parametrize("mutation", ("substitution", "policy", "corpus"))
def test_verified_producer_rejects_substituted_policy_or_nonmatching_corpus(mutation: str) -> None:
    text = "Atlas owner is Bob."
    profile = _profile(text.encode())
    request = _request(text, profile)
    producer = BootstrapTextPreparationProducer(profile=profile)
    if mutation == "substitution":
        request = request.model_copy(update={"observation": request.observation.model_copy(update={"text": "substituted"})})
    elif mutation == "policy":
        policy = TextPreparationPolicy.create(
            max_segment_characters=4095, supported_languages=("en",),
            segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1",
            context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1",
        )
        request = request.model_copy(update={"policy": policy})
    else:
        producer = BootstrapTextPreparationProducer(profile=_profile(b"Receipt is confirmed."))
    with pytest.raises(ValueError, match="substituted|policy|nonpromoting"):
        producer(request)
