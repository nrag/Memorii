from __future__ import annotations

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.llm_decision.models import EvalSnapshot
from memorii.core.llm_eval.golden import belief_golden_v1
from memorii.core.llm_eval.runner import OfflineLLMEvalRunner


REQUIRED_DOMAINS = {
    "domain:software_debugging",
    "domain:incident_investigation",
    "domain:architecture_decision_analysis",
    "domain:product_project_planning",
    "domain:research_literature_review",
    "domain:customer_support_operations",
    "domain:agent_task_execution",
}

REQUIRED_TASK_TYPES = {
    "task_type:root_cause_analysis",
    "task_type:bug_triage",
    "task_type:decision_review",
    "task_type:system_design",
    "task_type:roadmap_planning",
    "task_type:planning_diagnosis",
    "task_type:claim_validation",
    "task_type:support_triage",
    "task_type:customer_diagnosis",
    "task_type:solver_verification",
    "task_type:next_step_planning",
    "task_type:runtime_diagnosis",
    "task_type:state_management",
}


def _judge_review_with_constraints_snapshots() -> list[EvalSnapshot]:
    return [
        snapshot
        for snapshot in belief_golden_v1()
        if bool((snapshot.expected_output or {}).get("requires_judge_review") is True)
        and bool((snapshot.expected_output or {}).keys() - {"requires_judge_review"})
    ]


def _judge_only_snapshots() -> list[EvalSnapshot]:
    return [
        snapshot
        for snapshot in belief_golden_v1()
        if snapshot.expected_output is None or set((snapshot.expected_output or {}).keys()) == {"requires_judge_review"}
    ]


def _deterministic_snapshots() -> list[EvalSnapshot]:
    return [
        snapshot
        for snapshot in belief_golden_v1()
        if not bool((snapshot.expected_output or {}).get("requires_judge_review") is True)
    ]


def test_belief_golden_v1_has_minimum_snapshot_count() -> None:
    snapshots = belief_golden_v1()
    assert len(snapshots) >= 18


def test_belief_golden_v1_snapshot_ids_are_unique() -> None:
    snapshots = belief_golden_v1()
    snapshot_ids = [snapshot.snapshot_id for snapshot in snapshots]
    assert len(snapshot_ids) == len(set(snapshot_ids))


def test_belief_golden_v1_snapshots_validate() -> None:
    snapshots = belief_golden_v1()
    for snapshot in snapshots:
        validated = EvalSnapshot.model_validate(snapshot.model_dump(mode="json"))
        assert validated.snapshot_id == snapshot.snapshot_id


def test_belief_golden_v1_input_payloads_validate_as_belief_context() -> None:
    snapshots = belief_golden_v1()
    for snapshot in snapshots:
        context = BeliefUpdateContext.model_validate(snapshot.input_payload)
        assert context.decision.value


def test_belief_golden_v1_covers_required_domains() -> None:
    snapshots = belief_golden_v1()
    tags = {tag for snapshot in snapshots for tag in snapshot.tags}
    assert REQUIRED_DOMAINS.issubset(tags)


def test_belief_golden_v1_covers_required_task_types() -> None:
    snapshots = belief_golden_v1()
    tags = {tag for snapshot in snapshots for tag in snapshot.tags}
    assert REQUIRED_TASK_TYPES.issubset(tags)


def test_belief_golden_v1_every_snapshot_has_required_tag_categories() -> None:
    snapshots = belief_golden_v1()
    for snapshot in snapshots:
        assert any(tag.startswith("domain:") for tag in snapshot.tags)
        assert any(tag.startswith("task_type:") for tag in snapshot.tags)
        assert any(tag.startswith("belief_case:") for tag in snapshot.tags)


def test_belief_golden_v1_every_snapshot_has_required_metadata_fields() -> None:
    snapshots = belief_golden_v1()
    for snapshot in snapshots:
        context = BeliefUpdateContext.model_validate(snapshot.input_payload)
        metadata = context.metadata
        assert "hypothesis" in metadata
        assert "scenario" in metadata
        assert "evidence_summary" in metadata
        assert "missing_evidence_summary" in metadata
        assert metadata.get("golden_version") == "belief_v1"
        assert metadata.get("curation_tier") == "reviewed"


def test_belief_golden_v1_includes_evidence_and_missing_evidence_lists_when_required() -> None:
    snapshots = belief_golden_v1()
    for snapshot in snapshots:
        context = BeliefUpdateContext.model_validate(snapshot.input_payload)
        if context.evidence_count > 0:
            assert len(context.evidence_ids) >= 1
        if context.missing_evidence_count > 0:
            assert len(context.missing_evidence) >= 1


def test_offline_eval_runner_runs_deterministic_non_judge_belief_cases() -> None:
    runner = OfflineLLMEvalRunner()
    deterministic_snapshots = _deterministic_snapshots()

    report = runner.run_snapshots(deterministic_snapshots)

    assert report.total_cases == len(deterministic_snapshots)
    assert report.failed_cases == 0
    assert report.pass_rate_by_decision_point["belief_update"] == 1.0


def test_judge_review_with_constraints_cases_run_separately_and_are_marked() -> None:
    runner = OfflineLLMEvalRunner()
    judge_review_snapshots = _judge_review_with_constraints_snapshots()

    report = runner.run_snapshots(judge_review_snapshots)

    assert report.total_cases == len(judge_review_snapshots)
    assert report.total_cases >= 1
    assert all(result.requires_judge_review is True for result in report.results)


def test_judge_only_cases_run_separately_and_are_marked() -> None:
    runner = OfflineLLMEvalRunner()
    judge_only_snapshots = _judge_only_snapshots()

    report = runner.run_snapshots(judge_only_snapshots)

    assert report.total_cases == len(judge_only_snapshots)
    assert report.total_cases >= 1
    assert all(result.requires_judge_review is True for result in report.results)


def test_belief_golden_v1_covers_required_case_families() -> None:
    snapshots = belief_golden_v1()
    contexts = [BeliefUpdateContext.model_validate(snapshot.input_payload) for snapshot in snapshots]

    assert any(context.decision.value == "SUPPORTED" for context in contexts)
    assert any(context.decision.value == "REFUTED" for context in contexts)
    assert any(context.decision.value in {"INSUFFICIENT_EVIDENCE", "NEEDS_TEST"} for context in contexts)
    assert any(context.conflict_count > 0 for context in contexts)
    assert any(context.verifier_downgraded for context in contexts)


def test_belief_golden_v1_expected_outputs_have_sufficient_constraints() -> None:
    snapshots = belief_golden_v1()
    for snapshot in snapshots:
        expected_output = snapshot.expected_output
        if expected_output is None:
            continue
        keys = set(expected_output.keys())
        assert keys != set()
        assert keys != {"requires_judge_review"}


def test_every_refuted_case_expects_direction_decrease() -> None:
    snapshots = belief_golden_v1()
    for snapshot in snapshots:
        context = BeliefUpdateContext.model_validate(snapshot.input_payload)
        if context.decision.value == "REFUTED":
            expected_output = snapshot.expected_output or {}
            assert expected_output.get("direction") == "decrease"


def test_every_clean_supported_case_expects_direction_increase() -> None:
    snapshots = belief_golden_v1()
    for snapshot in snapshots:
        context = BeliefUpdateContext.model_validate(snapshot.input_payload)
        if context.decision.value != "SUPPORTED":
            continue
        if context.missing_evidence_count > 0:
            continue
        if context.conflict_count > 0:
            continue
        if context.verifier_downgraded:
            continue
        expected_output = snapshot.expected_output or {}
        assert expected_output.get("direction") == "increase"


def test_running_belief_golden_requires_no_live_llm_or_judge_calls() -> None:
    runner = OfflineLLMEvalRunner()

    report = runner.run_snapshots(belief_golden_v1())

    assert all(result.trace_id is not None for result in report.results)
    assert all(result.requires_judge_review is True or result.passed is True for result in report.results)
