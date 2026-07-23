import pytest
from memorii.core.benchmark.fixture_sets.memory_evolution_v1 import load_memory_evolution_v1_fixture_set
from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionBeliefLifecyclePolicy,
    MemoryEvolutionDecision,
    MemoryEvolutionDecisionDomain,
    MemoryEvolutionEvent,
    MemoryEvolutionEventRole,
    MemoryEvolutionFailureBucket,
    MemoryEvolutionScopeKind,
    MemoryEvolutionSourceType,
    MemoryEvolutionTemporalReference,
    MemoryEvolutionWarningBucket,
    expected_memory_evolution_decision_for_checkpoint,
    memory_evolution_assertion_passed,
    memory_evolution_context_for_checkpoint,
    memory_evolution_decision_diagnostics,
    memory_evolution_visible_decision_contract,
    rule_memory_evolution_decision_for_checkpoint,
)
from pydantic import ValidationError


def test_memory_evolution_v1_has_ten_episode_chain_scenarios() -> None:
    scenarios = load_memory_evolution_v1_fixture_set()

    assert len(scenarios) == 10
    assert sum(1 for scenario in scenarios if scenario.discriminative) >= 5
    assert all(len(scenario.events) >= 2 for scenario in scenarios)
    assert all(scenario.checkpoints for scenario in scenarios)


def test_memory_evolution_v1_checkpoint_references_are_event_derived() -> None:
    for scenario in load_memory_evolution_v1_fixture_set():
        event_ids = {event.event_id for event in scenario.events}
        for checkpoint in scenario.checkpoints:
            referenced = {
                *checkpoint.expected_retrieval_ids,
                *checkpoint.expected_citation_ids,
                *checkpoint.expected_context_citation_ids,
                *checkpoint.expected_excluded_memory_ids,
                *checkpoint.expected_checkpoint_active_record_ids,
                *checkpoint.expected_checkpoint_superseded_record_ids,
                *checkpoint.expected_checkpoint_retained_record_ids,
                *checkpoint.expected_belief_ranking,
                *checkpoint.expected_belief_scores.keys(),
                *(expectation.memory_id for expectation in checkpoint.expected_belief_states),
            }
            assert referenced.issubset(event_ids)


def test_expected_memory_evolution_decisions_pass_all_checkpoints() -> None:
    for scenario in load_memory_evolution_v1_fixture_set():
        for checkpoint in scenario.checkpoints:
            assert memory_evolution_assertion_passed(
                scenario=scenario,
                checkpoint=checkpoint,
                decision=expected_memory_evolution_decision_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                ).model_dump(mode="json"),
            )


def test_memory_evolution_requires_excluded_memories_in_rejected_or_context_channels() -> None:
    scenario = _scenario_by_id("evolution_wrong_entity_high_similarity")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["retrieval_context"]["rejected_memory_ids"] = []
    output["retrieval_context"]["query_context_memory_ids"] = []
    output["retrieval_context"]["query_historical_memory_ids"] = []

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert diagnostics.excluded_memory_missing_channel_ids == checkpoint.expected_excluded_memory_ids
    assert MemoryEvolutionFailureBucket.EXPECTED_EXCLUDED_MEMORY_CHANNEL_MISSING in diagnostics.failure_buckets


def test_memory_evolution_source_trust_allows_global_scope_enrichment() -> None:
    scenario = _scenario_by_id("evolution_source_trust_conflict")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["query_temporal_frame"]["scope_kind"] = "global"

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionFailureBucket.TEMPORAL_SCOPE_MISMATCH not in diagnostics.failure_buckets


def test_answer_matching_allows_unrelated_negative_explanation() -> None:
    scenario = _scenario_by_id("evolution_partial_merge_then_split")
    checkpoint = scenario.checkpoints[0]
    actual = (
        "Atlas has Alice as owner, is on Azure, and requires FedRAMP. "
        "The API ownership was split to Nikhil and is not included in the active account facts."
    )
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer"] = actual

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True


def test_answer_matching_rejects_local_negative_contradiction() -> None:
    scenario = _scenario_by_id("evolution_partial_merge_then_split")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer"] = "Alice is not the owner"

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.ANSWER_MISMATCH in diagnostics.failure_buckets


def test_memory_evolution_decision_rejects_removed_top_level_channels() -> None:
    scenario = _scenario_by_id("evolution_current_vs_historical_truth")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")

    for removed_field in (
        "selected_memory_ids",
        "active_memory_ids",
        "inactive_memory_ids",
        "archived_memory_ids",
        "citation_memory_ids",
    ):
        invalid = dict(output)
        invalid[removed_field] = []
        with pytest.raises(ValidationError):
            MemoryEvolutionDecision.model_validate(invalid)


def test_rule_memory_evolution_provider_fails_semantic_traps() -> None:
    failures = 0
    for scenario in load_memory_evolution_v1_fixture_set():
        if not scenario.discriminative:
            continue
        scenario_passed = all(
            memory_evolution_assertion_passed(
                scenario=scenario,
                checkpoint=checkpoint,
                decision=rule_memory_evolution_decision_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                ).model_dump(mode="json"),
            )
            for checkpoint in scenario.checkpoints
        )
        if not scenario_passed:
            failures += 1

    assert failures >= 5


def test_memory_evolution_assertion_requires_current_and_historical_truth() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_current_vs_historical_truth"
    )
    historical = next(
        checkpoint
        for checkpoint in scenario.checkpoints
        if checkpoint.checkpoint_id == "checkpoint:atlas-owner-january"
    )
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=historical,
    ).model_dump(mode="json")
    output["answer_selection"]["selected_memory_ids"] = ["mem:atlas-owner-bob-current"]
    output["answer_selection"]["supporting_memory_ids"] = ["mem:atlas-owner-bob-current"]
    output["answer_selection"]["citation_memory_ids"] = ["mem:atlas-owner-bob-current"]
    output["answer"] = "Bob"

    assert (
        memory_evolution_assertion_passed(
            scenario=scenario,
            checkpoint=historical,
            decision=output,
        )
        is False
    )


def test_memory_evolution_assertion_requires_wrong_entity_precision() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_wrong_entity_high_similarity"
    )
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["selected_memory_ids"] = ["mem:orion-billing-approver-nikhil"]
    output["answer_selection"]["supporting_memory_ids"] = ["mem:orion-billing-approver-nikhil"]
    output["answer_selection"]["citation_memory_ids"] = ["mem:orion-billing-approver-nikhil"]
    output["answer"] = "Nikhil"

    assert (
        memory_evolution_assertion_passed(
            scenario=scenario,
            checkpoint=checkpoint,
            decision=output,
        )
        is False
    )


def test_memory_evolution_assertion_requires_belief_degradation() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_belief_dependency_degradation"
    )
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["belief_scores"] = [
        {"memory_id": "belief:a-cache-miss-root", "belief": 0.8},
        {"memory_id": "belief:b-worker-retry-backed-by-a", "belief": 0.7},
        {"memory_id": "belief:c-customer-latency-backed-by-b", "belief": 0.6},
    ]

    assert (
        memory_evolution_assertion_passed(
            scenario=scenario,
            checkpoint=checkpoint,
            decision=output,
        )
        is False
    )


def test_memory_evolution_assertion_allows_top_selection_for_belief_ranking() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_competing_belief_reranking"
    )
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["selected_memory_ids"] = ["belief:b-worker-exhaustion"]

    assert memory_evolution_assertion_passed(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )


def test_memory_evolution_assertion_does_not_require_answer_text_for_graph_channel_checkpoint() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer"] = None

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionFailureBucket.ANSWER_MISMATCH not in diagnostics.failure_buckets


def test_memory_evolution_assertion_allows_non_checkpoint_active_lifecycle_equivalence_when_authored() -> None:
    scenario = _scenario_by_id("evolution_expired_fact_historical_query")
    checkpoint = next(item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:beta-flag-current")
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["lifecycle_snapshot"]["checkpoint_retained_record_ids"] = []
    output["lifecycle_snapshot"]["checkpoint_superseded_record_ids"] = ["mem:beta-flag-active-release-week"]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_RETAINED_RECORD_MISSING not in diagnostics.failure_buckets


def test_memory_evolution_split_query_accepts_canonical_entity_scope_enrichment() -> None:
    scenario = _scenario_by_id("evolution_partial_merge_then_split")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["query_temporal_frame"]["scope_kind"] = "entity"
    output["query_temporal_frame"]["scope_key"] = "Atlas"
    output["answer_selection"]["supporting_memory_ids"] = [
        "mem:atlas-owner-azure",
        "mem:atlas-owner-fedramp",
    ]
    output["lifecycle_snapshot"]["checkpoint_active_record_ids"] = [
        "mem:atlas-owner-azure",
        "mem:atlas-owner-fedramp",
        "mem:atlas-identity-split",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionFailureBucket.TEMPORAL_SCOPE_KEY_MISMATCH not in diagnostics.failure_buckets
    assert MemoryEvolutionWarningBucket.EXTRA_CHECKPOINT_ACTIVE_RECORD_IDS in diagnostics.warning_buckets


def test_memory_evolution_split_query_rejects_wrong_entity_scope_key() -> None:
    scenario = _scenario_by_id("evolution_partial_merge_then_split")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["query_temporal_frame"]["scope_kind"] = "entity"
    output["query_temporal_frame"]["scope_key"] = "Orion"

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.TEMPORAL_SCOPE_KEY_MISMATCH in diagnostics.failure_buckets


def test_memory_evolution_execution_rejects_suppressed_branch_as_active() -> None:
    scenario = _scenario_by_id("evolution_abandoned_then_resumed_work")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["lifecycle_snapshot"]["checkpoint_retained_record_ids"] = []
    output["lifecycle_snapshot"]["checkpoint_active_record_ids"] = [
        "exec:approach-a-blocked",
        "exec:approach-b-progressed",
    ]
    output["execution_selection"]["suppressed_branch_memory_ids"] = [
        "exec:approach-a-blocked",
        "exec:approach-a-started",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.SCHEMA_VALIDATION_FAILED in diagnostics.failure_buckets


def test_memory_evolution_execution_retained_branch_requires_suppression_signal() -> None:
    scenario = _scenario_by_id("evolution_abandoned_then_resumed_work")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["lifecycle_snapshot"]["checkpoint_retained_record_ids"] = []
    output["lifecycle_snapshot"]["checkpoint_active_record_ids"] = [
        "exec:approach-a-blocked",
        "exec:approach-b-progressed",
    ]
    output["execution_selection"]["suppressed_branch_memory_ids"] = ["exec:approach-a-started"]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_RETAINED_RECORD_MISSING in diagnostics.failure_buckets


def test_memory_evolution_assertion_treats_non_excluded_source_trust_corroboration_as_warning() -> None:
    scenario = _scenario_by_id("evolution_source_trust_conflict")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["supporting_memory_ids"] = [
        "mem:deploy-tool-failed",
        "mem:deploy-user-confirmed-failed",
    ]
    output["answer_selection"]["citation_memory_ids"] = [
        "mem:deploy-tool-failed",
        "mem:deploy-user-confirmed-failed",
    ]
    output["lifecycle_snapshot"]["checkpoint_active_record_ids"] = [
        "mem:deploy-tool-failed",
        "mem:deploy-user-confirmed-failed",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionFailureBucket.CITATION_CHANNEL_POLLUTION not in diagnostics.failure_buckets
    assert MemoryEvolutionWarningBucket.CONTEXT_CITATION_IN_DIRECT_CHANNEL in diagnostics.warning_buckets


def test_memory_evolution_source_trust_losers_cannot_remain_active_assertions() -> None:
    scenario = _scenario_by_id("evolution_source_trust_conflict")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["lifecycle_snapshot"]["checkpoint_active_record_ids"] = [
        "mem:deploy-tool-failed",
        "mem:deploy-user-confirmed-failed",
        "mem:deploy-transcript-succeeded",
        "mem:deploy-late-transcript-succeeded",
    ]
    output["lifecycle_snapshot"]["checkpoint_superseded_record_ids"] = []

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.SOURCE_TRUST_LOSER_MARKED_ACTIVE in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_SUPERSEDED_RECORD_MISSING in diagnostics.failure_buckets


def test_memory_evolution_assertion_fails_unexpected_context_citation() -> None:
    scenario = _scenario_by_id("evolution_source_trust_conflict")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["citation_memory_ids"] = [
        "mem:deploy-user-confirmed-failed",
        "mem:deploy-late-transcript-succeeded",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.SCHEMA_VALIDATION_FAILED in diagnostics.failure_buckets


def test_memory_evolution_context_declares_belief_channel_contract() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]

    context = memory_evolution_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    contract = context.metadata["output_channel_contract"]

    assert "belief_scores" in contract
    assert "answer_selection.citation_memory_ids" in contract
    assert "Direct evidence" in contract["answer_selection.citation_memory_ids"]
    assert "evaluated_belief_ids" in contract


def test_memory_evolution_context_declares_degraded_score_band() -> None:
    scenario = _scenario_by_id("evolution_belief_dependency_degradation")
    checkpoint = scenario.checkpoints[0]

    context = memory_evolution_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    contract = context.metadata["output_channel_contract"]

    assert "belief_score_calibration" in contract
    assert "0.35" in contract["belief_score_calibration"]


def test_memory_evolution_context_excludes_oracle_checkpoint_fields() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]

    context = memory_evolution_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    context_payload = context.model_dump(mode="json")

    assert context_payload["checkpoint"] == {
        "checkpoint_id": checkpoint.checkpoint_id,
        "timestamp": checkpoint.timestamp.isoformat().replace("+00:00", "Z"),
        "query_or_task": checkpoint.query_or_task,
        "query_language": "en",
        "evidence_languages": ["en"],
        "answer_language_policy": "match_query",
        "cross_lingual": False,
        "transliteration_policy": "allowed",
    }
    assert not _contains_key_prefix(context_payload["checkpoint"], "expected_")
    assert context.decision_contract == checkpoint.contract
    assert not _contains_key_prefix(
        context_payload["decision_contract"],
        "expected_",
    )


def test_memory_evolution_visible_decision_contract_is_fixture_authored_not_query_inferred() -> None:
    scenario = _scenario_by_id("evolution_current_vs_historical_truth")
    historical = next(item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:atlas-owner-january")
    rewritten = historical.model_copy(update={"query_or_task": "During January, name the Atlas owner."})

    contract = memory_evolution_visible_decision_contract(scenario=scenario, checkpoint=rewritten)

    assert contract == historical.contract
    assert contract.temporal_reference == "historical"
    assert contract.selected_memory_policy == "historical_truth"


def test_memory_evolution_command_context_uses_event_role_not_english_phrase() -> None:
    scenario = _scenario_by_id("evolution_abandoned_then_resumed_work")
    checkpoint = scenario.checkpoints[0]
    rewritten_events = [
        event.model_copy(
            update={
                "content": "Continúa con la corrección anterior.",
                "language": "es",
            }
        )
        if event.event_id == "exec:user-continue-previous"
        else event
        for event in scenario.events
    ]
    rewritten = scenario.model_copy(update={"events": rewritten_events})

    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=rewritten,
        checkpoint=checkpoint,
    )

    assert output.execution_selection is not None
    assert output.execution_selection.command_context_memory_ids == ["exec:user-continue-previous"]


def test_memory_evolution_command_like_observation_is_not_command_context() -> None:
    scenario = _scenario_by_id("evolution_abandoned_then_resumed_work")
    checkpoint = scenario.checkpoints[0]
    rewritten_events = [
        event.model_copy(update={"event_role": MemoryEvolutionEventRole.OBSERVATION})
        if event.event_id == "exec:user-continue-previous"
        else event
        for event in scenario.events
    ]
    rewritten = scenario.model_copy(update={"events": rewritten_events})

    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=rewritten,
        checkpoint=checkpoint,
    )

    assert output.execution_selection is not None
    assert output.execution_selection.command_context_memory_ids == []


def test_memory_evolution_diagnostics_fail_belief_ids_used_as_citations() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["citation_memory_ids"] = [
        "evidence:workers-exhausted",
        "belief:b-worker-exhaustion",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.CITATION_CHANNEL_POLLUTION in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.BELIEF_ID_USED_AS_CITATION in diagnostics.failure_buckets
    assert diagnostics.belief_ids_used_as_citations == ["belief:b-worker-exhaustion"]


def test_memory_evolution_diagnostics_fail_missing_required_belief_evidence() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["citation_memory_ids"] = []

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert diagnostics.missing_citation_ids == ["evidence:workers-exhausted"]
    assert MemoryEvolutionFailureBucket.EXPECTED_CITATION_MISSING in diagnostics.failure_buckets


def test_memory_evolution_diagnostics_fail_extra_citations_for_non_discriminative_checkpoint() -> None:
    scenario = _scenario_by_id("evolution_current_vs_historical_truth").model_copy(update={"discriminative": False})
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["citation_memory_ids"] = [
        *checkpoint.expected_citation_ids,
        "mem:unrelated-extra-citation",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert diagnostics.extra_citation_ids == ["mem:unrelated-extra-citation"]
    assert MemoryEvolutionFailureBucket.CITATION_CHANNEL_POLLUTION in diagnostics.failure_buckets


def test_memory_evolution_diagnostics_warn_when_beliefs_marked_active() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["lifecycle_snapshot"]["checkpoint_active_record_ids"] = [
        "belief:b-worker-exhaustion",
        "belief:c-database-locks",
        "belief:a-network-saturation",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert diagnostics.failure_buckets == []
    assert MemoryEvolutionWarningBucket.ACTIVE_CHANNEL_POLLUTION in diagnostics.warning_buckets
    assert MemoryEvolutionWarningBucket.BELIEF_CANDIDATE_MARKED_ACTIVE in diagnostics.warning_buckets


def test_memory_evolution_diagnostics_fail_wrong_belief_ranking_order() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["selected_memory_ids"] = [
        "belief:a-network-saturation",
        "belief:b-worker-exhaustion",
        "belief:c-database-locks",
    ]
    output["belief_scores"] = [
        {"memory_id": "belief:a-network-saturation", "belief": 0.7},
        {"memory_id": "belief:b-worker-exhaustion", "belief": 0.2},
        {"memory_id": "belief:c-database-locks", "belief": 0.1},
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.BELIEF_RANKING_WRONG_ORDER in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH not in diagnostics.failure_buckets
    assert MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT in diagnostics.warning_buckets
    assert diagnostics.actual_belief_ranking[0] == "belief:a-network-saturation"


def test_memory_evolution_diagnostics_fail_when_belief_scores_invert_selected_order() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["belief_scores"] = [
        {"memory_id": "belief:b-worker-exhaustion", "belief": 0.35},
        {"memory_id": "belief:c-database-locks", "belief": 0.25},
        {"memory_id": "belief:a-network-saturation", "belief": 0.4},
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.BELIEF_RANKING_WRONG_ORDER not in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.BELIEF_SCORE_ORDER_CONTRADICTS_SELECTED_ORDER in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL in diagnostics.failure_buckets
    assert diagnostics.actual_belief_ranking == checkpoint.expected_belief_ranking


def test_memory_evolution_assertion_suppresses_abandoned_branch() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_abandoned_then_resumed_work"
    )
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["selected_memory_ids"] = ["exec:approach-a-started"]
    output["answer_selection"]["citation_memory_ids"] = ["exec:approach-a-started"]
    output["execution_selection"]["selected_action_memory_ids"] = ["exec:approach-a-started"]
    output["execution_selection"]["active_work_state_memory_ids"] = ["exec:approach-a-started"]
    output["next_action"] = "continue approach A"

    assert (
        memory_evolution_assertion_passed(
            scenario=scenario,
            checkpoint=checkpoint,
            decision=output,
        )
        is False
    )


def test_memory_evolution_belief_degradation_accepts_none_as_no_answer_equivalent() -> None:
    scenario = _scenario_by_id("evolution_belief_dependency_degradation")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer"] = "None of the dependent beliefs remain confident after A is falsified."

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionFailureBucket.ANSWER_MISMATCH not in diagnostics.failure_buckets


def test_memory_evolution_belief_ranking_allows_calibration_drift_when_order_is_correct() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["belief_scores"] = [
        {"memory_id": "belief:b-worker-exhaustion", "belief": 0.6},
        {"memory_id": "belief:c-database-locks", "belief": 0.3},
        {"memory_id": "belief:a-network-saturation", "belief": 0.1},
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT in diagnostics.warning_buckets


def test_memory_evolution_belief_degradation_accepts_low_confidence_scores_without_exact_match() -> None:
    scenario = _scenario_by_id("evolution_belief_dependency_degradation")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["belief_scores"] = [
        {"memory_id": "belief:a-cache-miss-root", "belief": 0.0, "belief_state": "falsified"},
        {"memory_id": "belief:b-worker-retry-backed-by-a", "belief": 0.0, "belief_state": "degraded"},
        {"memory_id": "belief:c-customer-latency-backed-by-b", "belief": 0.0, "belief_state": "degraded"},
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT in diagnostics.warning_buckets
    assert MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT in diagnostics.warning_buckets


def test_memory_evolution_execution_rejects_suppressed_branch_as_direct_citation() -> None:
    scenario = _scenario_by_id("evolution_abandoned_then_resumed_work")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["next_action"] = "Continue working on Approach B to complete the fix."
    output["answer_selection"]["citation_memory_ids"] = [
        "exec:approach-b-progressed",
        "exec:approach-a-blocked",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.SCHEMA_VALIDATION_FAILED in diagnostics.failure_buckets
    assert MemoryEvolutionWarningBucket.LIFECYCLE_CHANNEL_DRIFT not in diagnostics.warning_buckets


def test_memory_evolution_historical_answer_requires_checkpoint_current_lifecycle() -> None:
    scenario = _scenario_by_id("evolution_expired_fact_historical_query")
    checkpoint = next(
        item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:beta-flag-release-week"
    )
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["lifecycle_snapshot"]["checkpoint_active_record_ids"] = []
    output["lifecycle_snapshot"]["checkpoint_retained_record_ids"] = ["mem:beta-flag-archived-now"]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_ACTIVE_RECORD_MISSING in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.RECORD_LIFECYCLE_CONTENT_STATE_CONFLATION in diagnostics.failure_buckets
    assert diagnostics.record_lifecycle_content_state_conflation_ids == ["mem:beta-flag-archived-now"]


def test_memory_evolution_historical_release_week_requires_temporal_anchor() -> None:
    scenario = _scenario_by_id("evolution_expired_fact_historical_query")
    checkpoint = next(
        item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:beta-flag-release-week"
    )
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["query_temporal_frame"] = {
        "temporal_reference": "historical",
        "decision_domain": "fact",
        "scope_kind": "none",
        "scope_key": None,
        "anchor_id": None,
        "valid_from": None,
        "valid_to": "2026-06-09T08:05:00Z",
        "confidence": 0.7,
        "rationale": "Unanchored historical frame.",
    }

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.TEMPORAL_FRAME_MISMATCH in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.TEMPORAL_ANCHOR_MISMATCH in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.TEMPORAL_INTERVAL_MISMATCH in diagnostics.failure_buckets


def test_memory_evolution_historical_january_uses_query_interval_not_checkpoint_time() -> None:
    scenario = _scenario_by_id("evolution_current_vs_historical_truth")
    checkpoint = next(item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:atlas-owner-january")

    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert diagnostics.expected_temporal_frame is not None
    assert diagnostics.expected_temporal_frame.temporal_reference == MemoryEvolutionTemporalReference.HISTORICAL
    assert diagnostics.expected_temporal_frame.valid_to.isoformat() == "2026-01-31T23:59:59+00:00"
    assert output["query_temporal_frame"]["valid_to"] == "2026-01-31T23:59:59Z"
    assert "mode" not in output["query_temporal_frame"]


def test_memory_evolution_historical_january_requires_start_bound() -> None:
    scenario = _scenario_by_id("evolution_current_vs_historical_truth")
    checkpoint = next(item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:atlas-owner-january")
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["query_temporal_frame"]["valid_from"] = None

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.TEMPORAL_FRAME_MISMATCH in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.TEMPORAL_INTERVAL_MISMATCH in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.TEMPORAL_FRAME_UNDER_SPECIFIED in diagnostics.failure_buckets


def test_memory_evolution_execution_checkpoint_bounds_are_warning_only() -> None:
    scenario = _scenario_by_id("evolution_abandoned_then_resumed_work")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["query_temporal_frame"]["valid_from"] = "2026-06-10T10:00:00Z"
    output["query_temporal_frame"]["valid_to"] = "2026-06-10T10:35:00Z"

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionWarningBucket.TEMPORAL_FRAME_ENRICHMENT in diagnostics.warning_buckets
    assert MemoryEvolutionFailureBucket.TEMPORAL_EXTRA_INTERVAL not in diagnostics.failure_buckets


def test_memory_evolution_degraded_beliefs_can_be_retained_as_evaluated_state() -> None:
    scenario = _scenario_by_id("evolution_belief_dependency_degradation")
    checkpoint = scenario.checkpoints[0]
    contract = memory_evolution_visible_decision_contract(scenario=scenario, checkpoint=checkpoint)
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["lifecycle_snapshot"]["checkpoint_active_record_ids"] = ["evidence:a-falsified"]
    output["evaluated_belief_ids"] = [
        "belief:b-worker-retry-backed-by-a",
        "belief:c-customer-latency-backed-by-b",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert contract.belief_lifecycle_policy == MemoryEvolutionBeliefLifecyclePolicy.DEGRADED_RETAINED_EVALUABLE
    assert diagnostics.assertion_passed is True
    assert MemoryEvolutionFailureBucket.EXPECTED_CHECKPOINT_ACTIVE_RECORD_MISSING not in diagnostics.failure_buckets


def test_memory_evolution_belief_degradation_uses_state_contract_not_exact_scores() -> None:
    scenario = _scenario_by_id("evolution_belief_dependency_degradation")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["belief_scores"] = [
        {"memory_id": "belief:a-cache-miss-root", "belief": 0.0, "belief_state": "falsified"},
        {"memory_id": "belief:b-worker-retry-backed-by-a", "belief": 0.3, "belief_state": "degraded"},
        {"memory_id": "belief:c-customer-latency-backed-by-b", "belief": 0.3, "belief_state": "degraded"},
    ]
    output["answer_selection"]["selected_memory_ids"] = [
        "belief:b-worker-retry-backed-by-a",
        "belief:c-customer-latency-backed-by-b",
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert diagnostics.missing_required_belief_score_ids == []
    assert diagnostics.belief_state_mismatch_ids == []
    assert MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH not in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.BELIEF_STATE_MISMATCH not in diagnostics.failure_buckets


def test_memory_evolution_belief_degradation_fails_overconfident_dependent_belief() -> None:
    scenario = _scenario_by_id("evolution_belief_dependency_degradation")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["belief_scores"] = [
        {"memory_id": "belief:a-cache-miss-root", "belief": 0.05, "belief_state": "falsified"},
        {"memory_id": "belief:b-worker-retry-backed-by-a", "belief": 0.6, "belief_state": "degraded"},
        {"memory_id": "belief:c-customer-latency-backed-by-b", "belief": 0.25, "belief_state": "degraded"},
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert "belief:b-worker-retry-backed-by-a" in diagnostics.belief_state_mismatch_ids
    assert MemoryEvolutionFailureBucket.BELIEF_STATE_MISMATCH in diagnostics.failure_buckets


def test_memory_evolution_current_query_uses_separate_scope_axis() -> None:
    scenario = _scenario_by_id("evolution_task_preference_does_not_overwrite_global")
    checkpoint = scenario.checkpoints[0]

    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is True
    assert diagnostics.expected_temporal_frame is not None
    assert diagnostics.expected_temporal_frame.temporal_reference == MemoryEvolutionTemporalReference.CURRENT
    assert diagnostics.expected_temporal_frame.decision_domain == MemoryEvolutionDecisionDomain.FACT
    assert diagnostics.expected_temporal_frame.scope_kind == MemoryEvolutionScopeKind.GLOBAL
    assert diagnostics.expected_temporal_frame.scope_key is None
    assert output["answer_selection"]["temporal_reference"] == "current"


def test_memory_evolution_temporal_reference_is_orthogonal_to_decision_domain() -> None:
    belief_scenario = _scenario_by_id("evolution_competing_belief_reranking")
    belief_checkpoint = belief_scenario.checkpoints[0]
    belief = expected_memory_evolution_decision_for_checkpoint(
        scenario=belief_scenario,
        checkpoint=belief_checkpoint,
    )
    execution_scenario = _scenario_by_id("evolution_abandoned_then_resumed_work")
    execution_checkpoint = execution_scenario.checkpoints[0]
    execution = expected_memory_evolution_decision_for_checkpoint(
        scenario=execution_scenario,
        checkpoint=execution_checkpoint,
    )
    historical_scenario = _scenario_by_id("evolution_current_vs_historical_truth")
    historical_checkpoint = next(
        checkpoint
        for checkpoint in historical_scenario.checkpoints
        if checkpoint.checkpoint_id == "checkpoint:atlas-owner-january"
    )
    historical = expected_memory_evolution_decision_for_checkpoint(
        scenario=historical_scenario,
        checkpoint=historical_checkpoint,
    )

    assert belief.query_temporal_frame.temporal_reference == "current"
    assert belief.query_temporal_frame.decision_domain == "belief"
    assert execution.query_temporal_frame.temporal_reference == "current"
    assert execution.query_temporal_frame.decision_domain == "execution"
    assert historical.query_temporal_frame.temporal_reference == "historical"
    assert historical.query_temporal_frame.decision_domain == "fact"


def test_memory_evolution_temporal_reference_rejects_scope_as_time() -> None:
    scenario = _scenario_by_id("evolution_task_preference_does_not_overwrite_global")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["temporal_reference"] = "scoped"

    with pytest.raises(ValidationError):
        MemoryEvolutionDecision.model_validate(output)


def test_memory_evolution_context_exposes_temporal_entity_state_without_expected_ids() -> None:
    scenario = _scenario_by_id("evolution_expired_fact_historical_query")
    checkpoint = next(
        item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:beta-flag-release-week"
    )

    context = memory_evolution_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    payload = context.model_dump(mode="json")

    assert payload["temporal_anchor_cards"] == [
        {
            "anchor_id": "anchor:release-week-2026-06",
            "aliases": ["release week"],
            "valid_from": "2026-06-01T00:00:00Z",
            "valid_to": "2026-06-08T00:00:00Z",
            "source_memory_ids": ["mem:beta-flag-active-release-week"],
        }
    ]
    state_by_id = {card["memory_id"]: card for card in payload["entity_state_cards"]}
    assert state_by_id["mem:beta-flag-active-release-week"]["record_lifecycle"] == "checkpoint_superseded"
    assert state_by_id["mem:beta-flag-archived-now"]["record_lifecycle"] == "checkpoint_active"
    assert not _contains_key_prefix(payload, "expected_")


def test_memory_evolution_expected_historical_answer_is_not_rejected() -> None:
    scenario = _scenario_by_id("evolution_current_vs_historical_truth")
    checkpoint = next(item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:atlas-owner-january")

    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )

    selected = set(output.answer_selection.selected_memory_ids)
    rejected = set(output.retrieval_context.rejected_memory_ids)
    historical = set(output.retrieval_context.query_historical_memory_ids)

    assert selected == {"mem:atlas-owner-alice-jan"}
    assert selected.issubset(historical)
    assert not selected & rejected


def test_memory_evolution_fails_when_selected_answer_is_also_rejected() -> None:
    scenario = _scenario_by_id("evolution_current_vs_historical_truth")
    checkpoint = next(item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:atlas-owner-january")
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["retrieval_context"]["rejected_memory_ids"] = ["mem:atlas-owner-alice-jan"]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.SCHEMA_VALIDATION_FAILED in diagnostics.failure_buckets


def test_memory_evolution_answer_alias_does_not_accept_negated_answer() -> None:
    scenario = _scenario_by_id("evolution_expired_fact_historical_query")
    checkpoint = next(item for item in scenario.checkpoints if item.checkpoint_id == "checkpoint:beta-flag-current")
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer"] = "not archived"

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.ANSWER_MISMATCH in diagnostics.failure_buckets


def test_memory_evolution_context_includes_surface_derived_evidence_effect_cards() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]

    context = memory_evolution_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)

    assert [card.memory_id for card in context.visible_memory_cards] == [event.event_id for event in scenario.events]
    effect = next(
        card for card in context.evidence_effect_cards if card.evidence_memory_id == "evidence:workers-exhausted"
    )
    assert effect.supports_memory_ids == ["belief:b-worker-exhaustion"]
    assert effect.weakens_memory_ids == ["belief:a-network-saturation"]
    assert effect.falsifies_memory_ids == []
    assert context.metadata["evidence_effect_policy"]["ranking_order"] == "supported > neutral > weakened > falsified"


def test_memory_evolution_evidence_effect_cards_handle_passive_and_equivalent_phrasing() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    rewritten_events = [
        event
        if event.event_id != "evidence:workers-exhausted"
        else MemoryEvolutionEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            source_type=MemoryEvolutionSourceType.TOOL,
            content="Worker telemetry shows B is supported, while A is now less likely.",
            entity_ids=list(event.entity_ids),
            trust_level=event.trust_level,
        )
        for event in scenario.events
    ]
    rewritten = scenario.model_copy(update={"events": rewritten_events})

    context = memory_evolution_context_for_checkpoint(scenario=rewritten, checkpoint=checkpoint)

    effect = next(
        card for card in context.evidence_effect_cards if card.evidence_memory_id == "evidence:workers-exhausted"
    )
    assert effect.supports_memory_ids == ["belief:b-worker-exhaustion"]
    assert effect.weakens_memory_ids == ["belief:a-network-saturation"]


def test_memory_evolution_diagnostics_name_weakened_above_neutral_belief_order() -> None:
    scenario = _scenario_by_id("evolution_competing_belief_reranking")
    checkpoint = scenario.checkpoints[0]
    output = expected_memory_evolution_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")
    output["answer_selection"]["selected_memory_ids"] = [
        "belief:b-worker-exhaustion",
        "belief:a-network-saturation",
        "belief:c-database-locks",
    ]
    output["belief_scores"] = [
        {"memory_id": "belief:b-worker-exhaustion", "belief": 0.6},
        {"memory_id": "belief:a-network-saturation", "belief": 0.3},
        {"memory_id": "belief:c-database-locks", "belief": 0.1},
    ]

    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=output,
    )

    assert diagnostics.assertion_passed is False
    assert MemoryEvolutionFailureBucket.BELIEF_RANKING_WRONG_ORDER in diagnostics.failure_buckets
    assert MemoryEvolutionFailureBucket.WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL in diagnostics.failure_buckets
    assert diagnostics.belief_effect_order_errors == ["belief:a-network-saturation>belief:c-database-locks"]


def _scenario_by_id(scenario_id: str):
    return next(item for item in load_memory_evolution_v1_fixture_set() if item.scenario_id == scenario_id)


def _contains_key_prefix(value: object, prefix: str) -> bool:
    if isinstance(value, dict):
        return any(
            (isinstance(key, str) and key.startswith(prefix)) or _contains_key_prefix(nested, prefix)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_key_prefix(item, prefix) for item in value)
    return False
