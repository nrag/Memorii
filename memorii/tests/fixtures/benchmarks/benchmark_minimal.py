"""Deterministic benchmark fixture set."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.models import (
    BenchmarkSystem,
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    BaselineApplicability,
    BaselinePolicy,
    ConflictCandidate,
    ConflictResolutionFixture,
    EndToEndFixture,
    ExecutionResumeFixture,
    ImplicitRecallFixture,
    LearningAcrossEpisodesFixture,
    LongHorizonDegradationFixture,
    RetrievalFixture,
    RetrievalFixtureMemoryItem,
    RoutingFixture,
    SolverResumeFixture,
    SolverValidationFixture,
)
from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope
from memorii.domain.routing import InboundEvent, InboundEventClass


def load_benchmark_fixture_set() -> list[BenchmarkScenarioFixture]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    long_horizon_noise_items = [
        RetrievalFixtureMemoryItem(
            item_id=f"tx:noise:{index:02d}",
            domain=MemoryDomain.TRANSCRIPT,
            text=f"irrelevant chatter entry {index}",
            task_id="task:3",
        )
        for index in range(1, 48)
    ]
    long_horizon_delayed_corpus = [
        RetrievalFixtureMemoryItem(
            item_id="tx:key",
            domain=MemoryDomain.TRANSCRIPT,
            text="service token rotates at midnight",
            task_id="task:3",
        ),
        RetrievalFixtureMemoryItem(
            item_id="sem:key",
            domain=MemoryDomain.SEMANTIC,
            text="rotation policy token midnight schedule",
            task_id="task:3",
        ),
        RetrievalFixtureMemoryItem(
            item_id="epi:key",
            domain=MemoryDomain.EPISODIC,
            text="last incident fixed by midnight token rotation check",
            task_id="task:3",
        ),
        *long_horizon_noise_items,
    ]
    long_horizon_early_corpus = [
        RetrievalFixtureMemoryItem(
            item_id="tx:key",
            domain=MemoryDomain.TRANSCRIPT,
            text="service token rotates at midnight",
            task_id="task:3",
        ),
        *long_horizon_noise_items[:10],
    ]

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
        event_class=InboundEventClass.TOOL_STATE_UPDATE,
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
            retrieval=RetrievalFixture(
                query="failing test stack trace",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(task_id="task:1"),
                top_k=4,
                corpus=retrieval_corpus,
                expected_relevant_ids=["tx:err", "sem:fact", "epi:case"],
                expected_excluded_ids=["sem:speculative"],
            ),
            routing=RoutingFixture(
                inbound_event=routing_event,
                expected_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER],
                expected_blocked_domains=[],
            ),
            end_to_end=EndToEndFixture(
                task_id="task:1",
                expect_pipeline_success=True,
                expect_writeback_domains=[MemoryDomain.EPISODIC],
                expect_writeback_candidate_ids=["wb:solver:task:1:exec:task:1:root:evt:tool:failed"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="learning_reuse_preference",
            category=BenchmarkScenarioType.LEARNING_ACROSS_EPISODES,
            learning_across_episodes=LearningAcrossEpisodesFixture(
                episode_two_query="format using concise bullet points",
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="pref:bullets",
                        domain=MemoryDomain.USER,
                        text="format using concise bullet points for user responses",
                        task_id="task:1",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="tx:style",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="latest chat asks for formatting style",
                        task_id="task:1",
                    ),
                ],
                expected_reuse_id="pref:bullets",
                baseline_without_reuse_retrieved_ids=["tx:style"],
                episode_one_writeback_domains=[MemoryDomain.USER, MemoryDomain.TRANSCRIPT],
                expected_writeback_domain=MemoryDomain.USER,
                expected_writeback_domains=[MemoryDomain.USER],
                expected_writeback_candidate_ids=["wb:learning:pref:bullets"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="long_horizon_noise_and_delay",
            category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
            long_horizon_degradation=LongHorizonDegradationFixture(
                early_retrieval=RetrievalFixture(
                    query="service token rotates at midnight",
                    intent=RetrievalIntent.RESUME_TASK,
                    scope=RetrievalScope(task_id="task:3"),
                    top_k=2,
                    corpus=long_horizon_early_corpus,
                    expected_relevant_ids=["tx:key"],
                ),
                delayed_retrieval=RetrievalFixture(
                    query="what token schedule applies now",
                    intent=RetrievalIntent.RESUME_TASK,
                    scope=RetrievalScope(task_id="task:3"),
                    top_k=3,
                    corpus=long_horizon_delayed_corpus,
                    expected_relevant_ids=["tx:key", "sem:key", "epi:key"],
                ),
                noise_ids=[item.item_id for item in long_horizon_noise_items],
                delayed_depends_on_early_context=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="conflict_newer_fact_wins",
            category=BenchmarkScenarioType.CONFLICT_RESOLUTION,
            conflict_resolution=ConflictResolutionFixture(
                candidates=[
                    ConflictCandidate(
                        candidate_id="fact:old",
                        recency_rank=1,
                        validity_status="active",
                        version=1,
                        preferred=False,
                    ),
                    ConflictCandidate(
                        candidate_id="fact:new",
                        recency_rank=3,
                        validity_status="active",
                        version=3,
                        preferred=True,
                    ),
                    ConflictCandidate(
                        candidate_id="fact:stale",
                        recency_rank=4,
                        validity_status="expired",
                        version=4,
                        preferred=False,
                    ),
                ]
                ,
                expected_winner_candidate_id="fact:new",
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="implicit_recall_structural_match",
            category=BenchmarkScenarioType.IMPLICIT_RECALL,
            implicit_recall=ImplicitRecallFixture(
                query="prepare handoff notes for next sprint",
                context_tokens=["retrospective", "handoff", "timeline"],
                top_k=2,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="epi:handoff",
                        domain=MemoryDomain.EPISODIC,
                        text="retrospective timeline for sprint transition checklist",
                        task_id="task:9",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="tx:keywords",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="handoff notes general template",
                        task_id="task:9",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="tx:noise",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="shopping reminder unrelated",
                        task_id="task:9",
                    ),
                ],
                relevant_ids=["epi:handoff"],
                relevant_memory_texts=["retrospective timeline for sprint transition checklist"],
                lexical_overlap_score=0.18,
                expected_domains=[MemoryDomain.EPISODIC, MemoryDomain.TRANSCRIPT],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="implicit_recall_solver_baseline_skip",
            category=BenchmarkScenarioType.IMPLICIT_RECALL,
            implicit_recall=ImplicitRecallFixture(
                query="link stale assumption to latest evidence",
                context_tokens=["assumption", "evidence", "invalidated"],
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="sol:stale-assumption",
                        domain=MemoryDomain.SOLVER,
                        text="prior assumption invalidated by latest benchmark evidence",
                        task_id="task:10",
                        solver_run_id="solver:10",
                    )
                ],
                relevant_ids=["sol:stale-assumption"],
                relevant_memory_texts=["prior assumption invalidated by latest benchmark evidence"],
                lexical_overlap_score=0.2,
                expected_domains=[MemoryDomain.SOLVER],
            ),
            baseline_applicability={
                BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE: BaselineApplicability(
                    policy=BaselinePolicy.SKIP,
                    skip_reason="Transcript-only baseline is not meaningful for solver-only implicit recall.",
                )
            },
        ),
    ]
