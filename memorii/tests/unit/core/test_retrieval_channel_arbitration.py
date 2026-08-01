from datetime import UTC, datetime

from memorii.core.memory_evolution import EnglishRuleMemoryExtractor
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.models import ProviderStoredRecord, RetrievalChannelStatus
from memorii.domain.enums import CommitStatus, MemoryDomain
from tests.support.memory_evolution_provider_harness import (
    MemoryEvolutionProviderHarness as ProviderMemoryService,
)


def _evolution_record(*, memory_id: str, text: str, task_id: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        content={"text": text},
        status=CommitStatus.COMMITTED,
        source_kind="user",
        task_id=task_id,
        timestamp=datetime(2026, 1, 15, tzinfo=UTC),
        is_raw_event=True,
    )


def _service() -> ProviderMemoryService:
    return ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        memory_evolution_extractor=EnglishRuleMemoryExtractor(),
        now_provider=lambda: datetime(2026, 1, 16, tzinfo=UTC),
    )


def test_unrelated_evolution_state_does_not_suppress_canonical_answer() -> None:
    service = _service()
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="semantic:timeout",
            domain=MemoryDomain.SEMANTIC,
            text="Timeout default is 30 seconds.",
            status="committed",
            task_id="task:timeout",
        )
    )
    service.memory_evolution_service.evolve_records(
        [
            _evolution_record(
                memory_id="event:atlas",
                text="Atlas migration owner is Bob.",
                task_id="task:atlas",
            )
        ]
    )

    result = service.prefetch_result(
        "What is the timeout default?",
        task_id="task:timeout",
    )

    assert result.selected_channel == "canonical"
    assert result.canonical.status == RetrievalChannelStatus.ANSWER
    assert "Timeout default is 30 seconds" in result.context
    assert "Atlas" not in result.context


def test_unsupported_evolution_language_preserves_canonical_answer() -> None:
    service = _service()
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="semantic:timeout",
            domain=MemoryDomain.SEMANTIC,
            text="El tiempo de espera predeterminado es 30 segundos.",
            status="committed",
            task_id="task:timeout",
        )
    )
    service.memory_evolution_service.evolve_records(
        [
            _evolution_record(
                memory_id="event:timeout",
                text="Timeout default is 30 seconds.",
                task_id="task:timeout",
            )
        ]
    )

    result = service.prefetch_result(
        "¿Cuál es el tiempo de espera predeterminado?",
        task_id="task:timeout",
        query_language="es",
    )

    assert result.selected_channel == "canonical"
    assert result.evolution.status == RetrievalChannelStatus.ABSTAIN
    assert "30 segundos" in result.context


def test_query_matched_evolution_answer_is_authoritative() -> None:
    service = _service()
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="semantic:owner:stale",
            domain=MemoryDomain.SEMANTIC,
            text="Atlas migration owner is Alice.",
            status="committed",
            task_id="task:atlas",
        )
    )
    service.memory_evolution_service.evolve_records(
        [
            _evolution_record(
                memory_id="event:owner:current",
                text="Atlas migration owner is Bob.",
                task_id="task:atlas",
            )
        ]
    )

    result = service.prefetch_result(
        "Who owns the Atlas migration now?",
        task_id="task:atlas",
    )

    assert result.selected_channel == "evolution"
    assert result.evolution.status == RetrievalChannelStatus.ANSWER
    assert "Bob" in result.context
    assert "Alice" not in result.context
