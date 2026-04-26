"""Deterministic frontier planner over persisted solver overlays."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.solver.models import NextTestAction
from memorii.domain.enums import SolverNodeStatus
from memorii.domain.solver_graph.overlays import SolverNodeOverlay
from memorii.stores.base.interfaces import OverlayStore, SolverGraphStore


class FrontierSelectionReason(str, Enum):
    HIGHEST_PRIORITY_FRONTIER = "highest_priority_frontier"
    NO_FRONTIER_FOUND = "no_frontier_found"
    FRONTIER_WITH_STRUCTURED_ACTION = "frontier_with_structured_action"
    FRONTIER_WITH_LEGACY_ACTION = "frontier_with_legacy_action"


class FrontierPlan(BaseModel):
    solver_run_id: str
    selected_node_id: str | None = None
    next_test_action: NextTestAction | None = None
    next_best_test: str | None = None
    reason: FrontierSelectionReason
    candidate_frontier_node_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SolverFrontierPlanner:
    """Select the next actionable solver frontier node from persisted overlays."""

    def select_next_frontier(
        self,
        *,
        solver_run_id: str,
        solver_store: SolverGraphStore,
        overlay_store: OverlayStore,
    ) -> FrontierPlan:
        latest_overlay = overlay_store.get_latest_version(solver_run_id)
        if latest_overlay is None:
            return FrontierPlan(
                solver_run_id=solver_run_id,
                reason=FrontierSelectionReason.NO_FRONTIER_FOUND,
            )

        candidates = [node for node in latest_overlay.node_overlays if self._is_candidate(node)]
        if not candidates:
            return FrontierPlan(
                solver_run_id=solver_run_id,
                reason=FrontierSelectionReason.NO_FRONTIER_FOUND,
            )

        ordered_candidates = sorted(candidates, key=self._candidate_sort_key)
        selected_overlay = ordered_candidates[0]

        solver_node = solver_store.get_node(solver_run_id, selected_overlay.node_id)
        if solver_node is None:
            return FrontierPlan(
                solver_run_id=solver_run_id,
                reason=FrontierSelectionReason.NO_FRONTIER_FOUND,
                candidate_frontier_node_ids=[candidate.node_id for candidate in ordered_candidates],
            )

        node_content = solver_node.content

        parsed_action: NextTestAction | None = None
        raw_action = node_content.get("next_test_action")
        if isinstance(raw_action, NextTestAction):
            parsed_action = raw_action
        elif isinstance(raw_action, dict):
            parsed_action = NextTestAction.model_validate(raw_action)

        next_best_test = node_content.get("next_best_test")
        next_best_test_text = next_best_test if isinstance(next_best_test, str) else None

        reason = FrontierSelectionReason.HIGHEST_PRIORITY_FRONTIER
        if parsed_action is not None:
            reason = FrontierSelectionReason.FRONTIER_WITH_STRUCTURED_ACTION
        elif next_best_test_text:
            reason = FrontierSelectionReason.FRONTIER_WITH_LEGACY_ACTION

        return FrontierPlan(
            solver_run_id=solver_run_id,
            selected_node_id=selected_overlay.node_id,
            next_test_action=parsed_action,
            next_best_test=next_best_test_text,
            reason=reason,
            candidate_frontier_node_ids=[candidate.node_id for candidate in ordered_candidates],
        )

    @staticmethod
    def _is_candidate(node: SolverNodeOverlay) -> bool:
        if node.reopenable:
            return True
        if node.status in {SolverNodeStatus.RESOLVED, SolverNodeStatus.MERGED, SolverNodeStatus.ARCHIVED}:
            return False
        return node.is_frontier or node.status == SolverNodeStatus.NEEDS_TEST or node.unexplained

    @staticmethod
    def _candidate_sort_key(node: SolverNodeOverlay) -> tuple[float, int, int, float, str]:
        return (
            -(node.frontier_priority or 0.0),
            0 if node.unexplained else 1,
            0 if node.reopenable else 1,
            node.belief,
            node.node_id,
        )
