from datetime import UTC, datetime

from memorii.core.consolidation import Consolidator
from memorii.domain.enums import CommitStatus, MemoryDomain


def test_solver_resolution_produces_episodic_writeback_candidate() -> None:
    consolidator = Consolidator()
    candidate = consolidator.from_solver_resolution(
        candidate_id="wb-1",
        task_id="task-1",
        solver_run_id="solver-1",
        execution_node_id="exec-1",
        summary="Root cause fixed",
        source_refs=["evt-1"],
    )

    assert candidate.target_domain == MemoryDomain.EPISODIC
    assert candidate.status == CommitStatus.CANDIDATE


def test_validated_abstraction_can_produce_semantic_writeback_candidate() -> None:
    consolidator = Consolidator()
    candidate = consolidator.from_validated_abstraction(
        candidate_id="wb-2",
        task_id="task-1",
        abstraction="Prefer dependency inversion for this interface family",
        source_refs=["evt-2"],
        is_validated=True,
        is_speculative=False,
    )

    assert candidate is not None
    assert candidate.target_domain == MemoryDomain.SEMANTIC


def test_speculative_lesson_is_blocked_from_semantic_auto_write() -> None:
    consolidator = Consolidator()
    candidate = consolidator.from_validated_abstraction(
        candidate_id="wb-3",
        task_id="task-1",
        abstraction="Maybe this always works",
        source_refs=["evt-3"],
        is_validated=True,
        is_speculative=True,
    )

    assert candidate is None


def test_transient_user_context_is_blocked_from_durable_user_write() -> None:
    consolidator = Consolidator()
    candidate = consolidator.from_user_finding(
        candidate_id="wb-4",
        task_id="task-1",
        statement="Use short answers in this one message",
        source_refs=["evt-4"],
        is_durable=False,
        is_validated=True,
        is_speculative=False,
    )

    assert candidate is None


def test_temporal_validity_fields_are_preserved_when_present() -> None:
    consolidator = Consolidator()
    valid_from = datetime.now(UTC)
    valid_to = datetime(2030, 1, 1, tzinfo=UTC)
    candidate = consolidator.from_user_finding(
        candidate_id="wb-5",
        task_id="task-1",
        statement="No calls after 6pm local time",
        source_refs=["evt-5"],
        is_durable=True,
        is_validated=True,
        is_speculative=False,
        valid_from=valid_from,
        valid_to=valid_to,
    )

    assert candidate is not None
    assert candidate.validity_window is not None
    assert candidate.validity_window.valid_from == valid_from
    assert candidate.validity_window.valid_to == valid_to


def test_no_direct_semantic_or_user_commit_from_consolidation() -> None:
    consolidator = Consolidator()
    sem = consolidator.from_validated_abstraction(
        candidate_id="wb-6",
        task_id="task-1",
        abstraction="Validated pattern",
        source_refs=["evt-6"],
        is_validated=True,
        is_speculative=False,
    )
    user = consolidator.from_user_finding(
        candidate_id="wb-7",
        task_id="task-1",
        statement="Always prefer markdown",
        source_refs=["evt-7"],
        is_durable=True,
        is_validated=True,
        is_speculative=False,
    )

    assert sem is not None and sem.status == CommitStatus.CANDIDATE
    assert user is not None and user.status == CommitStatus.CANDIDATE
