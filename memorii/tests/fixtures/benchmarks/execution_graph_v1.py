"""Execution graph benchmark v1 fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.execution_graph_decision import (
    ExecutionGraphExpectation,
    ExecutionGraphScenario,
)
from memorii.domain.enums import ExecutionEdgeType, ExecutionNodeStatus, ExecutionNodeType
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode


def load_execution_graph_v1_fixture_set() -> list[ExecutionGraphScenario]:
    return [
        _scenario(
            scenario_id="execution_simple_ready_frontier",
            task="continue the ready parser implementation",
            family="stable_ready_frontier",
            nodes=[
                _node("exec:parser:impl", "Implement parser", ExecutionNodeStatus.READY, 2),
                _node("exec:parser:tests", "Add parser tests", ExecutionNodeStatus.NOT_STARTED, 1),
            ],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:parser:impl"],
                active_frontier_node_ids=["exec:parser:impl"],
                resumed_node_id="exec:parser:impl",
                next_action_tokens=["parser", "impl"],
            ),
        ),
        _scenario(
            scenario_id="execution_simple_blocked_dependency",
            task="identify blocked work before continuing auth rollout",
            family="stable_blocked_dependency",
            nodes=[
                _node("exec:auth:migration", "Run auth migration", ExecutionNodeStatus.BLOCKED, 2),
                _node("exec:auth:secret", "Provision auth secret", ExecutionNodeStatus.READY, 1),
            ],
            edges=[_edge("edge:auth:secret-blocks-migration", "exec:auth:secret", "exec:auth:migration", ExecutionEdgeType.BLOCKS)],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:auth:secret"],
                active_frontier_node_ids=["exec:auth:secret"],
                blocked_node_ids=["exec:auth:migration"],
                resumed_node_id="exec:auth:secret",
                next_action_tokens=["auth", "secret"],
            ),
        ),
        _scenario(
            scenario_id="execution_done_node_not_frontier",
            task="continue checkout work after completed schema design",
            family="stable_done_suppression",
            nodes=[
                _node("exec:checkout:schema", "Design checkout schema", ExecutionNodeStatus.DONE, 3),
                _node("exec:checkout:worker", "Implement checkout worker", ExecutionNodeStatus.READY, 2),
            ],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:checkout:worker"],
                active_frontier_node_ids=["exec:checkout:worker"],
                resumed_node_id="exec:checkout:worker",
                next_action_tokens=["checkout", "worker"],
            ),
        ),
        _scenario(
            scenario_id="execution_waiting_node_blocks_next_step",
            task="continue release gate after external review",
            family="stable_waiting_node",
            nodes=[
                _node("exec:release:review", "External security review", ExecutionNodeStatus.WAITING, 3),
                _node("exec:release:notes", "Draft release notes", ExecutionNodeStatus.READY, 1),
            ],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:release:notes"],
                active_frontier_node_ids=["exec:release:notes"],
                blocked_node_ids=["exec:release:review"],
                resumed_node_id="exec:release:notes",
                next_action_tokens=["release", "notes"],
            ),
        ),
        _scenario(
            scenario_id="execution_abandoned_branch_suppressed",
            task="resume import work after the CSV branch was abandoned in favor of parquet",
            family="abandoned_work_suppression",
            nodes=[
                _node("exec:import:csv-fast-path", "CSV import fast path", ExecutionNodeStatus.RUNNING, 4),
                _node("exec:import:parquet-path", "Parquet import path", ExecutionNodeStatus.READY, 2),
            ],
            recent_events=[
                "The CSV fast path branch was abandoned after corrupt row handling failed.",
                "The parquet path is the accepted continuation.",
            ],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:import:parquet-path"],
                active_frontier_node_ids=["exec:import:parquet-path"],
                abandoned_node_ids=["exec:import:csv-fast-path"],
                resumed_node_id="exec:import:parquet-path",
                next_action_tokens=["parquet", "path"],
                discriminative=True,
            ),
        ),
        _scenario(
            scenario_id="execution_resumed_work_continuation",
            task="continue the resumed billing migration work",
            family="resumed_work_continuation",
            nodes=[
                _node("exec:billing:old-branch", "Old billing migration branch", ExecutionNodeStatus.RUNNING, 4),
                _node("exec:billing:resumed-checkpoint", "Resumed billing migration checkpoint", ExecutionNodeStatus.READY, 2),
            ],
            recent_events=[
                "The old branch was parked after tests diverged.",
                "The resumed checkpoint contains the verified continuation plan.",
            ],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:billing:resumed-checkpoint"],
                active_frontier_node_ids=["exec:billing:resumed-checkpoint"],
                abandoned_node_ids=["exec:billing:old-branch"],
                resumed_node_id="exec:billing:resumed-checkpoint",
                require_resumed_node=True,
                next_action_tokens=["resumed", "checkpoint"],
                discriminative=True,
            ),
        ),
        _scenario(
            scenario_id="execution_wrong_dependency_direction",
            task="unblock deployment by choosing the prerequisite work",
            family="dependency_direction",
            nodes=[
                _node("exec:deploy:ship", "Ship deployment", ExecutionNodeStatus.READY, 4),
                _node("exec:deploy:config", "Finalize deployment config", ExecutionNodeStatus.READY, 1),
            ],
            edges=[
                _edge("edge:deploy:ship-depends-config", "exec:deploy:ship", "exec:deploy:config", ExecutionEdgeType.DEPENDS_ON)
            ],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:deploy:config"],
                active_frontier_node_ids=["exec:deploy:config"],
                blocked_node_ids=["exec:deploy:ship"],
                resumed_node_id="exec:deploy:config",
                next_action_tokens=["deployment", "config"],
                discriminative=True,
            ),
        ),
        _scenario(
            scenario_id="execution_stale_branch_avoidance",
            task="continue notification implementation using the latest accepted branch",
            family="stale_branch_avoidance",
            nodes=[
                _node("exec:notify:v1-polling", "Notification polling implementation", ExecutionNodeStatus.RUNNING, 4),
                _node("exec:notify:v2-webhook", "Notification webhook implementation", ExecutionNodeStatus.READY, 2),
            ],
            recent_events=[
                "Polling v1 was superseded after webhook design was accepted.",
                "Webhook v2 is the latest accepted implementation path.",
            ],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:notify:v2-webhook"],
                active_frontier_node_ids=["exec:notify:v2-webhook"],
                stale_node_ids=["exec:notify:v1-polling"],
                resumed_node_id="exec:notify:v2-webhook",
                next_action_tokens=["webhook", "implementation"],
                discriminative=True,
            ),
        ),
        _scenario(
            scenario_id="execution_handoff_continuity",
            task="pick up Maya's handoff for the search pagination bug",
            family="task_handoff_continuity",
            nodes=[
                _node("exec:search:triage", "Search pagination triage", ExecutionNodeStatus.RUNNING, 4),
                _node("exec:search:handoff-fix", "Maya handoff fix for pagination cursor", ExecutionNodeStatus.READY, 2),
            ],
            recent_events=[
                "Maya handed off the cursor fix and said triage is complete.",
                "The next action is to implement the cursor fix from the handoff.",
            ],
            expectation=ExecutionGraphExpectation(
                selected_node_ids=["exec:search:handoff-fix"],
                active_frontier_node_ids=["exec:search:handoff-fix"],
                stale_node_ids=["exec:search:triage"],
                resumed_node_id="exec:search:handoff-fix",
                next_action_tokens=["cursor", "fix"],
                discriminative=True,
            ),
        ),
    ]


def _scenario(
    *,
    scenario_id: str,
    task: str,
    family: str,
    nodes: list[ExecutionNode],
    expectation: ExecutionGraphExpectation,
    edges: list[ExecutionEdge] | None = None,
    recent_events: list[str] | None = None,
) -> ExecutionGraphScenario:
    return ExecutionGraphScenario(
        scenario_id=scenario_id,
        task=task,
        family=family,
        nodes=nodes,
        edges=edges or [],
        recent_events=recent_events or [],
        expectation=expectation,
    )


def _node(
    node_id: str,
    title: str,
    status: ExecutionNodeStatus,
    minutes: int,
) -> ExecutionNode:
    stamp = datetime(2026, 1, 1, 12, minutes, tzinfo=UTC)
    return ExecutionNode(
        id=node_id,
        type=ExecutionNodeType.WORK_ITEM,
        title=title,
        description=title,
        status=status,
        created_at=stamp,
        updated_at=stamp,
    )


def _edge(edge_id: str, src: str, dst: str, edge_type: ExecutionEdgeType) -> ExecutionEdge:
    stamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return ExecutionEdge(
        id=edge_id,
        src=src,
        dst=dst,
        type=edge_type,
        created_at=stamp,
        updated_at=stamp,
    )
