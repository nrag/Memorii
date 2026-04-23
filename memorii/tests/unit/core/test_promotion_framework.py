from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.promotion import (
    PromotionAction,
    PromotionContext,
    PromotionContextBuilder,
    PromotionDecision,
    PromotionExecutor,
    PromotionService,
    RuleBasedPromotionDecider,
)
from memorii.domain.enums import CommitStatus, MemoryDomain


class FakePromotionDecider:
    def evaluate(self, *, candidate: CanonicalMemoryRecord, context: PromotionContext) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.KEEP_STAGED,
            target_domain=candidate.domain,
            reasons=["fake_decider"],
            decided_by="fake",
        )


def _candidate(
    *,
    memory_id: str,
    domain: MemoryDomain,
    text: str,
    source_kind: str,
    task_id: str = "task:1",
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=domain,
        text=text,
        content={"text": text},
        status=CommitStatus.CANDIDATE,
        source_kind=source_kind,
        timestamp=datetime.now(UTC),
        task_id=task_id,
        promotion_state="staged",
    )


def test_promotion_service_accepts_swappable_decider() -> None:
    plane = MemoryPlaneService()
    candidate = _candidate(
        memory_id="cand:episodic:1",
        domain=MemoryDomain.EPISODIC,
        text="incident summary",
        source_kind="provider:memory_write_dailylog",
    )
    plane.stage_record(candidate)

    service = PromotionService(
        context_builder=PromotionContextBuilder(memory_plane=plane),
        decider=FakePromotionDecider(),
        executor=PromotionExecutor(memory_plane=plane),
    )
    result = service.promote_candidate(candidate.memory_id)

    assert result.action == PromotionAction.KEEP_STAGED
    assert result.decided_by == "fake"


def test_rule_based_decider_commits_safe_explicit_semantic_candidate() -> None:
    plane = MemoryPlaneService()
    candidate = _candidate(
        memory_id="cand:semantic:1",
        domain=MemoryDomain.SEMANTIC,
        text="set timeout to 30 seconds",
        source_kind="provider:memory_write_longterm",
    )
    plane.stage_record(candidate)

    service = PromotionService(
        context_builder=PromotionContextBuilder(memory_plane=plane),
        decider=RuleBasedPromotionDecider(),
        executor=PromotionExecutor(memory_plane=plane),
    )
    result = service.promote_candidate(candidate.memory_id)

    assert result.action == PromotionAction.COMMIT
    assert result.committed_memory_id is not None
    committed = plane.get_record(result.committed_memory_id)
    assert committed is not None
    assert committed.source_candidate_id == candidate.memory_id


def test_duplicate_candidate_does_not_create_duplicate_commit() -> None:
    plane = MemoryPlaneService()
    committed = CanonicalMemoryRecord(
        memory_id="mem:semantic:existing",
        domain=MemoryDomain.SEMANTIC,
        text="set timeout to 30 seconds",
        content={"text": "set timeout to 30 seconds"},
        status=CommitStatus.COMMITTED,
        source_kind="seed",
        task_id="task:1",
    )
    plane.stage_record(committed)
    candidate = _candidate(
        memory_id="cand:semantic:duplicate",
        domain=MemoryDomain.SEMANTIC,
        text="set timeout to 30 seconds",
        source_kind="provider:memory_write_longterm",
    )
    plane.stage_record(candidate)

    service = PromotionService(
        context_builder=PromotionContextBuilder(memory_plane=plane),
        decider=RuleBasedPromotionDecider(),
        executor=PromotionExecutor(memory_plane=plane),
    )
    result = service.promote_candidate(candidate.memory_id)

    assert result.action == PromotionAction.KEEP_STAGED
    assert result.duplicate_of_memory_id == committed.memory_id
    assert result.committed_memory_id is None


def test_conflicting_user_candidate_is_not_blindly_committed() -> None:
    plane = MemoryPlaneService()
    plane.stage_record(
        CanonicalMemoryRecord(
            memory_id="mem:user:1",
            domain=MemoryDomain.USER,
            text="user likes long-form paragraphs",
            content={"text": "user likes long-form paragraphs"},
            status=CommitStatus.COMMITTED,
            source_kind="seed",
            task_id="task:1",
        )
    )
    candidate = _candidate(
        memory_id="cand:user:2",
        domain=MemoryDomain.USER,
        text="user prefers concise bullet points",
        source_kind="provider:memory_write_user",
    )
    plane.stage_record(candidate)

    service = PromotionService(
        context_builder=PromotionContextBuilder(memory_plane=plane),
        decider=RuleBasedPromotionDecider(),
        executor=PromotionExecutor(memory_plane=plane),
    )
    result = service.promote_candidate(candidate.memory_id)

    assert result.action in {PromotionAction.KEEP_STAGED, PromotionAction.REJECT}
    assert result.conflict_with_memory_ids == ["mem:user:1"]


def test_promoted_memory_is_visible_through_provider_prefetch_trace() -> None:
    plane = MemoryPlaneService()
    candidate = _candidate(
        memory_id="cand:user:pref",
        domain=MemoryDomain.USER,
        text="respond with concise bullet points",
        source_kind="provider:memory_write_user",
        task_id="task:learning",
    )
    plane.stage_record(candidate)
    plane.stage_record(
        CanonicalMemoryRecord(
            memory_id="tx:style",
            domain=MemoryDomain.TRANSCRIPT,
            text="style discussion in transcript",
            content={"text": "style discussion in transcript"},
            status=CommitStatus.COMMITTED,
            source_kind="seed",
            task_id="task:learning",
        )
    )

    promotion = PromotionService(
        context_builder=PromotionContextBuilder(memory_plane=plane),
        decider=RuleBasedPromotionDecider(),
        executor=PromotionExecutor(memory_plane=plane),
    )
    result = promotion.promote_candidate(candidate.memory_id)
    assert result.committed_memory_id is not None

    provider = ProviderMemoryService(memory_plane=plane)
    provider.prefetch(
        "preference profile concise bullet points",
        task_id="task:learning",
        session_id="session:learning",
        user_id="user:learning",
        top_k=3,
    )
    trace = provider.last_prefetch_trace()
    assert trace is not None
    assert trace.ranked_items
    assert result.committed_memory_id in {item.memory_id for item in trace.ranked_items}
