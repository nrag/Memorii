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
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_multi_event_create_update_invalidate_retrieve",
            category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
            long_horizon_degradation=LongHorizonDegradationFixture(
                early_retrieval=RetrievalFixture(
                    query="Atlas deploys use manual QA gate",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                    scope=RetrievalScope(task_id="task:atlas-deploy"),
                    top_k=1,
                    corpus=[
                        RetrievalFixtureMemoryItem(
                            item_id="mem:atlas:manual-qa-gate",
                            domain=MemoryDomain.SEMANTIC,
                            text="Atlas deploys use a manual QA gate before release.",
                            task_id="task:atlas-deploy",
                        ),
                    ],
                    expected_relevant_ids=["mem:atlas:manual-qa-gate"],
                ),
                delayed_retrieval=RetrievalFixture(
                    query="Atlas deploys current automated canary gate",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                    scope=RetrievalScope(task_id="task:atlas-deploy"),
                    top_k=1,
                    corpus=[
                        RetrievalFixtureMemoryItem(
                            item_id="mem:atlas:manual-qa-gate",
                            domain=MemoryDomain.SEMANTIC,
                            text="Atlas deploys use a manual QA gate before release.",
                            task_id="task:atlas-deploy",
                            validity_status=TemporalValidityStatus.INVALIDATED,
                        ),
                        RetrievalFixtureMemoryItem(
                            item_id="mem:atlas:automated-canary-gate",
                            domain=MemoryDomain.SEMANTIC,
                            text="Current Atlas deploys use an automated canary gate before release.",
                            task_id="task:atlas-deploy",
                        ),
                        *lifecycle_noise,
                    ],
                    expected_relevant_ids=["mem:atlas:automated-canary-gate"],
                    expected_excluded_ids=["mem:atlas:manual-qa-gate"],
                ),
                noise_ids=[item.item_id for item in lifecycle_noise],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.MULTI_EVENT_CREATE_UPDATE_INVALIDATE_RETRIEVE,
                expected_active_memory_ids=["mem:atlas:automated-canary-gate"],
                expected_inactive_memory_ids=["mem:atlas:manual-qa-gate"],
                expected_archived_memory_ids=["mem:atlas:manual-qa-gate"],
                expected_retrieval_ids=["mem:atlas:automated-canary-gate"],
                expected_excluded_retrieval_ids=["mem:atlas:manual-qa-gate"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_merge_with_provenance_link",
            category=BenchmarkScenarioType.CONFLICT_RESOLUTION,
            conflict_resolution=ConflictResolutionFixture(
                candidates=[
                    ConflictCandidate(
                        candidate_id="mem:user:review-style-linked",
                        recency_rank=5,
                        validity_status="active",
                        preferred=True,
                        version=5,
                    ),
                    ConflictCandidate(
                        candidate_id="cand:user:review-style-duplicate-from-session",
                        recency_rank=4,
                        validity_status="invalidated",
                        preferred=False,
                        version=4,
                    ),
                    ConflictCandidate(
                        candidate_id="cand:user:review-style-duplicate-from-pr",
                        recency_rank=3,
                        validity_status="invalidated",
                        preferred=False,
                        version=3,
                    ),
                ],
                expected_winner_candidate_id="mem:user:review-style-linked",
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.MERGE_WITH_PROVENANCE_LINK,
                expected_active_memory_ids=["mem:user:review-style-linked"],
                expected_inactive_memory_ids=[
                    "cand:user:review-style-duplicate-from-session",
                    "cand:user:review-style-duplicate-from-pr",
                ],
                expect_duplicate_avoidance=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_split_memory_by_entity",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="Atlas billing owner and Beacon export owner",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(),
                top_k=2,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:combined:atlas-beacon-owners",
                        domain=MemoryDomain.SEMANTIC,
                        text="Atlas and Beacon owners were previously combined in one memory.",
                        entity_tags=["Atlas", "Beacon"],
                        validity_status=TemporalValidityStatus.INVALIDATED,
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:atlas:billing-owner",
                        domain=MemoryDomain.SEMANTIC,
                        text="Atlas billing owner is Priya.",
                        entity_tags=["Atlas"],
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:beacon:export-owner",
                        domain=MemoryDomain.SEMANTIC,
                        text="Beacon export owner is Mateo.",
                        entity_tags=["Beacon"],
                    ),
                ],
                expected_relevant_ids=["mem:atlas:billing-owner", "mem:beacon:export-owner"],
                expected_excluded_ids=["mem:combined:atlas-beacon-owners"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.SPLIT_MEMORY_BY_ENTITY,
                expected_active_memory_ids=["mem:atlas:billing-owner", "mem:beacon:export-owner"],
                expected_inactive_memory_ids=["mem:combined:atlas-beacon-owners"],
                expected_retrieval_ids=["mem:atlas:billing-owner", "mem:beacon:export-owner"],
                expected_excluded_retrieval_ids=["mem:combined:atlas-beacon-owners"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_belief_dependency_invalidation",
            category=BenchmarkScenarioType.IMPLICIT_RECALL,
            implicit_recall=ImplicitRecallFixture(
                query="current confidence in rollout risk chain after upstream falsified",
                context_tokens=["falsified", "dependency", "confidence", "degraded", "rollout"],
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="belief:rollout:downstream-degraded",
                        domain=MemoryDomain.SOLVER,
                        text="Upstream premise A was falsified, so dependent beliefs B and C are degraded and need retest.",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="belief:rollout:downstream-confident",
                        domain=MemoryDomain.SOLVER,
                        text="Dependent belief C remains high confidence because B supported it earlier.",
                        validity_status=TemporalValidityStatus.INVALIDATED,
                    ),
                ],
                relevant_ids=["belief:rollout:downstream-degraded"],
                relevant_memory_texts=[
                    "Upstream premise A was falsified, so dependent beliefs B and C are degraded and need retest."
                ],
                lexical_overlap_score=0.15,
                expected_domains=[MemoryDomain.SOLVER],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.BELIEF_DEPENDENCY_INVALIDATION,
                expected_active_memory_ids=["belief:rollout:downstream-degraded"],
                expected_inactive_memory_ids=["belief:rollout:downstream-confident"],
                expected_retrieval_ids=["belief:rollout:downstream-degraded"],
                expected_excluded_retrieval_ids=["belief:rollout:downstream-confident"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_source_trust_conflict",
            category=BenchmarkScenarioType.CONFLICT_RESOLUTION,
            conflict_resolution=ConflictResolutionFixture(
                candidates=[
                    ConflictCandidate(
                        candidate_id="mem:deploy:transcript-staging",
                        recency_rank=4,
                        validity_status="active",
                        preferred=False,
                        version=1,
                    ),
                    ConflictCandidate(
                        candidate_id="mem:deploy:tool-prod",
                        recency_rank=3,
                        validity_status="active",
                        preferred=False,
                        version=2,
                    ),
                    ConflictCandidate(
                        candidate_id="mem:deploy:user-correction-prod-readonly",
                        recency_rank=2,
                        validity_status="active",
                        preferred=False,
                        version=3,
                    ),
                    ConflictCandidate(
                        candidate_id="mem:deploy:verified-prod-readonly",
                        recency_rank=1,
                        validity_status="active",
                        preferred=True,
                        version=4,
                    ),
                ],
                expected_winner_candidate_id="mem:deploy:verified-prod-readonly",
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.SOURCE_TRUST_CONFLICT,
                expected_active_memory_ids=["mem:deploy:verified-prod-readonly"],
                expected_inactive_memory_ids=[
                    "mem:deploy:transcript-staging",
                    "mem:deploy:tool-prod",
                    "mem:deploy:user-correction-prod-readonly",
                ],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_expire_and_archive_over_time",
            category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
            long_horizon_degradation=LongHorizonDegradationFixture(
                early_retrieval=RetrievalFixture(
                    query="temporary demo token valid today",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                    scope=RetrievalScope(task_id="task:demo"),
                    top_k=1,
                    corpus=[
                        RetrievalFixtureMemoryItem(
                            item_id="mem:demo:temporary-token",
                            domain=MemoryDomain.SEMANTIC,
                            text="Temporary demo token is valid today.",
                            task_id="task:demo",
                        ),
                    ],
                    expected_relevant_ids=["mem:demo:temporary-token"],
                ),
                delayed_retrieval=RetrievalFixture(
                    query="current demo auth method after token expiry",
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                    scope=RetrievalScope(task_id="task:demo"),
                    top_k=1,
                    corpus=[
                        RetrievalFixtureMemoryItem(
                            item_id="mem:demo:temporary-token",
                            domain=MemoryDomain.SEMANTIC,
                            text="Temporary demo token was valid yesterday.",
                            task_id="task:demo",
                            validity_status=TemporalValidityStatus.EXPIRED,
                        ),
                        RetrievalFixtureMemoryItem(
                            item_id="mem:demo:use-oauth",
                            domain=MemoryDomain.SEMANTIC,
                            text="Current demo auth method is OAuth.",
                            task_id="task:demo",
                        ),
                        *lifecycle_noise,
                    ],
                    expected_relevant_ids=["mem:demo:use-oauth"],
                    expected_excluded_ids=["mem:demo:temporary-token"],
                ),
                noise_ids=[item.item_id for item in lifecycle_noise],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.EXPIRE_AND_ARCHIVE_OVER_TIME,
                expected_active_memory_ids=["mem:demo:use-oauth"],
                expected_inactive_memory_ids=["mem:demo:temporary-token"],
                expected_archived_memory_ids=["mem:demo:temporary-token"],
                expected_retrieval_ids=["mem:demo:use-oauth"],
                expected_excluded_retrieval_ids=["mem:demo:temporary-token"],
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_task_scoped_does_not_overwrite_global",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="outside PR 84 general review answer preference",
                intent=RetrievalIntent.ANSWER_WITH_USER_CONTEXT,
                scope=RetrievalScope(user_id="user:lifecycle"),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:task:pr84-verbose-review",
                        domain=MemoryDomain.USER,
                        text="For PR 84 only, user wants exhaustive review comments.",
                        task_id="task:pr-84",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:user:review-concise-global",
                        domain=MemoryDomain.USER,
                        text="Outside a specific task, user prefers concise review answers.",
                    ),
                ],
                expected_relevant_ids=["mem:user:review-concise-global"],
                expected_excluded_ids=["mem:task:pr84-verbose-review"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.TASK_SCOPED_DOES_NOT_OVERWRITE_GLOBAL,
                expected_retrieval_ids=["mem:user:review-concise-global"],
                expected_excluded_retrieval_ids=["mem:task:pr84-verbose-review"],
                expect_scope_preservation=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_near_match_validity_distractor",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="current Orion billing migration owner",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:orion:billing-owner-current",
                        domain=MemoryDomain.SEMANTIC,
                        text="Current Orion billing migration owner is Nadia.",
                        entity_tags=["Orion"],
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:orion:billing-owner-old",
                        domain=MemoryDomain.SEMANTIC,
                        text="Old Orion billing migration owner was Nikhil.",
                        entity_tags=["Orion"],
                        validity_status=TemporalValidityStatus.INVALIDATED,
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:orion:billing-api-owner",
                        domain=MemoryDomain.SEMANTIC,
                        text="Orion billing API owner is Nikhil.",
                        entity_tags=["Orion"],
                    ),
                ],
                expected_relevant_ids=["mem:orion:billing-owner-current"],
                expected_excluded_ids=[
                    "mem:orion:billing-owner-old",
                    "mem:orion:billing-api-owner",
                ],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.NEAR_MATCH_VALIDITY_DISTRACTOR,
                expected_retrieval_ids=["mem:orion:billing-owner-current"],
                expected_excluded_retrieval_ids=[
                    "mem:orion:billing-owner-old",
                    "mem:orion:billing-api-owner",
                ],
                expect_pollution_avoidance=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_abandoned_resumed_work",
            category=BenchmarkScenarioType.IMPLICIT_RECALL,
            implicit_recall=ImplicitRecallFixture(
                query="resume current import repair checkpoint",
                context_tokens=["resumed", "checkpoint", "current", "import", "repair"],
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="exec:import:abandoned-branch",
                        domain=MemoryDomain.EXECUTION,
                        text="Abandoned import repair branch tried changing the parser with no validation.",
                        execution_node_id="node:abandoned",
                        validity_status=TemporalValidityStatus.INVALIDATED,
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="exec:import:resumed-checkpoint",
                        domain=MemoryDomain.EXECUTION,
                        text="Current resumed import repair checkpoint is to validate fixtures before parser edits.",
                        execution_node_id="node:resumed",
                    ),
                ],
                relevant_ids=["exec:import:resumed-checkpoint"],
                relevant_memory_texts=[
                    "Current resumed import repair checkpoint is to validate fixtures before parser edits."
                ],
                lexical_overlap_score=0.18,
                expected_domains=[MemoryDomain.EXECUTION],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.ABANDONED_RESUMED_WORK_LIFECYCLE,
                expected_active_memory_ids=["exec:import:resumed-checkpoint"],
                expected_inactive_memory_ids=["exec:import:abandoned-branch"],
                expected_retrieval_ids=["exec:import:resumed-checkpoint"],
                expected_excluded_retrieval_ids=["exec:import:abandoned-branch"],
                expect_pollution_avoidance=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_historical_truth_retrieval",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="who handled Atlas ownership at the start of the year",
                intent=RetrievalIntent.CONSOLIDATE_CASE,
                scope=RetrievalScope(),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:atlas:owner-current",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="Current Atlas owner is Bob.",
                        entity_tags=["Atlas"],
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:atlas:owner-january",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="In January, Atlas owner was Alice.",
                        entity_tags=["Atlas"],
                        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                        valid_to=datetime(2026, 2, 28, tzinfo=UTC),
                    ),
                ],
                expected_relevant_ids=["mem:atlas:owner-january"],
                expected_excluded_ids=["mem:atlas:owner-current"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.HISTORICAL_TRUTH_RETRIEVAL,
                expected_active_memory_ids=["mem:atlas:owner-january"],
                expected_retrieval_ids=["mem:atlas:owner-january"],
                expected_excluded_retrieval_ids=["mem:atlas:owner-current"],
                expect_temporal_addressability=True,
                require_lifecycle_decision=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_current_truth_retrieval",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="who should I ask about Atlas ownership today",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:atlas:owner-january",
                        domain=MemoryDomain.SEMANTIC,
                        text="In January, Atlas owner was Alice.",
                        entity_tags=["Atlas"],
                        validity_status=TemporalValidityStatus.EXPIRED,
                        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                        valid_to=datetime(2026, 2, 28, tzinfo=UTC),
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:atlas:owner-current",
                        domain=MemoryDomain.SEMANTIC,
                        text="Current Atlas owner is Bob.",
                        entity_tags=["Atlas"],
                    ),
                ],
                expected_relevant_ids=["mem:atlas:owner-current"],
                expected_excluded_ids=["mem:atlas:owner-january"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.CURRENT_TRUTH_RETRIEVAL,
                expected_active_memory_ids=["mem:atlas:owner-current"],
                expected_inactive_memory_ids=["mem:atlas:owner-january"],
                expected_retrieval_ids=["mem:atlas:owner-current"],
                expected_excluded_retrieval_ids=["mem:atlas:owner-january"],
                expect_temporal_addressability=True,
                require_lifecycle_decision=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_competing_belief_reranking",
            category=BenchmarkScenarioType.IMPLICIT_RECALL,
            implicit_recall=ImplicitRecallFixture(
                query="which timeout hypothesis should lead after the latest evidence",
                context_tokens=["timeout", "evidence", "leading", "hypothesis", "worker"],
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="belief:timeout:network",
                        domain=MemoryDomain.SOLVER,
                        text="Hypothesis A: network regression remains possible but dropped sharply below database lock after new evidence.",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="belief:timeout:worker",
                        domain=MemoryDomain.SOLVER,
                        text="Hypothesis B is now leading: worker pool saturation explains the timeout evidence.",
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="belief:timeout:database",
                        domain=MemoryDomain.SOLVER,
                        text="Hypothesis C: database lock is the second-most likely explanation, still less likely than worker saturation.",
                    ),
                ],
                relevant_ids=["belief:timeout:worker"],
                relevant_memory_texts=[
                    "Hypothesis B is now leading: worker pool saturation explains the timeout evidence."
                ],
                lexical_overlap_score=0.2,
                expected_domains=[MemoryDomain.SOLVER],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.COMPETING_BELIEF_RERANKING,
                expected_active_memory_ids=["belief:timeout:worker"],
                expected_retrieval_ids=["belief:timeout:worker"],
                expected_excluded_retrieval_ids=[
                    "belief:timeout:network",
                    "belief:timeout:database",
                ],
                expected_belief_ranking=[
                    "belief:timeout:worker",
                    "belief:timeout:database",
                    "belief:timeout:network",
                ],
                require_lifecycle_decision=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_partial_merge_preserve_unique_facts",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="what consolidated Atlas account facts should be retained",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:atlas:partial-a",
                        domain=MemoryDomain.SEMANTIC,
                        text="Atlas owner is Alice and Atlas uses Azure.",
                        entity_tags=["Atlas"],
                        validity_status=TemporalValidityStatus.INVALIDATED,
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:atlas:partial-b",
                        domain=MemoryDomain.SEMANTIC,
                        text="Atlas owner is Alice and Atlas requires FedRAMP.",
                        entity_tags=["Atlas"],
                        validity_status=TemporalValidityStatus.INVALIDATED,
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:atlas:merged-owner-azure-fedramp",
                        domain=MemoryDomain.SEMANTIC,
                        text="Atlas owner is Alice, Atlas uses Azure, and Atlas requires FedRAMP.",
                        entity_tags=["Atlas"],
                    ),
                ],
                expected_relevant_ids=["mem:atlas:merged-owner-azure-fedramp"],
                expected_excluded_ids=["mem:atlas:partial-a", "mem:atlas:partial-b"],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.PARTIAL_MERGE_PRESERVE_UNIQUE_FACTS,
                expected_active_memory_ids=["mem:atlas:merged-owner-azure-fedramp"],
                expected_inactive_memory_ids=["mem:atlas:partial-a", "mem:atlas:partial-b"],
                expected_retrieval_ids=["mem:atlas:merged-owner-azure-fedramp"],
                expected_excluded_retrieval_ids=["mem:atlas:partial-a", "mem:atlas:partial-b"],
                expected_merged_fact_tokens=["Alice", "Azure", "FedRAMP"],
                expect_duplicate_avoidance=True,
                expect_partial_merge=True,
                require_lifecycle_decision=True,
            ),
        ),
        BenchmarkScenarioFixture(
            scenario_id="lifecycle_high_similarity_active_distractor",
            category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
            retrieval=RetrievalFixture(
                query="who should I ask for final ownership calls on the Orion billing migration",
                intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                scope=RetrievalScope(),
                top_k=1,
                corpus=[
                    RetrievalFixtureMemoryItem(
                        item_id="mem:orion:billing-migration-approver",
                        domain=MemoryDomain.SEMANTIC,
                        text="Current Orion billing migration approver person is Nikhil.",
                        entity_tags=["Orion"],
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:orion:billing-migration-owner",
                        domain=MemoryDomain.SEMANTIC,
                        text="Current Orion billing migration owner person is Nadia.",
                        entity_tags=["Orion"],
                    ),
                    RetrievalFixtureMemoryItem(
                        item_id="mem:orion:billing-api-owner",
                        domain=MemoryDomain.SEMANTIC,
                        text="Current Orion billing API owner person is Nikhil.",
                        entity_tags=["Orion"],
                    ),
                ],
                expected_relevant_ids=["mem:orion:billing-migration-owner"],
                expected_excluded_ids=[
                    "mem:orion:billing-migration-approver",
                    "mem:orion:billing-api-owner",
                ],
            ),
            lifecycle=MemoryLifecycleExpectation(
                family=MemoryLifecycleFamily.HIGH_SIMILARITY_ACTIVE_DISTRACTOR,
                expected_retrieval_ids=["mem:orion:billing-migration-owner"],
                expected_excluded_retrieval_ids=[
                    "mem:orion:billing-migration-approver",
                    "mem:orion:billing-api-owner",
                ],
                expect_pollution_avoidance=True,
                require_lifecycle_decision=True,
            ),
        ),
    ]
