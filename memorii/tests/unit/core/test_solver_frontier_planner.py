from datetime import UTC, datetime

from memorii.core.solver import SolverFrontierPlanner
from memorii.core.solver.frontier import FrontierSelectionReason
from memorii.domain.common import SolverNodeMetadata
from memorii.domain.enums import CommitStatus, SolverCreatedBy, SolverNodeStatus, SolverNodeType
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion
from memorii.stores.overlays import InMemoryOverlayStore
from memorii.stores.solver_graph import InMemorySolverGraphStore


NOW = datetime.now(UTC)


def _make_node(node_id: str, *, content: dict[str, object]) -> SolverNode:
    return SolverNode(
        id=node_id,
        type=SolverNodeType.ACTION,
        content=content,
        metadata=SolverNodeMetadata(
            created_at=NOW,
            created_by=SolverCreatedBy.SYSTEM,
            candidate_state=CommitStatus.COMMITTED,
        ),
    )


def _overlay(
    node_id: str,
    *,
    status: SolverNodeStatus = SolverNodeStatus.ACTIVE,
    priority: float | None = None,
    is_frontier: bool = False,
    unexplained: bool = False,
    reopenable: bool = False,
    belief: float = 0.5,
) -> SolverNodeOverlay:
    return SolverNodeOverlay(
        node_id=node_id,
        belief=belief,
        status=status,
        frontier_priority=priority,
        is_frontier=is_frontier,
        unexplained=unexplained,
        reopenable=reopenable,
        updated_at=NOW,
    )


def _append_overlay(store: InMemoryOverlayStore, solver_run_id: str, overlays: list[SolverNodeOverlay]) -> None:
    store.append_overlay_version(
        SolverOverlayVersion(
            version_id=f"ov:{solver_run_id}:{len(store.list_versions(solver_run_id))}",
            solver_run_id=solver_run_id,
            created_at=NOW,
            committed=True,
            node_overlays=overlays,
        )
    )


def test_no_overlay_returns_no_frontier() -> None:
    planner = SolverFrontierPlanner()
    plan = planner.select_next_frontier(
        solver_run_id="solver:none",
        solver_store=InMemorySolverGraphStore(),
        overlay_store=InMemoryOverlayStore(),
    )

    assert plan.selected_node_id is None
    assert plan.reason == FrontierSelectionReason.NO_FRONTIER_FOUND


def test_needs_test_frontier_selected_with_legacy_next_best_test() -> None:
    solver_run_id = "solver:needs-test"
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    planner = SolverFrontierPlanner()

    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node("node-1", content={"next_best_test": "rerun_targeted_test"}))
    _append_overlay(
        overlay_store,
        solver_run_id,
        [_overlay("node-1", status=SolverNodeStatus.NEEDS_TEST, priority=1.0, is_frontier=True)],
    )

    plan = planner.select_next_frontier(
        solver_run_id=solver_run_id,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    assert plan.selected_node_id == "node-1"
    assert plan.next_best_test == "rerun_targeted_test"
    assert plan.next_test_action is None
    assert plan.reason == FrontierSelectionReason.FRONTIER_WITH_LEGACY_ACTION


def test_structured_next_test_action_is_extracted() -> None:
    solver_run_id = "solver:structured"
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    planner = SolverFrontierPlanner()

    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(
        solver_run_id,
        _make_node(
            "node-1",
            content={
                "next_test_action": {
                    "action_type": "run_command",
                    "description": "Run flaky test repeatedly",
                    "expected_evidence": "Flake reproduces",
                }
            },
        ),
    )
    _append_overlay(
        overlay_store,
        solver_run_id,
        [_overlay("node-1", status=SolverNodeStatus.NEEDS_TEST, priority=1.0, is_frontier=True)],
    )

    plan = planner.select_next_frontier(
        solver_run_id=solver_run_id,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    assert plan.next_test_action is not None
    assert plan.next_test_action.action_type == "run_command"
    assert plan.reason == FrontierSelectionReason.FRONTIER_WITH_STRUCTURED_ACTION


def test_higher_frontier_priority_wins() -> None:
    solver_run_id = "solver:priority"
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    planner = SolverFrontierPlanner()

    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node("node-low", content={}))
    solver_store.upsert_node(solver_run_id, _make_node("node-high", content={}))
    _append_overlay(
        overlay_store,
        solver_run_id,
        [
            _overlay("node-low", status=SolverNodeStatus.NEEDS_TEST, priority=0.2, is_frontier=True),
            _overlay("node-high", status=SolverNodeStatus.NEEDS_TEST, priority=1.0, is_frontier=True),
        ],
    )

    plan = planner.select_next_frontier(
        solver_run_id=solver_run_id,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    assert plan.selected_node_id == "node-high"


def test_unexplained_beats_ordinary_candidate_on_tie() -> None:
    solver_run_id = "solver:unexplained"
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    planner = SolverFrontierPlanner()

    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node("node-ordinary", content={}))
    solver_store.upsert_node(solver_run_id, _make_node("node-unexplained", content={}))
    _append_overlay(
        overlay_store,
        solver_run_id,
        [
            _overlay("node-ordinary", priority=1.0, is_frontier=True, belief=0.5),
            _overlay("node-unexplained", priority=1.0, is_frontier=True, unexplained=True, belief=0.5),
        ],
    )

    plan = planner.select_next_frontier(
        solver_run_id=solver_run_id,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    assert plan.selected_node_id == "node-unexplained"


def test_lower_belief_wins_when_other_fields_tied() -> None:
    solver_run_id = "solver:belief"
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    planner = SolverFrontierPlanner()

    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node("node-high-belief", content={}))
    solver_store.upsert_node(solver_run_id, _make_node("node-low-belief", content={}))
    _append_overlay(
        overlay_store,
        solver_run_id,
        [
            _overlay("node-high-belief", priority=1.0, is_frontier=True, belief=0.9),
            _overlay("node-low-belief", priority=1.0, is_frontier=True, belief=0.2),
        ],
    )

    plan = planner.select_next_frontier(
        solver_run_id=solver_run_id,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    assert plan.selected_node_id == "node-low-belief"


def test_deterministic_tiebreaker_by_node_id() -> None:
    solver_run_id = "solver:tiebreak"
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    planner = SolverFrontierPlanner()

    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node("node-b", content={}))
    solver_store.upsert_node(solver_run_id, _make_node("node-a", content={}))
    _append_overlay(
        overlay_store,
        solver_run_id,
        [
            _overlay("node-b", priority=1.0, is_frontier=True, belief=0.3),
            _overlay("node-a", priority=1.0, is_frontier=True, belief=0.3),
        ],
    )

    plan = planner.select_next_frontier(
        solver_run_id=solver_run_id,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    assert plan.selected_node_id == "node-a"


def test_reopenable_node_can_be_selected_even_if_resolved() -> None:
    solver_run_id = "solver:reopenable"
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    planner = SolverFrontierPlanner()

    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node("node-resolved", content={"next_best_test": "recheck_input"}))
    solver_store.upsert_node(solver_run_id, _make_node("node-other", content={}))
    _append_overlay(
        overlay_store,
        solver_run_id,
        [
            _overlay("node-resolved", status=SolverNodeStatus.RESOLVED, priority=1.0, reopenable=True, belief=0.4),
            _overlay("node-other", status=SolverNodeStatus.RESOLVED, priority=0.5, reopenable=False, belief=0.1),
        ],
    )

    plan = planner.select_next_frontier(
        solver_run_id=solver_run_id,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    assert plan.selected_node_id == "node-resolved"
    assert plan.next_best_test == "recheck_input"
