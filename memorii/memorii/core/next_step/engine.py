"""Next-step selection engine."""

from memorii.core.decision_state.models import DecisionState, DecisionStatus
from memorii.core.decision_state.service import DecisionStateService
from memorii.core.next_step.models import NextStepRequest, NextStepResult
from memorii.core.recall import summarize_work_states
from memorii.core.solver import SolverFrontierPlanner
from memorii.core.work_state.models import WorkStateEvent, WorkStateKind
from memorii.core.work_state.selector import WorkStateSelector
from memorii.core.work_state.service import WorkStateService
from memorii.stores.base.interfaces import OverlayStore, SolverGraphStore


class NextStepEngine:
    def __init__(
        self,
        *,
        work_state_service: WorkStateService | None = None,
        decision_state_service: DecisionStateService | None = None,
        solver_frontier_planner: SolverFrontierPlanner | None = None,
        solver_store: SolverGraphStore | None = None,
        overlay_store: OverlayStore | None = None,
    ) -> None:
        self._work_state_service = work_state_service
        self._work_state_selector = WorkStateSelector(work_state_service)
        self._decision_state_service = decision_state_service
        self._solver_frontier_planner = solver_frontier_planner
        self._solver_store = solver_store
        self._overlay_store = overlay_store

    def get_next_step(self, request: NextStepRequest) -> NextStepResult:
        scope = {
            "task_id": request.task_id,
            "session_id": request.session_id,
            "user_id": request.user_id,
        }
        effective_solver_run_id, solver_run_resolution_source = self._resolve_effective_solver_run_id(
            solver_run_id=request.solver_run_id,
            task_id=request.task_id,
            session_id=request.session_id,
        )

        if effective_solver_run_id is None:
            fallback_result = self._build_work_state_next_step_fallback(
                session_id=request.session_id,
                task_id=request.task_id,
                user_id=request.user_id,
                scope=scope,
            )
            return fallback_result.model_copy(
                update={
                    "based_on_solver_run_id": None,
                    "based_on_solver_node_id": None,
                    "planner_used": False,
                    "planner_reason": "no_solver_run_resolved",
                    "candidate_frontier_node_ids": [],
                    "requested_solver_run_id": request.solver_run_id,
                    "resolved_solver_run_id": None,
                    "solver_run_resolution_source": solver_run_resolution_source,
                }
            )

        if not self._planner_dependencies_ready():
            fallback_result = self._build_work_state_next_step_fallback(
                session_id=request.session_id,
                task_id=request.task_id,
                user_id=request.user_id,
                scope=scope,
            )
            return fallback_result.model_copy(
                update={
                    "based_on_solver_run_id": effective_solver_run_id,
                    "based_on_solver_node_id": None,
                    "planner_used": False,
                    "planner_reason": "planner_not_configured",
                    "candidate_frontier_node_ids": [],
                    "requested_solver_run_id": request.solver_run_id,
                    "resolved_solver_run_id": effective_solver_run_id,
                    "solver_run_resolution_source": solver_run_resolution_source,
                }
            )

        frontier_plan = self._solver_frontier_planner.select_next_frontier(
            solver_run_id=effective_solver_run_id,
            solver_store=self._solver_store,
            overlay_store=self._overlay_store,
        )

        if frontier_plan.selected_node_id is not None:
            if frontier_plan.next_test_action is not None:
                next_step: dict[str, object] = {
                    "action_type": frontier_plan.next_test_action.action_type,
                    "description": frontier_plan.next_test_action.description,
                    "confidence": 0.6,
                    "reason": frontier_plan.reason.value,
                    "evidence_ids": [],
                    "expected_evidence": frontier_plan.next_test_action.expected_evidence,
                    "success_condition": frontier_plan.next_test_action.success_condition,
                    "failure_condition": frontier_plan.next_test_action.failure_condition,
                    "required_tool": frontier_plan.next_test_action.required_tool,
                    "target_ref": frontier_plan.next_test_action.target_ref,
                }
            elif frontier_plan.next_best_test:
                next_step = {
                    "action_type": "run_test",
                    "description": frontier_plan.next_best_test,
                    "confidence": 0.55,
                    "reason": frontier_plan.reason.value,
                    "evidence_ids": [],
                }
            else:
                next_step = {
                    "action_type": "inspect_frontier",
                    "description": "Inspect the selected solver frontier node before continuing.",
                    "confidence": 0.45,
                    "reason": frontier_plan.reason.value,
                    "evidence_ids": [],
                }
            return NextStepResult(
                next_step=next_step,
                based_on_solver_run_id=effective_solver_run_id,
                based_on_solver_node_id=frontier_plan.selected_node_id,
                based_on_work_state_id=None,
                planner_used=True,
                planner_reason=frontier_plan.reason.value,
                candidate_frontier_node_ids=frontier_plan.candidate_frontier_node_ids,
                requested_solver_run_id=request.solver_run_id,
                resolved_solver_run_id=effective_solver_run_id,
                solver_run_resolution_source=solver_run_resolution_source,
                scope=scope,
            )

        fallback_result = self._build_work_state_next_step_fallback(
            session_id=request.session_id,
            task_id=request.task_id,
            user_id=request.user_id,
            scope=scope,
        )
        return fallback_result.model_copy(
            update={
                "based_on_solver_run_id": effective_solver_run_id,
                "based_on_solver_node_id": None,
                "planner_used": False,
                "planner_reason": "no_frontier_found",
                "candidate_frontier_node_ids": frontier_plan.candidate_frontier_node_ids,
                "requested_solver_run_id": request.solver_run_id,
                "resolved_solver_run_id": effective_solver_run_id,
                "solver_run_resolution_source": solver_run_resolution_source,
            }
        )

    def _build_work_state_next_step_fallback(
        self,
        *,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        scope: dict[str, str | None],
    ) -> NextStepResult:
        selected_work_states = self._work_state_selector.select_recall_work_states(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )
        work_state_summaries = summarize_work_states(
            selected_work_states,
            events_by_state_id=self._list_events_by_work_state_id(selected_work_states),
        )
        if not work_state_summaries:
            return NextStepResult(
                next_step={
                    "action_type": "ask_user",
                    "description": "No active work state found. Ask the user what they want to do next.",
                    "confidence": 0.2,
                    "reason": "no_active_work_state",
                    "evidence_ids": [],
                },
                based_on_work_state_id=None,
                planner_used=False,
                planner_reason="",
                solver_run_resolution_source="none",
                scope=scope,
            )

        selected_state = work_state_summaries[0]
        action_type = "continue_research"
        description = "Continue collecting evidence and summarize what changed."
        if selected_state.kind == WorkStateKind.TASK_EXECUTION:
            action_type = "continue_task"
            description = "Continue the active task and record progress when a meaningful step completes."
        elif selected_state.kind == WorkStateKind.INVESTIGATION:
            action_type = "inspect_failure"
            description = "Inspect the latest failure or missing evidence before committing a conclusion."
        elif selected_state.kind == WorkStateKind.DECISION:
            return NextStepResult(
                next_step=self._get_decision_next_step(selected_state),
                based_on_work_state_id=selected_state.work_state_id,
                planner_used=False,
                planner_reason="",
                solver_run_resolution_source="none",
                scope=scope,
            )
        return NextStepResult(
            next_step={
                "action_type": action_type,
                "description": description,
                "confidence": 0.4,
                "reason": "frontier_planner_not_yet_enabled",
                "evidence_ids": list(selected_state.source_event_ids),
            },
            based_on_work_state_id=selected_state.work_state_id,
            planner_used=False,
            planner_reason="",
            solver_run_resolution_source="none",
            scope=scope,
        )

    def _get_decision_next_step(self, selected_state) -> dict[str, object]:
        if self._decision_state_service is None:
            return {
                "action_type": "clarify_decision_criteria",
                "description": "Clarify options, criteria, and constraints before choosing.",
                "confidence": 0.4,
                "reason": "frontier_planner_not_yet_enabled",
                "evidence_ids": list(selected_state.source_event_ids),
                "decision_state_id": None,
            }

        decisions = self._decision_state_service.list_decisions(
            work_state_id=selected_state.work_state_id,
            statuses=[DecisionStatus.OPEN, DecisionStatus.DECIDED],
        )
        decision = self._select_relevant_decision(decisions)
        if decision is None:
            return {
                "action_type": "open_decision_state",
                "description": "Open a decision state for this decision work.",
                "confidence": 0.3,
                "reason": "decision_state_missing",
                "evidence_ids": list(selected_state.source_event_ids),
                "decision_state_id": None,
            }

        if not decision.options:
            return {
                "action_type": "add_decision_options",
                "description": "Add the options under consideration before making a recommendation.",
                "confidence": 0.45,
                "reason": "decision_options_missing",
                "evidence_ids": [evidence.evidence_id for evidence in decision.evidence],
                "decision_state_id": decision.decision_id,
            }

        if not decision.criteria:
            return {
                "action_type": "add_decision_criteria",
                "description": "Add decision criteria and weights before comparing options.",
                "confidence": 0.45,
                "reason": "decision_criteria_missing",
                "evidence_ids": [evidence.evidence_id for evidence in decision.evidence],
                "decision_state_id": decision.decision_id,
            }

        if not decision.evidence:
            return {
                "action_type": "add_decision_evidence",
                "description": "Add evidence for, against, or neutral to the options.",
                "confidence": 0.45,
                "reason": "decision_evidence_missing",
                "evidence_ids": [],
                "decision_state_id": decision.decision_id,
            }

        if decision.current_recommendation is None:
            return {
                "action_type": "set_decision_recommendation",
                "description": "Set a current recommendation based on the available options, criteria, and evidence.",
                "confidence": 0.5,
                "reason": "decision_recommendation_missing",
                "evidence_ids": [evidence.evidence_id for evidence in decision.evidence],
                "decision_state_id": decision.decision_id,
            }

        if decision.final_decision is None:
            return {
                "action_type": "finalize_decision",
                "description": "Finalize the decision or record why it remains open.",
                "confidence": 0.55,
                "reason": "decision_ready_to_finalize",
                "evidence_ids": [evidence.evidence_id for evidence in decision.evidence],
                "decision_state_id": decision.decision_id,
            }

        return {
            "action_type": "record_outcome",
            "description": "Record the decision outcome on the work state.",
            "confidence": 0.55,
            "reason": "decision_already_decided",
            "evidence_ids": [evidence.evidence_id for evidence in decision.evidence],
            "decision_state_id": decision.decision_id,
        }

    def _select_relevant_decision(self, decisions: list[DecisionState]) -> DecisionState | None:
        open_decision = next((decision for decision in decisions if decision.status == DecisionStatus.OPEN), None)
        if open_decision is not None:
            return open_decision
        return next((decision for decision in decisions if decision.status == DecisionStatus.DECIDED), None)

    def _list_events_by_work_state_id(self, work_states) -> dict[str, list[WorkStateEvent]]:
        if self._work_state_service is None:
            return {}
        return {
            state.work_state_id: self._work_state_service.list_work_state_events(state.work_state_id)
            for state in work_states
        }

    def _planner_dependencies_ready(self) -> bool:
        return (
            self._solver_frontier_planner is not None
            and self._solver_store is not None
            and self._overlay_store is not None
        )

    def _resolve_effective_solver_run_id(
        self,
        *,
        solver_run_id: str | None,
        task_id: str | None,
        session_id: str | None,
    ) -> tuple[str | None, str]:
        if solver_run_id is not None:
            return solver_run_id, "explicit"
        if self._work_state_service is None:
            return None, "none"
        if task_id is not None:
            resolved_by_task = self._work_state_service.resolve_solver_run_id(task_id=task_id)
            if resolved_by_task is not None:
                return resolved_by_task, "task_binding"
        if session_id is not None:
            resolved_by_session = self._work_state_service.resolve_solver_run_id(session_id=session_id)
            if resolved_by_session is not None:
                return resolved_by_session, "session_binding"
        return None, "none"
