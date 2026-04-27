from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from memorii.core.llm_decision.evals import (
    InMemoryEvalSnapshotStore,
    JsonlEvalSnapshotStore,
    build_golden_candidate_from_trace,
    should_harvest_golden_candidate,
)
from memorii.core.llm_decision.models import (
    EvalSnapshot,
    JudgeVerdict,
    JuryVerdict,
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_decision.provider import DisabledLLMDecisionProvider
from memorii.core.llm_decision.trace import InMemoryLLMDecisionTraceStore, JsonlLLMDecisionTraceStore


def _trace(
    *,
    trace_id: str = "trace:1",
    decision_point: LLMDecisionPoint = LLMDecisionPoint.PROMOTION,
    status: LLMDecisionStatus = LLMDecisionStatus.SUCCEEDED,
    fallback_used: bool = False,
) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=trace_id,
        decision_point=decision_point,
        mode=LLMDecisionMode.RULE_BASED,
        input_payload={"k": "v"},
        final_output={"decision": "ok"},
        status=status,
        fallback_used=fallback_used,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _snapshot(
    *,
    snapshot_id: str = "snap:1",
    decision_point: LLMDecisionPoint = LLMDecisionPoint.PROMOTION,
    source: str = "offline_golden",
) -> EvalSnapshot:
    return EvalSnapshot(
        snapshot_id=snapshot_id,
        decision_point=decision_point,
        input_payload={"k": "v"},
        source=source,
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def test_llm_decision_trace_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LLMDecisionTrace(
            trace_id="trace:extra",
            decision_point=LLMDecisionPoint.PROMOTION,
            mode=LLMDecisionMode.RULE_BASED,
            input_payload={},
            final_output={},
            status=LLMDecisionStatus.SUCCEEDED,
            created_at=datetime.now(UTC),
            extra_field="nope",
        )


def test_disabled_provider_returns_fallback_trace() -> None:
    provider = DisabledLLMDecisionProvider()
    trace = provider.decide(
        decision_point=LLMDecisionPoint.BELIEF_UPDATE,
        input_payload={"event": "x"},
        prompt_version="v-test",
    )

    assert trace.decision_point == LLMDecisionPoint.BELIEF_UPDATE
    assert trace.mode == LLMDecisionMode.RULE_BASED
    assert trace.fallback_used is True
    assert trace.status == LLMDecisionStatus.FALLBACK_USED
    assert trace.final_output == {}


def test_inmemory_trace_store_append_and_list() -> None:
    store = InMemoryLLMDecisionTraceStore()
    first = _trace(trace_id="trace:1", decision_point=LLMDecisionPoint.PROMOTION)
    second = _trace(
        trace_id="trace:2",
        decision_point=LLMDecisionPoint.BELIEF_UPDATE,
        status=LLMDecisionStatus.VALIDATION_FAILED,
    )

    store.append_trace(first)
    store.append_trace(second)

    assert [trace.trace_id for trace in store.list_traces()] == ["trace:1", "trace:2"]
    assert [trace.trace_id for trace in store.list_traces(decision_point=LLMDecisionPoint.BELIEF_UPDATE)] == [
        "trace:2"
    ]
    assert [trace.trace_id for trace in store.list_traces(status=LLMDecisionStatus.VALIDATION_FAILED)] == [
        "trace:2"
    ]


def test_jsonl_trace_store_append_and_list(tmp_path: pytest.TempPathFactory) -> None:
    store = JsonlLLMDecisionTraceStore(tmp_path / "trace.jsonl")
    first = _trace(trace_id="trace:j1")
    second = _trace(
        trace_id="trace:j2",
        decision_point=LLMDecisionPoint.CONFLICT_DETECTION,
        status=LLMDecisionStatus.PROVIDER_ERROR,
    )

    store.append_trace(first)
    store.append_trace(second)

    assert [trace.trace_id for trace in store.list_traces()] == ["trace:j1", "trace:j2"]
    assert [trace.trace_id for trace in store.list_traces(decision_point=LLMDecisionPoint.CONFLICT_DETECTION)] == [
        "trace:j2"
    ]
    assert [trace.trace_id for trace in store.list_traces(status=LLMDecisionStatus.PROVIDER_ERROR)] == [
        "trace:j2"
    ]


def test_inmemory_eval_snapshot_store_append_and_list() -> None:
    store = InMemoryEvalSnapshotStore()
    first = _snapshot(snapshot_id="snap:1", decision_point=LLMDecisionPoint.PROMOTION)
    second = _snapshot(snapshot_id="snap:2", decision_point=LLMDecisionPoint.BELIEF_UPDATE, source="online_log")

    store.append_snapshot(first)
    store.append_snapshot(second)

    assert [snapshot.snapshot_id for snapshot in store.list_snapshots()] == ["snap:1", "snap:2"]
    assert [
        snapshot.snapshot_id for snapshot in store.list_snapshots(decision_point=LLMDecisionPoint.BELIEF_UPDATE)
    ] == ["snap:2"]
    assert [snapshot.snapshot_id for snapshot in store.list_snapshots(source="online_log")] == ["snap:2"]


def test_jsonl_eval_snapshot_store_append_and_list(tmp_path: pytest.TempPathFactory) -> None:
    store = JsonlEvalSnapshotStore(tmp_path / "snapshots.jsonl")
    first = _snapshot(snapshot_id="snap:j1")
    second = _snapshot(snapshot_id="snap:j2", decision_point=LLMDecisionPoint.DECISION_SUMMARY, source="online_log")

    store.append_snapshot(first)
    store.append_snapshot(second)

    assert [snapshot.snapshot_id for snapshot in store.list_snapshots()] == ["snap:j1", "snap:j2"]
    assert [
        snapshot.snapshot_id for snapshot in store.list_snapshots(decision_point=LLMDecisionPoint.DECISION_SUMMARY)
    ] == ["snap:j2"]
    assert [snapshot.snapshot_id for snapshot in store.list_snapshots(source="online_log")] == ["snap:j2"]


def test_should_harvest_true_for_validation_failed() -> None:
    trace = _trace(status=LLMDecisionStatus.VALIDATION_FAILED)
    assert should_harvest_golden_candidate(trace=trace) is True


def test_should_harvest_true_for_jury_disagreement() -> None:
    trace = _trace(status=LLMDecisionStatus.SUCCEEDED)
    jury = JuryVerdict(
        snapshot_id="snap:1",
        decision_point=trace.decision_point,
        judge_verdicts=[JudgeVerdict(judge_id="judge:1", passed=True)],
        passed=False,
        disagreement=True,
    )
    assert should_harvest_golden_candidate(trace=trace, jury_verdict=jury) is True


def test_should_harvest_false_for_clean_success() -> None:
    trace = _trace(status=LLMDecisionStatus.SUCCEEDED)
    assert should_harvest_golden_candidate(trace=trace) is False


def test_build_golden_candidate_from_trace_stable() -> None:
    trace = _trace(trace_id="trace:stable", decision_point=LLMDecisionPoint.MEMORY_EXTRACTION)

    first = build_golden_candidate_from_trace(
        trace=trace,
        snapshot_id="snap:stable",
        reason="fallback_used",
    )
    second = build_golden_candidate_from_trace(
        trace=trace,
        snapshot_id="snap:stable",
        reason="fallback_used",
    )

    assert first.candidate_id == second.candidate_id
    assert first.snapshot_id == "snap:stable"
    assert first.decision_point == LLMDecisionPoint.MEMORY_EXTRACTION
    assert first.reason == "fallback_used"
