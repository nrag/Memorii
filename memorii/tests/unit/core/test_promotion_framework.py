from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.provider.models import ProviderOperation
from memorii.core.promotion import (
    PromotionAction,
    PromotionContext,
    PromotionContextBuilder,
    PromotionDecision,
    PromotionExecutor,
    PromotionReasonCode,
    PromotionService,
    RuleBasedPromotionDecider,
    build_promotion_decider,
)
from memorii.domain.enums import CommitStatus, MemoryDomain


class FakePromotionDecider:
    def evaluate(self, *, candidate: CanonicalMemoryRecord, context: PromotionContext) -> PromotionDecision:
        return PromotionDecision(
            action=PromotionAction.KEEP_STAGED,
            target_domain=candidate.domain,
            reason_codes=[PromotionReasonCode.FAKE_DECIDER],
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
    assert result.reason_codes == [PromotionReasonCode.FAKE_DECIDER]


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
    assert result.reason_codes == [PromotionReasonCode.SEMANTIC_EXPLICIT_WRITE_SAFE]
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
    assert result.reason_codes == [PromotionReasonCode.DUPLICATE_COMMITTED_MEMORY_EXISTS]


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
    assert result.reason_codes == [PromotionReasonCode.POSSIBLE_CONFLICT_WITH_COMMITTED_MEMORY]


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


def test_provider_staged_learning_candidate_uses_natural_source_kind_for_promotion() -> None:
    plane = MemoryPlaneService()
    provider = ProviderMemoryService(memory_plane=plane)
    staged = provider.apply_memory_write(
        operation=ProviderOperation.MEMORY_WRITE_USER,
        content="respond with concise bullet points",
        session_id="session:learning",
        task_id="task:learning",
        user_id="user:learning",
        action="upsert",
        target="user",
    )
    assert staged.candidate_ids
    candidate_id = staged.candidate_ids[0]
    candidate = plane.get_record(candidate_id)
    assert candidate is not None
    assert candidate.source_kind == "provider:memory_write_user"

    promotion = PromotionService(
        context_builder=PromotionContextBuilder(memory_plane=plane),
        decider=RuleBasedPromotionDecider(),
        executor=PromotionExecutor(memory_plane=plane),
    )
    result = promotion.promote_candidate(candidate_id)
    assert result.committed_memory_id is not None


def test_promotion_decider_factory_builds_rule_based_v1() -> None:
    decider = build_promotion_decider("rule_based_v1")
    assert isinstance(decider, RuleBasedPromotionDecider)


def test_promotion_decider_factory_rejects_unsupported_kind() -> None:
    try:
        build_promotion_decider("unknown_v99")
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected unsupported decider kind to raise ValueError")
    assert "unsupported promotion decider kind" in message
    assert "rule_based_v1" in message


def test_promote_candidates_exposes_structured_observability_counts() -> None:
    plane = MemoryPlaneService()
    semantic_candidate = _candidate(
        memory_id="cand:semantic:obs",
        domain=MemoryDomain.SEMANTIC,
        text="do not auto-expand claims",
        source_kind="provider:memory_write_longterm",
    )
    episodic_candidate = _candidate(
        memory_id="cand:episodic:obs",
        domain=MemoryDomain.EPISODIC,
        text="daily incident summary",
        source_kind="provider:memory_write_dailylog",
    )
    plane.stage_record(semantic_candidate)
    plane.stage_record(episodic_candidate)
    service = PromotionService(
        context_builder=PromotionContextBuilder(memory_plane=plane),
        decider=RuleBasedPromotionDecider(),
        executor=PromotionExecutor(memory_plane=plane),
    )

    batch = service.promote_candidates(task_id="task:1")

    assert batch.count_by_action[PromotionAction.COMMIT] == 2
    assert batch.count_by_target_domain[MemoryDomain.SEMANTIC] == 1
    assert batch.count_by_target_domain[MemoryDomain.EPISODIC] == 1
    assert batch.count_by_reason_code[PromotionReasonCode.SEMANTIC_EXPLICIT_WRITE_SAFE] == 1
    assert batch.count_by_reason_code[PromotionReasonCode.EPISODIC_CANDIDATE_TRUSTED_SOURCE] == 1
    assert batch.count_by_decider["rule_based_v1"] == 2
