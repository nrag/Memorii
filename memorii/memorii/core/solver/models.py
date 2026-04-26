"""Shared solver schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class NextTestAction(BaseModel):
    action_type: Literal[
        "inspect_file",
        "run_command",
        "ask_user",
        "search_memory",
        "call_tool",
        "delegate",
        "wait",
    ]
    description: str
    expected_evidence: str | None = None
    success_condition: str | None = None
    failure_condition: str | None = None
    required_tool: str | None = None
    target_ref: str | None = None

    model_config = ConfigDict(extra="forbid")
