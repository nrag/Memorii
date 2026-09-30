"""Model tools over the durable runtime: thin, typed, closed.

Six tools serve the durable runtime view; host-only dispatch and admin
operations are deliberately not model tools. Every tool returns the
plain provider-work-state summary when no durable binding exists — the
boundary is stated, never blurred. No tool accepts SQL, store paths or
event JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.harness_state.binding import HermesRuntimeStatePorts
from memorii.core.harness_state.service import HarnessStateError

TOOL_MEMORII_RESUME_TASK = "memorii_resume_task"
TOOL_MEMORII_GET_EXECUTION_STATE = "memorii_get_execution_state"
TOOL_MEMORII_GET_SOLVER_STATE = "memorii_get_solver_state"
TOOL_MEMORII_RECORD_OBSERVATION = "memorii_record_observation"
TOOL_MEMORII_PROPOSE_STATE_CHANGE = "memorii_propose_state_change"
TOOL_MEMORII_RECORD_ACTION_RESULT = "memorii_record_action_result"

#: The complete durable-runtime tool registry; host-only operations are
#: excluded by design.
RUNTIME_MODEL_TOOLS: frozenset[str] = frozenset(
    {
        TOOL_MEMORII_RESUME_TASK,
        TOOL_MEMORII_GET_EXECUTION_STATE,
        TOOL_MEMORII_GET_SOLVER_STATE,
        TOOL_MEMORII_RECORD_OBSERVATION,
        TOOL_MEMORII_PROPOSE_STATE_CHANGE,
        TOOL_MEMORII_RECORD_ACTION_RESULT,
    }
)


class ToolCall(BaseModel):
    """One closed model-tool invocation."""

    name: str = Field(min_length=1)
    principal: str = Field(min_length=1)
    arguments: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)

    def validate_name(self) -> None:
        if self.name not in RUNTIME_MODEL_TOOLS:
            raise HarnessStateError(
                f"invalid_request: unknown model tool {self.name}"
            )


class ToolResult(BaseModel):
    """Typed tool outcome; denials never carry task-derived data."""

    name: str
    status: Literal["ok", "denied", "unavailable"]
    payload: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeModelTools:
    """Dispatch the six durable-runtime tools through the bound ports."""

    def __init__(self, ports: HermesRuntimeStatePorts) -> None:
        self._ports = ports

    def dispatch(self, call: ToolCall) -> ToolResult:
        call.validate_name()
        try:
            if call.name in (
                TOOL_MEMORII_RESUME_TASK,
                TOOL_MEMORII_GET_EXECUTION_STATE,
                TOOL_MEMORII_GET_SOLVER_STATE,
            ):
                envelope = self._ports.read_bound_state(principal=call.principal)
                if call.name == TOOL_MEMORII_GET_SOLVER_STATE:
                    payload: dict[str, object] = {
                        "solver_id": envelope.solver_id,
                        "category": envelope.solver_category,
                        "candidate": [
                            block.label for block in envelope.candidate_hypotheses
                        ],
                        "committed": [
                            block.label for block in envelope.committed_hypotheses
                        ],
                        "overlay": envelope.selected_overlay_id,
                        "frontier": [block.label for block in envelope.frontier],
                        "unexplained": [
                            block.label for block in envelope.unexplained_evidence
                        ],
                    }
                else:
                    payload = {
                        "task_id": envelope.task_id,
                        "revision": envelope.revision,
                        "status": envelope.status,
                        "goal": envelope.goal,
                        "execution_node": envelope.current_execution_node,
                        "execution_status": envelope.execution_status,
                        "pending_actions": list(envelope.pending_actions),
                        "omissions": list(envelope.omissions),
                    }
                return ToolResult(name=call.name, status="ok", payload=payload)
            # Observation/proposal/action-result effects are not yet
            # implemented command kinds at this slice: the tool states that
            # plainly rather than pretending success.
            return ToolResult(
                name=call.name,
                status="unavailable",
                payload={
                    "reason": "command effect not implemented at this slice",
                },
            )
        except HarnessStateError:
            return ToolResult(
                name=call.name,
                status="denied",
                payload={},
            )


__all__ = [
    "RUNTIME_MODEL_TOOLS",
    "RuntimeModelTools",
    "TOOL_MEMORII_GET_EXECUTION_STATE",
    "TOOL_MEMORII_GET_SOLVER_STATE",
    "TOOL_MEMORII_PROPOSE_STATE_CHANGE",
    "TOOL_MEMORII_RECORD_ACTION_RESULT",
    "TOOL_MEMORII_RECORD_OBSERVATION",
    "TOOL_MEMORII_RESUME_TASK",
    "ToolCall",
    "ToolResult",
]
