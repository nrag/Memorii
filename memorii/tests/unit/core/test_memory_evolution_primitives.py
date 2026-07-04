from datetime import UTC, datetime

import pytest

from memorii.core.memory_evolution import (
    ClaimKey,
    EntityLinkState,
    EntityResolutionService,
    EvidenceSpan,
    ExtractionTriggerMode,
    ExtractedClaim,
    MemoryEvolutionService,
    MemoryEvolutionValidator,
    PredicateRegistry,
    RetrievalView,
    RuleMemoryExtractor,
    SourceModality,
    SourceModalityClassifier,
    build_memory_extractor_from_env,
)
from memorii.core.memory_evolution.models import ConfidenceComponents
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import CommitStatus, MemoryDomain, SourceType


def _record(
    memory_id: str,
    text: str,
    *,
    source_kind: str = "user",
    timestamp: datetime | None = None,
    task_id: str | None = "task:evolution",
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        content={"text": text},
        status=CommitStatus.COMMITTED,
        source_kind=source_kind,
        timestamp=timestamp or datetime(2026, 1, 1, tzinfo=UTC),
        task_id=task_id,
        is_raw_event=True,
    )


def test_claim_key_is_stable_and_excludes_object_value() -> None:
    first = ClaimKey(
        subject_entity_id="ent:atlas",
        predicate_id="owner",
        scope_key="task:1",
        qualifier_key="default",
    )
    second = ClaimKey(
        subject_entity_id="ent:atlas",
        predicate_id="owner",
        scope_key="task:1",
        qualifier_key="default",
    )

    assert first.stable_id() == second.stable_id()
    assert first.stable_id() == "ent:atlas|owner|task:1|default"


def test_predicate_registry_rejects_missing_policies() -> None:
    registry = PredicateRegistry()

    assert registry.require("owner").predicate_id == "owner"
    with pytest.raises(KeyError):
        registry.require("unknown_predicate")


def test_evidence_span_requires_valid_offset_pair() -> None:
    with pytest.raises(ValueError):
        EvidenceSpan(
            source_id="tx:1",
            quote="Atlas owner is Bob",
            char_start=10,
            source_type=SourceType.USER,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_validator_requires_evidence_quote_to_exist_in_source() -> None:
    validator = MemoryEvolutionValidator()
    source = _record("tx:1", "Atlas owner is Bob.")
    observation = {
        "source_id": source.memory_id,
        "text": source.text,
        "source_type": SourceType.USER,
        "timestamp": source.timestamp,
        "domain": source.domain,
        "task_id": source.task_id,
    }
    claim = ExtractedClaim(
        claim_id="claim:bad",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            scope_key="task:evolution",
        ),
        object_value="Alice",
        evidence_spans=[
            EvidenceSpan(
                source_id="tx:1",
                quote="Atlas owner is Alice",
                source_type=SourceType.USER,
                timestamp=source.timestamp,
            )
        ],
        confidence=ConfidenceComponents(
            extraction=0.7,
            evidence=0.1,
            source_trust=0.9,
            calibrated=0.5,
        ),
        extraction_run_id="run:1",
    )

    results = validator.validate_claim(
        claim=claim,
        observation_by_id={"tx:1": validator_source_from_dict(observation)},
    )

    assert not validator.accepted(results)
    assert any(result.validator_name == "evidence_span_support" for result in results)


def test_validator_rejects_wrong_predicate_even_when_quote_exists() -> None:
    validator = MemoryEvolutionValidator()
    source = _record("tx:wrong-predicate", "Atlas approver is Bob.")
    claim = ExtractedClaim(
        claim_id="claim:wrong-predicate",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas",
            predicate_id="owner",
            scope_key="task:evolution",
        ),
        object_value="Bob",
        evidence_spans=[
            EvidenceSpan(
                source_id=source.memory_id,
                quote="Atlas approver is Bob",
                source_type=SourceType.USER,
                timestamp=source.timestamp,
            )
        ],
        confidence=ConfidenceComponents(
            extraction=0.7,
            evidence=0.8,
            source_trust=0.9,
            calibrated=0.8,
        ),
        extraction_run_id="run:wrong-predicate",
    )

    results = validator.validate_claim(
        claim=claim,
        observation_by_id={
            source.memory_id: validator_source_from_dict(
                {
                    "source_id": source.memory_id,
                    "text": source.text,
                    "source_type": SourceType.USER,
                    "timestamp": source.timestamp,
                    "domain": source.domain,
                    "task_id": source.task_id,
                }
            )
        },
    )

    assert not validator.accepted(results)
    assert any(result.validator_name == "predicate_support" and result.verdict.value == "fail" for result in results)


def test_source_modality_classifier_identifies_non_assertions() -> None:
    classifier = SourceModalityClassifier()

    assert classifier.classify(
        validator_source_from_dict(
            {
                "source_id": "tx:q",
                "text": "Is Atlas owner Bob?",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ) == SourceModality.QUESTION
    assert classifier.classify(
        validator_source_from_dict(
            {
                "source_id": "tx:paste",
                "text": "Here is a doc: Atlas owner is Bob.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ) == SourceModality.QUOTED_OR_PASTED
    assert classifier.classify(
        validator_source_from_dict(
            {
                "source_id": "tx:hypo",
                "text": "Suppose Atlas owner is Bob.",
                "source_type": SourceType.USER,
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
    ) == SourceModality.HYPOTHETICAL


def test_current_and_historical_truth_are_both_addressable() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    jan = _record(
        "tx:jan",
        "Atlas owner is Alice.",
        timestamp=datetime(2026, 1, 10, tzinfo=UTC),
    )
    mar = _record(
        "tx:mar",
        "Atlas owner is Bob.",
        timestamp=datetime(2026, 3, 20, tzinfo=UTC),
    )

    plane.stage_record(jan)
    service.evolve_records([jan])
    plane.stage_record(mar)
    service.evolve_records([mar])

    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )
    historical = service.retrieve_claim_states(
        view=RetrievalView.HISTORICAL_AT,
        valid_at=datetime(2026, 1, 20, tzinfo=UTC),
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )

    assert [state.object_value for state in current] == ["Bob"]
    assert [state.object_value for state in historical] == ["Alice"]


def test_pasted_and_question_text_are_not_evolved_into_active_claims() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    pasted = _record("tx:pasted", "Here is a doc: Atlas owner is Bob.")
    question = _record("tx:question", "Is Atlas owner Bob?")

    result = service.evolve_records([pasted, question])

    assert result.claims == []
    assert result.deferred_observation_ids == ["tx:pasted"]
    assert result.skipped_observation_ids == ["tx:question"]
    assert service.retrieve_claim_states(view=RetrievalView.CURRENT) == []


def test_higher_trust_correction_blocks_later_transcript_chatter() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    transcript = _record(
        "tx:deploy:tool",
        "Atlas deploy succeeded.",
        source_kind="tool",
        timestamp=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )
    correction = _record(
        "tx:deploy:user",
        "Atlas deploy failed.",
        source_kind="user",
        timestamp=datetime(2026, 3, 1, 12, 5, tzinfo=UTC),
    )
    late_chatter = _record(
        "tx:deploy:late",
        "Atlas deploy succeeded.",
        source_kind="provider",
        timestamp=datetime(2026, 3, 1, 12, 10, tzinfo=UTC),
    )

    for record in [transcript, correction, late_chatter]:
        plane.stage_record(record)
        service.evolve_records([record])

    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="status",
        subject_entity_id="ent:atlas",
    )
    conflicts = service.retrieve_claim_states(view=RetrievalView.CONFLICTS)

    assert [state.object_value for state in current] == ["failed"]
    assert any(state.object_value == "succeeded" for state in conflicts)
    assert service.retrieve_claim_states(view=RetrievalView.EVIDENCE_ONLY)


def test_reinforcement_updates_existing_claim_confidence_instead_of_duplicating() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    first = _record("tx:first", "Atlas owner is Bob.", timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    second = _record("tx:second", "Atlas owner is Bob.", timestamp=datetime(2026, 1, 2, tzinfo=UTC))

    service.evolve_records([first])
    service.evolve_records([second])

    current = service.retrieve_claim_states(
        view=RetrievalView.CURRENT,
        predicate_id="owner",
        subject_entity_id="ent:atlas",
    )
    assert [state.object_value for state in current] == ["Bob"]
    assert len(current) == 1
    assert current[0].confidence_history
    assert current[0].confidence.calibrated > first_confidence_floor()


def test_entity_links_and_contradiction_sets_are_recorded() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    alice = _record("tx:alice", "Atlas owner is Alice.", timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    bob = _record("tx:bob", "Atlas owner is Bob.", timestamp=datetime(2026, 2, 1, tzinfo=UTC))

    first_result = service.evolve_records([alice])
    second_result = service.evolve_records([bob])

    assert {link.canonical_entity_id for link in first_result.entity_links} >= {"ent:atlas", "ent:alice"}
    assert second_result.contradiction_sets
    assert second_result.contradiction_sets[0].active_claim_id in {state.claim_id for state in second_result.claim_states}
    assert any(
        transition.transition_type.value == "supersede"
        for transition in second_result.transitions
    )


def test_entity_resolution_exposes_merge_split_and_claim_rekey_transitions() -> None:
    resolver = EntityResolutionService()
    primary = EntityLinkState(
        link_id="link:atlas",
        mention_text="Atlas",
        canonical_entity_id="ent:atlas",
        normalized_name="atlas",
        aliases=["Atlas"],
        confidence=0.8,
    )
    duplicate = EntityLinkState(
        link_id="link:atlas-project",
        mention_text="Atlas Project",
        canonical_entity_id="ent:atlas-project",
        normalized_name="atlas project",
        aliases=["Atlas Project"],
        confidence=0.7,
    )
    merged, invalidated, merge_transition = resolver.merge_links(primary=primary, duplicate=duplicate)
    split_old, split_new, split_transition = resolver.split_link(
        existing=merged,
        new_entity_id="ent:atlas-billing",
        mention_text="Atlas Billing",
    )
    claim = ExtractedClaim(
        claim_id="claim:rekey",
        claim_key=ClaimKey(
            subject_entity_id="ent:atlas-project",
            predicate_id="owner",
            scope_key="task:evolution",
        ),
        object_value="Bob",
        confidence=ConfidenceComponents(
            extraction=0.7,
            evidence=0.8,
            source_trust=0.9,
            calibrated=0.8,
        ),
        extraction_run_id="run:rekey",
    )
    rekeyed, rekey_transition = resolver.rekey_claim(
        claim=claim,
        new_subject_entity_id="ent:atlas",
    )

    assert "Atlas Project" in merged.aliases
    assert invalidated.lifecycle_state.value == "merged"
    assert split_old.lifecycle_state.value == "split"
    assert split_new.canonical_entity_id == "ent:atlas-billing"
    assert rekeyed.claim_key.subject_entity_id == "ent:atlas"
    assert merge_transition.transition_type.value == "entity_merge"
    assert split_transition.transition_type.value == "entity_split"
    assert rekey_transition.transition_type.value == "claim_rekey"


def test_provider_chat_ingestion_is_deferred_when_evolution_is_opted_in() -> None:
    service = ProviderMemoryService(
        memory_evolution_enabled=True,
        memory_evolution_extractor=RuleMemoryExtractor(),
    )

    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        role="user",
        task_id="task:evolution",
    )

    result = service.last_memory_evolution_result()
    assert result is not None
    assert result.claims == []
    assert result.deferred_observation_ids


def test_explicit_provider_memory_write_triggers_runtime_memory_evolution() -> None:
    service = ProviderMemoryService(
        memory_evolution_enabled=True,
        memory_evolution_extractor=RuleMemoryExtractor(),
    )

    service.apply_memory_write(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Atlas owner is Bob.",
        session_id=None,
        task_id="task:evolution",
        user_id=None,
        action="upsert",
        target="memory",
    )

    result = service.last_memory_evolution_result()
    assert result is not None
    assert [claim.object_value for claim in result.claims] == ["Bob"]
    assert result.observations[0].trigger_mode == ExtractionTriggerMode.IMMEDIATE
    assert any(record_id.startswith("mem:evolution:claim:") for record_id in result.written_record_ids)
    assert result.graph_nodes
    assert result.graph_edges
    assert result.graph_validation_errors == []


def test_memory_extractor_factory_defaults_to_rule_without_live_provider() -> None:
    extractor = build_memory_extractor_from_env(
        env={
            "MEMORII_ENV": "test",
            "MEMORII_SECRET_SOURCE": "process",
            "MEMORII_LLM_PROVIDER": "none",
            "MEMORII_DECISION_MODE": "auto",
        }
    )

    assert isinstance(extractor, RuleMemoryExtractor)


def validator_source_from_dict(payload: dict[str, object]):
    from memorii.core.memory_evolution.models import SourceObservation

    return SourceObservation.model_validate(payload)


def first_confidence_floor() -> float:
    return 0.8
