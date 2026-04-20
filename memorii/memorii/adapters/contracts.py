"""Thin adapter protocols for harness integration."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from memorii.adapters.events import HarnessEvent


class HarnessOutput(BaseModel):
    """Minimal structured output returned to host harnesses."""

    task_id: str
    next_action: str | None = None
    solver_state_summary: str = ""
    unresolved_questions: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    candidate_decisions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class HarnessAdapter(Protocol):
    """Adapter contract that translates harness payloads and runtime responses."""

    def start_task(self, task_id: str, payload: dict[str, object]) -> HarnessOutput:
        """Start a task with harness input payload."""

    def step(self, event: HarnessEvent) -> HarnessOutput:
        """Process a harness step event."""

    def resume_task(self, task_id: str) -> dict[str, object]:
        """Resume task and return adapter-compatible state payload."""

    def get_state(self, task_id: str) -> dict[str, object]:
        """Retrieve task state for harness consumption."""
