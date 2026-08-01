from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution import (
    ClaimAssertionMode,
    ClaimEpistemicStatus,
    ClaimKey,
    ClaimLifecycleState,
    ClaimModality,
    ClaimPolarity,
    ClaimSemanticContext,
    ClaimState,
    ConfidenceComponents,
    EnglishRuleMemoryExtractor,
    EntityMention,
    EntityResolutionService,
    EntityType,
    EvidenceSpan,
    ExtractedClaim,
    ExtractionRun,
    MemoryEvolutionMutationValidationError,
    MemoryEvolutionService,
    MemoryEvolutionValidator,
    MemoryExtractionProposal,
    RetrievalView,
    SourceObservation,
)
from memorii.core.memory_evolution.extraction import models_from_llm_output
from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionOutput, MemoryExtractionRunError
from memorii.core.memory_evolution.record_projection import record_from_claim_state
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain, SourceType, TemporalValidityStatus
from pydantic import ValidationError


def _observation() -> SourceObservation:
    return SourceObservation(
        source_id="tx:semantic-context",
        text="Alice believes Atlas owner is Bob.",
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
        speaker_id="operator",
    )


def _world_claim_for_evidence(
    *,
    observation: SourceObservation,
    evidence_spans: list[EvidenceSpan],
) -> ExtractedClaim:
    context = ClaimSemanticContext(
        assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
        epistemic_status=ClaimEpistemicStatus.ASSERTED,
        polarity=ClaimPolarity.POSITIVE,
        modality=ClaimModality.ASSERTION,
        attribution_source_id=observation.source_id,
    )
    return ExtractedClaim(
        claim_id="claim:evidence-form",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            assertion_mode=context.assertion_mode,
            epistemic_status=context.epistemic_status,
            polarity=context.polarity,
            modality=context.modality,
        ),
        object_value="Bob",
        semantic_context=context,
        evidence_spans=evidence_spans,
        confidence=ConfidenceComponents(extraction=0.9, evidence=0.9, source_trust=0.9, calibrated=0.9),
        extraction_run_id="run:evidence-form",
    )


def test_rule_claim_is_explicit_world_assertion_and_partitions_identity() -> None:
    observation = SourceObservation(
        source_id="tx:world",
        text="Atlas owner is Alice.",
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
        speaker_id="operator",
    )

    claim = EnglishRuleMemoryExtractor().extract([observation]).claims[0]

    assert claim.semantic_context == ClaimSemanticContext(
        assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
        epistemic_status=ClaimEpistemicStatus.ASSERTED,
        polarity=ClaimPolarity.POSITIVE,
        modality=ClaimModality.ASSERTION,
        attribution_source_id="tx:world",
        attribution_speaker_id="operator",
    )
    assert claim.claim_key.assertion_mode == ClaimAssertionMode.WORLD_ASSERTION
    assert "world_assertion" in claim.claim_key.stable_id()


def test_attributed_belief_is_source_grounded_but_not_promotion_eligible() -> None:
    observation = _observation()
    entities = [
        EntityMention(
            entity_id="ent:atlas",
            mention_text="Atlas",
            normalized_name="atlas",
            entity_type=EntityType.PROJECT,
            evidence_spans=[EvidenceSpan(source_id=observation.source_id, quote="Atlas", source_type=SourceType.USER, timestamp=observation.timestamp)],
            confidence=0.9,
        ),
        EntityMention(
            entity_id="ent:alice",
            mention_text="Alice",
            normalized_name="alice",
            entity_type=EntityType.PERSON,
            evidence_spans=[EvidenceSpan(source_id=observation.source_id, quote="Alice", source_type=SourceType.USER, timestamp=observation.timestamp)],
            confidence=0.9,
        ),
    ]
    context = ClaimSemanticContext(
        assertion_mode=ClaimAssertionMode.ATTRIBUTED_BELIEF,
        epistemic_status=ClaimEpistemicStatus.BELIEVED,
        polarity=ClaimPolarity.POSITIVE,
        modality=ClaimModality.ASSERTION,
        attribution_source_id=observation.source_id,
        attribution_speaker_id="operator",
        belief_holder_entity_id="ent:alice",
    )
    claim = ExtractedClaim(
        claim_id="claim:belief",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            assertion_mode=context.assertion_mode,
            epistemic_status=context.epistemic_status,
            polarity=context.polarity,
            modality=context.modality,
            belief_holder_entity_id=context.belief_holder_entity_id,
        ),
        object_value="Bob",
        semantic_context=context,
        evidence_spans=[EvidenceSpan(source_id=observation.source_id, quote=observation.text, source_type=SourceType.USER, timestamp=observation.timestamp)],
        confidence=ConfidenceComponents(extraction=0.8, evidence=0.8, source_trust=0.8, calibrated=0.8),
        extraction_run_id="run:belief",
    )
    proposal = MemoryExtractionProposal(
        run=ExtractionRun(
            extraction_run_id="run:belief",
            provider="test",
            input_source_ids=[observation.source_id],
            entity_ids=[entity.entity_id for entity in entities],
            claim_ids=[claim.claim_id],
        ),
        entities=entities,
        claims=[claim],
    )

    results = MemoryEvolutionValidator().validate_claim(
        claim=proposal.claims[0], observation_by_id={observation.source_id: observation}
    )

    assert any(result.rationale.startswith("attributed belief is evidence-only") for result in results)
    assert not MemoryEvolutionValidator().accepted(results)
    assert claim.claim_key.stable_id().endswith("attributed_belief|believed|positive|assertion|ent:alice")

    mismatched_speaker = claim.model_copy(
        update={"semantic_context": context.model_copy(update={"attribution_speaker_id": "forged"})}
    )
    speaker_results = MemoryEvolutionValidator().validate_claim(
        claim=mismatched_speaker,
        observation_by_id={observation.source_id: observation},
    )
    assert any("speaker does not match" in result.rationale for result in speaker_results)


def test_transport_defers_cross_field_semantics_and_legacy_stays_unclassified() -> None:
    base = {
        "subject_entity_ref": "atlas",
        "predicate_id": "owner",
        "object_value": "Alice",
        "object_entity_ref": None,
        "source_id": "tx:one",
        "quote": "Atlas owner is Alice",
        "confidence": 0.9,
    }
    legacy = MemoryExtractionOutput.model_validate(
        {"entities": [], "claims": [base], "actions": [], "identity_relations": []}
    )
    assert legacy.claims[0].semantic_context.assertion_mode == ClaimAssertionMode.LEGACY_UNCLASSIFIED

    bad = {
        **base,
        "semantic_context": {
            "assertion_mode": "world_assertion",
            "epistemic_status": "asserted",
            "polarity": "positive",
            "modality": "assertion",
            "attribution_source_id": "tx:other",
            "attribution_speaker_id": None,
            "reported_source_id": None,
            "belief_holder_entity_ref": None,
        },
    }
    transported = MemoryExtractionOutput.model_validate(
        {"entities": [], "claims": [bad], "actions": [], "identity_relations": []}
    )
    assert transported.claims[0].semantic_context.attribution_source_id == "tx:other"


def test_malformed_claim_semantics_isolated_to_partial_proposal_with_valid_sibling() -> None:
    observation = SourceObservation(
        source_id="tx:partial-semantics",
        text="Atlas owner is Bob.",
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
    )
    base_claim = {
        "subject_entity_ref": "atlas",
        "predicate_id": "owner",
        "object_value": "Bob",
        "object_entity_ref": "bob",
        "source_id": observation.source_id,
        "quote": observation.text,
        "confidence": 0.9,
    }
    valid_context = {
        "assertion_mode": "world_assertion",
        "epistemic_status": "asserted",
        "polarity": "positive",
        "modality": "assertion",
        "attribution_source_id": observation.source_id,
        "attribution_speaker_id": None,
        "reported_source_id": None,
        "belief_holder_entity_ref": None,
    }
    proposal = models_from_llm_output(
        run_id="run:partial-semantics",
        provider="test",
        model=None,
        prompt_hash=None,
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "entity_type": "project",
                    "source_id": observation.source_id,
                    "quote": "Atlas",
                    "confidence": 0.9,
                },
                {
                    "entity_ref": "bob",
                    "mention_text": "Bob",
                    "entity_type": "person",
                    "source_id": observation.source_id,
                    "quote": "Bob",
                    "confidence": 0.9,
                },
            ],
            "claims": [
                {**base_claim, "semantic_context": valid_context},
                {
                    **base_claim,
                    "semantic_context": {**valid_context, "attribution_source_id": "tx:other"},
                },
            ],
            "actions": [],
            "identity_relations": [],
        },
    )

    assert proposal.run.status.value == "partial"
    assert proposal.run.failure_code is not None
    assert proposal.run.validation_summary["claim_binding_errors"] == 1
    assert len(proposal.claims) == 1
    assert proposal.claims[0].semantic_context.attribution_source_id == observation.source_id
    assert any(error.startswith("claim[1]: ValueError:claim attribution source") for error in proposal.run.errors)


def test_llm_claim_identity_partitions_world_belief_and_polarity() -> None:
    observation = _observation()
    proposal = models_from_llm_output(
        run_id="run:semantic-identity",
        provider="test",
        model=None,
        prompt_hash=None,
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "entity_type": "project",
                    "source_id": observation.source_id,
                    "quote": "Atlas",
                    "confidence": 0.9,
                },
                {
                    "entity_ref": "alice",
                    "mention_text": "Alice",
                    "entity_type": "person",
                    "source_id": observation.source_id,
                    "quote": "Alice",
                    "confidence": 0.9,
                },
                {
                    "entity_ref": "bob",
                    "mention_text": "Bob",
                    "entity_type": "person",
                    "source_id": observation.source_id,
                    "quote": "Bob",
                    "confidence": 0.9,
                },
            ],
            "claims": [
                {
                    "subject_entity_ref": "atlas",
                    "predicate_id": "owner",
                    "object_value": "Bob",
                    "object_entity_ref": "bob",
                    "source_id": observation.source_id,
                    "quote": observation.text,
                    "confidence": 0.9,
                    "semantic_context": context,
                }
                for context in [
                    {
                        "assertion_mode": "world_assertion",
                        "epistemic_status": "asserted",
                        "polarity": "positive",
                        "modality": "assertion",
                        "attribution_source_id": observation.source_id,
                        "attribution_speaker_id": "operator",
                        "reported_source_id": None,
                        "belief_holder_entity_ref": None,
                    },
                    {
                        "assertion_mode": "world_assertion",
                        "epistemic_status": "asserted",
                        "polarity": "negative",
                        "modality": "assertion",
                        "attribution_source_id": observation.source_id,
                        "attribution_speaker_id": "operator",
                        "reported_source_id": None,
                        "belief_holder_entity_ref": None,
                    },
                    {
                        "assertion_mode": "attributed_belief",
                        "epistemic_status": "believed",
                        "polarity": "positive",
                        "modality": "possible",
                        "attribution_source_id": observation.source_id,
                        "attribution_speaker_id": "operator",
                        "reported_source_id": None,
                        "belief_holder_entity_ref": "alice",
                    },
                ]
            ],
            "actions": [],
            "identity_relations": [],
        },
    )

    assert proposal.run.status.value == "succeeded"
    assert len({claim.claim_id for claim in proposal.claims}) == 3
    assert len({claim.claim_key.stable_id() for claim in proposal.claims}) == 3
    assert {claim.semantic_context.polarity for claim in proposal.claims} == {
        ClaimPolarity.POSITIVE,
        ClaimPolarity.NEGATIVE,
    }
    assert any(claim.semantic_context.modality == ClaimModality.POSSIBLE for claim in proposal.claims)


def test_rekey_canonicalizes_belief_holder_and_key_together() -> None:
    observation = _observation()
    context = ClaimSemanticContext(
        assertion_mode=ClaimAssertionMode.ATTRIBUTED_BELIEF,
        epistemic_status=ClaimEpistemicStatus.BELIEVED,
        polarity=ClaimPolarity.NEGATIVE,
        modality=ClaimModality.POSSIBLE,
        attribution_source_id=observation.source_id,
        attribution_speaker_id=observation.speaker_id,
        belief_holder_entity_id="mention:alice",
    )
    claim = ExtractedClaim(
        claim_id="claim:belief-rekey",
        claim_key=ClaimKey(
            subject_entity_id="mention:atlas",
            predicate_id="owner",
            assertion_mode=context.assertion_mode,
            epistemic_status=context.epistemic_status,
            polarity=context.polarity,
            modality=context.modality,
            belief_holder_entity_id=context.belief_holder_entity_id,
        ),
        object_value="Bob",
        semantic_context=context,
        evidence_spans=[
            EvidenceSpan(
                source_id=observation.source_id,
                quote=observation.text,
                source_type=SourceType.USER,
                timestamp=observation.timestamp,
            )
        ],
        confidence=ConfidenceComponents(extraction=0.8, evidence=0.8, source_trust=0.8, calibrated=0.8),
        extraction_run_id="run:belief-rekey",
    )

    rekeyed, transition = EntityResolutionService().canonicalize_claim_entities(
        claim=claim,
        references={
            ("mention:atlas", claim.claim_key.scope.identity): "ent:atlas",
            ("mention:alice", claim.claim_key.scope.identity): "ent:alice",
        },
    )

    assert transition is not None
    assert rekeyed.claim_key.subject_entity_id == "ent:atlas"
    assert rekeyed.semantic_context.belief_holder_entity_id == "ent:alice"
    assert rekeyed.claim_key.belief_holder_entity_id == "ent:alice"


def test_service_persists_semantic_context_and_never_promotes_belief_or_legacy_claim() -> None:
    observation = SourceObservation(
        source_id="tx:semantic-service",
        text="Alice confirms Atlas owner is Bob.",
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
        speaker_id="operator",
    )
    output = {
        "entities": [
            {
                "entity_ref": "atlas",
                "mention_text": "Atlas",
                "entity_type": "project",
                "source_id": observation.source_id,
                "quote": "Atlas",
                "confidence": 0.9,
            },
                {
                    "entity_ref": "alice",
                "mention_text": "Alice",
                "entity_type": "person",
                "source_id": observation.source_id,
                "quote": "Alice",
                    "confidence": 0.9,
                },
                {
                    "entity_ref": "bob",
                    "mention_text": "Bob",
                    "entity_type": "person",
                    "source_id": observation.source_id,
                    "quote": "Bob",
                    "confidence": 0.9,
                },
        ],
        "claims": [],
        "actions": [],
        "identity_relations": [],
    }
    base_claim = {
        "subject_entity_ref": "atlas",
        "predicate_id": "owner",
        "object_value": "Bob",
        "object_entity_ref": "bob",
        "source_id": observation.source_id,
        "quote": observation.text,
        "confidence": 0.9,
    }
    output["claims"] = [
        {
            **base_claim,
            "semantic_context": {
                "assertion_mode": "world_assertion",
                "epistemic_status": "asserted",
                "polarity": "positive",
                "modality": "assertion",
                "attribution_source_id": observation.source_id,
                "attribution_speaker_id": "operator",
                "reported_source_id": None,
                "belief_holder_entity_ref": None,
            },
        },
        {
            **base_claim,
            "semantic_context": {
                "assertion_mode": "attributed_belief",
                "epistemic_status": "believed",
                "polarity": "positive",
                "modality": "assertion",
                "attribution_source_id": observation.source_id,
                "attribution_speaker_id": "operator",
                "reported_source_id": None,
                "belief_holder_entity_ref": "alice",
            },
        },
        base_claim,
    ]
    proposal = models_from_llm_output(
        run_id="run:semantic-service",
        provider="test",
        model=None,
        prompt_hash=None,
        observations=[observation],
        output=output,
    )

    class FixedExtractor:
        provider = "test"
        model = None
        prompt_hash = None

        def extract(self, observations: list[SourceObservation]) -> MemoryExtractionProposal:
            assert [item.source_id for item in observations] == [observation.source_id]
            return proposal

    memory_plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=memory_plane, extractor=FixedExtractor())
    service.evolve_records(
        [
            CanonicalMemoryRecord(
                memory_id=observation.source_id,
                domain=MemoryDomain.TRANSCRIPT,
                text=observation.text,
                content={"source_speaker_id": "operator"},
                status=CommitStatus.COMMITTED,
                validity_status=TemporalValidityStatus.ACTIVE,
                source_kind="user",
                timestamp=observation.timestamp,
                is_raw_event=True,
            )
        ]
    )

    current = service.retrieve_claim_states(view=RetrievalView.CURRENT)
    all_versions = service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    assert len(current) == 1
    assert current[0].semantic_context.assertion_mode == ClaimAssertionMode.WORLD_ASSERTION
    assert {state.lifecycle_state.value for state in all_versions} == {"active", "invalidated"}
    belief_state = next(
        state for state in all_versions if state.semantic_context.assertion_mode == ClaimAssertionMode.ATTRIBUTED_BELIEF
    )
    persisted = memory_plane.get_record(f"mem:evolution:claim:{belief_state.claim_id}")
    assert persisted is not None
    assert persisted.content["claim_state"]["semantic_context"] == belief_state.semantic_context.model_dump(mode="json")


def test_reported_belief_cannot_promote_when_model_mislabeled_as_world_assertion() -> None:
    observation = _observation()
    proposal = models_from_llm_output(
        run_id="run:mislabeled-world",
        provider="test",
        model=None,
        prompt_hash=None,
        observations=[observation],
        output={
            "entities": [
                {
                    "entity_ref": "atlas",
                    "mention_text": "Atlas",
                    "entity_type": "project",
                    "source_id": observation.source_id,
                    "quote": "Atlas",
                    "confidence": 0.9,
                },
                {
                    "entity_ref": "bob",
                    "mention_text": "Bob",
                    "entity_type": "person",
                    "source_id": observation.source_id,
                    "quote": "Bob",
                    "confidence": 0.9,
                }
            ],
            "claims": [
                {
                    "subject_entity_ref": "atlas",
                    "predicate_id": "owner",
                    "object_value": "Bob",
                    "object_entity_ref": "bob",
                    "source_id": observation.source_id,
                    "quote": observation.text,
                    "confidence": 0.9,
                    "semantic_context": {
                        "assertion_mode": "world_assertion",
                        "epistemic_status": "asserted",
                        "polarity": "positive",
                        "modality": "assertion",
                        "attribution_source_id": observation.source_id,
                        "attribution_speaker_id": "operator",
                        "reported_source_id": None,
                        "belief_holder_entity_ref": None,
                    },
                }
            ],
            "actions": [],
            "identity_relations": [],
        },
    )

    class FixedExtractor:
        provider = "test"
        model = None
        prompt_hash = None

        def extract(self, observations: list[SourceObservation]) -> MemoryExtractionProposal:
            return proposal

    service = MemoryEvolutionService(memory_plane=MemoryPlaneService(), extractor=FixedExtractor())
    result = service.evolve_records(
        [
            CanonicalMemoryRecord(
                memory_id=observation.source_id,
                domain=MemoryDomain.TRANSCRIPT,
                text=observation.text,
                content={"source_speaker_id": "operator"},
                status=CommitStatus.COMMITTED,
                validity_status=TemporalValidityStatus.ACTIVE,
                source_kind="user",
                timestamp=observation.timestamp,
                is_raw_event=True,
            )
        ]
    )

    assert result.claim_states[0].lifecycle_state.value == "invalidated"
    assert service.retrieve_claim_states(view=RetrievalView.CURRENT) == []


def test_current_and_historical_retrieval_exclude_persisted_legacy_claim_states() -> None:
    timestamp = datetime(2026, 7, 30, tzinfo=UTC)
    confidence = ConfidenceComponents(extraction=0.8, evidence=0.8, source_trust=0.8, calibrated=0.8)
    evidence = [
        EvidenceSpan(
            source_id="tx:legacy-replay",
            quote="Atlas owner is Bob.",
            source_type=SourceType.USER,
            timestamp=timestamp,
        )
    ]
    world_context = ClaimSemanticContext(
        assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
        epistemic_status=ClaimEpistemicStatus.ASSERTED,
        polarity=ClaimPolarity.POSITIVE,
        modality=ClaimModality.ASSERTION,
        attribution_source_id="tx:legacy-replay",
    )
    states = [
        ClaimState(
            claim_id="claim:resolved",
            claim_key=ClaimKey(
                subject_entity_id="ent:atlas",
                predicate_id="owner",
                assertion_mode=world_context.assertion_mode,
                epistemic_status=world_context.epistemic_status,
                polarity=world_context.polarity,
                modality=world_context.modality,
            ),
            object_value="Bob",
            lifecycle_state=ClaimLifecycleState.ACTIVE,
            source_claim_id="claim:resolved",
            confidence=confidence,
            semantic_context=world_context,
            evidence_spans=evidence,
            valid_from=timestamp,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        ClaimState(
            claim_id="claim:legacy",
            claim_key=ClaimKey(subject_entity_id="ent:atlas", predicate_id="owner"),
            object_value="Alice",
            lifecycle_state=ClaimLifecycleState.ACTIVE,
            source_claim_id="claim:legacy",
            confidence=confidence,
            evidence_spans=evidence,
            valid_from=timestamp,
            created_at=timestamp,
            updated_at=timestamp,
        ),
    ]
    memory_plane = MemoryPlaneService()
    memory_plane.write_records(
        [record_from_claim_state(state=state, source_candidate_id="replay") for state in states]
    )
    service = MemoryEvolutionService(memory_plane=memory_plane, now_provider=lambda: timestamp)

    assert [state.claim_id for state in service.retrieve_claim_states(view=RetrievalView.CURRENT)] == [
        "claim:resolved"
    ]
    assert [state.claim_id for state in service.retrieve_claim_states(view=RetrievalView.HISTORICAL_AT, valid_at=timestamp)] == [
        "claim:resolved"
    ]
    assert {state.claim_id for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)} == {
        "claim:resolved",
        "claim:legacy",
    }
    assert {state.claim_id for state in service.retrieve_claim_states(view=RetrievalView.EVIDENCE_ONLY)} == {
        "claim:resolved",
        "claim:legacy",
    }


@pytest.mark.parametrize(
    "unrelated_text",
    [
        "Atlas owner is not Alice.",
        "Who owns Atlas?",
        'Someone quoted "Atlas owner is Alice."',
        "Atlas owner might be Alice.",
        "Alice believes Atlas owner is Alice.",
    ],
)
def test_world_certification_uses_exact_positive_evidence_span_not_full_source(
    unrelated_text: str,
) -> None:
    positive_quote = "Atlas owner is Bob."
    observation = SourceObservation(
        source_id="tx:evidence-scope",
        text=f"{positive_quote} {unrelated_text}",
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
    )
    claim = _world_claim_for_evidence(
        observation=observation,
        evidence_spans=[
            EvidenceSpan(
                source_id=observation.source_id,
                quote=positive_quote,
                source_type=SourceType.USER,
                timestamp=observation.timestamp,
            )
        ],
    )

    results = MemoryEvolutionValidator().validate_claim(
        claim=claim,
        observation_by_id={observation.source_id: observation},
    )

    assert MemoryEvolutionValidator().accepted(results)


@pytest.mark.parametrize(
    ("governing_quote", "reason"),
    [
        ("Alice believes Atlas owner is Bob.", "reported belief or speech"),
        ("Atlas owner is not Bob.", "negated source"),
        ("Atlas owner might be Bob.", "modal or ambiguous source"),
        ('"Atlas owner is Bob."', "quoted source"),
        ("Who owns Atlas?", "interrogative source"),
    ],
)
def test_world_certification_rejects_nonassertive_governing_evidence_span(
    governing_quote: str,
    reason: str,
) -> None:
    observation = SourceObservation(
        source_id="tx:governing-evidence",
        text=f"Atlas owner is Bob. {governing_quote}",
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
    )
    claim = _world_claim_for_evidence(
        observation=observation,
        evidence_spans=[
            EvidenceSpan(
                source_id=observation.source_id,
                quote=governing_quote,
                source_type=SourceType.USER,
                timestamp=observation.timestamp,
            )
        ],
    )

    results = MemoryEvolutionValidator().validate_claim(
        claim=claim,
        observation_by_id={observation.source_id: observation},
    )

    assert any(f"world assertion is not source-certified: {reason}" == result.rationale for result in results)
    assert not MemoryEvolutionValidator().accepted(results)


def test_world_certification_rejects_ambiguous_attributed_evidence_spans() -> None:
    observation = SourceObservation(
        source_id="tx:multiple-evidence",
        text="Atlas owner is Bob. Atlas is active.",
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
    )
    claim = _world_claim_for_evidence(
        observation=observation,
        evidence_spans=[
            EvidenceSpan(
                source_id=observation.source_id,
                quote="Atlas owner is Bob.",
                source_type=SourceType.USER,
                timestamp=observation.timestamp,
            ),
            EvidenceSpan(
                source_id=observation.source_id,
                quote="Atlas is active.",
                source_type=SourceType.USER,
                timestamp=observation.timestamp,
            ),
        ],
    )

    results = MemoryEvolutionValidator().validate_claim(
        claim=claim,
        observation_by_id={observation.source_id: observation},
    )

    assert any("ambiguous attributed evidence spans" in result.rationale for result in results)
    assert not MemoryEvolutionValidator().accepted(results)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assertion_mode", "attributed_belief"),
        ("epistemic_status", "believed"),
        ("polarity", "negative"),
        ("modality", "possible"),
        ("belief_holder_entity_id", "ent:alice"),
    ],
)
def test_claim_state_rejects_key_semantic_identity_mutations(field: str, value: str) -> None:
    timestamp = datetime(2026, 7, 30, tzinfo=UTC)
    context = ClaimSemanticContext(
        assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
        epistemic_status=ClaimEpistemicStatus.ASSERTED,
        polarity=ClaimPolarity.POSITIVE,
        modality=ClaimModality.ASSERTION,
        attribution_source_id="tx:state-mutation",
    )
    state = ClaimState(
        claim_id="claim:state-mutation",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            assertion_mode=context.assertion_mode,
            epistemic_status=context.epistemic_status,
            polarity=context.polarity,
            modality=context.modality,
        ),
        object_value="Bob",
        lifecycle_state=ClaimLifecycleState.ACTIVE,
        source_claim_id="claim:state-mutation",
        confidence=ConfidenceComponents(extraction=0.9, evidence=0.9, source_trust=0.9, calibrated=0.9),
        semantic_context=context,
        valid_from=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
    payload = state.model_dump(mode="json")
    payload["claim_key"][field] = value

    with pytest.raises(ValidationError, match="claim state key must partition semantic proposition identity"):
        ClaimState.model_validate(payload)


def test_hydration_rejects_mismatched_claim_state_before_truth_retrieval() -> None:
    timestamp = datetime(2026, 7, 30, tzinfo=UTC)
    context = ClaimSemanticContext(
        assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
        epistemic_status=ClaimEpistemicStatus.ASSERTED,
        polarity=ClaimPolarity.POSITIVE,
        modality=ClaimModality.ASSERTION,
        attribution_source_id="tx:bad-hydration",
    )
    state = ClaimState(
        claim_id="claim:bad-hydration",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            assertion_mode=context.assertion_mode,
            epistemic_status=context.epistemic_status,
            polarity=context.polarity,
            modality=context.modality,
        ),
        object_value="Bob",
        lifecycle_state=ClaimLifecycleState.ACTIVE,
        source_claim_id="claim:bad-hydration",
        confidence=ConfidenceComponents(extraction=0.9, evidence=0.9, source_trust=0.9, calibrated=0.9),
        semantic_context=context,
        valid_from=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
    record = record_from_claim_state(state=state, source_candidate_id="replay")
    payload = dict(record.content["claim_state"])
    payload["claim_key"] = {**payload["claim_key"], "polarity": "negative"}
    memory_plane = MemoryPlaneService()
    memory_plane.write_records([record.model_copy(update={"content": {**record.content, "claim_state": payload}})])
    service = MemoryEvolutionService(memory_plane=memory_plane, now_provider=lambda: timestamp)

    with pytest.raises(ValidationError, match="claim state key must partition semantic proposition identity"):
        service.retrieve_claim_states(view=RetrievalView.CURRENT)


@pytest.mark.parametrize(
    ("source_text", "cropped_quote"),
    [
        ("Alice believes Atlas owner is Bob.", "Atlas owner is Bob."),
        ('Alice wrote "Atlas owner is Bob."', "Atlas owner is Bob."),
        ("It is not true that Atlas owner is Bob.", "Atlas owner is Bob."),
        ("It may be that Atlas owner is Bob.", "Atlas owner is Bob."),
        ("Is it true that Atlas owner is Bob?", "Atlas owner is Bob"),
    ],
)
@pytest.mark.parametrize("with_offsets", [False, True])
def test_service_rejects_cropped_nonassertive_construction_labeled_as_world_truth(
    source_text: str,
    cropped_quote: str,
    with_offsets: bool,
) -> None:
    observation = SourceObservation(
        source_id="tx:cropped-construction",
        text=source_text,
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
    )
    quote_start = source_text.index(cropped_quote)
    span = EvidenceSpan(
        source_id=observation.source_id,
        quote=cropped_quote,
        char_start=quote_start if with_offsets else None,
        char_end=quote_start + len(cropped_quote) if with_offsets else None,
        source_type=SourceType.USER,
        timestamp=observation.timestamp,
    )
    context = ClaimSemanticContext(
        assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
        epistemic_status=ClaimEpistemicStatus.ASSERTED,
        polarity=ClaimPolarity.POSITIVE,
        modality=ClaimModality.ASSERTION,
        attribution_source_id=observation.source_id,
    )
    claim = ExtractedClaim(
        claim_id="claim:cropped-construction",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            assertion_mode=context.assertion_mode,
            epistemic_status=context.epistemic_status,
            polarity=context.polarity,
            modality=context.modality,
        ),
        object_value="Bob",
        object_entity_id="ent:bob",
        semantic_context=context,
        evidence_spans=[span],
        confidence=ConfidenceComponents(extraction=0.9, evidence=0.9, source_trust=0.9, calibrated=0.9),
        extraction_run_id="run:cropped-construction",
    )
    entities = [
        EntityMention(
            entity_id="ent:atlas",
            mention_text="Atlas",
            normalized_name="atlas",
            entity_type=EntityType.PROJECT,
            evidence_spans=[span],
            confidence=0.9,
        ),
        EntityMention(
            entity_id="ent:bob",
            mention_text="Bob",
            normalized_name="bob",
            entity_type=EntityType.PERSON,
            evidence_spans=[span],
            confidence=0.9,
        ),
    ]
    proposal = MemoryExtractionProposal(
        run=ExtractionRun(
            extraction_run_id="run:cropped-construction",
            provider="test",
            input_source_ids=[observation.source_id],
            entity_ids=[entity.entity_id for entity in entities],
            claim_ids=[claim.claim_id],
        ),
        entities=entities,
        claims=[claim],
    )

    class FixedExtractor:
        provider = "test"
        model = None
        prompt_hash = None

        def extract(self, observations: list[SourceObservation]) -> MemoryExtractionProposal:
            return proposal

    service = MemoryEvolutionService(memory_plane=MemoryPlaneService(), extractor=FixedExtractor())
    try:
        result = service.evolve_records(
            [
                CanonicalMemoryRecord(
                    memory_id=observation.source_id,
                    domain=MemoryDomain.TRANSCRIPT,
                    text=observation.text,
                    status=CommitStatus.COMMITTED,
                    validity_status=TemporalValidityStatus.ACTIVE,
                    source_kind="user",
                    timestamp=observation.timestamp,
                    is_raw_event=True,
                )
            ]
        )
    except (MemoryEvolutionMutationValidationError, MemoryExtractionRunError):
        result = None

    if result is not None:
        assert all(state.lifecycle_state.value != "active" for state in result.claim_states)
    assert service.retrieve_claim_states(view=RetrievalView.CURRENT) == []


@pytest.mark.parametrize("with_offsets", [False, True])
def test_service_accepts_full_direct_positive_construction_in_multi_sentence_source(
    with_offsets: bool,
) -> None:
    quote = "Atlas owner is Bob."
    observation = SourceObservation(
        source_id="tx:full-construction",
        text=f"{quote} Alice believes Atlas owner is Carol.",
        source_type=SourceType.USER,
        timestamp=datetime(2026, 7, 30, tzinfo=UTC),
    )
    claim = _world_claim_for_evidence(
        observation=observation,
        evidence_spans=[
            EvidenceSpan(
                source_id=observation.source_id,
                quote=quote,
                char_start=0 if with_offsets else None,
                char_end=len(quote) if with_offsets else None,
                source_type=SourceType.USER,
                timestamp=observation.timestamp,
            )
        ],
    ).model_copy(
        update={"extraction_run_id": "run:full-construction", "object_entity_id": "ent:bob"}
    )
    entities = [
        EntityMention(
            entity_id="ent:atlas",
            mention_text="Atlas",
            normalized_name="atlas",
            entity_type=EntityType.PROJECT,
            evidence_spans=list(claim.evidence_spans),
            confidence=0.9,
        ),
        EntityMention(
            entity_id="ent:bob",
            mention_text="Bob",
            normalized_name="bob",
            entity_type=EntityType.PERSON,
            evidence_spans=list(claim.evidence_spans),
            confidence=0.9,
        ),
    ]
    proposal = MemoryExtractionProposal(
        run=ExtractionRun(
            extraction_run_id="run:full-construction",
            provider="test",
            input_source_ids=[observation.source_id],
            entity_ids=[entity.entity_id for entity in entities],
            claim_ids=[claim.claim_id],
        ),
        entities=entities,
        claims=[claim],
    )

    class FixedExtractor:
        provider = "test"
        model = None
        prompt_hash = None

        def extract(self, observations: list[SourceObservation]) -> MemoryExtractionProposal:
            return proposal

    service = MemoryEvolutionService(memory_plane=MemoryPlaneService(), extractor=FixedExtractor())
    result = service.evolve_records(
        [
            CanonicalMemoryRecord(
                memory_id=observation.source_id,
                domain=MemoryDomain.TRANSCRIPT,
                text=observation.text,
                status=CommitStatus.COMMITTED,
                validity_status=TemporalValidityStatus.ACTIVE,
                source_kind="user",
                timestamp=observation.timestamp,
                is_raw_event=True,
            )
        ]
    )

    assert result.claim_states[0].lifecycle_state.value == "active"
    assert [state.claim_id for state in service.retrieve_claim_states(view=RetrievalView.CURRENT)] == [
        claim.claim_id
    ]
