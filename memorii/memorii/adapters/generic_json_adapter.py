"""Generic JSON-based harness adapter."""

from memorii.adapters.contracts import HarnessOutput
from memorii.adapters.events import HarnessEvent, to_runtime_observation
from memorii.api.models import TaskInput
from memorii.core.execution import RuntimeStepResult
from memorii.api.service import MemoriiRuntimeAPI


class GenericJSONHarnessAdapter:
    """Stateless translation wrapper between JSON harness payloads and runtime API."""

    def __init__(self, runtime_api: MemoriiRuntimeAPI) -> None:
        self._runtime_api = runtime_api

    def start_task(self, task_id: str, payload: dict[str, object]) -> HarnessOutput:
        result = self._runtime_api.start_task(
            task_id=task_id,
            input=TaskInput(event_id=f"start:{task_id}", payload=payload),
        )
        return self._from_step_result(result.initial_step)

    def step(self, event: HarnessEvent) -> HarnessOutput:
        step_result = self._runtime_api.step(task_id=event.task_id, observation=to_runtime_observation(event)).result
        return self._from_step_result(step_result)

    def resume_task(self, task_id: str) -> dict[str, object]:
        resume = self._runtime_api.resume_task(task_id)
        return resume.model_dump(mode="json")

    def get_state(self, task_id: str) -> dict[str, object]:
        state = self._runtime_api.get_state(task_id)
        return state.model_dump(mode="json")

    def _from_step_result(self, step_result: RuntimeStepResult) -> HarnessOutput:
        return HarnessOutput(
            task_id=step_result.task_id,
            next_action=step_result.next_action,
            solver_state_summary=step_result.solver_state_summary,
            unresolved_questions=step_result.unresolved_questions,
            required_tests=step_result.required_tests,
            candidate_decisions=step_result.candidate_decisions,
        )
