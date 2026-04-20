"""Typed mapping records for Memorii memory directory."""

from pydantic import BaseModel, ConfigDict


class TaskExecutionGraphLink(BaseModel):
    task_id: str
    execution_graph_id: str

    model_config = ConfigDict(extra="forbid")


class ExecutionNodeSolverLink(BaseModel):
    task_id: str
    execution_node_id: str
    solver_run_id: str

    model_config = ConfigDict(extra="forbid")


class TranscriptTaskLink(BaseModel):
    task_id: str
    session_id: str | None = None
    thread_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class AgentMemoryPartitionLink(BaseModel):
    agent_id: str
    partition_key: str

    model_config = ConfigDict(extra="forbid")


class WritebackSourceLink(BaseModel):
    candidate_id: str
    task_id: str
    solver_run_id: str | None = None
    execution_node_id: str | None = None

    model_config = ConfigDict(extra="forbid")
