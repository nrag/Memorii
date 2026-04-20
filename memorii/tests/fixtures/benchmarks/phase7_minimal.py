"""Phase 7 deterministic benchmark fixture set."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.models import (
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    EndToEndFixture,
    ExecutionResumeFixture,
    RetrievalFixture,
    RetrievalFixtureMemoryItem,
    RoutingFixture,
    SolverResumeFixture,
    SolverValidationFixture,
)
from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope
from memorii.domain.routing import InboundEvent, InboundEventClass


def load_phase7_fixture_set() -> list[BenchmarkScenarioFixture]:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    retrieval_corpus = [
        RetrievalFixtureMemoryItem(
            item_id="tx:err",
            domain=MemoryDomain.TRANSCRIPT,
            text="failing test stack trace null pointer",
            task_id="task:1",
            execution_node_id="exec:1",
        ),
        RetrievalFixtureMemoryItem(
            item_id="sem:speculative",
            domain=MemoryDomain.SEMANTIC,
            text="unvalidated guess maybe root cause",
            task_id="task:1",
        ),
        RetrievalFixtureMemoryItem(
            item_id="sem:fact",
            domain=MemoryDomain.SEMANTIC,
            text="null pointer occurs when dependency uninitialized",
            task_id="task:1",
        ),
        RetrievalFixtureMemoryItem(
            item_id="epi:case",
            domain=MemoryDomain.EPISODIC,
            text="prior case solved by adding dependency guard",
            task_id="task:1",
            execution_node_id="exec:1",
        ),
        RetrievalFixtureMemoryItem(
            item_id="tx:other",
            domain=MemoryDomain.TRANSCRIPT,
            text="unrelated chat about deployment",
            task_id="task:2",
        ),
    ]

    routing_event = InboundEvent(
        event_id="evt:tool:failed",
        event_class=InboundEventClass.TOOL_RESULT,
        task_id="task:1",
        execution_node_id="exec:1",
        solver_run_id="solver:1",
        payload={"status": "failed", "message": "test failed"},
        timestamp=now,
    )

    return [
        BenchmarkScenarioFixture(
            scenario_id="retrieval_transcript_verbatim",
            category=BenchmarkScenarioType.TRANSCRIPT_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="failing test stack trace",
                intent=RetrievalIntent.RESUME_TASK,
                scope=RetrievalScope(task_id="task:1", execution_node_id="exec:1"),
                top_k=2,
                corpus=retrieval_corpus,
                expected_relevant_ids=["tx:err"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="retrieval_semantic_validated",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="null pointer dependency uninitialized",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(task_id="task:1", execution_node_id="exec:1"),
                top_k=2,
                corpus=retrieval_corpus,
                expected_relevant_ids=["sem:fact"],
                expected_excluded_ids=["sem:speculative"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="retrieval_episodic_prior_case",
            category=BenchmarkScenarioType.EPISODIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="prior case dependency guard",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(task_id="task:1", execution_node_id="exec:1"),
                top_k=2,
                corpus=retrieval_corpus,
                expected_relevant_ids=["epi:case"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="routing_failed_tool_result",
            category=BenchmarkScenarioType.ROUTING_CORRECTNESS,
            routing=RoutingFixture(
                inbound_event=routing_event,
                expected_domains=[MemoryDomain.EXECUTION, MemoryDomain.SOLVER, MemoryDomain.TRANSCRIPT],
                expected_blocked_domains=[],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="resume_execution_state",
            category=BenchmarkScenarioType.EXECUTION_RESUME,
            execution_resume=ExecutionResumeFixture(
                task_id="task:1",
                expected_node_ids=["exec:1", "exec:2"],
                expected_status_by_node={"exec:1": "RUNNING", "exec:2": "BLOCKED"},
                include_blocked_node=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="resume_solver_frontier",
            category=BenchmarkScenarioType.SOLVER_RESUME,
            solver_resume=SolverResumeFixture(
                solver_run_id="solver:1",
                execution_node_id="exec:1",
                expected_frontier=["q:1"],
                expected_unresolved_questions=["q:1"],
                expected_reopenable_branches=["q:1"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="solver_validation_downgrade",
            category=BenchmarkScenarioType.SOLVER_VALIDATION,
            solver_validation=SolverValidationFixture(
                decision="SUPPORTED",
                evidence_ids=[],
                available_evidence_ids={"obs:1"},
                expect_downgrade=True,
                expect_invalid_rejection=False,
                expect_abstention_preserved=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="e2e_fail_debug_resolve",
            category=BenchmarkScenarioType.END_TO_END,
            routing=RoutingFixture(
                inbound_event=routing_event,
                expected_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER],
                expected_blocked_domains=[],
            ),
            end_to_end=EndToEndFixture(
                task_id="task:1",
                expect_pipeline_success=True,
                expect_writeback_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION],
            ),
        ),
    ]
