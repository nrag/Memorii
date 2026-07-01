from datetime import UTC, datetime

import pytest

from memorii.core.memory_evolution import (
    ClaimKey,
    EvidenceSpan,
    ExtractedClaim,
    MemoryEvolutionService,
    MemoryEvolutionValidator,
    PredicateRegistry,
    RetrievalView,
    RuleMemoryExtractor,
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


def test_higher_trust_correction_blocks_later_transcript_chatter() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    transcript = _record(
        "tx:deploy:transcript",
        "Atlas deploy succeeded.",
        source_kind="provider",
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


def test_provider_ingestion_can_opt_into_runtime_memory_evolution() -> None:
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
    assert [claim.object_value for claim in result.claims] == ["Bob"]
    assert any(record_id.startswith("mem:evolution:claim:") for record_id in result.written_record_ids)


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
