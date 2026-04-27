"""Shared work-state selection helpers."""

from memorii.core.work_state.models import WorkStateRecord, WorkStateStatus
from memorii.core.work_state.service import WorkStateService


class WorkStateSelector:
    """Select recall-relevant work states using canonical scope precedence."""

    def __init__(self, work_state_service: WorkStateService | None) -> None:
        self._work_state_service = work_state_service

    def select_recall_work_states(
        self,
        *,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
    ) -> list[WorkStateRecord]:
        if self._work_state_service is None:
            return []

        included_statuses = [
            WorkStateStatus.ACTIVE,
            WorkStateStatus.CANDIDATE,
            WorkStateStatus.PAUSED,
        ]
        if task_id is not None:
            return self._work_state_service.list_states(task_id=task_id, statuses=included_statuses)
        if session_id is not None:
            return self._work_state_service.list_states(session_id=session_id, statuses=included_statuses)
        if user_id is not None:
            return self._work_state_service.list_states(user_id=user_id, statuses=included_statuses)
        return self._work_state_service.list_states(statuses=included_statuses)
