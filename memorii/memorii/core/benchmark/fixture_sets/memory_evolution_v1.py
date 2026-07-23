from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionAnswerProjectionPolicy,
    MemoryEvolutionBeliefLifecyclePolicy,
    MemoryEvolutionBeliefScorePolicy,
    MemoryEvolutionBeliefState,
    MemoryEvolutionBeliefStateExpectation,
    MemoryEvolutionCheckpoint,
    MemoryEvolutionCheckpointKind,
    MemoryEvolutionCitationPolicy,
    MemoryEvolutionDecisionDomain,
    MemoryEvolutionEvent,
    MemoryEvolutionEventRole,
    MemoryEvolutionExcludedMemoryPolicy,
    MemoryEvolutionLifecyclePolicy,
    MemoryEvolutionNextActionPolicy,
    MemoryEvolutionScenario,
    MemoryEvolutionScopeKeyPolicy,
    MemoryEvolutionScopeKind,
    MemoryEvolutionScopeMatchPolicy,
    MemoryEvolutionSelectedMemoryPolicy,
    MemoryEvolutionSourceType,
    MemoryEvolutionTemporalFrame,
    MemoryEvolutionTemporalIntervalPolicy,
    MemoryEvolutionTemporalReference,
    MemoryEvolutionVisibleDecisionContract,
)


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _temporal_frame(
    temporal_reference: MemoryEvolutionTemporalReference,
    *,
    decision_domain: MemoryEvolutionDecisionDomain = MemoryEvolutionDecisionDomain.FACT,
    scope_kind: MemoryEvolutionScopeKind = MemoryEvolutionScopeKind.NONE,
    scope_key: str | None = None,
    anchor_id: str | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    rationale: str = "Authored fixture temporal frame.",
) -> MemoryEvolutionTemporalFrame:
    return MemoryEvolutionTemporalFrame(
        temporal_reference=temporal_reference,
        decision_domain=decision_domain,
        scope_kind=scope_kind,
        scope_key=scope_key,
        anchor_id=anchor_id,
        valid_from=_ts(valid_from) if valid_from is not None else None,
        valid_to=_ts(valid_to) if valid_to is not None else None,
        confidence=1.0,
        rationale=rationale,
    )


def _event(
    event_id: str,
    timestamp: str,
    source_type: MemoryEvolutionSourceType,
    content: str,
    *,
    entity_ids: list[str] | None = None,
    task_id: str | None = None,
    scope: str | None = None,
    trust_level: int = 1,
    event_role: MemoryEvolutionEventRole = MemoryEvolutionEventRole.OBSERVATION,
    language: str = "en",
    script: str | None = None,
    subject_entity_id: str | None = None,
    predicate: str | None = None,
    object_value: str | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    temporal_anchor_ids: list[str] | None = None,
    temporal_anchor_aliases: list[str] | None = None,
) -> MemoryEvolutionEvent:
    return MemoryEvolutionEvent(
        event_id=event_id,
        timestamp=_ts(timestamp),
        source_type=source_type,
        content=content,
        entity_ids=entity_ids or [],
        task_id=task_id,
        scope=scope,
        trust_level=trust_level,
        event_role=event_role,
        language=language,
        script=script,
        subject_entity_id=subject_entity_id,
        predicate=predicate,
        object_value=object_value,
        valid_from=_ts(valid_from) if valid_from is not None else None,
        valid_to=_ts(valid_to) if valid_to is not None else None,
        temporal_anchor_ids=temporal_anchor_ids or [],
        temporal_anchor_aliases=temporal_anchor_aliases or [],
    )


def _truth_contract(
    *,
    historical: bool = False,
    scope_match_policy: MemoryEvolutionScopeMatchPolicy = MemoryEvolutionScopeMatchPolicy.EXACT,
    citation_policy: MemoryEvolutionCitationPolicy = MemoryEvolutionCitationPolicy.DIRECT_ONLY,
    lifecycle_policy: MemoryEvolutionLifecyclePolicy = MemoryEvolutionLifecyclePolicy.EXACT,
    allow_extra_temporal_anchor: bool = False,
    allow_extra_temporal_bounds: bool | None = None,
    excluded_memory_policy: MemoryEvolutionExcludedMemoryPolicy = MemoryEvolutionExcludedMemoryPolicy.NONE,
) -> MemoryEvolutionVisibleDecisionContract:
    if historical:
        return MemoryEvolutionVisibleDecisionContract(
            checkpoint_kind=MemoryEvolutionCheckpointKind.HISTORICAL_TRUTH,
            temporal_reference=MemoryEvolutionTemporalReference.HISTORICAL,
            decision_domain=MemoryEvolutionDecisionDomain.FACT,
            selected_memory_policy=MemoryEvolutionSelectedMemoryPolicy.HISTORICAL_TRUTH,
            answer_projection_policy=MemoryEvolutionAnswerProjectionPolicy.CLAIM_OBJECT,
            citation_policy=citation_policy,
            lifecycle_policy=lifecycle_policy,
            scope_match_policy=scope_match_policy,
            temporal_interval_policy=MemoryEvolutionTemporalIntervalPolicy.REQUIRE_START_AND_END,
            scope_key_policy=MemoryEvolutionScopeKeyPolicy.CANONICAL_ALIAS,
            allow_extra_temporal_anchor=allow_extra_temporal_anchor,
            allow_extra_temporal_bounds=bool(allow_extra_temporal_bounds),
            allow_historical_selected_memory=True,
            excluded_memory_policy=excluded_memory_policy,
        )
    return MemoryEvolutionVisibleDecisionContract(
        checkpoint_kind=MemoryEvolutionCheckpointKind.CURRENT_TRUTH,
        temporal_reference=MemoryEvolutionTemporalReference.CURRENT,
        decision_domain=MemoryEvolutionDecisionDomain.FACT,
        selected_memory_policy=MemoryEvolutionSelectedMemoryPolicy.CURRENT_TRUTH,
        answer_projection_policy=MemoryEvolutionAnswerProjectionPolicy.CLAIM_OBJECT,
        citation_policy=citation_policy,
        lifecycle_policy=lifecycle_policy,
        scope_match_policy=scope_match_policy,
        temporal_interval_policy=MemoryEvolutionTemporalIntervalPolicy.ALLOW_CHECKPOINT_BOUNDS,
        scope_key_policy=MemoryEvolutionScopeKeyPolicy.CANONICAL_ALIAS,
        allow_extra_temporal_anchor=allow_extra_temporal_anchor,
        allow_extra_temporal_bounds=True if allow_extra_temporal_bounds is None else allow_extra_temporal_bounds,
        excluded_memory_policy=excluded_memory_policy,
    )


def _belief_contract(*, degradation: bool = False) -> MemoryEvolutionVisibleDecisionContract:
    return MemoryEvolutionVisibleDecisionContract(
        checkpoint_kind=(
            MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION
            if degradation
            else MemoryEvolutionCheckpointKind.BELIEF_RANKING
        ),
        temporal_reference=MemoryEvolutionTemporalReference.CURRENT,
        decision_domain=MemoryEvolutionDecisionDomain.BELIEF,
        selected_memory_policy=MemoryEvolutionSelectedMemoryPolicy.BELIEF_ORDER,
        answer_projection_policy=MemoryEvolutionAnswerProjectionPolicy.GRAPH_CHANNELS_ONLY,
        citation_policy=(
            MemoryEvolutionCitationPolicy.DIRECT_WITH_CONTEXT_WARNING
            if degradation
            else MemoryEvolutionCitationPolicy.DIRECT_ONLY
        ),
        lifecycle_policy=(
            MemoryEvolutionLifecyclePolicy.EXACT if degradation else MemoryEvolutionLifecyclePolicy.WARNING
        ),
        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_OR_ENTITY,
        temporal_interval_policy=MemoryEvolutionTemporalIntervalPolicy.ALLOW_CHECKPOINT_BOUNDS,
        scope_key_policy=MemoryEvolutionScopeKeyPolicy.CANONICAL_ALIAS,
        belief_lifecycle_policy=(
            MemoryEvolutionBeliefLifecyclePolicy.DEGRADED_RETAINED_EVALUABLE
            if degradation
            else MemoryEvolutionBeliefLifecyclePolicy.RANKING_CANDIDATES_ALLOWED
        ),
        belief_score_policy=(
            MemoryEvolutionBeliefScorePolicy.DEGRADED_THRESHOLD
            if degradation
            else MemoryEvolutionBeliefScorePolicy.RANKING_ONLY
        ),
    )


def _execution_contract() -> MemoryEvolutionVisibleDecisionContract:
    return MemoryEvolutionVisibleDecisionContract(
        checkpoint_kind=MemoryEvolutionCheckpointKind.EXECUTION_CONTINUATION,
        temporal_reference=MemoryEvolutionTemporalReference.CURRENT,
        decision_domain=MemoryEvolutionDecisionDomain.EXECUTION,
        selected_memory_policy=MemoryEvolutionSelectedMemoryPolicy.ACTIVE_EXECUTION_STATE,
        answer_projection_policy=MemoryEvolutionAnswerProjectionPolicy.NEXT_ACTION,
        citation_policy=MemoryEvolutionCitationPolicy.DIRECT_WITH_CONTEXT_WARNING,
        lifecycle_policy=MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT,
        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_OR_TASK,
        temporal_interval_policy=MemoryEvolutionTemporalIntervalPolicy.ALLOW_CHECKPOINT_BOUNDS,
        scope_key_policy=MemoryEvolutionScopeKeyPolicy.CANONICAL_ALIAS,
        next_action_policy=MemoryEvolutionNextActionPolicy.NONEMPTY_STRUCTURED,
        requires_execution_selection=True,
        excluded_memory_policy=MemoryEvolutionExcludedMemoryPolicy.REJECTED_OR_CONTEXT,
    )


def _checkpoint(
    checkpoint_id: str,
    timestamp: str,
    query_or_task: str,
    *,
    contract: MemoryEvolutionVisibleDecisionContract,
    expected_answer: str | None = None,
    expected_next_action: str | None = None,
    expected_retrieval_ids: list[str] | None = None,
    expected_citation_ids: list[str] | None = None,
    expected_context_citation_ids: list[str] | None = None,
    expected_excluded_memory_ids: list[str] | None = None,
    expected_checkpoint_active_record_ids: list[str] | None = None,
    expected_checkpoint_superseded_record_ids: list[str] | None = None,
    expected_checkpoint_retained_record_ids: list[str] | None = None,
    expected_full_checkpoint_active_record_ids: list[str] | None = None,
    expected_full_checkpoint_superseded_record_ids: list[str] | None = None,
    expected_full_checkpoint_retained_record_ids: list[str] | None = None,
    expected_belief_ranking: list[str] | None = None,
    expected_belief_scores: dict[str, float] | None = None,
    expected_belief_states: list[MemoryEvolutionBeliefStateExpectation] | None = None,
    expected_answer_aliases: list[str] | None = None,
    expected_temporal_frame: MemoryEvolutionTemporalFrame | None = None,
) -> MemoryEvolutionCheckpoint:
    return MemoryEvolutionCheckpoint(
        checkpoint_id=checkpoint_id,
        timestamp=_ts(timestamp),
        query_or_task=query_or_task,
        contract=contract,
        expected_answer=expected_answer,
        expected_next_action=expected_next_action,
        expected_retrieval_ids=expected_retrieval_ids or [],
        expected_citation_ids=expected_citation_ids or [],
        expected_context_citation_ids=expected_context_citation_ids or [],
        expected_excluded_memory_ids=expected_excluded_memory_ids or [],
        expected_checkpoint_active_record_ids=expected_checkpoint_active_record_ids or [],
        expected_checkpoint_superseded_record_ids=expected_checkpoint_superseded_record_ids or [],
        expected_checkpoint_retained_record_ids=expected_checkpoint_retained_record_ids or [],
        expected_full_checkpoint_active_record_ids=expected_full_checkpoint_active_record_ids or [],
        expected_full_checkpoint_superseded_record_ids=expected_full_checkpoint_superseded_record_ids or [],
        expected_full_checkpoint_retained_record_ids=expected_full_checkpoint_retained_record_ids or [],
        expected_belief_ranking=expected_belief_ranking or [],
        expected_belief_scores=expected_belief_scores or {},
        expected_belief_states=expected_belief_states or [],
        expected_answer_aliases=expected_answer_aliases or [],
        expected_temporal_frame=expected_temporal_frame,
    )


def load_memory_evolution_v1_fixture_set() -> list[MemoryEvolutionScenario]:
    return [
        MemoryEvolutionScenario(
            scenario_id="evolution_current_vs_historical_truth",
            family="current_vs_historical_truth",
            discriminative=True,
            events=[
                _event(
                    "mem:atlas-owner-alice-jan",
                    "2026-01-10T09:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Atlas ownership in January belonged to Alice.",
                    entity_ids=["atlas"],
                    trust_level=3,
                ),
                _event(
                    "mem:atlas-owner-bob-current",
                    "2026-03-20T09:00:00",
                    MemoryEvolutionSourceType.VERIFIED_OBSERVATION,
                    "Atlas owner is Bob.",
                    entity_ids=["atlas"],
                    trust_level=5,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:atlas-owner-current",
                    "2026-04-01T09:00:00",
                    "Who owns Atlas today?",
                    contract=_truth_contract(),
                    expected_answer="Bob",
                    expected_retrieval_ids=["mem:atlas-owner-bob-current"],
                    expected_citation_ids=["mem:atlas-owner-bob-current"],
                    expected_checkpoint_active_record_ids=["mem:atlas-owner-bob-current"],
                    expected_checkpoint_superseded_record_ids=["mem:atlas-owner-alice-jan"],
                ),
                _checkpoint(
                    "checkpoint:atlas-owner-january",
                    "2026-04-01T09:05:00",
                    "Who owned Atlas in January?",
                    contract=_truth_contract(historical=True),
                    expected_answer="Alice",
                    expected_retrieval_ids=["mem:atlas-owner-alice-jan"],
                    expected_citation_ids=["mem:atlas-owner-alice-jan"],
                    expected_checkpoint_active_record_ids=["mem:atlas-owner-bob-current"],
                    expected_checkpoint_superseded_record_ids=["mem:atlas-owner-alice-jan"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.HISTORICAL,
                        valid_from="2026-01-01T00:00:00",
                        valid_to="2026-01-31T23:59:59",
                        rationale="The query asks who owned Atlas during January.",
                    ),
                ),
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_global_vs_task_scoped_preference",
            family="global_vs_task_scoped_preference",
            discriminative=False,
            events=[
                _event(
                    "mem:global-status-concise",
                    "2026-02-01T10:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Global status update style is concise.",
                    scope="global",
                    trust_level=3,
                ),
                _event(
                    "mem:incident-review-detailed",
                    "2026-02-15T10:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Incident review status update style is detailed timeline.",
                    task_id="task:incident-review",
                    scope="task",
                    trust_level=3,
                ),
                _event(
                    "mem:normal-status-concise-reminder",
                    "2026-02-20T10:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Normal status update style is concise.",
                    scope="global",
                    trust_level=3,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:normal-status-style",
                    "2026-02-21T10:00:00",
                    "What style should a normal status update use?",
                    contract=_truth_contract(
                        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_OR_GLOBAL,
                    ),
                    expected_answer="concise",
                    expected_retrieval_ids=["mem:normal-status-concise-reminder"],
                    expected_citation_ids=["mem:normal-status-concise-reminder"],
                    expected_checkpoint_active_record_ids=["mem:normal-status-concise-reminder"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.CURRENT,
                        scope_kind=MemoryEvolutionScopeKind.GLOBAL,
                        rationale="The query asks for the checkpoint-current normal status style visible as a global preference.",
                    ),
                ),
                _checkpoint(
                    "checkpoint:incident-status-style",
                    "2026-02-21T10:05:00",
                    "What style should an incident review status update use?",
                    contract=_truth_contract(
                        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_OR_TASK,
                    ),
                    expected_answer="detailed timeline",
                    expected_retrieval_ids=["mem:incident-review-detailed"],
                    expected_citation_ids=["mem:incident-review-detailed"],
                    expected_checkpoint_active_record_ids=["mem:incident-review-detailed"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.CURRENT,
                        scope_kind=MemoryEvolutionScopeKind.TASK,
                        scope_key="task:incident-review",
                        rationale="The query asks for the current style within the incident-review task scope.",
                    ),
                ),
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_task_preference_does_not_overwrite_global",
            family="task_preference_scope_inversion",
            discriminative=False,
            events=[
                _event(
                    "mem:global-summary-concise",
                    "2026-02-01T11:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Global summary style is concise.",
                    scope="global",
                    trust_level=3,
                ),
                _event(
                    "mem:project-debug-verbose",
                    "2026-02-10T11:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Project Phoenix debugging style is verbose.",
                    task_id="task:phoenix-debug",
                    scope="task",
                    trust_level=3,
                ),
                _event(
                    "mem:outside-project-summary-concise",
                    "2026-02-12T11:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Outside project summary style is concise.",
                    scope="global",
                    trust_level=3,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:outside-project-summary",
                    "2026-02-13T11:00:00",
                    "What style should an outside project summary use?",
                    contract=_truth_contract(
                        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_OR_GLOBAL,
                    ),
                    expected_answer="concise",
                    expected_retrieval_ids=["mem:outside-project-summary-concise"],
                    expected_citation_ids=["mem:outside-project-summary-concise"],
                    expected_checkpoint_active_record_ids=["mem:outside-project-summary-concise"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.CURRENT,
                        scope_kind=MemoryEvolutionScopeKind.GLOBAL,
                        rationale="The query asks for the checkpoint-current outside-project summary style visible as a global preference.",
                    ),
                )
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_source_trust_conflict",
            family="source_trust_conflict",
            discriminative=True,
            events=[
                _event(
                    "mem:deploy-transcript-succeeded",
                    "2026-03-01T12:00:00",
                    MemoryEvolutionSourceType.TRANSCRIPT,
                    "Transcript note says Atlas deploy succeeded.",
                    entity_ids=["atlas-deploy"],
                    trust_level=1,
                ),
                _event(
                    "mem:deploy-tool-failed",
                    "2026-03-01T12:05:00",
                    MemoryEvolutionSourceType.TOOL,
                    "Deployment tool result says Atlas deploy failed.",
                    entity_ids=["atlas-deploy"],
                    trust_level=4,
                ),
                _event(
                    "mem:deploy-user-confirmed-failed",
                    "2026-03-01T12:10:00",
                    MemoryEvolutionSourceType.USER,
                    "User correction confirms Atlas deploy failed.",
                    entity_ids=["atlas-deploy"],
                    trust_level=5,
                ),
                _event(
                    "mem:deploy-late-transcript-succeeded",
                    "2026-03-01T12:12:00",
                    MemoryEvolutionSourceType.TRANSCRIPT,
                    "Transcript chatter says current Atlas deploy state succeeded.",
                    entity_ids=["atlas-deploy"],
                    trust_level=1,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:deploy-current-state",
                    "2026-03-01T12:15:00",
                    "What is the current Atlas deploy state?",
                    contract=_truth_contract(
                        # A query without an explicit task/entity scope may be
                        # represented as either no scope or the global scope.
                        # Keep this allowance local to this checkpoint rather
                        # than weakening scope validation for all truth queries.
                        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_OR_GLOBAL,
                        citation_policy=MemoryEvolutionCitationPolicy.DIRECT_WITH_CONTEXT_WARNING,
                        excluded_memory_policy=MemoryEvolutionExcludedMemoryPolicy.REJECTED_OR_CONTEXT,
                    ),
                    expected_answer="failed",
                    expected_retrieval_ids=["mem:deploy-user-confirmed-failed"],
                    expected_citation_ids=["mem:deploy-user-confirmed-failed"],
                    expected_context_citation_ids=["mem:deploy-tool-failed"],
                    expected_excluded_memory_ids=[
                        "mem:deploy-transcript-succeeded",
                        "mem:deploy-late-transcript-succeeded",
                    ],
                    expected_checkpoint_active_record_ids=["mem:deploy-user-confirmed-failed"],
                    expected_checkpoint_superseded_record_ids=[
                        "mem:deploy-transcript-succeeded",
                        "mem:deploy-late-transcript-succeeded",
                    ],
                )
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_wrong_entity_high_similarity",
            family="wrong_entity_high_similarity",
            discriminative=True,
            events=[
                _event(
                    "mem:orion-billing-owner-nadia",
                    "2026-04-01T09:00:00",
                    MemoryEvolutionSourceType.VERIFIED_OBSERVATION,
                    "Orion billing owner is Nadia.",
                    entity_ids=["orion", "billing"],
                    trust_level=5,
                ),
                _event(
                    "mem:orion-billing-approver-nikhil",
                    "2026-04-01T09:05:00",
                    MemoryEvolutionSourceType.VERIFIED_OBSERVATION,
                    "Orion billing approver is Nikhil.",
                    entity_ids=["orion", "billing"],
                    trust_level=5,
                ),
                _event(
                    "mem:orion-billing-api-owner-nikhil",
                    "2026-04-01T09:10:00",
                    MemoryEvolutionSourceType.VERIFIED_OBSERVATION,
                    "Orion billing API owner is Nikhil.",
                    entity_ids=["orion", "billing-api"],
                    trust_level=5,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:orion-billing-owner",
                    "2026-04-01T09:20:00",
                    "Who owns Orion billing?",
                    contract=_truth_contract(
                        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_GLOBAL_OR_ENTITY,
                        excluded_memory_policy=MemoryEvolutionExcludedMemoryPolicy.REJECTED_OR_CONTEXT,
                    ),
                    expected_answer="Nadia",
                    expected_retrieval_ids=["mem:orion-billing-owner-nadia"],
                    expected_citation_ids=["mem:orion-billing-owner-nadia"],
                    expected_excluded_memory_ids=[
                        "mem:orion-billing-approver-nikhil",
                        "mem:orion-billing-api-owner-nikhil",
                    ],
                    expected_checkpoint_active_record_ids=["mem:orion-billing-owner-nadia"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.CURRENT,
                        scope_kind=MemoryEvolutionScopeKind.ENTITY,
                        rationale="The query asks for the checkpoint-current owner of the Orion billing entity.",
                    ),
                )
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_belief_dependency_degradation",
            family="belief_dependency_degradation",
            discriminative=True,
            events=[
                _event(
                    "belief:a-cache-miss-root",
                    "2026-05-01T09:00:00",
                    MemoryEvolutionSourceType.TOOL,
                    "Belief A: cache misses are causing worker retries.",
                    entity_ids=["incident-17"],
                    trust_level=3,
                ),
                _event(
                    "belief:b-worker-retry-backed-by-a",
                    "2026-05-01T09:05:00",
                    MemoryEvolutionSourceType.ASSISTANT,
                    "Belief B depends on A: worker retries explain queue growth.",
                    entity_ids=["incident-17"],
                    trust_level=2,
                ),
                _event(
                    "belief:c-customer-latency-backed-by-b",
                    "2026-05-01T09:10:00",
                    MemoryEvolutionSourceType.ASSISTANT,
                    "Belief C depends on B: queue growth explains customer latency.",
                    entity_ids=["incident-17"],
                    trust_level=2,
                ),
                _event(
                    "evidence:a-falsified",
                    "2026-05-01T09:20:00",
                    MemoryEvolutionSourceType.VERIFIED_OBSERVATION,
                    "Verified observation falsifies A: cache misses are normal.",
                    entity_ids=["incident-17"],
                    trust_level=5,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:belief-after-falsification",
                    "2026-05-01T09:25:00",
                    "Which beliefs remain confident after A is falsified?",
                    contract=_belief_contract(degradation=True),
                    expected_answer="no beliefs remain confident",
                    expected_retrieval_ids=["evidence:a-falsified"],
                    expected_citation_ids=["evidence:a-falsified"],
                    expected_checkpoint_active_record_ids=[
                        "evidence:a-falsified",
                        "belief:b-worker-retry-backed-by-a",
                        "belief:c-customer-latency-backed-by-b",
                    ],
                    expected_checkpoint_superseded_record_ids=[
                        "belief:a-cache-miss-root",
                    ],
                    expected_belief_scores={
                        "belief:a-cache-miss-root": 0.05,
                        "belief:b-worker-retry-backed-by-a": 0.2,
                        "belief:c-customer-latency-backed-by-b": 0.25,
                    },
                    expected_belief_states=[
                        MemoryEvolutionBeliefStateExpectation(
                            memory_id="belief:a-cache-miss-root",
                            expected_state=MemoryEvolutionBeliefState.FALSIFIED,
                            max_score=0.1,
                        ),
                        MemoryEvolutionBeliefStateExpectation(
                            memory_id="belief:b-worker-retry-backed-by-a",
                            expected_state=MemoryEvolutionBeliefState.DEGRADED,
                            max_score=0.35,
                        ),
                        MemoryEvolutionBeliefStateExpectation(
                            memory_id="belief:c-customer-latency-backed-by-b",
                            expected_state=MemoryEvolutionBeliefState.DEGRADED,
                            max_score=0.35,
                        ),
                    ],
                )
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_competing_belief_reranking",
            family="competing_belief_reranking",
            discriminative=True,
            events=[
                _event(
                    "belief:a-network-saturation",
                    "2026-05-02T10:00:00",
                    MemoryEvolutionSourceType.ASSISTANT,
                    "Hypothesis A: network saturation is possible at 40 percent.",
                    entity_ids=["incident-18"],
                    trust_level=2,
                ),
                _event(
                    "belief:b-worker-exhaustion",
                    "2026-05-02T10:01:00",
                    MemoryEvolutionSourceType.ASSISTANT,
                    "Hypothesis B: worker exhaustion is possible at 35 percent.",
                    entity_ids=["incident-18"],
                    trust_level=2,
                ),
                _event(
                    "belief:c-database-locks",
                    "2026-05-02T10:02:00",
                    MemoryEvolutionSourceType.ASSISTANT,
                    "Hypothesis C: database locks are possible at 25 percent.",
                    entity_ids=["incident-18"],
                    trust_level=2,
                ),
                _event(
                    "evidence:workers-exhausted",
                    "2026-05-02T10:10:00",
                    MemoryEvolutionSourceType.TOOL,
                    "Tool evidence supports B worker exhaustion and weakens A network saturation.",
                    entity_ids=["incident-18"],
                    trust_level=4,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:belief-reranking",
                    "2026-05-02T10:15:00",
                    "Rank the current root-cause beliefs.",
                    contract=_belief_contract(),
                    expected_answer="worker exhaustion",
                    expected_retrieval_ids=[
                        "belief:b-worker-exhaustion",
                        "belief:c-database-locks",
                        "belief:a-network-saturation",
                    ],
                    expected_citation_ids=["evidence:workers-exhausted"],
                    expected_belief_ranking=[
                        "belief:b-worker-exhaustion",
                        "belief:c-database-locks",
                        "belief:a-network-saturation",
                    ],
                    expected_belief_scores={
                        "belief:b-worker-exhaustion": 0.7,
                        "belief:c-database-locks": 0.2,
                        "belief:a-network-saturation": 0.1,
                    },
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.CURRENT,
                        decision_domain=MemoryEvolutionDecisionDomain.BELIEF,
                        scope_kind=MemoryEvolutionScopeKind.ENTITY,
                        rationale="The query asks for current root-cause beliefs for incident-18.",
                    ),
                )
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_partial_merge_then_split",
            family="partial_merge_then_split",
            discriminative=False,
            events=[
                _event(
                    "mem:atlas-owner-azure",
                    "2026-06-01T09:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Atlas account facts are Alice owner and Azure platform.",
                    entity_ids=["atlas"],
                    trust_level=3,
                ),
                _event(
                    "mem:atlas-owner-fedramp",
                    "2026-06-01T09:05:00",
                    MemoryEvolutionSourceType.USER,
                    "Atlas account facts are Alice owner and FedRAMP required.",
                    entity_ids=["atlas"],
                    trust_level=3,
                ),
                _event(
                    "mem:atlas-identity-split",
                    "2026-06-01T09:10:00",
                    MemoryEvolutionSourceType.VERIFIED_OBSERVATION,
                    "Atlas account facts are Alice owner Azure platform FedRAMP required; split Atlas API owner into Nikhil.",
                    entity_ids=["atlas", "atlas-api"],
                    trust_level=5,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:atlas-merged-split-facts",
                    "2026-06-01T09:15:00",
                    "What Atlas account facts remain active after the split?",
                    contract=_truth_contract(
                        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_GLOBAL_OR_ENTITY,
                    ),
                    expected_answer="Alice owner Azure FedRAMP required Nikhil",
                    expected_retrieval_ids=["mem:atlas-identity-split"],
                    expected_citation_ids=["mem:atlas-identity-split"],
                    expected_checkpoint_active_record_ids=["mem:atlas-identity-split"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.CURRENT,
                        scope_kind=MemoryEvolutionScopeKind.ENTITY,
                        scope_key="atlas",
                        rationale=(
                            "The query asks for the current state of the Atlas account entity after the API split."
                        ),
                    ),
                )
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_abandoned_then_resumed_work",
            family="abandoned_then_resumed_work",
            discriminative=True,
            events=[
                _event(
                    "exec:approach-a-started",
                    "2026-06-10T10:00:00",
                    MemoryEvolutionSourceType.ASSISTANT,
                    "Approach A started for the fix.",
                    task_id="task:fix",
                    trust_level=2,
                    event_role=MemoryEvolutionEventRole.ACTION_STATE,
                ),
                _event(
                    "exec:approach-a-blocked",
                    "2026-06-10T10:10:00",
                    MemoryEvolutionSourceType.TOOL,
                    "Approach A is blocked by unavailable migration access.",
                    task_id="task:fix",
                    trust_level=4,
                    event_role=MemoryEvolutionEventRole.BLOCKED_STATE,
                ),
                _event(
                    "exec:approach-b-progressed",
                    "2026-06-10T10:20:00",
                    MemoryEvolutionSourceType.ASSISTANT,
                    "Approach B progressed by updating the provider path.",
                    task_id="task:fix",
                    trust_level=3,
                    event_role=MemoryEvolutionEventRole.ACTION_STATE,
                ),
                _event(
                    "exec:user-continue-previous",
                    "2026-06-10T10:30:00",
                    MemoryEvolutionSourceType.USER,
                    "User says continue the previous fix.",
                    task_id="task:fix",
                    trust_level=3,
                    event_role=MemoryEvolutionEventRole.COMMAND_CONTEXT,
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:resume-previous-fix",
                    "2026-06-10T10:35:00",
                    "Continue the previous fix.",
                    contract=_execution_contract(),
                    expected_next_action="continue approach B provider path",
                    expected_retrieval_ids=["exec:approach-b-progressed"],
                    expected_citation_ids=["exec:approach-b-progressed"],
                    expected_checkpoint_active_record_ids=["exec:approach-b-progressed"],
                    expected_checkpoint_superseded_record_ids=["exec:approach-a-started"],
                    expected_checkpoint_retained_record_ids=["exec:approach-a-blocked"],
                    expected_excluded_memory_ids=["exec:approach-a-started", "exec:approach-a-blocked"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.CURRENT,
                        decision_domain=MemoryEvolutionDecisionDomain.EXECUTION,
                        scope_kind=MemoryEvolutionScopeKind.TASK,
                        scope_key="task:fix",
                        rationale="The query asks for the active continuation state within task:fix.",
                    ),
                )
            ],
        ),
        MemoryEvolutionScenario(
            scenario_id="evolution_expired_fact_historical_query",
            family="expired_fact_historical_query",
            discriminative=False,
            events=[
                _event(
                    "mem:beta-flag-active-release-week",
                    "2026-06-01T08:00:00",
                    MemoryEvolutionSourceType.USER,
                    "Beta flag is active during release week.",
                    entity_ids=["beta-flag"],
                    trust_level=3,
                    subject_entity_id="beta-flag",
                    predicate="state",
                    object_value="active",
                    valid_from="2026-06-01T00:00:00",
                    valid_to="2026-06-08T00:00:00",
                    temporal_anchor_ids=["anchor:release-week-2026-06"],
                    temporal_anchor_aliases=["release week"],
                ),
                _event(
                    "mem:beta-flag-archived-now",
                    "2026-06-08T08:00:00",
                    MemoryEvolutionSourceType.VERIFIED_OBSERVATION,
                    "Beta flag is archived now.",
                    entity_ids=["beta-flag"],
                    trust_level=5,
                    subject_entity_id="beta-flag",
                    predicate="state",
                    object_value="archived",
                    valid_from="2026-06-08T08:00:00",
                ),
            ],
            checkpoints=[
                _checkpoint(
                    "checkpoint:beta-flag-current",
                    "2026-06-09T08:00:00",
                    "What is the beta flag state now?",
                    contract=_truth_contract(
                        lifecycle_policy=MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT,
                        scope_match_policy=MemoryEvolutionScopeMatchPolicy.NONE_OR_GLOBAL,
                    ),
                    expected_answer="archived now",
                    expected_answer_aliases=["archived", "currently archived", "archived as of current time"],
                    expected_retrieval_ids=["mem:beta-flag-archived-now"],
                    expected_citation_ids=["mem:beta-flag-archived-now"],
                    expected_checkpoint_active_record_ids=["mem:beta-flag-archived-now"],
                    expected_checkpoint_superseded_record_ids=["mem:beta-flag-active-release-week"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.CURRENT,
                        rationale="The query asks for the checkpoint-current beta flag state.",
                    ),
                ),
                _checkpoint(
                    "checkpoint:beta-flag-release-week",
                    "2026-06-09T08:05:00",
                    "What was the beta flag state during release week?",
                    contract=_truth_contract(
                        historical=True,
                        lifecycle_policy=MemoryEvolutionLifecyclePolicy.NON_CHECKPOINT_ACTIVE_EQUIVALENT,
                    ),
                    expected_answer="active during release week",
                    expected_answer_aliases=["active"],
                    expected_retrieval_ids=["mem:beta-flag-active-release-week"],
                    expected_citation_ids=["mem:beta-flag-active-release-week"],
                    expected_checkpoint_active_record_ids=["mem:beta-flag-archived-now"],
                    expected_checkpoint_superseded_record_ids=["mem:beta-flag-active-release-week"],
                    expected_temporal_frame=_temporal_frame(
                        MemoryEvolutionTemporalReference.HISTORICAL,
                        anchor_id="anchor:release-week-2026-06",
                        valid_from="2026-06-01T00:00:00Z",
                        valid_to="2026-06-08T00:00:00Z",
                        rationale="The phrase release week resolves to the visible release-week anchor.",
                    ),
                ),
            ],
        ),
    ]
