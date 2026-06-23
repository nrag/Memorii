import json
from pathlib import Path

import pytest

from memorii.core.benchmark.lifecycle_decision import (
    DISCRIMINATIVE_LIFECYCLE_FAMILIES,
    LifecycleDecision,
    expected_lifecycle_decision_for_fixture,
    lifecycle_assertion_passed,
    rule_lifecycle_decision_for_fixture,
)
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.tools.run_benchmark import _transition_kind, main
from memorii.tools.run_live_llm_eval import EvalFakeClient
from tests.fixtures.benchmarks.memory_lifecycle_v1 import load_memory_lifecycle_v1_fixture_set


def _discriminative_fixtures():
    return [
        fixture
        for fixture in load_memory_lifecycle_v1_fixture_set()
        if fixture.lifecycle is not None
        and fixture.lifecycle.family in DISCRIMINATIVE_LIFECYCLE_FAMILIES
    ]


def test_lifecycle_decision_schema_requires_confidence_and_rationale() -> None:
    decision = LifecycleDecision.model_validate(
        {
            "selected_retrieval_ids": ["mem:1"],
            "active_memory_ids": ["mem:1"],
            "inactive_memory_ids": [],
            "archived_memory_ids": [],
            "belief_scores": [],
            "merged_summary": None,
            "confidence": 0.8,
            "rationale": "selected current memory",
            "failure_mode": None,
            "requires_judge_review": False,
        }
    )

    assert decision.selected_retrieval_ids == ["mem:1"]
    assert decision.confidence == 0.8


def test_rule_lifecycle_provider_fails_discriminative_traps() -> None:
    fixtures = _discriminative_fixtures()

    assert len(fixtures) == 5
    assert all(
        lifecycle_assertion_passed(
            fixture=fixture,
            decision=rule_lifecycle_decision_for_fixture(fixture).model_dump(mode="json"),
        )
        is False
        for fixture in fixtures
    )


def test_expected_lifecycle_decision_passes_discriminative_traps() -> None:
    fixtures = _discriminative_fixtures()

    assert all(
        lifecycle_assertion_passed(
            fixture=fixture,
            decision=expected_lifecycle_decision_for_fixture(fixture).model_dump(mode="json"),
        )
        is True
        for fixture in fixtures
    )


def test_required_lifecycle_decision_cases_are_routed_to_lifecycle_decision() -> None:
    fixtures = _discriminative_fixtures()

    assert all(fixture.lifecycle is not None for fixture in fixtures)
    assert all(fixture.lifecycle.require_lifecycle_decision for fixture in fixtures if fixture.lifecycle)
    assert {_transition_kind(fixture) for fixture in fixtures} == {"lifecycle_decision"}


def test_lifecycle_decision_rejects_retrieval_only_outputs() -> None:
    for fixture in _discriminative_fixtures():
        assert fixture.lifecycle is not None
        retrieval_only = {
            "selected_retrieval_ids": list(fixture.lifecycle.expected_retrieval_ids),
            "active_memory_ids": list(fixture.lifecycle.expected_active_memory_ids),
            "inactive_memory_ids": list(fixture.lifecycle.expected_inactive_memory_ids),
            "archived_memory_ids": list(fixture.lifecycle.expected_archived_memory_ids),
            "belief_scores": [],
            "merged_summary": None,
            "confidence": 0.8,
            "rationale": "retrieval-only output",
            "failure_mode": None,
            "requires_judge_review": False,
        }

        if fixture.lifecycle.expected_belief_ranking or fixture.lifecycle.expect_partial_merge:
            assert lifecycle_assertion_passed(fixture=fixture, decision=retrieval_only) is False


def test_lifecycle_decision_enforces_exact_temporal_and_role_selection() -> None:
    by_id = {fixture.scenario_id: fixture for fixture in _discriminative_fixtures()}

    historical = expected_lifecycle_decision_for_fixture(
        by_id["lifecycle_historical_truth_retrieval"]
    ).model_dump(mode="json")
    historical["selected_retrieval_ids"] = [
        "mem:atlas:owner-january",
        "mem:atlas:owner-current",
    ]
    assert (
        lifecycle_assertion_passed(
            fixture=by_id["lifecycle_historical_truth_retrieval"],
            decision=historical,
        )
        is False
    )

    role = expected_lifecycle_decision_for_fixture(
        by_id["lifecycle_high_similarity_active_distractor"]
    ).model_dump(mode="json")
    role["selected_retrieval_ids"] = [
        "mem:orion:billing-migration-owner",
        "mem:orion:billing-migration-approver",
    ]
    assert (
        lifecycle_assertion_passed(
            fixture=by_id["lifecycle_high_similarity_active_distractor"],
            decision=role,
        )
        is False
    )


def test_lifecycle_decision_enforces_belief_ranking_and_partial_merge() -> None:
    by_id = {fixture.scenario_id: fixture for fixture in _discriminative_fixtures()}

    belief = expected_lifecycle_decision_for_fixture(
        by_id["lifecycle_competing_belief_reranking"]
    ).model_dump(mode="json")
    belief["belief_scores"] = [
        {"memory_id": "belief:timeout:database", "belief": 0.9},
        {"memory_id": "belief:timeout:worker", "belief": 0.8},
        {"memory_id": "belief:timeout:network", "belief": 0.1},
    ]
    assert (
        lifecycle_assertion_passed(
            fixture=by_id["lifecycle_competing_belief_reranking"],
            decision=belief,
        )
        is False
    )

    merge = expected_lifecycle_decision_for_fixture(
        by_id["lifecycle_partial_merge_preserve_unique_facts"]
    ).model_dump(mode="json")
    merge["merged_summary"] = "Atlas owner is Alice and Atlas uses Azure."
    assert (
        lifecycle_assertion_passed(
            fixture=by_id["lifecycle_partial_merge_preserve_unique_facts"],
            decision=merge,
        )
        is False
    )


def test_lifecycle_decision_artifact_rows_are_traced(tmp_path: Path) -> None:
    main(
        [
            "--suite",
            "memory_lifecycle_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    )

    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "llm").glob("bench-*"))[-1]
    rows = [
        json.loads(line)
        for line in (run_dir / "lifecycle_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    lifecycle_rows = [row for row in rows if row["transition_type"] == "lifecycle_decision"]

    assert len(lifecycle_rows) == 5
    assert all(row["transition_assertion_passed"] is True for row in lifecycle_rows)


def test_lifecycle_decision_uses_live_code_path_with_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    expected_by_scenario = {
        fixture.scenario_id: expected_lifecycle_decision_for_fixture(fixture)
        for fixture in _discriminative_fixtures()
    }
    seen_prompt_refs: list[str] = []
    factory_called = False

    class LocalLiveClient(EvalFakeClient):
        provider_name = "openai"

        def complete_structured(
            self,
            request: LLMStructuredRequest,
            *,
            config: object,
        ) -> LLMStructuredResponse:
            del config
            seen_prompt_refs.append(request.prompt_ref)
            if request.prompt_ref != "lifecycle_decision:v1":
                return super().complete_structured(request, config=None)  # type: ignore[arg-type]

            scenario_id = str(request.metadata["scenario_id"])
            output = expected_by_scenario[scenario_id].model_dump(mode="json")
            return LLMStructuredResponse(
                request_id=request.request_id,
                provider=self.provider_name,
                raw_text=json.dumps(output),
                valid_json=False,
                schema_valid=False,
            )

    def _factory(config: object) -> LocalLiveClient:
        del config
        nonlocal factory_called
        factory_called = True
        return LocalLiveClient()

    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MEMORII_ENABLE_LIVE_LLM_TESTS", "true")
    monkeypatch.setattr("memorii.tools.run_benchmark.LLMClientFactory.from_config", _factory)

    assert main(
        [
            "--suite",
            "memory_lifecycle_v1",
            "--mode",
            "llm",
            "--allow-live",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    assert factory_called is True
    assert seen_prompt_refs.count("lifecycle_decision:v1") == 5
