import pytest
from datetime import UTC, datetime, timedelta

from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import (
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    BenchmarkSystem,
    EndToEndFixture,
    RetrievalFixture,
    RetrievalFixtureMemoryItem,
    RoutingFixture,
    ScenarioExecutionLevel,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, TemporalValidityStatus
from memorii.core.benchmark.scenarios import ScenarioExecutor
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope
from memorii.domain.routing import InboundEvent, InboundEventClass
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def test_end_to_end_scenario_success_and_pollution_signals() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    by_system = {
        result.system: result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve"
    }

    assert by_system[BenchmarkSystem.MEMORII].observation.scenario_success is True
    assert by_system[BenchmarkSystem.MEMORII].observation.execution_level == ScenarioExecutionLevel.SYSTEM_LEVEL
    assert by_system[BenchmarkSystem.MEMORII].metrics.writeback_candidate_correctness == 1.0
    assert by_system[BenchmarkSystem.MEMORII].observation.writeback_candidate_ids == [
        "wb:solver:task:1:exec:task:1:root:evt:tool:failed"
    ]
    assert by_system[BenchmarkSystem.FLAT_RETRIEVAL_BASELINE].observation.semantic_pollution is True
    assert by_system[BenchmarkSystem.FLAT_RETRIEVAL_BASELINE].observation.user_memory_pollution is True


def test_end_to_end_observation_carries_expected_routing_fields() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    memorii_result = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve" and result.system == BenchmarkSystem.MEMORII
    )
    assert memorii_result.observation.expected_routed_domains
    assert memorii_result.observation.expected_blocked_domains == []
    assert memorii_result.observation.blocked_domains == []
    assert memorii_result.metrics.blocked_write_accuracy is None


def test_end_to_end_scenario_fails_when_routing_expectation_is_wrong() -> None:
    fixtures = load_benchmark_fixture_set()
    target = next(item for item in fixtures if item.scenario_id == "e2e_fail_debug_resolve")
    wrong_routing_fixture = BenchmarkScenarioFixture.model_validate(
        {
            **target.model_dump(mode="python"),
            "routing": {
                **target.routing.model_dump(mode="python"),
                "expected_domains": ["transcript"],
            },
        }
    )
    report = BenchmarkHarness().run(
        fixtures=[wrong_routing_fixture] + [item for item in fixtures if item.scenario_id != target.scenario_id]
    )
    memorii_result = next(
        result
        for result in report.scenario_results
        if result.system == BenchmarkSystem.MEMORII and result.scenario_id == target.scenario_id
    )
    assert memorii_result.observation.scenario_success is False


def test_end_to_end_baseline_writebacks_are_not_copied_from_routed_domains() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    baseline = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve" and result.system == BenchmarkSystem.FLAT_RETRIEVAL_BASELINE
    )
    assert set(baseline.observation.routed_domains) == {
        MemoryDomain.TRANSCRIPT,
        MemoryDomain.EXECUTION,
        MemoryDomain.SOLVER,
    }
    assert set(baseline.observation.writeback_candidate_domains) == {MemoryDomain.SEMANTIC, MemoryDomain.USER}


def test_end_to_end_requires_retrieval_fixture_for_storage_semantics() -> None:
    target = next(item for item in load_benchmark_fixture_set() if item.scenario_id == "e2e_fail_debug_resolve")
    invalid_fixture = BenchmarkScenarioFixture.model_validate(
        {
            **target.model_dump(mode="python"),
            "retrieval": None,
        }
    )
    with pytest.raises(ValueError, match="requires retrieval corpus"):
        ScenarioExecutor().run(fixture=invalid_fixture, system=BenchmarkSystem.MEMORII)


def test_end_to_end_seeding_preserves_item_namespace_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_seeded: list[object] = []
    from memorii.core.execution import RuntimeStepResult
    from memorii.core.solver.abstention import SolverDecision
    from memorii.domain.retrieval import RetrievalPlan
    from memorii.domain.writebacks import WritebackCandidate, WritebackType
    from memorii.domain.common import Provenance
    from memorii.domain.enums import CommitStatus, SourceType
    from memorii.domain.routing import ValidationState
    from datetime import UTC, datetime

    class FakeRuntimeStepService:
        def __init__(self, **kwargs):
            pass

        def seed_memory_object(self, memory_object):
            captured_seeded.append(memory_object)

        def step(self, **kwargs):
            return RuntimeStepResult(
                task_id="task:e2e",
                execution_node_id="exec:task:e2e:root",
                solver_run_id="solver:task:e2e:exec:task:e2e:root",
                retrieval_plan=RetrievalPlan(intent=RetrievalIntent.DEBUG_OR_INVESTIGATE),
                routed_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER],
                solver_decision=SolverDecision.SUPPORTED,
                follow_up_required=False,
                downgraded=False,
                writeback_candidates=[
                    WritebackCandidate(
                        candidate_id="wb:1",
                        writeback_type=WritebackType.EPISODIC,
                        target_domain=MemoryDomain.EPISODIC,
                        status=CommitStatus.CANDIDATE,
                        content={"summary": "ok"},
                        provenance=Provenance(
                            source_type=SourceType.DERIVED,
                            source_refs=["evt:1"],
                            created_at=datetime.now(UTC),
                            created_by="test",
                        ),
                        source_task_id="task:e2e",
                        validation_state=ValidationState.VALIDATED,
                        eligibility_reason="solver_resolved",
                    )
                ],
            )

    monkeypatch.setattr("memorii.core.benchmark.scenarios.RuntimeStepService", FakeRuntimeStepService)

    fixture = BenchmarkScenarioFixture(
        scenario_id="e2e_namespace_preserve",
        category=BenchmarkScenarioType.END_TO_END,
        retrieval=RetrievalFixture(
            query="question",
            intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
            scope=RetrievalScope(),
            top_k=2,
            corpus=[
                RetrievalFixtureMemoryItem(
                    item_id="ctx:1",
                    domain=MemoryDomain.SEMANTIC,
                    text="fact",
                    task_id="task:custom",
                    execution_node_id="exec:custom",
                    solver_run_id="solver:custom",
                ),
                RetrievalFixtureMemoryItem(
                    item_id="ctx:2",
                    domain=MemoryDomain.EPISODIC,
                    text="case",
                ),
            ],
            expected_relevant_ids=["ctx:1"],
        ),
        routing=RoutingFixture(
            inbound_event=InboundEvent(
                event_id="evt:1",
                event_class=InboundEventClass.TOOL_STATE_UPDATE,
                task_id="task:e2e",
                payload={"status": "failed"},
                timestamp=datetime.now(UTC),
            ),
            expected_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER],
        ),
        end_to_end=EndToEndFixture(
            task_id="task:e2e",
            expect_pipeline_success=True,
            expect_writeback_domains=[MemoryDomain.EPISODIC],
        ),
    )

    ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    custom = next(item for item in captured_seeded if item.memory_id == "ctx:1")
    fallback = next(item for item in captured_seeded if item.memory_id == "ctx:2")
    assert custom.namespace["task_id"] == "task:custom"
    assert custom.namespace["execution_node_id"] == "exec:custom"
    assert custom.namespace["solver_run_id"] == "solver:custom"
    assert custom.scope.value == "execution_node"
    assert fallback.namespace["task_id"] == "task:e2e"
    assert fallback.namespace["memory_domain"] == MemoryDomain.EPISODIC.value
    assert "execution_node_id" not in fallback.namespace
    assert "solver_run_id" not in fallback.namespace
    assert fallback.scope.value == "task"


def test_end_to_end_runtime_writeback_validation_metadata_is_used() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    memorii = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve" and result.system == BenchmarkSystem.MEMORII
    )
    assert memorii.observation.semantic_pollution is False
    assert memorii.observation.user_memory_pollution is False


def test_system_level_runtime_retrieval_path_applies_scope_candidate_validity_and_dedupe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    from memorii.core.execution.service import RuntimeStepService as RealRuntimeStepService

    class SpyRuntimeStepService:
        def __init__(self, **kwargs):
            self._inner = RealRuntimeStepService(**kwargs)

        def seed_memory_object(self, memory_object):
            return self._inner.seed_memory_object(memory_object)

        def step(self, **kwargs):
            result = self._inner.step(**kwargs)
            captured["retrieved_by_domain"] = result.retrieved_by_domain
            return result

    monkeypatch.setattr("memorii.core.benchmark.scenarios.RuntimeStepService", SpyRuntimeStepService)
    now = datetime.now(UTC)
    fixture = BenchmarkScenarioFixture(
        scenario_id="e2e_runtime_retrieval_filtering",
        category=BenchmarkScenarioType.END_TO_END,
        retrieval=RetrievalFixture(
            query="query",
            intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
            scope=RetrievalScope(task_id="task:rt"),
            top_k=4,
            corpus=[
                RetrievalFixtureMemoryItem(
                    item_id="keep-active",
                    domain=MemoryDomain.EXECUTION,
                    text="debug context",
                    task_id="task:rt",
                    execution_node_id="exec:task:rt:root",
                    solver_run_id="solver:task:rt:exec:task:rt:root",
                    status=CommitStatus.COMMITTED,
                ),
                RetrievalFixtureMemoryItem(
                    item_id="drop-candidate",
                    domain=MemoryDomain.SOLVER,
                    text="candidate memory",
                    task_id="task:rt",
                    execution_node_id="exec:task:rt:root",
                    solver_run_id="solver:task:rt:exec:task:rt:root",
                    status=CommitStatus.CANDIDATE,
                ),
                RetrievalFixtureMemoryItem(
                    item_id="drop-expired",
                    domain=MemoryDomain.EPISODIC,
                    text="old memory",
                    task_id="task:rt",
                    execution_node_id="exec:task:rt:root",
                    solver_run_id="solver:task:rt:exec:task:rt:root",
                    status=CommitStatus.COMMITTED,
                    validity_status=TemporalValidityStatus.EXPIRED,
                    valid_to=now - timedelta(days=1),
                ),
                RetrievalFixtureMemoryItem(
                    item_id="drop-out-of-scope",
                    domain=MemoryDomain.EXECUTION,
                    text="other task memory",
                    task_id="task:other",
                    execution_node_id="exec:task:other:root",
                    solver_run_id="solver:task:other:exec:task:other:root",
                    status=CommitStatus.COMMITTED,
                ),
                RetrievalFixtureMemoryItem(
                    item_id="dup-id",
                    domain=MemoryDomain.TRANSCRIPT,
                    text="dup in transcript",
                    task_id="task:rt",
                    execution_node_id="exec:task:rt:root",
                    solver_run_id="solver:task:rt:exec:task:rt:root",
                    status=CommitStatus.COMMITTED,
                ),
                RetrievalFixtureMemoryItem(
                    item_id="dup-id",
                    domain=MemoryDomain.EXECUTION,
                    text="dup in execution",
                    task_id="task:rt",
                    execution_node_id="exec:task:rt:root",
                    solver_run_id="solver:task:rt:exec:task:rt:root",
                    status=CommitStatus.COMMITTED,
                ),
            ],
            expected_relevant_ids=["keep-active"],
        ),
        routing=RoutingFixture(
                inbound_event=InboundEvent(
                    event_id="evt:rt",
                    event_class=InboundEventClass.TOOL_STATE_UPDATE,
                    task_id="task:rt",
                    payload={"status": "failed"},
                    timestamp=now,
                ),
            expected_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER],
        ),
        end_to_end=EndToEndFixture(
            task_id="task:rt",
            expect_pipeline_success=True,
            expect_writeback_domains=[MemoryDomain.EPISODIC],
        ),
    )

    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.execution_level == ScenarioExecutionLevel.SYSTEM_LEVEL
    retrieved_by_domain = captured["retrieved_by_domain"]
    flattened = [memory_id for ids in retrieved_by_domain.values() for memory_id in ids]
    assert "keep-active" in flattened
    assert "drop-candidate" not in flattened
    assert "drop-expired" not in flattened
    assert "drop-out-of-scope" not in flattened
    assert flattened.count("dup-id") == 1


def test_end_to_end_memorii_consumes_runtime_blocked_domains_and_writeback_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.execution import RuntimeStepResult
    from memorii.core.solver.abstention import SolverDecision
    from memorii.domain.retrieval import RetrievalPlan

    class FakeRuntimeStepService:
        def __init__(self, **kwargs):
            pass

        def seed_memory_object(self, memory_object):
            return None

        def step(self, **kwargs):
            return RuntimeStepResult(
                task_id="task:e2e",
                execution_node_id="exec:task:e2e:root",
                solver_run_id="solver:task:e2e:exec:task:e2e:root",
                retrieval_plan=RetrievalPlan(intent=RetrievalIntent.DEBUG_OR_INVESTIGATE),
                retrieval_plan_queries=["transcript", "execution"],
                retrieved_ids_by_domain_raw={"transcript": ["tx:1"], "execution": ["tx:1"]},
                retrieved_ids_by_domain_deduped={"transcript": ["tx:1"], "execution": []},
                retrieved_ids_deduped=["tx:1"],
                routed_domains=[MemoryDomain.TRANSCRIPT],
                blocked_domains=[MemoryDomain.SEMANTIC],
                blocked_reasons={"semantic": "raw_event"},
                solver_decision=SolverDecision.SUPPORTED,
                follow_up_required=False,
                downgraded=False,
                writeback_trace=[
                    {
                        "candidate_id": "wb:trace:1",
                        "target_domain": "episodic",
                        "status": "candidate",
                        "validation_state": "validated",
                    }
                ],
                writeback_candidates=[],
            )

    monkeypatch.setattr("memorii.core.benchmark.scenarios.RuntimeStepService", FakeRuntimeStepService)

    fixture = BenchmarkScenarioFixture(
        scenario_id="e2e_runtime_observability",
        category=BenchmarkScenarioType.END_TO_END,
        retrieval=RetrievalFixture(
            query="q",
            intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
            scope=RetrievalScope(task_id="task:e2e"),
            top_k=1,
            corpus=[
                RetrievalFixtureMemoryItem(
                    item_id="tx:1",
                    domain=MemoryDomain.TRANSCRIPT,
                    text="context",
                )
            ],
            expected_relevant_ids=["tx:1"],
        ),
        routing=RoutingFixture(
            inbound_event=InboundEvent(
                event_id="evt:e2e",
                event_class=InboundEventClass.TOOL_RESULT,
                task_id="task:e2e",
                payload={"status": "failed"},
                timestamp=datetime.now(UTC),
            ),
            expected_domains=[MemoryDomain.TRANSCRIPT],
            expected_blocked_domains=[MemoryDomain.SEMANTIC],
        ),
        end_to_end=EndToEndFixture(
            task_id="task:e2e",
            expect_pipeline_success=True,
            expect_writeback_domains=[MemoryDomain.EPISODIC],
            expect_writeback_candidate_ids=["wb:trace:1"],
        ),
    )
    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.blocked_domains == [MemoryDomain.SEMANTIC]
    assert observation.writeback_candidate_ids == ["wb:trace:1"]
    assert observation.runtime_observability_status == "supported"
    assert observation.scenario_success is True


def test_end_to_end_marks_runtime_observability_unsupported_when_trace_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.execution import RuntimeStepResult
    from memorii.core.solver.abstention import SolverDecision
    from memorii.domain.retrieval import RetrievalPlan

    class FakeRuntimeStepService:
        def __init__(self, **kwargs):
            pass

        def seed_memory_object(self, memory_object):
            return None

        def step(self, **kwargs):
            return RuntimeStepResult(
                task_id="task:e2e",
                execution_node_id="exec:task:e2e:root",
                solver_run_id="solver:task:e2e:exec:task:e2e:root",
                retrieval_plan=RetrievalPlan(intent=RetrievalIntent.DEBUG_OR_INVESTIGATE),
                routed_domains=[MemoryDomain.TRANSCRIPT],
                solver_decision=SolverDecision.SUPPORTED,
                follow_up_required=False,
                downgraded=False,
            )

    monkeypatch.setattr("memorii.core.benchmark.scenarios.RuntimeStepService", FakeRuntimeStepService)
    fixture = next(item for item in load_benchmark_fixture_set() if item.scenario_id == "e2e_fail_debug_resolve")
    observation = ScenarioExecutor().run(fixture=fixture, system=BenchmarkSystem.MEMORII)
    assert observation.runtime_observability_status == "unsupported"
    assert "writeback_trace" in observation.runtime_observability_missing
    assert observation.scenario_success is None
