"""Public runtime API contracts for harness integrations."""

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.execution import RuntimeObservationInput, RuntimeStepResult
from memorii.domain.solver_graph.state import ExecutionResumeState, SolverResumeState


class TaskInput(BaseModel):
    event_id: str
    payload: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RuntimeTaskState(BaseModel):
    task_id: str
    execution: ExecutionResumeState
    solver_runs: list[SolverResumeState] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StartTaskResult(BaseModel):
    task_id: str
    created_execution_node_id: str
    initial_step: RuntimeStepResult

    model_config = ConfigDict(extra="forbid")


class StepResult(BaseModel):
    result: RuntimeStepResult

    model_config = ConfigDict(extra="forbid")


class ResumeTaskResult(BaseModel):
    task_id: str
    state: RuntimeTaskState

    model_config = ConfigDict(extra="forbid")


class IngestEventRequest(BaseModel):
    task_id: str
    observation: RuntimeObservationInput

    model_config = ConfigDict(extra="forbid")
