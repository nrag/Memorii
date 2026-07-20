from datetime import UTC, datetime

from memorii.core.memory_evolution import EnglishRuleMemoryExtractor
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import CommitStatus, MemoryDomain


def _action_record(*, memory_id: str, text: str, task_id: str, user_id: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        content={"text": text},
        status=CommitStatus.COMMITTED,
        source_kind="user",
        task_id=task_id,
        user_id=user_id,
        timestamp=datetime(2026, 1, 15, tzinfo=UTC),
        is_raw_event=True,
    )


def test_execution_prefetch_never_discloses_unreadable_branch_or_event() -> None:
    service = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        memory_evolution_extractor=EnglishRuleMemoryExtractor(),
    )
    evolution = service.memory_evolution_service
    evolution.evolve_records(
        [
            _action_record(
                memory_id="event:private-atlas",
                text="Private Atlas migration resumed",
                task_id="task:private-atlas",
                user_id="user:other",
            ),
            _action_record(
                memory_id="event:beta",
                text="Beta rollout resumed",
                task_id="task:beta",
                user_id="user:requester",
            ),
        ]
    )

    context = service.prefetch(
        "Continue the previous fix",
        task_id="task:beta",
        user_id="user:requester",
    )
    bundle = service.last_recall_bundle()
    assert bundle is not None
    serialized_trace = str(bundle.trace)

    assert "beta-rollout" in context
    assert "Private Atlas" not in context
    assert "private-atlas" not in context
    assert "event:private-atlas" not in serialized_trace
    assert "ent:private-atlas-migration" not in serialized_trace


def test_execution_prefetch_is_unchanged_when_unreadable_state_is_added() -> None:
    plane = MemoryPlaneService()
    service = ProviderMemoryService(
        memory_plane=plane,
        memory_evolution_extractor=EnglishRuleMemoryExtractor(),
    )
    evolution = service.memory_evolution_service
    beta = _action_record(
        memory_id="event:beta",
        text="Beta rollout resumed",
        task_id="task:beta",
        user_id="user:requester",
    )
    evolution.evolve_records([beta])
    before = service.prefetch(
        "Continue the previous fix",
        task_id="task:beta",
        user_id="user:requester",
    )

    evolution.evolve_records(
        [
            _action_record(
                memory_id="event:private-atlas",
                text="Private Atlas migration resumed",
                task_id="task:private-atlas",
                user_id="user:other",
            )
        ]
    )
    after = service.prefetch(
        "Continue the previous fix",
        task_id="task:beta",
        user_id="user:requester",
    )

    assert after == before
