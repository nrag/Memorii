from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.memory_evolution import (
    EnglishRuleMemoryExtractor,
    MemoryEvolutionService,
    MemoryQueryRequest,
    MemoryScope,
    SemanticFrameStatus,
    StructuredQueryAnalyzer,
)
from memorii.core.memory_evolution.temporal_contracts import TemporalEntityCandidate
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain


def _observation(*, language: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"tx:owner:{language}",
        domain=MemoryDomain.TRANSCRIPT,
        text="Atlas owner is Bob.",
        content={"text": "Atlas owner is Bob."},
        status=CommitStatus.COMMITTED,
        source_kind="user",
        timestamp=datetime(2026, 7, 16, tzinfo=UTC),
        task_id="task:atlas",
        language=language,
        is_raw_event=True,
    )


def _scope() -> MemoryScope:
    return MemoryScope(scope_key="task:atlas", task_id="task:atlas")


def test_english_rules_do_not_parse_text_declared_as_spanish() -> None:
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=EnglishRuleMemoryExtractor(),
    )

    result = service.evolve_records([_observation(language="es")])

    assert result.entities == []
    assert result.claims == []
    assert result.actions == []
    assert result.extraction_run.errors == ["tx:owner:es: unsupported_language:es"]


def test_english_query_analyzer_returns_typed_unsupported_language_abstention() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records([_observation(language="en")])

    decision = service.retrieve(
        MemoryQueryRequest(
            query="¿Quién es el propietario actual de Atlas?",
            query_language="es",
            reference_time=datetime(2026, 7, 17, tzinfo=UTC),
            scope=_scope(),
        )
    )

    assert decision.semantic_frame_status == SemanticFrameStatus.UNSUPPORTED
    assert decision.abstained is True
    assert decision.selected_record_ids == []
    assert decision.query_analysis is not None
    assert decision.query_analysis.failure_code == "unsupported_language"


def test_structured_analysis_can_resolve_spanish_query_from_visible_catalog() -> None:
    def analyze(**kwargs: object) -> dict[str, object]:
        candidates = kwargs["entity_candidates"]
        assert isinstance(candidates, list)
        atlas = next(
            candidate
            for candidate in candidates
            if isinstance(candidate, TemporalEntityCandidate) and "Atlas" in candidate.names
        )
        return {
            "language": "es",
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "candidate_entity_ids": [atlas.entity_id],
            "predicate_id": "owner",
            "model_confidence": 0.9,
        }

    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        query_analyzer=StructuredQueryAnalyzer(
            analyze,
            analyzer_name="multilingual_test_provider",
            analyzer_version="1",
        ),
    )
    service.evolve_records([_observation(language="en")])

    decision = service.retrieve(
        MemoryQueryRequest(
            query="¿Quién es el propietario actual de Atlas?",
            query_language="es",
            reference_time=datetime(2026, 7, 17, tzinfo=UTC),
            scope=_scope(),
        )
    )

    assert decision.semantic_frame_status == SemanticFrameStatus.MATCHED
    assert decision.abstained is False
    assert len(decision.selected_record_ids) == 1
    selected_states = {
        state.claim_id: state for state in service.retrieve_claim_states()
    }
    assert selected_states[decision.selected_record_ids[0]].object_value == "Bob"
