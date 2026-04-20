"""Simple CLI/test harness adapter for local execution flows."""

from memorii.adapters.contracts import HarnessOutput
from memorii.adapters.events import HarnessEvent
from memorii.adapters.generic_json_adapter import GenericJSONHarnessAdapter
from memorii.domain.routing import InboundEventClass


class CLITestHarnessAdapter:
    """Minimal convenience adapter around generic adapter for tests and CLI scripts."""

    def __init__(self, delegate: GenericJSONHarnessAdapter) -> None:
        self._delegate = delegate

    def start_task(self, task_id: str, user_text: str) -> HarnessOutput:
        return self._delegate.start_task(task_id=task_id, payload={"text": user_text})

    def add_user_message(self, task_id: str, event_id: str, text: str) -> HarnessOutput:
        return self._delegate.step(
            HarnessEvent(
                event_id=event_id,
                task_id=task_id,
                event_type=InboundEventClass.USER_MESSAGE,
                payload={"text": text},
            )
        )

    def add_tool_result(self, task_id: str, event_id: str, status: str, detail: str) -> HarnessOutput:
        return self._delegate.step(
            HarnessEvent(
                event_id=event_id,
                task_id=task_id,
                event_type=InboundEventClass.TOOL_RESULT,
                payload={"status": status, "detail": detail},
            )
        )

    def add_execution_update(self, task_id: str, event_id: str, update: dict[str, object]) -> HarnessOutput:
        return self._delegate.step(
            HarnessEvent(
                event_id=event_id,
                task_id=task_id,
                event_type=InboundEventClass.EXECUTION_STATE_UPDATE,
                payload=update,
            )
        )

    def resume_task(self, task_id: str) -> dict[str, object]:
        return self._delegate.resume_task(task_id)

    def get_state(self, task_id: str) -> dict[str, object]:
        return self._delegate.get_state(task_id)
