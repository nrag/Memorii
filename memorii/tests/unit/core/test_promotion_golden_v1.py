from __future__ import annotations

from memorii.core.llm_decision.models import EvalSnapshot
from memorii.core.llm_eval.golden import promotion_golden_v1
from memorii.core.llm_eval.runner import OfflineLLMEvalRunner
from memorii.core.promotion.models import PromotionContext


def test_promotion_golden_v1_has_minimum_snapshot_count() -> None:
    snapshots = promotion_golden_v1()
    assert len(snapshots) >= 14


def test_promotion_golden_v1_snapshot_ids_are_unique() -> None:
    snapshots = promotion_golden_v1()
    snapshot_ids = [snapshot.snapshot_id for snapshot in snapshots]
    assert len(snapshot_ids) == len(set(snapshot_ids))


def test_promotion_golden_v1_snapshots_validate() -> None:
    snapshots = promotion_golden_v1()
    for snapshot in snapshots:
        validated = EvalSnapshot.model_validate(snapshot.model_dump(mode="json"))
        assert validated.snapshot_id == snapshot.snapshot_id


def test_promotion_golden_v1_inputs_validate_as_promotion_context() -> None:
    snapshots = promotion_golden_v1()
    for snapshot in snapshots:
        context = PromotionContext.model_validate(snapshot.input_payload)
        assert context.candidate_id.startswith("cand:")


def test_promotion_golden_v1_covers_required_domains() -> None:
    snapshots = promotion_golden_v1()
    tags = {tag for snapshot in snapshots for tag in snapshot.tags}
    required_domains = {
        "domain:software_engineering",
        "domain:product_project_management",
        "domain:customer_support_operations",
        "domain:personal_assistant",
        "domain:research_analysis",
        "domain:decision_making_architecture",
        "domain:debugging_incident_investigation",
    }
    assert required_domains.issubset(tags)


def test_promotion_golden_v1_covers_required_task_types() -> None:
    snapshots = promotion_golden_v1()
    tags = {tag for snapshot in snapshots for tag in snapshot.tags}
    required_task_types = {
        "task_type:interaction_style",
        "task_type:temporary_planning_preference",
        "task_type:implementation",
        "task_type:root_cause_analysis",
        "task_type:decision_making",
        "task_type:system_design",
        "task_type:project_planning",
        "task_type:preference_inference",
        "task_type:customer_follow_up",
        "task_type:literature_review",
        "task_type:planning",
        "task_type:memory_maintenance",
    }
    assert required_task_types.issubset(tags)


def test_promotion_golden_v1_every_snapshot_has_required_tag_categories() -> None:
    snapshots = promotion_golden_v1()
    for snapshot in snapshots:
        assert any(tag.startswith("domain:") for tag in snapshot.tags)
        assert any(tag.startswith("task_type:") for tag in snapshot.tags)
        assert any(tag.startswith("memory_class:") for tag in snapshot.tags)


def test_offline_eval_runner_runs_full_promotion_golden_set() -> None:
    snapshots = promotion_golden_v1()
    runner = OfflineLLMEvalRunner()

    report = runner.run_snapshots(snapshots)

    assert report.total_cases == len(snapshots)
    assert report.failed_cases == 0


def test_offline_eval_runner_reports_deterministic_pass_rate() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(promotion_golden_v1())

    assert "promotion" in report.pass_rate_by_decision_point
    assert report.pass_rate_by_decision_point["promotion"] == 1.0


def test_inferred_preference_case_is_marked_for_judge_review() -> None:
    runner = OfflineLLMEvalRunner()
    snapshots = [
        snapshot
        for snapshot in promotion_golden_v1()
        if snapshot.snapshot_id == "promotion:v1:inferred-repeated-preference"
    ]

    report = runner.run_snapshots(snapshots)

    assert report.results[0].requires_judge_review is True


def test_duplicate_merge_placeholder_is_marked_for_judge_review() -> None:
    runner = OfflineLLMEvalRunner()
    snapshots = [
        snapshot
        for snapshot in promotion_golden_v1()
        if snapshot.snapshot_id == "promotion:v1:duplicate-merge-placeholder"
    ]

    report = runner.run_snapshots(snapshots)

    assert report.results[0].requires_judge_review is True


def test_running_promotion_golden_requires_no_live_llm_or_judge_calls() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(promotion_golden_v1())

    assert all(result.trace_id is not None for result in report.results)
    assert all(result.requires_judge_review is False or result.passed is True for result in report.results)
