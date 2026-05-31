"""Memory Lifecycle Benchmark v1 fixture set."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.models import (
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    ConflictCandidate,
    ConflictResolutionFixture,
    EndToEndFixture,
    ImplicitRecallFixture,
    LearningAcrossEpisodesFixture,
    LongHorizonDegradationFixture,
    MemoryLifecycleExpectation,
    MemoryLifecycleFamily,
    RetrievalFixture,
    RetrievalFixtureMemoryItem,
    RoutingFixture,
    WorkspaceLifecycleStage,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, TemporalValidityStatus
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope
from memorii.domain.routing import InboundEvent, InboundEventClass


def load_memory_lifecycle_v1_fixture_set() -> list[BenchmarkScenarioFixture]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    noisy_tool_event = InboundEvent(
        event_id="evt:lifecycle:tool-noise",
        event_class=InboundEventClass.TOOL_STATE_UPDATE,
        task_id="task:lifecycle-noise",
        payload={"status": "failed", "message": "retry retry null null temporary debug noise"},
        timestamp=now,
    )
    lifecycle_noise = [
        RetrievalFixtureMemoryItem(
            item_id=f"life:noise:{index:02d}",
            domain=MemoryDomain.TRANSCRIPT,
            text=f"unrelated lifecycle chatter {index}",
            task_id="task:lifecycle",
        )
        for index in range(1, 49)
    ]

    return [
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_create_and_reuse_user_preference",
            category=BenchmarkScenarioType.LEARNING_ACROSS_EPISODES,
            learning_across_episodes=LearningAcrossEpisodesFixture(
                episode_two_query="concise coding answer preference",
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:user:concise-coding",
                        domain=MemoryDomain.USER,
                        text="User prefers concise coding answers.",
                        task_id="task:lifecycle",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="tx:formatting-noise",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="User asked whether formatting looked okay.",
                        task_id="task:lifecycle",
                    ),
                ],
                expected_reuse_id="mem:user:concise-coding",
                baseline_without_reuse_retrieved_ids=["tx:formatting-noise"],
                episode_one_writeback_domains=[MemoryDomain.USER, MemoryDomain.TRANSCRIPT],
                expected_writeback_domain=MemoryDomain.USER,
                expected_writeback_domains=[MemoryDomain.USER],
                expected_writeback_candidate_ids=["wb:learning:mem:user:concise-coding"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.CREATE_AND_REUSE_USER_PREFERENCE,
                expected_stage_by_memory_id={"mem:user:concise-coding": WorkspaceLifecycleStage.AREA},
                expected_active_memory_ids=["mem:user:concise-coding"],
                expected_retrieval_ids=["mem:user:concise-coding"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_block_inferred_user_preference",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="examples when learning new APIs",
                intent=RetrievalIntent.ANSWER_WITH_USER_CONTEXT,
                scope=RetrievalScope(user_id="user:lifecycle"),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="tx:concise-once",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="In one chat the user asked for a concise answer.",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:user:explicit-style",
                        domain=MemoryDomain.USER,
                        text="User explicitly prefers examples when learning new APIs.",
                    ),
                ],
                expected_relevant_ids=["mem:user:explicit-style"],
                expected_excluded_ids=["tx:concise-once"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.BLOCK_INFERRED_USER_PREFERENCE,
                expected_retrieval_ids=["mem:user:explicit-style"],
                expected_excluded_retrieval_ids=["tx:concise-once"],
                expect_pollution_avoidance=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_merge_near_duplicate_preference",
            category=BenchmarkScenarioType.CONFLICT_RESOLUTION,
            conflict_resolution=ConflictResolutionFixture(
                candidates=[
                    ConflictCandidate(
                        candidate_id="mem:user:concise-direct",
                        recency_rank=3,
                        validity_status="active",
                        preferred=True,
                        version=4,
                    ),
                    ConflictCandidate(
                        candidate_id="cand:user:brief-direct-duplicate",
                        recency_rank=4,
                        validity_status="invalidated",
                        preferred=False,
                        version=3,
                    ),
                ],
                expected_winner_candidate_id="mem:user:concise-direct",
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.MERGE_NEAR_DUPLICATE_PREFERENCE,
                expected_active_memory_ids=["mem:user:concise-direct"],
                expected_inactive_memory_ids=["cand:user:brief-direct-duplicate"],
                expect_duplicate_avoidance=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_supersede_corrected_preference",
            category=BenchmarkScenarioType.CONFLICT_RESOLUTION,
            conflict_resolution=ConflictResolutionFixture(
                candidates=[
                    ConflictCandidate(
                        candidate_id="mem:user:detailed-default",
                        recency_rank=1,
                        validity_status="invalidated",
                        preferred=False,
                        version=1,
                    ),
                    ConflictCandidate(
                        candidate_id="mem:user:concise-coding",
                        recency_rank=3,
                        validity_status="active",
                        preferred=True,
                        version=3,
                    ),
                ],
                expected_winner_candidate_id="mem:user:concise-coding",
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.SUPERSEDE_CORRECTED_PREFERENCE,
                expected_stage_by_memory_id={"mem:user:detailed-default": WorkspaceLifecycleStage.ARCHIVE},
                expected_active_memory_ids=["mem:user:concise-coding"],
                expected_inactive_memory_ids=["mem:user:detailed-default"],
                expected_archived_memory_ids=["mem:user:detailed-default"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_preserve_task_scoped_preference",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="generally concise direct answers",
                intent=RetrievalIntent.ANSWER_WITH_USER_CONTEXT,
                scope=RetrievalScope(user_id="user:lifecycle"),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:task:verbose-pr",
                        domain=MemoryDomain.USER,
                        text="For PR 84 only, user wants very verbose review comments.",
                        task_id="task:pr-84",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:user:concise-global",
                        domain=MemoryDomain.USER,
                        text="User generally prefers concise direct answers.",
                    ),
                ],
                expected_relevant_ids=["mem:user:concise-global"],
                expected_excluded_ids=["mem:task:verbose-pr"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.PRESERVE_TASK_SCOPED_PREFERENCE,
                expected_retrieval_ids=["mem:user:concise-global"],
                expected_excluded_retrieval_ids=["mem:task:verbose-pr"],
                expect_scope_preservation=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_promote_repeated_project_fact",
            category=BenchmarkScenarioType.LEARNING_ACROSS_EPISODES,
            learning_across_episodes=LearningAcrossEpisodesFixture(
                episode_two_query="Friday release freeze current sprint",
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:project:friday-freeze",
                        domain=MemoryDomain.SEMANTIC,
                        text="Project release freeze happens every Friday in recent sprints.",
                        task_id="task:release",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="tx:standup",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="Standup mentioned release checklist.",
                        task_id="task:release",
                    ),
                ],
                expected_reuse_id="mem:project:friday-freeze",
                baseline_without_reuse_retrieved_ids=["tx:standup"],
                episode_one_writeback_domains=[MemoryDomain.SEMANTIC],
                expected_writeback_domain=MemoryDomain.SEMANTIC,
                expected_writeback_domains=[MemoryDomain.SEMANTIC],
                expected_writeback_candidate_ids=["wb:learning:mem:project:friday-freeze"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.PROMOTE_REPEATED_PROJECT_FACT,
                expected_stage_by_memory_id={"mem:project:friday-freeze": WorkspaceLifecycleStage.PROJECT},
                expected_active_memory_ids=["mem:project:friday-freeze"],
                expected_retrieval_ids=["mem:project:friday-freeze"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_supersede_stale_project_fact",
            category=BenchmarkScenarioType.CONFLICT_RESOLUTION,
            conflict_resolution=ConflictResolutionFixture(
                candidates=[
                    ConflictCandidate(
                        candidate_id="mem:project:manual-qa-gate",
                        recency_rank=1,
                        validity_status="invalidated",
                        preferred=False,
                        version=1,
                    ),
                    ConflictCandidate(
                        candidate_id="mem:project:automated-quality-gate",
                        recency_rank=4,
                        validity_status="active",
                        preferred=True,
                        version=4,
                    ),
                ],
                expected_winner_candidate_id="mem:project:automated-quality-gate",
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.SUPERSEDE_STALE_PROJECT_FACT,
                expected_active_memory_ids=["mem:project:automated-quality-gate"],
                expected_inactive_memory_ids=["mem:project:manual-qa-gate"],
                expected_archived_memory_ids=["mem:project:manual-qa-gate"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_avoid_wrong_entity_carryover",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="Apex specific evidence not confirmed",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:customer:apex-unknown",
                        domain=MemoryDomain.SEMANTIC,
                        text="Apex rollout requirement is not confirmed yet; ask for Apex-specific evidence.",
                        entity_tags=["Apex"],
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:customer:acme-soc2",
                        domain=MemoryDomain.SEMANTIC,
                        text="ACME requires SOC2 review before rollout.",
                        entity_tags=["ACME"],
                    ),
                ],
                expected_relevant_ids=["mem:customer:apex-unknown"],
                expected_excluded_ids=["mem:customer:acme-soc2"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.AVOID_WRONG_ENTITY_CARRYOVER,
                expected_retrieval_ids=["mem:customer:apex-unknown"],
                expected_excluded_retrieval_ids=["mem:customer:acme-soc2"],
                expect_pollution_avoidance=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_retrieval_after_expiration",
            category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
            long_horizon_degradation=LongHorizonDegradationFixture(
                early_retrieval=RetrievalFixture(
                    query="release freeze applies this sprint",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                    scope=RetrievalScope(task_id="task:release"),
                    top_k=2,
                    corpus=[
                        RetrievalFixtureMemoryItem(
                            item_id="mem:project:freeze-current",
                            domain=MemoryDomain.SEMANTIC,
                            text="Release freeze applies this sprint.",
                            task_id="task:release",
                        ),
                        *lifecycle_noise[:10],
                    ],
                    expected_relevant_ids=["mem:project:freeze-current"],
                ),
                delayed_retrieval=RetrievalFixture(
                    query="active release freeze current sprint",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                    scope=RetrievalScope(task_id="task:release"),
                    top_k=2,
                    corpus=[
                        RetrievalFixtureMemoryItem(
                            item_id="mem:project:freeze-expired",
                            domain=MemoryDomain.SEMANTIC,
                            text="Release freeze applied last sprint.",
                            task_id="task:release",
                            validity_status=TemporalValidityStatus.EXPIRED,
                        ),
                        RetrievalFixtureMemoryItem(
                            item_id="mem:project:no-current-freeze",
                            domain=MemoryDomain.SEMANTIC,
                            text="No active release freeze applies this sprint.",
                            task_id="task:release",
                        ),
                        *lifecycle_noise,
                    ],
                    expected_relevant_ids=["mem:project:no-current-freeze"],
                    expected_excluded_ids=["mem:project:freeze-expired"],
                ),
                noise_ids=[item.item_id for item in lifecycle_noise],
                delayed_depends_on_early_context=True,
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.RETRIEVAL_AFTER_EXPIRATION,
                expected_retrieval_ids=["mem:project:no-current-freeze"],
                expected_excluded_retrieval_ids=["mem:project:freeze-expired"],
                expected_archived_memory_ids=["mem:project:freeze-expired"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_end_to_end_with_noise",
            category=BenchmarkScenarioType.IMPLICIT_RECALL,
            implicit_recall=ImplicitRecallFixture(
                query="current coding answer preference",
                context_tokens=["corrected", "preference", "coding", "current"],
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:user:concise-coding-current",
                        domain=MemoryDomain.USER,
                        text="Current corrected preference: user wants concise coding answers.",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:user:detailed-old",
                        domain=MemoryDomain.USER,
                        text="Old superseded preference: user wants detailed answers by default.",
                        status=CommitStatus.ARCHIVED,
                        validity_status=TemporalValidityStatus.INVALIDATED,
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="tx:debug-noise",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="retry retry null null temporary debug log noise",
                    ),
                ],
                relevant_ids=["mem:user:concise-coding-current"],
                relevant_memory_texts=["Current corrected preference: user wants concise coding answers."],
                lexical_overlap_score=0.2,
                expected_domains=[],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.END_TO_END_LIFECYCLE_WITH_NOISE,
                expected_active_memory_ids=["mem:user:concise-coding-current"],
                expected_inactive_memory_ids=["mem:user:detailed-old", "tx:debug-noise"],
                expected_retrieval_ids=["mem:user:concise-coding-current"],
                expected_excluded_retrieval_ids=["mem:user:detailed-old", "tx:debug-noise"],
                expect_pollution_avoidance=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_end_to_end_noise_pipeline",
            category=BenchmarkScenarioType.END_TO_END,
            retrieval=RetrievalFixture(
                query="current corrected coding answer preference",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(task_id="task:lifecycle-noise"),
                top_k=4,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="tx:lifecycle-noise",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="retry retry null null temporary debug noise",
                        task_id="task:lifecycle-noise",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="sem:lifecycle-current",
                        domain=MemoryDomain.SEMANTIC,
                        text="Current corrected coding answer preference is concise.",
                        task_id="task:lifecycle-noise",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="epi:lifecycle-correction",
                        domain=MemoryDomain.EPISODIC,
                        text="User corrected old detailed-answer preference during the coding task.",
                        task_id="task:lifecycle-noise",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="sem:lifecycle-old",
                        domain=MemoryDomain.SEMANTIC,
                        text="Old superseded answer preference was detailed by default.",
                        task_id="task:lifecycle-noise",
                        validity_status=TemporalValidityStatus.INVALIDATED,
                    ),
                ],
                expected_relevant_ids=["sem:lifecycle-current", "epi:lifecycle-correction"],
                expected_excluded_ids=["sem:lifecycle-old"],
            ),
            routing=RoutingFixture(
                inbound_event=noisy_tool_event,
                expected_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER],
                expected_blocked_domains=[],
            ),
            end_to_end=EndToEndFixture(
                task_id="task:lifecycle-noise",
                expect_pipeline_success=True,
                expect_writeback_domains=[MemoryDomain.EPISODIC],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.END_TO_END_LIFECYCLE_WITH_NOISE,
                expected_active_memory_ids=["sem:lifecycle-current", "epi:lifecycle-correction"],
                expected_inactive_memory_ids=["sem:lifecycle-old"],
                expected_retrieval_ids=["sem:lifecycle-current", "epi:lifecycle-correction"],
                expected_excluded_retrieval_ids=["sem:lifecycle-old"],
                expect_pollution_avoidance=True,
            ),
        ),
    ]
