from __future__ import annotations

from memorii.core.benchmark.fixture_sets.memory_evolution_v1 import (
    load_memory_evolution_v1_fixture_set,
)
from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionDecisionContext,
    MemoryEvolutionDecisionOperation,
    MemoryEvolutionScopeKind,
    MemoryEvolutionSemanticDecision,
    MemoryEvolutionSemanticTemporalFrame,
    fake_llm_result_for_memory_evolution,
    memory_evolution_context_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_sim import (
    MemoryEvolutionSimReconstructionContext,
    SimClaimAssessment,
    SimClaimSemanticRole,
    SimSemanticDecision,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest
from memorii.core.prompts.models import PromptModelDefaults
from memorii.core.prompts.registry import default_prompt_root
from memorii.tools.benchmark_suites import memory_evolution as curated_suite
from memorii.tools.benchmark_suites import memory_evolution_sim as sim_suite
from memorii.tools.benchmark_suites.memory_evolution_artifacts import _llm_call_count
from memorii.tools.benchmark_suites.runtime_dependencies import (
    BenchmarkRuntimeDependencies,
    DryRunDecisionStrategy,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    generate_scenario_by_family,
    provider_result_for_sim_semantic,
)


class _ScriptedSimRepairAdapter:
    provider_name = "fake"

    def __init__(
        self,
        *,
        corrected_by_checkpoint: dict[str, SimSemanticDecision],
    ) -> None:
        self._corrected_by_checkpoint = corrected_by_checkpoint

    def decide(
        self,
        context: MemoryEvolutionSimReconstructionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        corrected = self._corrected_by_checkpoint[context.checkpoint.checkpoint_id]
        decision = (
            corrected
            if context.repair_request is not None
            else corrected.model_copy(
                update={
                    "claim_assessments": [
                        assessment.model_copy(
                            update={"claim_id": "not-visible"}
                        )
                        if index == 0
                        else assessment
                        for index, assessment in enumerate(
                            corrected.claim_assessments
                        )
                    ],
                }
            )
        )
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="memory_evolution_sim_reconstruction:v1",
            prompt_hash="offline-test",
            system="",
            user="",
            output_schema={},
            model_defaults=PromptModelDefaults(model="test-model"),
            metadata=metadata or {},
        )
        return provider_result_for_sim_semantic(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ScriptedCuratedRepairAdapter:
    provider_name = "fake"

    def __init__(
        self,
        *,
        corrected_by_checkpoint: dict[str, MemoryEvolutionSemanticDecision],
    ) -> None:
        self._corrected_by_checkpoint = corrected_by_checkpoint

    def decide(
        self,
        context: MemoryEvolutionDecisionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        corrected = self._corrected_by_checkpoint[context.checkpoint.checkpoint_id]
        if context.repair_request is not None:
            decision = corrected
        else:
            decision = corrected.model_copy(
                update={
                    "considered_memory_ids": [
                        *corrected.considered_memory_ids,
                        "not-visible",
                    ],
                    "selected_memory_ids": [
                        *corrected.selected_memory_ids,
                        "not-visible",
                    ],
                }
            )
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="memory_evolution_decision:v1",
            prompt_hash="offline-test",
            system="",
            user="",
            output_schema={},
            model_defaults=PromptModelDefaults(model="test-model"),
            metadata=metadata or {},
        )
        return fake_llm_result_for_memory_evolution(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


def _scripted_current_owner_decision(
    context: MemoryEvolutionSimReconstructionContext,
) -> SimSemanticDecision:
    primary = next(
        claim
        for claim in context.visible_claims
        if claim.subject_entity_type == "project"
        and claim.predicate_id == "owner"
        and claim.lifecycle_state == "active"
    )
    return SimSemanticDecision(
        operation="answer",
        claim_assessments=[
            SimClaimAssessment(
                claim_id=claim.claim_id,
                role=(
                    SimClaimSemanticRole.PRIMARY
                    if claim.claim_id == primary.claim_id
                    else SimClaimSemanticRole.IRRELEVANT
                ),
                belief_rank=None,
            )
            for claim in context.visible_claims
        ],
        answer=primary.object_value,
        next_action=None,
        uncertain_ids=[],
        confidence=0.9,
        rationale="scripted visible-context current owner selection",
    )


def _scripted_latest_fact_decision(
    context: MemoryEvolutionDecisionContext,
) -> MemoryEvolutionSemanticDecision:
    selected = max(
        context.visible_memory_cards,
        key=lambda card: (card.timestamp, card.trust_level, card.memory_id),
    )
    answer = selected.statement.rsplit(" ", maxsplit=1)[-1].rstrip(".")
    return MemoryEvolutionSemanticDecision(
        operation=MemoryEvolutionDecisionOperation.ANSWER,
        answer=answer,
        next_action=None,
        confidence=0.9,
        query_temporal_frame=MemoryEvolutionSemanticTemporalFrame(
            temporal_reference=context.decision_contract.temporal_reference,
            decision_domain=context.decision_contract.decision_domain,
            scope_kind=MemoryEvolutionScopeKind.NONE,
            scope_key=None,
            anchor_id=None,
            valid_from=None,
            valid_to=None,
            confidence=0.9,
            rationale="scripted current visible-context frame",
        ),
        selected_memory_ids=[selected.memory_id],
        considered_memory_ids=[
            card.memory_id for card in context.visible_memory_cards
        ],
        belief_scores=[],
        rationale="scripted latest visible fact selection",
        requires_judge_review=False,
    )


def test_sim_runner_repairs_once_and_accounts_for_both_provider_calls(
    monkeypatch,
) -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="current_vs_historical_truth",
        seed=7,
        noise_rate=0.35,
    )
    scenario = scenario.model_copy(update={"checkpoints": [scenario.checkpoints[0]]})
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=scenario.checkpoints[0],
    )
    corrected = _scripted_current_owner_decision(context)
    monkeypatch.setattr(
        sim_suite,
        "LLMMemoryEvolutionSimReconstructionAdapter",
        lambda *, runner, registry: _ScriptedSimRepairAdapter(
            corrected_by_checkpoint={
                scenario.checkpoints[0].checkpoint_id: corrected
            },
        ),
    )

    _scenario_rows, checkpoint_rows, _judge_rows, llm_rows = sim_suite._run_memory_evolution_sim_transitions(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        dependencies=BenchmarkRuntimeDependencies(
            dry_run_decision_strategy=DryRunDecisionStrategy.CLIENT_ADAPTERS,
        ),
    )

    assert all(row.success for row in checkpoint_rows)
    assert len(llm_rows) == len(scenario.checkpoints)
    assert _llm_call_count(llm_rows) == 2 * len(scenario.checkpoints)
    for row in llm_rows:
        assert len(row.provider_attempts) == 2
        assert row.provider_attempts[0].accepted is False
        assert set(row.provider_attempts[0].validation_issues) == {
            "invalid_claim_id",
            "missing_claim_assessment",
        }
        assert row.provider_attempts[1].accepted is True
        assert row.provider_attempts[1].repair_request is not None
        assert row.provider_attempts[1].previous_decision_digest is not None
        assert row.provider_attempts[1].compiled_output == row.output.model_dump(
            mode="json"
        )
        assert row.final_output_accepted is True
        assert row.fallback_outcome.value == "not_used"


def test_curated_runner_records_schema_valid_semantic_rejection_before_repair(
    monkeypatch,
) -> None:
    scenario = load_memory_evolution_v1_fixture_set()[0]
    scenario = scenario.model_copy(update={"checkpoints": [scenario.checkpoints[0]]})
    context = memory_evolution_context_for_checkpoint(
        scenario=scenario,
        checkpoint=scenario.checkpoints[0],
    )
    corrected = _scripted_latest_fact_decision(context)
    monkeypatch.setattr(
        curated_suite,
        "ExpectedMemoryEvolutionFakeAdapter",
        lambda *, scenarios, registry: _ScriptedCuratedRepairAdapter(
            corrected_by_checkpoint={
                scenario.checkpoints[0].checkpoint_id: corrected
            }
        ),
    )

    _scenario_rows, checkpoint_rows, llm_rows = curated_suite._run_memory_evolution_transitions(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        dependencies=BenchmarkRuntimeDependencies(),
    )

    assert all(row["success"] is True for row in checkpoint_rows)
    assert len(llm_rows) == len(scenario.checkpoints)
    for row in llm_rows:
        assert len(row.provider_attempts) == 2
        assert row.provider_attempts[0].provider_attempt_status.value == "succeeded"
        assert row.provider_attempts[0].semantic_validation_status == "failed"
        assert row.provider_attempts[0].accepted is False
        assert set(row.provider_attempts[0].validation_issues) == {
            "invalid_memory_id",
        }
        assert row.provider_attempts[1].semantic_validation_status == "passed"
        assert row.provider_attempts[1].accepted is True
        assert row.provider_attempts[1].repair_request is not None
        assert row.provider_attempts[1].previous_decision_digest is not None
        assert row.provider_attempts[1].compiled_output == row.output.model_dump(
            mode="json"
        )
        assert row.semantic_validation_status == "passed"
        assert row.final_output_accepted is True
