from memorii.core.retrieval import RetrievalPlanner
from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope


def test_retrieval_planner_chooses_execution_memory_for_continue_execution() -> None:
    planner = RetrievalPlanner()
    plan = planner.build_plan(
        intent=RetrievalIntent.CONTINUE_EXECUTION,
        scope=RetrievalScope(task_id="task-1", execution_node_id="exec-1"),
    )

    domains = [query.domain for query in plan.queries]
    assert domains[0] == MemoryDomain.EXECUTION


def test_retrieval_planner_chooses_solver_episodic_semantic_for_debug() -> None:
    planner = RetrievalPlanner()
    plan = planner.build_plan(
        intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
        scope=RetrievalScope(task_id="task-1", execution_node_id="exec-1", solver_run_id="solver-1"),
    )

    domains = [query.domain for query in plan.queries]
    assert domains == [MemoryDomain.SOLVER, MemoryDomain.EPISODIC, MemoryDomain.SEMANTIC]


def test_retrieval_planner_includes_namespace_and_scope_filters() -> None:
    planner = RetrievalPlanner()
    plan = planner.build_plan(
        intent=RetrievalIntent.RESUME_TASK,
        scope=RetrievalScope(task_id="task-1", execution_node_id="exec-1", solver_run_id="solver-1", agent_id="agent-1"),
    )

    query = plan.queries[0]
    assert query.scope.task_id == "task-1"
    assert query.namespace.execution_node_id == "exec-1"
    assert query.namespace.agent_id == "agent-1"


def test_retrieval_planner_can_request_raw_transcript_explicitly() -> None:
    planner = RetrievalPlanner()
    plan = planner.build_plan(
        intent=RetrievalIntent.ANSWER_WITH_USER_CONTEXT,
        scope=RetrievalScope(task_id="task-1", thread_id="thread-1"),
        include_raw_transcript=True,
    )

    transcript_query = next(query for query in plan.queries if query.domain == MemoryDomain.TRANSCRIPT)
    assert transcript_query.require_raw_transcript is True
