from datetime import UTC, datetime

from memorii.core.router import MemoryRouter
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.domain.routing import InboundEvent, InboundEventClass


def test_one_event_routes_to_multiple_memory_domains() -> None:
    router = MemoryRouter()
    decision = router.route_event(
        InboundEvent(
            event_id="evt-1",
            event_class=InboundEventClass.SOLVER_OBSERVATION,
            task_id="task-1",
            execution_node_id="exec-1",
            solver_run_id="solver-1",
            payload={"observation": "failing assertion"},
            timestamp=datetime.now(UTC),
        )
    )

    domains = {item.domain for item in decision.routed_objects}
    assert domains == {MemoryDomain.TRANSCRIPT, MemoryDomain.SOLVER}


def test_transcript_only_events_stay_transcript_only_when_appropriate() -> None:
    router = MemoryRouter()
    decision = router.route_event(
        InboundEvent(
            event_id="evt-2",
            event_class=InboundEventClass.AGENT_MESSAGE,
            task_id="task-1",
            payload={"content": "hello"},
            timestamp=datetime.now(UTC),
        )
    )

    assert [item.domain for item in decision.routed_objects] == [MemoryDomain.TRANSCRIPT]


def test_transcript_memory_preserves_verbatim_raw_payloads() -> None:
    router = MemoryRouter()
    raw_payload = {"nested": {"tool": "result", "raw": [1, 2, 3]}}
    decision = router.route_event(
        InboundEvent(
            event_id="evt-3",
            event_class=InboundEventClass.TOOL_RESULT,
            task_id="task-1",
            payload=raw_payload,
            timestamp=datetime.now(UTC),
        )
    )

    transcript = decision.routed_objects[0].memory_object
    assert transcript.memory_type == MemoryDomain.TRANSCRIPT
    assert transcript.content["raw"] == raw_payload


def test_stable_user_preference_creates_candidate_without_auto_commit() -> None:
    router = MemoryRouter()
    decision = router.route_event(
        InboundEvent(
            event_id="evt-4",
            event_class=InboundEventClass.USER_PREFERENCE_CANDIDATE,
            task_id="task-1",
            payload={"preference": "concise responses"},
            timestamp=datetime.now(UTC),
        )
    )

    user_object = next(item for item in decision.routed_objects if item.domain == MemoryDomain.USER).memory_object
    assert user_object.status == CommitStatus.CANDIDATE


def test_failing_test_routes_to_transcript_execution_and_solver() -> None:
    router = MemoryRouter()
    decision = router.route_event(
        InboundEvent(
            event_id="evt-5",
            event_class=InboundEventClass.TOOL_RESULT,
            task_id="task-1",
            execution_node_id="exec-1",
            solver_run_id="solver-1",
            payload={"status": "failed", "reason": "integration test failed"},
            timestamp=datetime.now(UTC),
        )
    )

    domains = {item.domain for item in decision.routed_objects}
    assert domains == {MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER}
